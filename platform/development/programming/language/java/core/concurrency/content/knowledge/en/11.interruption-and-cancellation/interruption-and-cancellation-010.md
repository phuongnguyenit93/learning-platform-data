# Ensuring finally Closes Resources When Stopping Tasks in Java

A Java task may finish normally, throw an exception, receive a cancellation request, be interrupted while waiting, or time out on the calling thread. In every case where **the task still has an opportunity to execute cleanup**, the programmer must close the resources it owns: streams, sockets, file handles, locks, self-managed transactions/sessions, child workers, and other objects with finite lifecycles. The fundamental tools are the **`try/finally`** block and **`try-with-resources`**.

However, **`Future.cancel(true)` is not a thread-killing operation**, and `finally` **does not guarantee execution in every kind of failure**, such as process kill, JVM halt, power loss, or a thread stuck and unable to reach an exit point. To achieve reliable cleanup, you must design **cooperative cancellation**, responsive waiting points, clear resource ownership, time bounds, error reporting, and tests covering termination paths.

This article covers **general Java concurrency**, using APIs in the JDK and Java 17+. Spring-specific concurrency mechanisms are reserved for another chapter.

## 1. Three Different Things: Cancellation Request, Task Termination, Resource Cleanup

| Concept | Definition | Example |
| --- | --- | --- |
| **Cancellation request** | One party asks the task to stop | `future.cancel(true)`, `thread.interrupt()` |
| **Task termination** | The task's code is actually no longer running | The `run()`/`call()` method has returned or thrown an exception |
| **Resource cleanup** | Releasing resources owned by the task | `close()`, `unlock()`, closing sockets, reclaiming handles |
| **Executor termination** | The executor has no remaining running tasks and has completed its lifecycle | `awaitTermination(...)` returns true |

These events are **not identical**. `cancel(true)` can transition a `Future` to the cancelled state before the worker finishes cleanup. A task that does not respond to interruption can keep running. `shutdownNow()` also only **attempts** to interrupt running tasks and returns the list of tasks that were never started; it does not guarantee that all resources are closed.

The design goal is: after a cancellation request is sent, the worker **receives the signal**, exits the business loop, passes through `finally` or `try-with-resources`, closes its resources, and then notifies the coordinator that **cleanup is complete**.

### Ownership Rule

**Whoever owns a resource is responsible for closing it at the right time.** If a worker opens its own file stream inside a method, the worker should usually close it. If a worker only **borrows** a shared client/queue managed by the application, the worker **must not** close it on its own when cancelled, because other tasks still use it.

## 2. `try/finally`: Cleanup When Leaving a Protected Region

Basic pattern:

```java
Resource resource = acquire();
try {
    use(resource);
} finally {
    release(resource);
}
```

This is a **snippet**; `Resource`, `acquire`, `use`, and `release` are illustrative names. If `acquire()` completes successfully and control enters `try`, the `finally` block executes when control leaves `try` along normal Java paths: completion, `return`, exception, or `InterruptedException` thrown from a blocking call.

**Do not write it like this:**

```java
Resource resource = acquire();
use(resource);
release(resource); // Skipped if use() throws an exception.
```

In code with cancellation, the likelihood of exceptions usually increases because `sleep`/`wait`/`join`/`BlockingQueue.take` can throw `InterruptedException`. If `close` is placed at the end of the code without `finally`, the cancellation path can skip cleanup.

### But `finally` Is Not Magic

`finally` is not guaranteed to complete when:

- The JVM/process is hard-killed, `Runtime.halt` is called, or there is a crash or power loss.
- Code is stuck forever inside the `try` block due to a loop with no exit condition or an unbounded blocking API that does not respond to interrupt.
- A thread is abruptly stopped by an unsafe mechanism, or the application no longer has a chance to run cleanup code.
- `close()` itself hangs, breaks, or throws an exception; subsequent cleanup code may not run if not structured properly.

**Practical scope of the “guarantee”:** when **Java control flow unwinds through the normal stack** and the JVM is still executing, `finally` runs according to language semantics. To clean up before a deadline or before process exit, you need additional lifecycle contracts/coordination beyond `finally`.

