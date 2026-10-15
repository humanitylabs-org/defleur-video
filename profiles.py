"""Immutable editorial instruction profiles; never select an LLM or claim approval."""
import hashlib
import json
from pathlib import Path
from editing import Rejected

ROOT = Path(__file__).resolve().parent
DEFAULT = "original-v1"
IDS = (DEFAULT, "sound-and-research-v1")


def get(profile_id=DEFAULT):
    if profile_id not in IDS:
        raise Rejected("unknown workflow profile")
    original = (ROOT / "SKILL.md").read_bytes()
    text = original if profile_id == DEFAULT else original + b"\n\n" + (ROOT / "ENHANCED.md").read_bytes()
    return {"id": profile_id, "version": 1, "instructions": text.decode(),
            "instruction_sha256": hashlib.sha256(text).hexdigest(),
            "original_sha256": hashlib.sha256(original).hexdigest(),
            "soundtrack_enabled": profile_id != DEFAULT, "music_default": False}


def listing():
    return {"default": DEFAULT, "profiles": [{k: v for k, v in get(p).items() if k != "instructions"} for p in IDS]}


def pin(profile_id=DEFAULT, provenance=None):
    p = get(profile_id)
    provenance = provenance or {}
    allowed = {"experiment_id", "arm", "agent_model_reported", "agent_harness_reported", "approved_cut_reference", "source_evidence"}
    if not isinstance(provenance, dict) or set(provenance) - allowed or len(json.dumps(provenance)) > 32000:
        raise Rejected("invalid experiment provenance; use bounded reported identity and source references")
    # A reported model and a cited prior approval are not independently verified approvals.
    return {k: v for k, v in p.items() if k != "instructions"} | {"provenance": provenance, "identity_verified": False, "human_approval": False}
