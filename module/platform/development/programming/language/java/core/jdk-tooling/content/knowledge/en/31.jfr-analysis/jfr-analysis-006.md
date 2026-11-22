# Analyzing Thread Latency with Java Flight Recorder (JFR)

Thread latency is the amount of time a thread cannot continue its intended work promptly. A thread may be waiting for a lock, waiting for a signal, parked in a thread pool, sleeping, waiting for data from a socket or file, or affected by GC. These wait periods can slow down requests even when JVM CPU utilization is not high.

Java Flight Recorder (JFR) records events with timestamps and durations to pinpoint where threads are stalled, while also capturing stack samples of threads actively executing code. It is well-suited for distinguishing whether an application is spending time on locks, I/O, scheduling, GC, or CPU processing. JDK Mission Control (JMC) lets you inspect recordings as timelines, tables, and charts; the `jfr` tool can filter and print events directly in the terminal.

JFR records duration events (with a start time and duration), instant events (recorded at a single point in time), and sample events (sampled periodically). Latency analysis primarily uses duration events; CPU profiling uses sample events.

## 1. Understanding Thread Latency

### 1.1. Latency Differs from CPU Time and Throughput

These three metrics measure different things:

| Metric | Meaning | Example |
|---|---|---|
| Request latency | Time from receiving a request to returning the response | Request takes 800 ms |
| Thread CPU time | Time a thread is actually executing on the CPU | Thread uses 120 ms of CPU |
| Throughput | Number of tasks completed per unit of time | 500 requests/second |

A request that takes 800 ms while the thread uses only 120 ms of CPU may have spent most of the remaining time waiting on a database, socket, lock, or queue. Looking at CPU alone can cause you to miss the real root cause.

Latency is also not a single event. A request may sequentially wait on a connection pool, read from a socket, wait on a lock, and only then continue processing. JFR events help locate those wait intervals, but they do not automatically compute end-to-end request latency if the application hands off the request across multiple threads or services.

### 1.2. What Is a Thread-Stalling Event?

A thread-stalling event is a duration event during which a thread is not executing the required application code. Examples:

- A thread waiting to enter a synchronized monitor.
- A thread calling `Object.wait` to wait for a notification.
- A thread parked in `LockSupport` or a library synchronization mechanism.
- A thread sleeping via `Thread.sleep`.
- A thread waiting for socket or file I/O data.

JFR records the timestamp, duration, thread, and optionally a stack trace. The stack trace points to where in the code the wait operation began; for lock contention, the event can also identify the thread holding the monitor.

Not every wait interval is a bug. Scheduled thread sleeps, workers waiting on a queue, or a thread waiting for another task can be normal behavior. Check which thread the event occurs on, whether it lies on the request's critical path, and whether it increases when latency rises.

## 2. JFR Events to Inspect

The event names below are the full names commonly used in HotSpot JDK 21.

| Event | What It Records | Signs to Investigate |
|---|---|---|
| `jdk.JavaMonitorEnter` | Thread blocked trying to enter a synchronized monitor | Many long events, same lock or same stack site |
| `jdk.JavaMonitorWait` | Thread called `Object.wait` and is waiting for notification/timeout | Prolonged waits, missing notifier, or unmet condition |
| `jdk.ThreadPark` | Thread parked via `LockSupport` and park-based mechanisms | Worker, Future, queue, or lock waiting too long |
| `jdk.ThreadSleep` | Thread sleeping via `Thread.sleep` | Polling or sleep on the request-handling path |
| `jdk.SocketRead` / `jdk.SocketWrite` | Socket read/write duration | Waiting on peer, network, backpressure, or upstream |
| `jdk.FileRead` / `jdk.FileWrite` | File read/write duration | Slow storage or synchronous file I/O |
| `jdk.ExecutionSample` | Stack sample of a thread executing Java code | Methods appearing frequently when CPU is high |
| `jdk.NativeMethodSample` | Stack sample inside a native method | Native calls consuming significant execution time |
| `jdk.ThreadCPULoad` / `jdk.CPULoad` | Per-thread/JVM and system CPU load | Thread or process consuming high CPU |
| `jdk.GCPhasePause` / `jdk.GarbageCollection` | GC and pause phases | Pauses coinciding with latency spikes |

