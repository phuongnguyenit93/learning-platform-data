# 18.2. JFR FileRead, FileWrite, SocketRead, and SocketWrite by Duration or Size

## 1. Purpose and scope of this lesson

When a Java application responds slowly, time may be spent in file or socket read/write operations. **Java Flight Recorder (JFR)** lets you record specific I/O operations as *duration events* to see **which thread**, **which file or connection**, **how long each operation took**, and **how many bytes were transferred**.

Four events to recognize:

- `jdk.FileRead` — a read operation from a file.
- `jdk.FileWrite` — a write operation to a file.
- `jdk.SocketRead` — a read operation from a socket.
- `jdk.SocketWrite` — a write operation to a socket.

**The focus of this lesson is two distinct filtering dimensions:** *duration* (events that took a long time) and *size* (events that transferred many bytes). An operation can be slow with very few bytes, or fast with many bytes. Therefore, "reading a lot of data" must never be treated as equivalent to "reading slowly," or vice versa.

After this lesson, you will be able to:

1. Read the exact names, fields, and units of the four events.
2. Understand clearly that **JFR `threshold` uses duration**, whereas filtering by byte count is usually done **after events are collected**.
3. Enable and verify these events in a recording; extract data using `jfr`, JDK Mission Control, or the `RecordingFile` API.
4. Group by path/endpoint/thread, find slow or high-byte operations, and separate what events actually prove from root-cause hypotheses.
5. Run a Java 17+ example that records all four I/O types and verifies their presence in a `.jfr` file.
6. Avoid misinterpretations caused by thresholds, missing events, concurrent operations, or JDK instrumentation coverage limits.

Scope: **JFR I/O events emitted by the JVM**, not an all-syscall OS counter or a complete network/disk monitoring solution. Results depend on the JDK, VM, event configuration, and the I/O API paths the application actually uses.

## 2. Path from I/O to a JFR event

~~~text
Java Code                        HotSpot/JDK instrumentation
----------                       ---------------------------
FileInputStream.read()  --------> jdk.FileRead
FileOutputStream.write() -------> jdk.FileWrite
Socket InputStream.read() ------> jdk.SocketRead
Socket OutputStream.write() ----> jdk.SocketWrite
                                           |
                                           | if event is enabled
                                           | and duration meets threshold
                                           v
                                      JFR Event
                        (startTime, duration, bytes, thread,
                         path or host/address/port...)
                                           |
                                           v
                                    .jfr Recording
                                           |
                         +-----------------+----------------+
                         |                                  |
                    jfr print/view                    JMC / Java API
                         |                                  |
                         +--------------> analysis <--------+
~~~

This diagram **illustrates common APIs that have instrumentation**. It does not promise that every `read()`/`write()` call or every NIO/asynchronous/native API emits a corresponding event across all JDK releases. A single library call may trigger multiple low-level operations, multiple operations may be coalesced, or an I/O path may bypass the observed hook. Verify on the exact target JVM and workload instead of guessing from method names.

A JFR recording contains **filtered events**, not a complete log of all I/O. If `threshold=20 ms`, a 2 ms operation may be omitted even if it transfers megabytes. Conversely, a 1-byte read taking 200 ms can still appear.

### 2.1. What is event duration?

`RecordedEvent.getDuration()` returns a `java.time.Duration` for **a single event**, i.e., the duration recorded for that operation. It does not equal total HTTP request latency, is not always physical device busy time, and does not directly represent application-wide bytes/second. Duration is also affected by how the API works, blocking behavior, scheduling, and instrumentation.

For example: `jdk.SocketRead` takes 180 ms to receive 100 bytes. Possible causes include a slow peer response, waiting for data, the network, TLS/application framing, or thread scheduling. **The event only localizes the duration of the call**; it is not enough to conclude the network is broken.

### 2.2. What is event size?

`bytesRead`/`bytesWritten` represent **the number of bytes transferred in the recorded operation**. They are not the entire file size, the total bytes of an HTTP request, business-level payload length, wire bandwidth utilization, or allocated disk space.

For example, a single `FileRead.bytesRead=8192` means that operation returned 8192 bytes according to instrumentation; the underlying file may still be gigabytes long. A single socket read request may be split across multiple events, each carrying only part of the bytes.

