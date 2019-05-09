import os
#move to sdcard if on remote 
try:
    os.chdir('/sd')
except OSError:
    pass

os.mkdir('dir1')
os.mkdir('dir2')

def make_files(files):
    for name in files:
        with open(name, 'w') as f:
            f.write('hello ')
            f.write(name + '\n')

make_files(('a.txt', 'b.txt', 'c.txt'))
os.chdir('dir1')
make_files(('d1a.txt', 'd1b.txt', 'd1c.txt'))
os.chdir('../dir2')
make_files(('d2a.txt', 'd2b.txt', 'd2c.txt'))
os.mkdir('depth')
os.chdir('depth')
make_files(('depa.txt', 'depb.txt'))
os.mkdir('deeper')
os.chdir('deeper')
make_files(('deepra.txt', 'deeprb.txt'))
