# Executor, ExecutorService, and ThreadPoolExecutor in Java Concurrency

> **Scope:** Java SE's Executor Framework, explaining the three levels of abstraction `Executor`, `ExecutorService`, and `ThreadPoolExecutor`; how to submit tasks, retrieve results, manage lifecycle and configure thread pools, control queues/rejection, Java Memory Model relationships, and deadlock-prone scenarios. This article focuses on **general Java concurrency**, without using Spring-specific mechanisms.

## 1. Why Does Java Have the Executor Framework?

The basic way to execute a task concurrently is to create a thread:

```java
Thread thread = new Thread(() -> doWork());
thread.start();
thread.join();
```

This is an **illustrative code snippet inside a method**: `doWork()` must be declared and the method must declare/handle `InterruptedException` from `join()`.

For a few tasks, this approach is simple. However, when an application continuously receives thousands of tasks, creating a platform thread for every task can increase overhead, the number of OS threads/stacks, contention, and make shutdown difficult to control. If many tasks need to share a finite number of workers, the application also needs:

- **A place to submit tasks** instead of directly managing each thread.
- **Execution policies:** run immediately in the caller, create a worker, place in a queue, limit concurrency.
- **Results/exceptions:** obtain the return value of a `Callable` and know whether a task succeeded or failed.
- **Lifecycle management:** stop accepting new tasks, wait for existing tasks to finish, cancel when needed.
- **Backpressure/rejection:** if both workers and the queue are busy, how should new tasks be handled?
- **Observability/tuning:** queue length, active threads, completed tasks, latency, and failures.

The Executor Framework **decouples "what needs to be done" from "where and how the task is executed"**. Instead of calling `new Thread` throughout the application, the caller describes the work as a `Runnable` or `Callable<T>` and hands it off to an executor.

**Important guarantee:** an executor **does not necessarily run tasks on a new thread**. `Executor` only defines an execution interface. An implementation may run synchronously in the caller, on a reused worker, on a pool, or via another strategy. Do not assume that calling `execute()` means starting a new thread.

## 2. Three API Levels to Distinguish

```text
Executor
   |
   +-- execute(Runnable)
   |
   +-- ExecutorService extends Executor
          |
          +-- submit(...), invokeAll(...), invokeAny(...)
          +-- shutdown(), shutdownNow(), awaitTermination(...)
          +-- Future<T> for result/cancellation
          |
          +-- ThreadPoolExecutor implements ExecutorService
                 |
                 +-- corePoolSize, maximumPoolSize, keepAliveTime
                 +-- BlockingQueue<Runnable>, ThreadFactory
                 +-- RejectedExecutionHandler, metrics/hooks
```

### 2.1. `Executor`: "Execute this Runnable"

`Executor` is a functional interface with a single method:

```java
void execute(Runnable command);
```

This is an **illustrative API signature**, not a method you need to implement yourself for every application. A concrete executor decides when and where a task runs.

Example of a **direct executor** that does not create workers:

```java
import java.util.concurrent.Executor;

Executor direct = Runnable::run;
direct.execute(() -> System.out.println("Executed by caller"));
```

This is a code snippet placed inside a method (with import). `Runnable::run` invokes `run()` directly on the thread calling `execute()`, so **there is no asynchrony**. This example shows that you should not infer from the name `Executor` that it always has a thread pool.

`Executor.execute()` accepts a `Runnable` and does not return a `Future`. If you want to receive a result/exception as a waitable object, use `ExecutorService.submit()` or combine it with a completion mechanism yourself.

### 2.2. `ExecutorService`: Submitting Tasks, Retrieving Results, Managing Lifecycle

`ExecutorService` **extends** `Executor`, adding core methods:

- `submit(Runnable)` returns `Future<?>`; when the task completes normally, `get()` returns `null`.
- `submit(Callable<T>)` returns `Future<T>`; `get()` returns a result of type `T` or throws `ExecutionException` if the task fails.
- `submit(Runnable, T result)` returns a `Future` with the value `result` when the runnable completes successfully.
- `invokeAll(Collection<? extends Callable<T>>)` accepts multiple tasks and returns a list of `Future`s in **input order**, not in task completion order.
- `invokeAny(...)` returns one successful result from a set of tasks, with no guarantee about which task wins; the remaining tasks may be cancelled according to the contract.
- `shutdown()` stops accepting new tasks and continues processing already submitted tasks.
- `shutdownNow()` attempts to stop running tasks and returns a list of tasks that were queued but not yet started.
- `awaitTermination(timeout, unit)` waits for the pool to reach the terminated state or for the timeout/interrupt to occur.
- `isShutdown()` and `isTerminated()` help observe the lifecycle.

`ExecutorService` is an **interface**. You cannot deduce core threads, queue, or rejection policy of every instance from the `ExecutorService` type alone: the actual execution behavior depends on the implementation.

### 2.3. `ThreadPoolExecutor`: A Configurable Concrete Implementation

`ThreadPoolExecutor` is a class in `java.util.concurrent` that lets you control:

1. Core worker count: `corePoolSize`.
2. Maximum worker count: `maximumPoolSize`.
3. How long workers beyond core are kept when idle: `keepAliveTime`.
4. Queue holding tasks not yet running: `BlockingQueue<Runnable>`.
5. How workers are created: `ThreadFactory`.
6. How tasks that cannot be accepted are handled: `RejectedExecutionHandler`.

