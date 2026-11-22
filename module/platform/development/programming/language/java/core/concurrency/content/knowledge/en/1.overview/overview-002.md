# Process, platform thread, virtual thread, and task in Java

## 1. The big picture: what does a program run on?

When reading a Java application where multiple jobs happen concurrently, you need to separate four concepts:

- **Process**: a single execution of a program managed by the operating system, with its own address space and resources isolated by the OS. Running `java Main` normally creates one process containing the JVM.
- **Platform thread**: a `java.lang.Thread` that the JVM binds to an operating system thread (OS thread). The OS schedules that thread to run on CPU cores.
- **Virtual thread**: a lightweight `java.lang.Thread` managed by the JVM and scheduled onto platform threads used as **carriers**. Virtual threads are a standard feature starting in Java 21; the `Thread.ofVirtual()` and `Executors.newVirtualThreadPerTaskExecutor()` APIs are finalized.
- **Task**: a unit of work to be performed, such as “read data”, “handle a request”, or “compute a result”. A task is **the work**, while a thread is **the execution context for the work**. A `Runnable` or `Callable` describes a task, but does not run on its own simply by creating the object.

Typical relationship:

```text
Operating System
  ├── Process A: JVM
  │     ├── platform thread "main" ──────────> runs Java code
  │     ├── platform thread in a thread pool -> runs multiple tasks sequentially
  │     └── carrier platform threads
  │           ├── virtual thread A ──────────> task A (when scheduled)
  │           ├── virtual thread B ──────────> task B (when scheduled)
  │           └── virtual thread C ──────────> task C (when scheduled)
  └── Process B: another program
```

This diagram illustrates logical relationships; it does not imply that each virtual thread has a dedicated, fixed carrier. A single carrier can run multiple virtual threads **in turn**; while running, a virtual thread is mounted onto a carrier.

### Quick comparison

| Criterion | Process | Platform thread | Virtual thread | Task |
| --- | --- | --- | --- | --- |
| Nature | OS process unit | Java thread bound to an OS thread | Java thread scheduled by the JVM onto a carrier | A piece of work or computation |
| Who schedules execution? | The OS manages processes/OS threads | The OS schedules the OS thread | The JVM schedules the virtual thread onto a carrier; the OS schedules the carrier | Chosen by the caller, executor, or coordinator |
| Memory/state | Process address space and resources, usually isolated from other processes | Thread stack and state; shares the process heap | Logical thread stack/state; shares the process heap | Input data, state, and result depending on design |
| Cost when creating many | Relatively high | Significant OS thread resources and stack | Typically much lower for large numbers of I/O-waiting tasks | Depends on the work and data themselves |
| Typical Java object/API | `Process`, `ProcessBuilder` to manage child processes | `Thread.ofPlatform()` | `Thread.ofVirtual()` | `Runnable`, `Callable`, `Future` |

**Remember:** one JVM typically has many threads; multiple threads in the same JVM can access the same objects on the heap. Two normal processes cannot directly access the same Java heap; to communicate, they need a mechanism such as sockets, pipes, files, or explicitly configured shared memory. Process isolation does not guarantee that tasks inside a process are automatically safe from data races.

## 2. Concurrency vs. parallelism

**Concurrency** means multiple tasks make progress over an overlapping time period. They can take turns on a single CPU core. **Parallelism** means two or more tasks actually execute at the exact same instant on different cores or processing units.

For example, while task A is waiting for a network response, the CPU can process task B. This is concurrency even when only one core executes Java code at a time. Two CPU-intensive tasks running simultaneously on two cores is parallelism.

Any kind of thread needs CPU time to execute code. Virtual threads **do not create extra CPU cores** and do not make a CPU-heavy algorithm faster merely by increasing the number of threads. The main strength of virtual threads is enabling you to maintain a very large number of I/O-waiting tasks using a sequential programming style without dedicating an OS thread to each waiting task.

## 3. Processes in a Java application

When you run `java MyApp`, the operating system starts a JVM process; inside the JVM are the `main` thread and runtime service threads. Each process has its own PID, set of resources (such as file descriptors and sockets), and lifecycle. The JVM can start a child process using `ProcessBuilder`, but **a child process is different from a new thread**: it has its own address space, termination/waiting mechanism, and communication channel.

Practical examples:

- Two separate invocations of `java MyApp` are two JVM processes, even if they use the same `.class` files.
- Within one JVM, a task reading from a socket and another task performing computations can share the same cache object; synchronizing cache access is a thread-level concern.
- For one JVM to pass data to another JVM, an IPC channel or exchange protocol is required; declaring a `static` variable does not make two JVMs share that variable.

Processes are appropriate when you need isolation boundaries, permissions, and independent lifecycles. Threads are appropriate when multiple tasks belonging to **the same application** need to coordinate and share data. These are two architectural decisions at two different layers.

