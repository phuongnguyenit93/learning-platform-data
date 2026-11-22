# Application Threads and JVM Internal Threads

In the same Java process, you may see `main`, `http-worker-1`, `pool-1-thread-1`, `Reference Handler`, `GC Thread#0`, or `C2 CompilerThread0`. They are all involved in the program's operation, but **do not share the same owner, responsibility, or lifecycle**. Properly distinguishing these threads helps explain why the JVM stays alive after `main` finishes, why the garbage collector needs its own threads, and why you should not count threads and conclude that every thread was created by the application.

This lesson belongs to the **JVM Lifecycle** topic, focusing on: (1) threads running application work, (2) runtime/JVM support threads, (3) daemon threads and process termination conditions, (4) coordination between threads, and (5) practical observation and diagnostics.

**Implementation scope:** thread/daemon concepts are based on Java SE; examples of GC workers, compiler threads, VM thread, safepoints, and `jcmd` commands primarily describe **HotSpot/OpenJDK on JDK 17+**. Some details, thread names, and thread counts depend on the version, operating system, GC, and JVM options. Java 21+ virtual threads are explained separately to avoid confusion with internal background threads.

## 1. One JVM, Many Threads Doing Different Things

A Java process can simultaneously have:

- **Threads running application code:** `main`, threads created by `new Thread(...)`, `ExecutorService` pool threads, web server or library workers. They execute business tasks and can be **platform threads** or (since Java 21) **virtual threads**.
- **Java runtime / foundational library service threads:** for example `Reference Handler` and some cleaner/scheduler threads. They may be represented by `java.lang.Thread`, are usually daemon threads, but are not business tasks you wrote yourself.
- **VM internal native threads:** for example GC workers, compiler workers, and some HotSpot VM coordination threads. Some **do not correspond to a normal `java.lang.Thread` object**; therefore, the list from `Thread.getAllStackTraces()` is not an absolute catalog of all native threads in the process.
- **OS threads from native/JNI libraries or other components:** may exist outside the usual `java.lang.Thread` management model.

This is a **grouping by responsibility**, not four mandatory types in the Java API. “Application threads” and “internal threads” describe **who uses them and for what**; “daemon/non-daemon”, “platform/virtual”, and “Java-level/native VM” are **different classification axes**.

```text
A JVM/HotSpot Process
│
├── Application Work
│   ├── main (platform thread)
│   ├── application-created workers (platform threads)
│   ├── request/executor workers
│   └── application virtual threads (Java 21+)
│
├── Runtime Services Visible at the Java Level (JDK-dependent)
│   ├── Reference Handler
│   └── Cleaner / other background services
│
└── VM Internal Operations (HotSpot/configuration-dependent)
    ├── GC workers / concurrent GC threads
    ├── JIT compiler threads
    ├── VM / service / watcher / sampling threads
    └── other auxiliary threads
```

Some systems such as HTTP servers or logging libraries create background workers on their own. Even though their names sound “internal”, they are still **threads serving application/library components**, not by default JVM GC or compiler threads.

## 2. Application Threads: Where the Program Performs Work

### 2.1. `main` Is the Entry Point, Not the Only Thread

For a standard program run with `java Main`, the Java launcher invokes `public static void main(String[] args)` in a thread typically named `main`, which is normally **non-daemon**.

`main` can create additional threads, submit tasks to a thread pool, or call libraries that create their own threads. Those threads can continue running after the `main` method returns. Therefore, **“the `main` method finishes” does not mean “the JVM stops”**.

A platform thread on HotSpot is typically backed by an operating system thread, so creating too many concurrent threads increases stack/native resource and scheduling overhead. This is a common execution relationship, not a reason to deduce that **every** Java thread must have its own OS thread (virtual threads are a clear exception since Java 21).

### 2.2. Creating and Completing a Platform Thread

```java
Thread worker = new Thread(() -> {
    // Application work executed on a separate thread.
    doBusinessWork();
}, "application-worker");

worker.start(); // Requests concurrent execution to begin.
worker.join();  // Current thread waits for worker to finish.
```

This snippet is **illustrative**, because `doBusinessWork()` is an undefined placeholder name. A complete runnable program is provided in section 6.

