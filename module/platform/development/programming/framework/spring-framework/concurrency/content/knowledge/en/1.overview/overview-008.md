# Learning Roadmap and Essential Java Concurrency Foundations

## 1. Objectives and Place in Spring Framework Concurrency

Concurrency is the ability to manage multiple tasks whose execution lifetimes overlap; parallelism is actually running multiple tasks at the same time across multiple processing cores. A Java application can handle many requests concurrently even if not every operation runs in parallel.

Before learning `TaskExecutor`, `@Async`, `TaskScheduler`, or how Spring manages background tasks, you need to understand the problems those mechanisms solve: creating and managing threads, safely sharing state, synchronization, task cancellation, error handling, resource limits, and testing. Spring provides an abstraction/integration layer, yet the Java Memory Model rules and task lifecycles still apply.

After this lesson, learners should be able to:

- Distinguish concurrency, parallelism, asynchronous execution, non-blocking I/O, and multithreading.
- Explain race conditions, visibility, atomicity, ordering, and *happens-before* relationships.
- Choose between `synchronized`, `volatile`, atomic variables, locks, and concurrent collections based on the kind of shared state.
- Use `ExecutorService`, `Future`, `CompletableFuture`, and coordination mechanisms to organize work in a controlled way.
- Design cancellation paths via interruption, timeouts, and shutdown; avoid deadlocks, starvation, and creating too many tasks.
- Understand Java 21 virtual threads and connect Java concepts to concurrency in Spring.

**Starting point:** solid grasp of classes/objects, interfaces and lambdas, exception handling, generics, collections, try/finally, and how to compile Java programs. Examples run on Java 17+ by default, except the virtual threads section which explicitly specifies Java 21+.

## 2. The Big Picture: Which Problem Leads to Which Tool?

| Problem | Java Knowledge/Tool to Learn | When to Use |
| --- | --- | --- |
| Independent work running off the calling thread | `Thread`, `Runnable`, `Callable` | Understanding the basic execution model |
| Multiple threads reading/writing state together | Java Memory Model, `synchronized`, `volatile`, `AtomicInteger` | Ensuring correctness |
| Need to coordinate timing and results | `join`, `Future`, `CountDownLatch`, `BlockingQueue` | Avoiding reliance on `sleep` to guess timing |
| Many tasks need to be managed | `ExecutorService`, thread pools, queues, shutdown | Managing resources and lifecycle |
| Need to compose chains of asynchronous tasks | `CompletableFuture` | Transforming, combining results, handling errors |
| Many requests waiting on I/O | Virtual threads (Java 21+) and load limits | Improving serving capacity when tasks mostly wait |
| Bringing concurrency into Spring | `TaskExecutor`, `@Async`, `TaskScheduler` | Integrating the Java task model with application configuration and lifecycle |

Do not choose a tool just to "run faster." First determine whether the task is **CPU-bound** (computation) or **I/O-bound** (waiting on network, file, or database), whether data is shared, what resource limits exist, and where results/errors must be returned.

## 3. Thread Model and Execution Lifecycle

A *process* has its own resource space; in Java, multiple threads of the same JVM generally share the heap while each thread has its own call stack. Data in shared objects can be accessed concurrently. Declaring a variable inside a method does not automatically guarantee safety if its reference points to a mutable, shared object.

- `Thread` represents an execution thread; `Runnable` describes a task returning no result; `Callable<V>` describes a task returning a result or throwing an exception.
- `start()` asks the JVM to start a new thread; calling `run()` directly is just a method call on the current thread.
- `join()` waits for a thread to finish. `sleep()` only pauses the current thread and creates **no** guarantee that another thread has finished.
- Java states `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED` reflect API-level states; `RUNNABLE` does not mean the thread is definitely using the CPU at the moment of observation.
- Non-daemon threads can keep the JVM alive; daemon threads are unsuitable for work that must finish before the application stops.

Complete example `ThreadBasics.java`:

```java
public class ThreadBasics {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> System.out.println("Worker finished"));
        worker.start();
        worker.join();
        System.out.println("Main finished");
    }
}
```

```bash
javac ThreadBasics.java
java ThreadBasics
```

Output:

```text
Worker finished
Main finished
```

This ordering is guaranteed because `join()` waits for the worker to finish before the main thread prints the second line. Do not infer execution order solely from the order of `start()` calls without coordination.

