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

"""
Includes wrappers for commands.
"""

__revision__ = "$Id$"

import supybot.fix as fix

import getopt

import time
import types
import threading

import supybot.log as log
import supybot.conf as conf
import supybot.utils as utils
import supybot.world as world
import supybot.ircdb as ircdb
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.structures as structures


###
# Non-arg wrappers -- these just change the behavior of a command without
# changing the arguments given to it.
###
def thread(f):
    """Makes sure a command spawns a thread when called."""
    def newf(self, irc, msg, args, *L, **kwargs):
        if threading.currentThread() is world.mainThread:
            t = callbacks.CommandThread(target=irc._callCommand,
                                        args=(f.func_name, self),
                                        kwargs=kwargs)
            t.start()
        else:
            f(self, irc, msg, args, *L, **kwargs)
    return utils.changeFunctionName(newf, f.func_name, f.__doc__)

class UrlSnarfThread(threading.Thread):
    def __init__(self, *args, **kwargs):
        assert 'url' in kwargs
        kwargs['name'] = 'Thread #%s (for snarfing %s)' % \
                         (world.threadsSpawned, kwargs.pop('url'))
        world.threadsSpawned += 1
        threading.Thread.__init__(self, *args, **kwargs)
        self.setDaemon(True)

class SnarfQueue(ircutils.FloodQueue):
    timeout = conf.supybot.snarfThrottle
    def key(self, channel):
        return channel

_snarfed = SnarfQueue()

class SnarfIrc(object):
    def __init__(self, irc, channel, url):
        self.irc = irc
        self.url = url
        self.channel = channel

    def __getattr__(self, attr):
        return getattr(self.irc, attr)

    def reply(self, *args, **kwargs):
        _snarfed.enqueue(self.channel, self.url)
        self.irc.reply(*args, **kwargs)

# This lock is used to serialize the calls to snarfers, so
# earlier snarfers are guaranteed to beat out later snarfers.
_snarfLock = threading.Lock()
def urlSnarfer(f):
    """Protects the snarfer from loops (with other bots) and whatnot."""
    def newf(self, irc, msg, match, *L, **kwargs):
        url = match.group(0)
        channel = msg.args[0]
        if not ircutils.isChannel(channel):
            return
        if ircdb.channels.getChannel(channel).lobotomized:
            self.log.info('Not snarfing in %s: lobotomized.', channel)
            return
        if _snarfed.has(channel, url):
            self.log.info('Throttling snarf of %s in %s.', url, channel)
            return
        irc = SnarfIrc(irc, channel, url)
        def doSnarf():
            _snarfLock.acquire()
            try:
                if msg.repliedTo:
                    self.log.debug('Not snarfing, msg is already repliedTo.')
                    return
                f(self, irc, msg, match, *L, **kwargs)
            finally:
                _snarfLock.release()
        if threading.currentThread() is not world.mainThread:
            doSnarf()
        else:
            L = list(L)
            t = UrlSnarfThread(target=doSnarf, url=url)
            t.start()
    newf = utils.changeFunctionName(newf, f.func_name, f.__doc__)
    return newf

decorators = ircutils.IrcDict({
    'thread': thread,
    'urlSnarfer': urlSnarfer,
})


###
# Arg wrappers, wrappers that add arguments to the command.  They accept the
# irc, msg, and args, of course, as well as a State object which holds the args
# (and kwargs, though none currently take advantage of that) to be given to the
# command being decorated, as well as the name of the command, the plugin, the
# log, etc.
###

# This is just so we can centralize this, since it may change.
def _int(s):
    return int(float(s))

def getInt(irc, msg, args, state, default=None, type='integer', p=None):
    try:
        i = _int(args[0])
        if p is not None:
            if not p(i):
                raise ValueError
        state.args.append(_int(args[0]))
        del args[0]
    except ValueError:
        if default is not None:
            state.args.append(default)
        else:
            irc.errorInvalid(type, args[0])

def getPositiveInt(irc, msg, args, state, *L):
    getInt(irc, msg, args, state,
           p=lambda i: i<=0, type='positive integer', *L)

def getNonNegativeInt(irc, msg, args, state, *L):
    getInt(irc, msg, args, state,
            p=lambda i: i<0, type='non-negative integer', *L)

def getId(irc, msg, args, state):
    getInt(irc, msg, args, state, type='id')

def getExpiry(irc, msg, args, state, default=None):
    now = int(time.time())
    try:
        expires = _int(args[0])
        if expires:
            expires += now
        state.args.append(expires)
        del args[0]
    except ValueError:
        if default is not None:
            if default:
                default += now
            state.args.append(default)
        else:
            irc.errorInvalid('number of seconds', args[0])
    # XXX This should be handled elsewhere; perhaps all optional args should
    # consider their first extra arg to be a default.
    except IndexError:
        if default is not None:
            if default:
                default += now
            state.args.append(default)
        else:
            raise

def getBoolean(irc, msg, args, state, default=None):
    try:
        state.args.append(utils.toBool(args[0]))
        del args[0]
    except ValueError:
        if default is not None:
            state.args.append(default)
        else:
            irc.errorInvalid('boolean', args[0])

