# ScheduledExecutorService for Delayed Tasks in Java

## 1. Lesson Objectives

After this lesson, you will be able to:

- Explain **ScheduledExecutorService** in the Executor Framework and distinguish **scheduling execution after a delay** from **periodic execution**.
- Correctly use the two overloads **schedule(Runnable, delay, unit)** and **schedule(Callable<V>, delay, unit)**; understand the role of **ScheduledFuture** for results, errors, timeouts, and cancellation.
- Distinguish **when a task becomes eligible to run** from **when the task actually starts**. Understand that the JDK scheduler does not guarantee hard real-time precision (*hard real-time*).
- Choose **Executors.newSingleThreadScheduledExecutor()**, **Executors.newScheduledThreadPool(n)**, or **ScheduledThreadPoolExecutor** with appropriate configuration.
- Safely handle **shutdown()**, **shutdownNow()**, **Future.cancel()**, **InterruptedException**, tasks that throw exceptions, and associated resources.
- Recognize key risks: scheduling too many tasks, a blocked worker, wall-clock/time-zone-based schedules, duplicate task execution across retries/restarts, and dependencies between tasks in the same executor.
- Understand the difference between **scheduleAtFixedRate()** and **scheduleWithFixedDelay()** so you do not confuse one-shot scheduling with periodic scheduling.
- Run Java 17+ examples with verifiable output without relying on guessing sleep durations or incidental scheduling order.

The scope of this lesson is **general Java concurrency**, under **Future & Scheduling**. It does not cover Spring-specific scheduling APIs, annotations, or mechanisms.

## 2. From ExecutorService to ScheduledExecutorService

**ExecutorService** decouples task submission from thread creation and management. **ScheduledExecutorService** extends ExecutorService and adds the ability to request that a task become **eligible for execution after a relative delay**, or be executed on a repeating schedule.

~~~java
// Syntax illustration inside a Java method.
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

try {
    ScheduledFuture<Integer> result =
            scheduler.schedule(() -> 6 * 7, 200, TimeUnit.MILLISECONDS);
    System.out.println(result.get());
} finally {
    scheduler.shutdown();
}
~~~

You need to import the classes in java.util.concurrent and declare/handle the checked exceptions of **Future.get()**. The snippet above is not a standalone main program; a complete runnable example is in Section 5.

Components:

| Component | Role |
| --- | --- |
| **Runnable** | Task that does not return a value from run(); the schedule(Runnable, ...) overload still returns a Future for tracking |
| **Callable<V>** | Task that returns V or throws an exception |
| **ScheduledExecutorService** | Interface supporting delayed scheduling and periodic execution |
| **ScheduledThreadPoolExecutor** | Thread-pool-based implementation managing a queue of delayed tasks |
| **ScheduledFuture<V>** | Future combined with the ability to query remaining delay via Delayed |
| **TimeUnit** | Unit for delay, period, and timeout parameters |
| **ExecutorService lifecycle** | shutdown, shutdownNow, awaitTermination, task cancellation, and resource cleanup |

**A scheduled task is not necessarily running.** It may be waiting for its due time, waiting for an idle worker, or already cancelled. **ScheduledFuture** lets you observe a specific task, but it is not a persistent schedule store across JVM restarts.

### Timeline Diagram

~~~text
Submitting Thread         Scheduler                         Worker
-----------------         ---------                         ------
schedule(task, 200 ms)
       |                       |
       +---- register ---------> task sits in queue waiting for due time
                                |
              200 ms relative   +--- task BECOMES ELIGIBLE to run
                                |                |
                                +--- worker free?+----> task.run()
                                |                |
                                |            if busy, keep waiting
       <---- ScheduledFuture ---+
~~~

Note that **“200 ms” is not a promise that the task runs at exactly the 200 ms mark**. Once due, running still depends on a worker, the OS scheduler, CPU availability, previous tasks, and system resources.

## 3. Two schedule Overloads for One-Shot Execution

### 3.1. Runnable: No Return Value

~~~java
// Illustration; scheduler is an already-created ScheduledExecutorService.
ScheduledFuture<?> future = scheduler.schedule(
        () -> System.out.println("done"),
        1, TimeUnit.SECONDS
);
~~~

The task prints “done” after it becomes eligible to run and a worker can serve it. When the task **completes normally**, **future.get()** returns **null**. If the Runnable throws an exception, Future.get() throws **ExecutionException** wrapping the cause. If the Future is cancelled, get() throws **CancellationException**.

### 3.2. Callable<V>: With a Return Value

~~~java
ScheduledFuture<Integer> future = scheduler.schedule(
        () -> 21 * 2,
        1, TimeUnit.SECONDS
);
int answer = future.get(); // 42 when the task completes successfully.
~~~

The snippet above is an illustration inside a method that has a scheduler variable and checked-exception handling. **get()** waits for the task to complete, not for exactly one second before returning. If the executor is overloaded, the total time from schedule to get() completing can be **longer than the delay**.

### 3.3. Delay Is Measured From Registration Time

The **delay** and **unit** parameters represent **relative time**, not a calendar timestamp by date/time. For example:

~~~java
scheduler.schedule(task, 500, TimeUnit.MILLISECONDS);
scheduler.schedule(task, 2, TimeUnit.SECONDS);
scheduler.schedule(task, 0, TimeUnit.MILLISECONDS);
~~~

These three lines illustrate registrations with a declared Runnable task. A **zero or negative delay** for one-shot schedule is interpreted as a request to execute **as soon as possible**; it is not a promise of synchronous execution on the submitting thread. The scheduler can still enqueue it.

**Do not confuse with periodic APIs:** **period** in scheduleAtFixedRate and the **delay between runs** in scheduleWithFixedDelay must be **positive**; zero or negative values for those parameters throw IllegalArgumentException. **initialDelay** in periodic scheduling can be 0.

## 4. ScheduledFuture, getDelay, and State Observation

**ScheduledFuture<V>** is both a **Future<V>** and a **Delayed**.

Notable APIs:

| API | Meaning |
| --- | --- |
| **get()** | Waits for completion and retrieves the result; may throw InterruptedException/ExecutionException/CancellationException |
| **get(timeout, unit)** | Waits at most the specified duration; may throw TimeoutException |
| **cancel(false)** | Attempts to cancel; does not request interrupting a running task |
| **cancel(true)** | Attempts to cancel; may request interrupting the executing thread |
| **isCancelled()** | Whether the Future was cancelled per contract |
| **isDone()** | Whether the Future has completed, including failure or cancellation, not necessarily success |
| **getDelay(unit)** | Estimated time until the task becomes eligible for execution |
| **compareTo(Delayed)** | Ordering of delayed tasks under the Delayed contract |

**getDelay() is not an exact countdown to when the task starts.** Once the task is past due while workers are busy, **getDelay() can be 0 or negative** even though the task has not started yet. After the Future completes, the delay value is also not a report of execution duration or latency.

**get(timeout)** limits how long the **caller waits on the Future**; it does not change the registered delay and **does not automatically cancel the task** on timeout. A caller may stop waiting while the worker still runs the task afterward.

### Three States to Keep Separate

~~~text
Scheduled -> not yet due -> due, waiting for worker -> running
                                                          |
                           +---------- completed ---------+
                           |               |
                           v               v
                        success        exception

Cancellation can happen before the task starts or while it is running.
~~~

**Future.isDone() = true** can result from success, failure, or cancellation. **isCancelled() = true** does not prove that all side effects have been reversed; cancellation is a Future state and requires cooperation from the task.

## 5. Example 1: Running a One-Shot Callable After a Delay

File **DelayedCallableDemo.java**:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class DelayedCallableDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(
                    () -> 21 * 2,
                    20, TimeUnit.MILLISECONDS
            );

            System.out.println("value = " + future.get());
            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DelayedCallableDemo.java
java DelayedCallableDemo
~~~

Stdout when the environment does not interrupt and the task completes normally:

~~~text
value = 42
done = true
cancelled = false
~~~

**Reasoning:**

1. The scheduler accepts the Callable and sets a relative trigger 20 ms later.
2. **future.get()** waits until the task executes and returns 42, even if the worker starts after the due time.
3. Once get() returns successfully, the Future is **done** and not cancelled.
4. The finally block requests shutdown so the worker does not keep the program alive after the scheduler is no longer needed.

Do not print an “elapsed = 20 ms” figure as required output: runtime overhead, clock resolution, and system load can cause measured elapsed time to vary.

### Runnable Whose Future Returns null on Completion

