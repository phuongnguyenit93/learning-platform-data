# Irregular Search and Early Stopping Example with CountedCompleter

When searching for a value in a **tree with irregular long/short branches**, a simple approach is sequential recursion: traversing each branch until the value is found. When the data is large enough, multiple branches can be split across workers in a `ForkJoinPool` for parallel processing. However, once a result is found, forcing all remaining branches to finish running before returning is often wasteful.

`CountedCompleter<T>` is a variant of `ForkJoinTask<T>` designed for tasks that have a **completion relationship via a pending count**, making it particularly well-suited for irregular work trees, dynamic branching, results that need to be merged, or **stopping waiting early** when one branch finds the answer. A task can report completion to its parent completer using `tryComplete()`; a branch that finds the answer can use `quietlyCompleteRoot()` to **mark the root as completed immediately**.

**Two things must be distinguished:**

1. **Root completes early:** `pool.invoke(root)`, `root.join()`, or `root.get()` can return after the root is completed.
2. **Child tasks have actually stopped:** this is not automatically true just because the root is completed; other tasks may still be running or have already been forked without checking the stop signal yet.

Therefore, we need to combine **`CountedCompleter` + safe result publication via `AtomicReference` + checking the result flag at cooperative points**, while also managing the pool lifecycle. All content belongs strictly to standard JDK Java concurrency (Java 17+), without using any other frameworks.

## 1. What is the irregular search problem?

Suppose a tree has a very deep left branch, while the right branch has only a few nodes and contains the target value:

```text
                 ROOT
                /    \
               /      \
         LEFT (deep)  RIGHT
            |          |
          ...        TARGET = 42
            |
         many nodes
```

If traversed sequentially from left to right, the program may spend a lot of wasted work before reaching the right branch. Using Fork/Join, each branch can become a small task for idle workers to **work-steal** and process. Because the tree is irregular, workers do not necessarily receive equal amounts of work; the work-stealing mechanism helps reduce imbalance when there are enough tasks.

However, the search requirement is usually to **find any element that satisfies the condition**, not necessarily the smallest element in traversal order. When one branch sees `42`, we can return the result early and let other branches **check the stop signal themselves**.

The contract should be defined upfront:

- **Find any:** accepts any one of multiple matches; CAS can be used to select exactly one "winner". The result may differ between runs if there are multiple matches.
- **Find first/min index:** must guarantee selection order; simply taking the first match found by the scheduler is **incorrect**. A different position-comparison/optimization algorithm is needed, and a conclusion can only be made once branches that could contain a higher-priority answer have been processed.
- **Stop early:** requires cooperation to reduce remaining work, not a guarantee that all workers are interrupted immediately.

The examples below choose **find any** and have only one matching node, so the printed output is **deterministic**.

## 2. How does CountedCompleter differ from RecursiveTask?

`RecursiveTask<V>` is typically written in the style: split in half, `left.fork()`, `right.compute()`, `left.join()`, then combine the results. The computation tree has a fairly clear relationship: the parent task waits for the child results to merge them.

`CountedCompleter<T>` allows a more flexible model:

- A task has a **parent completer**, but is not required to wait directly on each child using `join()`.
- Each task has a **pending count** to represent the completion signals still needed before it can be completed.
- When a child finishes, it calls `tryComplete()`; completion can propagate up the completer chain.
- A task can override `onCompletion(CountedCompleter<?> caller)` to merge/finalize when enough work is done.
- A branch with an answer can call `quietlyCompleteRoot()` to mark the root as completed **without waiting for the pending tree to reach 0**.
- Because the default result of `CountedCompleter` does not automatically become the found value, we can publish the winner via `AtomicReference` or implement a proper result protocol ourselves.

| Component | Practical Meaning |
|---|---|
| `CountedCompleter<T>` | Base class for tasks with a pending/completer completion mechanism. |
| `new Child(this, ...)` | Sets the current task as the parent completer. |
| `setPendingCount(n)` | Sets the number of pending signals according to the algorithm's protocol. |
| `addToPendingCount(n)` | Increases the pending count if additional work is spawned. |
| `fork()` | Submits the child task into the Fork/Join scheduling mechanism. |
| `tryComplete()` | Reports a completion / that a branch endpoint was reached; may decrement pending or complete and propagate to the parent. |
| `onCompletion(caller)` | Callback invoked when the task is actually completed via the `tryComplete()` path. |
| `quietlyCompleteRoot()` | Marks the **root** as completed immediately, without waiting for all children. |

