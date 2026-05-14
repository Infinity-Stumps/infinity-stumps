"""Run all simulations."""
import subprocess, sys
from pathlib import Path

sims_dir = Path(__file__).parent
scripts = sorted(p for p in sims_dir.glob("[0-9]*.py")
                 if p.name != "run_all.py")
for script in scripts:
    print(f"\n{'='*70}\nRunning {script.name}\n{'='*70}")
    r = subprocess.run([sys.executable, str(script)], cwd=sims_dir.parent)
    if r.returncode != 0:
        print(f"FAILED: {script.name}")
        sys.exit(r.returncode)
print(f"\nAll {len(scripts)} simulations complete. See outputs/")
