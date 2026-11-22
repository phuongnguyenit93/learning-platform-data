# Migrating legacy GC logs to Unified Logging

When upgrading Java from JDK 8 to JDK 11, 17, 21, or newer versions, certain legacy Garbage Collection (GC) logging options may no longer work as expected. Flags such as `-XX:+PrintGCDetails`, `-XX:+PrintGCTimeStamps`, `-XX:+PrintGCDateStamps`, `-Xloggc`, `-XX:+UseGCLogFileRotation`, or collector-specific detail flags commonly appeared in startup scripts, Maven/Gradle tasks, application servers, and container configurations. Starting in JDK 9, Java introduced **Unified JVM Logging**, using a unified syntax beginning with `-Xlog`.

Migrating is not just swapping flag names. Unified Logging changes how events are selected, verbosity levels, timestamp formats, tags, output destinations, and file rotation mechanisms. A configuration may still let the JVM boot yet write fewer details, write excessive logs, add I/O overhead, or break legacy parsers/GC dashboards expecting older field formats.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **JVM and Performance**, focusing on migrating traditional GC logs to Unified Logging, reading `-Xlog` syntax accurately, mapping flags conditionally, planning retention and rotation, testing on target JDKs, and preserving GC observability throughout upgrades.

**Ultimate goal:** the JVM starts with valid configuration, writes GC logs containing sufficient operational information without leaking data or filling disks, and log analysis tooling parses events accurately for the running collector and JDK.

## 1. Why is GC logging important during migration?

Garbage Collection affects heap usage, pause durations, response latency, throughput, and memory reclamation. GC logs supply evidence to answer:

- Did the application pause due to GC or safepoints/other causes?
- Are young collections occurring unusually frequently?
- Did Full GCs occur, and why?
- After GC, how much live data remains in the heap?
- Do GC pauses breach latency SLOs?
- Did allocation pressure shift after upgrading the JDK?
- Is the active collector the intended one?
- Did increasing heap size or tuning GC flags actually help?
- Before an `OutOfMemoryError`, how did GC behave?

A GC log helps distinguish memory leaks, allocation spikes, promotion pressure, heap sizing, and collector-change effects. However, **GC logs are not the entire performance monitoring system**. Combine them with metrics, thread dumps, JFR, heap dumps where appropriate, and application-level telemetry.

### 1.1. Observability model

~~~text
JVM process
   |
   +--> Unified Logging (-Xlog:gc*)
   |         |
   |         +--> GC events, heap, phases, age, ergonomics
   |         +--> Timestamps, levels, tags, GC IDs
   |
   +--> JFR / JMX / metrics
   |         |
   |         +--> CPU, allocation, pause latency
   |
   +--> Application metrics
             |
             +--> Throughput, request latency, errors
             |
             v
   Analyze pre- and post-migration data together
~~~

Preserving observability requires considering both **logs emitted by the JVM** and **systems collecting, parsing, and displaying them**.

## 2. Transition milestone between legacy GC logging and Unified Logging

Java 8 and older generations commonly used `PrintGC...` flags and `-Xloggc`. JDK 9 introduced Unified JVM Logging via JEP 158 and moved GC logging into the new framework via JEP 271.

| Stage | Common configuration | Points to watch |
|---|---|---|
| JDK 8 | -XX:+PrintGC, -XX:+PrintGCDetails, -Xloggc:... | Format depends on collector and flags |
| JDK 9 and later | -Xlog with tags, levels, and outputs | Multiple JVM log sources share one unified mechanism |
| JDK 11/17/21 and modern JDKs | -Xlog is the primary interface | Old flags may warn, be removed, or have release-specific transition behavior |
| Future JDKs | -Xlog and release-specific policies | Verify syntax, tags, collectors, and output policies on the exact JDK |

Never assume all legacy flags will be silently translated by a newer JVM. A flag may be accepted in one JDK release, flagged obsolete in another, or cause the JVM to reject startup.

### 2.1. Upgrading the JDK and changing collectors are two independent variables

Upgrading an application from Java 8 to Java 17 may simultaneously switch from Parallel GC to G1 GC via defaults or explicit config. In that case, GC log differences stem not only from Unified Logging, but also from **different collectors and event types**.

Example:

~~~text
Before:
  JDK 8 + Parallel GC + legacy GC flags

After:
  JDK 17 + G1 GC + Unified Logging
~~~

If GC pause charts shift, separate the impacts of runtime, collector, heap sizing, workload, and log format. Never compare raw "GC event" counts directly between two different collectors to conclude one is better.

## 3. Traditional GC logging flags

Example historical startup configuration:

~~~bash
java \
  -XX:+PrintGC \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -Xloggc:/var/log/myapp/gc.log \
  -XX:+UseGCLogFileRotation \
  -XX:NumberOfGCLogFiles=10 \
  -XX:GCLogFileSize=20M \
  -jar app.jar
~~~

This illustrates historical flags, not a recommended command for newer JDKs.

Intended capabilities:

- Log basic GC events.
- Log more detailed heap/collector information.
- Add timestamps since JVM start or wall-clock date/time.
- Write to a file instead of console only.
- Rotate files by size and count.

Some applications also used `-XX:+PrintTenuringDistribution`, `-XX:+PrintAdaptiveSizePolicy`, `-XX:+PrintReferenceGC`, `-XX:+PrintHeapAtGC`, or other JDK/collector-specific flags.

Migration challenge: there is no perfect 1:1 mapping from every legacy `Print...` flag to one single `-Xlog` selector. Detail granularity, event names, tags, and formats can differ. Migrate according to **observability goals**.

## 4. What is Unified Logging?

Unified Logging is the logging subsystem for multiple internal JVM components beyond GC. Depending on the JDK, it can report on class loading, safepoints, modules, threads, compilation, and other subsystems.

General syntax:

~~~text
-Xlog[:[selections][:[output][:[decorators][:output-options]]]]
~~~

Parts:

1. **selections:** picks tag sets and log levels, e.g., `gc*=info`.
2. **output:** sends logs to stdout, stderr, or a file.
3. **decorators:** attaches metadata per log line, such as time, uptime, level, tags.
4. **output-options:** configures output behavior, such as `filecount` and `filesize` for file rotation.

