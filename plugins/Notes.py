#!/usr/bin/env python

###
# Copyright (c) 2003, Brett Kelly
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

from baseplugin import *

import time
import os.path

import sqlite

import conf
import ircdb
import privmsgs
import callbacks
import ircutils
import debug

class Notes(callbacks.Privmsg):
    
    def __init__(self):
        callbacks.Privmsg.__init__(self)
        self.filename = os.path.join(conf.dataDir, 'Notes.db')
        if os.path.exists(self.filename):
            self.db = sqlite.connect(self.filename)
            self.cursor = self.db.cursor()
        else:
            self.makeDB()

    def makeDB(self):
        "create Notes database and tables"
        self.db = sqlite.connect(self.filename, converters={'bool': bool})
        self.cursor = self.db.cursor()
        self.cursor.execute("""CREATE TABLE users (
                               id INTEGER PRIMARY KEY,
                               name TEXT UNIQUE ON CONFLICT IGNORE
                               )""")
        self.cursor.execute("""CREATE TABLE notes (
                               id INTEGER PRIMARY KEY,
                               from_id INTEGER,
                               to_id INTEGER,
                               added_at TIMESTAMP,
                               read BOOLEAN,
                               public BOOLEAN,
                               note TEXT
                               )""")
        self.cursor.execute("""CREATE INDEX users_username ON users (name)""")
        self.db.commit()
   
    def _addUser(self, username):
        "not callable from channel, used to add users to database"
        self.cursor.execute('INSERT INTO users VALUES (NULL,%s)', username)
        self.db.commit()
        
    def getUserID(self, username):
        self.cursor.execute('SELECT id FROM users where name=%s', username)
        if self.cursor.rowcount != 0:
            results = self.cursor.fetchall()
            return results[0]
        else: # this should NEVER happen
            assert False

    def getUserName(self, userid):
        self.cursor.execute('SELECT name FROM users WHERE id=%s', userid)
        if self.cursor.rowcount != 0:
            results = self.cursor.fetchall()
            return results[0]
        else:
            raise KeyError

#    def setNoteUnread(self, irc, msg, args):
#        "set a note as unread"
#        noteid = privmsgs.getArgs(args) 
#        self.cursor.execute('UPDATE notes SET read=0 where id=%s'% noteid)
#        self.db.commit()
#        irc.reply(msg, conf.replySuccess)    
    
    def sendnote(self, irc, msg, args):
        "sends a new note to an IRC user"
        # sendnote <user> <text>
        (name, note) = privmsgs.getArgs(args, needed=2)
        sender = ircutils.nickFromHostmask(msg.prefix)
        if ircdb.users.hasUser(name):
            recipient = name
        else:
            n = irc.state.nickToHostmask(name)
            recipient = ircdb.users.getUserName(n)
        self._addUser(sender)
        self._addUser(recipient)
        senderID = self.getUserID(sender)
        recipID = self.getUserID(recipient)
        if ircutils.isChannel(msg.args[0]): 
            public = 1
        else: 
            public = 0
        debug.printf(senderID)
        debug.printf(recipID)
        debug.printf(public)
        debug.printf(note)
        self.cursor.execute("""INSERT INTO notes VALUES 
                               (NULL, %s, %s, %s, %s, %s, %s)""", 
                               senderID, recipID, int(time.time()),
                               0, public, note)
        self.db.commit()
        irc.reply(msg, conf.replySuccess)

    def getnote(self, irc, msg, args):
        "retrieves a single note by unique note id"
        #  BLOODY HELL, THIS ACTUALLY WORKS!!! 
        noteid = privmsgs.getArgs(args)
        sender = ircdb.users.getUserName(msg.prefix)
        senderID = self.getUserID(sender)[0]
        self.cursor.execute("""SELECT note, to_id, public FROM notes
                               WHERE id=%s LIMIT 1""", noteid)
        note, to_id, public = self.cursor.fetchone()
        debug.printf("senderID: %s" % senderID)
        if senderID == to_id:
            if public:
                irc.reply(msg, note)
            else:
                msg.args[0] = msg.nick
                irc.reply(msg, note)
            self.cursor.execute("""UPDATE notes SET read=%s 
                                   WHERE id=%s""", (1, noteid))
            self.db.commit()
        else:
            irc.error(msg, 'Error getting note')

    def newnotes(self, irc, msg, args):
        "takes no arguments, retrieves all unread notes for the requesting user"
        sender = ircdb.users.getUserName(msg.prefix)
        senderID = self.getUserID(sender)
        self.cursor.execute("""SELECT id, from_id FROM notes
                               WHERE to_id=%d
                               AND read=0""", senderID)
        notes = self.cursor.fetchall()
        L = []
        for (id, from_id) in notes:
            sender = self.getUserName(from_id)
            L.append(r'#%d from %s;;' % (id, sender))

#    def deletenote(self, irc, msg, args):
#        "removes single note using note id"
#        noteid = privmsgs.getArgs(args)
#        sender = ircdb.users.getUserName(msg.prefix)
#        senderID = self.getUserID(sender)
#        self.cursor.execute("""SELECT to_id FROM notes
#                               WHERE id=%d""" % int(noteid))
#        to_id = self.cursor.fetchall()
#        if senderID == to_id:
#            self.cursor.execute("""DELETE FROM notes
#                                   WHERE id=%d""" % noteid)
#            self.db.commit()
#            irc.reply(msg, conf.replySuccess)
#        else:
#            irc.error(msg, 'Unable to delete note')
            
    def getnotes(self, irc, msg, args):
        "takes no arguments gets all notes for sender"
        sender = ircdb.users.getUserName(msg.prefix)
        senderID = self.getUserID(sender)
        self.cursor.execute("""SELECT id, from_id FROM notes
                               WHERE to_id=%d""" % senderID)
        notes = self.cursor.fetchall()
        L = []
        for (id, from_id) in notes:
            sender = self.getUserName(from_id)
            L.append(r'#%d from %s;;' % (id, sender))

Class = Notes
