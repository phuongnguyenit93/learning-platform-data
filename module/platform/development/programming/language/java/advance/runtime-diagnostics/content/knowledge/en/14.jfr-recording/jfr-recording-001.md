# 14.1. What Events Does JFR Record? Relationship Between Event, Timestamp, Duration, and Stack Trace

## Learning Objectives

After this lesson, you will be able to:

1. Describe how **Java Flight Recorder (JFR)** collects runtime data using an **event** model and distinguish events from logs, metrics, and thread dumps.
2. Name the **JFR event groups** commonly used to investigate CPU, GC, allocation, I/O, synchronization, threads, and JVM activity.
3. Accurately interpret the meaning of **event type, timestamp/startTime, duration/endTime, event thread, payload, and stack trace** in a recording.
4. Distinguish **instant**, **duration**, **sampled**, and **periodic** events; understand why an event does not necessarily have a significant duration or a stack trace.
5. Create a `.jfr` file yourself, filter and read events using `jfr` or the Java 17+ API, and place events on a timeline without drawing false causal conclusions.

> **Key takeaway:** JFR stores typed events with metadata. Each event record indicates *what was observed*; the timestamp locates it in time; the duration (if present) represents the length of time the event measured; the stack trace (if collected) shows the call chain at the **stack capture point**. These four pieces of information complement one another, but they do not automatically form the complete execution history of a request.

## 1. What Is JFR and How Do Events Differ from Logs?

**Java Flight Recorder** is an observability system integrated into HotSpot/JDK that collects event records from the JVM, JDK libraries, and applications. Events are typically written to buffers at runtime and then assembled into a recording that can be saved as a binary `.jfr` file. It can be analyzed using the `jfr` tool, **Java Mission Control (JMC)**, or the `jdk.jfr.consumer` API.

Conceptual model:

```text
Application + JVM
    |
    | emits typed events with metadata
    v
JFR (event settings, timestamp, duration, payload, stack depending on configuration)
    |
    | writes to buffer / recording
    v
.jfr file
    |
    +--> jfr summary / jfr print
    +--> Java Mission Control (timeline, tables, flame graph depending on analysis)
    +--> RecordingFile / EventStream API
```

Comparison:

| Source | Nature | Which Questions Does It Answer Well? | Things to Keep in Mind |
| --- | --- | --- | --- |
| Application log | Messages written by code, usually text strings. | Business decisions, errors, correlation IDs, logged business flows. | Does not automatically carry CPU/GC/stack data for every operation. |
| Metric | Aggregated measurements over time: rates, counters, gauges. | CPU %, requests/s, GC pause p95, heap used. | Does not automatically identify the stack of a single occurrence. |
| Thread dump | Snapshot of thread stacks/states at the sampling point. | Where are threads, and what are they waiting on at snapshot time? | Does not automatically contain the full history of prior events. |
| **JFR event** | Record with type, timestamp, optional duration, thread, stack, and specialized fields. | What happened, when, for how long, and in what context? | May be sampled/filtered; absence of an event does not guarantee the activity did not occur. |

JFR is **not** a continuous log file containing every Java instruction, every method call, or every object allocation. The JVM tries to minimize overhead through configurations that select events, thresholds, sampling, periods, and buffers. Therefore, **the scope of observation depends on the recording settings**.

## 2. What Types of Events Does JFR Record?

The event names below are **representative examples** on modern HotSpot/JDK; whether a specific event is enabled or emitted depends on the **JDK, `.jfc` configuration file, threshold, and workload**. Not all of them are present in every file.

