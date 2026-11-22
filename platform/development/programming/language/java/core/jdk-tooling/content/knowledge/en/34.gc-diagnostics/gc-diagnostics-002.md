# Enabling GC Logging in Java

GC logging records Garbage Collector (GC) activity in the JVM. The logs show when GC runs, what triggered it, pause durations, heap usage before and after collection, processing phases, and CPU information. This is foundational data when investigating latency spikes, Full GCs, heap growth, allocation pressure, or differences between collectors.

Since JDK 9, Java uses Unified JVM Logging with the `-Xlog` option. On JDK 8, GC logging uses a separate set of flags such as `-XX:+PrintGCDetails`, `-Xloggc`, and rotation flags. You should not copy JDK 8 configurations verbatim to newer JDKs; choose the syntax that matches the actual runtime.

This lesson was tested on Zulu/OpenJDK 24.0.2. The command examples use Java 17+; detailed log output may vary depending on the JDK, collector, and workload.

## 1. What Is GC Logging Used For?

GC logs help answer operational questions:

- How often does GC run, and what types of collections are occurring?
- Which pauses are affecting request latency?
- How much heap is used before and after GC?
- Is Young GC happening too frequently? Are Mixed GCs or Full GCs occurring?
- Are there signs of allocation pressure, humongous allocations, or promotion pressure?
- How much CPU time is GC consuming?
- Are there long safepoints not directly related to GC?
- When changing heap size or collector, does GC behavior change?

Common symptoms and what to look for in the logs:

| Symptom | Log data to focus on |
|---|---|
| Periodic request latency spikes | Pause duration, GC cause, safepoint |
| Repeated Full GCs | `Pause Full`, heap before/after, cause |
| Heap after GC keeps growing | Post-collection occupancy, old generation, allocation |
| Excessively frequent Young GC | Young collection frequency, allocation rate |
| Long G1 Mixed GCs | Mixed collection, phases, region/reclaim |
| Unusually large allocations | Allocation/heap events, humongous regions |
| High CPU usage during GC | GC worker CPU, user/sys/real time |
| Pauses not explained by GC | Safepoint logs and VM operations |

GC logs provide JVM-level evidence. They do not directly identify which objects in source code are creating allocations; combine them with JFR, heap dumps, application metrics, and traces to find the root cause.

## 2. Differences Between JDK 8 and JDK 9+

### JDK 8: Dedicated GC Logging Flags

Common configuration example on HotSpot JDK 8:

~~~text
java -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:/var/log/myapp/gc.log -XX:+UseGCLogFileRotation -XX:NumberOfGCLogFiles=5 -XX:GCLogFileSize=20M -jar application.jar
~~~

Meaning:

- `-XX:+PrintGCDetails`: logs detailed GC information.
- `-XX:+PrintGCDateStamps`: adds date-time timestamps.
- `-Xloggc:<file>`: writes GC logs to a file.
- `-XX:+UseGCLogFileRotation`: enables log file rotation.
- `-XX:NumberOfGCLogFiles=5`: number of files in the rotation set.
- `-XX:GCLogFileSize=20M`: target size per file.

Some JDK 8 builds or JVM vendors have differences in flags and formatting; check `java -XX:+PrintFlagsFinal -version` and the vendor's documentation before deploying.

### JDK 9+: Unified JVM Logging

JDK 9 unified multiple JVM logging subsystems into Unified Logging. GC logging is enabled via `-Xlog`:

~~~text
java -Xlog:gc -jar application.jar
~~~

Equivalent configuration for more detailed GC logging:

~~~text
java -Xlog:gc*=info -jar application.jar
~~~

Unified Logging lets you configure tags, log levels, output, decorators, and rotation in a single expression. This is the recommended syntax for JDK 9 and later.

### Concept Mapping Table

| JDK 8 | Unified Logging |
|---|---|
| `-verbose:gc` | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | `-Xlog:gc*` |
| `-XX:+PrintGCDateStamps` | `time` or `utctime` decorator |
| `-XX:+PrintGCTimeStamps` | `uptime` decorator |
| `-Xloggc:<file>` | `file=<file>` in `-Xlog` |
| `-XX:+UseGCLogFileRotation` | `filecount=<n>` |
| `-XX:NumberOfGCLogFiles=<n>` | `filecount=<n>` |
| `-XX:GCLogFileSize=<size>` | `filesize=<size>` |

