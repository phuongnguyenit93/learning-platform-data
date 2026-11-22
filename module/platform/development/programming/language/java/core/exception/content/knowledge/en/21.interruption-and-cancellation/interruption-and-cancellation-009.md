# Limits of Timeout and Cancellation on Underlying Tasks

## 1. The problem: timing out does not mean the work has stopped

A Java program often submits asynchronous work to an `ExecutorService` or `CompletableFuture` and bounds how long it waits for the result. If the deadline expires, the caller may receive a `TimeoutException` or request cancellation via `Future.cancel(true)`. However, both actions describe **observability and work coordination**, not a guarantee that every underlying computation, I/O operation, or side effect has stopped.

Four distinct events must be separated:

1. **The caller stops waiting**: the calling thread exits `get(timeout, unit)` because no result arrived in time.
2. **The handle is marked cancelled or completed exceptionally**: the state of the `Future`/`CompletableFuture` may transition to terminal.
3. **The worker actually stops running**: the executing thread has finished, which usually requires the task to cooperate with interruption, a deadline, or a dedicated cancellation mechanism.
4. **External effects have stopped or been reverted**: databases, files, HTTP services, or payments are no longer changing; this level of guarantee requires its own mechanism.

These events **cannot be treated as interchangeable**. For example, `future.get(100, MILLISECONDS)` throws `TimeoutException`, yet the worker still sends the request and receives the response afterward. Or `future.cancel(true)` returns `true`, while the worker ignores the interrupt and continues writing a file. Or `CompletableFuture.orTimeout` completes the stage with `TimeoutException`, yet the supplier running in the executor still finishes its side effect.

After this lesson, you will be able to:
- Understand the exact contracts of `Future.get(timeout)`, `Future.cancel`, `CompletableFuture.orTimeout`, and `completeOnTimeout` in Java 17+.
- Distinguish caller timeout, I/O API timeout, interruption, cancellation, and remote outcome state.
- Design tasks that support cooperative cancellation and clean up resources with proper ownership.
- Evaluate race conditions, indeterminate outcomes, and the risk of duplicate side effects on retry.
- Write tests that verify **the worker actually stopped** and check post-processing state, rather than only asserting the Future's `isCancelled` flag.

## 2. Timeline model: caller and worker do not share a single stopping point

Suppose the caller needs a result within 200 ms, while the worker is loading data:

~~~text
Time            Caller                              Worker
t0              submit -> Future                    scheduled
t1              get(200 ms)                         sending HTTP request
t2              TimeoutException                    still waiting on server
t3              caller returns "timed out"          server finished processing
t4              caller may retry                    worker receives response
t5              ...                                 updates state/file
~~~

This timeline is illustrative only, not a promise about exact timing. Calling `get(timeout)` limits **how long the caller waits for that call**. It does not install a timer that forcibly halts the CPU, Java thread, socket, database query, or remote service.

The same operation can have multiple different deadlines:
- **Request timeout** at the incoming HTTP layer.
- **Result-wait timeout** in `Future.get(timeout, unit)`.
- **Connect timeout**, **read timeout**, or **request timeout** in the HTTP/JDBC client.
- **Overall task deadline** propagated by the application to sub-steps.
- **Remote system timeout** or database transaction timeout.
- **Retry deadline** of an external policy.

To ensure the user receives a timely response **and** prevent tasks from running too long, the corresponding mechanisms must work together. Simply wrapping `get` with a timeout is not enough.

## 3. `Future.get(timeout, unit)` only limits wait time

Example:

~~~java
Future<String> future = executor.submit(this::loadData);
String value = future.get(500, TimeUnit.MILLISECONDS);
~~~

This is a fragment assuming `executor`, `loadData`, and the imports already exist; the enclosing method must handle `InterruptedException`, `ExecutionException`, and `TimeoutException`. If 500 ms pass without a result, `get` may throw `TimeoutException`. **The Future may still be running and uncancelled**.

### Outcomes of `get(timeout, unit)`

