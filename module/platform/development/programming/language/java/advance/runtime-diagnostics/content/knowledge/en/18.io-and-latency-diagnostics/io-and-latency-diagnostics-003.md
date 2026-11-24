# 18.3 Correlating Threads in Native I/O with Timeout Settings and Data Progress

> **Scope:** I/O and latency diagnostics in Java 17+ applications (HotSpot/JDK), especially when thread dumps show threads in socket read/write, file I/O, or native library paths. The goal is not to label something "hung" from a single stack trace, but to **correlate three sources of evidence simultaneously**: (1) which operation the thread is waiting on, (2) which timeout/deadline is actually in effect at which layer, and (3) whether data is making progress over time.

## 1. Three mandatory questions before drawing conclusions

A thread appearing in `SocketInputStream.read`, `SocketDispatcher.read0`, `NioSocketImpl.timedRead`, `FileDispatcherImpl.read0`, or a JNI/native path **does not by itself prove a deadlock**. The native method may be waiting for the OS to return data, waiting on a network peer, waiting on storage, or reading in a loop with normal progress.

Answer these in order:

1. **What is the thread doing?** Capture multiple timestamped thread dumps, identify the Java thread ID, native thread ID (if available), stack frames, and corresponding connection/dependency. Distinguish socket read, socket write, `connect`, file I/O, selector/poll, TLS handshake, driver/native library calls, and lock waits.
2. **Which timeout actually applies?** Check the **runtime** configuration, scope, and units: TCP connect timeout, socket read timeout, overall business deadline, HTTP request timeout, connection-pool acquire timeout, driver/JDBC timeout, etc. "A timeout is configured" is not enough if it covers a different phase.
3. **Is data making progress?** Compare counters/timestamps at least at two points in time: bytes successfully read/written, completed messages/frames, time of last byte, request/response state, throughput, JFR I/O events, and peer-side metrics. No new bytes is different from "request not yet finished."

**A credible conclusion** must specify all three, for example:

> Thread `gateway-reader-7` is in a socket read to upstream A; the actual read timeout is 0 (infinite), and no business deadline is enforced; over the last 45 seconds `bytesReceived` remained unchanged at 8 KiB. Upstream also sent no new response chunks. This indicates a **suspected missing deadline / peer stopped sending**, not evidence of a Java monitor deadlock.

Conversely, if `bytesReceived` grows steadily and latency is high, seeing the thread frequently in read may reflect a **slow data stream or a large response**, rather than a single stuck read from start to finish.

## 2. Understanding thread states and "native I/O" accurately

### 2.1. `RUNNABLE` does not mean always consuming CPU

`java.lang.Thread.State` is a state reported by the JVM, **not a one-to-one mapping with OS thread state**:

| Java thread state | Typical meaning | Interpretation during I/O diagnostics |
| --- | --- | --- |
| `RUNNABLE` | Eligible to run according to the JVM | May be executing Java/native code **or waiting on an OS resource**; never conclude CPU-bound solely from `RUNNABLE`. |
| `BLOCKED` | Waiting to enter a Java monitor (`synchronized`) | This is monitor lock waiting, **not** an OS-blocked socket read. |
| `WAITING` | Indefinite wait in `wait`, `join`, `park`, etc. | May relate to a pool, condition, queue, or completion; inspect the stack. |
| `TIMED_WAITING` | Timed wait (`sleep`, `wait(timeout)`, `parkNanos`, etc.) | Does not mean socket I/O has a proper timeout configured. |
| `TERMINATED` | Thread has exited | A snapshot after the request finished cannot prove its earlier state. |

A Java thread can report `RUNNABLE` while native code/an OS syscall is waiting for data. Across different JDKs, stacks may show `SocketDispatcher.read0(Native Method)`, `sun.nio.ch.NioSocketImpl.timedRead`, `java.net.Socket$SocketInputStream.read`, or another wrapper class. **Frame names are not a stable contract across JDK/OS versions.**

**Shape illustration only**, not fixed output:

```text
"upstream-reader-7" #47 ...
   java.lang.Thread.State: RUNNABLE
    at sun.nio.ch.SocketDispatcher.read0(Native Method)
    at sun.nio.ch.SocketDispatcher.read(...)
    at java.net.Socket$SocketInputStream.read(...)
    at com.example.UpstreamClient.fetch(...)
```

The key items to identify are **read vs. write**, **where the application called from**, **thread ID/name**, **endpoint**, and **how long it stays there across multiple snapshots**. A single dump only shows state at the sampling instant; it cannot tell whether bytes moved between thread wakeups.

### 2.2. Java thread ID, native TID, and OS state

A HotSpot thread dump may include:

- Java thread name and Java thread ID.
- `nid=...` (native thread ID, typically shown in hex on Linux); formatting varies by tool/version.
- Stack trace, Java state, and lock owners/monitors when present.

When comparing against Linux `top -H`, `ps -L`, `strace`, or `/proc`, **convert/match the TID properly**; do not confuse JVM PID, Java `Thread.threadId()`, and OS thread ID as the same value. The OS may report sleeping/polling while the Java dump reports `RUNNABLE`.

`ThreadInfo.isInNative()` on `ThreadMXBean` indicates whether the Java thread is executing JNI native code by its own definition; it **does not** cover all VM-support code or JIT-generated machine code. Do not use this single boolean as sole proof that a socket is stuck in native I/O.

### 2.3. Platform threads, virtual threads, and asynchronous I/O

