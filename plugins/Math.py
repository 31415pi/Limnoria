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
Various math-related commands.
"""

__revision__ = "$Id$"

import plugins

import re
import math
import cmath
import types
import string
from itertools import imap

import utils
import privmsgs
import callbacks

import convertcore 


def configure(onStart, afterConnect, advanced):
    # This will be called by setup.py to configure this module.  onStart and
    # afterConnect are both lists.  Append to onStart the commands you would
    # like to be run when the bot is started; append to afterConnect the
    # commands you would like to be run when the bot has finished connecting.
    from questions import expect, anything, something, yn
    onStart.append('load Math')

class Math(callbacks.Privmsg):
    ###
    # So this is how the 'calc' command works:
    # First, we make a nice little safe environment for evaluation; basically,
    # the names in the 'math' and 'cmath' modules.  Then, we remove the ability
    # of a random user to get ints evaluated: this means we have to turn all
    # int literals (even octal numbers and hexadecimal numbers) into floats.
    # Then we delete all square brackets, underscores, and whitespace, so no
    # one can do list comprehensions or call __...__ functions.
    ###
    def base(self, irc, msg, args):
        """<base> <number>

        Converts from base <base> the number <number>
        """
        (base, number) = privmsgs.getArgs(args, required=2)
        try:
            base = int(base)
            if not (2 <= base <= 36):
                raise ValueError
        except ValueError:
            irc.error('<base> must be a number between 2 and 36.')
            return
        try:
            irc.reply(str(long(number, int(base))))
        except ValueError:
            irc.error('Invalid <number> for base %s: %s' % (base, number))

    _mathEnv = {'__builtins__': types.ModuleType('__builtins__'), 'i': 1j}
    _mathEnv.update(math.__dict__)
    _mathEnv.update(cmath.__dict__)
    def _sqrt(x):
        if isinstance(x, complex) or x < 0:
            return cmath.sqrt(x)
        else:
            return math.sqrt(x)
    _mathEnv['sqrt'] = _sqrt
    _mathRe = re.compile(r'((?:(?<![A-Fa-f\d])-)?'
                         r'(?:0x[A-Fa-f\d]+|'
                         r'0[0-7]+|'
                         r'\d+\.\d+|'
                         r'\.\d+|'
                         r'\d+\.|'
                         r'\d+))')
    def _floatToString(self, x):
        if -1e-10 < x < 1e-10:
            return '0'
        elif -1e-10 < int(x) - x < 1e-10:
            return str(int(x))
        else:
            return str(x)
    
    def _complexToString(self, x):
        realS = self._floatToString(x.real)
        imagS = self._floatToString(x.imag)
        if imagS == '0':
            return realS
        elif imagS == '1':
            imagS = '+i'
        elif imagS == '-1':
            imagS = '-i'
        elif x.imag < 0:
            imagS = '%si' % imagS
        else:
            imagS = '+%si' % imagS
        if realS == '0' and imagS == '0':
            return '0'
        elif realS == '0':
            return imagS.lstrip('+')
        elif imagS == '0':
            return realS
        else:
            return '%s%s' % (realS, imagS)

    def calc(self, irc, msg, args):
        """<math expression>

        Returns the value of the evaluted <math expression>.  The syntax is
        Pt's ython syntax; the type of arithmetic is floating point.  Floating
        point arithmetic is used in order to prevent a user from being able to
        crash to the bot with something like 10**10**10**10.  One consequence
        is that large values such as 10**24 might not be exact.
        """
        text = privmsgs.getArgs(args)
        if text != text.translate(string.ascii, '_[]'):
            irc.error('There\'s really no reason why you should have '
                           'underscores or brackets in your mathematical '
                           'expression.  Please remove them.')
            return
        # This removes spaces, too, but we'll leave the removal of _[] for
        # safety's sake.
        text = text.translate(string.ascii, '_[] \t')
        if 'lambda' in text:
            irc.error('You can\'t use lambda in this command.')
            return
        text = text.replace('lambda', '') # Let's leave it in for safety.
        
        def handleMatch(m):
            s = m.group(1)
            if s.startswith('0x'):
                i = int(s, 16)
            elif s.startswith('0') and '.' not in s:
                try:
                    i = int(s, 8)
                except ValueError:
                    i = int(s)
            else:
                i = float(s)
            x = complex(i)
            if x == abs(x):
                x = abs(x)
            return str(x)
        text = self._mathRe.sub(handleMatch, text)
        try:
            self.log.info('evaluating %r from %s' % (text, msg.prefix))
            print text
            x = complex(eval(text, self._mathEnv, self._mathEnv))
            irc.reply(self._complexToString(x))
        except OverflowError:
            maxFloat = math.ldexp(0.9999999999999999, 1024)
            irc.error('The answer exceeded %s or so.' % maxFloat)
        except TypeError:
            print "hey"
            irc.error('Something in there wasn\'t a valid number.')
        except NameError, e:
            irc.error('%s is not a defined function.' % str(e).split()[1])
        except Exception, e:
            irc.error(str(e))

    def icalc(self, irc, msg, args):
        """<math expression>

        This is the same as the calc command except that it allows integer
        math, and can thus cause the bot to suck up CPU.  Hence it requires
        the 'trusted' capability to use.
        """
        text = privmsgs.getArgs(args)
        if text != text.translate(string.ascii, '_[]'):
            irc.error('There\'s really no reason why you should have '
                           'underscores or brackets in your mathematical '
                           'expression.  Please remove them.')
            return
        # This removes spaces, too, but we'll leave the removal of _[] for
        # safety's sake.
        text = text.translate(string.ascii, '_[] \t')
        if 'lambda' in text:
            irc.error('You can\'t use lambda in this command.')
            return
        text = text.replace('lambda', '')
        try:
            self.log.info('evaluating %r from %s' % (text, msg.prefix))
            irc.reply(str(eval(text, self._mathEnv, self._mathEnv)))
        except OverflowError:
            maxFloat = math.ldexp(0.9999999999999999, 1024)
            irc.error('The answer exceeded %s or so.' % maxFloat)
        except TypeError:
            print "ho"
            irc.error('Something in there wasn\'t a valid number.')
        except NameError, e:
            irc.error('%s is not a defined function.' % str(e).split()[1])
        except Exception, e:
            irc.error(utils.exnToString(e))
    icalc = privmsgs.checkCapability(icalc, 'trusted')
            
    _rpnEnv = {
        'dup': lambda s: s.extend([s.pop()]*2),
        'swap': lambda s: s.extend([s.pop(), s.pop()])
        }
    def rpn(self, irc, msg, args):
        """<rpn math expression>

        Returns the value of an RPN expression.
        """
        stack = []
        for arg in args:
            try:
                x = complex(arg)
                if x == abs(x):
                    x = abs(x)
                stack.append(x)
            except ValueError: # Not a float.
                if arg in self._mathEnv:
                    f = self._mathEnv[arg]
                    if callable(f):
                        called = False
                        arguments = []
                        while not called and stack:
                            arguments.append(stack.pop())
                            try:
                                stack.append(f(*arguments))
                                called = True
                            except TypeError:
                                pass
                        if not called:
                            irc.error('Not enough arguments for %s' % arg)
                            return
                    else:
                        stack.append(f)
                elif arg in self._rpnEnv:
                    self._rpnEnv[arg](stack)
                else:
                    arg2 = stack.pop()
                    arg1 = stack.pop()
                    s = '%s%s%s' % (arg1, arg, arg2)
                    try:
                        stack.append(eval(s, self._mathEnv, self._mathEnv))
                    except SyntaxError:
                        irc.error('%r is not a defined function.' % arg)
                        return
        if len(stack) == 1:
            irc.reply(str(self._complexToString(complex(stack[0]))))
        else:
            s = ', '.join(imap(self._complexToString, imap(complex, stack)))
            irc.reply('Stack: [%s]' % s)

    def convert(self, irc, msg, args):
        """[<number>] <unit> to <other unit>

        Converts from <unit> to <other unit>. If number isn't given, it
        defaults to 1. For unit information, see 'units' command.
        """
        
        # see if the first arg is a number of some sort
        if args:       
            try:
                num = float(args[0])
                args.pop(0)
            except ValueError:
                num = 1.0
        else:
            raise callbacks.ArgumentError

        try:
            the_rest = ' '.join(args)
            (unit1, unit2) = the_rest.split(' to ')
        except ValueError:
            raise callbacks.ArgumentError

        try:
            newNum = convertcore.convert(num, unit1, unit2)
            newNum = self._floatToString(newNum)
            
            irc.reply('%s %s' % (newNum , unit2))
        except convertcore.UnitDataError, ude:
            irc.error(str(ude))

    def units(self, irc, msg, args):
        """ [<type>]

        With no arguments, returns a list of measurement types, which can be
        passed as arguments. When called with a type as an argument, returns
        the units of that type.
        """
        
        if len(args) == 0:
            type = None
        else:
            type = ' '.join(args)
        irc.reply(convertcore.units(type))
        
Class = Math

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