| Observed outcome | Meaning | Does it prove the worker stopped? |
| --- | --- | --- |
| Returns `T` | The Future completed normally with a result | The task represented by the Future completed; no guarantee external side effects were reverted |
| `ExecutionException` | The task completed exceptionally; the cause is in `getCause()` | The task managed by the Future finished with an error; sub-work it spawned may still be running |
| `TimeoutException` | No result received within the wait window | **No** |
| `InterruptedException` | The waiting thread was interrupted | **No** |
| `CancellationException` | The Future was cancelled when the caller retrieved the result | **Not necessarily**; the underlying task may not have actually stopped |

Calling `future.isDone()` after a timeout must also be interpreted accurately: `true` covers success, failure, and cancellation. Do not infer success from that flag alone. `isCancelled()` only states that the Future is in the cancelled state per its contract; it does not verify external resources.

**Never write logic** such as “`get` timed out so no order was created” or “timed out so immediately retry POST to create a new order” when the previous work may still be in progress.

## 4. `Future.cancel(boolean)` is a cancellation request, not a safe kill

`Future.cancel(mayInterruptIfRunning)` attempts to transition the task to the cancelled state. It may return `false` when cancellation is not possible, such as when the task has already completed; `true` means the Future cancellation request succeeded per contract. That success does not mean the running thread stopped immediately.

### 4.1. `cancel(false)` vs. `cancel(true)`

| Call | Key meaning | What is not guaranteed |
| --- | --- | --- |
| `cancel(false)` | Attempts to cancel without **requesting an interrupt** if the task is already running | Does not force an already-running worker to stop immediately |
| `cancel(true)` | Attempts to cancel and allows requesting an interrupt on the running thread | Does not force an uncooperative task to stop; does not roll back side effects |
| `get()` after a Future is cancelled | Throws `CancellationException` | Does not say whether the worker/remote is still running |
| `isCancelled()` | Checks whether the Future is in the cancelled state | Does not confirm I/O or external effects have stopped |

`cancel(true)` typically acts through **interruption** if the Future/Executor implementation supports it. However, Java interruption is a cooperative mechanism: it sets the interrupt flag or causes certain blocking APIs to throw `InterruptedException`. It is not a command that forcibly terminates arbitrary tasks.

For some running tasks, the Future may be marked cancelled while the worker continues for a while, or even runs to completion because it never checks for interruption. Once the Future is cancelled, `get()` will no longer return the worker's normal computed value, even if the worker finishes afterward.

### 4.2. Why `Thread.stop()` is not the answer

Do not use `Thread.stop()` to try to force cancellation because this API is deprecated for being unsafe: it can halt a thread at an arbitrary point, leaving shared objects/invariants in an inconsistent state and causing unpredictable consequences. Cooperative interruption, I/O timeout policies, and designing tasks with safe stopping points are the right practices to learn.

## 5. Interruption only works when underlying code cooperates

In Java, `Thread.interrupt()` represents **a request**. The task must observe and respond to it. Two common responses:

1. With interruptible blocking APIs such as `Thread.sleep`, `Object.wait`, `Thread.join`, or appropriate `BlockingQueue` operations, the thread can be woken up with `InterruptedException`.
2. In computation loops or operations that do not throw `InterruptedException` on their own, the code must check `isInterrupted()` or a cancellation token/flag with proper memory visibility.

Cooperative task pattern:

~~~java
Runnable worker = () -> {
    while (!Thread.currentThread().isInterrupted()) {
        try {
            processOneBatch();
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            break;
        }
    }
};
~~~

This is an illustrative fragment; `processOneBatch()` is undefined, and a policy is needed for other exceptions thrown by the task itself. If `processOneBatch()` takes minutes and does not support cancellation, the loop only checks the interrupt **after that method returns**. Therefore, place checkpoints inside long-running sections or propagate a deadline/cancellation into supporting sub-APIs.

### 5.1. The interrupt flag and `InterruptedException`

Blocking operations that throw `InterruptedException` typically clear the interrupt status when throwing. If code catches this exception and cannot declare `throws InterruptedException`, the standard pattern is to **restore the flag** and exit the task:

~~~java
try {
    queue.put(item);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

This is an illustrative fragment inside a `void` method where `queue` and `item` are declared. If you swallow the exception and continue, shutdown/cancellation may fail to stop the work. If the method signature allows `throws InterruptedException`, propagate the exception instead of handling it locally.

Distinguish clearly:
- `isInterrupted()` checks the thread's status **without clearing the flag**.
- `Thread.interrupted()` (static) checks the **current thread's** interrupt status and **clears the flag**.
- `Thread.currentThread().interrupt()` sets the flag again on the current thread.

Do not accidentally call `Thread.interrupted()` in a loop condition and lose the cancellation request if subsequent logic still needs to know.

### 5.2. Operations that do not necessarily interrupt immediately

Many tasks do not respond—or only respond indirectly—to interruption:
- CPU-bound loops that never check the flag.
- Native code, external libraries, or blocking APIs that do not specify interrupt behavior.
- Waiting to acquire a traditional `synchronized` intrinsic monitor: an interrupt request does not break monitor contention.
- I/O calls with their own timeout/semantics: do not assume every socket, JDBC call, or file operation immediately throws `InterruptedException`.
- Remote HTTP requests that have already reached the server: interrupting the client does not automatically make the server undo the operation.
- Code that catches `InterruptedException`, ignores it, and keeps running.

Different APIs respond to interruption in different ways—for example, by throwing an unchecked exception, closing a channel, or updating state; rely on the contract of the **specific API**. Do not assume every I/O library behaves like `Thread.sleep`.

### 5.3. Cooperative cancellation and cleanup

When a worker receives a cancellation request, it often needs to clean up **resources it owns**: closing streams, releasing locks, deleting temporary files, or rolling back uncommitted transactions. Use `try/finally` and `try-with-resources` at the appropriate scope.

However, `finally` is not an automatic rollback. If the worker already sent an email or committed to the database, cleanup after an interrupt does not retract that action. Furthermore, if cleanup itself performs non-interruptible blocking, cancellation responsiveness can still be slow; if cleanup throws an exception, preserve the primary cause according to your error-recording policy.

## 6. Complete Java 17 example: seeing the three limits

The following program intentionally uses `CountDownLatch` to control when the worker is allowed to proceed, rather than relying on random thread scheduling order.

1. `Future.get(timeout)` expires while the Future is still unfinished; releasing the latch lets the worker complete and the caller retrieve the result.
2. `Future.cancel(true)` cancels a sleeping task; here, `Thread.sleep` cooperates with interruption so the worker receives `InterruptedException`. Even though the worker returns a string after catching it, `Future.get()` on the cancelled Future still throws `CancellationException`.
3. `CompletableFuture.orTimeout` completes the future with `TimeoutException` while the supplier is still waiting on a latch. After releasing the latch, the worker finishes, even though the future is already in an error state.

Save as **`TimeoutCancellationLimitsDemo.java`**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

public class TimeoutCancellationLimitsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            CountDownLatch entered = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            Future<String> task = pool.submit(() -> {
                entered.countDown();
                release.await();
                return "work result";
            });
            entered.await();
            try {
                task.get(30, TimeUnit.MILLISECONDS);
            } catch (TimeoutException e) {
                System.out.println("get timed out");
            }
            System.out.println("after timeout, done=" + task.isDone());
            release.countDown();
            System.out.println("later result=" + task.get());

            CountDownLatch started = new CountDownLatch(1);
            CountDownLatch stopped = new CountDownLatch(1);
            AtomicBoolean noticedInterrupt = new AtomicBoolean();
            Future<String> cancellable = pool.submit(() -> {
                started.countDown();
                try {
                    Thread.sleep(Long.MAX_VALUE);
                    return "normal";
                } catch (InterruptedException e) {
                    noticedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                    return "stopped";
                } finally {
                    stopped.countDown();
                }
            });
            started.await();
            boolean accepted = cancellable.cancel(true);
            stopped.await();
            System.out.println("cancel returned=" + accepted);
            System.out.println("worker noticed interrupt=" + noticedInterrupt.get());
            try {
                cancellable.get();
            } catch (CancellationException e) {
                System.out.println("cancelled future has no result");
            }

            CountDownLatch stageStarted = new CountDownLatch(1);
            CountDownLatch stageRelease = new CountDownLatch(1);
            CountDownLatch stageFinished = new CountDownLatch(1);
            CompletableFuture<String> stage = CompletableFuture.supplyAsync(() -> {
                stageStarted.countDown();
                try {
                    stageRelease.await();
                    return "stage result";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "interrupted";
                } finally {
                    stageFinished.countDown();
                }
            }, pool);
            stageStarted.await();
            stage.orTimeout(30, TimeUnit.MILLISECONDS);
            try {
                stage.join();
            } catch (CompletionException e) {
                System.out.println("stage result=" + e.getCause().getClass().getSimpleName());
            }
            stageRelease.countDown();
            stageFinished.await();
            System.out.println("stage worker completed=" + (stageFinished.getCount() == 0));
        } finally {
            pool.shutdown();
        }
    }
}
~~~

