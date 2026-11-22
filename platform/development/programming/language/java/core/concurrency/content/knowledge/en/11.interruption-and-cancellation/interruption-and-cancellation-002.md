# interrupt(), isInterrupted(), and Thread.interrupted() in Java

## 1. Interrupt Is a Cooperative Signal, Not a Command to Force-Stop a Thread

In Java concurrency, a thread sometimes needs to ask another thread to **stop its current work**: a user cancels a task, the application shuts down, a request exceeds its deadline, or a group of workers no longer needs the result. Java's fundamental mechanism for this is **interrupt**.

The most common misconception: **`thread.interrupt()` is not equivalent to `Thread.stop()`**. It does not force running Java code to stop at an arbitrary point, does not roll back data updates, and does not automatically close all I/O. An interrupt is a **cooperative signal**. The receiving thread must reach an appropriate recognition point, then execute its cancellation policy, clean up resources, and terminate or continue according to its contract.

Three core methods:

- `thread.interrupt()`: requests interruption of the **target thread object**. Typically sets the target thread's *interrupt status*; if the thread is waiting in an interruptible method, it may cause that method to terminate with `InterruptedException` or an API-specific mechanism.
- `thread.isInterrupted()`: **reads the target thread's interrupt status** without **clearing the flag**.
- `Thread.interrupted()`: a **static** method that checks the interrupt status of the **currently executing thread** and **clears that status** upon reading (test-and-clear). It does not take a target object.

This lesson is within the scope of **general Java concurrency**, focusing on the Thread API and cancellation coordination in the JDK; it does not use any framework-specific mechanisms.

### Learning Objectives

After this lesson, you should be able to:

1. Compare the meaning, target, and side effects of the three APIs.
2. Explain why `InterruptedException` typically clears the interrupt flag and when to restore it with `Thread.currentThread().interrupt()`.
3. Write a worker that checks for interrupts during computation and handles cancellation when `sleep`/`wait`/`join`/`Condition.await` is interrupted.
4. Distinguish between a cancellation request and confirmation that cancellation has completed; use `join`, `Future`, or another coordination mechanism to wait safely.
5. Identify mistakes such as swallowing interrupts, accidentally clearing the flag, misusing the static method, and assuming every blocking API is interruptible.
6. Understand the limitations of interrupts regarding intrinsic monitors, I/O, executors, cancellation, and the Java Memory Model.

## 2. Exact Comparison Table of the Three APIs

| API | Who usually calls it? | Whose status is examined? | Does checking clear the interrupt flag? | Purpose |
| --- | --- | --- | --- | --- |
| `target.interrupt()` | The thread requesting cancellation or the target thread itself | `target` | Not a read/clear operation; sends an interrupt request | Ask the target thread to notice the signal |
| `target.isInterrupted()` | Any thread holding a reference to `target` | `target` | **No** | Observe the current flag |
| `Thread.interrupted()` | The **currently running** thread | The **current** thread | **Yes** | Check and consume the flag |
| `Thread.currentThread().isInterrupted()` | The currently running thread | The current thread | **No** | Self-check while preserving the flag |

### 2.1. Confusing Syntax

~~~java
// Illustration only, not a standalone program.
Thread worker = ...;

worker.interrupt();     // Sends an interrupt to worker.
worker.isInterrupted(); // Reads worker's flag without clearing it.

Thread.interrupted();   // Reads AND CLEARS the flag of the thread calling this line.
~~~

**Do not infer from a reference object that a static method inspects that object.** Although Java allows calling a static method through an expression of type `Thread`, writing `worker.interrupted()` is misleading syntax and still invokes the static method for the **current thread**, not to check `worker`. Always write `Thread.interrupted()` when you intentionally want to test-and-clear **yourself**.

`interrupt()` returns `void`, so no boolean indicating "cancellation succeeded" is returned from the call. `isInterrupted()` and `interrupted()` return a boolean representing **the flag state at the moment of observation**, not a conclusion that the business operation has stopped properly.

