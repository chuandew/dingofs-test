# Copyright 2024 DingoFS Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license.

import os
import shutil
import uuid

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--mount-point", required=True, help="FUSE mount point path"
    )


@pytest.fixture(scope="session")
def mount_point(request):
    mp = request.config.getoption("--mount-point")
    assert os.path.isdir(mp), f"{mp} is not a directory"
    return mp


@pytest.fixture
def test_dir(mount_point):
    d = os.path.join(mount_point, f"test_{uuid.uuid4().hex[:8]}")
    os.makedirs(d)
    yield d
    shutil.rmtree(d, ignore_errors=True)