## 3. Schema of the four event types

The following field names match metadata observed on OpenJDK 24 and are typical for HotSpot. **When automating, read the metadata of the actual JDK/file**, as internal events and fields can differ between releases.

| Event | Common specific fields | Primary meaning |
| --- | --- | --- |
| `jdk.FileRead` | `path: String`; `bytesRead: long`; `endOfFile: boolean` | Which file was read, bytes read, whether EOF was reached |
| `jdk.FileWrite` | `path: String`; `bytesWritten: long` | Which file was written, bytes written |
| `jdk.SocketRead` | `host: String`; `address: String`; `port: int`; `timeout: long`; `bytesRead: long`; `endOfStream: boolean` | Remote address/port, configured timeout (ms), data received, EOF on stream |
| `jdk.SocketWrite` | `host: String`; `address: String`; `port: int`; `bytesWritten: long` | Remote socket destination and bytes written |

All four types also share common event fields such as `startTime`, `duration`, `eventThread`, and `stackTrace` (if the recording collects stacks). When using the Java consumer API, obtain duration via `event.getDuration()` and thread via `event.getThread()`; do not guess how to interpret raw ticks in the file.

- `path` can be `N/A` or lack a useful path when using file descriptors, `System.in`/`System.out`, or special sources. Do not assume every file event has a valid absolute path.
- `host` and `address` may differ: hostname vs. IP address. `port` is the **remote port**, not by default the local listening port of the analyzed process.
- `timeout` on `SocketRead` is the configured read timeout (field annotated in milliseconds), **not the actual duration waited**. Use `event.getDuration()` to measure operation duration; never misread `timeout=5000` as "took 5 seconds."
- `endOfFile` and `endOfStream` indicate the read reached the end of the source. An EOF event with `bytesRead=0` does not prove 0 bytes were transferred over the entire session; it describes only that individual operation.
- `stackTrace` can be `null` if stack traces were not enabled for the event, were truncated by configuration, or were not provided by the JVM. Do not build pipelines that assume stacks are always present.

### 3.1. Inspecting fields with JDK tools

~~~bash
# Use the JDK being analyzed; verify schema directly on that JDK.
jfr metadata --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite

# If you already have a recording, inspect metadata embedded in that recording:
jfr metadata --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite io-diagnostics.jfr
~~~

`jfr metadata` does not count how many I/O operations occurred; it describes the schema. Use `jfr summary` and `jfr print` when you want to see **actual event instances**. Having metadata for an event does not mean instances exist in the file.

## 4. Duration and size are two independent criteria

| Criterion | Measured by | Where applied | Risk if misunderstood |
| --- | --- | --- | --- |
| **Duration** | `getDuration()` or `duration` field, usually shown in ms | JFR has **`threshold`** at capture time; also re-filtered post-capture | Drops thousands of fast I/Os, even if total bytes are huge |
| **Bytes** | `bytesRead` / `bytesWritten`, in **bytes** | Usually **filtered on collected events** via JMC/API/script | Data below the duration threshold is not in the file to filter by bytes |
| **Count** | Count of event instances | Aggregated by time window and event type | Count in the file is **qualifying events count**, not necessarily all I/O calls |
| **Endpoint/path** | `path` or `address/host + port` | Post-capture group/filter | Hostnames may be unstable; paths may contain sensitive data or be hidden |
| **Thread/stack** | `getThread()`, `getStackTrace()` | Investigate caller and waiting code | Stacks may be missing; does not replace full request traces |

### 4.1. JFR duration threshold

In `jdk.jfr`, the `threshold` setting specifies that **durations shorter than the threshold are not recorded**. It can be configured via `EventSettings.withThreshold(Duration)`, `.jfc` files, or recording control tools. In many default/common JFR configurations, I/O events have a threshold around **20 ms**; that is **the value of a specific configuration**, not a fixed rule across all JDKs. `default.jfc`, `profile.jfc`, or custom configurations may differ.

Examples:

- `threshold=20 ms`: reading 1 MiB in 4 ms is **not recorded** by this event type, despite the large byte count.
- `threshold=20 ms`: reading 16 bytes in 150 ms **can be recorded** if the event type is enabled and instrumentation captures it.
- `threshold=0`: does not drop events by duration; convenient for short lab measurements, but can generate **very large numbers of events**, increasing overhead, file size, and analysis cost.
- If the event is disabled, `threshold=0` will not help; `enabled=true` is required.

