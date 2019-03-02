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
from mycroft.skills.core import MycroftSkill, intent_handler, intent_file_handler
from mycroft.util.log import LOG

from mycroft.audio import wait_while_speaking
from mycroft.messagebus.message import Message

# Static values for tunein search requests
base_url = "http://opml.radiotime.com/Search.ashx"
headers = {}

class TuneinSkill(MycroftSkill):

    def __init__(self):
        super(TuneinSkill, self).__init__(name="TuneinSkill")

        self.audio_state = "stopped"  # 'playing', 'paused', 'stopped'
        self.station_name = None
        self.url = None

    @intent_file_handler('StreamRequest.intent')
    def handle_stream_intent(self, message):
        self.find_station(message.data["station"])
        LOG.debug("Station data: " + message.data["station"])


    # Attempt to find the first active station matching the query string
    def find_station(self, search_term):
        payload = { "query" : search_term }
        # get the response from the TuneIn API
        res = requests.post(base_url, data=payload, headers=headers)
        dom = parseString(res.text)
        # results are each in their own <outline> tag as defined by OPML (https://en.wikipedia.org/wiki/OPML)
        entries = dom.getElementsByTagName("outline")

        # Loop through outlines in the lists
        for entry in entries:
            # Only look at outlines that are of type=audio and item=station
            if (entry.getAttribute("type") == "audio") and (entry.getAttribute("item") == "station"):
                    if (entry.getAttribute("key") != "unavailable"):
                        # Ignore entries that are marked as unavailable
                        self.url = entry.getAttribute("URL")
                        self.station_name = entry.getAttribute("text")
                        self.audio_state = "playing"
                        self.speak_dialog("now.playing", {"station": self.station_name} )
                        LOG.debug("Found stream URL: " + self.url)
                        print ("TODO: Start Music here")
                        return

        # We didn't find any playable stations
        self.speak_dialog("not.found")
        LOG.debug("Could not find a station with the query term: " + search_term)

    def stop(self):
        if self.audio_state == "playing":
            print ("TODO: Stop Music here")
        self.audio_state = "stopped"
        self.station_name = None
        self.url = None
        return True

def create_skill():
    return TuneinSkill()
