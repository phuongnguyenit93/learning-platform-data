# Plugin Lifecycle: Quiescing New Requests, Draining In-Flight Work, and Cooperative Cancellation

When a Java plugin needs to be **disabled, hot-reloaded, upgraded, or removed**, you cannot simply flip an `enabled=false` flag and close the `ClassLoader`. The plugin may still be processing requests, holding callbacks registered with the host, running background jobs, using thread pools, or participating in unfinished `CompletionStage` chains. Closing resources too early can cause already-accepted requests to fail midway, leave data half-written, keep the old class loader alive forever, or let old tasks continue interfering with the new version.

A proper shutdown workflow must separate three actions:

1. **Stopping new work (quiesce / admission stop):** deciding to block new requests from reaching the plugin at a clear synchronization point.
2. **Waiting for in-flight work (graceful drain):** giving already-accepted tasks a chance to complete and release resources, within a bounded time limit.
3. **Cooperative cancellation:** if the wait expires, signaling cancellation so tasks can stop safely on their own, waiting until they **actually** exit, and only then completing cleanup. `Thread.interrupt()`, `Future.cancel(true)`, and `ExecutorService.shutdownNow()` are only **cancellation requests**, not commands that forcibly terminate execution instantaneously.

This topic belongs to the **plugin lifecycle**: the goal is not stopping the entire JVM, but retiring one plugin generation without unreasonably disrupting the host or other plugins. The following invariants, Java 17 examples, boundaries, and checklists apply to plugins loaded via `ServiceLoader`, custom `ClassLoader`s, `ModuleLayer`s, or custom extension point architectures.

## 1. Precisely Defining “Stopping a Plugin”

Distinguish **not accepting more work** from **having finished all work**. These are two different milestones.

~~~text
            host routes requests / events
                         |
                         v
                   admission gate
                  /              \
           ACCEPT                REJECT
             |                      |
             v                      +--> controlled error / route to new plugin
      register in-flight
             |
             v
       execute plugin work
             |
     success / failure / cancelled
             |
             v
      release in-flight
             |
             v
          drain == 0
             |
             v
  detach callbacks, close owned resources
             |
             v
           STOPPED
~~~

Meaningful logical states typically include:

| Logical State | Accept New Requests? | Already-Accepted Work | Permitted Actions |
| --- | --- | --- | --- |
| `ACTIVE` / `RUNNING` | Yes | Running | Admit and execute normally |
| `QUIESCING` | **No** | Continues running | Wait for completion, keep required resources alive |
| `CANCELLING` | No | Requested to stop | Set cancellation token, cancel tasks/Futures, interrupt if safe |
| `STOPPING` / `CLEANUP` | No | Must have exited or been isolated via an explicit strategy | Detach callbacks, close executors/resources, clean up registry |
| `STOPPED` | No | **No longer using plugin resources** | Safe to drop references to the old loader/layer generation |
| `FAILED_TO_STOP` / `QUARANTINED` | No | Some task refuses to stop or cleanup failed | Keep isolated, report error, proceed per policy |

This is a **conceptual model**; not every implementation needs all six enum values. The runnable example in Section 5 uses three states—`ACTIVE`, `QUIESCING`, `STOPPED`—plus a cancellation flag, which suffices to demonstrate the core logic. In production, dedicated failure and escalation states may be needed.

### Four Critical Invariants

1. **No new admissions after the gate closes.** If `accept` and `quiesce` race concurrently, there must be a *linearization* point: a request counts as “admitted” only if it wins before the gate-closing point.
2. **Every admitted unit of work is registered once and completed once.** The `inFlight` counter must never go negative or leak when a callback throws an `Exception` or `Error`.
3. **Never declare `STOPPED` while the plugin is still in use.** A `Future` reporting cancelled, `ExecutorService.shutdownNow()` returning, or a timeout expiring does not prove the worker has exited.
4. **Cleanup has explicit ownership and ordering.** Close only resources owned by that plugin generation; never close shared host/cross-plugin thread pools, HTTP clients, or class loaders.

If these invariants are violated, an application can still log “plugin unloaded” while an old worker continues mutating the database or an old callback calls into replaced classes.

## 2. Closing the Admission Gate Before Waiting

A common race bug:

~~~java
// Wrong illustration: checking and incrementing counter are not under the same synchronization.
if (running) {
    inFlight++;
    executePlugin();
}
~~~

If the shutdown thread sets `running=false` **between** the check and `inFlight++`, the drain thread may observe `inFlight==0` and close resources, right before an old request enters the plugin.

The solution is a **synchronized admission gate**. In the Java 17 example, both `call(...)` and `quiesce()` update state under **the same `ReentrantLock`**:

~~~text
Request thread                        Shutdown thread
---------------                       ----------------
acquire lock                          acquire lock
check state == ACTIVE                 set state = QUIESCING
inFlight++                            release lock
release lock
execute operation
finally inFlight-- / signal

=> both sides cannot "win" across the same gate-closing point.
~~~

Either ordering is safe:

- If the request acquires the lock first and is admitted, `inFlight` increments before shutdown observes the state; shutdown must **wait** for that request.
- If shutdown acquires the lock first and transitions to `QUIESCING`, any later request receives `RejectedExecutionException` and never touches the plugin.