Example:

~~~bash
java -Xlog:gc* -jar app.jar
~~~

How to read it: enables GC-tagged messages at the default matching level, written to the JVM's default output with default decorators.

Customized example:

~~~bash
java \
  -Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M \
  -jar app.jar
~~~

How to read it:

- `gc*=info`: captures GC logs at `info` level and related tag combinations.
- `file=logs/gc.log`: writes to a file.
- `time,uptime,level,tags`: prepends metadata per line.
- `filecount=10,filesize=20M`: configures file rotation.

Relative paths depend on the JVM process working directory. On Windows, shell quoting, path separators, and file permissions may differ.

## 5. Tags, levels, and tag sets

### 5.1. Tags classify events

In Unified Logging, a message can carry one or more tags such as:

~~~text
gc
gc,heap
gc,phases
gc,age
safepoint
os
class
~~~

Available tags and emitted events depend on JVM implementation and version. Never invent tag names assuming the JVM supports them.

### 5.2. Levels determine verbosity

Common levels:

| Level | Meaning | Typical use |
|---|---|---|
| off | Disables logging for selection | Selective suppression |
| error | Errors | Critical signals |
| warning | Warnings | Notable events |
| info | Operational info | Common production baseline |
| debug | Detailed diagnostic info | Enabled selectively |
| trace | Highly verbose detail | Short-term deep investigations |

Within a selector, a level threshold includes messages at that level and higher severity per logging rules. Using `gc*=trace` can generate heavy log volume and I/O overhead. Never leave trace on long-term just to "have complete data".

### 5.3. gc differs from gc*

Example:

~~~bash
-Xlog:gc
~~~

selects messages whose tag set matches `gc` per tag-set matching rules. It may omit messages carrying combined tags such as `gc,heap` or `gc,phases`.

By contrast:

~~~bash
-Xlog:gc*
~~~

uses a wildcard to select tag sets related to `gc`, including combinations with additional tags per Unified Logging rules.

This is a key distinction when replacing `-XX:+PrintGCDetails`: **-Xlog:gc does not mean -Xlog:gc***.

### 5.4. Combining multiple tags with a plus sign

~~~bash
-Xlog:gc+heap=debug
~~~

selects GC messages carrying the combined `gc` and `heap` tags at `debug` level per logging matching rules.

~~~bash
-Xlog:gc+phases=debug
~~~

selects GC phase details when the collector/JDK emits events with those tags.

To see which events are actually emitted, check `-Xlog:help` and real logs on your target JDK.

### 5.5. Multiple selectors inside one -Xlog option

Example:

~~~bash
-Xlog:gc*=info,safepoint=info
~~~

selects both GC and safepoint logs. To add extra granularity for one subset:

~~~bash
-Xlog:gc*=info,gc+heap=debug,safepoint=info
~~~

Verify effective log levels on overlapping tag sets. For complex setups, write selectors explicitly and test on the exact deployed JDK.

## 6. Output: console or file?

Unified Logging can write to:

- stdout.
- stderr.
- A file via `file=...`.
- Other outputs supported by the JVM/provider in that version.

Console example:

~~~bash
java -Xlog:gc*:stdout:uptime,level,tags -jar app.jar
~~~

File example:

~~~bash
java -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M -jar app.jar
~~~

Stderr example:

~~~bash
java -Xlog:gc*:stderr:uptime,level,tags -jar app.jar
~~~

### 6.1. Choices in containers

In Docker/Kubernetes, writing to stdout/stderr has advantages:

- Logs are collected via the platform's standard mechanism.
- No manual log directory management inside containers.
- Integrates easily with existing log aggregation pipelines.

Disadvantages also exist:

- GC logs and application logs mix in the same stream.
- Collector logs can become noisy when debug is enabled.
- Logging pipelines may handle multiline lines or truncation unexpectedly.
- Platform quotas and retention differ from JVM file rotation.

Writing to a file has advantages:

- Separates GC logs from application logs.
- Works cleanly with file-based analysis tools.
- Uses JVM-controlled file rotation.

Disadvantages include managing storage, permissions, sidecars/file shippers, volume mounts, and cleanup.

**Pick a log transport strategy suited to your infrastructure**, instead of blindly copying traditional VM flags into containers.

## 7. Decorators: capturing time and context

A Unified Logging line usually starts with bracketed prefixes carrying metadata from the selected decorators.

Illustrative example:

~~~text
[2026-11-12T10:30:00.250+0700][3.624s][info][gc] GC(12) Pause Young ... 28M->12M(256M) 3.40ms
~~~

Exact fields and formats vary by JDK, collector, and decorators. Do not treat the sample line as an immutable fixed format.

Common decorators:

| Decorator | Meaning |
|---|---|
| time | System wall-clock timestamp |
| utctime | UTC timestamp |
| uptime | Time since JVM startup |
| timemillis | Epoch timestamp in milliseconds where supported |
| uptimemillis | JVM uptime in milliseconds |
| timenanos / uptimenanos | Sub-millisecond resolution where supported by JDK |
| level | Log level |
| tags | Event tags |
| pid | Process identifier |
| tid | Thread identifier |

Check supported decorator names and formats via `-Xlog:help` on the running JDK.

### 7.1. Why include both time and uptime?

- `time` correlates GC pauses with application logs and wall-clock dashboards.
- `uptime` helps trace JVM lifecycle phases such as startup and warm-up.

When running multiple JVM instances, individual uptimes cannot serve as global timestamps. For centralized logs, keep `time` and attach instance/pod identity via log collector metadata.

### 7.2. Do not confuse event time with ingestion time

A GC event may happen at 10:30:00 while a sidecar ships it at 10:30:03. If dashboards sort by ingestion timestamp, pauses misalign with request latency spikes.

Parse event timestamps from the configured decorator, timezone, and precision, keeping ingestion timestamps separate for pipeline monitoring.

## 8. Migration table for legacy GC logging flags

