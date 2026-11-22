# Carrier Threads and JVM Scheduling in Virtual Threads

## 1. The Big Picture: Who Schedules Whom?

Since Java 21, a **virtual thread** is an official kind of `java.lang.Thread`. It helps applications create many concurrent task threads, especially when most of the time is spent waiting on I/O, without needing a dedicated operating system (OS) thread for each task. A virtual thread still executes Java code on the CPU through a **platform thread**; the JVM does not create CPUs or execute code "outside" an OS thread.

Three roles to distinguish:

| Component | Role | Key Point |
| --- | --- | --- |
| Virtual thread | Logical execution unit created by application code, typically one task per thread | Has its own identity, stack, `ThreadLocal`, and state; does not own an OS thread for its entire lifecycle |
| Carrier thread | A platform thread currently **carrying** a virtual thread while the virtual thread's code runs | One carrier can sequentially run multiple virtual threads; the same virtual thread can run on different carriers |
| JVM scheduler and OS scheduler | The JVM selects a virtual thread to **mount** onto a carrier; the OS selects when a platform/carrier thread is run by a CPU | Two different scheduling layers, with no fixed one-to-one mapping |

Conceptual diagram (the arrows depict different points in time, not all virtual threads running simultaneously):

```text
Application:  VT-A   VT-B   VT-C   VT-D   VT-E ... VT-N
                \      |      /       \      /
                 JVM virtual-thread scheduler
                          |
             +------------+------------+
             |                         |
          Carrier-1                 Carrier-2   ... (platform threads)
             |                         |
             +----- OS scheduler ------+
                          |
                       CPU cores
```

**Mount** is when the JVM attaches a virtual thread's execution context to a carrier so it can run. **Unmount** is when the JVM detaches that context, typically when the virtual thread waits on an operation that supports the suspension mechanism. The newly freed carrier can run another virtual thread. That is how **M virtual threads are multiplexed onto N platform threads** (M:N scheduling).

Virtual thread scheduling is a JDK implementation detail. The descriptions of `ForkJoinPool`, configuration parameters, and observable events in this article apply to modern OpenJDK/HotSpot implementations; they should not be treated as fixed guarantees across all JVMs.

## 2. A Mount → Park → Unmount → Remount Lifecycle

Consider a virtual thread reading data through a JDK-supported blocking I/O API:

1. The application calls `Thread.start()` or submits a task to `Executors.newVirtualThreadPerTaskExecutor()`. The virtual thread is placed into the ready-to-run work queue.
2. The JVM scheduler picks an available carrier and mounts the virtual thread. The code runs normally; in application code, `Thread.currentThread()` still returns the **virtual thread**, not the carrier.
3. The task calls a waiting operation, such as reading from a socket when no data is available yet. The JDK can **park/unmount** the virtual thread, saving the stack continuation state and yielding the carrier. Not every "blocking" call is guaranteed to unmount; it depends on the type of operation and the JDK version.
4. When I/O is ready, a timeout expires, or an appropriate wakeup signal arrives, the JDK makes the virtual thread **runnable** again and returns it to the scheduler.
5. The scheduler remounts it onto **any available carrier**. Execution resumes after the wait point and then completes like a normal thread.

```text
New VT -> runnable -> mounted/running -> waiting for I/O
                        ^                       |
                        |                       v
                        +--- runnable <- parked/unmounted
                             (awakened)
```

A virtual thread can park and resume many times; the carrier upon resume **does not have to be the previous carrier**. You must distinguish between "awakened and waiting in the runnable queue" and "immediately executing on a CPU": the JVM scheduler still needs to pick a carrier, and the OS still needs to schedule that carrier to run.

This does not change the semantics of `synchronized`, `volatile`, `Lock`, `interrupt`, or Java's happens-before rules. Virtual threads change how **waiting resources are utilized**, without adding new execution-order guarantees on their own.

## 3. How Does the Default Scheduler Work?

In OpenJDK/HotSpot, the default virtual thread scheduler uses a `ForkJoinPool` following a **work-stealing** model oriented toward asynchronous tasks (FIFO). This pool is dedicated to running virtual thread *continuations* and is **separate** from `ForkJoinPool.commonPool()` used by many other tasks, such as certain `CompletableFuture` operations or parallel streams.

