# CountedCompleter: Purpose and Differences from RecursiveTask and RecursiveAction

**`CountedCompleter<T>`** is a type of `ForkJoinTask<T>` in `java.util.concurrent`, designed for work that has **completion relationships depending on multiple subtasks**. Instead of each parent task having to call `join()` to wait for every child, it uses a **pending count**, a **completer** link (usually pointing to the parent), and the **`tryComplete()` / `onCompletion()`** methods to trigger processing once the relevant branches have signaled completion.

This makes `CountedCompleter` useful for traversing or decomposing large datasets, independent per-element operations, tasks with uneven processing times, result aggregation, and tree- or graph-shaped completion structures. In return, **the completion counting protocol is significantly more complex** than `RecursiveTask` and `RecursiveAction`: forgetting a completion signal, setting an incorrect pending count, or lacking synchronization for shared data can cause the root to never complete or aggregate incorrectly.

This article focuses on **general Java concurrency**, using JDK 17+ APIs without Spring dependencies. Examples clearly distinguish standalone runnable programs from snippets explaining algorithms.

## 1. Fork/Join Recap

`ForkJoinPool` is an executor geared toward **work that can be subdivided**. A running task can fork multiple subtasks; workers use a *work stealing* mechanism to utilize branches waiting in deques. The three important types of `ForkJoinTask` are:

- **`RecursiveTask<V>`**: subdivides a computation **that returns a result of type V**, typically `fork()`ing a child and `join()`ing to obtain the result before combining.
- **`RecursiveAction`**: subdivides **work that does not return a result through the Task**, typically using `invokeAll(...)` or `fork/join`; side effects must be designed to be thread-safe.
- **`CountedCompleter<T>`**: **completion-driven**; nodes signal completion via `tryComplete()` so a completer chain knows when to run `onCompletion()` and mark the root as completed. It can return a result, but is often used with `CountedCompleter<Void>` and external state/output.

### Mental model example: summing array segments

```text
                 [0..8) root
                    /    \
               [0..4)    [4..8)
               /   \       /   \
             [0..2)[2..4) [4..6)[6..8)
```

With `RecursiveTask<Integer>`, each node can wait on a child's `join()` and add the two results. With `RecursiveAction`, each leaf updates a synchronized result structure (for example `AtomicInteger`) and parents simply wait for children to finish. With `CountedCompleter`, a node can **fork children and return from `compute()` immediately**, while **the root's completion is not published** to the caller until enough `tryComplete()` signals propagate up the tree.

**Returning from `compute()` does not necessarily mean the task is completed according to `ForkJoinTask.isDone()`**. This is a major difference to keep in mind.

## 2. Comparison Table of the Three Task Types

| Criterion | `RecursiveTask<V>` | `RecursiveAction` | `CountedCompleter<T>` |
| --- | --- | --- | --- |
| Superclass | `ForkJoinTask<V>` | `ForkJoinTask<Void>` | `ForkJoinTask<T>` |
| Main method to implement | `protected V compute()` | `protected void compute()` | `public void compute()` |
| Common goal | Computation returning a single result | Transformation/traversal without returning via Task | Coordinating completion of multiple branches |
| Typical way to wait for subtasks | `fork` then `join`, or `invokeAll` | `invokeAll` / `join` | **Pending count + `tryComplete`**, no need to join each child |
| How result is obtained | Return value from `compute` | External side effect/output | Override `getRawResult()` or external state; default is typically `null` |
| Logic when branches finish | Parent combines after `join` | Parent continues after `join`/`invokeAll` | `onCompletion(caller)` is triggered when pending count meets condition |
| Child status | Child `join` has direct meaning | Child `join` has direct meaning | **Internal children with a completer** should generally not use `join`/`isDone` like a root |
| Difficulty | Easy to read and review for standard divide-and-conquer | Easy to use if tasks are independent | Easy to get pending count, caller, or result publication wrong |
| When to choose | Merge sort, sum, max, tree reduction | Applying per-element transformations | Completion trees, completion triggers, custom traversal, irregular workloads |

**There is no "fastest in all cases" choice**. `CountedCompleter` avoids having every parent wait on children via standard `join`; however, bookkeeping also has overhead. Simple workloads, small trees, or cases needing a direct result are often easier to maintain with `RecursiveTask`.

## 3. Constructors, Completer, and Pending Count

`CountedCompleter` can be constructed with:

```java
super();                   // No completer, pending = 0.
super(parent);             // With completer, pending = 0.
super(parent, initial);    // With completer, pending = initial.
```

This is a snippet inside a subclass constructor, where `parent` is `CountedCompleter<?>` and `initial` is a non-negative `int` according to the protocol being designed. The **completer** is the task that receives propagation when the current node becomes eligible to complete—typically the parent node in the tree.

Counting operations:

- `getPendingCount()`: reads the current pending count of the node.
- `setPendingCount(n)`: sets the pending count according to the node's design.
- `addToPendingCount(delta)`: atomically adds to the pending count.
- `compareAndSetPendingCount(expected, update)`: CAS on the pending count.
- `decrementPendingCountUnlessZero()`: decrements if nonzero, returning the value before the operation.
- `tryComplete()`: if pending is nonzero, decrements it and stops; if pending **is already zero**, invokes `onCompletion` for this node and continues trying to complete its completer, eventually marking the root as completed.
- `propagateCompletion()`: similar to `tryComplete`, but **does not invoke `onCompletion`** on the traversed nodes.
- `firstComplete()` / `nextComplete()`: supports custom traversal once completion conditions are met.
- `quietlyCompleteRoot()`: marks the root as completed without requiring all children to have signaled completion, useful in carefully designed early-return search algorithms.
- `complete(value)`: forces completion of this node **regardless of pending count**, running `onCompletion` and propagating to the completer. Not a general replacement for `tryComplete`.

**The pending count does not store child identities.** It is an **insufficient-signal counter**, not a `List<ForkJoinTask<?>>`. If you need to retrieve results from individual children, the programmer must maintain appropriate references/state manually.

## 4. Understanding `tryComplete()` Precisely

You can remember the core mechanism using this pseudocode:

```text
tryComplete(node, caller):
    if node.pending > 0:
        atomically decrement pending
        stop
    else:
        node.onCompletion(caller)
        if node.completer exists:
            move to node.completer (caller becomes previous node)
            repeat
        else:
            mark root as completed
```

This is **explanatory pseudocode**, not copied Java/JDK source code. A surprising detail: **if pending is currently 1 and you call `tryComplete()`, the count becomes 0, but the callback does not run during that same call**. A **subsequent** `tryComplete()` call that sees pending is already zero will trigger `onCompletion`.

### Example: a parent with two children

An easy-to-verify option is:

```java
setPendingCount(2);
new Node(this, leftRange).fork();
new Node(this, rightRange).fork();
tryComplete(); // Parent signals "my part of the work is done".
```

This is a snippet inside `compute()` of `Node extends CountedCompleter<Void>`, with class-dependent constructors/methods. There are **three completion signal paths** into the parent: the parent signaling itself after forking, left signaling, and right signaling. Pending starts at 2:

```text
One possible ordering scenario:
    pending = 2
    parent.tryComplete(): 2 -> 1
    left completes:       1 -> 0
    right completes:      0 => onCompletion(parent), propagate upward

Or children complete before parent:
    pending = 2
    left completes:       2 -> 1
    right completes:      1 -> 0
    parent.tryComplete(): 0 => onCompletion(parent), propagate upward
```

**In both orderings, the parent is completed exactly once according to the protocol**, provided each node signals once, pending is set correctly, and no abnormal error breaks completion. **Do not assume which node is guaranteed to be the final caller**: the `onCompletion(caller)` callback can be triggered by the parent signaling itself or by a child, depending on interleaving.

**Set pending before forking.** If you fork children first and set pending afterward, a child may finish and signal completion before the parent has registered the dependency, leading to premature completion or invalid state.

### Why does the JDK sometimes use pending = 1 for two halves?

An optimization in the Javadoc: the parent forks one child, while the other half **is computed directly on the current worker** (without creating an independent parent `tryComplete` callback). In that case, the count and number of completion signals differ from the simple `setPendingCount(2)` formula. Such an optimized example can look "off by one," yet it is correct when analyzing **all `tryComplete` paths that actually occur**. Do not copy a pending count from another problem without counting arrivals.

## 5. What Happens When `compute()` Returns?

For `RecursiveTask`, `compute()` returns a result; `ForkJoinTask` generally transitions the task to a completed state according to the execution protocol. For `RecursiveAction`, returning is also tied to finishing the body, and the parent typically joins children before returning.

With `CountedCompleter`, `compute()` **may simply create some children and return**. The root still waits for completion propagation; if the pending count is not handled properly, a call to `pool.invoke(root)` or `root.join()` can **wait forever** even though every `compute()` has returned.

### Illustrative mistake

```java
class Broken extends CountedCompleter<Void> {
    @Override
    public void compute() {
        doWork();
        // BUG: does not signal tryComplete() or equivalent completion.
    }
}
```

This is an **incomplete class/method snippet**, not runnable standalone. `ForkJoinPool.invoke(new Broken())` can wait indefinitely because the root is never marked completed. Returning from `compute()` does **not** mean the `CountedCompleter` is complete.

Correct in principle:

```java
@Override
public void compute() {
    doWork();
    tryComplete();
}
```

This is still a snippet; `doWork` must adhere to exception/cancellation handling. For a node with children, **set pending accurately before forking**; `tryComplete` at the end only signals that the current part of the work is done, and does not necessarily mark the node/root immediately.