Compile and run with JDK 17 or newer from the directory containing the file:

~~~bash
javac --release 17 TimeoutCancellationLimitsDemo.java
java TimeoutCancellationLimitsDemo
~~~

Expected stdout when the program runs normally without external interruption:

~~~text
get timed out
after timeout, done=false
later result=work result
cancel returned=true
worker noticed interrupt=true
cancelled future has no result
stage result=TimeoutException
stage worker completed=true
~~~

### 6.1. Why do these output lines matter?

**Future waiting for timeout section:** `entered.await()` ensures the task has entered the wait on `release`. Because the latch has not been opened, `get(30 ms)` cannot receive a result in time and throws `TimeoutException`. At this point, the Future is not done; when `main` calls `release.countDown()`, the task resumes and returns `work result`. The timeout has passed, yet the worker can still finish successfully.

**Cancel section:** `started.await()` ensures the worker has actually entered the task. `cancel(true)` requests cancellation; because the worker is in `Thread.sleep(Long.MAX_VALUE)`, the interrupt is delivered via `InterruptedException`. `stopped.await()` waits for the worker to finish its `finally` block before printing the flag; therefore, `worker noticed interrupt=true` does not rely on a racy early read. A cancelled Future does not return `"stopped"` via `get()`, even though the worker may finish its catch logic and return that value internally.

**CompletableFuture section:** the supplier waits on `stageRelease`. `stage.orTimeout(30 ms)` completes that future exceptionally if it has not finished within the window; `join()` observes a `CompletionException` wrapping `TimeoutException`. Only afterward does `main` release `stageRelease`. `stageFinished.await()` proves the supplier ran through `finally`. The last line does not mean `"stage result"` was published to the future: the future had already completed with an error earlier.

This example is a **latch-coordinated experiment**, not a production timeout strategy. The untimed `await()` calls are intentional because `main` knows when it will signal in this experiment; real tests and applications should use an overall deadline, escape hatches, and proper cleanup on unexpected errors.

## 7. `CompletableFuture.orTimeout` and `completeOnTimeout`

Java 9+ provides two convenience APIs, both available on Java 17:

~~~java
CompletableFuture<T> limited = original.orTimeout(2, TimeUnit.SECONDS);
CompletableFuture<T> defaulted = original.completeOnTimeout(fallback, 2, TimeUnit.SECONDS);
~~~

This is **illustrative syntax**, assuming `T`, `original`, and `fallback` are already declared. In both examples, the method called on `original` **returns that same CompletableFuture**; calling them back-to-back on the same object creates a race between the two policies rather than two independent handles as the variable names might suggest. When the deadline arrives and the future is still incomplete:

- `orTimeout` attempts to complete that `CompletableFuture` **exceptionally** with `TimeoutException`.
- `completeOnTimeout` attempts to complete that `CompletableFuture` **normally with the fallback value**.

They **do not automatically cancel or interrupt a running supplier** just because the future completed due to timeout. For `CompletableFuture.supplyAsync`, a running computation may continue on the executor even after the `CompletableFuture` already has a timeout result. If you want to interrupt the source, design an explicit cancellation handle/mechanism for that source and understand how cooperative the source is.

### 7.1. Timeout mutates a shared handle

When multiple callers hold references to **the same** `CompletableFuture`, calling `orTimeout` on the shared future can cause **all other callers** to observe that future completing with a timeout. This mutates the state of the Future object itself, not just “I no longer want to wait.”

If each caller needs its own timeout without altering the shared outcome, use a mechanism that bounds **the caller's wait** (such as `get(timeout)`) or create an appropriate dependent stage and apply the timeout to that private stage. Note the lifecycle and that cancellation propagation from a dependent stage back to the source is **not automatically guaranteed** merely because two stages are chained.