Representative constructor:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
    2, 4,
    30L, TimeUnit.SECONDS,
    new ArrayBlockingQueue<>(100),
    Executors.defaultThreadFactory(),
    new ThreadPoolExecutor.AbortPolicy()
);
```

This is a code snippet placed inside a method; it requires importing `ThreadPoolExecutor`, `TimeUnit`, `ArrayBlockingQueue`, and `Executors`. When the pool is no longer needed, lifecycle shutdown must be performed; this example omits that code because it only illustrates the constructor.

**Do not interpret `maximumPoolSize = 4` as meaning that whenever there are 4 tasks, the pool creates 4 threads.** The interaction between `corePoolSize` and the queue type determines when the pool creates new workers.

## 3. `Runnable`, `Callable`, and `Future`

### Runnable: No Declared Return Value

```java
Runnable task = () -> processEvent();
executor.execute(task);
```

This is an illustration with `processEvent()`/`executor` provided by the caller. `Runnable.run()` has the signature `void run()` and does not declare checked exceptions. If the task fails, exception propagation depends on how the task was submitted and the implementation; there is no `Future.get()` by default to retrieve it.

### Callable: Returns a Result and Can Throw Exception

```java
Callable<Integer> task = () -> 21 * 2;
Future<Integer> result = service.submit(task);
Integer value = result.get();
```

This is a code snippet inside a method where `service` is an `ExecutorService`, requiring imports for `java.util.concurrent.Callable` and `Future`; the method must handle/declare `InterruptedException`/`ExecutionException`.

`Callable<V>.call()` returns `V` and declares `throws Exception`. `ExecutorService.submit` wraps completion in a `Future`.

### `Future.get()` Is Not a "Non-blocking Poll"

- `get()` may **block** until the task completes.
- `get(timeout, unit)` may throw `TimeoutException`; **a timeout in `get` does not automatically cancel the task**.
- If the task throws an exception, `get()` throws `ExecutionException`, with `getCause()` holding the underlying cause.
- If the `Future` was cancelled, `get()` throws `CancellationException`.
- If the thread calling `get` is interrupted while waiting, `get` throws `InterruptedException`.
- `isDone()` is true when the task finishes **normally, with failure, or via cancellation**; it is not proof of success.
- `isCancelled()` indicates cancellation status; `cancel(true)` requests an interrupt if the task is running, **without guaranteeing that code ignoring interrupts will stop immediately**.

**Key point:** if you only call `submit` without observing the `Future` or another error-reporting channel, exceptions in the task can become "silent" failures at the call site. For critical tasks, failures must be checked/recorded according to an explicit protocol.

## 4. Runnable Java 17 Example: All Three API Levels

This program demonstrates three distinct behaviors and **does not depend on scheduler luck**:

1. `Executor` runs a task directly, confirming the `Runnable` was invoked.
2. `ExecutorService` accepts a `Callable` and returns 42 via `Future.get()`.
3. `ThreadPoolExecutor` has **one worker and queue capacity = 1**. We use a latch to hold the worker in the first task, enqueue the second task, and then submit the third task; with `AbortPolicy`, the third task **is rejected**. Then we release the latch, read both results, shut down, and wait for the pool to terminate.

Create the file **`ExecutorFrameworkDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executor;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExecutorFrameworkDemo {
    public static void main(String[] args) throws Exception {
        AtomicBoolean ran = new AtomicBoolean(false);
        Executor direct = Runnable::run;
        direct.execute(() -> ran.set(true));
        System.out.println("executorRan=" + ran.get());

        ExecutorService service = Executors.newSingleThreadExecutor();
        try {
            Future<Integer> answer = service.submit(() -> 6 * 7);
            System.out.println("submitResult=" + answer.get());
        } finally {
            service.shutdown();
        }

        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(1),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> first = pool.submit(() -> {
                started.countDown();
                release.await();
                return "first";
            });
            started.await();
            Future<String> second = pool.submit(() -> "second");

            boolean rejected = false;
            try {
                pool.execute(() -> { });
            } catch (RejectedExecutionException expected) {
                rejected = true;
            }
            System.out.println("rejectedWhenSaturated=" + rejected);

            release.countDown();
            System.out.println("taskResults=" + first.get() + "," + second.get());
        } finally {
            release.countDown();
            pool.shutdown();
        }
        System.out.println("poolTerminated="
                + pool.awaitTermination(5, TimeUnit.SECONDS));
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac --release 17 ExecutorFrameworkDemo.java
java ExecutorFrameworkDemo
```

**Verified stdout:**

```text
executorRan=true
submitResult=42
rejectedWhenSaturated=true
taskResults=first,second
poolTerminated=true
```

### Line-by-Line Analysis

**`executorRan=true`:** `Runnable::run` executes directly, so the `AtomicBoolean` value has already changed before `execute()` returns. No new platform thread is created just by calling `Executor.execute()` in this case.

**`submitResult=42`:** `Executors.newSingleThreadExecutor()` provides an `ExecutorService` with a single worker executing tasks sequentially. `submit(Callable<Integer>)` returns a `Future`; `get()` waits for the computation to finish and retrieves the result.

**`rejectedWhenSaturated=true`:**

- `ThreadPoolExecutor(1,1,..., new ArrayBlockingQueue<>(1), AbortPolicy)` has at most **one active worker**.
- The first task is run by the worker, signals `started.countDown()`, and then **waits on `release.await()`**, so the worker is not free.
- `started.await()` in `main` confirms the first task is at the checkpoint before submitting the next task.
- The second task cannot get an additional worker (max = 1), so it is enqueued into the **single slot**.
- The third task arrives while the worker is busy and the queue is full. `AbortPolicy` throws `RejectedExecutionException`, which the code catches and prints `true`.

**`taskResults=first,second`:** after `release.countDown()`, the worker finishes the first task, then runs the second task from the queue. Reading `Future.get()` ensures both complete; the result expression is combined in the order `main` calls `get`, not because the scheduler promises that `submit` call order always reflects thread completion order in every pool type.

**`poolTerminated=true`:** after retrieving both `Future`s and calling `pool.shutdown()`, `awaitTermination` succeeded in the verified run. `awaitTermination` has a 5-second timeout, so in an abnormally stuck environment it may return `false`; the program prints the actual observed state rather than inferring from a timeout that all threads have definitely stopped.

### Limitations of the Practice Example

- The latch only controls **the test schedule**, not a production work-processing model.
- The code calls `shutdown()` after the tasks complete; production code should have cancellation/timeouts or a shutdown policy when a `Future` never finishes.
- Calling `release.countDown()` in `finally` prevents the worker from remaining stuck on the latch if `main` encounters an exception midway.
- Standard Java SE executor classes do not automatically provide transactions for databases, external APIs, or file systems.
- For a failed task in `submit`, you can inspect the cause via `ExecutionException.getCause()`. `Future.get` is a completion/visibility boundary, not a guarantee that "every side effect outside the JVM has been committed".

## 5. How Does `ThreadPoolExecutor` Process a New Task?

For a `ThreadPoolExecutor` in the running state with a typical configuration, the main admission logic is:

1. If the current number of workers is **less than `corePoolSize`**, prioritize creating a worker to run the new task.
2. Once core is reached, try to **place the task into the work queue**.
3. If the queue cannot accept the task (usually because it is full), try to **create an additional worker** if the total number of workers is still below `maximumPoolSize`.
4. If the task can neither be enqueued nor have a new worker created, the executor **rejects** the task according to `RejectedExecutionHandler`.

```text
                  execute(task)
                       |
             workerCount < core?
              /               \
            yes               no
             |                 |
       create worker     offer to workQueue
                              /      \
                         success    failure
                            |          |
                         queued    workerCount < max?
                                      /       \
                                     yes      no
                                      |        |
                                create worker REJECT
```

This simplified diagram explains the common strategy; internally, the class also checks pool state and handles shutdown races. **A task can be rejected when the pool is shutting down**, even if the queue is not full.

### Example: `core=2`, `max=4`, Queue Capacity 3

- Tasks 1 and 2 can create two core workers.
- While the two core workers are busy, tasks 3–5 can sit in the queue.
- Tasks 6–7 arriving when the queue is full can trigger the 3rd and 4th workers.
- Task 8 arriving when all 4 workers are busy and the queue is still full → rejection according to policy.

This is an **illustrative scenario when earlier tasks have not finished yet**. If tasks complete quickly, the thread pool can reuse workers and the queue may not actually fill up; do not treat task sequence numbers as a fixed schedule for every execution.

### Configurations That Make `maximumPoolSize` Have Little Effect

If the work queue is a **nearly unbounded** `LinkedBlockingQueue`, tasks can keep being enqueued after core is reached, so the pool typically **does not grow workers beyond core** just because many tasks are queued. In that case, `maximumPoolSize` may not provide the scaling behavior the configurator expected.

If `SynchronousQueue` is used, it stores no items internally: the producer hands the task directly to a receiving worker. When no worker is idle and the worker count has not reached max, the pool can grow workers more aggressively; setting max too large risks creating very many threads under burst load.

**Choose the queue deliberately**, because it affects not only memory/backpressure but also directly determines how the thread pool scales its worker count.

## 6. Key Parameters and Trade-offs

| Parameter | Meaning | Common Misconception |
|---|---|---|
| `corePoolSize` | Target number of workers maintained by policy; workers may be created as tasks arrive, not necessarily all in the constructor | "Core threads are always prestarted immediately" |
| `maximumPoolSize` | Upper bound on workers in the executor (subject to queue and lifecycle conditions) | "The pool will always grow to max when many tasks arrive" |
| `keepAliveTime` | Idle timeout for workers above core by default | "All core threads automatically stop after keepAlive" |
| `workQueue` | Holds tasks waiting for a worker | "A thread-safe queue means the backlog cannot grow unboundedly" |
| `ThreadFactory` | How threads are created: name, daemon flag, priority, `UncaughtExceptionHandler`, etc. | "Setting daemon=true is a proper shutdown strategy" |
| `RejectedExecutionHandler` | Policy when a task cannot be accepted | "Rejection always throws an exception" |
| `allowCoreThreadTimeOut(true)` | Allows core workers to also time out when idle if API conditions are met | "Can be enabled with keepAlive=0 by default" |

### Worker Count and Workload Type

**CPU-bound:** if tasks are mostly computational and non-blocking, a number of platform workers close to the actually available CPUs is usually a good starting point for measurement. Adding too many workers causes context switching, cache contention, and lower throughput.

**I/O-bound:** tasks waiting on network/disk can benefit from having more concurrent tasks than CPUs. However, you must check downstream limits: connection pools, API rate limits, file descriptors, memory, and latency. A large worker count cannot solve an overloaded external resource.

**Mixed:** separate workload groups with different characteristics or use separate deadlines/capacities. For example, a very long file-reading task should not starve critical UI/health-check update tasks of workers.

These are **starting points for measurement**, not fixed formulas; workloads require benchmarking, profiling, and overload testing against real SLAs.

### `prestartCoreThread(s)`

`ThreadPoolExecutor` provides `prestartCoreThread()` and `prestartAllCoreThreads()` to create core workers before tasks arrive when you need to reduce cold-start latency. Using them is optional; creating many idle threads early also consumes resources.

### `allowCoreThreadTimeOut`

If you want core workers to also be reclaimed when idle, `allowCoreThreadTimeOut(true)` enables that mechanism with a valid keep-alive configuration. When new tasks arrive, workers can be recreated. This trades off idle resource usage against worker recreation time.

## 7. Work Queue and Backpressure

`ThreadPoolExecutor` typically uses a `BlockingQueue<Runnable>` to hold tasks that have not yet been assigned a worker. This is **the executor's task queue**, not necessarily the same data queue that business logic uses to pass messages.

Several options:

- `ArrayBlockingQueue<>(capacity)`: explicit capacity, FIFO, prevents unbounded backlog in the pool's queue.
- `LinkedBlockingQueue<>(capacity)`: bounded linked queue if an explicit capacity is passed.
- `new LinkedBlockingQueue<>()`: default capacity is very large (`Integer.MAX_VALUE`), **not a practical memory bound**.
- `SynchronousQueue<>()`: direct handoff, holds no backlog in the queue, making admission depend on an available worker or creating a new worker.
- `PriorityBlockingQueue`: priority ordering instead of FIFO and no hard capacity bound like `ArrayBlockingQueue`; not suitable by default for bounding resources.

**Work queue capacity does not equal total work in the system.** The total number of tasks accepted by the executor includes both running tasks and queued tasks. In addition, there may be tasks sitting in upstream queues, HTTP buffers, message brokers, or other sources.

### Choosing Backpressure Explicitly

If all workers are busy and the work queue is full, the executor must decide that **it cannot accept more tasks**. The default policy of `ThreadPoolExecutor` when using `AbortPolicy` is to throw `RejectedExecutionException`.

Callers should handle rejection according to the contract:

- Return "overloaded" to upstream.
- Retry with limits, backoff, and idempotency.
- Offload work to durable storage if loss is not acceptable.
- Throttle upstream / apply rate limiting.
- Use caller-runs thoughtfully to propagate backpressure to the submitting thread.

**Never silently ignore rejection** if the task is an order, payment, or mandatory event. Dropping tasks due to a "full queue" is a business behavior that must be declared and monitored.

## 8. Rejection Policies of `ThreadPoolExecutor`

| Handler | General Behavior | Caveats When Using |
|---|---|---|
| `AbortPolicy` | Throws `RejectedExecutionException` | Caller must catch/propagate/report |
| `CallerRunsPolicy` | Runs the task in **the thread calling `execute`** if the pool is not shut down | Slows down the caller (backpressure), breaks the assumption "tasks always run on workers"; when the pool is shut down, the task is dropped |
| `DiscardPolicy` | Silently drops the task | May lose data; unsuitable for mandatory work |
| `DiscardOldestPolicy` | Drops the task at the head of the queue and retries submitting the new task while running | May drop important work; undesirable interactions with priority queues and concurrency |

### `CallerRunsPolicy` Is Not Always Harmless

If the task performs heavy I/O and the caller is a request thread, caller-runs causes request latency to spike. If the task executes code that relies on worker identity/`ThreadLocal`, running the task in the caller can cause semantic bugs. With `submit()`, the task is typically wrapped in a `FutureTask`: caller-runs can execute it immediately in the caller, making the `submit` call take time before returning the `Future`.

**In particular:** once the executor has shut down, `CallerRunsPolicy` **does not run** the rejected task and may drop it. Therefore, if you need a guarantee that "the task is always executed or returns an error," you must design an explicit rejection contract rather than assuming caller-runs is unconditionally safe.

### `DiscardOldestPolicy` and FIFO Queues

"Oldest" here means the task at the head of the queue according to the queue's `poll()` behavior, **not necessarily the task with the oldest business timestamp**. With a priority queue, the "head" can even be the highest-priority task—discarding it may be the opposite of what you expect.

Both discard handlers can cause lost work. Only use them when the product contract genuinely permits dropping tasks and metrics exist to detect it.

### Custom Handler

`RejectedExecutionHandler.rejectedExecution(Runnable r, ThreadPoolExecutor executor)` lets you implement a custom policy. A production handler can emit a metric and throw a descriptive exception, but it must avoid **indefinite blocking or deadlock** on the same overloaded executor. The handler runs on the task-submission path and must be audited for concurrency.

## 9. `execute` vs. `submit`: Where Do Exceptions Go?

This is one of the most frequently overlooked operational differences.

```java
// Illustration inside a method, executor is ThreadPoolExecutor:
executor.execute(() -> {
    throw new IllegalStateException("failed in execute");
});

Future<?> future = executor.submit(() -> {
    throw new IllegalStateException("failed in submit");
});
```

This is an **illustrative snippet** with appropriate imports. In `submit`, the executor wraps the task in a `FutureTask` and stores the result/exception in the `Future`; calling `future.get()` throws `ExecutionException` with cause `IllegalStateException`.

With `execute`, an unchecked exception can escape the worker's `run()` method and be handled by the thread/implementation's uncaught exception mechanism; no `Future` is returned to the caller to inspect the cause. Do not assume that merely watching `System.err` is a complete error-monitoring strategy.

`ThreadPoolExecutor.afterExecute(Runnable r, Throwable t)` can be overridden to collect task completion information, but note: **when a task is wrapped by `submit` in a `FutureTask`, the exception is usually inside the `Future`, and the hook's `t` parameter may be `null`**. If you need to extract the failure, you must inspect the `Future` carefully (and avoid blocking indefinitely inside the hook).

**Operational recommendation:** use an explicit mechanism to **record failed tasks**, covering both business exceptions and infrastructure exceptions, instead of relying only on default worker logs.

## 10. `ExecutorService` Lifecycle and Safe Shutdown

### Logical States

An executor can be:

1. **Running:** accepts new tasks.
2. **Shutdown:** does not accept new tasks, but may continue already accepted tasks.
3. **Terminated:** no tasks remain executing; the executor has finished.
4. **Stop attempt:** `shutdownNow()` attempts to interrupt running tasks, without guaranteeing that every task stops immediately.

`shutdown()` does not wait. `awaitTermination()` **only waits** and returns a boolean; it does not call `shutdown()` itself. If `shutdown` is not called, a pool with remaining workers can keep the JVM running (especially when threads are non-daemon). Therefore, resource ownership and lifecycle must be clear.

### Graceful Shutdown Pattern

```java
static void stopGracefully(ExecutorService service)
        throws InterruptedException {
    service.shutdown(); // do not accept new tasks
    try {
        if (!service.awaitTermination(10, TimeUnit.SECONDS)) {
            service.shutdownNow(); // request interruption of running tasks
            if (!service.awaitTermination(10, TimeUnit.SECONDS)) {
                System.err.println("Executor did not terminate");
            }
        }
    } catch (InterruptedException e) {
        service.shutdownNow();
        Thread.currentThread().interrupt();
        throw e;
    }
}
```

This is an **illustrative static method** placed in a class that imports `ExecutorService` and `TimeUnit`; the 10-second threshold is only an example and should be chosen based on workload/SLA. When `InterruptedException` needs to be propagated, restoring the interrupt flag before rethrowing can fit the caller's contract; if stopping via another approach, that policy must be clearly defined.

`shutdownNow()` typically uses `Thread.interrupt()` as a signal. If a task ignores interrupts, is blocked on a non-interruptible operation, or sits in an infinite loop, it can still keep running. Do not assume a single `shutdownNow` is an absolute "kill task".

### Cancellation Inside Tasks

A task cooperating with interrupts:

```java
Runnable task = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            performOneUnitOfWork();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        cleanupOwnedResources();
    }
};
```

This is **illustrative code**: `performOneUnitOfWork()` may throw `InterruptedException`, and `cleanupOwnedResources()` must be defined. A task should not catch `InterruptedException` and keep looping forever, causing shutdown to hang. With `Future.cancel(true)`, the caller requests an interrupt; how quickly the task stops depends on the code and where it is blocked.

**Note:** `Future.get(timeout)` only times out for **the waiting caller**; it **does not automatically call `cancel(true)`**. If you want to cancel after a deadline, the caller must design the cancellation action and handle the result.

## 11. Common Deadlock When a Task Waits on Another Task in the Same Pool

An executor can deadlock without two nested locks. For example, a worker is running task A, A submits task B to **the same single-thread executor**, and then A calls `Future.get()` to wait for B.

```java
// Incorrect illustration: running this snippet with a single-worker pool.
ExecutorService pool = Executors.newSingleThreadExecutor();
pool.submit(() -> {
    Future<Integer> other = pool.submit(() -> 42);
    return other.get(); // A waits for B; B has no worker available to run.
});
```

This illustrative snippet requires `java.util.concurrent` imports, and if run as-is it risks **hanging**; do not use it as a runnable practice program. Task A holds the only worker and waits for B; B is queued and needs that worker, creating a **thread starvation deadlock**.

Increasing the pool size sometimes avoids a specific case, but it is not a sufficient solution if the dependency graph can be deeper or all workers block simultaneously. Proper solutions include:

- Do not wait on a dependent task's `Future` on **the same finite-worker executor**.
- Structure the computation as a single larger task when concurrency is not needed.
- Use appropriate completion orchestration, or a separate pool with designed capacity.
- Avoid blocking calls inside workers when they need that same pool to make progress.
- Set timeouts/cancellation on waiting points and monitor active/queued tasks.

Another pattern: N workers in a pool simultaneously call `BlockingQueue.put` on a full queue, while the consumer task needs to run on **that same exhausted pool**. Workers do not release their slots, and the consumer never gets CPU/a worker → hang. When designing a pipeline, you must consider both the executor work queue and business data queues.

## 12. Long-Running Tasks and a Shared Pool

If very short tasks are mixed with tasks that block on the network for several minutes in a small pool, short tasks can suffer starvation or high latency even though they need very little CPU.

### How to Separate Workloads

- **CPU executor:** moderate worker count based on available CPUs, avoiding long blocking I/O.
- **I/O executor:** bounded concurrency/queue aligned with connection pools and downstream capacity.
- **Scheduled executor:** delayed/periodic tasks use `ScheduledExecutorService`/`ScheduledThreadPoolExecutor` instead of calling `Thread.sleep()` in regular workers.
- **Single-thread owner:** commands that must execute sequentially for invariants can use `newSingleThreadExecutor()`, but backlog and shutdown must still be controlled.

You do not always need many pools; splitting into too many pools complicates lifecycle management and wastes resources. Separate them when SLAs, wait types, scalability, or state ownership genuinely differ.

### `Executors` Factory Methods and Default Risks

| Factory | Key Behavior | What to Watch Out For |
|---|---|---|
| `newSingleThreadExecutor()` | One worker processes tasks sequentially; worker is replaced on failure per contract | Queue can grow large; not bounded admission |
| `newFixedThreadPool(n)` | Fixed number `n` of workers, reused | Default work queue **has no small hard bound**, can build up backlog |
| `newCachedThreadPool()` | Reuses idle workers and creates more on demand | Can create very many platform threads under bursts; must consider limits |
| `newScheduledThreadPool(n)` | Delayed and periodic tasks | Different queue/timer policy; an exception in a periodic task can stop subsequent runs |
| `newWorkStealingPool()` | Based on `ForkJoinPool`, work-stealing | No execution order guarantee; not equivalent to a traditional FIFO pool |
| `newSingleThreadScheduledExecutor()` | One worker for sequential scheduling | Long tasks delay subsequent runs |

**Important:** `newFixedThreadPool(n)` only bounds the worker count, **not the practical number of waiting tasks** to a small capacity. When producers are faster than consumers, the work queue can accumulate huge numbers of tasks and consume RAM. If you need a bounded queue + explicit rejection policy, use `ThreadPoolExecutor` with an explicit constructor.

## 13. `ThreadFactory` and Thread Observability

`ThreadFactory` determines how new workers are created. It can be used to:

- Name threads for easy diagnostics, such as `image-worker-1`, `image-worker-2`.
- Set an `UncaughtExceptionHandler` for uncaught errors (does not replace reading exceptions from `Future`).
- Set daemon/thread priority according to a verified policy.
- Create workers with the appropriate context/class loader/thread group for the environment.

Java 17 example:

```java
AtomicInteger sequence = new AtomicInteger();
ThreadFactory factory = runnable -> {
    Thread t = new Thread(runnable,
            "image-worker-" + sequence.incrementAndGet());
    t.setDaemon(false);
    return t;
};
```

This is a code snippet placed inside a method with imports `java.util.concurrent.ThreadFactory` and `java.util.concurrent.atomic.AtomicInteger`.

**Do not choose `daemon=true` just so the JVM exits on its own** if important work is unfinished. Daemon threads can be terminated when the JVM exits without guaranteeing data flushes/state commits. The resource owner must still shut down and await completion according to the contract.

A `ThreadFactory` can refuse to create a thread (for example, returning `null` in certain situations); the pool class handles worker creation per API behavior. For production, custom factories should be tested under low-resource conditions or invalid configurations.

## 14. Memory Visibility and the Java Memory Model

The Executor Framework is not just a task queue; Java's concurrency APIs define memory consistency rules so data is safely published between threads.

Common relationships:

1. Actions in a thread prior to **submitting** a `Runnable`/`Callable` to an `ExecutorService` *happen-before* actions inside that task.
2. Actions inside the task *happen-before* actions in another thread **after `Future.get()` successfully retrieves the result**, per the API contract.
3. For `Executor.execute`, the API documentation describes memory consistency between actions prior to submitting a `Runnable` and the start of its execution.
4. Relationships from `Thread.start`, `join`, `volatile`, locks, and queues still apply if the program uses additional coordination mechanisms.

Example:

```java
// Illustration inside a method, with an existing ExecutorService service:
int[] data = {10, 20};
Future<Integer> task = service.submit(() -> data[0] + data[1]);
System.out.println(task.get()); // 30 if there is no competing mutation
```

This is illustrative code; the method must declare/handle checked exceptions. If `main` prepares `data` before `submit` and **does not mutate it concurrently**, the worker can see the prepared data per the memory consistency contract; after `get()`, `main` receives the correct result.

**However:** submission does not make subsequent mutations safe automatically. If `main` modifies `data[0]` while the worker is reading it, separate synchronization/ownership is still required. Returning a value from a task does not automatically make mutable objects it returns immutable.

### `Future.get` and Visibility Do Not Fix Work Atomicity

If two tasks both perform `counter++` on a plain `int` without synchronization, having `main` wait for both via `Future.get()` **does not prevent lost updates**. `get()` is only a completion/visibility boundary between the task and the caller; updates between the two workers may have already raced earlier.

Fix this using:

- `AtomicInteger.incrementAndGet()` for an independent counter.
- `synchronized`/`Lock` for multi-step invariants.
- Task-local accumulators merged after `Future.get()`.
- Immutable messages/ownership transfer when you want to avoid shared mutable state.

## 15. Metrics: Observing the Pool with Accurate Semantics

`ThreadPoolExecutor` provides observability APIs such as:

```java
int core = pool.getCorePoolSize();
int max = pool.getMaximumPoolSize();
int current = pool.getPoolSize();
int active = pool.getActiveCount();
int queued = pool.getQueue().size();
long completed = pool.getCompletedTaskCount();
```

This is an **illustrative snippet inside a method** where `pool` is a `ThreadPoolExecutor`.

Metrics used for monitoring:

- **Active count:** number of workers executing tasks at the time of observation (some counts are approximate).
- **Pool size:** total number of workers currently present.
- **Queue depth:** number of waiting tasks, excluding currently executing tasks.
- **Completed tasks:** number of tasks completed at the executor level; **does not mean the business operation succeeded**.
- **Rejection count:** usually needs to be tracked in the rejection handler because there is no standard built-in "rejected task counter" across all executors.
- **Task wait time:** time from submission to start (if instrumented), distinct from execution time.
- **Task execution time, queue age, and end-to-end latency:** help identify whether the bottleneck is at task admission, workers, or downstream.

Some getters use snapshots/approximations and can change immediately after being read. **Do not check `getQueue().size()` and assume the next task is guaranteed to be accepted**, because concurrent submissions/completions can change the queue. Do not call `getQueue().clear()` as a "normal throttling mechanism": it affects already-accepted tasks and can leave `Future`s never completing as callers expect.

### Thread Dumps and JFR

When suspecting pool congestion:

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process ID. Inspect whether workers are running, waiting on the queue, blocked on a monitor, or waiting on network/DB. `WAITING (parking)` on an idle worker can be **normal** and does not mean deadlock.

For sufficiently long workloads, JFR helps inspect thread park events, contention, and hot spots depending on JVM/recording settings. Observing thread states is only a snapshot; it must be combined with queue depth, task latency, retries/rejections, and business SLAs.

## 16. Key Decisions Before Tuning a Pool

When preparing an executor for production, clearly answer:

1. **What are the tasks?** CPU-bound, I/O-bound, long-running, periodic, or with external side effects?
2. **How does load arrive?** Average, bursts, peak concurrency, and ability to throttle upstream?
3. **What latency/throughput SLOs must be met?** Does queue wait time count toward the deadline?
4. **Memory limits?** How many references/payloads does each queued task hold; how much capacity is needed?
5. **What is downstream capacity?** DB connections, HTTP pools, API quotas, disk throughput?
6. **Can tasks be rejected/dropped?** If not, do you need durability/retry/idempotency mechanisms?
7. **What are the cancellation rules?** Deadlines, interrupts, retries, and rollback/compensation?
8. **Where are exceptions observed?** `Future`, `CompletionService`, logging/metrics, error channels?
9. **Who owns the executor?** Who is allowed to shut it down and when? Do not let an arbitrary service shut down a shared pool.
10. **Are there task-to-task dependencies?** Does a task call `Future.get` on another task in the same pool?
11. **Is there shared mutable state?** Task submission does not replace synchronization of the state itself.
12. **Are there metrics and overload tests?** Testing with only two lightweight tasks does not reveal behavior when the queue is full.

Tuning is meaningful only after acceptance semantics and lifecycle are clearly defined. Increasing thread count to reduce queue depth can overload downstream systems and increase errors; reducing threads to save CPU can cause starvation for interdependent tasks.

## 17. When Do You Need `CompletionService`, `ScheduledExecutorService`, or `ForkJoinPool`?

These three APIs are related to the Executor Framework, but **do not change the meaning of the three main levels**:

### `ExecutorCompletionService<V>`

If you submit multiple `Callable`s and want to retrieve results **in completion order**, `ExecutorCompletionService` wraps an `Executor`/`ExecutorService` and provides a completion queue of `Future`s. This differs from calling `future1.get()` then `future2.get()` in input order: a slow `Future` at the front can block the caller even when other `Future`s have already finished.

### `ScheduledExecutorService`

Used to run tasks after a delay or periodically:

- `schedule`: run once after a delay.
- `scheduleAtFixedRate`: schedule based on a periodic start interval.
- `scheduleWithFixedDelay`: wait a fixed delay after the previous execution finishes.

Periodic executions can be delayed when workers are busy; there is no absolute real-time guarantee. An exception from one periodic execution can stop subsequent runs per contract, so `Future`/results must be monitored.

### `ForkJoinPool`

Suited for divide-and-conquer tasks and work-stealing, especially when a problem has a fork/join structure. It has its own queue/scheduling semantics; do not assume it guarantees FIFO like a fixed thread pool using `LinkedBlockingQueue`. Long blocking I/O inside fork/join workers may require special design and blocking management.

This article focuses on `Executor`, `ExecutorService`, and `ThreadPoolExecutor`; the APIs above are complementary options when requirements fit.

## 18. Java 21+ Virtual Threads and Important Differences

Starting in Java 21, virtual threads allow creating many Java threads that are lighter than platform threads for many blocking I/O workloads. The API `Executors.newVirtualThreadPerTaskExecutor()` creates **a new virtual thread per task**, not a fixed pool of virtual threads with `corePoolSize/maximumPoolSize`.

- Java 17 **does not have stable virtual thread support** like Java 21; the main examples in this article use platform threads and run on JDK 17.
- Do not mechanically apply "platform thread pool sizing" thinking to a virtual-thread-per-task executor. To limit concurrent DB requests or API calls, use an appropriate `Semaphore`/rate limiter/connection pool.
- Virtual threads **do not** eliminate data races, shared mutable state, timeouts, or backpressure.
- For CPU-bound tasks, creating countless virtual threads does not exceed physical CPUs; you still need to measure the workload.

Check API availability by **JDK version** before copying code: `newVirtualThreadPerTaskExecutor()` does not compile with `--release 17`.

## 19. Common Mistakes and Fixes

1. **"Executor.execute always creates a new thread."** False: an implementation can run synchronously in the caller, such as a direct executor.
2. **"Executor and ExecutorService are identical."** False: `ExecutorService` adds `submit`, `Future`, and lifecycle/coordination APIs.
3. **"newFixedThreadPool(n) automatically limits all backlog to n."** False: `n` is the worker count; the queue can grow very large.
4. **"maximumPoolSize is the number of workers always created when there are many tasks."** False: pools usually enqueue first after reaching core; an unbounded queue leaves max rarely used.
5. **"shutdown waits for all tasks to finish."** False: `shutdown` stops accepting new tasks; wait using `Future`/`awaitTermination`.
6. **"shutdownNow kills all tasks immediately."** False: it usually only requests interrupts; tasks must cooperate.
7. **"Future.isDone means the task succeeded."** False: the task may have failed or been cancelled.
8. **"future.get(timeout) automatically cancels on timeout."** False: `get` timing out does not cancel the task.
9. **"Exceptions in submit automatically print stack traces like execute."** You cannot rely on that; task failures are held in the `Future`.
10. **"CallerRunsPolicy always throws an error on rejection."** False: it usually runs in the caller if the pool is not shut down; once shut down, it may drop the task.
11. **"DiscardPolicy still processes the task another way."** False: it drops the task; only use when losing work is acceptable.
12. **"Using an unbounded workQueue won't run out of memory."** False: backlog can grow to OOM under excessive load.
13. **"Tasks are independent because they run in a pool."** False: shared mutable fields can still race.
14. **"Calling Future.get after two tasks update the same counter guarantees the right total."** False: `get` provides completion/visibility, not atomicity against lost updates between workers.
15. **"A single-worker thread pool cannot deadlock."** False: a running task can wait on another task that can only be run by that single worker.
16. **"getQueue().size() == 0 means all tasks are finished."** False: tasks may still be running.
17. **"High pool activeCount means CPU is always overloaded."** False: workers may be blocked on I/O; check CPU/stacks/latency.
18. **"Setting daemon=true is enough to replace shutdown."** False: important work can be lost when the JVM exits.
19. **"Increasing max threads always increases throughput."** False: downstream bottlenecks, context switching, and GC can worsen.
20. **"ThreadFactory replaces error handling."** False: failures in `submit` are typically stored in the `Future`.
21. **"Any method can shut down an injected/shared executor."** Wrong ownership: the lifecycle owner must be defined so other users are not broken.
22. **"Having a thread pool gives tasks automatic timeouts."** No: deadlines must be designed into `Future`, I/O operations, cancellation, and queue admission.

## 20. Review Questions and Answers

**Q1.** Is `Executor` required to run tasks on another thread?  
**Answer:** No. It only defines the `execute(Runnable)` interface; an implementation may run directly in the caller.

**Q2.** Why do you need `ExecutorService` instead of `Executor` if you want to receive a computation result?  
**Answer:** `ExecutorService.submit(Callable<T>)` returns a `Future<T>`, on which you can call `get()` to wait for the result and catch exceptions/cancellation.

**Q3.** Does `ExecutorService.shutdown()` wait for running tasks to finish?  
**Answer:** No. It stops accepting new tasks; to wait, you must use `Future`/`awaitTermination`.

**Q4.** Pool `core=2`, `max=8`, very large queue: why might it only use 2 workers even with many tasks?  
**Answer:** Once core is reached, `ThreadPoolExecutor` prioritizes enqueueing before growing workers; if a large queue still accepts tasks, it generally does not need to create workers beyond core.

**Q5.** Pool `core=max=1`, queue capacity=1. Worker is busy, queue holds one task, a third task arrives: what happens with `AbortPolicy`?  
**Answer:** The new task is rejected with `RejectedExecutionException`. This is the scenario in the main example.

**Q6.** How does `CallerRunsPolicy` help with backpressure?  
**Answer:** When the pool is still active but saturated, the task can run directly in the thread calling `execute`, slowing down the caller and reducing submission rate. Watch out for thread-affinity/context and shutdown behavior.

**Q7.** A `submit` task throws `IllegalStateException`; what does the caller see from `future.get()`?  
**Answer:** `ExecutionException` with the task's exception as its cause (unless cancelled or interrupted per contract).

**Q8.** If `Future.get(100, MILLISECONDS)` throws `TimeoutException`, has the task definitely stopped?  
**Answer:** No. The timeout only ends the waiting call; the task may still be running.

**Q9.** A task in a single-thread pool submits a second task to the same pool and calls `get`; why is this dangerous?  
**Answer:** The first task holds the only worker and waits for the second task; the second task is queued and cannot run, which can deadlock.

**Q10.** Can you call `Future.get` after two tasks do `counter++` without synchronization and assume the total is accurate?  
**Answer:** No. `Future.get` guarantees completion/visibility on the caller side, but does not make counter updates between workers atomic.

**Q11.** Does `getQueue().size() == 0` prove the executor has finished processing all tasks?  
**Answer:** No; currently running tasks are not in the queue. Use `Future`s, termination status, and application-level completion.

**Q12.** Why shouldn't you use `newCachedThreadPool()` unchecked for a source with large bursts?  
**Answer:** It can create many platform threads when no workers are idle; you need admission/rate limits matched to resources.

**Q13.** When a task has a business error, does `getCompletedTaskCount()` distinguish success?  
**Answer:** Do not treat it as a success counter. It only measures completion at the executor level; separate business result/error metrics are needed.

**Q14.** With many independent CPU-bound tasks, is increasing workers to 10x the CPU count guaranteed to be faster?  
**Answer:** No. Scheduling overhead, cache contention, and resource bottlenecks can degrade performance; measure with a representative workload.

**Q15.** To have a bounded task backlog where tasks are explicitly rejected under overload, what should you configure?  
**Answer:** A `ThreadPoolExecutor` with core/max limits, a work queue with an explicit capacity, and a handler like `AbortPolicy`, with the caller handling rejection.

## 21. Checklist for Applying to Real Code

Before putting an executor into an application, verify:

- **Ownership:** which component creates the pool, who is allowed to submit, and who must shut it down?
- **Semantics:** do tasks require ordering, results, deadlines, retries, or idempotency?
- **Worker limits:** are core/max reasonable for CPUs and downstream resources?
- **Queue capacity:** is there a practical hard bound for bursts and memory budget?
- **Rejection:** will rejected tasks error out, retry, persist durably, or drop per contract?
- **Completion:** does the caller observe exceptions from `Future` or an explicit error channel?
- **Cancellation:** are interrupts respected, do I/O calls have timeouts, and do tasks clean up?
- **Deadlock:** does a task wait on another task in the same pool? Can producer/consumer stall due to lack of workers?
- **Visibility:** is data properly prepared before `submit`, and is shared mutable state inside tasks synchronized?
- **Monitoring:** are queue age, active workers, completed/failures, rejections, latency, and CPU collected?
- **Shutdown:** tested when the service exits with queued/running tasks and when interrupted?
- **Version:** are the classes/APIs used available in the target deployment JDK (especially new APIs from Java 21+)?

When answers are unclear, a simple configuration that is **bounded and fails loudly** is usually easier to operate than a huge pool with no rejection/timeouts.

## 22. Official References

- [Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): `execute` and memory-consistency properties.
- [Java SE 17 — ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `invokeAll`, `invokeAny`, lifecycle.
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): configuring workers, queues, handlers, hooks, and metrics.
- [Java SE 17 — Executors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html): factory methods.
- [Java SE 17 — Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `get`, `cancel`, exceptions, and memory consistency.
- [Java SE 17 — Callable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Callable.html): result-returning task interface.
- [Java SE 17 — BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): queueing, blocking, capacity, and publication.
- [Java SE 17 — RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html): rejection contract.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): Java Memory Model and happens-before.

**Summary:** `Executor` is the "run a Runnable" contract; `ExecutorService` adds `Future` results and lifecycle management; `ThreadPoolExecutor` implements a pool with **worker limits + work queue + rejection policy**. To apply it properly, do not only pick a thread count: you must control **backlog, workload type, errors, cancellation, shutdown, shared state, and memory visibility relationships**. A good thread pool is not the largest pool, but one with clear behavior under both normal load and overload.