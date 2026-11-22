# Designing Shutdown with Cancellation, Timeouts, and Resource Closing

A Java application often has many tasks running concurrently: reading files, querying databases, calling APIs, processing messages, performing background computations, and writing results. When the application needs to shut down, simply calling `System.exit()` or `ExecutorService.shutdown()` and abandoning the workers can lead to lost tasks, partially written data, leaked socket/file handles, and a process that fails to exit. Conversely, closing resources before workers stop using them can cause `IOException`, transaction errors, or incomplete writes.

This practical exercise asks you to design **a shutdown workflow with explicit states** that supports:

- Rejecting new tasks immediately once shutdown begins.
- Giving running and queued tasks an opportunity to complete within a bounded **grace period**.
- Requesting task cancellation via interruption and handling unstarted tasks when time expires.
- Providing a separate bounded **force period** to wait for workers to respond to cancellation.
- Closing shared resources **only after workers have actually stopped**; if they fail to stop, reporting an unsafe state and letting a higher-level coordinator handle it.
- Avoiding turning `cancel(true)`, `shutdownNow()`, or timeouts into a false promise that side effects have been rolled back.

The scope is general Java concurrency using JDK 17 APIs, without relying on Spring-specific lifecycle hooks or configuration.

## 1. Model and Exercise Goals

Suppose a service processes data import jobs. Each job may wait on I/O and use a shared resource such as a file writer or connection. When a stop request arrives, a shutdown coordinator must ensure that no new tasks slip into the executor while the system is closing.

```text
        RUNNING
    accept / run tasks
           |
           | receive stop signal
           v
       QUIESCING
     block new tasks
    executor.shutdown()
           |
           | grace time remaining?
           +---------------------------+
           |                           |
   all tasks finished            grace timeout
           |                           |
           v                           v
     TERMINATED                   CANCELLING
                              shutdownNow(), cancel
                                       |
                                wait force time
                                 /           \
                            stopped      still running
                               |               |
                               v               v
                         TERMINATED        NOT_TERMINATED
                               |               |
                               v               v
                         close resources   report error, do not
                            in order       close resources still
                               |           used by workers
                               v
                             CLOSED
```

Here, `RUNNING`, `QUIESCING`, `CANCELLING`, `TERMINATED`, and `CLOSED` are **application-level design states**, not `ExecutorService` state names. An executor has `isShutdown()` and `isTerminated()`, but it does not automatically manage all business resources.

**Exercise completion criteria:** new tasks are rejected after the admission gate closes; cooperative tasks are interrupted; tasks remaining in the queue do not run after escalation; shutdown does not wait indefinitely; resources are closed in the proper order; and results distinguish between a graceful stop, a stop after escalation, and a failure to stop.

## 2. Understanding Shutdown and Cancellation APIs

| API | Guarantees / Meaning | Does Not Guarantee |
|---|---|---|
| `ExecutorService.shutdown()` | Transitions the executor to a state that rejects new work; executes previously submitted tasks | Does not wait for tasks to finish; does not interrupt running tasks |
| `awaitTermination(timeout, unit)` | Waits up to the allowed duration; returns `true` if the executor has terminated | `false` does not cancel tasks; a timeout does not clean up resources |
| `shutdownNow()` | Attempts to stop running tasks via `Thread.interrupt()`; stops processing queued tasks and returns the list of unstarted tasks | Does not force running tasks to stop; does not automatically call `Future.cancel` on returned tasks |
| `Future.cancel(false)` | Attempts to cancel an unstarted task without requesting interruption of a running task | Does not reliably stop a task that has already started |
| `Future.cancel(true)` | Requests interruption of the running thread if possible | Does not undo I/O or side effects; a task may ignore interruption |
| `Future.get(timeout, unit)` | Limits the time **the caller waits for the Future result** | Does not bound the worker's CPU/I/O time or cancel the task automatically |
| `AutoCloseable.close()` | Closes the resource according to each class's contract | Does not guarantee that all workers have stopped using the resource |

