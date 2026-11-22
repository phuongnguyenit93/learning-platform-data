# Thread State Transitions by `sleep()`, `join()`, and `wait()` in Java

## 1. Why understand state transitions?

When a Java application performs multiple tasks concurrently, there are times when a thread is **running or ready to run**, and times when it must **wait for a period of time**, **wait for another thread to finish**, or **wait for a condition on shared data**. Three common APIs for this are:

- `Thread.sleep(...)`: the **currently executing thread** pauses for the requested duration.
- `someThread.join(...)`: the **thread calling `join`** waits for **`someThread`** to terminate, optionally with a timeout.
- `lock.wait(...)`: the **thread holding the monitor of `lock`** temporarily releases that monitor and waits to be notified, optionally with a timeout.

All three can prevent a thread from continuing to run immediately, but they differ in **who waits, what is being waited on, whether monitors are released, and the condition to resume**. Distinguishing them helps avoid unnecessary data locking, confusion about the Thread lifecycle, application hangs, and missed-signal bugs.

This lesson covers **general Java** concurrency, focusing on the standard APIs of `java.lang.Thread` and `java.lang.Object`. Framework-specific use cases are outside the scope of this lesson.

## 2. Six states observed via `Thread.State`

The `Thread.getState()` API returns one of the six values below. This is a **point-in-time snapshot of the state**, not a transition history or a guarantee of scheduler execution order.

| `Thread.State` | Meaning in Java | Example |
| --- | --- | --- |
| `NEW` | The Thread object has been created but `start()` has not been called yet | `new Thread(task)` |
| `RUNNABLE` | The thread is running or ready to run at the JVM level | After `start()`, when not waiting in any other state |
| `BLOCKED` | Waiting to acquire an intrinsic monitor to enter `synchronized` (or re-acquire a monitor) | Another thread currently holds the required monitor |
| `WAITING` | Waiting indefinitely for an action from another thread | `Object.wait()`, `Thread.join()` without timeout |
| `TIMED_WAITING` | Waiting with a time limit | `Thread.sleep(500)`, `Thread.join(500)`, `Object.wait(500)` |
| `TERMINATED` | The `run()` method has finished, including termination due to an unhandled exception | After the worker completes |

There is no `SLEEPING` or `JOINED` state in the `Thread.State` enum. "Sleeping" via `sleep` is represented as `TIMED_WAITING`; "joining" is typically `WAITING` or `TIMED_WAITING` of the **thread calling `join`**, rather than a new state of the worker.

Conceptual diagram (illustrates common paths only, does not cover every possible transition):

```text
                  start()
     NEW -------------------------> RUNNABLE
                                      |
             sleep(duration)          | waiting for synchronized monitor
             join(timeout)            +---------------------> BLOCKED
             wait(timeout)            |                           |
                   |                  |       acquired monitor    |
                   v                  |<--------------------------+
              TIMED_WAITING <---------+
                   |        timeout expires / notified / interrupted
                   +------------------> RUNNABLE (when ready)
                                      |
             join() / wait()          |   without timeout
                   |                  |
                   v                  |
                WAITING --------------+
                  wait ends
                                      |
                                      | run() finishes
                                      v
                                  TERMINATED
```

The return path after `wait` **may have to go through `BLOCKED`** to re-acquire the monitor before continuing. Once a thread has terminated, `start()` cannot be called again on the same object. `RUNNABLE` does not necessarily mean the thread is occupying the CPU at the moment of observation; the actual state changes very rapidly.

## 3. `Thread.sleep()`: pausing the current thread for a duration

### 3.1. API and resumption conditions

`Thread.sleep(long millis)` and `Thread.sleep(long millis, int nanos)` are **static methods**. They affect the **currently executing calling thread**, not a specified Thread object. You should not write `worker.sleep(100)` to express the intent "make worker sleep": Java allows calling a static method through a reference variable syntactically, but the operation still happens on the **calling thread**, causing confusion. Write `Thread.sleep(100)` explicitly.

During sleep caused by `Thread.sleep(500)`, the observed state of the sleeping thread is typically `TIMED_WAITING`. When the wait duration completes, the thread becomes eligible to resume execution; **there is no guarantee it will run after exactly 500 ms**, because clock precision and CPU scheduling depend on the JVM and operating system.

`sleep` is not a tool for waiting until a business condition becomes true. After the duration elapses, the external condition may still be false. If you need to react to events or data changes, use proper coordination mechanisms (a monitor with `wait/notifyAll`, `BlockingQueue`, latch, condition, future, etc.).