File **DelayedRunnableDemo.java**:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class DelayedRunnableDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        AtomicBoolean executed = new AtomicBoolean();

        try {
            ScheduledFuture<?> future = scheduler.schedule(
                    () -> executed.set(true),
                    10, TimeUnit.MILLISECONDS
            );

            Object value = future.get();

            System.out.println("runnable result = " + value);
            System.out.println("executed = " + executed.get());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 DelayedRunnableDemo.java
java DelayedRunnableDemo
~~~

Stdout:

~~~text
runnable result = null
executed = true
~~~

A Runnable task has no return value from run(), but **ScheduledFuture** still lets you wait for **completion** or receive errors. AtomicBoolean is an illustrative state-observation tool here; the completion semantics of Future already guarantee to main that actions before run() finishes have happened.

## 6. Choosing a Scheduler: Single Worker or Multiple Workers?

Two common factories:

~~~java
ScheduledExecutorService one =
        Executors.newSingleThreadScheduledExecutor();

ScheduledExecutorService many =
        Executors.newScheduledThreadPool(4);
~~~

This snippet uses imports from java.util.concurrent; in a real program you must shut down both executors according to their lifecycle.

| Criterion | Single-thread scheduled | Scheduled thread pool with N workers |
| --- | --- | --- |
| Concurrent running tasks | At most 1 | At most N |
| When a task is due while a worker is busy | Waits for the running task to finish | Can run on another idle worker |
| Two tasks becoming due together | Executed sequentially | Can execute in parallel |
| Sharing mutable state | Easy to establish single ownership if all accesses go through the executor | Requires appropriate atomics/locks/confinement |
| Long blocking task | Blocks all subsequent tasks | Using all N workers can block subsequent tasks |
| Delayed task queue | Can grow very large | Can still grow very large |
| Actual task completion order | Sequential on one worker | Not guaranteed to match submission order |

**newSingleThreadScheduledExecutor()** guarantees that no more than one task runs at a time; you should not assume **the same Thread object lives forever**. If the worker terminates abnormally, the executor may create a replacement worker. ThreadLocal is bound to a thread, not to the scheduler.

**newScheduledThreadPool(n)** uses **n core workers** on demand. With **ScheduledThreadPoolExecutor**, the delayed task queue is a **DelayedWorkQueue without a useful capacity limit for applying backpressure**. When all n workers are busy, due tasks still wait. Setting maximumPoolSize higher than core **does not produce scaling similar to a bounded ThreadPoolExecutor**, because the delayed queue is effectively unbounded.

### Do Not Treat “Scheduled” as “Job-Count Bounded”

If a producer registers many tasks with long delays every second, the scheduler can retain a large number of task objects in the queue. You need **admission control**, schedule limits, cancellation of unneeded schedules, and to consider **setRemoveOnCancelPolicy(true)** when using ScheduledThreadPoolExecutor so cancelled tasks are not retained in the queue for too long.

## 7. When a Task Is Due but No Worker Is Available

For example, a scheduler with only 1 worker:

~~~text
Time 0:
  Task A is running and blocking on I/O.

Time 100 ms:
  Task B becomes eligible to run.

Time 500 ms:
  Task A finishes; only now does the worker pick up B.

Result:
  B was scheduled for 100 ms later, but may actually start near 500 ms.
~~~

This is an illustrative diagram, not a timing bound guaranteed by the JDK.

Causes of post-due-time delay:

- All workers are busy executing other tasks, especially long blocking I/O.
- The CPU scheduler/JVM is busy, experiencing stop-the-world GC or high load.
- An earlier task holds a lock or waits on a resource that the new task also needs.
- Too many tasks in the queue become due at the same time.
- Shutdown/cancellation/exceptions change the scheduler's lifecycle state.
- Multiple application instances with independent schedules contend for a shared resource.

**ScheduledExecutorService is a tool for scheduling the earliest eligible run time, not a hard real-time scheduler.** If the business logic requires strict deadlines, you must design latency tracking, timeouts, and overdue handling explicitly.

### Trap: A Task Waiting on Another Task on the Same Single-Worker Scheduler

If task A runs on a single-thread scheduler and A calls schedule(task B, 0, ...) followed by **B.get()**, A occupies the worker while waiting for B. B cannot run because the only worker is busy with A: **thread-starvation deadlock**.

Do not write such dependency flows. Consider asynchronous composition or a different worker model if needed, and inspect the dependency graph before calling Future.get() inside a task.

## 8. Example 2: Cancelling a Queued Task Before Execution

**cancel(false)** is suitable when you want to prevent a task that has not started yet, without requesting an interrupt on a running task. To keep the example independent of “cancelling before 100 ms elapses”, we **intentionally hold the single worker** with a latch, place the second task into the queue, and cancel it while it is guaranteed to have no worker.

File **CancelDelayedTaskDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class CancelDelayedTaskDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        AtomicBoolean ran = new AtomicBoolean();

        try {
            Future<?> blocker = scheduler.submit(() -> {
                entered.countDown();
                try {
                    release.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                }
            });

            entered.await(); // The single worker is now held.

            ScheduledFuture<?> delayed = scheduler.schedule(
                    () -> ran.set(true),
                    0, TimeUnit.MILLISECONDS
            );

            boolean cancelled = delayed.cancel(false);

            release.countDown();
            blocker.get();

            scheduler.shutdown();
            scheduler.awaitTermination(5, TimeUnit.SECONDS);

            System.out.println("cancel accepted = " + cancelled);
            System.out.println("task ran = " + ran.get());
            System.out.println("cancelled = " + delayed.isCancelled());
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 CancelDelayedTaskDemo.java
java CancelDelayedTaskDemo
~~~

Stdout:

~~~text
cancel accepted = true
task ran = false
cancelled = true
~~~

**Why is the outcome deterministic?**

1. entered.await() confirms that **blocker has started** and is holding the single worker.
2. The delayed task has delay=0, but cannot run because the worker is still waiting on the latch.
3. Main calls cancel(false) while delayed is still pending, so cancellation succeeds.
4. When release opens, blocker finishes and the worker does not execute the cancelled task.
5. A cancelled Future has isCancelled() true; **calling delayed.get() would throw CancellationException**.

Be careful in production: cancel(false) can return false if the task has already completed or was already cancelled; returning true does not mean side effects from other tasks are rolled back. Once a task has started, **cancel(false) does not request an interrupt**, and the running task may continue executing.

## 9. cancel(true), Interruption, and Cleanup

**ScheduledFuture.cancel(true)** attempts to cancel the Future and **may interrupt the running thread** if the task has already started. It does not forcibly terminate Java code safely. Stopping depends on whether the task checks its interrupt status, uses interruptible blocking APIs, and cleans up resources.

Cooperative task pattern:

~~~java
// Illustration of a Runnable body, not a standalone file.
Runnable job = () -> {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            // Process short batches without holding locks for long periods.
            processBatch();
        }
    } finally {
        releaseOwnedResources();
    }
};
~~~

