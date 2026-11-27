# Reading Recording Data with the jfr Tool and JDK Mission Control

> **Topic:** Java 17  
> **Chapter:** Diagnostics and JFR  
> **Goal:** Record JVM activity with Java Flight Recorder (JFR), quickly inspect recording files using the `jfr` command, and analyze timelines, events, threads, GC, allocations, and performance issues using JDK Mission Control (JMC).

## 1. What Are JFR and JDK Mission Control?

**Java Flight Recorder (JFR)** is the JVM's event recording system. It collects data on application and runtime activity over time, such as:

- CPU load and thread execution time.
- Garbage collection, allocations, and memory pressure.
- Lock contention and blocked threads.
- I/O, file, socket, and system operations enabled in the recording configuration.
- Exceptions, class loading, JIT compilation, and other JVM events.

JFR stores data in a recording, typically with the `.jfr` extension. This file holds timestamped events, thread details, stack traces, and data fields specific to each event type.

**JDK Mission Control (JMC)** is a graphical tool for analyzing JFR recordings. JMC helps you:

- View a recording overview and recorded time window.
- Locate periods of high CPU, GC pauses, allocations, and lock contention.
- Browse events by timeline, thread, or event type.
- Drill down from an event to its stack trace and relevant code path.
- Run automated analysis rules to surface signals worth investigating.

In Java 17, the `jfr` command is included with the JDK. JMC is a separate tool installable from a JDK Mission Control distribution; do not assume every JDK 17 installation includes the JMC desktop application.

### 1.1. How Does JFR Differ from Application Logs?

Application logs record messages explicitly emitted by application code. JFR records events from the JVM, runtime, and other instrumented components. Both sources complement each other:

| Source | Best Answers the Question |
|---|---|
| Application logs | Which request failed? Which user called it? What happened in business terms? |
| Metrics | How do CPU, memory, latency, and throughput change over time? |
| JFR recording | Inside the JVM, which threads ran, waited on locks, allocated objects, or hit GC at what time? |
| Thread dump | At the moment of capture, which stack frame and state was each thread in? |
| Heap dump | Which objects retain heap and what are their reference relationships? |

JFR does not replace logs or metrics. For example, JFR can show that request-handling threads waited on a monitor during a window, while application logs link that window to specific request IDs or business operations.

### 1.2. Can JFR Be Used in Production?

JFR is designed to record events with low overhead when appropriately configured. It is commonly used to observe JVMs in production, including continuous recordings or time-bounded recordings.

Still, overhead is never zero. Enabling many detailed events, deep stack traces, high-frequency events, or long durations can increase CPU usage, recording file size, and I/O. Start with an appropriate configuration, test under representative workload, and monitor impact before broad rollout.

## 2. Preparing the Java 17 Environment

Requirements:

- JDK 17 running the application or compatible with the target process to diagnose.
- `jfr` and `jcmd` from the JDK's `bin` directory.
- A JDK Mission Control version supporting Java 17 recordings.
- Access permissions to the JVM process and recording output directory.

Verify tools:

```bash
java -version
jfr --version
jcmd -h
```

If the shell cannot find `jfr` or `jcmd`, invoke them by full path under `JAVA_HOME/bin` or add the JDK `bin` directory to `PATH`.

### 2.1. Identifying the Right JVM Process

The command:

```bash
jcmd -l
```

lists JVM processes visible to the current user. Output typically includes the PID and launch class/module name.

Example:

```text
18420 com.acme.orders.Main
19108 org.springframework.boot.loader.launch.JarLauncher
```

In subsequent examples, `<pid>` is the actual PID of the process to record. Do not use the illustrative PID on your own machine.

If the application runs in a container, run tools inside that container or an environment with matching process namespace access. A PID seen from the host may differ from the PID inside the container.

## 3. Creating a JFR Recording

Two approaches are commonly used: starting a recording at JVM launch or attaching to a running JVM with `jcmd`.

### 3.1. Enabling Recording at Application Startup

Example recording a 2-minute window using `profile` settings:

```bash
java -XX:StartFlightRecording:filename=orders-profile.jfr,settings=profile,duration=2m \
     -jar orders-service.jar
```

