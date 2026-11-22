# Observing Thread States with `Thread.getState()` in Java

When a Java program runs multiple tasks concurrently, we often want to answer: has a thread started yet, does it have a chance to run, is it waiting for a lock, waiting for a signal, waiting with a time limit, or has it finished? **`Thread.getState()`** is a quick observation API for the lifecycle of a `Thread`. However, the returned state is a **point-in-time snapshot**, not a complete log or a guarantee that the thread will still be in that state when we process the result.

This lesson focuses on **general Java** concurrency via `java.lang.Thread` and synchronization utilities in `java.util.concurrent`. The main focus is knowing how to **correctly read the six `Thread.State` values**, create observable scenarios, understand the limitations, and use states to assist diagnostics. No Spring-specific mechanisms are used.

## 1. What does `Thread.getState()` return?

Signature:

```java
public Thread.State getState()
```

This is an **API signature**, not a standalone Java program. `getState()` returns an element of the nested enum `Thread.State`, describing the state of the **target thread** at the time of observation:

```java
Thread worker = new Thread(() -> doWork());
Thread.State snapshot = worker.getState();
```

The snippet above illustrates the idea; `doWork()` is a hypothetical method name. `getState()` can be called before or after `start()`, while the thread is running, or after it has finished. You do not need `synchronized` just to call this observation method.

There are **six** values:

| `Thread.State` | How to read it | Typical scenario |
| --- | --- | --- |
| `NEW` | A `Thread` object has been created, but `start()` has not been called yet | `new Thread(task)` was just called |
| `RUNNABLE` | Executable in the JVM; may be running or waiting for CPU/OS resources | The thread has been started (`start()`) and is executing work or ready to run |
| `BLOCKED` | Waiting for a **monitor lock** to enter or re-enter a `synchronized` block/method | Two threads contending for the same monitor |
| `WAITING` | Waiting indefinitely according to a waiting mechanism, until woken up/completed/interrupted depending on the API | `Object.wait()` without timeout, `Thread.join()` without timeout, `LockSupport.park()` |
| `TIMED_WAITING` | Waiting for a specified time limit or duration | `Thread.sleep(...)`, `Object.wait(timeout)`, `Thread.join(timeout)`, `LockSupport.parkNanos(...)` |
| `TERMINATED` | The `run()` method has finished, whether normally or due to an uncaught exception | The thread has completed |

**There is no `RUNNING`, `SLEEPING`, `PARKED`, or `DEAD` in this enum.** Those terms sometimes appear in teaching diagrams or diagnostic tools, but they are not return values of `Thread.getState()`.

`RUNNABLE` is the most easily misunderstood case: it **does not prove the thread is actually occupying the CPU at the moment of observation**. The Java documentation states that a thread in this state may be executing in the JVM while still waiting for operating-system-level resources such as a processor. You cannot infer CPU usage from a `RUNNABLE` snapshot.

## 2. Lifecycle diagram: how can states transition?

Overview diagram:

```text
new Thread(...) 
      |
      v
     NEW
      |
      | start()
      v
  RUNNABLE <----------------------------------------------+
      |                                                  |
      | monitor contention / synchronized                |
      +-------> BLOCKED ----- monitor acquired ----------+
      |                                                  |
      | wait/park/join without timeout                   |
      +-------> WAITING ----- allowed to continue -------+
      |                                                  |
      | sleep/wait/park/join with timeout                |
      +-------> TIMED_WAITING -- timeout/signal ---------+
      |
      | run() returns or ends with uncaught exception
      v
 TERMINATED
```

This is a **conceptual diagram**, not a state machine describing every JVM transition. For example, a thread notified via `notify()` after `Object.wait()` may have to **wait to re-acquire the monitor** before continuing, so it can sometimes be observed as `BLOCKED`. After `interrupt()`, a thread may return to `RUNNABLE` to handle the interruption rather than automatically becoming `TERMINATED`.

Basic principles:

1. Creating a thread via a constructor only produces the `NEW` state; **calling `run()` directly** is an ordinary method call on the caller thread and does not `start()` a new thread.
2. `start()` asks the JVM to begin the thread lifecycle and may only be called **once on the same `Thread` object**. Calling it again after it has started—even after the thread has finished—throws `IllegalThreadStateException`.
3. A thread can move from `RUNNABLE` to waiting and back to `RUNNABLE` many times; **it does not have to pass through all six states**.
4. Once `run()` finishes, the final state is `TERMINATED`. To run more work on another thread, create a new thread or submit a task to an executor; do not restart the same `Thread`.

## 3. Java 17+ example: observing `NEW`, `RUNNABLE`, `TERMINATED`

The first example uses a worker running a loop with a `volatile` stop flag. Because there is no blocking wait point inside the loop, we can check `RUNNABLE` in a controlled manner. This spin loop is **only for learning and diagnostics** and should not be turned into a way to wait for work in real applications.

Save as `BasicThreadStateDemo.java`:

```java
import java.util.concurrent.TimeUnit;

public class BasicThreadStateDemo {
    private static volatile boolean stopRequested;

    private static void awaitState(Thread thread, Thread.State expected) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

        while (System.nanoTime() - deadline < 0) {
            if (thread.getState() == expected) {
                return;
            }
            Thread.onSpinWait();
        }

        throw new IllegalStateException(
                "Did not observe " + expected + "; last=" + thread.getState());
    }

    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            while (!stopRequested) {
                Thread.onSpinWait();
            }
        }, "demo-worker");

        System.out.println("Before start: " + worker.getState());

        worker.start();
        try {
            awaitState(worker, Thread.State.RUNNABLE);
            System.out.println("While active: " + worker.getState());
        } finally {
            stopRequested = true;
            worker.join();
        }

        System.out.println("After join: " + worker.getState());
    }
}
```

Commands to run on JDK 17 or later:

```bash
javac BasicThreadStateDemo.java
java BasicThreadStateDemo
```

In a normal run, when `RUNNABLE` is observed before the deadline, stdout is:

```text
Before start: NEW
While active: RUNNABLE
After join: TERMINATED
```

**Explanation:**

- Before `start()`, the worker object is `NEW`.
- `worker.start()` starts the new thread; the worker reads the `volatile stopRequested` flag in its loop. The volatile flag ensures the worker sees the stop request from `main`.
- `awaitState` **polls repeatedly with a three-second limit**, avoiding the assumption that calling `getState()` immediately after `start()` will observe the expected state. When the scheduler runs the worker is still not guaranteed; if the machine stalls for a long time or the JVM does not schedule it in time, the example reports an error instead of making a false claim.
- In this example, the worker is not waiting on a monitor, queue, or sleep, and the flag has not been set yet, so once active it stays in `RUNNABLE`. This state does not mean it has an entire dedicated CPU core.
- `stopRequested = true` asks the worker to exit, and `worker.join()` **waits for actual completion**. Only after `join()` succeeds is printing `TERMINATED` solidly grounded. `getState()` alone is not a completion wait.

Because `Thread.onSpinWait()` can consume CPU while waiting, this is only a short verification snippet for learning. In real code, use `CountDownLatch`, `BlockingQueue`, `Future`, or an appropriate signaling mechanism when waiting for events.

## 4. Distinguishing the three waiting states: `BLOCKED`, `WAITING`, and `TIMED_WAITING`

These three states look similar because the thread has not resumed its work, yet **the reason for waiting differs**.

### `BLOCKED`: waiting for an intrinsic monitor lock

Suppose thread A is currently in:

```java
synchronized (monitor) {
    // Holding the monitor inside the critical section.
}
```

If thread B also wants to enter the `synchronized (monitor)` block while A has not released the monitor, B can be `BLOCKED`. Both threads must contend for **the same monitor object** for this contention to occur.

`BLOCKED` is tied to **monitor entry/re-entry**. Do not interpret every "blocked" operation in English as `Thread.State.BLOCKED`:

- `Thread.sleep(...)` typically produces `TIMED_WAITING`.
- `Object.wait()` releases the monitor while waiting and typically produces `WAITING`.
- `BlockingQueue.take()` typically parks the thread via mechanisms in `java.util.concurrent.locks`, so it typically produces `WAITING` without a timeout.
- `ReentrantLock.lock()` under contention can wait via `LockSupport.park()`, which is typically observed as `WAITING`, **not `BLOCKED`** in the monitor sense.

