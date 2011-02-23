#!/usr/bin/env python

import optparse
import os
import sys

import asynproc
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
        with sequence.sequence_links(sequence.iterate_sequence(name, seq[0], seq[1], sequences[seq])) as links:
            directory = os.path.dirname(links[0])
            extension = os.path.splitext(links[0])[1]
            yield 'mf://' + os.path.join(directory, '*' + extension)
    else:
        yield name

def _main():
    parser = optparse.OptionParser("usage: %prog [options] input output")
    options, args = parser.parse_args()
    if len(args) != 2:
        parser.error('one input and one output is required')
    input_name = args[0]
    output_name = args[1]
    if not os.path.exists(input_name):
        parser.error('input "%s" does not exist' % input_name)
    if os.path.exists(output_name):
        parser.error('output "%s" already exists' % output_name)

    for input in get_input(input_name):
        asynproc.encode(input, output_name)


if __name__=='__main__':
    _main()
