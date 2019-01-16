rshell
=========

Remote MicroPython shell.

This is a simple shell which runs on the host and uses MicroPython's
raw-REPL to send python snippets to the pyboard in order to get
filesystem information, and to copy files to and from MicroPython's
filesystem.

It also has the ability to invoke the regular REPL, so rshell can be
used as a terminal emulator as well.

Note: With rshell you can disable USB Mass Storage and still copy files
into and out of your pyboard.

When using the commands, the /flash directory, and the /sdcard directory
(if an sdcard is inserted) are considered to be on the pyboard, and all
other directories are considered to be on the host. For an ESP based board you
can only reference its directory by using the board name e.g. /pyboard etc..

NOTE: rshell requires a fairly recent version of the MicroPython
firmware, specifically one which contains the ubinascii.unhexlify
command which was added May 19, 2015 (v1.4.3-28-ga3a14b9 or newer).

If your verion of the firmware isn't new enough, then you'll see an
error message something like this:

::

    >./rshell.py
    rshell needs MicroPython firmware with ubinascii.unhexlify

Installation
============

You can install rshell using the command:

::

    sudo pip3 install rshell

If you use a virtualenv, then you don't need the sudo. rshell needs Python3.
All of my testing was done using version 3.4.0.

Debian/Ubuntu users can get pip3 using:

::

    sudo apt-get install python3-pip

Sample Session
==============

This shows a pyboard in its default state, copying a hello.py and then
entering the repl and importing it.

::

    >rshell
    Welcome to rshell. Use Control-D to exit.
    /home/dhylands/Dropbox/micropython/rshell> ls -l /flash
       529 May 21 17:34 README.txt
       286 May 21 17:34 boot.py
        34 May 21 17:34 main.py
      2436 May 21 17:34 pybcdc.inf
    /home/dhylands/Dropbox/micropython/rshell> cp hello.py /flash
    /home/dhylands/Dropbox/micropython/rshell> ls -l /flash
       529 May 21 17:34 README.txt
       286 May 21 17:34 boot.py
        21 May 21 17:35 hello.py
        34 May 21 17:34 main.py
      2436 May 21 17:34 pybcdc.inf
    /home/dhylands/Dropbox/micropython/rshell> cat /flash/hello.py
    print('Hello World')
    /home/dhylands/Dropbox/micropython/rshell> repl
    Entering REPL. Use Control-X to exit.

    Micro Python v1.4.3-28-ga3a14b9 on 2015-05-21; PYBv1.0 with STM32F405RG
    Type "help()" for more information.
    >>>
    >>> import hello
    Hello World
    >>>
    /home/dhylands/Dropbox/micropython/rshell>

Command Line Options
====================

-h, --help
----------

Displays a list of the valid options. You should get something like the
following displayed:

::

    usage: rshell [options] [command]

    Remote Shell for a MicroPython board.

    positional arguments:
      cmd                   Optional command to execute

    optional arguments:
      -h, --help            show this help message and exit
      -b BAUD, --baud BAUD  Set the baudrate used (default = 115200)
      --buffer-size BUFFER_SIZE
                            Set the buffer size used for transfers (default = 512)
      -p PORT, --port PORT  Set the serial port to use (default '/dev/ttyACM0')
      -u USER, --user USER  Set username to use (default 'micro')
      -w PASSWORD, --password PASSWORD
                            Set password to use (default 'python')
      -e EDITOR, --editor EDITOR
                            Set the editor to use (default 'vi')
      -f FILENAME, --file FILENAME
                            Specifies a file of commands to process.
      -d, --debug           Enable debug features
      -n, --nocolor         Turn off colorized output
      --wait                How long to wait for serial port
      --binary              Enable binary file transfer
      --timing              Print timing information about each command
      --quiet               Turns off some output (useful for testing)

    You can specify the default serial port using the RSHELL_PORT environment
    variable.

-b BAUD, --baud BAUD
--------------------

Sets the baud rate to use when talking to the pyboard over a serial port. If
no baud is specified, then the baudrate from the RSHELL_BAUD environment
variable is used. If the RSHELL_BAUD environment variable is not defined then
the default baudrate of 115200 is used.

--buffer-size
-------------

Sets the buffer size used when transferring files between the host and the
pyboard. If no buffer size is specified, then the value from the
RSHELL_BUFFER_SIZE environment variable is used. If the RSHELL_BUFFER_SIZE
environment variable is not defined, then the default of 512 is used.

