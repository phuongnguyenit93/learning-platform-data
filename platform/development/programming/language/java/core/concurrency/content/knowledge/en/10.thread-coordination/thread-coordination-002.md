# Condition Waiting in Java: Why Use `while` Instead of `if`?

## 1. Objectives and Context

In **thread coordination**, a thread often needs to wait until shared state allows it to proceed: a consumer waits for a queue to have an element, a producer waits for a buffer to have space, a worker waits for a resource to be allocated, or multiple threads wait for a `ready` flag to be set. Java provides `Object.wait()` and `Condition.await()` to wait without spinning and continuously burning CPU. However, calling the right API is not enough: **a thread being woken up does not mean the condition it was waiting for has become true or is still true**.

The core rule of this lesson:

~~~java
// Structurally correct pattern:
synchronized (lock) {
    while (!conditionIsTrue()) {
        lock.wait();
    }
    // Perform the condition-dependent operation while still holding the lock.
}
~~~

In this illustrative snippet, `lock` and `conditionIsTrue()` are declared in the appropriate scope; the caller must handle/declare `InterruptedException`. **Never use `if` instead of `while`** when the condition must be guaranteed after waking up.

After this lesson, you will be able to:
- Distinguish the **business condition (predicate)** from the **wake-up signal (notification)**.
- Accurately explain the reasons why `wait()/await()` can return even though the predicate is still false: **spurious wakeup**, contention among waiters, and the condition changing before the thread reacquires the lock.
- Understand why **checking the predicate and calling wait must be inside the same synchronization protocol**, otherwise notifications can be lost.
- Recognize that `wait()` releases the monitor, `notify()/notifyAll()` does not immediately transfer the lock, and the waiter must reacquire the monitor before checking the condition.
- Use `while` with `Object.wait()`, `Condition.await()`, timeouts, interruption, and shutdown state.
- Run Java 17+ programs demonstrating why `if` is broken even when the code uses `synchronized`.

**Scope:** general **Java** concurrency mechanisms, without using Spring-specific annotations/APIs or asynchronous configurations, since Spring has its own chapter.

## 2. Two Different Facts: "Notified" vs. "Condition Met"

Suppose the queue is initially empty. A consumer may only take an element when:

~~~text
predicate notEmpty := queue.size() > 0
~~~

A producer can add an element and then call `notifyAll()`. But these are two distinct actions:
1. The producer **changes the state**: the queue now has data.
2. The producer **sends a signal**: waiting threads are permitted to attempt to wake up and contend for the lock.

Do not conflate them. A notification does not carry an element with it, does not grant a "permit to take one item," and **does not reserve a spot** for a specific consumer. Before the consumer wakes up and acquires the lock, another consumer may have already taken the element. Therefore, the statement "I was just notified" does not prove `!queue.isEmpty()`.

A simple scenario:

~~~text
Queue has 0 elements.
C1 is waiting because the queue is empty.
C2 is also waiting because the queue is empty.

Producer adds exactly 1 element X and calls notifyAll().
  |
  +-- C1 acquires the lock first, takes X, queue becomes empty again.
  |
  +-- C2 acquires the lock later.
        If using if: skips the stale check and calls remove -> error.
        If using while: rechecks, queue is still empty -> keeps waiting.
~~~

The **predicate** answers "am I allowed to proceed?", whereas the **notification** answers "an event has occurred that may have changed the condition, go recheck it." Correct code always relies on the **predicate read under the proper lock**, not on the arrival of a notification.

## 3. How Object.wait() and Monitors Work

### 3.1. The same monitor must protect both the predicate and the state

Consumer pattern:

~~~java
synchronized (monitor) {
    while (queue.isEmpty()) {
        monitor.wait();
    }
    return queue.removeFirst();
}
~~~

Producer pattern under the same protocol:

~~~java
synchronized (monitor) {
    queue.addLast(item);
    monitor.notifyAll();
}
~~~

These are illustrative snippets inside valid methods, assuming `monitor`, `queue`, and `item` already exist; the consumer side declares or handles `InterruptedException`. All paths that modify or read `queue` in relation to the predicate must use the **same monitor**.

Why:
- The consumer acquires the monitor to check the queue.
- If empty, `monitor.wait()` places the thread into the wait set and **releases that monitor** according to the `wait()` protocol. The producer cannot slip in between the check and the wait step in a way that loses the signal when both adhere to the monitor.
- The producer acquires the monitor, adds the element, calls `notifyAll()` while holding the monitor, and then releases the monitor.
- The woken consumer **must reacquire the monitor** before `wait()` returns; only then does it recheck `queue.isEmpty()`.
- If the condition is still false, the `while` loop calls `wait()` again. If true, `removeFirst()` executes **under the same lock** as the final check.

