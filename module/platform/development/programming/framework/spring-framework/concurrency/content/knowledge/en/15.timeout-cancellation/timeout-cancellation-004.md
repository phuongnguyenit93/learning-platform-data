# Future.cancel(true) and Cooperative Interruption

**Cancelling a Future does not mean forcibly killing a Java thread.** This is the most important principle when handling expired tasks, user-cancelled requests, or executor shutdown in **Spring Framework - concurrency**.

With a Future created by **ExecutorService.submit** and typically implemented by **FutureTask**, calling **cancel(true)** attempts to transition the Future to the cancelled state; if the work has already started and the implementation knows the executing thread, it can send a **Thread.interrupt()** request to that thread. Whether the work actually stops quickly and releases resources **depends on the task's own code and the APIs it is waiting on**.

An important contrast: standard Java's **CompletableFuture.cancel(true)** treats cancellation as a form of **exceptional completion**; the `true` parameter **has no effect for interrupting the computation** in this implementation. Therefore, you cannot see the same `cancel` method name and conclude both implementations behave identically toward the worker.

This lesson belongs to **Timeouts and Cancellation**. After this lesson, you should be able to distinguish Future state from task liveness, write interrupt-checking loops, handle `InterruptedException` properly, design deadlines/cancellation in Spring `@Async`, and test with deterministic synchronization rather than guessing timings with `Thread.sleep`.

## 1. Three Distinct Concepts: Future, Task, and Thread

When a request submits a task to `ThreadPoolTaskExecutor` or `ExecutorService`, there are at least three entities:

1. **Future**: an object representing the result or cancellation/completion state under the API contract.
2. **Task**: the actual running logic; it may be sitting in the queue, executing, blocked on I/O, or about to finish.
3. **Worker thread**: the resource executing the task; in a thread pool, workers are normally **reused** for subsequent tasks.

~~~text
HTTP caller                         ExecutorService / ThreadPool
     |                                        |
     +-- submit(callable) ------------------->| queue/task
     |                                        |     |
     |<------------------------ Future<T> ----+     v
     |                                          worker runs task
     |
     +-- future.cancel(true)
     |          |
     |          +-- requests cancelling Future
     |          +-- may interrupt worker if implementation supports it
     |
     +-- future.isCancelled() == true
                        |
                        +-- does NOT prove worker stopped all side effects
~~~

**isDone() == true** only indicates that the Future has reached a completion state under the contract, including **success, failure, or cancellation**; it is not an answer meaning “all Java code inside the task has exited and cleaned up resources”.

When designing business logic, separate:

- **Cancellation requested**: a component asked to stop.
- **Future cancelled**: the Future object is marked cancelled.
- **Execution stopped**: the task code exited its processing loop or blocking call.
- **Cleanup complete**: resources, locks, connections, files, and business state were reclaimed/handled.
- **Business effect committed**: external effects, such as a money transfer or DB write, may not be reversed just because the caller cancelled the Future.

An application that looks solely at `Future.isCancelled()` to confirm all of the levels above is flawed by design.

## 2. The Future.cancel(mayInterruptIfRunning) Contract

Java declares:

~~~java
boolean cancel(boolean mayInterruptIfRunning);
boolean isCancelled();
boolean isDone();
V get() throws InterruptedException, ExecutionException;
V get(long timeout, TimeUnit unit)
        throws InterruptedException, ExecutionException, TimeoutException;
~~~

This is an **abbreviated summary of the `Future<V>` interface**, not a standalone compilable Java file.

According to the **Future** contract:

- If the work has not started yet, once successfully cancelled it **should not be run**.
- If the work has already started, **mayInterruptIfRunning = true** allows the implementation to **request interrupting the executing thread**, when the implementation knows that thread.
- If **mayInterruptIfRunning = false**, do not request interrupting the running thread; currently executing work may continue.
- If the task has already completed, cancellation normally has no effect.
- The **boolean** value returned by `cancel` reflects the result of the cancellation attempt per implementation; **do not use it alone to infer the worker stopped**. Use `isCancelled()` to inspect Future state.
- After a Future is cancelled, **get()** or **get(timeout, unit)** throws **CancellationException** (unchecked) instead of returning a computed result.
- **isDone()** returns true for a Future that completed normally, failed, or was cancelled; a task cannot be considered “successful” from `isDone()` alone.

### Comparing cancel(false) and cancel(true)

| Situation | cancel(false) | cancel(true) |
| --- | --- | --- |
| Task has not started yet | May mark cancelled so body does not run | Same |
| Task running in FutureTask | May mark Future cancelled without **sending interrupt** | Attempts to **interrupt** the thread running the task |
| Code blocked in sleep/wait/CountDownLatch.await | `false` parameter does not wake it | Interrupt can cause the API to throw `InterruptedException` |
| CPU computation not checking interrupt flag | Can continue running | **Can still continue running** |
| Code with committed side effects | Does not undo side effects | Does not undo side effects |
| Standard CompletableFuture | Marks Future cancelled | **Same semantics; `true` does not drive interruption** |

**Do not confuse `cancel(false)` with “cannot cancel a running task”.** For example, `FutureTask` can transition the Future state to cancelled while **allowing the running computation to continue**. The eventual result is not delivered to the caller by the Future, yet side effects inside the task can still occur.

### Illustrative States

~~~text
NEW (queued) --cancel--> CANCELLED  (body should not run)
  |
  +--worker starts--> RUNNING --return--> SUCCESS
                            |
                            +--throws--> FAILURE
                            |
                            +--cancel(true)--> Future CANCELLED
                                                |
                                                +--worker may continue
                                                +--or cooperate and exit
~~~

This is a conceptual model, **not a standard state enum across all Future implementations**.

## 3. Thread.interrupt() Is a Signal, Not Thread.stop()

An interrupt call sends a **cooperative request** to a thread; it is unsafe to think of it as “killing the thread immediately”.

When `Thread.interrupt()` occurs, two situations typically arise:

1. **Thread is waiting in an interrupt-sensitive API**: e.g., `Thread.sleep()`, `Object.wait()`, `Thread.join()`, or `CountDownLatch.await()`. The API usually throws **InterruptedException** and **clears the interrupt flag** per the API contract.
2. **Thread is running CPU code or a non-interrupt-responsive API**: the interrupt flag is set; code must **check and exit** at an appropriate point, or the blocking API must support interruption under its own contract.

Interrupts can behave differently with NIO `InterruptibleChannel`, `Selector`, and certain specialized blocking operations. Never assume every socket client, JDBC driver, HTTP client, or native call stops immediately on interrupt.

**Do not use `Thread.stop()`** to “force” a task to stop. Forcibly stopping a thread can leave invariants inconsistent and locks/resources in a dangerous state. Proper design usually requires a signal + interrupt checkpoints + intentional cleanup.

### The Interrupt Flag and Two Ways to Check It

~~~java
boolean interrupted = Thread.currentThread().isInterrupted();

boolean wasInterruptedAndClearFlag = Thread.interrupted();
~~~

These are **two illustrative lines**, not a standalone Java file.

- **isInterrupted()**: checks the status without **clearing the flag**.
- **Thread.interrupted()**: a static method that checks the status of **the current thread** and **clears the interrupt flag**.

Therefore, in a CPU-bound loop with an interrupt condition, one typically writes:

~~~java
while (!Thread.currentThread().isInterrupted()) {
    performSmallUnitOfWork();
}
~~~

This is an **illustrative snippet** assuming `performSmallUnitOfWork` is defined. If code calls `Thread.interrupted()` repeatedly without reason, it can consume the interrupt signal and prevent another layer from observing the stop request.

## 4. InterruptedException: Must Be Handled to Cooperate in Stopping

Many blocking Java APIs declare **throws InterruptedException**. When catching this exception, one of two proper paths is usually taken:

**A. If the method can declare `throws InterruptedException`, propagate it to the layer owning the policy:**

~~~java
void waitForSignal(CountDownLatch latch)
        throws InterruptedException {
    latch.await();
}
~~~

This is an **illustrative method snippet** requiring `CountDownLatch` imported. Propagating the exception lets the caller decide cancellation and cleanup.

**B. If you cannot propagate `InterruptedException` (e.g., `Runnable.run()`), restore the interrupt flag and exit cleanly:**

~~~java
@Override
public void run() {
    try {
        blockingOperation();
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return; // Do not treat interruption as successfully completed work.
    } finally {
        releaseOwnedResources();
    }
}
~~~

This is an **illustrative snippet** in a class with `blockingOperation` and `releaseOwnedResources`.

Why restore the flag? Many APIs like **sleep/await** clear the interrupt status when throwing `InterruptedException`. If you cannot rethrow the exception, calling **Thread.currentThread().interrupt()** preserves the knowledge that an interrupt was requested before exiting the method. **Do not continue executing business logic** as if nothing happened.

**The wrong way:**

~~~java
try {
    Thread.sleep(1_000);
} catch (InterruptedException ignored) {
    // Swallows the signal and keeps looping indefinitely.
}
~~~

If this sits inside a multi-iteration loop, every interrupt can be swallowed while the task continues holding the worker. The caller thinks it cancelled, yet the system keeps logging, querying the DB, or sending requests.

### When Should You Not Simply Re-Interrupt and Continue?

- When the method can **throw InterruptedException**: letting the caller enforce an explicit cancellation policy is usually better.
- When an important cleanup step itself might be interrupted: define a specific cleanup strategy, deadline, and flag-restoration rule.
- When the task owns a transaction/connection: avoid continuing to commit business logic after receiving cancellation, unless the business contract requires finishing an already-started step.

A catch block that merely logs “interrupted” and **does not stop work** usually breaks the cancellation contract.

## 5. Complete Java 17 Example: cancel(true) Wakes a Blocked Task

The first example uses **ExecutorService.submit()**, obtains the task's Future, and cancels with **cancel(true)**. The task uses `CountDownLatch.await()` to wait; upon receiving the interrupt, it records the signal, restores the interrupt flag, exits, and runs cleanup in `finally`.

Create file **CooperativeCancelDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        AtomicBoolean cleanup = new AtomicBoolean(false);

        try {
            Future<String> future = pool.submit(() -> {
                started.countDown();
                try {
                    neverReleased.await();
                    return "unreachable";
                } catch (InterruptedException e) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "ignored-result";
                } finally {
                    cleanup.set(true);
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker has not started");
            }

            boolean accepted = future.cancel(true);

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Worker did not exit after interrupt request");
            }

            boolean cancelledGet = false;
            try {
                future.get();
            } catch (CancellationException expected) {
                cancelledGet = true;
            }

            System.out.println("cancel(true) succeeded: " + accepted);
            System.out.println("Future isCancelled: "
                    + future.isCancelled());
            System.out.println("Future isDone: " + future.isDone());
            System.out.println("Worker saw interrupt: "
                    + sawInterrupt.get());
            System.out.println("Cleanup ran: " + cleanup.get());
            System.out.println("get threw CancellationException: "
                    + cancelledGet);
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Pool did not terminate");
            }
        }
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 CooperativeCancelDemo.java
java CooperativeCancelDemo
~~~

**Stdout**, when the environment lets the worker start and exit within the test timeouts:

~~~text
cancel(true) succeeded: true
Future isCancelled: true
Future isDone: true
Worker saw interrupt: true
Cleanup ran: true
get threw CancellationException: true
~~~

**Why is this example deterministic?**

1. `main` waits on **started**, guaranteeing the task genuinely started before `cancel` is called.
2. The task blocks at **CountDownLatch.await()**, so it cannot complete on its own without an interrupt or someone opening the latch.
3. **FutureTask**, typically used by `ExecutorService.submit`, can interrupt the running thread. **cancel(true)** sends the signal.
4. `await` reacts to the interrupt with `InterruptedException`; the task marks **sawInterrupt**, executes `finally`, and stops.
5. `main` waits on **finished** before checking `cleanup`. Hence stdout has **no race** between the cleaning-up thread and the printing thread.
6. **future.get()** throws `CancellationException` because the Future state was cancelled. The **ignored-result** value that the `Callable` may return **is not published as a successful result**.
7. `main` closes the executor in `finally` to prevent worker leaks after the example.

