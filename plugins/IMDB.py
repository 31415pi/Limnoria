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
Does various (well, only one at the moment :)) things with the Internet Movie
Database.
"""

from baseplugin import *

import IMDb

import utils
import ircutils
import privmsgs
import callbacks


def configure(onStart, afterConnect, advanced):
    # This will be called by setup.py to configure this module.  onStart and
    # afterConnect are both lists.  Append to onStart the commands you would
    # like to be run when the bot is started; append to afterConnect the
    # commands you would like to be run when the bot has finished connecting.
    from questions import expect, anything, something, yn
    onStart.append('load IMDB')

class IMDB(callbacks.Privmsg):
    threaded = True
    def imdb(self, irc, msg, args):
        """<movie title>

        Returns the IMDB information on the movie given.
        """
        movie = privmsgs.getArgs(args)
        db = IMDb.IMDb()
        movies = db.search(movie)
        if len(movies) == 0:
            irc.reply(msg, 'No movies matched that title.')
        elif len(movies) == 1:
            movie = movies[0]
            title = utils.unCommaThe(movie.title())
            genres = utils.commaAndify(map(str.lower, movie.genres()))
            s = '"%s" (%s) belongs to the %s genres.  ' \
                'It\'s been rated %s out of 10.  ' \
                'More information is available at <%s>' % \
                (title, movie.year(), genres, movie.rating(), movie.url)
            irc.reply(msg, s)
        elif len(movies) > 20:
            s = 'More than 20 movies matched, please narrow your search.'
            irc.reply(msg, s)
        else:
            titles = ['%s (%s)' % \
                      (utils.unCommaThe(movie.title()), movie.year())
                      for movie in movies]
            if ircutils.shrinkList(titles, ', ', 425):
                irc.reply(msg, '%s movies matched, please narrow your search')
            else:
                irc.reply(msg, 'Matches: ' + utils.commaAndify(titles))


Class = IMDB

# vim:set shiftwidth=4 tabstop=8 expandtab textwidth=78:
