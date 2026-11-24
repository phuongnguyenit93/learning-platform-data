# Platform Threads, Thread Groups, and Virtual Threads in Java (Java 21+)

## Objectives

After this lesson, you will be able to:

- Distinguish **platform threads**, **virtual threads**, and **`ThreadGroup`**, and understand why a thread group is not a third kind of thread.
- Create, name, wait for completion of, and cooperatively cancel a thread via `Thread`, `join()`, `interrupt()`, or `Future`.
- Explain how the JVM uses carrier platform threads to execute virtual threads and why I/O blocking operations can unmount a carrier.
- Use `ThreadGroup` within its proper scope without confusing it with an executor/thread pool or a quota.
- Choose an appropriate handling model for CPU-bound/I/O-bound workloads and verify how Spring uses executors.

**Version scope:** Complete examples use **Java 21+** APIs, where virtual threads became a standard feature under JEP 444. Pinning caused by `synchronized` monitors changed starting in **Java 24** under JEP 491; version-specific notes are separated in a section below.

## 1. Concept Map: Two Thread Kinds and One Grouping Structure

A JVM process has a shared heap across multiple threads. Each thread has its own call stack and execution state, yet can access shared objects in the heap. This is the foundation of concurrency and also the source of race conditions, deadlocks, and the need for synchronization.

| Concept | Nature | Who Schedules It? | Purpose |
| --- | --- | --- | --- |
| **Platform thread** | A `java.lang.Thread` object bound to an OS thread for its entire lifetime | The OS schedules platform threads | Running work with a controlled number of OS threads |
| **Virtual thread** | A `java.lang.Thread` object that the JVM mounts onto a carrier platform thread when execution is needed | The JVM schedules virtual threads; the OS schedules carriers | Scaling concurrent tasks when most time is spent waiting |
| **`ThreadGroup`** | An object that organizes platform threads in a parent–child tree | **Does not schedule** | Historical grouping/observation capability; does not provide full task management |

**Key point:** Platform threads and virtual threads both implement the `Thread` programming interface. `ThreadGroup` is a **thread-grouping object**, not a thread, executor, pool, or third scheduler type.

### Lifecycle and `Thread.State` States

- `NEW`: the thread has been created but `start()` has not been called yet.
- `RUNNABLE`: executing or ready to execute according to the Java thread state model. It does not mean it is necessarily occupying a CPU at the exact moment of observation.
- `BLOCKED`: waiting to acquire a **monitor lock** to enter `synchronized`. It is not a generic name for all types of I/O waiting.
- `WAITING`: waiting indefinitely, for example `join()` without a timeout or certain signal-waiting operations.
- `TIMED_WAITING`: waiting for a bounded duration, such as `Thread.sleep(...)` or `join(timeout)`.
- `TERMINATED`: the execution method has finished. A terminated thread cannot be `start()`ed again.

`getState()` returns a snapshot that can change immediately. Do not poll thread state in a loop to decide which thread should run; use appropriate synchronization primitives, `Future`, or completion notifications.

## 2. Platform Threads: Lifecycle Bound to an OS Thread

When creating a platform thread, the JVM uses a corresponding operating system thread. The OS schedules execution, performs context switching, and manages its stack/resources. Creating too many platform threads can exhaust memory and hit OS or JVM limits. Exact sizes and limits depend on the environment; there is no universal number.

Three common creation patterns:

- `new Thread(runnable, "name")`: traditional way, creates a platform thread.
- `Thread.ofPlatform().name("name").start(runnable)`: Java 21 builder that expresses intent clearly.
- `Thread.ofPlatform().factory()`: provides a `ThreadFactory` for task-management components.

**`start()` vs. `run()`:** `thread.start()` asks the JVM to start a thread to execute `run()`; calling `thread.run()` directly only executes the method on the **current thread**. After calling `start()`, it cannot be called a second time on the same `Thread` object.

### Example 1 — Two Thread Kinds Using the Same `Thread` API

Save the code to `ThreadKindsDemo.java`:

~~~java
public class ThreadKindsDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread platform = Thread.ofPlatform()
                .name("platform-demo")
                .start(() -> {
                    Thread current = Thread.currentThread();
                    System.out.println(current.getName()
                            + " | virtual=" + current.isVirtual());
                });
        platform.join();

        Thread virtual = Thread.ofVirtual()
                .name("virtual-demo")
                .start(() -> {
                    Thread current = Thread.currentThread();
                    System.out.println(current.getName()
                            + " | virtual=" + current.isVirtual());
                });
        virtual.join();
    }
}
~~~

Compile and run (JDK 21+):

~~~bash
javac ThreadKindsDemo.java
java ThreadKindsDemo
~~~

Exact output:

~~~text
platform-demo | virtual=false
virtual-demo | virtual=true
~~~

Here the first `join()` finishes before the second thread is created, so the print order is fixed. If both were started before waiting, the printed lines could appear in reverse order due to non-deterministic scheduling.

`join()` waits for a **specific thread** to finish; `sleep()` only pauses briefly in the current thread. `sleep()` does not establish work coordination and does not automatically release monitor locks held by the thread. Never use `sleep(100)` to "ensure" another thread has finished.

### Concurrency and Thread Safety

A shared heap means `counter++` across multiple threads can lose updates because it is a read–compute–write sequence, not an atomic increment. Use `AtomicInteger`, `synchronized`, `Lock`, or a design that reduces shared state as required. `volatile` provides visibility and ordering guarantees, but does not automatically make an update sequence atomic. Virtual threads **do not cure** race conditions or deadlocks.

## 3. `ThreadGroup`: The Legacy Way to Group Threads

`java.lang.ThreadGroup` represents a named group that can contain subgroups. Thread groups form a tree; a group has a maximum priority limit for platform threads inside it. This API dates back to very early Java versions, when thread grouping and some diagnostic features relied on groups. Java SE 21 explicitly notes that new applications **rarely need** to create a `ThreadGroup`.

### Example 2 — Creating a Platform Thread in a Group

Save as `ThreadGroupDemo.java`:

~~~java
public class ThreadGroupDemo {
    public static void main(String[] args) throws InterruptedException {
        ThreadGroup group = new ThreadGroup("workers");

        Thread worker = new Thread(group, () -> {
            Thread current = Thread.currentThread();
            System.out.println(current.getThreadGroup().getName());
        }, "platform-worker");

        worker.start();
        worker.join();
        System.out.println("done");
    }
}
~~~

Run:

~~~bash
javac ThreadGroupDemo.java
java ThreadGroupDemo
~~~

Output:

~~~text
workers
done
~~~

The constructor `new Thread(group, runnable, name)` creates a **platform thread** as a member of `group`. In this example, reading the group name happens while the thread is alive. For a terminated thread, `getThreadGroup()` may return `null`, so do not use this method as a permanent registry.

### Limitations to Remember

1. `group.activeCount()` is an **instantaneous estimate** of live platform threads in the group and its subgroups, **not** the number of queued tasks or a hard quota.
2. `group.enumerate(array)` copies live **platform threads** into an array, racing with threads starting/terminating; if the array is too small, results may be incomplete.
3. `group.interrupt()` is a historical API; it does not build waiting, timeouts, results, structured cancellation, or exception-handling policies.
4. A thread group is not a sandbox or security isolation mechanism, nor does it control the JVM scheduler.

For **virtual threads**, the Java runtime provides **a special group** when `getThreadGroup()` is called. The virtual thread creation API **does not allow assigning** a custom `ThreadGroup`; virtual threads are **not counted** by `activeCount()`, **not enumerated** by `enumerate()`, and **not interrupted** by `ThreadGroup.interrupt()`.

If you need to accept tasks, limit worker counts, await results, and cancel, use `ExecutorService`/`Future` or higher-level coordination constructs. If you need to limit concurrent DB/HTTP calls, place the limit **on that resource**, such as a connection pool, semaphore, or rate limiter. A thread group cannot substitute for either role.

## 4. Virtual Threads: Many Waiting Tasks Without Holding Many OS Threads

**Virtual threads** were standardized in Java 21 (JEP 444, Project Loom). They are especially useful for the **one task/request per thread** model, where work mainly waits on HTTP, JDBC, sockets, or JVM-supported blocking operations.

### Mounting, Unmounting, and Carriers

A virtual thread can run on a carrier platform thread for a while, then temporarily yield the carrier:

1. A task is initialized as a virtual thread with its own `Thread` object.
2. The JVM schedules and **mounts** the virtual thread onto a carrier. The OS allocates CPU to the carrier.
3. Upon encountering an unmount-capable blocking operation, the JVM saves the virtual thread's continuation state and **releases the carrier** so it can run another virtual thread.
4. Once the wait condition is ready, the JVM resumes the virtual thread, possibly mounting it onto a **different carrier**.

Conceptual diagram:

~~~text
Virtual A  [CPU] ------- waiting I/O -------- [CPU] --> done
                   (A unmounts)       (A remounts)
Carrier 1  [A] [Virtual B] [Virtual C] [ ... ]
Carrier 2  [Virtual D] [Virtual E] [ ... ]
~~~

The diagram only expresses sharing carriers over time, not actual scheduling order. Inside the task, `Thread.currentThread()` **is still the task's virtual thread**, not the carrier. Therefore, never use the carrier's name as a request identifier.

The number of virtual threads can be vastly larger than the number of carriers, yet they **still consume** memory for tasks, data, and stacks; external systems still have limits on file descriptors, connections, and throughput. Virtual threads primarily help the **throughput of wait-heavy workloads**, without directly reducing single-query latency or increasing CPU core count.

### Creating Virtual Threads via Java 21 APIs

Common approaches:

~~~java
Thread direct = Thread.ofVirtual().name("request-1")
        .start(() -> System.out.println(Thread.currentThread().isVirtual()));

Thread simple = Thread.startVirtualThread(() -> {
    System.out.println("a virtual task");
});

ThreadFactory factory = Thread.ofVirtual().name("job-", 0).factory();
~~~

This snippet **only demonstrates the API** (add `import java.util.concurrent.ThreadFactory;` to a program containing it). In a real program, you must manage completion/cancellation and error handling for each task, for example using `join()` or `Future`. `Thread.startVirtualThread(runnable)` creates and immediately starts a virtual thread. A virtual thread's name may be empty if not explicitly set.

Virtual threads are **daemon threads**, have a fixed priority of `Thread.NORM_PRIORITY`, and do not support custom group configuration. If an application has only daemon threads remaining, the JVM may exit while some virtual tasks have not finished; always have a waiting and lifecycle-management strategy.

### Example 3 — One Virtual Thread per Task

Save as `VirtualTasksDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualTasksDemo {
    public static void main(String[] args) throws Exception {
        try (var executor = Executors.newVirtualThreadPerTaskExecutor()) {
            List<Future<String>> results = new ArrayList<>();

            for (int i = 1; i <= 3; i++) {
                int taskId = i;
                results.add(executor.submit(() -> {
                    Thread.sleep(50); // simulate wait time
                    return "task-" + taskId
                            + " | virtual=" + Thread.currentThread().isVirtual();
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
javac VirtualTasksDemo.java
java VirtualTasksDemo
~~~

Output:

~~~text
task-1 | virtual=true
task-2 | virtual=true
task-3 | virtual=true
~~~

`newVirtualThreadPerTaskExecutor()` creates **a new virtual thread for each task**; the three tasks may run interleaved, yet `Future.get()` in the second loop retrieves results in submission order, so the stdout shown is deterministic. `Thread.sleep(50)` only simulates waiting and is **not an I/O benchmark**. `try-with-resources` closes the executor and waits for tasks to finish according to Java 21's `ExecutorService.close()` contract.

**Do not pool virtual threads.** The design goal is to create a new thread for a task and let it terminate. Fixed pools are typically used to control the number of OS threads in the platform-thread model; pooling virtual threads indirectly limits task counts, complicates the model, and does not substitute for resource protection. To allow only 20 concurrent DB queries, use a **20-slot connection pool/semaphore**, not a 20-worker virtual thread pool.

## 5. Choosing a Model Based on Workload Nature

| Scenario | Recommended Direction | Reason |
| --- | --- | --- |
| Few long computations consuming CPU continuously | Platform thread executor with controlled parallelism | CPU cores limit actual parallel execution |
| Many independent requests with heavy blocking I/O wait time | Virtual thread per request/task, plus downstream limits | Carriers can serve other tasks while one task waits |
| Need results/cancellation/timeouts for many tasks | `ExecutorService`/`Future` and suitable cancellation mechanisms | Thread groups do not own task lifecycles |
| Service using an event loop / non-blocking Reactive Streams | Continue evaluating on the current non-blocking model | Virtual threads do not automatically improve already non-blocking pipelines |
| Backend allows only 20 DB connections | Connection pool capped to backend capacity | 10,000 virtual threads do not create 10,000 valid connections |

Distinguish two metrics: **throughput** is the number of tasks completed in a time interval; **latency** is the time to complete a single task. Virtual threads can improve service throughput when many OS threads were previously held while waiting, but they do not guarantee speeding up individual requests. For CPU-bound work, more virtual threads **do not create more CPUs**.

In real evaluations, measure CPU, heap, GC, p95/p99 latency, throughput, timeouts, error rate, queued tasks, and connection pool status. A `sleep` example on a local machine only teaches the API; it does not prove production performance.

## 6. Interruption, Cooperative Cancellation, and Shared Memory

`Thread.interrupt()` is a **stop-request signal**, not an immediate thread-kill command. A task must check the interrupted flag itself or pass through interrupt-aware calls such as `sleep()`, `wait()`, `join()`, and many library blocking operations. This rule applies to both thread kinds.

Example snippet **inside a `Runnable`**:

~~~java
try {
    Thread.sleep(1_000);
    // continue work
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // restore interrupt flag
    return; // exit the task intentionally
}
~~~

This is a fragment to explain exception handling, not a standalone Java class. When `InterruptedException` is thrown, the interrupted flag has usually been cleared; if caught at this layer and you cannot propagate it further, restore the flag for higher layers. In methods declaring `throws InterruptedException`, you can let the exception propagate.

With `Future`, `cancel(true)` requests interrupting the running task; it does not guarantee immediately stopping native calls or I/O that does not support interruption. Always close resources in `finally`/`try-with-resources`, configure network/DB timeouts, and design rollback on cancellation.

**Happens-before:** According to the Java Memory Model, actions prior to calling `Thread.start()` have a happens-before relationship with actions of the new thread; actions inside a terminated thread have a happens-before relationship with a thread calling `join()` and observing successful termination. Yet two concurrently running threads still need proper synchronization mechanisms for shared state, such as `AtomicInteger` or locks.

## 7. Limitations and Pitfalls of Virtual Threads

### 7.1. Pinning by JDK Version

A virtual thread can become **pinned** to its carrier: when it blocks, the carrier is also not freed to run another virtual thread. Pinning typically affects scalability under load; by itself it does not necessarily produce wrong results.

- **Java 21–23:** blocking operations inside a `synchronized` region or when native/foreign function frames are on the stack can pin the carrier. Avoid holding monitors across long I/O calls; you can move I/O outside locked sections or consider `ReentrantLock` with appropriate measurement.
- **Java 24+:** **JEP 491** enables handling `synchronized` without pinning the carrier as before. Pinning can still arise in native/foreign paths and specific library cases. Do not assume every blocking call is guaranteed to unmount.

Do not mass-replace `synchronized` with `ReentrantLock` without measuring. Even without pinning, **a lock still serializes** access to the protected data. Analyze according to your JDK and actual application stack.

### 7.2. `ThreadLocal`, Logging Context, and Request State

`ThreadLocal` and `InheritableThreadLocal` work on virtual threads, but since each task creates a distinct thread, using `ThreadLocal` to cache large resources per thread can be very memory-expensive and provides no reuse like a platform thread pool. For MDC, security context, or transaction context, understand the framework's context propagation/cleanup mechanisms; avoid assuming context is automatically shared from the carrier. When managing manually, clean up in `finally` and call `remove()`.

### 7.3. Protecting Downstream Dependencies

Removing the OS thread count limit can expose other bottlenecks sooner: DB connection pools, upstream APIs, file descriptors, rate limits, or queues. Design with **timeouts, capacity limits, backpressure, and controlled retries** at resource boundaries. Virtual threads do not automatically enforce any quotas.

### 7.4. Monitoring and Diagnostics

- `Thread.currentThread().isVirtual()` helps identify the running thread.
- `ThreadGroup.activeCount()`, `ThreadGroup.enumerate()`, and `Thread.getAllStackTraces()` do not return a complete list of virtual threads; avoid using them to count concurrent virtual tasks.
- On supported JVMs, `jcmd <pid> Thread.dump_to_file -format=json <file>` can export a JSON thread dump; replace `<pid>` and `<file>` with real values.
- JDK Flight Recorder (JFR) provides the `jdk.VirtualThreadPinned` event to find pinning. On Java 21 you can use `-Djdk.tracePinnedThreads=full` when investigating; prefer tools/flags appropriate for your current version.

## 8. Connection to Spring Framework and Spring Boot

Java threads appear in Spring applications via request-handling, `@Async`, schedulers, listeners, and executors used by the framework.

- With Spring Framework, `@Async` executes work via a **configured/selected executor**. The annotation alone does not prove the task is running on a virtual thread; inspect the executor and check `Thread.currentThread().isVirtual()` at the execution point.
- **Spring Boot 3.2+** supports enabling virtual threads on **Java 21+** via `spring.threads.virtual.enabled=true`. Supported auto-configured Boot components will use virtual threads depending on the version, though custom `Executor` beans can change executor selection.
- Virtual threads are daemons; if a daemon scheduler/task is what keeps the application alive, verify whether the JVM could exit. Spring Boot provides `spring.main.keep-alive=true` for appropriate cases.
- Blocking JDBC/HTTP can benefit when workloads are wait-heavy, yet DB connection counts and timeouts remain hard boundaries. For Reactor/WebFlux, never block the event loop indiscriminately; virtual threads do not automatically replace reactive design.

Configuration example **for a Spring Boot application that supports the feature** in `application.properties`:

~~~properties
spring.threads.virtual.enabled=true
~~~

After configuring, load-test and verify the actual executor, especially when the application has custom executors, task schedulers, or custom web servers. A valid property does not mean every call in the application has automatically moved to virtual threads.

## 9. Common Mistakes

1. **Calling `run()` thinking you got a new thread.** You need `start()`.
2. **Using `sleep()` to guarantee task ordering.** Use `join()`, `Future.get()`, or synchronization tools; `sleep()` also does not release held monitors.
3. **Treating `ThreadGroup` as a thread pool/concurrency limiter.** A group manages neither task queues nor quotas.
4. **Using `ThreadGroup.enumerate()` to count virtual threads.** This API ignores virtual threads.
5. **Believing virtual threads make CPU-bound code faster.** CPU cores and algorithms remain the limits.
6. **Creating a fixed virtual thread pool for all tasks.** Create a virtual thread per task and limit downstream resources directly.
7. **Ignoring interruption and timeouts.** Systems can hold resources or let tasks wait too long.
8. **Assuming `synchronized` pinning behaves identically on Java 21 and Java 24+.** JEP 491 changed the mechanism.
9. **Assuming `ThreadLocal` in virtual tasks reuses caches like a platform thread pool.** Each virtual task uses a different thread; consider memory and cleanup.

## 10. Self-Check Questions

**Question 1:** Why is `ThreadGroup` not on par with platform/virtual threads?  
**Answer:** It is a structure for grouping platform threads, not an execution unit or scheduler.

**Question 2:** What should a service with thousands of requests spending most of their time waiting on HTTP consider?  
**Answer:** Virtual threads per request/task may suit JVM-supported blocking I/O, paired with timeouts, upstream limits, and load testing.

**Question 3:** Does `RUNNABLE` guarantee a thread is currently occupying a CPU?  
**Answer:** No; Java combines ready and running states, and observing it is only a snapshot.

**Question 4:** Why do virtual threads not allow a 20-connection DB to serve 10,000 queries simultaneously?  
**Answer:** Virtual threads only reduce JVM waiting overhead; the connection pool still has only enough resources for 20 queries at the same instant.

**Question 5:** `spring.threads.virtual.enabled` is enabled, yet `@Async` still runs on a platform thread—what should you check?  
**Answer:** Spring Boot/JDK version, which executor `@Async` selects, custom `Executor` beans, and an `isVirtual()` verification check.

## References

- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): design, runtime, API, scalability.
- [Java SE 21 `Thread` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): behavior and lifecycle of both thread kinds.
- [Java SE 21 `ThreadGroup` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadGroup.html): thread groups and virtual thread limitations.
- [Oracle Java 21 — Virtual Threads](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): mount/unmount, blocking, pinning, diagnostics.
- [JEP 491 — Synchronize Virtual Threads without Pinning](https://openjdk.org/jeps/491): changes starting in Java 24.
- [Spring Boot Reference — Virtual Threads](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.virtual-threads): support and lifecycle in Spring Boot.
