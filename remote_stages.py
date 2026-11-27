"""Remote render stages: an outside runner (the Company's Mac render worker) may take a waiting
motion-capture or final-render stage, run it with this same app version, and hand back the stage folder.

Nothing here runs unless a runner asks for work (POST /v1/remote/claim). With no live runner the
service behaves exactly as before: one local worker, two active jobs. A stage the runner does not take,
gives back, or stops reporting on goes back to this box's own worker, so a Short always renders.

The runner never writes into a project directly: DeFleur builds the input bundle itself, and checks
the returned folder (flat files, allowed kinds, every SHA-256 and size against result.json, same
stage, same app version, same source and plan hashes) before the job becomes needs_review. The result
then sits in the same project and job as a local render, so callers read it unchanged.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import tarfile
import threading
import time

REMOTE_STAGES = frozenset({"motion-capture", "final-render"})
LIVE_S = 20            # a runner that has not asked for work for this long is not available
SILENT_S = 300         # a taken stage without a heartbeat for this long goes back to this box
MAX_SLOTS = 4
MAX_RESULT = 8 * 1024 ** 3
RUNNER = re.compile(r"^[a-z0-9][a-z0-9-]{0,31}$")
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .'()-]{0,39}$")
ARTIFACT = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
SUFFIXES = {".json", ".wav", ".png", ".mp4"}
FORMAT = "defleur-remote-stage/1"
SCHEMA = """
CREATE TABLE IF NOT EXISTS remote_jobs(job TEXT PRIMARY KEY, runner TEXT NOT NULL, label TEXT NOT NULL,
  claimed REAL NOT NULL, heartbeat REAL NOT NULL, state TEXT NOT NULL, note TEXT);
UPDATE remote_jobs SET state='returned', note='app restarted' WHERE state='running';
"""


from editing import Rejected  # noqa: E402  (the service maps it to HTTP 422)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def stage_of(plan: str | dict) -> str | None:
    value = json.loads(plan) if isinstance(plan, str) else plan
    return value.get("workflow_stage") if isinstance(value, dict) else None


class Registry:
    """Live runners (in memory: a restart fails every running job anyway)."""

    def __init__(self):
        self.lock = threading.Lock()
        self.runners: dict[str, dict] = {}

    def seen(self, runner: str, label: str, slots: int, arch: str):
        with self.lock:
            self.runners[runner] = {"runner": runner, "label": label, "slots": slots, "arch": arch, "seen": time.time()}

    def gone(self, runner: str):
        with self.lock:
            self.runners.pop(runner, None)

    def live(self) -> list[dict]:
        now = time.time()
        with self.lock:
            return [dict(r) for r in self.runners.values() if now - r["seen"] <= LIVE_S]

    def slots(self) -> int:
        return sum(r["slots"] for r in self.live())


def queue_full(c, registry: Registry, stage: str | None) -> bool:
    """The old rule (two active jobs) unless a runner is live; then remote stages and the local
    stages of parallel Shorts each get room for the runner's slots."""
    active = [stage_of(r[0]) for r in c.execute("SELECT plan FROM jobs WHERE state IN ('queued','running')").fetchall()]
    slots = registry.slots()
    if not slots:
        return len(active) >= 2
    remote = sum(1 for s in active if s in REMOTE_STAGES)
    if stage in REMOTE_STAGES:
        return remote >= slots + 2
    return len(active) - remote >= 2 + slots


def next_local(c, registry: Registry):
    """The oldest queued job this box's worker may run: remote stages wait for a live runner unless given back."""
    rows = c.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created").fetchall()
    if not rows:
        return None
    if not registry.live():
        return rows[0]
    returned = {r[0] for r in c.execute("SELECT job FROM remote_jobs WHERE state IN ('returned','failed')").fetchall()}
    for row in rows:
        if stage_of(row["plan"]) not in REMOTE_STAGES or row["id"] in returned:
            return row
    return None


def reap(c, now: float | None = None) -> int:
    """Taken stages whose runner went silent go back to this box's worker."""
    now = time.time() if now is None else now
    stale = [r[0] for r in c.execute("SELECT job FROM remote_jobs WHERE state='running' AND heartbeat < ?",
                                      (now - SILENT_S,)).fetchall()]
    for jid in stale:
        c.execute("UPDATE remote_jobs SET state='returned', note='the render worker stopped reporting' WHERE job=?", (jid,))
        c.execute("UPDATE jobs SET state='queued' WHERE id=? AND state='running'", (jid,))
    return len(stale)


def runner_info(value) -> dict:
    if not isinstance(value, dict) or set(value) - {"runner", "label", "version", "arch", "slots", "free_slots"}:
        raise Rejected("claim body is {runner, label, version, arch, slots, free_slots}")
    runner, label = value.get("runner"), value.get("label", "the render worker")
    if not isinstance(runner, str) or not RUNNER.fullmatch(runner):
        raise Rejected("runner must be a short lowercase name")
    if not isinstance(label, str) or not LABEL.fullmatch(label):
        raise Rejected("label must be a short plain name")
    slots, free = value.get("slots"), value.get("free_slots", value.get("slots"))
    if not all(isinstance(n, int) and not isinstance(n, bool) for n in (slots, free)) or not 1 <= slots <= MAX_SLOTS or not 0 <= free <= slots:
        raise Rejected(f"slots must be 1..{MAX_SLOTS} and free_slots 0..slots")
    arch = value.get("arch")
    if not isinstance(arch, str) or not re.fullmatch(r"[a-z0-9_]{1,16}", arch):
        raise Rejected("arch is required (for example arm64)")
    if not isinstance(value.get("version"), str):
        raise Rejected("version is required")
    return {"runner": runner, "label": label, "version": value["version"], "arch": arch, "slots": slots, "free": free}


