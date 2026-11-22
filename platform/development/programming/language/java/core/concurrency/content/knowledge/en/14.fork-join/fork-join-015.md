# Setting the Pending Count Before Forking to Prevent Premature Completion in Java CountedCompleter

> **Scope:** The **Fork/Join** mechanism of Java SE 17+, focusing on `java.util.concurrent.CountedCompleter` and the ordering of **registering pending completions before calling `fork()`**. This lesson explains the tree-based completion model, the `tryComplete()` mechanism, premature root completion bugs, "off by one" counting variants, data guarantees, and compilable/runnable exercises. It only covers **general Java concurrency**, without mixing in Spring-specific Fork/Join or scheduling mechanisms.

## 1. The Core Problem: A Child Task Can Complete Immediately After Fork

In Fork/Join, `fork()` makes a `ForkJoinTask` eligible for asynchronous processing. There is no guarantee that the parent thread will finish executing the subsequent lines before another worker completes the child task.

With `CountedCompleter`, each task maintains a **pending count** describing the number of completion signals still to be recorded according to **the protocol chosen by the algorithm author**. When a child task finishes, it can propagate a completion signal up to its parent task via `tryComplete()`.

If the parent thread **forks the child first and sets the pending count afterward**, the child task may call `tryComplete()` while the parent still has the default pending count of **0**. In that case, the completion path sees the parent as having "no pending left" and may invoke `onCompletion`, propagate up to the grandparent, or mark the root as completed **before the other child work finishes**.

**Golden rule:**

```java
setPendingCount(numberOfChildren);  // Register first
child1.fork();
child2.fork();
tryComplete();                       // Signal the current node's own work
```

This is **illustrative Java pseudocode inside `compute()`**, where `child1` and `child2` are `CountedCompleter` instances having `this` as their completer, and `numberOfChildren` corresponds to the number of children actually forked. In this variant, if there are two children to wait for, use `setPendingCount(2)`. Do not forget the parent's own `tryComplete()`, or another equivalent counting design.

The key principle is **register-before-publish** ordering: finish registering dependencies before publishing child tasks so that other workers can execute them.

## 2. Distinguishing CountedCompleter from RecursiveTask/RecursiveAction

Java Fork/Join has several task types:

| Type | Completion model | When it fits |
|---|---|---|
| `RecursiveTask<V>` | `compute()` returns V; typically `fork()` then `join()` children to combine results | Divide-and-conquer that needs to return a result up the tree |
| `RecursiveAction` | `compute()` does not return V; typically `join()`/`invokeAll` children | Parallel tasks that do not return a value directly |
| `CountedCompleter<T>` | Completes via **pending completion signals**, `tryComplete`, and optional `onCompletion`; does not necessarily call `join` on each child | Completion trees, fan-out, traversal, map/reduce, coordinating multiple branches without classic blocking join |

`CountedCompleter<T>` extends `ForkJoinTask<T>` and is an abstract class. A concrete class must implement `compute()`; it can override `onCompletion(CountedCompleter<?> caller)` or `onExceptionalCompletion(Throwable, CountedCompleter<?> caller)` when needed.

This class is often declared as `CountedCompleter<Void>` if it does not need to return a value through `invoke()`/`join()`. When there is an actual result, you need to understand `getRawResult()` and how results are published/read; do not assume that child results are automatically summed by `CountedCompleter`.

**Important difference:** with `RecursiveTask`, calling `join()` on a child is usually an explicit boundary for "waiting for the child". With `CountedCompleter`, **parent root completion depends on the exact number of completion reports**. If the count is wrong or `tryComplete` is called incorrectly, the root may complete prematurely or wait forever.

## 3. What Pending Count Is, and What It Is Not

In `CountedCompleter`, the initial count defaults to **0**, unless an initial pending count is passed to the constructor.

Core APIs:

```java
getPendingCount()
setPendingCount(int count)
addToPendingCount(int delta)
compareAndSetPendingCount(int expected, int count)
decrementPendingCountUnlessZero()
tryComplete()
propagateCompletion()
```

This is a **shortened signature list**, not standalone code. `setPendingCount` assigns a value; `addToPendingCount` atomically increments/decrements by delta; `tryComplete` either participates in decrementing the count or triggers completion, depending on the count's value at the time it is called.

The pending count **does not automatically know which tasks exist**. It is just an atomic integer, **not a child list or ownership registry**. `CountedCompleter` does not automatically track how many children you just forked, which child has finished processing, or whether each child calls complete exactly once.

That means:

- You must explicitly define the **number of completion signals** required.
- You must ensure **every child to be awaited is registered before it can signal**.
- The same child must not accidentally report `tryComplete` twice.
- There must be a completion path for the current node and completion paths for the children according to the counting convention.
- When a task fails/is cancelled, there must be an exception/cancellation policy rather than assuming every branch reports normal completion.
- The value `pending == 0` **does not by itself mean the task has been marked done**. In the `tryComplete` algorithm, an invocation that observes count equal to 0 is still needed to trigger `onCompletion`/propagate to the completer/root.

## 4. Exact Semantics of tryComplete()

According to the Java SE 17 specification, when `tryComplete()` is called on a task T:

1. If T's pending count is **non-zero**, it is atomically decremented and the call **returns**, without automatically calling `onCompletion` just because that decrement made the count 0.
2. If T's pending count is **0** at the time of inspection, `onCompletion(caller)` is triggered for T.
3. Then the mechanism may proceed up to T's completer and apply the same rule.
4. If it reaches the root (no completer left), the root is marked normally completed according to the completion traversal.

One way to visualize it:

```text
tryComplete() on task X
       |
       v
pending(X) > 0 ?
   | yes: decrement by 1 and return
   |
   no: call X.onCompletion(caller)
       |
       v
       Does X have completer P ?
           | yes: continue completion traversal at P
           | no: root completes
```

