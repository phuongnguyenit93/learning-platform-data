# 15.4. Using `jfr view` when the tool version supports it to inspect aggregated data

A Java Flight Recorder (JFR) file can contain thousands or millions of events from the JVM and application. Printing every event with `jfr print` is often far too verbose to quickly answer questions like "How much time are GC pauses taking?", "Which object types have the most allocation samples?", or "Which methods appear most often in CPU samples?". **`jfr view`** builds **predefined summary tables** from the events in a `.jfr` file and displays them directly in the terminal.

An important prerequisite in this topic is the **tool version**: the `jfr view` subcommand was added in **JDK 21**; JDK 17's `jfr` has `summary`/`print` but **does not have `view`**. Some vendors or distributions may backport or adjust features, so **check the actual `jfr` binary you are running and its help output**, rather than only looking at the version of the application that created the recording.

The goal of this lesson: verify support, create/inspect recordings, pick the right view, read summary tables accurately, distinguish absent data from "no problem," handle compatibility errors, and know fallback options on older JDKs.

## 1. Distinguishing JFR reading tools

| Command/tool | Primary output | When to use |
| --- | --- | --- |
| `jfr summary app.jfr` | Recording stats and event types, counts, and sizes. | **First step**: is the file readable, what is the recording span, and which events appear? |
| `jfr metadata app.jfr` | Describes event types, fields, and categories. | When you need to check schemas/fields before filtering or analyzing. |
| `jfr print --events ... app.jfr` | Prints **individual** selected events, in text/JSON/XML. | When you need timestamps, stack traces, and detailed fields of specific events. |
| `jfr view <view> app.jfr` | Aggregated/grouped summary tables using built-in **views** or supported event-type presentations. | When you need a quick overview from the CLI. |
| `jcmd <pid> JFR.view ...` | Displays a view from a running JVM's JFR data **if the diagnostic command is supported**. | When you want a near-real-time view without dumping a file first. |
| JDK Mission Control (JMC) | Graphical UI: timelines, charts, cross-event correlation. | Deep analysis, selecting time windows, drill-down, and visual stack inspection. |

**`summary` does not replace `view`.** `summary` mainly tells you **how many events** exist and how much space they take; a view like `gc-pauses` groups data around a pause perspective, while `allocation-by-class` focuses on allocation samples by class. At the same time, **`view` does not replace `print`** when you need to know the exact timestamp and fields of a single event.

`jfr view` **reads an existing recording file**; running this command does not itself record JFR data in the application. Make sure the `.jfr` file actually exists and contains events relevant to the question being investigated.

## 2. Check version and support first

Run the following commands in a terminal with a **JDK** installed (not a minimal runtime lacking tools):

```bash
java -version
jfr --version
jfr help
jfr help view
```

