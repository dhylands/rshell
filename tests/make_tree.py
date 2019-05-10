import os
#move to sdcard if on remote 
try:
    os.chdir('/sd')
except OSError:
    pass

os.mkdir('dir_a')
os.mkdir('dir_b')

def make_files(files):
    for name in files:
        with open(name, 'w') as f:
            f.write('hello ')
            f.write(name + '\n')

make_files(('a.txt', 'b.txt', 'c.txt'))
os.chdir('dir_a')
make_files(('d1a.txt', 'd1b.txt', 'd1c.txt'))
os.chdir('../dir_b')
make_files(('d2a.txt', 'd2b.txt', 'd2c.txt'))
os.mkdir('depth')
os.chdir('depth')
make_files(('depa.txt', 'depb.txt'))
os.mkdir('deeper')
os.chdir('deeper')
make_files(('deepra.txt', 'deeprb.txt'))

os.chdir('../../..')
os.mkdir('dir1')
os.mkdir('dir1/subdir')
os.mkdir('dir2')
os.mkdir('dir2/subdir')
os.chdir('dir1/subdir')
make_files(('file1',))
os.chdir('../../dir2/subdir')
make_files(('file2',))