**Extremely important:** "decrementing from 1 to 0" usually **does not trigger the completion callback in that same call**. A subsequent signal that sees the count already at 0 is needed. Therefore, some patterns use `setPendingCount(n)` for n children and then **the parent itself calls `tryComplete()`**: there are **n + 1 signals** in total (n children, one from the parent), causing the last signal to see pending equal to 0 and trigger completion.

### State Table with Two Children

Suppose the parent calls `setPendingCount(2)`, two children A/B are forked, and the parent calls `tryComplete` on itself:

| Event | Pending before | Behavior | Pending after |
|---|---:|---|---:|
| Parent `setPendingCount(2)` | 0 | Registers two signals from children | 2 |
| Parent `tryComplete()` (before the 2 children report) | 2 | Decrements by 1 and returns | 1 |
| A finishes, propagates signal to parent | 1 | Decrements by 1 and returns | 0 |
| B finishes, propagates signal to parent | 0 | Parent's `onCompletion`, continues up to root | 0 |

**The schedule can differ**: A or B might return before the parent calls `tryComplete` on itself. The table only illustrates one order, not a required execution order. With the right number of signals and registrations, the last signal will trigger completion even if signals arrive in different interleavings.

### Do Not Misuse 0 as a "Counter of Running Work"

`pendingCount` does not replace `Thread.State`, nor is it the number of executing threads or the `ForkJoinPool` queue size. It is the **state of the completion protocol** defined by the algorithm. Distinguish between "task is completed", "pending count read as 0", and "worker thread is idle".

## 5. Why Must setPendingCount Come Before Fork?

Consider two threads:

```text
Parent thread (P)                      Worker running child (C)
----------------------------------    --------------------------------------
new Child(P).fork()  ----------------> compute()
                                       processes quickly
                                       tryComplete()
                                           child pending == 0
                                           -> P pending == 0
                                           -> P.onCompletion(...)
                                           -> may complete root
P.setPendingCount(1)  (TOO LATE)
P still plans to fork/process another branch
```

This is a **valid concurrency interleaving**. The parent thread can be descheduled right after `fork()`. A worker can run and finish the child in that window. Consequences:

- `P.onCompletion` may run when P has not yet registered its dependency.
- If P is the root, `invoke()`/`join()` on the caller may be unblocked too early.
- The caller reads an aggregated result that does not yet contain all data, or cleans up resources while other children are still working.
- If P writes the pending count after it has already completed, the count state **no longer reflects the lifecycle**; incrementing the count late does not "undo" a completed root.
- The callback may be triggered out of phase; if there are external side effects, running before the intended time can violate invariants.

Use the right order:

```java
setPendingCount(1);
new Child(this).fork();
tryComplete();
```

This is an **illustrative snippet inside `compute()`**, with `Child` constructed so that `getCompleter() == this` and the child calls `tryComplete` upon completion. The count has been incremented/set **before** publishing the child to the scheduler.

**Do not "fix" this with `Thread.sleep()` between fork and setPendingCount.** Sleeping does not create an ordering rule guaranteeing the worker will always be slower. In fact, sleeping gives the child even more opportunity to run first.

## 6. Preserving Order with Multiple Children

For n independent children to await, the easiest version to understand is:

```java
@Override
public void compute() {
    int n = children.size();
    setPendingCount(n);          // Register all first

    for (Child child : children) {
        child.fork();
    }

    tryComplete();               // The parent's own signal
}
```

This is **pseudocode with Java syntax**, not a complete class; `children` holds `CountedCompleter` children using `this` as completer, and `Child` has compute logic ending with `tryComplete`.

Correctness conditions:

- n must equal the **number of child branches expected to report completion**, not merely the number of objects created.
- Every counted child must have a completer matching the parent.
- No child completes twice under the same protocol.
- `setPendingCount(n)` must run **before any child is forked/executed directly on another thread**.
- The parent's `tryComplete` is called after finishing the parent's own work (in this pattern).
- In a branch that creates no children (n=0), `tryComplete` on pending 0 allows direct completion.

### When a Child Subdivides into Further Children

`Child.compute()` can in turn call `setPendingCount(k)` and fork k grandchildren. Only when the grandchildren complete per protocol does the child report completion up to the parent. Thus, the parent **counts its direct children**, and does not add all grandchildren into the parent's count if grandchildren are already managed by the child.

Tree diagram:

```text
                    Root (pending=2)
                    /              \
              Left (pending=2)    Right (pending=2)
                /       \           /        \
              L1         L2       R1          R2

Each internal node:
  - Registers 2 before forking 2 children.
  - Calls tryComplete() on itself.
  - Receives completion signals from 2 children.

Only when Left and Right complete does it propagate to Root.
```

This enables recursive decomposition, where a forked child task can outlive the parent code snippet that just ran.

## 7. Runnable Java 17 Example: Ensuring Root Completes Only After Every Leaf Has Processed

The following program creates a tree that splits an 8-element array in half. Each internal node:

1. Computes `mid`.
2. Calls **`setPendingCount(2)` before forking any child**.
3. Forks two children with `this` as completer.
4. Calls `tryComplete()` for the node's own work.

Each leaf adds one element to `AtomicLong sum`, increments `AtomicInteger leaves`, and calls `tryComplete()`. The root overrides `onCompletion` to count root completions. The caller uses `ForkJoinPool.invoke(root)` to wait for the root to complete and then checks the results.

Create the file **`PendingCountDemo.java`**:

```java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public class PendingCountDemo {
    static final class SumTask extends CountedCompleter<Void> {
        final int[] values;
        final int lo, hi;
        final AtomicLong sum;
        final AtomicInteger leaves;
        final AtomicInteger rootCompletions;

        SumTask(SumTask parent, int[] values, int lo, int hi,
                AtomicLong sum, AtomicInteger leaves,
                AtomicInteger rootCompletions) {
            super(parent);
            this.values = values;
            this.lo = lo;
            this.hi = hi;
            this.sum = sum;
            this.leaves = leaves;
            this.rootCompletions = rootCompletions;
        }

        @Override
        public void compute() {
            if (hi - lo >= 2) {
                int mid = (lo + hi) >>> 1;
                setPendingCount(2); // MUST happen before either fork
                new SumTask(this, values, lo, mid, sum, leaves,
                        rootCompletions).fork();
                new SumTask(this, values, mid, hi, sum, leaves,
                        rootCompletions).fork();
            } else if (hi > lo) {
                sum.addAndGet(values[lo]);
                leaves.incrementAndGet();
            }
            tryComplete(); // current task's completion signal
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            if (getCompleter() == null) {
                rootCompletions.incrementAndGet();
            }
        }
    }

    static void runCase(ForkJoinPool pool, int[] input, String label) {
        AtomicLong sum = new AtomicLong();
        AtomicInteger leaves = new AtomicInteger();
        AtomicInteger completedRoot = new AtomicInteger();
        SumTask root = new SumTask(null, input, 0, input.length,
                sum, leaves, completedRoot);
        pool.invoke(root);
        System.out.println(label + "Sum=" + sum.get());
        System.out.println(label + "Leaves=" + leaves.get());
        System.out.println(label + "RootCompletions=" + completedRoot.get());
        System.out.println(label + "RootDone=" + root.isDone());
        System.out.println(label + "Pending=" + root.getPendingCount());
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(4);
        try {
            runCase(pool, new int[] {1, 2, 3, 4, 5, 6, 7, 8}, "data");
            runCase(pool, new int[0], "empty");
        } finally {
            pool.shutdown();
        }
    }
}
```

Compile and run with JDK 17:

```bash
javac --release 17 PendingCountDemo.java
java PendingCountDemo
```

**Verified compiled and run stdout:**

```text
dataSum=36
dataLeaves=8
dataRootCompletions=1
dataRootDone=true
dataPending=0
emptySum=0
emptyLeaves=0
emptyRootCompletions=1
emptyRootDone=true
emptyPending=0
```

### Reading the Results Correctly

- `dataSum=36` because 1+2+3+4+5+6+7+8 = 36.
- `dataLeaves=8` because the tree processes each cell of the array exactly once.
- `dataRootCompletions=1` means the `onCompletion` callback on the root was triggered once in the verified run, after the branches reported completion.
- `dataRootDone=true` shows that the root was marked done, allowing `pool.invoke(root)` to return.
- `dataPending=0` is the final pending count in this protocol. **Do not use the number 0 alone as proof that a task is done**; `isDone`/`invoke` provides the lifecycle signal.
- `emptySum=0`, `emptyLeaves=0`, and `emptyRootCompletions=1` also test the n=0 branch: no children are created, and `tryComplete` suffices for the root to complete.

### Why Does the Demo Have AtomicLong/AtomicInteger?

Multiple leaves can run concurrently on multiple workers. Each leaf adds to **a shared counter**, so `sum += values[lo]` on a plain `long` would risk lost updates. Using `AtomicLong.addAndGet` and `AtomicInteger.incrementAndGet` ensures individual updates are not lost.

**The `CountedCompleter` pending count does not automatically make every field updated by leaves thread-safe.** It coordinates completion; shared results still require ownership, atomic operations, or a map/reduce design via `onCompletion` and appropriate child results.

### Why Use invoke(root)?

`ForkJoinPool.invoke(root)` waits for the root task to finish before returning to the caller. If the completion protocol is wrong and the root completes **prematurely**, this method can also return early; `invoke` cannot know which child was missing from the pending count. Therefore, the source of truth is **the dependency relationship that the algorithm accurately registers**.

### Why Not Use Thread.sleep to Prove It?

Thread scheduling can change between runs. The demo relies on API invariants and completion traversal. There is no need to put a sleep in a leaf to "force" the root to wait long enough. Proper testing should prove correctness through signal counts and use `invoke` as the completion boundary, not rely on timing.

## 8. Proof of Count for the Binary-Split Tree

For an internal node with exactly two children:

- `setPendingCount(2)` sets pending = 2.
- The current node calls `tryComplete()` once when finishing its own work.
- Child A reports completion once via `tryComplete()` and propagates to the node.
- Child B reports similarly.

A total of **3 completion signals** arrive at the node, of which **the first two signals** take pending 2→1→0, and **the third signal** sees pending 0 and triggers `onCompletion`, then walks up to the completer.

**The signal order can be any order**:

```text
Schedule 1: self, A, B  -> 2->1, 1->0, onCompletion
Schedule 2: A, self, B  -> 2->1, 1->0, onCompletion
Schedule 3: B, A, self  -> 2->1, 1->0, onCompletion
```

All of these schedules are correct if all signals arrive exactly once and the parent count is set before the children can run. `tryComplete`/pending operations use atomic operations per contract, so multiple workers can send completion signals without losing a count decrement as with unsynchronized `int--`.

### Induction for the Entire Tree

**Base case:** a leaf forks no children, default pending is 0; after processing its element, the leaf calls `tryComplete`. It triggers the leaf's `onCompletion` and propagates one signal to its parent.

**Inductive step:** each child subtree has completed before the child sends a signal up to its parent; the parent registered both children before forking; the parent only triggers completion when it has both children and the parent's own signal. Therefore, a parent completes after all leaves in its subtree.

**Conclusion:** the root completes only after every registered leaf in the tree has finished processing. This is why the pending count must be set before publication: otherwise, the inductive step that "the parent already knows its dependencies" is broken.

**Assumptions:** every task always reaches normal completion, there are no uncaught exceptions/cancellations causing missing signals, no child reports completion twice, no logic intentionally calls `quietlyCompleteRoot` or `complete` to force early root completion, and there are no bugs in code outside `CountedCompleter`.

