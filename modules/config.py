"""Chargement de la configuration centrale depuis config.toml.

Utilisation :
    from modules.config import CONFIG
    CONFIG.paths.output_root          # → Path('data/output')
    CONFIG.pipeline.target_cn_ratio   # → 30

Le module charge le fichier une seule fois à l'import. Si config.toml est
absent, des valeurs par défaut raisonnables sont utilisées (compatible avec
l'historique du projet).
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    default_input: Path
    usb_import: Path
    output_root: Path
    silos_dir: Path
    composted_dir: Path
    saliency_subdir: str
    log_file: Path


@dataclass(frozen=True)
class Pipeline:
    target_cn_ratio: float
    silo_size_limit: int
    input_size_warning_mb: float
    compost_time_limit: float
    include_hidden_files: bool


@dataclass(frozen=True)
class Hardware:
    force_simulation: bool
    epaper_min_refresh_seconds: float
    epaper_lib_path: Path
    circular_size: int
    fullscreen: bool
    printer_enabled: bool
    printer_vendor_id: int
    printer_columns: int


@dataclass(frozen=True)
class Usb:
    polling_interval: float


@dataclass(frozen=True)
class Config:
    paths: Paths
    pipeline: Pipeline
    usb: Usb
    hardware: Hardware


_DEFAULTS = {
    "paths": {
        "default_input": "data/test",
        "usb_import": "data/usb_import",
        "output_root": "data/output",
        "silos_subdir": "silos",
        "composted_subdir": "composted",
        "saliency_subdir": "saliency_maps",
        "log_file": "compost_process.log",
    },
    "pipeline": {
        "target_cn_ratio": 30,
        "silo_size_limit": 100 * 1024 * 1024,
        "input_size_warning_mb": 5000,
        "compost_time_limit": 55,
        "include_hidden_files": False,
    },
    "usb": {
        "polling_interval": 2.0,
    },
    "hardware": {
        "force_simulation": False,
        "epaper_min_refresh_seconds": 20,
        "epaper_lib_path": "~/e-Paper/RaspberryPi_JetsonNano/python/lib",
        "circular_size": 720,
        "fullscreen": False,
        "printer_enabled": True,
        "printer_vendor_id": 0x04B8,
        "printer_columns": 42,
    },
}


def _load(config_path: Path) -> Config:
    data = dict(_DEFAULTS)
    if config_path.exists():
        with open(config_path, "rb") as f:
            loaded = tomllib.load(f)
        for section, values in loaded.items():
            data[section] = {**data.get(section, {}), **values}

    p = data["paths"]
    output_root = Path(p["output_root"])
    paths = Paths(
        default_input=Path(p["default_input"]),
        usb_import=Path(p["usb_import"]),
        output_root=output_root,
        silos_dir=output_root / p["silos_subdir"],
        composted_dir=output_root / p["composted_subdir"],
        saliency_subdir=p["saliency_subdir"],
        log_file=Path(p["log_file"]),
    )
    pl = data["pipeline"]
    pipeline = Pipeline(
        target_cn_ratio=pl["target_cn_ratio"],
        silo_size_limit=pl["silo_size_limit"],
        input_size_warning_mb=pl["input_size_warning_mb"],
        compost_time_limit=pl["compost_time_limit"],
        include_hidden_files=pl["include_hidden_files"],
    )
    u = data["usb"]
    usb = Usb(polling_interval=u["polling_interval"])
    h = data["hardware"]
    hardware = Hardware(
        force_simulation=bool(h["force_simulation"]),
        epaper_min_refresh_seconds=float(h["epaper_min_refresh_seconds"]),
        # expanduser : le chemin par défaut vise le dossier de l'utilisateur du Pi
        epaper_lib_path=Path(h["epaper_lib_path"]).expanduser(),
        circular_size=int(h["circular_size"]),
        fullscreen=bool(h["fullscreen"]),
        printer_enabled=bool(h["printer_enabled"]),
        printer_vendor_id=int(h["printer_vendor_id"]),
        printer_columns=int(h["printer_columns"]),
    )
    return Config(paths=paths, pipeline=pipeline, usb=usb, hardware=hardware)


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG = _load(_PROJECT_ROOT / "config.toml")
