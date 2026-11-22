# Fork/Join and Divide-and-Conquer in Java Concurrency

When processing a large volume of data, you can sometimes **split a large problem into independent subproblems**, let multiple workers process them concurrently, and then **combine the results**. This is the *divide-and-conquer* mindset. Java provides the **Fork/Join Framework** in `java.util.concurrent` to implement this style of task, especially when the workload is primarily CPU-bound.

**Fork/Join** is a model consisting of:
1. **Divide:** if the problem is large enough, split it into smaller branches.
2. **Fork:** give one or more branches the opportunity to be executed by another worker.
3. **Join:** wait for the required branch to complete and combine the results.
4. **Conquer/base case:** if the workload is small enough, compute it directly without splitting further.

In the JDK, the three commonly used components are `ForkJoinPool` (a pool with a work-stealing mechanism), `RecursiveTask<V>` (a task that returns a result), and `RecursiveAction` (a task that does not return a result). All of these belong to **general Java concurrency**; this lesson does not rely on any external framework.

## 1. Which problems fit divide-and-conquer?

Take the example of summing an 8-element array:

```text
sum([1,2,3,4,5,6,7,8])
                |
       +--------+--------+
       |                 |
sum([1,2,3,4])     sum([5,6,7,8])
       |                 |
   +---+---+         +---+---+
   |       |         |       |
sum(1,2) sum(3,4) sum(5,6) sum(7,8)
   |       |         |       |
   3       7        11      15
   +---+---+         +---+---+
      10                26
       +--------+--------+
                36
```

The subsum branches can execute independently. The final result is the sum of the subresults. If the total number of elements is very large and each branch has enough work, several branches can run in parallel across multiple CPU cores.

For divide-and-conquer to be effective, a problem should have the following characteristics:

- **Partitionable:** each branch reads/processes a separate data region or portion of the problem.
- **Minimal cross-dependencies:** no need to lock a shared variable for every element.
- **Clear result combination:** sum, min/max, statistics, result trees, or output written to disjoint regions.
- **Finite base case:** splitting eventually stops at a specific threshold rather than creating tasks indefinitely.
- **Sufficient work per branch:** the processing time for each branch must be significant compared to the overhead of creating, scheduling, and joining tasks.

Typical examples: recursive computations on arrays, tree processing, partitioning algorithms, transforming disjoint data regions, and certain search/aggregation algorithms that can be split independently.

Fork/Join is **not suitable by default** for small individual HTTP requests, file writes, database calls, or processing loops that strictly depend on the result of the previous step.

## 2. How does ForkJoinPool differ from creating a Thread per branch?

A naive approach is to create a `new Thread(...)` at every recursive node. As depth increases, the number of threads created can explode, consuming stack memory as well as startup and context-switching overhead.

`ForkJoinPool` replaces that approach with a group of **reusable worker threads** and many lightweight `ForkJoinTask` instances that are much lighter than threads. A worker processes a task; the task can fork child tasks without creating a new OS thread for each branch.

The **work-stealing** concept:

- Each worker has a local task queue (deque) to support processing its own branches.
- If a worker runs out of work, it can **steal** a pending task from another worker's queue.
- This mechanism tries to keep workers busy when branches are uneven in count or take different amounts of time.
- Execution order and the thread executing a branch are **not guaranteed to be fixed**; a newly forked task may even be executed later by the current worker itself.

```text
ForkJoinPool (parallelism ~ target number of workers)
       |
       +-- Worker 1: task A -> fork A1, A2
       |                 |
       |                 +-- process A2
       |
       +-- Worker 2: out of work -> steal A1
       |                                |
       +-- Worker 3: process another branch ---+
       |
       +-- Worker 4: may be idle if there is little work
```

**Work-stealing is a work-distribution strategy**, not a guarantee that every branch gets its own worker, that every worker stays busy, or that execution will be faster than running sequentially. `parallelism` is the pool's target parallelism level, not a guarantee that all tasks run simultaneously on that exact number of threads.

## 3. Core components and methods