## 6. Java 17: The Same Computation with Three ForkJoinTask Types

The following program sums the array `{1,2,3,4,5,6,7,8}` in three ways:

1. `RecursiveTask<Integer>`: each parent joins children's results and adds them.
2. `RecursiveAction`: updates an external `AtomicInteger`, using `invokeAll` to complete children.
3. `CountedCompleter<Integer>`: leaves contribute to an `AtomicInteger`; parents use pending + `tryComplete` without joining children, and the root overrides `getRawResult` to return the sum after completion.

Create the file **`ForkJoinThreeWays.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.RecursiveAction;
import java.util.concurrent.RecursiveTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class ForkJoinThreeWays {
    static final class SumTask extends RecursiveTask<Integer> {
        private final int[] data;
        private final int lo, hi;

        SumTask(int[] data, int lo, int hi) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
        }

        @Override
        protected Integer compute() {
            if (hi - lo <= 2) {
                int result = 0;
                for (int i = lo; i < hi; i++) result += data[i];
                return result;
            }

            int mid = (lo + hi) >>> 1;
            SumTask left = new SumTask(data, lo, mid);
            SumTask right = new SumTask(data, mid, hi);
            left.fork();
            int rightResult = right.compute();
            return left.join() + rightResult;
        }
    }

    static final class SumAction extends RecursiveAction {
        private final int[] data;
        private final int lo, hi;
        private final AtomicInteger total;

        SumAction(int[] data, int lo, int hi,
                  AtomicInteger total) {
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.total = total;
        }

        @Override
        protected void compute() {
            if (hi - lo <= 2) {
                for (int i = lo; i < hi; i++) {
                    total.addAndGet(data[i]);
                }
                return;
            }

            int mid = (lo + hi) >>> 1;
            invokeAll(
                    new SumAction(data, lo, mid, total),
                    new SumAction(data, mid, hi, total));
        }
    }

    static final class SumCompleter
            extends CountedCompleter<Integer> {
        private final int[] data;
        private final int lo, hi;
        private final AtomicInteger total;

        SumCompleter(SumCompleter parent, int[] data,
                     int lo, int hi, AtomicInteger total) {
            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.total = total;
        }

        @Override
        public void compute() {
            if (hi - lo > 2) {
                int mid = (lo + hi) >>> 1;
                setPendingCount(2);  // Register before forking.
                new SumCompleter(this, data, lo, mid, total).fork();
                new SumCompleter(this, data, mid, hi, total).fork();
            } else {
                for (int i = lo; i < hi; i++) {
                    total.addAndGet(data[i]);
                }
            }

            tryComplete(); // This node's own contribution is done.
        }

        @Override
        public Integer getRawResult() {
            return total.get();
        }
    }

    public static void main(String[] args) throws Exception {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            int viaTask =
                    pool.invoke(new SumTask(data, 0, data.length));

            AtomicInteger actionTotal = new AtomicInteger();
            pool.invoke(new SumAction(
                    data, 0, data.length, actionTotal));

            AtomicInteger completerTotal = new AtomicInteger();
            int viaCompleter = pool.invoke(new SumCompleter(
                    null, data, 0, data.length, completerTotal));

            System.out.println("RecursiveTask=" + viaTask);
            System.out.println("RecursiveAction=" + actionTotal.get());
            System.out.println("CountedCompleter=" + viaCompleter);
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool not terminated");
            }
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac ForkJoinThreeWays.java
java ForkJoinThreeWays
```

Stdout on a successful run:

```text
RecursiveTask=36
RecursiveAction=36
CountedCompleter=36
```

### Explaining the semantics accurately

- With `SumTask`, the parent actually **waits for the result** from `left.join()` and adds it to the right half computed directly. The task returns the result via `compute()`.
- With `SumAction`, `invokeAll` ensures children finish; `AtomicInteger` protects the shared sum. `RecursiveAction` does not pass the sum via a return value.
- With `SumCompleter`, the parent registers **2 pending arrivals before forking**. The parent calls `tryComplete()` itself when done with its forking work; each child propagates a signal up the tree upon completion. When the root completes, the atomic total has received all elements; `getRawResult()` returns the sum.
- `CountedCompleter<Integer>` here does not use a `return` value in `compute()` (the method is `void`). **Override `getRawResult()`** so `pool.invoke(root)` receives the result; per the JDK, the default `setRawResult` does not store a value automatically.
- `AtomicInteger` in the Action/Completer branches is a **simple choice to demonstrate completion**, not proof that it is the fastest way to sum. For very large arrays, contention on the atomic total can hurt performance; a per-branch reducer is usually better when optimization is needed.

**Key takeaway:** the same answer 36 is produced, but **how work completion is determined** differs. With `CountedCompleter`, **it is completely valid for the root's `compute()` to return before its children**, while `pool.invoke(root)` still only returns once the root is marked done by the completion protocol.

