# StampedLock with Optimistic Read in Java

## 1. The problem: frequent reads, infrequent writes, yet consistency is still required

Suppose many threads frequently read the coordinates of a point, while another thread occasionally updates both `x` and `y`. We want to reduce contention during reads, while avoiding reading `x` from a new update and `y` from an old update.

`java.util.concurrent.locks.StampedLock` is a JDK synchronization mechanism that supports **three modes**: *read lock*, *write lock*, and *optimistic read*. The distinctive feature is that an optimistic read **does not hold an actual read lock**. A reader obtains a **stamp**, reads the data into local variables, and then calls `validate(stamp)` to check whether a writer has invalidated the read. If validation fails, the reader must **re-read under an actual read lock** before using the result.

Standard pattern:

```java
long stamp = lock.tryOptimisticRead();
int localX = x;
int localY = y;

if (!lock.validate(stamp)) {
    stamp = lock.readLock();
    try {
        localX = x;
        localY = y;
    } finally {
        lock.unlockRead(stamp);
    }
}
// Only use localX, localY after the validate or fallback step.
```

This is an **illustrative snippet** inside a class that already has `lock`, `x`, and `y`, not a standalone program. The example section below provides complete classes with `main` to run on Java 17+.

### Benefits and limitations

- **Potential benefit:** when writers are rare, optimistic readers do not have to register a read lock acquisition and can reduce overhead/contention compared to a traditional read lock.
- **Limitation:** if a writer is currently modifying or has just modified the data, validation may fail; the reader must re-read and incur extra cost.
- **Not a silver bullet:** optimistic read does not automatically synchronize an entire object, does not block writers, does not guarantee always being faster, and does not grant access to an arbitrary mutable structure without checking.
- **Use only when speculative reading of the data is safe:** prefer primitive fields or carefully handled references, copy them into local variables, and **do not perform side effects based on unverified data**.

This is general Java concurrency knowledge using JDK APIs, not tied to any framework.

## 2. The three modes of `StampedLock`

| Mode | API to obtain stamp | What it guarantees | How to finish |
| --- | --- | --- | --- |
| **Write lock** | `writeLock()` | Excludes other writers and readers using a read lock; protects state updates | `unlockWrite(stamp)` |
| **Read lock** | `readLock()` | Multiple readers can hold it simultaneously; prevents writers from acquiring a write lock while held | `unlockRead(stamp)` |
| **Optimistic read** | `tryOptimisticRead()` | Obtains a version token to verify the read; **does not block writers** | `validate(stamp)`; **do not unlock an optimistic stamp** |

`StampedLock` uses a `long` value as a **stamp**. A stamp returned from lock operations is a **capability representing that lock acquisition**, not just a counter that the program is allowed to modify arbitrarily.

- `readLock()` and `writeLock()` may block until the lock is acquired; once successfully acquired, the caller must release the exact mode with the matching stamp.
- `tryOptimisticRead()` **does not block** waiting for a writer; it may return `0L` if a write lock is currently held.
- `validate(stamp)` returns `false` when the stamp is no longer valid according to the lock's synchronization state, including when the optimistic stamp is 0. A writer acquiring a write lock can invalidate an earlier optimistic stamp.
- Do not call `unlockRead` or `unlockWrite` with an optimistic stamp: it **does not represent a held lock**.

**An easy-to-miss rule:** a successful optimistic read does not mean the reader "holds" anything that blocks a writer. A writer can start updating at any time; the reader only accepts the copied values **after** stamp validation succeeds. Any subsequent access to shared state requires a new synchronization protocol.

## 3. Correct step-by-step optimistic read workflow

1. **Obtain a stamp:** `long stamp = lock.tryOptimisticRead()`. This is not `readLock()`.
2. **Speculatively read into locals:** read the required fields (e.g., `x`, `y`) and do not let those values drive side effects.
3. **Validate:** `lock.validate(stamp)` checks the validity of the optimistic read point. If a writer has invalidated the stamp, the speculatively read snapshot must not be used.
4. **Fallback:** when validation is `false`, acquire `readLock()`, re-read the fields **inside the critical section**, and call `unlockRead(stamp)` in `finally`.
5. **Use the snapshot:** after validation/fallback, use only the **captured local values**, or an immutable snapshot created from them. Do not continue reading shared fields outside the lock and treat them as part of the old snapshot.