## 9. Optimized Variant: Fork One Child, Compute the Other Directly

The `CountedCompleter` JavaDoc API also describes a variant:

```java
// Placed inside compute() of class Task extends CountedCompleter<Void>:
if (hi - lo >= 2) {
    int mid = (lo + hi) >>> 1;
    setPendingCount(1);                 // Only one child is forked
    new Task(this, mid, hi).fork();     // Right child asynchronously
    new Task(this, lo, mid).compute();  // Left child runs directly
} else {
    if (hi > lo) {
        process(array[lo]);
    }
    tryComplete();
}
```

This is **illustrative code inside a class**, where `Task`, `lo`, `hi`, `array`, and `process` are provided by the application. It is not a standalone file.

Why `setPendingCount(1)` when there are **two logical branches**?

- Only the **right child** is `fork()`ed, becoming an asynchronous task that needs to be counted separately.
- The left child runs **directly** via `compute()` on the current working thread.
- **There is no separate `tryComplete()` on the parent after the recursion branch**. The left completion signal walks through the completer chain and acts as "the work the parent was still doing".
- One signal from the right and one from the left make **two signals**: count 1→0, and then the next signal triggers `onCompletion`. This explains why it looks "off by one" yet is valid.

**Do not copy `setPendingCount(1)` while keeping code that forks both children and calls `tryComplete` on itself, or vice versa**. The pending count must match **the actual signal structure**, not mechanically match the number of `new Task` lines.

### Comparing the Two Patterns

| Pattern | Forked children | Pending registered | Self tryComplete | Completion condition |
|---|---:|---:|---|---|
| Easy to understand: fork both | 2 | 2 | Yes, after fork | 2 children + self signal |
| Optimized: fork right, compute left directly | 1 | 1 | No on internal branch; leaf calls it | Right + Left signals |
| Leaf with no fork | 0 | 0 | Yes, after processing | Single leaf signal |

**Optimization should not trade away clarity when you are learning.** Start with the pattern of setting the count to the number of forked children plus self `tryComplete`, and prove the completion schedule is correct. Only switch to the streamlined variant once you understand the exact count protocol and have tests in place.

## 10. addToPendingCount(1) Before Each Fork: When to Use It?

When the number of children is generated incrementally and n is not known in advance, you can use `addToPendingCount(1)` **before each fork**:

```java
// Illustration inside compute() of CountedCompleter:
for (WorkItem item : discoveredItems) {
    addToPendingCount(1);             // Register a child before fork
    new Child(this, item).fork();
}
tryComplete();                        // Only after registering all
```

This is illustrative code; types/variables need to be defined. Key points:

- `addToPendingCount(1)` executes atomically.
- **Each child is registered before publishing it**.
- In this pattern, the parent **has not called self `tryComplete` before the child-spawning loop finishes**, so it will not accidentally mark complete while still planning to register more work.
- If a child finishes quickly, the count can drop back to 0 before the next registration. That **does not automatically trigger `onCompletion`** because only a `tryComplete` call observing count 0 performs completion traversal; the parent's self signal is held until the end of the registration phase.
- However, if another thread could add more children after the parent has signaled its own completion or after the root is done, the count protocol needs a new design rather than calling add arbitrarily.

**Pitfall:** `setPendingCount(n)` after some children have already completed is not equivalent to adding n new ones. `setPendingCount` **overwrites the current value**; it can wipe out decrements that have already occurred. Only set once before publication, or use controlled increments before each fork under a clear protocol.

### Why Not Use an External AtomicInteger to Count Work?

You could build a different completion protocol with `AtomicInteger` and a latch, but once you use `CountedCompleter`, the pending count is part of the **completion control flow** supported by ForkJoin. An external counter does not automatically notify the completer and does not let `ForkJoinPool.invoke(root)` know when the root has completed.

## 11. Mistake: Count Equals n Without Self tryComplete

Suppose:

```java
setPendingCount(2);
new Child(this).fork();
new Child(this).fork();
// BUG: compute() returns without calling tryComplete().
```

This is an illustrative bug snippet inside `compute()`.

With two children, the first signal decrements 2→1, and the second decrements 1→0. **There is no third signal observing pending 0**, so the root may **never be marked complete**. A caller doing `join()`/`invoke()` risks waiting forever.

There are two fixes, depending on the protocol:

1. **Keep `setPendingCount(2)`** and call `tryComplete()` once on the parent after forking, as in the runnable example.
2. Choose another proven counting variant, such as `setPendingCount(1)` with no parent self-signal in a valid tail-call structure. Do not simply "lower the count arbitrarily" without accounting for the number of signals.

A pending count of 0 is an **intermediate state**; the completion event still needs to be properly triggered.

## 12. Mistake: Count Less Than Number of Children and Premature Completion

An intentionally wrong example:

```java
setPendingCount(1); // Wrong for the pattern of forking 2 children + self signal.
new Child(this, slowTask).fork();
new Child(this, fastTask).fork();
tryComplete();
```

This is an illustrative snippet, not a standalone class.

If the self signal arrives first, count goes 1→0. Then **the fast child** reports completion and observes pending 0, causing the parent to run `onCompletion`/propagate, while **the slow child may still be running**. Premature root completion is the logical consequence.

If using `ForkJoinPool.invoke(root)`, the caller may read the aggregated result **before the slow child writes its part**. It is not that `invoke` is broken: the root was **erroneously reported as completed** by the algorithm.

This is the exact failure mode targeted by this lesson: you must ensure the amount of work registered is **accurate and complete** before forking.

## 13. Mistake: Count Greater Than Number of Children and Hanging Forever

Example:

```java
setPendingCount(3); // Wrong: actually there are only 2 children + self signal.
new Child(this, left).fork();
new Child(this, right).fork();
tryComplete();
```

