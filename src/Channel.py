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
Basic channel management commands.  Many of these commands require their caller
to have the <channel>.op capability.  This plugin is loaded by default.
"""

__revision__ = "$Id$"

import fix

import time
import getopt
from itertools import imap

import conf
import ircdb
import utils
import ircmsgs
import schedule
import ircutils
import privmsgs
import callbacks

class Channel(callbacks.Privmsg):
    def op(self, irc, msg, args, channel):
        """[<channel>]

        If you have the #channel.op capability, this will give you ops.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.op(channel, msg.nick))
        else:
            irc.error(msg, 'How can I op you?  I\'m not opped!')
    op = privmsgs.checkChannelCapability(op, 'op')

    def halfop(self, irc, msg, args, channel):
        """[<channel>]

        If you have the #channel.halfop capability, this will give you halfops.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.halfop(channel, msg.nick))
        else:
            irc.error(msg, 'How can I halfop you?  I\'m not opped!')
    halfop = privmsgs.checkChannelCapability(halfop, 'halfop')

    def voice(self, irc, msg, args, channel):
        """[<channel>]

        If you have the #channel.voice capability, this will give you voice.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.voice(channel, msg.nick))
        else:
            irc.error(msg, 'How can I voice you?  I\'m not opped!')
    voice = privmsgs.checkChannelCapability(voice, 'voice')

    def deop(self, irc, msg, args, channel):
        """[<channel>] [<nick> ...]

        If you have the #channel.op capability, this will remove operator
        privileges from all the nicks given.  If no nicks are given, removes
        operator privileges from the person sending the message.
        """
        if not args:
            args.append(msg.nick)
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.deops(channel, args))
        else:
            irc.error(msg, 'How can I deop someone?  I\'m not opped!')
    deop = privmsgs.checkChannelCapability(deop, 'op')
    
    def dehalfop(self, irc, msg, args, channel):
        """[<channel>] [<nick> ...]

        If you have the #channel.op capability, this will remove half-operator
        privileges from all the nicks given.  If no nicks are given, removes
        half-operator privileges from the person sending the message.
        """
        if not args:
            args.append(msg.nick)
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.dehalfops(channel, args))
        else:
            irc.error(msg, 'How can I dehalfop someone?  I\'m not opped!')
    dehalfop = privmsgs.checkChannelCapability(dehalfop, 'op')
    
    def devoice(self, irc, msg, args, channel):
        """[<channel>] [<nick> ...]

        If you have the #channel.op capability, this will remove voice from all
        the nicks given.  If no nicks are given, removes voice from the person
        sending the message.
        """
        if not args:
            args.append(msg.nick)
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.devoices(channel, args))
        else:
            irc.error(msg, 'How can I devoice someone?  I\'m not opped!')
    devoice = privmsgs.checkChannelCapability(devoice, 'op')
    
    def cycle(self, irc, msg, args, channel):
        """[<channel>] [<key>]

        If you have the #channel.op capability, this will cause the bot to
        "cycle", or PART and then JOIN the channel. If <key> is given, join
        the channel using that key. <channel> is only necessary if the message
        isn't sent in the channel itself.
        """
        key = privmsgs.getArgs(args, required=0, optional=1)
        if not key:
            key = None
        irc.queueMsg(ircmsgs.part(channel))
        irc.queueMsg(ircmsgs.join(channel, key))
    cycle = privmsgs.checkChannelCapability(cycle, 'op')

    def kick(self, irc, msg, args, channel):
        """[<channel>] <nick> [<reason>]

        Kicks <nick> from <channel> for <reason>.  If <reason> isn't given,
        uses the nick of the person making the command as the reason.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        if irc.nick in irc.state.channels[channel].ops:
            (nick, reason) = privmsgs.getArgs(args, optional=1)
            if not reason:
                reason = msg.nick
            irc.queueMsg(ircmsgs.kick(channel, nick, reason))
        else:
            irc.error(msg, 'How can I kick someone?  I\'m not opped!')
    kick = privmsgs.checkChannelCapability(kick, 'op')

    def kban(self, irc, msg, args):
        """[<channel>] <nick> [<seconds>] [--{exact,nick,user,host}]

        If you have the #channel.op capability, this will kickban <nick> for
        as many seconds as you specify, or else (if you specify 0 seconds or
        don't specify a number of seconds) it will ban the person indefinitely.
        --exact bans only the exact hostmask; --nick bans just the nick;
        --user bans just the user, and --host bans just the host.  You can
        combine these options as you choose.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        channel = privmsgs.getChannel(msg, args)
        (optlist, rest) = getopt.getopt(args, '', ['exact', 'nick',
                                                   'user', 'host'])
        (bannedNick, length) = privmsgs.getArgs(rest, optional=1)
        # Check that they're not trying to make us kickban ourself.
        if not ircutils.isNick(bannedNick):
            self.log.warning('%r tried to kban a non nick: %r',
                             msg.prefix, bannedNick)
            raise callbacks.ArgumentError
        elif bannedNick == irc.nick:
            self.log.warning('%r tried to make me kban myself.', msg.prefix)
            irc.error(msg, 'I cowardly refuse to kickban myself.')
            return
        try:
            length = int(length or 0)
        except ValueError:
            irc.error(msg, 'Ban length must be a valid integer.')
            return
        try:
            bannedHostmask = irc.state.nickToHostmask(bannedNick)
        except KeyError:
            irc.error(msg, 'I haven\'t seen %s.' % bannedNick)
            return
        capability = ircdb.makeChannelCapability(channel, 'op')
        if optlist:
            (nick, user, host) = ircutils.splitHostmask(bannedHostmask)
            bnick = '*'
            buser = '*'
            bhost = '*'
            for (option, _) in optlist:
                if option == '--nick':
                    bnick = nick
                elif option == '--user':
                    buser = user
                elif option == '--host':
                    bhost = host
                elif option == '--exact':
                    (bnick, buser, bhost) = \
                                   ircutils.splitHostmask(bannedHostmask)
            banmask = ircutils.joinHostmask(bnick, buser, bhost)
        else:
            banmask = ircutils.banmask(bannedHostmask)
        # Check (again) that they're not trying to make us kickban ourself.
        if ircutils.hostmaskPatternEqual(banmask, irc.prefix):
            if ircutils.hostmaskPatternEqual(banmask, irc.prefix):
                self.log.warning('%r tried to make me kban myself.',msg.prefix)
                irc.error(msg, 'I cowardly refuse to ban myself.')
                return
            else:
                banmask = bannedHostmask
        # Check that we have ops.
        if irc.nick not in irc.state.channels[channel].ops:
            irc.error(msg, 'How can I kick or ban someone?  I\'m not opped.')
            return
        # Now, let's actually get to it.  Check to make sure they have
        # #channel.op and the bannee doesn't have #channel.op; or that the
        # bannee and the banner are both the same person.
        def doBan():
            irc.queueMsg(ircmsgs.ban(channel, banmask))
            irc.queueMsg(ircmsgs.kick(channel, bannedNick, msg.nick))
            if length > 0:
                def f():
                    irc.queueMsg(ircmsgs.unban(channel, banmask))
                schedule.addEvent(f, time.time() + length)
        if bannedNick == msg.nick:
            doBan()
        elif ircdb.checkCapability(msg.prefix, capability):
            if ircdb.checkCapability(bannedHostmask, capability):
                self.log.warning('%r tried to ban %r, but both have %s',
                                 msg.prefix, bannedHostmask, capability)
                irc.error(msg, '%s has %s too, you can\'t ban him/her/it.' %
                               bannedNick, capability)
            else:
                doBan()
        else:
            self.log.warning('%r attempted kban without %s',
                             msg.prefix, capability)
            irc.error(msg, conf.replyNoCapability % capability)

    def unban(self, irc, msg, args, channel):
        """[<channel>] <hostmask>

        Unbans <hostmask> on <channel>.  Especially useful for unbanning
        yourself when you get unexpectedly (or accidentally) banned from
        the channel.  <channel> is only necessary if the message isn't sent
        in the channel itself.
        """
        hostmask = privmsgs.getArgs(args)
        if irc.nick in irc.state.channels[channel].ops:
            irc.queueMsg(ircmsgs.unban(channel, hostmask))
        else:
            irc.error(msg, 'How can I unban someone?  I\'m not opped.')
    unban = privmsgs.checkChannelCapability(unban, 'op')

    def lobotomize(self, irc, msg, args, channel):
        """[<channel>]

        If you have the #channel.op capability, this will "lobotomize" the
        bot, making it silent and unanswering to all requests made in the
        channel. <channel> is only necessary if the message isn't sent in the
        channel itself.
        """
        c = ircdb.channels.getChannel(channel)
        c.lobotomized = True
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    lobotomize = privmsgs.checkChannelCapability(lobotomize, 'op')

    def unlobotomize(self, irc, msg, args, channel):
        """[<channel>]

        If you have the #channel.op capability, this will unlobotomize the bot,
        making it respond to requests made in the channel again.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        c = ircdb.channels.getChannel(channel)
        c.lobotomized = False
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    unlobotomize = privmsgs.checkChannelCapability(unlobotomize, 'op')

    def permban(self, irc, msg, args, channel):
        """[<channel>] <nick|hostmask>

        If you have the #channel.op capability, this will effect a permanent
        (persistent) ban on the given <hostmask> (or the current hostmask
        associated with <nick>.  <channel> is only necessary if the message
        isn't sent in the channel itself.
        """
        arg = privmsgs.getArgs(args)
        if ircutils.isNick(arg):
            banmask = ircutils.banmask(irc.state.nickToHostmask(arg))
        elif ircutils.isUserHostmask(arg):
            banmask = arg
        else:
            irc.error(msg, 'That\'s not a valid nick or hostmask.')
            return
        c = ircdb.channels.getChannel(channel)
        c.addBan(banmask)
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    permban = privmsgs.checkChannelCapability(permban, 'op')

    def unpermban(self, irc, msg, args, channel):
        """[<channel>] <hostmask>

        If you have the #channel.op capability, this will remove the permanent
        ban on <hostmask>.  <channel> is only necessary if the message isn't
        sent in the channel itself.
        """
        banmask = privmsgs.getArgs(args)
        c = ircdb.channels.getChannel(channel)
        c.removeBan(banmask)
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    unpermban = privmsgs.checkChannelCapability(unpermban, 'op')

    def ignore(self, irc, msg, args, channel):
        """[<channel>] <nick|hostmask>

        If you have the #channel.op capability, this will set a permanent
        (persistent) ignore on <hostmask> or the hostmask currently associated
        with <nick>. <channel> is only necessary if the message isn't sent in
        the channel itself.
        """
        arg = privmsgs.getArgs(args)
        if ircutils.isNick(arg):
            banmask = ircutils.banmask(irc.state.nickToHostmask(arg))
        elif ircutils.isUserHostmask(arg):
            banmask = arg
        else:
            irc.error(msg, 'That\'s not a valid nick or hostmask.')
            return
        c = ircdb.channels.getChannel(channel)
        c.addIgnore(banmask)
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    ignore = privmsgs.checkChannelCapability(ignore, 'op')

    def unignore(self, irc, msg, args, channel):
        """[<channel>] <hostmask>

        If you have the #channel.op capability, this will remove the permanent
        ignore on <hostmask> in the channel. <channel> is only necessary if the
        message isn't sent in the channel itself.
        """
        banmask = privmsgs.getArgs(args)
        c = ircdb.channels.getChannel(channel)
        c.removeIgnore(banmask)
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    unignore = privmsgs.checkChannelCapability(unignore, 'op')

    def ignores(self, irc, msg, args, channel):
        """[<channel>]

        Lists the hostmasks that the bot is ignoring on the given channel.
        <channel> is only necessary if the message isn't sent in the channel
        itself.
        """
        channelarg = privmsgs.getArgs(args, required=0, optional=1)
        channel = channelarg or channel
        c = ircdb.channels.getChannel(channel)
        if len(c.ignores) == 0:
            s = 'I\'m not currently ignoring any hostmasks in %r' % channel
            irc.reply(msg, s)
        else:
            L = c.ignores[:]
            L.sort()
            irc.reply(msg, utils.commaAndify(imap(repr, L)))
    ignores = privmsgs.checkChannelCapability(ignores, 'op')


    def addcapability(self, irc, msg, args, channel):
        """[<channel>] <name|hostmask> <capability>

        If you have the #channel.op capability, this will give the user
        currently identified as <name> (or the user to whom <hostmask> maps)
        the capability <capability> in the channel. <channel> is only necessary
        if the message isn't sent in the channel itself.
        """
        (name, capability) = privmsgs.getArgs(args, 2)
        capability = ircdb.makeChannelCapability(channel, capability)
        try:
            id = ircdb.users.getUserId(name)
            user = ircdb.users.getUser(id)
            user.addCapability(capability)
            ircdb.users.setUser(id, user)
            irc.reply(msg, conf.replySuccess)
        except KeyError:
            irc.error(msg, conf.replyNoUser)
    addcapability = privmsgs.checkChannelCapability(addcapability,'op')

    def removecapability(self, irc, msg, args, channel):
        """[<channel>] <name|hostmask> <capability>

        If you have the #channel.op capability, this will take from the user
        currently identified as <name> (or the user to whom <hostmask> maps)
        the capability <capability> in the channel. <channel> is only necessary
        if the message isn't sent in the channel itself.
        """
        (name, capability) = privmsgs.getArgs(args, 2)
        capability = ircdb.makeChannelCapability(channel, capability)
        try:
            id = ircdb.users.getUserId(name)
            user = ircdb.users.getUser(id)
            user.removeCapability(capability)
            ircdb.users.setUser(id, user)
            irc.reply(msg, conf.replySuccess)
        except KeyError:
            irc.error(msg, conf.replyNoUser)
    removecapability = privmsgs.checkChannelCapability(removecapability, 'op')

    def setdefaultcapability(self, irc, msg, args, channel):
        """[<channel>] <default response to unknown capabilities> <True|False>

        If you have the #channel.op capability, this will set the default
        response to non-power-related (that is, not {op, halfop, voice}
        capabilities to be the value you give. <channel> is only necessary if
        the message isn't sent in the channel itself.
        """
        v = privmsgs.getArgs(args)
        v = v.capitalize()
        c = ircdb.channels.getChannel(channel)
        if v == 'True':
            c.setDefaultCapability(True)
        elif v == 'False':
            c.setDefaultCapability(False)
        else:
            s = 'The default value must be either True or False.'
            irc.error(msg, s)
            return
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    setdefaultcapability = \
        privmsgs.checkChannelCapability(setdefaultcapability, 'op')

    def setcapability(self, irc, msg, args, channel):
        """[<channel>] <capability>

        If you have the #channel.op capability, this will add the channel
        capability <capability> for all users in the channel. <channel> is
        only necessary if the message isn't sent in the channel itself.
        """
        capability = privmsgs.getArgs(args)
        c = ircdb.channels.getChannel(channel)
        c.addCapability(capability)
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    setcapability = privmsgs.checkChannelCapability(setcapability, 'op')

    def unsetcapability(self, irc, msg, args, channel):
        """[<chanel>] <capability>

        If you have the #channel.op capability, this will unset the channel
        capability <capability> so each user's specific capability or the
        channel default capability will take precedence. <channel> is only
        necessary if the message isn't sent in the channel itself.
        """
        capability = privmsgs.getArgs(args)
        c = ircdb.channels.getChannel(channel)
        c.removeCapability(capability)
        ircdb.channels.setChannel(channel, c)
        irc.reply(msg, conf.replySuccess)
    unsetcapability = privmsgs.checkChannelCapability(unsetcapability, 'op')

    def capabilities(self, irc, msg, args):
        """[<channel>]

        Returns the capabilities present on the <channel>. <channel> is only
        necessary if the message isn't sent in the channel itself.
        """
        channel = privmsgs.getChannel(msg, args)
        c = ircdb.channels.getChannel(channel)
        L = list(c.capabilities)
        L.sort()
        irc.reply(msg, '[%s]' % ', '.join(L))

    def lobotomies(self, irc, msg, args):
        """takes no arguments

        Returns the channels in which this bot is lobotomized.
        """
        L = []
        for (channel, c) in ircdb.channels.iteritems():
            if c.lobotomized:
                L.append(channel)
        if L:
            L.sort()
            s = 'I\'m currently lobotomized in %s.' % utils.commaAndify(L)
            irc.reply(msg, s)
        else:
            irc.reply(msg, 'I\'m not currently lobotomized in any channels.')
                        

Class = Channel

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
