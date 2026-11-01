"""House policy tests. Synthetic PNGs are test fixtures, never generation evidence."""
import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import zlib

import house
import motion
from editing import Rejected


def beat(component='meter', start=3.5, end=6.5, ident='first'):
    return {'id': ident, 'component': component, 'start': start, 'end': end,
            'labels': ['HEALTHY'], 'font': 'Anton', 'color': '#e9b45c',
            'phases': [{'at': start+.2, 'word': 'healthy', 'action': 'transform'}],
            'spoken_anchor': 'a healthy level of skepticism', 'viewer_inference': 'Balance is useful',
            'state_before': 'Trust all', 'state_after': 'Healthy skepticism',
            'causal_action': 'The needle settles on healthy', 'speaker_return': 'Full speaker after end'}


def png(w=1080,h=1920):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    raw=(b'\0'+b'\x10\x20\x30'*w)*h
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')


class HouseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR'))
        self.root=Path(self.temp.name)
        self.plan={'duration':20,'beats':[beat()]}

    def tearDown(self):
        self.temp.cleanup()

    def reject(self, change, message, plan=None):
        p=copy.deepcopy(plan or self.plan);change(p)
        with self.assertRaisesRegex(Rejected,message): house.validate(p)

    def test_palette(self):
        self.reject(lambda p:p['beats'][0].update(color='#00ff00'),'palette')
        self.reject(lambda p:p['beats'][0].update(color='var(--anything)'),'palette')

    def test_font(self):
        self.reject(lambda p:p['beats'][0].update(font='Comic Sans'),'house fonts')

    def test_text_heavy_cards_rejected(self):
        self.reject(lambda p:p['beats'][0].update(labels=['This is a long sentence for the viewer to read']),'text-heavy cards rejected')
        self.reject(lambda p:p['beats'][0].update(labels=['ONE']*7),'too many labels')

    def test_spoken_line_not_duplicated(self):
        self.reject(lambda p:p['beats'][0].update(labels=['A HEALTHY LEVEL OF']),'repeat the spoken line')

    def test_first_visual_window(self):
        for start in (0,2.9,5.1,14.565):
            self.reject(lambda p:p['beats'][0].update(start=start,end=start+2,phases=[{'at':start+.2,'word':'healthy','action':'reveal'}]),'first meaningful visual')
        for start in (3,5):
            b=beat(start=start,end=start+2);house.validate({'duration':20,'beats':[b]})

    def test_beat_limit(self):
        self.reject(lambda p:p['beats'][0].update(end=15.2),'maximum beat length')
        b=beat(end=15.1);house.validate({'duration':40,'beats':[b]})

    def test_finite_and_boolean_numbers(self):
        for v in (True,float('nan'),float('inf'),-1,'3.5'):
            self.reject(lambda p:p.update(duration=v),'finite number')

    def test_return_to_speaker_and_closing_thought(self):
        self.reject(lambda p:p['beats'].append(beat('population',6.7,8,'second')),'return to the speaker')
        self.reject(lambda p:p['beats'][0].update(speaker_return=''),'speaker_return')
        self.reject(lambda p:p.update(duration=6.6),'closing thought')

    def test_coverage(self):
        b=beat(end=14);self.reject(lambda p:p.update(beats=[b]),'coverage')

    def test_generic_same_motion_graphics_throughout_is_rejected(self):
        p={'duration':40,'beats':[beat(start=3.5,end=6,ident='one'),beat(start=12,end=15,ident='two'),beat(start=25,end=28,ident='three')]}
        with self.assertRaisesRegex(Rejected,'generic same motion graphics throughout is rejected'):house.validate(p)

    def test_mix_even_when_motion_components_differ(self):
        p={'duration':40,'beats':[beat('lifeline',3.5,6,'one'),beat('population',12,15,'two'),beat('meter',25,28,'three')]}
        with self.assertRaisesRegex(Rejected,'mix rule'):house.validate(p)
        policy=house.set_policy(self.root,{'mix_required':False,'reason':'Owner chose independent motion-only module'})
        house.validate(p,configuration=policy)
        self.assertFalse(house.policy(self.root)['mix_required'])

    def test_mix_threshold_and_valid_image_mechanism_image(self):
        p={'duration':40,'beats':[beat('image-beat',3.5,6,'one'),beat('population',12,15,'two'),beat('image-beat',25,28,'three')]}
        for b in (p['beats'][0],p['beats'][2]):b.update(visual_id=b['id'],labels=[])
        house.validate(p)
        # No fake claim that fixture image bytes were generated or attached.
        with self.assertRaisesRegex(Rejected,'attach the generated PNG'):house.validate(p,project=self.root)
        p={'duration':29,'beats':[beat('lifeline',3.5,6,'one'),beat('population',12,15,'two'),beat('meter',20,23,'three')]}
        house.validate(p)

    def test_pivot_validation(self):
        self.reject(lambda p:p['beats'][0].update(phases=[]),'spoken pivots')
        self.reject(lambda p:p['beats'][0]['phases'][0].update(at=8),'inside the beat')
        self.reject(lambda p:p['beats'][0]['phases'][0].update(word='fabricated'),'spoken_anchor')
        self.reject(lambda p:p['beats'][0]['phases'][0].update(action='spin-forever'),'action')

    def test_unknown_custom_properties_rejected(self):
        self.reject(lambda p:p['beats'][0].update(css='background:red'),'unknown properties')
        self.reject(lambda p:p.update(caption_suppress=[{'start':4,'end':5}]),'no custom CSS/HTML')
        self.reject(lambda p:p['beats'][0].update(component='generic-card'),'app-owned component')

    def test_native_kit_compilation_and_tamper_detection(self):
        spec=house.validate(self.plan,project=self.root)
        result=motion.submit(self.root,house.compile_files(spec,self.root),house.native_plan(spec),20)
        self.assertTrue(result['submitted'])
        house.verify_submission(self.root,result['plan'],20)
        with self.assertRaisesRegex(Rejected,'closing thought'):house.verify_submission(self.root,result['plan'],6.6)
        (self.root/'motion/src/house/components.js').write_text('window.renderFrame=()=>{}')
        with self.assertRaisesRegex(Rejected,'house kit or plan changed'):house.verify_submission(self.root,result['plan'],20)

    def test_neutral_keeps_a_monochrome_typed_kit(self):
        p=house.set_policy(self.root,{'preset':'neutral','reason':'Explicit neutral project'})
        self.plan['beats'][0]['color']=p['default_color']
        configuration={**house.policy(),**p,'preset':'james'}
        validated=house.validate(self.plan,project=self.root,configuration=configuration)
        files=house.compile_files(validated,self.root)
        self.assertIn('"neutral": true',files['index.html'])
        self.assertIn('--house-gold:#f3ece2',files['house/house.css'])
        self.assertIn('plan.neutral ?',files['house/components.js'])
        self.assertIn('house/anton.woff2',files)

    def test_neutral_explicit_and_reason_required(self):
        self.assertEqual(house.policy(self.root)['preset'],'james')
        with self.assertRaises(Rejected):house.set_policy(self.root,{'preset':'neutral'})
        house.set_policy(self.root,{'preset':'neutral','reason':'Explicit custom-composition compatibility test'})
        self.assertEqual(house.policy(self.root)['preset'],'neutral')
        house.verify_submission(self.root,{},20)

    def test_model_pin_size_and_image_hash(self):
        p=house.plan_visual(self.root,'art','cinematic-metaphor','A concrete test subject, not owner creative content')
        file=self.root/'motion/src/assets/art.png';file.parent.mkdir(parents=True);file.write_bytes(png())
        with self.assertRaisesRegex(Rejected,'model pin'):house.attach_visual(self.root,'art','assets/art.png','other-model')
        file.write_bytes(png(540,960))
        with self.assertRaisesRegex(Rejected,'1080x1920'):house.attach_visual(self.root,'art','assets/art.png',house.MODEL)
        file.write_bytes(png());attached=house.attach_visual(self.root,'art','assets/art.png',house.MODEL)
        self.assertEqual(attached['sha256'],hashlib.sha256(file.read_bytes()).hexdigest())
        self.assertIn('not independently attested',attached['provenance'])
        b=beat('image-beat');b.update(labels=[],visual_id='art')
        house.validate({'duration':20,'beats':[b]},project=self.root)
        file.write_bytes(png()+b'changed')
        with self.assertRaisesRegex(Rejected,'bytes changed'):house.validate({'duration':20,'beats':[b]},project=self.root)

    def test_corrupt_png_rejected_not_only_header_sniffed(self):
        good=png()
        for data in (good[:24],good[:-12],good+b'extra',good[:40]+b'X'+good[41:]):
            with self.assertRaises(Rejected):house.png_size(data)

    def test_prompt_families_references_and_no_fake_evidence(self):
        self.assertEqual(len(house.registry()),7)
        for family in house.registry():
            p=house.plan_visual(self.root,'test',family,'Test subject')
            self.assertEqual(p['model'],'gpt-image-2-high')
            self.assertIn('1080x1920',p['prompt'])
            self.assertIn('fake evidence',p['prompt'])
            ref=p['reference']
            if ref.get('file'):
                self.assertEqual(hashlib.sha256((house.KIT/'references'/ref['file']).read_bytes()).hexdigest(),ref['sha256'])
        with self.assertRaises(Rejected):house.plan_visual(self.root,'../escape','comic-satire','x')

    def test_unreachable_connection_returns_exact_prompt_no_substitute(self):
        planned=house.plan_visual(self.root,'art','comic-satire','A bounded test subject')
        with patch('house.urllib.request.urlopen',side_effect=OSError('offline')) as request:
            out=house.generate_visual(self.root,'art')
        self.assertEqual(request.call_count,1)
        self.assertEqual(out['status'],'blocked');self.assertEqual(out['code'],'connection_unreachable')
        self.assertEqual(out['prompt'],planned['prompt']);self.assertEqual(out['reference'],planned['reference'])

    def test_no_image_transport_does_not_call_a_text_run(self):
        house.plan_visual(self.root,'art','comic-satire','Test subject')
        class Response:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,*a):return b'{"needs":{}}'
        with patch('house.urllib.request.urlopen',return_value=Response()) as request:
            out=house.generate_visual(self.root,'art')
        self.assertEqual(request.call_count,1)
        self.assertEqual(out['code'],'image_transport_not_available')

    def test_approved_historical_compositions_and_explicit_exceptions(self):
        for name in ('v3','v31'):
            fixture=json.loads((house.KIT/'fixtures'/f'{name}.json').read_text())
            policy={**house.policy(),**fixture['historical_project_policy']}
            approved=house.validate(fixture['plan'],configuration=policy)
            self.assertGreater(len(approved['beats']),0)
            motion.validate_plan(house.native_plan(approved),approved['duration'],set())
        v31=json.loads((house.KIT/'fixtures/v31.json').read_text())
        with self.assertRaisesRegex(Rejected,'mix rule'):house.validate(v31['plan'])


if __name__=='__main__':unittest.main(verbosity=2)
