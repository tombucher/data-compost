import json
import logging
from pathlib import Path

import numpy as np
from datetime import datetime
import math

from modules.config import CONFIG

logger = logging.getLogger(__name__)

# Définir les catégories de fichiers bruns (carbonés) et verts (azotés)
BROWN_CATEGORIES = ["system", "compressed", "executable", "hidden"]
GREEN_CATEGORIES = ["image", "audio", "video", "text", "document", "creative"]

# Ratio C/N de référence : un fichier dont l'inertie structurelle égale sa
# vitalité informationnelle vaut exactement cette valeur. C'est le pivot de
# toute l'échelle — au-dessus la matière est brune, en dessous elle est verte.
TARGET_CN_RATIO = CONFIG.pipeline.target_cn_ratio

# Bornes de la masse structurelle. En dessous de 1 Ko un fichier n'a presque
# pas de structure ; au-delà de 1 Go, en ajouter ne change plus sa nature.
MASS_FLOOR_BYTES = 1024
MASS_CEIL_BYTES = 1024 ** 3

# Inertie par catégorie : à quel point la matière résiste à la décomposition.
# 1.0 = carbone pur (déjà compressé, opaque, illisible), 0.2 = structure légère.
CATEGORY_INERTIA = {
    "compressed": 1.00,
    "executable": 0.95,
    "system": 0.90,
    "hidden": 0.85,
    "creative": 0.60,
    "video": 0.55,
    "image": 0.45,
    "audio": 0.45,
    "document": 0.30,
    "text": 0.20,
}
DEFAULT_INERTIA = 0.50

# Azote plancher : même une archive opaque nourrit un peu le compost.
MIN_VITALITY = 0.05

# Amplitude de l'effet de l'âge sur le ratio. 0.5 borne l'écart à un facteur 3
# entre un fichier du jour et un fichier très ancien.
AGE_SWING = 0.5

# Plafond du ratio, calé sur l'échelle agronomique : l'herbe coupée tourne
# autour de 15, le carton autour de 350, la sciure autour de 500. Un plafond
# à 100 rendait toutes les matières brunes identiques entre elles.
CN_CEILING = 500


def cn_position(ratio, target=TARGET_CN_RATIO, ceiling=CN_CEILING):
    """Place un ratio C/N sur une échelle d'affichage [0, 1], centrée sur la cible.

    0.5 correspond exactement au ratio cible : en dessous la matière est verte,
    au-dessus elle est brune. Les deux moitiés sont logarithmiques, sinon toute
    la matière verte — qui vit entre 1 et 30 — s'entasserait dans le premier
    dixième de la barre tandis que les archives satureraient l'autre bout.

    Les écrans normalisaient auparavant par `ratio / 100`, hérité du temps où
    le ratio était un index borné à 100 : depuis que l'échelle monte à 500,
    toute matière brune s'affichait de la même couleur.
    """
    try:
        ratio = float(ratio)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(ratio) or ratio <= 1:
        return 0.0 if ratio <= 1 else 1.0

    if ratio <= target:
        return _clamp(0.5 * math.log(ratio) / math.log(target))
    return _clamp(0.5 + 0.5 * math.log(ratio / target) / math.log(ceiling / target))


