# Interruptible and Uninterruptible Blocking Points in Java

## 1. Why Does Distinguishing Blocking Points Matter?

A thread can be **blocked/waiting** when waiting for a monitor, a lock, queue data, a signal from another thread, I/O, or elapsed time. When the system wants to stop work—such as canceling a task or shutting down an application—it commonly uses `Thread.interrupt()`. However, **not every blocking point reacts to an interrupt in the same way**.

There are three main categories:

1. **Interruptible blocking points:** the waiting operation can exit via `InterruptedException`, for example `Thread.sleep()`, `Object.wait()`, `Thread.join()`, `BlockingQueue.take()`, `CountDownLatch.await()`, and `ReentrantLock.lockInterruptibly()`.
2. **Blocking points that do not cancel waiting merely due to an interrupt:** for example, a thread waiting to enter a `synchronized` monitor, or `ReentrantLock.lock()`. An interrupt **does not force** another thread to release a lock it holds. The thread may continue waiting until the lock becomes available.
3. **Blocking points with their own reaction mechanisms:** `LockSupport.park()` can return due to an interrupt, but **does not throw `InterruptedException` and does not clear the flag automatically**; I/O through an `InterruptibleChannel` can close the channel and throw `ClosedByInterruptException`.

**Core takeaway:** `interrupt()` is a **cooperative request**, not `Thread.stop()`; it does not force another thread to terminate and does not automatically release all resources held by that thread. Whether cancellation is effective depends on the waiting operation, the interrupt status, and the application code.

This article covers **general Java concurrency** on JDK/Java 17+, without framework dependencies.

## 2. The Interrupt Flag and Basic APIs

Each thread has an **interrupt status** (interrupt flag). Another thread can call:

```java
worker.interrupt();
```

This is a snippet: `worker` is an already-declared `Thread` reference. This action asks the worker thread to pay attention to the interrupt; **it does not guarantee that the worker stops immediately**, nor does it make it throw an exception at every execution point.

Key APIs:

| API | Effect |
| --- | --- |
| `target.interrupt()` | Sends an interrupt signal to the target thread |
| `target.isInterrupted()` | Reads the target thread's interrupt status, **without clearing the flag** |
| `Thread.currentThread().isInterrupted()` | Reads the current thread's flag, **without clearing the flag** |
| `Thread.interrupted()` | Static method that reads **and clears** the interrupt status of the **current thread** |
| `InterruptedException` | Signal thrown by many interruptible waiting operations; **typically the flag has already been cleared when the exception is thrown** |

**Do not confuse the two ways of checking:**

```java
boolean keepFlag = Thread.currentThread().isInterrupted();
boolean consumeFlag = Thread.interrupted();
```

This is an illustrative snippet. `isInterrupted()` preserves the flag; `Thread.interrupted()` clears the flag, so calling it accidentally in a loop can cause the next check to no longer see the cancellation request.

For waiting operations that throw `InterruptedException` such as `sleep`/`wait`/`join`, when catching the exception you usually need to **propagate it** or **restore the flag** with `Thread.currentThread().interrupt()` if you cannot propagate it. Do not restore the flag mechanically in every situation: the caller layer may have already translated the signal into a final cancellation state and will not reuse the thread. What matters is having a **clear interrupt-handling contract** and never silently swallowing the cancellation request.

## 3. Classification Table of Common Blocking Points in the JDK