## 3. The Interrupt Flag and How It Is Recognized

A thread has an interrupt status. A typical flow:

~~~text
Thread A:                         Thread B:
  target.interrupt()  --------->     interrupt flag is set
                                     |
                                     +--> polling isInterrupted()
                                     |      sees true, cleans up, exits
                                     |
                                     +--> sleep/wait/join/await()
                                            interrupted with
                                            InterruptedException
                                            (status is usually cleared)
~~~

What happens next depends on **where the thread is at that moment** and **which API it is executing**:

- If it is running a normal computation loop, Java does not automatically throw an exception into an arbitrary computation instruction. It may continue running until it checks the flag itself.
- If it is waiting in an interruptible version of `Thread.sleep`, `Object.wait`, `Thread.join`, or `Condition.await`, the wait usually responds with `InterruptedException` and the interrupt flag is **cleared by contract**.
- If it is using `ReentrantLock.lockInterruptibly()` or `BlockingQueue.take()`, an interrupt request can terminate the wait with `InterruptedException`.
- If it is waiting to **acquire an intrinsic monitor** to enter `synchronized`, an interrupt does not cause the thread to exit the monitor-waiting state. The flag may be set, but the thread only reacts when it reaches a point capable of handling it.
- If it is inside an I/O operation, the response depends on the API: some NIO blocking channels have their own interrupt/channel-closing rules; you must not apply a blanket conclusion to every I/O source.

Therefore, **sending an interrupt** and **the thread completing** are two different events.

### 3.1. Interrupt Arriving Before a Sleep Call

If the current thread already has its interrupt flag set when calling `Thread.sleep(...)`, the call may throw `InterruptedException` immediately instead of sleeping for the full duration. This allows a worker to recognize a cancellation request even if the signal arrives before the wait point.

Do not use `Thread.sleep(100)` to "ensure" another thread has processed an interrupt. Sleep only affects the scheduling of the **calling thread**, not the state of the worker.

### 3.2. Interrupt Is a Request, Not Forced Termination

For example, a thread that never checks the flag and only runs an infinite computation:

~~~java
// Incorrect regarding cancellability; not a standalone program.
for (;;) {
    computeNextStep();
}
~~~

If `computeNextStep` does not use interruptible primitives or check the flag itself, calling `interrupt()` from outside may **never stop the loop**. A good cancellation protocol must design **cooperative cancellation points** at places where cleanup and safe exit are possible.

## 4. Example 1 — Test-and-Clear with Thread.interrupted() (Java 17+)

To understand the difference without depending on the scheduler, we use **the main thread itself** as the test subject. The program explicitly clears the initial flag, sets it again, observes it, and verifies that it gets cleared.

Create the file `InterruptFlagDemo.java`:

~~~java
public class InterruptFlagDemo {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        Thread.interrupted(); // Ensure the initial state for the experiment is clear.
        current.interrupt();

        System.out.println("isInterrupted #1 = "
            + current.isInterrupted());

        System.out.println("interrupted #1 = "
            + Thread.interrupted());

        System.out.println("isInterrupted #2 = "
            + current.isInterrupted());

