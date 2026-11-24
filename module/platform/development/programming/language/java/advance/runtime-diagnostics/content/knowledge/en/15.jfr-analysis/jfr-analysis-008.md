# 15.8. Analyzing locks, thread states, file/socket I/O, and exceptions with JFR

## Lesson objectives

After this lesson, you will be able to:

1. Read a **Java Flight Recorder (JFR)** file to spot signs of **lock contention**, monitor waits, park/sleep, file/socket I/O, and exceptions.
2. Properly distinguish `jdk.JavaMonitorEnter`, `jdk.JavaMonitorWait`, `jdk.ThreadPark`, `jdk.ThreadSleep`, and the states in `java.lang.Thread.State`.
3. Identify notable I/O events by **timestamp, duration, endpoint/path, byte count, event thread, and stack trace**; avoid confusing wait latency with CPU usage.
4. Understand `jdk.JavaExceptionThrow`, `jdk.JavaErrorThrow`, and exception statistics; know why an exception being **thrown** does not mean a failed request or process crash.
5. Combine multiple event groups on the same **timeline**, verify event settings/thresholds, and form hypotheses testable with logs, metrics, thread dumps, and experiments.
6. Run a Java 17+ program yourself to generate a recording with controlled wait operations, then read events using `jfr` and `jdk.jfr.consumer`.

> **Important limitation:** JFR records **the events the recording was configured to capture**. Absence of an event in the file does **not** prove the operation did not occur; a long-duration event does **not** by itself prove deadlock, hot CPU, or an external server outage.

## 1. Approach: moving from symptom to events and stacks

JFR records events with an **event type**, **start time**, **duration** (for duration events), **event thread**, **payload**, and optionally a **stack trace**. A single event usually answers only one narrow question:

- A thread spent 240 ms waiting to **enter a monitor** (`jdk.JavaMonitorEnter`).
- A thread **waited on a condition** via `Object.wait()` for 500 ms (`jdk.JavaMonitorWait`).
- A thread **parked** waiting for a task/lock/permit (`jdk.ThreadPark`).
- A **socket read** took 800 ms and returned some number of bytes (`jdk.SocketRead`).
- An exception was **thrown** at a stack (`jdk.JavaExceptionThrow`).

You must place events on a timeline and correlate them with real symptoms: rising request latency, queue backlogs, falling throughput, high CPU, timeouts, or error rates.

```text
Symptom: request p99 rises
        |
        v
Capture the right time window in .jfr
        |
        +--> Lock/park/wait? ------> Who waited? How long? On which stack?
        |
        +--> File/socket I/O? -----> Which endpoint/path? Duration, bytes, timeout?
        |
        +--> Exceptions? ----------> Which type? How frequent? Handled?
        |
        +--> Thread/CPU samples? --> Which threads? Waiting or sampled running?
        |
        v
Cross-check logs/request IDs, metrics, config, thread dumps
        |
        v
Hypothesis -> experiment -> confirm or refute
```

**Very common pitfall:** duration events can *overlap in time across multiple threads*. Summing 100 `SocketRead` events of 1 second each yields **100 seconds of total event duration**, which does not mean **100 wall-clock seconds** elapsed or that one request took 100 seconds.

## 2. Event table to know before analyzing

The names below are standard JFR event types in HotSpot/JDK 17–21+. Version, JVM implementation, `.jfc`, event thresholds, stack settings, and workload determine which types appear in a recording. Before analyzing, **run `jfr summary` and `jfr metadata` on the actual file**.

| Phenomenon | JFR event | Primary meaning |
| --- | --- | --- |
| `synchronized` contention | `jdk.JavaMonitorEnter` | Time a thread was blocked **waiting to enter an intrinsic monitor** before acquiring it. |
| Calling `Object.wait()` | `jdk.JavaMonitorWait` | Time a thread **waited on a monitor after `wait()`**, ending via notify, timeout, or interrupt. |
| Waiting via `LockSupport` and concurrent utilities | `jdk.ThreadPark` | Park duration, e.g., some wait operations in `Lock`, `Future`, queues, executors. |
| `Thread.sleep()` | `jdk.ThreadSleep` | Sleep duration; does not indicate lock contention. |
| Thread lifecycle | `jdk.ThreadStart`, `jdk.ThreadEnd` | Creation/completion milestones, not every `Thread.State` transition. |
| File reads/writes | `jdk.FileRead`, `jdk.FileWrite` | Measured I/O operation duration and path/bytes data when available. |
| TCP socket reads/writes | `jdk.SocketRead`, `jdk.SocketWrite` | Socket operation duration and endpoint/bytes when available. |
| Thrown exceptions | `jdk.JavaExceptionThrow` | Exception type, message/stack if the event is enabled and data is available. |
| Thrown errors | `jdk.JavaErrorThrow` | Event related to `Error`; does not mean the JVM crashed. |
| Periodic exception statistics | `jdk.ExceptionStatistics` | An aggregate view of exception counts, not a log of every throw. |
| Execution/CPU samples | `jdk.ExecutionSample`, `jdk.CPULoad`, `jdk.ThreadCPULoad` | Complementary when separating active computation from waiting. |

