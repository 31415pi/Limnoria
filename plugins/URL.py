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
Keeps track of URLs posted to a channel, along with relevant context.  Allows
searching for URLs and returning random URLs.  Also provides statistics on the
URLs in the database.
"""

import plugins

import os
import re
import time
import getopt
import urllib2
import urlparse

import sqlite

import conf
import debug
import utils
import ircmsgs
import privmsgs
import callbacks

def configure(onStart, afterConnect, advanced):
    # This will be called by setup.py to configure this module.  onStart and
    # afterConnect are both lists.  Append to onStart the commands you would
    # like to be run when the bot is started; append to afterConnect the
    # commands you would like to be run when the bot has finished connecting.
    from questions import expect, anything, something, yn
    onStart.append('load URL')

class URL(callbacks.Privmsg, plugins.Toggleable, plugins.ChannelDBHandler):
    toggles = plugins.ToggleDictionary({'tinysnarf':True,
                                        'tinyreply':True})
    _maxUrlLen = 46
    def __init__(self):
        self.nextMsgs = {}
        callbacks.Privmsg.__init__(self)
        plugins.ChannelDBHandler.__init__(self)
        plugins.Toggleable.__init__(self)

    def makeDb(self, filename):
        if os.path.exists(filename):
            return sqlite.connect(filename)
        db = sqlite.connect(filename)
        cursor = db.cursor()
        cursor.execute("""CREATE TABLE urls (
                          id INTEGER PRIMARY KEY,
                          url TEXT,
                          added TIMESTAMP,
                          added_by TEXT,
                          previous_msg TEXT,
                          current_msg TEXT,
                          next_msg TEXT,
                          protocol TEXT,
                          site TEXT,
                          filename TEXT
                          )""")
        cursor.execute("""CREATE TABLE tinyurls (
                          id INTEGER PRIMARY KEY,
                          url_id INTEGER,
                          tinyurl TEXT
                          )""")
        db.commit()
        return db

    _urlRe = re.compile(r"([-a-z0-9+.]+://[-\w=#!*()',$;&/@:%?.~]+)", re.I)
    def doPrivmsg(self, irc, msg):
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        if (msg.nick, channel) in self.nextMsgs:
            L = self.nextMsgs.pop((msg.nick, msg.args[0]))
            for (url, added) in L:
                cursor.execute("""UPDATE urls SET next_msg=%s
                                  WHERE url=%s AND added=%s""",
                               msg.args[1], url, added)
        if ircmsgs.isAction(msg):
            text = ircmsgs.unAction(msg)
        else:
            text = msg.args[1]
        for url in self._urlRe.findall(text):
            (protocol, site, filename, _, _, _) = urlparse.urlparse(url)
            previousMsg = ''
            for oldMsg in reviter(irc.state.history):
                if oldMsg.command == 'PRIVMSG':
                    if oldMsg.nick == msg.nick and oldMsg.args[0] == channel:
                        previousMsg = oldMsg.args[1]
            addedBy = msg.nick
            added = int(time.time())
            cursor.execute("""INSERT INTO urls VALUES
                              (NULL, %s, %s, %s, %s, %s, '', %s, %s, %s)""",
                           url, added, addedBy, msg.args[1], previousMsg,
                           protocol, site, filename)
            if self.toggles.get('tinysnarf', channel=msg.args[0]) and\
                len(url) > self._maxUrlLen:
                cursor.execute("""SELECT id FROM urls WHERE url=%s AND
                    added=%s AND added_by=%s""", url, added, addedBy)
                if cursor.rowcount != 0:
                    #debug.printf(url)
                    tinyurl = self._getTinyUrl(url)
                    if tinyurl:
                        id = int(cursor.fetchone()[0])
                        cursor.execute("""INSERT INTO tinyurls VALUES
                            (NULL, %s, %s)""", id, tinyurl)
                    if self.toggles.get('tinyreply', channel=msg.args[0]):
                        irc.queueMsg(callbacks.reply(msg, 'TinyURL: %s' %
                            tinyurl, prefixName=False))
            key = (msg.nick, channel)
            self.nextMsgs.setdefault(key, []).append((url, added))
        db.commit()

    _tinyRe = re.compile(r'(http://tinyurl.com/\w{4})</blockquote>')
    def _getTinyUrl(self, url, cmd=False):
        try:
            fd = urllib2.urlopen('http://tinyurl.com/create.php?url=%s' % url)
            s = fd.read()
            fd.close()
            m = self._tinyRe.search(s)
            if m is None:
                return None
            return m.group(1)
        except urllib2.HTTPError, e:
            if cmd:
                raise callbacks.Error, e.msg()
            else:
                debug.msg(e.msg())

    def _formatUrl(self, url, added, addedBy):
        #debug.printf((url, added, addedBy))
        when = time.strftime(conf.humanTimestampFormat,
                             time.localtime(int(added)))
        return '<%s> (added by %s at %s)' % (url, addedBy, when)

    def _formatUrlWithId(self, id, url, added, addedBy):
        #debug.printf((id, url, added, addedBy))
        return '#%s: %s' % (id, self._formatUrl(url, added, addedBy))

    def random(self, irc, msg, args):
        """[<channel>]

        Returns a random URL from the URL database.  <channel> is only required
        if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT id, url, added, added_by
                          FROM urls
                          ORDER BY random()
                          LIMIT 1""")
        if cursor.rowcount == 0:
            irc.reply(msg, 'I have no URLs in my database for %s' % channel)
        else:
            irc.reply(msg, self._formatUrlWithId(*cursor.fetchone()))

    def tiny(self, irc, msg, args):
        """<url>

        Returns a TinyURL.com version of <url>
        """
        url = privmsgs.getArgs(args)
        if self.toggles.get('tinysnarf', channel=msg.args[0]) and\
            self.toggles.get('tinyreply', channel=msg.args[0]):
            return
        url = self._getTinyUrl(url, cmd=True)
        if not url:
            irc.error(msg, 'Could not parse the TinyURL.com results page. '\
                '(%s)' % conf.replyPossibleBug)
        else:
            irc.reply(msg, url)

    def get(self, irc, msg, args):
        """[<channel>] <id>

        Gets the URL with id <id> from the URL database for <channel>.
        <channel> is only necessary if not sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        id = privmsgs.getArgs(args)
        cursor.execute("""SELECT url, added, added_by
                          FROM urls
                          WHERE id=%s""", id)
        if cursor.rowcount == 0:
            irc.reply(msg, 'No URL was found with that id.')
        else:
            irc.reply(msg, self._formatUrl(*cursor.fetchone()))

    def num(self, irc, msg, args):
        """[<channel>]

        Returns the number of URLs in the URL database.  <channel> is only
        required if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT COUNT(*) FROM urls""")
        (count,) = cursor.fetchone()
        irc.reply(msg, 'I have %s %s in my database.' % \
                  (count, int(count) == 1 and 'URL' or 'URLs'))

    def last(self, irc, msg, args):
        """[<channel>] [--{from,with,at,proto,near}=<value>] --{nolimit,fancy}

        Gives the last URL matching the given criteria.  --from is from whom
        the URL came; --at is the site of the URL; --proto is the protocol the
        URL used; --with is something inside the URL; --near is a string in the
        messages before and after the link.  If --nolimit is given, returns as
        many URLs as can fit in the message. --fancy returns information in
        addition to just the URL. <channel> is only necessary if the
        message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        (optlist, rest) = getopt.getopt(args, '', ['from=', 'with=', 'at=',
                                                   'proto=', 'near=',
                                                   'nolimit', 'fancy'])
        criteria = ['1=1']
        formats = []
        simple = True
        nolimit = False
        for (option, argument) in optlist:
            option = option.lstrip('-') # Strip off the --.
            if option == 'nolimit':
                nolimit = True
            if option == 'fancy':
                simple = False
            elif option == 'from':
                criteria.append('added_by LIKE %s')
                formats.append(argument)
            elif option == 'with':
                if '%' not in argument and '_' not in argument:
                    argument = '%%%s%%' % argument
                criteria.append('url LIKE %s')
                formats.append(argument)
            elif option == 'at':
                if '%' not in argument and '_' not in argument:
                    argument = '%' + argument
                criteria.append('site LIKE %s')
                formats.append(argument)
            elif option == 'proto':
                criteria.append('protocol=%s')
                formats.append(argument)
            elif option == 'near':
                criteria.append("""(previous_msg LIKE %s OR
                                    next_msg LIKE %s OR
                                    current_msg LIKE %s)""")
                if '%' not in argument:
                    argument = '%%%s%%' % argument
                formats.append(argument)
                formats.append(argument)
                formats.append(argument)
        db = self.getDb(channel)
        cursor = db.cursor()
        criterion = ' AND '.join(criteria)
        sql = """SELECT id, url, added, added_by
                 FROM urls
                 WHERE %s ORDER BY id DESC
                 LIMIT 100""" % criterion
        cursor.execute(sql, *formats)
        if cursor.rowcount == 0:
            irc.reply(msg, 'No URLs matched that criteria.')
        else:
            if nolimit:
                urls = ['<%s>' % t[1] for t in cursor.fetchall()]
                s = ', '.join(urls)
            elif simple:
                s = cursor.fetchone()[1]
            else:
                (id, url, added, added_by) = cursor.fetchone()
                timestamp = time.strftime('%I:%M %p, %B %d, %Y',
                                          time.localtime(int(added)))
                s = '#%s: <%s>, added by %s at %s.' % \
                    (id, url, added_by, timestamp)
            irc.reply(msg, s)


Class = URL

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
