# 10.1 Relationship Between Virtual Threads, Carrier Threads, and Platform Threads in Java 21

## Learning Objectives

Java 21 made **virtual threads** a permanent feature of the Java language/platform through **JEP 444**. Virtual threads allow the **one-thread-per-task/request** model to continue using easy-to-read sequential code, while the number of operating system threads no longer has to grow 1:1 with the number of tasks waiting on I/O.

However, during runtime diagnostics, three terms are very easy to misunderstand:

- **Platform thread:** a `java.lang.Thread` object bound by the JVM to an OS/kernel thread, typically in a 1:1 ratio throughout the platform thread's lifetime.
- **Virtual thread:** a `java.lang.Thread` object that executes application logic, **scheduled by the JVM** onto platform threads when runnable; it does not monopolize an OS thread for its entire lifetime.
- **Carrier thread:** **a platform thread acting as the execution vehicle for a virtual thread** at a given point in time. A carrier **is not a third kind of Thread** in Java SE 21.

The relationship between them explains why an application can have tens of thousands of virtual threads even when the operating system sees far fewer platform/kernel threads, why `Thread.currentThread()` inside a virtual thread still returns the **virtual Thread** rather than the carrier, and why certain `synchronized`/native code sections in **JDK 21** can **pin** a carrier, eroding scalability when tasks block for long durations.

After this lesson, you will be able to:

1. Accurately describe platform threads, virtual threads, carriers, and OS threads without conflating a **logical task** with a **physical execution resource**.
2. Understand the **mount → run → unmount/park → carrier reuse → remount** lifecycle, distinguishing JVM scheduling from operating-system scheduling.
3. Properly use `Thread.ofVirtual()`, `Thread.startVirtualThread()`, `Thread.ofPlatform()`, and `Executors.newVirtualThreadPerTaskExecutor()` in **Java 21**.
4. Explain scalability with blocking I/O, limits under CPU-bound/pinning workloads, and why **virtual threads do not make an individual task run faster**.
5. Write and run a Java 21 program demonstrating logical virtual thread identity, one hundred waiting tasks, and the limits of `ThreadMXBean`.
6. Diagnose scenarios involving rising platform/carrier counts, JFR pinning reports, thread dumps missing virtual threads, or applications still bottlenecked on a DB pool.
7. Distinguish what the Java API **guarantees** from **implementation-dependent** scheduler/HotSpot details, without inferring carrier identity from thread names.

> **Scope:** Java **21**, without using preview syntax from Java 19/20; the APIs here require JDK 21+ to compile. Important note: the **`synchronized` pinning** behavior presented below reflects **JDK 21**; newer JDKs may change the runtime mechanism. When applying this in production, always verify the **actual JDK/vendor/build running**.

## 1. The Big Picture: There Are Only Two Kinds of Java Thread

According to Java SE 21, `java.lang.Thread` represents an execution thread and has **two main kinds**: **platform threads** and **virtual threads**. Both are `Thread` objects, and both have an ID, a name, and `join()`/`interrupt()`/`ThreadLocal` capabilities per their respective APIs; they differ primarily in how they are scheduled and how they relate to OS resources.

| Perspective | Platform thread | Virtual thread |
| --- | --- | --- |
| Java object type | `java.lang.Thread` | `java.lang.Thread` |
| `isVirtual()` | `false` | `true` |
| Who decides when it runs? | The OS scheduler decides when to run the corresponding kernel/OS thread | The JVM virtual-thread scheduler decides when to **mount** it onto a carrier; the OS still schedules the carrier itself |
| Relationship to OS thread | Typically 1:1 throughout its lifetime | Can run on **different carriers over time**, without holding a dedicated OS thread while unmounted |
| Stack/resource | OS thread stack and kernel resources are generally larger | Stack/continuation managed by the JVM; can be stored as stack chunks on the heap when unmounted |
| Suitability | CPU-bound work, long-lived fixed tasks, native/low-level cases, traditional thread pools | Many independent tasks spending most of their time waiting on blocking I/O |
| Feasible count | Usually constrained by OS thread count, memory, and resource limits | Can be very large, but **not infinite**: heap, scheduler, application state, and resources outside the JVM still have limits |
| Daemon/priority | Can be daemon or non-daemon; priority per API | Always **daemon** and has **fixed priority** per the Java 21 contract |
| Java 21 `ThreadMXBean` | Monitors platform threads | **Does not monitor virtual threads** through this API |
| Typical creation | `new Thread(task)` or `Thread.ofPlatform()` | `Thread.ofVirtual()`, `Thread.startVirtualThread()`, per-task executor |

**A carrier thread does not belong in a third column**, because a carrier is simply a **platform thread** that the scheduler is currently using to execute a virtual thread. A platform thread may act as a carrier at one moment and later carry a different virtual thread. There is no public Java SE 21 API guaranteeing that a virtual thread stays bound to a fixed carrier.

### 1.1 "Virtual" Does Not Mean "Does Not Run on an OS Thread"

The CPU still executes instructions on real OS threads. A virtual thread is a **Java logical scheduling unit**, not an emulated CPU. When a virtual thread actually runs Java bytecode or native instructions, it must be **mounted** onto a carrier platform thread, which is then scheduled onto a CPU core by the OS scheduler.

Therefore:

- **100,000 virtual threads** does not mean **100,000 OS threads**.
- **1 virtual thread** does not mean **1 dedicated carrier**.
- **100,000 virtual threads** also does not mean **100,000 tasks computing concurrently on the CPU**.
- When a virtual thread is in a blocked state from which the JVM can **unmount** it, the carrier is reused for other work.
- When a virtual thread runs continuously CPU-bound, it consumes carrier execution time just like any other CPU-bound task; the scheduler does not create extra CPU capacity.
- A platform thread can execute traditional application code or act as a carrier; "carrier" is a **role in a scheduling relationship**, not a public `CarrierThread` subtype of `Thread`.

### 1.2 Illustrative Example: 10,000 Requests

Suppose an HTTP server receives 10,000 concurrent requests, each spending most of its time **waiting on database/network I/O**, while actual CPU processing is relatively brief.

**Traditional platform thread-per-request model:**

```text
Request #1    -> platform thread #1  -> OS thread #1  -> may block on DB read
Request #2    -> platform thread #2  -> OS thread #2  -> may block on DB read
...
Request #N    -> platform thread #N  -> OS thread #N  -> kernel resources grow with N
```

**Virtual thread-per-request model:**

```text
Request #1    -> virtual thread #1    \
Request #2    -> virtual thread #2     \
...                                   -> JVM scheduler -> carrier platform threads
Request #N    -> virtual thread #N     /                   -> OS threads -> CPUs
```

When many requests are waiting on I/O and are unmounted, many virtual threads can exist independently while the number of carriers remains much smaller. **N does not rigidly determine the carrier count**: CPU capacity, blocking/pinning, JDK scheduler policy, container resources, and workload mix determine actual runtime behavior.

