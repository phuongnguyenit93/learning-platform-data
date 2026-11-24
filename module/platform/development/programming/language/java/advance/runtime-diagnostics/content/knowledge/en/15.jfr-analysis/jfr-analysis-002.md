# 15.2 Reading jfr summary and metadata before choosing event groups to inspect

## Objectives

When you receive a **Java Flight Recorder (JFR)** file, the first step is to understand **what the file recorded, over what time interval, and what structure each event type has**. You should not immediately print the entire file or draw conclusions from an event whose name happens to sound like the issue you are investigating.

After this lesson, you will be able to:

1. Use **jfr summary** to inspect the file, time span, chunk count, **Count**, and **Size** by event type.
2. Use **jfr metadata** to find exact event names, categories, descriptions, and schemas for each event before writing queries.
3. Distinguish **defined event types** from **events that actually appear** in the recording.
4. Select event groups matching questions about CPU, GC, allocation, lock contention, thread parking, I/O, class loading, and runtime.
5. Filter events with **jfr print --events** or **--categories**, understanding the limitations of sampling, thresholds, event settings, and stack traces.
6. Create a small JFR recording yourself with Java 17+ and inspect it step by step using the tools bundled with the JDK.

**Scope:** commands and examples prioritize **HotSpot/OpenJDK 21**; Java 17 also includes the core `summary`, `metadata`, and `print` commands. Event sets, categories, data fields, and some subcommands may vary across JDK versions and vendors.

## 1. What is a JFR file and why take inventory first?

JFR collects **events** emitted by the JVM or the application: for example, GC start/end, execution samples, memory allocations, thread parks, file/socket access, and class loading activity. Data is typically stored in a binary file with the **.jfr** extension, along with type information for events and timestamps.

Distinguish three levels:

- **Recording:** an observation window with start/end times, chunks, and the collected event configuration.
- **Event type:** a kind of event, such as **jdk.GarbageCollection** or **jdk.ExecutionSample**, with a name, category, label, description, and field list.
- **Event instance:** a single occurrence written to the file, with `startTime`, data fields, and potentially `duration`, `thread`, or `stackTrace` depending on the type and settings.

A file containing hundreds of thousands of **jdk.ExecutionSample** events does not mean the CPU executed "hundreds of thousands of times," and an event type described in metadata does not mean the file contains instances of it.

**The right reading order:**

~~~text
Have a .jfr file
    |
    v
jfr summary: does the file have the right time span, event types, and data density?
    |
    v
jfr metadata: what are the names, categories, and fields of the events worth viewing?
    |
    v
Select event types that are relevant and actually have data
    |
    v
jfr print --events / --categories: print only the target set
    |
    v
Analyze duration, stackTrace, thread, object/GC IDs, correlation
~~~

If `summary` shows the file does not cover the incident window or lacks the required event groups, adjust the recording settings and re-capture rather than forcing conclusions from incomplete data.

## 2. Prerequisites before running

You need a **full JDK** with the **jfr** tool, not just a stripped-down JRE. Verify the active JDK and CLI availability:

~~~bash
java -version
jfr --version
jfr help
jfr help summary
jfr help metadata
jfr help print
~~~

Depending on the OS, open a terminal with **JDK/bin** on your PATH. A newer JDK can often read files created by older JDKs; the reverse is not always bidirectional because metadata, format, and event types evolve. For difficult investigations, record the **JVM vendor/version that wrote the file** and the **jfr CLI version** used to read it.

Once you have a file, let's use **recording.jfr** as an example (replace with the actual path). You do not need to connect to the original JVM to run **jfr summary/metadata/print** on a saved file.

~~~bash
jfr summary recording.jfr
jfr metadata recording.jfr
~~~

If **recording.jfr does not exist, is truncated, or is corrupt**, the commands may report a read error. Resolve the source file first. Do not treat "the command printed no events" as an application signal when the recording itself is invalid.

### Minimal file recording when you don't have a .jfr yet