**Typical mistake:** performing computations on shared fields **after** `validate`:

```java
// Conceptually wrong: recomputing from shared state after validate.
long stamp = lock.tryOptimisticRead();
int localX = x;
int localY = y;
if (lock.validate(stamp)) {
    return x + y; // Re-read x, y after validate.
}
```

This is an illustrative snippet without an enclosing method/class. After `validate`, a writer may have already started; the new read of `x`/`y` does not belong to the verified snapshot. Fix this with `return localX + localY` or by returning an immutable value built from **the verified locals**.

### Why must we keep locals?

If before `validate` a writer updates `x` and then `y`, the reader may temporarily observe an inconsistent combination. Failed validation requires **discarding** those locals and re-reading under the lock. If validation succeeds, the read is accepted according to `StampedLock`'s optimistic read protocol. Even if a writer arrives **immediately after** validation, the local snapshot still represents data read during a valid window; it does not need to reflect future updates.

Avoid deep dereferencing of a mutable object chain during an optimistic read: if references change concurrently, you may encounter a `NullPointerException`, an invalid index, or operate on an object being modified **even before reaching `validate`**. When state is complex, use an actual read lock or design immutable data that is safe to read speculatively.

## 4. Complete Java 17+ example: coordinates with an optimistic snapshot

Create the file `StampedPoint.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class StampedPoint {
    record Position(int x, int y) {}

    private final StampedLock lock = new StampedLock();
    private int x;
    private int y;

    public void moveTo(int newX, int newY) {
        long stamp = lock.writeLock();
        try {
            x = newX;
            y = newY;
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    public Position snapshot() {
        long stamp = lock.tryOptimisticRead();
        int localX = x;
        int localY = y;

        if (!lock.validate(stamp)) {
            stamp = lock.readLock();
            try {
                localX = x;
                localY = y;
            } finally {
                lock.unlockRead(stamp);
            }
        }
        return new Position(localX, localY);
    }

    public static void main(String[] args) {
        StampedPoint point = new StampedPoint();
        point.moveTo(4, 6);

        Position position = point.snapshot();
        System.out.println(position);
        System.out.println("Sum: " + (position.x() + position.y()));
    }
}
```

Compile and run:

```bash
javac StampedPoint.java
java StampedPoint
```

Deterministic output:

```text
Position[x=4, y=6]
Sum: 10
```

Explanation:

- `moveTo` acquires the write lock, updates **both fields** in the same critical section, and releases the lock in `finally`.
- `snapshot` obtains an optimistic stamp and captures `x` and `y` into locals. If the stamp has been invalidated by a writer, it falls back to a **read lock** to re-read consistently.
- The result is an immutable `record Position` over two primitive fields, without exposing mutable object state.
- The `main` example is sequential, so the output is fixed. In a concurrent program, a snapshot may reflect the coordinates before or after a `moveTo` call, but **a mixed x/y pair cannot be accepted** as long as all writers use the same `StampedPoint`'s write lock and readers follow the protocol above.

**Do not conflate "reading under a write lock" and "checking a stamp" into an assumption about speed:** only benchmarking your actual workload tells you whether optimistic reading is more effective than a regular `readLock`.

## 5. Java 17+ example: preserving an invariant under concurrent reads/writes

We have two internal balances with the invariant `left + right == 100`. A writer repeatedly transfers one unit from `left` to `right`; a reader repeatedly takes snapshots. A valid snapshot must never combine `left` from one transfer with `right` from another.

