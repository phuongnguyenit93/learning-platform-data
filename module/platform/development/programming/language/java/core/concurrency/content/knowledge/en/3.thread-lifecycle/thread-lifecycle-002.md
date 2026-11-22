# The BLOCKED, WAITING, and TIMED_WAITING States in the Java Thread Lifecycle

The three states `BLOCKED`, `WAITING`, and `TIMED_WAITING` all indicate that a thread is not currently making normal Java execution progress like a `RUNNABLE` thread. However, **the reason for waiting, the resources involved, and the wake-up mechanism are completely different**. Accurately distinguishing between these three states helps when reading thread dumps, identifying lock contention and deadlocks, and designing proper thread coordination. The content below applies to Java concurrency in general and is framework-independent.

## 1. Placing the Three States in the Full Lifecycle

`java.lang.Thread.State` is an `enum` with six values:

| State | Summary Meaning |
| --- | --- |
| `NEW` | The `Thread` object has been created, but `start()` has not been called yet. |
| `RUNNABLE` | The thread is ready to run or currently executing in the JVM; **this does not mean** it is occupying the CPU at every moment. |
| `BLOCKED` | Waiting to acquire an **intrinsic monitor lock** to enter or re-enter a `synchronized` block or method. |
| `WAITING` | Waiting indefinitely under a specific waiting mechanism until an event allows it to proceed. |
| `TIMED_WAITING` | Waiting under a timed mechanism, which can end due to a wake-up event or when the timeout expires. |
| `TERMINATED` | The `run()` method has finished, either normally or via an unhandled exception. |

There is no `RUNNING`, `SLEEPING`, or `DEADLOCKED` value in `Thread.State`. For example, "sleeping" is represented by `TIMED_WAITING`; a deadlock is a system condition that may manifest as `BLOCKED` or other waiting states. A thread can transition through many states before terminating; **this is a point-in-time snapshot, not the thread's full history**.

The three focal states:

| Criterion | `BLOCKED` | `WAITING` | `TIMED_WAITING` |
| --- | --- | --- | --- |
| What is it waiting for? | Ownership of a monitor lock | A signal/event, with no timeout specified on the wait operation | A signal/event **or** a time deadline |
| Direct examples | Entering `synchronized(lock)` while another thread holds `lock` | `Object.wait()`, `Thread.join()`, `LockSupport.park()` | `Thread.sleep(ms)`, `Object.wait(ms)`, `Thread.join(ms)`, `LockSupport.parkNanos(ns)` |
| Automatic timeout? | No timeout on acquiring a monitor via `synchronized` | No timeout specified | Yes, though there is no guarantee of running immediately at the exact deadline |
| Can it hold other locks? | Yes | Yes, depending on the API; specifically `Object.wait()` releases the monitor of the object being waited on | Yes, for example `sleep` does not release any held monitors |
| What to investigate | Who holds the monitor? How long is it held? Is there a deadlock cycle? | What condition is it waiting for? Who sends the signal? | What is the wait deadline? Is the timeout or signal working properly? |

## 2. BLOCKED: Waiting to Acquire an Intrinsic Monitor

Example:

```java
Object lock = new Object();

Thread first = new Thread(() -> {
    synchronized (lock) {
        // Task A holds the monitor of lock.
    }
});
Thread second = new Thread(() -> {
    synchronized (lock) {
        // Task B must wait if A is holding the monitor.
    }
});
```

This is an **illustrative snippet**, not a complete program. If `first` is inside `synchronized (lock)` when `second` attempts to enter the same monitor, `second` may be in `Thread.State.BLOCKED` until it acquires the lock. Simply declaring two threads as above **does not start them**: `start()` must be called; and contention cannot be assumed without proper coordination/timing.

### What is a monitor?

Every Java object can act as an intrinsic monitor. `synchronized (object)` requires the thread to own the monitor before entering the critical section; `synchronized` on an instance method uses the monitor of `this`; `static synchronized` uses the monitor of the corresponding `Class` object. When the monitor is held by another thread, a thread that has not yet acquired it waits in `BLOCKED`.

