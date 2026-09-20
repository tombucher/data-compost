#!/usr/bin/env bash
#
# Diagnostic de l'installation data-compost sur Raspberry Pi.
# À lancer APRÈS le redémarrage qui suit install-script.sh.
#
# Ne modifie rien. Sort avec un code non nul si au moins un test échoue.
#
# Usage : ./check-install.sh
#
set -uo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

PASS=0
FAIL=0
WARN=0

ok()    { echo -e "  ${GREEN}✓${NC} $1"; PASS=$((PASS + 1)); }
ko()    { echo -e "  ${RED}✗${NC} $1"; [ $# -gt 1 ] && echo -e "      ${YELLOW}→ $2${NC}"; FAIL=$((FAIL + 1)); }
warn()  { echo -e "  ${YELLOW}!${NC} $1"; [ $# -gt 1 ] && echo -e "      ${YELLOW}→ $2${NC}"; WARN=$((WARN + 1)); }
info()  { echo -e "    $1"; }
section() { echo; echo -e "${BOLD}${BLUE}$1${NC}"; }

have() { command -v "$1" >/dev/null 2>&1; }

# Les imports Python de contrôle ne doivent rien afficher d'autre que leur verdict
export PYGAME_HIDE_SUPPORT_PROMPT=1

if [ "$(id -u)" -eq 0 ]; then
  echo -e "${YELLOW}Lancez ce diagnostic en utilisateur normal, pas avec sudo :${NC}"
  echo "  les tests de groupes et de venv porteraient sur root."
  exit 1
fi

REPO_ROOT=""
for candidate in "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" "$HOME/data-compost"; do
  [ -f "$candidate/main.py" ] && { REPO_ROOT="$candidate"; break; }
done

echo -e "${BOLD}=== DIAGNOSTIC DATA-COMPOST ===${NC}"

# ---------------------------------------------------------------------------
section "1. Système"
# ---------------------------------------------------------------------------

if [ -r /proc/device-tree/model ]; then
  MODEL="$(tr -d '\0' < /proc/device-tree/model)"
else
  MODEL="inconnu"
fi
case "$MODEL" in
  *"Raspberry Pi 5"*) ok "Modèle : $MODEL" ;;
  *) warn "Modèle : $MODEL" "L'installation vise un Raspberry Pi 5." ;;
esac

if [ -r /etc/os-release ]; then
  . /etc/os-release
  case "${VERSION_CODENAME:-}" in
    bookworm|trixie) ok "OS : $PRETTY_NAME" ;;
    *) warn "OS : $PRETTY_NAME" "Testé sur Bookworm et Trixie." ;;
  esac
fi

if [ "$(getconf LONG_BIT)" = "64" ]; then
  ok "Noyau 64 bits ($(uname -r))"
else
  ko "Noyau 32 bits" "Le Pi 5 exige un système 64 bits."
fi

case "${XDG_SESSION_TYPE:-}" in
  wayland) ok "Session Wayland (${XDG_CURRENT_DESKTOP:-?})" ;;
  x11)     warn "Session X11" "wlr-randr ne fonctionnera pas ; utilisez xrandr." ;;
  "")      info "Session graphique non détectée (diagnostic lancé en SSH ?)" ;;
  *)       warn "Session : $XDG_SESSION_TYPE" ;;
esac

# ---------------------------------------------------------------------------
section "2. config.txt"
# ---------------------------------------------------------------------------

if [ -f /boot/firmware/config.txt ]; then
  CONFIG_TXT=/boot/firmware/config.txt
elif [ -f /boot/config.txt ]; then
  CONFIG_TXT=/boot/config.txt
else
  CONFIG_TXT=""
fi

if [ -z "$CONFIG_TXT" ]; then
  ko "config.txt introuvable"