### 3.2. `sleep` **does not release held monitors**

This is a key difference from `Object.wait()`. A thread inside `synchronized(lock)` still **owns the monitor of `lock`** if it calls `Thread.sleep` inside the block. Another thread attempting to enter `synchronized(lock)` may transition to `BLOCKED` until the monitor is released.

Complete example, create the file `SleepKeepsMonitorDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class SleepKeepsMonitorDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (lock) {
                entered.countDown();
                try {
                    Thread.sleep(150);
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }
                System.out.println("worker: vẫn giữ lock");
            }
        }, "sleep-worker");

        worker.start();
        entered.await();

        synchronized (lock) {
            System.out.println("main: đã lấy lock");
        }
        worker.join();
    }
}
```

Run with Java 17 or later:

```bash
javac SleepKeepsMonitorDemo.java
java SleepKeepsMonitorDemo
```

Output when the worker is not interrupted:

```text
worker: vẫn giữ lock
main: đã lấy lock
```

`entered.countDown()` is called while the worker is inside `synchronized(lock)`. `main` only proceeds after `entered.await()` and then attempts to acquire the same monitor. While `worker` sleeps, it **still holds the lock**, so `main` cannot print before the worker's line. If you sample `main`'s state right while it is waiting to acquire the monitor, you may see `BLOCKED`; `worker` during its sleep is typically `TIMED_WAITING`. Do not rely on `getState()` to assert that you will catch these two states at any arbitrary instant.

In practice, avoid sleeping for long periods while holding a shared monitor: doing so forces all other threads needing that monitor to wait, reducing throughput and increasing latency.

### 3.3. When interrupted

`Thread.sleep` declares `throws InterruptedException`. If the thread is interrupted before or during sleep, the call throws `InterruptedException`; when the exception is thrown via this mechanism, **the interrupt flag is cleared**. Code catching the exception typically propagates it or restores the interrupt flag with `Thread.currentThread().interrupt()` and exits in a controlled manner. Catching the exception and continuing an infinite loop can render cancellation requests ineffective.

## 4. `Thread.join()`: caller waits for another Thread to finish

### 4.1. Who transitions to a waiting state?

Given two threads: `main` and `worker`. When `main` calls `worker.join()`:

- **`main`** is the waiting thread: it typically enters `WAITING` if `join()` has no timeout, or `TIMED_WAITING` if `join(timeout)` is used.
- **`worker`** continues its own lifecycle. `worker` may be `RUNNABLE`, `BLOCKED`, `WAITING`, `TIMED_WAITING`, or already `TERMINATED` depending on when it is observed; **`join` does not cause `worker` to sleep or stop**.
- When `worker` terminates, `main` can proceed past `join()`. In the case of `join` with a timeout, `main` may also proceed because the timeout expired even if `worker` is still alive.

This is a common mistake: "`worker.join()` puts `worker` into `WAITING`" has the **wrong subject**. The one waiting is the thread calling `join`.

### 4.2. Deterministic completion order example

Create the file `JoinOrderDemo.java`:

```java
public class JoinOrderDemo {
    public static void main(String[] args) throws InterruptedException {
        Thread worker = new Thread(() -> {
            System.out.println("worker: hoàn thành");
        }, "worker");

        worker.start();
        worker.join();

        System.out.println("main: tiếp tục sau join");
    }
}
```

```bash
javac JoinOrderDemo.java
java JoinOrderDemo
```

Output:

```text
worker: hoàn thành
main: tiếp tục sau join
```

`start()` starts the worker, while `join()` makes `main` wait for the worker to terminate. Therefore, the order of the two lines is guaranteed by program structure; it does not depend on whether `main` or `worker` is scheduled on the CPU first. If `join()` is removed, the order of the two lines is no longer guaranteed.

### 4.3. `join(timeout)` can return before the worker finishes

`worker.join(200)` requests waiting for **at most approximately 200 ms** for `worker` to terminate. After the call returns normally, you must check `worker.isAlive()` if the business logic needs to know whether `worker` has actually finished:

```java
worker.join(200);
if (worker.isAlive()) {
    System.out.println("Worker chưa hoàn thành ở thời điểm kiểm tra");
}
```

This is an illustrative snippet placed in a context where `worker` is already defined and `InterruptedException` is handled. The message may or may not appear depending on execution timing. Do not treat `join(timeout)` returning as conclusive proof that `worker` is `TERMINATED`. Passing `millis = 0` in `join(0)` means **wait indefinitely**, not "do not wait".