### 2.1. Distinguishing JavaMonitorEnter and JavaMonitorWait

These two events are easy to confuse:

- `jdk.JavaMonitorEnter` occurs when a thread tries to enter a synchronized block/method while the monitor is held by another thread. In the event, `eventThread` is the waiting thread and `previousOwner` indicates the thread that previously held the lock.
- `jdk.JavaMonitorWait` occurs when code calls `Object.wait`. The thread releases the monitor and waits for another thread to call notify/notifyAll or for the timeout to expire. This is a condition-waiting mechanism, not necessarily lock contention.

If multiple threads have long `JavaMonitorEnter` events at the same stack site, find the monitor owner and inspect what the owner is doing inside the critical section. If multiple threads have `JavaMonitorWait` events, inspect the wait condition, the notifier, and the wakeup logic.

### 2.2. Distinguishing Park, Sleep, and I/O

- `ThreadPark` is typically associated with `LockSupport.park`, `ReentrantLock`, queues, Futures, or executors. A worker parking when there is no work can be completely normal.
- `ThreadSleep` is a sleep interval requested by code. Check whether the sleep is on the request path, in a polling loop, or in a retry loop.
- `SocketRead` indicates a thread waiting for data from a socket. The event can include host, port, byte count, and stack trace. Long read times may relate to an upstream service, network, or a slow-sending peer.
- `SocketWrite` can be prolonged when the peer reads slowly or when buffers/network experience backpressure.
- `FileRead` and `FileWrite` help detect synchronous file I/O that is blocking workers.

Do not conclude the network is slow from a single long `SocketRead`. Cross-reference host/port, bytes, timestamps, upstream logs, and request traces.

### 2.3. Distinguishing CPU-Bound and Wait-Bound

If critical threads have many `ExecutionSample` events in the same method and CPU load is high, the application may be CPU-bound. Use Hot Methods/Call Tree in JMC to find the most frequently sampled methods.

If requests are slow while CPU load is low and there are many long lock/socket/park events, the issue is likely resource contention or waiting on a dependency. A blocked thread generally does not appear in execution samples because it is not running Java code during that time.

Execution samples are sampled data, not an exact measurement of per-method runtime. Use them to identify relative hotspots, then confirm with profiling or appropriate measurements.

### 2.4. GC Can Also Cause Latency

GC has several phases that run concurrently with the application; the total duration of a GC does not mean that entire duration is an application pause. When investigating latency, inspect `jdk.GCPhasePause` and total pause time. Correlate pause timestamps with latency spikes rather than looking only at total GC time.

## 3. Creating a Flight Recording

### 3.1. Finding the JVM PID

List the JVMs visible to `jcmd`:

~~~bash
jcmd -l
~~~

Or:

~~~bash
jps -l
~~~

Use the PID of the right instance. Inside Docker or separate process namespaces, the PID inside the container may differ from the PID on the host; find the PID in the appropriate namespace.

`jcmd` must run on the same machine as the target JVM and under the same effective user/group identifiers used to launch the JVM. If attaching fails, check the PID, user, container, and Attach API policy.

### 3.2. Recording a Short Window

For a running JVM, start a recording with:

~~~bash
jcmd 12345 JFR.start name=thread-latency settings=profile duration=30s filename=thread-latency.jfr
~~~

Replace `12345` with the actual PID. The recording runs for 30 seconds and stops automatically, writing `thread-latency.jfr` in the target JVM's working directory. You can pass an absolute path to save to a specific directory; ensure the process has write permissions.

Check the active recording:

~~~bash
jcmd 12345 JFR.check name=thread-latency verbose=true
~~~

`settings=profile` collects more data than `default` and is suited for short investigative recordings. The `default` template has lower overhead and is suited for continuous recordings. Both can be customized for the events you need to observe.

### 3.3. Recording at Application Startup

If you want the recording to start with the application:

~~~bash
java -XX:StartFlightRecording=delay=10s,duration=60s,name=thread-latency,filename=thread-latency.jfr,settings=profile -cp out MyApplication
~~~

This waits 10 seconds after JVM startup, records for 60 seconds, and writes the file. This is useful when issues occur right at startup or when reproducing a consistent workload.

### 3.4. Continuous Recording and Dumping on Incident

You can maintain a lightweight recording using the `default` template, bounded on disk:

~~~bash
jcmd 12345 JFR.start name=continuous settings=default disk=true maxage=1h maxsize=512m
~~~

When latency spikes, dump the most recent data without stopping the recording:

~~~bash
jcmd 12345 JFR.dump name=continuous filename=incident.jfr maxage=10m
~~~

`JFR.dump` writes data to the file while the recording keeps running. When you need to stop it:

~~~bash
jcmd 12345 JFR.stop name=continuous filename=continuous-final.jfr
~~~

Use `JFR.check` to view recording names and statuses. Check `jcmd <pid> help JFR.start`, `help JFR.dump`, and `help JFR.stop` on the target JVM if you need exact syntax details.

## 4. Analyzing Recordings with JDK Mission Control

JDK Mission Control (JMC) opens `.jfr` files and displays events on a timeline. JMC is not bundled in every standard JDK installation; install a JMC build compatible with your environment and open the recording.

Useful views when investigating thread latency:

1. **Automated Analysis Results:** review initial warnings and bottleneck hints.
2. **Java Application → Threads:** inspect per-thread activity timelines, states, and stack traces.
3. **Threads → Latencies:** inspect latency-causing event types such as Java Monitor Wait, Java Monitor Blocked, and Java Thread Park.
4. **Contention / Lock Instances:** see which locks are contended, which threads are waiting, and the stack traces where locks are acquired.
5. **I/O:** inspect Socket Read/Write and File Read/Write by host, file, thread, and event.
6. **Hot Methods / Call Tree:** inspect frequently sampled code when the application is CPU-bound.
7. **JVM Internals → Garbage Collections:** correlate pause times and GC events with latency spikes.

On the timeline, each thread has a row and event bars represent time spent waiting. Select long events to inspect the stack trace, thread, lock owner, or host. If multiple events overlap at the same timestamp, check whether they affect the request's critical path.

## 5. Analyzing Recordings with jfr in the Terminal

### 5.1. Viewing the Recording Summary

~~~bash
jfr summary thread-latency.jfr
~~~

The summary shows recording duration, per-event counts, and data size. If expected events are missing, check the recording template and event settings before concluding the application did not exhibit that behavior.

### 5.2. Printing Thread-Stall Events

~~~bash
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite --stack-depth 32 thread-latency.jfr
~~~

Filter to a single event type for readability:

~~~bash
jfr print --events jdk.JavaMonitorEnter --stack-depth 32 thread-latency.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite thread-latency.jfr
jfr print --events jdk.ThreadPark,jdk.ThreadSleep thread-latency.jfr
~~~

A monitor contention event may look like:

~~~text
jdk.JavaMonitorEnter {
  startTime = 19:52:46.716
  duration = 85.3 ms
  monitorClass = java.lang.Object
  previousOwner = "fixture-lock-holder"
  eventThread = "fixture-lock-waiter"
  stackTrace = [
    ThreadLatencyFixture.lambda$main$1()
    java.lang.Thread.run()
  ]
}
~~~

Here, `fixture-lock-waiter` waited roughly 85 ms to acquire the monitor held by `fixture-lock-holder`. The stack trace shows where the waiter thread tried to enter the lock; inspect the owner's code to find the critical section holding the lock too long.

### 5.3. Inspecting CPU and GC

~~~bash
jfr print --events jdk.ExecutionSample,jdk.NativeMethodSample,jdk.ThreadCPULoad,jdk.CPULoad thread-latency.jfr
jfr print --events jdk.GCPhasePause,jdk.GarbageCollection thread-latency.jfr
~~~

If your JDK provides built-in summary views, list them first:

~~~bash
jfr help view
~~~

