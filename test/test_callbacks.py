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

from testsupport import *

import supybot.conf as conf
import supybot.utils as utils
import supybot.ircmsgs as ircmsgs
import supybot.callbacks as callbacks

tokenize = callbacks.tokenize


class TokenizerTestCase(SupyTestCase):
    def testEmpty(self):
        self.assertEqual(tokenize(''), [])

    def testNullCharacter(self):
        self.assertEqual(tokenize(utils.dqrepr('\0')), ['\0'])

    def testSingleDQInDQString(self):
        self.assertEqual(tokenize('"\\""'), ['"'])

    def testDQsWithBackslash(self):
        self.assertEqual(tokenize('"\\\\"'), ["\\"])

    def testDoubleQuotes(self):
        self.assertEqual(tokenize('"\\"foo\\""'), ['"foo"'])

    def testSingleWord(self):
        self.assertEqual(tokenize('foo'), ['foo'])

    def testMultipleSimpleWords(self):
        words = 'one two three four five six seven eight'.split()
        for i in range(len(words)):
            self.assertEqual(tokenize(' '.join(words[:i])), words[:i])

    def testSingleQuotesNotQuotes(self):
        self.assertEqual(tokenize("it's"), ["it's"])

    def testQuotedWords(self):
        self.assertEqual(tokenize('"foo bar"'), ['foo bar'])
        self.assertEqual(tokenize('""'), [''])
        self.assertEqual(tokenize('foo "" bar'), ['foo', '', 'bar'])
        self.assertEqual(tokenize('foo "bar baz" quux'),
                         ['foo', 'bar baz', 'quux'])

    def testNesting(self):
        self.assertEqual(tokenize('[]'), [[]])
        self.assertEqual(tokenize('[foo]'), [['foo']])
        self.assertEqual(tokenize('[ foo ]'), [['foo']])
        self.assertEqual(tokenize('foo [bar]'), ['foo', ['bar']])
        self.assertEqual(tokenize('foo bar [baz quux]'),
                         ['foo', 'bar', ['baz', 'quux']])
        try:
            orig = conf.supybot.reply.brackets()
            conf.supybot.reply.brackets.setValue('')
            self.assertEqual(tokenize('[]'), ['[]'])
            self.assertEqual(tokenize('[foo]'), ['[foo]'])
            self.assertEqual(tokenize('foo [bar]'), ['foo', '[bar]'])
            self.assertEqual(tokenize('foo bar [baz quux]'),
                             ['foo', 'bar', '[baz', 'quux]'])
        finally:
            conf.supybot.reply.brackets.setValue(orig)

    def testError(self):
        self.assertRaises(SyntaxError, tokenize, '[foo') #]
        self.assertRaises(SyntaxError, tokenize, '"foo') #"

    def testPipe(self):
        try:
            conf.supybot.reply.pipeSyntax.set('True')
            self.assertRaises(SyntaxError, tokenize, '| foo')
            self.assertRaises(SyntaxError, tokenize, 'foo ||bar')
            self.assertRaises(SyntaxError, tokenize, 'bar |')
            self.assertEqual(tokenize('foo|bar'), ['bar', ['foo']])
            self.assertEqual(tokenize('foo | bar'), ['bar', ['foo']])
            self.assertEqual(tokenize('foo | bar | baz'),
                             ['baz', ['bar',['foo']]])
            self.assertEqual(tokenize('foo bar | baz'),
                             ['baz', ['foo', 'bar']])
            self.assertEqual(tokenize('foo | bar baz'),
                             ['bar', 'baz', ['foo']])
            self.assertEqual(tokenize('foo bar | baz quux'),
                             ['baz', 'quux', ['foo', 'bar']])
        finally:
            conf.supybot.reply.pipeSyntax.set('False')
            self.assertEqual(tokenize('foo|bar'), ['foo|bar'])
            self.assertEqual(tokenize('foo | bar'), ['foo', '|', 'bar'])
            self.assertEqual(tokenize('foo | bar | baz'),
                             ['foo', '|', 'bar', '|', 'baz'])
            self.assertEqual(tokenize('foo bar | baz'),
                             ['foo', 'bar', '|', 'baz'])

    def testBold(self):
        s = '\x02foo\x02'
        self.assertEqual(tokenize(s), [s])
        s = s[:-1] + '\x0f'
        self.assertEqual(tokenize(s), [s])

    def testColor(self):
        s = '\x032,3foo\x03'
        self.assertEqual(tokenize(s), [s])
        s = s[:-1] + '\x0f'
        self.assertEqual(tokenize(s), [s])


