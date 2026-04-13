# Copyright 2026 DingoDB, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression tests for O_APPEND and concurrent append writes.

pjdfstest covers basic O_APPEND POSIX semantics (single-fd).
These tests go further: multiple fds / threads appending concurrently
to the SAME file, then verifying no data loss and no interleaving
corruption. DingoFS's write path must atomically read current length
and append at the end.

Covers:
  - Single-fd O_APPEND basic correctness
  - Two fds O_APPEND to same file
  - Multi-thread concurrent O_APPEND with total length check
  - O_APPEND after truncate
"""

import hashlib
import os
import threading

import pytest

pytestmark = pytest.mark.standard

MB = 1024 * 1024


def md5(data):
    return hashlib.md5(data).hexdigest()


def test_append_basic(test_dir):
    """O_APPEND: each write goes to end of file."""
    path = os.path.join(test_dir, "append_basic")

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    os.write(fd, b"AAA")
    os.write(fd, b"BBB")
    os.write(fd, b"CC")
    os.close(fd)

    with open(path, "rb") as f:
        assert f.read() == b"AAABBBCC"


def test_append_two_fds(test_dir):
    """Two fds O_APPEND to the same file, interleaved writes."""
    path = os.path.join(test_dir, "append_two_fd")

    fd1 = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    fd2 = os.open(path, os.O_WRONLY | os.O_APPEND)

    os.write(fd1, b"1111")
    os.write(fd2, b"2222")
    os.write(fd1, b"3333")
    os.write(fd2, b"4444")

    os.close(fd1)
    os.close(fd2)

    with open(path, "rb") as f:
        data = f.read()

    # Total should be 16 bytes, no data lost
    assert len(data) == 16, f"expected 16 bytes, got {len(data)}"
    # Each 4-byte chunk should be intact (no partial interleaving)
    chunks = [data[i:i + 4] for i in range(0, 16, 4)]
    valid = {b"1111", b"2222", b"3333", b"4444"}
    for c in chunks:
        assert c in valid, f"corrupted chunk: {c!r}"


@pytest.mark.xfail(reason="DingoFS does not yet support atomic multi-fd O_APPEND; "
                    "POSIX requires seek-to-end+write to be atomic, but FUSE "
                    "kernel uses cached i_size causing concurrent appends to "
                    "overlap. Known limitation — needs per-inode write lock.")
def test_append_concurrent_threads(test_dir):
    """8 threads each append 1000 × 64-byte records. Total must match."""
    path = os.path.join(test_dir, "append_concurrent")
    open(path, "w").close()

    num_threads = 8
    writes_per_thread = 1000
    record_size = 64
    expected_total = num_threads * writes_per_thread * record_size

    errors = []

    def appender(thread_id):
        try:
            fd = os.open(path, os.O_WRONLY | os.O_APPEND)
            record = bytes([thread_id & 0xFF]) * record_size
            for _ in range(writes_per_thread):
                written = os.write(fd, record)
                if written != record_size:
                    errors.append(f"thread {thread_id}: short write {written}")
            os.close(fd)
        except Exception as e:
            errors.append(f"thread {thread_id}: {e}")

    threads = [threading.Thread(target=appender, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"append errors: {errors}"

    actual_size = os.path.getsize(path)
    assert actual_size == expected_total, (
        f"total size mismatch: expected {expected_total}, got {actual_size} "
        f"(lost {expected_total - actual_size} bytes)"
    )

    # Verify each 64-byte record is intact (same byte repeated)
    with open(path, "rb") as f:
        data = f.read()
    for i in range(0, len(data), record_size):
        record = data[i:i + record_size]
        if len(record) == record_size:
            assert record == bytes([record[0]]) * record_size, (
                f"corrupted record at offset {i}"
            )


def test_append_after_truncate(test_dir):
    """Write data, truncate to 0, then O_APPEND — should start from 0."""
    path = os.path.join(test_dir, "append_trunc")

    with open(path, "wb") as f:
        f.write(os.urandom(4096))

    os.truncate(path, 0)

    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    os.write(fd, b"AFTER")
    os.close(fd)

    with open(path, "rb") as f:
        data = f.read()

    assert data == b"AFTER", f"expected b'AFTER', got {data!r} (len={len(data)})"


def test_append_large_records(test_dir):
    """Append 100 × 100KB records, verify total size and md5."""
    path = os.path.join(test_dir, "append_large")
    open(path, "w").close()

    records = [os.urandom(100 * 1024) for _ in range(100)]

    fd = os.open(path, os.O_WRONLY | os.O_APPEND)
    for r in records:
        os.write(fd, r)
    os.close(fd)

    expected = b"".join(records)
    with open(path, "rb") as f:
        actual = f.read()

    assert len(actual) == len(expected)
    assert md5(actual) == md5(expected), "append large records md5 mismatch"