## 4. Race Conditions and the Java Memory Model: Mandatory Foundations

A **race condition** occurs when the outcome depends on the interleaving order of operations across threads without proper program control. For example, `counter++` actually consists of reading the value, adding 1, and writing it back; two threads can read the same value and lose an increment.

Distinguish three properties:

1. **Atomicity:** an operation is observed as an indivisible unit. `counter++` on a shared `int` variable is not atomic.
2. **Visibility:** whether updates from one thread are seen by another thread in a timely manner.
3. **Ordering:** the compiler, CPU, and JVM may reorder operations within permitted bounds; you cannot rely on intuition about source-code order across threads.

The Java Memory Model (JMM) defines when operations have a *happens-before* relationship. Some key rules:

- Actions before `Thread.start()` in the calling thread happen-before actions in the newly started thread.
- All actions in a thread happen-before another thread returns successfully from `join()` on that thread.
- Unlocking a monitor happens-before every subsequent lock on that same monitor.
- A write to a `volatile` field happens-before every subsequent read of that same `volatile` variable.
- Actions before `CountDownLatch.countDown()` happen-before actions after another thread returns successfully from `await()`.

Without proper synchronization relationships, code with a *data race* can read stale values or exhibit unexpected behavior. Adding `sleep` does not fix memory visibility bugs.

### 4.1. Choosing a State Protection Mechanism

| Mechanism | Provides | Limitations |
| --- | --- | --- |
| `synchronized` | Mutual exclusion, visibility on monitor entry/exit, reentrant locking | Holding locks too long reduces concurrency; must avoid inconsistent lock ordering |
| `volatile` | Visibility and ordering for single-variable reads/writes; good for status flags | Does not make compound read–modify–write operations atomic |
| `AtomicInteger` / `AtomicReference` | Individual atomic operations based on CAS/variants | Does not automatically enforce invariants spanning multiple independent fields |
| `ReentrantLock` | Explicit locking, `tryLock`, interruptible lock acquisition | Must `unlock` in `finally` |
| Immutable data | Avoids mutating state after creation, easy to share | Still requires *safe publication* when publishing objects |
| Concurrent collections | Synchronization tailored to the data structure | Multi-step sequences may still need additional coordination |

A `volatile boolean running` flag is suitable for one thread to signal another thread to stop a loop, provided the loop checks the flag regularly. Conversely, `volatile int count` **does not** make `count++` safe; an atomic variable or locked region is required. For conditions involving multiple variables, protect the entire invariant with the same synchronization mechanism.

### 4.2. Safe Counting Example with AtomicInteger

```java
import java.util.concurrent.atomic.AtomicInteger;

public class AtomicCounterDemo {
    public static void main(String[] args) throws InterruptedException {
        AtomicInteger counter = new AtomicInteger();
        Runnable increment = () -> {
            for (int i = 0; i < 1_000; i++) {
                counter.incrementAndGet();
            }
        };

        Thread first = new Thread(increment);
        Thread second = new Thread(increment);
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println(counter.get());
    }
}
```

```bash
javac AtomicCounterDemo.java
java AtomicCounterDemo
```

Output:

```text
2000
```

`incrementAndGet()` performs atomic updates; the two `join()` calls ensure the program waits for both threads before reading. If replaced with a shared `int` incremented via `++`, the final value can be less than 2000, even if it occasionally happens to equal 2000; that is not a valid test.

### 4.3. Signaling and Visibility Guarantee Example

```java
import java.util.concurrent.CountDownLatch;

public class LatchDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);
        int[] shared = {0};

        Thread reader = new Thread(() -> {
            try {
                ready.await();
                System.out.println(shared[0]);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
        reader.start();

        shared[0] = 42;
        ready.countDown();
        reader.join();
    }
}
```

```bash
javac LatchDemo.java
java LatchDemo
```

Output when there is no external interrupt request:

```text
42
```

`countDown()` releases the thread calling `await()` and establishes a happens-before relationship for the prior write. `join()` makes the main thread wait until printing finishes. No extra `volatile` is needed on `shared[0]` under this exact synchronization sequence.

## 5. Coordinating Between Tasks

When multiple tasks depend on one another, express the dependency with explicit primitives:

- `CountDownLatch(n)`: one or more threads wait for `n` events; the latch is single-use and does not reset.
- `CyclicBarrier`: multiple threads meet at a cyclic synchronization point; useful when phases genuinely need to advance together.
- `Phaser`: coordinates multiple phases with a more flexible number of participants.
- `Semaphore`: limits the number of concurrent tasks using a resource; acquire/release must balance, even when exceptions occur.
- `BlockingQueue`: producer–consumer channel with blocking on take/put; bounded-capacity queues help apply *backpressure*.
- `Condition` paired with `Lock`: waits for a state condition; check the condition in a `while` loop, not a standalone `if`, because spurious wakeups or unmet conditions can occur.

Only use `wait()/notify()/notifyAll()` after understanding monitors, loop conditions, and lock-holding requirements; in most applications, prefer higher-level tools from `java.util.concurrent`.

Rule of thumb: share as little data as possible. Immutable values, message passing through queues, and isolating state per task are usually simpler than a web of locks.

## 6. ExecutorService, Thread Pools, and Future

Creating `new Thread(...)` for every request easily leaves lifecycle and resources uncontrolled. `Executor` is a job submission mechanism; `ExecutorService` adds task submission with results and shutdown management; `Future<T>` represents a result that may not be ready yet.

Minimum workflow:

1. Choose an executor fitting the workload characteristics and resource limits.
2. Submit `Runnable` or `Callable<T>` via `execute`/`submit`.
3. Obtain the result via `Future.get()` or design an asynchronous chain; `get()` can block and throw `ExecutionException`.
4. Set a timeout when waiting cannot be unbounded; handle `InterruptedException`.
5. `shutdown()` stops accepting new tasks while letting already-submitted tasks finish; `shutdownNow()` attempts to interrupt running tasks and returns the list of unstarted ones, with **no** guarantee of forced termination.
6. If needed, use `awaitTermination` to wait for the executor to finish within a deadline.

Complete example `ExecutorDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class ExecutorDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<Integer> answer = pool.submit(() -> 40 + 2);
            System.out.println(answer.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ExecutorDemo.java
java ExecutorDemo
```

Output:

```text
42
```

Using `finally` ensures `shutdown()` is called even if `get()` fails. In long-lived applications, the executor usually belongs to a managed component's lifecycle rather than creating a new pool per call.

### 6.1. Understanding Pools and Load Limits

A pool with few threads is suited to bounding concurrent CPU computation; a larger pool serving blocking I/O tasks can improve CPU utilization but consumes memory and increases context switching. The right count depends on hardware specs, wait times, downstream resources, and SLAs; there is no "single best number for every application."

Four metrics to observe: active task count, queue length, queue wait time, and rejection/timeout rate. An unbounded queue can hide overload behind ever-growing latency and memory usage. With `ThreadPoolExecutor`, understand `corePoolSize`, `maximumPoolSize`, `keepAliveTime`, the queue, and `RejectedExecutionHandler`; their interaction matters more than any single number alone.

Avoid pool-induced deadlocks from internal dependencies: if all workers are blocked in `Future.get()` waiting for other tasks that must also run on the same full pool, the system can hang forever. Review dependency structures, separate work types, or use appropriate non-blocking composition.

## 7. Cancellation, Interruption, Timeouts, and Error Handling

Interruption in Java is a **cooperative signal**. `Thread.interrupt()` sets the interrupt status; many blocking operations such as `sleep`, `wait`, and `BlockingQueue.take` throw `InterruptedException` and typically clear the interrupt flag when throwing. Task code must have a response policy: exit, clean up resources, or propagate the signal up to the managing layer.

Illustrative snippet **inside a task-executing method**:

```java
try {
    // Simulates an interruptible waiting operation.
    Thread.sleep(1_000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // preserve signal for caller layer to handle
    return; // only valid if inside a void-returning method
}
```

The snippet above is a fragment, not a standalone Java class. With a `Callable` allowed to throw `InterruptedException`, you can let the exception propagate; do not catch it and silently keep running as if no cancellation was requested.

- `Future.cancel(true)` requests interruption if the task is running; it does not force CPU-bound code or non-interruptible libraries to stop immediately.
- `Future.get(timeout, unit)` limits how long *the caller waits*, without automatically canceling the running task; consider calling `cancel(true)` per application policy.
- Task-level timeouts differ from socket/database/HTTP client timeouts. Bounds are needed at the I/O source to avoid holding resources too long.
- Exceptions in `submit(Callable/Runnable)` are captured in the `Future` and surfaced via `get()`; ignoring the `Future` can cause errors to go unnoticed.
- Do not use `Thread.stop()` for forced termination; ensure cleanup with `finally` or `try-with-resources`.

