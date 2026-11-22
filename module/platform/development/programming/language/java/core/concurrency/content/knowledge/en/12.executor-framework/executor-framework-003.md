# Fixed, Cached, and Single-Thread Executors in Java

## 1. Objectives and Scope

After this lesson, you will be able to:

- Distinguish the three factory methods **Executors.newFixedThreadPool(n)**, **Executors.newCachedThreadPool()**, and **Executors.newSingleThreadExecutor()** by worker count, thread creation/reuse mechanism, queue type, sequentiality, and resource limits.
- Understand the relationships among **Executor**, **ExecutorService**, **ThreadPoolExecutor**, **Runnable**, **Callable**, and **Future**.
- Explain why a **fixed pool does not have a bounded queue by default**, why a **cached pool does not have a practical user-specified thread limit**, and why a **single-thread executor does not mean the exact same Thread object lives forever**.
- Choose an executor for independent work, CPU-bound work, blocking I/O, pipelines requiring sequential execution, or resources needing fixed concurrency; avoid confusing "at most N workers" with "at most N accepted tasks".
- Use **submit()**, **execute()**, **Future.get()**, **shutdown()**, **shutdownNow()**, **awaitTermination()**, and handle errors, cancellation, timeouts, and interrupts according to their contracts.
- Create a **ThreadPoolExecutor with a bounded queue and rejection policy** when load control is needed instead of using the unbounded default factories.
- Run Java 17+ examples with deterministic stdout, and know how to verify concurrency properties without relying on Thread.sleep() or random log ordering.

The scope is **general Java concurrency in JDK 17+**, without covering Spring-specific executor configuration, lifecycle, or annotations. Examples use Java 17 platform threads. Virtual thread APIs introduced in newer JDK versions are not one of the three factories compared here.

## 2. First: What Is an Executor?

Instead of creating a separate Thread for every unit of work, an application can **submit tasks** to an executor that manages execution.

~~~java
// Illustrative snippet, not a standalone program:
ExecutorService pool = Executors.newFixedThreadPool(2);
try {
    Future<Integer> result = pool.submit(() -> 6 * 7);
    System.out.println(result.get());
} finally {
    pool.shutdown();
}
~~~

In a real Java file, you need to import the types in `java.util.concurrent` and handle/declare the checked exceptions from `get()`. Meaning of each component:

- **Runnable**: a task that does not return a result via its `run()` method, though it may have side effects.
- **Callable<T>**: a task that returns `T` or throws an exception from `call()`.
- **Executor.execute(Runnable)**: requests the executor to execute a `Runnable`.
- **ExecutorService**: adds `submit()`, `Future`, `shutdown`, `invokeAll`, `invokeAny`, and lifecycle control.
- **Future<T>**: represents the result/cancellation/completion of a task, with a `get()` method to wait for it.
- **ThreadPoolExecutor**: an executor implementation that manages platform worker threads, a queue, and task acceptance/rejection policies.

**Executor** decouples **task submission** from **how tasks are run**. Using an executor does not automatically make tasks thread-safe: if two tasks modify the same mutable HashMap without synchronization, a data race can still occur.

### Tasks, Workers, and the Queue Are Three Distinct Quantities

~~~text
Producer calls submit(task)
           |
           v
     ExecutorService
        |        |
        |        +-- Work queue: waiting tasks
        |
        +-- Worker threads: running tasks
                  |
                  +-- Future returns result/error/cancellation
~~~

An **accepted task** is not necessarily **running immediately**: it may still be waiting in the queue. A **thread pool with 4 workers** does not mean the queue only accepts 4 tasks. If tasks arrive faster than they are processed, the queue or the number of workers can grow depending on the factory.

## 3. Comparison Table of the Three Executor Types

| Criterion | newFixedThreadPool(n) | newCachedThreadPool() | newSingleThreadExecutor() |
| --- | --- | --- | --- |
| Concurrent task-executing threads | At most **n** | Can grow on demand; very large internal maximum limit | **1** |
| Persistent pool size | Creates workers as needed up to n; core threads do not expire by default | Idle threads can be reclaimed after an idle timeout | One worker as needed; can replace a dead worker |
| Default queue | **Practically unbounded LinkedBlockingQueue** | **SynchronousQueue**, direct handoff, does not hold a normal waiting backlog | **Practically unbounded LinkedBlockingQueue** |
| When a task arrives and all workers are busy | Placed in the queue | Typically creates a new worker (if below limit and resources allow) | Placed in the queue, does not run in parallel |
| Idle threads reused | Yes | Yes; defining cached behavior | Yes; worker is replaced if it dies |
| Preserves task execution order | Does not guarantee completion in submission order | No guarantee | Tasks are executed sequentially in queue insertion order |
| Can cause issues under unbounded load | Queue growth / memory | Thread growth / memory / thread exhaustion | Queue growth / latency |
| Typical purpose | Limit concurrency of a group of tasks | Many short, bursty tasks with external load control | Serialize a stream of work/state |

