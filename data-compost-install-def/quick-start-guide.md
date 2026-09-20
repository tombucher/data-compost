# Démarrage rapide — data-compost sur Raspberry Pi 5

Version condensée. Pour le détail, voir [README.md](README.md) et
[rpi5-display-guide.md](rpi5-display-guide.md).

## Matériel

- Raspberry Pi 5 + alimentation USB-C 5 V / 5 A officielle
- Écran circulaire Waveshare 4" (C), 720×720, DSI
- Écran e-paper Waveshare 2.9", SPI
- Imprimante thermique Epson TM-T70II, USB
- Écran HDMI standard (micro-HDMI côté Pi)

## 1. Système

Raspberry Pi OS **64 bits**, Bookworm ou Trixie, version complète avec bureau.
Configurez l'utilisateur, le Wi-Fi et SSH depuis Raspberry Pi Imager.

## 2. Installation

Copiez le dépôt data-compost sur le Pi, par exemple en `~/data-compost`.

> Attention : le dépôt <https://github.com/tombucher/data-compost> contient
> encore l'architecture de 2024 (`src/`, `front/`, `notebook/`), pas la version
> actuelle du projet. Transférez le dossier de travail directement, par `rsync`
> ou par clé USB, tant que le dépôt n'a pas été mis à jour.

```bash
rsync -av --exclude venv --exclude data/output \
      ~/Documents/data-compost/ tom@raspberrypi.local:~/data-compost/

# Puis sur le Pi :
cd ~/data-compost/data-compost-install-def
chmod +x install-script.sh check-install.sh
sudo ./install-script.sh
```

Puis redémarrer : `sudo reboot`

## 3. Vérification

```bash
~/scripts/check-install.sh
```

Tout doit être au vert. Sinon, chaque échec affiche la commande à lancer.

## 4. Tests matériels

```bash
~/scripts/test_epaper.py            # écran e-paper
~/scripts/test_printer.py           # imprimante thermique
wlr-randr                           # écrans détectés
~/scripts/raspi-display-manager.sh  # menu général
```

## 5. Lancer data-compost

```bash
cd ~/data-compost
source venv/bin/activate
python main.py --input data/test
python main.py --usb                # source = clé USB branchée à chaud
```

---

## Installation manuelle, l'essentiel

### Écran circulaire DSI

```bash
sudo nano /boot/firmware/config.txt
```

Ajouter à la fin :

```
[all]
dtoverlay=vc4-kms-v3d
dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC
```

Pas de `hdmi_timings` : sans effet sur Pi 5 avec le pilote KMS.

### Écran e-paper SPI

```bash
sudo raspi-config nonint do_spi 0
sudo apt install -y git python3-pil python3-numpy python3-spidev \
                    python3-gpiozero python3-lgpio
git clone https://github.com/waveshare/e-Paper ~/e-Paper
sudo usermod -a -G spi,gpio "$USER"
sudo reboot
```

`python3-rpi.gpio` est à éviter : RPi.GPIO ne fonctionne pas sur Pi 5.

### Imprimante thermique

```bash
sudo apt install -y python3-usb usbutils
lsusb | grep 04b8                                  # relever l'ID

echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", MODE="0660", GROUP="lp", TAG+="uaccess"' \
  | sudo tee /etc/udev/rules.d/99-epson-thermal.rules
echo 'blacklist usblp' | sudo tee /etc/modprobe.d/data-compost-usblp.conf
sudo modprobe -r usblp

sudo usermod -a -G lp,dialout "$USER"
sudo udevadm control --reload-rules && sudo udevadm trigger

python3 -m venv --system-site-packages ~/printer_env
~/printer_env/bin/pip install python-escpos pyusb
```

`usblp` doit rester déchargé, sinon pyusb échoue avec `Resource busy`.

### Disposition des écrans

Sous Wayland, `xrandr` ne configure rien. Utilisez `wlr-randr` :

```bash
sudo apt install -y wlr-randr
wlr-randr
wlr-randr --output DSI-1 --on --pos 0,0 --output HDMI-A-1 --on --pos 720,0
```

## Dépannage express

| Symptôme | Vérifier |
|---|---|
| Écran circulaire noir | `grep dsi /boot/firmware/config.txt` — et pas `/boot/config.txt` |
| `DSI-1` absent | Bloc tombé dans une section `[cm4]` ; ajouter `[all]` avant |
| E-paper muet | `ls /dev/spidev*` puis `groups \| grep spi` |
| `No module named 'RPi'` | `cd ~/e-Paper && git pull` (les versions récentes utilisent gpiozero) |
| Imprimante `Resource busy` | `lsmod \| grep usblp` doit être vide |
| Imprimante `Access denied` | `groups \| grep lp`, puis rouvrir la session |
| `externally-managed-environment` | Passer par `venv/bin/pip`, jamais pip système |
| Tout le reste | `~/scripts/check-install.sh` |