A thread may hold multiple locks, but `monitor.wait()` only automatically releases **the monitor of the `monitor` object**. It does not release other `synchronized` monitors or other `ReentrantLock` instances that the thread is holding. Holding another lock while waiting can cause deadlock or prevent the signaling thread from making progress.

### 3.2. wait() vs. sleep()

| API | Waiting Behavior | Lock Release Behavior |
| --- | --- | --- |
| `monitor.wait()` | Waits for notification, interruption, or spurious wakeup | **Releases only the monitor on which wait is called**, reacquires it before returning |
| `monitor.wait(millis)` | Adds timeout expiration | Releases and reacquires that same monitor |
| `Thread.sleep(millis)` | Sleeps for a duration | **Does not release any monitor** just because of sleeping |
| `condition.await()` | Waits for signal/interruption/spurious wakeup of `Condition` | Releases and reacquires **the lock associated with the Condition** |
| `BlockingQueue.take()` | Waits for the queue to have an element, unless interrupted | Primitive handles internal coordination itself; no manual `wait()` needed |

`Thread.sleep(100)` inside `synchronized` is not a way to wait for a producer to change state: the sleeping thread still holds the monitor, preventing the producer that needs that monitor from entering to update it. Adding `sleep` also does not establish the necessary happens-before relationship to fix a race.

### 3.3. The monitor must be held when calling wait/notify

Calling `wait()`, `notify()`, and `notifyAll()` on an object requires the current thread to hold **the monitor of that exact object**. Otherwise, Java throws `IllegalMonitorStateException`.

~~~java
Object lock = new Object();

// Protocol error: lock.wait(); // If not inside synchronized(lock).

synchronized (lock) {
    // lock.wait(); // Valid ownership, but will block waiting.
    lock.notifyAll(); // Valid ownership.
}
~~~

In the examples in this lesson, the thread calling wait must have an exit path—never call `wait()` indefinitely in `main` without another thread sending a signal.

## 4. Three Reasons You Must Recheck the Condition with while

### 4.1. Spurious wakeup (waking up without an expected signal)

The Javadoc for `Object.wait()` and `Condition.await()` explicitly permits a wait to return even without a corresponding notification or completion event. This is called a **spurious wakeup**.

Broken example:

~~~java
synchronized (monitor) {
    if (!ready) {
        monitor.wait();
    }
    useResource(); // No guarantee that ready == true.
}
~~~

On a spurious wakeup, `wait()` returns while `ready` is still false, and code using `if` does not go back to recheck. With `while`:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    useResource(); // Predicate was verified true while holding the monitor.
}
~~~

Java does not promise that spurious wakeups will occur on every run; do not use luck-based benchmarks or `Thread.sleep` to "prove" it. However, the code **must remain correct even when it happens**.

### 4.2. Multiple waiters can wake up together when there is only one resource

`notifyAll()` causes multiple waiters to attempt to wake up; each waiter must contend to reacquire the monitor. If the producer added one item, **only one consumer can take that item**. Another consumer waking up afterward may see an empty queue.

This problem occurs **even without spurious wakeups**. Therefore, the explanation that "`while` is only to guard against the JVM randomly waking threads up" is **incomplete**.

### 4.3. The condition changes after the signal but before the waiter reacquires the lock

Even when a producer has just called `notify()` because the condition became true:
- The producer still holds the monitor until it exits the `synchronized` block.
- The notified waiter cannot execute the code after `wait()` until it reacquires the monitor.
- A third thread may be scheduled to acquire the monitor before the waiter and modify the state.
- By the time the waiter holds the monitor again, the predicate may already be false.

This is analogous to **Mesa-style condition variables**: a signal does not "hand off" the condition; the waiter **rechecks it itself** after gaining the right to run. Never assume that `notifyAll()` immediately transitions a thread into executing business logic.

## 5. Runnable Example 1 — if Proceeds Incorrectly After a Valid Notification

Problem: a worker may only proceed if `ready=true`. `main` intentionally calls `notifyAll()` **without changing `ready`**. A program using `if` will proceed while the condition is still false. We use a latch to control the wait point rather than relying on `sleep`.

