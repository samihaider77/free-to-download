"""Real HLS/DASH fixture tests, including a full audio/video decode."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
import imageio_ffmpeg
from media import MediaDownload


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args): pass
    def send_error(self, code, message=None, explain=None):
        if code == 404:
            print('Missing fixture resource:', self.path)
        super().send_error(code, message, explain)


class MediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cls.ff(['-f','lavfi','-i','testsrc=size=160x90:rate=12','-f','lavfi','-i','sine=frequency=440',
                '-t','3','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(cls.root/'source.mp4')])
        cls.ff(['-i',str(cls.root/'source.mp4'),'-c','copy','-hls_time','1','-hls_list_size','0',str(cls.root/'sample.m3u8')])
        cls.ff(['-i',str(cls.root/'source.mp4'),'-c','copy','-f','dash',str(cls.root/'sample.mpd')])
        # Two renditions (720p and 360p) to check the quality choice.
        cls.ff(['-i',str(cls.root/'source.mp4'),'-filter_complex','[0:v]split=2[a][b];[a]scale=1280:720[hi];[b]scale=640:360[lo]',
                '-map','[hi]','-map','[lo]','-map','0:a','-c:v','libx264','-preset','ultrafast','-c:a','aac','-f','dash',
                '-init_seg_name','multi-init-$RepresentationID$.m4s','-media_seg_name','multi-$RepresentationID$-$Number%05d$.m4s',
                str(cls.root/'multi.mpd')])
        # LinkedIn labels DASH pieces with a nonstandard video/iso.segment MIME type.
        (cls.root/'linkedin.mpd').write_text((cls.root/'sample.mpd').read_text()
            .replace('mimeType="video/mp4"','mimeType="video/iso.segment"').replace('mimeType="audio/mp4"','mimeType="audio/iso.segment"'))
        # LinkedIn-style fMP4 HLS: a separate header-only init.mp4 plus numbered fragments.
        cls.ff(['-i',str(cls.root/'source.mp4'),'-c','copy','-f','hls','-hls_time','1','-hls_list_size','0',
                '-hls_segment_type','fmp4','-hls_fmp4_init_filename','init.mp4',str(cls.root/'fmp4.m3u8')])
        (cls.root/'page.html').write_text('<html><head><title>Fixture</title></head><body><video src="source.mp4"></video></body></html>')
        cls.server = ThreadingHTTPServer(('127.0.0.1',0),partial(Quiet,directory=str(cls.root)))
        threading.Thread(target=cls.server.serve_forever,daemon=True).start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def ff(cls, args):
        return subprocess.run([cls.ffmpeg,'-hide_banner','-loglevel','error','-y',*args],check=True,capture_output=True,cwd=cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.tmp.cleanup()

    def test_hls_dash_page_and_direct_decode_audio_and_video(self):
        for endpoint in ('sample.m3u8','sample.mpd','page.html','source.mp4','fmp4.m3u8','linkedin.mpd'):
            with self.subTest(endpoint=endpoint), tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                job=MediaDownload(self.base+'/'+endpoint,root/'result.mkv',root/'parts',4)
                job.run()
                self.assertEqual(job.status,'Complete',job.error)
                self.assertTrue(job.destination.exists())
                # No duplicate working copy is left behind once the file is published.
                self.assertFalse((root/'parts').exists())
                self.ff(['-i',str(job.destination),'-map','0:v:0','-map','0:a:0','-f','null','-'])

    def test_quality_choice_and_audio_only(self):
        import re
        for quality,height in (('best',720),('480',360),('720',720)):
            with self.subTest(quality=quality), tempfile.TemporaryDirectory() as folder:
                job=MediaDownload(self.base+'/multi.mpd',Path(folder)/'out.mkv',Path(folder)/'parts',quality=quality)
                self.assertEqual(job.run(),'Complete',job.error)
                probe=subprocess.run([self.ffmpeg,'-hide_banner','-i',str(job.destination)],capture_output=True,text=True).stderr
                self.assertEqual(int(re.search(r'Video: .*?, (\d+)x(\d+)',probe)[2]),height)
        with tempfile.TemporaryDirectory() as folder:
            job=MediaDownload(self.base+'/source.mp4',Path(folder)/'out.mp3',Path(folder)/'parts',quality='audio')
            self.assertEqual(job.run(),'Complete',job.error)
            self.assertEqual(job.destination.suffix,'.mp3')
            probe=subprocess.run([self.ffmpeg,'-hide_banner','-i',str(job.destination)],capture_output=True,text=True).stderr
            self.assertIn('Audio: mp3',probe)
            self.assertNotIn('Video:',probe)

    def test_header_only_init_segment_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            job=MediaDownload(self.base+'/init.mp4',Path(folder)/'out.mkv',Path(folder)/'parts')
            self.assertEqual(job.run(),'Error')
            self.assertIn('piece of a stream',job.error)
            self.assertFalse(list(Path(folder).glob('out.*')))

    def test_pause_before_start(self):
        with tempfile.TemporaryDirectory() as folder:
            job=MediaDownload(self.base+'/source.mp4',Path(folder)/'out.mkv',Path(folder)/'parts')
            job.pause(); self.assertEqual(job.run(),'Paused')

    def test_pause_and_resume_and_destination_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            job=MediaDownload(self.base+'/sample.m3u8',root/'out.mkv',root/'parts')
            original=job.check
            def interrupt():
                if job.received:
                    job.pause()
                original()
            job.check=interrupt
            self.assertEqual(job.run(),'Paused',job.error)
            self.assertFalse(job.destination.exists())
            job.check=original; job.stop.clear()
            self.assertEqual(job.run(),'Complete',job.error)
            first=job.destination; saved=first.read_bytes()
            # A stream URL has no real title, so a second copy is saved beside the first, never over it.
            self.assertEqual(job.run(),'Complete',job.error)
            self.assertNotEqual(job.destination,first)
            self.assertEqual(first.read_bytes(),saved)

    def test_same_titled_video_reports_already_downloaded(self):
        import yt_dlp.extractor.generic as generic
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            original=generic.GenericIE._real_extract
            # Pretend a site extractor recognised the video and gave it a real title.
            def titled(ie,url):
                info=original(ie,url); info.update(title='Fiery Spell',extractor_key='Youtube'); return info
            generic.GenericIE._real_extract=titled
            try:
                job=MediaDownload(self.base+'/source.mp4',root/'placeholder.mkv',root/'parts')
                self.assertEqual(job.run(),'Complete',job.error)
                saved=job.destination; data=saved.read_bytes()
                again=MediaDownload(self.base+'/source.mp4',root/'placeholder (1).mkv',root/'parts2')
                self.assertEqual(again.run(),'Complete',again.error)
            finally:
                generic.GenericIE._real_extract=original
            self.assertTrue(again.already_exists)
            self.assertEqual(again.destination,saved)
            self.assertEqual(saved.read_bytes(),data)
            self.assertEqual(sorted(p.name for p in root.glob('Fiery*')),['Fiery Spell.mp4'])
