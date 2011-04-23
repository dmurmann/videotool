#!/usr/bin/env python

import optparse
import os
import re
import sys

import asynproc
import coding
import sequence

def _main():
    parser = optparse.OptionParser("usage: %prog [options] input-dir output-dir")
    parser.add_option("--fps", dest="fps", help="set frames per second")
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error('one input and one output is required (-h for help)')
    input_dir = args[0]
    output_dir = args[1]
    for d in (input_dir, output_dir):
        if not os.path.isdir(d):
            parser.error('%s is not a directory!' % d)

    class DecodeOptions(coding.OptionsBase):
        def error(self, returncode, output):
            print ''.join(output)
        # def status(self, format, info):
        #     print format, info
    class EncodeOptions(coding.OptionsBase):
        def error(self, returncode, output):
            print ''.join(output)

    decode_options = DecodeOptions()
    decode_options.options = {}
    if options.fps:
        decode_options.options['r'] = options.fps
    else:
        decode_options.options['r'] = 24

    encode_options = EncodeOptions()
    encode_options.options = {}
    encode_options.options['crf'] = 22
    encode_options.options['keyint'] = 24
    encode_options.options['preset'] = 'slower'

    sequences = sequence.sequences(os.listdir(input_dir))
    for (head, tail), names in sequences.iteritems():
        output_name = os.path.join(output_dir, os.path.splitext(head + 'X' + tail)[0] + '.mp4')
        names = list(sequence.iterate_sequence(input_dir, head, tail, names))
        coding.encode_h264(names, output_name, decode_options=decode_options, encode_options=encode_options)

if __name__=='__main__':
    _main()
