# Future.cancel(true) and Practical Limitations in Java Concurrency

## 1. Purpose and Meaning of Task Cancellation

In multithreaded applications, sometimes a task is no longer needed: the caller has timed out, the request is closed, the worker must yield resources, or the application is shutting down. For a task submitted to an `ExecutorService`, the `Future<?>` object allows the caller to retrieve the result or **request cancellation** via `cancel(boolean mayInterruptIfRunning)`.

A common call looks like this:

~~~java
boolean accepted = future.cancel(true);
~~~

There is one critically important point:

> **`Future.cancel(true)` indicates that the cancellation request was accepted and, if appropriate for the implementation, attempts to interrupt the running thread; it does not guarantee that business logic has stopped by the time `cancel` returns, does not automatically roll back side effects, and does not force every I/O API to exit immediately.**

After this lesson, you will know how to:
- Correctly interpret `cancel(true)`, `cancel(false)`, the return value, `isCancelled()`, `isDone()`, and `get()`.
- Distinguish between **the state of the Future** and **the actual execution lifecycle of the code inside Callable/Runnable**.
- Write tasks that **cooperate with interruption** and manage cleanup in `finally`.
- Understand why a task that ignores interrupts can continue working **after the Future is already cancelled**.
- Distinguish between `Future.get(timeout, unit)` merely timing out the wait and **cancelling the task**.
- Cancel tasks **before they start**, while they are running, and after they have completed; handle races at the boundaries.
- Avoid misconceptions about blocking I/O, synchronized/locks, CPU-bound loops, `CompletableFuture.cancel(true)`, and executor shutdown.
- Design timeouts, cancellation, idempotency, resource cleanup, and verify them with **Java 17+** examples.

**Scope:** Java SE, `java.util.concurrent`, and Java concurrency in general. Spring-specific mechanisms are omitted since Spring-related topics have their own chapter.

## 2. Future Represents a Result, Not a Forceful Kill Switch

`Future<V>` represents the **final result of an asynchronous computation**, providing:
- `get()`: waits for and retrieves the result if the task completes normally; may throw `ExecutionException` if the task fails.
- `get(timeout, unit)`: waits **up to a specified duration** and throws `TimeoutException` if the result is not yet available.
- `cancel(boolean)`: requests cancellation according to the implementation's contract.
- `isCancelled()`: whether the task was marked as cancelled **before completing normally**.
- `isDone()`: whether the computation has **completed, failed, or been marked as cancelled**.

Commonly observed states:

~~~text
         submit
            |
            v
       Not started --------------+
            |                    |
            v                    |
         Running                 |
          /   \                  |
         /     \                 |
  Completed  Exception           |
         \     /                 |
          \   /                  |
           v v                   |
        Done normally/           |
        Done with error          |
                                 |
       cancel(...) succeeded ----+
                   |
                   v
           Future cancelled
          isDone == true
          isCancelled == true
          get() -> CancellationException

The thread may still continue running after the Future is cancelled.
~~~

This is a diagram of the **observable states of a Future**, not a complete diagram of every thread/JVM state. A task may receive an interrupt signal and then need additional time for cleanup. A task that **ignores** interrupts can even keep running until it finishes on its own, even though its result will no longer be published by the Future.

**`isDone() == true` does not mean "the thread has stopped"**. It only indicates that the computation represented by the Future has reached a completed state according to its contract, and **cancellation is a form of completion**.

## 3. What Do cancel(true) and cancel(false) Exactly Mean?

Interface signature:

~~~java
boolean cancel(boolean mayInterruptIfRunning);
~~~

| Scenario | `cancel(true)` | `cancel(false)` |
| --- | --- | --- |
| Task is still in the queue, not yet running | If cancellation succeeds, the task will not be executed | Same: the cancelled task will not be executed |
| Task has started but not yet completed | Requests cancellation; implementations like `FutureTask` may/attempt to interrupt the worker | Requests cancellation **without requesting an interrupt** on the running worker |
| Task already completed before the call | Usually returns `false`; the result is already fixed | Same |
| Cancellation was accepted | `isCancelled()==true` and `isDone()==true` | Same |
| Can the task still execute code after cancel? | **Yes**, if the task does not cooperate or has not observed the interrupt yet | **Yes** if the task is running, because no interrupt was requested |
| `get()` after the Future is cancelled | Throws `CancellationException` | Same |

Note that `cancel(true)` **is not a replacement for `Thread.stop()`**: it is not an unconditional thread-kill command. It only sets the Future's cancellation state and requests an interrupt when the implementation supports it; task code must **cooperate** to stop properly. `Thread.stop()` should not be used because it can leave objects in an inconsistent state.

### Return Value true/false

