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

import ircmsgs
import privmsgs
import callbacks

class FunctionsTest(unittest.TestCase):
    def testGetChannel(self):
        channel = '#foo'
        msg = ircmsgs.privmsg(channel, 'foo bar baz')
        args = msg.args[1].split()
        originalArgs = args[:]
        self.assertEqual(privmsgs.getChannel(msg, args), channel)
        self.assertEqual(args, originalArgs)
        msg = ircmsgs.privmsg('nick', '%s bar baz' % channel)
        args = msg.args[1].split()
        originalArgs = args[:]
        self.assertEqual(privmsgs.getChannel(msg, args), channel)
        self.assertEqual(args, originalArgs[1:])

    def testGetArgs(self):
        args = ['foo', 'bar', 'baz']
        self.assertEqual(privmsgs.getArgs(args), ' '.join(args))
        self.assertEqual(privmsgs.getArgs(args, required=2),
                         [args[0], ' '.join(args[1:])])
        self.assertEqual(privmsgs.getArgs(args, required=3), args)
        self.assertRaises(callbacks.ArgumentError,
                          privmsgs.getArgs, args, required=4)
        self.assertEqual(privmsgs.getArgs(args, required=3, optional=1),
                         args + [''])
        self.assertEqual(privmsgs.getArgs(args, required=0, optional=1),
                         ' '.join(args))


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