## 4. Platform threads: mapping to OS threads

`Thread.ofPlatform().start(runnable)` creates and starts a platform thread. A platform thread stays bound to an OS thread for its entire lifetime; the operating system is responsible for allocating CPU time. Each platform thread requires OS resources and a stack, so keeping tens of thousands of live platform threads is generally much more expensive than creating the same number of virtual threads.

**Note on states:** `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED` are `Thread.State` values observable through the API, not a guarantee of the exact moment the CPU is running the thread. `RUNNABLE` can include time spent ready to run. A thread waiting on a monitor lock, `join`, or `sleep` also does not automatically make other tasks safe.

For a small set of long-lived tasks, or tasks using native APIs with specific thread requirements, platform threads can be suitable. When a very large number of concurrent requests all wait on the network, using one platform thread per request easily hits OS thread resource limits; therefore, traditional applications often use a **pool** of platform threads with a bounded thread count and a task queue.

## 5. Virtual threads: lightweight Java threads scheduled by the JVM

A virtual thread is also a `Thread`: it has an identity, supports `start`, `join`, and `interrupt`, and can be inspected via `Thread.currentThread()` and `isVirtual()`. The difference is that a virtual thread **does not exclusively own an OS thread for its entire lifetime**.

In Java 21, the JVM mounts a virtual thread onto a carrier platform thread when it is ready to run. For many blocking I/O operations supported by the JDK, the JVM can unmount the virtual thread from its carrier while it waits, freeing the carrier to run another virtual thread. When the I/O result is ready, the virtual thread is scheduled to resume. This mechanism allows code that looks sequential—such as calling `read()` and then processing the result—to still serve many waiting connections.

Not every blocking call releases the carrier: there are differences across JDK versions, native libraries, and operation types. In **Java 21**, a virtual thread can experience **pinning** when performing a blocking operation inside a `synchronized` block/method or when executing native/foreign code; the carrier may be held during that time. Java 24 improves monitor pinning per JEP 491, though you still need to consider the specific JDK version and libraries in use. Pinning does not mean the program is always incorrect; it can reduce scalability when many waiting operations occur.

Virtual threads are particularly well suited for **I/O-bound** tasks such as waiting on network, file, or external system data. **CPU-bound** tasks still require CPU time and should have their parallelism bounded according to available processing resources.

### Example 1 — two thread kinds performing the same type of work

Create `ThreadKindsDemo.java`:

```java
import java.util.concurrent.atomic.AtomicInteger;

public class ThreadKindsDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger platformResult = new AtomicInteger();
        AtomicInteger virtualResult = new AtomicInteger();

        Thread platform = Thread.ofPlatform()
                .name("platform-demo")
                .start(() -> platformResult.set(10));

        Thread virtual = Thread.ofVirtual()
                .name("virtual-demo")
                .start(() -> virtualResult.set(20));

        platform.join();
        virtual.join();

        System.out.println("platform: value=" + platformResult.get()
                + ", virtual=" + platform.isVirtual());
        System.out.println("virtual: value=" + virtualResult.get()
                + ", virtual=" + virtual.isVirtual());
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac ThreadKindsDemo.java
java ThreadKindsDemo
```

Output:

```text
platform: value=10, virtual=false
virtual: value=20, virtual=true
```

Both threads are created and may run in any order. However, `join()` forces `main` to wait for both to finish before printing, so the order of the two output lines above is deterministic. `AtomicInteger` provides safe update/read operations; furthermore, when `join` returns normally, actions in the terminated thread have a *happens-before* relationship with actions after `join` in the waiting thread. `isVirtual()` distinguishes the thread kind; it does not indicate core count or actual parallelism.

**Important lifecycle note:** virtual threads in Java 21 are daemon threads and do not keep the JVM alive on their own. If `main` finishes with no other non-daemon threads running, the JVM can exit before virtual threads complete. Use `join`, `Future.get`, proper executor shutdown, or an appropriate lifecycle management mechanism to wait for required work.

## 6. A task is the work; a thread is where the work runs

Consider two ways to write tasks:

- `Runnable` describes work that returns no result: `() -> saveRecord()`.
- `Callable<T>` describes work that returns a result `T` or may throw an exception: `() -> calculateValue()`.

Creating a `Runnable` or `Callable` **does not create a thread and does not execute itself**. The caller can run it synchronously via `run()`, create a thread to run it, or submit it to an `ExecutorService`. `Thread.start()` initiates concurrent execution, whereas calling `runnable.run()` directly is just an ordinary method call on the current thread.