This table shows how to translate configuration intent. Log line formats and event contents are not identical between the two generations. On newer JDKs, use `-Xlog` instead of relying on legacy flags.

## 3. Structure of the `-Xlog` Option

General syntax:

~~~text
-Xlog[:[selections][:[output][:[decorators][:output-options]]]]
~~~

It can be read in four parts:

1. `selections`: selects the tags and levels to log.
2. `output`: writes to `stdout`, `stderr`, or a file.
3. `decorators`: additional metadata prepended to each log line.
4. `output-options`: file options, such as rotation.

Example:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

This command selects tag combinations containing `gc`, logs up to the `info` level, writes to `gc.log`, adds time/uptime/level/tags decorators, and rotates across five files with a target size of 20 MB each.

To view the syntax, tags, levels, and decorators available in your runtime:

~~~text
java -Xlog:help
~~~

The available tag list can vary by version and build. When a selector does not work, check the help output of the exact `java` binary used to run the application.

## 4. Tags, Wildcards, and Log Levels

Unified Logging categorizes messages using tags. A message can carry multiple tags, such as `gc,heap`, `gc,phases`, or `gc,cpu`.

### 4.1. Selecting Tags

| Selector | Meaning |
|---|---|
| `gc` | Only messages with the exact tag combination `gc` |
| `gc+heap` | Messages with both `gc` and `heap` tags |
| `gc+phases` | Messages with both `gc` and `phases` tags |
| `gc+ergo` | GC ergonomics messages |
| `gc+ref` | Reference processing messages |
| `safepoint` | Safepoint messages |
| `gc*` | Tag combinations containing the `gc` tag, including extended combinations |

The `+` operator requires all specified tags to be present together. A comma between selectors specifies independent selections.

Example logging GC and safepoints:

~~~text
-Xlog:gc,safepoint
~~~

Example logging only GC heap details:

~~~text
-Xlog:gc+heap=debug
~~~

Example logging GC phases and ergonomics:

~~~text
-Xlog:gc+phases=debug,gc+ergo=debug
~~~

### 4.2. Log Levels

JDK 24.0.2 provides the following levels:

| Level | Meaning |
|---|---|
| `off` | Disables the selector |
| `trace` | Very high detail |
| `debug` | Information for deep investigation |
| `info` | Standard operational information |
| `warning` | Warnings |
| `error` | Errors |

If no level is specified, the default is `info`. Higher detail levels such as `debug` and `trace` can generate large volumes of data, so enable them selectively and for limited durations.

Examples:

~~~text
-Xlog:gc*=info
-Xlog:gc+heap=debug
-Xlog:gc+phases=trace
~~~

`-Xlog:gc*=debug` can be very verbose. Do not enable all tags at `trace` in production long-term without evaluating disk usage and overhead.

## 5. Writing GC Logs to the Console

Simplest form:

~~~text
java -Xlog:gc -jar application.jar
~~~

Logs are written to `stdout` by default. You can explicitly specify the output:

~~~text
java -Xlog:gc=info:stdout -jar application.jar
~~~

Or write to `stderr`:

~~~text
java -Xlog:gc=info:stderr -jar application.jar
~~~

Console logging is useful when running in containers and deployment platforms that collect `stdout`/`stderr` into a logging platform. Check log driver settings, retention limits, multiline parsing, and storage costs.

If the application runs under a service manager, container runtime, or Kubernetes, ensure GC logs are aggregated into centralized observability and searchable by pod, container, process, or instance.

## 6. Writing GC Logs to a File

Basic production example:

~~~text
java -Xms512m -Xmx512m -Xlog:gc*=info:file=/var/log/myapp/gc.log:time,uptime,level,tags -jar application.jar
~~~

You can use a per-process filename:

~~~text
java -Xlog:gc*=info:file=/var/log/myapp/gc-%p-%t.log:time,uptime,level,tags -jar application.jar
~~~

Filename placeholders:

- `%p`: JVM PID.
- `%t`: JVM startup timestamp.
- `%hn`: hostname.

The target directory must exist, and the user running the JVM must have write permissions. On Windows, use a valid local path and avoid the `:` delimiter inside the selector/output configuration. For paths containing spaces, verify quoting according to your shell and launcher.

If running multiple JVMs on the same host, include the PID or hostname to prevent processes from writing to the same file. If using containers with ephemeral filesystems, configure volumes and file collection policies before deploying.

