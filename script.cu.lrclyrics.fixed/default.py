import os
from lib.utils import *

log('script version %s started' % ADDONVERSION, debug=True)

# kodi startup: check once per boot for the conflicting original addon,
# regardless of whether our own service setting is on - if the original is
# left enabled, it's what actually ends up running as the lyrics service
if sys.argv == ['']:
    disable_conflicting_addon()

    # Aeon Nox 5 skin patches (formerly a separate addon, merged in 2026-09-10
    # to remove a mutual <requires> dependency cycle - see lib/skinfix.py).
    # Must run before gui.MAIN() below takes over the process.
    from lib import skinfix
    _applied = skinfix.apply_skin_fixes_silently()
    if _applied and not xbmc.Monitor().waitForAbort(3):
        if xbmcgui.Dialog().yesno(
            ADDONNAME,
            'Applied %d Aeon Nox 5 skin fix(es). Restart Kodi now for them to take effect?' % _applied
        ):
            os.system('systemctl restart kodi &')

# kodi startup, service is disabled, exit
if sys.argv == [''] and not ADDON.getSettingBool('service'):
    log('service not enabled', debug=True)

# scraper test, run from addon settings
elif len(sys.argv) == 2 and sys.argv[1] == 'test':
    from lib.scrapertest import *
    test_scrapers()

# kodi startup, service is enabled, start main loop
elif not WIN.getProperty('culrc.running') == 'true':
    from lib import gui
    gui.MAIN()

# service is running, but gui was exited, user clicked lyrics button, reshow gui
elif not WIN.getProperty('culrc.guirunning') == 'TRUE':
    WIN.setProperty('culrc.force','TRUE')

# service is running, gui is viisible, user clicked the lyrics button, do nothing
else:
    log('script already running', debug=True)
    if not ADDON.getSettingBool('silent'):
        xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32158), time=2000, sound=False)

log('script version %s ended' % ADDONVERSION, debug=True)
