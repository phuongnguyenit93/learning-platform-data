# Completer Relationship, Pending Count, and Completion Tree of CountedCompleter in Java

## 1. What Problem Does CountedCompleter Solve?

In Fork/Join, a computation can be divided into many smaller units of work. With `RecursiveTask` or `RecursiveAction`, the common approach is to create subtasks, `fork()` part of them, and then `join()` to wait for results. For problems with many independent branches, uneven branch processing lengths, or the need to aggregate results once all branches complete, **CountedCompleter** allows building a **completion notification tree** where workers do not necessarily have to block with `join()` at each parent node.

`java.util.concurrent.CountedCompleter<T>` is an abstract class extending `ForkJoinTask<T>`, introduced in Java 8. Each task can hold:

- A **completer** reference: typically the parent task that will receive completion notifications from the current task.
- An integer **pending count**: the number of completion signals that still need to be consumed before the task is eligible to perform its completion action.
- A `compute()` method: performs the work and may create additional child tasks.
- An `onCompletion(CountedCompleter<?> caller)` callback: performs finalization work, such as merging branch results.
- A `tryComplete()` mechanism: decrements pending when positive, or triggers the completion callback and traverses up the completer chain when pending is already 0.

**Most common misconception:** `pending count` is **not** a list of child tasks automatically tracked by the JVM. You must **manually set the exact number of notifications**, order the timing of forks, and ensure all branches participating in the protocol call `tryComplete()` or an appropriate propagation mechanism.

This lesson is limited to **Java Fork/Join and concurrency in general**, using JDK 17+ APIs. It does not cover how other frameworks wrap or use executors.

### Learning Outcomes

After this lesson, you should be able to:

1. Distinguish **completer**, **pending count**, **parent/child computation**, and **ForkJoinTask completion status**.
2. Draw and explain the completion tree, knowing which signal decrements pending and which signal actually triggers `onCompletion()`.
3. Use `setPendingCount`, `addToPendingCount`, and `tryComplete` in the right order, avoiding premature completion or hanging forever.
4. Build runnable Java 17+ programs including a task tree, result aggregation, and a callback-free propagation form.
5. Know the differences between `tryComplete()`, `propagateCompletion()`, `complete(T)`, `quietlyCompleteRoot()`, and `firstComplete()/nextComplete()`.
6. Understand exception handling, cancellation, memory visibility, liveness limits, and cases where a simpler `RecursiveTask` should be chosen.

## 2. Basic Structure of CountedCompleter

### 2.1. Constructors

~~~java
// Signature illustrating the API; not a standalone program.
protected CountedCompleter();
protected CountedCompleter(CountedCompleter<?> completer);
protected CountedCompleter(
    CountedCompleter<?> completer,
    int initialPendingCount
);
~~~

- The no-arg constructor creates a task without a completer, with initial pending **0**.
- The constructor accepting `completer` creates a link to another CountedCompleter, with initial pending **0**.
- The three-argument constructor allows intentionally setting the initial pending count.
- `getCompleter()` returns the completer link established in the constructor.
- `getRoot()` follows the completer chain to obtain the root of the completion chain.
- A root task has `getCompleter() == null`; it can be `invoke()`d or submitted to a `ForkJoinPool`.

### 2.2. Compute Does Not Mean Complete

`CountedCompleter` requires subclasses to override:

~~~java
// Structural pattern in a subclass; not a standalone program.
@Override
public void compute() {
    performLocalWork();
    tryComplete();
}
~~~

`compute()` only describes the main computation. A task is **not necessarily marked completed just because `compute()` returns**. Completion depends on the CountedCompleter protocol; typically `tryComplete()` must be called at the end.

Why is it designed this way? A parent can fork children and finish its *local* work very quickly. However, the parent should only announce completion once the completion signals from the remaining work have been properly processed.

In `RecursiveTask`, developers often write `left.fork(); right.compute(); left.join();`. In `CountedCompleter`, the wiring after branches finish is expressed via **pending count + completer chain**, without needing to block the parent at `join()` at every level.

### 2.3. Root, Intermediate Nodes, and Leaves

~~~text
Root  (completer = null)
 |
 +-- Branch A (completer = Root)
 |      |
 |      +-- Leaf A1 (completer = Branch A)
 |      +-- Leaf A2 (completer = Branch A)
 |
 +-- Branch B (completer = Root)
        |
        +-- Leaf B1 (completer = Branch B)
        +-- Leaf B2 (completer = Branch B)
~~~

In this diagram, the **completer tree** is the tree of **completion** relationships. It often mirrors the algorithm's divide-and-conquer tree, though it does not have to match every method call relationship in the program.

For example, a task can **directly call `compute()` of one branch** to reduce fork overhead, while that branch still has the parent task as its completer. The "which task runs on which thread" relationship is distinct from the completer link.

## 3. What Does Pending Count Actually Count?

### 3.1. Not the Number of Running Tasks

A helpful way to understand it: pending count is the number of times `tryComplete()` observes a **non-zero** value and must decrement it **before** a subsequent call observes 0 to trigger completion of the node.

Suppose Root's pending count is set to **2**:

~~~text
Root.pending = 2

1st tryComplete arriving at Root:
    sees pending = 2 -> decrements to 1; does not call onCompletion

2nd tryComplete arriving at Root:
    sees pending = 1 -> decrements to 0; does not call onCompletion

3rd tryComplete arriving at Root:
    sees pending = 0 -> calls Root.onCompletion(caller)
                       -> if Root has no completer:
                          marks Root completed
~~~

**Watch out for "off-by-one":** A pending count of 2 in this mechanism corresponds to **two decrements and one call at state 0** to trigger completion. It does not simply mean "once two children finish, everything is automatically done" if you have not accounted for the parent's own `tryComplete()` call.