-d, --debug
-----------

Turns on debugging. This allows you to see the script which is sent over
the raw REPL and the response received.

-e EDITOR, --editor
-------------------

Specifies the editor to use with the edit command. If no editor is specified,
then the following environment variables will be searched: RSHELL_EDITOR,
VISUAL, and EDITOR. If none of those environment variables is set then vi will
be used.

-f FILENAME, --file FILENAME
----------------------------

Specifies a file of rshell commands to process. This allows you to
create a script which executes any valid rshell commands.

-n, --nocolor
-------------

By default, rshell uses ANSI color escape codes when displaying the
prompt and ls output. This option allows colorized output to be
disabled.

-a --ascii
----------

On certain platforms the raw REPL mode is unreliable with particular sequences
of binary characters. Specifying --ascii enables the transfer of binary files
to such platforms. It does this by encoding the data as ASCII hex.

--wait
------

If a port is specified defines how long rshell will wait for the port to exist
and for a connection to be established. The default is 0 seconds specifying an
immediate return.

-p PORT, --port PORT
--------------------

Specifies the serial port which should be used to talk to the
MicroPython board. You can set the RSHELL\_PORT environment variable to
specify the default port to be used, if --port is not specified on the
command line.

--quiet
-------

This option causes the Connecting messages printed when rshell starts to be
suppressed. This is mostly useful for the test scripts.

--timing
--------

If the timing option is specified then rshell will print the amount of time
that each command takes to execute.

-u USER, --user USER
--------------------

Specifies the username to use when logging into a WiPy over telnet. If no
username is specified, then the username from the RSHELL_USER environment
variable is used. If the RSHELL_USER environment variable doesn't exist
then the default username 'micro' is used.

-w PASSWORD, --password PASSWORD
--------------------------------

Specified the password to use when logging into a WiPy over telnet. If no
password is specified, then the password from the RSHELL_PASSWORD environment
variable is used. If the RSHELL_PASSWORD environment variable doesn't exist
then the default password 'python' is used.

cmd
---

If a command is specified, then that command will be executed and rshell will
exit. Examples:

::

    rshell cp somefile.py /flash
    rshell repl ~ pyb.bootloader() ~

File System
===========

rshell can be connected to multiple pyboards simultaneously. If the
board module exists on the pyboard (i.e. a file named board.py somewhere
in the module search path) and it contains an attribute called name
(e.g. :code:`name = "myboard"`) then the pyboard will use that name. If the board
module can't be imported then the board will be named, pyboard or wipy.
Names will have -1 (or some other number) to make the board name unique.

You can access the internal flash on the first board connected using
/flash and the sd card on the first board connected can be accessed
using /sd.

For all other connected pyboards, you can use /board-name/flash or
/board-name/sd (you can see the board names using the boards command).

The boards command will show all of the connected pyboards, along with all of
the directories which map onto that pyboard.

Commands
========

args
----

::

    args [arguments...]

Debug function for verifying argument parsing. This function just prints
out each argument that it receives.

boards
------

::

    boards

Lists all of the boards that rshell is currently connected to, their
names, and the connection.

You can give a custom name to a board with either copying over a :code:`board.py`
file or using the :code:`echo` command, e.g.

::

    echo name="myboard" > /pyboard/board.py

(Remember to exit rshell and re-enter to see the change).

cat
---

::

    cat FILENAME...

Concatenates files and sends to stdout.

cd
--

::

    cd DIRECTORY

Changes the current directory. ~ expansion is supported, and cd - goes
to the previous directory.

connect
-------

::

    connect TYPE TYPE_PARAMS
    connect serial port [baud]
    connect telnet ip-address-or-name

Connects a pyboard to rshell. rshell can be connected to multiple
pyboards simultaneously.

cp
--