## 7. Decorators: Adding Time and Context

Decorators are metadata prepended to each log line.

| Decorator | Information |
|---|---|
| `time` | Local date and time |
| `utctime` | UTC date and time |
| `uptime` | Time elapsed since JVM startup |
| `timemillis` | Epoch time in milliseconds |
| `uptimemillis` | Uptime in milliseconds |
| `timenanos` | Epoch time in nanoseconds |
| `uptimenanos` | Uptime in nanoseconds |
| `hostname` | Hostname |
| `pid` | Process ID |
| `tid` | Thread ID |
| `level` | Message level |
| `tags` | Tag combination |

Example:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,pid,level,tags
~~~

`time` helps correlate with application logs, alerts, and incident timelines. `uptime` is useful for comparing events within the same JVM lifecycle without being affected by system clock changes.

You can omit all decorators:

~~~text
-Xlog:gc=debug:file=gc.log:none
~~~

In production, keep at least timestamp, uptime, level, and tags. If multiple JVMs write logs to a shared system, PID or hostname helps distinguish the source.

## 8. File Rotation to Bound Disk Usage

GC logs should not grow unbounded on production volumes. Unified Logging supports file rotation:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Meaning:

- `filesize=20M`: target size before automatic rotation.
- `filecount=5`: number of rotated files retained, excluding the active file.
- The active file continues receiving logs after rotation.

When the file reaches the target size, the JVM rotates it and continues writing. Actual file size may slightly exceed the threshold due to chunked writes and rotation check timing.

Key notes:

- `filecount=0` disables rotation; old files may be overwritten.
- `filesize=0` disables automatic rotation, though manual rotation is still possible via `VM.log`.
- Choose file count and size based on log generation rate, required retention window, and volume capacity.
- If a log shipper reads files by name, verify how it tracks files across rotations.
- Do not let both local rotation and a log shipper delete files without aligning retention policies.

You can combine PID and timestamp placeholders with rotation:

~~~text
-Xlog:gc*=info:file=gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

## 9. Common GC Logging Configurations

### 9.1. Production Baseline

~~~text
-Xlog:gc*=info,safepoint=info:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Logs GC events and safepoints at `info` level with timestamp, uptime, and rotation. This is a solid starting point for long-term observation of GC behavior.

### 9.2. Heap Investigation

~~~text
-Xlog:gc*=info,gc+heap=debug:file=gc-heap.log:time,uptime,level,tags:filecount=5,filesize=50M
~~~

Adds heap details to understand occupancy and region/generation behavior by collector.

### 9.3. GC Phase Investigation

~~~text
-Xlog:gc*=info,gc+phases=debug,gc+ergo=debug:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=50M
~~~

Used when you need to understand time spent in individual phases or JVM ergonomics decisions. This configuration generates more log volume than the baseline.

### 9.4. Reference Processing Investigation

~~~text
-Xlog:gc+ref=debug:file=gc-ref.log:uptime,level,tags:filecount=3,filesize=20M
~~~

Used when soft/weak/phantom reference processing or reference queues are suspected of impacting GC time.

### 9.5. Safepoints Only

~~~text
-Xlog:safepoint=info:file=safepoint.log:time,uptime,level,tags:filecount=5,filesize=10M
~~~

Useful when observed pauses are not fully explained by GC pause events.

There is no need to enable all configurations at once. Start from the baseline, identify the question you need to answer, and raise the log level for the relevant tags.

## 10. Reading a GC Log Line

Example of an actual line captured from Zulu/OpenJDK 24.0.2:

~~~text
[0.842s][info][gc             ] GC(4) Pause Full (System.gc()) 6M->1M(32M) 2.290ms
~~~

How to read it:

- `[0.842s]`: JVM uptime when the line was logged.
- `[info]`: message level.
- `[gc]`: tag.
- `GC(4)`: collection ID; lines with the same ID belong to the same event/processing sequence.
- `Pause Full`: collection and pause type.
- `(System.gc())`: reported cause.
- `6M->1M`: heap usage before and after collection.
- `(32M)`: heap capacity recorded at the event.
- `2.290ms`: duration of the pause event.

An accompanying CPU line may appear:

~~~text
[0.842s][info][gc,cpu] GC(4) User=0.00s Sys=0.00s Real=0.00s
~~~

- `User`: CPU time in user mode.
- `Sys`: CPU time in kernel mode.
- `Real`: elapsed wall-clock time.

