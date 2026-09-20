import pygame
from queue import Empty
import math

# Constantes
WINDOW_SIZE = (1024, 1024)
BACKGROUND_COLOR = (0, 0, 0)  # Fond noir
SQUARE_BORDER_COLOR = (255, 255, 255)  # Contour blanc
TEXT_COLOR = (255, 255, 255)  # Texte blanc
MARGIN = 5
MIN_SQUARE_SIZE = 5
# Durée d'affichage du résultat final avant fermeture
LINGER_MS = 1500
MAX_SQUARE_SIZE = 500
SCALE_FACTOR = 10 / 10000  # 10ko = 1px

def calculate_square_size(file_size):
    """Calcule la taille du carré basée sur le poids du fichier."""
    size = int(math.sqrt(file_size * SCALE_FACTOR))
    return max(min(size, MAX_SQUARE_SIZE), MIN_SQUARE_SIZE)

def draw_square(screen, x, y, size):
    """Dessine un carré au contour blanc, sans remplissage."""
    pygame.draw.rect(screen, SQUARE_BORDER_COLOR, (x, y, size, size), 1)

def draw_progress_bar(screen, progress):
    """Dessine la barre de progression."""
    bar_width = WINDOW_SIZE[0] - 40
    bar_height = 20
    x = 20
    y = WINDOW_SIZE[1] - 40
    pygame.draw.rect(screen, (100, 100, 100), (x, y, bar_width, bar_height))
    pygame.draw.rect(screen, (200, 200, 200), (x, y, int(bar_width * progress), bar_height))

def start_visualization(queue, update_queue, total_files, ready_queue=None, log_queue=None):
    from modules.logging_config import setup_worker_logging
    setup_worker_logging(log_queue)
    pygame.init()
    font = pygame.font.Font(None, 24)
    small_font = pygame.font.Font(None, 20)

    files = {}
    current_file = None
    processed_files = 0
    max_y = MARGIN
    x, y = MARGIN, MARGIN

    clock = pygame.time.Clock()
    running = True
    finished_at = None

    # Initialiser la fenêtre et signaler que nous sommes prêts
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Visualisation de l'analyse des fichiers")
    
    # Signaler que l'initialisation est terminée
    if ready_queue:
        ready_queue.put(True)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill(BACKGROUND_COLOR)

        # Traiter les nouveaux fichiers
        try:
            while True:
                file_info = queue.get_nowait()
                if file_info is None:
                    # Fin de l'analyse : laisser le dernier état visible un
                    # instant, puis rendre la main. Sans cela le processus
                    # tournait indéfiniment et le coordinateur le terminait de
                    # force à chaque exécution.
                    finished_at = pygame.time.get_ticks()
                    break
                file_name, file_size, category = file_info
                size = calculate_square_size(file_size)
                
                if x + size + MARGIN > WINDOW_SIZE[0]:
                    # Passer à la ligne suivante
                    x = MARGIN
                    y = max_y + MARGIN
                    max_y = y + size
                else:
                    max_y = max(max_y, y + size)
                
                if y + size > WINDOW_SIZE[1] - 100:
                    # Réinitialiser si on atteint le bas de l'écran
                    x, y = MARGIN, MARGIN
                    max_y = MARGIN
                
                files[file_name] = {
                    'name': file_name,
                    'size': file_size,
                    'cn_ratio': 'N/A',
                    'category': category,
                    'x': x,
                    'y': y,
                    'visual_size': size
                }
                
                x += size + MARGIN
                current_file = files[file_name]
                processed_files += 1
        except Empty:
            pass

        # Traiter les mises à jour CN
        try:
            while True:
                update_info = update_queue.get_nowait()
                if update_info is None:
                    break
                file_name, cn_ratio = update_info
                if file_name in files:
                    files[file_name]['cn_ratio'] = cn_ratio
        except Empty:
            pass

        # Dessiner tous les carrés
        for file in files.values():
            draw_square(screen, file['x'], file['y'], file['visual_size'])

        # Afficher les informations au survol
        mouse_pos = pygame.mouse.get_pos()
        for file in files.values():
            if file['x'] < mouse_pos[0] < file['x'] + file['visual_size'] and \
               file['y'] < mouse_pos[1] < file['y'] + file['visual_size']:
                info_text = f"Nom: {file['name']}\n"
                info_text += f"Taille: {file['size'] / 1024:.2f} Ko\n"
                info_text += f"Ratio CN: {file['cn_ratio']}\n"
                info_text += f"Catégorie: {file['category']}"
                
                lines = info_text.split('\n')
                for i, line in enumerate(lines):
                    text_surface = small_font.render(line, True, TEXT_COLOR)
                    screen.blit(text_surface, (mouse_pos[0] + 10, mouse_pos[1] + i * 20))

        # Afficher le fichier en cours d'analyse
        if current_file:
            text = font.render(f"En cours: {current_file['name']} ({current_file['size'] / 1024:.2f} Ko)", True, TEXT_COLOR)
            screen.blit(text, (MARGIN, WINDOW_SIZE[1] - 70))

        # Dessiner la barre de progression
        progress = processed_files / total_files if total_files > 0 else 0
        draw_progress_bar(screen, progress)

        pygame.display.flip()
        clock.tick(30)  # 30 FPS

        if finished_at is not None and pygame.time.get_ticks() - finished_at >= LINGER_MS:
            running = False

    pygame.quit()

if __name__ == "__main__":
    # Ce bloc ne sera pas exécuté lorsque le module est importé
    pass