**Do not hold the state lock across the entire plugin call**: callbacks may wait on I/O, acquire their own locks, or call back into the host; holding the lock throughout execution easily causes contention and deadlocks. The lock wraps only **admission/counting/transitions**, while plugin work runs outside the lock.

### 2.1. The Gate Must Cover Every Entry Point That Creates Work

Closing an HTTP route while forgetting event consumers, schedulers, listeners, or task queues allows the plugin to keep receiving work. A real plugin may have multiple ingress paths:

- Router/gateway: REST/gRPC requests, WebSocket handlers.
- Subscriptions: event bus, message consumers, database change streams.
- Schedulers: cron jobs, timers, retry queues.
- Callbacks/capabilities: extension registries, hooks, listeners, completion callbacks.
- Async continuations: an admitted request may spawn secondary tasks after the main handler returns.

**The admission gate must cover every ingress into the plugin generation**, or each source must stop admitting and be tracked by the same shutdown coordinator. During hot reload, switching routing to the new plugin generation and closing the old generation's gate should be coordinated consistently so requests do not “fall between” two registries.

### 2.2. Distinguishing Accepted, Queued, and Running

`inFlight` must accurately reflect the contract:

| Work Type | Should It Be Counted? | Notes |
| --- | --- | --- |
| Request currently executing plugin code | Yes | Decrement only when plugin code actually exits |
| Request **accepted** by the host and sitting in a queue | If the contract commits to serving it, **yes** or track in a separate counter | If evicted/canceled before running, still release exactly once |
| Scheduled callback that has not run yet | Yes if the callback will access the old plugin | Close ingress and manage the callback's queue/lifecycle |
| Async task spawned before the handler returns | Yes, per **actual async lifetime** | Count each task or hold a lease until the entire work chain ends |
| Sleeping thread belonging only to the host and not using the plugin | Not necessarily | Must not block plugin unloading due to non-plugin resources |

Another bug is incrementing `inFlight` upon `submit` to an executor, yet decrementing only inside `Runnable.finally`. If `shutdownNow()` returns tasks that **never ran**, `finally` never executes and the counter hangs. Manage accepted/queued/running counts separately, or cancel and release leases cleanly for tasks that never started.

## 3. Graceful Drain: Bounded Waiting for In-Flight Work

After closing the gate:

1. Give already-admitted requests time to complete business logic and return results.
2. Observe `inFlight`; only when it reaches 0 can you be sure the tracked execution regions have exited.
3. Set a **finite deadline**: do not wait forever because a task lost connectivity, deadlocked, or blocked on I/O.
4. When the deadline expires, do not treat a timeout as “stopped”; move to the **cooperative cancellation** branch or escalation policy.

With `ReentrantLock`, `Condition.awaitNanos(...)` is the natural way to wait: `await` **temporarily releases the lock while waiting** and reacquires it on wakeup. Always check the condition in a `while` loop because of *spurious wakeups* or waking while other work remains.

~~~java
// Illustrative logic snippet, placed inside a class holding lock and Condition.
lock.lockInterruptibly();
try {
    while (inFlight > 0 && remainingNanos > 0) {
        remainingNanos = drained.awaitNanos(remainingNanos);
    }
    return inFlight == 0;
} finally {
    lock.unlock();
}
~~~

An implementation using `synchronized`/`wait`/`notifyAll`, `Phaser`, or a counter with `CompletableFuture` can also be correct, provided **admission and completion are synchronized with the gate-closing transition**, avoiding lost notifications and double releases.

### 3.1. Why Not Use `Thread.sleep` to “Wait Long Enough”?

Sleeping a fixed number of milliseconds and guessing all work is finished invites races. `sleep` is unrelated to actual progress and gives no correctness guarantee. Wait on the **actual condition** (`inFlight==0` or executor `isTerminated()`) with a deadline.

Avoid `Thread.join(0)` if you expect a 0 timeout to mean “don't wait”: in Java, `join(0)` means **wait forever**. Other APIs also treat 0 differently; read each API's exact contract.

### 3.2. Deadlines and Monotonic Time

For wait budgets, prefer computing remaining time with `System.nanoTime()` or `Condition.awaitNanos` to avoid wall-clock drift. A total budget can be partitioned:

~~~text
T0: close ingress
|---- graceful drain budget ----|
                                 |---- cooperative cancel grace ----|
                                                                       |---- cleanup budget ----|
                                                                         ^
                                                                      final outcome
~~~

In practice, shutdown must be bounded by the host/process deadline (Kubernetes termination grace period, application server, deploy pipeline). Do not give every task a full deadline sequentially so that total stop time exceeds the operational budget.

## 4. Cooperative Cancellation: Requesting Stop, Not Forcing Stop

When the grace period expires, the host can trigger `cancel` so all running work knows it must wrap up quickly. **Cooperative** means task code **actively checks the signal and exits along a safe path**, rather than being arbitrarily killed by the host mid-lock or mid-transaction.

### 4.1. Cancellation Token for CPU Loops or Multi-Step Workflows

A minimal model:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

final class CancellationToken {
    private final AtomicBoolean requested = new AtomicBoolean();

    void cancel() { requested.set(true); }
    boolean isCancelled() { return requested.get(); }
}
~~~

This is a complete class, though **without a `main`**. Each task receives a token scoped to the request or plugin lifecycle and checks it at safe points:

~~~java
for (Item item : items) {
    if (token.isCancelled()) {
        // Stop at a safe boundary; cleanup/rollback via finally or explicit policy.
        break;
    }
    process(item);
}
~~~

The loop above is an **illustration assuming** `items`/`process` and `token` are already defined. A token cannot by itself break a task stuck in blocking I/O; without checkpoints, it is merely an unobserved flag.

### 4.2. Thread Interruption for Waiting Tasks

`Thread.interrupt()` sets the interrupt status and wakes many standard blocking operations such as `CountDownLatch.await()`, `Thread.sleep()`, and `Object.wait()` with `InterruptedException`. It is not `Thread.stop()` and does not guarantee every piece of code or native I/O stops.

Example of proper handling at a responsible boundary:

~~~java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Restore status if not propagating.
    return; // Exit; finally will clean up resources.
}
~~~

This is a snippet; `blockingOperation` is not defined here. If the method signature permits `throws InterruptedException`, **prefer propagating the exception upward** rather than catching it and continuing as normal. When `InterruptedException` is thrown by standard blocking APIs, the interrupt status is cleared; restoring it with `Thread.currentThread().interrupt()` before leaving a layer that does not rethrow is an important convention.

**Wrong:** catching `InterruptedException`, ignoring it, and continuing the loop, or calling `Thread.interrupted()` just to log it while accidentally clearing the status. `Thread.currentThread().isInterrupted()` reads the flag **without clearing** it.

### 4.3. What Are the Limits of `Future.cancel(true)` and `shutdownNow()`?

- `Future.cancel(true)` **attempts** to cancel the task, potentially requesting an interrupt if running; a Future having `isCancelled()==true` or `isDone()==true` does not prove task code has exited `finally`.
- `ExecutorService.shutdown()` stops accepting new tasks and lets submitted tasks finish; it **does not wait**. You must call `awaitTermination(timeout, unit)`.
- `ExecutorService.shutdownNow()` attempts to stop running tasks, prevents queued tasks from starting, and returns unstarted `Runnable`s; it generally relies on interruption, is **best effort**, and gives no guarantee that threads have exited.
- For `CompletableFuture.cancel(boolean)`, the API states the `mayInterruptIfRunning` parameter **has no effect in the `CompletableFuture` implementation**, so do not rely on that call to assume a worker thread was interrupted.
- `Thread.stop()`/`Thread.suspend()` are dangerous, deprecated mechanisms that can corrupt invariants/locks; **never** use them to force-stop a plugin.

If a task executes a database transaction, the host must define commit/rollback boundaries and idempotency mechanisms. Canceling a request does not mean operations outside the JVM (HTTP APIs, transactions, published messages) were necessarily rolled back.

### 4.4. Avoiding Interrupting the Wrong Thread in Shared Pools

For **threads created exclusively for a request/plugin**, the host can hold a reference and send an interrupt as in the example. However, **never** store `Thread` references of tasks running on a shared pool and interrupt them unconditionally: the task may have finished and the thread may have been reused for another plugin or host job by the time the signal arrives.

In production, you should:

- Track a separate `Future`/cancellation handle per **individual task** and a token scoped per generation.
- Use a plugin-owned executor if you want to call `shutdown()/shutdownNow()` without affecting the host.
- Attach a version/generation ID when registering tasks so cancellation is never sent to a new generation by mistake.
- Ensure task code checks tokens/interrupts and finishes cleanup before being counted as quiesced.
- Separate **logical** cancellation of a Future from **physical** completion of plugin work.

## 5. Complete Java 17 Example: Admission Gate, Drain, and Cancel

The standalone example below demonstrates two scenarios:

- **Graceful:** the plugin has admitted one job; the host quiesces, waits, and the worker finishes on its own; no cancellation needed.
- **Timeout/abort:** the plugin has admitted one job waiting on a latch; the host quiesces, rejects a new request, confirms drain has not completed, issues cooperative interruption, waits for the worker to exit, and marks `STOPPED`.

Because this is a shutdown lesson, the code intentionally uses `CountDownLatch` instead of network/database I/O so **stdout is deterministic**, independent of machine speed. This is an admission-gate model; it does not register HTTP routes, message subscriptions, or an `ExecutorService`. The example also has no real plugin resources to close; in real plugins, cleanup must run **after draining** and **before declaring stop complete**.

