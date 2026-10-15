# Sound and source-research extension — version 1

Everything in original-v1 remains binding, including independent editorial authorship,
cut approval, original speech custody, full-frame motion, always-on captions,
smoke/proof review, final ASR and delivery gates. Do not change the model or harness.
Report their actual identities; the app's receipt records claims, not attestation.

Before the first stage select sound-and-research-v1 with select_workflow. Pin an
experiment ID, arm, reported model/harness and the actual prior approved-cut reference.
Use a fresh project per independent arm. Never call an old render a fresh baseline.

Research primary/original sources for relevant B-roll. Use existing plan.inserts;
record source URL, retrieval/capture date, asset SHA-256 and exact spoken anchor in
profile provenance.source_evidence. Distinguish screenshots from inferred claims.
Use native asset upload and motion submission, never external final-video processing.

Sound is authored as an immutable native soundtrack plan after cuts. Register audio
using upload_sound_asset (base64 for small assets) with a SHA-256 and a license receipt:
source_url, license (CC0-1.0, CC-BY-4.0 or owned), attribution and evidence. These are
operator-supplied receipts, not an automatic legal determination. Retain source evidence.
Only upload trusted licensed sounds; do not infer that a downloadable asset is licensed.

Use subtle but audible, relevant SFX, not a constant effect wash. Cues use edited seconds,
start/end, source_start, gain_db, fade_s and role (sfx/music). gain_db is relative to the
local dialogue RMS. Trial bounds are -28..-16 dB for SFX and -28..-20 dB for music;
start music near -22 dB and audition the actual clip, adjusting within those bounds.
The app records stem levels and rejects silent assets or speech-free cue windows.
These numeric bounds prevent replaying the failed -32 dB treatment; they do not prove audibility. Music defaults
OFF. B-off contains dialogue plus SFX; B-on contains the identical picture plus those SFX
and optional music. Listen to both; machine RMS evidence does not prove perceptual quality.
Never claim human listening, editorial approval or delivery approval from numeric checks.

Submit soundtrack with submit_soundtrack, execute native sound-mix with the locked
assemble_job and plan_sha256, then render_final with sound_mix_job and music=false.
For the optional music-on version use the same sound_mix_job and base_render_job of
B-off: the native final-render stage reuses the exact encoded picture. Each variant must
independently pass final ASR/acoustic/delivery checks. Do not bypass a failed gate.
Credits are an exported JSON sidecar; do not claim credits are embedded in the video.
