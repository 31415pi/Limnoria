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
import supybot.webutils as webutils
import supybot.callbacks as callbacks
import supybot.structures as structures


###
# Non-arg wrappers -- these just change the behavior of a command without
# changing the arguments given to it.
###

# Thread has to be a non-arg wrapper because by the time we're parsing and
# validating arguments, we're inside the function we'd want to thread.
def thread(f):
    """Makes sure a command spawns a thread when called."""
    def newf(self, irc, msg, args, *L, **kwargs):
        if world.isMainThread():
            t = callbacks.CommandThread(target=irc._callCommand,
                                        args=(f.func_name, self),
                                        kwargs=kwargs)
            t.start()
        else:
            f(self, irc, msg, args, *L, **kwargs)
    return utils.changeFunctionName(newf, f.func_name, f.__doc__)

class UrlSnarfThread(world.SupyThread):
    def __init__(self, *args, **kwargs):
        assert 'url' in kwargs
        kwargs['name'] = 'Thread #%s (for snarfing %s)' % \
                         (world.threadsSpawned, kwargs.pop('url'))
        super(UrlSnarfThread, self).__init__(*args, **kwargs)
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
        return self.irc.reply(*args, **kwargs)

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
# Converters, which take irc, msg, args, and a state object, and build up the
# validated and converted args for the method in state.args.
###

# This is just so we can centralize this, since it may change.
def _int(s):
    base = 10
    if s.startswith('0x'):
        base = 16
        s = s[2:]
    elif s.startswith('0b'):
        base = 2
        s = s[2:]
    elif s.startswith('0') and len(s) > 1:
        base = 8
        s = s[1:]
    try:
        return int(s, base)
    except ValueError:
        if base == 10:
            return int(float(s))
        else:
            raise

def getInt(irc, msg, args, state, type='integer', p=None):
    try:
        i = _int(args[0])
        if p is not None:
            if not p(i):
                raise ValueError
        state.args.append(i)
        del args[0]
    except ValueError:
        irc.errorInvalid(type, args[0])

def getNonInt(irc, msg, args, state, type='non-integer value'):
    try:
        i = _int(args[0])
        irc.errorInvalid(type, args[0])
    except ValueError:
        state.args.append(args.pop(0))

def getFloat(irc, msg, args, state):
    try:
        state.args.append(float(args[0]))
        del args[0]
    except ValueError:
        irc.errorInvalid('floating point number', args[0])

def getPositiveInt(irc, msg, args, state, *L):
    getInt(irc, msg, args, state,
           p=lambda i: i>0, type='positive integer', *L)

def getNonNegativeInt(irc, msg, args, state, *L):
    getInt(irc, msg, args, state,
            p=lambda i: i>=0, type='non-negative integer', *L)

def getId(irc, msg, args, state, kind=None):
    type = 'id'
    if kind is not None:
        type = kind + ' id'
    getInt(irc, msg, args, state, type=type)

def getExpiry(irc, msg, args, state):
    now = int(time.time())
    try:
        expires = _int(args[0])
        if expires:
            expires += now
        state.args.append(expires)
        del args[0]
    except ValueError:
        irc.errorInvalid('number of seconds', args[0])

def getBoolean(irc, msg, args, state):
    try:
        state.args.append(utils.toBool(args[0]))
        del args[0]
    except ValueError:
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

def getSeenNick(irc, msg, args, state, errmsg=None):
    try:
        _ = irc.state.nickToHostmask(args[0])
        state.args.append(args.pop(0))
    except KeyError:
        if errmsg is None:
            errmsg = 'I haven\'t seen %s.' % args[0]
        irc.error(errmsg)


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

def inChannel(irc, msg, args, state):
    if not state.channel:
        getChannel(irc, msg, args, state)
    if state.channel not in irc.state.channels:
        irc.error('I\'m not in %s.' % state.channel, Raise=True)

def callerInChannel(irc, msg, args, state):
    channel = args[0]
    if ircutils.isChannel(channel):
        if channel in irc.state.channels:
            if msg.nick in irc.state.channels[channel].users:
                state.args.append(args.pop(0))
            else:
                irc.error('You must be in %s.' % channel, Raise=True)
        else:
            irc.error('I\'m not in %s.' % channel, Raise=True)
    else:
        irc.errorInvalid('channel', args[0])

def getChannelOrNone(irc, msg, args, state):
    try:
        getChannel(irc, msg, args, state)
    except callbacks.ArgumentError:
        state.args.append(None)

def checkChannelCapability(irc, msg, args, state, cap):
    if not state.channel:
        getChannel(irc, msg, args, state)
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

def private(irc, msg, args, state):
    if ircutils.isChannel(msg.args[0]):
        irc.errorRequiresPrivacy(Raise=True)

