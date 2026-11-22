# Lock interface vs. intrinsic monitor in Java

Java has two common ways to protect shared data using **mutual exclusion**: the `synchronized` keyword, which uses an object's **intrinsic monitor**, and objects implementing `java.util.concurrent.locks.Lock`, most commonly `ReentrantLock`. Both can protect the same invariant and establish the necessary memory relationship between threads, but they differ in **how locks are acquired/released, cancellation while waiting, timeouts, wait conditions, and lock lifecycle management**.

Understanding this difference helps answer a concrete design question: **does my critical section only need simple exclusivity, or does it also require try-locking, deadlines, interruptibility, or multiple wait condition groups?** This article applies to Java concurrency in general, without covering integrated frameworks.

## 1. What exactly are the terms “lock” and “monitor”?

An **intrinsic monitor** (also called an *intrinsic lock* or *object monitor*) is associated with every Java object and is used when entering `synchronized`. A thread wishing to enter a synchronized block must own the corresponding monitor. Other threads attempting to acquire that monitor must wait until the owner releases it. A monitor allows only one thread to own it at a time and is **reentrant**: the same thread currently holding the lock can acquire it again multiple times.

The **`Lock` interface** is a library-level contract in `java.util.concurrent.locks`, providing methods such as `lock()`, `unlock()`, `tryLock()`, `lockInterruptibly()`, and `newCondition()`. `ReentrantLock` is a reentrant mutual exclusion implementation with additional features. A `ReentrantLock` object is still a Java object with its own intrinsic monitor, but **these two locking mechanisms are independent**.

Both protect shared state when **all relevant access paths follow the same lock or synchronization protocol**. Locking only the writer while readers read regular fields directly, or locking on two different objects, is not enough to protect invariants/visibility.

### Very short example

Intrinsic monitor:

```java
private final Object monitor = new Object();
private int count;

void increment() {
    synchronized (monitor) {
        count++;
    }
}
```

Explicit lock:

```java
private final Lock lock = new ReentrantLock();
private int count;

void increment() {
    lock.lock();
    try {
        count++;
    } finally {
        lock.unlock();
    }
}
```

Both code pieces are **snippets placed inside a class**, not standalone programs. The second example requires importing `java.util.concurrent.locks.Lock` and `ReentrantLock`. Both protect the read–modify–write `count++` if **all** reads/writes requiring consistency use that exact same lock. The obvious difference: `synchronized` automatically releases the monitor when exiting scope, whereas `Lock` requires the programmer to call `unlock()` after acquiring the lock.

## 2. Overview comparison table

| Criterion | `synchronized` / intrinsic monitor | `Lock` / `ReentrantLock` |
| --- | --- | --- |
| Mechanism | Language keyword and a Java object's monitor | Library-level API, an object implementing `Lock` |
| Acquiring the lock | Entering a `synchronized` block/method | `lock()`, `lockInterruptibly()`, or `tryLock(...)` |
| Releasing the lock | Automatic when exiting the block/method, including on exception | Calling `unlock()`, typically in `finally` |
| Non-blocking try-acquire | No standard `synchronized.tryLock()` syntax | `tryLock()` returns `boolean` immediately |
| Bounded wait time for acquisition | No timed acquire version of `synchronized` | `tryLock(timeout, unit)` |
| Interrupt while waiting **to acquire** | Cannot cancel waiting to enter a monitor via interrupt alone | `lockInterruptibly()` and timed `tryLock` support interruption |
| Condition waiting mechanism | `Object.wait/notify/notifyAll` on **that monitor** | `Condition.await/signal/signalAll` from `newCondition()` |
| Number of condition groups | One wait set attached to each object monitor | Multiple `Condition`s can be created on the same `ReentrantLock` |
| Reentrancy | Yes | `ReentrantLock` has it; **not every `Lock` implementation is the same** |
| Fairness option | No fairness option via `synchronized` | `ReentrantLock(true)` has a contract-based fairness policy, with limits |
| Thread state under contention | Usually `BLOCKED` when waiting to acquire the monitor | Usually parked, showing `WAITING`/`TIMED_WAITING` depending on API/implementation |
| Memory ordering guarantees | Monitor unlock happens-before the next lock on the same monitor | `Lock` lock/unlock has equivalent memory synchronization by contract |
| Preference for simplicity, minimal setup | Very suitable | More verbose; ownership/lifecycle must be managed explicitly |
| Locking across multiple methods/scopes | Requires designing `synchronized` around lexical scope | Can hold an explicit lock across call boundaries, though easy to forget unlock |
| Overhead | Depends on JVM/contended/uncontended workload | Depends on implementation/fairness/contended workload |

**There is no universal answer that “`ReentrantLock` is always faster” or “`synchronized` is always slower.”** The JVM optimizes monitors and lock libraries under various conditions. Measure workload, lock contention, and latency before choosing for performance.

