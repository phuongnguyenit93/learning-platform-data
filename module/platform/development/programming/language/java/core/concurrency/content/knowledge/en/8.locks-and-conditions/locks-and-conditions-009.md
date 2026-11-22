# ReentrantReadWriteLock: Lock Upgrading/Downgrading and Limitations in Java

In a multithreaded system, many operations only **read** the same state, whereas **write** operations require exclusivity to protect invariants. `ReentrantReadWriteLock` provides a pair of associated locks: `readLock()` for multiple readers to hold concurrently when no writer holds the lock, and `writeLock()` for a writer to have exclusive access. However, transitioning from read to write and from write to read is **asymmetric**: Java allows **write → read downgrading**, but **does not support read → write upgrading** while still holding the read lock.

This lesson belongs to the **Locks & Conditions** section, covering **general Java concurrency**, applicable to **Java 17+** and the standard API in `java.util.concurrent.locks`. It does not use any Spring-specific mechanisms.

After this lesson, you will:
- Know when to use a read lock, a write lock, and why an invariant and a locking protocol are still required.
- Understand the meaning of **reentrancy**, read/write ownership, and the number of locks that must be released.
- Prove why attempting to upgrade read → write can block itself indefinitely; know the **release read → acquire write → recheck condition** pattern.
- Perform **downgrading** in the exact order **write.lock → read.lock → write.unlock**, then continue reading and release the read lock.
- Understand the limitations: fairness, `tryLock`, conditions, interrupts, performance measurement, avoiding starvation/deadlock, and how to review code.

## 1. ReadWriteLock and Two Types of Access Rights

`java.util.concurrent.locks.ReadWriteLock` is an interface with two methods:

~~~java
Lock readLock();
Lock writeLock();
~~~

`ReentrantReadWriteLock` is a **reentrant** implementation that supports a **nonfair** policy (default) or a **fair** policy (specified via the constructor). Both locks belong to the **same structure** and coordinate read/write access on the **same protected state**.

| Current state | Request read lock | Request write lock |
| --- | --- | --- |
| No one holds the lock | Can acquire, depending on fairness policy/queue | Can acquire, depending on fairness policy/queue |
| One or more readers hold the lock | Other readers can read concurrently if policy allows | Other writers must wait for all readers to release |
| One writer holds the lock | Other readers must wait | Other writers must wait |
| **The same thread** holds the write lock | Can reenter write and additionally acquire read lock | Can reenter write lock |
| **The same thread** only holds the read lock | Can reenter read lock | **Cannot upgrade directly to write lock** |

The "can" cells must account for fairness, whether a writer is waiting, and interrupt status; a read lock is not a guarantee that a reader will always enter immediately when another reader is holding it.

Two core principles:

1. **Read-side concurrency:** multiple readers can enter the read-only section concurrently when no other writer holds the write lock.
2. **Write-side exclusion:** a writer holding the write lock excludes other readers/writers from the protected state, but only when **every access path** follows the same lock pair.

Separating read/write is an access-coordination decision. It **does not create invariants by itself**, does not turn mutable data into immutable data, and does not protect read/write operations performed outside the lock.

### 1.1. Memory visibility

According to the `ReadWriteLock` contract, the memory synchronization effects of the write lock apply to the corresponding read lock: a reader that successfully acquires the read lock must see updates published by the preceding write lock release under the locking protocol. Therefore, protected fields can be kept as normal fields instead of `volatile` when **all** appropriate operations use the proper lock.

However, memory visibility **does not replace mutual exclusion**: if a read–check–update operation needs to be atomic as a single unit, the write lock must be acquired for the entire action.

## 2. Example: Concurrent Reads, Exclusive Writes

On Java 17, use `java.util.concurrent.locks.ReentrantReadWriteLock` with two handles:

~~~java
private final ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
private final Lock read = rw.readLock();
private final Lock write = rw.writeLock();
~~~

This is an **illustrative** field snippet, not a standalone Java file. Remember to declare the lock as `private final` so as not to expose internal synchronization capabilities to callers outside the class.

### Java 17+ example: two readers actually holding the lock concurrently

