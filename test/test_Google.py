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

from test import *

class GoogleTestCase(ChannelPluginTestCase, PluginDocumentation):
    plugins = ('Google',)
    def testNoNoLicenseKeyError(self):
        self.irc.feedMsg(ircmsgs.privmsg(self.channel, 'google blah'))
        self.assertNoResponse(' ')
        
    def testGroupsSnarfer(self):
        self.assertNotError('google config groups-snarfer on')
        self.assertRegexp('http://groups.google.com/groups?dq=&hl=en&'
                          'lr=lang_en&ie=UTF-8&oe=UTF-8&selm=698f09f8.'
                          '0310132012.738e22fc%40posting.google.com',
                          r'comp\.lang\.python.*question: usage of __slots__')
        self.assertRegexp('http://groups.google.com/groups?selm=ExDm.'
                          '8bj.23%40gated-at.bofh.it&oe=UTF-8&output=gplain',
                          r'linux\.kernel.*NFS client freezes')

    def testConfig(self):
        self.assertNotError('google config groups-snarfer off')
        self.assertNoResponse('http://groups.google.com/groups?dq=&hl=en&'
                              'lr=lang_en&ie=UTF-8&oe=UTF-8&selm=698f09f8.'
                              '0310132012.738e22fc%40posting.google.com')
        self.assertNotError('google config groups-snarfer on')
        self.assertNotError('http://groups.google.com/groups?dq=&hl=en&'
                            'lr=lang_en&ie=UTF-8&oe=UTF-8&selm=698f09f8.'
                            '0310132012.738e22fc%40posting.google.com')


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

