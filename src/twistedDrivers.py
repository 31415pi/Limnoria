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

__revision__ = "$Id$"

import fix

import time

import log
import conf
import ircdb
import drivers
import ircmsgs

from twisted.internet import reactor
from twisted.manhole.telnet import Shell, ShellFactory
from twisted.protocols.basic import LineReceiver
from twisted.internet.protocol import ReconnectingClientFactory

class TwistedRunnerDriver(drivers.IrcDriver):
    def run(self):
        try:
            reactor.iterate(conf.poll)
        except:
            log.exception('Uncaught exception outside reactor:')

class SupyIrcProtocol(LineReceiver):
    delimiter = '\n'
    MAX_LENGTH = 1024
    def __init__(self):
        self.mostRecentCall = reactor.callLater(1, self.checkIrcForMsgs)

    def lineReceived(self, line):
        start = time.time()
        msg = ircmsgs.IrcMsg(line)
        log.debug('Time to parse IrcMsg: %s', time.time()-start)
        try:
            self.factory.irc.feedMsg(msg)
        except:
            log.exception('Uncaught exception outside Irc object:')

    def checkIrcForMsgs(self):
        if self.connected:
            msg = self.factory.irc.takeMsg()
            if msg:
                self.transport.write(str(msg))
        self.mostRecentCall = reactor.callLater(1, self.checkIrcForMsgs)

    def connectionLost(self, failure):
        self.mostRecentCall.cancel()
        self.factory.irc.reset()
        log.warning(failure.getErrorMessage())

    def connectionMade(self):
        self.factory.irc.driver = self

    def die(self):
        self.factory.continueTrying = False
        self.transport.loseConnection()

    def reconnect(self):
        self.transport.loseConnection()


class SupyReconnectingFactory(ReconnectingClientFactory):
    maxDelay = 600
    protocol = SupyIrcProtocol
    def __init__(self, (server, port), irc):
        self.irc = irc
        self.server = (server, port)
        reactor.connectTCP(server, port, self)

    def die(self):
        pass


class MyShell(Shell):
    def checkUserAndPass(self, username, password):
        try:
            id = ircdb.users.getUserId(username)
            u = ircdb.users.getUser(id)
            if u.checkPassword(password) and u.checkCapability('owner'):
                return True
            else:
                return False
        except KeyError:
            return False

class MyShellFactory(ShellFactory):
    protocol = MyShell

if conf.telnetEnable and __name__ != '__main__':
    reactor.listenTCP(conf.telnetPort, MyShellFactory())


Driver = SupyReconnectingFactory

try:
    ignore(poller)
except NameError:
    poller = TwistedRunnerDriver()
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