Parameters:

- `filename`: output recording file.
- `settings=profile`: uses a more detailed collection configuration for time-bounded performance investigation.
- `duration=2m`: stops the recording after 2 minutes.

If you want the recording to run throughout the process lifetime, omit `duration` and add `dumponexit=true` to dump on JVM exit:

```bash
java -XX:StartFlightRecording:filename=orders-runtime.jfr,settings=default,dumponexit=true \
     -jar orders-service.jar
```

Long-running recordings should generally use `default` settings and appropriate size/age caps. Verify disk capacity and environment retention policies.

### 3.2. Starting a Recording on a Running JVM with jcmd

This is convenient when diagnosing a running application without restarting:

```bash
jcmd <pid> JFR.start name=orders-profile settings=profile duration=2m filename=orders-profile.jfr
```

If successful, the JVM returns confirmation of the started recording and its recording ID. The file is written to a path writable by the process.

A default recording can be started with:

```bash
jcmd <pid> JFR.start name=orders-default settings=default duration=5m filename=orders-default.jfr
```

`default` fits general observation and longer durations; `profile` records more detailed data for investigating a short window. The configuration governs which events are enabled, thresholds, periods, and stack traces.

### 3.3. Starting a Continuous Recording and Dumping When Needed

You can have the JVM maintain a disk-backed recording and dump to a file when an issue is spotted:

```bash
jcmd <pid> JFR.start name=orders-continuous settings=default disk=true maxage=1h maxsize=250m
```

When you need to capture data:

```bash
jcmd <pid> JFR.dump name=orders-continuous filename=orders-incident.jfr
```

Continuous recordings retain a recent window around the time of an incident. Options:

- `disk=true`: writes recording data to disk using JFR's repository mechanism.
- `maxage=1h`: caps the age of retained data.
- `maxsize=250m`: caps the size of retained recording data.

These limits are examples; size them based on event rate and disk capacity. If a recording does not use disk, data stays in memory under different resource constraints.

### 3.4. Checking, Dumping, and Stopping Recordings

List existing recordings:

```bash
jcmd <pid> JFR.check
```

Dump a running recording:

```bash
jcmd <pid> JFR.dump name=orders-continuous filename=orders-snapshot.jfr
```

Stop a recording:

```bash
jcmd <pid> JFR.stop name=orders-continuous
```

Dump and stop are distinct operations. `JFR.dump` writes a snapshot of current recording data to a file; `JFR.stop` terminates the specified recording. During investigation, dump first if you want to keep data before stopping the recording.

### 3.5. Automatically Dumping on JVM Exit

For recordings started via `jcmd`, you can pass `dumponexit=true` when starting:

```bash
jcmd <pid> JFR.start name=orders-exit settings=default disk=true dumponexit=true
```

This instructs the JVM to write the recording when the process exits normally per JFR behavior. On forced kills or power loss, do not assume final data will always be dumped completely.

### 3.6. Viewing JFR Command Help

Available names and options can vary across specific JDK builds. Check help directly on the JDK you are using:

```bash
jcmd <pid> help JFR.start
jcmd <pid> help JFR.dump
jcmd <pid> help JFR.stop
```

And check CLI help:

```bash
jfr help
jfr help summary
jfr help print
jfr help configure
```

This verifies exact syntax rather than copying commands from a different JDK release.

## 4. Reading Recordings with the jfr Command

JDK 17 includes the `jfr` CLI to inspect metadata, statistics, and event contents inside recording files without opening JMC.

### 4.1. Viewing a Recording Summary

```bash
jfr summary orders-profile.jfr
```

The summary typically reports:

- Recording start and end timestamps.
- Duration.
- JFR/JVM version and recorded environment info.
- List of event types.
- Event counts and corresponding data sizes.

Start with `summary` to verify the recording covers the incident time window and contains the expected event types. If key events are absent, check recording configuration before deeper analysis.

### 4.2. Printing Event Contents

Print a recording as text:

```bash
jfr print orders-profile.jfr
```

Large files produce huge output. Usually filter by event type:

```bash
jfr print --events jdk.ExecutionSample orders-profile.jfr
jfr print --events jdk.GarbageCollection orders-profile.jfr
jfr print --events jdk.JavaMonitorEnter orders-profile.jfr
```

You can request deeper stack traces:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 64 orders-profile.jfr
```

Event names must exist in the recording's metadata and have been enabled in settings. If no data appears, verify event names with `jfr metadata` or check the event list in JMC.

### 4.3. Viewing Event Metadata

```bash
jfr metadata orders-profile.jfr
```

Metadata describes event types and defined data fields. It helps when you need to know:

- Exact event names.
- Which fields an event carries.
- Field data types and meanings.
- Whether the event is defined by the JVM or another component.

A JFR recording does not necessarily contain every event the JVM knows about. Metadata describes event types; `summary` shows which events actually appear in the recording.

### 4.4. Formatting Output as JSON or XML

To feed events into external processing tools, print events in structured formats:

```bash
jfr print --json --events jdk.GarbageCollection orders-profile.jfr
```

Or:

```bash
jfr print --xml --events jdk.GarbageCollection orders-profile.jfr
```

Output can be large, especially for high-frequency events. Filter events before converting and avoid storing sensitive data in uncontrolled locations.

### 4.5. Filtering by Event and Time

The `jfr print` CLI supports filtering by event type and certain time criteria depending on the JDK version. On Java 17, inspect exact supported options:

```bash
jfr help print
```

When correlating many events along a timeline, JMC is usually easier because it supports visual filtering and navigation. The CLI excels at quick checks, extracting specific event groups, or integration into analysis scripts.

### 4.6. Minimal CLI Workflow Example

Suppose you have `orders-incident.jfr`:

```bash
jfr summary orders-incident.jfr
jfr print --events jdk.GarbageCollection orders-incident.jfr
jfr print --events jdk.ExecutionSample --stack-depth 64 orders-incident.jfr
```

Read the summary first, then pick events aligned with your investigation hypothesis. If GC pauses are high, inspect GC events; if CPU is high, inspect execution samples and stack traces. Avoid printing an entire recording when you only need a targeted group of events.

## 5. Analyzing JFR Files with JDK Mission Control

JMC provides a graphical UI to browse recordings and connect events over time. Tab names or layouts may differ slightly across JMC versions, though the core analytical workflow remains similar.

### 5.1. Opening a Recording File

1. Install a JDK Mission Control version compatible with Java 17 JFR files.
2. Launch JMC.
3. Open the recording file using File Open or by dragging the `.jfr` file into the JMC window.
4. Wait for JMC to parse and index the data.
5. Open the Overview page to inspect timestamps, JVM details, and primary metrics.

JMC is a standalone application; having JDK 17 installed does not guarantee JMC is present on the machine. If a file was produced by a newer JDK, use a JMC version supporting that format/events. Do not assume old JMC versions understand all newer events.

### 5.2. Starting from the Overview Page

The Overview page helps confirm the recording has adequate data for investigation:

- When did the recording start and end?
- Which JVM, Java version, and OS produced the file?
- Does the recording window cover the incident timeframe?
- How did CPU load and heap usage change?
- Were there notable GC pauses?
- Did thread count rise abnormally?
- Which event groups appear frequently?

If the incident happened at 10:05 while the recording only started at 10:10, the recording may lack the initial trigger. Confirm the exact time window before drawing conclusions.

### 5.3. Using Automated Analysis

JMC includes automated analysis rules to highlight notable signals in a recording, such as:

- High CPU load or threads spending considerable time in certain stacks.
- Significant GC pauses or allocation pressure.
- Lock contention.
- Slow I/O.
- JVM settings or runtime behaviors worth checking.

Rule findings are **investigation leads**, not definitive diagnoses. A warning may match normal expected workload; conversely, a clean rule does not prove the application has no bugs. Open rule details, inspect underlying events, and correlate with failure timestamps and application metrics/logs.

### 5.4. Using Event Browser and Timeline

The Event Browser lets you inspect recorded events, typically filterable by:

- Event type.
- Time range.
- Thread.
- Stack trace.
- Field values such as duration or size, if supported by the event.

The timeline shows which events occurred before, during, and after an anomalous interval. For instance, rising CPU may coincide with execution samples in a set of methods; a long thread wait may coincide with monitor contention or socket reads.

Preserve time context while filtering. Filtering down to a single event type without checking neighboring events can hide important causal relationships.

## 6. Reading Key Event Groups

JFR defines many event types. Exact names and presence depend on recording settings, JVM version, and workload. The groups below are routinely helpful when diagnosing Java applications.

### 6.1. CPU and Execution Samples

Events such as `jdk.ExecutionSample` capture stack samples of executing threads at sampling ticks. In JMC, examine frequently sampled stacks to pinpoint CPU-intensive code.

Workflow:

1. Open the CPU/Method Profiling page or corresponding analysis section.
2. Select the high-CPU time window.
3. Inspect top methods or call trees by sample count.
4. Expand stack traces to identify callers and callees.
5. Link methods to specific requests, batches, or workloads via logs/metrics.

**Execution samples are statistical sampling data.** If a method accumulates many samples, it likely accounts for a substantial share of execution time in the sampled window; sample count is not an exact count of method invocations or absolute per-call CPU time.

Questions to ask:

- Which methods appear frequently in samples?
- Is CPU concentrated in application code, frameworks, or libraries?
- Are there hot loops or redundant data transformations?
- Is CPU growth driven by one thread or many threads?
- Do stack traces differ between normal operation and high load?

Do not optimize a method solely because it tops the list. Weigh sample share, workload, thread count, and latency impact.

### 6.2. Garbage Collection and Heap

Events such as `jdk.GarbageCollection`, `jdk.GCPhasePause`, and related GC events describe garbage collection activity.

In JMC, inspect:

- Start/end timestamps of GC cycles.
- Pause durations and pause phases.
- Collector type and GC cycle type.
- Heap occupancy before/after GC when provided by events.
- Periods of elevated allocation.
- GC frequency and impact on throughput/latency.

Some interpretation guidelines:

| Sign | Investigation Direction |
|---|---|
| Long pauses coincide with latency spikes | Check GC phases, heap occupancy, allocation pressure, and slow-request timing |
| Frequent GC cycles | Check allocation rate, object lifetimes, heap size, and workload |
| Post-GC heap climbs across cycles | Check live set, caches, collections, and retaining references |
| Many allocation samples from one stack | Locate code creating many objects; see if allocations can be reduced or reasonably reused |

Not every GC pause is a bug. GC is normal JVM behavior; compare durations and frequencies against latency targets and load levels.

### 6.3. Allocation and Object Pressure

Events like `jdk.ObjectAllocationSample` sample where objects are allocated. In JMC, stack traces help locate methods generating heavy allocations.

For example, an API converting thousands of records may create many temporary objects:

```java
List<String> labels = records.stream()
        .map(record -> record.getName() + ":" + record.getId())
        .toList();
