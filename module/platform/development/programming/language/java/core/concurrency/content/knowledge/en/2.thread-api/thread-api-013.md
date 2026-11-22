# Thread.Builder: creating platform threads, virtual threads, and configured ThreadFactory instances

## 1. Learning objectives and version requirements

Thread.Builder is the standard API in **Java 21+** for configuring and creating threads in a unified, readable way: choosing a **platform thread** or a **virtual thread**, setting names, deciding whether to start immediately, and creating a ThreadFactory to reuse the configuration in executors.

After this lesson, you will be able to:

- Distinguish between Thread.ofPlatform() and Thread.ofVirtual(), along with their costs and use cases.
- Use start(Runnable), unstarted(Runnable), and factory() according to the thread lifecycle; know exactly when a thread is started.
- Configure names, InheritableThreadLocal inheritance, uncaught exception handlers, and platform-thread-specific properties.
- Provide a ThreadFactory to an ExecutorService without confusing a thread factory with scheduling policies, concurrency limits, or queues.
- Write runnable Java 21+ applications, wait for threads to finish properly, and identify operational limits.

**Scope:** Java SE/JVM concurrency, without discussing frameworks. **Prerequisites:** use JDK 21 or newer for all examples; JDK 17 does not support these APIs. Virtual threads went through preview stages in earlier JDK releases, but the final release version is Java 21.

## 2. Mental model: builder → thread or factory

Thread.Builder is an **interface** with two specialized branches:

~~~text
Thread.ofPlatform() → Thread.Builder.OfPlatform
                     ├─ start(task)     → started platform thread
                     ├─ unstarted(task) → platform thread in NEW state
                     └─ factory()      → ThreadFactory creating platform threads

Thread.ofVirtual()  → Thread.Builder.OfVirtual
                     ├─ start(task)     → started virtual thread
                     ├─ unstarted(task) → virtual thread in NEW state
                     └─ factory()      → ThreadFactory creating virtual threads
~~~

Thread.Builder does not run a Runnable itself and does not represent a live thread. It is a **configuration builder for creating separate Thread instances**. Each Thread has an independent task and lifecycle. The builder can configure the name, handler, and several properties before creating the Thread.

Three ways to finish building:

| Call | Result | Has the thread started running? | Use when |
|---|---|---|---|
| builder.start(task) | New Thread | start() has been called to request scheduling | You need to create and run immediately. |
| builder.unstarted(task) | New Thread | Not yet; in NEW state | You want to keep a reference, arrange startup order, and call start() yourself. |
| builder.factory() | ThreadFactory | No thread is created just by calling factory() | You want to reuse the configuration when creating multiple threads or passing to an executor. |
| factory.newThread(task) | New unstarted Thread | Not yet; the caller or executor will start it | Using the factory under the java.util.concurrent.ThreadFactory contract. |

Short example:

~~~java
Thread platform = Thread.ofPlatform()
        .name("report-worker")
        .unstarted(() -> System.out.println("work"));

System.out.println(platform.getState()); // NEW
platform.start();                         // starts running here
platform.join();                          // waits for completion
~~~

In this example, only the statement printing NEW is guaranteed to execute before start() is called. With code running across multiple threads, the order of print statements between threads can vary: start() **does not mean** the Runnable has completed before the start() call returns. To depend on the result, use join(), Future.get(), or an appropriate synchronization mechanism.

## 3. Platform threads and virtual threads: same API, different execution model

A **platform thread** is typically mapped by the JVM to an OS native thread. It uses a native stack and the OS scheduler; a large number of threads incurs memory, creation/destruction, and scheduling costs.

A **virtual thread** is scheduled by the JVM on platform carrier threads. During many blocking I/O operations supported by the JDK, a virtual thread can suspend and yield its carrier for other work. It is suitable when many concurrent tasks spend most of their time **waiting on I/O**. A virtual thread still uses a Java Thread object, has a logical stack and associated data; it is not completely free.