`shutdown()` is the executor's **graceful shutdown**: it waits to finish what has already been accepted. `shutdownNow()` is **best-effort cancellation**: Java sends an interrupt, but a thread only stops when the task checks for it or a blocking operation is woken up. A busy loop that never checks the interrupted flag will keep running. Some I/O drivers do not support interruption; in those cases, you typically need an explicit timeout, closing the underlying channel, or the library's own cancellation mechanism.

`shutdownNow()` returns unstarted `Runnable` instances; if submitted via `submit()`, they are usually `RunnableFuture` instances, so you can call `cancel(false)` so callers waiting on `Future.get()` do not hang. If submitted via `execute()` with a plain `Runnable`, the application must have its own way to report the rejected/dropped status. Never assume returned tasks have completed.

**Interruption is a cooperative protocol:** when a piece of code catches `InterruptedException`, it should exit early or rethrow it. If it genuinely must catch without rethrowing, restore `Thread.currentThread().interrupt()` so upper layers still know about the cancellation signal. Never swallow an interruption and continue an infinite loop.

## 3. Before Writing Code: Designing Resource Ownership

A simple resource ownership diagram:

```text
Shutdown owner
  |
  +-- admission gate (reject new tasks)
  |
  +-- executor workers
  |       |
  |       +-- uses shared writer / client / connection
  |
  +-- resource owner (closes after workers stop)
```

Whichever component creates a resource must be responsible for closing it, or explicitly transfer ownership. If each task opens an independent `InputStream`, use `try-with-resources` inside the task to close it in the proper scope. If multiple tasks share a writer or client, the owning component should close it only after all tasks have stopped using it.

When shutting down multiple components, you usually need to **close in reverse dependency initialization order**: stop the work producer first; let consumers finish; flush/commit pending records per contract; and only then close writers, clients, connection pools, and underlying resources. For logging, keep the logger active long enough to record the final shutdown event.

Do not default to `finally { resource.close(); }` in the shutdown-managing thread if workers might still be running. `finally` is useful for releasing resources owned exclusively by the caller, whereas shared resources require **confirmation that no users remain** or a safe independent close protocol.

## 4. Complete Java 17 Example: Graceful Timeout, Forced Cancellation, and Resource Close

This example has a single-worker executor, a long-running job waiting on a `CountDownLatch`, another job waiting in the queue, and a simulated shared resource. When shutdown starts, the first job does not finish within the grace period, so the service escalates to `shutdownNow()`. The worker cooperates with interruption; the queued job is cancelled; and once the executor terminates, the resource is closed. The file name must be **`ShutdownPractice.java`**.

```java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class ShutdownPractice {
    static final class Resource implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        void checkOpen() {
            if (closed.get()) throw new IllegalStateException("Resource closed");
        }

        boolean isClosed() { return closed.get(); }

        @Override public void close() { closed.set(true); }
    }

    record ShutdownResult(boolean graceful, boolean terminated,
                          int cancelledQueued) {}

    static final class Service {
        private final Object admissionLock = new Object();
        private final Resource resource = new Resource();
        private final ExecutorService workers =
                Executors.newSingleThreadExecutor(r -> new Thread(r, "job-worker"));
        private boolean accepting = true;

        Future<?> submit(Runnable action) {
            synchronized (admissionLock) {
                if (!accepting) throw new RejectedExecutionException("Stopping");
                return workers.submit(() -> {
                    resource.checkOpen();
                    action.run();
                });
            }
        }

        ShutdownResult stop(Duration grace, Duration force)
                throws InterruptedException {
            synchronized (admissionLock) {
                accepting = false;
                workers.shutdown();
            }
            boolean graceful = false;
            int cancelled = 0;
            try {
                graceful = workers.awaitTermination(
                        grace.toNanos(), TimeUnit.NANOSECONDS);
                if (!graceful) {
                    List<Runnable> notStarted = workers.shutdownNow();
                    for (Runnable task : notStarted) {
                        if (task instanceof Future<?> future) {
                            future.cancel(false);
                        }
                        cancelled++;
                    }
                    if (!workers.awaitTermination(
                            force.toNanos(), TimeUnit.NANOSECONDS)) {
                        return new ShutdownResult(false, false, cancelled);
                    }
                }
                resource.close(); // Close only after all workers have stopped.
                return new ShutdownResult(graceful, true, cancelled);
            } catch (InterruptedException e) {
                workers.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }

        boolean resourceClosed() { return resource.isClosed(); }
    }

    public static void main(String[] args) throws InterruptedException {
        Service service = new Service();
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean workerInterrupted = new AtomicBoolean();

        service.submit(() -> {
            started.countDown();
            try {
                new CountDownLatch(1).await(); // Simulate a long-running task.
            } catch (InterruptedException e) {
                workerInterrupted.set(true);
                Thread.currentThread().interrupt();
            }
        });
        Future<?> queued = service.submit(() -> {
            throw new AssertionError("Queued task must not run");
        });
        if (!started.await(2, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Worker did not start");
        }

        ShutdownResult result = service.stop(
                Duration.ofMillis(100), Duration.ofSeconds(2));
        System.out.println("Graceful: " + result.graceful());
        System.out.println("Terminated: " + result.terminated());
        System.out.println("Queued cancelled: " + queued.isCancelled());
        System.out.println("Worker interrupted: " + workerInterrupted.get());
        System.out.println("Resource closed: " + service.resourceClosed());
        try {
            service.submit(() -> {});
        } catch (RejectedExecutionException e) {
            System.out.println("New task rejected: true");
        }
    }
}
```

