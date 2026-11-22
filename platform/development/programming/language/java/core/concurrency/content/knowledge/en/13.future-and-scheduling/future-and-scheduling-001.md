# Future in Java: get(), isDone(), isCancelled()

## 1. What does Future represent?

In Java Concurrency, **java.util.concurrent.Future<V>** is an object that represents the result of an asynchronous task that may complete in the future. When submitting a Callable<V> or Runnable to ExecutorService.submit(...), the program receives a Future to track status, wait for the result, or request cancellation of the work.

Future is not synonymous with a thread. A Future represents **a computation/task**; ExecutorService decides which worker runs the task and when. Future also does not automatically guarantee that the task will run successfully, will not block, or can be stopped immediately.

Three core methods:

| Method | Main meaning | Can block? |
|---|---|---|
| **V get()** | Waits for the task to complete and returns the result, or throws the corresponding exception | **Yes**, may wait indefinitely |
| **boolean isDone()** | Checks whether the Future is in a completed state | **No** |
| **boolean isCancelled()** | Checks whether the Future was successfully cancelled | **No** |

Future also has **cancel(boolean mayInterruptIfRunning)** to request cancellation and **get(long timeout, TimeUnit unit)** to limit the wait time. You need to understand these methods together to use get/isDone/isCancelled properly.

### Result of submit(...)

~~~java
ExecutorService executor = Executors.newSingleThreadExecutor();
try {
    Future<Integer> result = executor.submit(() -> 6 * 7);
    int answer = result.get(); // 42; may block if the task is not yet complete.
} finally {
    executor.shutdown();
}
~~~

This is an **illustrative snippet** inside a method that declares or handles InterruptedException/ExecutionException, not a standalone Java class. In the example above, the computation may have already finished before calling get; being asynchronous does not force get to wait for a long time.

**Notes on Callable and Runnable:**

- **submit(Callable<V>):** Future<V>.get() returns the value V if successful.
- **submit(Runnable):** Future<?>.get() returns **null** when the Runnable completes normally.
- **submit(Runnable, V result):** get() returns the provided result value if the Runnable completes normally.
- With Executor.execute(Runnable), the return type is void: there is no Future from the execute call on which to use get/isDone/isCancelled.

## 2. Understanding the Future lifecycle and states

A Future can be waiting in a queue, currently running, or already completed. When completed, the outcome can be **success**, **failure due to an exception**, or **successful cancellation**.

~~~text
                         submit task
                              |
                         Incomplete
                   (queued or running)
                        /      |      \
                       /       |       \
                  success   failure   cancelled
                     |         |          |
                  done=true  done=true  done=true
                  cancel=false cancel=false cancel=true
~~~

Behavior table of Future after observing its state:

| State | isDone() | isCancelled() | get() |
|---|---|---|---|
| Incomplete (queued/running) | false | false | May wait until completion |
| Completed **successfully** | true | false | Returns the result value |
| Completed **with an exception** | true | false | Throws ExecutionException containing the cause |
| Cancelled **successfully** | true | true | Throws CancellationException |

**Crucial conclusion:** **isDone() == true does not mean the task succeeded.** It only states that the computation has completed according to the Future contract, including cases of failure or cancellation. isCancelled() == false also **does not confirm success**: the task may not be finished yet or may have failed.

These states are snapshots at the **time of inspection**. A task may finish right after an isDone() call returns false. Do not combine multiple checks into an assumption about an immutable state while other threads are still active.

## 3. get(): waiting for the result and handling exceptions

With **Future<V>.get()**, the thread **calling get** may be blocked until the computation completes; the worker executing the task is another thread managed by the executor. If the work completed beforehand, get retrieves the result immediately. Several scenarios:

1. **Normal completion:** get() returns V; for a Runnable without a value, it returns null.
2. **Task throws an error:** get() throws **ExecutionException**; call getCause() to access the original error from the task.
3. **Future was successfully cancelled:** get() throws **CancellationException** (an unchecked exception).
4. **Waiting thread is interrupted:** get() throws **InterruptedException**; interrupting the thread calling get does not automatically mean the Future is cancelled.
5. **Task does not finish:** get() has no default wait timeout; if there is no exit path, the caller may be blocked indefinitely.

**get(timeout, unit)** waits at most for the requested duration and may throw **TimeoutException** if there is no result yet. A timeout **does not automatically cancel the Future**: the task may still be running and get() in a subsequent call may still return a successful result.

The two overloads declare different checked exceptions:

~~~java
V value = future.get(); // InterruptedException, ExecutionException
V value = future.get(2, TimeUnit.SECONDS);
// InterruptedException, ExecutionException, TimeoutException
~~~

