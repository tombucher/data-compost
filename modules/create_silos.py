import json
import logging
from pathlib import Path

import numpy as np
from collections import defaultdict

from modules.config import CONFIG

logger = logging.getLogger(__name__)

TARGET_CN_RATIO = CONFIG.pipeline.target_cn_ratio
SILO_SIZE_LIMIT = CONFIG.pipeline.silo_size_limit

def create_silos(cn_results_path, target_cn_ratio=TARGET_CN_RATIO):
    """Regroupe les fichiers analysés en silos équilibrés par ratio C/N et taille.

    Lit le JSON pointé par `cn_results_path`, crée des sous-dossiers `silo_N`
    via liens symboliques, et écrit un `silo_info.json` listant les
    statistiques de chaque silo. Renvoie le chemin de `silo_info.json`.
    """
    cn_results_path = Path(cn_results_path)
    with open(cn_results_path, 'r') as f:
        files_data = json.load(f)
    
    # Trier les fichiers par ratio C/N normalisé
    sorted_files = sorted(files_data, key=lambda x: x['cn_data']['normalized_cn_ratio'])
    
    silos = []
    current_silo = []
    current_size = 0
    current_total_normalized_cn = 0
    
    for file in sorted_files:
        file_size = file['common_metadata']['size']
        normalized_cn = file['cn_data']['normalized_cn_ratio']
        
        # Si l'ajout du fichier dépasse la limite de taille, commencer un nouveau silo
        if current_size + file_size > SILO_SIZE_LIMIT:
            if current_silo:
                silos.append(current_silo)
            current_silo = []
            current_size = 0
            current_total_normalized_cn = 0
        
        current_silo.append(file)
        current_size += file_size
        current_total_normalized_cn += normalized_cn
        
        # Vérifier si le silo actuel a atteint un équilibre proche de la cible
        if abs(current_total_normalized_cn / len(current_silo) - target_cn_ratio) < 1 and len(current_silo) > 1:
            silos.append(current_silo)
            current_silo = []
            current_size = 0
            current_total_normalized_cn = 0
    
    # Ajouter le dernier silo s'il contient des fichiers
    if current_silo:
        silos.append(current_silo)
    
    # Équilibrage final
    balanced_silos = balance_silos(silos, target_cn_ratio)
    
    # Créer les dossiers de silos et les liens symboliques
    base_silo_path = cn_results_path.parent / 'silos'
    base_silo_path.mkdir(parents=True, exist_ok=True)

    silo_info = []
    for silo_id, silo_files in enumerate(balanced_silos, 1):
        silo_path = base_silo_path / f'silo_{silo_id}'
        silo_path.mkdir(parents=True, exist_ok=True)

        total_size = sum(file['common_metadata']['size'] for file in silo_files)
        total_normalized_cn = sum(file['cn_data']['normalized_cn_ratio'] for file in silo_files)
        avg_normalized_cn = total_normalized_cn / len(silo_files)

        for file in silo_files:
            source_path = Path(file['common_metadata']['path'])
            dest_path = silo_path / source_path.name
            try:
                if dest_path.exists() or dest_path.is_symlink():
                    dest_path.unlink()

                dest_path.symlink_to(source_path)
                logger.info(f"Lien symbolique créé de {source_path} vers {dest_path}")
            except FileExistsError:
                logger.info(f"Le lien symbolique existe déjà: {dest_path}")
            except Exception as e:
                logger.error(f"Erreur lors de la création du lien symbolique de {source_path}: {str(e)}")

        silo_info.append({
            'silo_id': silo_id,
            'file_count': len(silo_files),
            'total_size': total_size,
            'avg_normalized_cn_ratio': avg_normalized_cn
        })

    output_path = base_silo_path / 'silo_info.json'
    with open(output_path, 'w') as f:
        json.dump(silo_info, f, indent=4)

    logger.info(f"Informations sur les silos exportées vers {output_path}")
    return str(output_path)

def balance_silos(silos, target_ratio):
    """Pour chaque silo dont la moyenne C/N s'éloigne de plus de 5 du target, le coupe en deux moitiés triées."""
    balanced_silos = []
    for silo in silos:
        if len(silo) < 2:
            balanced_silos.append(silo)
            continue
        
        silo_avg = sum(file['cn_data']['normalized_cn_ratio'] for file in silo) / len(silo)
        if abs(silo_avg - target_ratio) < 5:  # Tolérance de 5 unités
            balanced_silos.append(silo)
            continue
        
        # Trier le silo par ratio CN normalisé
        sorted_silo = sorted(silo, key=lambda x: x['cn_data']['normalized_cn_ratio'])
        
        # Diviser le silo en deux parties
        mid = len(sorted_silo) // 2
        balanced_silos.append(sorted_silo[:mid])
        balanced_silos.append(sorted_silo[mid:])
    
    return balanced_silos

def main(input_path):
    return create_silos(input_path)

if __name__ == "__main__":
    input_path = (Path(__file__).resolve().parent.parent.parent / 'data' / 'analysis_results.json')
    main(input_path)