| Blocking point / API | Interrupt while waiting | Notes |
| --- | --- | --- |
| `Thread.sleep(...)` | **Yes**: throws `InterruptedException` | Does not release held monitors; flag is typically cleared when thrown |
| `Object.wait(...)` | **Yes**: throws `InterruptedException` | Releases the waited-on monitor while waiting; reacquires it before returning/throwing |
| `Thread.join(...)` | **Yes**: throws `InterruptedException` | Interrupts **the joining thread**, does not automatically interrupt the joined worker |
| `BlockingQueue.put()/take()` | **Yes** | Waits for data/capacity; timed `offer/poll` overloads are also interruptible |
| `CountDownLatch.await(...)` | **Yes** | Timed `await(timeout)` returns a boolean; interrupt takes a different path via exception |
| `CyclicBarrier.await(...)` | **Yes** | The barrier can transition to a broken state when one waiter is interrupted |
| `Semaphore.acquire(...)` | **Yes** | `tryAcquire(timeout, unit)` is also interruptible |
| `Semaphore.acquireUninterruptibly()` | **Does not exit on interrupt** | Continues waiting for a permit; preserves/restores interrupt status per contract on completion |
| `ReentrantLock.lockInterruptibly()` | **Yes** | Can stop waiting **before acquiring the lock** |
| `ReentrantLock.tryLock(timeout, unit)` | **Yes** | Returns false on timeout; throws `InterruptedException` when interrupted |
| `ReentrantLock.lock()` | **Does not cancel waiting on interrupt** | Still waits to acquire the lock; preserves interrupt status per contract |
| `synchronized (monitor)` when held by another thread | **No**: no `InterruptedException` | Thread still has to wait for the monitor; the interrupt flag may remain set |
| `Condition.await()/awaitNanos(...)` | **Yes** | Releases the associated lock while waiting; reacquires the lock before continuing |
| `Condition.awaitUninterruptibly()` | **Does not exit on interrupt** | Still waits for predicate/signal, preserving the interrupt status |
| `Future.get()/get(timeout, unit)` | **Yes** | `TimeoutException` is a different outcome from `InterruptedException` |
| `CompletableFuture.get(...)` | **Yes** | `get()` can throw `InterruptedException` |
| `CompletableFuture.join()` | **Does not throw `InterruptedException`** | Can wait regardless of interrupt and preserve the flag; do not confuse with `Thread.join()` |
| `ExecutorService.awaitTermination(...)` | **Yes** | Expiration returns false; interrupt takes a different path |
| `LockSupport.park()/parkNanos(...)` | **Special reaction**: can return on interrupt | Does not clear the flag automatically, does not throw `InterruptedException`; can also return without a signal |
| `InterruptibleChannel` performing blocking I/O | **Yes per channel contract** | Can close the channel and throw `ClosedByInterruptException` |
| `Selector.select(...)` | **Can wake up the select** | Not `InterruptedException`; interrupt acts to wake up the selector and the flag state still needs handling |
| CPU computation loop without flag checks | **Does not stop automatically** | Must check interrupt cooperatively or use another cancellation mechanism |
| `InputStream.read()` / legacy socket I/O in general | **Depends on implementation and I/O object** | No guarantee that every blocking I/O is interruptible; check the specific class contract |

**Important:** the same label “blocking” does not imply the same interrupt semantics. Read the **API signature and contract**; some operations exit via `InterruptedException`, some block uninterruptibly, and some return or throw their own I/O exceptions.

## 4. Java 17+: `Thread.sleep` Responds to Interrupt and Clears the Flag

Create `InterruptSleepDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class InterruptSleepDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                Thread.sleep(60_000);
                System.out.println("Normal sleep completion");
            } catch (InterruptedException e) {
                System.out.println("Flag in catch: "
                        + Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("Flag restored: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "sleeper");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("Main done");
    }
}
```

Compile and run:

```bash
javac InterruptSleepDemo.java
java InterruptSleepDemo
```

Output on a normal run without external interrupts:

```text
Flag in catch: false
Flag restored: true
Main done
```

`started.countDown()` runs before the worker enters `sleep`, and `main` sends `interrupt` after the latch opens. If the interrupt arrives **before** the worker actually calls `sleep`, the next `sleep` still sees the flag set and throws `InterruptedException`. If the worker is already sleeping, the interrupt wakes it up. Both cases lead to the catch block; the long sleep is only there so the worker does not finish on its own before `main` sends the interrupt.

When interrupted, `Thread.sleep` throws `InterruptedException` and clears the interrupt status per its contract. The example **explicitly restores the flag** so that calling layers can see the thread received a cancellation request. In a real application, the worker should usually exit in a controlled manner rather than continuing heavy work after catching an interrupt.

**Do not put `sleep` inside `synchronized` thinking it releases the monitor.** Sleep does not release held locks, even though it can be interrupted.

## 5. Blocking Point That Does Not Support Canceling the Wait: Acquiring an Intrinsic Monitor

An easy-to-miss distinction is that **waiting to enter `synchronized` is not interruptible**. If a monitor is held by thread A, thread B trying to enter a `synchronized (monitor)` block can be in the JVM `BLOCKED` state. Calling `B.interrupt()` does not cause B to throw `InterruptedException` to abandon acquiring the monitor.

