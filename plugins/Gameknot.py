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
Handles URL snarfing for Gameknot.com and the gkstats command.
"""

import plugins

import re
import sets
import urllib2

import conf
import debug
import utils
import plugins
import ircutils
import privmsgs
import callbacks


def configure(onStart, afterConnect, advanced):
    # This will be called by setup.py to configure this module.  onStart and
    # afterConnect are both lists.  Append to onStart the commands you would
    # like to be run when the bot is started; append to afterConnect the
    # commands you would like to be run when the bot has finished connecting.
    from questions import expect, anything, something, yn
    onStart.append('load Gameknot')
    if advanced:
        print 'The Gameknot plugin has the functionality to watch for URLs'
        print 'that match a specific pattern (we call this a snarfer). When'
        print 'supybot sees such a URL, he will parse the web page for'
        print 'information and reply with the results.\n'
        if yn('Do you want the Gameknot stats snarfer enabled by default?') ==\
               'n':
            onStart.append('Gameknot toggle stat off')
        if yn('Do you want the Gameknot Game links snarfer enabled by '\
              'default?') == 'n':
            onStart.append('Gameknot toggle stat off')


class Gameknot(callbacks.PrivmsgCommandAndRegexp, plugins.Configurable):
    threaded = True
    regexps = ['gameknotSnarfer', 'gameknotStatsSnarfer']
    configurables = plugins.ConfigurableDictionary(
        [('game-snarfer', plugins.ConfigurableBoolType, True,
          """Determines whether the game URL snarfer is active; if so, the bot
          will reply to the channel with a summary of the game data when it
          sees a Gameknot game on the channel."""),
         ('stats-snarfer', plugins.ConfigurableBoolType, True,
          """Determines whether the stats URL snarfer is active; if so, the bot
          will reply to the channel with a summary of the stats of any player
          whose stats URL is seen on the channel.""")]
        )
    _gkrating = re.compile(r'<font color="#FFFF33">(\d+)</font>')
    _gkgames = re.compile(r's:</td><td class=sml>(\d+)</td></tr>')
    _gkrecord = re.compile(r'"#FFFF00">(\d+)[^"]+"#FFFF00">(\d+)[^"]+'\
        '"#FFFF00">(\d+)')
    _gkteam = re.compile(r'Team:(<.*?>)+(?P<name>.*?)</span>')
    _gkseen = re.compile(r'(seen on GK:\s+([^[]+ago)|.*?is hiding.*?)')
    def __init__(self):
        plugins.Configurable.__init__(self)
        callbacks.PrivmsgCommandAndRegexp.__init__(self)

    def die(self):
        plugins.Configurable.die(self)
        callbacks.PrivmsgCommandAndRegexp.die(self)
        
    def getStats(self, name):
        gkprofile = 'http://www.gameknot.com/stats.pl?%s' % name
        try:
            fd = urllib2.urlopen(gkprofile)
            profile = fd.read()
            fd.close()
            rating = self._gkrating.search(profile).group(1)
            games = self._gkgames.search(profile).group(1)
            (w, l, d) = self._gkrecord.search(profile).groups()
            try:
                w = int(w)
                l = int(l)
                d = int(d)
                wp = 100. * w / (w + l + d) # win percent
                lp = 100. * l / (w + l + d) # loss percent
                dp = 100. * d / (w + l + d) # draw percent
            except ValueError:
                w = w
                wp = 0.
                l = l
                lp = 0.
                d = d
                dp = 0.
            seen = self._gkseen.search(utils.htmlToText(profile))
            if seen is None:
                seen = ''
            elif 'is hiding' in seen.group(0):
                seen = '%s is hiding his/her online status.' % name
            elif seen.group(2).startswith('0'):
                seen = '%s is on gameknot right now.' % name
            else:
                seen = '%s was last seen on Gameknot %s.' % (name,
                seen.group(2))
            if games == '1':
                games = '1 active game'
            else:
                games = '%s active games' % games
            if 'Team:' in profile:
                team = self._gkteam.search(profile).group('name')
                s = '%s (team: %s) is rated %s and has %s ' \
                    'and a record of %s, %s, and %s ' \
                    '(win/loss/draw percentage: %.2f%%/%.2f%%/%.2f%%).  %s' % \
                    (name, team, rating, games,
                     utils.nItems(w, 'win'),
                     utils.nItems(l, 'loss'),
                     utils.nItems(d, 'draw'),
                     wp, lp, dp, seen)
            else:
                s = '%s is rated %s and has %s ' \
                    'and a record of %s, %s, and %s ' \
                    '(win/loss/draw percentage: %.2f%%/%.2f%%/%.2f%%).  %s' % \
                    (name, rating, games,
                     utils.nItems(w, 'win'),
                     utils.nItems(l, 'loss'),
                     utils.nItems(d, 'draw'),
                     wp, lp, dp, seen)
            return s
        except AttributeError:
            if ('User %s not found!' % name) in profile:
                raise callbacks.Error, 'No user %s exists.' % name
            else:
                raise callbacks.Error,'The format of the page was odd.  %s' %\
                    conf.replyPossibleBug
        except urllib2.URLError:
            raise callbacks.Error, 'Couldn\'t connect to gameknot.com'


    def gkstats(self, irc, msg, args):
        """<name>

        Returns the stats Gameknot keeps on <name>.  Gameknot is an online
        website for playing chess (rather similar to correspondence chess, just
        somewhat faster) against players from all over the world.
        """
        name = privmsgs.getArgs(args)
        irc.reply(msg, self.getStats(name))

    _gkPlayer = re.compile(r"popd\('(Rating[^']+)'\).*?>([^<]+)<")
    _gkRating = re.compile(r": (\d+)[^:]+:<br>(\d+)[^,]+, (\d+)[^,]+, (\d+)")
    _gkGameTitle = re.compile(r"<p><b>(.*?)\s*</b>&nbsp;\s*<span.*?>\(started")
    _gkWon = re.compile(r'>(\S+)\s+won')
    _gkReason = re.compile(r'won\s+\(\S+\s+(\S+)\)')
    def gameknotSnarfer(self, irc, msg, match):
        r"http://(?:www\.)?gameknot\.com/chess\.pl\?bd=\d+(&r=\d+)?"
        if not self.configurables.get('game-snarfer', channel=msg.args[0]):
            return
        #debug.printf('Got a GK URL from %s' % msg.prefix)
        url = match.group(0)
        fd = urllib2.urlopen(url)
        #debug.printf('Got the connection.')
        s = fd.read()
        #debug.printf('Got the string.')
        fd.close()
        try:
            gameTitle = self._gkGameTitle.search(s).groups()
            gameTitle = ircutils.bold(gameTitle)
            ((wRating, wName), (bRating, bName)) = self._gkPlayer.findall(s)
            wName = ircutils.bold(wName)
            bName = ircutils.bold(bName)
            if 'to move...' in s:
                if 'white to move' in s:
                    toMove = wName + ' to move.'
                else:
                    toMove = bName + ' to move.'
            else:
                # Game is over.
                m = self._gkWon.search(s)
                if m:
                    winner = m.group(1)
                    m = self._gkReason.search(s)
                    if m:
                        reason = m.group(1)
                    else:
                        reason = 'lost'
                    if winner == 'white':
                        toMove = '%s won, %s %s.' % (wName, bName, reason)
                    else:
                        toMove = '%s won, %s %s.' % (bName, wName, reason)
                else:
                    toMove = 'The game was a draw.'
            (wRating, wWins, wLosses, wDraws) = \
                      self._gkRating.search(wRating).groups()
            (bRating, bWins, bLosses, bDraws) = \
                      self._gkRating.search(bRating).groups()
            wStats = '%s; W-%s, L-%s, D-%s' % (wRating, wWins, wLosses, wDraws)
            bStats = '%s; W-%s, L-%s, D-%s' % (bRating, bWins, bLosses, bDraws)
            s = '%s: %s (%s) vs. %s (%s);  %s' % \
                (gameTitle, wName, wStats, bName, bStats, toMove)
            irc.reply(msg, s, prefixName=False)
        except ValueError:
            irc.error(msg,'That doesn\'t appear to be a proper Gameknot game.'\
                ' (%s)' % conf.replyPossibleBug)
        except Exception, e:
            irc.error(msg, debug.exnToString(e))
    gameknotSnarfer = privmsgs.urlSnarfer(gameknotSnarfer)

    def gameknotStatsSnarfer(self, irc, msg, match):
        r"http://gameknot\.com/stats\.pl\?([^&]+)"
        if not self.configurables.get('stats-snarfer', channel=msg.args[0]):
            return
        name = match.group(1)
        s = self.getStats(name)
        irc.reply(msg, s, prefixName=False)
    gameknotStatsSnarfer = privmsgs.urlSnarfer(gameknotStatsSnarfer)

Class = Gameknot

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