```

If the recording shows allocation samples concentrated in this pipeline, consider:

- Are unnecessary intermediate strings being created?
- Is the same data processed repeatedly?
- Can temporary objects be reduced while keeping code clear?
- Is an unbounded cache extending object lifetimes?

Note: `ObjectAllocationSample` is a sampled event, not a complete inventory of every allocated object. Do not treat sample counts as exact total objects or exact total bytes allocated without understanding how the event is configured and sampled.

### 6.4. Lock Contention and Thread Waiting

Events like `jdk.JavaMonitorEnter` record time threads spent waiting on monitors; `jdk.ThreadPark` helps inspect threads parked in synchronization constructs.

In JMC:

1. Open Threads or Lock Instances/Lock Profiling depending on the JMC version.
2. Locate long or repeated wait intervals.
3. Identify waiting threads and stack traces at the time of waiting.
4. Locate lock-holding threads or related code paths if recorded.
5. Check whether locks are held across I/O, external service calls, or slow work.

Example:

```java
public synchronized void updateInventory() {
    // Holding a monitor during a remote service call
    // can force other threads to wait for a long time.
    remoteService.refresh();
    updateLocalState();
}
```

One improvement may be shrinking the lock scope and moving I/O outside the critical section, while preserving data consistency invariants. JFR reveals contention signals; fixing code requires understanding business invariants.

### 6.5. File I/O and Socket I/O

Events like `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead`, and `jdk.SocketWrite` report I/O activity alongside duration/size/endpoint depending on event and settings.

When investigating:

- Inspect operations with long durations.
- Distinguish threads waiting on I/O from threads burning CPU.
- Check payload sizes and call counts.
- Follow stack traces into file/client/network libraries.
- Correlate with server-side or dependency logs.

Not every I/O event is recorded in every configuration. Settings often specify thresholds to log only sufficiently slow operations. Thus, seeing no slow events does not guarantee zero I/O; events may be disabled or thresholds too high.

### 6.6. Exceptions and Class Loading

Events such as `jdk.JavaExceptionThrow`, `jdk.ExceptionStatistics`, and class loading events help determine:

- Are exceptions spiking within a time window?
- Do exceptions repeat with the same stack trace?
- Is the application loading classes abnormally at runtime?
- Is a framework or plugin causing a spike in class loading?

Exceptions are not always the root cause of performance trouble. Some apps use exceptions for control flow, yet excessive exception throwing increases CPU and logging overhead. Inspect exception types, frequencies, stack traces, and context.

## 7. Choosing the Right Recording Configuration

JFR uses `.jfc` configuration files to govern enabled events, duration thresholds, sampling periods, stack traces, and other parameters.

### 7.1. default and profile

The JDK ships two common configurations:

| Configuration | Purpose | Typical Use |
|---|---|---|
| `default` | General monitoring with low data volume and low overhead | Continuous or long-duration recordings |
| `profile` | Captures more detailed data for performance investigations | Short recordings during issue reproduction |

`profile` is not always the best choice. It records extra events and stack traces, generating larger files or higher overhead depending on workload. For continuously running services, keep a `default` background recording and take short `profile` recordings when targeted investigation is needed.

### 7.2. Location of JFC Configuration Files

In JDK 17, bundled configurations usually reside under:

```text
JAVA_HOME/lib/jfr/
    default.jfc
    profile.jfc
