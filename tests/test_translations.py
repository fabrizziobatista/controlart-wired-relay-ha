"""Tests for Controlart translation catalogs."""

import json
from pathlib import Path

import pytest


INTEGRATION_DIR = Path(__file__).parents[1]
OPTIONS_FIELDS = {
    "host",
    "port",
    "scan_interval",
    "interlock_pairs",
    "interlock_delay_ms",
}


@pytest.mark.parametrize("language", ["en", "pt-BR"])
def test_options_flow_translations_are_complete(language: str) -> None:
    """Each runtime catalog contains labels for every options field."""
    translation_file = INTEGRATION_DIR / "translations" / f"{language}.json"
    translations = json.loads(translation_file.read_text(encoding="utf-8"))

    step = translations["options"]["step"]["init"]
    assert step["title"]
    assert step["description"]
    assert set(step["data"]) == OPTIONS_FIELDS
    assert all(step["data"][field] != field for field in OPTIONS_FIELDS)


@pytest.mark.parametrize("language", ["en", "pt-BR"])
def test_runtime_catalog_has_all_string_keys(language: str) -> None:
    """Runtime custom-integration catalogs mirror the complete strings tree."""
    source = json.loads(
        (INTEGRATION_DIR / "strings.json").read_text(encoding="utf-8")
    )
    translated = json.loads(
        (
            INTEGRATION_DIR / "translations" / f"{language}.json"
        ).read_text(encoding="utf-8")
    )

    assert _leaf_paths(translated) == _leaf_paths(source)


def _leaf_paths(value: object, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    """Return every scalar JSON path."""
    if not isinstance(value, dict):
        return {prefix}
    return {
        path
        for key, child in value.items()
        for path in _leaf_paths(child, (*prefix, key))
    }
