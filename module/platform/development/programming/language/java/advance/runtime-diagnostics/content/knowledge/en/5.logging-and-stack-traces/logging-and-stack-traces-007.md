# 5.7 -Xlog Syntax with Tags, Levels, Decorators, Files, and Log Rotation

When investigating GC pauses, class loading, safepoints, memory errors, or JVM behavior in Java 17+, looking only at application logs is usually insufficient. The HotSpot JVM provides **Unified JVM Logging**: an internal logging mechanism configured via the `-Xlog` startup flag. This syntax lets you choose **event groups (tags)**, **verbosity (levels)**, **per-line metadata (decorators)**, **output destinations (stdout/stderr/file)**, and **file rotation**.

Example:

```bash
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

The configuration above instructs the JVM to log tag sets containing `gc` at `info` level or higher to a file, using a filename with PID/startup timestamp, adding time/level/tags to each line, and enabling size-based rotation. This is **illustrative syntax**: `app.jar` and the `logs` directory must actually exist and be writable; when GC events fire depends on workload and runtime.

The lesson goal is to **read and write syntactically valid `-Xlog` commands**, accurately understand tag set matching, levels, decorators, files, and rotation, and know how to verify when logs do not appear or files grow unexpectedly. The lesson focuses on **HotSpot Unified Logging (JDK 17/21)** configuration—do not confuse it with application logging via SLF4J/Logback/Log4j.

## 1. What Does Unified JVM Logging Solve?

Unified Logging is the JVM's logging framework, introduced in HotSpot in Java 9 (JEP 158); GC logs and many runtime subsystems share the same tag/level/output selection model. It is especially useful for:

- Tracking GC start/end, causes, pauses, heap occupancy, and collector-specific details depending on tags.
- Correlating class loading/unloading when suspecting class loader leaks or slow startup.
- Observing safepoints, container/OS info, code cache, or compilation within the tags supported by the JVM.
- Producing log lines with timestamp/uptime/PID to correlate with metrics, application logs, and OS telemetry.
- Writing diagnostic data to rotating files, preventing a single file from growing unboundedly in many cases.

**Not every Java event goes through `-Xlog`.** `System.out.println`, application-printed stack traces, logs from SLF4J/Logback/Log4j, web access logs, and tracing each have their own configuration mechanisms. `-Xlog:gc` does not enable Spring DEBUG logs or alter Log4j configuration.

Treat `-Xlog` as a **source of runtime evidence**, placed alongside application logs, metrics, JFR, and OS/container telemetry. It does not by itself prove an incident's root cause without load, timing, and JVM flag context.

### 1.1 Checking What the Current JVM Actually Supports

Before applying a configuration:

```bash
java -version
java -Xlog:help
```

`java -Xlog:help` prints syntax help, available tags/levels/decorators, and examples for **the JVM launched by this `java` command**. Verify the service's actual version: your terminal may point to a different JDK. Tag lists and tag combinations can differ across JDK releases, collectors, and implementations. A valid tag name **does not guarantee** every combination with it will emit actual events.

A safe learning rule: **run `-Xlog:help` on the exact target JDK release and test with a small workload**, rather than blindly copying an option from a newer JDK onto an older JVM.

## 2. General Structure of -Xlog

Per the Java launcher documentation, the general form is:

```text
-Xlog[:[what][:[output][:[decorators][:output-options]]]]
-Xlog:help
-Xlog:disable
-Xlog:async
```

Where:

| Position | Name | Content | Example |
| --- | --- | --- | --- |
| After `-Xlog:` | `what` | Tag/tag set, wildcard, level; multiple selectors separated by commas | `gc*=debug,safepoint=info` |
| After second `:` | `output` | `stdout`, `stderr`, or `file=...` | `file=logs/gc.log` |
| After third `:` | `decorators` | Labels prepended before the message | `time,uptime,level,tags,pid` |
| After fourth `:` | `output-options` | Output settings, especially file rotation | `filecount=5,filesize=10M` |
| Directly after `-Xlog:` | directive | Global command/adjustment like `help`, `disable`, `async` | `-Xlog:help` |

**Colons separate *positions*, commas separate *items within a position*.** `+` joins multiple tags belonging to **the same tag set**. `*` at the end of a tag selector performs wildcard matching. `=` selects the level. These symbols have distinct roles and are not interchangeable.

Sample breakdown:

```text
-Xlog:gc*=debug:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=10M
      |         |                       |                      |
      what      output                  decorators             output-options
