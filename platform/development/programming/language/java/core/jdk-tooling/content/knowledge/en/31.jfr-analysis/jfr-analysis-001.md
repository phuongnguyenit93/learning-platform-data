# Reading and Analyzing JFR Files

**Java Flight Recorder (JFR)** records JVM runtime events into a binary file with the `.jfr` extension. A recording can contain information about CPU sampling, garbage collection, object allocation, threads, lock contention, I/O, class loading, JVM flags, and custom events defined by the application.

Reading a JFR file is the process of finding the right time range and event groups related to an issue, then correlating timestamps, durations, threads, stack traces, and data fields. The main tools are:

- **jfr command-line tool:** view summaries, filter events, read metadata, generate analysis tables, and export JSON/XML.
- **JDK Mission Control (JMC):** graphical interface for filtering by time, browsing events, viewing stack traces, flame charts, and automated analysis.
- **JFR Consumer API:** read events via Java code when automated reporting or processing is needed.

JFR files are binary data and should not be opened directly in a text editor. Start with a summary to understand the recording before filtering events.

## 1. What Does a JFR File Store?

A recording consists of chunks containing metadata and events. Metadata describes event names, labels, categories, fields, data types, and units. Events store the values recorded during the recording period.

An event can contain:

| Component | Meaning |
|---|---|
| Event type | Name of the event type, e.g., jdk.GarbageCollection |
| Start time | Timestamp when the event started |
| Duration | Duration of the event if it is a timed event |
| Event thread | Thread that created or committed the event |
| Stack trace | Call stack at the time the event was recorded |
| Fields | Event-specific values such as heap size, host, bytes, class, or request ID |

There are instant events, such as certain events that record when a thread starts. There are also duration events, such as file reads, socket reads, or monitor contention. When analyzing latency, duration and timestamp are often more important than raw event count.

A file can contain multiple chunks. JFR tools read all chunks within the same recording. The `Chunks` line in the summary indicates how many chunks the file contains.

JFR does not record every Java operation by default. Recording settings determine which events are enabled, sampling frequency, thresholds, and stack traces. Therefore, not seeing an event in the file may mean the event was not enabled, did not exceed the threshold, did not occur during the recording window, or was not sampled.

## 2. Verifying the File and Tool Version

The JFR command-line tool is located in the JDK's `bin` directory.

Windows PowerShell:

~~~powershell
Get-Command jfr
where.exe jfr
jfr version
~~~

Linux/macOS:

~~~bash
command -v jfr
jfr version
~~~

Verify file existence and size:

~~~powershell
Get-Item .\recording.jfr |
    Select-Object Name, Length, LastWriteTime
~~~

Linux/macOS:

~~~bash
ls -lh recording.jfr
file recording.jfr
~~~

When receiving a file from another machine, note the JDK that created the recording and the JDK being used to read it. Prefer tools of the same version or newer than the source version; if you encounter errors reading metadata or event types, check the version before concluding the file is corrupted.

Do not modify the original JFR file directly. Keep the original copy so you can re-run analyses or compare results.

## 3. First Step: jfr summary

Run:

~~~bash
jfr summary recording.jfr
~~~

The summary provides:

- Recording format version.
- Number of chunks.
- Start time.
- Total duration.
- List of event types.
- Event count per type.
- Size of recorded events in the file.

Abbreviated example output:

~~~text
Version: 2.1
Chunks: 1
Start: 2026-11-10 12:48:43 (UTC)
Duration: 1 s

Event Type                 Count  Size (bytes)
================================================
jdk.GarbageCollection          1            19
jdk.ThreadSleep                4            64
com.example.RequestEvent       4            84
jdk.ExecutionSample            0             0
~~~

This is an illustrative example; actual counts depend on the recording and settings.

### How to Read the Summary

**Start and Duration:** identify the time window covered by the recording. Correlate with the time users reported errors, deployments, CPU spikes, or GC pauses. Check timezones when comparing with application and system logs.

**Event Type:** shows which event types appeared. This serves as a map for choosing which events to inspect next.

**Count = 0:** the event type exists in metadata, but no events were recorded. The recording may not have enabled that event, the event may not have occurred, or it may not have exceeded the threshold.

