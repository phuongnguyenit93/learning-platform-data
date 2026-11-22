# Waiting Threads in Java: Understanding the WAITING State and Diagnosing with jstack

A **waiting thread** is a thread that has paused execution to wait for an action or condition from another thread. In Java, this state is represented by `Thread.State.WAITING`. This is often normal behavior in a multithreaded program: a worker waiting for data, a thread waiting for another thread to finish, or a task waiting for a synchronization signal.

Problems arise when a thread waits indefinitely because the signal never arrives, a shared condition is not updated properly, the thread holds a needed lock, or all workers in a thread pool are waiting on tasks that the pool itself must execute. To distinguish normal waiting from a hung application, you need to understand waiting mechanisms, how threads are woken up, and how to read thread dumps using `jstack` or `jcmd`.

## 1. What thread states exist in Java?

`Thread.State` is an enum that describes the state of a thread at a point of observation. Java defines six states:

| State | Meaning | Example |
|---|---|---|
| NEW | Created but `start()` has not been called yet | `new Thread(task)` |
| RUNNABLE | Executing or ready to be scheduled by the JVM | Running Java code |
| BLOCKED | Waiting to acquire a monitor lock to enter or re-enter a `synchronized` block | Another thread holds the lock |
| WAITING | Waiting indefinitely for an action from another thread | `Object.wait()`, `Thread.join()` |
| TIMED_WAITING | Waiting for a specified period | `sleep()`, `wait(timeout)` |
| TERMINATED | Execution has completed | `run()` finished |

These are JVM-level states, not a direct mirror of operating system thread states. `RUNNABLE` also does not guarantee that the thread is actively consuming CPU at the exact moment of observation.

`Thread.getState()` returns a snapshot. The state can change immediately after being read, so do not use this result as a synchronization mechanism or a substitute for locks, conditions, or queues.

## 2. What causes a thread to enter WAITING?

According to the Java API, a thread can enter `WAITING` by calling one of the following methods without a timeout:

- `Object.wait()`: waits for another thread to call `notify()` or `notifyAll()` on the same object, or to be interrupted.
- `Thread.join()`: waits for the joined thread to terminate.
- `LockSupport.park()`: pauses until a permit/unpark is available, the thread is interrupted, or another permitted return occurs.

Many higher-level concurrency APIs also use the park mechanism under the hood. Therefore, a thread dump may show `WAITING (parking)` even if application code never calls `Object.wait()` directly.

Some common scenarios:

- An executor worker waiting for a new task.
- A consumer waiting for data in `BlockingQueue.take()`.
- A thread waiting on `CountDownLatch.await()`.
- A thread waiting on `Future.get()` or `CompletableFuture.join()`.
- A thread waiting on a lock condition via `Condition.await()`.
- The main thread calling `worker.join()` to wait for a worker to finish.

A thread in the WAITING state does not automatically indicate a bug. You need to determine which condition the thread is waiting for and who is responsible for making that condition happen.

## 3. Distinguishing WAITING, BLOCKED, and TIMED_WAITING

These three states often appear next to each other in thread dumps, but they describe different situations.

| State | What the thread is waiting for | Timed? | Common indicators |
|---|---|---|---|
| WAITING | An action/signal from another thread | No | `Object.wait`, `Thread.join`, `LockSupport.park` |
| BLOCKED | Ownership of an intrinsic monitor | No | `waiting to lock`, `BLOCKED (on object monitor)` |
| TIMED_WAITING | An action or time expiration | Yes | `Thread.sleep`, `wait(timeout)`, `join(timeout)` |

Example:

~~~java
synchronized (lock) {
    lock.wait();          // WAITING
}

Thread.sleep(1_000);      // TIMED_WAITING

synchronized (lock) {
    // If another thread holds the lock, this thread is BLOCKED
}
~~~

`wait()` and `sleep()` are not equivalent. `wait()` is called on a monitor and releases that monitor while waiting. `sleep()` pauses the thread without releasing any monitor locks the thread currently holds.

## 4. How does Object.wait() work?

`wait()` must be called by a thread that owns the object's monitor. Typically, the call sits inside a `synchronized` block on that same object.

When `lock.wait()` is called, the JVM performs these main steps:

1. Checks whether the current thread owns the monitor of `lock`.
2. Places the thread into the object's wait set.
3. Releases the synchronization claims the thread holds on that specific object.
4. Suspends the thread until it is notified, notifiedAll, interrupted, timed out, or spuriously woken up.
5. The thread competes to re-acquire the monitor.
6. Only after re-acquiring the monitor does the `wait()` call return or throw `InterruptedException`.

