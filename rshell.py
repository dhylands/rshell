#!/usr/bin/env python3

"""Implement a remote shell which talks to a MicroPython board.

   This program uses the raw-repl feature of the pyboard to send small
   programs to the pyboard to carry out the required tasks.
"""

# from __future__ import print_function

import argparse
import binascii
import calendar
import cmd
from getch import getch
import inspect
import os
import pyboard
import select
import serial
import shutil
import sys
import tempfile
import time

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

LT_BLACK    = "\x1b[1;30m"
LT_RED      = "\x1b[1;31m"
LT_GREEN    = "\x1b[1;32m"
LT_YELLOW   = "\x1b[1;33m"
LT_BLUE     = "\x1b[1;34m"
LT_MAGENTA  = "\x1b[1;35m"
LT_CYAN     = "\x1b[1;36m"
LT_WHITE    = "\x1b[1;37m"

DK_BLACK    = "\x1b[2;30m"
DK_RED      = "\x1b[2;31m"
DK_GREEN    = "\x1b[2;32m"
DK_YELLOW   = "\x1b[2;33m"
DK_BLUE     = "\x1b[2;34m"
DK_MAGENTA  = "\x1b[2;35m"
DK_CYAN     = "\x1b[2;36m"
DK_WHITE    = "\x1b[2;37m"

NO_COLOR    = "\x1b[0m"

DIR_COLOR    = LT_CYAN
PROMPT_COLOR = LT_GREEN
PY_COLOR     = DK_GREEN
END_COLOR    = NO_COLOR

pyb = None
pyb_root_dirs = []
cur_dir = ''

HAS_BUFFER = False
IS_UPY = False
debug = False

SIX_MONTHS = 183 * 24 * 60 * 60

QUIT_REPL_CHAR = 'X'
QUIT_REPL_BYTE = bytes((ord(QUIT_REPL_CHAR) - ord('@'),)) # Control-X

# CPython uses Jan 1, 1970 as the epoch, where MicroPython uses Jan 1, 2000
# as the epoch. TIME_OFFSET is the constant number of seconds needed to
# convert from one timebase to the other.
#
# We use UTC time for doing our conversion because MicroPython doesn't really
# understand timezones and has no concept of daylight savings time. UTC also
# doesn't daylight savings time, so this works well.
TIME_OFFSET = calendar.timegm((2000, 1, 1, 0, 0, 0, 0, 0, 0))

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
        if comp == '.':
            continue
        if comp == '..' and len(new_comps) > 1:
            new_comps.pop()
        else:
            new_comps.append(comp)
    if len(new_comps) == 1:
        return new_comps[0] + '/'
    return '/'.join(new_comps)


def is_remote_path(filename):
    """Determines if a given file is located locally or remotely. We assume
       that any directories from the pyboard take precendence over local
       directories of the same name. Currently, the pyboard can have /flash
       and /sdcard.
    """
    test_filename = filename + '/'
    for root_dir in pyb_root_dirs:
        if test_filename.startswith(root_dir):
            return   True
    return False


def remote_repr(i):
    """Helper function to deal with types which we can't send to the pyboard."""
    repr_str = repr(i)
    if repr_str and repr_str[0] == '<':
        return 'None'
    return repr_str


def remote(func, *args, xfer_func=None, **kwargs):
    """Calls func with the indicated args on the micropython board."""
    args_arr = [remote_repr(i) for i in args]
    kwargs_arr = ["{}={}".format(k, remote_repr(v)) for k,v in kwargs.items()]
    func_str = inspect.getsource(func)
    func_str += 'output = ' + func.__name__ + '('
    func_str += ', '.join(args_arr + kwargs_arr)
    func_str += ')\n'
    func_str += 'if output is not None:\n'
    func_str += '    print(output)\n'
    func_str = func_str.replace('TIME_OFFSET', '{}'.format(TIME_OFFSET))
    func_str = func_str.replace('HAS_BUFFER', '{}'.format(HAS_BUFFER))
    func_str = func_str.replace('IS_UPY', 'True')
    if debug:
        print('----- About to send the following to the pyboard -----')
        print(func_str)
        print('-----')
    pyb.enter_raw_repl()
    output = pyb.exec_raw_no_follow(func_str)
    if xfer_func:
        xfer_func(*args, **kwargs)
    output, err = pyb.follow(timeout=10)
    pyb.exit_raw_repl()
    if debug:
        print('-----Response-----')
        print(output)
        print('-----')
    return output


def remote_eval(func, *args, **kwargs):
    """Calls func with the indicated args on the micropython board, and
       converts the response back into python by using eval.
    """
    return eval(remote(func, *args, **kwargs))