## 3. `try-with-resources` Is the Default Choice for `AutoCloseable`

Java `try-with-resources` automatically calls `close()` on resources declared in its header when leaving the block, even if the body throws an exception:

```java
try (InputStream input = Files.newInputStream(path)) {
    process(input);
}
```

This is a snippet requiring imports for `java.io.InputStream` and `java.nio.file.Files`, where `path` is a valid `Path` and `process` is a program method. `InputStream` implements `AutoCloseable`. `try-with-resources` helps prevent forgetting to close and handles **suppressed exceptions** when both the body and `close` fail.

A few rules:

- The resource must implement `AutoCloseable` (or `Closeable`).
- Resources in the header are closed in **reverse order** of declaration.
- If declaring the second resource fails, previously created resources are still closed according to `try-with-resources` semantics.
- `close()` can still throw an exception or block; the language does not promise that `close` will always succeed or respect a timeout.
- Creating a resource **beforehand** and using `try-with-resources` with a final/effectively final variable is valid syntax since Java 9, but you must be clear about **who actually owns** it. Do not close a shared resource just because a variable can be placed in the header.

**Prefer `try-with-resources`** when a resource has a clear lexical scope: file streams, readers/writers, sockets created by a task, or custom resources implementing `AutoCloseable`.

## 4. `InterruptedException`: A Cancellation Signal, Not a Request to Swallow Errors

Many JDK blocking methods respond to interruption with `InterruptedException`, such as `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()`, and `CountDownLatch.await()`.

If a worker has an opportunity to stop, the appropriate pattern is:

```java
try {
    while (true) {
        WorkItem item = queue.take();
        process(item);
    }
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Exit method; finally/try-with-resources will clean up.
} finally {
    cleanupOwnedResources();
}
```

This is a **snippet**, with `WorkItem`, `queue`, `process`, and `cleanupOwnedResources` defined elsewhere. Because `InterruptedException` usually **clears the interrupt flag when thrown**, we call `Thread.currentThread().interrupt()` if we catch the exception without **rethrowing it**, so caller/lifecycle code still knows the thread was requested to stop. Then we must **exit the work loop** to clean up, rather than continuing as if no signal arrived.

**If the method can declare `throws InterruptedException`**, it is often simplest to **let the exception propagate** and put cleanup in `finally`/`try-with-resources`. There is no need to restore the flag right before rethrowing if the policy is for the caller to handle interruption; what matters is **not swallowing the signal**.

### Anti-pattern: Catching and Continuing

```java
while (true) {
    try {
        doBlockingWork();
    } catch (InterruptedException ignored) {
        // BUG: swallows the signal, loop continues.
    }
}
```

This is a broken snippet. A `Future.cancel(true)` may be sent, but the worker keeps running forever, leaving the `finally` outside the loop with no chance to execute. If a task must support cancellation, exit the loop or transition state intentionally.

## 5. Runnable Java 17 Example: Interruption Leading to Resource Closure

This program uses a small `AutoCloseable` resource, a thread waiting on a `CountDownLatch` that is never opened, and `main` sending an interrupt after the thread has started. The worker catches `InterruptedException`, restores the interrupt flag, and exits; Java calls `close()` upon leaving `try-with-resources`. `main` only prints after `join` completes, so stdout is deterministic.

Create the file **`FinallyOnInterrupt.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FinallyOnInterrupt {
    static final class TrackedResource implements AutoCloseable {
        private final AtomicBoolean closed = new AtomicBoolean();

        @Override
        public void close() {
            closed.set(true);
        }

        boolean isClosed() {
            return closed.get();
        }
    }

    public static void main(String[] args) throws Exception {
        TrackedResource resource = new TrackedResource();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch neverOpened = new CountDownLatch(1);
        AtomicBoolean interruptRestored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            try (resource) {
                started.countDown();
                neverOpened.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                interruptRestored.set(
                        Thread.currentThread().isInterrupted());
            }
        }, "worker");

        worker.start();
        if (!started.await(5, TimeUnit.SECONDS)) {
            worker.interrupt();
            throw new IllegalStateException("Worker not started");
        }

        worker.interrupt();
        worker.join(5_000);
        if (worker.isAlive()) {
            throw new IllegalStateException("Worker did not finish");
        }

        System.out.println("resourceClosed=" + resource.isClosed());
        System.out.println("interruptRestored=" + interruptRestored.get());
    }
}
```