**Large count:** does not automatically mean an error. A common event such as an allocation sample or thread event can have a high count under a normal workload. Inspect duration, stack traces, threads, and trends.

The summary is an orientation step and does not replace detailed analysis.

## 4. Viewing Event Lists and Metadata

Metadata describes the events a file can contain.

View metadata for the entire recording:

~~~bash
jfr metadata recording.jfr
~~~

Filter by event:

~~~bash
jfr metadata --events jdk.GarbageCollection recording.jfr
~~~

Or view metadata for a custom event:

~~~bash
jfr metadata --events com.example.RequestEvent recording.jfr
~~~

Metadata can tell you:

- Full name and label of the event.
- Category and description.
- Event fields.
- Data types and timestamp/timespan units.
- Whether stack trace or thread fields are available.

When no file is passed, `jfr metadata` uses metadata from the currently installed JDK. To understand a specific recording, pass that file itself to see the schema of events stored in the recording.

Built-in event names usually have the `jdk.` prefix. Custom events can use their own names based on the application package. Do not assume every JDK has the exact same event types; check the actual metadata and JDK version.

## 5. Printing Events with jfr print

`jfr print` displays event values in a human-readable format.

Print all events:

~~~bash
jfr print recording.jfr
~~~

For large files, avoid printing everything right away. Filter by event type:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary recording.jfr
~~~

Filter by category:

~~~bash
jfr print --categories "GC,JVM,Java*" recording.jfr
~~~

Print deeper stack traces:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 recording.jfr
~~~

By default, stack traces have a depth of 5 frames. Increase the depth when you need to see the caller chain; output will be longer.

### Event Example

Output of a custom event may look like this:

~~~text
com.example.RequestEvent {
  startTime = 12:48:43.100
  duration = 101 ms
  requestId = "REQ-1"
  durationMs = 7
  eventThread = "main"
  stackTrace = [
    com.example.JfrFileDemo.main(String[]) line: 36
  ]
}
~~~

How to read it:

- Event type is `com.example.RequestEvent`.
- The event started at the displayed timestamp.
- Duration is the time elapsed from `begin()` to `end()`.
- `requestId` and `durationMs` are application-defined fields.
- `eventThread` indicates the thread that committed the event.
- `stackTrace` indicates the code location where the event was created.

Timestamp and duration are two different pieces of information. An event with a long duration may have started before users observed a spike; compare timestamps with neighboring events.

### Exporting JSON or XML

JSON:

~~~bash
jfr print --json --events com.example.RequestEvent recording.jfr
~~~

XML:

~~~bash
jfr print --xml --events com.example.RequestEvent recording.jfr
~~~

JSON/XML is suitable when feeding events into another analysis tool or processing them with scripts. Filter event types before exporting to limit data size.

Text output is useful for manual reading. Do not rely on text formatting as a stable protocol when building long-term automation; use the Consumer API when structured event reading is needed.

## 6. Using jfr view for Predefined Reports

The JDK provides views that aggregate recording data into tables. List available views:

~~~bash
jfr help view
~~~

Or view all views available for a file:

~~~bash
jfr view all-views recording.jfr
~~~

View all event types in the recording:

~~~bash
jfr view all-events recording.jfr
~~~

Some useful views:

| View | Purpose |
|---|---|
| gc | Garbage collection overview |
| gc-pauses | GC pause analysis |
| heap-configuration | Heap configuration |
| hot-methods | Methods with prominent CPU activity |
| allocation-by-class | Allocation by class |
| allocation-by-site | Allocation by code site |
| allocation-by-thread | Allocation by thread |
| contention-by-site | Lock contention by site |
| contention-by-thread | Lock contention by thread |
| thread-count | Thread count over time |
| thread-cpu-load | CPU load by thread |
| socket-reads-by-host | Socket reads by host |
| file-reads-by-path | File reads by path |
| exception-by-type | Exceptions by type |
| events-by-name | Event count by name |

Examples:

~~~bash
jfr view gc recording.jfr
jfr view gc-pauses recording.jfr
jfr view hot-methods recording.jfr
jfr view allocation-by-class recording.jfr
jfr view contention-by-site recording.jfr
jfr view thread-count recording.jfr
~~~

