# Java Threads, Platform Threads, and Virtual Threads in the JVM Execution Model

## 1. Objectives and Concept Map

In Java, `java.lang.Thread` represents **a Java thread of execution** with its call stack, state, identity, and interaction rules with the Java Memory Model. However, since **JDK 21**, a `Thread` object is not necessarily bound 1:1 to **an operating-system thread (OS thread)**: Java has **platform threads** and **virtual threads**. A virtual thread is a real Java thread, not a callback task in disguise, but is **scheduled by HotSpot/JDK onto platform threads as carriers** when it needs to run.

Distinguish three levels:

1. **Java thread**: the programming concept in `java.lang.Thread`; has `Thread.currentThread()`, stack trace, interrupt, `ThreadLocal`, monitor ownership, and happens-before semantics.
2. **Platform thread**: a regular Java `Thread` that the JVM binds to an **OS thread** in a 1:1 model in HotSpot; the OS scheduler manages running it on the CPU.
3. **Virtual thread**: a lightweight Java `Thread` that the **JDK scheduler** dynamically maps onto carrier platform threads in a many-virtual-threads-to-few-platform-threads model, via a mount/unmount mechanism when waiting appropriately.

After this lesson, you will know how to:
- Create, `start`, `join`, `interrupt` platform and virtual threads according to the JDK version.
- Explain the difference between a Java thread, OS thread, carrier, thread pool, executor, and task.
- Explain why virtual threads fit **many concurrent I/O-bound tasks**, but do not by themselves make CPU computation faster.
- Understand the relationship between blocking APIs, mount/unmount, scheduler, parking, monitors, pinning, and changes in **JDK 24 (JEP 491)**.
- Use `ExecutorService` with **one virtual thread per task**, limiting DB/downstream connections with `Semaphore` instead of pooling virtual threads.
- Avoid thread-safety bugs, shared-state races, `ThreadLocal` footprint, swallowed interrupts, blocking native code, and resource exhaustion.
- Read diagnostics/JFR/thread dumps with awareness of the differences between Java 17, Java 21, and Java 24+.
- Run Java 17+ and Java 21+ programs with deterministic output without inferring OS-thread mappings not guaranteed by the API.

## 2. Brief History: How Java 17 Differs from Java 21 and 24

| JDK | Virtual-thread API and status | Key points to remember |
| --- | --- | --- |
| **8–17** | No standard virtual threads in `java.lang.Thread` | `new Thread(...)` creates a platform thread in typical HotSpot; use executors/pools to manage cost |
| **19** | Virtual threads **preview** — **JEP 425** | Requires corresponding preview configuration when compiling/running code using preview APIs |
| **20** | Second preview — **JEP 436** | API/diagnostics continued to be adjusted; not considered stable |
| **21 (LTS)** | Virtual threads **final** — **JEP 444** | Includes `Thread.ofVirtual()`, `Thread.startVirtualThread(...)`, and `Executors.newVirtualThreadPerTaskExecutor()`; no preview needed |
| **22–23** | Continued official API | Pinning due to `synchronized` + blocking is still something to investigate on these versions |
| **24** | **JEP 491**: monitor synchronization no longer causes the old kind of pinning in common cases | Virtual threads can unmount when blocking inside many `synchronized` regions; native/foreign constraints still need attention |
| **25+** | Continued runtime/diagnostics improvements | Check the exact vendor/build; do not apply JDK 21 pinning rules to every future JDK |

**Do not confuse** virtual threads (JEP 444) with structured concurrency. `StructuredTaskScope` went through preview/API-change phases across multiple releases; this lesson uses **the standard stable Thread and ExecutorService of JDK 21+**, without requiring preview to be enabled to run examples.

