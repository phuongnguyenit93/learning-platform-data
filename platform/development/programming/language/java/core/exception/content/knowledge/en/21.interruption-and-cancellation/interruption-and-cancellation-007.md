# Why You Should Not Swallow `InterruptedException` and Continue as Normal

## 1. The Problem: A Stop Signal Can Disappear

In Java, a thread can be requested to **interrupt** when another component wants it to stop waiting, cancel work, release resources, or terminate in a controlled manner. Calling `thread.interrupt()` sends a signal to the **target thread**, typically via the thread's interrupt status; it does not forcibly kill the thread or automatically undo work already performed.

If the thread is in a waiting operation that supports interruption, such as `Thread.sleep()`, `Thread.join()`, or `BlockingQueue.take()`, it can receive an `InterruptedException`. Many waiting methods under this mechanism **clear the interrupt status when throwing the exception**. Therefore, a snippet like the following can accidentally lose the cancellation request:

```java
try {
    Thread.sleep(10_000);
} catch (InterruptedException ex) {
    // Ignore and continue working.
}
doMoreWork();
```

This is a **code snippet inside a method** where `doMoreWork()` is already defined, not a standalone program. If another thread requests an interrupt during `sleep`, the method exits `sleep` via the exception, but the handler neither forwards the signal, restores the flag, nor changes the control flow. `doMoreWork()` is still called. In a long-running worker loop, the task may keep running even though the system has already requested it to stop.

**"Swallowing `InterruptedException`"** means catching the interrupt signal without forwarding it to a responsible layer, without preserving the status, and continuing to operate as if no cancellation request ever occurred. This is a problem of **coordination protocol between threads**, not merely losing an error message.

## 2. Interrupt Is a Cooperative Request, Not a Forcible Stop Command

When A calls `worker.interrupt()`, the key behaviors to distinguish are:

1. The JVM sets the interrupted status on **worker**, except in cases where a waiting API reacts by throwing `InterruptedException` and clearing that status.
2. If the worker is running computation that does not check for interruption, calling `interrupt()` **does not automatically stop** the computation instructions.
3. If the worker is waiting in a method with an interruptible contract, the waiting operation can throw `InterruptedException` so the worker can decide to exit, return an error, or clean up.
4. The worker can proactively check `Thread.currentThread().isInterrupted()` in a loop that has no waiting points.
5. Interruption does not automatically roll back changes to objects, databases, files, or network requests.

`InterruptedException` should not be equated with a normal I/O error or user input error. In many concurrency libraries, it represents **a cancellation request or a change in thread control policy**. Swallowing this signal can break the termination contract of an upper-level component.

However, `interrupt()` does not always mean "cancel everything" in every application. The exact meaning is determined by the protocol between components; if a layer is responsible for handling interruption completely, it may consume the signal intentionally. The problem is **ignoring it without making an appropriate control decision**.

## 3. The Interrupt Flag Mechanism and Behavior of Waiting Methods

Each `Thread` has an interrupted status. Key APIs:

| API | Effect |
| --- | --- |
| `someThread.interrupt()` | Sends an interrupt signal to thread `someThread`; does not wait for it to finish |
| `Thread.currentThread().isInterrupted()` | Checks the flag of the current thread; **does not clear the flag** |
| `someThread.isInterrupted()` | Checks the flag of a referenced thread; **does not clear the flag** |
| `Thread.interrupted()` | `static` method that checks **the current thread** and **clears the flag** |
| `Thread.currentThread().interrupt()` | Sets/restores the interrupted flag for the current thread |
| `Thread.sleep(...)` | If interrupted while waiting (or if the interrupt flag is set on entry), throws `InterruptedException` and clears the flag per contract |
| `Thread.join(...)`, `Object.wait(...)` | Can throw `InterruptedException` when the waiting thread is interrupted and clears the flag |

The two easiest methods to confuse are:

```java
boolean flagStillThere = Thread.currentThread().isInterrupted();
boolean flagAndClearIt = Thread.interrupted();
```

These are two valid Java statements inside a method. `isInterrupted()` only reads the flag, whereas `Thread.interrupted()` has a **clear-on-read** effect. In a cancellation control loop, accidentally calling `Thread.interrupted()` and ignoring the return value can wipe out the stop request even without ever catching an `InterruptedException`.