**Two frequently confused events:** `jdk.JavaMonitorEnter` involves **contention entering `synchronized`**; `jdk.JavaMonitorWait` involves **`Object.wait()` after a thread already owned the monitor and temporarily released it**. Do not lump both together as "blocked on lock."

### Read fields by semantics, not just name

| Common field | How to use | Caveats |
| --- | --- | --- |
| `startTime`, `duration` | Order events chronologically and compare latencies. | Duration is typically elapsed time and may include waiting/scheduling; not automatically CPU time. |
| `eventThread` / `getThread()` | Identify the thread that emitted the event. | Thread names can collide and be reused; virtual threads and carriers have no fixed 1:1 pairing. |
| `stackTrace` | Inspect the call path where the event was recorded/sampled. | May be missing or depth-limited; the stack is not a history of the entire duration. |
| `monitorClass`, `previousOwner`, `address` | Investigate the monitor and previous owner when recorded by JFR. | `address` is a low-level runtime identifier, not a durable ID across JVMs/recordings. |
| `path`, `bytesRead`, `bytesWritten` | Find large or slow files/operations. | Do not infer full disk latency or physical disk I/O volume from a single event. |
| `host`, `address`, `port` | Group sockets by recorded endpoint. | One endpoint can serve many requests; does not replace a request ID. |
| `thrownClass`, `message` | Classify exceptions and spot repeats. | Do not use messages containing sensitive data as public keys; thrown does not mean uncaught. |

Field names **can vary by event type and JDK**, so check actual metadata, e.g., `jfr metadata --events jdk.JavaMonitorEnter recording.jfr`.

## 3. Inspecting a recording file before drawing conclusions

Suppose you receive `incident.jfr` from a troubled JVM. Using JDK 17+:

```bash
jfr summary incident.jfr
jfr metadata --events jdk.JavaMonitorEnter,jdk.SocketRead incident.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 20 incident.jfr
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite --stack-depth 20 incident.jfr
jfr print --events jdk.JavaExceptionThrow,jdk.JavaErrorThrow,jdk.ExceptionStatistics --stack-depth 20 incident.jfr
```

These commands **read the existing file** without modifying `.jfr` or running code inside the application.

- **`jfr summary`** shows recording duration, counts, and sizes by event type: the first step to avoid analyzing a type that was never recorded.
- **`jfr metadata`** shows field schemas for recorded types (or metadata present in the file); helps identify fields for JSON/API filtering.
- **`jfr print --events ...`** prints only events matching type names; can emit thousands of lines if many events exist.
- **`--stack-depth 20`** increases the **number of frames displayed**, without recovering stacks never recorded due to `stackTrace=false` or capture depth limits.

You can export JSON for external tooling:

```bash
jfr print --json --events jdk.SocketRead,jdk.SocketWrite incident.jfr
```

Do not assume every JDK version produces an **identical JSON schema**; cross-check `jfr metadata` and check field existence before querying. Do not send files containing internal exception messages, paths, or endpoints outside trusted environments.

If viewing in **Java Mission Control (JMC)**, open the recording, locate views for **Threads/Lock Instances**, **I/O**, and **Exceptions**, filter by time range/thread, and inspect event tables and stacks. Tab layouts and names vary by JMC version. The goal is **reading each event with its timeline context**, not relying on one fixed menu path.

## 4. Lock analysis: monitor contention vs. condition waiting

### 4.1. `jdk.JavaMonitorEnter`: when a thread blocks entering `synchronized`

Suppose:

```java
private static final Object LOCK = new Object();

// Thread A stays inside synchronized for a long time:
synchronized (LOCK) {
    processSlowly();
}

// Thread B arrives later and must wait for A to release LOCK:
synchronized (LOCK) {
    updateSharedState();
}
```

This is **illustrative code**, not a complete program. If thread B blocks entering the monitor long enough to exceed the JFR threshold, we may see `jdk.JavaMonitorEnter` for **thread B**. `duration` reflects the wait before acquiring the monitor—**not** how long `updateSharedState()` runs inside the critical section.

When inspecting the event:

1. **Which thread waited?** Read event thread/ID; remember thread pools may rename threads between tasks.
2. **Where did it wait?** Stack trace points to the frame invoking `synchronized`, e.g., handler, cache, formatter, or logger.
3. **What monitor class?** `monitorClass`; multiple instances of the same class can be distinct locks.
4. **Who held it previously?** `previousOwner` if populated; inspect the timeline/thread dumps to see what the owner was doing.
5. **Frequent or long waits?** Count events and inspect p95/p99/max plus how many threads contend on one monitor. Compare against recording duration and workload.

A single 200 ms event may just be transient contention. When many requests queue sequentially on the same lock and throughput drops, **that is a serialization/bottleneck signal worth investigating**.

### 4.2. `jdk.JavaMonitorWait`: `Object.wait()` is not monitor entry contention

```java
synchronized (LOCK) {
    while (!ready) {
        LOCK.wait();
    }
}
```

