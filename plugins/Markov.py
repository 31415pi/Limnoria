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
Add the module docstring here.  This will be used by the setup.py script.
"""

from baseplugin import *

import random
import os.path

import sqlite

import debug
import ircutils
import privmsgs
import callbacks


def configure(onStart, afterConnect, advanced):
    # This will be called by setup.py to configure this module.  onStart and
    # afterConnect are both lists.  Append to onStart the commands you would
    # like to be run when the bot is started; append to afterConnect the
    # commands you would like to be run when the bot has finished connecting.
    from questions import expect, anything, something, yn
    onStart.append('load Markov')

class Markov(callbacks.Privmsg, ChannelDBHandler):
    def __init__(self):
        ChannelDBHandler.__init__(self)
        callbacks.Privmsg.__init__(self)

    def makeDb(self, filename):
        if os.path.exists(filename):
            return sqlite.connect(filename)
        db = sqlite.connect(filename)
        cursor = db.cursor()
        cursor.execute("""CREATE TABLE pairs (
                          id INTEGER PRIMARY KEY,
                          first TEXT,
                          second TEXT,
                          UNIQUE (first, second) ON CONFLICT IGNORE
                          )""")
        cursor.execute("""CREATE TABLE follows (
                          id INTEGER PRIMARY KEY,
                          pair_id INTEGER,
                          word TEXT
                          )""")
        cursor.execute("""CREATE INDEX follows_pair_id ON follows (pair_id)""")
        db.commit()
        return db

    def doPrivmsg(self, irc, msg):
        if not ircutils.isChannel(msg.args[0]):
            return callbacks.Privmsg.doPrivmsg(self, irc, msg)
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        words = msg.args[1].split()
        for (first, second, follower) in window(words, 3):
            cursor.execute("""INSERT INTO pairs VALUES (NULL, %s, %s)""",
                           first, second)
            cursor.execute("""SELECT id FROM pairs
                              WHERE first=%s AND second=%s""", first, second)
            id = int(cursor.fetchone()[0])
            cursor.execute("""INSERT INTO follows VALUES (NULL, %s, %s)""",
                           id, follower)
            db.commit()
        return callbacks.Privmsg.doPrivmsg(self, irc, msg)

    def markov(self, irc, msg, args):
        """[<channel>] [<length>]

        Returns a randomly-generated Markov Chain generated sentence from the
        data kept on <channel> (which is only necessary if not sent in the
        channel itself) with <length> words.  <length> must be less than 80.
        """
        channel = privmsgs.getChannel(msg, args)
        length = privmsgs.getArgs(args, needed=0, optional=1)
        db = self.getDb(channel)
        cursor = db.cursor()
        if not length:
            length = random.randrange(30, 50)
        try:
            length = int(length)
            assert 0 <= length <= 80
        except (ValueError, AssertionError):
            irc.error(msg, 'Length must be an integer between 0 and 80')
            return
        words = []
        cursor.execute("""SELECT id, first, second FROM pairs
                          ORDER BY random()
                          LIMIT 1""")
        (id, first, second) = cursor.fetchone()
        debug.printf((id, first, second))
        id = int(id)
        words.append(first)
        words.append(second)
        debug.printf(words)
        while len(words) < length:
            debug.printf((words[-2], words[-1]))
            sql = """SELECT follows.word FROM pairs, follows
                     WHERE pairs.first=%s AND
                           pairs.second=%s AND
                           pairs.id=follows.pair_id
                     ORDER BY random()
                     LIMIT 1"""
            cursor.execute(sql, words[-2], words[-1])
            results = cursor.fetchone()
            if not results:
                break
            word = results[0]
            words.append(word)
        irc.reply(msg, ' '.join(words))

    def markovpairs(self, irc, msg, args):
        """[<channel>]

        Returns the number of Markov's chain links in the database for
        <channel>.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT COUNT(*) FROM pairs""")
        n = cursor.fetchone()[0]
        s = 'There are %s pairs in my Markov database for %s' % (n, channel)
        irc.reply(msg, s)

    def markovfollows(self, irc, msg, args):
        """[<channel>]

        Returns the number of Markov's third links in the database for
        <channel>.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT COUNT(*) FROM follows""")
        n = cursor.fetchone()[0]
        s = 'There are %s follows in my Markov database for %s' % (n, channel)
        irc.reply(msg, s)


Class = Markov

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
