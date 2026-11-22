# Legacy thread control APIs and migrating to cooperative task cancellation

When upgrading a long-lived Java application, code using legacy thread control APIs often poses a greater risk than compilation errors. An application may still run yet suffer deadlocks, data loss, aborted transactions, or resource leaks when a thread is stopped at an arbitrary point. These issues commonly appear in background processing systems, queue-reading workers, schedulers, crawlers, desktop applications, and servers that began manually managing Threads many years ago.

Within the **Java Advance Compatibility Migration** topic, chapter **Legacy APIs and Tools**, this lesson explains why operations such as Thread.stop, Thread.suspend, and Thread.resume are no longer appropriate; how to replace them with **cooperative cancellation**, interrupts, stop signals, Future, ExecutorService, and bounded shutdown mechanisms; and how to keep data, resources, and operational contracts stable during migration.

The goal is not to replace every stop call with interrupt. The goal is to turn task termination into an **explicit protocol between the party requesting cancellation and the code executing the task**.

## 1. Distinguishing threads, tasks, and service lifecycle

Three concepts are very easily conflated:

- **Thread:** the execution unit scheduled by the JVM. A thread can be a platform thread or a virtual thread on Java releases that support them.
- **Task:** a unit of work such as processing an order, downloading a file, consuming a message, or syncing a batch.
- **Service/worker:** a component with a longer lifecycle that manages multiple tasks, threads, connections, and resources.

Stopping a task does not necessarily require terminating the thread running it. Conversely, stopping a thread does not guarantee that the task has completed cleanup or transaction rollback.

Example:

~~~text
Shutdown request
        |
        v
Stop accepting new work
        |
        v
Wait for running work to finish
        |
        +--> Timed out? ---> Request cancel / interrupt
        |                             |
        |                             v
        |                        Cleanup, rollback
        |                             |
        +-----------------------------+
        |
        v
Close connections, executor, resources
        |
        v
Report stopped
~~~

A safe shutdown mechanism must specify **when new work is rejected**, **how running work is handled**, **who requests cancellation**, **how the task receives and responds to cancellation**, and **when the service can be confirmed stopped**.

## 2. Legacy Thread control APIs and safety issues

### 2.1. Thread.stop

Historical code might contain:

~~~java
Thread worker = new Thread(() -> runBatch());
worker.start();

// Legacy code — do not use as a safe stop mechanism
worker.stop();
~~~

Thread.stop was deprecated because it is **unsafe**. Under the historical mechanism, an asynchronous stop operation could terminate a thread mid-work via an abnormal error, causing held monitors to be released while shared object state was still inconsistent.

Suppose a thread is updating two fields that must always stay consistent:

~~~java
synchronized (account) {
    account.debit(100);
    account.recordTransfer(transferId);
}
~~~

If the thread is stopped abruptly between the two operations, another thread may observe partially updated state. Releasing the monitor does not automatically recover the business state.

Possible consequences include:

- Object invariants are broken.
- Data being written to a file is left incomplete.
- A batch is falsely marked complete.
- A resource is not closed along the expected business flow.
- Transaction or protocol state becomes invalid.
- Other threads read half-updated state.

Depending on the JDK version, these legacy methods may have been disabled or behave differently from their original design; some calls may throw UnsupportedOperationException. **Do not rely on their continued presence in the API to conclude they are suitable for migration.**

### 2.2. Thread.suspend and Thread.resume

Legacy example:

~~~java
worker.suspend();
performMaintenance();
worker.resume();
~~~

Thread.suspend can pause a thread **while it is holding a monitor/lock**. If another thread—including the thread calling resume—needs that monitor to proceed, the system can deadlock.

Moreover, controlling an arbitrary thread externally cannot reliably determine whether the thread is at a business-level safe point. For pause/resume needs, design a cooperative pausing protocol rather than using the legacy suspend/resume methods.

### 2.3. ThreadGroup.stop and similar variants

Some legacy codebases stop an entire ThreadGroup using group-level thread control APIs. The risks of asynchronous termination remain, and are even harder to isolate because multiple threads are affected simultaneously.

Do not replace it by iterating over the ThreadGroup and calling Thread.stop on each thread. Transition to managing **task ownership**, executor lifecycles, and cancellation tokens.

### 2.4. Do not confuse with valid APIs

Thread.interrupt, Thread.join, Thread.sleep, and modern concurrency APIs do not belong to the same category as stop/suspend/resume. They serve different purposes. interrupt is typically a **signal requesting cooperative termination or waking a blocking operation**, not forcing execution to terminate.

## 3. Why is forced termination the wrong model?

Forced termination cannot answer the questions that business data requires:

1. Which operation is currently executing?
2. Can it stop immediately, or must it complete a unit of work?
3. Has the state been committed yet?
4. Must the message be returned to the queue or marked for retry?
5. Do network connections, files, streams, or transactions need to be closed?
6. Is another thread waiting for the result?
7. Who is responsible for confirming that the task has finished stopping?

