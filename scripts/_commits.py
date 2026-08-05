"""Shared commit helpers for the contribution-graph generator.

Every mode (gradient, text, draw) eventually produces a mapping of
`date -> commit_count`, and we materialize that into backdated commits
the same way regardless of which mode produced it. This module owns the
materialization so the mode logic can stay mode-specific.
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime

# Identity used for every generated commit. The noreply email is linked to
# the GitHub account so the commits count toward the profile graph.
EMAIL = "165743429+kleinpanic@users.noreply.github.com"
NAME = "kleinpanic"


@dataclass(frozen=True)
class Plan:
    """A materialized plan: `date -> number of commits to create`."""

    counts: dict[date, int]
    start: date
    end: date

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def run_git(args: list[str], cwd: str, env: dict | None = None) -> str:
    """Run a git command, raise on failure with stderr attached."""
    r = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (rc={r.returncode}): {r.stderr.strip()}"
        )
    return r.stdout.strip()


def commit_one(
    *,
    repo: str,
    when: datetime,
    label: str,
    salt: str,
    message: str,
    apply: bool,
    payload: str,
) -> None:
    """Create one backdated commit.

    The commit content is written as a scratch file inside the repo so each
    commit has a unique SHA. `payload` is the file body; `salt` is included
    in the body (and embedded in the filename) to guarantee uniqueness even
    if the same logical commit is requested twice.
    """
    iso = when.strftime("%Y-%m-%dT%H:%M:%S")
    fname = f"c_{when.strftime('%Y%m%d_%H%M%S')}_{label}_{salt}.txt"
    path = os.path.join(repo, fname)
    if apply:
        with open(path, "w") as f:
            f.write(f"{payload}\nsalt={salt}\n")
        env = os.environ.copy()
        env.update({
            "GIT_AUTHOR_DATE": iso,
            "GIT_COMMITTER_DATE": iso,
        })
        run_git(
            [
                "git", "-c", f"user.name={NAME}", "-c", f"user.email={EMAIL}",
                "-c", "commit.gpgsign=false",
                "add", fname,
            ],
            cwd=repo,
        )
        run_git(
            [
                "git", "-c", f"user.name={NAME}", "-c", f"user.email={EMAIL}",
                "-c", "commit.gpgsign=false",
                "commit", "-m", message,
            ],
            cwd=repo,
            env=env,
        )
    else:
        print(f"  [dry-run] {iso}  {label}  '{message}'  -> {fname}")


def materialize(plan: Plan, *, repo: str, apply: bool, prefix: str) -> None:
    """Turn a Plan into actual commits (or dry-run printouts)."""
    if not apply:
        print(f"DRY-RUN: would create {plan.total} commits across {plan.days} days")
        print(f"  range: {plan.start} .. {plan.end}")
        print("  per-day cap in effect: ruled by Plan.counts")
        # Show a 5-row sample of the plan
        sample = sorted(plan.counts.items())[:5]
        for d, n in sample:
            print(f"  {d} -> {n} commit(s)")
        if len(plan.counts) > 5:
            print(f"  ... and {len(plan.counts) - 5} more days")
        return

    if not plan.counts:
        print("Plan is empty — nothing to materialize.", file=sys.stderr)
        return

    for d in sorted(plan.counts):
        n = plan.counts[d]
        for j in range(n):
            commit_one(
                repo=repo,
                when=datetime.combine(d, datetime.min.time()).replace(hour=12),
                label=prefix,
                salt=os.urandom(8).hex(),
                message=f"{prefix} {d.isoformat()} {j}",
                apply=True,
                payload=f"{prefix} {d.isoformat()} idx={j}",
            )
    print(f"DONE: {plan.total} commits across {plan.days} days "
          f"({plan.start} .. {plan.end})")


def cap_counts(
    counts: dict[date, int],
    *,
    max_per_day: int,
) -> dict[date, int]:
    """Clamp every per-day count to `max_per_day`. Counts <= 0 are dropped."""
    return {d: min(n, max_per_day) for d, n in counts.items() if n > 0}