**Important:** `pending count` is not the number of threads, the number of nodes remaining in the queue, or a `CountDownLatch`. It is a **completion protocol** constructed by the code. Setting the wrong count or missing a `tryComplete()` can cause the root to hang forever when **no** answer is found.

## 3. Understanding the pending count protocol accurately

We use the following consistent pattern for a node with `n` children:

```java
@Override
public void compute() {
    int n = node.children.length;
    setPendingCount(n);

    for (Node child : node.children) {
        new SearchTask(this, child, shared).fork();
    }

    tryComplete();
}
```

This is a **snippet**; the classes and `node`/`shared` variables must be defined. Each child also calls `tryComplete()` when finished. How the counting works:

- The parent sets pending = `n`.
- The parent calls `tryComplete()` itself after forking; this is treated as **one participation turn** of the parent in the protocol.
- Each completed child calls `tryComplete()`; when a child has no pending count, it propagates one completion turn to its parent completer.
- Out of the `n + 1` turns (parent + n children), the **first n turns** decrement pending down to 0; the **last turn** sees the count is 0, so it actually completes the parent and can propagate further up to its parent.

Because the parent and children run concurrently, the order of these turns is **non-deterministic**. Do not assume "the parent is always the first turn" or "the last child in list order will execute the callback". The pattern above is correct thanks to the signal count and atomic counter, not because of execution scheduling.

For a **leaf** with no children, the default pending count is 0; calling `tryComplete()` completes the leaf and notifies its parent completer.

This is just **one valid convention**, not the only way to use `CountedCompleter`. Another pattern might fork `n-1` children, compute the remaining child directly, and adjust the pending count accordingly. What matters is that **the pending count and the actual number of `tryComplete` turns must match**.

## 4. Parallel search and early stopping workflow

A `SearchTask` will work as follows:

```text
SearchTask.compute()
       |
       v
winner != null ? -------- yes ------> tryComplete(); return
       |
       no
       |
node satisfies predicate? -- yes ---> CAS(null, node)
       |                                   |
       |                              CAS wins?
       |                                   |
       |                                  yes
       |                                   v
       |                             quietlyCompleteRoot()
       |                                   |
       |                              tryComplete()
       |
       no
       |
setPendingCount(children.length)
       |
fork each child with completer = this
       |
tryComplete()
```

An `AtomicReference<Node>` holds the first committed match. When multiple workers find a match simultaneously, `compareAndSet(null, node)` allows only **one winner**. Other workers read `winner.get() != null` and skip work that has not started yet.

The phrase "stop early" here has two levels:

1. **Stop waiting at the root:** the winning worker calls `quietlyCompleteRoot()`; threads waiting on the root can retrieve the result immediately.
2. **Reduce remaining computation:** other branches must **check `winner` themselves** and return at a safe point. If a task is doing a long computation or blocking without checking, it may continue running after the root completes.

Do not call `Thread.stop()` or rely on `ForkJoinTask.cancel(true)` to forcibly terminate tasks. In `ForkJoinTask`, `mayInterruptIfRunning` does not act as a promise to interrupt the worker the way `FutureTask` does. For CPU-bound computations, periodically checking a winner/cancellation flag is the appropriate cooperative approach.

## 5. Example 1 — Finding a node in an irregular tree

We create a tree with one long left branch and short right branches. The root distributes work to its children, and idle workers can steal tasks. If a branch finds `42`, it records the winner using CAS and calls `quietlyCompleteRoot()`.

