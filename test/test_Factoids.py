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

from testsupport import *

try:
    import sqlite
except ImportError:
    sqlite = None

if sqlite is not None:
    class FactoidsTestCase(ChannelPluginTestCase, PluginDocumentation):
        plugins = ('Factoids',)
        def testRandomfactoid(self):
            self.assertError('random')
            self.assertNotError('learn jemfinch as my primary author')
            self.assertRegexp('random', 'primary author')

        def testLearn(self):
            self.assertNotError('learn jemfinch as my primary author')
            self.assertNotError('info jemfinch')
            self.assertRegexp('whatis jemfinch', 'my primary author')
            self.assertRegexp('whatis JEMFINCH', 'my primary author')
            self.assertRegexp('whatis JEMFINCH 1', 'my primary author')
            self.assertNotError('learn jemfinch as a bad assembly programmer')
            self.assertRegexp('whatis jemfinch 2', 'bad assembly')
            self.assertNotRegexp('whatis jemfinch 2', 'primary author')
            self.assertRegexp('whatis jemfinch', r'.*primary author.*assembly')
            self.assertError('forget jemfinch')
            self.assertError('forget jemfinch 3')
            self.assertError('forget jemfinch 0')
            self.assertNotError('forget jemfinch 2')
            self.assertNotError('forget jemfinch 1')
            self.assertError('whatis jemfinch')
            self.assertError('info jemfinch')

            self.assertNotError('learn foo bar as baz')
            self.assertNotError('info foo bar')
            self.assertRegexp('whatis foo bar', 'baz')
            self.assertNotError('learn foo bar as quux')
            self.assertRegexp('whatis foo bar', '.*baz.*quux')
            self.assertError('forget foo bar')
            self.assertNotError('forget foo bar 2')
            self.assertNotError('forget foo bar 1')
            self.assertError('whatis foo bar')
            self.assertError('info foo bar')

            self.assertError('learn foo bar baz') # No 'as'
            self.assertError('learn foo bar') # No 'as'

        def testChangeFactoid(self):
            self.assertNotError('learn foo as bar')
            self.assertNotError('change foo 1 s/bar/baz/')
            self.assertRegexp('whatis foo', 'baz')
            self.assertError('change foo 2 s/bar/baz/')
            self.assertError('change foo 0 s/bar/baz/')

        def testSearchFactoids(self):
            self.assertNotError('learn jemfinch as my primary author')
            self.assertNotError('learn strike as a cool guy working on me')
            self.assertNotError('learn inkedmn as another of my developers')
            self.assertNotError('learn jamessan as a developer of much python')
            self.assertNotError('learn bwp as author of my weather command')
            self.assertRegexp('search --regexp /.w./', 'bwp')
            self.assertRegexp('search --regexp /^.+i/',
                              'jemfinch.*strike')
            self.assertNotRegexp('search --regexp /^.+i/', 'inkedmn')
            self.assertRegexp('search --regexp /^j/',
                              'jemfinch.*jamessan')
            self.assertRegexp('search j*', 'jemfinch.*jamessan')
            self.assertRegexp('search --exact ke',
                              'inkedmn.*strike|strike.*inkedmn')
            self.assertRegexp('search *ke*',
                              'inkedmn.*strike|strike.*inkedmn')
            self.assertRegexp('search ke',
                              'inkedmn.*strike|strike.*inkedmn')
            self.assertRegexp('search jemfinch',
                              'my primary author')

        def testWhatisOnNumbers(self):
            self.assertNotError('learn 911 as emergency number')
            self.assertRegexp('whatis 911', 'emergency number')

        def testNotZeroIndexed(self):
            self.assertNotError('learn foo as bar')
            self.assertNotRegexp('info foo', '#0')
            self.assertNotRegexp('whatis foo', '#0')
            self.assertNotError('learn foo as baz')
            self.assertNotRegexp('info foo', '#0')
            self.assertNotRegexp('whatis foo', '#0')

        def testInfoReturnsRightNumber(self):
            self.assertNotError('learn foo as bar')
            self.assertNotRegexp('info foo', '2 factoids')


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

