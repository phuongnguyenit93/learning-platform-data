# Timeouts, Cancellation, and Deadlock Avoidance in Callbacks

In CRaC, the `beforeCheckpoint` and `afterRestore` callbacks run at sensitive points in the process lifecycle. The `beforeCheckpoint` callback must bring the application and its resources into a safe state so the JVM can create a checkpoint. The `afterRestore` callback must restore or verify the required resources before the application resumes serving work.

If a callback waits indefinitely for a thread, a lock, a database query, or an external service, the entire checkpoint/restore operation can hang. If a callback holds a lock while waiting for a task that also needs that lock, the application can fall into a deadlock. Therefore, callbacks need **bounded timeouts, controlled cancellation mechanisms, and clear locking rules**.

## 1. Why Can Callbacks Cause Checkpoint or Restore to Hang?

CRaC callbacks often have to coordinate multiple concurrently active components: request threads, worker threads, schedulers, connection pools, caches, files, and external services. These components may be holding locks or waiting on each other.

Some common scenarios:

- `beforeCheckpoint` waits for an in-flight request to finish, but that request is hung on an HTTP call without a read timeout.
- A callback calls `Future.get()` or `Thread.join()` without a time limit, causing the callback to wait forever when the background task does not complete.
- A callback acquires a lock currently held by a worker, while the worker waits for a signal that only the callback can emit.
- A callback holds `synchronized` or `ReentrantLock` and waits for another task; that task needs the very lock being held in order to finish.
- Two Resources invoke callbacks in a mutually dependent way and acquire multiple locks in different orders, forming a wait cycle.
- `afterRestore` reconnects to a database or message broker, but the client has no connect/read timeout, preventing the process from reaching readiness.

Callbacks should not assume that every thread and dependency will finish quickly. An operation that is normal while the application runs continuously can become a critical blocking point during the checkpoint or restore phase.

## 2. Distinguishing Timeout, Cancellation, and Interruption

These three concepts are related, but not identical:

| Concept | Meaning | Example |
| --- | --- | --- |
| Timeout | A time limit on waiting for a condition or operation. When it expires, the code detects that the operation has not completed. | Wait for an in-flight request for at most 20 seconds. |
| Cancellation | A request for a task to stop or to no longer produce a result. The task must support a cancellation mechanism to terminate safely. | Call `future.cancel(true)` after the wait timeout expires. |
| Interruption | A cooperative signal via the thread's interrupt flag to notify the thread that it should stop waiting or cancel its work. | `CountDownLatch.await()` throws `InterruptedException` when the thread is interrupted. |

A timeout does not automatically stop a task. For example, `future.get(5, TimeUnit.SECONDS)` throws `TimeoutException` after five seconds, but the submitted task may still continue running. To request that the task stop, the application must actively cancel it, and the task must respond to cancellation/interruption.

Similarly, `future.cancel(true)` does not forcibly terminate a running thread. The `true` parameter requests interrupting the executing thread if the task has already started; code inside the task must check for interruption or call APIs capable of responding to interruption. Interruption should not be treated as a safe thread-killing mechanism.

## 3. Setting a Deadline for the Entire Callback

You should not grant a fresh, full timeout to each step while forgetting the total callback duration. If a callback has five operations and each waits up to 30 seconds, the total time can exceed two minutes.

You should define an overall deadline using `System.nanoTime()` and pass the remaining time to each operation:

```java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(30);

long remainingNanos = deadline - System.nanoTime();
if (remainingNanos <= 0) {
    throw new TimeoutException("Checkpoint preparation deadline exceeded");
}

// Use remainingNanos for the next wait.
```

`System.nanoTime()` is suitable for measuring elapsed time because it does not depend on system clock adjustments. Do not use `System.currentTimeMillis()` to compute deadlines for short wait intervals that require accuracy.

Example of a 30-second budget:

| Work | Illustrative budget |
| --- | ---: |
| Stop accepting new work and wait for in-flight requests to complete | 18 seconds |
| Flush data or complete transactions | 5 seconds |
| Close or release external resources | 4 seconds |
| Buffer for handling and logging | 3 seconds |

This is only an example. Actual timeouts must be based on SLAs, the allowed checkpoint duration, dependency characteristics, and the amount of in-flight work. Sub-operations must use the remaining time from the overall deadline, avoiding stacking multiple independent timeouts.

Separate budgets should be set for `beforeCheckpoint` and `afterRestore`. Restore may need time to reconnect to services or rebuild pools; that time must stay within the startup/readiness limits allowed by the deployment system.

## 4. Stopping New Work and Draining In-Flight Work

Before closing resources, the application must prevent new requests from entering code paths that need those resources. Only then should the callback wait for the in-flight work count to drop to 0.

A typical sequence:

1. Transition the component to the `PREPARING` or `QUIESCING` state.
2. Reject, pause, or redirect new work according to the application's policy.
3. Wait for in-flight requests/tasks to complete within a bounded period.
4. If the time expires, request cancellation of the remaining tasks according to the defined policy.
5. Only when the state is safe, flush data and close/pause resources.
6. If a safe state cannot be reached, report an error so the checkpoint is rejected instead of continuing with resources in an indeterminate state.

The callback example below illustrates the processing structure. The methods `stopAcceptingNewWork`, `awaitInFlight`, `flushAndCloseResources`, and `rollbackPreparation` are application-specific logic; they must implement deadlines and cancellation appropriate for each resource type.

```java
import org.crac.Context;
import org.crac.Resource;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class ManagedResource implements Resource {

    @Override
    public void beforeCheckpoint(Context<? extends Resource> context) throws Exception {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(25);

        try {
            stopAcceptingNewWork();

            if (!awaitInFlight(remaining(deadline))) {
                throw new TimeoutException("In-flight work did not drain in time");
            }

            flushAndCloseResources(remaining(deadline));
        } catch (InterruptedException e) {
            // Preserve the interrupt status so the upper caller can detect it.
            Thread.currentThread().interrupt();
            rollbackPreparation();
            throw e;
        } catch (Exception e) {
            rollbackPreparation();
            throw e;
        }
    }

    @Override
    public void afterRestore(Context<? extends Resource> context) throws Exception {
        reconnectResources(Duration.ofSeconds(15));
        resumeAcceptingNewWork();
    }

    private void stopAcceptingNewWork() { /* application-specific */ }
    private boolean awaitInFlight(Duration timeout) throws InterruptedException {
        return true; // Replace with a bounded drain implementation.
    }
    private void flushAndCloseResources(Duration timeout) throws Exception { /* application-specific */ }
    private void rollbackPreparation() { /* application-specific and safe to repeat */ }
    private void reconnectResources(Duration timeout) throws Exception { /* application-specific */ }
    private void resumeAcceptingNewWork() { /* application-specific */ }

    private Duration remaining(long deadline) throws TimeoutException {
        long nanos = deadline - System.nanoTime();
        if (nanos <= 0) {
            throw new TimeoutException("Checkpoint preparation deadline exceeded");
        }
        return Duration.ofNanos(nanos);
    }
}
```

In real code, sub-operations must share the overall deadline instead of each helper consuming its own full timeout. The example above also assumes `rollbackPreparation()` can return the component to a safe operating state after preparation fails. If resources have already been partially closed, rollback must reopen them or mark the component not ready; do not re-enable accepting requests merely because the callback has exited.

## 5. Cancelling Running Tasks Properly

### With Future

If a callback waits on a task via `Future`, use the `get` overload with a timeout and request cancellation when it expires:

```java
try {
    future.get(5, TimeUnit.SECONDS);
} catch (TimeoutException e) {
    future.cancel(true);
    throw e;
}
```

The task needs to support interruption:

```java
void processWork() throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        processNextItem();
    }
}
```

