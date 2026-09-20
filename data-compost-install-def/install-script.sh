#!/usr/bin/env bash
#
# Installation de data-compost sur Raspberry Pi 5
#
# Périphériques configurés :
#   - Écran circulaire Waveshare 4" (C), 720x720, interface DSI
#   - Écran e-paper Waveshare 2.9", interface SPI/GPIO
#   - Imprimante thermique Epson TM-T70II, USB (ESC/POS direct)
#   - Écran HDMI standard
#
# Cible : Raspberry Pi OS Bookworm ou Trixie, 64 bits, session Wayland.
#
# Le script est idempotent : on peut le relancer sans rien casser.
# Il ne réécrit jamais config.txt en entier, il n'y insère qu'un bloc délimité.
#
# Usage : sudo ./install-script.sh [options]
#
set -euo pipefail

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

SKIP_UPGRADE=0      # ne pas faire apt upgrade
SKIP_APP=0          # ne pas installer l'application data-compost
SKIP_PRINTER=0      # ne pas configurer l'imprimante thermique
SKIP_EPAPER=0       # ne pas configurer l'écran e-paper
USE_DSI0=0          # brancher l'écran circulaire sur DSI0 au lieu de DSI1
WITH_CUPS=0         # installer CUPS en plus de l'accès ESC/POS direct
ASSUME_YES=0        # ne poser aucune question

usage() {
  cat <<'USAGE'
Usage : sudo ./install-script.sh [options]

  --skip-upgrade    Ne pas lancer apt upgrade (installation plus rapide)
  --skip-app        Ne configurer que les périphériques, pas l'application
  --skip-printer    Ignorer l'imprimante thermique
  --skip-epaper     Ignorer l'écran e-paper
  --dsi0            Écran circulaire branché sur le port DSI0 (par défaut DSI1)
  --with-cups       Installer aussi CUPS (par défaut : ESC/POS direct uniquement)
  -y, --yes         Répondre oui à toutes les questions
  -h, --help        Afficher cette aide
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --skip-upgrade) SKIP_UPGRADE=1 ;;
    --skip-app)     SKIP_APP=1 ;;
    --skip-printer) SKIP_PRINTER=1 ;;
    --skip-epaper)  SKIP_EPAPER=1 ;;
    --dsi0)         USE_DSI0=1 ;;
    --with-cups)    WITH_CUPS=1 ;;
    -y|--yes)       ASSUME_YES=1 ;;
    -h|--help)      usage; exit 0 ;;
    *) echo "Option inconnue : $1"; usage; exit 1 ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Affichage
# ---------------------------------------------------------------------------

print_status()  { echo -e "\033[1;34m[*]\033[0m $1"; }
print_success() { echo -e "\033[1;32m[+]\033[0m $1"; }
print_error()   { echo -e "\033[1;31m[-]\033[0m $1" >&2; }
print_warn()    { echo -e "\033[1;33m[!]\033[0m $1"; }
print_info()    { echo -e "    $1"; }

WARNINGS=()
warn() { print_warn "$1"; WARNINGS+=("$1"); }

confirm() {
  [ "$ASSUME_YES" -eq 1 ] && return 0
  read -r -p "$1 (o/n) : " -n 1 reply
  echo
  [[ "$reply" =~ ^[OoYy]$ ]]
}

# ---------------------------------------------------------------------------
# Contexte : root, utilisateur cible, modèle, chemin de config.txt
# ---------------------------------------------------------------------------

if [ "$(id -u)" -ne 0 ]; then
  print_error "Ce script doit être lancé avec sudo."
  print_info "Exemple : sudo ./install-script.sh"
  exit 1
fi

# L'utilisateur propriétaire de l'installation : jamais « pi » en dur, le nom
# par défaut est choisi à la création de la carte SD depuis Raspberry Pi Imager.
TARGET_USER="${SUDO_USER:-}"
if [ -z "$TARGET_USER" ] || [ "$TARGET_USER" = "root" ]; then
  TARGET_USER="$(getent passwd 1000 | cut -d: -f1 || true)"
fi
if [ -z "$TARGET_USER" ]; then
  print_error "Impossible de déterminer l'utilisateur cible."
  print_info "Relancez via « sudo ./install-script.sh » depuis une session utilisateur."
  exit 1
fi
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [ ! -d "$TARGET_HOME" ]; then
  print_error "Le dossier personnel de $TARGET_USER est introuvable : $TARGET_HOME"
  exit 1
fi

# Exécuter une commande en tant qu'utilisateur cible
as_user() { sudo -u "$TARGET_USER" -H bash -c "$1"; }

# Racine du dépôt data-compost : le dossier parent de ce script, s'il contient main.py
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
[ -f "$REPO_ROOT/main.py" ] || REPO_ROOT=""