A message processing example:

~~~text
Receive message
     |
     v
Read payload
     |
     v
Write to database
     |
     v
Commit transaction
     |
     v
Acknowledge to broker
~~~

If the thread is terminated right after writing to the database but before acknowledgement, the message may be redelivered. If the application lacks idempotency, data may be written twice. If it terminates before commit while having already acknowledged, the message may be lost.

Therefore, **cancellation semantics must align with business boundaries**: cancelling before starting, cancelling between units of work, rolling back an uncommitted unit, or requiring completion of the current unit before stopping.

## 4. What is cooperative cancellation?

Cooperative cancellation is a model in which:

- An authorized actor requests cancellation, such as a server, supervisor, or user.
- The cancellation request is communicated to the task via interrupt, state, or a cancellation token.
- The task periodically checks for the request at **safe points**.
- The task itself decides on cleanup, rollback, or completing indivisible work.
- The party requesting termination waits within a defined time limit.
- The termination outcome is recorded as completed, cancelled, timed out, or failed.

Key point: **cancellation is a protocol, not a kill-thread command**.

A simple protocol:

~~~text
RUNNING
   |
   | requestCancel()
   v
CANCELLING
   |
   +--> Check signal
   +--> Stop taking new work
   +--> Complete/roll back current unit
   +--> Close resources
   v
CANCELLED / STOPPED
~~~

Besides CANCELLED, a task can finish normally as COMPLETED or fail as FAILED. Some applications need to distinguish these termination types rather than lumping everything into “stopped”.

### 4.1. Two common signals

**Interrupt:** uses Thread's built-in mechanism, useful when a task is sleeping, waiting, joining, using BlockingQueue, or calling interruptible APIs.

**Stop flag:** uses volatile boolean or AtomicBoolean to express intent such as stopRequested; useful for CPU-bound loops or tasks that need to stop accepting new work at clear boundaries.

Both mechanisms can be combined. A flag conveys the service's intent, while interrupt wakes up a waiting thread.

## 5. Understanding Thread.interrupt properly

The call:

~~~java
worker.interrupt();
~~~

does not “kill” the worker. It issues an interruption signal. What happens next depends on the thread's state and the code inside.

- If the thread is running a normal CPU loop, it must check the interrupt status itself or call an equivalent checking method.
- If the thread is in certain interruptible wait operations, it may receive InterruptedException.
- If the thread is executing an I/O section or a library that does not support interruption, the request may not stop it immediately.
- If the task deliberately catches and ignores the interruption, the task may keep running.

### 5.1. isInterrupted and interrupted

The two APIs have an important difference:

~~~java
boolean flag = Thread.currentThread().isInterrupted();
~~~

isInterrupted **checks** the status without clearing the flag.

Meanwhile:

~~~java
boolean wasInterrupted = Thread.interrupted();
~~~

Thread.interrupted is a static method that checks the interrupt status of the **current thread** and **clears the flag** per the API semantics.

Do not use Thread.interrupted in a loop if it accidentally loses cancellation information that needs to propagate to other processing layers.

### 5.2. InterruptedException and restoring status

Many blocking APIs throw InterruptedException when a thread is interrupted. For many APIs, the interruption status is cleared when the exception is thrown. Therefore, if a method has no way to propagate InterruptedException to its caller, the common practice is to restore the flag:

~~~java
try {
    Thread.sleep(1000);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Restoring the flag allows upper calling layers to still recognize the interrupt request.

However, you do not always have to catch and restore immediately. If the method can declare throws InterruptedException, **propagating the exception upward** is usually cleaner:

~~~java
public void waitForWork() throws InterruptedException {
    Thread.sleep(1000);
}
~~~

The owner of the task will decide how to complete cancellation, perform cleanup, and report status.

## 6. Basic example: replacing Thread.stop with interrupt

Old dangerous code:

~~~java
Thread worker = new Thread(() -> {
    while (true) {
        performWork();
    }
});

worker.start();

// Legacy: should not be used
worker.stop();
~~~

Cooperative design:

~~~java
public final class PollingWorker implements Runnable {
    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                fetchAndProcessOneItem();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            closeOwnedResources();
        }
    }

    private void fetchAndProcessOneItem() throws InterruptedException {
        // For example, wait for an interval between polling rounds.
        Thread.sleep(200);
        // Process one unit of work, with appropriate stopping points.
    }

    private void closeOwnedResources() {
        // Clean up resources owned by the worker.
    }
}
~~~

Starting and requesting stop:

~~~java
Thread worker = new Thread(new PollingWorker(), "polling-worker");
worker.start();

// On shutdown:
worker.interrupt();
worker.join(5000);