## 7. What is `onCompletion(caller)` Used For?

The method:

```java
@Override
public void onCompletion(CountedCompleter<?> caller) {
    // Combine results, record a completion, release a stage...
}
```

is a snippet in a `CountedCompleter` subclass. The callback runs when a `tryComplete()` path sees the node's pending count **is already zero**, or when `complete(value)` is called per contract. By default, it does nothing.

Common use cases:

- **Combining children's data** once all relevant branches have completed.
- **Transitioning from map to reduce** once enough results are available.
- **Updating a parent node's state** once to support completion propagation.
- **Triggering the next phase** if the algorithm properly handles ownership, ordering, exceptions, and side effects.

**Note:** the `caller` parameter is the task that caused traversal to reach this node; it may equal `this` or be a subtask. Under the `setPendingCount(2)` + parent `tryComplete()` + two children protocol, **you cannot predict which interleaving will invoke the callback**; do not write code that only processes results when `caller != this` unless you have proven that condition from the exact protocol in use.

## 8. Java 17: Completion Callbacks and Tree Reduction Without Joining Children

The second example keeps results separately in each node rather than using a single `AtomicInteger` to add all elements. Each parent node only combines `left.value + right.value` inside `onCompletion`, once **both children have signaled completion**. This is a reducer pattern that illustrates callback-based result handling in `CountedCompleter`.

Create **`CountedCompleterReduceDemo.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class CountedCompleterReduceDemo {
    static final class SumNode extends CountedCompleter<Integer> {
        private final int[] data;
        private final int lo, hi;
        private final AtomicInteger callbacks;
        private SumNode left, right;
        private int value;

        SumNode(SumNode parent, int[] data, int lo, int hi,
                AtomicInteger callbacks) {
            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.callbacks = callbacks;
        }

        @Override
        public void compute() {
            if (hi - lo <= 2) {
                int sum = 0;
                for (int i = lo; i < hi; i++) {
                    sum += data[i];
                }
                value = sum;
            } else {
                int mid = (lo + hi) >>> 1;
                left = new SumNode(this, data, lo, mid, callbacks);
                right = new SumNode(this, data, mid, hi, callbacks);

                setPendingCount(2);
                left.fork();
                right.fork();
            }

            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) {
                value = left.value + right.value;
            }
            callbacks.incrementAndGet();
        }

        @Override
        public Integer getRawResult() {
            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger callbacks = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);
        SumNode root = new SumNode(
                null, data, 0, data.length, callbacks);

        try {
            int sum = pool.invoke(root);

            System.out.println("sum=" + sum);
            System.out.println("completionCallbacks="
                    + callbacks.get());
            System.out.println("rootPending="
                    + root.getPendingCount());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                throw new IllegalStateException("Pool not terminated");
            }
        }
    }
}
```

```bash
javac CountedCompleterReduceDemo.java
java CountedCompleterReduceDemo
```

Stdout on a normal run:

```text
sum=36
completionCallbacks=7
rootPending=0
```

**Why 7 callbacks?** The array has 8 elements with a leaf size threshold of 2 ⇒ the binary tree has **4 leaves + 2 intermediate nodes + 1 root = 7 nodes**. Each node goes through `onCompletion` exactly once under the example's pending protocol; a parent's callback adds the two child values after they have completed.

`caller` may vary depending on execution order, but the node count and sum are deterministic. This article **does not print thread names or callback order** because the scheduler does not guarantee them.

**Important regarding memory semantics:** The `left/right/value` fields here belong to each node and are written before the branch signals completion via the `CountedCompleter` protocol. The Javadoc notes that when pending counts are used properly, `onCompletion` can access fields of completed subtasks without additional synchronization for this combine step. This does **not** permit concurrent modification of `value` in other code outside the protocol; callbacks must follow the designed completion tree.

**When data is ordered:** `left.value + right.value` is commutative, making it easy to verify. If the result requires ordering—such as string concatenation, serialization, or sorting—use explicit `left/right` positions and combine in the proper business order, **not based on which task finishes first**.

## 9. Is a Completion Tree a CountDownLatch?

Both `CountDownLatch` and `CountedCompleter`'s pending count use the mental model of "waiting for enough signals." However, they differ:

| `CountDownLatch` | `CountedCompleter` |
| --- | --- |
| An independent latch object; callers can `await()` | A `ForkJoinTask` with a completer chain |
| `countDown` decrements the count down to 0 | `tryComplete` can decrement pending or invoke callback/propagate when count **is already** 0 |
| Callers can block waiting for the condition | A node's completion can be triggered by the thread finishing a child |
| Does not decompose a task tree itself | Tasks can fork children and manage completion |
| Does not combine results itself | `onCompletion` can combine results |
| Single-use latch that stays open once triggered | Each `CountedCompleter` node has its own completion protocol |

