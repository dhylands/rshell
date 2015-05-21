#!/usr/bin/env python3

"""Test program which generates an all-file.dat file which all 256 8-bit
   characters.
"""

def main():
    buf = bytearray(tuple(i for i in range(256)))
    with open('all-bytes.dat', 'wb') as file:
        file.write(buf)

main()
