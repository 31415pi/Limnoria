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

class ShrinkUrlTestCase(ChannelPluginTestCase):
    plugins = ('ShrinkUrl',)
    if network:
        def testTinyurl(self):
            try:
                conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(False)
                self.assertRegexp(
                    'url tiny http://sourceforge.net/tracker/?'
                    'func=add&group_id=58965&atid=489447',
                    r'http://tinyurl.com/rqac')
                conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(True)
                self.assertRegexp(
                    'url tiny http://sourceforge.net/tracker/?'
                    'func=add&group_id=58965&atid=489447',
                    r'http://tinyurl.com/rqac')
            finally:
                conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(False)

        def testTinysnarf(self):
            try:
                conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(True)
                self.assertSnarfRegexp(
                    'http://sourceforge.net/tracker/?func=add&'
                    'group_id=58965&atid=489447',
                    r'http://tinyurl.com/rqac.* \(at')
                self.assertSnarfRegexp(
                    'http://www.urbandictionary.com/define.php?'
                    'term=all+your+base+are+belong+to+us',
                    r'http://tinyurl.com/u479.* \(at')
            finally:
                conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(False)

        def testNonSnarfing(self):
            tiny = conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer()
            snarf = conf.supybot.plugins.ShrinkUrl.nonSnarfingRegexp()
            try:
                conf.supybot.plugins.ShrinkUrl.nonSnarfingRegexp.set('m/sf/')
                try:
                    conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(True)
                    self.assertSnarfNoResponse('http://sf.net/', 2)
                    self.assertSnarfResponse('http://www.sourceforge.net/',
                                             'http://tinyurl.com/2cnkf')
                finally:
                    conf.supybot.plugins.ShrinkUrl.tinyurlSnarfer.setValue(tiny)
            finally:
                conf.supybot.plugins.ShrinkUrl.nonSnarfingRegexp.setValue(snarf)



# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

