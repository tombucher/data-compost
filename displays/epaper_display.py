import pygame
import json
import os
import sys
import logging
import traceback
import multiprocessing
from enum import Enum

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("EPaperDisplay")

# Définition des phases du processus
class CompostPhase(Enum):
    IDLE = 0
    FILE_ANALYSIS = 1
    CN_CALCULATION = 2
    SILO_CREATION = 3
    COMPOSTING = 4
    RESULT_VISUALIZATION = 5

# Constantes
# Dimensions standard pour un écran ePaper 2.9" (296x128 pixels)
WINDOW_SIZE = (296, 128)  
BACKGROUND_COLOR = (255, 255, 255)  # Fond blanc pour e-paper
TEXT_COLOR = (0, 0, 0)  # Texte noir
HIGHLIGHT_COLOR = (50, 50, 50)  # Gris foncé

# Définir les classes de fichiers bruns (carbonés) et verts (azotés)
BROWN_CATEGORIES = ["system", "compressed", "executable", "hidden"]
GREEN_CATEGORIES = ["image", "audio", "video", "text", "document", "creative"]

class EPaperVisualizer:
    def __init__(self):
        """Initialise l'affichage des informations sur le compost pour écran ePaper."""
        try:
            # Initialiser Pygame
            pygame.init()
            self.screen = pygame.display.set_mode(WINDOW_SIZE)
            pygame.display.set_caption("Data Compost - E-paper Display")
            
            # Polices adaptées à l'écran ePaper
            self.title_font = pygame.font.SysFont('Courier', 16, bold=True)
            self.text_font = pygame.font.SysFont('Courier', 10)
            self.small_font = pygame.font.SysFont('Courier', 8)
            
            # État de l'interface
            self.current_page = 0
            self.max_pages = 3
            self.current_phase = CompostPhase.IDLE
            self.progress = 0.0
            
            # Données
            self.cn_data = None
            self.silo_data = None
            self.summary_data = {
                'total_files': 0,
                'brown_files': 0,
                'green_files': 0,
                'avg_cn_ratio': 0,
                'categories': {}
            }
            
        except Exception as e:
            logging.error(f"Erreur d'initialisation: {str(e)}")
            traceback.print_exc()
            pygame.quit()
            raise
    
    def update(self, phase, progress, data=None):
        """Met à jour l'état de l'affichage"""
        self.current_phase = phase if isinstance(phase, CompostPhase) else CompostPhase(phase)
        self.progress = progress
        
        # Mettre à jour les données si fournies
        if data is not None:
            if self.current_phase == CompostPhase.CN_CALCULATION:
                self.cn_data = data
                self._calculate_statistics()
            elif self.current_phase == CompostPhase.SILO_CREATION:
                self.silo_data = data
    
    def load_data(self, cn_results_path, silo_info_path=None):
        """Charge les données des fichiers JSON."""
        try:
            logging.info(f"Chargement des données depuis {cn_results_path}")
            if not os.path.exists(cn_results_path):
                logging.error(f"Le fichier {cn_results_path} n'existe pas")
                return False
                
            with open(cn_results_path, 'r') as f:
                self.cn_data = json.load(f)
                
            # Calculer les statistiques
            self._calculate_statistics()
                
            if silo_info_path and os.path.exists(silo_info_path):
                logging.info(f"Chargement des données de silos depuis {silo_info_path}")
                with open(silo_info_path, 'r') as f:
                    self.silo_data = json.load(f)
            
            return True
        except Exception as e:
            logging.error(f"Erreur lors du chargement des données: {str(e)}")
            traceback.print_exc()
            return False
    
    def _calculate_statistics(self):
        """Calcule les statistiques à partir des données CN."""
        if not self.cn_data:
            return
                
        self.summary_data['total_files'] = len(self.cn_data)
        
        # Compteurs par catégorie réelle
        categories = {}
        brown_files = 0
        green_files = 0
        total_cn_ratio = 0
        
        for file_data in self.cn_data:
            # Vérifier que les clés nécessaires existent
            if 'category' not in file_data:
                continue
                    
            category = file_data.get('category', 'unknown')
            cn_data = file_data.get('cn_data', {})
            file_type = cn_data.get('file_type', 'unknown')
            normalized_cn = cn_data.get('normalized_cn_ratio', 0)
            
            # Compter par catégorie réelle
            categories[category] = categories.get(category, 0) + 1
            
            # Compter les fichiers bruns/verts
            if file_type == 'brown':
                brown_files += 1
            elif file_type == 'green':
                green_files += 1
                    
            # Calculer le ratio C/N moyen
            total_cn_ratio += normalized_cn
        
        # Mettre à jour les statistiques
        self.summary_data['brown_files'] = brown_files
        self.summary_data['green_files'] = green_files
        self.summary_data['avg_cn_ratio'] = total_cn_ratio / len(self.cn_data) if self.cn_data else 0
        self.summary_data['categories'] = categories
        
        # Log pour débogage
        logging.info(f"Statistiques calculées: {self.summary_data}")
    
    def _draw_text(self, text, font, color, x, y):
        """Dessine un texte à une position spécifique."""
        try:
            text_surface = font.render(text, True, color)
            self.screen.blit(text_surface, (x, y))
            return text_surface.get_rect().height + y
        except Exception as e:
            logging.error(f"Erreur lors du dessin de texte: {str(e)}")
            return y + 10
    
    def _draw_text_centered(self, text, font, color, y, x=None):
        """Dessine un texte centré horizontalement."""
        try:
            text_surface = font.render(text, True, color)
            text_rect = text_surface.get_rect()
            if x is None:
                text_rect.centerx = self.screen.get_rect().centerx
            else:
                text_rect.x = x
            text_rect.y = y
            self.screen.blit(text_surface, text_rect)
            return text_rect.bottom
        except Exception as e:
            logging.error(f"Erreur lors du dessin de texte: {str(e)}")
            return y + 10
    
    def _draw_progress_bar(self, x, y, width, height, progress, min_val=0, max_val=100, current_val=None):
        """Dessine une barre de progression simple."""
        try:
            # Dessiner le cadre
            pygame.draw.rect(self.screen, TEXT_COLOR, (x, y, width, height), 1)
            
            # Dessiner la progression
            fill_width = int((progress - min_val) / (max_val - min_val) * width)
            if fill_width > 0:
                pygame.draw.rect(self.screen, TEXT_COLOR, (x, y, fill_width, height))
            
            # Afficher la valeur actuelle si fournie
            if current_val is not None:
                val_text = f"{current_val:.1f}"
                val_surf = self.small_font.render(val_text, True, TEXT_COLOR)
                val_rect = val_surf.get_rect(center=(x + fill_width, y + height // 2))
                self.screen.blit(val_surf, val_rect)
            
            return y + height
        except Exception as e:
            logging.error(f"Erreur lors du dessin de la barre de progression: {str(e)}")
            return y + height
    
    def _draw_summary_page(self):
        """Dessine la page de résumé des données - ultra minimaliste."""
        try:
            # Fond blanc pour l'ePaper
            self.screen.fill(BACKGROUND_COLOR)
            
            # Titre
            y = 5
            y = self._draw_text_centered("DATA COMPOST", self.title_font, TEXT_COLOR, y) + 5
            pygame.draw.line(self.screen, TEXT_COLOR, (10, y), (WINDOW_SIZE[0] - 10, y), 1)
            y += 10
            
            # Afficher la phase actuelle
            phase_name = self.current_phase.name.replace('_', ' ')
            y = self._draw_text(f"PHASE: {phase_name}", self.text_font, TEXT_COLOR, 10, y) + 5
            
            # Barre de progression de la phase
            y = self._draw_progress_bar(10, y, WINDOW_SIZE[0] - 20, 5, self.progress, current_val=self.progress)
            y += 5
            
            # Statistiques clés
            total_files = self.summary_data['total_files']
            brown_files = self.summary_data['brown_files']
            green_files = self.summary_data['green_files']
            avg_cn_ratio = self.summary_data['avg_cn_ratio']
            
            y = self._draw_text(f"FILES: {total_files}", self.text_font, TEXT_COLOR, 10, y) + 5
            y = self._draw_text(f"BROWN: {brown_files}", self.text_font, TEXT_COLOR, 10, y) + 5
            y = self._draw_text(f"GREEN: {green_files}", self.text_font, TEXT_COLOR, 10, y) + 5
            
            # Ratio C/N avec barre simple
            y = self._draw_text(f"C/N RATIO: {avg_cn_ratio:.1f}", self.text_font, TEXT_COLOR, 10, y) + 5
            self._draw_progress_bar(10, y, WINDOW_SIZE[0] - 20, 10, avg_cn_ratio, 0, 100)
            
            # Calculer le nombre total de pages
            total_silo_pages = (len(self.silo_data or []) + 2) // 3  # 3 silos max par page
            self.max_pages = 2 + max(1, total_silo_pages)
            
            # Indicateur de page en bas
            y = WINDOW_SIZE[1] - 15
            page_text = f"< PAGE {self.current_page + 1}/{self.max_pages} >"
            self._draw_text_centered(page_text, self.small_font, TEXT_COLOR, y)
            
        except Exception as e:
            logging.error(f"Erreur page résumé: {str(e)}")
            traceback.print_exc()

    def _draw_materials_page(self):
        """Dessine la page des matières - ultra minimaliste."""
        try:
            # Fond blanc pour l'ePaper
            self.screen.fill(BACKGROUND_COLOR)
            
            # Titre
            y = 5
            y = self._draw_text_centered("MATERIALS", self.title_font, TEXT_COLOR, y) + 5
            pygame.draw.line(self.screen, TEXT_COLOR, (10, y), (WINDOW_SIZE[0] - 10, y), 1)
            y += 5
            
            # Division de la page en deux colonnes
            col_width = WINDOW_SIZE[0] // 2
            
            # Colonne gauche - Matières brunes
            left_y = y
            self._draw_text("BROWN (C)", self.text_font, TEXT_COLOR, 10, left_y)
            left_y += 15
            
            # Catégories prédéfinies pour les matières brunes
            brown_counts = {cat: 0 for cat in BROWN_CATEGORIES}
            other_brown_count = 0
            
            # Compter les fichiers par catégorie
            for file_data in self.cn_data or []:
                if file_data.get('cn_data', {}).get('file_type') == 'brown':
                    category = file_data.get('category', 'unknown')
                    if category in brown_counts:
                        brown_counts[category] += 1
                    else:
                        other_brown_count += 1
            
            # Afficher les catégories prédéfinies (non vides)
            displayed = 0
            for cat, count in brown_counts.items():
                if count > 0:
                    left_y = self._draw_text(f"- {cat[:3].upper()}: {count}", self.small_font, 
                                          TEXT_COLOR, 10, left_y) + 5
                    displayed += 1
                    if displayed >= 2:  # Limiter à 2 catégories pour laisser de la place à "Autres"
                        break
            
            # Afficher la catégorie "Autres" si nécessaire
            if other_brown_count > 0:
                left_y = self._draw_text(f"- OTHER: {other_brown_count}", self.small_font, 
                                      TEXT_COLOR, 10, left_y) + 5
            
            # Si aucune catégorie affichée
            if displayed == 0 and other_brown_count == 0:
                left_y = self._draw_text("- None", self.small_font, TEXT_COLOR, 10, left_y) + 5
            
            # Colonne droite - Matières vertes
            right_y = y
            self._draw_text("GREEN (N)", self.text_font, TEXT_COLOR, col_width + 10, right_y)
            right_y += 15
            
            # Catégories prédéfinies pour les matières vertes
            green_counts = {cat: 0 for cat in GREEN_CATEGORIES}
            other_green_count = 0
            
            # Compter les fichiers par catégorie
            for file_data in self.cn_data or []:
                if file_data.get('cn_data', {}).get('file_type') == 'green':
                    category = file_data.get('category', 'unknown')
                    if category in green_counts:
                        green_counts[category] += 1
                    else:
                        other_green_count += 1
            
            # Afficher les catégories prédéfinies (non vides)
            displayed = 0
            for cat, count in sorted(green_counts.items(), key=lambda x: x[1], reverse=True):
                if count > 0:
                    right_y = self._draw_text(f"- {cat[:3].upper()}: {count}", self.small_font, 
                                          TEXT_COLOR, col_width + 10, right_y) + 5
                    displayed += 1
                    if displayed >= 2:  # Limiter à 2 catégories pour laisser de la place à "Autres"
                        break
            
            # Afficher la catégorie "Autres" si nécessaire
            if other_green_count > 0:
                right_y = self._draw_text(f"- OTHER: {other_green_count}", self.small_font, 
                                      TEXT_COLOR, col_width + 10, right_y) + 5
            
            # Si aucune catégorie affichée
            if displayed == 0 and other_green_count == 0:
                right_y = self._draw_text("- None", self.small_font, TEXT_COLOR, col_width + 10, right_y) + 5
            
            # Ratio idéal
            y = max(left_y, right_y) + 5
            ideal_text = "IDEAL C/N: 25:1 to 30:1"
            self._draw_text_centered(ideal_text, self.small_font, TEXT_COLOR, y)
            
            # Indicateur de page en bas
            y = WINDOW_SIZE[1] - 15
            page_text = f"< PAGE {self.current_page + 1}/{self.max_pages} >"
            self._draw_text_centered(page_text, self.small_font, TEXT_COLOR, y)
            
        except Exception as e:
            logging.error(f"Erreur page matières: {str(e)}")
            traceback.print_exc()

    def _draw_silos_page(self):
        """Dessine la page des silos - ultra minimaliste."""
        try:
            # Fond blanc pour l'ePaper
            self.screen.fill(BACKGROUND_COLOR)
            
            # Titre
            y = 5
            page_num = self.current_page
            total_silo_pages = (len(self.silo_data or []) + 2) // 3  # 3 silos max par page
            current_silo_page = page_num - 2  # Pages 0 et 1 sont pour résumé et matières
            
            title = f"SILOS {current_silo_page + 1}/{max(1, total_silo_pages)}"
            y = self._draw_text_centered(title, self.title_font, TEXT_COLOR, y) + 5
            pygame.draw.line(self.screen, TEXT_COLOR, (10, y), (WINDOW_SIZE[0] - 10, y), 1)
            y += 10
            
            if self.silo_data:
                # Calculer quels silos afficher sur cette page
                start_idx = current_silo_page * 3
                end_idx = min(start_idx + 3, len(self.silo_data))
                
                # Tableau minimaliste des silos pour cette page
                for i in range(start_idx, end_idx):
                    silo = self.silo_data[i]
                    silo_id = silo.get('silo_id', i+1)
                    file_count = silo.get('file_count', 0)
                    avg_cn = silo.get('avg_normalized_cn_ratio', 0)
                    
                    # Une ligne par silo
                    silo_line = f"SILO {silo_id}: {file_count} files, C/N {avg_cn:.1f}"
                    y = self._draw_text(silo_line, self.text_font, TEXT_COLOR, 10, y) + 3
                    
                    # Barre de progression pour le ratio C/N
                    self._draw_progress_bar(10, y, WINDOW_SIZE[0] - 20, 8, avg_cn, 0, 100)
                    y += 12
            else:
                # Message si aucune donnée
                y = self._draw_text_centered("NO SILO DATA", self.text_font, TEXT_COLOR, y + 30)
            
            # Indicateur de page en bas
            y = WINDOW_SIZE[1] - 15
            page_text = f"< PAGE {self.current_page + 1}/{self.max_pages} >"
            self._draw_text_centered(page_text, self.small_font, TEXT_COLOR, y)
            
        except Exception as e:
            logging.error(f"Erreur page silos: {str(e)}")
            traceback.print_exc()
    
    def draw(self):
        """Dessine la page actuelle"""
        if self.current_page == 0:
            self._draw_summary_page()
        elif self.current_page == 1:
            self._draw_materials_page()
        else:
            self._draw_silos_page()
    
    def display(self, update_queue=None, stop_queue=None):
        """Affiche les informations et gère l'interface utilisateur."""
        running = True
        clock = pygame.time.Clock()
        
        try:
            # Calculer le nombre total de pages
            if self.silo_data:
                total_silo_pages = (len(self.silo_data) + 2) // 3  # 3 silos max par page
                self.max_pages = 2 + total_silo_pages  # Page résumé + page matières + pages silos
            else:
                self.max_pages = 3  # Page résumé + page matières + 1 page silos vide
            
            while running:
                # Vérifier les événements Pygame
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            running = False
                        elif event.key == pygame.K_RIGHT:
                            self.current_page = (self.current_page + 1) % self.max_pages
                        elif event.key == pygame.K_LEFT:
                            self.current_page = (self.current_page - 1) % self.max_pages
                
                # Vérifier s'il y a un signal d'arrêt
                if stop_queue and not stop_queue.empty():
                    stop_queue.get()
                    running = False
                
                # Vérifier s'il y a des mises à jour de données
                if update_queue and not update_queue.empty():
                    try:
                        update_data = update_queue.get(block=False)
                        phase = update_data.get('phase')
                        progress = update_data.get('progress', 0.0)
                        data = update_data.get('data')
                        self.update(phase, progress, data)
                    except Exception as e:
                        logging.error(f"Erreur lors de la mise à jour : {str(e)}")
                
                # Dessiner la page actuelle
                self.draw()
                
                # Actualiser l'affichage
                pygame.display.flip()
                clock.tick(5)  # Rafraîchissement lent pour l'ePaper
        except Exception as e:
            logging.error(f"Erreur d'affichage: {str(e)}")
            traceback.print_exc()
        finally:
            pygame.quit()

def start_epaper_display(update_queue, stop_queue, cn_results_path=None, silo_info_path=None):
    """
    Fonction principale pour démarrer l'affichage ePaper dans un processus séparé.
    
    Args:
        update_queue: Queue pour recevoir les mises à jour d'état
        stop_queue: Queue pour recevoir les signaux d'arrêt
        cn_results_path: Chemin vers les résultats d'analyse C/N (optionnel)
        silo_info_path: Chemin vers les informations sur les silos (optionnel)
    """
    try:
        logging.info("Starting ePaper display process")
        
        # Initialiser l'affichage
        display = EPaperVisualizer()
        
        # Charger les données si les chemins sont fournis
        if cn_results_path:
            display.load_data(cn_results_path, silo_info_path)
        
        # Lancer l'affichage
        display.display(update_queue, stop_queue)
        
        logging.info("ePaper display process stopped")
        
    except Exception as e:
        logging.error(f"Error in ePaper display process: {str(e)}")
        pygame.quit()

def display_compost_info(cn_results_path, silo_info_path=None):
    """Fonction principale pour afficher les informations sur le compost (compatible avec le code existant)."""
    try:
        logging.info("Initialisation de l'affichage ePaper")
        display = EPaperVisualizer()
        
        logging.info(f"Chargement des données depuis {cn_results_path}")
        success = display.load_data(cn_results_path, silo_info_path)
        
        if success:
            logging.info("Affichage de l'interface utilisateur")
            display.display()
        else:
            logging.error("Impossible de charger les données")
    except Exception as e:
        logging.error(f"Erreur: {str(e)}")
        traceback.print_exc()
        pygame.quit()

if __name__ == "__main__":
    # Si lancé directement, utiliser les paramètres de ligne de commande
    if len(sys.argv) < 2:
        print("Usage: python epaper_display.py <cn_results_path> [silo_info_path]")
        sys.exit(1)
    
    cn_results_path = sys.argv[1]
    silo_info_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    display_compost_info(cn_results_path, silo_info_path)