**There is no built-in "`sizeThreshold=1MB`" setting for these four events in the `EventSettings` API.** If you want every event ≥1 MiB even when fast, you generally have to collect the needed events (lowering the duration threshold appropriately) and filter `bytesRead`/`bytesWritten` **after recording**. Lowering the threshold to 0 in production can incur very high overhead on systems performing high-frequency I/O.

### 4.2. Example classifying the same dataset

This is a **hypothetical table for learning interpretation**, not JFR output from a real machine:

| Event | Duration | Bytes | Notes |
| --- | ---: | ---: | --- |
| `SocketRead` A | 210 ms | 96 B | Slow, very few bytes; suspect waiting on peer/response |
| `FileRead` B | 3 ms | 4 MiB | Fast, many bytes; likely absent in a 20 ms threshold recording |
| `SocketWrite` C | 25 ms | 512 KiB | Both relatively long and large; inspect context |
| `FileWrite` D | 1 ms | 0 B | Write transferred zero bytes; check specific call case |
| `FileRead` E | 85 ms | 4 KiB | Slow, few bytes; check path, filesystem, and caller |

With `duration ≥20 ms`, the set has A/C/E. With `bytes ≥1 MiB`, the set has only B **if B was captured**; however, a JFR file recorded with `threshold=20 ms` will **not** contain B. Concluding "there were no large file reads" from that recording is wrong.

### 4.3. Using AND vs. OR to answer the right question

- **Slow:** `duration ≥ 20 ms`, regardless of bytes.
- **Large:** `bytes ≥ 1 MiB`, regardless of duration; only possible over events that were actually collected.
- **Both slow and large:** `duration ≥ 20 ms AND bytes ≥ 1 MiB`.
- **Slow or large:** `duration ≥ 20 ms OR bytes ≥ 1 MiB`.

State the condition explicitly in result tables. When looking for "requests transferring lots of data," filtering for **a single large-byte event** can miss a request performing 100 small operations. Supplement with aggregations by request/connection/time window using appropriate IDs or application traces.

## 5. Capturing a recording: picking a window and checking events

Suppose a HotSpot JVM has PID `21891` and the operator has attach permissions. The following commands are examples only; run `jcmd 21891 help JFR.start` on the target JVM before applying.

~~~bash
jcmd 21891 VM.version
jcmd 21891 help JFR.start

# Record temporarily for 1 minute with profile settings (file written by JVM when recording ends).
jcmd 21891 JFR.start name=io-diag settings=profile duration=1m filename=/secure/jfr/io-diag.jfr

# Check actual status and configuration:
jcmd 21891 JFR.check name=io-diag
~~~

`settings=profile` is a starting point for deeper investigation, **not a guarantee** that all four events are enabled with your desired threshold. Check the `.jfc`/settings and the recorded file afterward. Enabling more events, lowering thresholds, or turning on stack traces can increase CPU, I/O, disk usage, and latency impact. Test short captures in staging or a controlled incident window before deploying long-running configurations.

**Need per-event custom thresholds:** an easily verifiable approach in the Java API is:

~~~java
// Illustrative snippet inside code that already has a jdk.jfr.Recording variable named recording:
recording.enable("jdk.FileRead")
         .withThreshold(java.time.Duration.ofMillis(5));
recording.enable("jdk.FileWrite")
         .withThreshold(java.time.Duration.ofMillis(5));
recording.enable("jdk.SocketRead")
         .withThreshold(java.time.Duration.ofMillis(20));
recording.enable("jdk.SocketWrite")
         .withThreshold(java.time.Duration.ofMillis(20));
~~~

This snippet is **not a standalone program**. For an externally monitored JVM, you can create a custom `.jfc` with `jfr configure`, adjust the four events, and pass `settings=/path/to/your.jfc` when starting the recording. Verify `jfr configure` syntax and event settings via `jfr help configure` and the target JDK's metadata. Avoid editing the JDK's default templates or enabling `0 ms` indefinitely just to catch rare events.

### 5.1. Analyzing the recorded file