This is **illustrative code**. `wait()` **releases the monitor** while the thread waits for `notify`/`notifyAll`, timeout, or interrupt; before `wait()` returns normally, the thread must re-acquire the monitor. `jdk.JavaMonitorWait` reflects **condition waiting** via a monitor. It may report monitor class, notifier, timeout, or `timedOut` when recorded, depending on version/schema.

If stacks stop at `Object.wait`, ask:

- Who updates the `ready` condition? Is `notify`/`notifyAll` called in the right place under the same monitor?
- Is this an **idle worker** waiting for work (normal) or a request waiting for data that should already be available?
- Is there a **lost notification**, timeout, wrong guard condition, or upstream backlog?
- Is a thread reporting a long wait actually on the critical path of the request being investigated?

Do not conclude a long `JavaMonitorWait` is **monitor lock contention**; the two mechanisms are different.

### 4.3. `jdk.ThreadPark`: `LockSupport`, `Lock`, queues, and futures

Many abstractions in `java.util.concurrent` use park/unpark. For example, `ReentrantLock`, `CompletableFuture`, or `BlockingQueue` can emit `jdk.ThreadPark` in various code paths rather than `jdk.JavaMonitorEnter`.

```java
LockSupport.parkNanos(100_000_000L); // illustrative park up to ~100 ms
```

In `jdk.ThreadPark`, check event thread, `duration`, stack, `parkedClass`, and timeout/blocker if present in the schema. A stack leading to `CompletableFuture.get()` or `LinkedBlockingQueue.take()` may represent **waiting by design**, whereas a stack leading to a contended lock may represent a bottleneck. Always trace the **wake-up condition**: who completes the future, enqueues items, or releases the lock.

Do not equate every `ThreadPark` with a deadlock. Long thread parks in an idle executor are very common and often normal.

### 4.4. `jdk.ThreadSleep`: intentional sleeping or backoff

`Thread.sleep()` is timed waiting, commonly used in retry/backoff, schedulers, or demos. If a real request sleeps 500 ms on its critical path, latency increases; however, that is **not** lock contention unless other lock evidence exists. If a maintenance thread sleeps off the request path, do not prioritize it just because its duration is large.

### 4.5. Checklist for lock issues

| Signal | Questions to check | Additional evidence |
| --- | --- | --- |
| Many long `JavaMonitorEnter` events | Does the critical section contain I/O, logging, service calls, or heavy work? | Owner/contender stacks, thread dumps, CPU profile, synchronization code. |
| Long `JavaMonitorWait` | Which condition is awaited? Who is responsible for calling `notify`? | Guarded-block code, queue/condition state logs. |
| Frequent `ThreadPark` on request threads | Which future/lock/queue is awaited? Is there a timeout? | Stacks, queue depth, executor saturation, task completion. |
| Long `ThreadSleep` on request threads | Is retry/backoff inadvertently blocking requests? | Retry policy, timeout logs, and attempt counts. |
| No monitor events visible | Event disabled / high threshold, a different lock type, brief contention, or none occurred. | Check settings, `ThreadPark`, and thread dumps. |

> **Distinguishing deadlock:** a few long lock-wait events do **not** prove deadlock. You need evidence of a wait cycle / owners, thread dumps, and progress observation. A system slowed by lock contention can still make forward progress.

## 5. Thread states: do not equate `Thread.State` with JFR timeline colors

`java.lang.Thread.State` defines **NEW, RUNNABLE, BLOCKED, WAITING, TIMED_WAITING, TERMINATED**. JFR typically gives **partial observations** from lifecycle, wait, I/O, and sampling events; it **does not automatically emit a complete log every time a thread transitions between the six states**.

| Java state | API-level meaning | JFR signals that may support it | What must not be inferred |
| --- | --- | --- | --- |
| `NEW` | Thread has not called `start()` yet. | `ThreadStart` may not have appeared yet. | Cannot prove non-existence solely from a missing event. |
| `RUNNABLE` | Running or ready to run, sometimes in native I/O depending on VM. | `ExecutionSample`, thread CPU load. | `RUNNABLE` **does not mean consuming 100% CPU**. |
| `BLOCKED` | Waiting to enter an intrinsic monitor (`synchronized`). | `JavaMonitorEnter` when contention is recorded. | Does not cover every `Lock`/Future wait. |
| `WAITING` | Indefinite wait, such as `Object.wait()` or `park()`. | `JavaMonitorWait`, `ThreadPark` depending on activity. | Intentional waiting is not automatically a bug. |
| `TIMED_WAITING` | Timed wait such as `sleep`, `wait(timeout)`, `parkNanos`. | `ThreadSleep`, `JavaMonitorWait`, `ThreadPark`. | Event duration is not the configured timeout. |
| `TERMINATED` | Thread has finished. | `ThreadEnd` if collected. | A single end event does not explain full termination reasons. |

**Why not infer state from every gap?** JFR uses **thresholds**, sampling, and event filtering. An empty segment on a timeline might mean the thread was running CPU, performing uninstrumented work, executing operations below threshold, had the event disabled, or suffered data loss. Check `jdk.DataLoss`/metadata and cross-check CPU samples, thread dumps, or logs as needed.

### Analyzing thread pools and virtual threads