Compile and run commands:

```bash
javac -encoding UTF-8 ShutdownPractice.java
java ShutdownPractice
```

Output on the normal execution path:

```text
Graceful: false
Terminated: true
Queued cancelled: true
Worker interrupted: true
Resource closed: true
New task rejected: true
```

This example designs explicit synchronization points so the outcome can be verified: `started.await()` ensures the worker is executing the indefinitely waiting job; the queue holds a second job; the grace period expires because the worker has not finished; `shutdownNow()` interrupts the running job and returns the unstarted job; the unstarted job's `Future` is cancelled; and `awaitTermination()` confirms the executor has stopped before closing `Resource`. The resource in this example is **simulated with an `AtomicBoolean`**, not a real file writer or database connection.

In this code, `Service.stop()` is called once from a single management thread. If production allows multiple callers to invoke stop concurrently, you must design shutdown state/idempotency so that only one owner coordinates escalation and closes resources once. `Resource.close()` in the example simply sets a flag, whereas a real resource may throw `IOException`; close errors must be recorded or reported according to contract.

### Why Does `admissionLock` Matter?

If `submit()` checks `accepting` outside a lock, a race condition occurs:

```text
Thread A: sees accepting=true
Thread B: sets accepting=false; executor.shutdown()
Thread A: executor.submit(...) -> RejectedExecutionException
```

In this exercise, `submit()` and the `accepting=false; workers.shutdown()` block hold the same monitor. This establishes a clear synchronization boundary between the admission decision and the transition to stopping. Callers should still handle `RejectedExecutionException` per contract, especially if the executor can be shut down by another owner or wrapped by additional layers.

**Do not hold `admissionLock` during `awaitTermination()`:** waiting for a long time under a lock can block other paths that need the lock, or cause a deadlock if a worker needs that lock to finish. The example only holds the lock to update state and submit work, then waits outside the lock.

### Why Close Resources Only When `terminated=true`?

When `awaitTermination(force)` returns `false`, a worker may still be running and holding references to a writer, socket, or connection. Closing the resource immediately can race with writes, break transactions, or throw confusing errors. The demo intentionally returns `ShutdownResult(false, false, ...)` and **does not close the resource** while workers are still active. This signals the management layer to escalate handling: log the incident, collect stack/thread dumps, enforce I/O timeouts at the real layer, coordinate with a supervisor, or terminate the process per operational policy.

This mechanism does not guarantee that all state has been flushed or committed successfully: for each job, you must define when output is considered durable, and when retries and idempotency are needed to prevent duplicate processing.

## 5. Long-Running Tasks Must Cooperate with Cancellation

A non-blocking CPU-bound task must periodically check for interruption and stop at a safe point:

```java
// Illustrative logic inside a Runnable/Callable, not a standalone file.
while (hasMoreWork()) {
    if (Thread.currentThread().isInterrupted()) {
        persistCheckpointIfSafe();
        return;
    }
    processNextChunk();
}
```

