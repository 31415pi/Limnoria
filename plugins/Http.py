#!/usr/bin/env python

###
# Copyright (c) 2002, Jeremiah Fincher
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

"""
Provides several commands that go out to websites and get things.

Commands include:
  freshmeat
  stockquote
  foldoc
  gkstats
  zipcode
  weather
  slashdot
"""

from baseplugin import *

import re
import time
import urllib
import urllib2
import xml.dom.minidom

import utils
import debug
import privmsgs
import callbacks

class FreshmeatException(Exception):
    pass

class Http(callbacks.Privmsg):
    threaded = True
    _fmProject = re.compile('<projectname_full>([^<]+)</projectname_full>')
    _fmVersion = re.compile('<latest_version>([^<]+)</latest_version>')
    _fmVitality = re.compile('<vitality_percent>([^<]+)</vitality_percent>')
    _fmPopular=re.compile('<popularity_percent>([^<]+)</popularity_percent>')
    _fmLastUpdated = re.compile('<date_updated>([^<]+)</date_updated>')
    def freshmeat(self, irc, msg, args):
        """<project name>"""
        project = privmsgs.getArgs(args)
        url = 'http://www.freshmeat.net/projects-xml/%s' % project
        try:
            fd = urllib2.urlopen(url)
            text = fd.read()
            fd.close()
            if text.startswith('Error'):
                raise FreshmeatException, text
            project = self._fmProject.search(text).group(1)
            version = self._fmVersion.search(text).group(1)
            vitality = self._fmVitality.search(text).group(1)
            popularity = self._fmPopular.search(text).group(1)
            lastupdated = self._fmLastUpdated.search(text).group(1)
            irc.reply(msg,
              '%s, last updated %s, with a vitality percent of %s '\
              'and a popularity of %s, is in version %s.' % \
              (project, lastupdated, vitality, popularity, version))
        except FreshmeatException, e:
            irc.reply(msg, debug.exnToString(e))
        except Exception, e:
            debug.recoverableException()
            irc.reply(msg, debug.exnToString(e))

    def stockquote(self, irc, msg, args):
        """<company symbol>"""
        symbol = privmsgs.getArgs(args)
        url = 'http://finance.yahoo.com/d/quotes.csv?s=%s'\
              '&f=sl1d1t1c1ohgv&e=.csv' % symbol
        try:
            fd = urllib2.urlopen(url)
            quote = fd.read()
            fd.close()
        except Exception, e:
            irc.reply(msg, debug.exnToString(e))
            return
        data = quote.split(',')
        #debug.printf(data) # debugging
        if data[1] != '0.00':
            irc.reply(msg,
                       'The current price of %s is %s, as of %s EST.  '\
                       'A change of %s from the last business day.' %\
                       (data[0][1:-1], data[1], data[3][1:-1], data[4]))
            return
        else:
            m = 'I couldn\'t find a listing for %s' % symbol
            irc.error(msg, m)
            return

    def foldoc(self, irc, msg, args):
        """<something to lookup on foldoc>"""
        search = '+'.join([urllib.quote(arg) for arg in args])
        url = 'http://foldoc.doc.ic.ac.uk/foldoc/foldoc.cgi?query=%s' % search
        try:
            fd = urllib2.urlopen(url)
            html = fd.read()
            fd.close()
        except Exception, e:
            irc.error(msg, debug.exnToString(e))
        text = html.split('<P>\n', 2)[1]
        text = text.replace('.\n', '.  ')
        text = text.replace('\n', ' ')
        text = utils.htmlToText(text)
        irc.reply(msg, text.strip())

    _gkrating = re.compile(r'<font color="#FFFF33">(\d+)</font>')
    _gkgames = re.compile(r's:&nbsp;&nbsp;</td><td class=sml>(\d+)</td></tr>')
    _gkrecord = re.compile(r'"#FFFF00">(\d+)[^"]+"#FFFF00">(\d+)[^"]+'\
        '"#FFFF00">(\d+)')
    _gkteam = re.compile('Team:\s+(.*?)\s+Last time')
    _gkseen = re.compile('seen on GK:\s+([^[]+)')
    def gkstats(self, irc, msg, args):
        """<name>"""
        name = privmsgs.getArgs(args)
        gkprofile = 'http://www.gameknot.com/stats.pl?%s' % name
        try:
            fd = urllib2.urlopen(gkprofile)
            profile = fd.read()
            fd.close()
            rating = self._gkrating.search(profile).group(1)
            games = self._gkgames.search(profile).group(1)
            (w, l, d) = self._gkrecord.search(profile).groups()
            profile = utils.htmlToText(profile)
            seen = self._gkseen.search(profile).group(1)
            if seen.startswith('0'):
                seen = '%s is on gameknot right now.' % name
            else:
                seen = '%s was last seen on Gameknot %s.' % (name, seen)
            if profile.find('Team:') >= 0:
                team = self._gkteam.search(profile).group(1)
                irc.reply(msg, '%s (team: %s) is rated %s and has %s active ' \
                          'games and a record of W-%s, L-%s, D-%s.  %s' % \
                          (name, team, rating, games, w, l, d, seen))
            else:
                irc.reply(msg, '%s is rated %s and has %s active games ' \
                          'and a record of W-%s, L-%s, D-%s.  %s' % \
                          (name, rating, games, w, l, d, seen))
        except AttributeError:
            if profile.find('User %s not found!' % name) != -1:
                irc.error(msg, 'No user %s exists.')
            else:
                irc.error(msg, 'The format of the page was odd.')
        except urllib2.URLError:
            irc.error(msg, 'Couldn\'t connect to gameknot.com.')

    _zipcode = re.compile(r'Local Forecast for (.*), (.*?) ')
    def zipcode(self, irc, msg, args):
        """<US zip code>"""
        zip = privmsgs.getArgs(args)
        url = "http://www.weather.com/weather/local/%s?lswe=%s" % (zip, zip)
        try:
            html = urllib2.urlopen(url).read()
            (city, state) = self._zipcode.search(html).groups()
            irc.reply(msg, '%s, %s' % (city, state))
        except AttributeError:
            irc.error(msg, 'the format of the page was odd.')
        except urllib2.URLError:
            irc.error(msg, 'Couldn\'t open search page.')

    
    _tempregex = re.compile('CLASS=obsTempTextA>(\d+)&deg;F</b></td>',\
                         re.IGNORECASE)
    _cityregex = re.compile(r'Local Forecast for (.*), (.*?) ')
    _condregex = re.compile('CLASS=obsInfo2><b CLASS=obsTextA>(.*)</b></td>',\
                         re.IGNORECASE)
    def weather(self, irc, msg, args):
        """<US zip code>"""
        zip = privmsgs.getArgs(args)
        url = "http://www.weather.com/weather/local/%s?lswe=%s" % (zip, zip)
        try:
            html = urllib2.urlopen(url).read()
            city, state = self._cityregex.search(html).groups()
            temp = self._tempregex.search(html).group(1)
            conds = self._condregex.search(html).group(1)
            irc.reply(msg, 'The current temperature in %s, %s is %dF with %s'\
                           ' conditions' % (city, state, int(temp), conds))
        except AttributeError:
            irc.error(msg, 'the format of the page was odd.')
        except urllib2.URLError:
            irc.error(msg, 'Couldn\'t open the search page.')

    _slashdotTime = 0.0
    def slashdot(self, irc, msg, args):
        """takes no arguments"""
        if time.time() - self._slashdotTime > 1800:
            try:
                fd = urllib2.urlopen('http://slashdot.org/slashdot.xml')
                slashdotXml = fd.read()
                fd.close()
                dom = xml.dom.minidom.parseString(slashdotXml)
                headlines = []
                for headline in dom.getElementsByTagName('title'):
                    headlines.append(str(headline.firstChild.data))
                self._slashdotResponse = ' :: '.join(headlines)
                self._slashdotTime = time.time()
            except urllib2.URLError, e:
                irc.error(msg, str(e))
                return
        irc.reply(msg, self._slashdotResponse)

    _geekquotere = re.compile('<p class="qt">(.*?)</p>')
    def geekquote(self, irc, msg, args):
        "[<multiline>]"
        multiline = privmsgs.getArgs(args, needed=0, optional=1)
        try:
            fd = urllib2.urlopen('http://bash.org/?random1')
        except urllib2.URLError:
            irc.error(msg, 'Error connecting to geekquote server.')
            return
        html = fd.read()
        fd.close()
        if multiline:
            m = self._geekquotere.search(html, re.M)
        else:
            m = self._geekquotere.search(html)
        if m is None:
            irc.error(msg, 'No quote found.')
            return
        quote = utils.htmlToText(m.group(1))
        quote = ' // '.join(quote.splitlines())
        irc.reply(msg, quote)
        
    _acronymre = re.compile(r'<td[^w]+width="70[^>]+>(?:<b>)?([^<]+)(?:</b>)?')
    def acronym(self, irc, msg, args):
        """<acronym>

        displays the first 5 acronym matches"""
        acronym = privmsgs.getArgs(args)
        try:
            url = 'http://www.acronymfinder.com/' \
                  'af-query.asp?String=exact&Acronym=%s' % acronym
            request = urllib2.Request(url, headers={'User-agent':
              'Mozilla/4.0 (compatible; MSIE 5.5; Windows NT 4.0)'})
            fd = urllib2.urlopen(request)
        except urllib2.URLError:
            irc.error(msg, 'Couldn\'t connect to acronymfinder.com')
            return
        html = fd.read()
        fd.close()
        defs = self._acronymre.findall(html)
        if len(defs) == 0:
            irc.reply(msg, 'No definitions found.')
        else:
            defs=[repr(x.strip()) for x in defs[1:-1]][:5]
            irc.reply(msg, '%s could be %s' % (acronym, ', or '.join(defs)))

    _netcraftre = re.compile(r'whatos text -->(.*?)<a href="/up/acc', re.S)
    def netcraft(self, irc, msg, args):
        """<hostname>"""
        hostname = privmsgs.getArgs(args)
        url = 'http://uptime.netcraft.com/up/graph/?host=%s' % hostname
        fd = urllib2.urlopen(url)
        html = fd.read()
        fd.close()
        m = self._netcraftre.search(html)
        if m:
            html = m.group(1)
            s = utils.htmlToText(html, tagReplace='').strip('\xa0 ')
            irc.reply(msg, s[9:]) # Snip off "the site"
        elif html.find('We could not get any results') != -1:
            irc.reply(msg, 'No results found for %s.' % hostname)
        else:
            irc.error(msg, 'The format of the was odd.')


Class = Http

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