This example is a **conceptual model**, not a guarantee that 10,000 requests will cause the JDK to use exactly 8 or 16 carriers. If the DB connection pool only has 50 connections, virtual threads do not magically create 10,000 DB connections; other tasks will still have to wait on the database/application's bounded resources.

## 2. Platform Threads: The Link to the OS Scheduler

### 2.1 From Java Thread to Kernel Thread

A platform thread is a `java.lang.Thread` object that the JDK implementation typically maps to an OS/kernel thread. In the typical HotSpot model:

```text
Java platform Thread object
    |
    | typically bound 1:1 throughout lifetime
    v
OS/kernel thread (has native TID, stack, scheduling state)
    |
    v
Operating-system scheduler -> CPU
```

Benefits: predictable integration with OS behavior, well-suited for CPU-bound tasks and native libraries. Limitations: a long-lived OS thread typically holds kernel bookkeeping and a native stack, consuming memory, address space, and scheduling overhead; the number of OS threads cannot scale arbitrarily.

When platform-thread code invokes true OS-level blocking I/O, **that OS thread may have to wait**, unavailable to run another Java task the way a carrier is returned when a virtual thread unmounts.

### 2.2 Creating a Platform Thread in Java 21

```java
// Illustrative snippet placed inside a method; requires a main method or to be called elsewhere.
Thread thread = Thread.ofPlatform()
        .name("legacy-worker")
        .start(() -> System.out.println(
                Thread.currentThread().isVirtual()));
thread.join();
```

In a standalone example with no other stdout writers, the line printed by the worker is `false`. `Thread.ofPlatform()` is a Java 21 builder; `new Thread(task)` also continues to create a platform thread.

A platform thread can be used inside a `ThreadPoolExecutor`/`Executors.newFixedThreadPool()` and **reused** across many tasks. That is the traditional pattern for conserving thread counts compared to spawning one OS thread per request. Do not equate a **platform thread** with a **platform thread pool**: a platform thread object can exist standalone or as a pool worker.

### 2.3 OS Thread ID Differs from Java Thread ID

`Thread.threadId()` returns the **Java thread ID**, not the process PID and not guaranteed to match the native thread ID/LWP/TID. In a HotSpot thread dump, `nid=0x...` typically represents the native thread ID in hexadecimal for a platform thread.

For a virtual thread, the Java thread ID continues to identify the virtual `Thread`; **it does not turn into the carrier's OS TID**. When a virtual thread unmounts and remounts, that ID must not be treated as proof that it is still running on the same OS thread.

## 3. Virtual Threads: Logical Threads with Stable Identity

### 3.1 A Virtual Thread Is Still a Real Thread in the Java API

A virtual thread is not a `CompletableFuture`, not an arbitrary coroutine library, and not a callback-only task. It is a **Java `Thread` object** with a lifecycle, stack trace, interruption, exception handling, and thread-local data propagation according to the API.

Ways to create one in Java 21:

```java
Thread t1 = Thread.startVirtualThread(() -> work());
Thread t2 = Thread.ofVirtual().name("request-42").start(() -> work());
Thread t3 = Thread.ofVirtual().unstarted(() -> work());
t3.start();
```

This is a **non-standalone illustrative snippet**: the `work()` method is hypothetical. All three threads are virtual; `t3` does not begin until `start()`. The `startVirtualThread`, `ofVirtual`, and `isVirtual` methods are Java 21 APIs and **do not compile on JDK 17**.

### 3.2 Thread.currentThread() Returns the Virtual Thread, Not the Carrier

When a virtual thread's code is running on a carrier, for example:

```java
// Illustrative snippet placed inside the Runnable of a virtual thread.
Thread current = Thread.currentThread();
System.out.println(current.isVirtual());
```

`Thread.currentThread()` returns the **logical virtual Thread**. Even though the CPU is executing the code via a carrier platform thread, Java code does not "see itself turn into the carrier." This preserves:

- The virtual thread's identity and `threadId()`.
- The virtual thread's `ThreadLocal` and `InheritableThreadLocal` per its lifecycle/context.
- Interruption state and the `join()`/`isAlive()` API per the logical thread.
- Stack/exception information for the logical task.
- The virtual thread's name, if one was assigned.

**There is no public Java SE 21 method `Thread.getCarrierThread()`** for applications to infer or lock onto carrier identity. Do not read `Thread.currentThread().getName()` and attribute that name to an OS worker; that name belongs to the **virtual thread**.

### 3.3 Special Properties of Virtual Threads

| Java 21 Property | Operational Meaning |
| --- | --- |
| `isVirtual() == true` | This is a virtual Thread |
| `isDaemon() == true` | Virtual threads are daemon threads; they do not keep the JVM alive on their own once all non-daemon threads finish |
| Fixed priority | Do not use `setPriority` to prioritize virtual task scheduling as a throughput-control mechanism |
| Empty default name | Virtual threads do not get a friendly name automatically; set a name via the builder if you need it for log analysis |
| `threadId()` | The logical virtual Thread's own ID, not the OS native TID |
| `join()` | Another thread can wait for a virtual thread to finish |
| `ThreadLocal` | Supported, but creating many virtual threads can amplify memory retention if each task allocates a large cache |
| Exceptions/stack | Each virtual thread has its own logical failure flow and stack, even if its carrier changes |

Because virtual threads are daemon threads, the following snippet **should not be used** when you need to guarantee that every task finishes:

```java
// Anti-pattern illustration only: main may finish before the task.
Thread.startVirtualThread(() -> doLongTask());
```

The `doLongTask` method is hypothetical. When the last main/platform non-daemon thread exits, the JVM may shut down even if the virtual task has not completed. You should `join()`, await `Future.get()`, or use `try-with-resources` with an appropriate executor to manage completion and failures.

### 3.4 Virtual Threads Do Not Inherently Need a Pool

With platform threads, creating/destroying OS threads is typically expensive, so thread pools are standard practice. Virtual threads are **much cheaper** and are designed for a **one-virtual-thread-per-task** model, not for reusing the same virtual thread across multiple requests.

`Executors.newVirtualThreadPerTaskExecutor()` creates a **new virtual thread for every task**. It is not a fixed-size pool of a few virtual threads cycling through multiple tasks.

Using a **per-task** virtual thread preserves:

- A dedicated call stack and context for each task/request.
- Readable sequential code with `try/catch/finally`.
- Per-task cancellation/interruption.
- No need to rewrite business logic into callback chains just to avoid blocking an OS thread.

However, other resources such as connections, rate-limited APIs, file descriptors, and queue capacities still require explicit bounds.

## 4. Carrier: The Role of a Platform Thread While a Virtual Thread Is Mounted

