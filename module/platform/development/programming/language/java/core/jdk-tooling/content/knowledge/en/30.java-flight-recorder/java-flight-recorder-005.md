# Events in Java Flight Recorder (JFR)

**Java Flight Recorder (JFR)** is an event collection and profiling framework built into the JDK. JFR records what the JVM and application are doing along a timeline, including CPU, threads, garbage collection, allocation, class loading, exceptions, file I/O, socket I/O, and application-defined custom events.

A **JFR event** is a record with a timestamp, event type information, and a payload. Depending on the event type, a record may include a duration, stack trace, thread, class, or custom data fields. A recording file can contain thousands or millions of events; analysis tools use these events to build timelines, statistics, and identify bottlenecks.

JFR is useful when answering questions such as:

- Which thread is using the most CPU?
- Which methods appear most frequently in CPU samples?
- When does garbage collection occur and how long are the pauses?
- In which areas of code is object allocation increasing?
- Which monitor or lock is blocking threads?
- How long is the application waiting on files, sockets, or databases?
- Which classes were loaded or unloaded during an incident?
- Which requests are slower than the expected threshold?
- Does a specific business behavior correlate with GC, lock contention, or I/O?

This article focuses on the event model, commonly used event groups, how to configure recordings, how to read `.jfr` files, and how to create custom events using Java 17+. Event names, settings, and available data depend on the JDK release, JVM, and selected template; inspect the metadata of an actual recording before building automated analysis.

## 1. JFR and the event model

JFR collects data as timestamped events. Events are written to a recording repository/buffer and can be saved as a binary `.jfr` file for later analysis.

General model:

~~~text
Java application + HotSpot JVM
             |
             | JVM events / application events
             v
       Java Flight Recorder
             |
             | timestamped events
             v
     Recording buffers / repository
             |
             | dump
             v
          file.jfr
             |
       +-----+------+
       |            |
       v            v
 JDK Mission     jfr command /
 Control (JMC)   JFR consumer API
       |            |
       +-----+------+
             |
             v
   Timeline, tables, charts,
   event details and analysis
~~~

JFR and JDK Mission Control (JMC) are commonly used together:

- JFR collects data from the JVM and the application.
- JMC opens recording files, displaying timelines, charts, tables, and automated analysis results.
- The `jfr` command-line tool summarizes, filters, and prints events.
- The `jdk.jfr.consumer` API allows other applications to read or process events in Java code.

JFR is suitable for profiling and diagnostics while the application is running. Recordings can be started at JVM startup or at runtime using `jcmd`/JMC.

## 2. Four common event types

The JDK categorizes events by how they are emitted and recorded. Four key types are duration, instant, sample, and custom events.

### Duration event

A duration event has a start time and an end time. The event represents an activity that spans a period of time.

Examples:

- A thread waiting on a monitor.
- A thread waiting for an I/O operation.
- A garbage collection phase.
- An instrumented method or business task.
- Processing time of a request.

Duration helps answer when an activity started, when it ended, and how long it took.

A typical application-defined duration event:

~~~java
event.begin();
// Perform the work to be measured
event.end();
event.commit();
~~~

JFR records the event's timestamp and duration upon commit.

### Instant event

An instant event occurs at a single point in time and is recorded immediately when committed. The event does not need to measure a start/end interval.

Examples:

- An exception is thrown.
- A thread is created.
- A business state or milestone occurs.
- A configuration change takes place.

For a custom instant event, simply assign the fields and call `commit` without `begin`/`end`.

### Sample event

A sample event is recorded periodically or via a sampling mechanism. It provides periodic snapshots of the system state.

Examples:

- CPU load.
- Thread execution samples.
- Certain JVM statistics emitted periodically.

Sampling helps estimate behavior over time with lower overhead than instrumenting and recording every method call. Because it is sampled, the data does not necessarily cover every execution.

### Custom event

A custom event is defined by an application or library to record business-specific data.

Examples:

- `OrderProcessed`: an order was processed.
- `SlowHttpRequest`: an HTTP request exceeded a threshold.
- `SqlOperation`: a SQL operation completed.
- `PaymentAttempt`: a payment attempt.
- `CacheLookup`: cache access result and duration.

Custom events help correlate business data with JVM events. When a request is slow, you can check whether GC pauses, thread contention, CPU saturation, or slow socket reads occurred during the same time window.

## 3. Structure of an event

An event typically has the following components:

| Component | Meaning |
|---|---|
| Event name/type | Identifier name of the event type |
| Timestamp | Time when the event started or was recorded |
| Duration | Length of time if it is a duration event |
| Thread | Associated thread, when the event provides this information |
| Stack trace | Call stack at the time the event was recorded, if enabled |
| Payload fields | Data describing the event |
| Metadata | Label, description, category, unit, and display information |

Illustrative example:

~~~text
com.acme.OrderProcessed {
  startTime = 10:15:20.120
  duration = 42.5 ms
  orderId = "ORD-105"
  itemCount = 3
  succeeded = true
  eventThread = "http-worker-7"
}
~~~

This is simulated data to illustrate the structure, not fixed output from a JVM.

### Timestamp and duration

Timestamp places the event at the right position on the timeline. Duration indicates how long the event lasted. During performance analysis, compare event durations against the application's SLA or latency budget.

Instant events do not have a duration in the sense of measuring an execution interval. Duration events have a start time and an end time. Sample events are recorded at the sampling point.

### Stack trace

A stack trace shows the call path associated with the event, helping trace back to the method or call site that caused the activity.

Not all events include a stack trace. Stack traces may be disabled in event settings, limited by stack depth, or omitted in certain sample events.

Deeper stack traces provide more detail but can increase recording size and overhead. Only increase stack depth when the diagnostic question requires it.

### Payload fields

The payload consists of additional fields describing the event. For example, a custom event might record `orderId`, item count, and processing result.

Only record fields with diagnostic value. Do not put passwords, access tokens, session cookies, private request contents, or unnecessary personal data into the payload.

## 4. Built-in JVM event groups

JFR includes many built-in events. The template determines which events are enabled, which thresholds are applied, and whether stack traces are collected.

The names below are common examples; available events and fields may vary by JDK and recording settings.

### CPU and execution

| Example event | Information |
|---|---|
| jdk.CPULoad | Process/JVM and machine CPU load |
| jdk.ExecutionSample | Stack sample of an executing thread |
| jdk.NativeMethodSample | Sample related to native execution when supported |

Use these events to find methods or call paths that appear frequently in CPU samples, and to compare JVM CPU usage against overall machine CPU usage.

`ExecutionSample` is sampling data, not a complete list of every method call. A method appearing frequently in samples is a candidate for investigation, but should be interpreted alongside workload and execution time.

### Thread and synchronization

| Example event | Information |
|---|---|
| jdk.ThreadStart | Thread created |
| jdk.ThreadEnd | Thread ended |
| jdk.JavaMonitorEnter | Thread waiting to enter a synchronized monitor |
| jdk.JavaMonitorWait | Thread waiting on a monitor |
| jdk.ThreadPark | Thread parked |
| jdk.ThreadSleep | Thread sleeping |

These events help detect lock contention, long thread waits, abnormal thread lifecycles, and time the application spends not executing because it is waiting for resources.

For `JavaMonitorEnter`, pay attention to duration and stack traces. Many long-duration events on the same monitor can indicate a `synchronized` region limiting throughput.

### Garbage collection and memory

| Example event | Information |
|---|---|
| jdk.GarbageCollection | A GC cycle |
| jdk.GCPhasePause | A GC pause phase |
| jdk.GCHeapSummary | Heap information at GC milestones |
| jdk.ObjectAllocationSample | Allocation sample |
| jdk.MetaspaceSummary | Metaspace information when the event is enabled |

Use this group to inspect GC pauses, heap usage, allocation pressure, and live set changes. Do not conclude a memory leak from a single event or a single heap increase; compare across multiple points in time under equivalent workloads.

### Class loading and exceptions

| Example event | Information |
|---|---|
| jdk.ClassLoad | Class loaded |
| jdk.ClassUnload | Class unloaded |
| jdk.JavaExceptionThrow | Exception thrown |

If the number of classes increases continuously while class unloads remain low, check class loader lifecycles, dynamic proxies, generated classes, and plugin reloads. Exception events can help find frequently thrown exceptions, including those caught immediately afterward.

### File and network I/O

| Example event | Information |
|---|---|
| jdk.FileRead | File read operation |
| jdk.FileWrite | File write operation |
| jdk.SocketRead | Socket read operation |
| jdk.SocketWrite | Socket write operation |

I/O events are useful when latency is not caused by CPU or GC, but by waiting on the file system, sockets, or external services. Inspect duration, I/O size, thread, and stack trace if recorded.

### Verifying available events

Do not assume an event always exists or is enabled in every recording. You can inspect the file's metadata:

~~~bash
jfr metadata recording.jfr
~~~

Filter metadata by category or event:

~~~bash
jfr metadata --categories GC recording.jfr
jfr metadata --events jdk.CPULoad recording.jfr
~~~

You can list the event types in a file with:

~~~bash
jfr view types recording.jfr
~~~

Metadata shows event names, categories, and field layouts. This is a better basis than writing a parser against a fixed list of events.

## 5. Recording settings: default and profile

JFR ships with two common templates in the directory:

~~~text
JAVA_HOME/lib/jfr/
  default.jfc
  profile.jfc
~~~

These two templates control which events are recorded, duration thresholds, sampling periods, stack traces, and other settings.

