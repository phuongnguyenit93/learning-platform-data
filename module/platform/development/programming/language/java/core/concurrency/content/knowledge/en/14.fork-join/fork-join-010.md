# Task Dependencies and Circular Wait Risks in Fork/Join

## 1. Objectives

`ForkJoinPool` is an executor specialized for handling many tasks that can be decomposed into subtasks. The typical algorithm splits a large problem into independent branches, runs those branches when workers are available, and then combines the results using `join()`. The **work-stealing** mechanism helps workers find additional work from other workers.

An important limitation: **work-stealing cannot automatically detect or resolve logical wait cycles**. If task A can only complete when B completes, and B in turn needs A, then A→B→A is a dependency cycle. Adding more workers does not create a valid completion order. The `ForkJoinTask` Javadoc recommends that `join()` completion dependencies must be **acyclic** — that is, a **DAG (Directed Acyclic Graph)**.

This lesson helps you:
- Distinguish between `fork()`, `compute()`, `join()`, `ForkJoinPool.invoke()`, `ForkJoinTask.invokeAll()`, and `Future.get()`.
- Draw and read task dependency graphs, and detect self-joins and A→B→C→A wait cycles.
- Use the `fork one branch → compute the other branch → join` pattern to create a clear divide-and-conquer structure.
- Identify deadlocks caused by resource locks, permits, external I/O, or a completion signal that never arrives.
- Understand the purpose and limitations of `ForkJoinPool.ManagedBlocker` when a worker waits on non-Fork/Join operations.
- Choose between `RecursiveTask`, `RecursiveAction`, `CountedCompleter`, and staged DAG coordination.
- Practice three standalone Java 17+ programs: array sum, merging branches, and checking a graph for cycles before submission.
- Have a code review checklist, observe thread dumps, and answer practical scenarios.

**Scope:** General Java SE concurrency, without frameworks.

## 2. Fork, compute, and join are three distinct behaviors

`fork()` places a `ForkJoinTask` into the appropriate asynchronous execution stream; the task becomes a candidate for execution by workers. `compute()` is the direct logic of the subclass, while `join()` waits for the referenced task to complete and returns its result.

~~~java
@Override
protected Integer compute() {
    if (isSmall()) {
        return calculateDirectly();
    }

    PartTask left = new PartTask(leftInput());
    PartTask right = new PartTask(rightInput());

    left.fork();
    int rightValue = right.compute();
    int leftValue = left.join();
    return leftValue + rightValue;
}
~~~

This is **Java-like pseudocode** inside a `RecursiveTask<Integer>` subclass, where `isSmall`, `calculateDirectly`, and the constructors are application-defined. It is not a standalone program.

Dependency flow:

~~~text
          Parent
          /    \
        Left   Right
         |      |
     fork()   compute() on current worker
         |      |
      result  result
          \    /
         left.join()
              |
        combine results
~~~

Reasons this pattern is commonly used:
1. The parent forks only one branch, allowing another worker to pick up that branch when capacity is available.
2. The current worker executes the remaining branch itself, rather than forking both and just waiting.
3. Results are combined only once both branches' results are ready.
4. A child does not wait back on its parent, so the tree structure does not create a wait cycle.
5. A `THRESHOLD` can be set to avoid creating tasks for work that is too small.

Do not assume `fork()` means a task immediately starts on another thread. The pool may have no idle workers; the same worker can also participate in executing tasks through the Fork/Join mechanism. Correctness must not depend on worker names or a specific execution schedule.

## 3. A dependency is a must-complete-before relationship

In this lesson, the convention **A → B** means **A requires the result or completion of B before A can complete**.

### Safe case: DAG

~~~text
              Root
             /    \
            A      B
           / \    / \
          C   D  E   F

Root → A, B
A → C, D
B → E, F

C, D, E, F can complete on their own.
A and B combine only after their children.
Root combines only after A and B.
There is no path back to an ancestor.
~~~

The graph has a valid topological order: leaves first, intermediate nodes next, root last. Independent leaves can run in parallel; the runtime does not guarantee a single execution order.

### Error case: two-node cycle

~~~text
Task A: waits on B.join()
Task B: waits on A.join()

Graph:
A ─────► B
▲        │
└────────┘

