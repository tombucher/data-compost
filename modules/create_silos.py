import json
import logging
from pathlib import Path

import numpy as np
from collections import defaultdict

from modules.config import CONFIG

logger = logging.getLogger(__name__)

TARGET_CN_RATIO = CONFIG.pipeline.target_cn_ratio
SILO_SIZE_LIMIT = CONFIG.pipeline.silo_size_limit

# Tolérance autour de la cible en deçà de laquelle un silo est considéré mûr
SILO_TOLERANCE = 5

def create_silos(cn_results_path, target_cn_ratio=TARGET_CN_RATIO):
    """Regroupe les fichiers analysés en silos équilibrés par ratio C/N et taille.

    Lit le JSON pointé par `cn_results_path`, crée des sous-dossiers `silo_N`
    via liens symboliques, et écrit un `silo_info.json` listant les
    statistiques de chaque silo. Renvoie le chemin de `silo_info.json`.
    """
    cn_results_path = Path(cn_results_path)
    with open(cn_results_path, 'r') as f:
        files_data = json.load(f)
    
    silos = compose_silos(files_data, target_cn_ratio)

    # Créer les dossiers de silos et les liens symboliques
    base_silo_path = cn_results_path.parent / 'silos'
    base_silo_path.mkdir(parents=True, exist_ok=True)

    silo_info = []
    for silo_id, silo_files in enumerate(silos, 1):
        silo_path = base_silo_path / f'silo_{silo_id}'
        silo_path.mkdir(parents=True, exist_ok=True)

        total_size = sum(file['common_metadata']['size'] for file in silo_files)
        total_normalized_cn = sum(_cn(file) for file in silo_files)
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

        # Rendre l'écart visible : sur une matière trop homogène, aucun
        # assemblage ne peut atteindre la cible, et il vaut mieux le dire.
        deviation = avg_normalized_cn - target_cn_ratio
        log = logger.info if abs(deviation) <= SILO_TOLERANCE else logger.warning
        log(
            f"Silo {silo_id}: {len(silo_files)} fichier(s), "
            f"C/N moyen {avg_normalized_cn:.1f} (cible {target_cn_ratio}, écart {deviation:+.1f})"
        )

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


def _cn(file_data):
    """Ratio C/N d'un fichier analysé, 0 si le calcul a échoué."""
    return (file_data.get('cn_data') or {}).get('normalized_cn_ratio', 0)


def compose_silos(files_data, target_ratio=TARGET_CN_RATIO, size_limit=SILO_SIZE_LIMIT):
    """Assemble les fichiers en silos qui mélangent matière brune et verte.

    À chaque ajout, on choisit le côté qui rapproche la moyenne du silo de la
    cible : de la matière brune quand le mélange est trop azoté, de la verte
    quand il est trop carboné. Un silo se referme quand il atteint la cible ou
    la limite de taille.

    L'implémentation précédente triait les fichiers par C/N puis les découpait
    en tranches successives : elle regroupait donc les semblables, ce qui est
    exactement l'inverse d'un équilibrage. Un silo trop éloigné de la cible
    était ensuite coupé en deux moitiés triées, produisant deux silos encore
    plus homogènes que le premier.
    """
    # Plus carbonés d'abord d'un côté, plus azotés d'abord de l'autre : on
    # consomme les extrêmes en premier, ce sont eux qui déséquilibrent.
    brown = sorted((f for f in files_data if _cn(f) > target_ratio),
                   key=_cn, reverse=True)
    green = sorted((f for f in files_data if _cn(f) <= target_ratio), key=_cn)

    silos = []
    while brown or green:
        silo = []
        silo_size = 0
        silo_sum = 0.0

        while brown or green:
            average = silo_sum / len(silo) if silo else None

            # Premier fichier : commencer par l'extrême le plus abondant
            if average is None:
                pile = brown if len(brown) >= len(green) and brown else (green or brown)
            elif average > target_ratio:
                pile = green or brown       # trop carboné : ajouter du vert
            else:
                pile = brown or green       # trop azoté : ajouter du brun

            candidate = pile[0]
            candidate_size = candidate['common_metadata']['size']

            # Un silo doit pouvoir accueillir au moins un fichier, même énorme
            if silo and silo_size + candidate_size > size_limit:
                break

            pile.pop(0)
            silo.append(candidate)
            silo_size += candidate_size
            silo_sum += _cn(candidate)

            average = silo_sum / len(silo)
            if len(silo) >= 2 and abs(average - target_ratio) <= SILO_TOLERANCE:
                break  # mélange équilibré : le silo est mûr

        if not silo:
            break  # sécurité : aucun fichier n'a pu être placé
        silos.append(silo)

    return silos


def main(input_path):
    return create_silos(input_path)

if __name__ == "__main__":
    input_path = (Path(__file__).resolve().parent.parent.parent / 'data' / 'analysis_results.json')
    main(input_path)