`hasMoreWork()`, `persistCheckpointIfSafe()`, and `processNextChunk()` are placeholders representing business logic, not standard Java APIs. With interruptible blocking APIs—such as `BlockingQueue.take()`, `CountDownLatch.await()`, or `Thread.sleep()`—`InterruptedException` allows an early exit. A suitable pattern:

```java
try {
    workBlocking();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
} finally {
    releaseTaskOwnedResources();
}
```

The snippet above is Java pseudocode with hypothetical business methods. If a task catches `InterruptedException`, merely logs it, and continues a `while(true)` loop, escalation has no effect. Never call `Thread.stop()` to force a worker to halt: that API is unsafe, can release locks prematurely, and can corrupt object invariants.

Cancellation also has **business boundaries**: a partially written file needs a temp file + atomic rename (if supported by the filesystem) or checkpoint/cleanup; a database transaction needs proper rollback or commit; an external partner call may have already produced side effects before timing out, requiring an idempotency key and reconciliation. An interrupt cannot undo an already committed payment.

## 6. Timeouts: Distinguishing Three Layers

During shutdown, there are at least three distinct kinds of timeouts:

1. **Grace timeout:** how long accepted tasks are allowed to finish without active interruption.
2. **Force timeout:** how long to wait after sending cancellation/interruption requests.
3. **Per-task / per-I/O timeout:** time limits on socket, HTTP, lock, or queue waits even before shutdown begins.

Grace and force periods do not replace I/O timeouts. A task stuck in a library that ignores interruption can keep `awaitTermination` returning `false`. Similarly, `Future.get(2, SECONDS)` only bounds how long the thread **calling `get`** waits for the result; the worker can keep running after the caller times out. To cancel, you must call `cancel(true)` and have a cooperative task.

Consider an **overall shutdown deadline** rather than granting each step an unbounded full budget. For example, with a 10-second stop budget—6 seconds graceful, 4 seconds forced—subtract elapsed time at each stage; if many resources must be closed, reserve budget for flushing, closing, and reporting. Measure elapsed time with `System.nanoTime()` or an appropriate monotonic API; do not use `System.currentTimeMillis()` for accurate timeout tracking because the wall clock can jump.

One subtle detail: `Duration.toNanos()` can throw `ArithmeticException` if the duration is too large, and negative durations make no sense for shutdown. Production code should validate `Duration` parameters upfront (non-negative, no overflow, reasonable bounds) and choose a precision appropriate for the API.

## 7. Critical Scenario: A Task Still Refuses to Stop

If a worker ignores interruption:

```java
// Code illustrating a faulty task; should not be run in the main demo.
while (true) {
    doNonInterruptibleWork();
}
```

Even `shutdownNow()` only sends an interrupt. `awaitTermination(force)` may return `false`; Java has no safe mechanism to kill an individual thread that may hold monitors and access shared memory. In this situation:

- Surface the `NOT_TERMINATED` state along with the count of active workers/pools.
- Restrict new requests and leave resources still in use by workers open to avoid close races.
- Apply downstream-specific timeouts or cancellation if the API supports them.
- Collect thread dumps, stuck-task IDs, thread names, and elapsed times.
- If the workflow cannot recover, a process supervisor may need to terminate the process at a deadline and restart cleanly.

Never promise that data has been flushed when `close()` has not completed or workers are still active. If `shutdownNow()` returns unstarted tasks, classify which ones can be dropped and which must be re-enqueued into a durable queue. Do not blindly resubmit: an interrupted task may have already caused side effects, so retries must be idempotent.

### What If the Shutdown Coordinator Thread Itself Is Interrupted?

In the example, when `awaitTermination()` throws `InterruptedException`, the code calls `shutdownNow()`, restores the interrupt flag, and rethrows; shared resources are left unclosed because worker termination has not been proven. This avoids a close race, but **does not yet implement full handling of each queued `Future` in the interrupt branch**. A production system needs a supervisor responsible for taking over the shutdown process, cancelling or reporting status for queued tasks, and continuing to monitor until workers actually stop or the process is terminated by operational policy.

