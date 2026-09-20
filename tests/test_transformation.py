"""Tests sur la décomposition de la matière.

Deux invariants tiennent tout le reste : rien n'est écarté du compost, et
tout ce qui en sort pèse moins que ce qui y est entré.
"""
import pytest

from modules.transformation import (
    LOSS_MAX,
    LOSS_MIN,
    MIN_DECOMPOSED_BYTES,
    decompose_bytes,
    decompose_text,
)


@pytest.fixture
def binary_file(tmp_path):
    def _make(size, name="matiere.bin"):
        path = tmp_path / name
        # Motif répétitif : compressible, donc représentatif d'un fichier réel
        path.write_bytes(bytes(range(256)) * (size // 256 + 1))
        return path
    return _make


class TestDecomposeBytes:
    """Le traitement de la matière opaque : archives, exécutables, sons."""

    @pytest.mark.parametrize("intensity", [0.0, 0.25, 0.5, 0.75, 1.0])
    def test_always_loses_matter(self, binary_file, tmp_path, intensity):
        source = binary_file(100_000)
        destination = tmp_path / "composte.bin"
        written = decompose_bytes(source, destination, intensity)
        assert written < source.stat().st_size
        assert destination.stat().st_size == written

    def test_loss_follows_intensity(self, binary_file, tmp_path):
        source = binary_file(200_000)
        inert = decompose_bytes(source, tmp_path / "a.bin", 0.0)
        lively = decompose_bytes(source, tmp_path / "b.bin", 1.0)
        assert lively < inert, "une matière vive doit se décomposer davantage"

    def test_loss_stays_within_the_declared_range(self, binary_file, tmp_path):
        source = binary_file(200_000)
        original = source.stat().st_size
        for intensity, expected in [(0.0, LOSS_MIN), (1.0, LOSS_MAX)]:
            written = decompose_bytes(source, tmp_path / f"{intensity}.bin", intensity)
            assert written == pytest.approx(original * (1 - expected), rel=0.02)

    def test_something_always_remains(self, binary_file, tmp_path):
        """Décomposer n'est pas supprimer."""
        source = binary_file(50_000)
        written = decompose_bytes(source, tmp_path / "reste.bin", 1.0)
        assert written >= MIN_DECOMPOSED_BYTES

    @pytest.mark.parametrize("size", [24, 100, 500, 1024])
    def test_small_files_are_composted_too(self, tmp_path, size):
        """Aucune exemption pour les petits fichiers : eux aussi se décomposent."""
        source = tmp_path / f"petit_{size}.ini"
        source.write_bytes(b"x" * size)
        written = decompose_bytes(source, tmp_path / f"out_{size}.ini", 1.0)
        assert 0 < written < size

    def test_content_actually_changes(self, binary_file, tmp_path):
        source = binary_file(100_000)
        destination = tmp_path / "composte.bin"
        decompose_bytes(source, destination, 1.0)
        assert destination.read_bytes() != source.read_bytes()[:destination.stat().st_size]

    def test_empty_file_does_not_crash(self, tmp_path):
        source = tmp_path / "vide.dat"
        source.write_bytes(b"")
        assert decompose_bytes(source, tmp_path / "out.dat", 0.5) == 0


class TestDecomposeText:
    def test_loses_words(self):
        text = " ".join(["compost"] * 500)
        assert len(decompose_text(text, 1.0).split()) < 500

    def test_never_empties_completely(self):
        assert decompose_text("compost numerique", 1.0).strip() != ""

    def test_single_word_survives(self):
        assert decompose_text("compost", 1.0).strip() != ""

    def test_empty_text_does_not_crash(self):
        assert decompose_text("", 0.5) == ""

    def test_higher_intensity_removes_more(self):
        text = " ".join(["matiere"] * 2000)
        light = len(decompose_text(text, 0.0).split())
        heavy = len(decompose_text(text, 1.0).split())
        assert heavy < light