Create the file `StampedTransfer.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.StampedLock;

public class StampedTransfer {
    record Balances(int left, int right) {
        int total() {
            return left + right;
        }
    }

    private final StampedLock lock = new StampedLock();
    private int left = 100;
    private int right = 0;

    public void moveOne() {
        long stamp = lock.writeLock();
        try {
            if (left > 0) {
                left--;
                right++;
            }
        } finally {
            lock.unlockWrite(stamp);
        }
    }

    public Balances snapshot() {
        long stamp = lock.tryOptimisticRead();
        int observedLeft = left;
        int observedRight = right;

        if (!lock.validate(stamp)) {
            stamp = lock.readLock();
            try {
                observedLeft = left;
                observedRight = right;
            } finally {
                lock.unlockRead(stamp);
            }
        }
        return new Balances(observedLeft, observedRight);
    }

    public static void main(String[] args) throws InterruptedException {
        StampedTransfer book = new StampedTransfer();
        AtomicBoolean valid = new AtomicBoolean(true);

        Thread writer = new Thread(() -> {
            for (int i = 0; i < 100; i++) {
                book.moveOne();
            }
        }, "writer");

        Thread reader = new Thread(() -> {
            for (int i = 0; i < 5_000; i++) {
                if (book.snapshot().total() != 100) {
                    valid.set(false);
                }
            }
        }, "reader");

        writer.start();
        reader.start();
        writer.join();
        reader.join();

        System.out.println("Consistent snapshots: " + valid.get());
        System.out.println("Final balances: " + book.snapshot());
    }
}
```

Run:

```bash
javac StampedTransfer.java
java StampedTransfer
```

Output when both workers complete normally:

```text
Consistent snapshots: true
Final balances: Balances[left=0, right=100]
```

**Why does this example produce deterministic output despite non-deterministic scheduling?**

- Each `moveOne` holds the write lock from reading `left` until finishing the update to `right`, so neither another writer nor a read-lock reader can interleave during the modification.
- An optimistic reader may read between two writes; if a writer has started acquiring the write lock after the reader received its stamp, `validate` rejects that snapshot. The reader will **re-read both fields under the read lock**.
- The snapshot is `record Balances` containing two immutable integers; the `total` computation runs only on the two verified locals or values read under the read lock.
- The writer performs all 100 transfers starting from `left == 100`. Therefore, at the end `left == 0` and `right == 100`, regardless of scheduling.
- `join()` makes `main` wait for both workers. `AtomicBoolean` safely records whether an inconsistent snapshot was ever observed.

If a writer does not use **the same `StampedLock`**, the guarantee above no longer holds. A direct write to `left` or `right` that bypasses the lock breaks the contract even if the reader still calls `validate`.

**Scope:** this applies to state in **a single instance within a single JVM**. It does not by itself coordinate updates coming from another process/JVM or external service.

## 6. Why does `validate` matter for the Java Memory Model?

An optimistic read is **not the same** as a full read lock. During the speculative read phase, the reader holds no monitor or read lock to keep writers out. Reads of individual fields may observe values from different points in time.

`StampedLock`'s protocol uses stamps and validation to determine whether the read can be accepted or must fall back. Therefore:

- Only **capture the necessary values**, and do not publish them before validation.
- Do not rely on individual fields being atomic `int`s to conclude that the pair `(x, y)` is consistent.
- Do not allow writers to modify state **outside the write lock** of the same object.
- Do not perform side effects such as emitting events, deducting money, or updating maps based on **unvalidated** values.
- If validation fails, re-read **from scratch** under a read lock, rather than combining new fields with old ones.

With reference fields, reading a reference and then dereferencing a complex object can fail **before** reaching `validate` if the object is mutated and its internal structure is not safe. That is why the examples in this lesson intentionally use simple primitive fields and publish snapshots as immutable records.

`validate(stamp)` does not "freeze" state after returning `true`. Once validation succeeds, shared data can change again. **Only the captured local snapshot** is data you can use as the result of that read; an additional read from shared fields is a new operation and needs its own protection.

## 7. Optimistic read is not optimistic locking for every situation

It is easy to confuse different kinds of "optimistic":