**Official sources:** [JEP 425](https://openjdk.org/jeps/425), [JEP 436](https://openjdk.org/jeps/436), [JEP 444](https://openjdk.org/jeps/444), [JEP 491](https://openjdk.org/jeps/491).

## 3. Platform Thread: A Java Thread Bound to an OS Thread

On HotSpot, a platform thread typically has the relationship:

~~~text
Java platform Thread object
             |
             | bound by runtime to
             v
Operating-system thread
             |
             | OS scheduler
             v
CPU core(s), time slicing, kernel scheduling
~~~

Characteristics:
- An OS thread has a native stack and management structures in the operating system.
- Creating/destroying very many platform threads has significant cost; concurrency usually has to be limited according to CPU/RAM/OS limits.
- If a platform thread is **blocking on I/O** or waiting for a lock, its OS thread usually cannot serve another Java request during that time.
- The JDK provides `ThreadPoolExecutor` and factories in `Executors` to **reuse platform threads** across many tasks.
- A platform thread can be **daemon** or **non-daemon**, and has a priority within a range that the runtime/OS may interpret; do not use priority as a mechanism to control fairness or correctness.

Thread pool model example:

~~~text
10,000 requests waiting for I/O
          |
          v
  Blocking request queue
          |
     200 worker platform threads
          |
          v
  At most about 200 tasks run/wait
  in workers at a time;
  the rest wait in the queue
~~~

The number 200 is illustrative only. A thread pool helps avoid the cost of creating an OS thread per request, but **does not by itself solve** the limit on concurrent requests when workers are occupied by waiting operations. If I/O latency is high, the queue can grow and cause tail latency.

### A JVM Always Runs Multiple Kinds of Threads

In addition to application platform/virtual threads, HotSpot may have GC threads, JIT compiler threads, signal/reference processing, scheduler/carrier threads, and other service threads. The number of OS threads in the process does not equal the number of times the application calls `new Thread`. Internal GC/VM threads also have CPU/RSS cost.

## 4. Virtual Thread: A Java Thread Not Permanently Bound to an OS Thread

JEP 444 describes a virtual thread as a `java.lang.Thread` **not tied to a specific OS thread**. HotSpot/JDK has its own scheduler, using platform threads called **carriers** to run virtual threads.

~~~text
Virtual Thread V1  --mount--> Carrier P1 --OS scheduler--> CPU
Virtual Thread V2  --mount--> Carrier P2 --OS scheduler--> CPU
Virtual Thread V3  --WAITING (unmounted, not holding a carrier)
Virtual Thread V4  --WAITING (unmounted, not holding a carrier)
Virtual Thread V5  --RUNNABLE/queued

A moment later:
V1 waits on socket -> unmounts from P1
V5 mounts onto P1 -> continues processing
V1 I/O ready -> enqueued, may mount onto P2
~~~

Conceptual diagram, **not a mandatory execution schedule**. A virtual thread may use different carriers over time. There is no standard API allowing a virtual thread to pin down a specific carrier to use as work identity.

### Mount and Unmount

- **Mount:** the virtual thread is placed onto a carrier platform thread to execute Java code.
- **Unmount:** the runtime temporarily saves the necessary state so the virtual thread pauses at a suitable waiting operation, freeing the carrier for other virtual threads.
- **Resume:** when the event/operation completes, the virtual thread is placed into the scheduler and may mount on another carrier.

Many I/O operations in the JDK are designed to **wait with blocking semantics in Java source**, while internally switching to a mechanism that allows the virtual thread to unmount. Programmers still write sequential code:

~~~java
String response = httpClient.send(request, responseHandler).body();
~~~

This is an **illustrative snippet** requiring appropriate `httpClient`, `request`, and `responseHandler`. Whether an API/blocking call actually yields the carrier depends on the JDK operation, native paths, implementation, and version.

### Virtual Threads Are Not OS Kernel Scheduling

The JDK scheduler maps virtual threads to carriers; **the operating system still schedules OS threads onto CPU cores**. Therefore, virtual threads do not provide more CPU cores, do not make the network/database process faster, and do not bypass file-descriptor or connection-pool limits.

### The Carrier Is Not the Thread Identity Observed by the Application

When code runs in a virtual thread:
- `Thread.currentThread()` returns the **running virtual thread**, not the carrier.
- `Thread.currentThread().isVirtual()` is **true** (JDK 21+).
- `ThreadLocal` and the stack trace belong to the **logical virtual thread**, not automatically shared with the carrier.
- A virtual thread can resume on another carrier while Java logic still sees the same Thread.

You should not cache an OS thread ID from native code and assume it stays fixed for the lifetime of a virtual thread.

## 5. CPU-bound vs. I/O-bound: Virtual Threads Do Not Change Resource Laws

A service has 1000 requests, each spending 2 ms computing on the CPU and 200 ms waiting for I/O. When there are many concurrent requests, the waiting portion can be handled efficiently by virtual threads without holding a dedicated OS thread per request. This makes the **thread-per-request style** easier to scale.

However, if each request runs 200 ms of **pure CPU**, the actual CPU work making progress is still bounded by the number of cores/CPU quota. One million virtual threads can simply be one million tasks competing for CPU, with added scheduling overhead.

Model:

~~~text
I/O-bound requests:
  A few ms CPU -> Long I/O WAIT -> A few ms CPU
                   |
                   +-- virtual thread unmounts, carrier handles another task

CPU-bound requests:
  CPU -> CPU -> CPU -> CPU
  No carrier is freed just because the thread is virtual
~~~

**The virtual-thread scheduler is not guaranteed to preempt each virtual thread after a public timeslice.** Do not rely on a “1ms quantum” or a fixed fairness order. Design applications to cooperate with the scheduler and appropriate blocking APIs, avoiding very long CPU tasks occupying carriers unnecessarily.

### Little's Law Is a Thinking Tool, Not a Throughput Guarantee

In a stable system, the average number of concurrent tasks is approximately **L = λ × W** (throughput × time in the system). If the target is 1000 requests/s and each request has an average latency of 0.2 s, around 200 requests may be present concurrently. This does not mean exactly 200 OS threads are needed, nor does it mean only 200 DB connections are needed: **the actual time and resources** of each request determine that.

## 6. Standalone Java 17+: Platform Threads and Join

Before JDK 21, should you use `new Thread` or `Thread.ofPlatform()`? The `Thread.ofPlatform()` method is a newer-generation API, **not to be used in lessons running with Java 17**. The Java 17-compatible example below uses only `new Thread`.

Create file **`PlatformThreads17Demo.java`**:

~~~java
public class PlatformThreads17Demo {
    static final class Counter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        Counter counter = new Counter();
        Thread[] workers = new Thread[4];

        for (int i = 0; i < workers.length; i++) {
            workers[i] = new Thread(() -> {
                for (int j = 0; j < 1_000; j++) {
                    counter.increment();
                }
            }, "worker-" + i);
            workers[i].start();
        }

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("threads=" + workers.length);
        System.out.println("total=" + counter.get());
    }
}
~~~

Compile/run on JDK 17+:

~~~bash
javac --release 17 PlatformThreads17Demo.java
java PlatformThreads17Demo
~~~

**Exact stdout** if execution completes normally:

~~~text
threads=4
total=4000
~~~

Explanation:
- `start()` requests a new thread to run the `Runnable`; **calling `run()` directly does not create a new thread**.
- All four threads increment Counter 1000 times; `synchronized` prevents a data race on `value` in this program.
- `join()` makes main wait for the worker to finish. Returning from `join` also establishes a happens-before relationship for the worker's actions relative to the thread after the join according to the Java Memory Model.
- Do not use `Thread.sleep(...)` to “wait long enough”: scheduler timing is nondeterministic.
- Thread execution order varies across runs, but the **final result** is still 4000 thanks to synchronization.

If you remove `synchronized` and let multiple threads execute `value++` concurrently, the increment expression consists of multiple read/modify/write operations, which can lose updates. Thread-safety issues **are unrelated** to whether the thread is platform or virtual.

## 7. Java 21+: Creating Platform and Virtual Threads with Builders

JDK 21 has all of:
- `Thread.ofPlatform()`: creates a platform thread via a builder.
- `Thread.ofVirtual()`: creates a virtual thread.
- `Thread.startVirtualThread(Runnable)`: creates and starts a virtual thread in one call.
- `Thread.currentThread().isVirtual()`: checks the current thread.

Create file **`ThreadKinds21Demo.java`**:

~~~java
public class ThreadKinds21Demo {
    static String describe(String label) {
        Thread t = Thread.currentThread();
        return label + ": " + t.getName()
                + ", virtual=" + t.isVirtual()
                + ", daemon=" + t.isDaemon();
    }

