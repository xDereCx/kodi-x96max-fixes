# kodi-x96max-fixes

Small collection of Kodi fixes made for a CoreELEC (Omega) box running
skin **Aeon Nox 5** and the **CU LRC Lyrics** addon. Two separate
problems, two separate fixes.

## 1. `script.cu.lrclyrics.fixed/` — installable Kodi addon

A full fork of [CU LRC Lyrics](https://gitlab.com/ronie/script.cu.lrclyrics/)
(original by Taxigps/ronie, GPL-2.0-only) with two bugs fixed:

- **OK button did nothing while lyrics were shown.** The lyrics list
  control was stealing input focus, so the OK/Select action never
  reached the dialog's own handler. Fix: stopped forcing focus onto
  the lyrics list.
- **No way to reach the OSD/menu while lyrics were showing, and once
  reachable, lyrics wouldn't come back.** OK now closes the lyrics
  dialog and opens the music OSD; a background watcher then waits for
  the OSD to close and sets the addon's own `culrc.force` property
  (the same mechanism the addon already uses for its "show lyrics"
  remote button), which makes it reopen the lyrics view automatically
  — no need to leave and re-enter the visualization screen.

### Install

- **Zip install**: download/clone this repo, zip the
  `script.cu.lrclyrics.fixed/` folder, then in Kodi: Settings → Add-ons
  → Install from zip file.
- **Manual**: copy `script.cu.lrclyrics.fixed/` to your Kodi
  `addons/` directory (e.g. `/storage/.kodi/addons/` on CoreELEC),
  then enable it from Settings → Add-ons → My add-ons.
- Disable/uninstall the original `script.cu.lrclyrics` first — both
  can't run as the music lyrics service at the same time.

## 2. `skin-overrides/aeon-nox-5/` — manual skin file, not an addon

Fixes a dark horizontal band overlaying lyrics text, caused by a
`topbar.png` control in Aeon Nox 5's own override of the CU LRC
Lyrics dialog. This is a single file that belongs inside an
already-installed copy of the skin — see
[skin-overrides/aeon-nox-5/README.md](skin-overrides/aeon-nox-5/README.md)
for install steps.

## License

- `script.cu.lrclyrics.fixed/` keeps the original addon's
  GPL-2.0-only license (see its `LICENSE.txt`).
- `skin-overrides/aeon-nox-5/` is a modified copy of an Aeon Nox 5
  file, under the skin's own CC BY-NC-SA 4.0 license.
