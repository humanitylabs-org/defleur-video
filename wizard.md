---
wizard: 0.2
id: defleur-video
name: DeFleur Video
type: service
version: 0.6.5-testing
summary: Edit a talking-head video into a finished 1080x1920 vertical short with captions and motion graphics.
license: MIT
source: https://github.com/humanitylabs-org/defleur-video
runtime:
  kind: runtipi
  config: runtipi/config.json
  compose: runtipi/docker-compose.yml
mcp:
  path: /mcp
  port: 8787
  transport: streamable-http
skill: SKILL.md
provides: [video-editing, short-form-video]
recommends:
  agent: hermes
  model: claude-opus-5-5
system: false
uses: [transcriber, browser, files]
needs: [files]
health: /healthz
---

# DeFleur Video

Ask your Wizard to "edit this video". It transcribes through the Transcriber app, proposes one combined cut + motion plan for approval, renders through the shared Browser app, and saves the finished short to Files/Videos/Edited.

Split out of `wizard-app-store` with full history on 9 Oct 2026. The Runtipi files are unchanged and live in `runtipi/`. The image is still built and published by `wizard-app-store`'s `video.yml` until this repo's own workflow takes over.