| Template | Purpose | Characteristics |
|---|---|---|
| default.jfc | Continuous recording and routine observation | Collects a useful dataset with low overhead |
| profile.jfc | Targeted profiling over short periods | Collects more events, which may increase overhead |

`default.jfc` is generally suitable for continuous recordings and long-term monitoring. According to the JFR API documentation, this template typically has under 1% overhead, though actual results depend on workload and settings.

An important limitation: the `default` template in JDK 26 does not collect heap statistics or allocation profiling. If you need to analyze allocations or heap trends, use `profile` or appropriate custom settings.

`profile.jfc` collects more data, such as allocation information and more detailed stack traces. Use it for short windows to pinpoint specific root causes, then switch back to a lighter configuration if continuous recording is needed.

### Do not enable all events

Enabling too many events, setting thresholds too low, or sampling too frequently can:

- Increase recording data volume.
- Increase CPU and memory used for recording events.
- Increase file size.
- Increase application overhead.
- Generate too many events, making analysis harder.

Choose events based on the question you need to answer, not on the principle of collecting everything.

## 6. Two common recording styles

### Time-fixed recording

A time-fixed recording runs for a specified duration and then stops.

Examples:

- Profiling for 2 minutes while reproducing slow requests.
- Collecting 5 minutes during a CPU spike.
- Recording during a load test.
- Monitoring a deployment or warm-up.

Time-fixed recordings often use `profile.jfc` to capture richer data.

### Continuous recording

A continuous recording runs long-term, retaining recent data in a buffer/repository. When an investigation is needed, operators dump the relevant time range to a file.

When the buffer or repository reaches its limit, the oldest data may be discarded to make room for new data. Therefore, continuous recording is well suited for preserving recent history leading up to an incident.

`default.jfc` is a common choice for continuous recording. You can bound data age and size to prevent the recording from consuming disk space uncontrollably.

## 7. Starting a recording at JVM startup

Use the `StartFlightRecording` startup option:

~~~bash
java -XX:StartFlightRecording:settings=default,duration=5m,name=boot,filename=boot.jfr -jar app.jar
~~~

This example starts a recording when the application launches, uses `default` settings, records for 5 minutes, and saves to `boot.jfr`.

You can set a delay:

~~~bash
java -XX:StartFlightRecording:delay=20s,duration=2m,settings=profile,name=startup-profile,filename=startup.jfr -jar app.jar
~~~

The JVM waits 20 seconds and then starts recording for 2 minutes. This is useful when you want to skip initial startup or only capture a specific phase.

### Dumping a recording on JVM exit

~~~bash
java -XX:StartFlightRecording:settings=default,dumponexit=true,filename=shutdown.jfr -jar app.jar
~~~

`dumponexit` instructs the JVM to write the recording to a file on shutdown. Ensure the output directory exists and the process has write permissions.

### Continuous recording from startup

~~~bash
java -XX:StartFlightRecording:settings=default,disk=true,maxage=6h,maxsize=1g -XX:FlightRecorderOptions:repository=/var/tmp/jfr -jar app.jar
~~~

This example retains data for up to 6 hours and limits the disk repository size to 1 GB. The repository path must have sufficient disk space and write permissions.

## 8. Starting a recording at runtime with jcmd

If the JVM is already running, use `jcmd` instead of restarting just to enable a recording.

Find the PID:

~~~bash
jcmd -l
~~~

Check JFR commands:

~~~bash
jcmd 2125 help JFR.start
~~~

Start a 5-minute recording:

~~~bash
jcmd 2125 JFR.start name=incident settings=profile duration=5m filename=/secure/records/incident.jfr
~~~

Components:

- PID `2125` is an example; replace with the actual PID.
- `name` identifies the recording.
- `settings` selects `default` or `profile`.
- `duration` limits the recording time.
- `filename` specifies the output file.

If you only need lightweight continuous recording, choose `settings=default`. If you are investigating CPU, allocation, lock contention, or latency over a short window, you can choose `profile`.

### Checking running recordings

~~~bash
jcmd 2125 JFR.check
~~~

View detailed event settings:

~~~bash
jcmd 2125 JFR.check verbose=true
~~~

### Dumping a snapshot while keeping the recording running

~~~bash
jcmd 2125 JFR.dump name=incident filename=/secure/records/incident-snapshot.jfr
~~~

`JFR.dump` writes currently available data to a file while the recording continues. This is useful for taking a snapshot mid-incident without ending data collection.

You can bound the dump time range using `begin`, `end`, `maxage`, or `maxsize` according to the current JDK syntax.

### Stopping a recording and saving the file

~~~bash
jcmd 2125 JFR.stop name=incident filename=/secure/records/incident-final.jfr
~~~

`JFR.stop` ends the recording and saves the data to the specified file. If `filename` is omitted, recording data may be discarded when stopped; check the target JDK syntax before stopping.