Increase table width:

~~~bash
jfr view --width 160 hot-methods recording.jfr
~~~

Show the query that builds the view:

~~~bash
jfr view --verbose allocation-by-class recording.jfr
~~~

A view may report no events found if the recording lacks the required data. For example, the recording may be too short, settings may not enable the event, or the event only occurs under specific workload activity. Return to summary and metadata to confirm before drawing conclusions.

View names and table contents depend on the JDK. Run `jfr help view` on the exact JDK you are using.

## 7. Key Event Groups for Investigation

### CPU and Method Profiling

Events like `jdk.ExecutionSample` capture stack samples of executing threads at sampling points. They help identify methods that frequently appear in samples.

A sample is not a method invocation. If a method appears in many samples, it indicates that it accounts for a relatively large share of CPU time during the recording, not the exact number of calls.

Inspect:

~~~bash
jfr print --events jdk.ExecutionSample --stack-depth 32 recording.jfr
jfr view hot-methods recording.jfr
~~~

In JMC, view hot methods or the flame graph to find call paths with many samples.

### Garbage Collection and Heap

Common events:

- `jdk.GarbageCollection`.
- `jdk.GCHeapSummary`.
- `jdk.GCPhasePause`.
- `jdk.GCPhaseConcurrent`.
- Collector-specific events such as G1 or ZGC.

Inspect:

~~~bash
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary recording.jfr
jfr view gc recording.jfr
jfr view gc-pauses recording.jfr
~~~

Correlate GC start times, durations, collection types, heap before/after, and pause levels. A single long GC is not enough to conclude there is a problem; look at frequency, total pause time, allocation rate, and concurrent workload.

### Object Allocation and Memory

The `jdk.ObjectAllocationSample` event is a sampling event for allocation. It helps identify classes or stacks commonly associated with notable allocations, though it is not an exact record of every object allocation.

Inspect:

~~~bash
jfr print --events jdk.ObjectAllocationSample recording.jfr
jfr view allocation-by-class recording.jfr
jfr view allocation-by-site recording.jfr
jfr view allocation-by-thread recording.jfr
~~~

If a memory leak is suspected, track post-GC heap trends and inspect object retention using a heap dump or appropriate tools. JFR allocation samples help pinpoint where allocations occur; they do not replace heap dumps when you need to inspect the object graph and GC roots.

### Threads, Locks, and Parking

Some events:

- `jdk.ThreadStart` and `jdk.ThreadEnd`.
- `jdk.JavaMonitorEnter`.
- `jdk.JavaMonitorWait`.
- `jdk.ThreadPark`.
- `jdk.JavaMonitorInflate`.

Inspect:

~~~bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark recording.jfr
jfr view contention-by-site recording.jfr
jfr view contention-by-thread recording.jfr
~~~

Lock events often depend on thresholds. A brief monitor wait might not be recorded if it does not exceed the threshold. Read `ActiveSetting` or metadata/settings to see which configuration the recording used.

`ThreadPark` is often related to synchronizers such as `LockSupport`, `ReentrantLock`, or queues. Do not equate every thread park with an error; inspect thread state, stack trace, and wait duration.

### File and Network I/O

Events can include:

- `jdk.FileRead` and `jdk.FileWrite`.
- `jdk.SocketRead` and `jdk.SocketWrite`.
- `jdk.NetworkUtilization`.

Inspect:

~~~bash
jfr print --events jdk.FileRead,jdk.FileWrite recording.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite recording.jfr
jfr view socket-reads-by-host recording.jfr
jfr view file-reads-by-path recording.jfr
~~~

These events can help identify slow I/O operations, hosts with high response times, or frequently accessed file paths. Not every read/write appears; thresholds and event settings affect recorded data.

### Exceptions and Class Loading

Inspect exceptions:

~~~bash
jfr view exception-by-type recording.jfr
jfr view exception-by-message recording.jfr
jfr view exception-by-site recording.jfr
~~~

Inspect class loading:

~~~bash
jfr view class-loaders recording.jfr
jfr view longest-class-loading recording.jfr
~~~

