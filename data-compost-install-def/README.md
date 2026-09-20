# Installation de data-compost sur Raspberry Pi 5

Configuration du Raspberry Pi 5 et de ses périphériques pour faire tourner
l'installation data-compost sur du matériel réel, sans simulation d'écrans.

- Écran circulaire Waveshare 4 pouces (C), 720×720, interface DSI
- Écran e-paper Waveshare 2.9 pouces, interface SPI/GPIO
- Imprimante thermique Epson TM-T70II, USB en ESC/POS direct
- Écran HDMI standard

L'application pilote ces périphériques directement : chaque sortie teste
son matériel au démarrage et retombe sur une simulation à l'écran s'il est
absent. Le même code tourne donc sur le poste de développement et sur le Pi.
Pensez à passer `fullscreen = true` dans la section `[hardware]` de
`config.toml` une fois sur le Raspberry Pi.

## Table des matières

- [Prérequis](#prérequis)
- [Installation automatisée](#installation-automatisée)
- [Vérification](#vérification)
- [Configuration manuelle](#configuration-manuelle)
  - [Écran circulaire DSI](#écran-circulaire-waveshare-4-pouces-dsi)
  - [Écran e-paper](#écran-e-paper-waveshare-29-pouces)
  - [Imprimante thermique](#imprimante-thermique-epson)
  - [Disposition des écrans](#disposition-des-écrans)
- [Utilisation](#utilisation)
- [Dépannage](#dépannage)
- [Points spécifiques au Pi 5](#points-spécifiques-au-pi-5)

## Prérequis

- Raspberry Pi 5, Raspberry Pi OS **64 bits**, Bookworm ou Trixie
- Session graphique Wayland (par défaut depuis Bookworm)
- Accès sudo et connexion Internet
- Les périphériques physiques correspondants

Ce dossier doit se trouver à la racine du dépôt data-compost : le script
installe aussi l'application, et il localise `main.py` dans le dossier parent.

```
data-compost/
├── main.py
├── modules/
├── displays/
└── data-compost-install-def/     ← ce dossier
```

## Installation automatisée

```bash
cd ~/data-compost/data-compost-install-def
chmod +x install-script.sh check-install.sh
sudo ./install-script.sh
```

Le script :

1. installe les paquets système (GPIO, SPI, OpenCV, pygame, tesseract, ffmpeg) ;
2. ajoute un bloc délimité à `/boot/firmware/config.txt` pour l'écran DSI et le SPI ;
3. ajoute l'utilisateur aux groupes `spi`, `gpio`, `lp`, `dialout`, `video`, `render` ;
4. clone le pilote e-paper Waveshare dans `~/e-Paper` ;
5. configure l'imprimante en ESC/POS direct (règle udev, `~/printer_env`) ;
6. crée le venv de l'application avec `--system-site-packages` et installe
   [`requirements-rpi.txt`](requirements-rpi.txt) ;
7. installe les scripts de test et le gestionnaire dans `~/scripts/` ;
8. configure la disposition des écrans au démarrage via `wlr-randr`.

Options :

| Option | Effet |
|---|---|
| `--skip-upgrade` | Ne pas lancer `apt upgrade` |
| `--skip-app` | Ne configurer que les périphériques |
| `--skip-printer` | Ignorer l'imprimante |
| `--skip-epaper` | Ignorer l'écran e-paper |
| `--dsi0` | Écran circulaire sur le port DSI0 (par défaut DSI1) |
| `--with-cups` | Installer CUPS en plus de l'accès ESC/POS |
| `-y`, `--yes` | Ne poser aucune question |

Le script est **idempotent** : on peut le relancer sans dupliquer quoi que ce
soit. Il n'écrase jamais `config.txt`, il n'y insère qu'un bloc entre deux
marqueurs, et il en fait une sauvegarde horodatée à chaque exécution.

Redémarrez ensuite : les modifications de `config.txt` et de groupes ne
prennent effet qu'au redémarrage.

## Vérification

Après le redémarrage, en utilisateur normal (pas avec sudo) :

```bash
~/scripts/check-install.sh
```

Le diagnostic contrôle une quarantaine de points — fichier `config.txt` lu par
le système, overlay DSI, sortie 720×720 détectée, SPI, groupes, `gpiozero` et
`lgpio`, pilote Waveshare importable, module `usblp` écarté, `python-escpos`,
venv de l'application, corpus NLTK — et sort en erreur si l'un d'eux échoue.

## Configuration manuelle

À faire seulement si vous n'utilisez pas le script.

### Écran circulaire Waveshare 4 pouces (DSI)

Branchement : câble ruban sur le connecteur **DSI1** (Pi éteint), contacts
métalliques face aux contacts du connecteur. Certains modèles demandent une
alimentation 5 V complémentaire sur les pins GPIO 2 (5 V) et 6 (GND).

Configuration — le fichier est `/boot/firmware/config.txt`, **pas**
`/boot/config.txt`, qui n'est plus lu depuis Bookworm :

```bash
sudo nano /boot/firmware/config.txt
```

À la fin du fichier :

```
[all]
dtoverlay=vc4-kms-v3d
dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC
```

Sur le port DSI0, ajoutez `,dsi0` à la fin de la seconde ligne.

Le `[all]` garantit que les lignes ne tombent pas dans une section
conditionnelle (`[cm4]`, `[pi4]`…) présente plus haut, où elles seraient
ignorées.

> Ne mettez **pas** de `hdmi_timings` : ce réglage relève de l'ancien pilote
> firmware et n'a aucun effet avec `vc4-kms-v3d` sur Pi 5. Même chose pour
> `hdmi_force_hotplug`, `hdmi_drive` et `arm_64bit`, ignoré sur Pi 5 qui ne
> démarre qu'en 64 bits.

Redémarrez, puis vérifiez avec `wlr-randr` : une sortie `DSI-1` en 720×720
doit apparaître. La commande `tvservice` n'existe plus sur Pi 5.

### Écran e-paper Waveshare 2.9 pouces

Branchement sur le connecteur GPIO :

| Broche e-paper | GPIO (BCM) | Broche physique |
|---|---|---|
| VCC | 3.3 V | 1 |
| GND | GND | 6 |
| DIN (MOSI) | GPIO 10 | 19 |
| CLK (SCK) | GPIO 11 | 23 |
| CS | GPIO 8 | 24 |
| DC | GPIO 25 | 22 |
| RST | GPIO 17 | 11 |
| BUSY | GPIO 24 | 18 |
| PWR | GPIO 18 | 12 |

La broche PWR n'existe que sur certaines révisions du module. Le pilote
Waveshare pilote GPIO 18 dans tous les cas ; si votre module n'a pas cette
broche, l'écran fonctionne quand même avec VCC câblé au 3.3 V.

Activation du SPI et dépendances :

```bash
sudo raspi-config nonint do_spi 0
sudo apt update
sudo apt install -y git python3-pil python3-numpy python3-spidev \
                    python3-gpiozero python3-lgpio
git clone https://github.com/waveshare/e-Paper ~/e-Paper
```

> **N'installez pas `python3-rpi.gpio`.** RPi.GPIO ne fonctionne pas sur
> Raspberry Pi 5 : le GPIO passe par le contrôleur RP1 et la bibliothèque
> accède directement à `/dev/mem`. Le pilote e-paper de Waveshare utilise
> `gpiozero`, qui s'appuie sur `lgpio` et fonctionne correctement sur Pi 5.
> Si RPi.GPIO est déjà là (il est préinstallé), laissez-le, il ne gêne pas.

Test :

```bash
~/scripts/test_epaper.py
```

Le script essaie successivement `epd2in9_V2`, `epd2in9_V3`, `epd2in9`,
`epd2in9b_V4` et `epd2in9b_V3` pour s'adapter à la révision exacte du module.

### Imprimante thermique Epson

Le projet pilote l'imprimante en **ESC/POS direct** via `python-escpos` et
`pyusb`. CUPS n'est pas nécessaire et pose plus de problèmes qu'il n'en
résout : le module noyau `usblp`, dont CUPS a besoin, s'approprie le
périphérique et fait échouer pyusb avec un `Resource busy`. C'est la cause
la plus courante des échecs de branchement.

```bash
sudo apt install -y python3-usb usbutils

# Identifier l'imprimante — l'ID produit varie selon l'interface UB-*
lsusb | grep 04b8
```

Règle udev, par vendeur pour rester valable si le produit change :

```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", MODE="0660", GROUP="lp", TAG+="uaccess"' \
  | sudo tee /etc/udev/rules.d/99-epson-thermal.rules
```

Écarter `usblp` :

```bash
echo 'blacklist usblp' | sudo tee /etc/modprobe.d/data-compost-usblp.conf
sudo modprobe -r usblp
```

Appliquer et créer l'environnement Python :

```bash
sudo usermod -a -G lp,dialout "$USER"
sudo udevadm control --reload-rules && sudo udevadm trigger

python3 -m venv --system-site-packages ~/printer_env
~/printer_env/bin/pip install python-escpos pyusb
```

Le venv est nécessaire : depuis Bookworm, `pip install` hors environnement
virtuel est refusé (PEP 668, « externally-managed-environment »).

Test :

```bash
~/scripts/test_printer.py
```

Le shebang du script pointe directement sur `~/printer_env/bin/python3` : pas
besoin d'activer quoi que ce soit, et il détecte l'ID produit tout seul.

### Disposition des écrans

Raspberry Pi OS utilise Wayland depuis Bookworm. **`xrandr` ne configure plus
rien** : il ne voit que la couche de compatibilité XWayland. L'outil est
`wlr-randr`, et les noms de sorties changent — `HDMI-A-1` et non `HDMI-1`.

```bash
sudo apt install -y wlr-randr
wlr-randr                                        # lister les sorties

wlr-randr --output DSI-1 --on --pos 0,0 \
          --output HDMI-A-1 --on --pos 720,0     # HDMI à droite du circulaire
```

Pour appliquer au démarrage, le script écrit
`~/.config/autostart/data-compost-displays.desktop` et, si le compositeur est
labwc, une ligne dans `~/.config/labwc/autostart` — labwc ne lit pas
`~/.config/autostart`.

La recopie d'écran (mode miroir) n'est pas possible sous labwc.

## Utilisation

```bash
~/scripts/raspi-display-manager.sh
```

Le gestionnaire permet de tester l'e-paper et l'imprimante, de changer la
disposition des écrans, d'afficher les informations système et de lancer le
diagnostic complet.

Pour lancer le pipeline data-compost lui-même, depuis la racine du dépôt :

```bash
source venv/bin/activate
python main.py --input data/test
python main.py --usb              # attendre une clé USB et l'utiliser comme source
```

## Dépannage

### Écran circulaire DSI

| Problème | Cause probable et solution |
|---|---|
| Écran noir | Nappe DSI mal enfichée, ou alimentation complémentaire absente. Vérifiez que la ligne `dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC` est bien dans `/boot/firmware/config.txt` et pas dans `/boot/config.txt`. |
| `DSI-1` absent de `wlr-randr` | Le bloc de configuration est tombé dans une section `[cm4]`/`[pi4]`. Ajoutez `[all]` avant. |
| Affichage déformé | Retirez tout `hdmi_timings` : sans effet avec KMS, mais source de confusion. |
| L'écran marche, pas le HDMI | Vérifiez `wlr-randr` ; le HDMI apparaît en `HDMI-A-1` ou `HDMI-A-2`. |

### Écran e-paper

| Problème | Cause probable et solution |
|---|---|
| `No module named 'RPi'` | Le pilote cloné est une vieille révision. Faites `git pull` dans `~/e-Paper` : la version actuelle utilise `gpiozero`. |
| `Permission denied` sur GPIO ou SPI | L'utilisateur n'est pas dans `spi`/`gpio`, ou la session n'a pas été rouverte depuis. |
| Pas de `/dev/spidev*` | SPI non activé : `sudo raspi-config nonint do_spi 0` puis redémarrage. |
| `ImportError: epd2in9…` | Révision d'écran différente. Regardez `~/e-Paper/RaspberryPi_JetsonNano/python/examples/`. |
| Affichage corrompu | `epd.init()` puis `epd.Clear(0xFF)`. Évitez les rafraîchissements partiels répétés. |

### Imprimante thermique

| Problème | Cause probable et solution |
|---|---|
| `Resource busy` / `Errno 16` | Le module `usblp` tient le périphérique. Vérifiez `lsmod \| grep usblp` — la sortie doit être vide. |
| `Access denied` / `Errno 13` | Règle udev absente, ou utilisateur hors du groupe `lp`. Rouvrez la session après `usermod`. |
| Imprimante non détectée | `lsusb \| grep 04b8`. Vérifiez l'alimentation et le câble. |
| ID produit différent de `0202` | Normal selon l'interface UB-*. Les scripts détectent l'ID automatiquement. |
| Caractères illisibles | Accents non supportés par la page de code par défaut. Utilisez du texte sans accents, ou réglez `printer.charcode()`. |

### Application

| Problème | Cause probable et solution |
|---|---|
| `externally-managed-environment` | Vous utilisez pip hors venv. Passez par `venv/bin/pip`. |
| `ModuleNotFoundError: cv2` dans le venv | Le venv a été créé sans `--system-site-packages`. Supprimez-le et relancez l'installeur. |
| `TesseractNotFoundError` | `sudo apt install tesseract-ocr`. |
| Analyse audio dégradée | `librosa` n'est pas installé — c'est volontaire, il tire numba et llvmlite, longs à construire sur ARM. `pip install librosa` si vous en avez besoin. |

## Points spécifiques au Pi 5

Résumé des différences qui font échouer les tutoriels écrits pour des Pi
antérieurs :

| Sujet | Pi 4 et avant | Pi 5 / Bookworm+ |
|---|---|---|
| Fichier de configuration | `/boot/config.txt` | `/boot/firmware/config.txt` |
| GPIO en Python | `RPi.GPIO` | `gpiozero` + `lgpio`, ou `rpi-lgpio` |
| Serveur graphique | X11 | Wayland (wayfire puis labwc) |
| Disposition des écrans | `xrandr`, sortie `HDMI-1` | `wlr-randr`, sortie `HDMI-A-1` |
| État de l'affichage | `tvservice -s` | `wlr-randr` (tvservice supprimé) |
| Réglages HDMI | `hdmi_group`, `hdmi_mode`, `hdmi_timings` | Ignorés avec KMS |
| `pip install` système | autorisé | refusé (PEP 668), venv obligatoire |
| Utilisateur par défaut | `pi` | choisi à la création de l'image |

## Liens

- [Wiki Waveshare — 4inch DSI LCD (C)](https://www.waveshare.com/wiki/4inch_DSI_LCD_(C))
- [Wiki Waveshare — 2.9inch e-Paper Module](https://www.waveshare.com/wiki/2.9inch_e-Paper_Module_Manual)
- [Documentation config.txt Raspberry Pi](https://www.raspberrypi.com/documentation/computers/config_txt.html)
- [python-escpos](https://python-escpos.readthedocs.io/)
- [gpiozero](https://gpiozero.readthedocs.io/)
