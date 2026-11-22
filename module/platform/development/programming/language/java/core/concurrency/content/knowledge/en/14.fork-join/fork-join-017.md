# Why Does `compute()` Returning Not Mean `CountedCompleter` Is Complete?

In Java Fork/Join, `CountedCompleter<T>` is a type of `ForkJoinTask<T>` that supports **completion based on signals and the number of remaining work items to coordinate**, rather than relying solely on a method returning. This is the core difference that easily confuses beginners:

> **`CountedCompleter.compute()` can return normally, yet the task is still not in a completed state.** Completion depends on the protocol of calling `tryComplete()`, `propagateCompletion()`, or the corresponding explicit completion operation; if a signal is missing, the root task may wait indefinitely.

This is not a JVM bug. `CountedCompleter` intentionally separates **executing the `compute` body** from **completing the work tree** because a parent can simply fork subtasks and return while multiple child branches still have to run and send completion signals.

This article explains the mechanism in **Java SE 17+**, belonging to the **Fork/Join** group of **general Java concurrency**, without using Spring Framework concurrency classes or annotations.

## 1. Semantic Differences from `RecursiveTask` and `RecursiveAction`

`RecursiveTask<V>` and `RecursiveAction` are more familiar in the divide-and-conquer model:

- `RecursiveTask<V>.compute()` returns `V`, and when the implementation executes the task normally, that result is used to complete the `ForkJoinTask`.
- `RecursiveAction.compute()` returns `void`; when the task is executed normally, the task's execution under this model proceeds to completion.
- `CountedCompleter<T>.compute()` also returns `void`, but **simply returning does not automatically determine the completion state**. It uses a **completion protocol** with a pending count and a completer chain.

| Aspect | `RecursiveTask<V>` | `RecursiveAction` | `CountedCompleter<T>` |
| --- | --- | --- | --- |
| `compute` signature | `V compute()` | `void compute()` | `void compute()` |
| Familiar mechanism | Compute and return result | Complete action | Completion signals, parent completer, pending count |
| Normal return of `compute` when executed by executor | Usually completes the task | Usually completes the task | **Not sufficient to infer task completion** |
| Coordinating child branches | Usually `fork` then `join` | Usually `fork` then `join` | Usually `tryComplete` or `propagateCompletion` through the chain |
| Problem types | Reduction needing a result | Partitioned tasks without a result | Completion-driven trees, fan-out, and suitable dependency graphs |
| Retrieving result | Task result | No business result | Defaults to `null`; to return `T`, override `getRawResult` |

In `CountedCompleter`, **the task has been executed** and **the task has completed** are two events that must be distinguished. That allows the root task **not to block inside `compute()` waiting for each child**, while still allowing a caller outside the tree to use `pool.invoke(root)` to wait for the entire protocol to complete.

## 2. What Is `CountedCompleter`?

General signature:

```java
public abstract class CountedCompleter<T>
        extends ForkJoinTask<T> {
    public abstract void compute();
    public void onCompletion(CountedCompleter<?> caller);
    public final void tryComplete();
    public final void propagateCompletion();
    public final int getPendingCount();
    public final void setPendingCount(int count);
    public final void addToPendingCount(int delta);
}
```

This is an **excerpt of members for learning**, not a class you can compile: the real `CountedCompleter` resides in the JDK with many other methods/details.

Key components:

- **`compute()`:** does work at a node: processes directly or creates child branches.
- **`completer`:** reference to the node that will receive the completion effect from the current task; usually the parent.
- **`pendingCount`:** atomic counter of **completion signals that need to be coordinated** at the node.
- **`tryComplete()`:** sends one signal into the completion protocol; may decrement pending or, if pending is already 0, execute `onCompletion` and continue up to the completer.
- **`onCompletion(caller)`:** callback when the node reaches the normal completion threshold; often used to merge results from child tasks.
- **`propagateCompletion()`:** like `tryComplete` in its counting/signal-propagation mechanism, but does not invoke `onCompletion` along the propagation path.
- **Task status** (`isDone`, `join`, `get`): for the **root**, it reflects when the completion protocol has marked the root complete.

`CountedCompleter` is designed for algorithms with dependency trees; it does not automatically track the identity of every subtask. **The pending count is not an "auto-registering" child counter** — the algorithm author is responsible for incrementing/setting the count and sending the right signals.

## 3. What Happens When `compute()` Returns?

An error-prone mental model:

```text
compute() starts
   |
   v
fork tasks
   |
   v
compute() returns
   |
   v
[DOES NOT IMPLY isDone == true]
```

With `CountedCompleter`, the normal completion path is not "the executor sees the method return and immediately completes it." Instead, completion is coordinated by calls within the task or its child branches. It can be illustrated as:

```text
                 compute() returns
                       |
                       v
          node may not be complete yet
                       |
            child branches still working
                       |
          child.tryComplete() / ...
                       |
              pending transitions
                       |
             onCompletion if any
                       |
             propagate to completer
                       |
              root is marked
                    complete
```

Remember that **`compute` is not `Future.get`**. Code returning inside a worker is different from the caller holding a handle observing the state of the `ForkJoinTask`. A root can return from `compute` while `pool.invoke(root)` is still waiting because the root has not yet been completed by the protocol.

This is very useful: a parent can **fork a batch of branches and return the thread to the pool**, allowing the worker to continue executing other tasks instead of the parent holding a stack frame and waiting on `join` for each branch.

## 4. Java 17+ Example: Calling `compute()` Directly and Checking Status

Save as `BareComputeReturnDemo.java`:

```java
import java.util.concurrent.CountedCompleter;

public class BareComputeReturnDemo {
    static final class NoSignal extends CountedCompleter<Void> {
        @Override
        public void compute() {
            // Intentionally do not call tryComplete() or complete(...).
        }
    }

    public static void main(String[] args) {
        NoSignal task = new NoSignal();

        task.compute();
        System.out.println("Returned from compute: true");
        System.out.println("Done after return: " + task.isDone());

        task.tryComplete();
        System.out.println("Done after signal: " + task.isDone());
    }
}
```

Run with JDK 17+:

```bash
javac BareComputeReturnDemo.java
java BareComputeReturnDemo
```

Exact stdout:

```text
Returned from compute: true
Done after return: false
Done after signal: true
```

Analysis:

1. `compute()` runs synchronously on the main thread and returns normally.
2. There is no completion call, so `isDone()` remains false.
3. The task has no completer, and pending defaults to 0. `tryComplete()` sees pending is 0, runs the default `onCompletion` (which does nothing), and then marks the root complete.
4. `isDone()` transitions to true.

**Example limitation:** this is a **direct** call to `compute()`, without submitting the task to a `ForkJoinPool`; it is used to demonstrate the distinction between **returning** and **task completion** without depending on scheduling. In practice, you usually submit/invoke the root through a pool rather than treating a direct `compute()` call as the way to launch the framework.

## 5. `tryComplete()`: Each Call May Only Decrement the Count

The Java SE 17 Javadoc defines the basic semantics:

- If the current pending count is **non-zero**, `tryComplete()` **decrements it by one** and **stops completion propagation at that node**.
- If the current pending count **equals 0**, `tryComplete()` invokes `onCompletion(caller)` and then continues the same process with the completer; when the path reaches a root with no completer, the root is marked complete.
- The signal can originate from **the node itself** or from **a child node**, depending on the algorithm.
- Pending-count operations are atomic within the bounds of the defined methods; they **do not automatically manage** the identity/lifecycle of child branches.

Diagram of three calls to a node with `pendingCount = 2`:

```text
Initially node.pending = 2
signal #1: tryComplete() => 2 -> 1, NOT yet complete
signal #2: tryComplete() => 1 -> 0, NOT yet complete
signal #3: tryComplete() => sees 0, calls onCompletion,
                           then propagates to completer/root
```

This is **the easiest point to get wrong**: **pending equal to 0 does not mean the task is complete**. A subsequent `tryComplete` call must observe pending at 0 to perform the completion action under this mechanism.

In many algorithms, the number of `tryComplete` calls is designed to be **initial pending + 1** at that node. However, there are optimization patterns that omit a signal on the parent and set pending lower, so **you must not assume pending always equals the exact number of still-running child tasks**.

## 6. Why Isn't Pending Count an "Automatic Task Counter"?

If you write:

```java
setPendingCount(2);
new Child(this).fork();
new Child(this).fork();
```

this is an illustrative snippet inside a `CountedCompleter`, without a `Child` class definition shown here. Forking two children **does not automatically decrement the count when they return**. Each child must follow the `tryComplete` or `propagateCompletion` protocol, or the parent must manage signals another way.

Therefore, the count can be wrong in either direction:

- **Missing signal:** the root task never completes, and a caller in `join/get/invoke` may wait indefinitely.
- **Extra signal / count set too low:** a node can trigger completion prematurely while branches are still running or merged data is not yet ready.
- **Ignoring failures:** a branch that throws an exception or is canceled may not send a normal completion as expected; the failure policy must be distinguished from the normal path.
- **Not synchronizing external changes:** `setPendingCount` does not automatically protect other mutable fields if there are concurrent writers outside the algorithm.

Documentation should say **"pending is a counter of completion signals according to the algorithm's protocol"**, rather than "pending is the number of running threads" or "pending is definitely the number of unfinished children."

## 7. Two Correct Counting Strategies for Two Children

Suppose a parent splits into two completely independent children.

**Strategy A — parent also sends its own signal:**

```java
setPendingCount(2);
left.fork();
right.fork();
tryComplete(); // Parent's signal: finished dispatching children.
```

Each child, after finishing its work, calls `tryComplete()` with `completer = parent`. A total of three signals reach the parent: one from the parent + two from the children. With initial pending 2, the third signal observes count 0 and completes the parent.

**Strategy B — parent directly executes one child:**

```java
setPendingCount(1);
right.fork();
left.compute(); // This child calls tryComplete() on its own completion path.
```

The parent **does not call `tryComplete()` an extra time** on this path. There are two completion signals from the two children; pending is set to 1 so the first signal decrements it to 0, and the second signal completes the parent.

Both snippets are illustrative `compute` bodies, assuming the children have the correct completer and send an appropriate signal upon finishing. Do not mix the two strategies in the same place: if in Strategy B you also call `tryComplete` on the parent again, the parent may complete prematurely while a child is still unfinished.

**Rule:** choose the count based on **the actual number of signals that will arrive**, not on how many `fork()` calls appear in the code.

## 8. Java 17+ Example: Two Children + One Parent Signal