Create the file **`CountedCompleterIrregularSearch.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CountedCompleterIrregularSearch {
    static final class Node {
        final int value;
        final Node[] children;

        Node(int value, Node... children) {
            this.value = value;
            this.children = children;
        }
    }

    static final class SearchTask extends CountedCompleter<Void> {
        private final Node node;
        private final AtomicReference<Node> winner;

        SearchTask(
                CountedCompleter<?> parent,
                Node node,
                AtomicReference<Node> winner) {
            super(parent);
            this.node = node;
            this.winner = winner;
        }

        @Override
        public void compute() {
            if (winner.get() != null) {
                tryComplete();
                return;
            }

            if (node.value == 42) {
                if (winner.compareAndSet(null, node)) {
                    quietlyCompleteRoot();
                }
                tryComplete();
                return;
            }

            setPendingCount(node.children.length);
            for (Node child : node.children) {
                new SearchTask(this, child, winner).fork();
            }
            tryComplete();
        }
    }

    static Node irregularBranch(int levels) {
        Node current = new Node(-1);
        for (int i = 0; i < levels; i++) {
            current = new Node(-1, current, new Node(-1));
        }
        return current;
    }

    public static void main(String[] args)
            throws InterruptedException {
        Node rootNode = new Node(
                -1,
                irregularBranch(12),
                new Node(-1, new Node(42))
        );

        AtomicReference<Node> winner = new AtomicReference<>();
        SearchTask root = new SearchTask(null, rootNode, winner);
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            pool.invoke(root);
            Node found = winner.get();
            System.out.println("Found: "
                    + (found == null ? "none" : found.value));
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
```

Commands to run on JDK 17+:

```bash
javac CountedCompleterIrregularSearch.java
java CountedCompleterIrregularSearch
```

Output when unaffected by external interrupts/resource shortages:

```text
Found: 42
Root done: true
```

**Explanation:**

- `irregularBranch(12)` creates a branch with 12 levels, adding a short child branch at each level. The right branch of the root has only an intermediate node leading to `42`.
- Each node's `SearchTask` calls `setPendingCount(children.length)`, forks its children, and calls `tryComplete()`. Leaves call `tryComplete()` to report completion; if there is no match, completion signals propagate back up to the root.
- When a match is found, `winner.compareAndSet(null, node)` selects the first result; `quietlyCompleteRoot()` completes the root so `pool.invoke(root)` can return.
- **There is no guarantee that the match will be found before another worker finishes traversing the long branch.** Work-stealing, execution order, and scheduling depth are non-deterministic. What is guaranteed in this example is the unique matching value.
- After `pool.invoke(root)` returns, `main` may not know whether all children have finished. `pool.shutdown()` along with `awaitTermination()` are used to manage the lifecycle of the **custom pool** before exiting the program.

### Why use AtomicReference instead of volatile Node?

Because the algorithm can encounter **multiple matches** when the data is expanded. A `volatile Node winner` lets readers see the written reference, but two writers could both check `winner == null` and overwrite each other. CAS on `AtomicReference` ensures **only one winner is committed**. If the problem accepts any match and does not require uniqueness of the commit, `volatile` might suffice in a different design; however, for a "first successful claim", CAS is clear and easy to verify.

If you want the **node with the smallest key** or **lowest position**, picking "the first worker to win CAS" **does not guarantee** that result. You must adjust the selection algorithm and the point at which early conclusion is allowed according to priority order.

## 6. Why doesn't CountedCompleter return the winner by default?

Do not assume:

```java
CountedCompleter<Node> root = ...;
Node result = pool.invoke(root);
```

will automatically return the `Node` that was found. This is only a type snippet, not a full program. `CountedCompleter` **does not have a built-in value-result storage mechanism by default** like `RecursiveTask.compute()` returning `V`; the default implementation of `getRawResult()` returns `null`. If you want to return data directly through `ForkJoinTask`, you must implement an appropriate result protocol and ensure proper publication/completion.

The examples use `CountedCompleter<Void>` for completion and an `AtomicReference<Node>` for the winner. Because CAS publishes the winner **before** `quietlyCompleteRoot()`, a caller that observes root completion and reads the `AtomicReference` can retrieve the published result. This is clearer than expecting `invoke()` to return `Node` automatically.

**Do not confuse:** `quietlyCompleteRoot()` sets the root's completion state, but it does not run `onCompletion()` for the root by simulating sufficient pending counts, nor does it automatically execute cleanup for the children. If you need to merge results or perform cleanup in `onCompletion()`, do not treat `quietlyCompleteRoot` as equivalent to normal completion of the entire tree.

## 7. Example 2 — Proving the root finishes before a slow branch

To demonstrate that **early completion does not mean all children have stopped**, we create two branches:

- **SLOW:** has started, but waits on an unreleased latch `releaseSlow`.
- **HIT:** waits for SLOW to start, then finds the answer and calls `quietlyCompleteRoot()`.
- Main waits for the root to complete; at that point, SLOW is **guaranteed not to have been released yet** and thus has not gone through cleanup. Main prints the results, then opens the latch so SLOW can continue and waits for the pool to actually terminate.

