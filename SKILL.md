---
name: defleur-video-editing
description: Edit with DeFleur's independent cuts/captions, house motion and pinned generated-visual modules. Read the app-owned Conversation-first guide.
license: MIT
metadata:
  app: DeFleur Video (Wizard App Store)
  mcp: http://defleur-video:8787/mcp
  intended_setup: Hermes Agent with Claude Opus 5.5 for creative authorship only
---

# DeFleur · Conversation first v3.1

The app, not an agent's private skill or memory, owns the pipeline, fonts,
palette, components, image prompts, archive references, model pin and mix rules.
Read `workflow_guide(module="edit"|"motion"|"visuals"|"mixed")`. The complete
active instructions are shipped in `defleur/house/INSTRUCTIONS.md`, served by
`house_guide` and `read_workflow_doc("house-guide")`. No outside notes are needed.

## Three separable modules

- **A · Cuts + house captions + fixed crop.** Import -> start_edit -> inspect
  proposals -> ONE cut approval -> apply_cuts -> render_final(options={"motion":false})
  or `{"style":"captions"}` -> get_status until done. No Browser, image connection,
  motion author or Opus warning. Native captions are full-word heavy all-caps,
  white with the currently spoken word green, black stroke/shadow and restrained
  yellow emphasis. Preserve complete speech and a natural closing thought.
- **B · House motion.** An intended Opus author chooses typed components, short
  labels and exact spoken pivots, not executable HTML. Ask one combined cut +
  motion-plan approval. Convert source times through apply_cuts' time_map, then
  `submit_motion(files={},plan={duration,beats})`. The app compiles its own kit.
  Capture smoke/proof and inspect the actual frames before final motion render.
- **C · Visuals.** `plan_visual` builds the prompt and pinned archive references;
  `generate_visual` uses only this app's authorized box connection or returns the
  exact blocker with prompt/reference/upload instructions. Model is exactly
  **gpt-image-2-high**, PNG exactly **1080×1920**. No substitute provider. Upload
  through prepare_asset_upload, then `attach_visual`; model declarations on
  external uploads are not independently attested. Use the kit's image-beat.

## Conversation first · default James direction

Begin with the speaker. First meaningful support enters **3–5 seconds** into the
edited timeline. The majority is clean full-frame conversation, with meaningful
uninterrupted stretches and sparse explanation that clears completely. No
corner-tile speaker, permanent dashboard, caption suppression or repeated generic
motion. For a 30s+ Short with 3+ beats, mix generated art AND mechanism motion:
**Image -> mechanism -> image**. Consecutive components/techniques must differ.

The kit derives from approved v3 AI-authority, v3.1 Longevity, Two Futures and
Information Diet: lifeline, meter, stacked-moves, population/topology,
reservoir/accumulation, routing-chain, path-target, comparison-split,
source-frame, routine-grid, quality-area and shaped image-beat. Anton + Inter,
warm near-black/gold palette, maximum four-word labels and 11.6-second beats,
strictly under 50% graphics, clean returns and closing face are machine-checked.
Keep labels above native captions; never repeat the spoken sentence in a card.
The actual policy and provenance are in the shipped James preset.

Seven archive-grounded families and workflows ship in the app. Generate
illustrative portrait/metaphor/satire only; real evidence requires authentic
originals, host identity requires verified same-episode stills, and explanatory
mechanisms use editable motion. No invented papers, quotes, charts or screenshot
lookalikes. No music; no SFX unless explicitly requested. Keep native clean
speech custody; no external remux repair.

`set_house_policy` is an explicit, reasoned project exception, never an automatic
fallback: neutral allows legacy custom HTML; motion-only projects can relax mix.
Historical approved v3 has a later first beat; historical Longevity is motion-only.
Their archived fixtures retain these recorded exceptions without changing the
active default. New outputs always receive their own private review.

## Approval, authorship and delivery

For B/C, report actual creative-author identity; intended setup is Hermes Agent
with Claude Opus 5.5. A missing/mismatched model warns only for creative modules,
never before Module A imports. Do not claim a manifest proves the runtime model.
Inspect source identity, handles and prior edit history before calling material
fresh; use a new native project and preserve historical clips/drafts/approvals.

Never apply cuts before approval. Inspect untranscribed/noisy gaps. If
words_lost_near_cuts or dialogue gate fails, restore/widen the cut; distant ASR
variance is not proof of a missing word. Follow live get_status until done or
failed, not a fixed wait. Inspect several source/final frames for framing flags,
opening, every pivot, clean returns, both speakers and ending. Require full
decode, speech custody, final output hash and native delivery gate; gates are
not taste approval. Report what passed/failed and the playable final_mp4 link
(Files -> Videos -> Edited when available). Deliver a private **unapproved**
**v3.1 · Conversation first** draft, ask the owner to watch on a phone, never
publish or call it human-approved.