- With a **thread pool**, one platform thread serves **many tasks/requests sequentially**. Never attribute every event on the same thread name to one request without a request/correlation ID.
- With **virtual threads (Java 21+)**, one virtual thread can mount/unmount across **different carrier platform threads**. Never assume "virtual thread A always runs on carrier B."
- Lifecycle recording and specialized virtual thread events vary by JDK/JVM/recording. When investigating virtual threads, inspect events like `jdk.VirtualThreadPinned` (when supported and enabled), stacks, and appropriate dump tools instead of assuming a single platform thread ID suffices.
- **Stack sampling** captures stacks according to period/configuration, not exact method call counts.

For "hung request" bugs, prioritize building the chain: **what is the request waiting on → which thread/event shows it → which actor clears the condition → did that happen?** Listing thread states alone is not enough to find root cause.

## 6. File I/O analysis (`jdk.FileRead`, `jdk.FileWrite`)

File I/O events can include `path`, `bytesRead`/`bytesWritten`, `startTime`, `duration`, event thread, and stack (if enabled). They help distinguish which file operations are slowing the application down.

**Illustrative** example of an event set:

| Path | Event count | Summed event duration | Total bytes | Suggested check |
| --- | ---: | ---: | ---: | --- |
| `/var/log/app.log` | 900 | 3,400 ms | 5 MiB | Synchronous logging on the critical path? |
| `/data/cache.bin` | 22 | 1,800 ms | 300 MiB | Large file reads/writes, repeated I/O waits? |
| `/tmp/export.csv` | 2 | 5,500 ms | 85 MiB | An export task may be slow; should it stream? |

This is **not fixed output** from JFR. To prioritize investigation:

1. Check **max duration** and p95/p99 per path or call site; many tiny I/Os may matter less than one slow operation on the critical path.
2. Inspect **byte counts**, but do not divide `bytes/duration` to claim physical disk speed when caches, buffers, multiple threads, or native layers sit in between.
3. Distinguish **application-blocking I/O** from background I/O (log batching, file rotation, backups) using threads and stacks.
4. Check local/network filesystems, OS contention, disk queues, storage latency, and infra logs; JFR events do not diagnose a "failing disk" on their own.

A 200 ms `FileWrite` does not necessarily mean 200 ms of physical disk writing, since Java I/O can pass through the OS page cache, buffering, encryption layers, or async mechanisms. Nor does JFR necessarily record every file operation issued by native libraries.

## 7. Socket I/O analysis (`jdk.SocketRead`, `jdk.SocketWrite`)

Socket events show timestamps and elapsed durations of JVM-instrumented read/write operations along with endpoint details when available. Common fields include `host`, `address`, `port`, `bytesRead`, `bytesWritten`, `timeout`, and `endOfStream` (depending on event and JDK).

### A slow socket read can have many causes

An **800 ms** `jdk.SocketRead` may be caused by:

- The peer/server sending data late or processing the request slowly.
- Network latency, packet loss, or degraded connectivity.
- The application reading before data is ready due to protocol/request sequencing.
- Thread scheduling or resource contention around the operation.
- Misconfigured pools, retries, timeouts, or circuit breakers.

**Avoid concluding:** "800 ms socket read = network outage." JFR only sees the observed JVM side; cross-check peer/server metrics, network stats, TCP retransmissions (if available), traces, and logs.

### A slow socket write also does not prove a slow network

Long `SocketWrite` durations can stem from backpressure, full send buffers, a slow-reading peer, blocking I/O, or JVM workload. Inspect **bytes, endpoint, stack, event thread, duration**, and request timing. Writing a huge payload with a long duration may be completely normal under a known bandwidth cap.

### A practical filtering workflow

```bash
jfr print --events jdk.SocketRead,jdk.SocketWrite --stack-depth 20 incident.jfr
jfr print --events jdk.FileRead,jdk.FileWrite --stack-depth 20 incident.jfr
```

Filter by **endpoint/path** and aggregate by time window in JMC or a script. When exporting JSON, verify the actual schema before filtering. Never rely solely on hostname or IP as proof for a specific request, because connections can be pooled/reused and requests overlap.

**Compute cautiously:**

```text
count             = number of recorded events
totalEventTime    = sum of event durations
maxEventTime      = largest duration
totalBytes        = sum of bytes provided by events
```

`totalEventTime` across threads can **overlap**; it does not equal system-wide latency. When events below threshold are omitted, `count`, `totalEventTime`, and sample distributions are **biased**. Do not compare two recordings with different I/O thresholds as if they share the same ruler.

## 8. Exception analysis: "thrown" differs from "failed"

### 8.1. `jdk.JavaExceptionThrow` and `jdk.JavaErrorThrow`

An exception can be thrown and **caught/handled normally**, for example:

```java
try {
    Integer.parseInt("not-a-number");
} catch (NumberFormatException expected) {
    // The application may handle invalid input by design.
}
```

This is an illustrative snippet. When `jdk.JavaExceptionThrow` is enabled, JFR can record type, timestamp, `thrownClass`, `message`, and stack. **The presence of an event does not mean HTTP 500, a crash, or an unhandled error.**

