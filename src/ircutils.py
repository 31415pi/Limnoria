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

from fix import *

import re
import string
import fnmatch

import debug
import world

def isUserHostmask(s):
    p1 = s.find('!')
    p2 = s.find('@')
    if p1 < p2-1 and p1 >= 1 and p2 >= 3 and len(s) > p2+1:
        return True
    else:
        return False

def isServerHostmask(s):
    return (not isUserHostmask(s) and s.find('!') == -1 and s.find('@') == -1)

def nickFromHostmask(hostmask):
    assert isUserHostmask(hostmask)
    return nick(hostmask.split('!', 1)[0])

def userFromHostmask(hostmask):
    assert isUserHostmask(hostmask)
    return hostmask.split('!', 1)[1].split('@', 1)[0]

def hostFromHostmask(hostmask):
    assert isUserHostmask(hostmask)
    return hostmask.split('@', 1)[1]

def splitHostmask(hostmask):
    assert isUserHostmask(hostmask)
    nck, rest = hostmask.split('!', 1)
    user, host = rest.split('@', 1)
    return (nick(nck), user, host)

def joinHostmask(nick, ident, host):
    assert nick and ident and host
    return '%s!%s@%s' % (nick, ident, host)

_lowertrans = string.maketrans(string.ascii_uppercase + r'\[]~',
                               string.ascii_lowercase + r'|{}^')
def toLower(nick):
    return nick.translate(_lowertrans)

def nickEqual(nick1, nick2):
    return toLower(nick1) == toLower(nick2)

nickchars = string.ascii_lowercase + string.ascii_uppercase + r'-[]\\`^{}'
_nickre = re.compile(r'^[%s]+$' % re.escape(nickchars))
def isNick(s):
    if re.match(_nickre, s):
        return True
    else:
        return False

def isChannel(s):
    return (s and s[0] in '#&+!' and len(s) <= 50 and \
            '\x07' not in s and ',' not in s and ' ' not in s)

def hostmaskPatternEqual(pattern, hostmask):
    return fnmatch.fnmatch(toLower(hostmask), toLower(pattern))

_ipchars = string.digits + '.'
def isIP(s):
    """Not quite perfect, but close enough until I can find the regexp I want.

    >>> isIP('255.255.255.255')
    1

    >>> isIP('abc.abc.abc.abc')
    0
    """
    return (s.translate(string.ascii, _ipchars) == "")

def banmask(hostmask):
    """Returns a properly generic banning hostmask for a hostmask.

    >>> banmask('nick!user@host.domain.tld')
    '*!*@*.domain.tld'

    >>> banmask('nick!user@10.0.0.1')
    '*!*@10.0.0.*'
    """
    host = hostFromHostmask(hostmask)
    if isIP(host):
        return ('*!*@%s.*' % host[:host.rfind('.')])
    else:
        return ('*!*@*%s' % host[host.find('.'):])

_argModes = 'ovhblkqe'
def separateModes(args):
    """Separates modelines into single mode change tuples.

    Examples:

    >>> separateModes(['+ooo', 'jemfinch', 'StoneTable', 'philmes'])
    [('+o', 'jemfinch'), ('+o', 'StoneTable'), ('+o', 'philmes')]

    >>> separateModes(['+o-o', 'jemfinch', 'PeterB'])
    [('+o', 'jemfinch'), ('-o', 'PeterB')]

    >>> separateModes(['+s-o', 'test'])
    [('+s', None), ('-o', 'test')]

    >>> separateModes(['+sntl', '100'])
    [('+s', None), ('+n', None), ('+t', None), ('+l', '100')]
    """
    modes = args[0]
    assert modes[0] in '+-', 'Invalid args: %r' % args
    args = list(args[1:])
    ret = []
    index = 0
    length = len(modes)
    while index < length:
        if modes[index] in '+-':
            last = modes[index]
            index += 1
        else:
            if modes[index] in _argModes:
                ret.append((last + modes[index], args.pop(0)))
            else:
                ret.append((last + modes[index], None))
            index += 1
    return ret

def joinModes(modes):
    """Joins modes of the same form as returned by separateModes."""
    args = []
    modeChars = []
    currentMode = '\x00'
    for (mode, arg) in modes:
        if arg is not None:
            args.append(arg)
        if not mode.startswith(currentMode):
            currentMode = mode[0]
            modeChars.append(mode[0])
        modeChars.append(mode[1])
    args.insert(0, ''.join(modeChars))
    return args

def bold(s):
    """Returns the string s, bolded."""
    return "\x02%s\x02" % s

def isValidArgument(s):
    return '\r' not in s and '\n' not in s and '\x00' not in s

notFunky = string.printable+'\x02'
def safeArgument(s):
    if isValidArgument(s) and s.translate(string.ascii, notFunky) == '':
        return s
    else:
        return repr(s)

def replyTo(msg):
    if isChannel(msg.args[0]):
        return msg.args[0]
    else:
        return msg.nick

class nick(str):
    """This class does case-insensitive comparisons of nicks."""
    def __init__(self, s):
        self.lowered = toLower(s)

    def __eq__(self, s):
        try:
            return toLower(s) == self.lowered
        except:
            return False

    def __hash__(self):
        return hash(self.lowered)

if __name__ == '__main__':
    import sys, doctest
    doctest.testmod(sys.modules['__main__'])
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
