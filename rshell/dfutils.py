#!/usr/bin/env python3

"""Implements tooling for formatting df command columns"""

from enum import Enum


def convert_bytes(size, unit = '', always_append_unit = False):
    """Converts size in bytes to closest power of 1024: Ki, Mi, Gi, etc.
    """
    single_unit = '' if always_append_unit else unit
    appendix = unit if always_append_unit else ''
    for x in [single_unit, 'Ki', 'Mi', 'Gi', 'Ti']:
        if size < 1024.0:
            return "%3.1f%s%s" % (size, x, appendix)
        size /= 1024.0

    return size

def convert_bytes_si(size, unit = '', always_append_unit = False):
    """Converts size in bytes to closest power of 1000: K, M, G, etc.
    """
    single_unit = '' if always_append_unit else unit
    appendix = unit if always_append_unit else ''
    for x in [single_unit, 'K', 'M', 'G', 'T']:
        if size < 1000.0:
            return "%3.1f%s%s" % (size, x, appendix)
        size /= 1000.0

    return size


class DByteFormat(Enum):
    """Enum for selecting the formatting for size in bytes
    """

    BYTES = 1
    """Output in bytes
    """

    HUMAN = 2
    """Output in human readable format: powers of 1024
    """

    HUMAN_SI = 3
    """Output in human readable format: powers of 1000
    """


class DfColumn:

    def title(self):
        pass

    def formatted(statvfs, dev_name, dir):
        pass


class DfNumColumn(DfColumn):

    def __init__(self, num_format = '{:d}'):
        self.num_format = num_format

    def formatted(self, statvfs, dev_name, dir):
        value = self.get_num_value(statvfs)
        return self.num_format.format(value)

    def get_num_value(self, statvfs):
        pass


class DfByteColumn(DfNumColumn):

    def __init__(self, byte_format):
        self.byte_format = byte_format
        super().__init__('{:d}B')

    def formatted(self, statvfs, dev_name, dir):
        value = self.get_num_value(statvfs)
        if self.byte_format == DByteFormat.HUMAN:
            return convert_bytes(value, 'B')
        elif self.byte_format == DByteFormat.HUMAN_SI:
            return convert_bytes_si(value, 'B')
        else: # fallback to bytes as default
            return super().formatted(statvfs, dev_name, dir)


class DfFilesystem(DfColumn):

    def title(self):
        return 'Filesystem'

    def formatted(self, statvfs, dev_name, dir):
        return '{:s}@{:s}'.format(dir[:-1], dev_name)
        # format: /${dir_name}/@${device_name}
        # e.g. /flash@pyboard


class DfMountedOn(DfColumn):

    def title(self):
        return 'Mounted on'

    def formatted(self, statvfs, dev_name, dir):
        return '/{}{}'.format(dev_name, dir)[:-1]
        # format: /${device_name}/${dir_name}
        # e.g. /pyboard/flash


class DfNumBlocks(DfNumColumn):

    def title(self):
        return 'Blocks'

    def get_num_value(self, statvfs):
        return statvfs[2]
        # f_blocks


class DfBlockSize(DfNumColumn):

    def title(self):
        return 'Block size'

    def get_num_value(self, statvfs):
        return statvfs[1]
        # f_frsize


class DfUsedBlocks(DfNumColumn):

    def title(self):
        return 'Used'

    def get_num_value(self, statvfs):
        return statvfs[2] - statvfs[3]
        # f_blocks - f_used


class DfAvailBlocks(DfNumColumn):

    def title(self):
        return 'Available'

    def get_num_value(self, statvfs):
        return statvfs[4]
        # f_bavail


class DfCapacityBlocks(DfNumColumn):

    def __init__(self):
        super().__init__('{:.0f}%')

    def title(self):
        return 'Capacity'

    def get_num_value(self, statvfs):
        return 100 * (statvfs[2] - statvfs[3]) / statvfs[2] if statvfs[2] > 0 else 0
        # 100 * (f_blocks - f_used) / f_blocks
        #   or 0 if 0 blocks


class DfSizeBytes(DfByteColumn):

    def __init__(self, byte_format):
        super().__init__(byte_format)

    def title(self):
        return 'Size'

    def get_num_value(self, statvfs):
        return statvfs[1] * statvfs[2]
        # f_frsize * f_blocks


class DfUsedBytes(DfByteColumn):

    def __init__(self, byte_format):
        super().__init__(byte_format)

    def title(self):
        return 'Used'

    def get_num_value(self, statvfs):
        return statvfs[1] * (statvfs[2] - statvfs[3])
        # f_frsize * (f_blocks - f_used)


class DfAvailBytes(DfByteColumn):

    def __init__(self, byte_format):
        super().__init__(byte_format)

    def title(self):
        return 'Available'

    def get_num_value(self, statvfs):
        return statvfs[1] * statvfs[4]
        # f_frsize * f_bavail

class DfCapacityBytes(DfNumColumn):

    def __init__(self):
        super().__init__('{:.0f}%')

    def title(self):
        return 'Capacity'

    def get_num_value(self, statvfs):
        return 100 * (statvfs[2] - statvfs[3]) / statvfs[2] if statvfs[2] > 0 else 0
        # 100 * (f_blocks - f_used) / f_blocks
        #   or 0 if 0 blocks


def create_byte_sizes_columns(byte_format):
    """Returns standard set of columns for df command output
       in bytes in different formats
    """
    return [
        DfFilesystem(),
        DfSizeBytes(byte_format),
        DfUsedBytes(byte_format),
        DfAvailBytes(byte_format),
        DfCapacityBytes(),
        DfMountedOn(),
    ]


def create_block_sizes_columns():
    """Returns standard set of columns for df command output
       in blocks
    """
    return [
        DfFilesystem(),
        DfBlockSize(),
        DfNumBlocks(),
        DfUsedBlocks(),
        DfAvailBlocks(),
        DfCapacityBlocks(),
        DfMountedOn(),
    ]