### 7.2. `completeOnTimeout` can mask work still in progress

Example:

~~~java
CompletableFuture<String> displayed =
        CompletableFuture.supplyAsync(() -> remoteSave())
                .completeOnTimeout("pending", 1, TimeUnit.SECONDS);
~~~

This is a fragment with `remoteSave()` undefined; it requires importing `CompletableFuture` and `TimeUnit`. If the supplier is still running after 1 second, `displayed.join()` may return `pending`. That only means **a default value was used as the future's result**. It does not prove the remote write stopped, never started, produced no side effects, or will not succeed later.

Do not use a fallback like `"saved"` for a save operation whose outcome is unknown, as that produces a false confirmation. A status like `PENDING`/`UNKNOWN` may be more appropriate if the system has a job ID and a post-processing lookup path.

### 7.3. `CompletableFuture.cancel(true)` differs from `FutureTask.cancel(true)`

`CompletableFuture` implements `Future` but does not directly control the thread executing the computation. Per the Java contract, the `mayInterruptIfRunning` parameter in `CompletableFuture.cancel(boolean)` **has no interrupt-control effect for this implementation**. The call completes the future exceptionally with `CancellationException` if it can still be cancelled; it does not guarantee interrupting the supplier running via `supplyAsync`.

Do not infer from `CompletableFuture.cancel(true)` that code inside `supplyAsync` received an interrupt like the `Future` returned by `ExecutorService.submit()`. This is a very practical difference between two mechanisms sharing the `Future` interface.

## 8. Cancellation races with normal completion

A task can finish right around the time the caller requests cancellation:

~~~text
Scenario A:
worker finishes -> Future receives result -> cancel() returns false

Scenario B:
cancel() marks cancelled -> worker may still be running ->
get() on the cancelled Future throws CancellationException

Scenario C:
caller's get(timeout) expires -> worker finishes right after ->
caller saw timeout on the previous wait, result may now be ready
~~~

All three can happen. No separate `isDone()` check followed by `cancel()` turns those two operations into an atomic “if not done, guarantee stop” protocol. After a timeout, the task may finish before the caller calls cancel; then cancellation fails, yet the result may already be recorded in the Future.

**Do not write business logic that depends on inferring millisecond-level ordering.** Build explicit branches:
- If `cancel` returns `false`, the task may have already completed or cancellation failed; re-read the managed state appropriately.
- If `cancel` returns `true`, the Future is cancelled, but underlying work/side effects still need a separate verification channel if required.
- If `get` times out, the caller did not receive a result within the deadline—it is not the task's final conclusion.

If a request involves real money or critical resources, an `UNKNOWN` state is usually safer than asserting absolute failure.

## 9. I/O timeout does not mean server-side rollback

An HTTP client can time out when:
- It cannot connect to the server within the configured interval.
- It is waiting to receive data from the server.
- The overall request exceeds its deadline.
- A proxy or load balancer drops the connection.
- The client is interrupted or cancelled through the library's own mechanism.

From the caller's perspective, a timeout while awaiting a response **cannot reliably distinguish**:
1. The request never left the client.
2. The request reached the server but was not executed.
3. The server executed and committed it, but the response was lost.
4. The server is still executing after the client stopped waiting.

Similarly, a JDBC query timeout or statement cancellation is a **control request** forwarded to the driver/database on a best-effort basis, not proof that all related operations rolled back. Check transaction boundaries, isolation, auto-commit, statement type, and commit status per the driver/database contract. A failure right at `commit` can leave an **indeterminate** outcome: the server committed, but the client never received the acknowledgment.

### 9.1. Risk of duplicate side effects when retrying after timeout

Payment flow example:

~~~text
Client sends POST /charge, requestId=abc
    -> service receives request and records payment
Client times out before receiving response
Client retries POST /charge with a new requestId
    -> service creates a second transaction
~~~

This is a design bug. When an operation has side effects, use a **stable idempotency key for the same logical request**, combined with server-enforced rules and status queries to prevent duplicate effects. Merely attaching a header named `Idempotency-Key` without atomic server-side storage/deduplication provides no guarantee.

