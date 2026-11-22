# `compute()`, `fork()`, and `join()` in Java Fork/Join

When a problem can be divided into independent parts, Java provides the **Fork/Join Framework** to split a large task into smaller **subtasks**, have multiple workers process them, and then combine the results. The three most commonly seen calls are `compute()`, `fork()`, and `join()`. They **do not mean the same thing**:

- **`compute()`:** the method written by the developer to describe how to solve a task; it typically checks a threshold, splits data, invokes child tasks, and combines results. Calling `compute()` directly is **a normal method call**, running on the current thread.
- **`fork()`:** submits a `ForkJoinTask` into the asynchronous execution mechanism of Fork/Join so that it can be processed by another worker. It **does not guarantee that the task will run on another thread**, nor does it wait for the task to complete.
- **`join()`:** waits for a `ForkJoinTask` to complete and retrieves its result (or propagates an error according to its contract). `join()` is not like `Thread.join()`; when called inside a Fork/Join worker, the runtime can assist progress by executing related work rather than just waiting passively.

These three operations cooperate to form the **divide → fork/compute → join → combine** pattern. Choosing the split threshold, the number of subtasks, and the waiting order is crucial: creating too many tiny tasks causes overhead, while waiting in the wrong way can lose parallelism or create dependency cycles that fail to make progress.

This article belongs to the **Fork/Join** section of **general Java concurrency** and uses Java SE 17+. It does not use Spring Framework annotations, executors, or task execution mechanisms.

## 1. What kinds of problems does Fork/Join solve?

Fork/Join shines when a large workload can be split into **relatively independent** branches, such as:

- Computing sums, min/max, or statistics over a very large array.
- Transforming data across non-overlapping index ranges.
- Processing tree structures whose branches can be computed independently.
- Divide-and-conquer algorithms: merge sort, controlled parallel search.
- CPU-bound computations that need to utilize multiple processor cores.

Array sum example:

```text
                  sum[0..16)
                   /       \
            sum[0..8)     sum[8..16)
             /    \         /     \
          [0..4) [4..8) [8..12) [12..16)
             \      \       \       /
                   child results
                       |
                   sum results
```

The intervals here follow the **`[start, end)`** convention—inclusive start, exclusive end; this avoids overlapping elements between two branches.

If the data only has 10 elements, creating multiple tasks can actually be **slower than a `for` loop**. Fork/Join is not a promise that splitting smaller is always faster: it incurs task management, scheduling, cache, and contention costs.

## 2. Related classes and interfaces

| API | Primary role |
| --- | --- |
| `ForkJoinPool` | Executor specialized for processing `ForkJoinTask`, typically using **work-stealing** |
| `ForkJoinTask<V>` | Abstract class for tasks that can be forked/joined, providing `fork`, `join`, `invoke`, and completion state |
| `RecursiveTask<V>` | Divide-and-conquer task that **returns a result of type `V`** |
| `RecursiveAction` | Divide-and-conquer task that **does not return a result** |
| `CountedCompleter<T>` | Completion model based on dependency counting, useful for certain complex algorithms |
| `ForkJoinPool.commonPool()` | JVM-wide shared pool under the Java contract; resource contention must be considered |

The two most common types encountered when learning are `RecursiveTask<T>` and `RecursiveAction`.

```java
import java.util.concurrent.RecursiveTask;

final class SumTask extends RecursiveTask<Long> {
    @Override
    protected Long compute() {
        // Compute directly or split the task.
        return 0L;
    }
}
```

This is an **illustrative class**, without a `main` method or an actual splitting algorithm yet. The `compute()` method is **overridden** from `RecursiveTask`; it is not an API of `Thread`.

When no result is needed:

```java
import java.util.concurrent.RecursiveAction;

final class PrintAction extends RecursiveAction {
    @Override
    protected void compute() {
        // Perform an action that does not return a value.
    }
}
```

An action task can still be tracked using `ForkJoinTask<?>`; it is simply that `compute()` does not return a business result.

## 3. `compute()` is execution logic, not a thread-creation command

With `RecursiveTask<V>`:

```java
@Override
protected V compute() {
    if (smallEnough()) {
        return solveSequentially();
    }

    RecursiveTask<V> left = createLeft();
    RecursiveTask<V> right = createRight();
    // Run/combine child tasks according to the Fork/Join protocol.
}
```

This is **illustrative Java pseudocode**: the referenced methods are not defined.

When a task is executed by `ForkJoinPool`, the runtime invokes the `compute()` logic through the task mechanism. On the other hand, if a developer directly calls `someTask.compute()` from somewhere with access, that is a **synchronous call on the current thread**. The name `compute` itself does not trigger parallelism.

A well-structured `compute()` typically has:

1. **Base case:** when the data segment is small enough, compute sequentially and return the result.
2. **Split:** choose a midpoint and create child tasks for independent segments.
3. **Dispatch:** `fork` one or more child tasks while processing the remaining branch.
4. **Join:** wait for/read the results of the forked tasks.
5. **Combine:** merge the results according to the operation of the original problem.

If a base case is missing or the problem size is not reduced on each recursive step, the program can create infinite tasks, overflow the stack, or exhaust memory.

