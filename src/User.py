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
Provides commands useful to users in general. This plugin is loaded by default.
"""

import supybot

__revision__ = "$Id$"
__author__ = supybot.authors.jemfinch

import supybot.fix as fix

import re
import getopt
import fnmatch
from itertools import imap, ifilter

import supybot.conf as conf
import supybot.utils as utils
import supybot.ircdb as ircdb
from supybot.commands import *
import supybot.ircutils as ircutils
import supybot.privmsgs as privmsgs
import supybot.callbacks as callbacks

class User(callbacks.Privmsg):
    def _checkNotChannel(self, irc, msg, password=' '):
        if password and ircutils.isChannel(msg.args[0]):
            raise callbacks.Error, conf.supybot.replies.requiresPrivacy()

    def list(self, irc, msg, args, optlist, glob):
        """[--capability=<capability>] [<glob>]

        Returns the valid registered usernames matching <glob>.  If <glob> is
        not given, returns all registered usernames.
        """
        predicates = []
        for (option, arg) in optlist:
            if option == 'capability':
                def p(u, cap=arg):
                    try:
                        return u.checkCapability(cap)
                    except KeyError:
                        return False
                predicates.append(p)
        if glob:
            r = re.compile(fnmatch.translate(glob), re.I)
            def p(u):
                return r.match(u.name) is not None
            predicates.append(p)
        users = []
        for u in ircdb.users.itervalues():
            for predicate in predicates:
                if not predicate(u):
                    break
            else:
                users.append(u.name)
        if users:
            utils.sortBy(str.lower, users)
            irc.reply(utils.commaAndify(users))
        else:
            if predicates:
                irc.reply('There are no matching registered users.')
            else:
                irc.reply('There are no registered users.')
    list = wrap(list, [getopts({'capability':'capability'}),
                       additional('glob')])

    def register(self, irc, msg, args, optlist, name, password):
        """[--hashed] <name> <password>

        Registers <name> with the given password <password> and the current
        hostmask of the person registering.  This command (and all other
        commands that include a password) must be sent to the bot privately,
        not in a channel.  If --hashed is given, the password will be hashed
        on disk, rather than being stored in the default configured format.
        """
        addHostmask = True
        hashed = conf.supybot.databases.users.hash()
        for (option, arg) in optlist:
            if option == 'hashed':
                hashed = True
        try:
            ircdb.users.getUserId(name)
            irc.error('That name is already assigned to someone.', Raise=True)
        except KeyError:
            pass
        if ircutils.isUserHostmask(name):
            irc.errorInvalid('username', name,
                             'Hostmasks are not valid usernames.', Raise=True)
        try:
            u = ircdb.users.getUser(msg.prefix)
            if u.checkCapability('owner'):
                addHostmask = False
            else:
                irc.error('Your hostmask is already registered to %s' % u.name)
                return
        except KeyError:
            pass
        user = ircdb.users.newUser()
        user.name = name
        user.setPassword(password, hashed=hashed)
        if addHostmask:
            user.addHostmask(msg.prefix)
        ircdb.users.setUser(user)
        irc.replySuccess()
    register = wrap(register, ['private', getopts({'hashed':''}), 'something',
                               'something'])

    def unregister(self, irc, msg, args, user, password):
        """<name> [<password>]

        Unregisters <name> from the user database.  If the user giving this
        command is an owner user, the password is not necessary.
        """
        try:
            caller = ircdb.users.getUser(msg.prefix)
            isOwner = caller.checkCapability('owner')
        except KeyError:
            caller = None
            isOwner = False
        if not conf.supybot.databases.users.allowUnregistration():
            if not caller or not isOwner:
                self.log.warning('%s tried to unregister user %s.',
                                 msg.prefix, user.name)
                irc.error('This command has been disabled.  You\'ll have to '
                          'ask the owner of this bot to unregister your user.')
        if isOwner or user.checkPassword(password):
            ircdb.users.delUser(user.id)
            irc.replySuccess()
        else:
            irc.error(conf.supybot.replies.incorrectAuthentication())
    unregister = wrap(unregister, ['private', 'otherUser',
                                   additional('anything')])

    def changename(self, irc, msg, args, user, newname, password):
        """<name> <new name> [<password>]

        Changes your current user database name to the new name given.
        <password> is only necessary if the user isn't recognized by hostmask.
        If you include the <password> parameter, this message must be sent
        to the bot privately (not on a channel).
        """
        try:
            id = ircdb.users.getUserId(newname)
            irc.error('%s is already registered.' % utils.quoted(newname))
            return
        except KeyError:
            pass
        if user.checkHostmask(msg.prefix) or user.checkPassword(password):
            user.name = newname
            ircdb.users.setUser(user)
            irc.replySuccess()
    changename = wrap(changename, ['private', 'otherUser', 'something',
                                   additional('something', '')])

    def addhostmask(self, irc, msg, args, user, hostmask, password):
        """[<name>] [<hostmask>] [<password>]

        Adds the hostmask <hostmask> to the user specified by <name>.  The
        <password> may only be required if the user is not recognized by
        hostmask.  If you include the <password> parameter, this message must
        be sent to the bot privately (not on a channel).  <password> is also
        not required if an owner user is giving the command on behalf of some
        other user.  If <hostmask> is not given, it defaults to your current
        hostmask.  If <name> is not given, it defaults to your currently
        identified name.
        """
        if not hostmask:
            hostmask = msg.prefix
        if not ircutils.isUserHostmask(hostmask):
            irc.errorInvalid('hostmask', hostmask, 'Make sure your hostmask '
                      'includes a nick, then an exclamation point (!), then '
                      'a user, then an at symbol (@), then a host.  Feel '
                      'free to use wildcards (* and ?, which work just like '
                      'they do on the command line) in any of these parts.',
                      Raise=True)
        try:
            otherId = ircdb.users.getUserId(hostmask)
            if otherId != user.id:
                irc.error('That hostmask is already registered.', Raise=True)
        except KeyError:
            pass
        if not user.checkPassword(password) and \
           not user.checkHostmask(msg.prefix):
            try:
                u = ircdb.users.getUser(msg.prefix)
            except KeyError:
                irc.error(conf.supybot.replies.incorrectAuthentication(),
                          Raise=True)
            if not u.checkCapability('owner'):
                irc.error(conf.supybot.replies.incorrectAuthentication(),
                          Raise=True)
        try:
            user.addHostmask(hostmask)
        except ValueError, e:
            irc.error(str(e), Raise=True)
        try:
            ircdb.users.setUser(user)
        except ValueError, e:
            irc.error(str(e), Raise=True)
        irc.replySuccess()
    addhostmask = wrap(addhostmask, [first('otherUser', 'user'),
                                     optional('something'),
                                     additional('something', '')])

    def removehostmask(self, irc, msg, args, user, hostmask, password):
        """<name> <hostmask> [<password>]

        Removes the hostmask <hostmask> from the record of the user specified
        by <name>.  If the hostmask is 'all' then all hostmasks will be
        removed.  The <password> may only be required if the user is not
        recognized by his hostmask.  If you include the <password> parameter,
        this message must be sent to the bot privately (not on a channel).
        """
        if not user.checkPassword(password) and \
           not user.checkHostmask(msg.prefix):
            u = ircdb.users.getUser(msg.prefix)
            if not u.checkCapability('owner'):
                irc.error(conf.supybot.replies.incorrectAuthentication())
                return
        try:
            s = ''
            if hostmask == 'all':
                user.hostmasks.clear()
                s = 'All hostmasks removed.'
            else:
                user.removeHostmask(hostmask)
        except KeyError:
            irc.error('There was no such hostmask.')
            return
        ircdb.users.setUser(user)
        irc.replySuccess(s)
    removehostmask = wrap(removehostmask, ['private', 'otherUser', 'something',
                                           additional('something', '')])

    def setpassword(self, irc, msg, args, optlist, user, password,newpassword):
        """[--hashed] <name> <old password> <new password>

        Sets the new password for the user specified by <name> to
        <new password>.  Obviously this message must be sent to the bot
        privately (not in a channel).  If --hashed is given, the password will
        be hashed on disk (rather than being stored in plaintext.  If the
        requesting user is an owner user (and the user whose password is being
        changed isn't that same owner user), then <old password> needn't be
        correct.
        """
        hashed = conf.supybot.databases.users.hash()
        for (option, arg) in optlist:
            if option == 'hashed':
                hashed = True
        u = ircdb.users.getUser(msg.prefix)
        if user.checkPassword(password) or \
           (u.checkCapability('owner') and not u == user):
            user.setPassword(newpassword, hashed=hashed)
            ircdb.users.setUser(user)
            irc.replySuccess()
        else:
            irc.error(conf.supybot.replies.incorrectAuthentication())
    setpassword = wrap(setpassword, [getopts({'hashed':''}), 'otherUser',
                                     'something', 'something'])

    def username(self, irc, msg, args, hostmask):
        """<hostmask|nick>

        Returns the username of the user specified by <hostmask> or <nick> if
        the user is registered.
        """
        if ircutils.isNick(nickOrHostmask):
            try:
                hostmask = irc.state.nickToHostmask(hostmask)
            except KeyError:
                irc.error('I haven\'t seen %s.' % nick, Raise=True)
        try:
            user = ircdb.users.getUser(hostmask)
            irc.reply(user.name)
        except KeyError:
            irc.error('I don\'t know who that is.')
    username = wrap(username, [first('nick', 'hostmask')])

    def hostmasks(self, irc, msg, args, name):
        """[<name>]

        Returns the hostmasks of the user specified by <name>; if <name> isn't
        specified, returns the hostmasks of the user calling the command.
        """
        try:
            user = ircdb.users.getUser(msg.prefix)
            if name:
                if name != user.name and not user.checkCapability('owner'):
                    irc.error('You may only retrieve your own hostmasks.')
                else:
                    try:
                        user = ircdb.users.getUser(name)
                        hostmasks = map(repr, user.hostmasks)
                        hostmasks.sort()
                        irc.reply(utils.commaAndify(hostmasks))
                    except KeyError:
                        irc.errorNoUser()
            else:
                irc.reply(repr(user.hostmasks))
        except KeyError:
            irc.errorNotRegistered()
    hostmasks = wrap(hostmasks, ['private', additional('something')])

    def capabilities(self, irc, msg, args, user):
        """[<name>]

        Returns the capabilities of the user specified by <name>; if <name>
        isn't specified, returns the hostmasks of the user calling the command.
        """
        irc.reply('[%s]' % '; '.join(user.capabilities))
    capabilities = wrap(capabilities, [first('otherUser', 'user')])

    def identify(self, irc, msg, args, user, password):
        """<name> <password>

        Identifies the user as <name>. This command (and all other
        commands that include a password) must be sent to the bot privately,
        not in a channel.
        """
        if user.checkPassword(password):
            try:
                user.addAuth(msg.prefix)
                ircdb.users.setUser(user)
                irc.replySuccess()
            except ValueError:
                irc.error('Your secure flag is true and your hostmask '
                          'doesn\'t match any of your known hostmasks.')
        else:
            self.log.warning('Failed identification attempt by %s (password '
                             'did not match for %s).', msg.prefix, user.name)
            irc.error(conf.supybot.replies.incorrectAuthentication())
    identify = wrap(identify, ['private', 'otherUser', 'something'])

    def unidentify(self, irc, msg, args, user):
        """takes no arguments

        Un-identifies you.  Note that this may not result in the desired
        effect of causing the bot not to recognize you anymore, since you may
        have added hostmasks to your user that can cause the bot to continue to
        recognize you.
        """
        user.clearAuth()
        ircdb.users.setUser(user)
        irc.replySuccess('If you remain recognized after giving this command, '
                         'you\'re being recognized by hostmask, rather than '
                         'by password.  You must remove whatever hostmask is '
                         'causing you to be recognized in order not to be '
                         'recognized.')
    unidentify = wrap(unidentify, ['user'])

    def whoami(self, irc, msg, args):
        """takes no arguments

        Returns the name of the user calling the command.
        """
        try:
            user = ircdb.users.getUser(msg.prefix)
            irc.reply(user.name)
        except KeyError:
            irc.reply('I don\'t recognize you.')
    whoami = wrap(whoami)

    def setsecure(self, irc, msg, args, user, password, value):
        """<password> [<True|False>]

        Sets the secure flag on the user of the person sending the message.
        Requires that the person's hostmask be in the list of hostmasks for
        that user in addition to the password being correct.  When the secure
        flag is set, the user *must* identify before he can be recognized.
        If a specific True/False value is not given, it inverts the current
        value.
        """
        if value is None:
            value = not user.secure
        if user.checkPassword(password) and \
           user.checkHostmask(msg.prefix, useAuth=False):
            user.secure = value
            ircdb.users.setUser(user)
            irc.reply('Secure flag set to %s' % value)
        else:
            irc.error(conf.supybot.replies.incorrectAuthentication())
    setsecure = wrap(setsecure, ['private', 'user', 'something',
                                 additional('boolean')])

    def stats(self, irc, msg, args):
        """takes no arguments

        Returns some statistics on the user database.
        """
        users = 0
        owners = 0
        admins = 0
        hostmasks = 0
        for user in ircdb.users.itervalues():
            users += 1
            hostmasks += len(user.hostmasks)
            try:
                if user.checkCapability('owner'):
                    owners += 1
                elif user.checkCapability('admin'):
                    admins += 1
            except KeyError:
                pass
        irc.reply('I have %s registered users '
                  'with %s registered hostmasks; '
                  '%s and %s.' % (users, hostmasks,
                                  utils.nItems('owner', owners),
                                  utils.nItems('admin', admins)))
    stats = wrap(stats)


##     def config(self, irc, msg, args):
##         """[--list] <name> [<value>]

##         Sets the user configuration variable <name> to <value>, if given.  If
##         <value> is not given, returns the current value of <name> for the user
##         giving the command.  If --list is given, lists the values in <name>.
##         """
##         try:
##             id = ircdb.users.getUserId(msg.prefix)
##         except KeyError:
##             irc.errorNoUser()
##             return
##         list = False
##         (optlist, args) = getopt.getopt(args, '', ['list'])
##         for (option, arg) in optlist:
##             if option == '--list':
##                 list = True
##         if len(args) >= 2:
##             # We're setting.
##             pass
##         else:
##             # We're getting.
##             name = privmsgs.getArgs(args)
##             if not name.startswith('users.'):
##                 name = 'users.' + name
##             try:
##                 wrapper = Config.getWrapper(name)
##                 wrapper = wrapper.get(str(id))
##             except InvalidRegistryValue, e:
##                 irc.errorInvalid('configuration variable', name, Raise=True)
##             if list:
##                 pass
##             else:
##                 irc.reply(str(wrapper))

Class = User

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

