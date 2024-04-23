#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""This program implements a static file system from a http file."""

import errno
import logging
import os
import stat
from argparse import ArgumentParser
from email.utils import parsedate_to_datetime

import pyfuse3
import requests
import trio
import yaml


class webfile:
    def __init__(self, inode, name, url) -> None:
        self.inode = inode
        self.name = name # TODO: get name by Content-Disposition
        self.url = url
        self.session = requests.Session()

    async def getattr(self) -> pyfuse3.EntryAttributes:
        entry = pyfuse3.EntryAttributes()
        entry.st_ino = self.inode
        r = self.session.head(self.url)
        entry.st_mode = stat.S_IFREG | 0o444
        try:
            last_modified = (
                parsedate_to_datetime(r.headers["Last-Modified"]).timestamp() * 1e9
            )
        except KeyError:
            last_modified = 0
        entry.st_ctime_ns = last_modified
        entry.st_atime_ns = last_modified
        entry.st_mtime_ns = last_modified
        entry.st_size = int(r.headers.get("Content-Length", 0))
        return entry

    async def getfileinfo(self) -> pyfuse3.FileInfo:
        r = self.session.head(self.url)
        nonseekable = r.headers.get("Accept-Ranges", True)
        if nonseekable == "bytes":
            nonseekable = False
        else:
            if nonseekable not in ["none", "false", "False", "0", "no", "No"]:
                logging.warning("Unknown Accept-Ranges value: %s", nonseekable)
            nonseekable = True
        if nonseekable:
            logging.warning(f"File {self.name} is nonseekable")
        return pyfuse3.FileInfo(fh=self.inode, keep_cache=True, nonseekable=nonseekable)

    async def open(self):
        pass

    async def read(self, off, size) -> bytes:
        return self.session.get(
            self.url, headers={"Range": "bytes=%d-%d" % (off, off + size - 1)}
        ).content


class tempofs(pyfuse3.Operations):
    def __init__(self, config_path):
        super().__init__()

        # construct the file system from the config file
        with open(config_path, "r") as f:
            config: dict = yaml.load(f, Loader=yaml.FullLoader)
        self.files = []
        for name, url in config.items():
            inode = pyfuse3.ROOT_INODE + 1 + len(self.files)
            self.files.append(webfile(inode, name, url))

    def find(self, inode):
        for file in self.files:
            if file.inode == inode:
                return file
        raise IndexError

    async def getattr(self, inode, ctx=None):
        entry = pyfuse3.EntryAttributes()
        if inode == pyfuse3.ROOT_INODE:
            entry.st_mode = stat.S_IFDIR | 0o755
            entry.st_size = 0
            entry.st_gid = os.getgid()
            entry.st_uid = os.getuid()
            entry.st_ino = inode
            return entry
        else:
            for file in self.files:
                if file.inode == inode:
                    entry = await file.getattr()
                    entry.st_gid = os.getgid()
                    entry.st_uid = os.getuid()
                    entry.st_ino = inode
                    return entry
        raise pyfuse3.FUSEError(errno.ENOENT)

    async def lookup(self, parent_inode, name, ctx=None):
        if parent_inode != pyfuse3.ROOT_INODE:
            raise pyfuse3.FUSEError(errno.ENOENT)
        for file in self.files:
            if file.name == name:
                return file.getattr()
        raise pyfuse3.FUSEError(errno.ENOENT)

    async def opendir(self, inode, ctx):
        if inode != pyfuse3.ROOT_INODE:
            raise pyfuse3.FUSEError(errno.ENOENT)
        return inode

    async def readdir(self, fh, start_id, token):
        assert fh == pyfuse3.ROOT_INODE
        try:
            file = self.files[start_id]
            pyfuse3.readdir_reply(
                token,
                bytes(file.name, encoding="ascii"),
                await file.getattr(),
                start_id + 1,
            )
            return
        except IndexError:
            raise pyfuse3.FUSEError(errno.ENOENT)

    async def open(self, inode, flags, ctx) -> pyfuse3.FileInfo:
        if (
            flags & os.O_APPEND
            or flags & os.O_TRUNC
            or flags & os.O_RDWR
            or flags & os.O_WRONLY
        ):
            logging.warning("Only read is supported: %s", flags)
            raise pyfuse3.FUSEError(errno.EACCES)
        try:
            return await self.find(inode).getfileinfo()
        except IndexError:
            raise pyfuse3.FUSEError(errno.ENOENT)

    async def read(self, fh, off, size):
        logging.debug("read(%d, %d, %d)", fh, off, size)
        return await self.find(fh).read(off, size)


def init_logging(debug=False):
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d %(threadName)s: " "[%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    if debug:
        handler.setLevel(logging.DEBUG)
        root_logger.setLevel(logging.DEBUG)
    else:
        handler.setLevel(logging.INFO)
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        "config", type=str, help="the map file of the file system",
    )
    parser.add_argument("mountpoint", type=str, help="Where to mount the file system")
    parser.add_argument(
        "--debug", action="store_true", default=False, help="Enable debugging output"
    )

    return parser.parse_args()


def main():
    options = parse_args()
    init_logging(options.debug)

    testfs = tempofs(options.config)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add("fsname=tempofs")

    if options.debug:
        fuse_options.add("debug")
    pyfuse3.init(testfs, options.mountpoint, fuse_options)
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)


if __name__ == "__main__":
    main()