- `new Thread(...)` creates a thread object in the `NEW` state; the task has not actually started yet.
- `start()` requests the JVM to schedule the execution of `run()` in a new thread; it **does not guarantee** that the new thread runs immediately before the caller's next statement.
- `join()` causes the calling thread to **wait** for the target thread to terminate; `join()` does not “cancel” the task early. `join()` can be interrupted with `InterruptedException`.
- Calling `worker.run()` directly only invokes the method normally on the **current thread**, without spawning a parallel execution path.
- You must not call `start()` a second time on the same `Thread` object; doing so throws `IllegalThreadStateException`.

Using `ExecutorService`, structured concurrency (when available), or high-level utilities helps manage task counts and lifecycles better than creating unbounded threads. `ExecutorService` is a mechanism for using threads, **not a type of internal GC thread**.

### 2.3. Thread States at the Java Level

`Thread.State` has six values:

| State | Meaning at the Java Level |
| --- | --- |
| `NEW` | Object created, `start()` not yet called |
| `RUNNABLE` | Executing or ready to execute according to the JVM model; does not guarantee it is currently occupying the CPU |
| `BLOCKED` | Waiting to acquire a monitor lock to enter `synchronized` |
| `WAITING` | Waiting indefinitely via an operation such as `Object.wait()` or `Thread.join()` |
| `TIMED_WAITING` | Waiting with a timeout such as `Thread.sleep(...)`, timed `wait/join` |
| `TERMINATED` | Finished `run()` |

These are **states observed at a single point in time**, which can change as soon as you inspect them. Do not equate Java's `RUNNABLE` with the OS scheduler's “running on CPU” state. And `BLOCKED` specifically means **waiting for a monitor lock**, not a general term for any slow I/O.

## 3. Daemon/Non-Daemon and JVM Termination Conditions

### 3.1. Daemon Is a Lifecycle Property, Not an “Internal JVM” Label

For **platform threads**:

- **Non-daemon:** typically a thread performing application work that the process needs to wait to complete. As long as any non-daemon thread is alive, the JVM normally continues to stay alive.
- **Daemon:** typically performs auxiliary work. A daemon thread **does not by itself prevent the JVM shutdown sequence from starting** once all non-daemon threads have terminated.
- As of Java 17, when creating a `Thread` via a standard constructor, its initial daemon status is **inherited from the thread that created it**, unless changed before `start()`. Call `setDaemon(true/false)` **before starting**; changing it while the thread is running throws `IllegalThreadStateException`.

**Important rule:** a thread created by the application and then configured with `setDaemon(true)` **is still an application thread**, merely carrying the daemon property. Conversely, JVM support threads may not have a public `Thread` object for the application to read `isDaemon()`; you should not apply `java.lang.Thread`'s daemon rules to describe every internal native thread.

### 3.2. Standard Lifecycle When Started from the Launcher

```text
JVM starts
   │
   ├─► Required VM services are created on demand
   │
   └─► main thread executes main()
             │
             ├─► creates app-worker-A (non-daemon)
             ├─► creates app-monitor (daemon)
             └─► main() returns
                      │
                      ├─ Is app-worker-A still alive?
                      │     ├─ Yes → process continues running
                      │     └─ No → shutdown can begin
                      └─ app-monitor still running does not keep the process alive on its own
```

For a normally launched Java app, if all **started non-daemon threads** have terminated, the shutdown sequence can begin and remaining daemon threads are not guaranteed to complete their work. The runtime also has **shutdown hooks** and explicit termination methods such as `System.exit(...)`; valid hooks can run and extend the shutdown process. Calling `Runtime.halt(...)` or having the process forcibly killed has different consequences. You should not interpret “once all non-daemon threads die, the OS immediately reclaims the process” while ignoring the shutdown phase.

**Design implication:** work that must complete, flush, or close resources should not be left to an endless daemon thread. Provide an explicit lifecycle: accept stop requests, shut down executors, `join`/`awaitTermination`, `close()`, and shutdown hooks when appropriate.

## 4. What Do JVM/HotSpot Internal Threads Do?

HotSpot needs to perform many tasks concurrently with application bytecode. The items below are **implementation examples**, not a guarantee that every JVM or every process has the same thread names or counts.