        System.out.println("interrupted #2 = "
            + Thread.interrupted());
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac InterruptFlagDemo.java
java InterruptFlagDemo
~~~

Stdout when no external thread interferes with main's state:

~~~text
isInterrupted #1 = true
interrupted #1 = true
isInterrupted #2 = false
interrupted #2 = false
~~~

Step-by-step explanation:

1. `current.interrupt()` sets the current thread's interrupt flag.
2. `current.isInterrupted()` only **reads** the status, so the first result is `true` and the flag remains set.
3. `Thread.interrupted()` returns `true` **and simultaneously clears the flag**.
4. The subsequent `isInterrupted()` call returns `false`.
5. The next `Thread.interrupted()` call returns `false` because the flag was already consumed in step 3.

**Practical takeaway:** Do not insert `Thread.interrupted()` into logging or a conditional statement that only needs to observe the flag. Because it clears the flag, caller-layer code downstream may lose the cancellation signal.

## 5. Example 2 — Calling interrupt() on a Sleeping Thread (Java 17+)

This example demonstrates receiving the signal via `InterruptedException`. Use `CountDownLatch` to ensure `main` only sends the interrupt after the worker has entered the relevant code section; do not use `Thread.sleep` to guess timing.

Create the file `InterruptSleepDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptSleepDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch entered = new CountDownLatch(1);
        AtomicBoolean caught = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            entered.countDown();

            try {
                for (;;) {
                    Thread.sleep(1_000);
                }
            } catch (InterruptedException ex) {
                caught.set(true);

                // Since sleep usually clears the flag, we restore it
                // so caller/cleanup code can observe it.
                Thread.currentThread().interrupt();
                restored.set(
                    Thread.currentThread().isInterrupted()
                );
            }
        }, "interruptible-worker");

        worker.start();
        entered.await();

        worker.interrupt();
        worker.join();

        System.out.println("caught = " + caught.get());
        System.out.println("restored = " + restored.get());
    }
}
~~~

Compile and run:

~~~bash
javac InterruptSleepDemo.java
java InterruptSleepDemo
~~~

Output when the worker encounters no unexpected errors:

~~~text
caught = true
restored = true
~~~

**Why is there no race condition that changes the output?**

- The worker counts down the latch before entering the sleep loop; `main` waits on the latch before sending the interrupt. If the interrupt arrives **before** the first sleep, `sleep` still sees the flag and throws `InterruptedException` upon entry; if it arrives during sleep, the wait is interrupted.
- The sleep loop runs forever if no interrupt is received, so the worker cannot finish before the cancellation request.
- The worker catches the exception, records `caught=true`, restores the interrupt flag, and records `restored=true`.
- `main` calls `join()` to wait for the worker to terminate before reading the `AtomicBoolean` results. Output does not depend on thread log ordering because only `main` prints.

**Do not rely on `worker.isInterrupted()` after the thread is `TERMINATED` as the sole proof that it was ever interrupted.** Once a thread has finished, observing the object's flag does not replace having the worker record its handling state or report results through a coordination channel.

### 5.1. Why Catch and Then Re-Interrupt?

Some waiting APIs such as `Thread.sleep` throw `InterruptedException` and **clear the interrupt status**. If the current method is inside `Runnable.run()` and cannot declare `throws InterruptedException`, a practical pattern is:

~~~java
// Runnable pattern, not a standalone program.
try {
    performInterruptibleWork();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt(); // Restore flag.
    return; // Stop the task or begin cleanup per contract.
}
~~~

Restore the flag so higher layers or appropriate cleanup code can observe the cancellation request; do **not** continue performing side effects as if the task were never cancelled. If the method can declare `throws InterruptedException`, propagating the exception upward is usually clearer.

Another case is when the current layer **fully handles** the interrupt according to its protocol and intentionally continues; in that case, keeping or clearing the flag must be **deliberately documented**, rather than losing the signal through an empty catch block.

## 6. Example 3 — A Computation Loop Polling isInterrupted() (Java 17+)

For CPU-bound work that does not call `sleep`, `wait`, or `take`, the thread must poll for interruption itself to exit. A simple approach is `!Thread.currentThread().isInterrupted()`.

Create the file `InterruptPollingDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class InterruptPollingDemo {
    public static void main(String[] args)
            throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean noticed = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            started.countDown();

            while (!Thread.currentThread().isInterrupted()) {
                Thread.onSpinWait();
            }

            noticed.set(true);
        }, "polling-worker");

        worker.start();
        started.await();

        worker.interrupt();
        worker.join();

        System.out.println("noticed = " + noticed.get());
        System.out.println("finished = " + !worker.isAlive());
    }
}
~~~