This is why the most readable pattern when **N children are forked** is usually:

~~~java
// Pattern in parent's compute(); not a standalone program.
setPendingCount(N);             // Before forking.
for (int i = 0; i < N; i++) {
    createChild(this, i).fork();
}
tryComplete();                  // Parent contributes one completion arrival.
~~~

When the parent and N children each contribute **one arrival** to the protocol, there are N+1 arrivals in total—enough for the parent to have N decrements from N down to 0 and then one call that triggers the callback. Arrivals can occur in any order and still be accounted for correctly.

### 3.2. Why Set the Count Before Forking?

If the parent forks children first and then calls `setPendingCount`, another worker may process a child quickly and call `tryComplete()` toward the parent **before the parent writes pending**. In that case, the parent could complete prematurely, aggregate incomplete results, or have decrements overwritten by a late `setPendingCount`.

The right order is:

~~~text
Parent:
  1. Create or determine the number of branches to wait for
  2. Set the pending count
  3. Publish children via fork()
  4. Finish the parent's own work
  5. Call tryComplete() according to the counted design
~~~

If branches are created dynamically, `addToPendingCount(delta)` can increment pending atomically. However, **you must increment before enqueuing a branch that can complete**, and you must prove that the number of increments/decrements balances with the actual number of signals.

### 3.3. Atomicity of the Counter

Related methods:

| Method | Purpose |
| --- | --- |
| `getPendingCount()` | Reads the current pending count |
| `setPendingCount(int)` | Sets pending; safe only when the change conforms to the protocol |
| `addToPendingCount(int)` | Atomically adds delta |
| `compareAndSetPendingCount(expected, update)` | CAS on pending count |
| `decrementPendingCountUnlessZero()` | Decrements if currently non-zero; returns the value observed before decrementing per contract |
| `tryComplete()` | Decrements pending if non-zero, or triggers completion if zero |
| `propagateCompletion()` | Similar propagation mechanism, but **does not call onCompletion** |

The counter is updated using JDK atomic primitives, so multiple children can notify concurrently without losing updates to pending itself. Still, **correctness of the notification count remains an algorithmic responsibility**: the JVM does not automatically know how many children you created, which child is "valid", or which results are ready.

Do not take a snapshot `getPendingCount() == 0` and infer that the entire tree has been marked done. Pending may have reached 0 **while the next call to trigger completion has not yet occurred**.

## 4. How Does tryComplete() Traverse the Tree?

### 4.1. Conceptual Model (Not JDK Implementation Code)

~~~java
// PSEUDOCODE, not a standalone Java snippet or JDK source.
void tryCompleteConceptually(CountedCompleter<?> originalCaller) {
    CountedCompleter<?> node = this;
    CountedCompleter<?> caller = originalCaller;

    for (;;) {
        int pending = node.getPendingCount();

        if (pending != 0) {
            if (node.compareAndSetPendingCount(pending, pending - 1)) {
                return;
            }
            continue; // CAS lost; recheck.
        }

        node.onCompletion(caller);
        CountedCompleter<?> parent = node.getCompleter();
        if (parent == null) {
            // Mark root complete per ForkJoinTask mechanism.
            return;
        }

        caller = node;
        node = parent;
    }
}
~~~

This code is only a **conceptual model** of traversal, not a copy of the JDK implementation. Key observations:

1. At a node with non-zero pending: atomic decrement and **stop traversal** there.
2. At a node with zero pending: call `onCompletion(caller)`, then move to the completer.
3. If reaching the root with zero pending: after the callback, the root is marked complete.
4. When multiple branches report completion concurrently, CAS makes each decrement atomic; the callback should only be triggered according to the proven counting protocol.
5. `caller` is the task that caused traversal to reach the current node: it may be the node itself or a descendant that just completed. This parameter helps combine results at each node.

There is no automatic mechanism that "decrements pending once per forked child." The completion calls themselves generate those arrivals.

### 4.2. Illustrative Timeline with Two Children

Using the pattern where parent calls `setPendingCount(2)`, forks C1/C2, and calls `tryComplete()` itself:

~~~text
Root.pending = 2
Root forks C1 and C2

Root.tryComplete() -> Root.pending: 2 -> 1
C1.tryComplete()   -> C1.pending=0, C1.onCompletion()
                   -> Root.pending: 1 -> 0
C2.tryComplete()   -> C2.pending=0, C2.onCompletion()
                   -> Root.pending=0, Root.onCompletion(caller=C2)
                   -> Root completed
~~~

If C1 and C2 complete **before** Root's call:

~~~text
Root.pending = 2
C1.tryComplete()   -> Root.pending: 2 -> 1
C2.tryComplete()   -> Root.pending: 1 -> 0
Root.tryComplete() -> Root.pending=0, Root.onCompletion(caller=Root)
                   -> Root completed
~~~

Both orderings are valid. Therefore, **do not write logic in `onCompletion` that assumes `caller` is always the last child**. The Javadoc allows `caller == this` along some traversal paths; the callback must rely on invariants about ready results, not on a specific CPU schedule.

## 5. Example 1 — Root Waits for Two Leaves and Completes Only on Enough Signals (Java 17+)

We build a simple tree consisting of a Root and two Leaves. Each leaf adds a number to an `AtomicInteger`. Root has `onCompletion` to snapshot the final sum and count how many times the callback runs. Because the leaves are independent, no execution order is fixed.