This is a deliberate coordination example. **Blocking inside a ForkJoin worker is not a recommended performance pattern** for real workloads; the latch is used solely to demonstrate the difference in completion.

Create the file **`CountedCompleterEarlyStop.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class CountedCompleterEarlyStop {
    enum Kind { ROOT, SLOW, HIT }

    static final class SearchTask extends CountedCompleter<Void> {
        private final Kind kind;
        private final CountDownLatch slowStarted;
        private final CountDownLatch releaseSlow;
        private final AtomicReference<String> winner;
        private final AtomicBoolean slowFinished;

        SearchTask(
                CountedCompleter<?> parent,
                Kind kind,
                CountDownLatch slowStarted,
                CountDownLatch releaseSlow,
                AtomicReference<String> winner,
                AtomicBoolean slowFinished) {
            super(parent);
            this.kind = kind;
            this.slowStarted = slowStarted;
            this.releaseSlow = releaseSlow;
            this.winner = winner;
            this.slowFinished = slowFinished;
        }

        private SearchTask child(Kind childKind) {
            return new SearchTask(
                    this, childKind, slowStarted,
                    releaseSlow, winner, slowFinished
            );
        }

        @Override
        public void compute() {
            if (kind == Kind.ROOT) {
                setPendingCount(2);
                child(Kind.SLOW).fork();
                child(Kind.HIT).fork();
                tryComplete();
                return;
            }

            if (kind == Kind.SLOW) {
                slowStarted.countDown();
                try {
                    releaseSlow.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    slowFinished.set(true);
                }
                tryComplete();
                return;
            }

            // HIT only finds the answer after SLOW has started.
            try {
                slowStarted.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(e);
            }

            if (winner.compareAndSet(null, "HIT")) {
                quietlyCompleteRoot();
            }
            tryComplete();
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch slowStarted = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);
        AtomicReference<String> winner = new AtomicReference<>();
        AtomicBoolean slowFinished = new AtomicBoolean();
        ForkJoinPool pool = new ForkJoinPool(3);

        SearchTask root = new SearchTask(
                null, Kind.ROOT, slowStarted, releaseSlow,
                winner, slowFinished
        );

        try {
            pool.submit(root);
            root.get(5, TimeUnit.SECONDS);

            System.out.println("Found: " + winner.get());
            System.out.println("Root done: " + root.isDone());
            System.out.println("Slow finished before release: "
                    + slowFinished.get());
        } finally {
            releaseSlow.countDown();
            pool.shutdown();
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool did not terminate");
            }
        }

        System.out.println("Slow finished after release: "
                + slowFinished.get());
    }
}
```

```bash
javac CountedCompleterEarlyStop.java
java CountedCompleterEarlyStop
```

Output when there is no external interrupt:

```text
Found: HIT
Root done: true
Slow finished before release: false
Slow finished after release: true
```

**This is the crux of early stopping:**

1. Root sets `pending=2` and forks two children.
2. SLOW signals that it has started, then waits on the latch. HIT waits for that exact signal before publishing the result.
3. HIT performs CAS on `winner` and calls `quietlyCompleteRoot()`; `root.get()` can return while SLOW has still not been released.
4. Because SLOW only sets `slowFinished=true` when leaving `await()`, `main` sees **false** at the moment the root is already done.
5. Finally, `main` opens the latch, the pool is shut down and awaited for termination; after that, SLOW has set the flag to `true`.

Just because `root.isDone() == true` does **not** imply all children have finished. This is why production algorithms must consider ownership: if child tasks are still using streams, files, or shared data, the caller must not close their resources simply because the root was quietly completed.

In the example, the SLOW branch intentionally **does not stop when the winner appears** to prove this boundary. In a real search algorithm, branches must check `winner` frequently and terminate cooperatively at safe points.

## 8. Example 3 — When there is no result, the entire tree must be awaited

A search algorithm must also handle the case where **there is no match**. In that case, no one calls `quietlyCompleteRoot()`; the root only completes when **all branches have reported enough times** via `tryComplete()`. If a child is forgotten, the pending count is set incorrectly, or an early return happens without calling `tryComplete()`, the root can hang indefinitely.

This example splits an array into segments and tries to find a non-existent value. Each leaf increments a counter for every element checked. Because there is no match, after `pool.invoke(root)` the counter must equal the total number of elements.