Compile and run:

~~~bash
javac InterruptPollingDemo.java
java InterruptPollingDemo
~~~

Output:

~~~text
noticed = true
finished = true
~~~

The worker does not rely on a waiting API throwing an exception; it simply polls the flag. `main` sends the signal and then calls `join()` to confirm the loop has exited.

**Do not use this infinite spin loop as a typical production worker.** `Thread.onSpinWait()` is only an optimization hint for spin loops; it does not create a CPU-saving wait state, does not replace a blocking queue, and does not provide synchronization guarantees. In real applications with actual tasks, check the flag between units of work, or use an appropriate blocking primitive to avoid burning CPU.

### 6.1. What About Calling Thread.interrupted() in the Loop Condition?

You can also write:

~~~java
// Illustrative pattern, not a standalone program.
while (!Thread.interrupted()) {
    doSmallUnit();
}
~~~

When `Thread.interrupted()` detects that the flag is `true`, it **simultaneously clears the flag**. The loop will exit, but if subsequent code needs to see the flag, it will no longer find it set. It is usually better to **poll without consuming the flag** using `isInterrupted()`. Only use `Thread.interrupted()` when there is a clear reason to handle and clear a received signal.

## 7. An Example of a Static Method Easy to Misuse

A snippet that looks like it is asking "has the worker been interrupted?":

~~~java
// Semantically incorrect illustration; not a standalone program.
Thread worker = new Thread(() -> doWork());

boolean result = worker.interrupted(); // Does NOT check worker!
~~~

`interrupted()` is a static method: it checks/clears the flag of the **thread executing that line**, not `worker`. The result depends on the caller's state.

Write it properly:

~~~java
// Correct illustration; not a standalone program.
boolean workerFlag = worker.isInterrupted();
boolean myFlagWithoutClear =
    Thread.currentThread().isInterrupted();
boolean myFlagWithClear = Thread.interrupted();
~~~

When debugging, note **which thread** owns the flag and at **what point in time**. A flag can be cleared by the receiving thread itself when an interruptible API throws `InterruptedException` or when `Thread.interrupted()` is called. A single reading of `isInterrupted() == false` does not prove that the worker was never sent an interrupt.

## 8. InterruptedException and the Proper Handling Contract

### 8.1. Propagate Upward or Restore the Flag

Two patterns to remember:

**Pattern A — propagate the cancellation request to a caller with a `throws` contract:**

~~~java
// Method pattern, not a standalone program.
void doStep() throws InterruptedException {
    Thread.sleep(100);
    // Only proceed with the next part if not interrupted during sleep.
}
~~~

**Pattern B — cannot declare `throws` in `Runnable`:**

~~~java
// Runnable pattern, not a standalone program.
Runnable task = () -> {
    try {
        doStep();
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        // Perform cleanup if needed, then return.
        return;
    }
};
~~~

If the method has already performed some side effects before the interrupt, the caller needs to know the "partially completed" state according to the contract. An interrupt does not automatically roll back file writes, memory mutations, or remote queries.

### 8.2. Why Is an Empty Catch Dangerous?

~~~java
// Incorrect in many cancellation protocols; not a standalone program.
try {
    blockingCall();
} catch (InterruptedException ignored) {
    // Ignore; continue as if no cancellation request was received.
}
~~~

The waiting call usually cleared the flag before throwing the exception. With an empty catch, outer code no longer has the flag to detect, causing **lost cancellation**. The application may fail to stop at shutdown or a task may run past its deadline.

Restoring is not always mandatory: a specialized management layer may intentionally handle the interrupt and continue per its contract. However, **mindlessly swallowing it** is a common bug.

### 8.3. Do Not Confuse the Exception with a Normal Business Error

