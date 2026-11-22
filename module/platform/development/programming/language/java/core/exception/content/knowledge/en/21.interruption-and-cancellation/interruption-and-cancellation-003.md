# Distinguishing `Thread.interrupted()` from `isInterrupted()` in Java

When a task running on a thread needs to be stopped, Java typically uses **cooperative interruption**: one thread sends an interrupt request via `interrupt()`, while the receiving thread checks the signal itself and decides how to terminate safely. To check that signal, Java provides two very similar-looking methods: `Thread.interrupted()` and `thread.isInterrupted()`. Both return a `boolean`, but **which thread they inspect** and **whether they clear the interrupt status** are the two decisive differences.

Misunderstanding these two methods can cause the cancellation signal to be "consumed" too early, prevent a thread from stopping when requested, or leave a higher-level task unaware that the thread was interrupted.

## 1. Understand the interrupt status before comparing

Every `Thread` object has an interrupt status (often called the interrupt flag). This is a signal for the thread to cooperate with stopping, not a command that forces immediate termination.

- `targetThread.interrupt()` sends an interrupt request to `targetThread`. In typical situations, if the target thread is running, its interrupt status is set to `true`.
- Code on the target thread can read the interrupt flag, exit its loop, clean up resources, and return control to its caller.
- Certain interruptible blocking operations, such as `Thread.sleep()`, `Object.wait()`, `Thread.join()`, or `BlockingQueue.take()`, can throw `InterruptedException`. These operations typically **clear the interrupt status when throwing the exception**.
- Not every operation responds to `interrupt()`. For example, a CPU-bound computation that does not check the flag will not stop on its own; waiting to acquire a regular `synchronized` lock does not automatically become an interruptible wait either.

Therefore, it is important to distinguish between **sending the signal** (`interrupt()`), **observing the signal** (`isInterrupted()` or `Thread.interrupted()`), and **the response policy** (stopping, propagating the error, or cleaning up).

## 2. Two APIs: same flag read, different target and side effect

| Characteristic | `Thread.interrupted()` | `someThread.isInterrupted()` |
| --- | --- | --- |
| Method type | `static` | Instance method |
| Thread inspected | **The current thread**, i.e., the thread executing the call | **The `Thread` object called on** (`someThread`); may be the current thread or another thread |
| Return value | `true` if the interrupt status is set, otherwise `false` | `true` if the target thread's interrupt status is set, otherwise `false` |
| Status after the call | **Clears the current thread's interrupt flag** | **Does not change the interrupt flag** |
| Consecutive reads with no new signal | The first call may return `true`, and the second `false` because the first cleared it | Can remain `true` on both calls |
| Use case | The current thread wants to check **and actively consume** the signal | Check the status **without losing** the signal; can also observe another `Thread` |

Example distinguishing them directly on the running thread:

```java
Thread current = Thread.currentThread();

boolean a = current.isInterrupted(); // Read only, preserves the flag.
boolean b = Thread.interrupted();     // Reads and clears current's flag.
boolean c = current.isInterrupted(); // May be false because b cleared it.
```

The three lines above are an illustrative snippet, not a standalone Java program. If the interrupt status before the first line is `true` and no new interrupt request arrives in between, then `a == true`, `b == true`, `c == false`.

**Syntax trap:** `interrupted()` is a `static` method, so even though Java allows the syntax `someThread.interrupted()`, that call still checks **the current thread**, not `someThread`. Avoid writing it this way. To query another thread's status, call `someThread.isInterrupted()`.

You can write `Thread.currentThread().isInterrupted()` to read your own flag without clearing it. This is not a separate method: it simply obtains the current thread object and calls the instance API.

## 3. Runnable example: observing changes to the interrupt flag

Create the file **`InterruptFlagComparison.java`**:

```java
public class InterruptFlagComparison {
    public static void main(String[] args) {
        Thread current = Thread.currentThread();

        System.out.println("initial: " + current.isInterrupted());

        current.interrupt();
        System.out.println("peek: " + current.isInterrupted());
        System.out.println("readAndClear: " + Thread.interrupted());
        System.out.println("afterClear: " + current.isInterrupted());

        current.interrupt();
        try {
            Thread.sleep(10);
            throw new AssertionError("sleep should have been interrupted");
        } catch (InterruptedException exception) {
            System.out.println("afterSleepThrows: " + current.isInterrupted());
            current.interrupt();
            System.out.println("restored: " + current.isInterrupted());
        }

        System.out.println("finalReadAndClear: " + Thread.interrupted());
        System.out.println("finalStatus: " + current.isInterrupted());
    }
}
```

