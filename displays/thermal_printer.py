"""Imprimante thermique Epson : ticket de fin de compostage.

Le coordinateur alimentait déjà une file `'printer'` depuis l'origine, mais
aucun processus ne la lisait. Ce module la consomme et imprime un ticket quand
le compostage est terminé.

Comme pour l'e-paper, deux sorties possibles : l'imprimante réelle en ESC/POS
direct quand elle répond, sinon un mode à blanc qui journalise le ticket. Le
pipeline tourne donc sans imprimante branchée.

Un seul ticket par cycle, à l'arrivée en phase de visualisation : imprimer à
chaque message de progression viderait le rouleau en quelques minutes.
"""

import logging
import time

from modules.config import CONFIG
from modules.phases import CompostPhase, coerce_phase

logger = logging.getLogger("ThermalPrinter")


def format_receipt(summary, columns=None):
    """Compose le ticket en texte brut, sans accent.

    Les imprimantes ESC/POS n'affichent les accents que si la page de code
    correspond au texte envoyé, et elle varie d'un modèle à l'autre : on reste
    en ASCII, c'est la seule sortie fiable sur tout le parc.
    """
    columns = columns or CONFIG.hardware.printer_columns
    rule = "-" * columns

    def line(label, value):
        value = str(value)
        space = columns - len(label) - len(value)
        return f"{label}{' ' * max(1, space)}{value}"

    rows = [
        "DATA-COMPOST",
        rule,
        time.strftime("%Y-%m-%d %H:%M:%S"),
        "",
        line("Fichiers entres", summary.get("total_files", 0)),
        line("Fichiers compostes", summary.get("composted_files", 0)),
        line("Silos", summary.get("silo_count", 0)),
    ]

    if summary.get("avg_cn_ratio") is not None:
        rows.append(line("C/N moyen", f"{summary['avg_cn_ratio']:.1f}"))

    entree = summary.get("input_bytes") or 0
    sortie = summary.get("output_bytes") or 0
    if entree:
        rows += [
            "",
            line("Matiere entree", f"{entree / 1024:.0f} Ko"),
            line("Matiere restante", f"{sortie / 1024:.0f} Ko"),
            line("Perte", f"{(1 - sortie / entree) * 100:.1f} %"),
        ]

    rows += ["", rule, "Compostage termine", ""]
    return "\n".join(rows)


class DryRunPrinter:
    """Sortie de repli : le ticket part dans le journal."""

    name = "simulation"

    def print_receipt(self, text):
        logger.info("Ticket (aucune imprimante detectee) :\n%s", text)

    def close(self):
        pass


class EscposPrinter:
    """Imprimante Epson réelle, pilotée en ESC/POS direct via pyusb."""

    name = "escpos"

    def __init__(self, vendor_id=None):
        import usb.core
        from escpos.printer import Usb

        vendor_id = vendor_id or CONFIG.hardware.printer_vendor_id
        device = usb.core.find(idVendor=vendor_id)
        if device is None:
            raise RuntimeError(f"aucun peripherique {vendor_id:#06x} sur le bus USB")

        # L'identifiant produit varie selon l'interface UB-* installee :
        # on prend celui du peripherique trouve plutot que de le supposer.
        self.printer = Usb(vendor_id, device.idProduct)
        logger.info(f"Imprimante detectee : {vendor_id:#06x}:{device.idProduct:04x}")

    def print_receipt(self, text):
        lines = text.split("\n")
        self.printer.set(align="center", bold=True, double_height=True)
        self.printer.text(lines[0] + "\n")
        self.printer.set(align="left", bold=False, double_height=False)
        for row in lines[1:]:
            self.printer.text(row + "\n")
        self.printer.text("\n\n")
        self.printer.cut()

    def close(self):
        try:
            self.printer.close()
        except Exception as exc:  # noqa: BLE001 — l'arret ne doit pas lever
            logger.warning(f"Fermeture de l'imprimante incomplete : {exc}")


def create_printer(force_simulation=None, vendor_id=None):
    """Renvoie l'imprimante réelle si elle répond, le mode à blanc sinon."""
    if force_simulation is None:
        force_simulation = CONFIG.hardware.force_simulation

    if force_simulation:
        logger.info("Imprimante : simulation forcee par la configuration")
        return DryRunPrinter()

    try:
        return EscposPrinter(vendor_id=vendor_id)
    except Exception as exc:  # noqa: BLE001 — absence de materiel incluse
        logger.info(f"Imprimante : indisponible ({exc}), passage en mode a blanc")
        return DryRunPrinter()


def start_printer_display(update_queue, stop_queue, log_queue=None):
    """Processus imprimante : lit la file et imprime le ticket final.

    Même signature que les autres processus d'affichage, pour que le
    coordinateur les démarre tous de la même façon.
    """
    from modules.logging_config import setup_worker_logging
    setup_worker_logging(log_queue)

    if not CONFIG.hardware.printer_enabled:
        logger.info("Imprimante desactivee dans la configuration")
        return

    logger.info("Demarrage du processus imprimante")
    printer = create_printer()
    printed = False
    summary = {}

    try:
        while True:
            if not stop_queue.empty():
                stop_queue.get()
                break

            if update_queue.empty():
                time.sleep(0.2)
                continue

            message = update_queue.get(block=False)
            if not isinstance(message, dict):
                continue

            try:
                phase = coerce_phase(message.get("phase"))
            except (ValueError, KeyError):
                continue

            summary = _accumulate(summary, phase, message.get("data"))

            # Un seul ticket par cycle, une fois le compost constitue
            if phase == CompostPhase.RESULT_VISUALIZATION and not printed:
                printer.print_receipt(format_receipt(summary))
                printed = True

    except Exception as exc:  # noqa: BLE001 — le processus ne doit rien casser
        logger.error(f"Erreur dans le processus imprimante : {exc}")
    finally:
        printer.close()
        logger.info("Processus imprimante arrete")


def _accumulate(summary, phase, data):
    """Retient au passage ce dont le ticket aura besoin.

    Les données transitent phase par phase ; le ticket est imprimé à la fin,
    quand plus rien n'est renvoyé.
    """
    summary = dict(summary)

    if phase == CompostPhase.CN_CALCULATION and isinstance(data, list):
        summary["total_files"] = len(data)
        summary["input_bytes"] = sum(
            (f.get("common_metadata") or {}).get("size", 0) for f in data
        )
        ratios = [
            (f.get("cn_data") or {}).get("normalized_cn_ratio")
            for f in data
        ]
        ratios = [r for r in ratios if isinstance(r, (int, float))]
        if ratios:
            summary["avg_cn_ratio"] = sum(ratios) / len(ratios)

    elif phase == CompostPhase.SILO_CREATION and isinstance(data, list):
        summary["silo_count"] = len(data)

    elif phase == CompostPhase.COMPOSTING and isinstance(data, dict):
        summary.update(data)

    return summary
