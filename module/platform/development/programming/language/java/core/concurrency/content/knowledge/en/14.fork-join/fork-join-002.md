# ForkJoinPool and Work Stealing in Java

`ForkJoinPool` is an executor specialized for problems that can be **split into subtasks (fork)** and then **combined for results (join)**. Instead of having only a single centralized work queue where each thread picks up one complete task, workers in the pool can create additional subtasks while processing a large problem. **Work stealing** allows an idle worker to take pending work from another worker, helping balance load more effectively across uneven recursive branches.

This is not a magic bullet that makes every Java program run faster. `ForkJoinPool` works best when work can be split into units **large enough to offset fork/join overhead**, relatively independent, with minimal blocking I/O, and with a clear result-merging path. If tasks mainly make network calls, wait on locks, or require strict sequential ordering, a different task decomposition and executor may be more appropriate.

This Knowledge article belongs to **Fork/Join in Java Concurrency in general**. We will cover the divide-and-conquer model, worker deque and work-stealing mechanics, the `RecursiveTask`/`RecursiveAction` APIs, splitting thresholds, the common pool, blocking, exceptions, cancellation, runtime observation, and **Java 17+** examples. Spring-specific integrations belong to a separate chapter.

## 1. Why understand the pool's execution schedule?

`ForkJoinPool` schedules `ForkJoinTask` instances across workers and supports work stealing to balance uneven large/small branches. Each task is a unit of work, not a thread; the algorithm still requires a proper base case, splitting logic, and combination logic.

For an array sum problem, you can fork one half, compute the other half, and then join the results. This article dives into **per-worker deques, local task-taking policies, and task stealing**; work stealing does not guarantee execution order or speedup across every workload.
## 2. Basic Architecture of ForkJoinPool

`ForkJoinPool` resides in `java.util.concurrent`, extends `AbstractExecutorService`, and implements `ExecutorService`. It can accept tasks from threads outside the pool via `invoke`, `execute`, or `submit`, while optimizing tasks that spawn multiple child branches from running workers.

Key components:

| Component | Function |
| --- | --- |
| **ForkJoinPool** | Manages workers, execution scheduling, target parallelism level, lifecycle, and metrics. |
| **ForkJoinWorkerThread** | A worker running multiple `ForkJoinTask` instances; capable of helping process pending tasks from other workers. |
| **Internal work deque / queue** | Holds a worker's runnable tasks, supporting local popping and stealing according to the implementation policy. |
| **ForkJoinTask<V>** | Lightweight task for fork/join, with `fork()`, `join()`, `invoke()`, and completion status APIs. |
| **RecursiveTask<V>** | Recursive task base class that returns a value from `compute()`. |
| **RecursiveAction** | Recursive task base class that returns no value (`compute()` returns `void`). |
| **CountedCompleter<V>** | Variant using a completion count, suited for decomposition algorithms not structured as a simple join tree. |
| **Work stealing** | Idle workers look for pending tasks from other workers, reducing imbalance across branches. |

A `ForkJoinPool` is not "one thread per task." Many small tasks are executed across a number of workers bounded by the target parallelism. A new task does not necessarily create a new thread.

### 2.1 Regular executor work queue vs. work deque

In a traditional fixed thread pool, the intuitive model is typically:

~~~text
submission queue: [task A] [task B] [task C]
                   |        |        |
                 worker 1 worker 2 worker 3
~~~

With Fork/Join, while a worker executes task A, it can create A1, A2, A3; another worker, if idle, can take a task from the unexecuted branches:

~~~text
Worker 1: processing A
          local deque: [A1] [A2] [A3]
                            |
Worker 2: no tasks          +-- steal a waiting task
Worker 3: can process its own branch
~~~

This is a conceptual diagram, **not a guarantee** that queues always hold this exact order. Actual JVM data structures and optimizations may vary across JDK versions.

## 3. How does work stealing operate?

In the standard Fork/Join model, each worker typically prioritizes **its own tasks**; when it has no suitable local work left, it attempts to take tasks from other queues in the pool.

Intuition of the two ends of a deque:

~~~text
                   Worker A's deque
              old end            new end
             [T1] [T2] [T3] [T4]
               ^              ^
               |              |
       other worker steals  Worker A takes local
       from opposite end    from the active end
~~~

In default fork/join mode, **local work tends toward LIFO (last-in, first-out)**, whereas **stealing typically takes from the opposite end**, closer to older tasks. This idea helps a worker that just forked a branch continue processing work close to its current data, while an idle worker picks up another branch that usually has a larger scope to exploit parallelism.

However, do not build a program assuming "task T4 is guaranteed to run before T1":

- The scheduler, worker states, and external submissions alter execution order.
- The pool has queues for external (non-worker) submissions, not just one deque per worker.
- Certain helper paths during `join()` may cause a worker to execute the task it is waiting on or related tasks.
- JDK versions, contention levels, and the `asyncMode` option can change scheduling details.
- `getStealCount()` is an **approximate** monitoring metric, not a counter guaranteed to reflect every exact interleaving at all times.

### 3.1 Why is stealing from the opposite end useful?

