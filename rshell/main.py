#!/usr/bin/env python3

"""Implement a remote shell which talks to a MicroPython board.

   This program uses the raw-repl feature of the pyboard to send small
   programs to the pyboard to carry out the required tasks.
"""

# Take a look at https://repolinux.wordpress.com/2012/10/09/non-blocking-read-from-stdin-in-python/
# to see if we can uise those ideas here.

# from __future__ import print_function

# To run rshell from the git repository, cd into the top level rshell directory
# and run:
#   python3 -m rhsell.main
#
# that sets things up so that the "from rshell.xxx" will import from the git
# tree and not from some installed version.

import sys
try:
    from rshell.getch import getch
    from rshell.pyboard import Pyboard, PyboardError
    from rshell.version import __version__
except ImportError as err:
    print('sys.path =', sys.path)
    raise err

import argparse
import binascii
import calendar
import cmd
import inspect
import os
import select
import serial
import shutil
import socket
import tempfile
import time
import threading
import shlex
import itertools
from serial.tools import list_ports

import traceback

# I got the following from: http://www.farmckon.net/2009/08/rlcompleter-how-do-i-get-it-to-work/

# Under OSX, if you call input with a prompt which contains ANSI escape
# sequences for colors, and readline is installed, then the escape sequences
# do not get rendered properly as colors.
#
# One solution would be to not use readline, but then you'd lose TAB completion.
# So I opted to print the colored prompt before calling input, which makes
# things work most of the time. If you try to backspace when at the first
# column of the input it wipes out the prompt, but everything returns to normal
# if you hit return.

BROKEN_READLINE = True
FAKE_INPUT_PROMPT = False

import readline
import rlcompleter
if sys.platform == 'darwin':
    readline.parse_and_bind ("bind ^I rl_complete")
    BROKEN_READLINE = True
else:
    readline.parse_and_bind("tab: complete")
MONTH = ('', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
         'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')

# Attributes
# 0 Reset all attributes
# 1 Bright
# 2 Dim
# 4 Underscore
# 5 Blink
# 7 Reverse
# 8 Hidden

LT_BLACK = "\x1b[1;30m"
LT_RED = "\x1b[1;31m"
LT_GREEN = "\x1b[1;32m"
LT_YELLOW = "\x1b[1;33m"
LT_BLUE = "\x1b[1;34m"
LT_MAGENTA = "\x1b[1;35m"
LT_CYAN = "\x1b[1;36m"
LT_WHITE = "\x1b[1;37m"

DK_BLACK = "\x1b[2;30m"
DK_RED = "\x1b[2;31m"
DK_GREEN = "\x1b[2;32m"
DK_YELLOW = "\x1b[2;33m"
DK_BLUE = "\x1b[2;34m"
DK_MAGENTA = "\x1b[2;35m"
DK_CYAN = "\x1b[2;36m"
DK_WHITE = "\x1b[2;37m"

NO_COLOR = "\x1b[0m"
BG_LT_BLACK = "\x1b[1;40m"
BG_LT_RED = "\x1b[1;41m"
BG_LT_GREEN = "\x1b[1;42m"
BG_LT_YELLOW = "\x1b[1;43m"
BG_LT_BLUE = "\x1b[1;44m"
BG_LT_MAGENTA = "\x1b[1;45m"
BG_LT_CYAN = "\x1b[1;46m"
BG_LT_WHITE = "\x1b[1;47m"

BG_DK_BLACK = "\x1b[2;40m"
BG_DK_RED = "\x1b[2;41m"
BG_DK_GREEN = "\x1b[2;42m"
BG_DK_YELLOW = "\x1b[2;43m"
BG_DK_BLUE = "\x1b[2;44m"
BG_DK_MAGENTA = "\x1b[2;45m"
BG_DK_CYAN = "\x1b[2;46m"
BG_DK_WHITE = "\x1b[2;47m"

DIR_COLOR = LT_CYAN
PROMPT_COLOR = LT_GREEN
PY_COLOR = DK_GREEN
END_COLOR = NO_COLOR

cur_dir = ''

HAS_BUFFER = False
IS_UPY = False
DEBUG = False
BUFFER_SIZE = 512
QUIET = False

# It turns out that just because pyudev is installed doesn't mean that
# it can actually be used. So we only bother to try is we're running
# under linux.
USE_AUTOCONNECT = sys.platform == 'linux'

SIX_MONTHS = 183 * 24 * 60 * 60

QUIT_REPL_CHAR = 'X'
QUIT_REPL_BYTE = bytes((ord(QUIT_REPL_CHAR) - ord('@'),))  # Control-X

# DELIMS is used by readline for determining word boundaries.
DELIMS = ' \t\n>;'

# CPython uses Jan 1, 1970 as the epoch, where MicroPython uses Jan 1, 2000
# as the epoch. TIME_OFFSET is the constant number of seconds needed to
# convert from one timebase to the other.
#
# We use UTC time for doing our conversion because MicroPython doesn't really
# understand timezones and has no concept of daylight savings time. UTC also
# doesn't daylight savings time, so this works well.
TIME_OFFSET = calendar.timegm((2000, 1, 1, 0, 0, 0, 0, 0, 0))

DEVS = []
DEFAULT_DEV = None
DEV_IDX = 1

DEV_LOCK = threading.RLock()

def add_device(dev):
    """Adds a device to the list of devices we know about."""
    global DEV_IDX, DEFAULT_DEV
    with DEV_LOCK:
        for idx in range(len(DEVS)):
            test_dev = DEVS[idx]
            if test_dev.dev_name_short == dev.dev_name_short:
                # This device is already in our list. Delete the old one
                if test_dev is DEFAULT_DEV:
                    DEFAULT_DEV = None
                del DEVS[idx]
                break
        if find_device_by_name(dev.name):
            # This name is taken - make it unique
            dev.name += '-%d' % DEV_IDX
        dev.name_path = '/' + dev.name + '/'
        DEVS.append(dev)
        DEV_IDX += 1
        if DEFAULT_DEV is None:
            DEFAULT_DEV = dev


def find_device_by_name(name):
    """Tries to find a board by board name."""
    if not name:
        return DEFAULT_DEV
    with DEV_LOCK:
        for dev in DEVS:
            if dev.name == name:
                return dev
    return None


def find_serial_device_by_port(port):
    """Tries to find a board by port name."""
    with DEV_LOCK:
        for dev in DEVS:
            if dev.is_serial_port(port):
                return dev
    return None


def num_devices():
    with DEV_LOCK:
        return len(DEVS)

def is_micropython_usb_device(port):
    """Checks a USB device to see if it looks like a MicroPython device.
    """
    if type(port).__name__ == 'Device':
        # Assume its a pyudev.device.Device
        if ('ID_BUS' not in port or port['ID_BUS'] != 'usb' or
            'SUBSYSTEM' not in port or port['SUBSYSTEM'] != 'tty'):
            return False
        usb_id = 'usb vid:pid={}:{}'.format(port['ID_VENDOR_ID'], port['ID_MODEL_ID'])
    else:
        # Assume its a port from serial.tools.list_ports.comports()
        usb_id = port[2].lower()
    # We don't check the last digit of the PID since there are 3 possible
    # values.
    if usb_id.startswith('usb vid:pid=f055:980'):
        return True;
    # Check for Teensy VID:PID
    if usb_id.startswith('usb vid:pid=16c0:0483'):
        return True;
    return False


def autoconnect():
    """Sets up a thread to detect when USB devices are plugged and unplugged.
       If the device looks like a MicroPython board, then it will automatically
       connect to it.
    """
    if not USE_AUTOCONNECT:
        return
    try:
        import pyudev
    except ImportError:
        return
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    connect_thread = threading.Thread(target=autoconnect_thread, args=(monitor,), name='AutoConnect')
    connect_thread.daemon = True
    connect_thread.start()


def autoconnect_thread(monitor):
    """Thread which detects USB Serial devices connecting and disconnecting."""
    monitor.start()
    monitor.filter_by('tty')

    epoll = select.epoll()
    epoll.register(monitor.fileno(), select.POLLIN)

    while True:
        try:
            events = epoll.poll()
        except InterruptedError:
            continue
        for fileno, _ in events:
            if fileno == monitor.fileno():
                usb_dev = monitor.poll()
                print('autoconnect: {} action: {}'.format(usb_dev.device_node, usb_dev.action))
                dev = find_serial_device_by_port(usb_dev.device_node)
                if usb_dev.action == 'add':
                    # Try connecting a few times. Sometimes the serial port
                    # reports itself as busy, which causes the connection to fail.
                    for i in range(8):
                        if dev:
                            connected = connect_serial(dev.port, dev.baud, dev.wait)
                        elif is_micropython_usb_device(usb_dev):
                            connected = connect_serial(usb_dev.device_node)
                        else:
                            connected = False
                        if connected:
                            break
                        time.sleep(0.25)
                elif usb_dev.action == 'remove':
                    print('')
                    print("USB Serial device '%s' disconnected" % usb_dev.device_node)
                    if dev:
                        dev.close()
                        break


