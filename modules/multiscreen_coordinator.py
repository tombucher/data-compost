import os
import sys
import time
import json
import logging
import multiprocessing
import subprocess
import signal
from enum import Enum
from pathlib import Path

logger = logging.getLogger("CompostCoordinator")

# Définition des phases du processus
class CompostPhase(Enum):
    """Les 5 phases ordonnées du pipeline de compostage, du démarrage à la visualisation finale."""
    IDLE = 0
    FILE_ANALYSIS = 1
    CN_CALCULATION = 2
    SILO_CREATION = 3
    COMPOSTING = 4
    RESULT_VISUALIZATION = 5

class CompostVisualizer:
    """
    Coordinateur central pour le système de visualisation multiécran
    du processus de compostage numérique.
    """
    def __init__(self, input_directory, log_queue=None):
        self.input_directory = Path(input_directory)
        self.output_directory = Path('data/output')
        self.log_queue = log_queue
        self.current_phase = CompostPhase.IDLE
        self.phase_progress = 0.0
        self.processes = {}
        self.queues = {}
        
        # Créer les répertoires de sortie s'ils n'existent pas
        self.output_directory.mkdir(exist_ok=True, parents=True)
        
        # Chemins des fichiers de données intermédiaires
        self.analysis_results_path = self.output_directory / 'analysis_results.json'
        self.cn_results_path = self.analysis_results_path  # Même fichier, mis à jour
        self.silo_info_path = self.output_directory / 'silos' / 'silo_info.json'
        self.compost_output_path = self.output_directory / 'composted' / 'mixed_compost.bin'
        
        # S'assurer que les chemins existent
        (self.output_directory / 'silos').mkdir(exist_ok=True, parents=True)
        (self.output_directory / 'composted').mkdir(exist_ok=True, parents=True)
        
        # Initialiser les queues pour la communication inter-processus
        self.init_communication_queues()

    def init_communication_queues(self):
        """Initialise les queues pour la communication entre processus"""
        # Queue pour chaque écran
        self.queues = {
            'circular': multiprocessing.Queue(),  # Écran circulaire
            'hdmi': multiprocessing.Queue(),      # Écran HDMI principal
            'epaper': multiprocessing.Queue(),    # Écran e-paper
            'printer': multiprocessing.Queue(),   # Imprimante thermique
        }
        
        # Queue pour les mises à jour de progression
        self.progress_queue = multiprocessing.Queue()
        
        # Queue pour les signaux de terminaison
        self.stop_queue = multiprocessing.Queue()

    def start_display_processes(self):
        """Démarre les processus d'affichage pour chaque écran"""
        try:
            # Écran circulaire (processus Python)
            from displays.circular_display import start_circular_display
            self.processes['circular'] = multiprocessing.Process(
                target=start_circular_display,
                args=(self.queues['circular'], self.stop_queue, self.log_queue)
            )

            # Écran HDMI principal (processus Python)
            from displays.hdmi_display import start_hdmi_display
            self.processes['hdmi'] = multiprocessing.Process(
                target=start_hdmi_display,
                args=(self.queues['hdmi'], self.stop_queue, self.log_queue)
            )

            # Écran e-paper (processus Python)
            from displays.epaper_display import start_epaper_display
            self.processes['epaper'] = multiprocessing.Process(
                target=start_epaper_display,
                args=(self.queues['epaper'], self.stop_queue, str(self.cn_results_path), str(self.silo_info_path), self.log_queue)
            )
            
            # Démarrer les processus
            for name, process in self.processes.items():
                logger.info(f"Démarrage du processus d'affichage: {name}")
                process.start()
            
            logger.info("Tous les processus d'affichage sont démarrés")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du démarrage des processus d'affichage: {str(e)}")
            self.stop_all_processes()
            return False

    def update_displays(self, phase, progress, data=None):
        """
        Met à jour tous les écrans avec la phase et la progression actuelles
        """
        self.current_phase = phase
        self.phase_progress = progress
        
        # Préparer les données de mise à jour pour chaque écran
        update_data = {
            'phase': phase.value,
            'phase_name': phase.name,
            'progress': progress,
            'timestamp': time.time(),
            'data': data
        }
        
        # Envoyer les mises à jour à chaque écran
        for queue_name, queue in self.queues.items():
            if not queue.full():
                queue.put(update_data)
        
        logger.debug(f"Mise à jour des écrans: Phase={phase.name}, Progression={progress:.1f}%")

    def execute_analysis_phase(self):
        """Exécute la phase d'analyse des fichiers"""
        logger.info("Début de la phase d'analyse des fichiers")
        logger.info(f"Répertoire d'entrée: {self.input_directory}")
        self.update_displays(CompostPhase.FILE_ANALYSIS, 0.0)
        
        try:
            # Initialiser la visualisation
            from modules.analyze import count_files
            total_files = count_files(self.input_directory)
            logger.info(f"Nombre total de fichiers à analyser: {total_files}")
            
            # Créer une queue pour la visualisation
            visualization_queue = multiprocessing.Queue()
            update_queue = multiprocessing.Queue()
            ready_queue = multiprocessing.Queue()
            
            # Démarrer la visualisation dans un processus séparé
            from modules.file_analysis_visualization import start_visualization
            viz_process = multiprocessing.Process(
                target=start_visualization,
                args=(visualization_queue, update_queue, total_files, ready_queue, self.log_queue)
            )
            viz_process.daemon = True  # Marquer comme processus démon
            viz_process.start()
            
            # Attendre que la visualisation soit prête
            logger.info("Attente de l'initialisation de la visualisation...")
            ready_queue.get(timeout=10)
            
            # Lancer l'analyse
            from modules.analyze import analyze_directory
            self.analysis_results_path = analyze_directory(self.input_directory, visualization_queue)
            
            # Attendre que la visualisation se termine
            visualization_queue.put(None)
            update_queue.put(None)
            
            # Attendre un peu pour que la visualisation termine proprement
            viz_process.join(timeout=5)
            if viz_process.is_alive():
                logger.warning("Le processus de visualisation prend trop de temps, forçage de la terminaison")
                viz_process.terminate()
            
            logger.info(f"Analyse terminée. Résultats sauvegardés dans {self.analysis_results_path}")
            self.update_displays(CompostPhase.FILE_ANALYSIS, 100.0)
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de l'analyse des fichiers: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    def execute_cn_calculation_phase(self):
        """Exécute la phase de calcul des ratios C/N"""
        logger.info("Début de la phase de calcul des ratios C/N")
        self.update_displays(CompostPhase.CN_CALCULATION, 0.0)
        
        try:
            # Lancer le calcul C/N
            from modules.calculate_cn import calculate_cn
            self.cn_results_path = calculate_cn(self.analysis_results_path)
            
            # Charger les résultats pour les afficher
            with open(self.cn_results_path, 'r') as f:
                cn_results = json.load(f)
            
            # Mettre à jour les écrans avec les résultats
            self.update_displays(CompostPhase.CN_CALCULATION, 100.0, cn_results)
            
            logger.info(f"Calcul C/N terminé. Résultats sauvegardés dans {self.cn_results_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul C/N: {str(e)}")
            return False

    def execute_silo_creation_phase(self):
        """Exécute la phase de création des silos"""
        logger.info("Début de la phase de création des silos")
        self.update_displays(CompostPhase.SILO_CREATION, 0.0)
        
        try:
            # Lancer la création des silos
            from modules.create_silos import create_silos
            self.silo_info_path = create_silos(self.cn_results_path)
            
            # Charger les informations sur les silos pour les afficher
            with open(self.silo_info_path, 'r') as f:
                silo_info = json.load(f)
            
            # Mettre à jour les écrans avec les résultats
            self.update_displays(CompostPhase.SILO_CREATION, 100.0, silo_info)
            
            logger.info(f"Création des silos terminée. Informations sauvegardées dans {self.silo_info_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la création des silos: {str(e)}")
            return False

    def execute_composting_phase(self):
        """Exécute la phase de compostage (transformation des fichiers)"""
        logger.info("Début de la phase de compostage")
        self.update_displays(CompostPhase.COMPOSTING, 0.0)
        
        try:
            # Lancer le processus de compostage
            from modules.transformation import compost_process
            self.compost_output_path = compost_process(self.analysis_results_path)
            
            # Mettre à jour les écrans 
            self.update_displays(CompostPhase.COMPOSTING, 100.0)
            
            logger.info(f"Processus de compostage terminé. Résultat sauvegardé dans {self.compost_output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du processus de compostage: {str(e)}")
            return False

    def execute_visualization_phase(self):
        """Exécute la phase de visualisation du résultat"""
        logger.info("Début de la phase de visualisation du résultat")
        self.update_displays(CompostPhase.RESULT_VISUALIZATION, 0.0)
        
        try:
            # Lancer le visualiseur de compost dans un processus séparé
            visualizer_script = Path(__file__).parent / 'modules' / 'visualize_bin.py'
            
            if not visualizer_script.exists():
                visualizer_script = Path('modules') / 'visualize_bin.py'
            
            if not visualizer_script.exists():
                raise FileNotFoundError(f"Le script visualiseur n'existe pas: {visualizer_script}")
            
            # Lancer le visualiseur dans un processus séparé
            process = subprocess.Popen([sys.executable, str(visualizer_script), str(self.compost_output_path)])
            logger.info(f"Visualiseur binaire lancé avec PID: {process.pid}")
            
            # Mettre à jour les écrans
            self.update_displays(CompostPhase.RESULT_VISUALIZATION, 100.0)
            
            # Attendre que l'utilisateur ferme le visualiseur
            try:
                process.wait()
            except KeyboardInterrupt:
                logger.info("Interruption détectée, arrêt du visualiseur...")
                process.terminate()
            
            logger.info("Visualisation du résultat terminée")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors de la visualisation du résultat: {str(e)}")
            return False

    def run_full_process(self):
        """Exécute le processus complet de compostage numérique"""
        logger.info("Démarrage du processus complet de compostage numérique")
        
        # Démarrer les processus d'affichage
        if not self.start_display_processes():
            logger.error("Impossible de démarrer les processus d'affichage. Arrêt.")
            return False
        
        try:
            # Phase 1: Analyse des fichiers
            if not self.execute_analysis_phase():
                raise Exception("Échec de la phase d'analyse")
            
            # Phase 2: Calcul des ratios C/N
            if not self.execute_cn_calculation_phase():
                raise Exception("Échec de la phase de calcul C/N")
            
            # Phase 3: Création des silos
            if not self.execute_silo_creation_phase():
                raise Exception("Échec de la phase de création des silos")
            
            # Phase 4: Compostage
            if not self.execute_composting_phase():
                raise Exception("Échec de la phase de compostage")
            
            # Phase 5: Visualisation du résultat
            if not self.execute_visualization_phase():
                raise Exception("Échec de la phase de visualisation")
            
            logger.info("Processus complet de compostage numérique terminé avec succès")
            return True
            
        except Exception as e:
            logger.error(f"Erreur lors du processus complet: {str(e)}")
            return False
            
        finally:
            # Arrêter tous les processus d'affichage
            self.stop_all_processes()

    def stop_all_processes(self):
        """Arrête tous les processus d'affichage"""
        logger.info("Arrêt de tous les processus d'affichage")
        
        # Envoyer un signal d'arrêt à tous les processus
        for _ in range(len(self.processes)):
            self.stop_queue.put(True)
        
        # Attendre que les processus se terminent
        for name, process in self.processes.items():
            if process and process.is_alive():
                logger.info(f"Attente de la terminaison du processus: {name}")
                process.join(timeout=2)  # Réduire le timeout
                if process.is_alive():
                    logger.warning(f"Le processus {name} ne répond pas, terminaison forcée")
                    process.terminate()
                    # Si nécessaire, kill pour être sûr
                    process.kill() if hasattr(process, 'kill') else None
        
        # Vider toutes les queues pour éviter les blocages
        for queue_name, queue in self.queues.items():
            while not queue.empty():
                try:
                    queue.get(block=False)
                except:
                    pass
                    
        logger.info("Tous les processus d'affichage ont été arrêtés")

def main():
    """Fonction principale"""
    import argparse
    parser = argparse.ArgumentParser(description="Système de compostage numérique")
    parser.add_argument("--input", type=str, default="data/test", help="Répertoire d'entrée contenant les fichiers à composter")
    args = parser.parse_args()
    
    # Créer et exécuter le visualiseur de compostage
    visualizer = CompostVisualizer(args.input)
    try:
        visualizer.run_full_process()
    except KeyboardInterrupt:
        logger.info("Interruption détectée, arrêt du programme")
        visualizer.stop_all_processes()

if __name__ == "__main__":
    main()
