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

import os
import sys
import time
import types
import atexit
import logging

import ansi
import conf
import utils
import registry

deadlyExceptions = [KeyboardInterrupt, SystemExit]

class Formatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return timestamp(record.created)

    def formatException(self, (E, e, tb)):
        for exn in deadlyExceptions:
            if issubclass(e.__class__, exn):
                raise
        return logging.Formatter.formatException(self, (E, e, tb))


class BetterStreamHandler(logging.StreamHandler):
    def emit(self, record):
        msg = self.format(record)
        if not hasattr(types, "UnicodeType"): #if no unicode support...
            self.stream.write("%s\n" % msg)
        else:
            try:
                self.stream.write("%s\n" % msg)
            except UnicodeError:
                self.stream.write("%s\n" % msg.encode("UTF-8"))
        self.flush()


class StdoutStreamHandler(BetterStreamHandler):
    def disable(self):
        self.setLevel(sys.maxint) # Just in case.
        _logger.removeHandler(self)
        logging._acquireLock()
        try:
            del logging._handlers[self]
        finally:
            logging._releaseLock()

    def emit(self, record):
        if conf.supybot.log.stdout():
            try:
                BetterStreamHandler.emit(self, record)
            except ValueError, e: # Raised if sys.stdout is closed.
                self.disable()
                error('Error logging to stdout.  Removing stdout handler.')
                exception('Uncaught exception in StdoutStreamHandler:')
            

class BetterFileHandler(logging.FileHandler):
    def emit(self, record):
        msg = self.format(record)
        if not hasattr(types, "UnicodeType"): #if no unicode support...
            self.stream.write("%s\n" % msg)
        else:
            try:
                self.stream.write("%s\n" % msg)
            except UnicodeError:
                self.stream.write("%s\n" % msg.encode("UTF-8"))
        self.flush()


class ColorizedFormatter(Formatter):
    def formatException(self, (E, e, tb)):
        if conf.supybot.log.stdout.colorized():
            return ''.join([ansi.BOLD, ansi.RED,
                            Formatter.formatException(self, (E, e, tb)),
                            ansi.RESET])
        else:
            return Formatter.formatException(self, (E, e, tb))

    def format(self, record, *args, **kwargs):
        if conf.supybot.log.stdout.colorized():
            color = ''
            if record.levelno == logging.CRITICAL:
                color = ansi.WHITE + ansi.BOLD
            elif record.levelno == logging.ERROR:
                color = ansi.RED
            elif record.levelno == logging.WARNING:
                color = ansi.YELLOW
            return ''.join([color,
                            Formatter.format(self, record, *args, **kwargs),
                            ansi.RESET])
        else:
            return Formatter.format(self, record, *args, **kwargs)

# These are public.
formatter = Formatter('%(levelname)s %(asctime)s %(message)s')
pluginFormatter = Formatter('%(levelname)s %(asctime)s %(name)s %(message)s')

# These are not.
_logger = logging.getLogger('supybot')
debug = _logger.debug
info = _logger.info
warning = _logger.warning
error = _logger.error
critical = _logger.critical
exception = _logger.exception

setLevel = _logger.setLevel

atexit.register(logging.shutdown)

def getPluginLogger(name):
    if not conf.supybot.log.individualPluginLogfiles():
        return _logger
    log = logging.getLogger('supybot.plugins.%s' % name)
    if not log.handlers:
        filename = os.path.join(pluginLogDir, '%s.log' % name)
        handler = BetterFileHandler(filename)
        handler.setLevel(-1)
        handler.setFormatter(pluginFormatter)
        log.addHandler(handler)
    if name in sys.modules:
        # Let's log the version, this might be useful.
        module = sys.modules[name]
        try:
            if hasattr(module, '__revision__'):
                version = module.__revision__.split()[2]
                log.info('Starting log for %s (revision %s)', name, version)
            else:
                debug('Module %s has no __revision__ string.', name)
                log.info('Starting log for %s.', name)
        except IndexError:
            log.debug('Improper __revision__ string in %s.', name)
            log.info('Starting log for %s.', name)
    return log

