###
# Copyright (c) 2003-2004, James Vega
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
Accesses Sourceforge.net for various things
"""

import supybot

__revision__ = "$Id$"
__author__ = supybot.authors.jamessan

import re
import sets
import getopt

from itertools import ifilter, imap

import rssparser

import supybot.conf as conf
import supybot.utils as utils
import supybot.plugins as plugins
from supybot.commands import *
import supybot.ircutils as ircutils
import supybot.registry as registry
import supybot.webutils as webutils
import supybot.callbacks as callbacks


def configure(advanced):
    from supybot.questions import output, expect, anything, something, yn
    conf.registerPlugin('Sourceforge', True)
    output("""The Sourceforge plugin has the functionality to watch for URLs
              that match a specific pattern (we call this a snarfer). When
              supybot sees such a URL, he will parse the web page for
              information and reply with the results.""")
    if yn('Do you want this snarfer to be enabled by default?'):
        conf.supybot.plugins.Sourceforge.trackerSnarfer.setValue(True)

    output("""The bugs and rfes commands of the Sourceforge plugin can be set
              to query a default project when no project is specified.  If this
              project is not set, calling either of those commands will display
              the associated help.  With the default project set, calling
              bugs/rfes with no arguments will find the most recent bugs/rfes
              for the default project.""")
    if yn('Do you want to specify a default project?'):
        project = anything('Project name:')
        if project:
            conf.supybot.plugins.Sourceforge.defaultProject.set(project)

    output("""Sourceforge is quite the word to type, and it may get annoying
              typing it all the time because Supybot makes you use the plugin
              name to disambiguate calls to ambiguous commands (i.e., the bug
              command is in this plugin and the Bugzilla plugin; if both are
              loaded, you\'ll have you type "sourceforge bug ..." to get this
              bug command).  You may save some time by making an alias for
              "sourceforge".  We like to make it "sf".""")

class TrackerError(Exception):
    pass

conf.registerPlugin('Sourceforge')
conf.registerChannelValue(conf.supybot.plugins.Sourceforge, 'trackerSnarfer',
    registry.Boolean(False, """Determines whether the bot will reply to SF.net
    Tracker URLs in the channel with a nice summary of the tracker item."""))
conf.registerChannelValue(conf.supybot.plugins.Sourceforge, 'defaultProject',
    registry.String('', """Sets the default project to use in the case that no
    explicit project is given."""))
conf.registerGlobalValue(conf.supybot.plugins.Sourceforge, 'bold',
    registry.Boolean(True, """Determines whether the results are bolded."""))
conf.registerGlobalValue(conf.supybot.plugins.Sourceforge,
    'enableSpecificTrackerCommands', registry.Boolean(True, """Determines
    whether the bug, rfe, and patch commands (convenience wrappers around
    the tracker command) will be enabled."""))

class Sourceforge(callbacks.PrivmsgCommandAndRegexp):
    """
    Module for Sourceforge stuff. Currently contains commands to query a
    project's most recent bugs and rfes.
    """
    threaded = True
    callBefore = ['URL']
    regexps = ['sfSnarfer']

    _reopts = re.I
    _infoRe = re.compile(r'<td nowrap>(\d+)</td><td><a href='
                         r'"([^"]+)">([^<]+)</a>', re.I)
    _hrefOpts = '&set=custom&_assigned_to=0&_status=%s&_category=100' \
                '&_group=100&order=artifact_id&sort=DESC'
    _resolution=re.compile(r'<b>(Resolution):</b> <a.+?<br>(.+?)</td>',_reopts)
    _assigned=re.compile(r'<b>(Assigned To):</b> <a.+?<br>(.+?)</td>', _reopts)
    _submitted = re.compile(r'<b>(Submitted By):</b><br>([^-]+) - '
                            r'(?:nobody|<a href)', _reopts)
    _submitDate = re.compile(r'<b>(Date Submitted):</b><br>([^<]+)</', _reopts)
    _priority = re.compile(r'<b>(Priority):</b> <a.+?<br>(.+?)</td>', _reopts)
    _status = re.compile(r'<b>(Status):</b> <a.+?<br>(.+?)</td>', _reopts)
    _regexps =(_resolution, _submitDate, _submitted, _assigned, _priority,
               _status)
    _statusOpt = {'any':100, 'open':1, 'closed':2, 'deleted':3, 'pending':4}
    _optDict = {'any':'', 'open':'', 'closed':'', 'deleted':'', 'pending':''}

    _projectURL = 'http://sourceforge.net/projects/'
    _trackerURL = 'http://sourceforge.net/support/tracker.php?aid='
    def __init__(self):
        self.__parent = super(Sourceforge, self)
        self.__parent.__init__()
        self.__class__.sf = self.__class__.sourceforge

    def isCommand(self, name):
        if name in ('bug', 'rfe', 'patch'):
            return self.registryValue('enableSpecificTrackerCommands')
        else:
            return self.__parent.isCommand(name)

    def _formatResp(self, text, num=''):
        """
        Parses the Sourceforge query to return a list of tuples that
        contain the tracker information.
        """
        if num:
            for item in ifilter(lambda s, n=num: s and n in s,
                                self._infoRe.findall(text)):
                if self.registryValue('bold'):
                    yield (ircutils.bold(utils.htmlToText(item[2])),
                            utils.htmlToText(item[1]))
                else:
                    yield (utils.htmlToText(item[2]),
                            utils.htmlToText(item[1]))
        else:
            for item in ifilter(None, self._infoRe.findall(text)):
                if self.registryValue('bold'):
                    yield (ircutils.bold(item[0]), utils.htmlToText(item[2]))
                else:
                    yield (item[0], utils.htmlToText(item[2]))

    def _getTrackerURL(self, project, regex, status):
        """
        Searches the project's Summary page to find the proper tracker link.
        """
        try:
            text = webutils.getUrl('%s%s' % (self._projectURL, project))
            m = regex.search(text)
            if m is None:
                raise TrackerError, 'Invalid Tracker page'
            else:
                return 'http://sourceforge.net%s%s' % (utils.htmlToText(
                    m.group(1)), self._hrefOpts % self._statusOpt[status])
        except webutils.WebError, e:
            raise callbacks.Error, str(e)

    def _getTrackerList(self, url):
        """
        Searches the tracker list page and returns a list of the trackers.
        """
        try:
            text = webutils.getUrl(url)
            if "No matches found." in text:
                return 'No trackers were found.'
            head = '#%s: %s'
            resp = [head % entry for entry in self._formatResp(text)]
            if resp:
                if len(resp) > 10:
                    resp = imap(lambda s: utils.ellipsisify(s, 50), resp)
                return '%s' % utils.commaAndify(resp)
            raise callbacks.Error, 'No Trackers were found.  (%s)' % \
                  conf.supybot.replies.possibleBug()
        except webutils.WebError, e:
            raise callbacks.Error, str(e)

    _bold = lambda self, m: (ircutils.bold(m[0]),) + m[1:]
    _sfTitle = re.compile(r'Detail:(\d+) - ([^<]+)</title>', re.I)
    _linkType = re.compile(r'(\w+ \w+|\w+): Tracker Detailed View', re.I)
    def _getTrackerInfo(self, url):
        """
        Parses the specific tracker page, returning useful information.
        """
        try:
            bold = self.registryValue('bold')
            s = webutils.getUrl(url)
            resp = []
            head = ''
            m = self._linkType.search(s)
            n = self._sfTitle.search(s)
            if m and n:
                linktype = m.group(1)
                linktype = utils.depluralize(linktype)
                (num, desc) = n.groups()
                if bold:
                    head = '%s #%s: %s' % (ircutils.bold(linktype), num, desc)
                else:
                    head = '%s #%s: %s' % (linktype, num, desc)
                resp.append(head)
            else:
                return None
            for r in self._regexps:
                m = r.search(s)
                if m:
                    if bold:
                        resp.append('%s: %s' % self._bold(m.groups()))
                    else:
                        resp.append('%s: %s' % m.groups())
            return '; '.join(resp)
        except webutils.WebError, e:
            raise TrackerError, str(e)

    def bug(self, irc, msg, args, id):
        """<id>

        Returns a description of the bug with id <id>.  Really, this is
        just a wrapper for the tracker command; it won't even complain if the
        <id> you give isn't a bug.
        """
        self.tracker(irc, msg, args, id)
    bug = wrap(bug, [('id', 'bug')])

    def patch(self, irc, msg, args, id):
        """<id>

        Returns a description of the patch with id <id>.  Really, this is
        just a wrapper for the tracker command; it won't even complain if the
        <id> you give isn't a patch.
        """
        self.tracker(irc, msg, args, id)
    patch = wrap(patch, [('id', 'patch')])

    def rfe(self, irc, msg, args, id):
        """<id>

        Returns a description of the rfe with id <id>.  Really, this is
        just a wrapper for the tracker command; it won't even complain if the
        <id> you give isn't an rfe.
        """
        self.tracker(irc, msg, args, id)
    rfe = wrap(rfe, [('id', 'rfe')])

    def tracker(self, irc, msg, args, id):
        """<id>

        Returns a description of the tracker with id <id> and the corresponding
        url.
        """
        try:
            url = '%s%s' % (self._trackerURL, id)
            resp = self._getTrackerInfo(url)
            if resp is None:
                irc.error('Invalid Tracker page snarfed: %s' % url)
            else:
                irc.reply('%s <%s>' % (resp, url))
        except TrackerError, e:
            irc.error(str(e))
    tracker = wrap(tracker, [('id', 'tracker')])

    _trackerLink = {'bugs': re.compile(r'"([^"]+)">Bugs'),
                    'rfes': re.compile(r'"([^"]+)">RFE'),
                    'patches': re.compile(r'"([^"]+)">Patches'),
                   }
    def _trackers(self, irc, args, msg, optlist, project, tracker):
        status = 'open'
        for (option, _) in optlist:
            if option in self._statusOpt:
                status = option
        try:
            int(project)
            s = 'Use the tracker command to get information about a specific '\
                'tracker.'
            irc.error(s)
            return
        except ValueError:
            pass
        if not project:
            project = self.registryValue('defaultProject', msg.args[0])
            if not project:
                raise callbacks.ArgumentError
        try:
            url = self._getTrackerURL(project, self._trackerLink[tracker],
                                      status)
        except TrackerError, e:
            irc.error('%s.  I can\'t find the %s link.' %
                      (e, tracker.capitalize()))
            return
        irc.reply(self._getTrackerList(url))

    def bugs(self, irc, msg, args, optlist, project):
        """[--{any,open,closed,deleted,pending}] [<project>]

        Returns a list of the most recent bugs filed against <project>.
        <project> is not needed if there is a default project set.  Search
        defaults to open bugs.
        """
        self._trackers(irc, args, msg, optlist, project, 'bugs')
    bugs = wrap(bugs, [getopts(_optDict), additional('text', '')])

    def rfes(self, irc, msg, args, optlist, project):
        """[--{any,open,closed,deleted,pending}] [<project>]

        Returns a list of the most recent rfes filed against <project>.
        <project> is not needed if there is a default project set.  Search
        defaults to open rfes.
        """
        self._trackers(irc, args, msg, optlist, project, 'rfes')
    rfes = wrap(rfes, [getopts(_optDict), additional('text', '')])

    def patches(self, irc, msg, args, optlist, project):
        """[--{any,open,closed,deleted,pending}] [<project>]

        Returns a list of the most recent patches filed against <project>.
        <project> is not needed if there is a default project set.  Search
        defaults to open patches.
        """
        self._trackers(irc, args, msg, optlist, project, 'patches')
    patches = wrap(patches, [getopts(_optDict), additional('text', '')])

    _intRe = re.compile(r'(\d+)')
    _percentRe = re.compile(r'([\d.]+%)')
    def stats(self, irc, msg, args, project):
        """[<project>]

        Returns the current statistics for <project>.  <project> is not needed
        if there is a default project set.
        """
        url = 'http://sourceforge.net/' \
              'export/rss2_projsummary.php?project=' + project
        results = rssparser.parse(url)
        if not results['items']:
            irc.errorInvalid('SourceForge project name', project)
        class x:
            pass
        def get(r, s):
            m = r.search(s)
            if m is not None:
                return m.group(0)
            else:
                irc.error('Sourceforge gave me a bad RSS feed.', Raise=True)
        def gets(r, s):
            L = []
            for m in r.finditer(s):
                L.append(m.group(1))
            return L
        def afterColon(s):
            return s.split(': ', 1)[-1]
        for item in results['items']:
            title = item['title']
            description = item['description']
            if 'Project name' in title:
                x.project = afterColon(title)
            elif 'Developers on project' in title:
                x.devs = get(self._intRe, title)
            elif 'Activity percentile' in title:
                x.activity = get(self._percentRe, title)
                x.ranking = get(self._intRe, afterColon(description))
            elif 'Downloadable files' in title:
                x.downloads = get(self._intRe, title)
                x.downloadsToday = afterColon(description)
            elif 'Tracker: Bugs' in title:
                (x.bugsOpen, x.bugsTotal) = gets(self._intRe, title)
            elif 'Tracker: Patches' in title:
                (x.patchesOpen, x.patchesTotal) = gets(self._intRe, title)
            elif 'Tracker: Feature' in title:
                (x.rfesOpen, x.rfesTotal) = gets(self._intRe, title)
        irc.reply('%s has %s, '
                  'is %s active (ranked %s), '
                  'has had %s (%s today), '
                  'has %s (out of %s), '
                  'has %s (out of %s), '
                  'and has %s (out of %s).' %
                  (x.project, utils.nItems('developer', x.devs),
                   x.activity, x.ranking,
                   utils.nItems('download', x.downloads), x.downloadsToday,
                   utils.nItems('bug', x.bugsOpen, 'open'), x.bugsTotal,
                   utils.nItems('rfe', x.rfesOpen, 'open'), x.rfesTotal,
                   utils.nItems('patch',x.patchesOpen, 'open'), x.patchesTotal))
    stats = wrap(stats, ['lowered'])

    _totbugs = re.compile(r'Bugs</a>\s+?\( <b>([^<]+)</b>', re.S | re.I)
    def _getNumBugs(self, project):
        text = webutils.getUrl('%s%s' % (self._projectURL, project))
        m = self._totbugs.search(text)
        if m:
            return m.group(1)
        else:
            return ''

    _totrfes = re.compile(r'Feature Requests</a>\s+?\( <b>([^<]+)</b>',
                          re.S | re.I)
    def _getNumRfes(self, project):
        text = webutils.getUrl('%s%s' % (self._projectURL, project))
        m = self._totrfes.search(text)
        if m:
            return m.group(1)
        else:
            return ''

    def total(self, irc, msg, args, type, project):
        """{bugs,rfes} [<project>]

        Returns the total count of open bugs or rfes.  <project> is only
        necessary if a default project is not set.
        """
        if type == 'bugs':
            self._totalbugs(irc, msg, project)
        elif type == 'rfes':
            self._totalrfes(irc, msg, project)
    total = wrap(total, [literal(('bugs', 'rfes')), additional('something')])

    def _totalbugs(self, irc, msg, project):
        project = project or self.registryValue('defaultProject', msg.args[0])
        total = self._getNumBugs(project)
        if total:
            irc.reply(total)
        else:
            irc.error('Could not find bug statistics for %s.' % project)

    def _totalrfes(self, irc, msg, project):
        project = project or self.registryValue('defaultProject', msg.args[0])
        total = self._getNumRfes(project)
        if total:
            irc.reply(total)
        else:
            irc.error('Could not find RFE statistics for %s.' % project)

    def fight(self, irc, msg, args, optlist, projects):
        """[--{bugs,rfes}] [--{open,closed}] <project name> <project name> \
        [<project name> ...]

        Returns the projects, in order, from greatest number of bugs to least.
        Defaults to bugs and open.
        """
        search = self._getNumBugs
        type = 0
        for (option, _) in optlist:
            if option == 'bugs':
                search = self._getNumBugs
            if option == 'rfes':
                search = self._getNumRfes
            if option == 'open':
                type = 0
            if option == 'closed':
                type = 1
        results = []
        for proj in projects:
            num = search(proj)
            if num:
                results.append((int(num.split('/')[type].split()[0]), proj))
        results.sort()
        results.reverse()
        s = ', '.join(['\'%s\': %s' % (s, i) for (i, s) in results])
        irc.reply(s)
    fight = wrap(fight, [getopts({'bugs':'','rfes':'','open':'','closed':''}),
                         many('text')])

    def sfSnarfer(self, irc, msg, match):
        r"https?://(?:www\.)?(?:sourceforge|sf)\.net/tracker/" \
        r".*\?(?:&?func=detail|&?aid=\d+|&?group_id=\d+|&?atid=\d+){4}"
        if not self.registryValue('trackerSnarfer', msg.args[0]):
            return
        try:
            url = match.group(0)
            resp = self._getTrackerInfo(url)
            if resp is None:
                self.log.warning('Invalid Tracker page snarfed: %s', url)
            else:
                irc.reply(resp, prefixName=False)
        except TrackerError, e:
            self.log.warning(str(e))
    sfSnarfer = urlSnarfer(sfSnarfer)

Class = Sourceforge

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