A finishes only after B; B finishes only after A.
Neither node can complete on its own.
~~~

Increasing the number of workers from 2 to 16 cannot break this constraint. This is a **dependency cycle**, not simply "not running fast enough".

### Longer cycles or self-join

~~~text
A → B → C → A   (indirect cycle)
D → D           (self-dependency)
E → F → G       (no cycle in this part)
~~~

If a node sits outside a cycle but depends on a node inside the cycle, it can also wait forever. For example, `Root → A → B → C → B`: Root is not in the cycle, but it gets stuck because it cannot receive A's result.

### A faulty snippet to recognize, not execute

~~~java
@Override
protected Integer compute() {
    return this.join(); // WRONG: task waits for itself
}
~~~

This is a fragment inside a `RecursiveTask<Integer>` subclass, intentionally wrong. Running a `main` method that uses this snippet can hang indefinitely. This lesson does not provide an executable demo of a faulty join cycle to avoid hanging learners' environments or CI.

## 4. Why can't work-stealing resolve wait cycles?

Each worker can take tasks from its internal queue and steal queued tasks from other workers. When a Fork/Join task calls `join()`, the runtime has mechanisms to help execute tasks that can advance the computation. However, **the scheduling mechanism and the existence of a valid completion path are two different issues**.

- If a child has not been processed yet but has an independent execution path, another worker or the joining worker itself can help execute it.
- If a child is already running but waits on its parent, **it has no path to return a result** under the current logic.
- If a child needs a lock that the parent holds until `join()` finishes, the scheduler will not automatically release that lock.
- If a child is waiting on a `CountDownLatch` and no task has a remaining path to call `countDown`, adding workers will not produce the signal.
- If a child is stuck on remote I/O with no timeout, work-stealing can run other work, but it cannot guarantee the child will exit.

**Conclusion:** `join()` is useful for **acyclic** dependencies, not as a deadlock-detection primitive.

## 5. Runnable example 1: summing an array with an acyclic tree