```

Inspect these files to see which events are enabled and their current thresholds. Do not edit the JDK's shared default configuration files directly; create a separate configuration file for your application or environment.

### 7.3. Creating Custom Configurations with jfr configure

Example starting from `profile` and tuning the monitor contention event threshold:

```bash
jfr configure --input profile.jfc --output orders-diagnostic.jfc \
    jdk.JavaMonitorEnter#threshold=10ms
```

Then use the custom configuration file:

```bash
jcmd <pid> JFR.start name=orders-locks settings=orders-diagnostic.jfc duration=3m filename=orders-locks.jfr
```

This example merely shows how to pass one setting override. Verify valid events and options with `jfr help configure` and the metadata of your running JDK.

### 7.4. Enabling Events and Tuning Thresholds Intentionally

Some events record only when duration exceeds a threshold. Lowering the threshold catches shorter operations at the cost of higher event counts and file sizes.

When tuning configuration:

1. Define the hypothesis: CPU, allocation, locks, I/O, or GC?
2. Enable only required events.
3. Set thresholds based on target latency and workload.
4. Test with representative data.
5. Measure overhead, recording size, and signal usefulness.
6. Store JFC files alongside deployment docs for reproducibility.

Do not set every threshold to zero or enable every event indiscriminately. Overly noisy recordings add overhead, bloat files, and obscure critical signals.

### 7.5. Stack Traces and Sampling

Stack traces tie events back to application call paths, though not all events carry stack traces and not all events record at identical frequencies.

- Execution samples are periodic, hence statistical.
- Allocation samples are sampled views of allocation sites.
- I/O or lock events may record only upon exceeding thresholds.
- Some events record only when explicitly enabled in JFC.

When comparing two recordings, use equivalent configurations. If one recording captures stack traces and detailed events while the other does not, metrics cannot be compared directly.

## 8. Performance Investigation Workflow with JMC

A data-rich recording is only useful when the investigation question is clear. Follow this workflow:

### Step 1 — Identify the Incident Window

Align JFR timestamps with:

- Alerts/metrics showing CPU, latency, or error-rate spikes.
- Application logs and request IDs.
- Deployment or configuration change timestamps.
- Load increases or batch job start times.

Confirm whether the recording also covers the period immediately preceding the incident.

### Step 2 — Check Overview and Automated Analysis

Note CPU, heap, GC, thread count, and warnings. Pick one or two prominent signals to dig into. Avoid opening all events at once and trying to hunt through massive volumes of data.

### Step 3 — Select Event Groups by Symptom

| Symptom | Events / Data Groups to Inspect |
|---|---|
| High CPU | Execution samples, thread CPU load, method profiling |
| Latency spiking with GC | Garbage collection, GC phases/pauses, heap usage |
| Rising allocations | Object allocation samples, allocation stack traces |
| Long thread waits | Java monitor enter, thread park, thread states |
| Slow I/O | File read/write, socket read/write |
| Rising exceptions | Java exception throw, exception statistics |
| Rising class loading | Class load/unload and class loader events |

Event names may vary or be absent in a recording; follow the events actually recorded.

### Step 4 — Locate Stack Traces and Call Paths

When spotting abnormal events:

1. Select the event or event group.
2. Open the stack trace.
3. Identify the first frame in application code.
4. Inspect callers to understand why the code was invoked.
5. Check the thread, timestamp, and neighboring events.

Do not stop at a framework method without tracing which application code triggered it.

### Step 5 — Formulate and Verify a Hypothesis

Example:

- Hypothesis: latency spikes due to a shared lock.
- Evidence: many threads wait on the same monitor during the spike window; stack traces point to the same critical section.
- Verification: cross-check with latency metrics and logs; capture a recording after the fix to compare.

JFR helps form hypotheses and pinpoint where to look. Proving root cause requires combining logs, metrics, code inspection, and controlled testing.

### Step 6 — Compare Baseline and Post-Change Recordings

When evaluating a fix:

- Use similar workload and duration.
- Use identical JFR settings.
- Compare CPU samples, allocations, GC pauses, lock waits, and I/O durations.
- Check application latency/throughput metrics.
- Verify the change did not simply shift cost to another subsystem.

One metric dropping does not guarantee the whole system improved. For example, cutting allocations via caching can inflate the heap live set; check both sides.

## 9. Practice Example: Investigating High CPU

Suppose metrics show a service's CPU spiking sharply for several minutes without a corresponding rise in error rate.

### 9.1. Recording

If the process is running, start a short recording:

```bash
jcmd <pid> JFR.start name=cpu-incident settings=profile duration=3m filename=cpu-incident.jfr
```

While recording, reproduce or wait for the problematic workload. Once finished, inspect the file:

```bash
jfr summary cpu-incident.jfr
jfr print --events jdk.ExecutionSample --stack-depth 64 cpu-incident.jfr
```

### 9.2. Analyzing in JMC

1. Open `cpu-incident.jfr` in JMC.
2. Confirm the recording spans the CPU spike window.
3. Open CPU/Method Profiling and select the exact time range.
4. Inspect methods/call trees with high execution sample counts.
5. Expand stack traces to locate frequently appearing application code.
6. Cross-check threads, GC, and I/O to tell whether CPU spiked due to computation, GC, or other work.

For example, if samples cluster in JSON parsing, check parse frequency, payload sizes, intermediate object creation, and callers. If samples cluster in GC, pivot to analyzing allocation and GC events.

### 9.3. Verifying After the Fix

After optimizing, capture a new recording with similar configuration and workload. Compare:

- Execution sample share in the fixed method.
- CPU load and active thread count.
- Allocation samples and GC pauses.
- Latency/throughput from metrics.

Do not rely solely on raw sample counts from two recordings with different durations, configurations, or loads to claim performance improved.

## 10. Practice Example: Investigating Threads Waiting on Locks

Suppose latency spikes when concurrent requests update the same data structure.

### 10.1. Recording

```bash
jcmd <pid> JFR.start name=lock-incident settings=profile duration=5m filename=lock-incident.jfr
```

If the current profile does not capture sufficient monitor events for your needs, create a custom JFC with an appropriate threshold and re-record.

### 10.2. Finding Contention

In JMC:

1. Open Threads or Lock Instances/Lock Profiling.
2. Filter to the latency spike window.
3. Find monitor enters or parks with notable durations.
4. Open waiting threads' stack traces.
5. Identify the critical section and lock-holding code path if captured by the recording.
6. Correlate with concurrent request counts and latency metrics.

Seeing many threads waiting on the same monitor evidences contention. Inspect code to see if the lock is held too long, scoped too broadly, or if a lock holder stalls on I/O.

## 11. Practice Example: Investigating Allocations and GC

Suppose heap occupancy and GC activity rise during peak hours.

1. Record JFR with `profile` under representative load.
2. In JMC, inspect the GC timeline and pause durations.
3. Open the allocations view/stacks to locate major allocation sources.
4. Look for methods creating many temporary objects or continuously growing collections.
5. Cross-check with a heap dump if you need to see which objects remain alive and what holds references.

JFR and heap dumps answer different questions:

| Tool | Question |
|---|---|
| JFR allocation events | Which stacks allocated objects, and during which time windows? |
| JFR GC events | When did GC run, and what were the pauses and GC phases? |
| Heap dump | At the moment of the dump, which objects are alive, how much heap do they occupy, and which reference paths retain them? |

When suspecting a memory leak, JFR locates when abnormal allocation or GC starts; a heap dump with dominator/reference-chain analysis is usually required to determine why objects remain reachable.

## 12. Storing, Sharing, and Protecting JFR Files

Recordings are diagnostic data about your application and runtime environment. Depending on enabled events, files can contain:

- Class, method, package names, and stack traces.
- Thread names, process names, and runtime info.
- File paths, hosts, or I/O endpoints.
- System properties and custom event payloads emitted by the application.
- Deployment or configuration details that may reveal internal architecture.

Therefore:

- Store recordings in directories with restricted access permissions.
- Do not upload files to public services or attach to external tickets without reviewing data.
- Apply retention periods and delete files per organizational policy.
- Share only necessary portions; you can export filtered events rather than sending the whole recording.
- Monitor disk space when continuous recordings are enabled.

When using `maxage` and `maxsize`, understand these limit the recording repository; they do not replace storage-tier backup, retention, and access-control policies.

## 13. Common Errors When Reading JFR

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Recording file missing | JVM has not dumped yet, invalid path, or process lacks write permission | Check `JFR.start` output, directory permissions, and recording status |
| File small or missing expected events | Events disabled, recording too short, or threshold too high | Check `jfr summary`, metadata, and JFC file |
| JMC cannot open file | Corrupt file, incomplete dump, or JMC too old | Verify file integrity, use JMC supporting Java 17, and test `jfr summary` |
| No CPU events | Execution sampling disabled or no workload during window | Check event settings and re-record during reproduction |
| No short I/O events | I/O event threshold exceeds operation duration | Tune thresholds intentionally in JFC |
| Recording too large | Too many events, deep stacks, or long duration | Use `default`, cap duration/size, and filter needed events |
| CPU spikes after enabling recording | Overly detailed settings or instrumentation-sensitive workload | Measure overhead, trim events/stack depth, use shorter recordings |
| Two recordings yield confusing differences | Differing workload, duration, JFC, JDK, or load levels | Standardize conditions before comparing |
| No root cause found despite recording | Incident occurred outside recording window or needed events disabled | Widen recording window or build targeted JFC |
| JMC shows warnings while app behaves normally | Rules flag signals, not definitive conclusions | Inspect underlying events, workload, and SLOs before changing code |

## 14. Limitations When Interpreting JFR Data

### 14.1. Events Are Not Always Captured Exhaustively

JFR uses settings to balance detail and overhead. Some events are sampled, some record only past a threshold, and others require explicit enabling. Missing events in a recording do not prove an activity did not occur.

### 14.2. Samples Are Not Exact Measurements

Execution samples and allocation samples are great for spotting trends and hot spots. However, they are not equivalent to counting every method invocation or every object allocation accurately. Use metrics/benchmarks or specialized instrumentation when exact counts are required.

### 14.3. JFR Does Not Replace Heap Dumps

JFR records allocation and GC activity over time. It does not supply the complete live object graph at a point in time like a heap dump. When you need to know which object retains a large structure, capture a heap dump and use an appropriate heap analyzer.

### 14.4. JFR Does Not Replace Thread Dumps

JFR provides a timeline and event history across a recording window. A thread dump is a point-in-time snapshot, often helpful for seeing where every thread stands at once. When investigating deadlocks or instantaneous stalls, you may need thread dumps alongside JFR.

### 14.5. Recordings Do Not Automatically Prove Causality

Two events occurring close together do not mean the first caused the second. Use stack traces, thread identities, timestamps, logs, metrics, and controlled experiments to validate hypotheses.

## 15. Principles for Using JFR and JMC in Java 17

- Start with `default` for general observation or long-term recordings.
- Use `profile` for short investigation windows when more detailed events are needed.
- Record JDK version, JFC settings, timestamps, and workload for every recording.
- Run `jfr summary` before inspecting events to verify the file and available events.
- Use `jfr print` for quick checks or extracting event subsets; use JMC for timelines and stack trees.
- Distinguish sampled events from threshold-recorded events.
- Correlate JFR with application logs, metrics, and thread/heap dumps.
- Never draw conclusions from automated analysis without inspecting underlying events.
- Cap recording disk size and retention duration.
- Protect JFR files as internal diagnostic data that may contain sensitive information.

## 16. Practice Exercises

### Exercise 1 — Recording for 60 Seconds

Launch a Java 17 application with:

```bash
java -XX:StartFlightRecording:filename=app.jfr,settings=profile,duration=60s \
     -jar app.jar