- `true`: the call **succeeded in transitioning the Future to the cancelled state** according to the contract; **it does not prove the worker has finished**.
- `false`: cancellation could not be performed, for example because the computation has already completed or is already in a non-cancellable state according to the implementation. Do not use `false` alone to conclude "the task completed successfully": it could have failed or been cancelled earlier.
- `cancel(true)` can race with the task finishing on its own. Whichever wins first determines the outcome of the cancel call depending on timing; code must tolerate both paths.
- If the state is cancelled, subsequent `get()` calls throw `CancellationException` and do not return the result computed by the task, even if code inside the worker continues to run.

With `ExecutorService.submit(...)` in standard Java executors, the Future is typically implemented based on `FutureTask` and supports interrupting the worker when `cancel(true)` succeeds while the task is running. However, **Future is an interface**; other implementations may have different cancellation policies, so you must read the specific contract.

### CancellationException Is Not InterruptedException

`Future.get()` can throw different exceptions:
- `CancellationException` (*unchecked*): **the Future is in the cancelled state**.
- `InterruptedException` (*checked*): **the thread calling `get`** was interrupted while waiting; it does not mean the task was necessarily cancelled.
- `ExecutionException` (*checked*): the computation completed with an error stored in the Future.
- `TimeoutException` (*checked*, with timed get): the caller did not receive the result within the wait period; the task **may still be running and the Future may not be cancelled**.

These are four distinct situations. Do not catch `TimeoutException` and report "task cancelled" unless you actually called `cancel` and checked the result.

## 4. Interruption Works as a Cooperative Request

Every Java `Thread` has an **interrupt status**. `Thread.interrupt()` sets that status and affects certain waiting operations; different APIs react differently.

A CPU-bound task should check the status itself:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    doSmallUnitOfWork();
}
// Exit the loop and perform cleanup.
~~~

This snippet assumes `doSmallUnitOfWork()` is already declared and is not a standalone program. Work must be broken into small enough units to check the status; if a processing loop runs for minutes without checking, cancellation will be slow.

A task using an interruptible API such as `Thread.sleep()`, `Object.wait()`, `BlockingQueue.take()`, `CountDownLatch.await()`, or `Condition.await()` may receive an `InterruptedException`. Under the contract of these common operations, when the exception is thrown, **the interrupt status is cleared**.

An example `Callable` that lets the exception propagate:

~~~java
Callable<String> task = () -> {
    while (true) {
        Thread.sleep(1_000);
        doSmallUnitOfWork();
    }
};
~~~

This is a snippet requiring `import java.util.concurrent.Callable` and the assumed method declaration. When `sleep` is interrupted, the lambda can exit via `InterruptedException`; a cancelled Future still does not transition back to a normal completion state.

If you must catch `InterruptedException` and the current layer cannot propagate it, one handling pattern is:

~~~java
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Restore interrupt status.
    return;
}
~~~

This is an illustrative snippet inside a `void` method. Most importantly, **exit or handle the cancellation policy explicitly**—do not swallow the exception and then resume waiting indefinitely.

### Two Ways to Check Interrupt Status

- `Thread.currentThread().isInterrupted()`: checks **without clearing** the status.
- `Thread.interrupted()`: a static method that checks **and clears** the status of the **current thread**.

If you accidentally use `Thread.interrupted()` to check multiple times without saving the result, you may clear the cancellation request. Use `isInterrupted()` when you only want to know whether to stop.

## 5. Java 17 Example: A Task That Cooperates with cancel(true)

The program creates a task with an interruptible `Thread.sleep()` loop. Main waits for the task to start, calls `cancel(true)`, waits for the worker to actually exit the task via a latch, and then inspects the `Future`. It does not rely on arbitrary sleeps for timing.

Create file **`CooperativeCancellationDemo.java`**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class CooperativeCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);

        try {
            Callable<String> work = () -> {
                started.countDown();
                try {
                    while (true) {
                        Thread.sleep(60_000);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "stopped-by-interrupt";
                } finally {
                    exited.countDown();
                }
            };

            Future<String> future = pool.submit(work);
            started.await();

            boolean accepted = future.cancel(true);
            exited.await(); // Unlike Future.isDone(): wait for the task to actually exit.

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("isCancelled=" + future.isCancelled());
            System.out.println("isDone=" + future.isDone());
            System.out.println("workerExited=" + (exited.getCount() == 0));

            try {
                System.out.println("result=" + future.get());
            } catch (CancellationException e) {
                System.out.println("get=CancellationException");
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(1, TimeUnit.MINUTES)) {
                System.out.println("executor-not-terminated");
            }
        }
    }
}
~~~

Run:

~~~bash
javac CooperativeCancellationDemo.java
java CooperativeCancellationDemo
~~~

Stdout on a normal execution path, when the worker cooperates and the executor terminates:

~~~text
cancelAccepted=true
isCancelled=true
isDone=true
workerExited=true
get=CancellationException
~~~

**Analysis:**
1. `started.await()` ensures the worker has entered the callable; the task cannot finish on its own because it continuously waits in `sleep`.
2. `cancel(true)` on the Future returned by the executor marks it cancelled and requests an interrupt.
3. `Thread.sleep` observes the interrupt via `InterruptedException`, the worker proceeds to `finally`, and counts down the `exited` latch.
4. `exited.await()` verifies that the worker **has actually exited the callable**, which `future.isDone()` after cancellation **does not prove on its own**.
5. Even though the callable has a `return "stopped-by-interrupt"` branch, the Future is already cancelled, so `future.get()` throws `CancellationException` rather than returning that string.
6. `shutdownNow` in `finally` avoids leaving the worker alive if an error occurs mid-way; this is still a best-effort cancellation mechanism, not a guarantee that every uncooperative task will stop.

Note that the demo uses `exited.await()` without a timeout to illustrate the signal confirming worker termination. In production code, you should use a **deadline** for shutdown waiting and have a strategy for handling tasks that do not respond to interruption.

## 6. Why a Cancelled Future Does Not Mean the Worker Has Stopped

This is the most important limitation of `cancel(true)`. A task might:
- Neither call an interruptible API nor check `isInterrupted()`.
- Catch `InterruptedException` and ignore it, continuing its work.
- Be in a native operation or blocking I/O that does not respond to interruption immediately.
- Hold a lock or execute a long callback before reaching a check point.
- Be in `finally` cleanup, possibly still performing side effects after the Future has been marked cancelled.

### Java 17 Example: A Task Intentionally Ignoring Interrupts

The following program is **intentionally designed to be uncooperative**: the worker waits on a latch, but if interrupted, it catches the exception and **keeps waiting**. Main cancels the Future first and only then allows the worker to finish. The demo proves that code can run after `cancel(true)`, without creating a busy CPU loop.

