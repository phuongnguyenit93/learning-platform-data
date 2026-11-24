# CompletableFuture.cancel() Does Not Guarantee Interrupting the Worker Thread

When building asynchronous tasks in Java and Spring Framework, a common misconception is that calling `future.cancel(true)` will immediately interrupt the thread executing the work. **This is not true for `java.util.concurrent.CompletableFuture`.** Under the Java SE 17 contract, the `mayInterruptIfRunning` parameter of `CompletableFuture.cancel(boolean)` **has no effect**: this implementation does not use interruption to control processing.

`cancel(true)` primarily transitions the `CompletableFuture` object to the **cancelled state**, preventing callers from receiving a normal result. A worker that has already started may still continue waiting on I/O, writing to the database, or performing side effects **after `future.isCancelled()` is already `true`**. Cancelling the result does not mean terminating the work.

This lesson belongs to the **Timeouts and Cancellation** group in **Spring Framework - concurrency**. It explains standard Java 17 semantics, compares them with `FutureTask`, covers timeout types, applies them to `@Async`, shows how to design cooperative cancellation, and provides compilable/runnable examples.

## 1. Separating Result State from Execution Progress

There are three related but distinct entities:

- **Caller:** may decide it no longer wants to receive or wait for the result.
- **Result object `CompletableFuture<T>`:** holds pending, completed, failed, or cancelled state; supports composition via `CompletionStage`.
- **Actual work (worker/task):** executes on a thread, DB, network, or other software. It only actually stops if the logic or resource controlling it stops it.

A `CompletableFuture` can be created via `new CompletableFuture<>()` and completed by other code via `complete(value)`, **with no association to a specific worker**. Therefore, cancelling the result object cannot know for sure which thread would need to be interrupted.

~~~text
Caller                   CompletableFuture                 Worker
  |                             |                             |
  |--- runAsync(task, pool) ---->|--- dispatch --------------->|
  |                             |                         task starts
  |                             |                         running/waiting
  |--- future.cancel(true) ----->|                             |
  |<-- cancelled state ----------|                             |
  |                             |                             |
  |   isCancelled() = true      |                        worker may still
  |   join() throws cancellation|                        continue executing
  |                             |                             |
  |                             |                        finishes per logic
~~~

The crucial point is that **`cancel(true) == true` does not confirm the worker has stopped**. A caller receiving `CancellationException` from the Future may be looking at a cancelled result while the work is still running or a remote request has already been processed.

### 1.1. Two Different Questions

1. **Will the Future still provide a normal result?** Once cancelled successfully, no. A normal `complete(value)` will not overwrite the cancelled state.
2. **Has the worker stopped and cleaned up?** You cannot infer this from `isCancelled()`, `isDone()`, or `cancel()`. You need job state, a worker exit signal, or confirmation from the orchestrating system.

“Cancel” at the API level may only mean **cancelling the right to wait for/receive the result**; “stop job” is a stronger business protocol.

## 2. The Contract of CompletableFuture.cancel(boolean)

API signature in Java SE 17:

~~~java
public boolean cancel(boolean mayInterruptIfRunning)
~~~

This is an **abbreviated signature for reference**, not a method you define yourself. Key behaviors:

- If the Future is not yet completed, `cancel(...)` completes it with a `CancellationException`.
- The `mayInterruptIfRunning` parameter has no effect on how this implementation controls workers. Both `cancel(true)` and `cancel(false)` only mark the state as cancelled.
- If the Future already has a normal result or error beforehand, `cancel` does not replace the established outcome.
- Incomplete dependent `CompletableFuture`s will complete exceptionally due to source cancellation; the error on a derived stage may be a `CompletionException` whose cause is `CancellationException`.
- The return value from `cancel` is information about the **Future object's** state. It is not the result of a `Thread.interrupt()` call to a worker.

