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
Includes various accessories for callbacks.Privmsg based callbacks.
"""

__revision__ = "$Id$"

import fix

import time
import types
import threading

import conf
import ircdb
import world
import ircmsgs
import ircutils
import callbacks
import structures

def getChannel(msg, args):
    """Returns the channel the msg came over or the channel given in args.

    If the channel was given in args, args is modified (the channel is
    removed).
    """
    if args and ircutils.isChannel(args[0]):
        if conf.requireChannelCommandsToBeSentInChannel:
            if args[0] != msg.args[0]:
                s = 'Channel commands must be sent in the channel to which ' \
                    'they apply.'
                raise callbacks.Error, s
        return args.pop(0)
    elif ircutils.isChannel(msg.args[0]):
        return msg.args[0]
    else:
        raise callbacks.Error, 'Command must be sent in a channel or ' \
                               'include a channel in its arguments.'

def getArgs(args, required=1, optional=0):
    """Take the required/optional arguments from args.

    Always returns a list of size required + optional, filling it with however
    many empty strings is necessary to fill the tuple to the right size.  If
    there is only one argument, a string containing that argument is returned.

    If there aren't enough args even to satisfy required, raise an error and
    let the caller handle sending the help message.
    """
    assert not isinstance(args, str), 'args should be a list.'
    assert not isinstance(args, ircmsgs.IrcMsg), 'args should be a list.'
    if len(args) < required:
        raise callbacks.ArgumentError
    if len(args) < required + optional:
        ret = list(args) + ([''] * (required + optional - len(args)))
    elif len(args) >= required + optional:
        ret = list(args[:required + optional - 1])
        ret.append(' '.join(args[required + optional - 1:]))
    if len(ret) == 1:
        return ret[0]
    else:
        return ret

def checkCapability(f, capability):
    """Makes sure a user has a certain capability before a command will run."""
    def newf(self, irc, msg, args):
        if ircdb.checkCapability(msg.prefix, capability):
            f(self, irc, msg, args)
        else:
            self.log.warning('%r attempted %s without %s.',
                             msg.prefix, f.func_name, capability)
            irc.errorNoCapability(capability)
    newf = types.FunctionType(newf.func_code, newf.func_globals,
                              f.func_name, closure=newf.func_closure)
    newf.__doc__ = f.__doc__
    return newf

def checkChannelCapability(f, capability):
    """Makes sure a user has a certain channel capability before running f.

    Do note that you need to add a "channel" argument to your argument list.
    """
    def newf(self, irc, msg, args, *L):
        channel = getChannel(msg, args)
        chancap = ircdb.makeChannelCapability(channel, capability)
        if ircdb.checkCapability(msg.prefix, chancap):
            L += (channel,)
            ff = types.MethodType(f, self, self.__class__)
            ff(irc, msg, args, *L)
        else:
            self.log.warning('%r attempted %s without %s.',
                             msg.prefix, f.func_name, capability)
            irc.errorNoCapability(chancap)
    newf = types.FunctionType(newf.func_code, newf.func_globals,
                              f.func_name, closure=newf.func_closure)
    newf.__doc__ = f.__doc__
    return newf

def thread(f):
    """Makes sure a command spawns a thread when called."""
    def newf(self, irc, msg, args, *L):
        ff = types.MethodType(f, self, self.__class__)
        t = callbacks.CommandThread(self.callCommand, ff, irc, msg, args, *L)
        t.start()
    newf = types.FunctionType(newf.func_code, newf.func_globals,
                              f.func_name, closure=newf.func_closure)
    newf.__doc__ = f.__doc__
    return newf

def name(f):
    """Makes sure a name is available based on conf.requireRegistration."""
    def newf(self, irc, msg, args, *L):
        try:
            name = ircdb.users.getUser(msg.prefix).name
        except KeyError:
            if conf.requireRegistration:
                irc.errorNotRegistered()
                return
            else:
                name = msg.prefix
        L = (name,) + L
        ff = types.MethodType(f, self, self.__class__)
        ff(irc, msg, args, *L)
    newf = types.FunctionType(newf.func_code, newf.func_globals,
                              f.func_name, closure=newf.func_closure)
    newf.__doc__ = f.__doc__
    return newf

def channel(f):
    """Gives the command an extra channel arg as if it had called getChannel"""
    def newf(self, irc, msg, args, *L):
        channel = getChannel(msg, args)
        L = (channel,) + L
        ff = types.MethodType(f, self, self.__class__)
        ff(irc, msg, args, *L)
    newf = types.FunctionType(newf.func_code, newf.func_globals,
                              f.func_name, closure=newf.func_closure)
    newf.__doc__ = f.__doc__
    return newf

def urlSnarfer(f):
    """Protects the snarfer from loops and whatnot."""
    def newf(self, irc, msg, match, *L):
        now = time.time()
        cutoff = now - conf.snarfThrottle
        q = getattr(self, '_snarfedUrls', None)
        if q is None:
            q = structures.smallqueue()
            self._snarfedUrls = q
        while q and q[0][2] < cutoff:
            q.dequeue()
        url = match.group(0)
        if any(lambda t: t[0] == url and t[1] == msg.args[0], q) and \
               not world.testing:
            self.log.warning('Refusing to snarf %s from %r.', url, msg.prefix)
        else:
            q.enqueue((url, msg.args[0], now))
            if self.threaded:
                f(self, irc, msg, match, *L)
            else:
                L = list(L)
                t = threading.Thread(target=f, args=[self, irc, msg, match]+L)
                t.setDaemon(True)
                t.start()
                world.threadsSpawned += 1
    newf = types.FunctionType(newf.func_code, newf.func_globals,
                              f.func_name, closure=newf.func_closure)
    newf.__doc__ = f.__doc__
    return newf
        

class CapabilityCheckingPrivmsg(callbacks.Privmsg):
    """A small subclass of callbacks.Privmsg that checks self.capability
    before allowing any command to be called.
    """
    capability = '' # To satisfy PyChecker
    def callCommand(self, f, irc, msg, args):
        if ircdb.checkCapability(msg.prefix, self.capability):
            callbacks.Privmsg.callCommand(self, f, irc, msg, args)
        else:
            self.log.warning('%r tried to call %s without %s.',
                             msg.prefix, f.im_func.func_name, self.capability)
            irc.errorNoCapability(self.capability)


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
