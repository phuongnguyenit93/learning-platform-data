# Cascading Cancellation Signals Across Java Concurrency Processing Chains

## 1. Problem Statement and Learning Outcomes

A request is not necessarily processed by a single thread. A caller may submit a `Callable` to an `ExecutorService`; the parent task then creates child tasks; a child calls a `BlockingQueue`, waits on I/O, runs CPU work, or writes results to another system. When the caller times out or the user cancels, the question is not just **"was `cancel(true)` called?"**, but **"did the cancellation signal reach each layer properly, and did the task actually stop, clean up, or commit according to policy?"**

~~~text
Caller / Service shutdown
          |
          v
Coordinator (Parent Future) ---> Child A (CPU / queue)
          |                   \
          |                    +-- checkpoint / interrupt
          v
     Child B (I/O) ----------> timeout / close / remote request
          |
          v
     Publish / commit -------> state generation, idempotency
          |
          v
        Cleanup -------------> locks, permits, connections
~~~

There are two flows of information to distinguish:
- **Top-down:** cancellation request, deadline, interrupt, cancellation token, and the stop policy for each child.
- **Bottom-up:** result, exception, state of the worker actually exiting the task, completed cleanup, and whether the business operation committed or not.

After this lesson, you will be able to:
1. Distinguish **cancellation intent**, **interrupt status**, **Future cancelled**, **deadline**, **worker exited**, and **business finality**.
2. Propagate cancellation from a parent down to the child tasks **owned by the parent**, instead of assuming cancelling the parent automatically propagates across the entire tree.
3. Correctly use `InterruptedException`, `Thread.currentThread().isInterrupted()`, `Future.cancel(true)`, tokens, and timeouts.
4. Identify boundaries where interruption cannot interrupt on its own, such as certain I/O operations, `synchronized` monitor acquisition, or side effects in external systems.
5. Prevent lost cancellation, orphan tasks, resource leaks, late results, and duplicate commits on retry.
6. Run standalone examples on **Java 17+** with stdout and explain why the output behaves as it does.

**Scope:** Java SE and Java concurrency in general. Spring-specific mechanisms are not covered here because Spring-related topics have their own chapter.

## 2. Distinguishing the Layers of Cancellation

| Layer or state | Meaning | What must not be inferred |
| --- | --- | --- |
| Caller requested cancellation | The user/caller wants to abort the work | The task has stopped |
| Future.cancel(true) accepted | The Future accepted transitioning to the cancelled state, and the implementation may request interrupting the runner | All children have stopped or side effects have been rolled back |
| Thread interrupt status | A thread has been signaled with an interrupt request | CPU loops and all types of I/O will exit automatically |
| Cancellation token | Cancellation intent shared to stages that check the token | Blocked threads will wake up automatically |
| Deadline expired | The time budget has run out | The remote server has definitely stopped |
| Worker exited | The Callable/Runnable has finished executing | All remote side effects have been cancelled |
| Resource cleanup finished | Locks/permits/streams/connections have been released according to protocol | Business data has been rolled back |
| Business commit finalized | The result-writing point determines the final state | Can be inferred from a local cancelled flag |

**`Future.isDone() == true` includes completed, failed, or cancelled.** A cancelled Future can report `isDone` even while the callable is still executing cleanup. Calling `Future.get()` after cancellation throws `CancellationException`, but that is not a certificate that every branch in the processing chain has stopped.

A request can be in different state chains simultaneously:

~~~text
Future:   RUNNING -> CANCELLED -> isDone = true
Worker:   RUNNING -> received interrupt -> cleanup -> EXITED
Remote:   REQUEST_RECEIVED -> COMMITTED (even though caller cancelled)
Resource: ACQUIRED -> CLEANUP_PENDING -> RELEASED
~~~

Therefore, measure/check each state at the right layer rather than collapsing everything into a single `cancelled` boolean.

## 3. Caller Layer: Sources of Cancellation Signals and Deadlines

Cancellation can originate from:
- The user pressing cancel or the client disconnecting.
- `Future.get(timeout, unit)` timing out while waiting.
- A downstream step exceeding its deadline.
- A child encountering an unrecoverable error, making the remaining branches unnecessary.
- The service shutting down, needing to stop accepting new requests and release resources.
- A good-enough result already arriving from one of multiple search branches, making the remaining branches unnecessary.

These causes can have **different policies**. For example, a temporary report can discard the remaining computation, whereas an operation that has already sent a transaction to an external system needs to know the final outcome or compensate before considering it complete.

### `Future.get(timeout)` only limits how long the caller waits

