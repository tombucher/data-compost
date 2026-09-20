"""Sorties possibles pour l'écran e-paper 2.9 pouces.

Le rendu est fait une seule fois, en pygame, sur une surface hors écran. Ce
module se charge ensuite de l'envoyer quelque part : sur la dalle Waveshare
quand elle est branchée, dans une fenêtre sinon. Le code de dessin de
`epaper_display` n'a donc pas à savoir sur quoi il travaille, et la même
version tourne sur le poste de développement et sur le Raspberry Pi.

Contraintes propres à une dalle e-paper, que la simulation n'impose pas :

- un rafraîchissement complet prend environ deux secondes ;
- rafraîchir en continu abîme la dalle durablement ;
- l'écran conserve son image sans alimentation, il n'y a donc aucune raison
  de réécrire une image identique.

D'où le double garde-fou de `EPaperOutput.show()` : on n'écrit que si l'image
a changé, et jamais plus souvent que l'intervalle configuré.
"""

import hashlib
import logging
import sys
import time

import pygame

from modules.config import CONFIG

logger = logging.getLogger("EPaperDisplay")

# Résolution de la dalle Waveshare 2.9 pouces, en paysage
EPAPER_SIZE = (296, 128)


def surface_to_image(surface):
    """Convertit une surface pygame en image Pillow noir et blanc 1 bit.

    Point de jonction entre les deux mondes : le dessin reste en pygame, la
    dalle attend du Pillow.
    """
    from PIL import Image

    raw = pygame.image.tostring(surface, "RGB")
    image = Image.frombytes("RGB", surface.get_size(), raw)
    # « 1 » sans tramage : sur deux niveaux, le tramage de Floyd-Steinberg
    # transforme le texte en bouillie de points.
    return image.convert("L").point(lambda v: 255 if v > 127 else 0, mode="1")


class SimulatedEPaper:
    """Fenêtre pygame imitant la dalle. Utilisée hors Raspberry Pi."""

    name = "simulation"

    def __init__(self, size=EPAPER_SIZE):
        self.size = size
        self.screen = pygame.display.set_mode(size)
        pygame.display.set_caption("Data Compost — e-paper (simulation)")

    def render(self, surface):
        self.screen.blit(surface, (0, 0))
        pygame.display.flip()

    def close(self):
        pass


class WaveshareEPaper:
    """Dalle Waveshare 2.9 pouces réelle, en SPI.

    Le nom du module de pilotage dépend de la révision exacte du matériel ;
    on essaie les variantes connues plutôt que d'en imposer une.
    """

    name = "waveshare"
    DRIVER_CANDIDATES = (
        "epd2in9_V2", "epd2in9_V3", "epd2in9",
        "epd2in9b_V4", "epd2in9b_V3",
    )

    def __init__(self, lib_path=None):
        lib_path = lib_path or CONFIG.hardware.epaper_lib_path
        if lib_path and str(lib_path) not in sys.path:
            sys.path.insert(0, str(lib_path))

        driver = None
        for module_name in self.DRIVER_CANDIDATES:
            try:
                driver = __import__(f"waveshare_epd.{module_name}", fromlist=["EPD"])
                logger.info(f"Pilote e-paper : {module_name}")
                break
            except ImportError:
                continue
        if driver is None:
            raise ImportError("aucun pilote waveshare_epd epd2in9* disponible")

        self.epd = driver.EPD()
        self.epd.init()
        self.epd.Clear(0xFF)
        self._sleeping = False

    def render(self, surface):
        image = surface_to_image(surface)
        if self._sleeping:
            # Sortir de veille avant d'écrire, sinon la dalle ignore l'ordre
            self.epd.init()
            self._sleeping = False
        self.epd.display(self.epd.getbuffer(image))
        # Remettre en veille aussitôt : laisser la dalle sous tension entre
        # deux images la dégrade.
        self.epd.sleep()
        self._sleeping = True

    def close(self):
        try:
            self.epd.init()
            self.epd.Clear(0xFF)
            self.epd.sleep()
        except Exception as exc:  # noqa: BLE001 — l'arrêt ne doit jamais lever
            logger.warning(f"Arrêt de l'écran e-paper incomplet : {exc}")


def create_backend(force_simulation=None, lib_path=None):
    """Renvoie la dalle réelle si elle répond, la simulation sinon.

    Aucune exception ne remonte : une installation sans e-paper doit tourner.
    """
    if force_simulation is None:
        force_simulation = CONFIG.hardware.force_simulation

    if force_simulation:
        logger.info("Écran e-paper : simulation forcée par la configuration")
        return SimulatedEPaper()

    try:
        backend = WaveshareEPaper(lib_path=lib_path)
        logger.info("Écran e-paper : dalle Waveshare détectée")
        return backend
    except Exception as exc:  # noqa: BLE001 — absence de matériel incluse
        logger.info(f"Écran e-paper : dalle indisponible ({exc}), passage en simulation")
        return SimulatedEPaper()


class EPaperOutput:
    """Enveloppe un backend et décide *quand* écrire.

    C'est ici que vivent les deux règles qui protègent la dalle : ne rien
    envoyer d'identique, et espacer les écritures.
    """

    def __init__(self, backend=None, min_interval=None):
        self.backend = backend if backend is not None else create_backend()
        self.min_interval = (
            min_interval if min_interval is not None
            else CONFIG.hardware.epaper_min_refresh_seconds
        )
        self._last_digest = None
        # None et non 0.0 : sinon la toute première écriture se retrouve
        # bloquée par l'intervalle quand l'horloge démarre près de zéro.
        self._last_render = None

    @property
    def is_simulation(self):
        return isinstance(self.backend, SimulatedEPaper)

    def show(self, surface, force=False, now=None):
        """Envoie la surface si elle a changé et si le délai est écoulé.

        Renvoie True si l'écran a effectivement été réécrit.
        """
        now = time.monotonic() if now is None else now
        digest = hashlib.blake2b(
            pygame.image.tostring(surface, "RGB"), digest_size=16
        ).digest()

        if not force:
            if digest == self._last_digest:
                return False
            # La simulation n'a rien à ménager : elle suit le rythme du rendu
            if (
                not self.is_simulation
                and self._last_render is not None
                and (now - self._last_render) < self.min_interval
            ):
                return False

        self.backend.render(surface)
        self._last_digest = digest
        self._last_render = now
        return True

    def close(self):
        self.backend.close()