def autoscan():
    """autoscan will check all of the serial ports to see if they have
       a matching VID:PID for a MicroPython board. If it matches.
    """
    for port in serial.tools.list_ports.comports():
        if is_micropython_usb_device(port):
            connect_serial(port[0])


def escape(str):
    """Precede all special characters with a backslash."""
    out = ''
    for char in str:
        if char in '\\ ':
            out += '\\'
        out += char
    return out


def unescape(str):
    """Undoes the effects of the escape() function."""
    out = ''
    prev_backslash = False
    for char in str:
        if not prev_backslash and char == '\\':
            prev_backslash = True
            continue
        out += char
        prev_backslash = False
    return out


def align_cell(fmt, elem, width):
    """Returns an aligned element."""
    if fmt == "<":
        return elem + ' ' * (width - len(elem))
    if fmt == ">":
        return ' ' * (width - len(elem)) + elem
    return elem


def column_print(fmt, rows, print_func):
    """Prints a formatted list, adjusting the width so everything fits.
    fmt contains a single character for each column. < indicates that the
    column should be left justified, > indicates that the column should
    be right justified. The last column may be a space which imples left
    justification and no padding.

    """
    # Figure out the max width of each column
    num_cols = len(fmt)
    width = [max(0 if isinstance(row, str) else len(row[i]) for row in rows)
             for i in range(num_cols)]
    for row in rows:
        if isinstance(row, str):
            # Print a seperator line
            print_func(' '.join([row * width[i] for i in range(num_cols)]))
        else:
            print_func(' '.join([align_cell(fmt[i], row[i], width[i])
                                 for i in range(num_cols)]))


def find_macthing_files(match):
    """Finds all of the files wihch match (used for completion)."""
    last_slash = match.rfind('/')
    if last_slash == -1:
        dirname = '.'
        match_prefix = match
        result_prefix = ''
    else:
        dirname = match[0:last_slash]
        match_prefix = match[last_slash + 1:]
        result_prefix = dirname + '/'
    return [result_prefix + filename for filename in os.listdir(dirname) if filename.startswith(match_prefix)]


def resolve_path(path):
    """Resolves path and converts it into an absolute path."""
    if path[0] == '~':
        # ~ or ~user
        path = os.path.expanduser(path)
    if path[0] != '/':
        # Relative path
        if cur_dir[-1] == '/':
            path = cur_dir + path
        else:
            path = cur_dir + '/' + path
    comps = path.split('/')
    new_comps = []
    for comp in comps:
        # We strip out xxx/./xxx and xxx//xxx, except that we want to keep the
        # leading / for absolute paths. This also removes the trailing slash
        # that autocompletion adds to a directory.
        if comp == '.' or (comp == '' and len(new_comps) > 0):
            continue
        if comp == '..':
            if len(new_comps) > 1:
                new_comps.pop()
        else:
            new_comps.append(comp)
    if len(new_comps) == 1 and new_comps[0] == '':
        return '/'
    return '/'.join(new_comps)


def get_dev_and_path(filename):
    """Determines if a given file is located locally or remotely. We assume
       that any directories from the pyboard take precendence over local
       directories of the same name. /flash and /sdcard are associated with
       the default device. /dev_name/path where dev_name is the name of a
       given device is also considered to be associaed with the named device.

       If the file is associated with a remote device, then this function
       returns a tuple (dev, dev_filename) where dev is the device and
       dev_filename is the portion of the filename relative to the device.

       If the file is not associated with the remote device, then the dev
       portion of the returned tuple will be None.
    """
    if DEFAULT_DEV:
        if DEFAULT_DEV.is_root_path(filename):
            return (DEFAULT_DEV, filename)
    test_filename = filename + '/'
    with DEV_LOCK:
        for dev in DEVS:
            if test_filename.startswith(dev.name_path):
                dev_filename = filename[len(dev.name_path)-1:]
                if dev_filename == '':
                    dev_filename = '/'
                return (dev, dev_filename)
    return (None, filename)


def remote_repr(i):
    """Helper function to deal with types which we can't send to the pyboard."""
    repr_str = repr(i)
    if repr_str and repr_str[0] == '<':
        return 'None'
    return repr_str


def print_bytes(byte_str):
    """Prints a string or converts bytes to a string and then prints."""
    if isinstance(byte_str, str):
        print(byte_str)
    else:
        print(str(byte_str, encoding='utf8'))


def auto(func, filename, *args, **kwargs):
    """If `filename` is a remote file, then this function calls func on the
       micropython board, otherwise it calls it locally.
    """
    dev, dev_filename = get_dev_and_path(filename)
    if dev is None:
        if dev_filename[0] == '~':
            dev_filename = os.path.expanduser(dev_filename)
        return func(dev_filename, *args, **kwargs)
    return dev.remote_eval(func, dev_filename, *args, **kwargs)


def board_name(default):
    """Returns the boards name (if available)."""
    try:
        import board
        name = board.name
    except ImportError:
        name = default
    return repr(name)


def cat(src_filename, dst_file):
    """Copies the contents of the indicated file to an already opened file."""
    (dev, dev_filename) = get_dev_and_path(src_filename)
    if dev is None:
        with open(dev_filename, 'rb') as txtfile:
            for line in txtfile:
                dst_file.write(line)
    else:
        filesize = dev.remote_eval(get_filesize, dev_filename)
        return dev.remote(send_file_to_host, dev_filename, dst_file, filesize,
                          xfer_func=recv_file_from_remote)

def chdir(dirname):
    """Changes the current working directory."""
    import os
    os.chdir(dirname)


def copy_file(src_filename, dst_filename):
    """Copies a file from one place to another. Both the source and destination
       files must exist on the same machine.
    """
    try:
        with open(src_filename, 'rb') as src_file:
            with open(dst_filename, 'wb') as dst_file:
                while True:
                    buf = src_file.read(BUFFER_SIZE)
                    if len(buf) > 0:
                        dst_file.write(buf)
                    if len(buf) < BUFFER_SIZE:
                        break
        return True
    except:
        return False


def cp(src_filename, dst_filename):
    """Copies one file to another. The source file may be local or remote and
       the destnation file may be local or remote.
    """
    src_dev, src_dev_filename = get_dev_and_path(src_filename)
    dst_dev, dst_dev_filename = get_dev_and_path(dst_filename)
    if src_dev is dst_dev:
        # src and dst are either on the same remote, or both are on the host
        return auto(copy_file, src_filename, dst_dev_filename)

    filesize = auto(get_filesize, src_filename)

    if dst_dev is None:
        # Copying from remote to host
        with open(dst_dev_filename, 'wb') as dst_file:
            return src_dev.remote(send_file_to_host, src_dev_filename, dst_file,
                                  filesize, xfer_func=recv_file_from_remote)
    if src_dev is None:
        # Copying from host to remote
        with open(src_dev_filename, 'rb') as src_file:
            return dst_dev.remote(recv_file_from_host, src_file, dst_dev_filename,
                                  filesize, xfer_func=send_file_to_remote)

    # Copying from remote A to remote B. We first copy the file
    # from remote A to the host and then from the host to remote B
    host_temp_file = tempfile.TemporaryFile()
    if src_dev.remote(send_file_to_host, src_dev_filename, host_temp_file,
                      filesize, xfer_func=recv_file_from_remote):
        host_temp_file.seek(0)
        return dst_dev.remote(recv_file_from_host, host_temp_file, dst_dev_filename,
                              filesize, xfer_func=send_file_to_remote)
    return False


def eval_str(string):
    """Executes a string containing python code."""
    output = eval(string)
    return output


def get_filesize(filename):
    """Returns the size of a file, in bytes."""
    import os
    try:
        # Since this function runs remotely, it can't depend on other functions,
        # so we can't call stat_mode.
        return os.stat(filename)[6]
    except OSError:
        return -1


def get_mode(filename):
    """Returns the mode of a file, which can be used to determine if a file
       exists, if a file is a file or a directory.
    """
    import os
    try:
        # Since this function runs remotely, it can't depend on other functions,
        # so we can't call stat_mode.
        return os.stat(filename)[0]
    except OSError:
        return 0


def get_stat(filename):
    """Returns the stat array for a given file. Returns all 0's if the file
       doesn't exist.
    """
    import os

    def stat(filename):
        rstat = os.stat(filename)
        if IS_UPY:
            # Micropython dates are relative to Jan 1, 2000. On the host, time
            # is relative to Jan 1, 1970.
            return rstat[:7] + tuple(tim + TIME_OFFSET for tim in rstat[7:])
        return rstat
    try:
        return stat(filename)
    except OSError:
        return (0,) * 10


def listdir(dirname):
    """Returns a list of filenames contained in the named directory."""
    import os
    return os.listdir(dirname)


