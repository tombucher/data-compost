import os
import json
import mimetypes
import logging
from datetime import datetime
from pathlib import Path
import stat
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from PIL import Image
import cv2
import numpy as np
from moviepy import VideoFileClip
import librosa
import PyPDF2
from docx import Document
import nltk
from nltk.data import find
from nltk.sentiment import SentimentIntensityAnalyzer
import pytesseract
import colorgram
from langdetect import detect
import math

from modules.config import CONFIG

# torch / transformers / torchvision sont lourds (~600 Mo) et optionnels.
# Si absents, l'analyse vidéo dégrade gracieusement (pas de captioning BLIP).
try:
    import torch  # noqa: F401
    import torchvision.transforms as transforms
    from transformers import BlipProcessor, BlipForConditionalGeneration
    BLIP_AVAILABLE = True
except ImportError as _blip_import_error:
    transforms = None
    BlipProcessor = None
    BlipForConditionalGeneration = None
    BLIP_AVAILABLE = False
    logging.warning(
        "torch/transformers indisponibles — captioning vidéo désactivé (%s)",
        _blip_import_error,
    )

logger = logging.getLogger(__name__)

# Liste des ressources à vérifier
resources = ['tokenizers/punkt', 'taggers/averaged_perceptron_tagger', 'sentiment/vader_lexicon']

for resource in resources:
    try:
        find(resource)
        print(f"{resource} already installed.")
    except LookupError:
        print(f"Downloading {resource}...")
        nltk.download(resource.split('/')[-1])


# Catégories de fichiers
FILE_CATEGORIES = {
    "image": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg"],
    "audio": [".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a"],
    "video": [".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm"],
    "text": [".txt", ".md", ".rtf", ".csv"],
    "document": [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".webloc"],
    "creative": [".psd", ".ai", ".indd", ".xd", ".sketch", ".fig", ".ttf", ".otf"],
    "system": [".sys", ".dll", ".ini", ".config"],
    "compressed": [".zip", ".rar", ".7z", ".tar", ".gz"],
    "executable": [".exe", ".app", ".bat", ".sh", ".com"]
}


def numpy_to_python(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.int64):
        return int(obj)
    if isinstance(obj, np.float64):
        return float(obj)
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')

def get_file_category(file_path):
    p = Path(file_path)
    ext = p.suffix.lower()

    if p.name.startswith('.'):
        return "hidden"

    for category, extensions in FILE_CATEGORIES.items():
        if ext in extensions:
            return category

    # Extension inconnue, on l'ignore
    logger.info(f"Extension inconnue ignorée: {ext} pour le fichier {file_path}")
    return None  # Retourne None pour les fichiers inconnus


