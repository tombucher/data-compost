"""
Package pour les différents modules d'affichage du système de compostage numérique.

Ce package contient les modules pour afficher les informations sur les différents
écrans utilisés dans le système.
"""

from enum import Enum

# Définition des phases du processus, utilisée par tous les modules d'affichage
class CompostPhase(Enum):
    IDLE = 0
    FILE_ANALYSIS = 1
    CN_CALCULATION = 2
    SILO_CREATION = 3
    COMPOSTING = 4
    RESULT_VISUALIZATION = 5

# Importation pour faciliter l'accès
try:
    from .circular_display import start_circular_display
    from .hdmi_display import start_hdmi_display
    from .epaper_display import start_epaper_display, display_compost_info
except ImportError:
    # Gestion des erreurs lors de l'importation
    import logging
    logging.warning("Impossible d'importer certains modules d'affichage")

__all__ = [
    'CompostPhase',
    'start_circular_display',
    'start_hdmi_display',
    'start_epaper_display',
    'display_compost_info'
]
