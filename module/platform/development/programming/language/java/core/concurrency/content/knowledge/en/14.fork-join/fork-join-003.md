# RecursiveTask<V> vs. RecursiveAction in Java Fork/Join

## 1. Overview: Same Fork/Join, Different Result Contract

The **Fork/Join Framework** in `java.util.concurrent` is a divide-and-conquer task execution model: split a problem into sufficiently independent parts, distribute work across workers, and then wait and combine results when needed. **ForkJoinPool** uses **work stealing** so idle workers can take tasks from other workers, balancing the load of subdivisible tasks.

Two classes to distinguish:

- **`RecursiveTask<V>`**: defines `protected V compute()`. The task computes and **returns a result** of type `V`. A natural choice for sums, averages, finding maximums, counting, searching, or collecting statistics.
- **`RecursiveAction`**: defines `protected void compute()`. The task performs work **without returning a value from `compute()`**. Commonly used to update independent partitions of an array, transform data in place, or apply effects to clearly separated regions.

Both extend **ForkJoinTask**, can be submitted to a **ForkJoinPool**, call `fork()`, `join()`, `invoke()`, and share the same scheduling principles and data-safety requirements. The most important difference is **whether branches need to return/combine results**, not that one type "runs faster" by default.

**Quick choice:** need to `return` a value from each branch to combine → **RecursiveTask<V>**; need to process multiple data regions without branches returning values → **RecursiveAction**, provided side effects are managed safely.

## 2. Direct Comparison Table

| Aspect | `RecursiveTask<V>` | `RecursiveAction` |
|---|---|---|
| Superclass | `ForkJoinTask<V>` | `ForkJoinTask<Void>` |
| Method to override | `protected V compute()` | `protected void compute()` |
| Base case | Compute directly and **return V** | Execute directly and **return;** or reach end of method |
| After branching | Retrieve subtask results and **combine** | **join** to wait for branches to complete |
| Value of `join()` on success | Value of type `V` | `null` (type `Void`) |
| Value of `pool.invoke(...)` on success | Value of type `V` | `null` (type `Void`) |
| Typical examples | Sum, count, max, tree reduction | Updating image regions, transforming array slices |
| Common design mistake | Not combining all branches, splitting too small | Data race from multiple branches writing to the same region |

**Note on `Void`:** `compute()` of `RecursiveAction` has return type `void`. However, `RecursiveAction` extends `ForkJoinTask<Void>`, so `join()` and `pool.invoke(action)` have return type `Void`; they return `null` when completed normally. Distinguish the **return type of `compute`** from the return types of inherited APIs.

A `RecursiveTask<V>` can still cause side effects, and a `RecursiveAction` can still produce output data by updating shared objects. The API does not enforce purity; the programmer must design safe read/write regions.

## 3. Mechanics of fork, compute, join, and Work Stealing

Divide-and-conquer recursion follows this sequence:

1. Define a **base case**, for example an array segment of length at most `THRESHOLD`. When the threshold is reached, compute sequentially without creating more tasks.
2. If the threshold is not reached, split `[from, to)` into `[from, middle)` and `[middle, to)`.
3. **fork one branch** so another worker can pick it up for processing.
4. **compute the remaining branch directly on the current worker**.
5. **join** the forked branch to wait for completion, obtain its result, or ensure its side effects have occurred.
6. For `RecursiveTask`, **combine and return**; for `RecursiveAction`, finish after joining the branches that need to be awaited.

~~~text
               Task [0, 16)
                    |
             exceeds threshold?
                /        \
               yes        no
               |           |
         split in two   process sequentially
          /        \
     fork left   compute right
          \        /
           join left
               |
        RecursiveTask: combine + return V
        RecursiveAction: complete (void)
~~~

**`fork()` does not create a new OS thread for every branch.** It submits a `ForkJoinTask` into the pool's execution mechanism; the worker that actually runs it may be the current worker or another worker. Work stealing does not guarantee completion order across tasks, so verification examples must rely on **the result**, not on log line order.

Common pattern:

~~~java
// ILLUSTRATIVE CODE: types and methods depend on the specific problem.
LeftTask left = new LeftTask(...);
left.fork();
Result rightResult = new RightTask(...).compute();
Result leftResult = left.join();
return combine(leftResult, rightResult);
~~~

This is a **conceptual snippet**, not a standalone class. Do not mechanically fork both branches and immediately wait for both: computing one branch directly usually reduces scheduling overhead. More small `ForkJoinTask` instances does not mean more CPU power.

## 4. RecursiveTask<V>: Array Sum Example

The recursive formula for the sum is:

`sum(range) = sum(leftRange) + sum(rightRange)`.

When `range` is small enough, run a sequential loop. For larger branches, return partial sums for the parent to combine. No shared sum variable or lock is needed, because results are passed through `join()`.

### Complete Java 17 Code

Save as **RecursiveSumDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class RecursiveSumDemo {
    private static class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 3;

        private final long[] values;
        private final int from;
        private final int to;

        SumTask(long[] values, int from, int to) {
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

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(values, from, middle);
            SumTask right = new SumTask(values, middle, to);

            left.fork();
            long rightTotal = right.compute();
            long leftTotal = left.join();
            return leftTotal + rightTotal;
        }
    }

    public static void main(String[] args) {
        long[] numbers = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12};
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(
                    new SumTask(numbers, 0, numbers.length));
            System.out.println("sum=" + result);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac RecursiveSumDemo.java
java RecursiveSumDemo
~~~

Exact stdout:

~~~text
sum=78
~~~

**Analysis:**

- Ranges `[from, to)` are **half-open**: inclusive of `from`, exclusive of `to`. This prevents two sub-ranges from reading or writing overlapping elements due to off-by-one boundary errors.
- `THRESHOLD=3` is for easy observation in the example; in practice, benchmark to choose a threshold.
- If the segment length is less than or equal to 3, the loop sums directly and executes `return total`. This is the base case that guarantees recursion terminates.
- Otherwise, `left.fork()` schedules the left branch, and the right branch is computed directly via `right.compute()`. `left.join()` retrieves the left branch's sum.
- `return leftTotal + rightTotal` combines the two branches into the parent result. `pool.invoke` runs the root task and waits for it to finish; the sum of 1 to 12 is **78**, independent of scheduling order.

Generic note: `RecursiveTask<Long>` returns a `Long` object, and Java supports unboxing to `long`. You cannot use `RecursiveTask<long>` because generic type arguments must be reference types. For large sums, watch out for `long` limits and overflow.

## 5. RecursiveAction: In-Place Array Transformation Example

Problem: convert each word in an array to uppercase. We do not need to return a new array from each branch; each branch is assigned **an exclusive slice** of the original array and modifies only that slice. `RecursiveAction` expresses this intent clearly.

### Complete Java 17 Code