- **Target parallelism**: the number of carrier platform threads the scheduler aims to use to run virtual threads. By default, it is tied to the number of available processors seen by the JVM; it is a **target parallelism level**, not the number of virtual threads allowed to be created.
- **Runnable queue**: virtual threads that are ready but not yet mounted wait for the scheduler. Work-stealing helps carriers share work; it does not promise strict global FIFO ordering across the entire system.
- **Compensation**: when certain blocking activities make carriers unavailable, the implementation may increase the number of platform threads in the scheduler in some situations, subject to configuration and resource limits. This mechanism does not cure every case of pinning or native blocking.
- **OS scheduling**: even with many carriers, the amount of code running concurrently on the CPU still depends on physical CPUs, load, and the operating system's scheduler.

A very long CPU loop is not automatically divided by the virtual-thread scheduler into fair "time slices" for other virtual threads. Virtual threads are not suited as a means to speed up CPU-bound computation; OS preemption of a carrier does not mean the JVM preempts the virtual thread task holding that carrier.

**Mental model example:** 10,000 tasks waiting for socket responses can correspond to 10,000 virtual threads while needing only a small number of carriers *actively executing* code at any given moment. Conversely, 10,000 tasks computing continuously still contend for a finite number of CPU cores. There is no equation where "10,000 virtual threads = 10,000 tasks running on the CPU simultaneously."

## 4. Configuring the Scheduler: Understand Before Tuning

The following properties are **JDK implementation system properties**, passed at JVM startup:

| Property | Meaning | What It Does NOT Mean |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism` | Target parallelism of the scheduler; typically defaults to the number of processors the JVM sees | A limit on the number of virtual threads or business requests |
| `jdk.virtualThreadScheduler.maxPoolSize` | Limit on the number of platform threads the scheduler can use in compensation situations; defaults to 256 in JDK 21/25 | A value you should raise to match task count; a fix for long-blocking code |

Example of running the demo program with the scheduler targeting only two carriers:

```bash
javac CarrierSchedulingDemo.java
java -Djdk.virtualThreadScheduler.parallelism=2 CarrierSchedulingDemo
```

You should start with the defaults, measure queue/running/pinning metrics and throughput before tuning. Trying to raise parallelism on a CPU-bound workload can increase context switching. Setting it too low can cause runnable tasks to queue for a long time if carriers are held by long-running code. Network connection limits, databases, RAM, file descriptors, or external service throughput still need to be managed **separately**; the scheduler does not replace business resource limits.

**Do not confuse** `Executors.newVirtualThreadPerTaskExecutor()` with a pool holding N pre-created virtual threads: this executor creates **a new virtual thread for each task**, while the carrier pool lives at the JDK scheduling layer. Avoid using a fixed thread pool to "pool virtual threads." To limit concurrent access to a resource, use a dedicated mechanism such as a `Semaphore` or a connection pool.

## 5. Java 21+ Experiment: Many Virtual Threads Waiting, Few Carriers Still Progress

The following **CarrierSchedulingDemo.java** file creates 100 virtual threads, has each thread pause at a `CountDownLatch`, and then `main` opens the latch only after all 100 have reached the wait point. In standard execution on JDK 21+, waiting on a latch in a virtual thread does not need to occupy a carrier permanently.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class CarrierSchedulingDemo {
    public static void main(String[] args) throws InterruptedException {
        final int tasks = 100;
        CountDownLatch allWaiting = new CountDownLatch(tasks);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger virtualCount = new AtomicInteger();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < tasks; i++) {
                executor.submit(() -> {
                    if (Thread.currentThread().isVirtual()) {
                        virtualCount.incrementAndGet();
                    }
                    allWaiting.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });
            }

            allWaiting.await();
            System.out.println("Da den diem cho: "
                    + (tasks - allWaiting.getCount()));
            release.countDown();
        } // close() waits for submitted tasks to complete

        System.out.println("Virtual threads: " + virtualCount.get());
    }
}
```

Compile and run:

```bash
javac CarrierSchedulingDemo.java
java -Djdk.virtualThreadScheduler.parallelism=2 CarrierSchedulingDemo
```

**Stdout**:

```text
Da den diem cho: 100
Virtual threads: 100
```

Explanation:

- Each task runs in its own virtual thread; `Thread.currentThread().isVirtual()` checks the thread type accurately. Incrementing the counter happens **before** `countDown()`, so once `main` finishes waiting, the count has already reached 100.
- All tasks reach `release.await()` and suspend. `main` can still proceed, and then `countDown()` wakes up the waiting tasks.
- With `parallelism=2`, the program still allows all 100 virtual threads to reach the wait point. This **does not directly measure** the actual number of carriers and does not prove that every blocking I/O library unmounts; it illustrates how virtual threads share execution capacity.
- `CountDownLatch`, `AtomicInteger`, and the waiting mechanism ensure stable stdout; no specific ordering among the 100 tasks is assumed. In real code, you need to handle or report exceptions from `Future` when you want to detect task failures; `submit` can retain exceptions inside the `Future`.

You can change `tasks` to 1,000 if your environment has enough resources to observe waiting tasks, but avoid drawing benchmark conclusions from a single run. For meaningful comparisons, measure CPU, heap, throughput, latency, and queuing under a realistic workload.

## 6. Pinning: When the Carrier Is Not Released

**Pinning** occurs when a virtual thread is at a wait point but the JVM cannot unmount it, causing the carrier OS thread to be held/blocked along with it. Tasks usually remain logically correct; the main risk is **reduced scalability** when many carriers are held for long periods.

Distinguish between JDK versions:

| Version | What You Need to Know |
| --- | --- |
| **JDK 21–23** | Blocking inside a `synchronized` method/block can pin the carrier. If the wait is long and repeated frequently, this is a throughput issue worth investigating; JDK 21 supports `-Djdk.tracePinnedThreads=short` or `full` for inspection |
| **JDK 24+** | **JEP 491** allows virtual threads to unmount while waiting inside or waiting to acquire a Java monitor (`synchronized`), so the general rule "`synchronized` always causes pinning" no longer applies |
| **Modern JDKs** | Points involving native/foreign-function frames and certain special code paths/operations can still pin; you need to observe on the specific JDK version and platform you are running |

Do not "convert every `synchronized` to `ReentrantLock`" out of habit. On JDK 21–23, consider replacing only **long and frequent blocking sections** if pinning actually causes a bottleneck. On JDK 24+, re-measure because monitor handling has changed. Beyond pinning, **long CPU-bound code** or **native blocking** can also occupy carriers and cause a lack of progress, even though the causes are different.

In particular, code with a lock wrapping I/O will still suffer from **logical lock contention** even without pinning. "Not pinning the carrier" does not mean multiple tasks can enter a critical section together or that downstream services will process faster.

## 7. Observing the Scheduler and Diagnosing Bottlenecks

**JDK 21+:** use the virtual thread support in Java Flight Recorder (JFR) and thread dumps:

```bash
# Running JVM: replace PID with the actual process id
jcmd <PID> Thread.dump_to_file -format=json threads.json

# Example starting an app with JFR recording until the JVM exits
java -XX:StartFlightRecording=filename=recording.jfr,dumponexit=true CarrierSchedulingDemo

jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

- `jdk.VirtualThreadPinned` helps detect cases of blocking while pinned; common JFR configurations enable this event with a 20 ms threshold, so having no events **is not sufficient proof** that there is no short pinning.
- `jdk.VirtualThreadSubmitFailed` reflects failures when submitting a virtual thread task to the scheduler, usually indicating a need to check resource pressure.
- `jdk.VirtualThreadStart`/`jdk.VirtualThreadEnd` are typically not enabled by default because event volume can be huge. Enable them intentionally if you need lifecycle analysis.
- Thread dumps help inspect virtual threads, stacks, and where they are waiting. Do not read the number of virtual threads in a dump as the number of carriers or the number of threads running on the CPU.

**JDK 24+:** adds tools to inspect the scheduler directly:

```bash
jcmd <PID> Thread.vthread_scheduler
jcmd <PID> Thread.vthread_pollers
```

JDK 24 also introduces `jdk.management.VirtualThreadSchedulerMXBean` (JMX), providing metrics such as target parallelism, number of created carriers, estimated currently mounted virtual threads, and queued count; it also supports adjusting target parallelism via the MXBean. These numbers are **point-in-time snapshots/estimates** and cannot be used in isolation to conclude there is a leak or deadlock. The `Thread.vthread_scheduler` command and the MXBean are **not present in JDK 21**.

Interpret symptoms along the causal chain:

1. **Many virtual threads parked** while CPU is low and throughput is normal: typically tasks waiting on I/O or signals; do not assume this is an error on its own.
2. **Many virtual threads runnable/queued** with low throughput: check for CPU-busy carriers, tasks not yielding resources, pinning/native blocking, parallelism level, and resource limits.
3. **Many prolonged pinned events**: find the stack/path to native code or blocking sections, considering the JDK version and frequency.
4. **CPU near saturation**: profile CPU hotspots; increasing the number of virtual threads does not create more cores.
5. **High latency while the scheduler looks healthy**: inspect connection pools, downstream limits, I/O times, timeouts, and the number of concurrent open connections.

## 8. Common Misconceptions

- **"A virtual thread runs without needing an OS thread."** False: when executing code, it runs on a carrier platform thread scheduled by the OS.
- **"Each virtual thread has its own dedicated carrier."** False: many virtual threads share a pool of carriers, and each virtual thread can remount on a different carrier.
- **"Every blocking operation automatically yields the carrier."** False: it depends on unmount support, pinning state, and runtime/native boundaries.
- **"parallelism=2 only allows creating two virtual threads."** False: that is the scheduler's target parallelism, not a cap on the number of tasks.
- **"maxPoolSize is the maximum number of tasks, and increasing it fixes every bottleneck."** False: this property manages the scheduler's platform threads and does not fix blocking/pinning code or external I/O limits.
- **"Call `Thread.currentThread()` to see the carrier."** False: when running inside a virtual thread, that call returns the virtual thread itself.
- **"Virtual threads always run fairly and faster than platform threads."** False: there is no fair time-slicing guarantee at the virtual-thread scheduler layer; their strength is saving resources **while waiting**, not accelerating CPU work.
- **"Since JDK 24, `synchronized` still pins just like in JDK 21."** False: JEP 491 changes Java monitor behavior, though other causes of pinning can still exist.
- **"With a million virtual threads, you can drop all limits."** False: heap, network, sockets, file descriptors, connection pools, timeouts, and external service throughput remain finite.

## 9. When Applying This to Java Programs

Think in terms of **tasks**: if you have many independent pieces of work that spend most of their time waiting on I/O, the one-virtual-thread-per-task model keeps synchronous code readable without tying up a platform thread for the entire wait duration. Choose Java concurrency tools (`ExecutorService`, `Future`, `Semaphore`, `CountDownLatch`, `Lock`, `ThreadLocal`) based on the semantics of the problem; virtual threads do not replace synchronization, cancellation, or backpressure.

To evaluate a real-world application:

1. Identify CPU-bound parts, I/O-bound parts, wait times, and downstream limits.
2. Verify that libraries/I/O use JDK APIs that support park/unmount; do not assume every native call is virtual-thread-friendly.
3. Keep `interrupt` handling, task cancellation, timeouts, and resource management (`try-with-resources`) explicit.
4. Limit access to scarce resources with appropriate mechanisms rather than using "number of virtual threads" as an indirect limiter.
5. Monitor JFR, thread dumps, and (if on JDK 24+) scheduler metrics before tweaking properties.

**Self-check:**

1. If a virtual thread sleeps/waits on I/O and resumes on a different carrier, does `Thread.currentThread()`'s identity change? **No.** The logical thread identity remains the virtual thread.
2. Why do 1,000 parked virtual threads usually not require 1,000 carriers? **Because virtual threads can unmount, yielding their carriers to other runnable work.**
3. Why does the runnable queue grow when the CPU is saturated? **Because virtual threads wait for their turn to mount/run on a finite number of carriers/CPUs; adding more tasks does not increase CPU capacity.**
4. Why is the conclusion "every `synchronized` pins" outdated? **JEP 491 in JDK 24 changed how virtual threads wait on Java monitors without holding the carrier.**

## 10. Official Documentation for Version-by-Version Reference

- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mount/unmount mechanism, older pinning cases, and JFR.
- [Oracle Java 25 — Virtual Threads](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html): operational/adoption guidance and modern pinning behavior.
- [Java 25 — Thread API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): virtual thread characteristics and scheduler system properties.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): design background and the M:N model.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): Java monitor changes starting in JDK 24.
- [Java 25 — VirtualThreadSchedulerMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.management/jdk/management/VirtualThreadSchedulerMXBean.html): scheduler monitoring starting in JDK 24.
