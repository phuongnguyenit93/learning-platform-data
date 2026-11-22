# I/O Events in Java Flight Recorder

**I/O events** in Java Flight Recorder (JFR) are events that record certain JVM file or socket read and write operations, along with their execution duration, thread, data transferred, and calling context. These events help identify slow I/O points, pinpoint the involved files or remote hosts, and trace the stack trace leading to the operation.

The four key events are **jdk.FileRead**, **jdk.FileWrite**, **jdk.SocketRead**, and **jdk.SocketWrite**. JFR also provides aggregated views by file path, remote host, and latency type. During analysis, it is important to distinguish the duration of an I/O operation at the JVM level from the end-to-end processing time of a request; a slow socket read does not by itself prove that the remote server is processing slowly.

This lesson explains how to collect, read, and interpret I/O events using JFR, JDK Mission Control (JMC), jcmd, and the jfr CLI, and includes a Java 17+ lab that generates file I/O and loopback socket I/O for hands-on practice.

## 1. What Questions Do I/O Events Answer?

When an application is slow, the cause may lie in CPU, garbage collection, lock contention, the file system, the network, or a dependent service. I/O events help answer the following questions:

- Which thread is reading or writing a file?
- Which file path has slow operations?
- How many bytes is the application reading or writing?
- Which remote host and port are involved in socket I/O?
- How long does a socket read take?
- Which stack trace leads to the I/O operation?
- Are slow operations concentrated on a single file, a single host, or multiple dependencies?
- Does the latency come from file reads, file writes, socket reads, or socket writes?

JFR records events at JVM-instrumented I/O points. The data may include start time, duration, thread, stack trace, file path, or endpoint information. JFR does not record file contents or network payloads in these standard I/O events.

### I/O Events vs. CPU Profiling

CPU profiling samples threads while they are executing code. I/O events record the duration of instrumented I/O operations.

A thread may consume very little CPU yet still slow down requests because it is waiting on a socket or file. Conversely, a thread may continuously perform computations after reading data and create a CPU hot method.

You should combine I/O events with CPU samples, thread states, lock events, GC events, and application metrics to understand the entire execution path.

## 2. The Four Key I/O Events

JDK 24 JFR defines four standard events in the Java Application category:

| Event | Meaning | Key Fields |
|---|---|---|
| jdk.FileRead | Reading data from a file | Path, bytesRead, endOfFile |
| jdk.FileWrite | Writing data to a file | Path, bytesWritten |
| jdk.SocketRead | Reading data from a socket | Host, address, port, timeout, bytesRead, endOfStream |
| jdk.SocketWrite | Writing data to a socket | Host, address, port, bytesWritten |

Each event includes start time, duration, event thread, and stack trace according to JFR metadata. Stack traces are recorded when enabled in the event configuration.

### jdk.FileRead

Records operations that read data from a file. Key fields:

- **startTime:** timestamp when the operation started.
- **duration:** how long the operation took.
- **eventThread:** thread performing the operation.
- **stackTrace:** call stack at the point where the event was recorded, if enabled.
- **path:** full file path; may be N/A if the stream was created from a file descriptor such as System.in.
- **bytesRead:** number of bytes read, which may be 0.
- **endOfFile:** indicates whether the end of the file was reached.

If a file has many slow reads, group by path, inspect bytesRead, and examine the stack trace to identify the caller.

### jdk.FileWrite

Records operations that write data to a file:

- **path:** file path; may be N/A for file-descriptor-based streams such as System.out or System.err.
- **bytesWritten:** number of bytes written.
- **duration:** duration of the write operation.
- **eventThread** and **stackTrace:** thread and call stack context.

FileWrite does not prove that data has been durably persisted to the storage device. The data may still reside in OS buffers or the filesystem cache. If the application needs to force updates to storage, also inspect **jdk.FileForce** events or FileChannel.force() calls.

### jdk.SocketRead

Records operations that read data from a socket:

- **host:** remote hostname.
- **address:** remote IP address.
- **port:** remote port.
- **timeout:** socket read timeout value in milliseconds.
- **bytesRead:** number of bytes read.
- **endOfStream:** indicates whether end-of-stream was encountered.
- **duration**, **eventThread**, and **stackTrace:** timing and calling context.