**Note on "unbounded":** Java does not promise infinite memory. By default, fixed and single pools use queues with a very large capacity (practically unbounded), so overload can exhaust the heap before hitting the element count limit. A cached pool has a very large maximum worker threshold, but the OS/JVM can run out of thread-creation resources much earlier. Therefore, "practically unbounded" is a **risk**, not a promise of infinite scalability.

## 4. Fixed Thread Pool: Bounded Workers, Unbounded Backlog by Default

Creating the pool:

~~~java
// Illustrative snippet; requires importing java.util.concurrent.Executors.
ExecutorService pool = Executors.newFixedThreadPool(4);
~~~

Core characteristics of **newFixedThreadPool(nThreads)**:

1. When needed, the executor uses at most **nThreads** workers to process tasks.
2. Tasks arriving when all workers are busy are placed in the queue instead of creating an (n+1)th thread.
3. Idle workers are reused for subsequent tasks.
4. If a worker terminates due to an error before shutdown, the executor can create a replacement worker to continue serving tasks.
5. By default, platform worker threads in the pool **do not expire due to idleness** like a cached pool while the pool is still running.
6. The factory uses a queue without a useful bound for creating **default backpressure**; the number of waiting tasks can grow until it impacts memory/latency.

**What is fixed is the maximum concurrency level**, not the total number of submitted tasks, completion time, or an immutable thread count under all circumstances.

### When to Choose Fixed?

- Tasks are independent and you want to **cap the number of concurrently running tasks**, such as data-processing computations.
- Submission rate can be throttled or the workload is already bounded externally.
- You need one pool to serve many small/medium tasks, reducing the cost of creating a new Thread each time.
- You have a shutdown and error-handling plan.

**Do not assume this factory solves overload by default.** If a producer submits 100,000 tasks while 4 workers only process a few hundred tasks/second, the backlog accumulates and tail latency increases. An executor with bounded workers but an unbounded queue **does not bound the amount of accepted work**.

### Example 1: A Fixed Pool Runs at Most Two Tasks Concurrently

We use a CountDownLatch to force the first two tasks to hold their workers at a logical point, then verify that exactly two tasks are active. There is no need to use `sleep` to "get lucky" and catch concurrency.