Some JDK releases include views such as `latencies-by-type`, `contention-by-thread`, `contention-by-site`, `socket-reads-by-host`, and `thread-cpu-load`. When available, you can run:

~~~bash
jfr view latencies-by-type thread-latency.jfr
jfr view contention-by-thread thread-latency.jfr
jfr view contention-by-site thread-latency.jfr
~~~

The list of built-in views varies by JDK release. If a needed view is not available, use `jfr print` or open the file in JMC. `jfr metadata` lets you inspect event names, categories, and field layouts in a recording.

## 6. Interpreting Results and Finding Root Causes

| Symptom in Recording | Hypothesis to Test | Next Step |
|---|---|---|
| Many long `JavaMonitorEnter` on the same lock | Critical section holds monitor too long | Find `previousOwner`, stack trace, and code inside the synchronized block |
| Many long `JavaMonitorWait` | Thread waiting on an unmet notification/condition | Check notifier, timeout, queue, and signaling logic |
| Many `ThreadPark` on workers | Workers waiting on queue, Future, semaphore, or lock | Inspect executor, queue depth, and producer/consumer stack traces |
| Long `SocketRead` on request threads | Waiting on upstream or network | Group by host/port, correlate with upstream latency and network metrics |
| Long `SocketWrite` | Slow-reading peer or backpressure | Inspect consumer, buffers, and network throughput |
| Long `FileRead`/`FileWrite` | Slow file/storage I/O | Check file path, storage latency, and stack trace |
| Many `ExecutionSample` in one method, high CPU | CPU-bound code | Use Hot Methods/Call Tree and profile the method |
| GC pauses coincide with slow requests | Stop-the-world pauses contributing to latency | Inspect `GCPhasePause`, pause times, and allocation pressure |
| No stall events but high CPU | Time spent mostly in running code | Analyze execution samples and CPU metrics |

### 6.1. Finding Lock Contention

Start from `JavaMonitorEnter` events with long durations. Note:

- The waiting thread (`eventThread`).
- The thread that previously held the lock (`previousOwner`).
- The monitor class and the waiting thread's stack trace.
- The lock address to correlate events on the same monitor within a recording.

Then inspect the owner's stack in events or the thread timeline around the same timestamp. The owner may be performing I/O, logging, invoking callbacks, or running slow logic inside a synchronized block. If multiple waiters queue behind the same owner, that critical section may be limiting concurrency.

Do not conclude a deadlock from contention alone. A deadlock is a cycle of lock waits; contention may simply be one thread holding a lock for a long time before releasing it.

### 6.2. Finding I/O Bottlenecks

Group `SocketRead`/`SocketWrite` by host and thread. If one host accounts for most of the wait time, cross-reference that service's metrics. Check byte counts, read/write counts, and stack traces to identify which requests generate the I/O.

For file I/O, check which files are read/written most and the duration of each event. A slow log file or storage volume can block many workers if the application performs synchronous I/O.

The sum of I/O durations across multiple threads can exceed the recording duration because events occur concurrently. Do not add up durations across all threads and treat the total as wall-clock application slowdown.

### 6.3. Finding CPU Bottlenecks

When CPU load is high, inspect `ExecutionSample` and `NativeMethodSample`. Group stacks by method to find code accumulating the most samples. Use JMC Hot Methods and Call Tree to trace from hot methods back to callers.

Sampling shows which methods appear frequently at sample points; it is not an absolute measurement of per-method execution time. Compare with process and machine CPU metrics to confirm whether the JVM or another process is consuming CPU.

### 6.4. Checking Virtual Threads on JDK 21

JDK 21 includes the `jdk.VirtualThreadPinned` event. This event records when a virtual thread is pinned to its carrier thread longer than the default 20 ms threshold. While pinned, the carrier cannot be released to run other virtual threads.

On JDK 21, blocking operations inside a `synchronized` block/method or a native/foreign method can cause pinning. If your application uses virtual threads, filter for these events:

~~~bash
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed thread-latency.jfr
~~~

