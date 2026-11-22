# ForkJoinTask.cancel() vs. adaptInterruptible(Callable) on Java 21

## 1. The problem: cancelling Future state is different from stopping a running task

In Fork/Join, a task may already be queued, running on a worker, or completed. When the caller no longer needs the result, `ForkJoinTask.cancel(boolean mayInterruptIfRunning)` allows **transitioning the task's state to canceled** if the cancellation succeeds. However, **canceled does not automatically mean the running thread was interrupted or the task body has stopped**.

In Java 21, you need to clearly distinguish between two options:

- Ordinary `ForkJoinTask`, such as a `RecursiveTask` or a task created with `ForkJoinTask.adapt(Callable)`: the default implementation of `cancel(...)` **does not use interrupts to control cancellation**; the `mayInterruptIfRunning` value has no effect on the default implementation.
- `ForkJoinTask.adaptInterruptible(Callable<? extends T>)`: creates a special `ForkJoinTask<T>`; when `cancel(true)` is called, the implementation **attempts to interrupt the thread executing the Callable**, allowing the task to cooperate with cancellation.

What they have in common: in both cases, `isCancelled()` and `join()` reflect **the logical outcome of cancellation**, not a guarantee that all side effects, I/O, or cleanup have finished.

This article focuses on **standard Java Concurrency, not tied to Spring**. The content applies specifically to Java 21 APIs; some overloads with the same name were added in later JDKs, so you should not assume they exist in Java 21.

## 2. APIs to know

### 2.1. ForkJoinTask.cancel(boolean)

Signature:

```java
public boolean cancel(boolean mayInterruptIfRunning)
```

A successful cancellation has important consequences:

1. If the task **has not started yet**, execution of the task body is prevented.
2. `isCancelled()` and `isDone()` will return `true`, unless `reinitialize()` is called per the class contract.
3. `join()`, `get()`, and related result-retrieval methods will throw `CancellationException` instead of returning a result value.
4. If the task is already running, the canceled state **does not guarantee** that the task body stops immediately.
5. `cancel(true)` on the default implementation has no interrupt effect different from `cancel(false)`. Subclasses may override it, but must still preserve the cancellation contract and must not throw exceptions from `cancel` itself.

A return value of `true` means **the task is now in the canceled state** (including when it was already canceled earlier); it does not indicate that the worker was definitely just interrupted or has terminated. If the task completed normally before cancellation, the cancel request cannot transition it to canceled.

### 2.2. adapt(Callable) and adaptInterruptible(Callable)

Java 21 provides two adapters from `Callable<T>`:

```java
ForkJoinTask<Integer> ordinary =
        ForkJoinTask.adapt(() -> 6 * 7);

ForkJoinTask<Integer> interruptible =
        ForkJoinTask.adaptInterruptible(() -> 6 * 7);
```

Both create a `ForkJoinTask<Integer>`, execute `Callable.call()`, and allow retrieving the result via `join()`. Checked exceptions thrown by `call()` are wrapped by the adapter into a `RuntimeException` per the API contract when accessed via Fork/Join mechanisms; `Future.get()` still retains `Future`'s `ExecutionException` semantics.

The main difference lies in **cancellation while the task is running**:

- `adapt(Callable)` uses default Fork/Join-style cancellation; `cancel(true)` does not send an interrupt to the runner.
- `adaptInterruptible(Callable)` supports attempting to interrupt the runner when `cancel(true)` is called.
- If `cancel(false)` is called on the interruptible adapter, it **does not request interrupting the runner**; a running task may continue.
- The task must cooperate with interruption: `CountDownLatch.await()`, `sleep()`, or other interruptible blocking APIs may throw `InterruptedException`; CPU computation loops need to check the interrupt flag, while some I/O operations may not respond.

**API version:** `adaptInterruptible(Callable)` was introduced in Java 19 and is available in Java 21. The `adaptInterruptible(Runnable)` and `adaptInterruptible(Runnable, T)` overloads were introduced in Java 22, so do not include them in code compiled with `--release 21`.

### 2.3. Quick comparison table

