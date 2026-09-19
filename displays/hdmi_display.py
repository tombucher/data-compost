import pygame
import pygame.freetype
import math
import time
import random
import json
import logging
import multiprocessing
import numpy as np
from collections import defaultdict
import os
from pathlib import Path

from modules.phases import CompostPhase, PHASE_COLORS, coerce_phase
from modules.calculate_cn import CN_CEILING, cn_position

logger = logging.getLogger("HDMIDisplay")



class HDMIDisplay:
    """
    Classe pour gérer l'affichage principal sur l'écran HDMI.
    Montre des visualisations différentes selon la phase du processus.
    """
    def __init__(self, screen_size=(1280, 720)):
        """Initialise l'affichage HDMI"""
        self.width, self.height = screen_size
        
        # Initialiser Pygame
        pygame.init()
        pygame.freetype.init()
        
        # Créer la fenêtre
        self.screen = pygame.display.set_mode(screen_size)
        pygame.display.set_caption("Compost Process - Main Display")
        
        # Polices pour le texte
        self.title_font = pygame.freetype.SysFont('Arial', 32, bold=True)
        self.subtitle_font = pygame.freetype.SysFont('Arial', 24)
        self.text_font = pygame.freetype.SysFont('Arial', 16)
        self.mono_font = pygame.freetype.SysFont('Courier New', 14)
        
        # État initial
        self.current_phase = CompostPhase.IDLE
        self.progress = 0.0
        self.last_update_time = time.time()
        self.data = None
        
        # Paramètres d'animation
        self.particles = []
        self.file_nodes = {}  # Pour stocker les nœuds représentant les fichiers
        self.silos = []       # Pour stocker les représentations des silos
        self.animation_time = 0
        
        # Historique des mises à jour pour animations
        self.history = {
            'analysis': [],   # Fichiers analysés
            'cn_ratios': {},  # Ratios C/N par fichier
            'silos': [],      # Configurations des silos
        }
        
        logger.info("HDMI Display initialized")

    def update(self, phase, progress, data=None):
        """Met à jour l'état actuel de l'affichage"""
        try:
            # Convertir en CompostPhase si c'est un entier
            if isinstance(phase, int):
                phase = CompostPhase(phase)
            self.current_phase = phase
            self.progress = progress
            self.last_update_time = time.time()
            
            # Stocker les nouvelles données
            if data is not None:
                self.data = data
                self._process_data()
                
            logger.debug(f"Updated to Phase={phase.name}, Progress={progress:.1f}%")
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")

    def _process_data(self):
        """Traite les données reçues selon la phase actuelle"""
        if self.current_phase == CompostPhase.FILE_ANALYSIS and isinstance(self.data, list):
            # Comparer des dictionnaires par « in » sur une liste est quadratique
            # et coûteux ; le nom de fichier suffit à identifier la matière.
            for file_info in self.data:
                name = file_info.get('common_metadata', {}).get('name', '')
                if name and name not in self.file_nodes:
                    self.history['analysis'].append(file_info)
                    self._create_file_node(file_info)

        elif self.current_phase == CompostPhase.CN_CALCULATION and isinstance(self.data, list):
            # Stocker les ratios C/N
            for file_info in self.data:
                file_name = file_info.get('common_metadata', {}).get('name', '')
                cn_data = file_info.get('cn_data', {})
                if file_name and cn_data:
                    self.history['cn_ratios'][file_name] = cn_data
                    # Créer le nœud s'il n'existe pas encore. Le coordinateur
                    # n'envoie aucune donnée pendant la phase d'analyse : la
                    # branche ci-dessus ne se déclenchait donc jamais, aucun
                    # nœud n'était créé, et l'écran restait vide de bout en bout.
                    if file_name not in self.file_nodes:
                        self._create_file_node(file_info)
                    self.file_nodes[file_name]['cn_ratio'] = cn_data.get('normalized_cn_ratio', 0)
                    self.file_nodes[file_name]['file_type'] = cn_data.get('file_type', 'unknown')
        
        elif self.current_phase == CompostPhase.SILO_CREATION and isinstance(self.data, list):
            # Stocker les configurations de silos
            self.history['silos'] = self.data
            self._create_silos()
    
    def _create_file_node(self, file_info):
        """Crée un nœud visuel représentant un fichier"""
        name = file_info.get('common_metadata', {}).get('name', 'unknown')
        size = file_info.get('common_metadata', {}).get('size', 1)
        category = file_info.get('category', 'unknown')
        
        # Calculer la taille visuelle basée sur la taille du fichier (logarithmique)
        visual_size = max(5, min(30, math.log(size + 1) / math.log(1024 * 1024)))
        
        # Position aléatoire dans la zone de visualisation
        margin = 100
        x = random.randint(margin, self.width - margin)
        y = random.randint(margin, self.height - margin)
        
        # Couleur basée sur la catégorie de fichier
        color_seed = hash(category) % 1000
        r = (color_seed * 13) % 200 + 55
        g = (color_seed * 17) % 200 + 55
        b = (color_seed * 19) % 200 + 55
        
        self.file_nodes[name] = {
            'name': name,
            'size': size,
            'category': category,
            'visual_size': visual_size,
            'x': x,
            'y': y,
            'target_x': x,  # Pour les animations
            'target_y': y,
            'color': (r, g, b),
            'velocity_x': 0,
            'velocity_y': 0,
            'cn_ratio': 0,
            'file_type': 'unknown'
        }
    
    def _create_silos(self):
        """Crée des représentations visuelles des silos"""
        self.silos = []
        
        if not self.history['silos']:
            return
            
        num_silos = len(self.history['silos'])
        
        # Répartir les silos horizontalement
        silo_width = (self.width - 200) // num_silos
        
        for i, silo_info in enumerate(self.history['silos']):
            silo_id = silo_info.get('silo_id', i+1)
            file_count = silo_info.get('file_count', 0)
            total_size = silo_info.get('total_size', 0)
            avg_cn = silo_info.get('avg_normalized_cn_ratio', 0)
            
            # Position du silo
            x = 100 + i * silo_width
            y = self.height // 2
            
            # Hauteur proportionnelle au nombre de fichiers
            height = max(50, min(400, file_count * 10))
            
            self.silos.append({
                'id': silo_id,
                'x': x,
                'y': y,
                'width': silo_width - 20,
                'height': height,
                'file_count': file_count,
                'total_size': total_size,
                'avg_cn_ratio': avg_cn,
                'color': self._cn_ratio_to_color(avg_cn)
            })
            
            # Déplacer les nœuds de fichiers vers leurs silos
            # Cette logique est simplifiée, dans la réalité, vous auriez
            # besoin de savoir quels fichiers vont dans quel silo
            for node in self.file_nodes.values():
                # Assigner aléatoirement des fichiers aux silos pour la démonstration
                if random.random() < 1/num_silos:
                    node['target_x'] = x + random.randint(-silo_width//4, silo_width//4)
                    node['target_y'] = y + random.randint(-height//2, height//2)
    
    def _cn_ratio_to_color(self, cn_ratio):
        """Convertit un ratio C/N en couleur, du vert azoté au brun carboné.

        La position vient de cn_position(), centrée sur la cible et
        logarithmique de part et d'autre. Une division par 100 rendait
        identiques toutes les matières au-delà de ce seuil.
        """
        normalized = cn_position(cn_ratio)
        
        # Vert pour faible C/N (plus d'azote)
        # Brun pour C/N élevé (plus de carbone)
        if normalized < 0.5:  # Plus d'azote
            factor = normalized * 2
            r = int(100 + factor * 50)
            g = int(180 - factor * 30)
            b = int(50 + factor * 50)
        else:  # Plus de carbone
            factor = (normalized - 0.5) * 2
            r = int(150 + factor * 105)
            g = int(150 - factor * 70)
            b = int(100 - factor * 50)
            
        return (r, g, b)

    def draw(self):
        """Dessine l'interface selon la phase actuelle"""
        # Effacer l'écran avec un fond noir
        self.screen.fill((10, 10, 20))
        
        # Dessiner l'interface de base
        self._draw_base_interface()
        
        # Dessiner le contenu spécifique à la phase
        if self.current_phase == CompostPhase.IDLE:
            self._draw_idle_screen()
        elif self.current_phase == CompostPhase.FILE_ANALYSIS:
            self._draw_file_analysis()
        elif self.current_phase == CompostPhase.CN_CALCULATION:
            self._draw_cn_calculation()
        elif self.current_phase == CompostPhase.SILO_CREATION:
            self._draw_silo_creation()
        elif self.current_phase == CompostPhase.COMPOSTING:
            self._draw_composting()
        elif self.current_phase == CompostPhase.RESULT_VISUALIZATION:
            self._draw_result_visualization()
        
        # Mettre à jour l'animation
        self._update_animation()
        
        # Mettre à jour l'écran
        pygame.display.flip()

    def _draw_base_interface(self):
        """Dessine l'interface de base commune à toutes les phases"""
        # Titre de la phase
        phase_text = self.current_phase.name.replace('_', ' ')
        phase_color = PHASE_COLORS[self.current_phase]
        
        # Dessiner la barre du haut
        pygame.draw.rect(self.screen, (20, 20, 30), (0, 0, self.width, 60))
        
        # Afficher le titre de la phase
        self.title_font.render_to(self.screen, (20, 20), phase_text, phase_color)
        
        # Afficher la progression
        progress_text = f"Progress: {self.progress:.1f}%"
        text_width, _ = self.subtitle_font.get_rect(progress_text)[2:]
        self.subtitle_font.render_to(self.screen, (self.width - text_width - 20, 20), 
                                    progress_text, (200, 200, 200))
        
        # Barre de progression
        progress_bar_width = 300
        pygame.draw.rect(self.screen, (40, 40, 50), 
                        (self.width - progress_bar_width - 20, 45, progress_bar_width, 10))
        pygame.draw.rect(self.screen, phase_color, 
                        (self.width - progress_bar_width - 20, 45, 
                         int(progress_bar_width * self.progress / 100), 10))

    def _draw_idle_screen(self):
        """Dessine l'écran d'attente"""
        # Message de bienvenue
        welcome_text = "Bienvenue dans le système de compostage numérique"
        self.subtitle_font.render_to(self.screen, 
                                   (self.width//2 - 200, self.height//2 - 50), 
                                   welcome_text, (200, 200, 200))
        
        # Instructions
        instructions = "En attente du démarrage du processus..."
        self.text_font.render_to(self.screen, 
                               (self.width//2 - 150, self.height//2), 
                               instructions, (150, 150, 150))

    def _draw_file_analysis(self):
        """Dessine la visualisation de l'analyse des fichiers"""
        # Titre de section
        self.subtitle_font.render_to(self.screen, (20, 80), 
                                   "Analyse des fichiers en cours", (200, 200, 200))
        
        # Dessiner les nœuds de fichiers
        for name, node in self.file_nodes.items():
            # Dessiner le nœud (cercle)
            pygame.draw.circle(self.screen, node['color'], 
                             (int(node['x']), int(node['y'])), 
                             int(node['visual_size']))
            
            # Afficher le nom du fichier si la souris est proche
            mouse_x, mouse_y = pygame.mouse.get_pos()
            distance = math.sqrt((mouse_x - node['x'])**2 + (mouse_y - node['y'])**2)
            
            if distance < max(30, node['visual_size'] * 2):
                # Afficher le nom et la catégorie du fichier
                info_text = f"{name} ({node['category']})"
                self.text_font.render_to(self.screen, 
                                       (node['x'] - 10, node['y'] - node['visual_size'] - 20), 
                                       info_text, (255, 255, 255))

    def _draw_cn_calculation(self):
        """Dessine la visualisation du calcul C/N"""
        # Titre de section
        self.subtitle_font.render_to(self.screen, (20, 80), 
                                   "Calcul des ratios C/N", (200, 200, 200))
        
        # Dessiner les nœuds de fichiers avec leur ratio C/N
        for name, node in self.file_nodes.items():
            # Couleur basée sur le ratio C/N
            cn_color = self._cn_ratio_to_color(node['cn_ratio'])
            
            # Dessiner le nœud (cercle)
            pygame.draw.circle(self.screen, cn_color, 
                             (int(node['x']), int(node['y'])), 
                             int(node['visual_size']))
            
            # Bordure différente selon le type de fichier
            if node['file_type'] == 'brown':
                pygame.draw.circle(self.screen, (139, 69, 19), 
                                 (int(node['x']), int(node['y'])), 
                                 int(node['visual_size']), 2)
            elif node['file_type'] == 'green':
                pygame.draw.circle(self.screen, (34, 139, 34), 
                                 (int(node['x']), int(node['y'])), 
                                 int(node['visual_size']), 2)
            
            # Afficher le ratio C/N si la souris est proche
            mouse_x, mouse_y = pygame.mouse.get_pos()
            distance = math.sqrt((mouse_x - node['x'])**2 + (mouse_y - node['y'])**2)
            
            if distance < max(30, node['visual_size'] * 2):
                info_text = f"{name}: C/N = {node['cn_ratio']:.1f} ({node['file_type']})"
                self.text_font.render_to(self.screen, 
                                       (node['x'] - 10, node['y'] - node['visual_size'] - 20), 
                                       info_text, (255, 255, 255))
        
        # Légende
        self._draw_cn_legend()

    def _draw_cn_legend(self):
        """Dessine une légende pour les ratios C/N"""
        legend_x = self.width - 200
        legend_y = 80
        legend_width = 180
        legend_height = 120
        
        # Fond de la légende
        pygame.draw.rect(self.screen, (30, 30, 40), 
                       (legend_x, legend_y, legend_width, legend_height))
        
        # Titre de la légende
        self.text_font.render_to(self.screen, (legend_x + 10, legend_y + 10), 
                               "Légende C/N", (200, 200, 200))
        
        # Gradient de couleur
        gradient_width = legend_width - 20
        gradient_height = 20
        for i in range(gradient_width):
            # Interpoler sur l'échelle réelle : du vert le plus azoté au brun
            # le plus carboné, en passant par la cible au milieu
            ratio = CN_CEILING ** (i / gradient_width)
            color = self._cn_ratio_to_color(ratio)
            pygame.draw.line(self.screen, color, 
                           (legend_x + 10 + i, legend_y + 40), 
                           (legend_x + 10 + i, legend_y + 40 + gradient_height))
        
        # Étiquettes du gradient
        self.text_font.render_to(self.screen, (legend_x + 10, legend_y + 70), 
                               "0 (Azote)", (34, 139, 34))
        self.text_font.render_to(self.screen, (legend_x + gradient_width - 60, legend_y + 70), 
                               "100 (Carbone)", (139, 69, 19))
        
        # Types de fichiers
        pygame.draw.circle(self.screen, (100, 100, 100), (legend_x + 20, legend_y + 95), 8)
        pygame.draw.circle(self.screen, (139, 69, 19), (legend_x + 20, legend_y + 95), 8, 2)
        self.text_font.render_to(self.screen, (legend_x + 35, legend_y + 90), 
                               "Fichier brun (C)", (200, 200, 200))
        
        pygame.draw.circle(self.screen, (100, 100, 100), (legend_x + 20, legend_y + 115), 8)
        pygame.draw.circle(self.screen, (34, 139, 34), (legend_x + 20, legend_y + 115), 8, 2)
        self.text_font.render_to(self.screen, (legend_x + 35, legend_y + 110), 
                               "Fichier vert (N)", (200, 200, 200))

    def _draw_silo_creation(self):
        """Dessine la visualisation de la création des silos"""
        # Titre de section
        self.subtitle_font.render_to(self.screen, (20, 80), 
                                   "Création des silos de compostage", (200, 200, 200))
        
        # Dessiner les silos
        for silo in self.silos:
            # Dessiner le contour du silo
            pygame.draw.rect(self.screen, silo['color'], 
                           (silo['x'], silo['y'] - silo['height']//2, 
                            silo['width'], silo['height']), 3)
            
            # Afficher l'ID et le ratio C/N du silo
            silo_text = f"Silo {silo['id']}"
            self.text_font.render_to(self.screen, 
                                   (silo['x'] + 10, silo['y'] - silo['height']//2 + 10), 
                                   silo_text, (255, 255, 255))
            
            cn_text = f"C/N: {silo['avg_cn_ratio']:.1f}"
            self.text_font.render_to(self.screen, 
                                   (silo['x'] + 10, silo['y'] - silo['height']//2 + 30), 
                                   cn_text, (200, 200, 200))
            
            # Nombre de fichiers
            count_text = f"{silo['file_count']} fichiers"
            self.text_font.render_to(self.screen, 
                                   (silo['x'] + 10, silo['y'] - silo['height']//2 + 50), 
                                   count_text, (200, 200, 200))
        
        # Dessiner les nœuds de fichiers
        for name, node in self.file_nodes.items():
            # Couleur basée sur le ratio C/N
            cn_color = self._cn_ratio_to_color(node['cn_ratio'])
            
            # Dessiner le nœud (plus petit dans cette phase)
            pygame.draw.circle(self.screen, cn_color, 
                             (int(node['x']), int(node['y'])), 
                             int(node['visual_size'] * 0.8))
            
            # Bordure différente selon le type de fichier
            if node['file_type'] == 'brown':
                pygame.draw.circle(self.screen, (139, 69, 19), 
                                 (int(node['x']), int(node['y'])), 
                                 int(node['visual_size'] * 0.8), 1)
            elif node['file_type'] == 'green':
                pygame.draw.circle(self.screen, (34, 139, 34), 
                                 (int(node['x']), int(node['y'])), 
                                 int(node['visual_size'] * 0.8), 1)

    def _draw_composting(self):
        """Dessine la visualisation du processus de compostage"""
        # Titre de section
        self.subtitle_font.render_to(self.screen, (20, 80), 
                                   "Processus de compostage en cours", (200, 200, 200))
        
        # Centre de l'écran pour le "tourbillon" de compostage
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Dessiner le cercle de compostage
        pygame.draw.circle(self.screen, (60, 40, 20), 
                         (center_x, center_y), 100, 4)
        
        # Effet de dégradation progressive sur les nœuds de fichiers
        for name, node in self.file_nodes.items():
            # Calculer la distance au centre
            dx = node['x'] - center_x
            dy = node['y'] - center_y
            distance = math.sqrt(dx*dx + dy*dy)
            
            # Les fichiers sont attirés vers le centre pendant le compostage
            attraction = max(0.1, min(0.9, 100 / distance if distance > 0 else 0.9))
            node['target_x'] = node['x'] * (1 - attraction) + center_x * attraction
            node['target_y'] = node['y'] * (1 - attraction) + center_y * attraction
            
            # Calculer la "décomposition" - les nœuds deviennent plus petits et plus distordus
            decomposition = min(1.0, (100 - distance) / 100) * (self.progress / 100)
            size_factor = 1.0 - decomposition * 0.7
            
            # Les fichiers se transforment en particules
            if decomposition > 0.2:
                # Générer des particules
                if random.random() < decomposition * 0.1:
                    # Créer une nouvelle particule
                    angle = random.uniform(0, 2 * math.pi)
                    speed = random.uniform(0.5, 2)
                    size = random.uniform(1, 4)
                    if node['file_type'] == 'brown':
                        color = (139, 69, 19, 128)  # Brun avec transparence
                    else:
                        color = (34, 139, 34, 128)  # Vert avec transparence
                    
                    self.particles.append({
                        'x': node['x'],
                        'y': node['y'],
                        'vx': math.cos(angle) * speed,
                        'vy': math.sin(angle) * speed,
                        'size': size,
                        'color': color,
                        'life': random.uniform(0.5, 1.5)
                    })
            
            # Dessiner le nœud (déformé)
            if size_factor > 0.1:
                # Couleur basée sur le ratio C/N
                cn_color = self._cn_ratio_to_color(node['cn_ratio'])
                alpha = int(255 * (1 - decomposition))
                node_color = (cn_color[0], cn_color[1], cn_color[2], alpha)
                
                # Dessiner une forme déformée
                pygame.draw.ellipse(self.screen, node_color, 
                                  (int(node['x'] - node['visual_size'] * size_factor),
                                   int(node['y'] - node['visual_size'] * size_factor * (1 + 0.2 * math.sin(self.animation_time))),
                                   int(node['visual_size'] * 2 * size_factor),
                                   int(node['visual_size'] * 2 * size_factor * (1 + 0.3 * math.sin(self.animation_time + 1)))))
        
        # Dessiner les particules
        for particle in self.particles:
            # Couleur avec transparence
            color = particle['color']
            if len(color) == 3:
                color = (color[0], color[1], color[2], 255)
            
            # Dessiner une particule (petit cercle)
            pygame.draw.circle(self.screen, color, 
                             (int(particle['x']), int(particle['y'])), 
                             int(particle['size']))
        
        # Générer des particules aléatoires au centre du compostage
        if random.random() < 0.3:
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(2, 4)
            size = random.uniform(2, 5)
            particle_type = random.choice(['brown', 'green'])
            
            if particle_type == 'brown':
                color = (139, 69, 19, 200)  # Brun avec transparence
            else:
                color = (34, 139, 34, 200)  # Vert avec transparence
            
            self.particles.append({
                'x': center_x + random.uniform(-20, 20),
                'y': center_y + random.uniform(-20, 20),
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed,
                'size': size,
                'color': color,
                'life': random.uniform(1, 3)
            })

    def _draw_result_visualization(self):
        """Dessine la visualisation du résultat final"""
        # Titre de section
        self.subtitle_font.render_to(self.screen, (20, 80), 
                                   "Visualisation du compost numérique final", (200, 200, 200))
        
        # Message pour indiquer que la visualisation principale est dans une fenêtre séparée
        self.text_font.render_to(self.screen, (self.width//2 - 200, self.height//2 - 20), 
                               "La visualisation binaire est affichée dans une fenêtre séparée.", 
                               (200, 200, 200))
        
        self.text_font.render_to(self.screen, (self.width//2 - 180, self.height//2 + 10), 
                               "Le résultat final est disponible pour utilisation créative.", 
                               (200, 200, 200))
        
        # Afficher quelques statistiques sur le compostage
        stats_x = self.width // 2 - 150
        stats_y = self.height // 2 + 60
        
        # Nombre de fichiers compostés - calculer en comptant les fichiers dans le dossier composted
        composted_dir = os.path.join('data', 'output', 'composted')
        num_files = 0
        if os.path.exists(composted_dir):
            # Compter tous les fichiers sauf le fichier mixé final
            for file in os.listdir(composted_dir):
                if os.path.isfile(os.path.join(composted_dir, file)) and file != 'mixed_compost.bin':
                    num_files += 1
        
        self.text_font.render_to(self.screen, (stats_x, stats_y), 
                               f"Nombre de fichiers compostés: {num_files}", (200, 200, 200))
        
        # Nombre de silos utilisés
        num_silos = len(self.silos)
        self.text_font.render_to(self.screen, (stats_x, stats_y + 30), 
                               f"Nombre de silos de compostage: {num_silos}", (200, 200, 200))
        
        # Ratio C/N moyen final
        if num_silos > 0:
            avg_cn = sum(silo['avg_cn_ratio'] for silo in self.silos) / num_silos
            self.text_font.render_to(self.screen, (stats_x, stats_y + 60), 
                                   f"Ratio C/N moyen final: {avg_cn:.1f}", (200, 200, 200))
        
        # Calculer la taille totale initiale des fichiers d'entrée
        initial_size = 0
        try:
            with open(os.path.join('data', 'output', 'analysis_results.json'), 'r') as f:
                import json
                analysis_data = json.load(f)
                for file_data in analysis_data:
                    initial_size += file_data.get('common_metadata', {}).get('size', 0)
        except Exception as e:
            print(f"Erreur lors de la lecture des tailles initiales: {e}")
        
        # Afficher la taille totale initiale
        if initial_size > 0:
            size_str = f"{initial_size / 1024 / 1024:.2f} Mo" if initial_size > 1024*1024 else f"{initial_size / 1024:.2f} Ko"
            self.text_font.render_to(self.screen, (stats_x, stats_y + 90), 
                                   f"Taille initiale totale: {size_str}", (200, 200, 200))
        
        # Taille du fichier final de compost
        compost_file = os.path.join(composted_dir, 'mixed_compost.bin')
        if os.path.exists(compost_file):
            file_size = os.path.getsize(compost_file)
            size_str = f"{file_size / 1024 / 1024:.2f} Mo" if file_size > 1024*1024 else f"{file_size / 1024:.2f} Ko"
            self.text_font.render_to(self.screen, (stats_x, stats_y + 120), 
                                   f"Taille du compost final: {size_str}", (200, 200, 200))
            
            # Afficher le taux de compression
            if initial_size > 0:
                compression_rate = (1 - file_size / initial_size) * 100
                self.text_font.render_to(self.screen, (stats_x, stats_y + 150), 
                                       f"Taux de décomposition: {compression_rate:.1f}%", (200, 200, 200))

    def _update_animation(self):
        """Met à jour les animations pour la frame actuelle"""
        self.animation_time += 0.01
        
        # Mettre à jour les nœuds de fichiers
        for node in self.file_nodes.values():
            # Animation de déplacement fluide
            dx = node['target_x'] - node['x']
            dy = node['target_y'] - node['y']
            
            # Appliquer une force d'attraction vers la cible
            node['velocity_x'] = node['velocity_x'] * 0.9 + dx * 0.05
            node['velocity_y'] = node['velocity_y'] * 0.9 + dy * 0.05
            
            # Mettre à jour la position
            node['x'] += node['velocity_x']
            node['y'] += node['velocity_y']
        
        # Mettre à jour les particules
        for i in range(len(self.particles)-1, -1, -1):
            particle = self.particles[i]
            
            # Déplacer la particule
            particle['x'] += particle['vx']
            particle['y'] += particle['vy']
            
            # Réduire la durée de vie
            particle['life'] -= 0.02
            
            # Supprimer les particules mortes
            if particle['life'] <= 0:
                self.particles.pop(i)
                continue
            
            # Rebondir sur les bords
            if particle['x'] < 0 or particle['x'] > self.width:
                particle['vx'] *= -0.8
            if particle['y'] < 0 or particle['y'] > self.height:
                particle['vy'] *= -0.8
            
            # Appliquer une légère gravité
            particle['vy'] += 0.05

def start_hdmi_display(update_queue, stop_queue, log_queue=None):
    """
    Fonction principale pour démarrer l'affichage HDMI dans un processus séparé.

    Args:
        update_queue: Queue pour recevoir les mises à jour d'état
        stop_queue: Queue pour recevoir les signaux d'arrêt
        log_queue: Queue partagée pour le logging centralisé (optionnel)
    """
    from modules.logging_config import setup_worker_logging
    setup_worker_logging(log_queue)
    try:
        logger.info("Starting HDMI display process")
        
        # Initialiser l'affichage
        display = HDMIDisplay()
        
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
                    data = update_data.get('data')
                    display.update(phase, progress, data)
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
        logger.info("HDMI display process stopped")
        
    except Exception as e:
        logger.error(f"Error in HDMI display process: {str(e)}")
        pygame.quit()

if __name__ == "__main__":
    # Test de l'affichage HDMI
    # Crée une queue fictive pour simuler des mises à jour
    test_queue = multiprocessing.Queue()
    stop_queue = multiprocessing.Queue()
    
    # Démarrer l'affichage dans le processus principal
    display = HDMIDisplay()
    
    # Simuler des mises à jour de progression
    phases = list(CompostPhase)
    current_phase_index = 0
    progress = 0
    
    # Créer des données de test
    test_files = []
    for i in range(20):
        file_info = {
            'common_metadata': {
                'name': f"test_file_{i}.txt",
                'size': random.randint(1000, 1000000)
            },
            'category': random.choice(['image', 'text', 'audio', 'document', 'system']),
            'cn_data': {
                'normalized_cn_ratio': random.uniform(0, 100),
                'file_type': random.choice(['brown', 'green'])
            }
        }
        test_files.append(file_info)
    
    clock = pygame.time.Clock()
    running = True
    
    while running:
        # Gérer les événements
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
        
        # Mettre à jour la progression
        progress += 0.1
        if progress >= 100:
            progress = 0
            current_phase_index = (current_phase_index + 1) % len(phases)
        
        display.update(phases[current_phase_index], progress, test_files)
        display.draw()
        
        clock.tick(30)
    
    pygame.quit()
