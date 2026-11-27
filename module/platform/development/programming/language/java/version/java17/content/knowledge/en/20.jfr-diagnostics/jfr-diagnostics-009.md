# Unified Logging with Tags, Levels, and Rotating Files in Java 17

## 1. What Is Unified Logging?

**Unified Logging** is the HotSpot JVM's unified logging system, introduced in Java 9. Instead of each JVM subsystem having its own set of logging flags, Unified Logging provides one common syntax to select:

- **Tags:** groups of information to observe, such as GC, heap, class loading, or safepoints.
- **Levels:** message verbosity, from errors down to trace.
- **Output:** log destination, such as standard output, standard error, or a file.
- **Decorators:** metadata prepended to each line, such as timestamp, PID, thread ID, level, and tags.
- **Output options:** destination options, notably rotating file size and count.

In Java 17, Unified Logging is the current mechanism for observing JVM behavior. For instance, instead of relying on legacy GC logging flags, you can use `-Xlog:gc*` to collect GC logs and related tags.

Unified Logging is not an application logger like SLF4J or `java.util.logging`. It records internal events of the JVM and selected runtime components. Application logs should still be managed by an application logging framework.

## 2. General Syntax of `-Xlog`

Syntax:

~~~text
-Xlog[:what][:output][:decorators][:output-options]
~~~

Parts can be shortened or omitted depending on your goal.

| Part | Content |
|---|---|
| `what` | Tag selectors and levels to enable. |
| `output` | Destination: `stdout`, `stderr`, or `file=...`. |
| `decorators` | Metadata added to each log line. |
| `output-options` | Output options, such as `filecount` and `filesize`. |

Minimal example:

~~~text
-Xlog:gc
~~~

This enables logging for the `gc` tag at the default `info` level and writes to Unified Logging's default output.

More complete example:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

This means:

- Select tag sets matching `gc*` at level `info`.
- Write to `gc.log`.
- Prepend wall-clock time, JVM uptime, level, and tags to each line.
- Rotate files when the active file reaches 20 MB and keep up to five rotated log files per configuration.

When configuring logging, separate `what`, `output`, `decorators`, and `output-options` cleanly. Many configuration errors come from misplacing colons or commas between sections.

## 3. Tags and Tag Sets

A tag is a label attached by the JVM to a log message. Each message can carry one or more tags. For example, a GC message about the heap may carry a tag set consisting of `gc` and `heap`.

### 3.1. Selecting a Single Tag

~~~text
-Xlog:gc=info
~~~

Selects messages belonging to tag set `gc` at level `info`.

Common tags:

| Tag | Information Group |
|---|---|
| `gc` | Garbage collection activity. |
| `heap` | Heap state and structure. |
| `phases` | Internal phases within GC operations. |
| `safepoint` | Safepoints and details on bringing threads to a safe state. |
| `class` | Class loading and unloading activity. |
| `load` | Class loading details when combined with tag `class`. |
| `unload` | Class unloading details when combined with tag `class`. |
| `os` | Operating system-related details. |
| `container` | Container resource limit detection details on supported runtimes. |
| `compiler` | JIT compilation activity. |
| `jit` | Information related to JIT and the runtime compiler. |

The actual tag list depends on the JVM build and components compiled into the runtime. Do not guess a tag from a feature name; inspect the list supported by the running JDK via `-Xlog:help`.

### 3.2. Selecting Combined Tag Sets

A selector can require multiple tags to appear together:

~~~text
-Xlog:gc+heap=debug
~~~

The `gc+heap` selector matches messages carrying both `gc` and `heap` tags. This is useful when you want GC-related heap details without enabling all GC messages.

Another example:

~~~text
-Xlog:class+load=info
~~~

This selector logs class loading information at level `info`.

### 3.3. The `*` Wildcard

You can append a wildcard to a tag selector to match tag sets containing the specified tag:

~~~text
-Xlog:gc*=info
~~~

`gc*` broadens the scope beyond `gc` alone to include related tag sets containing `gc`, such as `gc+heap` or `gc+phases`.

