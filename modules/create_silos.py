import json
import os
import logging
import numpy as np
from collections import defaultdict

logging.basicConfig(level=logging.INFO)

TARGET_CN_RATIO = 30  # Ratio C/N cible pour chaque silo
SILO_SIZE_LIMIT = 100 * 1024 * 1024  # 1 GB, ajustez selon vos besoins

def create_silos(cn_results_path, target_cn_ratio=TARGET_CN_RATIO):
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
    base_silo_path = os.path.join(os.path.dirname(cn_results_path), 'silos')
    os.makedirs(base_silo_path, exist_ok=True)
    
    silo_info = []
    for silo_id, silo_files in enumerate(balanced_silos, 1):
        silo_path = os.path.join(base_silo_path, f'silo_{silo_id}')
        os.makedirs(silo_path, exist_ok=True)
        
        total_size = sum(file['common_metadata']['size'] for file in silo_files)
        total_normalized_cn = sum(file['cn_data']['normalized_cn_ratio'] for file in silo_files)
        avg_normalized_cn = total_normalized_cn / len(silo_files)
        
        for file in silo_files:
            source_path = file['common_metadata']['path']
            dest_path = os.path.join(silo_path, os.path.basename(source_path))
            try:
                # Vérifier si le lien symbolique existe déjà
                if os.path.exists(dest_path):
                    # Si on veut remplacer le lien existant, on le supprime d'abord
                    os.remove(dest_path)
                    
                # Créer le lien symbolique
                os.symlink(source_path, dest_path)
                logging.info(f"Lien symbolique créé de {source_path} vers {dest_path}")
            except FileExistsError:
                # Si le lien existe déjà, on l'ignore simplement (option alternative)
                logging.info(f"Le lien symbolique existe déjà: {dest_path}")
            except Exception as e:
                logging.error(f"Erreur lors de la création du lien symbolique de {source_path}: {str(e)}")
        
        silo_info.append({
            'silo_id': silo_id,
            'file_count': len(silo_files),
            'total_size': total_size,
            'avg_normalized_cn_ratio': avg_normalized_cn
        })
    
    output_path = os.path.join(base_silo_path, 'silo_info.json')
    with open(output_path, 'w') as f:
        json.dump(silo_info, f, indent=4)
    
    logging.info(f"Informations sur les silos exportées vers {output_path}")
    return output_path

def balance_silos(silos, target_ratio):
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
    input_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'analysis_results.json'))
    main(input_path)