**Limitation:** these booleans verify behavior in this example using `FutureTask` and `CountDownLatch`. They are **not** a promise that `cancel(true)` will make a specific JDBC, HTTP client, or native I/O call stop immediately.

## 6. cancel(true) Is Not Enough if CPU Code Does Not Check Interrupts

A CPU-bound task such as parsing a large file, scanning millions of items, or batch computing may run without calling any blocking method that throws `InterruptedException`. In that case, an interrupt mainly **sets the thread's interrupt flag**. If the loop never checks the flag or a cancellation token, work can continue until it finishes on its own.

Example of a cooperative loop:

~~~java
long calculate(List<Integer> numbers) {
    long total = 0;

    for (int i = 0; i < numbers.size(); i++) {
        if (Thread.currentThread().isInterrupted()) {
            throw new java.util.concurrent.CancellationException(
                    "Stop requested");
        }

        total += numbers.get(i);
    }

    return total;
}
~~~

This is an **illustrative method snippet**; it requires importing `java.util.List`. The loop checks the interrupt at each step, then stops at a safe checkpoint. For very tiny operations, checking the flag too often can add overhead; you can check per block, provided the deadline and stop responsiveness remain acceptable.

**Key point:** cancellation is a protocol between requester and processor. Place checkpoints at business boundaries where stopping is safe, not in the middle of an operation that must complete atomically.

### Do Not Infer from Future.isDone() That the Loop Exited

If a `FutureTask` is cancelled while the task is still running a loop that ignores the flag, **Future.isDone() can be true** while the worker is still burning CPU. From the moment it is cancelled, the Future can no longer provide a reliable result or “worker actually stopped” signal. If you need cleanup confirmation, you must have **a separate execution-completion signal** or observe lifecycle/resources.

## 7. Java 17 Example: Future Cancelled While Task Keeps Running

The following example intentionally **ignores the interrupt flag** in a CPU loop to prove the difference between **Future cancellation** and **execution termination**. It has a separate `AtomicBoolean` so `main` can release the task and avoid holding the worker forever.

Create file **NonCooperativeCancelDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class NonCooperativeCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean stop = new AtomicBoolean(false);

        try {
            Future<?> future = pool.submit(() -> {
                started.countDown();
                try {
                    while (!stop.get()) {
                        // Intentionally ignore interrupt.
                        Thread.onSpinWait();
                    }
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker has not started");
            }

            boolean cancelled = future.cancel(true);

            System.out.println("Future cancel(true): " + cancelled);
            System.out.println("Future isDone: " + future.isDone());
            System.out.println("Future isCancelled: "
                    + future.isCancelled());
            System.out.println("Worker still running: "
                    + (finished.getCount() == 1));

            // Separate signal allowing the loop to exit.
            stop.set(true);

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not exit");
            }

            System.out.println("Worker finished: true");
        } finally {
            stop.set(true);
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
~~~

Commands:

~~~bash
javac -encoding UTF-8 NonCooperativeCancelDemo.java
java NonCooperativeCancelDemo
~~~

**Stdout** under normal conditions:

~~~text
Future cancel(true): true
Future isDone: true
Future isCancelled: true
Worker still running: true
Worker finished: true
~~~

**Explanation:**

- `started` confirms the `Runnable` entered the processing loop before `main` cancels.
- **cancel(true)** transitions the task's Future to cancelled and may set the interrupt flag on the worker.
- **The loop only observes `stop`**, ignoring the interrupt flag; it keeps running.
- `main` checks **finished.getCount() == 1** before setting `stop`, proving the worker had not entered `finally` at the moment the Future was already cancelled.
- When `main` sets `stop=true`, the worker exits, counts down `finished`, and physical work ends.

This is an **intentionally negative example** illustrating what not to do in production: a CPU-burning spin loop. It runs very briefly in the test and has a `finally` block to release the worker. Real computation loops should use cooperative checkpoints and avoid busy-spinning as a waiting mechanism.

## 8. Cancelling a Task Still in the Queue

A `FutureTask` can be cancelled **before work begins**. When a worker later pulls the cancelled wrapper from the queue, the actual `Callable`/`Runnable` body should not run.

With **ExecutorService.newSingleThreadExecutor**, you can verify this by holding the worker on a first task, pushing a second task into the queue, and cancelling the second task. This mechanism differs from interrupting a running thread.

Create file **CancelQueuedDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelQueuedDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch releaseFirst = new CountDownLatch(1);
        AtomicBoolean secondRan = new AtomicBoolean(false);

        try {
            Future<?> first = pool.submit(() -> {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }

            Future<?> queued = pool.submit(
                    () -> secondRan.set(true));

            boolean cancelled = queued.cancel(false);

            releaseFirst.countDown();
            first.get(5, TimeUnit.SECONDS);

            // Barrier behind the cancelled task: confirms the worker
            // processed all queued items submitted before the barrier.
            Future<?> barrier = pool.submit(() -> { });
            barrier.get(5, TimeUnit.SECONDS);

            boolean getCancelled = false;
            try {
                queued.get();
            } catch (CancellationException expected) {
                getCancelled = true;
            }

            System.out.println("Cancelled before running: " + cancelled);
            System.out.println("Second task body ran: "
                    + secondRan.get());
            System.out.println("get reported cancelled: " + getCancelled);
        } finally {
            releaseFirst.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CancelQueuedDemo.java
java CancelQueuedDemo
~~~

**Stdout:**

~~~text
Cancelled before running: true
Second task body ran: false
get reported cancelled: true
~~~

**Meaning:** `cancel(false)` can still cancel a task **that has not started**. There is no need to request interrupting the worker, because the first worker is still processing another task. After `releaseFirst` opens, the cancelled second task wrapper may be drained from the queue, yet **its body is never executed**.

**Do not equate a non-running task with an immediately emptied queue.** Cancelling a `FutureTask` does not necessarily purge its wrapper from **every queue implementation at the exact instant of `cancel`**. Different executor types (especially scheduled executors) have their own policies for purging cancelled tasks. Observe queue retention/cleanup per executor type rather than relying on one universal rule.

## 9. Crucial Difference: CompletableFuture.cancel(true) Does Not Send Interrupt

Java SE 17's **CompletableFuture** also implements `Future`, yet its Javadoc states clearly: cancellation in this implementation is equivalent to a form of **exceptional completion with `CancellationException`**, and the **mayInterruptIfRunning parameter has no effect** because interrupts are not used to control processing.

Example:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                () -> blockingComputation(), executor);

result.cancel(true);
~~~

This is an **illustrative snippet** with `blockingComputation` and `executor` in scope. You **cannot infer** that calling `cancel(true)` on `CompletableFuture` interrupted the worker running `blockingComputation`. The Future result can be marked cancelled while the supplier continues running and producing side effects.

### Deterministic Java 17 Example

Create file **CompletableCancelDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CompletableCancelDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean gotInterruptedException = new AtomicBoolean(false);

        try {
            CompletableFuture<String> future =
                    CompletableFuture.supplyAsync(() -> {
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException e) {
                            gotInterruptedException.set(true);
                            Thread.currentThread().interrupt();
                        } finally {
                            finished.countDown();
                        }
                        return "physical-computation-finished";
                    }, pool);

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker has not started");
            }

            boolean cancelled = future.cancel(true);

            System.out.println("CompletableFuture cancel: "
                    + cancelled);
            System.out.println("CompletableFuture isCancelled: "
                    + future.isCancelled());
            System.out.println("Worker has not exited await: "
                    + (finished.getCount() == 1));

            release.countDown();

            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not finish");
            }

            boolean getCancelled = false;
            try {
                future.get();
            } catch (CancellationException expected) {
                getCancelled = true;
            }

            System.out.println("Worker interrupted by cancel: "
                    + gotInterruptedException.get());
            System.out.println("get threw CancellationException: "
                    + getCancelled);
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Pool did not terminate");
            }
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 CompletableCancelDemo.java
java CompletableCancelDemo
~~~

