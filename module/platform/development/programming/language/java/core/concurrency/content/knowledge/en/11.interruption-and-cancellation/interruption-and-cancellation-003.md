# InterruptedException and Valid Handling Patterns in Java

A thread may be waiting for data, sleeping, waiting for a lock, or waiting on another task. When an application wants to **request that a thread stop what it is doing**, Java commonly uses the **interrupt** mechanism. This is a **cooperative signal**, not a command to kill the thread. Many blocking APIs respond to that signal by throwing `InterruptedException` so application code has the opportunity to cancel work, close resources, or propagate the cancellation signal up to the caller.

The challenge is not just knowing how to `catch (InterruptedException e)`. You need to decide **who owns the cancellation policy**, whether to continue or stop the task, how the thread's interrupt status has been changed, and ensure resources are cleaned up on every exit path.

This lesson belongs to the **Interruption & Cancellation** topic, scoped to **general Java concurrency (Java 17+)**. Framework-specific cancellation mechanisms such as Spring are not covered.

After this lesson, you will be able to:
- Explain the difference between `Thread.interrupt()`, interrupt status, and `InterruptedException`.
- Understand why certain blocking methods throw `InterruptedException` and **clear the interrupt status** when throwing.
- Know the two standard policies: **propagate** or **re-interrupt and exit**.
- Handle interruption properly in `Runnable`, `Callable`, worker loops, `ExecutorService`, and `Future.cancel(true)`.
- Distinguish interruption from timeouts, cancellation, completion status, and resource closing.
- Recognize anti-patterns such as swallowing the exception, continuing indefinitely, accidentally clearing the flag, and treating interrupt as a forced stop mechanism.

## 1. Interrupt Is a Cooperative Signal, Not Thread.stop()

### 1.1. What Is Interrupt Status?

Each `Thread` object has an **interrupted status**. Another thread can request interruption by calling:

~~~java
worker.interrupt();
~~~

This call **does not mean** the worker stops immediately. Depending on what the worker is doing:

- If it is waiting in an interrupt-aware API such as `Thread.sleep(...)`, `Object.wait(...)`, `Thread.join(...)`, `BlockingQueue.take()`, or `CountDownLatch.await()`, the blocking call typically **throws `InterruptedException`** so the worker can decide how to handle it.
- If it is performing CPU computation without checking the status, it may **keep running**.
- If it is calling an I/O API or an external library, behavior may vary: some APIs respond to interruption according to their own contract, while some blocking calls do not unblock immediately. **Do not assume every I/O operation is aborted immediately**.
- If the worker has already completed, calling interrupt does not "undo already finished work".

The fundamental contract: **the requester sends the cancellation signal; the executor cooperates to stop**. A good shutdown protocol typically combines interruption with status checks, resource release, timeouts, and waiting for the worker to actually terminate.

### 1.2. Why Not Use Thread.stop()?

`Thread.stop()` is an unsafe API and has been deprecated. Forced termination can cause a thread to release monitors while an object's invariants are only partially updated, leaving other threads observing an inconsistent state. The modern approach is **cooperative cancellation**: the thread actively exits the processing block at an appropriate point.

`Thread.interrupt()` does not automatically roll back changes, does not call `close()` on every resource for you, and does not force the thread to execute `finally` at the exact instant of the signal.

## 2. Distinguishing Thread.interrupt(), isInterrupted(), and Thread.interrupted()

Three APIs that are easy to confuse:

| API | Who calls / who is checked? | Clears the interrupt status? |
| --- | --- | --- |
| `someThread.interrupt()` | Sends an interrupt request to `someThread` | Not a flag-checking/clearing operation in the caller sense |
| `someThread.isInterrupted()` | Reads the interrupt status of `someThread` | Does **not** clear it |
| `Thread.interrupted()` | Static method that checks the **current thread** | **Yes**, checks and **clears** the status |

**Important point:** Even if you write `t.interrupted()`, it still invokes the **static method** on `Thread`, which checks the thread **executing the call**, not `t`. You should write `Thread.interrupted()` explicitly to avoid confusion.

Standalone Java 17+ example:

~~~java
// InterruptFlagDemo.java
public class InterruptFlagDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        System.out.println("Initial: " + current.isInterrupted());
        current.interrupt();

        System.out.println("After interrupt: " + current.isInterrupted());
        System.out.println("Static check: " + Thread.interrupted());
        System.out.println("After static check: " +
            current.isInterrupted());
    }
}
~~~

