# Contributing to Infinity Stumps

Thanks for your interest. This project is open by design — see
[`docs/about.md`](docs/about.md) for the why. Contributions are welcome.

## Repository layout

This is a monorepo with one directory per discipline:

- `simulation/` — the Python estimation + LBW pipeline (this is where
  Phase 0 work lives, and what most of this guide covers)
- `firmware/` — anchor and ball-tag firmware (C / nRF Connect SDK)
- `hardware/` — KiCad PCB projects and enclosure design
- `app/` — the mobile app (iOS first)
- `docs/` — system-level architecture, BOM, prior-art strategy

Each directory has its own README with the specifics.

## Setup (simulation)

Requires Python 3.10+. From the `simulation/` directory:

```bash
make install
```

This does an editable install with dev extras (pytest, ruff, mypy,
pre-commit) and installs the pre-commit hooks.

## The workflow

1. Branch off `main`.
2. Make your change.
3. Run the gate (from `simulation/`):
   ```bash
   make check        # lint + typecheck + test — must pass
   ```
4. Open a PR. CI runs the same gate across Python 3.10–3.12.

`make format` auto-fixes lint and formatting. The pre-commit hooks run
ruff on every commit, so most style issues never reach a PR.

## Tests

- Tests live in `simulation/tests/`, one file per `simulation/src/` module.
- Shared fixtures (a standard delivery, anchor layouts, a seeded RNG) are in
  `simulation/tests/conftest.py` — prefer them over rebuilding setup in each test.
- Anything noise-driven must use the seeded `rng` fixture so it is
  deterministic.
- New behaviour in `simulation/src/` needs a test. New physics or estimator
  code should be checked against an analytic result or a known-good reference
  where one exists.

## Style

- Ruff handles formatting and linting — don't hand-format.
- Public functions take type hints.
- Comments explain *why*, not *what*. The codebase favours short, specific
  comments over restating the code.
- Keep simulation scripts in `simulation/sims/` self-contained: each one
  runs standalone and writes its figure to `simulation/outputs/`.

## Decisions

This project values dated decisions and explicit reasoning. Architectural
choices — including the ones that *didn't* work — are recorded in `CLAUDE.md`
and `docs/findings.md`. For a substantial architectural change, open an issue
to discuss before building. For routine fixes, just open a PR.

## Hard rules

- **Never run a simulation above 100 Hz.** 100 Hz is the ETSI duty-cycle-
  compliant deployment rate (see `docs/airtime-budget.md`). Higher rates
  produce aspirational numbers that don't reflect the real system.
- Don't change the calibrated geometry constants in `geometry.py` or the
  cricket-ball physics constants in `physics.py` without a documented reason
  — downstream simulation results depend on them.

## Licence of contributions

By contributing you agree your contributions are licensed under the
project's licences: Apache-2.0 for software, CERN-OHL-S v2 for hardware
designs, CC-BY-4.0 for documentation.