| Group | Example JFR Events | Practical Questions |
| --- | --- | --- |
| **GC & heap** | `jdk.GarbageCollection`, GC phase events, `jdk.GCHeapSummary` | When did GC occur, how long did it last, and how did the heap change? |
| **CPU / execution sampling** | `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` | Which stacks were sampled while running? How did process/machine CPU fluctuate? |
| **Memory allocation** | `jdk.ObjectAllocationSample`, other allocation event types depending on JDK/configuration | Which classes/objects appear in allocation samples; at which stacks do allocations occur? |
| **I/O** | `jdk.FileRead`, `jdk.FileWrite`, `jdk.SocketRead`, `jdk.SocketWrite` | Which I/O operations were slow, how many bytes, from which thread/stack? |
| **Synchronization / waiting** | `jdk.JavaMonitorEnter`, `jdk.ThreadPark` | Where are long monitor/park waits occurring; is there lock contention or queue wait? |
| **Threads and lifecycle** | `jdk.ThreadStart`, `jdk.ThreadEnd`, and events related to platform/virtual threads depending on JDK | When were threads started or terminated? |
| **Exceptions** | Events related to exceptions/throws, often needing explicit enabling for detailed capture | Which exceptions were thrown and at which call sites? |
| **Class/JIT/JVM** | Class loading, compilation, safepoint, flags, and environment events | How is the runtime loading classes, JIT-compiling, or stopping at safepoints? |
| **Application-defined** | Such as `demo.Task`, `app.OrderProcessed` from classes extending `jdk.jfr.Event` | When did a business step start/finish, and with what metadata? |

To see **which event types are actually present in a file**, use `jfr summary recording.jfr` or `jfr metadata recording.jfr`; to see which settings are enabled on a recording, check the actual `.jfc`/recording configuration. An absent `jdk.SocketRead` entry might mean no socket read occurred, the duration was below the threshold, the event was disabled, or the recording did not cover that time window.

### Distinguishing Four Common Event Kinds

1. **Instant event:** describes a point in time, such as thread start. `startTime` and `endTime` are identical, and `duration` is 0 according to the `RecordedEvent` API. You cannot measure *thread lifetime* from the start event alone.
2. **Duration event:** describes an operation from start to finish, such as socket read, thread park, monitor wait, or a custom business event measured with `begin()`/`end()`. It has `startTime`, `endTime`, and `duration`; short events may be dropped due to a **threshold**.
3. **Sampled event:** such as `jdk.ExecutionSample`, reflects only a sample point of a thread/stack according to a periodic interval or sampling algorithm; it does **not** mean every method invocation creates an event, nor does it mean the event's duration equals the CPU time used by the method.
4. **Periodic event:** such as CPU load or memory state metrics collected periodically. The timestamp marks when the metric was collected/recorded; payload fields may aggregate information over a time window. Do not infer that the entire window is the event's `duration`.

## 3. Structure of an Event Record: Type, Time, Thread, Payload, Stack

Imagine a `jdk.SocketRead` recorded with the following illustrative data (this is an **explanatory table**, not verbatim output produced by `jfr print`):

| Attribute | Illustrative Value | Meaning |
| --- | --- | --- |
| Event type | `jdk.SocketRead` | Identifies the event **type**. Many records of the same type can exist in a recording. |
| Start timestamp | `2026-10-29T09:30:15.100Z` | The point in time when the operation is considered to have started. |
| Duration | `85 ms` | The duration measured by the event: the operation may be waiting on I/O and does not necessarily use CPU continuously. |
| End timestamp | `2026-10-29T09:30:15.185Z` | The corresponding end point; logically equal to start + duration. |
| Event thread | `worker-4` | The thread associated with the event at recording time; not necessarily every thread involved in the system. |
| Payload | e.g. address/socket, bytes read | Specific fields provided by the event definition. |
| Stack trace | Sequence of `class.method(...)` frames | Call stack at the point JFR captured the stack, if enabled in the recording and supported by the type. |

Time formats displayed in the GUI, `jfr print`, or Java `Instant` may vary by tool and time zone. When comparing against logs, **normalize time zones** first—do not mistake different timestamp formats for events occurring at two different times.

An event type is described by metadata (name, label, category, field descriptors, and settings). **An event instance** is a concrete occurrence of that event type. `jdk.SocketRead` is the **type**; 500 reads during a recording can produce many `jdk.SocketRead` event **instances** if they satisfy the configuration.

### 3.1. `timestamp` / `startTime`: When?

The `RecordedEvent.getStartTime()` API returns a `java.time.Instant`, i.e., the **start time** of the event; `getEndTime()` returns the end time. For an instant event, the two timestamps are equal. Many tools display the time field named `startTime`, often referred to simply as the *timestamp*.

Do not confuse:

- **Event time**: when the activity occurred/was measured.
- **Commit time**: when the recorder accepted the event, or the data at `commit()` for application events.
- **Flush/file write time**: when buffered data is written to disk; this can be later than event time.
- **Analysis time**: when you open the `.jfr` file and inspect the results.

JFR buffers can be flushed to disk later; therefore, **file modification time** and **line order when printing a file** should not be used in place of event timestamps. When analyzing a timeline, take timestamps from the event metadata.

### 3.2. `duration`: How Long?

`RecordedEvent.getDuration()` returns a `java.time.Duration` measured at nanosecond resolution in the API. Semantically:

```text
eventStart ------------------------------------- eventEnd
    |<----------- event duration --------------->|

duration ≈ endTime - startTime
```

For a `SocketRead` operation lasting 85 ms, that is the **measured duration of the read operation**, which may include blocking/waiting for data/scheduling time. Do not automatically conclude 85 ms of **CPU time**. Nor should you infer that the entire HTTP request took exactly 85 ms, since a request may consist of many other steps.

Cases to note:

- For an **instant event**, duration is zero; this is not an error.
- For events with `@Threshold("10 ms")` or setting `threshold=10 ms`, events under 10 ms may **not be recorded**, even though the operation actually occurred.
- Some events have their primary meaning in a **payload measurement** (CPU load, byte count, utilization rate) rather than a meaningful duration.
- `Duration.toMillis()` **truncates down** to whole milliseconds; to analyze shorter operations, use `toNanos()` or more precise duration values.
- An unusually long event does not by itself prove that a method on the stack is consuming CPU: it may be **waiting time**, lock, network, or scheduling.

### 3.3. `stackTrace`: Where Was the Program?

`RecordedEvent.getStackTrace()` returns a `RecordedStackTrace` or `null`. When JFR collects a stack for an application-emitted event, `@StackTrace`/setting `stackTrace=true` enables recording the frame chain **at the moment of `Event.commit()`**, without automatically recording all methods executed over the entire duration. For JVM events, the stack reflects the context at the point where the JVM captures the stack for that event; for sampled events specifically, it means the stack **at the sampling point**.

A stack might show:

```text
com.example.Service.load()
  -> com.example.Client.read()
    -> java.net.Socket...
```

From this, you can ask "Which call path led to the socket read?", but you cannot yet assert that `Service.load()` used CPU throughout the entire duration.

**Essential limitations:**

- A stack trace may be **absent** because the type/setting/recording did not enable stack traces, or the JVM could not capture it in a specific case.
- Stacks may be **depth-limited**. Increasing the number of frames displayed by `jfr print` does not recover frames that were **never recorded**.
- An event's stack at commit/sampling time is **not a causal graph** across threads, processes, or services. You need request IDs/tracing/logs to connect cross-service operations.
- A stack appearing frequently in **samples** suggests an area worth investigating; the sample count does not directly equal the number of times the method was invoked.

### 3.4. What Roles Do Thread and Payload Play?

`eventThread`/`RecordedEvent.getThread()` indicates the thread associated with recording the event if captured; an event type also has domain-specific fields such as `bytesRead`, `duration`, address, GC type, object count, or operation ID. A JFR event may omit certain fields, so do not assume a fixed schema across all types/JDKs.

With **virtual threads**, the thread name and carrier thread can change over time; do not infer a fixed "one virtual thread = one platform thread" relationship from a single event. When correlating events for a single request, you need a reliable business correlation key (such as a request ID) if the application explicitly records one.

## 4. Relationship Among the Four Components on a Timeline

Consider three hypothetical events:

| Event | Start time | Duration | End time | What the Stack (if captured) Suggests |
| --- | --- | --- | --- | --- |
| `app.Request` | 10:00:00.000 | 120 ms | 10:00:00.120 | Position of `commit` in request-handling code |
| `jdk.SocketRead` | 10:00:00.020 | 70 ms | 10:00:00.090 | Call path to the read operation |
| `app.Checkpoint` | 10:00:00.100 | 0 ms | 10:00:00.100 | Position where the milestone event was emitted |

