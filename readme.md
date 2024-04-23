## Overview

TempoFS is a file system based on FUSE, casting files hosted over http(s) to local. It is suitable for e.g. setting up a ML training dataset or extract content from a large file on-the-fly without downloading the whole file.

## Requirements

```bash
sudo apt install libfuse3-dev pkgconf
pip install -r requirements.txt
# Or...
sudo apt install python3-pyfuse3
```

## Usage

In a YAML file, set the files and its url in the format of "filename: url" in each line. Subfolder is not supported, and all files are placed in the mounted directory.
Use an empty string as the filename to infer from URL.

```bash
mkdir mnt
python3 tempofs.py example.yaml mnt & # add `--debug` for debug info output
ls -lh mnt
# known issue: should `ls` the mounted root dir first to access its contents,
# since `LOOKUP` including subdirs has not be implemented yet.
tar -tf mnt/oc_all.tar # do some stuff
```

## Implements

> [`read`](https://man7.org/linux/man-pages/man2/read.2.html)`(int fd, void *buf, size_t count)` attempts to read up to `count` bytes from file descriptor `fd` into the buffer starting at `buf`. On files that support seeking, the read operation commences at the file offset, and the file offset is incremented by the number of bytes read.

This Linux system call has its counterpart in HTTP. For an HTTP file:

- Response header [`Accept-Ranges`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Accept-Ranges) determines if it supports partial requests, i.e. seeking;
- Request header [`Range`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Range) indicates the part of a document that the server should return;

Hence, it is possible to cast the operations on a file to the requests for a remote resource. Of course, the file is read-only.
