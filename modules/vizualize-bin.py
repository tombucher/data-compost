import pygame
import math
import random
import os
import sys
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple
import pygame.sndarray

class BinarySonifier:
    def __init__(self, sample_rate=44100):
        self.sample_rate = sample_rate
        self.base_freq = 60  # Fréquence de base en Hz
        pygame.mixer.init(frequency=sample_rate, size=-16, channels=2)

    def create_ambient_sound(self, data: bytes, duration: float = 5.0) -> np.ndarray:
        """Crée une nappe sonore stéréo à partir des données binaires"""
        num_samples = int(self.sample_rate * duration)
        audio_data = np.zeros((num_samples, 2))
        
        # Créer plusieurs couches harmoniques
        for i in range(0, min(len(data), 8)):
            byte_value = data[i]
            # Fréquence basée sur la valeur du byte
            freq = self.base_freq * (1 + byte_value / 127)
            # Temps
            t = np.linspace(0, duration, num_samples)
            # Générer l'onde avec amplitude réduite pour les hautes fréquences
            amplitude = 0.1 / ((i + 1) * 2)  # Réduire davantage l'amplitude des harmoniques supérieures
            wave = np.sin(2 * np.pi * freq * t) * amplitude
            
            # Créer un effet stéréo en variant légèrement entre gauche et droite
            pan = np.sin(2 * np.pi * 0.1 * t + i)  # Mouvement lent dans le champ stéréo
            pan_amount = 0.2  # Réduire légèrement l'effet stéréo
            left = wave * (1 + pan * pan_amount)
            right = wave * (1 - pan * pan_amount)
            
            # Ajouter aux canaux gauche et droit
            audio_data[:, 0] += left
            audio_data[:, 1] += right

        # Appliquer une enveloppe ADSR
        attack = int(0.1 * self.sample_rate)
        decay = int(0.2 * self.sample_rate)
        release = int(0.2 * self.sample_rate)
        
        # Créer l'enveloppe
        envelope = np.ones(num_samples)
        envelope[:attack] = np.linspace(0, 1, attack)
        envelope[attack:attack+decay] = np.linspace(1, 0.8, decay)
        envelope[-release:] = np.linspace(0.8, 0, release)
        
        # Appliquer l'enveloppe aux deux canaux
        audio_data *= envelope[:, np.newaxis]
        
        # Réduire légèrement l'amplitude globale avant la normalisation
        audio_data *= 0.8
        
        # Normaliser et convertir en int16
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val
        audio_data = np.int16(audio_data * 32767)
        
        return audio_data

    def update_sound(self, data: bytes, offset: int) -> None:
        """Crée et joue un nouveau segment sonore"""
        segment_size = min(1024, len(data) - offset)
        segment_data = data[offset:offset + segment_size]
        if segment_size > 0:
            try:
                audio_data = self.create_ambient_sound(segment_data)
                sound = pygame.sndarray.make_sound(audio_data)
                # Faire un fade out du son précédent et jouer le nouveau
                pygame.mixer.fadeout(100)
                sound.play(fade_ms=100)
            except Exception as e:
                print(f"Erreur lors de la création du son: {e}")