Here **processBatch()** and **releaseOwnedResources()** are placeholder methods. If processBatch calls a blocking API that throws InterruptedException, handle it by propagating or restoring the interrupt flag and exiting per your protocol.

**A critical point:** cancel(true) can transition the Future to cancelled **before the task's code actually finishes**. Therefore, do not infer that “Future cancelled” means side effects have stopped or resources have been cleaned up. If waiting for cleanup matters, use a dedicated completion protocol.

If holding a Semaphore permit, ReentrantLock, or file handle, the task must use **try/finally** to release ownership properly. Never rely on the task always reaching its final line.

## 10. Example 3: Future.get(timeout) Does Not Cancel the Task

We create a task that **has started but is waiting on an unreleased latch**, then call get with a timeout. Because the latch is not released yet, the Future is guaranteed **not to have completed** during the wait; after the timeout, main releases the latch and waits to retrieve the final value.

File **ScheduledFutureTimeoutDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class ScheduledFutureTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(() -> {
                entered.countDown();
                release.await();
                return 42;
            }, 0, TimeUnit.MILLISECONDS);

            entered.await();

            boolean timedOut = false;
            try {
                future.get(10, TimeUnit.MILLISECONDS);
            } catch (TimeoutException ex) {
                timedOut = true;
            }

            release.countDown();
            int value = future.get();

            System.out.println("wait timed out = " + timedOut);
            System.out.println("final value = " + value);
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            release.countDown();
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledFutureTimeoutDemo.java
java ScheduledFutureTimeoutDemo
~~~

Stdout:

~~~text
wait timed out = true
final value = 42
cancelled = false
~~~

**Analysis:**

- When main calls get(10ms), the worker has already entered the Callable and is waiting on **release**.
- Because main **has not released the latch**, the Future cannot complete normally; get times out and throws TimeoutException.
- The timeout only makes **the caller stop waiting**; it does not call cancel().
- Main opens release, the task returns 42, and the next Future.get() receives the result.
- isCancelled() is false because the Future was never cancelled.

Do not turn 10 ms into a scheduler speed benchmark: we only use it to demonstrate a **verifiable timeout path**, not to imply tasks always start or finish within 10 ms.

## 11. Exceptions in Scheduled Tasks

If a Callable or Runnable throws an unchecked exception, **ScheduledFuture.get()** for a one-shot task throws **ExecutionException**, and **getCause()** provides the underlying cause. An exception does not automatically retry the task.

File **ScheduledFailureDemo.java**:

~~~java
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