APIs in `java.util.concurrent` such as `BlockingQueue.take()`, `CountDownLatch.await()`, `Future.get()`, `Semaphore.acquire()`, `Lock.lockInterruptibly()`, and `Condition.await()` also support interruption according to their own contracts. Many blocking APIs clear the status when throwing `InterruptedException`; you should read the specific API documentation rather than assuming every Java call behaves identically.

Some APIs like `LockSupport.park()` have different semantics: they can **return** when interrupted without throwing `InterruptedException` and without clearing the flag. I/O calls or native operations also do not necessarily react quickly to interruption. Therefore, the fact that a thread is still running after `interrupt()` does not by itself prove the program is wrong; you must examine the **cooperative cancellation points** and the task's responsibilities.

## 4. Why Is `catch (InterruptedException) {}` Dangerous?

Swallowing an interruption can cause many consequences:

- **Ineffective cancellation:** `Future.cancel(true)` or `ExecutorService.shutdownNow()` attempted to interrupt the worker, yet the task continues as normal.
- **Slow or stalled application shutdown:** Shutdown hooks or controllers wait for the worker to exit while the worker keeps re-invoking waiting operations.
- **Erasing cancellation evidence:** Because some waiting methods clear the flag when throwing, upper layers calling `isInterrupted()` may see `false` and mistakenly assume no stop request was made.
- **Waiting all over again:** The handler ignores the exception and goes back to `sleep()`, `take()`, or `await()`; because the flag was cleared, the next wait can block again until a new signal arrives.
- **Post-cancellation side effects:** The worker continues writing to the database, sending notifications, processing jobs, or executing transactions that the caller believes it already requested to cancel.
- **Broken cross-layer contract:** The library was asked to terminate but hid the signal, leaving the service layer or scheduler unaware that the stop policy was violated.
- **Hard to diagnose:** Logs might merely record "sleep interrupted" as an unimportant warning, while the real issue is that the lifecycle is not following cancellation commands.

An empty `catch` statement is especially hard to review because readers cannot tell whether it was an intentional decision or a mistake. If you truly intend to consume the interruption, you must clearly document **who owns the cancellation request** and why the status has been fully handled.

## 5. Runnable Java 17+ Example: Swallowing vs. Restoring the Signal

The following program creates two workers sequentially. Each worker signals that it has started via a `CountDownLatch` and then waits using `Thread.sleep(...)`. The main thread requests to interrupt the worker.

- `SWALLOW`: catches `InterruptedException` and still runs the next step; because `sleep` clears the flag, `isInterrupted()` inside the handler is `false`.
- `RESTORE`: catches the error, calls `Thread.currentThread().interrupt()`, and `return`s to stop the task; the flag has value `true` at the check point after restoration.

Save as **`InterruptedExceptionHandlingDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptedExceptionHandlingDemo {
    private static void runCase(String name, boolean restore)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                Thread.sleep(60_000);
            } catch (InterruptedException ex) {
                System.out.println(name + " caught; flag="
                        + Thread.currentThread().isInterrupted());
                if (restore) {
                    Thread.currentThread().interrupt();
                    System.out.println(name + " stopped; flag="
                            + Thread.currentThread().isInterrupted());
                    return;
                }
                System.out.println(name + " continued despite cancellation");
            }
        }, name);
        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
    }

    public static void main(String[] args) throws InterruptedException {
        runCase("SWALLOW", false);
        runCase("RESTORE", true);
        System.out.println("DONE");
    }
}
```

Compile and run on JDK 17 or later:

```bash
javac -encoding UTF-8 InterruptedExceptionHandlingDemo.java
java InterruptedExceptionHandlingDemo
```

Standard output:

```text
SWALLOW caught; flag=false
SWALLOW continued despite cancellation
RESTORE caught; flag=false
RESTORE stopped; flag=true
DONE
```

**Why is this output notable?**

1. `started.await()` only confirms that the worker has reached the signaling point; `main` may interrupt just before or during `Thread.sleep`. Both cause the `sleep` operation to react with `InterruptedException`.
2. `Thread.sleep` clears the flag when throwing, so both handlers print `flag=false` immediately upon entering `catch`.
3. In the `SWALLOW` case, the program intentionally executes the "continued despite cancellation" step. In a real worker with a loop, skipping once like this can cause many more iterations to be processed.
4. In the `RESTORE` case, the handler restores the flag to `true` and then **exits the `Runnable`**. Merely restoring without exiting the control path can still cause a loop to keep running and subsequent blocking calls to be interrupted immediately.
5. `worker.join()` only waits for the worker to finish; it does not transfer an `InterruptedException` that occurred **in the worker** back to `main`. `runCase` declares `throws InterruptedException` because the `main` thread itself could also be interrupted while waiting in `await` or `join`.

