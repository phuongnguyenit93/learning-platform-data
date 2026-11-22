# Why Does await() Always Need a Condition-Checking Loop?

When using **`ReentrantLock`** and **`Condition`** from `java.util.concurrent.locks`, a thread often needs to wait for a business condition: "the queue has an element", "the gate is open", "capacity is available", "a result is ready", etc. The **`Condition.await()`** method lets the thread temporarily release the lock so another thread can modify the state, then be awakened and reacquire the lock to continue.

However, **being awakened does not mean the awaited condition is guaranteed to be true**. Therefore, the standard pattern is:

```java
lock.lock();
try {
    while (!conditionIsTrue()) {
        condition.await();
    }
    // Execute only when the current predicate is true, under the same lock.
} finally {
    lock.unlock();
}
```

This is an illustrative snippet, assuming `lock` is a `ReentrantLock`, `condition` is a `Condition` created via `lock.newCondition()`, and `conditionIsTrue()` reads state guarded by that same lock. The method containing this snippet must declare or handle `InterruptedException`.

**The `while` loop is not a decorative detail.** It is part of the correctness protocol: check the condition (*predicate*) → wait while it is false → wake up → **recheck** → act only when the condition is currently true.

## 1. How Does Condition.await() Work?

`Condition` is a conditional waiting mechanism bound to a `Lock`. Typically:

```java
ReentrantLock lock = new ReentrantLock();
Condition readyCondition = lock.newCondition();
```

`Condition.await()` operates according to this logic:

1. The thread must hold the **associated lock** when calling `await()`. For a `Condition` created from `ReentrantLock`, calling it without holding the lock throws `IllegalMonitorStateException`.
2. `await()` **releases the lock** (including the ReentrantLock hold depth per its contract) and places the thread into the condition wait queue.
3. Another thread acquires the lock, updates the shared state, and may then call `signal()` or `signalAll()`.
4. A waiter may wake up due to a signal, an interrupt, or a *spurious wakeup*. It still must **reacquire the lock** before `await()` returns normally or completes throwing `InterruptedException`.
5. After acquiring the lock, the waiter resumes right after `await()`. By this time, the shared state may have changed further, so it must recheck the predicate.

Diagram:

```text
Consumer thread                       Producer thread
---------------                       ---------------
lock.lock()
while (queueEmpty) {
    notEmpty.await()
      | release lock
      v                                lock.lock()
   WAITING                             queue.add(item)
      ^                                notEmpty.signal()
      |                                lock.unlock()
      +-- wake up, contend for lock ---+
    reacquire lock
    recheck queueEmpty
}
remove item
lock.unlock()
```

**`signal()` does not transfer the lock immediately.** The signaling thread typically still holds the lock until `unlock()`. The awakened waiter still has to wait its turn to acquire the lock. And `signal()` does not itself make `queueEmpty == false` true: the state-mutating code is responsible for that.

## 2. Three Reasons to Use while Instead of if

### Reason 1: Spurious wakeups — waking up without the expected signal

The `Condition.await()` contract **permits spurious wakeups**. The JVM/runtime may return a waiter without a direct `signal()` from another thread as the application intended. A timed wait can also expire before the predicate becomes true.

If you write:

```java
// NOT safe against spurious wakeups.
if (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

then the waiter may wake up while the queue is still empty, and `remove()` will throw an exception or violate the protocol. Changing it to:

```java
while (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

Both snippets assume the code already holds the lock guarding `queue` and the `notEmpty` condition; they are not standalone programs. On every wakeup, `while` reads the **current state**, regardless of the reason for waking up.

### Reason 2: A signal only grants a chance to check, not a reserved resource

Suppose two consumers, C1 and C2, are waiting because the queue is empty. The producer adds **one** element and calls `signalAll()`.

- Both C1 and C2 are awakened and can contend for the lock.
- C1 acquires the lock first, removes the last element, and unlocks.
- C2 acquires the lock later. The queue **is empty again**.

If C2 used `if`, it would proceed straight past `await()` **without rechecking** and try to remove a nonexistent element. With `while`, C2 detects that the queue is empty and waits again.

Even with `signal()` (waking only one waiter), another thread **not in the wait queue** can still acquire the lock ahead of the awakened waiter and consume the resource. Therefore, using `signal()` also **does not allow omitting `while`**.

### Reason 3: The condition can change before the waiter reacquires the lock

A producer might set `ready = true` and call `signal()`, and then another thread might set `ready = false` **before the waiter reacquires the lock**. A signal only reflects the state at an earlier point in time. The waiter must decide based on the **current predicate**, not on "I just received a signal."

General rule: **notification = a prompt to recheck; predicate = source of truth**.

## 3. Thinking Correctly About Predicate, Lock, and Condition

| Component | Responsibility |
|---|---|
| **State/predicate** | Represents the true business condition, e.g., `!queue.isEmpty()`, `open`, `remaining > 0`. |
| **Lock** | Guards every relevant read/write path of the state and ensures no interleaving between check-and-wait or check-and-act. |
| **Condition** | Provides a waiting queue and signaling for threads awaiting a predicate; it **does not store business truth**. |
| **await()** | Releases the associated lock, waits, then reacquires the lock before returning or handling an interrupt. |
| **signal()/signalAll()** | Gives waiter(s) a chance to wake up; does not guarantee the predicate is true or that a waiter runs immediately. |
| **while** | Rechecks the invariant after every wakeup path. |

A basic protocol:

```java
// Waiter side: use the lock protecting the state.
lock.lock();
try {
    while (!ready) {
        readyCondition.await();
    }
    consumeReadyState();
} finally {
    lock.unlock();
}

// Signaler side: same lock and same state.
lock.lock();
try {
    ready = true;
    readyCondition.signalAll();
} finally {
    lock.unlock();
}
```

This is an illustrative snippet requiring `lock`, `readyCondition`, `ready`, `consumeReadyState()`, and `InterruptedException` handling. If the condition is a one-time event, the `ready` predicate can stay true. If the condition involves a consumed resource, the predicate must be updated after each consumption.

**Key to preventing lost signals:** check the condition and call `await()` under the **same lock**. A thread modifying the condition cannot slip into the gap between the waiter checking false and releasing the lock to wait. If the signal happens before the waiter starts, the waiter will see the predicate as true once it acquires the lock and **will not wait**. Do not use `signal()` as a flag that automatically stores notifications.

## 4. Example 1: Condition Gate — Correct Whether Signal Arrives Before or After Waiter

Create file **`ConditionGateDemo.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionGateDemo {
    static final class Gate {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition opened = lock.newCondition();
        private boolean isOpen;

        void awaitOpen() throws InterruptedException {
            lock.lock();
            try {
                while (!isOpen) {
                    opened.await();
                }
            } finally {
                lock.unlock();
            }
        }

        void open() {
            lock.lock();
            try {
                isOpen = true;
                opened.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();

        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen();
                System.out.println("Worker entered");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "gate-worker");

        worker.start();
        gate.open();
        worker.join();
        System.out.println("Main finished");
    }
}
```

```bash
javac ConditionGateDemo.java
java ConditionGateDemo
```

Output when there is no external interrupt:

```text
Worker entered
Main finished
```

`gate.open()` may run **before** the worker enters `awaitOpen()`: when it acquires the lock, the worker sees `isOpen = true` and skips `await()`. If the worker is already waiting, `signalAll()` wakes it up to recheck the state after acquiring the lock. **Both schedules are correct** thanks to storing the predicate and using `while`.

The `isOpen` field does not need `volatile` in this protocol: all accesses use the same `ReentrantLock`, and unlock/lock establish the proper *happens-before* relationship under the Java Memory Model. `join()` ensures `Main finished` is printed after the worker has completed.

## 5. Example 2: A Reproducibly Broken if — signalAll for Two Waiters, One Permit

The following example is **intentionally written incorrectly** with `if` to illustrate why a signal does not reserve a resource for a waiter. Two workers wait for a single permit; after both have entered the waiting path, main publishes one permit and wakes everyone up. The bug is that both waiters proceed past `if` without rechecking the permit.

Create file **`BrokenIfAwaitDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class BrokenIfAwaitDemo {
    static final class BrokenPermit {
        final ReentrantLock lock = new ReentrantLock();
        final Condition changed = lock.newCondition();
        final CountDownLatch bothArrived = new CountDownLatch(2);
        boolean available;

        void takeIncorrectly(AtomicInteger accepted)
                throws InterruptedException {
            lock.lock();
            try {
                if (!available) { // Wrong: checks only once.
                    bothArrived.countDown();
                    changed.await();
                }
                available = false;
                accepted.incrementAndGet();
            } finally {
                lock.unlock();
            }
        }

        void publishOnePermit() {
            lock.lock();
            try {
                available = true;
                changed.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        BrokenPermit permits = new BrokenPermit();
        AtomicInteger accepted = new AtomicInteger();

        Runnable task = () -> {
            try {
                permits.takeIncorrectly(accepted);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread a = new Thread(task);
        Thread b = new Thread(task);
        a.start();
        b.start();

        permits.bothArrived.await();
        permits.publishOnePermit();
        a.join();
        b.join();

        System.out.println("Published permits: 1");
        System.out.println("Accepted requests: " + accepted.get());
    }
}
```

```bash
javac BrokenIfAwaitDemo.java
java BrokenIfAwaitDemo
```

Output in normal execution without interrupts:

```text
Published permits: 1
Accepted requests: 2
```

`bothArrived` counts down when each worker holds the lock and is about to wait. Main only publishes the permit after both have reached that point. Even if the second worker has not yet released the lock to `await()`, main still must wait to acquire the lock before `publishOnePermit()` can run; thus when main calls `signalAll()`, both workers are already on the wait path or have woken up per the API rules. With `if`, both can proceed past `await()` **without verifying that the permit still exists**; as a result, two requests are accepted even though only one permit was published.

**How to fix:** replace `if (!available)` with `while (!available)`, then set `available = false` under the same lock. Then only one thread consumes the permit; the other thread will `await()` again. However, in this example if there is only one permit **and no subsequent publish/close**, the remaining thread would wait indefinitely and `join()` would never finish. To demonstrate a complete fix, you must provide another permit or a close/cancel mechanism to wake up and let the remaining waiter exit. The queue example in the next section shows an explicit close protocol.

The example above is an **intentionally unsafe counterexample** and must not be used as production code.

## 6. Example 3: A Single-Slot Queue Using Two Conditions

In producer–consumer, there are two distinct predicates:

- **`notEmpty`:** the consumer may take when the slot has an item, or exit if closed.
- **`notFull`:** the producer may put when the slot is empty, or stop if closed.

Using two `Condition`s bound to the **same `ReentrantLock`** lets you signal the right group of waiters and avoid waking unrelated threads. Every `await()` still **needs a `while` loop**.

Create file **`OneSlotConditionQueue.java`**:

```java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class OneSlotConditionQueue {
    static final class Channel {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer value;
        private boolean closed;

        void put(int item) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value != null && !closed) {
                    notFull.await();
                }
                if (closed) {
                    throw new IllegalStateException("channel closed");
                }
                value = item;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        Integer take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (value == null && !closed) {
                    notEmpty.await();
                }
                if (value == null) {
                    return null; // Closed and no items left.
                }
                int result = value;
                value = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }

        void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Channel channel = new Channel();

        Thread producer = new Thread(() -> {
            try {
                for (int item = 1; item <= 3; item++) {
                    channel.put(item);
                }
                channel.close();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                channel.close();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                Integer item;
                while ((item = channel.take()) != null) {
                    System.out.println("Received: " + item);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();
        System.out.println("Finished");
    }
}
```

```bash
javac OneSlotConditionQueue.java
java OneSlotConditionQueue
```

Output in a normal run without interrupts:

```text
Received: 1
Received: 2
Received: 3
Finished
```

**Why is this correct?**

1. `value` and `closed` are private state only read/written under the same `lock`.
2. The producer checks `value != null && !closed` in a `while` loop; if the slot is full, `notFull.await()` releases the lock so the consumer can take the item.
3. The consumer checks `value == null && !closed` in a `while` loop; if the slot is empty, `notEmpty.await()` releases the lock so the producer can put an item.
4. When the producer finishes putting, it calls `notEmpty.signal()`; when the consumer finishes taking, it calls `notFull.signal()`. Because there is one producer and one consumer, signaling a single waiter fits the scope of this example.
5. `close()` sets `closed = true` and then calls `signalAll()` on **both condition queues**, because waiters must recheck for closure. The consumer still drains any item remaining in the slot before receiving `null` to indicate completion.
6. `join()` ensures the program prints `Finished` after both threads finish.

When scaling to multiple producers and consumers, you must clearly define close semantics, ordering, fairness, interruption, and error handling; whether `signal()` is sufficient depends on the protocol. This is a minimal implementation for learning about conditions, not a replacement for feature-rich production queues. For typical applications, **`ArrayBlockingQueue`** or `LinkedBlockingQueue` already manages locking/await/signal and provides clear `put()`/`take()` APIs.

## 7. signal() and signalAll() Do Not Replace Predicate Checks

`Condition.signal()` notifies **one** waiter on the corresponding condition queue; `signalAll()` moves **all** waiters on that condition into a state where they can contend for the lock. With `ReentrantLock` and a `Condition` from `newCondition()`, you must hold the lock when calling `signal()`/`signalAll()`.

Comparison with `Object.notify()`/`notifyAll()`:

| `Object.wait()` | `Condition.await()` |
|---|---|
| Bound to an object's intrinsic monitor. | Bound to a `Lock` and a `Condition` object created by the lock. |
| Wait via `synchronized(lockObj)` then `lockObj.wait()`. | Wait via `lock.lock()` then `condition.await()`. |
| Signal via `notify()`/`notifyAll()` on the same monitor object. | Signal via `signal()`/`signalAll()` on the corresponding `Condition`. |
| One object has one intrinsic wait set. | One `ReentrantLock` can have multiple condition queues (`notEmpty`, `notFull`). |
| Must wait in a `while` loop checking the predicate. | **Also must wait in a `while` loop checking the predicate.** |

The two API families are not directly interchangeable: `condition.signal()` does not wake a thread in `object.wait()`; `object.notify()` does not wake a thread in `condition.await()` on another condition.

`signal()` **does not accumulate permits**: a signal sent when no waiter is on that condition queue is not saved to wake a thread that arrives later. If your protocol needs to remember "3 remaining permissions to proceed," store a **counter state** or consider `Semaphore`, rather than assuming 3 `signal()` calls equal 3 permits.

## 8. Interruption: The Loop Must Still Respect the Cancellation Path

`await()` is an interruptible waiting operation. When a thread is interrupted while waiting, it may throw `InterruptedException` per its contract; the interrupt flag is cleared when the exception is thrown. Before completing the exception path, `ReentrantLock`'s `Condition.await()` **reacquires the lock**, so `finally { lock.unlock(); }` remains valid.

How to handle it:

```java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    // The ready state is genuinely true.
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    // Terminate cooperatively or propagate cancellation.
} finally {
    lock.unlock();
}
```

This is an illustrative snippet assuming the variables are already declared. In APIs that allow throwing `InterruptedException`, a simpler approach is to **propagate it** so the caller decides. Never swallow the exception and proceed as if the condition were true.

Create file **`InterruptibleConditionDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class InterruptibleConditionDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantLock lock = new ReentrantLock();
        Condition changed = lock.newCondition();
        CountDownLatch entered = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            lock.lock();
            try {
                entered.countDown();
                boolean ready = false;
                while (!ready) {
                    changed.await();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Waiting interrupted");
            } finally {
                lock.unlock();
            }
        }, "waiter");

        worker.start();
        entered.await();
        worker.interrupt();
        worker.join();

        System.out.println("Worker finished");
    }
}
```

```bash
javac InterruptibleConditionDemo.java
java InterruptibleConditionDemo
```

Output:

```text
Waiting interrupted
Worker finished
```

`entered.countDown()` signals main that the worker has entered the locked region; main may interrupt before or after the `changed.await()` call. In the former case, `await` detects the interrupt flag per its contract and throws; in the latter case, `await` is interrupted while waiting. Both run the `catch` block, restore the flag, unlock, and let the worker finish. `join()` waits for the worker before printing the final line. This is an example of **cooperative cancellation**, not using `interrupt()` to force a predicate change.

## 9. Does awaitUninterruptibly() Remove the Need for while?

**No.** `awaitUninterruptibly()` does not throw `InterruptedException` while waiting, but it can still experience spurious wakeups or be signaled when the predicate is not yet true. It still must be inside a `while` loop:

```java
lock.lock();
try {
    while (!ready) {
        condition.awaitUninterruptibly();
    }
} finally {
    lock.unlock();
}
```

Illustrative snippet; `condition`, `lock`, and `ready` are assumed declared. When interrupted while waiting, `awaitUninterruptibly()` keeps waiting instead of returning due to the interrupt; the interrupt status is preserved per its contract. Choose this API **only when the protocol truly needs to ignore interrupt requests during the wait**. Applications that need shutdown/cancellation are usually better served by interruptible `await()`.

## 10. Timed await(): Expiring Does Not Prove the Condition Is True

The variants `Condition.awaitNanos(long nanosTimeout)`, `await(long time, TimeUnit unit)`, and `awaitUntil(Date deadline)` allow bounded waiting. After they return, the program still must **recheck the predicate**. A timeout does not mean the condition became true; being signaled also does not mean the condition is still true.

Pattern using `awaitNanos`:

```java
long remaining = timeoutNanos;
lock.lock();
try {
    while (!ready) {
        if (remaining <= 0L) {
            return false; // Timed out before the condition became true.
        }
        remaining = condition.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
```

This is a code snippet **inside a method returning `boolean`** that may throw `InterruptedException`, not a standalone Java program. The variables `lock`, `condition`, `ready`, and `timeoutNanos` are assumed declared. `awaitNanos()` returns an estimate of the remaining time per its contract, which may be non-positive on timeout. Feeding `remaining` back into the loop ensures the total wait budget is managed rather than resetting the full timeout on every wakeup.

For `await(time, unit)`, the boolean return value **only indicates signal vs. timeout status**, not a replacement for the predicate. If you need exact handling of the condition around timeout, the API design should clearly state "succeeds when predicate is true" and check under the lock. If you need timeouts based on wall-clock time, watch out for clock changes; for interval measurement, `System.nanoTime()` is usually more appropriate than `currentTimeMillis()`.

## 11. Fair Locks, Signal Order, and Starvation

`new ReentrantLock(true)` creates a fair lock according to `ReentrantLock`'s lock-granting policy, but **it does not eliminate the need for `while`**. Fairness does not turn a signal into a resource reservation, and it does not prevent the predicate from changing between the signal and the waiter acquiring the lock.

`signal()` may follow an ordered waiter selection rule inside `ReentrantLock.ConditionObject`, but the final order in which threads **acquire the lock and act** also depends on contention and lock policy. Do not build correctness on an assumption that "the first waiter signaled will be the first to process data" unless the API contract actually guarantees all of that.

Many waiters waking up and then waiting again can increase contention or cause a *thundering herd*, especially when using `signalAll()`. Common optimizations are using multiple condition queues for distinct predicates, choosing `signal()` when provably sufficient, and keeping lock-held sections short. However, **performance tuning must come after the correctness of predicate + `while`**.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `if (!ready) await()` | Spurious wakeups or another thread taking the resource causes incorrect action. | Use `while (!ready) await()`. |
| Calling `await()` without holding the associated lock | `IllegalMonitorStateException` with `ReentrantLock`'s `Condition`. | Acquire the lock with `lock()`/`lockInterruptibly()`, unlock in `finally`. |
| Calling `signal()` outside the lock | `IllegalMonitorStateException` with `ReentrantLock`'s `Condition`. | Update state and signal under the same lock. |
| Assuming `signal()` guarantees the predicate is true | Predicate can change before the waiter reacquires the lock. | Recheck in `while`. |
| Relying on signals as stored state | Signals with no waiting threads are lost. | Store boolean/counter/queue state; signals only notify. |
| Calling `Thread.sleep()` while holding the lock to wait | Threads needing the lock to change the condition cannot enter, causing a stall/deadlock. | Use `await()`, which releases the lock per contract. |
| Checking the predicate outside the lock, then calling `await()` inside | Race between check and wait, risking lost signals. | Guard both predicate check and `await()` under the same lock. |
| Using `signalAll()` with `if` | Multiple waiters pass the stale guard and consume a single resource. | Every waiter must use `while`; update predicate upon consumption. |
| Swallowing `InterruptedException` | Loses cancellation signal and may continue against business rules. | Propagate or restore the flag and terminate cooperatively. |
| Resetting the full timeout after every wakeup | Can wait longer than the intended budget. | Track remaining time with `awaitNanos()`/deadline. |
| Calling `signal()` and waiting for the waiter to run before unlocking | Waiter cannot complete `await()` before reacquiring the lock. | Exit the lock region promptly after updating/signaling when appropriate. |
| Waiting on a predicate with no close/cancel path | Threads can hang forever if the condition never becomes true. | Design a `closed` state, `signalAll()`, and handle interruption. |

## 13. How to Verify an await-loop Is Correct

When reviewing a class that uses `Condition` directly, ask the following questions:

1. **What is the predicate?** For example, `!queue.isEmpty()`, `capacityAvailable`, `closed || ready`. Does it accurately represent the condition required to perform the action?
2. **Who can modify the predicate?** Do all relevant access paths use the same `ReentrantLock`?
3. **Is `while` used instead of `if`?** Is the predicate rechecked after every wakeup?
4. **Do the check and `await` share the same lock?** If not, there is a lost-signal window between check and wait.
5. **Does the post-loop action change the predicate?** If so, it must also occur under the lock and signal the appropriate waiters.
6. **What about close/interrupt/timeout?** Can the loop exit or cancel in a controlled manner without unintended infinite waiting?
7. **Does `signal` target the right condition queue?** With multiple predicates, `notEmpty` and `notFull` should be separated to avoid waking the wrong group.
8. **Is there a deadlock risk?** `await()` releases the associated lock but does not release other locks the thread holds. Avoid holding multiple nested locks without a consistent ordering.
9. **Can it be simplified?** If you just need a queue, `BlockingQueue` is usually easier to use correctly; if you just need a one-shot signal, `CountDownLatch` may fit; if you need permits, consider `Semaphore`.

## 14. When Do You Not Need to Write an await-loop Yourself?

`Condition` is a necessary low-level tool for building custom synchronization constructs, but many problems already have higher-level abstractions:

| Problem | Typically Appropriate Java Tool |
|---|---|
| Bounded/unbounded producer–consumer queue | `ArrayBlockingQueue`, `LinkedBlockingQueue`. |
| One-time gate | `CountDownLatch`. |
| Waiting for a task result | `Future.get()`, `CompletableFuture`. |
| Counting resources with permits | `Semaphore`. |
| Multi-phase rendezvous | `CyclicBarrier`, `Phaser`. |
| Custom coordination with multiple predicates | `ReentrantLock` + multiple `Condition`s; use `while` in every waiter. |

Avoid writing your own multi-threaded queue when unnecessary: beyond the await-loop, you also have to handle fairness, capacity, cancellation, shutdown, deadlocks, timeouts, and performance. Still, understanding **why `while` is mandatory** helps you read, debug, and use concurrent abstractions properly.

## 15. Self-Check Questions

1. **If `await()` is signaled, is the predicate guaranteed to be true?** No. Another thread may take the resource first or the predicate may change; the waiter must recheck.
2. **What is a spurious wakeup?** A waiter may wake up even without a signal corresponding to the business condition; this is permitted by the API contract.
3. **Why can't `while` be replaced with `if` when there is only one waiter?** Spurious wakeups and predicate changes can still occur; there is no general guarantee for `if`.
4. **Why must the predicate check share the same lock as `await()`?** To prevent another thread from changing the condition and signaling in the window between the check and the wait.
5. **Does `signalAll()` make every waiter eligible to act?** No. All must contend for the lock and check the predicate themselves; perhaps only one can make progress.
6. **Does `signal()` store a permit for a future thread to use?** No; to store continuation capability you need state/a counter, or `Semaphore`.
7. **Does `await()` release its associated lock?** Yes, per the `Condition`/`ReentrantLock` contract, and it must reacquire the lock before returning. It does not automatically release other locks.
8. **When `await()` is interrupted and throws an exception, should you proceed as if the condition were true?** No. You should propagate the cancellation request to the caller or restore the flag and exit per protocol.
9. **Does a timed `await` returning mean the predicate is true?** No; you must recheck both the predicate and the timeout budget.
10. **If you use a fair lock, do you still need `while`?** Yes. Fairness does not eliminate spurious wakeups and does not reserve resource state for a waiter.

**Takeaway:** `Condition.await()` only says *"release the lock and wait for a chance to recheck"*; it does not say *"the condition is now guaranteed to be true."* Therefore, the reliable pattern is always **hold the right lock → `while (!predicate) await()` → act under the lock**, with proper handling for timeouts, interruption, and signaling.
