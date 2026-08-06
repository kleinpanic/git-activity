"""Tests for backdated commit materialization.

These tests verify the git-commit path end-to-end: every commit in a
Plan is actually created, dates land on the right day, the author
identity is correct, and SHAs are unique. They run against a fresh
temporary git repo so they're not coupled to the repo's existing
history.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from _commits import EMAIL, NAME, Plan, commit_one, materialize

# ── helpers ─────────────────────────────────────────────────────────


def _git(*args: str, cwd: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return r.stdout.strip()


def _init_repo(path: str) -> None:
    """Init a git repo at `path` with a single empty init commit.

    Matches what the README instructs users to do before running the
    generator: `git init && git commit --allow-empty -m init`.
    """
    os.makedirs(path, exist_ok=True)
    _git("init", "-q", "-b", "main", cwd=path)
    _git("config", "user.email", EMAIL, cwd=path)
    _git("config", "user.name", NAME, cwd=path)
    _git("config", "commit.gpgsign", "false", cwd=path)
    _git("commit", "--allow-empty", "-q", "-m", "init", cwd=path)


def _plan_range(start: str, end: str, per_day: int) -> Plan:
    """Build a small Plan where every day in [start, end] gets `per_day` commits."""
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    days = (e - s).days + 1
    return Plan(
        counts={s + timedelta(days=i): per_day for i in range(days)},
        start=s,
        end=e,
    )


# ── materialize end-to-end tests ────────────────────────────────────


def test_materialize_creates_expected_commit_count(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-01", "2024-06-05", per_day=3)  # 5 days * 3 = 15
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    n = int(_git("rev-list", "--count", "HEAD", cwd=repo))
    # 1 init + 15 new = 16
    assert n == 16


def test_materialize_sets_author_date_to_target_day(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-01", "2024-06-03", per_day=2)
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    # Default git log is newest-first. The init commit is at the END
    # of that list, so skip the last line.
    out = _git("log", "--format=%ai", cwd=repo)
    lines = out.splitlines()
    assert len(lines) == 7  # 1 init + 6 backdated
    dates = sorted(line.split()[0] for line in lines[:-1])
    assert dates == [
        "2024-06-01", "2024-06-01",
        "2024-06-02", "2024-06-02",
        "2024-06-03", "2024-06-03",
    ]


def test_materialize_sets_committer_date_to_target_day(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-01", "2024-06-02", per_day=1)
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    # Skip the init commit (last in newest-first default log).
    out = _git("log", "--format=%ci", cwd=repo)
    lines = out.splitlines()
    assert len(lines) == 3  # 1 init + 2 backdated
    dates = sorted(line.split()[0] for line in lines[:-1])
    assert dates == ["2024-06-01", "2024-06-02"]


def test_materialize_uses_noreply_author_email(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-10", "2024-06-10", per_day=2)
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    out = _git("log", "--format=%ae", "--skip=1", cwd=repo)
    assert all(line == EMAIL for line in out.splitlines())


def test_materialize_uses_correct_author_name(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-10", "2024-06-10", per_day=1)
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    out = _git("log", "--format=%an", "--skip=1", cwd=repo)
    assert all(line == NAME for line in out.splitlines())


def test_materialize_creates_unique_shas(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-15", "2024-06-15", per_day=5)
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    out = _git("log", "--format=%H", "--skip=1", cwd=repo)
    shas = out.splitlines()
    assert len(shas) == 5
    assert len(set(shas)) == 5  # all unique


def test_materialize_writes_payload_file_with_salt(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-07-01", "2024-07-01", per_day=1)
    materialize(plan, repo=repo, apply=True, prefix="draw")
    # Find the new file (any c_*.txt that wasn't there before).
    files = sorted(os.listdir(repo))
    payload_files = [f for f in files if f.startswith("c_") and f.endswith(".txt")]
    assert len(payload_files) == 1
    body = (Path(repo) / payload_files[0]).read_text()
    assert body.startswith("draw 2024-07-01 idx=0\n")
    assert "salt=" in body


def test_materialize_empty_plan_is_noop(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = Plan(counts={}, start=date(2024, 1, 1), end=date(2024, 1, 1))
    materialize(plan, repo=repo, apply=True, prefix="gradient")
    n = int(_git("rev-list", "--count", "HEAD", cwd=repo))
    assert n == 1  # only the init commit


def test_materialize_dry_run_creates_no_commits(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    plan = _plan_range("2024-06-01", "2024-06-05", per_day=2)
    materialize(plan, repo=repo, apply=False, prefix="gradient")
    n = int(_git("rev-list", "--count", "HEAD", cwd=repo))
    assert n == 1  # only the init commit


# ── commit_one unit test ───────────────────────────────────────────


def test_commit_one_when_apply_false_writes_nothing(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    files_before = set(os.listdir(repo))
    commit_one(
        repo=repo,
        when=datetime(2024, 8, 1, 12, 0, 0),
        label="gradient",
        salt="deadbeef" * 2,  # 16 hex chars, no slashes
        message="gradient 2024-08-01 0",
        apply=False,
        payload="gradient 2024-08-01 idx=0",
    )
    files_after = set(os.listdir(repo))
    assert files_before == files_after


def test_commit_one_writes_unique_files_per_salt(tmp_path):
    repo = str(tmp_path / "repo")
    _init_repo(repo)
    # Two commits on the same day, same time — only `salt` differentiates.
    commit_one(
        repo=repo,
        when=datetime(2024, 8, 1, 12, 0, 0),
        label="gradient",
        salt="salt_a",
        message="gradient 2024-08-01 0",
        apply=True,
        payload="gradient 2024-08-01 idx=0",
    )
    commit_one(
        repo=repo,
        when=datetime(2024, 8, 1, 12, 0, 0),
        label="gradient",
        salt="salt_b",
        message="gradient 2024-08-01 1",
        apply=True,
        payload="gradient 2024-08-01 idx=1",
    )
    files = [f for f in os.listdir(repo) if f.startswith("c_")]
    assert len(files) == 2
    assert len(set(files)) == 2