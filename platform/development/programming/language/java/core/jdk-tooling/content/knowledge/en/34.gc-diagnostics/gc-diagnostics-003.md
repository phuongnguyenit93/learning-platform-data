# Reading and Configuring GC Log Formats in the JVM

## 1. What is a GC log?

A GC log is a log recorded by the JVM for Garbage Collection (GC) activities, including when a collection starts, collection type, cause, phases, heap usage before/after GC, pause duration, and CPU information. With a collector like G1, the log can also contain Eden/Survivor/Old region counts, metaspace status, evacuation details, and heap resizing decisions.

GC logs help answer operational questions:

- How often do Young GC or Full GC events occur, and how far apart are they?
- How many milliseconds does each pause last?
- How much does the heap decrease after a collection?
- Does the Old generation continue to grow after GC?
- Does GC suffer evacuation failures or allocation pressure?
- Is the impacted time spent in GC pauses, safepoints, or application activity?
- Which collector is the JVM using, and how is the heap configured?

A GC log is a time-ordered sequence of events. To investigate accurately, you need to read multiple lines belonging to the same GC event and compare multiple consecutive events. A single line or a single snapshot is rarely enough to conclude whether there is a memory leak or whether GC is the cause of slowness.

## 2. Unified Logging from JDK 9 Onward

Starting with JDK 9, HotSpot uses Unified JVM Logging to configure many log groups via the `-Xlog` option. GC logging is one tag group in this system.

Example enabling basic GC logging:

~~~bash
java -Xlog:gc -jar app.jar
~~~

Write all tag sets containing `gc` at the `info` level to a file:

~~~bash
java -Xlog:gc*=info:file=gc.log:time,uptime,level,tags -jar app.jar
~~~

In JDK 24.0.2, `java -Xlog:help` lists the syntax, levels, decorators, tags, outputs, and rotation options. The set of tags and log content can vary by JDK, vendor, and garbage collector.

With Java 8, a common configuration is:

~~~bash
java -XX:+PrintGCDetails -XX:+PrintGCDateStamps -Xloggc:gc.log -jar app.jar
~~~

These legacy flags belong to the GC logging system prior to Unified Logging. When running JDK 9+, use `-Xlog` to explicitly select tags, levels, decorators, and output. Do not mix Java 8 flags with Unified Logging syntax without checking the runtime in use.

## 3. General Syntax of -Xlog

Syntax:

~~~text
-Xlog[:[selections][:[output][:[decorators][:output-options]]]]
~~~

Components:

| Component | Meaning |
|---|---|
| `selections` | Selects the tag sets and log levels to record. |
| `output` | Destination for the log: stdout, stderr, or file. |
| `decorators` | Metadata prepended to each line, such as timestamp, uptime, level, tags. |
| `output-options` | Options for file output such as rotation size and file count. |

Example:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

You can read this in order:

1. `gc*=info`: selects logs with the `gc` tag at level `info` and above in severity.
2. `file=gc.log`: writes to the file gc.log.
3. `time,uptime,level,tags`: adds timestamp, uptime, level, and tags.
4. `filecount=5,filesize=20M`: keeps up to five rotated files, with a target size of 20 MB per file.

If the output part is omitted, logs go to stdout by default. If decorators are omitted, the JVM uses the default Unified Logging decorators.

## 4. Tags, Tag Sets, and Wildcards

Tags identify the content group of a log message. Examples:

- `gc`: general GC activity.
- `heap`: heap information.
- `phases`: phases within a collection.
- `ergo`: JVM ergonomic decisions.
- `ref`: reference processing.
- `metaspace`: class metadata.
- `cpu`: CPU metrics.
- `safepoint`: safepoint activity.
- `init`: GC and heap initialization information.

There are two common ways to combine tags:

**The plus sign (`+`) requires all specified tags to appear together in the tag set.**

~~~bash
-Xlog:gc+heap=debug
~~~