If the owner has just created a sequence of nearby tasks, it can process them locally with minimal contention against other workers. An idle worker takes a task from the opposite end, which often corresponds to an earlier-created branch with more remaining work. Having workers **avoid contending on the same end of the deque** reduces coordination overhead in many workloads.

This is a design goal, not a guarantee of perfectly balanced load. If an algorithm creates one very heavy task and thousands of nearly empty tasks, stealing still cannot automatically split that single heavy task into parts if `compute()` does not split it further.

### 3.2 Work stealing does not mean preemption

Worker B "steals" an **unexecuted or pending task in the scheduling structure**; it does not interrupt instructions of a task currently running on Worker A to take half its stack. If a leaf task is running long CPU work without forking further, idle workers cannot automatically subdivide that leaf.

Therefore, threshold design and problem decomposition matter more than the number of threads created.

## 4. RecursiveTask and RecursiveAction: choosing the right type

| Type | Method to implement | When to use |
| --- | --- | --- |
| `RecursiveTask<V>` | `protected V compute()` | Need to return results from tasks and combine them, such as sum, min/max, search, statistics. |
| `RecursiveAction` | `protected void compute()` | Perform operations without returning a result, such as transforming **non-overlapping** segments of an array. |
| `CountedCompleter<V>` | `compute()` with pending count/completion protocol | Completion/processing graph does not fit direct branch joining; requires understanding a more complex lifecycle. |

All of them are forms of `ForkJoinTask`. You can use `fork()` to schedule a subtask and `join()` to retrieve its result. Depending on the problem, a parent task can call `compute()` directly on another branch to reduce the number of forked tasks.

Common pattern for `RecursiveTask<Long>`:

~~~java
if (rangeSmallEnough) {
    return sequentialCompute();
}

Task left = new Task(start, mid);
Task right = new Task(mid, end);

left.fork();              // Let the left branch run asynchronously.
long rightResult = right.compute();  // Compute the right branch directly.
long leftResult = left.join();        // Get the left branch result when needed.
return leftResult + rightResult;
~~~

This is **illustrative pseudocode**; you need to define `Task`, `rangeSmallEnough`, `sequentialCompute()`, data types, and overflow handling according to the problem. Forking one branch and computing the other directly generally reduces queue pressure compared to forking both and immediately waiting.

## 5. Java 17+ Example: Summing with RecursiveTask

Create `ForkJoinSumDemo.java`:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;

public final class ForkJoinSumDemo {
    private static final class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2_048;
        private final long[] numbers;
        private final int start;
        private final int end;

        SumTask(long[] numbers, int start, int end) {
            this.numbers = numbers;
            this.start = start;
            this.end = end;
        }

