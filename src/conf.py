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

from fix import *

import sets
import os.path

###
# Directions:
#
# Boolean values should be either True or False.
###

###
# Directories.
###
logDir = 'logs'
confDir = 'conf'
dataDir = 'data'
pluginDir = 'plugins'

###
# Files.
###
userfile = os.path.join(confDir, 'users.conf')
channelfile = os.path.join(confDir, 'channels.conf')
ignoresfile = os.path.join(confDir, 'ignores.conf')
rawlogfile = os.path.join(logDir, 'raw.log')

###
# timestampFormat: A format string defining how timestamps should be.  Check
#                  the Python library reference for the "time" module to see
#                  what the various format specifiers mean.
###
timestampFormat = '[%d-%b-%Y %H:%M:%S]'

###
# throttleTime: A floating point number of seconds to throttle queued messages.
#               (i.e., messages will not be sent faster than once per
#                throttleTime units.)
###
throttleTime = 1.0

###
# allowEval: True if the owner (and only the owner) should be able to eval
#            arbitrary Python code.
###
allowEval = True

###
# defaultCapabilities: Capabilities allowed to everyone by default.  You almost
#                      certainly want to have !owner and !admin in here.
###
defaultCapabilities = sets.Set(['!owner', '!admin'])

###
# reply%s: Stock replies for various reasons.
###
replyError = 'An error has occurred and has been logged.'
replyNoCapability = 'You don\'t have the "%s" capability.'
replySuccess = 'The operation succeeded.'
replyIncorrectAuth = 'Your hostmasks don\'t match or your password is wrong.'
replyNoUser = 'I can\'t find that user in my database.'
replyInvalidArgument = 'I can\'t send \\r, \\n, or \\0 (\\x00).'
replyRequiresPrivacy = 'That can\'t be done in a channel.'
replyEvalNotAllowed = 'You must enable conf.allowEval for that to work.'

###
# errorReplyPrivate: True if errors should be reported privately so as not to
#                    bother the channel.
###
errorReplyPrivate = False

###
# telnetEnable: A boolean saying whether or not to enable the telnet REPL.
#               This will allow a user with the 'owner' capability to telnet
#               into the bot and see how it's working internally.  A lifesaver
#               for development.
###
telnetEnable = False
telnetPort = 31337

###
# poll: the length of a polling term.
#       If asyncore drivers are all you're using, feel free to make
#       this arbitrarily large -- be warned, however, that all other
#       drivers are just sitting around while asyncore waits during
#       this poll period (including the schedule).  It'll take more
#       CPU, but you probably don't want to set this more than 0.01
#       when you've got non-asyncore drivers to worry about.
###
poll = 1

###
# maxHistory: Maximum number of messages kept in an Irc object's state.
###
maxHistory = 100

###
# pingInterval: Number of seconds between PINGs to the server.
#               0 means not to ping the server.
###
pingInterval = 120

###
# nickmods: List of ways to 'spice up' a nick so the bot doesn't run out of
#           nicks if all his normal ones are taken.
###
nickmods = ['%s^', '^%s^', '__%s__', '%s_', '%s__', '__%s', '^^%s^^', '{%s}',
            '[%s]', '][%s][', '}{%s}{', '}{}%s', '^_^%s', '%s^_^', '^_^%s^_^']

###
# defaultAllow: Are commands allowed by default?
###
defaultAllow = True

###
# defaultChannelAllow: does an IrcChannel allow a command by by default?
###
defaultChannelAllow = True

###
# defaultIgnore: True if users should be ignored by default.
#                It's a really easy way to make sure that people who want to
#                talk to the bot register first.  (Of course, they can't
#                register if they're ignored.  We'll work on that.)
###
defaultIgnore = False

###
# ignores: Hostmasks to ignore.
###
ignores = []

###
# prefixChars: A string of chars that are valid prefixes to address the bot.
###
prefixChars = '@'

###
# detailedTracebacks: A boolean describing whether or not the bot will give
#                     *extremely* detailed tracebacks.  Be cautioned, this eats
#                     a lot of log file space.
###
detailedTracebacks = True

###
# driverModule: A string that is the module where the default driver for the
#               bot will be found.
###
driverModule = 'asyncoreDrivers'
#driverModule = 'twistedDrivers'

###############################
###############################
###############################
# DO NOT EDIT PAST THIS POINT #
###############################
###############################
###############################
class ConfigurationDict(dict):
    def __init__(self, L=()):
        L = [(key.lower(), value) for (key, value) in L]
        dict.__init__(self, L)

    def __setitem__(self, key, value):
        dict.__setitem__(self, key.lower(), value)

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key.lower())
        except KeyError:
            return ''

    def __contains__(self, key):
        return dict.__contains__(self, key.lower())

config = ConfigurationDict()
    
def processConfig(filename):
    import debug
    import email
    def reportConfigError(filename, msg):
        debug.unrecoverableError('%s: %s' % (filename, msg))
    try:
        fd = file(filename)
        m = email.message_from_file(fd)
        for (k, v) in m.items():
            config[k] = v
        if 'nick' not in config:
            reportConfigError(filename, 'No nick defined.')
        if 'server' not in config:
            reportConfigError(filename, 'No server defined.')
        if 'user' not in config:
            config['user'] = config['nick']
        if 'ident' not in config:
            config['ident'] = config['nick']
        server = config['server']
        if ':' in server:
            (server, port) = server.split(':', 1)
            try:
                server = (server, int(port))
            except ValueError:
                reportConfigError(filename, 'Server has an invalid port.')
        else:
            server = (server, 6667)
        config['server'] = server
        text = m.get_payload()
        while 1:
            # Gotta remove all extra newlines.
            newtext = text.replace('\n\n\n', '\n\n')
            if newtext == text:
                break
            else:
                text = newtext
        lines = text.splitlines()
        # There are 2 newlines separating the commands to be run on startup
        # from the commands to be run after connecting.  This separates them
        # based on those newlines.
        (onStart, afterConnect) = tuple(itersplit(lines,lambda s: not s,True))
        config['onStart'] = [s for s in onStart if s and s[0] != '#']
        config['afterConnect'] = [s for s in afterConnect if s and s[0] != '#']

    except IOError, e:
        reportConfigError(filename, e)
    except email.Errors.HeaderParseError, e:
        s = str(e)
        problem = s[s.rfind('`')+1:-2]
        msg = 'Invalid configuration format: %s' % problem
        reportConfigError(filename, msg)

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