Use latches to observe **exact two readers holding the read lock at the same time**, rather than relying on non-deterministic sleep durations.

~~~java
// ConcurrentReadersDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ConcurrentReadersDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable reader = () -> {
            rw.readLock().lock();
            try {
                entered.countDown();
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                rw.readLock().unlock();
            }
        };

        Thread first = new Thread(reader, "reader-1");
        Thread second = new Thread(reader, "reader-2");
        first.start();
        second.start();

        entered.await();
        System.out.println("Readers holding: " + rw.getReadLockCount());
        release.countDown();

        first.join();
        second.join();
        System.out.println("Readers after: " + rw.getReadLockCount());
    }
}
~~~

~~~bash
javac ConcurrentReadersDemo.java
java ConcurrentReadersDemo
~~~

Stdout:

~~~text
Readers holding: 2
Readers after: 0
~~~

When `main` completes `entered.await()`, both readers have acquired the read lock and are waiting on `release` before they can unlock. Therefore, the value 2 at the print point is deterministic. After releasing the latch and calling `join` on both threads, no one holds the read lock anymore, so the result is 0.

**Note:** `getReadLockCount()` is an observation/monitoring API; it should not be used as a condition to determine the correctness of an application's synchronization protocol. The example uses latches to pin an illustrative state, not relying on querying the reader count to perform updates.

### Lock/unlock rules

~~~java
read.lock();
try {
    // Only read the protected data.
} finally {
    read.unlock();
}

write.lock();
try {
    // Read, check, and modify invariants.
} finally {
    write.unlock();
}
~~~

These are **illustrative snippets**, assuming `read` and `write` are already declared. The `unlock` operation must be performed by the thread that currently owns the corresponding lock holds. `ReentrantReadWriteLock` counts hold acquisitions (reentrancy); every successful `lock` must be balanced by one `unlock`. Unlocking with wrong ownership may throw `IllegalMonitorStateException`.

## 3. Read → Write Upgrading: Not Supported

A common scenario: a thread reads a cache under a read lock, detects that the cache is missing/expired, and wants to **keep the read lock and request the write lock** to update it. This does not work.

~~~java
// DO NOT use this approach; illustrative code may block itself indefinitely.
rw.readLock().lock();
try {
    if (cacheNeedsRefresh()) {
        rw.writeLock().lock(); // Waits indefinitely if the thread still holds the read lock.
        try {
            refreshCache();
        } finally {
            rw.writeLock().unlock();
        }
    }
} finally {
    rw.readLock().unlock();
}
~~~

Here `cacheNeedsRefresh()` and `refreshCache()` are illustrative names, **not built-in Java APIs**; this snippet is not a standalone runnable file.

### 3.1. Why can it self-deadlock even with only one reader?

Thread T currently holds the read lock. To acquire the write lock, no reader may be holding the read lock (except when the owner thread already holds the write lock and then acquires the read lock). Thread T is itself the very reader preventing the writer from being granted access; yet T's code waits for `write.lock()` to return **before releasing the read lock**. It blocks its own progress.

~~~text
Thread T:
  read.lock()   -> already holds read
  write.lock()  -> waits for all read holders to release read
  read.unlock() -> placed after write.lock(), never reached

=> Self-deadlock / lock conversion wait that can never complete.
~~~

This point **is not fixed by fairness=true**, nor by `volatile` or changing the `finally` order. The fact that `ReentrantReadWriteLock` is **reentrant** only means a thread can reenter locks in the supported directions; it **does not** have an upgrade mode for a single reader.

### 3.2. Verifying with tryLock without hanging the program

~~~java
// UpgradeAttemptDemo.java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class UpgradeAttemptDemo {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();

        rw.readLock().lock();
        try {
            boolean upgraded = rw.writeLock().tryLock();
            System.out.println("Upgrade while holding read: " + upgraded);
            if (upgraded) {
                rw.writeLock().unlock();
            }
        } finally {
            rw.readLock().unlock();
        }

        boolean acquired = rw.writeLock().tryLock();
        System.out.println("Acquire after release: " + acquired);
        if (acquired) {
            rw.writeLock().unlock();
        }
    }
}
~~~