public class ScheduledFailureDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(
                    () -> {
                        throw new IllegalStateException("invalid state");
                    },
                    0, TimeUnit.MILLISECONDS
            );

            try {
                future.get();
            } catch (ExecutionException ex) {
                System.out.println(
                    "cause = " + ex.getCause().getClass().getSimpleName()
                );
            }

            System.out.println("done = " + future.isDone());
            System.out.println("cancelled = " + future.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledFailureDemo.java
java ScheduledFailureDemo
~~~

Stdout:

~~~text
cause = IllegalStateException
done = true
cancelled = false
~~~

**Difference from rejection:** if the scheduler has already shut down or rejects the submission, **schedule()** can throw **RejectedExecutionException directly on the submitting thread**, without returning a valid Future. If the task was accepted and then throws during execution, the failure is observed via Future.get().

**Do not ignore the Future** of an important task. An exception in a scheduled task may not surface as an exception on the submitting thread; you must have error-observation channels, metrics, and an appropriate retry policy.

## 12. How One-Shot and Periodic Schedules Differ

ScheduledExecutorService also provides two repeating execution methods:

~~~java
// Illustration:
scheduler.scheduleAtFixedRate(
        task, 0, 100, TimeUnit.MILLISECONDS
);

scheduler.scheduleWithFixedDelay(
        task, 0, 100, TimeUnit.MILLISECONDS
);
~~~

These snippets illustrate the parameters; task is a declared Runnable. Even though the method names all start with schedule, **periodic semantics differ from one-shot schedule()**.

### scheduleAtFixedRate: Targets Periodic Marks

With initialDelay=0 and period=100ms, the intended marks are roughly:

~~~text
t0, t0 + 100ms, t0 + 200ms, t0 + 300ms, ...
~~~

If a previous run takes a long time, the next run may start **late**. Under the ScheduledThreadPoolExecutor contract, successive executions **of the same periodic task do not overlap**, even if the executor has multiple workers. If the task runs longer than the period, subsequent runs may execute back-to-back without the intended gap.

### scheduleWithFixedDelay: Waits After the Previous Run Ends

With delay=100ms:

~~~text
Run 1 finishes
    |
    +-- wait 100ms --> Run 2 starts
                           |
                      Run 2 finishes
                           |
                           +-- wait 100ms --> Run 3 ...
~~~

Fixed-delay is usually easier to reason about for conditional polling or tasks that should only restart a set interval after the previous run finishes. It does not try to stay aligned to fixed marks from the initial start time.

### Comparison Table

| Intent | API | Characteristics |
| --- | --- | --- |
| Run **once** after a delay | **schedule(task, delay, unit)** | Future completes when the task finishes, fails, or is cancelled |
| Run repeatedly on a cadence from the initial mark | **scheduleAtFixedRate** | Ideal marks spaced by period; may be delayed, never overlaps the same periodic task |
| Run repeatedly after a pause from the previous finish | **scheduleWithFixedDelay** | Fixed pause between the end of one run and the start of the next |
| Wait for an exact **local wall-clock hour** each day | Recompute next target by date/zone | Do not blindly use period=24h due to DST/clock shifts |
| Work that must survive JVM restarts | Requires persistence and a different protocol | ScheduledExecutorService only holds schedules in-process |

**A periodic task that throws an exception** causes subsequent executions to be **suppressed** per contract, rather than retrying indefinitely. A periodic task's Future **does not complete normally** after a single tick: it represents the entire repeating sequence and only becomes done when cancelled or terminated abnormally. Do not call periodicFuture.get() indefinitely expecting it to return after the first tick.

## 13. Example 4: Stopping a Periodic Schedule After Three Runs

File **PeriodicStopDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class PeriodicStopDemo {
    public static void main(String[] args) throws Exception {
        ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();

        AtomicInteger runs = new AtomicInteger();
        CountDownLatch threeRuns = new CountDownLatch(3);

        try {
            ScheduledFuture<?> periodic =
                    scheduler.scheduleWithFixedDelay(
                            () -> {
                                runs.incrementAndGet();
                                threeRuns.countDown();
                            },
                            0, 10, TimeUnit.MILLISECONDS
                    );

            threeRuns.await();
            boolean stopped = periodic.cancel(false);

            System.out.println("at least three = " + (runs.get() >= 3));
            System.out.println("cancelled = " + stopped);
            System.out.println("future cancelled = "
                    + periodic.isCancelled());
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 PeriodicStopDemo.java
java PeriodicStopDemo
~~~

Stdout:

~~~text
at least three = true
cancelled = true
future cancelled = true
~~~

threeRuns.await() ensures main **does not cancel before reaching three runs**; while main is about to cancel, a subsequent run *might* already execute, so **do not print runs == 3 as a constant**. This is an important principle for concurrency testing: assert **guaranteed invariants**, not incidental thread interleavings.

A **periodic future** does not complete normally on its own. cancel(false) cancels future executions; once cancellation succeeds, isCancelled() is true. Cancellation does not mean side effects from the first three runs are undone.

## 14. Two Special Scheduler Shutdown Policies

**ScheduledThreadPoolExecutor** is the underlying implementation behind the JDK scheduler factories. When used directly, it exposes policies controlling tasks already registered before shutdown.

| Policy | Default Value | Meaning |
| --- | --- | --- |
| **getExecuteExistingDelayedTasksAfterShutdownPolicy()** | **true** | **One-shot tasks scheduled before shutdown** can still run after shutdown when they become due |
| **getContinueExistingPeriodicTasksAfterShutdownPolicy()** | **false** | Future periodic executions do not continue after shutdown |
| **getRemoveOnCancelPolicy()** | **false** | Cancelled tasks are not necessarily removed immediately from the waiting queue |

Corresponding setters:

~~~java
// Illustration with an already-created ScheduledThreadPoolExecutor scheduler:
scheduler.setExecuteExistingDelayedTasksAfterShutdownPolicy(false);
scheduler.setContinueExistingPeriodicTasksAfterShutdownPolicy(false);
scheduler.setRemoveOnCancelPolicy(true);
~~~

**Do not confuse shutdown with cancelling all existing schedules.** With the default **execute-existing-delayed=true**, if you schedule a task for 1 day from now and call shutdown(), the executor may retain resources waiting for that task to become due instead of terminating immediately.

### shutdown() vs. shutdownNow()

- **shutdown()** stops accepting new schedules. Already-registered tasks are handled according to the policies above; the method **does not block waiting for completion**.
- **shutdownNow()** attempts to interrupt running tasks and returns tasks that have not started; it does not guarantee running tasks stop immediately.
- **awaitTermination(timeout, unit)** waits for the executor to terminate and returns a boolean. If false, you must not assume cleanup is finished.
- Calling schedule after shutdown can throw **RejectedExecutionException**.
- If periodic-continue=true is configured, periodic tasks can keep running and prevent the executor from terminating until cancelled, shutdownNow, or the policy is changed.

### Example 5: One-Shot Delayed Task Still Runs After Default Shutdown

File **ScheduledShutdownDemo.java**:

~~~java
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class ScheduledShutdownDemo {
    public static void main(String[] args) throws Exception {
        ScheduledThreadPoolExecutor scheduler =
                new ScheduledThreadPoolExecutor(1);

        try {
            ScheduledFuture<Integer> future = scheduler.schedule(
                    () -> 42,
                    20, TimeUnit.MILLISECONDS
            );

            scheduler.shutdown(); // By default, still allows delayed one-shot tasks to run.
            System.out.println("value after shutdown = " + future.get());
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        } finally {
            scheduler.shutdownNow();
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ScheduledShutdownDemo.java
java ScheduledShutdownDemo
~~~

Stdout:

~~~text
value after shutdown = 42
~~~

The task was **registered before shutdown()**, and the default policy allows one-shot tasks to continue running after the executor stops accepting new tasks. Therefore future.get() still returns 42. The 20ms interval is the minimum delay to become eligible, not an execution SLA.

If you change it to **setExecuteExistingDelayedTasksAfterShutdownPolicy(false)** before shutdown, one-shot tasks that are not yet due will be cancelled per policy instead of remaining until execution. **You must explicitly decide what the application wants:** when shutting down, should existing schedules finish, be cancelled, or be persisted for recovery?

## 15. Cancelled Tasks May Remain in the Queue

For **ScheduledThreadPoolExecutor**, a cancelled task **is not necessarily removed from the queue immediately** by default. A task scheduled hours in advance and cancelled after a few seconds may stay in the delayed queue until its due time; in large numbers, this can retain memory unnecessarily.

When instantiating ScheduledThreadPoolExecutor directly, you can configure:

~~~java
// Illustrative code:
ScheduledThreadPoolExecutor scheduler =
        new ScheduledThreadPoolExecutor(2);
scheduler.setRemoveOnCancelPolicy(true);
~~~

This policy removes cancelled tasks from the queue upon cancellation per the executor's contract, reducing retention and making schedule-count management easier. It **does not forcibly stop already-running tasks** and does not replace capacity/admission design.

**Do not use queue.size() as a check-then-schedule admission controller:** between checking and submitting, other threads can register tasks and the count can change immediately. If you must limit “at most K active schedules”, use admission control with atomic primitives or permits, returning the permit on **every terminal state** under a proven protocol.

### When to Use ScheduledThreadPoolExecutor Directly?

Use it when you need policy setters, a custom thread factory, a rejection handler, or specific configuration/diagnostics. For simple one-shot delays, **Executors.newSingleThreadScheduledExecutor()** or **newScheduledThreadPool(n)** is clear enough. Avoid casting a factory-returned executor to ScheduledThreadPoolExecutor: a wrapper may hide the concrete implementation, and the factory's return type does not promise such a cast is valid.

## 16. Scheduling by Wall-Clock Time

**schedule(delay, unit)** takes a **relative delay**. If a requirement says “run at 09:00 in a specific time zone”, you must compute the distance between **now** and the **target instant**.

Illustrative example inside a Java program that already declares a scheduler:

~~~java
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.TimeUnit;

// target is an already-determined Instant:
long delayMillis = Math.max(
        0L,
        Duration.between(Instant.now(), target).toMillis()
);
scheduler.schedule(task, delayMillis, TimeUnit.MILLISECONDS);
~~~

This is an **illustrative code snippet**, not a Java file with main(): you need to declare **target**, **task**, and **scheduler**, and add the proper imports to your class.

### Easily Overlooked Factors

- **Instant** is an absolute point in time; **LocalDateTime** carries no time zone and by itself does not uniquely identify a global instant.
- If the user wants “09:00 in Asia/Ho_Chi_Minh”, you must use the corresponding **ZoneId** and compute the appropriate **ZonedDateTime**.
- Once the delay is computed, the scheduler only holds a **relative delay**. If the system clock is adjusted forward or backward, the scheduler does not reinterpret the wall-clock schedule.
- A repeating “09:00 every day” schedule must compute **the next day with the zone**, rather than naively repeating period=24 HOURS across time zones with DST.
- If target is already in the past, **Math.max(0, ...)** above submits the task to run as soon as possible, whereas your business logic may want to **reject overdue schedules**; decide according to your contract.
- Large durations or conversions can overflow; for far-future or complex schedules, validate the interval and use a suitable persistent scheduler.
- Time-zone/calendar rule changes and daylight saving transitions can cause local times to repeat or not exist in some regions. Define clear behavior for those cases.

### “24-Hour Delay” Is Not “Same Time Tomorrow”

In a region with daylight saving time, the interval between the same local time on two consecutive days can be **23 hours or 25 hours**. Using TimeUnit.DAYS only expresses a relative duration in time units; it has no knowledge of local calendars.

For calendar-based schedules, compute the next run from **ZonedDateTime**; only compute the next target after the current run finishes, while also handling downtime/restarts. That is a different problem from a one-shot ScheduledFuture.

## 17. Delayed Scheduling Is Not Durable Job Persistence

**ScheduledExecutorService keeps schedules in JVM memory**. If the process crashes, the server restarts, the JVM is killed, or the deployment changes, pending schedules are generally **not recovered automatically**.

If a workflow must guarantee:

- No lost schedules even if a process dies.
- Multiple JVMs do not execute the same schedule twice.
- Durable retry and backoff state.
- At-least-once execution or explicit acknowledgment.
- Auditing, replay, retry limits, or dead-letter policies.

...then you must design a **persistent job store/queue**, idempotency, and coordination in storage shared across processes. An in-JVM Java executor does not provide system-wide exactly-once execution on its own.

### Scheduling Notifications or Payments

Suppose a program schedules a task to send an email after 10 minutes. If the user cancels before the due time, calling future.cancel(false) can prevent the pending task. However, if the email has already started sending, cancellation cannot retract it. If the JVM restarts, the old future will not come back to life either.

For **financial operations or irreversible side effects**, persist state, use idempotency keys, handle duplicates, and implement a confirmation protocol; do not rely on ScheduledFuture as the source of truth.

## 18. Timeouts, Deadlines, and Cancellation Authority

**ScheduledExecutorService** governs when a task becomes eligible to run, while **Future.get(timeout)** governs how long the caller waits.

| Scenario | Tool | Meaning |
| --- | --- | --- |
| Want task to start no earlier than 5 seconds after registration | schedule(task, 5, SECONDS) | Delay before the task becomes eligible |
| Caller only has 1 second to wait for the result | future.get(1, SECONDS) | Caller may time out; task keeps running |
| No longer want a pending task to run | future.cancel(false) | Attempts to cancel; does not request interrupting a worker |
| Want to request interrupting a running task | future.cancel(true) | Requests cooperative cancellation/interrupt; does not roll back |
| Entire operation has a deadline | Compute remaining time for each step | Do not re-add the full timeout budget to each step |
| Want to know if the scheduler has actually stopped | awaitTermination(timeout, unit) | Observes lifecycle state after shutdown |

When performing multiple waits under a shared deadline, compute **remaining time** using the monotonic clock **System.nanoTime()** (with overflow-safe arithmetic), rather than granting the full budget again to every API call.

**Do not use Thread.sleep(delay) instead of schedule** when the goal is to “register work for a worker to run later” while the caller moves on: sleep blocks the calling thread itself and does not provide equivalent ScheduledFuture/cancel/queue semantics.

## 19. Common Design Mistakes

| Mistake | Problem | Fix |
| --- | --- | --- |
| Assuming schedule(delay=100ms) guarantees running at exactly 100ms | Execution still depends on workers and the OS scheduler | Frame it as “eligible after delay”; measure lateness |
| Blocking a single worker with long I/O | Subsequent due tasks are delayed | Do not block workers for long; choose pool size and isolate workloads |
| Using schedule() instead of a durable timer across restarts | Schedules are lost when the JVM dies | Use a persistent job store if durability is required |
| Using scheduleAtFixedRate for work intended to run once | Task repeats unexpectedly | Use schedule() |
| Calling periodic future.get() to wait for the first tick | get may never complete normally | Use CountDownLatch/Condition or a dedicated signal |
| Believing shutdown() immediately cancels all delayed tasks | By default, existing one-shot delayed tasks still run | Configure policies to match lifecycle requirements |
| Cancelling many far-future tasks and ignoring the queue | Cancelled tasks are retained for a long time | setRemoveOnCancelPolicy(true), cap schedule counts |
| Calling cancel(true) and assuming I/O was rolled back | Future cancellation does not undo side effects | Use cooperative cancellation and idempotency |
| Ignoring ExecutionException from Future | Task failures go unnoticed | Collect Futures and handle the cause |
| Timing out get() and assuming the task stopped | The task may still be running | Cancel explicitly per policy and track actual completion |
| Using wall-clock time to measure wait intervals | System clock can be adjusted | Use nanoTime for elapsed time/deadlines |
| Using fixed-rate 24h for daily 09:00 in a DST zone | Local time can shift | Compute ZonedDateTime for each day |
| Using a single worker and waiting on a child task in the same scheduler | Thread-starvation deadlock | Do not block waiting for a task that needs the same worker |
| Allowing unbounded delayed task submissions | Uncontrolled queue/memory growth | Apply admission control, limits, and telemetry |
| Casting a factory scheduler to ScheduledThreadPoolExecutor | Wrapper may not have that concrete type | Instantiate ScheduledThreadPoolExecutor directly if policies are needed |
| Using ThreadLocal for long-lived schedule state | Workers can be replaced and threads reused across tasks | Store state with explicit lifecycle and clean up ThreadLocal |
| Seeing Future.isDone() and assuming business success | Done includes failure and cancellation | Check get()/isCancelled() and business status |

## 20. Testing Delayed Schedules Without Relying on Random Timing

Writing proper tests for scheduling has two parts: **timing contracts** and **state contracts**.

**What to test:**

1. **One-shot Callable** returns the expected result via Future.get().
2. **One-shot Runnable** completes and Future.get() returns null.
3. **Cancel before start**: hold the worker with a latch, enqueue a task, call cancel(false), and verify the task did not run.
4. **Caller timeout**: hold the Callable on a latch, call Future.get(timeout), and verify the task can still complete after the caller releases the latch.
5. **Task throwing an exception**: Future.get() throws ExecutionException with the expected cause.
6. **Periodic scheduling**: use a CountDownLatch to count a few ticks and then cancel; do not assert an exact tick count since main can be delayed by the scheduler.
7. **Shutdown policies**: schedule before shutdown and verify delayed tasks run or are cancelled according to the configured policy.
8. **Overload**: intentionally keep all workers busy and verify delayed tasks only run once a worker is free; check memory/backlog if many schedules are submitted.
9. **Calendar schedules**: test date rollovers, time zones, and DST cases if the system requires them.
10. **Completion/side effects**: distinguish “task ran”, “retried”, “external operation committed”, and “Future cancelled”.

**Do not test with assumptions like:** “after Thread.sleep(100), the task has run.” That may pass on one machine and fail under load. Prefer latches, Futures, state notifications, and invariants. If you must measure time, use environment-appropriate thresholds and do not turn exact timer numbers into requirements the API does not promise.

## 21. Production Readiness Checklist

**Design:**

- [ ] Is the work **one-shot** or **periodic**? Did you choose the right API?
- [ ] Is it a relative delay or a local wall-clock schedule? Is the time zone specified?
- [ ] Do you need results, exceptions, cancellation, or deadlines? Are you keeping the ScheduledFuture?
- [ ] Must schedules survive restarts or multi-JVM deployments? If so, is there a persistent coordinator?
- [ ] Can the task be re-executed? Is idempotency enforced for external side effects?

**Load and Resources:**

- [ ] Is the worker count appropriate for CPU-bound/blocking I/O work and expected latency?
- [ ] Are long tasks occupying workers and making subsequent tasks overdue?
- [ ] Is the number of delayed tasks bounded, or is queue growth monitored?
- [ ] Is cancelled-task retention handled via removeOnCancelPolicy when needed?
- [ ] Do you track metrics for scheduled, started, completed, failed, cancelled, overdue, and queue size?

**Lifecycle:**

- [ ] Have you decided whether existing delayed tasks run or are cancelled on shutdown?
- [ ] Have you decided whether periodic tasks continue after shutdown?
- [ ] Are shutdown/awaitTermination and an appropriate fallback in place?
- [ ] Is RejectedExecutionException handled if producers submit after shutdown?
- [ ] If the caller times out or cancels the Future, does the task clean up cooperatively?
- [ ] Are you avoiding holding locks or occupying a worker to wait on another task in the same executor?

## 22. Self-Check Questions

**1. Does schedule(task, 500, MILLISECONDS) guarantee the task starts at exactly 500 ms?**  
No. The task becomes **eligible** after the delay; actual execution time depends on workers and the scheduler.

**2. Does ScheduledFuture.getDelay() == -100 ms mean the task has already finished?**  
No. The task may be past due while no worker is free yet.

**3. With schedule(Runnable, ...), what does get() return on success?**  
**null**, because Runnable does not return V via call().

**4. If Future.get(timeout) throws TimeoutException, does it automatically cancel the schedule?**  
No. Only the caller stops waiting; the task can still continue.

**5. How do cancel(false) and cancel(true) differ?**  
cancel(false) does not request interrupting a running task; cancel(true) may request an interrupt, though it does not force a rollback of side effects.

**6. Can a single periodic task run twice concurrently in a ScheduledThreadPoolExecutor with four workers?**  
Executions **of the same periodic task** do not overlap per contract; different periodic tasks can run concurrently.

**7. Why can periodicFuture.get() wait forever?**  
Because the Future represents the entire repeating sequence and does not complete normally after one tick. It must be cancelled or terminate abnormally to reach a terminal state.

**8. Does shutdown() cancel previously scheduled one-shot tasks that are not yet due by default?**  
No. ScheduledThreadPoolExecutor allows existing delayed one-shot tasks to execute after shutdown by default.

**9. Does using scheduleAtFixedRate with period=24 HOURS schedule at 09:00 local time every day in all time zones?**  
No. Local wall-clock times can shift offsets due to DST; you must recompute the corresponding calendar target.

**10. When can a single-thread scheduled executor deadlock?**  
When a running task occupies the only worker and waits on the Future of another task queued in the same executor.

**11. Can you rely on setRemoveOnCancelPolicy(true) to be sure a task has run?**  
No. It only controls removing **cancelled** tasks from the queue upon cancellation; it does not prove execution.

**12. Does ScheduledExecutorService guarantee schedules survive a JVM restart?**  
No. Schedules live in process memory; separate persistence/coordination is needed when required by the domain.

## 23. Summary

**ScheduledExecutorService** is the JDK tool for **registering work to run after a relative delay** and tracking it with **ScheduledFuture**. The **schedule()** methods serve **one-shot** tasks; the periodic methods address a different goal of repeating at a **fixed rate** or with a **fixed delay**.

The most important distinctions are:

- **Becoming due** does not mean **having started execution**.
- **Future.get(timeout) timing out** does not mean **the task was cancelled**.
- **Future.cancel()** does not mean **all side effects were undone**.
- **shutdown()** does not necessarily **cancel all registered schedules**.
- **An in-JVM scheduler** is not equivalent to **a durable, wall-clock-accurate, deduplicated multi-process scheduling service**.

Choose an appropriate worker count, bound pending schedules, retain and observe Futures, understand cancellation/shutdown policies, design wall-clock schedules with explicit time zones, and test using **invariants and blocking primitives** rather than expecting exact sleep timings.
