"""Phases du pipeline de compostage, et leur représentation visuelle.

Source unique. L'énumération était auparavant redéfinie à l'identique dans
cinq fichiers — le coordinateur, les trois écrans et `displays/__init__.py`.
Les classes obtenues étaient distinctes au sens de Python, si bien qu'un
`isinstance(phase, CompostPhase)` entre deux modules répondait toujours faux
et qu'une divergence dans l'une des copies serait passée inaperçue.
"""

from enum import Enum


class CompostPhase(Enum):
    """Les 5 phases ordonnées du pipeline, du démarrage à la visualisation."""
    IDLE = 0
    FILE_ANALYSIS = 1
    CN_CALCULATION = 2
    SILO_CREATION = 3
    COMPOSTING = 4
    RESULT_VISUALIZATION = 5


# Couleur associée à chaque phase, partagée par l'écran circulaire et l'HDMI
PHASE_COLORS = {
    CompostPhase.IDLE: (80, 80, 80),                   # Gris
    CompostPhase.FILE_ANALYSIS: (46, 204, 113),        # Vert
    CompostPhase.CN_CALCULATION: (52, 152, 219),       # Bleu
    CompostPhase.SILO_CREATION: (155, 89, 182),        # Violet
    CompostPhase.COMPOSTING: (241, 196, 15),           # Jaune
    CompostPhase.RESULT_VISUALIZATION: (231, 76, 60),  # Rouge
}

PHASE_DESCRIPTIONS = {
    CompostPhase.IDLE: "EN ATTENTE",
    CompostPhase.FILE_ANALYSIS: "ANALYSE DES FICHIERS",
    CompostPhase.CN_CALCULATION: "CALCUL C/N",
    CompostPhase.SILO_CREATION: "CRÉATION DES SILOS",
    CompostPhase.COMPOSTING: "COMPOSTAGE",
    CompostPhase.RESULT_VISUALIZATION: "VISUALISATION",
}


def coerce_phase(phase):
    """Accepte un CompostPhase, sa valeur entière ou son nom, et renvoie l'enum.

    Les messages transitent entre processus sous forme d'entiers : chaque écran
    refaisait la conversion à sa manière, avec des gardes différentes.
    """
    if isinstance(phase, CompostPhase):
        return phase
    if isinstance(phase, str):
        return CompostPhase[phase]
    return CompostPhase(phase)