- `java -version` shows which `java` the shell will invoke.
- `jfr --version` shows the version of the **`jfr` tool**; the two programs can point to **two different JDKs** due to `PATH` and `JAVA_HOME`.
- `jfr help view` (or `jfr --help view` if confirmed by that version's help) shows the syntax and **list of available views**.
- If the tool reports `view` is unrecognized, do not retry with a different view name. Use a JDK that supports `jfr view` (JDK 21+ per official docs) or switch to `jfr summary`/`jfr print`/JMC.

For example, an environment running a **service on JDK 17** and having **JDK 21 installed separately for analysis** is completely valid: you just need to invoke the `jfr` executable from JDK 21 to use `view`. However, verify that the **specific `.jfr` file is readable** via `jfr summary` before interpreting results; do not assume every recording from every JDK/vendor is 100% compatible.

On Linux/macOS, when multiple JDKs are installed, you can specify the full path (the path below is an **example**, not a path guaranteed to exist on every machine):

```bash
/opt/jdk-21/bin/jfr --version
/opt/jdk-21/bin/jfr help view
/opt/jdk-21/bin/jfr summary recording.jfr
```

On Windows, use `<JDK21_HOME>\bin\jfr.exe` in PowerShell/CMD after replacing the placeholder with the actual path. Do not rely on `java -version` alone as proof that `jfr` on `PATH` has the same version.

## 3. Core syntax of `jfr view`

According to JDK 21 documentation:

```text
jfr view [--verbose] [--width <integer>] [--truncate <mode>]
         [--cell-height <integer>] <view> <file>
```

Where:

- `<view>` is the name of a **view table** (e.g., `gc-pauses`, `thread-count`, `allocation-by-class`) or an **event type** supported for display. The available list is provided by `jfr help view`.
- `<file>` is the path to the JFR file, e.g., `recording.jfr`; an absolute path can be used.
- `--width N` sets the maximum table width (in characters); useful when class, method, or path names are long.
- `--cell-height N` limits the number of lines displayed inside a table cell, not the measurement time span.
- `--truncate beginning|end` controls whether to keep the beginning or end of text exceeding cell width; defaults to truncating the end per JDK 21 documentation.
- `--verbose` prints the **query/definition behind the view** so you understand how data is filtered, grouped, and computed. It does not enable missing events in the file.

Order: **options come before the view name**, and the filename comes after the view.

```bash
# List views and help for the exact JDK in use
jfr help view

# Example summary tables
jfr view gc-pauses recording.jfr
jfr view thread-count recording.jfr
jfr view allocation-by-class recording.jfr

# Increase table width, inspect the view's definition
jfr view --width 120 --verbose gc-pauses recording.jfr

# Control long-string truncation and lines per cell
jfr view --width 140 --truncate beginning --cell-height 3 allocation-by-site recording.jfr
```

View names can change across versions. The names above belong to the initial JDK 21 view set; **only use a name when `jfr help view` from the actual executable lists it**. Do not invent names like `cpu-hotspots` or `gc-summary` from memory and treat them as standard syntax.

Special commands in JDK 21+:

```bash
# List event types that can be passed directly to view for the file
jfr view types recording.jfr

# Print many predefined views sequentially (can be very long)
jfr view all-views recording.jfr

# Display all events using the view mechanism (can be huge)
jfr view all-events recording.jfr
```

`all-views` and `all-events` often produce massive output and take time; prefer a targeted view matching your question. `jfr view types` helps check **which event types exist in the recording**; it does not prove an event was configured or captured enough samples to represent all program activity.

## 4. Preparing a suitable recording

### 4.1. Capturing from a running JVM with `jcmd`

On a JVM with attach permissions (same host/matching user), create a recording over a two-minute window:

```bash
# <pid> must be replaced with the actual PID
jcmd <pid> JFR.start name=diag_2m settings=profile duration=120s filename=/tmp/diag-2m.jfr

# Only after the recording finishes and the file has been written:
jfr summary /tmp/diag-2m.jfr
jfr view gc-pauses /tmp/diag-2m.jfr
```

`JFR.start` operates on the JVM, while `jfr summary/view` reads the **file**. `duration=120s` tells the recording to stop after two minutes; when `filename` is specified, data is written to the file when the recording stops. The path must be accessible/writable by the **target JVM**. If the JVM runs inside a container, `/tmp/diag-2m.jfr` is on the **container/JVM** filesystem, not necessarily `/tmp` on the host running analysis commands.

`settings=profile` enables more events and incurs higher overhead/size than `default`. Pick a representative window, rather than recording `profile` indefinitely just to test views.

When a recording is already running and you need a snapshot before it stops:

```bash
jcmd <pid> JFR.dump name=diag_2m filename=/tmp/diag-snapshot.jfr
```

`JFR.dump` writes a snapshot and **the recording can continue running**. Contrast this with `JFR.stop`, which stops the recording. Check `jcmd <pid> help JFR.dump` and file write permissions if the command fails; do not expect the file to appear on your workstation if the JVM runs on another host.

### 4.2. Capturing at startup

Another example: record from service startup and automatically write the file on normal JVM exit:

```bash
java -XX:StartFlightRecording=filename=startup.jfr,settings=profile,dumponexit=true \
  -jar app.jar
```

Do not treat this example as a guarantee that **every crash/SIGKILL/OOMKilled** will leave a complete file. If you need to preserve incident evidence, prepare disk space, write permissions, and collection procedures in advance. Once you have the file, you can run `jfr summary` and `jfr view` on a suitable analysis machine.

### 4.3. Pick the events first, then pick the view

A view only aggregates **events that were recorded**. If a recording uses `default` or `profile` but the target event was disabled, the capture window was too short, events were filtered out by a threshold, or sampling missed short-lived work, the view may be empty.

For example:
- `allocation-by-class` is based on configured allocation/sampling events, **not an inventory of every single object** on the Java heap.
- `hot-methods` typically relies on samples, **not exact CPU time measurements per line of code**.
- `file-reads-by-path` does not necessarily record every brief file read if threshold/sampling settings omit them.
- `gc-pauses` is only meaningful if the recording window contains relevant GC events; a short recording may have zero GCs.

Therefore, when a view is empty, check **event names**, `jfr summary`, `jfr metadata`, and the recording configuration before claiming actual activity was zero.

## 5. Java 17+ hands-on lab — create a recording with known events

To practice `jfr view` without depending on a large application, the following example uses the **JFR API available since Java 17** to emit five `demo.BatchStep` events and save `view-demo.jfr`. The **recording creation** part can run on JDK 17; the **`jfr view`** part requires a binary that supports it, such as JDK 21+.

Save `JfrViewDemo.java`:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrViewDemo {
    @Name("demo.BatchStep")
    @Label("Batch step")
    @Category({"Demo", "Batch"})
    public static final class BatchStepEvent extends Event {
        @Label("Items processed")
        public int items;
    }

    public static void main(String[] args) throws Exception {
        try (Recording recording = new Recording()) {
            recording.enable(BatchStepEvent.class)
                    .withThreshold(Duration.ZERO);
            recording.start();

            for (int i = 1; i <= 5; i++) {
                BatchStepEvent event = new BatchStepEvent();
                event.items = i * 10;
                event.begin();
                Thread.sleep(50);
                event.commit();
            }

            recording.stop();
            recording.dump(Path.of("view-demo.jfr"));
        }

        System.out.println("Created view-demo.jfr");
    }
}
```

Compile and run with JDK 17 or later in a writable directory:

```bash
javac JfrViewDemo.java
java JfrViewDemo
```

**Stdout printed by the program if it runs successfully:**

```text
Created view-demo.jfr
```

The program explicitly enables `demo.BatchStep` with threshold zero, calls `begin()/commit()` five times, and calls `stop()/dump()` on the recording. File size, timestamps, additional event types, and how the tool formats tables can vary across JDKs. The program is not meant to simulate real CPU/GC load; it is meant to verify the **record – read – aggregated view** path.

On JDK 21+, read the file as follows:

```bash
jfr --version
jfr summary view-demo.jfr
jfr view types view-demo.jfr

# Custom event name, on jfr view versions supporting event-type views
jfr view demo.BatchStep view-demo.jfr

# Inspect individual events to cross-check
jfr print --events demo.BatchStep view-demo.jfr
```

For this custom event type, the `items` field is emitted as **10, 20, 30, 40, 50** in order with real timestamps/durations recorded by the JVM. **Do not assume `jfr view` will automatically compute "total items = 150"** when passing the event name: grouping, formulas, and output columns depend on the view/event-type definition. If you want the business total across the five events in the example, sum the `items` fields from individual events or process them intentionally; do not infer from a table header without checking.

If you use JDK 17's `jfr` on the same file, you can run `jfr summary` and `jfr print`, but `jfr view` **is not supported** per JDK 17 documentation. The JDK 21+ analysis step uses the exact `view-demo.jfr` file just created, not a new recording.

## 6. Choosing the right view for the diagnostic question

The views below are **examples from the JDK 21 view list**. Confirm the exact list with `jfr help view` on the machine in use.

| Practical question | Suggested views | How to read, caveats to remember |
| --- | --- | --- |
| Do GC pauses affect latency? | `gc-pauses`, `gc-pause-phases`, `gc` | Inspect count/total time/distribution of events and phases; check p95/p99 via timeline and specific events if needed. |
| Where is memory allocated? | `allocation-by-class`, `allocation-by-site`, `allocation-by-thread` | Samples by type, site, thread; sampling data and event settings affect results. |
| Which code appears often in CPU samples? | `hot-methods` | Hotspot hint; read stack samples, do not directly convert sample counts to exact milliseconds. |
| Is there a thread issue? | `thread-count`, `thread-cpu-load`, `thread-allocation` | Inspect trends/distributions from recorded events, relate to thread states and workload. |
| What I/O stands out? | `file-reads-by-path`, `file-writes-by-path`, `socket-reads-by-host` | Events exceeding threshold or enabled; not an inventory of every syscall. |
| Which errors/exceptions recur? | `exception-by-class` **only if listed by help**; more commonly `exception-by-site`, `exception-by-message` | Exception events can incur overhead; inspect exception class, site, and collection config. |
| How are class loaders behaving? | `class-loaders`, `longest-class-loading` | Cross-check load counts/lifecycle; the view itself does not prove a loader leak. |
| Environment differences? | `jvm-flags`, `container-memory-usage`, `cpu-load` | Observed configuration and usage; tied to recording window. |

**Do not use a single table alone to conclude root cause.** For example, `hot-methods` showing a high sample share in method A may simply reflect that the workload passes through A most often, not that A is buggy or needs optimization. `allocation-by-class` showing lots of `byte[]` still requires checking who allocates them, object lifetimes, and GC impact.

### Example of reading `gc-pauses` with hypothetical numbers

Suppose a recording lasts **120 seconds**, and the relevant events show **120 pauses** with a total pause time of **480 ms**. Independent calculations:

- **Average pause** = `480 ms / 120 = 4 ms` per pause.
- **Wall-clock share spent in pauses** (under a model where summed pauses do not overlap) = `0.48 s / 120 s = 0.4%`.

These are purely **hypothetical numbers for reading practice**, not default `jfr view` output and not "good/bad" thresholds for every system. You cannot deduce the **longest pause**, `p95`, or `p99` from just the sum and count. A few pauses lasting hundreds of milliseconds can cause high tail latency even with a 4 ms average.

To find out when those long pauses occurred, switch to `jfr print --events jdk.GarbageCollection ...` or JMC and inspect the relevant GC events/phases. Correlate with request latency/traffic in the same time window; avoid reading percentages or durations without checking units.

### Why "Top 10" requires caution

Views display top entries according to **that view's** statistic; it may be event count, sample count, total duration, or another ranking metric. Before concluding:

1. Check column names, units, and the view description.
2. Use `--verbose` to read the view's query/definition, especially for columns with abbreviated labels.
3. Check recording settings, thresholds, and sample counts.
4. When you need evidence of a specific occurrence, use `jfr print` or JMC's timeline.

"Not in the Top 10" **does not mean there is no problem**: the table may truncate row count, the event type may not be enabled, or sampling may have missed it.

## 7. Adjusting table readability in the terminal

### 7.1. Truncated class/method/path names

```bash
jfr view --width 160 --cell-height 4 allocation-by-site recording.jfr
```

`--width` increases table width, helping reveal long stack traces or paths. `--cell-height` increases lines shown per cell without increasing recorded events. If the terminal is still narrow, redirect output to a text file using shell tools or open it interactively in JMC; do not treat `...` as part of a Java identifier.

### 7.2. Choosing whether to keep the beginning or end of strings

```bash
jfr view --width 120 --truncate beginning file-reads-by-path recording.jfr
jfr view --width 120 --truncate end file-reads-by-path recording.jfr
```

Truncating the beginning can keep the recognizable **filename at the end of a path**; truncating the end can keep the **prefix/root directory**. This only changes display, not the recording. When writing an investigation report, do not copy a truncated path and treat it as the full path.

### 7.3. Inspecting the view query used

```bash
jfr view --verbose hot-methods recording.jfr
```

`--verbose` lets you see the filtering/grouping/aggregation mechanism the view uses in that version. Do not mistake this for a way to **enable stack traces or change JFR configuration**; the file is already recorded, and display flags cannot add missing events.

## 8. Reading live data with `jcmd JFR.view` when supported

Alongside reading files, on a JDK supporting the corresponding diagnostic command, you can inspect a view directly from a running JVM:

```bash
# Get the PID from the actual environment
jcmd -l

# Check whether the target JVM supports it
jcmd <pid> help JFR.view

# Example viewing from the JVM's data without specifying a .jfr file
jcmd <pid> JFR.view gc-pauses
```

`jcmd` requires appropriate attach permissions and must target the right JVM/PID. **`jfr view` and `jcmd JFR.view` do not share the exact same parameter interface:**

| | `jfr view` | `jcmd JFR.view` |
| --- | --- | --- |
| Source | An existing `.jfr` file. | JFR data of a running JVM. |
| Main input | `<view> <file>`. | `<pid> JFR.view <view>`. |
| Permissions | Read access to the file from the analysis machine. | Permission to attach to the JVM. |
| Time window | Contents of the recording file. | Depends on retained data and options like `maxage`/`maxsize` supported by the JVM. |
| Checking support | `jfr help view`. | `jcmd <pid> help JFR.view`. |

On supporting versions, `JFR.view` typically provides options such as `maxage`, `maxsize`, `width`, and `verbose`. Check the **target JVM's** help before using; do not blindly pass `jfr`'s `--width` syntax to `jcmd`, since `jcmd` uses its own `key=value`/positional arguments.

If the JVM does not support `JFR.view` or attach is unavailable, you can still create/dump JFR through permitted paths and analyze it **offline** with a newer JDK that has `jfr view`.

## 9. Safe alternatives on JDK 17 or when `view` is unavailable

For JDK 17, `jfr summary`, `jfr print`, and `jfr metadata` remain useful:

```bash
# Identify which events are present, counts, and recording span
jfr summary recording.jfr

# Inspect recorded event schemas
jfr metadata recording.jfr

# Print only recorded GC events (verify event names against summary)
jfr print --events jdk.GarbageCollection recording.jfr

# If external programmatic processing is needed, export JSON
jfr print --json --events jdk.GarbageCollection recording.jfr
```

`jfr print --json` outputs machine-readable event data for custom aggregation scripts; parse the JSON structure properly rather than running regexes over table output. For large files, printing all events can consume significant memory, time, and stdout volume. Filter by event type and extract only the fields you need.

Another option is **opening in JDK Mission Control**: filter time ranges, inspect GC timelines, CPU, allocations, threads, I/O, stack traces, and drill down. If you want quick views while the service still runs JDK 17, try the `jfr` executable from **JDK 21+ on your analysis machine**, after `summary` confirms file compatibility. There is no need to upgrade the production Java runtime just to view a summary table from an existing file.

## 10. Troubleshooting common issues

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `Unrecognized command: view` or help lacks `view` | `jfr` is too old or a different distribution. | Check `jfr --version` and executable path; use JDK 21+ with the feature or fallback. |
| `jfr: command not found` / `jfr.exe` not found | Minimal JRE in use, JDK not installed, or wrong `PATH`. | Locate `<JDK_HOME>/bin/jfr` and run by full path. |
| `Unknown view` | Misspelled view name or absent in this version. | Run `jfr help view`; distinguish `gc-pauses` from invented names. |
| Cannot open `recording.jfr` | Wrong path, file not finished/written, read permissions, or corrupt file. | `ls -lh`/`dir`, `jfr summary`, check JFR logs and file size. |
| View shows few or no rows | Event disabled, filtered by threshold, rare samples, short recording, unrelated view. | `jfr summary`, `jfr metadata`, `.jfc` config, and actual workload. |
| Many long names end in `...` | Narrow table/truncated display. | `--width`/`--cell-height`, change `--truncate`, inspect raw events if needed. |
| `all-views` produces too much output | Too broad on a large file. | Pick individual views per hypothesis; run `all-views` only when truly needed. |
| Numbers differ from dashboards | Different time window, event type, sampling, aggregation, or instance. | Align timestamps/timezone, JVM scope, thresholds, event names, and formulas. |
| `jcmd ... JFR.view` does not exist | Target JVM too old, command not provided, or missing attach permission. | `jcmd <pid> help`; switch to offline file analysis with `jfr view`. |
| View looks "inaccurate" on allocations | Sampling means numbers are not total actual allocations. | Check sampling event config and cross-check with profilers/other allocation metrics. |

### Pitfalls with file versions and event names

The version that **created** the recording, the version **reading** the recording, and the **recorded event types** are three separate facts. A JDK 17 recording can be opened with a JDK 21 tool to use `view`, though you still must check the file, event types, and schema with `summary`/`metadata`. Conversely, a newer file containing an event type unknown to an older tool must not be interpreted as "no events." Likewise, a view listed in help does not prove the recording enabled the corresponding events.

Be sure to record:
- Producer JDK/vendor/version of the recorded application.
- Reader JDK/vendor/version of `jfr` used for analysis.
- Recording settings (`default`/`profile`/custom), start–end times, duration, file size, and instance/PID.
- View name executed, display flags, and exact column names/units interpreted.

## 11. Practical workflow template when handed a `.jfr` file

**Scenario:** operations hands over `incident.jfr` and suspects GC pauses are impacting latency.

1. **Verify the tool:** run `jfr --version` and `jfr help view`; if `view` is absent, pick a newer tool or fallback.
2. **Check the source:** run `jfr summary incident.jfr` to verify the recording is valid, check its time span, and confirm GC events are present.
3. **Choose a view:** run `jfr view gc-pauses incident.jfr`; if GC phases are needed, use `gc-pause-phases` if listed in help.
4. **Read calculations properly:** distinguish counts, total time, averages, percentages, percentiles, and individual event timestamps. If a table only shows aggregates, do not infer the timing of a spike from it.
5. **Cross-check details:** run `jfr print --events jdk.GarbageCollection incident.jfr`, JMC timeline, and related GC events; align with request latency/traffic logs.
6. **Write a scoped conclusion:** "In the 14:00–14:02 recording on instance A, recorded GC pauses had ..." rather than "GC always causes all slowness in the system."
7. **Save reproducible commands:** record the `jfr` version, view name, and file path/name so others can verify the exact same data.

For a **allocation pressure** hypothesis, swap GC views for `allocation-by-class`/`allocation-by-site` and verify sampling; for a **CPU hot path** hypothesis, use `hot-methods` and check stacks/samples; for **thread/I/O** issues, choose specialized views and open detailed events when needed.

## 12. Misconceptions to avoid

- **“JDK 17 has JFR, so it definitely has `jfr view`.”** False: `view` was added in JDK 21, while `summary`/`print` were already in JDK 17.
- **“`jfr view` collects live data from a running process.”** False: `jfr view` reads a **file**; `jcmd JFR.view` is a separate interface for a running JVM when supported.
- **“An empty view means zero activity.”** False: the recording may not have enabled the event, lacked duration, or filtered it by threshold.
- **“View names are the same as event type names.”** Not necessarily: `gc-pauses` is an aggregated view; `jdk.GarbageCollection` is an event type name.
- **“`jfr summary` is a complete performance report.”** False: `summary` gives counts/sizes per event, lacking timelines and call paths needed for root-cause conclusions.
- **“`allocation-by-class` reflects every single heap allocation.”** False: it typically depends on sampling/enabled events.
- **“`hot-methods` is the exact % CPU of each method.”** False: it is typically a statistical observation from stack samples; check representativeness.
- **“Adding `--verbose` fills in missing stack traces.”** False: it is an option to **display the view definition**.
- **“Larger table width means the recording has more data.”** False: `--width`/`--truncate` only change text layout.
- **“View names in a tutorial apply to every future JDK.”** False: check the actual tool's help output.
- **“You can copy table output directly and parse it as stably as JSON.”** Not guaranteed: views are formatted for human readers; for stable automation, consider `jfr print --json` or the JFR consumer API and handle schemas explicitly.

## 13. Checklist before sending conclusions from `jfr view`

- [ ] Verified the `jfr` binary has `view` using `jfr help view`.
- [ ] `.jfr` file is readable via `jfr summary` and matches the right instance and time range.
- [ ] View chosen matches the **question** and appears in the tool version's help.
- [ ] Necessary events actually exist in the file; recording settings/thresholds/sampling are understood.
- [ ] Columns, units, and aggregation formulas are understood; used `--verbose` if unsure.
- [ ] Did not extrapolate p95/p99 or root cause from an aggregate table lacking that data.
- [ ] Checked `jfr print` or JMC whenever exact timestamps, stack traces, threads, or full paths are needed.
- [ ] Clearly recorded JDK tool version, file, view, time window, and data limitations when sharing the report.

**Takeaway:** `jfr view` is an **aggregation and presentation** layer over JFR events **that were already collected**; it lets you get quick insights from large files in the terminal. Prerequisites are **a tool version with support (JDK 21+ per official docs)**, capturing the right events, and understanding each view's statistics. On older JDKs or when tables lack depth, combine `jfr summary`, `jfr print`, `jfr metadata`, and JMC to verify.

### References

- [Oracle JDK 21 — The jfr Command, syntax and `jfr view` options](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle JDK 17 — The jfr Command (without `view`)](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [Inside Java — JFR View Command, Java 21 feature introduction and view examples](https://inside.java/2023/09/26/sip082/)
- [Oracle JDK 21 — The jcmd Command, `JFR.start`/`JFR.dump` and `JFR.view`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle JDK 17 — `jdk.jfr.Recording` API for the Java example](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html)