if (worker.isAlive()) {
    System.err.println("Worker chưa dừng sau giới hạn chờ");
}
~~~

In the example, join(5000) is a timed wait, **not a command terminating the thread after five seconds**. If the worker is still alive, the caller must have a follow-up policy such as monitoring, closing appropriate resources, or reporting a shutdown error; do not fall back to Thread.stop.

### 6.1. When does the example need additions?

The snippet only illustrates interrupt and cleanup. In real applications:

- fetchAndProcessOneItem must truly be interruptible or check for cancellation at appropriate points.
- An uncommitted unit of work must roll back or support idempotency.
- closeOwnedResources needs to handle exceptions that may occur.
- The thread owner must control calls to start, interrupt, and join.
- If the caller also receives InterruptedException during join, the caller must execute its own cancellation policy.

## 7. Stopping CPU-bound loops

A computation loop does not call blocking APIs and therefore will not stop automatically just because an interrupt was sent.

Example:

~~~java
public long countMatches(long limit) {
    long matches = 0;

    for (long i = 0; i < limit; i++) {
        if ((i & 1023) == 0 &&
                Thread.currentThread().isInterrupted()) {
            break;
        }

        if (isMatch(i)) {
            matches++;
        }
    }

    return matches;
}
~~~

Here, the task checks for interrupt periodically rather than on every iteration. Checking frequency is a trade-off between overhead and cancellation latency.

However, returning an incomplete count result could be misinterpreted by the consumer as normal completion. If the contract requires distinguishing them, throw CancellationException, return a result carrying a partial/cancelled status, or separate the cancellation status from the result value.

Example with an exception:

~~~java
private static void checkCancelled() {
    if (Thread.currentThread().isInterrupted()) {
        throw new java.util.concurrent.CancellationException(
            "Computation was cancelled");
    }
}
~~~

Do not use CancellationException as a substitute for automatic rollback; this is only a way to signal an incomplete status.

## 8. Cancellation tokens with volatile or AtomicBoolean

Interrupt is a thread-level signal. When a job uses multiple helpers, or needs to express a service's own stop policy, a cancellation token is an appropriate choice.

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

public final class CancellationToken {
    private final AtomicBoolean cancelled = new AtomicBoolean();

    public void cancel() {
        cancelled.set(true);
    }

    public boolean isCancelled() {
        return cancelled.get();
    }
}
~~~

Task receiving the token:

~~~java
public void processBatch(
        java.util.List<String> items,
        CancellationToken token) {

    for (String item : items) {
        if (token.isCancelled()) {
            return;
        }
        processOne(item);
    }
}
~~~

AtomicBoolean provides visibility and atomic access suitable for flags. If there is only one writer and multiple readers, a volatile boolean can also suffice for simple stop intent.

### 8.1. Limitations of a standalone token

A stop flag does not automatically wake a thread that is sleeping or waiting indefinitely:

~~~java
while (!token.isCancelled()) {
    queue.take(); // May block forever if the queue has no data.
}
~~~

In that situation, you can combine:

- A stopRequested flag and Thread.interrupt.
- Polling with an acceptable timeout.
- A signal/sentinel message per the queue protocol.
- Closing the resource or signaling wait/condition if supported by the API.

Do not use continuous busy-waiting just to check a flag, as it can cause high CPU consumption.

## 9. BlockingQueue example: avoiding getting stuck during shutdown

BlockingQueue.take is an interruptible operation. A worker can be written as:

~~~java
import java.util.concurrent.BlockingQueue;

public final class QueueWorker implements Runnable {
    private final BlockingQueue<Runnable> queue;

    public QueueWorker(BlockingQueue<Runnable> queue) {
        this.queue = queue;
    }