~~~java
try {
    return future.get(timeoutMillis, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    future.cancel(true); // Separate cancellation signal; get(timeout) does not do this automatically.
    throw e;
}
~~~

This is a snippet inside a method returning the Future's type, assuming `future`, `timeoutMillis`, and the corresponding imports are present. If `get(timeout)` throws `TimeoutException`, the task **may still be in the queue or running**, and `isCancelled()` does not automatically become `true`. Calling `cancel(true)` only sends a cancellation request; you must handle the rest according to contract.

### Overall deadline vs. per-stage timeout

Suppose a request has a 500 ms budget:

~~~text
Stage A takes 410 ms.
Stage B must not be granted a fresh 500 ms if the deadline is for the whole request.
Stage B only has about 90 ms left (minus overhead/cleanup).
~~~

If every stage is allowed to use a full 500 ms, a five-stage chain can cause the request to wait several times past its deadline. Carry a **shared deadline** or **remaining budget** across layers.

For durations within a single JVM, you can use `System.nanoTime()` to compute elapsed/remaining time; it is not a UTC timestamp and must not be sent raw to another JVM. When propagating deadlines over the network, use a cross-machine time protocol and appropriate safety margins.

## 4. Future and Executor Layer: Who Is Actually Cancelled?

`Future<V>.cancel(boolean mayInterruptIfRunning)` has two aspects:
- **Cancelling the result** represented by the Future.
- If `mayInterruptIfRunning=true` and the implementation supports it, **attempting to interrupt the thread** running the task.

Common observation table:

| Scenario | `cancel(true)` | `cancel(false)` |
| --- | --- | --- |
| Task has not started | Successfully cancels and prevents the task from running | Same |
| Task is running | Marks as cancelled; implementation may interrupt the runner | Does not request interrupting the runner |
| Task has completed | Does not cancel the completed result | Same |
| Future is already marked cancelled | `get()` throws `CancellationException` | Same |

`cancel(true)` is not `Thread.stop()`. Interruption is a **cooperative** request, not an unconditional kill. `FutureTask` and `Future` instances from standard executors support cancellation by attempting to interrupt the runner; however, `Future` is an **interface**, so you must check the specific implementation.

In particular, according to the **Java 17** Javadoc, `CompletableFuture.cancel(true)` **does not use interruption to control execution**, and the `mayInterruptIfRunning` parameter has no effect. Cancelling a `CompletableFuture` can cause `join()/get()` to observe cancellation, but it does not prove that a running `supplyAsync` has been interrupted.

### A Parent Future does not automatically manage all children

Suppose:

~~~java
Future<String> child = childPool.submit(childTask);
Future<String> parent = parentPool.submit(() -> child.get());
~~~

This is a snippet with executors and tasks already defined. When `parent.cancel(true)` is called:
- The thread waiting on `child.get()` may be interrupted, causing `get()` to throw `InterruptedException`.
- **The child Future does not automatically receive `cancel(true)`** just because the parent stopped waiting.
- If the child is still blocked on I/O or waiting on a queue, it can hold resources and keep running after the request was cancelled.
- The **coordinator/owner** must decide whether to cancel the child, wait for cleanup, or intentionally detach the child into an independent job.

## 5. Thread Layer: Interruption and Cooperation

`Thread.interrupt()` sets the interrupt status, and several blocking primitives respond to it:
- `Thread.sleep`, `Object.wait`, `CountDownLatch.await`, `BlockingQueue.take`, `Condition.await`, and `Future.get` typically throw `InterruptedException` when interrupted while waiting.
- A thread running CPU work usually **does not throw an exception automatically**; it must check the interrupt flag.
- Waiting to acquire an intrinsic `synchronized` monitor is not automatically interruptible like `ReentrantLock.lockInterruptibly()`.
- Blocking I/O has different semantics depending on the API/driver/native implementation; you cannot assume every `InputStream.read` stops immediately.

Cooperative CPU loop pattern:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    processSmallBatch();
}
cleanupAfterCancellation();
~~~

This is a snippet with those methods declared. Break work into small batches so cancellation response latency stays within acceptable bounds. A CPU-bound loop running for 10 minutes without checking status can continue for the full 10 minutes even though its Future is cancelled.

### Two different methods for checking the flag

- `Thread.currentThread().isInterrupted()`: checks the flag **without clearing** it.
- `Thread.interrupted()`: static method that reads **and clears** the current thread's interrupt flag.

Do not call `Thread.interrupted()` and discard its return value just to "probe": you could clear the cancellation request before an outer layer can read it.

### Propagate, restore, or handle?

When a method can throw `InterruptedException`, it should usually propagate it if it has no business reason to swallow it:

~~~java
String takeItem(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

If it cannot propagate and must exit:

~~~java
try {
    performInterruptibleOperation();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

The second snippet is inside a `void` method. Restoring the flag is useful so outer layers can still see the request; however, **you must also stop or transition state**, rather than restoring the flag and continuing as if nothing happened.

## 6. Java 17 Example: Future Cancelled and Worker Exited Are Two Different Things

Create the file **`InterruptBoundaryDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InterruptBoundaryDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(60_000);
                    return "completed";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "stopped";
                } finally {
                    exited.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);
            exited.await();

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + future.isCancelled());
            System.out.println("workerExited=" + (exited.getCount() == 0));

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get=CancellationException");
            }
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac InterruptBoundaryDemo.java
java InterruptBoundaryDemo
~~~

Stdout on an execution path without external interruption:

~~~text
cancelAccepted=true
futureCancelled=true
workerExited=true
get=CancellationException
~~~

Reasoning:
1. `started` confirms the Callable has started. `Thread.sleep(60_000)` keeps it from completing before main cancels it.
2. `cancel(true)` requests interrupting the runner. Whether the interrupt arrives before or during sleep, `sleep` will respond and exit.
3. The worker reaches `finally` and counts down the `exited` latch. Main **waits on `exited`**, rather than using `future.isDone()` to infer that the worker has stopped.
4. Even though the Callable returns `"stopped"` in the catch block, the Future is already cancelled so `get()` throws `CancellationException`.

A common real-world bug is checking only `future.isDone()` after cancel and assuming cleanup is complete. A cancelled Future can be done before the Callable unwinds the stack, returns a connection, or unlocks. When you need confirmation that execution has stopped, use a lifecycle signal or track worker/executor termination with a deadline.

## 7. Java 17 Example: Cancelling a Parent Does Not Automatically Cancel a Child

Create the file **`DetachedChildDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class DetachedChildDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService parents = Executors.newSingleThreadExecutor();
        ExecutorService children = Executors.newSingleThreadExecutor();

        CountDownLatch childStarted = new CountDownLatch(1);
        CountDownLatch releaseChild = new CountDownLatch(1);
        CountDownLatch childExited = new CountDownLatch(1);
        CountDownLatch parentWaiting = new CountDownLatch(1);
        CountDownLatch parentExited = new CountDownLatch(1);

        try {
            Future<Integer> child = children.submit(() -> {
                childStarted.countDown();
                try {
                    releaseChild.await();
                    return 7;
                } finally {
                    childExited.countDown();
                }
            });

            childStarted.await();

            Future<Integer> parent = parents.submit(() -> {
                parentWaiting.countDown();
                try {
                    return child.get() + 1;
                } finally {
                    parentExited.countDown();
                }
            });

            parentWaiting.await();
            boolean accepted = parent.cancel(true);
            parentExited.await();

            System.out.println("parentCancelAccepted=" + accepted);
            System.out.println("parentCancelled=" + parent.isCancelled());
            System.out.println("childCancelled=" + child.isCancelled());
            System.out.println("childExitedBeforeOwnCancel="
                    + (childExited.getCount() == 0));

            child.cancel(true);
            childExited.await();

            System.out.println("childCancelledNow=" + child.isCancelled());
            System.out.println("childExitedNow="
                    + (childExited.getCount() == 0));

            try {
                parent.get();
            } catch (CancellationException e) {
                System.out.println("parentGet=CancellationException");
            }
        } finally {
            releaseChild.countDown();
            parents.shutdownNow();
            children.shutdownNow();
            parents.awaitTermination(1, TimeUnit.MINUTES);
            children.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Compile and run:

~~~bash
javac DetachedChildDemo.java
java DetachedChildDemo
~~~

Stdout during normal execution:

~~~text
parentCancelAccepted=true
parentCancelled=true
childCancelled=false
childExitedBeforeOwnCancel=false
childCancelledNow=true
childExitedNow=true
parentGet=CancellationException
~~~

**Why?** The parent is waiting on `child.get()`, and the child is held at `releaseChild.await()`. Cancelling the parent can make the parent thread leave `get` via `InterruptedException`, but it does not automatically cancel the child. The child only receives the stop request on the explicit `child.cancel(true)` call, then exits and counts down its latch.

This example shows that **cancellation of a parent's result has no automatic propagation across all Futures in a program**. If the child belongs to a request coordinated by the parent, forgetting the child after cancellation creates **orphan work**, which can keep holding threads, I/O, or producing side effects. Conversely, if the child is genuinely an independent/durable background job, it may be intentionally detached from the parent: you must document ownership and lifecycle clearly.

## 8. Java 17 Example: Coordinator Propagates Cancellation to Child

The coordinator wants to **cancel the children it owns** when it can no longer continue. The next example creates a child and the parent waits for its result. If the parent is interrupted in `child.get()`, it explicitly calls `child.cancel(true)`.

Create the file **`CascadedCancelDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CascadedCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService parents = Executors.newSingleThreadExecutor();
        ExecutorService children = Executors.newSingleThreadExecutor();

        CountDownLatch childStarted = new CountDownLatch(1);
        CountDownLatch releaseChild = new CountDownLatch(1);
        CountDownLatch childExited = new CountDownLatch(1);
        CountDownLatch parentReady = new CountDownLatch(1);
        CountDownLatch parentExited = new CountDownLatch(1);

        AtomicReference<Future<String>> childHandle =
                new AtomicReference<>();

        try {
            Future<String> parent = parents.submit(() -> {
                Future<String> child = children.submit(() -> {
                    childStarted.countDown();
                    try {
                        releaseChild.await();
                        return "child-result";
                    } finally {
                        childExited.countDown();
                    }
                });

                childHandle.set(child);
                try {
                    childStarted.await();
                    parentReady.countDown();
                    return child.get();
                } catch (InterruptedException e) {
                    child.cancel(true);
                    Thread.currentThread().interrupt();
                    throw e;
                } finally {
                    parentExited.countDown();
                }
            });

            parentReady.await();
            boolean accepted = parent.cancel(true);

            parentExited.await();
            childExited.await();

            System.out.println("parentCancelAccepted=" + accepted);
            System.out.println("parentCancelled=" + parent.isCancelled());
            System.out.println("childCancelled="
                    + childHandle.get().isCancelled());
            System.out.println("childExited="
                    + (childExited.getCount() == 0));
        } finally {
            releaseChild.countDown();
            parents.shutdownNow();
            children.shutdownNow();
            parents.awaitTermination(1, TimeUnit.MINUTES);
            children.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac CascadedCancelDemo.java
java CascadedCancelDemo
~~~

Stdout on a normal execution path:

~~~text
parentCancelAccepted=true
parentCancelled=true
childCancelled=true
childExited=true
~~~

**Analysis:** The parent retains ownership of the child Future. When `Future.get()` is interrupted, the parent's catch block does not swallow the exception: it **cancels the child**, restores the interrupt status, and rethrows. The child is in an interruptible wait operation, so it exits and decrements `childExited`; main has a separate signal to observe that execution has finished.

**Limitations:** If the parent has **multiple** child Futures, it must manage all of them. If the child is not interruptible, `cancel(true)` is not enough to confirm it has stopped. The example illustrates the **interrupted while awaiting** path; real applications also need cleanup when the parent throws an exception elsewhere, cancellation before the child is submitted, partial child creation, and shutdown races.

### Pattern for managing multiple children

~~~java
List<Future<?>> ownedChildren = new ArrayList<>();
try {
    ownedChildren.add(childPool.submit(stageA));
    ownedChildren.add(childPool.submit(stageB));
    // Wait and aggregate.
} finally {
    if (requestNoLongerNeedsChildren) {
        for (Future<?> child : ownedChildren) {
            child.cancel(true);
        }
    }
}
~~~

This is **Java pseudocode** inside a method that already has `childPool`, `stageA`, `stageB`, and `requestNoLongerNeedsChildren`; it is not a standalone class. Do not use `finally` to cancel **every** child when business logic requires a detached-ownership job to keep running. The goal is to make ownership clear: who submits, who waits, who cancels, who cleans up, and who returns the result.

## 9. Cancellation Token: Propagating Cancellation Intent Across a Task Tree

Not every helper has a Future. A **cancellation token** is an object representing the intent to stop so stages can check it at checkpoints.

Common needs:
- A request flows through multiple methods/helpers.
- A parent coordinates multiple child tasks across different executors.
- A CPU loop needs to check cancellation intent between steps.
- A child can be cancelled individually **without** cancelling its siblings or parent.
- Cancelling the parent must cause all children still tied to the same request to observe the cancelled state.

### Java 17 Example: parent–child token

Create the file **`HierarchicalTokenDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class HierarchicalTokenDemo {
    static final class CancelToken {
        private final CancelToken parent;
        private final AtomicBoolean localCancelled = new AtomicBoolean();

        CancelToken(CancelToken parent) {
            this.parent = parent;
        }

        void cancel() {
            localCancelled.set(true);
        }

        boolean isCancelled() {
            return localCancelled.get()
                    || (parent != null && parent.isCancelled());
        }
    }

    public static void main(String[] args) throws Exception {
        CancelToken root = new CancelToken(null);
        CancelToken child = new CancelToken(root);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);

        try {
            Future<String> task = pool.submit(() -> {
                started.countDown();
                while (!child.isCancelled()) {
                    Thread.sleep(10); // Only to reduce CPU usage in the demo.
                }
                return "stopped-by-token";
            });

            started.await();
            root.cancel();

            System.out.println("rootCancelled=" + root.isCancelled());
            System.out.println("childCancelled=" + child.isCancelled());
            System.out.println("result=" + task.get());
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac HierarchicalTokenDemo.java
java HierarchicalTokenDemo
~~~

Stdout when there is no unintended interruption:

~~~text
rootCancelled=true
childCancelled=true
result=stopped-by-token
~~~

`AtomicBoolean` provides visibility for the token state. The child reads its own `isCancelled()` and its ancestor's, so parent cancellation is observed at the child. A token propagates **cancellation intent** from the parent scope; it does not automatically call `Thread.interrupt()` or close connections.

In the demo, `Thread.sleep(10)` only avoids a hot CPU spin; it is not a mechanism to guarantee immediate responsiveness. If a task is stuck on I/O without a timeout, it cannot check the token until the I/O returns. Real designs typically combine **token + interrupt/timed API/close**.

### Scope-independent cancellation

A child token is allowed to cancel itself without requiring the parent to be cancelled; other siblings can continue. However, if **all children** depend on a shared all-or-nothing outcome, the coordinator can decide to cancel the root when one child fails. That policy must be written at the **orchestration layer**, not implicitly assumed from the token.

### Tokens and memory semantics

A shared `boolean cancelled` is usually insufficient if accessed across threads without `synchronized`/`volatile`/atomics. Use `AtomicBoolean`, `volatile`, or an equivalent memory visibility protocol. If the token also carries a reason/deadline, publish fields consistently (immutable cancellation state / atomic reference if needed). Do not build a set of mutable fields where a reader can see the reason from one cancellation and the status from another.

## 10. Deadline and Remaining Budget

A request deadline can use an internal nano-time reference point and pass a Deadline object across stages. All stages use **remaining time**, rather than creating a fresh full timeout each time.

Create the file **`DeadlineBudgetDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class DeadlineBudgetDemo {
    static final class Deadline {
        private final long deadlineNanos;

        Deadline(long timeout, TimeUnit unit) {
            deadlineNanos = System.nanoTime() + unit.toNanos(timeout);
        }

        long remainingNanos() {
            return Math.max(0L, deadlineNanos - System.nanoTime());
        }
    }

    static void awaitWithinBudget(
            CountDownLatch event, Deadline deadline)
            throws InterruptedException, TimeoutException {

        long remaining = deadline.remainingNanos();
        if (remaining == 0L
                || !event.await(remaining, TimeUnit.NANOSECONDS)) {
            throw new TimeoutException("overall deadline reached");
        }
    }

    public static void main(String[] args) throws Exception {
        Deadline deadline = new Deadline(20, TimeUnit.MILLISECONDS);
        CountDownLatch neverCompleted = new CountDownLatch(1);

        try {
            awaitWithinBudget(neverCompleted, deadline);
            System.out.println("eventArrived");
        } catch (TimeoutException e) {
            System.out.println("budgetTimedOut=true");
        }
    }
}
~~~

Run:

~~~bash
javac DeadlineBudgetDemo.java
java DeadlineBudgetDemo
~~~

Stdout if the thread is not interrupted:

~~~text
budgetTimedOut=true
~~~

Because the latch **never counts down**, it cannot complete normally. If the deadline has already expired before the stage runs, the method immediately reports a timeout; if not, it waits for **only the remaining portion** and then reports a timeout. Elapsed milliseconds are not printed because scheduling timing is not fixed.

**Explicit limitations:** the example uses a short deadline; production code needs to validate negative/extremely large timeouts and avoid overflow when adding nano durations. `System.nanoTime()` is suitable for elapsed time **within a single JVM**, not as a timestamp that can be sent directly across machines.

**A Deadline object does not wake up a thread on its own**: it only lets you compute the budget. When a stage blocks on a socket, lock, queue, or remote call, you must pass the remaining budget into an API with an appropriate timeout or use a separate cancel/close channel. Putting `Future.get(timeout)` at the caller layer without setting timeouts on the I/O inside does not bound worker stop latency.

## 11. Blocking Operations: Each Layer Has a Different Interruption Mechanism

| Work type | Response to interrupt | Additional design needed |
| --- | --- | --- |
| `Thread.sleep` | Usually throws `InterruptedException` | Exit/restore/cleanup |
| `BlockingQueue.take` | Interruptible wait | `poll(timeout)` if there is a deadline |
| `CountDownLatch.await` | Interruptible wait | Ensure latch release/shutdown |
| `Future.get` | Waiting thread may receive `InterruptedException` | Cancel child Future separately |
| `Condition.await` | Interruptible wait, reacquires lock before exiting | `while` predicate, `finally` unlock |
| `ReentrantLock.lockInterruptibly` | Lock acquisition wait can be interrupted | Choose timeout when needed |
| Contending on intrinsic `synchronized` monitor | Does not throw `InterruptedException` while waiting for lock | Short critical section, check flag after entering |
| CPU loop | Does not stop without a checkpoint | `isInterrupted()`/token between batches |
| Blocking I/O | Varies across stream, socket, channel, driver | API-appropriate deadline, close per contract |
| Remote commit | Local interrupt does not mean remote rollback | Idempotency, transaction state |

**I/O cannot be guessed:** With some `InterruptibleChannel` implementations, interruption while blocking can close the channel and throw `ClosedByInterruptException`; with many other streams/sockets/drivers, semantics depend on the implementation, timeouts, or closing the resource. Never promise that every `InputStream.read()` returns immediately on `Future.cancel(true)`.

### Timeout does not cancel side effects on a remote service

A caller can lose the connection or time out **after the server has already received and committed** the request. If you retry without an idempotency key, you risk creating two records/payments. Therefore, deadline propagation does not replace duplicate-prevention and reconciliation protocols where side effects actually occur.

## 12. Cleanup: Cancellation Must Not Leak Resources

A task may hold a `Semaphore` permit, lock, file, stream, or connection when it receives an interrupt. `Future.cancel(true)` does not run cleanup code on the task's behalf; you must use `finally`/try-with-resources and ensure state is not left half-updated.

### Java 17 Example: releasing a permit after cancellation

Create the file **`ResourceReleaseDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public class ResourceReleaseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        Semaphore permits = new Semaphore(1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            Future<?> task = pool.submit(() -> {
                boolean acquired = false;
                try {
                    permits.acquire();
                    acquired = true;
                    started.countDown();
                    neverReleased.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    if (acquired) {
                        permits.release();
                    }
                    exited.countDown();
                }
            });

            started.await();
            boolean accepted = task.cancel(true);
            exited.await();

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + task.isCancelled());
            System.out.println("availablePermits="
                    + permits.availablePermits());
            System.out.println("workerExited="
                    + (exited.getCount() == 0));
        } finally {
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac ResourceReleaseDemo.java
java ResourceReleaseDemo
~~~

Normal stdout:

~~~text
cancelAccepted=true
futureCancelled=true
availablePermits=1
workerExited=true
~~~

`started` is counted down **after acquiring the permit**, so main only cancels the task once it has entered the permit-owned region. The interrupt makes `neverReleased.await()` terminate with `InterruptedException`; `finally` releases the permit and counts down `exited`. Main waits on `exited` before checking the permit count. Thus, the printed output proves that the local resource in the demo was returned, not just that the Future was cancelled.

**Production:** cleanup can throw exceptions, be slow, or block, so waiting for the worker to exit also needs a deadline and alerting. If a permit is released twice because two cancellation paths both run cleanup, the resource invariant is also broken; assign cleanup to a single owner and write idempotent logic when multiple termination paths exist.

## 13. Commit Boundary: Why Checking Interrupt Is Not Enough

A task that has started calling an external API, writing to a database, or publishing to shared state can still cause side effects after the caller cancels. Consider the snippet:

~~~java
if (!Thread.currentThread().isInterrupted()) {
    commitToExternalSystem(result);
}
~~~

This is an illustrative snippet with `result` and `commitToExternalSystem` defined by the application. There is a race:

~~~text
Worker                           Caller
------                           ------
check isInterrupted() -> false
                                 cancel(true)
commitToExternalSystem(result)
                                 Caller thinks task was aborted
~~~

The check and the commit are not a single transaction. Even if the worker is interrupted before sending, an earlier remote request may already have committed on the server.

Approaches when late results must not be written:
- **Generation/version:** each request/retry has a version; an old result cannot overwrite the new generation's state if publishing checks the version atomically.
- **Commit ownership:** a single component has authority to accept results and decide whether cancellation has already won.
- **Atomic state transition:** transition `RUNNING -> COMMITTING` under a lock/CAS according to the invariant to preserve; define which side wins if cancellation and commit race.
- **Idempotency key:** the target system recognizes retries of the same business operation.
- **Transaction or compensation:** if a partial commit cannot be rolled back atomically, provide a compensation mechanism and durable status.
- **Reconciliation:** when the caller times out without knowing what the remote system did, query the status by request ID instead of guessing "failed".

**Cancellation tokens and interrupt flags do not guarantee atomicity with commits outside the JVM.** If strong correctness is required, there must be a protocol at the exact boundary where side effects happen.

## 14. CompletableFuture and Dependency Graphs

Java 17 `CompletableFuture` builds pipelines with `thenApply`, `thenCompose`, `allOf`, and `anyOf`. However, **cancelling a CompletableFuture** does not mean cancelling all work underneath its stages:
- `cancel(true)` on `CompletableFuture` does not use interruption to control workers in Java 17.
- A running `supplyAsync` can continue producing side effects.
- Dependent stages can receive exceptional/cancellation completion per the `CompletableFuture` contract, but they do not automatically manage `FutureTask`/HTTP requests created by callbacks.
- If execution must be cancelled, you must pass a token/deadline into callbacks or separately retain task/I/O handles with an appropriate cancellation policy.

### Snippet applying a token in a pipeline

~~~java
CancelToken requestToken = new CancelToken(null);

CompletableFuture<String> result = CompletableFuture.supplyAsync(() -> {
    if (requestToken.isCancelled()) {
        return "cancelled-before-work";
    }

    String answer = computeWithCheckpoints(requestToken);
    if (requestToken.isCancelled()) {
        return "discarded";
    }
    return answer;
}, executor);

// On the caller side:
requestToken.cancel();
result.cancel(true);
~~~

This is a **snippet** using the `CancelToken` class from the earlier example along with application-defined `computeWithCheckpoints` and `executor`. `result.cancel(true)` is only cancellation at the `CompletableFuture` layer; `requestToken.cancel()` makes the cancellation intent observable by the callback itself. The final publish step still needs generation/commit control, because cancellation can arrive after the last check.

Do not assume that structured concurrency APIs introduced in newer Java versions are available on Java 17. With standard Java 17 APIs, **ownership of Futures/child tasks** must be managed explicitly.

## 15. Coordinator Error/Cancellation Policies

When one child fails, should all remaining children be cancelled? There is no single rule for every business case:

| Policy | When it applies | Other tasks |
| --- | --- | --- |
| All-or-nothing | Every child must succeed for a valid result | Cancel the rest on a required failure |
| Best-effort | Partial results can be returned within the deadline | Continue children that still have value |
| First-success | A valid result from any one of multiple children is enough | Cancel redundant children if safe |
| Durable background | The job must continue even if the caller disconnects | Detach ownership and monitor |
| Shared computation | Multiple callers need the same child | One caller cancelling must not arbitrarily cancel shared work for others |

The coordinator layer must keep **a list of the children it actually owns**. If a child is shared across multiple callers, a lease/reference count or an independent owner may be needed. Never arbitrarily cancel a shared task just because one caller lost interest in its result.

### Do not turn interruption into a "default success"

Wrong:

~~~java
try {
    return child.get();
} catch (InterruptedException ignored) {
    return defaultResult;
}
~~~

This is a snippet inside a method returning an appropriate type. It can mask the cancellation request, making the caller think the pipeline succeeded and commit an incorrect value. A better approach is to determine child ownership, cancel the child if no longer needed, and either propagate `InterruptedException` or restore the status and return an explicit cancelled state.

### When a worker is cancelled but still running

If a task ignores interrupts or is stuck in unfinished I/O, it can become **orphan work**. Even if `Future.isCancelled()` is true, there is no proof that resources have been released. Logs/metrics should distinguish:
- Cancellation requested.
- Cancellation accepted by Future.
- Child cancellation dispatched.
- Worker actually exited.
- Cleanup completed.
- Business commit accepted/rejected.

## 16. Executor Shutdown Is a Different System Layer from Request Cancellation

**`ExecutorService.shutdown()`**: rejects new tasks and allows already-submitted tasks to run according to contract.

**`shutdownNow()`**: attempts to stop running tasks via interruption and returns tasks that have not started, though this is **best-effort**.

**`awaitTermination(timeout, unit)`**: waits for the executor to terminate after shutdown; it does not initiate shutdown itself.

Snippet:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            // Log uncooperative tasks or overdue cleanup.
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This is a snippet with `pool` as an `ExecutorService` and `TimeUnit` imported. A cancelled request **has no right to shut down a shared executor** used by the whole application; cancel only the Futures/tokens belonging to that request. Application shutdown is what coordinates all request scopes, drains/cancels, waits for cleanup, and tracks non-cooperative workers.

## 17. Design Checklist for Cascading Cancellation Signals

1. **What is the cancellation source?** User, deadline, upstream error, or shutdown? Does each type have a different policy?
2. **Who owns the children?** Is there a complete list of Futures/handles when a parent spawns multiple branches?
3. **Should cancellation propagate downward?** All-or-nothing, or are jobs allowed to continue independently?
4. **What does each stage receive?** Interrupt, token, deadline, close, timed API, or a combination?
5. **Do CPU stages have checkpoints?** Could an overly long computation loop inflate cancellation latency?
6. **Does blocking I/O have real timeouts/cancellation?** Do not confuse `Future.get(timeout)` with socket/DB timeouts.
7. **Do intermediate layers swallow `InterruptedException`?** If they cannot propagate it, do they restore the flag and exit?
8. **Does each child clean up?** Are locks, permits, connections, and streams released in `finally`/try-with-resources?
9. **What if cleanup fails or hangs?** Is there a monitoring deadline so shutdown does not wait forever?
10. **Can cancellation happen during commit?** Are commit authority/state machine and idempotency in place?
11. **Can a late result overwrite a new generation?** Is there a CAS/version check at the publish point?
12. **Are any children shared among multiple callers?** A single caller must not cancel global work.
13. **Does the token structure have proper memory visibility?** Use atomics/volatile or immutable state.
14. **Is the remaining time budget propagated?** Do not restart the full timeout at every stage.
15. **Do metrics distinguish cancel acceptance from worker exit?** Do not report "cancel complete" based solely on `Future.isDone()`.
16. **Are tests coordinated deterministically?** Use latches/barriers instead of sleep to force execution points.
17. **Is shutdown concurrent with cancel idempotent?** Avoid double-release or double-compensation.
18. **Have liveness and throughput been measured after adding cancellation?** A cancellation path must not introduce new deadlocks.

## 18. Exercises and Self-Check Questions

1. Does `parent.cancel(true)` automatically call `child.cancel(true)`? **No**, unless an abstraction/coordinator is designed to propagate it.
2. Does `Future.isDone()==true` after cancel prove the Callable has exited? **No**; separate lifecycle observation is required.
3. Does `Future.get(timeout)` throwing `TimeoutException` cancel the task? **No**.
4. How does `Thread.currentThread().isInterrupted()` differ from `Thread.interrupted()`? **The latter is static and clears the current thread's flag**.
5. If a CPU loop does not check interrupts or a token, does cancel force it to stop? **No**.
6. If a parent token is cancelled, does a child token like the one in the example know? **Yes**, because it reads ancestor state.
7. Does a token changing to `true` automatically unblock a `BlockingQueue.take()` call? **No**; an interrupt/timed/wakeup protocol is needed.
8. Why can a parent waiting on `child.get()` be interrupted while the child keeps running? **The parent's `InterruptedException` does not cancel the child Future**.
9. Who is responsible for cancelling a child when it is no longer needed? **The owner/coordinator managing the child**, unless child ownership was explicitly detached.
10. Should a shared task be cancelled if one caller discards the result? **Not by default**; ownership and the requirements of other callers must be checked.
11. In Java 17, does `CompletableFuture.cancel(true)` always interrupt the `supplyAsync` thread? **No; `mayInterruptIfRunning` has no effect**.
12. Does `shutdownNow()` force every task to stop immediately? **No, it is only best-effort**.
13. Why is an overall deadline needed across multiple stages? **To avoid re-granting the full timeout and exceeding the requested time**.
14. Is `System.nanoTime()` a UTC timestamp that can be sent to another server? **No**, it is a relative duration measurement basis within a process.
15. Is `Future.get(timeout)` enough to interrupt every socket read? **No**; you must use an I/O API with appropriate timeout/close/cancel support.
16. Does checking interrupt right before committing prevent every commit after cancellation? **No**, there is still a race between the check and the commit.
17. If the server has already committed but the caller timed out, what should be done to avoid duplicates? **Use an idempotency key and query/reconcile state**.
18. Can a cancellation token replace memory visibility mechanisms? **No**, the token itself must use atomic/volatile/locking properly.
19. Why must cleanup happen in `finally`? **So exceptions/interruptions still lead to releasing resources at the owner**.
20. In `DetachedChildDemo`, does cancelling the parent make the child's `isCancelled` true? **No**, only the explicit child cancellation does.
21. In `CascadedCancelDemo`, why is the child's `isCancelled` true? **The parent catches `InterruptedException` and explicitly calls `child.cancel(true)`**.
22. In `ResourceReleaseDemo`, why does the permit count return to 1? **The worker runs `finally` and releases the permit after interruption, and main waits for `exited`**.
23. If cancellation and shutdown arrive together, can a resource be released twice? **Yes if the cleanup protocol is flawed**; you need an owner/idempotent transition.
24. Can the count of `cancel(true)==true` be treated as the count of rolled-back business operations? **No**, these are two different metrics.
25. Can a child intentionally keep running after a request is cancelled? **Yes**, if it is a durable background job, but ownership, resource management, and finality must be clearly separated.

## 19. Conclusion

**Cascading cancellation signals** is the design of propagating stop requests from the caller down through the coordinator, children, threads, blocking APIs, and commit points, while propagating results and cleanup status back up. `Future.cancel(true)`, interrupt status, cancellation tokens, and deadlines **are complementary mechanisms, not replacements for one another**.

A proper protocol must define:
- **Ownership scope:** which children belong to the parent and whether they must be cancelled with the parent.
- **Checkpoints:** which stages cooperate with interrupts/tokens, and which I/O has timeouts/close.
- **Resources:** who releases locks, permits, and connections, and confirms the worker exited.
- **Business logic:** which commits cancellation can prevent, and how already-completed side effects and late results are handled.
- **Observability:** not confusing Future cancelled with worker stopped and business finalized.

Measure the success of cancellation by **tasks actually stopping, resources actually being returned, and business results being handled correctly**, not merely by the return value of `cancel(true)`.

## Java SE 17 References

- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `isCancelled`, `get(timeout)`.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown`, `shutdownNow`, `awaitTermination`.
- [Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `interrupted`, `isInterrupted`.
- [CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): coordination across stages.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancellation semantics.
- [BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): `take` and `poll(timeout)`.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `lockInterruptibly` and `tryLock`.
- [InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html): interruption with blocking channels.
- [Java Language Specification `17](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before and the Java Memory Model.