~~~bash
# Verify the file is readable and see how many instances exist per type:
jfr summary /secure/jfr/io-diag.jfr

# Print only the four types; beware output volume can be very large:
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite /secure/jfr/io-diag.jfr

# If the JDK supports it, use view for a summary report:
jfr view types /secure/jfr/io-diag.jfr
~~~

- `summary` returns counts and content size per event type; **count=0** may mean no operations occurred, the event was disabled, the threshold was too high, the recording missed the time window, or that code path lacks instrumentation.
- `print` shows instances including duration, bytes, thread, path/remote address; formatting can change across JDK versions, so automation should use schema-aware APIs/formats and validate fields rather than slicing free-form text lines by fixed columns.
- `view` is a summary tool available when the JDK includes that subcommand; verify with `jfr help view`. Do not treat it as proof that all I/O was captured.
- In JDK Mission Control, inspect the I/O and Socket pages, sorting by duration, bytes, or event count; many views aggregate by host/path/thread. Distinguish metrics from **a threshold-filtered file** from the total workload.

`.jfr` files can contain paths, hosts, IPs, ports, thread names, and stack traces. Restrict access according to security policy and do not share recordings in public channels by default. Ensure the output directory exists, the target JVM has write permission, and sufficient disk space is available.

## 6. Java 17+ example: generating and verifying all four events

This example runs in **a single JVM**: it enables all four event types with threshold 0, writes/reads a temporary file, creates a loopback `ServerSocket` and exchanges data with a local `Socket`, stops/dumps the recording to a `.jfr` file, and reads it with `RecordingFile`.

It intentionally prints whether **at least one event with positive bytes** exists for each type rather than printing exact event counts, durations, or sizes (which depend on the JDK, OS, flushing, and I/O batching). Because `threshold=0` is used solely for this short demo, **do not copy this configuration verbatim into a 24/7 production collector**.

Save as `JfrIoEventsDemo.java`:

~~~java
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrIoEventsDemo {
    private static final String[] NAMES = {
        "jdk.FileRead", "jdk.FileWrite", "jdk.SocketRead", "jdk.SocketWrite"
    };

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("jfr-io-data-", ".bin");
        Path recordingFile = Files.createTempFile("jfr-io-recording-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                for (String name : NAMES) {
                    recording.enable(name)
                             .withThreshold(Duration.ZERO)
                             .withoutStackTrace();
                }
                recording.start();

                try (FileOutputStream out = new FileOutputStream(file.toFile())) {
                    out.write(new byte[] {1, 2, 3, 4});
                }
                try (FileInputStream in = new FileInputStream(file.toFile())) {
                    if (in.read() != 1) {
                        throw new IllegalStateException("File read failed");
                    }
                }

                try (ServerSocket server = new ServerSocket(
                        0, 1, InetAddress.getLoopbackAddress())) {
                    Thread replyThread = new Thread(() -> {
                        try (Socket accepted = server.accept()) {
                            byte[] request = accepted.getInputStream().readNBytes(4);
                            if (request.length != 4) {
                                throw new IOException("Incomplete request");
                            }
                            accepted.getOutputStream().write(new byte[] {5, 6, 7});
                        } catch (IOException e) {
                            throw new IllegalStateException(e);
                        }
                    }, "loopback-reply");
                    replyThread.start();

                    try (Socket client = new Socket(InetAddress.getLoopbackAddress(),
                                                    server.getLocalPort())) {
                        client.getOutputStream().write(new byte[] {1, 2, 3, 4});
                        byte[] response = client.getInputStream().readNBytes(3);
                        if (response.length != 3) {
                            throw new IOException("Incomplete response");
                        }
                    }
                    replyThread.join();
                }

                recording.stop();
                recording.dump(recordingFile);
            }

            Map<String, Boolean> found = new LinkedHashMap<>();
            for (String name : NAMES) found.put(name, false);

            try (RecordingFile reader = new RecordingFile(recordingFile)) {
                while (reader.hasMoreEvents()) {
                    RecordedEvent event = reader.readEvent();
                    String name = event.getEventType().getName();
                    if (!found.containsKey(name)) continue;
                    String field = name.endsWith("Read") ? "bytesRead" : "bytesWritten";
                    if (event.hasField(field) && event.getLong(field) > 0) {
                        found.put(name, true);
                    }
                }
            }
            for (Map.Entry<String, Boolean> entry : found.entrySet()) {
                System.out.println(entry.getKey() + "=" + entry.getValue());
            }
        } finally {
            Files.deleteIfExists(file);
            Files.deleteIfExists(recordingFile);
        }
    }
}
~~~

