# GC Log: Recording and Analyzing Garbage Collection

A **GC log** is a text log emitted by the Java Virtual Machine (JVM) that describes Garbage Collection (GC) activity, collector phases, heap changes, collection causes, and application stops at safepoints. Since Java 9, HotSpot has used **Unified Logging** via the `-Xlog` option; Java 17+ continues to use this syntax.

GC logs help answer operational questions: when GC occurred, which collection type ran, why the collection was triggered, how long the pause lasted, how the heap changed, and which phases took the collector's time. This is foundational data for investigating latency, throughput, allocation pressure, and memory pressure. You should read the log alongside workload, metrics, and JVM configuration; a single log line is not enough to conclude a memory leak or make tuning decisions.

## 1. Unified Logging and GC Logs

Before Java 9, GC logging typically used separate flags such as `-XX:+PrintGCDetails`, `-XX:+PrintGCDateStamps`, and `-Xloggc`. Unified Logging consolidates JVM diagnostic messages into a single system, allowing you to select content by **tag**, verbosity level, output destination, and timestamp format.

General syntax:

```text
-Xlog[:[tag-selection][:[output][:[decorators][:output-options]]]]
```

Components:

| Component | Role | Example |
| --- | --- | --- |
| Tag selection | Selects message groups and log level | `gc*=info`, `gc+heap=debug` |
| Output | Selects output destination | `stdout`, `stderr`, `file=gc.log` |
| Decorators | Selects metadata prepended to each message | `time,uptime,level,tags` |
| Output options | Configures file behavior and rotation | `filesize=20M,filecount=5` |

Check the exact tags, levels, decorators, and syntax supported by the running JDK:

```bash
java -Xlog:help
```

Specific GC tags and details depend on the JDK, JVM vendor, and garbage collector. Check the help output on the exact environment under investigation before using a specific selector.

## 2. Getting Started with Basic GC Logging

Write GC messages at the `info` level to the console:

```bash
java -Xlog:gc -jar app.jar
```

This command selects the `gc` tag set at the `info` level. Some messages that carry additional tags such as `gc,heap`, `gc,start`, or `gc,phases` require a matching selector to appear.

To capture most message groups tagged with `gc`, use a wildcard:

```bash
java -Xlog:gc*=info -jar app.jar
```

To see additional heap information and GC phases:

```bash
java -Xlog:gc*=debug -jar app.jar
```

The `debug` level is useful during investigation but generates more log volume. Only increase verbosity for as long as needed and monitor log disk usage.

To observe GC and safepoints together:

```bash
java -Xlog:gc*=info,safepoint=info -jar app.jar
```

Do not enable `all=trace` as a default production configuration. It can generate massive log volume and increase I/O overhead.

## 3. Understanding Tags, Wildcards, and Levels

Each message has a tag set and a level.

**Tags** describe the component or content of a log message. Common GC tags on HotSpot include:

| Tag | Typical Content |
| --- | --- |
| `gc` | Collection events and summary information |
| `heap` | Heap occupancy, regions, and memory changes |
| `phases` | Collection phases |
| `start` | Start of a collection or a phase |
| `ergo` | Automatic collector decisions and policies |
| `age` | Object age distribution and tenuring |
| `ref` | Reference processing |
| `region` | Regions for collectors such as G1 |
| `humongous` | Humongous objects in G1 |
| `cpu` | CPU time related to collection |
| `safepoint` | Events where the JVM brings threads to a safepoint |

Not every JVM or collector exposes the same tags. Run `java -Xlog:help` to see the actual list.

### Plus and Comma Have Different Meanings

- The `+` sign combines tags with a logical AND: `gc+heap` selects only messages that have both tags.
- A comma separates independent selectors: `gc,safepoint` selects messages belonging to either the `gc` tag or the `safepoint` tag.
- Without a wildcard, only the exact specified tag set matches.
- The `*` wildcard matches tag sets containing the specified tags, even if other tags are also present.

Examples:

```bash
# Exact tag set of gc and heap
-Xlog:gc+heap=debug

# Any tag set containing gc
-Xlog:gc*=info

# Any tag set containing gc and heap
-Xlog:gc+heap*=debug

# GC and safepoint as two separate selectors
-Xlog:gc*,safepoint=info
```

