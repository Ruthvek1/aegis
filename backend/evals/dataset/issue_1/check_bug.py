"""Stdlib-only bug checker for the seed repo.

Runs fully offline inside the locked-down sandbox (no pytest, no network).
Exit 0 (green) if divide() correctly raises ValueError on divide-by-zero
(i.e. the bug is fixed); exit 1 (red) otherwise.

Run as: python -B seed_repo/check_bug.py   (working dir = /workspace)
The script's own directory is on sys.path[0], so `import math_lib` resolves.
"""

import sys

from math_lib import divide

try:
    divide(6, 0)
except ValueError:
    # Fixed: divide-by-zero raises the documented ValueError.
    sys.exit(0)
except Exception:
    # Bug still present (e.g. ZeroDivisionError) or wrong exception type.
    sys.exit(1)

# No exception raised at all -> also wrong.
sys.exit(1)
