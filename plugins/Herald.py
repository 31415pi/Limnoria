#!/usr/bin/env python

###
# Copyright (c) 2002-2004, Jeremiah Fincher
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
Greets users who join the channel with a recognized hostmask with a nice
little greeting.
"""

__revision__ = "$Id$"

import os
import time
import getopt

import supybot.log as log
import supybot.conf as conf
import supybot.utils as utils
import supybot.world as world
import supybot.ircdb as ircdb
import supybot.ircmsgs as ircmsgs
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.privmsgs as privmsgs
import supybot.registry as registry
import supybot.callbacks as callbacks

filename = os.path.join(conf.supybot.directories.data(), 'Herald.db')

class HeraldDB(plugins.ChannelUserDB):
    def serialize(self, v):
        return [v]

    def deserialize(self, channel, id, L):
        if len(L) != 1:
            raise ValueError
        return L[0]

conf.registerPlugin('Herald')
conf.registerChannelValue(conf.supybot.plugins.Herald, 'heralding',
    registry.Boolean(True, """Determines whether messages will be sent to the
    channel when a recognized user joins; basically enables or disables the
    plugin."""))
conf.registerChannelValue(conf.supybot.plugins.Herald, 'throttleTime',
    registry.PositiveInteger(600, """Determines the minimum number of seconds
    between heralds."""))
conf.registerChannelValue(conf.supybot.plugins.Herald, 'default',
    registry.String('', """Sets the default herald to use.  If a user has a
    personal herald specified, that will be used instead.  If set to the empty
    string, the default herald will be disabled."""))
conf.registerChannelValue(conf.supybot.plugins.Herald.default, 'notice',
    registry.Boolean(True, """Determines whether the default herald will be
    sent as a NOTICE instead of a PRIVMSG."""))
conf.registerChannelValue(conf.supybot.plugins.Herald.default, 'public',
    registry.Boolean(False, """Determines whether the default herald will be
    sent publicly."""))
conf.registerChannelValue(conf.supybot.plugins.Herald, 'throttleTimeAfterPart',
    registry.PositiveInteger(60, """Determines the minimum number of seconds
    after parting that the bot will not herald the person when he or she
    rejoins."""))

class Herald(callbacks.Privmsg):
    def __init__(self):
        callbacks.Privmsg.__init__(self)
        self.db = HeraldDB(filename)
        world.flushers.append(self.db.flush)
        self.lastParts = plugins.ChannelUserDictionary()
        self.lastHerald = plugins.ChannelUserDictionary()

    def die(self):
        if self.db.flush in world.flushers:
            world.flushers.remove(self.db.flush)
        self.db.close()
        callbacks.Privmsg.die(self)

    def doJoin(self, irc, msg):
        channel = msg.args[0]
        if self.registryValue('heralding', channel):
            try:
                id = ircdb.users.getUserId(msg.prefix)
                herald = self.db[channel, id]
            except KeyError:
                default = self.registryValue('default', channel)
                if default:
                    default = plugins.standardSubstitute(irc, msg, default)
                    msgmaker = ircmsgs.privmsg
                    if self.registryValue('default.notice', channel):
                        msgmaker = ircmsgs.notice
                    target = msg.nick
                    if self.registryValue('default.public', channel):
                        target = channel
                    irc.queueMsg(msgmaker(target, default))
                return
            now = time.time()
            throttle = self.registryValue('throttleTime', channel)
            if now - self.lastHerald.get((channel, id), 0) > throttle:
                if (channel, id) in self.lastParts:
                   i = self.registryValue('throttleTimeAfterPart', channel)
                   if now - self.lastParts[channel, id] < i:
                       return
                self.lastHerald[channel, id] = now
                herald = plugins.standardSubstitute(irc, msg, herald)
                irc.queueMsg(ircmsgs.privmsg(channel, herald))

    def doPart(self, irc, msg):
        try:
            id = self._getId(irc, msg.prefix)
            self.lastParts[msg.args[0], id] = time.time()
        except KeyError:
            pass

    def _getId(self, irc, userNickHostmask):
        try:
            id = ircdb.users.getUserId(userNickHostmask)
        except KeyError:
            if not ircutils.isUserHostmask(userNickHostmask):
                hostmask = irc.state.nickToHostmask(userNickHostmask)
                id = ircdb.users.getUserId(hostmask)
            else:
                raise KeyError
        return id

    def default(self, irc, msg, args):
        """[<channel>] [--remove|<msg>]

        If <msg> is given, sets the default herald to <msg>.  A <msg> of ""
        will remove the default herald.  If <msg> is not given, returns the
        current default herald.  <channel> is only necessary if the message
        isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        (optlist, rest) = getopt.getopt(args, '', ['remove'])
        if optlist and rest:
            raise callbacks.ArgumentError
        for (option, _) in optlist:
            if option == '--remove':
                self.setRegistryValue('default', '', channel)
                irc.replySuccess()
                return
        text = privmsgs.getArgs(rest, required=0, optional=1)
        if not text:
            resp = self.registryValue('default', channel)
            if not resp:
                irc.reply('I do not have a default herald set.')
                return
            else:
                irc.reply(resp)
                return
        self.setRegistryValue('default', text, channel)
        irc.replySuccess()

    def get(self, irc, msg, args):
        """[<channel>] <user|nick|hostmask>

        Returns the current herald message for <user> (or the user
        <nick|hostmask> is currently identified or recognized as).  <channel>
        is only necessary if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        userNickHostmask = privmsgs.getArgs(args)
        try:
            id = self._getId(irc, userNickHostmask)
        except KeyError:
            irc.errorNoUser()
            return
        try:
            herald = self.db[channel, id]
            irc.reply(herald)
        except KeyError:
            irc.error('I have no herald for that user.')

    def add(self, irc, msg, args):
        """[<channel>] <user|nick|hostmask> <msg>

        Sets the herald message for <user> (or the user <nick|hostmask> is
        currently identified or recognized as) to <msg>.  <channel> is only
        necessary if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        (userNickHostmask, herald) = privmsgs.getArgs(args, required=2)
        try:
            id = self._getId(irc, userNickHostmask)
        except KeyError:
            irc.errorNoUser()
            return
        self.db[channel, id] = herald
        irc.replySuccess()

    def remove(self, irc, msg, args):
        """[<channel>] <user|nick|hostmask>

        Removes the herald message set for <user>, or the user
        <nick|hostmask> is currently identified or recognized as.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        channel = privmsgs.getChannel(msg, args)
        userNickHostmask = privmsgs.getArgs(args)
        try:
            id = self._getId(irc, userNickHostmask)
        except KeyError:
            irc.errorNoUser()
            return
        del self.db[channel, id]
        irc.replySuccess()

    def change(self, irc, msg, args):
        """[<channel>] <user|nick|hostmask> <regexp>

        Changes the herald message for <user>, or the user <nick|hostmask> is
        currently identified or recognized as, according to <regexp>.  <channel>
        is only necessary if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        (userNickHostmask, regexp) = privmsgs.getArgs(args, required=2)
        try:
            id = self._getId(irc, userNickHostmask)
        except KeyError:
            irc.errorNoUser()
            return
        try:
            changer = utils.perlReToReplacer(regexp)
        except ValueError, e:
            irc.error('That\'s not a valid regexp: %s.' % e)
            return
        s = self.db[channel, id]
        newS = changer(s)
        self.db[channel, id] = newS
        irc.replySuccess()


Class = Herald

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