- Intrinsic monitors are **reentrant**: the same thread can re-enter a `synchronized` block on the same monitor without deadlocking itself.
- Exiting `synchronized` normally or via an exception releases the monitor according to Java's mechanism.
- If a thread holds a monitor while performing long I/O, calling `sleep`, invoking a slow service, or doing heavy computation, other threads may queue up in `BLOCKED`.
- `BLOCKED` **does not mean** waiting on network or disk. With `ReentrantLock`, `Condition`, or many structures built on `AbstractQueuedSynchronizer`, waiting is typically implemented via `LockSupport.park` and may appear as `WAITING` or `TIMED_WAITING`; it does not necessarily show up as `BLOCKED`.
- There is no `synchronized.tryLock(timeout)`; if you need a bounded wait time to acquire a lock, consider the `Lock.tryLock(timeout, unit)` API and handle failure explicitly.

### Is BLOCKED a deadlock?

No. Brief contention is normal. A **deadlock** occurs when there is a circular wait dependency—for example, A holds `lock1` and waits for `lock2`, while B holds `lock2` and waits for `lock1`. In that case, both threads may remain `BLOCKED` forever. However, a thread in `BLOCKED` for 2 ms may simply be waiting for a legitimate critical section. To investigate, examine **the monitor being waited on, the thread currently owning that monitor, and the dependency chain**, rather than just counting `BLOCKED` threads.

## 3. WAITING: Waiting Indefinitely for a Condition or Signal

`WAITING` means the current wait method does not specify a time limit. Common sources:

- `Object.wait()`: the thread must hold the object's monitor, then **releases that object's monitor** and enters the wait set to wait for `notify`/`notifyAll`, an interrupt, or a spurious wakeup. Before `wait()` returns normally or throws `InterruptedException`, the thread must re-acquire that monitor.
- `Thread.join()` without a timeout: waits for the target thread to terminate if it is still alive; the thread calling `join` is the one waiting. Do not confuse the thread "being joined" with the thread in `WAITING`.
- `LockSupport.park()`: parks the thread until `unpark`, an interrupt, or a return permitted by the API. `park` **does not automatically release monitor locks** held by the caller.
- Some untimed wait operations such as `CountDownLatch.await()`, `Future.get()`, and `Condition.await()`: when they actually have to wait, they typically park the thread and may appear as `WAITING`. The actual state is a snapshot; do not rely on API names alone to assert the state at every nanosecond.

**Indefinite does not mean impossible to exit.** A signal may arrive, the condition may be met, the thread may be interrupted, an async result may complete, or the API may allow a spurious wakeup. Conversely, if the expected event never occurs, the thread may wait forever.

### How `Object.wait()` differs from `Thread.sleep()` in releasing locks

This is a very common point of confusion:

- When calling `lock.wait()` inside `synchronized(lock)`, the thread **releases `lock`'s monitor** so another thread can enter `synchronized(lock)`, update the condition, and call `notifyAll()`.
- When calling `Thread.sleep(...)` inside `synchronized(lock)`, the thread **keeps holding the monitor**. Other threads trying to enter the same monitor will become `BLOCKED` while it sleeps.
- `wait()` only releases the monitor of the object on which `wait` is called; if the thread holds any other monitors, they are **not automatically released**.
- `notify()` wakes up one eligible waiter in the wait set, with no guarantee of choosing the specific thread the developer intended. `notifyAll()` notifies all waiters on that monitor; those threads **must still contend to re-acquire the monitor**.

### Standard pattern: waiting for a condition with a `while` loop

`Object.wait()` is only a waiting mechanism; the business condition determines whether the thread can proceed. Because unexpected wakeups can occur, the condition must always be checked in a **`while`** loop rather than assuming a single `notify` means data is ready.

Standalone Java 17 example, saved as `WaitNotifyExample.java`:

```java
public class WaitNotifyExample {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        boolean[] ready = {false};

        Thread consumer = new Thread(() -> {
            synchronized (lock) {
                while (!ready[0]) {
                    try {
                        lock.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("Da nhan tin hieu");
            }
        });

        consumer.start();

        synchronized (lock) {
            ready[0] = true;
            lock.notifyAll();
        }

        consumer.join();
        System.out.println("Hoan tat");
    }
}
```

Run with Java 17+:

```bash
javac WaitNotifyExample.java
java WaitNotifyExample
```