`jdk.JavaErrorThrow` reflects thrown `Error` instances recorded by JFR; **do not treat it as proof the JVM is doomed to die**. Some `Error`s can still be caught within the system, though serious ones warrant immediate review.

**`jdk.ExceptionStatistics`** can show high-level trends when enabled, but it does not replace per-exception classification and request correlation. The number of "thrown" exceptions can differ dramatically from "uncaught" exceptions or failed responses.

### 8.2. Prioritizing by impact and change

| Observation | Check next |
| --- | --- |
| New exception appearing after a deploy | Compare type/stack/version, change logs, request paths. |
| One exception type spiking abruptly | Is there a retry loop, malformed input, parsing issue, timeout, or altered fallback? |
| Exceptions appearing while error rate is stable | Likely handled exceptions; measure overhead and noise before calling it an incident. |
| `IOException` coinciding with socket timeouts | Pair with `SocketRead`/`SocketWrite`, endpoints, and traces rather than concluding from timestamp overlap alone. |
| Severe `Error` / OOME | Combine with heap/GC/native memory, stderr, health checks, and OOME logs; JFR may not flush completely. |

**Risk of enabling throw events:** applications can throw exceptions at very high rates (especially exceptions used for control flow). Enabling detailed stacks/messages can raise overhead, grow file size, and expose sensitive data. Some JDKs throttle exception events; always check settings and the running version. Prefer short, targeted recordings for deep investigation.

### 8.3. Exception stack traces

The stack points to the **throw** site, not necessarily **where it was caught**, since the JFR stack trace does not include downstream catch-handling steps. To know whether requests failed:

- Cross-check logs with request IDs, response statuses, and retries/fallbacks.
- Look for the same exception repeating inside one request or across many requests.
- Verify whether that throw actually altered outcomes, throughput, or latency.

`message` may contain paths, hosts, parameters, or sensitive data; group by class/type/stack + sanitized context instead of logging raw messages publicly.

## 9. Capturing a new recording when the existing file lacks events

**Note:** this section applies when you are authorized to record JFR on the target JVM. `jcmd` must see the right PID and have attach permissions (typically same effective user on the same host/namespace). Inside containers, PIDs and paths may differ from the host.

Example on a JVM with actual PID `12345`:

```bash
jcmd -l
jcmd 12345 help JFR.start
jcmd 12345 JFR.start name=diagnostics settings=profile
jcmd 12345 JFR.check
```

Once the symptom reproduces, pull the file:

```bash
jcmd 12345 JFR.dump name=diagnostics filename=/tmp/incident.jfr
jcmd 12345 JFR.stop name=diagnostics
```

`JFR.dump` writes a dump **while the recording can keep running**; `JFR.stop` actually stops it. `/tmp/incident.jfr` is written by the **target JVM** in the filesystem seen by the JVM, not necessarily the shell where `jcmd` was invoked.

If you want a self-stopping recording:

```bash
jcmd 12345 JFR.start name=short-incident settings=profile duration=60s filename=/tmp/incident-60s.jfr
```

The file completes based on the duration and recording state; the `start` command returns before the 60 seconds finish. To tune specific events and thresholds, use **JMC Flight Recorder configuration** or build a custom `.jfc` based on `default`/`profile`; verify effective event settings via JFR metadata and recording config. Do not edit the JDK's bundled standard templates directly.

### `default` and `profile` do not guarantee every event is captured

- `settings=default`: optimized for low overhead, typically suited for continuous recording.
- `settings=profile`: typically captures more data, suited for short investigations at higher cost.
- Several events have **thresholds of a few to tens of milliseconds** (Oracle examples often use 20 ms for common I/O/monitor events), though exact values must be **read from the `.jfc`/recording of the running version**.
- Events below threshold are omitted; disabled events, uncollected samples, throttled events, off-window timing, or data loss can all leave "gaps."

**Controlled investigation strategy:** start with a short `profile` capture; if needed event types are missing, enable only the relevant group and lower thresholds for a bounded time while monitoring CPU/overhead/file size. Avoid `threshold=0` on all events continuously in production.

## 10. Java 17+ hands-on lab: generating controlled JFR signals

This example intentionally creates **monitor contention**, `Object.wait()`, park, sleep, file I/O, socket I/O over **the machine's loopback**, and a caught exception. It writes a file for you to analyze; exact event counts and durations depend on scheduling, JDK, tools, and OS.

Create **`JfrSignalsDemo.java`**:

```java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;
import jdk.jfr.Recording;

public class JfrSignalsDemo {
    private static final Object MONITOR = new Object();

    public static void main(String[] args) throws Exception {
        Path file = Path.of("jfr-signals-demo.jfr").toAbsolutePath();

        try (Recording recording = new Recording()) {
            for (String name : List.of(
                    "jdk.JavaMonitorEnter", "jdk.JavaMonitorWait",
                    "jdk.ThreadPark", "jdk.ThreadSleep",
                    "jdk.FileRead", "jdk.FileWrite",
                    "jdk.SocketRead", "jdk.SocketWrite")) {
                recording.enable(name)
                        .withThreshold(Duration.ZERO)
                        .withStackTrace();
            }
            recording.enable("jdk.ThreadStart");
            recording.enable("jdk.ThreadEnd");
            recording.enable("jdk.JavaExceptionThrow")
                    .withStackTrace();

            recording.start();
            createMonitorContention();
            synchronized (MONITOR) {
                MONITOR.wait(70);
            }
            LockSupport.parkNanos(TimeUnit.MILLISECONDS.toNanos(70));
            touchFile();
            touchLoopbackSocket();

            try {
                throw new IllegalArgumentException("demo-handled");
            } catch (IllegalArgumentException expected) {
                // Handled error: can still be recorded as a throw event.
            }

            recording.stop();
            recording.dump(file);
        }

        System.out.println("recording=jfr-signals-demo.jfr");
    }

    private static void createMonitorContention()
            throws InterruptedException {
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread owner = new Thread(() -> {
            synchronized (MONITOR) {
                locked.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "demo-monitor-owner");

        Thread contender = new Thread(() -> {
            synchronized (MONITOR) {
                // Enters the monitor only after owner releases the lock.
            }
        }, "demo-monitor-contender");

        owner.start();
        locked.await();
        contender.start();
        Thread.sleep(160);
        release.countDown();
        owner.join();
        contender.join();
    }

    private static void touchFile() throws Exception {
        Path path = Files.createTempFile("jfr-demo-", ".bin");
        try {
            Files.write(path, new byte[8192]);
            try (InputStream input = Files.newInputStream(path)) {
                input.readAllBytes();
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }

    private static void touchLoopbackSocket() throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {
            Thread peer = new Thread(() -> {
                try (Socket accepted = server.accept()) {
                    Thread.sleep(120);
                    accepted.getOutputStream().write(42);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            }, "demo-loopback-peer");

            peer.start();
            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(),
                    server.getLocalPort())) {
                int received = client.getInputStream().read();
                if (received != 42) {
                    throw new IllegalStateException(
                            "Unexpected byte: " + received);
                }
            }
            peer.join();
        }
    }
}
```

Compile and run (JDK 17+; requires permission to open a **localhost/loopback socket**):

```bash
javac --release 17 JfrSignalsDemo.java
java JfrSignalsDemo
```

If the program succeeds, the final output line is **exact**:

```text
recording=jfr-signals-demo.jfr
```

Results may differ in **event counts, ordering, durations, and fields** due to JDK internals, sampling timing, and buffering. `Thread.sleep(160)` aims to make contention easier to observe, though scheduling can still prevent the contender from waiting long enough. File reads/writes are usually very fast; even with threshold 0, whether an event is emitted depends on code paths and JVM instrumentation.

**Explanation of what the program does:**

1. Enables **duration events** with threshold 0 and stack traces so the demo has a chance to capture short operations. This setting is for the lab and not recommended in production.
2. Thread `demo-monitor-owner` holds `MONITOR` and waits on a latch. Thread `demo-monitor-contender` attempts to enter `synchronized`, creating the opportunity for `jdk.JavaMonitorEnter`.
3. `MONITOR.wait(70)` is condition waiting on a monitor; `LockSupport.parkNanos` is parking; `Thread.sleep` causes sleeping. These three waits **have distinct semantics**.
4. `Files.write`/`Files.newInputStream` demonstrate file I/O; `ServerSocket`/`Socket` communicate **locally** and intentionally delay the peer send to produce a socket read duration.
5. An exception is thrown and caught; it demonstrates exactly why **a throw event does not mean an unhandled error**.
6. `recording.stop()` and `recording.dump(file)` save the recording for inspection with tools.

Inspect which event types are actually present:

```bash
jfr summary jfr-signals-demo.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark --stack-depth 20 jfr-signals-demo.jfr
jfr print --events jdk.FileRead,jdk.FileWrite,jdk.SocketRead,jdk.SocketWrite --stack-depth 20 jfr-signals-demo.jfr
jfr print --events jdk.JavaExceptionThrow --stack-depth 20 jfr-signals-demo.jfr
```

**Exercise:** increase `Thread.sleep(160)` to `400` ms and compare the two recordings. You would expect longer monitor wait duration if the contender started waiting on time; however, if other events affect scheduling, check timestamps in JFR to verify rather than looking solely at totals.

## 11. Reading and grouping events with `jdk.jfr.consumer` (Java 17+)

When a file contains many events, you can summarize **type, count, and duration**, then inspect a few samples with thread/stack info. This is a standalone program requiring no external dependencies outside the JDK.

Create **`JfrSignalSummary.java`**:

```java
import java.nio.file.Path;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordedFrame;
import jdk.jfr.consumer.RecordedStackTrace;
import jdk.jfr.consumer.RecordedThread;
import jdk.jfr.consumer.RecordingFile;

public class JfrSignalSummary {
    private static final Set<String> INTERESTING = Set.of(
            "jdk.JavaMonitorEnter", "jdk.JavaMonitorWait",
            "jdk.ThreadPark", "jdk.ThreadSleep",
            "jdk.FileRead", "jdk.FileWrite",
            "jdk.SocketRead", "jdk.SocketWrite",
            "jdk.JavaExceptionThrow", "jdk.JavaErrorThrow");

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.out.println(
                    "Usage: java JfrSignalSummary <recording.jfr>");
            return;
        }

        Map<String, Long> counts = new TreeMap<>();
        Map<String, Long> totalNanos = new TreeMap<>();
        int examples = 0;

        try (RecordingFile file = new RecordingFile(Path.of(args[0]))) {
            while (file.hasMoreEvents()) {
                RecordedEvent e = file.readEvent();
                String type = e.getEventType().getName();

                if (!INTERESTING.contains(type)) {
                    continue;
                }

                counts.merge(type, 1L, Long::sum);
                totalNanos.merge(
                        type, e.getDuration().toNanos(), Long::sum);

                if (examples < 8) {
                    examples++;
                    RecordedThread thread = e.getThread();
                    String threadName = thread == null
                            ? "(unknown)"
                            : thread.getJavaName();

                    System.out.println(
                            type + " start=" + e.getStartTime()
                            + " duration=" + e.getDuration()
                            + " thread=" + threadName);

                    for (String field : new String[]{
                            "monitorClass", "previousOwner",
                            "path", "bytesRead", "bytesWritten",
                            "host", "address", "port",
                            "thrownClass", "message"}) {
                        if (e.hasField(field)) {
                            System.out.println(
                                    "  " + field + "="
                                    + String.valueOf(e.getValue(field)));
                        }
                    }

                    RecordedStackTrace trace = e.getStackTrace();
                    if (trace != null && !trace.getFrames().isEmpty()) {
                        RecordedFrame frame = trace.getFrames().get(0);
                        if (frame.getMethod() != null) {
                            System.out.println(
                                    "  topFrame="
                                    + frame.getMethod().getType().getName()
                                    + "." + frame.getMethod().getName());
                        }
                    }
                }
            }
        }

        System.out.println("=== Recorded-event totals ===");
        for (Map.Entry<String, Long> entry : counts.entrySet()) {
            String type = entry.getKey();
            double millis = totalNanos.get(type) / 1_000_000.0;
            System.out.printf(
                    "%s count=%d summedDurationMs=%.3f%n",
                    type, entry.getValue(), millis);
        }
    }
}
```

Compile and run after generating `jfr-signals-demo.jfr`:

```bash
javac --release 17 JfrSignalSummary.java
java JfrSignalSummary jfr-signals-demo.jfr
```

The program prints the first few matching events, then **counts by type** and computes **summed duration for events of that type**. Fixed numeric stdout cannot be given because JVMs, scheduling, and recordings vary. Both situations are valid:

- An event type never appears: the program **prints no summary line** for that type.
- Exception throws: usually have `duration=PT0S` or zero duration; do not use summed exception duration to measure "error handling time."

**Key limitations of this sample parser:**

- `totalNanos` is the **sum of recorded event durations**, not system elapsed time; durations across multiple threads can overlap.
- The program does **not** compute p95/p99 or split by path/endpoint/monitor or correlation ID; production analytics need further grouping and attention to sampling/thresholds.
- Call `e.hasField(...)` before `getValue(...)` because each event type has a different schema.
- `getThread()` and `getStackTrace()` can be `null`. The top stack frame is not necessarily the root cause.
- `RecordingFile` streams sequentially without holding all events in RAM; better than `readAllEvents()` for large files.

## 12. Real-world case analysis: p99 rises after a change

Suppose over 10 minutes, request p99 rises from 150 ms to 1,100 ms. JFR shows **illustrative** results:

| Observation group | Before deploy | After deploy | What to verify |
| --- | --- | --- | --- |
| `JavaMonitorEnter` in `CacheStore.update()` | Rare, under 10 ms | Frequent, 200–450 ms | Is the monitor held during I/O or serialization? |
| `SocketRead` to backend API | 70–110 ms | 80–120 ms | Network latency did not rise proportionally; likely not the main suspect. |
| `ThreadPark` on workers | Mostly while idle | Rises with queue backlog | Is queue congestion a consequence of a bottleneck or the cause? |
| `JavaExceptionThrow` `TimeoutException` | Low | Rising | Timeouts may be a **consequence** of slow requests, not necessarily the cause. |

Do not conclude everything from this table alone. Verification workflow:

1. **Align timestamps** across JFR, logs, and metrics (timezones, deploy timestamp, recording window).
2. **Confirm enabled events/thresholds** match between both recordings. Otherwise counts cannot be compared directly.
3. From `JavaMonitorEnter`, inspect stacks and owners and compare against post-deploy code. If I/O runs **inside `synchronized`**, that is a strong hypothesis.
4. Check thread dumps / other JFR thread/CPU views to confirm the owner really holds the monitor long and requests queue behind it.
5. Test an appropriate fix (e.g., moving I/O outside the critical section where thread safety permits), then re-measure p99 and lock waits.
6. If lock waits drop while p99 stays high, continue investigating sockets, queues, GC, and retries. **Do not force a root cause** before before/after numbers back it up.

This illustration highlights the difference between **cause** (prolonged lock hold), **symptom** (rising p99 / queues), and **consequence** (`TimeoutException`), though on a real system all three roles can shift.

## 13. Common interpretation errors