| Criterion | Thread.ofPlatform() | Thread.ofVirtual() |
|---|---|---|
| Thread type | Platform | Virtual |
| Native OS thread binding | Typically one platform thread has a corresponding native thread | Many virtual threads share carrier platform threads scheduled by the JVM |
| Cost at high volume | Higher due to native thread/stack/scheduler | Typically lower for many waiting tasks, still subject to resource limits |
| Daemon | Configurable or inherited upon creation | Always daemon; cannot be configured as non-daemon |
| Custom priority | Configurable, though effectiveness depends on JVM/OS | Fixed priority, no builder API to adjust |
| Custom ThreadGroup | Configurable | No builder option to assign a group |
| Stack size hint | Can use stackSize(long), platform-dependent | No stackSize on OfVirtual |
| Notable use cases | CPU work with bounded concurrency; controlled worker pools | Many blocking I/O tasks needing a readable sequential code model |

**Do not equate virtual threads with parallel execution on the CPU.** On a machine with P effective CPUs, thousands of virtual threads do not turn P into thousands of cores. For long CPU-bound tasks, CPU demand remains the bottleneck and you should not assume virtual threads will make the task faster.

Thread.currentThread() in code running on a virtual thread returns the **current virtual thread**, not the carrier object. Therefore, names, ThreadLocal, and state should be tied to the task's logical virtual thread, without making assumptions about a specific carrier.

## 4. Shared configuration on both builders

Both OfPlatform and OfVirtual provide common methods:

### 4.1. name(String) and name(String prefix, long start)

- name("job-runner") assigns the same fixed name to each Thread created by the builder; the name is **not required to be unique**.
- name("job-", 0) generates names sequentially as job-0, job-1, ... using a counter starting from a non-negative number. Each time the builder creates a Thread, it uses and increments the counter.
- When factory() is called, the factory receives the configuration state and a copy of the counter at creation time; threads created by the factory have that factory's name sequence. Not all factories share an application-wide counter by default.

Names help distinguish roles in logs, debugging, and thread dumps; they are not a mechanism for generating secure identifiers or guaranteeing execution order.

### 4.2. inheritInheritableThreadLocals(boolean)

Controls whether a new thread **inherits the initial values of InheritableThreadLocal** from the thread creating it. The default value is true; setting it to false is useful when you want to avoid accidentally carrying a parent task's context into a child thread:

~~~java
ThreadFactory factory = Thread.ofVirtual()
        .name("isolated-", 0)
        .inheritInheritableThreadLocals(false)
        .factory();
~~~

This is **not** a switch that disables all ThreadLocal usage. Tasks can still set ThreadLocal themselves; data should be cleared in a finally block when no longer in scope. InheritableThreadLocal should also not be used as a mechanism to pass arbitrary business context through executors: thread creation timing, the factory caller, and worker reuse affect inherited values. When a task needs data, passing it explicitly via parameters or context objects is easier to control.

### 4.3. uncaughtExceptionHandler(handler)

Configures how to receive an **unhandled** Throwable that causes a Thread to terminate abnormally:

~~~java
Thread t = Thread.ofPlatform()
        .name("reporter")
        .uncaughtExceptionHandler((thread, failure) ->
                System.err.println(thread.getName() + ": " + failure))
        .start(() -> {
            throw new IllegalStateException("failed");
        });
t.join();
~~~

This snippet is **illustrative code placed inside a method that can throw InterruptedException**, not a standalone Java program. The handler does not turn a failed task into a success; it supports logging, alerting, and final error handling. Note the difference from ExecutorService.submit(...): many executors **capture exceptions into a Future**, so errors usually surface when calling Future.get() as an ExecutionException rather than being passed to the Thread's uncaught exception handler. For critical tasks, the caller still needs to handle the Future's result and errors.

## 5. Configuration specific to platform threads

Only Thread.Builder.OfPlatform has the following options:

| Option | Meaning | Practical caveat |
|---|---|---|
| daemon(boolean), daemon() | Sets daemon status; daemon() is equivalent to true | Daemon threads do not keep the JVM alive once all non-daemon threads have finished. |
| priority(int) | Specifies priority from Thread.MIN_PRIORITY to Thread.MAX_PRIORITY | Does not guarantee runtime or fairness; effectiveness depends on the OS and ThreadGroup limits. |
| group(ThreadGroup) | Attaches the platform thread to a ThreadGroup | ThreadGroup is a legacy mechanism; do not use it as a resource limit or security boundary. |
| stackSize(long) | Hints the native stack size when creating a platform thread | The JVM/OS may ignore or adjust it; negative values are invalid, and 0 means ignore the hint. |