Save as `CountedCompleterSignalsDemo.java`:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class CountedCompleterSignalsDemo {
    static final class Root extends CountedCompleter<Void> {
        final AtomicInteger childActions = new AtomicInteger();
        final AtomicInteger rootHooks = new AtomicInteger();

        @Override
        public void compute() {
            setPendingCount(2);
            new Child(this).fork();
            new Child(this).fork();

            // Parent finished dispatching branches, but children may not be done yet.
            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            rootHooks.incrementAndGet();
        }
    }

    static final class Child extends CountedCompleter<Void> {
        private final Root root;

        Child(Root parent) {
            super(parent);
            this.root = parent;
        }

        @Override
        public void compute() {
            root.childActions.incrementAndGet();
            tryComplete(); // Send signal via completer = root.
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        Root root = new Root();

        try {
            pool.invoke(root);

            System.out.println("Child actions: "
                    + root.childActions.get());
            System.out.println("Root onCompletion: "
                    + root.rootHooks.get());
            System.out.println("Pending: " + root.getPendingCount());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CountedCompleterSignalsDemo.java
java CountedCompleterSignalsDemo
```

Exact stdout:

```text
Child actions: 2
Root onCompletion: 1
Pending: 0
Root done: true
```

**Why this does not depend on scheduling:**

1. The parent sets pending = 2 **before forking**, so a child cannot send completion before the count is configured.
2. There are exactly **three** signals to root: the parent's `tryComplete` and the two children's `tryComplete`.
3. The first two signals decrement the count via the atomic protocol; the final signal observes 0 and runs root's `onCompletion` once.
4. `pool.invoke(root)` returns normally only after root is marked complete; by then both children have updated `childActions`.
5. The order in which parent/children send signals **is not assumed**, yet the total signal count and outcome remain invariant.
6. `rootHooks` is incremented inside the normal completion callback, not by the constructor or by `compute` returning.
7. There are no `join()` calls on individual children; the parent receives completion via signals from the children rather than blocking while waiting on each branch.

If you omit one of the three signal calls without adjusting the protocol, root may **never complete**, even though the child actions have finished.

## 9. Subtle Case: Pending Is Already 0, Yet Root Still Has `isDone() == false`

Suppose a parent has only one child and writes:

```java
setPendingCount(1);
new Child(this).fork();
// FORGOT parent's tryComplete().
```

The child finishes and calls `tryComplete`; this operation sees the parent's pending count is 1, **decrements it to 0**, and stops. There is no remaining signal to observe 0 and trigger root completion.

In the end, you can have:

```text
child compute: ran
child.tryComplete: called
root.pendingCount: 0
root.isDone(): false
root.join(): may wait indefinitely
```

This is a **missing completion signal bug**, not a bug where `join` stopped working or the pool lacks threads. Increasing the pool's parallelism will not automatically fix a broken completion protocol.

To fix it, the parent must send its own signal (`tryComplete`) **after forking**, or switch the algorithm to a counting strategy that matches the signals that actually exist.

## 10. Java 17+ Example: Missing Signal Bug and Controlled Completion

Save as `MissingCompletionSignalDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class MissingCompletionSignalDemo {
    static final class Parent extends CountedCompleter<Void> {
        final CountDownLatch childReported = new CountDownLatch(1);

        @Override
        public void compute() {
            setPendingCount(1);
            new Child(this).fork();
            // BUG: missing parent's tryComplete().
        }
    }

    static final class Child extends CountedCompleter<Void> {
        private final Parent parent;

        Child(Parent parent) {
            super(parent);
            this.parent = parent;
        }

        @Override
        public void compute() {
            parent.tryComplete(); // Root pending: 1 -> 0.
            parent.childReported.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        Parent parent = new Parent();

        try {
            pool.execute(parent);
            parent.childReported.await();

            boolean gotTimeout = false;
            try {
                parent.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                gotTimeout = true;
            }

            System.out.println("Pending after child: "
                    + parent.getPendingCount());
            System.out.println("Done before fix: " + parent.isDone());
            System.out.println("Timed get expired: " + gotTimeout);

            // Only to terminate the buggy demo cleanly.
            parent.tryComplete();
            System.out.println("Done after missing signal: "
                    + parent.isDone());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

```bash
javac MissingCompletionSignalDemo.java
java MissingCompletionSignalDemo
```

Exact stdout on a normal run:

```text
Pending after child: 0
Done before fix: false
Timed get expired: true
Done after missing signal: true
```

**Intent of the demo:** `childReported` is counted down only after the child has sent one signal to the parent; the parent is still missing its own signal. `get(timeout)` avoids hanging forever, making it possible to **observe that the task is not yet complete**. Afterward, `main` sends the missing signal to release the root.

This is **not a production bug-fix pattern where an external thread arbitrarily calls `tryComplete`**. In a real algorithm, the parent/children themselves must follow a clear protocol; patching with external signals easily causes double completion or data races in complex workloads.

Do not replace the timeout with `parent.join()` when intentionally demonstrating broken code: `join` can wait indefinitely and hang the test.

## 11. `onCompletion(caller)` Is Not a Callback After Every `compute`

`onCompletion(CountedCompleter<?> caller)` runs when the completion protocol triggers normal completion of a node via `tryComplete` or `complete`; **the callback does not run simply because `compute` returns**.

Several cases:

- If `pendingCount > 0`, a `tryComplete` only decrements the count and **does not** call `onCompletion`.
- If `pendingCount == 0` when a `tryComplete` arrives, the callback is invoked on that node.
- If a child sends completion up to its parent, the `caller` parameter helps distinguish which child triggered the completion path.
- With `complete(T)`, the callback is invoked regardless of `pendingCount`, because it is an explicit completion operation by contract.
- `propagateCompletion` **does not call** `onCompletion` during normal propagation.

The Javadoc notes that `caller` may be the task itself or a child task; you should not assume it is always the parent or always equals `this`. In reduction algorithms, `onCompletion` typically merges child results once all are known to be ready.

## 12. Optimization Strategy: Fork One Child, Compute the Other

Unlike the example where a parent dispatches two children and sends its own signal, a binary-splitting algorithm can write:

```java
setPendingCount(1);
right.fork();
left.compute(); // left is a CountedCompleter with this parent.
```

If both `left` and `right` eventually send a completion signal once to the parent, **two signals** are enough to:

1. Have one signal decrement the parent's pending count from 1 to 0.
2. Have the remaining signal observe count 0, invoke `onCompletion`, and propagate up to ancestors.

The parent does not need to send `tryComplete` itself at the end of this branch. Reason: part of the parent's work is **turned into a direct `compute` call** on `left`, and `left` itself will send the completion.

**Warning:** if a caller misunderstands and adds `tryComplete` to the parent as well, there may be **three signals while the count only accounts for two**. The root could be marked complete while a child is still running, leaving results or side effects unready.

Similarly, if `left` simply returns from `compute` and **forgets to call `tryComplete`**, the parent may not receive enough signals — you cannot rely on the child's return to auto-complete.

## 13. Java 17+ Example: Summing with `CountedCompleter<Long>`

This example uses `onCompletion` to merge results **after both children have sent their signals**.

Save as `CountedCompleterSumDemo.java`:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;

public class CountedCompleterSumDemo {
    static final class SumTask extends CountedCompleter<Long> {
        private final int[] data;
        private final int start;
        private final int end;

        private SumTask left;
        private SumTask right;
        private long result;

        SumTask(SumTask parent, int[] data, int start, int end) {
            super(parent);
            this.data = data;
            this.start = start;
            this.end = end;
        }

        @Override
        public void compute() {
            if (end - start <= 4) {
                long sum = 0;
                for (int i = start; i < end; i++) {
                    sum += data[i];
                }
                result = sum;
                tryComplete();
                return;
            }

            int mid = start + (end - start) / 2;
            left = new SumTask(this, data, start, mid);
            right = new SumTask(this, data, mid, end);

            // Two children send two completion signals.
            setPendingCount(1);
            right.fork();
            left.compute();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) {
                result = left.result + right.result;
            }
        }

        @Override
        public Long getRawResult() {
            return result;
        }
    }

    public static void main(String[] args) {
        int[] input = new int[16];
        for (int i = 0; i < input.length; i++) {
            input[i] = i + 1;
        }

        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            SumTask root = new SumTask(
                    null, input, 0, input.length);

            long sum = pool.invoke(root);

            System.out.println("Sum: " + sum);
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac CountedCompleterSumDemo.java
java CountedCompleterSumDemo
```

Exact stdout:

```text
Sum: 136
Root done: true
```

**Detailed explanation:**

- The array holds numbers 1 through 16, so the exact sum is `16 × 17 / 2 = 136`.
- Each non-leaf node creates two children whose `completer` points to the parent.
- Non-leaf nodes use `setPendingCount(1)` because **two children** will each send a completion signal, and the parent does not call `tryComplete` itself on the split branch.
- One child is `fork`ed; the other child is computed **directly on the current thread**. The parent's `compute` returning does not itself finish the parent.
- Leaves compute their own sum into `result` and call `tryComplete`. That signal eventually propagates through ancestors when their counts are ready.
- An internal node's `onCompletion` merges only when both children have completed their required data. This callback may run on the thread performing the **final completion signal**, not necessarily the thread that created the parent.
- `getRawResult()` returns the root's value so `pool.invoke` can return `Long`. By default `CountedCompleter` returns `null` unless an appropriate result is overridden.
- There is no need to `join()` each child; **root completion** is the synchronization boundary for the entire reduction.

Important: this is a reduction model **that does not merge data via a shared mutable accumulator**; each leaf has its own `result`, and internal nodes only read child results once the completion protocol guarantees readiness.

## 14. Can You Call `join()` on `CountedCompleter` Children?

At the API level, `CountedCompleter` is still a `ForkJoinTask`, so it has `join()`. However, **the task status of nodes with a completer may not transition to "done" in the way a `RecursiveTask` user expects**.

The Java 17 Javadoc states that a `CountedCompleter` **with no completer** (the root) can be used as a standalone `ForkJoinTask` with a meaningful completion status; whereas `CountedCompleter`s **with a completer** are typically internal helpers and **their own task status may be arbitrary**, changing only through explicit completion operations or supported exceptional completion.

This leads to the bug:

```java
Child child = new Child(parent);
child.fork();
child.join(); // May wait against the wrong protocol
```

This is an illustrative snippet. If `child` sends `tryComplete` **to the parent** without the child itself being marked complete, `child.join()` does not automatically carry the "child's work is done" semantics of `RecursiveTask`.

**Usually wait on the root**, e.g. `pool.invoke(root)`, `root.join()` after the root has been submitted/forked in the right context, or `root.get(timeout, unit)` for a bounded check. Do not rely on `child.isDone()` as a progress counter for the entire tree.

## 15. Does `getPendingCount() == 0` Prove `isDone() == true`?

**No.** These are two different kinds of state:

| Observation | What Can Be Inferred |
| --- | --- |
| `getPendingCount() == 0` | The pending counter is currently 0 |
| Root's `isDone() == true` | The root task has been marked completed normally, abnormally, or canceled per contract |
| Root's `isCompletedNormally() == true` | The root task completed normally |
| `isCompletedAbnormally() == true` | The task completed abnormally or was canceled per contract |
| `root.join()` returns normally | The root is completed and the caller receives the raw result per contract |

As `MissingCompletionSignalDemo` shows, the root's pending count can already be 0 while the root has not received the next signal to trigger completion. Conversely, `complete(T)` can mark a task complete **regardless of `pendingCount`**. Therefore, there is no two-way equivalence between `pending == 0` and task status.

Moreover, reading `pendingCount` at a point in time is only a **snapshot value**. It does not replace the waiting contract of `join/get/invoke`, nor is it a way to measure how many workers are currently running or predict a completion deadline.

## 16. How Does `propagateCompletion()` Differ from `tryComplete()`?

By contract:

- `tryComplete()` may invoke `onCompletion` at the node when pending is 0, then propagate the signal up the chain.
- `propagateCompletion()` performs the corresponding pending-decrement/completion-propagation mechanism **but does not invoke `onCompletion`** along the path.

Use `propagateCompletion` when the algorithm **does not need a result-merging callback** at each node, for example when each leaf writes to its own disjoint data region and you only need to know when the entire tree is done.

Do not replace `tryComplete` with `propagateCompletion` in a reduction that relies on `onCompletion` to compute a sum: the root may be marked complete while the `result` field has not been merged properly.

Visualization:

```text
tryComplete:
  pending > 0 -> decrement
  pending = 0 -> onCompletion -> parent -> ... -> root completion

propagateCompletion:
  pending > 0 -> decrement
  pending = 0 ->               parent -> ... -> root completion
```

Both still must obey **the exact signal count**. `propagateCompletion` does not automatically find unfinished children and does not fix an under- or over-counted pending value.

## 17. Java 17+ Example: `propagateCompletion` Skips the Callback Yet Completes the Root

Save as `PropagateCompletionDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;

public class PropagateCompletionDemo {
    static final class Root extends CountedCompleter<Void> {
        final int[] values = {1, 2, 3, 4};
        final AtomicInteger callbacks = new AtomicInteger();

        @Override
        public void compute() {
            setPendingCount(2);

            new Leaf(this, values, 0, 2).fork();
            new Leaf(this, values, 2, 4).fork();

            propagateCompletion();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        private final int[] data;
        private final int from;
        private final int to;

        Leaf(Root parent, int[] data, int from, int to) {
            super(parent);
            this.data = data;
            this.from = from;
            this.to = to;
        }

        @Override
        public void compute() {
            for (int i = from; i < to; i++) {
                data[i] *= 2;
            }
            propagateCompletion();
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        Root root = new Root();

        try {
            pool.invoke(root);

            System.out.println("Values: "
                    + Arrays.toString(root.values));
            System.out.println("Root callback calls: "
                    + root.callbacks.get());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac PropagateCompletionDemo.java
java PropagateCompletionDemo
```

Exact stdout:

```text
Values: [2, 4, 6, 8]
Root callback calls: 0
Root done: true
```

**Explanation:**

- The two leaves write to non-overlapping ranges `[0,2)` and `[2,4)`.
- The parent sets pending = 2 and sends one signal after forking; the two leaves send two signals via `propagateCompletion`.
- Three signals complete the root, so `pool.invoke(root)` returns.
- No `onCompletion` is called because the entire completion path uses `propagateCompletion`.
- The array result is accurate because the leaves finished their required mutations before the root was completed.

For partitioned transformation tasks, `propagateCompletion` avoids unnecessary combining callbacks; however, if there is other mutable shared state, proper ownership or synchronization is still required.

## 18. `complete(T)`: Explicit Completion Without Waiting for Pending to Reach 0

`CountedCompleter.complete(T rawResult)` has different semantics from `tryComplete()`:

1. It **does not** require `pendingCount` to be 0.
2. It calls `setRawResult(rawResult)` per contract (by default `CountedCompleter` does nothing special).
3. It calls `onCompletion`.
4. It marks that task complete.
5. It forwards completion per the protocol to the completer if one exists.

This is useful for certain **early termination** algorithms once a good-enough result is found, or when a task can proactively publish a result without waiting for every branch. Misusing it, however, can expose an unready result to the caller or leave branches still mutating state.

Illustrative example:

```java
final class SimpleCompleter
        extends java.util.concurrent.CountedCompleter<Void> {
    @Override
    public void compute() {
        complete(null);
    }
}
```

This is an illustrative class without a `main`. `complete(null)` can complete a task even without calling `tryComplete`. For complex computations, **do not call `complete` just to "fix a hanging join"** when the pending protocol is wrong.

If the task has type `T` and you want to return a result from `join/invoke`, you can override `getRawResult()` to read the result field. The default `setRawResult` does not store a value the way `RecursiveTask<V>` users might expect.

## 19. `quietlyCompleteRoot()`: Intentional Early Root Termination

`quietlyCompleteRoot()` marks the root normally complete per the ForkJoin API without necessarily invoking `onCompletion` on every node.

For example, when searching for any element matching a condition: if one branch has already published the result using `AtomicReference.compareAndSet(null, found)`, the algorithm can **proactively complete the root** so the caller receives the result early instead of waiting for all unnecessary branches.

But you must distinguish:

- The root may be marked complete **before all children actually stop**, if the algorithm allows that.
- Still-running children must either be safe to continue or have their own cancellation policy.
- The result data must be published safely, for example via an atomic reference.
- Do not use early completion if the caller will read mutable shared state that children are still modifying without a protocol.
- "Already having a result" does not mean external side effects are rolled back or other tasks are automatically canceled.

Thus, `quietlyCompleteRoot` is a **specialized early-exit tool**, not a careless substitute for a forgotten `tryComplete`.

## 20. Which Thread Runs `onCompletion`?

For `CountedCompleter`, the `onCompletion` callback can be triggered by a `tryComplete` call from **the current node** or from **a subtask**. Therefore, the thread executing the callback may be **the worker that just completed the final signal**, not necessarily the worker that created the node.

This affects:

- **Thread affinity:** you must not assume the parent's `onCompletion` runs on the worker that called `parent.compute()`.
- **Logging context / `ThreadLocal`:** thread-bound data may differ between `compute` and `onCompletion`.
- **Shared state:** rely only on the completion protocol's effect when enough signals arrive, not on thread IDs.
- **I/O or slow callbacks:** running heavy blocking logic inside `onCompletion` can tie up a Fork/Join worker for a long time and hurt throughput.
- **Exceptions:** if `onCompletion` throws an exception, the computation may complete abnormally; the merged result cannot be assumed valid.

Do not use thread names or log ordering to verify completion. Mathematical correctness, the pending protocol, and root completion are what need to be checked.

## 21. Memory Visibility: When Is It Safe to Read a Child's Result?

A `CountedCompleter` algorithm often has each child write to its own result field, and then the parent reads it in `onCompletion`. The Javadoc states that **if the pending count and completion protocol are used properly**, accesses to the results of completed tasks can be performed safely inside the completion callback without additional synchronization solely for reading those fields.

However, that **does not mean all shared mutable state becomes thread-safe**:

- The child must write its result before sending the completion signal.
- The parent must read the result only after the protocol has received the corresponding required signals.
- Tasks must not continue modifying the same result after reporting "work done."
- If an external thread modifies the same field outside the protocol, a data race still exists.
- If using a shared `ArrayList` with multiple children calling `add` concurrently, you need synchronization or a local-results-plus-combine design.
- If early root completion is allowed, the caller may read state while children are still working; you must define which state is stable.

In `CountedCompleterSumDemo`, leaf children write `result` before `tryComplete`, and the parent's `onCompletion` merges only after both child signals arrive. That is what guarantees correctness, not anything special about naming the field `result`.

## 22. `onExceptionalCompletion`: Errors Are Not Normal Completion

`CountedCompleter` has the hook:

```java
public boolean onExceptionalCompletion(
        Throwable ex,
        CountedCompleter<?> caller)
```

This hook can be invoked when a task completes **abnormally**, such as when `compute` throws an exception or the task is marked exceptional. By default, it returns `true` to allow propagating exceptional completion to the completer when appropriate.

If you override it, understand the return value: `true` allows the exception to continue propagating up the chain, while `false` stops propagation along that path. This is **not** the normal completion callback `onCompletion`.

If a child fails, the parent may not receive a normal signal; propagating exceptional completion is designed to prevent the parent from waiting forever for the success of a failed computation. However, not every failure/cancellation of every task outside the system is automatically propagated meaningfully — only when the task and completion chain adhere to the contract.

**Do not automatically catch an exception and call `tryComplete` as if the child succeeded** if the child's data is invalid; doing so can cause the root to complete normally with a wrong result.

## 23. Java 17+ Example: An Exception from `compute` Can Complete the Task Abnormally

Save as `ExceptionalCountedCompleterDemo.java`:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;

public class ExceptionalCountedCompleterDemo {
    static final class FailingTask extends CountedCompleter<Void> {
        @Override
        public void compute() {
            throw new IllegalStateException("bad input");
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        FailingTask task = new FailingTask();

        try {
            boolean caughtExpected = false;
            try {
                pool.invoke(task);
            } catch (IllegalStateException e) {
                caughtExpected = true;
            }

            System.out.println("Caught exception: " + caughtExpected);
            System.out.println("Completed abnormally: "
                    + task.isCompletedAbnormally());
            System.out.println("Done: " + task.isDone());
        } finally {
            pool.shutdown();
        }
    }
}
```

```bash
javac ExceptionalCountedCompleterDemo.java
java ExceptionalCountedCompleterDemo
```

Stdout on a normal run:

```text
Caught exception: true
Completed abnormally: true
Done: true
```

**Why does this not contradict the title?** The rule "returning from `compute` does not complete the task" refers to a **normal return without a completion signal**. In this example, `compute` **does not return normally** — it throws an exception; Fork/Join records abnormal completion. This is **a different completion path**, not a mechanism that auto-completes a normal `CountedCompleter`.

There is no need to throw `InterruptedException` in this failure example; it uses an unchecked `IllegalStateException` to highlight the exceptional path.

## 24. When a Child Has a Completer, Why Can Its Own `isDone()` Be Unreliable?

In many `CountedCompleter` algorithms, a child is simply:

```java
@Override
public void compute() {
    doWork();
    tryComplete();
}
```

This is an illustrative snippet, with an application `doWork()`. When a child has a completer:

1. `tryComplete` on the child sees the child's pending count is 0 and triggers the child's callback.
2. It propagates the signal up to the parent and may decrement the parent's pending count or trigger the parent's completion.
3. **The child's own task status** may not be marked normally complete like a `RecursiveTask` while the root still progresses.
4. Therefore, polling `child.isDone()` or calling `child.join()` to verify that the algorithm has finished easily violates the contract.

The root without a completer is usually **the waiting point for publishing the result**. If you want each child to truly have its own completed `Future`, the design may need a different task type or deliberate explicit completion operations; do not accidentally mix the two models.

**Observe that pending and task status are different:** the pending field may drop to 0 while the child is not yet marked done, and this is not necessarily a bug if the root protocol progresses properly.

## 25. `firstComplete()`, `nextComplete()`, and Completion Traversal

Besides `tryComplete`, `CountedCompleter` supports:

- `firstComplete()`: when pending is non-zero, decrements the count and returns `null`; if pending is 0, returns the task itself to begin a completion traversal.
- `nextComplete()`: advances to the completer, possibly decrementing the parent's pending count or returning the parent when the completion condition is met; at the root, handles marking completion.
- `getRoot()`: gets the root of the completion chain.
- `helpComplete(maxTasks)`: helps execute some tasks along the completion path when possible.

These APIs are useful for custom algorithms, but harder to use correctly than `tryComplete` for beginners. If you do not need custom traversal, prefer **a clear protocol with pending count and one signal at the end of each successful path**.

Do not replace `tryComplete` with `firstComplete` alone and forget `nextComplete`; manually driving traversal requires understanding exactly which callbacks must run and when the root is marked done.

## 26. Common Mistakes

**1. "`compute()` returning means the task is complete."** False for normal completion of `CountedCompleter` if the completion signal is missing.

**2. "`pendingCount=0` means `join()` is guaranteed to return."** False. The count can be 0 without a call observing 0 to trigger completion.

**3. "`fork()` automatically registers and decrements pending."** False. `CountedCompleter` does not automatically track child identities and states for counting like that.

**4. "Two children always mean `setPendingCount(2)`."** No. If the parent also calls `tryComplete`, count 2 makes sense; if only the two children send signals, count 1 may be right. Count signals.

**5. "Just call `tryComplete` everywhere to be safe."** False. Extra signals can complete early before data is ready.

**6. "`tryComplete` when pending=1 completes the node immediately."** False. It decrements 1 to 0; a later signal triggers `onCompletion`.

**7. "`onCompletion` runs whenever any child finishes."** False. It runs when the completion protocol determines enough signals have arrived (or on explicit `complete`), not as a per-child callback for arbitrary children.

**8. "`onCompletion` definitely runs on the parent's thread."** False. The thread sending the final signal may be another worker.

**9. "`propagateCompletion` also executes `onCompletion`."** False. It skips this hook.

**10. "`complete(null)` only works when pending is already 0."** False. `complete` ignores pending count; misusing it can report completion prematurely.

**11. "`quietlyCompleteRoot` automatically stops all children."** False. It marks the root complete; canceling/cleaning up other children is separate.

**12. "`child.join()` is equivalent to waiting for the child's `compute` to return."** You cannot assume that for a `CountedCompleter` with a completer; child status can be arbitrary.

**13. "If a child throws an exception, the root still has to wait for normal signals forever."** Exceptional completion has its own propagation path via `onExceptionalCompletion` when the protocol is designed properly.

**14. "Increasing the number of threads in `ForkJoinPool` will fix a hung task."** No. If a completion signal is missing, adding workers will not synthesize that signal.

**15. "`getRawResult` by default automatically stores the argument passed to `complete(T)`."** No. `CountedCompleter` returns `null` by default; you must override it to return the actual result.

**16. "All child results are automatically thread-safe because they share the same `ForkJoinPool`."** False. Proper ownership and the completion protocol are what allow safe access at the required boundary.

**17. "A root with `isDone` true means every child has stopped."** Not if the algorithm performs intentional early completion; you must read the application's contract.

**18. "Sleeping for some duration verifies completion."** No. Use `root.get(timeout)`, a latch, or meaningful completion state, not arbitrary delays.

## 27. How to Debug When `pool.invoke(root)` or `root.join()` Hangs

If the root does not return, check in order:

1. **Does the root call a completion signal?** If `compute` forks children and returns, is the root waiting on children and properly accounting for the parent signal?
2. **Does every successful leaf call `tryComplete()` / `propagateCompletion()`?** Is there an early `return` branch that forgot the signal?
3. **Is `setPendingCount` executed before `fork`?** If a child finishes quickly before the count is set, a race causes miscounting.
4. **How many signals is the count modeling?** Does the parent send a signal, how many signals do children send, and what is the initial count?
5. **Are there extra or missing completion signals on error paths?** Are exceptions propagated, or caught and forgotten?
6. **Is anyone calling `complete` / `quietlyCompleteRoot` prematurely?** If so, the root may report done while data is still invalid.
7. **Is there a lock/monitor cycle?** A parent holding a lock while waiting for a task that needs that lock easily deadlocks.
8. **Is there blocking I/O inside workers?** The pool may run out of workers to make progress if tasks block for long.
9. **Are you joining child tasks instead of the root?** Child status is not necessarily a valid completion marker.
10. **Did you try increasing parallelism to mask a bug?** Test with a small pool and deterministic cases, and fix the contract rather than just adding threads.
11. **Is merged data written before the signal?** If written after the signal, the parent may merge unready data.
12. **Are multiple threads mutating pending count uncontrollably?** The methods are atomic, but the overall logic must still be sound.

A thread dump can show a worker waiting, but **it does not directly point out which completion signal was forgotten**. Combine leaf counters, expected signal counts, `root.getPendingCount()`, callbacks, and `get(timeout)` to diagnose.

## 28. When Should You Use `CountedCompleter` Instead of `RecursiveTask`?

`CountedCompleter` is useful when:

- Many subtasks only need to **report completion up a tree** without the parent waiting on each child with `join`.
- There is large fan-out/fan-in and results are merged via completion actions.
- Some algorithms can **terminate early** once an acceptable result is found.
- You need complex traversal or completion dependencies where pure fork/join would cause many blocking joins.
- You can accurately prove the **counts/signals/ownership** for all success and failure paths.

However, it is **harder to use than `RecursiveTask`** because the author must manually ensure the pending protocol. If you are only summing an array, `RecursiveTask<Long>` with `left.fork(); right.compute(); left.join()` is usually easier to read and review.

Do not choose `CountedCompleter` just to avoid writing `join` or because you heard it is "faster." Cost and benefit depend on the data tree, leaf size, work-stealing, contention, and the actual algorithm.

## 29. Self-Check Questions

**Q1:** `CountedCompleter.compute()` returns normally without calling any completion method. Is the root's `isDone()` guaranteed to be true?

**No.** There is no mechanism that auto-completes a normal `CountedCompleter` just from returning; the root may remain not done.

**Q2:** Initial `pendingCount` is 2, and `tryComplete()` is called twice on the same node. Must the node be complete yet?

**Not yet.** Two calls may only decrement 2 → 1 → 0. A subsequent call observing 0 is what triggers `onCompletion`.

**Q3:** Two children are forked and the parent also has one `tryComplete` after forking. What should the parent's pending count be set to under this simple strategy?

**2**, corresponding to three total completion signals (parent + two children); the final signal observes 0.

**Q4:** The parent forks `right` and computes `left` directly; both children send signals, and the parent does not send its own signal. What should pending be set to?

**1**, so there are two signals: one decrements to 0 and one triggers completion.

**Q5:** Does `getPendingCount() == 0` prove `root.join()` will return?

**No.** It may have decremented to 0 without a completion action yet; you must check the root status and whether the protocol is still missing a signal.

**Q6:** Why shouldn't you call `join()` on every child in a `CountedCompleter` tree?

Because internal `CountedCompleter`s with a completer are usually helpers; their own task status may not be marked complete like a `RecursiveTask`. Root completion is the reliable waiting point by design.

**Q7:** When is `propagateCompletion` appropriate?

When you do not need `onCompletion` to merge results; it propagates completion while skipping the callback, provided signals are counted accurately.

**Q8:** If children need to return results, where should the merging logic be placed?

Usually in the parent's `onCompletion`, after the completion protocol confirms all required child results are ready. For the root result, override `getRawResult` appropriately.

**Q9:** Does `complete(T)` wait for `pendingCount` to reach 0?

**No.** It completes explicitly regardless of count; use it only when the contract allows terminating that way.

**Q10:** If a child throws an exception in `compute`, can it be treated as a normal signal?

No. Exceptional completion has its own mechanism and can propagate via `onExceptionalCompletion`; do not turn an exception into a fake normal result.

**Q11:** Will increasing `ForkJoinPool` from 2 to 32 workers fix a missing `tryComplete` bug?

No. A missing signal is a logic bug, not a lack of workers.

**Q12:** Why can `onCompletion` run on a different thread from the parent's `compute`?

Because the final signal can be sent into the completion chain by a child running on another worker.

## 30. Production Readiness Checklist

1. **Clearly define the root and completer tree.** Which task is the root with no completer, and which tasks are helpers?
2. **Explicitly document how many signals arrive at each node.** Does the parent signal itself, and does each child signal?
3. **Set pending count before forking children.** Avoid children finishing too fast before the count is configured.
4. **Every normal completion path sends the exact number of signals.** Do not forget early-return branches.
5. **No double signaling.** Extra signals can complete early and make callbacks read unready data.
6. **If there is a result, write data before signaling.** The parent reads when the completion protocol has enough signals.
7. **Choose `tryComplete` or `propagateCompletion` intentionally.** Do not drop combining callbacks by switching APIs arbitrarily.
8. **Use `onCompletion` to merge once all dependencies are met.** Do not rely on thread execution order.
9. **The root is the waiting point for publishing results.** Do not assume child `isDone/join` is equivalent to a completion signal.
10. **Define exceptions and cancellation separately.** Do not turn partial failures into normal completion.
11. **Do not patch with unverified `complete(null)`.** Explicit completion can break the condition of waiting for all children.
12. **Do not wait on a task while holding a monitor needed by that same task.** Avoid lock-cycle deadlocks.
13. **Use timeouts in tests for protocol bugs.** `root.get(timeout)` prevents tests from hanging forever if a task is missing a signal.
14. **Measure task size and overhead.** `CountedCompleter` does not make an overly fine-grained algorithm fast on its own.
15. **Benchmark against a simple `RecursiveTask`.** Pick the tool with real benefit.
16. **Manage dedicated `ForkJoinPool` lifecycles.** Call `shutdown` if you own the pool; do not shut down the shared common pool.
17. **Re-read the API Javadoc for your Java version.** Do not rely on the "`compute` return == complete" assumption from other task types.

## 31. Summary

- **`CountedCompleter.compute()` returning does not mean the task is complete.** This class's design lets a parent fork children and return while completion is still being coordinated.
- **`pendingCount` is a counter of completion signals**, not an automatically managed count of children or workers.
- **`tryComplete()` when count > 0 only decrements the count**; when the count is already 0, a new signal calls `onCompletion` and propagates to the completer.
- **`getPendingCount() == 0` is not enough to conclude `root.isDone() == true`**.
- **`propagateCompletion()`** preserves the signaling mechanism but skips `onCompletion`; do not use it for reductions that need a result-merging callback.
- **`complete(T)`** can explicitly complete regardless of pending; misusing it can report results prematurely.
- **Internal `CountedCompleter`s with a completer do not necessarily have a meaningful task status for individual joining**; design result retrieval and waiting at the root per contract.
- **Every leaf must send its signal after finishing the required data**, and the pending count must be set before forking.
- **Exceptions/cancellation are a different completion path**, and must not be equated with normal signals.
- **You cannot fork more or add more workers to fix a missing signal bug**; you must fix the completion protocol.

**Key question during code review:** *"How many completion signals is each node waiting for, who will send them, and which call will finally observe pending at 0 to mark the root complete?"* If you cannot answer that precisely, `compute()` returning very likely only means **a worker finished the method body**, not that the entire `CountedCompleter` computation has completed.

**API Reference:** [Java SE 17 — CountedCompleter Javadoc](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html).