This is illustrative code. A total of three signals arrive at the parent: count 3→2→1→0. **No signal observes count 0 at the start**, so the root may fail to complete even though all children have finished.

Easily observable consequences are `join` hanging, the task remaining "active" forever, `onCompletion` not being called, and the pool reporting no clear error. Do not patch this with an extra meaningless `tryComplete` call; fix the calculation of the number of children and signal sources.

## 14. Mistake: Setting Count After Fork and Racing with Child Completion

The most dangerous example:

```java
new Child(this, left).fork();
new Child(this, right).fork();
setPendingCount(2); // WRONG: a child may have already reported complete.
tryComplete();
```

This is an illustrative bug snippet.

Several undesirable outcomes can occur depending on the interleaving:

- A fast child sees the parent's pending as 0, triggering parent/root completion before the count is set.
- After the parent writes pending 2, already-completed children cannot "report again", so pending stays positive and another caller may never see a new completion path.
- If the parent already ran `onCompletion` and the result was aggregated early, slow children may still be mutating shared state after the caller thinks the work is done.
- If the callback has side effects (writing the final result, closing a stream), those side effects can happen before a valid point in time.

**Proof of correctness cannot be "I ran it 1,000 times and it worked every time."** A race can be very rare when a child has not yet been scheduled on a CPU in time. Prove it by ordering: the parent count is registered **before publication**, regardless of scheduler interleaving.

## 15. Other Completion APIs: Do Not Substitute Mechanically

### `propagateCompletion()`

`propagateCompletion()` follows a traversal similar to `tryComplete()`, but **does not call `onCompletion`** when walking through completers. It is suitable when there is no need to aggregate results in a callback.

```java
// Illustration when nodes do not need onCompletion:
addToPendingCount(1);
new Child(this).fork();
// ... process local work
propagateCompletion();
```

This is an illustrative snippet inside a `CountedCompleter` class. **The correctness of the signal count must still be proven**. Changing `tryComplete` to `propagateCompletion` can drop an important combine step if `onCompletion` is performing reduction.

### `complete(T rawResult)`

`complete` can force a task to complete **regardless of the pending count**, invoke `onCompletion`, mark the task done, and participate in notifying the completer. It fits some "any first result is enough" algorithms, but is **not suitable as a replacement for `tryComplete`** when the goal is to wait for all children.

### `quietlyCompleteRoot()`

`quietlyCompleteRoot` marks the root complete without following the normal completion count path of all children. It can be valuable for early-result searches, but if the problem requires all children to finish, calling it early breaks the contract.

### `firstComplete()` and `nextComplete()`

These are traversal primitives for algorithms that need custom result combination/completion chains. Without a specific reason, using simple `tryComplete`/`onCompletion` is easier to prove correct.

## 16. onCompletion(caller): When to Aggregate Results

`onCompletion(CountedCompleter<?> caller)` can be overridden to combine child results once a node has received enough completion signals. `caller` represents whichever task triggered the completion traversal; it may be the node itself or its child/subtask.

Idea for map-reduce:

```java
@Override
public void onCompletion(CountedCompleter<?> caller) {
    // When the count protocol is correct, all awaited children have completed.
    // Combine data written by children into fields/result holders:
    result = left.result + right.result;
}
```

This is an **illustrative snippet**, requiring corresponding `result`, `left`, and `right` fields. It is not standalone and is unsafe if children were not properly registered, if child data is mutated outside the protocol, or if results have not been validly published.

**Main condition:** the parent cannot assume a child is done based solely on `getPendingCount()==0`. Timely callback execution depends on the completions that have been registered and have arrived. Adding a callback just because "count is currently 0" can aggregate prematurely if the count was under-registered.

Per the JavaDoc, when the pending count protocol is correct, result-combining actions in `onCompletion` can rely on the completion mechanism to access the data of completed subtasks. However, if shared data is also modified by a worker **outside the completion tree**, separate synchronization/ownership is needed.

## 17. Memory Visibility: Correct Completion Does Not Automatically Make All Data Thread-Safe

`CountedCompleter` helps establish completion relationships and task coordination, but should not be confused with a synchronized block surrounding every field.

### In the Demo

- Leaves update `sum` via `AtomicLong.addAndGet`, so no increments are lost due to interleaving.
- `leaves` uses `AtomicInteger.incrementAndGet`.
- Parent/child are linked via constructor `super(parent)` and `final` fields.
- After `ForkJoinPool.invoke(root)`, the caller observes the root as completed; normal updates within the properly registered subtree happen-before the completion the caller awaits.
- If a task outside the tree continues modifying `sum`, root completion does not automatically wait for that external task.

### When Partitioning Results by Child

Another approach is for each child to have its own result, write its result before calling `tryComplete()`, and then have the parent combine them in `onCompletion`. This approach often avoids multiple workers contending on a single atomic counter, but requires designing the result/parent links structure appropriately. Do not just change `sum` to a shared plain `long` and hope the pending count protects the addition.

### Happens-Before in ForkJoinTask

Java's concurrent task/future/join semantics provide the necessary memory ordering guarantees for publishing results when completion is properly managed. A caller calling `invoke()/join()` to wait for **a validly completed task** can use results prepared before completion according to the corresponding protocol.

**If the root is marked done prematurely**, the caller no longer has a valid completion barrier for the omitted children. You cannot invoke "invoke() guarantees visibility" to rescue an unregistered dependency graph.

## 18. How Do Pending Count and Thread Count Differ?

A root can have a pending count of 100 while the pool only has 4 workers. The count reflects **100 completion dependencies** per protocol, not 100 threads. `ForkJoinPool` uses work-stealing to process many tasks across a finite number of workers.

Conversely, a pool can have 32 workers while the root only has a pending count of 2 because it only waits for two direct children. Those two children might each wait for thousands of subtasks. The root counts **two direct completions**, not all grandchildren.