### Java 17+: Interrupt Does Not Make a Thread Abandon Waiting for a Monitor

Create `MonitorWaitInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorWaitInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch attempted = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            attempted.countDown();
            synchronized (monitor) {
                System.out.println("Entered after interrupt: "
                        + Thread.currentThread().isInterrupted());
            }
        }, "monitor-worker");

        synchronized (monitor) {
            worker.start();
            attempted.await();
            worker.interrupt();
            // Main still holds the monitor until exiting synchronized.
        }

        worker.join();
        System.out.println("Main done");
    }
}
```

Run:

```bash
javac MonitorWaitInterruptDemo.java
java MonitorWaitInterruptDemo
```

Output:

```text
Entered after interrupt: true
Main done
```

**Explanation:**

1. Main acquires `monitor` before starting the worker.
2. The worker signals that it is about to request the monitor via `attempted.countDown()`.
3. Main sends the interrupt while **still holding the monitor**, so the worker cannot enter the `synchronized` block even if it has already reached that line.
4. When main releases the monitor, the worker acquires it and enters the block. The interrupt flag remains set for the worker to inspect with `isInterrupted()`.
5. The worker does not throw `InterruptedException` merely for waiting on the monitor; the program has no catch block around acquisition.

You can check `Thread.getState()` when a thread is actually waiting for a monitor to observe `BLOCKED`, but `getState()` is only a **snapshot** and should not be used for coordination or timing-based testing.

### Contrast with `Object.wait()`

Even though it also involves an intrinsic monitor, **`Object.wait()` is interruptible**:

- To call `monitor.wait()`, the thread must **already hold** that monitor.
- When starting to wait, the thread **releases the waited-on object's monitor**, allowing another thread to enter, update the condition, and call `notify/notifyAll`.
- When woken up or interrupted, the thread must **reacquire the monitor** per the wait contract before returning or throwing `InterruptedException`.
- If another thread holds the monitor for too long, the interrupted thread may still have to **wait to reacquire the monitor** before the catch block runs. Thus, an interrupt does not guarantee immediate response latency.

When waiting for a condition, always use `while (!condition) monitor.wait()`, not just `if`, because **spurious wakeups** exist and state may change before the thread reacquires the monitor.

## 6. Interruptible Lock Acquisition: `lockInterruptibly()`

`ReentrantLock.lock()` is a lock-waiting operation, but it is **not an interruptible acquisition**. If the lock is held, an interrupt does not make `lock()` fail and exit. If you require **cancellation while waiting for a lock**, use `lockInterruptibly()` or `tryLock(timeout, unit)`.

### Java 17+: Stopping the Wait Before Acquiring a ReentrantLock

Create `InterruptibleLockDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleLockDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch attempted = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            boolean acquired = false;
            try {
                attempted.countDown();
                lock.lockInterruptibly();
                acquired = true;
                System.out.println("Unexpected lock acquisition");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Interrupted while waiting for lock");
            } finally {
                if (acquired) {
                    lock.unlock();
                }
            }
        }, "lock-worker");

        lock.lock();
        try {
            worker.start();
            attempted.await();
            worker.interrupt();
            worker.join(); // Worker has an exit path due to interrupt.
        } finally {
            lock.unlock();
        }

        System.out.println("Main released lock");
    }
}
```

Run:

```bash
javac InterruptibleLockDemo.java
java InterruptibleLockDemo
```

Output if there are no external interrupts:

```text
Interrupted while waiting for lock
Main released lock
```

Main holds `lock` until the worker finishes. The worker cannot acquire the lock, but `lockInterruptibly()` checks for interruption and throws `InterruptedException`. If the interrupt arrives before the worker calls `lockInterruptibly()`, the API also recognizes the interrupt status. Because the worker exits the wait, main can `join` even while still holding the lock.

This pattern is arranged to demonstrate **cancellable lock waiting**. It is not a general recommendation to `join` a worker while holding a lock. With regular `lock()`, holding a lock in main and joining a worker waiting on that lock can deadlock.

**Key rule:** only call `unlock()` if the worker actually acquired the lock. When `lockInterruptibly()` fails with an exception, the worker **does not hold the lock and must not unlock it**. If code wants to try for a bounded duration, use `tryLock(timeout, unit)` and check `boolean acquired`.