    @Override
    public void run() {
        try {
            while (!Thread.currentThread().isInterrupted()) {
                Runnable job = queue.take();
                job.run();
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } finally {
            releaseWorkerResources();
        }
    }

    private void releaseWorkerResources() {
        // Clean up if the worker owns resources.
    }
}
~~~

When an interrupt is sent while queue.take is waiting, it can throw InterruptedException so the worker proceeds to cleanup.

However, if job.run() takes a long time and does not cooperate, the worker still will not stop on time. An interruptible queue **does not guarantee that every job in the queue is interruptible**.

### 9.1. Cancelling before taking a job vs. cancelling while running a job

Two policies should be separated:

- **Stop accepting:** Stop taking additional jobs from the queue.
- **Cancel in-flight:** Request the running job to stop at a safe point.

A service consuming messages from a broker may need to finish and acknowledge the running job before stopping consumption of new jobs. Immediate interruption is not always appropriate.

### 9.2. Poison pill is an option, not a cure-all

Some systems put a sentinel object in the queue to tell workers to exit the loop. You must clearly determine the worker count, sentinel count, bounded capacity, processing order, which producers remain active, and the possibility of a full queue.

A poison pill can be useful when the queue protocol is controlled; it does not replace handling timeouts, threads stuck in jobs, or incomplete transactions.

## 10. Stopping tasks managed by ExecutorService

When many tasks execute concurrently, manually storing a Thread list and calling interrupt on each thread is often complex and error-prone. ExecutorService helps separate the task concept from the thread running the task.

Example:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

ExecutorService executor = Executors.newFixedThreadPool(4);

Future<?> future = executor.submit(() -> {
    while (!Thread.currentThread().isInterrupted()) {
        doOneUnitOfWork();
    }
});
~~~

To request cancellation of a task:

~~~java
boolean accepted = future.cancel(true);
~~~

Key implications of cancel(true):

- The system attempts to cancel the task if it has not yet completed.
- If the task is running, it may interrupt the thread executing the task according to the Future policy.
- The task must still cooperate with interruption to stop promptly and clean up resources.
- The boolean result should not be interpreted as “all cleanup is finished”.

If the task is inside a native call, non-interruptible I/O, or code deliberately ignoring the flag, it may continue running for some time.

### 10.1. How is cancel(false) different?

cancel(false) requests cancellation without proactively interrupting the executing thread. This is useful when you do not want to directly affect a unit of work that has already started, though it also does not guarantee an already-running task will stop immediately.

The policy for using true or false must be based on idempotency, transaction boundaries, and interruptibility of the task.

### 10.2. After cancellation, how do you retrieve the result?

Future.get can throw CancellationException for a cancelled future. Other common errors include InterruptedException for the waiting thread and ExecutionException if the task failed.

Do not write code assuming a cancelled task will always return a complete result.

~~~java
try {
    future.get();
} catch (java.util.concurrent.CancellationException e) {
    System.out.println("Task đã được yêu cầu hủy");
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
} catch (java.util.concurrent.ExecutionException e) {
    System.err.println("Task thất bại: " + e.getCause());
}
~~~

If the caller needs to know that task cleanup has actually finished, use an appropriate synchronization mechanism or additional lifecycle state instead of inferring it solely from the future being marked cancelled.

## 11. Graceful shutdown: shutdown, awaitTermination, and shutdownNow

ExecutorService provides a lifecycle management API set:

| API | Meaning |
|---|---|
| shutdown() | Stops accepting new tasks; allows already-submitted tasks to continue processing |
| awaitTermination(timeout, unit) | Waits for the executor to terminate within a time limit |
| shutdownNow() | Attempts to stop running tasks via interruption and returns queued tasks that have not started |
| isShutdown() | The executor has received a shutdown request |
| isTerminated() | Tasks have finished following shutdown according to executor conditions |

A common sequence is:

1. Stop accepting new work.
2. Call shutdown.
3. Wait gracefully within a time limit.
4. If expired, request stronger cancellation with shutdownNow.
5. Wait again for a short timeout.
6. If still not stopped, record the status and follow operational policy.

Java example:

~~~java
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

public final class ShutdownSupport {
    public static void stopExecutor(ExecutorService executor) {
        executor.shutdown();

        try {
            if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
                List<Runnable> notStarted = executor.shutdownNow();

                System.err.println(
                    "Tasks chưa bắt đầu: " + notStarted.size());

                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    System.err.println(
                        "Một số task vẫn chưa hoàn tất sau yêu cầu hủy");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
    }
}
~~~

This snippet is an illustrative shutdown structure. The 20-second and 5-second timeouts are not universal recommendations; choose them according to SLAs, task duration, transactions, and system requirements.

### 11.1. shutdownNow is not Thread.stop

The name can be misleading. shutdownNow **attempts** to stop executing tasks, primarily via interruption in many ExecutorService implementations. There is no guarantee that uncooperative tasks will stop immediately.

When a task runs specialized network I/O or a loop that does not check interrupts, the executor may fail to reach the terminated state.

### 11.2. When to shutdown first, when to cancel first?

- For transactional services, typically prioritize rejecting new work and then draining in-flight work within a deadline.
- For a search task whose result can be discarded, you can cancel quickly when the user cancels.
- For long batches, design checkpoints to resume after restart.
- For critical operations requiring atomicity, complete/roll back the unit of work before confirming shutdown.

Do not apply a single generic stop logic to every kind of task without describing each group's obligations.

## 12. CompletableFuture and differences in cancellation

CompletableFuture supports cancel, yet **you should not assume cancel(true) will interrupt the thread running the supplier** the way FutureTask in ExecutorService does.

In the standard CompletableFuture implementation, the mayInterruptIfRunning parameter does not directly control interrupting an in-progress computation. Transitioning the future to cancelled state does not mean the executing lambda has stopped.

Example:

~~~java
java.util.concurrent.CompletableFuture<String> future =
    java.util.concurrent.CompletableFuture.supplyAsync(() -> {
        return slowOperation();
    });

future.cancel(true);
~~~

slowOperation can still continue running. If the application needs real work cancellation, you must design a cancellation token, task/executor ownership, or a corresponding interruption-capable mechanism.

With a CompletableFuture chain, also clarify whether cancellation propagates to upstream, downstream, and side effects. Do not treat the state of a single future as the state of the entire workflow.

## 13. I/O and operations that do not respond to interrupt immediately

Not all blocking operations have the same interruption semantics. Some APIs throw InterruptedException; some involve interruptible channels; some APIs or native libraries do not respond in time.

A task performing HTTP requests, database queries, or socket reads may additionally need:

- Connect timeout.
- Read/socket timeout.
- Request deadline.
- The client library's own cancel/close mechanism.
- Closing resources at the right time.
- Transaction timeout.
- Retry policy and idempotency.

Example with traditional sockets:

~~~java
try (java.net.Socket socket = new java.net.Socket()) {
    socket.connect(
        new java.net.InetSocketAddress("example.org", 443),
        3000
    );

    socket.setSoTimeout(5000);
    // Read data via socket.getInputStream() within appropriate bounds.
}
~~~

connect timeout and read timeout serve different purposes. Apply protocol/client-level timeouts suited to the business logic rather than treating them as direct replacements for interruption.

### 13.1. Closing resources can help unblock

With some APIs, closing a socket, channel, or stream from a thread with proper ownership can wake up a blocked operation. However, exact behavior depends on the API and provider; verify it with integration tests.

Do not resort to Thread.stop because an I/O library lacks interrupt support. Look at the library's own cancel/timeout APIs or isolate the task in a controllable process if requirements are very strict.

### 13.2. One end-to-end deadline matters more than many isolated timeouts

If a request traverses three services, setting 30 seconds for each wait can push the entire flow past SLA. Design an overall deadline and pass remaining time down to each operation.

A cancellation token can carry a deadline or be paired with a deadline checker. This lets a task decline starting a new step when the time budget is no longer sufficient.

## 14. Preserving invariants, transactions, and cleanup

The hardest part of cooperative cancellation is choosing safe stopping boundaries. You must decide whether a task can stop immediately or must finish a transaction or unit of work first.

Example:

~~~java
public void processOrder(Order order)
        throws InterruptedException {

    checkInterrupted();

    // Start a unit of work with clear transaction boundaries.
    try {
        reserveInventory(order);
        createPaymentIntent(order);
        commitOrder(order);
    } catch (RuntimeException e) {
        compensateIfNecessary(order);
        throw e;
    }

    checkInterrupted();
}
~~~

The example is workflow pseudocode; the methods reserveInventory, createPaymentIntent, commitOrder, and compensateIfNecessary must be properly designed around the database/external service. In distributed systems, compensation is not the same as an automatic transaction rollback.

### 14.1. Do not check cancellation at points that break invariants

If a transaction must complete two operations as one atomic unit, checking in between the two steps can produce half-finished state. Define safe points before/after the transaction or ensure rollback works if cancellation happens mid-way.

### 14.2. finally and try-with-resources

Place cleanup in finally or try-with-resources where appropriate:

~~~java
public void handleFile(java.nio.file.Path path)
        throws java.io.IOException {

    try (java.io.InputStream input =
            java.nio.file.Files.newInputStream(path)) {
        // Process input.
    }
}
~~~

In cancellable tasks, code must ensure resources are closed even when InterruptedException or CancellationException occurs. If cleanup performs blocking operations, have a clear policy on timeouts and interrupt status to avoid hanging indefinitely during shutdown.

### 14.3. Do not swallow interruption during cleanup

If you catch InterruptedException and merely log and continue the whole loop, the thread loses the cancellation signal.

Error-prone code:

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException e) {
    System.err.println("Ignored");
}
~~~

Better handling:

~~~java
try {
    Thread.sleep(500);
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

If the method can propagate InterruptedException, declare throws and let the owner handle it at the appropriate higher level.

## 15. Locks, waits, and synchronization conditions

Not every lock-waiting situation is equally interruptible.

### 15.1. Synchronized monitors

When a thread is **waiting to acquire a monitor to enter synchronized**, an interrupt does not necessarily make it exit that monitor wait immediately.

Therefore, replacing Thread.stop with interrupt in a deadlocked locking design will not solve the problem by itself. You must fix lock ordering, shrink critical sections, or switch to primitives with interruptible waiting where appropriate.

### 15.2. ReentrantLock.lockInterruptibly

java.util.concurrent.locks.ReentrantLock provides a way to wait for a lock that responds to interrupts:

~~~java
import java.util.concurrent.locks.ReentrantLock;

public final class InventoryGuard {
    private final ReentrantLock lock = new ReentrantLock();

    public void update() throws InterruptedException {
        lock.lockInterruptibly();
        try {
            performCriticalUpdate();
        } finally {
            lock.unlock();
        }
    }

    private void performCriticalUpdate() {
        // Update data inside the critical section.
    }
}
~~~

If the thread is interrupted while waiting on lockInterruptibly, it can receive InterruptedException instead of waiting forever. Note: once the lock is held, the code must still preserve invariants and unlock in finally.

### 15.3. Condition.await, Object.wait, and Thread.join

Interruptible wait methods typically throw InterruptedException. Even so, the waiting thread must have proper loop conditions and appropriate wake-up code.

With Condition:

~~~java
lock.lockInterruptibly();
try {
    while (!ready && !cancelled) {
        condition.await();
    }
} finally {
    lock.unlock();
}
~~~

ready, cancelled, and condition are state belonging to the same synchronization mechanism in the example. Checking the condition in a while loop is important because a condition wait can wake up before the condition is met.

## 16. Cooperative pause/resume instead of Thread.suspend/resume

Some business scenarios genuinely need to pause and resume tasks: rate throttling, pausing a crawler, pausing message consumption, or phased maintenance.

A safe model can be a state machine:

~~~text
RUNNING ----requestPause----> PAUSING
   ^                            |
   |                            | reaches safe point
   |                            v
   +-----requestResume------- PAUSED
   |
   +-----resume/start-----------+

RUNNING / PAUSED ----requestStop----> STOPPING --> STOPPED
~~~

The thread transitions itself to PAUSED **after leaving critical sections and completing a safe unit of work**, rather than being halted by the JVM at an arbitrary instruction.

One implementation can use Lock + Condition or a semaphore. Pay special attention to:

- All state reads/writes must be synchronized or have visibility guarantees.
- requestStop must wake workers currently PAUSED as well.
- Do not wait on a Condition while holding other business locks that could cause deadlock.
- Resume must not lose a stop signal.
- Pause may require a timeout/acknowledgement so the caller knows the worker has actually stopped at a safe point.
- When interruption occurs, prioritize the stop policy instead of returning to PAUSED indefinitely.

The core point is **task-level pause/resume**, not asynchronous Thread-level suspend/resume.

## 17. Virtual threads and structured concurrency

In modern JDKs, virtual threads allow deploying many blocking tasks in a thread-per-task model with lower overhead across many workloads. However, they **do not change the principles of cooperative cancellation**.

Java 21 example:

~~~java
Thread worker = Thread.startVirtualThread(() -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            doInterruptibleWork();
        }
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
    } finally {
        cleanup();
    }
});
~~~