```

- `what = gc*=debug`: matches tag sets **containing** `gc`, from debug through more severe levels (info, warning, error).
- `output = file=...`: writes to a file whose name contains two JVM placeholders.
- `decorators = time,uptime,level,tags`: displays calendar time, JVM elapsed time, level, and tag set.
- `output-options = filecount=5,filesize=10M`: rotates files around 10 MB per file, using the configured file count.

**Warning:** if you omit `output` while still specifying decorators, preserve the empty slot with two consecutive colons `::`. For example, `-Xlog:gc::uptime,tid`: output stays stdout and decorators are `uptime,tid`. Do not treat `-Xlog:gc:uptime,tid` as "equivalent": the JVM will interpret `uptime,tid` as the **output** slot.

### 2.1 Valid Shorthand Forms

```bash
java -Xlog -version
java -Xlog:gc -version
java "-Xlog:gc=debug:stdout:uptime,level,tags" -version
java "-Xlog:gc=debug:file=gc.log:none" -version
java "-Xlog:gc::uptime,tid" -version
```

The commands here use `-version` to **test parser/configuration**, not as a benchmark; because the JVM may not perform observable GC during a brief exit, **having no GC log lines does not prove the configuration is wrong**. Depending on the JVM, startup logs or warnings may still appear.

## 3. Selecting Tags: gc, gc*, gc+heap, and Combinations

### 3.1 Tags Classify Runtime Messages

Each Unified Logging message has a **tag set** (one or more tags) and a level. Common tags in runtime diagnostics include `gc`, `safepoint`, `class`, `load`, `unload`, `os`, `container`, `compiler`, and `codecache`; the actual list is printed by `-Xlog:help`.

Crucially: **a selector without a wildcard matches the exact tag set**, not "contains substring" or "contains any of those tags".

| Selector | Meaning | Not equivalent to |
| --- | --- | --- |
| `gc` | Matches messages with the **exact** tag set `gc` | All GC-related logs |
| `gc*` | Matches every tag set **containing `gc`**, including `gc+heap` | Only the `gc` tag set |
| `gc+heap` | Matches the exact tag set consisting of `gc` and `heap` | Any tag set containing those two tags |
| `gc+heap*` | Matches tag sets containing **at least** `gc` and `heap` | Tag sets containing only one of the two |
| `gc,safepoint` | Two independent selectors: exact `gc` **or** exact `safepoint` | The `gc+safepoint` tag set |
| `gc+safepoint` | One selector for the tag set containing **both** `gc` and `safepoint` | Two comma-separated selectors |
| `all` | Meta-tag matching every tag set | Only `gc` or the tags you listed |

Examples:

```bash
java "-Xlog:gc=info" -jar app.jar
java "-Xlog:gc*=info" -jar app.jar
java "-Xlog:gc+heap=debug" -jar app.jar
java "-Xlog:gc+heap*=debug" -jar app.jar
java "-Xlog:gc=info,safepoint=debug" -jar app.jar
```

All examples require a valid `app.jar`. When the goal is **GC details**, `gc*` is usually better than `gc` because detailed messages often carry multiple tags. However, broader scope increases line count and overhead; start at `info` and raise verbosity with a concrete hypothesis.

### 3.2 Reading `+`, Commas, and Wildcards

Suppose a JVM has illustrative log events with these tag sets:

```text
[gc]
[gc,heap]
[gc,ergo]
[safepoint]
[gc,heap,region]
```

- `gc` matches only the first event (exact tag set).
- `gc*` matches events containing `gc`: first, second, third, and fifth.
- `gc+heap` matches only the second event.
- `gc+heap*` matches the second and fifth events.
- `gc,safepoint` matches only the first and fourth events.
- `gc*,safepoint` matches all events in this list since the fifth carries the `gc` tag.

These tag sets are a **matching illustration model**, not a guarantee that every JVM emits all five event types. Actual tags are documented in `-Xlog:help` output and depend on the implementation.

### 3.3 Expanding from Narrow to Broad

When starting an investigation:

1. Start with `-Xlog:gc=info` if you only need a basic GC summary.
2. Use `-Xlog:gc*=info` if you also want combined tag groups containing GC.
3. Raise `gc+heap=debug` or `gc+ergo*=debug` for heap/ergonomics hypotheses, **after checking tag support**.
4. Set a sufficiently short time window and proper rotation when enabling DEBUG/TRACE.
5. Never run `all=trace` continuously in production without assessing log volume and overhead.

## 4. Choosing Levels: Verbosity and Thresholds

HotSpot Unified Logging supports these levels:

| Level | Usage meaning | Relative verbosity |
| --- | --- | --- |
| `off` | Disables logging for the specified selection | Emits nothing for the selection |
| `error` | Error messages | Least |
| `warning` | Warnings and errors | Low |
| `info` | Common operational info and the two more severe levels | Medium |
| `debug` | More detailed than info | Higher |
| `trace` | Very detailed, typically for deep investigation | Highest |

**Levels act as thresholds**, not "only that exact level". For instance, `gc=debug` enables debug along with info/warning/error for the selected tag set; `gc=warning` omits info/debug/trace lines for that tag set. `off` is a special disabling setting, not a level "quieter than error that still prints".

Examples:

```bash
java "-Xlog:gc=info" -jar app.jar
java "-Xlog:gc*=debug" -jar app.jar
java "-Xlog:gc+heap=trace" -jar app.jar
java "-Xlog:gc*=info,safepoint*=off" -jar app.jar
```

In the last configuration, `safepoint*=off` suppresses logs belonging to safepoint tag sets (including combinations with this tag) within the applied scope, even though `gc*` might match overlapping tag sets. Oracle uses a similar example to show disabling a tag group. When selectors overlap, avoid guessing general precedence rules from expressions alone; check the actual output and how the JVM applies selections.

### 4.1 No Lines Does Not Prove the Option Is Wrong

A tag/level may emit zero events during the observation window. For example:

- `gc=debug`: the app ran for a few milliseconds with no GC event.
- `class+load=info`: the app already loaded classes before dynamic logging was enabled, so past loads are not logged.
- `safepoint=info`: no reportable events occurred during the window inspected.
- `gc+heap=trace`: the workload/collector emitted no messages on that exact tag set during the run.

Verify **syntax, tag selection, level, output path, and timing** before inferring from missing events that the JVM "had no GC".

## 5. Choosing Output: stdout, stderr, and file

`-Xlog` accepts:

```text
stdout
stderr
file=<filename>
```

When output is omitted, the default is **stdout**. Examples:

```bash
java "-Xlog:gc=info:stdout" -jar app.jar
java "-Xlog:gc=info:stderr" -jar app.jar
java "-Xlog:gc*=info:file=logs/gc.log" -jar app.jar
```

### 5.1 When to Use stdout/stderr?

In containerized systems, stdout/stderr are typically captured by the container runtime and log collector. This makes sense when the platform already provides its own rotation/retention. Still verify in practice:

- Does the collector distinguish stderr from stdout?
- Are there rate limits or dropped lines?
- Do collector-added timestamps conflict with or drift from JVM decorators?
- When app logs and JVM logs share a stream, can you distinguish sources via `[gc]`, `[info]`, PID/instance?
- Does the collector/driver handle rotation or must it be configured separately?

**Do not specify filecount/filesize for stdout expecting the JVM to rotate the stream.** Rotation in `-Xlog` applies to **file outputs**, not container log management.

### 5.2 When to Use file?

A dedicated file is helpful when keeping GC logs to correlate with JFR/metrics or avoiding mixing with application stdout:

```bash
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:time,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Points to verify before production rollout:

- The `logs/` directory already exists and the JVM user has permissions to create/write files.
- Relative paths resolve against the process's **working directory**, not necessarily the JAR's directory.
- Which filesystem/container volume holds the file; will pod restarts wipe logs; does a log collector read this path?
- Are disk quotas, inodes, retention, and backup settings appropriate?
- Does a launcher/service manager alter `user.dir` or the startup environment?
- Does the file contain sensitive information, and is it protected with proper permissions?

If the JVM cannot open the output file at startup, the logging flag itself can fail startup; verify stderr, exit code, and write permissions in a **staging/test environment first**.

### 5.3 `%p` and `%t` Placeholders in Filenames

Per the `java` documentation, filenames in `file=...` can include:

| Placeholder | Meaning | Purpose |
| --- | --- | --- |
| `%p` | JVM PID | Distinguishes JVMs configured with the same pattern |
| `%t` | JVM startup timestamp | Distinguishes multiple restarts |
| `gc-%p-%t.log` | Combined example | Reduces risk of old and new files colliding on the same name |

Generated filenames might look like `gc-4242-2026-10-29_08-00-00.log`, though **exact timestamp formatting and PID values depend on the JVM/environment**; this is not a character-for-character guarantee. Never build critical scripts assuming the full exact layout of `%t` without checking real files.

**Note:** PIDs can be reused over time and new containers often get PID 1, so `%p` **alone** does not guarantee unique filenames across restarts. `%t` helps reduce collisions, yet you still must check retention policies and how the JVM handles pre-existing filenames.

## 6. Decorators: Adding Per-Line Context

A **decorator** is JVM metadata placed before the message, such as wall-clock time, uptime, level, tag set, PID, thread ID, and host. When unspecified, the default is `uptime,level,tags`.

A **hypothetical** log line:

```text
[2.345s][info][gc] GC(1) Pause Young (Normal) ... 4.120ms
```

The `...` in this illustrative line represents omitted hypothetical message text, **not output from a verified run**. With defaults, the prefix shows how long the JVM had been running when the event occurred, its severity, and its tag set.

### 6.1 Useful Decorators