Run with JDK 17+:

```bash
javac FinallyOnInterrupt.java
java FinallyOnInterrupt
```

Stdout **when the thread runs and finishes within the deadline**:

```text
resourceClosed=true
interruptRestored=true
```

**Step-by-step explanation:**

1. `resource` is attached to the worker's `try-with-resources`; by the contract of this lesson, this object belongs to the worker's ownership, even though `main` keeps a reference solely to inspect it after `join`.
2. The worker calls `started.countDown()` and then waits on `neverOpened.await()`.
3. `main` only interrupts after knowing the worker has entered the `try` block. If the interrupt arrives before `await` actually blocks, `await` still responds with an exception when checking the interrupt status; if it arrives while waiting, the thread is woken up.
4. The worker catches `InterruptedException`, restores the interrupt flag, and records the result.
5. **`try-with-resources` closes the resource upon exiting the `try` block, before entering the `catch` clause of that same `try`.**
6. `worker.join()` ensures `main` reads the results after the worker has finished.

The task above does not use `Thread.stop()`; it stops via **cooperative interruption**, allowing cleanup to run along normal Java paths.

**Limitation:** this example only proves that the sample resource is closed on this cancellation path. It does not prove that every kind of I/O or native call responds to interruption; when replacing `neverOpened.await()` with other I/O, you must read its exact contract.

## 6. `finally` with Mutexes: Always Release a Successfully Acquired Lock

`ReentrantLock` is not automatically released by the JVM based on scope. Therefore, after `lock()` or `lockInterruptibly()` succeeds, you must place `unlock()` in `finally`:

```java
lock.lock();
try {
    updateState();
} finally {
    lock.unlock();
}
```

This is a snippet; `lock` is a `ReentrantLock` or `Lock`, and `updateState` is the protected logic.

### Watch the Placement of `lockInterruptibly()`

```java
lock.lockInterruptibly(); // May throw before acquiring the lock.
try {
    updateState();
} finally {
    lock.unlock(); // Only runs when acquisition succeeded.
}
```

This snippet is inside a method that `throws InterruptedException`. **Do not** place `unlock()` in a `finally` that runs even if `lockInterruptibly()` throws an exception before acquiring the lock. With `ReentrantLock`, unlocking when not the owner throws `IllegalMonitorStateException` and can mask the original error.

With intrinsic monitors, `synchronized(lock)` automatically releases the monitor when exiting the block, even on exception. However, **releasing a mutex does not mean closing files/sockets** created inside; resources with their own lifecycles still need `try-with-resources` or `finally`.

### `Semaphore`, Permits, and Ownership

If `semaphore.acquire()` succeeds, you must `release()` in `finally`. However, if `acquire()` is interrupted **before succeeding**, you must not release as if you owned a permit, otherwise you will erroneously increase the permit count:

```java
semaphore.acquire();
try {
    useLimitedResource();
} finally {
    semaphore.release();
}
```

This is a snippet in a method with `throws InterruptedException`. `semaphore`/`useLimitedResource` are defined outside the snippet. In particular, do not use a `finally` wrapping a failed acquisition to release unconditionally.

## 7. Cancelling a `Future`: Cancelled Does Not Mean Cleanup Is Done

`Future.cancel(true)` **requests** cancellation. For a running task, implementations like `FutureTask` can interrupt the running thread. However:

- If the task has not started yet and cancellation is accepted, the task may **not run**, so `finally` inside the task also **does not run**. Resources allocated outside the task still need an external owner to handle them.
- If the task is running, the `Future`'s cancelled flag may be published **before the worker code exits `finally`**. Do not use `future.isDone()` or `isCancelled()` as proof that `close` has completed.
- If the worker ignores interrupts or is blocked in an API that does not support cancellation, cancellation may not stop the worker early.
- `Future.get()` on a cancelled `Future` typically throws `CancellationException`; it **does not wait** for resource cleanup the way you might assume. You need a separate handshake or to wait for the executor to actually terminate.
- `cancel(false)` does not send an interrupt to a running task; stopping depends on the task and scheduling state.
- When `cancel(true)` returns false, the task may have already completed or cancellation was not accepted; you must analyze the result according to the contract, not guess.