## 9. Configuring continuous recording with jcmd

You can create a rolling recording:

~~~bash
jcmd 2125 JFR.start name=rolling settings=default disk=true maxage=6h maxsize=1g
~~~

Meaning:

- `disk=true` writes data to the disk repository.
- `maxage=6h` limits retained data to a maximum of 6 hours.
- `maxsize=1g` limits data size.
- `name=rolling` identifies the recording.

When an incident occurs, dump the data:

~~~bash
jcmd 2125 JFR.dump name=rolling filename=/secure/records/incident-window.jfr
~~~

The rolling recording continues running after the dump. To stop it completely:

~~~bash
jcmd 2125 JFR.stop name=rolling filename=/secure/records/rolling-final.jfr
~~~

Do not leave a continuous recording running without `maxage`/`maxsize` limits unless you have a storage and retention management plan.

## 10. Event settings: enabled, threshold, period, and stackTrace

Event settings determine which events are recorded and at what level of detail.

| Setting | Meaning | Example |
|---|---|---|
| enabled | Enable/disable event | true or false |
| threshold | Record duration events only if they meet the threshold | 10 ms |
| period | Interval for emitting periodic events | 1 s |
| stackTrace | Whether to record stack traces | true or false |
| throttle | Rate limit for event emission | 100/s |
| filter | Filter certain events by class/method or annotation, depending on event support | java.util.HashMap |

### enabled

If `enabled=false`, the event is not recorded. Enabling an event only takes effect when a recording is running and its settings allow that event.

### threshold

`threshold` is the minimum duration for an event to be recorded. For example, a `10 ms` threshold on `JavaMonitorEnter` means monitor contentions shorter than that threshold are not recorded.

`threshold` is useful when you only want to focus on significantly slow operations. If set too high, short but very frequent contentions may be missed.

### period

`period` applies to periodic or sampled events. For example, CPU Load sampled every second:

~~~text
jdk.CPULoad#period=1 s
~~~

Lowering the period increases sampling frequency and can increase data volume.

### stackTrace

`stackTrace=true` instructs JFR to record a stack trace when the event is emitted. Stack traces help identify call paths but can increase overhead and recording size.

### throttle

`throttle` limits the rate of event emission. For example, `100/s` caps the event rate at approximately 100 events per second according to the corresponding setting.

### filter

Some events support `filter` to restrict the classes, methods, or annotations being monitored. Not all events have a `filter` setting; check metadata or JFR API help to confirm.

## 11. Creating custom .jfc settings

You do not need to edit `default.jfc` or `profile.jfc` directly. Create a new file based on an existing template:

~~~bash
jfr configure --input profile.jfc --output incident.jfc jdk.JavaMonitorEnter#threshold=5ms
~~~

This example creates a new configuration with a 5 ms lock contention threshold. `incident.jfc` is your own copy; the original template remains intact.

You can add a custom event setting by prefixing the event name with a plus sign:

~~~bash
jfr configure --input default.jfc --output app-events.jfc +com.acme.OrderProcessed#enabled=true
~~~

Use a custom configuration when you need to record specific events or change sampling periods, thresholds, or stack traces.

When using `JFR.start`, you can specify the settings file:

~~~bash
jcmd 2125 JFR.start name=custom settings=/etc/acme/incident.jfc duration=5m filename=incident.jfr
~~~

Event settings can also be passed directly in `JFR.start` in the form `event-name#setting=value`. When a command-line setting conflicts with the `.jfc` configuration, the command-line value takes precedence.

## 12. Reading recording files with the jfr command

`.jfr` files are binary files. Do not open them directly in a text editor.

### Viewing a summary

~~~bash
jfr summary incident.jfr
~~~

`summary` shows recording information, duration, size, and event counts by type. This is the first step to confirm the file contains data and understand which events dominate the recording.

### Printing all events

~~~bash
jfr print incident.jfr
~~~

Output can be very long. Filter for the events you want to inspect.

### Filtering events by name

~~~bash
jfr print --events jdk.GarbageCollection,jdk.CPULoad incident.jfr
~~~

### Filtering by category

~~~bash
jfr print --categories GC incident.jfr
~~~

### Exporting JSON

~~~bash
jfr print --json --events jdk.GarbageCollection incident.jfr
~~~

JSON or XML is suitable for integrating with data processing tools, but build parsers against the schema of the actual recording and JDK.

### Adjusting stack trace depth

~~~bash
jfr print --stack-depth 20 incident.jfr
~~~

Stack traces are truncated at a default depth. Increasing the depth shows deeper call paths but can enlarge the output.

### Viewing summary views

~~~bash
jfr view all-views incident.jfr
jfr view all-events incident.jfr
~~~

You can also view a single event type as a view:

~~~bash
jfr view jdk.GarbageCollection incident.jfr
~~~

### Viewing metadata

