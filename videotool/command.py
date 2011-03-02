#!/usr/bin/env python

import optparse
import os
import re
import sys

import asynproc
import coding
import sequence


def get_input(name):
    if os.path.isdir(name):
        sequences = sequence.sequences(os.listdir(name))
        keys = list(sequences)
        if not len(keys):
            raise ValueError('no image sequence found in "%s"' % name)
        if len(keys) > 1:
            for i, seq in enumerate(keys):
                numbers = sequences[seq]
                print '%d) %s#%s' % ((i+1,) + seq), '[%s-%s]' % (numbers[0], numbers[-1])
            user_input = raw_input('select sequence> ')
            try:
                seq = keys[int(user_input)-1]
            except (ValueError, IndexError):
                raise ValueError('invalid selection "%s"' % user_input)
        else:
            seq = keys[0]
        names = list(sequence.iterate_sequence(name, seq[0], seq[1], sequences[seq]))
        missing_frames = int(sequences[seq][-1])-int(sequences[seq][0])+1 - len(names)
        if missing_frames:
            print >>sys.stderr, 'warning: sequence has %d missing frames' % missing_frames
        return names
    else:
        return name


def parse_aspect(aspect):
    try:
        result = float(aspect)
    except ValueError:
        parts = re.findall('[\d.]+', aspect)
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2 and float(parts[1]):
            return float(parts[0])/float(parts[1])
        else:
            raise ValueError('cannot parse aspect ratio "%s"' % aspect)
    else:
        return result


def to_nearest_multiple(x, multiple):
    return int(float(x)/multiple+0.5)*multiple


def calculate_format(width, aspect):
    height = float(width)/parse_aspect(aspect)
    return to_nearest_multiple(width, 16), to_nearest_multiple(height, 16)


def _main():
    #w, h = calculate_format(sys.argv[1], sys.argv[2])
    #print w, h, float(w)/h
    #return
    parser = optparse.OptionParser("usage: %prog [options] input output")
    parser.add_option("-f", "--force", dest="force", action="store_true",
                      default=False, help="overwrite existing output file")
    parser.add_option("--vf", dest="video_filters", help="video filters passed to decoding process")
    parser.add_option("--width", dest="width", help="resize video to match WIDTH")
    parser.add_option("--aspect", dest="aspect", help="set aspect ratio")
    parser.add_option("--fps", dest="fps", help="set frames per second")
    parser.add_option("--bitrate", dest="bitrate", help="controls the encoding rate (high|medium|low)")
    parser.add_option("--tune", dest="tune", help="tune the encoding")
    parser.add_option("--preset", dest="preset", help="encoding preset (speed/quality tradeoff)")
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error('one input and one output is required (-h for help)')
    input_name = args[0]
    output_name = args[1]
    if not os.path.exists(input_name):
        parser.error('input "%s" does not exist' % input_name)
    if not options.force and os.path.exists(output_name):
        parser.error('output "%s" already exists (force with -f)' % output_name)

    x264_options = {}
    mplayer_options = {}
    if options.video_filters:
        mplayer_options['vf'] = options.video_filters
    if options.width and options.aspect:
        mplayer_options['vf'] = 'scale=%d:%d' % calculate_format(options.width, options.aspect)
    if options.fps:
        mplayer_options['r'] = options.fps
    if options.bitrate:
        try:
            crf = int(options.bitrate)
        except ValueError:
            crf = dict(high=21, medium=23, low=25).get(options.bitrate, 23)
        x264_options['crf'] = crf
    if options.tune:
        x264_options['tune'] = options.tune
    if options.preset:
        x264_options['preset'] = options.preset

    h264_options = coding.OptionsBase()
    def status(format, info):
        sys.stdout.write(repr(info) + '\r')
        sys.stdout.flush()
    h264_options.status = status
    h264_options.options = x264_options

    coding.encode_h264(get_input(input_name), output_name, encode_options=h264_options)
    print


if __name__=='__main__':
    _main()
