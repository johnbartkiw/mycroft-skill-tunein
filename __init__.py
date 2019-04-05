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

import re
import requests
from xml.dom.minidom import parseString

from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel
from mycroft.skills.audioservice import AudioService
from mycroft.skills.core import intent_file_handler
from mycroft.util.log import LOG

from mycroft.audio import wait_while_speaking
from mycroft.util import play_mp3

# Static values for tunein search requests
base_url = "http://opml.radiotime.com/Search.ashx"
headers = {}


class TuneinSkill(CommonPlaySkill):

    def __init__(self):
        super().__init__(name="TuneinSkill")
        self.audio_service = AudioService(self.emitter)
        self.station_name = None
        self.stream_url = None
        self.mpeg_url = None
        self.process = None
        self.regexes = {}

    def CPS_match_query_phrase(self, phrase):
        # Look for regex matches starting from the most specific to the least
        # Play <data> internet radio on tune in
        match = re.search(self.translate_regex('internet_radio_on_tunein'), phrase)
        if match:
            data = re.sub(self.translate_regex('internet_radio_on_tunein'), '', phrase)
            LOG.debug("CPS Match (internet_radio_on_tunein): " + data)
            return phrase, CPSMatchLevel.EXACT, data

        # Play <data> radio on tune in
        match = re.search(self.translate_regex('radio_on_tunein'), phrase)
        if match:
            data = re.sub(self.translate_regex('radio_on_tunein'), '', phrase)
            LOG.debug("CPS Match (radio_on_tunein): " + data)
            return phrase, CPSMatchLevel.EXACT, data

        # Play <data> on tune in
        match = re.search(self.translate_regex('on_tunein'), phrase)
        if match:
            data = re.sub(self.translate_regex('on_tunein'), '', phrase)
            LOG.debug("CPS Match (on_tunein): " + data)
            return phrase, CPSMatchLevel.EXACT, data

        # Play <data> internet radio
        match = re.search(self.translate_regex('internet_radio'), phrase)
        if match:
            data = re.sub(self.translate_regex('internet_radio'), '', phrase)
            LOG.debug("CPS Match (internet_radio): " + data)
            return phrase, CPSMatchLevel.CATEGORY, data

        # Play <data> radio
        match = re.search(self.translate_regex('radio'), phrase)
        if match:
            data = re.sub(self.translate_regex('radio'), '', phrase)
            LOG.debug("CPS Match (radio): " + data)
            return phrase, CPSMatchLevel.CATEGORY, data

        return phrase, CPSMatchLevel.GENERIC, phrase

    def CPS_start(self, phrase, data):
        LOG.debug("CPS Start: " + data)
        self.find_station(data)

    @intent_file_handler('StreamRequest.intent')
    def handle_stream_intent(self, message):
        self.find_station(message.data["station"], message.data["utterance"])
        LOG.debug("Station data: " + message.data["station"])

    # Attempt to find the first active station matching the query string
    def find_station(self, search_term, utterance):
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
                    self.mpeg_url = entry.getAttribute("URL")
                    self.station_name = entry.getAttribute("text")
                    # this URL will return audio/x-mpegurl data. This is just a list of URLs to the real streams
                    self.stream_url = self.get_stream_url(self.mpeg_url)
                    self.audio_state = "playing"
                    self.speak_dialog("now.playing", {"station": self.station_name} )
                    wait_while_speaking()
                    LOG.debug("Found stream URL: " + self.stream_url)
                    self.audio_service.play(self.stream_url, utterance)
                    return

        # We didn't find any playable stations
        self.speak_dialog("not.found")
        wait_while_speaking()
        LOG.debug("Could not find a station with the query term: " + search_term)

    def get_stream_url(self, mpegurl):
        res = requests.get(mpegurl)
        # Get the first line from the results
        for line in res.text.splitlines():
            return self.process_url(line)

    # Check what kind of url was pulled from the x-mpegurl data
    def process_url(self, url):
        if (len(url) > 4):
            if url[-3:] == 'm3u':
                return url[:-4]
            if url[-3:] == 'pls':
                return self.process_pls(url)
            else:
                return url
        return url

    # Pull down the pls data and pull out the real stream url out of it
    def process_pls(self, url):
        res = requests.get(url)
        # Loop through the data looking for the first url
        for line in res.text.splitlines():
            if line.startswith("File1="):
                return line[6:]

    # Get the correct localized regex
    def translate_regex(self, regex):
        if regex not in self.regexes:
            path = self.find_resource(regex + '.regex')
            if path:
                with open(path) as f:
                    string = f.read().strip()
                self.regexes[regex] = string
        return self.regexes[regex]

def create_skill():
    return TuneinSkill()