| API | Observed on successful cancellation |
| --- | --- |
| `future.cancel(true)` | Future transitions to cancelled state; does not force-interrupt worker |
| `future.isCancelled()` | `true`: Future was cancelled |
| `future.isDone()` | `true`: has a completion state; does not mean worker has exited |
| `future.isCompletedExceptionally()` | `true`: cancellation is a form of exceptional completion |
| `future.join()` | Throws `CancellationException` on a directly cancelled root Future |
| `future.get()` | Throws `CancellationException` on a directly cancelled root Future |
| `future.complete(value)` after cancel | Does not change cancelled state back to a normal value |

`isDone()==true` also occurs when a Future **succeeds** or **fails**, so do not use it as a business signal meaning “task succeeded”. Likewise, `isCancelled()==true` is a logical state and does not prove side effects were rolled back.

### 2.1. Why Setting mayInterruptIfRunning=true Still Does Not Help

`CompletableFuture` does not need to bind a thread to the Future: it can be completed from a callback, completion stage, executor, event loop, or direct caller. Its cancellation API defines a result-state transition. JDK 17 explicitly documents that this parameter has no effect in this implementation because interrupts are not used to control processing.

Do not infer behavior from **parameter names**; rely on the **specific class contract**. This is an important difference from `FutureTask.cancel(true)`.

## 3. Standalone Java 17: Future Cancelled While Worker Still Waits

This example uses `CountDownLatch` for exact control: the worker has started but cannot finish before `main` opens the latch. `main` cancels the `CompletableFuture` before releasing the worker.

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
        CountDownLatch workerEnded = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean(false);
        try {
            CompletableFuture<Void> future = CompletableFuture.runAsync(() -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    interrupted.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    workerEnded.countDown();
                }
            }, pool);
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            System.out.println("1. cancel(true): " + future.cancel(true));
            System.out.println("2. isCancelled: " + future.isCancelled());
            try {
                future.join();
            } catch (CancellationException expected) {
                System.out.println("3. join(): CancellationException");
            }
            System.out.println("4. Worker ended before release: "
                    + (workerEnded.getCount() == 0));
            release.countDown();
            if (!workerEnded.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not finish");
            }
            System.out.println("5. Worker interrupted by cancel: "
                    + interrupted.get());
            System.out.println("6. isDone after worker exit: "
                    + future.isDone());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Compile/run commands with JDK 17+:

~~~bash
javac --release 17 CompletableFutureCancelDemo.java
java CompletableFutureCancelDemo
~~~

Verified stdout when running the program:

~~~text
1. cancel(true): true
2. isCancelled: true
3. join(): CancellationException
4. Worker ended before release: false
5. Worker interrupted by cancel: false
6. isDone after worker exit: true
~~~

**Explanation via synchronization constraints:**

1. `started.await(...)` guarantees the worker has actually started, not just sitting in the queue.
2. The worker is blocked at `release.await()`. It cannot exit while `main` has not opened the latch unless interrupted.
3. `future.cancel(true)` marks the result cancelled; `join()` already observes `CancellationException`.
4. The fourth line prints `false` because the worker is still waiting, proving the Future state became cancelled **before the worker left the task**.
5. `main` opens the latch and the worker exits normally. `interrupted` is `false`, so `cancel(true)` itself did not interrupt the worker in this controlled scenario.
6. `isDone()` on the last line merely repeats the Future state already set earlier, not a new acknowledgement that the worker finished.

`shutdownNow()` is only called in `finally` **after** the results have been observed. Reversing the order would let the shutdown interrupt distort the experiment.

### 3.1. Why Not Use Thread.sleep(100) to Guess?

A test that starts a task and sleeps 100 ms before cancelling can be affected by CI load, CPU scheduling, and worker startup time. Latches prove **already started** and **cannot finish yet**, avoiding conclusions based on accidental timing.

## 4. Comparison: FutureTask.cancel(true) Can Request Interruption

The `Future` interface has multiple implementations. `FutureTask` is commonly used when `ExecutorService.submit(...)` returns a `Future<?>`. With that implementation, `cancel(true)` can request `Thread.interrupt()` on the executing thread. However, **interruption is still a cooperative signal**, not a mechanism to forcibly kill a thread.