A long SocketRead may reflect a thread waiting for data, network delay, a slow remote peer, or an application protocol waiting for enough data to arrive. Correlate it with timeout, bytesRead, host/port, stack trace, and remote service logs.

### jdk.SocketWrite

Records operations that write data to a socket:

- **host**, **address**, **port:** remote endpoint.
- **bytesWritten:** number of bytes written to the socket.
- **duration:** duration of the write operation at the JVM level.
- **eventThread** and **stackTrace:** execution context.

A fast SocketWrite does not prove that the peer has received or processed the data. The write call may simply copy bytes into the kernel buffer and return. To measure peer processing time or round-trip latency, use correlation IDs, protocol timing, tracing, or telemetry on both ends of the connection.

## 3. Event Duration and Thresholds

I/O events are duration events. JFR typically records only events whose duration meets the configured threshold.

In the `JFR.start` help on OpenJDK 24.0.2 (verified):

| JFR template | File I/O threshold | Socket I/O threshold |
|---|---:|---:|
| default.jfc | 20 ms | 20 ms |
| profile.jfc | 10 ms | 10 ms |

Actual values may differ when using a custom `.jfc` or modifying event settings. Always verify the exact template and configuration of the recording.

### Why Might Short Events Not Appear?

Suppose an application performs 10,000 file reads, each lasting only 0.2 ms. With a 10 ms threshold, these operations may not be recorded. The recording might contain no FileRead events even though the application is reading files heavily.

Therefore:

- Seeing no events does not mean there is no I/O.
- Total bytes in the recording may be lower than actual total bytes.
- Event count is not necessarily the total number of read/write calls.
- Recorded events are biased toward operations slower than the threshold.
- Do not use recorded event counts to calculate full throughput if the threshold is filtering out short operations.

### Lowering the Threshold for Investigation

You can set a lower threshold when you need to capture more operations:

~~~bash
jcmd <pid> JFR.start name=io-detail settings=profile duration=20s filename=io-detail.jfr jdk.FileRead#threshold=1ms jdk.FileWrite#threshold=1ms jdk.SocketRead#threshold=1ms jdk.SocketWrite#threshold=1ms
~~~

The example above requests a 1 ms threshold for the four events in the recording. Verify the syntax and event support for your target JDK.

To record all durations, you can set a 0 ms threshold:

~~~bash
jcmd <pid> JFR.start name=io-all settings=profile duration=10s filename=io-all.jfr jdk.FileRead#threshold=0ms jdk.FileWrite#threshold=0ms jdk.SocketRead#threshold=0ms jdk.SocketWrite#threshold=0ms
~~~

A 0 ms threshold can generate a very large number of events, increasing recording size and overhead. Use it only for short durations and after evaluating the impact.

### Creating a Custom JFC

You can create a custom configuration based on `profile`:

~~~bash
jfr configure --input profile.jfc jdk.FileRead#threshold=2ms jdk.FileWrite#threshold=2ms jdk.SocketRead#threshold=2ms jdk.SocketWrite#threshold=2ms --output io-detail.jfc
~~~

Then use the configuration:

~~~bash
jcmd <pid> JFR.start name=io-detail settings=io-detail.jfc duration=30s filename=io-detail.jfr
~~~

The target JVM must be able to access `io-detail.jfc`. If the file is not in the default JFR directory, use the appropriate path on the host running the JVM.

## 4. Starting an I/O Recording with jcmd

First, identify the target JVM:

~~~bash
jcmd -l
~~~

Or:

~~~bash
jps -l
~~~

Verify the PID using OS tools and ensure you are targeting the right host, container, and user.

Start a 30-second `profile` recording:

~~~bash
jcmd <pid> JFR.start name=io-investigation settings=profile duration=30s filename=io-investigation.jfr
~~~

Check the recording:

~~~bash
jcmd <pid> JFR.check
~~~

`JFR.start` has an impact that depends on its settings; on JDK 24, the command is described as Medium impact, varying from low to high depending on configuration. `profile` collects more data than `default` and has higher overhead. For production, choose short durations, limit recording size, and monitor the application while recording.

### Default vs. Profile

| Template | Characteristics | Usage |
|---|---|---|
| default.jfc | Low overhead, suitable for continuous recording | Long-term monitoring or continuous recording |
| profile.jfc | Collects more data, including more detailed profiling | Short investigations when more evidence is needed |

