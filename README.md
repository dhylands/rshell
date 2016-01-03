rshell.py
=========

Remote MicroPytyhon shell.

This is a simple shell which runs on the host and uses MicroPython's raw-repl
to send python snippets to the pyboard in order to get filesystem information,
and to copy files to and from MicroPython's filesystem.

It also has the ability to invoke the regular REPL, so rshell can be used
as a terminal emulator as well.

Note: With rshell you can disable USB Mass Storage and still copy files into
and out of your pyboard.

When using the commands, the /flash directory, and the /sdcard directory
(if an sdcard is inserted) are considered to be on the pyboard, and all
other directories are considered to be on the host.

NOTE: rshell requires a fairly recent version of the MicroPython firmware,
specifically one which contains the ubinascii.unhexlify command which was
added May 19, 2015 (v1.4.3-28-ga3a14b9 or newer).

If your verion of the firmware isn't new enough, then you'll see an error
message something like this:
```
>./rshell.py
rshell needs MicroPython firmware with ubinascii.unhexlify
```

# Installation

rshell.py needs Python3. All of my testing was done using version 3.4.0.

rshell.py needs getch.py and pyboard.py. There is a copy of getch.py and 
pyboard.py in this repository, in the same directory that rshell.py came from.

You'll also need to install pyserial. In ubuntu I did
```
sudo pip3 install pyserial
```

# Sample Session

This shows a pyboard in its default state, copying a hello.py and then entering
the repl and importing it.

```
>./rshell.py
Welcome to rshell. Use Control-D to exit.
/home/dhylands/Dropbox/micropython/upy-shell/rshell> ls -l /flash
   529 May 21 17:34 README.txt
   286 May 21 17:34 boot.py
    34 May 21 17:34 main.py
  2436 May 21 17:34 pybcdc.inf
/home/dhylands/Dropbox/micropython/upy-shell/rshell> cp hello.py /flash
/home/dhylands/Dropbox/micropython/upy-shell/rshell> ls -l /flash
   529 May 21 17:34 README.txt
   286 May 21 17:34 boot.py
    21 May 21 17:35 hello.py
    34 May 21 17:34 main.py
  2436 May 21 17:34 pybcdc.inf
/home/dhylands/Dropbox/micropython/upy-shell/rshell> cat /flash/hello.py
print('Hello World')
/home/dhylands/Dropbox/micropython/upy-shell/rshell> repl
Entering REPL. Use Control-X to exit.

Micro Python v1.4.3-28-ga3a14b9 on 2015-05-21; PYBv1.0 with STM32F405RG
Type "help()" for more information.
>>> 
>>> import hello
Hello World
>>> 
/home/dhylands/Dropbox/micropython/upy-shell/rshell> 
```

# Command Line Options

## -h, --help

Displays a lit of the valid options. You should get something like the
following displayed:
```
usage: rshell [options] [command]

Remote Shell for a MicroPython board.

positional arguments:
  cmd                   Optional command to execute

optional arguments:
  -h, --help            show this help message and exit
  -p PORT, --port PORT  Set the serial port to use (default '/dev/ttyACM0')
  -f FILENAME, --file FILENAME
                        Specifies a file of commands to process.
  -d, --debug           Enable debug features
  -n, --nocolor         Turn off colorized output

You can specify the default serial port using the RSHELL_PORT environment
variable.
```
## -p PORT, --port PORT 
Specifies the serial port which should be used to talk to the MicroPython board.
You can set the RSHELL_PORT environment variable to specify the default port
to be used, if --port is not specified on the command line.

## -f FILENAME, --file FILENAME
Specifies a file of rshell commands to process. This allows you to create
a script which executes any valid rshell commands.

## -d, --debug
Turns on debugging. This allows you to see the script which is sent over the
raw REPL and the response received.

## -n, --nocolor
By default, rshell uses ANSI color escape codes when displaying the prompt
and ls output. This option allows colorized output to be disabled.

# File System

rshell can be connected to multiple pyboards simultaneously. If the board
module exists on the pyboard (i.e. a file named board.py somewhere in the
module search path) and it contains an attribute called name
then the pyboard will use that name. If the board module can't be imported
then the board will be named, pyboard or wipy. Names will have -1 (or some
other number) to make the board name unique.

You can access the internal flash on the first board connected using /flash
and the sd card on the first board connected can be accessed using /sd.

For all other connected pyboards, you can use /board-name/flash or
/board-name/sd (you can see the board names using the boards command).

# Commands

## args
```
args [arguments...]
```
Debug function for verifying argument parsing. This function just
prints out each argument that it receives.

## boards
```
boards
```
Lists all of the boards that rshell is currently connected to, their names,
and the connection.

## cat
```
cat FILENAME...
```
Concatinates files and sends to stdout.

## cd
```
cd DIRECTORY
```
Changes the current directory. ~ expansion is supported, and cd -
goes to the previous directory.

## connect

```
connect TYPE TYPE_PARAMS
connect serial port [baud]
connect telnet ip-address-or-name
```
Connects a pyboard to rshell. rshell can be connected to multiple pyboards
simultaneously.

## cp
```
cp SOURCE DEST
cp SOURCE... DIRECTORY
```
Copies the SOURCE file to DEST. DEST may be a filename or a
directory name. If more than one source file is specified, then
the destination should be a directory.

## echo
```
echo TEXT...
```
Display a line of text.

## edit
```
edit filename
```
If the file is on a pyboard, it copies the file to host, invokes an editor
and if any changes were made to the file, it copies it back to the pyboard.

The editor which is used defaults to vi, but can be overridem using either
the --editor command line option when rshell.py is invoked, or by using
the RSHELL_EDITOR, VISUAL or EDITOR environment variables (they are tried
in the order listed).

## filesize
```
filesize FILE
```
Prints the size of the file, in bytes. This function is primarily
testing.

## filetype
```
filetype FILE
```
Prints the type of file (dir or file). This function is primarily
for testing.

## help
```
help [COMMAND]
```
List available commands with no arguments, or detailed help when
a command is provided.

## ls
```
usage: ls [-a] [-l] FILE...

List directory contents.

positional arguments:
  FILE        Files or directories to list

optional arguments:
  -h, --help  show this help message and exit
  -a, --all   do not ignore hidden files
  -l, --long  use a long listing format
```
## mkdir
```
mkdir DIRECTORY...
```
Creates one or more directories.

## repl
```
repl [board-name] [~ line][~]
```
Enters into the regular REPL with the MicroPython board.
Use Control-X to exit REPL mode and return the shell. It may take
a second or two before the REPL exits.

If you provide a board-name then rshell will connect to that board,
otherwise it will connect to the default board (first connected board).

If you provide a tilde followed by a space (~ ) then anything after the
tilde will be entered as if you typed it on the command line.

If you want the repl to exit, end the line with the ~ character.

For example, you could use:
```
rshell.py repl ~ pyb.bootloader()~
```
and it will boot the pyboard into DFU.

## rm
```
usage: rm [-r|--recursive][-f|--force] FILE...

Removes files or directories (directories must be empty).

positional arguments:
  FILE             File to remove

optional arguments:
  -h, --help       show this help message and exit
  -r, --recursive  remove directories and their contents recursively
  -f, --force      ignore nonexistant files and arguments
```