| Group | Primary Responsibility | Relationship to the Application |
| --- | --- | --- |
| **GC worker threads** | Perform heap collection steps such as marking, copying/relocation, or parallel phases, depending on the collector | Helps reclaim memory; some phases require coordinating to pause application threads |
| **Concurrent GC threads** | Perform GC phases that can proceed concurrently with application code | Reduces part of the work during pause intervals; does not mean there are no pauses |
| **JIT compiler threads** | Compile/optimize hot bytecode into machine code, process compilation tasks | Runs in the background and can use CPU while the application continues executing |
| **VM / service / watcher threads** | Coordinate VM work, monitor and handle events or internal management tasks | Specific structure and names depend on HotSpot/JDK |
| **Reference Handler** | Handles the `Reference` mechanism according to Java library/runtime design | May appear as a Java daemon thread in a thread dump |
| **Cleaner and other Java background services** | Perform registered cleanup or runtime/library tasks | Should not use background cleanup as a replacement for explicit resource closing |
| **JFR / profiling / attach-related threads** | Collect observability data, profiling, or serve attach tools when enabled/needed | May appear depending on configuration and tools in use |

**Not all groups “run Java” like `new Thread(() -> ...)`.** In HotSpot's source code, both `JavaThread` and `NonJavaThread` groups exist; for example, compiler/GC/VM machinery can use native runtime structures. Therefore, `Thread.getAllStackTraces()`, JMX, or a Java-level thread dump **does not necessarily list every internal native thread**.

### 4.1. GC and Application Threads

When the application allocates objects, the heap experiences allocation pressure; the collector may run GC cycles depending on the algorithm and configuration. GC must coordinate with **mutator threads** (threads that mutate the object graph), identify GC roots, process references, and possibly relocate objects. Applications typically observe the results as pause times, throughput, or CPU consumption.

- **Stop-the-world (STW):** during certain phases, the JVM needs to temporarily pause the normal progress of application threads to obtain a consistent state; GC threads can continue performing collection work during that interval.
- **Concurrent GC:** part of the work runs concurrently with the application, but may still require pause phases or handshakes/safepoints.
- **Safepoint:** a point/state where the VM can coordinate operations requiring specific constraints on threads; not a signal that “GC always stops every thread at all times”.
- **Live references:** stack frames and other roots contribute to determining object reachability. A thread still holding a reference in a `ThreadLocal` or a collection can keep the object reachable and affect retention.

Collectors such as G1, Parallel, or ZGC have different strategies and support threads. The number of GC threads typically depends on available CPUs, configuration flags, and the JDK version. **Do not treat sample names or numbers found online as fixed rules.**

### 4.2. JIT Compiler and Application Threads

The application may be executing bytecode via the interpreter while HotSpot identifies frequently executed methods/code segments. Compiler threads compile observed code into native machine code; subsequent executions can use the generated compiled version. Optimization, deoptimization, and compiler tier selection are JVM decisions.

The JIT can use background CPU even while business threads continue running normally. Do not confuse seeing `CompilerThread` in diagnostic tools with the application invoking `javac` itself: **`javac` is a pre-runtime compiler**, whereas the JIT compiler is a runtime component of the VM.

### 4.3. Reference Processing and Cleanup

Java has special reference types such as `WeakReference`, `SoftReference`, and `PhantomReference`. GC and the reference processing mechanism coordinate to handle these references, with supporting operations in the runtime/Java library. The thread named `Reference Handler` in HotSpot/OpenJDK is a familiar example.

You should not conclude “Reference Handler is a GC worker” just because it has the word “Reference”, or “Cleaner will close sockets on time”. Automatic cleanup has **non-deterministic timing**; files, sockets, and connections with lifecycles should be managed explicitly with `try-with-resources` or `close()`.

## 5. Two Classification Dimensions Often Confused

| Question | Correct Classification | What It Does **Not** Prove |
| --- | --- | --- |
| Does the thread perform business work or support the JVM? | Application/runtime/internal role | Does not imply daemon status |
| Does the thread keep the JVM alive when `main` is done? | Daemon or non-daemon (platform threads, same shutdown rules) | Does not imply who created it |
| Is the thread bound 1–1 to an OS thread? | Platform or virtual in Java 21+ | Does not imply “GC” or “application” |
| Does the thread have a `java.lang.Thread` object? | Java-level or HotSpot internal native | Does not imply every OS thread will appear in the Java API |
| Are tasks processed concurrently? | Scheduling/threading behavior | Does not guarantee true parallel execution across multiple cores |

