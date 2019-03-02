# The MIT License (MIT)
#
# Copyright (c) 2019 John Bartkiw
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import requests
from xml.dom.minidom import parseString

from adapt.intent import IntentBuilder
from mycroft.skills.core import intent_handler
from mycroft.util.log import LOG

from mycroft.audio import wait_while_speaking
from mycroft.messagebus.message import Message
from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel

# Static values for tunein search requests
base_url = "http://opml.radiotime.com/Search.ashx"
headers = {}

class TuneinSkill(CommonPlaySkill):

    def __init__(self):
        super().__init__(name="TuneinSkill")

        self.audio_state = "stopped"  # 'playing', 'paused', 'stopped'
        self.station_name = None
        self.url = None

    @intent_handler(IntentBuilder("").require("Station").require("TuneIn"))
    def handle_station_search_intent(self, message):
        # In this case, respond by simply speaking a canned response.
        # Mycroft will randomly speak one of the lines from the file
        #    dialogs/en-us/hello.world.dialog
        self.find_station("Jazz 24")

    def stop(self):
        self.audio_state = "stopped"
        self.station_name = None
        self.url = None
        return True

    # Attempt to find the first active station matching the query string
    def find_station(search_term):
        payload = { "query" : search_term }
        # get the response from the TuneIn API
        res = requests.post(url, data=payload, headers=headers)
        # results are each in their own <outline> tag as defined by OPML (https://en.wikipedia.org/wiki/OPML)
        entries = dom.getElementsByTagName("outline")

        # Loop through outlines in the lists
        for entry in entries:
            # Only look at outlines that are of type=audio and item=station
            if (entry.getAttribute("type") == "audio") and (entry.getAttribute("item") == "station"):
                    if (entry.getAttribute("key") == "unavailable"):
                        # Ignore entries that are marked as unavailable
                    else:
                        self.url = entry.getAttribute("URL")
                        self.station_name = entry.getAttribute("text")
                        self.audio_state = "playing"
                        self.speak_dialog("now.playing", {"station": self.station_name} )
                        break

        # We didn't find any playable stations
        self.speak_dialog("not.found")

def create_skill():
    return TuneinSkill()