Create the file **`CountedCompleterNoMatch.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class CountedCompleterNoMatch {
    static final class ScanTask extends CountedCompleter<Void> {
        private final int[] data;
        private final int from;
        private final int to;
        private final int target;
        private final AtomicInteger visited;

        ScanTask(
                CountedCompleter<?> parent,
                int[] data, int from, int to,
                int target, AtomicInteger visited) {
            super(parent);
            this.data = data;
            this.from = from;
            this.to = to;
            this.target = target;
            this.visited = visited;
        }

        @Override
        public void compute() {
            if (to - from <= 4) {
                for (int i = from; i < to; i++) {
                    visited.incrementAndGet();
                    if (data[i] == target) {
                        throw new IllegalStateException(
                                "Unexpected target"
                        );
                    }
                }
                tryComplete();
                return;
            }

            int middle = from + (to - from) / 2;
            setPendingCount(2);
            new ScanTask(
                    this, data, from, middle, target, visited
            ).fork();
            new ScanTask(
                    this, data, middle, to, target, visited
            ).fork();
            tryComplete();
        }
    }

    public static void main(String[] args) {
        int[] data = new int[32];
        for (int i = 0; i < data.length; i++) {
            data[i] = i;
        }

        AtomicInteger visited = new AtomicInteger();
        ScanTask root = new ScanTask(
                null, data, 0, data.length, 99, visited
        );
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            pool.invoke(root);
            System.out.println("All checked: "
                    + (visited.get() == data.length));
            System.out.println("Visited: " + visited.get());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CountedCompleterNoMatch.java
java CountedCompleterNoMatch
```

Output:

```text
All checked: true
Visited: 32
Root done: true
```

All `[from, to)` ranges are disjoint and split down to segments of at most four elements. Each element increments `visited` only once. There is no `target=99`, so there is **no early completion**; the pending protocol and `tryComplete()` must finish completely for `pool.invoke(root)` to return. Using `AtomicInteger` for the demo counter allows branches to increment the same counter without lost updates.

In a real search application, instead of throwing an exception on a match, we would use `AtomicReference` and the winner rule from Example 1. Example 3 intentionally **tests only the no-match path**, a scenario where many `CountedCompleter` implementations are written incorrectly because the design only considers the early-match case.

## 9. Root completion, child completion, and cleanup

In theory, there are three distinct milestones:

```text
match detected
     |
     v
winner.compareAndSet(null, value)
     |
     v
quietlyCompleteRoot()
     |
     +---- root.get()/join()/invoke() can return
     |
     +---- other child tasks may still be running
                              |
                              v
                      cooperatively stop or complete
                              |
                              v
                       all tasks finish
                              |
                              v
                  cleanup/pool termination (if applicable)
```

Do not treat root completion as equivalent to `pool.awaitTermination()`. For a private pool owned by the application, you can shut it down and wait for termination after the root completes; for **`commonPool`**, you must never shut down the shared pool just to wait for child branches of a single request.

To manage branches that remain active after the root has completed:

- Only **read immutable shared data** or access it under a synchronization protocol.
- Have each branch check `winner != null` before expanding the tree and **periodically inside large leaves**.
- Do not hold locks/resources in the caller and close them right after `root.get()` if other tasks are still using them.
- If you need to guarantee that **all children have stopped before returning**, the algorithm must have a **separate whole-tree completion milestone**, or not call `quietlyCompleteRoot` until all children are done. Marking the root done early and waiting for all children are two different goals.
- If real cancellation is needed, propagate a stop flag and define safe cancellation points. `ForkJoinTask.cancel(true)` does not mean interrupting all forked child tasks.

**Memory visibility:** a successful `winner` CAS and `AtomicReference.get()` reads have memory effects corresponding to volatile writes/reads under the Java Memory Model. This ensures safe result publication. Root completion is only the completion milestone of the root; **it does not prove that pending writes from other children have completed or are observable**.

## 10. How does work-stealing help irregular search?

In an irregular tree, some branches contain far more nodes than others. If split into `ForkJoinTask`s, an idle worker can **steal** queued tasks from a busy worker's deque, increasing the chance that a fast branch is processed independently.

However, work-stealing **does not guarantee**:

- That a specific branch runs before another branch.
- That the branch containing the match is always found first.
- That `parallelism=4` means exactly four tasks are running concurrently at all times.
- That search speed always scales linearly with the number of cores.
- That child tasks are automatically canceled after the root completes.