### Does `ReentrantLock.lock()` Lose the Flag Since It Is Uninterruptible?

`ReentrantLock.lock()` still waits until it acquires the lock, even if interrupted while waiting; the API preserves the interrupt status per its contract. After acquiring the lock, code can explicitly check `Thread.currentThread().isInterrupted()` and decide not to proceed with a long operation.

**Do not** use `lock()` and expect to catch `InterruptedException` from that call. The `lock()` API does not declare that exception.

## 7. `LockSupport.park`: Wakes Up on Interrupt Without Throwing a Checked Exception

`LockSupport` is a low-level primitive for park/unpark. `park()` can return because:

- A permit was granted via `unpark(thread)`;
- The thread was interrupted;
- A **spurious return** (returning without the expected event).

`park()` **does not** automatically clear the interrupt status and **does not** throw `InterruptedException`. Therefore, code must check the actual condition and the interrupt flag, typically in a loop with an explicit predicate.

### Java 17+: Observing the Flag After Park

Create `ParkInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.LockSupport;

public class ParkInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();
            while (!Thread.currentThread().isInterrupted()) {
                LockSupport.park();
            }

            System.out.println("Flag after park: "
                    + Thread.currentThread().isInterrupted());
            System.out.println("Clear returned: "
                    + Thread.interrupted());
            System.out.println("Flag after clear: "
                    + Thread.currentThread().isInterrupted());
        }, "park-worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
    }
}
```

Run:

```bash
javac ParkInterruptDemo.java
java ParkInterruptDemo
```

Output:

```text
Flag after park: true
Clear returned: true
Flag after clear: false
```

The `while` loop handles **spurious returns**: even if `park()` returns early, the worker does not exit the loop until the flag is set. When the interrupt arrives, `park()` returns or the loop sees the flag is already set. `Thread.interrupted()` reads and **clears** the flag; that is why the last line is `false`.

**Note:** this is an example of the interrupt flag. When implementing a real queue/lock with `LockSupport`, the “can make progress” predicate must be checked using a proper synchronization protocol; `park/unpark` alone does not make arbitrary shared mutable state safe.

## 8. Is “Uninterruptible” Waiting Always Bad?

Not necessarily. Some operations must preserve invariants even if the user has canceled a request. For example, a short update section may wait for a lock, complete an in-JVM commit, and only then respond to the interrupt signal. However, **uninterruptible** means you cannot rely on `interrupt()` alone to enforce a strict wait-time bound at that point.

Some APIs are designed to **keep waiting despite interrupts**, while recording the flag:

- `Semaphore.acquireUninterruptibly()`;
- `Condition.awaitUninterruptibly()` (waiting on a predicate/condition per protocol);
- `ReentrantLock.lock()`;
- `CompletableFuture.join()` (unlike `Thread.join()`).

With these APIs, there must be a mechanism for **forward progress**, another timeout/bound when needed, or a guarantee that resources will eventually be released. `Condition.awaitUninterruptibly()` can wait forever if no appropriate signal/condition occurs; an interrupt alone is not an exit path.

**Do not choose uninterruptible APIs just to avoid handling `InterruptedException`.** Doing so can make the application hard to shut down, keep canceled requests holding threads for a long time, and accumulate waiting work in the system.

### `CompletableFuture.join()` Is Not Like `Thread.join()`

- `Thread.join()` (including timed join) can throw `InterruptedException` when **the waiting thread** is interrupted.
- `CompletableFuture.join()` returns the result or throws `CompletionException`/`CancellationException` accordingly and does not declare `InterruptedException`; an interrupt is not a normal exit path from `join()`'s wait.
- `CompletableFuture.get()`, on the other hand, is an **interruptible** waiting API with `InterruptedException`/`ExecutionException`; the timed overload also throws `TimeoutException`.
- A caller timeout **does not** automatically cancel the running task; a separate cancellation policy is needed.

Therefore, choose based on the **specific API**, not by guessing from the word “join” in the method name.

## 9. Interrupts and Java I/O: Always Check the Specific Class Contract

You cannot say “all I/O in Java is interruptible” or “no I/O is interruptible.” Behavior differs across traditional streams, sockets, NIO channels, and selectors.

### `java.nio.channels.InterruptibleChannel`