MODEL="inconnu"
[ -r /proc/device-tree/model ] && MODEL="$(tr -d '\0' < /proc/device-tree/model)"

# Bookworm et versions suivantes : /boot/firmware/config.txt.
# /boot/config.txt n'est plus lu depuis Bookworm.
if [ -f /boot/firmware/config.txt ]; then
  CONFIG_TXT=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  CONFIG_TXT=/boot/config.txt
  warn "Système ancien : config.txt trouvé dans /boot au lieu de /boot/firmware."
else
  print_error "config.txt introuvable (ni /boot/firmware/config.txt ni /boot/config.txt)."
  exit 1
fi

print_status "=== INSTALLATION DATA-COMPOST — RASPBERRY PI ==="
print_info "Modèle        : $MODEL"
print_info "Utilisateur   : $TARGET_USER ($TARGET_HOME)"
print_info "config.txt    : $CONFIG_TXT"
print_info "Dépôt         : ${REPO_ROOT:-non détecté}"
print_info "Date          : $(date)"
echo

case "$MODEL" in
  *"Raspberry Pi 5"*) ;;
  *)
    warn "Script prévu pour un Raspberry Pi 5, modèle détecté : $MODEL"
    confirm "Continuer quand même ?" || { print_info "Installation annulée."; exit 0; }
    ;;
esac

# Un /boot/config.txt résiduel n'est plus lu et induit en erreur : le signaler.
if [ "$CONFIG_TXT" = /boot/firmware/config.txt ] && [ -f /boot/config.txt ] && [ ! -L /boot/config.txt ]; then
  warn "Un fichier /boot/config.txt existe mais n'est PAS lu par le système."
  print_info "Le fichier réellement utilisé est /boot/firmware/config.txt."
  print_info "Vous pouvez supprimer /boot/config.txt pour éviter la confusion."
fi

# ---------------------------------------------------------------------------
# Paquets système
# ---------------------------------------------------------------------------

print_status "Mise à jour de la liste des paquets..."
apt-get update

if [ "$SKIP_UPGRADE" -eq 0 ]; then
  print_status "Mise à jour du système (--skip-upgrade pour sauter cette étape)..."
  DEBIAN_FRONTEND=noninteractive apt-get -y upgrade
fi

print_status "Installation des dépendances système..."
APT_PACKAGES=(
  git
  python3-pip python3-venv python3-dev build-essential
  python3-pil python3-numpy
  wlr-randr
)

# Bibliothèques GPIO. RPi.GPIO ne fonctionne PAS sur Pi 5 (nouveau contrôleur
# RP1) ; le pilote Waveshare e-Paper utilise gpiozero, qui passe par lgpio.
[ "$SKIP_EPAPER" -eq 0 ] && APT_PACKAGES+=(python3-gpiozero python3-lgpio python3-spidev)

# Imprimante : accès USB direct en ESC/POS, pas besoin de CUPS.
[ "$SKIP_PRINTER" -eq 0 ] && APT_PACKAGES+=(python3-usb usbutils)
[ "$WITH_CUPS" -eq 1 ] && APT_PACKAGES+=(cups libcups2-dev libcupsimage2-dev)

# Application : OpenCV et pygame en paquets système, bien plus rapide que pip.
if [ "$SKIP_APP" -eq 0 ]; then
  APT_PACKAGES+=(
    python3-opencv python3-pygame python3-scipy python3-matplotlib
    tesseract-ocr tesseract-ocr-fra
    ffmpeg libatlas-base-dev
  )
fi

DEBIAN_FRONTEND=noninteractive apt-get install -y "${APT_PACKAGES[@]}"
print_success "Dépendances système installées."

# RPi.GPIO préinstallé est inutilisable sur Pi 5 : le signaler sans le désinstaller
# (d'autres paquets peuvent en dépendre).
if dpkg -s python3-rpi.gpio >/dev/null 2>&1 && [[ "$MODEL" == *"Raspberry Pi 5"* ]]; then
  print_info "Note : python3-rpi.gpio est présent mais inopérant sur Pi 5."
  print_info "       Les scripts de ce projet utilisent gpiozero + lgpio."
fi

# ---------------------------------------------------------------------------
# config.txt : bloc géré, inséré sans écraser le reste du fichier
# ---------------------------------------------------------------------------

print_status "Configuration de config.txt..."

BEGIN_MARK="# >>> data-compost >>>"
END_MARK="# <<< data-compost <<<"

BACKUP="${CONFIG_TXT}.data-compost-backup-$(date +%Y%m%d-%H%M%S)"
cp -a "$CONFIG_TXT" "$BACKUP"
print_info "Sauvegarde : $BACKUP"