A practical strategy:
1. Generate `operationId` once before the first request.
2. Resend **the same ID and valid payload** on retries per the remote API contract.
3. On timeout, query status by ID first or follow the server's protocol.
4. Return a structured status such as `PENDING`/`UNKNOWN` if the outcome cannot yet be determined.
5. Record the operation for reconciliation when the final outcome cannot be confirmed immediately.

Do not retry indefinitely or issue concurrent duplicate retries without knowing the receiver's deduplication mechanism. If the task is a background job that must survive restarts, an in-memory `Future` handle is not enough; you need durable job/queue state or an appropriate orchestrator.

## 10. Propagating deadlines to downstream steps

For a request with a total budget of 2 seconds, giving each of three sub-calls 2 seconds can push total latency far beyond the limit. Allocate a **shared deadline** and pass the remaining time down to each step.

Java conceptual example:

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(2);

// Before each step:
long remaining = deadline - System.nanoTime();
if (remaining <= 0) {
    throw new TimeoutException("overall deadline exceeded");
}
String value = future.get(remaining, TimeUnit.NANOSECONDS);
~~~

This is a fragment requiring imports for `TimeUnit` and `TimeoutException` as well as handling other checked exceptions from `get`. `System.nanoTime()` is suitable for **measuring elapsed time** within a single process, not for logging timestamps or synchronizing with external services. Extremely large deadlines may require overflow handling; for normal business timeouts and reasonable bounds, this pattern illustrates the remaining-budget principle.

If the HTTP client layer supports a per-request timeout, pass `remaining` (or an appropriate smaller cap) to the client. If the database driver provides a query timeout or cancellation API, configure it per contract. Even so, full deadline propagation only **bounds wait time and attempts to stop**—it does not guarantee remote side effects will be undone.

### 10.1. Must you always cancel on timeout?

No. The caller can:
- **Simply stop waiting** and let a shared job continue running, such as a cache warm-up task.
- **Request cancellation** if the work is no longer valuable, the caller owns cancellation rights, and the task supports stopping.
- **Switch to background tracking** with a job ID and status polling when stopping safely is not possible.
- **Reconcile external state** if the task already sent a side-effecting request whose outcome is unknown.

Automatically cancelling a Future **shared across multiple requests** can cause other requests to lose their results. The orchestration layer must establish handle ownership before cancelling. Do not blindly put `cancel(true)` into every `catch (TimeoutException)` block without understanding the consequences.

## 11. `ExecutorService.shutdownNow()` does not safely force-stop

In Java 17:

| API | Meaning | Limitation |
| --- | --- | --- |
| `shutdown()` | Rejects new tasks; submitted tasks continue per executor rules | Does not cancel already-running tasks |
| `shutdownNow()` | Attempts to stop running tasks, typically via interrupt, and drains queued tasks | Does not guarantee all running tasks will stop |
| `awaitTermination(timeout, unit)` | Waits for the executor to terminate within the deadline | Returns `false` if not terminated yet; does not mean every task succeeded |

Typical shutdown code needs a wait deadline, a signaling policy, interruption handling, and logging of tasks that failed to terminate. Calling `shutdownNow()` twice or closing the pool cannot fix a task blocked in non-interruptible work; you must fix **the task or underlying API** to provide an exit path.

If a worker holds a file lock, connection, or resource it exclusively owns, letting the worker release it in `finally` is usually safer than an external thread arbitrarily closing a shared resource. Some APIs support cancellation by closing a task-owned resource, but read the thread-safety contract and true ownership scope before doing so.

## 12. Design options for long-running tasks

### 12.1. Split work into small units with cancellation checkpoints

If a task processes many items, instead of one long unchecked loop:
- Maintain state at points where progress can be observed.
- Check the deadline or interrupt flag at an appropriate cadence.
- Stop at a consistent boundary without leaving invariants broken.
- Clean up resources in `finally` or try-with-resources.
- Return a cancelled/partial result status if the contract allows.

Checking too frequently can add overhead, while checking too rarely delays cancellation; choose the frequency based on per-unit cost and stopping latency requirements. A task holding a long-lived lock needs a clear policy so other threads are not left blocked when it is cancelled.

### 12.2. “Partial success” outcomes should be explicit