def claim_row(c, jid: str, runner: str) -> dict:
    row = c.execute("SELECT * FROM remote_jobs WHERE job=?", (jid,)).fetchone()
    if row is None or row["runner"] != runner or row["state"] != "running":
        raise Rejected("this stage is not taken by this runner")
    return dict(row)


def references(value, ident) -> list[str]:
    """Every job id named anywhere in a stage input (assemble_job, crop_job, proof_job, ...)."""
    out: list[str] = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        elif isinstance(v, str) and ident.fullmatch(v) and v not in out:
            out.append(v)
    walk(value)
    return out


def write_bundle(target: Path, project_dir: Path, header: dict, refs: list[str]):
    """bundle.json + project/source.mp4 + project/motion/** + project/<ref>.stage/* as one plain tar."""
    tmp = target.with_suffix(".partial")
    with tarfile.open(tmp, "w", format=tarfile.PAX_FORMAT) as tar:
        data = json.dumps(header, allow_nan=False).encode()
        info = tarfile.TarInfo("bundle.json")
        info.size, info.mode, info.mtime = len(data), 0o600, int(time.time())
        tar.addfile(info, io.BytesIO(data))
        tar.add(project_dir / "source.mp4", "project/source.mp4", recursive=False)
        motion_dir = project_dir / "motion"
        if motion_dir.is_dir():
            for path in sorted(motion_dir.rglob("*")):
                if path.is_symlink() or not (path.is_file() or path.is_dir()):
                    continue
                tar.add(path, "project/" + path.relative_to(project_dir).as_posix(), recursive=False)
        for jid in refs:
            folder = project_dir / (jid + ".stage")
            if not folder.is_dir():
                continue
            tar.add(folder, f"project/{jid}.stage", recursive=False)
            for path in sorted(folder.iterdir()):
                if path.is_file() and not path.is_symlink():
                    tar.add(path, f"project/{jid}.stage/{path.name}", recursive=False)
    tmp.replace(target)


def read_result(stream, length: int, inbox: Path) -> tuple[dict, Path]:
    """Unpack result.json + stage/<flat files> from a tar body into inbox, refusing anything else."""
    if inbox.exists():
        shutil.rmtree(inbox)
    inbox.mkdir(mode=0o700)
    stage_dir = inbox / "stage"
    stage_dir.mkdir(mode=0o700)
    raw = inbox / "body.tar"
    remaining = length
    with raw.open("xb") as f:
        while remaining:
            chunk = stream.read(min(1 << 20, remaining))
            if not chunk:
                raise Rejected("truncated result upload")
            f.write(chunk)
            remaining -= len(chunk)
    result = None
    total = 0
    try:
        with tarfile.open(raw, "r:") as tar:
            for member in tar:
                name = member.name[2:] if member.name.startswith("./") else member.name
                if member.isdir() and name.rstrip("/") in ("", ".", "stage"):
                    continue
                if not member.isfile():
                    raise Rejected(f"result may only hold regular files, not {name!r}")
                total += member.size
                if total > MAX_RESULT:
                    raise Rejected("result too large")
                if name == "result.json":
                    if member.size > 4 * 1024 * 1024:
                        raise Rejected("result.json too large")
                    result = json.loads(tar.extractfile(member).read())
                    continue
                folder, _, base = name.partition("/")
                if folder != "stage" or not ARTIFACT.fullmatch(base) or base.startswith(".") or Path(base).suffix not in SUFFIXES:
                    raise Rejected(f"unexpected file in result: {name!r}")
                src = tar.extractfile(member)
                with (stage_dir / base).open("xb") as out:
                    shutil.copyfileobj(src, out, 1 << 20)
    except (tarfile.TarError, ValueError, FileExistsError) as exc:
        if isinstance(exc, Rejected):
            raise
        raise Rejected(f"result is not a valid stage archive: {type(exc).__name__}") from None
    finally:
        raw.unlink(missing_ok=True)
    if not isinstance(result, dict):
        raise Rejected("result.json missing")
    return result, stage_dir


def check_result(result: dict, stage_dir: Path, stage: str, version: str, source_sha256: str, plan_sha256: str):
    if result.get("stage") != stage:
        raise Rejected("result is for a different stage")
    if result.get("service_version") != version:
        raise Rejected(f"result came from DeFleur {result.get('service_version')}, this app is {version}")
    if result.get("source_sha256") != source_sha256 or result.get("plan_sha256") != plan_sha256:
        raise Rejected("result source or plan hash differs from this job")
    artifacts = result.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise Rejected("result lists no artifacts")
    names = {p.name for p in stage_dir.iterdir()}
    listed = [a.get("name") for a in artifacts if isinstance(a, dict)]
    if len(listed) != len(artifacts) or sorted(listed) != sorted(names):
        raise Rejected("result artifacts do not match the returned files")
    for a in artifacts:
        path = stage_dir / a["name"]
        if path.stat().st_size != a.get("bytes") or sha(path) != a.get("sha256"):
            raise Rejected(f"artifact {a['name']} hash or size differs from result.json")
    if not isinstance(result.get("summary"), dict):
        raise Rejected("result summary missing")
