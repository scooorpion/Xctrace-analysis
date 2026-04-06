# Xctrace Trace Analysis

[English](./README.md)

这个仓库用于分析 Apple Instruments 的 `.trace` 包。它通过 `xcrun xctrace export` 导出关键表，并生成一个紧凑的 `*-trace-summary.json`，方便后续查看和自动化分析。

## 这个仓库做什么

- 导出 trace 的目录信息
- 自动识别 trace 里实际存在的 schema
- 默认导出最重要的一批性能分析表
- 生成一个覆盖面清晰的摘要 JSON
- 把体积很大的原始表保留为按需导出

## 仓库结构

```text
xctrace-trace-analysis-github/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── agents/
│   └── openai.yaml
└── scripts/
    └── analyze_trace.py
```

## 文件说明

- `SKILL.md`
  Skill 的主说明文件，定义工作流、默认覆盖范围和输出解释
- `agents/openai.yaml`
  Skill 元数据文件，供兼容的 skill 运行器读取
- `scripts/analyze_trace.py`
  实际执行导出和摘要生成的主脚本

## 运行要求

- macOS
- 已安装可用的 `xcrun xctrace`
- Python 3
- 一个 Instruments 生成的 `.trace` 目录

## 基本用法

直接运行：

```bash
python3 scripts/analyze_trace.py /path/to/file.trace
```

指定输出目录：

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --output-dir /path/to/output
```

导出更大的原始表：

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --include-large-tables
```

跳过某张表：

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --skip-table swiftui-causes
```

## 默认输出文件

当 trace 中存在对应 schema 时，脚本会输出这些文件：

- `<basename>-toc.xml`
- `<basename>-potential-hangs.xml`
- `<basename>-hitches.xml`
- `<basename>-hang-risks.xml`
- `<basename>-swiftui-changes.xml`
- `<basename>-swiftui-update-groups.xml`
- `<basename>-swiftui-causes.xml`
- `<basename>-time-profile.xml`
- `<basename>-runloop-events.xml`
- `<basename>-hitches-renders.xml`
- `<basename>-hitches-gpu.xml`
- `<basename>-hitches-updates.xml`
- `<basename>-hitches-frame-lifetimes.xml`
- `<basename>-hitches-framewait.xml`
- `<basename>-trace-summary.json`

可选的大文件：

- `<basename>-swiftui-updates.xml`
- `<basename>-swiftui-full-causes.xml`
- `<basename>-time-sample.xml`

## 推荐阅读顺序

建议按这个顺序看结果：

1. `*-trace-summary.json`
2. `coverage`
3. `potential_hangs`
4. `hitches`
5. `time_profile`
6. `runloop_events`
7. `swiftui_update_groups`
8. `swiftui_causes`
9. 需要时再回头看 XML 原始表

## 摘要 JSON 包含什么

- `trace`
  录制元信息和 trace 中发现的 schema
- `coverage`
  本次尝试覆盖了哪些表、真正导出了哪些表、还有哪些表没覆盖
- `potential_hangs`
  hang 和 brief unresponsiveness 事件
- `hitches`
  卡顿统计和最长卡顿
- `time_profile`
  热线程和热点采样回溯
- `runloop_events`
  RunLoop 活动和 mode 统计
- `swiftui_update_groups`
  最耗时的 SwiftUI 更新类别
- `swiftui_causes`
  SwiftUI 更新传播链路
- `table_summaries`
  其它支持性表的概要统计

## 说明

- `xctrace export` 原生输出是 XML，不是 JSON
- 这个工具生成的摘要 JSON 不是完整无损转换，而是用于分析的紧凑摘要
- 在受限环境里，`xcrun xctrace export` 可能需要更高权限，因为 Instruments CLI 会使用 `~/Library/Caches` 下的缓存目录

## License

MIT