The lines above only illustrate the signatures in the context of Future<V> and require handling/declaring exceptions. CancellationException can still occur in both overloads.

### Do not mask the root error

If the task throws IllegalStateException("bad input"), the get() call on the caller throws ExecutionException. Inside catch (ExecutionException ex), **ex.getCause()** is the actual reason the task failed. Do not catch Exception and treat every case as a timeout or return a default result, because that will hide processing errors and corrupted data.

### Interruption is different from cancellation

When the caller is interrupted while waiting on get(), get may throw InterruptedException. The caller should **propagate the exception** or, if handling it locally without propagating, usually restore the interrupt flag via Thread.currentThread().interrupt() so upper layers know an interrupt was requested. Restoring the interrupt flag is not equivalent to future.cancel(true), and does not guarantee that the worker-side task stops.

## 4. Java 17 example: checking before and after completion

Use CountDownLatch to control the exact timing of observation. The task signals that it has started and then waits for a signal; main checks isDone()/isCancelled() when the task is **guaranteed not to have finished**, then unblocks it and reads the result. This example avoids depending on CPU speed to demonstrate states.

Save the file **FutureLifecycleDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureLifecycleDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<String> future = executor.submit(() -> {
                started.countDown();
                release.await();
                return "OK";
            });

            started.await();
            System.out.println("before: done=" + future.isDone()
                    + ", cancelled=" + future.isCancelled());

            release.countDown();
            System.out.println("get=" + future.get());
            System.out.println("after: done=" + future.isDone()
                    + ", cancelled=" + future.isCancelled());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac FutureLifecycleDemo.java
java FutureLifecycleDemo
~~~

Deterministic stdout:

~~~text
before: done=false, cancelled=false
get=OK
after: done=true, cancelled=false
~~~

At the point of printing the first line, the worker is waiting on the release latch and therefore cannot complete yet. After release.countDown(), get() synchronizes with the task's result; because get has returned normally, isDone is true and isCancelled is false on the last line.

**Memory relationship:** according to the Future contract, actions taken by the asynchronous computation **happen-before** actions in another thread that follow the return of the corresponding Future.get(). Therefore, get() not only retrieves the value but also provides an important synchronization point for data writes performed by the task. This does not make every access to shared data before get thread-safe; concurrent reads/writes prior to the synchronization point still require appropriate synchronization rules.

## 5. isDone(): knowing it is finished, not whether it finished well or badly

**isDone()** is a non-blocking check. When false, the task may not have started yet or is still running. When true, the computation has completed normally, failed, or been cancelled.

Proper usage:

- Monitoring status in a UI/metrics when a snapshot status is needed.
- Calling get() only when you want to retrieve the result or error; if isDone() is already true, get() does not need to wait for the computation to complete (but may still throw ExecutionException/CancellationException).
- Do not use a while (!future.isDone()) {} loop to **busy-spin**: it wastes CPU unnecessarily. If you simply want to wait, call get() or get(timeout,...); if you want to react as each task completes, consider CompletionService or an appropriate completion model.

**isDone true while get throws an error** is normal behavior when a task fails. Therefore, the pattern if (future.isDone()) { return future.get(); } is not a way to skip try/catch. It can only avoid waiting when the computation is still pending; errors still must be handled.

**A long-running task does not mean Future is wrong.** isDone remains false while the task is processing or waiting on a dependency. You should measure task duration, queue wait, lock contention, and I/O latency before concluding that a task is hung.

## 6. get(timeout, unit) and task failure: verification example

This example creates a task that waits on a latch to deterministically verify a timeout, then releases the latch to retrieve the result. It also submits a task that intentionally throws an error to observe ExecutionException. It does not use sleep to create fragile timing.