The table below gives a **starting point** for migration. Do not treat it as a strict 1:1 semantic equivalence across every JDK and collector.

| Legacy JDK purpose | Typical legacy flag(s) | Reference Unified Logging |
|---|---|---|
| Basic GC events | -XX:+PrintGC | -Xlog:gc |
| Detailed GC info | -XX:+PrintGCDetails | -Xlog:gc* |
| Write GC to file | -Xloggc:logs/gc.log | -Xlog:gc*:file=logs/gc.log |
| Include JVM uptime | -XX:+PrintGCTimeStamps | -Xlog:gc*:stdout:uptime,level,tags |
| Include wall-clock time | -XX:+PrintGCDateStamps | -Xlog:gc*:stdout:time,level,tags |
| Time spent at safepoints | -XX:+PrintGCApplicationStoppedTime | -Xlog:safepoint or JDK-matching selection |
| Track object ages | -XX:+PrintTenuringDistribution | Check gc+age at debug/trace |
| GC heuristics/ergonomics | -XX:+PrintAdaptiveSizePolicy | Check gc+ergo* at appropriate level |
| Heap state around GC | -XX:+PrintHeapAtGC | Check gc+heap at debug/trace |
| Rotate GC logs | -XX:+UseGCLogFileRotation, -XX:NumberOfGCLogFiles, -XX:GCLogFileSize | output-options filecount and filesize |

Notes:

- Some legacy flags existed only on specific JDKs or collectors.
- Information once printed on one line may now span multiple tags/levels.
- "Application stopped time" is not identical to GC pauses alone; inspect safepoint logs.
- For broad default GC details, `-Xlog:gc*` is a practical starting point without guaranteeing identical output to `PrintGCDetails`.
- For each observability need, trigger controlled GC events and inspect real output on the target JDK.

### 8.1. From PrintGCDetails to -Xlog:gc*

Old:

~~~bash
java -XX:+PrintGCDetails -jar app.jar
~~~

New:

~~~bash
java -Xlog:gc* -jar app.jar
~~~

On newer JDKs, logs may emit collector initialization, pause events, heap before/after stats, and phases across different tags. Do not expect identical line formats or units to Java 8.

### 8.2. From -Xloggc to file output

Old:

~~~bash
java -Xloggc:/var/log/myapp/gc.log -jar app.jar
~~~

New:

~~~bash
java -Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags -jar app.jar
~~~

If paths contain spaces or shell-special characters, quote properly for the OS and launcher.

### 8.3. From timestamp flags to decorators

Old:

~~~bash
-XX:+PrintGCDateStamps
-XX:+PrintGCTimeStamps
~~~

New:

~~~bash
-Xlog:gc*:stdout:time,uptime,level,tags
~~~

Specify outputs and decorators explicitly rather than relying on defaults whenever parsers or retention policies depend on a stable format.

## 9. Log file rotation in Unified Logging

Long-running GC logs can consume significant disk space. Unified Logging provides built-in rotation options for file outputs.

Example:

~~~bash
java \
  -Xlog:gc*:file=/var/log/myapp/gc.log:time,uptime,level,tags:filecount=10,filesize=20M \
  -jar app.jar
~~~

Concept:

- `filesize=20M` sets the target file size threshold before rotation per JVM mechanics.
- `filecount=10` controls how many rotated log files are retained.
- Once triggered, older files rotate and writing continues to a fresh file.

Verify exact rotation semantics on your target JDK. Never multiply `10 × 20M` naively and claim an absolute hard ceiling under every condition; active files, metadata, log managers, and operational factors also apply.

### 9.1. Differs from legacy rotation flags

Legacy configuration:

~~~bash
-XX:+UseGCLogFileRotation
-XX:NumberOfGCLogFiles=10
-XX:GCLogFileSize=20M
~~~

Do not keep these legacy flags after migrating to `-Xlog`. Use Unified Logging `output-options`, check startup, and verify actual rotated files on disk.

### 9.2. File paths, permissions, and cleanup

Before deploying, confirm:

- Target directory exists or is created by deployment.
- The JVM OS user holds write permission.
- Disk quota is sufficient.
- Retention policy is configured.
- Multiple JVM instances never share one log file.
- On shared volumes, each instance uses a distinct path.
- File shippers reading rotated logs neither drop nor duplicate events.
- When rolling back to an older JDK, startup flags and log paths match that runtime.

### 9.3. Avoid multiple JVMs writing to one file

If two JVM processes both write to:

~~~text
/var/log/myapp/gc.log
~~~

overwrites, interleaved lines, or rotation conflicts can happen depending on output mechanics. Separate paths per instance/container or write to stdout/stderr tagged with process/pod metadata.

Unified Logging supports output filename placeholders in some versions, such as process IDs or startup timestamps. Before using them, verify placeholder syntax and escaping on your exact target JDK rather than guessing.

## 10. Choosing a production baseline

A balanced setup for many apps starts with GC events at `info` level, adding targeted detail as needed.

Example:

~~~bash
java \
  -Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=8,filesize=25M \
  -jar app.jar
~~~

This is an example rather than a one-size-fits-all formula. Account for heap size, collector, GC frequency, log transport, and retention.

### 10.1. Minimal logging

~~~bash
-Xlog:gc=info
~~~

May suit systems relying primarily on JFR/JMX metrics and needing only basic pause logging. For deep troubleshooting, however, it can lack tag and phase details.

### 10.2. Short-term diagnostics

~~~bash
-Xlog:gc*=debug
~~~

Or target specific tag combinations:

~~~bash
-Xlog:gc*=info,gc+heap=debug,gc+phases=debug
~~~

When `trace` is needed for one area:

~~~bash
-Xlog:gc*=info,gc+age*=trace
~~~

Never turn on `trace` globally across production JVMs without measuring log volume. Often JFR is a more efficient tool for time-boxed diagnostics.

### 10.3. Do not enable debug merely because "a new collector probably needs it"

G1, Parallel, ZGC, and other collectors emit distinct messages. Enable only the tags and levels answering active operational questions. Excessive logging degrades performance or buries critical events.