`gc` and `gc*` are not equivalent. `gc` can omit messages carrying the `gc,heap` tag set; `gc*` includes all tag sets containing `gc`.

### Log Levels

| Level | Purpose |
| --- | --- |
| `off` | Disables matching messages |
| `trace` | Deepest detail, usually very verbose |
| `debug` | Additional diagnostic information |
| `info` | Normal operational information |
| `warning` | Warnings |
| `error` | Errors |

Levels act as a verbosity threshold. For example, `debug` includes messages at `debug` and higher-severity levels such as `info`, `warning`, and `error`. `trace` extends this further.

## 4. Choosing Output and Decorators

### Output Destination

GC logs can be written to:

- `stdout`: standard output.
- `stderr`: standard error.
- `file=filename`: a text file.

Writing to a file:

```bash
java -Xlog:gc*=info:file=gc.log -jar app.jar
```

Writing to the console fits containerized environments that already collect `stdout`/`stderr`. Writing to a file is suitable when logs must be kept locally, provided you manage rotation, disk space, and permissions.

You can include the PID and startup timestamp in the filename to prevent multiple JVMs from overwriting the same file:

```bash
java -Xlog:gc*=info:file=gc-%p-%t.log -jar app.jar
```

In the filename, `%p` is replaced by the PID and `%t` by the JVM startup timestamp. Some JDKs also support `%hn` to insert the hostname.

### Decorators

Decorators are metadata prepended to each message. By default, this typically includes `uptime`, `level`, and `tags`.

| Decorator | Meaning |
| --- | --- |
| `time` | Current date and time in ISO-8601 format |
| `utctime` | UTC time |
| `uptime` | Time elapsed since JVM startup |
| `timemillis` | Value corresponding to `System.currentTimeMillis()` |
| `uptimemillis` | Milliseconds since JVM startup |
| `timenanos` | Value corresponding to `System.nanoTime()` |
| `uptimenanos` | Nanoseconds since JVM startup |
| `hostname` | Hostname |
| `pid` | Process ID |
| `tid` | Thread ID |
| `level` | Log level |
| `tags` | Message tag set |

Example:

```bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
```

A log line may look like:

```text
[2026-11-10T20:10:09.178+0700][0.144s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
```

How to read it:

- `2026-11-10T20:10:09.178+0700`: wall-clock time.
- `0.144s`: the JVM has been running for 0.144 seconds.
- `info`: log level.
- `gc,start`: tag set.
- `GC(0)`: collection ID within this process.
- Everything after the ID: collection type and cause/description.

Use `time` or `utctime` to correlate with application logs across multiple machines. Use `uptime` to see event ordering within the same JVM.

## 5. Writing GC Logs to Files with Rotation

GC logs can grow quickly, especially when `debug` or `trace` is enabled. Configure rotation to limit disk usage and the number of retained files.

Example:

```bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
```

Meaning:

- `filecount=5`: keep at most five rotated files, excluding the active file.
- `filesize=20M`: trigger rotation when the file approaches the 20 MB target size.
- The actual size is approximate, not a strict byte-exact limit.

Key points to keep in mind:

- `filecount=0` disables rotation; older files may be overwritten.
- `filesize=0` disables automatic rotation; you can still rotate manually with `jcmd`.
- Including `%p` and `%t` in the filename helps avoid collisions across JVMs.
- Check volume capacity and retention policies before enabling verbose logging.
- When running in containers, use `stdout`/`stderr` or a file on a volume with an explicit collection and retention mechanism.

You can enable asynchronous logging:

```bash
java -Xlog:async -Xlog:gc*=info:file=gc.log -jar app.jar
```

Async mode writes messages into an intermediate buffer and a dedicated thread flushes them to the output. It reduces synchronous logging overhead at the log site, but the buffer is bounded; when the buffer fills up, new messages may be dropped. Only use it when you understand the trade-off between overhead and log completeness.

## 6. Common GC Log Configurations

Start with a concise configuration:

```bash
-Xlog:gc*=info
```

When you need more detail, increase verbosity based on the specific question:

| Goal | Configuration |
| --- | --- |
| GC summary | `-Xlog:gc` |
| All tag sets containing `gc` | `-Xlog:gc*=info` |
| Heap before/after GC | `-Xlog:gc+heap=debug` |
| GC phases | `-Xlog:gc+phases=debug` |
| Ergonomics decisions | `-Xlog:gc+ergo=debug` |
| Age/tenuring | `-Xlog:gc+age=debug` |
| Reference processing | `-Xlog:gc+ref*=debug` |
| Safepoints | `-Xlog:safepoint=info` |
| GC and safepoints together | `-Xlog:gc*,safepoint=info` |
| G1 region details | `-Xlog:gc+region=debug` |
| G1 humongous objects | `-Xlog:gc+humongous=debug` |

Specific tags depend on the collector and JDK. If a selector is unsupported, the JVM may fail at startup; check `java -Xlog:help` first.

Avoid leaving all selectors at `trace` for extended periods. Start with `info`, then enable `debug` for the relevant tag group for a short window sufficient to answer your question.

## 7. How to Read a GC Cycle

With G1, logs typically contain several message types:

- Collection start: `gc,start`.
- Workers/tasks: `gc,task`.
- Phases: `gc,phases`.
- Heap and regions: `gc,heap`, `gc,region`.
- Collection summary: `gc`.
- CPU time: `gc,cpu`.
- Concurrent work: lines describing `Concurrent Mark Cycle` or the corresponding concurrent phases.

A general example:

```text
[0.047s][info][gc,start] GC(2) Pause Full (System.gc())
[0.047s][info][gc,task] GC(2) Using 2 workers of 20 for full compaction
[0.048s][info][gc,phases] GC(2) Phase 1: Mark live objects 0.758ms
[0.048s][info][gc,phases] GC(2) Phase 2: Prepare compaction 0.066ms
[0.048s][info][gc,phases] GC(2) Phase 3: Adjust pointers 0.283ms
[0.048s][info][gc,phases] GC(2) Phase 4: Compact heap 0.076ms
[0.049s][info][gc,heap] GC(2) Humongous regions: 33->9
[0.049s][info][gc] GC(2) Pause Full (System.gc()) 35M->10M(40M) 1.637ms
```

This is an actual log snippet from HotSpot JDK 24.0.2 in a sample workload; GC IDs, timings, region counts, and sizes vary per run.

### Reading the Summary Line

Example:

```text
GC(2) Pause Full (System.gc()) 35M->10M(40M) 1.637ms
```

This can be interpreted as:

- `GC(2)`: collection ID 2.
- `Pause Full`: a stop-the-world full collection.
- `(System.gc())`: recorded cause is an explicit GC call.
- `35M`: heap occupancy before the collection.
- `10M`: heap occupancy after the collection.
- `(40M)`: heap capacity at the time of the log.
- `1.637ms`: pause duration reported for this collection.

Exact formatting varies by collector and JDK. Do not compare numbers across runs if heap size, collector, workload, or sampling window differ.

### Distinguishing Pauses from Concurrent Cycles

Not every GC log line means the application was paused.

- `Pause Young` and `Pause Full` are collection pauses; Java threads are stopped during the corresponding pause.
- `Concurrent Mark Cycle` describes a cycle with concurrent work; the application can continue running for most of that time.
- A concurrent cycle may include one or more short pauses.
- `GC(n)` groups messages belonging to the same collection.

Do not treat the total duration of a concurrent cycle as application pause time. When investigating latency, look at `Pause` lines, pause phases, and safepoints. When investigating CPU/throughput, also examine concurrent durations and CPU time.

## 8. Heap Before/After and Signs to Investigate

Heap log lines let you compare state before and after a collection. Detailed logs may look like:

```text
[debug][gc,heap] GC(34) Heap before GC invocations=33 (full 0):
[debug][gc,heap] GC(34) garbage-first heap ... used 34321K
[info ][gc,heap] GC(34) Eden regions: 8->0(18)
[info ][gc,heap] GC(34) Old regions: 2->2
[debug][gc,heap] GC(34) Heap after GC invocations=34 (full 0):
[debug][gc,heap] GC(34) garbage-first heap ... used 26129K
```