## 3. How does an intrinsic monitor work?

### 3.1. Monitor identity

Three common forms:

```java
class Example {
    private final Object lock = new Object();
    private static int globalCount;
    private int localCount;

    void withBlock() {
        synchronized (lock) {
            localCount++;
        }
    }

    synchronized void withInstanceMonitor() {
        localCount++;
    }

    static synchronized void withClassMonitor() {
        globalCount++;
    }
}
```

This is a class snippet; there is no `main` yet. `withBlock` uses the monitor of the `lock` object, `withInstanceMonitor` uses the monitor of `this`, and `static synchronized` uses the monitor of `Example.class`. **These three monitors are not the same.** If two methods both modify `localCount` but use different monitors, they do **not** mutually exclude each other. In this example, if callers can invoke both methods concurrently on the same instance, **one** lock must be standardized across both update paths.

Locking on `this` can be interfered with by external code if a caller writes `synchronized (instance)`. Locking with a private object `private final Object lock` helps prevent unintended interference with the locking protocol. Do not lock on objects that might be unintentionally shared, such as string literals or cached wrappers.

### 3.2. Scope-based monitor release

`synchronized` automatically releases the lock when execution leaves the block, even on `return` or an exception:

```java
synchronized (lock) {
    if (someCondition) {
        return;
    }
    updateState();
}
```

This is a snippet inside a method, assuming `lock`, `someCondition`, and `updateState()` are already defined. No manual `unlock` call is needed. However, automatic lock release **does not roll back data** that was partially modified before the exception; business invariants must still be protected by code.

### 3.3. Reentrancy and differences between monitors

A thread holding monitor `m` can re-enter `synchronized(m)`. This is useful when a synchronized method calls another synchronized method on the same instance. However, nested acquisition of **two different monitors** can still deadlock if two threads acquire them in opposite orders.

### 3.4. Waiting to acquire a monitor

If thread A is holding a monitor, thread B attempting to enter the same `synchronized` will typically be in `Thread.State.BLOCKED`. `Thread.interrupt()` does not cause B to throw `InterruptedException` merely because it is waiting for the monitor. After A releases, B can enter even if its interrupt flag is set. Do not confuse this with `Object.wait()` inside a monitor: **`wait()` supports interruption** and has its own semantics.

## 4. What contract is `Lock`, and what does `ReentrantLock` add?

Core methods of `java.util.concurrent.locks.Lock`:

| Method | Meaning |
| --- | --- |
| `lock()` | Acquires the lock, possibly waiting; interrupt handling while waiting depends on the implementation contract. |
| `lockInterruptibly()` | Attempts to acquire the lock and allows exiting via `InterruptedException` when interrupted. |
| `tryLock()` | Attempts to acquire the lock immediately; returns `true` if acquired and `false` otherwise. |
| `tryLock(long time, TimeUnit unit)` | Waits up to the bounded time to acquire the lock; returns `true/false`; supports interruption. |
| `unlock()` | Releases the lock owned by the thread; with `ReentrantLock`, calling it from the wrong owner may throw `IllegalMonitorStateException`. |
| `newCondition()` | Creates a `Condition` object for coordination on the lock, if supported by the implementation. |

`ReentrantLock` provides a reentrant implementation and monitoring information such as `isLocked()`, `isHeldByCurrentThread()`, `getHoldCount()`, `hasQueuedThreads()`, and the ability to configure fairness at construction time. Some observation methods only reflect a **snapshot** and should not be used to build custom timing-dependent coordination algorithms.

**Not every object implementing `Lock` has all the characteristics of `ReentrantLock`.** Read the contract of the specific implementation before assuming it is reentrant, fair, or has similar waiting behavior.

### Mandatory safe idiom for explicit locks

```java
lock.lock();
try {
    updateSharedState();
} finally {
    lock.unlock();
}
```

This snippet assumes `lock` is a `Lock` and `updateSharedState()` is the operation to protect. `lock.lock()` is placed **before** `try`: if acquisition fails/throws, we do not `unlock` an unowned lock. After successfully acquiring the lock, the data modification sits inside `try` and releasing is always in `finally`.

**Critical bug:** calling `lock.lock()` followed by a `return` or exception before `unlock()` without `finally`. All other threads may wait indefinitely; the bug is harder to debug than `synchronized` because the JVM does not automatically release an explicit `Lock` at the end of a method.

## 5. Java 17 example: two counters, both correct, different lock management

Create file `MonitorVsLockCounter.java`:

