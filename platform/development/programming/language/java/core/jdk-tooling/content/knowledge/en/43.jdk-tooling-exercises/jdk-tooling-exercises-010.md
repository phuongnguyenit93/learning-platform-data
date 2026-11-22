# Profiling Java with Java Flight Recorder (JFR)

## Objectives

After this lesson, you will be able to explain JFR and the role of JDK Mission Control (JMC); understand events, recordings, templates, and buffers; start and stop a recording at application startup or on a running JVM; create a continuous recording with size/age limits; read `.jfr` files using command-line tools and JMC; analyze CPU, allocation, garbage collection, threads, locks, and I/O; create custom JFR events in Java; tune event settings; build a repeatable profiling workflow; and troubleshoot common issues when collecting or analyzing data.

## 1. What is JFR?

**Java Flight Recorder (JFR)** is an event collection and diagnostics/profiling system built into the JVM of modern JDKs. JFR records timestamped events about the application, JVM, and runtime environment so developers can analyze behavior that has occurred.

A recording can provide information about:

- CPU activity and stack traces of running threads.
- Object allocation and memory allocation rate.
- Garbage collection, heap behavior, and GC pauses.
- Thread state, monitor contention, lock waits, and thread parks.
- File I/O, socket I/O, and wait durations.
- Class loading, JIT compilation, and internal JVM activity.
- Custom events defined by the application to mark business operations.

JFR is well suited for investigating performance issues that appear during a specific time window, even when the issue only occurs in staging or production environments and is hard to reproduce on a developer's machine.

### JFR is not a timer for every line of code

JFR collects many types of events. Some events measure duration; some record instantaneous occurrences; some sample periodically. CPU profiling is typically based on thread sampling, so sample proportions help identify CPU-intensive code regions rather than exact method invocation counts.

Use a recording to form a hypothesis, then cross-check it against code, metrics, logs, and repeatable measurements. A single chart or stack trace alone is not enough to conclude the root cause.

## 2. Distinguishing JFR, JMC, jcmd, and jfr

These four components are often used together, but each handles a different responsibility.

| Component | Role |
|---|---|
| JFR | Collects and stores events from the JVM into a recording file |
| JDK Mission Control (JMC) | Opens, visualizes, and analyzes recording files; can also control the JVM |
| jcmd | Sends diagnostic commands to a running JVM, such as start, check, dump, and stop recording |
| jfr | Command-line tool for reading summaries, printing events, viewing metadata, filtering, and configuring recordings |

JFR is built into the JDK/JVM. JMC is a separate analysis application and is not included in a standard JDK installation; you need to install a version of JMC compatible with the recording/JDK in use.

JFR and JMC form a workflow:

~~~text
Java application
       |
       v
JVM + JFR records events
       |
       v
Flight recording (.jfr)
       |
       +------> jfr CLI
       |
       +------> JDK Mission Control
                    |
                    v
            Charts / tables / stack traces
                    |
                    v
             Performance investigation
~~~

jcmd is one way to control a recording while the application is running. You do not need to modify source code or restart the JVM just to start a runtime recording if the JVM allows diagnostic commands.

## 3. Events are the data unit of JFR

An event typically has:

- **Timestamp:** when the event occurred.
- **Duration:** how long the event lasted, if it is a duration event.
- **Thread/context:** the associated thread or context.
- **Payload:** data fields describing the event.
- **Stack trace:** the related code location if the event is configured to capture stack traces.

Main event categories:

| Category | How it works | Examples |
|---|---|---|
| Duration event | Has a start time and end time | Lock wait, file/socket I/O |
| Instant event | Records a single point in time | An operation or JVM state |
| Sample event | Collected periodically | CPU/thread sample |
| Custom event | Defined by an application or tool | OrderProcessed, PaymentAttempt |

JFR includes many built-in events for the JVM and runtime. An application can add custom events to record the processing time of a request, payment operation, or other important workflow step.

### Event settings

Each event can be configured with attributes such as:

- enabled: turns the event on/off.
- threshold: records a duration event only when its duration exceeds the threshold.
- period: collection interval for periodic events.
- stackTrace: whether to record a stack trace.
- throttle: limits event rate in certain cases.

For example, if you only care about lock waits longer than 10 ms, you can use a threshold to ignore very short waits. Lowering the threshold captures more detail, but can also make the recording larger and increase overhead.

## 4. Recording templates: default and profile

The JDK provides two common JFR configurations in the JAVA_HOME/lib/jfr directory:

| Template | Purpose | Data level |
|---|---|---|
| default.jfc | Continuous monitoring and general diagnostics | Fewer events, low overhead |
| profile.jfc | Short-term profiling to find bottlenecks | More events, higher overhead |

Choose `default` when you need continuous recording and want to retain a recent window of data. Choose `profile` when you need more detail about methods, allocations, and application activity over a short period.

You should not use `profile` by default for long-running continuous recordings. More events usually mean more data, larger files, and greater impact on the workload.

### Time-fixed recording

A time-fixed recording runs for a specified duration and then stops automatically. It is a good choice when:

- You want to reproduce a specific workload.
- You are running a load test or benchmark.
- You need to analyze a single latency spike.
- You want to capture a short profile during peak hours.

### Continuous recording

A continuous recording runs long-term and retains a recent window of data. When the size limit or age limit is reached, older data is discarded to keep newer data.

This is useful when errors occur unexpectedly and you cannot know in advance when to start profiling. When an incident happens, dump the relevant portion of the recording and analyze it afterward.

## 5. Checking the JDK and tools before profiling

Verify the runtime:

~~~bash
java -version
javac -version
jcmd -l
jfr --version
~~~

The `jcmd` and `jfr` commands are usually located in the JDK `bin` directory. Use tools from a JDK compatible with the target JVM to avoid version mismatches or missing diagnostic commands.

View JFR help:

~~~bash
jcmd <PID> help JFR.start
jcmd <PID> help JFR.dump
jcmd <PID> help JFR.stop
jfr --help
jfr --help print
~~~

Replace `PID` with the actual process ID. Do not include angle brackets in the command.

`jcmd` must run on the same machine as the JVM and normally must use the same effective user/group that launched the JVM. For processes in containers, the PID may differ from the PID on the host; identify the PID in the correct process namespace/container before invoking `jcmd`.

JMC can be downloaded separately from the JDK Mission Control page. Open the `.jfr` file with JMC after the recording has been created.

## 6. Starting a recording at application startup

You can use the `-XX:StartFlightRecording` JVM option to begin collecting data as soon as the application starts.

Example of a 90-second recording with the `profile` template:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,duration=90s,filename=build/profile.jfr \
  -jar app.jar
~~~

Parameters:

- settings=profile: uses the `profile` template.
- duration=90s: automatically stops after 90 seconds.
- filename=build/profile.jfr: saves the recording to the specified file.
- -jar app.jar: launches the application.

You can write the recording when the JVM exits using `dumponexit=true`:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,dumponexit=true,filename=build/exit.jfr \
  -jar app.jar
~~~

If `duration` is not specified, the recording continues running until stopped or until the JVM exits. `dumponexit=true` instructs the JVM to write the recording to a file on shutdown.

### Choosing when to start

You can delay the start time:

~~~bash
java \
  -XX:StartFlightRecording:settings=profile,delay=30s,duration=60s,filename=build/delayed.jfr \
  -jar app.jar
~~~

This example waits 30 seconds after JVM startup and then records for 60 seconds. This is useful if you want to skip startup/warmup and focus on the steady-state workload phase.

### Limiting recording size

For recordings written to disk, you can limit data age and size:

~~~bash
java \
  -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=512M,dumponexit=true,filename=build/continuous.jfr \
  -jar app.jar
~~~

`maxage` and `maxsize` help control the data stored on disk. Choose limits appropriate for your event generation rate, disk capacity, and required retention window.

## 7. Starting a recording on a running JVM with jcmd

This is the common approach when you need to profile an already deployed application without restarting it.

List JVM processes:

~~~bash
jcmd -l
~~~

Illustrative example output:

~~~text
8124 com.example.CheckoutApplication
9130 org.example.Worker
~~~

Suppose the PID of the application to inspect is `8124`.

Start a recording:

~~~bash
jcmd 8124 JFR.start name=checkout-profile settings=profile duration=120s filename=/tmp/checkout-profile.jfr
~~~

Check the running recording:

~~~bash
jcmd 8124 JFR.check name=checkout-profile
~~~

JFR will stop automatically after 120 seconds and write the file to the specified `filename`.

### Recording without a fixed duration

You can start a recording and decide when to stop it later:

~~~bash
jcmd 8124 JFR.start name=incident settings=profile
~~~

Check:

~~~bash
jcmd 8124 JFR.check name=incident verbose=true
~~~

Dump current data while the recording keeps running:

~~~bash
jcmd 8124 JFR.dump name=incident filename=/tmp/incident-snapshot.jfr
~~~