### 5.1. Single File `PluginShutdownDemo.java`

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public final class PluginShutdownDemo {
    static final class PluginGate {
        enum State { ACTIVE, QUIESCING, STOPPED }

        private final ReentrantLock lock = new ReentrantLock();
        private final Condition drained = lock.newCondition();
        private final Map<Thread, Integer> activeThreads = new HashMap<>();
        private State state = State.ACTIVE;
        private int inFlight;
        private volatile boolean cancelRequested;

        <T> T call(Callable<T> operation) throws Exception {
            Objects.requireNonNull(operation);
            Thread owner = Thread.currentThread();
            lock.lock();
            try {
                if (state != State.ACTIVE) {
                    throw new RejectedExecutionException("plugin is stopping");
                }
                inFlight++;
                activeThreads.merge(owner, 1, Integer::sum);
            } finally {
                lock.unlock();
            }
            try {
                return operation.call();
            } finally {
                lock.lock();
                try {
                    inFlight--;
                    activeThreads.compute(owner,
                            (thread, depth) -> depth == 1 ? null : depth - 1);
                    if (inFlight == 0) drained.signalAll();
                } finally {
                    lock.unlock();
                }
            }
        }

        void quiesce() {
            lock.lock();
            try {
                if (state == State.ACTIVE) state = State.QUIESCING;
            } finally {
                lock.unlock();
            }
        }

        boolean awaitDrained(Duration timeout) throws InterruptedException {
            long remaining = timeout.toNanos();
            if (remaining < 0) throw new IllegalArgumentException("negative timeout");
            lock.lockInterruptibly();
            try {
                while (inFlight > 0 && remaining > 0) {
                    remaining = drained.awaitNanos(remaining);
                }
                return inFlight == 0;
            } finally {
                lock.unlock();
            }
        }

        void requestCancellation() {
            List<Thread> snapshot;
            lock.lock();
            try {
                if (state != State.QUIESCING) {
                    throw new IllegalStateException("quiesce first");
                }
                cancelRequested = true;
                snapshot = new ArrayList<>(activeThreads.keySet());
            } finally {
                lock.unlock();
            }
            for (Thread thread : snapshot) {
                thread.interrupt();
            }
        }

        boolean cancellationRequested() {
            return cancelRequested;
        }

        int activeCalls() {
            lock.lock();
            try { return inFlight; }
            finally { lock.unlock(); }
        }

        void markStopped() {
            lock.lock();
            try {
                if (state != State.QUIESCING || inFlight != 0) {
                    throw new IllegalStateException("still running");
                }
                state = State.STOPPED;
            } finally {
                lock.unlock();
            }
        }

        State state() {
            lock.lock();
            try { return state; }
            finally { lock.unlock(); }
        }
    }

    public static void main(String[] args) throws Exception {
        PluginGate normal = new PluginGate();
        CountDownLatch normalEntered = new CountDownLatch(1);
        CountDownLatch normalRelease = new CountDownLatch(1);
        Thread normalWorker = new Thread(() -> {
            try {
                normal.call(() -> {
                    normalEntered.countDown();
                    normalRelease.await();
                    return "ok";
                });
                System.out.println("gracefulWorker=completed");
            } catch (Exception e) {
                throw new RuntimeException(e);
            }
        }, "normal-request");
        normalWorker.start();
        normalEntered.await();
        normal.quiesce();
        System.out.println("gracefulBeforeRelease="
                + normal.awaitDrained(Duration.ZERO));
        normalRelease.countDown();
        normalWorker.join();
        System.out.println("gracefulAfterRelease="
                + normal.awaitDrained(Duration.ofSeconds(1)));
        normal.markStopped();
        System.out.println("gracefulState=" + normal.state());

        PluginGate gate = new PluginGate();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocked = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                gate.call(() -> {
                    started.countDown();
                    blocked.await();
                    return "completed";
                });
            } catch (InterruptedException expected) {
                Thread.currentThread().interrupt();
                System.out.println("worker=cancelled");
            } catch (Exception unexpected) {
                throw new RuntimeException(unexpected);
            }
        }, "plugin-request");

        worker.start();
        started.await();
        System.out.println("inFlight=" + gate.activeCalls());

        gate.quiesce();
        System.out.println("state=" + gate.state());
        try {
            gate.call(() -> "late request");
        } catch (RejectedExecutionException expected) {
            System.out.println("lateRequest=rejected");
        }
        System.out.println("drainedBeforeCancel="
                + gate.awaitDrained(Duration.ZERO));

        gate.requestCancellation();
        worker.join();
        System.out.println("cancelRequested=" + gate.cancellationRequested());
        System.out.println("drainedAfterCancel="
                + gate.awaitDrained(Duration.ofSeconds(1)));
        gate.markStopped();
        System.out.println("state=" + gate.state());
    }
}
~~~

Why is `activeThreads` a `Map<Thread,Integer>` instead of a `Set<Thread>`? A thread may make nested `gate.call(...)` calls; the map tracks entry depth per thread so exiting an inner call does not remove a thread that still has an active outer call. `inFlight` increments/decrements on each entry/exit. All updates to the counter and map occur under the lock; calling `operation.call()` runs **outside** the lock.

In the example, each task uses a **dedicated thread** and never reuses that thread for another task. `requestCancellation` takes a snapshot of currently executing plugin threads and sends interrupts **after releasing the lock** to avoid holding the mutex while signaling tasks. With shared pools or async tasks, replace thread tracking with task-specific cancellation handles as described in Section 4.4.

### 5.2. Compiling and Running

Save as `PluginShutdownDemo.java` in the current directory. With Java 17 or later:

~~~bash
javac --release 17 PluginShutdownDemo.java
java -cp . PluginShutdownDemo
~~~

**Stdout verified with Amazon Corretto JDK 17.0.15:**

~~~text
gracefulBeforeRelease=false
gracefulWorker=completed
gracefulAfterRelease=true
gracefulState=STOPPED
inFlight=1
state=QUIESCING
lateRequest=rejected
drainedBeforeCancel=false
worker=cancelled
cancelRequested=true
drainedAfterCancel=true
state=STOPPED
~~~