If the task is performing an I/O operation that does not respond to interruption, configure a timeout on the client itself or close the resource via its API to unblock the waiting operation. Cancellation is only a request; track whether the task has actually terminated.

### With ExecutorService

`shutdown()` prevents accepting new tasks but allows already-submitted tasks to continue running. `awaitTermination(timeout, unit)` waits within the time limit. If the timeout expires, `shutdownNow()` requests interrupting running tasks and returns tasks that have not started; it does not guarantee that all running tasks have stopped.

```java
executor.shutdown();

if (!executor.awaitTermination(10, TimeUnit.SECONDS)) {
    List<Runnable> neverStarted = executor.shutdownNow();
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        throw new TimeoutException("Executor did not stop");
    }
}
```

The snippet above only illustrates the wait/cancel mechanism. In a CRaC application, you must determine whether the executor can be recreated after restore. An `ExecutorService` that has been shut down cannot transition back to an active state; if it needs to continue being used, design the creation of a new executor in the appropriate lifecycle phase.

### With I/O and Databases

Do not rely solely on interruption to stop all I/O operations. Configure timeouts at the appropriate layer:

- HTTP client: connect timeout, response/read timeout, and overall request timeout.
- JDBC: query timeout, network/socket timeout, and a statement cancellation mechanism appropriate for the driver.
- Message broker: timeout when publishing/acknowledging, message processing deadline, and a re-verification mechanism on retry.
- Self-managed sockets: read/write timeouts and closing the socket when the cancellation policy requires it.
- Files or native calls: use time-bounded APIs if available; if an API cannot be safely cancelled, avoid calling it inside the callback or switch to a controllable design.

A client's timeout only bounds one kind of wait. For example, a connect timeout does not necessarily bound the response read time. You must identify exactly which APIs can block and configure the corresponding timeouts properly.

## 6. Avoiding Deadlocks When Using Locks in Callbacks

Deadlocks occur when threads hold resources that other threads need, forming an unresolvable wait cycle.

### Scenario 1: Callback holds a lock and waits for a worker

```text
Callback thread                    Worker thread
---------------                    -------------
lock.acquire()
wait for worker  ----------------> needs same lock
                                   cannot continue
callback waits forever
```

The callback holds the lock while waiting for the worker. The worker needs the lock to complete, so neither can make progress.

**How to handle:** do not hold application locks while waiting on a `Future`, latch, thread, or I/O. Acquire the lock only for a short state-update section, release the lock, and then wait for other tasks.

### Scenario 2: Two callbacks acquire locks in opposite order

```text
Callback A                         Callback B
----------                         ----------
holds lock A                       holds lock B
waits for lock B                   waits for lock A
```

If two callbacks or two components acquire multiple locks in different orders, they can create a deadlock. If multiple locks must be used, define a global ordering and follow it in all code paths. Even better, consolidate state changes into a single coordinator to reduce the number of locks that need coordination.

### Scenario 3: Waiting for a task on the same executor running the callback

If a callback runs on an executor with a finite number of workers and then submits a new task to that same executor and waits for it, the pool may have no free workers left. The new task never runs, while the callback waits for that task's result.

**How to handle:** do not synchronously wait for tasks submitted to an executor that may already be saturated or is running the callback. Perform the required work directly in the callback, use a separate executor with controlled capacity, or design a drain step before requesting the checkpoint.

## 7. Safe Locking Rules

- Do not use `synchronized` or unbounded `lock()` for resources that another thread may hold for a long time.
- With `ReentrantLock`, prefer `tryLock(timeout, unit)` when you need to wait for a lock; if the lock cannot be acquired within the timeout, report an error and handle rollback.
- Do not hold a lock while calling network, database, `Future.get`, `Thread.join`, `CountDownLatch.await`, or `ExecutorService.awaitTermination`.
- Do not call a business method from a callback if that method may acquire locks in a different order from normal threads.
- Use a consistent lock ordering if multiple locks must be acquired.
- Keep critical sections short, protecting only state transitions or data structure updates.
- Do not wait on a thread that itself needs the callback to complete before it can continue.
- Record lock wait times and the lock-holding thread when investigating incidents.