Save the file **`IfWaitBugDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class IfWaitBugDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch enteringWait = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (MONITOR) {
                if (!ready) {
                    enteringWait.countDown();
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                System.out.println("proceeded-when-ready=" + ready);
            }
        }, "if-waiter");

        worker.start();
        enteringWait.await();

        synchronized (MONITOR) {
            // A signal not tied to the predicate becoming true.
            MONITOR.notifyAll();
        }

        worker.join();
    }
}
~~~

Run on Java 17+:

~~~bash
javac IfWaitBugDemo.java
java IfWaitBugDemo
~~~

Stdout on an uninterrupted execution path:

~~~text
proceeded-when-ready=false
~~~

**Why is the outcome deterministic in this experiment?**
- The worker calls `enteringWait.countDown()` **while holding `MONITOR`**, right before `wait()`.
- `main` waits on the latch, then attempts to enter `synchronized(MONITOR)`. `main` **cannot enter** until the worker actually calls `wait()` and releases `MONITOR` (if the worker is still holding it).
- `main` calls `notifyAll()` while `ready` is still false and then releases the monitor.
- The worker reacquires the monitor, returns from `wait()`, and **does not recheck** because it has already exited the `if` branch. It prints false.

Even a genuine notification may not mean the desired condition has become true. This example exposes the `if` bug without having to wait for a random spurious wakeup.

**Do not use this `if` code in production.** If the worker depends on a real resource, the post-wakeup action may read nonexistent data or violate business invariants.

## 6. Runnable Example 2 — while Ignores a Premature Wakeup

Fix the same scenario with `while`. The first notification does not change `ready`; the worker rechecks and continues waiting. `main` waits for confirmation that the worker has **rechecked false** before setting `ready=true` and notifying a second time.

Create the file **`WhileWaitDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;

public class WhileWaitDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstWait = new CountDownLatch(1);
        CountDownLatch checkedFalseAgain = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            int falseChecks = 0;

            synchronized (MONITOR) {
                while (!ready) {
                    falseChecks++;

                    if (falseChecks == 1) {
                        firstWait.countDown();
                    }
                    if (falseChecks == 2) {
                        checkedFalseAgain.countDown();
                    }

                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                System.out.println(
                        "rechecked-false=" + (falseChecks >= 2));
                System.out.println("proceeded-when-ready=" + ready);
            }
        }, "while-waiter");

        worker.start();
        firstWait.await();

        synchronized (MONITOR) {
            MONITOR.notifyAll(); // Wakeup while ready is still false.
        }

        checkedFalseAgain.await();

        synchronized (MONITOR) {
            ready = true;
            MONITOR.notifyAll();
        }

        worker.join();
    }
}
~~~

Run:

~~~bash
javac WhileWaitDemo.java
java WhileWaitDemo
~~~

Stdout on normal completion:

~~~text
rechecked-false=true
proceeded-when-ready=true
~~~

**Reasoning:**
1. The worker first sees `ready=false` and signals `firstWait`.
2. `main` can only acquire `MONITOR` after the worker has entered `wait()` and released the monitor, so the first notify wakes up the waiting worker; `ready` is still false.
3. The worker reacquires the monitor, enters the top of the `while` loop, and increments `falseChecks`; the `checkedFalseAgain` latch confirms it has **observed false again**.
4. `main` sets `ready=true` under the monitor and notifies. If the worker has not entered `wait()` again yet, `main` must wait for the lock until the worker calls `wait()`; if the worker is already waiting, `main` can send the signal. Both cases are safe.
5. The worker only prints `proceeded-when-ready=true` after it has reacquired the monitor and the condition is true.

An extra spurious wakeup does not break the proof either: there may be more false checks, but ultimately the program only exits the `while` loop when the state genuinely permits it. The demo intentionally does not print the **exact count** of wakeups because the JDK does not guarantee that number.

**Core difference:** `if` checks once before waiting; `while` checks **before every wait and after every wakeup**.

## 7. Runnable Example 3 — Two Consumers Notified, Only One Item

If two waiters are waiting on an empty queue, and the producer adds one element and calls `notifyAll()`, the `if` pattern can cause the second waiter to attempt to remove an element that no longer exists.

This example coordinates the threads so that **both consumers enter the wait set before the producer adds the item**. We catch the error from `removeFirst()` and count the outcomes rather than depending on which thread wins.