### 5.3. Analyzing the Graceful Branch

1. `normalWorker` enters `normal.call(...)` first: the counter increments to 1 and `normalEntered` signals that it was admitted.
2. `normal.quiesce()` closes the gate; this request **is still allowed to finish** because it already passed admission.
3. `awaitDrained(Duration.ZERO)` immediately returns `false` since the worker is still waiting on `normalRelease`.
4. The host releases the latch and the worker finishes normally. The `finally` block in `call` decrements the counter to 0 and calls `signalAll()`.
5. `normalWorker.join()` ensures the thread exits in the test fixture; `awaitDrained(Duration.ofSeconds(1))` returns `true`; only then does the host call `markStopped()`.

Key point: **no cancellation is needed** if tasks complete within the grace window. Closing the gate should not by default abort requests that were already admitted.

### 5.4. Analyzing the Cancellation Branch

1. `worker` is admitted, `inFlight=1`, and then blocks on `CountDownLatch.await()`.
2. The host sets `state=QUIESCING`; a new `gate.call(...)` is rejected with `RejectedExecutionException`.
3. `awaitDrained(Duration.ZERO)` returns `false`; you must not ignore this and jump straight to `STOPPED`.
4. `requestCancellation()` sets the volatile token and calls `interrupt()` on the fixture's dedicated thread.
5. `blocked.await()` responds with `InterruptedException`. The worker catches it, restores the interrupt status, and exits; the `finally` block inside `gate.call` **still runs** to decrement `inFlight`.
6. The host calls `worker.join()`; afterward `awaitDrained(...)` becomes `true` and `markStopped()` succeeds.

This proves that **the cancellation signal** and **confirming work has exited** must be handled as two independent steps. In this program `join()` has no timeout because the test fixture knows for certain the latch supports interruption; production code must never assume every plugin reacts that quickly.

### 5.5. Boundaries of the Demo

- `PluginGate.call` runs synchronously on the calling thread; if a plugin calls `executor.submit(...)` and returns immediately, you must hold a lease or track the **actual async task** until it exits.
- `blocked` intentionally never receives `countDown()`; it serves to illustrate interrupting a waiting task. Real systems need a deadline so the host does not hang forever.
- `requestCancellation()` snapshots registered threads and interrupts them; this suits **threads dedicated to the example's work**, and is not a safe default pattern for shared thread pools.
- `markStopped()` in the demo only changes state because it owns no DB connections/HTTP clients/executors. When real resources exist, close/clean them up in order and record failures before marking completion.
- How `InterruptedException` is handled inside a callback is the task's responsibility; the host cannot force plugin code to react if the callback ignores the signal.
- `Duration.toNanos()` can throw on negative or overly large durations; production code should validate total budgets and handle overflow when computing deadlines.

## 6. When a Plugin Uses ExecutorService or Future

Many plugins use their own background executor. If **the executor is a resource owned by the plugin**, the `ExecutorService` API already supports a two-phase shutdown:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

static boolean stopOwnedExecutor(ExecutorService executor)
        throws InterruptedException {
    executor.shutdown(); // Stop accepting new tasks in this executor.
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow(); // Best effort: cancel queued/running tasks.
        return executor.awaitTermination(3, TimeUnit.SECONDS);
    }
    return true;
}
~~~

This is an **illustrative method** that must sit inside a class. The timeout values are policy examples, not JDK defaults.

**Practical sequence to follow:**

1. Close the plugin gate at the router/registry/consumer first so callbacks cannot keep submitting new tasks.
2. Call `executor.shutdown()` only if the executor **is exclusively owned by the plugin**.
3. Wait with `awaitTermination` using a bounded timeout. On timeout, call `shutdownNow()` and wait again.
4. If the executor still has not terminated, do **not** treat `shutdownNow()` as success; report stop-incomplete, quarantine the plugin, or let a higher-level coordinator decide whether to restart the process.
5. Are there any independent threads, subscriptions, or continuations outside this executor? Track them separately.

`shutdownNow()` returns a list of unstarted tasks. If the system tracks pending/accepted task counts, update them consistently after the queue is canceled. For `Future.cancel(true)`, do not use `Future.isDone()` as a reliable substitute for **the worker having exited plugin code**.

**Note on interruption during shutdown:** If the coordinating thread receives `InterruptedException` while waiting, it must preserve the cancellation request, apply upper-level policy, and usually restore the interrupt status if not rethrowing. Never swallow the interruption and log `STOPPED` while work is still running.

## 7. When a Request Spawns Asynchronous Work

A handler can look finished while plugin tasks remain alive:

~~~java
// Illustrates lifecycle bug if only handler execution time is counted:
CompletionStage<Result> handle(Request request) {
    return remoteCall(request).thenApply(this::transform);
}
~~~

If `handle` returns a `CompletionStage` immediately and the admission lease is released when **returning the stage**, drain can drop to 0 while the `transform` continuation has not even run yet. To make this right, one approach is:

~~~java
// Illustrative code: lease and stage are defined by the host.
CompletionStage<Result> stage = startPluginWork(request);
return stage.whenComplete((value, failure) -> lease.close());
~~~

`lease.close()` in the `whenComplete` callback must be **idempotent**, guarantee decrementing exactly once, and not be missed if `startPluginWork` throws before returning a stage. Use `try/catch` for the failed-submit path and an `AtomicBoolean` guard on release; avoiding double-decrement is essential.