Virtual threads also need cleanup, timeouts, termination contracts, and responsiveness to interruption. Do not use Thread.stop for either virtual threads or platform threads.

### 17.1. Structured concurrency

Structured concurrency is an approach to organizing child tasks within a scope so that lifetimes and cancellation are managed together with the parent task. Some JDKs provide the StructuredTaskScope API in preview status or evolving across releases.

Because the API and syntax can change between JDK versions, do not mechanically copy preview code across versions. Before using it, confirm the feature status and documentation for the **exact target JDK**. What matters about the model is:

- The parent task owns the child tasks.
- When the scope ends, the lifecycle of child tasks is explicitly handled.
- Failure/cancellation of one task can trigger a policy to stop related tasks.
- No orphaned child tasks are left running after the caller finishes.

These principles remain useful even if a project does not yet use a specific structured concurrency API.

## 18. Two-phase service shutdown: drain then cancel

A server system usually cannot halt all work the moment it receives SIGTERM or a shutdown request. Time must be given for requests that have already entered the system.

A practical shutdown policy:

~~~text
SHUTDOWN_REQUESTED
        |
        v
Mark service not ready
        |
        v
Stop accepting new requests/jobs
        |
        v
Drain in-flight within grace period
        |
     +--+------+
     |         |
  Complete   Timeout
     |         |
     |         v
     |     Interrupt/cancel
     |         |
     |      Cleanup
     +----+----+
          |
          v