class FunctionsTestCase(SupyTestCase):
    def testCanonicalName(self):
        self.assertEqual('foo', callbacks.canonicalName('foo'))
        self.assertEqual('foobar', callbacks.canonicalName('foo-bar'))
        self.assertEqual('foobar', callbacks.canonicalName('foo_bar'))
        self.assertEqual('foobar', callbacks.canonicalName('FOO-bar'))
        self.assertEqual('foobar', callbacks.canonicalName('FOOBAR'))
        self.assertEqual('foobar', callbacks.canonicalName('foo___bar'))
        self.assertEqual('foobar', callbacks.canonicalName('_f_o_o-b_a_r'))
        self.assertEqual('foobar--', callbacks.canonicalName('foobar--'))

    def testAddressed(self):
        oldprefixchars = str(conf.supybot.prefixChars)
        nick = 'supybot'
        conf.supybot.prefixChars.set('~!@')
        inChannel = ['~foo', '@foo', '!foo',
                     '%s: foo' % nick, '%s foo' % nick,
                     '%s: foo' % nick.capitalize(), '%s: foo' % nick.upper()]
        inChannel = [ircmsgs.privmsg('#foo', s) for s in inChannel]
        badmsg = ircmsgs.privmsg('#foo', '%s:foo' % nick)
        self.failIf(callbacks.addressed(nick, badmsg))
        badmsg = ircmsgs.privmsg('#foo', '%s^: foo' % nick)
        self.failIf(callbacks.addressed(nick, badmsg))
        for msg in inChannel:
            self.assertEqual('foo', callbacks.addressed(nick, msg), msg)
        msg = ircmsgs.privmsg(nick, 'foo')
        self.assertEqual('foo', callbacks.addressed(nick, msg))
        conf.supybot.prefixChars.set(oldprefixchars)
        msg = ircmsgs.privmsg('#foo', '%s::::: bar' % nick)
        self.assertEqual('bar', callbacks.addressed(nick, msg))
        msg = ircmsgs.privmsg('#foo', '%s: foo' % nick.upper())
        self.assertEqual('foo', callbacks.addressed(nick, msg))
        badmsg = ircmsgs.privmsg('#foo', '%s`: foo' % nick)
        self.failIf(callbacks.addressed(nick, badmsg))

    def testAddressedReplyWhenNotAddressed(self):
        msg1 = ircmsgs.privmsg('#foo', '@bar')
        msg2 = ircmsgs.privmsg('#foo', 'bar')
        self.assertEqual(callbacks.addressed('blah', msg1), 'bar')
        self.assertEqual(callbacks.addressed('blah', msg2), '')
        try:
            original = conf.supybot.reply.whenNotAddressed()
            conf.supybot.reply.whenNotAddressed.setValue(True)
            self.assertEqual(callbacks.addressed('blah', msg1), 'bar')
            self.assertEqual(callbacks.addressed('blah', msg2), 'bar')
        finally:
            conf.supybot.reply.whenNotAddressed.setValue(original)

    def testReply(self):
        prefix = 'foo!bar@baz'
        channelMsg = ircmsgs.privmsg('#foo', 'bar baz', prefix=prefix)
        nonChannelMsg = ircmsgs.privmsg('supybot', 'bar baz', prefix=prefix)
        self.assertEqual(ircmsgs.privmsg(nonChannelMsg.nick, 'foo'),
                         callbacks.reply(channelMsg, 'foo', private=True))
        self.assertEqual(ircmsgs.privmsg(nonChannelMsg.nick, 'foo'),
                         callbacks.reply(nonChannelMsg, 'foo'))
        self.assertEqual(ircmsgs.privmsg(channelMsg.args[0],
                                         '%s: foo' % channelMsg.nick),
                         callbacks.reply(channelMsg, 'foo'))
        self.assertEqual(ircmsgs.privmsg(channelMsg.args[0],
                                         'foo'),
                         callbacks.reply(channelMsg, 'foo', prefixName=False))
        self.assertEqual(ircmsgs.notice(nonChannelMsg.nick, 'foo'),
                         callbacks.reply(channelMsg, 'foo',
                                         notice=True, private=True))

    def testReplyTo(self):
        prefix = 'foo!bar@baz'
        msg = ircmsgs.privmsg('#foo', 'bar baz', prefix=prefix)
        self.assertEqual(callbacks.reply(msg, 'blah', to='blah'),
                         ircmsgs.privmsg('#foo', 'blah: blah'))
        self.assertEqual(callbacks.reply(msg, 'blah', to='blah', private=True),
                         ircmsgs.privmsg('blah', 'blah'))

    def testGetCommands(self):
        self.assertEqual(callbacks.getCommands(['foo']), ['foo'])
        self.assertEqual(callbacks.getCommands(['foo', 'bar']), ['foo'])
        self.assertEqual(callbacks.getCommands(['foo', ['bar', 'baz']]),
                         ['foo', 'bar'])
        self.assertEqual(callbacks.getCommands(['foo', 'bar', ['baz']]),
                         ['foo', 'baz'])
        self.assertEqual(callbacks.getCommands(['foo', ['bar'], ['baz']]),
                         ['foo', 'bar', 'baz'])

    def testTokenize(self):
        self.assertEqual(callbacks.tokenize(''), [])
        self.assertEqual(callbacks.tokenize('foo'), ['foo'])
        self.assertEqual(callbacks.tokenize('foo'), ['foo'])
        self.assertEqual(callbacks.tokenize('bar [baz]'), ['bar', ['baz']])