**Stdout:**

~~~text
CompletableFuture cancel: true
CompletableFuture isCancelled: true
Worker has not exited await: true
Worker interrupted by cancel: false
get threw CancellationException: true
~~~

**Interpretation:**

1. The `Supplier` waits at `release.await`, and `main` knows the worker started via `started`.
2. **future.cancel(true)** switches the `CompletableFuture` state to cancelled, **without interrupting the worker** in the standard implementation.
3. The worker is still waiting on `release`, so `finished` has not reached 0.
4. `main` opens `release` itself so the supplier finishes; the supplier returning a `String` does not change the future's **already cancelled** state.
5. **get()** throws `CancellationException`; the output is not `physical-computation-finished`.

**Do not turn this into the claim “no API returning CompletableFuture can ever interrupt”.** A framework or library can add an external cancellation mechanism or another Future that controls the task. What is proven here is that **calling `CompletableFuture.cancel(true)` on the standard JDK implementation does not automatically send an interrupt**.

## 10. Impact on Dependent Stages of CompletableFuture

A multi-step pipeline:

~~~java
CompletableFuture<Integer> source =
        CompletableFuture.supplyAsync(
                () -> loadValue(), ioExecutor);

CompletableFuture<String> output = source
        .thenApply(n -> n * 2)
        .thenApplyAsync(n -> "score:" + n, cpuExecutor);
~~~

This is an **illustrative snippet** with dependencies in scope.

If **source** is cancelled before completing, incomplete dependent stages are transitioned into **exceptional completion** per `CompletableFuture` semantics; you may observe **CompletionException with CancellationException as its cause**.

If **output** is cancelled, that changes the state of the `output` stage. **Do not assume cancelling `output` acts as an interrupt/auto-cancel request for all upstream work.** Already-scheduled stages may still be running or producing side effects.

This affects how you use:

- **thenApply/thenCompose**: composition establishes completion relationships; it does not create a physical stop protocol for the whole task tree.
- **allOf**: aggregates completion of futures, not an automatic “cancel all children”.
- **anyOf**: one branch completing does not automatically stop the remaining branches.
- **orTimeout**: transitions future state upon expiration, **without interrupting running work sources**.
- **completeOnTimeout**: can supply a fallback value upon expiration, without stopping underlying I/O suppliers.
- **exceptionally/handle**: recovers a value from exceptional completion, without turning running work into physically stopped work.

To **cancel multiple child tasks**, you must separately manage cancellable handles, deadlines, and resources for each task. If an underlying API provides its own cancel mechanism, invoke it per that API's contract and collect appropriate cleanup confirmations.

## 11. Timeout Does Not Mean Cancellation

A caller may wait on a Future:

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    // Caller no longer wants to wait past 2 seconds.
}
~~~

This is an **illustrative snippet** inside a method with a suitable future and return type. **TimeoutException** means **the caller waited past the deadline**, not that the task stopped automatically. If code catches `TimeoutException` and returns a response, the worker can continue running in the background.

If the goal is **not only to stop waiting but also to request stopping the task**, explicitly call `cancel(true)` on a suitable Future:

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    future.cancel(true);
    throw e;
}
~~~

This is an **illustrative snippet**, not a complete service. **cancel(true)** is still only a cooperative stop attempt and does not guarantee interrupting all I/O. Also distinguish:

- Caller **result-wait** timeout.
- Downstream **HTTP client / JDBC / socket** timeout.
- **Queue wait** timeout before the task starts.
- **Business processing deadline**, spanning multiple retries/hops.
- **Shutdown** timeout waiting for workers to finish.

Setting a timeout at one layer and not others can leave connections and workers running past the deadline. A shared deadline should be passed as immutable data (such as `Instant`) and checked at appropriate checkpoints.

### Race Between Completion and Timeout