If daemon/priority/group are not set, a platform thread may inherit values from the creating thread according to Thread API rules. Therefore, to clearly define behavior for specialized workers, set important properties explicitly rather than relying on uncontrolled context.

Example:

~~~java
Thread.Builder.OfPlatform builder = Thread.ofPlatform()
        .name("file-worker-", 0)
        .daemon(false)
        .priority(Thread.NORM_PRIORITY)
        .inheritInheritableThreadLocals(false);

Thread first = builder.unstarted(() -> performWork());
~~~

This is an **illustrative snippet**: performWork() is a hypothetical application method, not a standalone compilable example. You must call first.start() to run it.

**stackSize is not a resource guarantee.** It is a hint about stack size, does not promise the JVM will allocate that exact number of bytes, and does not directly indicate physical RAM usage. Too small a size can lead to StackOverflowError on deep stacks; too large a size can reduce the number of available native threads. Do not set this value based on guesswork.

### Virtual threads do not have daemon(false), priority(...), group(...), or stackSize(...)

Calling these methods on the result of Thread.ofVirtual() **will not compile**, because OfVirtual does not expose them. Virtual threads are always daemon and have a fixed priority. If you want to set task counts, deadlines, connection limits, or application exit conditions, use task management, executors, and synchronization mechanisms instead of trying to change platform-only properties.

## 6. Standalone example 1: creating platform/virtual threads from two factories

This is a complete Java 21+ program demonstrating configuration, name counters, unstarted newThread, start, join, and thread identification.

Save the file **ThreadBuilderBasics.java**:

~~~java
import java.util.concurrent.ThreadFactory;

public class ThreadBuilderBasics {
    public static void main(String[] args) throws InterruptedException {
        ThreadFactory platformFactory = Thread.ofPlatform()
                .name("platform-worker-", 1)
                .daemon(false)
                .priority(Thread.NORM_PRIORITY)
                .inheritInheritableThreadLocals(false)
                .factory();

        ThreadFactory virtualFactory = Thread.ofVirtual()
                .name("virtual-task-", 1)
                .inheritInheritableThreadLocals(false)
                .factory();

        Thread p = platformFactory.newThread(() -> {});
        Thread v = virtualFactory.newThread(() -> {});
        System.out.println("before=" + p.getState() + "," + v.getState());

        p.start();
        v.start();
        p.join();
        v.join();

        System.out.println("platform=" + p.getName()
                + ", virtual=" + p.isVirtual()
                + ", daemon=" + p.isDaemon());
        System.out.println("virtual=" + v.getName()
                + ", virtual=" + v.isVirtual()
                + ", daemon=" + v.isDaemon());
        System.out.println("after=" + p.getState() + "," + v.getState());
    }
}
~~~

Compile and run with JDK 21+:

~~~bash
javac --release 21 ThreadBuilderBasics.java
java ThreadBuilderBasics
~~~

Exact output for the example:

~~~text
before=NEW,NEW
platform=platform-worker-1, virtual=false, daemon=false
virtual=virtual-task-1, virtual=true, daemon=true
after=TERMINATED,TERMINATED
~~~

**Output analysis:**

1. factory.newThread(...) creates two Threads in the NEW state; the empty Runnables have not run yet.
2. Names are generated from the prefix and a counter starting at 1, separate for each factory.
3. p.start() and v.start() start two execution paths. Do not assume the order of the two tasks because scheduling can vary.
4. join() waits for both to finish before reading the final state; the TERMINATED result is deterministic.
5. isVirtual() identifies the thread type; isDaemon() shows the platform/virtual difference. Platform is set to daemon(false); virtual is inherently always daemon.

The command javac --release 21 requires a compiler that supports release 21 (JDK 21 or higher); on JDK 17 it will report unrecognized APIs or release. You can replace the empty Runnable with real work, but avoid depending on console print ordering between threads.

## 7. What does ThreadFactory do, and what does it not do?

ThreadFactory is a functional interface with one primary method:

~~~java
Thread newThread(Runnable runnable);
~~~

By contract, newThread returns an **unstarted Thread**; the factory caller (or executor) is responsible for starting it. factory() on Thread.Builder creates a ThreadFactory matching the current configuration. A factory created by a builder is **safe when multiple threads call newThread concurrently**; Thread.Builder itself is **not thread-safe** and should not be shared across different threads simultaneously modifying configuration and creating threads.

