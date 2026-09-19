import pygame
import math
import time
import logging
import multiprocessing

from modules.phases import (
    CompostPhase, PHASE_COLORS, PHASE_DESCRIPTIONS, coerce_phase,
)

logger = logging.getLogger("CircularDisplay")



class CircularProgressDisplay:
    """
    Classe pour gérer l'affichage sur l'écran circulaire.
    Montre la phase actuelle et la progression sous forme d'anneau.
    """
    def __init__(self, screen_size=(320, 320)):
        """Initialise l'affichage circulaire"""
        self.width, self.height = screen_size
        self.center = (self.width // 2, self.height // 2)
        self.radius = min(self.width, self.height) // 2 - 20
        
        # Initialiser Pygame
        pygame.init()
        pygame.font.init()
        
        # Créer la fenêtre
        self.screen = pygame.display.set_mode(screen_size)
        pygame.display.set_caption("Compost Process - Circular Display")
        
        # Polices pour le texte
        self.phase_font = pygame.font.SysFont('Arial', 28, bold=True)
        self.progress_font = pygame.font.SysFont('Arial', 40, bold=True)
        self.description_font = pygame.font.SysFont('Arial', 14)
        
        # État initial
        self.current_phase = CompostPhase.IDLE
        self.progress = 0.0
        self.last_update_time = time.time()
        
        # Épaisseur de l'anneau
        self.ring_thickness = 20
        
        # Animation
        self.animation_offset = 0
        self.animation_speed = 1
        
        logger.info("CircularProgressDisplay initialized")

    def update(self, phase, progress):
        """Met à jour l'état actuel de l'affichage"""
        try:
            # Convertir en CompostPhase si c'est un entier
            if isinstance(phase, int):
                phase = CompostPhase(phase)
            self.current_phase = phase
            self.progress = progress
            self.last_update_time = time.time()
            logger.debug(f"Updated to Phase={phase.name}, Progress={progress:.1f}%")
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")

    def draw(self):
        """Dessine l'interface circulaire"""
        # Effacer l'écran avec un fond noir
        self.screen.fill((0, 0, 0))
        
        # Dessiner l'anneau de progression externe
        self._draw_progress_ring()
        
        # Dessiner le cercle intérieur avec la couleur de la phase actuelle
        phase_color = PHASE_COLORS[self.current_phase]
        pygame.draw.circle(self.screen, phase_color, self.center, self.radius - self.ring_thickness - 10)
        
        # Dessiner le texte de la phase
        self._draw_phase_text()
        
        # Dessiner le pourcentage de progression
        self._draw_progress_text()
        
        # Mettre à jour l'écran
        pygame.display.flip()

    def _draw_progress_ring(self):
        """Dessine l'anneau de progression animé"""
        phase_color = PHASE_COLORS[self.current_phase]
        
        # Mettre à jour l'animation
        self.animation_offset = (self.animation_offset + self.animation_speed) % 360
        
        # Dessiner l'anneau de fond (gris)
        pygame.draw.circle(self.screen, (40, 40, 40), self.center, self.radius)
        pygame.draw.circle(self.screen, (0, 0, 0), self.center, self.radius - self.ring_thickness)
        
        # Dessiner l'anneau de progression
        if self.progress > 0:
            # Calculer l'angle correspondant à la progression
            angle = int(360 * self.progress / 100)
            
            # Dessiner l'arc de progression
            for i in range(angle):
                # Ajouter un effet de dégradé et d'animation
                pos = i - self.animation_offset
                if pos < 0:
                    pos += 360
                    
                # Faire varier légèrement la teinte pour créer un effet d'animation
                r, g, b = phase_color
                intensity = 0.7 + 0.3 * math.sin(math.radians(pos * 2))
                color = (int(r * intensity), int(g * intensity), int(b * intensity))
                
                # Convertir l'angle en radians
                rad = math.radians(i - 90)  # -90 pour commencer en haut
                
                # Calculer les points pour l'arc
                x1 = self.center[0] + (self.radius - self.ring_thickness) * math.cos(rad)
                y1 = self.center[1] + (self.radius - self.ring_thickness) * math.sin(rad)
                x2 = self.center[0] + self.radius * math.cos(rad)
                y2 = self.center[1] + self.radius * math.sin(rad)
                
                # Dessiner une ligne pour chaque degré de l'arc
                pygame.draw.line(self.screen, color, (x1, y1), (x2, y2), 2)

    def _draw_phase_text(self):
        """Dessine le texte indiquant la phase actuelle"""
        phase_name = PHASE_DESCRIPTIONS[self.current_phase]
        
        # Rendre le texte de la phase
        phase_text = self.phase_font.render(phase_name, True, (255, 255, 255))
        
        # Positionner le texte au centre
        text_rect = phase_text.get_rect(center=(self.center[0], self.center[1] - 20))
        
        # Dessiner le texte
        self.screen.blit(phase_text, text_rect)

    def _draw_progress_text(self):
        """Dessine le texte indiquant le pourcentage de progression"""
        # Rendre le texte du pourcentage
        progress_text = self.progress_font.render(f"{int(self.progress)}%", True, (255, 255, 255))
        
        # Positionner le texte au centre
        text_rect = progress_text.get_rect(center=(self.center[0], self.center[1] + 30))
        
        # Dessiner le texte
        self.screen.blit(progress_text, text_rect)

def start_circular_display(update_queue, stop_queue, log_queue=None):
    """
    Fonction principale pour démarrer l'affichage circulaire dans un processus séparé.

    Args:
        update_queue: Queue pour recevoir les mises à jour d'état
        stop_queue: Queue pour recevoir les signaux d'arrêt
        log_queue: Queue partagée pour le logging centralisé (optionnel)
    """
    from modules.logging_config import setup_worker_logging
    setup_worker_logging(log_queue)
    try:
        logger.info("Starting circular display process")
        
        # Initialiser l'affichage
        display = CircularProgressDisplay()
        
        # Horloge pour contrôler le framerate
        clock = pygame.time.Clock()
        running = True
        
        while running:
            # Vérifier s'il y a un signal d'arrêt
            if not stop_queue.empty():
                stop_queue.get()
                running = False
                break
            
            # Vérifier s'il y a des mises à jour
            try:
                if not update_queue.empty():
                    update_data = update_queue.get(block=False)
                    phase = update_data['phase']
                    progress = update_data['progress']
                    display.update(phase, progress)
            except (multiprocessing.queues.Empty, KeyError) as e:
                logger.debug(f"Queue error: {str(e)}")
            
            # Gérer les événements Pygame
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
            
            # Dessiner l'interface
            display.draw()
            
            # Contrôler le framerate
            clock.tick(30)
        
        # Nettoyage
        pygame.quit()
        logger.info("Circular display process stopped")
        
    except Exception as e:
        logger.error(f"Error in circular display process: {str(e)}")
        pygame.quit()

if __name__ == "__main__":
    # Test de l'affichage circulaire
    # Crée une queue fictive pour simuler des mises à jour
    test_queue = multiprocessing.Queue()
    stop_queue = multiprocessing.Queue()
    
    # Démarrer l'affichage dans le processus principal
    display = CircularProgressDisplay()
    
    # Simuler des mises à jour de progression
    phases = list(CompostPhase)
    current_phase_index = 0
    progress = 0
    
    clock = pygame.time.Clock()
    running = True
    
    while running:
        # Gérer les événements
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Mettre à jour la progression
        progress += 0.2
        if progress >= 100:
            progress = 0
            current_phase_index = (current_phase_index + 1) % len(phases)
        
        display.update(phases[current_phase_index], progress)
        display.draw()
        
        clock.tick(30)
    
    pygame.quit()
