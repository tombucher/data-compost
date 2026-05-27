#!/usr/bin/env python3
"""
Système de compostage numérique avec visualisation multiécran.

Ce script orchestre le processus de compostage de fichiers numériques
et coordonne l'affichage sur plusieurs écrans.
"""

import sys
import time
import logging
import argparse
import multiprocessing
from pathlib import Path
import shutil
from modules.usb_detector import USBDetector
from modules.multiscreen_coordinator import CompostVisualizer, CompostPhase
from modules.logging_config import setup_main_logging
from modules.config import CONFIG
from threading import Event

# Extensions de fichiers supportées par le pipeline d'analyse
SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".svg",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a",
    ".mp4", ".avi", ".mov", ".wmv", ".flv", ".mkv", ".webm",
    ".txt", ".md", ".rtf", ".csv",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".webloc",
    ".psd", ".ai", ".indd", ".xd", ".sketch", ".fig", ".ttf", ".otf",
    ".sys", ".dll", ".ini", ".config",
    ".zip", ".rar", ".7z", ".tar", ".gz",
    ".exe", ".app", ".bat", ".sh", ".com",
}


# Logging centralisé : configuré dans __main__ pour disposer de la log_queue
# partagée avec les sous-processus. Au niveau module on récupère seulement le
# logger nommé.
logger = logging.getLogger("MainScript")

def check_system_requirements():
    """Vérifie que les dépendances système sont présentes"""
    try:
        import pygame
        logger.info(f"Pygame version: {pygame.version.ver}")
    except ImportError:
        logger.error("Pygame n'est pas installé. Veuillez l'installer avec: pip install pygame")
        return False
        
    # Vérifier que les modules nécessaires sont disponibles
    project_root = Path(__file__).resolve().parent
    required_modules = [
        'analyze.py',
        'calculate_cn.py',
        'create_silos.py',
        'transformation.py',
        'compost_info_display.py',
        'visualize_bin.py',
    ]

    for module_name in required_modules:
        module_path = project_root / 'modules' / module_name
        if not module_path.exists():
            logger.warning(f"Module non trouvé: {module_path}")

    return True


def validate_input_directory(input_dir: Path) -> bool:
    """Valide qu'un dossier source est utilisable par le pipeline."""
    if not input_dir.exists() or not input_dir.is_dir():
        logger.error(f"Le répertoire d'entrée n'existe pas: {input_dir}")
        return False

    # Compter les fichiers exploitables (extensions supportées, non cachés)
    usable_files = [
        f for f in input_dir.rglob('*')
        if f.is_file()
        and not f.name.startswith('.')
        and f.suffix.lower() in SUPPORTED_EXTENSIONS
        and CONFIG.paths.saliency_subdir not in f.parts  # exclure les artefacts d'un run précédent
    ]

    if not usable_files:
        logger.error(f"Aucun fichier exploitable dans {input_dir} (extensions supportées: voir SUPPORTED_EXTENSIONS).")
        return False

    total_size_mb = sum(f.stat().st_size for f in usable_files) / (1024 * 1024)
    logger.info(f"{len(usable_files)} fichier(s) exploitable(s) — taille totale: {total_size_mb:.1f} Mo")

    if total_size_mb > CONFIG.pipeline.input_size_warning_mb:
        logger.warning(f"Volume important ({total_size_mb:.1f} Mo) — l'analyse peut être longue.")

    return True


def setup_directories():
    """Crée les répertoires nécessaires s'ils n'existent pas"""
    directories = [
        CONFIG.paths.output_root,
        CONFIG.paths.silos_dir,
        CONFIG.paths.composted_dir,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        logger.info(f"Répertoire vérifié: {directory}")

def parse_arguments():
    """Analyse les arguments de ligne de commande"""
    parser = argparse.ArgumentParser(
        description="Système de compostage numérique avec visualisation multiécran"
    )
    
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(CONFIG.paths.default_input),
        help="Répertoire contenant les fichiers à composter"
    )
    
    parser.add_argument(
        "--skip-displays", "-s",
        action="store_true",
        help="Exécuter uniquement le processus de compostage sans les affichages"
    )
    
    parser.add_argument(
        "--phase", "-p",
        type=int,
        choices=range(1, 6),
        help="Démarrer directement à une phase spécifique (1-5)"
    )
    
    parser.add_argument(
        "--usb",
        action="store_true",
        help="Attendre une clé USB et l'utiliser comme source"
    )
    
    return parser.parse_args()

def clean_output_directories(input_dir: Path | None = None):
    """Nettoie les répertoires de sortie et les artefacts saliency_maps du dossier d'entrée."""
    dirs_to_clean = [
        CONFIG.paths.output_root,
        CONFIG.paths.silos_dir,
        CONFIG.paths.composted_dir,
    ]

    # Nettoyer le dossier saliency_maps du dossier d'entrée (et fallback historique sur l'input par défaut)
    saliency_name = CONFIG.paths.saliency_subdir
    saliency_dirs = []
    if input_dir is not None:
        saliency_dirs.append(input_dir / saliency_name)
    saliency_dirs.append(CONFIG.paths.default_input / saliency_name)

    for saliency_dir in saliency_dirs:
        if saliency_dir.exists():
            try:
                shutil.rmtree(saliency_dir)
                logger.info(f"Dossier nettoyé: {saliency_dir}")
            except OSError as e:
                logger.error(f"Erreur lors du nettoyage de {saliency_dir}: {e}")

    # Nettoyer les dossiers de sortie
    for directory in dirs_to_clean:
        if not directory.exists():
            continue
        try:
            for entry in directory.iterdir():
                if entry.is_file():
                    entry.unlink()
                elif entry.is_dir() and not entry.name.startswith('.'):
                    shutil.rmtree(entry)
            logger.info(f"Dossier nettoyé: {directory}")
        except OSError as e:
            logger.error(f"Erreur lors du nettoyage de {directory}: {e}")

    # Recréer les dossiers
    setup_directories()