Important note: `wait()` only releases the monitor of the object it was called on. If the thread holds another lock, that lock can remain held for the entire wait duration. This is the source of many hard-to-spot deadlocks.

## 5. Why doesn't notify() make the thread run immediately?

`notify()` wakes up a single thread waiting on the current monitor. `notifyAll()` wakes up all threads waiting on that monitor.

A woken thread cannot continue immediately. It must wait for the thread currently owning the monitor to release the lock, and then compete to acquire the lock. The order in which `notify()` selects a thread is not guaranteed.

Both `notify()` and `notifyAll()` must be called while the current thread owns the same monitor. Otherwise, the JVM throws `IllegalMonitorStateException`.

Example:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

Updating the condition and signaling within the same critical section prevents race conditions. You should not call notify first and update the state outside the monitor.

## 6. The right wait/notify pattern: check the condition in a while loop

Do not write:

~~~java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useResource();
}
~~~

This is incorrect because a thread can experience a spurious wakeup, or another thread might consume the condition before the current thread resumes. In that case, code could proceed even though the condition is not met.

Use `while`:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    useResource();
}
~~~

The loop re-checks the condition after every wakeup. If the condition is still not met, the thread goes back to waiting.

The producer must also update the state under the same monitor:

~~~java
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}
~~~

The monitor ensures that updating and checking the state are synchronized. Exiting the producer's synchronized block happens-before the consumer re-acquires the same monitor, allowing the consumer to see the published update.

## 7. Avoiding lost notifications

A common bug occurs when a thread sends a signal before the consumer starts waiting. If you only use notify without storing the condition state, the signal can be lost.

Unsafe pattern:

~~~java
// Producer
lock.notify();

// Consumer
lock.wait();
~~~

`notify()` is not a stored message that a later thread can pick up. It only wakes up a thread currently in the wait set at the moment of the call.

Safe pattern storing the condition state:

~~~java
// Producer
synchronized (lock) {
    ready = true;
    lock.notifyAll();
}

// Consumer
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
~~~

If the producer runs first, the consumer sees `ready == true` and does not need to wait. If the consumer runs first, it places itself into the wait set; the producer updates the state and wakes it up. Both sides use the same monitor, so there is no gap between checking and registering to wait.

## 8. Why use notifyAll() when there are multiple types of waiters?

`notify()` picks an arbitrary waiter. If multiple threads wait on different conditions on the same monitor, the chosen thread might not be able to handle the condition that just changed.

For example, a single monitor might have consumers waiting for data and producers waiting for space. If notify wakes the wrong group, that thread checks its condition and goes back to sleep, while the thread that actually needs to run keeps waiting.

`notifyAll()` wakes all waiters so each thread re-checks its condition in its while loop. This is usually easier to get right when multiple conditions share a monitor, even though it can wake multiple threads to contend for the lock.

For systems with multiple independent conditions, consider using `ReentrantLock` with separate `Condition` instances, or higher-level abstractions like queues and semaphores to model the behavior cleanly.

## 9. Interruption as a way to ask a waiting thread to stop

`interrupt()` is a signal requesting a thread to cancel or stop its current activity. If the thread is waiting in `Object.wait()`, `Thread.sleep()`, or `Thread.join()`, it typically receives an `InterruptedException`.

When `InterruptedException` is thrown from these methods, the thread's interrupt status is cleared. If you catch the exception and do not propagate it, your code should restore the interrupt status when appropriate:

~~~java
try {
    lock.wait();
} catch (InterruptedException exception) {
    Thread.currentThread().interrupt();
    return;
}
~~~

If a method can declare `throws InterruptedException`, it is usually best to propagate the exception to the caller so the orchestration layer can decide whether to cancel the task. If you cannot propagate it, restore the interrupt status instead of swallowing the signal.

Do not use `Thread.stop()` to terminate a thread. Use interruption and a controlled shutdown procedure.

## 10. Waiting with a timeout and TIMED_WAITING

If you only want to wait for a bounded duration, use `wait(timeout)` or an equivalent timeout-based API. The thread will typically be in `TIMED_WAITING`.

Example:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait(2_000);
    }
}
~~~

A timeout does not guarantee the condition has become true. After the time expires, the thread must still re-check the state.

If you need to wait until an overall deadline while potentially waking up multiple times, compute the remaining time using `System.nanoTime()`. Do not repeat the full timeout after every spurious wakeup, as the total wait time could exceed expectations.

~~~java
long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);

synchronized (lock) {
    while (!ready) {
        long remaining = deadline - System.nanoTime();
        if (remaining <= 0) {
            break;
        }
        TimeUnit.NANOSECONDS.timedWait(lock, remaining);
    }
}
~~~

In real-world applications, consider using `Condition.awaitNanos()`, `CountDownLatch.await(timeout, unit)`, or deadline-aware APIs instead of writing synchronization primitives manually.

## 11. Using concurrency utilities instead of manual wait/notify

`wait/notify` is useful for understanding monitors, but many problems have safer and more readable abstractions in `java.util.concurrent`.

| API | Waiting model | When to use |
|---|---|---|
| CountDownLatch | Wait for a number of events to complete | Waiting for multiple initialization steps |
| CyclicBarrier | Multiple threads meet at a barrier point | Phased work coordination |
| BlockingQueue | Consumer waits for elements; producer waits for space | Producer/consumer pipelines |
| Semaphore | Wait for a permit | Limiting concurrent tasks |
| ReentrantLock + Condition | Wait on a condition tied to a lock | Multiple synchronization conditions |
| Future.get | Wait for a task result | Integrating with synchronous APIs |
| CompletableFuture | Chain asynchronous steps | Async pipelines |
| Thread.join | Wait for a thread to finish | Simple thread coordination |

Example of a consumer waiting on a queue:

~~~java
BlockingQueue<String> queue = new LinkedBlockingQueue<>();

String message = queue.take();
System.out.println("RECEIVED=" + message);
~~~

`take()` waits automatically when the queue is empty and wakes up when an element arrives. This expresses intent much more clearly than manually managing monitors, state flags, and notify calls.

## 12. Thread pools can have normal WAITING threads

Thread pools normally keep worker threads in a waiting state when there are no tasks. A thread dump may show workers parked in a queue or executor. This is usually an expected idle state by design.

However, a thread pool can suffer from starvation if all workers synchronously wait on other tasks submitted to the very same pool.

Example of a dangerous scenario:

1. The pool has two workers.
2. Two parent tasks occupy both workers.
3. Each parent task submits a child task to the same pool.
4. Each parent task calls `get()` to wait for its child task.
5. No free workers remain to run the two child tasks.

Both parent threads are WAITING, and the child tasks sit in the queue unable to start. This is a thread starvation deadlock even though there is no monitor deadlock cycle.

Avoid blocking workers waiting for subtasks in the same small, bounded pool. Use composition with `CompletableFuture`, separate executors by workload type, or design non-blocking pipelines where appropriate.

## 13. Reading thread dumps to find waiting threads

A thread dump is a snapshot of the stack traces and states of threads in a JVM. It helps answer:

- Which threads are WAITING?
- At which method is a thread waiting?
- Is it waiting on a monitor, a synchronizer, or a task result?
- Which thread holds the lock another thread needs?
- Do stack traces change across snapshots?
- Has the JVM detected any Java-level deadlocks?

In a dump, locate the thread name first, then read its state and stack trace right below it. For example:

~~~text
"demo-waiter" #35 prio=5 ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(...)
    at WaitingThreadDemo.lambda$main$0(WaitingThreadDemo.java:19)
    - waiting on <0x...> (a java.lang.Object)
~~~

The stack trace shows the thread waiting at `Object.wait()` in `WaitingThreadDemo`. If a thread is in `WAITING (parking)`, look for frames like `LockSupport.park`, `AbstractQueuedSynchronizer`, `CountDownLatch`, or `FutureTask` to understand the abstraction it is waiting on.

## 14. Finding JVM processes with jcmd or jps

Use `jcmd -l` to list running JVMs:

~~~bash
jcmd -l
~~~

Or:

~~~bash
jps -l
~~~

The output typically includes the process ID and main class. Pick the PID of the application you want to inspect. If running in a container, the PID namespace may differ from the host PID; run the command in the appropriate environment or use a suitable process access mechanism.

`jcmd` must run on the same machine as the target JVM and usually requires the same effective user/group that started the JVM. If attach is refused, check the user, container, OS permissions, and JVM configuration rather than assuming the application has no threads.

## 15. Using jcmd Thread.print

On modern JDKs, Oracle recommends preferring `jcmd` for JVM diagnostics.

Take a thread dump:

~~~bash
jcmd -l
jcmd 12345 Thread.print
~~~