Example using a fixed platform thread pool:

~~~java
ThreadFactory workerFactory = Thread.ofPlatform()
        .name("cpu-worker-", 0)
        .daemon(false)
        .factory();

java.util.concurrent.ExecutorService pool =
        java.util.concurrent.Executors.newFixedThreadPool(4, workerFactory);

// Actual tasks are submitted/executed by the application; must shut down and wait for completion.
~~~

This is a **snippet for integrating into a method**, not a standalone program. The executor decides **how many workers** there are, how work is fetched, and when workers start; the factory decides **how each Thread is created**. newFixedThreadPool(4, ...) limits the number of workers but uses an **unbounded queue** by default; it does not automatically protect the application from an unlimited backlog of waiting tasks. For workloads requiring backpressure, consider ThreadPoolExecutor with a bounded queue, timeouts, and an explicit rejection policy.

Common pitfall: creating a virtual ThreadFactory **does not automatically turn a fixed thread pool into an executor with one virtual thread per task**. A fixed pool still uses a finite set of workers according to that executor's mechanism; each worker picks up multiple tasks sequentially. If you want a separate virtual thread for each task, use Executors.newVirtualThreadPerTaskExecutor() or Executors.newThreadPerTaskExecutor(virtualFactory).

### Choosing the right executor

| Goal | Reasonable combination | What you must control yourself |
|---|---|---|
| At most a few reusable platform workers | newFixedThreadPool(n, platformFactory) or ThreadPoolExecutor | Queue, overload policy, timeouts, shutdown. |
| One virtual thread per task, default | Executors.newVirtualThreadPerTaskExecutor() | Number of accepted tasks, downstream resources, and cancellation. |
| One virtual thread per task, custom name/handler | Executors.newThreadPerTaskExecutor(Thread.ofVirtual().name("task-", 0).factory()) | Thread-per-task **has no thread cap** of its own; resource limits are needed. |
| Managing the lifecycle of a few Threads yourself | builder.start(...) / unstarted(...), join() | Manual startup, completion, and error handling. |

**Do not use an unbounded Executors.newThreadPerTaskExecutor(platformFactory)** for heavy loads without understanding native thread costs. This API creates a new thread for every task, does not reuse threads like a fixed pool, and has no built-in thread limit.

## 8. Standalone example 2: virtual ThreadFactory + executor + Semaphore

One virtual thread per task does not mean the underlying system can handle unlimited concurrent tasks. This example uses a Semaphore to allow many virtual threads to be created, while only **two tasks** enter a section simulating a limited resource at the same time.

Save the file **VirtualFactoryExecutor.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.ThreadFactory;