`JFR.dump` creates a snapshot file; the original recording continues running.

Once enough data has been collected, stop and save the remainder:

~~~bash
jcmd 8124 JFR.stop name=incident filename=/tmp/incident-final.jfr
~~~

If you use `JFR.stop` without specifying `filename`, the data may be discarded instead of saved to a file. Always specify `filename` when you want to keep the recording.

### Dumping a recent time window

`JFR.dump` supports limiting by data age or time range. For example:

~~~bash
jcmd 8124 JFR.dump name=incident maxage=15m filename=/tmp/incident-last-15m.jfr
~~~

This command saves recent data within the 15-minute limit. Verify that the recording contains data for that time window.

## 8. Maintaining a continuous recording for production applications

A continuous recording can be started with the application using a low-overhead configuration:

~~~bash
java \
  -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=512M,dumponexit=true,filename=/var/log/myapp/shutdown.jfr \
  -jar app.jar
~~~

In this example:

- settings=default selects a low-overhead configuration.
- disk=true enables writing data to the disk repository.
- maxage=6h retains data for up to six hours.
- maxsize=512M limits data size.
- dumponexit=true writes the recording on JVM shutdown.
- filename specifies the output file when dumping on shutdown.

When an incident occurs, you can use `jcmd` to dump the data needed for investigation while the JVM remains running.

### Why limit recordings?

Without proper limits, recording data can grow continuously and consume disk space. You need to manage:

- Repository size and dump file size.
- Data retention duration.
- Read permissions on recording files.
- Storage location and deletion schedule.
- Process for transferring files to an analysis environment.
- Available free space on the container/host.

Continuous recording helps preserve context leading up to an incident. However, it does not replace metrics and alerting; use metrics to detect anomalies, then use JFR to find the cause.

## 9. Capturing recordings with the JDK Mission Control UI

JMC can connect to a JVM and control recordings.

Basic workflow:

1. Open JDK Mission Control.
2. In the JVM Browser, select the target JVM.
3. Right-click and choose Start Flight Recording.
4. Choose where to save the file.
5. Choose Time Fixed or Continuous recording.
6. Choose the Continuous or Profiling template.
7. Adjust event settings/thresholds if needed.
8. Start the recording.
9. Dump or stop the recording when enough data has been collected.

For continuous recordings, JMC lets you choose age or size limits for retained data. You can also dump the entire recording, a recent portion, or a specific time range.

JMC can also configure triggers to start a recording automatically when a condition is met, depending on JMX configuration and JVM management permissions.

## 10. Reading recording files with the jfr tool

A `.jfr` file is a binary file. The `jfr` tool included with the JDK supports reading and converting the data into human-readable formats.

### Viewing a summary

~~~bash
jfr summary build/profile.jfr
~~~

The summary helps check:

- Start and end times.
- Total number of events.
- Which event types appear most frequently.
- Recording size.
- Event settings and general information.

If the file does not contain the expected events, review the template, recording duration, and event thresholds.

### Printing all events

~~~bash
jfr print build/profile.jfr
~~~

You can produce JSON output:

~~~bash
jfr print --json build/profile.jfr
~~~

Or XML:

~~~bash
jfr print --xml build/profile.jfr
~~~

### Filtering by event

~~~bash
jfr print --events jdk.ExecutionSample build/profile.jfr
~~~

Filtering by category:

~~~bash
jfr print --categories "Java Application" build/profile.jfr
~~~

Event/category names must match the metadata in the recording and the JDK version. You can use `jfr metadata` to inspect event names and field layouts.

### Viewing aggregated views

~~~bash
jfr view all-views build/profile.jfr
jfr view all-events build/profile.jfr
~~~

Then select a specific view listed by the tool:

~~~bash
jfr view <view-name> build/profile.jfr
~~~

### Inspecting metadata

~~~bash
jfr metadata build/profile.jfr
~~~

Metadata shows event types, categories, fields, and other details needed to understand the data in the recording.

## 11. Analyzing recordings with JMC

Open the `.jfr` file in JMC. A recording usually opens on the Automated Analysis Results page with groups of findings for Java Application, JVM Internals, and Environment.

Start from the time when the application was slow or failing, then drill down into the corresponding events and stack traces.

### CPU and method profiling

The goal is to find CPU-consuming code paths.

In JMC:

1. Open the Code/Method Profiling or Threads view.
2. Select the exact time range when the issue occurred.
3. Look at threads with high CPU sample counts.
4. Expand stack traces and find prominent packages/methods.
5. Inspect the corresponding code and dependencies.
6. Compare against a baseline recording under normal workload.