If your goal is capturing I/O events, check the FileRead/FileWrite/SocketRead/SocketWrite thresholds in the template. Even a `profile` recording can miss very short operations if the threshold is higher than their actual duration.

## 5. Analyzing I/O with the jfr CLI

JDK 24 provides aggregated I/O views in the `jfr` CLI.

View the summary:

~~~bash
jfr summary io-investigation.jfr
~~~

### File Reads by Path

~~~bash
jfr view file-reads-by-path io-investigation.jfr
~~~

This view groups read operations by file path. Use it to find files with notable read activity.

### File Writes by Path

~~~bash
jfr view file-writes-by-path io-investigation.jfr
~~~

This view helps identify files that are written frequently or have significant write durations.

### Socket Reads by Host

~~~bash
jfr view socket-reads-by-host io-investigation.jfr
~~~

Use this to see which remote hosts are involved in socket reads in the recording.

### Socket Writes by Host

~~~bash
jfr view socket-writes-by-host io-investigation.jfr
~~~

Use this to see which hosts are receiving data from the application.

### Latencies by Type

~~~bash
jfr view latencies-by-type io-investigation.jfr
~~~

This view summarizes latency by supported event type. It is a starting point for comparing I/O categories; you still need to inspect individual events and stack traces to find the caller.

You can increase the table width:

~~~bash
jfr view --width 160 file-reads-by-path io-investigation.jfr
~~~

Available view names and displayed columns depend on the JDK version. On older JDKs without `jfr view`, use JMC or `jfr print`.

### Printing Raw Events

To view individual FileRead/FileWrite events:

~~~bash
jfr print --events jdk.FileRead,jdk.FileWrite io-investigation.jfr
~~~

To view individual SocketRead/SocketWrite events:

~~~bash
jfr print --events jdk.SocketRead,jdk.SocketWrite io-investigation.jfr
~~~

You can filter for a single event:

~~~bash
jfr print --events jdk.SocketRead io-investigation.jfr
~~~

Raw events show start time, duration, thread, stack trace, and metadata fields. When a recording contains many events, the output can be very long; filter for the specific events you need to analyze.

## 6. Analyzing I/O in JDK Mission Control

JDK Mission Control (JMC) provides a graphical interface for opening `.jfr` recordings and analyzing I/O.

Workflow:

1. Open JMC.
2. Select Open File and open the recording.
3. Wait for JMC to parse the events.
4. Open the **I/O** page.
5. Select File Reads, File Writes, Socket Reads, or Socket Writes.
6. Sort by duration, bytes, or event count if supported by the table.
7. Select an event to inspect its details.
8. Inspect the stack trace to find the code generating the I/O.
9. Correlate with thread, CPU, lock, and application metrics.

JMC is a standalone tool and is not bundled as a GUI component with every JDK installation. You can use the `jfr` CLI if JMC is not installed.

### How to Read the File I/O Table

Look for files with:

- Many read/write operations.
- Large durations.
- High total bytes.
- Many events originating from the same stack trace.
- Paths on a network mount or slow storage.

A file with many short events may reflect normal workload. A file with few events but very long durations can cause significant request latency.

### How to Read the Socket I/O Table

Look for:

- Hosts with many socket reads/writes.
- Remote ports associated with databases, caches, APIs, or message brokers.
- High SocketRead duration.
- Low bytesRead paired with long duration.
- High SocketWrite duration or large byte counts.
- Threads and stack traces calling the endpoint.

If multiple threads are waiting on SocketRead to the same host, correlate with server-side latency and network metrics. You cannot determine from the client side alone which exact step the remote application is spending time on.

## 7. Interpreting FileRead and FileWrite

### Slow FileRead

Possible causes:

- High storage latency.
- Network filesystem or remote mount.
- Cache misses requiring reads from the storage device.
- Large files or reading across many data regions.
- Threads performing synchronous I/O.
- System under heavy I/O load.

Inspect path, bytesRead, duration, and stack trace. Compare the same file across multiple recordings and correlate with OS disk metrics.

### Slow FileWrite

Possible causes:

- Storage or filesystem bottleneck.
- Multiple threads writing concurrently to the same volume.
- Writing large volumes of data.
- Expensive filesystem metadata operations.
- Application buffering or flushing behavior.
- Antivirus, backups, or system tasks competing for I/O.