| Hasty conclusion | Evidence-based understanding |
| --- | --- |
| “Long `JavaMonitorWait` means `synchronized` contention.” | `JavaMonitorWait` ties to `Object.wait`; check notify/timeout conditions. To look for **monitor entry** waits, check `JavaMonitorEnter`. |
| “`ThreadPark` means deadlock.” | Parking can be normal idle workers or waiting on tasks/locks/futures; check who is responsible for unparking and the workload. |
| “`RUNNABLE` definitely consumes CPU.” | `RUNNABLE` can simply mean ready to run; check CPU samples/load and scheduling. |
| “No lock events means definitely no contention.” | Events may be disabled, filtered by threshold, or locks may use another abstraction like `ReentrantLock`. |
| “Green/empty gaps in the JFR timeline mean the thread was burning CPU.” | Gaps may result from missing events or sampling; check CPU/event settings. |
| “Long `SocketRead` means slow network.” | The peer may be slow to send, the app may read early, or scheduling/timeouts may contribute; check server logs, traces, and network metrics. |
| “2 s `FileWrite` means the disk was physically writing for 2 s.” | Buffers, caches, filesystems, and native I/O sit in between; the event measures instrumented code, not physical disk hardware. |
| “`JavaExceptionThrow` means a failed request.” | Many throws are caught and handled; check response/error rates and correlation. |
| “Summed event duration is how long the JVM was blocked.” | Durations overlap across threads; summing event time does not equal wall time. |
| “`--stack-depth 100` reveals unrecorded stacks.” | The flag only controls **printed** frames; it cannot recover uncaptured data. |
| “If no event appears in the recording, the operation never happened.” | Check time window, enablement, thresholds, throttling, sampling, JVM/JDK support, and data loss. |
| “Thread name is enough to link every event to one request.” | Thread pools reuse threads and virtual threads migrate carriers; use request IDs/tracing. |

## 14. Quick investigation checklist

- [ ] Identify **PID/JVM**, JDK, recording window, and when users saw errors.
- [ ] Run **`jfr summary`**, verify event types, counts, and settings.
- [ ] Filter **lock/park/wait/sleep** by duration, thread, stack, owner, and time.
- [ ] Filter **file/socket** by path/endpoint, bytes, duration, thread, and stack; cross-check infrastructure.
- [ ] Filter **exceptions/errors** by class, call site, trend, and actual request handling.
- [ ] Distinguish **elapsed duration**, **CPU sample**, **thread state**, and **wall-clock**.
- [ ] Never infer a leak, deadlock, or network failure from a single event.
- [ ] If data is missing, adjust **only the needed events/thresholds** in a short recording and measure overhead.
- [ ] Corroborate with logs, metrics, request correlation, thread dumps, tracing, or before/after experiments.
- [ ] Store `.jfr` files under security controls since stacks, paths, and exception messages can be sensitive.

## 15. Self-check questions

1. **What is the main difference between `jdk.JavaMonitorEnter` and `jdk.JavaMonitorWait`?** `JavaMonitorEnter` measures waiting to **enter an intrinsic monitor** under contention; `JavaMonitorWait` relates to `Object.wait()` on a monitor waiting for a condition.
2. **Why can `ReentrantLock` involve `ThreadPark` without `JavaMonitorEnter`?** It uses `java.util.concurrent` synchronization/parking rather than waiting on a Java intrinsic monitor.
3. **Does a 900 ms `SocketRead` duration prove the network failed?** No; it could be a slow peer response, early app read, scheduling, or network. Cross-check endpoints, traces, and metrics.
4. **Does an exception event mean a failed response?** No; the exception may have been caught and handled legitimately.
5. **Why is seeing zero `FileRead` events insufficient to conclude there was no file I/O?** The event may be disabled, filtered by threshold, uninstrumented, missed by sampling, or outside the recording window.
6. **Can you sum durations across all threads to get elapsed time?** No. Multiple events can overlap in time.
7. **What is the very first thing to do with an unfamiliar JFR file?** Run `jfr summary` to see what the recording actually contains; follow with `jfr metadata` and targeted filters.
8. **Is a thread in `WAITING` always a bug?** No; idle workers and normal waits/parks can be `WAITING`. Inspect the thread's role and wake-up condition.

## References

- [Oracle Java 21 — The `jfr` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): `summary`, `print`, `metadata`, event filters, stack depth, and JSON.
- [Oracle Java 21 — The `jcmd` Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): `JFR.start`, `JFR.check`, `JFR.dump`, `JFR.stop`.
- [Oracle — Troubleshoot Performance Issues Using Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshoot-performance-issues-using-jfr.html): locks, I/O, exceptions, and reading wait events.
- [Oracle Java 21 — JFR Event Settings](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/package-summary.html): `enabled`, `threshold`, `stackTrace`, `period`.
- [Oracle Java 21 — `RecordedEvent`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getStartTime`, `getDuration`, `getThread`, `getStackTrace`.
- [Oracle Java 21 — `RecordingFile` and reading JFR files](https://docs.oracle.com/en/java/javase/21/jfapi/parsing-recording-file.html).
- [Oracle Java 21 — `Recording` / `EventSettings`](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.jfr/jdk/jfr/Recording.html).
