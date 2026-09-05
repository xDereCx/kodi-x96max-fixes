import os
import shutil
import subprocess
import sys
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
BUNDLED_SCRIPT = os.path.join(ADDON_PATH, 'resources', 'files', 'network-watchdog.sh')
BUNDLED_SERVICE = os.path.join(ADDON_PATH, 'resources', 'files', 'network-watchdog.service')

TARGET_SCRIPT = '/storage/.config/network-watchdog.sh'
TARGET_SERVICE_DIR = '/storage/.config/system.d'
TARGET_SERVICE = os.path.join(TARGET_SERVICE_DIR, 'network-watchdog.service')

DIALOG = xbmcgui.Dialog()


def read(path):
    with open(path, 'rb') as f:
        return f.read()


def already_installed():
    if not (os.path.isfile(TARGET_SCRIPT) and os.path.isfile(TARGET_SERVICE)):
        return False
    return read(TARGET_SCRIPT) == read(BUNDLED_SCRIPT) and read(TARGET_SERVICE) == read(BUNDLED_SERVICE)


def enabled():
    result = subprocess.run(
        ['systemctl', 'is-enabled', 'network-watchdog.service'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return result.stdout.strip() == b'enabled'


def main():
    if not (os.path.isfile(BUNDLED_SCRIPT) and os.path.isfile(BUNDLED_SERVICE)):
        DIALOG.notification('Network watchdog', 'Bundled files missing, reinstall this addon', icon=xbmcgui.NOTIFICATION_ERROR)
        return

    if already_installed() and enabled():
        DIALOG.notification('Network watchdog', 'Already installed and enabled, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if not DIALOG.yesno(
        'Network watchdog',
        'This will install a systemd service to:\n%s\n%s\n\n'
        'It restarts connman if no LAN IP shows up within 60s of boot. Continue?'
        % (TARGET_SCRIPT, TARGET_SERVICE)
    ):
        return

    os.makedirs(TARGET_SERVICE_DIR, exist_ok=True)
    shutil.copy2(BUNDLED_SCRIPT, TARGET_SCRIPT)
    os.chmod(TARGET_SCRIPT, 0o755)
    shutil.copy2(BUNDLED_SERVICE, TARGET_SERVICE)

    subprocess.run(['systemctl', 'daemon-reload'])
    subprocess.run(['systemctl', 'enable', 'network-watchdog.service'])

    xbmc.log('[networkwatchdog] installed %s and %s' % (TARGET_SCRIPT, TARGET_SERVICE), xbmc.LOGINFO)
    DIALOG.ok('Network watchdog', 'Installed and enabled. This is a systemd service, not a Kodi feature - '
              'restart the whole box (not just Kodi) for it to actually run for the first time.')


def remove():
    # Kodi has no uninstall hook for script add-ons - clicking "Uninstall"
    # in the add-on browser just deletes this add-on's own folder, it
    # never runs any of our code. The systemd service and script this
    # addon installs to /storage/.config/ (outside Kodi entirely) would
    # otherwise keep running forever, uninstalled-from-Kodi or not - this
    # is the only way to actually undo that. Run it BEFORE uninstalling.
    if not (os.path.isfile(TARGET_SCRIPT) or os.path.isfile(TARGET_SERVICE)):
        DIALOG.notification('Network watchdog', 'Not installed, nothing to do', icon=xbmcgui.NOTIFICATION_INFO)
        return

    if not DIALOG.yesno(
        'Network watchdog',
        'This will stop and disable network-watchdog.service and remove:\n%s\n%s\n\nContinue?'
        % (TARGET_SCRIPT, TARGET_SERVICE)
    ):
        return

    subprocess.run(['systemctl', 'stop', 'network-watchdog.service'], stderr=subprocess.DEVNULL)
    subprocess.run(['systemctl', 'disable', 'network-watchdog.service'], stderr=subprocess.DEVNULL)
    if os.path.isfile(TARGET_SERVICE):
        os.remove(TARGET_SERVICE)
    if os.path.isfile(TARGET_SCRIPT):
        os.remove(TARGET_SCRIPT)
    subprocess.run(['systemctl', 'daemon-reload'])

    xbmc.log('[networkwatchdog] removed %s and %s' % (TARGET_SCRIPT, TARGET_SERVICE), xbmc.LOGINFO)
    DIALOG.ok('Network watchdog', 'Stopped, disabled, and removed. connman will no longer be auto-restarted on boot.')


if __name__ == '__main__':
    if len(sys.argv) == 2 and sys.argv[1] == 'remove':
        remove()
    else:
        main()