~~~bash
jfr metadata incident.jfr
~~~

Metadata shows event names, categories, and field layouts. Use it to verify event and field names before writing code to process recordings.

## 13. Analyzing recordings with JDK Mission Control

JDK Mission Control (JMC) provides a visual interface for analyzing `.jfr` files. JMC is not necessarily bundled with a standard JDK installation; download it from the official site and use a compatible version.

An analysis workflow:

1. Open JMC and select the recording file.
2. Check **Overview** to verify the time range and event counts.
3. Open **Automated Analysis Results** to inspect warnings and heuristics.
4. Check **CPU/Code** to find methods and packages consuming the most CPU.
5. Check **Threads** and **Locks** to find contention, thread parking, or waits.
6. Check **Memory** and **Garbage Collections** to inspect heap, allocations, and pauses.
7. Check **I/O** to find long-running file or socket operations.
8. Open **Event Browser** to inspect specific event types and fields.
9. Select a notable time range and drill down into the corresponding events.
10. Correlate with logs, metrics, traces, and the incident timeline.

### CPU and Code

Inspect CPU load, execution samples, top methods, and stack traces. If process CPU is high, look for methods appearing frequently in samples. If CPU is low while requests are slow, check thread waiting, locks, or I/O.

### Threads and Locks

Inspect thread activity, thread states, and monitor contention. A lock with many long-duration events can be a bottleneck. Check both the thread holding the lock and the threads waiting on it.

### Memory and GC

Inspect heap usage, allocation rate, object allocation samples, GC events, and pause durations. Heap growing and dropping after GC can be normal behavior; a steadily rising live set over time is a signal that warrants deeper investigation.

### I/O

Inspect file read/write and socket read/write durations. Long I/O events can indicate the application is waiting on storage, the network, or external services.

### Event Browser

Event Browser lists event types and per-type statistics. You can create custom pages to focus on a specific event.

## 14. Creating custom events with the Java API

The JFR API resides in the `jdk.jfr` module. You can create an event by extending `jdk.jfr.Event` and declaring the fields to record.

Useful annotations:

| Annotation | Role |
|---|---|
| @Name | Stable event name |
| @Label | Human-friendly display name |
| @Description | Description of the event or field |
| @Category | Groups events in analysis tools |
| @Threshold | Default duration threshold |
| @StackTrace | Enables/disables stack trace by default |
| @Period | Interval for periodic events |

Example business event `OrderProcessed`:

~~~java
@Name("com.acme.OrderProcessed")
@Label("Order Processed")
@Category({"Acme", "Orders"})
@Description("Records the processing of an order")
static class OrderProcessed extends Event {
    @Label("Order ID")
    String orderId;

    @Label("Item Count")
    int itemCount;

    @Label("Succeeded")
    boolean succeeded;
}
~~~

### Supported field types

Event classes support:

- Primitives: `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`.
- `String`.
- `Thread`.
- `Class`.

Arrays, enums, and other reference types are not recorded as regular event fields. Static fields are also excluded from the payload. Use simple, meaningful fields so JMC displays them clearly.

### Measuring a duration event

~~~java
OrderProcessed event = new OrderProcessed();
event.begin();

// Perform the work

event.end();
if (event.shouldCommit()) {
    event.commit();
}
~~~

`begin` starts timing, `end` stops the interval, and `commit` records the event. `shouldCommit` checks whether the event is enabled and meets the threshold before committing. You can use it to avoid building expensive payload data when the event will not be recorded.

### Recording an instant event

For events that do not need a duration:

~~~java
OrderStatusChanged event = new OrderStatusChanged();
event.orderId = "ORD-105";
event.status = "PAID";
event.commit();
~~~

There is no need to call `begin`/`end` for an instant event.

## 15. Java 17+ example: writing custom events to a JFR file

This example creates a recording, writes 5 `OrderProcessed` events, stops the recording, and exports `orders.jfr`.

Structure:

~~~text
project/
  src/
    com/acme/JfrEventDemo.java
  out/
~~~

File `src/com/acme/JfrEventDemo.java`:

~~~java
package com.acme;

import java.nio.file.Path;

import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrEventDemo {

    @Name("com.acme.OrderProcessed")
    @Label("Order Processed")
    @Category({"Acme", "Orders"})
    @Description("Records the processing of an order")
    static class OrderProcessed extends Event {
        @Label("Order ID")
        String orderId;

        @Label("Item Count")
        int itemCount;

        @Label("Succeeded")
        boolean succeeded;
    }

    public static void main(String[] args) throws Exception {
        Path output = Path.of("orders.jfr");

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("default"))) {
            recording.setName("orders-demo");
            recording.enable(OrderProcessed.class);
            recording.start();

            for (int i = 1; i <= 5; i++) {
                OrderProcessed event = new OrderProcessed();
                event.begin();
                Thread.sleep(10);
                event.end();

                if (event.shouldCommit()) {
                    event.orderId = "ORD-" + i;
                    event.itemCount = i;
                    event.succeeded = true;
                    event.commit();
                }
            }

            recording.stop();
            recording.dump(output);
        }

        System.out.println("RECORDING=orders.jfr");
        System.out.println("EVENTS=5");
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 --add-modules jdk.jfr -d out src/com/acme/JfrEventDemo.java
~~~

