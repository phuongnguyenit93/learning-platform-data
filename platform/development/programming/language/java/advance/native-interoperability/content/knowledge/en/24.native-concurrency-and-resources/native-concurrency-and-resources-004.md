# Do Not Assume a Shared Arena Automatically Prevents Data Races

## Objectives

When using the Foreign Function & Memory API (FFM) in Java 22 or later, it is necessary to distinguish between **allowing multiple threads to access the same memory region** and **ensuring that operations on data in that memory region are safe under concurrent execution**. `Arena.ofShared()` solves the problem of thread access scope and memory lifetime; it **does not automatically lock data, does not make counter increments atomic, and does not protect data structure invariants**.

After this lesson, you should be able to explain why two threads using the same `MemorySegment` can still lose updates, choose an appropriate synchronization approach, and ensure that the `Arena` is only closed after all tasks still using the memory region have finished.

## 1. What Does a Shared Arena Actually Guarantee?

FFM provides `Arena` to allocate and manage the lifetime of off-heap memory regions; a memory region is represented by `MemorySegment`. Each segment is bound to a scope. When the scope is no longer alive, accesses through FFM are rejected, helping prevent access to freed memory. The API also checks memory bounds and corresponding thread constraints.

| Arena | Who can access the segment? | Can it be closed explicitly? | Automatically prevents data races? |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | The owning thread of the arena | Yes, by the owning thread | Not a locking mechanism; other threads are denied access |
| `Arena.ofShared()` | Multiple threads | Yes, by any thread | **No** |
| `Arena.ofAuto()` | Multiple threads | No; lifetime is managed by GC | **No** |
| `Arena.global()` | Multiple threads | No; scope has an unbounded lifetime | **No** |

Properties such as *bounds checking*, *temporal safety*, and *thread accessibility* are different from *data-race freedom*:

- **Spatial bounds:** reading/writing outside the size of `MemorySegment` can be rejected.
- **Temporal bounds:** accessing when the scope is no longer alive is rejected.
- **Thread bounds:** a segment belonging to a confined arena can only be accessed by the owning thread; a segment belonging to a shared arena can be accessed by multiple threads.
- **Data synchronization:** whether threads reading/writing the same address follow the proper ordering and memory rules is the responsibility of the program.

The line `Arena.ofShared()` is **not equivalent** to wrapping every `segment.get(...)` and `segment.set(...)` in `synchronized`. Being able to use an arena from multiple threads also does not mean all data allocated by that arena is a thread-safe data structure.

## 2. How Do Data Races on Shared Memory Occur?

Suppose a segment contains an integer at byte offset `0`. Two threads both do:

1. Read the current value using `get`.
2. Compute the new value as `current + 1`.
3. Write it back using `set`.

If both read `0` before either thread writes, both will write `1`. Even though there were two intended increments, the result is still `1`: a **lost update**. The three read–compute–write steps themselves are not an atomic operation.

A possible execution schedule is:

| Time | Thread A | Thread B | Value in segment |
| --- | --- | --- | --- |
| t0 | — | — | 0 |
| t1 | Reads 0 | — | 0 |
| t2 | — | Reads 0 | 0 |
| t3 | Writes 1 | — | 1 |
| t4 | — | Writes 1 | 1 |

In real programs, missing synchronization can also lead to observing stale state, unexpected observation ordering, or multi-field structures being read in an inconsistent state. You cannot rely on a bug appearing rarely, or a single run producing the right result, to conclude that the code is safe.

### Example reproducing a lost update deterministically

Save all of the following code as **SharedArenaRaceDemo.java** (Java 22+):

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.CountDownLatch;

public class SharedArenaRaceDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment counter = arena.allocate(ValueLayout.JAVA_INT);
            counter.set(ValueLayout.JAVA_INT, 0L, 0);

            CountDownLatch bothRead = new CountDownLatch(2);
            CountDownLatch allowWrites = new CountDownLatch(1);

            Runnable increment = () -> {
                int current = counter.get(ValueLayout.JAVA_INT, 0L);
                bothRead.countDown();

                try {
                    allowWrites.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                counter.set(ValueLayout.JAVA_INT, 0L, current + 1);
            };

            Thread first = new Thread(increment);
            Thread second = new Thread(increment);
            first.start();
            second.start();

            bothRead.await();       // Ensure both have read the value 0.
            allowWrites.countDown();
            first.join();
            second.join();          // Do not close the arena while workers are still running.

            System.out.println(counter.get(ValueLayout.JAVA_INT, 0L));
        }
    }
}
~~~