FileWrite measures the instrumented write operation. It does not necessarily represent the time until data is fully persisted to physical media. If the application calls `FileChannel.force()` or `FileDescriptor.sync()`, also inspect FileForce events and force durations.

### More Bytes Does Not Always Mean Slow

A single 10 MB write completing in 5 ms can have better throughput than a 4 KB write taking 50 ms. Always look at both duration and bytes.

Do not sum bytes from a recording that used a threshold and treat that as the application's total I/O volume; short operations may have been omitted.

## 8. Interpreting SocketRead and SocketWrite

### High SocketRead Duration

SocketRead can take a long time when a thread is waiting for data. Possible causes include:

- Slow remote service response.
- Network congestion or packet loss.
- Server sending data in small chunks.
- Protocol requiring the client to wait for more data.
- Socket timeout configured too high.
- Application using blocking I/O when no data is available.

Inspect host, address, port, timeout, bytesRead, endOfStream, and stack trace. Compare with server-side traces to determine whether time is spent in the client, network, or server.

### High SocketWrite Duration

May be related to:

- Full socket send buffer.
- Network backpressure.
- Slow peer reading data.
- Sending large payloads.
- Congestion or an unstable network path.

However, a low SocketWrite duration does not prove the peer has received or processed the data. The kernel may accept bytes into its buffer and return immediately.

### Distinguishing Read Timeout from End-of-Stream

SocketRead has `timeout` and `endOfStream` fields. These are two different concepts:

- **timeout:** configured wait limit for the read operation.
- **endOfStream:** the peer closed its output or there is no more data to read.

If the application receives EOF, check the connection lifecycle and protocol. If a read timeout occurs, correlate with socket configuration and exception logs.

## 9. Event Duration Is Not End-to-End Request Latency

This is the most important limitation when analyzing I/O events.

Consider a request calling a remote API:

~~~text
Client request
  -> Serialize request
  -> SocketWrite
  -> Network
  -> Remote service processes request
  -> Network response
  -> SocketRead
  -> Deserialize response
  -> Client response
~~~

SocketWrite only measures the instrumented socket write operation. SocketRead measures the instrumented socket read operation. Total request time also includes serialization, network transit, remote processing, queueing, retries, and other steps.

Similarly, FileRead/FileWrite do not measure the entire business logic around file operations.

To measure end-to-end latency, use distributed tracing or application-level timing with correlation IDs. JFR I/O events help identify which I/O component is worth investigating; they do not replace full request traces.

## 10. Blocking, Non-Blocking, and Asynchronous I/O

Standard I/O events are recorded at points where the JDK instruments read/write operations. Interpretation depends on the API and implementation.

### Blocking I/O

In a blocking read, a thread may wait until data arrives, EOF is reached, or a timeout occurs. SocketRead duration can reflect how long the thread spent in that read operation.

### Non-Blocking I/O

With non-blocking NIO, read/write operations may return immediately with 0 bytes or a small amount of data. A short event does not show the total selector wait time or the logical wait time of the request.

### Asynchronous I/O

With asynchronous channels or event-driven frameworks, operations may complete on a different thread or callback. The stack trace and event thread may reflect the instrumented I/O point rather than the thread that originally initiated the request.

### Memory-Mapped and Native I/O

Memory-mapped file access does not correspond one-to-one with FileRead calls. Page faults and storage activity can occur outside standard FileRead events.

JNI, native libraries, or custom I/O mechanisms may not be fully represented by standard events. JFR I/O events are not an OS-wide syscall trace.

Therefore, combine JFR with OS-level disk/network metrics and framework telemetry when analyzing applications that use NIO, Netty, native transport, or memory-mapped files.

## 11. Thresholds and Question-Driven Event Filtering

Do not set a 0 ms threshold for all continuous recordings. Instead, start with `default` or `profile` and lower thresholds when needed.

For example, lower the threshold only for socket reads:

~~~bash
jcmd <pid> JFR.start name=socket-detail settings=profile duration=15s filename=socket-detail.jfr jdk.SocketRead#threshold=2ms
~~~

Lower the threshold only for file reads/writes:

~~~bash
jcmd <pid> JFR.start name=file-detail settings=profile duration=15s filename=file-detail.jfr jdk.FileRead#threshold=2ms jdk.FileWrite#threshold=2ms
~~~

