#!/usr/bin/env python3

import argparse
import json
import shlex
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path


DEFAULT_TABLES = [
    "potential-hangs",
    "hitches",
    "hang-risks",
    "swiftui-update-groups",
    "swiftui-causes",
    "swiftui-changes",
    "time-profile",
    "runloop-events",
    "hitches-renders",
    "hitches-gpu",
    "hitches-updates",
    "hitches-frame-lifetimes",
    "hitches-framewait",
]

LARGE_TABLES = [
    "swiftui-updates",
    "swiftui-full-causes",
    "time-sample",
]

IMPORTANT_OPTIONAL_TABLES = [
    "swiftui-updates",
    "swiftui-full-causes",
    "time-sample",
]

DEFAULT_EXPORT_RETRIES = 2
RETRY_DELAY_SECONDS = 1.0


class XctraceExportError(RuntimeError):
    def __init__(
        self,
        *,
        command: list[str],
        output_path: Path,
        table: str | None,
        returncode: int,
        stdout: str,
        stderr: str,
        attempts: int,
    ) -> None:
        self.command = command
        self.output_path = output_path
        self.table = table
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.attempts = attempts
        super().__init__(self.describe())

    def describe(self) -> str:
        scope = self.table or "toc"
        lines = [
            f"xctrace export failed for {scope} after {self.attempts} attempt(s) with exit code {self.returncode}",
            f"command: {shlex.join(self.command)}",
            f"output: {self.output_path}",
        ]
        stderr = self.stderr.strip()
        stdout = self.stdout.strip()
        if stderr:
            lines.append(f"stderr:\n{stderr}")
        elif stdout:
            lines.append(f"stdout:\n{stdout}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, object]:
        return {
            "table": self.table,
            "returncode": self.returncode,
            "attempts": self.attempts,
            "output": str(self.output_path),
            "command": self.command,
            "stdout": self.stdout.strip(),
            "stderr": self.stderr.strip(),
        }


class Resolver:
    def __init__(self) -> None:
        self.fmt: dict[str, str] = {}
        self.text: dict[str, str] = {}

    def observe(self, elem: ET.Element) -> None:
        elem_id = elem.get("id")
        if not elem_id:
            return
        elem_fmt = elem.get("fmt")
        if elem_fmt is not None:
            self.fmt[elem_id] = elem_fmt
        elem_text = (elem.text or "").strip()
        if elem_text:
            self.text[elem_id] = elem_text

    def value(self, elem: ET.Element) -> str | None:
        ref = elem.get("ref")
        if ref:
            return self.fmt.get(ref) or self.text.get(ref)
        return elem.get("fmt") or ((elem.text or "").strip() or None)

    def raw_text(self, elem: ET.Element, default: str = "0") -> str:
        ref = elem.get("ref")
        if ref:
            return self.text.get(ref, default)
        text = (elem.text or "").strip()
        return text or default


def cleanup_partial_export(output_path: Path) -> None:
    try:
        output_path.unlink(missing_ok=True)
    except OSError:
        pass


def run_xctrace_export(
    trace_path: Path,
    output_path: Path,
    xpath: str | None = None,
    *,
    table: str | None = None,
    retries: int = DEFAULT_EXPORT_RETRIES,
) -> None:
    command = ["xcrun", "xctrace", "export", "--input", str(trace_path), "--output", str(output_path)]
    if xpath is None:
        command.append("--toc")
    else:
        command.extend(["--xpath", xpath])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    max_attempts = max(1, retries + 1)
    last_error: XctraceExportError | None = None

    for attempt in range(1, max_attempts + 1):
        cleanup_partial_export(output_path)
        result = subprocess.run(command, capture_output=True, text=True)
        output_exists = output_path.exists()
        output_empty = output_exists and output_path.stat().st_size == 0

        if result.returncode == 0 and output_exists and not output_empty:
            return

        stderr = result.stderr or ""
        if result.returncode == 0 and output_empty:
            if stderr:
                stderr += "\n"
            stderr += "xctrace reported success but produced an empty export file."

        last_error = XctraceExportError(
            command=command,
            output_path=output_path,
            table=table,
            returncode=result.returncode,
            stdout=result.stdout or "",
            stderr=stderr,
            attempts=attempt,
        )
        cleanup_partial_export(output_path)

        if attempt < max_attempts:
            time.sleep(RETRY_DELAY_SECONDS * attempt)

    if last_error is not None:
        raise last_error

    raise RuntimeError("unreachable")


def export_tables(
    trace_path: Path,
    output_dir: Path,
    base_name: str,
    tables: list[str],
    available_tables: set[str],
    *,
    retries: int,
) -> tuple[dict[str, Path], list[dict[str, object]]]:
    outputs: dict[str, Path] = {}
    failures: list[dict[str, object]] = []

    for table in tables:
        if table not in available_tables:
            continue
        out_path = output_dir / f"{base_name}-{table}.xml"
        xpath = f'/trace-toc/run[@number="1"]/data/table[@schema="{table}"]'
        try:
            run_xctrace_export(trace_path, out_path, xpath=xpath, table=table, retries=retries)
        except XctraceExportError as exc:
            print(exc.describe(), file=sys.stderr)
            failures.append(exc.to_dict())
            continue
        outputs[table] = out_path

    return outputs, failures


def parse_trace_info(toc_path: Path) -> dict:
    tree = ET.parse(toc_path)
    run = tree.find("./run")
    if run is None:
        return {}

    device = run.find("./info/target/device")
    host_device = run.find("./info/target/host-device")
    process = run.find("./info/target/process")
    summary = run.find("./info/summary")

    summary_map: dict[str, str] = {}
    if summary is not None:
        for child in summary:
            if child.tag == "intruments-recording-settings":
                continue
            summary_map[child.tag] = (child.text or "").strip()

    tables = [table.get("schema") for table in run.findall("./data/table")]

    return {
        "run_number": run.get("number"),
        "device": device.attrib if device is not None else None,
        "host_device": host_device.attrib if host_device is not None else None,
        "process": process.attrib if process is not None else None,
        "tables": tables,
        "summary": summary_map,
    }


def parse_schema_columns(xml_path: Path) -> list[dict]:
    tree = ET.parse(xml_path)
    node = tree.find("./node")
    if node is None:
        return []
    schema = node.find("./schema")
    if schema is None:
        return []

    columns: list[dict] = []
    for col in schema.findall("./col"):
        columns.append(
            {
                "mnemonic": (col.findtext("./mnemonic") or "").strip(),
                "name": (col.findtext("./name") or "").strip(),
                "engineering_type": (col.findtext("./engineering-type") or "").strip(),
            }
        )
    return columns


def parse_potential_hangs(xml_path: Path) -> list[dict]:
    resolver = Resolver()
    rows: list[dict] = []

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue
        children = list(elem)
        rows.append(
            {
                "start": resolver.value(children[0]),
                "duration": resolver.value(children[1]),
                "duration_ns": int(resolver.raw_text(children[1])),
                "hang_type": resolver.value(children[2]),
                "thread": resolver.value(children[3]),
                "process": resolver.value(children[4]),
            }
        )
        elem.clear()

    return rows


def parse_hitches(xml_path: Path) -> dict:
    resolver = Resolver()
    hitches: list[dict] = []
    narrative_counts: Counter[str] = Counter()

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue
        children = list(elem)
        hitch = {
            "start": resolver.value(children[0]),
            "duration": resolver.value(children[1]),
            "duration_ns": int(resolver.raw_text(children[1])),
            "process": resolver.value(children[2]),
            "display": resolver.value(children[6]),
            "narrative": resolver.value(children[7]),
        }
        hitches.append(hitch)
        narrative_counts[hitch["narrative"] or "Unlabeled"] += 1
        elem.clear()

    return {
        "count": len(hitches),
        "narrative_counts": dict(narrative_counts),
        "top_by_duration": sorted(hitches, key=lambda item: item["duration_ns"], reverse=True)[:10],
    }


def parse_hang_risks(xml_path: Path) -> list[dict]:
    resolver = Resolver()
    rows: list[dict] = []

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue
        children = list(elem)
        rows.append(
            {
                "time": resolver.value(children[0]),
                "process": resolver.value(children[1]),
                "message": resolver.value(children[2]),
                "severity": resolver.value(children[3]),
                "event_type": resolver.value(children[4]),
                "thread": resolver.value(children[6]) if len(children) > 6 else None,
            }
        )
        elem.clear()

    return rows


def parse_generic_table(xml_path: Path) -> dict:
    columns = parse_schema_columns(xml_path)
    resolver = Resolver()
    top_rows: list[dict] = []
    row_count = 0
    value_counts: dict[str, Counter[str]] = {}

    duration_index = next(
        (
            idx
            for idx, col in enumerate(columns)
            if col["engineering_type"] == "duration" or col["mnemonic"] == "duration"
        ),
        None,
    )

    countable_types = {
        "event-concept",
        "short-string",
        "string",
        "medium-length-string",
        "boolean",
        "kdebug-func",
    }
    countable_indexes = [
        idx for idx, col in enumerate(columns) if col["engineering_type"] in countable_types
    ][:4]

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue

        row_count += 1
        children = list(elem)

        for idx in countable_indexes:
            if idx >= len(children):
                continue
            column_name = columns[idx]["mnemonic"] or columns[idx]["name"] or f"column_{idx}"
            value = resolver.value(children[idx])
            if value is not None:
                value_counts.setdefault(column_name, Counter())[value] += 1

        if duration_index is not None and duration_index < len(children):
            duration_elem = children[duration_index]
            duration_value = int(resolver.raw_text(duration_elem))
            row_summary: dict[str, object] = {"duration_ns": duration_value}
            for idx, column in enumerate(columns[: min(5, len(children))]):
                row_summary[column["mnemonic"] or column["name"] or f"column_{idx}"] = resolver.value(
                    children[idx]
                )
            top_rows.append(row_summary)
        elem.clear()

    top_rows.sort(key=lambda item: int(item["duration_ns"]), reverse=True)

    return {
        "row_count": row_count,
        "columns": columns,
        "value_counts": {
            key: [{"value": value, "count": count} for value, count in counter.most_common(10)]
            for key, counter in value_counts.items()
        },
        "top_by_duration": top_rows[:10],
    }


def parse_swiftui_update_groups(xml_path: Path) -> dict:
    resolver = Resolver()
    label_stats: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"count": 0, "total_duration_ns": 0, "max_duration_ns": 0}
    )

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue
        children = list(elem)
        label = resolver.value(children[2]) or ""
        duration_ns = int(resolver.raw_text(children[1]))
        stats = label_stats[label]
        stats["count"] += 1
        stats["total_duration_ns"] += duration_ns
        if duration_ns > stats["max_duration_ns"]:
            stats["max_duration_ns"] = duration_ns
        elem.clear()

    return {
        "row_count": sum(stats["count"] for stats in label_stats.values()),
        "unique_label_count": len(label_stats),
        "top_by_total_duration": [
            {"label": label, **stats}
            for label, stats in sorted(
                label_stats.items(), key=lambda item: item[1]["total_duration_ns"], reverse=True
            )[:20]
        ],
        "top_by_max_duration": [
            {"label": label, **stats}
            for label, stats in sorted(
                label_stats.items(), key=lambda item: item[1]["max_duration_ns"], reverse=True
            )[:20]
        ],
    }