Compile and run with Java 17 or later:

```bash
javac InterruptFlagComparison.java
java InterruptFlagComparison
```

Output on a normal standalone run:

```text
initial: false
peek: true
readAndClear: true
afterClear: false
afterSleepThrows: false
restored: true
finalReadAndClear: true
finalStatus: false
```

Reading the output step by step:

1. When the program starts, the `main` thread has not been interrupted, so `initial: false`.
2. `current.interrupt()` sets the flag to `true`. `current.isInterrupted()` only reads it, so `peek: true` and the flag remains set.
3. `Thread.interrupted()` returns `true` and clears the flag. Hence `afterClear: false`.
4. The program sets the flag again and calls `Thread.sleep(10)`. Because the thread already carries the interrupt status, `sleep()` throws `InterruptedException`; upon entering `catch`, the status has been cleared, producing `afterSleepThrows: false`.
5. Calling `current.interrupt()` inside `catch` **restores the interrupt signal**. Hence `restored: true`.
6. The final `Thread.interrupted()` call receives `true` again and clears the flag. `finalStatus: false` confirms the status after the final clear.

The value `10` in `sleep(10)` is the intended maximum wait duration (in milliseconds), not a delay needed to trigger the error: having the flag already set causes the sleep operation to be interrupted.

This example intentionally calls `Thread.interrupted()` to demonstrate the flag-clearing effect. In production code, you should not clear the interrupt signal if downstream code or a calling layer needs to know that the thread was requested to stop.

## 4. Which state changes on read?

Consider a sequence of operations **on the same thread**, with no other thread sending a new signal in between:

| Operation | Return value | Flag after operation |
| --- | --- | --- |
| Initially not interrupted | — | `false` |
| `Thread.currentThread().interrupt()` | `void` | `true` |
| `Thread.currentThread().isInterrupted()` | `true` | `true` |
| `Thread.currentThread().isInterrupted()` again | `true` | `true` |
| `Thread.interrupted()` | `true` | `false` |
| `Thread.interrupted()` again | `false` | `false` |

The table describes a controlled sequence. In a concurrent application, another thread can call `interrupt()` at any time; therefore, the results of two separate reads may differ due to a new signal, not solely because of how the API handles the flag.

**Rule of thumb:** `isInterrupted()` = *look and keep*; `Thread.interrupted()` = *look and clear* (on the current thread).

## 5. Combining with `InterruptedException` and propagating cancellation

There are three important scenarios when handling `InterruptedException`.

### 5.1. The method can declare `throws InterruptedException`

If a method is only an intermediate layer and can propagate the interrupt request to its caller, it is usually best to **propagate the exception**:

```java
void waitForItem(java.util.concurrent.BlockingQueue<String> queue)
        throws InterruptedException {
    String item = queue.take();
    System.out.println(item);
}
```

This is an illustrative method snippet placed inside a Java class. When `take()` throws `InterruptedException`, the method hands control back to the caller. Do not catch the exception just to log it and continue unconditionally.

### 5.2. Cannot propagate `InterruptedException`: catch and restore the flag

`Runnable.run()` does not declare checked exceptions. If you need to handle interruption while waiting inside `run()`, an appropriate pattern is to **exit the task** after restoring the status:

```java
@Override
public void run() {
    try {
        while (!Thread.currentThread().isInterrupted()) {
            String item = queue.take();
            process(item);
        }
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
    } finally {
        closeOwnedResources();
    }
}
```

This is **illustrative code inside a class implementing `Runnable`**, where `queue`, `process(...)`, and `closeOwnedResources()` are provided by the application. It cannot be compiled standalone without those components.

Because `queue.take()` cleared the flag when throwing `InterruptedException`, calling `Thread.currentThread().interrupt()` in `catch` restores the signal so calling code or thread-management infrastructure can observe it. Then `run()` finishes instead of entering another wait iteration. Resource cleanup is performed in `finally`.