**Do not mechanically replace `CountDownLatch(2)` with `setPendingCount(2)`.** The pending count in `CountedCompleter` typically **must also account for the parent node's own `tryComplete`** if the parent also signals once; thus, the initial number represents **the number of decrements before the callback-triggering call**, not simply "2 children still unfinished."

## 10. `propagateCompletion()` and Callback Overhead

When `onCompletion` is not needed on nodes, you can use:

```java
propagateCompletion();
```

in a `CountedCompleter` implementation. It is similar to `tryComplete` regarding pending decrements and propagation to the root, but **skips `onCompletion` callbacks** along the way. This is a reasonable choice for some **for-each side-effect** tasks that do not need parent-level combining.

**Do not use `propagateCompletion` when reduction in `onCompletion` is needed**. If you replace `tryComplete` with `propagateCompletion` in `CountedCompleterReduceDemo`, parent nodes will not sum child results via the callback; the returned sum may be wrong.

`firstComplete()/nextComplete()` are for algorithms needing **custom completion traversal**. They use pending counts to determine which node is ready; the actual logic runs inside a traversal loop written by the programmer. This advanced mechanism is useful for complex reductions but harder to review, so it is unnecessary when `onCompletion` can already express the behavior.

## 11. Return Values of CountedCompleter

For `RecursiveTask<V>`:

```java
@Override
protected Integer compute() {
    return 42;
}
```

is a snippet: `ForkJoinTask` receives the value directly from `compute`.

For `CountedCompleter<T>`, the `compute()` method is **`void`**. Typically, implementations use `CountedCompleter<Void>` and do not return a result via the task. If you want callers of `invoke()/join()` to receive a value, you need to manage result state and **override `getRawResult()`**:

```java
private int result;

@Override
public Integer getRawResult() {
    return result;
}
```

This is a snippet inside `CountedCompleter<Integer>`. The `result` data must be set properly before the root is marked complete. **`setRawResult(T)` by default does not store a value** in `CountedCompleter`. `complete(value)` does not automatically make an object know how to return a value unless result accessors are designed properly.

When choosing a result API, distinguish:

- **Root result**: when `pool.invoke(root)` returns, the root can return an appropriate value.
- **Internal subtask result**: a child with a completer should not be awaited via `join()` like in the normal `RecursiveTask` model; per the Javadoc, the status of an internal child **is not managed the same way as a root** unless there is explicit completion/cancellation/exception.
- **Side effects**: if results are written to an array/map/shared accumulator, proper atomicity/ownership and publication must be designed; do not assume mutable fields are thread-safe by default.

## 12. `getCompleter()`, `getRoot()`, and Parent Mapping

`getCompleter()` returns the completer node attached at task creation; `getRoot()` walks the chain until reaching a node with no completer. They represent **completion topology**.

In a tree:

```text
root (completer=null)
  |
  +-- left (completer=root)
  |     +-- left-left (completer=left)
  |     +-- left-right (completer=left)
  |
  +-- right (completer=root)
```

When a leaf calls `tryComplete()` following the protocol, it can contribute to completing its parent, grandparent, and ultimately the root. This chain is **not a `join`-style waiting link**, nor does it automatically store reverse references to all children. In a reducer, we must keep `left`/`right` references ourselves if we want to read individual results.

If you need a **non-tree** dependency graph (where one node is triggered by multiple different tasks), you must design arrivals, completion ownership, cancellation, failure handling, and paths appropriately. Do not try to assign two completers to one child: the constructor only sets **one** completer link, though you can build a separate trigger object to receive multiple arrivals.

## 13. Exceptions and `onExceptionalCompletion`

In `RecursiveTask`, an exception in a child can be observed when the caller `join()`s it. With `CountedCompleter`, an internal child can signal exceptional completion **along the completer chain** per contract.

There is a callback:

```java
@Override
public boolean onExceptionalCompletion(
        Throwable error, CountedCompleter<?> caller) {
    return true; // Allows propagation per contract.
}
```

This is a snippet inside a `CountedCompleter<?>` subclass. The default implementation returns `true`; returning `false` can prevent propagation to the next completer. However, this single callback **does not automatically roll back** already-completed leaves, close all resources, cancel all running subtasks, or turn side effects that already occurred into a transaction.

### If a leaf throws an exception

- The root may complete exceptionally depending on propagation and whether it has already completed.
- Siblings may still be running, having not yet seen the error; **a root exception is not proof that all siblings have stopped**.
- If early stopping is needed, design a shared cancellation flag, cooperative checks, or another management mechanism.
- Use `try/finally`/`try-with-resources` to clean up per-leaf resources; do not expect normal `onCompletion` to run on all exceptional paths.
- When the caller `invoke(root)`s, handle exceptions per the `ForkJoinTask` contract; unchecked errors may be wrapped/propagated depending on the API.
- For critical business results, specify the partial results policy clearly; some leaves may have updated shared state before another leaf failed.

