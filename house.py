"""App-owned Conversation-first house kit. No agent prompt controls rendered style.

James compositions are data, not executable HTML. Neutral is an explicit,
reasoned project choice. Revalidate against the native edited duration at capture.
"""
from __future__ import annotations
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import urllib.error
import urllib.request
import zlib

from editing import Rejected

ROOT = Path(os.environ.get('DEFLEUR_ROOT', Path(__file__).parent / 'defleur'))
KIT = ROOT / 'house'
MODEL = 'gpt-image-2-high'
COMPONENTS = ('lifeline', 'meter', 'stacked-moves', 'population', 'reservoir',
              'routing-chain', 'path-target', 'comparison-split', 'source-frame',
              'routine-grid', 'quality-area', 'image-beat')
ID = re.compile(r'^[a-z][a-z0-9_-]{0,47}$')
BEAT_META = ('spoken_anchor', 'viewer_inference', 'state_before', 'state_after', 'causal_action', 'speaker_return')


def under(project, *parts):
    """Confine every request-derived house path, including parent symlinks."""
    base = os.path.realpath(project) + os.sep
    target = os.path.realpath(os.path.join(base, *parts))
    if not target.startswith(base):
        raise Rejected('house path must stay inside this project')
    return Path(target)


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else copy.deepcopy(default)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.pending')
    tmp.write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def text(value, label, maximum=600):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise Rejected(f'{label}: nonempty text, at most {maximum} characters required')
    return value.strip()


def number(value, label, minimum=0):
    if type(value) not in (float, int) or not math.isfinite(value) or value < minimum:
        raise Rejected(f'{label}: finite number >= {minimum} required')
    return float(value)


def policy(project=None):
    p = read(project / 'house-policy.json', {}) if project else {}
    name = p.get('preset', 'james')
    preset = read(ROOT / 'defaults' / f'{name}-preset.json')
    return {'preset': name, **preset['house'], **p}


def set_policy(project, value):
    if not isinstance(value, dict) or set(value) - {'preset', 'mix_required', 'first_visual_window', 'reason'}:
        raise Rejected('house policy: only preset, mix_required, first_visual_window and reason are configurable')
    if value.get('preset', 'james') not in ('james', 'neutral'):
        raise Rejected('house policy preset must be james or neutral')
    value = {**value, 'reason': text(value.get('reason'), 'owner/project override reason')}
    if 'mix_required' in value and type(value['mix_required']) is not bool:
        raise Rejected('mix_required must be boolean')
    if 'first_visual_window' in value:
        w = value['first_visual_window']
        if not isinstance(w, list) or len(w) != 2 or number(w[0], 'window start') > number(w[1], 'window end'):
            raise Rejected('first_visual_window must be [start,end]')
    write(project / 'house-policy.json', value)
    return policy(project)


def registry():
    return read(KIT / 'families.json')


def guide(project=None):
    return {'version': 'conversation-first-v3.1', 'policy': policy(project),
            'components': list(COMPONENTS), 'families': registry(),
            'modules': {
                'edit': 'Import -> start_edit -> apply_cuts -> render_final(options={"motion":false}). Cuts, fixed crop and house captions only. No authorship warning, Browser, image or motion dependency.',
                'motion': 'Choose labels, components and spoken pivots, not HTML. submit_motion(files={},plan={duration,beats}) compiles the app kit. For motion-only Shorts >=30s with 3+ beats, explicitly set project mix_required:false with owner/project reason.',
                'visuals': 'plan_visual builds the exact pinned prompt and references. generate_visual reports connection blockers without substitution. Upload the resulting PNG through create_asset_upload, then attach_visual; finally use image-beat.'},
            'direction': (KIT / 'INSTRUCTIONS.md').read_text(),
            'mix_suggestion': 'Image -> mechanism -> image. Each beat must do a different job, then clear back to the full-frame speaker.',
            'submit_example': {'files': {}, 'plan': {'duration': 20, 'beats': [
                {'id': 'mechanism', 'component': 'meter', 'start': 3.5, 'end': 6.5,
                 'labels': ['TRUST ALL', 'HEALTHY', 'DOUBT ALL'], 'font': 'Anton', 'color': policy(project)['default_color'],
                 'phases': [{'at': 4.5, 'word': 'healthy', 'action': 'settle'}],
                 'spoken_anchor': 'a healthy level of skepticism', 'viewer_inference': 'one inference',
                 'state_before': 'one state', 'state_after': 'changed state',
                 'causal_action': 'word-locked change', 'speaker_return': 'full speaker after end'}]}}}


