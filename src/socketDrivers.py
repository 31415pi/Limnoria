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

import supybot.fix as fix

import time
import atexit
import select
import socket
from itertools import imap

import supybot.log as log
import supybot.conf as conf
import supybot.utils as utils
import supybot.world as world
import supybot.drivers as drivers
import supybot.ircmsgs as ircmsgs
import supybot.schedule as schedule

reconnectWaits = (0, 60, 300)
class SocketDriver(drivers.IrcDriver, drivers.ServersMixin):
    def __init__(self, irc):
        self.irc = irc
        drivers.ServersMixin.__init__(self, irc)
        drivers.IrcDriver.__init__(self) # Must come after setting irc.
        self.servers = ()
        self.eagains = 0
        self.inbuffer = ''
        self.outbuffer = ''
        self.connected = False
        self.reconnectWaitsIndex = 0
        self.reconnectWaits = reconnectWaits
        self.connect()

    def _handleSocketError(self, e):
        # (11, 'Resource temporarily unavailable') raised if connect
        # hasn't finished yet.  We'll keep track of how many we get.
        if e.args[0] != 11 and self.eagains > 120:
            drivers.log.disconnect(self.currentServer, e)
            self.reconnect(wait=True)
        else:
            log.debug('Got EAGAIN, current count: %s.', self.eagains)
            self.eagains += 1

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
                self.eagains = 0
            except socket.error, e:
                self._handleSocketError(e)

    def run(self):
        if not self.connected:
            # We sleep here because otherwise, if we're the only driver, we'll
            # spin at 100% CPU while we're disconnected.
            time.sleep(conf.supybot.drivers.poll())
            return
        self._sendIfMsgs()
        try:
            self.inbuffer += self.conn.recv(1024)
            self.eagains = 0
            lines = self.inbuffer.split('\n')
            self.inbuffer = lines.pop()
            for line in lines:
                start = time.time()
                msg = ircmsgs.IrcMsg(line)
                #log.debug('Time to parse IrcMsg: %s', time.time()-start)
                self.irc.feedMsg(msg)
        except socket.timeout:
            pass
        except socket.error, e:
            self._handleSocketError(e)
            return
        self._sendIfMsgs()

    def connect(self, **kwargs):
        self.reconnect(reset=False, **kwargs)
        
    def reconnect(self, wait=False, reset=True):
        server = self._getNextServer()
        if self.connected:
            drivers.log.reconnect(self.irc.network)
            self.conn.close()
        elif not wait:
            drivers.log.connect(self.currentServer)
        if reset:
            drivers.log.debug('Resetting %s.', self.irc)
            self.irc.reset()
        else:
            drivers.log.debug('Not resetting %s.', self.irc)
        self.connected = False
        if wait:
            self._scheduleReconnect()
            return
        try:
            self.conn = utils.getSocket(server[0])
        except socket.error, e:
            drivers.log.connectError(self.currentServer, e)
            self.reconnect(wait=True)
            return
        # We allow more time for the connect here, since it might take longer.
        # At least 10 seconds.
        self.conn.settimeout(max(10, conf.supybot.drivers.poll()*10))
        if self.reconnectWaitsIndex < len(self.reconnectWaits)-1:
            self.reconnectWaitsIndex += 1
        try:
            self.conn.connect(server)
            self.conn.settimeout(conf.supybot.drivers.poll())
        except socket.error, e:
            if e.args[0] == 115:
                now = time.time()
                when = now + 60
                whenS = log.timestamp(when)
                drivers.log.debug('Connection in progress, scheduling '
                                  'connectedness check for %s', whenS)
                schedule.addEvent(self._checkAndWriteOrReconnect, when)
            else:
                drivers.log.connectError(self.currentServer, e)
                self.reconnect(wait=True)
            return
        self.connected = True
        self.reconnectWaitPeriodsIndex = 0

    def _checkAndWriteOrReconnect(self):
        drivers.log.debug('Checking whether we are connected.')
        (_, w, _) = select.select([], [self.conn], [], 0)
        if w:
            drivers.log.debug('Socket is writable, it might be connected.')
            self.connected = True
            self.reconnectWaitPeriodsIndex = 0
        else:
            drivers.log.connectError(self.currentServer, 'Timed out')
            self.reconnect()

    def _scheduleReconnect(self):
        when = time.time() + self.reconnectWaits[self.reconnectWaitsIndex]
        if not world.dying:
            drivers.log.reconnect(self.irc.network, when)
        schedule.addEvent(self.reconnect, when)

    def die(self):
        drivers.log.die(self.irc)
        self.conn.close()
        # self.irc.die() Kill off the ircs yourself, jerk!

    def name(self):
        return '%s(%s)' % (self.__class__.__name__, self.irc)


Driver = SocketDriver

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