| Decorator | Meaning | Points to watch |
| --- | --- | --- |
| `time` / `t` | Calendar timestamp, ISO-8601 format | Useful for aligning with app/OS logs; watch timezones |
| `utctime` / `utc` | UTC timestamp | Preferred for correlating systems across timezones |
| `uptime` / `u` | Elapsed time since JVM start | Not a UTC timestamp; great for separating startup vs. steady state |
| `uptimemillis` / `um` | Uptime in milliseconds | Easy to correlate events within one JVM |
| `uptimenanos` / `un` | Uptime in nanoseconds | High resolution, though not every event has nanosecond accuracy |
| `timemillis` / `tm` | Value corresponding to `System.currentTimeMillis()` | Wall-clock can jump due to time synchronization |
| `timenanos` / `tn` | Value corresponding to `System.nanoTime()` | Do not interpret as calendar time |
| `pid` / `p` | JVM PID | PID must be scoped to host/namespace |
| `tid` / `ti` | Related Thread ID | Do not automatically equate to Java Thread ID without knowing JVM mapping |
| `level` / `l` | Message level | Useful for filtering/checking against configuration |
| `tags` / `tg` | Message tag list | Useful for verifying whether `gc` or `gc+heap` actually matched |
| `hostname` / `hn` | Hostname known to the JVM | Can be sensitive internal infrastructure info |
| `none` | Omits all decorators | Hard to analyze time/source unless metadata is added elsewhere |

Examples:

```bash
java "-Xlog:gc*=info:stdout:utctime,uptime,level,tags,pid" -jar app.jar
java "-Xlog:gc=debug:file=logs/gc.log:none:filecount=3,filesize=5M" -jar app.jar
java "-Xlog:gc::uptime,tid" -jar app.jar
```

**Decorators are specified in a single comma-separated slot.** Actual output order is fixed by the framework, not necessarily the order you typed.

### 6.2 Choosing Decorators for Investigation Needs

- Reading GC events from **one JVM**: `uptime,level,tags` may be enough.
- Correlating events across processes/hosts: consider `utctime,uptime,pid,level,tags`; the collector must still attach container/service identity since PIDs repeat across containers.
- Suspecting thread-specific events: add `tid`, without mistaking it for Java thread IDs if other tools use different identifiers.
- Using parsers/dashboards: standardize the decorator set across instances and preserve timezones/units.
- Shipping logs externally: consider omitting `hostname` or private infrastructure details when unnecessary.

Some collectors add their own timestamps; do not automatically drop JVM timestamps for that reason. The two timestamps serve different purposes: **when the JVM emitted the event** and **when the collector received it** can diverge due to buffering/delays.

## 7. Rotation: `filecount` and `filesize`

You cannot write `-Xlog:gc*=trace` into an ever-growing file on a long-running service without bounding disk usage. Unified Logging provides **size-based log rotation** for file outputs.

Configuration:

```bash
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Meaning:

- `filesize=10M`: target size threshold per file is roughly 10 MB. This is an **approximate threshold**, not guaranteed byte-exact due to individual event sizes and write mechanics.
- `filecount=5`: configures how many files participate in rotation/retention per HotSpot's mechanism. Rotation can overwrite old files; it is not a day-based retention policy.
- Upon hitting the threshold, the JVM rotates to the next file in the set and may reuse older slots. Check actual rotated filenames on the target JDK to configure collectors properly.
- `M` is the size suffix for `filesize`; syntax also supports `K`/`G`. Do not arbitrarily write "MB" or unsupported units.

### 7.1 The `filecount=0` Case

```bash
java "-Xlog:gc*=info:file=logs/gc.log:uptime,level,tags:filecount=0" -jar app.jar
```

Per JDK documentation, **`filecount=0` means no rotation**. Do not mistake it for keeping 0 files or disabling logging. With continuous logging, the file can grow without bound and pressure disk space; use only when another mechanism caps disk usage or the workload is short.

### 7.2 Defaults Are Not Always Appropriate

Per the JDK 21 man page, default file rotation uses up to **5 rotated files** with a **20 MB** target size unless overridden. Defaults are documented per release, not universal permanent guarantees across all JVMs. For production, **specify `filecount` and `filesize` explicitly** in startup configuration for clarity and auditability.

Do not treat `5 × 10 MB` as a strict disk upper bound: active/rotated files, event sizes, overhead, multiple JVMs, restarts, and leftover old files can make actual disk usage differ. If rotating on container ephemeral storage, check node/pod quotas and log shipping policies.

### 7.3 Rotation Does Not Replace Log Retention

Size-based rotation **does not automatically** handle:

- Retaining logs for a required number of days/months or compliance needs.
- Cleaning up files no longer belonging to a terminated process's rotation set.
- Backups, encryption, RBAC, or reader restrictions.
- Logs from multiple containers/replicas or metadata collected outside the JVM.
- Centralized shipping and preventing duplicate uploads.
- Disk exhaustion caused by other files/traces or disconnected log collectors.

For long-lived JVM services, coordinate `-Xlog` rotation, disk monitoring, collectors, and retention policies. Avoid running **two independent rotators** on the same file unless you know how the JVM and collector hold file descriptors: external rename/copytruncate can lose or duplicate logs.

### 7.4 Name Collisions, Restarts, and Write Permissions

When a JVM restarts with the same `file=logs/gc.log`, the existing file **may be overwritten** per documentation. Using `%p` and `%t` reduces collision risk, yet you still need cleanup/retention for old logs. If multiple replicas share a mounted directory, make names and paths uniquely identify instances; do not expect one JVM's `filecount` to manage files from other replicas.

## 8. Standalone Java 17+ Practice

To learn the syntax, use a runnable program with clear stdout, without promising identical GC log volume on every run. The example allocates small arrays and hints GC; whether the JVM emits events still depends on the collector and runtime.

Save **`UnifiedXlogDemo.java`**:

```java
public class UnifiedXlogDemo {
    private static volatile Object lastAllocation;