You can enable stack traces if the current event settings do not already enable them:

~~~bash
jcmd <pid> JFR.start name=io-stacks settings=profile duration=15s filename=io-stacks.jfr jdk.FileRead#stackTrace=true jdk.FileWrite#stackTrace=true jdk.SocketRead#stackTrace=true jdk.SocketWrite#stackTrace=true
~~~

Enabling stack traces makes recordings much more useful for finding callers, but it can increase overhead and recording size. Collect them only for as long as needed.

## 12. Java 17+ Lab: Generating File I/O and Socket I/O

The following lab creates a temporary file, repeats file write/read operations, and sends data over a loopback socket. The server thread reads data and pauses between sends to produce SocketRead durations long enough to capture in a recording.

Create **IoEventsDemo.java**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

public final class IoEventsDemo {
    public static void main(String[] args) throws Exception {
        int seconds = args.length == 0
                ? 20
                : Integer.parseInt(args[0]);

        if (seconds <= 0) {
            throw new IllegalArgumentException(
                    "seconds must be positive");
        }

        Path file = Files.createTempFile("jfr-io-demo-", ".bin");
        byte[] payload = new byte[16 * 1024];
        Arrays.fill(payload, (byte) 0x5A);

        AtomicReference<IOException> receiverFailure =
                new AtomicReference<>();

        try (ServerSocket server = new ServerSocket(
                0, 50, InetAddress.getLoopbackAddress())) {

            Thread receiver = new Thread(() -> {
                try (Socket accepted = server.accept()) {
                    InputStream input = accepted.getInputStream();
                    byte[] buffer = new byte[8192];

                    while (input.read(buffer) != -1) {
                        // Consume the received bytes.
                    }
                } catch (IOException ex) {
                    receiverFailure.set(ex);
                }
            }, "io-demo-receiver");

            receiver.start();

            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(),
                    server.getLocalPort())) {

                OutputStream socketOutput =
                        client.getOutputStream();

                System.out.println("READY");

                long deadline = System.nanoTime()
                        + seconds * 1_000_000_000L;

                while (System.nanoTime() < deadline) {
                    try (OutputStream output =
                            Files.newOutputStream(file)) {
                        output.write(payload);
                    }

                    try (InputStream input =
                            Files.newInputStream(file)) {
                        byte[] buffer = new byte[8192];

                        while (input.read(buffer) != -1) {
                            // Consume the file bytes.
                        }
                    }

                    Thread.sleep(30);
                    socketOutput.write(payload);
                    socketOutput.flush();
                }

                client.shutdownOutput();
            }

            receiver.join();
        } finally {
            Files.deleteIfExists(file);
        }

        if (receiverFailure.get() != null) {
            throw receiverFailure.get();
        }

        System.out.println("DONE");
    }
}
~~~

Compile:

~~~bash
javac --release 17 IoEventsDemo.java
~~~

Run the program in the first terminal:

~~~bash
java IoEventsDemo 20
~~~

Exact stdout:

~~~text
READY
DONE
~~~

`READY` appears right before the I/O loop. `DONE` appears after the program finishes running for the specified duration. The temporary file path is created automatically by the JVM and deleted when the program exits.

### Starting the Recording from a Second Terminal

Find the PID:

~~~bash
jps -l
~~~

Locate the `IoEventsDemo` line, then start a 10-second recording with a 0 ms threshold:

~~~bash
jcmd <pid> JFR.start name=io-lab settings=profile duration=10s filename=io-lab.jfr jdk.FileRead#threshold=0ms jdk.FileWrite#threshold=0ms jdk.SocketRead#threshold=0ms jdk.SocketWrite#threshold=0ms
~~~

Check status:

~~~bash
jcmd <pid> JFR.check
~~~

After the recording finishes:

~~~bash
jfr summary io-lab.jfr
~~~

Inspect the views:

~~~bash
jfr view file-reads-by-path io-lab.jfr
jfr view file-writes-by-path io-lab.jfr
jfr view socket-reads-by-host io-lab.jfr
jfr view socket-writes-by-host io-lab.jfr
jfr view latencies-by-type io-lab.jfr
~~~

Print detailed events:

~~~bash
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite io-lab.jfr
~~~

