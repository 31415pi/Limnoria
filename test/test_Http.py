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

class HttpTest(PluginTestCase):
    plugins = ('Http',)
    def testDeepthought(self):
        self.assertNotError('deepthought')

    def testStockquote(self):
        self.assertNotError('stockquote MSFT')

    def testFreshmeat(self):
        self.assertNotError('freshmeat supybot')

    def testTitle(self):
        self.assertResponse('title slashdot.org',
                            'Slashdot: News for nerds, stuff that matters')
        self.assertResponse('title http://www.slashdot.org/',
                            'Slashdot: News for nerds, stuff that matters')

    def testFoldoc(self):
        self.assertNotError('foldoc perl')

    def testGeekquote(self):
        self.assertNotError('geekquote')
        self.assertNotError('geekquote multiline')

    def testAcronym(self):
        self.assertNotError('acronym PERL')

    def testNetcraft(self):
        self.assertNotError('netcraft slashdot.org')