~~~bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
~~~

Stdout:

~~~text
Initial: false
After interrupt: true
Static check: true
After static check: false
~~~

The call to `Thread.interrupted()` returns `true` because the status was set, **and clears it at the same time**. Afterward, `isInterrupted()` returns `false`.

**Do not use `Thread.interrupted()` just to "peek" at the flag while expecting another caller to still see it.** If you accidentally clear the interrupt status in a helper, outer layers may not know a cancellation request occurred.

## 3. What Does InterruptedException Mean?

`InterruptedException` is a **checked exception**. Methods that may block and respond to interruption typically declare `throws InterruptedException`; the caller must **propagate** it or **catch and handle** it.

Common examples in Java 17:

| API | Why can it block? | When interrupted while waiting |
| --- | --- | --- |
| `Thread.sleep(...)` | Sleeps for a duration | Throws `InterruptedException` |
| `Thread.join(...)` | Waits for another thread to terminate | Throws `InterruptedException` |
| `Object.wait(...)` | Waits for a condition on a monitor | Throws `InterruptedException` |
| `BlockingQueue.put(e)` | Waits for space in the queue | Throws `InterruptedException` |
| `BlockingQueue.take()` | Waits for an item in the queue | Throws `InterruptedException` |
| `CountDownLatch.await()` | Waits for the count to reach 0 | Throws `InterruptedException` |
| `Semaphore.acquire()` | Waits for a permit | Throws `InterruptedException` |
| `ReentrantLock.lockInterruptibly()` | Waits to acquire the lock, interruptibly | Throws `InterruptedException` |
| `Condition.await()` | Waits for a signal/predicate | Throws `InterruptedException` |
| `Future.get()` | Waits for an asynchronous task to complete | May throw `InterruptedException` on the **thread calling get** |
| `ExecutorService.awaitTermination(...)` | Waits for the executor to terminate | Throws `InterruptedException` |

**Not every waiting API behaves this way.** For example, `ReentrantLock.lock()` does not declare `InterruptedException` and does not exit just because the caller is interrupted, whereas `lockInterruptibly()` is designed for cases where lock acquisition must respond to interruption requests. Some I/O mechanisms respond with different exceptions or their own mechanisms.

### 3.1. Why Is the Flag Usually Cleared When Throwing?

For `Thread.sleep`, `Object.wait`, and `Thread.join`, when the call detects an interrupt and throws `InterruptedException`, the interrupt status is **cleared by API contract**. Many waiting methods in `java.util.concurrent` also throw the exception and consume the status according to their own contracts.

Consequence: code inside `catch (InterruptedException e)` **must not assume** that `Thread.currentThread().isInterrupted()` is still `true`. This is why the **re-interrupt** pattern exists when the current layer cannot propagate the exception upward.

### 3.2. Standalone Example Verifying Status Before and After Catch

~~~java
// InterruptedSleepDemo.java
import java.util.concurrent.CountDownLatch;

public class InterruptedSleepDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                System.out.println("Worker ready");
                ready.countDown();
                Thread.sleep(60_000);
                System.out.println("Unexpected completion");
            } catch (InterruptedException e) {
                System.out.println("Flag in catch: " +
                    Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("Flag restored: " +
                    Thread.currentThread().isInterrupted());
            } finally {
                System.out.println("Cleanup executed");
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("Main finished");
    }
}
~~~

~~~bash
javac InterruptedSleepDemo.java
java InterruptedSleepDemo
~~~

Stdout (with no external interrupt on the main thread):

~~~text
Worker ready
Flag in catch: false
Flag restored: true
Cleanup executed
Main finished
~~~

`ready.countDown()` happens before main calls `worker.interrupt()`. The worker may already be in `sleep` or not have entered `sleep` yet; in either case, `sleep` detects the interrupt and throws. Once thrown, the status is cleared, so the first line in `catch` prints `false`. The code explicitly calls `interrupt()` on the current thread to restore the status. `finally` runs as the worker exits the scope.

**Note:** the example has no second waiting operation in the worker after restoring the flag, because a subsequent blocking call could throw immediately if it checks the interrupt status. In real-world designs, establish a clear exit and cleanup path rather than re-interrupting and continuing to process indefinitely.

## 4. First Valid Policy: Propagate InterruptedException

If your method **can declare `throws InterruptedException`**, the simplest and usually best approach is **not to swallow the signal**. Let the exception propagate to the layer responsible for deciding cancellation.