With parallel GC, total `User` time can exceed `Real` time because multiple workers run concurrently. `Real` is usually close to the observed duration, though it should be cross-checked with pause and safepoint events.

The format above is an example from a specific version and collector. Do not assume every collector or JDK prints the exact same text.

## 11. Distinguishing GC Event Types

### G1 GC

G1 typically logs messages such as:

- `Pause Young`: young collection.
- `Pause Young (Concurrent Start)`: young pause that initiates a concurrent cycle.
- `Pause Remark`: remark pause during the concurrent marking cycle.
- `Pause Cleanup`: cleanup pause.
- `Pause Mixed`: mixed collection processing both young and a subset of old regions.
- `Pause Full`: Full GC.

When investigating G1, examine pause duration, region counts, humongous allocations, mixed collections, and evacuation/marking phases. A long series of Mixed GCs does not necessarily have the same root cause as a Full GC.

### Parallel GC

The Parallel collector typically logs young/full collections with causes such as allocation failure. Check frequency, pause duration, heap before/after, and worker CPU.

### ZGC and Concurrent Collectors

Concurrent collectors have their own cycles and phases. Much of the work runs concurrently with application threads, so total cycle time does not equal application pause time. Examine individual pause events, cycle phases, and the JDK version.

Event names, tags, and detail levels vary by collector and JDK. Use `java -Xlog:help` and a representative recording from your own environment to confirm available tags.

## 12. Safepoint Logs and Application Pauses

GC pauses typically occur at safepoints, but not every safepoint is a GC. The JVM can stop threads for many other VM operations.

Enable safepoint logging:

~~~text
-Xlog:safepoint=info
~~~

It can be combined with GC logs:

~~~text
-Xlog:gc*=info,safepoint=info:file=gc-safepoint.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

When a latency spike occurs:

1. Find the corresponding time window in application logs/metrics.
2. Look for GC events near the same timestamp.
3. Compare pause duration against request latency.
4. If there is no matching GC pause, inspect safepoint events and VM operations.
5. Correlate with thread dumps or JFR when you need to see which threads were affected.

Do not sum the durations of all phase lines to calculate total pause time. Many phases are nested or run in parallel; use the overall pause event and safepoint timing for comparison.

## 13. Changing GC Logging at Runtime with `jcmd`

Since JDK 9, Unified Logging can be configured at runtime using the `VM.log` diagnostic command, provided the target JVM supports attach and permissions allow it.

List the current log configuration:

~~~text
jcmd <PID> VM.log list=true
~~~

View command help:

~~~text
jcmd <PID> help VM.log
~~~

Dynamically enable GC logging to a file:

~~~text
jcmd <PID> VM.log what=gc*=debug output=file=gc-live.log decorators=uptime,level,tags output_options=filecount=3,filesize=20M
~~~

In this example:

- `what=gc*=debug`: enables GC tag combinations at `debug` level.
- `output=file=gc-live.log`: creates the log file in the JVM's working directory.
- `decorators=uptime,level,tags`: adds uptime, level, and tags.
- `output_options=filecount=3,filesize=20M`: limits file rotation.

Verify the configuration:

~~~text
jcmd <PID> VM.log list=true
~~~

Manually rotate log outputs:

~~~text
jcmd <PID> VM.log rotate=true
~~~

`VM.log` can also configure `stdout` or `stderr` outputs. Parameters and capabilities vary by JDK version. JDK 8 does not use Unified Logging/`VM.log` in this way; on JDK 8, GC logging options generally must be set at JVM startup.

If you need to stop or modify a specific output, read `jcmd <PID> help VM.log` on the target JVM and identify the output index before making changes. Avoid using `disable=true` indiscriminately, as it removes all logging configuration.

## 14. Java 17+ Example: Creating Rotating GC Logs

