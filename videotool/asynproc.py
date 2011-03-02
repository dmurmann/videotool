#!/usr/bin/env python
# Copyright (C) 2011  The Foundation.  David Murmann.

import asyncore
import collections
import contextlib
import os
import signal
import subprocess
import sys
import tempfile
import time

from asyncore import loop

def separation(s, seps):
    """
    Similar to str.partition, but separates on the first character of the
    character set 'seps' instead of searching for a multicharacter separator.

    >>> separation('foo\\nbar\\rbaz\\n', '\\r\\n')
    ('foo', '\\n', 'bar\\rbaz\\n')
    >>> separation('bar\\rbaz\\n', '\\r\\n')
    ('bar', '\\r', 'baz\\n')
    >>> separation('baz\\n', '\\r\\n')
    ('baz', '\\n', '')
    >>> separation('', '\\r\\n')
    ('', '', '')
    """
    indices = []
    for c in seps:
        try:
            indices.append(s.index(c))
        except ValueError:
            pass
    if not indices:
        return s, '', ''
    i = min(indices)
    return s[:i], s[i], s[i+1:]


def which(name):
    """
    Simple replacement for the command line utility which.

    Searches for a file of the given name in the directories on PATH.
    Returns the full path of the first match or the name itself if it
    is not found.

    >>> which('ls')
    '/bin/ls'
    >>> which('not_existent')
    'not_existent'
    """
    if 'PATH' not in os.environ:
        return name
    for path in os.environ['PATH'].split(os.pathsep):
        try:
            names = os.listdir(path)
        except OSError:
            continue
        if name in names:
            return os.path.join(path, name)
    return name


def process_tree():
    ps = subprocess.Popen([which('ps')] + 'ax -o pid,ppid'.split(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout = ps.communicate()[0]
    result = collections.defaultdict(list)
    for line in stdout.split('\n'):
        if not line:
            continue
        try:
            pid, ppid = line.split()
            result[int(ppid)].append(int(pid))
        except ValueError:
            pass
    return result


@contextlib.contextmanager
def fifo_handle(name):
    """
    Creates a named pipe (fifo) in a new temporary directory.
    The directory and the fifo will be removed on exit.
    """
    tmp_dir = tempfile.mkdtemp()
    fifo = os.path.join(tmp_dir, name)
    os.mkfifo(fifo)
    try:
        yield fifo
    finally:
        for name in os.listdir(tmp_dir):
            os.unlink(os.path.join(tmp_dir, name))
        os.rmdir(tmp_dir)


@contextlib.contextmanager
def run_process(*args, **kwds):
    """
    Creates a subprocess.Popen object with the given arguments,
    but defaults to creating pipes for stdin, stdout and stderr.

    The process will be terminated on exit, and, if it is still
    running after a grace period, will be killed.  If the keyword
    terminate_children is True, the current process tree will be
    inspected and all child processes of the process will be
    terminated as well.
    """
    terminate_children = kwds.pop('terminate_children', False)
    kwds.setdefault('stdin', subprocess.PIPE)
    kwds.setdefault('stdout', subprocess.PIPE)
    kwds.setdefault('stderr', subprocess.STDOUT)
    #print 'running "%s"' % ' '.join(args[0])
    process = subprocess.Popen(*args, **kwds)
    process.terminate_children = terminate_children
    try:
        yield process
    finally:
        end_process(process)


def end_process(process):
    if getattr(process, 'terminate_children', False):
        try:
            pstree = process_tree()
        except OSError:
            pass
        else:
            for child_pid in pstree[process.pid]:
                try:
                    os.kill(child_pid, signal.SIGTERM)
                except OSError:
                    pass
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    i = 1
    try:
        while process.poll() is None and i < 20:
            # maximum sleep:  sum(i*i/100.0 for i in range(20)) = 24.7sec
            time.sleep(i*i/100.0)
            i += 1
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass


class LineHandler(asyncore.file_dispatcher):
    """
    An LineHandler reads from the given file object, and
    calls handle_line only after a complete line is recieved.

    This can be useful for handling line formatted output of
    subprocesses.
    """
    def __init__(self, fd, map=None, max_read_size=4096):
        asyncore.file_dispatcher.__init__(self, fd, map)
        self.line_buffer = []
        self.max_read_size = max_read_size

    def writable(self):
        return False

    def handle_read(self):
        buf = self.recv(self.max_read_size)
        while buf:
            line, sep, buf = separation(buf, '\r\n')
            if sep:
                self.handle_line(''.join(self.line_buffer) + line + sep)
                self.line_buffer = []
            else:
                self.line_buffer.append(line)

    def handle_line(self, line):
        self.log_info('unhandled line event', 'warning')
        print >>sys.stderr, repr(line)


class ProcessHandlerBase(LineHandler):
    def __init__(self, process, read_handler, error_handler, map=None, max_read_size=4096):
        LineHandler.__init__(self, process.stdout, map=map, max_read_size=max_read_size)
        self.process = process
        self.read_handler = read_handler
        self.error_handler = error_handler
        self.dependants = []
        self.output = []

    def handle_line(self, line):
        self.output.append(line)
        if self.read_handler is None:
            return
        for format, pattern in self.format_description.iteritems():
            match = pattern.search(line)
            if match is not None:
                self.read_handler(format, match.groupdict())

    def handle_close(self):
        self.close()
        if self.process.poll() is None:
            print >>sys.stderr, 'process closed pipe before ending'
            end_process(self.process)
        returncode = self.process.poll()
        if returncode is None or returncode != 0:
            if self.error_handler is not None:
                self.error_handler(returncode, self.output)
            for dependant in self.dependants:
                if dependant.process.poll() is None:
                    end_process(dependant.process)


def set_dependant(*handlers):
    for i in xrange(len(handlers)):
        handlers[i].dependants = handlers[:i] + handlers[i+1:]


def _main():
    import doctest
    doctest.testmod()
    return

if __name__=='__main__':
    _main()