~~~java
// Illustrative method in an application class:
static String receive(BlockingQueue<String> queue)
        throws InterruptedException {
    return queue.take();
}
~~~

The `receive` method above is only a snippet for illustration; it requires `import java.util.concurrent.BlockingQueue;` in a real file.

### 4.1. Runnable Example: Method Propagates, Worker Decides to Stop

~~~java
// PropagateInterruptedDemo.java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;

public class PropagateInterruptedDemo {
    private static String receive(BlockingQueue<String> queue)
            throws InterruptedException {
        return queue.take();
    }

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                receive(queue);
                System.out.println("Unexpected message");
            } catch (InterruptedException e) {
                System.out.println("Worker cancelled");
                Thread.currentThread().interrupt();
            } finally {
                System.out.println("Worker cleanup");
            }
        });

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
        System.out.println("Main done");
    }
}
~~~

~~~bash
javac PropagateInterruptedDemo.java
java PropagateInterruptedDemo
~~~

Stdout:

~~~text
Worker cancelled
Worker cleanup
Main done
~~~

Calling `started.countDown()` only guarantees the worker has entered the lambda, not necessarily that it is already inside `take()`. However, because the queue is empty and main sets the interrupt, the worker will receive `InterruptedException` in `take()` whether the interrupt arrives before or during the wait. The `receive` layer does not block the cancellation information; only the `Runnable` layer must catch it because `Runnable.run()` does not declare checked exceptions.

### 4.2. Cleaning Up While Still Propagating the Exception

~~~java
// Illustrative code; resource is already open and work is a method that may throw InterruptedException.
try {
    work();
} finally {
    releaseLocalState();
}
~~~

If `work()` throws `InterruptedException`, the `finally` block still runs (under normal JVM execution), and then the exception propagates to the caller. This is usually **clearer** than catching the exception and silently continuing.

For `AutoCloseable` resources, prefer `try-with-resources`, as Java calls `close()` when exiting the scope. Closing a resource does not automatically guarantee the task completed its business logic; if interrupted mid-way, consider an appropriate rollback/compensation protocol.

### 4.3. Do You Need to Re-Interrupt When Propagating?

If you **propagate `InterruptedException` itself**, the interruption signal is already communicated to the caller via the exception; you usually **do not need** to restore the flag in intermediate layers. The final caller decides whether to restore the status or stop.

Do not turn the re-interrupt pattern into a mechanical rule of "always re-interrupt and rethrow everywhere," as that can affect blocking calls in upper layers. What matters is having **a consistent handling contract** and not losing the cancellation request.

## 5. Second Valid Policy: Restore Interrupt and Exit

Some interfaces do not allow the current method to throw checked `InterruptedException`. Examples include `Runnable.run()`, `Supplier.get()`, or callbacks that do not declare checked exceptions. At that boundary, the standard pattern is:

~~~java
// Illustrative code in a Runnable:
try {
    doInterruptibleWork();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    return;
}
~~~

`doInterruptibleWork()` is an illustrative name, not a built-in Java API. The meaning is:

1. Catch `InterruptedException` specifically.
2. **Restore the interrupt flag**, so the thread owner or subsequent code can see that an interruption was requested.
3. **Exit** the current work (return, break out of the worker loop, or transition to shutdown per protocol), avoiding continuing as if everything were normal.

### 5.1. Consumer Loop Waiting on BlockingQueue

~~~java
// Illustrative code in a Runnable; queue and handle are already declared:
while (!Thread.currentThread().isInterrupted()) {
    try {
        Message item = queue.take();
        handle(item);
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    }
}
~~~

This snippet is not standalone because `Message` and `handle` are hypothetical APIs. If `handle(item)` performs I/O that can be interrupted or throws business errors, a follow-up policy must be designed. Repeatedly checking `isInterrupted()` does **not** clear the flag.

**Especially dangerous mistake:**

~~~java
// Anti-pattern: swallow interrupt and continue the loop.
while (true) {
    try {
        queue.take();
    } catch (InterruptedException ignored) {
        // Does not stop, does not notify, does not restore status.
    }
}
~~~

After the blocking call throws, the flag has usually been cleared. The loop keeps waiting and **ignores the cancellation request**. This can prevent `shutdownNow()` or application cancellation mechanisms from achieving the desired result.

