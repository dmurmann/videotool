
import tempfile
import contextlib
import os
import re
import sys


@contextlib.contextmanager
def sequence_links(names):
    tmp_dir = tempfile.mkdtemp()
    links = []
    for i, name in enumerate(names):
        links.append(os.path.join(tmp_dir, '%08d%s' % (i, os.path.splitext(name)[1])))
        os.symlink(os.path.abspath(name), links[-1])
    try:
        yield links[:]
    finally:
        for name in links:
            try:
                os.unlink(name)
            except OSError:
                pass
        os.rmdir(tmp_dir)


def sequences(names):
    names = sorted(names)
    digit_pattern = re.compile(r'\d+')
    sequences = {}
    last_partitions = []
    for i, name in enumerate(names):
        partitions = []
        for match in digit_pattern.finditer(name):
            start, end = match.span()
            partitions.append((name[:start], name[start:end], name[end:]))
            for head, number, tail in last_partitions:
                if name[:start] != head or name[end:] != tail:
                    continue
                key = head, tail
                if key in sequences:
                    sequences[key].append(name[start:end])
                else:
                    sequences[key] = [number, name[start:end]]
        last_partitions = partitions
    for numbers in sequences.values():
        numbers.sort(key=lambda x: int(x))
    return sequences


def iterate_sequence(directory, head, tail, numbers):
    last = None
    for v, n in sorted((int(n), n) for n in numbers):
        if v == last:
            continue
        yield os.path.join(directory, head + n + tail)
        last = v


def _main():
    #names = sorted(os.listdir(sys.argv[1]) + ['test0.%d.png' % i for
    # i in xrange(1)] + ['test1.%d.png' % i for i in xrange(20)])
    directory = sys.argv[1]
    names = os.listdir(directory)
    for (head, tail), numbers in sorted(sequences(names).iteritems()):
        with sequence_links(iterate_sequence(directory, head, tail, numbers)) as links:
            print links


if __name__=='__main__':
    _main()