Close resources
          |
          v
STOPPED / TIMEOUT_REPORTED
~~~

You should define:

- Overall grace period.
- Per-task timeout.
- Separate database/network timeouts.
- When to turn off readiness while still serving in-flight work.
- Who handles unfinished requests/jobs.
- Requeue/retry policy.
- Container orchestration/service manager deadline.
- How the final result is reported to operators.

If the server runs under an orchestrator such as Kubernetes, the JVM shutdown duration must fit the platform's termination grace period; otherwise, the JVM may be killed by the supervisor before graceful shutdown completes.

### 18.1. Rejecting new work after the shutdown signal

A common race:

~~~text
Thread A: requestShutdown()
Thread B: submitNewTask()
Thread A: awaitTermination()
~~~

If state transitions are not synchronized, new tasks can slip in after shutdown has begun. ExecutorService rejects submissions after shutdown by contract; at the application layer, ensure queue consumers, HTTP handlers, and schedulers also stop accepting/enqueuing new work at the right time.

## 19. Cancellation mechanisms by task category

No single stopping solution fits every type of work.

| Task category | Safe point / cancellation response | Commonly useful tools |
|---|---|---|
| Purely CPU-bound | Periodic flag/interrupt checks | isInterrupted, cancellation token |
| Queue waiting | Wake on interrupt, or timed poll | BlockingQueue.take/poll |
| Thread.sleep/wait/join | InterruptedException | interrupt and propagate/restore |
| Database processing | Transaction boundaries, timeouts, rollback | Transaction timeout, driver cancellation API |
| HTTP/network | I/O timeout, cancel request, close resource | Client-specific timeout/cancel |
| File processing | Checkpoints between chunks, cleanup | try-with-resources, token |
| Batch ETL | Checkpoints between records/batches, idempotency | Token, job state, retry |
| Scheduler | Stop new scheduling, drain current tasks | ScheduledExecutorService shutdown policy |
| Plugin | close/cancel contract, lifecycle callbacks | SPI cancellation contract |
| Native/uninterruptible call | External timeout, process isolation if needed | Process boundary, watchdog |