Compile and run with **JDK 17+ with JFR**. The sample requires permission to create temporary files and open loopback sockets:

~~~bash
javac JfrIoEventsDemo.java
java JfrIoEventsDemo
~~~

Stdout **directly verified on OpenJDK 24**:

~~~text
jdk.FileRead=true
jdk.FileWrite=true
jdk.SocketRead=true
jdk.SocketWrite=true
~~~

**How to interpret:**

- Each `true` line means the recording contains at least one instance with `bytesRead` or `bytesWritten` >0 for that event type. It does not state the total event count, total bytes, latency, or that the JVM always emits exactly one event per call.
- If another environment prints `false`, check JFR availability, thread/IO APIs, recording settings, loopback permissions, JVM/version, and metadata before blaming a Java bug. The example intentionally avoids fabricating fixed durations or byte counts.
- `Recording.enable(name).withThreshold(Duration.ZERO)` captures short operations in this lab. `withoutStackTrace()` reduces call stack data for these four event types, so this output cannot tell which method triggered the I/O; enable stacks during real investigations when needed.
- `recording.stop()` followed by `dump()` writes a copy from the stopped recording data before `close()`.
- `RecordingFile` reads each `RecordedEvent` and checks names/fields instead of parsing text output. It still needs to handle schema differences if run across multiple JDK versions.
- `finally` deletes temporary files; files can remain if the process is killed abruptly, so real environments must manage cleanup/retention.

## 7. Filtering by duration or size with the Java API

This is an **illustrative code snippet inside a `RecordedEvent` reading loop**, not a standalone program. It demonstrates separating slow operations (≥20 ms) from large operations (≥1 MiB). Whether this catches everything depends on which events were actually recorded.

~~~java
// "event" is a jdk.jfr.consumer.RecordedEvent read from RecordingFile.
String type = event.getEventType().getName();
boolean read = type.equals("jdk.FileRead") || type.equals("jdk.SocketRead");
boolean write = type.equals("jdk.FileWrite") || type.equals("jdk.SocketWrite");
if (read || write) {
    String bytesField = read ? "bytesRead" : "bytesWritten";
    if (event.hasField(bytesField)) {
        long bytes = event.getLong(bytesField);
        java.time.Duration elapsed = event.getDuration();
        boolean slow = elapsed.compareTo(java.time.Duration.ofMillis(20)) >= 0;
        boolean large = bytes >= 1024L * 1024L;

        if (slow || large) {
            // Apply analysis policy here: record appropriate metrics/summaries.
            System.out.printf("%s slow=%s large=%s%n", type, slow, large);
        }
    }
}
~~~

**Do not turn this snippet straight into a production parser:** you also must resolve paths/endpoints, time windows, nulls/schema variations, storage/privacy, missing events, and analysis load. Catching parsing exceptions and substituting `bytes=0` produces wrong numbers. When an expected API field does not exist, report a schema mismatch instead of assigning a misleading meaning.

To group by the same endpoint, you can key on:

- File: `event.getString("path")`, normalized per policy (temporary paths with random IDs can cause cardinality explosion).
- Socket: `host/address/port`, noting that the same IP can host multiple services by port and the same endpoint can have multiple connections.
- Window: `getStartTime()`/`getEndTime()`, aligned on timezone/clock to correlate with application logs.
- Thread: `event.getThread()`, convenient for finding the call site when stacks are enabled, though not always synonymous with "request owner."

### 7.1. An illustrative aggregation exercise

Within a 60-second window, there are 3 `SocketRead` events to the same peer:

| Event | Duration | bytesRead |
| --- | ---: | ---: |
| R1 | 100 ms | 100 |
| R2 | 5 ms | 4000 |
| R3 | 180 ms | 100 |

If **all three events were captured** (allowed by threshold):