def getChannelDb(irc, msg, args, state, **kwargs):
    if not conf.supybot.databases.plugins.channelSpecific():
        state.args.append(None)
        state.channel = None
    else:
        getChannel(irc, msg, args, state, **kwargs)

def getHaveOp(irc, msg, args, state, action='do that'):
    if state.channel not in irc.state.channels:
        irc.error('I\'m not even in %s.' % state.channel, Raise=True)
    if irc.nick not in irc.state.channels[state.channel].ops:
        irc.error('I need to be opped to %s.' % action, Raise=True)

def validChannel(irc, msg, args, state):
    if ircutils.isChannel(args[0]):
        # XXX Check maxlength in irc.state.supported.
        state.args.append(args.pop(0))
    else:
        irc.errorInvalid('channel', args[0])

def getHostmask(irc, msg, args, state):
    if ircutils.isUserHostmask(args[0]):
        state.args.append(args.pop(0))
    else:
        try:
            hostmask = irc.state.nickToHostmask(args[0])
            state.args.append(hostmask)
            del args[0]
        except KeyError:
            irc.errorInvalid('nick or hostmask', args[0])

def getBanmask(irc, msg, args, state):
    getHostmask(irc, msg, args, state)
    # XXX Channel-specific stuff.
    state.args[-1] = ircutils.banmask(state.args[-1])

def getUser(irc, msg, args, state):
    try:
        state.args.append(ircdb.users.getUser(msg.prefix))
    except KeyError:
        irc.errorNotRegistered(Raise=True)

def getOtherUser(irc, msg, args, state):
    try:
        state.args.append(ircdb.users.getUser(args[0]))
        del args[0]
    except KeyError:
        try:
            getHostmask(irc, msg, args, state)
            hostmask = state.args.pop()
            state.args.append(ircdb.users.getUser(hostmask))
        except (KeyError, IndexError, callbacks.Error):
            irc.errorNoUser(Raise=True)

def _getRe(f):
    def get(irc, msg, args, state):
        original = args[:]
        s = args.pop(0)
        def isRe(s):
            try:
                _ = f(s)
                return True
            except ValueError:
                return False
        try:
            while not isRe(s):
                s += ' ' + args.pop(0)
            state.args.append(f(s))
        except IndexError:
            args[:] = original
            raise
    return get

getMatcher = _getRe(utils.perlReToPythonRe)
getReplacer = _getRe(utils.perlReToReplacer)

def getNick(irc, msg, args, state):
    if ircutils.isNick(args[0]):
        if 'nicklen' in irc.state.supported:
            if len(args[0]) > irc.state.supported['nicklen']:
                irc.errorInvalid('nick', s,
                                 'That nick is too long for this server.')
        state.args.append(args.pop(0))
    else:
        irc.errorInvalid('nick', s)

def getChannel(irc, msg, args, state):
    if args and ircutils.isChannel(args[0]):
        channel = args.pop(0)
    elif ircutils.isChannel(msg.args[0]):
        channel = msg.args[0]
    else:
        state.log.debug('Raising ArgumentError because there is no channel.')
        raise callbacks.ArgumentError
    state.channel = channel
    state.args.append(channel)

def checkChannelCapability(irc, msg, args, state, cap):
    assert state.channel, \
           'You must use a channel arg before you use checkChannelCapability.'
    cap = ircdb.canonicalCapability(cap)
    cap = ircdb.makeChannelCapability(state.channel, cap)
    if not ircdb.checkCapability(msg.prefix, cap):
        irc.errorNoCapability(cap, Raise=True)
            
def getLowered(irc, msg, args, state):
    state.args.append(ircutils.toLower(args.pop(0)))

def getSomething(irc, msg, args, state, errorMsg=None, p=None):
    if p is None:
        p = lambda _: True
    if not args[0] or not p(args[0]):
        if errorMsg is None:
            errorMsg = 'You must not give the empty string as an argument.'
        irc.error(errorMsg, Raise=True)
    else:
        state.args.append(args.pop(0))

def getSomethingNoSpaces(irc, msg, args, state, *L):
    def p(s):
        return len(s.split(None, 1)) == 1
    getSomething(irc, msg, args, state, p=p, *L)

def getPlugin(irc, msg, args, state, requirePresent=False):
    cb = irc.getCallback(args[0])
    if requirePresent and cb is None:
        irc.errorInvalid('plugin', s)
    state.args.append(cb)
    del args[0]

def private(irc, msg, args, state):
    if ircutils.isChannel(msg.args[0]):
        irc.errorRequiresPrivacy(Raise=True)

def checkCapability(irc, msg, args, state, cap):
    cap = ircdb.canonicalCapability(cap)
    if not ircdb.checkCapability(msg.prefix, cap):
        state.log.warning('%s tried %s without %s.',
                          msg.prefix, state.name, cap)
        irc.errorNoCapability(cap, Raise=True)
    
