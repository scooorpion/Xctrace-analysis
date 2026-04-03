---
name: xctrace-trace-analysis
description: "Analyze Xcode Instruments `.trace` bundles with `xcrun xctrace export`. Use this skill to unpack a `.trace` file, export the most important performance tables by default, and generate one `*-trace-summary.json` file that records coverage, exported tables, unexported tables, hangs, hitches, SwiftUI update groups, SwiftUI cause edges, time-profile hotspots, runloop activity, and hitch subtable summaries."
---

# Xctrace Trace Analysis

Use `scripts/analyze_trace.py` for the standard workflow. It exports the trace TOC first, detects which schemas actually exist, exports the important tables that are available, and writes one compact JSON summary for automated review or further analysis.

## Workflow

1. Locate the `.trace` bundle and confirm the output directory.
2. Run the analyzer script on the trace.
3. Read the generated `*-trace-summary.json` first.
4. Check the `coverage` section before drawing conclusions.
5. Inspect exported XML tables only when the summary is not enough.
6. Export the largest raw tables only when the user explicitly wants full detail.

## Standard Command

```bash
python3 scripts/analyze_trace.py /path/to/file.trace
```

Common options:

```bash
python3 scripts/analyze_trace.py /path/to/file.trace --output-dir /path/to/output
python3 scripts/analyze_trace.py /path/to/file.trace --include-large-tables
python3 scripts/analyze_trace.py /path/to/file.trace --skip-table swiftui-causes
```

Default outputs:

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

Large optional outputs:

- `<basename>-swiftui-updates.xml`
- `<basename>-swiftui-full-causes.xml`
- `<basename>-time-sample.xml`

## Output Files

Read these files by role, not by creation order:

- `<basename>-trace-summary.json`
  Main result. Read this first. It contains:
  `trace` metadata, `coverage` of what was and was not exported, and parsed summaries for the most important tables.
- `<basename>-toc.xml`
  Trace table of contents. It records run metadata, device/process info, and which table schemas exist in the trace.
- `<basename>-potential-hangs.xml`
  Small event table for detected hangs or brief unresponsiveness. Use it to confirm whether the main thread actually stalled.
- `<basename>-hitches.xml`
  Frame hitch table. Use it to see whether the trace shows expensive app updates, GPU work, or display stutters.
- `<basename>-hang-risks.xml`
  Risk/fault-style events. This table is often empty. If it has rows, they can provide stronger direct evidence than hitches.
- `<basename>-time-profile.xml`
  Statistical CPU sample table. Use it to identify heavy threads and the hottest sampled backtraces.
- `<basename>-runloop-events.xml`
  RunLoop activity table. Use it to understand main-thread and worker-thread runloop patterns during the trace.
- `<basename>-swiftui-update-groups.xml`
  Aggregated SwiftUI update groups. Use it to find which categories of SwiftUI work consume the most time.
- `<basename>-swiftui-causes.xml`
  SwiftUI cause graph edges. Use it to see how updates propagate from one node category to another.
- `<basename>-swiftui-changes.xml`
  Additional SwiftUI change data. The summary treats this as a supporting table and records its row counts and top durations.
- `<basename>-hitches-renders.xml`
  Hitch subtable focused on render cost.
- `<basename>-hitches-gpu.xml`
  Hitch subtable focused on GPU cost.
- `<basename>-hitches-updates.xml`
  Hitch subtable focused on app update cost.
- `<basename>-hitches-frame-lifetimes.xml`
  Hitch subtable focused on frame lifetime behavior.
- `<basename>-hitches-framewait.xml`
  Hitch subtable focused on frame wait behavior.
- `<basename>-swiftui-updates.xml`
  Full raw SwiftUI update event stream. Usually very large. Export only when the user explicitly wants the raw detail.
- `<basename>-swiftui-full-causes.xml`
  Expanded SwiftUI cause graph details. Also very large. Export only when the default summary and focused tables are not enough.
- `<basename>-time-sample.xml`
  Raw time samples. Export only when `time-profile` is insufficient and the user wants raw per-sample detail.

## Coverage Model

Treat `*-trace-summary.json` as a coverage report, not just a result blob.

- `coverage.available_tables`
  Every schema discovered in the trace TOC.
- `coverage.requested_tables`
  The tables this skill attempted to cover by default.
- `coverage.exported_tables`
  The tables that were actually exported.
- `coverage.unavailable_requested_tables`
  Requested tables that do not exist in this trace.
- `coverage.unexported_available_tables`
  Schemas present in the trace but not exported by the current run.
- `coverage.important_unexported_available_tables`
  Large but important raw tables still available if the summary is not enough.

## Interpretation Order

Read the summary in this order:

1. `coverage`
2. `potential_hangs`
3. `hitches`
4. `time_profile`
5. `runloop_events`
6. `swiftui_update_groups`
7. `swiftui_causes`
8. `table_summaries`
9. Raw XML tables

Interpretation heuristics:

- Treat repeated `Potentially expensive app update(s)` hitches as a strong sign of excessive SwiftUI invalidation or layout churn.
- Treat `hang-risks` being empty as normal. Many useful traces still have zero rows there.
- Use `time_profile.top_main_thread_backtraces` to move from “the UI is heavy” to “these sampled stacks are hot.”
- Use `runloop_events.main_thread_mode_counts` when the issue looks like wakeups, mode churn, or long main-thread loop work.
- If the hottest cause edges are `View Creation / Reuse`, layout nodes, and display list nodes, prefer a SwiftUI update propagation explanation over a single business-method explanation.
- If `swiftui-updates` or `swiftui-full-causes` are not explicitly needed, do not export them by default. They can easily become hundreds of MB or more than 1 GB.

## Operational Notes

- `xctrace export` writes XML, not JSON. The skill converts selected exports into a compact summary JSON instead of attempting a naive one-to-one XML to JSON conversion for every table.
- In restricted execution environments, `xcrun xctrace export` may need unsandboxed access because Instruments CLI touches cache directories under `~/Library/Caches`. If the command fails with cache or permission errors, rerun with broader permissions.
- Keep artifacts next to the trace or in a user-specified output directory. Do not default to `/tmp` unless there is a reason.

## Resources

### scripts/

- `analyze_trace.py`: Export the high-signal tables from a `.trace` bundle and build a JSON summary.