**Do not** catch `InterruptedException` and immediately loop indefinitely as if no cancellation was requested. If your code is solely responsible for handling and terminating after an interrupt, it may have its own strategy, but it must be clear who owns the signal and when it is cleared.

### 5.3. Why can `isInterrupted()` be `false` after catching the exception?

APIs that throw `InterruptedException`, such as `sleep()`, `wait()`, and `join()`, typically clear the interrupt status when throwing. Therefore, checking `Thread.currentThread().isInterrupted()` right at the start of a `catch` block can return `false` even though the task itself was interrupted. This is valid behavior and does not mean the interrupt signal never occurred.

In particular, **do not call `Thread.interrupted()` inside `catch` hoping to re-verify the exception**: if the status was just restored or another interrupt signal arrived, that call can clear it again.

## 6. Practical example: stopping a worker waiting on a queue

Create the file **`InterruptibleQueueWorker.java`**:

```java
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.LinkedBlockingQueue;

public class InterruptibleQueueWorker {
    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new LinkedBlockingQueue<>();
        CountDownLatch started = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            try {
                started.countDown();
                while (!Thread.currentThread().isInterrupted()) {
                    String item = queue.take();
                    System.out.println("Processed: " + item);
                }
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            } finally {
                System.out.println(
                        "Worker ended; interrupted="
                                + Thread.currentThread().isInterrupted());
            }
        }, "queue-worker");

        worker.start();
        started.await();
        worker.interrupt();
        worker.join();

        System.out.println("Main observed worker termination");
    }
}
```

Compile and run:

```bash
javac InterruptibleQueueWorker.java
java InterruptibleQueueWorker
```

When run standalone with no items added to the queue, the output is:

```text
Worker ended; interrupted=true
Main observed worker termination
```

Explanation:

- `started` ensures `main` waits for the worker to start before issuing the interrupt request; if the interrupt arrives before the worker calls `queue.take()`, `take()` still detects the flag and throws `InterruptedException`.
- While no element is available, `take()` waits. When interrupted, it exits with `InterruptedException` and clears the flag.
- The worker calls `interrupt()` again in the `catch` block to restore the flag, then enters `finally`; the first line therefore prints `true`.
- `worker.join()` only makes `main` wait for the worker thread to terminate. It does not send an interrupt request to the worker. Because `main` prints after `join()` returns, the order of the two lines is guaranteed.
- `worker.isInterrupted()` reads the status at the moment of inspection; for a thread that has already terminated, **do not use the interrupt flag as a historical record to conclude why it stopped**. The example logs the status inside the worker's `finally` block before it finishes.

By design, this is **cooperative cancellation**: `main` requests a stop, and the worker responds at an interruptible wait point, cleans up, and terminates. `interrupt()` does not force-close resources or guarantee that arbitrary tasks will stop.

## 7. When should you use which method?

**Use `thread.isInterrupted()`** when you want to check whether a thread has received an interrupt request while **preserving the signal**. From inside a worker, `Thread.currentThread().isInterrupted()` is the readable choice for a work loop:

```java
while (!Thread.currentThread().isInterrupted()) {
    doOneSmallNonBlockingStep();
}
```

This is an illustrative snippet: `doOneSmallNonBlockingStep()` is provided by the application and must be able to finish each iteration; if it blocks too long in a non-interruptible operation, checking at the top of the loop will not stop it in time.

**Use `Thread.interrupted()`** when code on **the current thread itself** intentionally receives and consumes the interrupt signal, having explicitly decided that clearing the flag fits its contract. For example, a check that inspects the status and immediately returns from a method may accept consuming the signal if that layer truly owns the entire cancellation handling. However, if a calling layer still needs to know about the interrupt, preserve/restore the status or propagate `InterruptedException`.

A `while (!Thread.interrupted())` loop can be used to detect an interrupt and exit the loop, but note that the flag has already been cleared by the time the condition causes an exit. If subsequent code expects the flag to still be set or wants to forward the cancellation signal to a higher layer, this behavior easily causes bugs. For loops that do not need to consume the flag, `isInterrupted()` usually expresses intent more clearly.