def timestamp(when=None):
    if when is None:
        when = time.time()
    format = conf.supybot.log.timestampFormat()
    t = time.localtime(when)
    if format:
        return time.strftime(format, t)
    else:
        return str(int(time.mktime(t)))

def firewall(f, errorHandler=None):
    def logException(self, s=None):
        if s is None:
            s = 'Uncaught exception'
        if hasattr(self, 'log'):
            self.log.exception('%s:', s)
        else:
            exception('%s in %s.%s:', s, self.__class__.__name__, f.func_name)
    def m(self, *args, **kwargs):
        try:
            return f(self, *args, **kwargs)
        except Exception, e:
            logException(self)
            if errorHandler is not None:
                try:
                    errorHandler(self, *args, **kwargs)
                except Exception, e:
                    logException(self, 'Uncaught exception in errorHandler')
                    
    m = utils.changeFunctionName(m, f.func_name, f.__doc__)
    return m

class MetaFirewall(type):
    def __new__(cls, name, bases, dict):
        firewalled = {}
        for base in bases:
            if hasattr(base, '__firewalled__'):
                firewalled.update(base.__firewalled__)
        if '__firewalled__' in dict:
            firewalled.update(dict['__firewalled__'])
        for attr in firewalled:
            if attr in dict:
                try:
                    errorHandler = firewalled[attr]
                except:
                    errorHandler = None
                dict[attr] = firewall(dict[attr], errorHandler)
        return type.__new__(cls, name, bases, dict)


class LogLevel(registry.Value):
    """Invalid log level.  Value must be either DEBUG, INFO, WARNING, ERROR,
    or CRITICAL."""
    def set(self, s):
        s = s.upper()
        try:
            self.setValue(getattr(logging, s))
            _logger.setLevel(self.value) # _logger defined later.
        except AttributeError:
            self.error()

    def __str__(self):
        return logging.getLevelName(self.value)
    
conf.supybot.directories.register('log', registry.String('logs', """Determines
what directory the bot will store its logfiles in."""))

conf.supybot.register('log')
conf.supybot.log.register('level', LogLevel(logging.INFO, """Determines what
the minimum priority level logged will be.  Valid values are DEBUG, INFO,
WARNING, ERROR, and CRITICAL, in order of increasing priority."""))
conf.supybot.log.register('stdout', registry.Boolean(True, """Determines
whether the bot will log to stdout."""))
conf.supybot.log.register('individualPluginLogfiles', registry.Boolean(True,
    """Determines whether the bot will separate plugin logs into their own
    individual logfiles."""))

class BooleanRequiredFalseOnWindows(registry.Boolean):
    def set(self, s):
        registry.Boolean.set(self, s)
        if self.value and os.name == 'nt':
            raise InvalidRegistryValue, 'Value cannot be true on Windows.'
        
conf.supybot.log.stdout.register('colorized',
BooleanRequiredFalseOnWindows(False, """Determines whether the bot's logs to
stdout (if enabled) will be colorized with ANSI color."""))

conf.supybot.log.register('timestampFormat',
registry.String('[%d-%b-%Y %H:%M:%S]',
"""Determines the format string for timestamps in logfiles.  Refer to the
Python documentation for the time module to see what formats are accepted.
If you set this variable to the empty string, times will be logged in a
simple seconds-since-epoch format."""))
if not os.path.exists(conf.supybot.directories.log()):
    os.mkdir(conf.supybot.directories.log(), 0755)

pluginLogDir = os.path.join(conf.supybot.directories.log(), 'plugins')

if not os.path.exists(pluginLogDir):
    os.mkdir(pluginLogDir, 0755)

_handler = BetterFileHandler(os.path.join(conf.supybot.directories.log(),
                                          'misc.log'))
_handler.setFormatter(formatter)
_handler.setLevel(-1)
_logger.addHandler(_handler)
_logger.setLevel(conf.supybot.log.level())

_stdoutHandler = StdoutStreamHandler(sys.stdout)
_formatString = '%(name)s: %(levelname)s %(message)s'
_stdoutFormatter = ColorizedFormatter(_formatString)
_stdoutHandler.setFormatter(_stdoutFormatter)
_stdoutHandler.setLevel(-1)
_logger.addHandler(_stdoutHandler)


# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