**Do not catch `Throwable` and just call `tryComplete()` to silently continue** if you need to report errors. A normal completion signal can hide the fact that processing a partition failed.

## 14. Early Termination: `quietlyCompleteRoot()`

Some problems only need **any single result**: finding the first element matching a condition in the sense of "any matching element found," detecting existence, or finishing once there is a winner.

If a leaf finds a result and publishes it safely via `AtomicReference`, it can mark the root as completed early with:

```java
if (found.compareAndSet(null, candidate)) {
    quietlyCompleteRoot();
}
```

This is a snippet inside a `CountedCompleter` subclass, where `found` is `AtomicReference<T>`. **Do not use this approach for problems that must run all leaves**, such as sums and traversals with mandatory side effects.

**Very important:** the root being "completed" early **does not mean all sibling tasks have stopped**. Subtasks may still be running or already queued. They should periodically read `found` or cancellation state to skip unneeded work, and cleanup and lifecycle must be handled separately.

If the problem requires **the first element in array order** rather than any match, a winner via `compareAndSet(null, candidate)` can depend on scheduling; you cannot call it "first by index" without position comparison logic.

`complete(value)` forces a task to complete regardless of pending count and triggers callbacks/propagation differently from `quietlyCompleteRoot`. Do not use it arbitrarily to "fix" a root that hangs due to miscounting.

## 15. Why Does CountedCompleter Avoid Some Forms of Waiting?

In standard divide-and-conquer:

```java
left.fork();
int b = right.compute();
int a = left.join();
return a + b;
```

The parent worker may spend time at `join()`; `ForkJoinPool` has mechanisms supporting work stealing/helping, so it should not be viewed as an OS thread **always idle-blocking**. Still, parent code is written in a **wait for child result** style.

With `CountedCompleter`:

```java
setPendingCount(2);
left.fork();
right.fork();
tryComplete();
return; // Do not join children.
```

This is a snippet inside `compute()` of a `CountedCompleter` subclass; `left/right` are subtasks with the proper completer. The worker running the parent can switch to executing other tasks after forking and returning; **the completion action** is triggered by the final completion signal.

This can be useful when:
- Leaf tasks have widely varying execution times.
- Results can be combined via a callback on completion.
- A chain of processing stages should be triggered when enough arrivals occur.
- A task graph has many branches where waiting on each branch in the parent leads to inflexible code.

**There is no guarantee that `CountedCompleter` is always faster than `join`.** It adds counters, CAS operations, linkages, and callback logic. For balanced trees and small pure computations, `RecursiveTask` is often easier to write, easier to verify, and fast enough.

## 16. Common Pending Count Mistakes

| Mistake | Consequence | How to avoid |
| --- | --- | --- |
| Forgetting `tryComplete()` in a leaf | Root does not receive enough signals, `invoke`/`join` hangs | Every normal completion path must follow a clear protocol |
| Forgetting parent's own `tryComplete()` when using `setPendingCount(2)` for 2 children | Count may drop to 0 without running callback | Count all arrivals, including parent path |
| Forking child before setting pending | Child finishes before parent registers | Register count before forking |
| Setting pending smaller than actual arrivals | Parent completes too early, missing results | Verify caller counts and timing |
| Setting pending larger than arrivals | Callback/root never reaches completion | State diagrams and tests with timeouts |
| Assuming `setPendingCount(0)` completes task immediately | Pending 0 does not yet invoke callback/complete | Requires proper `tryComplete`/protocol call |
| Calling `tryComplete` multiple times for one completion | Premature callback or broken protocol | Each arrival sends one signal per design |
| Reading `getPendingCount()==0` and combining manually | Count 0 does not mean callback has run | Use `onCompletion`/completion semantics |
| Using `propagateCompletion` in a reducer needing callbacks | Skips combine step | Use `tryComplete` when `onCompletion` is needed |
| Calling `join` on internal `CountedCompleter` children | Child status does not follow root model | Wait on root or use result/trigger protocol |
| Root `compute` returns without signaling | Root never completes | Signal `tryComplete` in the right place |
| Non-idempotent external side effects in completion callback | Hard to recover on system exception/retry | Clear ownership, transactions, and policy |
| Shared output is an unsynchronized `ArrayList` | Data race/corruption | Immutable partitions, concurrent structures, locks/atomics |
| Combining in child completion order instead of logical order | Wrong result for non-commutative operations | Preserve `left/right` or fixed indices |
| Completing root early before required results are ready | Returns partial state | Only early-complete if contract allows |
| Assuming `caller ==` a fixed child | Interleaving changes `caller` | Never predict who sends the last signal |

## 17. Granularity, Threshold, and Performance

Fork/Join **should not create one task per element** when the element count is very large and the per-element operation is tiny. Every task, fork, and pending update has overhead. Choose a threshold so each leaf processes **a sufficiently large batch**:

- For pure CPU processing, base the threshold on data size, CPU work per element, and core count.
- For highly skewed workloads, splitting smaller can help work stealing but increases overhead.
- For blocking I/O, `ForkJoinPool` is usually not the first tool of choice; a blocking worker can reduce throughput depending on managed blocking mechanisms and APIs.
- With many leaves updating a single `AtomicInteger`, contention can become a bottleneck; consider per-subtask results + `onCompletion` as in `CountedCompleterReduceDemo`.
- `ForkJoinPool.commonPool()` is a shared resource; do not block tasks for long periods or shut down the common pool in a way that affects other code. For isolated examples, use `new ForkJoinPool(n)` and shut it down properly.
- Measure throughput, p95/p99, and CPU across thresholds, core counts, and input distributions; do not assume more subtasks are always faster.

### Work stealing does not solve all liveness bugs

If the pending count is wrong, a worker may have nothing left to do while the root is waiting for a signal **that will never arrive**. Work stealing does not generate a missing `tryComplete()`. Reasoning correctly about the completion protocol remains more important than pool tuning.

## 18. When Should You Not Choose CountedCompleter?

Choose `RecursiveTask` or `RecursiveAction` if:

- The problem is straightforward divide-and-conquer and combining after `join` is easy to understand.
- The task tree is small, child results are needed directly in the parent, and there is no complex completion pipeline.
- The team lacks experience verifying pending counts and exception paths.
- Maintainability/readability matters more than callback-based scheduling optimization.
- Simpler cancellation, exception, or structured ownership semantics are needed.

Choose `CountedCompleter` if:

- Tasks decompose and process irregular branches.
- You want **completion-driven callbacks** when multiple pieces of work finish.
- Counts can be designed cleanly and the parent does not need to join each child.
- You want to reduce via `onCompletion` or use custom completion traversal.
- You want early-exit on a safely published winner (with proper handling of orphan tasks).
- You are developing a library/concurrent component where throughput, complexity, and progress are thoroughly tested.

**Do not confuse `CountedCompleter` with `CompletableFuture`:** `CompletableFuture` is an abstraction for representing/composing completion stages, usually easier to use for business-level async workflows; `CountedCompleter` is a **low-level `ForkJoinTask` primitive** for building completion protocols with pending counts and completer chains.

## 19. Applicable Scenarios

### Traversing an array to perform independent actions

If each element must be processed exactly once and no result needs to be collected, use `CountedCompleter<Void>`, fork partitions, and call `tryComplete`. However, for small tasks, `Arrays.parallelSetAll` or appropriate streams are sometimes simpler; weigh the semantics.

### Summing/merging partition results

Use `RecursiveTask` if combining in the parent is easy to write. Use `CountedCompleter` if you want child completion to trigger `onCompletion` without making the parent wait on `join`. If combining is non-commutative, record `left/right` order.

### Searching for "any match"

Use `AtomicReference`/`AtomicInteger` to publish the winner and `quietlyCompleteRoot` if the contract allows early completion. Siblings need to check state themselves to stop; completing the root early does not automatically kill them.

### Pipeline completion

A node can represent a stage that only activates after several upstream branches finish. `CountedCompleter` provides an arrival-counting primitive, but does not by itself provide retries, durable messaging, exactly-once side effects, or backpressure. For distributed business workflows, use appropriate tools/transactions.

## 20. Testing Correctness Across Multiple Interleavings

A test that runs once and prints the right sum is not enough to prove correctness across all schedules. When reviewing `CountedCompleter`, test:

1. Empty input, one element, two elements, and threshold boundaries.
2. Various odd/even sizes and different depths.
3. Thread pools with 1 worker, 2 workers, and many workers.
4. Children finishing very early before the parent's `tryComplete`.
5. Parent's `tryComplete` running before all children.
6. A leaf throwing an exception; the root does not wait forever and the error is reported properly.
7. Multiple leaves writing to shared state; verify memory visibility/atomicity.
8. Whether the `onCompletion` callback is invoked exactly once per protocol.
9. Whether `propagateCompletion` drops a needed combine step.
10. Whether early completion leaves siblings running or causes extra side effects.
11. Cancellation/timeout/shutdown; root wait does not hang indefinitely.
12. Performance when threshold is too small or partitions are skewed.

### Practice testing with a deadline

```java
ForkJoinPool pool = new ForkJoinPool(2);
try {
    CountedCompleter<?> root = createRoot();
    pool.execute(root);
    root.get(5, TimeUnit.SECONDS);
} finally {
    pool.shutdownNow();
}
```

This is a **snippet** requiring imports for `ForkJoinPool`, `CountedCompleter`, and `TimeUnit`; `createRoot()` is application-defined, and the calling method must declare/handle checked exceptions from `get`. Timeouts help detect **liveness failures**, but **do not prove cancellation stops every child**; `shutdownNow()` only attempts to interrupt and should not be relied upon to finish a broken protocol.