### Two-Phase Coordination Pattern

**Phase 1:** send the cancellation request (cancel/interrupt). **Phase 2:** wait for the signal that **the worker has exited `finally`** or wait for executor termination, and only then declare the worker's resources closed.

If you only wait on `future.get()` and catch `CancellationException`, you are observing the **Future state**, not necessarily the **cleanup-complete state**.

## 8. Java 17: Distinguishing `Future.cancel(true)` from Worker Cleanup Completion

The following example has a `CountDownLatch finished` counted down in the **outermost `finally`**, after `try-with-resources` has closed the resource. `main` only prints once it sees `finished`, so it does not race with cleanup.

Create the file **`FutureCancelCleanup.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancelCleanup {
    static final class TrackedResource implements AutoCloseable {
        private final AtomicBoolean closed;

        TrackedResource(AtomicBoolean closed) {
            this.closed = closed;
        }

        @Override
        public void close() {
            closed.set(true);
        }
    }

    public static void main(String[] args) throws Exception {
        AtomicBoolean closed = new AtomicBoolean(false);
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        CountDownLatch neverOpened = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> future = pool.submit(() -> {
                try {
                    try (TrackedResource resource =
                                 new TrackedResource(closed)) {
                        started.countDown();
                        neverOpened.await();
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            if (!started.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Task not started");
            }

            boolean accepted = future.cancel(true);
            if (!finished.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Cleanup not completed");
            }

            System.out.println("cancelAccepted=" + accepted);
            System.out.println("futureCancelled=" + future.isCancelled());
            System.out.println("resourceClosed=" + closed.get());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac FutureCancelCleanup.java
java FutureCancelCleanup
```

Stdout when the program completes normally:

```text
cancelAccepted=true
futureCancelled=true
resourceClosed=true
```

**Why doesn't this test rely on lucky timing?**

- The worker is submitted and runs in a single-thread executor.
- `main` waits for `started`, proving the worker created the resource and reached the checkpoint inside the task.
- The worker then waits on `neverOpened.await()`; interruption causes `await` to throw `InterruptedException`, even if the interrupt arrives right before it actually blocks.
- `future.cancel(true)` requests interrupting the worker. When the worker exits, `try-with-resources` closes the resource first, and then the outermost `finally` counts down `finished`.
- `main` **waits for `finished` before printing**, instead of seeing `future.isCancelled()` and inferring that `close` has finished.

**One specific limitation:** if the worker fails before entering `try-with-resources` or is cancelled before running, you cannot rely on `finished` inside the body to run. In this program `started` was confirmed, so we know the task was active and had allocated the resource. In real systems, lifecycle design must manage all states: **queued / never started / running / completed**.

**Timeouts do not force `close`:** if `finished.await(5s)` returns false, `main` reports an error; the worker may still be blocked in an operation that does not respond to interruption. `shutdownNow()` attempts to send an interrupt, but cannot guarantee releasing native I/O or external resources.

## 9. `ExecutorService.shutdown()` and `shutdownNow()` Do Not Replace Task Cleanup

A properly shut down executor avoids abandoning workers:

```java
pool.shutdown();
try {
    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
        pool.shutdownNow();
        if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
            reportStuckWorkers();
        }
    }
} catch (InterruptedException e) {
    pool.shutdownNow();
    Thread.currentThread().interrupt();
}
```

This is a **snippet**, where `pool` is an `ExecutorService` and `reportStuckWorkers()` is an application method. Meaning:

1. `shutdown()` stops accepting new tasks, while giving already-accepted tasks a chance to complete normally.
2. `awaitTermination` waits a bounded duration for the executor to actually finish.
3. If the deadline expires, `shutdownNow()` attempts to interrupt running tasks and returns the list of tasks that have not started.
4. Wait a second time to see whether workers actually exited.
5. If the coordinating thread itself is interrupted, it attempts to request cancellation, **restores the interrupt flag**, and exits the wait path.