Do not confuse this wildcard with Java package wildcards. This is Unified Logging's tag set selection syntax.

### 3.4. Multiple Selectors in One Configuration

Selectors are separated by commas:

~~~text
-Xlog:gc=info,gc+heap=debug
~~~

This captures general GC logs at `info` and more detailed heap info at `debug`. You can combine tag sets according to your investigation needs, while avoiding enabling too many verbose groups in production.

### 3.5. Checking Which Tags the JVM Supports

Run:

~~~text
java -Xlog:help
~~~

This prints Unified Logging help, including:

- Tag sets supported by the runtime.
- Available levels.
- Decorators.
- Output options and related syntax.

This is the most reliable check when a tag or option does not work on a specific Java 17 build. You can save this output alongside JVM version info when preparing operational runbooks.

## 4. Levels: Log Verbosity

Unified Logging provides these levels:

| Level | Purpose |
|---|---|
| `off` | Disables messages for the selected tag selector. |
| `error` | Error events. |
| `warning` | Warnings. |
| `info` | General operational information. |
| `debug` | More detailed diagnostic information. |
| `trace` | Very detailed information, typically used for deep investigations. |

Verbosity increases from `error` down to `trace`. If the level is omitted in a selector, it defaults to `info`.

Examples:

~~~text
-Xlog:gc=warning
-Xlog:gc+heap=debug
-Xlog:class+load=info
-Xlog:safepoint=trace
~~~

`trace` can produce huge log volumes. Only enable it with a clear investigation goal, for a bounded period, and with sufficient storage capacity.

### 4.1. Levels Are Thresholds, Not Keyword Filters

Selecting `debug` causes the JVM to log `debug` messages and higher-severity messages for that selector. Selecting `info` logs `info`, `warning`, and `error` messages; `debug` and `trace` messages are excluded.

Choosing the right level controls both detail and log volume. Do not assume `debug` adds just a few extra lines; for some tags, it generates substantial output.

### 4.2. Using `off` to Silence a Group

You can turn off a specific tag set in the configuration:

~~~text
-Xlog:gc*=info,gc+heap=off
~~~

This enables tag sets containing `gc`, while disabling the `gc+heap` group via its own selector. When multiple selectors match the same message, verify selector precedence using documentation and `-Xlog:help` on your runtime; clearer configurations are easier to operate.

## 5. Output: Where Logs Are Written

Unified Logging supports these common destinations:

| Output | Meaning |
|---|---|
| `stdout` | Standard output. |
| `stderr` | Standard error. |
| `file=filename` | Writes to the specified file. |

Example writing GC logs to standard output:

~~~text
-Xlog:gc*=info:stdout
~~~

Writing to standard error:

~~~text
-Xlog:gc*=info:stderr
~~~

Writing to a file:

~~~text
-Xlog:gc*=info:file=gc.log
~~~

In container environments, writing to `stdout`/`stderr` works well when the platform collects console logs. On self-managed servers, writing to dedicated files can be more convenient for retention and analysis.

### 5.1. File Paths

Example on Linux:

~~~text
-Xlog:gc*=info:file=/var/log/myapp/gc.log
~~~

Example on Windows:

~~~text
-Xlog:gc*=info:file=C:/logs/myapp/gc.log
~~~

Ensure the target directory exists and the Java process has write permissions. If the path contains spaces, wrap the entire JVM argument in quotes appropriate for your shell or launch script.

### 5.2. Multiple Log Groups and Multiple Outputs

You can configure different tag groups with different destinations using multiple `-Xlog` flags. Example:

~~~text
java ^
  -Xlog:gc*=info:file=gc.log:uptime,level,tags:filecount=5,filesize=20M ^
  -Xlog:class+load=info:file=class-load.log:time,level,tags:filecount=3,filesize=10M ^
  -jar app.jar
~~~

