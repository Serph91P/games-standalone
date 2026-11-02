# Factorio: optional updates before startup

This fork adds a normal Pelican startup variable to the vanilla AMD64 Factorio egg. It uses the existing `ghcr.io/parkervcp/yolks:debian` image. There is no custom image and no external helper script to install.

## Variables

| Pelican name | Environment variable | Default | Behavior |
| --- | --- | --- | --- |
| Update on Start | `AUTO_UPDATE` | `0` | `0`: start installed Factorio without checking or downloading. `1`: check the selected version and update before starting if needed. |
| Factorio Version | `FACTORIO_VERSION` | `latest` | `latest` or `stable`: current stable headless release. `experimental`: experimental headless release. A version such as `2.1.24`: that exact release. |

The toggle is visible and editable like Factorio Version or Maximum Slots. `1` and `0` are the accepted enabled/disabled values. Updating the selected release can also downgrade the binary if you explicitly select an older release. Saves and mods must be compatible with the selected game version.

## Import into Pelican

1. Back up existing saves, mods and configuration before enabling updates on an existing server.
2. Import/update the egg using this fork's `egg-factorio.yaml`, not the upstream URL. The embedded update URL points to this fork's feature branch so refreshing the egg does not silently restore upstream behavior.
3. For an existing server, select/copy the egg's new **Default startup command** into the server's Startup settings as needed. Importing an egg does not necessarily overwrite an existing server-specific startup command. Changing only `AUTO_UPDATE` while retaining an old command does nothing.
4. Keep `Update on Start` at `0` until ready. Set `Factorio Version` to the desired channel or release, then enable `Update on Start` (`1`).
5. Start the server and check the console for `Factorio update: installed ...` or `Factorio update: already at ...`, followed by the normal Factorio hosting message.

No reinstall is required: the update routine is self-contained in the startup command. This repository change does not import anything into an existing panel or update an existing server automatically.

## File handling and failures

- An already matching version does not download an archive. Channel selections still query Factorio's official release API; an exact version pin does not.
- Downloads come from Factorio's official HTTPS headless endpoint. They are staged in a temporary directory on the server filesystem, extracted, and checked by executing the downloaded binary with `--version` before replacing the installed distribution.
- Only distribution directories `bin` and `data` are replaced. `saves`, `mods`, root configuration/allowlists and other top-level files are not touched. The existing `data/server-settings.json`, `data/map-gen-settings.json` and `data/map-settings.json` are copied into the new distribution. Other custom changes inside `bin` or `data` are not preserved.
- Staging requires enough free disk space for the archive and new distribution while the old distribution is retained.
- When enabled, API, download, extraction or version-validation failures prevent game startup. The server does not silently run an old binary. Disable `AUTO_UPDATE` to start the installed version without an internet check.
- Activation failures attempt to restore the previous `bin`/`data`. A failed restore keeps its staging directory and prints the recovery path rather than deleting the old files. This is not a backup or a power-loss-safe transaction; force-kill or host failure during replacement can require manual recovery.
- Symlinked `bin` or `data` directories are rejected. The update requires writable server files and an AMD64-compatible host, like the original egg.
- Mods are not automatically updated. Keep separate backups before game/save migrations; a successful binary update does not guarantee mod or save compatibility.

## Verification

Pelican's native YAML importer and environment exporter are exercised in an isolated `ghcr.io/pelican/panel:v1.0.0-rc.2` container, with networking disabled and no database writes. Startup tests run as UID/GID `1000:1000` through the actual Debian yolk `/entrypoint.sh`, including its template replacement and shell evaluation. Each test container uses `--rm`, with no production mounts or published ports.

```sh
python3 -m venv .venv
.venv/bin/pip install PyYAML
.venv/bin/python factorio/factorio/test_startup.py
# Optional: downloads real current stable, starts an isolated game, restarts it,
# and verifies that the second start skips the archive download.
.venv/bin/python factorio/factorio/test_live_download.py
```

The deterministic suite uses clearly identified executable/download fixtures for old/new versions and failure injection. The separate live smoke test uses the real Factorio release API, download and executable, creates only its own disposable world, and stops it with a timeout.