def validate(plan, duration=None, project=None, configuration=None):
    p = configuration or policy(project)
    if p['preset'] == 'neutral':
        return copy.deepcopy(plan)
    if not isinstance(plan, dict) or set(plan) - {'duration', 'beats', 'caption_emphasis', 'notes'}:
        raise Rejected('James house plans accept duration, beats, caption_emphasis and notes only; no custom CSS/HTML, inserts or caption suppression')
    duration = number(duration if duration is not None else plan.get('duration'), 'edited duration', .01)
    beats = plan.get('beats')
    if not isinstance(beats, list) or not 1 <= len(beats) <= 100:
        raise Rejected('house beats must contain 1-100 meaningful supporting visuals')
    allowed = {'id', 'component', 'start', 'end', 'labels', 'font', 'color', 'phases', 'visual_id',
               'source_asset', 'source_url', 'attribution', *BEAT_META}
    previous, coverage, kinds, last_component, ids = 0.0, 0.0, set(), None, set()
    for i, b in enumerate(beats):
        if not isinstance(b, dict) or set(b) - allowed:
            raise Rejected(f'beat {i}: unknown properties; house style cannot be overridden')
        if not isinstance(b.get('id'), str) or not ID.fullmatch(b['id']) or b['id'] in ids:
            raise Rejected(f'beat {i}: unique lowercase id required')
        ids.add(b['id'])
        c = b.get('component')
        if c not in COMPONENTS:
            raise Rejected(f'beat {i}: select an app-owned component from {COMPONENTS}')
        start, end = number(b.get('start'), 'beat start'), number(b.get('end'), 'beat end')
        if end <= start or end - start > p['max_beat_seconds'] + 1e-6:
            raise Rejected(f'beat {i}: maximum beat length is {p["max_beat_seconds"]}s')
        if i == 0 and not p['first_visual_window'][0] <= start <= p['first_visual_window'][1]:
            raise Rejected(f'first meaningful visual must enter at {p["first_visual_window"]}s, on the edited timeline')
        if i and start - previous < p['min_clean_gap_seconds'] - 1e-6:
            raise Rejected(f'beat {i}: must clear completely and return to the speaker for {p["min_clean_gap_seconds"]}s')
        if end > duration - p['closing_speaker_seconds'] + 1e-6:
            raise Rejected('last beat must return to the full-frame speaker for the complete closing thought')
        if c == last_component:
            raise Rejected('generic same motion graphics throughout is rejected: consecutive beats must use different components/techniques')
        last_component, previous = c, end
        coverage += end - start
        color = b.get('color', p['default_color'])
        if not isinstance(color, str) or color.lower() not in p['palette']:
            raise Rejected(f'beat {i}: color outside the house palette')
        if b.get('font', 'Anton') not in p['fonts']:
            raise Rejected(f'beat {i}: only house fonts {p["fonts"]} are allowed')
        labels = b.get('labels', [])
        if not isinstance(labels, list) or len(labels) > p['max_labels']:
            raise Rejected('too many labels; text-heavy cards rejected')
        for label in labels:
            label = text(label, 'label', 60)
            words = re.findall(r"\w+", label.lower())
            if len(label) > 28 or len(words) > p['max_label_words']:
                raise Rejected('text-heavy cards rejected: use short labels, not sentences')
            anchor_words = re.findall(r"\w+", str(b.get('spoken_anchor', '')).lower())
            if len(words) >= 4 and ' '.join(words) in ' '.join(anchor_words):
                raise Rejected('labels must not repeat the spoken line; native captions already carry it')
        for key in BEAT_META:
            text(b.get(key), f'beat {i} {key}')
        phases = b.get('phases')
        if not isinstance(phases, list) or not 1 <= len(phases) <= 3:
            raise Rejected('each beat needs 1-3 spoken pivots (phases), not decorative continuous motion')
        last_at = start
        for phase in phases:
            if not isinstance(phase, dict) or set(phase) != {'at', 'word', 'action'}:
                raise Rejected('phase requires exactly at, word, action')
            at = number(phase['at'], 'phase at')
            if not last_at <= at < end:
                raise Rejected('phases must be ordered inside the beat')
            last_at = at
            word = text(phase['word'], 'pivot word', 60).lower()
            if word not in b['spoken_anchor'].lower():
                raise Rejected('pivot word must occur in spoken_anchor')
            if phase['action'] not in ('reveal', 'transform', 'settle'):
                raise Rejected('phase action must be reveal, transform or settle')
        if c == 'image-beat':
            if labels:
                raise Rejected('image beats show art, never synthetic text/evidence; use native captions')
            vid = b.get('visual_id')
            if not isinstance(vid, str) or not ID.fullmatch(vid):
                raise Rejected('image-beat requires an attached visual_id')
            if project:
                attached = read(under(project, 'visuals', f'{vid}.json'))
                if not attached or attached.get('state') != 'attached':
                    raise Rejected(f'image-beat {vid}: attach the generated PNG first')
                path = under(project, 'motion', 'src', attached['asset'])
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != attached['sha256']:
                    raise Rejected('attached visual bytes changed; reattach and re-prove')
            kinds.add('image')
        else:
            kinds.add('motion')
        if c == 'source-frame':
            if not re.fullmatch(r'assets/[a-z0-9_-]+\.png', str(b.get('source_asset', ''))):
                raise Rejected('source-frame needs a PNG source_asset in assets/')
            if not str(b.get('source_url', '')).startswith('https://'):
                raise Rejected('source-frame needs a real https source_url, not generated evidence')
            text(b.get('attribution'), 'source attribution', 60)
    if coverage / duration >= p['max_graphic_fraction']:
        raise Rejected(f'graphic coverage {coverage / duration:.1%} is not below {p["max_graphic_fraction"]:.0%}; the conversation must be the majority')
    if p['mix_required'] and duration >= p['mix_min_seconds'] and len(beats) >= p['mix_min_beats'] and kinds != {'image', 'motion'}:
        raise Rejected('mix rule: a Short of 30s+ with 3+ beats needs generated-image AND motion-graphic beats; suggest Image -> mechanism -> image')
    out = copy.deepcopy(plan)
    out['duration'] = duration
    return out


