"""Run explicitly with the packaged executable path as the only argument."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import test_media

def run(executable):
    MediaTest = test_media.MediaTest
    MediaTest.setUpClass()
    try:
        for endpoint in ('sample.m3u8', 'sample.mpd', 'page.html'):
            with tempfile.TemporaryDirectory() as directory:
                result=subprocess.run([str(Path(executable).resolve()),'--media-smoke',MediaTest.base+'/'+endpoint,directory],
                                      timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
                report=json.loads((Path(directory)/'result.json').read_text())
                assert result.returncode == 0, report
                MediaTest.ff(['-i',report['destination'],'-map','0:v:0','-map','0:a:0','-f','null','-'])
                print('PASS: packaged download and audio/video decode:',endpoint)
    finally:
        MediaTest.tearDownClass()

if __name__ == '__main__':
    run(sys.argv[1])