Create file **`UncooperativeCancellationDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class UncooperativeCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean sideEffectAfterCancel = new AtomicBoolean(false);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    while (true) {
                        try {
                            release.await();
                            break;
                        } catch (InterruptedException ignored) {
                            // INTENTIONALLY WRONG: ignore cancellation for demonstration.
                        }
                    }
                    sideEffectAfterCancel.set(true);
                    return "completed-despite-cancel";
                } finally {
                    exited.countDown();
                }
            });

            started.await();
            boolean accepted = future.cancel(true);

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureDone=" + future.isDone());
            System.out.println("workerExitedBeforeRelease="
                    + (exited.getCount() == 0));

            release.countDown();
            exited.await();

            System.out.println("sideEffectAfterCancel="
                    + sideEffectAfterCancel.get());
            System.out.println("futureStillCancelled=" + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get=CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac UncooperativeCancellationDemo.java
java UncooperativeCancellationDemo
~~~

Stdout on a normal execution path:

~~~text
cancelAccepted=true
futureDone=true
workerExitedBeforeRelease=false
sideEffectAfterCancel=true
futureStillCancelled=true
get=CancellationException
~~~

**What happened?**
- `cancel(true)` can interrupt the worker waiting on `release.await()`, but the code **intentionally swallows** `InterruptedException` and waits again.
- Immediately after cancel, `Future.isDone()==true`, while `exited` has not yet been counted down: the task has not finished.
- Main counts `release` down to 0. The worker proceeds to record a demonstrative side effect, finishes the callable, and counts down `exited`.
- The Future remains cancelled; `get()` throws `CancellationException` even though the worker logic returned normally.

This is an **anti-pattern** example, not a recommendation to ignore interrupts. In practice, the side effect could be a DB write, an HTTP request, a cache update, or mutating business data that the caller assumed would no longer happen.

**Design implication:** if correctness requires "never write the result after cancellation", `Future.cancel(true)` alone is not enough. You need coordination via a state machine, token/generation, idempotency, commit authority, or a handling protocol at the final resource. The worker must check cancellation **before the commit point**; if the commit belongs to an external system, that system must be designed accordingly.

## 7. cancel(false): Cancelling the Result Without Requesting a Worker Interrupt

`future.cancel(false)` is not a "gentler cancel that still guarantees stopping":
- If the task **has not started** and cancellation succeeds, the worker will not execute that work.
- If the task **has already started**, `FutureTask` can transition the Future to cancelled **without interrupting** the worker. The running task can continue computing or doing I/O until it stops on its own.
- The caller sees `get()` throw `CancellationException`, but cannot infer that the underlying activity has stopped.
- `cancel(false)` can be appropriate when you do not want to send an interrupt to an already-running task whose result you no longer need; this **does not immediately free** the thread pool slot.

When a task is implemented with `FutureTask`, the cancel decision is separate from the interrupt signal: one is changing the **Future's state**, and the other is attempting to affect the **executing thread**. In programs with multiple Future types, always check the implementation's Javadoc instead of assuming `FutureTask` details apply to all of them.

## 8. Cancelling Before the Task Starts: The Task Is Not Executed

When using a single-worker executor, we can intentionally keep the worker busy with a first task and put a second task in the queue. If we cancel the second task **before it runs**, its runnable is not invoked.

Create file **`CancelQueuedTaskDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelQueuedTaskDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch blockerStarted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean queuedWorkRan = new AtomicBoolean(false);

        try {
            Future<?> blocker = pool.submit(() -> {
                blockerStarted.countDown();
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            blockerStarted.await();

            Future<?> queued = pool.submit(() ->
                    queuedWorkRan.set(true));

            boolean accepted = queued.cancel(true);
            release.countDown();
            blocker.get();

            pool.shutdown();
            pool.awaitTermination(1, TimeUnit.MINUTES);

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("queuedWasExecuted=" + queuedWorkRan.get());
            System.out.println("queuedCancelled=" + queued.isCancelled());

            try {
                queued.get();
            } catch (CancellationException e) {
                System.out.println("queuedGet=CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac CancelQueuedTaskDemo.java
java CancelQueuedTaskDemo
~~~

Stdout when the executor operates normally:

~~~text
cancelAccepted=true
queuedWasExecuted=false
queuedCancelled=true
queuedGet=CancellationException
~~~

**Why the result does not depend on execution order:**
1. `newSingleThreadExecutor` executes only one task at a time.
2. The `blocker` task has already started and is waiting on `release`, so the second task can only be queued.
3. `queued.cancel(true)` is called before releasing `release`, so the queued task cannot have run yet.
4. When the worker processes the cancelled Future, the runnable's body is not executed; `queuedWorkRan` remains false.
5. `queued.get()` throws `CancellationException`.

**Limitation:** cancelling a Future waiting in a queue does not necessarily make it **disappear immediately from every internal queue structure**. How cancelled tasks are purged from the work queue and how memory is managed can depend on the executor/implementation. Do not assume "cancel succeeded" means the queue size decreases immediately.

## 9. Future.get(timeout) Does Not Automatically Cancel the Task

`Future.get(timeout, TimeUnit.MILLISECONDS)` only limits **how long the thread calling `get` waits for the result**. When `TimeoutException` is thrown:
- The Future **may still be running** or waiting in the queue.
- `isCancelled()` usually remains false, unless another party cancelled it.
- The task **does not automatically receive an interrupt** just because the caller's `get` timed out.
- The caller must decide whether to call `future.cancel(true)` or let the task continue working.

### Java 17 Example: Timeout Belongs Only to the Caller

Create file **`TimedGetDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class TimedGetDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> future = pool.submit(() -> {
                started.countDown();
                release.await();
                return 42;
            });

            started.await();

            try {
                future.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("get=TimeoutException");
            }

            System.out.println("cancelled=" + future.isCancelled());
            System.out.println("doneBeforeRelease=" + future.isDone());

            release.countDown();
            System.out.println("resultAfterRelease=" + future.get());
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac TimedGetDemo.java
java TimedGetDemo
~~~

Stdout when main is not interrupted and the task operates normally:

~~~text
get=TimeoutException
cancelled=false
doneBeforeRelease=false
resultAfterRelease=42
~~~

The task is blocked at `release.await()` while main calls `get(20ms)`. After 20ms, main receives `TimeoutException`, but the Future is not cancelled; after `release.countDown()`, the task completes and `get()` returns 42.

**Common pitfall:** the caller times out and retries another business operation while the old task is still running. Both tasks can cause side effects together (placing an order twice, writing data twice, etc.). Limiting the result wait time **does not replace** a deadline on the remote operation itself, does not replace cancellation, and does not replace idempotency.

### Pattern for Deadline and Cancel on Timeout

~~~java
try {
    return future.get(timeout, TimeUnit.MILLISECONDS);
} catch (TimeoutException e) {
    boolean cancelAccepted = future.cancel(true);
    // Log/update status as required.
    // cancelAccepted does not guarantee that the worker has actually stopped.
    throw e;
}
~~~

This is a snippet **inside a method with an appropriate future, timeout, and return type**; it requires importing `TimeoutException` and `TimeUnit`. If the caller's timeout is part of an end-to-end deadline, total time spent in queues, I/O, retries, and cleanup must all be accounted for; merely adding `get(timeout)` does not establish a deadline for the entire business operation.

## 10. An Easily Misunderstood Limitation: CompletableFuture.cancel(true)

`CompletableFuture<T>` implements `Future<T>` but has its own cancellation policy. According to the Java 17 Javadoc, **the `mayInterruptIfRunning` parameter has no effect in the `CompletableFuture` implementation because interruption is not used to control processing**.

Therefore, if `CompletableFuture.supplyAsync(...)` has already started:
- `cf.cancel(true)` can transition the CompletableFuture to the cancelled state.
- Callers of `cf.get()`/`cf.join()` observe cancellation according to the CompletableFuture contract.
- **You must not infer** from `cancel(true)` that the thread executing `supplyAsync` was interrupted.
- The worker can keep running, perform side effects, or finish the calculation, though it cannot cause a cancelled CompletableFuture to publish a normal result again.
- Dependent stages may complete exceptionally/with cancellation depending on the dependency graph; there is no guarantee of interrupting the corresponding threads.

### Java 17 Example: Cancelling CompletableFuture Does Not Interrupt the Worker

Create file **`CompletableFutureCancelDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableFutureCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch exited = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);

        try {
            CompletableFuture<String> cf =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                            return "work-finished";
                        } catch (InterruptedException e) {
                            sawInterrupt.set(true);
                            Thread.currentThread().interrupt();
                            return "interrupted";
                        } finally {
                            exited.countDown();
                        }
                    }, pool);

            started.await();
            boolean accepted = cf.cancel(true);

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + cf.isCancelled());
            System.out.println("workerExitedBeforeRelease="
                    + (exited.getCount() == 0));

            release.countDown();
            exited.await();

            System.out.println("interruptObserved=" + sawInterrupt.get());

            try {
                cf.join();
            } catch (CancellationException e) {
                System.out.println("join=CancellationException");
            }
        } finally {
            release.countDown();
            pool.shutdownNow();
            pool.awaitTermination(1, TimeUnit.MINUTES);
        }
    }
}
~~~

