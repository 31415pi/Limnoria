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
Logs each channel to its own individual logfile.
"""

import supybot

__revision__ = "$Id$"
__author__ = supybot.authors.jemfinch

import supybot.plugins as plugins

import time
from cStringIO import StringIO

import os
import supybot.conf as conf
import supybot.world as world
import supybot.irclib as irclib
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.registry as registry
import supybot.callbacks as callbacks

conf.registerPlugin('ChannelLogger')
conf.registerGlobalValue(conf.supybot.plugins.ChannelLogger,
    'flushImmediately', registry.Boolean(False, """Determines whether channel
    logfiles will be flushed anytime they're written to, rather than being
    buffered by the operating system."""))
conf.registerChannelValue(conf.supybot.plugins.ChannelLogger,
    'stripFormatting', registry.Boolean(True, """Determines whether
    formatting characters (such as bolding, color, etc.) are removed when
    writing the logs to disk."""))
conf.registerChannelValue(conf.supybot.plugins.ChannelLogger, 'timestamp',
    registry.Boolean(True, """Determines whether the logs for this channel are
    timestamped with the timestamp in supybot.log.timestampFormat."""))
conf.registerChannelValue(conf.supybot.plugins.ChannelLogger, 'noLogPrefix',
    registry.String('[nolog]', """Determines what string a message should be
    prefixed with in order not to be logged.  If you don't want any such
    prefix, just set it to the empty string."""))
conf.registerChannelValue(conf.supybot.plugins.ChannelLogger, 'rotateLogs',
    registry.Boolean(False, """Determines whether the bot will automatically
    rotate the logs for this channel.  The bot will rotate logs when the
    timestamp for the log changes.  The timestamp is set according to
    the 'filenameTimestamp' configuration variable."""))
conf.registerChannelValue(conf.supybot.plugins.ChannelLogger,
    'filenameTimestamp', registry.String('%d-%a-%Y', """Determines how to
    represent the timestamp used for the filename in rotated logs.  When this
    timestamp changes, the old logfiles will be closed and a new one started.
    The format characters for the timestamp are in the time.strftime docs at
    python.org.  In order for your logs to be rotated, you'll also have to
    enable supybot.plugins.ChannelLogger.rotateLogs."""))

conf.registerGlobalValue(conf.supybot.plugins.ChannelLogger, 'directories',
    registry.Boolean(True, """Determines whether the bot will partition its
    channel logs into separate directories based on different criteria."""))
conf.registerGlobalValue(conf.supybot.plugins.ChannelLogger.directories,
    'network', registry.Boolean(True, """Determines whether the bot will use
    a network directory if using directories."""))
conf.registerGlobalValue(conf.supybot.plugins.ChannelLogger.directories,
    'channel', registry.Boolean(True, """Determines whether the bot will use
    a channel directory if using directories."""))
t = conf.registerGlobalValue(conf.supybot.plugins.ChannelLogger.directories,
    'timestamp', registry.Boolean(False, """Determines whether the bot will use
    a timestamp (determined by
    supybot.plugins.ChannelLogger.directories.timestamp.format) if using
    directories."""))
conf.registerGlobalValue(t, 'format', registry.String('%B', """Determines what
    timestamp format will be used in the directory stucture for channel logs if
    supybot.plugins.ChannelLogger.directories.timestamp is True."""))

class FakeLog(object):
    def flush(self):
        return
    def close(self):
        return
    def write(self, s):
        return

class ChannelLogger(callbacks.Privmsg):
    noIgnore = True
    def __init__(self):
        self.__parent = super(ChannelLogger, self)
        self.__parent.__init__()
        self.lastMsg = None
        self.laststate = None
        self.logs = {}
        world.flushers.append(self.flush)

    def die(self):
        for log in self._logs():
            log.close()
        world.flushers = [x for x in world.flushers
                          if hasattr(x, 'im_class') and
                          x.im_class is not self.__class__]

    def __call__(self, irc, msg):
        try:
            if msg.args and irc.isChannel(msg.args[0]):
                super(self.__class__, self).__call__(irc, msg)
            if self.lastMsg:
                self.laststate.addMsg(irc, self.lastMsg)
            else:
                self.laststate = irc.state.copy()
        finally:
            # We must make sure this always gets updated.
            self.lastMsg = msg

    def reset(self):
        for log in self._logs():
            log.close()
        self.logs.clear()

    def _logs(self):
        for logs in self.logs.itervalues():
            for log in logs.itervalues():
                yield log

    def flush(self):
        self.checkLogNames()
        for log in self._logs():
            try:
                log.flush()
            except ValueError, e:
                if e.args[0] != 'I/O operation on a closed file':
                    self.log.exception('Odd exception:')

    def logNameTimestamp(self, channel):
        format = self.registryValue('filenameTimestamp', channel)
        return time.strftime(format)

    def getLogName(self, channel):
        if self.registryValue('rotateLogs', channel):
            return '%s.%s.log' % (channel, self.logNameTimestamp(channel))
        else:
            return '%s.log' % channel

    def getLogDir(self, irc, channel):
        logDir = conf.supybot.directories.log()
        logDir = os.path.join(logDir, self.name())
        if self.registryValue('directories'):
            if self.registryValue('directories.network'):
                logDir = os.path.join(logDir,  irc.network)
            if self.registryValue('directories.channel'):
                logDir = os.path.join(logDir, channel)
            if self.registryValue('directories.timestamp'):
                format = self.registryValue('directories.timestamp.format')
                timeDir =time.strftime(format)
                logDir = os.path.join(logDir, timeDir)
        if not os.path.exists(logDir):
            os.makedirs(logDir)
        return logDir

    def checkLogNames(self):
        for (irc, logs) in self.logs.items():
            for (channel, log) in logs.items():
                if self.registryValue('rotateLogs', channel):
                    name = self.getLogName(channel)
                    if name != log.name:
                        log.close()
                        del logs[channel]

    def getLog(self, irc, channel):
        self.checkLogNames()
        try:
            logs = self.logs[irc]
        except KeyError:
            logs = ircutils.IrcDict()
            self.logs[irc] = logs
        if channel in logs:
            return logs[channel]
        else:
            try:
                name = self.getLogName(channel)
                logDir = self.getLogDir(irc, channel)
                log = file(os.path.join(logDir, name), 'a')
                logs[channel] = log
                return log
            except IOError:
                self.log.exception('Error opening log:')
                return FakeLog()

    def timestamp(self, log):
        format = conf.supybot.log.timestampFormat()
        if format:
            log.write(time.strftime(format))
            log.write('  ')

    def normalizeChannel(self, irc, channel):
        return ircutils.toLower(channel)

    def doLog(self, irc, channel, s):
        channel = self.normalizeChannel(irc, channel)
        log = self.getLog(irc, channel)
        if self.registryValue('timestamp', channel):
            self.timestamp(log)
        if self.registryValue('stripFormatting', channel):
            s = ircutils.stripFormatting(s)
        log.write(s)
        if self.registryValue('flushImmediately'):
            log.flush()

    def doPrivmsg(self, irc, msg):
        (recipients, text) = msg.args
        for channel in recipients.split(','):
            if ircutils.isChannel(channel):
                noLogPrefix = self.registryValue('noLogPrefix', channel)
                if noLogPrefix and text.startswith(noLogPrefix):
                    text = '-= THIS MESSAGE NOT LOGGED =-'
                nick = msg.nick or irc.nick
                if ircmsgs.isAction(msg):
                    self.doLog(irc, channel,
                               '* %s %s\n' % (nick, ircmsgs.unAction(msg)))
                else:
                    self.doLog(irc, channel, '<%s> %s\n' % (nick, text))

    def doNotice(self, irc, msg):
        (recipients, text) = msg.args
        for channel in recipients.split(','):
            if ircutils.isChannel(channel):
                self.doLog(irc, channel, '-%s- %s\n' % (msg.nick, text))

    def doNick(self, irc, msg):
        oldNick = msg.nick
        newNick = msg.args[0]
        for (channel, c) in irc.state.channels.iteritems():
            if newNick in c.users:
                self.doLog(irc, channel,
                           '*** %s is now known as %s\n' % (oldNick, newNick))
    def doJoin(self, irc, msg):
        for channel in msg.args[0].split(','):
            self.doLog(irc, channel,
                       '*** %s has joined %s\n' %
                       (msg.nick or msg.prefix, channel))

    def doKick(self, irc, msg):
        if len(msg.args) == 3:
            (channel, target, kickmsg) = msg.args
        else:
            (channel, target) = msg.args
            kickmsg = ''
        if kickmsg:
            self.doLog(irc, channel,
                       '*** %s was kicked by %s (%s)\n' %
                       (target, msg.nick, kickmsg))
        else:
            self.doLog(irc, channel,
                       '*** %s was kicked by %s\n' % (target, msg.nick))

    def doPart(self, irc, msg):
        for channel in msg.args[0].split(','):
            self.doLog(irc, channel,
                       '*** %s has left %s\n' % (msg.nick, channel))

    def doMode(self, irc, msg):
        channel = msg.args[0]
        if ircutils.isChannel(channel) and msg.args[1:]:
            self.doLog(irc, channel,
                       '*** %s sets mode: %s %s\n' %
                       (msg.nick or msg.prefix, msg.args[1],
                        ' '.join(msg.args[2:])))

    def doTopic(self, irc, msg):
        if len(msg.args) == 1:
            return # It's an empty TOPIC just to get the current topic.
        channel = msg.args[0]
        self.doLog(irc, channel,
                   '*** %s changes topic to "%s"\n' % (msg.nick, msg.args[1]))

    def doQuit(self, irc, msg):
        for (channel, chan) in self.laststate.channels.iteritems():
            if msg.nick in chan.users:
                self.doLog(irc, channel, '*** %s has quit IRC\n' % msg.nick)

    def outFilter(self, irc, msg):
        # Gotta catch my own messages *somehow* :)
        # Let's try this little trick...
        if msg.command in ('PRIVMSG', 'NOTICE'):
            # Other messages should be sent back to us.
            m = ircmsgs.IrcMsg(msg=msg, prefix=irc.prefix)
            self(irc, m)
        return msg


Class = ChannelLogger
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