At the exact instant `get(timeout)` throws `TimeoutException`, the task may have **just finished** or be finishing. Calling `cancel(true)` then may return `false` or yield another outcome depending on the Future implementation. Never infer from a timeout that the task definitely had no side effects or that a transaction can simply be undone.

## 12. Two Kinds of Cooperative Stopping: Interrupt and Cancellation Token

**Thread interrupt** is a **thread-level** signal, useful for supporting blocking APIs. However, some work needs to stop at a **business** level across multiple stages or multiple threads. In that case, a dedicated **cancellation token** helps pass cancellation intent into functions spanning multiple executors.

Simple token class example:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancelToken {
    private final AtomicBoolean cancelled = new AtomicBoolean(false);

    public void cancel() {
        cancelled.set(true);
    }

    public boolean isCancelled() {
        return cancelled.get();
    }
}
~~~

This is a **standalone Java 17 file named `CancelToken.java`**, with no `main`. The token can be passed into services with clear ownership of the work.

A worker processing multiple batches:

~~~java
for (Batch batch : batches) {
    if (token.isCancelled()
            || Thread.currentThread().isInterrupted()) {
        throw new java.util.concurrent.CancellationException(
                "Job was cancelled");
    }

    processBatch(batch);
}
~~~

This is an **illustrative snippet**, assuming `Batch`, `batches`, and `processBatch` exist. For each batch, clarify which work already produced side effects; stopping at a checkpoint after a batch does not automatically undo prior batches.

**Token limitations:**

- An **AtomicBoolean** does not automatically interrupt a thread blocked in I/O.
- `Future.cancel(true)` **does not automatically set the token**; an owner of the task must call both when appropriate.
- The token lives in JVM memory; across multiple services/processes, cancellation state must be propagated via protocol, queue, or store.
- Stopping immediately is not always safe; e.g., updating a pair of records that require transactional consistency or compensation may require finishing the in-progress step before stopping.

A well-designed cancellation API should treat **cancellation requested**, **stopped accepting new work**, **computation stopped**, and **cleanup finished** as distinct states.

## 13. Designing Cleanup: finally, try-with-resources, and Transactions

When a task stops due to interruption, it must still release owned resources: locks, streams, file handles, connections, semaphore permits, and temporary state.

Logic pattern:

~~~java
void work() throws InterruptedException {
    Resource resource = acquireResource();
    try {
        performSteps(resource);
    } finally {
        resource.close();
    }
}
~~~

This is **Java pseudocode** with application-defined `Resource`, `acquireResource`, and `performSteps`. It illustrates **ownership/cleanup**, not a standalone runnable file.

For resources implementing `AutoCloseable`, **try-with-resources** closes them on normal or exceptional exit. Still, cleanup itself can fail, block, or need a deadline; never assume a `finally` block always succeeds across every infrastructure layer.

### Transactional Scenarios

A task writing to the DB receives an interrupt:

- Interrupt does not automatically **ROLLBACK** every transaction by some universal rule.
- When running inside Spring **@Transactional**, whether the transaction commits or rolls back depends on the exception, rollback rules, and actual transaction boundaries.
- Once a task has sent a payment request or called an external API, the effect may already be executed downstream even if the caller cancelled the Future.
- Retries after cancellation must use **idempotency keys** and status-check/compensation strategies.

Do not write a **catch(InterruptedException)** that returns a “success” state and lets business commits continue if a stop request is supposed to cancel the process.

### Resources of Tasks That Never Started

If a task is cancelled **while still in the queue**, **`finally` inside the task body may never run**, because the body never started. Resources allocated **before submission** need an owner and cleanup outside the task or in a separate cancellation callback. This is why you should avoid opening connections/file handles before the task actually runs and queuing them for long periods.

## 14. Spring @Async: Cancellability Depends on Future Type and Executor

In Spring, **@Async** uses a proxy/interceptor mechanism to dispatch methods to an executor. The bean must be Spring-managed, async support enabled, and the call must go **through the proxy**; self-calling **this.method()** within the same bean normally bypasses the proxy.

When a method declares a `Future` or `CompletableFuture` return type, the caller receives a handle representing the result. However, **the ability to interrupt the actual task** is not identical across all return types and adapters:

- With a `Future` from **executor.submit(Callable)** backed by **FutureTask**, `cancel(true)` can normally interrupt the running worker.
- With standard **CompletableFuture**, **cancel(true) does not automatically interrupt** the supplier/body. This still matters when `CompletableFuture` is returned from Spring `@Async`.
- A framework may use another wrapper, delegation, or executor-specific behavior; never claim `cancel` on an outer Future always propagates to the underlying task without checking the implementation.
- **@Async void** returns no Future for the caller to call `cancel`. To cancel, design a job/command handle, deadline, token, or separate job-management API.

### Example ThreadPoolTaskExecutor Configuration in Spring

~~~java
package example.concurrent;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class WorkConfig {
    @Bean("workExecutor")
    public ThreadPoolTaskExecutor workExecutor() {
        ThreadPoolTaskExecutor executor =
                new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(20);
        executor.setThreadNamePrefix("work-");
        return executor;
    }
}
~~~

This is a **configuration file in a Spring Context application**; it cannot compile with plain `javac` without Spring dependencies. The example uses finite core/max/queue sizes to illustrate a pool; actual sizing must match resource capacity.

### Example Submitting a Callable to Get an Interrupt-Capable Future

~~~java
package example.concurrent;

import java.util.concurrent.Future;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ThreadPoolTaskExecutor workExecutor;

    public ReportService(ThreadPoolTaskExecutor workExecutor) {
        this.workExecutor = workExecutor;
    }

    public Future<String> submitReport(String id) {
        return workExecutor.submit(() -> {
            try {
                return generateReport(id);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw e;
            }
        });
    }

    private String generateReport(String id)
            throws InterruptedException {
        Thread.sleep(1000);
        return "report:" + id;
    }
}
~~~

This is an **illustrative file in a Spring application** using the `ThreadPoolTaskExecutor` bean. It deliberately uses **submit(Callable)** to return a `Future`; `generateReport` sleeps to simulate an interrupt-capable wait operation. Production needs real timeouts and resource cleanup rather than `sleep` simulating business work.