Do not infer the type of resource being waited on directly from the word "blocked" in business documentation. Always check the API and stack trace.

### `WAITING`: waiting indefinitely for a signal or condition

A thread can be in `WAITING` when calling `Object.wait()`, `Thread.join()`, `LockSupport.park()`, or synchronization APIs that use parking without a timeout.

"Indefinitely" only means **no self-wakeup deadline was specified in the call itself**. It does not mean the thread will never wake up; it can be woken by `notify/notifyAll`, unpark, completion of a synchronization condition, or interruption depending on the API. `Object.wait()` and `Condition.await()` can also experience spurious wakeups, so conditions must be re-checked according to the API contract.

### `TIMED_WAITING`: waiting with a duration/deadline

`Thread.sleep(1_000)` puts the current thread into `TIMED_WAITING` for the sleep duration. Other examples are `wait(timeout)`, `join(timeout)`, and `LockSupport.parkNanos(...)`.

**Having a timeout does not mean the thread is guaranteed to return to `RUNNABLE` at the exact deadline.** Expiration time, scheduling, lock contention, and interrupts can all affect when the thread actually resumes. `Thread.sleep(...)` also **does not release any monitor** the thread is holding.

## 5. Java 17+ example: creating scenarios to observe the three waiting states

The next example uses controlled waiting causes: a held monitor for `BLOCKED`, an unopened latch for `WAITING`, and `Thread.sleep` for `TIMED_WAITING`. Instead of calling `sleep` in `main` to **guess** when a worker changes state, the program polls with a time limit and then releases each worker.

Save as `WaitingStatesDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class WaitingStatesDemo {
    private static Thread.State observe(
            Thread thread, Thread.State expected) {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);

        while (System.nanoTime() - deadline < 0) {
            Thread.State current = thread.getState();
            if (current == expected) {
                return current;
            }
            Thread.onSpinWait();
        }

        throw new IllegalStateException(
                "Expected " + expected + ", last=" + thread.getState());
    }

    public static void main(String[] args) throws InterruptedException {
        // 1. Another thread is holding the intrinsic monitor.
        Object monitor = new Object();
        CountDownLatch aboutToContend = new CountDownLatch(1);
        Thread contender = new Thread(() -> {
            aboutToContend.countDown();
            synchronized (monitor) {
                // Can only enter after main releases the monitor.
            }
        }, "contender");

        synchronized (monitor) {
            contender.start();
            aboutToContend.await();
            System.out.println("Monitor: "
                    + observe(contender, Thread.State.BLOCKED));
        }
        contender.join();

        // 2. Thread waiting on a latch to open, with no timeout.
        CountDownLatch gate = new CountDownLatch(1);
        Thread waiter = new Thread(() -> {
            try {
                gate.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "waiter");

        waiter.start();
        try {
            System.out.println("Latch: "
                    + observe(waiter, Thread.State.WAITING));
        } finally {
            gate.countDown();
            waiter.join();
        }

        // 3. Thread sleeping for a given duration.
        Thread sleeper = new Thread(() -> {
            try {
                Thread.sleep(30_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "sleeper");

        sleeper.start();
        try {
            System.out.println("Sleep: "
                    + observe(sleeper, Thread.State.TIMED_WAITING));
        } finally {
            sleeper.interrupt();
            sleeper.join();
        }
    }
}
```

Run:

```bash
javac WaitingStatesDemo.java
java WaitingStatesDemo
```

When all three states are successfully observed before the deadline, the exact stdout is:

```text
Monitor: BLOCKED
Latch: WAITING
Sleep: TIMED_WAITING
```

**Why does the example intentionally keep the state stable?**

- `main` holds `monitor` while the `contender` thread tries to enter the same monitor. `aboutToContend` confirms the worker has reached the point just before lock contention; the `observe` loop waits to see `BLOCKED` instead of doing a single `sleep` and hoping.
- `gate` has not been `countDown()` during observation, so the worker calling `gate.await()` waits. On standard JDKs, a latch uses parking, so we observe `WAITING`. Afterward, `main` calls `countDown()` so the worker can exit.
- `sleeper` starts a long `sleep` so `main` has a chance to sample `TIMED_WAITING`. `interrupt()` in `finally` helps it finish quickly; it **does not forcibly kill the thread**, but causes `sleep` to respond with `InterruptedException`.
- `join()` is used to clean up each worker after its case. There is no need to use `getState()` to decide when to release resources.

