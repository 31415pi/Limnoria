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
Silently listens to every message received on a channel and keeps statistics
concerning joins, parts, and various other commands in addition to tracking
statistics about smileys, actions, characters, and words.
"""

__revision__ = "$Id$"

import plugins

import os
import re
import sets
import time
import getopt
import string
from itertools import imap, ifilter

import conf
import utils
import ircdb
import ircmsgs
import plugins
import privmsgs
import ircutils
import callbacks
import configurable

try:
    import sqlite
except ImportError:
    raise callbacks.Error, 'You need to have PySQLite installed to use this ' \
                           'plugin.  Download it at <http://pysqlite.sf.net/>'

def SmileyType(s):
    try:
        L = configurable.SpaceSeparatedStrListType(s)
        return re.compile('|'.join(imap(re.escape, L)))
    except configurable.Error:
        raise configurable.Error, 'Value must be a space-separated list of ' \
                                  'smileys or frowns.'
    
class ChannelDB(plugins.ChannelDBHandler,
                configurable.Mixin,
                callbacks.Privmsg):
    noIgnore = True
    configurables = configurable.Dictionary(
        [('self-stats', configurable.BoolType, True,
          """Determines whether the bot will keep channel statistics on itself,
          possibly skewing the channel stats (especially in cases where he's
          relaying between channels on a network."""),
         ('wordstats-top-n', configurable.IntType, 3,
          """Determines the maximum number of top users to show for a given
          wordstat when you request the wordstats for a particular word."""),
         ('smileys', SmileyType, SmileyType(':) ;) ;] :-) :-D :D :P :p (= =)'),
          """Determines what words count as smileys for the purpose of keeping
          statistics on the number of smileys each user has sent to the
          channel."""),
         ('frowns', SmileyType, SmileyType(':| :-/ :-\\ :\\ :/ :( :-( :\'('),
          """Determines what words count as frowns for the purpose of keeping
          statistics on the number of frowns each user has sent ot the
          channel."""),]
        )
    def __init__(self):
        callbacks.Privmsg.__init__(self)
        configurable.Mixin.__init__(self)
        plugins.ChannelDBHandler.__init__(self)
        self.lastmsg = None
        self.laststate = None
        self.outFiltering = False

    def die(self):
        callbacks.Privmsg.die(self)
        configurable.Mixin.die(self)
        plugins.ChannelDBHandler.die(self)

    def makeDb(self, filename):
        if os.path.exists(filename):
            db = sqlite.connect(filename)
        else:
            db = sqlite.connect(filename)
            cursor = db.cursor()
            cursor.execute("""CREATE TABLE user_stats (
                              id INTEGER PRIMARY KEY,
                              user_id INTEGER UNIQUE ON CONFLICT IGNORE,
                              last_seen TIMESTAMP,
                              last_msg TEXT,
                              smileys INTEGER,
                              frowns INTEGER,
                              chars INTEGER,
                              words INTEGER,
                              msgs INTEGER,
                              actions INTEGER,
                              joins INTEGER,
                              parts INTEGER,
                              kicks INTEGER,
                              kicked INTEGER,
                              modes INTEGER,
                              topics INTEGER,
                              quits INTEGER
                              )""")
            cursor.execute("""CREATE TABLE channel_stats (
                              smileys INTEGER,
                              frowns INTEGER,
                              chars INTEGER,
                              words INTEGER,
                              msgs INTEGER,
                              actions INTEGER,
                              joins INTEGER,
                              parts INTEGER,
                              kicks INTEGER,
                              modes INTEGER,
                              topics INTEGER,
                              quits INTEGER
                              )""")
            cursor.execute("""CREATE TABLE nick_seen (
                              name TEXT,
                              normalized TEXT UNIQUE ON CONFLICT REPLACE,
                              last_seen TIMESTAMP,
                              last_msg TEXT
                              )""")
            cursor.execute("""INSERT INTO channel_stats
                              VALUES (0, 0, 0, 0, 0, 0,
                                      0, 0, 0, 0, 0, 0)""")
            cursor.execute("""CREATE TABLE words (
                              id INTEGER PRIMARY KEY,
                              word TEXT UNIQUE ON CONFLICT IGNORE
                              )""")
            cursor.execute("""CREATE TABLE word_stats (
                              id INTEGER PRIMARY KEY,
                              word_id INTEGER,
                              user_id INTEGER,
                              count INTEGER,
                              UNIQUE (word_id, user_id) ON CONFLICT IGNORE
                              )""")
            cursor.execute("""CREATE INDEX word_stats_word_id
                              ON word_stats (word_id)""")
            cursor.execute("""CREATE INDEX word_stats_user_id
                              ON word_stats (user_id)""")
            db.commit()
        def p(s1, s2):
            return int(ircutils.nickEqual(s1, s2))
        db.create_function('nickeq', 2, p)
        return db

    def __call__(self, irc, msg):
        try:
            if self.lastmsg:
                self.laststate.addMsg(irc, self.lastmsg)
            else:
                self.laststate = irc.state.copy()
        finally:
            self.lastmsg = msg
        super(ChannelDB, self).__call__(irc, msg)
        
    def doPrivmsg(self, irc, msg):
        if ircutils.isChannel(msg.args[0]):
            self._updatePrivmsgStats(msg)
            self._updateWordStats(msg)

    _alphanumeric = string.ascii_letters + string.digits
    _nonAlphanumeric = string.ascii.translate(string.ascii, _alphanumeric)
    def _updateWordStats(self, msg):
        try:
            if self.outFiltering:
                id = 0
            else:
                id = ircdb.users.getUserId(msg.prefix)
        except KeyError:
            return
        (channel, s) = msg.args
        db = self.getDb(channel)
        cursor = db.cursor()
        words = s.lower().split()
        words = [s.strip(self._nonAlphanumeric) for s in words]
        criteria = ['word=%s'] * len(words)
        criterion = ' OR '.join(criteria)
        cursor.execute("SELECT id, word FROM words WHERE %s"%criterion, *words)
        for (wordId, word) in cursor.fetchall():
            cursor.execute("""INSERT INTO word_stats
                              VALUES(NULL, %s, %s, 0)""", wordId, id)
            cursor.execute("""UPDATE word_stats SET count=count+%s
                              WHERE word_id=%s AND user_id=%s""",
                           words.count(word), wordId, id)
        db.commit()

    def _updatePrivmsgStats(self, msg):
        (channel, s) = msg.args
        db = self.getDb(channel)
        cursor = db.cursor()
        chars = len(s)
        words = len(s.split())
        isAction = ircmsgs.isAction(msg)
        frowns = len(self.configurables.get('frowns', channel).findall(s))
        smileys = len(self.configurables.get('smileys', channel).findall(s))
        s = ircmsgs.prettyPrint(msg)
        cursor.execute("""UPDATE channel_stats
                          SET smileys=smileys+%s,
                              frowns=frowns+%s,
                              chars=chars+%s,
                              words=words+%s,
                              msgs=msgs+1,
                              actions=actions+%s""",
                       smileys, frowns, chars, words, int(isAction))
        cursor.execute("""INSERT INTO nick_seen VALUES (%s, %s, %s, %s)""",
                       msg.nick,ircutils.toLower(msg.nick),int(time.time()),s)
        try:
            if self.outFiltering:
                id = 0
            else:
                id = ircdb.users.getUserId(msg.prefix)
        except KeyError:
            return
        cursor.execute("""INSERT INTO user_stats VALUES (
                          NULL, %s, %s, %s, %s, %s,
                          %s, %s, 1, %s,
                          0, 0, 0, 0, 0, 0, 0)""",
                       id, int(time.time()), s,
                       smileys, frowns, chars, words, int(isAction))
        cursor.execute("""UPDATE user_stats SET
                          last_seen=%s, last_msg=%s, chars=chars+%s,
                          words=words+%s, msgs=msgs+1,
                          actions=actions+%s, smileys=smileys+%s,
                          frowns=frowns+%s
                          WHERE user_id=%s""",
                       int(time.time()), s, chars, words, int(isAction),
                       smileys, frowns, id)
        db.commit()

    def outFilter(self, irc, msg):
        if msg.command == 'PRIVMSG':
            if ircutils.isChannel(msg.args[0]):
                if self.configurables.get('self-stats', msg.args[0]):
                    db = self.getDb(msg.args[0])
                    cursor = db.cursor()
                    try:
                        self.outFiltering = True
                        self._updatePrivmsgStats(msg)
                    finally:
                        self.outFiltering = False
        return msg

    def doPart(self, irc, msg):
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""UPDATE channel_stats SET parts=parts+1""")
        try:
            id = ircdb.users.getUserId(msg.prefix)
            cursor.execute("""UPDATE user_stats SET parts=parts+1
                              WHERE user_id=%s""", id)
        except KeyError:
            pass
        db.commit()

    def doTopic(self, irc, msg):
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""UPDATE channel_stats SET topics=topics+1""")
        try:
            id = ircdb.users.getUserId(msg.prefix)
            cursor.execute("""UPDATE user_stats
                              SET topics=topics+1
                              WHERE user_id=%s""", id)
        except KeyError:
            pass
        db.commit()

    def doMode(self, irc, msg):
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""UPDATE channel_stats SET modes=modes+1""")
        try:
            id = ircdb.users.getUserId(msg.prefix)
            cursor.execute("""UPDATE user_stats
                              SET modes=modes+1
                              WHERE user_id=%s""", id)
        except KeyError:
            pass
        db.commit()

    def doKick(self, irc, msg):
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""UPDATE channel_stats SET kicks=kicks+1""")
        try:
            id = ircdb.users.getUserId(msg.prefix)
            cursor.execute("""UPDATE user_stats
                              SET kicks=kicks+1
                              WHERE user_id=%s""", id)
        except KeyError:
            pass
        try:
            kicked = msg.args[1]
            id = ircdb.users.getUserId(irc.state.nickToHostmask(kicked))
            cursor.execute("""UPDATE user_stats
                              SET kicked=kicked+1
                              WHERE user_id=%s""", id)
        except KeyError:
            pass
        db.commit()

    def doJoin(self, irc, msg):
        channel = msg.args[0]
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""UPDATE channel_stats SET joins=joins+1""")
        try:
            id = ircdb.users.getUserId(msg.prefix)
            cursor.execute("""UPDATE user_stats
                              SET joins=joins+1
                              WHERE user_id=%s""", id)
        except KeyError:
            pass
        db.commit()

    def doQuit(self, irc, msg):
        for (channel, c) in self.laststate.channels.iteritems():
            if msg.nick in c.users:
                db = self.getDb(channel)
                cursor = db.cursor()
                cursor.execute("""UPDATE channel_stats SET quits=quits+1""")
                try:
                    id = ircdb.users.getUserId(msg.prefix)
                    cursor.execute("""UPDATE user_stats SET quits=quits+1
                                      WHERE user_id=%s""", id)
                except KeyError:
                    pass
                db.commit()

    def seen(self, irc, msg, args):
        """[<channel>] [--user] <name>

        Returns the last time <name> was seen and what <name> was last seen
        saying.  --user will look for user <name> instead of using <name> as
        a nick (registered users, remember, can be recognized under any number
        of nicks) <channel> is only necessary if the message isn't sent on the
        channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        (optlist, rest) = getopt.getopt(args, '', ['user'])
        name = privmsgs.getArgs(rest)
        if ('--user', '') in optlist:
            table = 'user_stats'
            criterion = 'user_id=%s'
            try:
                name = ircdb.users.getUserId(name)
            except KeyError:
                try:
                    hostmask = irc.state.nickToHostmask(name)
                    name = ircdb.users.getUserId(hostmask)
                except KeyError:
                    irc.error(msg, conf.replyNoUser)
        else:
            table = 'nick_seen'
            criterion = 'normalized=%s'
            name = ircutils.toLower(name)
        sql = "SELECT last_seen,last_msg FROM %s WHERE %s" % (table,criterion)
        cursor.execute(sql, name)
        if cursor.rowcount == 0:
            irc.reply(msg, 'I have not seen %s.' % name)
        else:
            (seen, m) = cursor.fetchone()
            seen = int(seen)
            if isinstance(name, int):
                name = ircdb.users.getUser(int(name)).name
            s = '%s was last seen here %s ago saying: %s' % \
                (name, utils.timeElapsed(time.time() - seen), m)
            irc.reply(msg, s)

    def stats(self, irc, msg, args):
        """[<channel>] [<name>]

        Returns the statistics for <name> on <channel>.  <channel> is only
        necessary if the message isn't sent on the channel itself.  If <name>
        isn't given, it defaults to the user sending the command.
        """
        channel = privmsgs.getChannel(msg, args)
        name = privmsgs.getArgs(args, required=0, optional=1)
        if not name:
            try:
                id = ircdb.users.getUserId(msg.prefix)
                name = ircdb.users.getUser(id).name
            except KeyError:
                irc.error(msg, 'I couldn\'t find you in my user database.')
                return
        elif not ircdb.users.hasUser(name):
            try:
                hostmask = irc.state.nickToHostmask(name)
                id = ircdb.users.getUserId(hostmask)
            except KeyError:
                irc.error(msg, conf.replyNoUser)
                return
        else:
            id = ircdb.users.getUserId(name)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT * FROM user_stats WHERE user_id=%s""", id)
        if cursor.rowcount == 0:
            irc.error(msg, 'I have no stats for that user.')
            return
        values = cursor.fetchone()
        s = '%s has sent %s; a total of %s, %s, ' \
            '%s, and %s; %s of those messages %s' \
            '%s has joined %s, parted %s, quit %s, kicked someone %s, '\
            'been kicked %s, changed the topic %s, ' \
            'and changed the mode %s.' % \
            (name, utils.nItems('message', values.msgs),
             utils.nItems('character', values.chars),
             utils.nItems('word', values.words),
             utils.nItems('smiley', values.smileys),
             utils.nItems('frown', values.frowns),
             values.actions, values.actions == 1 and 'was an ACTION.  '
                                                 or 'were ACTIONs.  ',
             name,
             utils.nItems('time', values.joins),
             utils.nItems('time', values.parts),
             utils.nItems('time', values.quits),
             utils.nItems('time', values.kicks),
             utils.nItems('time', values.kicked),
             utils.nItems('time', values.topics),
             utils.nItems('time', values.modes))
        irc.reply(msg, s)

    def channelstats(self, irc, msg, args):
        """[<channel>]

        Returns the statistics for <channel>.  <channel> is only necessary if
        the message isn't sent on the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""SELECT * FROM channel_stats""")
        values = cursor.fetchone()
        s = 'On %s there have been %s messages, containing %s characters, ' \
            '%s words, %s smileys, and %s frowns; %s of those messages were ' \
            'ACTIONs.  There have been %s joins, %s parts, %s quits, ' \
            '%s kicks, %s mode changes, and %s topic changes.' % \
            (channel, values.msgs, values.chars,
             values.words, values.smileys, values.frowns, values.actions,
             values.joins, values.parts, values.quits,
             values.kicks, values.modes, values.topics)
        irc.reply(msg, s)

    def addword(self, irc, msg, args):
        """[<channel>] <word>

        Keeps stats on <word> in <channel>.  <channel> is only necessary if the
        message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        word = privmsgs.getArgs(args)
        word = word.strip()
        if word.strip(self._nonAlphanumeric) != word:
            irc.error(msg, '<word> must not contain non-alphanumeric chars.')
            return
        word = word.lower()
        db = self.getDb(channel)
        cursor = db.cursor()
        cursor.execute("""INSERT INTO words VALUES (NULL, %s)""", word)
        db.commit()
        irc.replySuccess(msg)

    def wordstats(self, irc, msg, args):
        """[<channel>] [<user>] [<word>]

        With no arguments, returns the list of words that are being monitored
        for stats.  With <user> alone, returns all the stats for that user.
        With <word> alone, returns the top users for that word.  With <user>
        and <word>, returns that user's stat for that word. <channel> is only
        needed if not said in the channel.  (Note: if only one of <user> or
        <word> is given, <word> is assumed first and only if no stats are
        available for that word, do we assume it's <user>.)
        """
        channel = privmsgs.getChannel(msg, args)
        (arg1, arg2) = privmsgs.getArgs(args, required=0, optional=2)
        db = self.getDb(channel)
        cursor = db.cursor()
        if not arg1 and not arg2:
            cursor.execute("""SELECT word FROM words""")
            if cursor.rowcount == 0:
                irc.reply(msg, 'I am not currently keeping any word stats.')
                return
            l = [repr(tup[0]) for tup in cursor.fetchall()]
            s = 'Currently keeping stats for: %s' % utils.commaAndify(l)
            irc.reply(msg, s)
        elif arg1 and arg2:
            user, word = (arg1, arg2)
            try:
                id = ircdb.users.getUserId(user)
            except KeyError: # Maybe it was a nick.  Check the hostmask.
                try:
                    hostmask = irc.state.nickToHostmask(user)
                    id = ircdb.users.getUserId(hostmask)
                except KeyError:
                    irc.error(msg, conf.replyNoUser)
                    return
            db = self.getDb(channel)
            cursor = db.cursor()
            word = word.lower()
            cursor.execute("""SELECT word_stats.count FROM words, word_stats
                              WHERE words.word=%s AND
                                    word_id=words.id AND
                                    word_stats.user_id=%s""", word, id)
            if cursor.rowcount == 0:
                cursor.execute("""SELECT id FROM words WHERE word=%s""", word)
                if cursor.rowcount == 0:
                    irc.error(msg, 'I\'m not keeping stats on %r.' % word)
                else:
                    irc.error(msg, '%s has never said %r.' % (user, word))
                return
            count = int(cursor.fetchone()[0])
            s = '%s has said %r %s.' % (user,word,utils.nItems('time', count))
            irc.reply(msg, s)
        else:
            # Figure out if we got a user or a word
            cursor.execute("""SELECT word FROM words
                              WHERE word=%s""", arg1)
            if cursor.rowcount == 0:
                # It was a user.
                try:
                    id = ircdb.users.getUserId(arg1)
                except KeyError: # Maybe it was a nick.  Check the hostmask.
                    try:
                        hostmask = irc.state.nickToHostmask(arg1)
                        id = ircdb.users.getUserId(hostmask)
                    except KeyError:
                        irc.error(msg, '%r doesn\'t look like a user I know '
                                           'or a word that I\'m keeping stats '
                                           'on' % arg1)
                        return
                cursor.execute("""SELECT words.word, word_stats.count
                                  FROM words, word_stats
                                  WHERE words.id = word_stats.word_id
                                  AND word_stats.user_id=%s
                                  ORDER BY words.word""", id)
                if cursor.rowcount == 0:
                    username = ircdb.users.getUser(id).name
                    irc.error(msg, '%r has no wordstats' % username)
                    return
                L = [('%r: %s' % (word, count)) for \
                     (word, count) in cursor.fetchall()]
                irc.reply(msg, utils.commaAndify(L))
                return
            else:
                # It's a word, not a user
                word = arg1
                numUsers = self.configurables.get('wordstats-top-n',
                                                  msg.args[0])
                cursor.execute("""SELECT word_stats.count,
                                         word_stats.user_id
                                  FROM words, word_stats
                                  WHERE words.word=%s AND
                                        words.id=word_stats.word_id
                                  ORDER BY word_stats.count DESC""",
                                  word)
                if cursor.rowcount == 0:
                    irc.error(msg, 'No one has said %r' % word)
                    return
                results = cursor.fetchall()
                numResultsShown = min(cursor.rowcount, numUsers)
                cursor.execute("""SELECT sum(word_stats.count)
                                  FROM words, word_stats
                                  WHERE words.word=%s AND
                                        words.id=word_stats.word_id""",
                                  word)
                total = int(cursor.fetchone()[0])
                ers = '%rer' % word
                ret = 'Top %s ' % utils.nItems(ers, numResultsShown)
                ret += '(out of a total of %s seen):' % \
                             utils.nItems(repr(word), total)
                L = []
                for (count, id) in results[:numResultsShown]:
                    username = ircdb.users.getUser(id).name
                    L.append('%s: %s' % (username, count))
                try:
                    id = ircdb.users.getUserId(msg.prefix)
                    rank = 1
                    s = ""  # Don't say anything if they show in the output
                            # already
                    seenUser = False
                    for (count, userId) in results:
                        if userId == id:
                            seenUser = True
                            if rank > numResultsShown:
                                s = 'You are ranked %s out of %s with %s.' % \
                                    (rank, utils.nItems(ers, len(results)),
                                     utils.nItems(repr(word), count))
                                break
                        else:
                            rank += 1
                    else:
                        if not seenUser:
                            s = 'You have not said %r' % word
                    ret = '%s %s.  %s' % (ret, utils.commaAndify(L), s)
                except KeyError:
                    ret = '%s %s.' % (ret, utils.commaAndify(L))
                irc.reply(msg, ret)
                           
Class = ChannelDB

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