1. **`StampedLock.tryOptimisticRead()`:** allows speculatively reading fields without holding a read lock, then uses `validate` to check whether the snapshot can be trusted. If not, re-read under a read lock.
2. **Optimistic update/CAS:** reads a value, prepares a new value, and uses `compareAndSet` to ensure the state has not changed before updating. This is a **conditional update**, different from verifying a read-only snapshot.
3. **Optimistic concurrency in storage systems:** may use versions or conditional updates at the source of truth; it is not automatically related to `StampedLock` stamps in the JVM.

**Never** do `tryOptimisticRead()` → `validate()` → and then mutate fields as if you had acquired a write lock. Another writer can step in right after `validate`, and an optimistic stamp itself **grants no write permission**. To modify protected state, you must acquire `writeLock()` (or convert from an existing lock via the proper API) and then **re-check the condition under the write lock**.

## 8. `StampedLock` is non-reentrant: a critical trap

Unlike the intrinsic monitor of `synchronized` and `ReentrantLock`, **`StampedLock` is not reentrant**.

Dangerous situation:

```java
// Dangerous snippet: the same thread already holds the write lock.
long stamp = lock.writeLock();
try {
    helper();
} finally {
    lock.unlockWrite(stamp);
}

// helper() calls lock.writeLock() again on the same lock.
```

This is a snippet illustrating a dangerous design, not a standalone runnable program. If `helper` calls `writeLock()` again while the current thread already holds the write lock, it can **block itself indefinitely**. `StampedLock` does not track an owner in a way that allows reentrancy.

Similar traps:

- Holding the write lock and calling a getter that acquires a read lock on the same `StampedLock`.
- Holding a read lock and calling a setter that requires a write lock without properly releasing/converting.
- Holding a read lock and waiting on a worker that needs the write lock to complete.
- Having an internal helper always acquire a lock even when the caller already holds a valid stamp.

**Design approach:** clearly separate public methods responsible for acquiring locks from private helpers that require the caller to already hold the lock. You can pass state/snapshots or operate directly inside the locked region, but you must specify the helper's preconditions. Never call back into public getters/setters that could self-block while a stamp is held.

## 9. Converting stamps with `tryConvertToWriteLock`

`StampedLock` supports attempting conversions between modes via `tryConvertToWriteLock(stamp)`, `tryConvertToReadLock(stamp)`, and `tryConvertToOptimisticRead(stamp)`, subject to stamp validity and lock state.

**Important:** `tryConvertToWriteLock(stamp)` can return **`0L` on failure**. Never assume conversion always succeeds. When it succeeds, you must use **the returned stamp** for subsequent operations; when it fails, **the original stamp is not automatically released**, and the caller must handle releasing or retrying according to its protocol.

Example scenario: ensure a cache is initialized exactly once. Start under a read lock to check `initialized`; if false, try converting to a write lock; if conversion fails, release the read lock, acquire the write lock, and **re-check the condition** because another thread may have initialized it during the lock handoff.

### Java 17+: one-time initialization using conversion with fallback

Create the file `StampedInitialize.java`:

```java
import java.util.concurrent.locks.StampedLock;

public class StampedInitialize {
    private final StampedLock lock = new StampedLock();
    private boolean initialized;
    private int value;
    private int initializationCount;

    public int getOrInitialize() {
        long stamp = lock.readLock();
        try {
            while (!initialized) {
                long writeStamp = lock.tryConvertToWriteLock(stamp);
                if (writeStamp != 0L) {
                    stamp = writeStamp;
                    value = 42;
                    initializationCount++;
                    initialized = true;
                    break;
                }

                lock.unlockRead(stamp);
                stamp = lock.writeLock();
                // Must re-check initialized once the write lock is acquired.
            }
            return value;
        } finally {
            lock.unlock(stamp);
        }
    }

    public int initializationCount() {
        long stamp = lock.readLock();
        try {
            return initializationCount;
        } finally {
            lock.unlockRead(stamp);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        StampedInitialize cache = new StampedInitialize();
        int[] results = new int[2];

        Thread a = new Thread(() -> results[0] = cache.getOrInitialize());
        Thread b = new Thread(() -> results[1] = cache.getOrInitialize());
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Values: [" + results[0] + ", " + results[1] + "]");
        System.out.println("Initialization count: "
                + cache.initializationCount());
    }
}
```