**Further distinction:** a future/stage can complete **before all external work behind it actually stops**, especially when cancellation only flips a logical state. If the plugin spawns auxiliary threads/processes that the stage does not track, the host still needs independent tracking.

### 7.1. Tasks Spawning More Tasks After Quiesce

An already-admitted request may try to spawn child jobs. Define a policy:

- **Disallow new child tasks** after quiesce (simple and safe if handlers can exit cleanly).
- Or allow child tasks belonging to an already-admitted request and **inherit the same request lease**, while ensuring deadlines/cancellation propagate and drain waits for the entire task tree.

Never let an old request reopen the gate or register new unbounded background timers. Tokens should therefore propagate across RPCs, callback chains, and executor wrappers, rather than sitting as an unchecked boolean flag at the root.

### 7.2. Coordinating Cancellation with Side Effects

If a plugin executes a pipeline:

~~~text
read input -> update database -> publish event -> acknowledge message
~~~

cooperatively stopping between two steps can leave a “DB written, event not published” state. Cancellation does not automatically undo committed side effects. You need transactions where supported, the outbox pattern, idempotency keys, checkpoints/retries, and duplicate handling per business contract. Especially in message consumers, never ack early before the handler truly succeeds; shutdown needs explicit requeue, dead-letter, or retry policies.

## 8. Hot Reload: One New Plugin Generation and One Old Generation

A safer rollout than “close and immediately reload”:

~~~text
Version/generation V1                  Version/generation V2
---------------------                  ---------------------
ACTIVE: accepts traffic                LOADING + health check
      |
      +-- atomically update host routing to V2 -----------> ACTIVE
      |
      +-- QUIESCING: reject new V1 entry
      |
      +-- DRAIN or CANCEL outstanding V1 calls
      |
      +-- detach callbacks, timers, event subscriptions
      |
      +-- close V1-owned resources and classloader (when safe)
      |
      +-- STOPPED; release strong references to V1
~~~

Switch routing to V2 only after V2 is loaded, registered, and passes appropriate health checks. If the new version fails initialization, keep V1 serving (if not yet quiesced) or roll back routing under an explicit policy; do not arbitrarily pull V1's state from `QUIESCING` back to `ACTIVE` if doing so could reuse resources already being torn down.

### 8.1. Detaching Callbacks Must Be Ordered

A typical shutdown includes:

1. **Disable/quiesce ingress:** block new routes, deregister service discovery for the old generation, pause message consumers if supported by the API.
2. **Stop producers:** stop timers/crons/retry producers that generate additional work.
3. **Drain or cancel:** wait for active requests, long-running tasks, queues, and continuations.
4. **Detach extension hooks:** unregister event listeners, callbacks, MBeans, service handles, observers, and related thread-local references.
5. **Close owned resources:** plugin-owned executors, HTTP/DB clients, file handles, sockets, caches, and classloader/JAR handles according to ownership.
6. **Remove registry strong refs:** remove V1 instances, `Class<?>`, provider factories, `ModuleLayer`s, and loaders from registries/caches once no longer in use.
7. **Report terminal outcome:** `STOPPED`, or an error/needs-escalation state if work still refuses to stop.

Do not close resources in one rigid order for every plugin. For instance, if a worker needs a DB connection to finish rollback, closing the DB pool before the worker exits is wrong; conversely, scheduler producers must stop early so they do not create new tasks.

### 8.2. Closing a ClassLoader Does Not Mean Immediate Class Unloading

`URLClassLoader.close()` releases loader resources such as handles to managed JARs, but it **does not** force the JVM to unload all classes defined by that loader and does not destroy remaining instances. As long as references remain from threads, thread context class loaders (TCCL), static host registries, caches, listeners, or executing plugin methods, the old generation may never be reclaimed.

When using a custom `ModuleLayer`, the module graph/classloaders likewise follow object reachability and garbage collection rules. There is no standard `ModuleLayer.close()` to terminate all tasks in a layer. Proactively clear references/callbacks and let GC decide reclaimability once usage ends.

### 8.3. Do Not Accidentally Cancel V2 While Stopping V1

Every task cancellation handle, token, lease, and registry entry should be tagged with a **generation ID**, not just the logical plugin name. For example, `payments:v12` differs from `payments:v13`, even though both implement `PaymentPlugin`. “Stop v12” must close only the gate and cancel tasks belonging to generation v12.

If all versions share a common executor, cancel only **V1's task handles**; never call `shutdownNow()` on the shared pool. If TCCL is used to load plugins, restore the worker's TCCL in `finally` right after the task so old classloaders are not retained on thread pools.

## 9. Options When a Plugin Refuses to Cancel

Some tasks do not respond to interrupts: CPU loops that never check tokens, stuck native calls, lock deadlocks, or I/O waits without timeouts. After both the graceful period and cancellation grace period expire, **do not claim stop succeeded** without evidence.