If an API contract forbids throwing `InterruptedException`, you must explicitly decide whether to ignore interruption during the final closing phase; you must still respect the time budget and restore the interrupt flag afterward. Never swallow the exception and declare shutdown complete.

## 8. Closing Real Resources in the Right Order

| Resource Type | Who Closes It? | Conditions / Notes |
|---|---|---|
| `ExecutorService` | Executor owner | `shutdown` → bounded `awaitTermination` → optional `shutdownNow` |
| Per-task `InputStream`, `OutputStream`, `Reader`, `Writer` | The task itself | `try-with-resources`; do not wait for a manager to close |
| Shared file writer | Owner after workers stop | Account for flushing, close errors, and multi-thread write consistency |
| Shared HTTP client or socket | Owner per client lifecycle | Check the specific client's timeout and close semantics |
| JDBC `Connection` inside a task | Connection-owning code | `try-with-resources`; handle rollback/commit explicitly |
| Database connection pool | Service-level owner | Stop accepting requests, drain in-flight work, then close the pool |
| `ScheduledExecutorService` | Scheduler owner | Stop scheduling new jobs; check policy for cancelling periodic/delayed tasks |
| Queue/message consumer | Consumer owner | Stop receiving first; ack and retry per delivery semantics |
| Flushable buffer/cache | Data owner | Needs dedicated flush time and a way to verify durability |

Not every resource is thread-safe when `close()` races with `use()`. Read the specific resource's contract. Some clients allow `close()` to abort pending connections, while others do not. This exercise prioritizes the order **stop producer → drain workers → escalate if needed → close downstream** for shared resources.

For `AutoCloseable` resources, use `try-with-resources` whenever lexical scoping fits. When shutting down multiple independent resources, if closing the first throws an exception, you should still attempt to close the remaining ones and aggregate/report the errors rather than leaving other connections open. `try-with-resources` automatically manages suppressed exceptions within its declared resource scope.

## 9. Extended Exercise: Multi-Component Shutdown Design

Suppose an application has the following pipeline:

```text
Scheduler -> Producer -> Queue -> Workers -> Database / OutputWriter
                    \-> MetricsExporter
```

Design a shutdown workflow with these requirements:

1. Upon receiving a shutdown signal, the scheduler stops creating new batches; the producer stops accepting tasks.
2. The queue has an explicit admission close; accepted jobs are either processed or marked unprocessed for safe retry.
3. Workers have a `gracePeriod` and are cancelled on expiration; each task uses I/O timeouts and interruption.
4. Jobs requiring durability have idempotency/receipts so they can be replayed after a restart without duplicating side effects.
5. The database pool/writer is closed only after no workers are using it; metrics and logging remain open long enough to record the shutdown outcome.
6. If any worker ignores interruption, record `NOT_TERMINATED` and let a supervisor handle it according to a deadline.
7. Include tests that prove the closing order, rather than relying on logs that merely look plausible.

The API design should expose a `ShutdownReport` result—for example `graceful`, `terminated`, `cancelledQueued`, `timedOut`, `resourceCloseFailures`, and actual elapsed time. Name fields accurately so `cancelledQueued` counts **cancellation requested / Future state transitioned**, rather than implying that side effects never occurred for tasks that had already started.

**Extension A:** Add a per-job timeout and a `CANCEL_REQUESTED` state distinct from `CANCELLED`. If a task has written to the database but is interrupted before acking, specify how a retry avoids creating duplicate records.

**Extension B:** Replace the simulated `Resource` with a `BufferedWriter` writing to a temporary file, where each task writes a formatted line. Use a lock or appropriate thread-safe writing strategy, and verify that `close()` never runs before the last worker finishes. Do not share a writer across threads if the API does not guarantee thread safety.

**Extension C:** Allow multiple callers to invoke stop concurrently; design an `AtomicReference<State>` or lock so only one shutdown execution performs escalation and resource closing while other callers wait for the same result. Avoid deadlocks between `submit`, `stop`, and worker callbacks.

## 10. Acceptance Tests

