# Aeon Nox 5 — CU LRC Lyrics topbar fix

Fixes a dark horizontal band overlaying song lyrics text during music
playback, caused by the `topbar.png` image control in this skin's own
override of the CU LRC Lyrics dialog.

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
3. Copy this repo's file over it:
   ```
   cp 1080i/script-cu-lrclyrics-main.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml
   ```
4. Restart Kodi (`systemctl restart kodi` on CoreELEC), or reboot.

Paths above are for CoreELEC; adjust for other platforms
(`~/.kodi/addons/...` on Linux desktop, etc).

License: this file is a modified copy of an Aeon Nox 5 skin file,
distributed under the skin's own license,
[CC BY-NC-SA 4.0](https://kodi.wiki/view/Add-on:Aeon_Nox).