    public static void main(String[] args)
            throws InterruptedException {
        String[] results = new String[2];

        Thread platform = Thread.ofPlatform()
                .daemon(false)
                .name("platform-1")
                .start(() -> results[0] = describe("platform"));

        Thread virtual = Thread.ofVirtual()
                .name("virtual-1")
                .start(() -> results[1] = describe("virtual"));

        platform.join();
        virtual.join();

        System.out.println(results[0]);
        System.out.println(results[1]);
    }
}
~~~

Compile/run with JDK **21+**, not `javac --release 17`:

~~~bash
javac --release 21 ThreadKinds21Demo.java
java ThreadKinds21Demo
~~~

**Exact stdout:**

~~~text
platform: platform-1, virtual=false, daemon=false
virtual: virtual-1, virtual=true, daemon=true
~~~

Characteristics:
- The platform thread in the example is explicitly set to non-daemon.
- **Virtual threads are always daemon threads** per the JDK 21 API. They cannot be made non-daemon by calling `setDaemon(false)`.
- A virtual thread has a fixed priority `Thread.NORM_PRIORITY` per the JDK 21 API; priority cannot be used to schedule more important tasks ahead of others.
- Each thread has its **own name** in the example so the output does not depend on the default virtual-thread name.
- Collecting strings into two separate elements and printing only **after join** eliminates interleaved printing by the two threads, making stdout deterministic.
- Do not print the carrier name: it is an implementation detail and may change when the virtual thread unmounts/remounts.

**Note:** virtual threads are daemon threads, so an application that only has running virtual threads left after the main platform thread finishes **will not be kept alive** by virtual threads alone. Use `join()` or a lifetime-managed `ExecutorService` before main exits.

## 8. Is a Thread Work or a Resource?

A thread is **where code executes**; a task is a **unit of work** that can be submitted to an executor.

In the traditional model:

~~~text
Many tasks
   |
   v
ExecutorService thread pool
   |
   +--> reusable platform worker #1
   +--> reusable platform worker #2
   +--> reusable platform worker #3
   ...
~~~

Goal of pooling: reuse relatively expensive **OS/platform threads**. With virtual threads, the recommended model is **one virtual thread per task**, not pooling virtual threads:

~~~text
Task 1 --> Virtual Thread 1 ----+
Task 2 --> Virtual Thread 2 ----+--> JDK scheduler --> carrier pool
Task 3 --> Virtual Thread 3 ----+
Task N --> Virtual Thread N ----+
~~~

`Executors.newVirtualThreadPerTaskExecutor()` creates **a new virtual thread for each submitted task**. It is not like a fixed thread pool with N reusable virtual workers. When the task finishes, the virtual thread also finishes.

### Why Not Pool Virtual Threads?

Virtual threads are typically significantly cheaper than platform threads in creation cost and stack resources while waiting. Pooling virtual threads would place **an artificial cap** on the number of tasks, losing most of the benefit of the request-per-thread style without helping manage downstream resources separately.

Instead of limiting the **number of virtual threads**, limit the **concurrency used on scarce resources**:
- Database connection pool.
- Downstream API quotas.
- Number of file descriptors/sockets.
- Concurrent writes to a service.
- Heap/request buffers.
- CPU-bound parallelism.

Use `Semaphore` or resource-based queues/backpressure; do not create a fixed virtual-thread pool as a default measure.

## 9. Java 21+: ExecutorService with One Virtual Thread Per Task

Create file **`VirtualExecutor21Demo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualExecutor21Demo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {

            List<Future<String>> futures = new ArrayList<>();

            for (int i = 0; i < 5; i++) {
                final int id = i;
                futures.add(executor.submit(() -> {
                    Thread.sleep(10);
                    return "task=" + id
                            + ", virtual="
                            + Thread.currentThread().isVirtual();
                }));
            }

            for (Future<String> future : futures) {
                System.out.println(future.get());
            }
        }
    }
}
~~~

Compile/run on JDK 21+:

~~~bash
javac --release 21 VirtualExecutor21Demo.java
java VirtualExecutor21Demo
~~~

**Exact stdout:**

~~~text
task=0, virtual=true
task=1, virtual=true
task=2, virtual=true
task=3, virtual=true
task=4, virtual=true
~~~

Although tasks may complete **out of order 0→4**, the print loop iterates `Future`s in the list in submission order; therefore the output is stable. `Thread.sleep(10)` may cause the virtual thread to unmount in a supporting runtime, but **each task is not guaranteed to take exactly 10 ms**, and this demo is not a throughput benchmark.

Notes:
- `Future.get()` can throw `ExecutionException` if a task fails; this must be handled in a real application.
- `try-with-resources` calls `ExecutorService.close()` to wait in a managed way for tasks to finish per the contract.
- Using an executor does not automatically apply timeouts/cancellation to unbounded I/O. Use deadlines, `Future.cancel(true)`, interrupt-aware APIs, or an appropriate scoping mechanism.
- For a request server, an executor-per-request is usually **unnecessary**; manage the executor lifecycle at a level appropriate for the application.

## 10. Java 21+: Limiting Downstream Concurrency with Semaphore

Suppose an application wants to run many virtual threads waiting on I/O, but a downstream service only allows **two** concurrent operations. Do not limit the JVM scheduler down to two carriers; protect that resource itself.

Create file **`VirtualSemaphore21Demo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicInteger;

public class VirtualSemaphore21Demo {
    public static void main(String[] args) throws Exception {
        Semaphore permits = new Semaphore(2);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        try (ExecutorService executor =
                Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<Boolean>> futures = new ArrayList<>();

            for (int i = 0; i < 6; i++) {
                futures.add(executor.submit(() -> {
                    permits.acquire();
                    try {
                        int current = active.incrementAndGet();
                        peak.accumulateAndGet(current, Math::max);
                        Thread.sleep(20);
                        return Thread.currentThread().isVirtual();
                    } finally {
                        active.decrementAndGet();
                        permits.release();
                    }
                }));
            }

            int completed = 0;
            boolean allVirtual = true;
            for (Future<Boolean> future : futures) {
                allVirtual &= future.get();
                completed++;
            }

            System.out.println("completed=" + completed);
            System.out.println("allVirtual=" + allVirtual);
            System.out.println("bounded=" + (peak.get() <= 2));
            System.out.println("activeAfter=" + active.get());
        }
    }
}
~~~

Commands:

~~~bash
javac --release 21 VirtualSemaphore21Demo.java
java VirtualSemaphore21Demo
~~~