def get_common_metadata(file_path):
    p = Path(file_path)
    stat_info = p.stat()
    mime_type, _ = mimetypes.guess_type(str(p))

    return {
        "name": p.name,
        "path": str(p.resolve()),
        "size": stat_info.st_size,
        "created_at": datetime.fromtimestamp(stat_info.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
        "accessed_at": datetime.fromtimestamp(stat_info.st_atime).isoformat(),
        "mime_type": mime_type,
        "permissions": stat.filemode(stat_info.st_mode),
        "owner": stat_info.st_uid,
        "group": stat_info.st_gid,
    }

def apply_colormap(saliency_map):
    return cv2.applyColorMap(saliency_map, cv2.COLORMAP_JET)

def create_heatmap(saliency_map, alpha=0.5):
    heatmap = cv2.applyColorMap(saliency_map, cv2.COLORMAP_JET)
    return cv2.addWeighted(heatmap, alpha, cv2.cvtColor(saliency_map, cv2.COLOR_GRAY2BGR), 1 - alpha, 0)

def analyze_image(file_path):
    file_path = Path(file_path)
    ext = file_path.suffix
    if ext.lower() == '.svg':
        file_size = file_path.stat().st_size
        return {
            "dimensions": (1, 1),  # valeur par défaut
            "format": "SVG",
            "mode": None,
            "saliency_map": None,
            "dominant_colors": [],  # liste vide au lieu de None
            "quality": 1,  # valeur par défaut
            "description": "SVG file"
        }

    try:
        # Open image with Pillow for metadata
        with Image.open(str(file_path)) as pil_img:
            # Récupérer les dimensions originales
            orig_width, orig_height = pil_img.size
            format = pil_img.format
            mode = pil_img.mode
            
            if orig_width * orig_height > 2000 * 1500:  # Seuil réduit à 2000x1500
                # Ratio de redimensionnement plus agressif
                ratio = min(1500 / orig_width, 1200 / orig_height)
                width = int(orig_width * ratio)
                height = int(orig_height * ratio)
                pil_img = pil_img.resize((width, height), Image.LANCZOS)
                logger.info(f"Image {file_path} redimensionnée de {orig_width}x{orig_height} à {width}x{height}")
                # Sauvegarder temporairement l'image redimensionnée
                temp_path = file_path.with_suffix(file_path.suffix + "_temp.jpg")
                pil_img.save(str(temp_path), quality=70)  # Qualité réduite pour économiser de l'espace
                img_path_for_cv = str(temp_path)
            else:
                width, height = orig_width, orig_height
                img_path_for_cv = str(file_path)

        # Read image with OpenCV for processing
        cv_image = cv2.imread(img_path_for_cv)
        if cv_image is None:
            raise ValueError(f"Failed to load image: {file_path}")

        # Create output directory
        output_dir = file_path.parent / CONFIG.paths.saliency_subdir
        output_dir.mkdir(parents=True, exist_ok=True)

        # Saliency map generation
        try:
            # Pour OpenCV 4.5+
            saliency_detector = cv2.saliency.StaticSaliencySpectralResidual.create()
            success, saliency_map = saliency_detector.computeSaliency(cv_image)
        except AttributeError:
            try:
                # Alternative pour OpenCV 4.x
                from cv2.saliency import StaticSaliencySpectralResidual_create
                saliency_detector = StaticSaliencySpectralResidual_create()
                success, saliency_map = saliency_detector.computeSaliency(cv_image)
            except (AttributeError, ImportError):
                # Fallback avec méthode personnalisée
                gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
                blur = cv2.GaussianBlur(gray, (21, 21), 0)
                saliency_map = blur  # Simple alternative
                success = True

        if not success:
            raise ValueError("Failed to compute saliency map")

        # Normalize saliency map to 0-255 range
        saliency_map_normalized = cv2.normalize(saliency_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

        # Generate saliency visualizations
        base_filename = file_path.stem

        # 1. Grayscale saliency map
        grayscale_path = output_dir / f"{base_filename}_saliency_gray.png"
        cv2.imwrite(str(grayscale_path), saliency_map_normalized)

        # 2. Colored saliency map
        colored_saliency = cv2.applyColorMap(saliency_map_normalized, cv2.COLORMAP_JET)
        colored_path = output_dir / f"{base_filename}_saliency_color.png"
        cv2.imwrite(str(colored_path), colored_saliency)

        # 3. Raw saliency map (float32)
        raw_path = output_dir / f"{base_filename}_saliency_raw.npy"
        np.save(str(raw_path), saliency_map)

        # Supprimer le fichier temporaire si créé
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()

        # Extract dominant colors
        colors = colorgram.extract(str(file_path), 5)
        dominant_colors = [(color.rgb.r, color.rgb.g, color.rgb.b) for color in colors]

        # Calculate image quality
        file_size = file_path.stat().st_size
        quality = (width * height) / file_size

        # Generate description (placeholder)
        image_description = pytesseract.image_to_string(Image.open(str(file_path)))

        # Prepare JSON data
        data = {
            "original_image": str(file_path),
            "dimensions": (orig_width, orig_height),  # Dimensions originales
            "processed_dimensions": (width, height),  # Dimensions traitées
            "format": format,
            "mode": mode,
            "saliency_map_gray": str(grayscale_path),
            "saliency_map_color": str(colored_path),
            "saliency_map_raw": str(raw_path),
            "dominant_colors": dominant_colors,
            "quality": quality,
            "description": image_description
        }

        return data

    except (IOError, OSError, Exception) as e:
        print(f"Error analyzing image: {e}")
        return None


# Fonction pour calculer intelligemment le nombre d'images à extraire en fonction de la durée de la vidéo
def calculate_num_frames(duration):
    if duration <= 30:
        return max(5, int(duration / 2))  # Minimum de 5 images pour les vidéos courtes
    elif duration <= 1800:  # Moins de 30 minutes
        return max(10, int(math.log(duration) * 5))
    else:
        return max(30, int(math.log(duration) * 10))  # Maximum de 30 images pour les vidéos longues


# Fonction principale d'analyse vidéo
def analyze_video(file_path):
    with VideoFileClip(file_path) as video:
        # Extraire les métadonnées de la vidéo
        duration = video.duration
        fps = video.fps
        size = video.size

        # Calculer le nombre d'images à extraire
        num_frames = calculate_num_frames(duration)

        # Extraire des images clés
        frames = [video.get_frame(t) for t in np.linspace(0, duration, num_frames)]

        frame_descriptions = []

        if BLIP_AVAILABLE:
            # Charger le modèle BLIP pour générer des descriptions d'images
            processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-base")
            model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-base")

            # Générer des descriptions pour les images clés
            for frame in frames:
                img_pil = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                inputs = processor(img_pil, return_tensors="pt")
                out = model.generate(**inputs)
                description = processor.decode(out[0], skip_special_tokens=True)
                frame_descriptions.append(description)
        else:
            logging.info("BLIP indisponible — descriptions vidéo omises pour %s", file_path)

        # Générer un résumé textuel basé sur les descriptions des images
        summary = ". ".join(frame_descriptions) if frame_descriptions else ""

    # Retourner toutes les informations collectées
    return {
        "duration": duration,
        "fps": fps,
        "size": size,
        "frame_descriptions": frame_descriptions,
        "summary": summary
    }


def analyze_audio(file_path):
    try:
        # Essayer avec librosa si disponible
        import librosa
        try:
            y, sr = librosa.load(file_path)
            duration = librosa.get_duration(y=y, sr=sr)
            return {
                "duration": duration,
                "sample_rate": sr,
                "tempo": 120,  # Valeur par défaut
                "genre": "Unknown",
                "quality": 0.8,
                "sentiment": "Neutral"
            }
        except Exception:
            # Fallback sans numba
            pass
            
    except ImportError:
        pass
        
    # Version alternative sans librosa/numba
    import wave
    try:
        with wave.open(file_path, 'rb') as wf:
            # Récupérer les propriétés de base
            n_channels = wf.getnchannels()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            
            # Calculer la durée
            duration = n_frames / framerate if framerate > 0 else 0
            
            return {
                "duration": duration,
                "sample_rate": framerate,
                "tempo": 120,  # Valeur par défaut
                "genre": "Unknown",
                "quality": 0.8,
                "sentiment": "Neutral"
            }
    except Exception as e:
        # Pour les formats non-wav
        return {
            "duration": 180,  # Valeur par défaut
            "sample_rate": 44100,
            "tempo": 120,
            "genre": "Unknown",
            "quality": 0.8,
            "sentiment": "Neutral"
        }

def analyze_document(file_path):
    file_path = Path(file_path)
    ext = file_path.suffix
    if ext.lower() == '.pdf':
        with open(file_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            num_pages = len(reader.pages)
            text = reader.pages[0].extract_text()[:1000]  # Extract first 1000 characters
    elif ext.lower() in ['.doc', '.docx']:
        doc = Document(file_path)
        num_pages = len(doc.paragraphs)
        text = '\n'.join([p.text for p in doc.paragraphs])[:1000]
    else:
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                text = file.read(1000)
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as file:
                    text = file.read(1000)
            except Exception as e:
                logging.error(f"Impossible de lire le fichier {file_path}: {str(e)}")
                return None
        num_pages = 1

    word_count = len(text.split())
    char_count = len(text)
    
    try:
        language = detect(text)
    except:
        language = "unknown"

    sentiment = SentimentIntensityAnalyzer().polarity_scores(text)

    return {
        "num_pages": num_pages,
        "preview": text,
        "word_count": word_count,
        "char_count": char_count,
        "language": language,
        "sentiment": sentiment
    }

def analyze_file(file_path):
    category = get_file_category(file_path)
    
    # Si la catégorie est None, on ignore le fichier
    if category is None:
        return None
    
    common_metadata = get_common_metadata(file_path)
    
    additional_data = {}
    try:
        if category == "image":
            additional_data = analyze_image(file_path)
        elif category == "video":
            additional_data = analyze_video(file_path)
        elif category == "audio":
            additional_data = analyze_audio(file_path)
        elif category in ["text", "document"]:
            additional_data = analyze_document(file_path)
    except Exception as e:
        logging.error(f"Erreur lors de l'analyse de {file_path}: {str(e)}")
        additional_data = {"error": str(e)}

    return {
        "common_metadata": common_metadata,
        "category": category,
        "additional_data": additional_data,
    }

def count_files(directory):
    """Compte le nombre total de fichiers dans le répertoire et ses sous-répertoires."""
    return sum(1 for _ in Path(directory).rglob('*') if _.is_file())

def analyze_directory(directory, visualization_queue=None):
    results = []
    directory = Path(directory)
    files_to_analyze = [p for p in directory.rglob('*') if p.is_file()]

    total_files = len(files_to_analyze)

    with ThreadPoolExecutor(max_workers=os.cpu_count()) as executor:
        futures = [executor.submit(analyze_file, file_path) for file_path in files_to_analyze]

        with tqdm(total=total_files, desc="Analyzing files", unit="file") as pbar:
            for future in as_completed(futures):
                result = future.result()
                if result is not None:
                    results.append(result)
                    if visualization_queue:
                        file_name = result['common_metadata']['name']
                        file_size = result['common_metadata']['size']
                        category = result['category']
                        visualization_queue.put((file_name, file_size, category))
                pbar.update(1)

    # Sauvegardez les résultats dans un fichier
    output_path = CONFIG.paths.output_root / 'analysis_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=4, default=numpy_to_python)

    logger.info(f"Résultats d'analyse exportés vers {output_path}")
    return str(output_path)

def main():
    directory = input("Entrez le chemin du répertoire à analyser : ")
    results = analyze_directory(directory)

    # Exporter les résultats en JSON
    output_path = CONFIG.paths.output_root / 'analysis_results.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=4)

    logger.info(f"Résultats exportés vers {output_path}")
    return output_path

if __name__ == "__main__":
    directory = Path(__file__).resolve().parent.parent.parent / 'data' / 'test'
    analyze_directory(directory)