`Thread.join()` can be interrupted while the caller is waiting. In that case, the **caller** receives `InterruptedException`; this by itself does not cancel or interrupt `worker`. If you want to request `worker` to stop, send a separate signal, such as `worker.interrupt()` with an appropriate cancellation contract.

### 4.4. Happens-before relationship

When a thread terminates, the actions it performed have a *happens-before* relationship with the actions of another thread that detects that termination via a successful `join()`. As a result, code after `worker.join()` can observe the writes made by the terminated worker under the guarantees of the Java Memory Model.

However, `join` is a mechanism for waiting on **thread termination**, not a mechanism for protecting a data structure while multiple threads are still modifying it concurrently. If other threads are still updating shared data, proper synchronization is still required.

## 5. `Object.wait()`: releasing a monitor and waiting for a condition

### 5.1. `wait` is a method on `Object`, not `Thread`

The common overloads are `lock.wait()`, `lock.wait(long timeout)`, and `lock.wait(long timeout, int nanos)`. Every Java object has an intrinsic monitor for use with `synchronized`, `wait`, `notify`, and `notifyAll`.

To call `lock.wait()`, **the current thread must hold the monitor of `lock` itself**, typically as:

```java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
}
```

This is an illustrative snippet with `lock` and `ready` already declared. If `lock.wait()` is called without owning the monitor of `lock`, Java throws `IllegalMonitorStateException`. Holding the monitor of a **different** object does not satisfy this requirement.

Unlike `sleep`, when a valid `lock.wait()` call is made, the waiting thread **releases the monitor of `lock` itself** and transitions to waiting. This allows another thread to enter `synchronized(lock)`, modify the guarded state, and send a notification.

### 5.2. How do `wait`, `notify`, and `notifyAll` coordinate?

Suppose a consumer needs to wait for a producer to set `ready = true`:

1. Consumer enters `synchronized(lock)` and checks the `ready` condition.
2. If not ready, consumer calls `lock.wait()`. It releases the `lock` monitor and waits (typically observed as `WAITING`).
3. Producer acquires the `lock` monitor, updates `ready = true`, and calls `lock.notifyAll()`.
4. `notifyAll()` **does not immediately release the monitor** held by the producer, nor does it guarantee the consumer runs immediately.
5. Producer exits `synchronized(lock)` to release the monitor; the consumer must **re-acquire the `lock` monitor** before `wait()` returns. While competing to re-acquire the monitor, the consumer may be observed as `BLOCKED`.
6. Consumer re-checks `ready` via the `while` loop and then processes the satisfied condition.

A waiting thread is not guaranteed to run immediately upon receiving a notification: it still has to contend for the monitor with other threads. `wait()` can return due to notification, timeout (for timed overloads), interruption, or **spurious wakeup**. Therefore, always check the condition in a **`while` loop**, never a single `if` statement.

### 5.3. Complete producer–consumer example without missed signals

Create the file `WaitNotifyDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class WaitNotifyDemo {
    public static void main(String[] args) throws InterruptedException {
        Object lock = new Object();
        boolean[] ready = {false};
        CountDownLatch consumerEntered = new CountDownLatch(1);

        Thread consumer = new Thread(() -> {
            synchronized (lock) {
                while (!ready[0]) {
                    System.out.println("consumer: đang chờ");
                    consumerEntered.countDown();
                    try {
                        lock.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("consumer: đã nhận điều kiện");
            }
        }, "consumer");

        consumer.start();
        consumerEntered.await();

        synchronized (lock) {
            ready[0] = true;
            lock.notifyAll();
            System.out.println("producer: đã phát tín hiệu");
        }

        consumer.join();
        System.out.println("main: hoàn thành");
    }
}
```

```bash
javac WaitNotifyDemo.java
java WaitNotifyDemo
```

Output when there is no interrupt:

```text
consumer: đang chờ
producer: đã phát tín hiệu
consumer: đã nhận điều kiện
main: hoàn thành
```

**Why is the output deterministic?** The consumer prints its message and calls `consumerEntered.countDown()` while holding `lock`. `main` waits on the latch before attempting to acquire `lock`. The consumer must reach `lock.wait()` and release the monitor before `main` can set `ready[0] = true`, so there is no gap between checking the condition and releasing the monitor where the notification could be lost. The producer prints while holding the monitor, so the consumer cannot print `"đã nhận điều kiện"` before it. Finally, `join()` places `"main: hoàn thành"` after the consumer terminates.

