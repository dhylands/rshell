#!/usr/bin/env python3

"""Implements getch. From: https://gist.github.com/chao787/2652257"""

# Last modified: <2012-05-10 18:04:45 Thursday by richard>

# @version 0.1
# @author : Richard Wong
# Email: chao787@gmail.com
class _Getch:
    """
    Gets a single character from standard input.  Does not echo to
    the screen.
    """
    def __init__(self):
        try:
            self.impl = _GetchWindows()
        except ImportError:
            try:
                self.impl = _GetchMacCarbon()
            except(AttributeError, ImportError):
                self.impl = _GetchUnix()

    def __call__(self):
        return self.impl()


class _GetchUnix:
    def __init__(self):
        import tty, sys

    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.buffer.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            return ch


class _GetchWindows:
    def __init__(self):
        import msvcrt

    def __call__(self):
        import msvcrt
        ch =  msvcrt.getch()
        if ch == b'\xe0':
            ch = {b'H': b'\x10', b'P': b'\x0e', b'M': b'\x06', b'K': b'\x02'}[msvcrt.getch()]
        return ch

class _GetchMacCarbon:
    """
    A function which returns the current ASCII key that is down;
    if no ASCII key is down, the null string is returned.  The
    page http://www.mactech.com/macintosh-c/chap02-1.html was
    very helpful in figuring out how to do this.
    """
    def __init__(self):
        import Carbon
        Carbon.Evt #see if it has this (in Unix, it doesn't)

    def __call__(self):
        import Carbon
        if Carbon.Evt.EventAvail(0x0008)[0]==0: # 0x0008 is the keyDownMask
            return ''
        else:
            #
            # The event contains the following info:
            # (what,msg,when,where,mod)=Carbon.Evt.GetNextEvent(0x0008)[1]
            #
            # The message (msg) contains the ASCII char which is
            # extracted with the 0x000000FF charCodeMask; this
            # number is converted to an ASCII character with chr() and
            # returned
            #
            (what,msg,when,where,mod)=Carbon.Evt.GetNextEvent(0x0008)[1]
            return chr(msg & 0x000000FF)

getch = _Getch()

if __name__ == "__main__":
    ch = getch()
    print('ch =',  ch)