Create the file **`TwoConsumersIfDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.NoSuchElementException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoConsumersIfDemo {
    private static final Object MONITOR = new Object();
    private static final ArrayDeque<String> queue = new ArrayDeque<>();

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothWaiting = new CountDownLatch(2);
        AtomicInteger claimed = new AtomicInteger();
        AtomicInteger failures = new AtomicInteger();

        Runnable consume = () -> {
            synchronized (MONITOR) {
                if (queue.isEmpty()) {
                    bothWaiting.countDown();
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                try {
                    queue.removeFirst();
                    claimed.incrementAndGet();
                } catch (NoSuchElementException e) {
                    failures.incrementAndGet();
                }
            }
        };

        Thread a = new Thread(consume, "consumer-a");
        Thread b = new Thread(consume, "consumer-b");
        a.start();
        b.start();

        bothWaiting.await();
        synchronized (MONITOR) {
            queue.addLast("X");
            MONITOR.notifyAll();
        }

        a.join();
        b.join();

        System.out.println("claimed=" + claimed.get());
        System.out.println("empty-remove-failures=" + failures.get());
    }
}
~~~

Run:

~~~bash
javac TwoConsumersIfDemo.java
java TwoConsumersIfDemo
~~~

Stdout when uninterrupted:

~~~text
claimed=1
empty-remove-failures=1
~~~

Why is this failure reproducible?
- `bothWaiting` only reaches 0 after both threads **have entered `synchronized` and are about to call `wait()`**. `main` can only add the item once it acquires the monitor, meaning the waiters have already released the monitor to wait.
- `notifyAll()` wakes both up. The first to acquire the lock takes item X; when the second acquires the lock later, the queue is already empty.
- Because `if` was used, the second consumer does not recheck the queue, so `removeFirst()` throws `NoSuchElementException`, which is caught and counted.
- `AtomicInteger` is only used to aggregate the demo results; it **does not fix the condition-waiting bug**.

Having a **lock protecting the queue is necessary but not sufficient** if the code uses `if` after wait: the consuming action must be performed **only when the predicate is true during the final lock acquisition**.

## 8. Fixing the Multi-Waiter Scenario: while Combined with a closed Condition

If you change `if` to `while(queue.isEmpty()) wait()` in the example above, the second consumer will **validly wait** after the sole item is taken. However, if the producer never adds another element, that thread could wait forever. This is not a bug in `while`; it is an undesigned **liveness/shutdown** requirement.

A sound protocol has two conditions:
- When `queue` has an item: take the item.
- When `queue` is empty **and closed**: finish waiting.
- When `queue` is empty **and not closed**: keep waiting.

Create the file **`TwoConsumersWhileDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;

public class TwoConsumersWhileDemo {
    private static final Object MONITOR = new Object();
    private static final ArrayDeque<String> queue = new ArrayDeque<>();
    private static boolean closed;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch bothWaiting = new CountDownLatch(2);
        AtomicInteger claimed = new AtomicInteger();
        AtomicInteger stopped = new AtomicInteger();

        Runnable consume = () -> {
            synchronized (MONITOR) {
                while (queue.isEmpty() && !closed) {
                    bothWaiting.countDown();
                    try {
                        MONITOR.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }

                if (queue.isEmpty()) {
                    stopped.incrementAndGet();
                    return;
                }

                queue.removeFirst();
                claimed.incrementAndGet();
            }
        };

        Thread a = new Thread(consume, "consumer-a");
        Thread b = new Thread(consume, "consumer-b");
        a.start();
        b.start();

        bothWaiting.await();

        synchronized (MONITOR) {
            queue.addLast("X");
            closed = true;
            MONITOR.notifyAll();
        }

        a.join();
        b.join();

        System.out.println("claimed=" + claimed.get());
        System.out.println("stopped=" + stopped.get());
        System.out.println("remaining=" + queue.size());
    }
}
~~~

Run:

~~~bash
javac TwoConsumersWhileDemo.java
java TwoConsumersWhileDemo
~~~

Stdout:

~~~text
claimed=1
stopped=1
remaining=0
~~~

Why is this version safe?
1. Both consumers wait while `queue.isEmpty() && !closed`.
2. `main` updates **both `queue` and `closed` under the same monitor** and then calls `notifyAll()`, avoiding inconsistent intermediate states.
3. One consumer takes X; the other consumer sees an empty queue but `closed=true`, so it exits instead of waiting forever or calling `removeFirst()` erroneously.
4. Both the check and the removal happen under the same monitor. Nobody can modify the queue between the two steps.
5. The `claimed/stopped` fields only serve the demo output; `main` reads them after `join()`, once the workers have finished.

**Note for real applications:** `closed` here means **no new elements will be accepted** while consumers may still drain existing items. If business requirements demand discarding all queued items immediately upon closing, different semantics must be defined. Do not blindly apply one shutdown rule to every kind of queue.

## 9. Lost Notification: Why Check–Wait Must Share the Same Monitor

A lost notification bug is different from the `if` bug in the previous sections. For example, suppose a thread checks a flag outside the monitor before waiting:

~~~java
// WRONG: ready is checked outside the monitor.
if (!ready) {
    synchronized (monitor) {
        monitor.wait();
    }
}
~~~

Another thread can set `ready=true` and call notify in **the gap between** the two steps. At that moment there is no waiter, so the notification is lost; the first thread then enters `wait()` and may wait forever. Making `ready` `volatile` may improve visibility for `ready` alone, but it **does not combine** the check and the wait into an atomic protocol.

The consistent pattern is:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
}
~~~

The path that modifies `ready` must also hold `monitor`:

~~~java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
~~~

This is how missed notifications are avoided **without storing signal history**. If the signal arrives first, the waiter sees the predicate is already true and does not wait. If the signal arrives after the waiter starts waiting, it wakes the waiter up to recheck.

**Protocol rule:** the predicate must be protected shared state; a notification is a hint to "come recheck" under the corresponding monitor/condition. Do not read the predicate under one lock while waiting under a different lock, unless another coordination design has been proven correct.