Create the file `SimpleCompleterTreeDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.atomic.AtomicInteger;

public class SimpleCompleterTreeDemo {
    static final class Root extends CountedCompleter<Void> {
        private final AtomicInteger sum = new AtomicInteger();
        private final AtomicInteger completionCalls =
            new AtomicInteger();
        private int finalSum;

        @Override
        public void compute() {
            setPendingCount(2);

            new Leaf(this, sum, 5).fork();
            new Leaf(this, sum, 7).fork();

            tryComplete(); // Root's own signal.
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            finalSum = sum.get();
            completionCalls.incrementAndGet();
        }

        int result() {
            return finalSum;
        }

        int completionCount() {
            return completionCalls.get();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        private final AtomicInteger sum;
        private final int contribution;

        Leaf(Root parent, AtomicInteger sum, int contribution) {
            super(parent);
            this.sum = sum;
            this.contribution = contribution;
        }

        @Override
        public void compute() {
            sum.addAndGet(contribution);
            tryComplete();
        }
    }

    public static void main(String[] args) {
        Root root = new Root();
        root.invoke();

        System.out.println("sum = " + root.result());
        System.out.println(
            "root completion calls = " + root.completionCount()
        );
        System.out.println("root done = " + root.isDone());
        System.out.println("root pending = " + root.getPendingCount());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac SimpleCompleterTreeDemo.java
java SimpleCompleterTreeDemo
~~~

Stdout when tasks complete normally:

~~~text
sum = 12
root completion calls = 1
root done = true
root pending = 0
~~~

**Why is the output deterministic?**

- Both leaves add 5 and 7 using `AtomicInteger.addAndGet`, so regardless of execution order, the sum is 12.
- Root **sets pending = 2 before forking**, then calls `tryComplete()` once.
- Each leaf performs its work and calls `tryComplete()`; the leaf's traversal with pending 0 leads to its completer, Root.
- A total of three completion arrivals at Root perform two decrements and one trigger of `onCompletion`.
- `root.invoke()` returns only after root is marked complete; thus the aggregated `finalSum` and callback count can be read afterward.
- `root.isDone() == true` is the status of **root**, not merely that `compute()` returned.
- It does not matter which leaf runs first or which thread invokes `onCompletion`.

**Do not confuse:** `completionCalls` is a counter variable used to verify the lesson. CountedCompleter does not automatically create such a counter for you; your logic must provide its own business results.

### What if Root Forgets tryComplete?

Suppose Root sets pending=2, forks two leaves, but **does not call tryComplete() itself**. The two leaves only provide two arrivals to Root: pending goes from 2 → 1 → 0, but **there is no third arrival** to trigger the root callback. `invoke()` can wait forever. This is a completion accounting bug, not an `AtomicInteger` bug or a scheduler bug.

### What if pending=1 and Root Still Calls tryComplete?

With two leaves, three arrivals total and only two needed for pending=1, Root can **complete before all work is guaranteed to be finished**, depending on interleaving order. Therefore, never tweak pending count just to "make it look reasonable" without re-proving the protocol.

## 6. Multi-Level Completion Trees: Child Does Not Mean Completed ForkJoinTask

Consider the tree:

~~~text
             Root (pending per signal count)
             /   \
        Branch1  Branch2
        /    \     /    \
      L1     L2   L3    L4
~~~

When L1 finishes and calls `tryComplete()`, traversal may reach Branch1 and **decrement Branch1's pending and stop**, not reaching Root yet. When Branch1 receives enough signals, it calls `onCompletion` and only then proceeds to Root. That allows Root to wait for **the entire group of work under each branch**.

A CountedCompleter *inside the tree with a non-null completer* is often just an **internal coordination node**. The Javadoc notes that the individual `isDone()` status of such a node **does not necessarily reflect** whether it has notified its parent of completion. That status only changes upon explicit completion operations, cancellation, or exceptions per contract.

**Important:** `tryComplete()` can propagate completion up to the completer **without marking each intermediate node as done**. Do not call `join()` on every internal node as if they were ordinary `RecursiveTask`s. Typically you invoke/join **the root**, or use a protocol that records branch completion if you truly need to wait on individual branches.

## 7. Example 2 — Divide-and-Conquer Tree Merging Results in onCompletion (Java 17+)

Problem: compute the sum of an `int[]` array. Each node is responsible for a range `[lo, hi)`. If the range is small, compute the local sum. If large, split into two children; once both children complete, the parent node merges their results in `onCompletion`.

Create the file `CompleterReduceDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.atomic.AtomicInteger;

public class CompleterReduceDemo {
    static final class Node extends CountedCompleter<Integer> {
        private final int[] data;
        private final int lo;
        private final int hi;
        private final AtomicInteger merges;
        private Node left;
        private Node right;
        private int result;

        Node(
                CountedCompleter<?> parent,
                int[] data,
                int lo,
                int hi,
                AtomicInteger merges
        ) {
            super(parent);
            this.data = data;
            this.lo = lo;
            this.hi = hi;
            this.merges = merges;
        }

        @Override
        public void compute() {
            if (hi - lo <= 2) {
                int local = 0;
                for (int i = lo; i < hi; i++) {
                    local += data[i];
                }
                result = local;
                tryComplete();
                return;
            }

            int mid = (lo + hi) >>> 1;
            left = new Node(this, data, lo, mid, merges);
            right = new Node(this, data, mid, hi, merges);

            setPendingCount(2);
            left.fork();
            right.fork();
            tryComplete(); // One arrival from the parent node.
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (left != null) {
                result = left.result + right.result;
                merges.incrementAndGet();
            }
        }

        @Override
        public Integer getRawResult() {
            return result;
        }
    }