def compile_files(plan, project=None):
    """Only shipped code + JSON-escaped data execute for James. No caller CSS/JS."""
    p = policy(project)
    data = copy.deepcopy(plan)
    for b in data['beats']:
        if b['component'] == 'image-beat' and project:
            visual = read(under(project, 'visuals', f'{b["visual_id"]}.json'))
            if not visual or visual.get('state') != 'attached':
                raise Rejected('attach the generated PNG before compiling image-beat')
            b['asset'] = visual['asset']
    # Neutral kit still available as assets; custom neutral files use the legacy path.
    data['palette'] = p['palette']
    data['neutral'] = p['preset'] == 'neutral'
    body = json.dumps(data, ensure_ascii=True).replace('<', '\\u003c')
    files = {'index.html': '<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="house/house.css">'
             '<img id="live" alt=""><main id="house"></main>'
             '<script src="defleur/ledger.js"></script><script src="defleur/gsap.min.js"></script>'
             '<script id="house-plan" type="application/json">' + body + '</script>'
             '<script src="house/components.js"></script>',
             'house/house.css': (KIT / 'content' / 'house.css').read_text(),
             'house/components.js': (KIT / 'content' / 'components.js').read_text()}
    if p['preset'] == 'neutral':
        files['house/house.css'] += '\n' + (KIT / 'content' / 'neutral.css').read_text()
    import base64
    for name in ('anton.woff2', 'inter-600.woff2'):
        files[f'house/{name}'] = {'base64': base64.b64encode((KIT / name).read_bytes()).decode()}
    return files