Example of acquiring a lock with a timeout:

```java
if (!lock.tryLock(2, TimeUnit.SECONDS)) {
    throw new TimeoutException("Could not acquire lifecycle lock");
}

try {
    updateLifecycleState();
} finally {
    lock.unlock();
}
```

This snippet holds the lock only while updating the state. If you need to wait for workers to drain, do so after releasing the lock.

## 8. Do Not Rely on Callback Order to Resolve Dependencies

An application may register multiple `Resource` instances: database pool, message consumer, scheduler, cache, and HTTP client. You should not create implicit dependencies where Resource A assumes Resource B has completed its callback simply because B was registered before or after it.

If resources require a specific preparation order, express that order in a single lifecycle coordinator or an application-owned orchestration mechanism. The coordinator can stop accepting work, drain workers, flush data, and then close resources in the defined order.

Avoid having A's callback directly invoke B's callback. This can lead to callbacks running twice, hard-to-control ordering dependencies, or deadlocks caused by the same resource being controlled from multiple places. Each resource should have a clear lifecycle owner.

## 9. Error Handling and Rollback When a Callback Does Not Complete

If a callback times out or is interrupted, do not ignore the error and let the checkpoint proceed while the resource is only partially prepared. Report the error so the checkpoint operation is rejected according to the runtime's semantics.

There is an important point: `afterRestore` is a callback for a successful restore phase. Do not rely on `afterRestore` to undo what `beforeCheckpoint` did if the checkpoint is aborted. If a callback closes a connection and then times out in the next step, the preparation logic itself or a coordinator must have a way to return the application to a safe state.

When there are multiple Resources, you should also not assume the runtime will automatically invoke a general rollback callback for all previously prepared Resources if another Resource fails. Design a preparation process that can roll back explicitly, or group related operations into a coordinator that can accurately track which parts have completed.

A useful state model:

```text
RUNNING
   |
   v
PREPARING
   |
   +---- error/timeout/interruption ----> ROLLING_BACK
   |                                      |
   |                                      v
   |                                  RUNNING or FAILED
   |
   v
QUIESCED
   |
   v
CHECKPOINTING
   |
   v
RESTORING
   |
   v
RECONNECTING
   |
   v
READY
```

If rollback cannot recover the resource, transition the component to `FAILED` or `NOT_READY`, keep traffic out, and emit an operational signal. Do not reset to `RUNNING` merely to avoid having the callback report an error.

## 10. Handling Interruption Properly

Blocking APIs such as `Future.get`, `CountDownLatch.await`, `Thread.join`, and `ReentrantLock.lockInterruptibly` can throw `InterruptedException`. When catching this exception, the callback should:

1. Stop the waiting operation safely.
2. Perform any necessary rollback for the preparation steps already completed.
3. Restore the interrupt flag using `Thread.currentThread().interrupt()` if `InterruptedException` was caught and the interruption is not being translated into another protocol.
4. Rethrow the exception to the CRaC layer so checkpoint/restore knows the callback did not complete.

Do not write:

```java
try {
    latch.await();
} catch (InterruptedException ignored) {
    // Continue as if completed.
}
```

This snippet swallows the cancellation signal and can cause the callback to continue in an unsafe state.

A more proper handling approach:

```java
try {
    if (!latch.await(10, TimeUnit.SECONDS)) {
        throw new TimeoutException("Workers did not stop");
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw e;
}
```

If the callback needs to roll back before throwing the exception, perform the rollback inside `catch` and only then restore the interrupt flag and rethrow. Rollback itself must also have a time limit or an exit mechanism when dependencies do not respond.

## 11. Orchestration-Layer Timeouts Do Not Replace In-Callback Timeouts

