# Xctrace Trace Analysis

[中文说明](./README.zh-CN.md)

Analyze Apple Instruments `.trace` bundles with `xcrun xctrace export` and produce a compact summary for performance investigation.

This repository packages a reusable skill plus a Python script that exports the most important tables from a trace and writes a `*-trace-summary.json` file for review.

## What It Does

- Exports the trace table of contents
- Detects which schemas are actually available in the trace
- Exports the highest-value tables by default
- Produces a compact summary JSON with coverage and key findings
- Leaves larger raw tables as optional follow-up exports

## Repository Layout

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

## Files

- `SKILL.md`
  Skill instructions and workflow guidance
- `agents/openai.yaml`
  Skill metadata for compatible skill runners
- `scripts/analyze_trace.py`
  Main export and summary script

## Requirements

- macOS
- Xcode command line tools with `xcrun xctrace`
- Python 3
- An Instruments `.trace` bundle

## Basic Usage

Run the script directly:

```bash
python3 scripts/analyze_trace.py /path/to/file.trace
```

Write outputs to a custom directory:

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --output-dir /path/to/output
```

Include larger raw tables:

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --include-large-tables
```

Skip a table:

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --skip-table swiftui-causes
```

## Default Outputs

The script exports these files when the corresponding schemas exist in the trace:

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

Optional large outputs:

- `<basename>-swiftui-updates.xml`
- `<basename>-swiftui-full-causes.xml`
- `<basename>-time-sample.xml`

## Read Order

Read results in this order:

1. `*-trace-summary.json`
2. `coverage`
3. `potential_hangs`
4. `hitches`
5. `time_profile`
6. `runloop_events`
7. `swiftui_update_groups`
8. `swiftui_causes`
9. Supporting XML tables

## Summary Structure

The summary JSON includes:

- `trace`
  Recording metadata and discovered schemas
- `coverage`
  Requested tables, exported tables, and still-uncovered available tables
- `potential_hangs`
  Detected hangs and brief unresponsiveness
- `hitches`
  Hitch counts and largest hitch durations
- `time_profile`
  Hot threads and sampled backtraces
- `runloop_events`
  RunLoop activity and mode counts
- `swiftui_update_groups`
  Highest-cost SwiftUI update categories
- `swiftui_causes`
  Update propagation edges
- `table_summaries`
  Supporting summaries for hitch subtables and SwiftUI change tables

## Notes

- `xctrace export` writes XML, not JSON
- The summary JSON is intentionally compact and not a full lossless trace conversion
- In restricted environments, `xcrun xctrace export` may need broader permissions because Instruments CLI uses cache directories under `~/Library/Caches`

## License

This repository does not include a license file by default. Choose and add one before public release if you want to define reuse terms.