    public static void main(String[] args) {
        System.out.println("APPLICATION_START");

        for (int i = 0; i < 64; i++) {
            lastAllocation = new byte[64 * 1024];
        }

        // Only a GC hint to the JVM, not a guarantee of emitting a specific GC event.
        System.gc();

        System.out.println("APPLICATION_END");
    }
}
```

Compile:

```bash
javac UnifiedXlogDemo.java
```

### 8.1 Enabling GC Logs to stdout

```bash
java "-Xlog:gc=info:stdout:uptime,level,tags" UnifiedXlogDemo
```

The two lines **printed by the Java program** always appear in order:

```text
APPLICATION_START
APPLICATION_END
```

The JVM may print Unified Logging messages before, between, or after these two lines depending on collector, startup, `System.gc()` handling, and environment. Therefore, **you cannot guarantee total stdout consists solely of those two lines**. `System.gc()` may be ignored or produce different events across JVMs; never treat hypothetical GC output as deterministic expected output.

### 8.2 Writing to a File with PID, Startup Time, and Rotation

First create a writable `logs` directory in the working directory. Unix/Linux shell example:

```bash
mkdir -p logs
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=3,filesize=1M" UnifiedXlogDemo
```

Or PowerShell:

```powershell
New-Item -ItemType Directory -Force logs
java "-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=3,filesize=1M" UnifiedXlogDemo
```

When run successfully, stdout from application code is:

```text
APPLICATION_START
APPLICATION_END
```

JVM lines matching the selector go into the configured file instead of mixing into stdout via this output. The JVM may still print warnings or other info to console via remaining logging config. Exact file count and log volume are **not deterministic** from this snippet: allocating a few MiB and calling `System.gc()` will not exceed `filesize=1M`. **Do not expect file rotation to occur** in this brief run. To test real rotation, run a workload generating enough log volume in a test environment while observing disk usage and logging cost.

### 8.3 Full Breakdown of the Example Command

```text
-Xlog:gc*=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=3,filesize=1M
      └ what  ┘  └────── output ───────┘ └────── decorators ─────┘ └─ options ────┘
```

- `gc*=info`: every tag set containing `gc` at info level or more severe.
- `file=...`: directs selected messages to a file under `logs`; `%p` and `%t` distinguish startup instances.
- `utctime,uptime,level,tags`: aligns events with UTC time and JVM lifecycle phase.
- `filecount=3,filesize=1M`: bounds rotated file count and approximate size per config.
- `UnifiedXlogDemo`: main class compiled by `javac`; not a JAR filename.
- Replace `UnifiedXlogDemo` with `-jar app.jar` only when `app.jar` actually exists with a runnable manifest main class.

### 8.4 Verifying Results After Execution

- Confirm the Java command succeeded and printed both application lines.
- Confirm the log file was created and its filename contains matching PID/timestamp.
- Inspect a few lines to verify decorators include UTC/uptime/level/tags.
- If no GC event appeared, check tags/levels and workload duration before assuming logging is broken.
- For rotation tests, increase event load **under control in a test environment**, observing file shifts/size; never stress production heap just to watch rotation.
- Record Java vendor/version and **redacted** command line, as syntax/tags vary across versions.

## 9. Common Configurations in Java Runtime Diagnostics

### 9.1 Lightweight GC Summary for Ongoing Monitoring

```bash
java "-Xlog:gc=info:file=logs/gc-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Prefer summary logs if your questions are simply GC frequency, pause durations, or overall collector behavior. To capture more GC subtags, switch `gc` to `gc*` and measure the resulting volume.