    public static void main(String[] args) {
        int[] data = {1, 2, 3, 4, 5, 6, 7, 8};
        AtomicInteger merges = new AtomicInteger();
        Node root = new Node(null, data, 0, data.length, merges);

        Integer total = root.invoke();

        System.out.println("sum = " + total);
        System.out.println("merge callbacks = " + merges.get());
        System.out.println("root complete = " + root.isDone());
    }
}
~~~

Compile and run:

~~~bash
javac CompleterReduceDemo.java
java CompleterReduceDemo
~~~

Stdout:

~~~text
sum = 36
merge callbacks = 3
root complete = true
~~~

**How to verify the result:**

- The array has eight numbers from 1 to 8, so the sum is 36.
- When the range has length at most 2, a leaf node computes the local sum and calls `tryComplete()`.
- A non-leaf node creates two children, sets pending=2 **before** forking, and reports its own completion.
- Once both branches have results, the parent node's `onCompletion` reads `left.result` and `right.result` and merges them into `result`.
- An eight-element tree with a leaf threshold of two elements has four leaves and **three internal nodes** (two nodes splitting 4 elements and one root), so `merges` increments exactly three times.
- `getRawResult()` returns the node's `result` field. CountedCompleter **does not automatically set the raw result** for you just because `onCompletion` merged results.
- `root.invoke()` returns only when root has completed; the final merged result is read at the root.

**Concurrency point:** Both children can run in parallel. The CountedCompleter Javadoc permits using results of subtasks that **have completed according to the protocol** inside `onCompletion` without needing extra `synchronized` blocks to access completed children's results. This does **not** mean any mutable field read at any arbitrary time is safe; that rule relies on pending count genuinely ensuring the children have finished writing.

**Example limitations:** Summing `int` can overflow for very large arrays; if the domain requires exact sums beyond the `int` range, use `long` or `Math.addExact`/business policy. For short arrays, the overhead of creating many ForkJoinTasks can outweigh parallelism benefits; use a larger threshold based on real benchmarks.

## 8. The onCompletion(caller) Callback: Who Can caller Be?

### 8.1. Why Is There a caller Parameter?

Method:

~~~java
// Signature in CountedCompleter, not a standalone program.
public void onCompletion(CountedCompleter<?> caller)
~~~

`caller` is the task that caused traversal to reach the current node. It can be:

- **The node itself** (`caller == this`) when the node calls `tryComplete()` at the exact moment pending is already 0.
- **A subtask/descendant** that signaled and traversed up through the completer chain.

In the merge example, the callback reads `left/right.result` already computed per protocol, so it does not need to inspect `caller`. In other tree structures, the callback can use `caller` to locate the arriving branch, that branch's result, or sibling links.

### 8.2. Do Not Rely on "The Last Child Running"

A subtle bug:

~~~java
// WRONG if assuming caller is guaranteed to be the last child.
// Pseudocode only, not a standalone program.
@Override
public void onCompletion(CountedCompleter<?> caller) {
    Child last = (Child) caller;
    // Assumes last is always a valid child other than this.
}
~~~

If the callback is triggered by the parent task itself (`caller == this`), the cast will fail. Even when the callback is invoked from a child, which one is "last" depends on scheduling. If you need to combine in left/right order, explicitly store `left`/`right` and use **position in the tree**, not completion timing.

### 8.3. Using the Callback for Reduce or Continuation

Appropriate actions inside `onCompletion`:

- Merging results of finished branches.
- Marking a phase/aggregation eligible to complete.
- Propagating a result up to the parent node.
- Recording terminal state based on published data.

It is inappropriate to have the callback block indefinitely waiting on another subtask; a correct pending count already represents waiting. If the callback calls `join()` on a task that depends on the same completion chain, you can create a deadlock. Keep callbacks short, with clear invariants, and avoid throwing unexpected exceptions.

## 9. Completion Tree vs. Ordinary ForkJoinTask.join Tree

| Aspect | `RecursiveTask/RecursiveAction` | `CountedCompleter` |
| --- | --- | --- |
| Dependency wiring | Usually `join()` forked branches | Pending count + `tryComplete()`/`onCompletion()` |
| Can parent exit compute() early? | If still needing join, compute waits per its logic | Yes, returning from compute does not mean root is done |
| Parent/child relationship | Usually via references to child tasks | Via completer chain, plus domain references |
| Result merging | Usually done in compute after `join` | Can be done in `onCompletion` |
| Completion protocol | Standard per-fork/join framework | Programmer balances pending/arrivals |
| Main risk | Improper wait/blocking, too many tiny tasks | Missing/extra signals, race when incrementing pending, misreading task status |
| Debugging difficulty | Relatively straightforward | Requires drawing the tree and counting signals |
| Best fit | Standard divide-and-conquer needing each branch's result | Multi-branch completion graphs, search/forEach/continuation |

**Note:** `CountedCompleter` is still **a ForkJoinTask** and has `fork/invoke/join` at the API level. The difference lies in *how completion is triggered*, not that it runs outside `ForkJoinPool`.

Do not choose CountedCompleter just because you want code to be "nonblocking" in every sense. A task can still perform blocking I/O or call waiting code inside `compute`. Its flexibility is **avoiding join dependencies at every parent node in the completion algorithm**, not automatically turning all work into nonblocking I/O.

## 10. Variants for Balancing Pending Count: N or N-1?

### 10.1. Easy-to-Verify Pattern: N Children + Parent Arrival

~~~java
// Inside compute(), N is known and N >= 0.
// Not a standalone program.
setPendingCount(N);
for (int i = 0; i < N; i++) {
    forkChildWithCompleter(this, i);
}
tryComplete();
~~~

You must ensure each child calls `tryComplete()` once along its valid path, including empty branches or early returns. If `N == 0`, the parent sets pending=0, calls `tryComplete()` itself, and can complete immediately.

