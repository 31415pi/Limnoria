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

"""
Various utility commands, mostly useful for manipulating nested commands.
"""

from baseplugin import *

import string

import utils
import privmsgs
import callbacks

def configure(onStart, afterConnect, advanced):
    from questions import expect, anything, yn
    onStart.append('load Utilities')

example = utils.wrapLines("""
<jemfinch> @list Utilities
<supybot> echo, ignore, re, repr, shrink, strconcat, strjoin, strlen, strlower, strtranslate, strupper
<jemfinch> @echo foo bar baz
<supybot> foo bar baz
<jemfinch> @ignore foo bar baz
<jemfinch> (he just ignores them; it's useful to run commands in sequence without caring about 'The operation succeeded' responses.)
<jemfinch> @repr "\n"
<supybot> "\n"
<jemfinch> @eval 'x'*1000
<supybot> My response would've been too long.
<jemfinch> @shrink [eval 'x'*1000]
<supybot> 'xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
<jemfinch> (it was shrunken to 400 characters)
<jemfinch> @strlen [shrink [eval 'x'*1000]]
<supybot> 400
<jemfinch> @strjoin + foo bar baz
<supybot> foo+bar+baz
<jemfinch> @strlower FOO BAR BAZ
<supybot> foo bar baz
<jemfinch> @strupper FOO bar baz
<supybot> FOO BAR BAZ
<jemfinch> @strtranslate abc def "abc is easy as 123"
<supybot> def is edsy ds 123
<jemfinch> @strconcat foo bar
""")

class Utilities(callbacks.Privmsg):
    def ignore(self, irc, msg, args):
        """takes no arguments

        Does nothing.  Useful sometimes for sequencing commands when you don't
        care about their non-error return values.
        """
        pass

    def shrink(self, irc, msg, args):
        """<text>

        Shrinks <text> to 400 characters.
        """
        text = privmsgs.getArgs(args)
        irc.reply(msg, text[:400])

    def strjoin(self, irc, msg, args):
        """<separator> <string 1> [<string> ...]

        Joins all the arguments together with <separator>.
        """
        sep = args.pop(0)
        irc.reply(msg, sep.join(args))

    def strtranslate(self, irc, msg, args):
        """<chars to translate> <chars to replace those with> <text>

        Replaces <chars to translate> with <chars to replace those with> in
        <text>.  The first and second arguments must necessarily be the same
        length.
        """
        (bad, good, text) = privmsgs.getArgs(args, needed=3)
        irc.reply(msg, text.translate(string.maketrans(bad, good)))

    def strupper(self, irc, msg, args):
        """<text>

        Returns <text> uppercased.
        """
        irc.reply(msg, privmsgs.getArgs(args).upper())

    def strlower(self, irc, msg, args):
        """<text>

        Returns <text> lowercased.
        """
        irc.reply(msg, privmsgs.getArgs(args).lower())

    def strlen(self, irc, msg, args):
        """<text>

        Returns the length of <text>.
        """
        total = 0
        for arg in args:
            total += len(arg)
        total += len(args)-1 # spaces between the arguments.
        irc.reply(msg, str(total))

    def repr(self, irc, msg, args):
        """<text>

        Returns the text surrounded by double quotes.
        """
        text = privmsgs.getArgs(args)
        irc.reply(msg, utils.dqrepr(text))

    def strconcat(self, irc, msg, args):
        """<string 1> <string 2>

        Concatenates two strings.  Do keep in mind that this is *not* the same
        thing as strjoin "", since if <string 2> contains spaces, they won't be
        removed by strconcat.
        """
        (first, second) = privmsgs.getArgs(args, needed=2)
        irc.reply(msg, first+second)

    def echo(self, irc, msg, args):
        """takes any number of arguments

        Returns the arguments given it.
        """
        irc.reply(msg, ' '.join(args), prefixName=False)

    def re(self, irc, msg, args):
        """<regexp> <text>

        If <regexp> is of the form m/regexp/flags, returns the portion of
        <text> that matches the regexp.  If <regexp> is of the form
        s/regexp/replacement/flags, returns the result of applying such a
        regexp to <text>
        """
        (regexp, text) = privmsgs.getArgs(args, needed=2)
        f = None
        try:
            r = utils.perlReToPythonRe(regexp)
            f = lambda s: ' '.join(r.findall(text))
        except ValueError, e:
            try:
                f = utils.perlReToReplacer(regexp)
                substitution = True
            except ValueError:
                irc.error(msg, 'Invalid regexp: %s' % e.args[0])
                return
            if f is None:
                irc.error(msg, 'Invalid regexp: %s' % e.args[0])
                return
        irc.reply(msg, f(text))


Class = Utilities
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