`ExecutorService` accepts tasks, decides how to execute them based on its implementation, and typically returns a `Future` to observe the outcome. A **platform thread pool** can reuse a fixed set of threads for many tasks sequentially. In contrast, `newVirtualThreadPerTaskExecutor()` creates **a new virtual thread for each task**, not a pool of reused virtual threads. The name “per task” describes the execution policy; it does not mean task and thread are the same concept.

### Example 2 — executing tasks with a virtual-thread-per-task executor

Create `TaskExecutorDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class TaskExecutorDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {

            Future<Integer> calculation = executor.submit(() -> {
                Thread.sleep(50);
                return 6 * 7;
            });
            Future<Boolean> typeCheck = executor.submit(
                    () -> Thread.currentThread().isVirtual());

            System.out.println("result=" + calculation.get());
            System.out.println("runsOnVirtualThread=" + typeCheck.get());
        }
    }
}
```

Run with JDK 21 or later:

```bash
javac TaskExecutorDemo.java
java TaskExecutorDemo
```

Output:

```text
result=42
runsOnVirtualThread=true
```

The two `submit` calls submit two independent tasks; each task runs in its own virtual thread. `Thread.sleep(50)` simulates wait time; it does not prove a performance speedup and does not guarantee the order in which the tasks actually start. `Future.get()` waits for the result (or throws an exception if the task fails). `try`-with-resources closes the executor according to the `ExecutorService` lifecycle, waiting for tasks to complete. The program prints in a fixed order because it calls `get` and prints sequentially.

**Do not overgeneralize:** `CompletableFuture.supplyAsync(...)` without an executor argument defaults to `ForkJoinPool.commonPool()` (under standard configuration); it **does not use virtual threads by default**. To run a task on virtual threads with that API, you must pass an appropriate executor.

## 7. What happens when a task waits, runs heavily, or is cancelled

### 7.1. Blocking I/O and carriers

A sequential-style network task might perform: send request → wait for response → parse result. With a platform thread, during the blocking operation, that OS thread is typically waiting and cannot execute another task on the same thread. With a virtual thread on a supported JDK and unmount-capable I/O operation, the JVM can return the carrier to the scheduler while the virtual thread waits.

This ability to utilize the carrier during wait times is what enables scaling the number of concurrent I/O tasks. If the task itself runs a continuous CPU loop, the virtual thread still occupies a carrier while executing; it is not inherently “lighter on CPU” than a platform thread.

### 7.2. Waiting for completion vs. cancelling work

- `thread.join()` waits for a thread to terminate; `future.get()` waits for a task to complete or fail.
- `future.get(timeout, unit)` only sets a time limit on **waiting for the result** on the caller's side. When a `TimeoutException` occurs, the task is not automatically cancelled.
- `future.cancel(true)` requests task cancellation and typically sends an interrupt signal to the running thread, but **does not guarantee the task stops immediately**.
- `thread.interrupt()` is a cooperative signal. Code waiting in many APIs such as `sleep`/`join` can receive an `InterruptedException`; long-running code must actively check the interrupt status and exit safely.

When catching `InterruptedException` and you cannot propagate it, the standard practice is to restore the interrupt flag via `Thread.currentThread().interrupt()` and then finish the unit of work or propagate the signal to the coordinating layer. Do not swallow the exception and continue as if no stop request occurred.

### 7.3. Lifecycle and resources outside the thread

Each task may hold sockets, transactions, connections, file descriptors, or buffers. Even though virtual threads are cheaper, **these resources do not automatically become cheaper**. If you create 100,000 virtual threads all calling a database that only supports 50 connections, the bottleneck remains the connection limit, the target system's capacity, and timeout policies.

Limit resource access with a connection pool, `Semaphore`, or appropriate backpressure mechanism. Do not “pool virtual threads” just to throttle load: limit at the actual scarce resource. Always specify timeouts, cancellation, controlled retries, and close resources in `try`-with-resources whenever possible.

## 8. Sharing data: virtual threads do not automatically solve race conditions

Threads in a single JVM normally see the same heap. Two tasks concurrently modifying a shared variable without a valid synchronization relationship can cause a **data race**, lost updates, or reads of values not guaranteed to be visible under the Java Memory Model. This applies equally to both platform threads and virtual threads.

For example, `counter++` consists of multiple steps—read, increment, write; two threads incrementing concurrently can lose an update. Replace it with `AtomicInteger.incrementAndGet()` when a simple counter suffices, or use locks, concurrent collections, and immutable/message-passing designs as required.

Useful *happens-before* relationships include the completion of `Thread.start()` before actions in the new thread, actions in a thread before a corresponding `join` returns, and the guarantees of `synchronized`, `volatile`, atomic classes, and `Future` per their API contracts. Do not equate “saw the right value in one run” with “the program is always correct”.