The caller can hold the task's `Future` and call **cancel(true)**. With `ThreadPoolTaskExecutor` backed by `ThreadPoolExecutor`, the handle has cancellation behavior close to `FutureTask`. Still, cancelling mid-task does not automatically undo logic that already ran earlier.

**A wrong inference to avoid:** returning **CompletableFuture** from **@Async** is not the same as the caller directly holding a `FutureTask` from `executor.submit`. If the goal is genuinely stopping workers, check the implementation's scheduling/cancellation mechanics and consider job management with explicit tokens and deadlines.

## 15. Spring CompletableFuture, Errors, and Result Notification

A Spring method example:

~~~java
@Async("workExecutor")
public CompletableFuture<String> buildReport(String id) {
    String result = compute(id);
    return CompletableFuture.completedFuture(result);
}
~~~

This is an **illustrative snippet** inside a bean with `compute` and corresponding imports. When called through the Spring proxy, the method is dispatched to the executor; inside the body it can return `completedFuture` because computation finished on the body thread. The caller observes the future provided by the proxy.

If the caller invokes **future.cancel(true)** on a returned **CompletableFuture**, **do not assume it interrupts the body thread**. Completion-layer cancellation may only mark the result cancelled. For tasks with real side effects, the system needs a dedicated cancellation protocol to stop physical processing.

### Error States That Must Be Distinguished

| Event | What the caller can observe | Meaning |
| --- | --- | --- |
| Executor refuses task | May throw **TaskRejectedException** right at submit/proxy | Work may never have been accepted |
| Worker throws exception | Future completes with error; `get` typically throws **ExecutionException** | Task ran and failed |
| Future cancelled | **CancellationException**, `isCancelled` true | Handle is cancelled; cleanup not yet concluded |
| Caller waits past deadline | **TimeoutException** from `get(timeout)` | Caller timed out waiting; task may still run |
| CompletableFuture.orTimeout | Future completes exceptionally with timeout | Does not automatically interrupt supplier |
| Caller interrupted while waiting in `get` | **InterruptedException** on caller | Waiting thread was interrupted; not equivalent to worker being cancelled |

**Do not catch every exception and treat it as “task was cancelled”.** That corrupts metrics and triggers unnecessary retry loops. Separate exceptions at **submit**, **wait**, and **worker execution**.

## 16. Do Not Arbitrarily Interrupt Pool Worker Threads

With `ThreadPoolTaskExecutor`, workers are reused to serve many different requests. You should not **hold a direct reference to a worker `Thread` and call `Thread.interrupt()`** as a generic way to cancel jobs when the executor/framework manages that thread.

Reasons:

- You can accidentally interrupt **a different task** after the worker finished the original task and was reused.
- You can break the executor's internal synchronization protocol by bypassing its API.
- You would have to manually resolve races between task completion and the thread starting the next task.
- There is no ownership/interrupt management contract if you only store thread names or shared `Thread` references.

**Prefer cancelling through the job's handle** (a valid `Future`, job token, or executor/cancellable-task API), rather than operating directly on shared worker threads.

### InterruptedException in a Pool Thread

Inside a task, when a blocking API throws `InterruptedException`, preserve the stop-request meaning. If you cannot propagate it, restore the flag and exit the body. Do not call `Thread.interrupted()` just to “clear” the flag mid-way and keep processing. Resetting thread state before the next task is the responsibility of the executor structure and task rules, not a license for a task to swallow interrupts.

## 17. shutdown(), shutdownNow(), and Cancelling a Single Task

These are three distinct operations:

| API | Scope | Primary behavior |
| --- | --- | --- |
| **future.cancel(true)** | One Future/task handle | Requests cancellation; may interrupt that task depending on implementation |
| **executor.shutdown()** | Entire ExecutorService | Stops accepting new tasks, normally lets accepted tasks finish |
| **executor.shutdownNow()** | Entire ExecutorService | Attempts to stop executing tasks (usually via interrupt), prevents queued tasks from starting, and returns unstarted tasks |

**shutdownNow() is also best effort** and does not guarantee stopping every worker immediately if tasks do not cooperate. An application with proper lifecycle management typically calls `shutdown`, waits up to a timeout, and considers `shutdownNow` if the deadline expires.

~~~java
pool.shutdown();
if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
    pool.shutdownNow();
}
~~~

This is an **illustrative snippet** inside a method with `pool` and appropriate `InterruptedException` handling. If the thread calling `awaitTermination` is interrupted, it should handle it according to lifecycle policy (e.g., `shutdownNow` and restore the flag) rather than swallowing the exception.

Spring manages `ThreadPoolTaskExecutor` lifecycle according to configuration and `ApplicationContext` lifecycle. **Do not shut down a shared Spring executor after every HTTP request**; doing so breaks other requests using the pool. Cancel individual work via its own handle/token; shut down pools when the application or owning component stops by design.

## 18. HTTP Disconnect, Request Timeout, and Business Cancellation

In a web application, a user closing the browser, a client disconnecting, or a gateway returning HTTP 504 **does not mean workers you submitted to an executor automatically stopped**.

Clarify:

- **HTTP request timeout** only bounds communication per framework/container configuration.
- **Future.get(timeout)** bounds how long one specific caller waits.
- **Client socket disconnect** may report an I/O-layer error without automatically cancelling a business job detached from the request.
- **Business cancellation** is an explicit contracted action: look up the job by `jobId`, authorize cancellation, record `cancel requested`, and signal the worker/job processor.
- **Durable background jobs** usually need status stored in a DB/queue, because an in-memory Future loses meaning across process restarts or when another worker process handles the job.

An API might look like:

~~~text
POST /reports       -> 202 Accepted, returns jobId (if job acceptance persisted)
DELETE /reports/{id} -> records cancel requested
GET /reports/{id}    -> PENDING / RUNNING / CANCEL_REQUESTED /
                        CANCELLED / SUCCEEDED / FAILED
~~~

