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
These are commands useful for administrating the bot; they all require their
caller to have the 'admin' capability.  This plugin is loaded by default.
"""

import supybot

__revision__ = "$Id$"
__author__ = supybot.authors.jemfinch

import supybot.fix as fix

import sys
import time
import pprint
from itertools import imap

import supybot.log as log
import supybot.conf as conf
import supybot.ircdb as ircdb
import supybot.utils as utils
import supybot.ircmsgs as ircmsgs
from supybot.commands import additional, wrap
import supybot.ircutils as ircutils
import supybot.privmsgs as privmsgs
import supybot.schedule as schedule
import supybot.callbacks as callbacks


class Admin(privmsgs.CapabilityCheckingPrivmsg):
    capability = 'admin'
    def __init__(self):
        self.__parent = super(Admin, self)
        self.__parent.__init__()
        self.joins = {}
        self.pendingNickChanges = {}

    def do437(self, irc, msg):
        """Nick/channel temporarily unavailable."""
        target = msg.args[0]
        if irc.isChannel(target): # We don't care about nicks.
            t = time.time() + 30
            # Let's schedule a rejoin.
            def rejoin():
                irc.queueMsg(ircmsgs.join(target))
                # We don't need to schedule something because we'll get another
                # 437 when we try to join later.
            schedule.addEvent(rejoin, t)
            self.log.info('Scheduling a rejoin to %s at %s; '
                          'Channel temporarily unavailable.', target, t)

    def do471(self, irc, msg):
        try:
            channel = msg.args[1]
            (irc, msg) = self.joins.pop(channel)
            irc.error('Cannot join %s, it\'s full.' % channel)
        except KeyError:
            self.log.debug('Got 471 without Admin.join being called.')

    def do473(self, irc, msg):
        try:
            channel = msg.args[1]
            (irc, msg) = self.joins.pop(channel)
            irc.error('Cannot join %s, I was not invited.' % channel)
        except KeyError:
            self.log.debug('Got 473 without Admin.join being called.')

    def do474(self, irc, msg):
        try:
            channel = msg.args[1]
            (irc, msg) = self.joins.pop(channel)
            irc.error('Cannot join %s, it\'s banned me.' % channel)
        except KeyError:
            self.log.debug('Got 474 without Admin.join being called.')

    def do475(self, irc, msg):
        try:
            channel = msg.args[1]
            (irc, msg) = self.joins.pop(channel)
            irc.error('Cannot join %s, my keyword was wrong.' % channel)
        except KeyError:
            self.log.debug('Got 475 without Admin.join being called.')

    def do515(self, irc, msg):
        try:
            channel = msg.args[1]
            (irc, msg) = self.joins.pop(channel)
            irc.error('Cannot join %s, I\'m not identified with the NickServ.'
                      % channel)
        except KeyError:
            self.log.debug('Got 515 without Admin.join being called.')

    def doJoin(self, irc, msg):
        if msg.prefix == irc.prefix:
            try:
                del self.joins[msg.args[0]]
            except KeyError:
                s = 'Joined a channel without Admin.join being called.'
                self.log.debug(s)

    def doInvite(self, irc, msg):
        channel = msg.args[1]
        if channel not in irc.state.channels:
            if conf.supybot.alwaysJoinOnInvite() or \
               ircdb.checkCapability(msg.prefix, 'admin'):
                self.log.info('Invited to %s by %s.', channel, msg.prefix)
                irc.queueMsg(ircmsgs.join(channel))
                conf.supybot.channels().add(channel)

    def join(self, irc, msg, args):
        """<channel>[,<key>] [<channel>[,<key>] ...]

        Tell the bot to join the whitespace-separated list of channels
        you give it.  If a channel requires a key, attach it behind the
        channel name via a comma.  I.e., if you need to join both #a and #b,
        and #a requires a key of 'aRocks', then you'd call 'join #a,aRocks #b'
        """
        if not args:
            raise callbacks.ArgumentError
        keys = []
        channels = []
        for channel in args:
            original = channel
            if ',' in channel:
                (channel, key) = channel.split(',', 1)
                channels.insert(0, channel)
                keys.insert(0, key)
            else:
                channels.append(channel)
            if not irc.isChannel(channel):
                irc.errorInvalid('channel', channel)
                return
            conf.supybot.channels().add(original)
        maxchannels = irc.state.supported.get('maxchannels', sys.maxint)
        if len(irc.state.channels) + len(channels) > maxchannels:
            irc.error('I\'m already too close to maximum number of '
                      'channels for this network.', Raise=True)
        irc.queueMsg(ircmsgs.joins(channels, keys))
        irc.noReply()
        for channel in channels:
            self.joins[channel] = (irc, msg)

    def channels(self, irc, msg, args):
        """takes no arguments

        Returns the channels the bot is on.  Must be given in private, in order
        to protect the secrecy of secret channels.
        """
        L = irc.state.channels.keys()
        if L:
            utils.sortBy(ircutils.toLower, L)
            irc.reply(utils.commaAndify(L))
        else:
            irc.reply('I\'m not currently in any channels.')
    channels = wrap(channels, ['private'])

    def do484(self, irc, msg):
        irc = self.pendingNickChanges.get(irc, None)
        if irc is not None:
            irc.error('My connection is restricted, I can\'t change nicks.')
        else:
            self.log.debug('Got 484 without Admin.nick being called.')

    def do433(self, irc, msg):
        irc = self.pendingNickChanges.get(irc, None)
        if irc is not None:
            irc.error('Someone else is already using that nick.')
        else:
            self.log.debug('Got 433 without Admin.nick being called.')

    def do438(self, irc, msg):
        """Can't change nick while in +m channel.  Could just be Freenode."""
        irc = self.pendingNickChanges.get(irc, None)
        if irc is not None:
            channel = msg.args[-1].strip().split()[-1][1:-1]
            assert hasattr(irc, 'msg')
            if ircutils.strEqual(irc.msg.args[0], channel):
                irc.error('I can\'t change nicks, '
                          '%s is +m and I\'m -v.' % channel, private=True)
            else:
                irc.error('I can\'t change nicks, '
                          'a channel I\'m in is +m and I\'m -v in it.')
        else:
            self.log.debug('Got 438 without Admin.nick being called.')

    def doNick(self, irc, msg):
        if msg.nick == irc.nick or msg.args[0] == irc.nick:
            try:
                del self.pendingNickChanges[irc]
            except KeyError:
                self.log.debug('Got NICK without Admin.nick being called.')

    def nick(self, irc, msg, args, nick):
        """[<nick>]

        Changes the bot's nick to <nick>.  If no nick is given, returns the
        bot's current nick.
        """
        if nick:
            conf.supybot.nick.setValue(nick)
            irc.queueMsg(ircmsgs.nick(nick))
            self.pendingNickChanges[irc.getRealIrc()] = irc
        else:
            irc.reply(irc.nick)
    nick = wrap(nick, [additional('nick')])

    def part(self, irc, msg, args):
        """<channel> [<channel> ...] [<reason>]

        Tells the bot to part the list of channels you give it.  If <reason>
        is specified, use it as the part message.
        """
        if not args:
            args = [msg.args[0]]
        channels = []
        reason = ''
        for (i, arg) in enumerate(args):
            if irc.isChannel(arg):
                channels.append(args[i])
                args[i] = None
            else:
                break
        args = filter(None, args)
        if not channels:
            channels.append(msg.args[0])
        if args:
            reason = ' '.join(args)
        for chan in channels:
            if chan not in irc.state.channels:
                irc.error('I\'m not currently in %s.' % chan)
                return
        for chan in channels:
            try:
                conf.supybot.channels.removeChannel(chan)
            except KeyError:
                pass # It might be in the network thingy.
            try:
                networkGroup = conf.supybot.networks.get(irc.network)
                networkGroup.channels.removeChannel(chan)
            except KeyError:
                pass # It might be in the non-network thingy.
        irc.queueMsg(ircmsgs.parts(channels, reason or msg.nick))
        inAtLeastOneChannel = False
        for chan in channels:
            if msg.nick in irc.state.channels[chan].users:
                inAtLeastOneChannel = True
        if not inAtLeastOneChannel:
            irc.replySuccess()
        else:
            irc.noReply()

    def addcapability(self, irc, msg, args, user, capability):
        """<name|hostmask> <capability>

        Gives the user specified by <name> (or the user to whom <hostmask>
        currently maps) the specified capability <capability>
        """
        # Ok, the concepts that are important with capabilities:
        #
        ### 1) No user should be able to elevate his privilege to owner.
        ### 2) Admin users are *not* superior to #channel.ops, and don't
        ###    have God-like powers over channels.
        ### 3) We assume that Admin users are two things: non-malicious and
        ###    and greedy for power.  So they'll try to elevate their privilege
        ###    to owner, but they won't try to crash the bot for no reason.

        # Thus, the owner capability can't be given in the bot.  Admin users
        # can only give out capabilities they have themselves (which will
        # depend on supybot.capabilities and its child default) but generally
        # means they can't mess with channel capabilities.
        if ircutils.strEqual(capability, 'owner'):
            irc.error('The "owner" capability can\'t be added in the bot.  '
                      'Use the supybot-adduser program (or edit the '
                      'users.conf file yourself) to add an owner capability.')
            return
        if ircdb.isAntiCapability(capability) or \
           ircdb.checkCapability(msg.prefix, capability):
            user.addCapability(capability)
            ircdb.users.setUser(user)
            irc.replySuccess()
        else:
            irc.error('You can\'t add capabilities you don\'t have.')
    addcapability = wrap(addcapability, ['otherUser', 'lowered'])

    def removecapability(self, irc, msg, args, user, capability):
        """<name|hostmask> <capability>

        Takes from the user specified by <name> (or the user to whom
        <hostmask> currently maps) the specified capability <capability>
        """
        if ircdb.checkCapability(msg.prefix, capability) or \
           ircdb.isAntiCapability(capability):
            try:
                user.removeCapability(capability)
                ircdb.users.setUser(user)
                irc.replySuccess()
            except KeyError:
                irc.error('That user doesn\'t have that capability.')
        else:
            s = 'You can\'t remove capabilities you don\'t have.'
            irc.error(s)
    removecapability = wrap(removecapability, ['otherUser','lowered'])

    def ignore(self, irc, msg, args, hostmask, expires):
        """<hostmask|nick> [<expires>]

        Ignores <hostmask> or, if a nick is given, ignores whatever hostmask
        that nick is currently using.  <expires> is a "seconds from now" value
        that determines when the ignore will expire; if, for instance, you wish
        for the ignore to expire in an hour, you could give an <expires> of
        3600.  If no <expires> is given, the ignore will never automatically
        expire.
        """
        if expires:
            expires += time.time()
        ircdb.ignores.add(hostmask, expires)
        irc.replySuccess()
    ignore = wrap(ignore, ['hostmask', additional('int', 0)])

    def unignore(self, irc, msg, args, hostmask):
        """<hostmask|nick>

        Ignores <hostmask> or, if a nick is given, ignores whatever hostmask
        that nick is currently using.
        """
        try:
            ircdb.ignores.remove(hostmask)
            irc.replySuccess()
        except KeyError:
            irc.error('%s wasn\'t in the ignores database.' % hostmask)
    unignore = wrap(unignore, ['hostmask'])

    def ignores(self, irc, msg, args):
        """takes no arguments

        Returns the hostmasks currently being globally ignored.
        """
        # XXX Add the expirations.
        if ircdb.ignores.hostmasks:
            irc.reply(utils.commaAndify(imap(repr, ircdb.ignores.hostmasks)))
        else:
            irc.reply('I\'m not currently globally ignoring anyone.')
    ignores = wrap(ignores)


Class = Admin

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
