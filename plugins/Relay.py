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
"""

__revision__ = "$Id$"

import plugins

import re
import sys
import copy
import time
from itertools import imap, ifilter

import conf
import utils
import world
import irclib
import drivers
import ircmsgs
import ircutils
import privmsgs
import registry
import callbacks

def configure(advanced):
    from questions import output, expect, anything, something, yn
    conf.registerPlugin('Relay', True)
    if yn('Would you like to relay between any channels?'):
        channels = anything('What channels?  Separated them by spaces.')
        conf.supybot.plugins.Relay.channels.set(channels)
    if yn('Would you like to use color to distinguish between nicks?'):
        conf.supybot.plugins.Relay.color.setValue(True)
    output("""Right now there's no way to configure the actual connection to
    the server.  What you'll need to do when the bot finishes starting up is
    use the 'start' command followed by the 'connect' command.  Use the 'help'
    command to see how these two commands should be used.""")

conf.registerPlugin('Relay')
conf.registerChannelValue(conf.supybot.plugins.Relay, 'color',
    registry.Boolean(False, """Determines whether the bot will color relayed
    PRIVMSGs so as to make the messages easier to read."""))
conf.registerChannelValue(conf.supybot.plugins.Relay, 'topicSync',
    registry.Boolean(True, """Determines whether the bot will synchronize
    topics between networks in the channels it relays."""))
conf.registerGlobalValue(conf.supybot.plugins.Relay, 'channels',
    conf.SpaceSeparatedSetOfChannels([], """Determines which channels the bot
    will relay in."""))

ircs = ircutils.IrcDict()
lastmsg = {} # Not IrcDict.  Doesn't map strings.
ircstates = {} # Not IrcDict.  Doesn't map strings.
abbreviations = {} # Not IrcDict.  Doesn't map strings.
originalIrc = None

def reload(x=None):
    global ircs, ircstates, lastmsg, abbreviations, originalIrc
    if x is None:
        return (ircs, ircstates, lastmsg, abbreviations, originalIrc)
    else:
        (ircs, ircstates, lastmsg, abbreviations, originalIrc) = x

class Relay(callbacks.Privmsg):
    noIgnore = True
    priority = sys.maxint
    def __init__(self):
        callbacks.Privmsg.__init__(self)
        self.ircs = ircs
        self.started = False
        self.ircstates = ircstates
        self.lastmsg = lastmsg
        self._whois = {}
        self.abbreviations = abbreviations

    def __call__(self, irc, msg):
        if self.started:
            try:
                irc = self._getRealIrc(irc)
                self.ircstates[irc].addMsg(irc, self.lastmsg[irc])
            finally:
                self.lastmsg[irc] = msg
        callbacks.Privmsg.__call__(self, irc, msg)

    def do376(self, irc, msg):
        L = []
        for channel in self.registryValue('channels'):
            if channel not in irc.state.channels:
                L.append(channel)
        if L:
            irc.queueMsg(ircmsgs.joins(L))
    do377 = do422 = do376

    def _getRealIrc(self, irc):
        if isinstance(irc, irclib.Irc):
            return irc
        else:
            return irc.getRealIrc()

    def start(self, irc, msg, args):
        """<network abbreviation for current server>

        This command is necessary to start the Relay plugin; the
        <network abbreviation> is the abbreviation that the network the
        bot is currently connected to should be shown as to other networks.
        For instance, if the network abbreviation is 'oftc', then when
        relaying messages from that network to other networks, the users
        will show up as 'user@oftc'.
        """
        global originalIrc
        realIrc = self._getRealIrc(irc)
        originalIrc = realIrc
        abbreviation = privmsgs.getArgs(args)
        self.ircs[abbreviation] = realIrc
        self.abbreviations[realIrc] = abbreviation
        self.ircstates[realIrc] = copy.copy(realIrc.state)
        self.lastmsg[realIrc] = ircmsgs.ping('this is just a fake message')
        self.started = True
        irc.replySuccess()
    start = privmsgs.checkCapability(start, 'owner')

    def connect(self, irc, msg, args):
        """<network abbreviation> <domain:port> (port defaults to 6667)

        Connects to another network at <domain:port>.  The network
        abbreviation <network abbreviation> is used when relaying messages from
        that network to other networks.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        abbreviation, server = privmsgs.getArgs(args, required=2)
        realIrc = self._getRealIrc(irc)
        if ':' in server:
            (server, port) = server.split(':')
            port = int(port)
        else:
            port = 6667
        newIrc = irclib.Irc(irc.nick, callbacks=realIrc.callbacks)
        newIrc.state.history = realIrc.state.history
        driver = drivers.newDriver((server, port), newIrc)
        newIrc.driver = driver
        self.ircs[abbreviation] = newIrc
        self.abbreviations[newIrc] = abbreviation
        self.ircstates[newIrc] = irclib.IrcState()
        self.lastmsg[newIrc] = ircmsgs.ping('this is just a fake message')
        irc.replySuccess()
    connect = privmsgs.checkCapability(connect, 'owner')

    def reconnect(self, irc, msg, args):
        """<network>

        Reconnects the bot to <network> when it has become disconnected.
        """
        network = privmsgs.getArgs(args)
        try:
            toReconnect = self.ircs[network]
        except KeyError:
            irc.error('I\'m not connected to %s.' % network)
            return
        toReeconnect.driver.reconnect()
        irc.replySuccess()
    reconnect = privmsgs.checkCapability(reconnect, 'owner')

    def disconnect(self, irc, msg, args):
        """<network>

        Disconnects and ceases to relay to and from the network represented by
        the network abbreviation <network>.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        network = privmsgs.getArgs(args)
        otherIrc = self.ircs[network]
        otherIrc.driver.die()
        world.ircs.remove(otherIrc)
        del self.ircs[network]
        del self.abbreviations[otherIrc]
        irc.replySuccess()
    disconnect = privmsgs.checkCapability(disconnect, 'owner')

    def join(self, irc, msg, args):
        """<channel>

        Starts relaying between the channel <channel> on all networks.  If on a
        network the bot isn't in <channel>, he'll join.  This commands is
        required even if the bot is in the channel on both networks; he won't
        relay between those channels unless he's told to oin both
        channels.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        channel = privmsgs.getArgs(args)
        if not ircutils.isChannel(channel):
            irc.error('%r is not a valid channel.' % channel)
            return
        self.registryValue('channels').add(ircutils.toLower(channel))
        for otherIrc in self.ircs.itervalues():
            if channel not in otherIrc.state.channels:
                otherIrc.queueMsg(ircmsgs.join(channel))
        irc.replySuccess()
    join = privmsgs.checkCapability(join, 'owner')

    def part(self, irc, msg, args):
        """<channel>

        Ceases relaying between the channel <channel> on all networks.  The bot
        will part from the channel on all networks in which it is on the
        channel.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        channel = privmsgs.getArgs(args)
        if not ircutils.isChannel(channel):
            irc.error('%r is not a valid channel.' % channel)
            return
        self.registryValue('channels').remove(ircutils.toLower(channel))
        for otherIrc in self.ircs.itervalues():
            if channel in otherIrc.state.channels:
                otherIrc.queueMsg(ircmsgs.part(channel))
        irc.replySuccess()
    part = privmsgs.checkCapability(part, 'owner')

    def command(self, irc, msg, args):
        """<network> <command> [<arg> ...]

        Gives the bot <command> (with its associated <arg>s) on <network>.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        if len(args) < 2:
            raise callbacks.ArgumentError
        network = args.pop(0)
        try:
            otherIrc = self.ircs[network]
        except KeyError:
            irc.error('I\'m not currently on the network %r.' % network)
            return
        Owner = irc.getCallback('Owner')
        Owner.disambiguate(irc, args)
        self.Proxy(otherIrc, msg, args)
    command = privmsgs.checkCapability(command, 'admin')
        
    def say(self, irc, msg, args):
        """<network> [<channel>] <text>

        Says <text> on <channel> (using the current channel if unspecified)
        on <network>.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        if not args:
            raise callbacks.ArgumentError
        network = args.pop(0)
        channel = privmsgs.getChannel(msg, args)
        text = privmsgs.getArgs(args)
        if network not in self.ircs:
            irc.error('I\'m not currently on %s.' % network)
            return
        if channel not in self.registryValue('channels'):
            irc.error('I\'m not currently relaying to %s.' % channel)
            return
        self.ircs[network].queueMsg(ircmsgs.privmsg(channel, text))
    say = privmsgs.checkCapability(say, 'admin')

    def nicks(self, irc, msg, args):
        """[<channel>] (only if not sent in the channel itself.)

        The <channel> argument is only necessary if the message isn't sent on
        the channel itself.  Returns the nicks of the people in the channel on
        the various networks the bot is connected to.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        realIrc = self._getRealIrc(irc)
        channel = privmsgs.getChannel(msg, args)
        if channel not in self.registryValue('channels'):
            irc.error('I\'m not relaying %s.' % channel)
            return
        users = []
        for (abbreviation, otherIrc) in self.ircs.iteritems():
            ops = []
            halfops = []
            voices = []
            usersS = []
            if abbreviation != self.abbreviations[realIrc]:
                try:
                    Channel = otherIrc.state.channels[channel]
                except KeyError:
                    s = 'Somehow I\'m not in %s on %s.'% (channel,abbreviation)
                    irc.error(s)
                    return
                numUsers = 0
                for s in Channel.users:
                    s = s.strip()
                    if not s:
                        continue
                    numUsers += 1
                    if s in Channel.ops:
                        ops.append('@%s' % s)
                    elif s in Channel.halfops:
                        halfops.append('%%%s' % s)
                    elif s in Channel.voices:
                        voices.append('+%s' % s)
                    else:
                        usersS.append(s)
                utils.sortBy(ircutils.toLower, ops)
                utils.sortBy(ircutils.toLower, voices)
                utils.sortBy(ircutils.toLower, halfops)
                utils.sortBy(ircutils.toLower, usersS)
                usersS = ', '.join(ifilter(None, imap(', '.join,
                                  (ops,halfops,voices,usersS))))
                users.append('%s (%s): %s' % 
                             (ircutils.bold(abbreviation), numUsers, usersS))
        users.sort()
        irc.reply('; '.join(users))

    def whois(self, irc, msg, args):
        """<nick>@<network>

        Returns the WHOIS response <network> gives for <nick>.
        """
        if not self.started:
            irc.error('You must use the start command first.')
            return
        nickAtNetwork = privmsgs.getArgs(args)
        realIrc = self._getRealIrc(irc)
        try:
            (nick, network) = nickAtNetwork.split('@', 1)
            if not ircutils.isNick(nick):
                irc.error('%s is not an IRC nick.' % nick)
                return
            nick = ircutils.toLower(nick)
        except ValueError:
            if len(self.abbreviations) == 2:
                # If there are only two networks being relayed, we can safely
                # pick the *other* one.
                nick = ircutils.toLower(nickAtNetwork)
                for (keyIrc, net) in self.abbreviations.iteritems():
                    if keyIrc != realIrc:
                        network = net
            else:
                raise callbacks.ArgumentError
        if network not in self.ircs:
            irc.error('I\'m not on that network.')
            return
        otherIrc = self.ircs[network]
        otherIrc.queueMsg(ircmsgs.whois(nick, nick))
        self._whois[(otherIrc, nick)] = (irc, msg, {})

    def do311(self, irc, msg):
        irc = self._getRealIrc(irc)
        nick = ircutils.toLower(msg.args[1])
        if (irc, nick) not in self._whois:
            return
        else:
            self._whois[(irc, nick)][-1][msg.command] = msg

    do301 = do311
    do312 = do311
    do317 = do311
    do319 = do311
    do320 = do311

    def do318(self, irc, msg):
        irc = self._getRealIrc(irc)
        nick = msg.args[1]
        loweredNick = ircutils.toLower(nick)
        if (irc, loweredNick) not in self._whois:
            return
        (replyIrc, replyMsg, d) = self._whois[(irc, loweredNick)]
        hostmask = '@'.join(d['311'].args[2:4])
        user = d['311'].args[-1]
        if '319' in d:
            channels = d['319'].args[-1].split()
            ops = []
            voices = []
            normal = []
            halfops = []
            for channel in channels:
                if channel.startswith('@'):
                    ops.append(channel[1:])
                elif channel.startswith('%'):
                    halfops.append(channel[1:])
                elif channel.startswith('+'):
                    voices.append(channel[1:])
                else:
                    normal.append(channel)
            L = []
            if ops:
                L.append('is an op on %s' % utils.commaAndify(ops))
            if halfops:
                L.append('is a halfop on %s' % utils.commaAndify(halfops))
            if voices:
                L.append('is voiced on %s' % utils.commaAndify(voices))
            if L:
                L.append('is also on %s' % utils.commaAndify(normal))
            else:
                L.append('is on %s' % utils.commaAndify(normal))
        else:
            L = ['isn\'t on any non-secret channels']
        channels = utils.commaAndify(L)
        if '317' in d:
            idle = utils.timeElapsed(d['317'].args[2])
            signon = time.strftime(conf.supybot.humanTimestampFormat(),
                                   time.localtime(float(d['317'].args[3])))
        else:
            idle = '<unknown>'
            signon = '<unknown>'
        if '312' in d:
            server = d['312'].args[2]
        else:
            server = '<unknown>'
        if '301' in d:
            away = '  %s is away: %s.' % (nick, d['301'].args[2])
        else:
            away = ''
        if '320' in d:
            if d['320'].args[2]:
                identify = ' identified'
            else:
                identify = ''
        else:
            identify = ''
        s = '%s (%s) has been%s on server %s since %s (idle for %s) and ' \
            '%s.%s' % (user, hostmask, identify, server, signon, idle,
                       channels, away)
        replyIrc.reply(s)
        del self._whois[(irc, loweredNick)]

    def do402(self, irc, msg):
        irc = self._getRealIrc(irc)
        nick = msg.args[1]
        loweredNick = ircutils.toLower(nick)
        if (irc, loweredNick) not in self._whois:
            return
        (replyIrc, replyMsg, d) = self._whois[(irc, loweredNick)]
        del self._whois[(irc, loweredNick)]
        s = 'There is no %s on %s.' % (nick, self.abbreviations[irc])
        replyIrc.reply(s)

    do401 = do402

    def _formatPrivmsg(self, nick, network, msg):
        # colorize nicks
        color = self.registryValue('color', msg.args[0])
        if color:
            nick = ircutils.mircColor(nick, *ircutils.canonicalColor(nick))
            colors = ircutils.canonicalColor(nick, shift=4)
        if ircmsgs.isAction(msg):
            if color:
                t = ircutils.mircColor('*', *colors)
            else:
                t = '*'
            s = '%s %s@%s %s' % (t, nick, network, ircmsgs.unAction(msg))
        else:
            if color:
                lt = ircutils.mircColor('<', *colors)
                gt = ircutils.mircColor('>', *colors)
            else:
                lt = '<'
                gt = '>'
            s = '%s%s@%s%s %s' % (lt, nick, network, gt, msg.args[1])
        return s

    def _sendToOthers(self, irc, msg):
        assert msg.command == 'PRIVMSG' or msg.command == 'TOPIC'
        for otherIrc in self.ircs.itervalues():
            if otherIrc != irc:
                if msg.args[0] in otherIrc.state.channels:
                    otherIrc.queueMsg(msg)

    def doPrivmsg(self, irc, msg):
        if self.started and ircutils.isChannel(msg.args[0]):
            irc = self._getRealIrc(irc)
            channel = msg.args[0]
            if channel not in self.registryValue('channels'):
                return
            if ircutils.isCtcp(msg) and \
               not 'AWAY' in msg.args[1] and \
               not 'ACTION' in msg.args[1]:
                return
            abbreviation = self.abbreviations[irc]
            s = self._formatPrivmsg(msg.nick, abbreviation, msg)
            m = ircmsgs.privmsg(channel, s)
            self._sendToOthers(irc, m)

    def doJoin(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            channel = msg.args[0]
            if channel not in self.registryValue('channels'):
                return
            abbreviation = self.abbreviations[irc]
            s = '%s (%s) has joined on %s' % (msg.nick,msg.prefix,abbreviation)
            m = ircmsgs.privmsg(channel, s)
            self._sendToOthers(irc, m)

    def doPart(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            channel = msg.args[0]
            if channel not in self.registryValue('channels'):
                return
            abbreviation = self.abbreviations[irc]
            s = '%s (%s) has left on %s' % (msg.nick, msg.prefix, abbreviation)
            m = ircmsgs.privmsg(channel, s)
            self._sendToOthers(irc, m)

    def doMode(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            channel = msg.args[0]
            if channel not in self.registryValue('channels'):
                return
            abbreviation = self.abbreviations[irc]
            s = 'mode change by %s on %s: %s' % \
                (msg.nick, abbreviation, ' '.join(msg.args[1:]))
            m = ircmsgs.privmsg(channel, s)
            self._sendToOthers(irc, m)

    def doKick(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            channel = msg.args[0]
            if channel not in self.registryValue('channels'):
                return
            abbrev = self.abbreviations[irc]
            if len(msg.args) == 3:
                s = '%s was kicked by %s on %s (%s)' % \
                    (msg.args[1], msg.nick, abbrev, msg.args[2])
            else:
                s = '%s was kicked by %s on %s' % \
                    (msg.args[1], msg.nick, abbrev)
            m = ircmsgs.privmsg(channel, s)
            self._sendToOthers(irc, m)

    def doNick(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            newNick = msg.args[0]
            network = self.abbreviations[irc]
            s = 'nick change by %s to %s on %s' % (msg.nick, newNick, network)
            for channel in self.registryValue('channels'):
                if newNick in irc.state.channels[channel].users:
                    m = ircmsgs.privmsg(channel, s)
                    self._sendToOthers(irc, m)

    def doTopic(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            if msg.nick == irc.nick:
                return
            (channel, newTopic) = msg.args
            network = self.abbreviations[irc]
            if self.registryValue('topicSync', channel):
                m = ircmsgs.topic(channel, newTopic)
            else:
                s = 'topic change by %s on %s: %s' %(msg.nick,network,newTopic)
                m = ircmsgs.privmsg(channel, s)
            self._sendToOthers(irc, m)

    def doQuit(self, irc, msg):
        if self.started:
            irc = self._getRealIrc(irc)
            network = self.abbreviations[irc]
            if msg.args:
                s = '%s has quit %s (%s)' % (msg.nick, network, msg.args[0])
            else:
                s = '%s has quit %s.' % (msg.nick, network)
            for channel in self.registryValue('channels'):
                if msg.nick in self.ircstates[irc].channels[channel].users:
                    m = ircmsgs.privmsg(channel, s)
                    self._sendToOthers(irc, m)

    def outFilter(self, irc, msg):
        if not self.started:
            return msg
        irc = self._getRealIrc(irc)
        if msg.command == 'PRIVMSG':
            abbreviations = self.abbreviations.values()
            rPrivmsg = re.compile(r'<[^@]+@(?:%s)>' % '|'.join(abbreviations))
            rAction = re.compile(r'\* [^/]+@(?:%s) ' % '|'.join(abbreviations))
            text = ircutils.unColor(msg.args[1])
            if not (rPrivmsg.match(text) or \
                    rAction.match(text) or \
                    'has left on ' in text or \
                    'has joined on ' in text or \
                    'has quit' in text or \
                    'was kicked by' in text or \
                    text.startswith('mode change') or \
                    text.startswith('nick change') or \
                    text.startswith('topic change')):
                channel = msg.args[0]
                if channel in self.registryValue('channels'):
                    abbreviation = self.abbreviations[irc]
                    s = self._formatPrivmsg(irc.nick, abbreviation, msg)
                    for otherIrc in self.ircs.itervalues():
                        if otherIrc != irc:
                            if channel in otherIrc.state.channels:
                                otherIrc.queueMsg(ircmsgs.privmsg(channel, s))
        elif msg.command == 'TOPIC' and len(msg.args) > 1 and \
             self.registryValue('topicSync', msg.args[0]):
            (channel, topic) = msg.args
            if channel in self.registryValue('channels'):
                for otherIrc in self.ircs.itervalues():
                    if otherIrc != irc:
                        try:
                            if otherIrc.state.getTopic(channel) != topic:
                                otherIrc.queueMsg(ircmsgs.topic(channel,topic))
                        except KeyError:
                            self.log.warning('Odd, not on %s on %s -- '
                                             'Can\'t synchronize topics.',
                                             channel, otherIrc.server)

        return msg

Class = Relay

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
