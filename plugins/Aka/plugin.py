###
# Copyright (c) 2013, Valentin Lorentz
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

import re
import os
import sys

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
from supybot.i18n import PluginInternationalization
_ = PluginInternationalization('Aka')

try:
    import sqlalchemy
    import sqlalchemy.ext
    import sqlalchemy.ext.declarative
except ImportError:
    sqlalchemy = None

if sqlalchemy:

    Base = sqlalchemy.ext.declarative.declarative_base()
    class Alias(Base):
        __tablename__ = 'aliases'

        id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True)
        name = sqlalchemy.Column(sqlalchemy.String, unique=True)
        alias = sqlalchemy.Column(sqlalchemy.String)


        def __init__(self, name, alias):
            self.name = name
            self.alias = alias
        def __repr__(self):
            return "<Alias('%r', '%r')>" % (self.name, self.alias)

    # TODO: Add table for locks
    # TODO: Add table for usage statistics

    class SqlAlchemyAkaDB(object):
        def __init__(self, filename):
            self.engines = ircutils.IrcDict()
            self.filename = filename
            self.sqlalchemy = sqlalchemy

        def close(self):
            self.dbs.clear()

        def get_db(self, channel):
            if channel in self.engines:
                engine = self.engines[channel]
            else:
                filename = plugins.makeChannelFilename(self.filename, channel)
                exists = os.path.exists(filename)
                engine = sqlalchemy.create_engine('sqlite:///' + filename)
                if not exists:
                    Base.metadata.create_all(engine)
                self.engines[channel] = engine
            assert engine.execute("select 1").scalar() == 1
            Session = sqlalchemy.orm.sessionmaker()
            Session.configure(bind=engine)
            return Session()


        def has_aka(self, channel, name):
            count = self.get_db(channel).query(Alias) \
                    .filter(Alias.name == name) \
                    .count()
            return bool(count)
        def get_aka_list(self, channel):
            list_ = list(self.get_db(channel).query(Alias.name))
            return list_

        def get_alias(self, channel, name):
            try:
                return self.get_db(channel).query(Alias.alias) \
                        .filter(Alias.name == name).one()[0]
            except sqlalchemy.orm.exc.NoResultFound:
                return None

        def add_aka(self, channel, name, alias):
            if self.has_aka(channel, name):
                raise AliasError(_('This Aka already exists.'))
            if sys.version_info[0] < 3:
                if isinstance(name, str):
                    name = name.decode('utf8')
                if isinstance(alias, str):
                    alias = alias.decode('utf8')
            db = self.get_db(channel)
            db.add(Alias(name, alias))
            db.commit()

        def remove_aka(self, channel, name):
            db = self.get_db(channel)
            db.query(Alias).filter(Alias.name == name).delete()
            db.commit()

def getArgs(args, required=1, optional=0, wildcard=0):
    if len(args) < required:
        raise callbacks.ArgumentError
    if len(args) < required + optional:
        ret = list(args) + ([''] * (required + optional - len(args)))
    elif len(args) >= required + optional:
        if not wildcard:
            ret = list(args[:required + optional - 1])
            ret.append(' '.join(args[required + optional - 1:]))
        else:
            ret = list(args)
    return ret

class AliasError(Exception):
    pass

class RecursiveAlias(AliasError):
    pass

dollarRe = re.compile(r'\$(\d+)')
def findBiggestDollar(alias):
    dollars = dollarRe.findall(alias)
    dollars = map(int, dollars)
    dollars.sort()
    if dollars:
        return dollars[-1]
    else:
        return 0

atRe = re.compile(r'@(\d+)')
def findBiggestAt(alias):
    ats = atRe.findall(alias)
    ats = map(int, ats)
    ats.sort()
    if ats:
        return ats[-1]
    else:
        return 0

AkaDB = plugins.DB('Aka', {'sqlalchemy': SqlAlchemyAkaDB})