Compile and run:

~~~text
javac SharedArenaRaceDemo.java
java SharedArenaRaceDemo
~~~

Output:

~~~text
1
~~~

The two `CountDownLatch` instances intentionally create an execution schedule where **both threads read before writing**; they do not make the increment atomic. `join()` waits for the threads to finish and ensures the result is read after the work has completed. The example does not rely on sleep timings or scheduler luck.

## 3. Four Ways to Organize Access Correctly

### 3.1. Read-only immutable data after safe publication

A segment can be read concurrently by multiple threads when the data has finished being initialized, has been **published using an appropriate synchronization mechanism**, and no thread modifies the same byte region during the reading phase. For example, initialize the data before starting workers, or hand off the segment through a thread-safe queue.

Simply assigning a segment to a shared variable, or a `volatile` reference variable, does not mean all subsequent content writes are protected. Avoid having a thread continue writing through another alias while other threads are still reading.

### 3.2. Independent, non-overlapping partitions

If each worker only reads/writes a **non-overlapping** byte range, you can allocate separate segments or create disjoint `asSlice(offset, size)` slices from a segment in a shared arena. Accessing independent byte regions can avoid data conflicts in those regions themselves.

However, `asSlice` only creates a **view** over the same memory; it does not copy data. Overlapping slices, shared metadata fields, total counters, or reusing the same address still require synchronization. You must wait for all workers using slices to finish before closing the arena.

### 3.3. Use the same lock for the entire compound operation

When multiple steps must be executed as a logical transaction (read then write, modify multiple fields, check a condition then update), use `synchronized` or `ReentrantLock`. The example below is an **illustrative snippet placed inside a method**, where `segment` is the shared segment and `lock` is **the exact same lock object** used by all involved threads:

~~~java
synchronized (lock) {
    int current = segment.get(ValueLayout.JAVA_INT, 0L);
    segment.set(ValueLayout.JAVA_INT, 0L, current + 1);
}
~~~

The lock scope must cover the **entire** read–modify–write sequence, not just the `set` operation alone. All read/write paths that need consistency must follow the same locking convention; locking only in the writer while the reader reads directly can still be wrong. For multi-field data that requires shared invariants, locking is often easier to prove correct than multiple separate atomic operations.

### 3.4. Use VarHandle for atomic updates

For a suitable scalar value, `ValueLayout.JAVA_INT.varHandle()` creates a `VarHandle` that accesses a segment using the coordinate pair `(MemorySegment, long byteOffset)`. `getAndAdd` performs an atomic addition at the specified address; `getVolatile` reads with volatile semantics. This approach is suitable for counters and simple state, when the layout, alignment, and access mode are supported by the platform.

Complete program **SharedArenaAtomicDemo.java** (Java 22+):

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.lang.invoke.VarHandle;

public class SharedArenaAtomicDemo {
    private static final VarHandle INT = ValueLayout.JAVA_INT.varHandle();

    public static void main(String[] args) throws InterruptedException {
        int incrementsPerThread = 100_000;

        try (Arena arena = Arena.ofShared()) {
            MemorySegment counter = arena.allocate(ValueLayout.JAVA_INT);

            Runnable increment = () -> {
                for (int i = 0; i < incrementsPerThread; i++) {
                    INT.getAndAdd(counter, 0L, 1);
                }
            };

            Thread first = new Thread(increment);
            Thread second = new Thread(increment);
            first.start();
            second.start();
            first.join();
            second.join();

            System.out.println((int) INT.getVolatile(counter, 0L));
        }
    }
}
~~~

Compile and run:

~~~text
javac SharedArenaAtomicDemo.java
java SharedArenaAtomicDemo
~~~

Output:

~~~text
200000
~~~

`Arena.allocate(ValueLayout.JAVA_INT)` allocates sufficient memory with appropriate alignment for `JAVA_INT` and initializes the memory region to `0`. Each of the two threads performs `getAndAdd(..., 1)` exactly `100_000` times, so the final sum is `200_000`.

**Do not over-extrapolate:** atomicity on a single integer does not automatically guarantee consistency of a multi-field record. When using access modes like `getAcquire`, `setRelease`, `compareAndSet`, `getAndAdd`, or other layout types, you must choose the right desired memory ordering relationship and respect alignment, byte order, data type, and the access modes actually supported. `JAVA_INT_UNALIGNED` or misaligned addresses are not appropriate choices when expecting atomic operations by default.

## 4. Shared Arena Lifetime Is a Separate Concurrency Concern