CPU execution samples show where threads were executing at sampling instants. A method appearing frequently in samples is worth investigating, but sample count is not an exact method invocation count.

Distinguish between:
- CPU-bound: threads continuously running and consuming CPU.
- Waiting: threads waiting on I/O, locks, conditions, or the scheduler.
- Blocked: threads waiting to acquire a monitor lock.
- Parked: threads paused waiting on a condition or synchronization.

An application with high latency is not necessarily consuming high CPU. Check thread states to determine whether it is running or waiting.

### Allocation and memory

If the application is creating too many objects:

1. Open the Memory/Allocation view.
2. Inspect the allocation rate over time.
3. Find classes or stack traces allocating many objects.
4. Check whether objects are allocated repeatedly in hot paths.
5. Evaluate temporary objects, collection growth, boxing, string conversion, and buffer allocation.
6. Compare the allocation rate before and after a fix.

High allocation can increase GC frequency and CPU time. However, high allocation does not automatically mean a memory leak.

A memory leak usually involves objects that are no longer needed but still retain references. Inspect the live set/retained objects and reference paths with an appropriate tool; JFR can help identify the timing and allocation sites.

### Garbage collection

In the GC view, check:

- Number of GCs.
- Pause times.
- Duration and interval between GCs.
- Allocation rate before GC.
- Heap usage before and after GC.
- Concurrent GC activity if the collector uses it.
- GC timestamps that coincide with latency spikes.

Heap growing and then dropping after GC can be normal temporary allocation. If the live set after each GC steadily increases across multiple cycles, investigate object retention.

Do not conclude GC is the root cause just because you see a pause. Correlate pauses with request latency and workload.

### Lock contention and synchronization

In the Threads/Locks view, look for:

- Threads blocked for long durations.
- Lock instances with many waiters.
- Stack traces of the thread holding the lock.
- Monitor enter/wait durations.
- Lock contention coinciding with latency spikes.

A lock with many waiters can serialize work. Check whether the critical section is performing I/O, calling an external service, or running long computations while holding the lock.

If you lower the threshold to capture shorter lock waits, the recording may generate many more events. Choose a threshold aligned with your target latency.

### File and socket I/O

In the I/O view, inspect:

- Read/write durations.
- Socket waits.
- Long-running file operations.
- Which threads are affected.
- Stack traces calling I/O.
- Whether slow I/O coincides with downstream latency.

Slow I/O can stem from network, storage, remote services, or queueing. JFR helps locate the call site and duration; cross-check with network metrics, server logs, and tracing to identify the system causing the slowdown.

## 12. Reading recordings by investigation question

Do not inspect every event in random order. Start with a specific question.

| Symptom | View/event to inspect | What to verify |
|---|---|---|
| High CPU | Execution samples, Threads, Code | Hot stacks and running threads |
| Increased request latency | Thread, I/O, Locks | Execution time and wait time |
| Long GC pauses | Garbage Collection, Memory | Pauses, heap, and allocation |
| Steadily growing memory | Allocation, GC, Heap/Old Object | Allocation sites and object retention |
| Stalled threads | Threads, Monitor/Locks | Blocked, parked, and lock owner |
| Slow disk/network | File I/O, Socket I/O | Call sites and durations |
| Slow startup | Class loading, JIT, startup events | Class initialization, compilation, and dependencies |

A useful workflow:

1. Mark the symptom timestamp using metrics/logs.
2. Open the recording and select the matching time range.
3. Identify threads or events correlated with the symptom.
4. Inspect the stack trace.
5. Verify against code and dependencies.
6. Form a testable hypothesis.
7. Change one factor.
8. Capture a new recording under an equivalent workload.
9. Compare before/after.

## 13. Tuning event settings and thresholds

`.jfc` files define which events are recorded and how they are collected.

Do not edit the default template files inside the JDK directly. Create a separate configuration file so it can be reviewed, version-controlled, and reused.

Example of creating a new configuration from the `profile` template:

~~~bash
jfr configure \
  --input "$JAVA_HOME/lib/jfr/profile.jfc" \
  --output build/jfr-custom.jfc \
  jdk.JavaMonitorEnter#threshold=5ms
~~~

This command creates a new configuration with a 5 ms monitor enter threshold. Check syntax and event names with `jfr help configure` and the target JDK's metadata if events differ across versions.

Using the configuration:

~~~bash
java \
  -XX:StartFlightRecording:settings=build/jfr-custom.jfc,duration=120s,filename=build/custom-profile.jfr \
  -jar app.jar
~~~

Some principles:

- Enable events needed for your investigation question.
- Set thresholds low enough to catch bottlenecks without collecting excessive events.
- Enable stack traces only when you need to identify call sites.
- Avoid enabling many detailed events long-term without evaluating overhead.
- Store configurations alongside profiling documentation for reuse.

### Stack depth

JFR stores stack traces with a limited depth. Increasing stack depth can help reveal more call layers, but it can also make the recording consume more resources.

Increase it when the current stack lacks sufficient context, and test the impact on a realistic workload. Do not set it to the maximum value just to get more data.

## 14. Creating custom events in Java

JFR allows applications to record business data by extending `jdk.jfr.Event`.

Custom events are useful when system events do not show which business operation is running. For example, we want to measure the processing time of an order and record the order ID, item count, and status.

### Java 17+ example

Create `src/JfrDemo.java`:

~~~java
import java.nio.file.Path;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.StackTrace;

public class JfrDemo {

    @Name("com.example.OrderProcessed")
    @Label("Order Processed")
    @Category({"Application", "Orders"})
    @Description("Measures the processing time of one order")
    @StackTrace(false)
    static class OrderProcessed extends Event {
        @Label("Order ID")
        String orderId;

        @Label("Item Count")
        int itemCount;

        @Label("Status")
        String status;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("orders.jfr");
        Configuration config = Configuration.getConfiguration("default");

