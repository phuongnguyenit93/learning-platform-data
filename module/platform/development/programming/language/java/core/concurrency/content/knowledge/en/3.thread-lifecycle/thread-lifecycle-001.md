# The NEW, RUNNABLE, and TERMINATED States in the Thread Lifecycle

In Java, `Thread` represents a thread of execution. A thread goes through lifecycle states from the time it is created, starts executing, until it finishes. `Thread.State` is an enum describing the **observable** state of a thread at a point in time. This lesson focuses on three key states:

- **`NEW`**: the `Thread` object has been created, but the thread has not yet been started by `start()`.
- **`RUNNABLE`**: the thread has started and may be running in the JVM **or ready to be scheduled to run**. This is not synonymous with occupying the CPU at the exact moment of inspection.
- **`TERMINATED`**: the thread has finished executing, whether it ended normally or due to an unhandled exception/error exiting `run()`.

These three states help explain why `new Thread(...)` does not run the task yet, how `start()` differs from `run()`, and why a `TERMINATED` `Thread` cannot be restarted.

## 1. A Thread Object and a Thread of Execution Are Not the Same

Constructing `new Thread(runnable)` creates a Java object storing the information needed for a thread, **without starting the task on a new thread yet**. The object is initially in the `NEW` state.

```java
Thread worker = new Thread(() -> {
    System.out.println("Worker started");
}, "my-worker");

// worker.getState() == Thread.State.NEW
worker.start();
```

This is an illustrative snippet that needs to be placed inside a valid method or class, not a standalone program. Calling `start()` requests the JVM to begin executing `run()` on a new thread. When the CPU actually runs the task is decided by the scheduler; `start()` does not mean the task has completed.

If you call `worker.run()` directly, Java executes that method **on the calling thread** (for example `main`) instead of creating a new thread. If `start()` was not called beforehand, the `worker` object remains in `NEW` after calling `run()` directly.

## 2. State Meanings and Transitions Table

| State | Condition | `isAlive()` on stable observation | What happens next? |
|---|---|---|---|
| `NEW` | Object created, not yet `start()`ed. | `false` | Successful `start()` → `RUNNABLE`. |
| `RUNNABLE` | Eligible to run or currently executing in the JVM. | `true` | Can remain RUNNABLE, pass through waiting states, and then become TERMINATED. |
| `TERMINATED` | `run()` has finished. | `false` | Final state; cannot be `start()`ed again. |

Java 17 defines **six** values in the `Thread.State` enum: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, and `TERMINATED`. The remaining three states appear when a thread is still alive but waiting for a lock or waiting for a condition/timeout. They serve as context for understanding the lifecycle, not the focus of this lesson.

### NEW: no execution activity of the new thread yet

An object in `NEW` can be configured (setting a name, attaching an uncaught exception handler, and for platform threads, setting daemon mode) before `start()`. If `start()` is never called, the task does not run automatically. Calling `run()` as an ordinary method does not transition the `Thread` to RUNNABLE.

### RUNNABLE: ready or currently running

The name `RUNNABLE` is easily misunderstood. **`Thread.State` does not have a separate `RUNNING` state.** The JVM combines "running" and "ready to run" into RUNNABLE; a thread competing for CPU may still report RUNNABLE even if the operating system has not allocated CPU to it at the moment of inspection.

Do not use `getState() == RUNNABLE` to conclude that a thread is doing useful work or how much CPU it is using. This state also makes no guarantees about execution order between threads.

### TERMINATED: execution has ended

`TERMINATED` occurs when the `run()` method has completed:

- Reaching the end of the method body or returning normally via `return`.
- An unhandled exception/error causes the thread to terminate.

It cannot be "reset" to NEW or RUNNABLE. Calling `start()` again on a thread that has already started, even if it is already `TERMINATED`, throws `IllegalThreadStateException`. To perform a new task, create a new `Thread` object or submit the work to a managed execution mechanism.

## 3. Lifecycle Diagram

```text
new Thread(task)
      |
      v
     NEW
      |
      | start() succeeds, only once
      v
   RUNNABLE <------> BLOCKED / WAITING / TIMED_WAITING
      |                (when the thread temporarily waits)
      |
      | run() returns or terminates due to an unhandled error
      v
  TERMINATED
      |
      +-- calling start() again: IllegalThreadStateException
```

A thread can transition from RUNNABLE to `BLOCKED` when waiting for a `synchronized` monitor, `WAITING` when waiting for an untimed condition (such as `CountDownLatch.await()`), or `TIMED_WAITING` during `Thread.sleep(...)`. When the wait ends, it can return to RUNNABLE and continue its work. Not every thread goes through every state; a short task can move from NEW through RUNNABLE to TERMINATED very quickly.

There is no safe API to arbitrarily set the state such as `setState(TERMINATED)`. To stop a thread, you must coordinate so that `run()` returns on its own (a stop signal, properly handled interruption, or controlled task cancellation). `Thread.stop()` is deprecated and unsafe.

## 4. Example 1: Clearly Observing NEW → RUNNABLE → TERMINATED

To observe the states, we need to prevent the worker from finishing too quickly before `main` can inspect it. The following example uses `CountDownLatch` as a started signal and `AtomicBoolean` as a stop signal. The worker temporarily runs an active loop, so it does not have to wait using `sleep()` with an estimated duration.

Create the file **`ThreadStateLifecycle.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class ThreadStateLifecycle {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch started = new CountDownLatch(1);
        AtomicBoolean stop = new AtomicBoolean(false);

        Thread worker = new Thread(() -> {
            started.countDown();
            while (!stop.get()) {
                Thread.onSpinWait();
            }
        }, "lifecycle-worker");

        System.out.println("Before start: "
                + worker.getState() + ", alive=" + worker.isAlive());

        worker.start();
        started.await();

        System.out.println("While worker is spinning: "
                + worker.getState() + ", alive=" + worker.isAlive());

        stop.set(true);
        worker.join();

        System.out.println("After join: "
                + worker.getState() + ", alive=" + worker.isAlive());
    }
}
```

Compile and run with JDK 17+:

```bash
javac ThreadStateLifecycle.java
java ThreadStateLifecycle
```

Expected output on a normal run:

```text
Before start: NEW, alive=false
While worker is spinning: RUNNABLE, alive=true
After join: TERMINATED, alive=false
```

**Step-by-step explanation:**

1. `new Thread(...)` creates the object without executing yet: `NEW`, `isAlive() == false`.
2. `worker.start()` starts the thread. The worker signals `started.countDown()` and keeps spinning in `while (!stop.get())`. `started.await()` ensures `main` only inspects after the worker reports it has started.
3. The worker is not waiting on a monitor, sleeping, or awaiting a latch inside the loop, so before receiving the stop signal, the observed state is RUNNABLE. It may be occupying the CPU or waiting to be scheduled CPU time.
4. `stop.set(true)` sends the signal with the memory visibility guarantees of `AtomicBoolean`. The worker exits the loop and finishes `run()`.
5. `worker.join()` waits for termination to complete. After `join()` returns normally, `getState()` is `TERMINATED` and `isAlive()` is `false`.

**Note:** the loop using `Thread.onSpinWait()` is an intentional way to produce RUNNABLE for learning purposes and can consume CPU. Do not use an unbounded busy-wait loop in production programs. If replaced with `Thread.sleep()` or `await()`, the state may be `TIMED_WAITING` or `WAITING`, and the inspection output will differ.

## 5. Example 2: Calling run() Does Not Replace start()

This example uses only one `Thread`, but runs the `Runnable` body in two different ways to show the difference.

Create the file **`StartVersusRun.java`**:

```java
public class StartVersusRun {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("Current thread: "
                    + Thread.currentThread().getName());
        }, "demo-worker");

        System.out.println("Initial state: " + worker.getState());

        worker.run();
        System.out.println("After direct run(): " + worker.getState());

        worker.start();
        worker.join();
        System.out.println("After start() and join(): " + worker.getState());

        try {
            worker.start();
        } catch (IllegalThreadStateException e) {
            System.out.println("Restart rejected: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

```bash
javac StartVersusRun.java
java StartVersusRun
```

Output when the launching thread is normally named `main`:

```text
Initial state: NEW
Current thread: main
After direct run(): NEW
Current thread: demo-worker
After start() and join(): TERMINATED
Restart rejected: IllegalThreadStateException
```

The first `worker.run()` call only executes the `Runnable` on the `main` thread, so `worker` remains NEW. The `worker.start()` call is what actually starts `demo-worker`. `join()` ensures the final check runs after the worker has finished. Attempting a second `start()` is rejected because a `Thread` object has only one execution lifecycle.

## 6. Example 3: Exceptions Also Lead to TERMINATED

`TERMINATED` does not mean the task succeeded; it only states that **the thread has ended**. The following snippet intentionally throws an exception, records it via `UncaughtExceptionHandler`, and then waits for completion using `join()`.

Create the file **`FailedThreadLifecycle.java`**:

```java
public class FailedThreadLifecycle {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            throw new IllegalStateException("intentional");
        }, "failing-worker");

        worker.setUncaughtExceptionHandler((thread, error) -> {
            System.out.println(thread.getName()
                    + " failed: " + error.getMessage());
        });

        System.out.println("Before start: " + worker.getState());
        worker.start();
        worker.join();
        System.out.println("After failure: " + worker.getState());
    }
}
```

```bash
javac FailedThreadLifecycle.java
java FailedThreadLifecycle
```

Output:

```text
Before start: NEW
failing-worker failed: intentional
After failure: TERMINATED
```

The handler logs the cause; it does not return the thread to RUNNABLE or automatically rerun the work. In real applications, you should record results/errors separately and decide whether to retry using **a new task or Thread**.

## 7. getState(), isAlive(), and join(): Using Each for Its Intended Purpose

### getState() is a snapshot, not a synchronization lock

`thread.getState()` returns the state at the moment of the call. By the next statement, the state may already be different. For example, a fast-running worker may already be `TERMINATED` right after `start()`, even if you expected it to be RUNNABLE. This is why you should not write logic like:

```java
// Illustrative snippet; worker is assumed to be already declared.
while (worker.getState() != Thread.State.TERMINATED) {
    // Continuous polling: wastes CPU, not a good waiting strategy.
}
```

Use `getState()` for logging or aiding investigation, not as a thread coordination mechanism. For waiting on completion, `join()` is more appropriate.

### isAlive() does not mean RUNNABLE

`isAlive()` indicates that the thread **has started and has not yet terminated**. At a stable point, NEW and TERMINATED return `false`; RUNNABLE returns `true`. However, `isAlive() == true` does not mean the state is RUNNABLE: a thread in `WAITING`, `TIMED_WAITING`, or `BLOCKED` is also alive.

`isAlive()` and `getState()` are two independent reads; if the state transitions between the two calls, the two retrieved values do not necessarily form an atomic snapshot. Example 1 intentionally keeps the worker from finishing so that the observation is easy to understand.

### join() is the completion wait point

`worker.join()` causes the **calling thread** to wait until the worker terminates, unless the wait is interrupted. It works for both daemon and user threads. `join()` has synchronization semantics: the Java Memory Model guarantees that the worker's actions before termination *happen-before* actions after another thread detects termination via `join()`. Similarly, actions before `Thread.start()` on the starting thread have a *happens-before* relationship with actions in the new thread.

Therefore, when you need to process results after a task, use an appropriate completion/synchronization mechanism (`join()`, `Future`, `CountDownLatch`, etc.), and avoid relying on state polling and hoping the data is ready.

## 8. Common Design Mistakes

| Misconception or wrong action | Consequence | Better practice |
|---|---|---|
| `new Thread(task)` has already started running | `task` is not executed yet, still NEW. | Call `start()` when you actually want to launch it. |
| `thread.run()` is equivalent to `thread.start()` | Task runs on the calling thread, creating no concurrency. | Call `start()` exactly once. |
| RUNNABLE means currently occupying CPU | Misjudging performance and bottleneck causes. | Observe CPU using a profiler/thread dump over time. |
| Right after `start()`, you will definitely see RUNNABLE | The task may finish or transition to WAITING very quickly. | Use synchronization signals if you want a deterministic experiment. |
| `TERMINATED` is a thread that can be reused | Calling `start()` again throws `IllegalThreadStateException`. | Create a new Thread for another run. |
| TERMINATED means a successful result | Unhandled exceptions also terminate the thread. | Manage errors/results separately from thread state. |
| `getState()` is a tool for waiting on a task | Race conditions, busy-wait loops, and hard-to-maintain code. | Use `join()` or an appropriate synchronization utility. |
| `isAlive()` means the worker is RUNNABLE | The worker might be BLOCKED/WAITING. | Check your observation intent and understand all six enum states. |

**Do not confuse with daemon/user threads:** `isDaemon()` indicates a different property regarding whether the thread keeps the JVM alive during normal JVM shutdown. Both daemon threads and user threads can have the states NEW, RUNNABLE, and TERMINATED; daemon mode is **not** part of the `Thread.State` enum.

When diagnosis is needed, you can read the state with `getState()`, give threads recognizable names, and use thread dumps (for example `jcmd <pid> Thread.print` on a suitable JDK). A single measurement is not enough to prove deadlock, CPU consumption, or progress; you need to observe progression over time and lock/signal relationships.

## 9. Self-Check

1. **If you create `new Thread(...)` without calling `start()`, what is its state?** NEW.
2. **Does calling `run()` directly transition a NEW object to RUNNABLE?** No; that is just a method call on the current thread.
3. **Why does Java not have `Thread.State.RUNNING`?** The JVM uses RUNNABLE for both ready-to-run and currently executing in its state model.
4. **Does a thread in `WAITING` have `isAlive() == true`?** Yes, if it has started and has not terminated yet.
5. **After `worker.join()` completes normally, what is the worker's state?** TERMINATED.
6. **Can an unhandled exception bring a thread to TERMINATED?** Yes; TERMINATED only indicates the thread has ended, not that it succeeded.
7. **Why shouldn't you use a loop checking `getState()` to wait for a result?** Because the state is a constantly changing snapshot, polling easily wastes CPU, and it does not replace synchronization mechanisms.
8. **Can you call `start()` again on a TERMINATED thread?** No; create a new Thread.

**Key takeaway:** `NEW` = not started; `RUNNABLE` = running or ready to run; `TERMINATED` = ended and cannot be restarted on the same object. Use `start()` to launch, `join()` to wait, and `getState()` primarily for observation.