This is still an example that measures state under real scheduling: if the JVM or OS is unusually slow, the `observe` loop may time out and throw `IllegalStateException`. The timeout is a **wait limit so the demo does not hang forever**, not a guarantee that the scheduler will always put the worker into the target state within three seconds.

## 6. Why is `getState()` only a snapshot, not a synchronization tool?

Consider the code:

```java
if (worker.getState() == Thread.State.WAITING) {
    // ...
}
```

Immediately after `getState()` returns, another thread may wake the worker up; or the worker may be interrupted, time out, or change state due to another event. The `if` statement only says **`WAITING` was observed**, not that the condition still holds on the very next statement.

This is a form of **time-of-check to time-of-use race**: the state can change between checking it and using that information. You should not write business logic based on the conclusion "if the thread is WAITING, then performing operation X is definitely safe."

Compare two ways of waiting for completion:

```java
// Do not use a state-reading loop as a completion-waiting mechanism.
while (worker.getState() != Thread.State.TERMINATED) {
    Thread.onSpinWait();
}
```

and:

```java
// Standard way to wait for a Thread to finish.
worker.join();
```

`join()` has the semantics of **waiting for a thread to complete**, supports interruption, and provides a happens-before relationship: all actions in the worker happen-before actions in the calling thread after `join()` succeeds. `getState()` is an observation API; it must not be used as a synchronization primitive in place of `join()`.

Similarly, if you want to wait for a task in an executor, use `Future.get()` or `CompletableFuture.join()` according to the required semantics. To know when multiple workers have reached a processing milestone, use `CountDownLatch` or an appropriate barrier. To wait for data, use a queue/condition. Those APIs express **work conditions**, whereas `Thread.State` only describes thread state.

### How do `getState()` and `isAlive()` differ?

`Thread.isAlive()` returns `true` after a thread has been started and has **not yet** died. It is a broader two-state check:

| Observation | `getState()` | `isAlive()` |
| --- | --- | --- |
| Before `start()` | `NEW` | `false` |
| After `start()`, not yet finished | One of `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING` | `true` |
| After `join()` succeeds | `TERMINATED` | `false` |

Because two reads happen at two different times, code must not rely on them always reflecting **the exact same instant**. `isAlive()` also does not prove the worker is making useful progress: the thread could be waiting or stuck.

### `getState()` does not represent the interrupt flag

`Thread.interrupt()` is the mechanism for requesting interruption. The `WAITING` or `TIMED_WAITING` state may change when an interruptible wait call throws `InterruptedException`; the **interrupt flag itself is not a `Thread.State` value**. Use `isInterrupted()` or `Thread.interrupted()` with the proper semantics if you need to check for interruption; note that `Thread.interrupted()` is a static method that checks **the current thread** and clears the interrupt flag when it returns `true`.

## 7. Same waiting state, different causes: reading state and stack trace together

You cannot determine exactly "what it is waiting on" from the enum alone:

- `WAITING` could be a worker waiting for a new task in a pool, a thread calling `join()` on another thread, calling `Object.wait()`, or being `park()`ed by a synchronization utility.
- `TIMED_WAITING` could be an intentional sleep, a timed wait for a signal, or waiting on a scheduled operation with an interval.
- `BLOCKED` indicates waiting for a monitor, but **a single `BLOCKED` observation does not prove deadlock**. It may just be very brief, completely normal lock contention.
- `RUNNABLE` could be executing CPU-bound code or waiting for OS resources; more information is needed to conclude why the system is slow.

When investigating, combine **thread name**, **stack trace**, **sampling timestamp**, **related monitors/locks**, and work progress metrics.

Example of capturing a stack trace in Java:

```java
Thread.State state = worker.getState();
StackTraceElement[] frames = worker.getStackTrace();
```

