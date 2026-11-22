# Designing Stop/Shutdown for Periodic Schedules in Java

## 1. The Problem: Stopping a Schedule Does Not Mean Stopping Running Work

In Java Concurrency, **ScheduledExecutorService** lets you schedule one-shot or recurring periodic tasks. Two common methods are **scheduleAtFixedRate(...)** and **scheduleWithFixedDelay(...)**; both return a **ScheduledFuture<?>**, representing the periodic schedule.

A periodic component such as a metric collector, health check, data synchronization job, or maintenance task needs a clearly designed lifecycle. When the application stops, you may need to:

1. **Prevent triggering new runs** after receiving a stop request.
2. **Allow the currently running execution to finish** if it is still within the allowed deadline.
3. **Request interruption of the currently running execution** if the deadline is exceeded or a fast stop is needed.
4. **Wait for resources to actually terminate** and report the shutdown status.
5. **Ensure multiple start/stop cycles do not create duplicate schedules** or use an already-shut-down executor.

These are distinct requirements. **ScheduledFuture.cancel(...)** affects a single task's schedule; **executor.shutdown()/shutdownNow()** affects the executor; **awaitTermination(...)** waits for the executor to finish. To guarantee safety, you must coordinate them and design tasks to cooperate with stop signals.

This lesson uses only scheduling and synchronization APIs from the Java standard library, without tying into any framework lifecycle.

## 2. Understanding scheduleAtFixedRate and scheduleWithFixedDelay

| API | How the Next Execution Time Is Determined | Notes When Stopping |
|---|---|---|
| **scheduleAtFixedRate(task, initialDelay, period, unit)** | Target schedule: start + k × period | If one run takes longer than period, the next run may start late; runs of **the same schedule** do not overlap |
| **scheduleWithFixedDelay(task, initialDelay, delay, unit)** | Next run starts after the previous run **finishes** plus delay | Easy to control the pause between runs; runs of **the same schedule** also do not overlap |

Both methods return a **ScheduledFuture** for the **entire periodic sequence**, not a separate Future per execution. The Future of a normally continuing schedule usually has **isDone() == false** even after many runs have completed. Do not call **get()** indefinitely to "get the result of the latest run": that call may block until the entire schedule ends due to cancellation or an error.

If a periodic run throws an exception out of the Runnable, **subsequent runs are suppressed** according to the ScheduledExecutorService contract. Therefore, logging, metrics, and exception-handling rules inside the Runnable are part of stop/shutdown design: a schedule stopping due to an error is not equivalent to an intentional stop.

In particular, **no two executions of the same periodic task run concurrently** in ScheduledThreadPoolExecutor; however, two **different** periodic tasks can run in parallel if the executor has multiple workers. An overly long run delays a fixed-rate schedule, but does not spawn a second run overlapping that same run.

## 3. Four Mechanisms to Distinguish

| API | Scope | Primary Effect |
|---|---|---|
| **ScheduledFuture.cancel(false)** | One schedule/task | If cancellation succeeds, prevents future runs, **does not request interruption** of the currently running execution |
| **ScheduledFuture.cancel(true)** | One schedule/task | If cancellation succeeds, may request an **interrupt** on the running thread; does not guarantee the task stops immediately |
| **ExecutorService.shutdown()** | Entire executor | Rejects new tasks and performs an orderly shutdown according to the executor's policies |
| **ExecutorService.shutdownNow()** | Entire executor | Attempts to stop running tasks via interrupt, prevents processing of waiting tasks, and returns the list of tasks that had not started |
| **ExecutorService.awaitTermination(timeout, unit)** | Entire executor | Blocks the calling thread to wait for the entire executor to terminate or time out; returns a boolean |

**shutdown() is not awaitTermination().** shutdown signals the start of stopping and returns; workers may still be running. Calling **isShutdown()** only tells you the executor has received shutdown. **isTerminated()** tells you it has finished all tasks after shutdown. **awaitTermination() == false** means the wait timeout expired before the executor terminated; it does not mean the shutdown operation was "rejected".