Exception events can be configured to record only errors or all exceptions. If the exception count in JFR is lower than in application logs, check event settings and thresholds before comparing.

## 8. Reading Events Along a Timeline

JFR is useful because events have timestamps and can have durations. When analyzing an incident, choose a time window associated with the symptoms.

A practical workflow:

1. Note the timestamps of CPU spikes, latency, OOM, or GC pauses from monitoring/logs.
2. Check the file's Start and Duration to verify whether the recording covers that time.
3. Use `summary` to find event types that have data.
4. Select event groups relevant to the symptoms.
5. Filter events using `jfr print` or predefined views.
6. Correlate timestamps, durations, threads, and stack traces.
7. Compare events before, during, and after the incident.
8. Verify hypotheses using logs, metrics, or other recordings.

Example when request latency increases:

- If a GC pause coincides with the spike, check pause duration and heap usage.
- If monitor contention is present, find the thread and code site holding the lock.
- If socket read durations are high, check the host and external service.
- If CPU samples cluster on a call path, inspect the methods and algorithms.
- If allocation samples cluster on a class, check object churn and caches.

Concurrent events do not by themselves prove causality. A GC pause may coincide with slow requests, while the root cause could be an allocation spike or a workload shift. Check the sequence of events and supporting evidence.

## 9. Reading Files with JDK Mission Control

JDK Mission Control (JMC) is a graphical tool for analyzing JFR recordings. JMC is distributed separately in many JDK environments; if it is not installed, install an appropriate build from the OpenJDK Mission Control project.

Workflow:

1. Open JMC.
2. Select File > Open File.
3. Choose the `.jfr` recording.
4. Wait for JMC to read metadata and build the analysis pages.
5. Start with Overview and Automated Analysis.
6. Open Event Browser to filter events by type, time range, thread, or field.
7. Select an event to view its fields and stack trace.
8. Use specialized views such as Threads, Memory, GC, Method Profiling, or I/O as appropriate.

### Overview and Automated Analysis

Overview helps you grasp the recording time range, JVM, OS, CPU, memory, and key highlights. Automated Analysis can surface warnings or suggestions based on recorded events.

This is a starting point for forming hypotheses. Do not treat automated warnings as final conclusions; open the underlying events and verify using timestamps, durations, and stack traces.

### Event Browser

Event Browser is suitable when detailed data filtering is needed:

- Select event type.
- Select time range.
- Filter by thread or field.
- Sort by timestamp/duration.
- Open an event to view fields and stack trace.

If events do not appear, check active filters, time range, and recording settings.

### Flame Graph and Method Profiling

The flame graph aggregates stack samples to show which call paths account for the most samples. The horizontal axis represents the proportion of samples; the vertical axis represents the call stack.

A wide frame indicates that the frame appears in a relatively large number of samples. Do not interpret width as an exact method call count.

## 10. Capturing Recordings with jcmd

If an application is already running and allows Attach, you can start a recording remotely using `jcmd`.

List JVMs:

~~~bash
jcmd -l
~~~

View supported commands:

~~~bash
jcmd <pid> help JFR.start
jcmd <pid> help JFR.dump
jcmd <pid> help JFR.stop
~~~

Start a recording:

~~~bash
jcmd <pid> JFR.start name=Incident settings=profile filename=incident.jfr duration=60s
~~~

Check recordings:

~~~bash
jcmd <pid> JFR.check
~~~

Dump a snapshot while the recording is still running:

~~~bash
jcmd <pid> JFR.dump name=Incident filename=incident-snapshot.jfr
~~~

Stop a recording:

~~~bash
jcmd <pid> JFR.stop name=Incident
~~~

In JDK 24, `jcmd` notes that `profile.jfc` collects more data than `default.jfc` at higher overhead. `default.jfc` has lower overhead and is better suited for continuous recording. Use `profile` for short windows when more detail is needed, while evaluating its impact on the workload.

To record right from JVM startup:

~~~bash
java -XX:StartFlightRecording=filename=app.jfr,duration=60s,settings=profile -jar app.jar
~~~

These commands require appropriate attach permissions. If the JVM disables Attach or the process runs in a different namespace, `jcmd` may fail to connect. Verify the correct PID, user, and runtime configuration.