**Do not write tests asserting exact callback order by thread name**; work stealing and scheduling vary. Assert invariants such as total sum, callback count, completion status, and that all permitted effects occurred.

## 21. Important FAQ

**1. Is `CountedCompleter` just `RecursiveAction` with a counter?** No. It changes the **completion protocol**: returning from `compute` is not enough; pending count and the completer chain determine when the root completes; it also provides callbacks, traversal, and early-completion APIs.

**2. What is the default pending count?** Zero if the constructor does not pass an initial count.

**3. Does `setPendingCount(2)` mean exactly two children are still running?** Not necessarily. It is an internal count of **how many `tryComplete` decrements are needed before the next trigger**. The protocol also depends on whether the parent signals itself.

**4. When `tryComplete` decrements 1→0, does it call `onCompletion` immediately?** No. When entering the method with a nonzero pending count, it decrements and returns; the next `tryComplete` call that sees zero invokes the callback/propagates.

**5. Can I fork children first and set pending afterward?** Not safe; children may run and signal completion beforehand, breaking the protocol.

**6. Do I need to `join()` each child?** Usually not; that is `CountedCompleter`'s strength. Wait for the **root** to complete, and do not casually join internal children that have a completer.

**7. Is `onCompletion` called by the parent or a child?** It runs on the traversal path triggered by **the final matching `tryComplete` call**. `caller` can be the current node or a child; do not predict the scheduler.

**8. Does `CountedCompleter<Integer>` automatically return a result from `compute()`?** No: `compute()` is `void`. To have `invoke/join` return a value, override `getRawResult()` or manage results per contract.

**9. How does `propagateCompletion` differ from `tryComplete`?** It skips `onCompletion` during traversal. Do not use it if a reducer relies on callbacks.

**10. Does `quietlyCompleteRoot` stop all subtasks?** No. It marks the root as completed early; other tasks may continue running.

**11. Does `CountedCompleter` guarantee wait-freedom?** No. Pending counts and `ForkJoinPool` do not automatically make the whole algorithm wait-free. The root can wait forever if the protocol is buggy.

**12. For a simple sum, which type is easiest to verify?** Usually `RecursiveTask<Integer>` because the result is explicit via `join`; `CountedCompleter` is valuable when you need a completion-driven architecture or specialized workloads.

**13. Can an exception from a leaf affect the root?** Yes, via exceptional completion propagation; however, it does not mean all siblings were canceled or all side effects were rolled back.

**14. Can I use `CountedCompleter<Void>` and a shared array to write results?** Yes, if each leaf owns a disjoint region or uses valid synchronization, and you wait for the root to complete before reading. The task structure does not automatically make array writes atomic for the same element.

**15. Is an internal `CountedCompleter` child having `isDone()==false` after signaling completion a bug?** Not necessarily. Per the API, the status of completers with a parent may not be marked the same way as a root without explicit completion, even after signaling completion through the chain.

## 22. Pre-Production Checklist

- **Why use `CountedCompleter` instead of `RecursiveTask`/`RecursiveAction`?** Is there a measurable completion-driven benefit?
- Does each node have **exactly one completer parent** and a clear responsibility?
- Has `pending count` been calculated from **actual arrivals**, including the parent's `tryComplete` if applicable?
- Is pending set **before** forking any child that could possibly complete?
- Does every normal execution path have `tryComplete`/`propagateCompletion` in the right place?
- Does `onCompletion` need to combine? If so, **do not use `propagateCompletion`**.
- How is child state held? Are `left/right` ordering and visibility valid?
- Does the root's `getRawResult` return data after completing per the protocol?
- Are exceptional paths, cancellation, and early-complete tested with sibling tasks?
- Is long blocking I/O avoided on the common pool, and is shutdown handled by the proper owner?
- Are threshold/granularity measured against real workloads and appropriate core counts?
- Is a shared accumulator causing unnecessary contention avoided?
- Do tests include deadlines, multiple pool sizes, and input boundary cases?
- Must all side effects complete, or is early return allowed? Is the contract clearly specified?

**In summary:** `RecursiveTask` **returns a result** and typically waits on children via `join`; `RecursiveAction` **returns no result** and typically waits for branches to finish; `CountedCompleter` provides a **completion protocol driven by pending counts and callbacks**. Its advantage is that parents do not necessarily join children; in return, the programmer is responsible for counting arrivals, propagating completion, combining results, handling errors, and ensuring liveness. **Only choose `CountedCompleter` when the completion structure genuinely delivers enough benefit to justify the added complexity.**

### References

- Oracle Java SE 17 API: [CountedCompleter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html)
- Oracle Java SE 17 API: [RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- Oracle Java SE 17 API: [RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html)
- Oracle Java SE 17 API: [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)