### 9.2 Temporary GC Details When Suspecting Heap/Ergonomics

```bash
java "-Xlog:gc*=debug:file=logs/gc-debug-%p-%t.log:utctime,uptime,level,tags,pid:filecount=5,filesize=20M" -jar app.jar
```

Use debug in a bounded measurement window, recording workload, JVM version, and heap flags. More debug output is **not automatically better**: larger files, CPU/I/O overhead, and internal details increase. Do not enable full GC trace in production just because p99 showed an unexplained spike.

### 9.3 Safepoints and GC in the Same Output

```bash
java "-Xlog:gc*=info,safepoint=info:file=logs/jvm-%p-%t.log:utctime,uptime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

Because `gc*` is a wildcard, the GC group is matched broadly; `safepoint=info` matches the **exact** `safepoint` tag set at info level. If safepoint subtags are needed, use `safepoint*` after verifying JDK support. Safepoint and GC timestamps **alone do not** justify blaming GC for every request latency spike; correlate with the same window and application metrics.

### 9.4 Class Loading/Unloading

```bash
java "-Xlog:class+load=info,class+unload=info:stdout:utctime,level,tags" -jar app.jar
```

Use when observing class loading or unloading, though frequency can be high, especially at startup. Do not treat this output as an exhaustive list of "every class ever loaded" if logging was enabled later or the collector dropped lines.

### 9.5 Container/cgroup Diagnostics

```bash
java "-Xlog:os+container=debug:stdout:uptime,level,tags" -jar app.jar
```

Useful when checking how the JVM perceives container limits on Linux environments with appropriate container support. Some environments emit nothing or lack identical tags/levels; `-Xlog:help` on the target version is the source of truth. **Do not confuse container CPU quota with whole-host CPU** when interpreting logs.

### 9.6 Disabling a Tag Group or Removing Decorators

```bash
java "-Xlog:gc*=info,safepoint*=off:stdout:uptime,level,tags" -jar app.jar
java "-Xlog:gc=debug:file=logs/gc-simple.log:none:filecount=2,filesize=5M" -jar app.jar
```

The first command excludes events whose tag sets contain `safepoint` from the selection; the second omits decorators, suitable only when time/level context comes reliably from elsewhere. For diagnostic logs needing time correlation, `none` usually destroys correlatability.

## 10. Interaction with Defaults and Multiple `-Xlog` Options

### 10.1 JVM Defaults

With no `-Xlog` specified, JDK 21 keeps default logging for `warning` and `error` messages on stdout with `uptime,level,tags` (conceptually equivalent to `-Xlog:all=warning:stdout:uptime,level,tags`). Therefore:

- `-Xlog:gc=info` enables additional `gc` info **without** meaning "print only GC and suppress all other warnings/errors".
- `-Xlog:help` prints help and exits without running the application.
- `-Xlog:disable` clears all current logging configuration, **including default warnings/errors**. This is a drastic option—use only when strictly required and understanding the loss of warnings.
- `-Xlog` with no selection enables default logging per documented semantics; it is not equivalent to `-Xlog:gc`.

### 10.2 Multiple `-Xlog` Flags on the Same Command Line

The Java launcher processes multiple `-Xlog` options in order; per documentation, configurations targeting the same output can **override earlier ones** in order of appearance. Therefore do not write:

```bash
java "-Xlog:gc=info:file=logs/jvm.log" "-Xlog:safepoint=debug:file=logs/jvm.log" -jar app.jar
```

and **assume** both selections combine into one output. To send two tag groups to the same destination, specify them together in **one selection**:

```bash
java "-Xlog:gc=info,safepoint=debug:file=logs/jvm-%p-%t.log:utctime,level,tags:filecount=5,filesize=10M" -jar app.jar
```

If you want two separate log files, use two distinct output names and verify the resulting configuration; remember JVM warnings may still go to stdout by default. Also account for flags injected via `JDK_JAVA_OPTIONS`, `JAVA_TOOL_OPTIONS`, launcher scripts, or container entrypoints altering the effective flags.

### 10.3 Dynamic Logging with `jcmd VM.log`

In many modern HotSpot builds, `jcmd PID VM.log` lets you **list or modify Unified Logging configuration of a running JVM**, provided attach permissions and command support exist.

Start with read-only checks:

```bash
jcmd 4242 help VM.log
jcmd 4242 VM.log list
```

`4242` is an illustrative PID only. Verify the exact PID/instance and permissions; `jcmd -l` has limitations when JVMs run in separate Docker PID namespaces. `VM.log` can configure `what`, `output`, `decorators`, `output_options`, or trigger rotation. Changes via diagnostic commands apply to the **running JVM**; never treat them as persistent startup changes across restarts.

To enable debug temporarily in production, follow an operational procedure: record initial state, bound observation duration, assess overhead/volume, prepare an explicit **rollback** step, and verify afterward. Never run logging changes against unverified PIDs or sweep across fleets blindly.

## 11. Common Syntax and Operational Mistakes

| Issue | Common cause | How to check/fix |
| --- | --- | --- |
| `-Xlog:gc` lacks heap details | Exact tag set `gc` does not match `gc+heap` | Use `gc*` or target `gc+heap` specifically |
| Wrote `gc+heap` expecting two separate groups | `+` is AND within one tag set, not OR | Use `gc,heap` only if you want both exact tag sets independently |
| Forgot `:` when omitting output | JVM parses decorators as output | Use `-Xlog:gc::uptime,tid` |
| No GC log in a short app | No event occurred / mismatched tag/level | Check workload, `-Xlog:help`, output |
| Used `debug` yet very few logs | Exact selector or rare events | Check actual tag sets, try controlled wildcard |
| Wrote `filesize=10MB` | Suffix may be invalid | Use `filesize=10M` per `-Xlog:help` |
| Set `filecount` on stdout | Rotation applies only to file outputs | Use `file=...` or container log management |
| `filecount=0` keeps growing | `0` means do not rotate | Use positive `filecount` / retention policy |
| JVM does not create file | Missing directory, permissions, wrong working dir, or startup failure | Check stderr/exit status and filesystem |
| File overwritten after restart | Output filename not unique | Use `%p`, `%t`, and file archival policy |
| Specified `time` yet order looks different | Framework enforces fixed decorator order | Check actual files and parser; do not assume input order |
| Two `-Xlog` flags on same file don't merge | Later option can override earlier output | Combine selectors in a single option |
| Logs mixed with app stdout | Shared output stream | Use a separate file or parser/metadata to separate |
| Disk full despite rotation | Multiple JVMs/old files, other logs, or tight quota | Budget disk, monitor, clean up per policy |
| Logs lack PID/instance | Missing decorators or duplicate container PIDs | Add `pid` and collector metadata |
| Content exposes paths/hosts/secrets | Raw runtime/log info shared verbatim | Minimize fields, redact before sharing |
| Used JDK 21 flags on another runtime | Tags/options differ by release/VM | Run `java -Xlog:help` on the service's actual JDK |

### 11.1 Tips for Reading Parser Errors

If the JVM fails to start due to `-Xlog` flags, capture the **full stderr message and exit code** in a test environment and check:

1. Are colons `:` in the right positions?
2. Are `+`, `*`, `,`, and `=` used correctly inside `what`?
3. Do the tag, level, and decorator appear in `java -Xlog:help` on the target JDK?
4. Is output `stdout`, `stderr`, or `file=...` with a valid path?
5. Are file options placed properly after decorators?
6. Are JVM options placed **before** the main class or `-jar` on the Java command line?
7. Does shell quoting preserve the whole argument when spaces, wildcards, or special characters appear?

A common confusing example:

```bash
java -jar app.jar "-Xlog:gc=info:file=gc.log"
```

Placed **after** `app.jar`, `-Xlog...` becomes an **application argument**, not a JVM option. Correct syntax:

```bash
java "-Xlog:gc=info:file=gc.log" -jar app.jar
```

In POSIX shells, `*` can undergo pathname expansion if unquoted. Wrapping the entire `-Xlog:...` string in quotes whenever wildcards or spaces appear avoids unintended shell expansion. On Windows, quoting and path separators differ; verify the exact arguments received by the JVM.

## 12. Operational Impact and Log Reliability

### 12.1 Excessive Logging Can Perturb the System Being Measured

`-Xlog:all=trace` or overly broad wildcards can generate massive message volume, increasing CPU/I/O, lock contention, and disk usage depending on collector/level. When measuring p99 latency or GC overhead, heavy logging can **skew measurements**. Always record the exact logging config for each run; never compare benchmarks across different log profiles and blame code alone.

Start at `info` with narrow tags; raise to `debug/trace` only temporarily. For GC logs, record timestamps, collector type, JDK version, and load pattern for analysis. If an expected event is missing, evaluate whether it didn't happen or was filtered by selection/level/collector.

### 12.2 Time Synchronization and Correlation

- `uptime` measures elapsed time since JVM start; it is not a substitute for UTC timestamps.
- `utctime` or `time` helps align with app logs/OS/JFR; make timezones explicit.
- `pid` can collide across containers or restarts; rely on container/instance IDs from orchestration.
- `tags` and `level` help debug parsers and separate GC events from safepoints.
- With rotation, events span multiple files: parsers must read in sequence without dropping or double-counting file boundaries.
- With a log collector, distinguish **when the JVM emitted the event** from **when the collector received the message**.

### 12.3 Asynchronous Logging and Potential Event Loss

Some modern HotSpot JDKs support `-Xlog:async`, letting producers push log messages into a buffer written by a background thread. This is a **global setting**; in JDK 21 the buffer is bounded and **messages can be dropped when full**. Never enable async and assume log line counts are lossless. When counting events or performing forensics, assess reliability, load conditions, and drop reporting. Synchronous logging is also not a durability guarantee if a process is killed or storage fails.

### 12.4 Sensitivity of JVM Logs

Logs can contain hostnames, process IDs, class/package names, file paths, JVM flags, runtime metadata, or environment details. Never paste full logs into public channels without vetting recipients; apply proper storage permissions and retention. GC logs generally contain less application payload than heap dumps, yet **you must never assume they are automatically safe to share publicly**.

## 13. Pre-Deployment `-Xlog` Configuration Checklist

- [ ] Verified which HotSpot/JDK release the service runs and checked `-Xlog:help` for required selectors.
- [ ] `what` uses exact tags/tag sets, `+` for AND, `,` for OR selectors, `*` for wildcard, `=` for level threshold.
- [ ] `info/debug/trace` level matches the diagnostic goal and expected overhead.
- [ ] Output explicitly set to `stdout`/`stderr`/`file=...`; empty slot colons `:` placed properly.
- [ ] Decorators are sufficient for analysis (at least timestamp/uptime, level, tags as needed).
- [ ] If using files, directory exists, JVM user has write access, and path/quota/volume/collector are verified.
- [ ] `filecount` and `filesize` configured appropriately, recognizing size rotation is not day-based retention.
- [ ] Filenames reduce collisions across restarts/replicas, e.g., `%p` and `%t`.
- [ ] Able to correlate logs with application metrics, GC/JFR, and process identity.
- [ ] No other `-Xlog` flag inadvertently overrides the same output or disables warnings/errors.
- [ ] Tested in an equivalent environment, not merely syntax-checked with `-version`.
- [ ] Assessed overhead, storage size, data security, and rollback plan for debug profiles.
- [ ] Have a reliable way to read rotated logs without gaps or duplicates.

## 14. Self-Check Exercises

**Q1.** Why does `-Xlog:gc=debug` not guarantee lines with the `gc+heap` tag set?

**Answer:** without a wildcard, `gc` matches the **exact** `gc` tag set. To broaden to tag sets containing GC, use `gc*=debug`; to match the exact tag set containing GC and heap, use `gc+heap=debug`.

**Q2.** To send GC logs to stdout using only `uptime,tid` decorators, what syntax must you use?

**Answer:** `-Xlog:gc::uptime,tid`. The `::` keeps the output slot empty (defaulting to stdout) followed by decorators.

**Q3.** Does `-Xlog:gc*=info:file=gc.log:time,level,tags:filecount=0` rotate files?

**Answer:** No. `filecount=0` means **no rotation**, so the file can grow continuously if the JVM logs heavily. For size-based rotation, use a positive `filecount` and an appropriate `filesize`.

**Q4.** Is `-Xlog:gc,safepoint` the same as `-Xlog:gc+safepoint`?

**Answer:** No. Comma defines **two independent selectors**, whereas plus defines **one tag set containing both tags**. Without wildcards, matching is exact on the tag set.

**Q5.** Why can `UnifiedXlogDemo` not promise exactly five GC log lines and one rotation?

**Answer:** log output depends on the actual JVM/collector/events, and a brief run is unlikely to emit enough events or bytes to rotate. `System.gc()` is only a JVM hint, not a guarantee of identical events across environments.

**Q6.** Does `java -jar app.jar -Xlog:gc` enable JVM logging?

**Answer:** Not as intended, because options after `-jar app.jar` are passed as **application arguments**. Use `java -Xlog:gc -jar app.jar`.

## References

- [Oracle JDK 21 — The java Command, Unified JVM Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html#enable-logging-with-the-jvm-unified-logging-framework): syntax, tags/levels, decorators, outputs/rotation, examples, and default logging.
- [Oracle JDK 17 — The java Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): checking syntax on Java 17+ baseline.
- [Oracle JDK 21 — jcmd VM.log](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): dynamic logging configuration, checking options, and attach permission limits.
- [OpenJDK JEP 158 — Unified JVM Logging](https://openjdk.org/jeps/158): tag sets, levels, output/decorator design, and file rotation.

**Key takeaway:** read `-Xlog` in order **`what : output : decorators : output-options`**. Use `+` for combined tags, `,` for multiple selectors, `*` for wildcard tag-set matching, and `=level` for thresholds. Verify log files, paths, permissions, and rotation on a real JVM; never treat "no logs seen" as proof no event occurred. In production, configure the minimum needed, watch overhead, and retain time/instance metadata for verifiable diagnostics.
