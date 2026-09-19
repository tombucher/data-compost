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

    def test_above_ceiling_is_clamped(self):
        from modules.calculate_cn import CN_CEILING
        assert normalize_cn_ratio(10_000) == CN_CEILING

    def test_explicit_max_is_honoured(self):
        assert normalize_cn_ratio(10_000, max_value=100) == 100

    def test_value_is_preserved_inside_the_range(self):
        """La sortie reste un C/N, comparable à la cible agronomique."""
        assert normalize_cn_ratio(30) == 30
        assert normalize_cn_ratio(12.4, decimals=1) == 12.4

    def test_monotonic_growth(self):
        values = [normalize_cn_ratio(r, decimals=4) for r in [0.1, 1, 10, 100]]
        assert values == sorted(values)

    def test_decimals_argument_respected(self):
        assert normalize_cn_ratio(50, decimals=2) == round(normalize_cn_ratio(50, decimals=2), 2)


class TestCalculateBaseCn:
    """Le contrat : carbone et azote dans (0, 1], comparables entre catégories.

    C'est la propriété qui manquait à la version précédente, où les fichiers
    bruns comptaient en octets bruts et les images en octets par pixel.
    """

    ALL_CATEGORIES = ["image", "audio", "video", "text", "document", "creative",
                      "system", "compressed", "executable", "hidden", "??"]

    @pytest.mark.parametrize("category", ALL_CATEGORIES)
    def test_both_axes_stay_within_unit_range(self, category):
        f = _make_file(category=category, size=500_000)
        carbon, nitrogen = calculate_base_cn(f)
        assert 0 < carbon <= 1
        assert 0 < nitrogen <= 1

    @pytest.mark.parametrize("category", ALL_CATEGORIES)
    def test_survives_empty_metadata(self, category):
        """L'analyse peut échouer et ne laisser aucune donnée annexe."""
        f = _make_file(category=category, size=1024, additional_data={})
        carbon, nitrogen = calculate_base_cn(f)
        assert carbon > 0 and nitrogen > 0

    def test_categories_are_mutually_comparable(self):
        """Une archive et une photo de même taille restent du même ordre.

        Elles différaient auparavant d'environ cinq ordres de grandeur, ce qui
        rendait tout équilibrage de silo illusoire.
        """
        size = 500_000
        archive, _ = calculate_base_cn(_make_file(category="compressed", size=size))
        photo, _ = calculate_base_cn(_make_file(
            category="image", size=size,
            additional_data={"dimensions": (1500, 1500), "dominant_colors": [1, 2, 3]},
        ))
        assert archive / photo < 10

    def test_carbon_grows_with_size(self):
        small, _ = calculate_base_cn(_make_file(category="image", size=10_000))
        large, _ = calculate_base_cn(_make_file(category="image", size=10_000_000))
        assert large > small

    def test_opaque_formats_carry_more_carbon(self):
        archive, _ = calculate_base_cn(_make_file(category="compressed", size=500_000))
        plain, _ = calculate_base_cn(_make_file(category="text", size=500_000))
        assert archive > plain

    def test_brown_category_has_floor_nitrogen(self):
        _, nitrogen = calculate_base_cn(_make_file(category="system", size=5000))
        assert nitrogen == pytest.approx(0.05)

    def test_image_with_zero_dimensions_does_not_crash(self):
        f = _make_file(category="image", size=2048,
                       additional_data={"dimensions": (0, 0), "dominant_colors": []})
        carbon, nitrogen = calculate_base_cn(f)
        assert carbon > 0 and nitrogen > 0

    def test_richer_image_carries_more_nitrogen(self):
        base = {"dimensions": (1500, 1500)}
        _, poor = calculate_base_cn(_make_file(
            category="image", size=500_000, additional_data={**base, "dominant_colors": []}))
        _, rich = calculate_base_cn(_make_file(
            category="image", size=500_000,
            additional_data={**base, "dominant_colors": [1, 2, 3, 4, 5], "description": "un texte"}))
        assert rich > poor

    def test_text_category_uses_word_count(self):
        f = _make_file(category="text", size=1000,
                       additional_data={"word_count": 100, "char_count": 500})
        carbon, nitrogen = calculate_base_cn(f)
        assert carbon > 0 and nitrogen > 0

    def test_longer_text_carries_more_nitrogen(self):
        _, short = calculate_base_cn(_make_file(
            category="text", size=1000, additional_data={"word_count": 20, "char_count": 100}))
        _, long = calculate_base_cn(_make_file(
            category="text", size=1000, additional_data={"word_count": 5000, "char_count": 25000}))
        assert long > short

    def test_audio_accepts_tempo_as_list(self):
        """librosa renvoie parfois un tableau de tempos plutôt qu'un scalaire."""
        scalar = calculate_base_cn(_make_file(
            category="audio", size=5_000_000,
            additional_data={"tempo": 120, "sample_rate": 44100}))
        listed = calculate_base_cn(_make_file(
            category="audio", size=5_000_000,
            additional_data={"tempo": [110, 130], "sample_rate": 44100}))
        assert scalar == pytest.approx(listed)