For small branches, fork/steal overhead can be greater than sequential traversal. For very deep trees or trees with very many nodes, forking at every node can create a huge number of tasks, putting pressure on allocation and completion management.

**Appropriate threshold:** only fork when the subtree is large enough (estimable by size/depth/cost), and traverse small subtrees sequentially while checking `winner`. The first example forks at every node to expose the `CountedCompleter` mechanism; it is an **educational example**, not an optimal benchmark/production configuration.

## 11. Avoiding common pitfalls

| Pitfall | Consequence | Fix |
|---|---|---|
| Forking `n` children but setting the wrong pending signal count. | Root may never complete on no-match, or complete too early. | Choose a clear convention and test the no-match path. |
| Forgetting to call `tryComplete()` in a leaf or a branch skipped because a winner already exists. | The completer chain does not receive enough completions; the tree does not finish normally. | Call `tryComplete()` on every appropriate exit path. |
| Calling `quietlyCompleteRoot()` and assuming all children are canceled. | Tasks keep running, using resources that have not been cleaned up. | Cooperative checks and a whole-child confirmation milestone. |
| Writing `winner = node` from multiple threads concurrently. | Matches can be overwritten; winner selection is unclear. | `AtomicReference.compareAndSet(null, node)`. |
| Guaranteeing "first match in order" using CAS first-writer. | Selection depends on the scheduler, not priority position. | Design deterministic ordering and valid conclusion points. |
| Keeping an unsynchronized shared mutable accumulator. | Lost updates or inconsistent result reads. | Immutable results, atomics/locks, or partitioning. |
| Setting `pendingCount=0` and completing the parent before children finish forking. | Missed children / unintended early completion. | Set pending before forking, and complete according to the protocol. |
| Calling `tryComplete()` too many times for a single branch. | Can cause premature completion or unexpected callbacks. | Use a clear protocol and only signal once the branch's work is done. |
| Relying on the root's `onCompletion()` after `quietlyCompleteRoot`. | The callback may not run on the early-completion path. | Separate winner publication and cleanup from callbacks only invoked on normal completion. |
| Ignoring the no-match case. | The root can wait forever when all leaves find nothing. | Test no-match and count all branches accurately. |
| Using `ForkJoinPool` for long blocking I/O. | Workers are held, reducing progress or causing deadlock. | Prefer suitable APIs/executors or `managedBlock` when justified. |
| Forking a task for every tiny node without evaluating overhead. | Task creation/stealing is more expensive than traversing the tree. | Batch or traverse sequentially in small subtrees. |

## 12. Exceptions, cancellation, and abnormal states

`CountedCompleter` is still a `ForkJoinTask`, with normal, exceptional, or canceled completion states. An unhandled exception in `compute()` can lead to abnormal completion, but you should not assume all children will automatically stop or all resources have been released.

Points to note:

1. If `compute()` throws an exception before calling `tryComplete()`, you must understand the **exceptional completion** path and `onExceptionalCompletion()` per the API; do not "swallow" errors and leave the pending tree stuck.
2. If multiple children fail, the design must determine which error is reported to the caller and what remaining children are allowed to do.
3. If the root has already quietly completed due to a match, a later exception from another child cannot automatically roll back an already-succeeded `get()`.
4. When using `get(timeout)`, `TimeoutException` only bounds the caller's wait; it **does not automatically cancel the tree**.
5. `ForkJoinTask.cancel(true)` is not a mechanism to forcibly interrupt running children; a cooperative flag is required.
6. If the result requires side effects (sending requests, writing files), avoid placing off-JVM actions in a region that multiple workers might execute concurrently without idempotency or transactions.

A safe approach is to **separate finding the winner** (CAS, no side effects) from **performing business actions on the winner**. The caller processes the winner after reaching the necessary completion milestone, while also defining what remaining children are allowed to continue accessing.

## 13. CountedCompleter vs. RecursiveTask: which to choose?