Deterministic stdout:

```text
Da nhan tin hieu
Hoan tat
```

The `ready` state is only read/written while holding `lock`, ensuring synchronization and visibility guarantees. If the producer enters the monitor before the consumer, the consumer sees `ready=true` and does not need to call `wait()`; if the consumer enters first, it calls `wait()` to **release** the monitor, allowing the producer to update the condition and call `notifyAll()`. Both execution paths are correct and never miss a signal because checking the condition and waiting happen within the same critical section. This example illustrates the `wait/notifyAll` protocol and **does not guarantee** that the consumer passes through `WAITING` on every run.

**Do not call `wait()/notify()/notifyAll()` without owning the object's monitor**: doing so throws `IllegalMonitorStateException`. Avoid using `wait` directly when `BlockingQueue`, `CountDownLatch`, `Condition`, or higher-level concurrency primitives express the requirement cleanly and with less risk.

## 4. TIMED_WAITING: Waiting with a Time Limit

Typical operations:

| API | Meaning | Impact on Monitors |
| --- | --- | --- |
| `Thread.sleep(1000)` | Pauses for at least roughly 1,000 ms according to scheduling, unless interrupted | **Does not** release held monitors |
| `lock.wait(1000)` | Waits in `lock`'s wait set for up to the specified duration; may wake up early | Releases `lock`'s monitor while waiting and re-acquires it before returning |
| `otherThread.join(1000)` | Waits for the target thread to terminate for up to the timeout | Does not release all monitors held by the caller |
| `LockSupport.parkNanos(nanos)` | Parks for up to the specified positive nanoseconds | Does not automatically release monitors |
| `future.get(timeout, unit)` or `latch.await(timeout, unit)` | Waits for a result/condition with a timeout | Does not by default release intrinsic monitors held by the caller |

`TIMED_WAITING` only shows that the caller is currently waiting in a timed operation; **it does not prove** that the thread is "hung" or violating an SLA. Actual wait duration is affected by OS/JVM scheduling; timeout expiration does not mean the caller immediately gets CPU time. Several APIs can also return early due to a signal, completion, interrupt, or spurious wakeup. `Thread.sleep` in particular can be interrupted, but should not be used as a condition-coordination mechanism.

**Java API note:** `Object.wait(0)` means wait *indefinitely*, not wait 0 ms and return immediately; `Thread.join(0)` also waits indefinitely. For positive deadlines, use the timed overloads and be clear about unit conventions (milliseconds/nanoseconds). `Thread.sleep(0)` does not create a useful `TIMED_WAITING` interval for condition waiting.

## 5. Runnable Experiment: Observing All Three States on Java 17

Run a coordinated program to produce all three target states. For `BLOCKED`, `main` holds a monitor and starts a contender. For `WAITING`, a thread uses `LockSupport.park()`. For `TIMED_WAITING`, a thread uses a timed `sleep`. The program checks `getState()` at a point where the wait reason is known; it does not rely on machine speed or accidental ordering.

Create `ThreadStatesExample.java`:

```java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.LockSupport;

public class ThreadStatesExample {
    private static void awaitState(Thread thread, Thread.State expected)
            throws InterruptedException {
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (thread.getState() != expected) {
            if (!thread.isAlive() || System.nanoTime() >= deadline) {
                throw new IllegalStateException(
                        "Khong quan sat duoc: " + expected);
            }
            Thread.sleep(1);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();

        Thread contender = new Thread(() -> {
            synchronized (lock) {
                // Enters after main releases the monitor.
            }
        }, "monitor-contender");

        synchronized (lock) {
            contender.start();
            awaitState(contender, Thread.State.BLOCKED);
            System.out.println("Da quan sat: BLOCKED");
        }
        contender.join();

        AtomicBoolean done = new AtomicBoolean(false);
        Thread parked = new Thread(() -> {
            while (!done.get()) {
                LockSupport.park();
            }
        }, "parked-worker");

        parked.start();
        awaitState(parked, Thread.State.WAITING);
        System.out.println("Da quan sat: WAITING");
        done.set(true);
        LockSupport.unpark(parked);
        parked.join();

        Thread sleeper = new Thread(() -> {
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "sleeping-worker");

        sleeper.start();
        awaitState(sleeper, Thread.State.TIMED_WAITING);
        System.out.println("Da quan sat: TIMED_WAITING");
        sleeper.interrupt();
        sleeper.join();
    }
}
```

