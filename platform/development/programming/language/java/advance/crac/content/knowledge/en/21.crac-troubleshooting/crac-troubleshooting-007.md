# Detecting Hung Callbacks and Deadlocks When Pausing Resources

In Java applications using CRaC (Coordinated Restore at Checkpoint), resources such as connection pools, HTTP clients, schedulers, message consumers, and worker threads often need to be prepared before the JVM creates a checkpoint. CRaC invokes `beforeCheckpoint` callbacks so the application can bring these resources to a safe state; after the process is restored, `afterRestore` callbacks help recreate or activate the resources.

A hung callback can prevent the entire checkpoint request from completing. A deadlock while stopping workers can cause a callback to wait indefinitely while a worker waits for a lock held by the callback. A dangerous case is when the application logs only "checkpoint started" with no completion log, and the process still exists yet can neither continue serving traffic nor complete the checkpoint.

To diagnose accurately, you need to distinguish **slow callbacks**, **callbacks waiting on resources**, **thread pools failing to drain**, **lock contention**, and **actual deadlocks**. An effective approach is to log per callback, set finite deadlines, avoid holding locks while waiting for tasks to finish, capture thread dumps when signs of hanging appear, and inspect lock state using `ThreadMXBean`.

## 1. Callback Lifecycle and Where Hangs Can Occur

A CRaC resource implementing the `org.crac.Resource` interface has two main callbacks:

- `beforeCheckpoint(Context<? extends Resource> context)`: prepares the resource before the JVM is checkpointed.
- `afterRestore(Context<? extends Resource> context)`: restores or recreates the resource after the JVM is restored.

Example:

~~~java
import org.crac.Context;
import org.crac.Core;
import org.crac.Resource;

public final class ExampleResource implements Resource {

    public ExampleResource() {
        Core.getGlobalContext().register(this);
    }

    @Override
    public void beforeCheckpoint(
            Context<? extends Resource> context) throws Exception {
        // Pause and close the resource.
    }

    @Override
    public void afterRestore(
            Context<? extends Resource> context) throws Exception {
        // Recreate or reconnect the resource.
    }
}
~~~

Callbacks execute on the checkpoint/restore handling flow. If a callback waits indefinitely, the process cannot complete the corresponding lifecycle phase. Simply having a live JVM PID does not prove the checkpoint is making progress.

### 1.1. Common Places Where beforeCheckpoint Gets Stuck

The following operations can cause long waits or deadlocks:

- Waiting on `ExecutorService.awaitTermination()` while a task needs a lock held by the callback.
- Calling `Future.get()` or `CompletableFuture.join()` to wait for work scheduled on the very executor that was just shut down.
- Calling `lock()` or entering `synchronized` while another thread holds the lock and is waiting on the callback.
- Waiting for the active task count to reach 0 while tasks are blocked on a database, socket, or message broker.
- Closing a connection pool while workers still hold connections or transactions.
- Waiting on an HTTP request/handshake without a connect timeout or read timeout.
- Invoking another resource's callback in reverse order relative to dependencies.
- Using a latch/condition but forgetting to signal in exception or cancellation branches.

### 1.2. Common Places Where afterRestore Gets Stuck

After restore, a callback can hang when:

- Waiting on a database or external service without a timeout.
- Waiting for a secret/config provider response.
- Recreating an executor while worker startup waits on a lock held by another thread.
- Waiting on a `Future` that can only be completed by a scheduler that has not been resumed yet.
- Starting an HTTP server while the port is already occupied by another process.
- Opening resources in the wrong order so that dependencies are not yet operational.
- Waiting for readiness or startup state to be updated by a thread that is no longer running.

Not every slow callback is a deadlock. For example, a database starting up may make reconnection take time while still making progress. Diagnosis requires observing stack traces and state changes across multiple thread dumps.

## 2. Recognizing Hung Callbacks via Logs and Duration

Each callback should log at least three milestones:

1. Callback start.
2. Start and end of each significant step inside the callback.
3. Callback completion along with duration.

Also record the resource name, phase, thread name, and checkpoint/restore operation ID if the system has a correlation ID.

Example:

~~~text
2026-11-13T07:10:00.010Z INFO  CRaC phase=beforeCheckpoint resource=job-gate event=start thread=main
2026-11-13T07:10:00.012Z INFO  CRaC phase=beforeCheckpoint resource=job-gate step=stop-admission
2026-11-13T07:10:00.015Z INFO  CRaC phase=beforeCheckpoint resource=job-gate step=await-active-tasks active=3
2026-11-13T07:10:20.015Z ERROR CRaC phase=beforeCheckpoint resource=job-gate event=timeout active=1 elapsedMs=20000
~~~

If logs show only `event=start` without `event=complete`, determine which step the callback is waiting at. Per-step logging helps narrow the scope before taking thread dumps.

### 2.1. Measuring Duration with System.nanoTime()

Use a monotonic clock to measure elapsed time within the process:

~~~java
long started = System.nanoTime();

try {
    resource.pause();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    logger.info(
            "CRaC callback resource={} elapsedMs={}",
            resourceName,
            elapsedNanos / 1_000_000);
}
~~~

`System.nanoTime()` is suitable for measuring duration because measurements are not skewed by system clock adjustments. Do not use `System.currentTimeMillis()` to check timeouts inside callbacks.

Note: the `finally` block only executes when the call returns or throws an exception. If the callback is stuck indefinitely, the completion log in `finally` will never appear. Therefore, you need start logs, step-by-step logs, and an external watchdog or thread monitoring tool.

### 2.2. Setting a Deadline for the Entire Callback

Do not just set individual timeouts per step while forgetting to bound total duration. For example, if a callback has three steps, each with a 20-second timeout, total time can reach 60 seconds. Pass a deadline or remaining budget across steps to ensure total duration stays within operational limits.

With timeouts using `nanoTime`, you can check elapsed time using subtraction:

~~~java
long started = System.nanoTime();
long budgetNanos = TimeUnit.SECONDS.toNanos(20);

// Before each potentially blocking step:
long elapsed = System.nanoTime() - started;
long remaining = budgetNanos - elapsed;

if (remaining <= 0) {
    throw new TimeoutException("Checkpoint preparation deadline exceeded");
}
~~~

Do not add the timeout to `started` and compare `nanoTime()` against that sum. Using subtraction helps avoid overflow bugs when computing deadlines.

## 3. Deadlock When a Callback Holds a Lock While Waiting for Workers

This is a common mistake when stopping an executor.

Suppose a callback uses a monitor to protect scheduler state:

~~~java
public synchronized void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    executor.shutdown();
    executor.awaitTermination(30, TimeUnit.SECONDS);
}
~~~

A running worker might need the same monitor to update state when it finishes:

~~~java
public synchronized void onTaskFinished() {
    activeTasks--;
    notifyAll();
}
~~~

What happens:

~~~text
Callback thread                          Worker thread
---------------                          -------------
Holds monitor
executor.shutdown()
awaitTermination()
  │
  │ waits for worker to finish
  │                                        Completes business work
  │                                        Calls onTaskFinished()
  │                                        Waits for monitor
  └────────────────────────────────────────┘
                 DEADLOCK
~~~

The callback holds the monitor while waiting for the executor to terminate. The worker needs the monitor to complete and return its thread to the pool. Both wait on each other, so no progress is made.

### 3.1. Principles to Fix

- Hold locks only for brief state updates.
- Set the flag to stop accepting new tasks inside the lock.
- Release the lock before waiting for active tasks to drain.
- Workers must have an exit path that always decrements the active count in `finally`.
- Wait with a timeout; do not use unbounded `awaitTermination()`.
- Do not close dependencies that workers still need before the workers finish.

Do not call `awaitTermination`, `Future.get`, `join`, or long-running I/O operations inside a `synchronized` block or while holding a lifecycle lock.

## 4. Using an Admission Gate and Condition to Drain Tasks Safely

A gate prevents new tasks from entering business logic and counts currently running tasks. `Condition.awaitNanos()` automatically releases the lock while waiting, allowing workers to acquire the lock to decrement the active count.

Example:

~~~java
package com.example.lifecycle;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class JobGate {

    private final ReentrantLock lock = new ReentrantLock();
    private final Condition drained = lock.newCondition();

    private boolean accepting = true;
    private int activeTasks;

    public boolean enter() {
        lock.lock();
        try {
            if (!accepting) {
                return false;
            }

            activeTasks++;
            return true;
        } finally {
            lock.unlock();
        }
    }

    public void exit() {
        lock.lock();
        try {
            if (activeTasks <= 0) {
                throw new IllegalStateException(
                        "No active task to exit");
            }

            activeTasks--;

            if (activeTasks == 0) {
                drained.signalAll();
            }
        } finally {
            lock.unlock();
        }
    }

    public void pauseAndAwait(Duration timeout)
            throws InterruptedException, TimeoutException {

        long budgetNanos = timeout.toNanos();

        if (budgetNanos <= 0) {
            throw new IllegalArgumentException(
                    "timeout must be positive");
        }

        long started = System.nanoTime();

        lock.lockInterruptibly();
        try {
            accepting = false;

            while (activeTasks > 0) {
                long elapsed = System.nanoTime() - started;
                long remaining = budgetNanos - elapsed;

                if (remaining <= 0) {
                    accepting = true;
                    drained.signalAll();

                    throw new TimeoutException(
                            "Active jobs did not drain before checkpoint");
                }

                drained.awaitNanos(remaining);
            }
        } catch (InterruptedException interrupted) {
            accepting = true;
            drained.signalAll();
            Thread.currentThread().interrupt();
            throw interrupted;
        } finally {
            lock.unlock();
        }
    }

    public void resume() {
        lock.lock();
        try {
            accepting = true;
            drained.signalAll();
        } finally {
            lock.unlock();
        }
    }

    public int activeTasks() {
        lock.lock();
        try {
            return activeTasks;
        } finally {
            lock.unlock();
        }
    }
}
~~~

`pauseAndAwait()` sets `accepting=false` before waiting. Because `enter()` checks the flag and increments the active count under the same lock, no new task can slip in between those two operations. While `awaitNanos()` waits, the lock is released so workers can call `exit()`.

If time expires, the gate is reopened before throwing `TimeoutException`. This matters when a checkpoint is rejected and the application continues running normally. In real applications, dedicated states such as `PAUSING`, `PAUSED`, and `RESUMING` may be needed to coordinate more complex multi-component flows.

### 4.1. Wrapping Tasks with try/finally

Every task accepted by the gate must call `exit()` exactly once:

~~~java
public void runScheduledJob() {
    if (!jobGate.enter()) {
        return;
    }

    try {
        reconciliationService.run();
    } finally {
        jobGate.exit();
    }
}
~~~

Do not call `exit()` on the branch where `enter()` returns false. Do not call `enter()` multiple times for the same task if there is only one `exit()`. If a task splits into child tasks, each child task must be managed separately or the parent must wait for children to complete before exiting.

## 5. Separating Stopping the Scheduler from Waiting for Task Completion

Stopping scheduling and draining tasks are two separate actions. A common procedure:

1. Close the admission gate.
2. Cancel or pause future schedules so no new tasks are enqueued.
3. Call graceful shutdown on the executor.
4. Wait for active tasks to finish within the deadline.
5. If tasks remain, capture a thread dump and fail the checkpoint.
6. Close databases/clients needed by tasks only after the tasks have finished.

Example with `ExecutorService`:

~~~java
executor.shutdown();

if (!executor.awaitTermination(20, TimeUnit.SECONDS)) {
    List<Runnable> queued = executor.shutdownNow();

    logger.warn(
            "Executor did not terminate; queuedTasks={}",
            queued.size());

    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new TimeoutException(
                "Background executor is still running");
    }
}
~~~

This snippet illustrates bounded shutdown. `shutdownNow()` only requests interruption of running tasks and returns tasks that have not started; it does not guarantee that threads have stopped. Tasks must respect interrupts and all I/O must have timeouts.

If tasks must finish before checkpoint, do not treat `shutdownNow()` as proof of a successful drain. If tasks cannot stop safely, reject the checkpoint and let the application continue running or handle it according to recovery policy.

### 5.1. Avoiding Waiting on Futures Executed on a Stopped Executor

Another mistake:

~~~java
executor.shutdown();
future.get();
~~~

If `future` represents a task that has not yet run or whose completion callback is scheduled on the same executor that was just shut down, `get()` may wait forever.

Before waiting on a future, verify that the task was submitted and has an active execution path. Use a timeout with `get(timeout, unit)`. If the task is canceled, handle `CancellationException`; if waiting is interrupted, preserve the interrupt status and exit the callback according to policy.

