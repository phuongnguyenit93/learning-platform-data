# ForkJoinPool.commonPool() and Shared Tasks in Java

> **Core idea:** `ForkJoinPool.commonPool()` returns a **shared Fork/Join executor within the same JVM**, rather than creating a separate pool for each call or module. Multiple `ForkJoinTask` instances, asynchronous `CompletableFuture` operations that do not specify an executor (under the default rule), and many parallel-stream computations may all share this execution infrastructure. Consequently, heavy CPU tasks or uncontrolled blocking in component A can slow down component B. It is important to distinguish between **pool sharing**, **worker sharing**, **data sharing**, and **resource isolation**: these are different concepts.

This article belongs to the **Fork/Join** group of **general Java concurrency**, using Java SE 17+. It does not use or analyze Spring.

## 1. What is the common pool and why does it exist?

`ForkJoinPool` implements `ExecutorService` and is designed for work that can be split (*fork*) and then combined (*join*). Its implementation uses a **work-stealing** mechanism so that an idle worker can take over some work from another worker. This is especially useful for divide-and-conquer algorithms, such as summing array segments, processing trees, or certain parallel computations.

Since Java 8, the JDK has provided a process-wide global pool:

~~~java
// API snippet — add imports and place inside a class/method when using.
ForkJoinPool pool = ForkJoinPool.commonPool();
~~~

Calls to `commonPool()` in a typical application receive the same instance. That reduces the need to create a dedicated new pool for every small task, but it also means **multiple components share the same resource**.

~~~text
                  SAME JVM
Module A ── ForkJoinTask ──────────┐
Module B ── CompletableFuture ─────┼──> ForkJoinPool.commonPool()
Module C ── parallel stream ───────┘             │
                                                ▼
                                         Shared workers
                                        [task A, task B, task C]
~~~

This is a conceptual diagram. It does not guarantee that every `CompletableFuture` call site or every stream operation always runs on a common-pool worker in **every configuration**, because default execution has exceptions and the caller thread can also participate.

**Sharing scope:** within a single JVM, not a distributed pool across multiple JVMs. The common pool does not create separate quotas for each library, request, or tenant.

### What the common pool does NOT provide

- It does not have a single global lock that automatically protects business objects.
- It does not automatically make `HashMap`, `ArrayList`, or mutable counters thread-safe.
- It does not guarantee that a task submitted earlier will finish earlier.
- It does not guarantee deadlines/p99 latency or dedicated resources for your module.
- It does not create additional CPUs merely through work-stealing.
- It does not allow an individual component to shut down the shared pool when that component finishes.
- It does not automatically cancel/roll back side effects when the caller gives up.

## 2. Work-stealing and how to use `fork`/`join`

A Fork/Join worker has queued tasks waiting; another idle worker can steal tasks from that worker. The typical algorithm:

1. A branch that is too large is split into two smaller subproblems.
2. `fork()` one branch so the pool can execute it.
3. The current worker processes the remaining branch via `compute()`.
4. Call `join()` on the forked branch to obtain its result.
5. Combine the results into the parent branch's value.

~~~text
                           SumTask(0..8)
                         /               \
                 SumTask(0..4)       SumTask(4..8)
                    /     \              /     \
                 leaf     leaf        leaf     leaf
                    \     /              \     /
                   merge                 merge
                         \               /
                           final result
~~~

Work-stealing does not mean each leaf is always executed by a different thread. With small data or few CPUs, many branches may run sequentially. Nor is there any guarantee that the order of forking, stealing, or completion matches the order in the source code.

### ForkJoinTask and Future

`ForkJoinTask<V>` implements `Future<V>` and adds the `fork()`, `join()`, and `invoke()` APIs. `join()` uses Fork/Join's waiting/joining mechanism; `Future.get()` has a contract with checked exceptions such as `InterruptedException` and `ExecutionException`. When a task throws an exception, `join()` may rethrow an unchecked exception/Error; do not treat it like `Future.get()` with respect to exception types.

For subtasks within the same `ForkJoinPool`, the `fork / compute / join` pattern is the framework's strength. Do not generalize that arbitrary `Future.get()`, network calls, or blocking I/O will all be handled safely by work-stealing.