~~~bash
javac UpgradeAttemptDemo.java
java UpgradeAttemptDemo
~~~

Stdout:

~~~text
Upgrade while holding read: false
Acquire after release: true
~~~

Even with no other threads present, `tryLock()` on the write lock returns `false` while the caller only holds the read lock. After releasing the read lock, the caller acquires the write lock successfully in this single-threaded program.

**Do not use `write.lock()` to intentionally experiment with self-deadlock**: the program will hang and may need to be terminated externally. For an incorrect upgrade protocol in a real application, inspect thread dumps and hold counts/stack traces to find where a thread attempts to acquire write while still holding read.

## 4. Replacing Upgrade with Release Read → Acquire Write → Recheck

If you need "read first, only modify if there is an issue", the correct pattern is:

1. Acquire the read lock to observe the state.
2. If an update is needed, **release all read holds belonging to the caller** before requesting the write lock.
3. Acquire the write lock.
4. **Recheck the condition** because another thread may have updated the state after the read lock was released.
5. If still needed, perform the update under the write lock, then release the write lock.
6. If you need to continue reading the protected state, reacquire the read lock or use downgrading as in the next section.

Because there is a gap between releasing read and acquiring write, you must not treat the initially read data as proof that the condition still holds.

### Example: once-initialized cache

~~~java
// CacheInitializationDemo.java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class CacheInitializationDemo {
    static final class Cache {
        private final ReentrantReadWriteLock rw =
            new ReentrantReadWriteLock();
        private String value;
        private int rebuildCount;

        String get() {
            rw.readLock().lock();
            try {
                if (value != null) {
                    return value;
                }
            } finally {
                rw.readLock().unlock();
            }

            // Gap: another thread may initialize the cache here.
            rw.writeLock().lock();
            try {
                if (value == null) { // MUST recheck.
                    value = "ready";
                    rebuildCount++;
                }
                return value;
            } finally {
                rw.writeLock().unlock();
            }
        }

        int rebuildCount() {
            rw.readLock().lock();
            try {
                return rebuildCount;
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Cache cache = new Cache();
        Thread a = new Thread(cache::get, "A");
        Thread b = new Thread(cache::get, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Value: " + cache.get());
        System.out.println("Rebuilds: " + cache.rebuildCount());
    }
}
~~~

~~~bash
javac CacheInitializationDemo.java
java CacheInitializationDemo
~~~

Stdout:

~~~text
Value: ready
Rebuilds: 1
~~~

Even though A and B may concurrently see `value == null` while holding the read lock, after releasing read they must contend for the write lock one at a time. The thread that receives the write lock first sets `"ready"`; the next thread **rechecks** and does not rebuild the data. `rebuildCount++` only runs when `value` is still null inside the write lock.

**Mistake:** only checking `if (value == null)` under the read lock, releasing read, and writing immediately under write **without rechecking**. This can perform redundant update computations, overwrite a newer version, or execute side effects twice. If rebuilding the cache involves time-consuming I/O, consider a separate ownership/synchronization design and avoid holding the write lock for too long; you cannot simply omit the recheck for optimization.

### Difference from a true upgrade

The pattern above **is not an atomic upgrade**: between the two lock acquisitions, other threads are free to change the state. Thanks to the recheck, we preserve the update condition inside the write lock; however, we do not preserve the exact snapshot observed under the read lock. If business logic requires transitioning read→write without losing access in between, the protocol must be redesigned (for example, acquiring write from the start, CAS on immutable state, or another primitive with an appropriate conversion contract).

## 5. Write → Read Downgrading: Supported

**Downgrading** means a thread holding the write lock wants to transition to **continuing stable reads** without letting another writer cut in between releasing write and acquiring read. `ReentrantReadWriteLock` supports this in the following order:

~~~text
(1) write.lock()       -- thread has exclusive write access
(2) update state       -- update data
(3) read.lock()        -- the writer itself acquires read as well
(4) write.unlock()     -- release write access, still holding read
(5) read state         -- other writers cannot modify while read is held
(6) read.unlock()      -- release read access
~~~

Step **(3) must come before step (4)**. If you release write before acquiring read, another writer can win the write lock and modify the data; in that case, observing the exact version just written is no longer guaranteed.

### 5.1. Complete Java 17+ example

~~~java
// DowngradeDemo.java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class DowngradeDemo {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        int[] data = {0}; // Only to demo shared data.

        rw.writeLock().lock();
        try {
            data[0] = 42;
            rw.readLock().lock(); // Writer is allowed to acquire the read lock.
        } finally {
            rw.writeLock().unlock();
        }

        // At this point, the thread holds read and no longer holds write.
        try {
            System.out.println("Value under read lock: " + data[0]);
            System.out.println(
                "Read holds: " + rw.getReadHoldCount());
            System.out.println(
                "Write holds: " + rw.getWriteHoldCount());
        } finally {
            rw.readLock().unlock();
        }

        System.out.println("Read holds after: " + rw.getReadHoldCount());
    }
}
~~~