```java
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

public class MonitorVsLockCounter {
    static class MonitorCounter {
        private int value;

        synchronized void increment() {
            value++;
        }

        synchronized int get() {
            return value;
        }
    }

    static class ExplicitCounter {
        private final Lock lock = new ReentrantLock();
        private int value;

        void increment() {
            lock.lock();
            try {
                value++;
            } finally {
                lock.unlock();
            }
        }

        int get() {
            lock.lock();
            try {
                return value;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        MonitorCounter monitor = new MonitorCounter();
        ExplicitCounter explicit = new ExplicitCounter();

        Runnable task = () -> {
            for (int i = 0; i < 10_000; i++) {
                monitor.increment();
                explicit.increment();
            }
        };

        Thread first = new Thread(task, "first");
        Thread second = new Thread(task, "second");
        first.start();
        second.start();
        first.join();
        second.join();

        System.out.println("monitor=" + monitor.get());
        System.out.println("lock=" + explicit.get());
    }
}
```

Run:

```bash
javac MonitorVsLockCounter.java
java MonitorVsLockCounter
```

Deterministic stdout:

```text
monitor=20000
lock=20000
```

Each worker runs `10_000` times; the two workers together produce `20_000` updates on each counter. `synchronized` and `ReentrantLock` protect the atomicity of `value++`, while `join()` ensures main waits for the workers to finish before reading. This is a **correctness example for atomicity and visibility**, **not a benchmark** of the speed of the two lock types. If a method reads `value` directly without using the same protocol, the class may no longer be thread-safe.

## 6. Strengths of `Lock`: try-locking and timeouts

With `synchronized`, a thread wanting to enter a monitor typically has to wait until it acquires it; there is no `synchronized.tryLock` or syntax to wait at most 200 ms. When business logic requires “if the lock cannot be acquired, return quickly, report busy, or take an alternative path,” `tryLock` is useful:

```java
if (lock.tryLock()) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} else {
    handleBusy();
}
```

This snippet assumes `lock`, `doWork`, and `handleBusy` exist. `tryLock()` does not wait long to contend for the lock. If using:

```java
if (lock.tryLock(200, TimeUnit.MILLISECONDS)) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
} else {
    handleTimeout();
}
```

This snippet must be inside a method that handles `InterruptedException` and requires importing `java.util.concurrent.TimeUnit`. Timed `tryLock` may wait up to the deadline and then return `false` if not acquired; actual timing also depends on the scheduler. If interrupted while waiting, it can throw `InterruptedException`; you must propagate it or restore the interrupt flag according to your cancellation policy.

### Runnable Java 17 example: trying to lock while another thread holds it

Create `TryLockExample.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

public class TryLockExample {
    public static void main(String[] args) throws Exception {
        ReentrantLock lock = new ReentrantLock();
        CountDownLatch acquired = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread holder = new Thread(() -> {
            lock.lock();
            try {
                acquired.countDown();
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
            }
        });

        holder.start();
        try {
            if (!acquired.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Holder did not acquire");
            }

            boolean immediate = lock.tryLock();
            if (immediate) {
                lock.unlock();
            }
            System.out.println("immediate=" + immediate);

            boolean timed = lock.tryLock(50, TimeUnit.MILLISECONDS);
            if (timed) {
                lock.unlock();
            }
            System.out.println("timed=" + timed);
        } finally {
            release.countDown();
            holder.join();
        }

        lock.lockInterruptibly();
        try {
            System.out.println("afterRelease=true");
        } finally {
            lock.unlock();
        }
    }
}
```

```bash
javac TryLockExample.java
java TryLockExample
```

Stdout when the program completes normally:

```text
immediate=false
timed=false
afterRelease=true
```

Main only starts attempting to acquire the lock after `holder` signals it has acquired `lock` via the `acquired` latch. Holder only releases after main opens `release` in `finally`, so **neither immediate nor timed tryLock succeeds** on the normal execution path. After `holder.join()`, the lock has been released; main acquires it successfully with `lockInterruptibly()` and prints the last line.

The `50 ms` timeout here is an API illustration, not an exact 50 ms benchmark. In tests/production, adjust the deadline to the environment, handle interrupts, and do not rely on a `sleep` to “hope” the holder is holding the lock. Two latches give us explicit coordination ordering.

### When is `lockInterruptibly()` needed?

If a thread has started waiting for a lock but the user's request is cancelled or the application is shutting down, `lockInterruptibly()` allows the lock wait to abort on interrupt. When interrupted while waiting, the method throws `InterruptedException` and does not return as if it acquired the lock. The caller must not `unlock()` if acquisition did not succeed.

Regular `ReentrantLock.lock()` does not use `InterruptedException` as a return path while contending for the lock; if controlled cancellation is needed, choose `lockInterruptibly()` or timed `tryLock`. Once the lock **has** been acquired, an interrupt does not automatically release the thread's lock: code is still responsible for releasing it in `finally`.

## 7. `Condition` vs. `Object.wait/notifyAll`

**Mutual exclusion** answers “who is allowed to enter the critical section?”. **Condition waiting** answers “when a business condition is not yet met, how does the thread holding the lock temporarily release it so others can change the condition?”. Both intrinsic monitors and explicit `Lock` support waiting mechanisms, but their APIs differ.