class BinaryVisualizer:
    def __init__(self, width: int, height: int):
        pygame.init()
        
        # Fenêtre principale pour la visualisation
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        self.sonifier = BinarySonifier()
        
        # Fenêtre secondaire pour les données brutes
        self.data_width = 400
        self.data_height = height
        self.data_screen = pygame.display.set_mode(
            (width + self.data_width, height)
        )
        self.viz_surface = pygame.Surface((width, height))
        self.data_surface = pygame.Surface((self.data_width, height))
        
        # Configuration
        self.background_color = (0, 0, 0)
        self.text_color = (255, 255, 255)
        self.lines_per_frame = 1000
        self.frame_duration = 5  # 5 secondes en millisecondes
        self.patterns: List[Dict] = []
        
        # Configuration du texte
        self.font = pygame.font.SysFont('courier', 10)
        self.data_font = pygame.font.SysFont('courier', 10)

    def create_frame_patterns(self, data: bytes, offset: int) -> List[Dict]:
        """Crée des motifs radiaux partant du centre"""
        patterns = []
        segment = data[offset:offset + self.lines_per_frame]
        
        # Définir le centre de l'écran
        center_x = self.width // 2
        center_y = self.height // 2
        
        # Calculer le rayon maximum possible
        max_radius = min(self.width, self.height) * 0.45
        
        for i, byte in enumerate(segment):
            # Calculer l'angle basé sur la position dans le segment
            angle = (i * 13) % 360
            
            # La valeur du byte influence la longueur de la ligne
            length = (math.log(byte + 1) / math.log(256)) * max_radius
            
            # Calculer le point de départ légèrement décalé du centre
            start_radius = max_radius * 0.1
            start_x = center_x + math.cos(math.radians(angle)) * start_radius
            start_y = center_y + math.sin(math.radians(angle)) * start_radius
            
            # Calculer le point d'arrivée
            end_radius = start_radius + length
            end_x = center_x + math.cos(math.radians(angle)) * end_radius
            end_y = center_y + math.sin(math.radians(angle)) * end_radius
            
            # L'épaisseur dépend de la valeur du byte
            thickness = max(1, byte % 3)
            
            # Créer la ligne
            patterns.append({
                'type': 'line',
                'start_x': start_x,
                'start_y': start_y,
                'end_x': end_x,
                'end_y': end_y,
                'thickness': thickness,
                'original_byte': byte,
                'index': offset + i
            })
            
            # Ajouter le caractère ASCII si c'est un caractère imprimable
            if 32 <= byte <= 126:
                text_radius = end_radius - 10
                text_x = center_x + math.cos(math.radians(angle)) * text_radius
                text_y = center_y + math.sin(math.radians(angle)) * text_radius
                
                patterns.append({
                    'type': 'text',
                    'char': chr(byte),
                    'x': text_x,
                    'y': text_y,
                    'angle': angle,
                    'original_byte': byte,
                    'index': offset + i
                })
        
        return patterns

    def draw_frame(self, patterns: List[Dict]) -> None:
        """Dessine un frame avec les motifs radiaux"""
        self.viz_surface.fill(self.background_color)
        
        # Trier les patterns pour dessiner d'abord les lignes, puis le texte
        lines = [p for p in patterns if p['type'] == 'line']
        texts = [p for p in patterns if p['type'] == 'text']
        
        # Dessiner les lignes
        for pattern in lines:
            pygame.draw.line(
                self.viz_surface,
                (255, 255, 255),
                (int(pattern['start_x']), int(pattern['start_y'])),
                (int(pattern['end_x']), int(pattern['end_y'])),
                pattern['thickness']
            )
        
        # Dessiner le texte
        for pattern in texts:
            text_surface = self.font.render(pattern['char'], True, (255, 255, 255))
            text_rect = text_surface.get_rect()
            text_rect.center = (pattern['x'], pattern['y'])
            self.viz_surface.blit(text_surface, text_rect)

    def draw_data_view(self, data: bytes, offset: int) -> None:
        """Dessine la vue des données brutes"""
        self.data_surface.fill(self.background_color)
        
        y_pos = 0
        line_height = 12
        bytes_per_line = 16
        
        for i in range(0, min(self.lines_per_frame, len(data) - offset), bytes_per_line):
            # Préparer la ligne de données
            hex_values = []
            ascii_values = []
            
            for j in range(bytes_per_line):
                if offset + i + j < len(data):
                    byte = data[offset + i + j]
                    hex_values.append(f"{byte:02X}")
                    ascii_values.append(chr(byte) if 32 <= byte <= 126 else '.')
                else:
                    hex_values.append("  ")
                    ascii_values.append(" ")
            
            # Formater et afficher la ligne
            offset_text = f"{offset + i:08X}"
            hex_text = " ".join(hex_values)
            ascii_text = "".join(ascii_values)
            
            text_surface = self.data_font.render(offset_text, True, (80, 80, 80))
            self.data_surface.blit(text_surface, (10, y_pos))
            
            text_surface = self.data_font.render(hex_text, True, (180, 180, 180))
            self.data_surface.blit(text_surface, (100, y_pos))
            
            text_surface = self.data_font.render(ascii_text, True, (255, 255, 255))
            self.data_surface.blit(text_surface, (350, y_pos))
            
            y_pos += line_height

    def run(self, file_path: str) -> None:
        """Exécute la visualisation avec le son"""
        try:
            with open(file_path, 'rb') as f:
                binary_data = f.read()
            
            data_offset = 0
            frame_start_time = pygame.time.get_ticks()
            current_patterns = self.create_frame_patterns(binary_data, data_offset)
            
            # Créer et jouer le premier son
            self.sonifier.update_sound(binary_data, data_offset)
            
            clock = pygame.time.Clock()
            running = True
            
            while running:
                current_time = pygame.time.get_ticks()
                
                # Vérifier s'il faut passer au frame suivant
                if current_time - frame_start_time >= self.frame_duration:
                    data_offset = (data_offset + self.lines_per_frame) % len(binary_data)
                    current_patterns = self.create_frame_patterns(binary_data, data_offset)
                    
                    # Mettre à jour le son avec les nouvelles données
                    self.sonifier.update_sound(binary_data, data_offset)
                    
                    frame_start_time = current_time
                
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_s:
                            self.save_screenshot()
                        elif event.key == pygame.K_m:  # Ajouter un contrôle pour couper le son
                            if pygame.mixer.get_busy():
                                pygame.mixer.stop()
                            else:
                                self.sonifier.update_sound(binary_data, data_offset)
                
                # Dessiner le frame actuel
                self.draw_frame(current_patterns)
                self.draw_data_view(binary_data, data_offset)
                
                # Mettre à jour l'affichage
                self.data_screen.fill(self.background_color)
                self.data_screen.blit(self.viz_surface, (0, 0))
                self.data_screen.blit(self.data_surface, (self.width, 0))
                
                pygame.display.flip()
                clock.tick(60)
                
        finally:
            pygame.quit()

    def save_screenshot(self) -> None:
        """Sauvegarde une capture d'écran"""
        if not os.path.exists("screenshots"):
            os.makedirs("screenshots")
        filename = f"screenshots/binary_vis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        pygame.image.save(self.data_screen, filename)
        print(f"Screenshot saved: {filename}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python visualize-bin.py <path_to_binary_file>")
        sys.exit(1)
        
    try:
        file_path = sys.argv[1]
        visualizer = BinaryVisualizer(1024, 768)
        print(f"Starting visualization of {file_path}")
        print("Controls:")
        print("- S: Save screenshot")
        print("- Close window to exit")
        visualizer.run(file_path)
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)