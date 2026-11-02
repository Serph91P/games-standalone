#!/usr/bin/env python3
"""Exercise the exported egg through the real Debian yolk entrypoint.

Requires PyYAML, Docker and the egg's Debian image. No host mounts or ports.
"""
import io
from pathlib import Path
import subprocess
import tarfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parent
EGG = yaml.safe_load((ROOT / 'egg-factorio.yaml').read_text())
IMAGE = next(iter(EGG['docker_images'].values()))


def bundle(files):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w') as archive:
        for name, content in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mode = 0o755 if name.startswith(('bin/', 'factorio/bin/', '.test-bin/')) else 0o644
            archive.addfile(info, io.BytesIO(content))
    return data.getvalue()


def binary(version):
    return (f'#!/bin/bash\nif [ "$1" = "--version" ]; then echo "Version: {version} (fixture)"; '
            'else echo "GAME_STARTED:$*"; fi\n').encode()


class StartupTests(unittest.TestCase):
    def test_pelican_import_and_variable_export(self):
        php = (ROOT / 'test_pelican_import.php').read_text().removeprefix('<?php')
        result = subprocess.run(
            ['docker', 'run', '--rm', '-i', '--network', 'none', '--entrypoint', 'php',
             'ghcr.io/pelican/panel:v1.0.0-rc.2', '-r', php],
            input=(ROOT / 'egg-factorio.yaml').read_bytes(), capture_output=True, timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout.decode() + result.stderr.decode())

    def test_update_is_an_editable_opt_in(self):
        variable = next((v for v in EGG['variables'] if v['env_variable'] == 'AUTO_UPDATE'), None)
        self.assertIsNotNone(variable, 'AUTO_UPDATE is missing from the exported egg')
        assert variable is not None
        self.assertEqual(str(variable['default_value']), '0')
        self.assertTrue(variable['user_viewable'])
        self.assertTrue(variable['user_editable'])
        self.assertIn('boolean', variable['rules'])

    def run_startup(self, enabled='0', version='stable', installed='2.0.47', curl_mode='ok',
                    candidate='2.1.24', fail_move=False):
        payload = bundle({'factorio/bin/x64/factorio': binary(candidate),
                          'factorio/data/core/version.txt': b'new bundled data',
                          'factorio/data/server-settings.json': b'package default'})
        files = {'bin/x64/factorio': binary(installed),
                 'data/server-settings.json': b'custom-server',
                 'data/map-gen-settings.json': b'custom-map-gen',
                 'data/map-settings.json': b'custom-map',
                 'saves/gamesave.zip': b'save-sentinel',
                 'mods/mod-list.json': b'mods-sentinel',
                 '.test-download.tar': payload}
        files['.test-bin/curl'] = b'''#!/bin/bash
printf '%s\n' "$*" >> /home/container/.curl-calls
if [ "$CURL_MODE" = "fail" ]; then exit 22; fi
case "$*" in
 *latest-releases*)
 if [ "$CURL_MODE" = "invalid_api" ]; then echo '{}';
 else echo '{"experimental":{"headless":"2.1.25"},"stable":{"headless":"2.1.24"}}'; fi;;
 *)
 if [ "$CURL_MODE" = "download_fail" ]; then exit 22; fi
 output=""
 while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ] || [ "$1" = "--output" ]; then shift; output="$1"; fi
  shift
 done
 if [ "$CURL_MODE" = "corrupt" ]; then echo invalid > "$output";
 else cp /home/container/.test-download.tar "$output"; fi;;
esac
'''
        if fail_move:
            files['.test-bin/mv'] = b'''#!/bin/bash
case "$1" in *.factorio-update.*/factorio/data) exit 1;; esac
exec /usr/bin/mv "$@"
'''
        command = '''tar -xf - -C /home/container; cd /home/container;
export PATH="/home/container/.test-bin:$PATH";
/entrypoint.sh; code=$?;
printf '\nRESULT:%s\n' "$code";
./bin/x64/factorio --version;
for f in data/server-settings.json data/map-gen-settings.json data/map-settings.json saves/gamesave.zip mods/mod-list.json; do printf '\nPRESERVED:%s:' "$f"; cat "$f"; done;
if [ -f .curl-calls ]; then printf '\nCURL_CALLS\n'; cat .curl-calls; fi;
find . -maxdepth 1 -name '.factorio-update.*' -printf 'LEFTOVER:%f\n';
exit "$code"'''
        env = {v['env_variable']: str(v.get('default_value', '')) for v in EGG['variables']}
        env.update(AUTO_UPDATE=enabled, FACTORIO_VERSION=version, SAVE_NAME='gamesave',
                   SERVER_PORT='34197', RCON_ENABLED='0', CURL_MODE=curl_mode,
                   STARTUP=EGG['startup_commands']['Default'])
        args = ['docker', 'run', '--rm', '-i', '--user', '1000:1000', '--entrypoint', 'bash']
        for name, value in env.items():
            args.extend(['-e', f'{name}={value}'])
        args.extend([IMAGE, '-c', command])
        result = subprocess.run(args, input=bundle(files), capture_output=True, timeout=90)
        output = result.stdout.decode() + result.stderr.decode()
        for name, value in [('data/server-settings.json', 'custom-server'),
                            ('data/map-gen-settings.json', 'custom-map-gen'),
                            ('data/map-settings.json', 'custom-map'),
                            ('saves/gamesave.zip', 'save-sentinel'),
                            ('mods/mod-list.json', 'mods-sentinel')]:
            self.assertIn(f'PRESERVED:{name}:{value}', output)
        self.assertNotIn('LEFTOVER:.factorio-update.', output)
        return result.returncode, output

    def test_disabled_starts_installed_version_without_network(self):
        code, output = self.run_startup(curl_mode='fail')
        self.assertEqual(code, 0, output)
        self.assertIn('GAME_STARTED:', output)
        self.assertIn('Version: 2.0.47', output)
        self.assertNotIn('CURL_CALLS', output)

    def test_enabled_updates_before_starting(self):
        code, output = self.run_startup(enabled='1')
        self.assertEqual(code, 0, output)
        self.assertIn('Version: 2.1.24', output)
        self.assertIn('GAME_STARTED:', output)
        self.assertIn('/get-download/2.1.24/headless/linux64', output)

    def test_current_version_skips_archive_download(self):
        code, output = self.run_startup(enabled='1', installed='2.1.24')
        self.assertEqual(code, 0, output)
        self.assertIn('Factorio update: already at 2.1.24', output)
        self.assertNotIn('https://factorio.com/get-download/2.1.24/', output)

    def test_latest_selects_stable(self):
        code, output = self.run_startup(enabled='1', version='latest')
        self.assertEqual(code, 0, output)
        self.assertIn('Factorio update: installed 2.1.24', output)

    def test_experimental_selects_experimental(self):
        code, output = self.run_startup(enabled='1', version='experimental', candidate='2.1.25')
        self.assertEqual(code, 0, output)
        self.assertIn('Factorio update: installed 2.1.25', output)

    def test_pin_skips_release_api(self):
        code, output = self.run_startup(enabled='1', version='2.1.24')
        self.assertEqual(code, 0, output)
        calls = output.split('CURL_CALLS\n', 1)[1]
        self.assertNotIn('latest-releases', calls)

    def test_failed_updates_never_start_or_replace_installed_version(self):
        for mode in ('fail', 'download_fail', 'corrupt', 'invalid_api'):
            with self.subTest(mode=mode):
                code, output = self.run_startup(enabled='1', curl_mode=mode)
                self.assertNotEqual(code, 0, output)
                self.assertNotIn('GAME_STARTED:', output)
                self.assertIn('Version: 2.0.47', output)

    def test_wrong_download_version_is_rejected(self):
        code, output = self.run_startup(enabled='1', version='2.1.25')
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('GAME_STARTED:', output)
        self.assertIn('Version: 2.0.47', output)

    def test_invalid_version_is_rejected_without_network(self):
        code, output = self.run_startup(enabled='1', version='not-a-version')
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('GAME_STARTED:', output)
        self.assertNotIn('CURL_CALLS', output)

    def test_failed_activation_restores_original_binary_and_config(self):
        code, output = self.run_startup(enabled='1', fail_move=True)
        self.assertNotEqual(code, 0, output)
        self.assertNotIn('GAME_STARTED:', output)
        self.assertIn('Version: 2.0.47', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