- Total count = 3, total bytesRead = **4,200 B**.
- Total duration = **285 ms**, average duration = **95 ms/event**.
- At a 20 ms threshold: there are 2 slow events, count 2, bytes of slow events = **200 B**.
- If the recording used a 20 ms threshold, R2 (5 ms, 4000 B) might **not exist** in the file: count and total bytes computed from JFR would then reflect **only events meeting the threshold**, not true I/O totals.
- Total duration of 285 ms does not necessarily mean the application spent 285 ms wall-clock time: events on different threads may overlap, and the same socket may be handled concurrently depending on application architecture.

**The ratio bytes/total duration is not actual network bandwidth.** For wait-heavy operations, it resembles transfer rate over *recorded call duration*; to measure real throughput, use total bytes over a **wall-clock** interval with complete coverage and cross-check network/OS metrics.

## 8. How to interpret slow I/O investigations

### 8.1. Long SocketRead, few bytes

For example, a `SocketRead` takes 450 ms but receives only 32 B:

- The request may be waiting for the server/peer to send data, experiencing network latency, slow backend processing, or application pauses between frames.
- `duration` describes the read operation; it does **not** directly measure RTT, congestion, or HTTP server processing time.
- Inspect host/address/port, thread name, stack if enabled, timestamp, and what step the application is in; combine with distributed traces, server logs, and network metrics to distinguish causes.

Specifically, `SocketRead.timeout` is a configured setting, not the actual wait time. If `timeout=5000 ms` while `event duration=40 ms`, do not claim the operation took 5 seconds.

### 8.2. Long or high-byte SocketWrite

Socket write returns when data is accepted by the API/socket stack according to its semantics, **not as proof that the remote service received and processed everything**. High duration can involve backpressure, send buffers, peer read speed, TLS wrappers, or scheduling. High byte counts may simply reflect batch payloads rather than a performance bug.

Identify connections with large total writes or prolonged write events; verify whether the application is streaming/uploading as designed. For HTTPS, `SocketWrite` events reflect socket-layer bytes (potentially ciphertext/framing), not necessarily the business payload size.

### 8.3. Prolonged FileRead/FileWrite

Slow file I/O can relate to disk, filesystem, network mounts, antivirus, page cache, contention, or scheduling. A fast `FileRead` does not prove a fast physical disk because data may come from the OS page cache; a fast `FileWrite` does not prove data has been safely `fsync`ed to storage.

Cross-check path (if available), mount/volume, actual file size, IOPS, disk latency, queue depth, JVM thread stacks, GC/CPU pressure, and concurrent workload. JFR events generally do not measure `fsync` duration or durability guarantees separately. If log flushing or JDBC storage is suspected, gather evidence at the appropriate layer.

### 8.4. "No events" does not mean "no I/O"

An empty result can occur because:

1. The event type was not enabled in `.jfc`/recording.
2. All operations had durations below the threshold.
3. The recording started too late, ended before the workload, or failed to dump.
4. The code used an API that does not emit this event type on that specific JDK.
5. Operations occurred in another process or native code outside the recorded JVM.
6. The wrong event name was filtered in `jfr print`/JMC.
7. The recording file is missing chunks, was not stopped/dumped properly, or was only partially read.

Therefore, always verify `jfr summary`, metadata, timestamps, settings, and a small sanity check operation before trusting "zero I/O."

## 9. Workload-oriented analysis and metric limits

| Question | How JFR helps | What else is needed to conclude |
| --- | --- | --- |
| What is the slowest file operation? | Sort `jdk.FileRead/FileWrite` by `duration` | Cross-check path, OS disk metrics, stack |
| Which peer causes long read waits? | Group `SocketRead` by host/address/port and inspect duration | Client/server traces, timeouts/retries, network metrics |
| Which file had the most bytes read? | Group `FileRead.bytesRead` | Threshold low enough not to miss fast reads; filesystem/process counters |
| What is total application traffic? | Sum of bytes from captured events is a signal | Complete socket metrics/telemetry, TLS framing, other sockets |
| Does I/O cause slow HTTP request p99? | Thread/timestamp/stack can point to suspects | Request spans, correlation IDs, app latency timeline |
| How many I/O calls per second? | Count events per time window | Verify coverage, threshold, instrumentation; do not equate event count with syscall count |
| Which thread produced each event? | `eventThread` and stack if enabled | Mapping to executor/task/request context |
| What caused retries, timeouts, EOF? | `SocketRead.timeout`, `endOfStream`, `FileRead.endOfFile` add context | App exceptions/logs, protocol state, peer telemetry |