## 4. What does `fork()` do?

Method:

```java
ForkJoinTask<V> fork()
```

`fork()` **schedules** the task for asynchronous execution, normally in the pool where the current worker is running. The task may be executed later by that same worker, or **stolen** by another worker via work-stealing.

Example:

```java
left.fork(); // Schedule the left branch; do not wait for the result.
int rightResult = right.compute(); // Compute immediately on the current thread.
int leftResult = left.join();      // Obtain the left branch result.
return leftResult + rightResult;
```

This is an illustrative snippet inside `compute()`, assuming `left` and `right` are valid `RecursiveTask<Integer>` instances.

**Common misconceptions:**

- `fork` is **not like `new Thread(task).start()`**. It operates on a `ForkJoinTask` inside a pool and does not create a new Java thread for each subtask.
- `fork` **does not guarantee parallel execution**. If the pool has one worker or the data is small, the result is still correct, but there is virtually no parallelism.
- `fork` **does not return the computed result**. It returns the task handle, usually the task itself to support chaining.
- Forked tasks must have their completion managed, typically with `join`, `invokeAll`, or another protocol; do not fork and forget tasks whose results matter.

Creating 1 million tasks from 1 million elements is a classic example that easily causes overhead. A stopping threshold is needed so each leaf processes a sufficiently large segment.

## 5. What does `join()` wait for, return, and how does it report errors?

For a `RecursiveTask<Long>`:

```java
long value = subtask.join();
```

`join` waits for the **specific subtask** to complete and returns its value if successful.

If the task fails with an unchecked exception, `join` can propagate the corresponding exception to the caller; you should not assume a default result like `0`. If the task is cancelled, `join` can throw `CancellationException`.

**Important:** `ForkJoinTask.join()` does not declare `InterruptedException`, and waiting in `join` is **not interruptible in the way `Future.get()` usually is**. If you need interruptible waiting or a timeout, the `ForkJoinTask` API provides `get()` / `get(timeout, unit)` under the `Future` contract; however, using those inside a worker requires careful thought about progress and dependencies. Do not arbitrarily turn an algorithm into a blocking `get` and assume work-stealing will resolve every wait cycle.

Comparison:

| Call | Purpose |
| --- | --- |
| `subtask.compute()` | Immediately compute the subtask's work on the current thread |
| `subtask.fork()` | Submit the task into Fork/Join so it can run asynchronously |
| `subtask.join()` | Wait for and retrieve the result/exception of a started task |
| `subtask.invoke()` | Start executing the task and wait for completion at the call boundary |
| `pool.invoke(task)` | Submit the root task to the pool and wait for the result |
| `ForkJoinTask.invokeAll(a, b)` | Helper to execute and wait for a group of `ForkJoinTask`s |

Fork/Join's `join` is **different** from `Thread.join()`: `Thread.join` waits for a thread to terminate and does not return a `RecursiveTask` computation result.

## 6. Standard pattern: fork one branch, compute the other

A recommended pattern in many binary-splitting algorithms:

```java
if (length <= threshold) {
    return computeSequentially();
}

var left = new SumTask(data, start, mid, threshold);
var right = new SumTask(data, mid, end, threshold);

left.fork();              // Allow another worker to pick up the left branch.
long rightSum = right.compute(); // Current thread does not sit idle waiting.
long leftSum = left.join();      // Synchronize on the left branch result.
return leftSum + rightSum;
```

This is an illustrative snippet; the variables and class are fully defined in the next example.

**Why not necessarily fork both?**

- Forking both branches creates more scheduling work when one branch could be processed immediately.
- The current worker can still do useful work on one branch while the other branch is available to be stolen.
- You only need to wait for the forked branch's result after finishing the current branch.

This is not a theorem that "forking one branch is always fastest." Performance depends on input size, partitioning strategy, locality, pool parallelism, and workload. Nevertheless, the **one fork + one direct compute + one join** pattern is easy to understand and avoids unnecessary task creation.

## 7. Java 17+ example: summing an array with `RecursiveTask<Long>`

