from lib.utils import *

log('script version %s started' % ADDONVERSION, debug=True)

# kodi startup: check once per boot for the conflicting original addon,
# regardless of whether our own service setting is on - if the original is
# left enabled, it's what actually ends up running as the lyrics service
if sys.argv == ['']:
    disable_conflicting_addon()

# kodi startup: once per skin ever, auto-install the decorative fonts the
# current-line display needs - without this, a fresh install on a skin
# nobody has run "Install decorative fonts" for manually just silently
# renders at the active skin's own fallback size/typeface forever, since
# there'd be no one around to run it by hand on every box this ends up on.
# Per user request this is fully automatic, no confirmation - just a
# non-blocking notification once it's done. Runs at boot, before any song
# can start playing, since installing only takes effect after a Kodi
# restart anyway (Font.xml is only read once at skin load) - doing this any
# later just means more songs shown in the wrong font first.
if sys.argv == ['']:
    from lib import fontinstall
    _installed, _result = fontinstall.auto_install_if_needed()
    if _installed:
        xbmcgui.Dialog().notification(ADDONNAME, LANGUAGE(32921), icon=ADDONICON, time=6000, sound=False)

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
