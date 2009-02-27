#!/usr/bin/env python

import os
import re
import sys
import shutil

def firstLines(filename, n):
    fd = file(filename)
    lines = []
    while n:
        n -= 1
        lines.append(fd.readline().rstrip('\r\n'))
    return lines

def firstLine(filename):
    return firstLines(filename, 1)[0]

def error(s):
    sys.stderr.write(s+'\n')
    sys.exit(-1)

def system(sh, errmsg=None):
    if errmsg is None:
        errmsg = repr(sh)
    ret = os.system(sh)
    if ret:
        error(errmsg + '  (error code: %s)' % ret)

def usage():
    error('Usage: %s [-s] <sf username> <version>\nSpecify -s to pass it on '
          'to the relevant git commands.' % sys.argv[0])

if __name__ == '__main__':
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        usage()

    sign = ''
    if len(sys.argv) == 4:
        if sys.argv[1] == '-s':
            sign = '-s'
            sys.argv.pop(1)
        else:
            usage()

    print 'Check version string for validity.'
    (u, v) = sys.argv[1:]
    if not re.match(r'^\d+\.\d+\.\d+\w*$', v):
        error('Invalid version string: '
              'must be of the form MAJOR.MINOR.PATCHLEVEL.')

    if os.path.exists('supybot'):
        error('I need to make the directory "supybot" but it already exists.'
              '  Change to an appropriate directory or remove the supybot '
              'directory to continue.')
    print 'Checking out fresh tree from git.'
    system('git clone ssh://%s@supybot.git.sourceforge.net/gitroot/supybot', u)
    os.chdir('supybot')
    system('git checkout -b maint origin/maint')

    print 'Checking RELNOTES version line.'
    if firstLine('RELNOTES') != 'Version %s' % v:
        error('Invalid first line in RELNOTES.')

    print 'Checking ChangeLog version line.'
    (first, _, third) = firstLines('ChangeLog', 3)
    if not re.match(r'^20\d\d-\d{2}-\d{2}\s+\w+.*<\S+@\S+>$', first):
        error('Invalid first line in ChangeLog.')
    if not re.match(r'^\t\* Version %s!$' % v, third):
        error('Invalid third line in ChangeLog.')

    print 'Updating version in version files.'
    versionFiles = ('src/conf.py', 'scripts/supybot', 'setup.py')
    for fn in versionFiles:
        sh = 'perl -pi -e "s/^version\s*=.*/version = \'%s\'/" %s' % (v, fn)
        system(sh, 'Error changing version in %s' % fn)
    system('git commit -a %s -m \'Updated to %s.\' %s'
           % (sign, v, ' '.join(versionFiles)))

    print 'Tagging release.'
    system('git tag %s -m %s' % (sign, v))

    print 'Removing test, sandbox.'
    shutil.rmtree('test')
    shutil.rmtree('sandbox')
    shutil.rmtree('.git')

    os.chdir('..')
    dirname = 'Supybot-%s' % v
    print 'Renaming directory to %s.' % dirname
    if os.path.exists(dirname):
        shutil.rmtree(dirname)
    shutil.move('supybot', dirname)

    print 'Creating tarball (gzip).'
    system('tar czvf Supybot-%s.tar.gz %s' % (v, dirname))
    print 'Creating tarball (bzip2).'
    system('tar cjvf Supybot-%s.tar.bz2 %s' % (v, dirname))
    print 'Creating zip.'
    system('zip -r Supybot-%s.zip %s' % (v, dirname))

    print 'Uploading package files to upload.sf.net.'
    system('scp Supybot-%s.tar.gz Supybot-%s.tar.bz2 Supybot-%s.zip '
           '%s@frs.sourceforge.net:uploads' % (v, v, v, u))

    print 'Committing %s+git to version files.' % v
    system('git checkout master')
    for fn in versionFiles:
        sh = 'perl -pi -e "s/^version\s*=.*/version = \'%s\'/" %s' % \
             (v + '+git', fn)
        system(sh, 'Error changing version in %s' % fn)
    system('git commit %s -m \'Updated to %s.\' %s'
           % (sign, v, ' '.join(versionFiles)))

    print 'Copying new version.txt over to project webserver.'
    system('echo %s > version.txt' % v)
    system('scp version.txt %s@shell.sf.net:/home/groups/s/su/supybot/htdocs'%u)

#    print 'Generating documentation.'
#    # docFiles is in the format {directory: files}
#    docFiles = {'.': ('README', 'INSTALL', 'ChangeLog'),
#                'docs': ('config.html', 'CAPABILITIES', 'commands.html',
#                         'CONFIGURATION', 'FAQ', 'GETTING_STARTED',
#                         'INTERFACES', 'OVERVIEW', 'PLUGIN-EXAMPLE',
#                         'plugins', 'plugins.html', 'STYLE'),
#               }
#    system('python scripts/supybot-plugin-doc')
#    pwd = os.getcwd()
#    os.chmod('docs/plugins', 0775)
#    sh = 'tar rf %s/docs.tar %%s' % pwd
#    for (dir, L) in docFiles.iteritems():
#        os.chdir(os.path.join(pwd, dir))
#        system(sh % ' '.join(L))
#    os.chdir(pwd)
#    system('bzip2 docs.tar')
#
#    print 'Uploading documentation to webspace.'
#    system('scp docs.tar.bz2 %s@supybot.sf.net:/home/groups/s/su/supybot'
#           '/htdocs/docs/.' % u)
#    system('ssh %s@supybot.sf.net "cd /home/groups/s/su/supybot/htdocs/docs; '
#           'tar jxf docs.tar.bz2"' % u)
#
#    print 'Cleaning up generated documentation.'
#    shutil.rmtree('docs/plugins')
#    configFiles = ('docs/config.html', 'docs/plugins.html',
#                   'docs/commands.html', 'docs.tar.bz2', 'test-conf',
#                   'test-data', 'test-logs', 'tmp')
#    for fn in configFiles:
#        os.remove(fn)

# This is the part where we do our release on Freshmeat using XMLRPC and
# <gasp> ESR's software to do it: http://freshmeat.net/p/freshmeat-submit/
