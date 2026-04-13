# Copyright 2026 DingoDB. All rights reserved.

import os
import errno
import ctypes
import ctypes.util
import hashlib

import pytest

pytestmark = pytest.mark.standard

MB = 1024 * 1024

libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)

FALLOC_FL_KEEP_SIZE = 0x01
FALLOC_FL_PUNCH_HOLE = 0x02


def fallocate(fd, mode, offset, length):
    ret = libc.fallocate(fd, mode, ctypes.c_long(offset), ctypes.c_long(length))
    if ret != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err))


def md5(data):
    return hashlib.md5(data).hexdigest()


def _try_fallocate(fd, mode, offset, length):
    """Call fallocate; skip test if ENOTSUP/EOPNOTSUPP."""
    try:
        fallocate(fd, mode, offset, length)
    except OSError as e:
        if e.errno in (errno.ENOTSUP, errno.EOPNOTSUPP):
            pytest.skip(f"fallocate not supported (errno={e.errno})")
        raise


def test_fallocate_basic(test_dir):
    """fallocate(0, 0, 10MB) should set file size to 10MB."""
    path = os.path.join(test_dir, "fa_basic")
    fd = os.open(path, os.O_CREAT | os.O_WRONLY)
    try:
        _try_fallocate(fd, 0, 0, 10 * MB)
    finally:
        os.close(fd)

    assert os.path.getsize(path) == 10 * MB


def test_fallocate_extend(test_dir):
    """Extend from 10MB to 20MB via fallocate."""
    path = os.path.join(test_dir, "fa_extend")
    # Create 10MB file
    with open(path, "wb") as f:
        f.write(os.urandom(10 * MB))
    assert os.path.getsize(path) == 10 * MB

    fd = os.open(path, os.O_WRONLY)
    try:
        _try_fallocate(fd, 0, 10 * MB, 10 * MB)
    finally:
        os.close(fd)

    assert os.path.getsize(path) == 20 * MB


def test_fallocate_keep_size(test_dir):
    """fallocate with KEEP_SIZE should not change file size."""
    path = os.path.join(test_dir, "fa_keepsize")
    with open(path, "wb") as f:
        f.write(os.urandom(20 * MB))
    assert os.path.getsize(path) == 20 * MB

    fd = os.open(path, os.O_WRONLY)
    try:
        _try_fallocate(fd, FALLOC_FL_KEEP_SIZE, 20 * MB, 10 * MB)
    finally:
        os.close(fd)

    assert os.path.getsize(path) == 20 * MB


def test_fallocate_punch_hole(test_dir):
    """Punch a 3MB hole at 5MB; reading [6MB, 7MB) should return all zeros."""
    path = os.path.join(test_dir, "fa_punch")
    data = os.urandom(10 * MB)
    with open(path, "wb") as f:
        f.write(data)

    fd = os.open(path, os.O_WRONLY)
    try:
        _try_fallocate(fd, FALLOC_FL_PUNCH_HOLE | FALLOC_FL_KEEP_SIZE,
                        5 * MB, 3 * MB)
    finally:
        os.close(fd)

    # Read the punched region [6MB, 7MB)
    with open(path, "rb") as f:
        f.seek(6 * MB)
        chunk = f.read(1 * MB)

    assert chunk == b"\x00" * (1 * MB), "punched region should be all zeros"


def test_fallocate_not_supported_skip(test_dir):
    """If fallocate returns ENOTSUP, the test should be skipped."""
    path = os.path.join(test_dir, "fa_notsup")
    fd = os.open(path, os.O_CREAT | os.O_WRONLY)
    try:
        _try_fallocate(fd, 0, 0, 1 * MB)
    finally:
        os.close(fd)
    # If we get here, fallocate is supported -- that is fine, test passes.