### 7.1. Observing another thread

You can use `worker.isInterrupted()` from a monitoring thread to read `worker`'s interrupt status without clearing its flag. However, the flag state can change between the time it is checked and the time you act on it; this is not a synchronization mechanism or a complete business result. Coordinate with `join()`, `Future`, a latch, or an appropriate completion mechanism if you need to know that the work has actually finished.

Writing `worker.interrupted()` does not match the intent: because `interrupted()` is `static`, it reads and clears the flag of **the calling monitoring thread**, not `worker`'s flag. Even though the compiler permits calling it through a variable, always call `Thread.interrupted()` to clearly show that the method is static.

### 7.2. Relationship with `Future.cancel(true)`

In tasks managed by `ExecutorService`, `Future.cancel(true)` requests cancellation and **may send an interrupt to the thread running the task**; `cancel(false)` does not request interrupting an already running task. The `Future` state and the worker's interrupt flag are two different concepts. Do not assume that `cancel(true)` will force a task that ignores interrupts to stop immediately.

A task running in a pool should have a strategy for responding to interrupts and cleaning up safely. However, you should not arbitrarily call `Thread.interrupted()` just to "clean up" the worker's flag; clearing the signal can confuse outer cancellation logic. When a library or framework contract requires different signal management, follow that contract consistently.

## 8. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `Thread.interrupted()` just to "check if interrupted" | Clears the flag; downstream code may miss the interrupt request | Use `Thread.currentThread().isInterrupted()` if you only want to inspect |
| Calling `otherThread.interrupted()` to query another thread | Actually checks/clears the calling thread's flag | Call `otherThread.isInterrupted()` |
| Catching `InterruptedException` and ignoring it | The task may continue even though it was asked to stop | Propagate the exception or restore the flag and terminate appropriately |
| Assuming `isInterrupted() == false` in `catch` proves no interrupt occurred | Overlooks that the waiting API may have cleared the flag when throwing | Rely on the caught `InterruptedException`, handle it, and restore the flag if needed |
| Using `interrupt()` as a hard stop command | Non-cooperative work keeps running | Choose interruptible wait points and check the flag in computation loops |
| Concluding `isInterrupted() == true` means the thread has stopped | Interruption is a request; the thread may still be running | Use `join()` or an appropriate completion mechanism |
| Calling `Thread.interrupted()` and continuing without accounting for the consumed signal | Loses the cancellation request for calling layers | Clarify handling responsibility; restore the flag if it must be forwarded |

One more note on concurrent threads: do not use the interrupt flag as a business state variable to replace `volatile`, locks, queues, or other synchronization primitives. The interrupt flag has a dedicated role: coordinating task cancellation/interruption.

## 9. Self-check questions

1. The `main` thread calls `worker.interrupt()`, then calls `Thread.interrupted()` inside `main` itself. Whose flag does that method check? **`main`'s**, because `interrupted()` is static and always operates on the current thread; it does not read `worker`'s flag.
2. A thread currently has its interrupt flag set to `true`. Calling `Thread.currentThread().isInterrupted()` twice in a row with no other changes returns what? **`true` and `true`**, because this method does not clear the flag.
3. Under the same conditions, calling `Thread.interrupted()` twice in a row returns what? **`true` and `false`**, because the first call cleared the flag.
4. Why can `isInterrupted()` right inside `catch (InterruptedException e)` often return `false`? Because the waiting API **cleared the flag when throwing `InterruptedException`**.
5. Inside `Runnable.run()`, what should you do if `BlockingQueue.take()` is interrupted and the program needs to stop the worker? **Restore the flag with `Thread.currentThread().interrupt()`, then exit the task and clean up**, or follow the interruption policy defined by the application.
6. Can `isInterrupted()` be used to check another thread? **Yes**, via `otherThread.isInterrupted()`. That only reads the flag at the moment of observation and does not guarantee the task has finished.

**Key takeaway:** `Thread.interrupted()` asks *"has the current thread been interrupted?"* and **clears** the status; `thread.isInterrupted()` asks *"has this thread been interrupted?"* and **preserves** the status. Choose the right API based on whether you need to **only observe** or **actively consume** the interrupt signal.