::

    usage: cp SOURCE DEST
    cp SOURCE... DIRECTORY
    cp [-r|--recursive] [SOURCE|SRC_DIR]... DIRECTORY
    cp [-r|--recursive] PATTERN DIRECTORY

    positional arguments:
      DEST             A destination file
      SOURCE           File to copy
      SRC_DIR          Directory to copy
      PATTERN          File or directory pattern match string e.g. foo/*.py

    optional arguments:
      -h, --help       show this help message and exit
      -r, --recursive  copy directories recursively

Copies the SOURCE file to DEST. DEST may be a filename or a directory
name. If more than one source file is specified, then the destination
should be a directory.

Directories will only be copied if -r is specified.

A single pattern may be specified, in which case the destination
should be a directory. Pattern matching is performed according to a subset
of the Unix rules (see below).

Recursive copying uses rsync (see below): where a file exists on source
and destination, it will only be copied if the source is newer than the
destination.


echo
----

::

    echo TEXT...

Display a line of text.

edit
----

::

    edit filename

If the file is on a pyboard, it copies the file to host, invokes an
editor and if any changes were made to the file, it copies it back to
the pyboard.

The editor which is used defaults to vi, but can be overridden using
either the --editor command line option when rshell.py is invoked, or by
using the RSHELL\_EDITOR, VISUAL or EDITOR environment variables (they
are tried in the order listed).

filesize
--------

::

    filesize FILE

Prints the size of the file, in bytes. This function is primarily
testing.

filetype
--------

::

    filetype FILE

Prints the type of file (dir or file). This function is primarily for
testing.

help
----

::

    help [COMMAND]

List available commands with no arguments, or detailed help when a
command is provided.

ls
--

::

    usage: ls [-a] [-l] [FILE|DIRECTORY|PATTERN]...

    List directory contents.

    positional arguments:
      FILE        File to list (show absolute path)
      DIRECTORY   Directory (list contents)
      PATTERN     File or directory pattern match string e.g. foo/*.py

    optional arguments:
      -h, --help  show this help message and exit
      -a, --all   do not ignore hidden files
      -l, --long  use a long listing format

Pattern matching is performed according to a subset of the Unix rules
(see below).

mkdir
-----

::

    mkdir DIRECTORY...

Creates one or more directories.

repl
----

::

    repl [board-name] [~ line][ ~]

Enters into the regular REPL with the MicroPython board. Use Control-X
to exit REPL mode and return the shell. It may take a second or two
before the REPL exits.

If you provide a board-name then rshell will connect to that board,
otherwise it will connect to the default board (first connected board).

If you provide a tilde followed by a space (~ ) then anything after the
tilde will be entered as if you typed it on the command line.

If you want the repl to exit, end the line with the ~ character.

For example, you could use:

::

    rshell.py repl ~ pyb.bootloader()~

and it will boot the pyboard into DFU.

If you want to execute multiple Python commands these should be separated
by the ~ character (not the ; character):

::

    rshell.py repl ~ import mymodule ~ mymodule.run()

rm
--

::

    usage: rm [-f|--force] FILE...
    rm [-f|--force] PATTERN
    rm -r [-f|--force] PATTERN
    rm -r [-f|--force] [FILE|DIRECTORY]...

    Removes files or directories (including their contents).

    positional arguments:
      FILE             File to remove
      DIRECTORY        Directory to remove (-r required)
      PATTERN          File matching pattern e.g. *.py

    optional arguments:
      -h, --help       show this help message and exit
      -r, --recursive  remove directories and their contents recursively
      -f, --force      ignore nonexistent files and arguments

A single pattern may be specified. Pattern matching is performed
according to a subset of the Unix rules (see below). Directories
can only be removed if the recursive argument is provided.

Beware of rm -r * or worse.

rsync
-----

::

    usage: rsync [-m|--mirror] [-n|--dry-run] [-v|--verbose] SRC_DIR DEST_DIR

    Recursively synchronises a source directory to a destination.
    Directories must exist.

    positional arguments:
      SRC_DIR          Directory containing source files.
      DEST_DIR         Directory for destination

    optional arguments:
      -h, --help       show this help message and exit
      -m, --mirror     remove files or directories from destination if
                       absent from source.
      -n, --dry-run    make no changes but report what would be done. Implies -v
      -v, --verbose    report changes made.


Synchronisation is performed by comparing the date and time of source
and destination files. Files are copied if the source is newer than the
destination.


shell
-----

The shell command can also be abbreviated using the exclamation point.

::

    shell some-command
    !some-command

This will invoke a command, and return back to rshell. Example:

::

    !make deploy

will flash the pyboard.

Pattern Matching
================

This is performed according to a subset of the Unix rules. The limitations
are that wildcards are only allowed in the rightmost directory of a path and
curly bracket {} syntax is unsupported:

::

    *.py Match files in current directory with a .py extension
    temp/x[0-9]a.* Match temp/x1a.bmp but not temp/x00a.bmp

    t*/*.bmp Invalid: will produce an error message
    {*.doc,*.pdf} Invalid: will produce an error message