# Réécrit un fichier depuis stdin en conservant son inode, ses permissions et
# son propriétaire — on écrit dans la partition de démarrage, mieux vaut ne pas
# la recréer de zéro.
rewrite_config() {
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  cat "$tmp" > "$CONFIG_TXT"
  rm -f "$tmp"
}

# Retirer un éventuel bloc précédent (relance du script). awk plutôt que sed -i :
# les marqueurs contiennent des « > » et « # », et la comparaison est littérale.
if grep -qF "$BEGIN_MARK" "$CONFIG_TXT"; then
  awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    index($0, b) == 1 { skip = 1; next }
    skip == 1 { if (index($0, e) == 1) skip = 0; next }
    { print }
  ' "$CONFIG_TXT" | rewrite_config
  print_info "Ancien bloc data-compost retiré."
fi

# Supprimer les lignes vides de fin, sinon chaque relance en empile une
awk '
  { lines[NR] = $0 }
  END {
    last = NR
    while (last > 0 && lines[last] ~ /^[[:space:]]*$/) last--
    for (i = 1; i <= last; i++) print lines[i]
  }
' "$CONFIG_TXT" | rewrite_config

DSI_OVERLAY="dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC"
[ "$USE_DSI0" -eq 1 ] && DSI_OVERLAY="${DSI_OVERLAY},dsi0"

# Inspecter le fichier AVANT d'y écrire : le relire pendant l'ajout donnerait
# des résultats dépendants du tampon d'écriture.
NEED_KMS=0
NEED_SPI=0
grep -qE '^\s*dtoverlay=vc4-kms-v3d' "$CONFIG_TXT" || NEED_KMS=1
if [ "$SKIP_EPAPER" -eq 0 ]; then
  grep -qE '^\s*dtparam=spi=on' "$CONFIG_TXT" || NEED_SPI=1
fi

{
  echo ""
  echo "$BEGIN_MARK"
  # Si le fichier se terminait par une section conditionnelle ([cm4], [pi4]...),
  # nos lignes y seraient rattachées et ignorées sur Pi 5. [all] remet à zéro.
  echo "[all]"
  echo "# Écran circulaire Waveshare 4\" (C) — 720x720, DSI"
  echo "$DSI_OVERLAY"
  [ "$NEED_KMS" -eq 1 ] && echo "dtoverlay=vc4-kms-v3d"
  if [ "$NEED_SPI" -eq 1 ]; then
    echo "# SPI pour l'écran e-paper 2.9\""
    echo "dtparam=spi=on"
  fi
  echo "$END_MARK"
} >> "$CONFIG_TXT"

# Les réglages hérités du firmware legacy n'ont plus d'effet avec le pilote KMS
# du Pi 5 et brouillent le diagnostic quand ils traînent dans le fichier.
for legacy in hdmi_timings hdmi_force_hotplug hdmi_drive hdmi_group hdmi_mode arm_64bit; do
  if grep -qE "^\s*${legacy}=" "$CONFIG_TXT"; then
    warn "config.txt contient « ${legacy}= », sans effet sur Pi 5 avec vc4-kms-v3d."
    print_info "       Ligne laissée en place ; à retirer à la main si elle gêne."
  fi
done

print_success "config.txt configuré (bloc délimité, reste du fichier intact)."

# SPI via raspi-config, pour rester cohérent avec l'outil système
if [ "$SKIP_EPAPER" -eq 0 ] && command -v raspi-config >/dev/null 2>&1; then
  raspi-config nonint do_spi 0 || warn "raspi-config n'a pas pu activer SPI."
fi

# ---------------------------------------------------------------------------
# Groupes utilisateur
# ---------------------------------------------------------------------------

print_status "Ajout de $TARGET_USER aux groupes matériels..."
for grp in spi gpio i2c lp dialout video render plugdev; do
  if getent group "$grp" >/dev/null 2>&1; then
    usermod -a -G "$grp" "$TARGET_USER"
  fi
done
print_success "Groupes mis à jour (effectif à la prochaine ouverture de session)."

# ---------------------------------------------------------------------------
# Écran e-paper Waveshare 2.9"
# ---------------------------------------------------------------------------

EPAPER_LIB=""