Add `-l` to print information about `java.util.concurrent` locks:

~~~bash
jcmd 12345 Thread.print -l
~~~

In PowerShell, you can look up the PID by main class name:

~~~powershell
$jvm = jcmd -l | Select-String 'WaitingThreadDemo' | Select-Object -First 1
$javaPid = ($jvm.ToString() -split '\s+')[0]
jcmd $javaPid Thread.print -l
~~~

Replace the class name in the filter with your running application's name. Verify the PID list before sending commands to avoid inspecting the wrong JVM.

## 16. Using jstack -l

`jstack` is the traditional JDK tool for printing thread stack traces in a JVM:

~~~bash
jstack -l 12345
~~~

The `-l` option requests additional information about ownable synchronizers and `java.util.concurrent` locks. Without this option, the thread dump focuses on monitors.

Oracle JDK now recommends `jcmd` for routine JVM diagnostics. `jstack` remains useful for learning, reading older documentation, and working in environments with existing workflows built around it. For core dumps, the corresponding tool is `jhsdb jstack`.

Do not take thread dumps in a tight loop. Capture a few snapshots spaced several seconds apart to see whether threads are making progress, changing lock owners, or stuck on the same stack.

## 17. Recognizing indicators in a thread dump

| Indicator | What may be happening | What to check |
|---|---|---|
| `WAITING (on object monitor)` | Waiting in `wait()` | Condition, notify, lock owner |
| `WAITING (parking)` | Waiting on a synchronizer/park | Queue, latch, future, condition |
| `TIMED_WAITING (sleeping)` | Sleeping | Is this an expected delay or a retry loop? |
| `TIMED_WAITING (on object monitor)` | `wait(timeout)` or similar mechanism | Timeout, condition after wakeup |
| `BLOCKED (on object monitor)` | Waiting to enter synchronized | Thread holding the monitor and lock hold duration |
| `RUNNABLE` with I/O stack | May be performing or waiting on native I/O | Socket, filesystem, external service |
| Multiple workers waiting on Future | Possible starvation or dependency chain | Executor size and task submission |

A `- waiting to lock` line usually indicates the monitor the thread needs. A `- locked` line indicates the monitor the thread holds at that frame. For `java.util.concurrent` synchronizers, use a dump with lock information to see additional owner/waiter details when provided by the JVM.

## 18. Distinguishing normal waiting, hangs, and deadlocks

A WAITING thread can be completely normal if another thread will wake it up when data or a condition becomes available.

Signs worth investigating:

- A thread waits longer than the expected SLA or timeout.
- No producer/worker remains that can satisfy the condition the consumer is waiting for.
- All pool workers are WAITING while tasks still sit in the queue.
- Multiple threads wait on the same monitor while the owner makes no progress.
- Stack traces across consecutive snapshots do not change.
- The application is unresponsive despite low CPU usage and no I/O progress.

A deadlock typically involves a lock dependency cycle: thread A holds lock 1 and waits for lock 2, while thread B holds lock 2 and waits for lock 1. The thread dump may print `Found one Java-level deadlock`.

Starvation or waiting on a lost signal can hang an application without a monitor deadlock. Therefore, a `No deadlocks found` message does not prove the entire application is healthy.

## 19. Taking multiple snapshots and comparing them

A single thread dump is a point-in-time snapshot. To diagnose issues, capture several dumps spaced briefly apart:

~~~bash
jcmd 12345 Thread.print -l > dump-1.txt
sleep 5
jcmd 12345 Thread.print -l > dump-2.txt
sleep 5
jcmd 12345 Thread.print -l > dump-3.txt
~~~

Compare thread names, states, stack frames, lock owners, and queue/task counts if your application exposes metrics. If stacks change, threads may be making slow progress. If all snapshots remain at the exact same wait point, trace the wakeup condition and the thread responsible for signaling it.

Do not upload thread dumps containing sensitive data to public places. Stack traces can expose internal class names, file paths, URLs, or environment details.

## 20. Checking for deadlocks with ThreadMXBean

The JDK Management API provides a way to detect deadlocks programmatically. The following example checks for both monitors and ownable synchronizers:

~~~java
import java.lang.management.ManagementFactory;
import java.lang.management.ThreadInfo;
import java.lang.management.ThreadMXBean;

public final class DeadlockCheck {
    private DeadlockCheck() {
    }

