#!/usr/bin/env python3
"""Run one DeFleur workflow stage from a remote-stage bundle (remote_stages.py), inside this same image.

The Company's Mac render worker runs it as `python3 /app/stage_runner.py /work` with the bundle unpacked in
/work (bundle.json + project/). It calls the exact workflow.run the service's own worker calls, with the
same native() limits, and writes /work/out/result.json + /work/out/stage/<artifacts>. On any failure it
writes /work/out/error.json and exits non-zero; the caller then gives the stage back to the Company box.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import time

import remote_stages
import service
import workflow
from editing import Rejected


def run(work: Path) -> dict:
    bundle = json.loads((work / "bundle.json").read_text())
    if bundle.get("format") != remote_stages.FORMAT:
        raise Rejected("not a DeFleur remote-stage bundle")
    if bundle.get("version") != service.VERSION:
        raise Rejected(f"bundle is for DeFleur {bundle.get('version')}; this image is {service.VERSION}")
    stage, value, metadata, jid = bundle["stage"], bundle["input"], bundle["metadata"], bundle["job"]
    if stage not in remote_stages.REMOTE_STAGES or not service.ID.fullmatch(jid):
        raise Rejected("bundle names a stage this runner does not run")
    project = work / "project"
    source = project / "source.mp4"
    if service.digest(source) != metadata["source_sha256"]:
        raise Rejected("bundle source hash differs from the project")
    jobs = bundle.get("jobs") or {}

    def lookup(ref, stages):
        # Same rule as Store.stage_ref: a finished stage of the same project, of an allowed kind.
        if not isinstance(ref, str) or not service.ID.fullmatch(ref):
            raise Rejected("job reference must be a 32-hex job id")
        job = jobs.get(ref)
        if not job or job["project"] != bundle["project"] or job["state"] != "needs_review" or not job["result"] \
                or job["result"].get("stage") not in stages:
            raise Rejected(f"job {ref} is not a finished {'/'.join(sorted(stages))} stage of this project")
        return job, project / (ref + ".stage")

    plan = {"workflow_stage": stage, "input": value}
    plan_sha256 = hashlib.sha256(service.json_bytes(plan)).hexdigest()
    if plan_sha256 != bundle.get("plan_sha256"):
        raise Rejected("bundle plan hash differs")
    root = project / (jid + ".stage")
    started = time.monotonic()
    service.NATIVE_CONTEXT.deadline = time.monotonic() + workflow.deadline_for(stage)
    try:
        result = workflow.run(stage, value, source, root, metadata, service.native, lookup,
                              service.NATIVE_CONTEXT.deadline, service.input_args)
    finally:
        del service.NATIVE_CONTEXT.deadline
    result.update({"source_sha256": metadata["source_sha256"], "plan_sha256": plan_sha256,
                   "elapsed_s": round(time.monotonic() - started, 3), "service_version": service.VERSION,
                   "upstream_commit": service.UPSTREAM, "ai_calls": 0, "arch": platform.machine()})
    out = work / "out"
    out.mkdir(exist_ok=True)
    shutil.move(str(root), str(out / "stage"))
    (out / "result.json").write_text(json.dumps(result, allow_nan=False))
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: stage_runner.py /work", file=sys.stderr)
        return 2
    work = Path(argv[0])
    try:
        result = run(work)
    except Exception as exc:  # report every failure plainly; the caller gives the stage back
        out = work / "out"
        out.mkdir(exist_ok=True)
        (out / "error.json").write_text(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:600]}))
        print(json.dumps({"ok": False, "error": str(exc)[:600]}), flush=True)
        return 1
    print(json.dumps({"ok": True, "stage": result["stage"], "elapsed_s": result["elapsed_s"],
                      "artifacts": len(result["artifacts"]), "arch": result["arch"]}), flush=True)
    return 0


if __name__ == "__main__":
    os.umask(0o077)
    raise SystemExit(main(sys.argv[1:]))