```

After the application finishes recording, run `jfr summary app.jfr` to verify duration and event list. Note which events appear.

### Exercise 2 — Attaching to a Running JVM

1. Use `jcmd -l` to find the PID.
2. Start a recording with `JFR.start` using an identifiable name.
3. Check with `JFR.check`.
4. Dump the recording with `JFR.dump`.
5. Stop the recording with `JFR.stop`.
6. Open the file in JMC.

Explain the difference between dump and stop.

### Exercise 3 — Reading Execution Samples

Run a CPU-heavy workload. Record with `profile`, then run:

```bash
jfr print --events jdk.ExecutionSample --stack-depth 64 app.jfr
```

Find a frequently appearing stack trace. Explain why sample count is not an exact method invocation count.

### Exercise 4 — Finding Lock Contention

Create a workload where multiple threads contend on the same monitor. Record JFR, open JMC, and locate `jdk.JavaMonitorEnter` or thread-waiting events. Identify the waiting thread's stack trace and the relevant critical section.

### Exercise 5 — Comparing default and profile

Run the same workload twice, once with `settings=default` and once with `settings=profile`. Compare:

- Event counts.
- File sizes.
- Events carrying stack traces.
- Ability to pinpoint CPU or allocation hot methods.

Document the trade-off between data detail and overhead.

### Exercise 6 — Analyzing a Recording with Abnormal GC

Open a recording containing multiple GC pauses. Inspect the GC timeline, heap occupancy, allocations, and allocation sample stack traces. State one hypothesis for the cause and what additional data is needed to verify it.

## 17. Official Documentation

- [Java 17 jfr command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): CLI syntax for summaries, metadata, printing events, and configuring recordings.
- [Java 17 jcmd command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): JVM process diagnostics and JFR commands.
- [Java 17 java command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): startup recording option `-XX:StartFlightRecording`.
- [Java SE 17 API — jdk.jfr](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html): Java Flight Recorder API and event model.
- [JDK Mission Control — Oracle](https://www.oracle.com/java/technologies/jdk-mission-control.html): information about JDK Mission Control.
- [OpenJDK JDK Mission Control](https://github.com/openjdk/jmc): JMC project source code and documentation.
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): making Flight Recorder an open technology in OpenJDK.

**Key Takeaway:** JFR records JVM and application events over a time window; `jfr` inspects summaries, metadata, and extracted events; JDK Mission Control visualizes timelines, stack traces, CPU, GC, allocations, locks, and I/O. Choose appropriate recording settings, understand sampling/threshold limits, correlate with logs and metrics, and protect recording files as internal diagnostic data.
