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
Provides several commands that go out to websites and get things.
"""

import supybot

__revision__ = "$Id$"
__contributors__ = {
    supybot.authors.jemfinch: ['bender', 'cyborg', 'doctype', 'freshmeat',
                               'headers', 'netcraft', 'size', 'title'],
    supybot.authors.jamessan: ['pgpkey', 'kernel', 'filext', 'zipinfo',
                               'acronym'],
    }

import supybot.plugins as plugins

import re
import sets
import getopt
import socket
import urllib
import xml.dom.minidom
from itertools import imap

import supybot.conf as conf
import supybot.utils as utils
from supybot.commands import *
import supybot.webutils as webutils
import supybot.registry as registry
import supybot.callbacks as callbacks

conf.registerPlugin('Http')

class FreshmeatException(Exception):
    pass

class Http(callbacks.Privmsg):
    threaded = True
    _titleRe = re.compile(r'<title>(.*?)</title>', re.I | re.S)
    def __init__(self):
        self.__parent = super(Http, self)
        self.__parent.__init__()

    def callCommand(self, name, irc, msg, *L, **kwargs):
        try:
            self.__parent.callCommand(name, irc, msg, *L, **kwargs)
        except webutils.WebError, e:
            irc.error(str(e))

    def headers(self, irc, msg, args, url):
        """<url>

        Returns the HTTP headers of <url>.  Only HTTP urls are valid, of
        course.
        """
        fd = webutils.getUrlFd(url)
        try:
            s = ', '.join(['%s: %s' % (k, v) for (k, v) in fd.headers.items()])
            irc.reply(s)
        finally:
            fd.close()
    headers = wrap(headers, ['httpUrl'])

    _doctypeRe = re.compile(r'(<!DOCTYPE[^>]+>)', re.M)
    def doctype(self, irc, msg, args, url):
        """<url>

        Returns the DOCTYPE string of <url>.  Only HTTP urls are valid, of
        course.
        """
        size = conf.supybot.protocols.http.peekSize()
        s = webutils.getUrl(url, size=size)
        m = self._doctypeRe.search(s)
        if m:
            s = utils.normalizeWhitespace(m.group(0))
            irc.reply(s)
        else:
            irc.reply('That URL has no specified doctype.')
    doctype = wrap(doctype, ['httpUrl'])

    def size(self, irc, msg, args, url):
        """<url>

        Returns the Content-Length header of <url>.  Only HTTP urls are valid,
        of course.
        """
        fd = webutils.getUrlFd(url)
        try:
            try:
                size = fd.headers['Content-Length']
                irc.reply('%s is %s bytes long.' % (url, size))
            except KeyError:
                size = conf.supybot.protocols.http.peekSize()
                s = fd.read(size)
                if len(s) != size:
                    irc.reply('%s is %s bytes long.' % (url, len(s)))
                else:
                    irc.reply('The server didn\'t tell me how long %s is '
                              'but it\'s longer than %s bytes.' % (url, size))
        finally:
            fd.close()
    size = wrap(size, ['httpUrl'])

    def title(self, irc, msg, args, url):
        """<url>

        Returns the HTML <title>...</title> of a URL.
        """
        size = conf.supybot.protocols.http.peekSize()
        text = webutils.getUrl(url, size=size)
        m = self._titleRe.search(text)
        if m is not None:
            irc.reply(utils.htmlToText(m.group(1).strip()))
        else:
            irc.reply('That URL appears to have no HTML title '
                      'within the first %s bytes.' % size)
    title = wrap(title, ['httpUrl'])

    def freshmeat(self, irc, msg, args, project):
        """<project name>

        Returns Freshmeat data about a given project.
        """
        project = ''.join(project.split())
        url = 'http://www.freshmeat.net/projects-xml/%s' % project
        try:
            text = webutils.getUrl(url)
            if text.startswith('Error'):
                text = text.split(None, 1)[1]
                raise FreshmeatException, text
            dom = xml.dom.minidom.parseString(text)
            def getNode(name):
                node = dom.getElementsByTagName(name)[0]
                return str(node.childNodes[0].data)
            project = getNode('projectname_full')
            version = getNode('latest_release_version')
            vitality = getNode('vitality_percent')
            popularity = getNode('popularity_percent')
            lastupdated = getNode('date_updated')
            irc.reply('%s, last updated %s, with a vitality percent of %s '
                      'and a popularity of %s, is in version %s.' %
                      (project, lastupdated, vitality, popularity, version))
        except FreshmeatException, e:
            irc.error(str(e))
    freshmeat = wrap(freshmeat, ['text'])

    def stockquote(self, irc, msg, args, symbol):
        """<company symbol>

        Gets the information about the current price and change from the
        previous day of a given company (represented by a stock symbol).
        """
        url = 'http://finance.yahoo.com/d/quotes.csv?s=%s' \
              '&f=sl1d1t1c1ohgv&e=.csv' % symbol
        quote = webutils.getUrl(url)
        data = quote.split(',')
        if data[1] != '0.00':
            irc.reply('The current price of %s is %s, as of %s EST.  '
                      'A change of %s from the last business day.' %
                      (data[0][1:-1], data[1], data[3][1:-1], data[4]))
        else:
            m = 'I couldn\'t find a listing for %s' % symbol
            irc.error(m)
    stockquote = wrap(stockquote, ['something'])

    _cyborgRe = re.compile(r'<p class="mediumheader">(.*?)</p>', re.I)
    def cyborg(self, irc, msg, args, name):
        """[<name>]

        Returns a cyborg acronym for <name> from <http://www.cyborgname.com/>.
        If <name> is not specified, uses that of the user.
        """
        if not name:
            name = msg.nick
        name = urllib.quote(name)
        url = 'http://www.cyborgname.com/cyborger.cgi?acronym=%s' % name
        html = webutils.getUrl(url)
        m = self._cyborgRe.search(html)
        if m:
            s = m.group(1)
            s = utils.normalizeWhitespace(s)
            irc.reply(s)
        else:
            irc.errorPossibleBug('No cyborg name returned.')
    cyborg = wrap(cyborg, [additional('somethingWithoutSpaces')])

    _acronymre = re.compile(r'valign="middle" width="7\d%" bgcolor="[^"]+">'
                            r'(?:<b>)?([^<]+)')
    def acronym(self, irc, msg, args, acronym):
        """<acronym>

        Displays acronym matches from acronymfinder.com
        """
        url = 'http://www.acronymfinder.com/' \
              'af-query.asp?String=exact&Acronym=%s' % urllib.quote(acronym)
        html = webutils.getUrl(url)
        if 'daily limit' in html:
            s = 'Acronymfinder.com says I\'ve reached my daily limit.  Sorry.'
            irc.error(s)
            return
        # The following definitions are stripped and empties are removed.
        defs = filter(None, imap(str.strip, self._acronymre.findall(html)))
        utils.sortBy(lambda s: not s.startswith('[not an acronym]'), defs)
        for (i, s) in enumerate(defs):
            if s.startswith('[not an acronym]'):
                defs[i] = s.split('] ', 1)[1].strip()
        if len(defs) == 0:
            irc.reply('No definitions found.')
        else:
            s = ', or '.join(defs)
            irc.reply('%s could be %s' % (acronym, s))
    acronym = wrap(acronym, ['text'])

    _netcraftre = re.compile(r'td align="left">\s+<a[^>]+>(.*?)<a href',
                             re.S | re.I)
    def netcraft(self, irc, msg, args, hostname):
        """<hostname|ip>

        Returns Netcraft.com's determination of what operating system and
        webserver is running on the host given.
        """
        url = 'http://uptime.netcraft.com/up/graph/?host=%s' % hostname
        html = webutils.getUrl(url)
        m = self._netcraftre.search(html)
        if m:
            html = m.group(1)
            s = utils.htmlToText(html, tagReplace='').strip()
            s = s.rstrip('-').strip()
            irc.reply(s) # Snip off "the site"
        elif 'We could not get any results' in html:
            irc.reply('No results found for %s.' % hostname)
        else:
            irc.error('The format of page the was odd.')
    netcraft = wrap(netcraft, ['text'])

    def kernel(self, irc, msg, args):
        """takes no arguments

        Returns information about the current version of the Linux kernel.
        """
        fd = webutils.getUrlFd('http://kernel.org/kdist/finger_banner')
        try:
            stable = 'unknown'
            snapshot = 'unknown'
            mm = 'unknown'
            for line in fd:
                (name, version) = line.split(':')
                if 'latest stable' in name:
                    stable = version.strip()
                elif 'snapshot for the stable' in name:
                    snapshot = version.strip()
                elif '-mm patch' in name:
                    mm = version.strip()
        finally:
            fd.close()
        irc.reply('The latest stable kernel is %s; '
                  'the latest snapshot of the stable kernel is %s; '
                  'the latest beta kernel is %s.' % (stable, snapshot, mm))
    kernel = wrap(kernel)

    _pgpkeyre = re.compile(r'pub\s+\d{4}\w/<a href="([^"]+)">'
                           r'([^<]+)</a>[^>]+>([^<]+)</a>')
    def pgpkey(self, irc, msg, args, search):
        """<search words>

        Returns the results of querying pgp.mit.edu for keys that match
        the <search words>.
        """
        urlClean = search.replace(' ', '+')
        host = 'http://pgp.mit.edu:11371'
        url = '%s/pks/lookup?op=index&search=%s' % (host, urlClean)
        fd = webutils.getUrlFd(url, headers={})
        try:
            L = []
            for line in iter(fd.next, ''):
                info = self._pgpkeyre.search(line)
                if info:
                    L.append('%s <%s%s>' % (info.group(3),host,info.group(1)))
            if len(L) == 0:
                irc.reply('No results found for %s.' % search)
            else:
                s = 'Matches found for %s: %s' % (search, ' :: '.join(L))
                irc.reply(s)
        finally:
            fd.close()
    pgpkey = wrap(pgpkey, ['text'])

    _filextre = re.compile(
        r'<strong>Extension:</strong>.*?<tr>.*?</tr>\s+<tr>\s+<td colspan='
        r'"2">(?:<a href[^>]+>([^<]+)</a>\s+|([^<]+))</td>\s+<td>'
        r'(?:<a href[^>]+>([^<]+)</a>|<img src="images/spacer.gif"(.))',
        re.I|re.S)
    def extension(self, irc, msg, args, ext):
        """<ext>

        Returns the results of querying filext.com for file extensions that
        match <ext>.
        """
        # XXX This probably ought to be handled in a converter from commands.py
        invalid = '|<>\^=?/[]";,*'
        for c in invalid:
            if c in ext:
                irc.error('\'%s\' is an invalid extension character' % c)
                return
        s = 'http://www.filext.com/detaillist.php?extdetail=%s&goButton=Go'
        text = webutils.getUrl(s % ext)
        matches = self._filextre.findall(text)
        #print matches
        res = []
        for match in matches:
            (file1, file2, comp1, comp2) = match
            if file1:
                filetype = file1.strip()
            else:
                filetype = file2.strip()
            if comp1:
                company = comp1.strip()
            else:
                company = comp2.strip()
            if company:
                res.append('%s\'s %s' % (company, filetype))
            else:
                res.append(filetype)
        if res:
            irc.reply(utils.commaAndify(res))
        else:
            irc.error('No matching file extensions were found.')
    extension = wrap(extension, ['text'])

    _zipinfore = re.compile(r'Latitude<BR>\(([^)]+)\)</th><th>Longitude<BR>'
                            r'\(([^)]+)\).*?<tr>(.*?)</tr>', re.I)
    _zipstatre = re.compile(r'(Only about \d+,\d{3} of.*?in use.)')
    def zipinfo(self, irc, msg, args, zipcode):
        """<zip code>

        Returns a plethora of information for the given <zip code>.
        """
        try:
            int(zipcode)
        except ValueError:
            irc.error('Zip code must be a 5-digit integer.')
            return
        if len(zipcode) != 5:
            irc.error('Zip code must be a 5-digit integer.')
            return
        url = 'http://zipinfo.com/cgi-local/zipsrch.exe?cnty=cnty&ac=ac&'\
              'tz=tz&ll=ll&zip=%s&Go=Go' % zipcode
        text = webutils.getUrl(url)
        if 'daily usage limit' in text:
            irc.error('I have exceeded the site\'s daily usage limit.')
            return
        m = self._zipstatre.search(text)
        if m:
            irc.reply('%s  %s is not one of them.' % (m.group(1), zipcode))
            return
        n = self._zipinfore.search(text)
        if not n:
            irc.error('Unable to retrieve information for that zip code.')
            return
        (latdir, longdir, rawinfo) = n.groups()
        # Info consists of the following (whitespace separated):
        # City, State Abbrev., Zip Code, County, FIPS Code, Area Code, Time
        # Zone, Daylight Time(?), Latitude, Longitude
        info = utils.htmlToText(rawinfo)
        info = info.split()
        zipindex = info.index(zipcode)
        resp = ['City: %s' % ' '.join(info[:zipindex-1]),
                'State: %s' % info[zipindex-1],
                'County: %s' % ' '.join(info[zipindex+1:-6]),
                'Area Code: %s' % info[-5],
                'Time Zone: %s' % info[-4],
                'Daylight Savings: %s' % info[-3],
                'Latitude: %s (%s)' % (info[-2], latdir),
                'Longitude: %s (%s)' % (info[-1], longdir),
               ]
        irc.reply('; '.join(resp))
    zipinfo = wrap(zipinfo, ['text'])


Class = Http

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