Run:

~~~bash
javac CompletableFutureCancelDemo.java
java CompletableFutureCancelDemo
~~~

Stdout on a normal execution path with a worker receiving no external interruption:

~~~text
cancelAccepted=true
futureCancelled=true
workerExitedBeforeRelease=false
interruptObserved=false
join=CancellationException
~~~

This is a very memorable difference between a **Future returned by an executor** and a **CompletableFuture in an asynchronous pipeline**. Do not assume all implementations of `Future.cancel(true)` interrupt the task runner the same way. If you need a cancellation channel with specific interruption, you must manage the corresponding task handle/`FutureTask`, timeout, and cancellation token in your own abstraction.

## 11. Operations That Often Do Not Respond to Interruption as Expected

### 11.1. CPU-Bound Loops Without Flag Checks

Wrong example:

~~~java
while (true) {
    performCpuWork(); // Does not check interrupt or cancellation token.
}
~~~

`cancel(true)` can set the interrupt status, but **it does not automatically insert a `break` branch** into the loop. The task can continue forever. Split CPU work into small chunks and check `Thread.currentThread().isInterrupted()` at checkpoints.

### 11.2. Waiting for a Monitor Lock with synchronized

A thread trying to **enter `synchronized(lock)`** can be in `Thread.State.BLOCKED`. Normal interruption **does not cause `synchronized` monitor contention to throw `InterruptedException` or give up**. When it eventually acquires the monitor, the code must check for interrupt/cancellation if it wants to stop.

If you need interruptible lock acquisition, consider `ReentrantLock.lockInterruptibly()` or `tryLock(timeout, unit)`, ensuring `unlock()` in `finally`. Each API has its own semantics; do not switch locks just hoping cancel will succeed without considering the business protocol.

### 11.3. Blocking I/O

There is no universal guarantee that `Thread.interrupt()` immediately interrupts **every** `InputStream.read()`, socket/file I/O, or native blocking call across all JDKs. For example:
- With some `InterruptibleChannel` implementations, interruption while blocked can close the channel and throw `ClosedByInterruptException`.
- Some traditional sockets/streams rely on timeouts, `close()`, or specific I/O implementations; `Socket#setSoTimeout` sets the maximum read wait time for the corresponding APIs.
- A library/driver call may handle interruption according to its own contract, not the caller's wishes.

If a task is waiting on an external dependency, **the timeout of the specific I/O API** and **resource cleanup/closing** are often just as important as interrupts. Do not assume closing a resource from another thread is always safe: you must follow that resource's contract, lifecycle, and ownership.

