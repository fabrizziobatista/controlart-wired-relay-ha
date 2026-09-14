"""Fixtures for Controlart Wired Relay tests."""

import os
from pathlib import Path
import sys
import tempfile

import pytest


INTEGRATION_DIR = Path(__file__).parents[1]


def _expose_flat_layout_as_custom_component() -> None:
    """Load flat repository sources from a path HA recognizes as an integration."""
    test_root = Path(tempfile.mkdtemp())
    components_dir = test_root / "custom_components"
    components_dir.mkdir()
    os.symlink(
        INTEGRATION_DIR,
        components_dir / "controlart_wired_relay",
        target_is_directory=True,
    )
    sys.path.insert(0, str(test_root))


_expose_flat_layout_as_custom_component()


pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading the integration from custom_components in every test."""
    yield
