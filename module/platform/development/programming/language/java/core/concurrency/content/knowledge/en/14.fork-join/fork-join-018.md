# onExceptionalCompletion(): Handling and Propagating Exceptions in CountedCompleter

## 1. Why does CountedCompleter have an exception callback?

`CountedCompleter<T>` is a form of `ForkJoinTask<T>` in `java.util.concurrent`, designed for tree-based task-splitting algorithms that signal completion via a **completer chain**. Each task can link to a parent `CountedCompleter` and has a **pending** count to manage normal completion. Unlike the typical `RecursiveTask` pattern that forks and joins each branch, `CountedCompleter` allows branches to call `tryComplete()` to advance the tree's completion process without forcing the parent to join each child directly.

There are two distinct event flows:

- **Normal completion**: branches finish their work and call `tryComplete()`; when conditions are met, `onCompletion(caller)` may execute, and then completion proceeds to the parent completer.
- **Exceptional completion**: `compute()` throws an exception out, or `completeExceptionally(Throwable)` is called on the task. In that case, Java uses **`onExceptionalCompletion(Throwable ex, CountedCompleter<?> caller)`** to handle the error callback and decide whether the error propagates up to the parent completer.

In real-world applications, a failure in a small leaf may need to fail the entire operation. Conversely, some problems allow ignoring certain failed leaves. This callback provides a **control point for exception propagation**. However, it does not replace data recovery, pending count management, sibling cancellation, or cleanup.

**Scope:** this lesson covers Java Concurrency / Fork/Join in general, not tied to any other framework's API or lifecycle.

## 2. Exact signature and contract

The method has the following signature:

~~~java
@Override
public boolean onExceptionalCompletion(
        Throwable ex, CountedCompleter<?> caller) {
    // Can record the error or update thread-safe state.
    return true;
}
~~~

This is an **illustrative snippet inside a subclass**; it must be paired with `extends CountedCompleter<...>` and an appropriate `compute()` method to form a standalone program.

| Component | Meaning |
|---|---|
| `ex` | The `Throwable` of the current failure path; the exception may pass through multiple completers |
| `caller` | The task that triggered the callback at the current link; may be `this` or a child task |
| `this` | The `CountedCompleter` currently handling exceptional completion |
| `return true` | Allows the error to continue propagating to the parent completer, **if a parent exists and has not yet completed** |
| `return false` | Blocks exception propagation from this link to the parent completer |
| Default implementation | Performs no additional handling, **returns `true`** |

**Key point:** when the callback is invoked, the current task is already in the **completed abnormally** state. Returning `false` **does not turn it into a success**, does not clear the exception that occurred, does not automatically decrement the pending count, and does not undo side effects.

If `this` has no parent completer (the root), returning `true` has no parent branch left to propagate to. If the parent has already completed normally, propagation also has no retroactive effect to change the parent's state. Do not interpret `true` as "the root always fails"; the completer chain and the state of each node still matter.

### `caller` is not always `this`

At the leaf where `compute()` throws an exception, the callback may receive `caller == this`. When the exception is propagated up to a parent, `caller` can be **the child that forwarded the error**. Thus, the two parameters `this` and `caller` let you distinguish between "the node being marked as failed" and "the node that triggered the error propagation."

Do not assume `caller` is always the original leaf at every level of the tree; each link typically receives the task directly below it. If you need to preserve the original error identity across multiple levels, manage separate metadata in a thread-safe manner.

## 3. What cases trigger the callback?

| Case | Is `onExceptionalCompletion` called? | Explanation |
|---|---|---|
| `compute()` throws `RuntimeException` out | Yes | The task is recorded as exceptional |
| `completeExceptionally(ex)` on an incomplete task | Yes | Explicitly transitions the task into the error path |
| `compute()` catches the error, uses a valid fallback, then calls `tryComplete()` | No | The task finishes normally according to the recovered logic |
| Normal `tryComplete()` | No | Follows `onCompletion()` |
| `cancel(true)` or `cancel(false)` | Does not trigger the error callback like the first two cases | Cancellation has its own state mechanism |
| Another task in the pool fails but does not belong to this completer chain | Not due to that error | No propagation across a non-existent relationship |

The exception contract of `CountedCompleter` does not mean "any `throw` statement appearing anywhere." If the code catches and fully recovers before returning normally, the callback has no reason to run.

Additionally, `ForkJoinTask` does not enforce which thread executes the callback at any given moment; do not rely on log ordering across multiple workers to infer causal ordering of independent tasks.

## 4. Error propagation flow through the completer tree

Suppose we have a three-level tree:

~~~text
                     ROOT
                       |
                    BRANCH
                       |
                      LEAF
             compute() throws an exception
~~~

If every callback returns `true` and the parent has not yet completed:

1. LEAF completes abnormally; `LEAF.onExceptionalCompletion(ex, LEAF)` is called.
2. LEAF returns `true`, so BRANCH is completed abnormally by the propagated error; `BRANCH.onExceptionalCompletion(ex, LEAF)` is called.
3. BRANCH returns `true`, so ROOT is marked abnormal if ROOT has not yet finished; ROOT's callback is called with `caller` being BRANCH in this propagation path.
4. A thread waiting on ROOT via `pool.invoke(root)`, `root.join()`, or `root.get()` can receive the error according to the respective API's contract.

If BRANCH returns **`false`**, ROOT is not automatically marked exceptional by this branch. LEAF and BRANCH **still fail**. The error is not "handled and resolved" just because the callback returned `false`.

**Concurrency note:** if the parent has already completed before the exception arrives, propagation cannot change the parent's result afterward. Siblings that have already been forked may continue executing even when ROOT fails.

### Difference between failure propagation and normal completion

`tryComplete()` is the mechanism that uses the pending count for **normal** completion; an exception from a child does not automatically call `tryComplete()` on behalf of that child. Therefore, when blocking propagation with `false`, the parent may lose both the **error signal** and the **normal completion signal**. If the parent still has a non-zero pending count, a caller waiting on the root may **hang indefinitely**.

To legitimately ignore errors, you must explicitly design how missing results are recorded, update completion accounting, and bring the root to a clear terminal state. Never replace `true` with `false` without defining a termination condition.

## 5. Java 17 Example: directly comparing true and false

The program below creates a **Parent** and a **Child** linked via `super(parent)`. Only **Child is submitted to the ForkJoinPool**; Parent serves as an object to observe propagation state. Child always throws `IllegalArgumentException`, and its callback returns `true` or `false` across iterations.

This setup intentionally **does not submit Parent to the pool**, avoiding a self-inflicted hang in the example when `false` is chosen. In a real system, a root with its own work and pending count needs a complete completion strategy.

Save the file as **ExceptionalPropagationDemo.java**:

~~~java
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class ExceptionalPropagationDemo {
    static final class Parent extends CountedCompleter<Void> {
        final AtomicBoolean hookCalled = new AtomicBoolean();
        final AtomicBoolean callerIsChild = new AtomicBoolean();
        Child child;

        @Override
        public void compute() {
            tryComplete();
        }

        @Override
        public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            hookCalled.set(true);
            callerIsChild.set(caller == child);
            return true;
        }
    }

    static final class Child extends CountedCompleter<Void> {
        final boolean propagate;
        final AtomicBoolean childHookCalled = new AtomicBoolean();
        final AtomicBoolean callerIsSelf = new AtomicBoolean();

        Child(Parent parent, boolean propagate) {
            super(parent);
            this.propagate = propagate;
        }

        @Override
        public void compute() {
            throw new IllegalArgumentException("invalid item");
        }

        @Override
        public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            childHookCalled.set(true);
            callerIsSelf.set(caller == this);
            return propagate;
        }
    }

    public static void main(String[] args) throws Exception {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            for (boolean propagate : new boolean[]{true, false}) {
                Parent parent = new Parent();
                Child child = new Child(parent, propagate);
                parent.child = child;
                try {
                    pool.invoke(child);
                } catch (IllegalArgumentException expected) {
                    System.out.println("child exception="
                            + expected.getClass().getSimpleName());
                }

                if (propagate) {
                    try {
                        parent.get(2, TimeUnit.SECONDS);
                    } catch (ExecutionException expected) {
                        System.out.println("parent get="
                                + expected.getClass().getSimpleName());
                    }
                }

                System.out.println("propagate=" + propagate);
                System.out.println("child abnormal=" + child.isCompletedAbnormally());
                System.out.println("child hook called=" + child.childHookCalled.get());
                System.out.println("child caller is self=" + child.callerIsSelf.get());
                System.out.println("parent abnormal=" + parent.isCompletedAbnormally());
                System.out.println("parent hook called=" + parent.hookCalled.get());
                System.out.println("parent caller is child=" + parent.callerIsChild.get());
                System.out.println("parent done=" + parent.isDone());
            }
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac ExceptionalPropagationDemo.java
java ExceptionalPropagationDemo
~~~

Output:

~~~text
child exception=IllegalArgumentException
parent get=ExecutionException
propagate=true
child abnormal=true
child hook called=true
child caller is self=true
parent abnormal=true
parent hook called=true
parent caller is child=true
parent done=true
child exception=IllegalArgumentException
propagate=false
child abnormal=true
child hook called=true
child caller is self=true
parent abnormal=false
parent hook called=false
parent caller is child=false
parent done=false
~~~

**Branch-by-branch analysis:**

- **True:** `child` still fails and the `child` callback runs; the error is propagated to `Parent`, and `Parent`'s callback runs with `caller == child`. `Parent` completes abnormally. When waiting with `parent.get(timeout)`, the caller receives `ExecutionException`, which is the checked wrapper per the `Future` API.
- **False:** `child` **still** has `isCompletedAbnormally() == true`, while `parent` does not receive exceptional completion from `child`, so `parent.isDone() == false` in this example. We do not call `parent.get()` on this branch.
- `pool.invoke(child)` delivers the unchecked exception to the caller; the message/stack trace chain may differ if the exception is transferred across workers, so the example checks the **exception type** rather than comparing the full message.

**Do not mechanically copy this Parent as a production task:** `Parent.compute()` is defined so the class is complete and valid, but it is not executed. Real-world problems must design pending counts, child handling, and root completion consistently.

## 6. Java 17 Example: throwing, recovery, completeExceptionally, and cancel

The following cases clarify that the callback only reflects the **exceptional state path**, not every exception that ever appeared in the method body.

Save the file as **CompletionCallbackDemo.java**:

~~~java
import java.util.concurrent.CountedCompleter;
import java.util.concurrent.ForkJoinPool;

public class CompletionCallbackDemo {
    static final class Probe extends CountedCompleter<Void> {
        private final String mode;
        private int exceptionalCalls;
        private int normalCalls;

        Probe(String mode) { this.mode = mode; }

        @Override
        public void compute() {
            if (mode.equals("throw")) {
                throw new IllegalStateException("failed");
            }
            if (mode.equals("recover")) {
                try {
                    throw new IllegalArgumentException("bad input");
                } catch (IllegalArgumentException handled) {
                    // A specific fallback policy is in place.
                }
            }
            tryComplete();
        }

        @Override
        public void onCompletion(CountedCompleter<?> caller) {
            normalCalls++;
        }

        @Override
        public boolean onExceptionalCompletion(
                Throwable ex, CountedCompleter<?> caller) {
            exceptionalCalls++;
            return true;
        }
    }

    public static void main(String[] args) {
        ForkJoinPool pool = new ForkJoinPool(2);
        try {
            Probe throwing = new Probe("throw");
            try {
                pool.invoke(throwing);
            } catch (IllegalStateException expected) {
                System.out.println("throw: abnormal="
                        + throwing.isCompletedAbnormally()
                        + ", exceptional hook=" + throwing.exceptionalCalls);
            }

            Probe recovered = new Probe("recover");
            pool.invoke(recovered);
            System.out.println("recover: normal hook=" + recovered.normalCalls
                    + ", exceptional hook=" + recovered.exceptionalCalls);

            Probe manual = new Probe("idle");
            manual.completeExceptionally(
                    new IllegalStateException("manual"));
            System.out.println("manual: abnormal=" + manual.isCompletedAbnormally()
                    + ", exceptional hook=" + manual.exceptionalCalls);

            Probe cancelled = new Probe("idle");
            cancelled.cancel(true);
            System.out.println("cancel: cancelled=" + cancelled.isCancelled()
                    + ", exceptional hook=" + cancelled.exceptionalCalls);
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Run commands:

~~~bash
javac CompletionCallbackDemo.java
java CompletionCallbackDemo
~~~

Stdout:

~~~text
throw: abnormal=true, exceptional hook=1
recover: normal hook=1, exceptional hook=0
manual: abnormal=true, exceptional hook=1
cancel: cancelled=true, exceptional hook=0
~~~

In `throw`, the task throws an exception and the exceptional hook is called. With `recover`, the example intentionally catches the exception and continues to `tryComplete()`, so `onCompletion` runs while `onExceptionalCompletion` does not. In real applications, only do this when **a genuinely valid fallback exists**; catching an exception and ignoring it is not a data-repair mechanism.

In `manual`, `completeExceptionally` is called on a task not yet submitted to the pool, still triggering the error callback path. In `cancel`, the task is cancelled via the cancellation mechanism, without invoking the exceptional hook as shown in the example.

## 7. onCompletion and onExceptionalCompletion do not replace each other

| Property | `onCompletion(caller)` | `onExceptionalCompletion(ex, caller)` |
|---|---|---|
| Execution path | Normal completion from the completion mechanism | Abnormal completion due to an error |
| Role | Combine results, update valid completion steps | Record the error, decide propagation |
| Return type | `void` | `boolean` |
| Error parameter | None | `Throwable ex` |
| Can propagate to parent? | Via normal completion mechanism | Via exceptional completion if the callback returns `true` and the parent is still eligible |
| Automatically rolls back or cancels siblings? | No | No |

`onCompletion` is called during normal completion per the `tryComplete()` or `complete(...)` contract; `caller` can be used to identify which branch completed. `onExceptionalCompletion` is called on the error path, and the `ex` parameter lets you inspect the cause. Both callbacks should be **short, non-blocking, and avoid throwing unnecessary new exceptions**, as they may run in a Fork/Join worker context.

If `onCompletion` throws an exception, completion may enter the abnormal path. Therefore, result-combining logic in the normal callback also needs testing and exception management.

## 8. Pending count and why returning false can hang the root

`CountedCompleter` only provides the primitives for programmers to design completion state:

| API | Meaning |
|---|---|
| `setPendingCount(int count)` | Sets the task's pending count |
| `addToPendingCount(int delta)` | Atomically adjusts the pending count |
| `tryComplete()` | Decrements pending when non-zero; when zero, handles normal completion and continues up the chain |
| `onCompletion(caller)` | Callback for the normal path |
| `propagateCompletion()` | Propagates normal completion without running `onCompletion` |
| `complete(T result)` | Completes the task using the special API |
| `completeExceptionally(ex)` | Completes the task along the exception path |

Pending count is **not a thread count**, nor is it a task count automatically maintained by the pool. If a leaf throws an exception before `tryComplete()` and the hook returns `false`, the parent **does not have its pending count decremented automatically** and **is not automatically marked exceptional**. If the root is still waiting for a signal from that leaf, `join()`, `get()`, or `invoke(root)` may wait forever.

**Do not apply a quick fix by arbitrarily calling `tryComplete()` on every failed branch.** A branch that failed to provide a valid result could cause the root to report success with missing data; other siblings might also still be running. If the business logic tolerates partial failures, you need explicit completion rules—for example, storing `Result<value,error>` in an aggregator, updating pending exactly once, applying an overall success condition, and setting a deadline.

Unless you intentionally build complex recovery, keeping the default `return true` is usually easier to reason about: a leaf's failure is reported to an active root rather than turning into an unexplained pending root.

### Root completed before the error propagated to it

A completer that has already completed normally **does not have its result retroactively changed** by an exception raised in a late child. This is not a callback bug; it reflects that the algorithm signaled completion before ensuring all required branches were done. Pending count design must prevent premature success.

## 9. Root failure does not guarantee siblings stop running

Suppose two children are forked together. Child A throws an exception, and propagation succeeds in marking the root abnormal. Child B may have already started processing an array or may still be running. **An exceptional root does not automatically cancel Child B**, does not wait for it to clean up, does not roll back side effects, and does not guarantee shared data regions are safe to reuse.

For algorithms with side effects, additional design is required:

1. **Cooperative stop signal** (e.g., `AtomicBoolean`) for other workers to check at safe points.
2. **In-flight task tracking** or a mechanism to signal cleanup completion, especially before reusing data.
3. **Resource limit and deadline policies**, avoiding continuous forking after an error has already occurred.
4. **Consistency management**, such as undo, idempotency, transactions, or compensation when external side effects are involved.
5. **Contextual error recording**, avoiding counting each callback at leaf/parent/root as independent business errors.

**The callback is not a tool for managing the entire lifecycle of the tree.** It only decides a single link in exception propagation. If you need to collect all sibling errors, you must store them in a separate thread-safe structure; a root may complete abnormally on the first error before others arrive.

## 10. Multi-level error handling strategies

A clear error design distinguishes three categories:

**Category A — Fail-fast:** any critical leaf failure fails the entire root. Keep `return true` and handle the exception from the root at the caller. To reduce wasted work, set a cooperative stop flag for siblings and wait for cleanup via a dedicated mechanism.

**Category B — Defined partial success:** failures in some branches are allowed, but missing results must be recorded and their completion accounted for by convention. Consider catching/recovering exceptions **inside `compute()`** when a valid fallback exists, or using a clear coordinator; `return false` is only a small part of the policy, not the whole solution.

**Category C — Bounded retry:** transient errors can be retried. Do not retry infinitely inside a worker callback. Bound the retry count, backoff, deadline, and concurrency level, ensuring no duplicate side effects are created. If a retry succeeds inside `compute()`, the task can complete normally; if retries are exhausted, let the error escape and propagate according to policy.

Tasks submitted to `ForkJoinPool.commonPool()` share resources with other components; avoid blocking callbacks or long retries that occupy workers. If you need dedicated ownership/lifecycle control, use a `ForkJoinPool` created for that component and manage shutdown when no tasks remain.

## 11. Handling Throwable, caller, exception wrappers, and cancellation

**Throwable:** the callback receives `Throwable ex` and can inspect the cause at each level. If an exception is transferred across workers, the displayed message or stack trace may differ due to the forwarding mechanism, so tests should verify the exception type/state and key context rather than relying on log order or exact stack trace text.

**Caller:** distinguish the current task (`this`) from the task that triggered the callback. The first example uses identity comparison to verify `caller == this` at the leaf and `caller == child` at the parent.

**get/join/invoke:** per the `Future` contract, `get()` on an exceptional task may throw a checked `ExecutionException`, whereas `join()/invoke()` typically propagate the task's unchecked exception. Do not treat an exception from the root as a `null` result or a silent success. Exceptions from other nodes may be recorded independently before reaching the root.

**Cancellation:** cancelling a task via `cancel(true)` is not a command to forcibly kill a worker. For `ForkJoinTask`, the interrupt flag does not carry the same thread-cancellation guarantees as some other implementations; the algorithm owner should maintain cooperative cancellation state. Cancelling an internal node does not automatically cancel the entire tree or trigger the exceptional callback as a `compute()` error.

**An exception does not necessarily trigger a callback at every node:** if a node has already completed, if an intermediate callback returns `false`, or if no completer exists, propagation stops. Record the original error separately if full auditing is a system requirement.

## 12. Testing errors and completion

| Test case | Expected observation |
|---|---|
| Leaf throws, callback returns `true` | Leaf is abnormal; uncompleted parent receives exceptional completion |
| Leaf throws, callback returns `false` | Leaf is still abnormal; parent does not automatically receive the error from leaf |
| Child fails and parent is still pending | Do not leave root `get()` waiting indefinitely when blocking propagation |
| Parent is already done before propagation | Do not assume the exception changes the parent's state |
| `compute()` catches error and falls back | Normal completion is called; exceptional hook does not run |
| `completeExceptionally` on an unfinished task | Exceptional callback runs per contract |
| `cancel` on `CountedCompleter` | Do not confuse cancelled state with the exceptional hook |
| Two siblings fail simultaneously | Have a way to collect/dedupe errors if business logic requires it |
| Root is exceptional, sibling still running | Cleanup and data synchronization are properly designed |
| Hook runs on worker | Non-blocking, no new contention introduced |

When testing concurrency, prefer **`CountDownLatch`**, timeouts, and `ForkJoinTask` state checks rather than just `Thread.sleep()` and guessing execution order. In particular, an exceptional `Future` does not guarantee that all other tasks in the pool have finished.

## 13. Common mistakes

- **Assuming `return false` swallows the child's exception:** the child is still abnormal, and a caller waiting on the child still receives the error.
- **Assuming `return true` always makes the root fail:** propagation only reaches completers that have not yet completed and are still linked.
- **Using the exceptional hook to call `tryComplete()` without a policy:** the parent may report success despite corrupted or missing data.
- **Forgetting pending count when allowing partial failure:** the root may wait forever.
- **Thinking `caller` is always `this`:** loses the error context from child tasks.
- **Logging the same exception at every level as separate errors:** causes duplicate metrics and alerts.
- **Assuming an exceptional root means all siblings have been cancelled:** other branches may continue running.
- **Catching and ignoring all exceptions in `compute()` and reporting success:** leads to inconsistent data.
- **Putting blocking I/O or long retries in the hook:** occupies Fork/Join workers and degrades work stealing.
- **Ignoring `ExecutionException` from `get()` and unchecked exceptions from `join()/invoke()`:** real errors are not properly reported to the caller.

## 14. Checklist and conclusion

Before overriding the callback, determine **which errors should propagate to the root**, **which ones may be recovered**, **what pending work the parent still has**, **who handles running siblings**, and **how the caller will be notified of failure**. A method returning a single boolean cannot replace an error and completion policy for the entire tree.

**Remember:** `onExceptionalCompletion(ex, caller)` is the callback for the **exceptional completion** branch; `return true` allows propagating the error to an uncompleted parent completer, while `return false` prevents that propagation step. **Neither turns a failed task into a successful one.** If you block propagation, you must have an intentional completion/root-cleanup mechanism; otherwise, the tree can hang waiting.

Official API reference: [CountedCompleter – Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountedCompleter.html).
