#!/usr/bin/env python3
"""Optional real-download smoke test; no production mounts or published ports."""
import subprocess
import unittest

from test_startup import EGG, IMAGE, bundle


class LiveDownloadTest(unittest.TestCase):
    def test_real_stable_download_and_game_start(self):
        files = {'mods/mod-list.json': b'{"mods":[{"name":"base","enabled":true}]}'}
        env = {v['env_variable']: str(v.get('default_value', '')) for v in EGG['variables']}
        env.update(AUTO_UPDATE='1', FACTORIO_VERSION='stable', SAVE_NAME='smoke',
                   SERVER_PORT='34197', RCON_ENABLED='0', STARTUP=EGG['startup_commands']['Default'])
        # The timeout also terminates the test game. No process survives this container.
        command = '''set -e; tar -xf - -C /home/container; cd /home/container;
curl --fail --location --silent --show-error --max-time 120 https://factorio.com/get-download/2.0.47/headless/linux64 --output old.tar.xz;
tar -xf old.tar.xz --strip-components=1; rm old.tar.xz;
cp data/map-gen-settings.example.json data/map-gen-settings.json;
cp data/map-settings.example.json data/map-settings.json;
sed -e 's/"public": true/"public": false/' -e 's/"lan": true/"lan": false/' data/server-settings.example.json > data/server-settings.json;
./bin/x64/factorio --version;
./bin/x64/factorio --create saves/smoke.zip --map-gen-settings data/map-gen-settings.json --map-settings data/map-settings.json;
set +e;
timeout --signal=INT --kill-after=10s 90s /entrypoint.sh > smoke.log 2>&1;
cat smoke.log;
grep -q 'Factorio update: installed' smoke.log && grep -q 'Hosting game at' smoke.log || exit 1;
cp smoke.log first-start.log;
timeout --signal=INT --kill-after=10s 15s /entrypoint.sh > smoke.log 2>&1;
cat smoke.log;
grep -q 'Factorio update: already at' smoke.log && grep -q 'Hosting game at' smoke.log || exit 1;
./bin/x64/factorio --version;
printf 'REAL_DOWNLOAD_AND_RESTART_PASS\n';'''
        args = ['docker', 'run', '--rm', '-i', '--user', '1000:1000', '--entrypoint', 'bash']
        for name, value in env.items():
            args.extend(['-e', f'{name}={value}'])
        args.extend([IMAGE, '-c', command])
        result = subprocess.run(args, input=bundle(files), capture_output=True, timeout=300)
        output = result.stdout.decode() + result.stderr.decode()
        print(output, flush=True)
        self.assertEqual(result.returncode, 0, output)
        self.assertIn('REAL_DOWNLOAD_AND_RESTART_PASS', output)


if __name__ == '__main__':
    unittest.main(verbosity=2)