This snippet uses an existing `worker` variable and is not a standalone program. A stack trace is also a snapshot that may not correspond to the exact same instant as the state read. If the thread changes between the two calls, the stack may reflect a different execution point; do not interpret this as a strictly atomic snapshot.

For JVM diagnostics, Java provides `java.lang.management.ThreadMXBean` to retrieve thread information, stack traces, and certain lock metrics/owners depending on platform support. When checking for deadlocks, `findDeadlockedThreads()` can detect wait cycles involving monitors and JVM-supported ownable synchronizers. A `null` result in one check **does not guarantee the program cannot deadlock in the future**. Thread dumps and tools like `jcmd Thread.print` are also useful for identifying where threads are waiting, though they should be correlated across multiple samples and real load context.

## 8. When should you sample thread states periodically?

`getState()` is useful in **diagnostics**, for example:

1. Confirming a newly created thread has not been started yet (`NEW`).
2. Seeing that a thread has finished after successful coordination (`TERMINATED`).
3. Identifying a worker contending for a monitor (`BLOCKED`) to see whether a critical section is too long.
4. Checking whether a worker is waiting for a signal or a timeout (`WAITING`/`TIMED_WAITING`), and then inspecting the condition and wakeup source.
5. Identifying threads whose states change together across multiple observations, then correlating with logs and thread dumps.

Reading **one** state of **one** thread only supports a narrow conclusion. When you need to understand trends, take multiple timestamped samples and compare them against completed task counts, queue times, CPU, lock contention, and stack traces.

For example, if 20 workers are all `WAITING` and the queue is empty, that may be a healthy idle pool. If the queue has thousands of tasks while workers remain `WAITING` for a long time with no tasks completing, you need to inspect synchronization conditions, signaling, and how work is submitted. Merely counting `WAITING` threads misses the context.

**Do not use continuous state polling in production** to drive task lifecycles. It is expensive, prone to state races, and provides no causal semantics. Add metrics for work progress and use synchronization primitives for control instead of state polling.

## 9. Observing the current thread and a worker thread

`Thread.currentThread()` returns the thread currently executing the statement. Therefore:

```java
Thread current = Thread.currentThread();
System.out.println(current.getName());
System.out.println(current.getState());
```

If called in `main` while the main thread is executing the print statement, `getState()` at the moment of reading will typically be `RUNNABLE`, but the **thread name** depends on how the program is run, and printing/reading stdout can cause the state to change afterward. Do not hardcode thread names or timing measurements in documentation as universal guarantees.

Distinguish this carefully:

```java
Thread worker = new Thread(() -> {
    // Here currentThread() is the worker after start().
});
System.out.println(worker.getState()); // May still be NEW.
worker.start();
```

While `run()` executes on the new worker after `start()`, the main thread continues independently. Calling `getState()` right after `start()` in `main` **does not guarantee** seeing `RUNNABLE`; if the worker finishes extremely quickly, `main` may see `TERMINATED`.

If you replace `worker.start()` with `worker.run()`, Java simply executes `run()` as an ordinary method on `main`; `worker` remains `NEW`, even though the code inside ran once on another thread. This is a mistake that especially leads learners to misunderstand the lifecycle.

## 10. Common misdiagnosis scenarios

### Case A: "A thread is `BLOCKED`, so the application is deadlocked"

Insufficient evidence. `BLOCKED` means waiting for a monitor; if the thread holding the monitor releases it soon, it is just contention. Deadlock requires a circular wait relationship or evidence that the system cannot make progress. You must check lock owners, stack traces, and progress over time.

### Case B: "A worker in a pool is `WAITING`, so it is hung"

Not necessarily. An idle worker may be waiting for a new job from a queue, which is normal. You must look at queue status, active worker count, completed task count, and pool policy.

### Case C: "`RUNNABLE` means running at 100% CPU"

False. `RUNNABLE` is not a CPU meter. A thread may not have been scheduled onto a CPU yet or may be waiting on OS resources. To check CPU usage, use CPU profiling/CPU time from an appropriate diagnostic tool, rather than inferring it from state.

### Case D: "`TIMED_WAITING` means the thread is about to terminate"

False. It only indicates the thread is waiting with a time limit; after the timeout expires or it is interrupted, it can go back to work and repeat the cycle many times.