def native_plan(plan):
    out = copy.deepcopy(plan)
    out['house_spec'] = copy.deepcopy(plan)
    out['beats'] = [{**{k: b[k] for k in ('id', 'start', 'end', *BEAT_META)},
                     'visual_family': 'generated-image' if b['component'] == 'image-beat' else 'diagram',
                     'caption_treatment': 'show'} for b in plan['beats']]
    out.pop('duration', None)
    out['caption_suppress'], out['inserts'] = [], []
    return out


def verify_submission(project, native, duration):
    if policy(project)['preset'] != 'james':
        return
    spec = native.get('house_spec')
    if not spec:
        raise Rejected('James preset requires the app-owned house kit; resubmit structured beats, not arbitrary HTML')
    validate(spec, duration, project)
    actual = project / 'motion' / 'src'
    for name, expected in compile_files(spec, project).items():
        if isinstance(expected, dict):
            import base64
            expected = base64.b64decode(expected['base64'])
        else:
            expected = expected.encode()
        if not (actual / name).is_file() or (actual / name).read_bytes() != expected:
            raise Rejected('house kit or plan changed; resubmit and capture a new proof')


def plan_visual(project, beat_id, family, subject):
    if not isinstance(beat_id, str) or not ID.fullmatch(beat_id):
        raise Rejected('beat_id must be a lowercase identifier')
    families = registry()
    if family not in families:
        raise Rejected(f'family must be one of {list(families)}')
    f = families[family]
    subject = text(subject, 'subject', 1500)
    prompt = (f'Create illustrative art for a vertical DeFleur short. Subject: {subject}\n'
              f'Family: {f["name"]}. Workflow: {f["workflow"]}\n'
              'Composition: 9:16, exactly 1080x1920; cover-safe central focal action; protect the lower caption band '
              '(x=120..960,y=1220..1460) from essential detail. Show one concrete relationship. '
              'Use the pinned archive reference for visual vocabulary, not its literal subject. '
              'No lettering, captions, watermark, fabricated quotations, screenshots, study charts or fake evidence. '
              'Separate real-source content from recreated illustration. Preserve complete focal subjects for shaped cut-in and purposeful reveal. '
              'Never apply arbitrary drifting or repeat a generic diagram.\n'
              f'Family constraint: {f["constraint"]}')
    state = {'beat_id': beat_id, 'family': family, 'subject': subject, 'prompt': prompt, 'model': MODEL,
             'width': 1080, 'height': 1920, 'state': 'planned', 'reference': f['reference'],
             'reference_url': f'/v1/house/references/{f["reference"]["file"]}' if f['reference'].get('file') else None,
             'generation_allowed': f['generation_allowed'],
             'upload': {'create_asset_upload': {'path': f'assets/{beat_id}.png'},
                        'attach_visual': {'beat_id': beat_id, 'model': MODEL, 'asset': f'assets/{beat_id}.png'}}}
    write(under(project, 'visuals', f'{beat_id}.json'), state)
    return state