The `ready` variable is read/written **only inside `synchronized(lock)`**, establishing data visibility through monitor release/acquisition; using a single-element array here is only to provide a holder that can be referenced by the lambda, not a synchronization mechanism. In real applications, use a clearly named state object.

**Why still use `while`?** Java permits wakeups without a corresponding `notify/notifyAll`, or another thread might make the condition false again before the consumer acquires the monitor. The `while` loop forces re-checking the actual predicate that must hold.

### 5.4. `wait(timeout)` and wakeup outcomes

Inside `synchronized(lock)`, `lock.wait(500)` sets a wait timeout. The thread is typically `TIMED_WAITING` while waiting, but **returning does not prove the condition is true**. You must check the condition again. `wait(0)` means wait indefinitely.

Similarly, `notify()` typically wakes up **one** thread waiting on that monitor, without choosing in any order you might expect. `notifyAll()` wakes up all threads waiting on that monitor; they then compete to re-acquire the monitor and re-check their conditions. When multiple condition types share one monitor, `notifyAll()` generally reduces the risk of waking the wrong thread that cannot make progress, though it may wake more threads and increase contention. Choose the strategy that fits the actual invariants.

### 5.5. `wait` only releases the monitor being waited on

If a thread holds both `lockA` and `lockB`, and then calls `lockA.wait()`, it releases the `lockA` monitor but **keeps holding `lockB`**. Calling `wait` inside nested locks can easily cause deadlock if the producer needs `lockB` to establish the wakeup condition. `wait` also does not automatically release other lock types such as `ReentrantLock`. When using `ReentrantLock`, use the corresponding `Condition.await/signal` instead of mixing with `Object.wait/notify` on an unrelated object.

## 6. Direct comparison of the three APIs

| Question | `Thread.sleep(100)` | `worker.join()` | `lock.wait()` |
| --- | --- | --- | --- |
| Where is the API defined? | Static method on `Thread` | Instance method on `Thread` | Instance method on `Object` |
| Who waits? | The current thread | The thread calling `join` | The thread holding `lock`'s monitor and calling `wait` |
| What is it waiting for? | The requested duration | A target thread to terminate; or timeout | Notification/interrupt/spurious wakeup; or timeout |
| Typical observed state | `TIMED_WAITING` | `WAITING` or `TIMED_WAITING` | `WAITING` or `TIMED_WAITING` |
| Must own a monitor? | No | No | Yes, must hold the monitor of the object on which `wait` is called |
| Releases held monitors? | No | Does not release monitors held by the caller | Yes, releases the monitor of the object on which `wait` is called |
| Must check condition after returning? | If business logic depends on a condition: yes | With timeout: check `isAlive()` | Yes, use `while` for the guarded condition |
| When caller is interrupted while waiting? | `InterruptedException` | `InterruptedException` | `InterruptedException` |
| Primary purpose | Time delay, simulating waits in learning exercises | Coordinating thread lifecycle termination | Coordinating conditions between threads via a monitor |

**Specifically for `join`:** the `worker` object is the **target being waited on**, not "the thread put into WAITING". The waiting state belongs to the caller. **Specifically for `wait`:** the thread releases the waited object's monitor, but by the time `wait` returns, the thread has re-acquired that monitor. **Specifically for `sleep`:** a thread can sleep inside `synchronized` while still holding the monitor.

## 7. Being interrupted during `sleep`, `join`, or `wait`

All three APIs can throw `InterruptedException` when the thread executing the call is interrupted. Interruption is a **cooperative signal**: it is not a mechanism that forcibly kills a JVM thread instantaneously. A waiting call may throw the exception and typically clears the interrupt status before transferring control to `catch`.

Create the file `SleepInterruptDemo.java` to clearly see the effect on a **sleeping thread**:

```java
import java.util.concurrent.CountDownLatch;

public class SleepInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch ready = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                Thread.sleep(10_000);
            } catch (InterruptedException e) {
                System.out.println("catch: interrupted=" +
                        Thread.currentThread().isInterrupted());
                Thread.currentThread().interrupt();
                System.out.println("restored: interrupted=" +
                        Thread.currentThread().isInterrupted());
            }
        }, "worker");

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();
        System.out.println("main: worker đã kết thúc");
    }
}
```

```bash
javac SleepInterruptDemo.java
java SleepInterruptDemo
```

Output:

```text
catch: interrupted=false
restored: interrupted=true
main: worker đã kết thúc
```