def parse_swiftui_causes(xml_path: Path) -> dict:
    resolver = Resolver()
    edge_counts: Counter[tuple[str | None, str | None, str | None]] = Counter()
    source_counts: Counter[str | None] = Counter()
    destination_counts: Counter[str | None] = Counter()

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue
        children = list(elem)
        source = resolver.value(children[2])
        destination = resolver.value(children[4])
        label = resolver.value(children[5])
        edge_counts[(label, source, destination)] += 1
        source_counts[source] += 1
        destination_counts[destination] += 1
        elem.clear()

    return {
        "top_source_nodes": [
            {"node": node, "count": count} for node, count in source_counts.most_common(20)
        ],
        "top_destination_nodes": [
            {"node": node, "count": count}
            for node, count in destination_counts.most_common(20)
        ],
        "top_edges": [
            {
                "label": label,
                "source": source,
                "destination": destination,
                "count": count,
            }
            for (label, source, destination), count in edge_counts.most_common(30)
        ],
    }


def parse_time_profile(xml_path: Path) -> dict:
    resolver = Resolver()
    row_count = 0
    total_weight_ns = 0
    thread_weights: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"samples": 0, "total_weight_ns": 0}
    )
    state_weights: Counter[str] = Counter()
    stack_weights: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"samples": 0, "total_weight_ns": 0}
    )
    main_thread_stack_weights: defaultdict[str, dict[str, int]] = defaultdict(
        lambda: {"samples": 0, "total_weight_ns": 0}
    )

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue

        row_count += 1
        children = list(elem)
        thread = resolver.value(children[1]) or "Unknown Thread"
        state = resolver.value(children[4]) or "Unknown State"
        weight_ns = int(resolver.raw_text(children[5]))
        stack = resolver.value(children[6]) or "No Backtrace"

        total_weight_ns += weight_ns
        thread_weights[thread]["samples"] += 1
        thread_weights[thread]["total_weight_ns"] += weight_ns
        state_weights[state] += weight_ns
        stack_weights[stack]["samples"] += 1
        stack_weights[stack]["total_weight_ns"] += weight_ns

        if "Main Thread" in thread:
            main_thread_stack_weights[stack]["samples"] += 1
            main_thread_stack_weights[stack]["total_weight_ns"] += weight_ns
        elem.clear()

    return {
        "row_count": row_count,
        "total_weight_ns": total_weight_ns,
        "top_threads_by_weight": [
            {"thread": thread, **stats}
            for thread, stats in sorted(
                thread_weights.items(), key=lambda item: item[1]["total_weight_ns"], reverse=True
            )[:10]
        ],
        "thread_state_weight": [
            {"state": state, "total_weight_ns": weight}
            for state, weight in state_weights.most_common(10)
        ],
        "top_backtraces_by_weight": [
            {"backtrace": stack, **stats}
            for stack, stats in sorted(
                stack_weights.items(), key=lambda item: item[1]["total_weight_ns"], reverse=True
            )[:10]
        ],
        "top_main_thread_backtraces": [
            {"backtrace": stack, **stats}
            for stack, stats in sorted(
                main_thread_stack_weights.items(),
                key=lambda item: item[1]["total_weight_ns"],
                reverse=True,
            )[:10]
        ],
    }