File **FixedPoolDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class FixedPoolDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        CountDownLatch twoStarted = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        Callable<Integer> task = () -> {
            int now = active.incrementAndGet();
            peak.accumulateAndGet(now, Math::max);
            twoStarted.countDown();
            try {
                release.await();
                return 1;
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 0; i < 4; i++) {
                futures.add(pool.submit(task));
            }

            twoStarted.await();
            System.out.println("first wave active = " + active.get());
            release.countDown();

            int sum = 0;
            for (Future<Integer> f : futures) {
                sum += f.get();
            }
            System.out.println("completed = " + sum);
            System.out.println("peak <= 2 = " + (peak.get() <= 2));
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Run commands:

~~~bash
javac -encoding UTF-8 FixedPoolDemo.java
java FixedPoolDemo
~~~

Stdout under normal execution without external interrupts:

~~~text
first wave active = 2
completed = 4
peak <= 2 = true
~~~

**Explanation:**

- Two workers enter the task, increment `active`, and wait on `release`. Because the pool has at most 2 workers, the remaining two tasks must wait in the queue.
- When `main` sees the `twoStarted` latch reach 0, both initial tasks are still waiting on `release`, so `active` equals 2.
- After `release`, all four tasks complete on their own schedules, each returning 1, so the sum is 4.
- `peak` does not exceed 2 even though 4 tasks were submitted.
- `finally` releases the latch in case the wait path hits an exception and requests the pool to stop. In production code, cooperative `shutdown` and waiting for termination according to policy is usually better than unconditional `shutdownNow`.

**Do not infer** that a fixed pool always keeps two tasks active. If the workload does not have enough tasks or the JVM has not created the workers yet, the number of running tasks can be fewer than n. The example above deliberately uses latches to observe two workers running simultaneously.

## 5. Cached Thread Pool: Reusing Idle Workers, Creating Workers When No One Can Receive

~~~java
// Illustrative snippet, not a standalone program:
ExecutorService pool = Executors.newCachedThreadPool();
~~~

The common cached pool pattern uses these ThreadPoolExecutor characteristics:

- **Core pool size = 0**.
- **Maximum pool size** is very large (configured as `Integer.MAX_VALUE` in the JDK factory).
- **SynchronousQueue**: a **direct handoff** queue; it does not accumulate a list of waiting tasks the way `LinkedBlockingQueue` does.
- **Default 60-second keep-alive**: idle workers can be reclaimed if they no longer receive work.
- An incoming task is handed to a suitable idle worker; if no worker is ready to receive it, the executor can create a new worker.

A cached pool **does not bound concurrency to a small fixed number**. It is suitable when tasks are short, bursts are controllably bounded, and newly created threads do not threaten system resources.

### Risk with Long-Running Blocking I/O

Suppose there are 2,000 requests, and each task blocks for a long time waiting on an external service. If no worker is idle at the moment a task is submitted, a cached pool may attempt to create very many threads. Each platform thread consumes memory, stack space, and scheduling resources. The system can suffer **thread exhaustion**, increased context switching, reduced throughput, or thread-creation failures.

`SynchronousQueue` **does not automatically provide backpressure** at a desired business limit. If you need to cap the maximum number of active requests, use a `Semaphore`, a bounded executor, or an appropriately bounded queue, and define an overload policy.

### Example 2: Cached Pool Creates Enough Workers When Tasks Wait Together

File **CachedPoolDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.atomic.AtomicInteger;

public class CachedPoolDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newCachedThreadPool();
        CountDownLatch threeStarted = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();

        Callable<Integer> task = () -> {
            active.incrementAndGet();
            threeStarted.countDown();
            try {
                release.await();
                return 1;
            } finally {
                active.decrementAndGet();
            }
        };

        try {
            List<Future<Integer>> futures = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                futures.add(pool.submit(task));
            }

            threeStarted.await();
            System.out.println("concurrent active = " + active.get());

            release.countDown();

            int sum = 0;
            for (Future<Integer> f : futures) {
                sum += f.get();
            }
            System.out.println("completed = " + sum);
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CachedPoolDemo.java
java CachedPoolDemo
~~~

Stdout:

~~~text
concurrent active = 3
completed = 3
~~~

All three tasks wait together on `release`; there is no idle worker to receive the second and third tasks, so the cached pool can expand enough for all three tasks to start. Using latches makes the observed result deterministic in the example. **This does not mean a cached pool always creates a new thread for every task**: after a task finishes, its worker can be reused for another task; when idle for too long, a worker can be evicted.

If the design only allows **2 concurrent requests**, a cached pool does not enforce that limit by itself. You need additional control (such as a `Semaphore`) or to choose an executor with bounded workers and an appropriate backlog policy.

## 6. Single-Thread Executor: One Task Running at a Time

~~~java
// Illustrative snippet:
ExecutorService pool = Executors.newSingleThreadExecutor();
~~~

**newSingleThreadExecutor()** has this contract:

1. Only **one worker actively executes a task** at a time.
2. Tasks are **executed sequentially**; no two tasks in the same executor run overlapping each other.
3. Tasks enter the queue to wait their turn. With the default factory, the queue is **practically unbounded**.
4. If the worker fails and terminates before shutdown, the executor creates a replacement worker as needed; **you should not rely on the same Thread object living forever**.
5. The returned executor is a wrapper that does not expose a simple public way to resize the pool to multiple workers, unlike creating a `ThreadPoolExecutor` with core/max equal to 1 directly.
6. When multiple threads submit concurrently, the exact order among concurrent calls is determined by submission timing; **there is no natural business ordering** unless the application defines one.

A single-thread executor is a straightforward way to build a **single-owner model updating shared mutable state**. However, other threads must not directly mutate that state at the same time, otherwise confinement is broken.

### Example 3: Processing Three Commands Sequentially

File **SingleThreadPoolDemo.java**:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class SingleThreadPoolDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        StringBuilder state = new StringBuilder();

        try {
            pool.submit(() -> state.append("A"));
            pool.submit(() -> state.append("B"));
            pool.submit(() -> state.append("C"));

            Future<String> result = pool.submit(state::toString);
            System.out.println("state = " + result.get());
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 SingleThreadPoolDemo.java
java SingleThreadPoolDemo
~~~

Stdout:

~~~text
state = ABC
~~~

**Why is it safe to use StringBuilder?** The tasks mutating `StringBuilder` and the snapshot task all run sequentially on one executor. `main` does **not** read or modify `StringBuilder` directly while the worker is processing; `main` only receives the `String` via `Future.get()`. In this example's model, no two threads access the mutable state simultaneously.

**Note:** Do not infer that "using an executor named single" forces every call on an object to go through the executor. If another thread directly calls `state.append("X")` while the worker is processing, a race still occurs. And if tasks have external side effects, sequential execution inside one JVM does not automatically provide transactions or exactly-once semantics.

### Do Not Treat a ThreadLocal as Immutable Business State Bound to the Worker

A single-thread executor **usually reuses one thread**, but it can replace the worker if the previous thread dies. **ThreadLocal** is attached to a specific thread, not to the executor. Thus if the worker is replaced, `ThreadLocal` values can disappear; when a worker is reused, old task context can remain if `remove()` is not called. Business data should live in an owner object with a clear lifecycle rather than relying on `ThreadLocal` as long-term storage.

## 7. Selection Guide by Need and Task Type

| Scenario | Starting Choice | Additional Controls Needed |
| --- | --- | --- |
| Independent computation, want at most N active tasks | Fixed pool | Size according to CPU/workload, backlog, overload |
| Short tasks, bursty arrivals, externally bounded concurrency | Cached pool may fit | Practical max threads, blocking duration, OS resources |
| Sequential commands on the same mutable state | Single-thread executor | Queue growth, head-of-line blocking, task failure |
| Millions of long-waiting I/O requests | Do not default to a cached platform-thread pool | Bounded resource model, backpressure, suitable JDK/platform model |
| Request handling needing timeouts and bounded backlog | Bounded `ThreadPoolExecutor` | Queue capacity, rejection, cancellation, shutdown |
| Want tasks to complete in submission order | Single-thread executor or result-ordering protocol | Submission order across multiple producers, slow/failed tasks |
| Want ordered output while still running in parallel | Fixed/cached + store `Future` by index and combine properly | Completion order differs from submission order |
| A task submits another task and waits on its `Future` on the same worker | Avoid circular dependency patterns | Thread-starvation deadlock |

**Do not choose based solely on thread count.** Consider task execution time, blocking time, submission rate, RAM, queue growth risk, and latency targets. For CPU-bound tasks, a worker count close to the effective CPU count can be an initial benchmark starting point, but it is not a fixed formula for every workload.

## 8. What Happens When Submission Exceeds Service Capacity

Suppose an application receives 1,000 tasks per second while the pool can only process 100 tasks/second. Without backpressure, the backlog grows by roughly 900 tasks/second for as long as that load persists.

### Fixed and Single: Queue Grows

~~~text
Incoming -> [Worker 1][Worker 2] + [Queue: task task task task ...]
                                          |
                                      backlog grows
~~~

If the queue is not bounded at an appropriate business limit, latency can grow very large or memory can be exhausted. **Having bounded workers** is different from **having bounded waiting tasks**.

### Cached: Workers Grow

~~~text
Incoming -> [Worker 1][Worker 2][Worker 3][Worker 4] ...
                each worker blocks for a long time
                -> number of platform threads grows
~~~

A cached pool emphasizes worker reuse and rapid expansion when no worker is idle; under uncontrolled blocking load, it can exhaust thread-creation resources.

### Single: Head-of-Line Blocking

A slow first task or one waiting on I/O forces all subsequent tasks to **wait their turn**. If the first task gets stuck indefinitely, the queue can accumulate without any trailing work making progress. That is the trade-off of the sequential model.

**Backpressure** means the system actively limits the amount of unprocessed work so producers must wait, are rejected in a controlled way, or apply a permitted data-loss policy per specification. The defaults of the three factories are not a general-purpose backpressure solution.

## 9. Configuring a ThreadPoolExecutor with a Bounded Queue

When you need to bound both the number of workers and the queue simultaneously, you can construct a `ThreadPoolExecutor` explicitly.

File **BoundedExecutorDemo.java**:

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1,
                0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy()
        );

        CountDownLatch workerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> first = pool.submit(() -> {
                workerStarted.countDown();
                release.await();
                return 1;
            });

            workerStarted.await();   // Worker is running task 1.
            Future<Integer> second = pool.submit(() -> 2); // Queue has 1 slot.

            boolean rejected = false;
            try {
                pool.submit(() -> 3); // Worker busy, queue full.
            } catch (RejectedExecutionException ex) {
                rejected = true;
            }

            System.out.println("rejected = " + rejected);
            release.countDown();

            System.out.println("sum = " + (first.get() + second.get()));
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 BoundedExecutorDemo.java
java BoundedExecutorDemo
~~~

Stdout:

~~~text
rejected = true
sum = 3
~~~

**Exact explanation:**

1. `core=max=1`, so the pool has **one worker**.
2. `ArrayBlockingQueue` with `capacity=1` holds only **one waiting task**.
3. Task 1 has signaled `started` and is waiting on `release`, so task 2 sits in the queue.
4. Task 3 cannot run immediately and the queue is full; `AbortPolicy` throws `RejectedExecutionException` immediately on `submit`.
5. `main` releases task 1 and retrieves the results of the two accepted Futures: `1 + 2 = 3`.
6. `finally` ensures the latch is released even on error and requests the pool to stop.

This example illustrates **explicit bounds**, not a recommendation to always drop tasks when a queue is full. You must define the real response when rejection occurs: bounded retries, returning busy, throttling the producer, or offloading work to durable storage.

### Rejection Policies and Their Meanings

| Handler | Primary Behavior | Risk |
| --- | --- | --- |
| **AbortPolicy** | Throws `RejectedExecutionException` | Caller must handle it; suitable when work must not be silently lost |
| **CallerRunsPolicy** | When not shut down, executes the task in the thread calling `execute` | Can block the producer and break the assumption that "tasks always run on a dedicated worker" |
| **DiscardPolicy** | Drops the rejected task without throwing | Easy to lose work silently; hard to determine status |
| **DiscardOldestPolicy** | Drops the head of the queue and retries `execute` | Older tasks can be lost; unsuitable for mandatory jobs |

**Especially with thread confinement:** If `CallerRunsPolicy` is used, a rejected task can run **directly on the submitting thread**. Thus an architecture relying on "only one worker executes all operations on state" can be broken if the caller also executes tasks. Overload policies must match **ownership** and invariants, not just throughput.

### The Queue Also Affects How the Pool Scales Workers

For `ThreadPoolExecutor` in general:

- If the current worker count is below `corePoolSize`, the pool usually creates a new worker to handle the task.
- Once `core` workers exist, the executor usually **attempts to enqueue**.
- If enqueuing fails and the worker count is below `maximumPoolSize`, the executor can create an additional worker.
- If it can neither enqueue nor create a worker, the task is rejected.

This explains why **`maximumPoolSize` has no effect on scaling above `core`** for an unbounded queue that keeps accepting enqueues. To adjust worker counts dynamically, you must understand both **core/max and the queue type**. Avoid setting a very high max while keeping an unbounded queue and expecting the pool to scale workers when the queue backs up.

## 10. submit(), execute(), and Exception Handling

### execute(Runnable)

**execute()** hands a `Runnable` to the executor. If the `Runnable` throws an unchecked exception, handling depends on the execution path, thread factory/handler, and `ThreadPoolExecutor`; the error may reach the worker thread's uncaught exception handler, and the worker is replaced. **Do not assume the caller of `execute()` directly catches exceptions thrown inside the task.**

### submit(Runnable/Callable)

**submit()** returns a `Future`. Exceptions occurring in the task are typically stored in the `Future`; a caller calling **Future.get()** will receive an **ExecutionException** and inspect its cause. If the `Future` is ignored, task errors may go unseen by the submitter through normal control flow.

### Example 5: Catching Errors from Future.get()

File **FutureFailureDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(1);

        try {
            Future<Integer> result = pool.submit(() -> {
                throw new IllegalArgumentException("invalid input");
            });

            try {
                result.get();
            } catch (ExecutionException ex) {
                System.out.println(
                    "cause = " + ex.getCause().getClass().getSimpleName()
                );
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 FutureFailureDemo.java
java FutureFailureDemo
~~~

Stdout:

~~~text
cause = IllegalArgumentException
~~~

**Future.get()** can also throw `InterruptedException` if the waiting caller is interrupted; a cancelled `Future` can throw `CancellationException`. Do not treat `isDone()` as success: **done includes success, failure, and cancellation**.

### Submission Order Does Not Mean Completion Order

Fixed/cached executors can run tasks in parallel, so a task submitted later may finish earlier. To collect results in stored order, `main` can keep a list of `Future`s and call `get()` by index; that is **result-collection order**, not proof that tasks ran sequentially. If you want to react in **actual completion order**, see **ExecutorCompletionService** or an appropriate composition mechanism.

A single-thread executor runs tasks sequentially in the order they were queued into the executor, but you cannot infer the order of concurrent `submit` calls across multiple producers solely from the executor's name.

## 11. Lifecycle: shutdown, shutdownNow, and awaitTermination

An `ExecutorService` needs a clear lifecycle. On Java 17, use `try/finally` to ensure `shutdown` is called when the pool is no longer needed.

| API | Basic Contract |
| --- | --- |
| **shutdown()** | Stops accepting new tasks, continues processing tasks already accepted before shutdown |
| **shutdownNow()** | Attempts to stop running tasks (typically via interrupt), returns the list of tasks that had not started executing |
| **isShutdown()** | Whether shutdown has been requested |
| **isTerminated()** | Whether all tasks have completed after shutdown |
| **awaitTermination(timeout, unit)** | Waits at most the specified time for the executor to terminate; returns a `boolean` |
| **submit after shutdown** | Typically rejected according to the rejection policy |

**shutdown() does not block** until all tasks finish; it only initiates the shutdown process. **shutdownNow() does not guarantee stopping running tasks**, because tasks may not handle interrupts. The list returned by `shutdownNow()` may contain tasks that were waiting in the queue; the policy for retrying/logging those tasks must be decided by the application.

A cooperative shutdown example:

~~~java
// Illustrative snippet inside a method that throws InterruptedException:
pool.shutdown();

if (!pool.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
    java.util.List<Runnable> pending = pool.shutdownNow();
    // Log/schedule handling of pending tasks per business requirements.
    if (!pool.awaitTermination(10, java.util.concurrent.TimeUnit.SECONDS)) {
        // Log that some tasks still did not terminate.
    }
}
~~~

There is no `main()` in this snippet; `pool` must be an initialized `ExecutorService`. In real systems, if a thread is performing non-interruptible I/O, calling `shutdownNow` may not make it terminate. **Using a timeout does not mean the task was cancelled and its side effects were rolled back**.

### Do Not Block Yourself During Shutdown

If a task running in a single-thread executor submits a subtask **to the same executor** and calls `Future.get()` to wait for the subtask, the sole worker is occupied by the current task so the subtask cannot run. This is a **thread-starvation deadlock**.

Similarly, trying to wait for an executor to terminate from inside one of its own workers, while the executor must wait for that worker to finish, can cause a wait cycle. Analyze the **dependency graph**, not just the thread count.

## 12. Task Cancellation and Interrupts

**Future.cancel(true)** requests cancellation and may interrupt the thread running the task. It does **not** forcibly stop execution immediately, undo completed I/O, or roll back transactions. **cancel(false)** does not request interrupting an already-running task, though it can still mark the `Future` as cancelled according to its contract.

A task that supports cancellation should:

- Check **Thread.currentThread().isInterrupted()** at checkpoints in long loops.
- Handle **InterruptedException** from blocking APIs: propagate it or restore the interrupt flag and exit per policy.
- Release locks/permits/streams/resources properly in `finally`.
- Avoid calling non-idempotent external operations uncontrollably in retry paths.
- Distinguish a **request timeout** from **the task actually stopping** and **side effects being committed**.

### Example 6: Cancelling a Task Waiting on a Latch

File **ExecutorCancelDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutorCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            Future<?> task = pool.submit(() -> {
                entered.countDown();
                try {
                    neverReleased.await();
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                }
            });

            entered.await();
            boolean cancelled = task.cancel(true);

            pool.shutdown();
            boolean terminated = pool.awaitTermination(
                    5, TimeUnit.SECONDS
            );

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("worker interrupted = " + sawInterrupt.get());
            System.out.println("pool terminated = " + terminated);
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ExecutorCancelDemo.java
java ExecutorCancelDemo
~~~

Stdout when the worker receives the interrupt and terminates per protocol (normal environment):

~~~text
cancel accepted = true
worker interrupted = true
pool terminated = true
~~~

**Explanation:**

- `entered.await()` ensures the task has started before `main` calls `cancel`.
- The worker is waiting on a `CountDownLatch` that is never signaled, so `cancel(true)` is an appropriate interrupt request for that blocking wait.
- The worker catches `InterruptedException`, sets the observation flag, and finishes.
- `awaitTermination` checks whether the executor has terminated; the caller only prints status after requesting shutdown and waiting.
- A `Future` marked cancelled **does not mean an arbitrary task will always receive an interrupt successfully**. This example deliberately chooses `CountDownLatch.await()` to illustrate a cooperative cancellation path.

**In practice:** If the 5-second timeout elapses due to a very busy environment or an unresponsive worker, `pool terminated` can be `false`; do not use a fixed numeric wait to prove the JVM always terminates by a deadline. The takeaway here is to **check the result of `awaitTermination`**, rather than assuming success.

## 13. Java Memory Model: Submitting Tasks and Retrieving Future Results

`ExecutorService` has important memory consistency rules:

- Actions in a thread **prior to submitting a Runnable/Callable to an ExecutorService** *happen-before* the actions of that task.
- Actions in the task *happen-before* actions in another thread **after retrieving the result via Future.get()**.

Because of this, passing input prepared before `submit` and reading output after `Future.get()` has a solid JMM foundation.

~~~text
Producer thread                        Worker thread
----------------                       -------------
prepare input
submit(task)        --- happens-before -> task reads input
                                         task produces result
future.get()         <- happens-before -- task finishes
consume result
~~~

However, **do not modify mutable input concurrently while the task is reading it** without additional synchronization. The happens-before guarantee of `submit` does not allow the producer to keep writing unsynchronized to the same object after submitting and expect the worker to see a consistent snapshot.

A single-thread executor also does not automatically protect against code outside the executor accessing the worker's state. Business state is only truly confined if only the owner worker mutates it and communicates with other threads through channels with clear contracts.

## 14. Independent Tasks and Shared State

A pool allows multiple tasks to **run concurrently**, but does not guarantee safe access to shared mutable state:

~~~java
// Illustrative anti-pattern when a pool has multiple workers:
java.util.HashMap<String, Integer> totals = new java.util.HashMap<>();

pool.submit(() -> totals.put("a", 1));
pool.submit(() -> totals.put("b", 2));
~~~

Both `put` calls on `HashMap` can occur concurrently; `HashMap` is not thread-safe by contract. Do not try to fix this by adding `Thread.sleep` in one task. Options depend on your invariants:

- If you only need a map supporting concurrent operations, consider **ConcurrentHashMap** and operations with appropriate atomic semantics.
- If multiple fields must be updated together, use a **lock** protecting the entire in-JVM transaction.
- If possible, move the state to a **single-thread owner** and send commands to the owner.
- If tasks are independent, return immutable results and merge them on one thread after `Future.get()`.

**Do not infer that every sequence of operations on ConcurrentHashMap is atomic**: `containsKey` followed by `put` is still a check-then-act race unless you use conditional operations such as `putIfAbsent`/`computeIfAbsent` per contract.

### When Does Single-Thread Help Avoid Locks?

If a mutable object is only touched by tasks running on the same single-thread executor, operations on that object have no concurrent access from the executor's tasks. You can reduce the need for locks inside the object. But if a producer holds a reference to that object and modifies it directly, or uses `CallerRunsPolicy` causing a task to run on the calling thread, the ownership model is broken.

### When Do Fixed/Cached Pools Need Atomics or Locks?

When tasks in a pool share mutable state, all related accesses need an appropriate protocol: atomic increments for counters, CAS for single-variable state, locks for multi-step invariants, or message passing to avoid sharing.

## 15. Do Not Confuse Pool Name with Thread Identity and ThreadLocal

Fixed, cached, and single-thread executors all **reuse threads** according to their policies. Common mistakes:

- Task A stores context in a `ThreadLocal` and forgets **remove()**; Task B running later on the same worker can see leftover context.
- A thread name or ID is not a request ID: one worker can run very many tasks.
- A single-thread executor can replace its worker if the old worker dies; do not store business state solely in `ThreadLocal` expecting it never to be lost.
- A cached pool can create a new thread for an incoming task when no worker is idle, so `ThreadLocal` data from a previous task is not guaranteed to appear.
- A fixed pool has N threads, with no promise that a given task always belongs to the same specific worker.

For task context, the safe approach is to **pass the needed data in the task object** or set/clear `ThreadLocal` scoped inside `try/finally` if `ThreadLocal` is truly needed. Any context shared via mutable references still requires safe publication and ownership analysis.

## 16. Pool Sizing and Measurement Principles

### CPU-Bound

For continuously CPU-intensive tasks, a worker count close to the actual allocated CPU count is a **starting point for measurement**. Too many CPU-bound workers can increase context switching, cache contention, and degrade performance. Do not treat `Runtime.availableProcessors()` as an absolute formula: the JVM may be subject to container quotas, hyper-threading, mixed workloads, and application constraints.

### Blocking I/O

Tasks may spend a lot of time waiting on sockets/files/databases. You may need more workers than CPUs, but you must still bound **real resources** such as connection counts, memory, remote rate limits, and queue backlogs. A cached pool is not an automatic answer for every I/O problem.

### Single-Thread

One worker is good when correctness requires sequential execution and the load fits a single thread's processing capacity. However, it will experience head-of-line blocking when a task takes a long time. Measure **queue latency**, task processing time, and backlog, not just CPU.

### Which Metrics to Measure?

| Metric | Why It Is Useful |
| --- | --- |
| Throughput (tasks/second) | Actual processing capacity |
| Active worker count | Concurrency level and contention |
| Queue size/age | Pending backlog and latency risk |
| Rejection count | Overload has exceeded acceptance policy |
| Task execution latency | Task runtime |
| Queue waiting latency | Time from submit to start of execution |
| Tail latency p95/p99 | End-user impact during load spikes |
| Heap/thread count | Memory/thread exhaustion risk |
| Error/cancel/timeout count | Why tasks ended, not just `isDone` |

Do not conclude that fixed is faster than cached or vice versa from a single benchmark. Test across multiple task sizes, CPU counts, blocking durations, producer rates, warmup/JIT, and resource limits. You can combine **bounded concurrency** with other mechanisms rather than picking just one factory.

## 17. Deadlocks and Circular Waits in Executors

### Single-Thread Task Waiting on Another Task in the Same Pool

~~~java
// Illustrative anti-pattern; if placed inside a task running on a single pool:
Future<?> child = sameSinglePool.submit(() -> doChildWork());
child.get(); // The sole worker is waiting on a task that cannot run yet.
~~~

Non-standalone snippet: `sameSinglePool` and `doChildWork()` are hypothetical placeholders; `child.get()` requires checked-exception handling. If there is only one worker, the child task is queued behind the parent task while the parent waits on the child; that is a **thread-starvation deadlock**.

### Fixed Pool Fully Occupied by Dependent Waiting Tasks

This is not just a single-thread issue. A 4-worker fixed pool can be completely occupied by 4 parent tasks, each submitting a child task to the same pool and waiting on `Future.get()`. All child tasks sit in the queue with no free worker to process them. Increasing the pool to 8 may only push the failure threshold if the dependency design still has cycles.

### Waiting on a Future While Holding a Lock

Thread A holds lock L and calls `Future.get()` waiting for a worker; the worker needs to acquire lock L to finish. A wait cycle cannot be solved by switching from cached to fixed. You must analyze the dependency graph, avoid waiting inside critical sections when possible, or design an appropriate asynchronous workflow.

### When to Separate Executors?

A parent task that must wait on a child belonging to a different resource/wait type can be organized on a separate executor, or results can be chained asynchronously so workers are not held in a wait cycle. However, creating more executors does not fix flawed dependency logic by itself, does not replace timeouts/cleanup, and does not mean more pools are always better.

## 18. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| A fixed pool accepts at most N tasks | N bounds active workers; the queue can accept many more tasks |
| A fixed pool always has N Thread objects pre-created from construction | Workers can be created on demand; they can be replaced on failure |
| A cached pool caps threads at the CPU count | No; cached can create very many platform threads |
| A cached pool holds its backlog in LinkedBlockingQueue | The default pattern uses `SynchronousQueue` handoff |
| A single-thread executor has one immutable Thread object forever | The worker can be replaced, while the sequential contract is preserved |
| Single-thread means multiple submitting threads get deterministic business order | Concurrent submitters need explicit ordering rules |
| A pool having workers means a task always runs immediately | A task may sit in the queue or be rejected |
| `Future.isDone()` means the task succeeded | Done can also mean failure or cancellation |
| `submit()` automatically prints errors when a task throws | Exceptions are usually stored in the `Future` and observed via `get()` |
| `shutdown()` waits for all tasks to finish before returning | It initiates shutdown; it does not block |
| `shutdownNow()` guarantees stopping tasks immediately | It typically only sends interrupts/attempts to stop; tasks must cooperate |
| `Future.get(timeout)` timing out means the worker was cancelled | It only limits how long the caller waits |
| Default factories already provide backpressure | Fixed/single have practically unbounded queues; cached grows workers |
| Setting `maximumPoolSize` higher than `core` always scales the pool up to max | An unbounded queue can absorb the backlog so the pool never exceeds `core` |
| `CallerRunsPolicy` only slows down the application | It can shift where the task executes, breaking owner-thread assumptions |
| A pool makes all shared state thread-safe | You must use atomics/locks/confinement for data |
| Data in `ThreadLocal` belongs to the executor | `ThreadLocal` belongs to a specific thread, not the executor or request |

## 19. Checklist When Choosing an Executor

**Correctness:**

- [ ] Are tasks independent or do they mutate shared state?
- [ ] Is **serialization** required, or is out-of-order completion allowed?
- [ ] Can callers submit concurrently, and what are the task ordering rules?
- [ ] Does any task submit child tasks and wait for their results in the same pool?
- [ ] Are any callbacks or side effects invoked while holding a lock?
- [ ] Is `ThreadLocal` set and removed properly within each task's scope?

**Load and Resources:**

- [ ] Are tasks CPU-bound or blocking, and what is the typical wait duration?
- [ ] Are target concurrency, queue capacity, and connection/thread limits known?
- [ ] Is there a clear backpressure or rejection policy under overload?
- [ ] Are queue age, active count, rejections, timeouts, and errors measured?
- [ ] Has tail latency been tested under bursts/overload?

**Lifecycle and Errors:**

- [ ] Is the executor shut down at the end of its lifecycle?
- [ ] Is there `awaitTermination` or an appropriate shutdown monitoring mechanism?
- [ ] Is there a policy when a task does not respond to interrupts?
- [ ] Are errors caught via `Future.get`, `CompletionService`, or another error-reporting channel?
- [ ] Are timeouts/cancellations kept distinct from side-effect completion?
- [ ] How are tasks submitted after executor shutdown handled?

## 20. Self-Check Questions

**1. Does `newFixedThreadPool(4)` block submitting the fifth task?**  
Not in the sense of always blocking or rejecting once 4 tasks exist. Typically the fifth task is queued if all four workers are busy; the default queue is very large. For a bounded backlog, use a different configuration/mechanism.

**2. Does a cached pool automatically limit the number of threads to the CPU core count?**  
No. When no worker is idle to receive a handoff, a cached pool can create many more platform threads until it hits configuration or resource limits.

**3. Does a single-thread executor guarantee every task runs on the exact same Thread object for its entire lifetime?**  
No. It guarantees only one task executes at a time and follows queue order; the actual thread may be replaced if the worker dies.

**4. If a submitted `Callable` throws an exception, where can the caller obtain the error details?**  
`Future.get()` can throw `ExecutionException` containing the cause; you must inspect/log it instead of discarding the `Future`.

**5. Will a `ThreadPoolExecutor` with `core=2`, `max=8`, and an unbounded queue normally grow to 8 workers when the queue gets long?**  
Not necessarily. The queue keeps accepting tasks after `core` is reached, so `maximumPoolSize` may not be used to scale under normal conditions.

**6. When is `CallerRunsPolicy` dangerous for state that only one worker is allowed to mutate?**  
When the queue is full, a task can run on the submitting thread rather than the owner worker; the confinement assumption is broken.

**7. Is `shutdown()` the same as `shutdownNow()`?**  
No. `shutdown` stops accepting new tasks while letting accepted tasks continue; `shutdownNow` attempts to stop running tasks and returns unstarted tasks without guaranteeing they stop.

**8. Does `Future.get(timeout)` throwing `TimeoutException` prove the task is no longer running?**  
No. Only the caller stopped waiting after the deadline; the task may still be running.

**9. If the first task runs slowly in a single-thread executor, will later tasks run ahead of it to reduce latency?**  
No, not in the same executor by its sequential design; they wait for the earlier task, creating head-of-line blocking.

**10. Should a cached pool be used for all I/O operations?**  
No. If blocking is long or request volume is unbounded, the thread count can grow excessively. You must evaluate load, resources, and backpressure.

## 21. Summary

A **fixed pool** is suitable when you need to **bound concurrency** to N workers, but you must manage the backlog because the default queue is practically unbounded. A **cached pool** fits workloads with short, bursty tasks and external load control, but can grow platform threads very large when all workers are busy. A **single-thread executor** fits when you need **task serialization and a single owner handling mutable state**, at the cost of potential queue growth and head-of-line blocking.

All three are implementations of **ExecutorService**: consider **tasks, workers, queue, rejection, cancellation, Future errors, and shutdown** together. When strict resource limits or backpressure are required, use a **ThreadPoolExecutor explicitly configured with a bounded queue and a rejection policy**. An executor does not replace proving **happens-before, atomicity, and data invariants** for the tasks being executed.