On JDK 21+, virtual threads can **unmount from their carrier** when waiting on compatible blocking operations. Thus, a virtual thread waiting on a socket does not necessarily "occupy" an OS thread; traditional thread dumps and OS thread counts may not show the full relationship the way platform threads do.

With NIO/event-loops (`Selector.select`, non-blocking `SocketChannel`), one thread can wait for readiness across **many connections**. Never conclude solely from a `select()` stack that connection X is slow. Correlate with selector key/channel metrics, connection state, and per-request counters.

An SDK/driver may call JNI, native TLS/crypto, a database client, or async I/O underneath. If the stack stops at a Java wrapper, investigation may require library traces/logs, a native profiler, TCP metrics, or driver configuration. **Do not assume every native I/O path honors `Socket#setSoTimeout`.**

## 3. Timeout map: different timeouts do not substitute for one another

Names containing "timeout" sound similar but bound **different stages**. Always record the **configuration source**, **effective value**, **unit**, **covered phase**, and **behavior upon expiration**.

| Timeout/deadline | Covered phase | Common Java/API mechanisms | What it does NOT guarantee |
| --- | --- | --- | --- |
| **TCP connect timeout** | Establishing the TCP connection | `Socket.connect(endpoint, timeoutMs)`; `HttpClient.Builder.connectTimeout` for **new connections** | Does not bound server response time, body reading, connection-pool acquisition, or post-connect work. |
| **Socket read timeout** | A single blocking read on a `Socket` input stream | `Socket.setSoTimeout(ms)` and `InputStream.read` | Does not automatically cap **the entire response** across multiple reads; does not bound connect or write. |
| **Socket accept timeout** | Waiting for a new connection on a server socket | `ServerSocket.setSoTimeout(ms)` | Does not bound reading the body from a client after accept. |
| **HTTP request timeout** | Request/response as defined by the library | `HttpRequest.Builder.timeout(Duration)` | Does not automatically ensure all downstream processing/user streaming code is bounded by one business deadline. |
| **Pool acquire timeout** | Waiting to borrow a connection/client resource from a pool | HTTP/JDBC pool-specific options | Does not bound I/O after borrowing the connection. |
| **TLS handshake timeout** | TLS negotiation phase | Depends on API/client/driver and how it uses sockets | TCP connect success does not mean TLS completed. |
| **Query/driver socket timeout** | SQL commands/driver network operations | `Statement.setQueryTimeout`, JDBC driver socket/network options | A query timeout does not cover pool wait, app queues, or every native read. |
| **Overall operation deadline** | Start to final business outcome | App context/deadline, tracing/client policies, custom `System.nanoTime()` | If checked only between I/O calls, a single un-timed blocking call can still overshoot. |
| **File I/O deadline** | Reading/writing storage | FileChannel, async I/O, SDK-specific APIs | Java file read/write **has no** universal equivalent to `Socket.setSoTimeout` across all filesystems. |

### 3.1. `Socket.connect` vs. `Socket.setSoTimeout`

With blocking `java.net.Socket`:

```java
Socket socket = new Socket();
socket.connect(new InetSocketAddress("example.invalid", 443), 1000);
socket.setSoTimeout(500);
```

This is an **illustrative configuration snippet**, not a standalone program to connect to a real host. `1000` ms limits **connect**, and `500` ms limits **a single blocking read** on the socket's `InputStream`. `setSoTimeout` must be set **before** starting a read to take effect as intended.

Per the API, `setSoTimeout(0)` means **infinite**; a read exceeding a positive timeout throws `SocketTimeoutException`, yet **the socket remains valid** at the API level. Whether to continue reading or close/retry depends on protocol and request state. Do not assume a timeout discards previously received data, and do not assume retrying a read is safe for all transactions.

**Important:** `SO_TIMEOUT` applies per blocking read, **not to the total time to finish an entire message**. If the peer sends 1 byte every 400 ms and the socket read timeout is 500 ms, successive `read()` calls can keep completing while the overall response drags on for minutes. A separate **overall deadline** is needed to guard against this "trickle" pattern.

A non-blocking `SocketChannel` with a `Selector` uses its own readiness model. Do not assume `Socket.setSoTimeout` applies to every NIO variant, async stream, or SDK; verify the exact API the code calls.

### 3.2. HTTP client: settings that look present but cover the wrong phase

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofMillis(500))
        .build();