| Observed State | Recommended Response |
| --- | --- |
| `inFlight==0`, resource cleanup succeeded | Transition to `STOPPED` |
| Task has not exited yet but still responds to cancel | Wait within remaining budget, update progress |
| Task unresponsive, cannot be isolated | Keep `FAILED_TO_STOP`/`QUARANTINED`; do not reuse risky resources |
| Task holds dangerous side effects/transactions | Do not blindly close connections/loaders; trigger recovery policy |
| Process shutdown has a hard deadline | Process-level orchestration may have to terminate/restart the instance and recover durable work afterward |

For plugins running **in the same JVM**, there is no safe Java SE primitive to “forcibly terminate a single arbitrary plugin” guaranteed not to corrupt the host. If hard isolation is required for uncooperative code, run untrusted plugins in **separate processes/containers** over IPC/RPC; then OS-level orchestration can terminate the process past its deadline with proper recovery mechanisms.

The shutdown coordinator must record **deadline expiration** and return an unsuccessful outcome when necessary. Marking `STOPPED` merely to make a dashboard look clean is a serious operational bug.

## 10. Timeout Policies, Retries, and Observability Data

Define a concrete shutdown policy, for example:

| Phase | Example Duration | Rules |
| --- | --- | --- |
| Quiesce admission | Immediate on stop start | Admit no new requests past the synchronized gate-closing point |
| Graceful drain | 10 seconds | Wait conditionally; do not interrupt soon-to-finish tasks early |
| Cooperative cancel grace | Next 5 seconds | Send tokens/cancel handles, interrupt tasks that support it |
| Cleanup | Within remaining budget | Detach listeners, close owned resources |
| Escalation | When total deadline expires | Report non-terminal/incomplete or restart process per policy |

These values are **operational examples**, not standard timeouts of `ServiceLoader`/JPMS/JDK. Timeouts depend on SLAs, task types, and platform deadlines.

Measure and log:

- `pluginId`, `generationId`, before/after states, stop reason (deploy, disable, crash, timeout).
- Ingress-closed timestamp, active/queued requests at start and remaining at each stage.
- Counts of tasks completed naturally, failed, canceled, ignoring interrupts, or still hung.
- Drain duration, cancel duration, cleanup duration, and total time to terminal outcome.
- Resources that failed to close, stack traces, and root causes of `InterruptedException`/`CancellationException`.
- Late-request rejection rate and caller response/fallback behavior.

Do not log sensitive request data or entire script/plugin payloads to monitor shutdown. Log task identifiers and intentional error details to limit leakage.

## 11. Common Mistakes and How to Fix Them

| Mistake | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Setting boolean `enabled=false` without synchronizing with task admission | Race: request slips past check before gate closes | Admission state and `inFlight++` must be atomic under the same lock/CAS protocol |
| `inFlight++` on submit, decrement only in `Runnable.finally` | Tasks canceled while still queued never run `finally` | Issue leases for queued/cancel-before-start, release exactly once |
| Using `Future.isDone()` to prove the plugin is idle | A canceled Future can complete before worker code exits | Track physical completion / owned executor termination |
| `shutdownNow()` then immediately closing the plugin | Interruption is best effort only | Wait for `awaitTermination`/drain confirmation; report failure if not stopped |
| Catching `InterruptedException` and ignoring it | Task keeps running while host thinks it canceled | Propagate or restore interrupt and exit at a safe point |
| Calling `Thread.stop()` | Corrupts invariants/locks and shared state | Cancellation tokens and voluntary interruption |
| Holding locks while running plugin callbacks | Deadlocks; shutdown cannot acquire the lock | Locks manage only state/counters; release before callbacks |
| Closing DB client/JAR loader before drain | In-flight tasks fail mid-execution | Wait for tasks to stop/roll back properly, then close |
| Removing only the router while forgetting event listeners/timers | Plugin still gets invoked outside HTTP | Inventory all ingress paths and async continuations |
| Using the same ID to cancel V1 and V2 | Can cancel requests on the new version | Attach generation ID and ownership to task handles |
| Setting no deadline | Shutdown hangs forever if a plugin does not cooperate | Explicit grace budget, cancel budget, and escalation |
| Catching all `Throwable` and reporting success | Swallows critical cleanup/stop errors | Aggregate errors; retain failed/incomplete state when needed |
| Shutting down an executor shared across plugins | Breaks the host or other plugins | Shut down only plugin-owned resources |
| Clearing the registry while TCCL/callbacks remain | Retains the old classloader, leaking memory | Clean up callbacks/TCCL/threads/caches and inspect heap when needed |

One easy confusion: `ServiceLoader.reload()` only refreshes the provider cache of one loader object; it **does not** stop in-flight requests, cancel tasks, close instances, shut down thread pools, or unload plugins. Do not use `reload()` as a shutdown command.

## 12. Testing and Acceptance Criteria

A reliable lifecycle implementation should have an automated test suite:

### 12.1. Admission Race

Run many requests racing against `quiesce`. Verify that after the quiesce point, **no new requests are admitted** into that generation. Requests admitted before the cutoff must be accounted for in active/queued counters. Do not check only final totals; continuously pump requests while stopping.

### 12.2. Graceful Completion

Create a task blocked on a latch; transition the gate to `QUIESCING`; verify drain is not done; release the latch and verify drain succeeds. No cancellation is needed. This branch is illustrated by `gracefulBeforeRelease=false` / `gracefulAfterRelease=true` in Section 5's code.

### 12.3. Cooperative Cancellation