Another bad variant is catching, re-interrupting, and then **immediately continuing** to wait on `take()` in an infinite loop. Because the flag remains set, the blocking API may repeatedly throw again, causing an error loop and high CPU usage. If you choose to restore the status, it must be paired with an **exit path**.

### 5.2. What If the Method Must Return a Value?

If the contract does not allow throwing a checked exception, you can:
- Return an explicit result representing **cancelled** if the API supports it.
- Restore the flag and propagate the information using a result type or exception **accepted by the API**.
- Let the thread-management layer decide on retry/cancellation rather than retrying indefinitely yourself.

Do not fabricate a fake success value (such as returning `0` for an incomplete transaction) just to "get the catch block over with." Converting to an unchecked exception may suit some abstractions, but it requires a clear contract; blindly wrapping `InterruptedException` in a `RuntimeException` without restoring the flag can lose the cancellation state for the coordinating layer.

## 6. InterruptedException Does Not Always Mean "Already Stopped"

An interrupted thread **might**:
- Catch the exception and exit cleanly.
- Catch the exception and continue working.
- Be executing code that does not respond to interruption.
- Be cleaning up or executing incomplete I/O or transactions.

Therefore, `interrupt()` is a **request**, not **confirmation that cancellation has completed**. To know that a worker has actually terminated, you can call `join()`, wait on a `CountDownLatch`/`Future`, or use an appropriate completion signal, with a timeout if needed.

Distinguish between these states:

| Event | Certain conclusion |
| --- | --- |
| `worker.interrupt()` is called | An interrupt request was sent per the `Thread` contract |
| `worker.isInterrupted() == true` | The interrupt status is set at the moment of observation |
| Blocking call throws `InterruptedException` | The call exited via the interruption path |
| `worker.join()` returns normally | The worker has terminated |
| `Future.cancel(true)` returns `true` | The `Future` is marked cancelled; an interrupt was requested if the task was running and supports it |
| `Future.isCancelled() == true` | The `Future` is in the cancelled state, **does not prove the worker stopped immediately** |
| `ExecutorService.shutdownNow()` returns | Attempted to stop via interrupt and returned unstarted tasks; **does not guarantee** workers have terminated |

### 6.1. Interrupt Does Not Roll Back

If a task performs:
1. Writing to a file or database.
2. Sending a request.
3. Waiting for a response and getting interrupted.

You cannot infer that step 1 or 2 was automatically reversed. Cancellation is a matter of **lifecycle and business contract**, not just a thread exception. Design transactional boundaries, idempotency, retries, or compensation for your specific system.

## 7. Future.cancel(true) and Interruption in ExecutorService

`ExecutorService.submit(...)` returns a `Future`. With common implementations based on `FutureTask`, `cancel(true)` requests cancellation and **attempts to interrupt the running thread**; however, it does not guarantee the task stops immediately. `cancel(false)` does not request interrupting a running worker.

After a `Future` is cancelled:
- `future.isCancelled()` may return `true`.
- `future.get()` throws `CancellationException` (unchecked), without returning a result even if the task code partially executed.
- The worker may still be cleaning up or may not have responded to the interrupt yet.

### Java 17+ Example Distinguishing Cancelled Future from Worker Completion

~~~java
// FutureCancellationDemo.java
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class FutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        CountDownLatch neverReleased = new CountDownLatch(1);

        try {
            Future<String> future = pool.submit(() -> {
                entered.countDown();
                try {
                    neverReleased.await();
                    return "completed";
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return "stopped cooperatively";
                } finally {
                    finished.countDown();
                }
            });

            entered.await();
            boolean accepted = future.cancel(true);

            finished.await(); // Wait for the task to actually exit scope.
            System.out.println("Cancel accepted: " + accepted);
            System.out.println("Future cancelled: " + future.isCancelled());

            try {
                future.get();
            } catch (CancellationException e) {
                System.out.println("get(): CancellationException");
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("Worker did not terminate");
            }
        }
    }
}
~~~

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Under normal execution without external interruption, stdout:

~~~text
Cancel accepted: true
Future cancelled: true
get(): CancellationException
~~~

Reasoning:
- Main only calls `cancel(true)` after the task has started (`entered.await()`). The task is waiting or about to wait on a latch that is never released.
- Cancelling requests an interrupt; the task catches `InterruptedException`, restores the flag, and leaves the scope. `finished.await()` confirms `finally` ran.
- The `Future` remains **cancelled**, so `get()` throws `CancellationException` even though the callable returned `"stopped cooperatively"` while handling cancellation.
- `pool.shutdownNow()` is the executor cleanup step, not a replacement for the worker handling interruption itself; the example waits for the pool to terminate with a timeout.