~~~bash
javac DowngradeDemo.java
java DowngradeDemo
~~~

Stdout:

~~~text
Value under read lock: 42
Read holds: 1
Write holds: 0
Read holds after: 0
~~~

Within the same thread, after `rw.readLock().lock()` and `rw.writeLock().unlock()`, the read hold remains. `getReadHoldCount()` returns the number of read holds of the calling thread itself, unlike `getReadLockCount()` which measures the total read holds on the lock structure. `getWriteHoldCount()` is the number of reentrant write holds of the calling thread.

The demo uses a single thread for easy observation, but the downgrade order also holds with multiple threads: another writer cannot acquire the write lock while the read lock is still held. The hold count methods are for monitoring/diagnostics, **not primitives for deciding synchronization protocols**.

### 5.2. Proper exception handling with two locks

If real-world code is complex, acquiring the read lock while holding write and releasing each lock in different scopes can easily introduce bugs:

- If the read lock has not been acquired yet when write is released, do not assume the caller holds read.
- If the read lock has been acquired, there must be a corresponding `finally` block to release read when no longer needed.
- If holding multiple write holds due to reentrancy, all write holds must be released before write access is actually relinquished.
- Do not transfer lock ownership to another thread; the thread that acquires a lock is responsible for releasing the corresponding lock.

You can encapsulate the state transition in a tested internal abstraction rather than having multiple callers reproduce the downgrade sequence manually.

## 6. Combining Double-Check with Downgrade for a Cache

A common use case: read the cache; if invalid, request write access to refresh it; then continue processing the data under the read lock.

~~~text
read.lock
  cache valid? -- yes --> use under read --> read.unlock
       |
       no
       v
read.unlock
write.lock
  recheck valid? -- no --> refresh
  read.lock (downgrade)
write.unlock
  use under read
read.unlock
~~~

The following snippet is an **illustrative code pattern** in a class with fields `ReentrantReadWriteLock rw`, `boolean valid`, and `Object data`. Assume `refresh()` produces the data readers need; this is not a standalone Java file.

~~~java
Object useCache() {
    rw.readLock().lock();
    try {
        if (valid) {
            return data;
        }
    } finally {
        rw.readLock().unlock();
    }

    rw.writeLock().lock();
    try {
        if (!valid) { // Condition must be rechecked.
            data = refresh();
            valid = true;
        }
        rw.readLock().lock(); // Acquire read before releasing write.
    } finally {
        rw.writeLock().unlock();
    }

    try {
        return data;
    } finally {
        rw.readLock().unlock();
    }
}
~~~

This approach **downgrades in the right direction** and prevents other writers from cutting in between refreshing and starting to read the new version. If `refresh()` throws an exception **before acquiring the read lock**, the `finally` block releases write and the exception propagates; execution will not reach the final read block. For complex tasks, consider whether the mutable `data` value can be modified outside the lock: returning a reference and using it after releasing the read lock may no longer provide a stable snapshot if the object continues to be modified by writers. You can return an immutable copy, copy the data under the lock, or keep all processing that requires consistency entirely within the read lock's scope.