if [ "$SKIP_EPAPER" -eq 0 ]; then
  print_status "Installation du pilote e-paper Waveshare..."

  EPAPER_DIR="$TARGET_HOME/e-Paper"
  if [ -d "$EPAPER_DIR/.git" ]; then
    print_info "Dépôt déjà présent, mise à jour..."
    as_user "cd '$EPAPER_DIR' && git pull --ff-only" || warn "git pull a échoué dans $EPAPER_DIR"
  else
    as_user "git clone --depth 1 https://github.com/waveshare/e-Paper '$EPAPER_DIR'"
  fi
  # Le clone est fait en tant qu'utilisateur : pas de chown correctif nécessaire,
  # mais on répare le cas d'une installation précédente faite en root.
  chown -R "$TARGET_USER:$TARGET_USER" "$EPAPER_DIR"

  EPAPER_LIB="$EPAPER_DIR/RaspberryPi_JetsonNano/python/lib"
  if [ ! -d "$EPAPER_LIB" ]; then
    warn "Bibliothèque e-paper introuvable : $EPAPER_LIB"
    EPAPER_LIB=""
  fi

  print_success "Pilote e-paper installé."
fi

# ---------------------------------------------------------------------------
# Imprimante thermique Epson — ESC/POS direct
# ---------------------------------------------------------------------------

PRINTER_ID=""

if [ "$SKIP_PRINTER" -eq 0 ]; then
  print_status "Configuration de l'imprimante thermique Epson..."

  # Détecter l'identifiant réel plutôt que de le supposer : le TM-T70II
  # n'expose pas toujours 04b8:0202 selon l'interface UB-* installée.
  PRINTER_ID="$(lsusb | grep -oE '04b8:[0-9a-fA-F]{4}' | head -n1 || true)"
  if [ -n "$PRINTER_ID" ]; then
    print_success "Imprimante Epson détectée : $PRINTER_ID"
  else
    warn "Aucune imprimante Epson détectée sur le bus USB."
    print_info "       Règle udev écrite pour tout périphérique Epson (04b8:*)."
    print_info "       Branchez et allumez l'imprimante, puis relancez ce script"
    print_info "       ou vérifiez avec : lsusb | grep 04b8"
  fi

  # Règle udev : accès au groupe lp + uaccess pour la session locale.
  # Une règle par vendeur, pour rester valide si le produit change.
  cat > /etc/udev/rules.d/99-epson-thermal.rules <<EOF
# Imprimante thermique Epson — accès direct ESC/POS depuis l'espace utilisateur
SUBSYSTEM=="usb", ATTRS{idVendor}=="04b8", MODE="0660", GROUP="lp", TAG+="uaccess"
EOF

  # Le module noyau usblp s'accapare l'imprimante et provoque le classique
  # « Resource busy » de pyusb. On l'écarte puisqu'on pilote en ESC/POS direct.
  if [ "$WITH_CUPS" -eq 0 ]; then
    cat > /etc/modprobe.d/data-compost-usblp.conf <<'EOF'
# data-compost pilote l'imprimante en ESC/POS direct via pyusb.
# usblp prendrait le périphérique et pyusb échouerait avec « Resource busy ».
blacklist usblp
EOF
    modprobe -r usblp 2>/dev/null || true
    print_info "Module usblp désactivé (conflit avec l'accès ESC/POS direct)."
  else
    rm -f /etc/modprobe.d/data-compost-usblp.conf
    print_info "CUPS demandé : usblp laissé actif."
    systemctl enable --now cups || warn "Impossible de démarrer le service CUPS."
    # Pas de --remote-admin --remote-any : l'administration CUPS reste locale,
    # l'ouvrir au réseau exposerait l'interface d'administration à tout le LAN.
    cupsctl --share-printers 2>/dev/null || true
  fi

  udevadm control --reload-rules
  udevadm trigger --subsystem-match=usb

  # Environnement Python dédié à l'imprimante, avec accès aux paquets système
  PRINTER_ENV="$TARGET_HOME/printer_env"
  if [ ! -x "$PRINTER_ENV/bin/python" ]; then
    as_user "python3 -m venv --system-site-packages '$PRINTER_ENV'"
  fi
  as_user "'$PRINTER_ENV/bin/pip' install --upgrade pip >/dev/null"
  as_user "'$PRINTER_ENV/bin/pip' install --upgrade python-escpos pyusb"

  print_success "Imprimante configurée (ESC/POS direct)."
fi

# ---------------------------------------------------------------------------
# Scripts de test
# ---------------------------------------------------------------------------

print_status "Installation des scripts de test..."

SCRIPTS_DIR="$TARGET_HOME/scripts"
install -d -o "$TARGET_USER" -g "$TARGET_USER" "$SCRIPTS_DIR"

# --- test e-paper ---------------------------------------------------------
if [ "$SKIP_EPAPER" -eq 0 ]; then
cat > "$SCRIPTS_DIR/test_epaper.py" <<EOF
#!/usr/bin/env python3
"""Test de l'écran e-paper Waveshare 2.9" sur Raspberry Pi 5.

Le pilote Waveshare s'appuie sur gpiozero (et donc lgpio sur Pi 5).
RPi.GPIO ne fonctionne pas sur Pi 5 et n'est pas utilisé ici.
"""
import sys
import time
from pathlib import Path