else
  ok "Fichier lu par le système : $CONFIG_TXT"

  if [ "$CONFIG_TXT" = /boot/firmware/config.txt ] && [ -f /boot/config.txt ] && [ ! -L /boot/config.txt ]; then
    warn "/boot/config.txt existe mais n'est PAS lu" "Vestige trompeur, supprimable."
  fi

  if grep -qF "# >>> data-compost >>>" "$CONFIG_TXT"; then
    ok "Bloc data-compost présent"
  else
    ko "Bloc data-compost absent" "Relancez install-script.sh."
  fi

  if grep -qE '^\s*dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC' "$CONFIG_TXT"; then
    ok "Overlay écran circulaire 4\" (C) configuré"
  else
    ko "Overlay DSI absent" "Attendu : dtoverlay=vc4-kms-dsi-waveshare-panel,4_0_inchC"
  fi

  if grep -qE '^\s*dtoverlay=vc4-kms-v3d' "$CONFIG_TXT"; then
    ok "Pilote graphique KMS actif"
  else
    ko "dtoverlay=vc4-kms-v3d absent"
  fi

  if grep -qE '^\s*dtparam=spi=on' "$CONFIG_TXT"; then
    ok "SPI activé dans config.txt"
  else
    ko "dtparam=spi=on absent" "Nécessaire pour l'écran e-paper."
  fi

  for legacy in hdmi_timings hdmi_force_hotplug hdmi_drive arm_64bit; do
    grep -qE "^\s*${legacy}=" "$CONFIG_TXT" && \
      warn "Réglage hérité « ${legacy}= » présent" "Sans effet sur Pi 5 avec KMS."
  done
fi

# ---------------------------------------------------------------------------
section "3. Écrans"
# ---------------------------------------------------------------------------

if have wlr-randr; then
  ok "wlr-randr installé"
  if OUTPUTS="$(wlr-randr 2>/dev/null)"; then
    if echo "$OUTPUTS" | grep -q '^DSI-1'; then
      ok "Écran circulaire détecté (DSI-1)"
      if echo "$OUTPUTS" | grep -A1 '^DSI-1' | grep -qE '720x720'; then
        ok "Résolution 720x720 confirmée"
      else
        warn "DSI-1 présent mais pas en 720x720"
      fi
    else
      ko "Aucune sortie DSI-1" "Nappe DSI mal enfichée, ou redémarrage pas encore fait."
    fi
    if echo "$OUTPUTS" | grep -q '^HDMI-A-'; then
      ok "Écran HDMI détecté ($(echo "$OUTPUTS" | grep -oE '^HDMI-A-[0-9]' | head -1))"
    else
      info "Aucun écran HDMI branché"
    fi
  else
    info "wlr-randr sans réponse (hors session graphique)"
  fi
else
  ko "wlr-randr absent" "sudo apt install wlr-randr"
fi

if have xrandr && [ "${XDG_SESSION_TYPE:-}" = "wayland" ]; then
  info "Rappel : sous Wayland, xrandr ne voit que XWayland et ne configure rien."
fi

# ---------------------------------------------------------------------------
section "4. Écran e-paper (SPI / GPIO)"
# ---------------------------------------------------------------------------

if ls /dev/spidev* >/dev/null 2>&1; then
  ok "Périphériques SPI : $(ls /dev/spidev* | tr '\n' ' ')"
else
  ko "Aucun /dev/spidev*" "SPI non activé, ou redémarrage manquant."
fi

MISSING_GROUPS=()
for grp in spi gpio lp dialout video render; do
  getent group "$grp" >/dev/null 2>&1 || continue
  id -nG | tr ' ' '\n' | grep -qx "$grp" || MISSING_GROUPS+=("$grp")