## 8. CompletableFuture: Building Asynchronous Work Chains

`CompletableFuture<T>` both represents the final result and supports dependent stages. Points to learn in order:

- `supplyAsync` creates work returning a result; `runAsync` returns no data. By default, async methods without an explicit executor typically use `ForkJoinPool.commonPool()`.
- `thenApply` transforms the value; `thenCompose` is used when the next step also returns a `CompletionStage` to avoid nested `Future<Future<T>>`; `thenCombine` combines two independent results.
- `thenApplyAsync`/`thenComposeAsync` allow specifying an executor; methods without the `Async` suffix do not inherently run on a separate thread and may run on the thread completing the prior stage.
- `exceptionally` produces a fallback value after an error; `handle` handles both success and failure; `whenComplete` observes the outcome and performs side effects without changing the result type.
- Both `join()` and `get()` can block when incomplete; `join()` wraps errors as unchecked (`CompletionException`), whereas `get()` uses checked exceptions.
- Once you have a chain of stages, prefer composing the pipeline instead of calling `join()` between every step, especially in environments with limited workers.

Complete example `CompletableFutureDemo.java`:

```java
import java.util.concurrent.CompletableFuture;

public class CompletableFutureDemo {
    public static void main(String[] args) {
        CompletableFuture<String> result =
                CompletableFuture.supplyAsync(() -> "java")
                        .thenApply(String::toUpperCase);

        System.out.println(result.join());
    }
}
```

```bash
javac CompletableFutureDemo.java
java CompletableFutureDemo
```

Output:

```text
JAVA
```

Do not infer thread names or stage execution order from this output. In applications with blocking I/O, consider a dedicated bounded executor with a clear lifecycle instead of the default common pool.

## 9. Concurrent Collections, Locks, and Thread-Local State

### 9.1. Shared Data Structures

- `ConcurrentHashMap` supports high concurrent access and atomic per-key operations such as `compute`, `merge`, and `putIfAbsent`. The pattern `if (!map.containsKey(k)) map.put(k, v)` consists of two separate operations and is not automatically atomic.
- `CopyOnWriteArrayList` suits read-heavy, very-rare-write scenarios; each mutation incurs an array copy cost.
- `BlockingQueue` coordinates producers and consumers; bounded-capacity queues are usually safer than unbounded queues under heavy load.
- `ConcurrentLinkedQueue` is a non-blocking thread-safe queue; it does not provide capacity limits or backpressure on its own.
- A thread-safe collection by itself does not turn a multi-statement workflow into a transaction. Business invariants must still be defined.

### 9.2. When Do You Need a Lock?

`ReentrantLock` allows timed waits or interruptible lock acquisition, but must always be unlocked properly:

```java
lock.lock();
try {
    // Access protected shared state.
} finally {
    lock.unlock();
}
```

This is an illustrative fragment assuming `lock` is an already-initialized and shared `ReentrantLock`. `ReadWriteLock`/`StampedLock` help in some read-heavy, write-light patterns at the cost of complexity; use them only after measuring and verifying correctness.

### 9.3. ThreadLocal and Thread Boundaries

`ThreadLocal<T>` stores values per thread and **does not** automatically transfer across different executor workers. In a pool, workers are reused, so leftover request data after a task finishes can leak or mix contexts. When setting a ThreadLocal manually, you typically need `remove()` in `finally`. Do not use ThreadLocal to replace explicit parameter passing.

In Spring, transaction context, logging context (MDC), and certain security/request contexts are often bound to a thread. Offloading work via `@Async` or an executor can lose context, so supported context-propagation mechanisms with lifecycle control must be used; do not assume "same request" means "same thread."

## 10. Java 21 Virtual Threads: Addition to the Roadmap

Java 21 provides virtual threads as a stable feature. A virtual thread still has Java `Thread` semantics, yet many virtual threads can be managed by the JVM over a small number of carrier platform threads. They are especially useful for tasks spending significant time **waiting on blocking I/O**, letting you write straightforward sequential code while still achieving high concurrency.

Complete example, **runs on Java 21+ only**, `VirtualThreadDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class VirtualThreadDemo {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<String> result = executor.submit(() -> "hello virtual");
            System.out.println(result.get());
        }
    }
}
```