**Crucial distinction:** `shutdownNow()` does not close task resources on your behalf, nor does it promise that all threads stop immediately. If there are tasks that never ran, `finally` inside those tasks does not execute; pre-prepared resources must be closed by another owner. For shared resources, their lifetime is usually tied to the application/executor owner, not individual tasks.

## 10. Where a Resource Is Opened Determines Who Must Close It

### 10.1. Task Opens Its Own Resource

```java
void runTask(Path path) throws IOException {
    try (InputStream in = Files.newInputStream(path)) {
        readFully(in);
    }
}
```

This snippet requires imports for `IOException`, `InputStream`, `Files`, `Path`, and a `readFully` method. If a worker creates an input stream exclusively for that job, it should close it within that job's scope.

### 10.2. Resource Shared by the Application

```java
void runTask(SharedClient client) {
    client.sendOneRequest();
    // Do not close client; the application owner manages its lifecycle.
}
```

`SharedClient` is an illustrative type, not a built-in JDK class. The task **does not own** the resource, so cancelling one job must not disrupt other jobs by closing the shared client.

### 10.3. Resource Created Before Submission

```java
Resource resource = openResource();
Future<?> f = pool.submit(() -> use(resource));
```

These two lines are a snippet with illustrative names. If `f.cancel(true)` happens **before the task starts**, the lambda may not run, and a `finally` placed **inside the lambda** will never get a chance to close `resource`. Design **clear ownership transfer**:

- Best: open the resource **inside the task** and use `try-with-resources`, if opening beforehand is unnecessary.
- If opening beforehand is required: the creator retains responsibility for closing when the task is rejected/never started, or use an owner object that manages state, ownership handoff, and single-time closing.
- When multiple actors might try to close concurrently, use an idempotent close policy / ownership protocol; do not rely on luck to avoid double-close.

### 10.4. Task with Multiple Resources

```java
try (Reader reader = Files.newBufferedReader(source);
     Writer writer = Files.newBufferedWriter(target)) {
    copy(reader, writer);
}
```

This is a snippet requiring imports for `Reader`, `Writer`, `Files`, `Path`, along with `source`, `target`, and `copy`. Resources are closed in **reverse order of declaration**: `writer`, then `reader`. If one `close` throws an error, Java still attempts to close the remaining resources per `try-with-resources` semantics.

**Do not open expensive resources or ones with side effects in a constructor and hand them to a worker without considering tasks being rejected or cancelled before running.**

## 11. `close()` Can Fail: Do Not Mask the Original Exception

A subtle bug occurs when the body throws an exception and `finally` also throws an exception during `close`:

```java
try {
    doWork();
} finally {
    resource.close(); // If close throws, the original exception may be masked.
}
```

This is a snippet assuming `doWork`/`resource` are defined. With `try-with-resources`, if the **body** throws an exception and `close` also throws an exception, Java preserves the primary exception from the body and adds the `close` error to the **suppressed exceptions** list.

### Java 17: Demonstrating Suppressed Exceptions

Create **`SuppressedCleanupDemo.java`**:

```java
import java.io.IOException;

public class SuppressedCleanupDemo {
    static final class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource r = new FailingResource()) {
            throw new IOException("work failed");
        } catch (IOException e) {
            System.out.println("primary=" + e.getMessage());
            System.out.println(
                    "suppressed=" + e.getSuppressed()[0].getMessage());
        }
    }
}
```

```bash
javac SuppressedCleanupDemo.java
java SuppressedCleanupDemo
```

Exact stdout:

```text
primary=work failed
suppressed=close failed
```

**Takeaway:** if the work fails and the close operation also fails, both errors matter. When logging, record suppressed exceptions (`Throwable.getSuppressed()`) instead of only printing the primary exception's message.

For manual multi-step cleanup, if the first `close` throws an exception, subsequent steps may be skipped. Design nested `finally` blocks, `try-with-resources`, or collect close errors so that **every resource gets a chance to be released**. Do not `return` inside `finally`, as it can **suppress exceptions or return values** from the body.

## 12. Closing a Resource Does Not Always Stop I/O Immediately

