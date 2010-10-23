###
# Copyright (c) 2010, Valentin Lorentz
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

import re
import sys
import ctypes
import random
from cStringIO import StringIO
import mh_python as megahal
import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks

try:
    from supybot.i18n import PluginInternationalization
    from supybot.i18n import internationalizeDocstring
    _ = PluginInternationalization('MegaHAL')
except:
    # This are useless function that's allow to run the plugin on a bot
    # without the i18n plugin
    _ = lambda x:x
    internationalizeDocstring = lambda x:x

class MegaHAL(callbacks.Plugin):
    """This plugins provides a MegaHAL integration for Supybot.
    MegaHAL must be installed ('apt-get install megahal' on Debian)"""
    callAfter = ['MoobotFactoids', 'Factoids', 'Infobot']
    callBefore = ['Dunno']
    
    def __init__(self, irc):
        self.__parent = super(MegaHAL, self)
        self.__parent.__init__(irc)
        # UTILISER UN CHANGEMENT DE RÉPERTOIRE DE TRAVAIL !
        stdout = sys.stdout
        sys.stdout = StringIO() # Don't display MegaHAL welcome message twice
        megahal.initbrain()
        sys.stdout = stdout
        
        random.seed()
    
    _dontKnow = [
                 'I don\'t know enough to answer you yet!',
                 'I am utterly speechless!',
                 'I forgot what I was going to say!'
                ]
    _translations = {
                     'I don\'t know enough to answer you yet!':
                         _('I don\'t know enough to answer you yet!'),
                     'I am utterly speechless!':
                         _('I am utterly speechless!'),
                     'I forgot what I was going to say!':
                         _('I forgot what I was going to say!'),
                    }

    def _response(self, msg, prb, reply):
        if random.randint(0, 100) < prb:
            response = megahal.doreply(msg)
            if self._translations.has_key(response):
                response = self._translations[response]
            reply(response)
        else:
            megahal.learn(msg)

    def doPrivmsg(self, irc, msg):
        message = msg.args[1]
        probability = self.registryValue('answer.probability')
        
        answer = False
        learn = False
        
        if message.startswith(irc.nick) or re.match('\W.*', message):
            # Managed by invalidCommand
            return
        
        print repr(message)
        if answer:
            self._response(message,
                           self.registryValue('answer.probability'),
                           irc.reply)
        elif learn:
            megahal.learn(message)
    
    def invalidCommand(self, irc, msg, tokens):
        message = msg.args[1]
        usedToStartWithNick = False
        if message.startswith(message):
            parsed = re.match('(.+ |\W)?(?P<message>\w.*)', message)
            message = parsed.group('message')
            usedToStartWithNick = True
        if self.registryValue('answer.commands') or usedToStartWithNick:
            self._response(message,
                        self.registryValue('answer.probabilityWhenAdressed'),
                        irc.reply)
        elif self.registryValue('learn.commands'):
            megahal.learn(message)
    
    @internationalizeDocstring
    def cleanup(self, irc, msg, args):
        """takes no argument
        
        Saves MegaHAL brain to disk."""
        megahal.cleanup()
        irc.replySuccess()

Class = MegaHAL


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