```text
10:00:00.000                    .020             .090   .100    .120
    |---------------------------|----------------|------|-------|
Request: [======================================================]
Socket :                             [====================]
Checkpoint:                                               *
```

This is an **illustrative timeline interpretation example**, not real output from a JVM. You can say the socket read occurred **within the interval** of the request, but to assert they belong to the **same request**, you must have correlation from thread/context, code, or tracing. Overlapping timestamps on a multi-request JVM are **not sufficient**.

Different pieces of data answer different questions:

- **What?** `eventType` and payload.
- **When?** `startTime`, `endTime`.
- **How long?** `duration` if the event represents a time interval.
- **Where in code?** `stackTrace` if recorded, plus the event thread.
- **Why?** Must combine context, logs, thresholds, other JFR events, and experiments; a single event alone does not prove root cause.

A duration event does not necessarily write two separate start/end records; normally **a single event record** contains the timing information covering the whole interval.

## 5. Capturing a JFR Recording from a Running JVM with `jcmd`

You need **JDK 17+** with `jcmd` and `jfr`, a running target JVM, and valid attach permissions. To find the right process:

```bash
jcmd -l
jcmd 12345 help JFR.start
```

`12345` is an **illustrative PID**; replace it with the real JVM PID. Option names and capabilities by JDK should be checked with `jcmd <PID> help JFR.start`, `help JFR.dump`, `help JFR.stop`.

### Method A: Record continuously and dump on demand

```bash
# Start a named recording with a lower-overhead configuration:
jcmd 12345 JFR.start name=runtime-check settings=default

# View active recordings:
jcmd 12345 JFR.check

# Create a .jfr snapshot file of the running recording:
jcmd 12345 JFR.dump name=runtime-check filename=/tmp/runtime-check.jfr

# When enough data has been collected, stop the recording:
jcmd 12345 JFR.stop name=runtime-check
```

- `settings=default` uses the JDK configuration designed for low overhead; `settings=profile` typically records more data and should be used for short periods when deep analysis is needed.
- `JFR.dump` **writes currently available data to a file while the recording continues running**. Do not confuse it with `JFR.stop`.
- The `filename` path for `JFR.dump` is resolved **by the target JVM**. If the JVM runs inside a container, `/tmp/runtime-check.jfr` lives in the filesystem seen by the **container JVM**.
- Collected data depends on how long the recording ran. If the activity had not occurred yet or events were filtered out, the file may not contain the event type you are looking for.
- When taking multiple snapshots, use distinct filenames to avoid overwriting earlier results.

### Method B: Recording that stops automatically after a fixed duration

```bash
jcmd 12345 JFR.start name=short-profile settings=profile duration=60s filename=/tmp/short-profile.jfr
```

Once the duration elapses, the JVM stops the recording and saves the file according to the configuration. Do not look for the file immediately when the start command returns and assume 60 seconds of data has already been captured. JFR documentation describes `duration`, directory, filename, and setting effects; always verify the actual state/file after completion.

**Permissions and resources:** requires the right user/PID namespace; minimal containers may lack `jcmd`. JFR produces sensitive data such as class/method names, paths, and runtime details. Choose storage locations, durations, access permissions, and retention policies appropriately. Do not enable high-frequency events with full stack traces en masse without measuring overhead.

## 6. Using `jfr` to Read Event Names, Timestamps, Durations, and Stacks

Assume `runtime-check.jfr` is already on the machine where you run the JDK tools (you may need to copy the file out of a container first).

```bash
# Summarize event types and sample counts:
jfr summary runtime-check.jfr

# Print JVM events recorded in the file:
jfr print --events jdk.GarbageCollection runtime-check.jfr

# Focus on I/O, showing more frames if the file has stacks:
jfr print --events jdk.SocketRead,jdk.SocketWrite --stack-depth 12 runtime-check.jfr

# Export selected events as JSON for analysis tools:
jfr print --json --events jdk.SocketRead runtime-check.jfr
```

`jfr summary` tells you which events **actually exist in the recording** and their counts. `jfr print` can filter by type name or category and increase the number of displayed frames with `--stack-depth`. Depending on the event/recording, the output may omit the stack trace field. The `--json` option changes **how events are printed**; it does not turn the underlying binary recording into an immutable schema across all JDKs.

