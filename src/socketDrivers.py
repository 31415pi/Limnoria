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
Contains simple socket drivers.  Asyncore bugged (haha, pun!) me.
"""

from __future__ import division

__revision__ ="$Id$"

import fix

import time
import socket
from itertools import imap

import log
import conf
import world
import drivers
import ircmsgs
import schedule

instances = 0
originalPoll = conf.poll

class SocketDriver(drivers.IrcDriver):
    def __init__(self, (server, port), irc, reconnectWaits=(0, 60, 300)):
        global instances
        instances += 1
        conf.poll = originalPoll / instances
        self.server = (server, port)
        drivers.IrcDriver.__init__(self) # Must come after server is set.
        self.irc = irc
        self.irc.driver = self
        self.inbuffer = ''
        self.outbuffer = ''
        self.connected = False
        self.reconnectWaitsIndex = 0
        self.reconnectWaits = reconnectWaits
        self.reconnect()

    def _sendIfMsgs(self):
        msgs = [self.irc.takeMsg()]
        while msgs[-1] is not None:
            msgs.append(self.irc.takeMsg())
        del msgs[-1]
        self.outbuffer += ''.join(imap(str, msgs))
        if self.outbuffer:
            try:
                sent = self.conn.send(self.outbuffer)
                self.outbuffer = self.outbuffer[sent:]
            except socket.error, e:
                # (11, 'Resource temporarily unavailable') raised if connect
                # hasn't finished yet.
                if e.args[0] != 11:
                    log.warning('Disconnect from %s: %s',self.server,e.args[1])
                    self.reconnect(wait=True)
        
    def run(self):
        if not self.connected:
            time.sleep(conf.poll) # Otherwise we might spin.
            return
        self._sendIfMsgs()
        try:
            self.inbuffer += self.conn.recv(1024)
            lines = self.inbuffer.split('\n')
            self.inbuffer = lines.pop()
            for line in lines:
                start = time.time()
                msg = ircmsgs.IrcMsg(line)
                log.debug('Time to parse IrcMsg: %s', time.time()-start)
                try:
                    self.irc.feedMsg(msg)
                except:
                    log.exception('Uncaught exception outside Irc object:')
        except socket.timeout:
            pass
        except socket.error, e:
            # Same as with _sendIfMsgs.
            if e.args[0] != 11:
                log.warning('Disconnect from %s: %s', self.server, e.args[1])
                self.reconnect(wait=True)
            return
        self._sendIfMsgs()
        
    def reconnect(self, wait=False):
        if wait:
            self._scheduleReconnect()
            return
        self.conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.conn.settimeout(conf.poll*10) # Allow more time for connect.
        if self.reconnectWaitsIndex < len(self.reconnectWaits)-1:
            self.reconnectWaitsIndex += 1
        try:
            self.conn.connect(self.server)
            self.conn.settimeout(conf.poll)
        except socket.error, e:
            if e.args[0] != 115:
                log.warning('Error connecting to %s: %s', self.server, e)
                self.reconnect(wait=True)
        self.connected = True
        self.reconnectWaitPeriodsIndex = 0
        
    def die(self):
        self.irc.die()

    def _scheduleReconnect(self):
        self.irc.reset()
        if self.connected:
            self.conn.close()
        self.connected = False
        when = time.time() + self.reconnectWaits[self.reconnectWaitsIndex]
        whenS = time.strftime(conf.logTimestampFormat, time.localtime(when))
        if not world.dying:
            log.info('Scheduling reconnect to %s at %s', self.server, whenS)
        schedule.addEvent(self.reconnect, when)

    def name(self):
        return '%s%s' % (self.__class__.__name__, self.server)


Driver = SocketDriver

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