LIBDIR = Path("${EPAPER_LIB:-$TARGET_HOME/e-Paper/RaspberryPi_JetsonNano/python/lib}")
if LIBDIR.is_dir():
    sys.path.insert(0, str(LIBDIR))
else:
    sys.exit(f"Bibliothèque Waveshare introuvable : {LIBDIR}")

from PIL import Image, ImageDraw, ImageFont

# Le nom du module dépend de la révision exacte du module e-paper.
EPD = None
for module_name in ("epd2in9_V2", "epd2in9_V3", "epd2in9", "epd2in9b_V4", "epd2in9b_V3"):
    try:
        EPD = __import__(f"waveshare_epd.{module_name}", fromlist=["EPD"])
        print(f"Pilote utilisé : {module_name}")
        break
    except ImportError:
        continue
if EPD is None:
    sys.exit("Aucun pilote epd2in9* trouvé. Vérifiez le modèle exact de votre écran.")


def pick_font(size):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def main():
    epd = EPD.EPD()
    epd.init()
    epd.Clear(0xFF)

    # L'écran est physiquement en portrait : on dessine en paysage 296x128.
    image = Image.new("1", (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)

    draw.text((8, 4), "DATA-COMPOST", font=pick_font(20), fill=0)
    draw.text((8, 32), "e-paper 2.9\" — OK", font=pick_font(14), fill=0)
    draw.text((8, 54), time.strftime("%Y-%m-%d %H:%M:%S"), font=pick_font(14), fill=0)
    draw.line((8, 78, 288, 78), fill=0, width=2)
    draw.rectangle((8, 86, 288, 120), outline=0)
    draw.text((14, 94), "Raspberry Pi 5 / gpiozero", font=pick_font(12), fill=0)

    epd.display(epd.getbuffer(image))
    epd.sleep()
    print("Test réussi : l'écran doit afficher le texte.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — diagnostic utilisateur
        print(f"Erreur : {exc}")
        print()
        print("Pistes :")
        print("  - SPI activé ?            ls /dev/spidev*")
        print("  - Utilisateur dans spi/gpio ? groups")
        print("  - Câblage RST=17 DC=25 CS=8 BUSY=24 PWR=18 (BCM)")
        print("  - Autre révision d'écran : voir ~/e-Paper/.../examples/")
        sys.exit(1)
EOF
chmod +x "$SCRIPTS_DIR/test_epaper.py"
fi

# --- test imprimante ------------------------------------------------------
if [ "$SKIP_PRINTER" -eq 0 ]; then
cat > "$SCRIPTS_DIR/test_printer.py" <<EOF
#!$TARGET_HOME/printer_env/bin/python3
"""Test de l'imprimante thermique Epson en ESC/POS direct.

Le shebang pointe sur l'environnement ~/printer_env : le script s'exécute
directement, sans activation préalable et sans bricolage de sys.path.
"""
import sys
import time

try:
    import usb.core
    from escpos.printer import Usb
except ImportError as exc:
    sys.exit(
        f"Dépendance manquante ({exc}).\n"
        "Réinstallez avec :\n"
        "  ~/printer_env/bin/pip install python-escpos pyusb"
    )

EPSON_VENDOR = 0x04B8


def find_printer():
    """Cherche le premier périphérique Epson branché, sans identifiant figé."""
    device = usb.core.find(idVendor=EPSON_VENDOR)
    if device is None:
        sys.exit(
            "Aucun périphérique Epson (04b8) détecté.\n"
            "  - L'imprimante est-elle allumée et branchée en USB ?\n"
            "  - Vérifiez avec : lsusb | grep 04b8"
        )
    return device.idProduct


def main():
    product_id = find_printer()
    print(f"Imprimante trouvée : 04b8:{product_id:04x}")

    printer = Usb(EPSON_VENDOR, product_id)

    printer.set(align="center", bold=True, double_height=True, double_width=True)
    printer.text("DATA-COMPOST\n")
    printer.set(align="center", bold=False, double_height=False, double_width=False)
    printer.text("Test d'impression thermique\n")
    printer.text("----------------------------\n\n")

    printer.set(align="left")
    printer.text("Date : " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n\n")
    printer.text("Peripheriques configures :\n")
    printer.text("  - Ecran DSI circulaire 4\"\n")
    printer.text("  - Ecran e-paper 2.9\"\n")
    printer.text("  - Imprimante thermique\n")
    printer.text("  - Ecran HDMI\n\n")

    printer.set(align="center")
    printer.text("Installation OK\n")
    printer.text("\n\n\n")
    printer.cut()
    print("Impression envoyée.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 — diagnostic utilisateur
        print(f"Erreur : {exc}")
        print()
        print("Pistes :")
        print("  - « Resource busy » : le module usblp tient le périphérique.")
        print("    Vérifiez : lsmod | grep usblp   (doit être vide)")
        print("  - Permissions : groups | grep lp, puis rouvrir la session")
        print("  - Identifiant : lsusb | grep 04b8")
        sys.exit(1)
EOF
chmod +x "$SCRIPTS_DIR/test_printer.py"
fi

chown -R "$TARGET_USER:$TARGET_USER" "$SCRIPTS_DIR"
print_success "Scripts de test installés dans $SCRIPTS_DIR"

# ---------------------------------------------------------------------------
# Application data-compost
# ---------------------------------------------------------------------------

if [ "$SKIP_APP" -eq 0 ]; then
  if [ -z "$REPO_ROOT" ]; then
    warn "main.py introuvable au-dessus de ce script : installation de l'application ignorée."
    print_info "       Placez ce dossier dans le dépôt data-compost, ou utilisez --skip-app."
  else
    print_status "Installation de l'application data-compost..."

    VENV="$REPO_ROOT/venv"
    # --system-site-packages : le venv voit opencv, pygame, numpy, gpiozero et
    # spidev installés par apt. Compiler ces paquets avec pip sur un Pi prend
    # des heures pour un résultat moins bien optimisé.
    if [ ! -x "$VENV/bin/python" ]; then
      as_user "python3 -m venv --system-site-packages '$VENV'"
    else
      print_info "Environnement virtuel déjà présent."
      # Un venv copié depuis un poste de développement, ou créé sans l'option,
      # ne verrait ni opencv ni pygame : mieux vaut le dire tout de suite.
      if grep -q '^include-system-site-packages\s*=\s*false' "$VENV/pyvenv.cfg" 2>/dev/null; then
        warn "Le venv existant est isolé des paquets système."
        print_info "       opencv, pygame et gpiozero lui seront invisibles."
        print_info "       Corrigez avec : rm -rf '$VENV' puis relancez ce script."
      fi
    fi

    REQ="$SCRIPT_DIR/requirements-rpi.txt"
    if [ -f "$REQ" ]; then
      as_user "'$VENV/bin/pip' install --upgrade pip >/dev/null"
      as_user "'$VENV/bin/pip' install -r '$REQ'"
    else
      warn "requirements-rpi.txt introuvable, dépendances Python non installées."
    fi

    # Corpus NLTK utilisés par analyze.py et transformation.py
    as_user "'$VENV/bin/python' -m nltk.downloader -q punkt averaged_perceptron_tagger vader_lexicon wordnet" \
      || warn "Téléchargement des corpus NLTK incomplet (réseau ?)."

    chown -R "$TARGET_USER:$TARGET_USER" "$VENV"
    print_success "Application installée dans $VENV"
  fi
fi

# ---------------------------------------------------------------------------
# Disposition des écrans (Wayland)
# ---------------------------------------------------------------------------

print_status "Configuration de la disposition des écrans..."

# Raspberry Pi OS Bookworm et suivants utilisent Wayland (wayfire puis labwc).
# xrandr ne pilote plus rien : il ne voit que la couche XWayland.
WLR_CMD='wlr-randr --output HDMI-A-1 --on --output DSI-1 --on'

AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
install -d -o "$TARGET_USER" -g "$TARGET_USER" "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/data-compost-displays.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Disposition des écrans data-compost
Exec=sh -c "sleep 5 && $WLR_CMD"
X-GNOME-Autostart-enabled=true
Hidden=false
NoDisplay=true
EOF
chown -R "$TARGET_USER:$TARGET_USER" "$TARGET_HOME/.config"

# labwc ignore ~/.config/autostart : il lit son propre fichier autostart.
if [ -d "$TARGET_HOME/.config/labwc" ] || pgrep -x labwc >/dev/null 2>&1; then
  install -d -o "$TARGET_USER" -g "$TARGET_USER" "$TARGET_HOME/.config/labwc"
  LABWC_AUTOSTART="$TARGET_HOME/.config/labwc/autostart"
  touch "$LABWC_AUTOSTART"
  if ! grep -qF "data-compost" "$LABWC_AUTOSTART"; then
    printf '\n# data-compost : disposition des écrans\n(sleep 5 && %s) &\n' "$WLR_CMD" >> "$LABWC_AUTOSTART"
  fi
  chown "$TARGET_USER:$TARGET_USER" "$LABWC_AUTOSTART"
  print_info "Entrée ajoutée à ~/.config/labwc/autostart"
fi

print_success "Disposition des écrans configurée (wlr-randr)."
print_info "Ajustez ensuite avec : wlr-randr --output HDMI-A-1 --pos 720,0"

# ---------------------------------------------------------------------------
# Gestionnaire de périphériques
# ---------------------------------------------------------------------------

print_status "Installation du gestionnaire de périphériques..."

cat > "$SCRIPTS_DIR/raspi-display-manager.sh" <<'MANAGER'
#!/usr/bin/env bash
# Gestionnaire de périphériques data-compost — Raspberry Pi 5
set -uo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'
YELLOW='\033[0;33m'; BOLD='\033[1m'; NC='\033[0m'

pause() { echo; read -r -p "Entrée pour continuer..."; }

have() { command -v "$1" >/dev/null 2>&1; }

show_menu() {
  clear
  echo -e "${BOLD}=== GESTIONNAIRE DE PÉRIPHÉRIQUES — DATA-COMPOST ===${NC}"
  echo
  echo -e "${BLUE}[1]${NC} Tester l'écran e-paper"
  echo -e "${BLUE}[2]${NC} Tester l'imprimante thermique"
  echo -e "${BLUE}[3]${NC} Configurer la disposition des écrans"
  echo -e "${BLUE}[4]${NC} Informations système"
  echo -e "${BLUE}[5]${NC} Diagnostic complet de l'installation"
  echo -e "${BLUE}[6]${NC} Redémarrer le Raspberry Pi"
  echo -e "${BLUE}[0]${NC} Quitter"
  echo
  echo -n "Option (0-6) : "
}

test_epaper() {
  echo -e "${YELLOW}[*] Test de l'écran e-paper...${NC}"
  if [ -x "$HOME/scripts/test_epaper.py" ]; then
    python3 "$HOME/scripts/test_epaper.py"
  else
    echo -e "${RED}[-] ~/scripts/test_epaper.py absent.${NC}"
  fi
  pause
}

test_printer() {
  echo -e "${YELLOW}[*] Test de l'imprimante thermique...${NC}"
  if [ -x "$HOME/scripts/test_printer.py" ]; then
    # Le shebang pointe déjà sur ~/printer_env : pas d'activation nécessaire.
    "$HOME/scripts/test_printer.py"
  else
    echo -e "${RED}[-] ~/scripts/test_printer.py absent.${NC}"
  fi
  pause
}

configure_displays() {
  echo -e "${YELLOW}[*] Disposition des écrans${NC}"
  if ! have wlr-randr; then
    echo -e "${RED}[-] wlr-randr absent : sudo apt install wlr-randr${NC}"
    pause; return
  fi
  echo "Sorties détectées :"
  wlr-randr | grep -E '^[A-Za-z]' || true
  echo
  echo "1) HDMI à droite de l'écran circulaire"
  echo "2) HDMI à gauche de l'écran circulaire"
  echo "3) HDMI seul actif"
  echo "4) Écran circulaire seul actif"
  echo "0) Retour"
  echo
  read -r -p "Option (0-4) : " opt

  case "$opt" in
    1) cmd="wlr-randr --output DSI-1 --on --pos 0,0 --output HDMI-A-1 --on --pos 720,0" ;;
    2) cmd="wlr-randr --output HDMI-A-1 --on --pos 0,0 --output DSI-1 --on --pos 1920,0" ;;
    3) cmd="wlr-randr --output HDMI-A-1 --on --output DSI-1 --off" ;;
    4) cmd="wlr-randr --output DSI-1 --on --output HDMI-A-1 --off" ;;
    0) return ;;
    *) echo -e "${RED}[-] Option invalide.${NC}"; pause; return ;;
  esac

  if eval "$cmd"; then
    echo -e "${GREEN}[+] Appliqué.${NC}"
  else
    echo -e "${RED}[-] Échec. Les noms de sortie varient : vérifiez « wlr-randr ».${NC}"
    pause; return
  fi

  read -r -p "Enregistrer pour le démarrage ? (o/n) : " -n 1 save; echo
  if [[ "$save" =~ ^[Oo]$ ]]; then
    mkdir -p "$HOME/.config/autostart"
    cat > "$HOME/.config/autostart/data-compost-displays.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Disposition des écrans data-compost