def public(irc, msg, args, state, errmsg=None):
    if not ircutils.isChannel(msg.args[0]):
        if errmsg is None:
            errmsg = 'This message must be sent in a channel.'
        irc.error(errmsg, Raise=True)

def checkCapability(irc, msg, args, state, cap):
    cap = ircdb.canonicalCapability(cap)
    if not ircdb.checkCapability(msg.prefix, cap):
##         state.log.warning('%s tried %s without %s.',
##                           msg.prefix, state.name, cap)
        irc.errorNoCapability(cap, Raise=True)

def anything(irc, msg, args, state):
    state.args.append(args.pop(0))

def getUrl(irc, msg, args, state):
    if webutils.urlRe.match(args[0]):
        state.args.append(args.pop(0))
    else:
        irc.errorInvalid('url', args[0])

def getNow(irc, msg, args, state):
    state.args.append(int(time.time()))

def getCommandName(irc, msg, args, state):
    state.args.append(callbacks.canonicalName(args.pop(0)))

def getIp(irc, msg, args, state):
    if utils.isIP(args[0]):
        state.args.append(args.pop(0))
    else:
        irc.errorInvalid('ip', args[0])

def getLetter(irc, msg, args, state):
    if len(args[0]) == 1:
        state.args.append(args.pop(0))
    else:
        irc.errorInvalid('letter', args[0])

def getMatch(irc, msg, args, state, regexp, errmsg):
    m = regexp.search(args[0])
    if m is not None:
        state.args.append(m)
        del args[0]
    else:
        irc.error(errmsg, Raise=True)

def getLiteral(irc, msg, args, state, literals, errmsg=None):
    if isinstance(literals, basestring):
        literals = (literals,)
    if args[0] in literals:
        state.args.append(args.pop(0))
    elif errmsg is not None:
        irc.error(errmsg, Raise=True)
    else:
        raise callbacks.ArgumentError

def getPlugin(irc, msg, args, state, require=True):
    cb = irc.getCallback(args[0])
    if cb is not None:
        state.args.append(cb)
        del args[0]
    elif require:
        irc.errorInvalid('plugin', args[0])
    else:
        state.args.append(None)

wrappers = ircutils.IrcDict({
    'id': getId,
    'ip': getIp,
    'int': getInt,
    'now': getNow,
    'url': getUrl,
    'float': getFloat,
    'nonInt': getNonInt,
    'positiveInt': getPositiveInt,
    'nonNegativeInt': getNonNegativeInt,
    'letter': getLetter,
    'haveOp': getHaveOp,
    'expiry': getExpiry,
    'literal': getLiteral,
    'nick': getNick,
    'seenNick': getSeenNick,
    'channel': getChannel,
    'inChannel': inChannel,
    'callerInChannel': callerInChannel,
    'plugin': getPlugin,
    'boolean': getBoolean,
    'lowered': getLowered,
    'anything': anything,
    'something': getSomething,
    'filename': getSomething,
    'commandName': getCommandName,
    'text': anything,
    'somethingWithoutSpaces': getSomethingNoSpaces,
    'capability': getSomethingNoSpaces,
    'channelDb': getChannelDb,
    'hostmask': getHostmask,
    'banmask': getBanmask,
    'user': getUser,
    'public': public,
    'private': private,
    'otherUser': getOtherUser,
    'regexpMatcher': getMatcher,
    'validChannel': validChannel,
    'regexpReplacer': getReplacer,
    'checkCapability': checkCapability,
    'checkChannelCapability': checkChannelCapability,
})

def addConverter(name, wrapper):
    wrappers[name] = wrapper

def getConverter(name):
    return wrappers[name]

def callConverter(name, irc, msg, args, state, *L):
    getConverter(name)(irc, msg, args, state, *L)

###
# Contexts.  These determine what the nature of conversions is; whether they're
# defaulted, or many of them are allowed, etc.  Contexts should be reusable;
# i.e., they should not maintain state between calls.
###
def contextify(spec):
    if not isinstance(spec, context):
        spec = context(spec)
    return spec

def setDefault(state, default):
    if callable(default):
        state.args.append(default())
    else:
        state.args.append(default)

class context(object):
    def __init__(self, spec):
        self.args = ()
        self.spec = spec # for repr
        if isinstance(spec, tuple):
            assert spec, 'tuple spec must not be empty.'
            self.args = spec[1:]
            self.converter = getConverter(spec[0])
        elif spec is None:
            self.converter = getConverter('anything')
        else:
            assert isinstance(spec, basestring)
            self.args = ()
            self.converter = getConverter(spec)

    def __call__(self, irc, msg, args, state):
        log.debug('args before %r: %r', self, args)
        self.converter(irc, msg, args, state, *self.args)
        log.debug('args after %r: %r', self, args)

    def __repr__(self):
        return '<%s for %s>' % (self.__class__.__name__, self.spec)