### 10.2. Optimized Pattern in the Javadoc: N-1 Child Arrivals, No Separate Parent Call

The `CountedCompleter` Javadoc shows an example of reducing overhead by **not forking all branches**, instead forking the right branch and processing the left branch directly. When the parent does not contribute a final arrival itself and lets the branches drive completion, the pending count can look **"off by one"**.

An optimized pattern must have an exact proof of the number of arrivals:

~~~java
// Algorithm pseudocode: must prove arrival count.
// Not a standalone program.
setPendingCount(1);
right.fork();
left.compute();  // Left branch runs directly,
                 // and leaves call tryComplete().
~~~

With two branches contributing two completion arrivals to the parent in total: the first decrements 1 → 0, and the second triggers completion. The parent **does not** make an extra `tryComplete()` call on this path.

**Do not mix the two patterns:** If you use pending=1 while the parent also calls `tryComplete()` as in the full N-child pattern, the node can complete prematurely. If you use pending=2 with only two child arrivals and no parent arrival, it can hang forever. Write down *who calls tryComplete, how many times, and when*.

### 10.3. Verifying with a Signal Table

| Design | Initial Pending | Expected Arrivals | Enough for onCompletion? |
| --- | ---: | ---: | --- |
| 0 children, parent calls itself | 0 | 1 | Yes |
| 2 children + parent calls itself | 2 | 3 | Yes |
| 2 children, parent does not call | 1 | 2 | Yes, if every child reports properly |
| 2 children, parent does not call | 2 | 2 | **No**, may hang |
| 2 children + parent calls itself | 1 | 3 | **Wrong accounting**, may complete early |
| 3 children + parent calls itself | 3 | 4 | Yes |

However, **counting arrivals correctly is only a necessary condition**. You must also ensure children have finished writing results and were registered before the task can complete. If you increment the count late or share state unsafely, results can still be wrong.

## 11. How Does propagateCompletion() Differ from tryComplete()?

`propagateCompletion()` uses the same completer and pending-count traversal as `tryComplete()`, but **does not call `onCompletion()`** along the traversal path.

Purpose: optimize trees where the job is purely to apply effects at the leaves (such as writing each array element or accumulating into independent atomic counters) and **no reduce callback is needed** at each node.

Comparison:

| Method | Pending nonzero | Pending zero | Calls onCompletion? |
| --- | --- | --- | --- |
| `tryComplete()` | Decrements count, stops | Walks up completer chain and completes root when reached | **Yes** |
| `propagateCompletion()` | Decrements count, stops | Walks up chain and completes root when reached | **No** |
| `complete(T)` | Does not wait for pending count | Completes the called task and triggers propagation to completer | Calls callback on the called task |
| `quietlyCompleteRoot()` | Does not wait for full count | Marks root complete | Does not replace full business bookkeeping |

Do not replace `tryComplete()` with `propagateCompletion()` in a tree that needs `onCompletion()` to merge results: the root may return without the aggregation ever running.

## 12. Example 3 — propagateCompletion Without Callbacks (Java 17+)

Create the file `PropagationOnlyDemo.java`:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.atomic.AtomicInteger;

public class PropagationOnlyDemo {
    static final class Root extends CountedCompleter<Void> {
        final AtomicInteger visits = new AtomicInteger();

        @Override
        public void compute() {
            setPendingCount(2);

            new Leaf(this, visits).fork();
            new Leaf(this, visits).fork();

            propagateCompletion();
        }
    }

    static final class Leaf extends CountedCompleter<Void> {
        private final AtomicInteger visits;

        Leaf(Root parent, AtomicInteger visits) {
            super(parent);
            this.visits = visits;
        }

        @Override
        public void compute() {
            visits.incrementAndGet();
            propagateCompletion();
        }
    }

    public static void main(String[] args) {
        Root root = new Root();
        root.invoke();

        System.out.println("visits = " + root.visits.get());
        System.out.println("root done = " + root.isDone());
    }
}
~~~

Compile and run:

~~~bash
javac PropagationOnlyDemo.java
java PropagationOnlyDemo
~~~

Stdout:

~~~text
visits = 2
root done = true
~~~

Both leaves increment the root's `AtomicInteger`. Because no callback needs to run, `propagateCompletion()` simply manages pending and completes the root. For independent side effects, this can be cleaner than defining no-op callbacks at every node.

**Important:** This does not prove `propagateCompletion()` is faster in all cases. Choose the method based on **whether `onCompletion` is needed**, then measure your actual workload if optimizing.

## 13. complete(T), quietlyCompleteRoot, and Other Traversal Methods

### 13.1. complete(T) Does Not Wait for Pending

`complete(T rawResult)` completes **the called task** regardless of its current pending count. Per the CountedCompleter contract, it invokes that task's `onCompletion(this)`, marks the task complete, and then triggers `tryComplete()` on its completer (if any).

This is useful when an algorithm has a **decisive completion point** that does not need to wait for remaining work, but it can also break the protocol if misused.

~~~java
// Illustration, not a standalone program.
task.complete(result);
~~~

Do not use `complete(...)` as a "patch" for a miscalculated pending count in an algorithm that must wait for all children. It **bypasses pending on the called task**, so it can yield incomplete results.

### 13.2. quietlyCompleteRoot()

`quietlyCompleteRoot()` marks root completion without waiting for all pending counts to reach 0. It commonly appears in **search** algorithms: once one branch finds an answer, there is no need to wait for all other branches to finish before returning the result.

However:

- Remaining branches may still be running or may not stop immediately.
- To cut short remaining work, they must **check a stop signal themselves** (for example, an `AtomicReference` that already holds a result).
- Side effects already performed in other branches are not automatically rolled back.
- Do not use early completion if invariants require **every branch** to finish executing.