**ThreadLocal:** data is stored per thread, including virtual threads. Creating a very large number of virtual threads and storing heavy objects in `ThreadLocal` can still consume substantial memory and prolong resource lifetimes. Do not assume `ThreadLocal` state from a previous task will exist in the next task under `newVirtualThreadPerTaskExecutor`: each task receives a new virtual thread.

## 9. Choosing an execution unit for real-world scenarios

| Scenario | Reasonable starting choice | Rationale and conditions |
| --- | --- | --- |
| Need to run an isolated program with resource/permission boundaries | New process | OS-level boundary; must explicitly handle IPC, errors, and process reaping |
| A few long-lived background tasks or tasks tied to native OS threads | Platform thread | Suitable when thread count is bounded and native behavior requires a dedicated thread |
| High volume of independent requests, mostly waiting on I/O | Virtual thread per task | Synchronous code is easy to follow; fewer OS threads held during supported I/O waits |
| Many CPU-bound computations | Executor with concurrency bounded by CPU | Virtual threads do not increase CPU capacity; need to partition work and measure performance |
| Calling a service/DB with a fixed quota or connection pool | Task + resource access limit | A large number of virtual threads does not replace quotas, timeouts, and backpressure |
| Multiple tasks needing return values, error propagation, or controlled cancellation | `ExecutorService` + `Future` | Separates task description from scheduling and lifecycle tracking |

Do not choose based on the maximum thread count in a demo. Measure wait times, CPU, memory, connection counts, contention, latency, and throughput under realistic load. The goal is to let more **useful work** make progress safely, not to create the most threads.

## 10. Misconceptions to eliminate

1. **“One task is always one thread.”** False. A thread in a pool can run thousands of tasks over time; a single task can split itself into multiple subtasks. Only with `newVirtualThreadPerTaskExecutor` does the executor assign a new virtual thread to each task.
2. **“Virtual threads do not use OS threads.”** False. Java code in a virtual thread still runs on a carrier platform thread; the OS still schedules carriers onto the CPU.
3. **“Virtual threads make CPU-heavy problems run faster.”** There is no such guarantee. CPU-bound tasks still compete for the same CPU cores, and creating too many tasks can even add overhead.
4. **“Thread.sleep() means yielding the CPU fairly.”** `sleep` requests a minimum wait per the API semantics; it does not guarantee fairness, exact resumption timing, or execution order.
5. **“With virtual threads, you don't need locks.”** False. Both thread kinds share data and must obey the Java Memory Model.
6. **“With Future.get(timeout), the task has stopped when it times out.”** False. Timing out while waiting is not cancellation; you need separate cancel, interrupt, and cleanup policies.
7. **“More virtual threads means more DB connections.”** False. The connection pool and target system still determine useful concurrency.
8. **“All blocking operations unmount virtual threads.”** False. There are pinning/native cases and differences across JDK versions; verify in the actual runtime environment.

## 11. Self-check questions

**Scenario A:** Run `java MyApp` twice. Each invocation creates 20 virtual threads. How many Java processes are there, and do the virtual threads share `static` variables between the two runs by default?

**Answer:** Typically there are two JVM processes; each process has its own heap space. The two groups of virtual threads in the two processes do not directly share the same `static` variables.

**Scenario B:** An application has 5,000 HTTP jobs, each mostly waiting for a network response. Why might virtual threads be a better fit than 5,000 platform threads?

**Answer:** The JVM can unmount many virtual threads waiting on I/O, reusing a much smaller set of carrier OS threads to run ready virtual threads. Actual results still depend on the networking library, target system limits, sockets, memory, and runtime configuration.

**Scenario C:** Switching from platform threads to virtual threads, `counter++` on a shared variable still produces wrong results. Why?

**Answer:** The race condition comes from an unsynchronized multi-step update, not from the thread kind. You need `AtomicInteger`, synchronization, or an appropriate thread-safe data structure.

**Scenario D:** A task calls `Future.get(100, MILLISECONDS)` and times out. Is the running task guaranteed to have stopped?

**Answer:** No. The timeout only ends the caller's wait for the result; to cancel it, you must call `cancel` and design the task to respond to interruption and close resources properly.

## 12. Summary of relationships

A **Process** sets OS-level execution and resource boundaries. Inside a JVM process, a **platform thread** provides an execution thread bound to an OS thread, while a **virtual thread** provides a lightweight Java thread that the JVM mounts onto a carrier when it needs to run. A **Task** describes the work to be completed; the executor or application code decides which thread runs the task and how results are managed.

With Java 21+, the natural approach for many I/O-waiting tasks is **one virtual thread per task** combined with lifecycle management, timeouts, and resource limits. For CPU-bound tasks or specific OS/native constraints, base decisions on core count, actual cost, and measurements. Regardless of the execution unit chosen, data safety and task cancellation remain the program's design responsibilities.