Save as **RecursiveUppercaseDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Locale;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class RecursiveUppercaseDemo {
    private static class UppercaseAction extends RecursiveAction {
        private static final int THRESHOLD = 2;

        private final String[] words;
        private final int from;
        private final int to;

        UppercaseAction(String[] words, int from, int to) {
            this.words = words;
            this.from = from;
            this.to = to;
        }

        @Override
        protected void compute() {
            if (to - from <= THRESHOLD) {
                for (int i = from; i < to; i++) {
                    words[i] = words[i].toUpperCase(Locale.ROOT);
                }
                return;
            }

            int middle = from + (to - from) / 2;
            UppercaseAction left =
                    new UppercaseAction(words, from, middle);
            UppercaseAction right =
                    new UppercaseAction(words, middle, to);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) {
        String[] words = {"java", "fork", "join", "tasks"};
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new UppercaseAction(words, 0, words.length));
            System.out.println(Arrays.toString(words));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run commands:

~~~bash
javac RecursiveUppercaseDemo.java
java RecursiveUppercaseDemo
~~~

Stdout:

~~~text
[JAVA, FORK, JOIN, TASKS]
~~~

**Differences from RecursiveTask:**

- `protected void compute()` does not produce a `Long` or return value for the parent. In the base case, it simply processes the region and executes **return;**.
- Branches hold references to the same `words` array, but write only to **non-overlapping ranges**: one branch `[from, middle)`, the other `[middle, to)`.
- The right branch runs directly; `left.join()` ensures the left branch finishes. When the root `invoke()` returns normally, all branches have completed and printing the array afterward sees the result.
- `Locale.ROOT` gives testable results independent of the machine's default locale.

**Caution:** Do not assume `RecursiveAction` is automatically safe. If multiple branches call `sharedList.add(...)` on a plain `ArrayList` or update `sharedCounter++` concurrently, a data race can occur. Partition exclusive regions, or use appropriate synchronization/structures when sharing is unavoidable.

## 6. Two Approaches for the Same Kind of Work

### Computing an Aggregate Value

If you want to count elements matching a condition, the natural approach is for each `RecursiveTask<Integer>` to return its branch count; the parent adds the two counts. Avoid having every `RecursiveAction` call `AtomicInteger.incrementAndGet()` on a single counter if your goal is performance scaling: increased contention can slow down parallel tasks.

### In-Place Data Transformation

If you want to modify each pixel in an image array, `RecursiveAction` with non-overlapping segments avoids allocating and merging multiple result arrays. However, if you need to return a new immutable image, you can choose `RecursiveTask<Result>` or pre-allocate a separate target array and use an Action to write into exclusive segments; the choice depends on **ownership and how data is published**.

| Problem | Recommendation | Reason |
|---|---|---|
| Sum, max, min, count | `RecursiveTask<Long>` or suitable result type | Each branch returns a partial result to combine |
| Search for an object | `RecursiveTask<Optional<T>>` or custom result type | Needs to represent found/not-found outcomes |
| In-place array slice transform | `RecursiveAction` | Exclusive write regions can be partitioned |
| Produce a new dataset | Design-dependent; Task returning results or Action writing separate output regions | Must define how results are combined |
| Blocking HTTP/JDBC calls | Usually choose an I/O-appropriate executor | ForkJoin workers do not shine when blocked |
| A small, indivisible operation | Sequential execution | Avoids task creation overhead |

There is no rule that "RecursiveAction is faster because it does not create a result." In practice, performance depends on the computational work, data structures, task distribution, and synchronization cost.

## 7. Understanding the API Precisely: compute, fork, join, invoke, and invokeAll

**`compute()`** is the method you override. Calling `right.compute()` directly is a **synchronous Java method call** on the current thread; it does not spawn a thread or enqueue a task.

**`fork()`** submits the task into the Fork/Join execution mechanism. Which worker runs the task and when depends on scheduling, not a guarantee of `fork()`. Each new branch generally needs a new task instance; do not reuse a completed task as if it were a fresh independent job.

**`join()`** waits for the task to complete and returns `V` (Task) or `null` (Action). A Fork/Join worker may help execute tasks while waiting, unlike simple passive waiting. `join()` can throw an unchecked exception if the task fails or is cancelled. Unlike `Future.get()`, `join()` **does not declare checked** `InterruptedException`/`ExecutionException`; do not treat these two methods as identical.

**`pool.invoke(root)`** submits the root task to the pool and waits for it to finish. For `RecursiveTask<Long>`, it returns `Long`; for `RecursiveAction`, it returns `Void` (`null` on success). `pool.submit(task)` and `pool.execute(task)` can also submit tasks to the pool, but obtaining a `Future` or waiting for results differs from synchronous `invoke`.

**`ForkJoinTask.invokeAll(a, b)`** executes and waits for the given subtasks; for `RecursiveTask`, you still need to retrieve their values to combine them when the problem requires it. This is an alternative style, not mandatory for every problem.

For background tasks, identify **who is responsible for join/get**. If you submit and ignore the result without an error-reporting mechanism, exceptions in tasks can go unnoticed in application logic.

## 8. Choosing Threshold and Parallelism Level

If you split a million-element array into a million `ForkJoinTask` instances, the cost of object allocation, scheduling, synchronization, and GC can exceed the computation itself. If the threshold is too large, there will not be enough tasks to spread across workers.

Practical selection steps:

1. Determine the **execution cost of a leaf** (base case) when run sequentially.
2. Choose a threshold large enough so each leaf has meaningful work, yet still creates enough branches to keep workers busy, even when branch execution times vary.
3. Benchmark multiple sizes/thresholds on **real data and hardware** after warm-up/JIT; measure wall time, CPU utilization, allocation/GC, contention, and throughput.
4. For data with highly uneven processing costs, simply halving element counts may not balance **workload**; a different splitting strategy may be needed.
5. Measure sequential speed as a baseline: Fork/Join only pays off when parallelism gains outweigh management overhead.

`ForkJoinPool(parallelism)` configures the target parallelism level. It does not guarantee that exact number of threads is always running at every moment, and it does not create extra CPUs beyond the resources actually allocated to the JVM. If the application runs in a container, consider CPU quotas, other pools, and overall system load.

**Threshold=2 or 3 in the examples are illustrative values.** For simple operations like adding numbers, the optimal threshold can be much larger; do not put example thresholds into production without measuring.

## 9. Correctness: Partitioning, Memory Visibility, and Data Races

Each branch must have clear data boundaries.

- **Shared reading of immutable data:** multiple `RecursiveTask` instances reading an array that is not modified during computation is a favorable case.
- **Writing to exclusive regions:** multiple `RecursiveAction` instances updating non-overlapping segments of the same array is a sound pattern.
- **Writing to shared data:** you must use synchronization or concurrent structures where appropriate; otherwise, updates can be lost and the Java Memory Model can be violated.
- **Combining data:** Tasks return partial results via `join()`; the parent combines results after subtasks complete, reducing contention.

Unsafe example:

~~~java
// Illustrative snippet only, assuming sharedCounter is a shared variable:
sharedCounter++; // Not atomic when multiple tasks update concurrently.
~~~

Task completion and `join()` provide the necessary synchronization to observe results after a task finishes; however, they **do not make concurrent writes by two branches to overlapping positions thread-safe**. In the Action example, the array is only read for printing **after** the root `pool.invoke()` returns normally.

For any branching scheme, verify that `[from, middle)` and `[middle, to)` completely cover the array without overlap, and that the base case handles empty ranges if the algorithm allows them. Missing or duplicating elements can produce wrong results even without a data race.

## 10. Exceptions: A Failed Task Does Not Silently Become Null

If `compute()` throws an unchecked exception, the task terminates abnormally; `join()` or `invoke()` can propagate the exception to the caller. When propagated across workers, the implementation may reconstruct/wrap the exception, so **do not rely on the exact same message string or stack trace across every execution schedule**.

Complete example **RecursiveFailureDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class RecursiveFailureDemo {
    private static class FailingTask extends RecursiveTask<Integer> {
        @Override
        protected Integer compute() {
            throw new IllegalArgumentException("bad element");
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            try {
                pool.invoke(new FailingTask());
            } catch (IllegalArgumentException failure) {
                System.out.println(
                        "error=" + failure.getClass().getSimpleName());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac RecursiveFailureDemo.java
java RecursiveFailureDemo
~~~

Stdout:

~~~text
error=IllegalArgumentException
~~~

The example checks the **exception type**, rather than relying on a message that may vary when errors propagate across workers. One failing branch **does not automatically roll back other branches**; remaining branches may have already completed or still be running. If tasks have side effects, design error handling, idempotency, or data recovery at the appropriate business layer.

If `join()/invoke()` fails due to cancellation, it can throw `CancellationException`. Unlike `Future.get()`, `join()/invoke()` do not force the caller to declare `ExecutionException`; do not ignore the error path because of that.

## 11. Cancellation and Task Interruption Limits

`RecursiveTask` and `RecursiveAction` inherit `cancel(...)` from `ForkJoinTask`/`Future`. However, **do not assume `cancel(true)` will interrupt a running thread** as in some `FutureTask` usages: `ForkJoinTask` does not rely on interruption to control cancellation in that way. If your problem needs early stopping, design an appropriate cooperative stop flag, check it at safe points, and avoid publishing results before required subtasks finish.

A `ForkJoinTask` transitioning to the cancelled state does not prove that all data transformations were rolled back or that workers immediately stopped mutating state. This is especially important for `RecursiveAction`, which often modifies data in place.

Also, if you `fork()` the left branch and then computing the right branch throws an error before `join()`, the left branch may keep running. Depending on requirements, track outstanding tasks, prevent publishing incomplete results, and perform appropriate cleanup.

## 12. Do Not Use Fork/Join as a Default Blocking I/O Pool

Work stealing works well when leaf tasks are **primarily CPU-bound** and complete in finite time. When a worker waits on network, database, blocking file I/O, or long locks, that worker cannot process other branches; throughput can drop.

**ForkJoinPool.ManagedBlocker** is an advanced mechanism for declaring certain blocking operations to `ForkJoinPool` so the pool can consider adjusting workers; it does not turn every I/O task into a good Fork/Join candidate. For frequent I/O tasks, use an `ExecutorService` with dedicated queue/timeout configuration or virtual threads on Java 21+, along with downstream limits.

Do not shut down `ForkJoinPool.commonPool()` as if it belonged solely to one module. The common pool is a shared JVM resource that other APIs may use. For work that needs control over parallelism, errors, and lifecycle, create a dedicated `ForkJoinPool` as in the examples, and shut it down when no longer needed. **`shutdown()`** does not wait for all tasks to stop on its own; when completion guarantees are needed, manage wait timeouts according to the appropriate API and lifecycle.

## 13. Common Mistakes

| Mistake | Consequence | Correct Approach |
|---|---|---|
| `RecursiveAction.compute()` tries to `return sum` | Wrong return type, fails to compile | Use `RecursiveTask<Long>` |
| `RecursiveTask<Long>.compute()` omits a return on a branch | Fails to compile or wrong combine | Have a base case and return on every success path |
| Skipping `join()` on Action because "there is no result" | Parent may publish before child finishes | Join to guarantee completion |
| Forking too many tiny tasks | Scheduling/GC overhead | Use a threshold and compute one branch directly |
| Multiple Actions modifying the same index or non-thread-safe List | Data race, lost updates | Partition write regions or synchronize properly |
| Tasks adding to a global sum variable in every branch | Contention and risk of error | Return partial sums and combine |
| Calling `compute()` thinking it runs in parallel | Actually a synchronous call | Use `fork` or `submit` properly |
| Believing `fork()` always creates a new thread | Misunderstands scheduling | Pool manages workers and work stealing |
| Not controlling the base case | Deep recursion or non-termination | Ensure segments shrink monotonically |
| Treating log order as a fixed result | Scheduling order is non-deterministic | Assert results after `join`/`invoke` |
| Ignoring exceptions/cancellation | Missing results or partial side effects | Handle errors and state explicitly |
| Using Fork/Join for blocking I/O without design | Workers get occupied, pool stalls easily | Use a suitable executor or I/O model |

## 14. Selection Checklist

Answer these in order:

1. **What result must be returned from branches?** If values must be combined, prefer `RecursiveTask<V>`; if only transforming independent regions, consider `RecursiveAction`.
2. **Are the base case and threshold defined?** Is the algorithm guaranteed to terminate and avoid splitting to the point where overhead outweighs benefits?
3. **Is data partitioning exact?** Does every element fall into the right region to be processed, with no two tasks writing to the same region unintentionally?
4. **Are all required branches joined?** Even if another branch fails or the caller is cancelled, are outstanding tasks accounted for?
5. **Did you measure before and after parallelizing?** Do you have a sequential baseline, CPU utilization, GC, and partitioning cost?
6. **Is the task primarily CPU-bound?** If it involves blocking I/O, have you considered a more suitable executor/approach?
7. **Are exceptions and side effects governed by a clear policy?** Never silently treat a failed task as a success.
8. **Who owns the ForkJoinPool?** Avoid impacting the common pool and manage shutdown for dedicated pools.

**Remember:** `RecursiveTask<V>` produces **per-branch results and combines them into a final result**; `RecursiveAction` performs **work with no return value from `compute()`**, typically updating independent data regions. Both run on Java's Fork/Join and work-stealing mechanism; differences in performance and reliability come from the work-splitting algorithm, how results are combined, split thresholds, data ownership, and error handling.