def print_bytes(byte_str):
    """Prints a string or converts bytes to a string and then prints."""
    if isinstance(byte_str, str):
        self.print(byte_str)
    else:
        self.print(str(byte_str, encoding='utf8'))


def auto(func, filename, *args, **kwargs):
    """If `filename` is a remote file, then this function calls func on the
       micropython board, otherwise it calls it locally.
    """
    if is_remote_path(filename):
        return remote_eval(func, filename, *args, **kwargs)
    return func(filename, *args, **kwargs)


def cat(src_filename, dst_file):
    """Copies the contents of the indicated file to an already opened file."""
    if is_remote_path(src_filename):
        filesize = remote_eval(get_filesize, src_filename)
        return remote(send_file_to_host, src_filename, dst_file, filesize,
                      xfer_func=recv_file_from_remote)
    with open(src_filename, 'rb') as txtfile:
        for line in txtfile:
            dst_file.write(line)


def copy_file(src_filename, dst_filename):
    """Copies a file from one place to another. Both the source and destination
       files must exist on the same machine.
    """
    try:
        with open(src_filename, 'rb') as src_file:
            with open(dst_filename, 'wb') as dst_file:
                while True:
                    buf = src_file.read(512)
                    if len(buf) > 0:
                        dst_file.write(buf)
                    if len(buf) < 512:
                        break
        return True
    except:
        return False


def cp(src_filename, dst_filename):
    """Copies one file to another. The source file may be local or remote and
       the destnation file may be local or remote.
    """
    src_is_remote = is_remote_path(src_filename)
    dst_is_remote = is_remote_path(dst_filename)
    if src_is_remote == dst_is_remote:
        return auto(copy_file, src_filename, dst_filename)
    filesize = auto(get_filesize, src_filename)
    if src_is_remote:
        with open(dst_filename, 'wb') as dst_file:
            return remote(send_file_to_host, src_filename, dst_file, filesize,
                          xfer_func=recv_file_from_remote)
    with open(src_filename, 'rb') as src_file:
        return remote(recv_file_from_host, src_file, dst_filename, filesize,
                      xfer_func=send_file_to_remote)


def eval_str(str):
    """Executes a string containing python code."""
    output = eval(str)
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
        return (0, 0, 0, 0, 0, 0, 0, 0)


def listdir(dirname):
    """Returns a list of filenames contained in the named directory."""
    import os
    return os.listdir(dirname)


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
    return auto(remove_file, filename, recursive, force)


