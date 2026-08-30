# xDereCx Kodi Fixes

A Kodi addon repository of small, hand-picked fixes for addons/skins used
on a CoreELEC (Omega) box running skin **Aeon Nox 5**. Install the
repository once, then install/update addons from it directly in Kodi as
more get added over time.

## Install (one-time, on any Kodi box)

1. In Kodi: **Settings → File manager → Add source**, add
   `https://xderecx.github.io/kodi-x96max-fixes/zips/repository.xderecx.kodifixes/`
   (name it e.g. `xderecx-fixes`).
2. **Settings → Add-ons → Install from zip file**, pick the source above,
   then `repository.xderecx.kodifixes-1.0.0.zip`.
3. **Settings → Add-ons → Install from repository → xDereCx Kodi Fixes**
   — install whichever addons you want from the list.

From then on, Kodi checks this repository for updates the same way it
does for any official repo — no need to repeat the zip install step
unless the repository addon itself changes id.

This is hosted on GitHub Pages (not raw.githubusercontent.com), because
Kodi's file browser needs an actual directory listing to find the zip —
raw.githubusercontent.com only serves exact known file paths and can't
be browsed at all. `build_repo.py` generates a tiny `index.html` in
every folder under `zips/` so Kodi's browser can see what's there.

## What's in the repository

- **`script.cu.lrclyrics.fixed`** — fork of
  [CU LRC Lyrics](https://gitlab.com/ronie/script.cu.lrclyrics/)
  (original by Taxigps/ronie, GPL-2.0-only) with two fixes:
  - OK button on the remote no longer gets swallowed by the lyrics
    dialog's stolen input focus.
  - OK now shows the music OSD/menu, and the lyrics view automatically
    reopens (via the addon's own `culrc.force` mechanism) once the OSD
    is closed, instead of requiring a full navigation reset.
  - Disable/uninstall the original `script.cu.lrclyrics` first — both
    can't run as the music lyrics service at once.

- **`script.xderecx.aeonnox5lyricsfix`** — small Program add-on. Run it
  once from **Add-ons → Program add-ons** (needs `skin.aeon.nox.5`
  already installed): it patches the skin's own CU LRC Lyrics override
  file to hide the `topbar.png` control that draws a dark band over
  lyrics text during playback, keeping a one-time `.bak` of the
  original. Restart Kodi afterwards. Re-running it is a no-op if
  already applied, and it refuses to touch anything if the skin isn't
  installed or the target file looks different than expected.

- **`script.xderecx.networkwatchdog`** — small Program add-on, not a
  Kodi/skin fix but a system-level one delivered the same way. Run it
  once from **Add-ons → Program add-ons**: it installs a systemd
  oneshot service + script to `/storage/.config/` that waits up to 60s
  after boot for a `192.168.x.x` LAN IP (ignoring WireGuard/OpenVPN/PPP
  tunnel interfaces) and restarts `connman` if none shows up. Fixes
  boots where the network never comes up on its own. Confirmed working
  on x96max+. Re-running it is a no-op if already installed and
  enabled.

## Manual-install fallback (no addon)

- **`skin-overrides/aeon-nox-5/`** — the same one-file skin fix as
  `script.xderecx.aeonnox5lyricsfix` above, but as a plain file to
  copy by hand if you'd rather not run a script, or the program addon
  refuses to apply because the skin file layout changed. See
  [skin-overrides/aeon-nox-5/README.md](skin-overrides/aeon-nox-5/README.md).

## Repo layout / adding a new addon later

```
<addon-id>/          addon source, one folder per addon (must contain addon.xml)
skin-overrides/      manual-install-only skin files, not real Kodi addons
zips/                generated repository payload — do not hand-edit
build_repo.py        regenerates zips/ from the addon source folders
```

To add or update an addon:

1. Add/edit its folder at the repo root (folder name must equal the
   addon's `id` in `addon.xml`; bump `version` on any change).
2. Run `python3 build_repo.py` to regenerate `zips/`.
3. `git add -A && git commit && git push`.

Kodi picks up the new/updated addon automatically next time it checks
the repository (or via Settings → Add-ons → Check for updates).

## License

- `script.cu.lrclyrics.fixed/` keeps the original addon's
  GPL-2.0-only license (see its `LICENSE.txt`).
- `skin-overrides/aeon-nox-5/` is a modified copy of an Aeon Nox 5
  file, under the skin's own CC BY-NC-SA 4.0 license.
- `repository.xderecx.kodifixes/` (the repository addon itself) is
  GPL-2.0-only.