**Subtle point:** the method above returns the reference inside the `try` block, but `finally` releases the read lock before the caller receives and uses the object. If the caller needs to access multiple mutable properties consistently afterward, simply returning the reference **is not enough**; an immutability contract or a copy is required.

## 7. Reentrancy Is Not Upgrading

`ReentrantReadWriteLock` allows the same thread to:

- While holding **read**, call `read.lock()` again and `unlock()` the exact same number of times.
- While holding **write**, call `write.lock()` again, incrementing the write hold count.
- While holding **write**, additionally acquire **read**; this is the basis of downgrading.

It **does not allow** a thread holding only read to upgrade to write. Even if it believes it is "the only reader", requesting write can still hang because of that thread's own read hold.

Do not apply the intuition "ReentrantLock lets the same thread reacquire the lock" to a **read → write** transition: these two access modes are different.

### When the same thread holds both read and write, are other writers allowed to run?

No. While the owner thread holds write, other readers/writers are blocked. Once the owner thread releases all write holds while keeping read, other readers may enter concurrently (depending on fairness), while other writers still cannot modify the data. This shift in access is what gives downgrading its purpose.

### Why must you release the exact number of times?

Illustrative example:

~~~java
rw.writeLock().lock();
rw.writeLock().lock();
try {
    // Write hold count = 2 in the same thread.
} finally {
    rw.writeLock().unlock();
    rw.writeLock().unlock();
}
~~~

If one `unlock` is omitted, the thread still holds the write lock and can block all other readers/writers, creating a hard-to-detect liveness bug. This snippet is not a standalone file; `rw` is assumed to be declared.

## 8. Fairness, tryLock, and Starvation Risk

### 8.1. Two modes

~~~java
ReentrantReadWriteLock nonfair = new ReentrantReadWriteLock();
ReentrantReadWriteLock fair = new ReentrantReadWriteLock(true);
~~~

**Nonfair (default):** acquisition order is not guaranteed; throughput is usually higher, but under continuous contention, readers or writers can be delayed for a very long time, or even indefinitely.

**Fair:** the JDK applies an **approximately arrival-order** policy for contending threads, grouping readers and writers based on whoever has been waiting the longest. Fair mode can reduce starvation risk, but incurs additional overhead and **does not guarantee OS scheduler fairness**, nor does it provide a specific deadline for every task.

Important: **`readLock().tryLock()` and `writeLock().tryLock()` do not honor the fair policy** in the normal queued way; they can immediately acquire the lock if available, even if threads are waiting (barging). When you need to honor fairness while attempting a non-blocking acquisition, the `tryLock(0, TimeUnit.SECONDS)` overloads have the corresponding semantics and handle interrupts.

### 8.2. Do not choose a lock solely by the fair label

Factors to measure:
- Read/write ratio, hold duration of each lock, contention level.
- Amount of work inside the critical section.
- Do tasks need a deadline? `tryLock(timeout, unit)` or `lockInterruptibly()` can be useful.
- Tail latency, writer starvation risk, overhead from switching or rechecking.

A read/write lock can be slower than `synchronized` or a regular `ReentrantLock` if the critical section is very small, the number of readers is low, writes are frequent, or contention is high. The advantage of concurrent readers is only worthwhile when **reads are frequent enough and the work under the read lock is substantial enough**.

### 8.3. Interrupts and timeouts

Both `readLock()` and `writeLock()` support `lockInterruptibly()`/`tryLock(timeout, unit)`. Never call `unlock()` if the lock was not acquired:

~~~java
// Illustrative code: write is a declared Lock.
if (write.tryLock(100, java.util.concurrent.TimeUnit.MILLISECONDS)) {
    try {
        // Perform update.
    } finally {
        write.unlock();
    }
} else {
    // Timed out without acquiring the write lock.
}
~~~

The method in the illustrative snippet must declare or handle `InterruptedException`. A timeout does not promise write access, so the caller must have a plan to cancel, retry, or report failure as needed.

## 9. Conditions: Supported Only by the Write Lock

An important difference from a standalone `ReentrantLock` is **Condition**:

~~~java
ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
Condition condition = rw.writeLock().newCondition(); // Valid.
rw.readLock().newCondition(); // UnsupportedOperationException.
~~~

In the snippet above, you need to import `java.util.concurrent.locks.Condition` when using it in a real file. A `Condition` created from the write lock has a condition contract similar to `ReentrantLock`; typically `await()`/`signal()` are only called while holding the associated write lock. `readLock().newCondition()` is **not supported**.

### Standalone example verifying the limitation

~~~java
// ConditionSupportDemo.java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ConditionSupportDemo {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        Condition valid = rw.writeLock().newCondition();
        System.out.println("Write condition created: " + (valid != null));

        try {
            rw.readLock().newCondition();
            System.out.println("Unexpected support");
        } catch (UnsupportedOperationException e) {
            System.out.println("Read condition unsupported");
        }
    }
}
~~~

~~~bash
javac ConditionSupportDemo.java
java ConditionSupportDemo
~~~

Stdout:

~~~text
Write condition created: true
Read condition unsupported
~~~

If you need a wait condition coordinating multiple readers/writers, clearly design the predicate and the lock owning the condition. When using `await()`, always recheck the predicate in a `while` loop because a thread can wake up before the condition is true; do not synchronize by waiting on a read lock condition, which does not exist.

## 10. Comparison with ReentrantLock, StampedLock, and Concurrent Collections

| Tool | Strengths | Caveats |
| --- | --- | --- |
| `ReentrantLock` | Simple mutual exclusion, reentrant, conditions, and multiple wait modes | Does not allow concurrent readers in the critical section |
| `ReentrantReadWriteLock` | Multiple concurrent readers, exclusive writer, **write→read downgrade** | **No read→write upgrade**, overhead/fairness/conditions |
| `StampedLock` (JDK 8+) | Read/write stamps, optimistic reads, some `tryConvertToWriteLock`/`tryConvertToReadLock` | **Not reentrant**; conversion can fail; optimistic read requires validation, do not treat stamps like regular monitors |
| `ConcurrentHashMap` | Provides concurrent map operations, some per-key atomic APIs | Caller's sequence of operations is not automatically atomic; multi-key reads/writes may need additional design |
| Immutable snapshot with atomic reference | Readers get an immutable version, writers swap reference atomically | Multi-writer update logic must use CAS; objects must be truly immutable |

**StampedLock is not a way to "enable upgrading" for ReentrantReadWriteLock.** It is a different primitive with a different contract. `tryConvertToWriteLock(stamp)` can fail when access cannot be converted; the caller must handle failure, including properly releasing the old stamp and potentially trying another strategy. `StampedLock` is also non-reentrant, and optimistic reads do not guarantee a valid snapshot unless verified with `validate`.

If the logic only needs a quick single read/write on a map, a collection's atomic API can be simpler than a coarse lock. However, the choice must be driven by **invariants**, not just the number of readers.

## 11. Common Mistakes

- **"If I'm the only reader, read.lock → write.lock works."** False: direct upgrading is not supported and can block itself indefinitely.
- **"Fair=true fixes the upgrade issue."** False: fairness does not change ownership/upgrade rules.
- **"Releasing read then acquiring write is an atomic upgrade."** False: another thread can modify the data in the gap, so rechecking is mandatory.
- **"write.unlock() followed by read.lock() is a safe downgrade."** False: another writer can cut in between the two calls.
- **"Reentrant means unlocking once after multiple locks."** False: you must balance the exact number of lock acquisitions.
- **"Only writers need locks; readers can just read normal fields outside."** False: readers must follow the same protocol to observe valid data/snapshots.
- **"readLock.newCondition() works just like writeLock.newCondition()."** False: read condition throws `UnsupportedOperationException`.
- **"tryLock strictly obeys fair=true."** False for untimed `tryLock()`.
- **"ReadWriteLock is always faster than synchronized."** There is no guarantee; you must benchmark for your workload.
- **"getReadLockCount() is a primitive for deciding upgrades."** False: it is a monitoring metric and does not create atomic lock conversion.
- **"Once downgraded, no other reader can ever enter."** False: after releasing write while keeping read, other readers may be allowed to read concurrently (depending on policy); other writers still cannot write.
- **"Holding a lock while calling slow external code has no impact."** False: it can increase contention, latency, and deadlock risk.