When analyzing:

1. Compare heap occupancy before and after the collection.
2. Observe Eden/Survivor/Old regions if provided by the collector.
3. Track old-gen occupancy across multiple collections.
4. Check promotion and tenuring as objects survive multiple young GCs.
5. Correlate with allocation rate, GC cause, and workload at the same time.

If post-GC heap occupancy climbs steadily over many cycles under a comparable workload, object retention or a growing live set may be occurring. If the heap drops sharply yet GC runs constantly, allocation pressure may be high. Both cases require further evidence; GC logs do not tell you which objects hold references.

To identify objects retaining heap, combine class histograms, heap dumps, JFR old-object sampling, or Eclipse Memory Analyzer (MAT).

## 9. Safepoint Logs and Application Stop Time

A safepoint is a state where the JVM brings Java threads to a safe point to perform internal operations. GC is a major cause, but not the only reason the JVM enters a safepoint.

Enable safepoint logging:

```bash
java -Xlog:safepoint=info -jar app.jar
```

Or combine it with GC:

```bash
java -Xlog:gc*,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags -jar app.jar
```

Safepoint logs help you observe:

- Time spent waiting for threads to reach a safepoint.
- Time spent executing the operation at the safepoint.
- Total stop time associated with the safepoint.
- Safepoints caused by non-GC VM operations.

A pause can involve both safepoint synchronization time and operation execution time. Therefore, if GC pauses are short while application stopped time is long, check safepoint synchronization and concurrent VM operations.

Do not mechanically sum all safepoint lines and GC phases, as intervals can overlap or be nested. Read the context and timestamps of each event.

## 10. Dynamic GC Logging with `jcmd VM.log`

Unified Logging can be reconfigured while the JVM is running; you do not necessarily have to restart just to enable another selector.

List JVMs:

```bash
jcmd -l
```

View command help on the target process:

```bash
jcmd 18420 help VM.log
```

List current log configuration:

```bash
jcmd 18420 VM.log list
```

Enable additional heap details to a new file:

```bash
jcmd 18420 VM.log output=file=gc-live.log what=gc+heap=debug decorators=time,uptime,level,tags output_options=filesize=10M,filecount=5
```

Where:

- `output`: selects the target file or configured output.
- `what`: tag selection and level to enable.
- `decorators`: metadata for each line.
- `output_options`: file rotation settings.

You can inspect the updated configuration with `VM.log list`. Manually rotate log files:

```bash
jcmd 18420 VM.log rotate
```

`VM.log` has low impact on JDK 24. `jcmd` must run on the same host and typically requires the same effective user/group as the target JVM. PID `18420` is only an example.

Dynamic changes apply only from the moment they are enabled onward; they do not retroactively generate logs for past collections. Verify the output path and JVM write permissions before enabling a new file. Avoid disabling all logging unless you understand it may also clear existing `warning`/`error` configurations.

## 11. Migrating from Legacy GC Log Flags to Unified Logging

On Java 9+, use `-Xlog` instead of legacy GC logging flags.

| Legacy Flag | Unified Logging Configuration |
| --- | --- |
| `-XX:+PrintGC` | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | `-Xlog:gc*` |
| `-XX:+PrintHeapAtGC` | `-Xlog:gc+heap=trace` |
| `-XX:+PrintGCApplicationStoppedTime` | `-Xlog:safepoint` |
| `-XX:+PrintTenuringDistribution` | `-Xlog:gc+age=debug` |
| `-XX:+PrintReferenceGC` | `-Xlog:gc+ref*=debug` |
| `-Xloggc:gc.log` | `-Xlog:gc:file=gc.log` |

Some legacy flags are deprecated or removed. Do not mix old and new configurations arbitrarily; use Unified Logging syntax and check the JDK help output.

`-Xloggc` is replaced by `-Xlog:gc:file=...` in modern JDKs. For Java 8, you must use flags compatible with that version because Unified Logging does not exist there.

## 12. Java 17 Hands-On Example: Generating and Reading GC Logs