**Exact stdout:**

~~~text
completed=6
allVirtual=true
bounded=true
activeAfter=0
~~~

Explanation:
- There are 6 virtual tasks, but **at most two** tasks can enter the protected section at the same time.
- `Semaphore.acquire()` waits for a permit; when the virtual thread can park/unmount, the carrier is used for another task.
- `try/finally` ensures the permit is released even if processing inside the protected section fails after `acquire` succeeds.
- `peak` may be 1 or 2 depending on scheduling; the example only prints the **true invariant** `peak <= 2`, without guessing it will be exactly 2.
- The demo bounds concurrency, **it does not make a database automatically handle infinite requests**. In practice, there should be timeouts/backpressure instead of letting hundreds of thousands of virtual tasks wait for permits and hold buffers forever.

**General takeaway:** “virtual threads are cheap” is different from “every resource they access is infinite.”

## 11. Thread Lifecycle: start, wait, join, interrupt

Both platform and virtual threads are Java threads and follow the fundamental semantics of `Thread`.

A conceptual diagram:

~~~text
NEW
 |
 | start()
 v
RUNNABLE ---------------------+
 |                           |
 +--> WAITING / TIMED_WAITING|
 |       (join, sleep, park, |
 |        blocking operations)|
 |                           |
 +--> BLOCKED (monitor) -----+
 |
 | run() finishes or throws an uncaught exception
 v
TERMINATED
~~~

**Thread.State** is a Java-level state, not a mirror of every scheduler/kernel state. `RUNNABLE` can include a thread **running or waiting for CPU**; `WAITING` does not tell you which carrier is being held. Do not infer pinning solely from `getState()`.

### `start()` vs. `run()`

~~~java
Thread t = new Thread(() -> System.out.println("running"));
t.run();   // executes Runnable on the current thread
// t.start(); // another line: requests a separate thread
~~~

This is an illustrative snippet. If you call `run()` directly, the new Thread object does not transition to the started state. If you then call `start()` once, it will run the Runnable in a new thread **again**. If you call `start()` twice on the same Thread object, the second call throws `IllegalThreadStateException`.

### `join()` and happens-before

Writes completed in a worker before it terminates are visible to the thread calling `join()` according to happens-before rules after `join` succeeds. This allows reading results from `String[] results` in the ThreadKinds example without making each element `volatile`, provided main actually joins before reading and no other writer is running concurrently.

### `interrupt()` Is a Cooperative Signal

It is not “kill the thread immediately.” When a virtual or platform thread is interrupted:
- If waiting in certain interruptible APIs, the API may throw `InterruptedException`.
- Code should usually clean up, stop the task, or restore the interrupt flag if it cannot propagate the exception upward.
- A thread performing CPU computation does not stop automatically just because the interrupt flag is set if the code does not check it / cancellation is not propagated.

### Java 21+ Interrupt Demo

Create file **`VirtualInterrupt21Demo.java`**:

~~~java
import java.util.concurrent.atomic.AtomicReference;

public class VirtualInterrupt21Demo {
    public static void main(String[] args) throws Exception {
        AtomicReference<String> result =
                new AtomicReference<>("not-completed");

        Thread worker = Thread.ofVirtual().start(() -> {
            try {
                Thread.sleep(100_000);
                result.set("finished");
            } catch (InterruptedException ex) {
                result.set("interrupted");
                Thread.currentThread().interrupt();
            }
        });

        worker.interrupt();
        worker.join();

        System.out.println("result=" + result.get());
    }
}
~~~

Run:

~~~bash
javac --release 21 VirtualInterrupt21Demo.java
java VirtualInterrupt21Demo
~~~

**Exact stdout:**

~~~text
result=interrupted
~~~

Under normal program conditions, `interrupt()` is sent almost immediately after `start()`. Whether the worker has not yet entered `sleep` or has already entered it, when `sleep` checks the interrupt it will wake up/throw, so the `catch` branch sets `"interrupted"`. Do not use a timer to measure how “fast” interrupting is.

## 12. Blocking I/O and Pinning: Distinguishing JDK 21 from JDK 24+

### JDK 21–23: Blocking Under a Monitor Can Pin the Carrier

A simple scenario:

~~~java
synchronized (lock) {
    socketReadBlocking();
}
~~~

This is an illustrative snippet requiring appropriate `lock` and `socketReadBlocking()`. On JDK 21–23, a virtual thread executing a blocking operation inside a `synchronized` region may **be pinned** to its carrier platform thread. If the virtual thread waits on I/O for a long time while pinned, **the carrier is also held**, reducing the ability to run other virtual threads.

~~~text
JDK 21-23:
Virtual thread holds monitor
     |
Blocking I/O inside synchronized
     |
Virtual thread may be PINNED
     |
Carrier/OS thread is held while waiting
     |
Reduces scalability when many such tasks occur
~~~

Pinning does not make a Java program's result wrong; it primarily causes a **throughput/CPU carrier availability** issue. Not every short `synchronized` block is a problem. If it only protects a few in-memory instructions, mechanically replacing all locks can complicate the code without improving performance.

### JDK 24+: JEP 491 Improves `synchronized`

**JEP 491: Synchronize Virtual Threads without Pinning** was released in JDK 24. HotSpot can let virtual threads **unmount even while holding a monitor or waiting to enter a monitor**, in supported cases, so **it is no longer necessary to switch `synchronized` to `ReentrantLock` just to avoid the old kind of monitor pinning**.

However:
- Pinning or carrier capture can still occur with **native methods/foreign function calls** and certain VM/OS interaction paths.
- Not all I/O operations have the same ability to unmount; behavior depends on the API, OS, and JDK.
- Measure pinning on the actual build; do not draw conclusions from `synchronized` syntax without knowing the runtime version.

**A migration lesson:** the advice “you must replace `synchronized` with `ReentrantLock` on virtual threads” could be valid when addressing blocking hotspots on **JDK 21**, but is outdated if stated as a mandatory rule for **JDK 24+**.

### Native/Foreign Pinning

If a virtual thread calls native code/JNI/FFM and blocks along a path that cannot unmount, the carrier may be pinned. JNI critical operations also have their own rules regarding object references/critical sections. Do not swap a Java monitor and assume a native path has also stopped pinning.