`InterruptedException` means **a waiting operation was interrupted**; it does not prove that prior results of the entire task were rolled back and does not always indicate a bug. Often it is part of cancellation/control flow.

When a worker receives `InterruptedException`, choose a clear policy:

1. Close or release resources according to proper ownership.
2. Preserve state invariants (do not hold locks indefinitely, do not leave data half-updated).
3. Return a cancelled/failed outcome via the task API if needed.
4. Terminate, propagate the exception, or restore the flag depending on the abstraction layer handling it.

In code using `Lock`, always use `finally` to unlock if acquisition succeeded, whether the task completes normally or is interrupted.

## 9. Which Blocking APIs Respond to Interrupt?

| Situation | Typical behavior on Java 17+ | Notes |
| --- | --- | --- |
| `Thread.sleep(...)` | Throws `InterruptedException` and clears flag | Does not automatically release monitors held by the thread |
| `Object.wait(...)` | Throws `InterruptedException`; must reacquire monitor before returning | Must hold the correct object's monitor; wait inside a `while` loop |
| `Thread.join()` | If the thread **calling join** is interrupted, `join` throws `InterruptedException` | Interrupts the waiter, does not mean the joined thread was interrupted |
| `Condition.await()` | May throw `InterruptedException` and returns with the lock reacquired | Predicate must be rechecked in a `while` loop |
| `BlockingQueue.take()` | Typically throws `InterruptedException` when interrupted while waiting | Queue still needs a valid producer/consumer protocol |
| `CountDownLatch.await()` | Throws `InterruptedException` when waiting is interrupted | Does not automatically set count to 0 |
| `Semaphore.acquire()` | May throw `InterruptedException` | Does not automatically release permits acquired in earlier steps |
| `ReentrantLock.lockInterruptibly()` | Waiting to acquire the lock can be interrupted | Must unlock if acquisition succeeded |
| `ReentrantLock.lock()` | Does not stop waiting solely because of an interrupt | Flag may remain set for later handling |
| Waiting to **enter `synchronized`** | Interrupt does not terminate waiting for the monitor | Different from `Object.wait()` inside a monitor |
| `CompletableFuture.cancel(true)` | Does not use `mayInterruptIfRunning` to control execution per API contract | Do not infer that the underlying task was interrupted |
| `Future.cancel(true)` | Requests cancellation and may send an interrupt to the running task | Best-effort only; does not guarantee side effects stop immediately |

**Do not overgeneralize about I/O:** For example, some NIO interruptible channels throw `ClosedByInterruptException` and close the channel when the waiting thread is interrupted, while other blocking I/O types have their own contracts. Check the exact Javadoc of the resource you are using.

A method having "blocking" in its description does not mean it will always throw `InterruptedException`; both the API family and the timing of interrupt handling matter.

### 9.1. Thread.join() Is Different from interrupt(thread)

If `main` is in `worker.join()` and another thread calls `main.interrupt()`, **`main`** may receive `InterruptedException` from `join()`. `worker` is not automatically interrupted by `main`, so it may continue running.

Conversely, if `main` calls `worker.interrupt()` while `worker` is waiting, `worker` may receive the interrupt; `main` still needs `join()` or another mechanism if it needs confirmation of completion.

Do not use the `join` method name as proof that the work succeeded; it only waits for the thread to terminate. Task errors must be surfaced through a separate channel if the caller needs to handle them.

## 10. Example 4 — Future.cancel(true) Requesting Task Cancellation (Java 17+)

An executor manages its worker threads, so callers typically **do not hold a reference to call `worker.interrupt()` directly**. When submitting a task, `Future.cancel(true)` is the mechanism to request cancellation. The task still must cooperate, such as catching `InterruptedException` during `sleep`.

