import os
import time
import logging
import platform
import threading
import subprocess

from modules.config import CONFIG


class USBDetector:
    """Détecteur de clés USB compatible avec macOS et Raspberry Pi."""

    def __init__(self, callback=None, polling_interval=None):
        if polling_interval is None:
            polling_interval = CONFIG.usb.polling_interval
        """
        Initialise le détecteur USB.
        
        Args:
            callback: Fonction à appeler quand une nouvelle clé USB est détectée.
                      La fonction recevra le chemin du point de montage en argument.
            polling_interval: Intervalle en secondes entre chaque vérification.
        """
        self.callback = callback
        self.polling_interval = polling_interval
        self.known_devices = set()
        self.running = False
        self.system = platform.system()
        self.thread = None
        
    def start(self):
        """Démarre la détection en arrière-plan."""
        if self.thread and self.thread.is_alive():
            return False
        
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop)
        self.thread.daemon = True
        self.thread.start()
        logging.info("Détecteur USB démarré")
        return True
        
    def stop(self):
        """Arrête la détection."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=self.polling_interval*2)
        logging.info("Détecteur USB arrêté")
        
    def _monitor_loop(self):
        """Boucle principale de surveillance."""
        # Initialiser l'ensemble des périphériques connus
        self.known_devices = self._get_mounted_usb_devices()
        logging.info(f"Périphériques initialement connus: {self.known_devices}")
        
        while self.running:
            try:
                # Obtenir la liste actuelle des périphériques
                current_devices = self._get_mounted_usb_devices()
                
                # Trouver les nouveaux périphériques
                new_devices = current_devices - self.known_devices
                
                # Trouver les périphériques débranchés
                removed_devices = self.known_devices - current_devices
                
                # N'afficher des logs que s'il y a des changements
                if new_devices:
                    logging.info(f"Nouveaux périphériques détectés: {new_devices}")
                
                if removed_devices:
                    logging.info(f"Périphériques retirés: {removed_devices}")
                
                # Mettre à jour la liste des périphériques connus
                self.known_devices = current_devices
                
                # Appeler le callback pour chaque nouveau périphérique
                for device_path in new_devices:
                    logging.info(f"Nouvelle clé USB détectée: {device_path}")
                    if self.callback:
                        try:
                            self.callback(device_path)
                        except Exception as callback_error:
                            logging.error(f"Erreur dans le callback: {str(callback_error)}")
                
                # Attendre avant la prochaine vérification
                time.sleep(self.polling_interval)
                
            except Exception as e:
                logging.error(f"Erreur lors de la détection USB: {str(e)}")
                time.sleep(self.polling_interval)
    
    def _get_mounted_usb_devices(self):
        """
        Détecte les périphériques USB montés selon le système d'exploitation.
        
        Returns:
            Un ensemble de chemins de points de montage.
        """
        if self.system == "Darwin":  # macOS
            return self._get_macos_usb_devices()
        elif self.system == "Linux":  # Raspberry Pi
            return self._get_linux_usb_devices()
        else:
            logging.warning(f"Système d'exploitation non pris en charge: {self.system}")
            return set()
    
    def _get_macos_usb_devices(self):
        """Détecte les périphériques USB sur macOS."""
        devices = set()

        # Méthode 1: scan /Volumes
        try:
            if os.path.exists("/Volumes"):
                for volume in os.listdir("/Volumes"):
                    try:
                        volume_path = os.path.join("/Volumes", volume)
                        if volume not in ["Macintosh HD", "System", "Data"] and os.path.ismount(volume_path):
                            devices.add(volume_path)
                    except (OSError, PermissionError) as e:
                        logging.debug(f"Ignoré {volume}: {e}")
        except (OSError, PermissionError) as e:
            logging.warning(f"Impossible de lister /Volumes: {e}")

        # Méthode 2: df -h
        try:
            df_result = subprocess.run(
                ["df", "-h"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            for line in df_result.stdout.splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 9:
                    device = parts[0]
                    mount_point = parts[8]
                    if "/dev/disk" in device and mount_point.startswith("/Volumes/") and "Macintosh HD" not in mount_point:
                        devices.add(mount_point)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logging.warning(f"df -h indisponible: {e}")

        return devices

    def _get_linux_usb_devices(self):
        """Détecte les périphériques USB sur Linux (Raspberry Pi)."""
        devices = set()

        # Méthode 1: scan /media et /mnt
        for base_path in ["/media", "/mnt"]:
            if not os.path.exists(base_path):
                continue
            try:
                for username in os.listdir(base_path):
                    try:
                        user_path = os.path.join(base_path, username)
                        if not os.path.isdir(user_path):
                            continue
                        for device in os.listdir(user_path):
                            device_path = os.path.join(user_path, device)
                            if os.path.isdir(device_path):
                                devices.add(device_path)
                    except (OSError, PermissionError) as e:
                        logging.debug(f"Ignoré {username} dans {base_path}: {e}")
            except (OSError, PermissionError) as e:
                logging.warning(f"Impossible de lister {base_path}: {e}")

        # Méthode 2: lsblk
        try:
            result = subprocess.run(
                ["lsblk", "-o", "NAME,MOUNTPOINT", "-n", "-l"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5
            )
            for line in result.stdout.splitlines():
                parts = line.strip().split()
                if len(parts) >= 2 and parts[0].startswith("sd") and parts[1] not in [None, ""]:
                    devices.add(parts[1])
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError) as e:
            logging.debug(f"lsblk indisponible: {e}")

        return devices