"""Runtime test configuration using the same ha-testcontainer shape as UIX."""

from __future__ import annotations

import atexit
import os
from pathlib import Path
import shutil
import tempfile


REPO_ROOT = Path(__file__).parent.parent
TESTS_ROOT = REPO_ROOT / "tests"
_COMPONENTS_ROOT = Path(tempfile.mkdtemp(prefix="approved-scripts-components-"))


def _default_ha_version() -> str:
    for line in (TESTS_ROOT / "HA_VERSION").read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value
    return "stable"


# The test-only fake MQTT integration makes successful delegated execution
# observable without requiring a network broker. It is copied beside the real
# custom integration only in the disposable HA test container.
shutil.copytree(
    REPO_ROOT / "custom_components" / "approved_scripts",
    _COMPONENTS_ROOT / "approved_scripts",
)
shutil.copytree(
    TESTS_ROOT / "fixtures" / "custom_components" / "fake_mqtt",
    _COMPONENTS_ROOT / "fake_mqtt",
)
shutil.copytree(
    TESTS_ROOT / "fixtures" / "custom_components" / "fake_zwave_js",
    _COMPONENTS_ROOT / "fake_zwave_js",
)
atexit.register(shutil.rmtree, _COMPONENTS_ROOT, ignore_errors=True)

os.environ.setdefault("HA_VERSION", _default_ha_version())
os.environ.setdefault("HA_CONFIG_PATH", str(TESTS_ROOT / "ha-config"))
os.environ["HA_CUSTOM_COMPONENTS_PATH"] = str(_COMPONENTS_ROOT)
os.environ.setdefault("HA_SETUP_INTEGRATION", "approved_scripts")