## 10. Inside Every while Loop, Maintain the Invariant at the Point of Lock Release

`while` does not automatically fix all concurrency bugs. You must ensure **the object's state is consistent before `wait()` releases the lock**.

For example, suppose a buffer has `size` and actual elements in a queue. If the code decrements `size` and then calls `wait()` before removing the actual element, another thread entering the monitor can observe `size != queue.size()`. It will act on a corrupt predicate and may corrupt data.

Principled wrong pattern:

~~~java
synchronized (monitor) {
    available--;
    monitor.wait(); // Releases the lock while the invariant is not yet restored.
    reserved++;
}
~~~

Suppose the invariant is `available + reserved == total`. After decrementing `available` but before incrementing `reserved`, the invariant is broken. If the thread is interrupted or an exception occurs, it may never complete the second step; `synchronized` automatically releasing the lock does not roll back changes already made.

A good pattern:

~~~java
synchronized (monitor) {
    while (available <= 0) {
        monitor.wait();  // State unchanged, invariant remains valid.
    }

    available--;
    reserved++;          // Complete update within the same critical section.
    monitor.notifyAll(); // If predicates of another waiter group might change.
}
~~~

The snippets above belong inside a method that handles `InterruptedException` and has its state appropriately declared. The path that returns/releases resources must use the same monitor and signal after the state changes.

**Invariant** states whether the object is valid; **predicate** states whether a waiting thread can act yet. An empty buffer can be completely valid under the invariant `0 <= size <= capacity` while not satisfying the predicate `notEmpty`. After wakeup, `while` rechecks the predicate; every update path under the monitor must preserve the invariant.

## 11. Runnable Bounded Buffer with Multiple Producers/Consumers

This is a hand-rolled abstraction for learning thread coordination. In production code, the standard library's `BlockingQueue` is usually the better choice; however, writing it ourselves shows why **two `while` loops** are needed.