Run:

```bash
javac StampedInitialize.java
java StampedInitialize
```

Output when the program completes normally:

```text
Values: [42, 42]
Initialization count: 1
```

**Loop explanation:**

- If the read stamp converts to a write stamp successfully, that thread has permission to update and set `initialized = true`.
- If conversion fails, the thread releases the **read lock** first, then acquires the **write lock**. The gap between releasing and acquiring may allow another thread to initialize; therefore, `while (!initialized)` must be re-evaluated **after** acquiring the write lock.
- If the write lock has been acquired and `initialized` is still false, calling `tryConvertToWriteLock` with a valid write stamp allows continuing in write mode. If another thread has already initialized, the loop skips the write step.
- `lock.unlock(stamp)` in `finally` uses **the current stamp**, whether it is currently in read mode or write mode; the `unlock(stamp)` API supports releasing the lock according to the valid stamp of the held mode. Release only once per valid acquisition.

This is an intentional example to introduce conversion. When one-time initialization needs are simple, `synchronized` or an immutable holder may be easier to maintain. Conversion is not the default choice for every getter that might write.

## 10. Related read/write APIs and safe stamp usage

`StampedLock` also provides `tryReadLock()`, `tryWriteLock()`, timeout overloads, `readLockInterruptibly()`, and `writeLockInterruptibly()`. These APIs are for **acquiring an actual lock**; do not confuse them with `tryOptimisticRead()`, which obtains a lock-free read token.

Practical rules:

- **Lock acquisition returns a one-time stamp tied to the lock-holding lifecycle.** Do not cache stamps long-term to reuse after releasing.
- `unlockRead(stamp)` is only for a held read stamp; `unlockWrite(stamp)` is only for a held write stamp. Using an invalid or mismatched stamp can throw `IllegalMonitorStateException`.
- `unlock(stamp)` works with a valid held read or write stamp, but **must not** be used to release an optimistic stamp.
- Do not use stamps as business version numbers, transaction IDs, or cross-process security tokens.
- `StampedLock` does not track ownership the way `ReentrantLock` does; passing stamps across threads is not like a thread-owned reentrant lock at the API level. Unless a design truly requires it and is thoroughly verified, keep the component that acquires the lock responsible for releasing it in a clear `try/finally` block.
- If a thread is interrupted while holding a lock, the lock **is not automatically released**; the code must ensure `finally` runs. Interruptible acquisition methods declare `InterruptedException` and need to be handled or propagated.
- When conversion fails (returns 0), **do not** call unlock for the mode that was not acquired; manage the previously held stamp according to the API contract.

## 11. When can `StampedLock` be more effective?

**Often worth considering when** read frequency is very high, writes are rare, the snapshot consists of a few simple fields, speculative reading is cheap, and validation success rate is high. Because optimistic reads do not contend for a read lock with writers, they can reduce overhead in some systems.

**Usually not a good fit when:**

- Writers update frequently: validation fails often, forcing readers to read twice and pay fallback overhead.
- Snapshots require iterating/reading a complex mutable collection: speculative reads may be unsafe **before validation**.
- Nested method calls require reentrancy: `StampedLock` can self-deadlock.
- Many operations need condition waiting: `StampedLock` does not directly provide `Condition` like `ReentrantLock`.
- Short, low-contention read locks: the implementation overhead of optimistic reading may not pay off.
- Strict fairness or tight response-time bounds are required: `StampedLock` does not guarantee a fairness policy and can exhibit starvation under contention; measure and design timeouts/cancellation appropriately.
- State is a single value that can be updated with `AtomicReference` or an immutable snapshot: an atomic design may be simpler.

### Comparison with other synchronization approaches