## 12. Code Review Checklist

1. **Identify shared state and invariants:** caches, maps, counters, fields that must be read consistently.
2. **Mark read-only sections and write sections:** does any operation in a read section actually mutate a mutable object?
3. **Look for upgrade patterns:** does the code hold `readLock` and call `writeLock.lock`/`lockInterruptibly` or `tryLock`? If so, redesign to release read and recheck.
4. **Look for downgrade patterns:** is **read acquired before releasing write**? Is read finally released in a `finally` block?
5. **Check reentrant hold counts:** are there multiple locks with a missing unlock? Does the caller already hold a lock from an outer scope?
6. **Ensure all readers/writers use the same rw instance:** do not create a new lock per call or expose the lock reference in an API unintentionally.
7. **Check fairness and liveness:** nonfair has delay/starvation risk, fair has overhead, timed `tryLock` must handle timeouts/interrupts.
8. **Check Conditions:** only create conditions from the write lock, and check predicates in a `while` loop.
9. **Measure behavior:** compare throughput/latency against `ReentrantLock`/`synchronized` under realistic workloads; do not assume a read/write lock is better.
10. **Use thread dumps when stuck:** distinguish between a thread waiting to upgrade, a multi-lock deadlock, or normal contention.

## 13. Self-Check

**1.** Thread T holds the read lock and is the only reader. Will calling `writeLock().lock()` successfully upgrade?  
**Answer:** No. `ReentrantReadWriteLock` does not support read→write upgrading; the code may wait on itself indefinitely.

**2.** After detecting an invalid cache under the read lock, why must you recheck once the write lock is acquired?  
**Answer:** Because in the gap between releasing read and waiting for write, another thread may have refreshed the cache; the old condition is no longer reliable.

**3.** You need to immediately read the version you just wrote without letting another writer cut in. What is the correct order?  
**Answer:** `write.lock → update → read.lock → write.unlock → read → read.unlock`.

**4.** How do `rw.writeLock().newCondition()` and `rw.readLock().newCondition()` differ?  
**Answer:** The write lock supports `Condition`; the read lock throws `UnsupportedOperationException`.

**5.** With `new ReentrantReadWriteLock(true)`, does `tryLock()` strictly respect the fair policy?  
**Answer:** No. Untimed `tryLock()` can barge when the lock is available.

**6.** If there are only very short reads and frequent writes, is a read/write lock guaranteed to be faster than `synchronized`?  
**Answer:** No; the overhead of managing readers/writers may outweigh the benefit. Real-world benchmarking is required.

**7.** If a thread holds the write lock, acquires the read lock, and releases write, what access does that thread still hold?  
**Answer:** It still holds the read lock; it can continue reading. Other writers cannot update until all relevant read holds are released.

**8.** Does using `StampedLock.tryConvertToWriteLock` always succeed in upgrading?  
**Answer:** No. Conversion can return 0 when access cannot be changed; failure and stamp lifecycle must be handled properly.

**9.** One thread reads a `Map` without holding the read lock, while a writer updates it under the write lock. Is this thread-safe?  
**Answer:** No, if the map is mutable and there is no other synchronization protocol. Readers must obey the lock or use a collection/design with appropriate guarantees.

**Takeaway:** `ReentrantReadWriteLock` separates access into **multiple readers / single writer**. **Read→write upgrading is not supported**; releasing read and then acquiring write requires **rechecking**. **Write→read downgrading is supported**, but you must **acquire read before releasing write**. Correctness depends on invariants and every access path; performance, fairness, conditions, and reentrancy are the boundaries that must be verified.

### Standard References

- Java 17 `ReentrantReadWriteLock` (reentrancy, downgrading, fairness, conditions): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html
- Java 17 `ReadWriteLock` (memory consistency, sharing semantics): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html
- Java 17 `Lock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html
- Java 17 `StampedLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/StampedLock.html