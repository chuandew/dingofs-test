# DingoFS Integration Tests

DingoFS 文件系统级集成测试。唯一输入是 FUSE 挂载点路径，不关心底层实现——可以在 DingoFS / JuiceFS / ext4 上运行。

## 目录结构

```
dingofs-test/
├── conftest.py              # 共享 fixture（--mount-point, test_dir）
├── functional/              # 通用 POSIX 功能测试（33 个，可被 pjdfstest 替代）
│   └── test_*.py
├── regression/              # DingoFS 专有测试（83 个，永久保留）
│   ├── test_regression_*.py     # Bug 回归测试
│   ├── test_*.py                # DingoFS 特有路径测试
│   └── ...
├── pyproject.toml
├── pytest.ini
└── README.md
```

## functional/ — 通用 POSIX（33 个测试）

纯 POSIX 语义验证，pjdfstest 集成后可替代。

| 文件 | 用例 | 级别 | 内容 |
|------|------|------|------|
| `test_basic_io.py` | 5 | smoke | create / read / write / delete / stat |
| `test_directory.py` | 6 | smoke | mkdir / rmdir / readdir / 嵌套 / 递归删除 |
| `test_metadata.py` | 6 | smoke | chmod / chown / utime / stat type / unlink |
| `test_links.py` | 4 | smoke | hardlink nlink / symlink / readlink / 悬空 |
| `test_rename.py` | 3 | smoke | 同目录 / 跨目录 / 目录 rename |
| `test_truncate.py` | 4 | standard | shrink / grow / 零填充 / truncate-to-zero |
| `test_xattr.py` | 4 | standard | set / get / list / remove |
| `test_concurrent.py` | 1 | standard | 8 线程写不同文件 md5 |

## regression/ — DingoFS 专有（83 个测试）

DingoFS 实现相关的 Bug 回归 + 边界测试，标准工具无法替代。

### Bug 回归（每个文件头注释含 fix commit + 验证方式）

| 文件 | 用例 | 对应 commit | Bug |
|------|------|-------------|-----|
| `test_regression_multi_fd.py` | 4 | `645895eb8` | 多 fd 写后读不一致 |
| `test_regression_concurrent_flush.py` | 3 | `e2fe490db` | write/flush 并发数据错乱 |
| `test_regression_read_correctness.py` | 5 | `d4460570f` | 读数据不正确（fuse_reply 路径）|
| `test_regression_truncate_shrink_grow.py` | 3 | `924688abe` | truncate 缩-扩旧数据复活 |
| `test_regression_overwrite_otrunc.py` | 4 | `e5cf76916` | O_TRUNC 覆盖写竞态（last_write_length_ 未重置）|
| `test_regression_hardlink_multi_fd.py` | 4 | — | hardlink 跨路径多 fd 一致性 |
| `test_regression_rename_overwrite.py` | 5 | — | rename 覆盖 inode 清理 |
| `test_readdir_backward.py` | 6 | `7a9d0ad9c` | seekdir 回退崩溃 |
| `test_regression_append_concurrent.py` | 5 | — | O_APPEND 并发丢数据（xfail，已知限制）|

### DingoFS 特有路径测试（标准工具覆盖不了）

| 文件 | 用例 | 测试点 |
|------|------|--------|
| `test_regression_chunk_boundary_write.py` | 8 | 64MB chunk 边界 + 4MB block 边界写入 |
| `test_large_file.py` | 8 | 1B~130MB md5 往返（跨 chunk）|
| `test_seek_read.py` | 12 | chunk 边界两侧 seek 读（skip=63M/64M/65M）|
| `test_regression_sparse_chunk_boundary.py` | 4 | 稀疏文件跨 chunk hole/data |
| `test_sparse_file.py` | 1 | 100MB 稀疏 + 三段 patch |
| `test_regression_fragmented_writes.py` | 4 | 碎片化小写入（1B pwrite × 200）|
| `test_fallocate.py` | 5 | Fallocate allocate/keep-size/punch-hole |
| `test_statfs.py` | 2 | quota 追踪正确性 |

### 已知限制（xfail 标记）

| 测试 | 限制 | 优先级 |
|------|------|--------|
| `test_append_concurrent_threads` | 并发 O_APPEND 不保证原子性（FUSE 缓存 i_size 导致 offset 重叠）| P2 |
| `test_fallocate_*`（MDS 模式）| MDS 端 Fallocate 未实现，全部 SKIP | P1 |

## 测试分级

| 级别 | 标记 | 耗时 | 何时跑 |
|------|------|------|--------|
| **smoke** | `-m smoke` | < 30s | 每次 PR |
| **standard** | `-m standard` | < 3 min | 合并后 / nightly |
| **全量** | 无标记 | < 1 min (ext4) / < 1 min (MDS) | 定时 / 手动 |

## 快速开始

### 前置条件

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 运行

```bash
# ext4 上验证测试本身
uv run pytest --mount-point=/tmp/test-ext4

# DingoFS 上跑全量
uv run pytest --mount-point=/mnt/dingofs

# 只跑 functional
uv run pytest functional/ --mount-point=/mnt/dingofs

# 只跑 regression
uv run pytest regression/ --mount-point=/mnt/dingofs

# 只跑 smoke
uv run pytest --mount-point=/mnt/dingofs -m smoke
```

> `uv run` 会自动创建虚拟环境并安装依赖，无需手动操作。

## 设计原则

1. **唯一输入是挂载点**：`--mount-point=/mnt/dingofs`，测试不感知部署细节
2. **每个测试独立**：`test_dir` fixture 在挂载点下创建 `test_<uuid>` 子目录，自动清理
3. **ext4 先验证**：开发时先在本地跑通，确认测试本身没 bug
4. **functional 可替代**：通用 POSIX 部分后续引入 pjdfstest 替代
5. **regression 永久保留**：DingoFS 专有路径和 Bug 回归，不可替代

## 添加新测试

### 通用 POSIX 测试 → `functional/`

```python
# functional/test_new.py
import os, pytest
pytestmark = pytest.mark.smoke

def test_something(test_dir):
    path = os.path.join(test_dir, "file")
    with open(path, "wb") as f:
        f.write(b"hello")
    with open(path, "rb") as f:
        assert f.read() == b"hello"
```

### DingoFS 专有测试 → `regression/`

```python
# regression/test_regression_new_bug.py
"""Regression test for <bug description>.

Bug: <what went wrong>
Fix: commit <hash> — <what was changed>
Files changed: <list>

Verification:
  buggy binary (pre <hash>): <which test> should FAIL
  fixed binary (post <hash>): all tests PASS
  works on: <local / MDS / both>
"""
import os, pytest
pytestmark = pytest.mark.standard

def test_the_bug(test_dir):
    ...
```

## 已发现的 Bug

通过本测试项目发现并修复的 DingoFS Bug：

| Bug | 发现测试 | 状态 |
|-----|----------|------|
| truncate shrink-grow 旧数据复活 | `test_regression_truncate_shrink_grow` | 已修复 |
| O_TRUNC 覆盖写竞态（last_write_length_） | `test_regression_overwrite_otrunc` | 已修复 |
| 并发 O_APPEND 数据丢失 | `test_regression_append_concurrent` | 待定（P2）|

## 后续计划

- [ ] 集成 pjdfstest（~8800 条 POSIX 合规测试）替代 functional/
- [ ] 集成 hypothesis 随机文件操作测试
- [ ] CI workflow（GitHub Actions self-hosted runner）
- [ ] fsync + unmount/remount 持久化测试
- [ ] 多挂载点并发测试