**Point to check with other APIs:** Not every `Future` type or asynchronous abstraction implements `cancel(true)` by interrupting the executing thread. Always read the contract of the **specific `Future` implementation**; for instance, `CompletableFuture.cancel(boolean)` has different semantics regarding interruption. Do not infer from the `true` argument a universal guarantee that every kind of async computation is aborted immediately.

## 8. Shutting Down Executors Properly and Handling Coordinator Thread Interruption

A service that owns an `ExecutorService` needs a plan to stop accepting new tasks and wait for submitted tasks to finish. `shutdown()` does not automatically stop tasks waiting indefinitely on a queue or I/O. `shutdownNow()` attempts to interrupt running tasks, but still relies on task cooperation.

### 8.1. Graceful Shutdown Pattern in Java 17

~~~java
// ExecutorShutdownDemo.java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExecutorShutdownDemo {
    public static void main(String[] args) {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            pool.execute(() -> System.out.println("Task finished"));
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                        System.err.println("Executor still running");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
    }
}
~~~

~~~bash
javac ExecutorShutdownDemo.java
java ExecutorShutdownDemo
~~~

In a normal run, stdout:

~~~text
Task finished
~~~

How to read this:
1. `shutdown()` stops accepting new tasks; it does **not** wait by itself.
2. `awaitTermination(...)` waits with a timeout for the executor to terminate.
3. On timeout, `shutdownNow()` requests interruption of running tasks and returns unstarted tasks; it does not guarantee all workers have stopped.
4. If the **thread coordinating shutdown** is interrupted while waiting, preserve the signal with `Thread.currentThread().interrupt()` and have a follow-up policy. This pattern attempts `shutdownNow()` before restoring the flag.

**JDK note:** On Java 17, `ExecutorService` does not provide `AutoCloseable.close()` as in newer versions. Manage shutdown explicitly as shown above rather than assuming `try (ExecutorService e = ...)` compiles on every JDK.

### 8.2. What Happens When Catching InterruptedException from awaitTermination?

This is an interruption of the **caller thread waiting on the executor**, not necessarily an interruption of the workers in the pool. The caller must decide whether to keep waiting under a special protocol or request a stronger shutdown, and then restore the status or propagate according to the contract. Never assume an exception on the caller means the workers are dead.

## 9. Interruptible Locks, Conditions, and Different Waiting Points

### 9.1. Lock.lock() vs. lockInterruptibly()

`ReentrantLock.lock()` acquires the lock without exiting via `InterruptedException`. If the caller is waiting for the lock and gets interrupted, the call normally keeps waiting until the lock is acquired (the interrupt status is preserved/restored per the implementation). Conversely, `lockInterruptibly()` allows lock acquisition waiting to be interrupted.

Standalone Java 17+ example:

~~~java
// InterruptibleLockDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch ready = new CountDownLatch(1);

        lock.lock(); // Main holds the lock.
        try {
            Thread waiter = new Thread(() -> {
                ready.countDown();
                try {
                    lock.lockInterruptibly();
                    try {
                        System.out.println("Unexpected acquisition");
                    } finally {
                        lock.unlock();
                    }
                } catch (InterruptedException e) {
                    System.out.println("Waiter interrupted");
                    Thread.currentThread().interrupt();
                }
            });

            waiter.start();
            ready.await();
            waiter.interrupt();
            waiter.join();
        } finally {
            lock.unlock();
        }

        System.out.println("Main released lock");
    }
}
~~~

~~~bash
javac InterruptibleLockDemo.java
java InterruptibleLockDemo
~~~

Stdout:

~~~text
Waiter interrupted
Main released lock
~~~

Main holds the lock until after `waiter.join()`, so the waiter cannot acquire it. It receives the interrupt and `lockInterruptibly()` throws; the waiter only calls `unlock()` when it actually acquires the lock. `finally` in main releases the lock after the waiter finishes.

**Warning:** Do not place `unlock()` outside the block that runs only after the caller has acquired the lock. If `lockInterruptibly()` throws before succeeding, calling `unlock()` without ownership can throw `IllegalMonitorStateException`.

### 9.2. Condition.await() and Object.wait()

`Object.wait()` must be called while the thread holds the corresponding monitor; while waiting, it **releases the monitor** and must reacquire it before returning per contract. `Condition.await()` typically releases the associated lock while waiting and reacquires it before returning, per the condition/lock contract. Both can throw `InterruptedException`.