def main():
    """Fonction principale du programme"""
    # Analyser les arguments
    args = parse_arguments()
    visualizer = None  # Initialiser visualizer à None
    usb_detector = None  # Initialiser usb_detector à None
    log_queue, log_listener = setup_main_logging(CONFIG.paths.log_file)

    try:
        # Vérifier les prérequis
        if not check_system_requirements():
            return 1
            
        # Nettoyer les dossiers avant de commencer
        clean_output_directories(Path(args.input))

        # Préparer les répertoires
        setup_directories()

        
        # Mode USB
        usb_ready = Event()  # Pour signaler qu'une clé USB a été détectée
        
        # Fonction de callback pour le détecteur USB
        def handle_usb_detection(mount_point):
            """Fonction appelée quand une clé USB est détectée"""
            logger.info(f"Clé USB détectée: {mount_point}")
            
            # Si en mode USB, copier les fichiers vers le répertoire d'entrée
            if args.usb and not usb_ready.is_set():
                logger.info(f"Copie des fichiers depuis la clé USB: {mount_point}")
                
                # Utiliser le répertoire d'entrée standard
                input_dir = CONFIG.paths.default_input
                input_dir.mkdir(parents=True, exist_ok=True)
                
                # Effacer les fichiers existants (optionnel)
                for file in input_dir.glob("*"):
                    if file.is_file():
                        file.unlink()
                
                # Compter les fichiers copiés
                file_count = 0
                
                # Copier les fichiers
                mount_path = Path(mount_point)
                try:
                    for file_path in mount_path.glob("**/*"):
                        if file_path.is_file():
                            # Créer le chemin de destination
                            rel_path = file_path.relative_to(mount_path)
                            dest_path = input_dir / rel_path.name  # Juste le nom du fichier, pas les sous-répertoires
                            
                            # Copier le fichier
                            shutil.copy2(str(file_path), str(dest_path))
                            file_count += 1
                            logger.info(f"Fichier copié: {file_path.name}")
                    
                    if file_count > 0:
                        logger.info(f"{file_count} fichiers copiés de la clé USB vers {input_dir}")
                        usb_ready.set()  # Signaler que la clé est prête
                    else:
                        logger.warning("Aucun fichier trouvé sur la clé USB")
                        
                except Exception as e:
                    logger.error(f"Erreur lors de la copie des fichiers: {str(e)}")
        
        # Initialiser le détecteur USB
        usb_detector = USBDetector(callback=handle_usb_detection)
        usb_detector.start()
        
        # Si mode USB, attendre une clé USB
        if args.usb:
            logger.info("Mode USB activé. En attente d'une clé USB...")
            while not usb_ready.is_set():
                time.sleep(1)  # Vérifier toutes les secondes
            
            logger.info(f"Clé USB détectée, démarrage du processus avec {args.input}")
        
        # Vérifier et valider le répertoire d'entrée
        input_directory = Path(args.input)
        if not validate_input_directory(input_directory):
            return 1
        
        logger.info(f"Démarrage du processus de compostage numérique")
        logger.info(f"Répertoire d'entrée: {input_directory}")
        
        # Créer et démarrer le visualiseur
        visualizer = CompostVisualizer(input_directory, log_queue=log_queue)
        
        # Démarrer le processus complet
        if args.skip_displays:
            # Exécuter uniquement le processus de compostage
            logger.info("Mode sans affichage activé, exécution du processus uniquement")
            
            # Exécuter les phases séquentiellement
            if args.phase:
                start_phase = CompostPhase(args.phase)
                logger.info(f"Démarrage à la phase: {start_phase.name}")
            else:
                start_phase = CompostPhase.FILE_ANALYSIS
            
            # Exécuter les phases à partir de la phase de départ
            if start_phase.value <= CompostPhase.FILE_ANALYSIS.value:
                visualizer.execute_analysis_phase()
            if start_phase.value <= CompostPhase.CN_CALCULATION.value:
                visualizer.execute_cn_calculation_phase()
            if start_phase.value <= CompostPhase.SILO_CREATION.value:
                visualizer.execute_silo_creation_phase()
            if start_phase.value <= CompostPhase.COMPOSTING.value:
                visualizer.execute_composting_phase()
            if start_phase.value <= CompostPhase.RESULT_VISUALIZATION.value:
                visualizer.execute_visualization_phase()
        else:
            # Exécuter le processus complet avec visualisation
            visualizer.run_full_process()
        
        logger.info("Processus de compostage numérique terminé avec succès")
        return 0
        
    except KeyboardInterrupt:
        logger.info("Processus interrompu par l'utilisateur")
        return 130
    except Exception as e:
        logger.error(f"Erreur lors du processus: {str(e)}")
        logger.exception(e)
        return 1
    finally:
        # Nettoyage final
        if visualizer:  # Vérifier que visualizer existe avant d'appeler stop_all_processes
            visualizer.stop_all_processes()
        if usb_detector:  # Vérifier que usb_detector existe avant d'appeler stop
            usb_detector.stop()
        log_listener.stop()

if __name__ == "__main__":
    # Configurer multiprocessing pour fonctionner correctement
    multiprocessing.set_start_method('spawn', force=True)
    
    # Exécuter le programme principal
    sys.exit(main())