### Case E: "A `TERMINATED` thread can have `start()` called again"

False. A `Thread` object that has already been started cannot be started a second time. Create a new thread or submit a task to an executor instead.

### Case F: "Calling `getState()` in a loop is the standard way to wait for a thread to finish"

False. Use `join()` or the result of a future/latch. `getState()` is for observation; spinning on state wastes CPU and does not provide the desired synchronization guarantees.

### Case G: "Calling `interrupt()` makes a thread become `TERMINATED`"

Not necessarily. Interruption is only a request. When a thread is in `sleep()` or an interruptible wait, it may throw `InterruptedException`, execute the catch block, and continue. The final state depends on the logic inside `run()`.

### Case H: "Waiting on `ReentrantLock.lock()` is definitely `BLOCKED`"

Incorrect. `BLOCKED` in `Thread.State` is tied to **intrinsic monitors**, not all lock types. Explicit locks may use parking and are therefore often seen in `WAITING`. Read the stack trace to understand the actual API and mechanism.

## 11. Do virtual threads change how we interpret this?

On Java 21+, virtual threads are also `Thread` objects and can be observed with `getState()`. However, a virtual thread is scheduled by the JVM onto carrier platform threads; therefore, **do not equate a virtual thread's state with an OS thread running on a specific CPU**. The timing of parking, waiting, and scheduling can differ in detail from platform threads.

The two Java 17+ programs in this lesson use platform threads to clearly illustrate the foundational lifecycle. If an application uses virtual threads on Java 21+, the meaning of observations still follows `Thread.State`, while performance or scheduler evaluation must be analyzed separately. Do not infer the number of carrier threads from the number of `RUNNABLE` virtual threads.

## 12. Self-check questions

**1. Why can calling `worker.getState()` right after `worker.start()` produce different results across runs?**

Because the scheduler and task duration determine when state transitions happen, while `getState()` only captures a single instant. For a very short-lived worker, `main` may observe `RUNNABLE` or even `TERMINATED` when reading it.

**2. What is the most important difference between `BLOCKED` and `WAITING`?**

`BLOCKED` is directly related to waiting for an **intrinsic monitor**. `WAITING` is waiting without a timeout via mechanisms like `wait/park/join`, which does not mean waiting for monitor entry. An API using `ReentrantLock` can park and appear as `WAITING`.

**3. Does `Thread.sleep(1000)` release a `synchronized` lock that the thread is holding?**

No. `sleep` does not release monitors. Therefore, another thread can be `BLOCKED` while the monitor owner is in `TIMED_WAITING`.

**4. If a thread is in `WAITING`, does that definitely mean the application has a bug?**

No. The thread may be waiting for new work or waiting for a legitimate signal. You need to examine the wait condition, signal source, number of tasks in the queue, and state/stack samples over time.

**5. Why is `join()` used after sampling in the examples?**

Because `join()` actually waits for the worker to finish and establishes a synchronization relationship upon completion. `getState()` only observes; it does not wait and does not hold the state fixed.

**6. Which mechanism should be used to know when three tasks have finished, and what role does `getState()` play?**

Use `CountDownLatch`, futures, or an appropriate completion-waiting mechanism to coordinate the three tasks. `getState()` only helps diagnose which thread is in what state during that process.

## 13. Key takeaways

- `Thread.getState()` returns **one** of six states: `NEW`, `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, `TERMINATED`.
- `RUNNABLE` **does not mean actively consuming CPU**; `BLOCKED` only means waiting for a monitor; `WAITING` and `TIMED_WAITING` describe waiting without or with a timeout.
- `getState()` is a **snapshot that can become stale immediately**. Do not rely on a single observation to determine business conditions or prove a deadlock.
- When you need to **wait for completion**, use `join()`, `Future`, or another synchronization primitive. When you need to **find the cause of waiting**, combine the state with stack traces, monitors/locks, and work progress.
- Design observation examples with controlled conditions, confirm states using **bounded-timeout** polling, and always provide a cleanup path for started threads.

Understanding these limitations makes `getState()` a useful observation tool for learning, testing, and troubleshooting Java concurrency, rather than a source of false inferences about the scheduler or task completion.