## 11. Creating JFR Files with the Java Flight Recorder API

Applications can create recordings programmatically using the API in the `jdk.jfr` module. Custom events are useful for recording business context such as request ID, order ID, batch name, or processing time.

Example event:

~~~java
@Name("com.example.RequestEvent")
@Label("Request event")
@Category({"Demo", "Application"})
public static class RequestEvent extends Event {
    @Label("Request ID")
    public String requestId;

    @Label("Duration in milliseconds")
    public int durationMs;
}
~~~

Enable the event in a `Recording`:

~~~java
recording.enable(RequestEvent.class)
         .withThreshold(Duration.ZERO)
         .withStackTrace();
~~~

Basic steps:

1. Create a `Recording` with an appropriate configuration.
2. Enable event types and set thresholds.
3. Start the recording.
4. Create the event, call `begin()`, set fields, call `end()`, and `commit()`.
5. Stop the recording.
6. Dump to a `.jfr` file.

Do not put sensitive data such as passwords, tokens, or full request payloads into custom events. Record only fields needed for diagnostics.

## 12. Complete Java 17+ Example: Creating and Reading a JFR File

The example consists of two programs. `JfrFileDemo` creates a file with four custom events. `JfrReader` opens that file using `RecordingFile`, filters events by name, and computes the average duration.

Structure:

~~~text
jfr-file-demo/
└── src/
    └── com/
        └── example/
            ├── JfrFileDemo.java
            └── JfrReader.java
~~~

### JfrFileDemo.java

~~~java
package com.example;

import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Configuration;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrFileDemo {
    @Name("com.example.RequestEvent")
    @Label("Request event")
    @Category({"Demo", "Application"})
    public static final class RequestEvent extends Event {
        @Label("Request ID")
        public String requestId;

        @Label("Duration in milliseconds")
        public int durationMs;
    }

    public static void main(String[] args) throws Exception {
        Path destination = Path.of(args[0]).toAbsolutePath();

        try (Recording recording =
                     new Recording(Configuration.getConfiguration("profile"))) {
            recording.setName("JFR file analysis demo");
            recording.setToDisk(true);
            recording.enable(RequestEvent.class)
                     .withThreshold(Duration.ZERO)
                     .withStackTrace();

            recording.start();

            for (int i = 1; i <= 4; i++) {
                RequestEvent event = new RequestEvent();
                event.requestId = "REQ-" + i;
                event.durationMs = i * 7;

                event.begin();
                Thread.sleep(100);
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(destination);

            System.out.println("Recording written: " + destination.getFileName());
            System.out.println("Custom events committed: 4");
        }
    }
}
~~~

### JfrReader.java

~~~java
package com.example;

import java.nio.file.Path;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrReader {
    private JfrReader() {
    }

    public static void main(String[] args) throws Exception {
        long count = 0;
        long totalDuration = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent event = file.readEvent();

                if (event.getEventType().getName()
                        .equals("com.example.RequestEvent")) {
                    String requestId = event.getString("requestId");
                    int durationMs = event.getInt("durationMs");

                    System.out.printf(
                            "%s duration=%dms%n", requestId, durationMs);

                    count++;
                    totalDuration += durationMs;
                }
            }
        }

        System.out.println("Matched events=" + count);
        System.out.println(
                "Average duration=" +
                (count == 0 ? 0 : totalDuration / count) + "ms");
    }
}
~~~

### Compiling

From the `jfr-file-demo` root directory:

~~~bash
mkdir -p build/classes

javac --release 17 \
    -d build/classes \
    src/com/example/JfrFileDemo.java \
    src/com/example/JfrReader.java
~~~

### Creating the Recording

~~~bash
java -cp build/classes \
    com.example.JfrFileDemo sample.jfr
~~~

Output:

~~~text
Recording written: sample.jfr
Custom events committed: 4
~~~

### Reading the File with the Java API

~~~bash
java -cp build/classes \
    com.example.JfrReader sample.jfr
~~~

Exact output:

~~~text
REQ-1 duration=7ms
REQ-2 duration=14ms
REQ-3 duration=21ms
REQ-4 duration=28ms
Matched events=4
Average duration=17ms
~~~