### 13.3. firstComplete() and nextComplete()

The two methods `firstComplete()`/`nextComplete()` allow building a **custom completion traversal**:

- `firstComplete()` returns the node itself if pending is 0; if pending is non-zero, it decrements it and returns `null`.
- `nextComplete()` continues on the completer, or marks the root complete when reaching the root.

They are useful for reduce algorithms that maintain child/sibling lists and traverse completions manually. Because they are easy to misuse if combined with `tryComplete` in an uncontrolled way, start from the simpler `tryComplete + onCompletion` pattern before optimizing.

### 13.4. getRoot() and helpComplete()

`getRoot()` follows the task's completer chain to obtain the root. `helpComplete(int maxTasks)` attempts to help process some unprocessed tasks that have the current task on their completion path, within the API's bounds.

`helpComplete` does not guarantee "processing exactly maxTasks tasks" or replace all scheduling mechanisms. Do not use it to fix a tree missing completion signals; pending logic bugs are not cured by adding workers or calling help repeatedly.

## 14. Return Values: getRawResult and setRawResult

Many CountedCompleters use `CountedCompleter<Void>` because the actual result is a **side effect on a data structure** or guaranteeing all work is finished. In that case `invoke()` typically returns `null`.

If you want to return a value such as `CountedCompleter<Integer>`, you must design **where the result is stored**:

~~~java
// Pattern in a subclass, not a standalone program.
private int result;

@Override
public Integer getRawResult() {
    return result;
}
~~~

The Javadoc notes that `setRawResult(T)` by default does not serve as a useful result setter in CountedCompleter, so do not assume it is used to store aggregations as in some other `ForkJoinTask`s.

For example, `CompleterReduceDemo` overrides `getRawResult()` to return the merged sum after the root completes. For an internal node with a non-null completer, do not rely on `join()` of that node to fetch the aggregation unless you have explicitly designed **a task status mechanism**. The standard channel for the aggregated result is **the root**.

## 15. Exceptional Completion and Error Propagation in the Tree

### 15.1. Exceptions from compute

If `compute()` throws an exception, `ForkJoinTask` can mark the task **completed exceptionally**. With `CountedCompleter`, exceptions **can be propagated up the completer chain** per contract.

Related callback:

~~~java
// Signature in a subclass, not a standalone program.
@Override
public boolean onExceptionalCompletion(
        Throwable error,
        CountedCompleter<?> caller
) {
    // Record/decide whether to propagate further.
    return true;
}
~~~

By default, `onExceptionalCompletion` returns `true` to allow propagating the error up to incomplete completers. Returning `false` can stop further upward propagation; however, this should not be chosen just to "hide errors."

**Do not assume:** `onCompletion` applies only to normal completion. One branch throwing an exception does not mean remaining children automatically stop or partial aggregations are rolled back. The caller must define error policy and cleanup.

### 15.2. Errors Differ from Missing Signals

If a child fails and the protocol lacks an appropriate exceptional completion/cancellation path, a root waiting for normal signals may never complete normally. Conversely, a root completing exceptionally does not mean every branch has finished cleanup.

When using CountedCompleter for real work:

1. Identify which task is the **root responsible for reporting errors**.
2. Decide propagation via `onExceptionalCompletion`.
3. Collect exceptions thoroughly if multiple branches can fail; a single first throwable is not automatically a list of all errors.
4. Define whether remaining branches should be cancelled and via an appropriate cooperative cancellation mechanism.
5. Never let an aggregation callback use results from a branch that did not complete normally.
6. Manage pool lifecycle and resources outside the thread pool.

### 15.3. InterruptedException and Blocking Tasks

`CountedCompleter` does **not** automatically make every `compute()` interruptible. If you call I/O or a blocking API inside `compute`, it still has the limitations of that API. `ForkJoinPool` is primarily designed for small, short tasks or blocking supported by mechanisms like `ForkJoinPool.ManagedBlocker` where appropriate.

Do not treat exception propagation as a promise to automatically stop all threads. Each branch must have a stop protocol and cleanup if it has important side effects.

## 16. Pending-Count Bugs: How to Identify and Fix Them Properly

### 16.1. Missing Arrival: Root Never Completes

**Symptom:** Root forked children, all children appear finished, yet `root.invoke()/join()` keeps waiting. Common cause: a node retains pending > 0 due to a missing `tryComplete()` or miscounted arrivals.

Example:

~~~java
// WRONG if only two children report and the parent does not report itself.
setPendingCount(2);
left.fork();
right.fork();
// Missing parent's tryComplete.
~~~

Two children notify at most twice, taking pending 2 → 1 → 0, with no third arrival reaching the node at state 0. **Fix:** add the parent's `tryComplete` per the N-child pattern, or redesign with pending=1 and ensure only the two children contribute signals, without mixing both.

### 16.2. Extra Arrival: Premature Completion

**Symptom:** `onCompletion` reads uncomputed values, root returns while children are still running, results vary across runs.

Possible causes:

- Setting pending too low for the actual number of completion arrivals.
- A branch calling `tryComplete()` twice (for instance, once in `try` and once in `finally`).
- Parent reporting itself while also using a pending formula optimized for when the parent **does not** report.
- Creating branches dynamically and incrementing pending after forking.

**Fix:** draw the completion tree and list **every call path to `tryComplete`/`propagateCompletion`/`complete`**. Prove each path reports the exact number of times and results are published before notification. Never treat symptoms with `Thread.sleep()` or by changing schedulers.

### 16.3. Late setPendingCount