## 3. Example 1 — two calls return the same common pool

Create `CommonPoolIdentity.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;

public class CommonPoolIdentity {
    public static void main(String[] args) {
        ForkJoinPool a = ForkJoinPool.commonPool();
        ForkJoinPool b = ForkJoinPool.commonPool();

        System.out.println("same instance = " + (a == b));

        ForkJoinTask<Integer> task = a.submit(() -> 6 * 7);
        System.out.println("answer = " + task.join());

        System.out.println("still shared = "
                + (b == ForkJoinPool.commonPool()));
    }
}
~~~

Run:

~~~bash
javac CommonPoolIdentity.java
java CommonPoolIdentity
~~~

Normal stdout:

~~~text
same instance = true
answer = 42
still shared = true
~~~

`a` and `b` point to the same executor instance. `ForkJoinTask<Integer>` waits for the value `42` to be computed. The program **does not call `shutdown()`** on the common pool: it is not a resource privately owned by the `main` method.

## 4. Example 2 — divide-and-conquer RecursiveTask and merging results

Create `CommonPoolSum.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class CommonPoolSum {
    private static final class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2;

        private final int[] values;
        private final int from;
        private final int to;

        SumTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long total = 0;
                for (int i = from; i < to; i++) {
                    total += values[i];
                }
                return total;
            }

            int mid = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, mid);
            SumTask right = new SumTask(values, mid, to);

            left.fork();
            long rightResult = right.compute();
            long leftResult = left.join();

            return leftResult + rightResult;
        }
    }

    public static void main(String[] args) {
        int[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        long sum = ForkJoinPool.commonPool().invoke(
                new SumTask(numbers, 0, numbers.length));
        System.out.println("sum = " + sum);
    }
}
~~~

Compile/run:

~~~bash
javac CommonPoolSum.java
java CommonPoolSum
~~~

Output:

~~~text
sum = 36
~~~

The leaves read disjoint elements of `numbers` and return local values. There is no `long sharedTotal` updated by multiple workers via `sharedTotal += ...`, so there are no lost updates. The results are combined via `leftResult + rightResult` after both branches have produced their results.

`THRESHOLD=2` is only to make recursion easy to observe. In real workloads, a threshold that is too small creates too many tasks and overhead; a threshold that is too large leaves too few branches able to run in parallel. Benchmark before choosing.

**Note:** If leaves concurrently write to an unsynchronized `ArrayList` or mutate a shared mutable object, Fork/Join **does not automatically protect that data**. Prefer reducing over immutable values, partitioning separate outputs and then merging, or applying synchronization that preserves the invariant.

## 5. Two clients sharing a pool can interfere with each other

A module using the common pool does not own all of its workers. When module A submits many CPU-heavy tasks, module B—which also uses the common pool—may have to wait for an idle worker, even if B only has a few short tasks. This is the **noisy neighbor** phenomenon within a single JVM.

~~~text
Normal load:
    workers: [A] [B] [idle] [idle]
    task B has a chance to be processed early

When A creates many CPU tasks:
    workers: [A] [A] [A] [A]
    B's tasks may have to wait depending on scheduling
    B's latency may increase
~~~

This is an illustrative model, not a guaranteed worker count or outcome. Work stealing helps distribute work, but **does not guarantee** deadlines or per-module fairness.

### Example 3 — two components submitting to the same resource

