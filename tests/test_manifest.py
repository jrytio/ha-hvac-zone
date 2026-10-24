"""Manifest, HACS metadata and translations agree with the code."""

import json
from pathlib import Path

from custom_components.hvac_zone.const import DOMAIN
from custom_components.hvac_zone.lib import NUMBER_SPECS, TIME_KEYS

ROOT = Path(__file__).parent.parent
PACKAGE = ROOT / "custom_components" / DOMAIN


def test_manifest():
    manifest = json.loads((PACKAGE / "manifest.json").read_text())
    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["version"]


def test_every_setting_has_a_name():
    entity = json.loads((PACKAGE / "translations" / "en.json").read_text())["entity"]
    assert set(entity["number"]) == {spec.key for spec in NUMBER_SPECS}
    assert set(entity["time"]) == set(TIME_KEYS)
