"""Run every simulation script in this directory, in name order."""

import subprocess
import sys
from pathlib import Path

sims_dir = Path(__file__).parent
scripts = sorted(p for p in sims_dir.glob("*.py") if p.name != "run_all.py")

for script in scripts:
    print(f"\n{'=' * 70}\nRunning {script.name}\n{'=' * 70}")
    result = subprocess.run([sys.executable, str(script)], cwd=sims_dir.parent)
    if result.returncode != 0:
        print(f"FAILED: {script.name}")
        sys.exit(result.returncode)

print(f"\nAll {len(scripts)} simulations complete. See outputs/")