In particular, **daemon != JVM internal** and **JVM internal != all daemon Java threads**. A web program can create its own daemon scheduling threads, while HotSpot has native VM threads that `Thread.isDaemon()` is not the direct API to describe.

## 6. Runnable Java 17 Example: Application Creates Two Types of Threads

Create the file **`ThreadRolesDemo.java`**:

```java
public class ThreadRolesDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(
                () -> System.out.println("worker: task completed"),
                "application-worker"
        );
        worker.setDaemon(false); // Must finish before the JVM can terminate on its own.

        Thread helper = new Thread(
                () -> System.out.println("helper: task completed"),
                "application-helper"
        );
        helper.setDaemon(true);  // Thread created by the application, but is a daemon.

        System.out.println("worker before start = " + worker.getState());
        System.out.println("worker daemon = " + worker.isDaemon());
        System.out.println("helper daemon = " + helper.isDaemon());

        worker.start();
        worker.join();           // Locks output order, waits for worker to finish.
        System.out.println("worker after join = " + worker.getState());

        helper.start();
        helper.join();           // Intentionally waits for helper so the demo always has full output.
        System.out.println("main: done");
    }
}
```

Run with JDK 17 or later:

```bash
javac ThreadRolesDemo.java
java ThreadRolesDemo
```

**Deterministic stdout of the example:**

```text
worker before start = NEW
worker daemon = false
helper daemon = true
worker: task completed
worker after join = TERMINATED
helper: task completed
main: done
```

**Why is this order stable?** The two separate threads are only `start()`ed sequentially, and after each `start()` there is a `join()` before the next step. `join` completes when the target thread has terminated; therefore, it does not depend on whether the OS grants CPU to the worker earlier or later. The printed lines in the example do not reflect actual GC thread names/counts, because the JVM performs internal operations independently of this business log.

This example demonstrates:

1. An application creates its own **non-daemon worker** and **daemon helper**; both are **application threads**.
2. `worker` goes from `NEW` to `TERMINATED` after `start()/join()`.
3. `helper` is a daemon but **still runs to completion** in the example because `main` actively calls `join()`; if `join()` is removed, there is no guarantee helper prints in time or completes before shutdown.
4. The line `main: done` does not assert that all internal VM threads have disappeared before the program returns. The runtime manages them itself during termination.

**Experimental variation:** remove `helper.join()` and run multiple times. Output from helper may or may not appear, depending on scheduling. Do not use the random presence/absence of a line to conclude that daemon threads always or never run.

## 7. Java 21+: Virtual Thread Does Not Mean JVM Background Thread

Starting in Java 21, applications can create **virtual threads**: `Thread.startVirtualThread(runnable)` or `Thread.ofVirtual()...`. They are logical threads scheduled by the Java runtime onto **carrier platform threads**. They are typically more resource-efficient than platform threads when many tasks wait on I/O, but do not replace all needs for controlling concurrent workloads.

- A virtual thread is an **application thread** if the application created it, even though it is supported by the scheduler/runtime.
- Virtual threads always have **daemon status**; they **do not keep the JVM alive** merely by existing.
- A carrier thread is a platform thread serving scheduling; **it is not the virtual thread itself**, and carrier threads should not be lumped together with dedicated GC/JIT workers.
- `Thread.currentThread()` when executed inside a virtual thread returns the **virtual thread**, not the carrier executing it.
- A virtual thread can run across different carriers over time. Therefore, do not assume each virtual thread has a corresponding OS thread.

Small example specifically for **Java 21+**, which will not compile on Java 17:

```java
public class VirtualThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread task = Thread.ofVirtual().name("request-virtual").start(() -> {
            Thread current = Thread.currentThread();
            System.out.println("name = " + current.getName());
            System.out.println("virtual = " + current.isVirtual());
            System.out.println("daemon = " + current.isDaemon());
        });
        task.join();
        System.out.println("main: done");
    }
}
```

Run:

```bash
javac VirtualThreadDemo.java
java VirtualThreadDemo
```

Stdout:

```text
name = request-virtual
virtual = true
daemon = true
main: done
```

The `task.join()` line causes the program to wait for the task to complete. If an application creates virtual threads to handle long-running work without a lifecycle management mechanism, once non-daemon platform threads are gone, the JVM can still begin shutdown. **Do not use daemon status to define the origin or importance of a task.**

## 8. The Role of Threads in the JVM Lifecycle: From Startup to Shutdown

| Milestone | Application Threads | Internal/Runtime Threads |
| --- | --- | --- |
| **Startup** | Launcher brings the application to `main` according to the launch model | VM initializes the runtime, thread management structures, and required services |
| **Loading/warming up the application** | `main` calls code, creates workers, touches libraries | Class loading, compiler threads, and background services may be activated on demand |
| **Handling load** | Request/task threads process data; generate allocations | GC may run, JIT optimizes hot code, services coordinate continuously |
| **Waiting for I/O/locks** | May be in `WAITING`, `TIMED_WAITING`, `BLOCKED`, or still `RUNNABLE` depending on the operation | Runtime/OS coordinate wakeups, I/O, scheduling, and certain GC phases |
| **Application requests stop** | Stop accepting tasks, cancel/close pools, wait for critical work, close resources | VM processes shutdown hooks/termination events according to the runtime mechanism |
| **Process termination** | No tasks remain running in the process | VM stops operating, the operating system reclaims the process's resources |

**The application author's responsibility** is to manage the threads/tasks they create: set reasonable concurrency limits, respond to interruption, close executors/resources, control `ThreadLocal` leaks, and ensure essential work completes on shutdown. **The JVM's responsibility** is runtime scheduling/execution, memory/GC/JIT management, and maintaining internal VM services. You should not “stop a GC thread” or operate directly on internal threads based on names found in a dump.

## 9. Observation and Diagnostics with Tools

In a Java application, `Thread.currentThread()`, `Thread.getState()`, `Thread.isDaemon()`, and `ThreadMXBean` help observe **Java threads** at the API level. When operating HotSpot:

```bash
# Run the example with GC and safepoint logs (GC may not occur in a small program)
java -Xlog:gc*,safepoint ThreadRolesDemo

# List Java PIDs of running processes
jcmd -l

# Capture a Java thread dump of the process (replace <pid> with the actual PID)
jcmd <pid> Thread.print -l

# View heap info supported by HotSpot
jcmd <pid> GC.heap_info
```

`jcmd` is typically included in the JDK and requires appropriate permissions/attach capability. A short-lived JVM like `ThreadRolesDemo` may exit before you can run `jcmd`; use a longer-lived application for practical inspection.

**Safe reading practices:**

- Identify `main` and framework/application threads by **stack trace and where the thread was created**, not solely by names like `pool-N-thread-M`.
- Recognize runtime support threads such as `Reference Handler` or `Common-Cleaner` if they appear; do not assume every JDK displays the same names.
- GC and compiler threads may appear in **OS-level/native diagnostics** or dedicated modes/logs, but may **not appear completely in `Thread.print`**. Therefore, a Java thread dump **does not prove** “the JVM has no GC workers”.
- Compare multiple snapshots over time to distinguish threads doing normal work from threads stuck for a long time. `RUNNABLE` alone is not proof of high CPU; `WAITING` alone is not an error.
- When analyzing native thread stacks/metaspace/code cache overhead, HotSpot provides **Native Memory Tracking (NMT)** when enabled at startup, such as `-XX:NativeMemoryTracking=summary`, followed by `jcmd <pid> VM.native_memory summary`. NMT incurs overhead and only summarizes the memory types it tracks.

```bash
# When native memory tracking is needed; enable at application startup
java -XX:NativeMemoryTracking=summary ThreadRolesDemo
# Then while the application is still alive:
jcmd <pid> VM.native_memory summary
```

These commands are examples for compatible HotSpot/JDK versions; there is no fixed stdout because it depends on PID, configuration, process age, and runtime activity.

### Common Symptoms and What to Check