Do not write logic like:

```java
setPendingCount(pool.getParallelism()); // WRONG if the number of children differs from the number of workers.
```

This is an illustrative bug snippet, where `pool` is a `ForkJoinPool`. `parallelism` is a pool parameter, not the number of task dependencies.

Similarly, `ForkJoinPool.getQueuedTaskCount()` is an estimate of queued tasks, not to be used as a pending count. Do not rely on a queue size snapshot to deduce exactly how many children still need to complete.

## 19. Error Handling and Exceptional Completion

Normal completion of `CountedCompleter` and exceptional completion are two separate concerns that must be designed independently.

- If a child's `compute()` throws an exception, `ForkJoinTask`/`CountedCompleter` has its own exceptional completion semantics.
- `onExceptionalCompletion(Throwable ex, CountedCompleter<?> caller)` lets you customize exception propagation up to the completer per contract.
- If a child fails before sending a normal `tryComplete`, the parent should not just **wait forever for normal signals** without a failure propagation or cancellation policy.
- If you need to collect **all errors** from multiple children, you must define a shared error holder/aggregation and how other children continue or stop; do not assume default `CountedCompleter` saves every exception automatically.
- `quietlyCompleteRoot()` can stop some search algorithms early, but must not be abused to skip unfinished work if all children are required to complete.

An illustrative pattern:

```java
@Override
public boolean onExceptionalCompletion(
        Throwable ex, CountedCompleter<?> caller) {
    recordFailure(ex); // application-defined method
    return true;       // Allow propagation per contract
}
```

This is an illustrative method inside a `CountedCompleter` subclass. `recordFailure` must be thread-safe, bounded, and avoid throwing a new exception that masks the original cause. Read the JavaDoc to understand the boolean return value of the callback and avoid counting one failure across multiple levels as multiple independent failures.

**Important:** the runnable example above is simple addition that does not throw exceptions; failure logic was intentionally kept separate so a short sample would not turn into a hard-to-verify error/recovery framework.

## 20. Cancellation and Early Completion

If the caller calls `cancel()` on the root while children are still running, cancellation does not automatically guarantee that children stop immediately. If an algorithm uses `quietlyCompleteRoot()` when finding the first result, the root can become done even while other branches still have tasks in progress.

Therefore, distinguish three kinds of contracts:

1. **All-work completion:** the root is done only when all awaited children have completed. Use an accurate pending count and normal completion traversal.
2. **First-result completion:** the root can be done early once a good-enough result is found, but other tasks/cancellation and side effects must be managed carefully.
3. **Failure-fast completion:** the root ends abnormally when a child fails, while other children may need cancellation/cleanup.

The topic **"setting the pending count before fork"** specifically pertains to type 1. Do not silently turn it into first-result completion just to make `invoke` return early.

## 21. What If Work Dynamically Spawns More Children?

With dynamic trees, we often do not know all descendants in advance. There are two main approaches:

- **Register current batch of children:** compute n and `setPendingCount(n)` before forking the batch.
- **Incremental registration:** `addToPendingCount(1)` before each child `fork`, holding the self completion signal until the registration phase finishes.

If **a child can spawn more children** after its parent has reported its own completion, create a separate `CountedCompleter` subtree and have the parent wait for **that child's completion**; the child manages its grandchildren with its internal pending count.

**Do not let any other thread add a dependency to a parent after the parent could already complete.** That is no longer a simple traditional fork-join structure, and may require a different coordination protocol, such as `Phaser` or an ownership-based task registry, if the number of participants is dynamic.

### Example Reasoning: Task Stream Fan-Out

Suppose a node reads 5 work items and then forks 5 children. You need:

```text
discover items
setPendingCount(5)
fork item 1
fork item 2
fork item 3
fork item 4
fork item 5
tryComplete()
```

If you do not know the number of items before reading them all, do not set count to 0 and fork haphazardly. Either read the whole list first (if memory allows), or use `addToPendingCount(1)` **before each fork** and keep the registration phase from completing too early.

## 22. Testing for Races: Do Not Verify with a Lucky Execution Schedule

A `CountedCompleter` program with a wrong count can run correctly thousands of times if the parent happens to call `setPendingCount` before workers process the child. Therefore, testing needs two layers:

### A. Checking Counting Logic via Invariants

For each internal node:

1. How many completions need to be awaited?
2. Which children do they come from?
3. Does the parent send a self completion signal?
4. Are signals sent exactly once?
5. Is the count registered **before any child can send a signal**?
6. Before all dependencies are complete, is there any path using `complete`/`quietlyCompleteRoot` to mark done early?
7. If a child fails, what is the exceptional completion path?

Tests cannot replace answering these questions.

### B. Controlled Stress Testing

- Use empty inputs, single-element, two-element, non-power-of-2 sizes, and thousands of elements.
- Run on `ForkJoinPool(1)`, `ForkJoinPool(2)`, and larger worker counts to vary interleaving levels.
- Ensure the total number of leaves processed matches the element count and the sum/reduce result is correct.
- Insert `CountDownLatch` or `Phaser` to simulate a child finishing earlier than the parent's next step, without turning the test into a deadlock.
- Use `ForkJoinTask.get(timeout, unit)` so a hanging test can fail by deadline; do not use `Thread.sleep()` as proof of completion.
- When testing wrong-count cases, run them in a harness with timeouts and cancellation; **do not put intentional bugs into production**.

### Why Is the "Late Pending Count" Bug Hard to Spot in Tests?

Because `fork` may simply enqueue the child and the current worker keeps running. If the parent immediately calls `setPendingCount` right after `fork`, on a particular machine/load the parent may win the race. Yet another idle worker can easily steal the child and finish it first. Correctness guarantees must be independent of who runs first.

## 23. Observing ForkJoinPool and Task Completion