Create `GcLoggingDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class GcLoggingDemo {
    private GcLoggingDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("GC_LOG_DEMO_READY");

        for (int round = 0; round < 10; round++) {
            List<byte[]> retained = new ArrayList<>();

            for (int i = 0; i < 16; i++) {
                retained.add(new byte[256 * 1024]);
            }

            retained.clear();
            System.gc();
            Thread.sleep(200);
        }

        System.out.println("GC_LOG_DEMO_DONE");
    }
}
~~~

Compile:

~~~text
javac --release 17 GcLoggingDemo.java
~~~

Run with a small heap and GC logging to a rotating file:

~~~text
java -Xms32m -Xmx32m -Xlog:gc*=info:file=gc.log:uptime,level,tags:filecount=3,filesize=8k GcLoggingDemo
~~~

Program stdout:

~~~text
GC_LOG_DEMO_READY
GC_LOG_DEMO_DONE
~~~

After running, check the generated files:

~~~text
dir gc.log*
~~~

You can inspect part of the log:

~~~text
type gc.log
~~~

In a test run on Zulu/OpenJDK 24.0.2, the output contained `gc.log` and `gc.log.0`, confirming rotation worked. One captured line:

~~~text
[0.842s][info][gc             ] GC(4) Pause Full (System.gc()) 6M->1M(32M) 2.290ms
~~~

Actual timestamps, GC IDs, heap occupancy, and file counts vary by run and environment. `System.gc()` is used here only in a lab to produce easily observable events; do not add it to production applications to force GC.

## 15. Analyzing GC Logs by Operational Question

### Pause Time and Latency

Track pause durations and P50/P95/P99 distributions across GC events. A few long pauses can hurt tail latency even when average GC time is low. Compare timestamps against request latency and SLOs.

### Heap Before/After GC

Observe post-collection occupancy over time. If heap after GC rises steadily across multiple cycles, investigate retained objects, caches, queues, or object lifetimes. A single increase in post-GC heap is not enough to conclude a memory leak.

### Allocation Pressure

Frequent Young GCs can reflect a high allocation rate. Combine with JFR allocation events or application profiling to find the classes/methods allocating heavily. GC logs alone usually do not reveal the full call site.

### Full GC

Repeated Full GCs require investigating the cause: allocation failure, promotion failure, explicit GC, metadata pressure, or collector-specific conditions. Inspect the cause, heap before/after, phases, and the logs immediately preceding the Full GC.

### Humongous Allocations with G1

G1 can log region/humongous allocation details. Large objects occupy multiple contiguous regions and can increase heap pressure. Check object sizes, allocation sites, and region settings; do not change heap size or collector based on a single log line.

### CPU and Safepoints

Compare `User`, `Sys`, `Real`, and safepoint durations. If application pauses are longer than GC pauses, investigate safepoint synchronization or other VM operations. If `User` is high, GC workers may be consuming significant CPU even when wall-clock pause time is lower.

## 16. Combining GC Logging with JFR and Metrics

Each tool answers a different class of questions:

| Tool | Best-suited questions |
|---|---|
| GC log | When did GC run, what type/cause, how long was the pause, and how did heap change? |
| JFR | Which threads, allocation samples, locks, I/O, and events occurred at the same time? |
| Heap dump | Which objects are retaining heap, and what are their reference chains? |
| Application metrics | How did request latency, throughput, queue depth, and error rate change? |
| Distributed tracing | Which services/databases did a request hit, and which span was slow? |

An investigation workflow:

1. Use GC logs to identify timestamps and pause types.
2. Locate the same time window in JFR.
3. Inspect allocations, execution samples, thread parks, and lock events.
4. Correlate with application metrics and traces.
5. If post-GC occupancy remains high over time, consider taking a heap dump following data-protection procedures.
6. Form a specific hypothesis and change one variable at a time.

GC logging should stay enabled continuously at a reasonable level so you have pre-incident history. JFR can run a default recording to provide deeper context when needed.

## 17. Deploying GC Logging in Services, Containers, and Kubernetes

### Bare-Metal / VM Services

Place JVM options in the startup script or service configuration. Verify that the user running the JVM has write permissions to the log directory and that rotation does not conflict with the log shipper.

### Containers

If logs are collected from `stdout`/`stderr`, use:

~~~text
-Xlog:gc*=info,safepoint=info:stdout:time,uptime,level,tags
~~~

If writing files inside a container, mount a volume with appropriate capacity and retention. A container's local filesystem may be wiped when the pod/container is replaced.

### Kubernetes

You can direct logs to `stdout` for collection by the container runtime. Ensure the log collector parses timestamps, preserves pod/container metadata, and does not drop multiline GC lines. If using file output, mount a volume and configure a sidecar/agent to collect rotated files.

In every environment, calculate disk budget based on the number of JVMs, hourly log volume, retention days, and rotated file count. Do not assume a single `filesize` fits every workload.

## 18. Troubleshooting

### `Unrecognized VM option '-Xlog...'`

**Cause:** running on JDK 8 or a runtime that does not support Unified Logging.

**Resolution:** check `java -version`. For HotSpot JDK 8, use legacy GC logging flags; for JDK 9+, use `-Xlog`.

### No GC Logs Appearing

**Cause:** wrong selector, unwritable output path, logs going to a different `stdout`/`stderr`, or the workload has not triggered GC yet.

**Resolution:** test `-Xlog:gc` first, check `java -Xlog:help`, directory permissions, and the actual JVM command line.

### Log File Not Created

**Cause:** directory does not exist, insufficient write permissions, invalid path, or the JVM exits before opening the output.

**Resolution:** create the directory before startup, verify service user permissions, and test with a relative filename in a controlled working directory.

### Rotation Not Happening

**Cause:** file has not reached `filesize`, `filecount=0`, or the output configuration omits file rotation options.

**Resolution:** check `VM.log list=true`, test with a small file size in a lab to confirm, then choose a size suited for production.

### Logs Too Large

**Cause:** `gc*=debug`/`trace` enabled, too many tags, high-allocation workload, or rotation not configured.

**Resolution:** revert to `gc*=info`, enable only necessary tags, bound `filecount`/`filesize`, and configure retention in the log platform.

### GC Pauses in Logs Do Not Match Request Latency

**Cause:** unsynchronized timestamps, requests running on a different JVM, or latency caused by I/O, locks, or other safepoints.

**Resolution:** add `time` and `uptime`, correlate trace IDs, JFR, and safepoint logs. Check timezone settings in the centralized logging system.

### Confusion Over Heap Before/After

**Cause:** confusing post-collection heap capacity with `-Xmx`, or comparing different collectors/phases.

**Resolution:** read the capacity printed on the same line, check `-Xms`/`-Xmx`, the collector, and related events. Use heap metrics to track trends.

### Cannot Change Logging at Runtime with `jcmd`

**Cause:** JDK does not support Unified Logging, attach is disabled, different user/PID namespace, or the command is unavailable on the target.

**Resolution:** run `jcmd <PID> help VM.log`, verify attach permissions and the correct PID. If unsupported, configure logging at JVM startup.

### GC Logs Lack Enough Detail to Find Allocation Sites

**Cause:** GC logs focus on collections and heap usage, not full call sites for every allocation.

**Resolution:** use JFR allocation profiling or an appropriate profiler; if a memory leak is suspected, use a heap dump and retained-size analysis.

## 19. Production GC Logging Checklist

- [ ] Verified JDK vendor and version.
- [ ] Selected the right syntax: JDK 8 legacy flags or JDK 9+ `-Xlog`.
- [ ] Enabled baseline `gc*=info` and safepoints if needed.
- [ ] Selected `stdout`/`stderr` or file output to match log collection.
- [ ] Added timestamp, uptime, level, and tags decorators.
- [ ] Configured `filecount` and `filesize` when writing to files.
- [ ] Verified log directory exists and JVM user has write permissions.
- [ ] Calculated disk budget, rotation, and retention.
- [ ] Confirmed log shipper handles rotated files or `stdout` properly.
- [ ] Tested the configuration in staging under a representative workload.
- [ ] Know how to read GC ID, cause, heap before/after, and pause duration.
- [ ] Enable detailed tags only when investigating a specific hypothesis.
- [ ] Know how to inspect/change runtime logging via `jcmd VM.log` if supported by the JDK.
- [ ] Synchronized timestamps for correlation with application logs and metrics.
- [ ] Established procedures for securing and retaining logs per operational policy.

## 20. References

- Oracle JDK 24 — `java` Command, Unified Logging section: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — `jcmd` Command and diagnostic commands: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- OpenJDK JEP 158 — Unified JVM Logging: https://openjdk.org/jeps/158
- OpenJDK JEP 271 — Unified GC Logging: https://openjdk.org/jeps/271
- Oracle JDK 24 — Java Garbage Collection Tuning Guide: https://docs.oracle.com/en/java/javase/24/gctuning/

Enable GC logging using the syntax appropriate for your JDK version, choose tags and levels based on your goal, add timestamps, and bound disk usage with rotation. Use GC logs to find timing, causes, and pauses; combine them with JFR, metrics, and tracing when you need to determine why an application is creating memory pressure or slowing down.