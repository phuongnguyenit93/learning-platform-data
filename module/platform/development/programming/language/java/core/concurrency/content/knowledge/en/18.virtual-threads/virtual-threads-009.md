# Pinning with Monitors and Native Code in Java 21

> **Scope:** Java SE 21, virtual threads per JEP 444. This article focuses on JVM mechanics and Java concurrency APIs; it does not cover Spring configuration or integration.

## 1. What Is Pinning and Why Does It Matter?

A virtual thread is a lightweight `java.lang.Thread` scheduled by the JVM. When running, a virtual thread is **mounted** onto a platform thread (commonly called a **carrier thread**). Many virtual threads can take turns using a much smaller number of carrier threads. This model is especially beneficial when tasks must wait on I/O: if the blocking operation is supported by the JDK, the JVM can **unmount** the virtual thread, freeing the carrier to run other tasks.

**Pinning** is a situation in which a virtual thread cannot unmount from its carrier during a given execution segment. Being pinned does not by itself cause correctness bugs. The problem arises when a virtual thread **blocks while pinned**: the carrier must also wait, reducing the number of carriers available to serve other virtual threads.

Normal flow when waiting on I/O:

~~~text
Virtual thread A ── running on carrier #1 ── hits blocking point
                                                   ↓
                                        A unmounts / waits
Carrier #1 ── idle ── runs virtual threads B, C, ...
                                                   ↓
                                        A's I/O completes
Virtual thread A ── remounted onto an available carrier
~~~

Pinned case:

~~~text
Virtual thread A ── inside monitor/native frame
             ↓
          hits long blocking point
             ↓
A cannot unmount → carrier #1 is also held while waiting
             ↓
Fewer carriers to run B, C, ... → throughput/latency may degrade
~~~

Three concepts should be kept distinct:

- **Blocking**: a task must wait for a condition, such as `Thread.sleep`, socket I/O, or acquiring a lock. Blocking does not automatically mean pinning; many blocking operations can yield the carrier.
- **Pinning**: a technical constraint that prevents a virtual thread from leaving its carrier at that moment. Pinning is only a real concern when the wait is long or occurs frequently.
- **Lock contention/deadlock**: issues of coordinating access to resources. Changing the locking mechanism can resolve carrier pinning, but it does not automatically solve lock contention, deadlocks, connection limits, or other bottlenecks.

Virtual threads do not make the CPU run faster and do not eliminate the cost of slow I/O; their main benefit is reducing the number of OS threads sitting idle while waiting.

## 2. Two Major Sources of Pinning in Java 21

### 2.1. `synchronized` and JVM Monitors

In JDK 21, when a virtual thread executes code inside a `synchronized` method or block, it is pinned to its carrier. If a blocking operation that normally supports unmounting occurs while holding the monitor, unmounting **cannot happen**; the carrier is held for the duration of the wait.

Example:

~~~java
private final Object guard = new Object();

void updateAndWait() throws InterruptedException {
    synchronized (guard) {
        // Small state updates are usually not a concern.
        Thread.sleep(200); // On Java 21: waiting while holding a monitor -> carrier is pinned.
    }
}
~~~

This is an **illustrative snippet inside a class**, not a standalone runnable program. `Thread.sleep` simulates a blocking operation; in a real application, a slow I/O call inside a `synchronized` region can have a similar effect.

**Do not conclude that all `synchronized` usage is bad.** A monitor block that only updates a few in-memory variables and finishes very quickly rarely causes significant issues. What to look for is **long or frequent blocking while holding a monitor**. `synchronized` methods have the same issue: the monitor scope covers the entire method body, including indirect calls that may block.

Monitors still guarantee normal mutual exclusion and happens-before rules. Pinning is a characteristic of the virtual thread execution mechanism in JDK 21; it does not change the synchronization contract or introduce data races by itself.

### 2.2. Native Methods and Foreign Functions

JDK 21 can also pin a virtual thread while it is executing a **native method** (for example via JNI) or a **foreign function** (an interface for calling code outside the JVM). While native code remains on the stack, the JVM cannot arbitrarily detach the virtual thread's continuation as it does at supported Java blocking points.

Example real-world scenario:

~~~text
Virtual thread
    └─ Java wrapper
         └─ JNI / foreign call
              └─ native library waits on socket, lock, or device for 500 ms
                   └─ carrier is occupied during the wait
~~~

Not every native method call causes an application problem: a very fast native call may be negligible. You need to measure the **duration and frequency of waiting inside the native segment**. Replacing an outer Java monitor around a JNI call with `ReentrantLock` does not eliminate pinning caused by the native frame itself.

In Java 21, the Foreign Function & Memory API is still in **preview** (JEP 442); this article only examines the nature of native interaction and does not require using the preview API.

## 3. Why Does Pinning Reduce Scalability?

Suppose the scheduler has a finite number of carriers, and many virtual threads are serving independent I/O tasks:

1. If a virtual thread waits on I/O and unmounts successfully, the carrier is reused for another task; the number of waiting tasks can be much larger than the number of OS threads.
2. If each task enters a monitor and then waits 200 ms while pinned, a carrier must wait along with each task.
3. When many carriers are pinned at the same time, other virtual threads may have to wait for their turn to run, even if they do not contend for the same monitor or resource.
4. The result can be lower throughput, growing queues, and higher tail latency. The severity depends on load, blocking duration, carrier count, and other bottlenecks.

**Note:** increasing the number of carriers or changing scheduler configuration is not a root-cause fix. Creating more OS threads may partially mask symptoms while increasing resource consumption. First, identify the code paths that block while pinned.

## 4. Runnable Java 21 Example: Monitor vs. `ReentrantLock`

Create the file **`PinningJava21Demo.java`**:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public class PinningJava21Demo {
    private static final Object MONITOR = new Object();
    private static final ReentrantLock LOCK = new ReentrantLock();

    public static void main(String[] args) throws InterruptedException {
        Thread monitorThread = Thread.ofVirtual()
                .name("monitor-demo")
                .start(() -> {
                    synchronized (MONITOR) {
                        pause(150);
                    }
                });
        monitorThread.join();

        Thread lockThread = Thread.ofVirtual()
                .name("reentrant-lock-demo")
                .start(() -> {
                    LOCK.lock();
                    try {
                        pause(150);
                    } finally {
                        LOCK.unlock();
                    }
                });
        lockThread.join();

        System.out.println("Hoàn tất hai ví dụ");
    }

    private static void pause(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Tác vụ bị ngắt", ex);
        }
    }
}
~~~

Compile and run with **JDK 21** (no `--enable-preview` needed):

~~~bash
javac PinningJava21Demo.java
java PinningJava21Demo
~~~

Standard output of the program if not interrupted:

~~~text
Hoàn tất hai ví dụ
~~~

Explanation:

- `Thread.ofVirtual().start(...)` creates and starts a virtual thread. `join()` makes the program wait for each demo section to finish.
- The first section holds an **intrinsic monitor** during `Thread.sleep(150)`. On Java 21, this illustrates pinning: the sleep operation cannot yield the carrier because it is inside a `synchronized` region.
- The second section holds a **`ReentrantLock`** while sleeping. `Thread.sleep` can unmount the virtual thread normally because holding a `ReentrantLock` does not by itself pin the carrier the way a monitor does in Java 21.
- `finally` ensures the lock is released even if the logic inside the locked region throws an exception. Omitting `unlock()` can leave the lock stuck logically.
- This is a **mechanics demo**, not a benchmark: the two tasks run sequentially and will finish in roughly similar times. The difference is that the carrier is released while waiting, not the number of milliseconds slept or the stdout line.

In practice, using `ReentrantLock` still requires preserving critical section correctness; unmounting a virtual thread does not mean the lock has been released. Other tasks needing that same lock still have to wait.

## 5. Observing Pinning with JDK 21 Tools

### 5.1. Stack Traces: `jdk.tracePinnedThreads`

Run on JDK 21:

~~~bash
java -Djdk.tracePinnedThreads=full PinningJava21Demo
~~~

The JDK can print a stack trace when a virtual thread performs a blocking operation while pinned, highlighting native frames and frames holding monitors. Look for frames near the `synchronized`/`pause` lines of the demo; **do not rely on an exact stack trace**, because frame names, line numbers, and ordering can vary across JDK builds.

Short mode:

~~~bash
java -Djdk.tracePinnedThreads=short PinningJava21Demo
~~~

- `full`: more frames, useful for finding the full call path and where the monitor is held.
- `short`: briefer output, useful for quick screening.
- This property is for Java 21 diagnostics; do not assume its behavior or support is identical across all later JDK versions.

**Important:** seeing no stack traces does not prove the application has no performance problems. Some scenarios do not hit a blocking point, only occur under load, or are not captured by this tool in the way you expect.

### 5.2. Java Flight Recorder: `jdk.VirtualThreadPinned`

Collect a JFR recording when running the demo:

~~~bash
java -XX:StartFlightRecording=filename=pinning.jfr,dumponexit=true PinningJava21Demo
jfr print --events jdk.VirtualThreadPinned pinning.jfr
~~~

In JDK 21, the `jdk.VirtualThreadPinned` event is enabled by default with a **20 ms duration threshold** in standard recording configurations. It records when a virtual thread is pinned longer than the threshold during a blocking operation. With a 150 ms sleep inside a monitor, the demo is designed to exceed this threshold; whether the event appears in practice also depends on the recording environment and JFR configuration.

When reading events, pay attention to duration, timestamp, the virtual thread involved, and the stack trace. Cross-reference the stack trace with the monitor acquisition site or native call. You can filter and analyze JFR recordings with JDK Mission Control when you need to inspect a full load profile.

If no events appear, verify that the recording was actually created, check the event/threshold configuration, and confirm that the workload actually exercised the blocking branch. Do not interpret a short, low-load run as proof that the system never pins.

### 5.3. Measure Impact, Not Just Event Counts

In a test environment simulating realistic traffic, evaluate these together:

- **Pinning frequency/duration**: where events occur, and whether they repeat frequently or last long.
- **Service capacity**: throughput, average latency, p95/p99, and abnormal spikes.
- **Carriers and queuing**: whether many tasks are waiting for a turn to run due to finite carriers.
- **Independent bottlenecks**: DB connection pools, socket/file descriptor limits, shared locks, slow downstream APIs, or CPU saturation.

Fix only the pinning sites that actually have an impact rather than doing a project-wide replacement of `synchronized`.

## 6. Fixing Pinning Based on Root Cause

### Approach 1: Move I/O Outside `synchronized` When Invariants Allow

Illustrative before–after example (this is **sample code** and must be adapted to the state consistency requirements of your specific application):

~~~java
// Before: slow I/O is inside the monitor.
synchronized (guard) {
    updateState();
    sendSlowRequest();
}

// After: only protect the state operation; perform I/O outside.
synchronized (guard) {
    updateState();
}
sendSlowRequest();
~~~

The latter reduces monitor hold time and avoids monitor-induced pinning during I/O, but it is **valid only if business rules do not require updating state and sending the request to be atomic with each other**. If you need transactional guarantees, ordering, data snapshots, or race prevention, design an appropriate mechanism (snapshot, queue, state machine, etc.); do not arbitrarily move calls out of a critical section.

### Approach 2: Replace Monitors That Must Enclose Blocking with `ReentrantLock`

~~~java
// Illustration inside a class with a ReentrantLock field named lock.
lock.lock();
try {
    blockingOperation();
} finally {
    lock.unlock();
}
~~~

`ReentrantLock` allows a virtual thread to wait at supported blocking points without being pinned by an **intrinsic monitor**; this is the approach recommended in Java 21 documentation for lock regions with long and frequent blocking.

However, review the contract before switching:

- `synchronized` releases the monitor automatically when exiting scope; `ReentrantLock` requires `unlock()` in `finally`.
- `wait()/notify()/notifyAll()` are tied to intrinsic monitors and cannot be copied verbatim. With explicit locks, the corresponding wait/signal mechanism is `Condition`, and the wait condition must be redesigned properly.
- Reentrant locks do not solve contention for the same resource: multiple virtual threads needing the same lock still have to queue up.
- Avoid holding a lock across I/O if the work can be reorganized more safely and simply.

### Approach 3: For Native/JNI/Foreign Calls, Address the Cause Outside the JVM

If a native library frequently blocks for a long time:

1. Measure time spent in the native call and look for a non-blocking/asynchronous API version if available.
2. Avoid holding extra Java monitors across the call unnecessarily.
3. Consider offloading blocking native work to a **bounded pool of platform threads** or a dedicated load-controlled component if the API cannot be changed yet. This isolates OS thread demand, **it does not make the native call non-blocking**.
4. Limit concurrent tasks according to native resource capacity; handle timeouts, cancellation, and backpressure according to the API contract.

Changing `synchronized` to `ReentrantLock` in a wrapper **does not by itself eliminate native pinning**. Likewise, increasing the number of virtual threads does not give the native library more resources.

### Approach 4: Consider the JDK Version When Possible

**JDK 21–23** have the monitor-related pinning limitation described above. **JDK 24** introduces **JEP 491 — Synchronize Virtual Threads without Pinning**: a virtual thread can release its carrier when blocking in many `synchronized` scenarios where JDK 21 had to pin.

This **does not eliminate every source of pinning**: native/foreign interactions and other JVM cases still need to be checked. When an application must run on **Java 21** in production, diagnose and handle it according to Java 21 behavior; do not backport JDK 24 expectations.

## 7. Common Misconceptions and Mistakes

| Misconception | Accurate Understanding in Java 21 |
|---|---|
| “Using `synchronized` breaks virtual threads.” | Monitors remain correct for synchronization; the concern is when a virtual thread blocks **for a long time or frequently** while pinned. |
| “Every blocking call causes pinning.” | Many JDK-supported blocking operations unmount the virtual thread; pinning depends on monitor/native context. |
| “`ReentrantLock` makes all threads using the lock run in parallel.” | The lock is still mutually exclusive. Only the carrier can be freed when a virtual thread blocks at a supported point. |
| “Switching a Java wrapper to `ReentrantLock` fixes JNI pinning.” | An active native frame can still pin; you must examine the native call and how it executes. |
| “No `jdk.VirtualThreadPinned` events means no pinning.” | The event has a threshold, configuration, and load dependence; absence of events does not mean zero pinning. |
| “Increasing virtual thread count automatically increases throughput.” | Carriers, CPU, locks, connection pools, and downstream services remain real limits; measure under load. |
| “Java 24 eliminates all carrier pinning issues.” | JEP 491 addresses monitor-induced pinning; other cases remain, especially native/foreign code. |

## 8. Checklist for Auditing a Java 21 System

1. **Confirm the actual runtime** with `java -version`. Do not infer Java 21 behavior from runs on JDK 24+.
2. **Locate suspicious sites**: `synchronized` methods/blocks wrapping socket/DB/file I/O, sleep, or native calls that may block.
3. **Reproduce with a realistic workload**; enable JFR and, when needed, `-Djdk.tracePinnedThreads=full` to correlate events with stack traces.
4. **Prioritize by impact**: pinning frequency, carrier hold duration, and effect on p95/p99/throughput.
5. **Apply the minimal fix that preserves semantics**: narrow monitor scope, move I/O outside when safe, use `ReentrantLock` properly, or isolate native blocking.
6. **Re-measure and verify concurrency correctness**: shared data, operation ordering, race conditions, wait times, timeouts, and resource limits. Conclude improvement only when post-change metrics confirm it.

## 9. Key Takeaways

**Pinning is not a deadlock, nor is it a bug in `Thread.sleep` or `synchronized` specifically.** In Java 21, it is a consequence of a virtual thread being unable to unmount while inside certain monitor-holding contexts or native frames. If that context also encloses a long blocking point, the carrier is held waiting, negating the scalability advantage of virtual threads for I/O-bound tasks.

Focus on **blocking inside pinned regions**, prove it with JFR/traces, and fix it in accordance with your program's synchronization constraints. Short, purely in-memory `synchronized` regions can usually be left as they are.

## References

- [JEP 444 — Virtual Threads, standardized in JDK 21](https://openjdk.org/jeps/444).
- [Oracle Java SE 21 — Virtual Threads: scheduling, pinning, and diagnostics](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).
- [OpenJDK JEP 491 — Synchronize Virtual Threads without Pinning (JDK 24)](https://openjdk.org/jeps/491).
- [Dev.java — Virtual Threads, pinning limitations by JDK version](https://dev.java/learn/new-features/virtual-threads/).
