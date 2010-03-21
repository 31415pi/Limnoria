###
# Copyright (c) 2010, Daniel Folkinshteyn
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

from supybot.test import *

try:
    import sqlite3
except ImportError:
    from pysqlite2 import dbapi2 as sqlite3 # for python2.4


class MessageParserTestCase(ChannelPluginTestCase):
    plugins = ('MessageParser','Utilities',) #utilities for the 'echo'
    
    def testAdd(self):
        self.assertError('messageparser add') #no args
        self.assertError('messageparser add "stuff"') #no action arg
        self.assertNotError('messageparser add "stuff" "echo i saw some stuff"')
        self.assertRegexp('messageparser show "stuff"', '.*i saw some stuff.*')
        
        self.assertError('messageparser add "[a" "echo stuff"') #invalid regexp
        self.assertError('messageparser add "(a" "echo stuff"') #invalid regexp
        self.assertNotError('messageparser add "stuff" "echo i saw no stuff"') #overwrite existing regexp
        self.assertRegexp('messageparser show "stuff"', '.*i saw no stuff.*')
        
    def testShow(self):
        self.assertNotError('messageparser add "stuff" "echo i saw some stuff"')
        self.assertRegexp('messageparser show "nostuff"', 'there is no such regexp trigger')
        self.assertRegexp('messageparser show "stuff"', '.*i saw some stuff.*')
        self.assertRegexp('messageparser show --id 1', '.*i saw some stuff.*')
    
    def testInfo(self):
        self.assertNotError('messageparser add "stuff" "echo i saw some stuff"')
        self.assertRegexp('messageparser info "nostuff"', 'there is no such regexp trigger')
        self.assertRegexp('messageparser info "stuff"', '.*i saw some stuff.*')
        self.assertRegexp('messageparser info --id 1', '.*i saw some stuff.*')
        self.assertRegexp('messageparser info "stuff"', 'has been triggered 0 times')
        self.feedMsg('this message has some stuff in it')
        self.getMsg(' ')
        self.assertRegexp('messageparser info "stuff"', 'has been triggered 1 times')
    
    def testTrigger(self):
        self.assertNotError('messageparser add "stuff" "echo i saw some stuff"')
        self.feedMsg('this message has some stuff in it')
        m = self.getMsg(' ')
        self.failUnless(str(m).startswith('PRIVMSG #test :i saw some stuff'))
        
# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