Even if `main` interrupts `worker` before `worker` actually enters `sleep`, `sleep` still detects the interrupt and throws the exception; therefore the example does not need to rely on `main` "timing 10 seconds". `isInterrupted()` inside `catch` is `false` because the flag was cleared when `InterruptedException` was thrown. The code restores the flag so the calling layer can recognize the interrupt request.

For `join`, if `main` is interrupted while waiting on `worker.join()`, **`main`** is the thread that receives `InterruptedException`; `worker` is not automatically interrupted. For `wait`, the thread waiting on the monitor receives `InterruptedException`; before throwing the exception, Java must complete re-acquiring the monitor according to the `wait` contract.

Do not swallow `InterruptedException` and keep waiting indefinitely if the feature needs to support cancellation. If you cannot declare `throws InterruptedException`, the common pattern is to restore the interrupt flag and exit the task or propagate cancellation state to the coordinating layer. Also do not call `Thread.stop()` to resolve a waiting thread; it is a deprecated and unsafe API.

## 8. Which state appears after waking up?

You cannot mechanically apply a rule like "after `wait`, it is immediately `RUNNABLE`":

- `sleep`: when the duration expires or it is interrupted, the thread can become ready to run again; any monitors it holds remain held until it exits the `synchronized` block.
- `join`: when the worker terminates or the timeout expires, the caller is allowed to proceed; the caller still must be scheduled on the CPU.
- `wait`: after `notify/notifyAll`, timeout expiration, spurious wakeup, or interrupt, the thread still has to **re-acquire the monitor of the `wait` target object**. If the monitor is held by someone else, it may be observed in `BLOCKED` before resuming execution.
- If never notified, without a timeout, never interrupted, and without a spurious wakeup, an untimed `wait()` can keep waiting forever. This is why programs must guarantee a clear path to update the condition and send a notification.

`Thread.getState()` is a diagnostic tool. For example, `System.out.println(worker.getState())` can help observe state, but the result is a snapshot and may change immediately afterward. **Do not use a polling loop checking `getState() == WAITING` as a substitute for a proper coordination protocol**. When you need to verify ordering, use a latch, monitor, or `Future` as shown in the examples rather than depending on CPU scheduling.

## 9. Common mistakes and their causes

### 9.1. Confusing which thread waits when calling `join`

**Misconception:** "Calling `worker.join()` puts `worker` to sleep."

**Truth:** the caller of `worker.join()` waits for `worker` to finish; `worker` continues running normally. If `worker` in turn waits on the caller via another mechanism, a wait cycle (deadlock) can occur. Sketch who waits on whom before adding `join` calls.

### 9.2. Sleeping while holding a monitor to wait for another thread to change data

```java
synchronized (lock) {
    while (!ready) {
        Thread.sleep(100);
    }
}
```

The snippet above has a design flaw: if the producer thread also needs `synchronized(lock)` to change `ready`, the consumer keeps holding the lock across its `sleep` and check iterations, so the producer can never enter to make the condition true. **Fix it by using `lock.wait()` inside a `while` loop** to release the monitor while waiting, or use an appropriate high-level synchronization construct.

### 9.3. Calling `wait()` outside `synchronized`

```java
lock.wait(); // IllegalMonitorStateException if the caller does not hold the lock monitor
```

It must be called inside `synchronized(lock)` (or when actually owning that monitor). Declaring the `lock` variable as `final` does not make a thread own the monitor.

### 9.4. Using `if` instead of `while` to wait for a condition

```java
synchronized (lock) {
    if (!ready) {
        lock.wait();
    }
    useReadyData();
}
```

This snippet is risky. `wait` can return while the condition is still false; replace `if` with `while` and keep both the condition check and shared data inside the guarded region. `useReadyData()` represents application-defined work.

### 9.5. Calling `notify` too early or not holding the same monitor

If the producer calls `notifyAll` on a different object than the one the consumer is waiting on, the consumer is not woken up. If the condition is not stored in data and the signal is sent before the consumer starts waiting, the notification can be lost. The protocol of "check condition + `wait`" under the **same monitor**, and producer "update condition + `notifyAll`" under the **same monitor**, prevents this gap.

### 9.6. Forgetting that a timeout does not mean completion

`worker.join(100)` can return even though `worker` has not terminated. `lock.wait(100)` can return even though the producer has not signaled. `Thread.sleep(100)` only makes the thread wait for a duration; it does not guarantee a specific event has occurred. After a timeout, check the predicate you actually care about rather than assuming the condition is true.

