"""Create the custom-components directory required by a persistent test HA."""

from __future__ import annotations

from pathlib import Path
import shutil
import tempfile


REPO_ROOT = Path(__file__).parents[1]
destination = Path(tempfile.mkdtemp(prefix="approved-scripts-components-"))

shutil.copytree(
    REPO_ROOT / "custom_components" / "approved_scripts",
    destination / "approved_scripts",
)
shutil.copytree(
    REPO_ROOT / "tests" / "fixtures" / "custom_components" / "fake_mqtt",
    destination / "fake_mqtt",
)
shutil.copytree(
    REPO_ROOT / "tests" / "fixtures" / "custom_components" / "fake_zwave_js",
    destination / "fake_zwave_js",
)

print(destination)
