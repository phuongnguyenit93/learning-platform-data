# tryComplete(), propagateCompletion(), and onCompletion(): Completion Propagation Mechanisms in Java

When using `ForkJoinPool` with the `RecursiveTask` model, developers typically create two child tasks, call `fork()`, and wait with `join()`. However, not every parallel algorithm fits the **parent-waits-for-each-child** style. Some problems are fan-out/fan-in: many subtasks have varying durations, and once enough completion signals arrive, a parent task needs to execute the next step **without forcing a worker to block waiting on each child**.

`java.util.concurrent.CountedCompleter<T>` solves this using a **completion count** and a **completion chain**. It extends `ForkJoinTask<T>`, holds a reference to a *completer* (usually the parent) and a *pending* count that needs to be recorded, and provides three core APIs:

- `tryComplete()`: records a completion signal; when the pending count is already 0, invokes `onCompletion(caller)` and then **propagates up to the completer**.
- `propagateCompletion()`: uses the same recording and upward propagation mechanism, but **does not invoke `onCompletion`** along the propagation path.
- `onCompletion(CountedCompleter<?> caller)`: callback for the normal completion path once enough signals have arrived, used to merge results or perform a continuation.

Correct usage depends heavily on the **signal-counting rules**, not merely remembering method names. Miscounting can cause the root to complete prematurely, run callbacks before data is ready to be merged, or cause `invoke()/join()` to hang forever.

This Knowledge article covers **Java Concurrency's Fork/Join framework in general**, without using Spring-specific mechanisms. The main examples run on **JDK 17+**, accompanied by compile/run commands, stdout, and completion-path analysis.

## 1. When do you need CountedCompleter instead of RecursiveTask?

Imagine scanning a large dataset split into segments. Each segment is processed independently; only after all sub-segments complete is the final step allowed to aggregate the results.

With `RecursiveTask`, the parent typically writes:

~~~java
left.fork();
long rightValue = right.compute();
long leftValue = left.join();
return leftValue + rightValue;
~~~

This is an **illustrative snippet** from a `compute()` method of `RecursiveTask<Long>`, not a standalone runnable program. Calling `join()` on the child is an explicit coordination point; `ForkJoinPool` has helping mechanisms while waiting on `join`, but the algorithm structure remains tied to the parent waiting for the child.

With `CountedCompleter`, the parent can:

1. Set the **number of signals still to be received**.
2. Create/fork the children and let the body of its own `compute()` finish without waiting via `join()`.
3. Have each child call `tryComplete()` or `propagateCompletion()` when it finishes processing.
4. Let signals accumulate up the completer chain; a callback at a parent node runs only when enough signals have arrived according to the protocol.
5. Mark the root as complete when propagation actually reaches the root and completes according to the rules.

This is a **completion-count-based continuation model**, suitable when the task structure is more complex than a sequential join tree. It does not automatically provide data aggregation, locks for shared state, or transactions.

### 1.1 Key members

| Member | Purpose |
| --- | --- |
| `CountedCompleter<T>` | Fork/join task with a counter-based completion protocol. |
| `getCompleter()` | Returns the completer passed to the constructor, usually the parent; the root usually has `null`. |
| `getPendingCount()` | Reads the **current** pending count, not a list of actual children. |
| `setPendingCount(n)` | Sets the required number of signals according to the algorithm contract. |
| `addToPendingCount(delta)` | Atomically increments/decrements the pending count, used when spawning tasks dynamically. |
| `tryComplete()` | Receives a signal; either decrements or invokes callback and moves upward. |
| `propagateCompletion()` | Receives a signal / moves upward **without running the callback**. |
| `onCompletion(caller)` | Handles normal completion at a node when the pending count meets the condition. |
| `onExceptionalCompletion(ex, caller)` | Hook for the exceptional completion path, **distinct** from normal completion. |
| `getRawResult()` | Provides the value for a task returning `T`; by default it does not automatically read from arbitrary fields. |

**Note:** `CountedCompleter` does not automatically maintain a list of which children are running, finished, or failed. The pending count is merely a **synchronized integer**; the program must manage child→parent references and result data itself if needed.

## 2. Pending count: not simply the “number of children”

Precise behavior of `tryComplete()` in Java 17:

- If `getPendingCount() > 0` at the time of the attempt, the operation **decrements the count once** and returns, without calling `onCompletion` at that node.
- If the pending count is **already 0** at the time of the attempt, it calls `onCompletion(caller)` and then continues attempting to complete **this node's completer**.
- When the propagation path reaches a **root with no completer**, the root is finally marked as normally completed so that callers in `invoke()/join()` are released.
- When the callback executes at a node, the `caller` parameter is the task that triggered the propagation step reaching that node; it may be `this` or a child.

The somewhat counterintuitive part: **the signal that transitions pending from 1 to 0 does not invoke the callback**. There must be **one more call** when the count is already 0 to trigger the callback.

### 2.1 A task with an initial pending count of 2

~~~text
Initial pending: 2

1st tryComplete():
    sees pending=2 -> decrements to 1 -> return

2nd tryComplete():
    sees pending=1 -> decrements to 0 -> return

3rd tryComplete():
    sees pending=0 -> onCompletion(caller)
                   -> tries completer next / marks root done
~~~

Therefore, the initial pending count is usually equal to **the number of signals that will arrive at the node before the final triggering signal**.

| How many completion calls will reach the node? | Initial pending usually set to |
| --- | --- |
| 1 signal | 0 |
| 2 signals | 1 |
| 3 signals | 2 |
| N signals | N−1 |