Exec=sh -c "sleep 5 && $cmd"
X-GNOME-Autostart-enabled=true
Hidden=false
NoDisplay=true
EOF
    if [ -d "$HOME/.config/labwc" ]; then
      sed -i '/data-compost/,+1d' "$HOME/.config/labwc/autostart" 2>/dev/null || true
      printf '\n# data-compost : disposition des écrans\n(sleep 5 && %s) &\n' "$cmd" \
        >> "$HOME/.config/labwc/autostart"
    fi
    echo -e "${GREEN}[+] Enregistré.${NC}"
  fi
  pause
}

show_system_info() {
  echo -e "${YELLOW}[*] Informations système${NC}"
  echo
  echo -e "${BOLD}Modèle      :${NC} $(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo inconnu)"
  echo -e "${BOLD}OS          :${NC} $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo -e "${BOLD}Noyau       :${NC} $(uname -r)"
  have vcgencmd && echo -e "${BOLD}Temp. CPU   :${NC} $(vcgencmd measure_temp | cut -d= -f2)"
  echo -e "${BOLD}Session     :${NC} ${XDG_SESSION_TYPE:-inconnue} (${XDG_CURRENT_DESKTOP:-?})"
  echo
  echo -e "${BOLD}Sorties vidéo :${NC}"
  if have wlr-randr; then wlr-randr | grep -E '^[A-Za-z]' || true
  else echo "  wlr-randr absent"; fi
  echo
  echo -e "${BOLD}USB :${NC}"; lsusb
  echo
  echo -e "${BOLD}SPI :${NC}"; ls -l /dev/spidev* 2>/dev/null || echo "  aucun /dev/spidev* (SPI désactivé ?)"
  pause
}