This example allocates several temporary byte arrays, drops references to them, and requests an explicit GC to produce an easy-to-inspect log. A static array is retained to distinguish reclaimed objects from objects that remain reachable.

Create the directory structure:

```text
project/
  src/
    GcLogDemo.java
  out/
```

File `src/GcLogDemo.java`:

```java
public final class GcLogDemo {
    private static final byte[] RETAINED = new byte[8 * 1024 * 1024];

    private GcLogDemo() {
    }

    public static void main(String[] args) {
        byte[][] temporary = new byte[12][];

        for (int i = 0; i < temporary.length; i++) {
            temporary[i] = new byte[1024 * 1024];
        }

        System.out.println("allocated temporary arrays=" + temporary.length);
        temporary = null;

        System.out.println("requesting explicit GC");
        System.gc();

        System.out.println(
            "GC request completed; retained bytes=" + RETAINED.length
        );
    }
}
```

Compile with Java 17:

```bash
mkdir out
javac --release 17 -g -d out src/GcLogDemo.java
```

Run with G1, a bounded heap, and detailed GC logging:

```bash
java -Xms32m -Xmx64m -XX:+UseG1GC -Xlog:gc*=info:file=gc-demo.log:uptime,level,tags:filecount=3,filesize=1m -cp out GcLogDemo
```

Stdout from the test run:

```text
allocated temporary arrays=12
requesting explicit GC
GC request completed; retained bytes=8388608
```

In `gc-demo.log`, a log snippet from the same run looks like:

```text
[0.047s][info][gc,start] GC(2) Pause Full (System.gc())
[0.047s][info][gc,task] GC(2) Using 2 workers of 20 for full compaction
[0.048s][info][gc,phases] GC(2) Phase 1: Mark live objects 0.758ms
[0.048s][info][gc,phases] GC(2) Phase 2: Prepare compaction 0.066ms
[0.048s][info][gc,phases] GC(2) Phase 3: Adjust pointers 0.283ms
[0.048s][info][gc,phases] GC(2) Phase 4: Compact heap 0.076ms
[0.049s][info][gc,heap] GC(2) Humongous regions: 33->9
[0.049s][info][gc] GC(2) Pause Full (System.gc()) 35M->10M(40M) 1.637ms
```

The output above is from a HotSpot JDK 24.0.2 run using Java 17-compatible source. IDs, timings, region counts, and sizes may differ on another run.

Key observations:

- `System.gc()` appears as the cause of the Full GC.
- Heap occupancy drops from `35M` to `10M`.
- The 8 MiB static array remains reachable.
- `GC(2)` links the phases and summary line of the same collection.
- The compaction phases explain the work performed by the collector during the pause.

`System.gc()` is used here purely for demonstration. Do not invoke explicit GC as a routine operational strategy; the JVM may ignore it depending on configuration, and a full GC can cause significant pauses.

## 13. Combining GC Logs with JFR and Other Tools

GC logs provide a useful text view of collections, causes, heap occupancy, and phases. For deeper analysis, combine them with:

| Tool | Role |
| --- | --- |
| GC unified log | Text timeline, causes, heap, phases, safepoints |
| JFR | Structured events, allocation samples, pause distribution, and thread context |
| Java Mission Control | UI for analyzing JFR recordings |
| `jcmd GC.heap_info` | Point-in-time heap summary |
| `jcmd GC.class_histogram` | Object counts and sizes by class |
| `jcmd GC.heap_dump` | Generates an HPROF file for object graph analysis |
| Eclipse MAT | Dominator tree, retained size, and GC roots |
| OS/container metrics | RSS, CPU throttling, memory limits, and process pressure |

Examples:

- GC log shows P99 pauses rising: cross-reference JFR `GarbageCollection`, `GCPhasePause`, and safepoints.
- GC log shows old-gen growing: use a class histogram or heap dump to find object retention.
- Concurrent GC takes too long: inspect JFR GC CPU time, CPU saturation, and container throttling.
- Frequent GCs with stable post-GC heap: inspect allocation-by-site to locate allocation pressure.

GC logs and JFR complement each other. There is no need to enable `trace` across all GC logs if JFR already provides richer data for the question at hand.

