#!/usr/bin/env python3

"""Test program which compares two directory trees on local system
args:
full path to directory 1
full path to directory 2
(optional) --verbose
Exit value 0 on success 1 on fail
"""
import sys
import os


def main():
    verbose = len(sys.argv) == 4 and sys.argv[3] == '--verbose'
    source = sys.argv[1]
    dest = sys.argv[2]
    source_list = [x[1:] for x in os.walk(source)]
    dest_list = [x[1:] for x in os.walk(dest)]
    lens = len(source_list)
    if lens != len(dest_list):
        if verbose:
            print('Length fail ', lens, len(dest_list))
        sys.exit(1)
    for subdir in range(lens):
        if False in map(lambda str0, str1 : str0 == str1, source_list[subdir], dest_list[subdir]):
            if verbose:
                print('Subdir fail ', source_list[subdir], dest_list[subdir])
            sys.exit(1)
    if verbose:
        print('Directories match')
    sys.exit(0)

if __name__ == '__main__':
    main()