**shutdownNow() is not "kill thread" either.** Java interruption is a cooperative mechanism. A compute-bound task that never checks for interrupts, waits on I/O that does not respond to interrupts, or is stuck in an external library can still continue. You must not assume all tasks or side effects have ceased simply because shutdownNow() has returned.

**cancel() and execution results:** A successfully cancelled Future reports **isCancelled() == true**, **isDone() == true**, and **get()** throws CancellationException. However, an in-flight run may still continue after cancel(false) is called, so the Future's state is not confirmation that the internal execution has actually exited.

## 4. Policies Specific to ScheduledThreadPoolExecutor

**ScheduledThreadPoolExecutor** is the flexible implementation of ScheduledExecutorService. It has important policies during shutdown:

| Policy | Default | Meaning |
|---|---|---|
| **getContinueExistingPeriodicTasksAfterShutdownPolicy()** | **false** | Existing periodic tasks **do not continue** after shutdown() by default |
| **getExecuteExistingDelayedTasksAfterShutdownPolicy()** | **true** | Already-scheduled **one-shot** delayed tasks continue after shutdown() by default |
| **getRemoveOnCancelPolicy()** | **false** | Cancelled tasks may remain in the delay queue until their scheduled time under default cleanup |

This creates an important distinction: calling **shutdown()** on ScheduledThreadPoolExecutor stops periodic sequences by default, but **one-shot tasks scheduled far in the future can still keep the executor from terminating**. If you do not want pending one-shot delayed tasks to run on shutdown, the executor owner can configure:

~~~java
scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
~~~

When many schedules are cancelled early, consider:

~~~java
scheduler.setRemoveOnCancelPolicy(true);
~~~

This setting helps remove cancelled tasks from the queue sooner, avoiding unnecessarily holding references for a long time; it does not turn shutdownNow into a forcible termination mechanism. The two lines above are **illustrative snippets** assuming a `scheduler` variable of type ScheduledThreadPoolExecutor, not a standalone program.

**Do not enable** setContinueExistingPeriodicTasksAfterShutdownPolicy(true) if the goal is to stop all periodic schedules on shutdown. Setting it to true can keep periodic tasks executing after shutdown, preventing the executor from terminating as desired. If you use true for a special business requirement, you must have explicit cancel operations and termination checks.

**Scope:** the policy-tuning methods above belong to **ScheduledThreadPoolExecutor**, not the general contract of every ScheduledExecutorService implementation. If you are passed an arbitrary ScheduledExecutorService, rely only on interface methods or explicitly verify the underlying implementation you own.

## 5. Recommended Graceful Stop Sequence

For a component that **exclusively owns** a ScheduledThreadPoolExecutor and one or a few periodic schedules, the typical sequence is:

1. **Block new start/schedule requests.** Mark the STOPPING state with proper synchronization so other threads cannot create additional schedules while stopping.
2. **Save the ScheduledFuture handle on start**, then call **cancel(false)** to prevent new runs without actively interrupting the in-flight run.
3. **Call shutdown()** on the executor owned by the component. If the executor is shared, **do not shut down** resources managed by other components: only cancel the schedules you own.
4. **awaitTermination** with a bounded timeout, from a coordinating thread outside the running worker. Check the return value.
5. If the timeout expires and policy permits, call **shutdownNow()** to request interruption, then wait for another bounded timeout.
6. **Handle InterruptedException** on the coordinating thread: typically call shutdownNow() per system policy, restore the interrupt flag, and return or propagate the interrupted state.
7. **Close dependent resources** after ensuring tasks are no longer using them, or have a safe shutdown convention if tasks do not respond to interrupts.

Do not close HTTP clients, files, or connection pools **before** the in-flight run stops using them if doing so would cause the task to fail mid-flight. On the other hand, if I/O can block indefinitely, you need timeouts at the I/O layer and an independent release mechanism; waiting on the executor alone is not enough.

### Invariants to Maintain