## 11. Unified Logging and safepoint logging

GC pauses often coincide with moments when Java threads must stop or coordinate. Yet **not every safepoint is GC**, and **not every concurrent collector activity causes a major stop-the-world pause**.

Distinguish:

- GC event: a memory collection cycle or phase.
- Stop-the-world GC pause: an application stop caused by a collector phase requiring threads to pause.
- Safepoint: a state/point where the JVM coordinates Java threads for certain runtime operations.
- Application stopped time: may include non-GC causes depending on measurement and log source.
- Concurrent GC work: collector work running concurrently with application threads, whose total duration is not all pause time.

### 11.1. Enabling safepoints

Example:

~~~bash
-Xlog:safepoint=info
~~~

Combined:

~~~bash
-Xlog:gc*=info,safepoint=info:stdout:time,uptime,level,tags
~~~

Emitting safepoint events helps diagnose application freezes that GC logs alone cannot explain.

### 11.2. Do not sum GC log durations mechanically

A collector may perform long concurrent cycles alongside brief pauses. If a parser adds every duration in GC logs into "application downtime", numbers will be wrong.

Dashboards must accurately classify events as pauses, concurrent cycles, evacuations, cleanups, or other phases. Naming depends on collector and JDK version.

## 12. How to read a GC Unified Logging line

Illustrative log line:

~~~text
[2026-11-12T10:30:00.250+0700][3.624s][info][gc] GC(12) Pause Young (Normal) (G1 Evacuation Pause) 128M->72M(512M) 5.4ms
~~~

Breakdown:

- Wall-clock timestamp: `2026-11-12T10:30:00.250+0700`.
- Uptime: `3.624` seconds since JVM startup.
- Level: `info`.
- Tags: `gc`.
- `GC(12)`: an identifier linking messages belonging to one GC activity per JDK conventions.
- `Pause Young...`: event/collector description.
- `128M->72M(512M)`: heap occupancy before/after and reported capacity in the sample message.
- `5.4ms`: logged event duration.

Note: exact numbers, formats, and units vary by collector and release. For concurrent events, reported durations or heap figures may carry different semantics.

### 12.1. GC IDs are not timestamps

`GC(12)` groups related messages within one JVM run, yet restarts reset the GC ID sequence. When centralized logs aggregate multiple instances, GC IDs alone cannot uniquely identify events cluster-wide.

Combine process/container IDs, startup timestamps, and GC IDs when correlating across instances.

### 12.2. Before/after heap does not directly equal RSS

GC heap usage tracks managed Java heap reported per event. Process RSS also includes metaspace, thread stacks, code cache, direct buffers, native libraries, and other memory regions.

If RSS rises while after-GC heap stays flat, investigate off-heap/native memory rather than GC logs alone.

### 12.3. Pause time does not equal request latency

A GC pause can delay requests, yet request latency also reflects network, thread contention, I/O, and application logic. Correlate timestamps and metrics instead of looking at pause durations in isolation.

## 13. GC log formats vary by collector

A system may use:

- Serial GC.
- Parallel GC.
- G1 GC.
- ZGC.
- Shenandoah GC on supporting JDKs/vendors.
- Other collectors or modes depending on JDK distribution.

These collectors do not share an identical event model. Even for the same collector, log messages can change across JDK releases.

### 13.1. G1

Can emit:

- Pause Young.
- Mixed collections.
- Concurrent marking.
- Heap regions.
- Humongous allocations.
- Remembered sets and GC phases.

Tags like `gc+heap` or `gc+phases` help deep investigations, yet never treat every line as a pause.

### 13.2. ZGC

ZGC emphasizes concurrent operations to minimize pause times. It logs cycles and phases with differing durations. Parsers written strictly for Parallel/G1 may misclassify ZGC logs.

### 13.3. Shenandoah

Shenandoah also logs collector- and version-specific concurrent and pause events. Confirm the collector is supported in your distribution and configured properly before enabling collector-specific tags/flags.

### 13.4. Do not upgrade JDK and switch collectors without a baseline

If switching collectors simultaneously, capture baseline and target metrics:

- p50/p95/p99 request latency.
- GC pause distribution.
- Heap allocation rate.
- CPU utilization.
- Throughput.
- RSS and container memory.
- Concurrent GC activity.
- Full GC frequency where meaningful for the collector.

That evaluates real runtime behavior rather than comparing log text alone.

## 14. Using -Xlog:help

Before adopting flags from old docs, run:

~~~bash
java -Xlog:help
~~~

This prints the exact logging capabilities of that JDK, including:

- Available log levels.
- Available tags.
- Outputs and decorators.
- Output file and rotation options.
- Selector syntax.

On machines with multiple JDK installs, run **the exact `java` executable used in deployment**, not just the workstation default.

### 14.1. Why avoid copying unverified tags?

A tag mentioned in a blog or another JDK version may not exist or may carry different info on your JDK. Invalid configs can cause the JVM to reject startup while parsing VM options.

Safe sequence:

1. Pick the target JDK.
2. Run `java -Xlog:help`.
3. Build a minimal configuration.
4. Run a startup smoke test.
5. Trigger controlled GC activity in testing.
6. Verify the generated log file/output actually contains needed data.

## 15. Distinguishing command-line, environment, and application configuration

GC logging configures the **JVM process**, not application logger levels in Log4j, Logback, or `java.util.logging`.

Example:

~~~bash
java -Xlog:gc* -jar app.jar
~~~

differs completely from:

~~~properties
logging.level.root=INFO
~~~

Changing Spring Boot's `logging.level.root` does not enable GC logs. Conversely, `-Xlog:gc*=debug` does not raise Logback's application loggers to `DEBUG`.

### 15.1. Where startup flags can live

- Shell scripts or Windows services.
- Dockerfile `ENTRYPOINT`/`CMD`.
- Kubernetes Deployment `args` and `env`.
- `JAVA_TOOL_OPTIONS` or `JDK_JAVA_OPTIONS` per launcher behavior.
- Application server domain configs.
- Gradle test JVM arguments.
- Maven Surefire/Failsafe `argLine`.
- Systemd service units.
- Cloud runtime startup options.
- CI performance test jobs.

