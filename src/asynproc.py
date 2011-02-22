#!/usr/bin/env python
# Copyright (C) 2011  The Foundation.  David Murmann.

import asyncore
import collections
import contextlib
import os
import re
import signal
import subprocess
import sys
import tempfile
import time


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

    # seps = set(seps)
    # for i, c in enumerate(s):
    #     if c in seps:
    #         return s[:i], c, s[i+1:]
    # return s, '', ''


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
    ps = subprocess.Popen([which('ps')] + '-o pid,ppid -ax'.split(),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = ps.communicate()
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
    terminate_childen is True, the current process tree will be
    inspected and all child processes of the process will be
    terminated as well.
    """
    terminate_children = kwds.pop('terminate_children', False)
    for pipe in ('stdin', 'stdout', 'stderr'):
        if pipe not in kwds:
            kwds[pipe] = subprocess.PIPE
    process = subprocess.Popen(*args, **kwds)
    try:
        yield process
    finally:
        if terminate_children:
            try:
                pstree = process_tree()
            except OSError:
                pass
            else:
                for child_pid in pstree[process.pid]:
                    try:
                        os.kill(child_pid, signal.SIGTERM)
                    except OSError as e:
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


class output_line_dispatcher(asyncore.file_dispatcher):
    """
    An output_line_dispatcher reads from the given file object, and
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


class x264_handler(output_line_dispatcher):
    format_desc = {
        'status_long': re.compile(r'(?P<frame>\d+)/(?P<nframes>\d+) frames.*[^0-9.](?P<fps>\d*\.?\d*) fps'
                                   '.*[^0-9.](?P<bitrate>\d*\.?\d*) kb/s.*eta (?P<eta>\d+:\d+:\d+)'),
        'status_short': re.compile(r'(?P<frame>\d+) frames.*[^0-9.](?P<fps>\d*\.?\d*) fps'
                                    '.*[^0-9.](?P<bitrate>\d*\.?\d*) kb/s'),
        }
    def handle_line(self, line):
        #print repr(line)
        for format, pattern in self.format_desc.iteritems():
            match = pattern.search(line)
            if match is not None:
                print format, match.groupdict()

class mplayer_handler(output_line_dispatcher):
    format_desc = {
        'status': re.compile(r'V:\s*(?P<time>\d*\.\d*).*[^0-9](?P<frame>\d+)/[^0-9]*(?P<nframes>\d+)[^0-9]'),
        }
    def handle_line(self, line):
        #print repr(line)
        for format, pattern in self.format_desc.iteritems():
            match = pattern.search(line)
            if match is not None:
                print format, match.groupdict()


def run_x264(input, output, **options):
    options.setdefault('preset', 'veryslow')
    # The following defaults are for QuickTime compatibility
    options.setdefault('profile', 'main')
    options.setdefault('bframes', '2')
    options.setdefault('ref', '8')
    options.setdefault('partitions', 'p8x8,b8x8,i4x4,p4x4')

    option_list = [('--'+k, str(v)) for k, v in options.iteritems()]
    option_list = [opt for x in option_list for opt in x]

    return run_process([which('x264'), '--output', output, input] +
                       option_list, stderr=subprocess.STDOUT)


def run_mplayer(input, output, **options):
    for opt, val in [('vf', 'scale=:::0'), ('sound', False), ('benchmark', True),
                     ('quiet', False), ('lavdopts', 'skiploopfilter=none:threads=1'),
                     ('consolecontrols', False), ('noconfig', 'all'), ('fontconfig', False),
                     ('vo', 'yuv4mpeg:file="%s"' % output)]:
        options.setdefault(opt, val)
    # Decode jpgs with the ijpg codec, to force conversion to rgb,
    # which will then correctly convert to yuv.  The mplayer internal
    # jpg decoder would write the full range yuv data to the output
    # stream (instead of 16-235).
    if input.endswith(('.jpg', '.jpeg')):
        options.setdefault('vc', 'ijpg,')

    option_list = []
    for k, v in options.iteritems():
        if v is True:
            option_list.append('-'+k)
        elif v is False:
            option_list.append('-no'+k)
        elif not v:
            continue
        else:
            option_list.append('-'+k)
            option_list.append(str(v))

    return run_process([which('mplayer'), input] + option_list, stderr=subprocess.STDOUT,
                       terminate_children=True)


def _main():
    with fifo_handle('video.y4m') as named_pipe:
        with run_x264(named_pipe, sys.argv[2]) as x264:
            with run_mplayer(sys.argv[1], named_pipe) as mplayer:
                mplayer_handler(mplayer.stdout)
                x264_handler(x264.stdout)
                asyncore.loop()


    #import doctest
    #doctest.testmod()
    #return

    return

if __name__=='__main__':
    _main()
    sys.exit(0)








"""
x264
 --crf 24
 --preset veryslow
 --threads auto
 --tune film
 --profile main --bframes 2 --ref 8 --partitions p8x8,b8x8,i4x4,p4x4
 --output temp.mp4
 fifo.y4m

 --keyint
 --min-keyint

mplayer
 input
 -noautosub
 -ass -ass-color efba6b00 -ass-font-scale 0.5625
 -vf crop=x:y,scale=x:y::0
 -vo yuv4mpeg:file=fifo.y4m
 -nosound
 -benchmark
 -quiet

afconvert -v input.wav -o output.mp4 --bitrate 448000 --file mp4f --data aac --channellayout MPEG_5_1_C -q 127

neroAacEnc -br 448000 -2pass -if in.wav -of out.mp4
neroAacEnc -q 0.5 -if in.wav -of out.mp4
First pass:  processed 31 seconds...
Second pass: processed 31 seconds...

"""

def run_x264(input, output, options):
    executable = which('x264')
    if not executable:
        print >>sys.stderr, 'x264 not found'
        return
    yield 'enter', executable
    with run_process([executable, '--output', output, input] + options) as process:
        while process.poll() is None:
            print process.stdout.read(1024)
            yield 'running', nframes
    yield 'exit', nframes

def read_fifo(fifo):
    #print 'thread', open(fifo, 'wb').write('hello')
    open(fifo, 'wb').write('hello')

def read_fifo2(fifo):
    fp = open(fifo, 'wb')
    #fp = os.open(fifo, os.O_WRONLY)
    #print 'thread'
    while True:
        fp.write('.\n')
        fp.flush()
        time.sleep(1)

if 0:
    import threading

    with fifo_handle('video.y4m') as fifo:
        #print fifo
        #t1 = threading.Thread(target=read_fifo, args=(fifo,))
        #t1.start()
        t1 = threading.Thread(target=read_fifo2, args=(fifo,))
        t1.daemon = True
        t1.start()
        output_dispatcher(open(fifo, 'rb'))
        asyncore.loop()

        #print line
        #print open(fifo, 'rb').read()
        #fp = open(fifo, 'wb')
        #fp.write('hello')
        #fp.close()
        #print fifo
        #fp = os.open(fifo, os.O_RDONLY)
        #os.close(fp)
    return

if 0:
    tmp_dir = tempfile.mkdtemp()
    fifo = os.path.join(tmp_dir, 'video.y4m')
    os.mkfifo(fifo)
    try:
        process(fifo)
    finally:
        for name in os.listdir(tmp_dir):
            os.unlink(os.path.join(tmp_dir, name))
        os.rmdir(tmp_dir)


def process(fifo):
    import errno

    input_dir = '/mnt/fuckup/projects/Einslive/schwerelos/media/edit_outputs/MASTER_FINAL/furs_kopierwerk/'
    #out_fp = os.open(fifo, os.O_RDONLY)
    #out_fp = os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)

    outpipe = os.path.join(input_dir, 'pipe.ppm')
    print outpipe
    #out_fp = os.open(outpipe, os.O_WRONLY)
    #open(outpipe, 'wb')

    for name in os.listdir(input_dir + '110115_1LIVE_schwerelos_dpx'):
        print name
        #continue
        fname = os.path.join(input_dir + '110115_1LIVE_schwerelos_dpx', name)
        fp = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        p1 = subprocess.Popen(['convert', fname, '-set', 'colorspace', 'sRGB', '-colorspace', 'RGB', '-depth', '8', 'ppm:'+fifo])
        while True:
            try:
                v = os.read(fp, 4096)
                if not v:
                    break
            except OSError, e:
                if e.errno == errno.EAGAIN:
                    time.sleep(0.1)
                    print 'again'
                    continue
                raise
        p1.wait()
        #out_fp.write(fp.read())
        fp.close()
        #out = os.path.join(input_dir + 'test2', name + '.jpg')
    #out_fp.close()