Create the file **`BoundedBufferWhileDemo.java`**:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class BoundedBufferWhileDemo {
    private static final class Buffer<T> {
        private final ArrayDeque<T> queue = new ArrayDeque<>();
        private final int capacity;

        Buffer(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        synchronized void put(T value) throws InterruptedException {
            while (queue.size() == capacity) {
                wait();
            }
            queue.addLast(value);
            notifyAll();
        }

        synchronized T take() throws InterruptedException {
            while (queue.isEmpty()) {
                wait();
            }
            T value = queue.removeFirst();
            notifyAll();
            return value;
        }

        synchronized int size() {
            return queue.size();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Buffer<Integer> buffer = new Buffer<>(2);
        AtomicInteger sum = new AtomicInteger();
        List<Thread> threads = new ArrayList<>();

        for (int p = 0; p < 2; p++) {
            final int base = p * 5;
            Thread producer = new Thread(() -> {
                try {
                    for (int i = 1; i <= 5; i++) {
                        buffer.put(base + i);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            threads.add(producer);
        }

        for (int c = 0; c < 2; c++) {
            Thread consumer = new Thread(() -> {
                try {
                    for (int i = 0; i < 5; i++) {
                        sum.addAndGet(buffer.take());
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });
            threads.add(consumer);
        }

        for (Thread thread : threads) {
            thread.start();
        }
        for (Thread thread : threads) {
            thread.join();
        }

        System.out.println("sum=" + sum.get());
        System.out.println("remaining=" + buffer.size());
    }
}
~~~

Run:

~~~bash
javac BoundedBufferWhileDemo.java
java BoundedBufferWhileDemo
~~~

Stdout when uninterrupted:

~~~text
sum=55
remaining=0
~~~

**Result proof:** The two producers put the numbers 1 through 5 and 6 through 10 (total 55); the two consumers take a total of 10 elements. `synchronized put/take` maintains the invariant `0 <= size <= 2` and prevents two consumers from taking the same element. `while` prevents taking from an empty queue or adding to a full buffer after wakeup. `AtomicInteger` is used to sum results from both consumers, avoiding a race on the sum; `join()` waits for all threads to finish before `main` prints.

**What is not fixed:** the element ordering between **the two different producers** and which consumer receives which number are nondeterministic. The program only asserts the final sum and count. If one thread is interrupted and stops early, the other side may wait forever; the demo intentionally omits a close protocol to stay focused on `while`, so do not substitute it for a production queue without cancellation/shutdown.

### When multiple waiter groups share a monitor

Producers wait for `notFull`; consumers wait for `notEmpty`. An arbitrary `notify()` might wake a producer while the buffer is still full or a consumer while it is still empty, while the group that actually needs to wake remains asleep. `notifyAll()` is simpler and easier to prove live in a shared-monitor example; every waiter must recheck its predicate. The trade-off is waking multiple threads only for them to go back to sleep (contention/thundering herd).

In designs with multiple predicate types, `ReentrantLock` paired with multiple `Condition` objects allows signaling the right group.

## 12. Condition.await() and signal(): Same while Principle

With `java.util.concurrent.locks.ReentrantLock`:

~~~java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Members/methods of a class (snippet, not a standalone file):
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final ArrayDeque<String> queue = new ArrayDeque<>();

public String take() throws InterruptedException {
    lock.lockInterruptibly();
    try {
        while (queue.isEmpty()) {
            notEmpty.await();
        }
        return queue.removeFirst();
    } finally {
        lock.unlock();
    }
}

public void put(String value) {
    lock.lock();
    try {
        queue.addLast(value);
        notEmpty.signal();
    } finally {
        lock.unlock();
    }
}
~~~

If using this snippet in a class, you also need to import `java.util.ArrayDeque`. Constraints:
- The caller must **hold the exact `ReentrantLock`** associated with the `Condition` before calling `await()/signal()`.
- `await()` **releases the lock while waiting**, then reacquires it before returning or throwing `InterruptedException`.
- `signal()` **does not release the lock immediately** and does not grant permission to bypass the predicate.
- Even when a `Condition` has only one type of waiter, spurious wakeups and other threads can still make the predicate false; always use `while`.
- `unlock()` in `finally` ensures the lock is released if an exception occurs.

**Do not mechanically convert `notifyAll` to `signal`** without analyzing liveness. `signal` picks one waiter on that condition; if multiple predicate types share one `Condition`, waking the wrong type or too few waiters can cause a stall. Use separate `Condition` instances for `notEmpty/notFull` when needed, or `signalAll` if the protocol requires waking everyone.

### When do you not need to write while manually?

`BlockingQueue.take()` already implements the wait/take protocol per its class contract; the caller does not need to check `isEmpty()` before calling `take()`:

~~~java
String item = blockingQueue.take();
~~~

This is a snippet inside a method where `blockingQueue` is declared and `InterruptedException` must be handled. If you need non-blocking behavior, use `poll()`, which returns `null` when empty (for standard queues that disallow nulls). If you need bounded waiting, use `poll(timeout, unit)`.

**Do not write:**

~~~java
if (!blockingQueue.isEmpty()) {
    String item = blockingQueue.take();
}
~~~

Because another consumer can drain the queue right after `isEmpty()`, causing `take()` to block even though the condition was once true. A single `take/poll` call with the appropriate semantics avoids caller-side check-then-act races.

## 13. Timed Wait: while Is Still Required, Without Resetting the Timeout

Overloads such as `Object.wait(long millis)`, `Condition.await(long time, TimeUnit unit)`, and `Condition.awaitNanos(long nanosTimeout)` allow bounded waiting.

**Note:** `Object.wait(0)` waits **indefinitely**, not "zero wait." A timed wait can return due to a signal, spurious wakeup, timeout expiration, or interruption; in all cases, never infer that the predicate is true without checking it.

Pattern that fails an overall deadline requirement:

~~~java
while (!ready) {
    monitor.wait(1_000); // Grants a full extra second on every wakeup.
}
~~~

If there are multiple wakeups while `ready` remains false, the total wait time can far exceed 1 second. For an overall timeout, track the **remaining time**.

### Condition.awaitNanos pattern

~~~java
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

// Snippet representing fields/methods inside a class:
private final ReentrantLock lock = new ReentrantLock();
private final Condition readyChanged = lock.newCondition();
private boolean ready;

public boolean awaitReady(long timeout, TimeUnit unit)
        throws InterruptedException {
    long remaining = unit.toNanos(timeout);
    lock.lockInterruptibly();
    try {
        while (!ready) {
            if (remaining <= 0) {
                return false;
            }
            remaining = readyChanged.awaitNanos(remaining);
        }
        return true;
    } finally {
        lock.unlock();
    }
}

public void makeReady() {
    lock.lock();
    try {
        ready = true;
        readyChanged.signalAll();
    } finally {
        lock.unlock();
    }
}
~~~

- `while` checks the predicate after every return from `awaitNanos`.
- `remaining` is decremented using the API's return value, avoiding resetting to the initial timeout.
- The method returns `false` if the condition-wait budget expires while the predicate is still false.
- The method returns `true` **only after observing `ready=true` while holding the lock**.
- The timing calculation here covers the **condition wait duration**, not an end-to-end deadline that includes initially acquiring `lock`. If an overall deadline is required, you must also budget `lockInterruptibly()` using an appropriate `tryLock(remaining, unit)`/deadline protocol.

Do not use repeated `Thread.sleep` as a timed condition wait in latency-sensitive applications or when fast cancellation is needed.

## 14. Interruption and Exceptions: Never Bypass the Condition

When a thread is interrupted during `Object.wait()` or `Condition.await()`, the API may throw `InterruptedException`. **Interruption is not a sign that the predicate is true.** The worker must stop, propagate the exception, or follow a dedicated cancellation policy. Never catch the exception and continue business operations as if permission had been granted.

Appropriate pattern in a method declaring `throws InterruptedException`:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait(); // If interrupted, the exception propagates out.
    }
    useResource();
}
~~~

If unable to propagate:

~~~java
try {
    doInterruptibleWait();
} catch (InterruptedException e) {
    Thread.currentThread().interrupt(); // Restore interrupt status.
    return; // Do not use the resource when the predicate is not true.
}
~~~

This is a snippet inside a `void` method. With `Object.wait()`, the JVM requires the thread to reacquire the monitor before `wait()` returns or throws on interruption per the contract, ensuring `synchronized` still governs lock release. However, shared state may have been modified by **other threads** during the wait; do not assume it stayed unchanged.

### Exception after a half-completed operation

Suppose the invariant is `available + reserved == total`; the code updates `available--`, calls a method that can throw, and only then increments `reserved++`. If an exception occurs in between, `synchronized` automatically releases the monitor but **does not roll back** state. Validate first, commit the full update within the critical section, and roll back if business logic requires it; never enter `wait()` while the state violates an invariant observable by other threads.

### Shutdown must be part of the predicate

If producers stop permanently, consumers can wait forever even with a correct `while` loop. Add a `closed`/`cancelled` condition and call `notifyAll/signalAll` on shutdown:

~~~java
synchronized (monitor) {
    while (queue.isEmpty() && !closed) {
        monitor.wait();
    }

    if (queue.isEmpty()) {
        // closed == true and no items left:
        // terminate per protocol (e.g., Optional.empty).
    } else {
        // take the element and process it.
    }
}
~~~

This snippet illustrates control flow, not a standalone program. The write `closed=true` must happen under the same monitor, followed by waking all relevant waiters. If there are two waiter groups such as producers and consumers, shutdown may need to signal **both** groups. When closing means no new additions are allowed but queued items may be drained, consumers can still take remaining items before terminating.

## 15. Common Misconceptions and Pitfalls

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| `if (!ready) wait()` | Skips rechecking after wakeup | `while (!ready) wait()` |
| Assuming `notify()` means the condition is definitely true | Notify does not carry the predicate or reserve a spot | Read state under the monitor after wakeup |
| Only thinking about spurious wakeups | Ignores contention among multiple waiters | Account for resource competition as well |
| Checking outside the lock, then waiting inside the lock | Missed notification | Check and wait under the same monitor |
| Producer modifies state outside the monitor | No consistent protocol or visibility | All access paths use the same lock |
| Calling wait/notify without holding the right monitor | `IllegalMonitorStateException` | Hold the monitor of the target object |
| Thinking `notifyAll` releases the monitor | Waiters still have to contend for the lock | The signaling thread must exit the lock block |
| Using `Thread.sleep()` instead of wait | Sleep does not release the monitor | Use condition wait or `BlockingQueue` |
| Using `getState() == WAITING` to decide whether to notify | Snapshot is racy and not a business predicate | Rely on protected state |
| Releasing the lock between checking and taking the element | Check-then-act race | Keep both operations in the critical section |
| Waiting while an invariant is broken | Other threads may observe inconsistent state | Restore invariant before waiting |
| Using `notify()` with multiple waiter types | Wakes wrong group, can stall progress | `notifyAll` or separate `Condition`s |
| Timed wait always reusing the initial timeout | Wakeups cause total wait to exceed deadline | Track remaining time or deadline |
| Ignoring `InterruptedException` | Cancellation/shutdown hangs | Propagate or restore and exit |
| One item with two waiters, no `closed` state | One waiter may validly wait forever | Design a close/cancel protocol |
| Hand-rolling wait/notify for a simple queue | Unnecessarily error-prone | Prefer `BlockingQueue.take/poll` |
| Using `LongAdder/AtomicInteger` to "fix" `if` wait | Atomic counters do not replace predicate/lock protocols | Design the condition protocol properly |

## 16. Checklist for Designing a Waiting Mechanism

1. **What is the exact predicate?** Not just "a notification arrived," but a testable condition like `!queue.isEmpty()` or `ready == true`.
2. **Which state forms the predicate?** Who writes it, who reads it, and do all of them use the same monitor/lock?
3. **What is the invariant?** Does it hold before the thread releases the lock or enters `wait()/await()`?
4. **Is the predicate checked in a `while` loop?** If woken by a spurious wakeup or if another waiter consumed the resource, does the code recheck?
5. **Are the final check and the action in the same critical section?** If the lock is released between them, the condition can vanish.
6. **Is the signal sent after the state changes?** A signal does not replace state; if state hasn't changed, the waiter will simply wait again.
7. **What if the signal happens before the waiter arrives?** A correct pattern must let the waiter observe the predicate is already true and skip waiting.
8. **Are there multiple waiter groups?** Choose `notifyAll` or separate `Condition`s to avoid waking the wrong group.
9. **Are overall timeout and interruption handled?** Do not reuse the full timeout after every wakeup; provide an exit path when the task is cancelled.
10. **Could producers stop existing?** Require `closed/cancelled`, a poison pill, or an explicit termination protocol.
11. **Are other locks held while waiting?** `wait()` only releases its own monitor.
12. **Can a higher-level primitive be used?** `BlockingQueue` for data, `CountDownLatch` for one-shot signals, `Semaphore` for permits, `Phaser` for phased execution.
13. **Has liveness been verified?** Preserving invariants while threads wait forever can still be a design bug.
14. **Has exception-handling logic been checked?** Releasing a lock does not mean rolling back state.
15. **Are coordinated tests used instead of `sleep` for reproduction?** Latches/barriers help force an interleaving; stress tests supplement this but do not prove the absence of races.

## 17. Self-Check Questions

1. Why can't you use `if` after `notifyAll()` and blindly proceed? **Because another thread may take the resource first, the predicate may be false, and spurious wakeups can occur.**
2. If only a single consumer is waiting, is `while` still necessary? **Yes**, because of spurious wakeups and the predicate still being able to change.
3. Does `Object.wait()` release all locks currently held? **No**, only the monitor of the object on which `wait()` is called.
4. Does `Thread.sleep(100)` inside `synchronized` help a producer enter the monitor? **No**, `sleep` holds the monitor.
5. If a producer notifies before the consumer starts waiting, what happens under a correct protocol? **The consumer checks the state, sees the predicate is true, and does not wait.**
6. Why doesn't `volatile ready` automatically prevent missed notifications when checking and waiting are separated? **Volatile does not make those two steps atomic within a monitor protocol.**
7. Two consumers are notified via `notifyAll` for one item; at most how many succeed in taking it? **One.** The other must recheck and either wait or exit if closed.
8. If code uses `while` and still waits forever when no producers remain, is that a `while` bug? **No; it is missing a termination/timeout/cancellation protocol.**
9. What are the requirements to validly call `Condition.await()`? **The thread must hold the lock associated with the `Condition` and handle interruption.**
10. After `Condition.await()` returns, can you skip checking the predicate? **No**, you must use `while`.
11. How do `notify()` and `notifyAll()` differ? **`notify` selects one waiter; `notifyAll` wakes all waiters in the wait set, with no execution order guarantee.**
12. Why shouldn't a timed wait inside a `while` loop always reuse 1 second? **Each wakeup increases total elapsed time beyond the intended deadline.**
13. When `InterruptedException` occurs, may you proceed to use the awaited resource? **Not automatically; interruption is a cancellation path, not proof that the condition is true.**
14. Why can calling `wait()` between two related state updates violate an invariant? **`wait()` releases the monitor, exposing intermediate state to other threads.**
15. Should you use `if (!queue.isEmpty()) queue.take()` to avoid blocking? **No, the queue may become empty after the check; use `poll()` if you want non-blocking behavior.**
16. In the `IfWaitBugDemo` experiment, why is printing false valid even though a notification was received? **The notification was sent without changing `ready`; `if` did not recheck.**
17. In the `TwoConsumersIfDemo` experiment, why does one removal fail? **Both waiters were woken up but there was only one item; the second waiter did not recheck.**
18. What matters more than observing `Thread.State.WAITING`? **Business state and the predicate under a proper synchronization protocol.**

## Conclusion

**A thread waking up does not mean the condition is ready.** `wait()/await()` can return due to spurious wakeups, and even with a genuine notification, another thread may consume the resource before the waiter does. Therefore, condition waiting in Java must rely on **`while` checking the predicate under the same lock**, never on a single-check `if`.

The right protocol: **acquire lock → check predicate → if false, wait/await and release lock → reacquire lock → recheck in `while` → perform the necessary action while still holding the lock → update invariant and signal → release lock**. Add timeout, interruption, and shutdown handling to guarantee progress; prefer higher-level primitives like `BlockingQueue` when you do not need to build a custom monitor protocol.

## Java SE 17 References

- [java.lang.Object — wait, notify, notifyAll](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): monitor ownership, wait set, spurious wakeup, reacquire.
- [java.util.concurrent.locks.Condition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Condition.html): await, signal, signalAll, and condition waiting.
- [java.util.concurrent.locks.ReentrantLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html): lock, lockInterruptibly, unlock.
- [java.util.concurrent.BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html): take, poll, and timeouts.
- [Java Language Specification 17 — Threads and Locks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html): happens-before and the Java Memory Model.