~~~java
// WRONG ordering, not a standalone program.
child.fork();
setPendingCount(1);
~~~

The child may finish very quickly, so the parent receives the signal while count is still 0 and completes prematurely. Setting pending before a child can run is a fundamental requirement.

### 16.4. Mixing complete with tryComplete

`complete(T)` is **unconditional completion** for the target task. If code both proactively completes a child and lets the child call `tryComplete` along the normal path, it can generate more signals than designed or break full-branch aggregation.

Choose one consistent protocol. If early completion is needed, clearly specify **why skipping pending tasks is allowed** and the cleanup semantics for remaining tasks.

### 16.5. Misunderstanding Intermediate Node isDone

You may observe a child/completer that has already propagated completion up to its parent while `child.isDone()` still does not reflect status like a standalone `ForkJoinTask`. This is documented behavior in the Javadoc. Do not write tests asserting "every internal node `isDone == true`" unless your program actually invokes methods that update node status per contract.

### 16.6. Deadlock from Reverse Join Dependencies

If node A holds logic waiting on `B.join()`, while B's completion depends on a callback/signal from A, A can create a cycle. CountedCompleter is designed to use completion chains in place of many `join` calls, but it **does not automatically prevent deadlocks** if code adds locks or improper waits.

### 16.7. Ordered Results

If results must preserve left/right order (e.g., string concatenation, ordered log merging), do not use "which child finishes first" to determine order. Label left/right in the structure and read each child's specific field in `onCompletion`.

## 17. Thread Safety and the Java Memory Model

### 17.1. Child Results Published to onCompletion

Per the `CountedCompleter` Javadoc, if pending count is managed properly, actions in `onCompletion` may access result fields of children that completed according to the protocol **without adding manual synchronization solely to publish those results**.

However, this guarantee is tied to **a correct completion protocol**. If the callback runs early due to an undercounted pending or a child signals completion before writing its result, no memory primitive turns an uncomputed value into the right result.

In `CompleterReduceDemo`, each child writes `result` before calling `tryComplete()`; the parent merges only once signals are properly balanced.

### 17.2. Arrays and Shared Mutable Data

If each child processes a **non-overlapping** slice of an array, write regions can be safe by ownership. But if children update a shared counter, use `AtomicInteger` or an appropriate structure. CountedCompleter's pending count **only protects completion accounting**; it does not automatically make all domain fields atomic.

`SimpleCompleterTreeDemo` uses `AtomicInteger` for the sum because both leaves update it concurrently. The reduce example stores partial sums in distinct `Node` instances, and the parent reads those results when allowed to merge.

### 17.3. Root Completion and the Caller Side

`root.invoke()`/`root.join()` are the completion wait points for the root per the `ForkJoinTask` contract. The caller must not read an unsynchronized `result` field while the root is still RUNNING and expect a consistent snapshot.

Do not think of pending count as a transaction or a general memory barrier for every related object. When side effects involve databases or networks, you need synchronization/transactions and error policies specific to that domain.

## 18. Performance and Choosing Branch Granularity

### 18.1. Forking Too Finely

If a problem has a few thousand elements and creates a `ForkJoinTask` per element, the overhead of task allocation, scheduling, queueing, callbacks, and cache contention can exceed the data processing time.

An effective implementation typically:

- Stops splitting when a range has at most **threshold** elements.
- Processes an entire range sequentially in a leaf rather than one task per element.
- Forks fewer branches, processing one branch directly on the worker when appropriate.
- Considers a balanced tree structure to avoid funneling all notifications into a single hot root.
- Measures task creation cost and worker idle ratio for the workload.

Threshold is a performance parameter, **not a correctness condition**, as long as splitting preserves non-overlapping invariants and each branch reports completion properly.

### 18.2. Tree Completion and Contention

With a root containing tens of thousands of direct children, all children may contend on updating **the root's single pending count**. Splitting into multiple branches distributes contention; each branch reports only once to its parent after its subtree completes.

A tree reduces fan-in at a single point, but also increases node and callback counts. Choosing tree depth and fan-out should be guided by benchmarks on real data.

### 18.3. Work Stealing

`ForkJoinPool` is designed to support work stealing: idle workers can steal tasks from other queues. `CountedCompleter` integrates with this scheduling mechanism, but **does not guarantee** that every task runs on a separate thread or that all tasks run in parallel immediately.

When measuring performance, examine branch duration skew, core count, pool parallelism, leaf size, GC, allocation, and contention. Do not conclude "non-blocking join means always faster than RecursiveTask"; a simpler structure is often better if the workload does not need complex completion callbacks.

## 19. Meaningful Testing of Completion Trees

### 19.1. Testing Results and Callback Counts

From the runnable examples:

- With a root and two leaves, the sum must be 12 and the root's `onCompletion` runs once.
- With array 1..8, the sum must be 36, with three merge callbacks from the three internal nodes.
- With propagation-only, the visit count must be 2 and the root is done.

All such assertions should be checked after `root.invoke()`/`join()`, never reading unpublished results while other threads are still updating them.

### 19.2. Testing Different Interleavings

Do not rely on `Thread.sleep(50)` and assume a child has finished. Use `CountDownLatch` or `CyclicBarrier` if you need to force branches to a synchronization point, and set a **timeout** at the test level so the test suite does not hang when pending is miscounted.

Test cases to cover:

1. Children complete **before** the parent calls `tryComplete()` itself.
2. Parent reports completion **before** the children.
3. Children concurrently call `tryComplete()` on the same node.
4. Empty branches or small leaf thresholds: is there still one valid completion?
5. Child throws an exception: root reports an error or the exceptional completion protocol behaves properly.
6. Early termination in search: root completes while remaining branches may still be running.
7. Multiple invocations or task reuse: do not arbitrarily re-`invoke()` an already completed `CountedCompleter` without a reset design.
8. All array elements are processed exactly once per domain rules, with no duplicates or omissions.