def anything(irc, msg, args, state):
    state.args.append(args.pop(0))
    
wrappers = ircutils.IrcDict({
    'id': getId,
    'int': getInt,
    'positiveInt': getPositiveInt,
    'nonNegativeInt': getNonNegativeInt,
    'haveOp': getHaveOp,
    'expiry': getExpiry,
    'nick': getNick,
    'channel': getChannel,
    'plugin': getPlugin,
    'boolean': getBoolean,
    'lowered': getLowered,
    'anything': anything,
    'something': getSomething,
    'somethingWithoutSpaces': getSomethingNoSpaces,
    'channelDb': getChannelDb,
    'hostmask': getHostmask,
    'banmask': getBanmask,
    'user': getUser,
    'private': private,
    'otherUser': getOtherUser,
    'regexpMatcher': getMatcher,
    'validChannel': validChannel,
    'regexpReplacer': getReplacer,
    'checkCapability': checkCapability,
    'checkChannelCapability': checkChannelCapability,
})

class State(object):
    def __init__(self, name=None, logger=None):
        if logger is None:
            logger = log
        self.args = []
        self.kwargs = {}
        self.name = name
        self.log = logger
        self.getopts = []
        self.channel = None
            
def args(irc,msg,args, types=[], state=None,
         getopts=None, noExtra=False, requireExtra=False, combineRest=True):
    orig = args[:]
    if state is None:
        state = State(name='unknown', logger=log)
    if requireExtra:
        combineRest = False # Implied by requireExtra.
    types = types[:] # We're going to destroy this.
    if getopts is not None:
        getoptL = []
        for (key, value) in getopts.iteritems():
            if value != '': # value can be None, remember.
                key += '='
            getoptL.append(key)
    def callWrapper(spec):
        if isinstance(spec, tuple):
            assert spec, 'tuple specification cannot be empty.'
            name = spec[0]
            specArgs = spec[1:]
        else:
            assert isinstance(spec, basestring) or spec is None
            name = spec
            specArgs = ()
        if name is None:
            name = 'anything'
        enforce = True
        optional = False
        if name.startswith('?'):
            optional = True
            name = name[1:]
        elif name.endswith('?'):
            optional = True
            enforce = False
            name = name[:-1]
        wrapper = wrappers[name]
        try:
            wrapper(irc, msg, args, state, *specArgs)
        except (callbacks.Error, ValueError, callbacks.ArgumentError), e:
            state.log.debug('%r when calling wrapper.', utils.exnToString(e))
            if not enforce:
                state.args.append('')
            else:
                state.log.debug('Re-raising %s because of enforce.', e)
                raise
        except IndexError, e:
            state.log.debug('%r when calling wrapper.', utils.exnToString(e))
            if optional:
                state.args.append('')
            else:
                state.log.debug('Raising ArgumentError because of '
                                'non-optional args.')
                raise callbacks.ArgumentError

    # First, we getopt stuff.
    if getopts is not None:
        (optlist, args) = getopt.getopt(args, '', getoptL)
        for (opt, arg) in optlist:
            opt = opt[2:] # Strip --
            assert opt in getopts
            if arg is not None:
                assert getopts[opt] != ''
                state.getopts.append((opt, callWrapper(getopts[opt])))
            else:
                assert getopts[opt] == ''
                state.getopts.append((opt, True))

    # Second, we get out everything but the last argument (or, if combineRest
    # is False, we'll clear out all the types).
    while len(types) > 1 or (types and not combineRest):
        callWrapper(types.pop(0))
    # Third, if there is a remaining required or optional argument
    # (there's a possibility that there were no required or optional
    # arguments) then we join the remaining args and work convert that.
    if types:
        assert len(types) == 1
        if args:
            rest = ' '.join(args)
            args = [rest]
        callWrapper(types.pop(0))
    if noExtra and args:
        log.debug('noExtra and args: %r (originally %r)', args, orig)
        raise callbacks.ArgumentError
    if requireExtra and not args:
        log.debug('requireExtra and not args: %r (originally %r)', args, orig)
    log.debug('args: %r' % args)
    log.debug('State.args: %r' % state.args)
    log.debug('State.getopts: %r' % state.getopts)
    return state

# These are used below, but we need to rename them so their names aren't
# shadowed by our locals.
_args = args
_decorators = decorators
def wrap(f, *argsArgs, **argsKwargs):
    def newf(self, irc, msg, args, **kwargs):
        state = State('%s.%s' % (self.name(), f.func_name), self.log)
        state.cb = self # This should probably be in State.__init__.
        _args(irc,msg,args, state=state, *argsArgs, **argsKwargs)
        if state.getopts:
            f(self, irc, msg, args, state.getopts, *state.args, **state.kwargs)
        else:
            f(self, irc, msg, args, *state.args, **state.kwargs)

    decorators = argsKwargs.pop('decorators', None)
    if decorators is not None:
        decorators = map(_decorators.__getitem__, decorators)
        for decorator in decorators:
            newf = decorator(newf)
    return utils.changeFunctionName(newf, f.func_name, f.__doc__)


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