| API | Meaning | When to use |
|---|---|---|
| `ForkJoinPool` | Specialized executor for `ForkJoinTask`s; supports work-stealing. | Running divide-and-conquer task trees, managing parallelism/lifecycle. |
| `RecursiveTask<V>` | Abstract class for a task returning a result of type `V`; override `compute()`. | Computing sums, counts, min/max, statistics, or returning a result object. |
| `RecursiveAction` | Abstract class for a task without a return value; `compute()` returns `void`. | Transforming independent array regions, in-place sorting with safe partitioning. |
| `task.fork()` | Submits a `ForkJoinTask` to the scheduling mechanism to execute asynchronously relative to the current task. | When you want a child branch to have the opportunity to run in parallel. |
| `task.join()` | Waits for a child task to complete and retrieves its result; runtime exceptions may be rethrown. | Combining results when a branch has been forked. |
| `task.invoke()` | Executes the task and waits for its result. | When you want to process a `ForkJoinTask` synchronously. |
| `ForkJoinTask.invokeAll(a,b)` | Executes a group of tasks using Fork/Join and waits for them to complete. | When both branches are `RecursiveAction`s or manual fork/join is unnecessary. |
| `pool.invoke(root)` | Submits the root task to the pool and waits for the result. | Entry point for starting a task tree from the caller. |
| `pool.execute(task)` | Submits a task for execution without immediately waiting at the caller. | When managing completion at another step. |

