# vim:expandtab:autoindent:tabstop=4:shiftwidth=4:filetype=python:textwidth=0:
# License: GPL2 or later see COPYING
# Written by Jan Vcelak
# Copyright (C) 2010 Jan Vcelak <jvcelak@redhat.com>

# python library imports
import os
import sys
import tempfile
import stat
import atexit

# our imports
from mockbuild.trace_decorator import decorate, traceLog, getLog
import mockbuild.util
from mockbuild.mounts import BindMountPoint

requires_api_version = "1.0"

# plugin entry point
decorate(traceLog())
def init(plugins, conf, buildroot):
    if mockbuild.util.selinuxEnabled():
        getLog().info("selinux enabled")
        SELinux(plugins, conf, buildroot)
    else:
        getLog().info("selinux disabled")

# classes
class SELinux(object):
    """On SELinux enabled box, this plugin will pretend, that SELinux is disabled in build environment.

       - fake /proc/filesystems is mounted into build environment, excluding selinuxfs
       - option '--setopt=tsflags=nocontext' is appended to each 'yum' command
    """

    decorate(traceLog())
    def __init__(self, plugins, conf, buildroot):
        self.buildroot = buildroot
        self.config = buildroot.config
        self.state = buildroot.state
        self.conf = conf

        self.filesystems = self._selinuxCreateFauxFilesystems()
        self.chrootFilesystems = buildroot.make_chroot_path("/proc/filesystems")

        atexit.register(self._selinuxAtExit)

        self.buildroot.mounts.add(BindMountPoint(srcpath=self.filesystems, bindpath=self.chrootFilesystems))

        if self._selinuxYumIsSetoptSupported():
            plugins.add_hook("preyum", self._selinuxPreYumHook)
            plugins.add_hook("postyum", self._selinuxPostYumHook)
        else:
            getLog().warning("selinux: 'yum' does not support '--setopt' option")

    decorate(traceLog())
    def _selinuxCreateFauxFilesystems(self):
        (fd, path) = tempfile.mkstemp(prefix="mock-selinux-plugin.")

        host = open("/proc/filesystems")
        try:
            for line in host:
                if not "selinuxfs" in line:
                    os.write(fd, line)
        finally:
            host.close()

        os.close(fd)
        os.chmod(path, stat.S_IRUSR|stat.S_IRGRP|stat.S_IROTH)

        return path

    decorate(traceLog())
    def _selinuxAtExit(self):
        if os.path.exists(self.filesystems):
            try:
                os.unlink(self.filesystems)
            except OSError, e:
                getLog().warning("unable to delete selinux filesystems (%s): %s" % (self.filesystems, e))
                pass

    decorate(traceLog())
    def _selinuxPreYumHook(self):
        self._originalUtilDo = mockbuild.util.do
        mockbuild.util.do = self._selinuxDoYum

    decorate(traceLog())
    def _selinuxPostYumHook(self):
        mockbuild.util.do = self._originalUtilDo

    decorate(traceLog())
    def _selinuxDoYum(self, command, *args, **kargs):
        option = "--setopt=tsflags=nocontexts"

        if type(command) is list:
            if command[0].startswith(self.buildroot.pkg_manager.command):
                command.append(option)
        elif type(command) is str:
            if command.startswith(self.buildroot.pkg_manager.command):
                command += " %s" % option

        return self._originalUtilDo(command, *args, **kargs)

    decorate(traceLog())
    def _selinuxYumIsSetoptSupported(self):
        # ugly hack: discover, whether yum supports --setopt option
        sys.path.insert(0, '/usr/share/yum-cli')
        import cli
        supported = hasattr(cli.YumBaseCli, "_parseSetOpts")
        sys.path.pop(0)

        return supported