Create standalone file **`InterruptibleFutureDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptibleFutureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch observed = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean(false);
        try {
            Future<?> handle = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(60_000);
                } catch (InterruptedException ex) {
                    sawInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    observed.countDown();
                }
            });
            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not start");
            }
            System.out.println("1. Future.cancel(true): " + handle.cancel(true));
            if (!observed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Worker did not observe interruption");
            }
            System.out.println("2. Worker observed interruption: " + sawInterrupt.get());
            System.out.println("3. Future isCancelled: " + handle.isCancelled());
        } finally {
            pool.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 InterruptibleFutureDemo.java
java InterruptibleFutureDemo
~~~

Verified stdout:

~~~text
1. Future.cancel(true): true
2. Worker observed interruption: true
3. Future isCancelled: true
~~~

The worker is in `Thread.sleep(...)`, which reacts to interrupts with `InterruptedException`. `FutureTask.cancel(true)` sends the interrupt request and the program observes it.

Even so, if the worker ignores the interrupt flag, blocks in non-interruptible I/O, or has already committed a transaction, `Future.cancel(true)` **cannot guarantee the worker stops immediately** and does not roll back side effects.

| Mechanism | Direct meaning | Guarantees immediate stop? |
| --- | --- | --- |
| `CompletableFuture.cancel(true)` | Marks result cancelled with `CancellationException`; ignores mayInterruptIfRunning | No |
| `FutureTask.cancel(true)` | Requests cancellation, may send interrupt to running thread | No; task must cooperate |
| `Thread.interrupt()` | Sends interrupt signal; some blocking APIs observe it and throw `InterruptedException` | No |
| `ExecutorService.shutdownNow()` | Attempts to interrupt running tasks and stop accepting work | No; best-effort mechanism |
| `AtomicBoolean` token | Sends an application-defined stop flag | No; worker must check the flag |

Do not use `Thread.stop()` to force a task to terminate: it is an unsafe and deprecated API. Do not arbitrarily call interrupt on a shared pool thread when you do not own the work.

## 5. Cancellation in a CompletionStage Chain

With `thenApply`, `thenCompose`, `whenComplete`, and other stages, distinguish the **source Future** from **dependent stages**.

~~~java
CompletableFuture<String> source = new CompletableFuture<>();
CompletableFuture<Integer> dependent =
        source.thenApply(String::length);
source.cancel(true);
~~~

This is illustrative Java code (requires importing `CompletableFuture`). If the source is incomplete and cancelled:

- `source.isCancelled()` is `true`; `source.join()` throws `CancellationException`.
- Incomplete `dependent` stages will complete exceptionally, typically with `CompletionException` carrying cause `CancellationException`.
- The `String::length` function receives no normal result to process.
- `dependent.isCancelled()` **is not necessarily `true`**, because a derived stage may simply carry an exceptional state rather than being the object on which `cancel(...)` was directly called.

**Cancelling a dependent stage does not implicitly cancel upstream work**, and cancelling a source Future does not know how to cancel an HTTP request, JDBC query, or work already handed off to another system. If cancellation signals must propagate through a pipeline, build an explicit cancellation protocol.

Example classification callback on the source Future:

~~~java
source.whenComplete((value, error) -> {
    if (error instanceof java.util.concurrent.CancellationException) {
        System.out.println("Result cancelled");
    } else if (error != null) {
        System.out.println("Result failed: " + error);
    } else {
        System.out.println("Result completed: " + value);
    }
});
~~~

This is an illustrative snippet with no fixed stdout unless `source`'s state at registration time is known. On a dependent stage, the exception may be wrapped in `CompletionException`; inspect the cause rather than comparing only the outer type.

Completion callbacks may run on the thread that completes/cancels the stage; `*Async` variants use different scheduling mechanisms. Avoid long blocking operations inside callbacks without knowing which thread will execute them.

## 6. Timeouts Do Not Automatically Stop Workers

Java's timeout APIs represent **the right to wait for a result**, **result state**, or **I/O timeout**—three separate responsibilities.

| API | Behavior when time expires | Auto-interrupts worker? |
| --- | --- | --- |
| `future.get(2, SECONDS)` | Caller stops waiting, receives `TimeoutException` | No |
| `future.orTimeout(2, SECONDS)` | The `CompletableFuture` itself completes exceptionally with `TimeoutException` if still pending | No |
| `future.completeOnTimeout(fallback, 2, SECONDS)` | The `CompletableFuture` itself completes with the fallback value if still pending | No |
| `future.cancel(true)` | `CompletableFuture` transitions to cancelled if still possible | No; `true` parameter is ignored |
| HTTP/JDBC client timeout | Limits I/O operations per the specific API | Library-dependent; must not be equated with Future cancel |

`orTimeout(...)` and `completeOnTimeout(...)` return **the same CompletableFuture instance they are called on**, not an independent copy of the result. If the underlying task is still running, it may continue writing data even after the Future returns a timeout error or fallback.

Example integrating with slow work:

~~~java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(() -> slowOperation(), executor);
result.orTimeout(2, TimeUnit.SECONDS);
~~~

The snippet above assumes `slowOperation()`, `executor`, and imports exist. It **does not guarantee interrupting** `slowOperation()` after 2 seconds. For real network/DB deadlines, configure timeouts in the respective client library and add safeguards when side effects have already occurred.

### 6.1. Timeouts from a Whole-System Perspective

A task might spend 5 seconds in the executor queue and then 10 seconds executing. If the SLA allows 8 seconds total, a 10-second I/O timeout on the worker is insufficient. Track `t_submit`, `t_start`, and `t_finish`, apply an end-to-end deadline, and check the expiration at the start point to avoid executing work that is already worthless.

**Caller timeout, Future cancelled state, and stopping side-effect execution are three events that must be verified separately.**

## 7. With Spring @Async, Distinguish the Future from the Worker

In Spring Framework, an `@Async` method can return `CompletableFuture<T>` so callers can receive the result, chain callbacks, or track errors. However, **there is no general contract that calling `cancel(true)` on the returned Future will interrupt the target method running inside `ThreadPoolTaskExecutor`**.

Things to verify:

1. `@EnableAsync` is enabled and the bean is genuinely managed by Spring.
2. The caller goes through the Spring proxy. Self-invocation such as `this.doWork()` normally bypasses the interceptor in default proxy mode.
3. `@Async("jobExecutor")` selects the right executor. The method may be queued or already started when the caller receives the Future.
4. If the executor rejects the work, `TaskRejectedException` can occur **right at submission time**, not as a cancellation state of an already-running task.
5. `@Async void` has no returned Future for the caller to call `cancel`; a separate cancel-request channel is needed if the business flow supports it.
6. With `CompletableFuture<T>`, even if `cancel(true)` succeeds on the handle, you must still verify the worker actually stopped via application logic/metrics.

Do not implement a Cancel API button simply by calling `storedFuture.cancel(true)` and returning “job definitely stopped”. The Future may be cancelled while the worker is still calling a remote service.

## 8. Cooperative Cancellation via Cancellation Token in Spring

If the requirement is to **stop the work**, design a cooperative mechanism rather than relying on Future state:

1. The orchestrating service creates a token per job.
2. The worker checks the token at safe points between processing steps.
3. The cancel endpoint sets the token to request stopping.
4. The worker stops, cleans up, and reports the final status.
5. The system distinguishes `CANCEL_REQUESTED` from `CANCELLED`: receiving the request differs from confirming the stop.

An in-JVM token can be an `AtomicBoolean`. It is thread-safe, but **does not automatically wake up blocking I/O**, so long tasks still need separate timeouts and interruption mechanisms for fast responsiveness.

### 8.1. Configuring ThreadPoolTaskExecutor

File `AsyncPoolConfiguration.java` (Spring Framework 6.x and Java 17+):

~~~java
package example.concurrency;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AsyncPoolConfiguration {
    @Bean("jobExecutor")
    public ThreadPoolTaskExecutor jobExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("job-");
        return executor;
    }
}
~~~

This is **Spring integration code** requiring the Spring Context dependency and registration via `ApplicationContext`; it cannot be compiled standalone with `javac` without a classpath. The pool numbers are illustrative only, not universal tuning for all workloads.

### 8.2. Worker Checking the Stop Signal

File `ReportWorker.java`:

~~~java
package example.concurrency;

import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportWorker {
    @Async("jobExecutor")
    public CompletableFuture<String> build(
            String reportId, AtomicBoolean cancelRequested) {
        try {
            for (int part = 1; part <= 10; part++) {
                if (cancelRequested.get()
                        || Thread.currentThread().isInterrupted()) {
                    throw new CancellationException(
                            "Report cancellation requested: " + reportId);
                }
                // Simulate I/O; in a real application, configure HTTP/DB timeouts.
                TimeUnit.MILLISECONDS.sleep(100);
            }
            return CompletableFuture.completedFuture("ready:" + reportId);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            return CompletableFuture.failedFuture(ex);
        }
    }
}
~~~

This code demonstrates **token checkpoints** inside a worker. Only after a step finishes does the loop observe the flag. If the worker is inside `sleep(...)`, merely flipping `AtomicBoolean` does not wake it up. Do not use `Thread.sleep` as fake I/O in production while neglecting real timeouts.

A caller in **another bean** can use:

~~~java
AtomicBoolean stopRequested = new AtomicBoolean(false);
CompletableFuture<String> result =
        reportWorker.build("R-17", stopRequested);

// Later, the user requests cancellation:
stopRequested.set(true);

// Observe worker completion under the cooperative protocol:
result.whenComplete((value, error) -> {
    if (error != null) {
        System.out.println("Worker did not complete normally: " + error);
    } else {
        System.out.println("Worker completed: " + value);
    }
});
~~~

This is an **illustrative caller snippet**, assuming `reportWorker` is Spring-injected and `AtomicBoolean` and `CompletableFuture` are imported. There is no fixed stdout: the work may complete before or after the flag is set.

**Why not immediately call `result.cancel(true)` in this example?** Because then `result` would immediately report cancelled while the worker had not yet checked the token, losing a channel for observing when the worker actually exits. When the contract requires knowing the job has stopped, keep job status or completion signaling separate.

### 8.3. Cancelling Jobs Across Processes or Multiple Replicas

`AtomicBoolean` only signals within a single JVM. If a job runs on pod A and the cancel request arrives at pod B, an in-memory flag on B cannot affect worker A. The design needs a job ID, centralized status storage, and a signaling or polling channel to the right worker. For durable jobs, add a job store, retry/idempotency, and post-restart recovery mechanisms.

Tokens stored in a map need lifecycle cleanup so memory does not leak, yet they should not be deleted before the worker has actually finished.

## 9. Interruption Is a Cooperative Signal, Not a Thread-Kill Command

Some Java APIs such as `Thread.sleep`, `Object.wait`, or `BlockingQueue.take` support interruption via `InterruptedException`. When code catches this exception and cannot propagate it upward, the common pattern is to restore the interrupt flag and exit:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This is **pseudocode inside a void method**, assuming `blockingOperation()` can throw `InterruptedException`. In a method that can declare `throws InterruptedException`, rethrowing it is also valid handling.

Avoid `catch (InterruptedException ignored) {}` and continuing indefinitely. At the same time, do not assume every JDBC/HTTP/remote API stops immediately upon seeing an interrupt: some I/O needs its own timeouts/cancellation, and a remote system may already have received the request.

### 9.1. Side Effects Are Not Undone by Cancel

A worker may already have written to the database, sent an email, or performed an HTTP POST before the caller requests cancellation. When `future.cancel(true)` succeeds, effects that have already happened **are not rolled back**. In Spring, transaction context is usually thread-bound; the caller's transaction does not automatically propagate fully to an `@Async` worker. Cancelling the caller's Future does not automatically roll back the worker's transaction.

For business operations that must not be lost or processed twice, use idempotency keys, job status, rollback/compensation protocols, and a durable job source where appropriate. Do not promise “cancellation succeeded” merely because the handle transitioned to cancelled.

## 10. Cancelling a Task Before It Starts Running

If a task is still waiting in the queue, cancelling a Future before it starts may cause the executor's wrapper to **skip the task logic** when a worker picks it up. However, this depends on the implementation, Future type, how callbacks were created, and cancellation mechanics. Do not assume every `CompletableFuture.cancel()` will cleanly remove tasks from every `TaskExecutor` queue.

For a `FutureTask` from `ExecutorService.submit(...)`, successful cancellation before the task runs normally prevents the `Callable/Runnable` body from executing. For a `CompletableFuture` using `runAsync`, inspect the actual dispatch/wrapper path if preventing execution strictly is required.

Likewise, cancelling a dependent stage does not mean stopping the source stage. A stage may already have launched an HTTP call before downstream is cancelled. Design explicit cancellation propagation if upstream stages must also stop.

## 11. Verifying Cancellation in Production

To prevent dashboards from reporting “100% jobs cancelled” while workers are still running, track separately:

| Event/metric | Meaning |
| --- | --- |
| `submitted_total` | Number of tasks requested |
| `started_total` | Number of workers actually started |
| `cancel_requested_total` | Number of stop requests |
| `future_cancelled_total` | Number of Future handles transitioned to cancelled |
| `worker_stopped_total` | Number of workers signaling exit/cleanup |
| `completed_total` | Number of tasks completed normally |
| `failed_total` | Number of tasks failed |
| `cancel_latency` | Interval from cancel request to worker stop confirmation |
| `active_threads` / `queue_depth` | How busy the pool is and how large the backlog is |

The names above are **suggested metric names**, not mandatory built-in Spring defaults. Use a job ID / correlation ID to link logs across caller, worker, and downstream systems. If a Future is cancelled, `whenComplete` can run immediately and report a cancellation error **before the worker actually stops**; do not treat that callback as a stopped confirmation metric.

### 11.1. Clear Status Terminology

- **`CANCEL_REQUESTED`:** the system has received the cancel request.
- **`CANCELLING`:** the worker is cooperating to exit and clean up, if distinguishing this phase is needed.
- **`CANCELLED`:** confirmation has been obtained that the job is no longer executing work per the application protocol.
- **`SUCCEEDED`:** the worker finished before the cancel request took effect.
- **`FAILED`:** another error occurred; determine whether retry or compensation is needed.

Do not use `future.isCancelled()` to decide all of these business states without a confirmation channel from the worker.

## 12. Reliable Testing Practices

A cancellation-related test should guarantee **the worker has started** before calling cancel. Use latches/barriers or fake clients capable of pausing at deterministic points:

1. **Cancelling a running CompletableFuture:** use `CompletableFutureCancelDemo`; assert the Future is cancelled while the worker is still waiting; then release the latch for cleanup.
2. **FutureTask receiving interrupt:** use `InterruptibleFutureDemo`; have the worker block in an interruptible API, cancel it, and verify the worker observes `InterruptedException`.
3. **Timeout does not stop the worker:** create a task with a latch, call `get(timeout)`/`orTimeout`, and verify the callback has not passed the latch before `main` opens it.
4. **Spring @Async proxy:** call through a real Spring bean, not `this.method()`; inject the proper executor and token.
5. **Cancellation at side-effect boundaries:** use a fake DB/API to verify the worker produces no new side effects after the designed token checkpoint; also verify handling when a side effect has already occurred.
6. **Shutting down the executor:** clean up in `finally` using finite timeouts so tests do not hang or leave workers running indefinitely afterward.

Tests using `Thread.sleep(100)` in `main` to guess that a task has started are often flaky on CI. Latches provide proof of ordering in examples.

## 13. Common Misconceptions

**“`CompletableFuture.cancel(true)` definitely sends an interrupt to the worker.”** False. Per Java SE 17, the `mayInterruptIfRunning` parameter has no effect on the `CompletableFuture` implementation.

**“`cancel(true)` returning true means the worker has stopped.”** False. That is the Future's state, not an acknowledgement from the worker.

**“`future.isDone()==true` means the work is finished.”** False. Cancellation and errors are also completion states of the Future; the worker may still be running.

**“`join()` throwing CancellationException means the database has not committed.”** False. Side effects may already have occurred or continue executing.

**“`get(timeout)` throwing TimeoutException means the task is automatically cancelled.”** False. Only the caller stopped waiting for the result.

**“`orTimeout` will interrupt the thread after N seconds.”** False. It updates the `CompletableFuture` state, without controlling actual I/O.

**“`AtomicBoolean` wakes the worker up automatically.”** False. The flag must be checked; blocking I/O needs appropriate timeouts or interrupts.

**“When Spring @Async returns a Future, Spring guarantees interrupting the method's thread on cancel.”** There is no such general guarantee. Verify the implementation and design an explicit stop protocol.

**“If a future is cancelled, all dependents and upstream work stop running too.”** False. Dependents may complete exceptionally, while upstream does not automatically receive a stop command.

**“Cancelling a job means all committed transactions can be rolled back.”** False. Cancellation is a control decision, not a system-wide transaction rollback.

## 14. Self-Check Questions

**Question 1.** `CompletableFuture.cancel(true)` returns true while the worker is waiting on `CountDownLatch.await()`. Is the worker guaranteed to receive `InterruptedException`?

**Answer:** no. `CompletableFuture` ignores the `true` parameter, so the worker can keep waiting until the latch is opened or another interrupt source occurs.

**Question 2.** Do `isCancelled()==true` and `isDone()==true` prove the worker has exited?

**Answer:** no. Both methods only reflect the result state; you need a stop signal from the worker.

**Question 3.** How does `FutureTask.cancel(true)` differ from `CompletableFuture.cancel(true)`?

**Answer:** `FutureTask` can request interrupting the running thread; standard `CompletableFuture` does not use interrupts to control processing. Neither guarantees rollback or instant termination.

**Question 4.** If `get(2, SECONDS)` throws `TimeoutException`, is the task cancelled?

**Answer:** not automatically. Only the caller's wait attempt timed out.

**Question 5.** In the first example, why does it print “Worker ended before release: false”?

**Answer:** the worker had started but was still waiting on the latch; `main` had not opened the latch yet and `cancel` did not interrupt the worker.

**Question 6.** How should you design a Cancel feature for a long-running Spring `@Async` job?

**Answer:** you need a job ID, dedicated token/status, worker checks at safe points, I/O timeouts, and a distinction between `CANCEL_REQUESTED` and `CANCELLED`; with multiple pods, you need distributed signaling/coordination.

**Question 7.** If the caller cancels the Future right after an HTTP POST creating an order, is it guaranteed the order was not created?

**Answer:** no. The request may already have reached the remote service; use idempotency keys, status lookup, and/or appropriate compensation mechanisms.

**Question 8.** To prove `cancel` does not interrupt the worker, should a test use random sleep or a latch?

**Answer:** use a latch to guarantee the worker has started and cannot finish before `cancel`, then observe interruption and cleanup in a controlled order.

## 15. Official References

- Java SE 17 — `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 17 — `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17 — `FutureTask`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html
- Java SE 17 — `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 — `Thread.interrupt()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Spring Framework — Task Execution and Scheduling / `@Async`: https://docs.spring.io/spring-framework/reference/integration/scheduling.html
- Spring Framework — `ThreadPoolTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html
