from lib.utils import *

log('script version %s started' % ADDONVERSION, debug=True)

# kodi startup: check once per boot for the conflicting original addon,
# regardless of whether our own service setting is on - if the original is
# left enabled, it's what actually ends up running as the lyrics service
if sys.argv == ['']:
    disable_conflicting_addon()

# kodi startup, service is disabled, exit
if sys.argv == [''] and not ADDON.getSettingBool('service'):
    log('service not enabled', debug=True)

# scraper test, run from addon settings
elif len(sys.argv) == 2 and sys.argv[1] == 'test':
    from lib.scrapertest import *
    test_scrapers()

# install decorative fonts into the active skin, run from addon settings
elif len(sys.argv) == 2 and sys.argv[1] == 'installfonts':
    from lib import fontinstall
    ok, result = fontinstall.install()
    if ok and result:
        xbmcgui.Dialog().ok(ADDONNAME, 'Installed decorative fonts into %d file(s) in the active skin. Restart Kodi for them to take effect.' % result)
    elif ok:
        xbmcgui.Dialog().ok(ADDONNAME, 'Decorative fonts were already installed for the active skin.')
    else:
        xbmcgui.Dialog().ok(ADDONNAME, 'Could not install decorative fonts: %s' % result)

# remove previously installed decorative fonts, run from addon settings
elif len(sys.argv) == 2 and sys.argv[1] == 'removefonts':
    from lib import fontinstall
    ok, result = fontinstall.remove()
    if ok:
        xbmcgui.Dialog().ok(ADDONNAME, 'Removed decorative fonts, restored %d skin file(s) from backup. Restart Kodi for it to take effect.' % result)
    else:
        xbmcgui.Dialog().ok(ADDONNAME, result)

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
