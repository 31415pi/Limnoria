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
import sys
import time
import socket
import asyncore
import asynchat

import repl
import conf
import debug
import ircdb
import world
import drivers
import ircmsgs
import ircutils
import schedule

class AsyncoreRunnerDriver(drivers.IrcDriver):
    def run(self):
        #debug.printf(asyncore.socket_map)
        try:
            asyncore.poll(conf.poll)
        except:
            debug.recoverableException()


class AsyncoreDriver(asynchat.async_chat, object):
    def __init__(self, (server, port), irc, reconnect=True):
        #debug.methodNamePrintf(self, '__init__')
        asynchat.async_chat.__init__(self)
        self.server = (server, port)
        self.reconnect = reconnect
        self.irc = irc
        self.irc.driver = self
        self.buffer = ''
        self.set_terminator('\n')
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.connect(self.server)
        except:
            debug.recoverableException('terse')
            self.scheduleReconnect()
            self.close()

    def scheduleReconnect(self):
        if self.reconnect:
            when = time.time() + 60
            whenS = time.strftime(conf.timestampFormat, time.localtime(when))
            debug.msg('Scheduling reconnect at %s' % whenS, 'normal')
            def makeNewDriver():
                self.irc.reset()
                driver = self.__class__(self.server, self.irc, self.reconnect)
                driver.irc.driver = driver
            schedule.addEvent(makeNewDriver, when)

    def writable(self):
        #debug.methodNamePrintf(self, 'writable')
        while self.connected:
            m = self.irc.takeMsg()
            if m:
                self.push(str(m))
            else:
                break
        return asynchat.async_chat.writable(self)

    def handle_error(self):
        debug.recoverableException()
        self.scheduleReconnect()
        self.close()

    def collect_incoming_data(self, s):
        #debug.methodNamePrintf(self, 'collect_incoming_data')
        self.buffer += s

    def found_terminator(self):
        #debug.methodNamePrintf(self, 'found_terminator')
        start = time.time()
        msg = ircmsgs.IrcMsg(self.buffer)
        debug.msg('Time to parse IrcMsg: %s' % (time.time()-start), 'verbose')
        self.buffer = ''
        try:
            self.irc.feedMsg(msg)
        except:
            debug.recoverableException()

    def handle_close(self):
        #debug.methodNamePrintf(self, 'handle_close')
        self.scheduleReconnect()
        self.die()

    reconnect = handle_close

    def handle_connect(self):
        pass

    def die(self):
        self.close()

    
class ReplListener(asyncore.dispatcher, object):
    def __init__(self, port=conf.telnetPort):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.set_reuse_addr()
        self.bind(('', port))
        self.listen(5)

    def handle_accept(self):
        (sock, addr) = self.accept()
        debug.msg('Connection made to telnet-REPL: ' + str(addr),'normal')
        Repl((sock, addr))


class Repl(asynchat.async_chat, object):
    filename = 'repl'
    def __init__(self, (sock, addr)):
        asynchat.async_chat.__init__(self, sock)
        self.buffer = ''
        self.prompt = """SupyBot version %s.
Python %s
Type disconnect() to disconnect.
Name: """ % (world.version, sys.version.translate(string.ascii, '\r\n'))
        self.u = None
        self.authed = False
        self.set_terminator('\r\n')
        self.repl = repl.Repl(addr[0])
        self.repl.namespace['disconnect'] = self.close
        self.push(self.prompt)
        self.tries = 0

    _re = re.compile(r'(?<!\r)\n')
    def push(self, data):
        asynchat.async_chat.push(self, self._re.sub('\r\n', data))

    def collect_incoming_data(self, data):
        if self.tries >= 3:
            self.close()
        self.buffer += data
        if len(self.buffer) > 1024:
            self.close()

    def handle_close(self):
        self.close()

    def handle_error(self):
        self.close()

    def found_terminator(self):
        if self.u is None:
            try:
                name = self.buffer
                self.buffer = ''
                self.u = ircdb.users.getUser(name)
                self.prompt = 'Password: '
            except KeyError:
                self.push('Unknown user.\n')
                self.tries += 1
                self.prompt = 'Name: '
                msg = 'Unknown user %s on telnet REPL.' % name
                debug.msg(msg,'high')
            self.push(self.prompt)
        elif self.u is not None and not self.authed:
            password = self.buffer
            self.buffer = ''
            if self.u.checkPassword(password):
                if self.u.checkCapability('owner'):
                    self.authed = True
                    self.prompt = '>>> '
                else:
                    self.push('Only owners can use this feature.\n')
                    self.close()
                    msg = 'Attempted non-owner user %s on telnet REPL' % name
                    debug.msg(msg, 'high')
            else:
                self.push('Incorrect Password.\n')
                self.prompt = 'Name: '
                self.u = None
                msg = 'Invalid password for user %s on telnet REPL.' % name
                debug.msg(msg, 'high')
            self.push(self.prompt)
        elif self.authed:
            debug.msg('Telnet REPL: %s' % self.buffer)
            ret = self.repl.addLine(self.buffer+'\r\n')
            self.buffer = ''
            if ret is not repl.NotYet:
                if ret is not None:
                    s = self._re.sub('\r\n', str(ret))
                    self.push(s)
                    self.push('\r\n')
                self.prompt = '>>> '
            else:
                self.prompt = '... '
            self.push(self.prompt)

try:
    ignore(poller)
except NameError:
    poller = AsyncoreRunnerDriver()

if conf.telnetEnable and __name__ != '__main__':
    try:
        ignore(_listener)
    except NameError:
        _listener = ReplListener()

Driver = AsyncoreDriver

if __name__ == '__main__':
    ReplListener()
    asyncore.loop()
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