```bash
javac ThreadStatesExample.java
java ThreadStatesExample
```

Stdout when the states are observed within the check timeout:

```text
Da quan sat: BLOCKED
Da quan sat: WAITING
Da quan sat: TIMED_WAITING
```

**Experiment explanation:**

1. `main` holds `lock`. `contender` calls `synchronized(lock)` but cannot acquire the monitor yet, so it becomes `BLOCKED`. Once `main` exits the synchronized block, `contender` can enter the monitor and finish.
2. `parked` calls `LockSupport.park()` without an available permit, so it can enter `WAITING`. `main` sets the `done` flag and calls `unpark`; the loop around `park` handles cases where `park` returns without `unpark`. `AtomicBoolean` ensures visibility of the flag.
3. `sleeper` sleeps for up to 10 seconds. `main` observes `TIMED_WAITING`, then calls `interrupt()` to end it early without waiting the full 10 seconds.

`awaitState` is for **experimentation only**. It polls a snapshot with a deadline and may throw an exception if the machine is extremely busy or the thread is affected unexpectedly. In production, **do not write application control logic by guessing thread states with `getState()`**; use `join`, `CountDownLatch`, `Future`, `Condition`, or condition-based coordination primitives. States can change very quickly between two reads.

## 6. Common State Transitions

### Monitor contention

```text
Thread A: RUNNABLE --enters synchronized(lock) successfully--> RUNNABLE
Thread B: RUNNABLE --fails to acquire monitor lock--> BLOCKED
Thread A: ... exits synchronized(lock), releases monitor ...
Thread B: BLOCKED --acquires monitor--> RUNNABLE
```

This is a logical flow; acquiring a monitor and changing states can happen very quickly, so sampling is not guaranteed to catch every state.

### `wait()/notifyAll()`

```text
Consumer holds monitor M and sees condition=false
Consumer calls M.wait(): releases M, may enter WAITING
Producer acquires M, updates condition=true, calls M.notifyAll()
Consumer is woken up but must re-acquire M
Consumer may be BLOCKED while producer still holds M
Producer releases M; consumer re-acquires M, re-checks while loop, then continues
```

**`notifyAll()` does not immediately hand over the monitor** to a waiter. If the producer continues holding `M` for a long time, the consumer cannot execute the code after `wait()` even though it has been notified. After receiving the notification, the waiter may also not be the thread immediately chosen by the scheduler. Use `while` because the signal only tells the thread to re-check the condition; it does not replace the condition check.

### Timed waiting

```text
RUNNABLE --Thread.sleep(200)--> TIMED_WAITING
TIMED_WAITING --timeout expires or interrupt--> RUNNABLE
```

With `wait(timeout)` or `join(timeout)`, reaching the end of the timeout **does not guarantee** that the condition is satisfied. With `wait(timeout)`, the thread must still re-acquire the monitor; with `join(timeout)`, you must check `isAlive()` if you need to know whether the target thread actually terminated.

## 7. What Happens on Interrupt?

`Thread.interrupt()` is a **cooperative signal requesting cancellation or redirection**, not an immediate command to kill the thread.

| Operation | Typical Response |
| --- | --- |
| `Object.wait()`, `Thread.sleep()`, `Thread.join()` | Throws `InterruptedException` if interrupted while waiting, and the interrupt status is typically cleared when the exception is thrown |
| `CountDownLatch.await()`, `Future.get()` | May throw `InterruptedException` per the API contract |
| `LockSupport.park()` | May return and preserve the interrupt flag; does not throw `InterruptedException` |
| Waiting for a `synchronized` monitor (`BLOCKED`) | Interrupt cannot cancel acquiring an intrinsic monitor via the `synchronized` syntax |
| `ReentrantLock.lockInterruptibly()` | Can respond to interrupts while waiting for the lock, unlike `synchronized` |

