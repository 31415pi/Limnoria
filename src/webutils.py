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

__revision__ = "$Id$"

import supybot.fix as fix

import re
import socket
import urllib
import urllib2
import httplib
import urlparse

import supybot.conf as conf

Request = urllib2.Request
urlquote = urllib.quote
urlunquote = urllib.unquote

class WebError(Exception):
    pass

# XXX We should tighten this up a bit.
urlRe = re.compile(r"(\w+://[^\])>\s]+)", re.I)
httpUrlRe = re.compile(r"(https?://[^\])>\s]+)", re.I)

REFUSED = 'Connection refused.'
TIMED_OUT = 'Connection timed out.'
UNKNOWN_HOST = 'Unknown host.'
RESET_BY_PEER = 'Connection reset by peer.'
FORBIDDEN = 'Client forbidden from accessing URL.'

def strError(e):
    try:
        n = e.args[0]
    except Exception:
        return str(e)
    if n == 111:
        return REFUSED
    elif n in (110, 10060):
        return TIMED_OUT
    elif n == 104:
        return RESET_BY_PEER
    elif n in (8, 3):
        return UNKNOWN_HOST
    elif n == 403:
        return FORBIDDEN
    else:
        return str(e)

_headers = {
    'User-agent': 'Mozilla/4.0 (compatible; Supybot %s)' % conf.version,
    }

def getUrlFd(url, headers=None):
    """Gets a file-like object for a url."""
    if headers is None:
        headers = _headers
    try:
        if not isinstance(url, urllib2.Request):
            if '#' in url:
                url = url[:url.index('#')]
            request = urllib2.Request(url, headers=headers)
        else:
            request = url
        httpProxy = conf.supybot.protocols.http.proxy()
        if httpProxy:
            request.set_proxy(httpProxy, 'http')
        fd = urllib2.urlopen(request)
        return fd
    except socket.timeout, e:
        raise WebError, TIMED_OUT
    except (socket.error, socket.sslerror), e:
        raise WebError, strError(e)
    except httplib.InvalidURL, e:
        raise WebError, 'Invalid URL: %s' % e
    except urllib2.HTTPError, e:
        raise WebError, strError(e)
    except urllib2.URLError, e:
        raise WebError, strError(e.reason)
    # Raised when urllib doesn't recognize the url type
    except ValueError, e:
        raise WebError, strError(e)

def getUrl(url, size=None, headers=None):
    """Gets a page.  Returns a string that is the page gotten."""
    fd = getUrlFd(url, headers=headers)
    try:
        if size is None:
            text = fd.read()
        else:
            text = fd.read(size)
    except socket.timeout, e:
        raise WebError, TIMED_OUT
    fd.close()
    return text

def getDomain(url):
    return urlparse.urlparse(url)[1]

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:

