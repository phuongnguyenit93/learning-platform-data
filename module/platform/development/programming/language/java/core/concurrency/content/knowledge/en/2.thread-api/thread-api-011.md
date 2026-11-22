# `Thread.join()`: Waiting for a Thread to Finish in Java

## 1. What problem does `join()` solve?

In Java, after calling `Thread.start()`, the new thread can run concurrently with the calling thread. `start()` **does not wait** for the work in that thread to complete. If the current thread needs the result or must ensure the other task has finished before continuing, it can call `join()` on the `Thread` object representing the thread to wait for.

```java
Thread worker = new Thread(() -> doWork());
worker.start();  // Ask the JVM to start the worker thread
worker.join();   // Current thread waits for worker to finish
useResult();     // Runs only after join() returns normally
```

The snippet above is **illustrative code only** because `doWork()` and `useResult()` are not defined; a complete example is in the next section.

**Core semantics:** `worker.join()` means “the **calling** thread will wait for `worker` to finish.” It does not mean `worker` waits for the calling thread, nor does it start `worker` automatically.

- If called from `main`, `main` is the thread blocked while waiting.
- If called from another worker, the worker calling `join()` is the thread blocked.
- The target thread continues executing according to the JVM's scheduling; `join()` does not “run it on its behalf,” does not make the target thread finish early, and does not guarantee that it succeeds.
- The target thread may complete before `join()` is called; in that case, `join()` can return immediately.

### How `join()` and `sleep()` differ

`Thread.sleep(100)` asks the **current thread** to pause for the specified duration, regardless of whether the worker has finished. `worker.join()` waits for a **specific condition: the worker terminating**. Therefore, using `sleep()` to “wait long enough for the worker and then read the result” is incorrect synchronization: the worker may be faster or slower than expected.

## 2. Java 17+ Example: Guaranteeing Order and Reading the Result After `join()`

Create the file `JoinBasic.java`:

```java
public class JoinBasic {
    private static int result;

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            int sum = 0;
            for (int number = 1; number <= 5; number++) {
                sum += number;
            }

            result = sum;
            System.out.println("Worker finished");
        }, "calculator");

        worker.start();
        worker.join();

        System.out.println("Result: " + result);
        System.out.println("Worker alive: " + worker.isAlive());
    }
}
```

Compile and run:

```bash
javac JoinBasic.java
java JoinBasic
```

Output on successful execution:

```text
Worker finished
Result: 15
Worker alive: false
```

**Exact interpretation:**

1. `new Thread(...)` creates the thread object; no task has been executed by the new thread yet.
2. `worker.start()` starts the thread, after which `main` and `worker` can make progress independently.
3. The worker sums the numbers from 1 to 5, assigns `result = 15`, and prints the message.
4. `worker.join()` does not return normally before the worker has actually terminated.
5. After `join()`, `main` reads `result` and observes `isAlive() == false`. Because the message is printed before the worker terminates, the order of the three lines above is deterministic in this example program.

**Java Memory Model note:** every action in the worker **happens-before** another thread detects that the worker has successfully terminated via `join()`. Therefore, in the example above, after `join()` returns normally, `main` sees `result = 15`; the `result` field does not need to be marked `volatile` solely to pass the result across this termination boundary. That **does not** make all concurrent accesses to shared variables before the worker terminates safe, nor does it guarantee correctness if `join()` is interrupted or only waits with a timeout while the worker is still running.

## 3. Overloads of `join()`

`Thread` in Java 17 provides the common overloads:

| Method | Meaning |
| --- | --- |
| `void join() throws InterruptedException` | Waits for the target thread to terminate, with no timeout |
| `void join(long millis) throws InterruptedException` | Waits at most approximately `millis` milliseconds if `millis > 0`; `millis == 0` means wait indefinitely |
| `void join(long millis, int nanos) throws InterruptedException` | Waits with a timeout specified in milliseconds and nanoseconds; the nanosecond part is handled according to the implementation's resolution |

Invalid time arguments throw `IllegalArgumentException`: `millis < 0`, or `nanos < 0` or `nanos > 999_999`.

**Pitfall:** `join(0)` does **not** mean “check immediately without waiting.” It means wait until the thread terminates, similar to `join()`. If you need to check whether a thread is still alive without blocking, use `isAlive()`, keeping in mind that the state may change immediately after the check.

**Timing pitfall:** `join(100)` does not promise to return after exactly 100 ms. Wakeup and scheduling depend on the JVM/OS, so in practice it may be later. Do not use `join(long)` as a precise timer. For `join(long, int)`, the resolution and rounding of the nanosecond part depend on the implementation.

**Return value:** all three overloads return `void`. With a timed join, returning **does not indicate** whether the worker finished or the timeout expired. You must check `worker.isAlive()` afterward, then decide whether to keep waiting, cancel the task, or record an incomplete state.

## 4. Java 17+ Example: `join(timeout)` and Handling an Unfinished Worker

Create the file `JoinTimeout.java`:

```java
public class JoinTimeout {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            try {
                Thread.sleep(200); // Simulate a time-consuming task
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "slow-worker");

        worker.start();
        worker.join(25); // Wait at most approximately 25 ms

        if (worker.isAlive()) {
            System.out.println("Worker may still be running");
            worker.join(); // Wait for actual termination to clean up the example
        }

        System.out.println("Worker terminated: " + !worker.isAlive());
    }
}
```

Run:

```bash
javac JoinTimeout.java
java JoinTimeout
```

The last line is **always** `Worker terminated: true` if the program completes normally. The line `Worker may still be running` may or may not appear, because the outcome depends on scheduling: the worker may have already finished before `main` checks `isAlive()`. Do not use the sleep duration in this example to conclude a real production timeout threshold.

The code above only demonstrates how to detect status after a timed join. For a task with no completion bound, the second `join()` **may wait indefinitely**. In a real application, you need a clear policy: return an “in progress” result, set a deadline, send a cooperative cancellation signal, or continue tracking from a lifecycle management component. `join(timeout)` **does not automatically cancel** the target thread when the timeout expires.

## 5. `InterruptedException`: The Waiting Thread Is Interrupted

The overloads of `join()` declare `throws InterruptedException`. If the thread **waiting inside `join()`** is interrupted, the wait call may throw `InterruptedException`. This is a signal asking to stop waiting or stop work according to the program's protocol; it **does not mean** the target thread has finished, nor does it automatically propagate the interrupt to the worker.

Two common handling approaches:

- **Propagate the exception:** the method declares `throws InterruptedException` so the caller can decide how to terminate, clean up, and recover.
- **Catch at a layer that cannot propagate:** perform necessary cleanup and usually call `Thread.currentThread().interrupt()` to preserve the interrupt signal for upper layers. When `InterruptedException` is thrown from a blocking wait operation, the current thread's interrupt status has usually been cleared; therefore, restoring it is an important step if you do not rethrow the exception.

Example of restoring the interrupt flag in a method that does not declare `throws`:

```java
static boolean waitFor(Thread worker) {
    try {
        worker.join();
        return true;
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return false;
    }
}
```

This snippet is an **illustrative method** used inside another class; the `worker` variable is the thread to wait for. A return value of `false` means **the wait did not complete**; you must not infer that the worker failed or terminated. The caller must decide how to proceed according to the application's stop/cancellation policy.

**Distinguish the two actions:**

- `waitingThread.interrupt()`: requests interruption of the thread currently inside `join()`; may cause `InterruptedException` in that thread.
- `worker.interrupt()`: sends an interrupt signal to the worker; the worker must respond appropriately on its own, such as handling `InterruptedException` or checking the interrupt flag. There is no guarantee the worker will terminate immediately, especially for tasks that ignore interrupts.

Do not use `Thread.stop()` to forcibly terminate a worker: this API is deprecated and unsafe.

## 6. Does `join()` Guarantee That the Task Succeeded?

**No.** `join()` only confirms that the thread has terminated when it returns normally without a timeout. A worker may terminate because it finished running or because of an unhandled error. An exception thrown inside the worker **is not automatically rethrown** into the thread calling `join()`. Therefore, `join()` does not replace a result or error reporting mechanism.

If using `Thread` directly, you can store the result and error in a clearly designed holder. The following example catches a business error in the worker and reads it after `join()`:

Create the file `JoinFailure.java`:

```java
import java.util.concurrent.atomic.AtomicReference;

public class JoinFailure {
    public static void main(String[] args) throws InterruptedException {
        AtomicReference<String> error = new AtomicReference<>();

        Thread worker = new Thread(() -> {
            try {
                throw new IllegalArgumentException("invalid input");
            } catch (IllegalArgumentException e) {
                error.set(e.getMessage());
            }
        });

        worker.start();
        worker.join();

        if (error.get() != null) {
            System.out.println("Task failed: " + error.get());
        }
    }
}
```

Run:

```bash
javac JoinFailure.java
java JoinFailure
```

Output:

```text
Task failed: invalid input
```

`AtomicReference` here provides a clear, thread-safe holder for the error state across threads. For passing data **only after `join()` succeeds**, the happens-before relationship of `join()` is already sufficient for visibility; however, in more complex problems, `Future`/`CompletableFuture` usually express results, exceptions, timeouts, and task cancellation more directly.

## 7. Common Cases That Cause Hangs or Incorrect Waiting

### 7.1. A thread calling `join()` on itself

```java
Thread.currentThread().join(); // Dangerous: waiting for the currently running thread to finish
```

A thread only finishes when its own code finishes, yet it waits for itself: it can get stuck indefinitely unless an appropriate interrupt occurs. Do not use self-join.

### 7.2. Two threads waiting on each other

If thread A calls `b.join()` while B calls `a.join()` when both are active, both can wait indefinitely. This is a dependency cycle similar to deadlock, even if it does not necessarily occur on a programmer-acquired monitor lock.

Design rule: build an **acyclic wait graph**. Typically a coordinator thread waits for workers; a worker should not wait back on the coordinator thread while the coordinator is waiting on that worker.

### 7.3. Holding a lock that the worker also needs

If the calling thread holds a monitor/lock and calls `join()` on a worker while the worker needs that exact lock to complete, the program can deadlock: the caller holds the lock while waiting for the worker, and the worker waits for the lock to finish. Separate the lock-holding region from the wait operation and check lock dependency order.

Conceptual example to avoid:

```java
synchronized (sharedLock) {
    worker.join(); // Dangerous if worker must acquire sharedLock to exit
}
```

This is illustrative code assuming `worker` and `sharedLock` are already declared. Do not conclude that every `join()` inside `synchronized` deadlocks; the bug occurs when there is a reverse dependency path.

### 7.4. Calling `join()` on a thread that has not been `start()`ed

A `Thread` object still in the `NEW` state has not executed `run()`; calling `join()` does not start the task. Because that thread is not `isAlive()`, `join()` may return immediately. Therefore, call `start()` at the right time before waiting, unless you intentionally check an already terminated thread.

### 7.5. Treating a timed join return as completion

`worker.join(100)` does not guarantee the worker is done. If you need the complete result, check `!worker.isAlive()` after waiting and only read completion-dependent results when that condition is satisfied. If the thread is still running, do not use unsynchronized mutable data as if it were finished.

### 7.6. Waiting indefinitely on a task that may hang

`join()` without a timeout makes the calling thread wait until the target thread terminates or is interrupted. If the worker is stuck in I/O, deadlock, or an infinite loop, the waiter can get stuck too. Consider timeouts/cancellation at the architectural level, especially on paths that must meet a deadline.

## 8. `join()` and Other Waiting Mechanisms in Java

| Waiting mechanism | When it fits | What to remember |
| --- | --- | --- |
| `Thread.join()` | Need to wait for **a specific thread** to terminate | Only indicates thread lifecycle completion; does not return task result or error |
| `Thread.join(timeout)` | Want to spend a bounded amount of time waiting for a thread to terminate | Returns `void`; must check whether it is still alive |
| `Future.get()` | Task submitted via `ExecutorService`, need task result and error | Can throw `ExecutionException`; has timeout overload |
| `CompletableFuture.join()` | Asynchronous pipeline with `CompletableFuture` | Can throw unchecked `CompletionException`; named `join` but semantics differ from `Thread.join` |
| `CountDownLatch.await()` | One or more threads wait for a **work milestone/event** | Not directly tied to a specific thread terminating; requires proper countdown |
| `Thread.sleep()` | Need to pause the current thread | Does not confirm that another task has completed |

These options are standard Java APIs; there is no need to bring framework content into a lesson on `Thread.join()`.

## 9. Key Takeaways and Practice Checklist

1. Create a `Thread`, call `start()`, then call `join()` from the thread **that needs to wait**.
2. `join()` waits for the thread's lifecycle; it does **not** start the thread and does **not** automatically propagate results or exceptions.
3. A successful `join()` after the target thread terminates establishes a **happens-before** relationship, making the worker's writes prior to termination visible.
4. `join(0)` waits indefinitely; with `join(timeout)`, always check `isAlive()` before assuming the work is done.
5. `InterruptedException` can occur; propagate the exception upward or restore the interrupt status if caught and not propagated.
6. Avoid self-join, A → B → A cycles, and waiting while holding a lock that the worker needs.
7. If the problem already involves a thread pool, results, errors, timeouts, or coordinating multiple tasks, consider `Future` and appropriate concurrency abstractions instead of manually creating and joining threads.

**Conclusion:** `Thread.join()` is a simple and essential primitive for one thread to wait for another to complete, while establishing the necessary synchronization relationship for writes made before the target thread terminates. Using it at the right time, handling interrupts, and verifying status when using timeouts will prevent most common bugs.