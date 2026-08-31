# Aeon Nox 5 — CU LRC Lyrics fixes

Two independent fixes for this skin's CU LRC Lyrics dialog:

1. `1080i/script-cu-lrclyrics-main.xml` — removes a dark horizontal band
   overlaying song lyrics text during music playback, caused by the
   `topbar.png` image control in this skin's own override of the dialog.
2. `1080i/Font.xml` — the lyrics dialog auto-selects one of 5 decorative
   display fonts depending on line length (`lyrsh16`/`38`/`50`/`72`/`94`).
   Two of them, `PollerOne.ttf` and `Fredoka One.ttf`, are missing glyphs
   for several Latin Extended-A characters used in Slovak/Czech (Č, Ď,
   Ľ, Ĺ, Ň, Š, Ť, Ž and lowercase) - confirmed via a font cmap dump, not
   just visual inspection. Whichever line happened to get auto-sized
   into one of those two fonts would silently drop those letters, while
   other lines (using the other three fonts, which do have full
   coverage) displayed correctly - looking like a random/inconsistent
   bug rather than a font gap. Both are now pointed at
   `nasalization-rg.ttf` and `Ranchers-Regular.ttf` respectively (two of
   the already-bundled fonts confirmed to have full coverage), used
   elsewhere in this same font set.

This is **not** an installable Kodi addon — Aeon Nox 5 is a large
third-party skin and this is a one-file override that belongs inside an
already-installed copy of it. You install it by copying the file into
place manually.

## What changed

In `1080i/script-cu-lrclyrics-main.xml`, the `topbar.png` image control
(originally shown via `<visible>Control.IsVisible(120)</visible>`) is
now permanently hidden with `<visible>false</visible>`.

## Install

1. Make sure `skin.aeon.nox.5` is already installed on your Kodi device.
2. Back up the original file first:
   ```
   cp /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml.bak
   ```
3. Copy this repo's files over the originals (back up first, same as
   step 2, for `Font.xml` too if you want a rollback path):
   ```
   cp 1080i/script-cu-lrclyrics-main.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml
   cp 1080i/Font.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/Font.xml
   ```
4. Restart Kodi (`systemctl restart kodi` on CoreELEC), or reboot.

Paths above are for CoreELEC; adjust for other platforms
(`~/.kodi/addons/...` on Linux desktop, etc).

License: this file is a modified copy of an Aeon Nox 5 skin file,
distributed under the skin's own license,
[CC BY-NC-SA 4.0](https://kodi.wiki/view/Add-on:Aeon_Nox).