def generate_visual(project, beat_id):
    if not isinstance(beat_id, str) or not ID.fullmatch(beat_id):
        raise Rejected('invalid beat_id')
    state = read(under(project, 'visuals', f'{beat_id}.json'))
    if not state:
        raise Rejected('plan_visual first')
    if not state['generation_allowed']:
        return {**state, 'status': 'blocked', 'code': 'authentic_source_required',
                'message': 'This family needs an authentic source or same-episode host still. Do not generate documentary evidence or identities.'}
    grant = os.environ.get('WIZARD_APP_GRANT', '')
    url = os.environ.get('CONNECTION_ROUTER_URL', 'http://wizard-connection-router:8802').rstrip('/')
    # Never read host credentials or impersonate a different app. No alternate provider.
    headers = {'X-Wizard-Grant': grant} if grant else {}
    try:
        req = urllib.request.Request(url + '/v1/needs', headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            needs = json.loads(response.read(1 << 20))
    except urllib.error.HTTPError as e:
        try:
            error = json.loads(e.read(10000))
        except (ValueError, UnicodeError):
            error = {'message': f'Connection Router returned HTTP {e.code}'}
        return {**state, 'status': 'blocked', 'connection': error, 'http_status': e.code,
                'message': 'Image generation stopped; use this exact app-built prompt and reference with the pinned model, then attach_visual. No substitute provider was called.'}
    except (OSError, ValueError) as e:
        return {**state, 'status': 'blocked', 'code': 'connection_unreachable', 'message': f'Connection Router unreachable ({type(e).__name__}); no generation attempted.'}
    # Current published router run schema is text-only (system/messages/max_tokens/stream/abilities).
    # Do not fabricate an image adapter or claim text completion is image generation.
    return {**state, 'status': 'blocked', 'code': 'image_transport_not_available',
            'message': 'Connection Router is reachable but this release has no supported binary image-generation contract for gpt-image-2-high. No text route or alternate model was used.',
            'connection': needs}


def png_size(data):
    """Validate all PNG chunks/CRCs without Pillow in the service interpreter."""
    if not data.startswith(b'\x89PNG\r\n\x1a\n'):
        raise Rejected('attach_visual accepts real PNG images only')
    pos, dimensions, compressed, ended = 8, None, [], False
    while pos + 12 <= len(data):
        n = struct.unpack('>I', data[pos:pos+4])[0]
        kind = data[pos+4:pos+8]
        end = pos + 12 + n
        if end > len(data) or zlib.crc32(data[pos+4:pos+8+n]) & 0xffffffff != struct.unpack('>I', data[pos+8+n:end])[0]:
            raise Rejected('invalid PNG chunk/CRC')
        payload = data[pos+8:pos+8+n]
        if dimensions is None:
            if kind != b'IHDR' or n != 13:
                raise Rejected('invalid PNG header')
            w, h, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', payload)
            if (w, h) != (1080, 1920):
                raise Rejected('generated visual must be exactly 1080x1920 (9:16 cover-safe)')
            if depth != 8 or color not in (2, 6) or compression or filtering or interlace:
                raise Rejected('use a non-interlaced 8-bit RGB/RGBA PNG')
            dimensions = (w, h, color)
        if kind == b'IDAT':
            compressed.append(payload)
        if kind == b'IEND':
            ended = True
            if n or end != len(data):
                raise Rejected('invalid PNG ending')
            break
        pos = end
    if not ended or not compressed:
        raise Rejected('incomplete PNG')
    expected = dimensions[1] * (1 + dimensions[0] * (3 if dimensions[2] == 2 else 4))
    try:
        dec = zlib.decompressobj()
        raw = dec.decompress(b''.join(compressed), expected + 1)
        if len(raw) != expected or not dec.eof or dec.unused_data:
            raise Rejected('invalid PNG pixel data')
    except zlib.error:
        raise Rejected('invalid PNG compression') from None
    stride = 1 + dimensions[0] * (3 if dimensions[2] == 2 else 4)
    if any(raw[y * stride] > 4 for y in range(dimensions[1])):
        raise Rejected('invalid PNG scanline filters')
    return dimensions[:2]


def attach_visual(project, beat_id, asset, model):
    if model != MODEL:
        raise Rejected(f'visual model pin is {MODEL}; no alternate model accepted')
    if not isinstance(beat_id, str) or not ID.fullmatch(beat_id):
        raise Rejected('invalid beat_id')
    state = read(under(project, 'visuals', f'{beat_id}.json'))
    if not state or not state['generation_allowed']:
        raise Rejected('plan an eligible illustrative visual first')
    if asset != f'assets/{beat_id}.png':
        raise Rejected('attach the exact project-local upload path from plan_visual')
    file = under(project, 'motion', 'src', 'assets', beat_id + '.png')
    if not file.is_file() or file.is_symlink():
        raise Rejected('upload the PNG with create_asset_upload first')
    data = file.read_bytes()
    png_size(data)
    state.update(state='attached', asset=asset, sha256=hashlib.sha256(data).hexdigest(),
                 provenance='externally supplied; model is declared, not independently attested', declared_model=model)
    write(under(project, 'visuals', f'{beat_id}.json'), state)
    return state
