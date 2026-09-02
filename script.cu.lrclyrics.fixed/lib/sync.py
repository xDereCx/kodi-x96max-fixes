import time
from lib.utils import *

ADDON = xbmcaddon.Addon()
LANGUAGE = ADDON.getLocalizedString

# Auto-close if the user hasn't touched the slider in a while, so it doesn't
# stay parked on top of the lyrics indefinitely after a quick up/down nudge.
IDLE_TIMEOUT = 4.0

class GUI(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        self.function = kwargs['function']
        self.offset = kwargs['offset']
        self.Monitor = kwargs['monitor']

    def onInit(self):
        self._get_controls()
        self._init_values()
        self.exit = False
        self.last_update = time.time()
        while (not self.Monitor.abortRequested()) and xbmc.getCondVisibility('Player.HasAudio') and (not self.exit):
            if (time.time() - self.last_update) > IDLE_TIMEOUT:
                break
            xbmc.sleep(100)
        self.close()

    def _get_controls(self):
        self.header = self.getControl(10)
        self.slider = self.getControl(11)
        self.label = self.getControl(12)

    def _init_values(self):
        # static legend so it's obvious which way the slider makes lyrics
        # play earlier vs. later, instead of only a numeric readout
        self.header.setLabel(LANGUAGE(32010))
        string = self._get_string(self.offset)
        self.label.setLabel(string)
        self.slider.setFloat((self.offset * 1.0), -20.0, 0.5, 20.0)

    def _get_string(self, val):
        if val > 0.0:
            string = LANGUAGE(32009) % str(val)
        elif val < 0.0:
            string = LANGUAGE(32008) % str(-val)
        else:
            string = LANGUAGE(32011)
        return string

    def onAction(self, action):
        if action.getId() in CANCEL_DIALOG:
            self.exit = True
        else:
            val = self.slider.getFloat()
            self.val = round(val,1)
            string = self._get_string(self.val)
            self.label.setLabel(string)
            self.function(self.val)
            self.last_update = time.time()
