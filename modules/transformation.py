import json
import time
import random
from pathlib import Path
from PIL import Image
import cv2
import numpy as np
import nltk
from nltk.corpus import wordnet
from scipy.ndimage import gaussian_filter
import io

from modules.analyze import analyze_file
from modules.create_silos import create_silos
from modules.config import CONFIG


nltk.download('wordnet', quiet=True)

# Fonction de configuration simplifiée
def load_config():
    project_root = Path(__file__).resolve().parent.parent
    return {
        'output_dir': project_root / 'data' / 'output',
        'data_dir': project_root / 'data',
        'silos_dir': project_root / 'data' / 'output' / 'silos',
    }

config = load_config()

def load_saliency_map(saliency_path):
    return cv2.imread(saliency_path, cv2.IMREAD_GRAYSCALE)

def create_simple_saliency_map(image_path):
    """Crée une carte de saillance simple à partir d'une image."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            # Si l'image ne peut pas être lue, retourner une carte par défaut
            return np.ones((100, 100), dtype=np.uint8) * 128
            
        # Convertir en niveaux de gris
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        # Appliquer un flou gaussien
        blur = cv2.GaussianBlur(gray, (21, 21), 0)
        
        # Essayer d'amplifier les contours pour une meilleure saillance
        edges = cv2.Canny(blur, 50, 150)
        result = cv2.addWeighted(blur, 0.7, edges, 0.3, 0)
        
        return result
    except Exception as e:
        print(f"Erreur lors de la création d'une carte de saillance simple: {e}")
        return np.ones((100, 100), dtype=np.uint8) * 128  # Valeur par défaut

def pixelate_image(image_path, saliency_map, intensity):
    """Pixelise une image avec une taille de bloc modulée par la saillance et l'intensité (0-1)."""
    try:
        # Ouvrir l'image avec PIL
        img = Image.open(image_path)
        
        # Convertir en tableau numpy pour traitement
        img_array = np.array(img)
        
        # Vérifier que l'image est correctement chargée
        if img_array.size == 0:
            print(f"Erreur: Image vide pour {image_path}")
            return img  # Retourner l'image originale
        
        # Dimensions de l'image
        if len(img_array.shape) == 3:  # Image couleur
            height, width, _ = img_array.shape
        else:  # Image en niveaux de gris
            height, width = img_array.shape
        
        # Redimensionner la carte de saillance pour correspondre à l'image
        if saliency_map is not None and saliency_map.size > 0:
            try:
                # Pour être sûr d'avoir une carte en couleur
                if len(saliency_map.shape) == 2:  # Si en niveaux de gris
                    # Convertir la carte en JET colormap pour avoir des zones colorées
                    saliency_color = cv2.applyColorMap(saliency_map, cv2.COLORMAP_JET)
                else:
                    saliency_color = saliency_map.copy()
                
                # Redimensionner pour correspondre à l'image
                saliency_color = cv2.resize(saliency_color, (width, height))
                
                # S'assurer que c'est en format BGR
                if len(saliency_color.shape) == 2:
                    saliency_color = cv2.cvtColor(saliency_color, cv2.COLOR_GRAY2BGR)
                
                # Convertir en HSV pour mieux manipuler les couleurs
                saliency_hsv = cv2.cvtColor(saliency_color, cv2.COLOR_BGR2HSV)
                
            except Exception as e:
                print(f"Erreur lors de la préparation de la carte de saillance: {e}")
                saliency_color = np.zeros((height, width, 3), dtype=np.uint8)
                saliency_hsv = np.zeros((height, width, 3), dtype=np.uint8)
        else:
            # Créer une carte colorée aléatoire si aucune n'est fournie
            saliency_color = np.zeros((height, width, 3), dtype=np.uint8)
            
            # Remplir avec des valeurs aléatoires pour varier les effets
            for i in range(3):  # BGR
                saliency_color[:,:,i] = np.random.randint(0, 255, (height, width), dtype=np.uint8)
            
            saliency_hsv = cv2.cvtColor(saliency_color, cv2.COLOR_BGR2HSV)
        
        # Ajuster l'intensité globale
        enhanced_intensity = min(1.0, intensity * 1.5)
        
        # Créer une copie de l'image originale pour le résultat
        result = img_array.copy()
        
        # Taille de bloc de base pour la pixellisation
        base_block_size = max(4, int(8 * enhanced_intensity))
        
        # Préparer une image floutée pour l'effet de flou
        if len(img_array.shape) == 3:
            blurred = cv2.GaussianBlur(img_array, (15, 15), 0)
        else:
            blurred = cv2.GaussianBlur(img_array, (15, 15), 0)
        
        # Créer une image en niveaux de gris pour le tramage
        if len(img_array.shape) == 3:
            grayscale = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            grayscale = img_array.copy()
        
        # Traiter l'image par blocs
        for y in range(0, height, base_block_size):
            for x in range(0, width, base_block_size):
                # Définir les limites du bloc
                y_end = min(y + base_block_size, height)
                x_end = min(x + base_block_size, width)
                
                # Récupérer les valeurs de couleur moyennes de la carte de saillance pour ce bloc
                block_hsv = saliency_hsv[y:y_end, x:x_end].mean(axis=(0, 1))
                hue = block_hsv[0]  # Teinte (0-179 en OpenCV)
                sat = block_hsv[1]  # Saturation (0-255)
                val = block_hsv[2]  # Valeur/Luminosité (0-255)
                
                # Déterminer l'effet à appliquer en fonction de la teinte (H dans HSV)
                # Rouge: 0-20 ou 160-179, Vert: 40-80, Bleu clair: 90-110, Bleu foncé: 110-140
                
                # Effet à appliquer selon la couleur dominante du bloc
                if (hue < 20 or hue > 160) and sat > 100:  # Rouge - conserver les détails
                    # Ne rien faire - garder l'original
                    pass
                
                elif 35 < hue < 85 and sat > 70:  # Vert - pixellisation
                    # Calculer la taille du bloc en fonction de la valeur et de l'intensité
                    # Plus lumineux = blocs plus petits
                    block_size = max(3, int(base_block_size * (1 - val/255 * 0.5)))
                    
                    # Adapter les limites du bloc pour éviter les débordements
                    for by in range(y, y_end, block_size):
                        by_end = min(by + block_size, y_end)
                        for bx in range(x, x_end, block_size):
                            bx_end = min(bx + block_size, x_end)
                            
                            # Calculer et appliquer la couleur moyenne
                            if len(img_array.shape) == 3:
                                color = img_array[by:by_end, bx:bx_end].mean(axis=(0, 1))
                                result[by:by_end, bx:bx_end] = color
                            else:
                                color = img_array[by:by_end, bx:bx_end].mean()
                                result[by:by_end, bx:bx_end] = color
                
                elif 85 < hue < 110 and sat > 70:  # Bleu clair - flou
                    # Calculer l'intensité du flou
                    blur_strength = enhanced_intensity * (1 - val/255)
                    
                    # Mélanger l'original et le flou
                    if len(img_array.shape) == 3:
                        for c in range(img_array.shape[2]):
                            result[y:y_end, x:x_end, c] = img_array[y:y_end, x:x_end, c] * (1 - blur_strength) + \
                                                         blurred[y:y_end, x:x_end, c] * blur_strength
                    else:
                        result[y:y_end, x:x_end] = img_array[y:y_end, x:x_end] * (1 - blur_strength) + \
                                                 blurred[y:y_end, x:x_end] * blur_strength
                
                elif 110 < hue < 140 and sat > 70:  # Bleu foncé - tramage/demi-teinte
                    # Taille des points de la trame
                    dot_size = max(1, int(2 + 3 * enhanced_intensity * (1 - val/255)))
                    spacing = dot_size * 2
                    
                    # Créer un masque blanc pour ce bloc
                    if len(img_array.shape) == 3:
                        mask = np.ones((y_end - y, x_end - x, 3), dtype=np.uint8) * 255
                    else:
                        mask = np.ones((y_end - y, x_end - x), dtype=np.uint8) * 255
                    
                    # Dessiner des points dans le masque
                    for dy in range(0, y_end - y, spacing):
                        cy = min(dy + spacing//2, y_end - y - 1)
                        for dx in range(0, x_end - x, spacing):
                            cx = min(dx + spacing//2, x_end - x - 1)
                            
                            # Valeur de gris à cette position (plus sombre = point plus grand)
                            if len(img_array.shape) == 3:
                                gray_val = grayscale[y + cy, x + cx]
                            else:
                                gray_val = img_array[y + cy, x + cx]
                            
                            # Rayon du point proportionnel à l'intensité inverse
                            radius = int((255 - gray_val) / 255 * dot_size)
                            
                            if radius > 0:
                                # Limites pour le dessin du cercle
                                y_min = max(0, cy - radius)
                                y_max = min(y_end - y, cy + radius + 1)
                                x_min = max(0, cx - radius)
                                x_max = min(x_end - x, cx + radius + 1)
                                
                                # Dessiner le cercle noir
                                for py in range(y_min, y_max):
                                    for px in range(x_min, x_max):
                                        if (px - cx)**2 + (py - cy)**2 <= radius**2:
                                            if len(img_array.shape) == 3:
                                                mask[py, px] = [0, 0, 0]  # Noir
                                            else:
                                                mask[py, px] = 0  # Noir
                    
                    # Appliquer le masque au bloc
                    result[y:y_end, x:x_end] = mask
                
                else:  # Autres couleurs ou faible saturation - effet aléatoire mélangé
                    # Effet basé sur la valeur (luminosité)
                    effect_intensity = enhanced_intensity * (1 - val/255)
                    
                    if effect_intensity > 0.3:  # Seuil pour appliquer un effet
                        # Choisir un effet aléatoirement
                        rand_effect = np.random.randint(0, 4)
                        
                        if rand_effect == 0:  # Pixellisation
                            # Taille du bloc
                            block_size = max(2, int(base_block_size * effect_intensity))
                            
                            # Adapter les limites du bloc
                            for by in range(y, y_end, block_size):
                                by_end = min(by + block_size, y_end)
                                for bx in range(x, x_end, block_size):
                                    bx_end = min(bx + block_size, x_end)
                                    
                                    # Calculer et appliquer la couleur moyenne
                                    if len(img_array.shape) == 3:
                                        color = img_array[by:by_end, bx:bx_end].mean(axis=(0, 1))
                                        result[by:by_end, bx:bx_end] = color
                                    else:
                                        color = img_array[by:by_end, bx:bx_end].mean()
                                        result[by:by_end, bx:bx_end] = color
                        
                        elif rand_effect == 1:  # Flou
                            # Appliquer un flou
                            if len(img_array.shape) == 3:
                                for c in range(img_array.shape[2]):
                                    result[y:y_end, x:x_end, c] = img_array[y:y_end, x:x_end, c] * (1 - effect_intensity) + \
                                                                blurred[y:y_end, x:x_end, c] * effect_intensity
                            else:
                                result[y:y_end, x:x_end] = img_array[y:y_end, x:x_end] * (1 - effect_intensity) + \
                                                         blurred[y:y_end, x:x_end] * effect_intensity
                        
                        elif rand_effect == 2:  # Grain/Bruit
                            # Ajouter du bruit
                            noise = np.random.randint(-30, 30, size=result[y:y_end, x:x_end].shape) * effect_intensity
                            result[y:y_end, x:x_end] = np.clip(result[y:y_end, x:x_end] + noise, 0, 255)
                        
                        elif rand_effect == 3:  # Contraste
                            # Ajuster le contraste
                            contrast = 1.0 + effect_intensity
                            result[y:y_end, x:x_end] = np.clip(
                                (result[y:y_end, x:x_end].astype(float) - 128) * contrast + 128, 
                                0, 255
                            ).astype(np.uint8)
        
        # Convertir en image PIL
        result_img = Image.fromarray(result.astype(np.uint8))
        
        # Retourner l'image transformée
        return result_img
        
    except Exception as e:
        print(f"Erreur lors de la transformation de l'image {image_path}: {str(e)}")
        import traceback
        traceback.print_exc()
        # En cas d'échec, retourner l'image originale
        try:
            return Image.open(image_path)
        except:
            print(f"Impossible de charger l'image originale {image_path}")
            return Image.new('RGB', (100, 100), color=(0, 0, 0))


def simple_datamosh(video_path, saliency_map, intensity):
    cap = cv2.VideoCapture(video_path)
    frames = []
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    
    saliency_map = cv2.resize(saliency_map, (frames[0].shape[1], frames[0].shape[0]))
    
    for i in range(1, len(frames)):
        mask = saliency_map < 128 * (1 - intensity)
        frames[i][mask] = frames[i-1][mask]
    
    return frames

def replace_words(text, intensity):
    """Remplace une fraction des mots du texte par des synonymes WordNet, proportionnelle à intensity (0-1)."""
    words = text.split()
    for i, word in enumerate(words):
        if random.random() < intensity:
            synsets = wordnet.synsets(word)
            if synsets:
                words[i] = synsets[0].lemmas()[0].name()
    return ' '.join(words)

def mix_files(composted_files, output_path):
    """Concatène byte-à-byte tous les fichiers compostés vers un unique fichier binaire de sortie (mixed_compost.bin)."""
    mixed_data = b''
    for file in composted_files:
        try:
            with open(file, 'rb') as f:
                mixed_data += f.read()
        except FileNotFoundError:
            print(f"Fichier non trouvé: {file}")
        except Exception as e:
            print(f"Erreur lors de la lecture du fichier {file}: {str(e)}")
    
    if not mixed_data:
        print("Attention: Aucune donnée à écrire dans le fichier de sortie.")
    
    with open(output_path, 'wb') as f:
        f.write(mixed_data)
    
    print(f"Taille du fichier de sortie: {len(mixed_data)} octets")

def compost_process(analysis_results_path):
    """Orchestre la 'décomposition' : itère sur les fichiers, applique compost_file à chacun, puis mix_files. Renvoie le chemin du binaire final."""
    analysis_results_path = Path(analysis_results_path)
    with open(analysis_results_path, 'r') as f:
        file_data = json.load(f)

    start_time = time.time()
    composted_files = []

    output_dir = analysis_results_path.parent / 'composted'
    output_dir.mkdir(parents=True, exist_ok=True)

    for file_info in file_data:
        composted_file = compost_file(file_info, output_dir)
        if composted_file:
            composted_files.append(composted_file)

        if time.time() - start_time > 55:
            break

    output_path = output_dir / 'mixed_compost.bin'
    mix_files(composted_files, output_path)

    print(f"Composting process completed in {time.time() - start_time} seconds")

    return str(output_path)

def compost_file(file_info, output_dir):
    """Applique la transformation adaptée au type (pixelation image / extraction frame vidéo / remplacement mots / copie). Renvoie le chemin du fichier composté ou None."""
    output_dir = Path(output_dir)
    file_path = Path(file_info['common_metadata']['path'])
    file_name = file_path.name
    file_type = file_info['category'].lower()

    output_dir.mkdir(parents=True, exist_ok=True)
    composted_path = output_dir / f"composted_{file_name}"
    
    cn_ratio = file_info['cn_data']['normalized_cn_ratio']
    intensity = min(cn_ratio / 30, 1)

    try:
        if file_type in ['image', 'document']:
            saliency_path = Path(file_info.get('additional_data', {}).get('saliency_map_gray', ''))

            if saliency_path.exists():
                saliency_map = cv2.imread(str(saliency_path), cv2.IMREAD_GRAYSCALE)
            else:
                print(f"Création d'une carte de saillance pour {file_path}")
                saliency_map = create_simple_saliency_map(str(file_path))

            # Vérifier que la carte de saillance est valide
            if saliency_map is None or saliency_map.size == 0:
                saliency_map = np.ones((100, 100), dtype=np.uint8) * 128  # Carte par défaut

            if file_type == 'image':
                img = pixelate_image(str(file_path), saliency_map, intensity)

                try:
                    # Pour les JPG, PNG, etc., sauvegarder en JPEG avec qualité réduite
                    if composted_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff'}:
                        # Assurer que l'extension est .jpg pour compression
                        composted_path = composted_path.with_suffix('.jpg')
                        img.save(str(composted_path), 'JPEG', quality=70)
                    else:
                        # Pour les autres formats, sauvegarder tel quel
                        img.save(str(composted_path))

                    print(f"Image compostée sauvegardée: {composted_path}")

                    # Vérifier la taille avant/après
                    original_size = file_path.stat().st_size
                    new_size = composted_path.stat().st_size
                    reduction = (1 - new_size / original_size) * 100 if original_size > 0 else 0
                    print(f"Réduction de taille: {original_size/1024:.1f}KB → {new_size/1024:.1f}KB ({reduction:.1f}%)")

                except Exception as e:
                    print(f"Erreur lors de la sauvegarde de l'image compostée: {str(e)}")
                    # Essayer une approche alternative en cas d'erreur
                    try:
                        img.convert('RGB').save(str(composted_path), 'JPEG', quality=70)
                        print(f"Sauvegarde de secours réussie: {composted_path}")
                    except Exception as e2:
                        print(f"Échec de la sauvegarde alternative: {str(e2)}")

            else:  # document
                # Pour les documents, on les traite comme du texte
                with open(file_path, 'r', errors='ignore') as f:
                    text = f.read()
                new_text = replace_words(text, intensity)
                with open(composted_path, 'w') as f:
                    f.write(new_text)

        elif file_type == 'video':
            try:
                cap = cv2.VideoCapture(str(file_path))
                if not cap.isOpened():
                    raise Exception("Unable to open video file")

                # Lire la dernière image de la vidéo
                last_frame = None
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        break
                    last_frame = frame.copy()

                if last_frame is not None:
                    # Sauvegarder l'image extraite avec extension .jpg
                    composted_path = composted_path.with_suffix(composted_path.suffix + '.jpg')
                    cv2.imwrite(str(composted_path), last_frame)
                    print(f"Image extraite de la vidéo et sauvegardée: {composted_path}")
                else:
                    raise Exception("Impossible d'extraire des images de la vidéo")

                cap.release()
                return str(composted_path)
            except Exception as e:
                print(f"Error processing video {file_path}: {str(e)}")
                return None

        elif file_type in ['audio', 'creative', 'hidden']:
            # Pour ces types, on copie simplement le fichier
            import shutil
            shutil.copy2(str(file_path), str(composted_path))

        else:
            print(f"Warning: Unsupported file type: {file_type}")
            return None

    except Exception as e:
        print(f"Error composting file {file_path}: {str(e)}")
        return None

    if composted_path.exists():
        file_size = composted_path.stat().st_size
        original_size = file_info['common_metadata']['size']
        if file_size > 0:
            # Si le fichier composté est plus grand que l'original, le redimensionner davantage
            if file_type == 'image' and file_size > original_size * 0.8:
                try:
                    img = Image.open(str(composted_path))
                    width, height = img.size
                    # Redimensionner de 50% supplémentaires
                    img = img.resize((width//2, height//2), Image.LANCZOS)
                    img.save(str(composted_path), 'JPEG', quality=60)
                    print(f"Redimensionnement supplémentaire appliqué à {composted_path}")
                except Exception as e:
                    print(f"Erreur lors du redimensionnement supplémentaire: {str(e)}")

            print(f"Fichier composté créé avec succès: {composted_path} ({file_size} octets)")
            return str(composted_path)
        else:
            print(f"Erreur: Le fichier composté est vide: {composted_path}")
            return None
    else:
        print(f"Erreur: Le fichier composté n'a pas été créé: {composted_path}")
        return None



def create_dummy_saliency_map(height, width):
    return np.random.randint(0, 256, (height, width), dtype=np.uint8)

def guess_file_type(filename):
    # Implémentez cette fonction pour déterminer le type de fichier basé sur son extension
    ext = Path(filename).suffix.lower()
    if ext in ['.jpg', '.jpeg', '.png', '.gif']:
        return 'image'
    elif ext in ['.mp4', '.avi', '.mov']:
        return 'video'
    elif ext in ['.txt', '.md', '.doc', '.docx']:
        return 'text'
    else:
        return 'unknown'

if __name__ == "__main__":
    silo_data_path = config['silos_dir'] / 'silo_info.json'
    print(f"Silo data path: {silo_data_path}")
    if silo_data_path.exists():
        print("Silo info file found.")
    else:
        print("Silo info file not found!")
    compost_process(silo_data_path)