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

import os
import time

from test import *

class DebianTestCase(PluginTestCase, PluginDocumentation):
    plugins = ('Debian',)
    timeout = 100
    cleanDataDir = False
    fileDownloaded = False

    def setUp(self, nick='test'):
        PluginTestCase.setUp(self)
        try:
            if os.path.exists(os.path.join(conf.dataDir, 'Contents-i386.gz')):
                pass
            else:
                print
                print "Dowloading files, this may take awhile"
                while not os.path.exists(os.path.join(conf.dataDir,
                    'Contents-i386.gz')):
                    time.sleep(1)
                print "Download complete"
                print "Starting test ..."
                self.fileDownloaded = True
        except KeyboardInterrupt:
            pass

    def testDebversion(self):
        self.assertNotError('debversion')
        self.assertRegexp('debversion lakjdfad', r'^No package.*\(all\)')
        self.assertRegexp('debversion unstable alkdjfad',
            r'^No package.*\(unstable\)')
        self.assertRegexp('debversion gaim',
            r'Total matches:.*gaim.*\(stable\)')
        self.assertError('debversion unstable')

    def testDebfile(self):
        if not self.fileDownloaded:
            pass
        self.assertNotError('debfile')
        self.assertRegexp('debfile --exact bin/gaim', r'net/gaim')

    def testDebincoming(self):
        self.assertNotError('debincoming')

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