Save as **ForkJoinSumDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinSumDemo {
    static class SumTask extends RecursiveTask<Long> {
        private static final int THRESHOLD = 2;

        private final long[] numbers;
        private final int from;
        private final int to;

        SumTask(long[] numbers, int from, int to) {
            this.numbers = numbers;
            this.from = from;
            this.to = to;
        }

        @Override
        protected Long compute() {
            if (to - from <= THRESHOLD) {
                long sum = 0;
                for (int i = from; i < to; i++) {
                    sum += numbers[i];
                }
                return sum;
            }

            int middle = from + (to - from) / 2;
            SumTask left = new SumTask(numbers, from, middle);
            SumTask right = new SumTask(numbers, middle, to);

            left.fork();
            long rightSum = right.compute();
            long leftSum = left.join();
            return leftSum + rightSum;
        }
    }

    public static void main(String[] args) {
        long[] numbers = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(2);

        try {
            long answer = pool.invoke(
                    new SumTask(numbers, 0, numbers.length));
            System.out.println("sum=" + answer);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run:

~~~bash
javac ForkJoinSumDemo.java
java ForkJoinSumDemo
~~~

Stdout:

~~~text
sum=36
~~~

Why this works:
- The root node handles `[0,8)`; it splits into `[0,4)` and `[4,8)`.
- The leaves compute partial sums over **non-overlapping** ranges.
- Each parent combines two values only after the required subtasks have completed.
- No child waits on an ancestor; the graph is a valid tree.
- The input array is only read and is not concurrently modified by any thread in this example.
- Even though workers may pick up tasks in different schedules, addition over this data yields 36.

A threshold of 2 is only for illustration. For large arrays or cheap operations, a threshold that is too small makes task creation, scheduling, and work-stealing overhead outweigh the benefits. Benchmark to choose a threshold; do not treat 2 as an optimal formula.

## 6. Runnable example 2: combining independent data as a DAG

The `BuildReport` task needs two results: `ReadPart(3)` and `ReadPart(4)`. Both are independent; their results are combined into a string after completion.

~~~text
            BuildReport
            /         \
        ReadPart 3   ReadPart 4
            \         /
           combine(9,16)
               |
          "total=25"
~~~

Save as **ForkJoinDagDemo.java**:

~~~java
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveTask;

public class ForkJoinDagDemo {
    static final class ReadPart extends RecursiveTask<Integer> {
        private final int input;

        ReadPart(int input) {
            this.input = input;
        }

        @Override
        protected Integer compute() {
            return input * input;
        }
    }

    static final class BuildReport extends RecursiveTask<String> {
        @Override
        protected String compute() {
            ReadPart left = new ReadPart(3);
            ReadPart right = new ReadPart(4);

            left.fork();
            int rightValue = right.compute();
            int leftValue = left.join();

            return "left=" + leftValue
                    + ";right=" + rightValue
                    + ";total=" + (leftValue + rightValue);
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            System.out.println(pool.invoke(new BuildReport()));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac ForkJoinDagDemo.java
java ForkJoinDagDemo
~~~

Stdout:

~~~text
left=9;right=16;total=25
~~~

`ReadPart` does not need its parent before returning a result. The parent waits on one child via `join()` and computes the other child itself, so the directed wait relationship forms no cycle. Regardless of whether `left` or `right` finishes first, the values are combined using deterministic variables and stdout is stable.

**Extending to a true DAG:** if both A and B depend on C, that is a diamond graph. C does not necessarily need to be computed twice. Use a **single** representation of C's computation result, manage ownership/scheduling clearly, and have A and B simply consume the valid result. Do not arbitrarily fork the same `ForkJoinTask` instance multiple times, especially while the task is running.

## 7. Dependencies through shared resources: hidden wait cycles

Not every wait edge is written explicitly as `join()`.

Example:

~~~text
Parent holds monitor L
   |
   +-- forks Child
   |
   +-- Child needs synchronized(L) before completing
   |
   +-- Parent calls Child.join() while still holding L

Parent releases L only after Child.join().
Child completes only after acquiring L.
=> Parent waits on Child, Child waits on a resource held by Parent.
~~~

Anti-pattern:

~~~java
synchronized (sharedLock) {
    child.fork();
    child.join();
}
~~~

This is a **fault-illustrating fragment** inside a method where `sharedLock` and `child` are assumed to be defined. It is dangerous **if the child actually needs that same monitor to complete**. If the child does not need L, the snippet above does not automatically prove a deadlock — you must examine the child's dependencies.

A Java intrinsic monitor is reentrant **for the same thread**, not for another thread trying to enter a monitor held by the parent thread. Fork/Join may have mechanisms to help execute tasks, but you must not rely on them to mask an incorrect resource-ownership relationship.

### Semaphores can also create cycles

~~~text
A holds the last permit of Semaphore S
A forks B and then joins B
B tries to acquire S before completing
A releases S only after joining B
B cannot acquire the permit, A cannot get the result
~~~

`finally` will release the permit if the code exits the `try` block, but if a wait cycle prevents exiting, `finally` **never executes**. Therefore, you must design lock acquire/release ordering and graph edges properly, not just add cleanup.

### How to fix

1. Take a snapshot of shared state under the lock if needed.
2. **Release the lock** before forking/joining subtasks that might need that lock.
3. Compute on immutable inputs if possible.
4. Combine results after the joins.
5. When you need to commit to shared state, re-acquire the lock and **check the version/invariant**, because the state may have changed while the lock was released.

Conceptual snippet:

~~~java
Input snapshot;
synchronized (sharedLock) {
    snapshot = copyState();
}

Result answer = pool.invoke(new ComputeTask(snapshot));

synchronized (sharedLock) {
    commitOnlyIfStillValid(answer);
}
~~~

This is **integration pseudocode**; `Input`, `Result`, `copyState`, `ComputeTask`, and `commitOnlyIfStillValid` are components the application must define. Do not treat releasing the lock between steps as an atomic transaction; the commit phase must verify that the input data has not become stale.

## 8. How do deadlock, starvation, and slow tasks differ?

| Phenomenon | Example | What needs fixing |
|---|---|---|
| **Dependency cycle** | A joins B, B joins A | Remove cyclic edges, restructure the graph |
| **Resource wait cycle** | Parent holds lock, child needs lock while parent joins | Release/reorder resource ownership |
| **Thread starvation** | Worker blocks waiting for a child task that has no worker to run | Review dependencies, executor capacity, blocking strategy |
| **Missing signal** | Child waits on `CountDownLatch` with no one calling `countDown` | Fix the signal producer and `finally` blocks |
| **Slow I/O** | Leaf waits on a remote call with no timeout | Set I/O timeouts/cancellation per the API |
| **High overhead** | Millions of tiny subtasks | Thresholding and batching |
| **Valid DAG with few workers** | Independent leaves but only 1 worker | May be slow, not automatically a deadlock |

A valid DAG only states that there are no **dependency cycles**; it does not guarantee every leaf will complete: a leaf can fail, wait indefinitely on external I/O, or hit resource exhaustion. Therefore, liveness design must cover **both the graph and resources**.

## 9. Do not block arbitrarily inside compute()

`ForkJoinPool` is optimized for divide-and-conquer computation, but a `compute()` method might inadvertently call:
- `Future.get()` on a future created by another executor;
- `CountDownLatch.await()` whose signaler has not been scheduled;
- network I/O without a timeout;
- a very long `Thread.sleep()`;
- acquiring a lock/permit whose owner is waiting on the current task.

If a worker is blocked in an operation **that is not a join managed by ForkJoinPool**, the pool will not necessarily compensate with enough workers to maintain progress. The JDK provides `ForkJoinPool.ManagedBlocker` to signal certain blocking situations and allow the pool to **potentially** maintain parallelism with spare threads.

### ManagedBlocker is not a deadlock solver

`ForkJoinPool.managedBlock(blocker)` invokes the blocker's `isReleasable()` and `block()` methods according to its contract. When run from a `ForkJoinPool`, the runtime may add/activate another worker if appropriate within limits and resource availability.

It **does not**:
- break an A→B→A relationship;
- release a lock held by a parent;
- call `countDown` on a forgotten latch;
- make I/O interruptible if the underlying API does not support it;
- guarantee adding workers under every policy or when system resources are exhausted;
- automatically make a shared mutable object thread-safe.

If there is a cycle, **fix the graph**. If there is unmanaged blocking and the graph is acyclic, `ManagedBlocker` can be a useful tool, provided you understand `isReleasable`, `block`, cancellation responsibilities, and workload testing.

### ForkJoinTask.join and Future.get are not the same

`ForkJoinTask.join()` normally returns the result when completed normally, or throws an unchecked exception/`Error` when the task completes abnormally. `ForkJoinTask.get()` follows the `Future` contract with checked exceptions such as `InterruptedException`, `ExecutionException`, and `TimeoutException` in the timed overload.

- `join()` **has no timeout parameter**.
- `join()` **does not declare `InterruptedException`**.
- `get(timeout, unit)` only limits **how long the caller waits**; it does not break a cycle.
- `Thread.join()` is the API for waiting on a **Thread** to terminate, distinct from `ForkJoinTask.join()`.
- `CompletableFuture.join()` has its own exception semantics; do not conflate them.

## 10. Runnable example 3: checking for dependency cycles before creating tasks

Instead of running a join example that could hang, we check the graph using **three-color DFS**:
- 0: unvisited.
- 1: currently on the recursion stack (VISITING).
- 2: traversal completed (DONE).

If from a node we follow an edge to a node that is currently VISITING, there is a **back-edge**, meaning a cycle.

Save the file as **TaskDependencyCycleDemo.java**:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class TaskDependencyCycleDemo {
    static boolean hasCycle(Map<String, List<String>> graph) {
        Map<String, Integer> state = new HashMap<>();
        for (String node : graph.keySet()) {
            if (visit(node, graph, state)) {
                return true;
            }
        }
        return false;
    }

    private static boolean visit(
            String node,
            Map<String, List<String>> graph,
            Map<String, Integer> state) {

        int mark = state.getOrDefault(node, 0);
        if (mark == 1) return true;
        if (mark == 2) return false;

        state.put(node, 1);
        for (String dependency : graph.get(node)) {
            if (!graph.containsKey(dependency)) {
                throw new IllegalArgumentException(
                        "Unknown dependency: " + dependency);
            }
            if (visit(dependency, graph, state)) {
                return true;
            }
        }
        state.put(node, 2);
        return false;
    }

    public static void main(String[] args) {
        Map<String, List<String>> valid = Map.of(
                "root", List.of("left", "right"),
                "left", List.of("leaf"),
                "right", List.of("leaf"),
                "leaf", List.of()
        );

        Map<String, List<String>> invalid = Map.of(
                "A", List.of("B"),
                "B", List.of("C"),
                "C", List.of("A")
        );

        System.out.println("validHasCycle=" + hasCycle(valid));
        System.out.println("invalidHasCycle=" + hasCycle(invalid));
    }
}
~~~

Commands:

~~~bash
javac TaskDependencyCycleDemo.java
java TaskDependencyCycleDemo
~~~

Stdout:

~~~text
validHasCycle=false
invalidHasCycle=true
~~~

In the first graph, `leaf` has no dependencies, and the other nodes only have edges pointing down toward `leaf`, so there is no cycle. The second graph has A→B→C→A, so DFS returns to A while it is VISITING and returns `true`.

**Important limitations:**
- The graph here is **read-only** and not concurrently modified; therefore a plain `HashMap` is sufficient.
- Graphs can change dynamically in real applications; adding edges and checking acyclicity must be synchronized to avoid races.
- Recursive DFS can hit `StackOverflowError` on extremely deep graphs; in that case use iterative DFS or Kahn's algorithm.
- Detecting no cycles is **not sufficient** to guarantee all nodes complete; you must still check exceptions, missing tasks, blocking, and lifecycle.
- This program does not deadlock because it **only inspects the graph** and does not execute cyclic-wait tasks.

## 11. DAGs with shared prerequisites: be careful with completion ownership

A DAG is not necessarily a tree. Consider:

~~~text
       Root
       /  \
      A    B
       \  /
        C
~~~

Both A and B depend on C. If C is CPU-intensive, creating **two instances** to compute the same C can be wasteful. If C has side effects, executing it twice can be dangerous.

Principles:
1. Decide **who owns** C's computation and when C is scheduled.
2. Both dependents must use the result only **after C completes**.
3. Do not re-fork the same running `ForkJoinTask` instance as if a task were an arbitrarily callable function.
4. If C fails, define whether A/B fail or fall back, avoiding infinite waits.
5. If dependencies are created dynamically, ensure you do not add edge B→A concurrently with A→B and introduce a cycle.

For graphs with many shared prerequisites, you can organize **stages in topological order**, use `CompletableFuture` to express dependencies, or apply `CountedCompleter` when completion callbacks fit well. You do not need to force every graph into a `RecursiveTask` tree.

## 12. Topological order and readiness

Using the convention that A→B means A depends on B:

~~~text
Root → A
Root → B
A → C
B → C

Valid order: C, A, B, Root
or:          C, B, A, Root

After C, A and B are independent and can run in parallel.
Root runs/combines only when A and B complete.
~~~

A DAG scheduler can:
- Track the dependency count of each node.
- Enqueue only nodes whose prerequisites are satisfied.
- When a node finishes, decrement the unresolved dependency count on its dependents.
- Enqueue dependents that become ready.
- Report a clear error if no nodes are making progress while unresolved nodes remain due to a cycle or missing prerequisite.
- Define fail-fast or partial-result behavior when a prerequisite fails.

The key idea is **not occupying a worker just to wait on a task that is not ready yet** if readiness can be managed before scheduling. This reduces thread starvation in complex graphs.

## 13. Exceptions, timeouts, and cancellation

`ForkJoinTask.join()` can throw an unchecked exception when a task completes abnormally. `ForkJoinTask.isDone()` can be `true` because the task completed normally, exceptionally, or was cancelled — it does not necessarily mean the computation returned a successful result.

With `ForkJoinTask.get(timeout, unit)`, the caller can bound the wait phase, but a timeout:
- does not fix a cycle;
- does not automatically cancel the task just because `get` timed out;
- does not guarantee a worker performing I/O has stopped;
- does not roll back prior side effects.

An easily misunderstood detail from the Java 17 `ForkJoinTask.cancel(boolean)` Javadoc: **the `mayInterruptIfRunning` parameter has no effect in the default implementation**, because `ForkJoinTask` does not use interrupts to control cancellation the way some `FutureTask` implementations do. Therefore, `task.cancel(true)` is not a guarantee that a blocked worker will be immediately interrupted.

If tasks need cooperative cancellation, you must design appropriate signals/checkpoints and cleanup. `shutdownNow()` is also not a safe rescue for a broken dependency cycle. Do not run an actual cyclic graph to "see if the JVM resolves it on its own".

## 14. Observing and debugging stuck tasks

Useful metrics:

| API/tool | Meaning | Limitations |
|---|---|---|
| `pool.getParallelism()` | Target parallelism | Not the number of currently running tasks |
| `pool.getPoolSize()` | Current number of workers | Can change over time |
| `pool.getActiveThreadCount()` | Estimate of active workers | Not a transactional snapshot |
| `pool.getRunningThreadCount()` | Estimate of running workers | May not reflect all blocking |
| `pool.getQueuedTaskCount()` | Estimate of tasks in worker queues | Does not describe the full graph |
| `pool.getQueuedSubmissionCount()` | Estimate of external submissions | Can change continuously |
| `pool.getStealCount()` | Work-stealing statistics | Does not prove progress/correctness |
| Thread dump / JFR | Call stacks and JVM state | Point-in-time capture |
| Logging task IDs | Which task waits on which and holds which resource | Requires deliberate instrumentation |

When thread dumps show many workers stuck in `join` or a blocking call, build a **wait-for graph**:
1. Which task is waiting on which task?
2. Was the awaited task ever forked/submitted?
3. Is that task running, failed, cancelled, or still sitting in a queue?
4. Is any node waiting on an ancestor or on itself?
5. Is a parent holding a lock/permit that a child needs?
6. Is there a latch/barrier with no remaining signaler?
7. If the graph is acyclic, where is the leaf task stuck (I/O, lock, resource exhaustion)?
8. Is there a dependency requiring a task in the same pool whose workers are all held by waiting parents?

Do not infer from `queueSize==0` that all work is done. A pool with empty queues can still have workers waiting on each other without making progress.

## 15. Common code review mistakes

**Mistake 1: Self-join.** A task waits on the very task currently computing.

**Mistake 2: A→B→A.** Two tasks wait on each other; adding workers does not create a completion order.

**Mistake 3: A→B→C→A.** Indirect cycles that are hard to spot when dependencies span multiple modules.

**Mistake 4: Parent holds a monitor/permit while joining a child that needs the same resource.** Hidden resource-wait cycle.

**Mistake 5: Forking a task but forgetting to join the required result.** The parent may return too early or miss child failures.

**Mistake 6: Joining a task that has no path to be scheduled/completed.** No obvious cycle, yet it still hangs.

**Mistake 7: Treating a `ForkJoinTask` instance as reusable and forking it arbitrarily multiple times.** Violates its completion lifecycle.

**Mistake 8: Blocking I/O or `Future.get` without a timeout inside `compute`.** Worker capacity can be starved.

**Mistake 9: Assuming `ManagedBlocker` always creates a new worker.** It only assists with managing certain blocking operations, subject to constraints.

**Mistake 10: Assuming `ManagedBlocker` solves cyclic graphs.** A broken graph must be fixed.

**Mistake 11: Tasks that are too small.** Scheduling overhead exceeds the benefits of parallelism.

**Mistake 12: Using `Thread.sleep` to "wait for a child".** Sleep does not synchronize task completion/visibility.

**Mistake 13: Multiple tasks modifying the same mutable array without partitioning or synchronization.** Fork/Join does not make data races disappear.

**Mistake 14: Thinking `cancel(true)` interrupts a `ForkJoinTask` worker by default.** The `ForkJoinTask` Javadoc states otherwise.

**Mistake 15: Ignoring exceptional completion.** The parent must handle child failures instead of assuming a valid result.

**Mistake 16: Treating `getQueuedTaskCount == 0` as all tasks finished.** Workers may be blocked.

**Mistake 17: Updating a dependency graph dynamically without synchronization.** Two threads adding edges concurrently can introduce a cycle.

**Mistake 18: Using the common pool for long, uncontrolled blocking tasks.** Impacts other tasks sharing the common pool.

**Mistake 19: Confusing dependency completion with database transaction ordering.** Fork/Join does not roll back side effects.

**Mistake 20: Running real deadlock tests without guards.** Can hang CI or the JVM; check graphs statically or design bounded tests.

## 16. Design checklist

- [ ] Is the dependency arrow direction defined consistently?
- [ ] Do all dependencies have a **valid completion order** (DAG)?
- [ ] Does no task join itself, an ancestor, or a task that indirectly waits on it?
- [ ] Is there cycle detection when building a DAG or adding edges dynamically?
- [ ] Is each task scheduled with clear ownership, without arbitrarily re-forking an instance?
- [ ] Does the parent join the children whose results it needs?
- [ ] Are no locks/permits needed by a child held during `join()`?
- [ ] Can all leaves complete without waiting on an impossible signal?
- [ ] Are there I/O/blocking APIs? Are deadlines, cancellation, and `ManagedBlocker` handled appropriately?
- [ ] Are small tasks bounded by a reasonable threshold?
- [ ] Is there a mechanism for exception propagation and cleanup when a task fails?
- [ ] Does cancellation handling avoid assuming `cancel(true)` always interrupts the worker?
- [ ] Does shared mutable state have clear ownership/synchronization?
- [ ] Are task IDs, dependency IDs, and metrics available to construct a wait-for graph?
- [ ] Is there a clear owner for pool lifecycle and shutdown?
- [ ] Have benchmarks been compared against a sequential algorithm on real workloads?

## 17. Practice questions with answers

**Question 1.** A calls `B.join()`, B calls `A.join()`. Will using `ForkJoinPool(32)` fix it?

**Answer:** No. A dependency cycle has no valid completion order, regardless of how many workers there are.

**Question 2.** Why is `left.fork(); right.compute(); left.join()` generally recommended?

**Answer:** The current worker executes one branch while the other branch can be executed by another worker; afterward it only waits for the needed result. This reduces unnecessary task creation/scheduling and keeps the graph clear.

**Question 3.** A parent holds lock L and then joins a child that needs L. Where is the bug?

**Answer:** The parent releases L only after `join`, while the child finishes only after acquiring L: a resource-wait cycle. You must change lock ownership ordering or split the processing phases.

**Question 4.** Does `ForkJoinTask.join()` have a timeout like `get(1, SECONDS)`?

**Answer:** No. `join` has no timeout overload; `get(timeout)` only limits the caller's wait phase.

**Question 5.** Does `ForkJoinTask.cancel(true)` always interrupt the worker?

**Answer:** No. The default implementation does not use `mayInterruptIfRunning` to control interruption.

**Question 6.** Does `ManagedBlocker` break A→B→A?

**Answer:** No. It can help compensate with workers for blocking, but it does not change the dependency graph.

**Question 7.** Is the graph Root→A, Root→B, A→C, B→C a DAG or a cycle?

**Answer:** A DAG. Node C is a shared prerequisite; there is no backward path forming a cycle.

**Question 8.** If an array is modified by another thread while `SumTask` is summing it, is the result guaranteed to be correct?

**Answer:** No. Fork/Join does not automatically prevent data races on mutable input data; ownership/snapshots or synchronization are required.

**Question 9.** Does an acyclic graph guarantee the program will never hang?

**Answer:** No. A leaf can wait indefinitely on I/O, an unreleased resource, or an unscheduled task.

**Question 10.** Why is checking for cycles before submission better than creating a broken graph and waiting on `join`?

**Answer:** It fails early, avoids putting the JVM into an impossible wait relationship, and makes debugging clear.

## 18. Official documentation

- **ForkJoinTask (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html
- **ForkJoinPool (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html
- **RecursiveTask (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html
- **RecursiveAction (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html
- **CountedCompleter (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html
- **CompletableFuture (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- **Future (Java SE 17):** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html

**Takeaway:** Fork/Join excels when there are independent computation branches and **acyclic** completion relationships. Work-stealing assists with scheduling, **but cannot fix an A→B→A cycle or a wait cycle through locks/permits**. Designing a proper dependency graph, avoiding holding resources across `join()`, bounding blocking, and checking for cycles before execution are the foundation for ensuring liveness.