Run:

~~~bash
java --add-modules jdk.jfr -cp out com.acme.JfrEventDemo
~~~

Exact stdout:

~~~text
RECORDING=orders.jfr
EVENTS=5
~~~

The `orders.jfr` file is created in the working directory. Event duration spans from `begin` to `end`; the payload records the order ID, item count, and processing status.

### Inspecting custom events

View summary:

~~~bash
jfr summary orders.jfr
~~~

Print only the custom event:

~~~bash
jfr print --events com.acme.OrderProcessed orders.jfr
~~~

The output contains actual timestamps and durations, so timing numbers vary by machine. Check `orderId`, `itemCount`, and `succeeded` to confirm the payload was recorded.

## 16. Reading recordings with the JFR consumer API

In addition to the `jfr` command, Java code can read events from a file using the `jdk.jfr.consumer` package.

Example:

~~~java
import java.io.IOException;
import java.nio.file.Path;

import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrReader {
    public static void main(String[] args) throws IOException {
        Path file = Path.of(args[0]);

        try (RecordingFile recording = new RecordingFile(file)) {
            while (recording.hasMoreEvents()) {
                RecordedEvent event = recording.readEvent();

                if (event.getEventType().getName()
                        .equals("com.acme.OrderProcessed")) {
                    System.out.println(
                            event.getString("orderId")
                            + " items="
                            + event.getInt("itemCount")
                            + " success="
                            + event.getBoolean("succeeded"));
                }
            }
        }
    }
}
~~~

Compile:

~~~bash
javac --release 17 --add-modules jdk.jfr -d out src/com/acme/JfrReader.java
~~~

Run:

~~~bash
java --add-modules jdk.jfr -cp out com.acme.JfrReader orders.jfr
~~~

Stdout:

~~~text
ORD-1 items=1 success=true
ORD-2 items=2 success=true
ORD-3 items=3 success=true
ORD-4 items=4 success=true
ORD-5 items=5 success=true
~~~

Event order in the example follows creation order. For large recordings, avoid loading the entire file into memory unnecessarily; streaming sequentially via `RecordingFile` or `EventStream` is more appropriate.

## 17. Event streaming at runtime

If you need to receive events as they are emitted, you can use `RecordingStream` from `jdk.jfr.consumer`.

Example:

~~~java
import jdk.jfr.Configuration;
import jdk.jfr.consumer.RecordingStream;

public final class LiveJfrEvents {
    public static void main(String[] args) throws Exception {
        try (RecordingStream stream =
                     new RecordingStream(Configuration.getConfiguration("default"))) {
            stream.onEvent("jdk.GarbageCollection",
                    event -> System.out.println(event));
            stream.onEvent("jdk.CPULoad",
                    event -> System.out.println(event));
            stream.start();
        }
    }
}
~~~

`RecordingStream` streams events from the current JVM. This example listens for GC and CPU Load events; the program keeps running until the stream is closed or the process exits.

Event streaming is suitable when an application needs to react to events or forward them to another system. Control processing rate, queues, backpressure, and data access permissions so a slow consumer does not increase memory usage.

## 18. Designing useful business events

Custom events are most valuable when they help link business processing time with JVM behavior.

Example for HTTP requests:

| Field | Meaning |
|---|---|
| route | Normalized route name |
| method | HTTP method |
| statusCode | HTTP status |
| duration | Processing duration |
| result | Success/failure |
| tenantTier | Tenant tier if needed for analysis |
| requestId | Sanitized correlation ID |

Example for SQL:

| Field | Meaning |
|---|---|
| operation | SELECT, INSERT, UPDATE |
| datasource | Datasource name |
| duration | Execution duration |
| rows | Number of rows returned or affected |
| success | Result |

Do not record raw SQL containing user data, credentials, or sensitive parameters. Usually only the operation name, datasource, duration, and row count are needed.

### Choosing fields with reasonable cardinality

Avoid creating event fields with millions of unique values unless necessary. A `requestId` can be helpful for tracing a single request, but it introduces high cardinality. Only include it in short recordings or when there is a clear correlation requirement.

For long-term monitoring, use route templates instead of full URLs and bucket values where appropriate.

## 19. Analyzing CPU, memory, GC, locks, and I/O

### CPU bottleneck

1. Open the **CPU/Code** view.
2. Inspect CPU load over time.
3. Inspect `ExecutionSample` and top methods.
4. Select a period of elevated CPU.
5. Open stack traces to identify the call path.
6. Correlate threads and workload in the same window.

