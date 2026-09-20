"""Tests sur la composition des silos.

Le contrat : un silo est un *mélange*. L'implémentation précédente triait les
fichiers par C/N puis les découpait en tranches, ce qui regroupait les
semblables — l'inverse d'un équilibrage.
"""
import pytest

from modules.create_silos import SILO_TOLERANCE, compose_silos


def _file(cn_ratio, size=1, name=None):
    name = name or str(cn_ratio)
    return {
        "common_metadata": {"size": size, "path": f"/x/{name}", "name": name},
        "cn_data": {"normalized_cn_ratio": cn_ratio},
    }


def _flatten(silos):
    return [f for silo in silos for f in silo]


def _avg(silo):
    return sum(f["cn_data"]["normalized_cn_ratio"] for f in silo) / len(silo)


class TestMaterialIsPreserved:
    def test_no_file_is_lost_or_duplicated(self):
        files = [_file(i * 7, name=f"f{i}") for i in range(20)]
        silos = compose_silos(files, target_ratio=30)
        names = sorted(f["common_metadata"]["name"] for f in _flatten(silos))
        assert names == sorted(f["common_metadata"]["name"] for f in files)

    def test_empty_input_gives_no_silo(self):
        assert compose_silos([], target_ratio=30) == []

    def test_every_silo_holds_at_least_one_file(self):
        files = [_file(i * 7, name=f"f{i}") for i in range(20)]
        silos = compose_silos(files, target_ratio=30)
        assert all(len(silo) > 0 for silo in silos)


class TestMixing:
    def test_brown_and_green_end_up_together(self):
        """Une archive et des photos doivent se retrouver dans le même silo."""
        files = [_file(400, name="archive")] + [_file(5, name=f"photo{i}") for i in range(20)]
        silos = compose_silos(files, target_ratio=30)
        archive_silo = next(s for s in silos
                            if any(f["common_metadata"]["name"] == "archive" for f in s))
        assert len(archive_silo) > 1, "l'archive est restée seule au lieu d'être mélangée"
        assert any(f["cn_data"]["normalized_cn_ratio"] <= 30 for f in archive_silo)

    def test_balanced_material_reaches_the_target(self):
        """Avec assez de vert pour compenser le brun, un silo doit viser 30."""
        files = [_file(400, name="archive")] + [_file(5, name=f"photo{i}") for i in range(20)]
        silos = compose_silos(files, target_ratio=30)
        assert abs(_avg(silos[0]) - 30) <= SILO_TOLERANCE

    def test_beats_the_sorted_chunk_approach(self):
        """Comparaison directe avec l'ancienne logique de tri puis découpe."""
        files = [_file(400, name="a"), _file(300, name="b")] + \
                [_file(5, name=f"p{i}") for i in range(30)]

        composed = compose_silos(files, target_ratio=30)
        composed_error = sum(abs(_avg(s) - 30) for s in composed) / len(composed)

        # Ancienne approche : tri par C/N puis tranches de taille égale
        ordered = sorted(files, key=lambda f: f["cn_data"]["normalized_cn_ratio"])
        chunk = len(ordered) // len(composed) or len(ordered)
        sorted_chunks = [ordered[i:i + chunk] for i in range(0, len(ordered), chunk)]
        sorted_error = sum(abs(_avg(s) - 30) for s in sorted_chunks) / len(sorted_chunks)

        assert composed_error < sorted_error


class TestHomogeneousMaterial:
    """Sur une matière uniforme, aucun assemblage ne peut atteindre la cible.

    Le code doit alors terminer proprement plutôt que boucler ou perdre des
    fichiers — le cas est fréquent : une clé USB de photos n'a que du vert.
    """

    def test_only_green_terminates(self):
        files = [_file(5, name=f"p{i}") for i in range(10)]
        silos = compose_silos(files, target_ratio=30)
        assert len(_flatten(silos)) == 10

    def test_only_brown_terminates(self):
        files = [_file(400, name=f"z{i}") for i in range(10)]
        silos = compose_silos(files, target_ratio=30)
        assert len(_flatten(silos)) == 10

    def test_single_file(self):
        silos = compose_silos([_file(42, name="seul")], target_ratio=30)
        assert len(silos) == 1 and len(silos[0]) == 1


class TestSizeLimit:
    def test_limit_is_respected_between_files(self):
        files = [_file(30, size=40, name=f"f{i}") for i in range(10)]
        silos = compose_silos(files, target_ratio=30, size_limit=100)
        for silo in silos:
            if len(silo) > 1:
                assert sum(f["common_metadata"]["size"] for f in silo) <= 100

    def test_oversized_file_still_gets_a_silo(self):
        """Un fichier plus gros que la limite ne doit pas bloquer la boucle."""
        files = [_file(30, size=10_000, name="enorme"), _file(30, size=10, name="petit")]
        silos = compose_silos(files, target_ratio=30, size_limit=100)
        assert len(_flatten(silos)) == 2

    def test_all_files_oversized(self):
        files = [_file(30, size=10_000, name=f"gros{i}") for i in range(3)]
        silos = compose_silos(files, target_ratio=30, size_limit=100)
        assert len(_flatten(silos)) == 3
        assert all(len(silo) == 1 for silo in silos)


class TestMissingData:
    def test_file_without_cn_data_is_still_placed(self):
        """Le calcul C/N peut échouer : le fichier ne doit pas disparaître."""
        files = [{"common_metadata": {"size": 1, "path": "/x/y", "name": "y"}},
                 _file(30, name="ok")]
        silos = compose_silos(files, target_ratio=30)
        assert len(_flatten(silos)) == 2