You can start a recording for a Java application at launch:

~~~bash
java -XX:StartFlightRecording=filename=recording.jfr,duration=60s,settings=profile -jar app.jar
~~~

This command uses **HotSpot** with JFR and requires a valid output file path. After the configured duration, the JVM writes the recording; the application can continue running. For an already-running process, you can use **jcmd PID JFR.start** and **JFR.dump** depending on attach capability and permissions, though this lesson focuses on *reading an exported recording*, not managing live recordings in depth.

**Do not assume `profile` contains every event:** `settings=default/profile`, modified thresholds, sampling rates, `stackTrace`, and the JDK version determine what gets recorded. A file can be packed with type A events while recording zero instances of type B.

## 3. jfr summary: reading the overall map before inspecting details

Command:

~~~bash
jfr summary recording.jfr
~~~

Depending on the JDK version, the output usually shows **version/file**, **chunks**, **start/duration**, and a table of event types with **Count** and **Size**. Here is a shortened illustration with **completely hypothetical numbers**:

~~~text
Version: 2.x
Chunks: 1
Start: 2026-10-29 09:00:00 (UTC)
Duration: 60 s

Event Type                         Count       Size (bytes)
jdk.CPULoad                           60              2400
jdk.ExecutionSample                  800             50000
jdk.GarbageCollection                  8              1600
jdk.GCHeapSummary                     16              2200
jdk.JavaMonitorEnter                   0                 0
jdk.SocketRead                         0                 0
...
~~~

Presentation, sort order, timestamps, and event counts can vary. **Do not treat this illustrative block as guaranteed stdout from a real file.**

### 3.1. Start, Duration, Chunks: checking whether the capture window fits

- **Start**: start timestamp of the recording/chunks; check timezone and when the symptom occurred.
- **Duration**: length of time covered by the file, not the duration of individual events.
- **Chunks**: JFR stores data in chunks containing metadata and event records; a file can span multiple chunks.
- **Version/format**: helps confirm readability with the tool you are using.

Suppose a latency error occurred at **15:35**, but the file recorded **15:10–15:15**: even if the file is valid, it **does not represent** the error window. Or the file spans 10 minutes while the issue only appeared in the final 5 seconds: total Count/Size across the file does not tell you the time distribution; you must inspect `startTime` on filtered events.

### 3.2. What is Count?

**Count** is the number of **recorded event instances** per type in the file. It **does not necessarily equal** the actual number of operations in the application:

- **Periodic events**, e.g., CPU load: Count depends on the emission period and recording duration.
- **Sampling events**, e.g., execution/allocation samples: Count reflects **collected samples**, not total CPU instructions, total allocated objects, or method call counts.
- **Threshold events**, e.g., some I/O/lock events: operations below the threshold may **not be recorded**.
- **Disabled events**: the type may not be collected under the current configuration.
- **Events dropped/truncated** or a filtered/scrubbed recording: observed data may be incomplete.

Therefore, **Count=0 does not prove the phenomenon did not happen**. It only says the file contains no instances of that type as read by `summary`. Before concluding, check **event settings, coverage, duration, thresholds, and file integrity**.

### 3.3. What is Size?

**Size** in the summary table is the amount of **serialized space used by event records** per event type (exact calculation depends on the tool version). It is not:

- RAM used by Java objects of that type.
- CPU time spent executing the event.
- Heap bytes leaked.
- File or socket bytes processed by I/O events.

An event type with few instances but large stack traces or metadata payloads can have a large **Size**. An event type with a high Count and small instances can also contribute substantially to recording size. **Size is useful for seeing which data types dominate the file and the recording footprint**, not as an application health metric.

### 3.4. Which questions can summary answer?

Summary quickly answers: "Which event types are in the file, how many instances, how long is the recording, and which types take up most of the record bytes?" Summary **does not reveal** stack traces, specific threads, GC causes, allocation origins, individual blocking durations, or multi-event correlations. Those belong to later steps.