Some blocking operations respond to interruption (e.g., `BlockingQueue.take`, `CountDownLatch.await`). However, do not assume that **all blocking I/O** responds to `Thread.interrupt()` in the same way.

- **NIO interruptible channels**: behavior on interrupt/close is specified by the channel type's contract; a blocking operation may be terminated with an appropriate exception when the channel is interrupted/closed.
- **`java.net.Socket`/stream I/O**: behavior depends on the API, runtime, timeout, and platform. Read the contract and set `Socket.setSoTimeout(...)` where appropriate; `Thread.interrupt` is not a universal button to terminate every kind of socket read.
- **A native or third-party library call** may not check interrupts and may continue blocking.
- **`AutoCloseable.close()` can block** during flushing, handshakes, writing data, or waiting for other state; it does not inherently have a deadline.
- **Shutdown hooks** also do not guarantee cleanup if the process is hard-killed or a hook hangs; avoid relying on hooks as the sole protocol protecting critical data.

If you need reliable I/O cancellation, design **timeouts in the right API**, closing the channel/socket from a manager per its contract, or using APIs with explicit cancellation. Do not use `Thread.stop()` to force exit — abrupt termination can break invariants and cause corruption.

## 13. Resource Cleanup May Need Its Own Interrupt Policy

After a worker is interrupted, the thread still has its interrupt flag set (if restored). If the resource's `close()` uses a blocking operation that responds to interruption, **cleanup can be cut short**.

Three principles to consider:

1. **Prefer non-blocking and idempotent cleanup** when designing self-managed resource wrappers.
2. If cleanup must block, define a **deadline**, fallback, logging, and owner responsibilities; do not simply call `close` and hope it finishes.
3. If an implementation must **defer interruption for cleanup**, manipulate the interrupt flag intentionally and **restore the status** afterward; never clear the interrupt flag accidentally.

There is no single pattern right for every `close()`. For file streams that close quickly and do not throw checked exceptions, `try-with-resources` is very clear. For network connections with complex shutdown handshakes, read the contract and design lifecycle management outside the task; even choosing “abort immediately” instead of “flush/commit everything” can be a business decision.

### Why Not Swallow Exceptions in `close`?

```java
finally {
    try {
        resource.close();
    } catch (Exception ignored) {
        // Wrong if we need to know that closing the resource failed.
    }
}
```

This snippet discards all cleanup error information. If a close error cannot propagate because the primary business exception must be preserved, at a minimum **record/attach a suppressed exception** or report the failed cleanup status. Avoid log spam during shutdown, but also do not let the system report “closed” when the resource is still open.

## 14. Ensuring Cleanup Even When a Task Fails Without Interruption

A worker does not only die from `InterruptedException`. It can throw `IOException`, `RuntimeException`, a custom timeout, a validation exception, or return early due to a business condition. Therefore, **placing cleanup at the scope with matching ownership** is a stronger principle than adding `close()` to every `catch` branch.

Good example:

```java
try (Resource r = open()) {
    if (skipThisTask()) {
        return;
    }
    doWork(r);
}
```

This is a snippet; the resource is closed even on the normal `return` path. If you must manually close multiple resources that do not implement `AutoCloseable`, use `try/finally` around each successful acquisition and arrange the release order clearly.

**Avoid invoking untrusted callbacks while holding a mutex or closing a resource** if the callback might block, reenter, acquire locks in reverse order, or throw an exception that interrupts cleanup. When possible, capture an immutable event/snapshot first and invoke callbacks outside the critical section using a separate notification protocol.

## 15. Acquiring and Closing Resources in the Right Order

A safe lifecycle typically follows:

1. **Acquire**: obtain the resource; if acquisition fails, only clean up the parts that were successfully acquired.
2. **Register ownership**: ensure that from the moment of successful acquisition, a scope/owner is responsible for closing it.
3. **Execute**: perform the work; include cancellation points, timeouts, and controlled state.
4. **Cancel**: when a cancellation request arrives, stop accepting more work and help the task exit interrupt-supporting wait points.
5. **Cleanup**: run `finally`/`try-with-resources`; handle close errors and attempt to release all related resources.
6. **Signal completion**: once cleanup is actually done, signal a `CountDownLatch`/completion state with proper happens-before ordering.
7. **Coordinator verifies**: only report "closed" when there is evidence of completion, or surface timeouts/cleanup failures.

