#!/usr/bin/env python

import supybot

import fix

import os
import sys
import pydoc
import pprint
import socket
import optparse
import textwrap

import ansi
import conf
import debug
import utils
import ircutils

debug.minimumPriority = 'high'

useColor = False

def wrapWithBold(f):
    def ff(*args, **kwargs):
        if useColor:
            sys.stdout.write(ansi.BOLD)
        ret = f(*args, **kwargs)
        if useColor:
            print ansi.RESET
        return ret
    return ff

from questions import yn, anything, something, expect
yn = wrapWithBold(yn)
expect = wrapWithBold(expect)
anything = wrapWithBold(anything)
something = wrapWithBold(something)

def getPlugins():
    filenames = []
    for dir in conf.pluginDirs:
        filenames.extend(os.listdir(dir))
    plugins = []
    for filename in filenames:
        if filename.endswith('.py') and filename[0].isupper():
            plugins.append(os.path.splitext(filename)[0])
    if 'OwnerCommands' in plugins:
        plugins.remove('OwnerCommands')
    plugins.sort()
    return plugins

def loadPlugin(name):
    import OwnerCommands
    try:
        module = OwnerCommands.loadPluginModule(name)
        if hasattr(module, 'Class'):
            return module
        else:
            myPrint("""That plugin loaded fine, but didn't seem to be a real
            Supybot plugin; there was no Class variable to tell us what class
            to load when we load the plugin.  We'll skip over it for now, but
            you can always add it later.""")
            return None
    except Exception, e:
        myPrint("""We encountered a bit of trouble trying to load that plugin.
        Python told us %s.  We'll skip over it for now, you can always add it
        later.""" % e)
        return None

def describePlugin(module, showUsage):
    if module.__doc__:
        myPrint(module.__doc__, unformatted=False)
    elif hasattr(module.Class, '__doc__'):
        myPrint(module.Class.__doc__, unformatted=False)
    else:
        myPrint("""Unfortunately, this plugin doesn't seem to have any
        documentation.  Sorry about that.""")
    if showUsage:
        if hasattr(module, 'example'):
            if yn('This plugin has a usage example.  '
                  'Would you like to see it?') == 'y':
                pydoc.pager(module.example)
        else:
            myPrint("""This plugin has no usage example.""")
    
def configurePlugin(module, onStart, afterConnect, advanced):
    if hasattr(module, 'configure'):
        myPrint("""Beginning configuration for %s..."""%module.Class.__name__)
        module.configure(onStart, afterConnect, advanced)
        print # Blank line :)
        myPrint("""Done!""")
    else:
        onStart.append('load %s' % module.__name__)

def clearLoadedPlugins(onStart, plugins):
    for s in onStart:
        if s.startswith('load '):
            (_, plugin) = s.split(None, 1)
            if plugin in plugins:
                plugins.remove(plugin)

def getDirectoryName(default):
    done = False
    while not done:
        dir = anything('What directory do you want to use?  '
                       '[defaults to %s]' % os.path.join(os.curdir, default))
        if not dir:
            dir = default
        dir = os.path.expanduser(dir)
        dir = os.path.abspath(dir)
        try:
            os.makedirs(dir)
            done = True
        except OSError, e:
            if e.args[0] != 17: # File exists.
                myPrint("""Sorry, I couldn't make that directory for some
                reason.  The Operating System told me %s.  You're going to
                have to pick someplace else.""" % e)
            else:
                done = True
    return dir
        
def myPrint(s, unformatted=True):
    if unformatted:
        s = utils.normalizeWhitespace(s)
    print textwrap.fill(s)
    print