High CPU can be caused by tight computation loops, serialization, regex, compression, or large data processing. A method appearing in many samples is a clue, not sole proof.

### Memory allocation

1. Inspect allocation rate and allocation samples.
2. Find classes allocating the most objects.
3. Inspect top allocation methods.
4. Compare heap usage over time.
5. If a memory leak is suspected, collect a heap dump and analyze retained heap/GC roots.

High allocation does not equal a leak. Short-lived objects reclaimed by GC can increase GC pressure while the live set remains stable.

### Garbage collection

1. Inspect GC events on the timeline.
2. Check pause durations.
3. Inspect heap before and after GC.
4. Correlate allocation rate and live set.
5. Check collector phases and when request latency spikes occur.

If slow requests coincide with GC pauses, determine whether the pause is the primary cause or merely co-occurring during a high-load period.

### Lock contention

1. Inspect `JavaMonitorEnter` and synchronization events.
2. Look for long durations or high wait counts.
3. Check the monitor/class and stack trace.
4. Identify the thread holding the lock.
5. Correlate with throughput and latency.

A single lock contention event is not enough to conclude a bottleneck. Look at total wait time, frequency, and the number of affected threads.

### I/O latency

1. Inspect `FileRead`/`FileWrite` and `SocketRead`/`SocketWrite`.
2. Filter for operations with large durations.
3. Check thread, endpoint, or file metadata if available.
4. Correlate with external service logs.
5. Check timeouts, retries, and pool saturation.

## 20. Choosing thresholds and sampling periods

Thresholds and periods directly affect data volume.

| Goal | How to choose |
|---|---|
| Find only significant lock waits | Set threshold based on the latency you want to observe |
| Monitor CPU continuously | Use a suitable sampling period; avoid sampling too densely |
| Investigate slow requests | Create custom duration events with thresholds aligned to SLA |
| Find allocations | Choose `profile` or appropriate allocation events |
| Monitor GC | Enable GC events and pause details |
| Continuous production recording | Start with `default.jfc` |

Example lowering the lock contention threshold to 5 ms:

~~~text
jdk.JavaMonitorEnter#threshold=5ms
~~~

Example sampling CPU Load every second:

~~~text
jdk.CPULoad#period=1 s
~~~

Lower thresholds can capture more events. Shorter periods increase sampling frequency. Do not choose extremely small values without measuring overhead and recording size.

## 21. Overhead and recording limits

JFR is designed to collect runtime data with low overhead, but overhead is not zero.

Contributing factors:

- Number of enabled events.
- Sampling frequency.
- Duration thresholds.
- Whether stack traces are recorded.
- Stack depth.
- Application event rate.
- Custom event payload size.
- Recording duration.
- `default` vs. `profile` configuration.

Some events or settings can add extra cost and, in certain cases, trigger GC to collect information. Test in staging or during a representative load window before expanding recording scope.

### Size limits

Use `maxage` and `maxsize` to bound data on disk. With continuous recordings, the buffer can discard the oldest data when limits are reached.

Do not let recording files accumulate indefinitely. Monitor disk usage, set retention policies, and delete files after investigations conclude.

### path-to-gc-roots

This option collects paths to GC roots to help track down memory leaks. Collecting it can take time and pause the application briefly.

Enable it only when a memory leak is suspected:

~~~bash
jcmd 2125 JFR.start name=leak-check settings=profile duration=5m path-to-gc-roots=true filename=leak-check.jfr
~~~

Do not enable `path-to-gc-roots` in routine production recordings.

## 22. Protecting data in JFR files

Recordings can contain a great deal of internal information:

- Thread, class, package, and method names.
- Stack traces and call paths.
- System properties and JVM configuration.
- File paths, socket metadata, and endpoints.
- Application-recorded event payloads.
- Business data if custom events are not designed carefully.

Protective measures:

1. Record only necessary events and fields.
2. Never include passwords, tokens, cookies, or raw request bodies in events.
3. Normalize routes, hostnames, and SQL metadata where appropriate.
4. Store files in directories with restricted read permissions.
5. Encrypt at rest or in transit per organizational policy.
6. Limit retention duration.
7. Review files before sharing outside the organization.
8. Scrub unnecessary events or threads before sharing.
9. Log who collected the recording, when, and for what purpose.
10. Delete temporary copies once the investigation is complete.

You can use `jfr scrub` to remove specific events, categories, or threads:

~~~bash
jfr scrub --exclude-events jdk.SocketRead,jdk.SocketWrite input.jfr sanitized.jfr
~~~

Scrubbing helps remove unwanted content but does not replace manual review. Verify the sanitized file before sharing, as sensitive data may still reside in other events or custom payloads.

## 23. Troubleshooting JFR

