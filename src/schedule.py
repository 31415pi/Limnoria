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
Schedule plugin with a subclass of drivers.IrcDriver in order to be run as a
Supybot driver.
"""

__revision__ = "$Id$"

import fix

import time
import heapq

import drivers

class mytuple(tuple):
    def __cmp__(self, other):
        return cmp(self[0], other[0])
    def __le__(self, other):
        return self[0] <= other[0]
    def __lt__(self, other):
        return self[0] < other[0]
    def __gt__(self, other):
        return self[0] > other[0]
    def __ge__(self, other):
        return self[0] >= other[0]

class Schedule(drivers.IrcDriver):
    """An IrcDriver to handling scheduling of events.

    Events, in this case, are functions accepting no arguments.
    """
    def __init__(self):
        drivers.IrcDriver.__init__(self)
        self.schedule = []
        self.events = {}
        self.counter = 0

    def addEvent(self, f, t, name=None):
        """Schedules an event f to run at time t.

        name must be hashable and not an int.
        """
        if name is None:
            name = self.counter
            self.counter += 1
        elif isinstance(name, int):
            raise ValueError, 'int names are reserved for the scheduler.'
        assert name not in self.events
        self.events[name] = f
        heapq.heappush(self.schedule, mytuple((t, name)))

    def removeEvent(self, name):
        """Removes the event with the given name from the schedule."""
        del self.events[name]
        heapq.heappop(self.schedule)
        self.schedule = [(t, n) for (t, n) in self.schedule if n != name]

    def addPeriodicEvent(self, f, t, name=None):
        """Adds a periodic event that is called every t seconds."""
        def wrapper():
            f()
            self.addEvent(wrapper, time.time() + t, name)
        wrapper()

    removePeriodicEvent = removeEvent

    def run(self):
        while self.schedule and self.schedule[0][0] < time.time():
            (t, name) = heapq.heappop(self.schedule)
            f = self.events[name]
            del self.events[name]
            f()

try:
    ignore(schedule)
except NameError:
    schedule = Schedule()

addEvent = schedule.addEvent
removeEvent = schedule.removeEvent
addPeriodicEvent = schedule.addPeriodicEvent
removePeriodicEvent = removeEvent
run = schedule.run
# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