run_diagnostic() {
  if [ -x "$HOME/scripts/check-install.sh" ]; then
    "$HOME/scripts/check-install.sh"
  else
    echo -e "${RED}[-] ~/scripts/check-install.sh absent.${NC}"
  fi
  pause
}

while true; do
  show_menu
  read -r option
  case "$option" in
    1) test_epaper ;;
    2) test_printer ;;
    3) configure_displays ;;
    4) show_system_info ;;
    5) run_diagnostic ;;
    6) echo -e "${YELLOW}[*] Redémarrage...${NC}"; sudo reboot ;;
    0) exit 0 ;;
    *) echo -e "${RED}[-] Option invalide.${NC}"; sleep 1 ;;
  esac
done
MANAGER
chmod +x "$SCRIPTS_DIR/raspi-display-manager.sh"

# Copier le script de diagnostic s'il est fourni à côté de l'installeur
if [ -f "$SCRIPT_DIR/check-install.sh" ]; then
  install -m 755 -o "$TARGET_USER" -g "$TARGET_USER" \
    "$SCRIPT_DIR/check-install.sh" "$SCRIPTS_DIR/check-install.sh"
fi

chown -R "$TARGET_USER:$TARGET_USER" "$SCRIPTS_DIR"

# Raccourci sur le bureau, s'il existe un bureau
DESKTOP_DIR="$TARGET_HOME/Desktop"
[ -d "$TARGET_HOME/Bureau" ] && DESKTOP_DIR="$TARGET_HOME/Bureau"
if [ -d "$DESKTOP_DIR" ]; then
  cat > "$DESKTOP_DIR/DisplayManager.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Gestionnaire d'affichage