Per the `InterruptibleChannel` contract, when a thread is blocked in I/O on a channel implementing this interface and is interrupted, the channel may be closed and the operation throws `ClosedByInterruptException`, with the interrupt status set. If another thread closes the channel while an operation is blocked, it can throw `AsynchronousCloseException`. This is **not** `InterruptedException`.

Crucially, **a closed channel** cannot simply be reused as-is. Code must manage its lifecycle and reopen the resource if needed; do not just catch the exception and retry on the same closed channel.

### `Selector.select()`

With NIO selectors, interrupting a thread inside `select()` has an effect similar to `wakeup()` for channel selection, but it does not mean the operation must throw `InterruptedException`. Code must inspect the select result, the interrupt status, and the selector lifecycle. Do not assume that interrupting a selector automatically cancels all I/O on every registered channel.

### `InputStream.read()` and Traditional Sockets

Interrupt responsiveness **depends on the class and how the resource was created**. An `InputStream` may have no contract to cancel a blocking read via `Thread.interrupt()`. Some socket/channel types have their own close or interrupt mechanisms. On Java 17, you should not assume virtual-thread behaviors (introduced in newer Java versions) apply to platform threads running on JDK 17.

When using I/O, read the contract of the class you use, set socket/channel timeouts where supported, or manage resource closing appropriately. For blocking sockets, distinguish between I/O timeouts and the thread's interrupt status; they are separate mechanisms.

## 10. How Do Interrupt, Timeout, and Cancellation Relate?

Several operations provide both **interruptible waits** and **timeouts**:

| API | Timeout | Interrupt | Typical outcomes |
| --- | --- | --- | --- |
| `BlockingQueue.poll(timeout, unit)` | Yes | Yes | Element / `null` / `InterruptedException` |
| `ReentrantLock.tryLock(timeout, unit)` | Yes | Yes | `true` / `false` / `InterruptedException` |
| `CountDownLatch.await(timeout, unit)` | Yes | Yes | `true` / `false` / `InterruptedException` |
| `Future.get(timeout, unit)` | Yes | Yes | Value / `TimeoutException` / `InterruptedException` / task error |
| `Thread.join(timeout)` | Yes | Yes | Returns `void`; check `isAlive()` afterward |
| `Object.wait(timeout)` | Yes | Yes | Returns; must recheck predicate |
| `Condition.awaitNanos(remaining)` | Yes | Yes | Estimated remaining nanos; check predicate |
| `Semaphore.tryAcquire(timeout, unit)` | Yes | Yes | `true` / `false` / `InterruptedException` |

**Timeout** means the caller's wait duration has expired; the task or producer **may still be running**. **Interrupt** is a signal sent to a thread. **Cancellation** is a task-level decision; it can often use interruption as a delivery mechanism, but it does not mean “all side effects have been successfully canceled.”

For example, `Future.cancel(true)` requests cancellation by attempting to interrupt the thread running the task if appropriate. It cannot guarantee that the task honors interrupts or stops at an unsupported I/O/blocking point. The `Future` state may already be cancelled while the task code is still executing a section that has not responded to the interrupt. Do not use a `Future`'s cancellation flag to infer that external resources have definitely rolled back.

## 11. Designing a Cooperative Interruptible Worker

A processing loop can combine an **interruptible blocking point** with **flag checks in CPU sections**:

```java
// Snippet showing a worker structure, not a standalone Java file.
while (!Thread.currentThread().isInterrupted()) {
    try {
        Task task = queue.take(); // Interruptible.
        process(task);            // May be CPU/I/O; needs its own contract.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        break;
    }
}
cleanup();
```

Here `Task`, `queue`, `process`, and `cleanup` are components that must be declared in the real application. When `take()` is interrupted, the worker restores the flag and exits the loop; cleanup operations run afterward. If `process(task)` runs long CPU work and never checks for interrupts, shutdown **can still be slow** even though `queue.take()` is interruptible.

For long CPU code, check `Thread.currentThread().isInterrupted()` periodically at safe points; determine **after which step** it is safe to stop without corrupting data. For I/O, configure timeouts/resource closing per the API; for locks, consider `lockInterruptibly`; for waiting loops, do not swallow interrupts and continue waiting indefinitely.

### When Cleanup Is Needed

Do not let an interrupt bypass `finally` blocks that release locks, permits, connections, files, or other acquired resources. Conversely, do not **release what was never successfully acquired**:

```java
// Snippet: lock is an already-declared ReentrantLock.
boolean acquired = false;
try {
    lock.lockInterruptibly();
    acquired = true;
    // Perform work under the lock.
} finally {
    if (acquired) {
        lock.unlock();
    }
}
```

This snippet belongs inside a method declared `throws InterruptedException`. This structure distinguishes the success path from being interrupted **before acquiring the lock**, avoiding calling `unlock()` when not the owner.

## 12. Common Mistakes

1. **“`interrupt()` is equivalent to killing a thread.”** False: it only sends a request; code and APIs decide how to respond.
2. **“A thread waiting on `synchronized` will throw `InterruptedException`.”** False: monitor acquisition is not interruptible that way.
3. **“`Object.wait()` and waiting to enter a monitor are the same thing.”** False: `wait` is interruptible and releases the monitor while waiting; waiting to acquire a monitor is not interruptible.
4. **“`ReentrantLock.lock()` will stop waiting when interrupted.”** False: you must use `lockInterruptibly()` or timed `tryLock` if you need an exit path.
5. **“After catching `InterruptedException`, the flag is definitely still true.”** False: many blocking APIs clear the flag when throwing; you may need to restore it.
6. **“`Thread.interrupted()` only reads the flag.”** False: it reads **and clears** the current thread's flag.
7. **“`park()` throws `InterruptedException`.”** False: it returns with the flag preserved; it can also wake up without an interrupt.
8. **“`Thread.sleep()` releases the monitor.”** False: sleep does not release held monitors or locks.
9. **“`CompletableFuture.join()` responds to interrupts like `Thread.join()`.”** False: their semantics differ.
10. **“`Future.cancel(true)` guarantees the task has stopped.”** False: it is a cooperative request and may not have been handled yet.
11. **“Every `InputStream.read()` is woken up by `Thread.interrupt()`.”** There is no general guarantee; check the specific I/O type.
12. **“Interrupting a thread in `InterruptibleChannel` only produces `InterruptedException` and leaves the channel intact.”** False: it can throw `ClosedByInterruptException` and close the channel.
13. **“Using uninterruptible APIs avoids all complexity.”** False: it only shifts the problem to shutdown behavior, backpressure, or deadlocks.
14. **“Once an interrupt is received, no cleanup is needed.”** False: cleanup, rollback/ack, and resource release must still follow the protocol.
15. **“Interrupting a thread waiting on a worker automatically interrupts the worker.”** False: the interrupted thread and the waited-on thread are two different objects.

## 13. Checklist for Choosing a Blocking Point in Java

1. **What is the operation waiting for?** A lock, monitor, queue data, permit, signal, task, CPU, or I/O?
2. **Does the specific API support interruption?** Read the contract; do not infer from the word “blocking.”
3. **What is the response?** `InterruptedException`, boolean/null, returning from `park()`, or an I/O exception like `ClosedByInterruptException`?
4. **Is the interrupt status preserved or cleared?** Check and restore/propagate appropriately; avoid calling `Thread.interrupted()` unintentionally.
5. **Should it wait unboundedly?** If not, choose an API with a timeout and use a shared deadline across multiple wait steps.
6. **Are locks/permits/resources held?** Structure `try/finally`; only release what was acquired.
7. **Do CPU/I/O tasks have check points?** If not, an interrupt will only be noticed at the next blocking point or not at all.
8. **How is the task actually canceled?** Consider `Future.cancel`, cooperative interrupts, status flags, I/O timeouts, and closing resources when necessary.
9. **Does mid-flight cancellation break invariants?** Identify safe stopping points and handle partial side effects.
10. **Can interrupt paths be tested?** Use a latch/lock to place the thread into a controlled waiting state, then send an interrupt and verify exit timing, flag state, and cleanup.
11. **Are multiple locks/waits nested?** Interrupting one blocking point does not automatically untangle a deadlock or make another thread release its lock.
12. **Does application shutdown make progress?** Monitor termination deadlines, remaining waiting threads, and interrupt handling under realistic load.

**Remember:** some Java blocking points **throw `InterruptedException` and exit the wait**, some **keep waiting despite an interrupt**, and some have **their own return/exception mechanisms**. To cancel safely, you must know the exact waiting API, handle the interrupt status properly, design cleanup in `finally`, and never equate interruption with forced task termination.