**Do not sum the durations of the four events and call it "total time the application was stalled."** Events across multiple threads can overlap in time, or a single request may perform both FileWrite and SocketWrite. Measure the critical path via application tracing if user latency is the target.

**Do not sum bytes from both sides of the same internal connection and treat it as unique system traffic.** A JVM running both loopback client and server like the lab will record both `SocketWrite` on the sender and `SocketRead` on the receiver; those are two observations of one data flow, not two independent payloads.

## 10. Overhead, data safety, and deployment environment

### 10.1. Trade-offs when lowering thresholds

Lowering thresholds can increase event volume, recording size, CPU usage, and stack trace/aggregation cost. Use higher thresholds to spot **slow spikes**, then run short captures with lower thresholds if you need complete **byte/count** statistics. Do not run `0 ms` indefinitely on I/O-heavy systems without benchmarking.

Experiment design: capture baseline throughput/p95/p99/error rate and CPU; enable the JFR configuration for an equivalent load window; measure deltas; trim events or raise thresholds if impact exceeds budget. For continuous recordings, set `maxage`/`maxsize` and monitor disk/repository capacity.

### 10.2. Potentially sensitive fields

`path`, `host`, `address`, `port`, `thread name`, and `stackTrace` can reveal system layout, user filenames, or internal connection endpoints. Do not put raw paths/endpoints with unbounded cardinality into metric labels. Store only what is needed for investigation, restrict `.jfr` file access via permissions, and delete temporary files after analysis.

### 10.3. Deploying outside the tested JVM

Different JDKs/vendors may alter events, fields, or instrumentation behavior. Checking `jfr metadata` on the recording and `event.hasField(...)` in code prevents silent failures. For JVMs in containers, account for PID namespaces, `jcmd` permissions, and the target JVM's filesystem paths. NIO, asynchronous I/O, virtual threads, or native libraries can change event coverage; validate experimentally with the APIs actually used.

When `.jfr` files are large, running `jfr print` on everything can produce huge stdout: filter by event type and time range where supported, or use `jfr view`/JMC or the `RecordingFile` streaming API with bounded aggregation. For continuous dashboards, pair JFR with application/OpenTelemetry telemetry and OS metrics; do not treat incident recordings as the sole source of metrics.

## 11. Common pitfalls

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| `FileRead` is rare so files are rarely read | Threshold dropped all short operations | Read settings and verify against workload |
| `SocketRead.timeout = 2000` means the read took 2 seconds | Timeout is a configured limit | Use `getDuration()` for actual duration |
| `bytesWritten` equals HTTP response size | Socket includes framing/TLS and multiple writes | Measure business payload separately or aggregate with context |
| Using `duration` to compute app-wide throughput | Events may not cover all I/O and can overlap | Use wall-clock and valid byte totals, cross-checked with other telemetry |
| Filtering "bytes ≥1MiB" after recording with 20 ms threshold and calling it complete | Fast large I/Os were already dropped | Lower duration threshold for a bounded measurement window when overhead is acceptable |
| Adding loopback socket read and write as "unique" traffic | Both sides observe the same data | Specify direction/endpoint clearly |
| Fast FileWrite means durable disk write | Write may only hit cache/buffers | Distinguish write from fsync/flush/durability |
| Enabling all four events at threshold 0 in production without limits | Event volume and overhead can be large | Test briefly, bound duration/size, and measure impact |
| One JFR event equals one request | One request can do many I/Os; many requests share a socket | Use app IDs/traces to correlate |
| Stacks are always present to find call sites | `stackTrace` may be disabled | Enable stacks when needed for investigation and benchmark overhead |
| Upgrading JDK while keeping hard-coded field parsers | Schema can change | Check `jfr metadata`/`hasField` during upgrades |

## 12. Exercises and self-check