For example, seeing **jdk.GarbageCollection: 8** only tells you 8 GC events were recorded. It does not prove GC caused high latency. You need **startTime, duration, GC type, heap before/after, and latency timestamps**.

## 4. jfr metadata: reading the schema before writing filters

Basic command:

~~~bash
jfr metadata recording.jfr
~~~

Unlike `summary`, **metadata** describes *type definitions*: event names, categories, labels, descriptions, fields, and annotations related to semantics/units. It does not list all event instances and does not give instance counts for a type.

With JDK 21, you can filter which metadata to view:

~~~bash
jfr metadata --events jdk.GarbageCollection recording.jfr
jfr metadata --events jdk.ExecutionSample recording.jfr
jfr metadata --events jdk.JavaMonitorEnter,jdk.ThreadPark recording.jfr
~~~

You can filter by category if the file's categories match:

~~~bash
jfr metadata --categories "Garbage Collection" recording.jfr
~~~

**Exact category names differ from event names** and may be path-like/hierarchical labels depending on the event. If nothing is returned, inspect unfiltered metadata or run **jfr help metadata** to confirm the syntax and actual category names.

### 4.1. How to read an event definition

An event type may include:

| Metadata component | Meaning | How to use |
| --- | --- | --- |
| **Name** | Machine-readable name, usually **jdk.SomeEvent** or custom like **demo.WorkPhase** | Use with **--events** |
| **Label/Description** | Human-readable label and description | Pick events matching the phenomenon under investigation |
| **Category** | One or more grouping levels, e.g., GC, Profiling, I/O | Select an entire group during exploration |
| **startTime / duration** | Timestamp and/or length of activity when the event type has those fields | Filter by time range, find slow operations |
| **thread / eventThread** | Thread info if recorded by the event type/configuration | Distinguish the thread where the event occurred from a sampled thread |
| **stackTrace** | Saved frames when supported and enabled | Trace code paths; do not assume it is always present |
| **Specific fields** | GC id, class, monitor, allocation size, address, bytesRead... depending on the event | Decide whether the data is sufficient to answer the question |
| **Unit/content annotations** | Time span, bytes, percentage, data amount... | Avoid unit or conversion mistakes |

**Field names in this table are general concepts**, not a fixed schema for all events. For example, a CPU sample event and a GC event do not necessarily share the same fields; an event might have no meaningful duration. Read the actual schema of the **type in the specific recording** before extracting values or writing a parser.

### 4.2. metadata with a file vs. metadata without a file

~~~bash
# Type definitions read from the recording:
jfr metadata recording.jfr

# When omitting the file argument, uses metadata from the JDK running the jfr tool:
jfr metadata
~~~

The second form is handy for looking up event names **supported by the current JDK**, but it does not prove an older file contains that type, and types/fields may have changed between the recording JDK and the reading JDK. For a specific incident, prefer **jfr metadata recording.jfr**.

**Being defined in metadata does not mean Count > 0.** A type can appear in metadata with zero event instances. Always read **summary** to verify data actually exists in the file, then use **metadata** to understand how to interpret it.

### 4.3. Metadata is not a copy of all recording settings

Metadata shows *event types and their potential fields*, sometimes with setting definitions/annotations. It **does not replace verifying the effective event settings** of the recording: whether an event was enabled, what threshold or period was used, whether `stackTrace` was saved, and the full configuration during capture. To verify actual settings, inspect the recording configuration (`.jfc` / JFR APIs / JFR configuration metadata if recorded and parseable) along with capture notes.

**Specifically:** seeing a **stackTrace** field in the schema **does not guarantee** every instance has a full stack trace. Stacks may be disabled, truncated, missing frames due to sampling, or contain frames unrelated to what you expected to trace.

## 5. Choosing events by question: from summary to shortlist

An effective approach is to start from the **symptom**, cross-check against types that actually have non-zero Counts in the file, and then inspect metadata.