| Approach | Strengths | Main limitations |
| --- | --- | --- |
| `synchronized` | Simple, reentrant, automatically releases monitor on scope exit | All readers sharing the monitor can exclude one another |
| `ReentrantReadWriteLock` | Multiple concurrent readers, exclusive writer, reentrant locks | Readers must acquire an actual read lock; writers can face contention |
| `StampedLock` read/write | Multiple readers or one writer, supports conversion | Non-reentrant; manual stamp management |
| `StampedLock` optimistic read | Lock-free speculative read; validate then fallback | Speculatively read data must be safe; writers can cause retries |
| Immutable snapshot + `AtomicReference` | Readers get a consistent immutable reference, easy to reason about | Writers may need to build a new snapshot and CAS/retry |

**Do not assume "StampedLock is faster" by default:** speed also depends on critical section length, reader/writer counts, CPU cores, validation cost, fallback rate, data structures, and the JVM itself. Benchmark with JMH or a realistic measured workload; observe latency, throughput, lock contention, and validation failure rate.

## 12. Common mistakes to avoid

1. **"An optimistic read already holds a lock."** False: it does not block writers; validation is mandatory.
2. **"`tryOptimisticRead()` always returns a valid stamp."** False: it can return `0L` when a write lock is held; `validate` will not confirm that stamp.
3. **"Validate first, then read fields."** False: read data into locals **first**, validate **after**, and then use only the verified locals.
4. **"If validation succeeds, shared fields cannot change anymore."** False: a writer can start after validation; never re-read shared fields as part of the old snapshot.
5. **"If validation fails, use the read data anyway."** False: discard the speculative snapshot and fall back/re-read according to the protocol.
6. **"Any mutable object can be deeply accessed and then validated."** False: dereferencing/indexing/iterating a collection can fail or cause side effects before validation.
7. **"StampedLock is ReentrantLock plus an optimistic mode."** False: `StampedLock` is **non-reentrant**.
8. **"Converting read → write always succeeds."** False: `tryConvertToWriteLock` can return `0L`; release the lock properly and re-check state after acquiring the write lock.
9. **"Optimistic stamps must also be unlocked."** False: this stamp does not represent a held lock.
10. **"Acquire the read/write lock twice and unlock once."** There is no monitor-style reentrancy; this can deadlock or corrupt the stamp lifecycle.
11. **"Having writers use StampedLock is enough."** False if other code paths read or write state while bypassing the protection policy.
12. **"Increasing thread count is a benchmark that proves effectiveness."** Not enough: you must compare the same workload, with warm-up, representative read/write ratios, and statistical confidence.

## 13. Checklist when applying to a real Java class

1. **Identify invariants:** which fields must be consistent within the same snapshot?
2. **Encapsulate state:** fields and `StampedLock` should be private; all writers must use `writeLock()`.
3. **Define the read protocol:** speculatively read into locals, call `validate(stamp)`, and fall back to `readLock()` if needed.
4. **No side effects before validation:** do not log business decisions, mutate state, or invoke callbacks from unvalidated data.
5. **Control mutable references:** prefer primitives and immutable snapshots; do not iterate unprotected mutable collections.
6. **Release the right stamp:** write/read locks must be unlocked in `finally`; optimistic stamps are not unlocked.
7. **Do not assume reentrancy:** review nested helper calls and read → write upgrade paths.
8. **Conversions must have a failure path:** if `0L` is returned, handle the old stamp, acquire the appropriate lock, and re-check the condition.
9. **Handle errors/interrupts/timeouts:** never lose a stamp or leave other threads waiting indefinitely.
10. **Measure before and after:** validation success rate, fallback count, contention, throughput, and latency under realistic read/write load.

**Remember:** `StampedLock.tryOptimisticRead()` allows **speculative reading without holding a read lock**, followed by `validate(stamp)` to verify the snapshot. If validation fails, **re-read from scratch under `readLock()`**. Always manage write/read lock stamps properly, avoid reentrancy, and choose optimistic reads only when speculative data is safe and real workloads show a benefit.