### 7.1. With an intrinsic monitor

A producer/consumer waiting on the `monitor` itself:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    consume();
}
```

This is a snippet assuming `ready` and `consume()` are protected by `monitor`. `wait()` requires the caller to own **the monitor of the object on which `wait` is called**, otherwise it throws `IllegalMonitorStateException`. While waiting, `wait()` releases that monitor; after being awakened, the thread must **re-acquire the monitor** before `wait()` returns.

The producer uses:

```java
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
```

`notifyAll()` wakes up waiters belonging to the monitor's wait set; it does not immediately hand the monitor over to a waiter. The producer still holds the monitor until leaving the synchronized block. Waiters must use **`while`** to re-check the predicate due to spurious wakeups, multiple consumers, or the predicate changing before it re-acquires the lock.

### 7.2. With `Lock` and `Condition`

`ReentrantLock.newCondition()` returns a `Condition` bound to the explicit lock:

```java
lock.lock();
try {
    while (!ready) {
        readyCondition.await();
    }
    consume();
} finally {
    lock.unlock();
}
```

Producer:

```java
lock.lock();
try {
    ready = true;
    readyCondition.signalAll();
} finally {
    lock.unlock();
}
```

These are two snippets in the same class assuming `lock` is a `ReentrantLock`, `readyCondition = lock.newCondition()`, and `ready/consume` use the same lock; requires importing `java.util.concurrent.locks.Condition` and `ReentrantLock`. `await()` may only be called when the caller holds the associated lock; it **releases the lock while waiting and re-acquires it before returning**. `signal()`/`signalAll()` require holding the corresponding lock for `ReentrantLock.ConditionObject`, otherwise they throw `IllegalMonitorStateException`.

**A Condition is not another mutex:** it is a **condition wait queue** associated with the lock. The same lock can create two different conditions such as `notEmpty` and `notFull`, whereas an intrinsic monitor has a single default wait set.

### 7.3. `await` is not like `sleep`

| Operation | Releases the held lock to wait? | Receives signals? |
| --- | --- | --- |
| `Object.wait()` | Releases the monitor of the `wait` target object | `notify/notifyAll`, interrupt, spurious wakeup |
| `Condition.await()` | Releases the **associated Lock**, then re-acquires it before returning | `signal/signalAll`, interrupt, spurious wakeup |
| `Thread.sleep(ms)` | **Does not automatically release** held monitor or `Lock` | Can time out or be interrupted |
| `LockSupport.park()` | **Does not automatically release** held monitor/`Lock` | Permit from `unpark`, interrupt, spurious return |

If you sleep while holding a lock and wait for another thread to change the predicate under the same lock, the other thread cannot enter to modify the data. `wait/await` is designed to temporarily release the lock to give state a chance to progress.

## 8. Java 17 example: one lock, two conditions `notEmpty` and `notFull`

A “single-slot buffer” stores only one element at a time. Producers must wait when the buffer is full; consumers must wait when the buffer is empty. `ReentrantLock` allows two separate wait queues to signal the right group:

Create `ConditionBufferExample.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionBufferExample {
    static class OneSlotBuffer {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private Integer item;

        void put(int value) throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (item != null) {
                    notFull.await();
                }
                item = value;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        int take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (item == null) {
                    notEmpty.await();
                }
                int result = item;
                item = null;
                notFull.signal();
                return result;
            } finally {
                lock.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        OneSlotBuffer buffer = new OneSlotBuffer();
        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<Integer> consumer = pool.submit(buffer::take);
            Future<Void> producer = pool.submit(() -> {
                buffer.put(42);
                return null;
            });

            producer.get(5, TimeUnit.SECONDS);
            int received = consumer.get(5, TimeUnit.SECONDS);
            System.out.println("received=" + received);
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Compile/run:

```bash
javac ConditionBufferExample.java
java ConditionBufferExample
```

Stdout when the program completes normally:

```text
received=42
```

**Analysis:**

1. If the consumer arrives first, it acquires `lock`, sees `item == null`, and calls `notEmpty.await()`: **releases the lock** and waits.
2. The producer acquires the lock, sets `item = 42`, calls `notEmpty.signal()`, and releases the lock. After re-acquiring the lock, the consumer checks the predicate again and reads 42.
3. If the producer arrives first, `item` already has 42 when the consumer arrives; the consumer does not need to `await()`. Both orderings produce the same result.
4. `notFull` becomes useful when a subsequent producer arrives while the slot is full. The example only has one item, so the `notFull` wait path does not necessarily occur, but the code implements both conditions.
5. `producer.get` and `consumer.get` propagate exceptions from tasks back to main while waiting for results. A timeout in the caller does not itself guarantee the task has stopped; `shutdownNow()` attempts to interrupt workers if they have not finished.

Because `Integer` is used as the marker for data presence/absence, `null` is reserved for the empty state; if the problem allows null payloads, a separate `occupied` flag or another representation is needed. This is an educational example; in real applications consider `ArrayBlockingQueue`, which already encapsulates synchronization rules, bounds, and proper signaling.

**Why are two `Condition`s useful?** With a single intrinsic monitor, `notify()` might wake a waiter that cannot make progress (e.g., a producer while the buffer is still full), so simple implementations often use `notifyAll()` and re-check predicates. With `ReentrantLock`, `notEmpty.signal()` targets the consumer group, and `notFull.signal()` targets the producer group; you must still use `while` and hold the lock when signaling.

## 9. Monitor equivalent and when it is sufficient

If there is only one condition or low contention, an intrinsic monitor is often concise:

```java
class MonitorOneSlotBuffer {
    private Integer item;

    synchronized void put(int value) throws InterruptedException {
        while (item != null) {
            wait();
        }
        item = value;
        notifyAll();
    }

    synchronized int take() throws InterruptedException {
        while (item == null) {
            wait();
        }
        int result = item;
        item = null;
        notifyAll();
        return result;
    }
}
```

Java 17 class snippet without `main`. Here synchronized instance methods use `this`'s monitor. `wait()` and `notifyAll()` are implicitly called on `this` while the thread holds that monitor. Using `notifyAll` notifies waiters with different predicates as well, and then each thread **re-checks its own `while`**; this is a simple tradeoff but can wake up unnecessary waiters.

You should not convert every `synchronized` to `ReentrantLock` just because “Lock has more features.” If the problem is just a short critical section, a single lock with clear identity, and no need for timeouts or separate conditions, `synchronized` is usually easier to read and has less risk of forgetting to release the lock.

## 10. Java Memory Model guarantees

Locks protect **two things**: mutual exclusion at the critical section and memory synchronization between threads participating in the same protocol.

### 10.1. With monitors

A thread releasing (unlocking) monitor `M` happens-before the next lock of monitor `M`. Therefore:

```java
synchronized (monitor) {
    sharedValue = 42;
}
```

and later:

```java
synchronized (monitor) {
    System.out.println(sharedValue);
}
```

These snippets assume the same monitor and variable `sharedValue`, not a standalone program. If the reader genuinely acquires the monitor after the writer has released it and no other writer intervenes to modify it, it can see the write of 42 via memory synchronization. If **two different monitors** are used, there is no monitor-happens-before between them merely from using the same `synchronized` keyword.

### 10.2. With `Lock`

By the `Lock` contract, a successful `unlock` has the same memory synchronization effects as a monitor release; a successful `lock` has the same as a monitor acquisition. Therefore, callers do not need to add `volatile` to a regular field that is already protected on **all** read/write paths by the same `ReentrantLock`.

However: **`lock.tryLock()` returning `false` is not a successful acquisition**; it does not protect the critical section and must not be treated as “data is already synchronized.” Similarly, status methods like `isLocked()` do not replace actually acquiring the lock to read protected state.

### 10.3. With `wait` and `await`

When waiting, a thread releases the monitor/associated lock and later re-acquires it; together with the release/acquire relationship, this forms the publication mechanism from producer to consumer. **A signal only notifies**; the data predicate under the same lock is the source of truth to check. Do not trust “if there was a signal, the condition must still be true” because other waiters may have consumed the resource before the newly awakened thread re-acquires the lock.

### 10.4. Happens-before does not mean an atomic workflow

Example:

```java
if (stock > 0) {
    stock--;
}
```

If two threads are allowed to interleave between the check and the decrement, both can see the same old stock. Using a `volatile int stock` is not enough. Putting **both the check and the decrement** inside the same `synchronized`/`lock`, or using CAS on an atomic variable, is how to protect the invariant. Calling `join()` after a worker finishes lets main observe the result; it **cannot recover updates that were lost** earlier.

## 11. Fairness, starvation, and reentrancy

### 11.1. What does `ReentrantLock(true)` mean?

`new ReentrantLock(true)` requests a fairness policy: under lock contention, the implementation tends to favor the thread that has been waiting longer according to the lock's contract. However:

- It does not guarantee fairness at the **CPU scheduling** level or at every absolute moment of lock acquisition.
- The no-arg `tryLock()` can **barge** and acquire the lock if it is currently free, even for a fair lock with other threads queued.
- Fairness often has higher throughput/latency cost in many workloads; do not enable it unconditionally just because it sounds fair.
- If you need timed acquisition that respects fairness, read the exact semantics of `tryLock(timeout, unit)` for `ReentrantLock`.
- Fairness does not solve holding locks too long, deadlocks from multi-lock ordering, or external dependencies that never complete.

### 11.2. Reentrancy does not mean infinite or free

`ReentrantLock` allows the same thread to call `lock()` multiple times; each call increments the hold count. The thread must call `unlock()` **the same number of times it acquired** before another thread can enter. With `synchronized`, the monitor is also reentrant and nesting is managed by the JVM by scope.

Example:

```java
lock.lock();
try {
    lock.lock();
    try {
        // Same thread is holding the lock twice.
    } finally {
        lock.unlock();
    }
} finally {
    lock.unlock();
}
```

This snippet assumes `lock` is a `ReentrantLock`. If `unlock` is only called once, the hold count remains 1 and the lock is still owned by that thread. Therefore nested acquisition should be used thoughtfully; usually keep code to a simple discipline to avoid this bug.

### 11.3. Starvation and priority inversion

No mutex guarantees that business requests are always served fairly according to an SLA. When one thread holds a lock for a long time, other threads must wait; if the lock-holding thread is delayed by the scheduler or performs blocking I/O, overall system latency rises. A fair `ReentrantLock` can help reduce some unfair lock contention phenomena, but it is not a tool to solve all priority inversion or overloading.

## 12. Choosing `lockInterruptibly` and handling interruption

Another important difference between a monitor and `Lock` is **cancellation while still waiting for acquisition**:

| Situation | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Attempting to acquire the lock | Interrupt does not cancel intrinsic monitor acquisition | `lockInterruptibly()` can throw `InterruptedException` |
| Already holding the lock, thread is interrupted | Does not automatically release the monitor | Does not automatically release the explicit lock |
| Waiting on a condition | `Object.wait()` responds to interrupt with an exception | `Condition.await()` responds to interrupt per contract |
| Want to wait at most 250 ms to **acquire** the lock | No timed intrinsic monitor acquisition | `tryLock(250, TimeUnit.MILLISECONDS)` |
| Want to try immediately without waiting | No non-blocking monitor try-acquire in `synchronized` syntax | `tryLock()` |

**Do not confuse acquisition with condition waiting.** `Object.wait(timeout)` has a timeout, but it is only called **after the thread already owns the monitor**, to wait for a condition; it does **not** give entering `synchronized` a timeout. Similarly, `Condition.await(timeout)` differs from `lock.tryLock(timeout)`: the former waits on a condition while temporarily releasing the lock; the latter waits to acquire the lock.

When catching `InterruptedException` and not rethrowing it, typically restore the flag `Thread.currentThread().interrupt()` and exit the work path appropriately. Do not swallow the interrupt and loop forever. With `ReentrantLock.lockInterruptibly()`, if the method throws `InterruptedException` before returning normally, the caller **does not have the lock** and must not `unlock()` as if it did.

## 13. Thread dumps and observability tools

On HotSpot/OpenJDK, `jcmd <pid> Thread.print -l` or Java Flight Recorder can help inspect lock contention and waiting threads. Distinctions to note:

- A thread waiting for a `synchronized` **intrinsic monitor** usually shows `BLOCKED (on object monitor)`.
- A thread waiting for a `ReentrantLock` via `LockSupport.park`/`AbstractQueuedSynchronizer` can usually be in `WAITING` or `TIMED_WAITING`, depending on the method, timeout, and runtime.
- A thread waiting in `Object.wait()` on a monitor condition usually shows `WAITING`; waiting in `Object.wait(timeout)` usually shows `TIMED_WAITING`.
- A thread waiting in `Condition.await()` can also appear in the stack via `LockSupport`/`AbstractQueuedSynchronizer.ConditionObject`.
- Do not conclude there is a deadlock from a single `BLOCKED` or `WAITING` thread; look for lock cycles and owners, and inspect multiple snapshots, wait durations, and call paths.

Example command (substitute a real PID):

```bash
jcmd <PID> Thread.print -l
```

Do not include this command in the stdout of the Java programs above. Dump contents depend on the JDK, version, and observation time.

`ThreadMXBean` has APIs to detect certain deadlocks involving monitors and ownable synchronizers. It is useful when checking `synchronized` and `ReentrantLock`, but cannot prove the absence of business-level deadlocks involving DB/HTTP/queues or all other wait conditions.

## 14. Very common mistakes when switching from monitors to `Lock`

### 14.1. Forgetting to release an explicit lock

```java
lock.lock();
doWork();             // If this throws an exception, unlock is skipped.
lock.unlock();
```

Wrong when `doWork()` throws. Fix by using `try/finally` immediately after successful acquisition.

### 14.2. `unlock` when not holding the lock

```java
if (lock.tryLock()) {
    try {
        doWork();
    } finally {
        lock.unlock();
    }
}
```

Correct because `unlock` is only called if `tryLock` returns true. If `tryLock` is false or `lockInterruptibly` is interrupted before acquiring the lock, do not `unlock`. With `ReentrantLock`, another thread calling `unlock` throws `IllegalMonitorStateException`; there is no “unlocking on behalf of” the owner.

### 14.3. Mixing `synchronized(lock)` with `lock.lock()`

```java
ReentrantLock lock = new ReentrantLock();

// Thread A:
synchronized (lock) {
    update();
}

// Thread B:
lock.lock();
try {
    update();
} finally {
    lock.unlock();
}
```

This is a snippet illustrating two code paths, not a standalone runnable program. **The two do not protect each other:** path A acquires the *intrinsic monitor of the ReentrantLock object*, while path B acquires the *explicit ReentrantLock state*. Thus A and B can enter both regions concurrently even though they use the exact same reference variable named `lock`. Choose **one consistent mechanism** for all actors accessing the same state.

### 14.4. Using a condition with the wrong lock

```java
Condition condition = lock.newCondition();
// ...
condition.await();
```

If the caller is not holding the right `lock`, `ReentrantLock` will throw `IllegalMonitorStateException`. The same applies when signaling: you must hold the corresponding lock when calling `condition.signal()`/`signalAll()`. When there are two conditions from the same lock, both still protect the data with **that same lock**; conditions only partition the waiters into groups.

### 14.5. Using `if` instead of `while`

```java
if (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

Wrong because a spurious wakeup or another consumer might take the item before the newly awakened thread re-acquires the lock. Use:

```java
while (queue.isEmpty()) {
    notEmpty.await();
}
return queue.remove();
```

Both snippets assume `queue`, `notEmpty`, and that the lock is held. With condition waiting, **always tie waiting to a real predicate protected by the same lock**.

### 14.6. Signaling outside the critical section

Modifying the predicate and signaling must stay within a consistent lock protocol. Setting `ready` unsynchronized and calling `signal` outside the lock both violates `ReentrantLock`'s Condition contract and can miss signals or expose inconsistent data. Update state and signal **while holding the lock**; the awakened thread will still wait for the lock to be released.

### 14.7. Overly broad locks and I/O in the critical section

Placing HTTP/DB calls, `Thread.sleep`, or untrusted callbacks while holding a lock can make other threads wait a long time, increase tail latency, or deadlock when the callback acquires locks in a different order. Try to hold locks only for invariant state transitions; move I/O/callbacks outside if business logic allows. If you must hold a lock to preserve a transaction, set deadlines, control lock order, and design failure modes.

## 15. Lock ordering, deadlocks, and “exclusivity” does not mean “bug-free”

Suppose A acquires `lock1` then `lock2`, while B acquires `lock2` then `lock1`. Both can hold one lock and wait forever for the other. This happens with **both intrinsic monitors and `ReentrantLock`**. One policy to reduce deadlocks is to always acquire multiple locks in a **consistent global order**. When using `Lock` and logic permits, `tryLock(timeout)` can help detect/escape wait situations, though it does not automatically fix business invariants or guarantee liveness on retry.

Adding mutexes can also create **lock convoys** (many threads queuing behind a slow holder), contention, and throughput limits. Once correctness is protected, measure critical-section duration, queue wait, p95/p99, CPU, thread dumps/JFR, and prefer designs that reduce shared mutable state or partition ownership if needed.

**Do not rely on `Thread.sleep` to “wait for a lock to be released.”** In code already holding a lock, sleeping does not release it. Outside a critical section, sleep is still not a synchronization signal; use `Condition`, `BlockingQueue`, `CountDownLatch`, or another purpose-built contract.

## 16. Practical tool selection questions

| Requirement | Recommendation | Why |
| --- | --- | --- |
| Protect a simple counter/collection with a short critical section | `synchronized`; or an atomic class if it is a single operation | Concise, auto-releases lock, easy to review |
| Want to try immediately, without waiting if the resource is busy | `Lock.tryLock()` | Receives false and handles busy state |
| Want to bound the time **waiting to acquire the lock** | `Lock.tryLock(timeout, unit)` | Supports deadline at acquisition |
| Want to respond to interrupts while **contending for the lock** | `lockInterruptibly()` | Provides a cancellation path while waiting to acquire |
| Need two or more wait groups on the same state | `ReentrantLock` + multiple `Condition`s | `notEmpty`/`notFull`, avoids waking the wrong group |
| Only one simple condition, waiting on a predicate | `synchronized` + `wait/notifyAll` may suffice | No need to manage explicit unlock |
| Need more fairness under lock contention | Consider `ReentrantLock(true)` and measure in practice | Fairness has overhead, does not guarantee absolute CPU scheduling |
| Many readers, few writers on a large structure | Evaluate `ReadWriteLock` or an immutable snapshot | Can increase read concurrency, but more complex; not automatically better |
| Very simple single-variable data | `AtomicInteger`/`AtomicReference` | Specific operations can be atomic without a mutex |
| Standard producer–consumer queue | `BlockingQueue` | Built-in wait conditions and battle-tested thread-safe protocol |

**`ReadWriteLock`** is a different interface, with `readLock()` and `writeLock()` returning corresponding `Lock`s; it is **not automatically equivalent** to a single `Lock`. `StampedLock` is also a separate tool with a different API and contract, **not directly implementing `Lock`**. Do not switch designs just because a name sounds stronger; choose based on invariants, read/write paths, wait conditions, fairness, and actual load.

### Java 21+ and virtual threads

Virtual threads must still protect shared mutable state under the Java Memory Model just like platform threads. `synchronized`, `Lock`, and atomic classes still matter; virtual threads **do not make race conditions disappear on their own**. Blocking/pinning behavior of monitors/locks and runtime observability can differ across JDK versions; when deploying large numbers of virtual threads, measure with JFR/thread diagnostics on your actual JDK version. The lessons here use stable APIs runnable from Java 17.

## 17. Self-check exercises

**1. Do both `synchronized` and `ReentrantLock` guarantee visibility?** Yes, when readers/writers participate in **the same monitor or the same explicit lock** under the unlock→lock contract. Locking different objects creates no shared guarantee.

**2. Why should `lock.lock()` be placed before `try`?** `unlock()` must only be called after a successful acquisition. Placing acquisition inside `try` with `finally { unlock(); }` can cause finally to unlock when the lock is not held if acquisition throws.

**3. When a thread is waiting to acquire a `synchronized` monitor, does calling `interrupt()` make it exit waiting for the monitor and throw `InterruptedException`?** No. For interruptible acquisition, use `Lock.lockInterruptibly()` or timed `tryLock`. However, `Object.wait()` after entering the monitor does respond to interrupts.

**4. Does `wait(1000)` set a timeout for entering `synchronized`?** No. `Object.wait(1000)` is a timed condition wait after already owning the monitor; it releases the monitor while waiting and re-acquires it before returning.

**5. Is `synchronized (lock)` on a `ReentrantLock` object equivalent to `lock.lock()`?** No. The former acquires the object's intrinsic monitor; the latter uses the explicit lock state.

**6. Why must `while` be used around `Condition.await()`?** There can be spurious wakeups, contention among multiple consumers, or the predicate may have changed before the thread re-acquires the lock. Only a predicate re-checked under the lock determines whether to proceed.

**7. A buffer has two conditions `notFull` and `notEmpty`; are those two different mutexes?** No. They are two wait sets attached to **one ReentrantLock**, partitioning waiters into groups while the data is still protected under the same mutex.

**8. Should `ReentrantLock(true)` be enabled for every application?** No. Fairness has tradeoffs and does not guarantee absolute scheduling order. Start with correctness, monitor actual starvation/latency, and only enable it if requirements and measurements justify it.

**9. If `Lock.tryLock()` returns false, does that mean a subsequent read of mutable state is safe?** No. The caller does not own the lock; it must not enter the critical section or treat failure as a valid memory handoff.

**10. Once a thread calls `signal()`, does the waiter immediately run the code after `await()`?** No. The waiter must **re-acquire the lock** before `await` returns, and then re-check the predicate; signaling does not transfer mutex ownership by itself.

## 18. Checklist before choosing or reviewing

- **What invariant needs to be protected?** An increment, check–then–act, multiple fields, or a queue with conditions?
- **Is the lock identity correct?** Do all readers/writers use the same monitor or the same `Lock`, without accidentally mixing two lock types?
- **Are timeouts/interrupts needed when waiting for the lock?** If so, `Lock.tryLock`/`lockInterruptibly` are useful.
- **If using `Lock`, do all successful acquisition paths release via `finally`?** Are there any `return`/throw paths that forget to unlock?
- **If using `Condition`, is the predicate protected by the same lock, is `await` inside a `while`, and is signal called while holding the lock?**
- **If using `Object.wait`, does the caller hold the right monitor and re-check the condition after waking up?**
- **Is the lock held while doing I/O, sleeping, or calling untrusted callbacks?** Consider moving that work outside the critical section.
- **Are there multiple locks requiring a consistent acquisition order?** If there is a lock-order cycle, design to avoid deadlock.
- **Is fairness needed and have contention/throughput been measured?** Do not enable fair locks on gut feeling.
- **Do tests verify invariants and multiple interleavings?** Are there deadlines, cancellation, and worker error handling?
- **Using virtual threads?** You still must apply the JMM properly and benchmark on the actual JDK.

**Conclusion:** `synchronized` is the simple, scope-safe choice for monitor mutual exclusion and a single wait set bound to an object. `Lock`, especially `ReentrantLock`, adds control over acquisition (try-immediately, timeouts, interruptible), fairness, and multiple `Condition`s. Both only truly protect data when using **the right lock, the right invariant scope, and the right protocol on every access path**; choose based on concrete needs and measure concurrency consequences rather than blindly replacing one with the other everywhere.
