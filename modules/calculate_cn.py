import json
import logging
from pathlib import Path

import numpy as np
from datetime import datetime
import math

logger = logging.getLogger(__name__)

# Définir les catégories de fichiers bruns (carbonés) et verts (azotés)
BROWN_CATEGORIES = ["system", "compressed", "executable", "hidden"]
GREEN_CATEGORIES = ["image", "audio", "video", "text", "document", "creative"]

def determine_file_type(file_data):
    """Classe un fichier en 'brown' (carboné), 'green' (azoté) ou 'unknown' selon sa catégorie."""
    category = file_data['category']
    name = file_data['common_metadata']['name']
    
    # Vérifier si le fichier est caché (commence par un point)
    if name.startswith('.'):
        return "brown"
    
    if category in ["system", "compressed", "executable", "hidden"]:
        return "brown"
    elif category in ["image", "audio", "video", "text", "document", "creative"]:
        return "green"
    else:
        return "unknown"

def calculate_age_factor(file_data):
    """Renvoie un facteur dans (0, 1] : ~1 pour un fichier récent, → 0 pour un fichier ancien (décroissance exp sur 1 an)."""
    modified_time = datetime.fromisoformat(file_data['common_metadata']['modified_at'])
    age = (datetime.now() - modified_time).days
    return np.exp(-age / 365)  # Plus le fichier est vieux, plus le facteur est proche de 0

def calculate_base_cn(file_data):
    """Calcule (carbone, azote) bruts à partir des métadonnées spécifiques au type de média."""
    category = file_data['category']
    size = file_data['common_metadata']['size']
    
    if category == 'image':
        additional_data = file_data.get('additional_data', {})
        dimensions = additional_data.get('dimensions', (1, 1))
        width, height = dimensions
        num_colors = len(additional_data.get('dominant_colors') or [])
        quality = additional_data.get('quality', 1)
        carbon = size / (width * height) if width and height else size
        nitrogen = (num_colors / 5) * quality if quality is not None else 1
    elif category == 'video':
        additional_data = file_data.get('additional_data', {})
        duration = additional_data.get('duration', 1)
        fps = additional_data.get('fps', 1)
        num_descriptions = len(additional_data.get('frame_descriptions', []))
        carbon = size / 5 / (duration * fps) if duration and fps else size
        nitrogen = fps / 10 + num_descriptions / 10
    elif category == 'audio':
        additional_data = file_data.get('additional_data', {})
        duration = additional_data.get('duration', 1)
        sample_rate = additional_data.get('sample_rate', 1)
        quality = additional_data.get('quality', 1)
        carbon = size / (duration * sample_rate) if duration and sample_rate else size
        tempo = additional_data.get('tempo')
        if isinstance(tempo, (int, float)):
            nitrogen = tempo / 120 + quality
        elif isinstance(tempo, list) and len(tempo) > 0:
            nitrogen = sum(tempo) / (120 * len(tempo)) + quality
        else:
            logging.warning(f"Invalid type for tempo: {type(tempo)}. Using default value.")
            nitrogen = 1 + quality
    elif category in ['text', 'document']:
        additional_data = file_data.get('additional_data', {})
        word_count = additional_data.get('word_count', 1)
        char_count = additional_data.get('char_count', 1)
        carbon = size / 2 / word_count / 10 if word_count else size
        nitrogen = size * word_count / char_count / 10 if char_count else 1
    elif category in ["system", "compressed", "executable", "hidden"]:
        carbon = size
        nitrogen = 0.1
    else:
        carbon = size / 1024 / 1024
        nitrogen = 1
    
    return carbon, nitrogen

def calculate_cn_ratio(file_data):
    """Calcule le ratio C/N d'un fichier en pondérant carbone/azote par son type et son âge.

    Renvoie un dict avec file_type, carbon, nitrogen, raw_cn_ratio et normalized_cn_ratio.
    Le file_type final est reclassé selon la dominance C vs N effective.
    """
    file_type = determine_file_type(file_data)
    age_factor = calculate_age_factor(file_data)
    base_carbon, base_nitrogen = calculate_base_cn(file_data)
    
    if file_type == "brown":
        carbon = base_carbon * (2 - age_factor)
        nitrogen = base_nitrogen * age_factor
    elif file_type == "green":
        carbon = base_carbon * age_factor
        nitrogen = base_nitrogen * (2 - age_factor)
    else:
        carbon = base_carbon
        nitrogen = base_nitrogen
    
    raw_cn_ratio = carbon / nitrogen if nitrogen != 0 else float('inf')
    normalized_cn_ratio = normalize_cn_ratio(raw_cn_ratio, decimals=0)  # Arrondi à l'entier
    
    # Reclassification basée sur la comparaison directe entre carbone et azote
    if carbon > nitrogen:
        file_type = "brown"
    elif carbon < nitrogen:
        file_type = "green"
    # Si carbon == nitrogen, file_type reste inchangé
    
    return {
        'file_type': file_type,
        'carbon': carbon,
        'nitrogen': nitrogen,
        'raw_cn_ratio': raw_cn_ratio,
        'normalized_cn_ratio': normalized_cn_ratio
    }

def normalize_cn_ratio(raw_ratio, min_value=1, max_value=100, decimals=0):
    """Normalise un ratio C/N brut sur l'échelle [min_value, max_value] via log10 (saturée à [0.01, 1000])."""
    if raw_ratio <= 0:
        return min_value
    
    # Utiliser une échelle logarithmique pour mieux répartir les valeurs
    log_ratio = math.log10(raw_ratio)
    
    # Définir des seuils pour la normalisation
    min_log = math.log10(0.01)  # Correspond à un ratio C/N de 0.01
    max_log = math.log10(1000)  # Correspond à un ratio C/N de 1000
    
    # Normaliser sur l'échelle logarithmique
    normalized = (log_ratio - min_log) / (max_log - min_log)
    
    # Assurez-vous que la valeur normalisée est entre 0 et 1
    normalized = max(0, min(1, normalized))
    
    # Mapper sur l'échelle souhaitée et arrondir
    result = min_value + normalized * (max_value - min_value)
    return round(result, decimals)

def calculate_cn(input_path):
    """Lit un fichier d'analyses JSON, calcule le ratio C/N par fichier et réécrit le résultat sur place.

    Renvoie le chemin d'entrée pour chaînage dans le pipeline.
    """
    with open(input_path, 'r') as f:
        analysis_results = json.load(f)
    
    for file_data in analysis_results:
        if 'additional_data' not in file_data or file_data['additional_data'] is None:
            file_data['additional_data'] = {}
        
        try:
            cn_data = calculate_cn_ratio(file_data)
            file_data['cn_data'] = cn_data
        except Exception as e:
            logging.error(f"Error calculating C/N ratio for {file_data['common_metadata']['name']}: {str(e)}")
            file_data['cn_data'] = {
                'file_type': 'unknown',
                'carbon': 0,
                'nitrogen': 0,
                'raw_cn_ratio': 0,
                'normalized_cn_ratio': 0,
                'error': str(e)
            }
    
    # Écrire les résultats mis à jour dans le même fichier
    with open(input_path, 'w') as f:
        json.dump(analysis_results, f, indent=4)
    
    logging.info(f"Résultats C/N ajoutés au fichier {input_path}")
    return input_path


if __name__ == "__main__":
    input_path = Path(__file__).resolve().parent.parent.parent / 'data' / 'analysis_results.json'
    calculate_cn(input_path)