When catching `InterruptedException` without rethrowing it, code should typically restore the flag via `Thread.currentThread().interrupt()` and exit or propagate an appropriate error. Do not write a `while(true)` loop that keeps waiting and swallows interrupts indefinitely. When using `LockSupport.park()`, note that if the interrupt flag remains set, a subsequent `park()` may return immediately; ensure there is a clear exit condition.

## 8. Reading Thread Dumps Properly

On HotSpot/OpenJDK, you can capture a JVM thread dump using JDK diagnostic tools, for example (replace with actual PID):

```bash
jcmd <PID> Thread.print -l
```

The following snippets **illustrate common structural information**, not fixed stdout across all JDK versions:

```text
"worker-1" ... java.lang.Thread.State: BLOCKED (on object monitor)
    - waiting to lock <...> (a java.lang.Object)
"worker-2" ... java.lang.Thread.State: WAITING (parking)
    at jdk.internal.misc.Unsafe.park(...)
"worker-3" ... java.lang.Thread.State: TIMED_WAITING (sleeping)
    at java.lang.Thread.sleep(...)
```

Always read the stack trace, the monitor/synchronizer being waited on, the lock owner thread, and evidence across multiple thread dumps:

- **Many `BLOCKED` threads on the same monitor:** find the thread holding the monitor, where the lock was acquired, and the duration of the critical section. If many threads contend for the same lock for a long time, consider narrowing the `synchronized` scope or removing blocking I/O from the critical section.
- **`WAITING` at `Object.wait`:** identify the condition, the `notify/notifyAll` path, whether the producer can run, and whether the condition is re-checked.
- **`WAITING` at `LockSupport.park`:** inspect the synchronization library in the stack trace (`Future`, `ReentrantLock`, queue, idle pool worker, etc.). An idle thread pool worker that is parked can be **completely normal**.
- **`TIMED_WAITING` at `sleep`:** find out why it is sleeping (retry, backoff, schedule, or accidental blocking). `TIMED_WAITING` on a timed queue poll or connection wait has a different meaning; inspect the calling frames and deadline.
- **Deadlock:** identify a cycle between threads and locks. `ThreadMXBean.findDeadlockedThreads()` helps detect certain deadlocks involving object monitors and ownable synchronizers, but it does not replace analyzing logical wait cycles, network, DB, or external resources.

`Thread.getState()`, thread dumps, and metrics are **observability** tools, not mechanisms to enforce synchronization protocols. Java-level thread states also do not map 1:1 to OS scheduler states: for example, a `RUNNABLE` thread may still be waiting on OS resource handling. The presence of `WAITING` or `TIMED_WAITING` alone does not prove a performance bug.

In Java 21+, **virtual threads** also expose Java-level states at the API level, but mounting/unmounting on carrier threads and how JVM tools display virtual threads can differ from platform threads. Do not infer OS thread counts simply by counting waiting virtual threads; interpret diagnostics according to your JDK version. This article does not use any framework or API outside Java core and Java concurrent utilities.

## 9. Distinguishing Monitor Waiting from Condition Waiting

A common source of confusion:

```java
synchronized (lock) {
    lock.wait();
}
```

Before calling `wait`, the thread already **owns the monitor**. Upon entering `wait`, it releases the monitor and enters `WAITING`; after `notifyAll`, it must re-acquire the monitor. While trying to re-acquire the monitor before succeeding, its state may be `BLOCKED`. Thus, **a thread can appear in `WAITING` and then transition to `BLOCKED` within the same coordination cycle**, with no contradiction.

Conversely:

```java
synchronized (lock) {
    Thread.sleep(500);
}
```

The sleeping thread may be in `TIMED_WAITING` **while still holding `lock`**. Other threads attempting to enter `synchronized(lock)` will be `BLOCKED`. This is usually why sleeping, making HTTP calls, reading files, or waiting on a long-running `Future` inside a critical section should be avoided.

With `ReentrantLock` and `Condition`, `condition.await()` releases **the lock associated with the condition** while waiting and re-acquires it before continuing—serving a similar coordination purpose to `Object.wait` with a different API. Do not conclude "no `BLOCKED` means no lock contention": many modern locks park threads and show up as `WAITING`.

## 10. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Treating every `BLOCKED` as a deadlock | Brief monitor contention can be normal | Find the owner and wait cycle; compare multiple thread dumps |
| Treating every `WAITING` as a hung thread | Idle workers and waiting on a queue/signal are valid states | Inspect the stack, exit condition, duration, and system load |
| Assuming `WAITING` only comes from `Object.wait` | `join`, `park`, and many synchronizers also wait | Read the actual stack frames and associated resources |
| Assuming `TIMED_WAITING` means a timeout has occurred | It is the state **while** waiting with a deadline | Check return values/exceptions and deadlines |
| Calling `notify` and assuming the waiter gets the monitor immediately | The waiter still has to contend to re-acquire the monitor | Keep critical sections short and use a condition loop |
| Using `if (conditionFalse) wait()` | Spurious wakeups, multiple consumers, and changed conditions | Use `while` to re-check the condition after waking |
| Calling `wait` outside `synchronized` | Throws `IllegalMonitorStateException` | Hold the proper monitor before calling `wait` |
| Assuming `sleep` or `park` releases monitors | They do not automatically release intrinsic monitors | Avoid sleep/I/O/long waits while holding a monitor |
| Swallowing `InterruptedException` | Loses cancellation signals and makes shutdown hard | Propagate or restore the interrupt and exit appropriately |
| Relying on `getState()` for production coordination | Race condition between reading the state and acting | Use `Future`/`CountDownLatch`/queues/conditions |
| Using `wait(0)` as a zero timeout | `wait(0)` means wait indefinitely | Use a positive timeout and verify units and deadlines |
| Assuming `ReentrantLock` contention always shows as `BLOCKED` | It may use `park`/`WAITING` | Read the stack trace and lock metadata |

## 11. Quick Check-Your-Understanding Questions

**1. If two threads are both `BLOCKED`, is it definitely a deadlock?** No. They could both be waiting for a third thread to release a monitor. Confirm a deadlock only when there is an unresolvable wait cycle or an appropriate diagnostic detection.

**2. What state will a thread calling `join()` be in?** If the target thread is still running and the caller actually has to wait without a timeout, the caller may be in `WAITING`. `join(positive timeout)` can lead to `TIMED_WAITING`. If the target has already terminated, the caller does not need to enter a waiting state.

**3. Does `notifyAll()` move a thread from `WAITING` directly to `RUNNABLE`?** Not necessarily. The woken thread must re-acquire the monitor for `wait`, so it may be seen in `BLOCKED` before continuing. After resuming, it must still check the condition in a `while` loop.

**4. Does `Thread.sleep(1000)` inside `synchronized` allow another thread to enter the monitor?** No. A sleeping thread does not automatically release monitors. Other threads may become `BLOCKED` while it is in `TIMED_WAITING`.

**5. Is a thread in `TIMED_WAITING` guaranteed to finish its task after 1 second?** No. The timeout only bounds a specific wait operation; scheduling, re-acquiring locks, and the remaining steps of the task can make the total time longer.

**6. Does having many `WAITING` threads in a thread pool mean it is overloaded?** You cannot conclude that. Idle workers waiting for new tasks are normal. You need to look at active workers, queue depth, throughput, latency, errors, and stack traces.

## 12. Practical Checklist for Debugging Java Concurrency

1. Record the **state, stack trace, lock identity, and lock owner** of the relevant threads at multiple points in time.
2. If `BLOCKED`, identify which monitor is contended and why the holder keeps it for so long.
3. If `WAITING`, identify the waiting mechanism (monitor, park, join, Future, latch, queue) and the release condition/actor.
4. If `TIMED_WAITING`, identify the configured timeout, its unit, early-exit conditions, and timeout handling.
5. Verify whether monitors are held during `sleep`, I/O waits, or `park`; check for both deadlocks and logical stalls.
6. Review interrupt handling, cancellation, condition loops, timeouts, and resource release.
7. Draw conclusions from **multiple pieces of evidence** (thread dumps, JFR, logs, CPU/lock metrics), not from a single `getState()` value.

**Key takeaway:** `BLOCKED` is contention for an **intrinsic monitor**; `WAITING` is untimed waiting on a coordination mechanism; `TIMED_WAITING` is timed waiting. The most important questions when troubleshooting are **what the thread is waiting for, what/who will let it proceed, and whether it is holding resources that block other threads**.