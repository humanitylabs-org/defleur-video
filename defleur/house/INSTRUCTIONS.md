# Conversation first · v3.1 — active James preset

This app release activates the editorial direction formerly preserved on the
Conversation-first branches. Historical artifacts are packaged under
`house/content/historical/` unchanged; their instruction-only status is not the status
of this release. Native audio, alignment, captions, crop and delivery helpers
remain byte-pinned. Style is app-owned data and assets, never an agent's notes.

## Three independently usable modules

**A · Edit.** `workflow_guide(module="edit")` is the safe entry point for any
agent. Import -> start_edit -> inspect transcript/cut proposals -> one owner cut
approval -> apply_cuts -> get_status -> render_final(options={"motion":false})
(or `{"style":"captions"}`). This gives the house active-word captions and
fixed-per-setup 9:16 face crop without motion, images, Browser or an Opus warning.
Caption styling stays heavy all-caps, white with a green spoken word, black
outline/shadow and restrained yellow emphasis. Keep all complete words. Inspect
noisy or untranscribed gaps before asking to cut them; no automated approval.

**B · House motion.** `workflow_guide(module="motion")` includes the creative
authorship check. Choose app components, short labels and 1–3 exact spoken pivots;
never supply your own HTML/CSS/JS in the James preset. Submit
`submit_motion(project_id,files={},plan={"duration":edited_duration,"beats":[...]})`.
Every beat has `id`, `component`, `start`, `end`, `labels`, optional house `font`
and `color`, `phases:[{"at":edited_second,"word":spoken_pivot,"action":"reveal"|"transform"|"settle"}]`,
plus `spoken_anchor`, `viewer_inference`, `state_before`, `state_after`,
`causal_action` and `speaker_return`. The app supplies renderFrame, native ledger,
GSAP, local fonts, foam/ambient background and component geometry. It rejects
arbitrary overrides rather than trying to guess what arbitrary JavaScript draws.

**C · Generated visuals.** `plan_visual(project_id,beat_id,family,subject)` owns
the prompt, pinned archive references, model `gpt-image-2-high` and exact
1080×1920 non-interlaced RGB/RGBA PNG format. `generate_visual` checks the app's
existing authorized Connection Router, never host credentials, an agent model
or another provider. A missing grant/route/image transport returns the exact
blocker and exact prompt/reference/upload instructions. Stop there; never claim
an image was generated. The currently published router transport is text-only;
no speculative image API is used. After an externally generated image is
uploaded through `prepare_asset_upload`, call `attach_visual` with the exact
asset path and declared model. Model declarations are recorded honestly, not
misrepresented as provider attestation. A changed image hash invalidates capture.
Use `component:"image-beat",visual_id:beat_id,labels:[]` for shaped cut-in and a
purposeful 5.5% push at the spoken pivot. No fake evidence, charts or screenshots.

Seven families and their actual workflows live in `families.json`: boss/glitch,
cinematic metaphor, comic satire, authentic meme remix, explanatory mechanisms,
real documentary evidence and same-episode host identity. Only illustrative art
is generated. Mechanisms use Module B; documentary and identity assets require
real sources. Owner-supplied reference thumbnails 506,554,633,440,539 are packaged
with archive IDs and hashes. References 542/569 remain source links because
third-party rights/context have not been established. They are not fake stand-ins.

## Conversation-first editorial contract

- Begin on the speaker's face. The first meaningful supporting image/animation
  enters at **3–5 seconds of the edited timeline**; captions/logos/titles do not
  satisfy it. Do not start with a visual or defer it to 10–15 seconds.
- Keep a **majority of clean, full-frame conversation** and meaningful
  uninterrupted stretches. Every visual makes one useful point and clears
  completely. Never shrink a speaker into a corner or hold a split-screen.
- On 30-second-plus Shorts with 3+ beats, include generated art **and** mechanism
  motion: **Image -> mechanism -> image** is the default suggestion. Never use
  the same component/technique on consecutive beats. Do not add filler to meet
  a quota; use a documented project exception when motion alone is appropriate.
- Select visuals for the actual new passage. Source scroll/highlight needs a
  relevant authentic source and clear attribution. Illustration is not evidence.
- Native full-word active captions remain visible through every beat. Graphics
  occupy the content region above the caption band (y=1220..1460 at 1080 wide).
  Use Anton and Inter labels, not paragraphs or a second copy of the dialogue.
- No music. No sound effects unless explicitly requested. Render from native
  clean dialogue; do not externally remux the final to repair custody.
- Preserve exact camera boundaries, complete spoken words, natural cadence and
  a complete closing thought on the speaker.

## Machine policy and its provenance

`defaults/james-preset.json` records all numerical limits, palette and provenance.
3–5s comes directly from v3.1. The 11.6s maximum is the longest approved Longevity
beat (15.85–27.45). Strictly under 50% graphics encodes v3.1's majority-clean rule
(Longevity is 30.4/75.89s). Four words per label covers the approved labels.
One second minimum clean return/closing reserve is an implementation floor,
not a claim that the director specified exact one-second pacing.

`set_house_policy` requires a visible reason for owner/project exceptions. It can
select neutral custom composition mode, relax mix, or change the first-visual
window. This is explicit, persisted and auditable; no automatic fallback.
Historical v3 begins at 14.565s and predates the new early-visual rule. Historical
Longevity is motion-only. Their archived/ported regression fixtures explicitly
record these necessary historical exceptions; the active default is not weakened.
The neutral preset keeps custom HTML/GSAP compatibility and neutral font tokens.

## Native workflow, authorship and review

For B/C/mixed, actual Claude Opus 5.5 under Hermes is the intended creative author;
record actual runtime evidence, not just a manifest claim. Mechanics/verification
can be performed by other agents; no substitution for an approved creative author
is implied. The warning never applies to Module A. Ask ONE combined cuts/visuals
approval before applying decisions when visuals are requested.

For fresh passages, inspect source ranges and edit history across available
archive/render ledgers; a new title is not new footage. Use a fresh project,
record source identity and handles, cut map and duplicate-check coverage/gaps.
Preserve historical clips, notes and approvals.

Convert approved source times through apply_cuts' time_map to edited seconds.
Run native submit_motion -> capture_motion smoke -> inspect real frames -> proof
-> inspect contact sheet and phone-scale frames -> render_final(motion:true).
The app revalidates style, actual edited duration and image/kit bytes at capture.
Require dialogue and delivery gates, complete decode, speech custody and final
output hash. Inspect opening, early visual entrance, every pivot, clean returns,
both speakers and the closing thought. Sampled screenshots are not full decode
or subjective approval. Remote media workers perform capture, rendering and ASR.

Deliver one private **unapproved** draft named **v3.1 · Conversation first** when
authorized. Report resolution/duration, cuts, beat times, caption count, framing
flags, gate reasons, words lost versus distant ASR variance, and the playable
link. Ask the owner to watch on a phone; never mark unseen content approved or
publish it. Selecting a new private viewing draft is not human acceptance.