### 11.4. Long Callbacks or Cleanup

Even a cooperative task may still run `finally` after being interrupted:
- Closing streams, returning connections, releasing locks.
- Recording metrics or completion states.
- Finishing an operation that cannot be abandoned mid-way without violating an invariant.

Therefore, the time between **cancel accepted** and **resource fully released** may be non-zero. For systems requiring clean shutdown, track completion via a latch/executor termination or a dedicated cleanup signal, not just `Future.isDone()` of the cancelled task.

## 12. Cancelling a Task and Shutting Down an Executor Are Two Different Levels

### shutdown()

`ExecutorService.shutdown()` stops accepting new tasks, but **already-submitted tasks are allowed to complete** per the contract. `shutdown()` does not mean sending interrupts to cancel all running tasks.

### shutdownNow()

`ExecutorService.shutdownNow()` **attempts** to stop actively executing tasks and halts the processing of waiting tasks. Common implementations use `Thread.interrupt()` to request running tasks to stop, but this is **best-effort**; if a task does not respond to interruption, it may continue. The method returns a list of tasks that had not started executing; how tasks/Futures are represented depends on the specific implementation.

### awaitTermination()

`awaitTermination(timeout, unit)` waits for the executor to reach the terminated state or for the timeout to expire (or for the caller to be interrupted). This is a **way to observe executor termination** after `shutdown()/shutdownNow()`, not something that automatically requests tasks to stop if you have not initiated shutdown.

Common pattern:

~~~java
pool.shutdown();
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            // Report uncooperative tasks or prolonged cleanup.
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
~~~

This is a snippet assuming `pool` is an already-initialized `ExecutorService`. The illustrative timeouts do not replace real SLOs; a complex service may need an overall deadline, control over I/O-blocking tasks, and tracking of unreleased resources.

**Do not assume calling `cancel(true)` on each Future is enough for a thread pool to shut down.** A task that ignores interrupts can prevent the executor from terminating and keep the entire process alive if non-daemon platform threads are used.

## 13. Protecting Business Invariants and Side Effects During Cancellation

Cancellation can arrive at many points:

~~~text
queued -> started -> validated -> remote call -> commit -> cleanup -> done
   |         |          |            |          |         |
   +---- cancel requested at any point in time -----------+
~~~

Risks:
- **Committed before cancel arrived:** the caller may see the Future cancelled, yet the side effect already happened; it cannot be rolled back by an interrupt.
- **Calling a remote API when cancel arrives:** the remote command may have already completed even though the caller did not receive the response; retrying can create duplicates.
- **Holding a lock when cancel arrives:** the task must ensure `finally` releases the lock; interruption does not automatically roll back state.
- **Partial state updated:** the task must not abort mid-way leaving an invalid invariant, such as decrementing inventory without recording the corresponding order.
- **Task is cancelled but still running:** it may publish its result late, overwriting the state of a replacement task.

Defensive designs:
1. **Idempotency key:** the same business request has only one accepted effect at the system performing the side effect.
2. **Generation/version/token:** only the currently valid execution is authorized to publish/commit the result; an old cancelled task cannot overwrite a newer version.
3. **Explicit state:** `NEW -> RUNNING -> COMMITTING -> SUCCEEDED/FAILED/CANCELLED` following a protocol with atomic transitions where needed.
4. **Transaction/compensation:** when updating multiple resources, define rollback or compensation if mid-way interruption leaves partial state.
5. **Cancellation checkpoints:** check interrupt/token before heavy steps and right before commit when possible; an atomic protocol is still needed to avoid a race between "checked" and "commit".
6. **Bounded waits:** timeouts for I/O, lock waits, and cleanup; do not rely solely on timed `get`.
7. **Ownership-aware cleanup:** try-with-resources and `finally`, returning connections, releasing semaphores, unlocking; do not let a cancelled task hold resources indefinitely.

### Important Note on "Checking Before Commit"

The following is **not enough** if you must strictly guarantee no commit occurs after cancellation:

~~~java
if (!Thread.currentThread().isInterrupted()) {
    commitToExternalSystem();
}
~~~

A cancel can arrive **after the check but before the commit**. If the business contract requires excluding side effects from cancelled tasks, there must be a commit-authorization protocol at the target system or a unified atomic state transition; merely checking the interrupt flag is insufficient.

## 14. Future.cancel(true) and Other Future Models

### FutureTask

`FutureTask<V>` is an implementation that can run a `Callable`/`Runnable`. When cancelling a running task with `cancel(true)` and it succeeds, it attempts to interrupt the running thread. Even if the task continues running, the result state of the FutureTask remains cancelled. In common executors, `submit` creates tasks following this pattern or an equivalent.