When opening in **Java Mission Control**, you can inspect events on a timeline, filter by time/type/thread, and inspect durations and stacks if present. An effective approach is to inspect **event types and counts** first, then align durations and stacks at the same timestamps with load/GC/logs to understand their meaning.

### Reading Events via API Instead of Parsing Text

The JDK library `jdk.jfr.consumer.RecordingFile` provides these methods:

```java
RecordedEvent event = recordingFile.readEvent();
Instant startedAt = event.getStartTime();
Instant endedAt = event.getEndTime();
Duration elapsed = event.getDuration();
RecordedStackTrace trace = event.getStackTrace();
```

This is only an **illustrative snippet in the context of an already-opened `RecordingFile`**; a complete runnable program is in section 7. For large files, iterate event by event using `hasMoreEvents()`/`readEvent()` rather than `RecordingFile.readAllEvents()` to avoid holding all events in memory.

## 7. Java 17+ Practice: Creating Two Event Types and Inspecting the Four Components

This exercise creates **one duration event** and **one instant event**, then reads them back from a `.jfr` file, letting you see the time/duration/stack relationships without depending on whether a network call or GC happens to occur.

Create the file **`JfrTimelineDemo.java`**:

```java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public class JfrTimelineDemo {
    @Name("demo.Task")
    @Label("Demo timed task")
    @Category({"Demo", "Learning"})
    static class TaskEvent extends Event {
        @Label("Operation")
        String operation;
    }

    @Name("demo.Checkpoint")
    @Label("Demo checkpoint")
    @Category({"Demo", "Learning"})
    static class CheckpointEvent extends Event {
        @Label("Message")
        String message;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-timeline-demo.jfr").toAbsolutePath();

        try (Recording recording = new Recording()) {
            recording.enable(TaskEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.enable(CheckpointEvent.class)
                    .withStackTrace();

            recording.start();

            TaskEvent task = new TaskEvent();
            task.operation = "simulate-wait";
            task.begin();
            Thread.sleep(80);
            task.end();
            task.commit();

            CheckpointEvent checkpoint = new CheckpointEvent();
            checkpoint.message = "after-task";
            checkpoint.commit();

            recording.stop();
            recording.dump(file);
        }

        int customEvents = 0;
        try (RecordingFile reader = new RecordingFile(file)) {
            while (reader.hasMoreEvents()) {
                RecordedEvent event = reader.readEvent();
                String type = event.getEventType().getName();

                if (!type.equals("demo.Task")
                        && !type.equals("demo.Checkpoint")) {
                    continue;
                }

                customEvents++;
                System.out.println("event=" + type);
                System.out.println("start=" + event.getStartTime());
                System.out.println("end=" + event.getEndTime());
                System.out.println(
                        "durationMs=" + event.getDuration().toMillis());
                System.out.println(
                        "stackPresent=" + (event.getStackTrace() != null));
            }
        }

        System.out.println("customEvents=" + customEvents);
        System.out.println("file=" + file.getFileName());
    }
}
```

Compile and run in the directory containing the file (no Maven/Gradle dependencies required):

```bash
javac --release 17 JfrTimelineDemo.java
java JfrTimelineDemo
```

You can reliably verify the **last two lines** of output:

```text
customEvents=2
file=jfr-timeline-demo.jfr
```

The `event`, `start`, `end`, `durationMs`, and `stackPresent` lines preceding the last two lines **depend on execution timing and configuration**. You will see two events with types `demo.Task` and `demo.Checkpoint` (do not assume every JDK version orders them identically when iterating the file). `demo.Task` has a duration around or greater than 80 ms because `Thread.sleep(80)` may wait extra for the scheduler; `demo.Checkpoint` calls `commit()` directly without `begin()`, so it represents an instant milestone with duration 0. `stackPresent` is typically `true` due to `.withStackTrace()`.

Inspect the newly created file:

```bash
jfr summary jfr-timeline-demo.jfr
jfr print --events demo.Task,demo.Checkpoint --stack-depth 12 jfr-timeline-demo.jfr
```

**Why this example works:**

