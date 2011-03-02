
import os
import re

import sequence
import asynproc

from asynproc import which
from coding_sequence import sequence_as_str_repr


class X264Handler(asynproc.ProcessHandlerBase):
    format_description = {
        'status_long': re.compile(r'(?P<frame>\d+)/(?P<nframes>\d+) frames.*[^0-9.](?P<fps>\d*\.?\d*) fps'
                                   '.*[^0-9.](?P<bitrate>\d*\.?\d*) kb/s.*eta (?P<eta>\d+:\d+:\d+)'),
        'status_short': re.compile(r'(?P<frame>\d+) frames.*[^0-9.](?P<fps>\d*\.?\d*) fps'
                                    '.*[^0-9.](?P<bitrate>\d*\.?\d*) kb/s'),
        }


class MPlayerHandler(asynproc.ProcessHandlerBase):
    format_description = {
        'status': re.compile(r'V:\s*(?P<time>\d*\.\d*).*[^0-9](?P<frame>\d+)/[^0-9]*(?P<nframes>\d+)[^0-9]'),
        }


class FFmpegHandler(asynproc.ProcessHandlerBase):
    format_description = {
        'all': re.compile(r'(?P<all>.*)'),
        'status': re.compile(r'frame=[ ]*(?P<frame>[\d.]+).*fps=[ ]*(?P<fps>[\d.]+)'),
        }


class OptionsBase(object):
    def status(self, format, info):
        pass

    def error(self, returncode, output):
        pass


def decode_to_yuv(*args, **kwds):
    decoder_type = kwds.pop('type', None)
    if decoder_type == 'mplayer':
        return decode_to_yuv_mplayer(*args, **kwds)
    else:
        return decode_to_yuv_ffmpeg(*args, **kwds)


def decode_to_yuv_mplayer(input, output, **options):
    for opt, val in [('vf', 'scale=:::0'), ('sound', False), ('benchmark', True),
                     ('quiet', False), ('lavdopts', 'skiploopfilter=none:threads=1'),
                     ('consolecontrols', False), ('noconfig', 'all'),
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

    return asynproc.run_process([which('mplayer'), input] + option_list, terminate_children=True)


def decode_to_yuv_ffmpeg(input, output, **options):
    for opt, val in [('f', 'yuv4mpegpipe'), ('pix_fmt', 'yuv420p'), ('y', True)]:
        options.setdefault(opt, val)
    option_list = []
    for k, v in options.iteritems():
        if v is True:
            option_list.append('-'+k)
        else:
            option_list.append('-'+k)
            option_list.append(str(v))
    return asynproc.run_process([which('ffmpeg'), '-i', input] + option_list + [output])


def encode_yuv_to_h264(input, output, **options):
    options.setdefault('preset', 'veryslow')
    # The following defaults are for QuickTime compatibility
    options.setdefault('profile', 'main')
    options.setdefault('bframes', '2')
    options.setdefault('ref', '8')
    options.setdefault('partitions', 'p8x8,b8x8,i4x4,p4x4')

    option_list = [('--'+k, str(v)) for k, v in options.iteritems()]
    option_list = [opt for x in option_list for opt in x]

    return asynproc.run_process([which('x264'), '--output', output, input] + option_list)


def encode_h264(input, output, decode_options=None, encode_options=None):
    if decode_options is None:
        decode_options = OptionsBase()
    if encode_options is None:
        encode_options = OptionsBase()
    decode_options.options = getattr(decode_options, 'options', {})
    encode_options.options = getattr(encode_options, 'options', {})
    decoder_type = decode_options.options.get('type', 'ffmpeg')
    with sequence_as_str_repr(input, decoder_type) as input:
        with asynproc.fifo_handle('video.y4m') as named_pipe:
            with encode_yuv_to_h264(named_pipe, output, **encode_options.options) as encoder:
                with decode_to_yuv(input, named_pipe, **decode_options.options) as decoder:
                    if decoder_type == 'mplayer':
                        decoder_handler = MPlayerHandler
                    else:
                        decoder_handler = FFmpegHandler
                    decoder_handler = decoder_handler(decoder, decode_options.status,
                                                      decode_options.error)
                    encoder_handler = X264Handler(encoder, encode_options.status,
                                                  encode_options.error)
                    asynproc.set_dependant(decoder_handler, encoder_handler)
                    asynproc.loop()