| Question | Default ForkJoinTask | `adaptInterruptible(Callable)` |
| --- | --- | --- |
| Does cancelling before start prevent the task body from running? | Yes, if cancellation succeeds | Yes, if cancellation succeeds |
| `cancel(false)` on a running task | Marks canceled, does not request interrupt | Marks canceled, does not request interrupt |
| `cancel(true)` on a running task | The `true` parameter has no interrupt effect in the default implementation | **Attempts to interrupt the thread** running the Callable |
| `isCancelled()` after successful cancellation | `true` | `true` |
| `join()` after successful cancellation | Throws `CancellationException` | Throws `CancellationException` |
| Can a running task continue after being canceled? | Yes | Yes, if it does not handle interrupts or the interrupt is not enough to stop it |
| When to choose? | Non-blocking divide-and-conquer computation, state-based/cooperative cancellation | Callable needs to react while waiting on an interruptible API |

Do not interpret this table as "the interruptible adapter forcibly stops the thread." Java does not provide a safe, forcible cancellation mechanism for arbitrary tasks.

## 3. Three state levels that must be observed separately

An accurate mental model is to distinguish three events:

1. **Cancellation accepted:** `cancel(...)` transitions the Future/task to the canceled state.
2. **Interruption requested:** with `adaptInterruptible(callable)` and `cancel(true)` when the callable is already running, the implementation attempts to send an interrupt to the executing thread.
3. **Task body actually exited:** the code reaches an exit point, runs `finally`, and releases the resources it holds.

These three points in time can differ. In particular, once the canceled state has been marked:

```java
boolean cancelled = task.isCancelled();
boolean done = task.isDone();
```

`cancelled == true` and `done == true` **do not confirm** that the task has actually exited its loop or finished its side effects. `isDone()` describes the state of the `ForkJoinTask`; if the task was canceled while running, the code may still continue for some time.

To verify that the task body has left a critical section, the application needs a separate mechanism if required—for example, a `CountDownLatch` that calls `countDown()` in `finally`, or closing resources / terminating a protocol at an appropriate boundary. Do not use the mere fact that `get()` threw `CancellationException` as confirmation of cleanup.

## 4. Standalone Java 21 example: observing cancel and interrupt

The example below intentionally makes the Callable **wait on a `CountDownLatch`** to reproduce a running task in a controlled way. It exercises three scenarios:

1. `adapt(Callable)` + `cancel(true)`: the task is canceled in state, but does not receive an interrupt from the default cancel alone.
2. `adaptInterruptible(Callable)` + `cancel(false)`: the task is canceled in state, but does not request an interrupt.
3. `adaptInterruptible(Callable)` + `cancel(true)`: the runner receives the interrupt request, and `await()` exits via `InterruptedException`.

`CountDownLatch` here is solely for demonstrating semantics. In real Fork/Join usage, tasks should be short, decomposable, and avoid long waits; if work is primarily I/O or blocking, evaluate an appropriate executor model.