Create the file `FutureCancellationDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FutureCancellationDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch finished = new CountDownLatch(1);
        AtomicBoolean noticedInterrupt = new AtomicBoolean();

        try {
            Future<?> future = pool.submit(() -> {
                entered.countDown();
                try {
                    for (;;) {
                        Thread.sleep(1_000);
                    }
                } catch (InterruptedException ex) {
                    noticedInterrupt.set(true);
                    Thread.currentThread().interrupt();
                } finally {
                    finished.countDown();
                }
            });

            entered.await();
            boolean requestAccepted = future.cancel(true);
            finished.await();

            System.out.println("cancel accepted = " + requestAccepted);
            System.out.println("future cancelled = " + future.isCancelled());
            System.out.println("worker noticed = " + noticedInterrupt.get());
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.out.println("pool still shutting down");
            }
        }
    }
}
~~~

Compile and run:

~~~bash
javac FutureCancellationDemo.java
java FutureCancellationDemo
~~~

Typical output when the task has no other errors and the executor stops within 5 seconds:

~~~text
cancel accepted = true
future cancelled = true
worker noticed = true
~~~

Analysis:

- `entered` ensures the task has actually started running and entered the code region before the caller cancels.
- `cancel(true)` requests cancellation and permits interrupting a running worker. This is not a general promise that any task can be forced to stop within a bounded time.
- In the example, the `sleep` loop responds to the interrupt; the catch marks the state, restores the flag, and exits.
- `finished.await()` confirms that **the task's cleanup code has reached the end**, which is distinct from `future.isCancelled()` alone. The caller reads `noticedInterrupt` after the latch for a stable observation.
- `shutdownNow()` requests interruption of active workers and returns a list of tasks that had not started; it does not guarantee every task terminates immediately; `awaitTermination` waits up to the timeout.
- If the inner task does not check for interrupts or is stuck in a non-cancellable API, `cancel(true)` may mark the future as cancelled while the actual code is still running.

Do not use `future.isCancelled()` as proof that a transaction was rolled back, a file was closed, or a network operation has stopped. Distinguish **Future state** from **external resource state**.

## 11. Memory Model: Interrupt and Happens-Before

The Java Memory Model has an important rule: **an action that interrupts a thread synchronizes-with (establishes a happens-before relationship with) the point where the target thread detects the interrupt** (for example, checking via `isInterrupted()`/`Thread.interrupted()` or receiving `InterruptedException` per the appropriate API).

This helps publish updates performed before the interrupt action to the detection point in the target thread. However, interrupt should not be used as an **arbitrary data-passing protocol** or as a replacement for a business-state notification primitive.

An example to distinguish:

~~~java
// Illustration only, not a standalone program.
payload = prepareData();
worker.interrupt(); // Cancellation signal, with an HB edge when the worker detects it.
~~~

If the worker actually detects the interrupt per contract, the sender's actions prior to the interrupt have an appropriate happens-before relationship. However:

- If the worker never checks and never enters an interruptible API, you have no detection point to rely on.
- If multiple threads also update `payload` concurrently, you must protect it with a separate synchronization protocol.
- If you need to pass work/results across multiple rounds or multiple producers, use `BlockingQueue`, `Future`, or a data structure with a clear memory-consistency contract.
- If you need to wait for the worker to finish, `join()`/latch/future remains the waiting mechanism; `interrupt()` is only a request.

`volatile boolean cancelled` or `AtomicBoolean` can also serve as a cancellation flag protocol when the worker only does CPU work. However, updating a standalone flag may **fail to wake up** a thread blocked on a queue/sleep/wait. Interrupts combined with interruptible wait points are usually more appropriate in that case.

## 12. Designing an Interruptible Worker Properly

### 12.1. Break Tasks into Small Units

To cancel responsively without checking the flag on every single operation, divide work into bounded steps:

~~~java
// CPU work handling pattern, not a standalone program.
void runTask() {
    while (!Thread.currentThread().isInterrupted()) {
        if (!hasMoreWork()) {
            return;
        }
        processOneBoundedUnit();
    }
}
~~~

Conditions for this model to be responsive:

- `processOneBoundedUnit()` must have a bounded duration or additional check points.
- If a method blocks on non-interruptible I/O, the flag may be set while the thread remains stuck.
- Side effects that have already occurred must have idempotency/compensation rules if retries are needed.
- On exit, resources must be cleaned up, which can be placed in `finally` or try-with-resources.
- If the API needs to report the cancellation reason, provide an appropriate result; do not just log and disappear.

### 12.2. Do Not Stop Another Thread with Thread.stop()

`Thread.stop()` is unsafe because it can stop a thread while holding locks or breaking invariants, and this API is deprecated. The right choice is usually **cooperative cancellation** via interrupts/flags, combined with completion conditions, deadlines, and releasing resources owned by the worker.

### 12.3. Cleanup and the Interrupt Flag

If cleanup involves interruptible waiting operations, **restoring the flag immediately** and then calling those waits may cause them to throw `InterruptedException` right away. How you order restore, cleanup, and propagation must follow the contract and resource safety.

A simple pattern when catching at the boundary of a `Runnable`:

~~~java
// Logic pattern, not a standalone program.
boolean interrupted = false;
try {
    doInterruptibleWork();
} catch (InterruptedException ex) {
    interrupted = true;
} finally {
    releaseResourcesWithoutUnboundedWait();
    if (interrupted) {
        Thread.currentThread().interrupt();
    }
}
~~~

This pattern only applies if cleanup does not depend on a long interruptible wait and there are no other exceptions to handle. In real applications, you must consider cleanup ordering, additional exceptions, and propagating the signal back to the layer owning the task. The core principle is **never accidentally lose the cancellation request**.

## 13. Common Mistakes

| Mistake | Why It Is Wrong | Right Approach |
| --- | --- | --- |
| Treating `interrupt()` as force-stop | The worker may not cooperate | Design check points and interruptible waits |
| Using `target.interrupted()` to query target's flag | It is a static method for the **current thread** | Use `target.isInterrupted()` |
| Calling `Thread.interrupted()` to "log status" | Clears the flag unintentionally | Use `Thread.currentThread().isInterrupted()` |
| Empty `catch (InterruptedException)` | Waiting API usually cleared the flag; cancellation notice is lost | Propagate or restore and exit per contract |
| Calling `interrupt()` and assuming the task has stopped | It is only a request; the task may still be running | Wait with `join`, latch, or lifecycle outcome |
| Manually throwing `InterruptedException` everywhere when the flag is true | May violate the API's exception contract | Handle according to design and appropriate cancellation points |
| Calling `Thread.sleep` to "wait for worker to finish cancelling" | Sleep does not confirm completion | Use `join`/`Future`/`CountDownLatch` |
| Assuming interrupt unlocks a blocked `synchronized` | Entering an intrinsic monitor is not interruptible | Design lock ordering or choose `lockInterruptibly` if needed |
| Assuming interrupt cancels all I/O | I/O APIs have different contracts | Check the API, timeouts, and resource closing |
| Using `Future.cancel(false)` and expecting a running worker to be interrupted | `mayInterruptIfRunning=false` does not request interrupting a running worker | Choose `true` when appropriate; task must still cooperate |
| Assuming `future.isCancelled()` = cleanup finished | Future state does not equal side-effect lifecycle | Coordinate completion confirmation separately |
| Reading the flag after the worker has terminated to infer history | The flag at a later point is not a log of all interrupts | Record state inside the task; use a result channel |
| Retrying a task after interrupt without considering idempotency | May duplicate side effects | Design retries and compensation per business logic |

## 14. Testing in Practice

### 14.1. Controlled Cancellation Testing

Do not write tests that rely on `Thread.sleep(50)` in `main` and guess that the worker has entered a waiting state. Instead:

1. Use `CountDownLatch` or a similar primitive to know when the worker has entered the code under test.
2. Send `interrupt()` or `Future.cancel(true)`.
3. Wait for termination confirmation using `join`, a latch, or a `Future` per the contract.
4. Verify that the task preserves invariants, releases locks, closes resources, and does not ignore the cancellation request.
5. Set a timeout so the test does not hang indefinitely if code intentionally fails to cooperate.
6. Distinguish between "future was cancelled" and "worker actually reached cleanup."
7. Test both the case where the interrupt arrives before the worker enters `sleep` and while the worker is waiting.
8. For CPU-bound workers, test self-polling of the flag; for blocking workers, test the actual API the worker uses.

### 14.2. Observation and Debugging

- Thread dumps help inspect `RUNNABLE`, `WAITING`, `TIMED_WAITING`, and `BLOCKED` states; they are not a complete history of interrupts.
- Logs should record the **interrupt-received event**, cancellation reason, and cleanup result, rather than just logging a boolean flag that may have been cleared.
- With `ExecutorService`, monitor shutdown duration, unresponsive tasks, and open resources.
- If a task does not stop, check whether it polls the flag, which primitive it is waiting on, whether it holds locks at a blocking point, and whether that API responds to interrupts.
- Keep cancellation time predictable: long-running I/O tasks should have timeouts or an appropriate resource-closing mechanism.

### 14.3. Limitations of Testing

A passing stress test does not prove every possible interleaving is safe. You must reason based on the Java Memory Model and API contracts. The examples in this lesson intentionally use latches and print output after `join` so they **do not claim random scheduler ordering is fixed**.

## 15. Self-Check Questions

**1.** Does `worker.interrupt()` guarantee that the worker terminates before the method returns?

No. It sends an interrupt request and may cause interruptible waits to respond; the worker must cooperate and may need to clean up before exiting. Use `join` or another mechanism to wait.

**2.** How does `worker.isInterrupted()` differ from `Thread.interrupted()`?

`worker.isInterrupted()` reads `worker`'s flag without clearing it; `Thread.interrupted()` reads the **current thread** and clears that flag. One is an instance method on a receiver, and the other is a static method.

**3.** After `Thread.sleep(...)` throws `InterruptedException`, why might the catch block need `Thread.currentThread().interrupt()`?

Because `sleep` usually clears the flag when throwing the exception; restoring it lets higher layers recognize the cancellation request if the method cannot propagate the exception upward.

**4.** If a worker calls no blocking APIs and never checks the flag, will an interrupt force it to stop?

No. Interrupt is cooperative; the computation loop must check the flag itself or use another valid cancellation mechanism.

**5.** Why does calling `Thread.interrupted()` from the `main` thread not check the worker's flag?

Because it is a static method, it always acts on the **currently executing thread** — in this case `main` — regardless of what worker variables are in scope.

**6.** `main` is waiting on `worker.join()` and `main` itself is interrupted. What happens?

`join()` may throw `InterruptedException` in **`main`**; it does not automatically send an interrupt to `worker`. Caller code needs to handle the cancellation signal and decide whether to separately request `worker` to stop.

**7.** Does `Future.cancel(true)` returning `true` prove that all side effects of the task have completely stopped?

No. The `Future` may be marked cancelled while the task has not yet reacted or cleanup has not finished. A confirmation protocol is needed if the business logic requires it.

**8.** When should you choose `Thread.interrupted()` instead of `isInterrupted()`?

When you **intentionally** want to check and consume the interrupt status of the **current thread**, with a specific protocol handling that signal. If you are only polling or observing without mutating state, prefer `isInterrupted()`.

**Key takeaway:** `interrupt()` **requests** interruption of a target thread; `isInterrupted()` **observes without clearing**; `Thread.interrupted()` **checks and clears the current thread's flag**. Building proper cancellation requires identifying interrupt recognition points, handling `InterruptedException`, preserving the signal when appropriate, protecting invariants, and waiting for the task to actually finish if business logic requires it.