When waiting on a predicate, always use a loop:

~~~java
// Illustrative code in a class with lock, condition, and boolean ready:
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    consumeReadyState();
} finally {
    lock.unlock();
}
~~~

`consumeReadyState()` is a hypothetical application method. Here `condition.await()` can throw, so the enclosing method should declare `throws InterruptedException` or catch it according to policy. `finally` releases the lock; do not guess the state of the predicate after being interrupted.

**Why use `while`?** Spurious wakeups can occur, or the state may be changed by another thread before execution resumes, so always re-check the condition.

### 9.3. Thread.sleep Does Not Release Monitors

`Thread.sleep(...)` **does not release** any monitors held by the thread. If a thread sleeps inside `synchronized`, other threads needing the same monitor remain blocked. Therefore, do not use sleep as a way to "give another thread a chance to enter the lock" in a condition protocol. Use `wait/notify` or `Condition` per contract when you need to release the lock while waiting.

## 10. Cooperative Stopping in CPU-Bound Tasks

A computation loop that never calls blocking APIs may **never throw `InterruptedException`** just because another thread calls `interrupt()`. It must actively check the interrupt flag at reasonable points.

~~~java
// CooperativeCpuDemo.java
import java.util.concurrent.CountDownLatch;

public class CooperativeCpuDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (!Thread.currentThread().isInterrupted()) {
                // Illustrative checkpoint; performs no real work.
                Thread.onSpinWait();
            }
            System.out.println("CPU worker stopped");
        });

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();
        System.out.println("Main observed termination");
    }
}
~~~

~~~bash
javac CooperativeCpuDemo.java
java CooperativeCpuDemo
~~~

Stdout in a normal run:

~~~text
CPU worker stopped
Main observed termination
~~~

The thread checks with `isInterrupted()`, so it does not clear the flag; main sends the interrupt and calls `join()` to confirm actual termination.

The example uses spinning for simple illustration, **not as an efficient CPU-bound processing technique**. In a real algorithm, check the flag after each appropriate chunk of work and avoid empty loops that burn CPU. For blocking operations that support interruption, prefer those APIs over manual spinning.

### 10.1. Custom Volatile Flag vs. Interrupt

An application can use `volatile boolean stopRequested` to ask a worker to stop a computation loop, especially when not using blocking APIs. However, if the worker is blocked in `BlockingQueue.take()`, merely setting `stopRequested = true` **does not wake up `take`**. You may need `interrupt`, a sentinel, or a timed poll. Do not maintain two inconsistent stop mechanisms (for example, one place sets a flag and another interrupts, while the worker only monitors one of them).

## 11. Cleanup, try-with-resources, and Business Correctness

### 11.1. Cleanup Must Run When Code Actually Exits Scope

A worker often holds:
- Resources such as `InputStream`, `Reader`, `Socket`, or connections.
- Context state such as `ThreadLocal`.
- Locks or semaphore permits.
- Multi-step update tasks.

When interrupted, design the exit path through `finally` or `try-with-resources`:

~~~java
// Illustrative code in a class; resource and process have appropriate contracts.
try (Resource resource = openResource()) {
    process(resource); // May throw InterruptedException.
} finally {
    threadContext.remove();
}
~~~

`Resource`, `openResource()`, `process(...)`, and `threadContext` are hypothetical names to illustrate structure, not a standalone file. `try-with-resources` calls `close()` when leaving the scope and `finally` cleans up the context. However, **cancellation does not automatically close resources the instant the caller sends an interrupt**: only when execution passes through the cleanup scope, or the owner has a dedicated closing protocol.

### 11.2. Keeping the Interrupt Flag Can Affect Cleanup

After catching and re-interrupting, subsequent blocking calls on the **same thread** may detect the flag and throw immediately. If cleanup needs to wait on an interruptible API, design how it should behave explicitly:
- If possible, let cleanup happen in `finally` before the cancellation signal is propagated to the caller.
- If you must wait on a resource-closing step with a timeout, decide whether to defer, restore, or re-handle the interrupt status per contract, **without accidentally clearing the signal permanently**.
- Do not run unbounded blocking I/O in `finally` and expect cancellation to always complete quickly.
- For permits/locks, only release when actually owned; for per-task `ThreadLocal`, clear mappings in `finally`, especially in worker pools that reuse threads.