### ScheduledFuture

`ScheduledExecutorService.schedule(...)` and periodic methods return a `ScheduledFuture`; cancelling can prevent subsequent scheduled executions. For an **already-running** execution, `mayInterruptIfRunning` still only carries the semantics of the corresponding implementation. For periodic tasks, cancellation does not undo previous side effects. The policy for removing cancelled tasks from the delay queue also depends on the executor (e.g., `ScheduledThreadPoolExecutor#setRemoveOnCancelPolicy`); do not assume cancellation immediately shrinks the memory queue.

### CompletableFuture

`CompletableFuture.cancel(true)` **does not use interrupts to control the task** in the Java 17 implementation. It is a way to **complete the future exceptionally** and affects dependent stages, but it is not equivalent to `FutureTask.cancel(true)`. To actually request the task to stop, you need a cancellation channel supported by the work itself.

### Thread and ForkJoinTask

If managing `Thread` directly, `thread.interrupt()` is only a cancellation request; you do not automatically get a result Future. For `ForkJoinTask`, cancellation/interrupt semantics should likewise not be inferred from `FutureTask`; read the documentation of the specific implementation. **Do not build a generic abstraction assuming "every Future interrupts the worker on cancel(true)"**.

## 15. Common Mistakes

| Misconception or Mistake | Consequence | How to Handle |
| --- | --- | --- |
| `cancel(true) == true` interpreted as the thread having stopped | Side effects/cleanup may still run | Track task exit or use a dedicated completion protocol |
| `isDone() == true` interpreted as work succeeding | Cancel and exceptions also count as done | Check `isCancelled()`, handle `get()` properly |
| `get()` after cancel expected to return the computed task result | Actually throws `CancellationException` | Separate Future state from worker behavior |
| Catching `InterruptedException` and continuing indefinitely | Task does not cooperate with cancellation | Propagate or restore status and exit |
| Using `Thread.interrupted()` to check while ignoring the return value | Clears the interrupt status | Use `isInterrupted()` when you want to read without clearing |
| CPU loop without checking any flag | Does not respond to cancel | Add checkpoints and process work in chunks |
| Waiting on contended `synchronized` and expecting interrupt to release immediately | No contract like `lockInterruptibly` | Use an appropriate lock API or reconsider lock structure |
| Assuming all I/O stops on interrupt | Task remains blocked | Use I/O API-specific timeouts/close |
| `get(timeout)` interpreted as the task being cancelled | Task keeps running, easy to trigger duplicate retries | Call `cancel` explicitly if needed and protect idempotency |
| `cancel(false)` interpreted as the task will stop | Running task can continue | Understand "do not request interrupt" semantics |
| `CompletableFuture.cancel(true)` interpreted as interrupting the worker | Incorrect for Java 17 | Add a dedicated cancellation token/task handle |
| Using `shutdownNow()` and assuming the executor definitely terminated | Noncooperative workers can continue | Use `awaitTermination` with a deadline and alerting |
| Stopping between two shared-state updates | Broken business invariant | Protect commit/rollback, cleanup in `finally` |
| Cancelling an old task and immediately submitting a new one without a version guard | Late result from the old task overwrites new data | Use generation/version/idempotent commit |
| Not setting timeouts for downstream I/O | Cancel may fail to free the worker | Set timeouts at the right API and limit concurrency |
| Not verifying whether running tasks release resources | Connection, semaphore, or lock leaks | Try-with-resources, `finally`, completion metrics |

## 16. Reliable Cancellation Testing

A proper test must measure **two different things**:
1. **Future state:** what `cancel` returns, what `isCancelled/isDone` report, and what `get` throws.
2. **Execution state:** how far the callable ran, whether it exited, and whether cleanup and final side effects occurred.

How to test:
- **Use latches/barriers** to force the task to actually start or actually sit in the queue before cancelling; do not use `Thread.sleep(100)` as proof of execution order.
- Test cancellation **before starting**, while in `sleep/take/wait`, during CPU work, and when the task is uncooperative.
- Test both `cancel(true)` and `cancel(false)` on the actual implementation being used.
- Test `CompletableFuture.cancel(true)` separately: a cancelled result is not proof of interruption.
- Test `get(timeout)`: verify that the Future can still complete after the caller times out.
- Use `CountDownLatch exited` or `awaitTermination` to verify the worker/executor has actually stopped; **do not use `Future.isDone()` after cancel as a substitute assertion**.
- Ensure every test branch **releases latches in `finally`** and closes the executor so tests do not hang.
- When side effects matter, use a fake resource/gateway and verify there are no duplicates or overwrites after cancel; do not just check a boolean "cancel requested" variable.
- Test cases where interruption is caught/cleared or native I/O callbacks do not support cancellation; do not infer from one passing `sleep` test that all work is interruptible.
- Track metrics: cancel requests, cancel accepted, worker exits, cleanup duration, pool active count, queued count, timeouts, and tasks running past their deadline.