class PrivmsgTestCase(ChannelPluginTestCase):
    plugins = ('Utilities', 'Misc')
    conf.allowEval = True
    timeout = 2
    def testEmptySquareBrackets(self):
        self.assertError('echo []')

    def testSimpleReply(self):
        self.assertResponse("eval irc.reply('foo')", 'foo')

    def testSimpleReplyAction(self):
        self.assertResponse("eval irc.reply('foo', action=True)",
                            '\x01ACTION foo\x01')

    def testReplyWithNickPrefix(self):
        self.feedMsg('@strlen foo')
        m = self.irc.takeMsg()
        self.failUnless(m is not None, 'm: %r' % m)
        self.failUnless(m.args[1].startswith(self.nick))
        try:
            original = conf.supybot.reply.withNickPrefix()
            conf.supybot.reply.withNickPrefix.setValue(False)
            self.feedMsg('@strlen foobar')
            m = self.irc.takeMsg()
            self.failUnless(m is not None)
            self.failIf(m.args[1].startswith(self.nick))
        finally:
            conf.supybot.reply.withNickPrefix.setValue(original)

    def testErrorPrivateKwarg(self):
        try:
            original = conf.supybot.reply.errorInPrivate()
            conf.supybot.reply.errorInPrivate.setValue(False)
            m = self.getMsg("eval irc.error('foo', private=True)")
            self.failIf(ircutils.isChannel(m.args[0]))
        finally:
            conf.supybot.reply.errorInPrivate.setValue(original)

    def testErrorNoArgumentIsArgumentError(self):
        self.assertHelp('eval irc.error()')

    def testErrorWithNotice(self):
        try:
            original = conf.supybot.reply.errorWithNotice()
            conf.supybot.reply.errorWithNotice.setValue(True)
            m = self.getMsg("eval irc.error('foo')")
            self.failUnless(m.command == 'NOTICE')
        finally:
            conf.supybot.reply.errorWithNotice.setValue(original)

    def testErrorReplyPrivate(self):
        try:
            original = str(conf.supybot.reply.errorInPrivate)
            conf.supybot.reply.errorInPrivate.set('False')
            # If this doesn't raise an error, we've got a problem, so the next
            # two assertions shouldn't run.  So we first check that what we
            # expect to error actually does so we don't go on a wild goose
            # chase because our command never errored in the first place :)
            s = 're s/foo/bar baz' # will error; should be "re s/foo/bar/ baz"
            self.assertError(s)
            m = self.getMsg(s)
            self.failUnless(ircutils.isChannel(m.args[0]))
            conf.supybot.reply.errorInPrivate.set('True')
            m = self.getMsg(s)
            self.failIf(ircutils.isChannel(m.args[0]))
        finally:
            conf.supybot.reply.errorInPrivate.set(original)

    # Now for stuff not based on the plugins.
    class First(callbacks.Privmsg):
        def firstcmd(self, irc, msg, args):
            """First"""
            irc.reply('foo')

    class Second(callbacks.Privmsg):
        def secondcmd(self, irc, msg, args):
            """Second"""
            irc.reply('bar')

    class FirstRepeat(callbacks.Privmsg):
        def firstcmd(self, irc, msg, args):
            """FirstRepeat"""
            irc.reply('baz')

    class Third(callbacks.Privmsg):
        def third(self, irc, msg, args):
            """Third"""
            irc.reply(' '.join(args))

    def tearDown(self):
        if hasattr(self.First, 'first'):
            del self.First.first
        if hasattr(self.Second, 'second'):
            del self.Second.second
        if hasattr(self.FirstRepeat, 'firstrepeat'):
            del self.FirstRepeat.firstrepeat
        ChannelPluginTestCase.tearDown(self)

    def testDispatching(self):
        self.irc.addCallback(self.First())
        self.irc.addCallback(self.Second())
        self.assertResponse('firstcmd', 'foo')
        self.assertResponse('secondcmd', 'bar')
        self.assertResponse('first firstcmd', 'foo')
        self.assertResponse('second secondcmd', 'bar')

    def testAmbiguousError(self):
        self.irc.addCallback(self.First())
        self.assertNotError('firstcmd')
        self.irc.addCallback(self.FirstRepeat())
        self.assertError('firstcmd')
        self.assertError('firstcmd [firstcmd]')
        self.assertNotRegexp('firstcmd', '(foo.*baz|baz.*foo)')
        self.assertResponse('first firstcmd', 'foo')
        self.assertResponse('firstrepeat firstcmd', 'baz')

    def testAmbiguousHelpError(self):
        self.irc.addCallback(self.First())
        self.irc.addCallback(self.FirstRepeat())
        self.assertError('help first')

    def testHelpDispatching(self):
        self.irc.addCallback(self.First())
        self.assertHelp('help firstcmd')
        self.assertHelp('help first firstcmd')
        self.irc.addCallback(self.FirstRepeat())
        self.assertError('help firstcmd')
        self.assertRegexp('help first firstcmd', 'First', 0) # no re.I flag.
        self.assertRegexp('help firstrepeat firstcmd', 'FirstRepeat', 0)

    class TwoRepliesFirstAction(callbacks.Privmsg):
        def testactionreply(self, irc, msg, args):
            irc.reply('foo', action=True)
            irc.reply('bar') # We're going to check that this isn't an action.

    def testNotActionSecondReply(self):
        self.irc.addCallback(self.TwoRepliesFirstAction())
        self.assertAction('testactionreply', 'foo')
        m = self.getMsg(' ')
        self.failIf(m.args[1].startswith('\x01ACTION'))

    def testEmptyNest(self):
        try:
            conf.supybot.reply.whenNotCommand.set('True')
            self.assertError('echo []')
            conf.supybot.reply.whenNotCommand.set('False')
            self.assertResponse('echo []', '[]')
        finally:
            conf.supybot.reply.whenNotCommand.set('False')

    def testDispatcherHelp(self):
        self.assertNotRegexp('help first', r'\(dispatcher')
        self.assertNotRegexp('help first', r'%s')

    def testDefaultCommand(self):
        self.irc.addCallback(self.First())
        self.irc.addCallback(self.Third())
        self.assertError('first blah')
        self.assertResponse('third foo bar baz', 'foo bar baz')

    def testSyntaxErrorNotEscaping(self):
        self.assertError('load [foo')
        self.assertError('load foo]')

    def testNoEscapingAttributeErrorFromTokenizeWithFirstElementList(self):
        self.assertError('[plugin list] list')

    class InvalidCommand(callbacks.Privmsg):
        def invalidCommand(self, irc, msg, tokens):
            irc.reply('foo')

    def testInvalidCommandOneReplyOnly(self):
        try:
            original = str(conf.supybot.reply.whenNotCommand)
            conf.supybot.reply.whenNotCommand.set('True')
            self.assertRegexp('asdfjkl', 'not a valid command')
            self.irc.addCallback(self.InvalidCommand())
            self.assertResponse('asdfjkl', 'foo')
            self.assertNoResponse(' ', 2)
        finally:
            conf.supybot.reply.whenNotCommand.set(original)

    class BadInvalidCommand(callbacks.Privmsg):
        def invalidCommand(self, irc, msg, tokens):
            s = 'This shouldn\'t keep Misc.invalidCommand from being called'
            raise Exception, s

    def testBadInvalidCommandDoesNotKillAll(self):
        try:
            original = str(conf.supybot.reply.whenNotCommand)
            conf.supybot.reply.whenNotCommand.set('True')
            self.irc.addCallback(self.BadInvalidCommand())
            self.assertRegexp('asdfjkl', 'not a valid command')
        finally:
            conf.supybot.reply.whenNotCommand.set(original)