There is no single cleanup pattern that fits every API. What must be preserved is **not losing the cancellation request** and **not leaking state or handles** outside their owning scope.

## 12. Distinguishing InterruptedException from TimeoutException and CancellationException

| Type | Where does it usually appear? | Primary meaning |
| --- | --- | --- |
| `InterruptedException` | `sleep`, `join`, `take`, `await`, `Future.get`, `lockInterruptibly` | **The waiting thread** was requested to interrupt |
| `TimeoutException` | `Future.get(timeout, unit)` | The caller timed out waiting; **the task is not necessarily cancelled** |
| `CancellationException` | `Future.get()` after the `Future` was cancelled | The `Future` was cancelled and provides no result |
| `ExecutionException` | `Future.get()` when the `Callable` failed | The task terminated with an exception (cause in `getCause()`) |
| `RejectedExecutionException` | Submitting when an executor is not accepting tasks or is overloaded per configuration | The task was rejected from submission, not interrupted |

For example, `future.get(100, MILLISECONDS)` throwing `TimeoutException` **does not automatically call `future.cancel(true)`**. The caller must decide whether to request cancellation and handle the fact that the task may still be running. Conversely, `Future.get()` may throw `InterruptedException` because the **caller thread** was interrupted while waiting; that **does not mean the running task was necessarily interrupted or cancelled**.

**Do not lump these exceptions into a generic catch and ignore them**: they represent different lifecycle states and require different responses.

## 13. Common Anti-Patterns

| Mistake | Why it is wrong | How to handle it |
| --- | --- | --- |
| `catch (InterruptedException ignored) {}` | Swallows the cancellation request | Propagate or restore + exit |
| Catch, restore flag, then immediately loop on blocking call | Can throw repeatedly, causing a busy error loop | Exit the worker or transition to a shutdown path |
| Catch and `return success` despite incomplete task | Reports false business outcome | Report cancelled/failure per contract |
| Call `Thread.interrupted()` just to check | Clears the current thread's flag | Use `isInterrupted()` if you do not want to clear |
| Use `interrupt()` as "kill immediately" | Worker may not cooperate | Implement cooperative cancellation + wait for termination |
| Hold a lock while waiting indefinitely with no cancellation path | Can prolong contention/deadlock | Design appropriate lock/condition/timeout |
| Call `unlock()` when `lockInterruptibly()` did not succeed | Wrong ownership, another exception | Only unlock inside the scope after acquiring the lock |
| Call `shutdownNow()` and assume all tasks stopped | Only attempts to interrupt; tasks may keep running | Track termination and worker exit paths |
| `Future.get(timeout)` times out and treat task as cancelled | Timeout only stops caller waiting | Cancel explicitly if needed, and monitor completion |
| Rely on `finally` as protection against process kill | JVM crash/halt may not run `finally` | Need recovery/durable consistency if required |
| Reset interrupt status unintentionally | Loses cancellation signal for caller | Only clear when owning the protocol |
| Repurpose `InterruptedException` as an arbitrary business exception | Confuses lifecycle signal with data error | Preserve the interrupted wait/cancellation meaning |

### 13.1. Avoid "Catch Generic Exception and Retry"

~~~java
// Anti-pattern illustrative code:
while (true) {
    try {
        doWork();
    } catch (Exception e) {
        log(e);
    }
}
~~~

If `doWork()` blocks and throws `InterruptedException`, the generic catch may **swallow** it; the thread does not stop. Note that `doWork` and `log` are placeholders, not a standalone Java program.

Separate `InterruptedException` into its own handling branch wherever it can be thrown, before categorizing other errors. If catching `Exception` at a supervisory layer, ensure cancellation signals are not turned into "normal errors, retry immediately."

### 13.2. Not Every Catch Must Re-Interrupt

If the caller genuinely requires **waiting despite interruption** (certain specialized internal mechanisms), it can record the interrupt temporarily, continue waiting, and restore the status upon leaving the scope. However, this is an **intentional exception**, not the default for workers. If the goal is to respond to stop requests, continuing to wait indefinitely usually violates the cancellation contract.

## 14. Design and Self-Check Checklist

### Quick Checklist