### 9.7. Ignoring lifecycle and interruption handling

Failing to handle `InterruptedException` can prevent clean task cancellation or cause unbounded waiting. With `join` on a thread that never terminates, the caller can block forever. With `wait`, if no remaining thread can update the condition and notify, there is a risk of a business-logic hang. Design appropriate exit paths, timeouts, and cleanup.

## 10. Which API should you use in practice?

**`sleep`** is appropriate when the problem genuinely requires a time delay or simulating a wait in a learning environment. Do not use it as a "rough synchronization" mechanism between threads.

**`join`** is appropriate when a managing thread needs to be certain another thread has terminated, such as shutting down a worker before the program exits. If tasks are managed by an `ExecutorService` and you need a result or exception, `Future.get()` usually expresses intent better.

**`wait/notifyAll`** is suited for understanding the primitive monitor mechanism and when you genuinely need to manage a condition guarded by `synchronized` yourself. In real application code, constructs like `BlockingQueue`, `CountDownLatch`, `Semaphore`, `Condition`, or `CompletableFuture` usually express intent more clearly and reduce protocol bugs. They have their own waiting mechanisms; do not cross-call `Object.wait` on an arbitrary object expecting to receive signals from those constructs.

With **virtual threads** (Java 21+), `sleep` and `join` still retain their respective waiting semantics, and `Thread.State` values still represent the Java thread's state. The JVM can unmount a virtual thread from its carrier in many waiting scenarios to save OS threads; this **does not change monitor rules**: `sleep` does not release monitors, `wait` must hold and then release the object's monitor, and `notifyAll` does not release the monitor immediately. In Java 21, blocking operations inside a `synchronized` block can cause carrier pinning; newer Java versions include improvements, though you should measure on your actual JDK and libraries. Do not use virtual threads as a substitute for data synchronization rules.

## 11. Self-check

**Question 1.** `main` calls `Thread.sleep(300)` while inside `synchronized(lock)`, and another worker tries to enter `synchronized(lock)`. What states can the two threads be in?

**Answer:** `main` is typically `TIMED_WAITING` due to `sleep` while still holding the `lock` monitor. The worker can be `BLOCKED` waiting for the monitor. Observed states are snapshots and depend on timing.

**Question 2.** `main` calls `worker.join()` while `worker` is running. Which thread is waiting and what happens when `worker` finishes?

**Answer:** `main` is the caller so it is typically `WAITING`; `worker` continues its work. When `worker` terminates, `main` can continue past `join()`.

**Question 3.** Consumer calls `lock.wait()` inside `synchronized(lock)`. Why can the producer modify the data and call `notifyAll()` on the same lock?

**Answer:** `wait` releases the `lock` monitor, giving the producer a chance to acquire it. The producer updates the data and sends the signal; the consumer must re-acquire the monitor before returning from `wait`, then re-check the condition with `while`.

**Question 4.** `lock.wait(100)` returns normally. Can you be sure the producer sent a notification and the condition is true?

**Answer:** No. It could have been a timeout, a notification, or a spurious wakeup; you must re-check the condition.

**Question 5.** `worker.join(100)` returns; is `worker` guaranteed to be `TERMINATED`?

**Answer:** Not yet. `join(timeout)` may have timed out. Check `worker.isAlive()` to know whether `worker` is still alive at the time of checking.

**Question 6.** Why does `Thread.sleep` not prevent missed notifications like the `while (!ready) lock.wait()` pattern does?

**Answer:** `sleep` does not atomically tie checking a condition to releasing a monitor, nor is it woken by `notify` as part of the monitor protocol. If sleeping inside `synchronized`, the thread keeps holding the monitor, preventing the producer from updating the condition.

## 12. Conclusion

All three calls can pause a thread, but they serve **three different needs**:

- `sleep(duration)`: **the current thread waits for time**, typically `TIMED_WAITING`, without releasing held monitors.
- `other.join()`: **the calling thread waits for `other` to terminate**, typically `WAITING` or `TIMED_WAITING`, without putting `other` into a waiting state.
- `lock.wait()`: **the thread owning `lock`'s monitor releases that monitor and waits to be notified of a condition**, typically `WAITING`; after waking up, it must still re-acquire the monitor and re-check the condition.

Understanding **who waits, what is waited on, which monitor is released, and what condition allows continuation** is the foundation for accurately reading the Thread lifecycle and designing safe concurrent programs in Java.
