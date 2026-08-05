# Plan — Commit the git-activity Generator

## Objective

Persist the `git-activity` backdated-commit generator into the repo so the gradient (and any future patterns) is reproducible. After this plan, the repo has `scripts/`, `tests/`, `pyproject.toml`, `requirements.txt`, `.gitignore`, `RESEARCH.md`, and `PLAN.md` all tracked in git.

## End-state definition

**Done** when:
1. `git ls-files` shows the scaffolding files (`scripts/`, `tests/`, `pyproject.toml`, `requirements.txt`, `.gitignore`, `RESEARCH.md`, `PLAN.md`) as tracked.
2. `python3 -m pytest tests/ -v` runs all 22 tests and they pass.
3. The CLI runs in dry-run mode (no `--apply`) and produces a sane preview.
4. The README still points at the contribution graph.
5. The repo's 2,372 existing gradient commits are untouched (no rebase, no history rewrite).

## Pre-conditions

- Repo is on `main`, fully synced with `origin/main` (no unpushed, no unpulled).
- `git config user.email` is `165743429+kleinpanic@users.noreply.github.com` (the noreply email).
- `commit.gpgsign=false` is set so backdated commits do not require GPG signing.

## Steps (TDD order)

1. **Verify the existing scaffolding works.** Run `python3 -m pytest tests/ -v` and confirm 22 tests pass. This is the "check before the code" step — the tests already exist from a prior session and they pass.
2. **Run the CLI in dry-run mode** to verify the entry point works end-to-end.
3. **Write `RESEARCH.md`** explaining the design (3 modes, 5x7 bitmap font, per-day cap, salt for SHA uniqueness, why the historical `c_*.txt` files stay).
4. **Write `PLAN.md`** (this file) documenting the work.
5. **Commit in this order** (so the verification leads the source, per AGENTS.md):
   - commit 1: tooling (`.gitignore`, `pyproject.toml`, `requirements.txt`)
   - commit 2: helpers (`scripts/_commits.py`, `scripts/font_5x7.py`)
   - commit 3: tests (`tests/test_gradient.py`, `tests/test_text.py`, `tests/test_draw.py`)
   - commit 4: CLI entry point (`scripts/generate_gradient.py`)
   - commit 5: research note (`RESEARCH.md`)
   - commit 6: plan (`PLAN.md`)
6. **Sync to origin** with `git push origin main`.

## Risks

- **Push policy.** Public repo `kleinpanic/git-activity`. The new commits are documentation + python source only — they touch no existing commits and create no backdated commits. Pushing is safe.
- **History rewrite.** None planned. The 2,372 existing gradient commits stay.
- **Re-running the gradient.** Not in scope. The CLI defaults to dry-run; `--apply` is opt-in.

## What was *not* done

- No CI workflow.
- No release tag.
- No PyPI package. The pyproject.toml `[project.scripts]` entry is enough for `pip install -e .` to make the CLI work locally.
- No re-validation of the existing 2,372 commits.

## Verification

| Check | Command | Expected |
|---|---|---|
| Tests pass | `python3 -m pytest tests/ -v` | 22 passed |
| CLI dry-run | `python3 scripts/generate_gradient.py --mode gradient --start 2024-01-01 --end 2024-01-05` | 32 commits, 5-day preview |
| CLI text mode | `python3 scripts/generate_gradient.py --mode text --text "KLEIN" --start 2026-07-11 --end 2026-08-04` | 71 commits, 29-day preview |
| Tracked files | `git ls-files scripts/ tests/ pyproject.toml requirements.txt .gitignore` | paths listed |
| Synced | `git status` | clean working tree, in sync with origin/main |
| Existing commits | `git rev-list --count HEAD` | 2373 (unchanged) + 6 new commits after push |

## Executed

Steps 1-5 above. Step 6 (push) is left to the user to perform; the local commits are in place.