When an environment combines multiple option sources, inspect the final resolved JVM command line. Valid flags in a script ignored by the launcher have no effect.

### 15.2. Maven test JVM

Conceptual example in Surefire plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <version>3.2.5</version>
    <configuration>
        <argLine>
            -Xlog:gc*:file=target/test-gc.log:uptime,level,tags
        </argLine>
    </configuration>
</plugin>
~~~

Version and config are illustrative. Check which JVM Surefire forks, any `argLine` injected by coverage/agent tools, and plugin versions. Never overwrite an existing `argLine` and accidentally drop Java agents.

### 15.3. Gradle test JVM

Example:

~~~groovy
tasks.withType(Test).configureEach {
    jvmArgs(
        "-Xlog:gc*:stdout:uptime,level,tags"
    )
}
~~~

This configures the JVM forked by Gradle for matching `Test` tasks, not production JVMs. If the Gradle daemon uses one JDK while tests use another toolchain, test against the real target runtime.

## 16. Configuration for containers and Kubernetes

Containers typically route logs across multiple hops:

~~~text
JVM stdout/stderr
       |
       v
Container runtime log
       |
       v
Log collector / shipper
       |
       v
Centralized log store
~~~

Sending GC logs to stdout:

~~~bash
java -Xlog:gc*=info:stdout:time,uptime,level,tags -jar app.jar
~~~

routes them alongside container logs per infrastructure conventions.

### 16.1. Advantages

- Avoids mounting writable log directories.
- Leverages platform rotation and retention.
- Automatically attaches pod, namespace, container, and node metadata.
- Uses standard cluster log collection.

### 16.2. Things to watch

- If app logs also use stdout, pipelines must separate GC logs via tags/prefixes.
- Collectors may parse in-line timestamps differently from container runtime timestamps.
- Burst GC logging can increase log ingestion costs.
- Container restarts must be recognized when GC IDs and uptimes reset.
- Kubernetes log rotation/retention is independent of JVM `filecount`/`filesize`.
- Sidecars/agents must support the matching JDK and collector versions.

### 16.3. File logs inside containers

If choosing file output:

~~~bash
-Xlog:gc*:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
~~~

verify `/logs` is a writable mount, the JVM user holds write permission, and file shippers can read it. In read-only container filesystems, an unmounted `/logs` path prevents the JVM from opening the log output.

Avoid writing large GC logs to ephemeral filesystems without quotas/cleanup; containers risk eviction or disk exhaustion.

## 17. Where can legacy GC log parsers break?

Parsers built for JDK 8 often search for patterns like:

~~~text
[GC ...
[Full GC ...
[Times: user=...
~~~

Unified Logging uses different prefixes and message formats, for example:

~~~text
[3.624s][info][gc] GC(12) Pause Young ...
~~~

Parser compatibility can break because:

- Timestamps switched from legacy formats to new decorators.
- `[info][gc]` prefixes were added.
- GC IDs appear across messages.
- Event names changed.
- Heap units and field placements shifted.
- Newer collectors emit different phase logs.
- Related metrics no longer sit on a single line.
- Rotated file naming changed.
- Structured fields go unrecognized by legacy parsers.

### 17.1. Do not patch parsers with loose regexes

A regex matching every `ms` number can conflate:

- GC pause durations.
- Concurrent cycle durations.
- Time to reach safepoint.
- Time spent at safepoint.
- Subphase durations.
- Application event durations.

Dashboards can report wildly wrong downtime or throughput without raising parse errors.

Use parsers supporting **your exact JDK version + collector + Unified Logging format**, or maintain parser test suites backed by representative fixtures.

### 17.2. Verify key dashboards

Examples:

- GC pause p95/p99.
- Full GC counts.
- Percentage of JVM time spent in GC.
- Post-GC heap occupancy.
- Allocation rate.
- Collector metadata.
- OutOfMemory incidents.
- Time to safepoint.

For concurrent collectors, define "GC time percentage" carefully. Never sum every concurrent cycle duration, divide by uptime, and label it stop-the-world pause time.

### 17.3. Use log fixtures

Store sample fixture files:

~~~text
fixtures/
  jdk8-parallel-gc.log
  jdk11-g1-unified.log
  jdk17-g1-unified.log
  jdk21-g1-unified.log
  jdk21-zgc-unified.log
~~~

Filenames are illustrative and do not imply every project uses every combination. Fixtures should capture startup, pauses, concurrent events, rotation, and shutdown rather than a single tidy line.

## 18. Comparing GC before and after a JDK upgrade

To assess migration impact, compare under matched conditions:

| Factor | Before | After |
|---|---|---|
| Runtime JDK | Build/vendor/update | Build/vendor/update |
| GC collector | Parallel/G1/... | Parallel/G1/... |
| Heap | `-Xms`/`-Xmx` | `-Xms`/`-Xmx` |
| Container memory | Limit and host | Limit and host |
| Workload | Throughput, payload | Equivalent |
| GC logging | Legacy | Unified |
| Log parser | Version | Version supporting new format |
| Application version | Commit/release | Commit/release |
| JVM flags | Actual flag set | Actual flag set |

If collector, heap sizing, and application code all change at once, attributing pause shifts to Unified Logging becomes nearly impossible.

### 18.1. Metrics to use

- Pause counts and latency distributions.
- Longest pause within the observation window.
- Time between collections.
- Post-GC heap occupancy.
- Allocation rate and promotion pressure where available.
- CPU cost.
- Application p95/p99 latency.
- Throughput.
- Full GC frequency where meaningful per collector.
- RSS and container memory headroom.

### 18.2. Logs do not cover every metric

Some metrics are better captured via JFR, JMX, Micrometer, or collector-specific counters. Do not infer unlogged metrics with false precision. Pick the right telemetry tool for each question.

## 19. Running JDK 8 and newer JDKs side by side in the same organization

Large organizations may run Java 8 services alongside Java 17/21 services. A shared global env var holding `-Xlog:gc*` will break Java 8 launches.

### 19.1. Choose flags per runtime JDK

~~~text
JDK 8:
  -XX:+PrintGCDetails
  -XX:+PrintGCDateStamps
  -Xloggc:logs/gc.log

JDK 9+:
  -Xlog:gc*:file=logs/gc.log:time,uptime,level,tags
~~~

Branch based on **the actual launching JDK**, not Maven compiler release or `sourceCompatibility`. Bytecode targeting 8 may execute on JDK 17; in that case, JVM logging flags must follow JDK 17.

### 19.2. Do not habitually stuff both flag sets onto one JVM

Mixing legacy and Unified flags can cause warnings, startup failures, or unexpected log output depending on the JDK. Maintain one documented GC logging flag set per runtime group and verify startup.

### 19.3. Java version detection

Startup scripts can detect JDK versions to select matching flags. However, version parsers must safely handle differing version formats across Java 8, 9+, vendor builds, and patch updates.

Whenever your platform allows, manage profiles or container images per runtime family instead of complex shell detection scripts.

## 20. GC logs and operational security

GC logs primarily record heap metadata, class-loading/collector behavior, and JVM lifecycle events rather than application payloads by default. Even so, they can disclose:

- File paths and deployment layout.
- JVM process names, PIDs, and instance IDs.
- Activity windows, uptime, capacity, and traffic patterns.
- Selected class/tag/debug metadata depending on level.
- Infrastructure and memory sizing details.

Enabling tags beyond GC or setting `trace` widens exposure. Enforce:

- Least-privilege log file read/write permissions.
- Controlled retention and cleanup.
- Never attaching raw GC logs to public issues when sensitive metadata is present.
- Scoped access permissions on centralized logs.
- Disk safeguards so logs never fill volumes and take down services.
- Time-boxed diagnostic debug policies.

### 20.1. OOME dumps differ from GC logs

Heap dumps can contain live objects and application data, including secrets. Never confuse GC logs with heap dumps. When enabling `-XX:+HeapDumpOnOutOfMemoryError`, enforce stricter security and disk limits for dump files.

## 21. Common -Xlog configuration errors

### 21.1. JVM fails to start due to syntax error

Missing colons, invalid tags, or bad `output-options` make the JVM fail with invalid `-Xlog` option errors.

Resolution:

1. Capture the full JVM command line.
2. Run `java -Xlog:help` on the target JDK.
3. Start simple with `-Xlog:gc*`.
4. Add output, decorators, and rotation step by step.
5. Smoke-test startup before deploying.

### 21.2. JVM starts yet produces no GC log

Possible reasons:

- No GC occurred during observation.
- Selector was too narrow.
- Logs went to stdout/stderr rather than the expected file.
- Relative file path resolved elsewhere.
- Container directory was not mounted.
- Log rotated to a different filename.
- Startup flags were never actually passed to the JVM.

Never conclude "GC didn't run" solely from an empty file.

### 21.3. Only brief GC lines appear without heap/phase details

Often caused by using `-Xlog:gc` instead of `-Xlog:gc*` or setting too low a level on desired tags. Enable `gc*` or targeted tag sets in a test environment.

### 21.4. Excessive logging spikes disk usage

`gc*=debug` or `gc*=trace` emits high event volumes; combined with heavy traffic and unmanaged rotation, disk consumption climbs fast.

Fix: drop back to `info` or narrow tags, bound output and retention, and monitor collector quotas.

### 21.5. Log parser miscounts GC pauses

If a parser counts concurrent GC phase durations as stop-the-world pauses, reported latency spikes falsely. Classify events accurately per collector/JDK, cross-check app metrics, and update the parser.

### 21.6. GC log dates/times drift from dashboards

Check decorators, timezones, host/container clocks, offsets, and ingestion timestamps. Never treat JVM uptime as an epoch timestamp.

### 21.7. Legacy flags report Unrecognized VM option

Retired `PrintGC...` or old rotation flags are rejected by newer runtimes. Migrate flags cleanly to `-Xlog` matching intent, auditing all JVM args instead of enabling `-XX:+IgnoreUnrecognizedVMOptions` to silence errors blindly.

### 21.8. JVM fails opening the GC log file

Caused by missing parent paths, permission denied, read-only filesystems, or container security policies. Configure valid paths and test under the exact service OS user.

### 21.9. Multiple -Xlog flags behave unexpectedly

Passing multiple `-Xlog` options targeting overlapping outputs/selectors can yield non-obvious overrides. Define each output destination and its selections cleanly instead of copy-pasting overlapping flags.

### 21.10. Newer JDK emits different collector/event tags

The exact same `-Xlog:gc*` option emits different content when switching from G1 to ZGC or upgrading JDK releases. Update parsers rather than forcing Java 8 regexes onto new formats.

## 22. Workflow for migrating legacy GC log configurations

### Step 1 — Collect active configurations

Record:

- JDK vendor, version, update/build.
- Active collector.
- Heap sizing and container limits.
- Startup flags across all sources.
- Log paths, rotation, and retention.
- Tools, parsers, and dashboards consuming GC logs.
- Observability needs: pauses, heap, safepoints, tuning.

Never inspect one startup script while missing flags injected by Docker, systemd, Maven/Gradle, or application servers.

### Step 2 — Map the intent of each legacy flag

Example:

| Legacy flag | Intent |
|---|---|
| `PrintGCDetails` | Detailed GC visibility |
| `PrintGCDateStamps` | Correlate with wall-clock time |
| `PrintGCTimeStamps` | Correlate with JVM uptime |
| `Xloggc` | Write to file |
| `UseGCLogFileRotation` | Prevent unbounded file growth |
| `PrintTenuringDistribution` | Track object age and promotion |
| `PrintGCApplicationStoppedTime` | Investigate safepoint/stop times |

You do not need to reproduce every legacy text line verbatim. Simply ensure **every operational question the old flags answered still has an answer**.

### Step 3 — Build minimal -Xlog config

Example:

~~~bash
-Xlog:gc*=info:file=logs/gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

When safepoints are needed:

~~~bash
-Xlog:gc*=info,safepoint=info:file=logs/jvm-gc.log:time,uptime,level,tags:filecount=10,filesize=20M
~~~

### Step 4 — Verify via -Xlog:help

Run on the exact target JDK. If collector-specific tags are needed, verify they exist and emit expected data.

### Step 5 — Startup smoke test

Launch the JVM with the new config and verify:

- Exit status and zero startup errors.
- Expected GC collector active.
- File or console output exists.
- Decorator formats match expectations.
- Write permissions and paths work.
- No warnings/errors from leftover legacy flags.

### Step 6 — Generate workload and inspect logs

Run a realistic allocation/GC test workload. Never invoke `System.gc` in production just to force log output; `System.gc` may behave unexpectedly depending on flags and collectors. Test via realistic traffic or controlled allocation in staging.

### Step 7 — Confirm rotation and ingestion

Verify rotated filenames, `filecount`/`filesize`, sidecar/agent collection completeness, safe restart behavior without overwrites, and dashboard parsing.

### Step 8 — Compare metrics and roll out gradually

Canary the change while monitoring GC pauses, after-GC heap, CPU, p99 latency, and log volume. If changing collectors simultaneously, record both changes explicitly to avoid misattribution.

### Step 9 — Retire legacy flags

Once verified, remove unused legacy GC flags and update runbooks and parser docs. Never leave one production container running Java 8 flags while peers run Unified Logging.

## 23. Complete migration example: Java 8 to Java 17

### 23.1. Java 8 config before migration

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -XX:+PrintGCDetails \
  -XX:+PrintGCDateStamps \
  -XX:+PrintGCTimeStamps \
  -Xloggc:/logs/gc.log \
  -XX:+UseGCLogFileRotation \
  -XX:NumberOfGCLogFiles=5 \
  -XX:GCLogFileSize=20M \
  -jar orders-service.jar
~~~

This illustrates a historical setup selecting G1 with detailed GC logging, timestamps, file output, and rotation.

### 23.2. Java 17 config after migration

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -Xlog:gc*=info:file=/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders-service.jar
~~~

Key changes:

- Preserved heap and collector initially to minimize variables.
- Replaced `PrintGC...` flags with `-Xlog`.
- Retained wall-clock time, uptime, level, and tags.
- Kept file output and rotation with matching operational intent.
- Removed legacy rotation flags.

### 23.3. If safepoint analysis is needed

~~~bash
java \
  -Xms2g \
  -Xmx2g \
  -XX:+UseG1GC \
  -Xlog:gc*=info,safepoint=info:file=/logs/jvm.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar orders-service.jar
~~~

This adds safepoint data to the specified output; older parsers expecting GC-only lines may need tag filtering.

### 23.4. Verification checks

After updating, validate independently:

1. JVM boots cleanly with zero invalid option errors.
2. Log file is created.
3. A test workload triggers GC events.
4. Logs include timestamps and GC IDs.
5. File rotation triggers as configured.
6. Dashboards distinguish pauses from concurrent phases.
7. Application latency and throughput do not degrade due to log volume.
8. Rollback config supplies JDK-8-compatible flags if reversion is needed.

## 24. Relationship between GC logs and JVM memory tuning

During migrations, teams sometimes bundle legacy tuning flags alongside logging flags and carry everything verbatim onto the new JDK. Separate them cleanly:

- **Logging flags:** control what information is logged.
- **GC selection flags:** choose the collector.
- **GC tuning flags:** adjust pause goals and heuristics.
- **Heap flags:** set memory bounds and region configs.
- **Diagnostic flags:** expose extra telemetry.

Example:

~~~text
-Xlog:gc*                  -> logging
-XX:+UseG1GC               -> collector selection
-Xmx4g                     -> heap maximum
-XX:MaxGCPauseMillis=200   -> collector tuning goal where applicable
~~~

Translating `PrintGCDetails` to `-Xlog` is no reason to silently alter `-Xmx`, `MaxGCPauseMillis`, or the collector. Keep unrelated variables stable in early phases to isolate real impact.

### 24.1. GC logs reveal problems without fixing them automatically

If GC logs reveal frequent collections under high live heap occupancy, real fixes involve cutting allocations, fixing leaks, sizing heap properly, or tuning the collector. Raising logging to `debug`/`trace` will not speed up GC; it may actually add CPU/I/O cost.

## 25. Dynamic logging and short-term diagnostics

Several modern JDKs support adjusting Unified Logging on a live JVM via administrative tools like `jcmd` with `VM.log`. Exact capabilities and syntax depend on JDK version, permissions, and environment.

Diagnostic check command:

~~~bash
jcmd <pid> help VM.log
~~~

`<pid>` is a placeholder for the process ID, not literal syntax.

For short-term production debugging, check dynamic logging support on your target JDK rather than restarting services. Keep in mind:

- Requires matching attach/management permissions.
- Container runtimes may block attach or `jcmd`.
- Never adjust sensitive services casually without governance.
- Verify which log outputs and rotation rules are active.
- Revert levels to baseline after troubleshooting.
- Dynamic updates may disappear upon JVM restart.

**Never assume every production JVM permits `jcmd`.** Follow operational and security policies.

## 26. Testing log volume and overhead

`gc*=trace` can spike log generation rates, especially under heavy allocation workloads and verbose collector phase events.

Measure:

- Bytes logged per minute.
- Messages per second.
- CPU overhead of formatting/writing logs.
- Disk I/O and write latency.
- Log shipper memory and buffers.
- Ingestion cost.
- Risk of dropped logs when pipelines saturate.
- Impact on application tail latency.

### 26.1. Never benchmark overhead from one unrepeatable run

Comparing logging-off vs. trace across two runs with different workloads proves nothing. Hold load, heap, collector, JDK, and environment steady across enough runs to gauge variance.

### 26.2. Production baseline vs. debug profile

Document two distinct profiles:

**Baseline:** captures enough data for GC pauses and heap trends with controlled log volume.

**Diagnostic:** enables extra tags/levels for a specific issue, with explicit expiration and an owner.

Never let a diagnostic debug profile become the permanent default once an incident closes.

## 27. Operational checklist after migrating to Unified Logging

- [ ] Confirmed target JDK runtime, vendor, and build.
- [ ] Inspected `java -Xlog:help` on the exact target JDK.
- [ ] Inventoried every legacy GC logging flag across all startup sources.
- [ ] Separated logging flags from heap and collector tuning flags.
- [ ] Chose `gc` vs. `gc*` intentionally based on required details.
- [ ] Set an appropriate production level; kept debug/trace time-boxed.
- [ ] Added `safepoint` selector where stop-time analysis is needed.
- [ ] Chose file vs. stdout/stderr output per infrastructure.
- [ ] Explicitly specified `time`/`uptime`/`level`/`tags` decorators.
- [ ] Verified paths, permissions, and disk quotas.
- [ ] Configured rotation and retention when logging to files.
- [ ] Ensured multiple JVMs never share one log file carelessly.
- [ ] Passed startup smoke tests without invalid options.
- [ ] Verified test workloads generate expected events.
- [ ] Verified log parsers support the exact JDK and collector.
- [ ] Confirmed dashboards separate GC pauses from concurrent work.
- [ ] Checked timestamps against timezone and ingestion drift.
- [ ] Verified log shippers capture rotated files cleanly.
- [ ] Monitored log volume and I/O overhead.
- [ ] Compared heap, pauses, CPU, and latency during canary.
- [ ] Kept older-JDK-compatible flags in rollback runbooks.
- [ ] Removed legacy GC logging flags once migration completed.

## 28. Migration logging decision record template

~~~text
APPLICATION
  Service:
  Current JDK/vendor/build:
  Target JDK/vendor/build:
  Current collector:
  Target collector:
  Heap -Xms/-Xmx:
  Container memory limit:

LEGACY GC LOGGING
  Old JVM flags:
  Log path:
  Timestamp format:
  Rotation and retention:
  Parser/dashboard:
  Questions answered by legacy logs:

UNIFIED LOGGING
  Selected -Xlog:
  Selected tags:
  Levels:
  Output:
  Decorators:
  Filecount/filesize:
  Expected log volume:
  Safepoint logging?:

DEPLOYMENT
  Host/container:
  JVM user:
  Writable log paths:
  Log shipper:
  Rotation ownership:
  Multi-instance naming:
  Retention and access policy:

VALIDATION
  java -Xlog:help:
  Startup smoke test:
  GC workload test:
  Log readback:
  Rotation test:
  Parser compatibility:
  Dashboard metrics:
  Canary latency/CPU:
  Rollback flags:

DECISION
  Approved baseline:
  Diagnostic profile:
  Owner:
  Exceptions:
  Removal milestone for old flags:
~~~

Records must state the exact **JDK version, collector, and `-Xlog` selection**. Writing merely "GC logging enabled" does not let others reproduce monitoring reliably.

## 29. Common misconceptions

### "-Xlog:gc and -Xlog:gc* are identical"

False. The wildcard expands selection across GC-related tag combinations. `gc*` is generally broader than `gc`.

### "Just replacing -Xloggc with -Xlog keeps the exact same log format"

False. Prefixes, tags, levels, event names, and collector semantics can all change. Re-test parsers and dashboards.

### "PrintGCDetails maps cleanly to one exact selector"

No universal 1:1 guarantee exists across every JDK. `-Xlog:gc*` is a starting point; specialized tags may require debug/trace levels.

### "If the new JDK rejects old GC flags, just add IgnoreUnrecognizedVMOptions"

Never do this. Silencing flag errors can blind observability or mask misconfiguration. Migrate flags properly by intent and smoke-test startup.

### "Timestamps in GC logs are always UTC"

False. `time`, `utctime`, and runtime timezones differ. Always read the configured format explicitly.

### "A long concurrent GC cycle means the app paused that entire time"

False. Concurrent work and stop-the-world pauses measure different things.

### "GC heap usage equals total JVM RSS"

False. Native memory, thread stacks, direct buffers, and other spaces sit outside the Java heap.

### "Switching to stdout eliminates retention management"

False. Container runtimes and log aggregation pipelines still enforce rotation, quotas, and retention; responsibility merely shifts.

### "Setting filecount and filesize guarantees never filling the disk"

Never treat it as an absolute guarantee. Multiple JVM instances, file shippers, secondary outputs, or volume layouts can still exhaust storage.

### "A Java 8 GC parser automatically handles all Java 21 logs"

False. Formats, events, and collectors change; use compatible parsers and fixture tests.

### "Raising the log level improves GC performance"

False. Logging yields diagnostic visibility, usually at minor overhead, without tuning GC execution.

### "Upgrading the JDK and seeing the app start means GC logging migration succeeded"

Insufficient. File output, rotation, parsers, dashboards, and operational alerts can still fail silently.

## 30. Conclusion

Migrating legacy GC logs to Unified Logging is essential to Java compatibility migrations because it directly determines post-upgrade JVM observability and performance troubleshooting.

Core principles:

1. **From JDK 9 onward, `-Xlog` is the primary unified logging interface.** Migrate old GC configs by observability intent rather than mechanical string swaps.
2. **Master selections, tags, levels, outputs, and decorators.** Distinguish `gc` from `gc*` and `info` from `debug`/`trace`.
3. **Manage rotation, retention, and log transport.** File output in VMs/containers and stdout in Kubernetes imply different operational responsibilities.
4. **Never treat GC log formats as immutable stable APIs.** Collectors, JDKs, and tags evolve; parsers must keep pace.
5. **Separate GC pauses, safepoints, and concurrent activity.** Never misreport latency by summing arbitrary durations.
6. **Maintain comparable baselines.** Hold collectors, heap sizing, and workloads steady during initial JDK verification.
7. **Test the full operational path.** Startup, event emission, file rotation, shipping, dashboards, and rollback must all be verified.

A clean Unified Logging migration does more than silence warnings about retired GC flags. It keeps operations teams able to see how the JVM reclaims memory, explain performance shifts, and catch real regressions on newer JDKs without paying unexpected log-volume or operational costs.