Prolonged, repeated pinning can degrade server scalability. Inspect the stack trace and the operation causing pinning; consider replacing long-held synchronized blocks around I/O with an appropriate lock mechanism after confirming via a recording. Pinning rules change across JDK releases, so verify against the exact version you are running.

Virtual threads help an application handle many concurrent I/O-bound tasks and improve throughput; they do not make CPU-bound code run faster or automatically reduce the latency of an individual request.

## 7. Customizing Thresholds to Catch Short Events

JFR duration events may be filtered by a threshold in the template. If the threshold is 10 ms, a 2 ms event will not be recorded. Specific thresholds depend on the event and template; JDK 21 documentation notes that default synchronization events in JMC are above 10 ms, whereas many Java Application events have different thresholds.

Check the active settings:

~~~bash
jcmd 12345 JFR.check name=thread-latency verbose=true
~~~

If you need to observe shorter contention, you can lower thresholds for a short recording:

~~~bash
jcmd 12345 JFR.start name=short-contention settings=profile duration=20s filename=short-contention.jfr jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms jdk.SocketRead#threshold=5ms jdk.SocketWrite#threshold=5ms
~~~

Or create a reusable configuration file:

~~~bash
jfr configure --input "$JAVA_HOME/lib/jfr/profile.jfc" --output latency.jfc jdk.JavaMonitorEnter#threshold=5ms jdk.JavaMonitorWait#threshold=5ms jdk.ThreadPark#threshold=5ms jdk.SocketRead#threshold=5ms jdk.SocketWrite#threshold=5ms
~~~

Then pass this configuration file to `JFR.start` with `settings=/path/to/latency.jfc`. Lower thresholds generate more events, increase recording size, and can raise overhead. Lower thresholds only for the events under investigation, record briefly, and monitor the impact.

Do not enable heap statistics while measuring latency unless you need heap data. That option can trigger an old GC at the start and end of the recording, introducing pauses that skew your measurements.

## 8. Hands-On Java 17+: Generating Multiple Types of Thread Latency

The following example creates threads to observe:

- `fixture-lock-holder` holds a monitor for a while; `fixture-lock-waiter` repeatedly waits for that monitor.
- `fixture-monitor-wait` calls `Object.wait` with a timeout.
- `fixture-parker` uses `LockSupport.parkNanos`.
- `fixture-sleeper` uses `Thread.sleep`.
- `fixture-socket-reader` waits for bytes from a loopback socket.
- `fixture-cpu-worker` runs a computation loop to generate CPU samples.

Create `ThreadLatencyFixture.java`:

~~~java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;

public final class ThreadLatencyFixture {
    private static final Object LOCK = new Object();
    private static volatile boolean running = true;
    private static volatile long checksum;