| Problem | Usually Suitable | Reason |
|---|---|---|
| Array sum / split in half and wait for both halves | `RecursiveTask<Long>` | Returns a result and uses `join()` for simple combining. |
| Modify disjoint array segments, wait for all | `RecursiveAction` | No return value needed; can use `invokeAll()`. |
| Dynamic work tree, irregular fan-out, completion driven by child signals | `CountedCompleter` | Flexible pending/completer chain. |
| "Find any" and allow root to return early after a match | `CountedCompleter` + atomic winner | `quietlyCompleteRoot()` provides early root completion. |
| Finding a result that must follow strict priority order | Algorithm with separate ordering/completion proof | Scheduler-dependent CAS first-winner is insufficient. |
| Simple search on small data | Sequential loop/recursion | Easy to verify, no task scheduling overhead. |

If the problem only needs fork-left, compute-right, join-left, `RecursiveTask` is usually easier to read and maintain. `CountedCompleter` is powerful but **more complex in its pending protocol**, so use it when the benefits of dynamic completion trees or early completion are truly worthwhile.

## 14. Checklist for building a correct early-stopping search

1. **Define the result:** find any match or the first match in order?
2. **Choose work-splitting data:** independent trees/graphs/search blocks, avoiding multiple tasks mutating the same data unsynchronized.
3. **Define the base case:** if there are no children, check the predicate then call `tryComplete()`.
4. **Specify the pending protocol:** with the example's convention, `setPendingCount(n)`, fork `n` children, parent calls `tryComplete()`, and each child also reports completion.
5. **Set pending before forking:** children can finish very quickly.
6. **Publish the winner atomically:** `AtomicReference.compareAndSet(null, found)`.
7. **Intentional early root completion:** only the valid winner calls `quietlyCompleteRoot()`.
8. **Cooperative stop:** every branch reads `winner` before expanding, and large leaves also check periodically.
9. **Do not use root done as a substitute for all children done:** if whole-tree cleanup is needed, use a separate confirmation milestone.
10. **Test no-match:** the root must complete normally when all leaves find nothing.
11. **Test multi-match:** the result satisfies the predicate, though it does not default to the smallest priority.
12. **Test irregular trees:** deep/short branches, children finishing before parents, and varying execution orders.
13. **Test timeouts and errors:** non-cooperative tasks, exceptions in leaves, mid-flight cancellation.
14. **Measure performance:** compare against sequential traversal, tune thresholds, and observe task creation overhead, work-stealing, and GC.
15. **Manage the pool:** distinguish root completion from custom pool termination; do not shut down `commonPool` for a single request.

## 15. Self-check questions

1. **Does `CountedCompleter` always use `join()` to wait for each child?** No; the pending count and `tryComplete()` coordinate completion.
2. **Does `setPendingCount(n)` automatically fork `n` tasks?** No; the code must create/fork the tasks and emit the corresponding completion signals.
3. **Why set pending before forking?** A child can run very fast and report completion before the parent finishes `compute()`.
4. **What does `quietlyCompleteRoot()` do?** Marks the root as completed early, without automatically canceling children.
5. **After `root.get()` succeeds, can you immediately close resources that children are still using?** Not if the root completed early; ownership and child termination must be managed.
6. **Why use `AtomicReference.compareAndSet(null, node)`?** Only one worker is allowed to publish the winner when multiple matches race.
7. **When there is no match, what causes the root to complete?** All branches reporting `tryComplete()` enough times according to the pending protocol.
8. **Does `CountedCompleter.getRawResult()` return the winner by default?** No; you must design result storage/protocol yourself or use an external atomic winner.
9. **Is `onCompletion()` guaranteed to run just because `quietlyCompleteRoot()` was called?** No; early completion is a different path from normal pending completion.
10. **Does work-stealing guarantee the matching branch runs first?** No, execution scheduling and fan-out are not fixed.
11. **If there are two matches, does CAS first-winner guarantee the smallest position?** No; the winner depends on contention.
12. **Why check `winner` inside large leaves?** To reduce work after another branch has found the answer.
13. **Does `ForkJoinTask.cancel(true)` guarantee interrupting a running worker?** No; cooperative stopping is required.
14. **When is `RecursiveTask` simpler?** When all branches must be processed and results are cleanly merged via `join`.
15. **Why is `CountedCompleter` harder?** Because correctness depends on the pending signal protocol, early completion, and child lifecycles.

**Key takeaway:** `CountedCompleter` uses **pending count + `tryComplete()`** to coordinate work trees, while **`AtomicReference` + `quietlyCompleteRoot()`** publishes a match and frees the caller from waiting on the entire tree. **Root done early does not mean all children have stopped**: cooperative cancellation, ownership, and cleanup must be designed separately.