| Symptom | What to Check First |
| --- | --- |
| `main` printed “done” but the process has not exited | Live non-daemon workers/executors/servers, shutdown hooks, or library threads |
| Application exits while background tasks remain | Are only daemon/virtual threads left? Is there `join`/shutdown coordination for work that must finish? |
| Thread count grows endlessly | Unbounded thread pool configuration, stuck tasks, thread leaks, server frameworks creating workers |
| `OutOfMemoryError: unable to create native thread` | OS/process limits, memory reserved for thread stacks, platform/native thread count; do not immediately blame the Java heap |
| Significant pauses or CPU used by the collector | Collect GC logs/JFR, allocation pressure, collector, and safepoints |
| High CPU in JIT threads or during warm-up | Analyze compilation activity and workload; do not infer buggy business code from the thread name alone |
| Thread dump has many `WAITING` or `BLOCKED` threads | Read stacks, lock owners, wait/notification, and take multiple snapshots; distinguish idle pools from deadlocks |
| Memory leaks tied to threads | `ThreadLocal` holding references, queues, listeners, and executor/container lifetimes |

**Practical warning:** do not call `Thread.stop()` to “kill” a stuck thread, because this method is deprecated and unsafe. Prefer cooperative cancellation mechanisms: `interrupt()`, `Future.cancel(true)` when appropriate, timeouts, closing resources, and handling interruption properly.

## 10. Common Misconceptions

1. **“Closing `main` terminates the JVM.”** False when non-daemon threads are still running or the system is in the shutdown process.
2. **“Daemon means JVM internal thread.”** False; applications can also create daemon threads, like `application-helper` in the example.
3. **“Every thread name in a dump was created by the JVM itself.”** False; servers, logging frameworks, and thread pools create many custom names.
4. **“A Java thread dump lists all OS/native threads.”** Not guaranteed. HotSpot has internal threads not exposed as normal Java `Thread`s.
5. **“A `RUNNABLE` thread is definitely consuming CPU.”** False; it may be ready to run or engaged in a context-dependent native operation.
6. **“GC threads always run concurrently and never stop the application.”** False; GC strategies have different pause phases and concurrent phases.
7. **“JIT compiler threads compile Java source code like `javac`.”** False; JIT optimizes bytecode to machine code at runtime.
8. **“Creating a Java 21 virtual thread is equivalent to creating an OS thread.”** False; virtual threads typically run sequentially across carrier platform threads.
9. **“Using `setDaemon(true)` completely solves application shutdown.”** False; it can cause important tasks to terminate mid-way and does not replace explicit resource closing.
10. **“More threads definitely means faster execution.”** False; there is still contention, scheduling overhead, CPU/memory limits, and non-parallelizable workloads.

## 11. Self-Check

1. If `main` returns while an `ExecutorService` still maintains non-daemon workers, must the JVM exit immediately? How should the executor be closed?
2. In `ThreadRolesDemo`, why is `helper` a daemon yet always prints its line? What changes when `helper.join()` is removed?
3. When a Java thread dump does not show “GC Thread” names, can you conclude the JVM is not running GC? What other kind of observation is needed?
4. Why are `Reference Handler` and `C2 CompilerThread` two different examples of runtime services? Which one can be a `java.lang.Thread`?
5. If a Java 21 application creates thousands of virtual threads, why is the number of OS threads usually much smaller? Why are those virtual threads still application threads?
6. How do a `BLOCKED` thread and a `WAITING` thread differ? Why is thread count alone not enough to diagnose a deadlock?

**Key takeaway:** The JVM initializes and operates **threads that serve the runtime itself** while **application threads** execute user work. Daemon status only affects the rule for keeping the process alive; it **does not** determine thread ownership. In operations, observe properly at the Java-level, native VM, and OS levels, and manage application thread lifecycles explicitly.

### Original References

- [Java SE 17 — `java.lang.Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): thread creation, `start()`, `join()`, and daemon behavior.
- [Java SE 17 — `Thread.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.State.html): six states observed from Java.
- [JVM Specification 17 — Runtime Data Areas, Threads (`2.5)](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.5): specification foundation for thread execution context and data.
- [JVM Specification 21 — JVM Termination (`5.7)](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.7): termination and shutdown.
- [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): virtual threads, carriers, scheduling.
- [Oracle JDK 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual thread execution model.