public class VirtualFactoryExecutor {
    public static void main(String[] args) throws Exception {
        ThreadFactory factory = Thread.ofVirtual()
                .name("io-task-", 0)
                .inheritInheritableThreadLocals(false)
                .factory();
        Semaphore limit = new Semaphore(2);

        try (ExecutorService executor = Executors.newThreadPerTaskExecutor(factory)) {
            List<Future<String>> results = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                final int id = i;
                results.add(executor.submit(() -> {
                    limit.acquire();
                    try {
                        Thread.sleep(20);
                        return "completed-" + id;
                    } finally {
                        limit.release();
                    }
                }));
            }
            for (Future<String> result : results) {
                System.out.println(result.get());
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 VirtualFactoryExecutor.java
java VirtualFactoryExecutor
~~~

Output:

~~~text
completed-0
completed-1
completed-2
completed-3
~~~

**Why is the output in a fixed order?** Execution may finish out of order, but the program stores Futures in submission order and prints results by iterating over that list. Future.get() waits for the corresponding task to finish, regardless of when the result was processed.

**Why is finally placed after acquire()?** A thread should only release a permit after acquire() succeeds. If interrupted while waiting in acquire(), an exception is thrown before entering try/finally, so someone else's permit is not released. Once a permit is acquired, sleep() may be interrupted; finally still runs to return the permit.

**Why try-with-resources?** Since Java 21, ExecutorService can be closed with try-with-resources; close() performs an orderly shutdown and waits for tasks to finish. For applications with strict deadlines, appropriate timeout, cancellation, and shutdown policies may be needed instead of waiting indefinitely.

**Limitations of the example:** The Semaphore caps access to the simulated resource, **not** the number of virtual threads created by the executor or the number of accepted tasks. A real application still needs bounded admission/backpressure, deadlines, connection limits, memory limits, and upstream queues. Thread.sleep(20) is used to illustrate waiting; it is not a speed benchmark or proof of performance advantage.

## 9. Configuration and error management in real applications

### 9.1. Creating tasks and managing lifecycles

- If using builder.start(...) directly, always keep the necessary references to call join() or use coordination mechanisms if the process must wait for results.
- Virtual threads are daemon: the JVM can begin exiting when no non-daemon threads remain; creating virtual threads **is not enough** to guarantee critical tasks finish before the process exits.
- If using an executor, ensure shutdown/close, await tasks, or apply cancellation policies when deadlines are exceeded.
- Do not start() a Thread a second time: a Thread that has already started, even if completed, cannot be restarted and will throw IllegalThreadStateException. You can create a **new Thread from the same factory**.

### 9.2. Cancellation and interruption

Thread.interrupt() does not forcibly kill a task at any arbitrary point. Many blocking APIs respond with InterruptedException, but tasks must cooperate by checking and exiting properly. In a catch block for InterruptedException where you cannot rethrow, you should usually call Thread.currentThread().interrupt() to restore the flag, then finish the task or let the caller decide.

With ExecutorService.submit(...), task errors are wrapped in the Future; Future.get() can throw ExecutionException. Future.cancel(true) requests interruption when possible, and does not prove that resources have been released or that the task reached a successful business state.

### 9.3. Handlers do not replace business error handling

uncaughtExceptionHandler is used for unhandled errors at the top level of a Thread. It is not a retry mechanism, does not automatically record rollbacks, and does not replace Future.get(). If the handler itself throws an error, the runtime does not guarantee additional handling as you might intend. Keep handlers simple and avoid adding risky operations inside them.

### 9.4. Thread context and data

InheritableThreadLocal can pass data to child threads by default; in a pool, a worker may be created at a time far removed from task submission. With virtual thread-per-task, a large number of threads means data in ThreadLocal can increase memory overhead. Do not use ThreadLocal to cache large objects per virtual thread; avoid carrying sensitive data or uncontrolled mutable state across tasks. Pass parameters explicitly, scope lifecycles, and clean up in finally when needed.

## 10. Common misconceptions

**"Thread.Builder is similar to an ExecutorService."** False. A builder describes **how to create a Thread**; an executor decides **task acceptance, queueing, work scheduling, and shutdown**. A ThreadFactory is also only responsible for creating Threads and does not manage queues itself.

**"factory.newThread(task) runs the task immediately."** False. It returns an unstarted Thread. If using it yourself, you must call start(); if handed to an executor, the executor manages starting it.

**"You can change daemon, priority, or stackSize of a virtual thread via the builder."** False. Those APIs only exist on OfPlatform. Virtual threads are always daemon, have fixed priority, and do not provide native stack customization through the builder.

**"name("worker") creates a unique name for every thread."** False. It sets a fixed name. To get a numbered sequence of names, use name("worker-", start).

**"A builder can be used freely from multiple threads."** False. Thread.Builder is not thread-safe; the ThreadFactory produced by builder.factory() is thread-safe. Finish configuring and share the factory, avoiding concurrent mutation of the builder.

**"Creating millions of virtual threads is always safe."** False. Each task still carries memory, objects, and references, and may hold connections, mutexes, file descriptors, or call other services. You must limit incoming load and expensive resources according to actual capacity.

**"Virtual threads create more CPUs."** False. They help utilize blocking I/O wait time, not increase hardware capacity. For compute-heavy tasks, controlled concurrency limits remain important.

**"You don't need to know about pinning or blocking."** Inaccurate. Whether the JVM yields the carrier when a virtual thread blocks depends on the operation type and JDK version; native calls, native/foreign code, or synchronization mechanisms in some JDKs can prevent unmounting. For example, pinning issues related to synchronized have been significantly improved in newer JDKs compared to JDK 21. You must observe and test on the exact runtime version being deployed, rather than applying conclusions across all versions.

**"ThreadMXBean.getThreadCount() is the total of platform + virtual threads."** False in Java 21: java.lang.management.ThreadMXBean tracks **platform threads** and does not count virtual threads. If the number of threads in the system grows primarily due to virtual threads, metrics from MXBean will not reflect all running tasks.

**"Increasing thread priority fixes throughput problems."** No guarantee. Scheduling also depends on load, OS, CPU, waiting, locks, and container quotas. Priority is not a substitute for measurement.

## 11. Observation and debugging

Investigate issues in order from symptom to cause:

| Symptom | What to observe | How to address |
|---|---|---|
| Task does not appear to run | Is the Thread in NEW? Was start() called? Has the Executor shut down? | Distinguish unstarted/newThread from start; check lifecycle. |
| Duplicate thread names | Using name(String) or name(prefix, start)? | Name using an incrementing sequence and categorize task roles. |
| Process exits before tasks finish | Are only daemon/virtual threads left? | Join/Future.get/close executor, design proper shutdown. |
| Platform threads or native memory increasing | Creating an OS thread per task? How are pool/queue configured? | Limit workers, reuse pools, measure native stack/OS limits. |
| Many virtual tasks created but latency increases | Backend, connection pool, semaphore, queue, timeout | Set downstream resource limits and backpressure. |
| Errors get "lost" | Using submit() without reading Future? | Read Future.get(), log task errors; handlers are not a replacement. |
| ThreadLocal retaining unexpected data | Pool reuse, inheritable values, cleanup | Pass context explicitly, call remove() in the proper scope. |

For practical diagnostics, give workers/virtual tasks meaningful names, and use Java Flight Recorder (JFR) and thread dump tools appropriate for your **JDK version**. Monitor CPU, memory, context switches, task count, queue depth, downstream latency, and cancellation in parallel. For platform threads, ThreadMXBean or OS thread tools are useful; for virtual threads, also use observability tools that support virtual-thread events/dumps because many classic thread counters only reflect platform threads.

Do not run benchmarks with millions of threads on machines without controlled test resource limits: performance is governed by workload, CPU, native memory, heap, connections, and wait times. The runnable examples in this lesson demonstrate API semantics and do **not** by themselves compare the speed of platform and virtual threads.

## 12. Decision diagram and checklist

~~~text
Need to create a Thread in Java 21+?
  │
  ├─ A few tasks, managing lifecycle yourself
  │      └─ Thread.ofPlatform()/ofVirtual()
  │           → configure → start(...) or unstarted(...).start()
  │           → join()/error handling
  │
  └─ Many tasks needing result management/resource closing
         │
         ├─ CPU-bound or need to limit native worker count
         │      └─ platform ThreadFactory + executor with appropriate workers/queue
         │
         └─ Mostly blocking I/O, many concurrent tasks
                └─ virtual ThreadFactory + thread-per-task executor
                     + downstream resource limits, timeouts, backpressure
~~~

Before applying this in a real application, verify:

1. You are using JDK 21+ and understand the difference between builder.start, builder.unstarted, and factory.newThread.
2. You have chosen the right thread type for the workload and clearly defined who starts, who joins, and who closes the executor.
3. You have assigned role-descriptive names and do not treat name as a unique ID.
4. You have used the right options: daemon/priority/group/stackSize for platform; virtual does not customize those properties.
5. You have considered InheritableThreadLocal inheritance, uncaught exception handling, Future errors, and interruption.
6. You have limited connections/expensive resources, and decided task admission rates and overload policies.
7. You have measured on the actual runtime/OS in use, avoiding evaluating virtual concurrency solely with MXBean platform-thread metrics.

## 13. Official API documentation for reference

- Thread.Builder (Java 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.html
- Thread.Builder.OfPlatform: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfPlatform.html
- Thread.Builder.OfVirtual: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.Builder.OfVirtual.html
- ThreadFactory: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ThreadFactory.html
- Executors: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
- ThreadMXBean: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html

**Key takeaway:** Thread.Builder clarifies **thread type and thread creation configuration**; start()/unstarted()/factory() clarify **when and how creation/startup happens**. ThreadFactory passes configuration into task management infrastructure but does not replace an executor, concurrency limits, error handling, or shutdown. Platform threads and virtual threads share much of the Thread API, yet have different resource characteristics and operational choices.