class additional(context):
    def __init__(self, spec, default=None):
        self.__parent = super(additional, self)
        self.__parent.__init__(spec)
        self.default = default

    def __call__(self, irc, msg, args, state):
        try:
            self.__parent.__call__(irc, msg, args, state)
        except IndexError:
            log.debug('Got IndexError, returning default.')
            setDefault(state, self.default)

class optional(additional):
    def __call__(self, irc, msg, args, state):
        try:
            super(optional, self).__call__(irc, msg, args, state)
        except (callbacks.ArgumentError, callbacks.Error), e:
            log.debug('Got %s, returning default.', utils.exnToString(e))
            setDefault(state, self.default)

class any(context):
    def __call__(self, irc, msg, args, state):
        originalStateArgs = state.args
        state.args = []
        try:
            try:
                while args:
                    super(any, self).__call__(irc, msg, args, state)
            except IndexError:
                originalStateArgs.append(state.args)
        finally:
            state.args = originalStateArgs

class many(any):
    def __call__(self, irc, msg, args, state):
        context.__call__(self, irc, msg, args, state)
        super(many, self).__call__(irc, msg, args, state)

class getopts(context):
    """The empty string indicates that no argument is taken; None indicates
    that there is no converter for the argument."""
    def __init__(self, getopts):
        self.spec = getopts # for repr
        self.getopts = {}
        self.getoptL = []
        for (name, spec) in getopts.iteritems():
            if spec == '':
                self.getoptL.append(name)
                self.getopts[name] = None
            else:
                self.getoptL.append(name + '=')
                self.getopts[name] = contextify(spec)
        log.debug('getopts: %r', self.getopts)
        log.debug('getoptL: %r', self.getoptL)

    def __call__(self, irc, msg, args, state):
        log.debug('args before %r: %r', self, args)
        (optlist, rest) = getopt.getopt(args, '', self.getoptL)
        getopts = []
        for (opt, arg) in optlist:
            opt = opt[2:] # Strip --
            log.debug('opt: %r, arg: %r', opt, arg)
            context = self.getopts[opt]
            if context is not None:
                st = state.essence()
                context(irc, msg, [arg], st)
                assert len(st.args) == 1
                getopts.append((opt, st.args[0]))
            else:
                getopts.append((opt, True))
        state.args.append(getopts)
        args[:] = rest
        log.debug('args after %r: %r', self, args)



###
# This is our state object, passed to converters along with irc, msg, and args.
###
class State(object):
    log = log
    def __init__(self):
        self.args = []
        self.kwargs = {}
        self.channel = None

    def essence(self):
        st = State()
        for (attr, value) in self.__dict__.iteritems():
            if attr not in ('args', 'kwargs', 'channel'):
                setattr(st, attr, value)
        return st

###
# This is a compiled Spec object.
###
class Spec(object):
    def _state(self, attrs={}):
        st = State()
        st.__dict__.update(attrs)
        return st

    def __init__(self, types, allowExtra=False, combineRest=True):
        self.types = types
        self.allowExtra = allowExtra
        self.combineRest = combineRest
        utils.mapinto(contextify, self.types)

    def __call__(self, irc, msg, args, stateAttrs={}):
        state = self._state(stateAttrs)
        if self.types:
            types = self.types[:]
            while types:
                if len(types) == 1 and self.combineRest and args:
                    break
                context = types.pop(0)
                context(irc, msg, args, state)
            if types and args:
                assert self.combineRest
                args[:] = [' '.join(args)]
                types[0](irc, msg, args, state)
        if args and not self.allowExtra:
            raise callbacks.ArgumentError
        return state

# This is used below, but we need to rename it so its name isn't
# shadowed by our locals.
_decorators = decorators
def wrap(f, specList=[], decorators=None, **kw):
    spec = Spec(specList, **kw)
    def newf(self, irc, msg, args, **kwargs):
        state = spec(irc, msg, args, stateAttrs={'cb': self, 'log': self.log})
        f(self, irc, msg, args, *state.args, **state.kwargs)
    newf = utils.changeFunctionName(newf, f.func_name, f.__doc__)
    if decorators is not None:
        decorators = map(_decorators.__getitem__, decorators)
        for decorator in decorators:
            newf = decorator(newf)
    return newf


__all__ = ['wrap', 'context', 'additional', 'optional', 'any',
           'many', 'getopts', 'getConverter', 'addConverter', 'callConverter']

if world.testing:
    __all__.append('Spec')
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