def listdir_matches(match):
    """Returns a list of filenames contained in the named directory.
       Only filenames which start with `match` will be returned.
       Directories will have a trailing slash.
    """
    import os
    last_slash = match.rfind('/')
    if last_slash == -1:
        dirname = '.'
        match_prefix = match
        result_prefix = ''
    else:
        match_prefix = match[last_slash + 1:]
        if last_slash == 0:
            dirname = '/'
            result_prefix = '/'
        else:
            dirname = match[0:last_slash]
            result_prefix = dirname + '/'
    def add_suffix_if_dir(filename):
        if (os.stat(filename)[0] & 0x4000) != 0:
            return filename + '/'
        return filename
    matches = [add_suffix_if_dir(result_prefix + filename)
               for filename in os.listdir(dirname) if filename.startswith(match_prefix)]
    return matches


def listdir_stat(dirname):
    """Returns a list of tuples for each file contained in the named
       directory. Each tuple contains the filename, followed by the tuple
       returned by calling os.stat on the filename.
    """
    import os

    def stat(filename):
        rstat = os.stat(filename)
        if IS_UPY:
            # Micropython dates are relative to Jan 1, 2000. On the host, time
            # is relative to Jan 1, 1970.
            return rstat[:7] + tuple(tim + TIME_OFFSET for tim in rstat[7:])
        return rstat
    if dirname == '/':
        return tuple((file, stat('/' + file))
                     for file in os.listdir(dirname))
    return tuple((file, stat(dirname + '/' + file))
                 for file in os.listdir(dirname))


def make_directory(dirname):
    """Creates one or more directories."""
    import os
    try:
        os.mkdir(dirname)
    except:
        return False
    return True


def mkdir(filename):
    """Creates a directory."""
    return auto(make_directory, filename)


def remove_file(filename, recursive=False, force=False):
    """Removes a file or directory."""
    import os
    try:
        mode = os.stat(filename)[0]
        if mode & 0x4000 != 0:
            # directory
            if recursive:
                for file in os.listdir(filename):
                    success = remove_file(filename + '/' + file, recursive, force)
                    if not success and not force:
                        return False
            os.rmdir(filename)
        else:
            os.remove(filename)
    except:
        if not force:
            return False
    return True


def rm(filename, recursive=False, force=False):
    """Removes a file or directory tree."""
    return auto(remove_file, filename, recursive, force)


def sync(src_dir, dst_dir, mirror=False, dry_run=False, print_func=None):
    """Synchronizes 2 directory trees."""
    src_files = sorted(auto(listdir_stat, src_dir), key=lambda entry: entry[0])
    dst_files = sorted(auto(listdir_stat, dst_dir), key=lambda entry: entry[0])
    for src_basename, src_stat in src_files:
        dst_basename, dst_stat = dst_files[0]
        src_filename = src_dir + '/' + src_basename
        dst_filename = dst_dir + '/' + dst_basename
        if src_basename < dst_basename:
            # Source file/dir which doesn't exist in dest - add it
            continue
        if src_basename == dst_basename:
            src_mode = stat_mode(src_stat)
            dst_mode = stat_mode(dst_stat)
            if mode_isdir(src_mode):
                if mode_isdir(dst_mode):
                    # src and dst re both directories - recurse
                    sync(src_filename, dst_filename,
                         mirror=mirror, dry_run=dry_run, stdout=sys.stdout)
                else:
                    if print_func:
                        print_func("Source '%s' is a directory and "
                                   "destination '%s' is a file. Ignoring"
                                   % (src_filename, dst_filename))
            else:
                if mode_isdir(dst_mode):
                    if print_func:
                        print_func("Source '%s' is a file and "
                                   "destination '%s' is a directory. Ignoring"
                                   % (src_filename, dst_filename))
                else:
                    if stat_mtime(src_stat) > stat_mtime(dst_stat):
                        if print_func:
                            print_func('%s is newer than %s - copying'
                                       % (src_filename, dst_filename))
                        if not dry_run:
                            cp(src_filename, dst_filename)
            continue
        while src_basename > dst_basename:
            # file exists in dst and not in src
            if mirror:
                if print_func:
                    print_func("Removing %s" % dst_filename)
                if not dry_run:
                    rm(dst_filename)
            del dst_files[0]
            dst_basename, dst_stat = dst_files[0]


def set_time(rtc_time):
    import pyb
    rtc = pyb.RTC()
    rtc.datetime(rtc_time)


# 0x0D's sent from the host get transformed into 0x0A's, and 0x0A sent to the
# host get converted into 0x0D0A when using sys.stdin. sys.tsin.buffer does
# no transformations, so if that's available, we use it, otherwise we need
# to use hexlify in order to get unaltered data.

def recv_file_from_host(src_file, dst_filename, filesize, dst_mode='wb'):
    """Function which runs on the pyboard. Matches up with send_file_to_remote."""
    import sys
    import ubinascii
    try:
        import pyb
        usb = pyb.USB_VCP()
        if HAS_BUFFER and usb.isconnected():
            # We don't want 0x03 bytes in the data to be interpreted as a Control-C
            # This gets reset each time the REPL runs a line, so we don't need to
            # worry about resetting it ourselves
            usb.setinterrupt(-1)
    except ImportError:
        # This means that there is no pyb module, which happens on the wipy
        pass
    try:
        with open(dst_filename, dst_mode) as dst_file:
            bytes_remaining = filesize
            if not HAS_BUFFER:
                bytes_remaining *= 2  # hexlify makes each byte into 2
            buf_size = BUFFER_SIZE
            write_buf = bytearray(buf_size)
            read_buf = bytearray(buf_size)
            while bytes_remaining > 0:
                read_size = min(bytes_remaining, buf_size)
                buf_remaining = read_size
                buf_index = 0
                while buf_remaining > 0:
                    if HAS_BUFFER:
                        bytes_read = sys.stdin.buffer.readinto(read_buf, bytes_remaining)
                    else:
                        bytes_read = sys.stdin.readinto(read_buf, bytes_remaining)
                    if bytes_read > 0:
                        write_buf[buf_index:bytes_read] = read_buf[0:bytes_read]
                        buf_index += bytes_read
                        buf_remaining -= bytes_read
                if HAS_BUFFER:
                    dst_file.write(write_buf[0:read_size])
                else:
                    dst_file.write(ubinascii.unhexlify(write_buf[0:read_size]))
                # Send back an ack as a form of flow control
                sys.stdout.write('\x06')
                bytes_remaining -= read_size
        return True
    except:
        return False


def send_file_to_remote(dev, src_file, dst_filename, filesize, dst_mode='wb'):
    """Intended to be passed to the `remote` function as the xfer_func argument.
       Matches up with recv_file_from_host.
    """
    bytes_remaining = filesize
    while bytes_remaining > 0:
        if HAS_BUFFER:
            buf_size = BUFFER_SIZE
        else:
            buf_size = BUFFER_SIZE // 2
        read_size = min(bytes_remaining, buf_size)
        buf = src_file.read(read_size)
        #sys.stdout.write('\r%d/%d' % (filesize - bytes_remaining, filesize))
        #sys.stdout.flush()
        if HAS_BUFFER:
            dev.write(buf)
        else:
            dev.write(binascii.hexlify(buf))
        # Wait for ack so we don't get too far ahead of the remote
        while True:
            char = dev.read(1)
            if char == b'\x06':
                break
            # This should only happen if an error occurs
            sys.stdout.write(chr(ord(char)))
        bytes_remaining -= read_size
    #sys.stdout.write('\r')


def recv_file_from_remote(dev, src_filename, dst_file, filesize):
    """Intended to be passed to the `remote` function as the xfer_func argument.
       Matches up with send_file_to_host.
    """
    bytes_remaining = filesize
    if not HAS_BUFFER:
        bytes_remaining *= 2  # hexlify makes each byte into 2
    buf_size = BUFFER_SIZE
    write_buf = bytearray(buf_size)
    while bytes_remaining > 0:
        read_size = min(bytes_remaining, buf_size)
        buf_remaining = read_size
        buf_index = 0
        while buf_remaining > 0:
            read_buf = dev.read(buf_remaining)
            bytes_read = len(read_buf)
            if bytes_read:
                write_buf[buf_index:bytes_read] = read_buf[0:bytes_read]
                buf_index += bytes_read
                buf_remaining -= bytes_read
        if HAS_BUFFER:
            dst_file.write(write_buf[0:read_size])
        else:
            dst_file.write(binascii.unhexlify(write_buf[0:read_size]))
        # Send an ack to the remote as a form of flow control
        dev.write(b'\x06')   # ASCII ACK is 0x06
        bytes_remaining -= read_size


def send_file_to_host(src_filename, dst_file, filesize):
    """Function which runs on the pyboard. Matches up with recv_file_from_remote."""
    import sys
    import ubinascii
    try:
        with open(src_filename, 'rb') as src_file:
            bytes_remaining = filesize
            if HAS_BUFFER:
                buf_size = BUFFER_SIZE
            else:
                buf_size = BUFFER_SIZE // 2
            while bytes_remaining > 0:
                read_size = min(bytes_remaining, buf_size)
                buf = src_file.read(read_size)
                if HAS_BUFFER:
                    sys.stdout.buffer.write(buf)
                else:
                    sys.stdout.write(ubinascii.hexlify(buf))
                bytes_remaining -= read_size
                # Wait for an ack so we don't get ahead of the remote
                while True:
                    char = sys.stdin.read(1)
                    if char:
                        if char == '\x06':
                            break
                        # This should only happen if an error occurs
                        sys.stdout.write(char)
        return True
    except:
        return False