- After entering STOPPING, no concurrent **start()** call may be accepted.
- For each periodic schedule, at most **one** ScheduledFuture handle is active within a single lifecycle.
- **stop()** must be idempotent or clearly specify the contract for repeated calls.
- A shut-down executor **cannot be reused for rescheduling**: typically create a new service/executor instance for a new lifecycle.
- Avoid holding locks for a long time during awaitTermination: a running task might need that lock to exit, causing a deadlock.
- Never call awaitTermination **from inside the very worker** that the executor is waiting to finish.

## 6. Java 17 Example: Graceful Stop, Allowing the In-Flight Run to Finish

This example intentionally uses **CountDownLatch** to control timing: the worker starts a run and waits, main calls **cancel(false)** while that run has not finished, unblocks it to complete, calls shutdown(), and waits for the executor to terminate. Setting the delay between runs to 1 day is solely so the example always observes **one run**; this is not a recommended period for real applications.

Save the file **GracefulPeriodicStopDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class GracefulPeriodicStopDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicInteger runs = new AtomicInteger();

        try {
            ScheduledFuture<?> periodic = scheduler.scheduleWithFixedDelay(
                    () -> {
                        runs.incrementAndGet();
                        started.countDown();
                        try {
                            release.await();
                        } catch (InterruptedException interrupted) {
                            Thread.currentThread().interrupt();
                        }
                    },
                    0, 1, TimeUnit.DAYS
            );

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            // The current run is still waiting for release.
            boolean cancelled = periodic.cancel(false);
            release.countDown();
            scheduler.shutdown();
            boolean terminated = scheduler.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("cancel accepted=" + cancelled);
            System.out.println("runs=" + runs.get());
            System.out.println("future cancelled=" + periodic.isCancelled());
            System.out.println("executor terminated=" + terminated);
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac GracefulPeriodicStopDemo.java
java GracefulPeriodicStopDemo
~~~

Expected output on a machine with normal execution capacity completing within the 5-second timeout:

~~~text
cancel accepted=true
runs=1
future cancelled=true
executor terminated=true
~~~

**Why is this verifiable?** The `started` latch ensures the first run has entered the Runnable body, while the `release` latch keeps that run from finishing before `cancel(false)`. Successful cancellation transitions the Future to cancelled, yet **does not actively interrupt** the worker. After `release`, the worker finishes; `shutdown` and `awaitTermination` wait for the entire executor to stop. In `finally`, `shutdownNow()` acts as a safeguard if the normal path does not complete; it does not erase the graceful-stop outcome already observed.

**Important:** do not use `Thread.sleep(...)` and hope `main` "cancels in time" before the worker. That approach depends on timing and easily produces flaky example results.

## 7. Java 17 Example: Graceful Shutdown Timeout Followed by Interrupt Escalation

If a running execution does not cooperate and finish within the grace period, the program needs an escalation policy. This example uses a latch to keep the worker waiting; `shutdown()` does not interrupt the worker, so `awaitTermination` with a short timeout returns false. Then `shutdownNow()` sends an interrupt, letting the worker exit `CountDownLatch.await()`.

Save **EscalatingShutdownDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class EscalatingShutdownDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocker = new CountDownLatch(1);
        AtomicBoolean sawInterrupt = new AtomicBoolean();

        try {
            ScheduledFuture<?> periodic = scheduler.scheduleAtFixedRate(
                    () -> {
                        started.countDown();
                        try {
                            blocker.await();
                        } catch (InterruptedException interrupted) {
                            sawInterrupt.set(true);
                            Thread.currentThread().interrupt();
                        }
                    },
                    0, 1, TimeUnit.DAYS
            );

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task did not start");
            }

            periodic.cancel(false);
            scheduler.shutdown();
            boolean graceful = scheduler.awaitTermination(30, TimeUnit.MILLISECONDS);

            if (!graceful) {
                scheduler.shutdownNow();
            }
            boolean terminated = scheduler.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("graceful=" + graceful);
            System.out.println("interrupt seen=" + sawInterrupt.get());
            System.out.println("terminated=" + terminated);
        } finally {
            blocker.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

Run:

~~~bash
javac EscalatingShutdownDemo.java
java EscalatingShutdownDemo
~~~

Under responsive JDK/scheduler conditions without exceeding the 5-second timeout:

~~~text
graceful=false
interrupt seen=true
terminated=true
~~~

**Explanation:** `cancel(false)` stops the schedule, but the worker waiting on the latch has not finished. `shutdown()` rejects new tasks and begins stopping the executor; the 30 ms grace period expires while the worker is still blocked, so `graceful=false`. `shutdownNow()` attempts an interrupt, causing `CountDownLatch.await()` to throw `InterruptedException`. The worker records the signal, restores the interrupt flag, and exits; only then can the executor terminate.

The `finally` safeguard ensures the latch is not held forever if an exception occurs. In a real system, **shutdownNow may fail to make a task exit**, so you must still check the boolean returned by `awaitTermination`. If `terminated=false`, you must report an incomplete stop status, record metrics/alerts, enforce I/O timeouts, or execute the appropriate recovery procedure.

## 8. Idempotent Lifecycle Management Pattern

In an application, stop requests may arrive from multiple paths or concurrently with start. A simple pattern is to **synchronize state transitions**, while waiting for task execution must happen **outside the lock**. The example below creates the executor once; calling stop multiple times does not reschedule and does not wait inside a synchronized block.

Save **PeriodicLifecycleDemo.java**:

~~~java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class PeriodicLifecycleDemo {
    private final ScheduledThreadPoolExecutor scheduler =
            new ScheduledThreadPoolExecutor(1);

    private ScheduledFuture<?> periodic;
    private boolean stopping;

    public synchronized void start() {
        if (stopping || periodic != null) {
            throw new IllegalStateException("Already started or stopping");
        }
        scheduler.setRemoveOnCancelPolicy(true);
        scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
        periodic = scheduler.scheduleWithFixedDelay(
                () -> System.out.println("tick"),
                1, 1, TimeUnit.DAYS
        );
    }

    public boolean stop(long timeout, TimeUnit unit)
            throws InterruptedException {
        synchronized (this) {
            if (!stopping) {
                stopping = true;
                if (periodic != null) {
                    periodic.cancel(false);
                }
                scheduler.shutdown();
            }
        }

        if (scheduler.awaitTermination(timeout, unit)) {
            return true;
        }
        scheduler.shutdownNow();
        return scheduler.awaitTermination(timeout, unit);
    }

    public static void main(String[] args) throws InterruptedException {
        PeriodicLifecycleDemo service = new PeriodicLifecycleDemo();
        service.start();
        boolean stopped = service.stop(5, TimeUnit.SECONDS);
        System.out.println("stopped=" + stopped);
    }
}
~~~

Run:

~~~bash
javac PeriodicLifecycleDemo.java
java PeriodicLifecycleDemo
~~~

Normal output:

~~~text
stopped=true
~~~

The program sets an `initialDelay` of one day so there is no `"tick"` before stopping. `start()` and the transition to `STOPPING` synchronize on the same monitor; `awaitTermination` happens outside the monitor. A second call to `stop` does not repeat the cancel/shutdown steps but can still wait for the executor. **Note:** if two callers enter `stop` concurrently just as the grace period expires, both may attempt `shutdownNow`; to have a single coordinator for the entire wait phase, use a state machine and a dedicated completion signal. At larger scale, you must clearly define who owns the right to stop, the absolute deadline, how errors are collected, and how status is reported.

Regarding `InterruptedException` handling in `stop`, the coordinating layer typically calls `shutdownNow` according to policy and **restores the interrupt flag** if it does not propagate the exception. The example above intentionally declares **throws InterruptedException** so the caller can decide; it does not hide the fact that the caller was interrupted.

### Shared Executor Case

If the executor is shared across multiple components, **a component that does not own the executor should only cancel its own ScheduledFuture**. If it calls `shutdown()` itself, it may stop schedules and tasks belonging to other parties. The centralized executor owner bears ultimate responsibility for `shutdown` and `awaitTermination`. When a service needs to guarantee it accepts no more work, it must synchronize `stop`/`start` within the service itself rather than relying solely on the executor's state.

## 9. Writing a Runnable That Responds to Stop Signals

Cancelling a Future or interrupting a worker does not automatically terminate all Java code. Build work cooperatively:

- **Check stop/interrupted state** at safe points before long processing steps or between batches.
- **Use bounded I/O timeouts**, because many I/O calls may not respond to `Thread.interrupt()` as desired.
- **Do not swallow InterruptedException** and continue the loop as if no stop were requested; usually restore the interrupt flag and exit early or propagate the exception.
- **Clean up in finally / try-with-resources** for resources belonging to the individual run; avoid holding locks while waiting on long I/O.
- **Do not spawn unbounded additional work** onto other executors once `STOPPING`; you must also cancel/await child tasks if you want to report a truly complete stop.
- **Keep business state consistent:** cancel does not roll back HTTP requests, file writes, transactions, or published events that have already occurred. For retries, use idempotency and/or appropriate transactions/compensation.

Pseudo-code example for a run that processes data in batches:

~~~java
void runBatch() {
    for (Batch batch : inputBatches) {
        if (stopping.get() || Thread.currentThread().isInterrupted()) {
            return;
        }
        processOneBatchWithTimeout(batch);
    }
}
~~~

This is an **illustrative snippet, not a standalone compilable program**: `stopping` is an `AtomicBoolean` owned by the component, and `inputBatches` and `processOneBatchWithTimeout` represent hypothetical business logic. The key point is checking for stop at batch boundaries, rather than cutting off data mid-write without a recovery design.

### If a Task Fails and Unintentionally Stops the Schedule

For a `Runnable` scheduled with `scheduleAtFixedRate`/`scheduleWithFixedDelay`, an uncaught exception stops subsequent runs. You can actively catch, log, and determine which errors are retryable; however, **do not swallow all errors and keep running indefinitely**. You should have a consecutive-failure threshold, backoff, health status, and a way to report a broken schedule. Clearly distinguish between: stopped by management request, cancelled, and failed due to error.

## 10. Deciding Wait Times and Handling Timeouts

A shutdown policy must answer three questions: **how much extra time to give the current task**, **what to do when the timeout expires**, and **what if an interrupt was sent yet the task still has not exited**.

Example sequence:

~~~text
RUNNING
   |
   | stop requested
   v
STOPPING: reject new schedules
   |
   | cancel(false) periodic futures, shutdown()
   v
WAIT_GRACEFUL -- awaitTermination -> terminated=true --> STOPPED
   |
   | timeout (false)
   v
ESCALATE: shutdownNow(), log/metrics
   |
   | additional bounded awaitTermination
   +---- terminated=true --> STOPPED
   |
   +---- terminated=false --> STOP_INCOMPLETE
                                (needs alert/recovery)
~~~

Do not define the **STOPPED** state solely by `isShutdown` or `isCancelled`. If a worker is still inside an I/O or blocking section, the stop is not complete by resource-release criteria. Define the level of guarantee the service commits to: "rejected new tasks", "requested cancellation", or "all workers exited and all dependencies can be released". These states can be separated significantly in time.

**Total deadline** also differs from two `awaitTermination` calls with the same timeout: if each waits 5 seconds, the total time can be around 10 seconds. When the system only allows 5 seconds overall, compute the **remaining time** against a monotonic deadline (e.g. `System.nanoTime`) before each wait to avoid accidentally exceeding the time budget.

If another thread calls `stop` again while the first is waiting, avoid races over who escalates and who receives the result. A single coordinator or completion future for the lifecycle is usually clearer than multiple callers each waiting and intervening on their own.

## 11. Testing Shutdown Behavior with Controlled Scenarios

Do not just call `Thread.sleep` and hope the task has started. `CountDownLatch`, `Semaphore`, and synchronization utilities let you establish clear checkpoints: the task **has entered its body**, **is being held**, **is allowed to exit**, **has received an interrupt**. From there you can verify both the Future's state and the executor's state.

| Scenario | What to Verify |
|---|---|
| Stop before the first run | No new runs occur; executor terminates according to policy |
| Stop while a run is executing | `cancel(false)` prevents the next run, the in-flight run completes |
| Stop when a run is unresponsive | Grace period expires, `shutdownNow` is attempted, success is not reported while the executor still has workers |
| Calling stop twice | Does not reschedule, does not throw unexpected errors under an idempotent contract |
| Race between start and stop | After `STOPPING`, no new future is accepted |
| Task throws an exception | Subsequent runs are suppressed; error is reported/recorded |
| Pending delayed one-shot task | Verify the policy on continuing execution after shutdown |
| I/O dependency unresponsive to interrupt | Deadline and alerts are not bypassed |
| Caller of stop is interrupted | Signal is preserved/propagated, avoiding indefinite waiting |
| Shared executor | Stopping one component does not shut down another component's schedules |

You can track metrics such as: number of active periodic tasks, duration of each run, last run time and outcome, failure count, timestamp when stop was requested, shutdown wait duration, escalation count, and the executor `isTerminated()` flag. With `ScheduledThreadPoolExecutor`, you can also monitor **getQueue().size()** and **getActiveCount()**; do not treat queue size as the number of future periodic runs stored or as the sole measure of system health.

## 12. Common Design Mistakes

1. **Calling only `cancel(false)` and considering the stop done.** The Future is cancelled, but the current run may still be processing; synchronize and confirm termination if you own the executor.
2. **Calling only `shutdown()` and assuming everything ends immediately.** `shutdown` does not wait; one-shot delayed tasks may still remain under the default policy.
3. **Treating `shutdownNow()` as a mandatory kill command.** Interruption is cooperative; you must handle unresponsive tasks.
4. **Calling `awaitTermination` inside the executor's own periodic Runnable.** The worker waits for the executor that needs that very worker to exit in order to terminate, leading to deadlock/timeout.
5. **Not saving the `ScheduledFuture`.** Makes it hard to cancel individual schedules or manage a component sharing an executor.
6. **Forgetting stop/start concurrency.** Two `start` calls can create duplicate schedules; `stop` racing with `start` can let a new schedule slip through.
7. **Enabling `continueExistingPeriodicTasksAfterShutdownPolicy(true)` without `cancel`.** The executor may keep running periodic tasks after shutdown and never terminate.
8. **Treating `isDone()` of a periodic Future as the result of each run.** A normally running periodic schedule is typically not done.
9. **Swallowing `InterruptedException` or closing connections before the task exits.** Prolongs shutdown or corrupts in-flight data.
10. **Restarting the same already-shut-down executor.** `schedule(...)` will be rejected; to restart, create a new lifecycle and executor.

## 13. Pre-Production Design Checklist

- Who owns the `ScheduledExecutorService`? Is this component allowed to shut down the executor or only cancel its own schedules?
- Does the schedule use fixed-rate or fixed-delay? Could a single run take longer than the desired interval?
- Is the `ScheduledFuture` saved for each schedule? Does `stop` block all new schedules?
- On stop, should the in-flight run finish or may it be interrupted? Which steps are safe to stop?
- Are timeouts configured for database/network/file I/O and are child tasks managed?
- Are shutdown policies for **periodic** and **one-shot delayed** tasks set appropriately?
- Are there a grace period, escalation, total deadline, and `STOP_INCOMPLETE` state if termination fails?
- Are `start`/`stop`/repeated `stop` synchronized and deadlock-free?
- Have you tested mid-run stop, failing tasks, delayed tasks, and interrupt-unresponsive I/O?
- Do metrics/logs distinguish between "stop requested", "Future cancelled", and "executor terminated"?

**Remember:** a reliable stop/shutdown must separately control **future schedules**, **in-flight work**, and **the executor lifecycle**. With Java `ScheduledExecutorService`, combine **cancel(false)** for graceful stop, **shutdown() + awaitTermination()** to wait for completion, and **shutdownNow()** as a bounded escalation step; always prepare a fallback for tasks that do not cooperate with interruption.
