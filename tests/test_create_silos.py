"""Tests sur la logique de regroupement en silos."""
import pytest

from modules.create_silos import balance_silos


def _file(cn_ratio, size=1):
    return {
        "common_metadata": {"size": size, "path": f"/x/{cn_ratio}", "name": str(cn_ratio)},
        "cn_data": {"normalized_cn_ratio": cn_ratio},
    }


class TestBalanceSilos:
    def test_silo_smaller_than_two_kept_intact(self):
        single = [_file(50)]
        empty = []
        result = balance_silos([single, empty], target_ratio=30)
        assert result == [single, empty]

    def test_already_balanced_silo_kept(self):
        # avg = 30, target = 30, |diff| = 0 < 5 → conservé tel quel
        silo = [_file(28), _file(30), _file(32)]
        result = balance_silos([silo], target_ratio=30)
        assert result == [silo]

    def test_unbalanced_silo_is_split_in_half_sorted(self):
        # avg = 60, target = 10, |diff| = 50 > 5 → split
        silo = [_file(40), _file(80), _file(60), _file(60)]
        result = balance_silos([silo], target_ratio=10)
        assert len(result) == 2
        # Le tri par C/N doit séparer les bas / hauts
        low_half_ratios = [f["cn_data"]["normalized_cn_ratio"] for f in result[0]]
        high_half_ratios = [f["cn_data"]["normalized_cn_ratio"] for f in result[1]]
        assert max(low_half_ratios) <= min(high_half_ratios)

    def test_odd_size_silo_split_lower_half_smaller(self):
        silo = [_file(10), _file(20), _file(30), _file(40), _file(50)]
        # avg = 30, target = 100 → split
        result = balance_silos([silo], target_ratio=100)
        assert [len(s) for s in result] == [2, 3]

    def test_preserves_all_files_across_splits(self):
        silo = [_file(i * 10) for i in range(1, 7)]
        result = balance_silos([silo], target_ratio=1000)
        flat = [f for sublist in result for f in sublist]
        assert sorted(f["cn_data"]["normalized_cn_ratio"] for f in flat) == [10, 20, 30, 40, 50, 60]
