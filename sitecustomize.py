from __future__ import annotations

import os
import sys
from pathlib import Path


if Path(sys.argv[0]).name.startswith("pytest"):
    os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