def _clamp(value, low=0.0, high=1.0):
    """Ramène `value` dans [low, high], en absorbant None et les types inattendus."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return low
    if math.isnan(value):
        return low
    return max(low, min(high, value))


def _structural_mass(size):
    """Masse structurelle d'un fichier, de 0 (1 Ko) à 1 (1 Go), en échelle log.

    La taille brute s'étale sur six ordres de grandeur : la comparer
    linéairement écraserait tout ce qui n'est pas une vidéo.
    """
    size = max(int(size or 0), 1)
    if size <= MASS_FLOOR_BYTES:
        return 0.0
    span = math.log10(MASS_CEIL_BYTES / MASS_FLOOR_BYTES)
    return _clamp(math.log10(size / MASS_FLOOR_BYTES) / span)


def _structural_carbon(category, size):
    """Carbone : inertie de la matière, dans (0, 1].

    Produit de la masse du fichier et de l'opacité de son format. Mesuré de la
    même façon pour toutes les catégories, contrairement à la version
    précédente où les fichiers bruns comptaient en octets bruts et les images
    en octets par pixel — deux échelles séparées par cinq ordres de grandeur.
    """
    inertia = CATEGORY_INERTIA.get(category, DEFAULT_INERTIA)
    # Le plancher de 0.25 traduit qu'un fichier minuscule garde une structure.
    return inertia * (0.25 + 0.75 * _structural_mass(size))


def _chromatic_spread(colors):
    """Étalement des couleurs dominantes dans l'espace RVB, dans [0, 1].

    Compter les couleurs ne servait à rien : colorgram en extrait toujours le
    nombre demandé (5), donc le terme valait 1.0 pour chaque image. C'est leur
    dispersion qui distingue une photographie vive d'un aplat monochrome.
    """
    points = []
    for color in colors or []:
        try:
            r, g, b = (float(c) for c in tuple(color)[:3])
        except (TypeError, ValueError):
            continue
        points.append((r, g, b))

    if len(points) < 2:
        return 0.0

    spreads = []
    for channel in range(3):
        values = [p[channel] for p in points]
        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        spreads.append(math.sqrt(variance))

    # 128 = écart-type d'une répartition qui couvrirait tout le canal
    return _clamp((sum(spreads) / 3) / 128)


def _image_vitality(data, size):
    """Azote d'une image : richesse chromatique, densité de détail, texte lisible."""
    colors = _chromatic_spread(data.get("dominant_colors"))

    # Octets par pixel : une image dense en détail se comprime mal. C'est une
    # grandeur indépendante de la masse totale, contrairement à « quality »
    # qui en était l'inverse exact et annulait donc le ratio.
    dimensions = data.get("dimensions") or (0, 0)
    try:
        width, height = dimensions[0], dimensions[1]
        pixels = int(width) * int(height)
    except (TypeError, ValueError, IndexError):
        pixels = 0
    detail = _clamp((size / pixels) / 0.5) if pixels > 0 else 0.0

    legible = 0.3 if (data.get("description") or "").strip() else 0.0

    return MIN_VITALITY + 0.50 * colors + 0.30 * detail + 0.15 * legible


def _video_vitality(data):
    """Azote d'une vidéo : cadence et variété des scènes."""
    motion = _clamp(_clamp(data.get("fps"), 0, 120) / 30)
    scenes = _clamp(len(data.get("frame_descriptions") or []) / 10)
    return MIN_VITALITY + 0.50 * motion + 0.45 * scenes


def _audio_vitality(data):
    """Azote d'un son : tempo et finesse d'échantillonnage."""
    tempo = data.get("tempo")
    if isinstance(tempo, (list, tuple)) and tempo:
        tempo = sum(tempo) / len(tempo)
    rhythm = _clamp(_clamp(tempo, 0, 300) / 160)
    fidelity = _clamp(_clamp(data.get("sample_rate"), 0, 192000) / 48000)
    return MIN_VITALITY + 0.60 * rhythm + 0.35 * fidelity


def _text_vitality(data):
    """Azote d'un texte : abondance de mots et longueur moyenne du vocabulaire."""
    word_count = _clamp(data.get("word_count"), 0, 10 ** 7)
    char_count = _clamp(data.get("char_count"), 0, 10 ** 9)
    abundance = _clamp(word_count / 2000)
    lexical = _clamp((char_count / word_count) / 8) if word_count else 0.0
    return MIN_VITALITY + 0.60 * abundance + 0.35 * lexical