**Exercise 1 — separating the two criteria.** There is a `FileRead` of 2 ms / 8 MiB and a `SocketRead` of 150 ms / 128 B. If the recording threshold is 20 ms, which event can appear? Only the socket read. What must you do to find the 8 MiB file read? Record with a lower threshold (after measuring overhead), then filter on `bytesRead`.

**Exercise 2 — units.** `SocketRead.timeout=3000`, `getDuration()=120 ms`, `bytesRead=64`. What is the timeout? 3000 ms **configured setting**. The operation recorded 120 ms and 64 B, which alone does not confirm a network or server fault.

**Exercise 3 — measurement scope.** In 1 minute, 100 socket reads each take 5 ms and 8 KiB, while JFR threshold is 20 ms. `summary` reports count=0. Can you conclude network throughput=0? No; the operations lacked enough duration to become events.

**Exercise 4 — adding durations.** Two parallel threads each have `SocketRead.duration=100 ms` during 10:00:00.000–10:00:00.100. Total duration=200 ms, elapsed window is only 100 ms. Do not use 200 ms as request wall-clock latency without analyzing the critical path.

**Exercise 5 — duplicated data.** A JVM runs both a loopback client and loopback server and writes 1 MiB. The recording shows `SocketWrite.bytesWritten≈1 MiB` and `SocketRead.bytesRead≈1 MiB` for the same exchange. Can you say "2 MiB of independent data were transferred"? No; those are two viewpoints of one data stream.

**Exercise 6 — root cause.** Top `FileWrite` event is 500 ms, `bytesWritten=512`; the JVM uses a network-mounted drive. Which sources should be cross-checked? Thread stacks, timestamps, app logs, OS I/O wait and filesystem/network mount metrics, plus GC/CPU to distinguish stalls.

**Exercise 7 — checking code.** Run `JfrIoEventsDemo`, then try `.withThreshold(Duration.ofSeconds(10))` on all four events. Why might it print `false`? The four sample operations take less than 10 seconds and are filtered out. Do not alter the boolean printing logic to force `true`.

**Exercise 8 — choosing the filter.** Requirement: "I/Os ≥10 MiB *or* ≥100 ms." Write the condition `bytes >= 10*1024*1024 || duration >= 100 ms` on collected events. Explain why setting `threshold=100ms` at capture time will never guarantee capturing fast events ≥10 MiB.

## 13. Operational checklist

- [ ] Target the exact JVM/PID and exact time window exhibiting slow I/O.
- [ ] Confirm all four events are enabled and know the actual `threshold` values.
- [ ] Remember duration is for one event and bytes are for **that operation**, not identical to request/file/connection totals.
- [ ] Inspected `jfr summary` and file metadata to avoid drawing conclusions from empty event counts.
- [ ] Selected duration filters, byte filters, AND/OR logic, and grouping by path/peer/time with clear annotations.
- [ ] Understand missing data due to thresholds or instrumentation; do not substitute 0.
- [ ] Combine threads/stacks/app traces and OS metrics before declaring root cause.
- [ ] Monitor overhead, retention, disk usage, access permissions, and `.jfr` cleanup.

**Conclusion:** JFR provides useful evidence for **duration** and **byte counts** of recorded file/socket operations. The capture `threshold` primarily controls **duration**, whereas questions about "how many I/O bytes" must be analyzed from fields on **events that were actually captured**. Read the schema, capture limits, and workload thoroughly before turning results into a performance assessment.

## References

- Oracle Java SE 21, [The jfr Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html) — `metadata`, `summary`, `print`, and `view`.
- Oracle Java SE 21, [The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html) — `JFR.start`, `JFR.check`, and recording options.
- Oracle Java SE 21, [jdk.jfr Package](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html) — `enabled`, `threshold`, `period`, and `stackTrace`.
- Oracle Java SE 21, [EventSettings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/EventSettings.html) — `withThreshold(Duration)` and event configuration.
- Oracle Java SE 21, [RecordedEvent](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html) — `getDuration`, `getStartTime`, `getEndTime`.
- Oracle Java SE 21, [Recording](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html) and [RecordingFile](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html) — starting/recording/dumping and reading `.jfr` in Java.
- Oracle Java SE 21, [Troubleshooting Guide](https://docs.oracle.com/en/java/javase/21/troubleshoot/) — investigating I/O bottlenecks with JFR, thresholds, and overhead of additional event collection.