Comment=Écrans et périphériques data-compost
Exec=$SCRIPTS_DIR/raspi-display-manager.sh
Icon=preferences-desktop-display
Terminal=true
Categories=Utility;
EOF
  chmod +x "$DESKTOP_DIR/DisplayManager.desktop"
  chown "$TARGET_USER:$TARGET_USER" "$DESKTOP_DIR/DisplayManager.desktop"
fi

print_success "Gestionnaire installé : $SCRIPTS_DIR/raspi-display-manager.sh"

# ---------------------------------------------------------------------------
# Bilan
# ---------------------------------------------------------------------------

echo
print_status "=== INSTALLATION TERMINÉE ==="
print_info "Écran circulaire : $DSI_OVERLAY"
[ "$SKIP_EPAPER" -eq 0 ]  && print_info "E-paper          : ${EPAPER_LIB:-non installé}"
[ "$SKIP_PRINTER" -eq 0 ] && print_info "Imprimante       : ${PRINTER_ID:-non détectée} (ESC/POS direct)"
[ "$SKIP_APP" -eq 0 ] && [ -n "$REPO_ROOT" ] && print_info "Application      : $REPO_ROOT/venv"
print_info "Scripts          : $SCRIPTS_DIR"
print_info "Sauvegarde       : $BACKUP"

if [ ${#WARNINGS[@]} -gt 0 ]; then
  echo
  print_warn "${#WARNINGS[@]} avertissement(s) :"
  for w in "${WARNINGS[@]}"; do print_info "- $w"; done
fi

echo
print_info "Un redémarrage est nécessaire : config.txt et les groupes ont changé."
print_info "Après redémarrage, lancez : $SCRIPTS_DIR/check-install.sh"

echo
if confirm "Redémarrer maintenant ?"; then
  print_info "Redémarrage..."
  reboot
else
  print_info "Pensez à redémarrer : sudo reboot"
fi

exit 0