### 4.1 What Is Mounting?

When the JVM scheduler selects a runnable virtual thread, it **mounts** the virtual thread onto a **carrier platform thread** to execute code. The OS scheduler then decides when the carrier gets CPU time on a core.

```text
Virtual task A (logical Thread A)
   |
   | JVM: mount
   v
Carrier P1 = a platform Thread
   |
   v
OS thread TID=... -> scheduled onto a core by the OS scheduler
```

The core point: if code calls `Thread.currentThread()` while A is mounted, it still receives the **virtual A** object, not the carrier P1 object. The carrier is the physical execution substrate used by the scheduler, not a new application-level thread object.

### 4.2 Unmounting and Remounting

When A invokes a blocking operation supported by the JVM for **parking/unmounting** (for example, certain socket I/O or waiting points in the standard library), the VM can save A's stack/continuation, **unmount** A from carrier P1, and return carrier P1 to run a different virtual thread.

When the I/O completes or the task is unparked, the scheduler puts A back onto the runnable queue. A can be **remounted** onto P1 or onto a **different carrier P2**. **There is no guarantee that remounting will use the same OS thread.**

```text
Time           Logical virtual A                  Carrier platform threads
----------     ---------------------------------  --------------------------
T0             A runnable                         P1 idle, P2 idle
T1             A mounts and runs                  P1 runs A
T2             A calls I/O and needs to wait      JVM unmounts A from P1
T3             A is still waiting on I/O          P1 runs B; P2 runs C
T4             A's I/O completes                  A becomes runnable again
T5             A remounts and continues           P2 may run A

A remains **one** virtual Thread at all points T0..T5.
```

This is a **conceptual timeline**, not a promise that calling a specific API always produces these exact six steps or remounts on P2. The scheduler and OS are highly dynamic; code paths may not yield if I/O completes immediately, or may fail to unmount due to native calls or pinning.

### 4.3 Blocking Does Not Always Unmount

A common misconception is that "a virtual thread never holds its carrier when blocking." In **JDK 21**, that is **false**. Certain blocking operations are integrated into the JDK to unmount; pinning scenarios or native/foreign code can block **the carrier as well**.

Therefore, distinguish carefully among:

- **Waiting and unmounted virtual thread:** does not occupy a carrier while waiting.
- **Running virtual thread on a carrier:** occupies an execution slot to perform work.
- **Pinned and blocked virtual thread:** the carrier is not released; the cost can resemble a blocked OS thread.
- **Virtual thread waiting on a connection pool:** it may unmount, yet the request still has no connection, so throughput may not improve.
- **Carrier preempted by the OS scheduler:** the virtual thread may remain mounted while not executing at the instant the OS allocates the CPU to another thread.

A single virtual thread does not **parallelize** the code inside it: each virtual thread executes a single sequential flow; utilizing multiple CPU cores requires multiple runnable tasks and suitable algorithms.

## 5. Who Schedules What?

### 5.1 Two Levels of Scheduling

```text
Virtual Threads A, B, C, D, ...
               |
               | JVM virtual-thread scheduler:
               | selects a runnable task to mount
               v
      Carrier platform Threads P1, P2, ...
               |
               | OS scheduler:
               | assigns OS threads to CPU cores
               v
           CPU execution
```

- The **JVM** decides which virtual thread is mounted/remounted and when it parks/unparks.
- The **OS** decides which platform/kernel thread (including carriers) gets CPU time.
- There can be **many more virtual threads than carriers** because waiting on I/O does not hold a carrier.
- The number of tasks **executing on CPU simultaneously** is still bounded by cores/quotas, carrier availability, and work scheduling.
- A carrier is not durable ownership of a request; a request must never attach business state to carrier identity.

### 5.2 The JDK 21 Implementation's Scheduler

In **OpenJDK/HotSpot Java 21**, the default virtual-thread scheduler is built on a dedicated **`ForkJoinPool`** that uses carrier platform threads. This is a **JDK implementation detail**, not a promise that every JVM/vendor shares the same worker naming, queue policy, or carrier count.

The Java 21 `Thread` API documents two system properties of the reference implementation:

| Property | Meaning | Reference Default from JDK 21 API |
| --- | --- | --- |
| `jdk.virtualThreadScheduler.parallelism` | Number of platform threads available for scheduling virtual threads as target parallelism | **Number of available processors** |
| `jdk.virtualThreadScheduler.maxPoolSize` | Ceiling on the number of platform threads the scheduler may use per its pool management mechanism | **256** |

Example running the lab with **parallelism** set to 2:

```bash
java -Djdk.virtualThreadScheduler.parallelism=2 VirtualCarrierRelationLab
```

Do not conclude that "the scheduler has exactly two Java platform threads in every snapshot." The JVM also has GC/JIT/management threads, and the scheduler itself may apply compensation logic or adjust worker counts away from target parallelism in certain situations. The max pool ceiling is a scheduler limit, **not a cap on the number of virtual threads**.

In JDK 21 specifically, the scheduler **does not automatically expand parallelism to compensate for pinning** in a way that lets you assume "whenever it pins, a new carrier spawns." Instead of just raising parallelism, you need to detect code paths that pin frequently and for long durations.

**Do not tune these two properties merely because you see many waiting virtual threads.** Measure CPU quota, JFR pinning, response times, workload mix, and pool/connection limits, and benchmark on the same JDK build before changing scheduler tuning.

### 5.3 Carriers Can Differ Within the Same Logical Call Stack

Suppose `processRequest()` calls `loadFromDatabase()`. After the virtual thread unmounts during network I/O and remounts, the Java source still looks like a normal sequential call:

```java
// Illustrative snippet; the methods belong to the application and are not standalone.
Order order = repository.findById(id); // May wait on I/O.
validate(order);
sendResponse(order);
```

Between `findById` and `validate`, the logical virtual thread preserves its exception context, stack, and `ThreadLocal` per the API, even if the carrier changes. The application **does not need** to be aware of the carrier or manually reconstruct the call stack after a callback; that is a major value of virtual threads.

## 6. Standalone Java 21 Lab: Thread Identity and Waiting Task Count

This example uses only the **Java 21 standard library**, requiring no Internet, database, or framework. It has two parts:

1. A named virtual thread using a latch to stay **alive** while `main` inspects its identity and `ThreadMXBean`.
2. An executor creating **100 virtual threads** waiting on a latch; `main` waits until they **reach the wait point** before printing the counts. This is an experiment in **logical concurrency**, not an exact measurement of the VM's carrier count.

Create the file **`VirtualCarrierRelationLab.java`**:

```java
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicReference;

public final class VirtualCarrierRelationLab {
    public static void main(String[] args) throws Exception {
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicReference<Thread> seenInside = new AtomicReference<>();

        Thread virtual = Thread.ofVirtual()
                .name("demo-virtual")
                .start(() -> {
                    seenInside.set(Thread.currentThread());
                    entered.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                });

        entered.await();
        Thread captured = seenInside.get();

        System.out.println("main.isVirtual=" +
                Thread.currentThread().isVirtual());
        System.out.println("worker.isVirtual=" + captured.isVirtual());
        System.out.println("worker.sameObject=" + (captured == virtual));
        System.out.println("worker.name=" + captured.getName());
        System.out.println("worker.isDaemon=" + captured.isDaemon());
        System.out.println("mxbean.seesWorker=" +
                (ManagementFactory.getThreadMXBean()
                        .getThreadInfo(virtual.threadId()) != null));

        release.countDown();
        virtual.join();

        final int totalTasks = 100;
        CountDownLatch reachedWaitPoint = new CountDownLatch(totalTasks);
        CountDownLatch allowToFinish = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            for (int i = 0; i < totalTasks; i++) {
                results.add(executor.submit(() -> {
                    reachedWaitPoint.countDown();
                    allowToFinish.await();
                    return Thread.currentThread().isVirtual();
                }));
            }

            reachedWaitPoint.await();
            System.out.println("tasks.reachedWaitPoint=" + totalTasks);
            System.out.println("platformThreads.observed=" +
                    ManagementFactory.getThreadMXBean().getThreadCount());

            allowToFinish.countDown();
            boolean everyTaskVirtual = true;
            for (Future<Boolean> result : results) {
                everyTaskVirtual &= result.get();
            }
            System.out.println("tasks.allVirtual=" + everyTaskVirtual);
        }
    }
}
```

Compile and run on **JDK 21**:

```bash
javac VirtualCarrierRelationLab.java
java VirtualCarrierRelationLab
```

**The first six stdout lines are deterministic on a Java 21 JVM launched with the standard launcher:**

```text
main.isVirtual=false
worker.isVirtual=true
worker.sameObject=true
worker.name=demo-virtual
worker.isDaemon=true
mxbean.seesWorker=false
```

The remaining lines take the form:

```text
tasks.reachedWaitPoint=100
platformThreads.observed=<actual-platform-threads>
tasks.allVirtual=true
```

Here `platformThreads.observed` is an **actual value that depends on the JVM, machine, GC, scheduler, and measurement timing**; the placeholder in the illustrative block **is not literal stdout**. The two lines `tasks.reachedWaitPoint=100` and `tasks.allVirtual=true` are deterministic expectations when the program runs normally without environmental interruption or error.

### 6.1 What the Lab Proves

- `Thread.ofVirtual().name("demo-virtual").start(...)` creates a concrete virtual `Thread` object.
- Inside the task, `Thread.currentThread()` is the **exact `virtual` object** returned to `main`; hence `worker.sameObject=true`.
- The virtual thread **is still alive** when `main` calls `getThreadInfo` because it is waiting on `release`; `mxbean.seesWorker=false` is the **platform-only** limitation of `ThreadMXBean` in Java 21, not a sign that the thread has terminated.
- The application-assigned virtual thread name exists independently of the carrier's name.
- Virtual threads are daemon threads. `main` waits via `join()` and `Future.get()` so the program does not exit early.
- `newVirtualThreadPerTaskExecutor` creates a **new virtual thread for each task**, rather than pooling virtual `Thread` objects and reusing them across different tasks.
- Once 100 tasks have reached the wait point, we have 100 logical tasks coordinating on a latch; `getThreadCount()` reports **platform threads**, not the 100 virtual tasks combined.

### 6.2 What the Lab Does **Not** Prove

Do not infer from `platformThreads.observed` that "exactly X carriers ran the 100 tasks." `ThreadMXBean.getThreadCount()` includes **many other platform threads**, such as `main` and JIT/management/helper threads reported by the bean, and **does not isolate the carrier pool**. Measuring carriers/scheduler activity requires telemetry/JFR/OS observations suited to the VM implementation.

Additionally, `reachedWaitPoint.countDown()` happens **right before** `allowToFinish.await()`; when `main` prints 100, it proves all tasks **reached the point just prior to waiting**, not an atomic snapshot guaranteeing all 100 tasks were parked in the exact same nanosecond. That is the difference between **experimental synchronization** and **true runtime observation**.

### 6.3 Why Not Use Thread.sleep to Print the "Carrier ID"?

In Java SE 21, `Thread.currentThread()` called inside a virtual thread always returns the virtual `Thread`. There is no public API guaranteeing that `currentThread().threadId()` is the carrier ID. Printing the ID before and after `sleep()` **still prints the virtual thread's ID**, even if it remounts on a different carrier.

Similarly, seeing a `ForkJoinPool-...-worker-...` name in a single thread dump does not prove a request kept that carrier throughout its lifetime. Carriers can change, and a thread dump captures only a single point in time.

### 6.4 Why Does the Code Require JDK 21?

These APIs **do not exist in Java 17**:

- `Thread.ofVirtual()` and `Thread.startVirtualThread()`.
- `Thread.isVirtual()` and `Thread.threadId()` (the API signatures used in this lab).
- `Executors.newVirtualThreadPerTaskExecutor()`.

Virtual threads were a preview feature in JDK 19/20 and were **finalized** in Java 21. To practice JDK 21 properly, compile with JDK 21 `javac` and run with JDK 21 `java`; avoid situations where `javac` comes from JDK 21 while `java` on `PATH` comes from JDK 17, causing execution to fail.

You can verify with:

```bash
java -version
javac -version
```

These two commands show the **current terminal's runtime/compiler**, which does not automatically prove that a production Java service uses the same version. When diagnosing a real service, verify the version of the **target JVM process**.

## 7. Mount/Unmount and Blocking I/O: Why Virtual Threads Scale

### 7.1 What Happens on a Parkable Operation?

Simplified model:

```text
Virtual A running               JVM sees I/O that must wait
   |                                    |
   v                                    v
carrier P1 runs A ---> A is parked/unmounted; state is preserved
                          |
                          +-- P1 runs virtual B
                          |
                      I/O completion / unpark
                          |
                          v
                    A becomes runnable again
                          |
                          v
                    A remounts onto an available carrier
```

While a virtual thread is unmounted, it does not "lose" its Java call stack. The runtime preserves its logical state so code resumes right after the operation. The stack can be managed on the heap as **stack chunks/continuations** when unmounted, instead of each virtual thread holding a dedicated native OS stack for its entire lifetime.

This is why many blocking I/O tasks can coexist with far fewer carriers than virtual threads.

### 7.2 Are All Blocking APIs Fully Supported?

Never promise that "every I/O call will release the carrier." JDK 21 integrates many standard-library blocking operations with the virtual-thread scheduler, but:

- A blocking operation that completes immediately may not need to unmount.
- A native call, FFM foreign function, or poorly integrated library may **pin** the carrier or perform true OS-level blocking.
- A `synchronized` statement on the stack can prevent unmounting when blocking (JDK 21).
- JDBC drivers and network libraries may have their own synchronization mechanisms; verify in practice.
- CPU-bound operations still require a carrier to execute and do not automatically increase CPU capacity.

**`Thread.sleep(...)` and many blocking waits** can usually park/unmount on Java 21 if not pinned, but do not use them to infer carrier identity or quantify an exact context-switch count.

### 7.3 CPU-Bound Work Remains Subject to Physical Limits

Suppose a server has 8 CPU cores or a quota equivalent to 8 cores:

- Creating 100,000 virtual threads **waiting on network I/O** can be reasonable if heap, connection pools, and backends can sustain it.
- Creating 100,000 virtual threads running **heavy computation** does not create 100,000 CPU cores.
- If CPU-bound tasks continuously contend for CPU, the scheduler still has to time-slice across finite carriers and cores, which can increase latency.
- For CPU-heavy workloads, bounding parallelism/task counts and using appropriate work queues and profilers remains essential.

Oracle emphasizes: **virtual threads provide scale/throughput**, not a guarantee that an individual task runs faster (latency). If the backend still has bounded capacity, end-to-end throughput remains limited by the backend.

## 8. Pinning in JDK 21: When a Virtual Thread Cannot Release Its Carrier

### 8.1 What Is Pinning?

**Pinning** occurs when a virtual thread is executing or blocking in a state that prevents the JVM from **unmounting** it from its carrier during certain blocking operations. In that case, the carrier (and its underlying OS thread) may be held for the duration of the wait.

According to **Oracle JDK 21** documentation, the two primary scenarios are:

1. A virtual thread is executing code inside a **`synchronized` block/method** and encounters a blocking operation that needs to yield.
2. A virtual thread is executing a **native method** or **foreign function** (within the corresponding APIs) and cannot unmount.

**Pinning is not inherently a correctness bug.** A very short `synchronized` block that only modifies in-memory variables can be completely normal. A **scalability** problem arises when many virtual threads **frequently block for long periods while pinned**, reducing the carriers available to process runnable tasks.

### 8.2 JDK 21 Anti-Pattern: Long I/O Inside `synchronized`

```java
// Illustration inside a class; remoteFetch() is assumed to perform blocking I/O.
private final Object guard = new Object();

void load() throws Exception {
    synchronized (guard) {
        remoteFetch();
    }
}
```

This snippet is not standalone; `remoteFetch()` is hypothetical. If `load()` runs on a virtual thread and `remoteFetch()` blocks for a long time, in **JDK 21** holding the monitor can **pin the virtual thread** and hold the carrier. If hundreds of requests hit the same pattern, throughput can drop.

**You do not need to replace every `synchronized` with `ReentrantLock`.** Prioritize fixing hot paths that **frequently** perform blocking operations while holding a monitor. For short, CPU-only `synchronized` critical sections, changing locks may add complexity without improving the system.

### 8.3 Alternative Designs When Needed

If a lock is required to protect state, but I/O does not strictly need to happen inside the critical section:

```java
// Illustrative code; not standalone because remoteFetch/applyResult are defined by the application.
Data snapshot;
synchronized (guard) {
    snapshot = readSnapshot();
}

Result result = remoteFetch(snapshot);

synchronized (guard) {
    applyResult(result);
}
```

You must **design for consistency**: if state can change between the two critical sections, you need version checking, validation, or appropriate transaction semantics. Do not mechanically pull I/O outside a lock if doing so breaks atomicity or correctness.

If you must hold an **exclusive lock across a blocking operation**, the Java 21 docs suggest considering `ReentrantLock` on hot paths:

```java
// Illustration inside a class, not standalone.
private final java.util.concurrent.locks.ReentrantLock lock =
        new java.util.concurrent.locks.ReentrantLock();

void loadWithExplicitLock() throws Exception {
    lock.lock();
    try {
        remoteFetch();
    } finally {
        lock.unlock();
    }
}
```

`ReentrantLock` uses explicit unlocking and has its own semantics; it can help avoid pinning caused by intrinsic monitors in JDK 21, **without automatically eliminating lock contention or the need to protect state**. If many requests still have to wait on the same lock, throughput may remain serialized.

### 8.4 Does the Scheduler "Automatically Compensate Carriers" for Pinning?

Do not assume so. For **pinning** in OpenJDK/JDK 21, the scheduler **does not increase parallelism solely to compensate** for carriers held by pinned blocking operations. Many pinned virtual threads can leave the application short of carriers to run other tasks, even when many logical virtual threads are runnable.

Do not reach first for blindly raising `jdk.virtualThreadScheduler.parallelism` or `maxPoolSize`: you may merely mask the symptom, increase OS thread pressure, and keep long blocking inside critical sections. First identify the **source of pinning** and contention.

### 8.5 This Is a Java 21 Version-Specific Behavior

This section describes **JDK 21**. Newer Java versions may change the pinning mechanism around monitors. Do not treat "synchronized always pins virtual threads" as a permanent truth across all Java releases. When upgrading the JDK, re-verify documentation and JFR behavior on the **running version**, rather than blindly applying Java 21-specific workarounds.

## 9. Diagnosing Pinning and Carriers with JFR, jcmd, and Logging

### 9.1 JFR VirtualThreadPinned

**JDK Flight Recorder (JFR)** provides the events:

- `jdk.VirtualThreadPinned`: a virtual thread was pinned long enough to exceed the configured threshold while blocking. Oracle JDK 21 notes this event is typically enabled by default with a **20 ms threshold** in the relevant configuration.
- `jdk.VirtualThreadStart` / `jdk.VirtualThreadEnd`: lifecycle events, typically **disabled by default**, enabled only when genuinely needed.
- `jdk.VirtualThreadSubmitFailed`: the scheduler could not submit/start/unpark a virtual thread due to resource issues or another state requiring investigation; typically enabled under JDK 21 defaults.

A command to inspect an existing JFR recording:

```bash
# Reference: recording.jfr must actually exist on the machine invoking jfr.
jfr print --events jdk.VirtualThreadPinned,jdk.VirtualThreadSubmitFailed recording.jfr
```

This command **reads an existing JFR file**; it does not start a recording or fetch data from another JVM. Output depends on the recording window, threshold, event configuration, and whether pinning actually occurred in the JVM. Seeing no events may mean the event was not enabled, the duration stayed below threshold, or no pinning occurred during the window; it does not automatically prove **"zero pinning exists."**

### 9.2 jdk.tracePinnedThreads on JDK 21

To investigate hot paths on **JDK 21**, Oracle docs describe the system property:

```bash
java -Djdk.tracePinnedThreads=full YourApp
java -Djdk.tracePinnedThreads=short YourApp
```