def main():
    parser = optparse.OptionParser(usage='Usage: %prog [options]',
                                   version='Supybot %s' % conf.version)
    (options, args) = parser.parse_args()
    nick = ''
    user = ''
    ident = ''
    password = ''
    server = None
    onStart = []
    afterConnect = []
    debugVariables = {}
    configVariables = {}
    
    myPrint("""This is a wizard to help you start running supybot.  What it
    will do is create a single Python file whose effect will be that of
    starting an IRC bot with the options you select here.  So hold on tight
    and be ready to be interrogated :)""")

    myPrint("""First of all, we can bold the questions you're asked so you can
    easily distinguish the mostly useless blather (like this) from the
    questions that you actually have to answer.""")
    if yn('Would you like to try this bolding?') == 'y':
        useColor = True
        if yn('Do you see this in bold?') == 'n':
            myPrint("""Sorry, it looks like your terminal isn't ANSI compliant.
            Try again some other day, on some other terminal :)""")
            useColor = False
        else:
            myPrint("""Great!""")

    ###
    # Preliminary questions.
    ###
    myPrint("""We've got some preliminary things to get out of the way before
    we can really start asking you questions that directly relate to what your
    bot is going to be like.""")

    # Advanced?
    myPrint("""We want to know if you consider yourself an advanced Supybot
    user because some questions are just utterly boring and useless for new
    users.  Others might not make sense unless you've used Supybot for some
    time.""")
    advanced = yn('Are you an advanced Supybot user?') == 'y'

    ### Directories.
    myPrint("""Now we've got to ask you some questions about where some of
    your directories are (or, perhaps, will be :)).  If you're running this
    wizard from the directory you'll actually be starting your bot from and
    don't mind creating some directories in the current directory, then just
    don't give answers to these questions and we'll create the directories we
    need right here in this directory.""")

    # logDir
    myPrint("""Your bot will need to put his logs somewhere.  Do you have any
    specific place you'd like them?  If not, just press enter and we'll make
    a directory named "logs" right here.""")
    conf.logDir = getDirectoryName('logs')
    configVariables['logDir'] = conf.logDir

    # dataDir
    myPrint("""Your bot will need to put various data somewhere.  Things like
    databases, downloaded files, etc.  Do you have any specific place you'd
    like the bot to put these things?  If not, just press enter and we'll make
    a directory named "data" right here.""")
    conf.dataDir = getDirectoryName('data')
    configVariables['dataDir'] = conf.dataDir

    # confDir
    myPrint("""Your bot must know where to find his configuration files.  It'll
    probably only make one or two, but it's gotta have some place to put them.
    Where should that place be?  If you don't care, just press enter and we'll
    make a directory right here named "conf" where it'll store his stuff. """)
    conf.confDir = getDirectoryName('conf')
    configVariables['confDir'] = conf.confDir

    myPrint("Good!  We're done with the directory stuff.")

    # pluginDirs
    myPrint("""Your bot will also need to know where to find his plugins at.
    Of course, he already knows where the plugins that he came with are, but
    your own personal plugins that you write for will probably be somewhere
    else.  Where do you plan to put those plugins?  If you don't know, just
    press enter and we'll put a "plugins" directory right here that you can
    stick your own personal plugins in.""")
    pluginDir = getDirectoryName('plugins')
    conf.pluginDirs.append(pluginDir)
    myPrint("""Of course, you can have more than one plugin directory.""")
    while yn('Would you like to add another plugin directory?') == 'y':
        pluginDir = getDirectoryName('plugins')
        if pluginDir != 'plugins' and pluginDir not in conf.pluginDirs:
            conf.pluginDirs.append(pluginDir)
    configVariables['pluginDirs'] = conf.pluginDirs

    ###
    # Bot stuff
    ###
    myPrint("""Now we're going to ask you things that actually relate to the
    bot you'll be running.""")

    # server
    if server:
        if yn('You\'ve already got a default server of %s:%s.  '
              'Do you want to change this?' % server) == 'y':
            server = None
    while not server:
        serverString = something('What server would you like to connect to?')
        try:
            myPrint("""Looking up %s...""" % serverString)
            ip = socket.gethostbyname(serverString)
        except:
            myPrint("""Sorry, I couldn't find that server.  Perhaps you
            misspelled it?""")
            continue
        myPrint("""Found %s (%s).""" % (serverString, ip))
        myPrint("""IRC Servers almost always accept connections on port
        6667.  They can, however, accept connections anywhere their admin
        feels like he wants to accept connections from.""")
        if yn('Does this server require connection on an odd port?')=='y':
            port = 0
            while not port:
                port = something('What port is that?')
                try:
                    i = int(port)
                    if not (0 < i < 65536):
                        raise ValueError
                except ValueError:
                    myPrint("""That's not a valid port.""")
                    port = 0
        else:
            port = 6667
        server = ':'.join(map(str, [serverString, port]))

    # nick
    if nick:
        if yn("You've already got a default nick of %s.  "
              "Do you want to change this?" % nick) == 'y':
            nick = ''
    while not nick:
        nick = something('What nick would you like your bot to use?')
        if not ircutils.isNick(nick):
            myPrint("""That's not a valid nick.  Go ahead and pick another.""")
            nick = ''

    # user
    if user:
        if yn("You've already got a default user of %s.  "
              "Do you want to change this?" % user) == 'y':
              user = ''
    if not user:
        myPrint("""If you've ever done a /whois on a person, you know that IRC
        provides a way for users to show the world their full name.  What would
        you like your bot's full name to be?  If you don't care, just press
        enter and it'll be the same as your bot's nick.""")
    while not user:
        user = anything('What would you like your bot\'s full name to be?')
        if not user:
            user = nick

    # ident (if advanced)
    if advanced:
        if ident:
            if yn("You've already got a default ident of %s.  "
                  "Do you want to change this?" % ident) == 'y':
                ident = ''
        if not ident:
            myPrint("""IRC servers also allow you to set your ident, which they
            might need if they can't find your identd server.  What would you
            like your ident to be?  If you don't care, press enter and we'll
            use the same string as your bot's nick.""")
        while not ident:
            ident = anything('What would you like your bot\'s ident to be?')
            if not ident:
                ident = nick
    else:
        ident = nick

    # password
    if password:
        if yn('You\'ve already got a default password of %s.  '
              'Do you want to change this?' % password) == 'y':
            password = ''
    if not password:
        myPrint("""Some servers require a password to connect to them.  Most
        public servers don't.  If you try to connect to a server and for some
        reason it just won't work, it might be that you need to set a
        password.""")
        password = anything('What password?  If you decided not to use a '
                            'password, just press enter.')

    myPrint("""Of course, having an IRC bot isn't the most useful thing in the
    world unless you can make that bot join some channels.""")
    if yn('Do you want your bot to join some channels when he connects?')=='y':
        channels = something('What channels?')
        while not all(ircutils.isChannel, channels.split()):
            # FIXME: say which ones weren't channels.
            myPrint("""Not all of those are valid IRC channels.  Be sure to
            prefix the channel with # (or +, or !, or &, but no one uses those
            channels, really).""")
            channels = something('What channels?')
        afterConnect.append('join %s' % channels)

    ###
    # Plugins
    ###
    plugins = getPlugins()
    for s in ('AdminCommands','UserCommands','ChannelCommands','MiscCommands'):
        s = 'load %s' % s
        if s not in onStart:
            onStart.append(s)
    clearLoadedPlugins(onStart, plugins)

    # bulk
    addedBulk = False
    if advanced and yn('Would you like to add plugins en masse first?') == 'y':
        addedBulk = True
        myPrint("""The available plugins are %s.  What plugins would you like
        to add?  If you've changed your mind and would rather not add plugins
        in bulk like this, just press enter and we'll move on to the individual
        plugin configuration.""" % utils.commaAndify(plugins))
        massPlugins = anything('Separate plugin names by spaces:')
        for name in massPlugins.split():
            module = loadPlugin(name)
            if module is not None:
                configurePlugin(module, onStart, afterConnect, advanced)
                clearLoadedPlugins(onStart, plugins)

    # individual
    if yn('Would you like to look at plugins individually?') == 'y':
        myPrint("""Next comes your oppurtunity to learn more about the plugins
        that are available and select some (or all!) of them to run in your
        bot.  Before you have to make a decision, of course, you'll be able to
        see a short description of the plugin and, if you choose, an example
        session with the plugin.  Let's begin.""")
        showUsage = yn('Would you like the option of seeing usage examples?') \
                    =='y'
        name = expect('What plugin would you like to look at?', plugins)
        while name:
            module = loadPlugin(name)
            if module is not None:
                describePlugin(module, showUsage)
                if yn('Would you like to load this plugin?') == 'y':
                    configurePlugin(module, onStart, afterConnect, advanced)
                    clearLoadedPlugins(onStart, plugins)
            if yn('Would you like add another plugin?') == 'n':
                break
            name = expect('What plugin would you like to look at?', plugins)
    
    ###
    # Sundry
    ###
    myPrint("""Although supybot offers a supybot-adduser.py script, with which
    you can add users to your bot's user database, it's *very* important that
    you have an owner user for you bot.""")
    if yn('Would you like to add an owner user for your bot?') == 'y':
        import ircdb
        name = something('What should the owner\'s username be?')
        try:
            id = ircdb.users.getUserId(name)
            u = ircdb.users.getUser(id)
            if u.checkCapability('owner'):
                myPrint("""That user already exists, and has owner capabilities
                already.  Perhaps you added it before? """)
                if yn('Do you want to remove its owner capability?')=='y':
                    u.removeCapability('owner')
                    ircdb.setUser(id, u)
            else:
                myPrint("""That user already exists, but doesn't have owner
                capabilities.""")
                if yn('Do you want to add to it owner capabilities?') == 'y':
                    u.addCapability('owner')
                    ircdb.setUser(id, u)
        except KeyError:
            password = something('What should the owner\'s password be?')
            (id, u) = ircdb.users.newUser()
            u.name = name
            u.setPassword(password)
            u.addCapability('owner')
            ircdb.users.setUser(id, u)

    myPrint("""Of course, when you're in an IRC channel you can address the bot
    by its nick and it will respond, if you give it a valid command (it may or
    may not respond, depending on what your config variable replyWhenNotCommand
    is set to).  But your bot can also respond to a short "prefix character,"
    so instead of saying "bot: do this," you can say, "@do this" and achieve
    the same effect.  Of course, you don't *have* to have a prefix char, but
    if the bot ends up participating significantly in your channel, it'll ease
    things.""")
    if yn('Would you like to set the prefix char(s) for your bot?') == 'y':
        myPrint("""Enter any characters you want here, but be careful: they
        should be rare enough that people don't accidentally address the bot
        (simply because they'll probably be annoyed if they do address the bot
        on accident).  You can even have more than one.  I (jemfinch) am quite
        partial to @, but that's because I've been using it since my ocamlbot
        days.""")
        conf.prefixChars = anything('What would you like your bot\'s '
                                    'prefix character(s) to be?')
        configVariables['prefixChars'] = conf.prefixChars
    else:
        configVariables['prefixChars'] = ''

    # enablePipeSyntax
    myPrint("""Supybot allows nested commands.  You've probably
    read about them in our website or documentation, and almost certainly have
    seen them in the plugin examples (if you chose to read them),  By default,
    they work with a syntax that looks something like Lisp with square
    brackets.  I.e., to call the command foo on the output of bar, you would
    use "foo [bar]".  Supybot is also capable of providing a pipe syntax
    similar to *nix pipes.  In addition to "foo [bar]", you could achieve the
    same effect with "bar | foo", which some people find more natural.  This
    syntax is disabled by default because so many people have pipes in their
    nicks, and we've found it to be somewhat frustrating to have to quote such
    nicks in commands.""")
    if yn('Would you like to enable the pipe syntax for nesting?') == 'y':
        configVariables['enablePipeSyntax'] = True

    ###
    # debug variables.
    ###

    # debug.stderr
    myPrint("""By default, your bot will log not only to files in the logs
    directory you gave it, but also to stderr.  We find this useful for
    debugging, and also just for the pretty output (it's colored!)""")
    if yn('Would you like to turn off this logging to stderr?') == 'y':
        debugVariables['stderr'] = False
    else:
        # debug.colorterm
        myPrint("""Some terminals may not be able to display the pretty colors
        logged to stderr.  By default, though, we turn the colors off for
        Windows machines and leave it on for *nix machines.""")
        if yn('Would you like to turn this colorization off?') == 'y':
            debugVariables['colorterm'] = False

    # debug.minimumPriority
    myPrint("""Your bot can handle debug messages at four priorities, 'high,'
    'normal,' 'low,' and 'verbose,' in decreasing order of priority.  By
    default, your bot will log all of these priorities.  You can, however,
    specify that he only log messages above a certain priority level.  Of
    course, all error messages will still be logged.""")
    priority = anything('What would you like the minimum priority to be?  '
                        'Just press enter to accept the default.')
    while priority and priority not in ['verbose', 'low', 'normal', 'high']:
        myPrint("""That's not a valid priority.  Valid priorities include
        'verbose,' 'low,' 'normal,' and 'high,' not including the quotes or
        the commas.""")
        priority = anything('What would you like the minimum priority to be?  '
                            'Just press enter to accept the default.')
    if priority:
        debugVariables['minimumPriority'] = priority

    if advanced:
        myPrint("""Here's some stuff you only get to choose if you're an
        advanced user :)""")

        # replyWhenNotCommand
        myPrint("""By default, when people address your bot but don't give it
        a valid command, it'll respond with a message saying that they didn't
        give it a valid command.  When your channel grows more accustomed to
        the bot, they may prefer that it not do that, since any command you
        give the bot (at least within the included plugins) will respond with
        something, so invalid commands are still noticeable.  This decreases
        the channel traffic somewhat.""")
        if yn('Would you like to turn off the bot\'s replies when he\'s '
              'addressed but given a non-command?') == 'y':
            configVariables['replyWhenNotCommand'] = False

        myPrint("""Here in supybot-developer world, we really like Python.  In
        fact, we like it so much we just couldn't do without the ability to
        have our bots evaluate arbitrary Python code.  Of course, we are aware
        of the possible security hazards in allowing such a thing, but we're
        pretty sure our capability system is sound enough to do such a thing
        with some kind of security.  Nevertheless, by default we have these
        commands (eval and exec, both in the OwnerCommands plugin which is
        loaded by default) disabled by a config variable allowEval.  If you'd
        like to use either eval or exec, you'll have to make this variable
        True.  Unless you intend to hack on supybot a lot, we suggest against
        it -- it's just not worth the risk, and if you find something that you
        can't do via a command because the command you want doesn't exist, you
        should tell us and we'll implement the command (rather than make you
        allow eval).  But either way, here's your chance to enable it.""")
        if yn('Would you like to enable allowEval, possibly opening you to '
              'a significant security risk?') == 'y':
            configVariables['allowEval'] = True

        # throttleTime
        myPrint("""In order to prevent flooding itself off the network,
        your bot by default will not send more than one message per second to
        the network.  This is, however, configurable.""")
        if yn('Would you like to change the minimum amount of time between '
              'messages your bot sends to the network?') == 'y':
            throttleTime = None
            while throttleTime is None:
                throttleTime = something('How long do you want your bot to '
                                         'wait between sending messages to '
                                         'the server?')
                try:
                    throttleTime = float(throttleTime)
                except ValueError:
                    myPrint("""That's not a valid time.  You'll need to give
                    a floating-point number.""")
                    throttleTime = None
        
    ###
    # This is close to the end.
    ###
    if not advanced:
        myPrint("""There are a lot of options we didn't ask you about simply
        because we'd rather you get up and running and have time left to play
        around with your bot.  But come back and see us!  When you've played
        around with your bot enough to know what you like, what you don't like,
        what you'd like to change, then come back and run this script again
        and tell us you're an advanced user.  Some of those questions might be
        boring, but they'll really help you customize your bot :)""")
    else:
        myPrint("""This is your last chance to do any configuration before I
        write the bot script.""")
        if yn('Would you like to add any commands to be given to the bot '
              'before it connects to the server?') == 'y':
            command = anything('What command?  Just press enter when done.')
            while command:
                onStart.append(command)
                command = anything('Another command?')
        if yn('Would you like to add any commands to be given to the bot '
              'after it connects to the server?') == 'y':
            command = anything('What command?  Just press enter when done.')
            while command:
                afterConnect.append(command)
                command = anything('Another command?')

    ###
    # Writing the bot script.
    ###
    filename = reduce(os.path.join, [conf.installDir, 'src', 'template.py'])
    fd = file(filename)
    template = fd.read()
    fd.close()

    format = pprint.pformat
    template = template.replace('"%%nick%%"', repr(nick))
    template = template.replace('"%%user%%"', repr(user))
    template = template.replace('"%%ident%%"', repr(ident))
    template = template.replace('"%%password%%"', repr(password))
    template = template.replace('"%%server%%"', repr(server))
    template = template.replace('"%%onStart%%"', format(onStart))
    template = template.replace('"%%afterConnect%%"', format(afterConnect))
    template = template.replace('"%%debugVariables%%"', format(debugVariables))
    template = template.replace('"%%configVariables%%"',
                                format(configVariables))
    template = template.replace('/usr/bin/env python',
                                os.path.normpath(sys.executable))

    filename = '%s-botscript.py' % nick
    fd = file(filename, 'w')
    fd.write(template)
    fd.close()

    if os.name == 'posix':
        os.chmod(filename, 0755)
        
    myPrint("""All done!  Your new bot script is %s.  If you're running a *nix,
    you can start your bot script with the command line "./%s".  If you're not
    running a *nix or similar machine, you'll just have to start it like you
    start all your other Python scripts.""" % (filename, filename))

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
