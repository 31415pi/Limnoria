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
import operator

def isUserHostmask(s):
    """Returns whether or not the string s is a valid User hostmask."""
    p1 = s.find('!')
    p2 = s.find('@')
    if p1 < p2-1 and p1 >= 1 and p2 >= 3 and len(s) > p2+1:
        return True
    else:
        return False

def isServerHostmask(s):
    """Returns True if s is a valid server hostmask."""
    return (not isUserHostmask(s) and s.find('!') == -1 and s.find('@') == -1)

def nickFromHostmask(hostmask):
    """Returns the nick from a user hostmask."""
    assert isUserHostmask(hostmask)
    return nick(hostmask.split('!', 1)[0])

def userFromHostmask(hostmask):
    """Returns the user from a user hostmask."""
    assert isUserHostmask(hostmask)
    return hostmask.split('!', 1)[1].split('@', 1)[0]

def hostFromHostmask(hostmask):
    """Returns the host from a user hostmask."""
    assert isUserHostmask(hostmask)
    return hostmask.split('@', 1)[1]

def splitHostmask(hostmask):
    """Returns the nick, user, host of a user hostmask."""
    assert isUserHostmask(hostmask)
    nck, rest = hostmask.split('!', 1)
    user, host = rest.split('@', 1)
    return (nick(nck), user, host)

def joinHostmask(nick, ident, host):
    """Joins the nick, ident, host into a user hostmask."""
    assert nick and ident and host
    return '%s!%s@%s' % (nick, ident, host)

_lowertrans = string.maketrans(string.ascii_uppercase + r'\[]~',
                               string.ascii_lowercase + r'|{}^')
def toLower(s):
    """Returns the string s lowered according to IRC case rules."""
    return s.translate(_lowertrans)

def nickEqual(nick1, nick2):
    """Returns True if nick1 == nick2 according to IRC case rules."""
    return toLower(nick1) == toLower(nick2)

_nickchars = r'_[]\`^{}|-'
_nickre = re.compile(r'^[A-Za-z%s][0-9A-Za-z%s]+$' % (re.escape(_nickchars),
                                                      re.escape(_nickchars)))
def isNick(s):
    """Returns True if s is a valid IRC nick."""
    if re.match(_nickre, s):
        return True
    else:
        return False

def isChannel(s):
    """Returns True if s is a valid IRC channel name."""
    return (s and s[0] in '#&+!' and len(s) <= 50 and \
            '\x07' not in s and ',' not in s and ' ' not in s)

def hostmaskPatternEqual(pattern, hostmask):
    """Returns True if hostmask matches the hostmask pattern pattern."""
    return fnmatch.fnmatch(toLower(hostmask), toLower(pattern))

_ipchars = string.digits + '.'
def isIP(s):
    """Not quite perfect, but close enough until I can find the regexp I want.

    >>> isIP('255.255.255.255')
    1

    >>> isIP('abc.abc.abc.abc')
    0
    """
    if s.translate(string.ascii, _ipchars) == '':
        quads = s.split('.')
        if len(quads) <= 4:
            for quad in quads:
                if int(quad) >= 256:
                    return False
            return True
        else:
            return False
    else:
        return False

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
    """Returns if s is strictly a valid argument for an IRC message."""
    return '\r' not in s and '\n' not in s and '\x00' not in s

notFunky = string.ascii[32:]+'\x02'
def safeArgument(s):
    """If s is unsafe for IRC, returns a safe version."""
    if isValidArgument(s) and s.translate(string.ascii, notFunky) == '':
        return s
    else:
        return repr(s)

def replyTo(msg):
    """Returns the appropriate target to send responses to msg."""
    if isChannel(msg.args[0]):
        return msg.args[0]
    else:
        return msg.nick

def privmsgPayload(L, sep, limit=425):
    """Returns a valid privmsg payload given a list of strings and a separator.

    Items are popped from the back of the list until the payload is small
    enough to fit into a single PRIVMSG payload.
    """
    shrinkList(L, sep, limit)
    return sep.join(L)

def shrinkList(L, sep='', limit=425):
    """Shrinks a list of strings to a given combined length of limit."""
    length = len(sep)
    while reduce(operator.add, map(length.__add__, map(len, L)), 0)> limit:
          L.pop()


class nick(str):
    """This class does case-insensitive comparisons of nicks."""
    def __init__(self, s):
        self.original = s
        self.lowered = toLower(s)

    def __repr__(self):
        return repr(self.original)

    def __str__(self):
        return str(self.original)
    
    def __eq__(self, s):
        try:
            return toLower(s) == self.lowered
        except:
            return False

    def __hash__(self):
        return hash(self.lowered)


class IrcDict(dict):
    """Subclass of dict to make key comparison IRC-case insensitive."""
    def __contains__(self, s):
        return dict.__contains__(self, toLower(s))
    has_key = __contains__

    def __setitem__(self, s, v):
        dict.__setitem__(self, toLower(s), v)

    def __getitem__(self, s):
        return dict.__getitem__(self, toLower(s))

    def __delitem__(self, s):
        dict.__delitem__(self, toLower(s))


if __name__ == '__main__':
    import sys, doctest
    doctest.testmod(sys.modules['__main__'])
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
