"""Tests sur la couche matérielle : sélection de sortie et ménagement de la dalle.

Le matériel n'est pas branché ici. Ce qui est vérifiable sans lui, et qui
compte, c'est que l'absence de matériel ne casse rien et que les règles
protégeant la dalle e-paper sont respectées.
"""
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from displays.epaper_backend import (  # noqa: E402
    EPAPER_SIZE,
    EPaperOutput,
    SimulatedEPaper,
    create_backend,
    surface_to_image,
)
from displays.thermal_printer import (  # noqa: E402
    DryRunPrinter,
    _accumulate,
    create_printer,
    format_receipt,
)
from modules.phases import CompostPhase  # noqa: E402


class RecordingBackend:
    """Sortie factice : compte les écritures au lieu d'en faire."""

    def __init__(self):
        self.renders = 0

    def render(self, surface):
        self.renders += 1

    def close(self):
        pass


@pytest.fixture
def surface():
    pygame.init()
    s = pygame.Surface(EPAPER_SIZE)
    s.fill((255, 255, 255))
    return s


class TestBackendSelection:
    def test_falls_back_to_simulation_without_hardware(self):
        """Sans dalle branchée, le pipeline doit tourner quand même."""
        assert isinstance(create_backend(force_simulation=False), SimulatedEPaper)

    def test_simulation_can_be_forced(self):
        assert isinstance(create_backend(force_simulation=True), SimulatedEPaper)

    def test_printer_falls_back_to_dry_run(self):
        assert isinstance(create_printer(force_simulation=False), DryRunPrinter)


class TestSurfaceConversion:
    def test_produces_a_one_bit_image(self, surface):
        image = surface_to_image(surface)
        assert image.mode == "1"
        assert image.size == EPAPER_SIZE

    def test_dark_pixels_become_black(self, surface):
        pygame.draw.rect(surface, (0, 0, 0), (0, 0, 10, 10))
        image = surface_to_image(surface)
        assert image.getpixel((5, 5)) == 0
        assert image.getpixel((200, 100)) == 255


class TestRefreshDiscipline:
    """Une dalle e-paper met deux secondes à s'écrire et s'use à être réécrite."""

    def test_identical_image_is_not_resent(self, surface):
        backend = RecordingBackend()
        out = EPaperOutput(backend=backend, min_interval=0)
        assert out.show(surface, now=0) is True
        assert out.show(surface, now=100) is False
        assert backend.renders == 1

    def test_changed_image_is_sent(self, surface):
        backend = RecordingBackend()
        out = EPaperOutput(backend=backend, min_interval=0)
        out.show(surface, now=0)
        pygame.draw.rect(surface, (0, 0, 0), (0, 0, 20, 20))
        assert out.show(surface, now=1) is True
        assert backend.renders == 2

    def test_minimum_interval_is_respected(self, surface):
        backend = RecordingBackend()
        out = EPaperOutput(backend=backend, min_interval=20)
        assert out.show(surface, now=0) is True

        pygame.draw.rect(surface, (0, 0, 0), (0, 0, 20, 20))
        assert out.show(surface, now=5) is False, "écriture trop rapprochée"

        assert out.show(surface, now=25) is True
        assert backend.renders == 2

    def test_force_bypasses_both_guards(self, surface):
        backend = RecordingBackend()
        out = EPaperOutput(backend=backend, min_interval=20)
        out.show(surface, now=0)
        assert out.show(surface, force=True, now=1) is True

    def test_simulation_is_not_throttled(self, surface):
        """Une fenêtre n'a rien à ménager : elle suit le rythme du rendu."""
        out = EPaperOutput(backend=SimulatedEPaper(), min_interval=3600)
        assert out.show(surface, now=0) is True
        pygame.draw.rect(surface, (0, 0, 0), (0, 0, 20, 20))
        assert out.show(surface, now=1) is True


class TestReceipt:
    def _summary(self):
        return {
            "total_files": 11, "composted_files": 11, "silo_count": 2,
            "avg_cn_ratio": 84.2, "input_bytes": 7_588_000, "output_bytes": 3_770_000,
        }

    def test_contains_the_essentials(self):
        text = format_receipt(self._summary(), columns=42)
        assert "DATA-COMPOST" in text
        assert "11" in text and "50.3 %" in text

    def test_respects_the_paper_width(self):
        text = format_receipt(self._summary(), columns=32)
        assert all(len(line) <= 32 for line in text.split("\n"))

    def test_stays_ascii(self):
        """Les pages de code ESC/POS varient d'un modèle à l'autre."""
        text = format_receipt(self._summary())
        text.encode("ascii")

    def test_survives_an_empty_summary(self):
        assert "DATA-COMPOST" in format_receipt({})

    def test_no_division_by_zero_without_input(self):
        assert format_receipt({"output_bytes": 10, "input_bytes": 0})


class TestSummaryAccumulation:
    def test_collects_across_phases(self):
        files = [
            {"common_metadata": {"size": 1000}, "cn_data": {"normalized_cn_ratio": 10}},
            {"common_metadata": {"size": 3000}, "cn_data": {"normalized_cn_ratio": 20}},
        ]
        s = _accumulate({}, CompostPhase.CN_CALCULATION, files)
        assert s["total_files"] == 2
        assert s["input_bytes"] == 4000
        assert s["avg_cn_ratio"] == 15

        s = _accumulate(s, CompostPhase.SILO_CREATION, [{"silo_id": 1}, {"silo_id": 2}])
        assert s["silo_count"] == 2

        s = _accumulate(s, CompostPhase.COMPOSTING,
                        {"composted_files": 2, "output_bytes": 2000})
        assert s["composted_files"] == 2
        # Les phases précédentes ne doivent pas être écrasées
        assert s["total_files"] == 2 and s["silo_count"] == 2

    def test_ignores_unexpected_payloads(self):
        assert _accumulate({}, CompostPhase.CN_CALCULATION, None) == {}
        assert _accumulate({}, CompostPhase.SILO_CREATION, "pas une liste") == {}