| Scenario | Expected Behavior |
|---|---|
| No tasks, stop called | Executor terminates, resources close |
| All tasks finish within grace | No `shutdownNow` needed; `graceful=true` |
| Task waiting on an interruptible operation | Grace expires, interruption stops worker; resources close after termination |
| Unstarted task in the queue | After `shutdownNow`, does not run; Future/receipt reflects cancelled state |
| Submit racing with stop | Accepted only before admission closes; rejected cleanly afterward |
| Worker throws `RuntimeException` | Does not leak task resources; shutdown still completes and error is reported |
| Worker ignores interrupt | Force timeout expires, `terminated=false`; does not claim resources were safely closed |
| Shutdown coordinator thread is interrupted | Not treated as completed; supervisor continues cleanup |
| Resource `close()` throws an exception | Close failure is reported without losing information about unfinished tasks |
| Two concurrent stop calls | Single shutdown execution; no double-close or inconsistent cancellation |
| Task causes side effects then times out | Retry uses idempotency/reconciliation; cancellation is not treated as rollback |
| Multiple executors and schedulers | Stopped in dependency order; no new tasks submitted to a closed executor |

To keep tests independent of thread scheduling, use `CountDownLatch`, `CyclicBarrier`, or controlled synchronization to construct the scenarios under test. Avoid relying solely on arbitrary `Thread.sleep()` calls to "make sure a task has started." Use timeouts on all critical `await()` calls in tests to avoid hanging the entire CI pipeline.

Track real metrics during shutdown: accepted, completed, cancelled, queued, and active task counts; tasks still running at timeout; graceful and forced durations; whether resources closed cleanly or failed; and IDs of unprocessed jobs. The count of cancelled `Future` instances alone does not prove side effects were rolled back; combine it with business state and transaction status.

## 11. Common Design Mistakes

- **Calling `shutdown()` and assuming the executor has stopped:** `shutdown()` only rejects new tasks; it does not wait for completion.
- **Waiting indefinitely:** a single task stuck on I/O prevents the process from stopping by its deadline.
- **Calling `shutdownNow()` and immediately closing the writer:** interruption is only a cooperative request; a worker may still be writing.
- **Ignoring the `Runnable` list returned by `shutdownNow()`:** unstarted jobs lack a clear result/contract, and `Future.get()` can hang.
- **Closing resources in the shutdown owner's `finally` block regardless of `isTerminated()`:** races with workers that have not stopped.
- **Swallowing `InterruptedException`:** drops the cancellation signal and renders escalation ineffective.
- **Setting a timeout only on `Future.get()`:** the waiting thread is released, but the worker and its I/O can keep running forever.
- **Not blocking admission before draining:** producers keep submitting tasks while consumers are shutting down.
- **Using `Thread.stop()`:** can corrupt data invariants and leave locks in an inconsistent state.
- **Confusing cancelled with rolled back:** a task that already executed side effects may be retried and duplicated.
- **Closing resources in arbitrary order:** a dependency still in use gets closed prematurely.
- **Not handling concurrent shutdown calls:** multiple callers invoking stop can double-close resources or report conflicting states.

## 12. Conclusion and Implementation Checklist

When designing a safe Java shutdown, answer all of these questions:

1. Who owns task admission, who owns the executor, and who owns each resource?
2. What boundary guarantees no new tasks can slip in once stopping begins?
3. What are the grace and force timeouts, and which workload and SLA justify them?
4. Do tasks cooperate with interruption, and does all blocking I/O have appropriate timeouts?
5. How are queued tasks cancelled or reported as failed, and do they need to survive restarts?
6. What state confirms all workers have stopped before resources are closed?
7. If a worker fails to stop, who takes over escalation and ensures the process does not hang?
8. Does the shutdown report distinguish graceful, forced, timed out, cancelled, and close failures?
9. Are there interleaving and fault-injection tests for races, exceptions, cancellation, and resource closing?

**Key takeaway:** shutdown is a **multi-phase coordinated protocol**, not a single command. Block new work, give existing work a chance to finish, request cancellation on timeout, verify termination, and only then close resources. When a timeout is not enough to stop a worker, report the incomplete state accurately and use an out-of-thread recovery strategy rather than closing resources early or claiming a safe stop.