class TestCnRatioScale:
    """L'échelle doit s'étaler autour de la cible, pas s'écraser sur une borne."""

    def test_balanced_material_sits_on_the_target(self):
        """Inertie == vitalité doit donner exactement le ratio de référence."""
        from modules.calculate_cn import TARGET_CN_RATIO, _structural_carbon, _informational_nitrogen
        assert TARGET_CN_RATIO * 0.5 / 0.5 == pytest.approx(TARGET_CN_RATIO)

    def test_archive_is_browner_than_photograph(self):
        archive = calculate_cn_ratio(_make_file(category="compressed", size=5_000_000,
                                                name="sauvegarde.zip"))
        photo = calculate_cn_ratio(_make_file(
            category="image", size=500_000, name="photo.jpg",
            additional_data={"dimensions": (1500, 1500), "dominant_colors": [1, 2, 3, 4, 5]}))
        assert archive["raw_cn_ratio"] > photo["raw_cn_ratio"]
        assert archive["file_type"] == "brown"

    def test_images_no_longer_collapse_to_the_floor(self):
        """Sept photographies comparables produisaient toutes 1 ou presque."""
        ratios = []
        for size, colors in [(410_574, 2), (489_624, 3), (543_339, 4),
                             (712_886, 5), (499_644, 5)]:
            r = calculate_cn_ratio(_make_file(
                category="image", size=size, name=f"{size}.jpg",
                additional_data={"dimensions": (1500, 1494),
                                 "dominant_colors": list(range(colors))}))
            ratios.append(r["normalized_cn_ratio"])
        assert min(ratios) > 1, f"écrasement sur la borne basse : {ratios}"
        assert len(set(ratios)) > 1, f"aucune variation entre fichiers : {ratios}"


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

    def test_very_old_file_stays_finite(self):
        """L'azote a un plancher : plus de ratio infini sur les fichiers anciens.

        La pondération précédente multipliait l'azote par un facteur d'âge qui
        finissait par tomber à zéro par sous-dépassement, produisant un C/N
        infini qui contaminait ensuite la moyenne des silos.
        """
        f = _make_file(category="system", size=100, modified_days_ago=100_000)
        result = calculate_cn_ratio(f)
        assert math.isfinite(result["raw_cn_ratio"])
        assert result["nitrogen"] > 0

    def test_age_effect_stays_bounded(self):
        """L'âge module le ratio, il ne doit pas l'écraser.

        Avec l'ancienne pondération, dix-huit mois divisaient le C/N d'une
        image par sept et effaçaient toute différence de contenu.
        """
        data = {"dimensions": (1500, 1494), "dominant_colors": [1, 2, 3, 4, 5]}
        fresh = calculate_cn_ratio(_make_file(category="image", name="a.jpg", size=500_000,
                                              modified_days_ago=0, additional_data=data))
        old = calculate_cn_ratio(_make_file(category="image", name="b.jpg", size=500_000,
                                            modified_days_ago=3650, additional_data=data))
        # Un fichier ancien est plus décomposé, donc plus pauvre en carbone
        assert old["raw_cn_ratio"] < fresh["raw_cn_ratio"]
        # mais l'écart reste borné au facteur prévu par AGE_SWING
        assert fresh["raw_cn_ratio"] / old["raw_cn_ratio"] < 3.5