class PrivmsgCommandAndRegexpTestCase(PluginTestCase):
    plugins = ()
    class PCAR(callbacks.PrivmsgCommandAndRegexp):
        def test(self, irc, msg, args):
            "<foo>"
            raise callbacks.ArgumentError
    def testNoEscapingArgumentError(self):
        self.irc.addCallback(self.PCAR())
        self.assertResponse('test', 'test <foo>')

class RichReplyMethodsTestCase(PluginTestCase):
    plugins = ()
    class NoCapability(callbacks.Privmsg):
        def error(self, irc, msg, args):
            irc.errorNoCapability('admin')
    def testErrorNoCapability(self):
        self.irc.addCallback(self.NoCapability())
        self.assertRegexp('error', 'admin')


class WithPrivateNoticeTestCase(ChannelPluginTestCase):
    plugins = ()
    class WithPrivateNotice(callbacks.Privmsg):
        def normal(self, irc, msg, args):
            irc.reply('should be with private notice')
        def explicit(self, irc, msg, args):
            irc.reply('should not be with private notice',
                      private=False, notice=False)
    def test(self):
        self.irc.addCallback(self.WithPrivateNotice())
        # Check normal behavior.
        m = self.assertNotError('normal')
        self.failIf(m.command == 'NOTICE')
        self.failUnless(ircutils.isChannel(m.args[0]))
        m = self.assertNotError('explicit')
        self.failIf(m.command == 'NOTICE')
        self.failUnless(ircutils.isChannel(m.args[0]))
        # Check abnormal behavior.
        originalInPrivate = conf.supybot.reply.inPrivate()
        originalWithNotice = conf.supybot.reply.withNotice()
        try:
            conf.supybot.reply.inPrivate.setValue(True)
            conf.supybot.reply.withNotice.setValue(True)
            m = self.assertNotError('normal')
            self.failUnless(m.command == 'NOTICE')
            self.failIf(ircutils.isChannel(m.args[0]))
            m = self.assertNotError('explicit')
            self.failIf(m.command == 'NOTICE')
            self.failUnless(ircutils.isChannel(m.args[0]))
        finally:
            conf.supybot.reply.inPrivate.setValue(originalInPrivate)
            conf.supybot.reply.withNotice.setValue(originalWithNotice)
            
            
        

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
