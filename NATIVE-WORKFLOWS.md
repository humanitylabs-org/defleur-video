# Native workflow candidate — operator handoff

This branch adds native profiles and sound stages to DeFleur Video. It does not
change the intended agent model, authorize an edit, or select a provider. The
original `SKILL.md` and bundled upstream helpers remain byte-for-byte unchanged.

## Candidate deployment

Use `compose.native.yml` in an isolated Compose project. Build only a pushed
commit; set `VIDEO_IMAGE`, `VIDEO_REVISION`, `VIDEO_API_TOKEN`, and `DATA_ROOT` in
a private environment file outside the checkout. `DATA_ROOT` must live on the
external work disk. Optional `VIDEO_PORT` defaults to 28787, published on loopback
only. Browser and Transcriber have no host port. Set `VIDEO_PUBLIC_URL` to the
operator's authenticated forwarding origin if download links need that origin.
Do not reuse production data or disturb other containers. Bring up only this
Compose project, and retain its data for resumable jobs.

The service keeps its original system interpreter. Native sound analysis runs
as an isolated helper in the existing pinned virtualenv using its existing NumPy
dependency. No new model or unpinned dependency was added.

Verify `/healthz`, authenticated `/v1/capabilities`, then MCP initialize and
`capabilities`. Require Transcriber reachable/model installed, Browser reachable,
and motion_ready. A successful health response alone is not workflow readiness.

## API sequence

1. `GET /v1/workflows` lists `original-v1` (default) and `sound-and-research-v1`.
   `GET /v1/workflows/{id}` returns exact instruction text and hashes. MCP:
   `list_workflows`, `workflow_guide(profile_id=...)`.
2. Import/upload a **fresh project per arm** through the existing native tools.
   `POST /v1/projects/{id}/workflow` with `{profile_id, provenance}` pins the
   instructions. Allowed provenance: experiment_id, arm, agent_model_reported,
   agent_harness_reported, approved_cut_reference, source_evidence. These are
   claims/references, not independently verified identity or fresh approval.
   Profile selection freezes after the first job. MCP: `select_workflow`.
3. Independently author both arms with the actual requested model. Replay only
   common approved cuts, not prior composition/results. Preserve real source,
   model/harness, original approval reference and all returned job IDs.
4. Original arm uses the unchanged dialogue/motion/render flow. Enhanced arm
   uploads trusted audio to `POST /v1/projects/{id}/sound-assets`, payload:
   `{base64, extension, sha256, license_receipt: {source_url, license,
   attribution, evidence}}`. Allowed extensions: wav/mp3/flac/ogg/m4a (leading
   dot). Allowed receipts: CC0-1.0, CC-BY-4.0, owned. Assets and receipts are
   content-addressed. No server URL fetch or filesystem path parameter.
5. `POST .../soundtrack` accepts `{version:1,cues:[{asset_id,role,start,end,
   source_start,gain_db,fade_s}]}` and returns `plan_sha256`. Timings are edited
   seconds; no silent looping or padding. Gain is relative to local dialogue
   RMS: -28..-16 dB SFX, -28..-20 dB music (trial bounds; audition still required). Fades >=5ms and <= half cue length.
   At least one SFX is required. Overlap exceeding aggregate limits is rejected.
6. `POST .../stages/sound-mix` with `{assemble_job,plan_sha256}`. Poll native
   job status; retain the returned mix receipt, credits, dual WAV hashes and
   immutable dialogue-premix hash. MCP: `mix_soundtrack`, `sound_job_status`.
7. `render_final` options `{motion:true,sound_mix_job:<job>,music:false}` gives
   B-off, dialogue plus SFX, mixed before the native final encoder. Then use
   `{motion:true,sound_mix_job:<same>,music:true,base_render_job:<off-render>}`
   for B-on. The second native final-render stage reuses the exact compressed
   picture stream, encodes new AAC, decodes all picture frames and verifies
   their hashes match B-off. No recapture and no external rendering script.
   HTTP accepts these same extra fields on the existing final-render stage.
8. Both render jobs require their own existing final ASR, acoustic scan and
   delivery gate. Speech-cut/dialogue gates continue to read original speech;
   sound gate additionally checks mix/source custody, AAC decoded correlation,
   duration and sample peak. No threshold in the original gate is relaxed.
   `credits.json` is an exported sidecar, not embedded metadata. Download it
   from the render job's stage-artifacts endpoint. Human listening is still
   mandatory; RMS/correlation are not perceptual approval or true-peak proof.

## Verification scope

`test_native_sound.py` runs real HTTP upload, profile freeze, receipt/hash/timing
rejections, original PCM assembly, licensed synthetic sound mix, AAC encode and
decoded custody check. Run the suite with the image's original system Python.
`NATIVE_SOUND_EVIDENCE` can save its actual JSON report. The fixture is generated
owned sine waves; it does **not** prove speech ASR or human listening quality.
Run the existing `test_service.py` regression suite too. Full Browser capture,
speech ASR, both variant final-render paths and end-to-end delivery acceptance
must be reported from real execution, not inferred from this fixture.

## Review limitations

This is a candidate, not an approved release. License receipts are supplied by
the operator and retained; the app cannot establish legal title automatically.
There is no automatic ducking: fixed dialogue-relative gain, fades and overlap
limits are used. Silent/speech-free cue windows fail closed rather than guessing
a level. Loudness/true-peak and subjective audibility still require review.
## Native common-mechanics evidence

`pcm-assemble` now emits `pcm-identity.json`: an independent direct comparison of every complete kept PCM block with the source at its mapped position, bound to source/edited/map hashes. `apply_cuts` preserves the lexical lost/added lists and original near-cut rejection. Only a usable aligned word wholly retained in a verified block can become `asr_variance_pcm_verified`; no word-pair whitelist, threshold reduction or listening approval is implied. Cut-overlap, acoustic and dialogue custody gates still apply. Truncated/crossing/unusable intervals or any mismatched PCM cannot use this route.

Framing accepts `shot_boundaries: [{"source_frame": 452}, {"source_frame": 490}]`, meaning the first source frame of each independently observed camera shot, or exact frame-aligned `source_s` instead. These split only the VIDEO crop ledger at the first corresponding output frame. Audio, approved cuts and canonical edit map stay unchanged. Targets and `new_setup_at` keep their original kept-segment indexes. Both sides of each shot are sampled, with one fixed crop per setup and unchanged face margins. Supply the same framing to preview, capture and final render; shot boundaries are not permission for detector-driven panning.