def parse_runloop_events(xml_path: Path) -> dict:
    resolver = Resolver()
    row_count = 0
    main_thread_rows = 0
    interval_counts: Counter[str] = Counter()
    event_counts: Counter[str] = Counter()
    mode_counts: Counter[str] = Counter()
    main_thread_modes: Counter[str] = Counter()

    for _, elem in ET.iterparse(xml_path, events=("end",)):
        resolver.observe(elem)
        if elem.tag != "row":
            continue
        row_count += 1
        children = list(elem)
        interval_type = resolver.value(children[2]) or "Unknown"
        event_type = resolver.value(children[3]) or "Unknown"
        mode = resolver.value(children[6]) or "Unknown"
        is_main = resolver.value(children[7]) == "Yes"

        interval_counts[interval_type] += 1
        event_counts[event_type] += 1
        mode_counts[mode] += 1
        if is_main:
            main_thread_rows += 1
            main_thread_modes[mode] += 1
        elem.clear()

    return {
        "row_count": row_count,
        "main_thread_rows": main_thread_rows,
        "interval_type_counts": [
            {"interval_type": name, "count": count} for name, count in interval_counts.most_common(10)
        ],
        "event_type_counts": [
            {"event_type": name, "count": count} for name, count in event_counts.most_common(10)
        ],
        "mode_counts": [{"mode": name, "count": count} for name, count in mode_counts.most_common(10)],
        "main_thread_mode_counts": [
            {"mode": name, "count": count} for name, count in main_thread_modes.most_common(10)
        ],
    }