- `TaskEvent` and `CheckpointEvent` both extend `jdk.jfr.Event`; `@Name` sets the type name for filtering, `@Category` provides grouping metadata, and fields `operation`/`message` are the **payload**.
- `recording.enable(...).withThreshold(Duration.ZERO).withStackTrace()` enables the event, prevents short duration events from being dropped by a threshold, and requests stack capture at commit time.
- `task.begin()` before sleep and `task.end()` after sleep: duration reflects **elapsed time** between the two points, including time spent waiting; it **does not measure CPU time**.
- `task.commit()` records the event along with its payload and timing data; the stack is the commit location in `main`, not the entire 80 ms execution.
- `checkpoint.commit()` without a `begin()`/`end()` pair models an instant event.
- `recording.stop()` closes the recording interval; `recording.dump(file)` saves the data to `.jfr` before closing the recording resource.
- `RecordingFile` iterates over many events, including system events if present; we only print those whose exact type name matches our `demo.` events.

**Extension exercise:** change `withThreshold(Duration.ZERO)` on `demo.Task` to `withThreshold(Duration.ofMillis(200))`, keep the sleep around 80 ms, and run again from scratch with a new file/name. That duration event will normally **not be recorded** because it is shorter than the threshold; `customEvents` will typically become 1. This behavior illustrates why not finding an event **does not prove** the operation never happened.

## 8. Combining Event, Timestamp, Duration, and Stack to Investigate an Issue

Suppose request latency increases abnormally. Proceed along a verifiable sequence:

1. **Select the actual failure time window.** Record the request timestamp from logs, time zone, PID, workload, and the interval covered by the recording.
2. **Check that the recording has the needed events:** `jfr summary`; if `jdk.SocketRead` or `jdk.JavaMonitorEnter` is missing, inspect the profile/threshold settings instead of assuming there was no I/O or lock contention.
3. **Filter events by time window and thread.** One JVM handles many concurrent requests; you need a solid link such as a request ID in an application event, context, or trace if you want to attribute events to a single request.
4. **Read both `startTime` and `duration`.** A 300 ms socket read inside a 500 ms request may be a major contributor; however, you must verify the actual operation and related events. `jdk.ExecutionSample` events are only samples and do not represent operation length.
5. **Open stack traces with the right semantics.** For I/O/wait events, the stack shows where the call originated; for sampled events, the stack is at the sampling instant; for custom events, the stack is at commit time. Multiple events may be needed to establish the cause.
6. **Cross-reference GC/CPU/locks/metrics.** A GC pause or hot CPU may coincide with slow I/O, but temporal overlap alone is not enough to prove causation.
7. **Gather controlled follow-up evidence:** compare recordings, adjust targeted thresholds or event settings, and avoid enabling all events with all stacks indefinitely.

### Examples Distinguishing Valid Conclusions from Hasty Ones

| Data in JFR | Valid Conclusion | Unwarranted Conclusion |
| --- | --- | --- |
| `jdk.SocketRead` duration 250 ms | A read operation was measured at roughly 250 ms. | CPU ran for 250 ms, or the whole request took only 250 ms. |
| `jdk.ExecutionSample` repeating frequently on one stack | That stack was sampled often during the recording window, warranting CPU analysis. | The method was called exactly N times or used CPU for the entire interval between two samples. |
| `jdk.JavaMonitorEnter` with long duration | There was a monitor wait long enough for JFR to record. | The entire system is deadlocked or the thread is permanently BLOCKED. |
| `jdk.CPULoad` CPU increasing | Observed CPU level was high during the measurement interval. | A specific class caused high CPU without checking stacks/samples. |
| `RecordedEvent.getStackTrace() == null` | The recording has no stack trace for that event. | The JVM was not running Java code or had no call stack. |
| No events seen with 2 ms duration | No such event exists in the recorded data. | No 2 ms operations occurred: they may have been filtered out by a threshold. |

## 9. Settings That Determine What You See

Common JDK JFR settings include:

| Setting | Meaning | Effect on Interpretation |
| --- | --- | --- |
| `enabled` | Enables/disables recording an event type. | Disabled types produce no recorded instances. |
| `threshold` | Only records duration events meeting the time threshold. | Short events may disappear, **biasing the duration distribution toward long operations**. |
| `stackTrace` | Requests a stack trace for the event when possible. | Enabling adds context but increases data/overhead; if disabled or unavailable, the API returns `null`. |
| `period` | Interval for emitting periodic events. | Fewer samples do not mean the phenomenon vanished. |
| Event sampling / profile | Frequency and set of events sampled/recorded. | Sample count does not equal method invocation count. |

Two common JDK configurations:

- **`default.jfc`** (or `settings=default`): event set and overhead level suitable for longer-running recordings.
- **`profile.jfc`** (or `settings=profile`): collects richer information for deep analysis at higher overhead; use within bounded windows and measure impact.

JFR does not always collect **every stack**, **every allocation**, **every exception**, or **every I/O call**. Before saying "there is no problem," verify **whether the event type is enabled, what the threshold is, and when the recording started and stopped**.

## 10. Common Misconceptions

| Misconception | What Is True |
| --- | --- |
| "An event's timestamp is when the `.jfr` file was written." | Event timestamps indicate when the activity was observed; buffering/dumping may write the file later. |
| "A long-duration event means CPU-bound work." | Duration is usually elapsed time; it can include waiting on I/O, locks, or the scheduler. |
| "An event type is a single occurrence." | One type has many event instances; distinguish type metadata from individual event records. |
| "JFR records every Java method call." | JFR selects events via settings, thresholds, and sampling; it does not automatically record every method call. |
| "The stack in a duration event represents the entire execution." | The stack usually reflects the record/commit point or sampling point, not the full sequence of states over time. |
| "No stack = no Java code." | Stacks may be disabled, unavailable in the recording, or truncated. |
| "`jfr print --stack-depth 100` recovers the full stack." | It only increases the number of frames **displayed if enough frames were recorded**; it cannot recover uncaptured frames. |
| "Two events with close timestamps definitely belong to the same request." | You need thread/context/correlation and concurrency checks; matching timestamps alone are not enough. |
| "`JFR.dump` stops the recording." | `JFR.dump` writes a snapshot while the recording can continue; `JFR.stop` is the stop command. |
| "Duration 0 is a broken event." | Valid instant events have a duration of 0. |

## 11. Self-Check Questions

1. **How does a JFR event differ from an event type?** An event type is the **schema/category**; an event is a recorded occurrence carrying a specific type, time, and fields.
2. **How do `startTime` and `endTime` relate for an instant event?** They are equal, with `duration = 0`.
3. **Is the duration of `jdk.SocketRead` CPU time?** No. It is the measured duration of the operation, which can include time spent waiting on I/O.
4. **Why might a slow operation be missing from JFR?** The recording did not cover that time, the event was disabled, threshold/sampling filtered it, event configuration omitted it, or the JVM/JDK did not support that event.
5. **At what point in time is the stack trace captured in a custom JFR event?** Usually when `Event.commit()` is called if `stackTrace` is enabled.
6. **Does JFR automatically link two events at the same timestamp into one request?** No. You need a correlation ID, thread context, or grounded tracing information.
7. **If you want to know how many `jdk.SocketRead` events are in a file, which command should you run first?** `jfr summary recording.jfr`, followed by `jfr print --events jdk.SocketRead recording.jfr` to inspect details.
8. **How should `jdk.ExecutionSample` events be read?** As stack samples collected via a sampling mechanism; do not equate each sample with one method call or a duration.

## References

- [Oracle JDK 21 — JFR API, package `jdk.jfr`, settings and event definitions](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html).
- [Oracle JDK 21 — `jdk.jfr.Event` (`begin`, `end`, `commit`, `shouldCommit`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Event.html).
- [Oracle JDK 21 — `RecordedEvent` (`getStartTime`, `getEndTime`, `getDuration`, `getStackTrace`)](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html).
- [Oracle JDK 21 — `jcmd` (`JFR.start`, `JFR.dump`, `JFR.check`, `JFR.stop`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 21 — `jfr` (`summary`, `print`, `--events`, `--stack-depth`, `--json`)](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html).
- [Oracle JDK 21 — `RecordingFile` and iterating large files](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html).