### What Role Does `ReentrantLock` Play?

`java.util.concurrent.locks.ReentrantLock` is a lock primitive with `tryLock`, timed acquisition, fairness options, condition variables, and typically works with appropriate virtual-thread parking. It is beneficial when those exact semantics are needed; it is not automatically faster than `synchronized` for every workload.

## 13. Carrier Scheduler and Parallelism

JEP 444 describes the scheduler implementation based on a **work-stealing ForkJoinPool**, distinct from `ForkJoinPool.commonPool()`. The scheduler uses platform threads to run virtual threads.

Some relevant HotSpot/JDK system properties:

| Property | Role | Notes |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism` | Adjusts the scheduler's target parallelism | Default is typically tied to the number of available processors recognized by the JVM |
| `jdk.virtualThreadScheduler.maxPoolSize` | Caps the maximum number of platform threads the scheduler uses in certain compensation scenarios | Do not use it as the number of virtual threads that can be created |
| `jdk.tracePinnedThreads` | Helps trace pinning on JDK 21–23 | Behavior changed/no longer as useful as before after JEP 491; prefer JFR on newer JDKs |

Example customization (only after measuring):

~~~bash
java -Djdk.virtualThreadScheduler.parallelism=4 MyApp
~~~

This is a **command template**, requiring a valid `MyApp` class. It does not create four additional CPU cores and does not guarantee there are only four platform threads in the entire JVM. GC threads/JIT threads and compensation paths can add OS threads.

**Usually you should not tune scheduler properties prematurely.** If a service is bottlenecked on the DB pool, increasing carrier parallelism will not give the DB more connections; it can even cause CPU contention. If the workload is heavily CPU-bound, increasing the virtual-thread count does not replace managing how many tasks can usefully run concurrently.

### `Thread.yield()` Is Not a Fair Scheduling Mechanism

`Thread.yield()` is only a **hint**; it does not guarantee the thread will unmount/remount, yield a specific timeslice, or that another thread will run immediately. Do not rely on it to solve deadlock, starvation, or scheduling fairness.

## 14. Stack, Heap, and Resource Cost

A platform thread has a native stack attached to the OS thread; creating very many platform threads can exhaust **virtual address space, native memory, and OS scheduling resources**.

A virtual thread has **stack state dynamically managed by the JVM**; when unmounted, the state can reside in **stack chunk objects** on the heap. Thus, many waiting virtual threads do not each require holding an independent native stack equivalent to a platform thread. However, “virtual threads are cheap” **does not mean free**.

Each virtual thread still has:
- A Java Thread object and state structures.
- Live stack frames/stack chunks.
- Captured lambdas, task objects, Futures/executor metadata.
- References to buffers, request payloads, transactions, or connections.
- The virtual thread's own `ThreadLocal` entries/values when used.
- Queuing/timeouts/cancellation bookkeeping.

One million waiting virtual threads where each task holds a 10 KiB payload can retain **many GiB** just for payloads, not counting stack/task overhead. Memory budget and the number of file descriptors/connections must still be accounted for.

### `ThreadLocal`: The API Still Works, the Usage Pattern May Not Fit

JEP 444 ensures virtual threads in JDK 21 can use `ThreadLocal`. However:
- A `ThreadLocal` with a large value on **every** virtual thread multiplies the footprint by the number of threads.
- The pattern “each worker platform thread has an expensive cache/reusable connection” no longer makes sense if each task runs on a **short-lived virtual thread**.
- `ThreadLocal` belongs to the **logical virtual thread**, not to the carrier when the thread switches mounts.
- Clean up thread-local references when the task finishes or when the scope is no longer needed. Do not use `ThreadLocal` as an unbounded global request cache.

Distinguish **context propagation** from **resource pooling**. A request ID can be attached to the appropriate task/thread context, but a JDBC connection should still be obtained from a **separate bounded connection pool**.

## 15. Synchronization and the Java Memory Model Do Not Change

Virtual threads **do not automatically eliminate data races**. The inherent issues still exist:
- `x++` is not atomic.
- Regular `HashMap`/`ArrayList` are not thread-safe for concurrent mutations.
- `volatile` guarantees certain ordering/visibility relationships; it does not turn compound increments into atomic operations.
- `synchronized` and `Lock` protect critical sections according to their semantics.
- `AtomicInteger`/`LongAdder` have trade-offs suited to different update patterns.
- `ExecutorService` does not guarantee all tasks will finish before main if the application ignores executor lifecycle/cancellation.

Example:

~~~java
// Snippet: shared counter needing atomicity.
AtomicInteger count = new AtomicInteger();
Runnable job = count::incrementAndGet;
~~~

This is illustrative code, requiring `import java.util.concurrent.atomic.AtomicInteger;`. Whether the job runs on 100 platform threads or 100 virtual threads, `AtomicInteger` helps ensure atomic increments.

### Typical Happens-Before Rules

- Actions before calling `Thread.start()` **happen-before** actions in the started thread.
- Actions in a thread **happen-before** another thread detects that it has terminated via a successful `join()`.
- A `volatile` write happens-before a corresponding subsequent `volatile` read in synchronization order.
- A monitor unlock happens-before a subsequent lock on the same monitor.
- `ExecutorService/Future` also have memory consistency effects per the API contract.

These rules apply at the **Java Memory Model** level, regardless of whether the thread runs on carrier P1 or P2.

## 16. Deadlock, Starvation, and Overload

Virtual threads do not cure deadlock:
- Task A holds Lock1 and waits for Lock2.
- Task B holds Lock2 and waits for Lock1.
- No matter how large the number of virtual threads, it will not break a circular wait.

Virtual threads also do not by themselves:
- Increase the maximum number of database connections.
- Increase downstream API throughput.
- Avoid transactional locks or DB deadlocks.
- Avoid unbounded backpressure/queues.
- Make blocking native/unsupported I/O paths yield the OS carrier.
- Increase CPU cores for compute-intensive tasks.

**New risk:** because creating virtual threads is very easy, an application can accept **too many requests/tasks at once**, causing exhaustion of DB, socket limits, heap buffers, external rate limits, or semaphore wait queues. Always tie concurrency policy to **downstream capacity and latency SLOs**.

### A Wrong Example of Limiting Concurrency

~~~java
// Illustrative anti-pattern:
// Executors.newFixedThreadPool(20) inadvertently caps
// I/O-waiting requests to 20 worker platform threads.
//
// Do not create a "pool of 20 virtual threads" to simulate
// that same limit if the goal is to maximize I/O waiting concurrency.
~~~

In a production application, **request admission control** and bounded queues may be needed to limit the total number of requests being processed, even when using virtual threads. A semaphore only addresses a specific resource, not a protection policy for every kind of overload.

## 17. Which I/O Usually Yields the Carrier, Which I/O Needs Measurement?

| Operation / scenario | General expectation | Caveat |
| --- | --- | --- |
| `Thread.sleep(...)` in a virtual thread | Can unmount/yield the carrier | Exact wake-up time is not guaranteed |
| `BlockingQueue.take()` | Usually parks the virtual thread, yielding the carrier | Check the specific API/JDK path |
| `LockSupport.park()` | Has virtual-thread support | Does not mean the OS thread is parked |
| `Socket`/some `java.net` blocking I/O | Implemented in the JDK so a virtual thread can wait without holding a carrier | Other drivers/native paths need verification |
| `Future.get()` waiting on a task | Can use appropriate parking | If the task deadlocks, waiting can still be indefinite |
| `synchronized` + blocking, JDK 21–23 | Risks pinning the carrier | Move long blocking out of the monitor if it is a hotspot |
| `synchronized` + blocking, JDK 24+ | Monitor-related pinning is improved per JEP 491 | Other native/OS limitations remain |
| JNI/FFM native operation waiting | May hold/pin the carrier | Depends on the native call path; not solved merely by `ReentrantLock` |
| Long CPU loop | Uses a carrier while computing | Does not create additional CPU capacity |

**Do not apply the formula “every blocking operation unmounts”**. APIs/versions/hardware/OS implementations differ. If you change the JDK or JDBC driver, re-measure I/O/thread behavior on the target runtime.

## 18. Observing Virtual Threads with JFR and jcmd

### JFR Events

Java Flight Recorder has events related to virtual threads, depending on the version and recording configuration:
- `jdk.VirtualThreadStart` and `jdk.VirtualThreadEnd`: lifecycle events; usually **not enabled by default** because the number of virtual threads can be very large.
- `jdk.VirtualThreadPinned`: detects cases where a virtual thread pins a carrier for a long time according to the configured threshold.
- `jdk.VirtualThreadSubmitFailed`: issues when the runtime submits/starts/unparks a virtual thread to the scheduler.
- CPU, allocation, thread park, and GC events can aid interpretation if enabled/collected with sufficient data.

An application with very short-lived virtual threads can generate millions of lifecycle events; enabling all `Start/End` events in production can cause overhead. Use JFR profiles and select events according to the investigation question.

### Diagnostic Commands

On a supported JDK, run with the **actual PID** of the Java process:

~~~bash
jcmd PID Thread.dump_to_file -format=json virtual-threads.json
jcmd PID JFR.start name=VThreads settings=profile duration=60s filename=vthreads.jfr
jcmd PID JFR.check
~~~

The `PID` syntax above is a **placeholder** and must be replaced with the process ID. Command availability, options, and file shape may vary by JDK build; use `jcmd PID help` to confirm. Traditional thread dumps may not list every virtual thread the way you are used to with platform threads; the JSON format via the dedicated command helps observe virtual threads better on supported JDKs.

### JDK 21–23 Pinning Diagnostics

You can try:

~~~bash
java -Djdk.tracePinnedThreads=full MyApp
~~~

This is an example with a valid `MyApp` class, mainly useful on JDK 21–23 for monitor/native pinning. On JDK 24+, JEP 491 resolved the old monitor pinning case and this property is no longer as reliable a tool as before; prefer **JFR `jdk.VirtualThreadPinned`** and appropriate logging/profiling.

**Do not read JFR event count = number of affected requests.** One request can have multiple blocking operations; event sampling/thresholds cause some occurrences not to be recorded, and pinning does not automatically mean an SLO violation.

## 19. Thread Dumps and Metrics: Measured Thread Count May Not Be the Right Target

Platform-thread-oriented management APIs, OS tools, and thread counts usually **do not directly reflect the number of virtual threads**.

For example:
- OS utilities counting Linux threads/Windows threads of a process primarily see **OS/platform threads**.
- The virtual thread count can be much larger without the OS thread count increasing correspondingly.
- Traditional `ThreadMXBean` focuses on platform threads; do not infer the JVM only has that many logical Java threads.
- Virtual-thread dumps/observability APIs help inspect logical stacks, but exporting very large files can create overhead.

**The operational goal** should not be “as many virtual threads as possible,” but rather:
- completed requests/s;
- p95/p99 end-to-end latency;
- CPU quota, throttling, RSS, heap occupancy;
- DB connection usage and wait times;
- runnable/blocked/parked task profile;
- pinned events/carrier availability on the relevant JDK;
- error/timeout/cancellation rate.

If p99 increases, combine the event timeline with tracing, downstream pool metrics, and GC/JIT/OS signals. Do not assume every latency spike is pinning.

## 20. Comparing Platform Thread Pools and Virtual-Thread-Per-Task

| Attribute | Platform thread / pool | Virtual thread per task |
| --- | --- | --- |
| Relationship to OS | 1:1 in typical HotSpot | N:M via carriers by the JDK scheduler |
| Thread creation | Relatively expensive, usually pooled | Lighter, created fresh for each task |
| Stack | Native thread stack is a significant resource | Stack state dynamically managed by the JVM, with stack chunks on the heap when unmounted |
| Blocking I/O | Worker OS thread is usually held | Many JDK blocking APIs can unmount and yield the carrier |
| CPU-bound | Runs on OS cores | Still runs on OS cores/carriers, does not increase physical CPU |
| Effect on thread-per-request | Pool can cap concurrent requests | Allows many tasks to wait without a dedicated OS thread |
| Synchronization | `synchronized`, `Lock`, atomic APIs | **Same Java Memory Model/locking semantics** |
| ThreadLocal | Often reused per pool worker | Each virtual thread has its own context; there can be very many values |
| Primary tuning | Pool size, queue, rejection, native stacks | Downstream capacity, task admission, heap footprint, pinning/GC |
| Suitable scenarios | CPU-bound fixed workers, legacy libraries, or specific resource control | High-concurrency blocking I/O, request-per-task, easy to preserve call stacks/try-catch |
| Risks | Worker starvation, OS thread exhaustion | Resource overload, pinning/native paths, memory retained by tasks |

**Do not choose virtual threads just for “more threads.”** If an existing asynchronous non-blocking pipeline works well, switching to virtual threads may simplify code, but CPU/latency/throughput benefits need to be measured. Do not replace a production reactive framework based solely on toy benchmark results.

## 21. The Request-Per-Thread Model and Code Easier to Understand Than Callbacks

A controller might do:

~~~java
Response handle(Request request) throws Exception {
    User user = users.load(request.userId());
    Price price = pricingService.quote(user);
    auditService.record(request, price);
    return new Response(user, price);
}
~~~

This is **illustrative pseudo-code**, requiring appropriate classes/services, not a standalone program. If `users.load` and `pricingService.quote` are virtual-thread-friendly blocking operations, **one virtual thread per request** can wait naturally across sequential calls without holding a carrier for the entire I/O duration. You still get:
- traditional try/catch/finally;
- a Java call stack reflecting the chain of work;
- structured control flow with loops/conditions;
- debugger/stack traces tied to the logical thread.

But note:
- A sequential request with three I/O calls still has to wait for their execution times. Virtual threads **do not automatically parallelize** dependent operations.
- If you want to run multiple independent I/O calls concurrently, you still need orchestration APIs such as futures or other concurrent constructs.
- The JDBC driver/HTTP client/file I/O library must be checked for compatibility and appropriate behavior.
- Holding transactions/connections/locks for too long remains a domain/business issue.

## 22. Interrupt, Timeout, Cancellation, and Shutdown

In a server with thousands of virtual threads, managing lifetime matters more than the cost of calling `Thread.ofVirtual()`.

### Use Deadlines

A request should not block indefinitely when a downstream dies. Use:
- network client and database driver timeouts;
- `Future.get(timeout, unit)` when appropriate;
- cancellation/`interrupt()` per each API's contract;
- admission control/backpressure;
- executor shutdown and controlled waiting for tasks to finish.

### Prefer Not Swallowing Interrupts

Anti-pattern:

~~~java
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Do nothing: loses cancellation signal.
}
~~~

This is an illustrative snippet. If you cannot declare `throws InterruptedException` to the caller, you should usually clean up and **restore the interrupt status** via `Thread.currentThread().interrupt()`, or terminate the task appropriately for the context.

### Do Not Use `Thread.stop()`

`Thread.stop()` is unsafe / has had its usability removed in many modern API modes, and is not a reliable way to cancel a task. Use cooperative cancellation and resource cleanup in `finally`.

### Virtual Threads Are Daemon; Main Lifecycle Is Critical

If main only calls `Thread.startVirtualThread(...)` and returns, the program may terminate before the virtual thread finishes, because virtual threads are always daemon. You need `join()`, `Future.get()`, or an executor lifecycle to ensure the desired work completes.

## 23. Common Pitfalls When Moving from Thread Pools to Virtual Threads

| Mistake | Consequence and fix |
| --- | --- |
| Switching a fixed pool to a million virtual threads when the DB pool only has 20 connections | Moves the bottleneck to connection acquisition/queue; bound with a semaphore/pool and timeout |
| Pooling virtual threads to “save threads” | Reduces concurrency unrelated to real resources; use virtual-thread-per-task |
| Assuming virtual threads make compute-heavy tasks N times faster | CPU cores/CPU quota do not increase; measure CPU workload |
| Using `ThreadLocal` to hold large buffers for every request | Increases per-task heap footprint; review resource sharing/pooling |
| Treating `Thread.currentThread()` as the carrier | It is the logical virtual Thread, not the OS thread identity |
| Saving an OS thread ID and assuming it stays fixed after blocking | A virtual thread can resume on another carrier |
| Seeing `synchronized` on JDK 21–23 and ignoring pinning | Long blocking in a monitor can hold a carrier; profiling is needed |
| Always replacing `synchronized` with `ReentrantLock` on JDK 24+ | JEP 491 handles common monitor pinning; lock choice should be based on semantics |
| Believing all blocking I/O yields the carrier | Native/foreign and some OS/filesystem operations have exceptions |
| Not joining daemon virtual threads before main exits | Tasks may not have completed |
| Using `Thread.sleep` to wait for a result to be “definitely done” | Race condition; use `join`/`Future.get`/latch |
| Ignoring `InterruptedException` | Loses cancellation, tasks live too long |
| Sharing HashMap/ArrayList and incrementing `++` without synchronization | Data races/lost updates even though threads are virtual |
| Treating OS thread count as the virtual thread count | Metrics mainly reflect platform/OS threads |
| Treating a “10,000 sleep tasks are fast” benchmark as proof the DB can handle 10,000 queries | Downstream limits are completely different |
| Developing virtual-thread code and building with `--release 17` | The API is only official from JDK 21; build with JDK 21+ |

## 24. Production Rollout Checklist

1. **Identify the workload:** CPU-bound, I/O-bound, waiting ratio, and peak concurrency.
2. **Choose the JDK:** prefer a release with standard virtual threads (JDK 21+); if `synchronized`-related pinning matters, test **JDK 24+** on the target vendor/build.
3. **Keep sequential APIs clear:** use virtual thread per task for blocking logic; do not rewrite into callbacks just to save OS threads.
4. **Measure scarce resources:** DB connections, sockets, downstream QPS, heap buffers, connection wait times.
5. **Have admission control:** semaphores, bounded queues, rate limits, and per-request deadlines where needed.
6. **Verify cancellation:** interrupts are propagated/restored, resources cleaned up, executor shut down.
7. **Audit `ThreadLocal`:** avoid expensive values per virtual thread; context must not depend on carrier affinity.
8. **Audit blocking/native calls:** look for pinning/long carrier occupancy on the exact JDK.
9. **Observe with JFR/thread dumps:** enable events purposefully, avoid unbounded collection of every task start/end.
10. **Load test with real limits:** throughput, p95/p99, CPU quota, RSS, GC, connection pool wait, errors.
11. **Canary rollout:** monitor for regressions and have a rollback plan.
12. **Do not overlook security/context:** audit request identity, thread-scoped data, and lifetime to avoid leaks between tasks.

## 25. Self-Check Questions

**Question 1.** Is a Java virtual thread a new OS thread for every `Thread.ofVirtual().start(...)`?

**Answer:** No. A virtual thread is a Java Thread mounted onto a carrier platform thread by the JVM/JDK scheduler when running, and can unmount when waiting.

**Question 2.** What does `Thread.currentThread()` return when running on a virtual thread?

**Answer:** The current virtual thread, not the carrier.

**Question 3.** Can a platform thread resume on any other OS thread like a virtual thread?

**Answer:** In typical HotSpot, a platform thread is bound 1:1 to one OS thread, though that OS thread can run on different CPU cores via the OS scheduler.

**Question 4.** Will a virtual thread turn a 10-second CPU calculation loop into one second on the same number of cores?

**Answer:** No. It helps concurrency when blocking, and does not increase the number of CPU cores.

**Question 5.** Are virtual threads official in Java 17?

**Answer:** No. JDK 19/20 had preview; JDK 21 made them final under JEP 444.

**Question 6.** Are virtual threads daemon?

**Answer:** Yes, per the JDK 21 Thread API, so join/executor lifecycle is needed to avoid losing tasks when main exits.

**Question 7.** Does `Executors.newVirtualThreadPerTaskExecutor()` reuse 10 virtual workers?

**Answer:** No. It creates a new virtual thread for each submitted task.

**Question 8.** If the DB only has 10 connections, should the number of virtual threads be capped at exactly 10?

**Answer:** Not necessarily. Limit the number of operations **using the DB** via a pool/semaphore; other tasks can still do work/wait on other resources.

**Question 9.** Does a virtual thread's `ThreadLocal` change when switching carriers?

**Answer:** No. It belongs to the logical virtual thread; the carrier's `ThreadLocal` does not belong to the virtual thread.

**Question 10.** Is `value++` executed concurrently by multiple virtual threads safe?

**Answer:** No. Synchronization/atomics/locking is required as needed.

**Question 11.** Why is JDK 21 pinning in `synchronized` noteworthy?

**Answer:** Blocking inside a monitor can hold the carrier OS thread, reducing scalability.

**Question 12.** Does JDK 24 still require replacing every `synchronized` with `ReentrantLock`?

**Answer:** No. JEP 491 resolves common monitor-related pinning; native/foreign paths and synchronization correctness still need consideration.

**Question 13.** Is the OS thread count in Task Manager equal to the number of virtual threads?

**Answer:** No. Many virtual threads use a limited number of carriers, so the OS count differs from logical threads.

**Question 14.** Does `Thread.interrupt()` immediately “kill” a virtual thread?

**Answer:** No. It is a cooperative signal that can cause interruptible blocking APIs to throw or be checked by code.

**Question 15.** Can `Thread.sleep(10)` be treated as exactly 10 ms and used to prove scheduler fairness?

**Answer:** No. Wake-up time/OS scheduling is not guaranteed to be exact.

**Question 16.** A request thread holds a 1 MiB buffer, with 50,000 waiting requests: is it “free” because virtual threads are used?

**Answer:** No. Payloads alone could occupy around 50,000 MiB if they remain reachable, not counting stacks/metadata.

**Question 17.** Which tool helps investigate virtual thread pinning?

**Answer:** JFR event `jdk.VirtualThreadPinned` and JDK-appropriate diagnostics; on JDK 21–23 `-Djdk.tracePinnedThreads` can be used. Events must be correlated with actual latency/CPU.

**Question 18.** Why is a program that prints a result after `join()` deterministic even though thread scheduling is not fixed?

**Answer:** Main only reads after the workers finish; happens-before from thread termination/join guarantees visibility of the properly written result, provided there is no other concurrent conflicting writer.

## 26. Summary Diagram

~~~text
           JAVA CONCURRENCY PROGRAMMING
                      |
               java.lang.Thread
                      |
              +-------+-------+
              |               |
        PLATFORM THREAD    VIRTUAL THREAD
        HotSpot ~1:1 OS    JDK scheduler M:N
              |               |
          OS Thread       Mounts on CARRIER
              |               |
         OS scheduler     OS platform thread
              |               |
              +-------+-------+
                      |
                    CPU
                      |
           BLOCKING / WAITING?
              |               |
       Platform worker     Virtual thread can
       usually held        unmount and yield carrier
                              |
                      JDK 21-23: watch out for
                      pinning under synchronized
                              |
                      JDK 24+: JEP 491
                      improves monitor pinning
                              |
                    NATIVE / OS EXCEPTIONS
                              |
                  CAPACITY / CORRECTNESS
              DB pools + Semaphores + timeouts
              JMM + interrupts + joins
              JFR + diagnostics + load testing

Virtual threads increase concurrency for I/O-bound work
but do not create new CPU, RAM, or downstream capacity.
~~~

**Conclusion:** both platform and virtual threads are **real Java threads**, subject to the same thread-safety principles and the Java Memory Model. Platform threads are typically bound directly to OS threads; virtual threads allow many I/O-waiting Java tasks to share a smaller number of carriers while keeping sequential code. Virtual threads fit **thread-per-request for I/O-bound workloads**; performance and reliability still depend on CPU, heap, native I/O, connection limits, monitoring, and cancellation handling. In particular, **JDK 21 pinning under monitors** and **JDK 24+ JEP 491** must be interpreted according to the **exact version**, rather than merged into one immutable rule.

## Official References

- [JEP 425 — Virtual Threads (Preview), JDK 19](https://openjdk.org/jeps/425).
- [JEP 436 — Virtual Threads (Second Preview), JDK 20](https://openjdk.org/jeps/436).
- [JEP 444 — Virtual Threads, JDK 21](https://openjdk.org/jeps/444).
- [JEP 491 — Synchronize Virtual Threads without Pinning, JDK 24](https://openjdk.org/jeps/491).
- [Java SE 21 — Thread API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html).
- [Java SE 21 — Executors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html).
- [Java SE 21 — ExecutorService API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- [Java SE 21 — Semaphore API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).
- [Java SE 21 — Java Core Libraries: Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html).
- [JLS Java SE 21 — §17 Threads and Locks / Java Memory Model](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html).
- [JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Oracle JDK 24 — Significant Changes (JEP 491)](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html).