```bash
javac VirtualThreadDemo.java
java VirtualThreadDemo
```

Output:

```text
hello virtual
```

Virtual threads **do not** speed up CPU computations beyond what available cores can handle, do not make data structures automatically thread-safe, and do not eliminate connection pool, database, or external API limits. Do not "pool virtual threads to limit thread count"; when concurrency toward an external resource must be capped, use a semaphore, connection pool, or backpressure mechanism. On Java 21, certain blocking situations inside a `synchronized` monitor can also pin the carrier thread (pinning); measure on the exact JDK version deployed. Understand platform threads and traditional executors before choosing virtual threads.

## 11. Common Concurrency Bugs and How to Spot Them

| Symptom | Common Cause | Remediation Direction |
| --- | --- | --- |
| Counter or final sum randomly too low | Read–modify–write race | Atomic operations or locks protecting the invariant |
| Thread seems not to see a stop flag | Missing visibility guarantee | `volatile`, locks, or synchronization primitives |
| Application hangs despite low CPU | Deadlock, circular waits, or tasks waiting on a full pool | Thread dumps, identify lock/`Future.get` cycles, restructure dependencies |
| Latency and memory grow with load | Unbounded queue, no backpressure | Bounded queues, timeouts, rejection policies |
| Exceptions occur but caller never sees them | Ignored `Future` or missing async error handling | Observe completion/errors and contextual logging |
| Shutdown drags on, tasks do not stop | Unhandled interruption or I/O without timeouts | Cooperative cancellation, timeouts at the source |
| Wrong transaction/log context under async | Thread-local context not propagated automatically | Proper context propagation, clear transaction boundaries |
| Flaky tests | Relying on `sleep` to assume order, or data races | Latches/barriers, futures, explicit timeouts, stress tests |

Three distinct concepts: **deadlock** is a waiting cycle where none of the parties can proceed; **starvation** is a task not receiving enough resources/opportunities to run; **livelock** is parties continuously reacting without making progress. All three require analyzing system progress, not simply "adding threads."

## 12. Testing, Measurement, and Operations

Concurrency must prove both **correctness** and **performance**:

1. Write concrete invariants: for example, "1000 successful requests increment the counter by exactly 1000," "each job is processed only once," "no task runs after shutdown."
2. Create controlled starting points using `CountDownLatch`/barriers; avoid using `Thread.sleep` as a synchronization mechanism.
3. Use timeouts on tests and waiting operations to ensure failing tests terminate with diagnostics rather than hanging forever.
4. Run multiple iterations with varying load and execution schedules to increase the chance of exposing races; a "green" test run is not absolute proof that no race exists.
5. Inspect thread dumps to view stacks, thread states, and held/waited monitors; use Java Flight Recorder (JFR) and metrics to measure blocking, lock contention, queue depth, active task count, timeouts, and latency.
6. Distinguish throughput (tasks completed per unit time), latency (per-task delay), and resource consumption; higher throughput does not automatically mean better latency.
7. Test failure scenarios: tasks throwing exceptions, client timeouts, executor rejections, mid-flight cancellation, shutdown with pending tasks, and slow downstream systems.

Measured data is only meaningful within the context of the workload, CPU, JVM, pool configuration, and dependent services. Do not optimize by guesswork.

## 13. Staged Learning Roadmap and Completion Criteria

| Stage | Topics to Study | Practice Exercises to Complete | Exit Criteria |
| --- | --- | --- | --- |
| **1. Execution model** | Concurrency vs. parallelism; `Thread`, `Runnable`, `Callable`, `start/join`, lifecycle | Run two tasks and explain output order with and without `join` | Explain why `run()` does not start a new thread |
| **2. Memory correctness** | Races, atomicity, visibility, ordering, JMM, happens-before | Reproduce a counter race; fix with `AtomicInteger` and `synchronized` | Prove why `volatile count++` is still wrong |
| **3. Coordination and cancellation** | Latches, queues, semaphores, interrupts, timeouts | Producer–consumer with a bounded queue; shut down safely on request | Do not use `sleep` as completion signal; do not swallow interrupts |
| **4. Execution management** | Executors, pool sizing, queues, Future, shutdown/rejection | Process multiple jobs with bounds and collect results/errors | No thread leaks; overload is controlled |
| **5. Async composition** | `CompletableFuture`, stages, combining/errors, suitable executors | Run two simulated calls in parallel, combine results, provide fallback | Distinguish non-blocking composition from blocking `join` |
| **6. Additional tools** | Concurrent collections, locks, ThreadLocal, Java 21 virtual threads | Compare state-sharing design vs. message passing; measure waiting I/O tasks | State trade-offs and downstream limits |
| **7. Transition to Spring** | `TaskExecutor`, `@Async`, `TaskScheduler`, lifecycle/context | A background service with clear logs, timeouts, error handling, and tests | Know how to pick an executor and understand context/transactions across thread switches |

