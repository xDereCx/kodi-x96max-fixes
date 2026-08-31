# Hisense TV remote — blue button → ContextMenu

Remaps the blue button on a Hisense TV remote (received by CoreELEC over
HDMI-CEC) from its Kodi default of `ActivateWindow(Pictures)` to
`ContextMenu`.

## Why

The TV's dedicated "Menu" button doesn't pass through CEC at all — it's
handled entirely on the TV side and CoreELEC never sees it (confirmed
with `cec-client -m` monitoring: repeated presses produced no
`User Control Pressed` CEC command, only routine bus polling traffic).
The coloured buttons (red/green/yellow/blue) do pass through and are
bound by Kodi's default `remote.xml` to `ActivateWindow(Videos/Music/
Pictures/TVChannels)`. Blue (→ Pictures) was picked to repurpose since
it isn't otherwise used on this box.

This makes the blue button open Kodi's context menu - useful for
addons like the CU LRC Lyrics fork in this same repo, whose sync/reload/
delete options live in a context menu.

## Install

```
cp custom_remote.xml /storage/.kodi/userdata/keymaps/custom_remote.xml
```

Restart Kodi (`systemctl restart kodi` on CoreELEC) to load it.

## Notes

- This is a **global** keymap override - it doesn't depend on the CU
  LRC Lyrics addon and will affect the blue button everywhere in Kodi.
- If you use Pictures often, remap to a different unused button instead
  (check with `cec-client -m` first to confirm your remote's button
  actually reaches CoreELEC before wiring it up).
