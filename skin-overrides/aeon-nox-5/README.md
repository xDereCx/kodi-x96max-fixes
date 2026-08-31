# Aeon Nox 5 — CU LRC Lyrics fixes

Works together with `service.xderecx.musicfanart` in this repo (its
rotating artist fanart is what these patches display/refresh).

1. `1080i/script-cu-lrclyrics-main.xml` — removes a dark horizontal band
   overlaying song lyrics text during music playback, caused by the
   `topbar.png` image control in this skin's own override of the dialog.
   Also adds a full-screen background image control bound to
   `Window(Visualisation).Property(ArtistSlideshow.Image)` (the property
   `service.xderecx.musicfanart` rotates every ~12s) directly inside this
   window - see "Fanart freezing" below for why.
2. `1080i/MusicVisualisation.xml` — permanently hides the skin's own
   `Player.Art(fanart)` background image control (`<visible>false</visible>`),
   which otherwise sits on top of / instead of the rotating fanart image
   whenever a track's info tag has its own static fanart cached.
3. `1080i/Font.xml` — the lyrics dialog auto-selects one of 5 decorative
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
now permanently hidden with `<visible>false</visible>`, and a new
full-screen background `<control type="image">` was inserted at the top
of `<controls>`.

In `1080i/MusicVisualisation.xml`, the `Player.Art(fanart)` background
control's `<visible>` condition was replaced with `false`.

## Fanart freezing on one image (why two files needed changing)

`service.xderecx.musicfanart` rotates a Window property every ~12s to
cycle artist fanart images. That worked fine on the plain visualisation
screen, but the screen actually visible during playback is almost
always the CU LRC Lyrics dialog on top of it - and Kodi only actively
keeps redrawing the topmost open window each frame. The visualisation
window's own image control (bound to the rotating property) stopped
getting refreshed the instant the lyrics dialog opened, so the display
froze on whatever image happened to be showing at that moment, even
though the property kept changing correctly underneath the whole time.

The fix duplicates the same property-bound background image control
directly inside the lyrics dialog's own XML, so it refreshes as part of
that window's own active render loop instead of relying on a frozen
window underneath it. `MusicVisualisation.xml`'s own `Player.Art(fanart)`
control also had to be forced invisible since it could otherwise render
on top of / instead of the rotating image whenever the current track's
info tag had its own (static, per-track, non-rotating) cached fanart.

## Install

1. Make sure `skin.aeon.nox.5` is already installed on your Kodi device.
2. Back up the originals first:
   ```
   cp /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml.bak
   cp /storage/.kodi/addons/skin.aeon.nox.5/1080i/MusicVisualisation.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/MusicVisualisation.xml.bak
   cp /storage/.kodi/addons/skin.aeon.nox.5/1080i/Font.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/Font.xml.bak
   ```
3. Copy this repo's files over the originals:
   ```
   cp 1080i/script-cu-lrclyrics-main.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/script-cu-lrclyrics-main.xml
   cp 1080i/MusicVisualisation.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/MusicVisualisation.xml
   cp 1080i/Font.xml \
      /storage/.kodi/addons/skin.aeon.nox.5/1080i/Font.xml
   ```
4. Restart Kodi (`systemctl restart kodi` on CoreELEC), or reboot.

Paths above are for CoreELEC; adjust for other platforms
(`~/.kodi/addons/...` on Linux desktop, etc).

License: this file is a modified copy of an Aeon Nox 5 skin file,
distributed under the skin's own license,
[CC BY-NC-SA 4.0](https://kodi.wiki/view/Add-on:Aeon_Nox).