Save the file as `ForkJoinCancellationDemo.java`:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ForkJoinPool;
import java.util.concurrent.ForkJoinTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ForkJoinCancellationDemo {
    public static void main(String[] args) throws InterruptedException {
        runCase("adapt + cancel(true)", false, true);
        runCase("interruptible + cancel(false)", true, false);
        runCase("interruptible + cancel(true)", true, true);
    }

    private static void runCase(
            String label, boolean useInterruptible, boolean interruptOnCancel)
            throws InterruptedException {

        ForkJoinPool pool = new ForkJoinPool(1);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean caughtInterrupt = new AtomicBoolean(false);

        Callable<String> work = () -> {
            started.countDown();
            try {
                release.await();
                return "completed";
            } catch (InterruptedException interrupted) {
                caughtInterrupt.set(true);
                return "interrupted";
            } finally {
                exited.countDown();
            }
        };

        ForkJoinTask<String> task = useInterruptible
                ? ForkJoinTask.adaptInterruptible(work)
                : ForkJoinTask.adapt(work);

        try {
            pool.execute(task);
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task did not start");
            }

            boolean cancelled = task.cancel(interruptOnCancel);
            if (!cancelled || !task.isCancelled()) {
                throw new AssertionError("Cancellation was not accepted");
            }

            if (useInterruptible && interruptOnCancel) {
                // Task is using await(): the interrupt will make it exit.
                if (!exited.await(5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Interrupt was not observed");
                }
            } else if (exited.getCount() == 0) {
                throw new AssertionError("Unexpected early exit");
            }

            // Allow the non-interrupted tasks to exit cleanly as well.
            release.countDown();
            if (!exited.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Task body did not exit");
            }

            boolean joinCancelled = false;
            try {
                task.join();
            } catch (CancellationException expected) {
                joinCancelled = true;
            }

            System.out.println(label
                    + " | cancelled=" + task.isCancelled()
                    + " | caughtInterrupt=" + caughtInterrupt.get()
                    + " | joinCancelled=" + joinCancelled);
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Pool did not terminate");
            }
        }
    }
}
```

Compile and run with **JDK 21**:

```bash
javac --release 21 ForkJoinCancellationDemo.java
java ForkJoinCancellationDemo
```

Expected stdout on JDK 21:

```text
adapt + cancel(true) | cancelled=true | caughtInterrupt=false | joinCancelled=true
interruptible + cancel(false) | cancelled=true | caughtInterrupt=false | joinCancelled=true
interruptible + cancel(true) | cancelled=true | caughtInterrupt=true | joinCancelled=true
```

The latches establish a clear ordering: `started.await()` completes only after the Callable has started; `release` holds the two non-interrupted cases inside `await()`; `exited` confirms the code has left the task body before printing the result. The `interruptible + true` case proceeds only after observing that the task body exited following the interrupt.

The code above **does not use `Thread.sleep` to guess when the task has started**. The `await(timeout)` calls also prevent the demo from hanging indefinitely if the environment is overloaded or an API behaves unexpectedly. If the pool cannot schedule a task within 5 seconds, the demo intentionally throws an `AssertionError` instead of claiming an unobserved result.

An easy detail to miss: here the Callable catches `InterruptedException` and returns the string `"interrupted"`, yet once `cancel(true)` has marked the `ForkJoinTask` as canceled, **`join()` still throws `CancellationException`** instead of returning that string. This is clear evidence that **the logical outcome of the Future** differs from **the actual exit path of the task body**.

## 5. Why is cancel(true) not the same as Thread.interrupt()?

`cancel(boolean)` belongs to the `Future` interface, but each implementation may have specific rules for how tasks are canceled. You should not look at the parameter name `mayInterruptIfRunning` alone and assume every implementation sends an interrupt.

**Default `ForkJoinTask`** is designed for lightweight, short, fork/join-structured computations. The Java 21 documentation explicitly states that the `mayInterruptIfRunning` parameter has no effect in the default implementation, because interrupts are not used to control cancellation.

**The interruptible adapter** is an intentional choice for a `Callable` that needs cancellation behavior closer to a standard `Future`. When `cancel(true)` is called, it attempts to interrupt the runner executing the Callable. If the callable is blocked in `CountDownLatch.await()`, `Thread.sleep()`, or another interruptible waiting API, it will typically exit promptly with `InterruptedException`.

That difference applies only when **the runner has already started** and is able to receive interrupts. If the task is canceled **before running**, both can prevent the body from executing; there is no runner to interrupt. If the task has already completed, cancelling cannot transition it back to canceled.

You should also distinguish **external cancellation** from **self-stopping tasks**. Inside `RecursiveTask.compute()`, a task can return early when it detects an application-managed cancellation flag. Checking `isCancelled()` inside a loop is only useful if the application's control flow actually has a checkpoint and exit path.

## 6. Which API to choose in Java 21?

### 6.1. RecursiveTask/RecursiveAction for divide-and-conquer problems

A typical `RecursiveTask<V>` splits work into smaller pieces using `fork()` and `join()`. You must avoid long blocking calls inside branches, because occupied workers can starve the pool of threads needed to process remaining tasks.

```java
// Fragment inside compute() of a RecursiveTask<Long>.
if (hi - lo <= threshold) {
    return sumDirectly(data, lo, hi);
}
int mid = lo + (hi - lo) / 2;
SumTask left = new SumTask(data, lo, mid, threshold);
SumTask right = new SumTask(data, mid, hi, threshold);
left.fork();
long rightValue = right.compute();
return left.join() + rightValue;
```

This is a fragment with application-defined classes/variables, not a standalone program. If you want to cancel an entire fork/join tree, **cancelling only the root task does not prove that all child branches have stopped**. The design needs a cooperative coordination mechanism—for example, a safely shared stop flag that branches check periodically before forking more work.

### 6.2. adapt(Callable) when wrapping a simple Callable

`ForkJoinTask.adapt(callable)` is appropriate if the main goal is to adapt a Callable into the Fork/Join API and the default cancellation semantics are acceptable. Do not expect `cancel(true)` to interrupt a running blocking call.

### 6.3. adaptInterruptible(Callable) when reacting to cancellation is needed

`ForkJoinTask.adaptInterruptible(callable)` is useful if the Callable may block or needs to stop when cancellation is requested. It is a valid Java 21 API for `Callable`; some programs may want to leverage this behavior when running work in a `ForkJoinPool`.

However, do not conclude that **all blocking tasks belong in `ForkJoinPool`**. The pool is optimized for decomposing computation. Blocking can degrade worker efficiency; consider `ForkJoinPool.ManagedBlocker`, a different executor, I/O deadlines, and bounding the number of active tasks when truly necessary.

### 6.4. Decision table

| Scenario | Recommendation |
| --- | --- |
| CPU-bound decomposition, short subtasks, minimal blocking | `RecursiveTask` / `RecursiveAction`, cooperative cancellation |
| Adapting a `Callable<T>` to `ForkJoinTask<T>` without interrupt-on-cancel | `ForkJoinTask.adapt(callable)` |
| Callable waits on APIs supporting `InterruptedException` and needs `cancel(true)` to attempt interrupting the runner | `ForkJoinTask.adaptInterruptible(callable)` |
| Long blocking work that cannot cooperate with interrupts | Design separate timeouts and resource cancellation; consider an executor dedicated to I/O |
| Task must survive restarts or roll back side effects | Use application-level job state and transactions/idempotency; `ForkJoinTask` provides no durability |

## 7. Checking status and retrieving results

Key APIs:

| Method | Meaning |
| --- | --- |
| `cancel(boolean)` | Attempts to transition the task to canceled; may or may not attempt interrupt depending on the implementation |
| `isDone()` | `true` if completed normally, failed, or canceled |
| `isCancelled()` | `true` if the state is canceled |
| `isCompletedNormally()` | `true` if completed normally |
| `isCompletedAbnormally()` | `true` if failed or canceled |
| `getException()` | Computation exception or `CancellationException` when canceled; `null` if none yet |
| `join()` | Waits and returns the result; throws `CancellationException` (unchecked) on cancellation |
| `get()` | Per the `Future` interface: may throw `InterruptedException`, `ExecutionException`, or `CancellationException` |

`join()` and `get()` do not wrap errors the same way. `join()` throws abnormal exceptions as unchecked exceptions (or `Error`), whereas `get()` reports task failures via `ExecutionException`. For cancellation, both can throw `CancellationException`.

Example status-checking fragment:

```java
if (task.isCancelled()) {
    System.out.println("Result unavailable");
} else if (task.isCompletedNormally()) {
    System.out.println(task.join());
} else if (task.isCompletedAbnormally()) {
    System.out.println("Failed: " + task.getException());
}
```

This is a fragment assuming `task` is declared elsewhere. These status checks serve to classify the outcome; they do not replace a mechanism for confirming that the task body has actually exited or finished cleanup.

### Checked exceptions from Callable

`Callable.call()` allows checked exceptions such as `IOException`. `adapt` and `adaptInterruptible` convert checked exceptions into `RuntimeException` when surfaced as a `ForkJoinTask`. Callers must design handling for the underlying exception accordingly; if `get()` is used, execution failures are surfaced via `ExecutionException` per `Future` semantics.

Do not catch every `RuntimeException` and assume "task canceled": cancellation has its own dedicated exception, `CancellationException`. A Callable failing due to a business or I/O error must be distinguished from caller-requested cancellation.

## 8. Cancelling a fork/join tree: why cancelling the root is not enough

Subtasks are separate `ForkJoinTask` instances. When a root forks two branches, they have their own completion/cancellation states. Cancelling the root can cause `root.join()` to report cancellation, but it does not by itself prove that all child branches were canceled—especially branches that have already started running and are producing side effects.

A cooperative pattern uses an `AtomicBoolean` or an application-managed cancellation token:

```java
// Fragment: branches are passed the same AtomicBoolean stopRequested.
if (stopRequested.get()) {
    return 0L; // Only appropriate when 0 is the agreed-upon aborted result.
}
long partial = computeChunk();
if (stopRequested.get()) {
    return 0L;
}
return partial;
```

**Warning about results:** Returning `0` on cancellation here only illustrates an exit point; in a real aggregation problem, returning a partial sum without clearly indicating cancellation can cause business-logic errors. It is usually better to represent cancellation state separately or handle exceptions/cancellation according to the contract of the overall computation.

If you want to stop every branch, you must propagate the signal across the entire tree and design cleanup. `adaptInterruptible(Callable)` only attempts to interrupt **the runner of that adapter task**; it does not seek out and interrupt other subtasks forked from inside the Callable.

## 9. Cooperative interruption

Common cases when `cancel(true)` is called on an interruptible adapter:

- **Waiting in `CountDownLatch.await()` or `Thread.sleep()`:** receives `InterruptedException` and can exit promptly.
- **Running a CPU loop:** if not calling a waiting API, must check `Thread.currentThread().isInterrupted()` at checkpoints.
- **Performing I/O:** depends on whether the API supports interruption. Many network operations require client/socket timeouts to avoid hanging for long periods.
- **Holding a lock or updating state:** must avoid stopping in the middle of an unrestored invariant; use `try/finally` to close and release resources.
- **Calling an external system:** interrupting a Java thread does not automatically roll back an already-sent request.

Example of a Callable checking for interrupts during computation:

```java
Callable<Long> calculation = () -> {
    long sum = 0L;
    for (int i = 0; i < 1_000_000; i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new InterruptedException("Computation interrupted");
        }
        sum += i;
    }
    return sum;
};
```

When using `adaptInterruptible(calculation)`, calling `cancel(true)` on a running task can cause the loop to detect the interrupt at the next check. If the task completes before cancellation, `cancel` will not revert a successful result to canceled. Do not rely on real-time execution timing to expect cancel to always win a race.

### Handling InterruptedException

If a Callable cannot complete properly when interrupted, it is common to let `InterruptedException` propagate out of `call()` (which declares `throws Exception`) so the task body exits. If you catch the exception to clean up, you can rethrow it:

```java
try {
    blockingStep();
} catch (InterruptedException interrupted) {
    cleanupLocalState();
    throw interrupted;
}
```

This is a fragment using application-defined functions. If a method cannot propagate a checked exception, it should restore the interrupt flag via `Thread.currentThread().interrupt()` and exit according to its own contract. Never swallow the interrupt and continue an infinite loop.

## 10. Caution with shutdown, timeouts, and resources

`pool.shutdown()` stops accepting new work and lets already-accepted tasks complete under normal shutdown semantics; `pool.shutdownNow()` attempts to interrupt running tasks and processes unstarted tasks per the `ExecutorService` contract. Do not equate pool shutdown with `task.cancel(true)`.

Even when using the interruptible adapter, **a caller-side timeout** and **cancelling the task** remain two separate actions:

```java
try {
    String result = task.get(500, TimeUnit.MILLISECONDS);
    consume(result);
} catch (java.util.concurrent.TimeoutException timedOut) {
    task.cancel(true); // Explicitly request cancellation after timeout.
}
```

This is a fragment: `task` and `consume` are application-defined; to compile standalone, you also need to handle `InterruptedException`, `ExecutionException`, and `CancellationException`. `get(timeout)` throwing `TimeoutException` **does not automatically cancel** the task; you must call `cancel(true)` if application policy requires stopping it.

Similarly, after `cancel(true)`, you should have a way to observe that the task has actually exited if holding connections, locks, or other resources is a significant risk. Use I/O deadlines and monitor for stuck workers; do not rely on `isCancelled()` alone to conclude that a resource has definitely been released.

## 11. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Assuming `ForkJoinTask.cancel(true)` interrupts the worker by default | Blocking task keeps running/waiting; Future is already canceled | Distinguish the default implementation from the interruptible adapter |
| Assuming `adaptInterruptible` guarantees forcible termination | A task that does not respond to interrupts can still hold resources | Design interruption checkpoints, I/O timeouts, and cleanup |
| Calling `cancel(false)` and expecting the runner to be interrupted | The `false` argument does not request an interrupt | Use `true` when needed and when cooperative cancellation is supported |
| Treating `isDone()` as task success | Canceled and failed tasks are also done | Use `isCompletedNormally()`, `isCancelled()`, and `getException()` |
| Treating `join()` throwing `CancellationException` as completed cleanup | Resources are still held by a body that has not exited | Observe completion of the body/cleanup separately |
| Calling `pool.invoke(task)` synchronously and intending to cancel from the same thread | The calling thread is blocked waiting for `invoke` to finish | Use `execute(task)` / `submit(task)` and keep a handle to cancel from the caller |
| Ignoring `InterruptedException` in a Callable | Task keeps running after a cancellation request | Propagate it or handle it and exit |
| Cancelling the root and assuming all subtasks have stopped | Subtasks may continue causing side effects | Propagate a tree-wide cancellation signal and check it in each branch |
| Using the `adaptInterruptible(Runnable)` overload on Java 21 | Does not compile: this overload is from Java 22 | Use the `Callable` overload on Java 21 |
| Using `ForkJoinPool` for unbounded long-running I/O | Worker starvation, reduced throughput | Set deadlines, choose an appropriate executor, consider `ManagedBlocker` |
| Treating a canceled task as a transaction rollback | External data may already have been modified | Use idempotency/compensation and state verification |

## 12. Checklist for choosing and verifying cancellation

1. **Identify the task type**: divide-and-conquer computation or a Callable with blocking?
2. **Identify the implementation**: default `RecursiveTask`/`adapt` or `adaptInterruptible(Callable)`?
3. **Identify the cancellation timing**: before running, while running, or after completion?
4. **Distinguish the boolean's meaning**: `cancel(true)` does not automatically force a thread to stop; which implementation actually attempts an interrupt?
5. **Use an observable signal**: `CountDownLatch` or cleanup completion if you need to prove the task body has exited.
6. **Set I/O timeouts**: do not rely solely on interrupts when a library does not support them.
7. **Clean up resources**: `try/finally`, `try-with-resources`, and clear ownership for resources created before the task starts.
8. **Test races**: cancel before the task runs, after it starts, and after it has completed.
9. **Preserve the result contract**: `CancellationException`, computation errors, and success must be distinct branches.
10. **Verify the exact version**: use only APIs published in Java 21 if the module targets Java 21.

## 13. Self-check questions

**1. With an ordinary `RecursiveTask`, does `cancel(true)` interrupt the worker?**  
No, under the default `ForkJoinTask` implementation; the `mayInterruptIfRunning` parameter has no interrupt effect there.

**2. Is `adaptInterruptible(Callable)` available in Java 21 or only later?**  
It is available in Java 21 (introduced in Java 19). The two overloads taking `Runnable` appeared in Java 22.

**3. Does `cancel(true)` on the interruptible adapter guarantee that the Callable has stopped all side effects when `cancel` returns?**  
No. It only attempts to interrupt the runner; the Callable must cooperate and clean up after itself.

**4. If a task has been canceled but the Callable body subsequently returns a value, will `join()` return that value?**  
No. Once the canceled state is successfully set, `join()` throws `CancellationException`, regardless of whether the Callable body later reaches a `return` statement.

**5. Does `isDone() == true` mean the task body has exited all processing?**  
No. For a task canceled while running, the Future state can be done before the code actually stops.

**6. Can `get(timeout)` be used instead of `cancel(true)`?**  
No. `get(timeout)` only limits how long the caller waits; timing out does not automatically send a cancellation signal.

**7. Why shouldn't `adaptInterruptible` be used as a way to cancel an entire fork/join tree?**  
It manages the runner of a single adapter task and does not automatically propagate cancellation to independently created subtasks.

**8. When should you avoid `ForkJoinPool`?**  
When tasks are primarily long-blocking, depend on external resources, or cannot be decomposed effectively; in those cases, consider a more suitable executor and architecture.

## References

- [Java SE 21 — ForkJoinTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
- [Java SE 21 — ForkJoinPool](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ForkJoinPool.html)
- [Java SE 21 — Callable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Callable.html)
- [Java SE 21 — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html)
- [Java SE 21 — RecursiveTask](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/RecursiveTask.html)
- [Java SE 22 — ForkJoinTask (for comparing new overloads)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/ForkJoinTask.html)