`full` can print the relevant stack trace when a virtual thread blocks while pinned, highlighting/marking native frames or frames holding monitors; `short` prints less detail. This is **illustrative startup syntax**; replace `YourApp` with the real main class or launcher. Output can be voluminous and contain internal method names/paths; you must evaluate overhead and log sensitivity.

Do not assume this option is supported identically in **newer JDKs**, or that it can be attached dynamically to every JVM. Consult the documentation for your exact version and prefer JFR with appropriate overhead/retention when production policy allows.

### 9.3 Thread.dump_to_file and Traditional Thread Dumps

Oracle JDK 21 documentation describes a mechanism to generate a **virtual-thread-aware thread dump**:

```bash
# First, check the list of commands supported by the target JVM.
jcmd 12345 help Thread.dump_to_file

# If supported, the target JVM writes the JSON file at its path:
jcmd 12345 Thread.dump_to_file -format=json /approved/threads-12345.json
```

**12345 is a hypothetical PID**, and the path is also an example. Some JDK builds vary in command availability; `jcmd PID help` on the **target JVM** is the authoritative source. The file is written on the **JVM's filesystem**—pay special attention to container mount namespaces and permissions; it will not automatically appear on your laptop just because you ran the command from an external shell.

Traditional commands:

```bash
jcmd 12345 Thread.print -l
jstack -l 12345
```

generally focus on **platform threads** and lock info, and are not guaranteed to include every **unmounted virtual thread** in Java 21. Therefore, do not conclude "there are only 40 threads" from a traditional thread dump alone when the app has thousands of virtual tasks.

### 9.4 ThreadMXBean Does Not Monitor Virtual Threads in Java 21

In Java SE 21, `ManagementFactory.getThreadMXBean()` serves **platform threads**:

- `getThreadCount()` is the number of live platform threads per the bean, **not** all virtual threads.
- `getAllThreadIds()` does not list virtual thread IDs.
- `getThreadInfo(virtualThread.threadId())` returns **`null`**, even while the virtual thread is alive.
- `dumpAllThreads(...)` is not a complete dump of all virtual threads.
- `findMonitorDeadlockedThreads()` and `findDeadlockedThreads()` do not detect deadlock cycles **involving virtual threads** per the Java 21 contract.

Thus, do not use `ThreadMXBean` or the JConsole Threads tab to infer virtual task counts, virtual contention, or the absence of virtual-thread deadlocks. Use JFR, the appropriate `jcmd` dump, application-level metrics, and trace context.

### 9.5 Carrier CPU Is Not Automatically a Single Virtual Task's CPU

OS tools like `top -H`, `ps -L`, or process monitors observe **OS/kernel threads**, i.e., carriers and other platform threads. A single carrier can sequentially execute virtual threads A, B, C, ... within the same sampling window.

Therefore:

- "Carrier P1 used 80% CPU" does **not** mean virtual thread A used 80% CPU across that entire period.
- Virtual thread A may have switched carriers upon remounting.
- To find hot methods or logical work, use **JFR CPU samples** and appropriate correlation/trace IDs.
- Do not equate a carrier's HotSpot `nid=0x...` with a virtual task's `Thread.threadId()`.
- If native blocking/pinning occurs, JFR and stack traces can help pinpoint the exact code path; a lone OS CPU sample cannot confirm pinning.

## 10. Threads, Tasks, Carriers, Connections: Four Different Resources

In many web applications, the question "do virtual threads solve all thread pool problems?" must be answered by distinguishing four quantities:

1. **Logical tasks / virtual threads:** the number of concurrent units of work, typically one virtual thread per request.
2. **Carrier/platform threads:** the number of OS execution slots the JVM uses to run **runnable or pinned** virtual threads at given moments.
3. **CPU cores/quota:** the physical/scheduler compute capacity provided by the OS.
4. **External capacity:** DB pools, HTTP connection pools, rate limits, file descriptors, memory, downstream throughput, queue sizes, and network latency.

### 10.1 A Quantitative Throughput Example

Suppose:

- A server receives an average of 500 requests/second.
- Each request takes 0.2 seconds on average, mostly waiting on a backend.
- By steady-state **Little's law**, average concurrency is approximately:

```text
concurrency ~= throughput × responseTime
            ~= 500 requests/s × 0.2 s
            ~= 100 requests
```

If the downstream slows down and response time rises to 5 seconds at the same throughput, concurrency can rise to around **2,500 requests**. Virtual threads avoid needing 2,500 OS threads to hold those waiting requests, **but they do not allow the backend to serve 2,500 concurrent queries if the DB pool is capped at 50 connections**.

To enforce resource limits, use an appropriate **semaphore/rate limit/connection pool**. Do not use a fixed-size **virtual thread pool** as a proxy for resource limits; bound the **actual resource** and let each task keep its own logical thread by design.

### 10.2 Virtual Threads Do Not Reduce Slow I/O Latency

If a SQL query takes 300 ms on the DB, virtual threads do not make that query finish in 3 ms. The benefit is that while the request waits 300 ms, the carrier can serve another request. Total throughput can increase if platform thread count was previously the bottleneck, but if the DB is already overloaded, adding concurrency can **worsen latency**.

Design goals:

- Well-suited for **I/O-heavy concurrent workloads**.
- Does not promise speedup for individual CPU-heavy tasks.
- Put timeouts, cancellation, and limits in the right places.
- Monitor CPU, heap, carrier pinning, and downstream capacity.
- Benchmark under the same workload and percentile latencies, not merely by comparing thread counts.

### 10.3 ThreadLocal in Systems with Many Virtual Tasks

Virtual threads support `ThreadLocal`; values are bound to the **virtual thread**, not the carrier. Using it for lightweight correlation context can be appropriate, but legacy patterns like "one DB connection, large parser buffer, or expensive cache per thread" easily cause memory amplification when every request spawns a new virtual thread.

Example:

```java
// Illustrates a potential anti-pattern in an application with many virtual threads.
private static final ThreadLocal<byte[]> BIG_BUFFER =
        ThreadLocal.withInitial(() -> new byte[1024 * 1024]);
```

If 5,000 virtual threads each actually initialize a 1 MiB `BIG_BUFFER`, the theoretical memory for buffers alone is around **5,000 MiB** (excluding overhead). This is a hypothetical calculation, **not a memory figure that every application automatically consumes**. Remedies include shrinking buffers, bounding concurrency, safely sharing resources, or choosing appropriate context propagation; do not apply a one-size-fits-all fix before measuring.

And because virtual threads are not reused, a `ThreadLocal` cache "created once per thread-pool worker" becomes a **per-request cache** when migrating to the virtual per-task model. That is a lifecycle change that must be reviewed during migration.

## 11. Design Mistakes When Confusing Carriers with Virtual Threads

