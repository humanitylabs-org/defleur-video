# DeFleur Video API with James DeFleur's original workflow helpers bundled (see NOTICE).
FROM ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d AS uv

# Node runtime + exact-pinned puppeteer-core and GSAP (package-lock.json) for James' capture.cjs. No browser here:
# capture connects to the shared Browser app.
FROM node:22.23.5-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS capture
WORKDIR /opt/capture
COPY capture/package.json capture/package-lock.json /opt/capture/
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund && rm -rf /root/.npm \
    && node -e "require('puppeteer-core'); require('fs').statSync('node_modules/gsap/dist/gsap.min.js')"

FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55 AS venv
ENV DEBIAN_FRONTEND=noninteractive UV_NO_CACHE=1 UV_PYTHON_DOWNLOADS=never
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
COPY requirements.lock /tmp/requirements.lock
# Hash-locked CPU-only torch/stable-ts/numpy/matplotlib (uv pip compile --generate-hashes). No faster-whisper.
RUN uv venv --python /usr/bin/python3 /opt/venv \
    && uv pip install --python /opt/venv/bin/python --require-hashes --no-deps \
       --index-url https://download.pytorch.org/whl/cpu --extra-index-url https://pypi.org/simple \
       --index-strategy unsafe-best-match -r /tmp/requirements.lock \
    && rm -rf /opt/venv/lib/python3.12/site-packages/torch/include /opt/venv/lib/python3.12/site-packages/torch/test \
    && find /opt/venv -name '__pycache__' -prune -exec rm -rf {} + \
    && /opt/venv/bin/python -c "import torch, stable_whisper, numpy, matplotlib, PIL, onnxruntime, uvicorn, cv2; assert cv2.FaceDetectorYN; import mcp.server.mcpserver; print(torch.__version__)"

FROM ubuntu:24.04@sha256:534baea6a22c03a63003dbc8dbe78fe34bc0d7e595d9a9dc9834884ff530eb55
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 VIDEO_BIND=0.0.0.0 VIDEO_DATA_DIR=/data \
    DEFLEUR_ROOT=/opt/defleur VIDEO_HELPER_PYTHON=/opt/venv/bin/python VIDEO_MODELS_DIR=/data/models
RUN apt-get update && apt-get install -y --no-install-recommends python3 ffmpeg util-linux tini ca-certificates fontconfig fonts-dejavu-core fonts-montserrat \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir /app /data && chown 1000:1000 /data
RUN test -f /usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf && fc-match -f '%{file}' 'sans-serif:style=Bold' | grep -q '^/usr/share/fonts/truetype/dejavu/' \
    && fc-match -f '%{file}' 'Montserrat:style=Black' | grep -q 'Montserrat-Black'
# Fonts for installed style packs (wizard-os#1012): Playfair Display Italic and Cormorant Garamond (+ Italic), SIL OFL 1.1,
# from google/fonts at a pinned commit (Ubuntu does not package them). Hashes pinned; licences copied beside them.
ADD --checksum=sha256:a5e26dc5e2e77fb2803a0bf02fd4f81ee136ec8dea863ccdb0c59a263b21378b \
    https://raw.githubusercontent.com/google/fonts/5026800714d07231937d92eb4cceabf06e05d74e/ofl/playfairdisplay/PlayfairDisplay-Italic%5Bwght%5D.ttf \
    /usr/share/fonts/truetype/wizard-styles/PlayfairDisplay-Italic.ttf
ADD --checksum=sha256:b20b7d9626dd956b2c5e558692ad328b1f19e3275e2782db4fa07670d83f35e0 \
    https://raw.githubusercontent.com/google/fonts/5026800714d07231937d92eb4cceabf06e05d74e/ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf \
    /usr/share/fonts/truetype/wizard-styles/CormorantGaramond.ttf
ADD --checksum=sha256:0f48ea6abb2084537854f7174c470991a463b13036309e3b50a81511611c530d \
    https://raw.githubusercontent.com/google/fonts/5026800714d07231937d92eb4cceabf06e05d74e/ofl/cormorantgaramond/CormorantGaramond-Italic%5Bwght%5D.ttf \
    /usr/share/fonts/truetype/wizard-styles/CormorantGaramond-Italic.ttf
ADD --checksum=sha256:566be814f8e96e93dfa16101331557eb6b5467e9e03f627c0910fe93ca12300e \
    https://raw.githubusercontent.com/google/fonts/5026800714d07231937d92eb4cceabf06e05d74e/ofl/playfairdisplay/OFL.txt \
    /usr/share/fonts/truetype/wizard-styles/OFL-PlayfairDisplay.txt
ADD --checksum=sha256:60700d351cac4650c51f3f9db318d2a420f8b45052dba2715eb5fec41f0f6956 \
    https://raw.githubusercontent.com/google/fonts/5026800714d07231937d92eb4cceabf06e05d74e/ofl/cormorantgaramond/OFL.txt \
    /usr/share/fonts/truetype/wizard-styles/OFL-CormorantGaramond.txt
RUN chmod 0644 /usr/share/fonts/truetype/wizard-styles/* && fc-cache -f \
    && fc-match -f '%{file}' 'Playfair Display:style=Italic' | grep -q 'wizard-styles/PlayfairDisplay-Italic' \
    && fc-match -f '%{file}' 'Cormorant Garamond:style=Italic' | grep -q 'wizard-styles/CormorantGaramond-Italic' \
    && fc-match -f '%{file}' 'Montserrat:style=Bold' | grep -q 'Montserrat-Bold'
COPY --from=venv /opt/venv /opt/venv
COPY --from=capture /usr/local/bin/node /usr/bin/node
COPY --from=capture /opt/capture /opt/capture
COPY capture/capture-remote.cjs capture/capture-remote.diff /opt/capture/
RUN /usr/bin/node --version
# YuNet face detector (opencv_zoo commit f12e127, MIT, Shiqi Yu); hash = upstream git-lfs oid.
ADD --checksum=sha256:8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4 \
    https://media.githubusercontent.com/media/opencv/opencv_zoo/f12e12798e8314f7c074a6656816c048dcc95b7a/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
    /opt/models/yunet.onnx
RUN chmod 0644 /opt/models/yunet.onnx
LABEL org.opencontainers.image.source="https://github.com/humanitylabs-org/defleur-video" org.opencontainers.image.description="DeFleur Video API + MCP endpoint (audio/edit, face crop, motion capture via the Browser app, captions, final encode)"
# James' plugin files, byte-for-byte (upstream commit 30768288eb1308b18216a5df5eb4648fbce3e55b, MIT per plugin.json).
COPY defleur/ /opt/defleur/
COPY NOTICE /opt/defleur/NOTICE
WORKDIR /app
COPY service.py remote_stages.py stage_runner.py editing.py client.py workflow.py transcriber.py scan_windows.py energy.py face_audit.py final_render.py motion.py motion_frames.py mcp_server.py styles.py style_render.py /app/
# Agent-facing editing judgment (Agent Skills format), served at GET /SKILL.md and as an MCP resource.
COPY SKILL.md /app/
RUN /opt/venv/bin/python -I /opt/defleur/skills/defleur-audio/scripts/test_audio_gate.py
USER 1000:1000
EXPOSE 8787
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/usr/bin/python3", "/app/service.py"]
HEALTHCHECK --interval=30s --timeout=5s CMD ["/usr/bin/python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/healthz', timeout=3).read()"]
