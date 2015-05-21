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

# Commands

## args
```
args [arguments...]
```
Debug function for verifying argument parsing. This function just
prints out each argument that it receives.

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
repl
```
Enters into the regular REPL with the MicroPython board.
Use Control-X to exit REPL mode and return the shell. It may take
a second or two before the REPL exits.

If you prvide a line to the repl command, then that will be executed.
If you want the repl to exit, end the line with the ~ character.

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
# Installation

rshell.py needs getch.py and pyboard.py. There is a copy of getch.py and 
pyboard.py in this repository, in the same directory that rshell.py came from.