    public static void main(String[] args) {
        ThreadMXBean bean = ManagementFactory.getThreadMXBean();
        long[] ids = bean.findDeadlockedThreads();

        if (ids == null || ids.length == 0) {
            System.out.println("DEADLOCKS=0");
            return;
        }

        ThreadInfo[] infos = bean.getThreadInfo(ids, true, true);
        for (ThreadInfo info : infos) {
            System.out.println("DEADLOCK_THREAD=" + info.getThreadName());
            System.out.println(info);
        }
    }
}
~~~

`findDeadlockedThreads()` finds deadlock cycles involving monitors or ownable synchronizers. `findMonitorDeadlockedThreads()` checks only monitor deadlocks. This is a diagnostic check; it does not replace proper lock design or business timeout monitoring.

## 21. Virtual threads and waiting states

Virtual threads were introduced in Java 21. They are well suited for I/O-bound waiting workloads because the JVM can unmount a virtual thread from its carrier thread during many supported blocking operations.

A virtual thread in WAITING does not necessarily tie up a platform thread for the entire wait duration. This lets an application serve many blocking tasks with fewer platform threads.

However, virtual threads do not eliminate synchronization bugs: lost notifications, deadlocks, holding locks for too long, starvation from finite resources, or waiting on futures without deadlines can still occur.

Tools and thread dump formats may vary by JDK version. On newer JDKs, `jcmd Thread.print` displays platform threads and mounted virtual threads; `Thread.dump_to_file` can be used to write dumps to a file when fuller inspection is needed, depending on runtime support.

## 22. Java 17+ example: creating a controlled WAITING thread

The example below creates a thread named `demo-waiter`. This thread waits on a monitor until the main thread updates the condition and calls `notifyAll()`. The `--interrupt` flag tests the interruption cancellation path; `--hold` keeps the thread waiting for a few seconds so there is time to capture a thread dump.

File `WaitingThreadDemo.java`:

~~~java
import java.util.concurrent.TimeUnit;

public final class WaitingThreadDemo {
    private static final Object MONITOR = new Object();
    private static boolean released;

    private WaitingThreadDemo() {
    }

    public static void main(String[] args) throws InterruptedException {
        boolean holdForDump = args.length > 0 && "--hold".equals(args[0]);
        boolean interruptWaiter = args.length > 0 && "--interrupt".equals(args[0]);

        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                System.out.println("WAITER_READY");
                try {
                    while (!released) {
                        MONITOR.wait();
                    }
                    System.out.println("WAITER_RESUMED");
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    System.out.println("WAITER_INTERRUPTED");
                    System.out.println("INTERRUPT_RESTORED="
                            + Thread.currentThread().isInterrupted());
                }
            }
        }, "demo-waiter");

        waiter.start();

        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (waiter.getState() != Thread.State.WAITING
                && System.nanoTime() < deadline) {
            Thread.onSpinWait();
        }

        if (waiter.getState() != Thread.State.WAITING) {
            throw new IllegalStateException("Waiter did not enter WAITING state");
        }
        System.out.println("OBSERVED_STATE=" + waiter.getState());

        if (interruptWaiter) {
            waiter.interrupt();
        } else {
            if (holdForDump) {
                System.out.println("READY_FOR_THREAD_DUMP");
                Thread.sleep(5000);
            }

            synchronized (MONITOR) {
                released = true;
                MONITOR.notifyAll();
            }
        }

        waiter.join();
        System.out.println("MAIN_DONE");
    }
}
~~~

Compile with JDK 17 or later:

~~~bash
javac --release 17 -Xlint:all -Werror WaitingThreadDemo.java
~~~

Normal run:

~~~bash
java WaitingThreadDemo
~~~

Exact output:

~~~text
WAITER_READY
OBSERVED_STATE=WAITING
WAITER_RESUMED
MAIN_DONE
~~~

Interrupt path run:

~~~bash
java WaitingThreadDemo --interrupt
~~~

Exact output:

~~~text
WAITER_READY
OBSERVED_STATE=WAITING
WAITER_INTERRUPTED
INTERRUPT_RESTORED=true
MAIN_DONE
~~~

This program uses a very short spin loop solely so the exercise can deterministically observe the WAITING state. Do not poll `Thread.getState()` as a thread coordination mechanism in real applications; use a latch, condition, queue, or lock.

## 23. Capturing jstack and jcmd for the example

To hold the waiter in the WAITING state for a few seconds, run:

~~~bash
java WaitingThreadDemo --hold
~~~

In another terminal, find the PID:

~~~bash
jcmd -l
~~~

Then run:

~~~bash
jcmd 12345 Thread.print -l
jstack -l 12345
~~~

Replace the example PID with the PID of the `WaitingThreadDemo` process. In PowerShell, you can filter the PID automatically:

~~~powershell
$jvm = jcmd -l | Select-String 'WaitingThreadDemo' | Select-Object -First 1
$javaPid = ($jvm.ToString() -split '\s+')[0]
jcmd $javaPid Thread.print -l
jstack -l $javaPid
~~~

In the output, look for the `demo-waiter` thread. The key lines will look like:

~~~text
"demo-waiter" #35 ...
   java.lang.Thread.State: WAITING (on object monitor)
    at java.lang.Object.wait(...)
    at WaitingThreadDemo.lambda$main$0(WaitingThreadDemo.java:...)
~~~

After capturing the dump, the program wakes up the waiter and exits. In real applications, do not assume a single thread dump points to a single root cause; combine stack traces with lock state, metrics, and business logs.

## 24. Common mistakes when working with waiting threads

| Mistake | Consequence | Fix |
|---|---|---|
| Calling wait outside synchronized | IllegalMonitorStateException | Hold the right monitor when calling wait |
| Calling notify on a different object | Waiter is never woken up | Use the same object as the monitor |
| Using if instead of while | Proceeds even when condition is not met | Check the condition in a while loop |
| Notifying before updating state | Consumer may see stale state | Update and notify inside the same synchronized block |
| Catching InterruptedException and ignoring it | Cancellation signal is lost | Propagate or restore the interrupt |
| Holding another lock while waiting | Other threads cannot acquire the needed lock | Minimize synchronized scope, avoid nested locks |
| Using sleep to wait for another thread | Race conditions and flaky tests | Use a latch, condition, or join |
| Waiting on a Future in the same saturated pool | Thread starvation deadlock | Use async composition or a separate executor |
| Seeing WAITING and assuming deadlock | Misdiagnosis | Check wait condition, owner, and multiple snapshots |
| Taking only one thread dump | Misses state transitions | Compare multiple snapshots over time |

## 25. Diagnostic workflow for waiting threads in an application

When a request or task hangs, follow these steps in order:

1. Identify the JVM process and when the slowdown began.
2. Capture a thread dump using `jcmd Thread.print -l` or `jstack -l`.
3. Find relevant threads by name, request ID, or stack frame.
4. Note the WAITING/BLOCKED/TIMED_WAITING state.
5. Identify the waiting API: `Object.wait`, `join`, `park`, latch, queue, or `Future`.
6. Find the thread responsible for signaling or completing the task.
7. Check the lock owner, queue length, executor active count, and timeouts.
8. Capture additional snapshots after a few seconds to see if threads are progressing.
9. Check for deadlocks and starvation; do not look only for monitor cycles.
10. Write a reproduction test, fix the root cause, and add a regression test.

If you need to analyze events over time, Java Flight Recorder and JDK Mission Control can supplement thread dumps with thread samples, lock profiles, and runtime metrics. A thread dump is a snapshot; JFR helps observe behavior over a time window.

## 26. Code review checklist for waiting threads

- [ ] Every `Object.wait()` call is inside `synchronized` on the correct object.
- [ ] Wait conditions are checked inside a `while` loop.
- [ ] The producer updates state and calls notify under the same monitor.
- [ ] No unnecessary locks are held while waiting.
- [ ] Interrupts are propagated or restored properly.
- [ ] Waits have timeouts/deadlines when business logic requires time bounds.
- [ ] Thread pools cannot be saturated by tasks synchronously waiting on subtasks.
- [ ] High-level APIs like `BlockingQueue`, `CountDownLatch`, or `Condition` are considered.
- [ ] Threads are named for easy identification in dumps.
- [ ] There is a way to capture and read thread dumps in the runtime environment.
- [ ] Deadlocks, starvation, and lost signals are distinguished.
- [ ] Tests verify both normal wakeup and interrupt paths.

## References

- Oracle Java SE 26 — [Thread.State](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.State.html).
- Oracle Java SE 26 — [Object.wait(), notify() and notifyAll()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html).
- Oracle Java SE 26 — [Thread and Interruption](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html).
- Oracle JDK 26 — [The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html).
- Oracle JDK 26 — [Diagnostic Tools: jstack, Thread Dumps and Deadlock Detection](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html).
- Dev.java — [Concurrency](https://dev.java/learn/concurrency/).