Create `SharedClientsDemo.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;

public class SharedClientsDemo {
    private static final class ClientA {
        static ForkJoinTask<String> submit() {
            return ForkJoinPool.commonPool().submit(() -> "A");
        }
    }

    private static final class ClientB {
        static ForkJoinTask<String> submit() {
            return ForkJoinPool.commonPool().submit(() -> "B");
        }
    }

    public static void main(String[] args) {
        ForkJoinTask<String> a = ClientA.submit();
        ForkJoinTask<String> b = ClientB.submit();

        System.out.println("results = " + a.join() + b.join());
        System.out.println("same executor = "
                + (ForkJoinPool.commonPool() == ForkJoinPool.commonPool()));
    }
}
~~~

Run:

~~~bash
javac SharedClientsDemo.java
java SharedClientsDemo
~~~

Stdout:

~~~text
results = AB
same executor = true
~~~

The output `AB` is because **`main` concatenates the results in the order `a.join() + b.join()`**; it does not prove that task A ran before task B. The two tasks can execute in a different order. This program demonstrates instance sharing, without trying to turn a single stress run into a scheduling guarantee.

## 6. CompletableFuture and the default async executor

In Java 17, methods such as `CompletableFuture.supplyAsync(supplier)` and `runAsync(runnable)` **without an explicit executor** typically use `ForkJoinPool.commonPool()` as the default asynchronous execution facility.

**Important exception in the Java 17 API:** If the common pool **does not support a parallelism of at least 2**, the implementation may create **a new Thread for each async task**. Therefore, do not write tests requiring every `supplyAsync` call to always execute on a thread named `ForkJoinPool.commonPool-worker-...`.

Distinguish the method forms:

~~~java
// Snippets, not a standalone program.
CompletableFuture<Integer> a =
        CompletableFuture.supplyAsync(() -> 21);

CompletableFuture<Integer> b =
        CompletableFuture.supplyAsync(() -> 21, dedicatedExecutor);

CompletableFuture<Integer> c =
        a.thenApply(x -> x * 2);

CompletableFuture<Integer> d =
        a.thenApplyAsync(x -> x * 2, dedicatedExecutor);
~~~

- `a` uses the default async facility, usually the common pool.
- `b` specifies a dedicated executor, not relying on the default facility for **that stage**.
- `c` is a synchronous continuation, which may run on the thread that completed the previous stage or on the caller thread depending on timing; do not assume a fixed thread.
- `d` specifies an executor for the asynchronous continuation.

When you want to isolate an entire pipeline, audit **every async continuation**: specifying an executor on the initial `supplyAsync` while subsequently calling `thenApplyAsync` without an executor can cause later stages to fall back to the default facility.

### Example 4 — default facility and explicit Executor

Create `CompletableFuturePools.java` (Java 17+):

~~~java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class CompletableFuturePools {
    public static void main(String[] args) throws InterruptedException {
        ExecutorService dedicated = Executors.newFixedThreadPool(2);

        try {
            CompletableFuture<Integer> defaultTask =
                    CompletableFuture.supplyAsync(() -> 20);

            CompletableFuture<Integer> explicitTask =
                    CompletableFuture.supplyAsync(() -> 22, dedicated);

            System.out.println("sum = "
                    + (defaultTask.join() + explicitTask.join()));
        } finally {
            dedicated.shutdown();
            if (!dedicated.awaitTermination(10, TimeUnit.SECONDS)) {
                dedicated.shutdownNow();
            }
        }

        System.out.println("dedicated shutdown = "
                + dedicated.isShutdown());
    }
}
~~~

Run:

~~~bash
javac CompletableFuturePools.java
java CompletableFuturePools
~~~

Stdout:

~~~text
sum = 42
dedicated shutdown = true
~~~

The result does not depend on the execution order of the two tasks. The explicitly created pool is a **module-owned resource** that must be shut down; the common pool does not need to be—and should not be—shut down by this code.

`newFixedThreadPool(2)` is used here to illustrate **ownership/isolation**, not as a production-safe configuration under overload: this factory typically uses an unbounded queue. With rate-unbounded producers, you need a bounded queue and appropriate backpressure/rejection policies.

## 7. Parallel streams can also share the Fork/Join infrastructure

`stream.parallel()` or `parallelStream()` triggers parallel evaluation of elements when a terminal operation runs. In common JDK implementations, parallel streams involve the common Fork/Join infrastructure; **the thread invoking the terminal operation may also participate**.

The resulting value can be deterministic for pure reductions, but the worker assignment and completion timing of individual elements are not fixed.

### Example 5 — parallel reduction with a stable result

Create `ParallelStreamSum.java` (Java 17+):

~~~java
import java.util.stream.IntStream;

public class ParallelStreamSum {
    public static void main(String[] args) {
        long sum = IntStream.rangeClosed(1, 100)
                .parallel()
                .mapToLong(x -> x)
                .sum();

        System.out.println("sum = " + sum);
    }
}
~~~

Run:

~~~bash
javac ParallelStreamSum.java
java ParallelStreamSum
~~~

Stdout:

~~~text
sum = 5050
~~~

Summing `long` over 1..100 does not overflow and is a pure reduction. Even if element splitting order varies, the sum remains `5050`. By contrast, `parallel().forEach(System.out::println)` has non-deterministic output order.

**Unsafe counterexample** (snippet, not a standalone program):

~~~java
List<Integer> results = new ArrayList<>();
IntStream.range(0, 1_000).parallel().forEach(results::add);
~~~

`ArrayList` is not thread-safe for concurrent writers. Use an appropriate collector/reduction or a data structure/synchronization protocol that satisfies the invariant, rather than replacing a `for` loop with `parallel()` and ignoring races.

### Parallel is not automatically faster

- Too little data: splitting/joining overhead exceeds computation cost.
- Too little work per element: not enough CPU work to amortize overhead.
- Blocking calls: sharing the pool can reduce throughput and interfere with other modules.
- Stateful operations/shared locks: contention/serialization.
- Memory allocations/GC: branches allocate many intermediate objects.
- CPU cores limited by containers or other processes.

Measure the actual workload before using parallel streams, especially in libraries serving multiple requests.

## 8. Shared pool + blocking I/O: a hard-to-trace cause of latency

Fork/Join works best for **computational** tasks that can be decomposed and coordinated. When a worker is blocked on long network/database/file I/O or waiting on a latch that no worker can release, the pool loses the ability to use that worker for other tasks.

~~~text
commonPool workers:
  W1 -> blocking HTTP
  W2 -> blocking database
  W3 -> blocking wait
  W4 -> CPU work

Tasks from another module on the same pool:
  may have to wait, increasing queueing delay and p99 latency
~~~

Calling `CompletableFuture.supplyAsync(() -> blockingRemoteCall())` does not turn `blockingRemoteCall()` into non-blocking I/O. It only offloads the computation asynchronously with respect to the caller; **a worker can still be blocked**.

Options when the workload is predominantly blocking I/O:

- Use a **dedicated ExecutorService** for I/O, with bounded workers/in-flight limits and timeouts.
- Front the queue with bounded admission or an explicit rejection/backpressure policy.
- Apply connect/read/request timeouts and cooperative cancellation where feasible.
- Minimize holding locks across I/O; do not wait for a task that needs the same lock.
- Use true asynchronous/non-blocking I/O when supported by the library.
- When blocking inside a ForkJoin worker is unavoidable, consider `ForkJoinPool.ManagedBlocker` and its limitations.

**Do not** simply increase common-pool parallelism to fix every issue: DB connection pools, API rate limits, sockets, and CPUs still have limits. More threads can sometimes worsen contention/GC.

## 9. ManagedBlocker: notifying ForkJoinPool of a wait

`ForkJoinPool.ManagedBlocker` has two methods:

- `isReleasable()`: returns true if execution can proceed without blocking.
- `block()`: performs the wait (if needed) and returns true when progress can be made.

When `ForkJoinPool.managedBlock(blocker)` is called from a ForkJoin worker, the pool may attempt to **compensate** for the blocked worker by adjusting workers under certain conditions. This **does not** guarantee a replacement thread will always be created, does not turn I/O into non-blocking I/O, and does not guarantee deadlines.

Java 17+ snippet illustrating the idea (not a standalone program; the `latch` variable at the call site needs an appropriate scope):

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;

final class LatchBlocker implements ForkJoinPool.ManagedBlocker {
    private final CountDownLatch latch;

    LatchBlocker(CountDownLatch latch) {
        this.latch = latch;
    }

    @Override
    public boolean isReleasable() {
        return latch.getCount() == 0;
    }

    @Override
    public boolean block() throws InterruptedException {
        latch.await();
        return true;
    }
}

// Inside a method that throws InterruptedException:
ForkJoinPool.managedBlock(new LatchBlocker(latch));
~~~

Do not treat `ManagedBlocker` as a “command to spawn unlimited workers”; resource limits still exist, and if nothing ever signals the latch, the worker can still wait forever. In many applications, isolating I/O into a dedicated executor with explicit capacity is easier to control.

## 10. Nested waits and thread starvation

Not every wait operation is supported by Fork/Join the way `ForkJoinTask.join()` is in a recursive algorithm.

Dangerous situation:

~~~text
Task A holds lock L and waits for task B's Future.
Task B needs lock L to complete.
A waits for B; B waits for A to release L -> potential deadlock.
~~~

Or a group of tasks occupies all workers and then waits for an external event produced by tasks **waiting** to be scheduled in the same executor. Work stealing can balance runnable tasks, but it cannot create forward progress for an unresolvable dependency cycle.

With `CompletableFuture`, consider expressing dependencies using `thenCompose`, `thenCombine`, and `allOf` instead of blocking with `join()`/`get()` inside every stage. However, **composition does not create additional CPUs/workers** and does not fix a downstream bottleneck; audit your executors and failure policies.

For recursive Fork/Join tasks, a pattern that is usually effective is `left.fork(); right.compute(); left.join();`, rather than forking every branch and blocking on all of them at every recursion level.

## 11. Common pool and lifecycle: do not shut down shared resources

`ForkJoinPool.commonPool()` is part of the JVM's shared infrastructure. According to the `ForkJoinPool` documentation, shutdown calls on the **common pool** have no effect the way they do on a user-created pool.

Consequences:

- Module A **cannot** rely on `commonPool().shutdown()` to stop only A's tasks.
- Module B may still be using the common pool.
- `awaitQuiescence(timeout, unit)` relates to the quiescent state of the **pool**, which can be affected by tasks from other clients; it is not “join all of my own tasks”.
- To manage your own tasks, keep `ForkJoinTask`/`Future` handles and await/cancel them according to an appropriate protocol.
- If you need to shut down workers when a module stops, create a **privately owned** pool, track its tasks, and shut it down.
- `ForkJoinPool` in Java 17 should not be written as an `AutoCloseable` with try-with-resources as in newer JDK versions; use explicit `shutdown`/`awaitTermination` when owning a pool.

### Example 6 — a dedicated pool that can be shut down

Create `DedicatedForkJoinPool.java` (Java 17+):

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;

public class DedicatedForkJoinPool {
    public static void main(String[] args) throws InterruptedException {
        ForkJoinPool owned = new ForkJoinPool(2);

        try {
            ForkJoinTask<Integer> first = owned.submit(() -> 3 * 3);
            ForkJoinTask<Integer> second = owned.submit(() -> 4 * 4);

            System.out.println("sum of squares = "
                    + (first.join() + second.join()));
        } finally {
            owned.shutdown();
            if (!owned.awaitTermination(10, TimeUnit.SECONDS)) {
                owned.shutdownNow();
            }
        }

        System.out.println("owned shutdown = " + owned.isShutdown());
        System.out.println("common still shared = "
                + (ForkJoinPool.commonPool() == ForkJoinPool.commonPool()));
    }
}
~~~

Run:

~~~bash
javac DedicatedForkJoinPool.java
java DedicatedForkJoinPool
~~~

Normal stdout:

~~~text
sum of squares = 25
owned shutdown = true
common still shared = true
~~~

The `owned` pool separates worker queues and has its own lifecycle. However, all pools in the same JVM still **compete for CPU, heap, GC, and OS resources**, so executor-level isolation does not equate to a dedicated CPU quota or hard real-time scheduling.

Do not create a new `ForkJoinPool` **per request**. A pool is typically created per component lifecycle, reused, monitored, and closed when there are no more users.

## 12. Parallelism, system properties, and JVM configuration

`ForkJoinPool.getCommonPoolParallelism()` returns the target parallelism of the common pool. In typical setups, the JDK chooses this level based on the number of processors visible to the JVM; the configuration may be affected by container/CPU quotas and JVM settings.

Some settings can be specified via system properties, for example:

~~~bash
java -Djava.util.concurrent.ForkJoinPool.common.parallelism=4 MyApplication
~~~

This is a syntax example, **not a recommendation to set 4 for every application**. The `ForkJoinPool` documentation also describes other properties related to the common-pool thread factory and exception handler.

Cautions:

1. Set the property **before the common pool is initialized**; calling `System.setProperty` afterward is not a way to resize an already-created pool.
2. Do not assume a fixed “cores minus one” formula across all JDKs/containers/settings.
3. Target parallelism is not a promise that the exact same number of workers is running at every moment.
4. Low parallelism can cause `CompletableFuture`'s default async facility to take the fallback path of creating new threads.
5. Excessively high parallelism can cause context switching or downstream overload.
6. Changing JVM-wide settings affects **all modules** using the common pool, not just the feature being tuned.

If tuning needs arise for only one workload, a **dedicated pool** is usually a clearer configuration boundary.

## 13. ThreadLocal and context when using shared workers

`ThreadLocal` binds data to the **current thread**; it does not automatically propagate state from the submitting thread to another worker.

~~~java
// Structural snippet, not a standalone program.
ThreadLocal<String> requestContext = new ThreadLocal<>();
requestContext.set("request-1");

ForkJoinPool.commonPool().execute(() -> {
    String observed = requestContext.get();
    // Must not assume observed == "request-1".
});
~~~

Some parallel-stream computations also use the caller thread as a participant, so relying on `ThreadLocal` for access decisions or business logic is even more likely to produce timing-dependent behavior.

When context is needed, prefer passing **immutable task inputs** containing the request ID, deadline, correlation ID, or required values. If you explicitly set a `ThreadLocal` on a worker, clean it up in `finally` and understand the implementation's inheritance/retention rules. Do not use a shared worker as per-request state storage.

Do not apply framework-specific request-context models here; this article discusses Java `ThreadLocal` in general.

## 14. ForkJoinTask cancellation has its own semantics

`ForkJoinTask` implements `Future`, but it is not a regular `FutureTask`. According to the Java 17 API, for the default `ForkJoinTask` implementation, the `mayInterruptIfRunning` parameter of `cancel(boolean)` **does not interrupt the worker in the way a reader might expect**; interruption is not the default mechanism for controlling `ForkJoinTask` cancellation.

Therefore:

- `task.cancel(true)` can mark the task as cancelled, but does not guarantee that a running body stops immediately.
- `isDone()` after cancel is a `Future` state, not proof that side effects/cleanup have completed.
- `CompletableFuture.cancel(true)` likewise **does not use the `mayInterruptIfRunning` parameter to control the computation** in the `CompletableFuture` implementation.
- If a long CPU computation must be stopped, design a **cooperative cancellation token**, such as an `AtomicBoolean` checked at safe points.
- For tasks with I/O, add I/O deadlines/timeouts; interrupting or cancelling does not automatically roll back a database.
- A task that has already sent an email, called a payment API, or written to a DB may still have side effects even if its `Future` is later cancelled.

Do not interpret “shared pool” as “no task can be cancelled”; you can still cancel **specific handles**, provided you understand each task type's semantics.

## 15. Observing and measuring the common pool

Some `ForkJoinPool` metrics:

| API | Meaning |
| --- | --- |
| `getCommonPoolParallelism()` | Shared target parallelism |
| `getParallelism()` | Instance target parallelism |
| `getPoolSize()` | Current number of workers, as a snapshot |
| `getActiveThreadCount()` | Estimate of active worker count |
| `getRunningThreadCount()` | Estimate of workers doing useful work per contract |
| `getQueuedTaskCount()` | Estimate of tasks in work queues |
| `getQueuedSubmissionCount()` | Estimate of pending external submissions |
| `getStealCount()` | Estimate of work-steal operations |
| `isQuiescent()` | Observes whether the pool is quiescent at the time of reading |
| `toString()` | Summary pool state for monitoring/debugging |

These values are observations/estimates and do not form an **atomically consistent snapshot** of the entire pool. `getQueuedTaskCount()==0` does not prove your module's tasks are all finished: they may still be running, waiting on an external resource, or sitting in the submission queue. Wait on the actual tasks' `join()`/`get()`/explicit acks.

### Diagnosing a noisy neighbor

Separate out:

- **Submission-to-start latency**: how long does a task wait to be scheduled?
- **Execution latency**: how long does the body run?
- **End-to-end latency**: includes both plus other overhead.
- **CPU saturation**: is CPU actually exhausted, or are workers mostly blocked?
- **GC/heap**: are queued tasks retaining large object graphs?
- **Blocking time**: network, DB, locks, latches, Future waits.
- **Queued submissions/tasks and steal count**: is there a backlog trend?
- **Failures/cancellation/timeouts**: is work lost or are useless tasks still running?
- **Concurrent modules**: does a spike in module A coincide with a p99 increase in B?

Do not infer root cause from a single call to `getActiveThreadCount()` or `getStealCount()`; measure trends, representative workloads, and other bottlenecks.

## 16. Proper benchmarking and testing

- First verify the **correctness** of the divide-and-conquer algorithm and shared-state invariants.
- Use sufficiently large inputs and a reasonable threshold; with inputs that are too small, fork overhead can dominate.
- Do not benchmark with a few ultra-short operations and conclude the common pool is “always faster”.
- Compare sequential, common pool, and dedicated pool on the same workload, checking throughput, p95/p99, and CPU.
- Measure blocking, GC, queueing, and downstream saturation together.
- Test with multiple modules under load to evaluate interference.
- Do not assume worker names or log ordering are always fixed.
- If testing a blocking workload, use a **dedicated pool and timeouts**, rather than trying to occupy all common-pool workers of the test suite.
- Close dedicated pools in `finally` and call `awaitTermination` with a timeout to avoid leaking live workers across tests.

### Deterministic tests

For `CommonPoolSum`, the output `sum=36` is an invariant; there is no need to guess which branch ran on which worker. For `SharedClientsDemo`, `results=AB` is only how two completed Futures are concatenated; it does not prove an A-before-B schedule.

For cancellation, `Future` state and **the body actually stopping** can differ; if you need to test body progress, use a separate latch/ack rather than assuming `isDone()` means cleanup is finished.

## 17. Common pool or dedicated pool?

### Use the common pool when

- Tasks are CPU-bound, relatively short, and splittable.
- There is no long blocking I/O or uncontrolled dependency cycle.
- Strict latency isolation between modules is not required.
- No separate executor shutdown tied to a component lifecycle is needed.
- Task volume and shared-memory invariants are clearly designed.
- Measured under real workloads when other libraries are active concurrently.

### Consider a dedicated pool when

- A feature has its own SLA/p99 and is sensitive to noisy neighbors.
- There is blocking I/O or per-downstream concurrency limits are needed.
- There are many recursive tasks and parallelism needs tuning per workload.
- You need a custom thread factory, monitoring, failure/rejection policy, or lifecycle.
- You want to actively shut down/cancel a module's tasks when the module stops.
- You need to test without affecting JVM-wide resources.

**Note:** A dedicated `ForkJoinPool` fits work-stealing computation; when the workload consists of many blocking I/O requests, a `ThreadPoolExecutor` with explicit sizing and a bounded queue may be more appropriate. A “dedicated pool” isolates work at the executor level, not CPU/heap/DB independently.

## 18. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “`commonPool()` creates a new pool each time.” | Multiple callers receive the same common pool instance |
| “The common pool allocates separate resources per library.” | Workers are shared; noisy neighbors can occur |
| “Fork/Join is FIFO by task submission.” | Work stealing does not guarantee completion order |
| “Fork/Join makes every object thread-safe.” | Shared mutable state still needs synchronization |
| “Splitting every element into a ForkJoinTask is always fast.” | Overhead and GC can exceed leaf work |
| “CompletableFuture async always uses a common-pool thread.” | There is a fallback when parallelism is insufficient; explicit Executor is supported |
| “Passing an executor to the first stage makes the whole pipeline use that pool.” | Async continuations without an executor may use the default facility |
| “Parallel streams are always fast.” | Small/blocking/stateful workloads can be slower or wrong |
| “Work-stealing definitely prevents starvation.” | Blocking, dependency cycles, and finite resources still cause stalls |
| “ManagedBlocker always opens another worker.” | Compensation is a conditional mechanism with no deadline guarantee |
| “`shutdown()` closes the common pool.” | Shutting down the common pool has no effect per contract |
| “`getQueuedTaskCount()==0` proves completion.” | Active tasks or external submissions may still remain |
| “`cancel(true)` definitely interrupts a ForkJoinTask.” | Default ForkJoinTask cancellation does not use interruption like FutureTask |
| “A dedicated pool eliminates all mutual interference.” | CPU, heap, GC, and downstream I/O are still shared |
| “Caller's ThreadLocal is automatically present in a common worker.” | There is no automatic context propagation |
| “Each request should create a pool.” | Per-request pool creation/destruction is usually costly and blows budgets |

## 19. Self-check questions

**Question 1.** Two modules both call `ForkJoinPool.commonPool()`. Do they receive two different pools?  
**Answer:** No, they share the same instance and can contend for workers.

**Question 2.** Does `CompletableFuture.supplyAsync(supplier)` always run on a common-pool worker?  
**Answer:** Usually it uses the common pool, but Java 17 has a fallback that creates a new `Thread` if the common pool does not support a parallelism of at least 2.

**Question 3.** Why is `left.fork(); right.compute(); left.join();` usually better than forking both branches and waiting?  
**Answer:** The worker processes one branch itself while giving the other branch a chance to be stolen, reducing overhead and unnecessary waiting.

**Question 4.** A parallel stream calls `forEach(out::add)` on a shared `ArrayList`. Is this safe?  
**Answer:** No. Use a suitable collector/reduction or synchronization.

**Question 5.** Library A submits many blocking tasks to the common pool, while module B runs CPU computations via the common pool. Can B slow down?  
**Answer:** Yes; workers/resources are shared and blocking reduces capacity.

**Question 6.** Does `ForkJoinPool.managedBlock` guarantee a replacement worker is always created?  
**Answer:** No; compensation depends on conditions, pool limits, and the OS.

**Question 7.** A component calls `ForkJoinPool.commonPool().shutdown()` to stop itself. Is that proper ownership?  
**Answer:** No. The common pool is a shared resource; shutdown calls have no effect on the common pool per the API.

**Question 8.** Does `ForkJoinTask.cancel(true)` guarantee an interrupt is sent to the running body?  
**Answer:** No; the default implementation does not use interruption to control cancellation.

**Question 9.** Does a dedicated pool give the JVM more CPU cores?  
**Answer:** No. It only isolates executor-level workers/queues/lifecycle; CPU, memory, and downstream systems are still shared.

**Question 10.** Does `getQueuedTaskCount()==0` prove a module's work is finished?  
**Answer:** No. You must wait on specific `Future`s/acks.

**Question 11.** Where might `thenApplyAsync(fn)` without an `Executor` run after `supplyAsync(..., ownPool)`?  
**Answer:** It may use the default async facility, usually the common pool; pass an executor to the continuation when isolation is needed.

**Question 12.** Can you verify the correctness of `CommonPoolSum` via the log order of branches?  
**Answer:** You should not. Verify the sum `36` and invariants instead of depending on the scheduler.

## Java SE 17 References

- [`ForkJoinPool`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work-stealing, `commonPool`, parallelism, managed blocking, monitoring, and lifecycle.
- [`ForkJoinTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, cancellation semantics.
- [`RecursiveTask`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): recursive task that returns a result.
- [`CompletableFuture`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): default async executor, overloads taking an `Executor`, and cancellation.
- [`ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): submit, `Future`, and lifecycle.
- [`Future`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): results, completion, and cancellation.
- [Stream package](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html): parallel streams, stateless behavior, reductions.
- [`ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread context semantics.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): synchronization and happens-before.

**Key takeaway:** `ForkJoinPool.commonPool()` reduces the cost of creating separate pools for suitable Fork/Join work, but brings **shared-resource interference**. Know which APIs may use the shared pool, avoid long blocking inside shared workers, manage your own `Future`/task handles, and switch to a dedicated executor when you need isolation, tuning, or independent shutdown.