Save the file **FutureTimeoutFailureDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class FutureTimeoutFailureDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newFixedThreadPool(2);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        try {
            Future<Integer> slow = executor.submit(() -> {
                started.countDown();
                release.await();
                return 7;
            });

            started.await();
            try {
                slow.get(20, TimeUnit.MILLISECONDS);
            } catch (TimeoutException timeout) {
                System.out.println("timeout, still pending=" + !slow.isDone());
            }

            // A timeout on the caller does not cancel the task.
            release.countDown();
            System.out.println("slow result=" + slow.get());

            Future<Integer> failed = executor.submit(() -> {
                throw new IllegalStateException("demo failure");
            });

            try {
                failed.get();
            } catch (ExecutionException failure) {
                System.out.println("failure cause="
                        + failure.getCause().getClass().getSimpleName());
            }
            System.out.println("failed isDone=" + failed.isDone());
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

Run commands:

~~~bash
javac FutureTimeoutFailureDemo.java
java FutureTimeoutFailureDemo
~~~

Stdout:

~~~text
timeout, still pending=true
slow result=7
failure cause=IllegalStateException
failed isDone=true
~~~

First, slow is guaranteed to still be waiting on the latch, so get with a 20 ms timeout throws TimeoutException and isDone remains false. After opening the latch, the next get returns 7. The failed task throws IllegalStateException; get wraps the error in ExecutionException, while isDone is true because the computation has ended.

**In practice upon timeout:** depending on business logic, the caller can retry, cancel the task, return an error, or keep waiting; you must choose explicitly. If a timed-out request no longer needs the result, consider future.cancel(true) and deadline/cancellation mechanisms for downstream I/O as well. Do not blindly retry multiple times while the old task is still running, as that can multiply load on the system.

## 7. isCancelled(): checking cancellation outcome and understanding cancel(...)

**isCancelled()** is true only if the Future **was successfully cancelled before completing normally**. Wanting to cancel does not mean isCancelled is true; if the task has already finished before cancel, cancel typically returns false and isCancelled remains false.

The method **cancel(boolean mayInterruptIfRunning)** returns a boolean indicating whether the cancellation request succeeded according to the Future contract:

- **cancel(false):** attempts to cancel **without sending an interrupt to the running thread**. A running task may still continue executing its body; however, the Future has transitioned to the cancelled state, and get() will throw CancellationException if cancel succeeded.
- **cancel(true):** if the task is running, the implementation may interrupt the executing worker to ask the task to stop. An interrupt is only a cooperative signal; code that does not check for interruption or non-interruptible I/O may still keep running.
- **cancel(...) returns false:** cancellation did not succeed, for example because the computation has already completed or the Future cannot be cancelled. Do not assume the result is a success; check and handle get if needed.
- **isCancelled() == true:** get() throws CancellationException, and isDone() is true. However, this **does not prove that external side effects have stopped, been rolled back, or never occurred**.

**Important relationship:** cancellation is a state of the Future; actual termination of the task is a separate matter. Especially with cancel(false) on a running task or cancel(true) when code does not respond to interrupts, the Future can report cancelled while part of the underlying work still continues.

### Java 17 example: cancelling while a task is waiting

Save the file **FutureCancellationDemo.java**:

~~~java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class FutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch blocker = new CountDownLatch(1);

        try {
            Future<Integer> future = executor.submit(() -> {
                started.countDown();
                blocker.await();
                return 123;
            });

            started.await();
            boolean cancelled = future.cancel(true);

            System.out.println("cancel accepted=" + cancelled);
            System.out.println("done=" + future.isDone()
                    + ", cancelled=" + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException expected) {
                System.out.println("get -> CancellationException");
            }
        } finally {
            blocker.countDown();
            executor.shutdown();
        }
    }
}
~~~

Run:

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Stdout:

~~~text
cancel accepted=true
done=true, cancelled=true
get -> CancellationException
~~~

started.await() ensures the worker has entered the task body, while blocker.await() has not been released yet. cancel(true) transitions the Future state to cancelled and sends an interrupt request to the worker; CountDownLatch.await() supports interruption. Releasing the blocker in finally is a defensive step so the worker is not left stuck if another branch occurs.

If the task performs database writes, HTTP requests, or file writes, **cancelling the Future does not automatically undo effects that have already happened**. Designing work with side effects should consider idempotency, I/O timeouts, transactions, and business completion states.

## 8. Using get/isDone/isCancelled together: sensible handling patterns

### When the caller actually needs the result

Calling get(timeout,...) with an appropriate deadline is usually easier to read and avoids polling loops. Catch separately:

- **InterruptedException:** the waiting caller was interrupted; propagate or restore the interrupt flag if handled here.
- **ExecutionException:** the task failed; classify the cause and handle the business/technical error.
- **TimeoutException:** the wait timed out; evaluate whether to cancel or discard the result.
- **CancellationException:** the Future was cancelled; handle as the cancellation branch, do not treat as a valid result.

In code that handles InterruptedException locally:

~~~java
try {
    return future.get(1, TimeUnit.SECONDS);
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Caller interrupted", interrupted);
}
~~~

This is an **illustrative snippet inside a method that has a Future<V> and return type V**; ExecutionException, TimeoutException, and CancellationException still need to be declared/handled at the appropriate level. If the method can declare throws InterruptedException, propagating the checked exception is usually clearer.

### When you only want to display status