The example uses the Windows Command Prompt line continuation character (`^`). On Linux/macOS, replace it with `\` at the end of each line or write it all on one line. The first flag logs GC; the second logs class loading to a separate file to avoid mixing two event streams in one file.

When adding multiple configurations, keep track of which tag selector writes to which output. If the same tag set is configured multiple times, verify the effective configuration via actual logs and `jcmd <pid> VM.log list`.

## 6. Decorators: Metadata on Every Log Line

Decorators add metadata to each log line to aid analysis. Syntax:

~~~text
-Xlog:gc*:stdout:uptime,level,tags
~~~

Commonly used decorators:

| Decorator | Meaning |
|---|---|
| `time` | Calendar time when the log line is written. |
| `utctime` | UTC time. |
| `uptime` | Elapsed time since JVM startup. |
| `timemillis` | Calendar time in milliseconds. |
| `uptimemillis` | Uptime in milliseconds. |
| `timenanos` | Calendar time at nanosecond resolution per logger formatting. |
| `uptimenanos` | Uptime in nanoseconds. |
| `pid` | Process ID. |
| `tid` | Thread ID. |
| `level` | Message level. |
| `tags` | Tag set attached to the message. |
| `none` | No decorators added. |

An example log line might look like:

~~~text
[2026-11-15T10:30:12.345+0000][12.345s][info][gc] GC(4) Pause Young ...
~~~

In the example:

- The timestamp shows the system clock time.
- Uptime helps align events within the JVM's run duration.
- `info` is the level.
- `gc` is the tag.

`uptime` is helpful when correlating multiple logs from the same process run. `time` is helpful when aligning with application logs or external timelines. You can combine multiple decorators separated by commas.

### 6.1. Default Decorators

If no decorators are specified, Unified Logging uses the runtime's default set. In operational settings, it is good practice to explicitly specify `uptime,level,tags` or `time,uptime,level,tags` for consistent, readable formatting.

### 6.2. Decorators Do Not Change Event Content

Decorators only prepend metadata to log messages. They do not cause the JVM to emit additional event types. To observe heap, class loading, or safepoints, you still must select the corresponding tags in the `what` section.

## 7. Rotating Files: `filecount` and `filesize`

Writing continuously to a single file can cause unbounded growth and fill the disk. Unified Logging supports log rotation when the output is a file.

Two key options:

| Option | Meaning |
|---|---|
| `filesize=<size>` | File size threshold before triggering rotation. |
| `filecount=<count>` | Number of rotated files to retain. |

Example:

~~~text
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

When the log file reaches the 20 MB threshold, the JVM rotates the file according to configuration and retains the specified number of rotated files. This bounds local log disk consumption.

### 7.1. Choosing File Size and Count

Suppose you configure:

~~~text
filecount=5,filesize=20M
~~~

Storage allocated to this log group will be roughly six files of 20 MB when counting both the active file and the rotated files, plus slight variance from rotation timing and filesystem metadata. Budget extra disk space for other logs, files currently being read by log shippers, and copied files.

Choose values based on:

- Log generation rate per second.
- How long logs must remain on disk for investigation.
- Disk capacity allocatable to the JVM.
- Frequency of shipping logs to centralized storage.
- Enabled log level (`info`, `debug`, or `trace`).

If logs ship continuously to a centralized system, fewer local files are needed. If logs must stay on the host for post-incident investigation, configure enough files and size to cover the desired window.

### 7.2. Example Rotating GC Log Configuration

~~~text
java \
  -Xms2g \
  -Xmx2g \
  -Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=8,filesize=32M \
  -jar app.jar
~~~

This is a solid starting setup for collecting GC logs where multiple smaller files are preferred over one huge file. Create the `logs` directory beforehand and ensure the JVM user has write permissions.

### 7.3. Rotation Does Not Replace Retention Policies

Rotation keeps local disk usage relatively bounded, but it is not a backup or archive system. If logs must be retained for days or months, forward them to centralized storage or an archival process with its own retention policy.

Do not write `trace` logs to an unbounded file. When enabling verbose levels, adjust `filesize`, `filecount`, and collection duration together.

## 8. Practical Configurations by Diagnostic Goal

### 8.1. Monitoring GC at Info Level

~~~text
-Xlog:gc*=info:stdout:uptime,level,tags
~~~

Use when you need a high-level view of GC cycles, pauses, and related info.

### 8.2. Inspecting Heap Details and GC Phases

~~~text
-Xlog:gc+heap=debug,gc+phases=debug:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

Use when investigating why pauses are long or why heap shifts abnormally. `debug` produces more logs than `info`; enable for a limited period.

### 8.3. Tracking Class Loading

~~~text
-Xlog:class+load=info,class+unload=info:file=class-lifecycle.log:time,level,tags:filecount=3,filesize=10M
~~~

Useful when investigating when classes are loaded/unloaded, class loaders, or metadata footprint tied to class lifecycles.

### 8.4. Tracking Safepoints

~~~text
-Xlog:safepoint=info:file=safepoint.log:time,uptime,level,tags:filecount=5,filesize=10M
~~~

Safepoint logs help analyze how long the JVM takes to bring threads to a safe state. This is useful when long pauses occur and it is unclear how much time was GC work versus waiting for threads to reach a safepoint.

### 8.5. Combining GC and Safepoints

~~~text
-Xlog:gc*=info,safepoint=info:file=jvm-diagnostics.log:time,uptime,level,tags:filecount=6,filesize=25M
~~~

Both log groups write to the same file for easy timeline correlation. If you need separate access control, retention, or volume caps per group, use separate outputs.

### 8.6. Investigating the JIT Compiler

~~~text
-Xlog:compiler=debug:file=compiler.log:uptime,level,tags:filecount=3,filesize=20M
~~~

Compiler logs can be very verbose. Enable only when investigating JIT behavior, method compilation, or code cache issues; do not leave on permanently in every environment.

## 9. Discovering and Verifying Settings with `-Xlog:help`

When a selector does not produce the expected logs, do not immediately assume the JVM subsystem is inactive. First check syntax and runtime support:

~~~text
java -Xlog:help
~~~

Verify:

1. Does the tag exist in this runtime?
2. Is the tag set combined properly with `+`?
3. Is the wildcard placed correctly?
4. Is the level valid?
5. Is the output path valid and writable?
6. Are decorators in the supported list?
7. Are output options placed after the decorators section?

You can check the JVM version:

~~~text
java -version
~~~

This matters because tags, log formatting, and implementation details can differ across vendors or JDK updates. Document the exact runtime when creating diagnostic runbooks.

## 10. Changing Logging on a Running JVM with `jcmd`

Restarting an application just to enable extra logs is not always possible. HotSpot provides the `VM.log` diagnostic command, invocable via `jcmd`, to list or modify Unified Logging settings in a running JVM.

First, find the PID:

~~~text
jcmd -l
~~~

List current logging configurations:

~~~text
jcmd <pid> VM.log list
~~~

Add a GC logging configuration to standard output:

~~~text
jcmd <pid> VM.log output=stdout what="gc*=debug" decorators="uptime,level,tags"
~~~

Add a file-based logging configuration:

~~~text
jcmd <pid> VM.log output="file=gc-live.log" what="gc*=info" decorators="time,uptime,level,tags" output_options="filecount=5,filesize=20M"
~~~

Check the exact `VM.log` syntax on the running runtime:

~~~text
jcmd <pid> help VM.log
~~~

Changes applied via `VM.log` affect only the current process; they do not automatically update startup scripts or service definitions for the next restart. Save permanent settings into your launch configuration once validated.

### 10.1. Permissions and Environment

`jcmd` requires permission to attach to the target process per OS and JVM rules. In some container setups or system accounts, the command may not see the PID or fail to attach. Check the JVM user, PID namespace, attach permissions, and operational policies.

Do not widen system privileges just to toggle logs without understanding security implications. If attaching is not possible, schedule `-Xlog` configuration at the next restart through your deployment pipeline.

## 11. Reading Logs and Correlating Events

A Unified Logging line generally follows this pattern:

~~~text
[decorators] message
~~~

Example:

~~~text
[12.345s][info][gc] GC(7) Pause Young (Normal) (G1 Evacuation Pause) 512M->180M(2G) 18.4ms
~~~

When reading, identify:

- Uptime or timestamp to place the event on a timeline.
- Level to gauge verbosity.
- Tag set to know which subsystem emitted the message.
- Message body for specific metrics and details.

Do not simply grep for a word like `Pause` and jump to conclusions. Group lines sharing the same GC ID or uptime window, especially when analyzing GC phases, safepoints, class loading, and compiler events.

### 11.1. Correlating GC Pauses with Safepoints

GC pauses often require stop-the-world pauses. Safepoint logs provide details on stopping threads and safepoint overhead. When seeing long pauses, compare:

- Time spent reaching/waiting for threads to enter the safepoint.
- Time GC spent performing collection work.
- Time spent resuming threads.

This separates long pauses caused by GC processing large heaps from long pauses caused by threads taking too long to reach a safepoint.

### 11.2. Correlating Class Loading with Memory

When class counts climb rapidly, correlate class loading/unloading with class loader counts, metaspace usage, and application lifecycle. Unified Logging supplies the events; tools like JFR, `jcmd`, and runtime metrics provide supporting data to find the cause.

### 11.3. Avoiding Conclusions from Incomplete Log Context

Logs can be truncated by rotation, process restarts, or log shippers missing files. When analyzing:

- Verify timestamps and uptimes in each file.
- Identify which file is active versus rotated.
- Record the PID to avoid mixing logs from two different process runs.
- Verify which level/tag settings were active during the incident.
- Cross-reference with application metrics and request logs.

## 12. Overhead and Considerations When Enabling Logging

Unified Logging is built for JVM observability, yet logging still carries overhead:

- Extra CPU work to format and emit messages.
- Increased disk I/O and filesystem pressure.
- Storage consumption.
- Potential latency impact if output stalls or logs flood excessively.
- Detailed logs may reveal class names, paths, runtime structure, or operational details.

Recommendations:

1. Start at level `info` with narrow tags.
2. Raise to `debug`/`trace` only with an investigation hypothesis.
3. Enable rotation on file outputs.
4. Set appropriate log file access permissions.
5. Do not record sensitive data in application logs or diagnostic configs.
6. Disable or tone down verbose logs once investigation completes.
7. Measure impact in a production-like environment before keeping settings long-term.

Do not run `all=trace` in production as a default configuration. It can emit massive volumes of logs and distort the exact performance characteristics you are trying to measure.

## 13. Common Configuration Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Desired logs missing | Tag set or level mismatch. | Check `-Xlog:help`, test a narrow selector like `gc=info`. |
| Too many logs | Broad wildcard or `debug`/`trace` level. | Narrow tag sets and lower the level. |
| Log file not created | Bad path, missing directory, or no write permission. | Verify path and permissions of the JVM user. |
| Log file grows indefinitely | Rotation not configured. | Configure `filecount` and `filesize`. |
| Unclear which thread emitted a line | Missing thread ID decorator. | Add `tid` when analyzing multithreaded events. |
| Hard to merge logs across restarts | Using only uptime without timestamp/PID. | Add `time` or `utctime`, `pid`, and keep session metadata. |
| `jcmd VM.log` fails to attach | Wrong PID, different user, namespace, or restricted attach. | Check permissions and process environment. |
| Combined selector yields unexpected output | Confusing single tag vs. tag set, wildcards, or overlapping selectors. | Inspect tag sets and current settings via `VM.log list`. |
| Beginning of logs missing | Rotation, restart, or log shipper missed older files. | Check rotated files, PID, and uptime. |
| Logging causes high I/O | Too many tags or overly verbose levels enabled. | Reduce scope and collection duration; use rotation. |

## 14. Practice Exercises

### Exercise 1 — Exploring Tags and Levels

Run `java -Xlog:help`. Record the tags related to GC, heap, safepoints, and class loading supported by your runtime. Identify valid levels and available decorators.

### Exercise 2 — Comparing Selectors

Run the same program with:

~~~text
-Xlog:gc=info
-Xlog:gc*=info
-Xlog:gc+heap=debug
~~~

Compare the volume and types of messages produced. Explain the differences between a single tag, a wildcard tag set, and a combined tag set.

### Exercise 3 — Changing Decorators

Run with `uptime,level,tags`, then with `time,pid,tid,level,tags`. Compare how easily you can correlate logs across multiple processes and align JVM logs with application logs.

### Exercise 4 — Writing Rotating Files

Enable GC logging with `filecount=3,filesize=1M` during a workload that generates sufficient logs. Observe the active file and rotated files. Explain how rotation bounds local storage.

### Exercise 5 — Splitting Logs by Subsystem

Write GC logs to `gc.log` and class loading logs to `class-load.log`. Use timestamp and level decorators. Explain when to separate outputs versus consolidating into one file.

### Exercise 6 — Adjusting at Runtime with jcmd

Start a long-running Java application. Use `jcmd -l` to find its PID, `jcmd <pid> VM.log list` to view configuration, and then add a GC selector at `debug` level. Confirm logs appear and inspect how to disable/adjust settings using `jcmd <pid> help VM.log`.

### Exercise 7 — Investigating Long Pauses

Enable `gc*=info` and `safepoint=info`, and run a high-allocation workload. Correlate lines by uptime and GC ID. Determine how much time went to safepoint overhead versus GC work if the logs supply sufficient detail.

## 15. Workflow for Configuring Unified Logging in a Project

An operational workflow:

1. **Define the question to answer.** For example: long GC pauses, abnormal class loading, or prolonged safepoints.
2. **Choose narrow tags.** Use `gc`, `gc+heap`, `gc+phases`, `class+load`, or `safepoint` as needed.
3. **Choose the lowest sufficient level.** Start at `info`; raise to `debug` or `trace` only when required.
4. **Choose output.** Console if the platform collects stdout/stderr; file if storing on the host.
5. **Choose decorators.** Commonly `time,uptime,level,tags`; add `pid`/`tid` as needed.
6. **Configure rotation.** Set `filesize` and `filecount` to match log rate and desired retention.
7. **Verify against the actual runtime.** Check `-Xlog:help`, test output, and `jcmd <pid> VM.log list`.
8. **Monitor impact.** Check I/O, CPU, disk usage, and latency.
9. **Scale back after investigation.** Lower levels or disable verbose tags once no longer needed.
10. **Document settings in runbooks/deployment configs.** Record JDK version, JVM flags, and change timestamps for reproducibility.

## 16. Principles to Remember

- Unified Logging is the HotSpot JVM's unified logging framework using `-Xlog` syntax in Java 17.
- `what` selects tags/tag sets and levels; `output` selects stdout, stderr, or a file; `decorators` add metadata; `output-options` control destination options.
- Combined tag sets use `+`; multiple selectors use commas; the `*` wildcard matches related tag sets.
- Common levels are `off`, `error`, `warning`, `info`, `debug`, and `trace`; omitting the level defaults to `info`.
- `-Xlog:help` lists tags, levels, decorators, and options supported by the runtime.
- Decorators like `time`, `uptime`, `pid`, `tid`, `level`, and `tags` anchor logs to exact timelines and processes.
- File outputs can rotate using `filesize` and `filecount` to cap local storage.
- `jcmd <pid> VM.log` inspects and updates logging on a running JVM; runtime changes do not automatically update startup configs.
- Start with narrow tags and `info` level; enable `debug`/`trace` only with a targeted investigation goal.
- Unified Logging complements application logging, JFR, and metrics; it does not replace them.
- Use current `-Xlog` syntax in Java 17; avoid instructions based on legacy JVM logging flags.

### References

- [Oracle Java 17 — The `-Xlog` Option](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [Oracle Java 17 — Unified Logging](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158).
- [JEP 271 — Unified GC Logging](https://openjdk.org/jeps/271).
- [Oracle Java 17 — `jcmd` Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html).