The table only outlines design directions. The interrupt responsiveness of each API must be verified via documentation and integration tests on the target JDK/dependencies.

## 20. Migrating each legacy code pattern

### 20.1. From direct stop()

**Before:**

~~~java
worker.stop();
~~~

**After:** assign worker ownership to a component with requestStop, set a stop flag or send an interrupt, and wait for the worker to confirm shutdown at a safe point. Avoid letting arbitrary classes throughout the application call interrupt on threads they do not own.

### 20.2. From suspend()/resume()

**Before:**

~~~java
worker.suspend();
worker.resume();
~~~

**After:** create PAUSE_REQUESTED/PAUSED states and a condition. The worker pauses only when not holding critical locks and can clean up/acknowledge. requestStop must wake up paused workers.

### 20.3. From an infinite while(true) loop

**Before:**

~~~java
while (true) {
    work();
}
~~~

**After:**

~~~java
while (!stopRequested.get() &&
       !Thread.currentThread().isInterrupted()) {
    workOneUnit();
}
~~~

Also update workOneUnit if it contains blocking calls or holds a transaction open for too long.

### 20.4. From manually managing hundreds of Threads

**Before:** manually calling new Thread, maintaining lists, interrupting each thread, joining manually, and struggling to control resources.

**After:** use ExecutorService or an appropriate task scope model, defining owners and shutdown policies. Thread counts, queue capacity, and retries should be designed for the workload, rather than assuming “more threads means faster”.

### 20.5. From CompletableFuture.cancel assuming it stops the lambda

**Before:** calling cancel(true) and treating the supplier as stopped.

**After:** design a token or manage the Future of the actual executing task; inspect side effects and cleanup, not just the CompletableFuture state.

## 21. Common migration mistakes

### “Replacing Thread.stop with Thread.interrupt is enough”

False. interrupt is only meaningful when the task receives the signal, exits a blocking operation, or checks a flag. An uncooperative task may continue running.

### “InterruptedException is an ordinary error, just log it”

False in many worker loops. If you swallow the exception without propagating status/cancellation, code may continue running against shutdown requests.

### “Future.cancel(true) means the task has finished cleanup”

False. You must distinguish the future state, the interruption attempt, and the task's actual lifecycle.

### “shutdownNow will kill every thread”

False. It attempts to request cancellation, typically via interruption, and some tasks may not respond.

### “Thread.suspend is safe as long as resume follows”

False. The thread may hold a lock when suspended; the resuming code may deadlock or never get to execute.

### “Use daemon threads so shutdown is unnecessary”

Daemon threads do not guarantee completing work or cleanup before the JVM exits. They do not replace resource lifecycle management.

### “Closing a socket is always equivalent to interrupt”

Not all I/O and libraries behave the same way. Check API contracts, timeouts, and resource ownership.

### “Thread.interrupted only checks status”

False. This static method checks and then clears the interrupt status of the current thread. If you only want to observe it, usually use isInterrupted.

### “A cancelled task has no external side effects”

False. Database operations, HTTP calls, or message publishes may already have committed before cancellation was processed. That is why idempotency, compensation, or clear state protocols are necessary.

## 22. Migration workflow for codebases with legacy Thread APIs

### Step 1 — Scope the code and ownership

Search for usages:

~~~bash
rg -n "Thread[.]stop|[.]stop\(\)|[.]suspend\(\)|[.]resume\(\)" src
~~~

The result is only a text search and may mix in stop methods of other classes or miss binary dependencies. Check the actual classes of objects, generated source, and third-party libraries.