Deployment scripts or tools may set a timeout when waiting for a checkpoint command, but an external caller's timeout does not guarantee that the operation inside the JVM has been safely cancelled. For example, stopping a waiting `jcmd` process does not mean the JVM has definitely cancelled the checkpoint.

Therefore, distinguish between:

- **Callback deadline:** the time limit that callback code allows a preparation or recovery step to run.
- **JVM/CRaC operation timeout:** the time limit of the checkpoint/restore operation according to the runtime and deployment setup.
- **Orchestration timeout:** the time limit a script, job, or deployment controller waits for the result.

An orchestration timeout is useful for detecting operations that exceed the operational window, but after it expires you must check the JVM state, CRaC/CRIU logs, and the checkpoint directory before retrying. Do not send a second checkpoint command or delete an image currently being written without knowing whether the first operation has finished.

## 12. Observing and Testing Time-Bounded Callbacks

Each Resource should record the following information:

- Resource name/identifier and checkpoint attempt id.
- Callback start and end timestamps, and total duration.
- Number of in-flight requests or tasks when draining started.
- Lock wait time and the associated lock type, if any.
- Dependency being called and configured timeout.
- Number of cancelled tasks, number of tasks still running after cancellation, and timeout reason.
- Rollback or reconnect outcome.

Do not log credentials, tokens, or sensitive data in callback logs. Logs should be sufficient to identify the hung step without exposing data held in resources.

Test scenarios should include:

1. Workers complete normally before the deadline.
2. Workers run past the deadline and the callback requests cancellation.
3. Workers ignore interruption to verify that the system detects tasks that have not stopped.
4. A lock is held by another thread longer than the timeout.
5. Two components risk acquiring locks in opposite order.
6. An HTTP/database dependency does not respond.
7. The callback is interrupted while waiting.
8. One preparation step succeeds, but the next step fails, requiring rollback.
9. Restore succeeds, but reconnecting a dependency exceeds the deadline.
10. The application does not accept traffic until all critical resources are ready.

Tests should run with the actual JDK/CRaC and deployment environment. Unit tests for timeout helpers and state machines are useful, but they do not replace integrated checkpoint/restore testing.

## 13. Callback Design Checklist

- [ ] Every callback has a clear overall deadline.
- [ ] Every blocking operation has a defined timeout or exit mechanism.
- [ ] Sub-timeouts use the remaining time from the overall deadline.
- [ ] The application stops accepting new work before draining in-flight work.
- [ ] Tasks have a cooperative cancellation/interruption mechanism.
- [ ] I/O, database, and HTTP clients have timeouts at the appropriate layers.
- [ ] Locks are not held while waiting on workers, Futures, or network calls.
- [ ] Tasks are not awaited on an executor that may already be saturated or is running the callback.
- [ ] Lock ordering is consistent and there are no wait cycles between Resources.
- [ ] Timeouts or interruptions cause the checkpoint to be rejected if resources are not yet safe.
- [ ] Explicit rollback is implemented; do not rely on `afterRestore` to undo an aborted checkpoint.
- [ ] After restore, traffic is only enabled once resources have reconnected and readiness is achieved.
- [ ] Duration, timeouts, cancellations, and errors are logged per Resource.
- [ ] Timeout, potential deadlock, interruption, and slow-dependency cases have been tested.

## 14. Conclusion

CRaC callbacks must finish within a controlled period and leave resources in a deterministic state. Stopping new work, draining in-flight work, using an overall deadline, setting timeouts at the appropriate I/O layers, and cancelling tasks cooperatively help prevent callbacks from waiting indefinitely. Avoid holding locks while waiting on other tasks, enforce consistent lock ordering, and manage rollback when a checkpoint is aborted to avoid deadlocks or leaving the application in a half-finished state.

After restore, reconnect dependencies within the allowed time limit and bring the application to ready only once critical resources are operational. When timeouts, cancellation, and state transitions are clearly designed, callbacks become an observable and controllable part of the checkpoint–restore cycle.