This is an **API sketch**, not a built-in Spring contract. You may also need states like `CANCEL_FAILED` or `FINISHED_WITH_SIDE_EFFECT` when cancellation arrives too late. **Cancel requested** and **cancelled** should not be treated as the same event.

An HTTP endpoint returning **202 Accepted** after a `TaskExecutor` rejected the task is wrong if 202 means the work was accepted. Check submission status or durable enqueueing before acknowledging.

## 19. Side Effects and Races When Cancelling Too Late

Example workflow:

~~~text
[validate] -> [write DB] -> [call payment gateway] -> [send email]
                     ^
                     |
                cancel(true) at this point
~~~

If cancellation arrives after the DB commits or an external API receives the command, interrupting the worker **does not reverse** effects that already happened.

Proper design for a side-effecting workflow requires:

1. Choosing safe cancellation checkpoints **before** starting an irreversible step.
2. Checking both **deadline** and **cancel token** at checkpoints.
3. For steps already started, deciding whether to **await outcome, check status, or compensate**; never assume “thread was interrupted” means downstream never ran.
4. Using **idempotency keys** on retries or when callers may resend requests.
5. Storing state / job version to prevent races where both `CANCELLED` and `SUCCEEDED` are reported simultaneously.
6. Recording a **cleanup-complete event** when the worker has released resources, not merely when `Future.isDone` becomes true.

**Mandatory business question:** “Does cancel mean not starting new steps, or must we also try to stop an in-progress step?” Those two contracts have very different implications for timeouts, compensation, quotas, and user messaging.

## 20. Testing Cancellation Without Relying on Scheduler Luck

A proper test must establish the target state before calling cancel:

### Testing a Running, Interrupt-Sensitive Task

1. Use **CountDownLatch started** to know the worker has started.
2. Put the worker into **await()**, ensuring it cannot finish on its own.
3. `main` calls **Future.cancel(true)**.
4. Worker observes `InterruptedException` and signals cleanup via a **finished** latch.
5. `main` waits on `finished` with a timeout before asserting.
6. Verify `Future.isCancelled()` and that `Future.get()` throws `CancellationException`.

That is the pattern of **CooperativeCancelDemo**.

### Testing a Non-Cooperative Task

1. Task intentionally ignores interrupt but has a separate **AtomicBoolean stop** for cleanup.
2. `main` waits for the task to start and calls `cancel(true)`.
3. Assert `Future.isDone/isCancelled` is true **while `finished` has not yet been signaled**.
4. Set `stop` and await `finished`; avoid leaking workers in tests.

That is the pattern of **NonCooperativeCancelDemo**.

### Testing a Queued Task

1. Single-worker pool is busy.
2. Second task sits in the queue.
3. `cancel(false)` the second task before releasing the worker.
4. After the first worker finishes, use a barrier task to wait until the queue has been drained.
5. Assert the second task's body **did not run**.

That is the pattern of **CancelQueuedDemo**.

### Testing CompletableFuture

1. Supplier runs and waits on a latch without self-completing.
2. `main` calls `CompletableFuture.cancel(true)`.
3. Assert Future is marked cancelled **while the worker is still waiting**.
4. Open the latch yourself, confirm the worker finishes and **did not observe `InterruptedException` from cancellation**.
5. `get` still throws `CancellationException`.

That is the pattern of **CompletableCancelDemo**.

**Do not use `Thread.sleep(100)` as proof that a task has started or exited.** `Thread.sleep` can be used when real work needs a delay, but concurrency tests must use synchronization primitives to order events. Always put timeouts on `await` and `get` so CI never hangs forever.

## 21. Common Misconceptions

**“`Future.cancel(true)` kills the task immediately.”** False. With `FutureTask`, it can request an interrupt; the task must cooperate to stop or the blocking API must support interruption.

**“`cancel` returning true proves the worker finished cleanup.”** False. That is the result of attempting to cancel the Future, not a physical cleanup signal.

**“`isDone()` is only true when the task succeeds.”** False. Exceptions and cancellation also make `isDone` true.

**“`Future.cancel(false)` can never cancel a task.”** False. It can cancel queued tasks, and `FutureTask` can mark a running task's Future cancelled without interrupting it.

**“`CompletableFuture.cancel(true)` always interrupts the supplier.”** False per Java 17 Javadoc: `mayInterruptIfRunning` **has no effect** in standard `CompletableFuture`.

**“`Thread.interrupt()` is the same as `Thread.stop()`.”** False. Interrupt is a cooperative request; `Thread.stop` is dangerous forced termination and is deprecated.

**“`InterruptedException` is unimportant so it can be swallowed.”** False. Swallowing it and continuing work often defeats cancellation and clogs pools.

**“`Thread.interrupted()` only reads the flag and changes nothing.”** False. It **reads and clears** the current thread's interrupt flag.

**“`Thread.currentThread().isInterrupted()` also clears the flag.”** False. It only observes the status.

**“`get(timeout)` expiring automatically calls cancel.”** False. Timeout only bounds wait time; trying to stop the task requires an explicit action.

**“`CompletableFuture.orTimeout` automatically interrupts blocking HTTP client/JDBC calls.”** False. It controls future completion, not cancelling all underlying work sources.

**“When `@Async` returns `CompletableFuture`, `cancel(true)` is equivalent to cancelling a `FutureTask`.”** Cannot be assumed. Inspect the implementation and pass appropriate cancellation tokens/deadlines.

**“A cancelled Future means no side effects were committed.”** False. The task may have written to the DB, sent email, or called external services before cancellation.

**“You can directly interrupt shared workers by thread name.”** Dangerous. The worker may be running a different task because the thread pool reused it.

**“`shutdownNow` definitely stops every task instantly.”** False. It is best-effort interruption, not forced physical termination of uncooperative tasks.

**“Worker `finally` always runs when a queued task is cancelled.”** False. If the body never ran, `finally` inside the body never gets a chance to execute.

**“HTTP client disconnect automatically cancels jobs submitted to an executor.”** Not automatically. Jobs need an explicit cancellation contract.

## 22. Self-Check Exercises