Record which component creates the thread, who owns it, and who has authority to request stopping.

### Step 2 — Classify work and safe points

For each worker, identify:

- CPU loop or blocking?
- Does the work involve transactions?
- Can it cancel mid-way, or must it finish a unit?
- Is requeuing or checkpointing needed?
- Is a caller waiting for results?
- What are the timeout and SLA?
- Which shared state and locks must be preserved?

### Step 3 — Design the cancellation protocol

Choose interrupt, cancellation tokens, queue signals, or the corresponding library's cancel API. Clearly separate:

- stop accepting new work;
- cancel pending tasks;
- cancel running tasks;
- wait for cleanup;
- report final state.

### Step 4 — Implement cleanup and error handling

Add finally/try-with-resources, timeouts, transaction handling, exception propagation, and sufficient logging to see which tasks were cancelled.

Do not merely rename methods while keeping vague semantics. Update the service's API such as requestShutdown, awaitStopped, or cancelJob to express intent clearly.

### Step 5 — Replace the thread management mechanism

Where appropriate, migrate to ExecutorService, lifecycle-aware task schedulers, or the target JDK's task scope model. Do not rewrite the entire architecture before understanding ownership and resource limits.

### Step 6 — Test cancellation

Create scenarios:

- Cancelling before the task starts.
- Cancelling during computation.
- Cancelling while waiting on a queue.
- Cancelling during a network/database wait.
- Cancelling while holding a lock or near a transaction boundary.
- Cancelling concurrently with completion.
- Cancelling multiple times.
- Shutting down while new tasks are being submitted.
- Cleanup throwing an exception.
- Caller waiting on the result also being interrupted.

Verify data state after cancellation as well, not just that thread.isAlive becomes false.

### Step 7 — Run on the target JDK and environment

Verify behavior on the actual JDK, frameworks, drivers, containers, executors, and classloaders being deployed. Different JDKs may have improvements in thread scheduling or interruptibility of certain APIs; do not extrapolate from results on another Java version.

### Step 8 — Monitor after deployment

Monitor:

- Actual shutdown duration.
- Number of cancelled, failed, or unfinished tasks.
- Resource leaks and thread leaks.
- Queue backlog.
- Frequency of timeouts and retries.
- Deadlocked/blocked threads.
- Rate of data needing recovery or requeuing.
- Tasks failing to meet cancellation deadlines.

## 23. Shutdown decision document template

~~~text
SERVICE / WORKER
  Service name:
  Thread/task owner:
  Runtime JDK:
  Executor/thread model:
  Queue or scheduler:

LEGACY API
  Thread.stop / suspend / resume usage:
  Source location:
  Trigger:
  Reason for historical design:

WORK CONTRACT
  Unit of work:
  Safe cancellation points:
  Transaction boundary:
  Idempotency/retry policy:
  External side effects:

CANCELLATION PROTOCOL
  Who requests cancellation:
  Interrupt / token / queue signal:
  Stop accepting policy:
  In-flight drain policy:
  Pending task policy:
  Timeout / deadline:

CLEANUP
  Owned resources:
  Rollback/compensation:
  Logging and metrics:
  Failure on cleanup:

VALIDATION
  Cancellation before start:
  Cancellation during blocking:
  CPU-bound cancellation:
  Race with completion:
  Repeated shutdown:
  Thread/resource leak:
  Deployment shutdown:
  Rollback plan:
~~~

A good record must let operators know whether **the stop request was sent**, **the tasks actually finished**, or **the deadline expired with work still unfinished**. These three states are not interchangeable.

## 24. Summary

Moving from legacy thread control APIs to cooperative task cancellation is not a minor syntax change. It replaces the mechanism of “asynchronously interfering with a thread” with an intentional protocol for managing work and resources.

The most important principles:

1. **Do not use Thread.stop, suspend, or resume for business control.** They do not allow tasks to preserve invariants and can create deadlocks or inconsistent state.
2. **Interrupt is a request, not a thread-kill command.** Tasks must respond via check points or interruptible blocking APIs.
3. **Stop signals must pair with safe points.** Define when rollback is allowed, when units of work finish, and when resources close.
4. **Manage tasks with clear ownership.** Use Future, ExecutorService, tokens, queue protocols, or task scopes where appropriate.
5. **Graceful first, bounded escalation second.** Stop accepting work, drain, request cancellation, wait for cleanup, and report errors on timeout.
6. **Protect data and operations.** Test transactions, idempotency, race conditions, thread/resource leaks, and shutdown duration on the actual runtime.
7. **Do not equate cancelled status with a stopped task.** Observe actual outcomes and cleanup.

A well-migrated Java system can request task cancellation without needing to know which exact instruction a thread is executing. The task itself participates in termination, preserves the correctness of shared state, and provides clear evidence of whether it completed, was cancelled, or could not stop within the deadline.
