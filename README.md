# xDereCx Kodi Fixes

A Kodi addon repository of small, hand-picked fixes for addons/skins used
on a CoreELEC (Omega) box running skin **Aeon Nox 5**. Install the
repository once, then install/update addons from it directly in Kodi as
more get added over time.

## Install (one-time)

1. In Kodi: **Settings → File manager → Add source**, add
   `https://raw.githubusercontent.com/xDereCx/kodi-x96max-fixes/master/zips/repository.xderecx.kodifixes/`
   (name it e.g. `xderecx-fixes`).
2. **Settings → Add-ons → Install from zip file**, pick the source above,
   then `repository.xderecx.kodifixes-1.0.0.zip`.
3. **Settings → Add-ons → Install from repository → xDereCx Kodi Fixes**
   — install whichever addons you want from the list.

From then on, Kodi checks this repository for updates the same way it
does for any official repo — no need to repeat the zip install step
unless the repository addon itself changes id.

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

## Not in the repository (manual install only)

- **`skin-overrides/aeon-nox-5/`** — a single skin XML file fixing a
  dark band overlaying lyrics text in Aeon Nox 5. This can't be a
  Kodi-repository addon: it's a one-file override that has to be
  copied into an *already-installed* copy of that (large, third-party)
  skin. See
  [skin-overrides/aeon-nox-5/README.md](skin-overrides/aeon-nox-5/README.md)
  for manual install steps.

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