Results may vary depending on the JDK, operating system, filesystem, and network stack. SocketRead typically has a longer duration because the receiver thread waits 30 ms before the client sends data. FileRead/FileWrite and SocketWrite can be very short; the 0 ms threshold increases the likelihood of capturing them.

If no events appear, verify that the events are enabled in the recording settings, check the threshold, PID, attach permissions, and JDK version. Do not treat the exact event count as fixed because the runtime may perform additional I/O operations.

## 13. Reading the Lab Results

### File Events

Look for paths containing the `jfr-io-demo` prefix. FileWrite and FileRead events show the byte count and operation duration.

If many events have very low durations, it indicates that file operations complete quickly in your current local environment. Do not assume production storage will have the same latency.

### Socket Events

Look for the loopback host and the dynamically assigned ServerSocket port. SocketRead on the receiver thread may have a duration approximately equal to the wait interval between client sends.

Port and address values change across runs. Do not treat the port number from an example as a fixed value.

### Stack Traces

Open an event and inspect its stack trace. In this lab, the call path will lead to `FileInputStream`/`FileOutputStream` or `Socket` input/output operations. Stack traces may differ depending on the JDK implementation and how the libraries implement I/O.

## 14. Combining I/O Events with Other Data Sources

I/O events tell you which operation is slow; other data sources help explain why.

| Additional Data | Question to Answer |
|---|---|
| JFR CPU samples | Is the thread consuming CPU or mostly waiting on I/O? |
| Thread states | Is the thread RUNNABLE, WAITING, or BLOCKED? |
| GC events | Do pauses or allocation pressure coincide with slow I/O? |
| Lock events | Did the thread experience lock contention before calling I/O? |
| Application tracing | Which request corresponds to the I/O operation? |
| Server-side tracing | How long did the remote service take to process the request? |
| OS disk metrics | What are the storage latency, queue depth, and throughput? |
| OS network metrics | What are the retransmission, congestion, and interface throughput metrics? |
| Container metrics | Are CPU throttling, disk quotas, or network policies having an impact? |

### Example: Analyzing a Slow API

Suppose a SocketRead to `db.internal:5432` has a high duration.

1. Check the event thread and stack trace to identify the call site.
2. Check timeout and bytesRead.
3. Correlate the same time window with database server metrics.
4. Use distributed tracing to determine query time on the server.
5. Check network latency and connection pool behavior.
6. Determine whether the issue is client wait, network, server processing, or queueing.

Do not increase socket timeouts or retry counts just to mask latency. First identify the root cause and its impact on request concurrency.

## 15. Common Pitfalls When Analyzing I/O Events

### Missing FileRead or FileWrite Events

The operation may be shorter than the threshold, the event may be disabled, file access may go through a native/memory-mapped path, or the recording may not cover the I/O window. Check event settings and lower the threshold in a short recording.

### Missing SocketRead Events

The socket read may be very short, a non-blocking read may return immediately, the event may be below the threshold, or the code may use another native/async path. Check SocketRead event settings and stack traces.

### High SocketRead Duration While Remote Server Logs Look Fast

The client may be waiting for data sent in chunks, network delay, or protocol framing. Compare timestamps on both ends and inspect `bytesRead`/`endOfStream`.

### Low SocketWrite Duration While Requests Remain Slow

The write may only be copying bytes into the kernel buffer. Remote processing and response reading happen in later stages. Use end-to-end tracing and server-side metrics.

### Fast FileWrite While Data Persistence Is Slow

FileWrite does not guarantee that data has been forced to storage. Check FileForce events, `FileChannel.force()`, filesystem behavior, and OS storage metrics.

### Recording Has No Stack Traces

The event settings may not have `stackTrace` enabled, or the event may not be configured to collect stacks. Enable `stackTrace` for the required events in a short recording and measure the overhead.

### JFR Recording Is Too Large

Reduce the duration, raise the threshold, enable only necessary events, or use `maxsize`/`maxage`. Do not leave a 0 ms threshold enabled continuously without evaluating event volume.

### Cannot Connect with jcmd

Verify PID, host, user/group, container namespace, and attach permissions. `jcmd` must run on the same machine as the target JVM with appropriate permissions.

## 16. Security and Privacy of I/O Recordings

Standard I/O events do not record file payloads or socket data, but metadata can still be sensitive:

- Full file paths can reveal usernames, directory structures, and customer names.
- Hostnames, IPs, and ports can reveal internal topology.
- Stack traces can expose packages, classes, and deployment paths.
- Thread names may contain service or tenant names.
- JFR recordings may also contain system properties, JVM flags, and other events depending on settings.

Therefore:

- Store `.jfr` files in directories with restricted access.
- Use appropriate encryption and retention policies.
- Do not send recordings over public channels.
- Redact hostnames, paths, and sensitive details before sharing.
- Do not commit recordings to Git.
- Log who collected the recording, when, host, PID, and purpose.
- Delete recordings once the investigation retention period expires.

## 17. I/O Bottleneck Investigation Workflow

1. Identify the affected service, host, JVM PID, and workload.
2. Record the JDK version, JVM flags, and incident time window.
3. Start a JFR recording with `default` or `profile` settings.
4. If needed, lower the threshold for the relevant I/O events.
5. Use `file-reads-by-path`, `file-writes-by-path`, `socket-reads-by-host`, and `socket-writes-by-host` to find prominent groups.
6. Open individual events to inspect duration, bytes, thread, and stack trace.
7. Separate local I/O duration from end-to-end request latency.
8. Correlate with CPU, GC, locks, OS disk/network, and remote service metrics.
9. Form a testable hypothesis.
10. Change one variable at a time and re-run an equivalent workload.
11. Compare duration, throughput, bytes, request latency, and error rate.
12. Store recordings and reports according to your retention policy.

## 18. I/O Event Checklist

- Confirm the correct JVM, PID, host, and user.
- Check the four events: FileRead, FileWrite, SocketRead, SocketWrite.
- Check thresholds in `default`/`profile`/custom settings.
- Remember that operations shorter than the threshold may not be recorded.
- Inspect duration, bytes, path, or host/port.
- Inspect event thread and stack trace.
- Distinguish FileWrite from FileForce.
- Distinguish SocketWrite from remote acknowledgement.
- Do not treat SocketRead duration as end-to-end request latency.
- Account for blocking, non-blocking, and asynchronous behavior.
- Use the JMC I/O page or `jfr` CLI views.
- Use `jfr print` to inspect raw events.
- Combine OS metrics, distributed tracing, and server-side logs.
- Lower thresholds only for as long as needed.
- Protect paths, hosts, and recording metadata.
- Re-measure after optimization using an equivalent workload.

## 19. Key Terminology

| Term | Meaning |
|---|---|
| I/O event | Event recording an input/output operation |
| JFR | Java Flight Recorder, framework for recording runtime events |
| jdk.FileRead | Event for reading data from a file |
| jdk.FileWrite | Event for writing data to a file |
| jdk.SocketRead | Event for reading data from a socket |
| jdk.SocketWrite | Event for writing data to a socket |
| jdk.FileForce | Event for forcing file updates to storage |
| Duration | How long an event operation takes |
| Threshold | Duration threshold required for an event to be recorded |
| Stack trace | Sequence of method calls leading to an operation |
| Blocking I/O | Operation that may wait until completion or timeout |
| Non-blocking I/O | Operation that may return immediately even when no data is available |
| Asynchronous I/O | I/O that completes asynchronously via callback/future |
| Backpressure | Condition where the receiver or network cannot keep up with the send rate |
| End-of-stream | No more data available to read from the stream |
| JMC | JDK Mission Control, tool for analyzing JFR recordings |
| JFC | JFR recording configuration |
| Distributed tracing | Tracking a single request across multiple services |
| Loopback | Network connection routing back to the local machine |

I/O events in JFR help identify files, endpoints, threads, and call paths associated with slow I/O operations. Check thresholds before interpreting metrics, distinguish operation duration from end-to-end latency, and combine JFR with tracing and OS metrics to find the true root cause.

## References

- Oracle JDK 24 — [Java Flight Recorder](https://docs.oracle.com/en/java/javase/24/jfapi/flight-recorder-api-programmers-guide.pdf)
- Oracle JDK 24 — [The jcmd Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html)
- Oracle JDK 24 — [The jfr Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jfr.html)
- Oracle JDK 24 — [Troubleshooting Guide: Diagnostic Tools](https://docs.oracle.com/en/java/javase/24/troubleshoot/diagnostic-tools.html)
- Oracle — [JDK Mission Control](https://docs.oracle.com/en/java/java-components/jdk-mission-control/index.html)