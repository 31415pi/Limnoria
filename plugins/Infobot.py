#!/usr/bin/python

###
# Copyright (c) 2004, Jeremiah Fincher
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
Infobot compatibility, for the parts that we don't support already.
"""

__revision__ = "$Id$"
__author__ = 'Jeremy Fincher (jemfinch) <jemfinch@users.sf.net>'

import plugins

import os
import re
import cPickle as pickle

import conf
import utils
import ircmsgs
import ircutils
import privmsgs
import callbacks

conf.registerPlugin('Infobot')

def configure(advanced):
    # This will be called by setup.py to configure this module.  Advanced is
    # a bool that specifies whether the user identified himself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    from questions import expect, anything, something, yn
    conf.registerPlugin('Infobot', True)

filename = os.path.join(conf.supybot.directories.data(), 'Infobot.db')

class InfobotDB(object):
    def __init__(self):
        try:
            fd = file(filename)
        except EnvironmentError:
            self._is = utils.InsensitivePreservingDict()
            self._are = utils.InsensitivePreservingDict()
        else:
            (self._is, self._are) = pickle.load(fd)
        self._changes = 0
        self._responses = 0

    def flush(self):
        fd = file(filename, 'w')
        pickle.dump((self._is, self._are), fd)
        fd.close()

    def close(self):
        self.flush()

    def getIs(self, factoid):
        ret = self._is[factoid]
        self._responses += 1
        return ret

    def setIs(self, fact, oid):
        self._changes += 1
        self._is[fact] = oid
        self.flush()

    def delIs(self, factoid):
        del self._is[factoid]
        self._changes += 1
        self.flush()

    def hasIs(self, factoid):
        return factoid in self._is

    def getAre(self, factoid):
        ret = self._are[factoid]
        self._responses += 1
        return ret

    def hasAre(self, factoid):
        return factoid in self._are

    def setAre(self, fact, oid):
        self._changes += 1
        self._are[fact] = oid
        self.flush()

    def delAre(self, factoid):
        del self._are[factoid]
        self._changes += 1
        self.flush()
        
    def getChangeCount(self):
        return self._changes

    def getResponseCount(self):
        return self._responses

class Infobot(callbacks.PrivmsgCommandAndRegexp):
    regexps = ['doForget', 'doFactoid', 'doUnknown']
    def __init__(self):
        self.db = InfobotDB()
        self.irc = None
        self.msg = None
        self.force = False
        self.replied = False
        self.addressed = False
        callbacks.PrivmsgCommandAndRegexp.__init__(self)

    def die(self):
        self.db.close()

    def reply(self, s, irc=None, msg=None):
        if self.replied:
            self.log.debug('Already replied, not replying again.')
            return
        if irc is None:
            assert self.irc is not None
            irc = self.irc
        if msg is None:
            assert self.msg is not None
            msg = self.msg
        self.replied = True
        irc.reply(plugins.standardSubstitute(irc, msg, s), prefixName=False)
        
    def confirm(self, irc=None, msg=None):
        # XXX
        self.reply('Roger that!', irc=irc, msg=msg)

    def dunno(self, irc=None, msg=None):
        # XXX
        self.reply('I dunno, dude.', irc=irc, msg=msg)

    def factoid(self, key, irc=None, msg=None):
        if irc is None:
            assert self.irc is not None
            irc = self.irc
        if msg is None:
            assert self.msg is not None
            msg = self.msg
        isAre = None
        key = plugins.standardSubstitute(irc, msg, key)
        if self.db.hasIs(key):
            isAre = 'is'
            value = self.db.getIs(key)
        elif self.db.hasAre(key):
            isAre = 'are'
            value = self.db.getAre(key)
        if isAre is None:
            if self.addressed:
                self.dunno(irc=irc, msg=msg)
        else:
            # XXX
            self.reply('%s %s %s, $who.' % (key,isAre,value), irc=irc, msg=msg)

    def normalize(self, s):
        s = ircutils.stripFormatting(s)
        s = s.strip() # After stripFormatting for formatted spaces.
        s = utils.normalizeWhitespace(s)
        contractions = [('what\'s', 'what is'), ('where\'s', 'where is'),
                        ('who\'s', 'who is'),]
        for (contraction, replacement) in contractions:
            if s.startswith(contraction):
                s = replacement + s[len(contraction):]
        return s
        
    _forceRe = re.compile(r'^no[,: -]+', re.I)
    def doPrivmsg(self, irc, msg):
        maybeAddressed = callbacks.addressed(irc.nick, msg,
                                             whenAddressedByNick=True)
        if maybeAddressed:
            self.addressed = True
            payload = maybeAddressed
        else:
            payload = msg.args[1]
        #print '*', payload
        payload = self.normalize(payload)
        #print '**', payload
        maybeForced = self._forceRe.sub('', payload)
        if maybeForced != payload:
            self.force = True
            payload = maybeForced
        #print '***', payload
        if payload.endswith(irc.nick):
            self.addressed = True
            payload = payload[:-len(irc.nick)]
            payload = payload.strip(', ') # Strip punctuation separating nick.
            payload += '?' # So doUnknown gets called.
        #print '****', payload
        try:
            #print 'Payload:', payload
            #print 'Force:', self.force
            #print 'Addressed:', self.addressed
            msg = ircmsgs.privmsg(msg.args[0], payload, prefix=msg.prefix)
            callbacks.PrivmsgCommandAndRegexp.doPrivmsg(self, irc, msg)
        finally:
            self.force = False
            self.replied = False
            self.addressed = False

    def callCommand(self, f, irc, msg, *L, **kwargs):
        try:
            self.irc = irc
            self.msg = msg
            callbacks.PrivmsgCommandAndRegexp.callCommand(self, f, irc, msg,
                                                          *L, **kwargs)
        finally:
            self.irc = None
            self.msg = None

    def doForget(self, irc, msg, match):
        r"^forget\s+(.+?)[?!. ]*$"
        fact = match.group(1)
        for method in [self.db.delIs, self.db.delAre]:
            try:
                method(fact)
            except KeyError:
                pass
        self.confirm()

    def doUnknown(self, irc, msg, match):
        r"^(.+?)\?[?!. ]*$"
        key = match.group(1)
        key = plugins.standardSubstitute(irc, msg, key)
        self.factoid(key) # Does the dunno'ing for us itself.
    # TODO: Add invalidCommand.

    def doFactoid(self, irc, msg, match):
        r"^(.+)\s+(was|is|am|were|are)\s+(also\s+)?(.+?)[?!. ]*$"
        (key, isAre, maybeForce, value) = match.groups()
        if key.lower() in ('where', 'what', 'who'):
            # It's a question.
            self.factoid(value)
            return
        isAre = isAre.lower()
        self.force = self.force or bool(maybeForce)
        key = plugins.standardSubstitute(irc, msg, key)
        value = plugins.standardSubstitute(irc, msg, value)
        if isAre in ('was', 'is', 'am'):
            if self.db.hasIs(key):
                if not self.force:
                    value = self.db.getIs(key)
                    self.reply('But %s is %s.' % (key, value))
                    return
                else:
                    value = '%s or %s' % (self.db.getIs(key), value)
            self.db.setIs(key, value)
        else:
            if self.db.hasAre(key):
                if not self.force:
                    value = self.db.getAre(key)
                    self.reply('But %s are %s.' % (key, value))
                    return
                else:
                    value = '%s or %s' % (self.db.getAre(key), value)
            self.db.setAre(key, value)
        if self.addressed or self.force:
            self.confirm()

    def stats(self, irc, msg, args):
        """takes no arguments

        Returns the number of changes and requests made to the Infobot database
        since the plugin was loaded.
        """
        irc.reply('There have been %s answered and %s made '
                  'to the database since this plugin was loaded.' %
                  (utils.nItems('request', self.db.getChangeCount()),
                   utils.nItems('change', self.db.getResponseCount())))
        


Class = Infobot

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
