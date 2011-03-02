
import contextlib
import os
import tempfile


@contextlib.contextmanager
def _sequence_links(names):
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


def _mplayer_sequence_repr(directory, extension):
    return 'mf://' + os.path.join(directory, '*' + extension)


def _ffmpeg_sequence_repr(directory, extension):
    return  os.path.join(directory, '%08d' + extension)


@contextlib.contextmanager
def sequence_as_str_repr(input, type):
    """Convert a list of filenames to a string representing that sequence.

    If input is not a list, it is assumed to be a filename already and
    is returned directly, otherwise a temporary directory is created
    and every file in the input list is symbolically linked into the
    directory.  The returned representation depends on the given type:

    type == 'mplayer':  returns a mplayer mf:// compatible url.
    type == 'ffmpeg':  returns a ffmpeg image2 compatible filename. (default)
    """
    if isinstance(input, list):
        with _sequence_links(input) as links:
            directory = os.path.dirname(links[0])
            extension = os.path.splitext(links[0])[1]
            if type == 'mplayer':
                yield _mplayer_sequence_repr(directory, extension)
            else:
                yield _ffmpeg_sequence_repr(directory, extension)
    else:
        yield input