This configuration selects logs carrying the `gc` and `heap` tag set. Without a wildcard, only exact tag set matches are selected.

**The asterisk (`*`) is a wildcard for tag sets containing the specified tag.**

~~~bash
-Xlog:gc*=info
~~~

This configuration selects every tag set that contains `gc`, such as `gc`, `gc,heap`, `gc,phases`, or `gc,metaspace`.

Commas separate independent selections. Example:

~~~bash
-Xlog:gc*=info,safepoint*=info
~~~

This selects both the GC log group and the safepoint log group. When analyzing pauses, viewing both groups together is often useful.

Do not confuse `gc+heap` with `gc*`: one selects a specific tag set, while the other covers multiple tag sets containing `gc`.

## 5. Log Levels

Unified Logging supports the following levels:

| Level | Purpose |
|---|---|
| `off` | Disables logging for the selection. |
| `error` | Critical errors. |
| `warning` | Warnings. |
| `info` | General operational information. |
| `debug` | Details for investigation. |
| `trace` | Very deep details. |

The selected level sets the maximum verbosity threshold recorded. For example, `info` includes info, warning, and error; `debug` includes debug along with more severe levels. `trace` generates much larger log volumes and can cause files to grow quickly.

Examples:

~~~bash
# Standard GC summary
-Xlog:gc=info

# Heap details
-Xlog:gc+heap=debug

# Phase details
-Xlog:gc+phases=debug

# Collector decisions
-Xlog:gc+ergo=debug

# Safepoint
-Xlog:safepoint=info
~~~

Start with `info` for general monitoring. Only increase to `debug` or `trace` once you have identified what additional detail you need to investigate.

## 6. Decorators: Reading Line-Prefix Metadata

Decorators add context before the log message content:

| Decorator | Meaning |
|---|---|
| `time` | Date and time in the system timezone. |
| `utctime` | Date and time in UTC. |
| `uptime` | Time since JVM startup, in seconds. |
| `timemillis` | Epoch time in milliseconds. |
| `uptimemillis` | Uptime in milliseconds. |
| `timenanos` | Epoch time in nanoseconds. |
| `uptimenanos` | Uptime in nanoseconds. |
| `hostname` | Hostname. |
| `pid` | Process ID. |
| `tid` | Thread ID. |
| `level` | Log level. |
| `tags` | Tag set of the log event. |

Example:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags
~~~

A log line might start like this:

~~~text
[2026-11-10T20:10:29.474+0700][0.161s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
~~~

How to read it:

- `2026-11-10T20:10:29.474+0700`: timestamp in the system timezone.
- `0.161s`: the JVM has been running for about 0.161 seconds.
- `info`: log level.
- `gc,start`: tag set.
- Everything after the brackets is the event content.

If you need to compare logs across multiple machines in different timezones, use `utctime` or synchronize timezones before analyzing. If you need to correlate logs with metrics by JVM runtime, `uptime` is very helpful.

You can omit all decorators using `none`:

~~~bash
-Xlog:gc=info:stdout:none
~~~

The log then contains only the message content, which is easier to read in some situations but loses timestamp and tag context.

## 7. Choosing Output: stdout, stderr, or File

Log to console:

~~~bash
-Xlog:gc*=info:stdout:uptime,level,tags
~~~

Log to stderr:

~~~bash
-Xlog:gc*=info:stderr:uptime,level,tags
~~~

Log to a file:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags
~~~

For server applications, writing to a separate file is usually more convenient because:

- It avoids mixing GC logs with application logs.
- Retention and rotation can be configured independently.
- Files are easier to collect for investigation.
- It is easier to search GC lines by tag, uptime, or GC ID.

Ensure the directory already exists and the user running the JVM has write permission. Relative paths are resolved against the process working directory; use absolute paths when a service does not have a fixed working directory.

File names support placeholders:

- `%p` is replaced by the JVM PID.
- `%t` is replaced by the JVM startup timestamp.
- `%hn` is replaced by the hostname.

Example:

~~~bash
-Xlog:gc*=info:file=gc-%p-%t-%hn.log:time,uptime,level,tags
~~~

Placeholders prevent multiple JVMs from writing to the same file name when running in a shared directory.

## 8. Rotation: Limiting File Size and Count

If GC logs are allowed to grow unbounded, they can fill up the disk. Unified Logging supports size-based rotation:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Meaning:

- `filesize=20M`: target size before triggering rotation.
- `filecount=5`: keeps up to five rotated files, not counting the active file.
- `filecount=0`: disables rotation; old log files may be overwritten when the output is opened.
- `filesize=0`: disables automatic size-based rotation; manual rotation can still be triggered using diagnostic commands.

An example fileset might look like:

~~~text
gc.log
gc.log.0
gc.log.1
gc.log.2
gc.log.3
gc.log.4
~~~

When the active file reaches the threshold, the JVM rotates the older files and continues writing to a new file. The threshold is a target size; a file may slightly exceed it depending on check timing and log record size.

You can use `K`, `M`, or `G` suffixes. Choose limits based on allocation/GC rate, required history retention, and disk space allocated to the application.

If manual rotation is needed, use `jcmd PID VM.log rotate=true`. This rotates all log outputs that support rotation for that JVM.

## 9. General Production GC Log Configuration

A common configuration that is sufficient for investigating most initial GC issues:

~~~bash
java -Xms512m -Xmx2g \
  -Xlog:gc*=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

This configuration:

- Records all tag sets containing `gc`.
- Records `info` level and more severe levels.
- Includes timestamp, uptime, level, and tags.
- Writes to a file containing the PID and startup timestamp.
- Rotates at a 20 MB threshold, keeping five old files.

You can also include safepoints:

~~~bash
java -Xms512m -Xmx2g \
  -Xlog:gc*=info,safepoint*=info:file=logs/jvm-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
~~~

Using a single file makes it easy to compare GC events with safepoints. If you want to separate the two groups for collection or separate retention, configure separate outputs and verify the command line using `-Xlog:help`.

## 10. Enabling Detailed Logs for Investigation

When general GC logs indicate a problem, increase detail in the specific area you need to inspect.

### Heap and regions

~~~bash
-Xlog:gc+heap=debug
~~~

Used to view heap status and region changes per collection. With G1, the log can show Eden, Survivor, Old, and Humongous regions before/after GC.

### Phases

~~~bash
-Xlog:gc+phases=debug
~~~

Used to inspect the duration of individual phases, such as evacuation, merge roots, or post-evacuation. If total pause time is high, a phase breakdown helps identify which step consumes the most time.

### Collector decisions

~~~bash
-Xlog:gc+ergo=debug
~~~

Used to inspect JVM self-tuning decisions such as generation sizing, worker count, or collection selection.

### Reference processing

~~~bash
-Xlog:gc+ref=debug
~~~

Used when you suspect SoftReference, WeakReference, FinalReference, or PhantomReference processing is contributing to GC time.

### Metaspace

~~~bash
-Xlog:gc+metaspace=info
~~~

Used to inspect metadata information and the impact of class unloading on memory.

You can combine multiple groups in a single command:

~~~bash
-Xlog:gc*=info,gc+phases=debug,gc+heap=debug
~~~

Enabling `debug` across many tag sets can cause logs to grow rapidly. Start with a narrow group and turn off detailed logging once you have collected enough data.

## 11. Understanding GC ID and Correlating Multi-Line Logs

A single collection can produce multiple lines with the same GC ID:

~~~text
[0.161s][info][gc,start] GC(0) Pause Young (Normal) (G1 Evacuation Pause)
[0.163s][info][gc,phases] GC(0)   Evacuate Collection Set: 1.67ms
[0.163s][info][gc,heap] GC(0) Eden regions: 17->0(5)
[0.163s][info][gc,heap] GC(0) Survivor regions: 0->3(3)
[0.163s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->15M(32M) 2.242ms
~~~

`GC(0)` is the collection ID within the JVM. Lines sharing the same ID describe different aspects of the same event. The ID increments within the process and is useful for correlating start, phases, heap, and summary lines.

Do not compare GC IDs across JVM restarts as a global identifier. After a restart, the counter can reset.

An opening line typically states the collection type and cause. The summary line typically contains heap before/after values and pause duration. The lines in between provide phase, region, metaspace, and worker details.

## 12. Reading the Pause Summary Line

Example:

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->15M(32M) 2.242ms
~~~

Interpretation:

| Part | Meaning |
|---|---|
| `Pause Young` | This is a young collection pause. |
| `Normal` | Collection classification by the collector. |
| `G1 Evacuation Pause` | G1 performed an evacuation pause. |
| `17M` | Heap used before the collection. |
| `15M` | Heap used after the collection. |
| `(32M)` | Heap capacity at the time of logging. |
| `2.242ms` | Pause duration reported for the event. |

General form:

~~~text
before->after(capacity) pause-duration
~~~

These are overall heap figures for the event. Do not use them to infer the exact live set of each individual generation. For other collectors, the summary content and wording may differ.

A short pause does not automatically mean GC has no impact. Check frequency, total pause time, request latency, and how long the application is stopped.

## 13. Reading Phases, Heap Regions, and CPU

### Phase duration

Example:

~~~text
GC(0)   Pre Evacuate Collection Set: 0.04ms
GC(0)   Merge Heap Roots: 0.01ms
GC(0)   Evacuate Collection Set: 1.67ms
GC(0)   Post Evacuate Collection Set: 0.16ms
GC(0)   Other: 0.13ms
~~~

Phase durations help pinpoint which part takes the most time. In this example, evacuation accounts for most of the time among the listed phases. The sum of phases may not match the total pause exactly due to measurement boundaries, rounding, and other overhead.

### Region changes in G1

~~~text
GC(0) Eden regions: 17->0(5)
GC(0) Survivor regions: 0->3(3)
GC(0) Old regions: 2->13
GC(0) Humongous regions: 0->0
~~~

Example breakdown:

- Eden decreased from 17 regions to 0, with a target capacity shown as 5.
- Survivor increased from 0 to 3 regions.
- Old increased from 2 to 13 regions due to object promotion or movement.
- Humongous regions remained unchanged.

Region size is determined by the heap configuration. Do not convert region counts to MB without knowing the region size. Initialization logs typically include a `Heap Region Size` line.

### CPU time

Some logs include a line like:

~~~text
GC(0) User=0.00s Sys=0.02s Real=0.00s
~~~

- `User`: CPU time spent in user mode by the participating threads.
- `Sys`: CPU time spent in kernel mode.
- `Real`: elapsed wall-clock time.

For parallel collections, total User time can exceed Real time because multiple workers use CPU simultaneously. Compare CPU time against pause duration, worker count, and system load to understand whether the collection is CPU-bound.

## 14. Distinguishing Young GC, Mixed GC, and Full GC

Collection names in the log depend on the collector:

- **Young GC:** collects the young generation. With G1, this is typically named `Pause Young`.
- **Mixed GC:** G1 collects young regions along with a subset of old regions in the same collection. The log may show `Pause Young (Mixed)`.
- **Full GC:** a whole-heap collection using the collector's full collection mechanism. The log may show `Pause Full`.

Not all collectors use the same names or cycles. For example, G1 has a concurrent marking cycle, mixed collections, and full GC; Serial/Parallel represent collections differently.

A Full GC can be triggered by allocation failure, explicit GC, metadata pressure, or other causes. Check the cause in the log and `gc+ergo` lines to understand the JVM's decision.

Do not conclude that Full GC always means a memory leak. Check heap occupancy after Full GC, recurrence frequency, allocation rate, and object retention.

## 15. Safepoint Logs and GC Pauses

GC pauses usually require the JVM to bring threads to a safepoint. However, not every safepoint is a GC, and not all safepoint time is spent executing GC.

Enable safepoint logging:

~~~bash
-Xlog:safepoint=info
~~~

Record both GC and safepoints:

~~~bash
-Xlog:gc*=info,safepoint*=info:file=jvm.log:time,uptime,level,tags
~~~

Safepoint logs help investigate how long the JVM takes to reach a safepoint and how long it stays inside the safepoint. If the application experiences long pauses while GC phases are short, inspect safepoint transitions and other VM operations.

Do not add every safepoint duration to GC time. Correlate events by timestamp and cause to determine whether a pause comes from GC or another VM operation.

## 16. Configuring GC Logging at Runtime with jcmd

Unified Logging can be changed while the JVM is running without restarting. Use the `VM.log` diagnostic command.

View the current configuration:

~~~bash
jcmd 18420 VM.log list=true
~~~

Enable an additional GC output to a file:

~~~bash
jcmd 18420 VM.log output="file=gc-runtime.log" what="gc*=info" decorators="uptime,level,tags" output_options="filecount=3,filesize=20M"
~~~

Verify the updated configuration:

~~~bash
jcmd 18420 VM.log list=true
~~~

Rotate all log outputs:

~~~bash
jcmd 18420 VM.log rotate=true
~~~

Main options for `VM.log`:

| Option | Meaning |
|---|---|
| `output` | Output name or new output, e.g. `file=gc-runtime.log`. |
| `what` | Tag selection and level to record. |
| `decorators` | Decorators displayed on each line. |
| `output_options` | Rotation and output options. |
| `list=true` | Lists the current log configuration. |
| `rotate=true` | Rotates log outputs. |
| `disable=true` | Disables and clears the entire logging configuration. |

`disable=true` affects the entire JVM logging configuration, not just GC output. Use it only when you intentionally want to disable all log configurations.

Runtime configuration only records events from the moment it is enabled onward; it cannot recover GC events that occurred earlier. In JDK 24.0.2 testing, `VM.log list=true` confirms the new file output, `gc*=info` selection, and rotation options; `rotate=true` performs rotation successfully.

## 17. Rotation and File Management in Practice

Startup configuration example:

~~~bash
-Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Runtime example:

~~~bash
jcmd 18420 VM.log output="file=logs/gc-runtime.log" what="gc*=info" decorators="time,uptime,level,tags" output_options="filecount=5,filesize=20M"
~~~

Operational points:

- Create the log directory before starting or enabling the output.
- Verify write permissions for the user running the JVM.
- Calculate total disk usage based on rotated file count and number of JVM instances.
- Archive old files before rotation removes them if long-term retention is needed.
- Use file names with PID or timestamp when multiple instances write to the same location.
- Synchronize server timezones and clocks to correlate with application logs.
- Do not leave verbose `trace` logging running indefinitely without limits.

Size-based rotation maintains a recent window of history. It does not replace long-term retention policies or log shipping.

## 18. Java 17 Example to Generate GC Logs for Practice

Create `src/GCLogDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GCLogDemo {
    public static void main(String[] args) throws Exception {
        List<byte[]> retained = new ArrayList<>();
        System.out.println("GCLogDemo ready");

        for (int cycle = 1; cycle <= 300; cycle++) {
            for (int i = 0; i < 8; i++) {
                retained.add(new byte[256 * 1024]);
                if (retained.size() > 40) {
                    retained.remove(0);
                }
            }

            if (cycle % 20 == 0) {
                System.gc();
                System.out.println("explicit GC requested at cycle " + cycle);
            }

            Thread.sleep(20);
        }

        System.out.println("GCLogDemo complete");
    }
}
~~~

This program allocates continuously, retains up to 40 arrays, and requests an explicit GC every 20 cycles. The goal is to generate enough activity to observe in the logs. Do not use `System.gc()` as a GC tuning technique in production.

Compile:

~~~bash
mkdir -p out logs
javac --release 17 -g -d out src/GCLogDemo.java
~~~

Run with a 32 MB heap and G1:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC -Xlog:gc*=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=3,filesize=2M -cp out GCLogDemo
~~~

Program stdout:

~~~text
GCLogDemo ready
explicit GC requested at cycle 20
explicit GC requested at cycle 40
explicit GC requested at cycle 60
explicit GC requested at cycle 80
explicit GC requested at cycle 100
explicit GC requested at cycle 120
explicit GC requested at cycle 140
explicit GC requested at cycle 160
explicit GC requested at cycle 180
explicit GC requested at cycle 200
explicit GC requested at cycle 220
explicit GC requested at cycle 240
explicit GC requested at cycle 260
explicit GC requested at cycle 280
explicit GC requested at cycle 300
GCLogDemo complete
~~~

The number and duration of GC events depend on the JDK, collector, heap, machine, and scheduling timing. The stdout above is the program's output; do not assume that every `System.gc()` call guarantees a Full GC.

## 19. Reading Log Files and Filtering Events

Open the file directly in an editor or use filtering commands.

Linux/macOS:

~~~bash
grep -E "Pause Young|Pause Full|System.gc|Metaspace|Humongous" logs/gc-*.log
~~~

Windows PowerShell:

~~~powershell
Select-String -Path logs/gc-*.log -Pattern "Pause Young","Pause Full","System.gc","Metaspace","Humongous"
~~~

Count events by type:

~~~bash
grep -c "Pause Young" logs/gc.log
grep -c "Pause Full" logs/gc.log
~~~

To inspect a specific GC, take the ID from the summary line, such as `GC(135)`, and filter for all lines with that same ID. When reading rotated logs, you may need to search across multiple files.

Do not filter only for summary lines and ignore phase lines. When pauses are long, `gc+phases` and `gc+heap` lines reveal which work took time and how memory regions changed.

Do not write parsers that hardcode column positions or rely on a single log string format. GC log content varies across collectors and JDK versions; if automation is needed, pin the JDK/collector and test the parser against representative logs from each version.

## 20. Analyzing Trends and Warning Signs

### Long pauses

Find summary lines with high durations, then correlate the GC ID with phase logs. If one phase dominates the pause, examine what work that phase performs. Cross-reference with latency metrics at the same timestamp.

### Frequent Young GC

If many `Pause Young` events appear close together, the application may be allocating rapidly. Check heap size, allocation rate, object lifetime, and pause duration. Frequent Young GC is not automatically a bug if pauses are small and throughput is stable.

### Increasing Old occupancy after collections

If heap used after GC keeps rising, objects may be getting promoted or retained by the application. Check old regions, live set after collection, concurrent marking, and Full GC. Use a heap dump or JFR when you need to identify the objects and references holding them.

### Repeated Full GC

Check the cause, heap occupancy before/after, metaspace, and ergonomic details. If Full GC runs repeatedly while reclaiming little memory, investigate memory pressure, object retention, and heap limits.

### Evacuation failure or allocation failure

These messages indicate the collector could not finish moving objects or could not satisfy allocations as expected. Inspect phase, region, free space, and collector logs around the same GC ID. Do not change heap flags before understanding the workload and root cause.

### Growing Metaspace

Look for `gc,metaspace` lines and correlate them with class loading/unloading. Metaspace growth can be normal while an application loads classes; investigate class loader lifecycles if usage fails to stabilize across cycles.

### Long safepoints with short GC

If application pause times do not match GC durations, inspect `safepoint` logs and other VM operations. GC logs and safepoint logs complement each other; they are not two counters you can simply add together.

## 21. Comparing GC Logs with jstat, jcmd, and JFR

| Tool | Data | Best used when |
|---|---|---|
| GC log | Event timeline, cause, phase, heap change, pause, and rotation. | Analyzing GC across multiple collections. |
| `jstat` | Memory pool snapshots, GC counters, and cumulative time. | Quickly checking trends on a running JVM. |
| `jcmd GC.heap_info` | Heap summary at the time of invocation. | Checking capacity and heap structure. |
| JFR | Time-ordered runtime events, allocations, threads, locks, GC, and CPU sampling. | Correlating GC with application activity. |
| Heap dump | Object graph and references. | Identifying objects retaining heap when a leak is suspected. |

GC logs are usually the primary source for the pause timeline. Use `jstat` for quick observation and JFR to correlate GC with allocations, threads, and locks. Use a heap dump when you need to find the specific objects holding memory.

## 22. Common Mistakes When Configuring and Reading GC Logs

| Symptom | Cause | Resolution |
|---|---|---|
| No log file created | Wrong path, directory does not exist, or missing write permission. | Create the directory and check permissions for the JVM user. |
| Log only has general GC lines | Selected `gc` instead of wildcard `gc*`, or detailed tags are not enabled. | Use `-Xlog:gc*=info` and raise needed tags to `debug`. |
| No phase breakdown visible | `gc+phases` tag not enabled at the appropriate level. | Enable `-Xlog:gc+phases=debug`. |
| Log file grows too fast | `trace`/`debug` enabled too broadly or no rotation configured. | Narrow tags/levels and set `filesize`/`filecount`. |
| Logs overwritten on restart | Rotation disabled or shared file name used. | Enable `filecount` and use `%p`/`%t`. |
| Missing logs for past GC events | Logging was enabled after the event occurred or old files were rotated out. | Enable at startup or check all rotated files. |
| Unable to understand lines of the same event | Reading a single line without correlating by GC ID. | Search for all lines with the same `GC(n)`. |
| GC time and safepoint time differ | The two metrics measure different scopes of activity. | Correlate events and timestamps instead of adding them directly. |
| Parser breaks after JDK upgrade | Tags, content, or log format changed. | Test parsers per JDK/collector and avoid fixed-column assumptions. |
| Cannot change configuration at runtime | JVM does not support the diagnostic command or attach permissions are insufficient. | Check `jcmd PID help VM.log` and user/PID namespace. |
| Manual rotation does not work | Output is not a file or command targeted the wrong JVM. | Check `jcmd PID VM.log list=true`, then retry `rotate=true`. |

## 23. Workflow for Enabling and Analyzing GC Logs in Production

1. Identify the JDK version, JVM vendor, collector, PID, and heap flags.
2. Choose baseline `gc*=info` logging with decorators including `time`, `uptime`, `level`, and `tags`.
3. Write to a dedicated file using a name with PID/timestamp and configure rotation.
4. Start the application or enable logging at runtime using `jcmd PID VM.log`.
5. Verify the output with `VM.log list=true` and confirm the file is being written.
6. When a latency spike occurs, note the timestamp and find GC IDs near that time.
7. Read the summary line to check GC type, heap before/after, and pause duration.
8. Correlate phase, heap, metaspace, CPU, and safepoint lines sharing the same event ID.
9. Compare multiple collections to identify trends instead of concluding from a single event.
10. If more detail is needed, enable narrow debug tags like `gc+phases` or `gc+heap` during the investigation.
11. Cross-reference with application metrics, JFR, `jstat`, and heap dumps as needed.
12. Archive necessary files before rotation removes them, and protect logs according to internal data policies.

## 24. References

- [Unified Logging — Java Virtual Machine Guide, JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The java Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [The jcmd Command — JDK 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [HotSpot Virtual Machine Garbage Collection Tuning Guide — JDK 24](https://docs.oracle.com/en/java/javase/24/gctuning/)

GC log formatting in HotSpot Unified Logging is configured via tag selections, levels, outputs, decorators, and rotation. Start with `-Xlog:gc*=info` for an overall timeline, correlate lines by GC ID, and enable phase/heap/ergo logs only when deeper investigation is needed. Always bound file sizes, cross-reference pauses with safepoints and application metrics, and verify syntax against the exact JDK in use.