| Misconception | What Is True in Java 21 |
| --- | --- |
| "A virtual thread has no Thread object." | A virtual thread is itself a `java.lang.Thread` object. |
| "A carrier is a third Java Thread type." | A carrier is a **platform thread currently carrying a virtual thread**; Java SE has two Thread kinds. |
| "Virtual threads run without an OS thread." | When code actually executes, it is mounted onto an OS-backed carrier. |
| "A virtual thread stays bound to one carrier." | It can remount on a different carrier after unmounting. |
| "`Thread.currentThread()` returns the carrier in virtual code." | It returns the **virtual Thread**, not the carrier. |
| "A virtual thread's `threadId()` equals the native TID." | It is a Java logical thread ID, not an OS native TID. |
| "Any blocking call releases the carrier." | Pinning, native calls, or unsupported blocking can hold the carrier in JDK 21. |
| "`synchronized` is always wrong with virtual threads." | The risk is **frequent and long blocking while pinned**; short critical sections can be fine. |
| "Using `ReentrantLock` makes getting stuck impossible." | Lock contention and deadlocks can still happen; it only changes the pinning mechanism for specific cases. |
| "The scheduler spawns unlimited carriers on pinning." | JDK 21 does not compensate for pinning that way; limits and OS costs apply. |
| "Each virtual thread consumes a fixed native stack like a platform thread." | Stacks/continuations are flexibly managed by the JVM; they still consume heap/resources. |
| "100,000 virtual threads = 100,000 requests executing CPU in parallel." | Runnable CPU work is bounded by carriers, cores, and quotas. |
| "Virtual threads eliminate the need for a DB connection pool." | DB connections, QPS, file descriptors, and downstream limits still exist. |
| "Virtual threads should be reused in a fixed thread pool." | The recommended design is **virtual thread per task**; limit real resources rather than pooling virtual threads. |
| "Virtual threads don't have ThreadLocal." | They do, which makes large per-task caches dangerous at scale. |
| "Virtual threads are non-daemon so they keep the JVM alive." | Virtual threads are **daemon**; you must join/await completion. |
| "`ThreadMXBean.getThreadCount` includes all virtual threads." | Java 21 `ThreadMXBean` monitors platform threads only. |
| "Traditional thread dumps always include all unmounted virtual threads." | You need virtual-thread-aware dumps/JFR rather than inferring from platform-only output. |
| "A carrier's CPU identifies virtual request X's CPU." | A carrier can serve many virtual threads over time. |
| "Virtual threads cut the latency of a 300 ms RPC." | They help capacity/throughput in I/O-waiting workloads without speeding up an individual RPC. |

## 12. Practical Diagnostic Workflow

### Step 1 — Confirm the Exact JVM and JDK 21

Record the service, environment, process PID/start time, container/node, JDK vendor/version/build, and Java flags. Do not substitute the version from `java -version` in a separate terminal for the production process's version. If you suspect pinning behavior changed, verify the **exact JDK update release**.

### Step 2 — Define the Question

For example:

- "Why is the number of waiting requests rising while OS thread count stays flat?"
- "Why is CPU still high after migrating to virtual threads?"
- "Why did p99 latency degrade when the DB slowed down?"
- "Are carriers being pinned on a hot path?"
- "Why does `ThreadMXBean` show only 60 threads when the app spawns thousands of tasks?"
- "Is there a virtual-thread deadlock or starvation missed by a platform-only detector?"

Do not conclude carrier saturation solely from the number of virtual tasks. Separate CPU-bound work, I/O-bound waiting, resource starvation, and pinning.

### Step 3 — Collect Telemetry Within the Right Scope

| What You Need to Know | Appropriate Source | Limitations |
| --- | --- | --- |
| JVM/platform thread count | `ThreadMXBean`, OS metrics, `jcmd Thread.print` | Does not fully cover virtual tasks on Java 21 |
| Virtual task lifecycle/pinning | `jdk.VirtualThread*` JFR events per configuration | Recording/event thresholds can miss short events |
| Current virtual thread stacks | `jcmd PID help Thread.dump_to_file`, appropriate tools | Tool availability and output size depend on JDK/build |
| CPU hotspots | JFR CPU samples, profiler, and OS CPU | Requires sampling time and correlation |
| External bottleneck | DB/HTTP pool metrics, network/traces, rate limits | Outside `ThreadMXBean`'s scope |
| Pinning code path | `jdk.VirtualThreadPinned` or `jdk.tracePinnedThreads` on JDK 21 | Only when the feature/recording is enabled; subject to threshold/overhead |
| Resource memory | Heap/non-heap metrics, JFR allocations, container RSS | Do not assume "each virtual thread uses 0 bytes" |

### Step 4 — Correlate Timeline and Hypotheses

If JFR reports dense pinned events in a method making I/O calls inside `synchronized`, that is **strong evidence** to review the lock scope on JDK 21. If there are no pinned events while DB pool wait is high, resource capacity may be the real bottleneck. If CPU is pinned at 100% with many runnable virtual tasks, CPU profiling and scheduling analysis are needed.

Consider both **duration and frequency** of pinning, not just event counts. A single 25 ms event during warm-up does not mean production cannot scale, whereas continuous multi-second pinning on a hot endpoint can be severe.

### Step 5 — Choose Fixes Based on Root Cause

- Pinning from blocking inside `synchronized`: separate I/O from the monitor or use an appropriate lock mechanism while preserving correctness.
- DB pool exhaustion: tune concurrency, connection limits, SQL latency, timeouts, and load shedding.
- CPU saturation: optimize CPU-heavy code or scale cores/instances; do not raise virtual thread counts indefinitely.
- `ThreadLocal` memory pressure: remove inappropriate per-thread resource caches and use shared resource pools with clear lifecycles.
- Missing virtual thread visibility: add JFR/virtual-aware dumps, correlation IDs, and app-level metrics.
- Long request latency: inspect downstream calls, timeouts, and retries rather than concluding virtual threads "run slowly."

### Step 6 — Report Conclusions Alongside Limitations

Hypothetical report template:

```yaml
captureTimeUtc: "2026-10-29T09:30:00Z"
service: "checkout-service"
jvmVersion: "21.0.x"
virtualTaskModel: "one virtual thread per incoming request"
observation:
  requestsInFlight: 2500
  platformThreadCount: 56
  cpuUtilization: "medium"
  databasePoolWait: "high"
  pinnedJfrEvents: "not observed in this recording"
hypotheses:
  - "database connection capacity may limit throughput"
notProven:
  - "no pinning exists outside recording window"
  - "platformThreadCount measures total virtual threads"
nextSteps:
  - "correlate pool wait with p99 latency"
  - "review DB query and timeout behavior"
```

The numbers and names above are **examples only**, not data from an observed process. A sound conclusion always separates **what was measured** from **what remains unproven**.

## 13. Self-Check and Answers

