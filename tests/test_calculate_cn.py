"""Tests unitaires sur la logique pure de calculate_cn."""
from datetime import datetime, timedelta

import math
import pytest

from modules.calculate_cn import (
    calculate_age_factor,
    calculate_base_cn,
    calculate_cn_ratio,
    determine_file_type,
    normalize_cn_ratio,
)


def _make_file(category="text", name="foo.txt", size=1024, modified_days_ago=0,
               additional_data=None):
    modified_at = (datetime.now() - timedelta(days=modified_days_ago)).isoformat()
    return {
        "category": category,
        "common_metadata": {
            "name": name,
            "size": size,
            "modified_at": modified_at,
        },
        "additional_data": additional_data or {},
    }


class TestDetermineFileType:
    def test_hidden_file_is_brown(self):
        assert determine_file_type(_make_file(name=".hidden.txt", category="text")) == "brown"

    def test_system_category_is_brown(self):
        assert determine_file_type(_make_file(category="system")) == "brown"

    @pytest.mark.parametrize("category", ["image", "audio", "video", "text", "document", "creative"])
    def test_organic_categories_are_green(self, category):
        assert determine_file_type(_make_file(category=category)) == "green"

    def test_unknown_category(self):
        assert determine_file_type(_make_file(category="exotic")) == "unknown"


class TestCalculateAgeFactor:
    def test_new_file_factor_near_one(self):
        assert calculate_age_factor(_make_file(modified_days_ago=0)) == pytest.approx(1.0, abs=1e-3)

    def test_one_year_old_is_about_one_over_e(self):
        factor = calculate_age_factor(_make_file(modified_days_ago=365))
        assert factor == pytest.approx(math.exp(-1), rel=1e-3)

    def test_old_file_factor_decays(self):
        new = calculate_age_factor(_make_file(modified_days_ago=10))
        old = calculate_age_factor(_make_file(modified_days_ago=3650))
        assert old < new


class TestNormalizeCnRatio:
    def test_zero_clamped_to_min(self):
        assert normalize_cn_ratio(0) == 1

    def test_negative_clamped_to_min(self):
        assert normalize_cn_ratio(-42) == 1

    def test_above_max_log_clamped_to_max(self):
        assert normalize_cn_ratio(10_000) == 100

    def test_monotonic_growth(self):
        values = [normalize_cn_ratio(r, decimals=4) for r in [0.1, 1, 10, 100]]
        assert values == sorted(values)

    def test_decimals_argument_respected(self):
        assert normalize_cn_ratio(50, decimals=2) == round(normalize_cn_ratio(50, decimals=2), 2)


class TestCalculateBaseCn:
    def test_text_category_uses_word_count(self):
        f = _make_file(category="text", size=1000,
                       additional_data={"word_count": 100, "char_count": 500})
        carbon, nitrogen = calculate_base_cn(f)
        assert carbon > 0 and nitrogen > 0

    def test_image_with_zero_dimensions_falls_back_to_size(self):
        f = _make_file(category="image", size=2048,
                       additional_data={"dimensions": (0, 0), "dominant_colors": [], "quality": 1})
        carbon, _ = calculate_base_cn(f)
        assert carbon == 2048

    def test_brown_category_low_nitrogen(self):
        f = _make_file(category="system", size=5000)
        carbon, nitrogen = calculate_base_cn(f)
        assert carbon == 5000
        assert nitrogen == 0.1

    def test_unknown_category_default(self):
        f = _make_file(category="??", size=1024 * 1024)
        carbon, nitrogen = calculate_base_cn(f)
        assert carbon == 1.0
        assert nitrogen == 1


class TestCalculateCnRatio:
    def test_returns_expected_keys(self):
        result = calculate_cn_ratio(_make_file(category="text", size=200,
                                               additional_data={"word_count": 10, "char_count": 50}))
        assert set(result) == {"file_type", "carbon", "nitrogen", "raw_cn_ratio", "normalized_cn_ratio"}

    def test_classifies_brown_when_carbon_dominates(self):
        # Fichier system → brown au départ, carbone dominant → reste brown
        result = calculate_cn_ratio(_make_file(category="system", size=1_000_000))
        assert result["file_type"] == "brown"
        assert result["carbon"] > result["nitrogen"]

    def test_zero_nitrogen_yields_infinite_raw_ratio(self):
        # Force nitrogen=0 via une catégorie text avec char_count=0 → division par char_count
        # Plus simple : on monte un fichier brown avec age_factor proche de 0
        f = _make_file(category="system", size=100, modified_days_ago=100_000)
        result = calculate_cn_ratio(f)
        # nitrogen = 0.1 * age_factor ≈ 0 → raw_cn très grand
        assert result["raw_cn_ratio"] == float("inf") or result["raw_cn_ratio"] > 1e6