When the system makes no progress, inspect:

- `ForkJoinPool.getActiveThreadCount()` and `getRunningThreadCount()`: snapshots/estimates of worker activity, not proof that the root is done.
- `getQueuedTaskCount()`: estimate of tasks sitting in queues, not the number of incomplete dependencies.
- `getStealCount()`: approximate amount of work stealing per API, useful when studying load balance.
- `ForkJoinTask.isDone()`, `isCompletedNormally()`, `isCompletedAbnormally()`: task lifecycle.
- `CountedCompleter.getPendingCount()`: remaining completion signals per the task's protocol.
- `onCompletion` callback: where results are combined after dependencies, but only meaningful if pending bookkeeping is correct.
- Exception outcome of `join`/`get`: distinguish failure, cancellation, and timeout.

A JVM diagnostic command:

```bash
jcmd <PID> Thread.print -l
```

Replace `<PID>` with the actual process PID. A thread dump shows what workers are running, waiting, or blocked elsewhere; it does not record the entire history of completion counts. When debugging rare bugs, add selective event tracing rather than logging every task at high frequency and causing contention.

**Do not expect a thread dump to automatically point out "forgot setPendingCount before fork".** That is a protocol bug in source code. Some workers may already be idle while root pending > 0 and the caller is still waiting.

## 24. Performance: Fork Large Enough and Avoid Unnecessary Global Atomics

The pattern of splitting every single element into a leaf task in the demo is **to illustrate completion**, not to optimize performance. With large data, creating millions of `CountedCompleter` instances can incur allocations, queue operations, and contention.

Common optimizations:

- Split down to a sufficiently large **grain size**, e.g., each leaf processes a chunk of 1,000 elements instead of 1 element, depending on the workload.
- Use the **fork one branch, process the other directly** technique to reduce task count.
- Have each leaf hold a local result and combine in `onCompletion` instead of all leaves contending on one `AtomicLong`.
- Avoid unnecessary blocking I/O on `ForkJoinPool` workers; work-stealing is better suited for splittable computations.
- Profile allocation, CPU, queue/steal counts, and tail latency before deciding on tuning.
- Do not sacrifice correctness to save one `setPendingCount` call; a premature completion race can be very hard to detect.

### When Is CountedCompleter Not Needed?

If a simple algorithm returns a result by forking a child and joining in the parent, `RecursiveTask<V>` may be easier to understand. If you only need to run N independent tasks and wait for all of them, `ExecutorService.invokeAll`, `CompletableFuture.allOf`, or `CountDownLatch` may fit depending on data types and lifecycle.

Choose the primitive that expresses dependencies most clearly; do not use `CountedCompleter` just because "no join is needed" without a good reason.

## 25. Common Mistakes and Fixes

1. **Forking first and setting pending count afterward.** A child can complete before being registered; set the count before any fork.
2. **`setPendingCount(2)` for two children but forgetting self `tryComplete`.** Two signals only decrement 2→1→0; completion is not triggered yet.
3. **`setPendingCount(1)` in the pattern of forking two children + self signal.** The parent can complete while a child is still running.
4. **`setPendingCount(3)` for two children + self signal.** The parent can sit at pending 0 and wait forever due to a missing final completion-triggering signal.
5. **Using `getPendingCount()==0` to assert done.** You need `isDone`/completion callback and a correct protocol.
6. **Using pool parallelism as the pending count.** Pending counts logical completions, not worker threads.
7. **A child calling `tryComplete` twice.** Can cause premature completion or trigger callbacks erroneously.
8. **Child lacking the right completer.** Signal does not reach the intended parent, and the root may hang.
9. **Calling `setPendingCount` again after children have started completing.** Can overwrite atomic decrements and lose progress.
10. **Forgetting the last child must still signal even with no data.** An empty subtree also needs a completion path if it was registered.
11. **Using `complete()`/`quietlyCompleteRoot()` to patch a wrong-count deadlock.** Can report done when work is unfinished.
12. **Assuming `invoke` automatically waits for every task forked in the JVM.** `invoke` only waits for the root `ForkJoinTask` per the root's completion protocol.
13. **Assuming `CountedCompleter` makes `long++` thread-safe.** Shared mutable results still need atomics/locks/partitioned ownership.
14. **Not distinguishing normal vs. exceptional completion.** A child throwing may require failure propagation/cancellation policy.
15. **Using `Thread.sleep` to force the parent to run before the child.** Provides no guarantee, only alters timing.
16. **Reading `onCompletion` and assuming the parent thread runs the callback.** The callback can be triggered on the worker completing the last signal, not necessarily the thread that originally ran the parent.
17. **Assuming every child needs `pendingCount=1`.** Leaves can use pending=0 and `tryComplete` to propagate the signal; count is per-node state.
18. **Seeing pending 0 and calling `addToPendingCount` after completion.** You cannot revive a root already marked done by incrementing the count late.
19. **Off-by-one optimization without adjusting signaling code.** The count must match the variant; do not copy a single `setPendingCount` line in isolation.
20. **Creating millions of tiny tasks and assuming work stealing is always faster than a sequential loop.** Grain size and overhead must be measured.
21. **Assuming child completion means all grandchildren are done without a protocol.** A child must manage its subtree and signal the parent at the right time.
22. **Using `CountedCompleter` as a distributed job coordinator.** It manages task completion within a JVM; there is no durability/replay on process crash.

## 26. CountedCompleter Algorithm Review Checklist

Before merging code:

- **Dependency tree:** which children have the current node as completer? Are any parent/child links wired wrongly?
- **Signals:** how many completion signals will each node receive?
- **Count:** does initial/set/add pending count match the number of signals and self-signal?
- **Ordering:** are all pending children to be awaited registered **before any fork**?
- **Tail-call variant:** did you change the fork/direct-compute structure while forgetting to update count/self `tryComplete`?
- **Leaf:** does every base-case branch, including an empty array, call `tryComplete` exactly once?
- **Combining:** does `onCompletion` run after all required child data is ready? Does the result holder have shared mutations outside the tree?
- **Exceptions:** when a child throws, how does the root handle failure, and must other branches be cancelled?
- **Cancellation:** when the caller cancels the root, do children still have running side effects?
- **Memory:** is data published safely, avoiding races independent of the completion count?
- **Liveness:** can a missing signal leave pending count positive, or at 0 with the root not done?
- **Testing:** empty/small/odd/large inputs, different parallelism levels, timeouts, stress, and asserted invariants?
- **Monitoring:** are metrics for queue/worker activity and root done/exception status clear?
- **JDK version:** does the sample run on JDK 17; if using newer APIs, note the version.

## 27. Self-Check Questions and Answers

**Q1.** Why must `setPendingCount` be called before `fork`?  
**A:** After `fork`, a child can be processed by another worker and call `tryComplete` immediately. If the parent still has pending 0, completion may propagate prematurely before the dependency is registered.

**Q2.** If a parent forks two children and then calls `tryComplete` on itself in the simple pattern, what should pending be initialized to?  
**A:** 2. There are 3 signals in total (the parent and 2 children); the first two signals decrement 2→1→0, and the third triggers completion.

**Q3.** Why doesn't `onCompletion` necessarily run immediately when pending decrements from 1 to 0?  
**A:** When `tryComplete` sees a non-zero count, it decrements and returns; a subsequent invocation must observe count 0 to execute the callback.

**Q4.** When `getPendingCount()==0`, can you declare the root has `isDone()==true`?  
**A:** No. Count 0 is a protocol state; task completion must still be properly triggered.

**Q5.** Does `CountedCompleter` automatically track the list of forked children?  
**A:** No. Pending is an integer, not attached to task IDs. The algorithm author manages completer links and signals.

**Q6.** If there are 8 leaves but `ForkJoinPool` only has 2 workers, should the root set pending count to 8 or 2?  
**A:** Neither can be deduced from those two numbers. The root typically counts its **direct children**, e.g., 2; each child manages its own subtree. Pending is not parallelism.

**Q7.** With n=0 children and default pending 0, how does the root complete normally?  
**A:** After processing the node's work (which may have no data), call `tryComplete()` to trigger the callback/root completion.

**Q8.** With two children, why can the `right.fork()`/`left.compute()` variant use pending 1?  
**A:** The parent does not self-`tryComplete` in the internal branch; it waits for one forked branch and the completion signal from the directly computed branch. Two signals are enough for count 1→0 and then the callback.

**Q9.** Can calling `setPendingCount(2)` after a child has already reported completion fix the race?  
**A:** No. Completion may have already propagated to the root, or the new count overwrites the decrement. Registration must happen before publication.

**Q10.** Is `pool.invoke(root)` guaranteed to wait for every `ForkJoinTask` in the pool?  
**A:** No. It waits for the root according to the root's lifecycle. If the dependency graph is incomplete, the root may be done early even while other tasks are still running.

**Q11.** Is a shared `long sum` updated by leaves with `sum += value` safe just because the pending count is right?  
**A:** No. Pending coordinates completion; it does not make concurrent updates atomic. Use `AtomicLong` or local results and combine.

**Q12.** When `onCompletion` is called, is the thread executing the callback guaranteed to be the parent thread?  
**A:** No. The callback may run on the last thread that triggers the completion traversal.

**Q13.** Is `complete(T)` the same as `tryComplete`?  
**A:** No. `complete` can finish a task regardless of pending count, suitable for early-completion in some algorithms but wrong for all-work completion if used prematurely.

**Q14.** How does `propagateCompletion` differ from `tryComplete`?  
**A:** It uses completion traversal but skips `onCompletion`; suitable when no result-combining callback is needed.

**Q15.** When a child is undercounted, what outcomes can occur?  
**A:** Root completes early, `onCompletion` aggregates incomplete data, caller's `invoke` returns early, and some children are still running/writing state.

**Q16.** When overcounted or missing the self signal, what outcomes can occur?  
**A:** The root does not receive an invocation observing pending 0, so `join`/`invoke` can wait indefinitely.

**Q17.** Why is a stress test passing many times not enough to prove the count is right?  
**A:** Thread scheduling may only rarely let a child finish before the parent sets the count. You must prove register-before-fork for all valid interleavings.

**Q18.** Can another thread add children after the root is already done?  
**A:** Code could be written to do so, but it is **not part of a valid completion protocol** for an already-done root; a different coordination design is needed instead of incrementing pending late.

## 28. References

- [Java SE 17 — CountedCompleter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html): specification of pending count, `setPendingCount`, `addToPendingCount`, `tryComplete`, and the **"must set pending count before fork"** example.
- [Java SE 17 — ForkJoinTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinTask.html): `fork`, `join`, `invoke`, lifecycle/exception handling.
- [Java SE 17 — ForkJoinPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): work stealing, `invoke`, parallelism, and monitoring.
- [Java SE 17 — RecursiveTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveTask.html): Fork/Join task type that returns a result.
- [Java SE 17 — RecursiveAction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/RecursiveAction.html): Fork/Join task type that does not return a value.
- [Java SE 17 — AtomicLong](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicLong.html): atomic addition for shared counters.
- [Java Language Specification `17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): data races, happens-before, and memory ordering.

**Final takeaway:** `fork()` can cause a child to run and finish **before the parent's next statement**. Therefore, **registering the pending count before forking** is not an optimization trick—it is a correctness condition of `CountedCompleter`. With the easy-to-understand pattern `setPendingCount(n); fork n children; tryComplete();`, the count and signals must match; with optimized variants, the signal count must be re-proven. Only then do `onCompletion` and `invoke(root)` accurately represent "all dependencies have completed".