Save as `ForkJoinSumDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    static final class SumTask extends RecursiveTask<Long> {
        private final int[] data;
        private final int start;
        private final int end;
        private final int threshold;

        SumTask(int[] data, int start, int end, int threshold) {
            this.data = data;
            this.start = start;
            this.end = end;
            this.threshold = threshold;
        }

        @Override
        protected Long compute() {
            if (end - start <= threshold) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += data[i];
                }
                return sum;
            }

            int mid = start + (end - start) / 2;

            SumTask left = new SumTask(
                    data, start, mid, threshold);
            SumTask right = new SumTask(
                    data, mid, end, threshold);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();

            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        int[] numbers = new int[16];
        for (int i = 0; i < numbers.length; i++) {
            numbers[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long result = pool.invoke(
                    new SumTask(numbers, 0, numbers.length, 4));

            System.out.println("Sum: " + result);
            System.out.println("Expected: " + (16L * 17 / 2));
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run:

```bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
```

**Exact** stdout, independent of scheduling order:

```text
Sum: 136
Expected: 136
```

Explanation:

1. The array contains the numbers 1 through 16, so the mathematical sum is 136.
2. The root task solves `[0,16)`, splitting it into two non-overlapping ranges `[0,8)` and `[8,16)`.
3. When a range has ≤4 elements, the leaf task sums sequentially without creating further child tasks.
4. Each parent forks one branch, directly computes the other branch, and then joins the forked result.
5. `long` addition prevents overflow for this small dataset; using `long` is also more appropriate than `int` for large sums.
6. No two tasks write to the array; they only read the array created before `pool.invoke`. Thus, no data race occurs on the array.
7. `pool.invoke` waits for the root task's result; `main` does not print until the entire required summation tree has finished.
8. `pool.shutdown` indicates that no new tasks will be accepted; the example does not leave a self-created pool alive indefinitely without lifecycle management.

**Do not infer that having four workers means four tasks always run simultaneously.** The contract guarantees the result, not that each leaf is executed by a different thread.

## 8. Visualizing the task tree of the sum example

With `threshold=4`:

```text
SumTask[0,16)  (parent)
├── SumTask[0,8)
│   ├── SumTask[0,4)   => 1+2+3+4       = 10
│   └── SumTask[4,8)   => 5+6+7+8       = 26
│   -> 10+26 = 36
└── SumTask[8,16)
    ├── SumTask[8,12)  => 9+10+11+12    = 42
    └── SumTask[12,16) => 13+14+15+16  = 58
    -> 42+58 = 100

Root: 36 + 100 = 136
```

The total number of `SumTask` objects created in this run is **7**: 1 root, 2 intermediate tasks, and 4 leaves. This is a fixed balanced tree, so the count of 7 can be determined independently of which worker executes which task.

**Task objects are different from threads.** Seven task objects do **not** mean seven Java threads are created. A small number of workers can process thousands of short tasks using queue/work-stealing mechanisms.

## 9. When to use `RecursiveAction` instead of `RecursiveTask`?

If a task only **transforms data** without needing to return an aggregated result, `RecursiveAction` has a `compute()` method returning `void`.

Examples:

- Computing squares and writing into different segments of the same array.
- Applying a transform to each element within non-overlapping index ranges.
- Traversing a tree and performing properly protected local operations.

Condition for safety: child tasks must have **clear data-region ownership**. If two tasks write to the same element or mutate a standard `ArrayList` concurrently, using Fork/Join does not automatically make them thread-safe.

If a task genuinely needs a result to combine, `RecursiveTask<V>` is usually more natural. There is no need to create side effects just to pass results back when the return type already supports it.

## 10. Java 17+ example: writing to non-overlapping segments

Save as `ForkJoinActionDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;

public class ForkJoinActionDemo {
    static final class SquareAction extends RecursiveAction {
        private final int[] values;
        private final int start;
        private final int end;

        SquareAction(int[] values, int start, int end) {
            this.values = values;
            this.start = start;
            this.end = end;
        }