**Question 1.** How many primary kinds of `Thread` objects exist in Java 21? Which kind is a carrier?

**Answer:** **two kinds**: platform and virtual. A carrier is **a platform thread currently being used to run a virtual thread**, not a third kind.

**Question 2.** Inside a virtual thread, what does `Thread.currentThread().isVirtual()` return while mounted on a carrier?

**Answer:** **`true`**. `Thread.currentThread()` returns the logical virtual Thread, not the carrier.

**Question 3.** A virtual thread waits on I/O, the JVM unmounts it, and the carrier runs another virtual thread. When I/O completes, must the first virtual thread remount on the exact same carrier?

**Answer:** **no**. The JVM can choose a different carrier, and Java code should not store carrier identity.

**Question 4.** If an OS has 16 cores, can there be 10,000 virtual threads?

**Answer:** yes, if memory and resources allow, especially when most are waiting on I/O. However, **there cannot be 10,000 tasks computing on the CPU simultaneously**; compute capacity remains bounded by cores/quotas.

**Question 5.** Do virtual threads make each SQL query 10x faster?

**Answer:** **no**. They increase the ability to serve many concurrent waiting tasks if OS thread count was previously the bottleneck; DB latency and capacity do not vanish on their own.

**Question 6.** Under what circumstances does Java 21 pinning involve `synchronized`?

**Answer:** when a virtual thread **blocks while still inside a `synchronized` block or method** (as well as certain native/foreign calls), preventing unmounting and holding the carrier. Short critical sections without long blocking typically do not need replacement.

**Question 7.** Must every `synchronized` block be replaced with `ReentrantLock` to use virtual threads?

**Answer:** no. Fix only hot paths that **frequently and lengthily** pin; preserve correctness, lock ordering, and resource policies.

**Question 8.** Java 21 `ThreadMXBean.getThreadCount()` reports 40 while the app has 5,000 waiting virtual requests. Is that abnormal?

**Answer:** not necessarily; `ThreadMXBean` measures **platform threads**, not virtual threads.

**Question 9.** A JFR recording has no `jdk.VirtualThreadPinned` events. Does that prove zero pinning occurs?

**Answer:** no. Pinning might happen outside the recording window, stay below the threshold, have the event disabled, or occur in unexercised code paths.

**Question 10.** Does a `ThreadLocal` move from virtual thread A to the carrier when A unmounts?

**Answer:** no. `ThreadLocal` is bound to **logical Thread A**, not the carrier; that is precisely why large per-thread caches can drive up memory when many virtual threads exist.

**Question 11.** Why is `newVirtualThreadPerTaskExecutor()` not a virtual-thread pool?

**Answer:** it creates a **new virtual thread for every task**, rather than retaining a set of virtual threads to reuse across tasks. The carrier platform threads are the execution resources managed by the scheduler.

**Question 12.** Since virtual threads are daemon threads, why use `Future.get()` or `join()`?

**Answer:** to wait for work to finish and handle errors; if all main/non-daemon threads exit first, the JVM can shut down with virtual tasks still incomplete.

**Question 13.** Carrier P1 uses 90% CPU. Can you conclude that virtual-thread request A used 90% CPU?

**Answer:** no. P1 may carry many virtual threads sequentially; CPU sampling and trace correlation are needed to attribute hotspots to logical work.

**Question 14.** Does raising `jdk.virtualThreadScheduler.parallelism` from 8 to 100 always improve throughput?

**Answer:** no. CPU quotas, pinning, memory, external pool/DB limits, and overhead can worsen results. Always benchmark and measure the root cause.

**Question 15.** Why does this lesson use Java 21 instead of compiling virtual-thread examples on Java 17?

**Answer:** virtual threads became a permanent feature in Java 21 with `Thread.ofVirtual`, `isVirtual`, and the per-task executor; Java 17 did not yet have those APIs.

## 14. Practice and Operations Checklist

- Understand that Java 21 has only **platform Threads** and **virtual Threads**; a carrier is a **role played by a platform Thread**.
- Grasp the two scheduling layers: **JVM mounts virtual → carrier platform → OS schedules carrier on CPU**.
- Understand **unmounting** on supported park/blocking operations; carriers can be reused, and remounting is not bound to the same carrier.
- In virtual-thread code, `Thread.currentThread()` is the **virtual Thread**, not the carrier.
- Do not use `threadId()` or the virtual Thread's name to infer the carrier's OS TID.
- Know that virtual threads are **daemon**, have fixed priority, have an empty default name, and support `ThreadLocal`.
- Write Java 21 code using `Thread.ofVirtual`, `Thread.startVirtualThread`, or `Executors.newVirtualThreadPerTaskExecutor`; await completion and handle failures.
- Do not pool/reuse virtual threads solely to limit DB/HTTP capacity; bound the **actual resources**.
- Distinguish I/O-bound scaling from CPU-bound work; virtual threads raise **potential throughput**, not single-task latency.
- On **JDK 21**, find hot paths blocking inside `synchronized`/native code that cause **pinning**; do not mechanically replace all monitors.
- Use JFR `jdk.VirtualThreadPinned`, JDK 21-appropriate pinning trace options, and virtual-thread-aware thread dumps.
- Know that `ThreadMXBean` and OS tools primarily see **platform threads** and should not be used to count all virtual tasks.
- Verify the exact JVM/PID/start time/JDK build, container/CPU quota, downstream resource limits, and incident window.
- Never conclude root cause from a single thread count, carrier name, or snapshot; correlate metrics/JFR/traces and tool capabilities.

**Conclusion:** a virtual thread is a **logical execution unit**, a platform thread is an **OS-backed Java unit**, and a carrier is a **platform thread temporarily used by the scheduler to run a virtual thread**. The mount/unmount relationship lets many concurrent I/O-waiting tasks use far fewer OS threads, but **it does not remove CPU or external resource limits**. When diagnosing Java 21, you must understand pinning, thread identity, the scheduler, and the blind spots of platform-only observability to avoid drawing wrong conclusions about thread counts, CPU usage, and scalability.

### Official References

- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): platform/virtual/carrier, mount/unmount, JDK 21 pinning, thread creation APIs, JFR events, `Thread.dump_to_file`.
- [OpenJDK — JEP 444: Virtual Threads](https://openjdk.org/jeps/444): goals, scheduling design, scalability, limitations, and Java 21 API finalization decisions.
- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): platform/virtual distinction, `currentThread()`, `isVirtual()`, daemon/priority, scheduler system properties.
- [Java SE 21 — Executors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html): `newVirtualThreadPerTaskExecutor()`.
- [Java SE 21 — ThreadMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): platform-threads-only management limitation.
- [Oracle JDK 21 — The jcmd Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): serviceability commands targeting a JVM.
- [Oracle JDK 21 — Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/flight-recorder-api-programmers-guide.html): JFR recordings and event configuration.