The example is intentionally small with no real side effects, and does not imply that all forms of I/O are interruptible. `Thread.sleep(60_000)` is the expected wait duration, but in the demo `main` requests an interrupt immediately so it does not wait a full minute. If a very unusual runtime environment interrupts `main` from outside the program, it may throw `InterruptedException` at `await` or `join`; the listed output assumes normal execution with only the interrupt calls shown in the code.

## 6. Best Pattern When the Contract Allows: Propagate `InterruptedException`

If the method you are writing **can declare `throws InterruptedException`**, the easiest way to preserve the signal is usually not to catch it, or to catch it only for cleanup and then rethrow:

```java
void waitForItem(BlockingQueue<String> queue)
        throws InterruptedException {
    String item = queue.take();
    process(item);
}
```

This is a method snippet inside a class where `process(String)` is already defined; `java.util.concurrent.BlockingQueue` must be imported. `queue.take()` can wait and throw `InterruptedException`. When the exception propagates out of `waitForItem`, the calling layer knows the operation stopped due to an interrupt request and can decide to cancel the entire workflow.

If cleanup is required:

```java
void runOneStep() throws InterruptedException {
    Resource resource = acquireResource();
    try {
        blockingOperation();
    } finally {
        resource.close();
    }
}
```

This is a structural pattern, with `Resource`, `acquireResource()`, and `blockingOperation()` defined by the application. `finally` runs on the exit path of the method as `InterruptedException` propagates. `close()` should be designed to handle cleanup errors without accidentally masking the original interrupt exception.

**You do not necessarily have to restore the flag in every block that catches and then executes `throw ex`**: for a method declaring `throws InterruptedException`, the caller already receives an explicit signal via the exception. Many waiting contracts intentionally clear the interrupt flag when throwing; propagating the exception preserves that exact mechanism. If a caller needs to restore the flag to pass the signal to higher-level code that cannot declare the exception, do so at the appropriate boundary.

## 7. When You Cannot Throw a Checked Exception: Restore and Exit