| Symptom/question | Events to look for first | Why inspect them | Caveats |
| --- | --- | --- | --- |
| High CPU, processing hotspot | **jdk.ExecutionSample**, **jdk.CPULoad**, possibly native/CPU samples depending on JDK | Stack samples and CPU trends | Sample count is not CPU time or method call count |
| Pauses/latency around GC | **jdk.GarbageCollection**, **jdk.GCPhasePause**, **jdk.GCHeapSummary**, collector-specific events | Timeline, duration, heap, and GC phases | Events vary by GC collector and configuration |
| Creating many temporary objects | **jdk.ObjectAllocationSample**, and other allocation events if enabled | Allocating classes/stacks that may cause pressure | Sampling/weight; do not infer live heap or leaks directly |
| Contention entering synchronized | **jdk.JavaMonitorEnter** | Monitor contention exceeding threshold | Low Count may be due to threshold |
| Threads parked or waiting | **jdk.ThreadPark** | Duration, thread, and stack if present | Parking is not automatically a bug |
| Slow socket reads | **jdk.SocketRead**, **jdk.SocketWrite** | Duration and I/O context | Events below threshold may not be recorded |
| File I/O | **jdk.FileRead**, **jdk.FileWrite** | Operation, bytes, duration | Count is not syscall count; small I/O may be absent |
| Abnormal class loading | **jdk.ClassLoad**, **jdk.ClassLoadingStatistics**, or actual types in file | Class loading/metaspace fluctuations | Types/fields depend on JDK and profile |
| Thread churn | **jdk.ThreadStart**, **jdk.ThreadEnd**, **jdk.ThreadCPULoad** if present | Thread creation/termination and activity | Not equivalent across all virtual threads on every JDK |
| Custom business timing | Application-defined event names, e.g., **demo.WorkPhase** | Measure business operations, transaction spans | Names/fields defined by the event author |

These event examples **are only starting points**. Inspect the actual metadata in the file; when an event is absent or Count=0, re-evaluate how data was collected. GC, CPU, and I/O groups usually must be **correlated by timestamp** rather than picking one event and inferring causation.

**Example:** production p99 latency spikes, but `summary` only shows `CPULoad` and `ExecutionSample` with no `FileRead`/`SocketRead` events. You **can analyze CPU**, but you cannot yet conclude "I/O did not cause the latency"; you need a recording with appropriate I/O data.

## 6. When to filter by event vs. by category

### 6.1. Choose event name when the target is known

~~~bash
jfr print --events jdk.GarbageCollection recording.jfr
jfr print --events jdk.ExecutionSample recording.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.ThreadPark recording.jfr
~~~

**--events** accepts type names (simple or fully qualified per tool syntax, with filter support). For repeatable workflows, prefer **fully qualified names from metadata**, especially when custom events share simple names.

### 6.2. Choose category to explore related events on one topic

~~~bash
jfr print --categories GC recording.jfr
~~~

This command uses a category filter. Cross-check actual categories in **jfr metadata** instead of assuming every GC-related event is under a single category named "GC" or grouped identically across JDKs.

If you combine **--categories** and **--events** in **jfr print**, according to JDK 21 documentation, the result is the **union** of events matching each filter, not the intersection:

~~~bash
jfr print --categories GC --events jdk.CPULoad recording.jfr
~~~

The command above prints both events in category GC **and** `CPULoad`; it **does not mean** "only `CPULoad` belonging to GC." This matters when you want a narrow filter.

### 6.3. Choosing stack depth and output format

~~~bash
# View more frames if the recording saved stacks:
jfr print --events jdk.ExecutionSample --stack-depth 20 recording.jfr

# Choose structured format for script processing:
jfr print --json --events jdk.GarbageCollection recording.jfr
~~~

**--stack-depth** only changes how many frames the CLI **displays**; it does not add stacks that were never recorded in the file. **--json** aids automated parsing, though JSON structure depends on schema and version; inspect real output before writing a parser. Avoid printing an entire large recording: output can reach millions of lines and expose sensitive data.

### 6.4. When jfr view is available

JDK 21 includes **jfr view** for aggregated views. You can check supported views:

~~~bash
jfr help view
jfr view types recording.jfr
~~~

This step comes **after** `summary`/`metadata` when you want convenient summary tables; **you do not need `jfr view` to understand file structure**. Older JDK versions have fewer subcommands, so if `view` is unavailable, continue using `summary`, `metadata`, and `print`.

## 7. Java 17+ hands-on: create a JFR file with an easily inspectable event schema

The goal of this example is to **guarantee custom events emitted by your own code**, then match `summary`, `metadata`, and `print`. The example needs no web server or production data.

Create **JfrInventoryDemo.java**:

~~~java
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.Recording;

public final class JfrInventoryDemo {
    @Name("demo.WorkPhase")
    @Label("Work Phase")
    @Category({"Demo", "JFR"})
    public static class WorkPhase extends Event {
        @Label("Phase Name")
        public String phase;

        @Label("Processed Items")
        public long items;
    }

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-inventory-demo.jfr");

        try (Recording recording = new Recording()) {
            recording.enable(WorkPhase.class)
                    .withThreshold(Duration.ZERO)
                    .withStackTrace();
            recording.start();

            for (int i = 1; i <= 3; i++) {
                WorkPhase event = new WorkPhase();
                event.phase = "phase-" + i;
                event.items = i * 100L;
                event.begin();
                event.end();
                event.commit();
            }

            recording.stop();
            recording.dump(file);
        }