class Aka(callbacks.Plugin):
    """Add the help for "@plugin help Aka" here
    This should describe *how* to use this plugin."""

    def __init__(self, irc):
        self.__parent = super(Aka, self)
        self.__parent.__init__(irc)
        self._db = AkaDB()

    def isCommandMethod(self, name):
        channel = dynamic.channel
        return self._db.has_aka(channel, name) or \
                self._db.has_aka('global', name) or \
                self.__parent.isCommandMethod(name)

    def listCommands(self):
        channel = dynamic.channel
        return set(self._db.get_aka_list(channel) +
                self._db.get_aka_list('global') +
                self.__parent.listCommands())

    def getCommandMethod(self, command=None, name=None):
        if command:
            assert name is None
            try:
                return self.__parent.getCommandMethod(command)
            except AttributeError:
                pass
        name = name or callbacks.formatCommand(command)
        channel = dynamic.channel
        original = self._db.get_alias(channel, name)
        if not original:
            original = self._db.get_alias('global', name)
        biggestDollar = findBiggestDollar(original)
        biggestAt = findBiggestAt(original)
        wildcard = '$*' in original
        def f(irc, msg, args):
            tokens = callbacks.tokenize(original)
            if biggestDollar or biggestAt:
                args = getArgs(args, required=biggestDollar, optional=biggestAt,
                                wildcard=wildcard)
            def regexpReplace(m):
                idx = int(m.group(1))
                return args[idx-1]
            def replace(tokens, replacer):
                for (i, token) in enumerate(tokens):
                    if isinstance(token, list):
                        replace(token, replacer)
                    else:
                        tokens[i] = replacer(token)
            replace(tokens, lambda s: dollarRe.sub(regexpReplace, s))
            if biggestAt:
                assert not wildcard
                args = args[biggestDollar:]
                replace(tokens, lambda s: atRe.sub(regexpReplace, s))
            if wildcard:
                assert not biggestAt
                # Gotta remove the things that have already been subbed in.
                i = biggestDollar
                while i:
                    args.pop(0)
                    i -= 1
                def everythingReplace(tokens):
                    for (i, token) in enumerate(tokens):
                        if isinstance(token, list):
                            if everythingReplace(token):
                                return
                        if token == '$*':
                            tokens[i:i+1] = args
                            return True
                        elif '$*' in token:
                            tokens[i] = token.replace('$*', ' '.join(args))
                            return True
                    return False
                everythingReplace(tokens)
            self.Proxy(irc, msg, tokens)
        if biggestDollar and (wildcard or biggestAt):
            flexargs = _(' at least')
        else:
            flexargs = ''
        doc = format(_('<an alias,%s %n>\n\nAlias for %q.'),
                    flexargs, (biggestDollar, _('argument')), original)
        f = utils.python.changeFunctionName(f, name, doc)
        return f

    def _add_aka(self, channel, name, alias):
        if self.__parent.isCommandMethod(name):
            raise AliasError(_('You can\'t overwrite commands in '
                    'this plugin.'))
        if self._db.has_aka(channel, name):
            raise AliasError(_('This Aka already exists.'))
        biggestDollar = findBiggestDollar(alias)
        biggestAt = findBiggestAt(alias)
        wildcard = '$*' in alias
        if biggestAt and wildcard:
            raise AliasError(_('Can\'t mix $* and optional args (@1, etc.)'))
        if alias.count('$*') > 1:
            raise AliasError(_('There can be only one $* in an alias.'))
        self._db.add_aka(channel, name, alias)

    def _remove_aka(self, channel, name):
        self._db.remove_aka(channel, name)

    def add(self, irc, msg, args, optlist, name, alias):
        """[--channel <#channel>] <name> <command>

        Defines an alias <name> that executes <command>.  The <command>
        should be in the standard "command argument [nestedcommand argument]"
        arguments to the alias; they'll be filled with the first, second, etc.
        arguments.  $1, $2, etc. can be used for required arguments.  @1, @2,
        etc. can be used for optional arguments.  $* simply means "all
        remaining arguments," and cannot be combined with optional arguments.
        """
        channel = 'global'
        for (option, arg) in optlist:
            if option == 'channel':
                if not ircutils.isChannel(arg):
                    irc.error(_('%r is not a valid channel.') % arg,
                            Raise=True)
                channel = arg
        if ' ' not in alias:
            # If it's a single word, they probably want $*.
            alias += ' $*'
        try:
            self._add_aka(channel, name, alias)
            self.log.info('Adding Aka %q for %q (from %s)',
                          name, alias, msg.prefix)
            irc.replySuccess()
        except AliasError as e:
            irc.error(str(e))
    add = wrap(add, [getopts({
                                'channel': 'somethingWithoutSpaces',
                            }),'commandName', 'text'])

    def remove(self, irc, msg, args, channel, name):
        """[<#channel|global>] <name>

        Removes the given alias, if unlocked.
        """
        try:
            self._remove_aka(channel, name)
            self.log.info('Removing Aka %q (from %s)', name, msg.prefix)
            irc.replySuccess()
        except AliasError as e:
            irc.error(str(e))
    remove = wrap(remove, [first(('literal', 'global'), 'channel'),
                           'commandName'])


Class = Aka


# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