### 19.3. When a Test Hangs

If `invoke()` waits indefinitely:

- Inspect `getPendingCount()` on key nodes (read as a diagnostic snapshot, do not alter logic around it).
- List the expected number of `setPendingCount`, `addToPendingCount`, and `tryComplete` calls.
- Check child exceptions: is there an early return or throw path that skips normal signaling?
- Take a thread dump to see whether workers are waiting or deadlocked on another lock.
- Check whether the parent could complete before children were published.
- Re-verify **N+1 arrivals for pending=N** in the fork N children + parent arrival pattern.

A timeout alone does not prove a monitor deadlock; it may simply mean the root never received enough completion signals.

## 20. CountedCompleter Code Review Checklist

| Question | Criterion |
| --- | --- |
| Does each node have the right completer? | `super(parent)` or appropriate constructor; root has null parent |
| When is pending count set? | Before forking children that can report completion |
| How many completion arrivals reach the node? | Both parent arrival and child arrivals counted |
| Does every leaf call `tryComplete`/propagate properly? | No omissions via return/throw and no double reporting |
| Is there a result-merging callback? | Use `tryComplete` and `onCompletion` |
| No callback needed? | Can use `propagateCompletion` |
| Are all results written before signaling? | Child publishes result before `tryComplete` |
| Does `onCompletion(caller)` account for `caller==this`? | No blind cast to child |
| Can root complete before enough branches finish? | Avoid low pending or unconditional complete |
| Is `join()` used on intermediate nodes? | Understand internal node status |
| Is there an exception propagation policy? | Clear `onExceptionalCompletion` or root handling |
| Are there external side effects outside the JVM? | Separate rollback/cleanup policy |
| Are tasks large enough to fork? | Benchmark threshold and contention |
| Tested under multiple interleavings? | Use latches, timeouts, invariant checks |
| Confusing pending count with auto-tracked child count? | It is only a code-managed atomic counter |

## 21. Self-Check Questions

**1.** A parent forks 3 children and **also calls `tryComplete()` itself** after forking. What should `setPendingCount` be under the simple pattern?

**3**. There are 4 arrivals (parent + 3 children); three arrivals decrement pending from 3 down to 0, and the fourth triggers the callback.

**2.** Pending is already 0; is that enough to conclude root `isDone()`?

Not yet. The subsequent `tryComplete()` call to enter the callback branch and mark the root complete may not have happened yet.

**3.** Does it matter if a child calls `tryComplete()` before the parent calls `setPendingCount`?

It can fail. The child can cause the node to complete early while pending is still 0, and then the parent writes the count late. **Set pending before forking**.

**4.** Why must `onCompletion(caller)` not always cast `caller` to a child?

Because `caller` is sometimes **the node itself** when the node triggers completion; it is not always another child.

**5.** Does `propagateCompletion()` trigger `onCompletion()`?

No. It continues the counting and propagation mechanism **without invoking completion callbacks** along the way.

**6.** Does calling `complete(result)` wait for pending to reach 0?

No. It completes the called task regardless of pending, then triggers propagation to the completer if present.

**7.** Why is `RecursiveTask.join()` on every intermediate node not the default reasoning for CountedCompleter?

Because nodes with a completer may only propagate completion up to their parent; their own `isDone()` status is not necessarily marked as normal completion through traversal. Typically you wait on the root or a specifically designed result.

**8.** In reduce, when is the parent allowed to read `left.result` and `right.result`?

Once both branches are guaranteed to have **finished writing** and the completion protocol actually allows the parent to run `onCompletion`; not merely because they were forked or the parent's `compute` returned.

**9.** Why can a root with 10,000 direct children suffer contention?

Because many children concurrently update the root's single pending count. Splitting into branches reduces fan-in, at the trade-off of more nodes and callbacks.

**10.** If you want to return immediately when one search branch finds a result, which API can you use?

`quietlyCompleteRoot()` combined with a thread-safe result holder (such as `AtomicReference`) and a protocol for remaining branches to recognize they can stop. It does not automatically kill other branches.

**11.** Can a child's exception affect the root?

Yes. `onExceptionalCompletion` by default allows propagating exceptional completion up to the completer per contract. However, it does not automatically ensure all other branches are cancelled or side effects are rolled back.

**12.** When should you choose `RecursiveTask` instead of `CountedCompleter`?

When the algorithm only needs to fork branches, join results, and combine them directly, a `RecursiveTask` is usually easier to write, easier to review, and carries less risk of pending bugs. Use `CountedCompleter` when you genuinely need multi-branch completion traversal or continuation.

## 22. Official References and Conclusion

Official Java 17 Javadoc:

- [CountedCompleter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): defines `pending count`, `completer`, `tryComplete()`, `onCompletion()`, `propagateCompletion()`, `firstComplete()`, `nextComplete()`, and forEach/map-reduce/search examples.
- [ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): task lifecycle, `fork`, `invoke`, `join`, cancellation, and exceptional completion.
- [ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, scheduling, and task-managing workers.

**Key takeaway:** `CountedCompleter` does not automatically count children. A **completer tree** is a chain of tasks receiving completion notifications; **pending count** is an algorithm-configured arrival counter; `tryComplete()` decrements pending when non-zero or triggers `onCompletion()` and walks up to the parent when zero. With the **N children + parent self-report** pattern, use `pending = N`, set pending before forking, and ensure every valid path reports exactly once. Only when both completion accounting and result publication are right does the root represent a reliably completed computation.