def _informational_nitrogen(category, data, size):
    """Azote : vitalité informationnelle, dans (0, 1].

    Ce que la matière offre à décomposer. Les catégories brunes sont opaques —
    une archive ou un exécutable ne livre aucun contenu lisible — et restent
    donc au plancher.
    """
    data = data or {}
    if category in BROWN_CATEGORIES:
        return MIN_VITALITY
    if category == "image":
        return _image_vitality(data, size)
    if category == "video":
        return _video_vitality(data)
    if category == "audio":
        return _audio_vitality(data)
    if category in ("text", "document"):
        return _text_vitality(data)
    if category == "creative":
        # Formats propriétaires : structure lourde, contenu illisible sans l'outil
        return MIN_VITALITY + 0.15
    return 0.30

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
    """Calcule (carbone, azote) de base, tous deux dans (0, 1] et comparables.

    Le carbone mesure l'inertie structurelle — masse du fichier pondérée par
    l'opacité de son format. L'azote mesure la vitalité informationnelle — ce
    que la matière offre à décomposer. Les deux grandeurs sont indépendantes et
    évaluées de la même manière pour toutes les catégories, ce qui permet de
    comparer une archive et une photographie sur la même échelle.
    """
    category = file_data['category']
    size = file_data['common_metadata']['size']
    additional_data = file_data.get('additional_data') or {}

    carbon = _structural_carbon(category, size)
    nitrogen = _informational_nitrogen(category, additional_data, size)

    return carbon, nitrogen

def calculate_cn_ratio(file_data):
    """Calcule le ratio C/N d'un fichier en pondérant carbone/azote par son type et son âge.

    Renvoie un dict avec file_type, carbon, nitrogen, raw_cn_ratio et normalized_cn_ratio.
    Le file_type final est reclassé selon la dominance C vs N effective.
    """
    file_type = determine_file_type(file_data)
    age_factor = calculate_age_factor(file_data)
    base_carbon, base_nitrogen = calculate_base_cn(file_data)
    
    # L'âge accentue le caractère de la matière : le brun se dessèche et se
    # carbonise, le vert se décompose et libère son azote. Le débattement est
    # borné à AGE_SWING pour que l'âge module le ratio sans l'écraser — la
    # pondération précédente le divisait par sept dès dix-huit mois, effaçant
    # toute différence de contenu entre les fichiers.
    aging = AGE_SWING * (1 - age_factor)  # 0 si récent, AGE_SWING si très ancien
    if file_type == "brown":
        carbon = base_carbon * (1 + aging)
        nitrogen = base_nitrogen * (1 - aging)
    elif file_type == "green":
        carbon = base_carbon * (1 - aging)
        nitrogen = base_nitrogen * (1 + aging)
    else:
        carbon = base_carbon
        nitrogen = base_nitrogen
    
    # Le ratio est calé sur la cible : inertie == vitalité donne exactement
    # TARGET_CN_RATIO. La frontière brun/vert tombe donc pile sur la valeur
    # agronomique de référence.
    raw_cn_ratio = TARGET_CN_RATIO * carbon / nitrogen if nitrogen != 0 else float('inf')
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

def normalize_cn_ratio(raw_ratio, min_value=1, max_value=CN_CEILING, decimals=0):
    """Borne un ratio C/N dans [min_value, max_value] en conservant sa valeur.

    La valeur renvoyée reste un ratio C/N, directement comparable à la cible
    agronomique. C'est ce dont `create_silos` a besoin : il compare la moyenne
    d'un silo à `target_cn_ratio`.

    L'ancienne version remappait le ratio en logarithme sur un index [1, 100],
    ce qui produisait deux grandeurs incomparables — un index de 30 n'avait
    rien à voir avec un C/N de 30 — et écrasait toutes les images entre 1 et 7.
    """

    if raw_ratio is None:
        return min_value
    if isinstance(raw_ratio, float) and math.isnan(raw_ratio):
        return min_value
    if raw_ratio <= 0:
        return min_value

    return round(max(min_value, min(max_value, raw_ratio)), decimals)

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