def build_summary(
    exports: dict[str, Path],
    trace_info: dict,
    requested_tables: list[str],
    available_tables: set[str],
    failed_exports: list[dict[str, object]],
) -> dict:
    exported_tables = [name for name in exports.keys() if name != "toc"]
    unavailable_requested_tables = [table for table in requested_tables if table not in available_tables]
    unexported_available_tables = sorted(table for table in available_tables if table not in exported_tables)
    failed_requested_tables = [str(item["table"]) for item in failed_exports if item.get("table")]

    summary: dict[str, object] = {
        "trace": trace_info,
        "coverage": {
            "requested_tables": requested_tables,
            "available_tables": sorted(available_tables),
            "exported_tables": exported_tables,
            "unavailable_requested_tables": unavailable_requested_tables,
            "unexported_available_tables": unexported_available_tables,
            "important_unexported_available_tables": [
                table for table in IMPORTANT_OPTIONAL_TABLES if table in unexported_available_tables
            ],
            "failed_requested_tables": failed_requested_tables,
            "failed_exports": failed_exports,
        },
    }

    if "potential-hangs" in exports:
        summary["potential_hangs"] = parse_potential_hangs(exports["potential-hangs"])
    if "hitches" in exports:
        summary["hitches"] = parse_hitches(exports["hitches"])
    if "hang-risks" in exports:
        summary["hang_risks"] = parse_hang_risks(exports["hang-risks"])
    if "swiftui-update-groups" in exports:
        summary["swiftui_update_groups"] = parse_swiftui_update_groups(
            exports["swiftui-update-groups"]
        )
    if "swiftui-causes" in exports:
        summary["swiftui_causes"] = parse_swiftui_causes(exports["swiftui-causes"])
    if "time-profile" in exports:
        summary["time_profile"] = parse_time_profile(exports["time-profile"])
    if "runloop-events" in exports:
        summary["runloop_events"] = parse_runloop_events(exports["runloop-events"])

    generic_tables = [
        table
        for table in [
            "swiftui-changes",
            "hitches-renders",
            "hitches-gpu",
            "hitches-updates",
            "hitches-frame-lifetimes",
            "hitches-framewait",
        ]
        if table in exports
    ]
    if generic_tables:
        summary["table_summaries"] = {
            table.replace("-", "_"): parse_generic_table(exports[table]) for table in generic_tables
        }

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export selected xctrace tables from a .trace bundle and build a compact JSON summary."
    )
    parser.add_argument("trace_path", help="Path to the .trace bundle")
    parser.add_argument(
        "--output-dir",
        help="Directory for exported artifacts. Defaults to the trace parent directory.",
    )
    parser.add_argument(
        "--include-large-tables",
        action="store_true",
        help="Also export raw swiftui-updates and swiftui-full-causes tables.",
    )
    parser.add_argument(
        "--skip-table",
        action="append",
        default=[],
        help="Schema name to skip. Repeat for multiple tables.",
    )
    parser.add_argument(
        "--export-retries",
        type=int,
        default=DEFAULT_EXPORT_RETRIES,
        help="How many times to retry a failed xctrace export before giving up on that table.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trace_path = Path(args.trace_path).expanduser().resolve()
    if not trace_path.exists():
        print(f"Trace not found: {trace_path}", file=sys.stderr)
        return 1
    if trace_path.suffix != ".trace":
        print(f"Expected a .trace bundle: {trace_path}", file=sys.stderr)
        return 1

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else trace_path.parent.resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    tables = [table for table in DEFAULT_TABLES if table not in set(args.skip_table)]
    if args.include_large_tables:
        tables.extend(table for table in LARGE_TABLES if table not in set(args.skip_table))

    base_name = trace_path.stem

    try:
        toc_path = output_dir / f"{base_name}-toc.xml"
        run_xctrace_export(trace_path, toc_path, xpath=None, retries=args.export_retries)
        trace_info = parse_trace_info(toc_path)
        available_tables = set(trace_info.get("tables", []))
        exports = {"toc": toc_path}
        exported_tables, failed_exports = export_tables(
            trace_path,
            output_dir,
            base_name,
            tables,
            available_tables,
            retries=args.export_retries,
        )
        exports.update(exported_tables)
        summary = build_summary(exports, trace_info, tables, available_tables, failed_exports)
    except XctraceExportError as exc:
        print(exc.describe(), file=sys.stderr)
        return exc.returncode or 1

    summary_path = output_dir / f"{base_name}-trace-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))

    manifest = {
        "trace": str(trace_path),
        "output_dir": str(output_dir),
        "summary": str(summary_path),
        "exports": {name: str(path) for name, path in exports.items()},
        "failed_exports": failed_exports,
    }
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
