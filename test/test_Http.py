#!/usr/bin/env python

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

from testsupport import *

class HttpTest(PluginTestCase):
    plugins = ('Http',)
    if network:
        def testExtension(self):
            self.assertHelp('extension')
            self.assertRegexp('extension doc', r'Microsoft\'s Word Document')
            self.assertError('extension zapohd')
            self.assertError('extension fo<')

        def testHeaders(self):
            self.assertError('headers ftp://ftp.cdrom.com/pub/linux')
            self.assertNotError('headers http://www.slashdot.org/')

        def testDoctype(self):
            self.assertError('doctype ftp://ftp.cdrom.com/pub/linux')
            self.assertNotError('doctype http://www.slashdot.org/')
            m = self.getMsg('doctype http://moobot.sf.net/')
            self.failUnless(m.args[1].endswith('>'))

        def testSize(self):
            self.assertError('size ftp://ftp.cdrom.com/pub/linux')
            self.assertNotError('size http://supybot.sf.net/')
            self.assertNotError('size http://www.slashdot.org/')

        def testStockquote(self):
            self.assertNotError('stockquote MSFT')
            self.assertError('stockquote MSFT SCOX')

        def testFreshmeat(self):
            self.assertNotError('freshmeat supybot')
            self.assertNotError('freshmeat My Classifieds')
            self.assertNotRegexp('freshmeat supybot', 'DOM Element')
            m = self.assertNotRegexp('freshmeat asdlfkasjdf','Exception')
            self.failIf(m.args[1].count('Error') > 1)

        def testTitle(self):
            self.assertResponse('title slashdot.org',
                                'Slashdot: News for nerds, stuff that matters')
            self.assertResponse('title http://www.slashdot.org/',
                                'Slashdot: News for nerds, stuff that matters')
            self.assertNotRegexp('title '
                                 'http://www.amazon.com/exec/obidos/tg/detail/-/'
                                 '1884822312/qid=1063140754/sr=8-1/ref=sr_8_1/'
                                 '002-9802970-2308826?v=glance&s=books&n=507846',
                                 'no HTML title')
            # Checks the non-greediness of the regexp
            self.assertResponse('title '
                                'http://www.space.com/scienceastronomy/'
                                'jupiter_dark_spot_031023.html',
                                'Mystery Spot on Jupiter Baffles Astronomers')
            # Checks for @title not-working correctly
            self.assertResponse('title '\
                'http://www.catb.org/~esr/jargon/html/F/foo.html',
                'foo')

        def testAcronym(self):
            self.assertRegexp('acronym ASAP', 'as soon as possible')
            self.assertNotRegexp('acronym asap', 'Definition')
            self.assertNotRegexp('acronym UNIX', 'not an acronym')
            # Used to pass requests with spaces ... make sure that stays fixed
            self.assertNotError('acronym W T F')

        def testNetcraft(self):
            self.assertNotError('netcraft slashdot.org')

        def testKernel(self):
            self.assertNotError('kernel')

        def testPgpkey(self):
            self.assertNotError('pgpkey jeremiah fincher')

        def testZipinfo(self):
            self.assertRegexp('zipinfo 02135',
                              r'City: Brighton; State: MA; County: Suffolk')
            self.assertError('zipinfo 123456')
            self.assertError('zipinfo O1233')
            self.assertRegexp('zipinfo 00000',
                              r'Only about \d+,\d+ of the \d+,\d+ possible')
            self.assertRegexp('zipinfo 78014', 'County: La Salle')
            self.assertRegexp('zipinfo 90001',
                              r'City: Los Angeles.*County: Los Angeles')


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