~~~text
if (future.isCancelled()) {
    // Cancelled.
} else if (future.isDone()) {
    // Completed, but success/failure is not yet known.
    // To know the result, you still must call get() and handle exceptions.
} else {
    // Pending: queued or running.
}
~~~

This is **pseudocode** illustrating the states, not a standalone Java class. The check order does not create an atomic snapshot: if another thread completes/cancels right after the check, the next observed state may change. For UI or metrics, clearly document that this is a snapshot.

### When receiving multiple Futures

If you have a list of Futures and call get() sequentially in submission order, a slow first task can block the caller even though later tasks have already completed. Do not continuously poll the entire list in a busy CPU loop. Options in standard Java include:

- **ExecutorCompletionService:** retrieves Futures in the order tasks **complete**, rather than submission order; you still must call get and handle errors.
- **invokeAll(collection):** waits for a collection of tasks to complete according to the contract; the timeout overload can cancel unfinished tasks when the deadline expires.
- **CompletableFuture:** when you need composition, callbacks, and result-processing chains; it implements Future but has its own API. With CompletableFuture, join() uses CompletionException (unchecked) instead of get()'s checked-exception model.

The options above address multi-task scenarios; to understand Future.get/isDone/isCancelled, first master the semantics of a single Future.

## 9. Future in ScheduledExecutorService

Future also appears in standard Java scheduling:

- **schedule(Callable/V or Runnable, delay, unit)** returns a ScheduledFuture. Before the one-shot task finishes running, isDone is usually false; after running successfully, get returns the result (for Runnable, usually null).
- **scheduleAtFixedRate** and **scheduleWithFixedDelay** return a ScheduledFuture representing a **periodic** execution sequence. While the periodic sequence continues normally, the Future is not considered completed after each run, so isDone usually remains false.
- **get() on a normally running periodic Future may wait forever**, because the sequence has not terminated. After successful cancellation, get throws CancellationException. If a periodic run throws an exception that prevents further executions, the Future may complete via the failure branch and get throws ExecutionException.
- **cancel(true)** on a ScheduledFuture does not guarantee that a currently running callback stops immediately; interruption and side-effect rules still apply.

Therefore, you should not call get() indefinitely on a periodic task if the design expects "getting the result of each run." If you want per-run results, you need a separate mechanism to emit events/results, rather than relying on the Future of the entire periodic schedule.

## 10. Common mistakes

| Mistake | Consequence | How to handle |
|---|---|---|
| Reading isDone() == true as "success" | Ignores failure/cancel branches | Call get() and handle ExecutionException/CancellationException |
| Reading isCancelled() == false as "finished well" | Confused with queued, running, or failed | Combine state checks with the result of get |
| Calling get() indiscriminately on the main/UI/request-handling thread | May block indefinitely | Set deadlines, consider async architecture |
| Thinking get(timeout) automatically stops the task | Old task may continue, causing duplicate processing on retry | Decide on cancel separately; ensure idempotency when needed |
| Thinking cancel(true) always "kills" the worker | Side effects or non-interruptible code may continue | Support interruption, I/O timeouts, and proper rollback/compensation |
| Busy-spinning with while (!isDone()) | Burns CPU and does not handle errors | Use get/get(timeout), CompletionService, or completion APIs |
| Swallowing InterruptedException | Loses the caller's shutdown/cancel signal | Propagate or restore the interrupt flag |
| Ignoring ExecutionException.getCause() | Hides the real error that occurred in the task | Classify/log the root cause |
| Waiting on get() for a periodic scheduled task | May wait until cancellation/failure, not per period | Design a separate result mechanism for each run |
| Not shutting down ExecutorService | Workers may keep the JVM alive or leak resources | Manage lifecycle, shutdown, and await termination per policy |

## 11. Memorization and self-check checklist

After this lesson, you should be able to explain:

1. Why can get() block the caller while isDone()/isCancelled() do not?
2. How do the three outcomes (**success, failure, cancellation**) affect the state table and the result of get()?
3. Why does isDone() true not mean the task succeeded, and why does isCancelled() false not mean the task has completed?
4. When get(timeout,...) throws TimeoutException, does the worker-side task continue running?
5. What is the difference between interrupting the thread **waiting on get** and calling cancel(true) on the Future?
6. Why do cancel(false) or cancel(true) not automatically guarantee that external side effects stop or roll back?
7. Why does the Future of a **periodic** scheduled task not complete after each successful run?

**Core takeaway:** **get()** is the gateway to retrieve results and errors and may wait; **isDone()** only confirms that the computation has ended according to the Future state; **isCancelled()** indicates that the computation was successfully cancelled. All three must be understood alongside cancellation, interruption, timeouts, and executor lifecycle to manage asynchronous work safely.
