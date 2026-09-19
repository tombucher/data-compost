# Guide technique — périphériques d'affichage sur Raspberry Pi 5

Documentation de référence pour le socle matériel de data-compost. Le
[README](README.md) couvre l'installation ; ce document explique le
fonctionnement et donne le code de pilotage.

## Sommaire

1. [Ce qui change sur le Pi 5](#1-ce-qui-change-sur-le-pi-5)
2. [Écran circulaire DSI](#2-écran-circulaire-dsi-waveshare-4-c)
3. [Écran e-paper SPI](#3-écran-e-paper-waveshare-29)
4. [Imprimante thermique](#4-imprimante-thermique-epson-tm-t70ii)
5. [Écran HDMI et disposition](#5-écran-hdmi-et-disposition-des-écrans)
6. [Intégration dans data-compost](#6-intégration-dans-data-compost)
7. [Commandes de diagnostic](#7-commandes-de-diagnostic)

---

## 1. Ce qui change sur le Pi 5

La plupart des tutoriels en ligne visent le Pi 4 sous Bullseye. Quatre
ruptures expliquent l'essentiel des échecs.

**Le GPIO passe par le RP1.** Le Pi 5 déporte les entrées-sorties sur une puce
dédiée. `RPi.GPIO`, qui écrivait directement dans les registres via
`/dev/mem`, ne fonctionne plus. Le remplaçant officiel est `gpiozero`, adossé
à `lgpio`, qui passe par l'interface noyau `/dev/gpiochip`. Pour du code
existant, `rpi-lgpio` réimplémente l'API de RPi.GPIO au-dessus de lgpio.

**La configuration a déménagé.** La partition de démarrage est montée sur
`/boot/firmware` depuis Bookworm. `/boot/config.txt` n'est plus lu. Un fichier
qui y traînerait donnerait l'illusion d'une configuration active.

**Le graphique est en KMS, et la session en Wayland.** Les réglages
`hdmi_group`, `hdmi_mode`, `hdmi_timings`, `hdmi_drive` et
`hdmi_force_hotplug` appartiennent à l'ancienne pile firmware et sont ignorés.
`tvservice` a disparu. `xrandr` ne voit plus que XWayland et ne configure
rien : l'outil est `wlr-randr`, et les sorties se nomment `HDMI-A-1`,
`HDMI-A-2`, `DSI-1`.

**Python est protégé.** Depuis Bookworm, `pip install` hors environnement
virtuel est refusé (PEP 668). Tout passe par un venv, ou par les paquets
`python3-*` d'apt.

---

## 2. Écran circulaire DSI Waveshare 4" (C)

Dalle ronde 720×720, connectée en DSI. Vue par le système comme un écran
ordinaire : une fois l'overlay chargé, pygame, le bureau et tout le reste s'y
affichent sans code particulier.

### Branchement

Pi éteint, nappe dans le connecteur **DSI1** (celui côté port Ethernet sur le
Pi 5), contacts métalliques vers les contacts du connecteur, loquet refermé
sans forcer. Certaines révisions demandent une alimentation complémentaire :
fil rouge sur la broche 2 ou 4 (5 V), fil noir sur la broche 6 (GND).

### Configuration

Dans `/boot/firmware/config.txt`, à la fin :

```
[all]
dtoverlay=vc4-kms-v3d
dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC
```

Sur DSI0 : `dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC,dsi0`

Le `[all]` referme toute section conditionnelle ouverte plus haut dans le
fichier. Sans lui, un bloc ajouté après un `[cm4]` serait silencieusement
ignoré sur un Pi 5 — panne difficile à diagnostiquer, l'écran reste noir et
la configuration a pourtant l'air correcte.

Le paramètre `4_0_inchC` désigne précisément la révision (C) de la dalle
4 pouces. Le wiki Waveshare est explicite : sur Bookworm, ces deux lignes
suffisent, il n'y a ni pilote à compiler ni `hdmi_timings` à ajouter.

### Vérification

```bash
wlr-randr
```

Attendu :

```
DSI-1 "Unknown Unknown"
  Physical size: ...
  Enabled: yes
  Modes:
    720x720 px, 60.000000 Hz (preferred, current)
```

### Afficher dessus depuis pygame

Sous Wayland, pygame passe par SDL. Pour cibler l'écran circulaire, le plus
simple est de placer la fenêtre sur la sortie correspondante et de la passer
en plein écran sans bordure :

```python
import os
import pygame

# Position de l'écran circulaire dans l'espace de bureau, telle que
# définie par wlr-randr --output DSI-1 --pos 0,0
os.environ.setdefault("SDL_VIDEO_WINDOW_POS", "0,0")

pygame.init()
screen = pygame.display.set_mode((720, 720), pygame.NOFRAME)
```

La dalle étant ronde, tout ce qui sort du cercle inscrit est invisible :
dessinez dans un disque de rayon 360 centré sur (360, 360).

---

## 3. Écran e-paper Waveshare 2.9"

296×128 pixels, monochrome, piloté en SPI. Rafraîchissement complet de l'ordre
de deux secondes ; l'image reste affichée sans alimentation.

### Câblage

| Broche e-paper | GPIO (BCM) | Broche physique | Rôle |
|---|---|---|---|
| VCC | 3.3 V | 1 | Alimentation |
| GND | GND | 6 | Masse |
| DIN | GPIO 10 | 19 | SPI MOSI |
| CLK | GPIO 11 | 23 | SPI SCLK |
| CS | GPIO 8 | 24 | Chip select |
| DC | GPIO 25 | 22 | Data / command |
| RST | GPIO 17 | 11 | Reset |
| BUSY | GPIO 24 | 18 | Occupation |
| PWR | GPIO 18 | 12 | Alimentation logique |

PWR n'est présent que sur certaines révisions. Le pilote Waveshare pilote
GPIO 18 dans tous les cas ; sans cette broche, l'écran fonctionne avec VCC sur
le 3.3 V.

Alimentez en **3.3 V, pas en 5 V** : les lignes SPI du Pi ne sont pas tolérantes
5 V.

### Dépendances

```bash
sudo raspi-config nonint do_spi 0
sudo apt install -y python3-pil python3-numpy python3-spidev \
                    python3-gpiozero python3-lgpio
git clone https://github.com/waveshare/e-Paper ~/e-Paper
sudo usermod -a -G spi,gpio "$USER"
```

Le fichier `epdconfig.py` du dépôt Waveshare importe `spidev` et `gpiozero`,
et ne dépend ni de RPi.GPIO ni de wiringPi. C'est ce qui rend le module
utilisable tel quel sur Pi 5 — à condition d'avoir une copie à jour du dépôt.
Une version ancienne clonée il y a plus d'un an importe encore `RPi.GPIO` et
échouera : faites `git pull`.

### Pilotage

```python
import sys
import time
from pathlib import Path

LIBDIR = Path.home() / "e-Paper/RaspberryPi_JetsonNano/python/lib"
sys.path.insert(0, str(LIBDIR))

from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd2in9_V2 as epd_driver

epd = epd_driver.EPD()
epd.init()
epd.Clear(0xFF)                       # 0xFF = blanc

# L'écran est physiquement en portrait : on dessine en paysage 296x128
image = Image.new("1", (epd.height, epd.width), 255)   # mode "1" = 1 bit
draw = ImageDraw.Draw(image)
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)

draw.text((8, 8), "PHASE 3 / SILOS", font=font, fill=0)   # 0 = noir
draw.text((8, 32), "C/N moyen : 27.8", font=font, fill=0)

epd.display(epd.getbuffer(image))
epd.sleep()                           # indispensable entre deux affichages
```

Le nom du module dépend de la révision : `epd2in9_V2`, `epd2in9_V3`,
`epd2in9`, ou une variante `b` pour les modèles trois couleurs. Les exemples
du constructeur sont dans `~/e-Paper/RaspberryPi_JetsonNano/python/examples/`.

### Précautions

- Appelez `epd.sleep()` après chaque affichage. Laisser la dalle sous tension
  en continu la dégrade durablement.
- Espacez les rafraîchissements complets d'au moins 180 secondes en usage
  prolongé, sinon l'image finit par rémanencer.
- Le rafraîchissement partiel (`epd.displayPartial`) est plus rapide mais
  laisse des traces : intercalez un rafraîchissement complet régulièrement.
- Ne réinitialisez pas l'écran à chaque mise à jour : gardez un objet `EPD`
  vivant et rappelez seulement `display()`.

---

## 4. Imprimante thermique Epson TM-T70II

Imprimante de tickets, 80 mm, ESC/POS, connectée en USB via une interface
UB-U05 ou équivalente.

### Deux approches, une seule à retenir

**CUPS** présente l'imprimante comme une imprimante système. Il s'appuie sur
le module noyau `usblp`, qui prend le contrôle exclusif du périphérique. Cela
convient pour imprimer un PDF, mal pour piloter les commandes ESC/POS.

**ESC/POS direct**, via `python-escpos` et `pyusb`, parle au périphérique en
USB brut : coupe du papier, QR codes, styles, images en mode raster. C'est ce
dont le projet a besoin.

Les deux ne cohabitent pas : tant que `usblp` est chargé, pyusb renvoie
`Resource busy` (errno 16). D'où le `blacklist usblp`. C'est le point qui
bloque le plus souvent quand on suit un tutoriel générique, parce que la
plupart installent CUPS par réflexe.

### Configuration

```bash
sudo apt install -y python3-usb usbutils
lsusb | grep 04b8          # 04b8 = Seiko Epson ; l'ID produit varie
```

Règle udev par vendeur, valable quelle que soit l'interface :

```
SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", MODE="0660", GROUP="lp", TAG+="uaccess"
```

`TAG+="uaccess"` donne aussi l'accès à l'utilisateur de la session locale, ce
qui évite de dépendre uniquement de l'appartenance au groupe.

```bash
echo 'blacklist usblp' | sudo tee /etc/modprobe.d/data-compost-usblp.conf
sudo modprobe -r usblp
sudo usermod -a -G lp,dialout "$USER"
sudo udevadm control --reload-rules && sudo udevadm trigger

python3 -m venv --system-site-packages ~/printer_env
~/printer_env/bin/pip install python-escpos pyusb
```

### Pilotage

```python
#!/home/USER/printer_env/bin/python3
import usb.core
from escpos.printer import Usb

EPSON = 0x04B8

device = usb.core.find(idVendor=EPSON)
if device is None:
    raise SystemExit("Imprimante Epson absente du bus USB")

printer = Usb(EPSON, device.idProduct)

printer.set(align="center", bold=True, double_height=True)
printer.text("DATA-COMPOST\n")
printer.set(align="left", bold=False, double_height=False)
printer.text("Silo 1 : 4 fichiers, C/N 27.8\n")
printer.image("data/output/composted/apercu.png")   # image raster
printer.qr("https://example.org/compost/42", size=6)
printer.cut()
```

Ne codez pas l'ID produit en dur : il change selon l'interface installée. La
détection par vendeur suffit tant qu'un seul périphérique Epson est branché.

Pour les accents, réglez la page de code avec `printer.charcode("CP858")`, ou
restez en ASCII — c'est plus sûr d'un modèle à l'autre.

Le shebang pointe directement sur l'interpréteur du venv : le script est
exécutable sans activation préalable, y compris depuis un service ou un
gestionnaire de fenêtres.

---

## 5. Écran HDMI et disposition des écrans

Le Pi 5 a deux sorties micro-HDMI, `HDMI-A-1` (près de l'USB-C) et
`HDMI-A-2`. Aucune configuration n'est nécessaire : l'EDID du moniteur suffit.

### wlr-randr

```bash
wlr-randr                                    # état de toutes les sorties

# Circulaire à gauche, HDMI à droite
wlr-randr --output DSI-1 --on --pos 0,0 \
          --output HDMI-A-1 --on --pos 720,0

wlr-randr --output HDMI-A-1 --mode 1920x1080@60
wlr-randr --output HDMI-A-1 --off
```

`--pos` prend des coordonnées absolues dans l'espace de bureau : il n'y a pas
d'équivalent de `--right-of`, il faut calculer l'origine. Avec le circulaire
en 0,0 et sa largeur de 720, le HDMI commence à 720,0.

La recopie d'écran n'est pas possible sous labwc.

### Au démarrage

Le compositeur détermine le mécanisme :

- **wayfire** (Bookworm initial) lit `~/.config/autostart/*.desktop` et la
  section `[autostart]` de `~/.config/wayfire.ini` ;
- **labwc** (défaut sur Pi 4 et 5 depuis fin 2024) ignore
  `~/.config/autostart` et lit `~/.config/labwc/autostart`, un script shell.

L'installeur écrit dans les deux, avec cinq secondes d'attente le temps que
les sorties soient déclarées.

```bash
# ~/.config/labwc/autostart
(sleep 5 && wlr-randr --output DSI-1 --on --pos 0,0 --output HDMI-A-1 --on --pos 720,0) &
```

Vérifier le compositeur en cours : `echo $XDG_CURRENT_DESKTOP`, ou
`pgrep -l 'labwc|wayfire'`.

---

## 6. Intégration dans data-compost

État actuel : les trois modules de `displays/` ouvrent des fenêtres pygame qui
imitent les écrans — 320×320 pour le circulaire, 296×128 en noir et blanc pour
l'e-paper, 1280×720 pour le HDMI. Utile pour développer sur un poste de
travail, à remplacer sur le Pi.

Le passage au matériel réel se répartit ainsi :

| Écran | Aujourd'hui | Sur le Pi |
|---|---|---|
| Circulaire | fenêtre pygame 320×320 | même code pygame en 720×720 plein écran sur `DSI-1` — aucune réécriture, seulement la taille et le placement |
| HDMI | fenêtre pygame 1280×720 | idem, plein écran sur `HDMI-A-1` |
| E-paper | fenêtre pygame noir et blanc | à réécrire : Pillow + `waveshare_epd`, pygame n'intervient plus |
| Imprimante | file `'printer'` que personne ne lit | processus à écrire, consommant la file et imprimant en ESC/POS |

Le coordinateur `modules/multiscreen_coordinator.py` alimente déjà une file par
périphérique, imprimante comprise. Les messages ont cette forme :

```python
{
    'phase': 3,
    'phase_name': 'SILO_CREATION',
    'progress': 100.0,
    'timestamp': 1758312345.67,
    'data': {...},          # résultats de la phase, ou None
}
```

Un pilote e-paper réel se branche donc au même endroit que le simulateur, avec
la même signature `start_epaper_display(update_queue, stop_queue, cn_results_path, silo_info_path, log_queue)`.
Deux contraintes à respecter côté e-paper : ne pas redessiner à chaque message
(la dalle met deux secondes et s'use), et appeler `sleep()` entre les
affichages.

---

## 7. Commandes de diagnostic

```bash
# Vue d'ensemble
~/scripts/check-install.sh

# Matériel et système
cat /proc/device-tree/model
uname -m                            # doit renvoyer aarch64
. /etc/os-release && echo "$PRETTY_NAME"
vcgencmd measure_temp

# Configuration de démarrage
grep -v '^#' /boot/firmware/config.txt | grep -v '^$'
ls -l /boot/config.txt              # ne doit pas exister, ou être ignoré

# Écrans
wlr-randr
echo "$XDG_SESSION_TYPE $XDG_CURRENT_DESKTOP"

# SPI et GPIO
ls -l /dev/spidev*
groups
python3 -c "import gpiozero, lgpio, spidev; print('GPIO OK')"

# Imprimante
lsusb | grep 04b8
lsmod | grep usblp                  # doit être vide
~/printer_env/bin/python -c "import escpos, usb.core; print('ESC/POS OK')"

# Application
cd ~/data-compost && venv/bin/python -c "import modules.analyze; print('pipeline OK')"
tail -f ~/data-compost/compost_process.log
```

## Références

- [Wiki Waveshare — 4inch DSI LCD (C)](https://www.waveshare.com/wiki/4inch_DSI_LCD_(C))
- [Wiki Waveshare — 2.9inch e-Paper Module](https://www.waveshare.com/wiki/2.9inch_e-Paper_Module_Manual)
- [Dépôt e-Paper Waveshare](https://github.com/waveshare/e-Paper)
- [config.txt — documentation Raspberry Pi](https://www.raspberrypi.com/documentation/computers/config_txt.html)
- [gpiozero](https://gpiozero.readthedocs.io/)
- [rpi-lgpio, remplaçant de RPi.GPIO](https://rpi-lgpio.readthedocs.io/)
- [python-escpos](https://python-escpos.readthedocs.io/)