        @Override
        protected Long compute() {
            if (end - start <= THRESHOLD) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += numbers[i];
                }
                return sum;
            }

            int mid = start + (end - start) / 2;
            SumTask left = new SumTask(numbers, start, mid);
            SumTask right = new SumTask(numbers, mid, end);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        long[] data = new long[100_000];
        for (int i = 0; i < data.length; i++) {
            data[i] = i + 1L;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            long sum = pool.invoke(
                    new SumTask(data, 0, data.length));
            System.out.println("Sum: " + sum);
            System.out.println("Expected: 5000050000");
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
~~~

Stdout when there is no external interruption:

~~~text
Sum: 5000050000
Expected: 5000050000
~~~

### 5.1 Step-by-step explanation

- The root task manages the range `[0, 100000)` and returns `Long`.
- Ranges larger than `2048` elements keep splitting at the midpoint; smaller ranges are computed sequentially in the leaf.
- `left.fork()` allows the left branch to be processed by the current worker or another worker.
- `right.compute()` runs the right branch directly on the current thread, avoiding forking an extra task just for that work.
- `left.join()` ensures the left branch result is received before adding the two sums. It may already be finished or require waiting/helping with work.
- The data array is read-only after submission; each leaf reads a distinct range. There is no shared mutable accumulator needing `synchronized`.
- The sum from 1 to 100000 is `100000 * 100001 / 2 = 5000050000`; `long` is used to avoid `int` overflow.
- A dedicated pool is created with target parallelism 4, then shut down and awaited in `finally`. The program does not require exactly 4 workers to actually run concurrently.

**Note:** `THRESHOLD=2048` is an illustrative value, **not an optimal formula** for every CPU/dataset. For a 100000-element array, a sequential loop can even be faster than fork/join due to overhead. This exercise demonstrates **the right model**, not a specific speed claim.

### 5.2 Protecting input data

`numbers` is a reference to a mutable array. Passing the reference into a task does not freeze the array. The example is only safe because `main` **does not modify `data`** while `pool.invoke` is running. If another thread modifies elements concurrently, the result may not represent a consistent snapshot. You can copy the input before submitting or use appropriate ownership/synchronization.

## 6. Why fork one branch, compute the other, and join the forked one?

A wasteful pattern is:

~~~java
left.fork();
right.fork();
return left.join() + right.join();
~~~

This is an illustrative snippet. It can be correct in terms of results if the tasks are independent, but it increases scheduling calls for both branches and then immediately waits, sometimes causing unnecessary overhead.

Common pattern:

~~~java
left.fork();
long rightValue = right.compute();
return left.join() + rightValue;
~~~

It utilizes the current thread for one branch while the other branch can be stolen. However, this is a **heuristic**, not an absolute performance rule; tree structure and data can make the choice of which branch to fork matter. With uneven decomposition, you should give a branch with substantial work the opportunity to run in parallel and avoid creating too many tiny tasks.

### 6.1 Do not call fork then immediately join without parallel work

~~~java
left.fork();
return left.join(); // Wasteful if there is no other independent work.
~~~

The snippet above provides little parallel opportunity for the current thread. Optimization only makes sense when, while `left` is running, the current worker has **other work to do** or another worker is ready to pick up the task. For a fork/join tree, calling `compute` directly on one branch is usually appropriate.

### 6.2 The task tree must terminate

A common bug is splitting without shrinking the size:

~~~java
if (size > THRESHOLD) {
    // Spawn new tasks with the same start/end.
}
~~~

This is buggy pseudocode. Each split must reduce the problem domain and have a guaranteed leaf/base case. Otherwise, it can cause infinite recursion, `StackOverflowError`, or spawn countless tasks and exhaust memory.

## 7. RecursiveAction: processing independent data regions

If no return value is needed, `RecursiveAction` is suitable. For example, incrementing every element of an array exactly once. Leaves operate only on **disjoint** segments, so no atomic increment is needed per element.

Create `ForkJoinActionDemo.java`:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.TimeUnit;

public final class ForkJoinActionDemo {
    private static final class IncrementTask extends RecursiveAction {
        private static final int THRESHOLD = 512;
        private final int[] numbers;
        private final int start;
        private final int end;

        IncrementTask(int[] numbers, int start, int end) {
            this.numbers = numbers;
            this.start = start;
            this.end = end;
        }

        @Override
        protected void compute() {
            if (end - start <= THRESHOLD) {
                for (int i = start; i < end; i++) {
                    numbers[i]++;
                }
                return;
            }

            int mid = start + (end - start) / 2;
            IncrementTask left =
                    new IncrementTask(numbers, start, mid);
            IncrementTask right =
                    new IncrementTask(numbers, mid, end);

            left.fork();
            right.compute();
            left.join();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        int[] values = new int[10_000];
        ForkJoinPool pool = new ForkJoinPool(3);
        try {
            pool.invoke(new IncrementTask(values, 0, values.length));
            int sum = 0;
            boolean allOnes = true;
            for (int value : values) {
                sum += value;
                allOnes &= value == 1;
            }

            System.out.println("Sum: " + sum);
            System.out.println("All ones: " + allOnes);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile/run:

~~~bash
javac ForkJoinActionDemo.java
java ForkJoinActionDemo
~~~

Stdout:

~~~text
Sum: 10000
All ones: true
~~~

**Analysis:** the two subtasks always manage non-overlapping half-open ranges `[start, mid)` and `[mid, end)`. Each element is written by only one leaf, so there are no lost updates from two workers modifying the same index. After `pool.invoke`, the entire root computation is complete and `main` can inspect the array per the fork/join contract.

If you change the problem to "every task increments **the same variable** `globalCount++`", it will create a data race / lost update; you must use reduction, `LongAdder` per metrics contract, or an appropriate synchronization primitive. `ForkJoinPool` itself **does not make shared mutable state thread-safe**.

## 8. How does work stealing balance uneven branches?

A real-world task tree is rarely perfectly balanced. For example:

~~~text
                        Root
                      /      \
              small branch   large branch
                 |            /      \
               10 ms        60 ms    70 ms
~~~

These numbers are illustrative, not runtime measurements. If one worker holds the entire large branch while another worker has finished the small branch, CPU capacity could sit idle. With further decomposition and work stealing, the idle worker can pick up unexecuted tasks from the busy worker.

Key points to understand:

1. Stealing happens on **transferable tasks**, not by "splitting in half" a currently executing instruction.
2. Good balancing depends on whether the large task can still be subdivided.
3. If tasks are too small, fork/steal overhead can exceed the leaf work.
4. If tasks need to acquire a shared lock, adding more workers will not yield proportional throughput.
5. If a leaf requires slow I/O, work stealing does not automatically guarantee a replacement worker during unmanaged blocking.

An important habit is to **avoid expecting every worker to stay 100% busy**. In trees with dependencies, combine phases or small workloads can naturally leave workers temporarily idle.

## 9. Grain size and threshold: why not fork per element?

There is overhead for each task creation/scheduling/metadata, join, worker coordination, and cache effects. If you split down to every single element:

~~~text
N elements -> nearly 2N task tree nodes
each leaf performs only a single addition
overhead may exceed the actual operation
~~~

This is an illustrative model. In practice, task count depends on tree structure, how the code forks, and direct branch execution.

A **threshold** decides when to process sequentially. How to choose it:

- Large enough that a leaf performs meaningful useful work.
- Small enough to generate more leaves than workers, enabling load balancing.
- Matched to per-element complexity: computing a complex checksum can use smaller chunks than simple integer addition.
- Matched to data/cache layout, array size, and task object allocation cost.
- Based on measurement, not "gut-feeling optimization."

You can benchmark `THRESHOLD` at 256, 1024, 4096, and 16384 with **the same data, JDK, and load**, inspecting median/p95, throughput, and allocation. Do not draw conclusions from a single `System.nanoTime` run due to JIT warmup, GC, CPU scheduling, and noise.

### 9.1 Computing work and span

In parallel algorithm modeling:

- **Work T1**: amount of work if executed sequentially.
- **Span T∞**: length of the longest dependency chain (critical path), even with infinite workers.
- With `P` workers, actual runtime also depends on scheduling overhead, contention, and memory bandwidth; you cannot simply compute `T1/P`.

A balanced binary split tree reduces the span of many reduction problems, but if the combine step is a heavy sequential bottleneck or data hits a memory bandwidth limit, adding workers will not produce corresponding speedup.

Do not equate core count with speed: higher parallelism does not eliminate memory bandwidth costs or non-splittable sequential work.

## 10. Parallelism, worker count, and commonPool

### 10.1 Parallelism is not the number of always-executing threads

~~~java
ForkJoinPool pool = new ForkJoinPool(4);
System.out.println(pool.getParallelism()); // 4
~~~

This is an illustrative snippet and should be placed in a context that properly manages `shutdown()`. `getParallelism()` returns the configured **target parallelism**, not proof that four workers are always actively executing code. `getPoolSize()` may differ from target parallelism, for example when the pool compensates for blocking.

Metrics such as `getActiveThreadCount()`, `getRunningThreadCount()`, and `getQueuedTaskCount()` are snapshots/estimates at the moment of observation, not to be used to assert business invariants.

### 10.2 ForkJoinPool.commonPool()

~~~java
ForkJoinPool shared = ForkJoinPool.commonPool();
~~~

`commonPool()` is a JVM-wide shared pool. Many components may use it, including `ForkJoinTask` instances not submitted to a custom pool; APIs such as `CompletableFuture.supplyAsync` without an explicit executor typically use the common pool depending on API/JDK conditions.

Notes:

- **Do not shut down `commonPool`** when a module finishes; it is a shared resource, and normal shutdown has no effect on stopping the common pool per the API contract.
- One module submitting heavy CPU or blocking tasks to the common pool can impact the latency of other modules.
- Settings like `java.util.concurrent.ForkJoinPool.common.parallelism` can affect the pool; avoid relying on implicit defaults when an application needs resource isolation.
- Results can differ on machines with fewer cores, CPU-limited containers, or different JVM options.
- Create a **custom pool** when you need isolation, explicit target parallelism, or a dedicated lifecycle.

In JDK 17, `ForkJoinPool.commonPool()` is generally suitable for independent CPU-bound divide-and-conquer tasks, though sharing can become unpredictable in large systems where multiple libraries submit to it.

## 11. Java 17+ Example: submitting tasks from a thread outside the pool

`ForkJoinPool` does not only run `RecursiveTask`. It also implements `ExecutorService` and can accept standard `Callable` tasks. Create `ForkJoinSubmitDemo.java`:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class ForkJoinSubmitDemo {
    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            Future<Integer> answer = pool.submit(() -> 6 * 7);
            System.out.println("Answer: " + answer.get());
            System.out.println("Target parallelism: "
                    + pool.getParallelism());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac ForkJoinSubmitDemo.java
java ForkJoinSubmitDemo
~~~

Stdout:

~~~text
Answer: 42
Target parallelism: 2
~~~

**Analysis:** `main` is not a `ForkJoinWorkerThread`, yet it can still submit tasks to the pool. `Future.get()` waits for the result and throws checked exceptions per the `Future` API, unlike `ForkJoinTask.join()`. This example is not meant to prove work stealing occurred; a single small `Callable` can be handled entirely by one worker with no tasks to steal.

When the goal is simply executing many independent `Runnable`/`Callable` tasks, `ThreadPoolExecutor` or `Executors.newFixedThreadPool` can also be suitable. Work stealing is particularly valuable when the workload generates **dynamic fork/join branches** or small tasks distributable across workers.

## 12. fork(), join(), invoke(), get(), and invokeAll()

These APIs sound similar but have distinct differences:

| API | Role |
| --- | --- |
| `ForkJoinTask.fork()` | Schedules the task for asynchronous execution in the current task's pool or the common pool per contract. Returns the task itself. |
| `ForkJoinTask.join()` | Returns the result upon completion; on abnormal completion, propagates `RuntimeException`/`Error` via task mechanics rather than checked `ExecutionException`. |
| `ForkJoinTask.invoke()` | Executes this task and awaits its result; a convenience for root/subtasks per contract. |
| `ForkJoinPool.invoke(task)` | Common entry point from `main`/non-workers: submits the root `ForkJoinTask` to the pool and waits for the result. |
| `ForkJoinTask.invokeAll(left, right)` | Forks/joins a group of subtasks and guarantees completion or reports abnormal completion per contract. |
| `ForkJoinTask.get()` | Conforms to the `Future` API: throws checked `InterruptedException`/`ExecutionException`. |
| `Thread.join()` | Waits for **the lifecycle of a Java Thread**, does not return a `ForkJoinTask` value. |

`ForkJoinTask.join()` is not the same as `Thread.join()`: one retrieves a task's result, while the other waits for a thread to terminate. Notably, `ForkJoinTask.join()` does not throw checked `InterruptedException` on its normal waiting path; therefore, if an application needs cancellation/deadline policies, you must choose an API and lifecycle design more explicit than calling `join` indefinitely.

`get()` does not guarantee a task has started if you only instantiated a `RecursiveTask` without submitting/forking/invoking it. Creating a task object is not executing it.

### 12.1 Tasks must not be arbitrarily forked multiple times

A `ForkJoinTask` typically has a lifecycle of "new -> scheduled/executing -> completed". Do not submit/fork **the same running instance** multiple times. If you want to run the same logic again, create a new task instance with the appropriate input.

Reinitializing a completed task is a low-level capability with specific rules; most applications do not need it and should not use it to arbitrarily "reset" a task.

## 13. Java Memory Model and correctness in fork/join

`ForkJoinPool` manages scheduling, but **does not make shared data immutable or thread-safe**. Distinguish between:

- **Task ownership:** each task owns a specific input/output range.
- **Publication:** the caller prepares input before submit/invoke; must adhere to executor/task memory-consistency effects.
- **Completion:** the caller only reads output after the subtask completes via `join()`, `invoke()`, or the corresponding completion contract.
- **Shared state:** if multiple tasks write to the same collection/counter without coordination, races can occur regardless of `fork()/join()`.

In `ForkJoinSumDemo`, all leaves **only read** the array so there is no write contention; partial sums are returned as immutable `Long` values and joined/reduced. In `ForkJoinActionDemo`, leaves write to disjoint regions and `main` reads after completion. These are designs that are easy to prove correct.

### 13.1 Avoid a shared mutable accumulator

Buggy pattern:

~~~java
static long total;

void computeLeaf(long value) {
    total += value; // Possible lost update when leaves run concurrently.
}
~~~

This is an illustrative buggy snippet. `total += value` is a multi-step read-modify-write; multiple workers can overwrite each other's updates.

Correct approaches:

1. Each `RecursiveTask<Long>` returns a partial sum, and the parent calls `join()` and sums them.
2. If it is truly an independent metric and only an approximate sum is needed during updates, choose an appropriate atomic/adder primitive; do not use it in place of multi-step invariants.
3. If multiple fields are transactionally related, use a synchronization protocol or immutable aggregate with a shared commit boundary.

**Reduction via return values is usually the most natural approach** for Fork/Join because it avoids cache contention on a global variable.

## 14. Blocking I/O: a weakness that requires dedicated design

Fork/Join is primarily optimized for short computational tasks that can be forked/joined. When a worker executes:

~~~java
String content = remoteService.fetch(); // May wait on the network for a long time.
~~~

This is an illustrative snippet; the remote API is hypothetical. If a worker blocks on I/O or waits on a lock/condition **not managed by the pool**, the pool may run short of active workers to serve remaining tasks. The Java 17 Javadoc explicitly states that the pool can adjust when workers wait on `join` or managed synchronization, but **does not guarantee thread compensation for blocked I/O or unmanaged synchronization**.

### 14.1 Design guidelines

- Prefer reserving `ForkJoinPool` for **CPU-bound divide-and-conquer**; for many blocking I/O requests, consider an executor suited to connection counts, quotas, and timeouts.
- Do not hold a monitor while blocking on remote I/O or waiting on `Future.get()` without a clear deadline.
- If you must block on a primitive unknown to the pool, `ForkJoinPool.managedBlock(ManagedBlocker)` gives the pool **an opportunity** to compensate with a worker to maintain parallelism; it does not promise unlimited thread creation.
- Choose clear timeouts/cancellations and resource ownership; `managedBlock` does not provide timeouts or resolve deadlocks on its own.
- If tasks share a pool with other subsystems, prolonged blocking can affect unrelated workloads.

### 14.2 Illustrative ManagedBlocker

The following Java method snippet illustrates waiting on a `CountDownLatch`:

~~~java
static void awaitManaged(CountDownLatch latch)
        throws InterruptedException {
    ForkJoinPool.managedBlock(new ForkJoinPool.ManagedBlocker() {
        @Override
        public boolean isReleasable() {
            return latch.getCount() == 0;
        }

        @Override
        public boolean block() throws InterruptedException {
            latch.await();
            return true;
        }
    });
}
~~~

This is a **method snippet** requiring imports `java.util.concurrent.CountDownLatch` and `java.util.concurrent.ForkJoinPool`; there is no `main`. `isReleasable()` indicates whether execution can proceed without blocking; `block()` performs the actual wait and returns `true` when no further blocking is needed.

If called from a `ForkJoinWorkerThread`, the pool can manage/compensate for the blocking condition subject to its algorithm and resource limits. However:

- If the latch never counts down, the task can still wait indefinitely.
- If the worker still holds another lock that the producer needs in order to call `countDown`, a deadlock can occur.
- If the blocking is inside a remote call that does not support cancellation, wrapping it in `managedBlock` will not fix a broken protocol.
- If a timeout is needed, pass a deadline into the blocker/wait API and handle the result properly.
- Some logic inside `ManagedBlocker` may be invoked repeatedly; you must uphold the `isReleasable`/`block` contract.

## 15. Deadlock and starvation in fork/join trees

An erroneous pattern is sharing a small pool and **blocking on work that the pool itself lacks available workers to execute**. `ForkJoinTask.join()` has work-helping mechanisms to avoid common cases, but it does not guarantee resolving arbitrary dependency graphs, especially those waiting on I/O or out-of-band synchronization.

A dangerous design example:

~~~text
Worker A holds monitor L
  -> waits for a signal / Future from task B
Task B is waiting to acquire monitor L to complete
=> dependency cycle: A does not release L, B cannot run
~~~

This is not a "work stealing failed" bug, but a **dependency deadlock** caused by holding a monitor while waiting for another task that needs that monitor.

### 15.1 Common anti-patterns

| Anti-pattern | Why it is risky | Alternative |
| --- | --- | --- |
| Forking a task and joining while holding a monitor the subtask needs. | Lock wait cycle. | Release the lock / finish the critical section before joining. |
| Tasks in the pool waiting indefinitely on I/O. | Exhausts active workers; starvation risk. | Deadlines, an appropriate I/O executor, or `managedBlock` per contract. |
| Task A waits on B, B waits on A via join/Future. | Dependency cycle that cannot make progress. | Design an acyclic DAG; review the dependency graph. |
| Forking millions of tiny leaves. | Sharp rise in overhead/queue/memory. | Sequential processing threshold and decomposition limit. |
| Every leaf locking a global mutex for long durations. | Parallelism is serialized, high contention. | Partition state, reduce results instead of a shared accumulator. |
| Third-party code holding common pool workers for long periods. | Impacts other modules. | Custom pool/lifecycle isolation, avoid unmanaged blocking. |
| Re-forking a ForkJoinTask while it is running. | Invalid task lifecycle, unsupported behavior. | Create a new task instance for each computation. |

Do not jump to "changing `ForkJoinPool(4)` to 100" to fix starvation. Adding workers can increase memory usage, context switching, and contention, while the deadlock still remains.

## 16. asyncMode, local LIFO/FIFO, and event-style tasks

Some `ForkJoinPool` constructors accept an `asyncMode` parameter. Per the Java 17 documentation:

- By default (`asyncMode` disabled), the pool generally optimizes local execution with a policy supporting **fork/join tasks that are joined**.
- With `asyncMode=true`, the pool uses **local FIFO scheduling** for event-style tasks **that are never joined**; this is an appropriate option in certain asynchronous task processing models.
- It **does not guarantee global FIFO** across all external submissions, workers, and steals.
- It does not change the semantics of `join()` or make dependent tasks independent.

API-level constructor example:

~~~java
ForkJoinPool pool = new ForkJoinPool(
        4,
        ForkJoinPool.defaultForkJoinWorkerThreadFactory,
        null,
        true
);
~~~

This is a code snippet (place inside a method/class and import `ForkJoinPool`). `true` selects async scheduling mode for local tasks per contract; `null` means no custom `UncaughtExceptionHandler` is used. Do not choose `asyncMode=true` merely because you believe "FIFO must be fairer": measure actual latency/throughput and understand your task pattern.

## 17. CountedCompleter: when join is no longer a simple tree

`CountedCompleter<V>` is a specialized `ForkJoinTask` that lets subtasks coordinate via a **completion count** instead of the parent calling `join()` on each child in a fixed binary tree. It is useful for certain traversal, map/scan, propagation, and complex event-driven completion algorithms.

However, complexity increases:

- `setPendingCount`/`addToPendingCount` tracks how many children still need to coordinate.
- `tryComplete()`/`propagateCompletion()` advances completion when no pending tasks remain.
- `onCompletion(...)` and `onExceptionalCompletion(...)` have distinct roles per contract.
- If the pending count is wrong or the completion method is not called properly, the root may never complete.
- You must distinguish completion of the **main task** from side effects of children, and avoid reading shared state before all required children finish.

For an array sum, do not start with `CountedCompleter`: `RecursiveTask<Long>` is simpler and easier to audit. Only use `CountedCompleter` when **the algorithm genuinely needs a different completion graph shape** and the team thoroughly understands the protocol.

## 18. Observation: measuring work stealing without over-interpreting

`ForkJoinPool` provides monitoring APIs such as:

| Metric / method | Approximate meaning | What not to infer |
| --- | --- | --- |
| `getStealCount()` | Estimate of tasks taken by other workers for execution. | Not proof that every task was stolen that exact number of times. |
| `getQueuedTaskCount()` | Estimate of tasks remaining in worker queues. | Does not accurately include all running tasks or unclaimed submissions. |
| `getQueuedSubmissionCount()` | Estimate of pending tasks from external submissions. | Not the remaining task count of a business batch. |
| `getActiveThreadCount()` | Estimate of active workers. | Not equivalent to the number of actually busy cores. |
| `getRunningThreadCount()` | Estimate of workers not suspended by join/managed synchronization. | Does not guarantee the absence of unmanaged blocking I/O. |
| `getPoolSize()` | Number of workers started and not yet terminated. | Not always equal to `getParallelism()`. |
| `getParallelism()` | Configured target parallelism. | Not the exact number of tasks that ran in parallel. |
| `toString()` | Convenient pool state snapshot for debugging. | Not an exact history log, has no transaction semantics. |

For a small example, `getStealCount()` might be 0, 1, or another number depending on scheduling. **Do not assert specific stdout values for this metric.** Instead:

1. Assert that the business result is **correct and deterministic**.
2. Measure across multiple runs, representative data sizes, and parallelism levels.
3. Inspect throughput, CPU utilization, p95/p99, allocation, GC, and steal counts when the workload is large enough.
4. Observe contention/blocked tasks using thread dumps, JFR, and a profiler.
5. Check whether the bottleneck is memory bandwidth, threshold, false sharing, lock contention, or I/O.

### 18.1 Avoid benchmarks with a shared bottleneck

If every leaf calls `System.out.println` for each element, output I/O locking can dominate runtime, preventing the benchmark from reflecting work stealing. Similarly, many tasks adding to the same `AtomicLong` can cause cache contention that masks the benefit of parallel reduction.

Benchmarks should compare **the same algorithm**, inputs, JDK, VM options, warmup, and CPU environment. Use JMH for JVM microbenchmarks when needed instead of running once and drawing conclusions.

## 19. When to choose ForkJoinPool over other executors?

| Problem | Commonly considered choice | Reason |
| --- | --- | --- |
| CPU-bound divide-and-conquer, dynamic task trees, reduction | **ForkJoinPool + RecursiveTask** | Work stealing helps distribute load when tasks fork subtasks. |
| Array transformations over independent ranges, no return value | **ForkJoinPool + RecursiveAction** | Partitioning avoids a shared mutable accumulator. |
| Many independent callables of similar duration, no child forking | **Fixed thread pool** or ForkJoinPool after measurement | Work stealing does not necessarily provide an advantage. |
| Many blocking I/O tasks | Executor designed for specific blocking/resources, or Java 21+ virtual threads | ForkJoin workers are not guaranteed to compensate for unmanaged blocking. |
| Tasks with complex deadlines/cancellation, batch results | `ExecutorService` + `Future`/`CompletionService` | Clear lifecycle/result semantics per requirements. |
| Data stream processing with parallel stages | Parallel Stream when appropriate, or a custom pipeline | Often built on fork/join internals, but requires understanding ordering and the shared pool. |
| Composing multiple dependent async operations | `CompletableFuture` composition | Expresses dependencies/callbacks more clearly than a recursive join tree. |

Crucially: **ForkJoinPool is a scheduling strategy, not a transaction API or safe-publication mechanism for arbitrary data**. The choice must start from invariants, work splittability, scheduling overhead, and cancellation/shutdown requirements, and only then optimize throughput.

## 20. Common mistakes and fixes

**Mistake 1: Forking a task per element thinking "more tasks means faster."** No: task overhead, scheduling, and allocation can overwhelm the workload. Choose a leaf threshold and measure.

**Mistake 2: Creating one large Task with a single CPU-bound leaf and expecting stealing.** There are no subtasks available to steal; work does not split itself automatically.

**Mistake 3: Using a global `total += value` across all leaves.** Race/lost update; return partial results and combine after `join`.

**Mistake 4: Using `Thread.sleep()` to measure worker ordering.** The scheduler does not guarantee order. Verify the final result, and use latches for interleaving tests if needed.

**Mistake 5: Assuming `getStealCount()` must be positive if ForkJoinPool is "working."** For small work or branches handled by the original worker, 0 steals is completely valid.

**Mistake 6: Making long blocking I/O calls inside `compute()`.** Can starve active workers; use timeouts, another executor, or `managedBlock` appropriately.

**Mistake 7: Increasing parallelism to cure a deadlock caused by holding a lock then joining.** A dependency deadlock does not disappear just by adding more workers.

**Mistake 8: Shutting down `ForkJoinPool.commonPool()` when a module finishes.** The common pool is shared; you do not own it like a custom pool.

**Mistake 9: Using a custom pool without shutdown/await.** Can leak lifecycle and resources depending on the environment. The owner must manage the pool.

**Mistake 10: Using `RecursiveAction` to mutate the same index across multiple tasks without synchronization.** No atomic/invariant guarantees; partition or synchronize.

**Mistake 11: Using `ForkJoinTask.join()` like `Thread.join()`.** Different contracts, different exceptions and results.

**Mistake 12: Re-forking the same running ForkJoinTask.** Invalid lifecycle; create a new instance for a new computation.

**Mistake 13: Enabling `asyncMode` and claiming all tasks are globally FIFO.** It relates to local FIFO for certain asynchronous workloads, not global ordering.

**Mistake 14: Splitting overlapping ranges `[start, mid]` and `[mid, end]` for write operations.** Index `mid` may be processed twice; use half-open intervals consistently.

**Mistake 15: Measuring speed once without warmup.** JIT, GC, CPU, and I/O make single-run conclusions invalid; measure representative workloads and evaluate performance alongside correctness.

## 21. Process for designing a Fork/Join algorithm

1. **Confirm the problem is splittable:** can subproblems be computed independently or does the reduction have suitable properties?
2. **Write a reference sequential function:** have passing tests before parallelizing.
3. **Define the data domain:** use `[start, end)` to split without gaps or overlaps.
4. **Choose a base case:** leaves large enough to be worthwhile, avoiding infinite recursion.
5. **Design the reduction:** combine partial results after `join`, handling overflow/precision appropriately.
6. **Choose fork/compute/join order:** avoid over-forking and avoid joining while holding locks.
7. **Ensure tasks do not recklessly share mutable state:** copy/snapshot or partition ownership.
8. **Choose the pool owner:** common pool if isolation is unneeded, custom pool if dedicated parallelism/lifecycle is required.
9. **Handle failure/cancellation:** abnormal completion, interrupts/deadlines, and cleanup must have a policy.
10. **Measure CPU/overhead/threshold:** compare against the sequential baseline; do not assume parallel is always faster.
11. **Observe work stealing:** treat metrics as estimates, not execution-order assertions.
12. **Evaluate memory bandwidth and contention:** these may be the true limit rather than worker count.
13. **Test for regressions:** results must be correct for empty, very small, very large, and skewed-branch inputs.
14. **Review when upgrading JDK/changing infrastructure:** schedulers and CPU quotas can affect workload characteristics.

## 22. Self-check questions

**1.** What is the key advantage of ForkJoinPool over a fixed thread pool?  
**Answer:** Workers can spawn subtasks and work-steal pending tasks from other workers, which is useful for uneven divide-and-conquer workloads.

**2.** Does work stealing take half of a currently running instruction from another worker?  
**Answer:** No. It takes **pending runnable tasks**, not by preempting a running leaf.

**3.** Why does a worker typically take local tasks from one end of a deque while a thief takes from the opposite end?  
**Answer:** To support locality and reduce contention at the same end of the queue; this is the algorithmic intuition, not a guarantee of every JVM interleaving.

**4.** How do `RecursiveTask<V>` and `RecursiveAction` differ?  
**Answer:** `RecursiveTask` returns a value from `compute`; `RecursiveAction` has a `void` `compute`.

**5.** Why is the pattern `left.fork(); right.compute(); left.join();` generally sensible?  
**Answer:** One branch gets a chance to run in parallel while the current worker executes the other, reducing scheduling overhead compared to forking both.

**6.** Is forking per array element to compute a sum guaranteed to be faster than a `for` loop?  
**Answer:** No. Fork/join overhead can exceed addition cost; a leaf threshold and measurement are required.

**7.** Does `getParallelism() == 4` prove four workers are always running concurrently?  
**Answer:** No, that is the target parallelism, not a snapshot of currently working threads.

**8.** When is `getStealCount() == 0` completely valid?  
**Answer:** When the workload is small, tasks finish on their owning worker, or there is no opportunity to steal.

**9.** How should `ForkJoinPool.commonPool()` be used?  
**Answer:** Treat it as a shared resource; do not shut it down yourself, and avoid prolonged blocking that could affect other subsystems.

**10.** How does `ForkJoinTask.join()` differ from `Future.get()` regarding errors?  
**Answer:** `join` reports abnormal completion via `RuntimeException`/`Error` per contract, whereas `Future.get` uses checked `ExecutionException` and throws `InterruptedException`.

**11.** Why is reading the array after `pool.invoke` safe in `ForkJoinActionDemo`?  
**Answer:** Leaves modify disjoint regions, and the root computation has completed before `main` inspects the result.

**12.** If every leaf writes to `globalCounter++`, is there a race condition?  
**Answer:** Yes. `ForkJoinPool` does not automatically synchronize shared state; use reduction or an appropriate primitive.

**13.** What is the risk of long blocking I/O inside `compute()`?  
**Answer:** Workers become occupied and the pool does not guarantee thread compensation for unmanaged blocking; throughput and liveness can degrade.

**14.** Does `ForkJoinPool.managedBlock` make every wait safe indefinitely?  
**Answer:** No. It informs the pool of blocking so it can attempt compensation, but you still need timeouts, absence of deadlocks, and resource limits.

**15.** Does enabling `asyncMode=true` guarantee global FIFO for all tasks?  
**Answer:** No. It mainly changes local scheduling for non-joined asynchronous-style tasks; it does not create global ordering.

**16.** When should you use `CountedCompleter` instead of `RecursiveTask`?  
**Answer:** When the completion pattern does not fit a direct join tree and the benefit justifies the more complex pending-count protocol.

**17.** A task forks the left branch and never joins/awaits completion, yet `main` reads the left branch's result immediately—is that valid?  
**Answer:** There is no guarantee the task has finished or of proper visibility; you must use completion/join or a proper result-publication protocol.

**18.** Why can't we claim ForkJoin is always faster than sequential execution?  
**Answer:** Work may be too small, memory-bandwidth bound, suffer from contention or blocking, or task-splitting overhead may exceed parallel gains.

**Takeaway:** `ForkJoinPool` is specialized for **task trees capable of fork/join and work decomposition**, while work stealing lets idle workers pick up pending tasks to balance load. **Correctness** comes from non-overlapping range partitioning, post-join reduction, and data ownership; **performance** comes from grain size, parallelism level, minimal blocking, and real measurement. Do not confuse `ForkJoinPool` scheduling with transactions, fairness, or automatic thread safety of arbitrary shared objects.

## Official References

- [ForkJoinPool — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, common pool, parallelism, ManagedBlocker, monitoring.
- [ForkJoinTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): fork, join, invoke, and lifecycle.
- [RecursiveTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): recursive task with return value.
- [RecursiveAction — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): task without return value.
- [CountedCompleter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): completion count for advanced patterns.