If 70 out of 100 files were processed before timing out, the system should not just return `false`. Depending on the domain, use results like `Completed(100)`, `Partial(70, failures)`, `Cancelled(70)`, or `Unknown(operationId)`. If the caller needs to resume or compensate, it must know:
- Which units completed.
- Which units were not processed or have unknown status.
- Which parts can be safely retried.
- Which outcomes have already been committed or published.

A Future's `CancellationException` alone carries none of that information. A progress/identifier channel outside the Future may be necessary, especially after a crash or restart.

### 12.3. Stopping safely does not mean undoing

A worker interrupted after writing 70 records may stop very quickly, yet those 70 records remain if they were already committed. If “all or nothing” is required, use transactions or atomic publishing within what the resource supports. If actions spanned multiple systems, you need compensation, sagas, outboxes, or reconciliation; each has limits, and compensation itself can fail.

## 13. Common anti-patterns

### Mistake 1: Timeout means the task failed completely

~~~java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    return "nothing happened";
}
~~~

This is a fragment for anti-pattern analysis; other checked exceptions/types must be handled in real code. `TimeoutException` only means the caller did not get a result within one second. Returning `"nothing happened"` can be wrong if the server already wrote data or the worker will still process it.

### Mistake 2: `cancel(true)` means the worker is definitely dead

~~~java
future.cancel(true);
System.out.println("work was stopped");
~~~

This is an illustrative fragment with no verification that the worker stopped. Distinguish between **requesting Future cancellation** and **confirming worker completion** if the caller needs that confirmation. Use a separate completion channel or job state model, while keeping a timeout so you do not wait forever.

### Mistake 3: Swallowing `InterruptedException`

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException ignored) {
    // Continue running as if there were no cancellation request.
}
~~~

This is an anti-pattern fragment. To respect cancellation requests, propagate the exception or restore the interrupt flag and exit the task per contract. Do not turn an interrupt into a worker failure value when it was actually the coordinating thread that got interrupted.

### Mistake 4: `orTimeout` automatically interrupts all upstream stages

If stage A calls a remote service, stage B chains from A, and B has a timeout, this does not issue a guaranteed cancel to the socket/remote service used by A. Dependent stages only express result dependencies; stopping the source requires a cancellation mechanism supported by the source API.

### Mistake 5: Retrying a side-effecting task with a new operationId

A network error or timeout can arrive after a commit. If a retry generates a different `operationId`, the receiver may execute the side effect twice. Reuse the same `operationId` and proper server-side idempotency/status-lookup contracts.

### Mistake 6: Assuming `Future.isDone()` means all resources are cleaned up

A Future can be done due to cancellation, stage timeout, or abnormal completion. With `CompletableFuture`, the underlying supplier may still be active after the future completed due to timeout. Verify resource/worker cleanup through a dedicated channel when guarantees are required.

### Mistake 7: Closing arbitrary resources from the coordinating thread

Closing a connection or stream shared by another task or multiple requests can break other work. Only close resources with clear ownership or use vendor-supported cancellation APIs with explicit thread-safety rules.

## 14. Testing the real limits of timeout and cancellation

A good test suite must deterministically construct states at the right moments rather than relying on `Thread.sleep(100)` and guessing scheduler behavior. `CountDownLatch` lets you know when a task has started, block it at a deterministic point, and release it when desired.

| Scenario | Behavior to verify |
| --- | --- |
| `get(timeout)` expires | Caller receives `TimeoutException`, but Future is not automatically cancelled |
| Latch released after timeout | Worker can still finish and return a result |
| `cancel(true)` while task is in `sleep` | Worker receives interrupt and runs cleanup; Future reports cancelled |
| `cancel(true)` on CPU task ignoring interrupt | Future may report cancelled, but worker continues until its logic exits |
| `cancel(false)` while task is running | No promise that an interrupt is sent to the worker |
| `CompletableFuture.orTimeout` on blocked supplier | Future completes exceptionally with timeout; supplier may continue |
| `completeOnTimeout` | Future returns fallback, but source may still be running |
| `cancel(true)` on `CompletableFuture` | Do not assume the supplier receives an interrupt |
| Timeout right near completion | Accept races among result, timeout, and cancellation per contract |
| Caller interrupted during `get` | Handle `InterruptedException`; do not infer the task failed |
| Remote operation times out after commit | Query `operationId` to verify; do not duplicate side effects |
| Multiple consumers share one future | One caller's timeout/cancellation does not unexpectedly break another's result |

