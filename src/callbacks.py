###
# Copyright (c) 2002-2005, Jeremiah Fincher
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
This module contains the basic callbacks for handling PRIVMSGs.  Both Privmsg
and PrivmsgRegexp classes are provided; for offering callbacks based on
commands and their arguments (much like *nix command line programs) use the
Privmsg class; for offering callbacks based on regular expressions, use the
PrivmsgRegexp class.  Read their respective docstrings for more information on
how to use them.
"""

import supybot

import re
import copy
import sets
import time
import shlex
import getopt
import string
import inspect
import operator
from cStringIO import StringIO
from itertools import imap, ifilter

import supybot.log as log
import supybot.conf as conf
import supybot.utils as utils
import supybot.world as world
import supybot.ircdb as ircdb
import supybot.irclib as irclib
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.registry as registry

def _addressed(nick, msg, prefixChars=None, nicks=None,
              prefixStrings=None, whenAddressedByNick=None,
              whenAddressedByNickAtEnd=None):
    def get(group):
        if ircutils.isChannel(target):
            group = group.get(target)
        return group()
    def stripPrefixStrings(payload):
        for prefixString in prefixStrings:
            if payload.startswith(prefixString):
                payload = payload[len(prefixString):].lstrip()
        return payload

    assert msg.command == 'PRIVMSG'
    (target, payload) = msg.args
    if not payload:
        return ''
    if prefixChars is None:
        prefixChars = get(conf.supybot.reply.whenAddressedBy.chars)
    if whenAddressedByNick is None:
        whenAddressedByNick = get(conf.supybot.reply.whenAddressedBy.nick)
    if whenAddressedByNickAtEnd is None:
        r = conf.supybot.reply.whenAddressedBy.nick.atEnd
        whenAddressedByNickAtEnd = get(r)
    if prefixStrings is None:
        prefixStrings = get(conf.supybot.reply.whenAddressedBy.strings)
    # We have to check this before nicks -- try "@google supybot" with supybot
    # and whenAddressedBy.nick.atEnd on to see why.
    if any(payload.startswith, prefixStrings):
        return stripPrefixStrings(payload)
    elif payload[0] in prefixChars:
        return payload[1:].strip()
    if nicks is None:
        nicks = get(conf.supybot.reply.whenAddressedBy.nicks)
        nicks = map(ircutils.toLower, nicks)
    else:
        nicks = list(nicks) # Just in case.
    nicks.insert(0, ircutils.toLower(nick))
    # Ok, let's see if it's a private message.
    if ircutils.nickEqual(target, nick):
        payload = stripPrefixStrings(payload)
        while payload and payload[0] in prefixChars:
            payload = payload[1:].lstrip()
        return payload
    # Ok, not private.  Does it start with our nick?
    elif whenAddressedByNick:
        for nick in nicks:
            lowered = ircutils.toLower(payload)
            if lowered.startswith(nick):
                try:
                    (maybeNick, rest) = payload.split(None, 1)
                    toContinue = False
                    while not ircutils.isNick(maybeNick, strictRfc=True):
                        if maybeNick[-1].isalnum():
                            toContinue = True
                            break
                        maybeNick = maybeNick[:-1]
                    if toContinue:
                        continue
                    if ircutils.nickEqual(maybeNick, nick):
                        return rest
                    else:
                        continue
                except ValueError: # split didn't work.
                    continue
            elif whenAddressedByNickAtEnd and lowered.endswith(nick):
                rest = payload[:-len(nick)]
                possiblePayload = rest.rstrip(' \t,;')
                if possiblePayload != rest:
                    # There should be some separator between the nick and the
                    # previous alphanumeric character.
                    return possiblePayload
    if conf.supybot.reply.whenNotAddressed():
        return payload
    else:
        return ''

def addressed(nick, msg, **kwargs):
    """If msg is addressed to 'name', returns the portion after the address.
    Otherwise returns the empty string.
    """
    payload = msg.addressed
    if payload is not None:
        return payload
    else:
        payload = _addressed(nick, msg, **kwargs)
        msg.tag('addressed', payload)
        return payload

def canonicalName(command):
    """Turn a command into its canonical form.

    Currently, this makes everything lowercase and removes all dashes and
    underscores.
    """
    if isinstance(command, unicode):
        command = command.encode('utf-8')
    special = '\t -_'
    reAppend = ''
    while command and command[-1] in special:
        reAppend = command[-1] + reAppend
        command = command[:-1]
    return command.translate(utils.str.chars, special).lower() + reAppend

def reply(msg, s, prefixName=None, private=None,
          notice=None, to=None, action=None, error=False):
    msg.tag('repliedTo')
    # Ok, let's make the target:
    # XXX This isn't entirely right.  Consider to=#foo, private=True.
    target = ircutils.replyTo(msg)
    if ircutils.isChannel(target):
        channel = target
    else:
        channel = None
    if notice is None:
        notice = conf.get(conf.supybot.reply.withNotice, channel)
    if private is None:
        private = conf.get(conf.supybot.reply.inPrivate, channel)
    if prefixName is None:
        prefixName = conf.get(conf.supybot.reply.withNickPrefix, channel)
    if error:
        notice =conf.get(conf.supybot.reply.error.withNotice, channel) or notice
        private=conf.get(conf.supybot.reply.error.inPrivate, channel) or private
        s = 'Error: ' + s
    if private:
        prefixName = False
        if to is None:
            target = msg.nick
        else:
            target = to
    if to is None:
        to = msg.nick
    # Ok, now let's make the payload:
    s = ircutils.safeArgument(s)
    if not s and not action:
        s = 'Error: I tried to send you an empty message.'
    if prefixName and ircutils.isChannel(target):
        # Let's may sure we don't do, "#channel: foo.".
        if not ircutils.isChannel(to):
            s = '%s: %s' % (to, s)
    if not ircutils.isChannel(target):
        if conf.supybot.reply.withNoticeWhenPrivate():
            notice = True
    # And now, let's decide whether it's a PRIVMSG or a NOTICE.
    msgmaker = ircmsgs.privmsg
    if notice:
        msgmaker = ircmsgs.notice
    # We don't use elif here because actions can't be sent as NOTICEs.
    if action:
        msgmaker = ircmsgs.action
    # Finally, we'll return the actual message.
    ret = msgmaker(target, s)
    ret.tag('inReplyTo', msg)
    return ret

def error(msg, s, **kwargs):
    """Makes an error reply to msg with the appropriate error payload."""
    kwargs['error'] = True
    msg.tag('isError')
    return reply(msg, s, **kwargs)

def getHelp(method, name=None):
    if name is None:
        name = method.__name__
    doclines = method.__doc__.splitlines()
    s = '%s %s' % (name, doclines.pop(0))
    if doclines:
        help = ' '.join(doclines)
        s = '(%s) -- %s' % (ircutils.bold(s), help)
    return utils.str.normalizeWhitespace(s)

def getSyntax(method, name=None):
    if name is None:
        name = method.__name__
    doclines = method.__doc__.splitlines()
    return '%s %s' % (name, doclines[0])

class Error(Exception):
    """Generic class for errors in Privmsg callbacks."""
    pass

class ArgumentError(Error):
    """The bot replies with a help message when this is raised."""
    pass

class Tokenizer(object):
    # This will be used as a global environment to evaluate strings in.
    # Evaluation is, of course, necessary in order to allowed escaped
    # characters to be properly handled.
    #
    # These are the characters valid in a token.  Everything printable except
    # double-quote, left-bracket, and right-bracket.
    validChars = utils.str.chars.translate(utils.str.chars, '\x00\r\n \t')
    def __init__(self, brackets='', pipe=False, quotes='"'):
        if brackets:
            self.validChars=self.validChars.translate(utils.str.chars, brackets)
            self.left = brackets[0]
            self.right = brackets[1]
        else:
            self.left = ''
            self.right = ''
        self.pipe = pipe
        if self.pipe:
            self.validChars = self.validChars.translate(utils.str.chars, '|')
        self.quotes = quotes
        self.validChars = self.validChars.translate(utils.str.chars, quotes)


    def _handleToken(self, token):
        if token[0] == token[-1] and token[0] in self.quotes:
            token = token[1:-1]
            token = token.decode('string-escape')
        return token

    def _insideBrackets(self, lexer):
        ret = []
        while True:
            token = lexer.get_token()
            if not token:
                raise SyntaxError, 'Missing "%s".  You may want to ' \
                                   'quote your arguments with double ' \
                                   'quotes in order to prevent extra ' \
                                   'brackets from being evaluated ' \
                                   'as nested commands.' % self.right
            elif token == self.right:
                return ret
            elif token == self.left:
                ret.append(self._insideBrackets(lexer))
            else:
                ret.append(self._handleToken(token))
            firstToken = False
        return ret

    def tokenize(self, s):
        lexer = shlex.shlex(StringIO(s))
        lexer.commenters = ''
        lexer.quotes = self.quotes
        lexer.wordchars = self.validChars
        args = []
        ends = []
        while True:
            token = lexer.get_token()
            if not token:
                break
            elif token == '|' and self.pipe:
                # The "and self.pipe" might seem redundant here, but it's there
                # for strings like 'foo | bar', where a pipe stands alone as a
                # token, but shouldn't be treated specially.
                if not args:
                    raise SyntaxError, '"|" with nothing preceding.  I ' \
                                       'obviously can\'t do a pipe with ' \
                                       'nothing before the |.'
                ends.append(args)
                args = []
            elif token == self.left:
                args.append(self._insideBrackets(lexer))
            elif token == self.right:
                raise SyntaxError, 'Spurious "%s".  You may want to ' \
                                   'quote your arguments with double ' \
                                   'quotes in order to prevent extra ' \
                                   'brackets from being evaluated ' \
                                   'as nested commands.' % self.right
            else:
                args.append(self._handleToken(token))
        if ends:
            if not args:
                raise SyntaxError, '"|" with nothing following.  I ' \
                                   'obviously can\'t do a pipe with ' \
                                   'nothing before the |.'
            args.append(ends.pop())
            while ends:
                args[-1].append(ends.pop())
        return args

def tokenize(s, channel=None):
    """A utility function to create a Tokenizer and tokenize a string."""
    pipe = False
    brackets = ''
    nested = conf.supybot.commands.nested
    if nested():
        brackets = conf.get(nested.brackets, channel)
        if conf.get(nested.pipeSyntax, channel): # No nesting, no pipe.
            pipe = True
    quotes = conf.get(conf.supybot.commands.quotes, channel)
    start = time.time()
    try:
        ret = Tokenizer(brackets=brackets,pipe=pipe,quotes=quotes).tokenize(s)
        log.stat('tokenize took %s seconds.' % (time.time() - start))
        return ret
    except ValueError, e:
        raise SyntaxError, str(e)

def getCommands(tokens):
    """Given tokens as output by tokenize, returns the command names."""
    L = []
    if tokens and isinstance(tokens, list):
        L.append(tokens[0])
        for elt in tokens:
            L.extend(getCommands(elt))
    return L

def findCallbackForCommand(irc, name):
    """Given a command name and an Irc object, returns a list of callbacks that
    commandName is in."""
    L = []
    name = canonicalName(name)
    for callback in irc.callbacks:
        if not isinstance(callback, PrivmsgRegexp):
            if hasattr(callback, 'isCommand'):
                if callback.isCommand(name):
                    L.append(callback)
    return L

def formatArgumentError(method, name=None):
    if name is None:
        name = method.__name__
    if hasattr(method, '__doc__') and method.__doc__:
        if conf.get(conf.supybot.reply.showSimpleSyntax, dynamic.channel):
            return getSyntax(method, name=name)
        else:
            return getHelp(method, name=name)
    else:
        return 'Invalid arguments for %s.' % method.__name__

def checkCommandCapability(msg, cb, commandName):
    assert isinstance(commandName, basestring), commandName
    plugin = cb.name().lower()
    pluginCommand = '%s.%s' % (plugin, commandName)
    def checkCapability(capability):
        assert ircdb.isAntiCapability(capability)
        if ircdb.checkCapability(msg.prefix, capability):
            log.info('Preventing %s from calling %s because of %s.',
                     msg.prefix, pluginCommand, capability)
            raise RuntimeError, capability
    try:
        antiPlugin = ircdb.makeAntiCapability(plugin)
        antiCommand = ircdb.makeAntiCapability(commandName)
        antiPluginCommand = ircdb.makeAntiCapability(pluginCommand)
        checkCapability(antiPlugin)
        checkCapability(antiCommand)
        checkCapability(antiPluginCommand)
        checkAtEnd = [commandName, pluginCommand]
        default = conf.supybot.capabilities.default()
        if ircutils.isChannel(msg.args[0]):
            channel = msg.args[0]
            checkCapability(ircdb.makeChannelCapability(channel, antiCommand))
            checkCapability(ircdb.makeChannelCapability(channel, antiPlugin))
            checkCapability(ircdb.makeChannelCapability(channel,
                                                        antiPluginCommand))
            chanPlugin = ircdb.makeChannelCapability(channel, plugin)
            chanCommand = ircdb.makeChannelCapability(channel, commandName)
            chanPluginCommand = ircdb.makeChannelCapability(channel,
                                                            pluginCommand)
            checkAtEnd += [chanCommand, chanPlugin, chanPluginCommand]
            default &= ircdb.channels.getChannel(channel).defaultAllow
        return not (default or \
                    any(lambda x: ircdb.checkCapability(msg.prefix, x),
                        checkAtEnd))
    except RuntimeError, e:
        s = ircdb.unAntiCapability(str(e))
        return s


class RichReplyMethods(object):
    """This is a mixin so these replies need only be defined once.  It operates
    under several assumptions, including the fact that 'self' is an Irc object
    of some sort and there is a self.msg that is an IrcMsg."""
    def __makeReply(self, prefix, s):
        if s:
            s = '%s  %s' % (prefix, s)
        else:
            s = prefix
        return ircutils.standardSubstitute(self, self.msg, s)

    def _getConfig(self, wrapper):
        return conf.get(wrapper, self.msg.args[0])

    def replySuccess(self, s='', **kwargs):
        v = self._getConfig(conf.supybot.replies.success)
        if v:
            s = self.__makeReply(v, s)
            return self.reply(s, **kwargs)
        else:
            self.noReply()

    def replyError(self, s='', **kwargs):
        v = self._getConfig(conf.supybot.replies.error)
        s = self.__makeReply(v, s)
        return self.reply(s, **kwargs)

    def replies(self, L, prefixer=None, joiner=None,
                onlyPrefixFirst=False, **kwargs):
        if prefixer is None:
            prefixer = ''
        if joiner is None:
            joiner = utils.str.commaAndify
        if isinstance(prefixer, basestring):
            prefixer = prefixer.__add__
        if isinstance(joiner, basestring):
            joiner = joiner.join
        if conf.supybot.reply.oneToOne():
            return self.reply(prefixer(joiner(L)), **kwargs)
        else:
            msg = None
            first = True
            for s in L:
                if onlyPrefixFirst:
                    if first:
                        first = False
                        msg = self.reply(prefixer(s), **kwargs)
                    else:
                        msg = self.reply(s, **kwargs)
                else:
                    msg = self.reply(prefixer(s), **kwargs)
            return msg

    def noReply(self):
        self.msg.tag('repliedTo')

    def _error(self, s, Raise=False, **kwargs):
        if Raise:
            raise Error, s
        else:
            return self.error(s, **kwargs)

    def errorNoCapability(self, capability, s='', **kwargs):
        if 'Raise' not in kwargs:
            kwargs['Raise'] = True
        if isinstance(capability, basestring): # checkCommandCapability!
            log.warning('Denying %s for lacking %s capability.',
                        self.msg.prefix, utils.str.quoted(capability))
            if not self._getConfig(conf.supybot.reply.error.noCapability):
                v = self._getConfig(conf.supybot.replies.noCapability)
                s = self.__makeReply(v % capability, s)
                return self._error(s, **kwargs)
            else:
                log.debug('Not sending capability error, '
                          'supybot.reply.error.noCapability is False.')
        else:
            log.warning('Denying %s for some unspecified capability '
                        '(or a default).', self.msg.prefix)
            v = self._getConfig(conf.supybot.replies.genericNoCapability)
            return self._error(self.__makeReply(v, s), **kwargs)

    def errorPossibleBug(self, s='', **kwargs):
        v = self._getConfig(conf.supybot.replies.possibleBug)
        if s:
            s += '  (%s)' % v
        else:
            s = v
        return self._error(s, **kwargs)

    def errorNotRegistered(self, s='', **kwargs):
        v = self._getConfig(conf.supybot.replies.notRegistered)
        return self._error(self.__makeReply(v, s), **kwargs)

    def errorNoUser(self, s='', name='that user', **kwargs):
        if 'Raise' not in kwargs:
            kwargs['Raise'] = True
        v = self._getConfig(conf.supybot.replies.noUser)
        try:
            v = v % name
        except TypeError:
            log.warning('supybot.replies.noUser should have one "%s" in it.')
        return self._error(self.__makeReply(v, s), **kwargs)

    def errorRequiresPrivacy(self, s='', **kwargs):
        v = self._getConfig(conf.supybot.replies.requiresPrivacy)
        return self._error(self.__makeReply(v, s), **kwargs)

    def errorInvalid(self, what, given=None, s='', repr=True, **kwargs):
        if given is not None:
            if repr:
                given = _repr(given)
            else:
                given = '"%s"' % given
            v = '%s is not a valid %s.' % (given, what)
        else:
            v = 'That\'s not a valid %s.' % what
        if 'Raise' not in kwargs:
            kwargs['Raise'] = True
        return self._error(self.__makeReply(v, s), **kwargs)

_repr = repr

class IrcObjectProxy(RichReplyMethods):
    "A proxy object to allow proper nested of commands (even threaded ones)."
    def __init__(self, irc, msg, args, nested=0):
        log.verbose('IrcObjectProxy.__init__: %s' % args)
        assert isinstance(args, list), 'Args should be a list, not a string.'
        self.irc = irc
        self.msg = msg
        self.nested = nested
        if not self.nested and isinstance(irc, self.__class__):
            # This is for plugins that indirectly spawn a Proxy, like Alias.
            self.nested += irc.nested
        maxNesting = conf.supybot.commands.nested.maximum()
        if maxNesting and self.nested > maxNesting:
            log.warning('%s attempted more than %s levels of nesting.',
                        self.msg.prefix, maxNesting)
            return self.error('You\'ve attempted more nesting than is '
                              'currently allowed on this bot.')
        # The deepcopy here is necessary for Scheduler; it re-runs already
        # tokenized commands.
        self.args = copy.deepcopy(args)
        self.counter = 0
        self.commandMethod = None # Used in error.
        self._resetReplyAttributes()
        if not args:
            self.finalEvaled = True
            self._callInvalidCommands()
        else:
            self.finalEvaled = False
            world.commandsProcessed += 1
            self.evalArgs()

    def __eq__(self, other):
        return other == self.getRealIrc()

    def __hash__(self):
        return hash(self.getRealIrc())

    def _resetReplyAttributes(self):
        self.to = None
        self.action = None
        self.notice = None
        self.private = None
        self.noLengthCheck = None
        if ircutils.isChannel(self.msg.args[0]):
            self.prefixName = conf.get(conf.supybot.reply.withNickPrefix,
                                       self.msg.args[0])
        else:
            self.prefixName = conf.supybot.reply.withNickPrefix()

    def evalArgs(self):
        while self.counter < len(self.args):
            if isinstance(self.args[self.counter], basestring):
                self.counter += 1
            else:
                self.__class__(self, self.msg,
                               self.args[self.counter], nested=self.nested+1)
                return
        self.finalEval()

    def _callTokenizedCommands(self):
        log.verbose('Calling tokenizedCommands.')
        for cb in self.irc.callbacks:
            if hasattr(cb, 'tokenizedCommand'):
                log.verbose('Trying to call %s.tokenizedCommand.', cb.name())
                self._callTokenizedCommand(cb)
                if self.msg.repliedTo:
                    log.verbose('Done calling tokenizedCommands: %s.',cb.name())
                    return

    def _callTokenizedCommand(self, cb):
        try:
            cb.tokenizedCommand(self, self.msg, self.args)
        except Error, e:
            return self.error(str(e))
        except Exception, e:
            log.exception('Uncaught exception in %s.tokenizedCommand.' %
                          cb.name())

    def _callInvalidCommands(self):
        log.debug('Calling invalidCommands.')
        for cb in self.irc.callbacks:
            if hasattr(cb, 'invalidCommand'):
                log.debug('Trying to call %s.invalidCommand.' % cb.name())
                self._callInvalidCommand(cb)
                if self.msg.repliedTo:
                    log.debug('Done calling invalidCommands: %s.',cb.name())
                    return

    def _callInvalidCommand(self, cb):
        try:
            cb.invalidCommand(self, self.msg, self.args)
        except Error, e:
            return self.error(str(e))
        except Exception, e:
            log.exception('Uncaught exception in %s.invalidCommand.'%
                          cb.name())

    def _callCommand(self, name, cb):
        try:
            self.commandMethod = cb.getCommand(name)
            if not world.isMainThread():
                # If we're a threaded command, we may not reply quickly enough
                # to prevent regexp stuff from running.  So we do this to make
                # sure it doesn't happen.  Neither way (tagging or not tagging)
                # is perfect, but this seems better than not tagging.
                self.msg.tag('repliedTo')
            try:
                cb.callCommand(name, self, self.msg, self.args)
            except Error, e:
                self.error(str(e))
            except Exception, e:
                cb.log.exception('Uncaught exception in %s.%s:',
                                 cb.name(), name)
                if conf.supybot.reply.error.detailed():
                    return self.error(utils.exnToString(e))
                else:
                    return self.replyError()
        finally:
            self.commandMethod = None

    def findCallbackForCommand(self, command):
        cbs = findCallbackForCommand(self, command)
        if len(cbs) > 1:
            command = canonicalName(command)
            # Check for whether it's the name of a callback; their dispatchers
            # need to get precedence.
            for cb in cbs:
                if canonicalName(cb.name()) == command:
                    return [cb]
            try:
                # Check if there's a configured defaultPlugin -- the user gets
                # precedence in that case.
                defaultPlugins = conf.supybot.commands.defaultPlugins
                plugin = defaultPlugins.get(command)()
                if plugin and plugin != '(Unused)':
                    cb = self.irc.getCallback(plugin)
                    if cb is None:
                        log.warning('%s is set as a default plugin '
                                    'for %s, but it isn\'t loaded.',
                                    plugin, command)
                        raise registry.NonExistentRegistryEntry
                    else:
                        return [cb]
            except registry.NonExistentRegistryEntry, e:
                # Check for whether it's a src/ plugin; they get precedence.
                important = []
                importantPlugins = defaultPlugins.importantPlugins()
                for cb in cbs:
                    if cb.name() in importantPlugins:
                        # We do this to handle multiple importants matching.
                        important.append(cb)
                if len(important) == 1:
                    return important
        return cbs

    def finalEval(self):
        assert not self.finalEvaled, 'finalEval called twice.'
        self.finalEvaled = True
        command = self.args[0]
        cbs = self.findCallbackForCommand(command)
        if not cbs:
            # Normal command not found, let's go for the specialties now.
            # First, check for addressedRegexps -- they take precedence over
            # tokenizedCommands.
            for cb in self.irc.callbacks:
                if isinstance(cb, PrivmsgCommandAndRegexp):
                    payload = addressed(self.irc.nick, self.msg)
                    for (r, name) in cb.addressedRes:
                        if r.search(payload):
                            log.debug('Skipping tokenizedCommands: %s.%s',
                                      cb.name(), name)
                            return
            # Now we call tokenizedCommands.
            self._callTokenizedCommands()
            # Return if we've replied.
            if self.msg.repliedTo:
                log.debug('Not calling invalidCommands, '
                          'tokenizedCommands replied.')
                return
            # Now we check for regexp commands, which override invalidCommand.
            for cb in self.irc.callbacks:
                if isinstance(cb, PrivmsgRegexp):
                    for (r, name) in cb.res:
                        if r.search(self.msg.args[1]):
                            log.debug('Skipping invalidCommand: %s.%s',
                                      cb.name(), name)
                            return
                elif isinstance(cb, PrivmsgCommandAndRegexp):
                    for (r, name) in cb.res:
                        if r.search(self.msg.args[1]):
                            log.debug('Skipping invalidCommand: %s.%s',
                                      cb.name(), name)
                            return
            # No matching regexp commands, now we do invalidCommands.
            self._callInvalidCommands()
        elif len(cbs) > 1:
            names = sorted([cb.name() for cb in cbs])
            return self.error('The command %s is available in the %s plugins.  '
                              'Please specify the plugin whose command you '
                              'wish to call by using its name as a command '
                              'before %s.' %
                              (command, utils.str.commaAndify(names), command))
        else:
            cb = cbs[0]
            del self.args[0] # Remove the command.
            if world.isMainThread() and \
               (cb.threaded or conf.supybot.debug.threadAllCommands()):
                t = CommandThread(target=self._callCommand,
                                  args=(command, cb))
                t.start()
            else:
                self._callCommand(command, cb)

    def reply(self, s, noLengthCheck=False, prefixName=None,
              action=None, private=None, notice=None, to=None, msg=None):
        """reply(s) -> replies to msg with s

        Keyword arguments:
          noLengthCheck=False: True if the length shouldn't be checked
                               (used for 'more' handling)
          prefixName=True:     False if the nick shouldn't be prefixed to the
                               reply.
          action=False:        True if the reply should be an action.
          private=False:       True if the reply should be in private.
          notice=False:        True if the reply should be noticed when the
                               bot is configured to do so.
          to=<nick|channel>:   The nick or channel the reply should go to.
                               Defaults to msg.args[0] (or msg.nick if private)
        """
        # These use and or or based on whether or not they default to True or
        # False.  Those that default to True use and; those that default to
        # False use or.
        assert not isinstance(s, ircmsgs.IrcMsg), \
               'Old code alert: there is no longer a "msg" argument to reply.'
        if msg is None:
            msg = self.msg
        if prefixName is not None:
            self.prefixName = prefixName
        if action is not None:
            self.action = self.action or action
            self.prefixName = False
        if notice is not None:
            self.notice = self.notice or notice
        if private is not None:
            self.private = self.private or private
        if to is not None:
            self.to = self.to or to
        # action=True implies noLengthCheck=True and prefixName=False
        self.noLengthCheck=noLengthCheck or self.noLengthCheck or self.action
        target = self.private and self.to or self.msg.args[0]
        if self.finalEvaled:
            try:
                if not isinstance(self.irc, irclib.Irc):
                    s = s[:conf.supybot.reply.maximumLength()]
                    return self.irc.reply(s, to=self.to,
                                          notice=self.notice,
                                          action=self.action,
                                          private=self.private,
                                          prefixName=self.prefixName,
                                          noLengthCheck=self.noLengthCheck)
                elif self.noLengthCheck:
                    # noLengthCheck only matters to IrcObjectProxy, so it's not
                    # used here.  Just in case you were wondering.
                    m = reply(msg, s, to=self.to,
                              notice=self.notice,
                              action=self.action,
                              private=self.private,
                              prefixName=self.prefixName)
                    self.irc.queueMsg(m)
                    return m
                else:
                    s = ircutils.safeArgument(s)
                    allowedLength = conf.get(conf.supybot.reply.mores.length,
                                             target)
                    if not allowedLength: # 0 indicates this.
                        allowedLength = 450 - len(self.irc.prefix)
                        allowedLength -= len(msg.nick)
                    maximumMores = conf.get(conf.supybot.reply.mores.maximum,
                                            target)
                    maximumLength = allowedLength * maximumMores
                    if len(s) > maximumLength:
                        log.warning('Truncating to %s bytes from %s bytes.',
                                    maximumLength, len(s))
                        s = s[:maximumLength]
                    if len(s) < allowedLength or \
                       not conf.get(conf.supybot.reply.mores, target):
                        # In case we're truncating, we add 20 to allowedLength,
                        # because our allowedLength is shortened for the
                        # "(XX more messages)" trailer.
                        s = s[:allowedLength+20]
                        # There's no need for action=self.action here because
                        # action implies noLengthCheck, which has already been
                        # handled.  Let's stick an assert in here just in case.
                        assert not self.action
                        m = reply(msg, s, to=self.to,
                                  notice=self.notice,
                                  private=self.private,
                                  prefixName=self.prefixName)
                        self.irc.queueMsg(m)
                        return m
                    msgs = ircutils.wrap(s, allowedLength)
                    msgs.reverse()
                    instant = conf.get(conf.supybot.reply.mores.instant,target)
                    while instant > 1 and msgs:
                        instant -= 1
                        response = msgs.pop()
                        m = reply(msg, response, to=self.to,
                                  notice=self.notice,
                                  private=self.private,
                                  prefixName=self.prefixName)
                        self.irc.queueMsg(m)
                        # XXX We should somehow allow these to be returned, but
                        #     until someone complains, we'll be fine :)  We
                        #     can't return from here, though, for obvious
                        #     reasons.
                        # return m
                    if not msgs:
                        return
                    response = msgs.pop()
                    if msgs:
                        n = ircutils.bold('(%s)')
                        n %= utils.str.nItems(len(msgs), 'message', 'more')
                        response = '%s %s' % (response, n)
                    prefix = msg.prefix
                    if self.to and ircutils.isNick(self.to):
                        try:
                            state = self.getRealIrc().state
                            prefix = state.nickToHostmask(self.to)
                        except KeyError:
                            pass # We'll leave it as it is.
                    mask = prefix.split('!', 1)[1]
                    Privmsg._mores[mask] = msgs
                    public = ircutils.isChannel(msg.args[0])
                    private = self.private or not public
                    Privmsg._mores[msg.nick] = (private, msgs)
                    m = reply(msg, response, to=self.to,
                                            action=self.action,
                                            notice=self.notice,
                                            private=self.private,
                                            prefixName=self.prefixName)
                    self.irc.queueMsg(m)
                    return m
            finally:
                self._resetReplyAttributes()
        else:
            self.args[self.counter] = s
            self.evalArgs()

    def error(self, s='', Raise=False, **kwargs):
        if Raise:
            if s:
                raise Error, s
            else:
                raise ArgumentError
        if s:
            if not isinstance(self.irc, irclib.Irc):
                return self.irc.error(s, **kwargs)
            else:
                m = error(self.msg, s, **kwargs)
                self.irc.queueMsg(m)
                return m
        else:
            if self.commandMethod is not None:
                # We can recurse here because it only gets called once.
                return self.reply(formatArgumentError(self.commandMethod),
                                  **kwargs)
            else:
                raise ArgumentError # We shouldn't get here, but just in case.

    def getRealIrc(self):
        """Returns the real irclib.Irc object underlying this proxy chain."""
        if isinstance(self.irc, irclib.Irc):
            return self.irc
        else:
            return self.irc.getRealIrc()

    def __getattr__(self, attr):
        return getattr(self.irc, attr)


class CommandThread(world.SupyThread):
    """Just does some extra logging and error-recovery for commands that need
    to run in threads.
    """
    def __init__(self, target=None, args=(), kwargs={}):
        (self.name, self.cb) = args
        self.__parent = super(CommandThread, self)
        self.command = self.cb.getCommand(self.name)
        threadName = 'Thread #%s (for %s.%s)' % (world.threadsSpawned,
                                                 self.cb.name(), self.name)
        log.debug('Spawning thread %s' % threadName)
        self.__parent.__init__(target=target, name=threadName,
                               args=args, kwargs=kwargs)
        self.setDaemon(True)
        self.originalThreaded = self.cb.threaded
        self.cb.threaded = True

    def run(self):
        try:
            self.__parent.run()
        finally:
            self.cb.threaded = self.originalThreaded


class CanonicalString(registry.NormalizedString):
    def normalize(self, s):
        return canonicalName(s)

class CanonicalNameSet(utils.NormalizingSet):
    def normalize(self, s):
        return canonicalName(s)

class CanonicalNameDict(utils.InsensitivePreservingDict):
    def key(self, s):
        return canonicalName(s)

class Disabled(registry.SpaceSeparatedListOf):
    sorted = True
    Value = CanonicalString
    List = CanonicalNameSet

conf.registerGlobalValue(conf.supybot.commands, 'disabled',
    Disabled([], """Determines what commands are currently disabled.  Such
    commands will not appear in command lists, etc.  They will appear not even
    to exist."""))

class DisabledCommands(object):
    def __init__(self):
        self.d = CanonicalNameDict()
        for name in conf.supybot.commands.disabled():
            if '.' in name:
                (plugin, command) = name.split('.', 1)
                if command in self.d:
                    if self.d[command] is not None:
                        self.d[command].add(plugin)
                else:
                    self.d[command] = CanonicalNameSet([plugin])
            else:
                self.d[name] = None

    def disabled(self, command, plugin=None):
        if command in self.d:
            if self.d[command] is None:
                return True
            elif plugin in self.d[command]:
                return True
        return False

    def add(self, command, plugin=None):
        if plugin is None:
            self.d[command] = None
        else:
            if command in self.d:
                if self.d[command] is not None:
                    self.d[command].add(plugin)
            else:
                self.d[command] = CanonicalNameSet([plugin])

    def remove(self, command, plugin=None):
        if plugin is None:
            del self.d[command]
        else:
            if self.d[command] is not None:
                self.d[command].remove(plugin)

class Privmsg(irclib.IrcCallback):
    """Base class for all Privmsg handlers."""
    # For awhile, a comment stood here to say, "Eventually callCommand."  But
    # that's wrong, because we can't do generic error handling in this
    # callCommand -- plugins need to be able to override callCommand and do
    # error handling there (see the Http plugin for an example).
    __firewalled__ = {'isCommand': None,}
                      # 'invalidCommand': None} # Gotta raise callbacks.Error.
    public = True
    alwaysCall = ()
    threaded = False
    noIgnore = False
    Proxy = IrcObjectProxy
    commandArgs = ['self', 'irc', 'msg', 'args']
    # These must be class-scope, so all plugins use the same one.
    _mores = ircutils.IrcDict()
    _disabled = DisabledCommands()
    def isDisabled(self, command):
        return self._disabled.disabled(command, self.name())

    def __init__(self):
        self.__parent = super(Privmsg, self)
        myName = self.name()
        self.log = log.getPluginLogger(myName)
        # We can't do this because of the specialness that Owner and Misc do.
        # I guess plugin authors will have to get the capitalization right.
        # self.callAfter = map(str.lower, self.callAfter)
        # self.callBefore = map(str.lower, self.callBefore)
        ### Setup the dispatcher command.
        canonicalname = canonicalName(myName)
        self._original = getattr(self, canonicalname, None)
        docstring = """<command> [<args> ...]

        Command dispatcher for the %s plugin.  Use 'list %s' to see the
        commands provided by this plugin.  Use 'config list plugins.%s' to see
        the configuration values for this plugin.  In most cases this dispatcher
        command is unnecessary; in cases where more than one plugin defines a
        given command, use this command to tell the bot which plugin's command
        to use.""" % (myName, myName, myName)
        def dispatcher(self, irc, msg, args):
            def handleBadArgs():
                if self._original:
                    self._original(irc, msg, args)
                else:
                    if args:
                        irc.error('%s is not a valid command in this plugin.' %
                                  args[0])
                    else:
                        irc.error()
            if args:
                name = canonicalName(args[0])
                if name == canonicalName(self.name()):
                    handleBadArgs()
                elif self.isCommand(name):
                    cap = checkCommandCapability(msg, self, name)
                    if cap:
                        irc.errorNoCapability(cap)
                        return
                    del args[0]
                    method = getattr(self, name)
                    try:
                        realname = '%s.%s' % (canonicalname, name)
                        method(irc, msg, args)
                    except (getopt.GetoptError, ArgumentError):
                        irc.reply(formatArgumentError(method, name))
                else:
                    handleBadArgs()
            else:
                handleBadArgs()
        dispatcher = utils.changeFunctionName(dispatcher, canonicalname)
        if self._original:
            dispatcher.__doc__ = self._original.__doc__
            dispatcher.isDispatcher = False
        else:
            dispatcher.__doc__ = docstring
            dispatcher.isDispatcher = True
        setattr(self.__class__, canonicalname, dispatcher)

    def __call__(self, irc, msg):
        # This is for later dynamic scoping.
        if msg.command == 'PRIVMSG':
            if self.noIgnore or not ircdb.checkIgnored(msg.prefix,msg.args[0]):
                self.__parent.__call__(irc, msg)
        else:
            self.__parent.__call__(irc, msg)

    def isCommand(self, name):
        """Returns whether a given method name is a command in this plugin."""
        # This function is ugly, but I don't want users to call methods like
        # doPrivmsg or __init__ or whatever, and this is good to stop them.

        # Don't canonicalize this name: consider outFilter(self, irc, msg).
        # name = canonicalName(name)
        if self.isDisabled(name):
            return False
        if hasattr(self, name):
            method = getattr(self, name)
            if inspect.ismethod(method):
                code = method.im_func.func_code
                return inspect.getargs(code)[0] == self.commandArgs
            else:
                return False
        else:
            return False

    def getCommand(self, name):
        """Gets the given command from this plugin."""
        name = canonicalName(name)
        assert self.isCommand(name), '%s is not a command.' % \
                                     utils.str.quoted(name)
        return getattr(self, name)

    def callCommand(self, name, irc, msg, *L, **kwargs):
        checkCapabilities = kwargs.pop('checkCapabilities', True)
        if checkCapabilities:
            cap = checkCommandCapability(msg, self, name)
            if cap:
                irc.errorNoCapability(cap)
                return
        method = self.getCommand(name)
        assert L, 'Odd, nothing in L.  This can\'t happen.'
        self.log.info('%s.%s called by %s.', self.name(), name, msg.prefix)
        self.log.debug('args: %s', L[0])
        start = time.time()
        try:
            method(irc, msg, *L)
        except (getopt.GetoptError, ArgumentError):
            irc.reply(formatArgumentError(method, name=name))
        except (SyntaxError, Error), e:
            self.log.debug('Error return: %s', utils.exnToString(e))
            irc.error(str(e))
        elapsed = time.time() - start
        log.stat('%s took %s seconds', name, elapsed)

    def getCommandHelp(self, name):
        name = canonicalName(name)
        assert self.isCommand(name), \
               '%s is not a command in %s.' % (name, self.name())
        command = self.getCommand(name)
        if hasattr(command, 'isDispatcher') and \
           command.isDispatcher and self.__doc__:
            return utils.str.normalizeWhitespace(self.__doc__)
        elif hasattr(command, '__doc__'):
            return getHelp(command)
        else:
            return 'The %s command has no help.' % utils.str.quoted(name)

    def registryValue(self, name, channel=None, value=True):
        plugin = self.name()
        group = conf.supybot.plugins.get(plugin)
        names = registry.split(name)
        for name in names:
            group = group.get(name)
        if channel is not None:
            if ircutils.isChannel(channel):
                group = group.get(channel)
            else:
                self.log.debug('registryValue got channel=%r', channel)
        if value:
            return group()
        else:
            return group

    def setRegistryValue(self, name, value, channel=None):
        plugin = self.name()
        group = conf.supybot.plugins.get(plugin)
        names = registry.split(name)
        for name in names:
            group = group.get(name)
        if channel is None:
            group.setValue(value)
        else:
            group.get(channel).setValue(value)

    def userValue(self, name, prefixOrName, default=None):
        try:
            id = str(ircdb.users.getUserId(prefixOrName))
        except KeyError:
            return None
        plugin = self.name()
        group = conf.users.plugins.get(plugin)
        names = registry.split(name)
        for name in names:
            group = group.get(name)
        return group.get(id)()

    def setUserValue(self, name, prefixOrName, value,
                     ignoreNoUser=True, setValue=True):
        try:
            id = str(ircdb.users.getUserId(prefixOrName))
        except KeyError:
            if ignoreNoUser:
                return
            else:
                raise
        plugin = self.name()
        group = conf.users.plugins.get(plugin)
        names = registry.split(name)
        for name in names:
            group = group.get(name)
        group = group.get(id)
        if setValue:
            group.setValue(value)
        else:
            group.set(value)


class SimpleProxy(RichReplyMethods):
    """This class is a thin wrapper around an irclib.Irc object that gives it
    the reply() and error() methods (as well as everything in RichReplyMethods,
    based on those two)."""
    def __init__(self, irc, msg):
        self.irc = irc
        self.msg = msg

    def error(self, s, msg=None, **kwargs):
        if 'Raise' in kwargs and kwargs['Raise']:
            if s:
                raise Error, s
            else:
                raise ArgumentError
        if msg is None:
            msg = self.msg
        m = error(msg, s, **kwargs)
        self.irc.queueMsg(m)
        return m

    def reply(self, s, msg=None, **kwargs):
        if msg is None:
            msg = self.msg
        assert not isinstance(s, ircmsgs.IrcMsg), \
               'Old code alert: there is no longer a "msg" argument to reply.'
        m = reply(msg, s, **kwargs)
        self.irc.queueMsg(m)
        return m

    def __getattr__(self, attr):
        return getattr(self.irc, attr)

IrcObjectProxyRegexp = SimpleProxy

class PrivmsgRegexp(Privmsg):
    """A class to allow a person to create regular expression callbacks.

    Much more primitive, but more flexible than the 'normal' method of using
    the Privmsg class and its lexer, PrivmsgRegexp allows you to write
    callbacks that aren't addressed to the bot, for instance.  There are, of
    course, several other possibilities.  Callbacks are registered with a
    string (the regular expression) and a function to be called (with the Irc
    object, the IrcMsg object, and the match object) when the regular
    expression matches.  Callbacks must have the signature (self, irc, msg,
    match) to be counted as such.

    A class-level flags attribute is used to determine what regexp flags to
    compile the regular expressions with.  By default, it's re.I, which means
    regular expressions are by default case-insensitive.

    If you have a standard command-type callback, though, Privmsg is a much
    better class to use, at the very least for consistency's sake, but also
    because it's much more easily coded and maintained.
    """
    flags = re.I
    Proxy = SimpleProxy
    commandArgs = ['self', 'irc', 'msg', 'match']
    def __init__(self):
        self.__parent = super(PrivmsgRegexp, self)
        self.__parent.__init__()
        self.res = []
        #for name, value in self.__class__.__dict__.iteritems():
        for name, value in self.__class__.__dict__.items():
            value = getattr(self, name)
            if self.isCommand(name):
                try:
                    r = re.compile(value.__doc__, self.flags)
                    self.res.append((r, name))
                except re.error, e:
                    self.log.warning('Invalid regexp: %s (%s)',
                                     utils.str.quoted(value.__doc__), e)
        utils.sortBy(operator.itemgetter(1), self.res)

    def callCommand(self, name, irc, msg, *L, **kwargs):
        try:
            self.__parent.callCommand(name, irc, msg, *L, **kwargs)
        except Exception, e:
            # We catch exceptions here because IrcObjectProxy isn't doing our
            # dirty work for us anymore.
            self.log.exception('Uncaught exception in %s.%s:',
                               self.name(), name)
            if conf.supybot.reply.error.detailed():
                irc.error(utils.exnToString(e))
            else:
                irc.replyError()

    def doPrivmsg(self, irc, msg):
        if msg.isError:
            self.log.info('%s not running due to msg.isError.', self.name())
            return
        for (r, name) in self.res:
            spans = sets.Set()
            for m in r.finditer(msg.args[1]):
                # There's a bug in finditer: http://www.python.org/sf/817234
                if m.span() in spans:
                    break
                else:
                    spans.add(m.span())
                irc = self.Proxy(irc, msg)
                self.callCommand(name, irc, msg, m)


class PrivmsgCommandAndRegexp(Privmsg):
    """Same as Privmsg, except allows the user to also include regexp-based
    callbacks.  All regexp-based callbacks must be specified in a sets.Set
    (or list) attribute "regexps".
    """
    flags = re.I
    regexps = ()
    addressedRegexps = ()
    Proxy = SimpleProxy
    def __init__(self):
        self.__parent = super(PrivmsgCommandAndRegexp, self)
        self.__parent.__init__()
        self.res = []
        self.addressedRes = []
        for name in self.regexps:
            method = getattr(self, name)
            r = re.compile(method.__doc__, self.flags)
            self.res.append((r, name))
        for name in self.addressedRegexps:
            method = getattr(self, name)
            r = re.compile(method.__doc__, self.flags)
            self.addressedRes.append((r, name))

    def isCommand(self, name):
        return self.__parent.isCommand(name) or \
               name in self.regexps or \
               name in self.addressedRegexps

    def getCommand(self, name):
        try:
            return getattr(self, name) # Regexp stuff.
        except AttributeError:
            return self.__parent.getCommand(name)

    def callCommand(self, name, irc, msg, *L, **kwargs):
        try:
            self.__parent.callCommand(name, irc, msg, *L, **kwargs)
        except Exception, e:
            # As annoying as it is, Python doesn't allow *L in addition to
            # well-defined keyword arguments.  So we have to do this trick.
            catchErrors = kwargs.pop('catchErrors', False)
            if catchErrors:
                self.log.exception('Uncaught exception in callCommand:')
                if conf.supybot.reply.error.detailed():
                    irc.error(utils.exnToString(e))
                else:
                    irc.replyError()
            else:
                raise

    def doPrivmsg(self, irc, msg):
        if msg.isError:
            self.log.debug('%s not running due to msg.isError.', self.name())
            return
        s = addressed(irc.nick, msg)
        if s:
            for (r, name) in self.addressedRes:
                if msg.repliedTo and name not in self.alwaysCall:
                    continue
                for m in r.finditer(s):
                    proxy = self.Proxy(irc, msg)
                    self.callCommand(name, proxy, msg, m, catchErrors=True)
        for (r, name) in self.res:
            for m in r.finditer(msg.args[1]):
                proxy = self.Proxy(irc, msg)
                self.callCommand(name, proxy, msg, m, catchErrors=True)


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
