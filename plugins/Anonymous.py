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
Allows folks to talk through the bot anonymously.
"""

__revision__ = "$Id$"

import plugins

import conf
import utils
import ircdb
import ircmsgs
import privmsgs
import registry
import callbacks


def configure(advanced):
    # This will be called by setup.py to configure this module.  Advanced is
    # a bool that specifies whether the user identified himself as an advanced
    # user or not.  You should effect your configuration by manipulating the
    # registry as appropriate.
    from questions import expect, anything, something, yn
    conf.registerPlugin('Anonymous', True)

conf.registerPlugin('Anonymous')
conf.registerChannelValue(conf.supybot.plugins.Anonymous,
    'requirePresenceInChannel', registry.Boolean(True, """Determines whether
    the bot should require people trying to use this plugin to be in the
    channel they wish to anonymously send to."""))
conf.registerGlobalValue(conf.supybot.plugins.Anonymous, 'requireRegistration',
    registry.Boolean(True, """Determines whether the bot should require people
    trying to use this plugin to be registered."""))


class Anonymous(callbacks.Privmsg):
    private = True
    def say(self, irc, msg, args):
        """<channel> <text>

        Sends <text> to <channel>.
        """
        (channel, text) = privmsgs.getArgs(args, required=2)
        if self.registryValue('requireRegistration'):
            try:
                _ = ircdb.users.getUser(msg.prefix)
            except KeyError:
                irc.errorNotRegistered()
                return
        if channel not in irc.state.channels:
            irc.error('I\'m not in %s, chances are that I can\'t say anything '
                      'in there.' % channel)
            return
        if self.registryValue('requirePresenceInChannel', channel) and \
           msg.nick not in irc.state.channels[channel].users:
            irc.error('You must be in %s to "say" in there.' % channel)
            return
        c = ircdb.channels.getChannel(channel)
        if c.lobotomized:
            irc.error('I\'m lobotomized in %s.' % channel)
            return
        if not c.checkCapability(self.__class__.__name__):
            irc.error('That channel has set its capabilities so as to '
                      'disallow the use of this plugin.')
            return
        irc.queueMsg(ircmsgs.privmsg(channel, text))


Class = Anonymous

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