When measuring latency, distinguish:
- **Cancellation request latency:** time to call `cancel`.
- **Task stop latency:** from the cancellation request until the worker is no longer executing the task.
- **Resource release latency:** until all connections/locks/permits are returned.
- **Business finality latency:** until the system knows for certain whether the side effect succeeded, failed, or needs compensation.

These intervals **are not necessarily the same**.

## 17. Self-Check Questions

1. Does `Future.cancel(true)` returning `true` prove the worker has exited? **No.** It only proves the Future accepted cancellation per its contract.
2. Can a cancelled Future have `isDone() == true` while the runnable is still running? **Yes.**
3. After successful cancellation, what exception does `Future.get()` throw? **`CancellationException`**.
4. Does `Future.get(timeout)` throwing `TimeoutException` automatically interrupt/cancel the task? **No.**
5. If a `Callable` catches `InterruptedException`, ignores it, and keeps waiting, does `cancel(true)` force it to stop? **No.**
6. With `cancel(false)` on an already-running `FutureTask`, can the task continue? **Yes, because no interrupt was requested.**
7. Can cancelling a queued task before a worker picks it up prevent its runnable from running? **Yes, if cancellation succeeds according to that executor/Future.**
8. How do `Thread.currentThread().isInterrupted()` and `Thread.interrupted()` differ? **The first does not clear the flag; the second (static) method clears the current thread's flag.**
9. Why might a task trying to enter `synchronized` not stop immediately when interrupted? **Waiting for a monitor via `synchronized` is not an interruptible lock operation like `lockInterruptibly()`.**
10. Does an interrupt guarantee closing every socket or making every `InputStream.read()` return immediately? **No**, semantics depend on the API and implementation.
11. In Java 17, does `CompletableFuture.cancel(true)` interrupt the thread processing `supplyAsync`? **That is not the mechanism of the `CompletableFuture` implementation**; the `mayInterruptIfRunning` flag has no effect.
12. Does `shutdownNow()` guarantee that all tasks have stopped? **No, it is only a best-effort attempt.**
13. Why can a cancelled Future still create a database record? **The worker may have committed before cancel, been in the middle of I/O, or continued running after the Future was cancelled.**
14. Why is checking interrupt right before sending an external request still not enough to guarantee no side effects after cancellation? **There is a race between the check and the commit; idempotency or a commit protocol is required.**
15. When should you restore the interrupted flag in a `catch` block? **When the code cannot propagate `InterruptedException` and needs the calling layer to know about the interrupt request while exiting/following the cancellation policy.**
16. How do `CancellationException` and `InterruptedException` from `get()` differ? **The first indicates the Future was cancelled; the second indicates the thread calling `get` was interrupted.**
17. When cancelling a queued task, can you assert it is immediately removed from every executor queue? **No; how queued/cancelled tasks are managed depends on the implementation.**
18. If a task is cancelled but you still need to ensure resources are closed, what must you track? **Execution completion and cleanup via a dedicated protocol, not just `isDone`.**

## 18. Conclusion

`Future.cancel(true)` is a **cancellation request that may send an interrupt**, not a mechanism to forcefully halt Java code. When cancellation is accepted, the Future can immediately report `isCancelled()==true` and `isDone()==true`; `get()` throws `CancellationException`, yet the worker **may still be running, cleaning up, or producing side effects**.

Tasks must cooperate with interruption, choose appropriate I/O APIs with timeout/cancellation support, and release resources in `finally`. `get(timeout)` only bounds the caller's wait time, while `CompletableFuture.cancel(true)` in Java 17 **does not use interrupts** to control the worker. For business operations with non-repeatable side effects, add **idempotency, commit authorization, explicit completion states, and stop-latency monitoring**; never take the return value of `cancel` as proof that all consequences have vanished.

## Java SE 17 References

- [Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): `cancel`, `isCancelled`, `isDone`, `get`, and timeouts.
- [FutureTask](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html): task result and cancellation implementation.
- [ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `submit`, `shutdown`, `shutdownNow`, `awaitTermination`.
- [Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `interrupted`, and `isInterrupted`.
- [CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): `cancel` and the `mayInterruptIfRunning` note.
- [ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): `lockInterruptibly`, `tryLock`.
- [InterruptibleChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/InterruptibleChannel.html): closing a channel when interrupted while blocked and `ClosedByInterruptException`.