`Arena.ofShared()` allows multiple threads to access a segment and allows any thread to call `close()`. **That does not allow closing the arena while a worker still intends to read/write.** Lifetime management and content synchronization are two separate responsibilities:

- Create the arena, allocate, and pass the segment to workers while the scope is still alive.
- Track workers using `join()`, `Future.get()`, or an appropriate coordination mechanism.
- Only close the arena after ensuring no tasks are still using the segment. On errors/interrupts, design the cleanup path so that workers actually stop or finish before the resource is freed.
- Do not return a segment from a closed `try-with-resources` scope and expect it to be usable elsewhere.
- Do not rely on `arena.scope().isAlive()` alone to prove that the next access is safe: the state can change between the time of check and the time of use (*time-of-check/time-of-use*).

FFM has a scope-checking mechanism and can throw an exception when accessing an expired segment; some cases of closing concurrently with a scoped access can even cause `close()` to fail. Those checks are meant to protect memory lifetime, **not to fix lost-update bugs or automatically complete a worker shutdown protocol**.

For JNI, native downcalls, or C libraries accessing the same address, you must design **a synchronization protocol that both the Java side and the native side obey**. Java-side `synchronized` is only useful for threads/access paths that actually use the same lock; it does not automatically force native code outside the JVM to obey that lock.

## 5. Misconceptions and Fixes

| Misconception | Why is it wrong? | How to handle it |
| --- | --- | --- |
| “`ofShared()` is already thread-safe, so `get` then `set` is safe.” | The arena allows use from multiple threads, but read–modify–write is still separate. | Use a lock covering the operation, or an appropriate atomic `VarHandle`. |
| “Splitting with `asSlice()` gives each thread its own copy.” | Slices still share the same underlying memory region. | Ensure byte ranges do not overlap or actually copy the data. |
| “Adding `volatile` to the `MemorySegment` variable will protect the bytes.” | `volatile` on a reference does not make content updates atomic. | Synchronize access to the content using an explicit protocol. |
| “A separate lock per worker is enough.” | Two different locks do not mutually exclude each other. | Use the same shared lock for all access paths that need protection. |
| “If `isAlive()` returns `true`, closing the arena concurrently is still fine.” | Checking then using is not atomic with closing the scope. | Coordinate ownership and wait for workers before closing. |
| “`asReadOnly()` freezes the entire memory region.” | Only that view cannot write; a writable alias can still modify the data. | Stop all writers or create a safe immutable snapshot. |
| “Running tests many times without errors means there is no race.” | Scheduling and hardware can hide bugs. | Analyze conflicting accesses and happens-before relationships, and add coordination tests. |

## 6. Checklist When Using a Shared Arena in Real Systems

1. **Who writes which bytes?** List writers, readers, offsets, sizes, and views/aliases. Are there any overlapping regions?
2. **Can the data change concurrently?** If not, initialize and publish safely before reading. If yes, choose independent partitioning, locking, or atomics according to actual needs.
3. **Which operation needs to be atomic?** A single value or a whole group of fields/invariants? `get` + `set` does not replace `getAndAdd`.
4. **What guarantees data visibility ordering?** State specifically `join`, latch, lock, queue, volatile/VarHandle access mode, or native protocol; avoid relying on `sleep`.
5. **Who closes the arena, and when?** Identify the owner managing the lifetime and the point where workers finish, including when exceptions/interrupts occur.
6. **Is the layout correct?** Check byte offset, size, alignment, byte order, and support for atomic access modes.
7. **Have unfavorable schedules been tested?** Reproduce two workers reading together before writing, or multiple workers incrementing a counter a well-defined number of times.

**Self-check question:** If you remove `CountDownLatch` in the first example and run it again, the result might happen to be `2`. Why does that result **not** prove the program is safe? Because the read–modify–write operation still lacks a mechanism guaranteeing atomicity; changing the execution schedule can cause a lost update again. If replaced with `getAndAdd` as in the second example, the result is protected by an atomic operation on the counter's address itself.

## References

- [Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): lifetime, thread confinement, shared arena, and close.
- [Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): spatial/temporal bounds and operations on segments.
- [Java SE 24 — ValueLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html): layout, alignment, and VarHandle.
- [Java SE 24 — VarHandle](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/invoke/VarHandle.html): atomic operations and access modes.

**Takeaway:** `Arena.ofShared()` solves **multi-thread accessibility and memory region lifetime**. The responsibility for **synchronizing conflicting accesses to the same data** still belongs to the program design.