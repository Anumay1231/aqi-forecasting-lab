"""Project-wide configuration: paths, cities, chronological splits."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "data" / "raw" / "AllIndiaBulletinsMaster2025_openrefined.csv"
PROCESSED_DIR = ROOT / "data" / "processed"
ARTIFACTS = ROOT / "artifacts"
FIGURES = ARTIFACTS / "figures"

SOURCE = {
    "name": "CPCB National AQI daily bulletins (parsed by UrbanEmissions.info)",
    "repo": "https://github.com/urbanemissionsinfo/AQI_bulletins",
    "file": "data/Processed/AllIndiaBulletinsMaster2025_openrefined.csv",
    "original": "https://cpcb.nic.in/AQI_Bulletin.php",
    "license": "GPL-3.0 (repository); underlying bulletins are public CPCB releases",
}

# Modelling window starts when each city's monitoring network stabilised
# (Mumbai: 1 station through 2018, 7+ from 2019; Delhi: 28+ from 2018).
CITIES = {
    "Mumbai": {"model_start": "2019-01-01"},
    "Delhi": {"model_start": "2018-01-01"},
}
PRIMARY_CITY = "Mumbai"

TRAIN_END = "2023-12-31"   # fit + order selection
VAL_END = "2024-12-31"     # model selection on 2024
TEST_END = "2025-12-31"    # final untouched evaluation on 2025
HORIZONS = [1, 3, 7]
MAX_H = 7

# CPCB National AQI bands
AQI_BANDS = [
    (0, 50, "Good", "#2e9d5b"),
    (51, 100, "Satisfactory", "#8cc152"),
    (101, 200, "Moderate", "#e8c547"),
    (201, 300, "Poor", "#ee8a3c"),
    (301, 400, "Very Poor", "#d9453d"),
    (401, 500, "Severe", "#8e2430"),
]


def aqi_category(v: float) -> str:
    for lo, hi, name, _ in AQI_BANDS:
        if v <= hi:
            return name
    return "Severe"


def city_slug(city: str) -> str:
    return city.lower().replace(" ", "_")