When simulating a task that **ignores interrupts** in a test, only do so with a deadline and a guaranteed exit—such as a latch released in the test's `finally` block. Avoid creating unrecoverable infinite loops. Cleanup tests should verify that the worker actually exited its processing section, not just assert `Future.isCancelled()`.

Do not assert a specific log order across two threads unless the test establishes a synchronization relationship. When testing millisecond-level bounds, use latches or event points that deterministically decide the outcome rather than tight timeouts tuned to machine speed, which cause flaky tests.

## 15. Decision tree after a caller times out

~~~text
Caller has no result before the deadline
|
+-- Read-only work with no side effects?
|      +-- Yes: return timeout / let task finish or request cancellation
|      +-- Unsure: inspect sub-tasks and external system impact
|
+-- Does the caller own cancellation rights?
|      +-- No: do not cancel a shared task just because one caller timed out
|      +-- Yes: consider cancelling based on what the task supports
|
+-- Does the task support interruption/deadlines?
|      +-- Yes: issue the request and verify stop progress via a managed channel
|      +-- No: redesign I/O/task or use a pending status
|
+-- Are there indeterminate external effects?
       +-- Yes: use operationId, idempotency, status lookup/reconciliation
       +-- No: report cancelled/incomplete outcome per contract
~~~

There is no universal “timeout → roll back everything” branch. The right path depends on work scope, ownership, cancellation cooperation, and each resource's protocol.

## 16. Checklist for asynchronous Java APIs

1. **Name states accurately:** timeout means “no result received in time”; Future cancel means “handle cancelled”—do not equate either with worker stopped or side effects undone.
2. **Propagate deadlines purposefully:** bound caller wait times and configure network/database timeouts per the specific API.
3. **Cancel only with ownership:** distinguish private vs. shared Futures; avoid cancelling a job still needed by other callers.
4. **Make tasks cooperative:** check interrupts/deadlines, never swallow `InterruptedException`, establish consistent stopping points, and clean up scoped resources.
5. **Know the APIs:** `Future.get(timeout)` does not cancel; `Future.cancel(true)` only attempts cancel/interrupt; `CompletableFuture.orTimeout` completes the future exceptionally; `CompletableFuture.cancel(true)` does not guarantee interrupting the supplier.
6. **Expect races:** a task may finish as timeout/cancellation occurs; read state in a controlled manner without relying on unsynchronized ordering.
7. **Respect side effects:** cancelling a Java task does not roll back a remote service. For side-effecting requests, use idempotency keys and status lookups when needed.
8. **Design the lifecycle:** manage executors, await shutdown within a deadline, log tasks that could not terminate, and prevent resource leaks.
9. **Report meaningful outcomes:** distinguish completed, failed, cancelled, pending, and unknown; provide job IDs/progress if results may arrive after the caller timed out.
10. **Test the underlying state:** verify whether the worker/remote actually stopped, rather than only asserting handle exceptions or flags.

### Applied exercise

Design a Java service that accepts a request to export a report and upload it to object storage. The API must respond within 3 seconds, while the work may take up to 30 seconds. Answer:

- When `future.get(3, SECONDS)` times out, should you return “failed”, “accepted”, or a job ID for follow-up lookup? Why?
- If the user cancels the report, where should `cancel(true)` be called? Does the upload task support stopping? If the upload already completed in storage but the response was lost, what is the right status?
- Can a single `CompletableFuture.orTimeout(3, SECONDS)` be shared across multiple callers? What happens to the supplier?
- If the upload is retried, how do you avoid creating two files with the same content under different identifiers or mistakenly publishing two versions?
- Write a latch-based test proving the task is still running after timeout; add a test showing the worker receives an interrupt and cleans up temporary files without arbitrarily deleting an already-published file.

**Key takeaway:** Timeout bounds **waiting or future state**, while cancellation is a **request to cancel**. Whether an executing task actually stops—and how its effects on files, databases, or external services are controlled—depends on task design and the underlying system's protocols.