This table is **a rule of thumb for patterns where each signal arrives exactly once and there is no dynamic registration**. It does not replace every `CountedCompleter` algorithm: if a node calls `tryComplete()` on itself after registering children, the total signal count must also include that **self-signal**.

### 2.2 Do not read pending as the number of unfinished children

The pending count does not know task identities; it only knows how many adjustments have occurred. Therefore:

- `pending == 0` **does not prove** all children have finished if any child has not yet sent its signal.
- `pending == 0` also **does not automatically mean the root is done**. One more `tryComplete()`/`propagateCompletion()` call is still needed to trigger the final path.
- `getPendingCount()` is a concurrent snapshot and should not be used alone to determine a transaction/snapshot of child data.
- `setPendingCount(...)` is not “setting the number of threads to use”; it is part of the completion protocol.

A common mistake is setting pending equal to the number of children and having each child call `tryComplete()` once: the node may sit at 0 without **ever running `onCompletion`** because the final triggering signal is missing.

## 3. Two valid counting patterns: self-signal and child-only

Suppose a parent creates exactly two children.

### Pattern A — Parent also signals completion for itself

~~~text
Parent: pending = 2

Parent finishes preparing/forking children -> parent.tryComplete()
Child 1 finishes -> child.tryComplete() -> signals parent
Child 2 finishes -> child.tryComplete() -> signals parent

Total three signals: parent + child1 + child2.
pending=2 -> 1 -> 0 -> parent's callback -> propagation.
~~~

This pattern is common when the parent has its own work or creates children dynamically. **You must increment pending before a child can complete**.

### Pattern B — Only the two children signal completion

~~~text
Parent: pending = 1

Parent creates child1, child2, does not call parent.tryComplete().
Child 1 -> signals parent: pending 1 -> 0
Child 2 -> signals parent: pending 0 -> onCompletion/propagate

Total two signals. No self-signal.
~~~

This is the pattern used by the sum-tree examples in this article: the parent delegates work to two children, and the parent itself does not send a third signal. If you replace `pending=1` with `pending=2` without adding `parent.tryComplete()`, the root may **never complete**.

### 3.1 When a child finishes before the parent's compute returns

`CountedCompleter` does not require the parent to wait for children at the end of `compute()`. A forked child may finish either before or after the parent returns. The protocol remains correct if:

1. You register pending/child references **before forking** so there is no race with completion.
2. Each child completion path sends one signal the exact expected number of times.
3. The callback reads results only when the signals fully represent the data to be merged.
4. You do not call `quietlyCompleteRoot()` early while children still have side effects that must be awaited.

## 4. tryComplete(): callback then climbing the completer chain

Consider the tree:

~~~text
                       Root
                      /    \
                     A      B
                   /  \    /  \
                  A1  A2  B1  B2
~~~

Each leaf has pending 0. Each internal node has pending 1 because only two children send signals.

If A1 finishes before A2:

~~~text
A1.tryComplete()
  A1.pending=0 -> A1.onCompletion(A1)
  -> A.tryComplete(): A.pending=1 -> decrements to 0; stops

A2.tryComplete()
  A2.pending=0 -> A2.onCompletion(A2)
  -> A.tryComplete(): A.pending=0 -> A.onCompletion(A2)
  -> Root.tryComplete(): ...
~~~

Branch B behaves similarly. Once both A and B report completion to Root, Root's callback executes once and Root is marked done.

Key points:

- **The parent does not call `join()` on each child**.
- Which worker executes the parent's callback depends on the last signal path; **do not rely on thread names** to assert that the callback runs on the parent thread.
- The `caller` parameter may be the child that triggered the final step, or `this` in the self-signal pattern. It is not fixed to be the “right child” or the “later-submitted child”.
- A node's callback is triggered **after enough signals arrive**, not necessarily right when the node's `compute()` method returns.

### 4.1 What does the default onCompletion do?

The default implementation of `onCompletion(CountedCompleter<?> caller)` **does nothing**. It is an extension point for application logic, such as merging results from two branches or marking a continuation step.

If the tree does not need callbacks at its nodes, `propagateCompletion()` is usually simpler and avoids unnecessary callback method invocation overhead.

## 5. Java 17+ Example: Sum tree with onCompletion merging results

The following example decomposes an 8-element array. Each leaf computes the sum of a small slice; each internal node sums its two children **inside `onCompletion`**. No shared `AtomicLong` is needed for all workers to add into.