`Runnable.run()` does not declare `throws InterruptedException`. For a worker that should terminate when interrupted, a common pattern is:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            WorkItem item = queue.take();
            process(item);
        }
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        return;
    } finally {
        releaseResources();
    }
}
```

This is a snippet inside a class that defines `queue` of type `BlockingQueue<WorkItem>` along with `process` and `releaseResources`; it is not a standalone program. It has three key points:

- The loop condition proactively checks the interrupted flag.
- If `queue.take()` is interrupted, it throws an exception; the handler **restores the flag** so upstream/outer code can still observe the signal.
- `return` exits `run()`, while `finally` still performs cleanup.

This pattern is only appropriate when interruption is defined as **a request to terminate the worker**. If business logic has transactions to roll back or checkpoints to save before stopping, organize controlled cleanup rather than just adding `return`.

Avoid the half-baked pattern:

```java
while (true) {
    try {
        Thread.sleep(1000);
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
    }
}
```

This is an **intentionally wrong example**. After the handler restores the flag, the loop calls `sleep` again. Because the flag is set, `sleep` can immediately throw `InterruptedException` and clear the flag; the handler sets the flag again. The result can be a **hot loop**, burning CPU, doing no useful work, and never terminating. Therefore, **restoring the flag must be paired with the right control flow**, typically `break`, `return`, or returning an explicit cancellation result.

## 8. Why You Must Also Watch Out for `catch (Exception)` and Wrappers

A method can accidentally swallow an interruption even without writing a dedicated `catch (InterruptedException)`:

```java
try {
    queue.take();
} catch (Exception ex) {
    logger.warn("Cannot receive next item", ex);
    // Continue the loop — InterruptedException was swallowed.
}
```

This is an **error-illustrating snippet**, with `queue` and `logger` defined by the application. `InterruptedException` extends `Exception`, so a `catch (Exception)` block catches it. If the code simply continues, the shutdown request can be lost.

You should also inspect code that catches other parent exceptions and adapters that convert checked exceptions into unchecked ones:

- `catch (Throwable)` also includes `Error`, which can mask unsafe JVM states; it is not a solution for making a worker "never die."
- `throw new RuntimeException(ex)` preserves `cause` but **does not necessarily preserve the interrupt status**. If an outer layer only checks the flag, that information can be lost.
- Logging `ex.getMessage()` and ignoring it fails to convey the control meaning of interruption.
- Wrapping all errors as "request timeout" or "unknown failure" prevents the system from distinguishing cancellation from a dependency failure.

If you are at an API boundary that must convert `InterruptedException` into an unchecked exception and no longer has a signature to propagate it, a common pattern is:

```java
try {
    blockingOperation();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("Operation interrupted", ex);
}
```

This is an **implementation snippet**, with `blockingOperation()` being an interruptible method. It both preserves `cause` and restores the status. However, the wrapper type and the decision to throw must follow the API contract. Do not turn an interruption into a state error when the caller needs to distinguish cancellation separately; a dedicated exception may be more appropriate. If the task has already fulfilled the cancellation request by exiting normally and only needs to report "cancelled," throwing a wrapper is not mandatory either.

## 9. When Is It Acceptable to "Consume" an Interruption?

There are components that **own the entire cancellation protocol** and are responsible for handling the interruption right on the spot. In that case, not propagating or not restoring the flag can be an intentional decision. For example, a controller managing system shutdown might catch the signal, transition state to `STOPPING`, perform cleanup to a confirmed state, and return a result according to its own contract.

For a case to be considered properly handled, you must demonstrate:

1. The component catching the exception is indeed the party responsible for **completing the handling of the cancellation signal**.
2. The task does not continue performing contract-violating side effects after the cancellation request has been accepted.
3. The caller or lifecycle manager has a way to recognize that the task stopped/cancelled properly, such as a `Future`, status, or callback.
4. Cleanup does not mask critical errors and does not wait indefinitely because the flag was lost.
5. The decision is clearly documented and tested, rather than being an empty `catch` caused by forgetting to handle it.

Some libraries have APIs that only accept returning normally or reporting cancellation via a dedicated result. In such cases, consuming the exception is acceptable if the cancellation workflow is completed and external state remains accurate.

The statement "you must always call `Thread.currentThread().interrupt()` immediately when catching `InterruptedException`" is **too absolute**. For methods declaring the checked exception, propagating `InterruptedException` already preserves the signal. At a boundary that genuinely finishes handling the interruption, keeping the flag set could cause subsequent operations to be interrupted unintentionally. What must be avoided is **mindlessly swallowing it and continuing as normal**.

## 10. How Common APIs Signal Interruption

| API | Operation | When Interrupted |
| --- | --- | --- |
| `Thread.sleep` | Pause thread | Throws `InterruptedException` and clears interrupt status |
| `Object.wait` | Wait on monitor per wait/notify protocol | Throws `InterruptedException`, clears status; must own the valid monitor |
| `Thread.join` | Wait for a thread to finish | The **waiting** thread receives `InterruptedException`, not an error of the joined thread |
| `BlockingQueue.take` | Wait for an available element | Can throw `InterruptedException`; task should stop/propagate per contract |
| `CountDownLatch.await` | Wait for counter to reach 0 | Can throw `InterruptedException` |
| `Future.get` | Wait for task result | Can throw `InterruptedException` on the **waiting thread**, distinct from task's `ExecutionException` |
| `Semaphore.acquire` | Wait for a permit | Can throw `InterruptedException` |
| `Lock.lockInterruptibly` | Wait for lock in an interruptible manner | Can throw `InterruptedException` |
| `ExecutorService.awaitTermination` | Wait for executor to finish | Can throw `InterruptedException` on the waiting thread |
| `LockSupport.park` | Park waiting on permit/interrupt | Can return when interrupted, not via the usual `InterruptedException` path |

Not every waiting operation supports interruption. For example, a normal `ReentrantLock.lock()` has no contract to throw `InterruptedException` while waiting for the lock; use `lockInterruptibly()` when you want cancellation via interrupt. Some I/O operations behave differently depending on the channel, provider, and OS. If you need guaranteed timely termination, you must have timeouts or appropriate resource closing/cancellation mechanisms, rather than relying solely on `interrupt()`.

## 11. `Future.cancel(true)` and `shutdownNow()` Cannot Guarantee a Task Stops

When tasks run in an `ExecutorService`, management code often uses:

```java
Future<?> future = executor.submit(task);
future.cancel(true);
```

This is a code snippet with `executor` and `task` already defined. `cancel(true)` **requests** cancellation of the work and may interrupt the executing thread if the task is running. This does not mean the JVM has forcibly aborted all computation or reversed side effects.

If the task:

- is calling an interruptible API and **obeys the signal**, it can exit early;
- catches `InterruptedException` and ignores it, it **can keep working** even though the future reports cancelled;
- is performing long CPU computation without checking the flag, it can continue until finished;
- is in an I/O operation that does not respond to interruption, it may not stop immediately;
- has already committed to a DB or sent a network request, those effects are not automatically rolled back.

`ExecutorService.shutdownNow()` attempts to stop executing tasks via interruption, stops accepting new work, and returns the list of tasks that have not started. It is *best effort*; if tasks ignore interrupts, the executor may not terminate within the expected time. `shutdown()` requests stopping acceptance of new tasks while allowing already-submitted work to continue per the executor's policy.

With `CompletableFuture`, remember that `cancel(boolean mayInterruptIfRunning)` does not use this parameter to control interruption in the same way as `FutureTask`; in `CompletableFuture`'s implementation, that parameter has no effect because interrupts are not used to control processing. Do not build a task-stopping protocol assuming every future API shares the same interrupt mechanism.

## 12. Cancellation While Waiting and Task Failure Are Two Different Kinds of Information

In concurrent code, thread A may wait for a result produced by B:

```java
try {
    String value = future.get();
    use(value);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
} catch (ExecutionException ex) {
    handleTaskFailure(ex.getCause());
}
```

This is a **code snippet inside a method returning `void`**, with `future`, `use`, and `handleTaskFailure` provided by the application and `ExecutionException` imported.

Distinguish between:

- `InterruptedException`: **A, which is waiting**, was requested to interrupt. The wait was interrupted; B may **still be running**. Stopping B as well requires a separate policy, such as `future.cancel(true)` if appropriate.
- `ExecutionException`: task B completed with an error; `getCause()` holds the reason B failed. This is **task result** information, not A's interrupt signal.
- `CancellationException`: the `Future` is in a cancelled state; that does not necessarily prove all side effects of the task have stopped.
- `TimeoutException` from `future.get(timeout, unit)`: A waited past the deadline; B may keep running unless cancelled per policy.

Swallowing `InterruptedException` in A and calling `get()` again can cause A to keep waiting indefinitely, breaking deadlines or shutdown requests. That is a common example of "being asked to stop waiting, yet waiting again."

## 13. Handling Interruption in a Worker Loop

A long-running worker typically has three kinds of steps: receiving a request, processing data, and recording results. If using `BlockingQueue.take()`, a cooperative cancellation design can look like:

```java
void workerLoop(BlockingQueue<Job> queue)
        throws InterruptedException {
    while (!Thread.currentThread().isInterrupted()) {
        Job job = queue.take();
        execute(job);
    }
}
```

This is a **method snippet**, with `Job` and `execute(Job)` defined by the application. `take()` receives the interrupt signal according to the rules, but `execute(job)` also needs a contract for handling cancellation and state. If `execute` blocks in I/O or performs heavy CPU work with no check points, the worker will not stop immediately.

If replaced with a loop that always catches and ignores:

```java
while (true) {
    try {
        Job job = queue.take();
        execute(job);
    } catch (InterruptedException ex) {
        // Do nothing, repeat take().
    }
}
```

This is an **intentionally wrong example**. After an interrupt, `take()` throws, the flag is cleared, and the loop continues waiting for a new job. This can prevent shutdown from ever completing, even though management components have already sent the cancellation request.

In production design, you must also decide:

- If a worker is cancelled mid-job, is the job marked **cancelled**, **retryable**, or **unknown**?
- If the job has partially written data, what transactions/rollbacks, checkpoints, or compensations are permitted?
- If multiple workers share a queue, interruption can happen right after taking a job; under what contract should that job be returned or have its progress recorded?
- If cleanup runs while the interrupt flag is set, subsequent blocking operations may immediately throw an exception again; bounded cleanup and separate error handling must be planned.

Do not infer that "having received `InterruptedException`" means "all state has been rolled back." Those are two separate concerns.

## 14. Cleanup, State, and Consistency on Interruption

When receiving a cancellation request, the application may be holding locks, file handles, transactions, or mutating state. Two coordinating principles:

**First, do not hide the cancellation request.** Usually propagate `InterruptedException` or restore the interrupt flag before exiting the task, so upper layers can recognize the state.

**Next, ensure cleanup within realistic bounds.** Use `finally`, `try-with-resources`, transaction rollback, lock release, or checkpoints per contract. Cleanup tasks themselves can throw exceptions or block; you cannot assume recovery always succeeds.

Example of a meaningful structure (snippet; the referenced methods must be defined):

```java
try {
    startTransaction();
    doInterruptibleWork();
    commitTransaction();
} catch (InterruptedException ex) {
    try {
        rollbackTransaction();
    } catch (RuntimeException rollbackFailure) {
        ex.addSuppressed(rollbackFailure);
    }
    throw ex;
} finally {
    releaseResources();
}
```

This snippet assumes the enclosing method **declares `throws InterruptedException`** and the DB/rollback operations are application methods with compatible defined exception types. `addSuppressed` preserves the rollback failure information but **does not make the rollback succeed**. This is only an analytical structure; real applications must handle all DB exceptions, commit uncertainty, the possibility that rollback itself may be interrupted, and transaction-related details.

If `commitTransaction()` has already succeeded before a cancellation request arrives, the committed data may still persist. There is no guarantee that "interrupt equals rollback." Do not automatically retry a job with side effects after cancellation without idempotency or reconciliation.

## 15. Tying Interruption to Timeout and Deadline Policies

Interrupt requests and timeouts are related but not identical:

- **Deadline/timeout:** a time limit for completion or waiting; `get(timeout)` can throw `TimeoutException` to the calling thread.
- **Interrupt:** requests a specific thread to stop waiting or cooperatively stop; many APIs throw `InterruptedException`.
- **Cancellation:** a lifecycle state of a task/request, which may trigger an interrupt but also carries semantics about results and side effects.

A controller may cancel a future due to a timeout, but if the worker swallows the interruption and continues, execution time can exceed the deadline and still produce side effects after the caller has given up.

A strategy can combine timeouts, `cancel(true)` when supported by the API, checking the interrupt flag at reasonable points, and propagating deadlines down to dependencies. Do not treat `interrupt()` as a universal timeout mechanism for every socket, file, JDBC driver, or external service.

## 16. Do Not Treat Interruption as a Business Error for Infinite Retries

Suppose a worker sends requests to a backend. For transient network errors, you can retry with a bounded attempt count, backoff, and jitter. However, if the thread is interrupted, it is usually a signal from the management system that **retrying should not continue**.

Common mistake:

```java
while (true) {
    try {
        requestRemote();
        break;
    } catch (Exception ex) {
        Thread.sleep(1000);
    }
}
```

This is an **intentionally wrong code snippet**, with `requestRemote()` already defined; to compile, the checked `InterruptedException` from `sleep` must also be handled or declared. If the retry loop catches `Exception` without distinguishing cancellation errors, or catches an interrupt at an upper layer and continues, it can fight against shutdown.

A better policy pattern:

1. If the error is **`InterruptedException`**, propagate it or restore the flag and exit the task.
2. If it is a retryable dependency error, check the deadline and interrupt status before the next iteration.
3. Back off using an interruptible wait operation so it can stop quickly when cancelled.
4. If retries have side effects, use an idempotency key and check uncertain outcomes.
5. When the retry budget is exceeded, report an error with context and terminate per contract.

Do not automatically convert an interruption into an `IllegalStateException` and route it into the "retry transient error" branch. Retry policies must recognize cancellation as a distinct case.

## 17. Virtual Threads Must Also Respect Interruption

A virtual thread (stable since Java 21) is still a `Thread` with an interrupt status and `InterruptedException` rules on supporting APIs. It makes running many blocking tasks lighter; it does **not** make cancellation automatic or perform rollbacks.

A virtual thread sleeping in `Thread.sleep(...)` can also be interrupted, throwing `InterruptedException` and requiring code to decide whether to exit or restore the signal. If the handler ignores it and continues, the virtual thread can still perform contract-violating work.

If using newer Java versions with **structured concurrency** or task-group management frameworks, cancelling sibling tasks often relies on interruption or similar mechanisms. A child task swallowing the signal can make it difficult for the group to finish on time. Structured concurrency APIs and their stability status vary by JDK version; check the actual JDK contract rather than applying a Java 17 demo snippet to APIs that do not exist in Java 17.

## 18. How to Test That Interruption Is Not Swallowed

Tests should verify **the signal and post-signal behavior**, not just assert that the log contains the string "InterruptedException."

| Case | What to Verify |
| --- | --- |
| Thread in `sleep` is interrupted | `InterruptedException` occurs in the interrupted thread itself |
| Handler swallows and continues | Post-cancellation processing step is observable (to detect the bug) |
| Handler restores and returns | Flag is restored at the required point; task does not perform the next business step |
| Method `throws InterruptedException` | Exception propagates to the caller instead of being masked |
| Worker using `BlockingQueue.take()` | Cancellation makes the worker exit the loop rather than going back to wait for jobs indefinitely |
| `Future.cancel(true)` | Task reacts appropriately; do not assume all side effects were rolled back |
| Interrupted during cleanup | Resources are handled per policy; primary error info is not lost |
| Timeout waiting on `Future.get(timeout)` | Caller distinguishes timeout from interrupt and actual task failure |
| Another thread is working | Interrupting one worker does not automatically "throw an exception" onto another worker's call stack |
| A loop using `Thread.interrupted()` | Verify clear-on-read behavior does not lose the cancellation signal |

For reliable tests, use `CountDownLatch`, `Future`, `AtomicBoolean`, or synchronization primitives to control ordering, along with generous timeouts. Avoid tests that rely solely on `Thread.sleep(100)` and assume the scheduler has definitely run. Always ensure threads/executors are requested to shut down in `finally`, even if assertions fail.

If a task is uncooperative and keeps running forever, tests need time limits and proper isolation; never let the entire test suite hang indefinitely.

## 19. Common Mistakes and Fixes

| Problematic Code | Consequence | Fix Direction |
| --- | --- | --- |
| `catch (InterruptedException ignored) {}` | Erases cancellation trace, task continues | Propagate, or restore flag and exit task |
| Catch `Exception`, log, and keep looping | Swallows interruptions from blocking APIs | Catch `InterruptedException` separately first and follow contract |
| `Thread.currentThread().interrupt()` then continue `while(true)` | Hot loop when waiting API throws immediately on next iteration | `break`/`return` or coordinate cancellation state |
| Call `Thread.interrupted()` just to check and discard result | Accidentally clears flag | Use `isInterrupted()` when checking without clearing the flag |
| Treat `cancel(true)` as a forcible stop | Task may still run and produce side effects | Design cooperative cancellation and idempotency |
| Swallow interrupt to "guarantee job completion" | Can break caller's deadline/shutdown | Separate must-complete requirements from cancellation protocol, document clearly |
| Convert `InterruptedException` into normal retry error | Worker keeps retrying when already cancelled | Classify cancellation separately, preserve cause/flag when needed |
| Assume interruption rolls back DB/files | Data may already be committed/written | Transactions, cleanup, checkpoints, and independent reconciliation |
| Assume every I/O API reacts to interrupt immediately | Task fails to stop on time | Check contracts, use timeouts, close resources when appropriate |
| Log once and nobody observes the outcome | Caller still thinks task is running | Return clear future/status/error callback |

## 20. API Design and Code Review Checklist

1. Identify **who has the right to interrupt**, and whether interrupt means **cancel**, shutdown, aborting a single wait, or another signal.
2. List interruptible waiting points: `sleep`, `wait`, `join`, `take`, `get`, locks, latches, and other integrated APIs.
3. If a method can declare `throws InterruptedException`, prefer **propagating** the signal to the policy-owning layer.
4. If you cannot throw a checked exception, choose a clear handling policy; for stopping a task, usually **restore flag + return/break**, and clean up in `finally`.
5. Avoid `catch (Exception)` or `catch (Throwable)` that mixes cancellation requests with business errors.
6. Do not restore the flag and return to a blocking call in a loop without checking an exit condition.
7. When a task is cancelled, determine the state of completed work, transactions, checkpoints, and side effects that need reconciliation.
8. With `Future.cancel(true)`, `shutdownNow()`, or executors, do not assume a task is guaranteed to stop if the code is uncooperative.
9. Distinguish **interrupted**, **cancelled**, **timed out**, and **failed** in results, logging, and monitoring.
10. Test cancellation paths when the task is waiting, processing, cleaning up, and when dependencies do not respond to interrupts.

**Rule of thumb:** `InterruptedException` is usually an intentional coordination signal. Catching and ignoring it can erase the signal and cause the task to continue against the request. **Propagate it**, or **restore the flag and exit on the right path**, unless the current layer truly owns and has completely handled the entire cancellation protocol.