## 6. Setting Timeouts for Locks and I/O

A callback can hang because of unbounded locks or I/O. Turn every potentially blocking operation into one with a deadline.

### 6.1. Using tryLock Instead of Unbounded Lock When Appropriate

~~~java
if (!resourceLock.tryLock(5, TimeUnit.SECONDS)) {
    throw new TimeoutException(
            "Could not acquire resource lock before checkpoint");
}

try {
    prepareResource();
} finally {
    resourceLock.unlock();
}
~~~

`tryLock` with a timeout helps the callback report a clear error when a resource is held too long by another thread. When the lock cannot be acquired, identify which owner thread holds it and why; do not retry indefinitely in the callback.

### 6.2. Timeouts for Network and Database

Closing a client or waiting for a server response can hang if socket timeouts are not configured.

You should check the corresponding timeout types:

- Connection timeout.
- Socket/read timeout.
- Request/response timeout.
- Database query timeout.
- Transaction timeout.
- Pool acquisition timeout.
- Broker acknowledgement/close timeout.

Do not only configure timeouts on the HTTP client while forgetting timeouts on DNS, TLS handshake, database drivers, or broker clients. Property names and semantics depend on the specific library.

### 6.3. Do Not Perform Deferrable Work in beforeCheckpoint

`beforeCheckpoint` should focus on bringing resources into a checkpointable state:

- Stop accepting new work.
- Drain running tasks.
- Commit/roll back transactions.
- Close connections/sockets.
- Stop threads or timers that must be recreated.

Tasks such as loading large caches, calling reinitialization APIs, refreshing secrets, or opening new connections should generally be done in `afterRestore`. Moving the right operations to the right phase reduces checkpoint duration and limits lock contention.

## 7. Callback Ordering and Dependency Deadlocks

CRaC manages callbacks according to resource registration order within the same context: `beforeCheckpoint` is invoked in reverse order, while `afterRestore` is invoked in registration order. You can use this behavior to order dependencies.

Suppose a worker depends on a database pool:

- The database must be created before the worker after restore.
- The worker must be stopped before the database before checkpoint.

You can register the database first and the worker second:

~~~text
Registration:
1. DatabaseResource
2. WorkerResource

beforeCheckpoint (reverse order):
1. WorkerResource stops and drains
2. DatabaseResource closes pool

afterRestore (registration order):
1. DatabaseResource creates new pool
2. WorkerResource resumes
~~~

If WorkerResource's callback directly calls `databaseResource.close()` while DatabaseResource also has its own callback, it may close twice or create unclear ordering. Each resource should have a single lifecycle owner; the coordinator only orchestrates dependencies and admission state.

In nested contexts or frameworks that auto-register resources, verify the actual ordering of the CRaC version in use. Do not infer a global ordering between two resources located in different contexts.

## 8. Structured Callback Logging and Duration Measurement

A small wrapper gives all callbacks a uniform log format:

~~~java
package com.example.lifecycle;

import java.util.concurrent.TimeUnit;
import org.slf4j.Logger;

public final class CallbackTiming {

    private CallbackTiming() {
    }

    public static void run(
            Logger logger,
            String phase,
            String resource,
            CheckedAction action) throws Exception {

        long started = System.nanoTime();

        logger.info(
                "CRaC callback start phase={} resource={} thread={}",
                phase,
                resource,
                Thread.currentThread().getName());

        try {
            action.run();
        } catch (Exception failure) {
            long elapsed = System.nanoTime() - started;

            logger.error(
                    "CRaC callback failed phase={} resource={} elapsedMs={}",
                    phase,
                    resource,
                    TimeUnit.NANOSECONDS.toMillis(elapsed),
                    failure);

            throw failure;
        }

        long elapsed = System.nanoTime() - started;

        logger.info(
                "CRaC callback complete phase={} resource={} elapsedMs={}",
                phase,
                resource,
                TimeUnit.NANOSECONDS.toMillis(elapsed));
    }

    @FunctionalInterface
    public interface CheckedAction {
        void run() throws Exception;
    }
}
~~~

Usage:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    CallbackTiming.run(
            logger,
            "beforeCheckpoint",
            "job-gate",
            () -> jobGate.pauseAndAwait(Duration.ofSeconds(20)));
}
~~~