### Ownership Note for `ThreadLocal`

A `ThreadLocal` can hold a mutable resource on a thread pool worker. If each task calls `set` without calling `remove` in `finally`, state can persist on the **reused thread** and leak into other tasks. Pattern:

```java
try {
    context.set(taskContext);
    doWork();
} finally {
    context.remove();
}
```

This is a snippet, where `context` is an appropriate `ThreadLocal<?>` and `taskContext` belongs to the task. `remove` clears the thread's binding to the value; **it does not automatically call `close()` on the value object** if it implements `AutoCloseable`. If the value owns real resources, it must be closed separately according to ownership.

## 16. Testing Cancellation Scenarios: Require Cleanup Evidence

### Minimum Scenario Set

| Scenario | What to Verify |
| --- | --- |
| Task returns normally | `close()` is called per scope |
| Body throws an exception | `close()` is still called, original error is not lost |
| Blocking wait throws `InterruptedException` | Worker exits, cleanup executes |
| `future.cancel(true)` while task is running | Do not treat a cancelled `Future` as proof cleanup is done |
| Task cancelled **before starting** | Resources outside the task have an owner that closes them |
| `close` throws an exception | Cleanup error is reported/kept as suppressed appropriately |
| Task ignores interrupt | Coordinator times out, does not claim resource is closed |
| Executor shutdown | No running tasks remain before closing shared resources |
| Multiple resources, one `close` fails | Remaining resources still get a chance to close |
| Shared resource borrowed by task | Cancelling one task does not close the application's resource |

### Use Handshakes Instead of `Thread.sleep`

To reliably test cancelling **after the worker has started**, use a `CountDownLatch started`; to know cleanup has finished, use a `CountDownLatch finished` in `finally` after the close steps. Do not `sleep(20)` and assume the worker is waiting at the right spot; scheduling makes no such guarantee.

### Assert Only After Cleanup Has Actually Completed

A test that only checks:

```java
future.cancel(true);
assert future.isCancelled();
```

is **not enough** to prove the resource was closed. Java `assert` can also be disabled if `-ea` is not enabled. Use your test framework's assertions or an explicit `AssertionError`, along with a `finished` event or true executor termination matching the resource's lifecycle.

## 17. Common Mistakes

| Misconception or Mistake | Consequence | How to Handle |
| --- | --- | --- |
| “`cancel(true)` kills the worker immediately” | Worker may keep running | Cooperative cancellation + timeout |
| “`isCancelled()` means `close` is done” | Cleanup may still be running | Wait for `finished` or real termination |
| “`finally` always runs even if the JVM is killed” | No such guarantee | Out-of-process recovery/idempotency |
| Catching `InterruptedException` and ignoring it | Worker never exits loop, `finally` never runs | Propagate or restore + exit |
| Placing `close` after the body without `finally` | Exceptions/returns skip `close` | `try-with-resources`/`finally` |
| Closing a shared client when one task is cancelled | Breaks other tasks | Identify resource owner |
| Allocating resource before submit, closing only in task | Cancel before start leaks resource | External owner or create inside task |
| Calling `unlock()` without successful acquire | New exception, wrong lock ownership | `finally` only after successful acquire |
| Calling `semaphore.release()` when acquire fails | Artificially inflates permit count | Release only after successful acquire |
| `close()` throws and masks original exception | Loses root cause of failure | `try-with-resources`, suppressed exceptions |
| Multiple closes in one `finally`, first throws | Later resources may not be closed | TWR or separate catch/nested `finally` |
| Claiming all I/O is interruptible | Worker may remain blocked | API-specific cancel/timeout/close |
| Using `Thread.stop()` to force cleanup | Risk of broken invariants/corruption | Cooperative cancellation |
| Using `sleep` to test cleanup timing | Flaky tests | Latches/handshakes |
| Forgetting `ThreadLocal.remove()` | Task state leaks across thread pool | Per-task cleanup in `finally` |
| Completely suppressing `close` errors | Falsely reports shutdown succeeded | Record and report status |