Use both a task blocking in `await`/`sleep` and a CPU task with token checks. Trigger cancel; verify workers observe the signal, run `finally`, and decrement counters exactly once. The `worker=cancelled` branch of the sample code demonstrates interruptible waiting. Add a test with a task ignoring interrupts to verify **timeout leads to `FAILED_TO_STOP`**, never reporting `STOPPED`.

### 12.4. Queued Task Canceled Before Running

Submit tasks to a bounded queue, quiesce, then cancel pending tasks. Verify tasks that never started are still released from accepted/queued counts without waiting on a `finally` that never runs. If holding `Future`s, distinguish `isCancelled` from actual task cleanup.

### 12.5. Async Continuations and Callbacks

Have the initial task return a `CompletionStage` early while the stage is still processing. Ensure drain is not marked complete; only after the stage/child tasks finish is the generation lease released. Stop timers/schedulers and unregister hooks so no new work is generated.

### 12.6. Cleanup Errors and Reload

Simulate an `AutoCloseable.close()` failure; the system must log the error, handle remaining resources per policy, and not disguise it as complete success. Load a new generation concurrently while the old generation drains; ensure V1 tasks never accidentally invoke V2 and stopping V1 does not shut down a shared executor.

### 12.7. Coordinator Thread Interruption

Interrupt the thread inside `awaitDrained`. Ensure the shutdown workflow does not silently bail out and declare `STOPPED`; quiesce state remains preserved, interruption is propagated/restored per ownership, and the upper coordinator knows the stop did not complete.

### 12.8. Metrics and Memory Leaks

Across repeated load/quiesce/unload cycles, monitor threads, executors, active listeners, open handles, and retained classloaders. Do not promise immediate classloader GC; use heap dumps and weak references to investigate strong references lingering after a reasonable period.

**`STOPPED` criteria:** the gate admits no new requests; all work for that generation has terminated per the agreed definition; callbacks/subscriptions and owned resources are cleaned up; no host path intentionally calls the old plugin again; and no unresolved stop errors are hidden.

## 13. Implementation Checklist for Real Plugin Systems

Before shipping hot reload/disable to production, answer clearly:

1. **What are all ingress points that can invoke the plugin?** Routers, event buses, schedulers, message consumers, callback registries, async tasks.
2. **Where is admission?** Is there a synchronization point guaranteeing `accept` and `quiesce` cannot race?
3. **What is counted?** In-flight calls, queued tasks, futures/continuations, or all of them? Is release guaranteed exactly once even on exceptional completion or pre-run cancellation?
4. **What is the grace budget?** Who owns the overall deadline, and is finishing valid requests prioritized?
5. **What is the concrete cancellation mechanism?** Do tasks have token checks, interruptible waits, I/O timeouts, and rollback/idempotency?
6. **Where is actual task exit confirmed?** Never confuse a canceled `Future` with an exited worker.
7. **What if a task refuses to stop?** Are there incomplete/quarantine states, alerts, process isolation, or restart policies?
8. **Which resources belong to the plugin?** Executors, connections, caches, listeners, class loaders; never close shared host resources.
9. **How does hot reload manage generations?** New routing, V1-scoped cancellation, dropping old refs, without affecting V2.
10. **What are the hard tests?** Concurrent requests, queued cancellation, async continuations, delayed interrupts, timeouts, cleanup failures, and leaks.
11. **What about business data after cancellation?** Are there transactions/compensation, idempotency, retries, and preservation of results for already-admitted requests?
12. **Who is allowed to declare `STOPPED`?** Only the coordinator that verified actual stop conditions, never based solely on a timeout or a cancel signal.

## 14. Quick Reference

~~~text
RUNNING
   |
   +-- close admission gate (atomic with new-request registration)
   v
QUIESCING
   |
   +-- wait until inFlight == 0 (bounded graceful deadline)
   |              |
   |              +-- drained --> cleanup owned resources --> STOPPED
   |
   +-- timeout --> request cooperative cancellation
                           |
                           +-- set token / cancel task handles / interrupt when safe
                           |
                           +-- wait until ACTUAL workers have exited
                                         |
                                         +-- drained --> cleanup --> STOPPED
                                         |
                                         +-- still running --> FAILED_TO_STOP
                                                            / QUARANTINED
                                                            / escalation
~~~

**Concluding principle:** **Stopping new requests** is an admission-policy change; **waiting for in-flight work** is a measurable runtime fact; **cooperative cancellation** is only a signal asking tasks to stop cleanly. None of these three steps can substitute for another. A plugin finishes its shutdown lifecycle only when no entry paths remain into the old generation, tasks are genuinely no longer using its resources, and cleanup has been performed according to ownership.

### Official References

- [Java SE 17 – ExecutorService](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow`, `awaitTermination`, and the two-phase shutdown pattern.
- [Java SE 17 – Thread](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): `interrupt`, `join`, interruption status, and why `Thread.stop()` is unsafe.
- [Java SE 17 – InterruptedException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html): responding to interrupted waits and interrupt status.
- [Java SE 17 – Future](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html): cancellation requests and Future state.
- [Java SE 17 – CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html): cancellation semantics in the implementation.
- [Java SE 17 – Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): `awaitNanos`, condition waits, and spurious wakeups.
- [Java SE 17 – URLClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()` and the scope of class loader resource release.