If a callback hangs, the `start` log still appears while `complete` does not. You can add logs for each substep, active task count, lock acquisition duration, and dependency wait time.

Do not log secrets, connection strings, or business payloads in callback diagnostics.

## 9. Detecting Deadlocks with ThreadMXBean

Java provides `ThreadMXBean` to observe threads and detect certain types of deadlocks.

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockDetector {

    private DeadlockDetector() {
    }

    public static void dumpDeadlockedThreads() {
        ThreadMXBean bean =
                ManagementFactory.getThreadMXBean();

        long[] ids = bean.findDeadlockedThreads();

        if (ids == null || ids.length == 0) {
            System.out.println("No monitor/ownable-synchronizer deadlock detected");
            return;
        }

        ThreadInfo[] infos =
                bean.getThreadInfo(ids, true, true);

        for (ThreadInfo info : infos) {
            if (info != null) {
                System.err.println(info);
            }
        }
    }
}
~~~

`findDeadlockedThreads()` finds deadlocks involving monitors and ownable synchronizers observable by the JVM. A `null` result does not prove the application is not hung.

It does not detect every kind of logical wait, for example:

- A thread waiting on a `CountDownLatch` where no thread calls `countDown()`.
- `Future.get()` waiting on a task that is no longer scheduled.
- A callback waiting on an unresponsive external service.
- Two components waiting on each other via messages or database state.
- A thread waiting on a socket read without a timeout.

Therefore, combine ThreadMXBean with thread dumps, callback logs, and executor status.

### 9.1. Monitoring Thread Count and Status

You can log the following information from `ThreadMXBean`:

~~~java
ThreadMXBean bean =
        ManagementFactory.getThreadMXBean();

logger.info(
        "threadCount={} peakThreadCount={} daemonThreadCount={}",
        bean.getThreadCount(),
        bean.getPeakThreadCount(),
        bean.getDaemonThreadCount());
~~~

If you can retrieve `ThreadInfo` for all threads, log threads with name prefixes such as `crac-`, `scheduler-`, `worker-`, and `http-`. Standardized thread names help identify which pool is stuck.

Do not continuously dump full stack traces on every probe. Collect them only when a callback exceeds its threshold or when an alert fires.

## 10. Capturing Thread Dumps When Checkpoint Makes No Progress

When logs show a callback started but did not complete, capture multiple thread dumps a few seconds apart to compare.

### 10.1. Using jcmd

On Linux, if the attach API is still functional and permissions allow:

~~~bash
jcmd <PID> Thread.print -l
~~~

Depending on the JDK, you can use:

~~~bash
jstack -l <PID>
~~~

`-l` requests printing additional lock information, including monitors and ownable synchronizers. Run as a user with permission to attach to the JVM and in the right PID namespace.

If the checkpoint command is waiting on a callback, you can try capturing a thread dump from another terminal. However, attach may be unavailable under certain JVM states, containers, or security profiles.

### 10.2. Using SIGQUIT on Linux

If attach does not work yet the process still receives signals:

~~~bash
kill -3 <PID>
~~~

On HotSpot, SIGQUIT typically causes the JVM to print a thread dump to the process's stdout/stderr. Ensure container logs are collected so the output is not lost.

Do not send SIGKILL to "try freeing" the callback. SIGKILL terminates the process immediately and prevents callback cleanup or rollback.

### 10.3. Capturing Multiple Dumps

A single thread dump may show a thread in `WAITING` or `TIMED_WAITING`, which is not enough to conclude a deadlock. Capture two or three dumps a few seconds apart:

- If the stack and lock owner do not change, the thread may be stuck.
- If the thread advances to the next step, the callback is still making progress.
- If the same thread repeatedly waits on the same monitor and the owner thread makes no progress either, check for a lock cycle.
- If the thread is waiting on a socket read, check timeouts and network/service state.
- If the thread is waiting on `awaitTermination`, inspect worker threads and the executor queue.

A useful Linux command to observe threads at the OS level:

~~~bash
ps -L -p <PID> -o pid,tid,stat,pcpu,comm,wchan:32
~~~

`wchan` can help identify where a thread is sleeping in the kernel, though it does not replace a Java stack trace. A thread with low CPU does not mean a deadlock; it may be legitimately waiting on I/O.

### 10.4. Using a Timeout on the Checkpoint Command

