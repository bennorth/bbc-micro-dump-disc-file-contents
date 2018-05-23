# This script, written Ben North 2018, is hereby placed into
# the public domain.
#
# https://github.com/bennorth/bbc-micro-dump-disc-file-contents
#
"""
Setup:

pip install pyserial
pip install attrs
"""

import serial
import attr
import json
from functools import reduce
from operator import concat


@attr.s
class DumpFragment:
    offset = attr.ib()
    data = attr.ib()

    @classmethod
    def from_dump_line(cls, line):
        offset = int(line[:6], 16)
        raw_hex_pieces = [line[7:30][i:i+2] for i in range(0, 23, 3)]
        data = [int(p, 16) for p in raw_hex_pieces if p != '  ']
        # For extra reassurance, could verify against ASCII dump here.
        return cls(offset, data)


@attr.s
class FileInfo:
    name = attr.ib()
    size = attr.ib()

    @classmethod
    def from_info_line(cls, line):
        pieces = line.split(' ')
        name = pieces[0]
        size_hex = pieces[-2]
        size = int(size_hex, 16)
        return cls(name, size)


@attr.s
class DiskFile:
    info = attr.ib()
    data = attr.ib()

    @classmethod
    def from_info_and_fragments(cls, info, fragments):
        exp_offsets = [i * 8 for i in range(len(fragments))]
        got_offsets = [frag.offset for frag in fragments]
        assert got_offsets == exp_offsets

        file_data = reduce(concat, (frag.data for frag in fragments), [])
        assert len(file_data) == info.size

        return cls(info, file_data)

    def as_dict(self):
        return {'name': self.info.name,
                'size': self.info.size,
                'data': list(self.data)}


class BBCController:
    def __init__(self):
        self.port = serial.Serial('/dev/ttyUSB0',
                                  baudrate=9600,
                                  bytesize=serial.SEVENBITS,
                                  parity=serial.PARITY_EVEN,
                                  stopbits=serial.STOPBITS_ONE,
                                  timeout=3.0)

    def do_raw(self, cmd):
        self.port.write(cmd.encode())
        self.port.write(b'\r')

        read_chars = []
        while True:
            next_char = self.port.read(1)
            if len(next_char) == 0:
                break
            read_chars.append(next_char)
        response = b''.join(read_chars)

        assert response[-1] == ord('>')
        return response.decode()

    def disc_listing(self):
        raw_info = self.do_raw('*INFO *.*')
        raw_lines = raw_info.split('\n\r')
        assert raw_lines[0] == '*INFO *.*'
        assert raw_lines[-1] == '>'
        info_lines = raw_lines[1:-1]
        return [FileInfo.from_info_line(line) for line in info_lines]

    def file_dump(self, file_info):
        cmd = f'*DUMP {file_info.name}'
        raw_dump = self.do_raw(cmd)

        raw_lines = raw_dump.split('\n\r')
        assert raw_lines[0] == cmd
        assert raw_lines[-1] == '>'

        content_lines = raw_lines[1:-1]
        fragments = [DumpFragment.from_dump_line(line) for line in content_lines]

        print(f'dumped {file_info.name}')
        return DiskFile.from_info_and_fragments(file_info, fragments)

    def dump_whole_disc(self, fname, drive=0, skip_files=[]):
        ignored = self.do_raw(f'*DRIVE {drive}')
        file_infos = self.disc_listing()
        for i in file_infos:
            print(f'{i.name}  {i.size}')
        all_dumps = [self.file_dump(info) for info in file_infos
                     if info.name not in skip_files]
        with open(fname, 'w') as f_out:
            json.dump([d.as_dict() for d in all_dumps], f_out)


"""
Example usage:

bbc = BBCController()
bbc.dump_whole_disc('disc-16-0.json', 0)
bbc.dump_whole_disc('disc-16-2.json', 2, ['BADFILE1', 'BADFILE2'])
"""
