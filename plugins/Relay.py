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
Handles relaying between networks.

Commands include:
  startrelay
  relayconnect
  relaydisconnect
  relayjoin
  relaypart
"""

from baseplugin import *

import ircdb
import debug
import irclib
import ircmsgs
import ircutils
import privmsgs
import callbacks
import asyncoreDrivers

class IdDict(dict):
    def __setitem__(self, key, value):
        dict.__setitem__(self, id(key), value)

    def __getitem__(self, key):
        return dict.__getitem__(self, id(key))

    def __contains__(self, key):
        return dict.__contains__(self, id(key))

class Relay(callbacks.Privmsg):
    def __init__(self):
        callbacks.Privmsg.__init__(self)
        self.ircs = []
        self.started = False
        self.abbreviations = {} #IdDict({})
        
    def startrelay(self, irc, msg, args):
        "<network abbreviation for current server>"
        if ircdb.checkCapability(msg.prefix, 'owner'):
            realIrc = irc.getRealIrc()
            abbreviation = privmsgs.getArgs(args)
            self.ircs.append(realIrc)
            self.abbreviations[realIrc] = abbreviation
            self.started = True
            irc.reply(msg, conf.replySuccess)
        else:
            irc.error(msg, conf.replyNoCapability % 'owner')

    def relayconnect(self, irc, msg, args):
        "<network abbreviation> <domain:port> (port defaults to 6667)"
        if ircdb.checkCapability(msg.prefix, 'owner'):
            abbreviation, server = privmsgs.getArgs(args, needed=2)
            if ':' in server:
                (server, port) = server.split(':')
                port = int(port)
            else:
                port = 6667
            newIrc = irclib.Irc(irc.nick, callbacks=irc.callbacks)
            driver = asyncoreDrivers.AsyncoreDriver((server, port))
            driver.irc = newIrc
            newIrc.driver = driver
            self.ircs.append(newIrc)
            self.abbreviations[newIrc] = abbreviation
            irc.reply(msg, conf.replySuccess)
        else:
            irc.reply(msg, conf.replyNoCapability % 'owner')

    def relaydisconnect(self, irc, msg, args):
        "<network>"
        pass

    def relayjoin(self, irc, msg, args):
        "<channel>"
        if ircdb.checkCapability(msg.prefix, 'owner'):
            channel = privmsgs.getArgs(args)
            for otherIrc in self.ircs:
                if channel not in otherIrc.state.channels:
                    otherIrc.queueMsg(ircmsgs.join(channel))
            irc.reply(msg, conf.replySuccess)
        else:
            irc.reply(msg, conf.replyNoCapability % 'owner')

    def relaypart(self, irc, msg, args):
        "<channel>"
        if ircdb.checkCapability(msg.prefix, 'owner'):
            channel = privmsgs.getArgs(args)
            for otherIrc in self.ircs:
                if channel in otherIrc.state.channels:
                    otherIrc.queueMsg(ircmsgs.part(channel))
            irc.reply(msg, conf.replySuccess)
        else:
            irc.reply(msg, conf.replyNoCapability % 'owner')

    def doPrivmsg(self, irc, msg):
        callbacks.Privmsg.doPrivmsg(self, irc, msg)
        if not isinstance(irc, irclib.Irc):
            irc = irc.getRealIrc()
        if self.started and ircutils.isChannel(msg.args[0]):
            channel = msg.args[0]
            debug.printf('self.abbreviations = %s' % self.abbreviations)
            debug.printf('self.ircs = %s' % self.ircs)
            debug.printf('irc = %s' % irc)
            abbreviation = self.abbreviations[irc]
            s = '<%s@%s> %s' % (msg.nick, abbreviation, msg.args[1])
            for otherIrc in self.ircs:
                debug.printf('otherIrc = %s' % otherIrc)
                if otherIrc != irc:
                    debug.printf('otherIrc != irc')
                    debug.printf('id(irc) = %s, id(otherIrc) = %s' % \
                                 (id(irc), id(otherIrc)))
                    if channel in otherIrc.state.channels:
                        otherIrc.queueMsg(ircmsgs.privmsg(channel, s))

    def doJoin(self, irc, msg):
        if self.started:
            channels = msg.args[0].split(',')
            abbreviation = self.abbreviations[irc]
            s = '%s has joined on %s' % (msg.nick, abbreviation)
            for otherIrc in self.ircs:
                if otherIrc != irc:
                    for channel in channels:
                        if channel in otherIrc.state.channels:
                            otherIrc.queueMsg(ircmsgs.privmsg(channel, s))

    def doPart(self, irc, msg):
        if self.started:
            channels = msg.args[0].split(',')
            abbreviation = self.abbreviations[irc]
            s = '%s has left on %s' % (msg.nick, abbreviation)
            for otherIrc in self.ircs:
                if otherIrc == irc:
                    continue
                for channel in channels:
                    if channel in otherIrc.state.channels:
                        otherIrc.queueMsg(ircmsgs.privmsg(channel, s))

Class = Relay
        
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