You can bound the wait time of the client invoking checkpoint:

~~~bash
timeout --signal=TERM 60s jcmd <PID> JDK.checkpoint
~~~

The `timeout` command bounds the runtime of the `jcmd` client process. It **does not guarantee canceling the callback or rolling back the checkpoint operation inside the JVM** when the client terminates. If the command expires, check the process status and capture a thread dump before deciding the next action.

## 11. Reading Thread Dumps to Identify Failure Types

Some common indicators:

| Indicator in dump | Possible meaning | What to check |
|---|---|---|
| `BLOCKED` and `waiting to lock` | Thread is waiting for a monitor | Which thread owns the monitor, lock ordering |
| `Found one Java-level deadlock` | JVM detected a monitor/ownable-synchronizer cycle | Stacks and lock owners of threads in the cycle |
| `WAITING` at `CountDownLatch.await` | Waiting for a signal | Who is supposed to call `countDown`, whether exception branches missed signaling |
| `TIMED_WAITING` at `awaitTermination` | Callback waiting on executor | Whether workers are still active, whether they wait for a lock held by the callback |
| `FutureTask.get` or `CompletableFuture.join` | Waiting for an async result | Whether the task is executed, whether the executor was shut down |
| `SocketDispatcher.read` or socket read | Waiting on I/O | Read timeouts, remote service, DNS/TLS |
| `Object.wait` | Waiting on a monitor/condition | Exit condition and signaling thread |
| `LockSupport.park` | Thread is parked | Lock, condition, future, or synchronizer being awaited |

A callback can hang without a deadlock cycle. For example, a single thread waiting indefinitely on an external API. In that case, `findDeadlockedThreads()` may return `null`; the thread dump still shows the stack waiting on I/O.

## 12. Handling Callback Timeouts and Rolling Back State

If `beforeCheckpoint` cannot stop resources within the allowed time, the callback should fail so checkpoint does not proceed in an unsafe state. However, before throwing an exception, the application must check which state was modified and whether it can be rolled back.

For example:

- Admission gate closed, yet workers did not drain.
- Scheduler paused, yet executor did not shut down.
- One pool closed, yet other pools did not close.
- Readiness switched to `REFUSING_TRAFFIC`.
- A listener stopped accepting requests.

If the checkpoint is rejected and the process keeps running, paused components must be resumed or restored according to policy. Do not let the application keep running while the gate remains closed or readiness remains false indefinitely.

Handling pattern:

~~~java
@Override
public void beforeCheckpoint(
        Context<? extends Resource> context) throws Exception {

    readiness.refusingTraffic();
    jobGate.pauseAdmission();

    try {
        jobGate.awaitDrained(Duration.ofSeconds(20));
        scheduler.pause();
        closeResourcesForCheckpoint();

    } catch (Exception failure) {
        scheduler.resumeIfPaused();
        jobGate.resume();
        readiness.acceptingTraffic();

        throw failure;
    }
}
~~~

This is a skeleton. In real applications, not every resource can be safely reopened after closing. You must accurately track completed steps and roll back in reverse order. If a closed resource cannot recover, you may need to fail the process or transition to a controlled recovery path instead of advertising readiness.

### 12.1. afterRestore Failure

If `afterRestore` cannot reconnect to dependencies:

- Keep readiness at `REFUSING_TRAFFIC`.
- Do not resume workers that depend on an unready resource.
- Log the phase, resource, and exception.
- Perform bounded retries if the error may be transient.
- Use startup/liveness policies suited to self-recovery capabilities.
- Mark Ready only after all required dependencies are operational.

Do not swallow exceptions and make the process appear to have restored successfully. If recovery cannot continue, let orchestration handle it according to designed policy, such as restarting or cold-starting from a valid artifact.

## 13. Avoiding Deadlocks Across Multiple Resource Callbacks

When there are multiple resources, deadlocks can emerge due to inconsistent lock ordering.

Example:

~~~text
Resource A callback:
  holds lock A
  calls B.close()
  waits for lock B

Resource B worker:
  holds lock B
  calls A.update()
  waits for lock A
~~~

This is lock-order inversion. Two components acquire locks in different orders.

Countermeasures:

- Design a global lock ordering and follow it across all code paths.
- Avoid having one resource's callback directly invoke another resource's lifecycle methods.
- Use a coordinator to manage dependency ordering.
- Do not hold locks when calling external code or waiting on an executor.
- Separate state transitions from opening/closing resource operations.
- When possible, use `tryLock` with a timeout and log owner/phase.
- Avoid concurrent callbacks closing the same resource.

If resource A depends on B, use the appropriate CRaC registration order instead of nesting manual close/open calls. Ensure only one owner drives each resource's lifecycle.

## 14. Observing Callback Progress with a Watchdog

A watchdog can detect callbacks exceeding thresholds. There are two implementation approaches:

- An internal watchdog records callback start time and alerts if the callback has not finished.
- An external supervisor monitors logs/metrics/processes and collects thread dumps upon timeout.

For actual checkpoints, an external watchdog is often useful because it does not depend on an executor the application is preparing to stop. However, ensure the watchdog has permission to access the process and logs.

A status record might include:

~~~text
checkpointOperationId=cp-2026-11-13-001
phase=beforeCheckpoint
resource=database-pool
startedAt=2026-11-13T07:10:00Z
elapsedMs=12000
thread=main
status=RUNNING
step=await-pool-drain
activeConnections=2
~~~

Suggested metrics:

| Metric | Meaning |
|---|---|
| `crac_callback_duration_seconds` | Callback duration by phase/resource |
| `crac_callback_in_progress` | Whether a callback is currently running |
| `crac_callback_timeouts_total` | Number of callbacks exceeding deadline |
| `crac_active_workers` | Number of active worker tasks |
| `crac_executor_termination_seconds` | Executor termination time |
| `crac_lock_wait_seconds` | Lifecycle lock wait duration |
| `crac_checkpoint_failures_total` | Number of checkpoint failures |
| `crac_restore_callback_failures_total` | Number of callback failures after restore |

Use bounded-cardinality labels such as resource name and phase. Do not attach unbounded request IDs or checkpoint IDs as metric labels; those values belong in logs or traces.

## 15. Controlled Testing of Slow Callbacks and Deadlocks

Do not wait until production to discover hung callbacks. You can test the lifecycle using mock resources and synchronization controls.

### 15.1. Testing Callback Timeouts

Use `CountDownLatch` to simulate an unfinished worker:

~~~java
CountDownLatch releaseWorker = new CountDownLatch(1);

executor.submit(() -> {
    try {
        releaseWorker.await();
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    }
});

assertThrows(
        TimeoutException.class,
        () -> gate.pauseAndAwait(Duration.ofMillis(100)));
~~~

After the test, always release the latch and shut down the executor in `finally` so the test does not leave background threads behind.

### 15.2. Testing Normal Worker Completion

1. Let the worker enter the gate.
2. Call pause from another thread.
3. Verify new tasks are rejected.
4. Call `exit()` for the running worker.
5. Verify pause completes.
6. Verify active count equals 0.
7. Call resume and verify new tasks can enter.

### 15.3. Testing Lock Inversion

Create two test threads with two locks and use latches to control lock acquisition order. Confirm that the detector or thread dump shows the wait cycle. The test must have timeouts and cleanup so it does not hang the test suite.

Do not introduce intentional deadlocks into production environments. The goal is to prove the detection and timeout mechanisms work.

### 15.4. Testing on a Real CRaC Runtime

Unit tests only verify gate and lock logic. Add integration tests with a real JDK/CRaC engine to confirm:

- `beforeCheckpoint` is actually invoked.
- Exceptions/timeouts in callbacks cause the checkpoint request to fail according to runtime semantics.
- The process can continue or roll back after a checkpoint failure.
- `afterRestore` executes in the right resource order.
- Threads/executors are recreated properly.
- Logs and thread dumps can be collected in the container environment.

`simengine` is useful for testing callback flow, yet does not replace CRIU checkpoint/restore testing on Linux. Run integration tests with the exact JDK vendor/build, CRIU, kernel, container runtime, and security context planned for deployment.

## 16. Runbook When Checkpoint Hangs

When a checkpoint command does not complete, handle it in the following sequence:

1. Record the PID, start time, checkpoint command, and checkpoint operation ID.
2. Identify the last callback with a `start` log but no `complete` log.
3. Inspect the resource and the last recorded step.
4. Capture a thread dump using `jcmd Thread.print -l`, `jstack -l`, or SIGQUIT if attach is unavailable.
5. Capture one or two more dumps a few seconds later to determine whether stacks are making progress.
6. Check lock owners, active workers, executor queues, and I/O timeouts.
7. Use `ThreadMXBean.findDeadlockedThreads()` if the JVM still allows calling management APIs.
8. If the callback has a deadline, wait for the controlled timeout and let the checkpoint request fail safely.
9. After failure, confirm that gates, schedulers, pools, and readiness have been rolled back or resumed.
10. Retry checkpoint only after the root cause is identified and the application state is stable.

Do not delete a checkpoint directory currently being written or restored by the engine. Do not send SIGKILL merely because a callback is slow. If the process cannot self-recover, collect logs and dumps before deciding to restart per the application's runbook.

## 17. Quick Diagnosis Table

| Symptom | Likely cause | Evidence to collect | Resolution |
|---|---|---|---|
| Callback logs start without complete | Callback is waiting or blocked | Thread dumps and step logs | Identify wait point, set timeout |
| Callback waiting on `awaitTermination` | Workers have not stopped | Worker thread dumps and executor state | Release lock, check tasks and interrupts |
| Thread `BLOCKED` on monitor | Lock contention or deadlock | Lock owner and stack chain | Fix lock ordering, shrink critical section |
| `findDeadlockedThreads()` returns null yet callback hangs | Waiting on I/O, latch, or future | Stack traces and dependency state | Add proper timeouts/signals/cancellations |
| Active task count does not decrease | Worker failed to call exit or has not finished | Enter/exit logs, thread dumps | Put exit in finally and handle cancellation |
| Callback timeout, checkpoint fails | Drain did not finish within budget | Active count, task state | Increase budget with justification or fix stuck tasks |
| Checkpoint fails yet application receives no traffic | Gate/readiness not rolled back | Availability state and resource state | Resume in order, do not publish false Ready |
| afterRestore hangs during reconnect | Dependency or network not ready | Client logs, timeouts, thread dumps | Bounded retries, keep readiness false |
| Multiple callbacks closing same resource | Unclear lifecycle owner | Callback start/end per resource | Choose a single owner and coordinate order |
| Hangs only on one node | Differences in kernel/runtime/permissions | Node fingerprint and CRIU logs | Compare environments and test on exact node |

## 18. Design Principles for Hang-Free Callbacks

An operable CRaC callback should adhere to these principles:

1. **Log start and completion:** record phase, resource, thread, and elapsed time.
2. **Have an overall deadline:** never let a callback wait indefinitely.
3. **Do not hold locks while waiting:** release locks before `awaitTermination`, `Future.get`, I/O, or condition waits.
4. **Drain in order:** stop admission, stop scheduling, drain tasks, and only then close dependencies.
5. **Tasks have exit paths:** use `finally` to decrement active counts and handle interrupts.
6. **I/O has timeouts:** databases, sockets, brokers, and secret providers must have appropriate timeouts.
7. **Clear lifecycle owner:** do not allow two callbacks to close/open the same resource.
8. **Intentional rollback:** if checkpoint is rejected, restore paused/closed components when possible.
9. **Diagnostic tooling:** thread dumps, ThreadMXBean, executor metrics, and callback timing.
10. **Test failure paths:** test slow tasks, lock contention, interrupts, timeouts, and restore callback failures.

When a callback hangs, start from the last callback with a `start` log, determine what the thread is waiting on using thread dumps, and trace the lock owner or unresponsive dependency. Deadlocks must be fixed in lock ordering and thread coordination; slow callbacks need deadlines and timeouts for blocking operations; non-draining tasks need an admission gate and safe termination mechanisms. Merely increasing timeouts or restarting the JVM may mask symptoms without solving the root cause.

## 19. References

- [CRaC: Implementing the CRaC API](https://crac.org/use/implement-crac/): registering resources and implementing before-checkpoint/after-restore callbacks.
- [Java ThreadMXBean API](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ThreadMXBean.html): monitoring threads and detecting observable deadlocks.
- [jcmd tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): sending diagnostic commands to a running JVM.
- [jstack tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jstack.html): capturing thread stack traces and lock information.
- [ExecutorService API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): shutdown, awaitTermination, and managing executor lifecycle.
- [ReentrantLock API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): timed lock acquisition and condition waiting.