## 14. Common Mistakes When Configuring and Reading GC Logs

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| No GC logs appear | Tag set too narrow or wrong selector | Check `-Xlog:help`, try `-Xlog:gc*` |
| Only `gc` summary lines appear | Wildcard or sub-tags not enabled | Enable `gc*` or `gc+heap=debug` |
| JVM reports selector error | Tag does not exist on that JDK/collector | Check the actual tag list |
| Too much log output | `debug`/`trace` enabled on too many tags | Lower to `info`, narrow tags and duration |
| Log file grows indefinitely | Rotation not configured | Use `filesize` and `filecount` |
| Logs get overwritten | Rotation disabled or colliding filenames | Use PID/timestamp and configure rotation |
| Cannot write log file | JVM lacks permissions or directory missing | Check owner, permissions, and disk space |
| Dynamic logs do not appear | Wrong `jcmd` PID/user or unsupported command | Use `jcmd -l`, `help VM.log`, and the same user account |
| Long GC duration but short pauses | Collector is performing concurrent work | Distinguish `Concurrent Mark Cycle` from `Pause` |
| Safepoint time differs from GC pause | Safepoint caused by a non-GC VM operation | Correlate timestamps, tags, and operations |
| Post-GC heap grows | Live set growth or workload change | Compare multiple cycles under equivalent workload; check retention |
| Logs do not match app timestamps | Only `uptime` enabled or clock skew across hosts | Enable `time`/`utctime`, `pid`, and align with application timestamps |

## 15. Workflow for Investigating GC Using Logs

1. Record the JDK version, JVM vendor, collector, min/max heap, and container limits.
2. Start with `-Xlog:gc*=info` and write to a file with rotation.
3. Include `time`, `uptime`, `pid`, and `tags` to correlate with application logs.
4. Identify abnormal collections by GC ID, cause, and timestamp.
5. Compare heap before/after and Eden/Survivor/Old Gen regions if available.
6. Read pause durations, concurrent phases, and safepoints.
7. If needed, enable `gc+heap=debug`, `gc+phases=debug`, or `gc+ergo=debug` for a short window.
8. Use `jcmd VM.log list` to verify configuration; adjust dynamically with `VM.log` when appropriate.
9. Correlate with JFR, application latency, CPU, container metrics, and deployments.
10. If retention is suspected, capture a heap dump and analyze it with MAT.
11. Change one GC setting at a time, re-run an equivalent workload, and compare.
12. Retain logs according to retention policy, protect sensitive data, and disable verbose selectors after investigation.

Do not tune a collector based solely on a single Full GC line or one long pause. Determine whether the issue stems from allocation rate, live set growth, pause phases, CPU contention, or resource limits.

## 16. Takeaways

- GC logs in Java 9+ use Unified Logging via `-Xlog`.
- `-Xlog:gc` logs GC summaries; `-Xlog:gc*` includes all tag sets containing `gc`.
- `+` combines tags with AND; `,` separates independent selectors; `*` expands matching tag sets.
- `info`, `debug`, and `trace` increase verbosity; `trace` can produce very large logs.
- Output can target `stdout`, `stderr`, or a file; decorators provide time, PID, level, and tags.
- `filesize`/`filecount` bound log files; `%p`/`%t` prevent filename collisions.
- `GC(n)` links all messages belonging to one collection.
- `Pause Young`/`Pause Full` are stop-the-world pauses; `Concurrent Mark Cycle` does not mean the application is stopped the entire time.
- Heap before/after helps spot trends, but does not identify which objects hold references.
- Safepoint logs include non-GC VM operations as well.
- `jcmd PID VM.log` lets you inspect and update logging configuration on a running JVM.
- Combine GC logs with JFR, heap dumps, MAT, and metrics to find root causes.
- Do not leave `debug`/`trace` running unnecessarily in production; manage disk, rotation, and log access permissions.

Understanding how to select tags, read GC IDs, analyze heap and pause data, and configure rotation enables you to use GC logs for evidence-based JVM diagnostics while keeping application impact under control.

## References

- [The java Command — JDK 24: Unified Logging](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [Garbage-First Garbage Collector Tuning — Java SE 24](https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html)
- [The java Command — JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html)