done
if [ ${#MISSING_GROUPS[@]} -eq 0 ]; then
  ok "Groupes matériels : $(id -nG | tr ' ' ',')"
else
  ko "Groupes manquants : ${MISSING_GROUPS[*]}" "Fermez puis rouvrez la session (ou redémarrez)."
fi

if python3 -c "import gpiozero" 2>/dev/null; then
  ok "gpiozero importable"
  if python3 -c "import lgpio" 2>/dev/null; then
    ok "lgpio importable (backend GPIO du Pi 5)"
  else
    ko "lgpio absent" "sudo apt install python3-lgpio"
  fi
else
  ko "gpiozero absent" "sudo apt install python3-gpiozero"
fi

if python3 -c "import RPi.GPIO" 2>/dev/null && [[ "$MODEL" == *"Raspberry Pi 5"* ]]; then
  info "RPi.GPIO est installé mais inopérant sur Pi 5 — non utilisé par ce projet."
fi

if python3 -c "import spidev" 2>/dev/null; then
  ok "spidev importable"
else
  ko "spidev absent" "sudo apt install python3-spidev"
fi

EPAPER_LIB="$HOME/e-Paper/RaspberryPi_JetsonNano/python/lib"
if [ -d "$EPAPER_LIB/waveshare_epd" ]; then
  ok "Pilote Waveshare présent"
  if PYTHONPATH="$EPAPER_LIB" python3 -c "from waveshare_epd import epdconfig" 2>/dev/null; then
    ok "Module waveshare_epd importable"
  else
    ko "waveshare_epd non importable" "Dépendance manquante : PIL, numpy, gpiozero ou spidev."
  fi
else
  ko "Pilote Waveshare absent" "git clone https://github.com/waveshare/e-Paper ~/e-Paper"
fi

if [ -x "$HOME/scripts/test_epaper.py" ]; then
  ok "Script de test : \$HOME/scripts/test_epaper.py"
else
  warn "\$HOME/scripts/test_epaper.py absent"
fi

# ---------------------------------------------------------------------------
section "5. Imprimante thermique"
# ---------------------------------------------------------------------------

if have lsusb; then
  if EPSON="$(lsusb | grep -iE '04b8:[0-9a-f]{4}' || true)"; then
    if [ -n "$EPSON" ]; then
      ok "Imprimante Epson détectée : $(echo "$EPSON" | grep -oE '04b8:[0-9a-f]{4}' | head -1)"
    else
      warn "Aucun périphérique Epson (04b8) sur le bus USB" "Imprimante éteinte ou débranchée ?"
    fi
  fi
else
  warn "lsusb absent" "sudo apt install usbutils"
fi

if have lsmod; then
  if lsmod | grep -q '^usblp'; then
    ko "Module usblp chargé" "Il accapare l'imprimante : pyusb échouera avec « Resource busy »."
  else
    ok "Module usblp non chargé (accès ESC/POS direct possible)"
  fi
else
  info "lsmod indisponible : impossible de vérifier le module usblp."
fi

if [ -f /etc/udev/rules.d/99-epson-thermal.rules ]; then
  ok "Règle udev imprimante en place"
else
  ko "Règle udev absente" "/etc/udev/rules.d/99-epson-thermal.rules"
fi

PRINTER_PY="$HOME/printer_env/bin/python3"
if [ -x "$PRINTER_PY" ]; then
  ok "Environnement \$HOME/printer_env présent"
  if "$PRINTER_PY" -c "import escpos" 2>/dev/null; then
    ok "python-escpos importable"
  else
    ko "python-escpos absent" "\$HOME/printer_env/bin/pip install python-escpos"
  fi
  if "$PRINTER_PY" -c "import usb.core" 2>/dev/null; then
    ok "pyusb importable"
  else
    ko "pyusb absent" "\$HOME/printer_env/bin/pip install pyusb"
  fi
else
  ko "\$HOME/printer_env absent" "Relancez install-script.sh sans --skip-printer."
fi

if [ -x "$HOME/scripts/test_printer.py" ]; then
  ok "Script de test : \$HOME/scripts/test_printer.py"
else
  warn "\$HOME/scripts/test_printer.py absent"
fi

# ---------------------------------------------------------------------------
section "6. Application data-compost"
# ---------------------------------------------------------------------------

if [ -z "$REPO_ROOT" ]; then
  warn "Dépôt data-compost introuvable" "Attendu à côté de ce script ou dans ~/data-compost."
else
  ok "Dépôt : $REPO_ROOT"
  VENV_PY="$REPO_ROOT/venv/bin/python"
  if [ -x "$VENV_PY" ]; then
    ok "Environnement virtuel présent"

    if "$VENV_PY" -c "import cv2" 2>/dev/null; then
      ok "Le venv voit les paquets système (opencv accessible)"
    else
      ko "opencv invisible depuis le venv" \
         "Le venv a été créé sans --system-site-packages. Supprimez-le et relancez l'installeur."
    fi

    MODULES_OK=1
    for mod in numpy cv2 pygame PIL scipy nltk tqdm pytesseract colorgram langdetect docx PyPDF2 moviepy; do
      "$VENV_PY" -c "import $mod" 2>/dev/null || { ko "Module Python manquant : $mod"; MODULES_OK=0; }
    done
    [ "$MODULES_OK" -eq 1 ] && ok "Toutes les dépendances Python du pipeline sont importables"

    if "$VENV_PY" -c "import librosa" 2>/dev/null; then
      ok "librosa présent (analyse audio complète)"
    else
      info "librosa absent — analyse audio en mode dégradé, c'est prévu."
    fi

    if (cd "$REPO_ROOT" && "$VENV_PY" -c "
import modules.analyze, modules.calculate_cn, modules.create_silos
import modules.transformation, modules.visualize_bin
" 2>/dev/null); then
      ok "Les modules du pipeline s'importent"
    else
      ko "Échec d'import des modules du pipeline" \
         "Détail : cd $REPO_ROOT && venv/bin/python -c 'import modules.analyze'"
    fi
  else
    ko "Environnement virtuel absent" "$REPO_ROOT/venv"
  fi

  if have tesseract; then
    ok "tesseract installé ($(tesseract --version 2>&1 | head -1))"
  else
    ko "tesseract absent" "sudo apt install tesseract-ocr — l'OCR des images en dépend."
  fi

  if have ffmpeg; then
    ok "ffmpeg installé"
  else
    warn "ffmpeg absent" "sudo apt install ffmpeg — nécessaire à l'analyse vidéo."
  fi

  NLTK_OK=1
  for corpus in corpora/wordnet tokenizers/punkt sentiment/vader_lexicon; do
    "${VENV_PY:-python3}" - "$corpus" <<'PY' 2>/dev/null || NLTK_OK=0
import sys
import nltk
nltk.data.find(sys.argv[1])
PY
  done
  if [ "$NLTK_OK" -eq 1 ]; then
    ok "Corpus NLTK disponibles"
  else
    warn "Corpus NLTK incomplets" "venv/bin/python -m nltk.downloader punkt wordnet vader_lexicon averaged_perceptron_tagger"
  fi
fi

# ---------------------------------------------------------------------------
section "7. Détection de clé USB"
# ---------------------------------------------------------------------------

MOUNTS="$(ls -d /media/"$USER"/* 2>/dev/null || true)"
if [ -n "$MOUNTS" ]; then
  ok "Clé USB montée : $MOUNTS"
else
  info "Aucune clé USB montée — normal si rien n'est branché."
  info "Le détecteur surveille /media/$USER et /mnt."
fi

# ---------------------------------------------------------------------------
# Bilan
# ---------------------------------------------------------------------------

echo
echo -e "${BOLD}=== BILAN ===${NC}"
echo -e "  ${GREEN}$PASS réussis${NC}   ${YELLOW}$WARN avertissements${NC}   ${RED}$FAIL échecs${NC}"
echo

if [ "$FAIL" -eq 0 ]; then
  echo -e "${GREEN}Installation opérationnelle.${NC}"
  echo "  Test e-paper    : ~/scripts/test_epaper.py"
  echo "  Test imprimante : ~/scripts/test_printer.py"
  echo "  Gestionnaire    : ~/scripts/raspi-display-manager.sh"
  exit 0
else
  echo -e "${RED}$FAIL point(s) à corriger — voir les flèches ci-dessus.${NC}"
  exit 1
fi
