# DereC Kodi Fixes

A Kodi addon repository of small, hand-picked fixes for addons/skins used
on a CoreELEC (Omega) box running skin **Aeon Nox 5**. Install the
repository once, then install/update addons from it directly in Kodi as
more get added over time.

## Install (one-time, on any Kodi box)

1. In Kodi: **Settings → File manager → Add source**, add
   `https://xderecx.github.io/kodi-x96max-fixes/zips/repository.xderecx.kodifixes/`
   (name it e.g. `xderecx-fixes`).
2. **Settings → Add-ons → Install from zip file**, pick the source above,
   then `repository.xderecx.kodifixes-1.1.0.zip`.
3. **Settings → Add-ons → Install from repository → DereC Kodi Fixes**
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
  (original by Taxigps/ronie, GPL-2.0-only) with several fixes on top:
  - OK button on the remote no longer gets swallowed by the lyrics
    dialog's stolen input focus; OK now shows the music OSD/menu, and
    the lyrics view automatically reopens (via the addon's own
    `culrc.force` mechanism) once the OSD is closed, instead of
    requiring a full navigation reset.
  - Manual sync offset correction (up/down while timed lyrics are
    showing) restored after the focus change above had silently broken
    it. Now opens an on-screen slider (same one as the context menu's
    "Sync" option) with a "LATER <---- SYNC OFFSET ----> EARLIER"
    legend and a live readout, instead of a bare notification - the
    offset is saved into the `.lrc` file itself, so it sticks
    across replays.
  - Plain (untimed) txt lyrics no longer get stuck showing only the
    first line forever (same focus-related regression).
  - Several scraper reliability fixes: a crash in the lrclib.net
    scraper that could silently abort the entire remaining fallback
    chain; a Music163 false positive that returned songwriter-credit
    text as if it were real lyrics; and duration-aware filtering so a
    title/artist match to a different edit (radio edit, remix,
    extended version) is rejected instead of producing badly
    out-of-sync lyrics.
  - Auto-disables the original `script.cu.lrclyrics` on every Kodi
    startup if it's found installed and enabled — both can't run as the
    music lyrics service at once, and this used to be a manual step.
  - Declares `script.xderecx.aeonnox5lyricsfix` (below) as a real addon
    dependency, so Kodi installs it automatically alongside this one.
  - See the addon's own version history (`addon.xml` news) for the
    full per-version breakdown.

- **`service.xderecx.musicfanart`** ("DC Artist Artwork DL") — a
  lightweight replacement for Artist Slideshow. Looks up TheAudioDB /
  fanart.tv / Deezer for the currently playing artist and rotates
  through the results as a background image roughly every 12s, saved
  permanently into the artist's own music folder (`Fanart/` subfolder)
  so repeat plays don't re-download. Runs as a proper Kodi background
  service (started once at Kodi startup) instead of a re-invoked
  script. Needs `script.xderecx.aeonnox5lyricsfix` (below) actually
  *run* once — not just installed — to display anything at all; also
  declared as a dependency so it installs automatically.

- **`script.xderecx.aeonnox5lyricsfix`** ("Aeon Nox 5 Skin Fixes") —
  small Program add-on, and the real functional dependency behind both
  addons above. Installed automatically alongside them, but still needs
  to be **run once manually** from **Add-ons → Program add-ons** (after
  `skin.aeon.nox.5` is installed) — patching a third-party skin's files
  isn't something to do silently without asking. Patches up to 3
  `skin.aeon.nox.5` files in one confirmation, each with a one-time
  `.bak` backup, no-op for anything already applied:
  - `1080i/script-cu-lrclyrics-main.xml` — hides the `topbar.png`
    control that draws a dark band over lyrics text, and adds the
    rotating-fanart background control `service.xderecx.musicfanart`
    needs (the lyrics dialog is what's usually on screen during
    playback, and Kodi doesn't keep redrawing the window underneath an
    open dialog, so the fanart control has to live inside this same
    window to stay live).
  - `1080i/MusicVisualisation.xml` — hides the skin's own static
    `Player.Art(fanart)` background so it can't cover the rotating one.
  - `1080i/Font.xml` — fixes missing Slovak/Czech diacritics (Č, Ď, Ľ,
    Ĺ, Ň, Š, Ť, Ž) in 2 of the 5 decorative fonts the lyrics dialog
    auto-selects between depending on line length.

  Restart Kodi after running it for the changes to take effect.

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

- **`keymaps/hisense-blue-contextmenu/`** — a `custom_remote.xml` for
  `/storage/.kodi/userdata/keymaps/` that remaps the blue button on a
  Hisense TV remote (received over HDMI-CEC) to open Kodi's
  ContextMenu, since the TV's own dedicated Menu button doesn't pass
  through CEC at all on this hardware. See
  [keymaps/hisense-blue-contextmenu/README.md](keymaps/hisense-blue-contextmenu/README.md).

## Repo layout / adding a new addon later

```
<addon-id>/          addon source, one folder per addon (must contain addon.xml)
keymaps/             manual-install-only remote.xml overrides, not real Kodi addons
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
- `service.xderecx.musicfanart/` is MIT.
- `script.xderecx.aeonnox5lyricsfix/` bundles modified copies of Aeon
  Nox 5 files (`resources/skinfile/*.dat`), under the skin's own
  CC BY-NC-SA 4.0 license; the patcher script itself is CC BY-NC-SA 4.0
  too, matching what it distributes.
- `keymaps/` files are plain Kodi keymap XML, released the same way as
  the rest of this repo (CC BY-NC-SA 4.0) - not a modified copy of
  anything third-party.
- `repository.xderecx.kodifixes/` (the repository addon itself) is
  GPL-2.0-only.