| Symptom | Possible cause | Resolution |
|---|---|---|
| `jcmd` does not see the JVM | Wrong PID, container namespace, or different user | Run `jcmd -l`/`ps` in the right environment and verify attach permissions |
| `JFR.start` is not supported | JVM lacks Flight Recorder or command is unavailable | Check JDK/JVM and `jcmd PID help` |
| Custom event missing from file | Event not enabled or recording was not running at commit | Enable the event in the recording and check with `JFR.check` |
| Event appears but fields are missing | Unsupported field type or `static` field | Use primitive/`String`/`Thread`/`Class` and instance fields |
| Short-duration events missing | Threshold is higher than actual duration | Check the event threshold and lower it cautiously |
| `.jfr` file is too large | Too many events, short period, or deep stack traces | Use `default`, raise thresholds, and bound `maxage`/`maxsize` |
| Recording file not created | Wrong `filename`, directory lacks write permission, or recording not stopped/dumped | Verify path, permissions, and `JFR.stop`/`JFR.dump` |
| `JFR.dump` does not stop the recording | Expected behavior | Use `JFR.stop` to end the recording |
| `JFR.stop` does not save a file | `filename` was not provided | Provide `filename` when you need to keep the data |
| JMC cannot open the file | Incomplete file, incompatible version, or corrupted data | Check `jfr summary` and use a matching JMC version |
| No allocation data visible | `default.jfc` does not enable allocation profiling | Use `profile` or custom settings |
| Recording lacks heap statistics | `default.jfc` does not collect heap statistics | Choose appropriate settings and measure overhead |
| Stack traces are too short | Stack depth or setting is limited | Check `stackTrace` and stack depth configuration |
| File contains sensitive data | Event payload or system metadata holds internal info | Scrub, restrict access permissions, and enforce retention |

## 24. Practical incident analysis workflow

1. Identify the symptom: high CPU, slow requests, GC pauses, lock contention, or slow I/O.
2. Identify the application's PID and JDK.
3. Check running recordings with `JFR.check`.
4. If a continuous recording exists, dump the incident time window.
5. If no recording is running, start an appropriate recording with `jcmd`.
6. Choose `default` for lightweight collection or `profile` for short-term investigation.
7. Bound `duration`, `maxage`, and `maxsize`.
8. Run `jfr summary` to verify the file and event counts.
9. Open the file in JMC or filter with `jfr print`/`view`.
10. Select the time window with abnormal latency.
11. Correlate CPU, GC, threads, locks, memory, and I/O.
12. Use stack traces to trace back to the code path.
13. Check logs/metrics/traces to confirm the hypothesis.
14. Only enable more events or lower thresholds if the current recording lacks sufficient data.
15. Document the conclusion, confidence level, and reproduction steps.
16. Secure and delete files according to retention policies once finished.

## 25. Key takeaways

- JFR is an event collection and profiling framework built into the JDK.
- Events have a timestamp, type, payload, and optionally a duration and stack trace.
- Four common types are duration, instant, sample, and custom events.
- JFR records event groups for CPU, threads, locks, GC, memory, class loading, exceptions, and I/O.
- `default.jfc` is suited for low-overhead continuous recording; `profile.jfc` collects more data with higher overhead.
- `default.jfc` does not collect heap statistics or allocation profiling in JDK 26's default configuration.
- Start recordings at startup with `StartFlightRecording` or at runtime with `jcmd JFR.start`.
- `JFR.check` inspects recordings, `JFR.dump` takes a snapshot while continuing, and `JFR.stop` ends the recording.
- `maxage` and `maxsize` help bound continuous recording data.
- Event settings include `enabled`, `threshold`, `period`, `stackTrace`, and `throttle`.
- Custom events are created by extending `jdk.jfr.Event` and declaring supported fields.
- `begin`/`end` measure duration; `commit` writes the event; `shouldCommit` avoids payload work when the event will not be recorded.
- `jfr summary`, `print`, `view`, `metadata`, `configure`, and `scrub` help inspect, filter, and manage recording files.
- JMC provides visualizations for timelines, CPU, memory, GC, threads, locks, and I/O.
- JFR does not replace logs, metrics, or distributed tracing; these data sources complement each other with incident context.
- `.jfr` files can contain stack traces, system metadata, and business data; protect them like production data.

## Official references

- [Diagnostic Tools — JDK 26, Flight Recorder](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [The jfr Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jfr.html)
- [The java Command — StartFlightRecording, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [jdk.jfr Package Summary — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Event API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Event.html)
- [Recording API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/Recording.html)
- [Flight Recorder API Programmer's Guide — JDK 26](https://docs.oracle.com/en/java/javase/26/jfapi/)
- [JFR Consumer API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.jfr/jdk/jfr/consumer/package-summary.html)
- [JDK Mission Control](https://www.oracle.com/java/technologies/jdk-mission-control.html)