        System.out.println("Created " + file);
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --add-modules jdk.jfr JfrInventoryDemo.java
java --add-modules jdk.jfr JfrInventoryDemo
~~~

When it runs successfully in a writable directory, the **exact stdout printed by the program itself** is:

~~~text
Created jfr-inventory-demo.jfr
~~~

The file **jfr-inventory-demo.jfr** is created in the working directory. The **demo.WorkPhase** event is committed three times in the program; assuming no data-collection error, `summary` will show this type with **Count=3**. Auxiliary JVM events, timestamps, chunk count, and file size are not fixed, so full hypothetical stdout is not shown.

### 7.1. Reading summary of the newly created file

~~~bash
jfr summary jfr-inventory-demo.jfr
~~~

Look for the **demo.WorkPhase** row in the **Event Type / Count / Size** table. Many other event types emitted by the runtime/JFR may appear; that is not an error. Match **Count** against the number of events committed in code. **Size** is record bytes, not the sum **items=600**; `items` is business data inside the event with its own unit.

### 7.2. Reading metadata of the custom event

~~~bash
jfr metadata --events demo.WorkPhase jfr-inventory-demo.jfr
~~~

Look for the name **demo.WorkPhase**, label **Work Phase**, category **Demo, JFR**, and fields **phase** (String) and **items** (long). The runtime may add standard fields related to `startTime`/`duration`/`eventThread`/`stackTrace` to the event representation. Metadata descriptions and formatting may vary slightly across JDKs.

This clearly illustrates: metadata tells you **`items` is `long`**, but **does not tell you `items=100, 200, 300`**; to inspect values of individual occurrences, you must run **jfr print**.

### 7.3. Printing only the instances you want to see

~~~bash
jfr print --events demo.WorkPhase jfr-inventory-demo.jfr
~~~

You will find three occurrences with `phase` **phase-1**, **phase-2**, **phase-3** and `items` **100**, **200**, **300** in emission order. Timestamps, durations, and stack frames depend on the execution and JDK.

At this point you have verified three layers:

| Step | New information obtained |
| --- | --- |
| summary | Recording exists; `demo.WorkPhase` has instance count and serialized size |
| metadata | `demo.WorkPhase` has name, label, category, and fields matching the schema |
| print | Concrete instances with values and timestamps |

### 7.4. Trying a filter with no events

~~~bash
jfr print --events jdk.SocketRead jfr-inventory-demo.jfr
~~~

Having no `SocketRead` in the output **does not prove** the JVM process never performed network I/O during its entire lifecycle, nor does it confirm the event was enabled or met its threshold; the command only reflects **instances of that type present in the filtered file**.

You can run **jfr metadata --events jdk.SocketRead** without a file to see the event type known to the current JDK, but avoid inferring backward that the custom recording captured that event.

## 8. A short checklist when receiving a JFR file from production

Before deciding which group to analyze, check:

| Check | Question to answer | Action |
| --- | --- | --- |
| **File/Provenance** | Which JVM/JDK, which app, and when was the file created? | Record JDK/version, filename, host/PID if provided |
| **Time window** | Do Start/Duration cover the incident? | If not, find another recording or re-capture |
| **Chunks / integrity** | Is the file readable and intact? | Run `summary`; handle corrupt or truncated files |
| **Event presence** | Is the desired type Count > 0 or completely absent? | Do not assume data exists when Count=0 |
| **Volume** | Which event types dominate Count/Size? | Filter selectively before printing; watch overhead |
| **Schema** | What are the exact names/categories/fields? | Run `metadata` against the recording itself |
| **Collection settings** | What sampling/threshold/period/stackTrace settings applied? | Check JFR capture config and recording conditions |
| **Correlation keys** | Are `startTime`, `duration`, `thread`, `gcId`, `stackTrace`, or IDs suitable? | Design queries around actual fields |
| **Privacy** | Does the file contain sensitive class names, thread names, command lines, stacks/payloads? | Restrict storage, sharing, and apply redaction per policy |

**Do not confuse "JFR has data" with "JFR has proof of the root cause."** Sometimes `summary` reports thousands of GC events while the incident is network congestion; without I/O events or correlation, you need to capture the right event group and time window.

## 9. Analyzing three scenarios of choosing the wrong events

### Scenario A: High CPU, but summary mostly shows jdk.CPULoad

**Question:** can you find hot methods from `CPULoad` alone?

**Answer:** `CPULoad` mainly reflects load levels and does not necessarily include application call stacks. If `summary` has **jdk.ExecutionSample** and `metadata` confirms `stackTrace` is present, print execution samples and analyze them; otherwise, you need a recording with proper sampling/profiling. A high CPU reading does not by itself point to a method.

### Scenario B: Suspected contention, but JavaMonitorEnter Count=0

There are at least four possibilities: the event was disabled, the threshold filtered out short waits, the error occurred outside the capture window, or the application had no contention of the kind measured by this event. From Count=0 **you cannot pick a single explanation**. Cross-check the file, settings, timeline, `ThreadPark`/monitor-related events, and actual lock usage.

### Scenario C: Suspected allocation pressure, seeing very large ObjectAllocationSample Count

Read `metadata` to see whether the event has fields for **objectClass**, thread/stack, **weight**, or sampling information appropriate for the JDK. A large Count is only **the number of samples**, not the number of allocated objects. Do not use it to compute live object counts or leaks. If you need retained heap and GC roots, use a heap dump/object graph as a separate complementary measurement; do not distort what JFR means.

## 10. Structure of a good analysis from a JFR file

A concise diagnostic note should separate three levels of evidence:

**1. Verified observability:** "Recording started at time X, lasted Y; `summary` shows GC and execution samples, zero `JavaMonitorEnter` instances; `metadata` defines the schema of GC/CPU events."

**2. Observations from real data:** "During the incident window there are long-duration GC events" or "ExecutionSample stacks cluster in method A." These statements must rest on **jfr print/view or event-instance analysis**, not merely on the Count table.

**3. Hypotheses to verify:** "GC or lock contention may be causing latency; need to cross-check request timestamps, GC logs, metrics, or capture additional event classes." Explicitly note any missing samples or off-window capture.

Separating these three levels prevents turning **measurability** into **causal proof**, and tells recipients when a recording needs to be re-captured.

## 11. Common mistakes and how to fix them

1. **Printing the whole file before viewing summary.** Large files produce huge output; run `summary`, filter by type, then print.
2. **Using metadata to count events.** Metadata describes types; use `summary` or read instances to count.
3. **Using summary to look for fields or stacks.** Summary does not replace `metadata` or `print`.
4. **Thinking Size is heap bytes or I/O bytes.** It is the size of event data recorded in the file.
5. **Thinking sample Count equals real operation count.** Sampling, thresholds, and periods make Count differ from total operations.
6. **Seeing an event in metadata and claiming the file has that event.** Always check instance count.
7. **Seeing Count=0 and concluding "no problem."** The event may be disabled, filtered by threshold, or missed by the recording window.
8. **Assuming `jfr metadata` without a file describes the application's recording.** It describes the JDK running the command, which may differ from the producer JDK.
9. **Writing category filters with guessed names.** Check actual categories in `metadata`; when precision is needed, use full event names.
10. **Combining `--events` and `--categories` thinking it is an intersection.** In JDK 21 `jfr print`, they select a **union**.
11. **Increasing `--stack-depth` thinking it creates unrecorded stacks.** It only increases what is printed when stack data already exists.
12. **Ignoring `startTime` and timezone.** An incident outside the recording window misleads the entire analysis.
13. **Treating every GC event as an application pause.** Check GC type/phase/duration and correlation with latency.
14. **Mixing event fields across JDKs.** Inspect the schema from the `.jfr` file itself and check tool versions.
15. **Assigning root cause from an event name.** Inspect values/timeline and verify with other evidence.
16. **Sharing JFR files carelessly.** Files may contain command-line flags, arguments, class/method names, paths, network info, and sensitive custom event data; share only per policy.

## 12. Self-check questions

**Question 1:** `summary` reports **jdk.ExecutionSample Count=10.000**. Can we say the JVM executed exactly 10,000 method calls?  
**Answer:** No. That is the number of recorded execution samples, not a call count.

**Question 2:** `metadata` lists **jdk.JavaMonitorEnter**, yet `summary` reports Count=0. What has been confirmed?  
**Answer:** The type definition exists in metadata; there are zero instances of that type in the file. It does not prove there was no contention or that the event was enabled.

**Question 3:** `summary` reports **jdk.SocketRead Size=80 KB**. Did the application read 80 KB from sockets?  
**Answer:** No. That is serialized event data size. To read I/O byte counts, inspect the corresponding fields in event instances and the event's semantics.

**Question 4:** You need to check the **duration** or **stackTrace** fields of `jdk.JavaMonitorEnter` before writing a parser. Which command do you run?  
**Answer:** **jfr metadata --events jdk.JavaMonitorEnter recording.jfr**, then verify instance data via **jfr print** and confirm stacks were collected.

**Question 5:** You want to view both GC and `CPULoad` without printing every event. Command?  
**Answer:** **jfr print --categories GC --events jdk.CPULoad recording.jfr** (the combination is a **union**, not an intersection).

**Question 6:** `metadata` without a file on machine A differs from metadata inside a recording from machine B. What is the right way to read and understand the recording itself?  
**Answer:** **jfr metadata recording.jfr**; also note the producer JDK and reader JDK.

**Question 7:** A recording is 30 seconds long, and a 2-minute incident occurred 10 minutes later. Can you infer the cause from this file?  
**Answer:** There is insufficient direct basis; you need a recording covering the incident window or other correlated data sources.

## References

- [Oracle JDK 21 — The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): syntax for **summary, metadata, print, view**, filters, and stack-depth.
- [Oracle JDK 17 — The jfr Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html): core command set when using JDK 17.
- [Oracle JDK 21 — jdk.jfr package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): event model, annotations, settings, and schema.
- [Oracle JDK 21 — Recording API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html): creating/enabling/starting/stopping/dumping recordings.
- [Oracle JDK 21 — EventSettings API](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): threshold, period, and stackTrace.
- [Oracle dev.java — JFR command line tool](https://dev.java/learn/jvm/jfr/tools/): official hands-on guide for JFR files.
