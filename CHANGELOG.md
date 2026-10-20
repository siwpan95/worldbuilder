# Changelog

本项目所有值得注意的变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-20（重建同名发行版）

> 说明：原 `v1.0.0`（2026-08-27，包名 `procgen`）已连同 Gitee release 一并删除重建，
> 以避免"包名 procgen / 包名 worldbuilder"两种身份共用同一版本号而互相矛盾。

### Changed

- **发行名与导入名 `procgen` → `worldbuilder`**（包目录 `procgen/` → `worldbuilder/`，示例别名 `pg` → `wb`）。
  原因：PyPI 上 `procgen` 已被 OpenAI 的 Procgen Benchmark 占用，与本库无关。
- Gitee 仓库路径保持不变（`siwpan/procgen`），**包名一律以 PyPI 为准**。

### Added

- 首次发布到 PyPI：`pip install worldbuilder`（sdist + wheel）。
- 打包元数据补全：作者、MIT 许可、keywords、classifiers、依赖声明。
- 依赖：仅 `numpy>=1.24.0`；CLI 绘图为可选 `Pillow`（`pip install worldbuilder[cli]`）。

### 已作废

- 原 `## [1.0.0] - 2026-08-27`（旧包名 `procgen` 的首个 Gitee 发行版）已删除重建。
