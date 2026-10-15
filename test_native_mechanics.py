"""Focused PCM custody and video-only shot-boundary regressions (stdlib fixtures)."""
import copy
import json
import tempfile
import unittest
import wave
from pathlib import Path

import editing
import face_audit
import final_render
import workflow


class PCMIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source, self.edited = self.root / 'source.wav', self.root / 'edited.wav'
        self.pcm = b''.join(i.to_bytes(2, 'little', signed=True) for i in range(1000))
        self.wav(self.source, self.pcm)
        self.wav(self.edited, self.pcm[200:1600])
        self.block = dict(start_s=.1, end_s=.8, start_sample=100, end_sample=800,
                          output_start=0., output_end=.7, output_start_sample=0, output_end_sample=700)
        self.edit = dict(sample_rate=1000, channels=1, samples=700, duration=.7, segments=[self.block])
        self.word = dict(word='in.', index=0, start=.65, end=.75)

    def wav(self, path, pcm, rate=1000, channels=1):
        with wave.open(str(path), 'wb') as w:
            w.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
            w.writeframes(pcm)

    def review(self, word=None):
        w = word or self.word
        return editing.edit_word_review([w], ['on.'], [self.block], 1., [w])

    def resolve(self, word=None):
        w = word or self.word
        proof = editing.pcm_identity(self.source, self.edited, self.edit)
        return editing.resolve_pcm_variance(self.review(w), [w], self.edit, proof)

    def test_near_word_resolved_only_by_fresh_complete_pcm_proof(self):
        self.assertTrue(self.review()['fail'])
        proof = editing.pcm_identity(self.source, self.edited, self.edit)
        self.assertTrue(proof['pass'])
        r = self.resolve()
        self.assertFalse(r['fail'])
        self.assertEqual(r['lost'], ['in'])
        self.assertEqual(r['added'], ['on'])
        self.assertEqual(len(r['lost_near_cuts_original']), 1)
        self.assertEqual(r['asr_variance_pcm_verified'][0]['pcm_evidence']['word_samples'], 100)

    def test_truncated_offset_and_mutated_pcm_fail(self):
        for pcm in (self.pcm[200:1598], self.pcm[202:1602], self.pcm[200:700]+b'xx'+self.pcm[702:1600]):
            with self.subTest(size=len(pcm)):
                self.wav(self.edited, pcm)
                self.assertFalse(editing.pcm_identity(self.source, self.edited, self.edit)['pass'])
                self.assertTrue(self.resolve()['fail'])

    def test_rate_channels_and_map_offsets_fail(self):
        for rate, ch in ((2000, 1), (1000, 2)):
            self.wav(self.edited, self.pcm[200:1600], rate, ch)
            self.assertFalse(editing.pcm_identity(self.source, self.edited, self.edit)['pass'])
        self.wav(self.edited, self.pcm[200:1600])
        for key, value in [('output_start_sample', 1), ('end_s', .79), ('start_sample', 101)]:
            e = copy.deepcopy(self.edit); e['segments'][0][key] = value
            self.assertFalse(editing.pcm_identity(self.source, self.edited, e)['pass'])

    def test_crossing_collapsed_nonfinite_timing_never_resolved(self):
        for a, b in ((.75, .85), (.7, .7), (.75, .65), (.65, float('nan'))):
            w = dict(self.word, start=a, end=b)
            self.assertTrue(self.resolve(w)['fail'])

    def test_proof_cannot_be_reused_for_another_map(self):
        proof = editing.pcm_identity(self.source, self.edited, self.edit)
        other = copy.deepcopy(self.edit); other['segments'][0]['start_s'] = .11
        r = editing.resolve_pcm_variance(self.review(), [self.word], other, proof)
        self.assertTrue(r['fail'])


class ShotRangesTests(unittest.TestCase):
    def setUp(self):
        self.edit = dict(fps='24', frames=48, duration=2., source_frame_indices=list(range(120, 168)),
                         segments=[dict(start_s=5., end_s=7., output_start=0., output_end=2.)])

    def test_video_only_source_frame_boundary_exact_coverage(self):
        before = copy.deepcopy(self.edit)
        ranges = face_audit.visual_ranges(self.edit, {'shot_boundaries': [{'source_frame': 139}]})
        self.assertEqual(self.edit, before)
        self.assertEqual([(r['output_start'], r['output_end']) for r in ranges], [(0., 19/24), (19/24, 2.)])
        self.assertEqual(ranges[0]['source_frames'][-1], 138)
        self.assertEqual(ranges[1]['source_frames'][0], 139)
        self.assertTrue(ranges[1]['force_setup'])
        ledger = {'ranges': [dict(start=r['output_start'], end=r['output_end'], crop=[i, 0, 4, 8]) for i,r in enumerate(ranges)]}
        for f in range(48):
            self.assertEqual(final_render.crop_at(ledger, f/24)[0], int(f >= 19))

    def test_time_boundary_and_segment_compatibility(self):
        a = face_audit.visual_ranges(self.edit, {'shot_boundaries': [{'source_frame': 139}]})
        b = face_audit.visual_ranges(self.edit, {'shot_boundaries': [{'source_s': 139/24}]})
        self.assertEqual(a, b)
        self.assertEqual(len(face_audit.visual_ranges(self.edit, {})), 1)
        self.assertEqual(face_audit.visual_ranges(self.edit, {'targets': {'0': 'right'}})[0]['target'], 'right')

    def test_invalid_and_unmapped_boundaries_rejected(self):
        for row in ({'source_frame': True}, {'source_frame': -1}, {'source_frame': 139.5},
                    {'source_s': float('nan')}, {'source_s': 5.81}, {'source_frame': 999},
                    {'source_frame': 139, 'source_s': 139/24}, {'source_frame': 120}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                face_audit.visual_ranges(self.edit, {'shot_boundaries': [row]})
        with self.assertRaises(ValueError):
            face_audit.visual_ranges(self.edit, {'shot_boundaries': [{'source_frame': 140}, {'source_frame': 139}]})

    def test_schema_accepts_shots_rejects_bad_types(self):
        workflow._framing({'shot_boundaries': [{'source_frame': 139}]}, 1)
        for row in ({'source_frame': True}, {'source_s': float('inf')}, {'source_frame': 139, 'other': 1}):
            with self.assertRaises(workflow.Rejected):
                workflow._framing({'shot_boundaries': [row]}, 1)

    def test_coverage_gap_fails_closed(self):
        with self.assertRaises(ValueError):
            final_render.crop_at({'ranges': [{'start': 0., 'end': .5, 'crop': [0,0,4,8]},
                                            {'start': 1., 'end': 2., 'crop': [1,0,4,8]}]}, .75)


if __name__ == '__main__':
    unittest.main()