1. **Who owns the stop authority?** Main thread, service, executor, or supervisory component?
2. **Where is the worker waiting?** `sleep`, `take`, `await`, lock, I/O, or a CPU loop?
3. **Does the API support interruption?** Read the exact contract; do not guess that every blocking call throws `InterruptedException`.
4. **Can the method rethrow?** If so, prefer propagating `InterruptedException` to the decision-making layer. If not, restore the flag and exit per protocol.
5. **Do all exit paths have cleanup?** `finally`, try-with-resources, unlock/permit/ThreadLocal.
6. **Do you wait to confirm termination?** `join()`/`Future`/`awaitTermination` as appropriate, with timeouts when needed.
7. **Are you confusing timeout with cancellation?** A timed wait timing out does not automatically cancel the task.
8. **Can producers/consumers get stuck indefinitely?** The shutdown protocol must be able to wake waiting workers.
9. **Is business status reported accurately?** A cancelled task must not report success or lose work without recovery.
10. **Have you tested the race between "interrupt already sent" and "not yet entered blocking call"?** Compliant blocking APIs must detect an already-set status; your code must not rely only on sleep timing.

### Self-Check Questions

**1.** Does `worker.interrupt()` guarantee the worker stops immediately?  
**Answer:** No. It is a cooperative request; the worker may catch the exception and continue, or may not have checked the flag yet.

**2.** What is the difference between `Thread.interrupted()` and `Thread.currentThread().isInterrupted()`?  
**Answer:** Both inspect the current thread when called this way, but `Thread.interrupted()` **clears the status**, whereas `isInterrupted()` **does not**.

**3.** After `Thread.sleep` throws `InterruptedException`, what is `isInterrupted()` usually?  
**Answer:** `false`, because the waiting call cleared the status when throwing. If you cannot rethrow and want to preserve the signal for outer layers, call `Thread.currentThread().interrupt()`.

**4.** What should a method declared `throws InterruptedException` do when `queue.take()` is interrupted?  
**Answer:** Usually let the exception propagate to the caller, cleaning up resources in `finally` if needed; do not swallow it.

**5.** `Runnable.run()` does not declare checked exceptions; what should an interrupted worker do?  
**Answer:** One valid option is to catch `InterruptedException`, re-interrupt the current thread, and exit the task; the exact policy depends on the contract.

**6.** Does `Future.cancel(true)` returning `true` prove all side effects of the task have stopped?  
**Answer:** No. The `Future` is marked cancelled and an interrupt is requested when appropriate; the task may still be running or cleaning up.

**7.** If `future.get(timeout)` throws `TimeoutException`, is the task automatically cancelled?  
**Answer:** No. The caller must decide to cancel separately and handle completion.

**8.** Do `lock.lock()` and `lock.lockInterruptibly()` differ while waiting?  
**Answer:** Yes. `lockInterruptibly()` can exit waiting via `InterruptedException`; `lock()` does not have the same checked-exception throwing contract.

**9.** In a worker loop, what does catching `InterruptedException` and continuing `take()` indefinitely cause?  
**Answer:** It swallows the stop signal—or causes a continuous error loop if restored and repeated—preventing shutdown from making progress.

**10.** After catching `InterruptedException` and restoring the flag, should you continue calling `sleep()` as if nothing happened?  
**Answer:** Usually no. `sleep()` may detect the flag and throw immediately; if you want to stop, exit per the protocol.

**11.** Can `join()` be used to confirm a worker has terminated after interruption?  
**Answer:** Yes, if `join()` returns normally. The caller should consider timed `join` and handle the waiting thread itself being interrupted.

**12.** Does `ExecutorService.shutdown()` unblock all tasks currently in `BlockingQueue.take()`?  
**Answer:** No. `shutdown()` does not automatically interrupt or supply items; a worker stop/cancel protocol and waiting for termination are required.

**13.** A worker finishes updating a file and is then interrupted. Does catching `InterruptedException` automatically undo the file update?  
**Answer:** No. You must design appropriate transaction/recovery/compensation if business logic requires it.

**Remember:** `InterruptedException` is a key signal of **cooperative cancellation**. **Propagate** it when possible; if the current layer cannot propagate checked exceptions, usually **restore the interrupt flag and exit**. Always distinguish a **cancellation request** from **completion**, keep cleanup properly scoped, and do not turn interruption into a normal error that gets swallowed.

### Standard References

- Java SE 17, `Thread.interrupt()`, `Thread.interrupted()`, `isInterrupted()`, and `sleep()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17, `InterruptedException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/InterruptedException.html
- Java SE 17, `BlockingQueue`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html
- Java SE 17, `Future`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Future.html
- Java SE 17, `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17, `ReentrantLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html