This is a knowledge-dependency order, not a fixed time commitment. If you are starting out, prioritize mastering stages 1–4 before moving to Spring abstractions. Experienced developers can demonstrate competence through the exercises and skip areas they already master.

### Suggested Capstone Exercise

Build a Java program that processes a list of 100 simulated "jobs," with at most 5 jobs active simultaneously; each job has an ID and either a result or an error. The program must:

- Never spawn threads arbitrarily; use an executor with a clear lifecycle and explicit concurrency limit.
- Collect all successful results, accurately tally errors, and leave no unfinished tasks forgotten.
- Support timeouts/cooperative cancellation when exceeding a deadline; shut down cleanly after finishing.
- Use thread-safe data/primitives in the right places; verify invariants across repeated test runs.
- Measure total elapsed time, maximum concurrent jobs, and explain what happens when the job count scales 10x.

A solid solution can choose a bounded pool on Java 17+, or Java 21's virtual-thread-per-task executor combined with a semaphore when I/O is the bottleneck. What matters is explaining resource limits, cancellation behavior, and correctness—not picking the "newest" API.

## 14. Mapping Java Knowledge to Spring Framework Concurrency

Once the Java foundation is solid, learners transition to Spring with corresponding questions:

| Java Concurrency | Corresponding Question in Spring |
| --- | --- |
| `Executor` / `ExecutorService` | Which `TaskExecutor` runs the task and who manages its lifecycle/pool? |
| `Future` / `CompletableFuture` | How does an `@Async` service return results/errors to the caller? |
| Thread boundary | Is the `@Async` proxy actually invoked through a Spring bean? Does self-invocation bypass advice? |
| `ScheduledExecutorService` | How do `TaskScheduler` / `@Scheduled` handle scheduling, overlap, and shutdown? |
| Interrupts, timeouts, rejections | Under overload or cancellation, what are the application's error/limit policies and observability? |
| `ThreadLocal` and transactions | How are security/logging/transaction contexts handled across thread boundaries? |
| Virtual threads | What support configs do the JDK and Spring/Boot versions have, and can downstream handle higher concurrency? |

Important note: standard `@Async` calls operate via a Spring proxy; calling an async method from another method on the same object (*self-invocation*) can bypass the proxy mechanism. A thread-bound transaction does not automatically follow into an async thread; transaction boundaries and context must be redefined before implementation. Deeper Spring sections address declaring executors, enabling async, configuring schedulers, exception handlers, and operational observability; this Java lesson provides the foundation for understanding those decisions.

## 15. Self-Assessment Checklist Before Studying Spring Concurrency

- [ ] I can distinguish many tasks waiting from many tasks using the CPU in parallel.
- [ ] I can explain `start`, `run`, `join`, `sleep`, and the meaning of thread states.
- [ ] I can point out a race/visibility issue in an example and describe the happens-before relationship that fixes it.
- [ ] I understand when to use `volatile`, atomic types, locks, and concurrent collections.
- [ ] I can write a producer–consumer or task pipeline with proper coordination, without relying on `sleep`.
- [ ] I use executors with clear shutdown, timeouts, results, and error handling.
- [ ] I know how to handle `InterruptedException` and do not assume `cancel(true)` guarantees stopping a task.
- [ ] I can compose multiple `CompletableFuture` instances and distinguish asynchronous tasks from non-blocking operations.
- [ ] I can spot unbounded queues, deadlocks, thread starvation, and ThreadLocal bugs.
- [ ] I can explain when virtual threads are useful and what their limits are.
- [ ] I can pinpoint where Spring switches threads, where transactions/contexts can be affected, and how to test them.

**Completion standard:** write a small concurrency application on your own, prove the correctness of shared data, control errors/cancellation/resources, and explain your thread or executor choices. Spring's concurrency features then become a way of integrating well-understood principles into the application lifecycle.