def sync(src_dir, dst_dir, mirror=False, dry_run=False, print_func=None):
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
                         mirror=mirror, dry_run=dry_run, stdout=stdout)
                else:
                    if print_func:
                        print_func("Source '%s' is a directory and "
                                   "destination '%s' is a file. Ignoring"
                                   % (src_filename, dst_filename))
            else:
                if mode_isdir(dst_mode):
                    if print_func:
                        printf_func("Source '%s' is a file and "
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


def set_time(time):
    import pyb
    rtc = pyb.RTC()
    rtc.datetime(time)


def sync_time():
    """Sets the time on the pyboard to match the time on the host."""
    now = time.localtime(time.time())
    remote(set_time, (now.tm_year, now.tm_mon, now.tm_mday, now.tm_wday + 1,
                      now.tm_hour, now.tm_min, now.tm_sec, 0))

# 0x0D's sent from the host get transformed into 0x0A's, and 0x0A sent to the
# host get converted into 0x0D0A when using sys.stdin. sys.tsin.buffer does
# no transformations, so if that's available, we use it, otherwise we need
# to use hexlify in order to get unaltered data.

def recv_file_from_host(src_file, dst_filename, filesize, dst_mode='wb'):
    """Function which runs on the pyboard. Matches up with send_file_to_remote."""
    import sys
    import ubinascii
    try:
        with open(dst_filename, dst_mode) as dst_file:
            bytes_remaining = filesize
            if not HAS_BUFFER:
                bytes_remaining *= 2 # hexlify makes each byte into 2
            buf_size = 512
            write_buf = bytearray(buf_size)
            read_buf = bytearray(buf_size)
            while bytes_remaining > 0:
                read_size = min(bytes_remaining, buf_size)
                buf_remaining = read_size
                buf_index = 0;
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


def send_file_to_remote(src_file, dst_filename, filesize, dst_mode='wb'):
    """Intended to be passed to the `remote` function as the xfer_func argument.
       Matches up with recv_file_from_host.
    """
    bytes_remaining = filesize
    while bytes_remaining > 0:
        if HAS_BUFFER:
            buf_size = 512
        else:
            buf_size = 256
        read_size = min(bytes_remaining,  buf_size)
        buf = src_file.read(read_size)
        if HAS_BUFFER:
            pyb.serial.write(buf)
        else:
            pyb.serial.write(binascii.hexlify(buf))
        # Wait for ack so we don't get too far ahead of the remote
        while True:
            ch = pyb.serial.read(1)
            if ch == b'\x06':
                break
            # This should only happen if an error occurs
            sys.stdout.write(chr(ord(ch)))
        bytes_remaining -= read_size


def recv_file_from_remote(src_filename, dst_file, filesize):
    """Intended to be passed to the `remote` function as the xfer_func argument.
       Matches up with send_file_to_host.
    """
    bytes_remaining = filesize
    if not HAS_BUFFER:
        bytes_remaining *= 2 # hexlify makes each byte into 2
    buf_size = 512
    write_buf = bytearray(buf_size)
    while bytes_remaining > 0:
        read_size = min(bytes_remaining, buf_size)
        buf_remaining = read_size
        buf_index = 0
        while buf_remaining > 0:
            read_buf = pyb.serial.read(buf_remaining)
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
        pyb.serial.write(b'\x06')   # ASCII ACK is 0x06
        bytes_remaining -= read_size


def send_file_to_host(src_filename, dst_file, filesize):
    """Function which runs on the pyboard. Matches up with recv_file_from_remote."""
    import sys
    import ubinascii
    try:
        with open(src_filename, 'rb') as src_file:
            bytes_remaining = filesize
            if HAS_BUFFER:
                buf_size = 512
            else:
                buf_size = 256
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
                    ch = sys.stdin.read(1)
                    if ch:
                        if ch == '\x06':
                            break
                        # This should only happen if an error occurs
                        sys.stdout.write(ch)
        return True
    except:
        return False


def test_buffer():
    """Checks the micropython firmware to see if sys.stdin.buffer exists."""
    import sys
    try:
        x = sys.stdin.buffer
        return True
    except:
        return False


def test_readinto():
    """Checks the micropython firmware to see if sys.stdin.readinto exists."""
    import sys
    try:
        x = sys.stdin.readinto
        return True
    except:
        return False


def test_unhexlify():
    """Checks the micropython firmware to see if ubinascii.unhexlify exists."""
    import ubinascii
    try:
        func = ubinascii.unhexlify
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


class ByteWriter(object):
    """Class which implements a write method which can takes bytes or str."""

    def __init__(self, stdout):
        self.stdout = stdout

    def write(self, data):
        if isinstance(data, str):
            self.stdout.write(bytes(data, encoding='utf-8'))
        else:
            self.stdout.write(data)

    def flush(self):
        self.stdout.flush()

class ShellError(Exception):
    """Errors that we want to report to the user and keep running."""
    pass

class Shell(cmd.Cmd):
    """Implements the shell as a command line interpreter."""

    def __init__(self, filename=None, **kwargs):
        cmd.Cmd.__init__(self, **kwargs)

        self.stdout = ByteWriter(self.stdout.buffer)
        self.stdout_to_shell = self.stdout

        self.filename = filename
        self.line_num = 0

        global cur_dir
        cur_dir = os.getcwd()
        self.set_prompt()
        self.columns = shutil.get_terminal_size().columns

    def set_prompt(self):
        self.prompt = PROMPT_COLOR + cur_dir + END_COLOR + '> '

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
        if debug:
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
        try:
            return cmd.Cmd.onecmd(self, line)
        except ShellError as err:
            self.print(err)
        except SystemExit:
            # When you use -h with argparse it winds up call sys.exit, which
            # raises a SystemExit. We intercept it because we don't want to
            # exit the shell, just the command.
            return False

    def default(self, line):
        self.print("Unrecognized command:", line)

    def emptyline(self):
        """We want empty lines to do nothing. By default they would repeat the
        previous command.

        """
        pass

    def postcmd(self, stop, line):
        if self.stdout != self.stdout_to_shell:
            if is_remote_path(self.redirect_filename):
                if debug:
                    print('Copy redirected output to "%s"' % self.redirect_filename)
                # This belongs on the remote. Copy/append now
                filesize = self.stdout.tell()
                self.stdout.seek(0)
                remote(recv_file_from_host, self.stdout, self.redirect_filename,
                       filesize, dst_mode=self.redirect_mode,
                       xfer_func=send_file_to_remote)
            self.stdout.close()
            self.stdout = self.stdout_to_shell
        self.set_prompt()
        return stop

    def print(self, *args, end='\n'):
        """Convenience function so you don't need to remember to put the \n
           when using self.stdout.write.
        """
        self.stdout.write(bytes(' '.join(str(arg) for arg in args), encoding='utf-8'))
        self.stdout.write(bytes(end, encoding='utf-8'))

    def create_argparser(self, cmd):
        try:
            argparse_args = getattr(self, "argparse_" + cmd)
        except AttributeError:
            return None
        doc_lines = getattr(self, "do_" + cmd).__doc__.expandtabs().splitlines()
        if '' in doc_lines:
            blank_idx = doc_lines.index('')
            usage = doc_lines[:blank_idx]
            description = doc_lines[blank_idx+1:]
        else:
            usage = doc_lines
            description = []
        parser = argparse.ArgumentParser(
            prog=cmd,
            usage='\n'.join(usage),
            description='\n'.join(description)
        )
        for args,kwargs in argparse_args:
            parser.add_argument(*args, **kwargs)
        return parser

    def line_to_args(self, line):
        """This will convert the line passed into the do_xxx functions into
        an array of arguments and handle the Output Redirection Operator.
        """
        args = line.split()
        self.redirect_filename = ''
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
                self.redirect_mode = 'wb'
                if debug:
                    print('Redirecting (write) to', self.redirect_filename)
            else:
                self.redirect_mode = 'ab'
                if debug:
                    print('Redirecting (append) to', self.redirect_filename)
            if is_remote_path(self.redirect_filename):
                self.stdout = tempfile.TemporaryFile()
            else:
                self.stdout = open(self.redirect_filename, self.redirect_mode)

            del args[redirect_index + 1]
            del args[redirect_index]
        cmd, arg, line = self.parseline(self.lastcmd)
        parser = self.create_argparser(cmd)
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

    def do_cat(self, line):
        """cat FILENAME...

           Concatinates files and sends to stdout.
        """
        # Note: when we get around to supporting cat from stdin, we'll need
        #       to write stdin to a temp file, and then copy the file
        #       since we need to know the filesize when copying to the pyboard.
        args = self.line_to_args(line)
        for filename in args:
            filename = resolve_path(filename)
            mode = auto(get_mode, filename)
            if not mode_exists(mode):
                self.print("Cannot access '%s': No such file" % filename)
                continue
            if not mode_isfile(mode):
                self.print("'%s': is not a file" % filename)
                continue
            cat(filename, self.stdout)

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
        else:
            self.print("Directory '%s' does not exist" % dirname)

    def do_cp(self, line):
        """cp SOURCE DEST
           cp SOURCE... DIRECTORY

           Copies the SOURCE file to DEST. DEST may be a filename or a
           directory name. If more than one source file is specified, then
           the destination should be a directory.
        """
        args = self.line_to_args(line)
        if len(args) < 2:
            self.print('Missing desintation file')
            return
        dst_dirname = resolve_path(args[-1])
        dst_mode = auto(get_mode, dst_dirname)
        for src_filename in args[:-1]:
            src_filename = resolve_path(src_filename)
            src_mode = auto(get_mode, src_filename)
            if not mode_exists(src_mode):
                self.print("File '{}' doesn't exist".format(src_filename))
                return False
            if mode_isdir(dst_mode):
                dst_filename = dst_dirname + '/' + os.path.basename(src_filename)
            else:
                dst_filename = dst_dirname
            if not cp(src_filename, dst_filename):
                self.print("Unable to copy '%s' to '%s'" %
                           (src_filename, dst_filename))
                break

    def do_echo(self, line):
        """echo TEXT...

           Display a line of text.
        """
        args = self.line_to_args(line)
        self.print(*args)

    def do_filesize(self, line):
        """filesize FILE

           Prints the size of the file, in bytes. This function is primarily
           testing.
        """
        filename = resolve_path(line)
        print(auto(get_filesize, filename))

    def do_filetype(self, line):
        """filetype FILE

           Prints the type of file (dir or file). This function is primarily
           for testing.
        """
        if len(line) == 0:
            self.print("Must provide a filename")
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
            self.print("Use Control-D to exit rshell.");
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
    def do_ls(self, line):
        """ls [-a] [-l] FILE...

           List directory contents.
        """
        args = self.line_to_args(line)
        if len(args.filenames) == 0:
            args.filenames = ['.']
        for filename in args.filenames:
            filename = resolve_path(filename)
            mode = auto(get_mode, filename)
            if not mode_exists(mode):
                self.print("Cannot access '%s': No such file or directory" % 
                           filename)
                continue
            if not mode_isdir(mode):
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

    def do_mkdir(self, line):
        """mkdir DIRECTORY...

           Creates one or more directories.
        """
        args = self.line_to_args(line)
        for filename in args:
            filename = resolve_path(filename)
            if not mkdir(filename):
                self.print('Unable to create %s' % filename)

    def repl_serial_to_stdout(self):
        """Runs as a thread which has a sole purpose of readding bytes from
           the seril port and writing them to stdout. Used by do_repl.
        """
        save_timeout = pyb.serial.timeout
        # Set a timeout so that the read returns periodically with no data
        # and allows us to check whether the main thread wants us to quit.
        pyb.serial.timeout = 1
        while not self.quit_serial_reader:
            try:
                ch = pyb.serial.read(1)
            except serial.serialutil.SerialException:
                # THis happens if the pyboard reboots, or a USB port
                # goes away.
                return
            if not ch:
                # This means that the read timed out. We'll check the quit
                # flag and return if needed
                if self.quit_when_no_output:
                    break
                continue
            self.stdout.write(ch)
            self.stdout.flush()
        pyb.serial.timeout = save_timeout

    def do_repl(self, line):
        """repl

           Enters into the regular REPL with the MicroPython board.
           Use Control-X to exit REPL mode and return the shell. It may take
           a second or two before the REPL exits.

           If you prvide a line to the repl command, then that will be executed.
           If you want the repl to exit, end the line with the ~ character.
        """
        self.print('Entering REPL. Use Control-%c to exit.' % QUIT_REPL_CHAR)
        import threading
        self.quit_serial_reader = False
        self.quit_when_no_output = False
        t = threading.Thread(target=self.repl_serial_to_stdout)
        t.daemon = True
        t.start()
        # Wake up the prompt
        pyb.serial.write(b'\r')
        if line:
            if line[-1] == '~':
                line = line[:-1]
                self.quit_when_no_output = True
            pyb.serial.write(bytes(line, encoding='utf-8'))
            pyb.serial.write(b'\r')
        if not self.quit_when_no_output:
            while True:
                ch = getch()
                if not ch:
                    continue
                if ch == QUIT_REPL_BYTE:
                    self.print('');
                    self.quit_serial_reader = True
                    break
                if ch == b'\n':
                    pyb.serial.write(b'\r')
                else:
                    pyb.serial.write(ch)
                pyb.serial.flush()
        t.join()

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
    def do_rm(self, line):
        """rm [-r|--recursive][-f|--force] FILE...

           Removes files or directories (directories must be empty).
        """
        args = self.line_to_args(line)
        for filename in args.filename:
            filename = resolve_path(filename)
            if not rm(filename, recursive=args.recursive, force=args.force):
                if not args.force:
                    self.print('Unable to remove', filename)
                break

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


def main():
    """The main program."""
    default_baud = 115200
    default_port = os.getenv("RSHELL_PORT")
    if not default_port:
        default_port = '/dev/ttyACM0'
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
        "-p", "--port",
        dest="port",
        help="Set the serial port to use (default '%s')" % default_port,
        default=default_port
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
        "cmd",
       nargs=argparse.REMAINDER,
        help="Optional command to execute"
    )
    args = parser.parse_args(sys.argv[1:])

    if args.debug:
        print("Baud = %d" % args.baud)
        print("Port = %s" % args.port)
        print("Debug = %s" % args.debug)
        print("Cmd = [%s]" % ', '.join(args.cmd))

    global debug
    debug = args.debug

    if args.nocolor:
        global DIR_COLOR, PROMPT_COLOR, PY_COLOR, END_COLOR
        DIR_COLOR = ''
        PROMPT_COLOR = ''
        PY_COLOR = ''
        END_COLOR = ''

    global pyb
    pyb = pyboard.Pyboard(args.port, baudrate=args.baud)

    if remote_eval(test_buffer):
        global HAS_BUFFER
        HAS_BUFFER = True
        if debug:
            print("Setting HAS_BUFFER to True")
    elif not remote_eval(test_unhexlify):
        print("rshell needs MicroPython firmware with ubinascii.unhexlify")
        return
    else:
        if debug:
            print("MicroPython has unhexlify")

    global pyb_root_dirs
    pyb_root_dirs = ['/{}/'.format(dir) for dir in remote_eval(listdir, '/')]

    sync_time()

    if args.filename:
        with open(args.filename) as cmd_file:
            shell = Shell(stdin=cmd_file, filename=args.filename)
            shell.cmdloop('')
    else:
        cmd_line = ' '.join(args.cmd)
        if cmd_line == '':
            print('Welcome to rshell. Use Control-D to exit.')
        shell = Shell()
        shell.cmdloop(cmd_line)


main()