def test_buffer():
    """Checks the micropython firmware to see if sys.stdin.buffer exists."""
    import sys
    try:
        _ = sys.stdin.buffer
        return True
    except:
        return False


def test_readinto():
    """Checks the micropython firmware to see if sys.stdin.readinto exists."""
    import sys
    try:
        _ = sys.stdin.readinto
        return True
    except:
        return False


def test_unhexlify():
    """Checks the micropython firmware to see if ubinascii.unhexlify exists."""
    import ubinascii
    try:
        _ = ubinascii.unhexlify
        return True
    except:
        return False


def mode_exists(mode):
    return mode & 0xc000 != 0


def mode_isdir(mode):
    return mode & 0x4000 != 0


def mode_isfile(mode):
    return mode & 0x8000 != 0


def stat_mode(stat):
    """Returns the mode field from the results returne by os.stat()."""
    return stat[0]


def stat_size(stat):
    """Returns the filesize field from the results returne by os.stat()."""
    return stat[6]


def stat_mtime(stat):
    """Returns the mtime field from the results returne by os.stat()."""
    return stat[8]


def word_len(word):
    """Returns the word lenght, minus any color codes."""
    if word[0] == '\x1b':
        return len(word) - 11   # 7 for color, 4 for no-color
    return len(word)


def print_cols(words, print_func, termwidth=79):
    """Takes a single column of words, and prints it as multiple columns that
    will fit in termwidth columns.
    """
    width = max([word_len(word) for word in words])
    nwords = len(words)
    ncols = max(1, (termwidth + 1) // (width + 1))
    nrows = (nwords + ncols - 1) // ncols
    for row in range(nrows):
        for i in range(row, nwords, nrows):
            word = words[i]
            if word[0] == '\x1b':
                print_func('%-*s' % (width + 11, words[i]),
                           end='\n' if i + nrows >= nwords else ' ')
            else:
                print_func('%-*s' % (width, words[i]),
                           end='\n' if i + nrows >= nwords else ' ')


def decorated_filename(filename, stat):
    """Takes a filename and the stat info and returns the decorated filename.
       The decoration takes the form of a single character which follows
       the filename. Currently, the only decodation is '/' for directories.
    """
    mode = stat[0]
    if mode_isdir(mode):
        return DIR_COLOR + filename + END_COLOR + '/'
    if filename.endswith('.py'):
        return PY_COLOR + filename + END_COLOR
    return filename


def is_hidden(filename):
    """Determines if the file should be considered to be a "hidden" file."""
    return filename[0] == '.' or filename[-1] == '~'


def is_visible(filename):
    """Just a helper to hide the double negative."""
    return not is_hidden(filename)


def print_long(filename, stat, print_func):
    """Prints detailed information about the file passed in."""
    size = stat_size(stat)
    mtime = stat_mtime(stat)
    file_mtime = time.gmtime(mtime)
    curr_time = time.time()
    if mtime > curr_time or mtime < (curr_time - SIX_MONTHS):
        print_func('%6d %s %2d %04d  %s' % (size, MONTH[file_mtime[1]],
                                            file_mtime[2], file_mtime[0],
                                            decorated_filename(filename, stat)))
    else:
        print_func('%6d %s %2d %02d:%02d %s' % (size, MONTH[file_mtime[1]],
                                                file_mtime[2], file_mtime[3], file_mtime[4],
                                                decorated_filename(filename, stat)))


def trim(docstring):
    """Trims the leading spaces from docstring comments.

    From http://www.python.org/dev/peps/pep-0257/

    """
    if not docstring:
        return ''
    # Convert tabs to spaces (following the normal Python rules)
    # and split into a list of lines:
    lines = docstring.expandtabs().splitlines()
    # Determine minimum indentation (first line doesn't count):
    indent = sys.maxsize
    for line in lines[1:]:
        stripped = line.lstrip()
        if stripped:
            indent = min(indent, len(line) - len(stripped))
    # Remove indentation (first line is special):
    trimmed = [lines[0].strip()]
    if indent < sys.maxsize:
        for line in lines[1:]:
            trimmed.append(line[indent:].rstrip())
    # Strip off trailing and leading blank lines:
    while trimmed and not trimmed[-1]:
        trimmed.pop()
    while trimmed and not trimmed[0]:
        trimmed.pop(0)
    # Return a single string:
    return '\n'.join(trimmed)


def add_arg(*args, **kwargs):
    """Returns a list containing args and kwargs."""
    return (args, kwargs)


def connect(port, baud=115200, user='micro', password='python', wait=0):
    """Tries to connect automagically vie network or serial."""
    try:
        ip_address = socket.gethostbyname(port)
        #print('Connecting to ip', ip_address)
        connect_telnet(port, ip_address, user=user, password=password)
    except socket.gaierror:
        # Doesn't look like a hostname or IP-address, assume its a serial port
        #print('connecting to serial', port)
        connect_serial(port, baud=baud, wait=wait)


def connect_telnet(name, ip_address=None, user='micro', password='python'):
    """Connect to a MicroPython board via telnet."""
    if ip_address is None:
        try:
            ip_address = socket.gethostbyname(name)
        except socket.gaierror:
            ip_address = name
    if not QUIET:
        if name == ip_address:
            print('Connecting to (%s) ...' % ip_address)
        else:
            print('Connecting to %s (%s) ...' % (name, ip_address))
    dev = DeviceNet(name, ip_address, user, password)
    add_device(dev)


def connect_serial(port, baud=115200, wait=0):
    """Connect to a MicroPython board via a serial port."""
    if not QUIET:
        print('Connecting to %s ...' % port)
    try:
        dev = DeviceSerial(port, baud, wait)
    except DeviceError as err:
        sys.stderr.write(str(err))
        sys.stderr.write('\n')
        return False
    add_device(dev)
    return True


class SmartFile(object):
    """Class which implements a write method which can takes bytes or str."""

    def __init__(self, file):
        self.file = file

    def close(self):
        self.file.close()

    def flush(self):
        self.file.flush()

    def read(self, num_bytes):
        return self.file.buffer.read(num_bytes)

    def seek(self, pos):
        self.file.seek(pos)

    def tell(self):
        return self.file.tell()

    def write(self, data):
        if isinstance(data, str):
            return self.file.write(data)
        return self.file.buffer.write(data)


class DeviceError(Exception):
    """Errors that we want to report to the user and keep running."""
    pass


class Device(object):

    def __init__(self, pyb):
        self.pyb = pyb
        self.has_buffer = False  # needs to be set for remote_eval to work
        self.has_buffer = self.remote_eval(test_buffer)
        if self.has_buffer:
            if DEBUG:
                print("Setting has_buffer to True")
        elif not self.remote_eval(test_unhexlify):
            raise ShellError('rshell needs MicroPython firmware with ubinascii.unhexlify')
        else:
            if DEBUG:
                print("MicroPython has unhexlify")
        self.root_dirs = ['/{}/'.format(dir) for dir in self.remote_eval(listdir, '/')]
        self.sync_time()
        self.name = self.remote_eval(board_name, self.default_board_name())

    def check_pyb(self):
        """Raises an error if the pyb object was closed."""
        if self.pyb is None:
            raise DeviceError('serial port %s closed' % self.dev_name_short)

    def close(self):
        """Closes the serial port."""
        if self.pyb and self.pyb.serial:
            self.pyb.serial.close()
        self.pyb = None

    def is_root_path(self, filename):
        """Determines if 'filename' corresponds to a directory on this device."""
        test_filename = filename + '/'
        for root_dir in self.root_dirs:
            if test_filename.startswith(root_dir):
                return True
        return False

    def is_serial_port(self, port):
        return False

    def read(self, num_bytes):
        """Reads data from the pyboard over the serial port."""
        self.check_pyb()
        try:
            return self.pyb.serial.read(num_bytes)
        except (serial.serialutil.SerialException, TypeError):
            # Write failed - assume that we got disconnected
            self.close()
            raise DeviceError('serial port %s closed' % self.dev_name_short)

    def remote(self, func, *args, xfer_func=None, **kwargs):
        """Calls func with the indicated args on the micropython board."""
        global HAS_BUFFER
        HAS_BUFFER = self.has_buffer
        args_arr = [remote_repr(i) for i in args]
        kwargs_arr = ["{}={}".format(k, remote_repr(v)) for k, v in kwargs.items()]
        func_str = inspect.getsource(func)
        func_str += 'output = ' + func.__name__ + '('
        func_str += ', '.join(args_arr + kwargs_arr)
        func_str += ')\n'
        func_str += 'if output is None:\n'
        func_str += '    print("None")\n'
        func_str += 'else:\n'
        func_str += '    print(output)\n'
        func_str = func_str.replace('TIME_OFFSET', '{}'.format(TIME_OFFSET))
        func_str = func_str.replace('HAS_BUFFER', '{}'.format(HAS_BUFFER))
        func_str = func_str.replace('BUFFER_SIZE', '{}'.format(BUFFER_SIZE))
        func_str = func_str.replace('IS_UPY', 'True')
        if DEBUG:
            print('----- About to send %d bytes of code to the pyboard -----' % len(func_str))
            print(func_str)
            print('-----')
        self.check_pyb()
        try:
            self.pyb.enter_raw_repl()
            self.check_pyb()
            output = self.pyb.exec_raw_no_follow(func_str)
            if xfer_func:
                xfer_func(self, *args, **kwargs)
            self.check_pyb()
            output, _ = self.pyb.follow(timeout=10)
            self.check_pyb()
            self.pyb.exit_raw_repl()
        except (serial.serialutil.SerialException, TypeError):
            self.close()
            raise DeviceError('serial port %s closed' % self.dev_name_short)
        if DEBUG:
            print('-----Response-----')
            print(output)
            print('-----')
        return output

    def remote_eval(self, func, *args, **kwargs):
        """Calls func with the indicated args on the micropython board, and
           converts the response back into python by using eval.
        """
        return eval(self.remote(func, *args, **kwargs))

    def status(self):
        """Returns a status string to indicate whether we're connected to
           the pyboard or not.
        """
        if self.pyb is None:
            return 'closed'
        return 'connected'

    def sync_time(self):
        """Sets the time on the pyboard to match the time on the host."""
        now = time.localtime(time.time())
        self.remote(set_time, (now.tm_year, now.tm_mon, now.tm_mday, now.tm_wday + 1,
                               now.tm_hour, now.tm_min, now.tm_sec, 0))

    def write(self, buf):
        """Writes data to the pyboard over the serial port."""
        self.check_pyb()
        try:
            return self.pyb.serial.write(buf)
        except (serial.serialutil.SerialException, BrokenPipeError, TypeError):
            # Write failed - assume that we got disconnected
            self.close()
            raise DeviceError('{} closed'.format(self.dev_name_short))


class DeviceSerial(Device):

    def __init__(self, port, baud, wait):
        self.port = port
        self.baud = baud
        self.wait = wait

        if wait and not os.path.exists(port):
            toggle = False
            try:
                sys.stdout.write("Waiting %d seconds for serial port '%s' to exist" % (wait, port))
                sys.stdout.flush()
                while wait and not os.path.exists(port):
                    sys.stdout.write('.')
                    sys.stdout.flush()
                    time.sleep(0.5)
                    toggle = not toggle
                    wait = wait if not toggle else wait -1
                sys.stdout.write("\n")
            except KeyboardInterrupt:
                raise DeviceError('Interrupted')

        self.dev_name_short = port
        self.dev_name_long = '%s at %d baud' % (port, baud)

        try:
            pyb = Pyboard(port, baudrate=baud, wait=wait)
        except PyboardError as err:
            print(err)
            sys.exit(1)

        # Bluetooth devices take some time to connect at startup, and writes
        # issued while the remote isn't connected will fail. So we send newlines
        # with pauses until one of our writes suceeds.
        try:
            # we send a Control-C which should kill the current line
            # assuming we're talking to tha micropython repl. If we send
            # a newline, then the junk might get interpreted as a command
            # which will do who knows what.
            pyb.serial.write(b'\x03')
        except serial.serialutil.SerialException:
            # Write failed. Now report that we're waiting and keep trying until
            # a write succeeds
            sys.stdout.write("Waiting for transport to be connected.")
            while True:
                time.sleep(0.5)
                try:
                    pyb.serial.write(b'\x03')
                    break
                except serial.serialutil.SerialException:
                    pass
                sys.stdout.write('.')
                sys.stdout.flush()
            sys.stdout.write('\n')

        # In theory the serial port is now ready to use
        Device.__init__(self, pyb)

    def default_board_name(self):
        return 'pyboard'

    def is_serial_port(self, port):
        return self.dev_name_short == port

    def timeout(self, timeout=None):
        """Sets the timeout associated with the serial port."""
        self.check_pyb()
        if timeout is None:
            return self.pyb.serial.timeout
        try:
            self.pyb.serial.timeout = timeout
        except:
            # timeout is a property so it calls code, and that can fail
            # if the serial port is closed.
            pass


class DeviceNet(Device):

    def __init__(self, name, ip_address, user, password):
        self.dev_name_short = '{} ({})'.format(name, ip_address)
        self.dev_name_long = self.dev_name_short

        try:
            pyb = Pyboard(ip_address, user=user, password=password)
        except (socket.timeout, OSError):
            raise DeviceError('No response from {}'.format(ip_address))
        except KeyboardInterrupt:
            raise DeviceError('Interrupted')
        Device.__init__(self, pyb)

    def default_board_name(self):
        return 'wipy'

    def timeout(self, timeout=None):
        """There is no equivalent to timeout for the telnet connection."""
        return None

class AutoBool(object):
    """A simple class which allows a boolean to be set to False in conjunction
       with a with: statement.
    """

    def __init__(self):
        self.value = False

    def __enter__(self):
        self.value = True

    def __exit__(self, type, value, traceback):
        self.value = False

    def __call__(self):
        return self.value


class ShellError(Exception):
    """Errors that we want to report to the user and keep running."""
    pass


class Shell(cmd.Cmd):
    """Implements the shell as a command line interpreter."""

    def __init__(self, filename=None, timing=False, **kwargs):
        cmd.Cmd.__init__(self, **kwargs)
        if 'stdin' in kwargs:
            cmd.Cmd.use_rawinput = 0

        self.real_stdout = self.stdout
        self.smart_stdout = SmartFile(self.stdout)

        self.stderr = SmartFile(sys.stderr)

        self.filename = filename
        self.line_num = 0
        self.timing = timing

        global cur_dir
        cur_dir = os.getcwd()
        self.prev_dir = cur_dir
        self.columns = shutil.get_terminal_size().columns

        self.redirect_dev = None
        self.redirect_filename = ''
        self.redirect_mode = ''

        self.quit_when_no_output = False
        self.quit_serial_reader = False
        readline.set_completer_delims(DELIMS)

        self.set_prompt()

    def set_prompt(self):
        if self.stdin == sys.stdin:
            prompt = PROMPT_COLOR + cur_dir + END_COLOR + '> '
            if FAKE_INPUT_PROMPT:
                print(prompt, end='')
                self.prompt = ''
            else:
                self.prompt = prompt
        else:
            # Executing commands from a file
            self.prompt = ''

    def cmdloop(self, line=None):
        if line:
            line = self.precmd(line)
            stop = self.onecmd(line)
            stop = self.postcmd(stop, line)
        else:
            cmd.Cmd.cmdloop(self)

    def onecmd(self, line):
        """Override onecmd.

        1 - So we don't have to have a do_EOF method.
        2 - So we can strip comments
        3 - So we can track line numbers
        """
        if DEBUG:
            print('Executing "%s"' % line)
        self.line_num += 1
        if line == "EOF":
            if cmd.Cmd.use_rawinput:
                # This means that we printed a prompt, and we'll want to
                # print a newline to pretty things up for the caller.
                self.print('')
            return True
        # Strip comments
        comment_idx = line.find("#")
        if comment_idx >= 0:
            line = line[0:comment_idx]
            line = line.strip()

        # search multiple commands on the same line
        lexer = shlex.shlex(line)
        lexer.whitespace = ''

        for issemicolon, group in itertools.groupby(lexer, lambda x: x == ";"):
            if not issemicolon:
                self.onecmd_exec("".join(group))

    def onecmd_exec(self, line):
        try:
            if self.timing:
                start_time = time.time()
                result = cmd.Cmd.onecmd(self, line)
                end_time = time.time()
                print('took %.3f seconds' % (end_time - start_time))
                return result
            else:
                return cmd.Cmd.onecmd(self, line)
        except DeviceError as err:
            self.print_err(err)
        except ShellError as err:
            self.print_err(err)
        except SystemExit:
            # When you use -h with argparse it winds up call sys.exit, which
            # raises a SystemExit. We intercept it because we don't want to
            # exit the shell, just the command.
            return False

    def default(self, line):
        self.print_err("Unrecognized command:", line)

    def emptyline(self):
        """We want empty lines to do nothing. By default they would repeat the
        previous command.

        """
        pass
    def precmd(self, line):
        self.stdout = self.smart_stdout
        return line

    def postcmd(self, stop, line):
        if self.stdout != self.smart_stdout:
            if self.redirect_dev is not None:
                # Redirecting to a remote device, now that we're finished the
                # command, we can copy the collected output to the remote.
                if DEBUG:
                    print('Copy redirected output to "%s"' % self.redirect_filename)
                # This belongs on the remote. Copy/append now
                filesize = self.stdout.tell()
                self.stdout.seek(0)
                self.redirect_dev.remote(recv_file_from_host, self.stdout,
                                         self.redirect_filename, filesize,
                                         dst_mode=self.redirect_mode,
                                         xfer_func=send_file_to_remote)
            self.stdout.close()
        self.stdout = self.real_stdout
        if not stop:
            self.set_prompt()
        return stop

    def print(self, *args, end='\n', file=None):
        """Convenience function so you don't need to remember to put the \n
           at the end of the line.
        """
        if file is None:
            file = self.stdout
        s = ' '.join(str(arg) for arg in args) + end
        file.write(s)

    def print_err(self, *args, end='\n'):
        """Similar to print, but prints to stderr.
        """
        self.print(*args, end=end, file=self.stderr)
        self.stderr.flush()

    def create_argparser(self, command):
        try:
            argparse_args = getattr(self, "argparse_" + command)
        except AttributeError:
            return None
        doc_lines = getattr(self, "do_" + command).__doc__.expandtabs().splitlines()
        if '' in doc_lines:
            blank_idx = doc_lines.index('')
            usage = doc_lines[:blank_idx]
            description = doc_lines[blank_idx+1:]
        else:
            usage = doc_lines
            description = []
        parser = argparse.ArgumentParser(
            prog=command,
            usage='\n'.join(usage),
            description='\n'.join(description)
        )
        for args, kwargs in argparse_args:
            parser.add_argument(*args, **kwargs)
        return parser

    def filename_complete(self, text, line, begidx, endidx):
        """Wrapper for catching exceptions since cmd seems to silently
           absorb them.
        """
        try:
            return self.real_filename_complete(text, line, begidx, endidx)
        except:
            traceback.print_exc()

    def real_filename_complete(self, text, line, begidx, endidx):
        """Figure out what filenames match the completion."""

        # line contains the full command line that's been entered so far.
        # text contains the portion of the line that readline is trying to complete
        # text should correspond to line[begidx:endidx]
        #
        # The way the completer works text will start after one of the characters
        # in DELIMS. So if the filename entered so far was "embedded\ sp" and
        # then text will point to the s in sp.
        #
        # The following bit of logic backs up to find the real beginning of the
        # filename.

        for before_match in range(begidx, 0, -1):
            if line[before_match] in DELIMS and before_match >= 1 and line[before_match - 1] != '\\':
                break

        # We set fixed to be the portion of the filename which is before text
        # and match is the full portion of the filename that's been entered so
        # far (that's that part we use for matching files).
        #
        # When we return a list of completions, the bit that we return should
        # just be the portion that we replace 'text' with.

        fixed = unescape(line[before_match+1:begidx]) # fixed portion of the match
        match = unescape(line[before_match+1:endidx]) # portion to match filenames against

        # We do the following to cover the case that the current directory
        # is / and the path being entered is relative.
        if match[0] == '/':
            abs_match = match
        elif cur_dir == '/':
            abs_match = cur_dir + match
        else:
            abs_match = cur_dir + '/' + match

        completions = []
        prepend = ''
        if abs_match.rfind('/') == 0:  # match is in the root directory
            # This means that we're looking for matches in the root directory
            # (i.e. abs_match is /foo and the user hit TAB).
            # So we'll supply the matching board names as possible completions.
            # Since they're all treated as directories we leave the trailing slash.
            with DEV_LOCK:
                if match[0] == '/':
                    completions += [dev.name_path for dev in DEVS if dev.name_path.startswith(abs_match)]
                else:
                    completions += [dev.name_path[1:] for dev in DEVS if dev.name_path.startswith(abs_match)]
            if DEFAULT_DEV:
                # Add root directories of the default device (i.e. /flash/ and /sd/)
                if match[0] == '/':
                    completions += [root_dir for root_dir in DEFAULT_DEV.root_dirs if root_dir.startswith(match)]
                else:
                    completions += [root_dir[1:] for root_dir in DEFAULT_DEV.root_dirs if root_dir[1:].startswith(match)]
        else:
            # This means that there are at least 2 slashes in abs_match. If one
            # of them matches a board name then we need to remove the board
            # name from fixed. Since the results from listdir_matches won't
            # contain the board name, we need to prepend each of the completions.
            with DEV_LOCK:
                for dev in DEVS:
                    if abs_match.startswith(dev.name_path):
                        prepend = dev.name_path[:-1]

        paths = sorted(auto(listdir_matches, match))
        for path in paths:
            path = prepend + path
            completions.append(escape(path.replace(fixed, '', 1)))
        return completions

    def directory_complete(self, text, line, begidx, endidx):
        """Figure out what directories match the completion."""
        return [filename for filename in self.filename_complete(text, line, begidx, endidx) if filename[-1] == '/']

    def line_to_args(self, line):
        """This will convert the line passed into the do_xxx functions into
        an array of arguments and handle the Output Redirection Operator.
        """
        args = line.split()
        self.redirect_filename = ''
        self.redirect_dev = None
        redirect_index = -1
        if '>' in args:
            redirect_index = args.index('>')
        elif '>>' in args:
            redirect_index = args.index('>>')
        if redirect_index >= 0:
            if redirect_index + 1 >= len(args):
                raise ShellError("> requires a filename")
            self.redirect_filename = resolve_path(args[redirect_index + 1])
            rmode = auto(get_mode, os.path.dirname(self.redirect_filename))
            if not mode_isdir(rmode):
                raise ShellError("Unable to redirect to '%s', directory doesn't exist" %
                                 self.redirect_filename)
            if args[redirect_index] == '>':
                self.redirect_mode = 'w'
                if DEBUG:
                    print('Redirecting (write) to', self.redirect_filename)
            else:
                self.redirect_mode = 'a'
                if DEBUG:
                    print('Redirecting (append) to', self.redirect_filename)
            self.redirect_dev, self.redirect_filename = get_dev_and_path(self.redirect_filename)
            try:
                if self.redirect_dev is None:
                    self.stdout = SmartFile(open(self.redirect_filename, self.redirect_mode))
                else:
                    # Redirecting to a remote device. We collect the results locally
                    # and copy them to the remote device at the end of the command.
                    self.stdout = SmartFile(tempfile.TemporaryFile(mode='w+'))
            except OSError as err:
                raise ShellError(err)

            del args[redirect_index + 1]
            del args[redirect_index]
        curr_cmd, _, _ = self.parseline(self.lastcmd)
        parser = self.create_argparser(curr_cmd)
        if parser:
            args = parser.parse_args(args)
        return args

    def do_args(self, line):
        """args [arguments...]

           Debug function for verifying argument parsing. This function just
           prints out each argument that it receives.
        """
        args = self.line_to_args(line)
        for idx in range(len(args)):
            self.print("arg[%d] = '%s'" % (idx, args[idx]))

    def do_boards(self, _):
        """boards

           Lists the boards that rshell is currently connected to.
        """
        rows = []
        with DEV_LOCK:
            for dev in DEVS:
                if dev is DEFAULT_DEV:
                    dirs = [dir[:-1] for dir in dev.root_dirs]
                else:
                    dirs = []
                dirs += ['/{}{}'.format(dev.name, dir)[:-1] for dir in dev.root_dirs]
                dirs = 'Dirs: ' + ' '.join(dirs)
                rows.append((dev.name, '@ %s' % dev.dev_name_short, dev.status(), dirs))
        if rows:
            column_print('<<< ', rows, self.print)
        else:
            print('No boards connected')

    def complete_cat(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_cat(self, line):
        """cat FILENAME...

           Concatinates files and sends to stdout.
        """
        # note: when we get around to supporting cat from stdin, we'll need
        #       to write stdin to a temp file, and then copy the file
        #       since we need to know the filesize when copying to the pyboard.
        args = self.line_to_args(line)
        for filename in args:
            filename = resolve_path(filename)
            mode = auto(get_mode, filename)
            if not mode_exists(mode):
                self.print_err("Cannot access '%s': No such file" % filename)
                continue
            if not mode_isfile(mode):
                self.print_err("'%s': is not a file" % filename)
                continue
            cat(filename, self.stdout)

    def complete_cd(self, text, line, begidx, endidx):
        return self.directory_complete(text, line, begidx, endidx)

    def do_cd(self, line):
        """cd DIRECTORY

           Changes the current directory. ~ expansion is supported, and cd -
           goes to the previous directory.
        """
        args = self.line_to_args(line)
        if len(args) == 0:
            dirname = '~'
        else:
            if args[0] == '-':
                dirname = self.prev_dir
            else:
                dirname = args[0]
        dirname = resolve_path(dirname)

        mode = auto(get_mode, dirname)
        if mode_isdir(mode):
            global cur_dir
            self.prev_dir = cur_dir
            cur_dir = dirname
            auto(chdir, dirname)
        else:
            self.print_err("Directory '%s' does not exist" % dirname)

    def do_connect(self, line):
        """connect TYPE TYPE_PARAMS
           connect serial port [baud]
           connect telnet ip-address-or-name

           Connects a pyboard to rshell.
        """
        args = self.line_to_args(line)
        num_args = len(args)
        if num_args < 1:
            self.print_err('Missing connection TYPE')
            return
        connect_type = args[0]
        if connect_type == 'serial':
            if num_args < 2:
                self.print_err('Missing serial port')
                return
            port = args[1]
            if num_args < 3:
                baud = 115200
            else:
                try:
                    baud = int(args[2])
                except ValueError:
                    self.print_err("Expecting baud to be numeric. Found '{}'".format(args[2]))
                    return
            connect_serial(port, baud)
        elif connect_type == 'telnet':
            if num_args < 2:
                self.print_err('Missing hostname or ip-address')
                return
            name = args[1]
            connect_telnet(name)
        else:
            self.print_err('Unrecognized connection TYPE: {}'.format(connect_type))

    def complete_cp(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_cp(self, line):
        """cp SOURCE DEST
           cp SOURCE... DIRECTORY

           Copies the SOURCE file to DEST. DEST may be a filename or a
           directory name. If more than one source file is specified, then
           the destination should be a directory.
        """
        args = self.line_to_args(line)
        if len(args) < 2:
            self.print_err('Missing desintation file')
            return
        dst_dirname = resolve_path(args[-1])
        dst_mode = auto(get_mode, dst_dirname)
        for src_filename in args[:-1]:
            src_filename = resolve_path(src_filename)
            src_mode = auto(get_mode, src_filename)
            if not mode_exists(src_mode):
                self.print_err("File '{}' doesn't exist".format(src_filename))
                return False
            if mode_isdir(dst_mode):
                dst_filename = dst_dirname + '/' + os.path.basename(src_filename)
            else:
                dst_filename = dst_dirname
            if not cp(src_filename, dst_filename):
                self.print_err("Unable to copy '%s' to '%s'" %
                               (src_filename, dst_filename))
                break

    def do_echo(self, line):
        """echo TEXT...

           Display a line of text.
        """
        args = self.line_to_args(line)
        self.print(*args)

    def complete_edit(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_edit(self, line):
        """edit FILE

           Copies the file locally, launches an editor to edit the file.
           When the editor exits, if the file was modified then its copied
           back.

           You can specify the editor used with the --editor command line
           option when you start rshell, or by using the VISUAL or EDITOR
           environment variable. if none of those are set, then vi will be used.
        """
        if len(line) == 0:
            self.print_err("Must provide a filename")
            return
        filename = resolve_path(line)
        dev, dev_filename = get_dev_and_path(filename)
        mode = auto(get_mode, filename)
        if mode_exists(mode) and mode_isdir(mode):
            self.print_err("Unable to edit directory '{}'".format(filename))
            return
        if dev is None:
            # File is local
            os.system("{} '{}'".format(EDITOR, filename))
        else:
            # File is remote
            with tempfile.TemporaryDirectory() as temp_dir:
                local_filename = os.path.join(temp_dir, os.path.basename(filename))
                if mode_exists(mode):
                    print('Retrieving {} ...'.format(filename))
                    cp(filename, local_filename)
                old_stat = get_stat(local_filename)
                os.system("{} '{}'".format(EDITOR, local_filename))
                new_stat = get_stat(local_filename)
                if old_stat != new_stat:
                    self.print('Updating {} ...'.format(filename))
                    cp(local_filename, filename)

    def complete_filesize(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_filesize(self, line):
        """filesize FILE

           Prints the size of the file, in bytes. This function is primarily
           testing.
        """
        if len(line) == 0:
            self.print_err("Must provide a filename")
            return
        filename = resolve_path(line)
        self.print(auto(get_filesize, filename))

    def complete_filesize(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_filetype(self, line):
        """filetype FILE

           Prints the type of file (dir or file). This function is primarily
           for testing.
        """
        if len(line) == 0:
            self.print_err("Must provide a filename")
            return
        filename = resolve_path(line)
        mode = auto(get_mode, filename)
        if mode_exists(mode):
            if mode_isdir(mode):
                self.print('dir')
            elif mode_isfile(mode):
                self.print('file')
            else:
                self.print('unknown')
        else:
            self.print('missing')

    def do_help(self, line):
        """help [COMMAND]

           List available commands with no arguments, or detailed help when
           a command is provided.
        """
        # We provide a help function so that we can trim the leading spaces
        # from the docstrings. The builtin help function doesn't do that.
        if not line:
            cmd.Cmd.do_help(self, line)
            self.print("Use Control-D to exit rshell.")
            return
        parser = self.create_argparser(line)
        if parser:
            parser.print_help()
            return
        try:
            doc = getattr(self, 'do_' + line).__doc__
            if doc:
                self.print("%s" % trim(doc))
                return
        except AttributeError:
            pass
        self.print(str(self.nohelp % (line,)))

    argparse_ls = (
        add_arg(
            '-a', '--all',
            dest='all',
            action='store_true',
            help='do not ignore hidden files',
            default=False
        ),
        add_arg(
            '-l', '--long',
            dest='long',
            action='store_true',
            help='use a long listing format',
            default=False
        ),
        add_arg(
            'filenames',
            metavar='FILE',
            nargs='*',
            help='Files or directories to list'
        ),
    )

    def complete_ls(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_ls(self, line):
        """ls [-a] [-l] FILE...

           List directory contents.
        """
        args = self.line_to_args(line)
        if len(args.filenames) == 0:
            args.filenames = ['.']
        for idx in range(len(args.filenames)):
            filename = resolve_path(args.filenames[idx])
            stat = auto(get_stat, filename)
            mode = stat_mode(stat)
            if not mode_exists(mode):
                self.print_err("Cannot access '%s': No such file or directory" %
                               filename)
                continue
            if not mode_isdir(mode):
                if args.long:
                    print_long(filename, stat, self.print)
                else:
                    self.print(filename)
                continue
            if len(args.filenames) > 1:
                if idx > 0:
                    self.print('')
                self.print("%s:" % filename)
            files = []
            for filename, stat in sorted(auto(listdir_stat, filename),
                                         key=lambda entry: entry[0]):
                if is_visible(filename) or args.all:
                    if args.long:
                        print_long(filename, stat, self.print)
                    else:
                        files.append(decorated_filename(filename, stat))
            if len(files) > 0:
                print_cols(sorted(files), self.print, self.columns)

    def complete_mkdir(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_mkdir(self, line):
        """mkdir DIRECTORY...

           Creates one or more directories.
        """
        args = self.line_to_args(line)
        for filename in args:
            filename = resolve_path(filename)
            if not mkdir(filename):
                self.print_err('Unable to create %s' % filename)

    def repl_serial_to_stdout(self, dev):
        """Runs as a thread which has a sole purpose of readding bytes from
           the seril port and writing them to stdout. Used by do_repl.
        """
        with self.serial_reader_running:
            try:
                save_timeout = dev.timeout()
                # Set a timeout so that the read returns periodically with no data
                # and allows us to check whether the main thread wants us to quit.
                dev.timeout(1)
                while not self.quit_serial_reader:
                    try:
                        char = dev.read(1)
                    except serial.serialutil.SerialException:
                        # This happens if the pyboard reboots, or a USB port
                        # goes away.
                        return
                    except TypeError:
                        # These is a bug in serialposix.py starting with python 3.3
                        # which causes a TypeError during the handling of the
                        # select.error. So we treat this the same as
                        # serial.serialutil.SerialException:
                        return
                    except ConnectionResetError:
                        # This happens over a telnet seesion, if it resets
                        return
                    if not char:
                        # This means that the read timed out. We'll check the quit
                        # flag and return if needed
                        if self.quit_when_no_output:
                            break
                        continue
                    self.stdout.write(char)
                    self.stdout.flush()
                dev.timeout(save_timeout)
            except DeviceError:
                # The device is no longer present.
                return

    def do_repl(self, line):
        """repl [board-name] [~ line [~]]

           Enters into the regular REPL with the MicroPython board.
           Use Control-X to exit REPL mode and return the shell. It may take
           a second or two before the REPL exits.

           If you prvide a line to the repl command, then that will be executed.
           If you want the repl to exit, end the line with the ~ character.
        """
        args = self.line_to_args(line)
        if len(args) > 0 and line[0] != '~':
            name = args[0]
            line = ' '.join(args[1:])
        else:
            name = ''
        dev = find_device_by_name(name)
        if not dev:
            self.print_err("Unable to find board '%s'" % name)
            return

        if line[0:2] == '~ ':
            line = line[2:]

        self.print('Entering REPL. Use Control-%c to exit.' % QUIT_REPL_CHAR)
        self.quit_serial_reader = False
        self.quit_when_no_output = False
        self.serial_reader_running = AutoBool()
        repl_thread = threading.Thread(target=self.repl_serial_to_stdout, args=(dev,), name='REPL_serial_to_stdout')
        repl_thread.daemon = True
        repl_thread.start()
        # Wait for reader to start
        while not self.serial_reader_running():
            pass
        try:
            # Wake up the prompt
            dev.write(b'\r')
            if line:
                if line[-1] == '~':
                    line = line[:-1]
                    self.quit_when_no_output = True
                dev.write(bytes(line, encoding='utf-8'))
                dev.write(b'\r')
            if not self.quit_when_no_output:
                while self.serial_reader_running():
                    char = getch()
                    if not char:
                        continue
                    if char == QUIT_REPL_BYTE:
                        self.quit_serial_reader = True
                        # When using telnet with the WiPy, it doesn't support
                        # an initial timeout. So for the meantime, we send a
                        # space which should cause the wipy to echo back a
                        # space which will wakeup our reader thread so it will
                        # notice the quit.
                        dev.write(b' ')
                        # Give the reader thread a chance to detect the quit
                        # then we don't have to call getch() above again which
                        # means we'd need to wait for another character.
                        time.sleep(0.5)
                        # Print a newline so that the rshell prompt looks good.
                        self.print('')
                        # We stay in the loop so that we can still enter
                        # characters until we detect the reader thread quitting
                        # (mostly to cover off weird states).
                        continue
                    if char == b'\n':
                        dev.write(b'\r')
                    else:
                        dev.write(char)
        except DeviceError as err:
            # The device is no longer present.
            self.print('')
            self.stdout.flush()
            self.print_err(err)
        repl_thread.join()

    argparse_rm = (
        add_arg(
            '-r', '--recursive',
            dest='recursive',
            action='store_true',
            help='remove directories and their contents recursively',
            default=False
        ),
        add_arg(
            '-f', '--force',
            dest='force',
            action='store_true',
            help='ignore nonexistant files and arguments',
            default=False
        ),
        add_arg(
            'filename',
            metavar='FILE',
            nargs='+',
            help='File to remove'
        ),
    )

    def complete_rm(self, text, line, begidx, endidx):
        return self.filename_complete(text, line, begidx, endidx)

    def do_rm(self, line):
        """rm [-r|--recursive][-f|--force] FILE...

           Removes files or directories (directories must be empty).
        """
        args = self.line_to_args(line)
        for filename in args.filename:
            filename = resolve_path(filename)
            if not rm(filename, recursive=args.recursive, force=args.force):
                if not args.force:
                    self.print_err('Unable to remove', filename)
                break

    def do_shell(self, line):
        """!some-shell-command args

           Launches a shell and executes whatever command you provide. If you
           don't provide any commands, then it will launch a bash sub-shell
           and when exit from bash (Control-D) then it will return to rshell.
        """
        if not line:
            line = '/bin/bash'
        os.system(line)

    argparse_sync = (
        add_arg(
            '-m', '--mirror',
            dest='mirror',
            action='store_true',
            help="causes files in the destination which don't exist in"
                 "the source to be removed. Without --mirror only file"
                 "copies occur, not deletions will occur.",
            default=False,
        ),
        add_arg(
            '-n', '--dry-run',
            dest='dry_run',
            action='store_true',
            help='shows what would be done without actually performing any file copies',
            default=False
        ),
        add_arg(
            'src_dir',
            metavar='SRC_DIR',
            help='Source directory'
        ),
        add_arg(
            'dst_dir',
            metavar='DEST_DIR',
            help='Destination directory'
        ),
    )
    # Do_sync isn't fully implemented/tested yet, hence the leading underscore.
    def _do_sync(self, line):
        """sync [-m|--mirror] [-n|--dry-run] SRC_DIR DEST_DIR

           Synchronizes a destination directory tree with a source directory tree.
        """
        args = self.line_to_args(line)
        src_dir = resolve_path(args.src_dir)
        dst_dir = resolve_path(args.dst_dir)
        sync(src_dir, dst_dir, mirror=args.mirror, dry_run=args.dry_run)


def real_main():
    """The main program."""
    try:
        default_baud = int(os.getenv('RSHELL_BAUD'))
    except:
        default_baud = 115200
    default_port = os.getenv('RSHELL_PORT')
    #if not default_port:
    #    default_port = '/dev/ttyACM0'
    default_user = os.getenv('RSHELL_USER') or 'micro'
    default_password = os.getenv('RSHELL_PASSWORD') or 'python'
    default_editor = os.getenv('RSHELL_EDITOR') or os.getenv('VISUAL') or os.getenv('EDITOR') or 'vi'
    global BUFFER_SIZE
    try:
        default_buffer_size = int(os.getenv('RSHELL_BUFFER_SIZE'))
    except:
        default_buffer_size = BUFFER_SIZE
    parser = argparse.ArgumentParser(
        prog="rshell",
        usage="%(prog)s [options] [command]",
        description="Remote Shell for a MicroPython board.",
        epilog=("You can specify the default serial port using the " +
                "RSHELL_PORT environment variable.")
    )
    parser.add_argument(
        "-b", "--baud",
        dest="baud",
        action="store",
        type=int,
        help="Set the baudrate used (default = %d)" % default_baud,
        default=default_baud
    )
    parser.add_argument(
        "--buffer-size",
        dest="buffer_size",
        action="store",
        type=int,
        help="Set the buffer size used for transfers (default = %d)" % default_buffer_size,
        default=default_buffer_size
    )
    parser.add_argument(
        "-p", "--port",
        dest="port",
        help="Set the serial port to use (default '%s')" % default_port,
        default=default_port
    )
    parser.add_argument(
        "-u", "--user",
        dest="user",
        help="Set username to use (default '%s')" % default_user,
        default=default_user
    )
    parser.add_argument(
        "-w", "--password",
        dest="password",
        help="Set password to use (default '%s')" % default_password,
        default=default_password
    )
    parser.add_argument(
        "-e", "--editor",
        dest="editor",
        help="Set the editor to use (default '%s')" % default_editor,
        default=default_editor
    )
    parser.add_argument(
        "-f", "--file",
        dest="filename",
        help="Specifies a file of commands to process."
    )
    parser.add_argument(
        "-d", "--debug",
        dest="debug",
        action="store_true",
        help="Enable debug features",
        default=False
    )
    parser.add_argument(
        "-n", "--nocolor",
        dest="nocolor",
        action="store_true",
        help="Turn off colorized output",
        default=False
    )
    parser.add_argument(
        "--wait",
        dest="wait",
        type=int,
        action="store",
        help="Seconds to wait for serial port",
        default=0
    )
    parser.add_argument(
        "--timing",
        dest="timing",
        action="store_true",
        help="Print timing information about each command",
        default=False
    )
    parser.add_argument(
        '-V', '--version',
        dest='version',
        action='store_true',
        help='Reports the version and exits.',
        default=False
    )
    parser.add_argument(
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Turns off some output (useful for testing)",
        default=False
    )
    parser.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="Optional command to execute"
    )
    args = parser.parse_args(sys.argv[1:])

    if args.debug:
        print("Debug = %s" % args.debug)
        print("Port = %s" % args.port)
        print("Baud = %d" % args.baud)
        print("User = %s" % args.user)
        print("Password = %s" % args.password)
        print("Wait = %d" % args.wait)
        print("nocolor = %d" % args.nocolor)
        print("Timing = %d" % args.timing)
        print("Quiet = %d" % args.quiet)
        print("Buffer_size = %d" % args.buffer_size)
        print("Cmd = [%s]" % ', '.join(args.cmd))

    if args.version:
        print(__version__)
        return

    global DEBUG
    DEBUG = args.debug

    global QUIET
    QUIET = args.quiet

    global EDITOR
    EDITOR = args.editor

    BUFFER_SIZE = args.buffer_size

    if args.nocolor:
        global DIR_COLOR, PROMPT_COLOR, PY_COLOR, END_COLOR
        DIR_COLOR = ''
        PROMPT_COLOR = ''
        PY_COLOR = ''
        END_COLOR = ''
    else:
        if sys.platform == 'darwin':
            # The readline that comes with OSX screws up colors in the prompt
            global FAKE_INPUT_PROMPT
            FAKE_INPUT_PROMPT = True

    if args.port:
        try:
            connect(args.port, baud=args.baud, wait=args.wait, user=args.user, password=args.password)
        except DeviceError as err:
            print(err)
    else:
        autoscan()
    autoconnect()

    if args.filename:
        with open(args.filename) as cmd_file:
            shell = Shell(stdin=cmd_file, filename=args.filename, timing=args.timing)
            shell.cmdloop('')
    else:
        cmd_line = ' '.join(args.cmd)
        if cmd_line == '':
            print('Welcome to rshell. Use Control-D to exit.')
        if num_devices() == 0:
            print('')
            print('No MicroPython boards connected - use the connect command to add one')
            print('')
        shell = Shell(timing=args.timing)
        try:
            shell.cmdloop(cmd_line)
        except KeyboardInterrupt:
            print('')

def main():
    """This main function saves the stdin termios settings, calls real_main,
       and restores stdin termios settings when it returns.
    """
    save_settings = None
    stdin_fd = -1
    try:
        import termios
        stdin_fd = sys.stdin.fileno()
        save_settings = termios.tcgetattr(stdin_fd)
    except ImportError:
        pass
    try:
        real_main()
    finally:
        if save_settings:
            termios.tcsetattr(stdin_fd, termios.TCSANOW, save_settings)

if __name__ == "__main__":
    main()