    public static void main(String[] args) throws Exception {
        ServerSocket server = new ServerSocket(
            0, 16, InetAddress.getLoopbackAddress()
        );

        Thread lockHolder = new Thread(() -> {
            while (running) {
                synchronized (LOCK) {
                    try {
                        Thread.sleep(90);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                pause(5);
            }
        }, "fixture-lock-holder");

        Thread lockWaiter = new Thread(() -> {
            while (running) {
                synchronized (LOCK) {
                    checksum++;
                }
                pause(5);
            }
        }, "fixture-lock-waiter");

        Thread monitorWaiter = new Thread(() -> {
            Object waitLock = new Object();
            while (running) {
                synchronized (waitLock) {
                    try {
                        waitLock.wait(55);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
            }
        }, "fixture-monitor-wait");

        Thread parker = new Thread(() -> {
            while (running) {
                LockSupport.parkNanos(55_000_000L);
            }
        }, "fixture-parker");

        Thread sleeper = new Thread(() -> {
            while (running) {
                pause(55);
            }
        }, "fixture-sleeper");

        Thread socketReader = new Thread(() -> {
            try (Socket socket = server.accept()) {
                while (running && socket.getInputStream().read() != -1) {
                    // Wait for the next byte from the local client.
                }
            } catch (Exception e) {
                if (running) {
                    throw new RuntimeException(e);
                }
            }
        }, "fixture-socket-reader");

        Thread socketWriter = new Thread(() -> {
            try (Socket socket = new Socket(
                    InetAddress.getLoopbackAddress(), server.getLocalPort())) {
                while (running) {
                    socket.getOutputStream().write(1);
                    socket.getOutputStream().flush();
                    pause(65);
                }
            } catch (Exception e) {
                if (running) {
                    throw new RuntimeException(e);
                }
            }
        }, "fixture-socket-writer");

        Thread cpuWorker = new Thread(() -> {
            long value = 1;
            while (running) {
                value = value * 1664525 + 1013904223;
                checksum ^= value;
            }
        }, "fixture-cpu-worker");

        Thread[] threads = {
            lockHolder, lockWaiter, monitorWaiter, parker,
            sleeper, socketReader, socketWriter, cpuWorker
        };

        for (Thread thread : threads) {
            thread.setDaemon(true);
            thread.start();
        }

        System.out.println("ThreadLatencyFixture ready");
        new CountDownLatch(1).await();
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
~~~

Compile and run in the first terminal:

~~~bash
javac --release 17 -d out ThreadLatencyFixture.java
java -cp out ThreadLatencyFixture
~~~

Exact stdout:

~~~text
ThreadLatencyFixture ready
~~~

The program stays running so you have time to capture a recording. This is a test workload that intentionally creates waits; do not use this logic in production applications.

In the second terminal, find the PID and capture an 8-second recording:

~~~bash
jcmd -l
jcmd 12345 JFR.start name=thread-latency settings=profile duration=8s filename=thread-latency.jfr
~~~

Once the recording finishes:

~~~bash
jfr summary thread-latency.jfr
jfr print --events jdk.JavaMonitorEnter,jdk.JavaMonitorWait,jdk.ThreadPark,jdk.ThreadSleep,jdk.SocketRead,jdk.ExecutionSample thread-latency.jfr
~~~

If your JDK includes summary latency views:

~~~bash
jfr help view
jfr view latencies-by-type thread-latency.jfr
jfr view contention-by-thread thread-latency.jfr
~~~

In the fixture recording, you will see monitor contention events associated with `fixture-lock-waiter` and owner `fixture-lock-holder`; socket read events associated with `fixture-socket-reader`; and park/wait/sleep events associated with their respective threads. CPU samples will appear for threads executing code and may also include JIT compiler threads.

Stop the fixture with `Ctrl+C` in the first terminal after collecting the data.

## 9. Latency Investigation Workflow in Real Applications

1. Identify the slow request or operation using metrics/APM; record p50, p95, p99, and when it occurred.
2. Identify the affected JVM/PID, JDK release, workload, and instance.
3. Start JFR before or during the incident window; choose `default` for continuous recording or `profile` for a short investigation.
4. Use JMC Automated Analysis Results and Threads/Latencies to find which event types dominate time.
5. Group events by thread, lock, stack site, or host; inspect long, recurring events on the critical path.
6. If lock contention appears, find the owner and the code holding the lock; if socket/file I/O appears, correlate with dependency and storage metrics.
7. If CPU is high, analyze execution samples, Hot Methods, and Call Tree.
8. If GC pauses coincide with spikes, inspect `GCPhasePause` and total pause time.
9. Correlate with application logs, trace IDs, request metrics, and a baseline recording from a normal period.
10. Change one confirmed cause, re-run the same workload, and compare p95/p99 along with the event profile.

JFR does not automatically know which HTTP request an event belongs to unless the application records request context. When you need to tie events to business operations, use distributed tracing or emit a custom JFR event with a controlled request/operation identifier. Do not put sensitive data into custom events.

## 10. Limitations and Common Pitfalls

| Symptom | Possible Cause | How to Address |
|---|---|---|
| No lock events visible | Event disabled, threshold too high, or contention too short | Check `JFR.check verbose=true` and lower thresholds in a short recording |
| No SocketRead/SocketWrite visible | Template does not enable the event or I/O duration is below threshold | Check event settings and enable the event in the configuration |
| High latency but no stall events | CPU-bound, event not enabled, or waits below threshold | Inspect `ExecutionSample`/CPU load and verify the template |
| Many ThreadSleep events while app is healthy | Scheduled sleeps or intentional polling | Check whether those threads are on the critical path |
| JavaMonitorWait mistaken for lock contention | `Object.wait` is condition waiting and releases the monitor | Distinguish from `JavaMonitorEnter`; inspect notifier and timeout |
| Cannot attach with jcmd | Wrong PID, different user/group, or wrong container namespace | Run on the same host/user as the JVM and verify the PID |
| No .jfr file created | Recording not stopped yet, wrong working directory, or missing write permission | Check `JFR.check`/`JFR.stop` and the file path |
| Very large recording file | Recording too long, too many events, or threshold too low | Bound `duration`/`maxage`/`maxsize` and enable only needed events |
| JFR impacts measured latency | Detailed profile, overly low threshold, or heap statistics enabled | Use `default` when appropriate, shorten the recording, and disable heap statistics |
| jfr view does not exist | Built-in views vary by JDK release | Run `jfr help view` or use `jfr print`/JMC |

### 10.1. Event Thresholds Can Hide Short Waits

Many duration events are not recorded if their duration is below the threshold. Therefore, a recording without long `JavaMonitorEnter` events does not prove the system has no lock contention. Check event thresholds and consider lowering them to a few milliseconds in a short recording.

Do not set low thresholds for all events in a long recording without measuring overhead. More events produce larger files and can increase collection cost.

### 10.2. Protecting Flight Recordings

A JFR file can contain stack traces, class/method names, thread names, hosts/IPs, file paths, system properties, and environment details. Store recordings only in authorized locations, restrict read access, and sanitize data before sharing externally. Delete files according to your retention policy once the investigation is complete.

## 11. Pre-Conclusion Checklist

- [ ] Identified request latency via metrics/APM.
- [ ] Verified the correct PID, JVM instance, and JDK release.
- [ ] Recording covers the incident window.
- [ ] Template and thresholds enable the events needed for investigation.
- [ ] Distinguished `JavaMonitorEnter` from `JavaMonitorWait`.
- [ ] Identified waiter thread, lock owner, and stack site when contention is present.
- [ ] Checked `SocketRead`/`Write` and `FileRead`/`Write` when I/O is suspected.
- [ ] Checked `ExecutionSample`/CPU load when CPU-bound behavior is suspected.
- [ ] Correlated GC pauses if timestamps align with latency spikes.
- [ ] Checked `VirtualThreadPinned` if using virtual threads on JDK 21.
- [ ] Did not treat summed event durations across multiple threads as end-to-end request latency.
- [ ] Cross-referenced logs, traces, and a baseline recording.
- [ ] Recording did not enable heap statistics unnecessarily during latency measurement.
- [ ] JFR files are secured and deleted according to retention policy.

## 12. Takeaways

JFR helps reveal both time threads spend blocked and time threads spend executing code. Start with duration events such as `JavaMonitorEnter`, `JavaMonitorWait`, `ThreadPark`, `ThreadSleep`, `SocketRead`, and `FileRead` to locate wait intervals. When stall events are scarce but CPU is high, inspect `ExecutionSample` and Hot Methods. If GC pauses coincide with spikes, analyze `GCPhasePause`.

Use JMC to inspect timelines, Latencies, Contention, and I/O; use `jfr summary` and `jfr print` to filter events in the terminal. Lower thresholds only when you need to observe short waits, and monitor overhead. Finally, correlate JFR with request metrics and traces: duration events explain where threads paused, while request latency must still be measured at the application level.

References:

- [Diagnostic Tools — Java SE 21: Flight Recorder](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [The jcmd Command — Java SE 21: JFR.start/JFR.dump/JFR.stop](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [The jfr Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html)
- [Troubleshoot Performance Issues Using Flight Recorder — Java SE 21](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf)
- [Virtual Threads — Java SE 21: JFR Events and Pinning](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html)
- [Java Mission Control and Flight Recorder Demo Series — Latencies/Contention](https://www.oracle.com/webfolder/technetwork/tutorials/obe/java/mc-jfr/index.html)