### Inspecting the Same File with the CLI

~~~bash
jfr summary sample.jfr
jfr metadata --events com.example.RequestEvent sample.jfr
jfr print --events com.example.RequestEvent sample.jfr
jfr view events-by-name sample.jfr
~~~

This example was compiled with `javac --release 17` and run on JDK 24.0.2. Timestamps, file sizes, and system event counts may vary by machine; the four custom events and the `JfrReader` output are determined by the example data.

## 13. Reading Large Files with RecordingFile

The Consumer API resides in the `jdk.jfr` module, package `jdk.jfr.consumer`.

Key classes:

| API | Role |
|---|---|
| RecordingFile | Opens a `.jfr` file and reads events sequentially |
| RecordedEvent | Represents a recorded event |
| RecordedEvent.getEventType() | Retrieves event metadata/type |
| RecordedEvent.getStartTime() | Retrieves start timestamp |
| RecordedEvent.getDuration() | Retrieves duration |
| RecordedEvent.getThread() | Retrieves the associated thread if present |
| RecordedEvent.getStackTrace() | Retrieves the stack trace if the event has one |
| RecordedEvent.getValue(name) | Retrieves a field by name |

For large files, prefer sequential reading with `hasMoreEvents()` and `readEvent()` as shown in the example. Avoid calling `readAllEvents()` indiscriminately, as it loads all events into memory and can cause heap pressure.

When processing each event:

- Filter event types early to reduce work.
- Read only the fields you need.
- Aggregate metrics instead of keeping all `RecordedEvent` instances in a collection.
- Close `RecordingFile` using try-with-resources.
- Handle `IOException` and schema differences when reading files from other JDKs.
- Check whether a field exists in event metadata before assuming all recordings share the same schema.

If you need to export data, write CSV/JSON under an application-controlled schema and preserve timestamps, timezones, event types, and units.

## 14. Filtering and Scrubbing Recordings Before Sharing

JFR files can contain sensitive information: system properties, environment variables, command lines, process names, file paths, hosts/network addresses, internal classes, stack traces, and custom application fields.

Do not send raw `.jfr` files to public tickets or unapproved services.

`jfr scrub` creates a new recording by including or excluding event types, categories, or threads.

Example removing environment variable and initial system property events:

~~~bash
jfr scrub --exclude-events InitialEnvironmentVariable,InitialSystemProperty recording.jfr recording-scrubbed.jfr
~~~

Keep only socket events:

~~~bash
jfr scrub --include-events "jdk.Socket*" recording.jfr socket-only.jfr
~~~

Keep only events from threads whose names contain `main`:

~~~bash
jfr scrub --include-threads main recording.jfr main-thread-only.jfr
~~~

Filter by category:

~~~bash
jfr scrub --exclude-categories "JVM,OS" recording.jfr filtered.jfr
~~~

After scrubbing, inspect the new file:

~~~bash
jfr summary recording-scrubbed.jfr
jfr print recording-scrubbed.jfr
~~~

**Scrub is not a field-level secret-redaction tool.** It filters by event type, category, or thread; retained events can still contain tokens, URLs, SQL, request data, or other sensitive details. Inspect the actual metadata, events, and fields before sharing. Keep the original file in a secure location.

## 15. Handling Multi-Chunk Recordings or Large Files

The summary shows the number of chunks in the file. For large files, use JMC or filter events to avoid dumping the entire recording as text.

Some file-management commands:

~~~bash
jfr disassemble recording.jfr --output chunks/
~~~

`disassemble` splits a recording into smaller files/chunks for individual processing.

~~~bash
jfr assemble repository/ recording-assembled.jfr
~~~

`assemble` creates a recording from remaining chunks in a disk repository. This command is useful when recovering a recording from a repository after a crash or working with chunks that have not yet been merged into a complete file.

Check syntax on the JDK in use:

~~~bash
jfr help disassemble
jfr help assemble
~~~

Do not manually merge files by concatenating bytes or renaming extensions. Use JFR tools to preserve chunk structure and metadata.

## 16. Common Errors When Reading JFR Files

### File Not Found

Check the working directory, relative/absolute paths, and file read permissions. If the recording is inside a container, ensure the file has been copied to a location accessible by the tools.

### Invalid or Truncated File

The recording may not have been completely dumped, may have been partially copied, or the process may have terminated while writing. Check the file size, source, and try reading with a compatible JDK. If the recording is still running, use `JFR.dump` to create a complete snapshot instead of copying the active file directly.

### Summary Missing Expected Events

Check recording duration, settings, event thresholds, and workload timing. The event may not have been enabled or may not have occurred during the recording window.

### jfr print Output Too Long

Filter by event type or category. Reduce stack depth if the output is large. For large files, use `jfr view` or JMC.

### jfr view Reports No Events Found

The view may require events not present in the recording. Check `summary` and `metadata`; if the event was not enabled, create a new recording with appropriate settings.

### Missing Stack Traces

The event may not have stack traces enabled, or that event type may not provide stacks. Check recording settings and metadata. When needed, configure the event with stack traces in the next recording.

### Unreadable JSON/XML

Ensure output was not truncated by the terminal or pipeline. Write directly to a file, check the `jfr` exit code, and use a JSON/XML parser to validate structure.

### File Too Large

Reduce recording duration, use `default` settings when appropriate, limit `maxage`/`maxsize`, filter events when exporting, or use JMC to browse data. Do not reduce event settings to the point of losing data needed for investigation.

## 17. JFR File Analysis Checklist

- [ ] Verify file source, JDK version, and creation time.
- [ ] Keep the original copy and work on a copy when scrubbing.
- [ ] Run `jfr summary` to check chunks, start time, duration, and event counts.
- [ ] Confirm the recording covers the incident time window.
- [ ] Check metadata and event settings.
- [ ] Select event types relevant to the symptoms.
- [ ] Use `jfr print` or `jfr view` to filter data.
- [ ] Read timestamps, durations, threads, stack traces, and fields.
- [ ] Correlate CPU, GC, allocation, locks, and I/O along the timeline.
- [ ] Use JMC when visual filtering or flame graphs are needed.
- [ ] Use `RecordingFile` for automated processing and large files.
- [ ] Do not confuse sampling events with exact invocation counts.
- [ ] Do not infer causality solely from concurrent events.
- [ ] Review for sensitive data before sharing the file.
- [ ] Record the commands, versions, filters, and hypotheses tested.

## 18. Commands to Remember

~~~bash
# Check JFR tool version
jfr version

# Summary: start, duration, chunks, event counts
jfr summary recording.jfr

# Inspect event schema and fields
jfr metadata recording.jfr

# Print selected event types
jfr print --events jdk.GarbageCollection,jdk.GCHeapSummary recording.jfr

# Print deeper stack traces
jfr print --events jdk.ExecutionSample --stack-depth 32 recording.jfr

# Export JSON or XML
jfr print --json recording.jfr
jfr print --xml recording.jfr

# Predefined analysis views
jfr view gc recording.jfr
jfr view hot-methods recording.jfr
jfr view allocation-by-class recording.jfr
jfr view contention-by-site recording.jfr

# Filter event types into a new recording
jfr scrub --exclude-events InitialEnvironmentVariable,InitialSystemProperty recording.jfr filtered.jfr

# Live recording control
jcmd <pid> JFR.start name=Incident settings=profile filename=incident.jfr duration=60s
jcmd <pid> JFR.check
jcmd <pid> JFR.dump name=Incident filename=incident-snapshot.jfr
jcmd <pid> JFR.stop name=Incident
~~~

Effective JFR file analysis starts with a summary, then selecting event types and views relevant to the symptoms. Use timestamps, durations, threads, and stack traces to connect CPU, GC, allocation, locks, and I/O along the same timeline. JMC helps with visual exploration; the `RecordingFile` API is suited for structured processing. Always check recording settings and protect files because JFR data can contain internal application details.

## References

- [The jfr Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- [The jcmd Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- [JDK Flight Recorder API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/module-summary.html)
- [RecordingFile API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html)
- [RecordedEvent API — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html)
- [OpenJDK Mission Control](https://github.com/openjdk/jmc)
