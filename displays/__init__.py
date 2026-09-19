"""
Package pour les différents modules d'affichage du système de compostage numérique.

Ce package contient les modules pour afficher les informations sur les différents
écrans utilisés dans le système.
"""

# Réexport pour compatibilité : la définition vit dans modules.phases
from modules.phases import CompostPhase

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