        try (Recording recording = new Recording(config)) {
            recording.setName("orders-demo");
            recording.setToDisk(true);
            recording.enable(OrderProcessed.class);
            recording.start();

            for (int i = 1; i <= 3; i++) {
                OrderProcessed event = new OrderProcessed();
                event.orderId = "ORD-" + i;
                event.itemCount = i * 2;
                event.status = "OK";

                event.begin();
                processOrder();
                event.end();

                if (event.shouldCommit()) {
                    event.commit();
                }
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("Recording saved: orders.jfr");
    }

    private static void processOrder() throws InterruptedException {
        Thread.sleep(20);
    }
}
~~~

Compile with JDK 17+:

~~~bash
mkdir -p out
javac --release 17 -d out src/JfrDemo.java
java -cp out JfrDemo
~~~

Stdout:

~~~text
Recording saved: orders.jfr
~~~

The `orders.jfr` file is created in the working directory.

### Code explanation

- OrderProcessed extends Event: defines the event type.
- @Name: provides a stable event name for configuration and filtering.
- @Label, @Category, @Description: provide readable metadata in JMC.
- @StackTrace(false): disables stack trace capture for this custom event.
- begin() and end(): measure the duration of one execution.
- shouldCommit(): checks whether the event should be recorded according to event settings/threshold.
- commit(): submits the event to JFR.
- Recording: creates a recording using the `default` configuration, enables the custom event, starts, stops, and dumps to a file.

JFR supports Java primitives and certain reference types such as `String`, `Thread`, and `Class` for event fields. Arrays, enums, and other reference types do not automatically become supported event fields. Use types supported by the API and verify the event metadata.

### Why use shouldCommit?

Constructing the payload can be expensive. If the event is disabled or its duration is below the threshold, `shouldCommit()` may return `false`.

For expensive payloads, compute extra data only when the event is likely to be recorded:

~~~java
OrderProcessed event = new OrderProcessed();

event.begin();
processOrder();
event.end();

if (event.shouldCommit()) {
    event.orderId = buildExpensiveDiagnosticId();
    event.itemCount = countItems();
    event.status = "OK";
    event.commit();
}
~~~

This example only illustrates deferring payload computation. In real code, assign the necessary fields at appropriate times so the data accurately reflects the measured operation.

### Choosing where to place custom events

Place events at meaningful business boundaries, such as:

- A request being processed.
- A call to a payment provider.
- A batch import completing.
- A message being processed.
- A step in a workflow.

Do not create events for every small loop or simple getter. Overly dense events can bloat the recording and increase overhead.

Never record passwords, access tokens, session IDs, personal information, request bodies, or sensitive data in event fields. Choose pseudonymized identifiers or correlation IDs that contain no secrets.

## 15. Controlling JFR with the Recording API

In addition to `jcmd`, an application can control recordings using the API in the `jdk.jfr` module.

A recording is created from a `Configuration` or settings map, then configured before calling `start`.

Condensed example:

~~~java
Configuration config = Configuration.getConfiguration("default");

try (Recording recording = new Recording(config)) {
    recording.setName("application-diagnostic");
    recording.setMaxAge(Duration.ofHours(1));
    recording.setMaxSize(256L * 1024 * 1024);
    recording.setToDisk(true);
    recording.start();

    runWorkload();

    recording.stop();
    recording.dump(Path.of("application.jfr"));
}
~~~

This snippet requires the following imports:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Configuration;
import jdk.jfr.Recording;
~~~

Meaning:

- setMaxAge: limits the age of retained data.
- setMaxSize: limits the size of retained data.
- setToDisk(true): enables writing data to the disk repository.
- start(): starts the recording.
- stop(): stops the recording.
- dump(Path): exports data to a `.jfr` file.
- close(): releases the recording's data/resources.

Without `maxAge` or `maxSize`, a disk-backed recording can grow without bound. Always set limits for long-running recordings.

In this example, `runWorkload()` is an application method, not a JFR API. Replace it with the actual operation you want to observe.

## 16. Evaluating overhead and recording quality

JFR is designed to collect data with low overhead, but overhead is not zero and depends on the application, event settings, template, event frequency, and recording duration.

Some principles:

- Start with `default` for continuous recordings.
- Use `profile` for short windows when more detail is needed.
- Measure recording impact using a representative benchmark/load test.
- Do not enable detailed events without a specific question.
- Limit `maxage` and `maxsize`.
- Increase stack depth only when needed.
- Monitor file size and event generation rate.

### Caution with Heap Statistics

Heap Statistics can trigger a full/old garbage collection at the start and end of collection to gather heap information. This can cause pauses and skew latency measurements.

Enable it only when investigating a memory leak or when you need live-set analysis. When measuring latency or GC pauses, consider excluding this event from the recording.

### Caution with Path to GC Roots

Collecting paths to GC roots can be time-consuming and cause pauses. Enable it only when you have a specific memory leak hypothesis. Do not enable it for all continuous recordings.

## 17. Building a repeatable profiling workflow

A good profiling session requires a clear goal and well-defined measurement conditions.

### Before recording

1. Record the symptom: high CPU, increased latency, GC pauses, memory growth, or slow I/O.
2. Record the timestamp or time window when it occurs.
3. Record the JDK version, JVM flags, and runtime environment.
4. Confirm the workload and traffic are sufficiently representative.
5. Choose the template and duration.
6. Determine where the recording will be saved and access permissions.
7. Check disk space and file limits.

### During recording

1. Do not change multiple configuration variables at the same time.
2. Record the start/end timestamps.
3. Record related request, batch, or incident IDs.
4. Watch external metrics to identify the window to analyze.
5. Dump the recording close to the symptom timestamp.

### After recording

1. Run `jfr summary`.
2. Open the file in JMC.
3. Select the exact time range.
4. Find events/threads correlated with the symptom.
5. Read stack traces and event payloads.
6. Form a testable hypothesis.
7. Change one factor.
8. Repeat the recording under an equivalent workload.
9. Compare CPU, allocation, pauses, lock waits, or I/O durations.

### Recording results

A profiling report should capture:

| Field | Content |
|---|---|
| Application | Service name/build/version |
| JDK | Vendor, version, and runtime |
| Environment | OS, CPU, memory, container limits |
| Workload | Request rate, scenario, test duration |
| Recording | Template, start/end, file size |
| Symptom | CPU, latency, memory, GC, lock, or I/O |
| Finding | Event, thread, stack trace, and time range |
| Hypothesis | Suspected root cause |
| Change | Code/config adjusted |
| Before/after | Comparison metrics and recordings |
| Limitation | Missing events, sampling interval, or insufficient data |

## 18. JFR in production and data security

JFR can be used to investigate production applications because it is built into the JVM and supports continuous recording with low overhead. Even so, you must measure overhead under real workloads and apply data management policies.

A recording can contain:

- Thread names and stack traces.
- Class/package and method names.
- JVM arguments or system properties.
- File paths, hostnames, and environment information.
- Custom event payloads written by the application.
- Metadata that helps infer internal service behavior or structure.

Do not share `.jfr` files outside your organization by default. Control read permissions, retention periods, and transfer channels.

### Scrubbing data before sharing

You can use `jfr scrub` to remove unnecessary events, categories, or threads:

~~~bash
jfr scrub \
  --exclude-threads "HealthCheck*" \
  --exclude-events "jdk.SomeSensitiveEvent" \
  input.jfr sanitized.jfr
~~~

The event/thread names in this example are illustrative; choose filters based on the actual metadata of the recording.

Scrubbing by event/thread does not replace manual review. Inspect custom event payloads, command-line values, and sensitive information before sharing a recording.

### Restricting JVM control permissions

`jcmd` allows sending diagnostic commands to the JVM. Grant permissions only to trusted operators and secure the host/container where the JVM runs. Do not expose diagnostic access or JMX management broadly on public networks.

## 19. How does JFR differ from heap dumps, thread dumps, and metrics?

| Tool | Data | Best-suited question |
|---|---|---|
| JFR | Time-series events, samples, durations, stacks | What happened during the slow period? |
| Heap dump | Object graph at a single point in time | Which objects are being retained in the heap? |
| Thread dump | Thread states and stacks at a single point in time | Are threads running, blocked, or deadlocked? |
| Metrics | Aggregated numbers over time | When is the system abnormal and how severe is it? |
| Logs | Business events/application messages | Which request or operation failed? |
| Distributed tracing | Spans across multiple services | Which service/downstream caused the latency? |

JFR does not replace these tools. It supplements them with detailed runtime data to correlate symptoms with threads, allocations, GC, locks, and I/O.

Example:
- Metrics detect a p99 latency increase.
- Distributed tracing points to a slow payment service.
- JFR shows the service's threads waiting on socket I/O.
- Logs/correlation IDs help pinpoint the specific downstream request.

Combining these sources helps avoid blaming the JVM when the issue lies in the network or another service.

## 20. Common errors and how to handle them

### jcmd -l does not show the JVM

**Cause:** wrong user, process is in a different container namespace, JVM is running on another host, or PID is not listed.

**Resolution:** run on the correct host/container; use the same effective user/group; identify the PID in the correct namespace; check `jcmd PID help`.

### jcmd reports attach failure

**Cause:** different user permissions, attach listener disabled, container policy, or the JVM does not support diagnostic attach in the way being used.

**Resolution:** check process permissions, runtime, and attach settings; inspect JVM logs; if attach is not possible, configure the recording at startup with `-XX:StartFlightRecording`.

### .jfr file not found

**Cause:** recording not stopped/dumped yet, wrong working directory, unwritable path, or JVM exited before dumping.

**Resolution:** verify `filename` in `JFR.start`; use `JFR.check`; specify an absolute writable path; use `dumponexit=true` if dumping on shutdown is needed.

### Recording file is empty or missing events

**Cause:** template does not enable the desired events, recording is too short, event threshold is too high, or the workload has not generated the events.

**Resolution:** run `jfr summary` and `jfr metadata`; check the template; adjust event settings; re-record during a workload exhibiting the symptom.

### CPU profile does not point to a clear method

**Cause:** recording is too short, too few samples, threads were inactive in the time range, or the bottleneck is waiting/I/O rather than CPU.

**Resolution:** record longer during a steady workload; check Threads and I/O; verify the time range; cross-check with metrics.

### JFR file is too large

**Cause:** using the `profile` template for too long, enabling too many events, low thresholds, or overly frequent custom events.

**Resolution:** use `default` for continuous recordings; limit `duration`/`maxage`/`maxsize`; reduce events/stack traces; add appropriate throttling or thresholds.

### JMC cannot open the recording

**Cause:** incomplete file, truncated file, JMC version too old, or file copied while still being written.

**Resolution:** dump the recording properly using `JFR.dump` or `JFR.stop`; check the file with `jfr summary`; update JMC to a compatible version; copy the file after the dump completes.

### Custom event not visible

**Cause:** event not enabled, class not yet loaded, unsupported field type, recording not running, or event filtered out by threshold.

**Resolution:** call `recording.enable(EventClass.class)`; check `event.isEnabled()`/`shouldCommit()`; inspect metadata with `jfr metadata`; verify the recording contains the event name.

### Profiling results differ from benchmark

**Cause:** different workload, warmup, JDK, CPU, memory limits, or event settings.

**Resolution:** standardize workload and environment; document JDK/JVM flags; capture baseline and recording over the same duration; do not directly compare two recordings taken under different conditions.

### Latency increases when Heap Statistics is enabled

**Cause:** Heap Statistics can trigger an old/full GC to collect heap data.

**Resolution:** disable this event when measuring latency; enable it only during controlled memory leak/live-set investigations.

### JFR.stop ran but no file was produced

**Cause:** `filename` was not passed, so recording data may have been discarded.

**Resolution:** stop with `filename=/path/to/output.jfr`; verify the file exists and run `jfr summary`.

### Recording contains sensitive data

**Cause:** custom events or metadata contain identifiers, paths, system properties, or request information.

**Resolution:** restrict access permissions; scrub unnecessary events/threads; inspect payloads; delete files according to retention policy; do not send unreviewed files externally.

## 21. Hands-on exercises

### Exercise 1 — Capture a recording from an application

1. Run a sample Java application or service.
2. Use `jcmd -l` to find its PID.
3. Start a 60-second recording using `settings=profile`.
4. Send a steady workload during the recording window.
5. Verify the `.jfr` file was created.
6. Run `jfr summary` and open the file in JMC.

Results to record: JDK version, template, duration, file size, and event count.

### Exercise 2 — Find a bottleneck

1. Choose a workload with high CPU or high latency.
2. Open the Threads/Code/Memory/I/O views.
3. Find the problematic time range.
4. Identify prominent threads, events, and stack traces.
5. Write a hypothesis about the cause.
6. Propose a testable change.

Do not just write "method A is slow"; state whether it is using CPU, waiting on a lock, or waiting on I/O, along with evidence from the recording.

### Exercise 3 — Record a custom business event

1. Compile and run `JfrDemo`.
2. Open `orders.jfr` in JMC.
3. Find the `com.example.OrderProcessed` event.
4. Inspect duration, order ID, item count, and status.
5. Replace `Thread.sleep` with another processing operation.
6. Capture the recording again and compare durations.

### Exercise 4 — Compare default and profile

1. Capture a recording using `default`.
2. Run the same workload and capture a recording using `profile`.
3. Compare event count, file size, and method/allocation data.
4. Note the observed overhead.
5. Recommend the appropriate template for continuous monitoring vs. short-term profiling.

## 22. Checklist before concluding profiling

### Collection

- [ ] Correct JVM/PID and user identified.
- [ ] Compatible JDK/JFR version.
- [ ] Template matches the goal.
- [ ] Recording covers the exact time the symptom occurred.
- [ ] Workload is sufficiently representative.
- [ ] Size/time limits are configured.
- [ ] `.jfr` file is completely dumped.

### Analysis

- [ ] Checked summary and event metadata.
- [ ] Selected the exact time range.
- [ ] Distinguished CPU, waiting, blocked, and I/O.
- [ ] Read stack traces/event payloads.
- [ ] Cross-checked metrics, logs, or traces.
- [ ] Documented a testable hypothesis.
- [ ] Did not treat sample count as an exact method call count.

### Operations and security

- [ ] Measured overhead on an appropriate workload.
- [ ] Did not enable expensive events unnecessarily.
- [ ] Recording has retention and access controls.
- [ ] No unintended sensitive data present.
- [ ] Reviewed/scrubbed the file before sharing.
- [ ] Saved environment and configuration details for reproducibility.

## 23. Official references

- [JDK Mission Control User Guide — Flight Recorder](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html) — event types, templates, time-fixed/continuous recordings, and how to capture and analyze recordings.
- [JDK Mission Control User Guide](https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/jdk-mission-control.html) — JMC, JVM Browser, JMX Console, and Flight Recorder.
- [The jcmd Command — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html) — JFR.start, JFR.check, JFR.dump, JFR.stop, and diagnostic commands.
- [The java Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html) — StartFlightRecording, event settings, max age/size, and repository options.
- [jfr — Parse and Print Flight Recorder Files](https://dev.java/learn/jvm/monitoring-troubleshooting/monitoring/jfr/) — jfr summary, print, view, metadata, configure, scrub, and file handling.
- [Configuring the JDK Flight Recorder — Dev.java](https://dev.java/learn/jvm/monitoring-troubleshooting/jfr/configure/) — .jfc, default.jfc, profile.jfc, and event settings.
- [Event — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html) — defining custom events, field types, begin, end, commit, and shouldCommit.
- [Recording — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html) — controlling recordings with the Java API, size limits, and dump.
- [jdk.jfr Package — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — event metadata, event settings, and the Flight Recorder API.
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 11](https://docs.oracle.com/en/java/javase/11/troubleshoot/troubleshoot-performance-issues-using-jfr.html) — overhead, heap statistics, and notes on performance analysis.

JFR helps record the actual behavior of the JVM and application for post-incident investigation. Choose a recording template based on your goal, capture the right time range, analyze events and stack traces with JMC or `jfr`, and verify your hypothesis with an equivalent workload. A solid workflow collects enough data to locate bottlenecks while keeping overhead, storage size, and recording access under control.