## 18. Production Design Checklist

- **Which resources does the task own exclusively?** Which ones are only borrowed from an application owner?
- Are resources allocated **before or after the task is scheduled**? If the task never runs, who closes them?
- Is **`try-with-resources`** used for `AutoCloseable`? If not, does every successful acquisition have a proper `finally`?
- Do blocking operations **support interruption**? If not, is there a dedicated close/cancel/timeout API?
- When catching `InterruptedException`, does the code **exit** or propagate? Is the flag restored when catching without rethrowing?
- If `close()` throws an exception or blocks, is there a plan to preserve the original error, log it, and enforce a deadline?
- After `future.cancel(true)`, does the coordinator **wait for actual cleanup** before releasing shared resources?
- Is `ExecutorService.shutdownNow()` treated as a cancellation **request** rather than a completion guarantee?
- Are resources opened before a task starts managed by another owner if the task is cancelled/never started?
- If there are multiple resources, are they closed in the proper order and are errors from each `close` handled?
- Are there any `ThreadLocal` values or callbacks/references in the task that need to be cleared?
- Do tests cover **normal return, exception, interrupt, cancel-before-start, cancel-while-running, close failure, and shutdown timeout**?
- If the process crashes before cleanup, does business state have appropriate **recovery/idempotency/lease/transaction** mechanisms?

## 19. Self-Check Questions

**1. Does `Future.cancel(true)` returning true guarantee the file is closed?** No. It indicates cancellation was accepted per the contract; it does not prove the worker has passed through `finally`.

**2. If a worker catches `InterruptedException` and continues an infinite loop, will an outer `finally` run?** Only if the worker actually leaves the `try` block; swallowing the interrupt can keep it from exiting, so cleanup will not run in time.

**3. When should you use `try-with-resources` instead of `try/finally`?** When the resource implements `AutoCloseable` and ownership can be expressed with a clear scope; TWR also handles suppressed exceptions when both the body and `close` fail.

**4. Can a task that never ran execute its internal `finally`?** No. Resources opened before submission must have another owner when the task is cancelled before starting.

**5. Should you call `unlock` if `lockInterruptibly` is interrupted before acquiring?** No. At that point the caller does not own the lock.

**6. Does `shutdownNow()` promise that all workers stop?** No. It attempts to interrupt running tasks; unresponsive tasks may keep running.

**7. Can you rely on `System.exit`/kill for `finally` to run?** No. You must design recovery for abnormal process termination.

**8. Why shouldn't an exception from `close()` mask an exception from the body?** Because the original business error must be preserved; `try-with-resources` keeps it as the primary exception and places the close error in the suppressed list.

**9. Why is closing a shared client in each task's `finally` wrong?** The resource belongs to another owner and may still be in use by other tasks in the same application.

**10. If the interrupt flag is set when cleanup uses a blocking API, what is the risk?** Cleanup may be interrupted immediately or fail early per the API contract; you need a cleanup policy that also preserves cancellation status.

**11. To test whether a task closed its resources, is checking `future.isDone()` == true enough?** No, especially for a cancelled `Future`. You must verify an actual cleanup-completion signal or true executor termination.

**12. Why should `ThreadLocal.remove()` be in `finally`?** Thread pools reuse threads; old bindings can persist across multiple tasks if not removed, causing state and indirect resource leaks.

## 20. Conclusion

**`finally` and `try-with-resources` are cleanup guardrails along normal Java execution paths, not commands that forcibly terminate a task.** To close resources reliably upon cancellation, combine:

1. **Clear ownership** (who opens, who closes, per-task vs. shared resources).
2. **Cooperative interruption** (tasks check signals, exit blocking points, and do not swallow `InterruptedException`).
3. **Scoped cleanup** (`try-with-resources` or `finally` around every successfully acquired resource).
4. **Completion handshakes** (do not confuse a cancelled `Future` with a worker that has finished closing).
5. **Failure handling** (suppressed close errors, timeouts, I/O-specific cancellation APIs, and crash recovery).

Putting these elements in place makes task termination paths **predictable, testable, and free of resource leaks**, without resorting to abrupt thread-termination mechanisms.