**Exercise 1.** A `Callable` is inside `Thread.sleep(10_000)` and the caller calls `cancel(true)` on its `FutureTask`. What is likely to happen?

**Answer:** The Future can transition to cancelled, `Thread.sleep` receives the interrupt and throws `InterruptedException`; the `Callable` should cooperatively stop and clean up. Do not claim every other I/O API reacts identically.

**Exercise 2.** Both `Future.isDone()` and `Future.isCancelled()` are true, yet the worker's CPU metric keeps climbing. Is there a contradiction?

**Answer:** No. The Future may have been cancelled in state while the task never stopped because it does not check or react to interrupts.

**Exercise 3.** A task is in the queue and has not started. Can `cancel(false)` succeed?

**Answer:** Yes. There is no need to interrupt a thread running that task; the queued task can be marked cancelled so its body does not run.

**Exercise 4.** Why should `catch(InterruptedException)` restore the interrupt flag when a `Runnable` cannot propagate the exception?

**Answer:** Many APIs clear the flag when throwing `InterruptedException`. Restoring the flag preserves the interrupt signal for layers that may observe it, while the body should exit intentionally.

**Exercise 5.** A `CompletableFuture` created with `supplyAsync` is waiting on a latch, and `cf.cancel(true)` is called. Is `latch.await` guaranteed to throw `InterruptedException`?

**Answer:** No. Standard `CompletableFuture` does not use `mayInterruptIfRunning` to interrupt the supplier. To stop waiting, you need another signal or source cancellation.

**Exercise 6.** A caller invokes `Future.get(1, SECONDS)` and catches `TimeoutException`, without calling `cancel`. Does the worker stop automatically?

**Answer:** Not guaranteed. The timeout on `get` only stops the caller from waiting.

**Exercise 7.** A task already sent a payment request and was then cancelled. Can you record the status as “definitely unpaid”?

**Answer:** No. You must check the outcome with the payment system and use idempotency/compensation per the business contract.

**Exercise 8.** Why is a separate `finished` latch needed after `cancel(true)`?

**Answer:** Because `Future.isDone/isCancelled` does not prove the worker's final/`finally` code ran. A separate signal lets you verify execution completion or cleanup.

**Exercise 9.** Should you use `Thread.interrupted()` in every long loop condition instead of `isInterrupted()`?

**Answer:** Not by default. `Thread.interrupted()` clears the flag, making downstream/outer layers miss the signal. `isInterrupted()` observes without clearing.

**Exercise 10.** Does Spring `@Async void` provide a `Future` for callers to invoke `cancel(true)`?

**Answer:** No. To cancel, you must design a job handle, token, deadline, or another job-management mechanism.

**Exercise 11.** How do `shutdown()` and `shutdownNow()` differ?

**Answer:** `shutdown` stops accepting new tasks and lets accepted tasks continue per contract; `shutdownNow` attempts to interrupt running tasks and prevents queued tasks from starting, though it is still best effort.

**Exercise 12.** A running `FutureTask` receives `cancel(false)`, and afterward the `Callable` still writes to the database. Is this a Java bug?

**Answer:** No. `cancel(false)` does not request interrupting the worker; the Future can be cancelled while execution continues. Application design must account for side effects and cancellation rules.

## 23. Checklist for Safe Task Cancellation

- [ ] Identify the actual Future implementation: **FutureTask, CompletableFuture, or framework wrapper**.
- [ ] Distinguish **Future cancelled**, **execution stopped**, and **cleanup complete**.
- [ ] Know clearly whether **cancel(true)** issues an interrupt request to the worker in the implementation used.
- [ ] For long CPU tasks: place **interrupt/cancel-token checkpoints** at safe stopping points.
- [ ] For blocking operations: use APIs with supported **timeouts/cancellation**, not interrupts alone.
- [ ] When catching `InterruptedException`: **propagate or restore the flag and exit**, never swallow the signal.
- [ ] Use **finally/try-with-resources** to clean up resources owned by the task.
- [ ] Handle resources allocated **before the task starts**, because a cancelled queued task may never run its body/`finally`.
- [ ] Do not manually interrupt workers of a shared Spring thread pool outside the task contract.
- [ ] Set an **overall timeout** and per-operation timeouts for HTTP/DB/sockets as appropriate.
- [ ] With `CompletableFuture`, separate cancellation of **completion** from cancellation of **computation**.
- [ ] Control concurrency/rejection/queues so work is not retained past its deadline.
- [ ] Separate job state **CANCEL_REQUESTED** from **CANCELLED/CLEANED** when accurate observability is required.
- [ ] Verify DB/external side effects, using idempotency and compensation when needed.
- [ ] Test using **CountDownLatch** and `Future.get(timeout)`, not `sleep` alone.
- [ ] In Spring integration tests, verify the `@Async` proxy and exact executor; test cancellation behavior of the real handle.

## Conclusion

**`Future.cancel(true)` is a cancellation request, not a command to forcibly stop a Java thread.** With `FutureTask` typically created by `ExecutorService.submit`, the method can transition the Future to cancelled and attempt to interrupt the executing worker; for the task to stop quickly, it must **cooperate** by reacting to `InterruptedException`, checking the interrupt flag or a cancellation token at safe checkpoints, and cleaning up. With standard **CompletableFuture**, **cancel(true) does not interrupt computation**; instead it marks an exceptional completion with `CancellationException`.

In Spring, do not look only at a `Future`/`CompletableFuture` return type and assume cancellability. Identify the executor, wrapper, proxy, and application contract; separate wait timeouts, stop requests, physical termination, and side-effect state. Good design must be able to answer **whether cancellation was requested, whether the task actually stopped, and whether related resources/orders are in a consistent state**.

**Official references:**

- Java SE 17 [Future API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html).
- Java SE 17 [FutureTask API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html).
- Java SE 17 [Thread.interrupt, interrupted, and isInterrupted](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html).
- Java SE 17 [ExecutorService shutdown, submit, cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html).
- Java SE 17 [CompletableFuture cancel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).
- Spring Framework [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html).