        @Override
        protected void compute() {
            if (end - start <= 4) {
                for (int i = start; i < end; i++) {
                    values[i] = i * i;
                }
                return;
            }

            int mid = start + (end - start) / 2;
            SquareAction left = new SquareAction(
                    values, start, mid);
            SquareAction right = new SquareAction(
                    values, mid, end);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args) {
        int[] values = new int[16];
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            pool.invoke(new SquareAction(
                    values, 0, values.length));
            System.out.println(Arrays.toString(values));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinActionDemo.java
java ForkJoinActionDemo
```

Exact stdout:

```text
[0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100, 121, 144, 169, 196, 225]
```

Why is this safe?

- Each leaf writes only to **its own disjoint index range** of the array; no two writers access the same slot.
- Each parent waits via `join()` for its forked branch, so the root task completes only after all branches have finished updating.
- `main` reads the array **after `pool.invoke(...)`** returns; the synchronization relationship upon completion guarantees visibility of all completed updates.
- If you replaced the assignment with `values[i]++` on **overlapping** segments, a different design would be required; you must not expect Fork/Join to automatically prevent data races.

## 11. Does `fork()` followed immediately by `join()` create useful parallelism?

A performance anti-pattern:

```java
left.fork();
long leftValue = left.join(); // Wait immediately.
long rightValue = right.compute();
return leftValue + rightValue;
```

This is an illustrative snippet inside `compute()`. The current worker does not proactively work on the right branch before waiting for the left branch. The Fork/Join runtime may assist progress during `join`, but this style usually **misses an obvious opportunity** for the current worker to compute the remaining branch.

Usually better:

```java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
```

These snippets assume `left`/`right` and `long` result variables are already declared.

Not every early `join` is a deadlock. It is primarily a work-organization and performance mistake. A **true deadlock** can happen if a task waits on a circular dependency, holds an unreleased lock, or blocks on a resource that only the awaited task can provide.

Practical rule: **do not wait for a subtask while the current thread still has an independent branch it can compute right away.**

## 12. `fork()` vs. `invoke()` and `pool.invoke()`

Three easily confused methods:

```java
left.fork();         // Schedule; do not wait yet.
Long a = left.join(); // Wait for the forked task and get the result.

Long b = right.invoke(); // Execute + wait for the task immediately.

Long c = pool.invoke(root); // Submit the root task to the pool + wait.
```

This is an illustrative snippet; the variables are not declared within a complete class.

**Key distinctions:**

- `ForkJoinTask.invoke()` starts execution and waits for this task to complete in the Fork/Join manner.
- `ForkJoinPool.invoke(task)` is a convenient entry point from an external thread into the pool: the pool processes the root task and the caller waits for the result.
- `ForkJoinPool.execute(task)` submits a task **without waiting** for completion at the call site; keep the handle if you need to `join`/`get` later.
- `ForkJoinPool.submit(task)` returns a task/future handle, allowing the caller to manage completion via the API.
- `fork()` is convenient **inside Fork/Join work** to spawn subtasks that can be picked up by other workers.

When application code creates its own pool, calling `pool.invoke(root)` is usually clearest for a synchronous computation that needs a result. It is unnecessary to manually call `root.fork()` on the `main` thread followed by `root.join()`; reasoning about which pool executes the task can become difficult if different pools are mixed.

## 13. What is the benefit of `invokeAll`?

`ForkJoinTask.invokeAll(left, right)` is a fork/join utility for a **group of tasks**. It arranges execution and waits for the group to complete according to the Fork/Join protocol, after which the caller can retrieve results from those tasks.

```java
ForkJoinTask.invokeAll(left, right);
return left.join() + right.join();
```

This is an illustrative snippet inside a `RecursiveTask<Integer>`, with `left`/`right` as integer-typed child tasks.

Advantages: readable when there are multiple equivalent subtasks, and you do not have to write every `fork`/`join` call manually. However, for algorithms that can process one branch inline, the one-fork-one-compute pattern sometimes reduces overhead. **Benchmark with a realistic workload** to choose.

When a child task fails, you must understand the group's exceptional completion policy; do not assume that tasks with existing side effects are automatically rolled back when another task throws.

## 14. Java 17+ example: using `ForkJoinTask.invokeAll`

Save as `ForkJoinInvokeAllDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.RecursiveTask;

public class ForkJoinInvokeAllDemo {
    static final class CountEvenTask extends RecursiveTask<Integer> {
        private final int start;
        private final int end;

        CountEvenTask(int start, int end) {
            this.start = start;
            this.end = end;
        }

        @Override
        protected Integer compute() {
            if (end - start <= 4) {
                int count = 0;
                for (int i = start; i < end; i++) {
                    if ((i & 1) == 0) {
                        count++;
                    }
                }
                return count;
            }

            int mid = start + (end - start) / 2;
            CountEvenTask left = new CountEvenTask(start, mid);
            CountEvenTask right = new CountEvenTask(mid, end);

            ForkJoinTask.invokeAll(left, right);
            return left.join() + right.join();
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(3);
        try {
            int count = pool.invoke(new CountEvenTask(0, 20));
            System.out.println("Even numbers in [0,20): " + count);
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinInvokeAllDemo.java
java ForkJoinInvokeAllDemo
```

Exact stdout:

```text
Even numbers in [0,20): 10
```

The even numbers in `[0, 19]` are `0,2,4,...,18`: 10 in total. The root and child tasks only process non-overlapping integer ranges. `invokeAll` is a **subtask management helper**; it does not perform the addition for our code.

In some algorithms, `invokeAll` has different overhead than manually forking one branch and computing the other; changing the scheduling approach does not change the mathematical result if each task is written correctly and has no improper shared side effects.

## 15. Work-stealing: why doesn't Fork/Join create a thread per subtask?

`ForkJoinPool` has a relatively bounded set of workers. During divide-and-conquer, a worker typically manages a queue/deque of spawned tasks. An idle worker can **steal** unprocessed tasks from another worker.

Conceptual view:

```text
Worker A                         Worker B
--------                         --------
computing(root)                  idle
fork(left)
compute(right)                   steal(left)
  |                                |
  |                                compute(left)
  |                                |
right result                     left result
  |                                |
join(left) <-----------------------+
combine
```

This diagram shows a **possible mechanism**, not a guarantee that the left task always runs on worker B.

Key truths to remember:

- Work-stealing helps balance load when branches have varying computation lengths.
- In common implementations, local tasks and stolen tasks use different retrieval policies to improve locality and reduce contention, but **you should not write logic that depends on a specific FIFO/LIFO processing order**.
- A pool with `parallelism = 4` does not mean a task is split into exactly four branches.
- A task can run on the same worker that forked it; another idle worker does not need to exist.
- Work-stealing does not solve data races, long blocking I/O, or logical dependency cycles.

## 16. The threshold determines task granularity

In the array example, the condition:

```java
if (end - start <= threshold) {
    return computeSequentially();
}
```

sets a limit on leaf size. This is an illustrative snippet.

**Threshold too small:**

- Many task objects.
- Many fork/join operations and queue management calls.
- Overhead can exceed the computation time.
- Limits cache/locality benefits and increases GC pressure.

**Threshold too large:**

- Few branches processed in parallel.
- One worker may hold a very large data segment while others sit idle.
- Missed load-balancing opportunities.

**How to choose?** Measure your actual workload and per-element processing cost. An array of a few dozen elements does not need parallelism; an array of tens of millions of elements with significant CPU operations may be worth splitting. The threshold of 4 in the demos is solely to **make the split tree clearly visible**, not a recommended production setting.

A rule of thumb is to create enough leaves to balance workers while ensuring each leaf does **enough useful work** to offset overhead. There is no universal threshold number for every CPU or algorithm.

## 17. Java 17+ example: counting `compute()` invocations to observe split cost

Save as `ForkJoinTaskCountDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinTaskCountDemo {
    static final class CountingSum extends RecursiveTask<Long> {
        private final int start, end, threshold;
        private final AtomicInteger tasksSeen;

        CountingSum(int start, int end, int threshold,
                    AtomicInteger tasksSeen) {
            this.start = start;
            this.end = end;
            this.threshold = threshold;
            this.tasksSeen = tasksSeen;
        }

        @Override
        protected Long compute() {
            tasksSeen.incrementAndGet();

            if (end - start <= threshold) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += i + 1L;
                }
                return sum;
            }

            int mid = start + (end - start) / 2;
            CountingSum left = new CountingSum(
                    start, mid, threshold, tasksSeen);
            CountingSum right = new CountingSum(
                    mid, end, threshold, tasksSeen);

            left.fork();
            long r = right.compute();
            return left.join() + r;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(4);
        AtomicInteger seen = new AtomicInteger();

        try {
            long sum = pool.invoke(
                    new CountingSum(0, 16, 4, seen));
            System.out.println("Sum: " + sum);
            System.out.println("Compute invocations: " + seen.get());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinTaskCountDemo.java
java ForkJoinTaskCountDemo
```

Exact stdout:

```text
Sum: 136
Compute invocations: 7
```

Because the logical array has 16 elements and a threshold of 4, the fixed split tree consists of 1 root, 2 internal tasks, and 4 leaf tasks. Each object executes `compute()` exactly once, so the atomic counter reaches 7, **regardless of which task runs first**.

Counting tasks is not a throughput benchmark. If you change the threshold to 1, the task tree will be larger, yet the mathematical result remains 136 when the algorithm is correct. For real optimization, measure elapsed time on sufficiently large inputs after proper warm-up while controlling CPU/load.

## 18. Data costs and correctness of the combine operation

To split and combine safely, the combine operation generally needs suitable properties:

- Sum: `left + right`, watching for overflow.
- Min/max: `Math.min(left, right)` or `Math.max(...)`.
- Count: sum the counts.
- List concatenation: pay attention to **order** and ownership.
- Floating-point operations: changing the addition order can change rounding.

For example, with `double`, floating-point addition is **not strictly associative** due to rounding errors:

```text
(a + b) + c  is not necessarily ==  a + (b + c)
```

Therefore, a Fork/Join algorithm aggregating floating-point numbers may produce a bitwise-different result from a sequential loop because the combine order differs. If exact reproducibility is required, you must define a stable combine tree, numeric type, and error policy.

For mutable results (such as `ArrayList`), each leaf should create its **own result**, and the parent should merge them after `join`. Avoid having multiple tasks call `add` on a shared `ArrayList` without synchronization; that can cause races and structural corruption.

## 19. Does input data need to be immutable?

Not all inputs have to be immutable, but there must be **clear ownership rules**.

Common safe pattern:

1. Finish populating an `int[]` before submitting the root task.
2. Subtasks only **read** that array.
3. No other thread modifies the array while the computation is running.
4. Read the result only after the root task completes.

With `RecursiveAction` writing to an array, child tasks must own **non-overlapping index regions**. An external thread outside the task tree modifying the same indices while tasks run breaks this assumption.

`ForkJoinTask.join()`/completion and submission provide the necessary memory consistency guarantees to publish data according to the protocol. However, they **do not** make regular collections like `ArrayList`, `HashMap`, or shared mutable objects thread-safe if multiple writers contend on them.

If an algorithm needs a shared accumulator, it is usually better for **each task to return its own result and combine them**, rather than using a high-contention shared counter.

## 20. `join()` does not resolve dependency cycles

A serious logic bug is creating tasks that depend on each other in a cycle:

```text
Task A needs join(Task B)
Task B needs join(Task A)
```

Neither task can complete before the other. Even though the pool has work-stealing, **the algorithm is still broken**.

Logic-level anti-pattern example:

```java
// Illustrates a flawed idea, not a runnable program.
ForkJoinTask<?> a = ...;
ForkJoinTask<?> b = ...;

// a waits on b, b waits on a -> dependency cycle.
```

In the snippet above, `...` is illustrative notation that is invalid if compiled; **do not run**.

A dangerous variant is **holding a monitor while joining**:

```java
synchronized (lock) {
    child.fork();
    child.join(); // If child needs lock, this can deadlock.
}
```

This is an illustrative snippet with `child` and `lock` defined elsewhere. If `child` needs to acquire `lock` to complete, the parent holds the lock while waiting for `child`: the wait cycle may never break on its own.

**Rule:** do not wait on a subtask that might need a resource/monitor currently held by the parent, and do not create dependency cycles between subtasks.

## 21. Blocking I/O and `ForkJoinPool`

Fork/Join is primarily optimized for many splittable computational tasks. If each task calls socket reads, JDBC, long `Thread.sleep`, or `Future.get()` waiting on work in another pool, workers can become blocked, reducing the number of active workers.

Work-stealing does not guarantee spawning enough extra workers to compensate for every blocking call. Some situations can use `ForkJoinPool.ManagedBlocker` via `ForkJoinPool.managedBlock(...)`, giving the pool a chance to manage blocking more appropriately, but this requires designing a contract-compliant blocker and **must not be applied blindly**.

When a workload is mostly blocking I/O and lacks a divide-and-conquer structure, it is usually more sensible to use an `ExecutorService` or another suitable concurrency model rather than forcing everything into `RecursiveTask`.

**Do not equate a Fork/Join `join` waiting on a subtask with an external network wait.** The runtime understands the pool's own task structure far better than an arbitrary blocking operation performed by a task.

## 22. How do errors in `compute()` propagate?

If a child task throws an unchecked exception or `Error`, the task can complete **abnormally**. A parent calling `join()` or root calling `pool.invoke(...)` will observe the error per the Fork/Join contract; there is no valid numeric result for that failed branch.

Example of a task intentionally rejecting negative input.

Save as `ForkJoinExceptionDemo.java`:

```java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinExceptionDemo {
    static final class ValidateTask extends RecursiveTask<Integer> {
        private final int input;

        ValidateTask(int input) {
            this.input = input;
        }

        @Override
        protected Integer compute() {
            if (input < 0) {
                throw new IllegalArgumentException("negative input");
            }
            return input * 2;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            try {
                pool.invoke(new ValidateTask(-3));
            } catch (IllegalArgumentException e) {
                System.out.println("Rejected: " + e.getMessage());
            }
            System.out.println("Good result: "
                    + pool.invoke(new ValidateTask(5)));
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ForkJoinExceptionDemo.java
java ForkJoinExceptionDemo
```

Exact stdout:

```text
Rejected: negative input
Good result: 10
```

A failing task **does not automatically shut down the entire pool**; afterward, the pool can still run valid tasks if it remains active. However, if a parent forked multiple tasks and one throws an error, the other branches may have already produced side effects. Do not treat an exception as a multi-task transaction rollback.

If you need to aggregate errors from multiple tasks, define a clear exception-handling and cancellation policy; do not just catch and return `0`, corrupting the business result.

## 23. `join()` and `get()`: interruption, timeout, exception

`ForkJoinTask` implements `Future<V>`, so familiar operations can be used:

| Method | General behavior |
| --- | --- |
| `join()` | Waits for task completion via Fork/Join, returns result or throws unchecked/cancellation exception |
| `get()` | Waits for completion per the `Future` contract, with `InterruptedException` and `ExecutionException` as appropriate |
| `get(timeout, unit)` | Waits with a time limit, may throw `TimeoutException` |
| `cancel(...)` | Attempts to cancel the task; does not mean the worker stops immediately |
| `isDone()` | Task has reached a completed state, including normal/exceptional/cancelled |
| `isCompletedNormally()` | Task completed normally |
| `isCompletedAbnormally()` | Task completed with an exception or cancellation, per the `ForkJoinTask` contract |

When using timed `get`, **the timeout only limits the caller's wait**, not the running task itself. The task may finish later and return its result on another `get` call. If you need to request termination, you must have a separate cancellation policy.

An important nuance: per its contract, `ForkJoinTask.cancel(boolean)` does not use the `mayInterruptIfRunning` parameter to control execution interruption like some other `Future` implementations. Do not assume from `cancel(true)` that a `ForkJoinTask` will be interrupted directly.

In real applications, avoid using `join()` to wait on external I/O; it is meant for **dependencies between `ForkJoinTask`s** in a computation tree.

## 24. Managing cancellation in a task tree

Cancelling a root task does not automatically prove that every spawned subtask has stopped its side effects or cleaned up. Parallel cancellation is more complex than a single flag because multiple branches may have already started.

To design a cooperatively cancellable task tree, you need:

- A **cancellation token** (such as an `AtomicBoolean`) shared across branches when appropriate.
- **Checkpoints** that inspect the token before splitting further or doing expensive work.
- Limits on the number of tasks spawned after cancellation has been requested.
- Rules for handling subtasks already forked but not yet joined (join/cancel/cleanup per contract).
- Resource ownership management so files, connections, or locks are not leaked.
- A final result that distinguishes normal completion, partial work, failure, and cancellation.

Example snippet:

```java
if (cancelled.get()) {
    return 0L; // Only valid if the contract allows a partial result.
}
```

This is an illustrative snippet; `cancelled` belongs to the application. **Do not automatically return 0 on cancellation if the caller could interpret it as a valid sum.** In many APIs, it is better to report a cancelled status or throw an exception so invalid data does not look like success.

Also, `Thread.interrupt()` does not force every CPU-bound subtask to stop; code must cooperatively check the signal.

## 25. `ForkJoinPool.commonPool()` vs. custom pools

`ForkJoinPool.commonPool()` is a shared pool used by many APIs and library code. `ForkJoinTask.fork()` operations in certain contexts outside a worker may involve the common pool under the `ForkJoinTask` contract.

The advantage of the common pool is not having to create a separate pool for every small computation. Disadvantages:

- Unrelated tasks can **compete for workers and throughput**.
- An application with poorly suited blocking code can affect other users of the pool.
- The common pool's lifecycle **is not owned by any individual component**; do not shut it down arbitrarily as you would a private pool.
- You cannot rely on the default parallelism being a fixed number across all machines/JVMs.
- Security policies, resource limits, or runtime configurations may alter actual behavior.

If you need resource isolation or control over parallelism, create `new ForkJoinPool(parallelism)` and manage `shutdown` when done; however, creating a private pool for **every single request** is usually wasteful.

In this article's examples, each program creates its own pool to demonstrate clear ownership and avoid depending on common pool contention.

## 26. Parallelism does not equal task count

Example:

```java
ForkJoinPool pool = new ForkJoinPool(4);
```

This is an illustrative snippet, not a complete program.

`4` is the **target parallelism level**/configuration for the pool's workers, not a promise that exactly four tasks are running at every instant.

A tree with 100 leaf tasks can still be processed over time by a small group of workers. Conversely, a task may execute completely sequentially if the threshold is too large and creates no branches.

Factors affecting throughput:

- Actual number of CPU cores and load from other applications.
- Cost of each leaf; overly small tasks cause overhead.
- Balance of the split tree.
- Number of idle workers available to steal work.
- Memory bandwidth costs and cache misses.
- Contention from shared locks/atomics.
- Blocking time inside tasks.
- Result-combining and object-allocation costs.

Do not benchmark with just one small input; use realistic inputs, warm-up, multiple runs, controlled JVM/GC conditions, and no logging in inner loops.

## 27. Common mistakes

**1. "Calling `compute()` creates a new thread."** False. `compute` is task logic; calling it directly is a method call on the current thread.

**2. "`fork()` is equivalent to `Thread.start()`."** False. `fork` schedules a `ForkJoinTask`; it does not create a new thread for every subtask.

**3. "`fork()` guarantees parallel execution."** False. The pool may use the same worker, or the task may never have a chance to be stolen.

**4. "`join()` is only for joining `Thread`s."** False. `ForkJoinTask.join` waits for **a task and its result**, unlike `Thread.join` which waits for a thread to terminate.

**5. "Forking both branches and joining immediately is always best."** Not by default. One-fork-one-compute can have less overhead and avoid unnecessary waiting.

**6. "Smaller thresholds are always faster."** False. Too many tiny subtasks waste time on scheduling and object allocation.

**7. "Using Fork/Join makes a shared `ArrayList` thread-safe."** False. Shared mutable state requires explicit synchronization or ownership.

**8. "`join` will rescue any dependency deadlock."** False. Dependency cycles or holding a monitor while joining can prevent progress.

**9. "When one task throws an exception, all side effects of other tasks are rolled back."** False. Other subtasks may have already written to data or external resources.

**10. "`ForkJoinPool(4)` guarantees four tasks are always running."** False. `parallelism` is a target concurrency configuration, not the exact active task count at every moment.

**11. "`join()` must declare `throws InterruptedException`."** False. `join` does not declare checked interruption; `Future.get` can do that.

**12. "A `get(timeout)` timeout automatically cancels the task."** False. It only times out the wait call.

**13. "`ForkJoinTask.cancel(true)` always interrupts the worker."** False. That parameter does not have the same effect under the `ForkJoinTask` contract.

**14. "Fork/Join is best suited for all blocking I/O."** No. It favors divide-and-conquer computation; unmanaged blocking can starve workers.

**15. "A completed task always means a successful business result."** No. `isDone` can include abnormal completion or cancellation; you must check status properly.

**16. "The common pool can be shut down arbitrarily by a component."** Wrong about ownership. The shared pool does not belong to any single task.

**17. "A task can fork itself and then join itself."** Wrong about dependencies: creating a wait cycle on the same task is a design bug.

**18. "`double` addition results always match sequential order."** Not guaranteed due to differing floating-point rounding across the combine tree.

## 28. Fork/Join algorithm review checklist

1. **Can the problem be split into independent branches?** If not, Fork/Join may complicate the code without speeding it up.
2. **Does the base case shrink to a guaranteed stopping threshold?** If not, there is a risk of infinite recursion.
3. **Do `[start,end)` ranges cover all data without overlapping?** Check odd counts, empty arrays, and size 1.
4. **Was the threshold chosen based on processing cost or just guessed?** Overly small tasks cause overhead.
5. **Is one branch forked and another computed inline where appropriate?** Avoid joining too early.
6. **Are all necessary forked tasks joined or completion-managed?** Do not leave unfinished results ignored.
7. **Is the combine operation mathematically sound?** Including overflow and floating-point non-associativity.
8. **Is the input immutable, safely published, or properly owned?** Prevent concurrent external writes if unsynchronized.
9. **Is there a shared mutable accumulator?** Consider local results combined afterward instead of lock/atomic contention.
10. **Are there callbacks or blocking I/O inside `compute`?** If so, consider another architecture or proper managed blocking.
11. **Are there dependency cycles or waits while holding a monitor?** These are real deadlock sources.
12. **Do exceptions or cancellations leave partial side effects?** Define how failures and cleanup are reported.
13. **Which pool executes the root/subtasks?** Avoid mixing pools with unclear ownership.
14. **Are outputs tested independently of scheduling order?** Use small examples with known mathematical results.
15. **Have you benchmarked a real workload?** Compare against a sequential loop while controlling input, JIT, and GC.
16. **Are custom pools closed after use?** Use proper `shutdown`/lifecycle management.
17. **Are you avoiding overfitting on `getStealCount` or pool metric snapshots?** Observed metrics are not correctness conditions.

## 29. Self-check questions

**Question 1.** Does `compute()` automatically create a new thread when called directly?

**No.** It is a method overridden from `RecursiveTask`/`RecursiveAction`. Calling it directly runs on the current thread; to have a pool manage the task, submit/invoke it via `ForkJoinPool` or organize fork/join in the proper context.

**Question 2.** Does `fork()` guarantee the branch runs immediately on another worker?

**No.** It schedules the task for Fork/Join processing. Another worker **may** steal it, but the same worker can also execute it.

**Question 3.** What does `join()` return for a `RecursiveTask<Long>`?

When the task completes normally, it returns that task's `Long` result. When the task fails or is cancelled, the caller must handle the corresponding exception.

**Question 4.** Why do we often write `left.fork(); right.compute(); left.join();`?

Because the current worker does useful work on the right branch while the left branch can be executed by another worker, instead of joining `left` immediately and leaving `right` uncomputed.

**Question 5.** How many `SumTask` instances are created for 16 elements split in half down to a threshold of 4 in the balanced example?

**7**: 1 root, 2 internal, and 4 leaf tasks. Task count does not equal thread count.

**Question 6.** How does `RecursiveAction` differ from `RecursiveTask<V>`?

`RecursiveAction.compute` returns `void` and suits tasks that only perform controlled side effects; `RecursiveTask<V>.compute` returns a `V` result for the parent to combine.

**Question 7.** If one leaf writes to the same index as another leaf in an `int[]`, is it safe just because they share a `ForkJoinPool`?

**No.** Writing to overlapping regions can cause a data race. Partitioned ownership or proper synchronization is required.

**Question 8.** Do `ForkJoinTask.join()` and `Future.get()` share the same interruption contract?

**No.** `join` does not declare `InterruptedException`; `get` supports interruptible waiting per the `Future` contract and has a timeout overload.

**Question 9.** How does `pool.invoke(root)` differ from `root.fork()`?

`pool.invoke` submits the root task to the **chosen pool** and waits for the result. `fork` schedules the task in the caller's Fork/Join context and does not wait for completion at the call site.

**Question 10.** Why doesn't a child task throwing an exception roll back other tasks?

Because Fork/Join is an in-memory scheduling/completion mechanism, not a transaction manager. Other side effects may have already occurred.

**Question 11.** Should a CPU-bound task doing 10 additions be split into 10 `RecursiveTask`s?

Normally no. Task creation and scheduling overhead can outweigh the computation; pick a large enough threshold or run sequentially.

**Question 12.** When should Fork/Join be avoided?

When work cannot be split independently, has heavy cross-dependencies, consists mostly of unmanaged blocking I/O, or requires durable/distributed execution semantics that `ForkJoinPool` does not provide.

## 30. Summary

- **`compute()`** is the task-solving logic; it defines the base case, splits branches, and combines results.
- **`fork()`** schedules a subtask for potential asynchronous execution in Fork/Join; it does not create a separate thread per task and does not guarantee parallel execution.
- **`join()`** waits for a forked task to finish and retrieves its result, with `ForkJoinTask` exception/cancellation semantics; it is not `Thread.join()`.
- For divide-and-conquer, the **fork one branch → compute the other branch → join the forked branch → combine** pattern keeps workers doing useful work and reduces some overhead.
- **`RecursiveTask<V>`** is used when a result is needed; **`RecursiveAction`** is for actions that return no value. `invokeAll` is a helper to execute and wait for a group of subtasks.
- **Work-stealing** balances tasks across workers; there can be many more tasks than threads, and execution order must not be assumed for correctness.
- **Threshold, data ownership, and the combine operation** determine performance and correctness. Creating overly small tasks, writing to shared regular collections, or holding monitors while joining can all cause bugs.
- **Exceptions, cancellations, and timeouts** have their own contracts; Fork/Join does not automatically roll back side effects, is not suited for all blocking I/O, and does not provide hard real-time guarantees.
- Create a **private pool with clear ownership and shutdown** when resource isolation is needed; never shut down the shared common pool.

In every Fork/Join algorithm, ask yourself: **"Which parts can execute independently in parallel, which parts should be computed directly, and what condition guarantees all branches are done before I combine the results?"** Answering these three questions will guide you to use `compute()`, `fork()`, and `join()` far more accurately than relying on method names alone.