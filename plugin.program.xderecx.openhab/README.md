# openHAB Home – Kodi add-on (`plugin.program.xderecx.openhab`)

Browse and control an [openHAB](https://www.openhab.org/) server from Kodi, in any skin:

- **Floors → rooms → devices** from openHAB's semantic model.
- **Floor plans:** rooms drawn as rectangles in your own layout, each with its temperature
  (orange = heating, red = problem). Arrows move between rooms, OK opens the room.
- **House status:** problems first (offline devices, low batteries, alarms…), then room temperatures and
  the items you choose. It can also be shown as a home-screen widget.
- **Control:** switches toggle on OK, temperature setpoints open a list of temperatures, items with options
  (e.g. a radiator valve preset) open a selection list, other numbers/strings an input dialog.
- **Languages:** English, Slovak (follows the Kodi interface language).

Nothing about a specific house is in the add-on. Floor plans, the status list, readable labels and problem
conditions are read from **item metadata** in your openHAB (namespace `kodi`, see step 3).

Requirements: openHAB 4 or 5 reachable from the Kodi box over HTTP, Kodi 19 or newer (Python 3).
Developed on openHAB 5.2 and Kodi 20 (CoreELEC).

---

## 1. openHAB: a user and an API token for Kodi

The token is stored on the Kodi box in plain text, so give Kodi its **own user with role `user`**
(can read and control items, cannot change Things or settings). Never use an admin token.

On the openHAB machine open the console (`openhab-cli console`; the console password is described in the
openHAB docs, *Administration → Console*) and run:

```
openhab:users add kodi <a new password> user
openhab:users addApiToken kodi kodi admin
```

- The password is for the new openHAB user `kodi` only (web UI login); Kodi itself uses the token.
- The token name may contain **letters and digits only** (e.g. `kodi`, not `kodi-box`), otherwise the
  command fails with "An unexpected error occurred".
- `addApiToken` prints the token (`oh.kodi.…`) once. Revoke it with `openhab:users rmApiToken kodi kodi`.

Check: with that token `GET /rest/items` works, `GET /rest/things` returns 403.

## 2. openHAB: semantic model

The add-on uses the standard semantic model (Settings → Model in the openHAB UI):

- **Floors** (`Location_Indoor_Floor`, e.g. tag `GroundFloor`/`FirstFloor` or `Floor`) are the top level.
  Outdoor locations that are not part of a floor are listed after them.
- **Rooms** and other locations are part of a floor (*isPartOf*).
- **Equipment** has a location (*hasLocation*); its **points** are the items you see and control.

Without any metadata the add-on already works as a browser (floors → rooms → equipment → points).

## 3. openHAB: metadata `kodi` (floor plans, status, labels)

Add it per item: **openHAB UI → Items → item → Add Metadata → Enter Custom Namespace → `kodi`**, or in
an `.items` file, or over the REST API (`PUT /rest/items/<item>/metadata/kodi`). Each item has one
`kodi` value plus optional config parameters.

### Floor plans

| Item | value | config |
|---|---|---|
| floor (optional) | `plan` | `w`, `h` = size of the drawing (default: bounding box of its rooms) |
| room / location | `plan` | `x`, `y`, `w`, `h` = rectangle; optional `label`, `floor` (draw it on this floor although it is not part of it in the model, e.g. a yard), `x2`, `y2`, `w2`, `h2`, `label2` = a second, non-selectable rectangle of the same room (L-shaped rooms) |

Units are up to you (cm, pixels of a drawing…); the plan is scaled to the screen. `y` grows downwards.
A floor with at least one room with a plan opens as a plan; the plan has a "Room list" button.

```
Group Kitchen "Kitchen" (GroundFloor) ["Kitchen"] { kodi="plan"[x=0, y=0, w=320, h=410] }
Group LivingRoom "Living room" (FirstFloor) ["LivingRoom"] { kodi="plan"[x=520, y=140, w=280, h=520, x2=360, y2=0, w2=440, h2=140, label2="Kitchen"] }
```

### Room temperature (shown in lists, on the plan and in the status)

Mark the points of a thermostat / radiator valve:

| value | meaning | config |
|---|---|---|
| `temperature` | measured room temperature | |
| `setpoint` | target temperature | |
| `mode` | mode / preset shown in brackets | |
| `heating` | heating indicator (room drawn orange) | `on` = state that means heating (default `ON`, e.g. `heating`) |

```
Number:Temperature Office_TRV_Temp   (Office_TRV) { kodi="temperature"[label="Room temperature"] }
Number:Temperature Office_TRV_Target (Office_TRV) { kodi="setpoint"[label="Target"] }
String             Office_TRV_Preset (Office_TRV) { kodi="mode" }
String             Office_TRV_Action (Office_TRV) { kodi="heating"[on="heating"] }
```

### Any item: label, order, hidden, status, problem

Use value `-` (or a role above) and these config parameters:

| config | effect |
|---|---|
| `label` | name shown in Kodi instead of the item label |
| `order` | position among the points of its equipment (lower first) and in the status list |
| `hidden=true` | not listed in its equipment |
| `status=true` | listed in **House status** as `label: state` |
| `problem` | condition; when the state matches, the item is listed as a problem (status list first, room red on the plan) |
| `problem_text` | text of the problem, `{state}` = current state (default: `equipment – label: state`) |

Conditions: `== ON`, `!= online`, `<= 20`, `>= 30`, `< 5`, `> 90` (numbers compared numerically, the unit is
ignored), `~ regex` (state matches), `!~ regex` (state does not match). NULL/UNDEF never match.

```
Number:Dimensionless Office_TRV_Battery (Office_TRV) { kodi="-"[label="Battery", problem="<= 20"] }
String  Office_TRV_Availability { kodi="-"[problem="!= online", problem_text="Office valve is offline"] }
Switch  Fridge_Door_Alarm       { kodi="-"[problem="== ON", problem_text="Fridge door open"] }
Switch  Boiler_Flame            { kodi="-"[status=true, label="Boiler flame", order=10] }
```

## 4. Kodi: install and settings

1. Install the repository "DereC Kodi Addons" (see the main README of this repository), then
   **Add-ons → Install from repository → DereC Kodi Addons → Program add-ons → openHAB Home**.
   If it is not listed yet: My add-ons → Add-on repository → DereC Kodi Addons → Update.
2. Add-on settings: **openHAB address** (e.g. `http://192.168.1.10:8080`) and the **API token** from step 1.

Typing the token on a remote is tedious - alternatives: paste it from a phone with a Kodi remote app with a
keyboard (Kore, Yatse), or write the settings file over SSH while Kodi is stopped (CoreELEC/LibreELEC paths;
`systemctl stop kodi` first, otherwise Kodi can overwrite the file on exit):

```
systemctl stop kodi
D=/storage/.kodi/userdata/addon_data/plugin.program.xderecx.openhab
mkdir -p $D
cat > $D/settings.xml <<'EOF'
<settings version="2">
    <setting id="url">http://<openHAB IP>:<port></setting>
    <setting id="token"><TOKEN></setting>
    <setting id="timeout">8</setting>
</settings>
EOF
systemctl start kodi
```

## 5. Main menu and widget

Every skin stores its main menu differently:

- **Aeon Nox 5:** open the add-on → "Add to the main menu (Aeon Nox 5)" (also in the add-on settings).
  It uses the first free main menu slot Custom1-6 (`Skin.SetString`, no skin file is changed), adds the
  House status widget under it and reloads the skin. The widget layout (type 1-13) can be changed in the
  settings ("Apply widget type"); "Remove from the main menu" undoes it.
- **Skins with a home menu editor** (Skin Shortcuts, e.g. Arctic Horizon 2, Estuary Mod V2): skin settings →
  customize home menu → add item → Add-on → openHAB Home; widget: Add-on → openHAB Home → House status.
- **Estuary** (default skin) has no custom main menu items: Add-ons → Program add-ons → openHAB Home.

Paths for menus, submenus and widgets:

| what | path |
|---|---|
| add-on | `RunAddon(plugin.program.xderecx.openhab)` |
| floor plan | `plugin://plugin.program.xderecx.openhab/?action=plan&name=<floor item>` |
| a room / location (list) | `plugin://plugin.program.xderecx.openhab/?action=loc&name=<location item>` |
| house status (widget) | `plugin://plugin.program.xderecx.openhab/?action=status` |

From a skin menu use `ActivateWindow(Programs,"<path>",return)` for the folder paths.