Create `CountedCompleterSumDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterSumDemo {
    private static final class SumTask extends CountedCompleter<Long> {
        private static final int THRESHOLD = 2;
        private final long[] values;
        private final int start, end;
        private final AtomicInteger callbackCount;
        private SumTask left, right;
        private long result;

        SumTask(CountedCompleter<?> parent, long[] values, int start,
                int end, AtomicInteger callbackCount) {
            super(parent);
            this.values = values;
            this.start = start;
            this.end = end;
            this.callbackCount = callbackCount;
        }

        @Override public void compute() {
            if (end - start <= THRESHOLD) {
                long local = 0;
                for (int i = start; i < end; i++) local += values[i];
                result = local;
                tryComplete();
                return;
            }

            int mid = start + (end - start) / 2;
            left = new SumTask(this, values, start, mid, callbackCount);
            right = new SumTask(this, values, mid, end, callbackCount);
            setPendingCount(1); // Two child signals; last signal completes.
            right.fork();
            left.compute();
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) result = left.result + right.result;
            callbackCount.incrementAndGet();
        }

        @Override public Long getRawResult() { return result; }
    }

    public static void main(String[] args)
            throws InterruptedException {
        long[] values = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger callbacks = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(4);

        try {
            Long sum = pool.invoke(
                    new SumTask(null, values, 0, values.length, callbacks));
            System.out.println("Sum: " + sum);
            System.out.println("onCompletion calls: " + callbacks.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                pool.shutdownNow();
        }
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac CountedCompleterSumDemo.java
java CountedCompleterSumDemo
~~~

Stdout:

~~~text
Sum: 36
onCompletion calls: 7
~~~

**Explanation:**

1. The array has 8 numbers from 1 to 8; the correct sum is **36**.
2. With threshold 2: the tree has **4 leaves** (each handling 2 elements), **2 intermediate internal nodes**, and **1 root** — 7 nodes in total.
3. Each leaf computes its own `result` and calls `tryComplete()`. Since pending is 0 at a leaf, the leaf's callback runs and the signal propagates up to its parent.
4. Each internal node creates two children, **sets pending=1 before forking**, forks the right branch, and computes the left branch directly. The internal node itself does not call `tryComplete` right after spawning, because only the two children signal completion.
5. The first child reporting up decrements the parent's pending from 1→0; the last child arriving when pending is already 0 triggers the parent's `onCompletion`.
6. Inside the parent's callback, `left.result` and `right.result` have already been computed by the subtrees according to the protocol; the parent writes `result = left.result + right.result`.
7. `getRawResult()` returns the task's `result`. `CountedCompleter<Long>` **does not infer the result** solely from the generic return type; we must override it so `pool.invoke(root)` reads the stored value.
8. Each node invokes `onCompletion` exactly once: 7 callbacks. `AtomicInteger` is used only to count callbacks for the demo, not to sum the data itself, avoiding unnecessary contention.

The sum and callback count are **deterministic per the tree**, whereas which worker runs a callback or the print order if printed inside callbacks is **non-deterministic**; thus the demo prints only after `pool.invoke(root)` finishes.

### 5.1 Why can child results be read safely inside the callback?

Per the `CountedCompleter` contract, if pending counts and signal flow are used properly, `onCompletion` executes after sufficient completion steps from the children; the Java documentation notes that no additional synchronization is needed **within `onCompletion`** to read fields of the task and its completed children under that protocol.

This condition is **not a license to read arbitrary global variables**: if an external thread concurrently mutates `values`, or if a child signals before actually finishing writing its result, correctness is still broken. Protect input ownership, write the result **before** signaling, and do not let external writers bypass the contract.

## 6. propagateCompletion(): propagating without invoking onCompletion

If callbacks at nodes are **not needed**, use `propagateCompletion()`:

- If the pending count at the node is positive, decrement it once and return.
- If pending is 0, **do not call `onCompletion`**, and continue propagating the signal up to the completer.
- At a root with no completer, marks the root normally done when propagation reaches it.
- Results will **not be merged automatically**. If reduction is needed, another protocol must prepare the results; do not replace `tryComplete` with `propagateCompletion` in the sum example and still expect callbacks to combine child results.

### 6.1 Direct comparison

| Condition at node | `tryComplete()` | `propagateCompletion()` |
| --- | --- | --- |
| Pending > 0 | Decrements once and returns. | Decrements once and returns. |
| Pending = 0 | Calls `onCompletion(caller)` then climbs to completer. | **Skips callback**, climbs to completer immediately. |
| Reaching root | Marks root completed after required callback path. | Marks root completed **without callbacks**. |
| Use when | Parent must merge results, cleanup/continuation once children finish. | Only need to ensure all leaves finish, no per-node logic to run. |
| Consequence if chosen wrongly | Callback may run when unwanted. | Loses aggregation/continuation that depends on the callback. |

## 7. Java 17+ Example: propagateCompletion without invoking callbacks

The example below transforms each element `input[i]` into `output[i] = input[i] + 1`. Write ranges are non-overlapping; **no merge callback is needed**: after the root completes, `main` can sum `output` sequentially.

Create `CountedCompleterPropagateDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterPropagateDemo {
    private static final class MapTask extends CountedCompleter<Void> {
        private static final int THRESHOLD = 2;
        private final int[] input, output;
        private final int start, end;
        private final AtomicInteger callbacks;

        MapTask(CountedCompleter<?> parent, int[] input, int[] output,
                int start, int end, AtomicInteger callbacks) {
            super(parent);
            this.input = input;
            this.output = output;
            this.start = start;
            this.end = end;
            this.callbacks = callbacks;
        }

        @Override public void compute() {
            if (end - start <= THRESHOLD) {
                for (int i = start; i < end; i++)
                    output[i] = input[i] + 1;
                propagateCompletion();
                return;
            }

            int mid = start + (end - start) / 2;
            setPendingCount(1);
            new MapTask(this, input, output, mid, end, callbacks).fork();
            new MapTask(this, input, output, start, mid, callbacks).compute();
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {
        int[] input = {1, 2, 3, 4, 5, 6, 7, 8};
        int[] output = new int[input.length];
        AtomicInteger callbacks = new AtomicInteger();
        ForkJoinPool pool = new ForkJoinPool(3);

        try {
            pool.invoke(new MapTask(
                    null, input, output, 0, input.length, callbacks));
            int sum = 0;
            for (int value : output) sum += value;

            System.out.println("Transformed sum: " + sum);
            System.out.println("onCompletion calls: " + callbacks.get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                pool.shutdownNow();
        }
    }
}
~~~

Compile/run:

~~~bash
javac CountedCompleterPropagateDemo.java
java CountedCompleterPropagateDemo
~~~

Stdout:

~~~text
Transformed sum: 44
onCompletion calls: 0
~~~

**Analysis:**

- The output is `{2,3,4,5,6,7,8,9}` and the sum is 44.
- Each leaf writes its own output slice and calls `propagateCompletion()`; the completion path through internal nodes does not execute callbacks.
- Overriding `onCompletion` intentionally increments a counter if ever called, verifying that **the callback count is 0**.
- The root is still marked done once all signals from children have properly propagated to the root, so `main` safely reads `output` after `pool.invoke`.
- You must use the correct pending count and non-overlapping ranges; `propagateCompletion` does not automatically make data-race writes safe.

This is an example of a **completion barrier via `CountedCompleter`**, with no need to merge at each node. If the next step requires tree-wise merging, use `tryComplete` with an appropriate callback or another reduction mechanism.

## 8. onCompletion(caller): callback body and caller parameter

`onCompletion(CountedCompleter<?> caller)` is invoked when the **normal completion** path of `tryComplete()` reaches a node whose pending count is already 0. By default this method does nothing; override it when you need to perform a step after enough signals arrive from children.

Common cases:

- **Leaf:** pending is 0; the leaf calls `tryComplete()` so `onCompletion(leaf)` has `caller == this`.
- **Parent triggered by the last child:** `caller` may be the child that triggered the chain, typically `caller != this`.
- **Parent sending the final self-signal:** `caller == this` can happen if the parent calls `tryComplete()` when pending has already reached 0.

Therefore, never **assume `caller` is always a child** or always `this`. If you use `caller` to retrieve a result, understand the protocol clearly and handle both cases.

### 8.1 Result-merging callback

In `CountedCompleterSumDemo`:

~~~java
@Override public void onCompletion(CountedCompleter<?> caller) {
    if (left != null) result = left.result + right.result;
    callbackCount.incrementAndGet();
}
~~~

This is a snippet belonging to the defined class. A node with `left == null` is a leaf and already has `result` from `compute`; the callback does not need to change `result`. A node with two children merges after **both subtrees have sent their required signals**.

If the callback has side effects such as sending network messages or calling uncontrolled code:

- It can slow down the root's critical completion path.
- It can throw an exception and turn the completion path into abnormal completion.
- There is no guarantee the callback runs on a fixed worker.
- If the callback updates global shared state, it still requires normal synchronization.
- If aggregation order matters, you must store child positions and combine them in business order; the final `caller` does not determine data order.

### 8.2 “Once per node” depends on the protocol

Documentation describes the callback as firing once when pending counts are used properly. However, if code calls `tryComplete()` extra times, misuses `complete()`, or reuses a task with an invalid lifecycle, you cannot preserve a “always once” guarantee on a broken protocol.

**Define the number of signals, who sends them, and when** before implementing the callback.

## 9. Java 17+ Example: self-signal and one-child pattern

A parent has one child and also sends a signal itself upon finishing the child-creation step. In that case, **two total signals** are needed, so pending is initialized to 1.

Create `CountedCompleterSelfSignalDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CountedCompleterSelfSignalDemo {
    private static final class Root extends CountedCompleter<Void> {
        private final AtomicInteger callbacks = new AtomicInteger();

        Root() { super(null, 1); }

        @Override public void compute() {
            new Child(this).fork();
            tryComplete(); // Root's own work is complete.
        }

        @Override public void onCompletion(CountedCompleter<?> caller) {
            callbacks.incrementAndGet();
        }
    }

    private static final class Child extends CountedCompleter<Void> {
        Child(CountedCompleter<?> parent) { super(parent); }
        @Override public void compute() { tryComplete(); }
    }

    public static void main(String[] args)
            throws InterruptedException {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            Root root = new Root();
            pool.invoke(root);
            System.out.println("Root callbacks: " + root.callbacks.get());
            System.out.println("Root done: " + root.isDone());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS))
                pool.shutdownNow();
        }
    }
}
~~~

Commands:

~~~bash
javac CountedCompleterSelfSignalDemo.java
java CountedCompleterSelfSignalDemo
~~~

Stdout:

~~~text
Root callbacks: 1
Root done: true
~~~

**Explanation:**

- Root needs two signals: from **Root.compute()** and from **Child.compute()**. Pending=1.
- If `Root.tryComplete` runs first, it decrements pending 1→0; when `Child.tryComplete` reaches Root, pending 0 triggers the root callback.
- If Child finishes first, the signal from Child decrements pending 1→0; `Root.tryComplete` arriving later triggers the root callback.
- In both schedules, the root callback runs **exactly once**; however, **caller** may be either Root or Child. That is why the demo does not print the caller/thread name and only prints the counter after `invoke()`.
- Root does not call `join()` on Child, yet it is still not marked done before receiving both signals.

This minimal example illustrates why the pending count formula depends on the number of signals, not just the number of children.

## 10. Comparing the three APIs step by step

For a node `N` with initial pending count 1:

~~~text
Initially: N.pending=1

Signal 1: childA.tryComplete()/propagateCompletion()
          -> reaches N, sees 1, decrements to 0, return

Signal 2: childB.tryComplete()
          -> reaches N, sees 0
          -> N.onCompletion(childB)
          -> continues to N.getCompleter()

Signal 2': childB.propagateCompletion()
          -> reaches N, sees 0
          -> DOES NOT call N.onCompletion
          -> continues to N.getCompleter()
~~~

Use this example to remember:

- `tryComplete()` is **count + callback + propagation**.
- `propagateCompletion()` is **count + propagation**, skipping the callback.
- `onCompletion(...)` **is not a signal-sending method**. It is a hook **invoked by `tryComplete`/`complete` per the contract**.

If a developer calls `onCompletion(caller)` directly from `compute`, that is just a normal Java method call; it does not decrement pending or mark the root done. Never replace `tryComplete()` with a direct callback call.

## 11. Completion propagation is not every child's completion status

An important nuance in the `CountedCompleter` Javadoc: a task with `getCompleter() != null` is typically an **internal helper**, and the `isDone()` state of that helper itself **does not necessarily reflect when it sent its completion signal**. Passing a signal up to the parent does not necessarily mark the individual helper task as completed in the way `RecursiveTask.join()` is usually used.

Therefore:

- Use `invoke(root)` / `join(root)` to wait for **the entire completion protocol of the root**.
- **Do not by default** call `child.join()` on every `CountedCompleter` helper and expect them all to have standalone task completion status.
- `child.getPendingCount()==0` is not a `Future` completion flag.
- The root completes normally only when the completion path reaches it according to the protocol, not because the parent's `compute` returns.
- If you manually use `complete(T)`/`quietlyCompleteRoot()` to mark completion early, you may cause the root to be done while some children still have side effects running; understand the algorithm's guarantees.

The right mental model is a **graph of completion signals**, not every parent sitting at a `join()` line waiting for a child.

## 12. complete(T), quietlyCompleteRoot(), and why they differ from tryComplete

Beyond the three core APIs, `CountedCompleter` has several stronger methods:

### 12.1 complete(T rawResult)

In Java 17, `complete(rawResult)`:

1. Calls `setRawResult(rawResult)`;
2. Calls `onCompletion(this)`;
3. Marks **the current task** completed;
4. Triggers `tryComplete()` on its completer if one exists.

It performs **unconditional completion**: it does not wait for the pending count to reach 0 and **does not adjust the pending count** of the task being completed. Therefore, do not use `complete(result)` to replace a normal “child finished” signal if the parent truly needs all children.

With `CountedCompleter<T>`, the default `setRawResult(T)` may **not store any useful value**; for `get()/join()` to return `T`, the subclass must implement appropriate result management, typically overriding `getRawResult()` and/or `setRawResult()`.

### 12.2 quietlyCompleteRoot()

`quietlyCompleteRoot()` marks the **root** complete without following the normal callback path. It is useful for **first-match search** where one branch finds an answer and wants the root to return early.

However, once the root has completed early:

- Other workers/children may **still be running**.
- Root completion does not automatically cancel/interrupt all children.
- Do not use it if the application requires all child side effects to finish before returning.
- To cancel remaining branches in a controlled way, you can publish a result flag via `AtomicReference` and have children check it at safe points, or use an appropriate cancellation policy.

`quietlyCompleteRoot()` is not a fix for a miscalculated pending count; it will **mask bugs** without proving all tasks have finished.

## 13. onExceptionalCompletion: exceptions follow a different path

`onCompletion(...)` is the hook for **normal completion**. If `compute()` throws an exception or a task is completed abnormally via `completeExceptionally(Throwable)`, `CountedCompleter` has a separate **exceptional completion** path.

Hook:

~~~java
@Override
public boolean onExceptionalCompletion(
        Throwable error, CountedCompleter<?> caller) {
    logFailure(error);
    return true; // Allow the error to propagate up to the completer per contract.
}
~~~

This is an **illustrative snippet**; it assumes `logFailure` exists, and must be placed inside a `CountedCompleter` subclass. The default implementation of `onExceptionalCompletion` returns `true` without doing anything else, generally allowing the error to propagate to the parent if the parent has not yet completed.

Points to note:

- Errors can **travel up the completer chain** without running remaining normal callbacks.
- `false` is a decision not to continue exception propagation per the contract; it does **not** mean automatic rollback or result substitution.
- One canceled child does not by default cancel all remaining children.
- Do not catch `Throwable` and silently call `tryComplete()` as if the task succeeded, unless the contract defines a **valid fallback result** and preserves invariants.
- If the `onCompletion` callback itself throws an exception, it also complicates the completion path; callbacks should be small, clear, and avoid external side effects that are hard to roll back.

When you want to retrieve failures from the root, use `pool.invoke(root)` (which throws an appropriate unchecked abnormal completion) or `Future.get()` under the checked `ExecutionException` contract. Do not treat a helper's `compute()` returning as proof of root success.

## 14. Proper ordering: register children before forking

A subtle race occurs when you create and fork a child immediately, **and only then increment pending**:

~~~java
new Child(this).fork();
addToPendingCount(1); // Risk: Child may complete before registration.
~~~

This is an **incorrect snippet**. If the child finishes very quickly, it can call `tryComplete()`, propagate to the parent, and see the count not yet incremented. The parent may run its callback/propagate too early while the parent is still about to register more work.

Correct pattern:

~~~java
addToPendingCount(1);
new Child(this).fork();
~~~

This is an illustrative snippet for the case where **the parent has one additional signal matching the algorithm's structure**, not a mindless “always add 1 per child” rule. You must calculate from the **total number of signals** per the pattern, not increment arbitrarily.

For a parent with two children and **no self-signal**, the verified example sets `setPendingCount(1)` before forking the two children. With a self-signal plus N children, a common model sets pending=N and has the self and N children each signal once.

### 14.1 When spawning children dynamically

When the number of children is not known in advance:

1. The parent owns child registration.
2. Before forking each new child, increment the pending count accordingly **per a protocol with a self-signal or final trigger**.
3. Once no more children will be created, the parent sends its self-signal via `tryComplete()` if the model requires it.
4. Each completed child calls `tryComplete`/`propagateCompletion` exactly once.
5. Do not register new children **after the root may already have been marked complete**, unless the algorithm has a clear dedicated protocol for it.

A late-registration race can trigger the callback before all work is known, resulting in missing data. `CountedCompleter` does not manage a list of children to rescue this situation.

## 15. Result aggregation, side effects, and ownership

In the array-sum problem, each node writes its own `result`; the parent's callback reads child results **after enough signals arrive**. This is a sound pattern because each node has a single owner writing its result, and the parent reads only after completion.

Define ownership clearly:

| Data | Who writes? | When is reading safe? |
| --- | --- | --- |
| Input array immutable during execution | Caller prepares before `invoke`. | Leaves can read in parallel per publication contract. |
| `leaf.result` | The leaf itself upon finishing. | Parent callback after the leaf completes per signal protocol. |
| `parent.result` | Parent inside `onCompletion`. | Grandparent callback after parent has signaled completion. |
| Global counter metrics | Multiple workers may write. | Use `AtomicInteger`/`LongAdder` per consistency requirements. |
| Partitioned output array | Leaf owns non-overlapping `[start,end)`. | Caller reads after root completes. |
| Shared mutable List/Map | Potentially multiple writers. | Requires concurrent structure, lock, or dedicated ownership. |

### 15.1 Do not let callback order dictate completion order

`onCompletion(caller)` may be executed by different workers depending on which branch arrives last. If the combine operation is **non-commutative** (for example, string concatenation that must preserve order, or merging an ordered tree), you must store explicit left/right slots and combine **left then right**, not based on “which child called the callback last”.

In `SumTask`, integer addition is commutative so left/right order does not affect the outcome. For concatenation or event-stream operations, order can be part of correctness.

### 15.2 Avoid slow I/O inside callbacks unless necessary

An `onCompletion` calling a remote API can hold the root's critical path for a long time, block workers, and if it throws an exception, disrupt the completion chain. Keep callbacks to small, pure aggregation, and place I/O after the root completes or in an appropriate executor/layer. If a callback must block on a `ForkJoinPool`, consider `managedBlock` and deadlines as needed; it neither fixes deadlocks nor rolls back state automatically.

## 16. Who can the callback caller be? Why not assert thread names?

With the self-signal pattern, two schedules are valid:

~~~text
Schedule A:
Root.tryComplete()  -> pending 1→0
Child.tryComplete() -> Root.onCompletion(caller=Child)

Schedule B:
Child.tryComplete() -> pending 1→0
Root.tryComplete()  -> Root.onCompletion(caller=Root)
~~~

Both schedules produce the same business result. Therefore:

- `caller == this` is **not** always true.
- `caller != this` is **not** always true.
- The callback is not guaranteed to run on the thread that created the parent object.
- Log sequence numbers inside callbacks are not invariants when workers execute in parallel.

Write callbacks around **data/node relationships** and the aggregation contract; do not depend on worker names, CPU, or nanoseconds.

## 17. Why can internal task isDone be misleading?

A `CountedCompleter` acting as a helper with a completer is often just a link in signal processing. Per the Java 17 Javadoc, **the completion status of the helper itself** may not change unless it is completed via `complete`, `cancel`, `completeExceptionally`, or experiences exceptional completion through `compute` on its own path.

Therefore:

~~~java
CountedCompleter<?> child = ...; // Helper with a completer.
child.fork();
child.join(); // Not the standard CountedCompleter tree-waiting pattern.
~~~

This is an **anti-pattern snippet**, not standalone runnable code. If the child only calls `tryComplete()` to signal its parent, `join()` on the child must not be used as a substitute measure for the root having received all completions. Instead:

~~~java
CountedCompleter<?> root = ...; // Root with proper completion protocol.
pool.invoke(root);
~~~

This snippet assumes a valid root and pool, with appropriate exception handling. Callers should wait on the **root**, while helpers participate in signal propagation by design.

A similar issue arises when using `getPendingCount() == 0` as a stopping condition: pending 0 still does not prove the completion callback has run or that the root has been marked done.

## 18. Cancellation, progress, and deadlocks

`CountedCompleter` reduces the need to wait on every child with `join`, but does not guarantee every program is free of deadlocks/starvation.

Common risks:

- **Missing a signal:** a leaf returns and forgets `tryComplete/propagateCompletion`; the root keeps waiting.
- **Extra signal:** calling twice or double-completing causes callbacks to run too early or duplicate.
- **Pending registered after fork:** a fast child finishes before the parent increments the count.
- **Leaf blocks indefinitely:** completion cannot advance even with a correct counter.
- **Lock deadlock:** parent/child holds a monitor and waits for code that needs that monitor.
- **Unfinished side effects:** a child signals before data writes complete.
- **Isolated cancellation:** canceling a helper does not automatically complete/cancel the entire root and other helpers.
- **Swallowed errors:** catching an exception and reporting normal completion with invalid state.
- **Task tree too deep/small:** fork overhead, GC, and work stealing can outweigh useful work.

### 18.1 Root progress does not mean all resources are released

An algorithm may **early-complete** the root after finding the first result via `quietlyCompleteRoot()`. Other branches must **check a completion/cancellation flag themselves** if they are to stop quickly. There must be an executor/cleanup management policy. `root.isDone()` in that case does not prove all auxiliary tasks have stopped and all resources are closed.

### 18.2 Interruption and deadlines

`ForkJoinTask.join()` does not throw checked `InterruptedException` under its normal contract. If the program needs a deadline, consider `get(timeout, unit)` at an appropriate entrypoint, combined with **cooperative cancellation** of tasks. An expired timed `get` only limits how long the caller waits; it does not stop the whole tree. Avoid trying to "fix" a deadlock by abruptly stopping a thread holding a lock.

## 19. Testing and observing completion behavior

Good tests do not infer correctness from non-deterministic log order. Instead:

1. **Correct result:** the array-sum problem yields sum=36, the transformed output yields sum=44.
2. **Callback count:** a 7-node tree following the protocol invokes 7 `onCompletion` calls with `tryComplete`; using `propagateCompletion` yields 0.
3. **Self-signal race:** test both completion orders (parent vs. child) using latches, verifying the root callback runs exactly once.
4. **Zero-length input:** define leaf behavior clearly; do not fork infinitely.
5. **Threshold:** non-overlapping boundary indices, tree nodes have a base case.
6. **Failure injection:** a child throws an exception; the root must complete abnormally or use a controlled fallback, not wait forever.
7. **Timeout:** tests have appropriate deadlines so non-daemon threads do not hang CI.
8. **Callback side effects:** if a callback writes shared mutable state, verify thread safety and idempotency.
9. **Duplicate/missing signals:** review the static protocol and add metrics to detect pending counts not reaching the expected state.
10. **Multiple JDK/CPU environments:** results must be correct regardless of worker ordering.

### 19.1 Distinguishing callback count from steal count

`ForkJoinPool.getStealCount()` estimates the number of work-stealing events and has no fixed arithmetic relationship with the `onCompletion()` callback count. A task tree can run on a single worker with zero steals and still execute every callback. Do not assert that steals must occur to prove `CountedCompleter` is working.

### 19.2 Do not test completion with sleep

~~~java
root.fork();
Thread.sleep(100);
System.out.println(root.isDone());
~~~

This is an **anti-pattern snippet**, assuming code handles `InterruptedException`. `sleep` does not guarantee the root has completed; tests can be flaky. Use `pool.invoke(root)`, `root.join()` (for the root), or `get(timeout)` and assert the result/callbacks.

## 20. Choosing between tryComplete and propagateCompletion

| Question | If “Yes”, consider |
| --- | --- |
| Must the parent merge child results **once enough signals arrive**? | `tryComplete` + `onCompletion`. |
| Only need the root to know the whole tree is done, with outputs written to disjoint regions? | `propagateCompletion`, no callback. |
| Does the algorithm find a result early without waiting for other branches? | `quietlyCompleteRoot`/early-completion pattern with its own stop and cleanup protocol. |
| Must the root return `T` from `invoke()`? | Override `getRawResult` and manage the result field safely. |
| Does the parent create a dynamic number of children? | `addToPendingCount` **before forking**, plus an appropriate self-signal/final trigger. |
| Can a child fail? | Design `onExceptionalCompletion` and root failure semantics. |
| Does the parent need to identify which child finished? | Store child references/results; pending count does **not** store identity. |

### 20.1 When not to use CountedCompleter?

If the problem is just a simple binary-tree array sum, `RecursiveTask<Long>` with `left.fork(); right.compute(); left.join();` may be **more readable and less error-prone**. `CountedCompleter` is worthwhile when you genuinely need **multi-signal-based continuations/callbacks**, wide fan-out task trees, or reduced direct joins—not just because the API sounds advanced.

If you only need to wait for N independent tasks, `CountDownLatch` or `CompletionService` may also be simpler depending on whether you need values, errors, or partial results. Do not build a completer task tree just to replace a very simple event counter.

## 21. Common pitfalls

| Pitfall | Consequence | How to fix |
| --- | --- | --- |
| Setting pending=2 for two children without a parent self-signal. | Both children only decrement, missing the callback trigger. | Pending=1 for child-only 2 signals, or add a proper self-signal. |
| Calling `tryComplete` in a leaf before writing `result`. | Parent may read an unready result. | Write all data before signaling. |
| Forking a child before incrementing pending. | A fast child causes the parent to complete early. | Register pending before forking. |
| Replacing `tryComplete` with `propagateCompletion` in a reduction tree. | No callback remains to combine child results. | Keep `tryComplete` or move result aggregation to another protocol. |
| Assuming `onCompletion` runs only on the parent thread. | Races / wrong scheduling assumptions. | Make callbacks thread-safe, independent of worker identity. |
| Treating the last `caller` as the “correct order” of results. | Non-commutative merges produce wrong order. | Store left/right positions and use business order. |
| Calling `child.join()` on an internal helper. | Helper may not be marked done like a root task. | Wait on the root with a proper completion protocol. |
| Using `pending==0` as a completed flag. | Count is 0 but final signal/callback has not run yet. | Rely on root completion via `invoke`/`join`/`get`. |
| Ignoring exceptional completion. | Root may report errors or hang in hard-to-diagnose ways. | Define a failure contract and `onExceptionalCompletion` if needed. |
| Calling `complete(T)` to bypass pending because “one child is ready”. | Root/task completes too early, missing data. | Use normal signals or an explicit early-completion contract. |
| `onCompletion` performs slow remote I/O / long blocking. | Holds critical path, blocks workers. | Keep callbacks light; do post-processing outside the task tree. |
| Same child sends a signal twice. | Extra completion, premature or duplicate callbacks. | Each completion path signals exactly once. |
| Incrementing pending after the final signal could have passed. | Races with callback / early root completion. | Clear ownership for registration and state machine. |
| Assuming work stealing will occur because `CountedCompleter` is used. | False assumption; scheduling still depends on workload. | Measure with pool metrics if needed; do not assert steal count. |
| Not shutting down a self-created pool. | Hard-to-manage resources/lifecycle. | Use `try/finally`, `shutdown`/`awaitTermination` with timeout. |

## 22. Checklist for reviewing a CountedCompleter class

- [ ] Root/completer graph is acyclic and links are set up properly.
- [ ] Each node defines **how many signals will arrive** (self + child).
- [ ] Pending count is set/incremented **before** children can finish.
- [ ] For N signals in a fixed pattern, pending=N−1 or an equivalent proven protocol.
- [ ] Every normal completion path sends exactly one signal.
- [ ] Leaves write results/state safely **before** `tryComplete/propagateCompletion`.
- [ ] Callbacks do not rely on caller identity or worker thread beyond what the contract guarantees.
- [ ] If aggregation uses callbacks, leaf/internal nodes are properly distinguished and result fields are ready.
- [ ] If callbacks are skipped, `propagateCompletion` truly fits the business logic.
- [ ] Result-bearing tasks override `getRawResult()` appropriately.
- [ ] Errors/cancellations/timeouts have exit paths to prevent the root from waiting forever.
- [ ] `child.isDone()` is not confused with root completion.
- [ ] `complete/quietlyCompleteRoot` are not called to mask pending count bugs.
- [ ] No I/O or lock waiting inside callbacks that could cause deadlock or starvation.
- [ ] Pool lifecycle has an owner; the common pool is not shut down.
- [ ] Tested with small/large inputs, multiple schedules, and failure injection.

## 23. Self-check questions

**1.** What does `tryComplete()` do when it sees pending=3?  
**Answer:** Decrements pending to 2 and returns; does not call `onCompletion`.

**2.** What does `tryComplete()` do when it sees pending=0?  
**Answer:** Calls `onCompletion(caller)`, then continues trying completion on the completer; at the root, marks it done per contract.

**3.** Two children send exactly two signals, and the parent does not self-signal. What is the initial pending count?  
**Answer:** 1, because the first signal decrements 1→0 and the second triggers the callback.

**4.** A parent has two children **and** calls `tryComplete` itself after spawning them. What is the initial pending count?  
**Answer:** Under the self-signal pattern, 2 for a total of three signals; must be registered properly before forking.

**5.** Does a pending count of 0 mean the root is already done?  
**Answer:** Not necessarily. Another signal at pending 0 is needed to trigger the callback / mark the root completed.

**6.** How does `propagateCompletion` differ from `tryComplete`?  
**Answer:** Both record counts and propagate, but `propagateCompletion` skips `onCompletion` along the entire path.

**7.** If you need to merge child results in `onCompletion`, which method should you choose?  
**Answer:** `tryComplete` with the proper pending count and a callback accessing ready child results.

**8.** Why is forking a child before `addToPendingCount` dangerous?  
**Answer:** The child may finish and trigger the parent before the parent registers pending, leading to premature completion.

**9.** Is the `caller` of `onCompletion` always the right child?  
**Answer:** No. It may be `this` or the last child; there is no ordering guarantee.

**10.** For a `CountedCompleter` helper task with a completer, is `isDone()` always true after signaling its parent?  
**Answer:** No; the helper's task status and signaling the parent are two different things.

**11.** Why must `getRawResult()` be overridden in `CountedCompleter<Long>`?  
**Answer:** To provide the computed/stored result field to `invoke/join/get`; the generic type does not generate a value automatically.

**12.** Will changing every `tryComplete` to `propagateCompletion` in the sum example print 36?  
**Answer:** No guarantee: the result-merging callbacks will not run, so internal results will not be computed.

**13.** Does `complete(result)` respect the pending count?  
**Answer:** No. It is unconditional completion, used when you genuinely want to bypass normal pending counts per contract.

**14.** Does `quietlyCompleteRoot()` guarantee all children have stopped?  
**Answer:** No; it can mark the root complete early in a search pattern while other children are still running.

**15.** When `compute` throws an exception, does `onCompletion` run like on the normal path?  
**Answer:** No. There is a separate exceptional completion path and `onExceptionalCompletion` hook.

**16.** Does using `CountedCompleter` make any shared mutable map thread-safe?  
**Answer:** No. Completion signaling does not replace mutual exclusion or invariant protocols.

**17.** If two leaves finish nearly simultaneously, can you predict which worker runs the callback?  
**Answer:** No. The callback is triggered by the last signal path and runtime scheduling.

**18.** Why is using `propagateCompletion` reasonable in the transform example?  
**Answer:** Each leaf writes a disjoint output slice with no per-internal-node merging; the root only needs to know all are done.

**19.** What bug causes the root to wait forever even though all leaves have finished?  
**Answer:** For example, pending set too high, a leaf forgetting to signal, or a completion path failing to propagate up to the parent.

**20.** When should you use `RecursiveTask` instead of `CountedCompleter`?  
**Answer:** When the join/reduce tree is simple, fork/compute/join logic is clearer, and no special continuation is needed.

**Key takeaway:** `CountedCompleter` uses **pending signals and a completer chain** to coordinate completion. `tryComplete()` decrements pending or (when 0) invokes `onCompletion` and climbs up; `propagateCompletion()` climbs up while skipping callbacks; `onCompletion(caller)` is where merging/continuations happen after enough signals arrive. For a correct program, accurately count **self + child signals**, register before forking, write results before signaling, and rely only on **root completion** to confirm the entire tree per the contract.

## References

- [CountedCompleter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): official documentation on pending count, `tryComplete`, `propagateCompletion`, `onCompletion`, results, and callbacks.
- [ForkJoinTask — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): lifecycle and `fork/invoke/join/get` methods.
- [ForkJoinPool — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): scheduling and work stealing.