HttpRequest request = HttpRequest.newBuilder(URI.create("https://example.com"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();
```

This is an illustrative snippet (requiring `import java.net.URI;`, `java.net.http.*;`, `java.time.Duration;`, and an enclosing class/method). `HttpClient`'s `connectTimeout` is used only when **creating a new connection**; it has no effect on a reused connection. `HttpRequest.timeout` bounds waiting for the response per the `HttpRequest`/HTTP client contract and can produce an `HttpTimeoutException`.

Do not infer from `connectTimeout=500ms` that the request will complete in 500 ms. Nor should you assume the HTTP client timeout covers asynchronous work **after** the response is handed to a consumer, parsing/transformation logic, or application-level retries. Verify actual lifecycle behavior for your client and body handler.

If a request retries 3 times with a 2-second timeout each, **total time** also includes backoff, pool wait, and serialization and can far exceed 2 seconds. Maintain an operation-level deadline (e.g., a 3-second budget) and pass the remaining budget down to each attempt.

### 3.3. Write timeouts and other limits

`Socket.setSoTimeout` is a **read timeout**, not a way to bound a blocking `OutputStream.write`. Writing large data to a TCP socket when the peer stops reading can hit backpressure/full send buffers; to bound **the entire send operation**, use an API/client with supported deadlines/cancellation or design non-blocking channels/selectors with explicit policies.

Even when `write()` returns successfully, data may only have been copied into local/kernel buffers, **not** received, parsed, or processed by the peer. `bytesWritten` in JFR or the application therefore differs from business acknowledgment.

For DB/network drivers, TLS, DNS, pool acquire, or native libraries: inspect each subsystem's timeouts and log the final effective configuration. Never configure a value in one layer and assume it propagates automatically to another.

## 4. How should "data progress" be measured?

### 4.1. Do not look only at live threads or `ESTABLISHED` connections

A TCP connection in `ESTABLISHED` state can go long periods without receiving new bytes; a `RUNNABLE` thread can be waiting on read; and a server can keep sending tiny chunks without completing a response. At least four independent signals are needed:

1. **`bytesReceived`**: accumulate bytes **actually returned successfully** by read, not bytes *requested* into a buffer.
2. **`lastByteReceivedAt`**: monotonic timestamp (`System.nanoTime()`) when `n > 0`; inspect `now - lastByteReceivedAt` to detect idle stalls.
3. **`framesCompleted`/`recordsCompleted`**: number of messages or responses completed after valid protocol parsing; receiving 1 MiB does **not** prove a valid response has finished.
4. **`operationStartedAt`, `deadline`, `stage`, `outcome`**: total elapsed time, remaining deadline, and current stage (connect, handshake, read headers, read body, decode, persist, ...).

With `InputStream.read(byte[])`: a **positive** return value means that many bytes were received; `-1` means end-of-stream (EOF). If called with a zero-length buffer, the API may return `0` with **no progress**. Never add `0` or `-1` to `bytesReceived`. With non-blocking `SocketChannel.read`, `0` can also mean no bytes were available on that poll.

When `read()` times out, **earlier reads** may already have received valid data; a timeout does not erase prior progress. To support recovery/retry, the application must track parser state, offsets, correlation IDs, and idempotency of subsequent operations.

### 4.2. What can you compute from two snapshots?

Illustrative example (same operation, same socket, measured with a monotonic clock):

| Timestamp | `bytesReceived` | `framesCompleted` | `lastByteAge` | Most recent stack |
| --- | ---: | ---: | ---: | --- |
| 10:00:00 | 8192 | 0 | 2 s | `SocketInputStream.read` |
| 10:00:10 | 8192 | 0 | 12 s | `SocketInputStream.read` |
| 10:00:20 | 8192 | 0 | 22 s | `SocketInputStream.read` |

**Assessment:** the same request received no new bytes for 20 seconds; the thread was repeatedly sampled on the read path; check read timeout, end-to-end deadline, peer state, and network. **You cannot yet** determine which side caused the stall without peer-side data.

Another example:

| Timestamp | `bytesReceived` | `framesCompleted` | `lastByteAge` | Most recent stack |
| --- | ---: | ---: | ---: | --- |
| 10:00:00 | 8192 | 0 | 0.2 s | `SocketInputStream.read` |
| 10:00:10 | 17408 | 0 | 0.4 s | `SocketInputStream.read` |
| 10:00:20 | 26624 | 0 | 0.1 s | `SocketInputStream.read` |

**Assessment:** bytes are progressing (~0.9 KiB/s), yet the frame/response is still incomplete; suspect low throughput, oversized payload, backpressure, framing/protocol issues, or a drip-feeding peer. Raising the read timeout will not fix the latency cause; an overall deadline and throughput/idle thresholds may help.

**Distinguish `bytesRead` from usable application bytes:** TLS/compression/protocol framing can make socket-layer byte counts differ from decoded application bytes. Metrics must specify which layer they measure; avoid summing across layers and double counting.

### 4.3. Numbers worth putting in telemetry

An **illustrative** event/log template containing no payload:

```json
{
  "operation": "fetch-inventory",
  "correlationCode": "opaque-7F3B",
  "stage": "READ_BODY",
  "elapsedMs": 1480,
  "remainingDeadlineMs": 520,
  "configuredReadTimeoutMs": 500,
  "bytesReceived": 8192,
  "expectedBytes": 32768,
  "lastByteAgeMs": 970,
  "framesCompleted": 0,
  "outcome": "PENDING"
}
```

Never log full URLs, query strings, auth headers, request/response bodies, or PII just for debugging. `expectedBytes` is reliable only when the protocol has explicit framing/length and is not compressed/streamed under different semantics; if unknown, record `unknown` instead of guessing.

**Control cardinality:** `operation`/`stage`/`outcome` have bounded value sets; `correlationCode` belongs in traces/logs/JFR with proper retention and access controls, **not** as a label on time-series metrics. Do not emit a log or event per byte; emit progress by interval, byte threshold, request completion, or timeout/error.

## 5. Collecting evidence: thread dumps + timeouts + JFR + OS

### 5.1. Capturing multiple timestamped thread dumps

When the process is alive and attach permissions exist:

```bash
jcmd -l
jcmd <PID> Thread.print -l > threads-t0.txt
sleep 5
jcmd <PID> Thread.print -l > threads-t1.txt
sleep 5
jcmd <PID> Thread.print -l > threads-t2.txt
```

Replace `<PID>` with the real JVM PID. Thread dump files should include timestamps recorded by the collection script; naming them `t0`/`t1` does **not** guarantee they are exactly 5 seconds apart if the host is overloaded.

Analyze by **Java thread ID/native ID**, not just thread name: a thread pool may switch workers or requests between captures. Inspect application frames (`service`, `client`, `driver`) to see **who invoked the read**, and get peer addresses from configuration/metrics/traces. Frames such as `Unsafe.park`, `LockSupport.park`, `Selector.select`, and `SocketDispatcher.read0` carry distinct meanings and should not be lumped together as "native I/O stuck."

In JVMs where attaching is blocked by permissions/namespaces, use platform-authorized mechanisms (`jstack`/signal support/diagnostic endpoints/runtime observability). Never grant ad-hoc admin/ptrace privileges in production without authorization; dumping also carries overhead and can expose sensitive data.

### 5.2. JFR: inspecting **completed and recorded I/O**

JDK JFR provides useful event types:

- `jdk.SocketRead`: duration, remote host/address/port, `timeout` (per JVM schema), `bytesRead`, `endOfStream`.
- `jdk.SocketWrite`: duration, remote endpoint, and `bytesWritten`.
- `jdk.FileRead`: duration, path, `bytesRead`, `endOfFile`.
- `jdk.FileWrite`: duration, path, and `bytesWritten`.

**Check the actual schema of the running JDK**:

```bash
jfr metadata --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite
```

`jdk.SocketRead.timeout` is the timeout value instrumented/recorded in the event, **not** equal to the actual duration of the read. `bytesRead` is the byte count of **that single read event**, not the request's total `bytesReceived`. `endOfStream=true` is distinct from `bytesRead=0`.

A `SocketRead` event typically appears when the read path is **recorded by the JDK after a call completes** and meets the threshold. **Never infer "no SocketRead event ⇒ no read occurred"**: the recording may have the event disabled, filtered by threshold, dropped, using an uninstrumented implementation, or throwing a timeout/exception may not emit an event as expected. In a real check on JDK 24, a blocking read throwing `SocketTimeoutException` produced zero `jdk.SocketRead` events, whereas a successful 251 ms read was recorded when the event was explicitly enabled.

### 5.3. Configuring a targeted recording

You can use `jfr configure` to generate a custom settings file (keeping other defaults):

```bash
jfr configure --output io.jfc \
  'jdk.SocketRead#enabled=true' \
  'jdk.SocketRead#threshold=5ms' \
  'jdk.SocketWrite#enabled=true' \
  'jdk.SocketWrite#threshold=5ms' \
  'jdk.FileRead#enabled=true' \
  'jdk.FileRead#threshold=5ms' \
  'jdk.FileWrite#enabled=true' \
  'jdk.FileWrite#threshold=5ms'
```

This command creates `io.jfc` **without starting a recording**. A 5 ms threshold is an example for spotting slow I/O; it intentionally omits fast operations. Lower the threshold to `0` only in a lab or controlled investigation window when every instrumented I/O call must be captured; event volume and overhead will increase.

Start a recording at JVM launch:

```bash
java -XX:StartFlightRecording=name=io,settings=io.jfc,disk=true,filename=io.jfr,dumponexit=true \
  -jar app.jar
```

`app.jar` is an **illustrative** application name. On a running JVM with attach permissions:

```bash
jcmd <PID> JFR.start name=io settings=io.jfc duration=2m filename=io-snapshot.jfr
jcmd <PID> JFR.check name=io verbose=true
```

Inspect the recording with:

```bash
jfr summary io-snapshot.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite io-snapshot.jfr
```

If recording differently, pass the actual `.jfr` path. `jfr summary` gives event counts per type; `jfr print` shows details to group by host, port, thread, duration/bytes. You can also open JFR in JDK Mission Control (JMC) to correlate timelines.

**Warning:** If `threshold=20 ms`, a fast read returning 16 KiB may not be recorded, while a 300 ms read receiving 0 bytes might also not appear if the error path emits no event. Therefore, **do not treat summed JFR `bytesRead` as exact total traffic**, and never treat missing events as proof of no I/O. Combine with application byte counters and network/driver metrics.

### 5.4. OS and peer-side evidence

On Linux, for example:

```bash
ps -L -p <PID> -o pid,tid,stat,wchan:32,comm
ss -tinp
lsof -nP -p <PID>
```

`ps -L` helps correlate OS TID and wait channel where available; `ss` provides socket states, queues, and TCP info; `lsof` lists open file descriptors/sockets. Each command has its own scope and privilege requirements; do not interpret `ESTABLISHED` as the app actively receiving data or `Recv-Q=0` as the peer being "dead."

When syscall/network traces (`strace`, eBPF, packet captures) are needed, obtain proper operational approval; they incur overhead and can capture sensitive payloads or addresses. On Windows/macOS, choose the corresponding OS tools. When investigating both ends of a connection, account for clock drift/synchronization; distinguish timestamps from OS captures, app logs, and JFR events.

## 6. Java 17+ lab: read timeout occurs even after receiving partial data

This lab runs completely on loopback; **no external server is needed**. A server thread sends `"HE"`, holds `"LLO"` until the client hits a read timeout, and then sends the remainder. It demonstrates three points:

1. A **single read** timeout does not discard bytes received in earlier reads.
2. `SO_TIMEOUT` is not an overall deadline; the socket remains usable after a timeout.
3. Concluding whether progress exists requires measuring bytes across **multiple reads** and checking whether the protocol completed.

### 6.1. Create `NativeIoProgressLab.java`

```java
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.SocketTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NativeIoProgressLab {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        CountDownLatch allowTail = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try (ServerSocket listener = new ServerSocket(0, 1, loopback)) {
            Future<?> peer = pool.submit(() -> {
                try (Socket socket = listener.accept()) {
                    OutputStream out = socket.getOutputStream();
                    out.write("HE".getBytes(StandardCharsets.US_ASCII));
                    out.flush();
                    allowTail.await();
                    out.write("LLO".getBytes(StandardCharsets.US_ASCII));
                    out.flush();
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress(loopback, listener.getLocalPort()), 1000);
                client.setSoTimeout(2000);
                InputStream in = client.getInputStream();

                byte[] first = in.readNBytes(2);
                if (first.length != 2) throw new IllegalStateException("missing first part");
                int bytesReceived = first.length;
                System.out.println("received=" + new String(first, StandardCharsets.US_ASCII)
                    + " bytes=" + bytesReceived);

                client.setSoTimeout(args.length > 0 && args[0].equals("observe") ? 10000 : 150);
                try {
                    int b = in.read();
                    throw new IllegalStateException("expected timeout, read=" + b);
                } catch (SocketTimeoutException expected) {
                    System.out.println("read-timeout bytes=" + bytesReceived);
                }

                allowTail.countDown();
                client.setSoTimeout(2000);
                byte[] tail = in.readNBytes(3);
                if (tail.length != 3) throw new IllegalStateException("missing tail");
                bytesReceived += tail.length;
                System.out.println("received=" +
                    new String(first, StandardCharsets.US_ASCII) +
                    new String(tail, StandardCharsets.US_ASCII) +
                    " bytes=" + bytesReceived);
            } finally {
                allowTail.countDown();
            }
            peer.get(5, TimeUnit.SECONDS);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

**Detailed explanation:**

- `ServerSocket` binds loopback on port 0: the OS picks a free port; nothing is exposed to external networks.
- The `pool` thread acts as the peer. It writes **exactly 2 bytes** `"HE"`, then waits on `allowTail` before writing `"LLO"`. Thus the client cannot receive the tail before the signal fires.
- The initial `readNBytes(2)` requests 2 bytes to demonstrate the prefix; this is a lab simplification. In production, read streams in a loop and inspect each `read` alongside a deadline so progress remains observable.
- The client sets `SO_TIMEOUT=150` ms for the next read. Because the server deliberately sends no new bytes, `SocketTimeoutException` occurs.
- After the timeout, `bytesReceived` is still 2; the server is allowed to send the rest and the client advances it to 5. **That is observable progress**, unlike having received zero bytes.
- With the `observe` argument, the second read's timeout increases to 10 seconds to give time to capture a thread dump **while the client is inside read**. This is not a production setting.
- `peer.get` verifies the server threw no errors in the lab, and `finally` ensures the server is never left waiting indefinitely on the latch.

### 6.2. Compiling, running, and reading stdout

```bash
javac NativeIoProgressLab.java
java NativeIoProgressLab
```

**Exact program stdout** (compiled/run on OpenJDK 24):

```text
received=HE bytes=2
read-timeout bytes=2
received=HELLO bytes=5
```

Note: `Thread.sleep` is not used for server timing in the demo; `CountDownLatch` ensures the server waits until the client has observed the timeout. Wall timings can vary with OS scheduling, but the order and content of these lines remain stable when the program succeeds.

Try observing a dump:

```bash
java NativeIoProgressLab observe
```

In a second terminal **while the 10-second read is waiting**:

```bash
jcmd -l
jcmd <PID> Thread.print -l
```

Locate the `"main"` thread and stack frames in `InputStream.read`/socket or NIO depending on JDK. A snapshot taken too late might catch the thread after the read finishes; extend the lab's observation window deliberately if needed. **Java state can be `RUNNABLE` even though the thread is waiting on OS I/O.** Never treat a single late dump as root-cause proof.

### 6.3. Creating a JFR recording and checking actual events

Use custom settings if you want to see short I/O calls in the lab:

```bash
jfr configure --output io.jfc \
  'jdk.SocketRead#enabled=true' \
  'jdk.SocketRead#threshold=0' \
  'jdk.SocketWrite#enabled=true' \
  'jdk.SocketWrite#threshold=0'
```

```bash
java -XX:StartFlightRecording=name=lab,settings=io.jfc,filename=io.jfr,dumponexit=true \
  NativeIoProgressLab
jfr summary io.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite io.jfr
```

`jfr configure` and the flags above are real JDK commands. When running in Windows PowerShell, replace the Bash line continuations (`\`) with a single line or PowerShell's line-continuation character; do not paste multiline Bash commands directly into PowerShell.

**Reading the results:** I/O events report instrumented read/write calls with `duration`, `timeout`, `bytesRead` or `bytesWritten`, and endpoint per schema. **Event counts are not fixed across JVMs/JDKs**; never assert that every `read` call throwing an exception emits a `SocketRead`. A test on OpenJDK 24 with a read timeout actually produced **0** `SocketRead` events for the exception branch, even though Java caught the timeout as expected.

This is why **application-level progress tracking** is needed alongside JFR: record `bytesReceived`/`lastByteAt` in code (with sensible sampling), then align on timestamps with JFR events, thread dumps, and socket stats.

## 7. Designing an overall deadline to prevent "drip feed"

A production system should separate:

- **Connect budget**: maximum time to establish a connection.
- **Read idle timeout**: maximum time for one blocking read waiting for new bytes.
- **Overall deadline**: from operation start until the result must complete or abort.
- **Progress/throughput expectation**: after each interval, meaningful bytes/frames or minimum throughput must arrive, depending on protocol.

Measure elapsed time with a monotonic clock like `System.nanoTime()`, not wall clock from `System.currentTimeMillis()`, because NTP/clock adjustments can jump wall time.

### 7.1. Illustrative code: one deadline spanning multiple reads

This is an **illustrative Java method**, not a standalone runnable file. It requires `import java.io.*;`, `import java.net.*;`, `import java.util.concurrent.TimeUnit;` and belongs inside an enclosing class:

```java
static byte[] readExactlyBeforeDeadline(
        Socket socket, int expectedBytes, long maxMillis) throws IOException {
    if (expectedBytes < 0 || maxMillis <= 0) {
        throw new IllegalArgumentException("invalid limit");
    }

    byte[] result = new byte[expectedBytes];
    int received = 0;
    long deadline = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(maxMillis);
    InputStream in = socket.getInputStream();

    while (received < expectedBytes) {
        long remainingNanos = deadline - System.nanoTime();
        if (remainingNanos <= 0) {
            throw new SocketTimeoutException("overall deadline exceeded");
        }

        long remainingMs = TimeUnit.NANOSECONDS.toMillis(remainingNanos);
        int timeoutMs = (int) Math.max(1L, Math.min(500L, remainingMs));
        socket.setSoTimeout(timeoutMs);

        int n = in.read(result, received, expectedBytes - received);
        if (n == -1) {
            throw new EOFException("unexpected EOF after " + received + " bytes");
        }
        if (n > 0) {
            received += n;
            // Record lastProgressAt/bytesReceived metrics here; do not log the body.
        }
    }
    return result;
}
```

**What does this solve?** After each successful `read`, it recomputes **remaining time** instead of granting a fresh fixed timeout indefinitely. `setSoTimeout` is capped to `min(per-read cap, remaining deadline)`, preventing a drip-feeding peer from extending the operation endlessly. Time spent in phases **before/after** this method must still be counted in the business operation's deadline if end-to-end bounds are required.

**Method limitations:**

- `expectedBytes` should only be passed when the protocol has a **validated** message length—never allocate arrays from an untrusted large client length that could trigger OOM; production code should enforce a max message size and use a streaming parser.
- `maxMillis` must be within a reasonable range; guard against nanosecond addition overflow for huge deadlines.
- Millisecond rounding and OS scheduling can shift timeouts slightly; this is not a hard real-time deadline.
- If a native API/driver **does not** honor this timeout mechanism, setting `Socket` options will not help; use the appropriate API.
- If the request cannot be safely retried, catching a timeout is only for recording outcome/cleanup; do not auto-retry transactions with unknown side effects.
- `readExactlyBeforeDeadline` is a single-connection/synchronous pattern; concurrent clients need pool/async integration, cancellation, and explicit resource lifecycle management.

### 7.2. Budgets must flow across the entire request

Illustrative example (not optimal defaults):

| Stage | Independent budget | Signals to measure |
| --- | ---: | --- |
| Pool acquire | 100 ms | pool wait, queue depth, timeout counter |
| TCP connect | 300 ms | connect duration, failure rate, reused/new |
| TLS handshake | 300 ms | handshake duration, timeouts/errors |
| Read | Up to 500 ms per blocking read | `bytesReceived`, `lastByteAge`, bytes/sec |
| **Entire operation** | **2 s** | `startedAt`, `deadlineRemaining`, final outcome |

Do not simply add these numbers to estimate max latency: one operation may involve multiple reads, retries, redirects, and queuing. **The 2-second overall deadline must propagate down into each phase**; each phase receives the remaining budget and may need to shorten or abort early. If an upstream server or gateway enforces a 1-second timeout, a 10-second client timeout only pins threads waiting on a request that has already failed upstream.

Also never call `Future.get(2, SECONDS)` and assume that "cancels I/O." Timing out `get` only makes **the caller stop waiting**; the underlying task/I/O may keep running. Check the API contract, how to cancel/close the connection, and how resources are released.

## 8. Field correlation: scenario matrix

| Thread evidence | Timeout evidence | Progress evidence | Reasonable investigation path |
| --- | --- | --- | --- |
| Multiple dumps in `SocketInputStream.read`/native read; low CPU | `SO_TIMEOUT=0`, no overall deadline | Bytes unchanged for 30 s | Missing read timeout/deadline or silent peer; inspect upstream/socket stats, add bounded deadlines. |
| Dumps continuously in read | 500 ms per read, no overall deadline | Bytes grow by a few bytes every 400 ms | "Drip-feed": individual reads do not time out yet total response drags; add overall deadline/min throughput policy. |
| Repeated socket reads, slow request | Reasonable read timeout | Bytes grow rapidly, frame still incomplete | Large response, framing/content-length/chunked parsing, downstream decode, or server streaming; do not call it deadlock. |
| Stack in `SocketDispatcher.write`/write path | Only read timeout configured | Bytes sent stagnant or large Send-Q | Check backpressure, unread peer, client/channel write timeout/cancellation. |
| Stack in `Selector.select` | Per-request timeout in app | Some channels have bytes, others do not | Event loop serving many connections; need per-channel metrics, do not blame all latency on the selector thread. |
| Worker waiting on pool/queue, never reaches read | Only connect/read timeouts configured | Byte progress = 0 because no socket acquired | Pool saturation or upstream concurrency/bulkhead; network timeouts do not cover queue wait. |
| Thread in TLS/handshake | Short connect timeout | TCP connected but no app bytes | Check handshake deadline, certificates, peer TLS, protocol negotiation; TCP connect success is not completion. |
| Thread in file/native driver read | Network `SO_TIMEOUT` set | File I/O counters/offsets unchanged | Unrelated to socket timeout; check storage, filesystem, JNI/driver-specific timeouts. |
| App timeout returned yet thread remains in native call | Caller `Future.get` timed out | Thread/FD still alive, no progress | Caller timeout does not guarantee cancellation; verify close/cancel semantics and leaked tasks. |
| Many `RUNNABLE` threads in dump but low process CPU | Timeouts appear adequate | Bytes rising steadily | Normal I/O activity or slow throughput; avoid concluding CPU runaway solely from `RUNNABLE`. |

### Case A — Endpoint stops sending data

**Evidence:** thread dumps t0/t1/t2 share the same `read` stack, `bytesReceived` unchanged, `lastByteAge` climbs, TCP remains `ESTABLISHED`, JFR has no new completed reads. Timeout setting = 0 or larger than upstream budget.

**Action:** collect peer state, connection mapping, server logs, proxy/gateway timeouts; set an appropriate read timeout and **overall deadline**. After timeout, clean up/reuse connections according to protocol/SDK rules; do not retry non-idempotent requests without knowing server outcome.

**What NOT to conclude:** "JFR shows no `SocketRead`, so no I/O is happening"—a pending read or exception path may emit no event.

### Case B — Reading steadily, yet request never finishes

**Evidence:** app counters rise, JFR has many small `SocketRead`s, random thread dumps catch reads, total latency breaches SLO. `framesCompleted=0`, `expectedBytes` is large or unknown.

**Action:** inspect framing, chunked encoding, server-side serialization, actual payload being parsed, compression ratio, and network throughput; choose appropriate streaming and bounds. A per-read timeout alone will not cap total duration if bytes keep arriving just in time.

### Case C — Timeout configured on HTTP client, yet app still waits on pool

**Evidence:** thread stack is in acquire queue/lock with no socket read; client set `connectTimeout` 500 ms, yet total requests wait seconds for the connection pool. Active connections are at maximum.

**Action:** check pool acquire timeout, queued tasks, busy connections, and total deadline; measure `poolWaitMs`. Raising or tuning `SO_TIMEOUT` will not help because I/O has not started yet.

### Case D — Blocked on write, peer not reading

**Evidence:** thread is in socket write, Send-Q grows or `bytesWritten` stalls, while a 300 ms read timeout is enabled. JFR `SocketWrite` may show a slow write only after it finishes.

**Action:** evaluate backpressure, protocol flow control, server receive rate, and outbound write deadline. `setSoTimeout` does not apply to writes. Local write success does not prove the peer processed the data.

### Case E — File I/O or native library

**Evidence:** thread dump in `FileDispatcherImpl.read0`/JNI/native call, file offset unchanged, storage latency rising; network timeouts are valid but irrelevant.

**Action:** use `jdk.FileRead/FileWrite` events, filesystem metrics, disk queue/latency, mount/NFS state, or library docs; check specific cancel/interrupt semantics. `Thread.State.RUNNABLE` is not enough to conclude file I/O is deadlocked.

### Case F — Virtual threads or event loops

**Evidence:** many virtual threads waiting on sockets while OS thread count stays relatively low; or a selector thread serving many channels. A single OS snapshot hides the call path of individual requests.

**Action:** add virtual-thread-aware thread dumps / matching JFR events, per-request correlation, deadlines, and byte progress; do not multiply OS thread count by request count to infer "blocked threads."

## 9. Sequence of actions during an ongoing incident

1. **Isolate the request/operation:** safe correlation ID, endpoint/dependency, effective timeouts, total latency, start time. Verify same PID/JDK/host/container.
2. **Capture at least 2–3 snapshots** (e.g., 5 seconds apart): timestamped thread dumps, active request counts, byte progress, `lastByteAge`, pool stats, OS sockets/TCP queues, logs.
3. **Map thread → operation → endpoint:** Java stack and app frames, Java thread ID/native TID, connection/FD, and correlation ID. With async/virtual threads, thread name alone is insufficient.
4. **Build an effective timeout table:** connect, pool acquire, TLS, read, write, request/overall deadline, retries. Check for `0`/unset and units; document each phase.
5. **Cross-check JFR:** enable/check `SocketRead`, `SocketWrite`, `FileRead`, `FileWrite`; review thresholds and `duration`, `timeout`, `bytesRead`, `bytesWritten`. Do not substitute JFR for application counters.
6. **Classify:** no progress, slow progress, transfer complete but business logic unfinished, waiting on pool/selector, file/native stall, or genuine CPU/lock issue.
7. **Apply controlled mitigation:** timeouts/deadlines at the right layer, bounded concurrency, proper cancel/close semantics, backpressure, peer fixes, safe retries; avoid blindly raising timeouts everywhere without knowing the cause.
8. **Verify after the fix:** same load and duration; measure success/error rate, timeout rate, p95/p99 latency, bytes/s, in-flight requests, JFR I/O durations, pool waits, and thread snapshots. Never declare fixed just because error logs vanished.

**Conclusion template usable in an engineering report:**

```text
Time window: 10:00:00–10:00:30 UTC
JVM: pid ..., JDK ..., service ...
Operation: fetch-inventory, correlation: opaque-...
Thread: javaId ..., nativeTID ..., stack: SocketInputStream.read(...)
Configured: connect=300 ms, read=0 ms, request-deadline=unset
Progress: bytesReceived=8192 at both t0 and t1; framesCompleted=0
Peer evidence: upstream no response-body bytes since 09:59:58
Interpretation: likely stalled peer read, unbounded by current read timeout
Mitigation: read idle timeout 500 ms + operation deadline 2 s
Verification: compare p99, timeout/error, throughput and partial-read behavior
```

This is an **illustrative template**, not numbers from a real system. The final report should state the confidence level of each conclusion—for instance "suspected" when peer logs are missing.

## 10. Common mistakes

1. **"`RUNNABLE` means 100% CPU."** False: Java state differs from OS scheduling; native I/O can block in the kernel.
2. **"A thread in `SocketDispatcher.read0` is definitely deadlocked."** False: distinguish blocked I/O from Java monitor deadlock and check multiple snapshots/progress.
3. **"Having a connect timeout means the request has a total timeout."** False: connect covers only connection setup, and pooling/reuse changes when it applies.
4. **"With `SO_TIMEOUT=500`, the whole response takes at most 500 ms."** False: that timeout applies **per blocking read**; multi-read responses can still drag on.
5. **"`SO_TIMEOUT` also bounds `write()`."** False: read timeout and write/backpressure are separate.
6. **"`read()` returns the requested number of bytes."** False: streams may return fewer; count the actual returned `n>0`.
7. **"One new byte means the request is healthy."** False: a peer may drip-feed, framing may stay incomplete, and the overall SLA may already be breached.
8. **"Successful `bytesWritten` means the server processed it."** False: bytes may only have entered the local network stack; business acknowledgment is required.
9. **"No `SocketRead` event in JFR means no reads happened."** False: thresholds, disabled settings, exceptions, incomplete calls, or uninstrumented paths can omit events.
10. **"`SocketRead.timeout` in JFR is the actual duration."** False: the event records configured `timeout` and `duration` separately.
11. **"One thread dump proves a request hung for 30 seconds."** False: a single snapshot has no time dimension; timestamps/counters are required.
12. **"`Future.get` timeout cancelled the native I/O."** False: `get` timing out does not guarantee the task stopped; proper API cancellation/resource closing is required.
13. **"TCP `ESTABLISHED` means data progress is occurring."** False: a socket can stay open with zero new payload.
14. **"Raising timeouts solves all I/O latency."** False: it can merely increase in-flight requests and mask peer, pool, or retry issues.
15. **"Byte counts from TLS/socket/body decoder can be added together."** False: those layers can count the same data in different representations.
16. **"A virtual thread waiting on a socket always pins an OS thread."** False: compatible blocking I/O generally unmounts; use observability tools suited to your JDK.

## 11. Short checklist before concluding

- [ ] Know **PID, JDK/OS, Java thread ID, native TID**, application stack, and actual endpoint.
- [ ] Have **multiple snapshots** over time, not just one thread dump.
- [ ] Identify **read/write/connect/file/selector/pool/handshake**, rather than lumping everything into "native I/O."
- [ ] Verified **runtime timeout values**, scopes, and units (0, unset, library defaults).
- [ ] Enforced an **overall deadline** if the operation must meet an SLA, not only per-read timeouts.
- [ ] Measured **`bytesReceived`/`bytesWritten` and frame/message completion** over the same period; tracked `lastByteAge`.
- [ ] Distinguished `SocketRead.duration` vs. `SocketRead.timeout`; accounted for JFR thresholds and missing-event limits.
- [ ] Checked peer side, OS sockets/queues, pools, and drivers if symptoms extend beyond the Java stack.
- [ ] Attached safe correlation IDs and stages; avoided logging bodies/tokens/PII.
- [ ] After fixing, verified timeout/error rate, p95/p99, throughput, and live connection/thread counts.

**Conclusion:** A thread sitting in a native I/O frame is an **investigation starting point**, not the answer. Connect the thread stack and state with **effective timeouts** and **byte/message progress over time**. Only when all three align can you distinguish a legitimately waiting connection, a drip-feeding peer, a missing timeout configuration, a queue/pool bottleneck, and a genuinely stalled I/O operation.

## References

- [Oracle Java 21 — `Thread.State`: RUNNABLE and differences from OS state](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.State.html)
- [Oracle Java 21 — `Socket`: `connect`, `setSoTimeout`, read semantics](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [Oracle Java 21 — `InputStream`: read, readNBytes, and EOF](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
- [Oracle Java 21 — `HttpClient.Builder.connectTimeout`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Oracle Java 21 — `HttpRequest.Builder.timeout`](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html)
- [Oracle Java 21 — `SocketChannel` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/SocketChannel.html)
- [Oracle Java 21 — `ThreadInfo` and thread dumps](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadInfo.html)
- [Oracle Java 21 — `jcmd`: Thread.print and JFR commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java 21 — `jfr`: metadata, summary, print, configure](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Oracle Java 21 — `jdk.jfr`: event settings, threshold, and stack trace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html)
- [Oracle — Troubleshoot Performance Issues Using JFR: Socket/File Read/Write](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
