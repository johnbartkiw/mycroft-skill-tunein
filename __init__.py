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

import yaml
import os.path
from os import path
from os.path import expanduser

from mycroft.audio.services.vlc import VlcService

from mycroft.skills.common_play_skill import CommonPlaySkill, CPSMatchLevel
from mycroft.skills.core import intent_file_handler
from mycroft.util.log import LOG
from mycroft.audio import wait_while_speaking
from lingua_franca.parse import match_one

# Static values for tunein search requests
base_url = "http://opml.radiotime.com/Search.ashx"
headers = {}
MAXALIASES = 5


def request_api(search_term):
    """ Requests the TuneIn API for stations that match the search_term
    If the uttered station is not found it tries to redo (retries:1) the request with
    a suggested station name - if one is given

    Args:
        search_term: The requested station name

    Returns:
        dom: The DOM containing relevant stations
    """
    tries = 2

    while tries and search_term:
        payload = {"query": search_term}
        # get the response from the TuneIn API
        res = requests.post(base_url, data=payload, headers=headers)
        dom = parseString(res.text)
        # Only look at outlines that are of type=audio and item=station (.. and available)
        for entry in reversed(dom.getElementsByTagName("outline")):
            if entry.getAttribute("key") == "unavailable" or (entry.getAttribute("type") != "audio") or (
                    entry.getAttribute("item") != "station"):
                parent = entry.parentNode
                parent.removeChild(entry)

        if dom.getElementsByTagName("outline").length != 0:
            break
        # if the input term isnt exact (eg. "Deutschlandfunk Nowa") - and not complete gibberish - the api returns
        # <body>
        # <outline text="Did you mean?">
        # <outline type="link" text="Deutschlandfunk Nova" URL="http://opml.radiotime.com/Search.ashx?event=d..."/>
        _dom = parseString(res.text)
        for entry in _dom.getElementsByTagName("outline"):
            if entry.getAttribute("type") == "link":
                search_term = entry.getAttribute("text")
                break
        else:
            search_term = ""
        tries -= 1

    return dom


def _fuzzy_match(query, entries):
    stations = [entry.getAttribute("text") for entry in entries]
    if len(stations):
        _match, perc = match_one(query, stations)
        for entry in entries:
            if _match == entry.getAttribute("text"):
                return entry, perc
    return None, None


class TuneinSkill(CommonPlaySkill):

    def __init__(self):
        super().__init__(name="TuneinSkill")

        self.mediaplayer = VlcService(config={'low_volume': 10, 'duck': True})
        self.audio_state = "stopped"  # 'playing', 'stopped'
        self.station_name = None
        self.stream_url = None
        self.mpeg_url = None
        self.regexes = {}
        self.aliases = {}

    def initialize(self):
        self.init_websettings()
        self.settings_change_callback = self.init_websettings

    def init_websettings(self):
        self.get_aliases()

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
        self.find_station(message.data["station"])
        LOG.debug("Station data: " + message.data["station"])

    def get_aliases(self):
        self.aliases.clear()
        for i in range(0, MAXALIASES):
            _station = self.settings.get(f"station{i}", False)
            _alias = self.settings.get(f"alias{i}", False)
            if _station and _alias:
                self.aliases[_alias.lower()] = _station.lower()

    def remove_aliases(self, search_term):
        """ Applies the aliases either defined in the webconfig or using ~/tunein_aliases.yaml (deprecated)"""
        # backwards compat
        if not self.aliases:
            home = expanduser('~')
            alias_file = home + '/tunein_aliases.yaml'
            if path.exists(alias_file):
                with open(alias_file, 'r') as file:
                    self.aliases = yaml.load(file, Loader=yaml.FullLoader)

        for alias, station in self.aliases.items():
            if alias in search_term:
                search_term = search_term.replace(alias, station)
                LOG.debug(f"Removed alias. Search_term: {search_term}")

        return search_term

    # Attempt to find the first active station matching the query string
    def find_station(self, search_term):

        tracklist = []
        retry = True
        search_term = self.remove_aliases(search_term)

        dom = request_api(search_term)
        # results are each in their own <outline> tag as defined by OPML (https://en.wikipedia.org/wiki/OPML)
        # fuzzy matches the query to the given stations NodeList
        match, perc = _fuzzy_match(search_term, dom.getElementsByTagName("outline"))

        # No matching stations
        if match is None:
            self.speak_dialog("not.found")
            wait_while_speaking()
            LOG.debug("Could not find a station with the query term: " + search_term)
            return

        # stop the current stream if we have one running
        if self.audio_state == "playing":
            self.stop()
        # Ignore entries that are marked as unavailable
        self.mpeg_url = match.getAttribute("URL")
        self.station_name = match.getAttribute("text")
        # this URL will return audio/x-mpegurl data. This is just a list of URLs to the real streams
        self.stream_url = self.get_stream_url(self.mpeg_url)
        self.audio_state = "playing"
        self.speak_dialog("now.playing", {"station": self.station_name})
        wait_while_speaking()
        LOG.debug("Station: " + self.station_name)
        LOG.debug("Station name fuzzy match percent: " + str(perc))
        LOG.debug("Stream URL: " + self.stream_url)
        tracklist.append(self.stream_url)
        self.mediaplayer.add_list(tracklist)
        self.mediaplayer.play()

    def get_stream_url(self, mpegurl):
        res = requests.get(mpegurl)
        # Get the first line from the results
        for line in res.text.splitlines():
            return self.process_url(line)

    def stop(self):
        if self.audio_state == "playing":
            self.mediaplayer.stop()
            self.mediaplayer.clear_list()
            LOG.debug("Stopping stream")

        self.audio_state = "stopped"
        self.station_name = None
        self.stream_url = None
        self.mpeg_url = None
        return True

    def shutdown(self):
        if self.audio_state == 'playing':
            self.mediaplayer.stop()
            self.mediaplayer.clear_list()

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