`ForkJoinTask.join()` **differs from** `Thread.join()`: it waits for a **task** in the ForkJoin Framework, not for a `Thread` object to terminate. `ForkJoinTask.join()` does not declare `InterruptedException` like `Thread.join()`; needing a wait timeout and interrupt handling requires appropriate API design (such as `Future`'s `get(timeout, unit)`).

`RecursiveTask.compute()` is code that you write; **this method decides the base case, how to split, and how to combine**. The framework does not guess the threshold or partition arrays for your application.

## 4. Pattern: fork one branch, compute one branch, join the forked branch

A simple pattern for `RecursiveTask<Result>`:

```java
@Override
protected Result compute() {
    if (smallEnough()) {
        return calculateDirectly();
    }

    Task left = new Task(leftRange);
    Task right = new Task(rightRange);

    left.fork();                    // Give left a chance to run in parallel.
    Result rightResult = right.compute(); // Current worker computes right directly.
    Result leftResult = left.join();       // Wait for left when actually needed.

    return combine(leftResult, rightResult);
}
```

This is **Java-syntax pseudocode**, not a standalone class: `Task`, `Result`, `Range`, and the illustrative methods are not defined. Complete programs are shown in the following sections.

**Why not `left.fork(); left.join(); right.compute();`?** If you join immediately after forking, the worker may have to wait for `left` to finish before starting `right`, losing part of the opportunity to overlap work. The fork `left` -> compute `right` -> join `left` pattern keeps the current thread doing useful work while `left` can be processed by another worker.

You can fork both branches and then join them, but when a worker is traversing a recursive tree, computing one branch directly generally reduces scheduling overhead and is recommended as a sensible pattern. Not every case must follow one exact order; correctness still depends on the data, not on execution order.

## 5. Example 1 — Summing an array with RecursiveTask<Long>

We split a `long[]` into two half-open segments `[from, to)` until the number of elements in a segment does not exceed `THRESHOLD`. Branches only **read data**, and `join()` combines the subsums; there is no need for `AtomicLong` or `synchronized` on a global sum variable.

Create the file **`ForkJoinSumDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    private static final int THRESHOLD = 256;

    static final class SumTask extends RecursiveTask<Long> {
        private final long[] data;
        private final int from;
        private final int to;

        SumTask(long[] data, int from, int to) {
            this.data = data;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += data[i];
                }
                return sum;
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(data, from, middle);
            SumTask right = new SumTask(data, middle, to);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();

            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        long[] data = new long[10_000];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1;
        }

        long sequential = 0;
        for (long value : data) {
            sequential += value;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long parallel = pool.invoke(
                    new SumTask(data, 0, data.length)
            );

            System.out.println("Sequential: " + sequential);
            System.out.println("ForkJoin: " + parallel);
            System.out.println("Equal: " + (sequential == parallel));
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
```

Output:

```text
Sequential: 50005000
ForkJoin: 50005000
Equal: true
```

**Step-by-step explanation:**

1. `data` contains the numbers from 1 to 10,000; the mathematical sum is `10000 * 10001 / 2 = 50005000`.
2. The root task covers `[0,10000)`. Whenever a segment is larger than 256 elements, it splits into two **non-overlapping** halves.
3. `left.fork()` gives `left` a chance to run in parallel; the current worker calls `right.compute()` to make good use of its time.
4. `left.join()` waits for `left` if it has not finished yet and retrieves its sum. Each node returns the sum of its two branches, so the root receives the total sum.
5. There is no shared accumulator modified by multiple workers. The variables `sum`, `leftSum`, and `rightSum` are local to each `compute()` invocation, avoiding data races.
6. `main` receives the result from `pool.invoke()` after the root task completes, then prints it. The program does not print worker order so that stdout does not depend on scheduling.

**Note:** `ForkJoinPool(4)` only sets the requested parallelism level for the pool; it does not prove that the machine runs four times faster. With an array of only 10,000 elements and very cheap addition, the sequential version may be faster due to task-splitting overhead.

## 6. Choosing a threshold: where to stop splitting

`THRESHOLD` is the maximum number of elements processed directly in a leaf task. It is a **performance parameter**, not a constant that Java prescribes for every algorithm.

- Threshold **too small**: creates too many tasks, increasing allocation, deque management, stealing, joining, and recursion overhead; overhead can exceed useful work.
- Threshold **too large**: too few branches, less opportunity for load balancing; other workers may sit idle while one large branch computes.
- **Appropriate** threshold: each leaf has enough work and there are enough branches to distribute without creating millions of tiny tasks.

Approximate example: with `N = 1_000_000` elements and a threshold of 1,000, the number of leaves is around `N / 1000` (depending on how halves split), not one task per element. Actual speed also depends on per-element computation cost, memory bandwidth, JIT warm-up, and CPU core count.

Tuning practices:

1. Build a **sequential version** as a baseline and verify result correctness.
2. Ensure the computation is large enough; test multiple thresholds (for example 256, 1,024, 4,096, 16,384).
3. Benchmark with realistic data, hardware, and JVM settings; run multiple iterations with warm-up and measure variance.
4. Monitor throughput, allocations, GC, steal counts, and CPU utilization where helpful.
5. Do not treat a single `System.nanoTime()` measurement around one small call as a general conclusion.

The overhead ratio also varies by operation type: if a leaf performs simple array arithmetic, the threshold may need to be large; if each element requires heavy computation, a smaller threshold can be beneficial.

## 7. RecursiveAction: modifying independent data regions

`RecursiveAction` does not return a value from `compute()`. It fits cases where branches can **write to disjoint data regions** without combining result objects. The key requirement is that every branch only modifies the range it owns, preventing two workers from writing to the same slot.

Example: squaring each element of an array. The program intentionally uses a small array so stdout is easy to inspect; this is a **concurrency-correctness** example, not a benchmark.

Create the file **`ForkJoinSquareDemo.java`**:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinSquareDemo {
    static final class SquareTask extends RecursiveAction {
        private static final int THRESHOLD = 2;

        private final int[] values;
        private final int from;
        private final int to;

        SquareTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= THRESHOLD) {
                for (int i = from; i < to; i++) {
                    values[i] = values[i] * values[i];
                }
                return;
            }

            int middle = from + (to - from) / 2;
            invokeAll(
                    new SquareTask(values, from, middle),
                    new SquareTask(values, middle, to)
            );
        }
    }

    public static void main(String[] args) {
        int[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            pool.invoke(new SquareTask(values, 0, values.length));
            System.out.println("Squares: " + Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinSquareDemo.java
java ForkJoinSquareDemo
```

Output:

```text
Squares: [1, 4, 9, 16, 25, 36, 49, 64]
```

**Why is `synchronized` unnecessary when writing to the array?** Each task processes a half-open range `[from,to)`. The two subranges `[from,middle)` and `[middle,to)` do not share any indices; no two tasks in the tree write to the same element. `invokeAll()` waits for the branches to finish before the parent node returns; `pool.invoke()` waits for the entire tree to finish before `main` reads the full array.

Do not generalize that "using Fork/Join makes mutable arrays always thread-safe." If tasks write to a shared index, mutate a shared `ArrayList`, or increment a shared counter without synchronization, races still occur. The safety of this example relies on **disjoint write ownership**.

## 8. RecursiveTask returning a composite aggregate result

Not every divide-and-conquer problem computes only a single number. You can create an immutable result object containing **sum, minimum, and maximum**, and combine them at each branch. This is a task-level map/reduce pattern: each leaf creates its own result, and the parent node combines them without mutating global state.

Create the file **`ForkJoinStatsDemo.java`**:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinStatsDemo {
    record Stats(long sum, int min, int max) {
        static Stats combine(Stats a, Stats b) {
            return new Stats(
                    a.sum() + b.sum(),
                    Math.min(a.min(), b.min()),
                    Math.max(a.max(), b.max())
            );
        }
    }

    static final class StatsTask extends RecursiveTask<Stats> {
        private static final int THRESHOLD = 2;

        private final int[] values;
        private final int from;
        private final int to;

        StatsTask(int[] values, int from, int to) {
            this.values = values;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Stats compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                int min = Integer.MAX_VALUE;
                int max = Integer.MIN_VALUE;

                for (int i = from; i < to; i++) {
                    int value = values[i];
                    sum += value;
                    min = Math.min(min, value);
                    max = Math.max(max, value);
                }
                return new Stats(sum, min, max);
            }

            int middle = from + (to - from) / 2;
            StatsTask left = new StatsTask(values, from, middle);
            StatsTask right = new StatsTask(values, middle, to);

            left.fork();
            Stats rightResult = right.compute();
            Stats leftResult = left.join();
            return Stats.combine(leftResult, rightResult);
        }
    }

    public static void main(String[] args) {
        int[] values = {8, 3, 12, 4, 9, 1, 7, 6};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            Stats stats = pool.invoke(
                    new StatsTask(values, 0, values.length)
            );

            System.out.println("Sum: " + stats.sum());
            System.out.println("Min: " + stats.min());
            System.out.println("Max: " + stats.max());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinStatsDemo.java
java ForkJoinStatsDemo
```

Output:

```text
Sum: 50
Min: 1
Max: 12
```

Each `StatsTask` branch creates a new `Stats`, and the parent node calls `Stats.combine` to merge them. The result does not depend on task execution order. For an empty array, the `min/max` initialization in this example **does not represent valid statistics**; this code assumes at least one element in the input and should reject empty arrays or return a result type representing an empty state in production library code.

If the combine operation is not **associative**, the result can change when the split tree changes. Integer addition in the example is mathematically associative (though Java `long` can overflow on sufficiently large inputs); `double` addition has rounding error, so different combination orders can produce slightly different floating-point results. Never assume every reduction is safe to split and combine arbitrarily.

## 9. Do not share a mutable accumulator across branches

An unsafe pattern:

```java
// ANTI-PATTERN: sharedTotal is a shared mutable variable.
sharedTotal += values[i];
```

If multiple tasks execute this line concurrently, the read-add-write operation is not atomic, which can cause *lost updates*. Adding `volatile` to `sharedTotal` does not make `+=` atomic either.

Better alternatives:

- Use `RecursiveTask<Long>` to return local sums and then **join and combine**, as in `ForkJoinSumDemo`.
- Have `RecursiveAction`s modify **disjoint data regions**, then read after the entire tree completes.
- If shared state updates are truly required, use proper synchronization tools, though contention on a shared counter can negate Fork/Join's advantages.

When child tasks hold references to the same mutable object, creating multiple `RecursiveTask`s **does not automatically copy the object**. You must actively ensure disjoint access, immutability, or synchronization. Returning results as an immutable `record` clarifies ownership and reduces shared mutable state.

## 10. Java Memory Model: visibility after join/invoke

Java Fork/Join has memory synchronization rules for **submitting tasks and retrieving results**. Actions before submitting a task to an executor have a *happens-before* relationship with the task's actions; actions of an asynchronous computation have a *happens-before* relationship with actions after another thread retrieves the result via the corresponding `Future.get()`. `ForkJoinTask` completion primitives such as `join()` also provide synchronization so that a completed branch's result can be safely used according to the task contract.

In `ForkJoinSumDemo`, the array data is initialized **before submitting the root task**; tasks only read it. In `ForkJoinSquareDemo`, child tasks write to disjoint regions and the tree finishes before `main` prints the array, because `pool.invoke(root)` returns only after the root finishes coordinating its branches.

This does **not** allow `main` to read an array being modified by tasks **before** a completion synchronization point has occurred; nor does it make unprotected concurrent mutations elsewhere safe.

`join()` is a synchronization point for waiting on a task, not a mechanism that "locks all variables." If an external thread continues modifying the input data while Fork/Join is running, you still need proper synchronization design or an immutable snapshot.

## 11. ForkJoinPool.commonPool() vs. a custom pool

The JDK provides a shared pool:

```java
ForkJoinPool common = ForkJoinPool.commonPool();
```

This pool is shared by Java components that use the common pool by default, and operations such as certain `parallelStream()` or asynchronous `CompletableFuture` calls may involve it depending on how they are invoked and the environment. Using the common pool helps **reuse workers** without creating a new pool per computation, but carries the risk of unrelated workloads competing for CPU.

Comparison:

| Usage | Advantages | Considerations |
|---|---|---|
| `ForkJoinPool.commonPool()` | Shared pool; no need to manage workers per computation. | No isolated control over contention across subsystems; do not shut down the common pool like a private pool. |
| `new ForkJoinPool(parallelism)` | Explicit control over parallelism for a workload group and lifecycle management. | Creating a pool consumes resources; must be shut down when no longer needed. |
| `pool.invoke(rootTask)` | Caller waits for the root task tree's result. | Caller blocks until root completes; if root stalls, caller may stall as well. |
| `pool.submit(task)` | Returns a `Future`-like handle to await elsewhere. | Requires managing completion, timeout, cancellation, and errors. |

**Do not create a `new ForkJoinPool()` for each element or each branch.** Typically, one pool suffices for the entire tree. Child tasks are forked into the pool's work mechanism rather than managing their own separate pools.

`commonPool()` has the special lifecycle of a shared pool; calling `shutdown()` on the common pool does not behave like shutting down a private pool. Do not let one feature in a system arbitrarily shut down a shared resource used by other components.

## 12. Great for CPU-bound work; be careful with blocking I/O

Fork/Join is optimized for many short, independent computational tasks that benefit from work-stealing. You should not push thousands of blocking I/O calls into `ForkJoinTask`s and assume it will scale like a pool designed for blocking requests.

Problems when blocking:

1. A worker blocked on a socket, database, or long-held lock cannot participate in stealing or executing other work.
2. If tasks wait on each other without proper coordination mechanisms, the pool can fail to make progress; some waiting patterns can even cause deadlock.
3. Arbitrarily increasing parallelism can shift the bottleneck to external services or databases without making the system faster.
4. I/O calls typically need **timeouts directly at the I/O API** and independent cancellation/cleanup.

`ForkJoinPool.managedBlock(ManagedBlocker)` is a mechanism to notify the pool about certain blocking situations so it can compensate with additional workers when conditions permit. It does **not** turn blocking I/O into non-blocking I/O, does **not** guarantee deadlock freedom, and does **not** solve backpressure or timeouts by itself.

If the problem is mainly I/O-bound, an appropriate `ThreadPoolExecutor`, asynchronous I/O, or a different task design may be simpler and more effective. For heavy, independently separable CPU computations, Fork/Join is usually worth evaluating.

## 13. Errors, cancellation, deadlines, and exceptions

`RecursiveTask.compute()` can throw runtime exceptions. When a task is invoked via `pool.invoke()` or `join()`, exceptions can be propagated to the waiting thread according to `ForkJoinTask` semantics. Do not assume the rest of the entire tree has been cleaned up just because one branch threw an exception; other tasks may still be running and need their own data/error management contract.

`ForkJoinTask` also implements `Future`, so it provides operations like `get()`, `get(timeout, unit)`, `cancel()`, `isDone()`, and `isCancelled()`. However:

- Regular `join()` **has no timeout parameter** and does not declare `InterruptedException`.
- `get(timeout)` limits how long the caller waits; it **does not automatically stop the task** when the timeout expires.
- `ForkJoinTask.cancel(true)` **should not be assumed** to guarantee interrupting a running worker: `ForkJoinTask` cancellation has its own limited contract; cancellation may not stop currently executing code.
- `isDone()` only indicates that the task is in a completed/cancelled state per the API; it does not prove that all side effects and external resources have been cleaned up.

A long-running task needs a **cooperative cancellation** strategy, stop checkpoints, proper interruption handling, deadlines where needed, and cleanup in `finally`. If using a private pool, the caller should manage bounded `shutdown()`/`awaitTermination()` rather than assuming workers always terminate on their own.

Do not use `Thread.stop()` or forcibly abort a branch while it is modifying shared state; the risk of breaking invariants remains.

## 14. Algorithmic and performance pitfalls

| Pitfall | Why it causes problems | How to improve |
|---|---|---|
| Forking one element at a time. | Creates too many tasks; overhead exceeds computation. | Use a threshold for the base case. |
| Missing base case / stop condition. | Infinite recursion; can cause `StackOverflowError` or task explosion. | Ensure splitting produces smaller segments and has a stopping threshold. |
| `left.fork(); left.join(); right.compute();`. | Joining too early loses the opportunity to overlap `right` with `left`. | Fork one branch, compute the other directly, then join. |
| Forking a task and forgetting to join when its result is needed. | Parent may return an incomplete or partial result. | Join all branches that must be combined before returning from parent. |
| Sharing a mutable accumulator. | Data races, lost updates, or heavy contention. | Return local results or split into disjoint write regions. |
| Assuming `parallelism=8` means 8 cores always run at 100%. | Small workloads, imbalance, or blocking leave threads idle. | Measure CPU/steals; improve branching and threshold. |
| Putting blocking I/O into tasks without accounting for the pool. | Workers are held up, reducing throughput or causing deadlock. | Use an appropriate executor/async I/O, or `managedBlock` when suitable. |
| Assuming branch execution order is deterministic. | Work-stealing, scheduler, and `join()` can produce different schedules. | Derive output from data/result combination, not execution schedule. |
| Combining with a non-associative operation while expecting invariant results. | Merge tree order can affect the answer. | Define a mathematically sound combine or document precision/order sensitivity. |
| Creating a new pool for every recursive call. | Wastes threads and resources. | Use a single pool for the whole tree. |
| Forgetting to shut down a private pool. | Pool resources may stay alive unnecessarily long. | Close lifecycle at the owner and await termination appropriately. |
| Reading mutable data before completion point. | May observe partially updated data. | Wait for `invoke`/`join` and use proper synchronization protocols. |

## 15. Systematic divide-and-conquer problem design

Before choosing Fork/Join, you can use this checklist:

1. **Is the sequential version correct?** Establish the baseline output, handle empty input, overflow, and data boundaries.
2. **How to split?** Usually use half-open ranges `[from,to)` so branches do not overlap; `middle = from + (to-from)/2` avoids a form of overflow when computing the midpoint.
3. **What is the base case?** If `to-from <= threshold`, compute directly so overly small child tasks are not created.
4. **Are the two branches independent?** If they modify the same object, control shared state or design them to return separate results.
5. **Is the combine step correct?** For sum/min/max, combining is straightforward; for non-associative algorithms, consider ordering.
6. **How many tasks?** Estimate overhead; do not confuse having many tasks with having many CPUs running simultaneously.
7. **Which pool to choose?** The common pool is acceptable for general workloads; use a private pool if isolation and lifecycle control are needed.
8. **Is there blocking?** If tasks must wait on I/O or external resources, re-evaluate the Executor Framework and `managedBlock`.
9. **How are errors/cancellation/timeouts handled?** The task tree needs cleanup rules and completion tracking.
10. **Are you measuring performance properly?** Warm up the JIT, compare against sequential, test multiple thresholds/datasets, and verify results.
11. **Avoid fragmenting resources:** do not create additional pools or threads inside `compute()` without a clear reason.
12. **Design the external API cleanly:** expose only a high-level compute method; do not force callers to manage child tasks manually.

## 16. Fork/Join, ExecutorService, and parallel streams

| Need | APIs typically considered | Key notes |
|---|---|---|
| Recursive branching computation tree with result merging | `ForkJoinPool` + `RecursiveTask`. | Control branching/threshold; must design result and join. |
| Transforming disjoint data regions | `RecursiveAction`. | Write to non-overlapping regions; parent waits for all children. |
| Non-recursive list of independent tasks | `ExecutorService.invokeAll()` or `submit()`. | Timeouts, queueing, and cancellation are still necessary. |
| Pipeline-style collection processing | `parallelStream()` when tasks fit. | Convenient, but still must avoid shared mutable state and benchmark. |
| Blocking I/O, external APIs | Workload-appropriate executor/async I/O. | Do not assume Fork/Join is optimal for blocking. |
| Small workload and very cheap computation | Sequential loop. | Avoids task creation and work-stealing overhead. |

Fork/Join is a powerful tool, not a reason to **parallelize everything**. Summing a small array can be faster with a `for` loop. Conversely, when you have a large array, multiple cores, and sufficiently heavy computation, the divide-and-conquer model makes it easy to introduce parallelism without manually coordinating thousands of `Thread`s.

## 17. Self-check questions

1. **What are the three logical steps of divide-and-conquer?** Split into subproblems, solve subproblems/base case, and combine results.
2. **How does `RecursiveTask` differ from `RecursiveAction`?** `RecursiveTask` returns a result value, whereas `RecursiveAction` returns no result from `compute()`.
3. **Does `ForkJoinPool` create one OS thread per task?** No; it reuses worker threads and schedules many `ForkJoinTask`s.
4. **What is work-stealing used for?** An idle worker can take tasks from another worker's queue to balance work.
5. **Why is `left.fork(); right.compute(); left.join();` commonly used?** It gives `left` a chance to run in parallel while the current worker still computes `right`.
6. **What happens if the threshold is too small?** The number of tasks and coordination overhead grow excessively.
7. **Are multiple tasks guaranteed to run in parallel?** No; actual execution depends on parallelism level, data, and the scheduler.
8. **Why avoid a single shared mutable sum variable?** Multiple tasks can contend on updates, causing lost updates or heavy contention.
9. **Is it safe for two `RecursiveAction` tasks to modify an array concurrently?** Only if their write regions do not overlap or a proper synchronization protocol is used.
10. **How does `pool.invoke(root)` differ from `pool.execute(root)`?** `invoke` waits for `root` to complete and returns its result; `execute` only submits the task without waiting immediately.
11. **Is `ForkJoinTask.join()` the same as `Thread.join()`?** No; one waits for a task, the other waits for a thread.
12. **Does `ForkJoinTask.join()` have a timeout?** No; if bounded waiting is needed, consider `get(timeout, unit)` and a cancellation protocol.
13. **Is Fork/Join suitable for handling thousands of blocking sockets?** Usually not the default choice; consider other blocking/async APIs.
14. **Why is an immutable `Stats` object easier to combine safely than a shared accumulator?** Each leaf returns its own result and the parent combines them after `join`.
15. **Do you always get a large speedup over sequential execution?** No; task, memory, and scheduling overhead can outweigh the useful work.

**Key takeaway:** Fork/Join combines **divide-and-conquer + lightweight tasks + work-stealing + result joining** to exploit parallelism for problems with independent branches. Correctness relies on base cases, non-overlapping partitioning, proper combination, and completion synchronization; performance relies on workload, threshold, and pool configuration — not on how many tasks are created.
