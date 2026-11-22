# Arena.ofShared and Closing Rules When Used by Multiple Threads

## Objectives

Starting from JDK 22, the Foreign Function & Memory API (FFM, JEP 454) is a standard API in the `java.lang.foreign` package. `Arena` allocates and manages the lifecycle of native memory regions represented by `MemorySegment`. When only one thread is working, `Arena.ofConfined()` is usually the simplest. However, when **multiple Java threads must access one or more of the same native segments**, `Arena.ofShared()` allows this without confining access to the creating thread.

However, **“shared” does not mean “always safe to close at any time”**. It also **does not automatically synchronize data** when multiple threads read/write concurrently. The topic of this lesson is designing a coordination contract between the arena manager and the workers using the memory.

After this lesson, you will be able to:

- Distinguish `Arena.ofShared()`, `Arena.ofConfined()`, `Arena.ofAuto()`, and `Arena.global()`.
- Understand the concepts of scope, access lifetime, cross-thread access rights, and the effect on all segments/slices allocated by the arena.
- Understand `Arena.close()` accurately: a successful close invalidates the scope; close is **not idempotent**; close may throw `IllegalStateException` when a segment is being accessed concurrently.
- Organize the lifecycle **create → dispatch work → wait for all work to finish → close** even when a worker fails or the waiting thread is interrupted.
- Distinguish **lifecycle safety** from **data-race safety**; know when partitioning, locks, or atomic/VarHandle are needed.
- Use `ReentrantReadWriteLock` as a lease mechanism to prevent close from interfering with an operation.
- Run a Java JDK 22+ example with four workers sharing a native segment and verify the error when accessing after close.
- Recognize pitfalls with `ExecutorService.shutdown()`, `scope().isAlive()`, callbacks/reentrancy, native pointer escape, and FFM downcalls.

> **Version:** The main code uses `java.lang.foreign.Arena`, `MemorySegment`, and `ValueLayout` **stable from JDK 22**; with JDK 22, `--enable-preview` is not needed. JDK 17 does not have the stable `java.lang.foreign` package, so the example cannot be compiled with `javac 17`. If a project still runs Java 17, you can look into `ByteBuffer.allocateDirect`/JNI or the incubator API for that specific version, though the lifecycle contract will differ.

## 1. Arena Manages Both Memory and Temporal Bounds

`MemorySegment` is a Java object describing a contiguous memory region with a size and access scope. `Arena` allocates native regions and associates segments with a **scope**. In addition to byte bounds, FFM enforces **temporal bounds**: a segment must not be accessed after its scope is invalidated.

~~~text
        Arena.ofShared()
              |
          shared scope
              |
     +--------+---------+----------------+
     |                  |                |
     v                  v                v
native segment A   native segment B   mapped segment C
     |                  |                |
     +------------------+----------------+
              |
T1/T2/T3 are allowed to access while the scope is alive
              |
coordinator waits for everyone to finish using it
              |
          arena.close()
              |
      scope is invalidated
              |
A, B, C and all of their slices can no longer be accessed
~~~

Key points to remember:

1. `Arena.ofShared()` creates a scope **not tied to a specific owner thread**. Its segments can be accessed from any thread subject to the remaining FFM constraints.
2. Any thread can **call** `close()` on a shared arena. This is an API capability, **not** a suggestion for each worker to close it when done.
3. **When `close()` completes normally**, the scope is no longer alive and the native regions allocated by the arena are freed.
4. A `MemorySegment`, an `asSlice(...)`, and a mapped segment using the same arena **share a lifetime**. Holding a Java reference to a slice does not extend the native lifetime after close.
5. `MemorySegment` is a GC-managed Java object; the **native** region allocated by the arena still belongs to the arena's lifecycle and does not wait for Java GC when the arena has been explicitly closed.

### Comparison of the Four Arena Types

| Type | Threads allowed to access | Explicit close | Key difference |
|---|---|---|---|
| `Arena.ofConfined()` | Only the thread that created the arena | Yes, only the owning thread | Easy to control; wrong thread may throw `WrongThreadException` |
| `Arena.ofShared()` | Any thread | Yes, any thread | Requires coordinating close with usages |
| `Arena.ofAuto()` | Any thread | No: `close()` throws `UnsupportedOperationException` | Lifetime depends on GC; cleanup timing is non-deterministic |
| `Arena.global()` | Any thread | No: `close()` throws `UnsupportedOperationException` | Memory region has unbounded lifetime; avoid using indiscriminately |

The `Arena` API is specified to be thread-safe at the implementation level, but it is **not a data structure with locks protecting every byte inside a segment**. Thread-safe allocation and thread-safe access to business state are two separate concerns.

## 2. Two Different Kinds of Safety

### Lifecycle Safety (lifecycle/temporal safety)

T1 must no longer be using native memory when the coordinator closes the arena. In the FFM API, every access checks the scope within the runtime-controlled boundary, and after a successful close a new access will be invalid. However, the application must still arrange so that **multi-step operations** and native callbacks do not have their resources terminated unexpectedly.

### Data Safety (data-race safety)

Suppose T1 and T2 both do:

~~~java
int old = segment.get(ValueLayout.JAVA_INT, 0L);
segment.set(ValueLayout.JAVA_INT, 0L, old + 1);
~~~

This is a **Java JDK 22+ snippet**, assuming `segment` is still alive and the region has sufficient size/alignment. The two statements `get` and `set` are **not an atomic increment**. T1 and T2 can both read the old value, and then both write back the same result → losing one increment. `Arena.ofShared()` does not fix this bug.

When workers only need to process **non-overlapping** regions, distinct indices can be partitioned. When multiple threads share the same location, one of the following tools must be chosen:

- `synchronized`/`Lock` to serialize the related operations;
- `VarHandle` with a supported access mode, proper layout, and proper alignment to perform appropriate atomic operations;
- a single-writer/multiple-readers model with a clear happens-before relationship;
- organizing data into per-worker regions and reducing/merging after joining.

**The lock to keep the resource alive** and **the lock to protect data** may be two different locks. Do not assume having an `Arena.ofShared()` solves both.

## 3. What Are the Exact Rules of Close?

According to the Java SE 22 API for `Arena.close()`:

| Case | Contract |
|---|---|
| Successful close | `arena.scope().isAlive() == false`; segments belonging to the scope cannot be accessed; native backing regions are freed |
| Calling close again | `IllegalStateException`; close is **not idempotent** |
| Concurrent access to a segment of the arena is in progress | Close **may throw `IllegalStateException`**, e.g. an FFM downcall is currently using the segment |
| Calling close on a confined arena from a non-owner thread | `WrongThreadException` |
| Calling close on `ofAuto()`/`global()` | `UnsupportedOperationException` |
| Custom cleanup action fails | `RuntimeException` may be thrown per the contract |

**Important point:** `Arena.ofShared()` does not promise that `close()` will wait for all workers to finish. The specification also states that close **may fail when a segment is being accessed concurrently**. A correct program does not use that exception as a waiting technique (“keep retrying close in a loop until it stops failing”).

And **do not mark the resource as CLOSED if you do not know whether close completed successfully**. If close fails due to concurrent access, duplicate close, or another cleanup failure, the policy must be based on the actual cause and state.

### What Does the API Guarantee When Close Succeeds?

After a `close()` returns normally:

- The arena's scope is invalidated.
- All allocations/mappings belonging to the arena lose access permission, not just the segment held by the thread calling close.
- Java local variables/fields may still hold a `MemorySegment` object, but that object **no longer has permission to use the native backing memory**.
- Access after close is rejected, typically with `IllegalStateException`.

**Do not confuse “the Java object still exists” with “the native resource still exists”.** This is the source of many use-after-close bugs in FFM code.

## 4. Why Do Multiple Threads Need a Close Coordinator?

Instead of letting every worker call `arena.close()` when “I am done”, design a single owner:

~~~text
coordinator                  worker A         worker B
    |                           |                |
create shared arena           |                |
    |                           |                |
allocate segments             |                |
    |---- submit segment ------>|                |
    |-------------------------- submit ---------->|
    |                           |                |
    |                        access A          access B
    |                           |                |
    |<------- task A done ------|                |
    |<-------------------- task B done ----------|
    |
stop new submissions
join all in-flight work
    |
arena.close() ONE TIME
    |
CLOSED
~~~

In a real-world scenario, the coordinator needs to ensure:

1. Users know the exact borrowed lifetime; do not store a `MemorySegment` or raw pointer for future work outside the defined protocol.
2. Do not dispatch new work after shutdown begins.
3. Wait for **all** users currently using the segment to finish, even if a Future throws an exception.
4. Once the resource has no remaining users, call `close()` once.
5. Only allow release/recreate under the defined contract; do not “fix” an out-of-scope segment by retaining the old address.

**Principle:** “Shared allows multiple threads to use it; the owner closes it after all threads have returned their usage rights.”

## 5. Complete JDK 22+ Example: Four Workers Writing Four Separate Regions

The following program uses an `Arena.ofShared()`, allocates a native region large enough for four `int`s, and submits four tasks to a thread pool. Each worker is assigned a unique index. After the tasks complete, main reads in order and the arena closes. Finally, the program attempts to use an escaped slice to demonstrate the effect of close.

### 5.1. File `SharedArenaDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public final class SharedArenaDemo {
    private static final int WORKERS = 4;
    private static final ValueLayout.OfInt INT = ValueLayout.JAVA_INT;

    /*
     * Wait for ALL tasks to actually finish before the arena closes.
     * If the waiting thread is interrupted, keep waiting and then restore
     * the interrupt flag. This is a learning policy with no timeout.
     */
    private static void shutdownAndJoin(ExecutorService pool) {
        pool.shutdown();
        boolean interrupted = false;

        try {
            for (;;) {
                try {
                    if (pool.awaitTermination(1, TimeUnit.DAYS)) {
                        break;
                    }
                } catch (InterruptedException ex) {
                    interrupted = true;
                }
            }
        } finally {
            if (interrupted) {
                Thread.currentThread().interrupt();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        MemorySegment escapedSlice;

        try (Arena arena = Arena.ofShared()) {
            long bytes = (long) WORKERS * INT.byteSize();
            MemorySegment shared = arena.allocate(
                    bytes, INT.byteAlignment());

            // Slice shares the same scope, DOES NOT extend lifetime.
            escapedSlice = shared.asSlice(0L, INT.byteSize());

            ExecutorService pool =
                    Executors.newFixedThreadPool(WORKERS);
            List<Future<?>> jobs = new ArrayList<>();

            try {
                for (int i = 0; i < WORKERS; i++) {
                    final int index = i;

                    jobs.add(pool.submit(() -> {
                        // Each worker writes its own slot, no overlap.
                        shared.setAtIndex(
                                INT, index, (index + 1) * 10);
                    }));
                }

                for (Future<?> job : jobs) {
                    job.get();
                }
            } finally {
                // Even if get() throws, other workers are still joined.
                shutdownAndJoin(pool);
            }

            int[] values = new int[WORKERS];
            for (int i = 0; i < WORKERS; i++) {
                values[i] = shared.getAtIndex(INT, i);
            }

            System.out.println("values=" + Arrays.toString(values));
            System.out.println(
                    "sameScope="
                    + shared.scope().equals(escapedSlice.scope()));
            System.out.println(
                    "aliveInside=" + arena.scope().isAlive());

        } // arena.close() only after shutdownAndJoin.

        System.out.println(
                "aliveOutside=" + escapedSlice.scope().isAlive());

        try {
            escapedSlice.get(INT, 0L);
            System.out.println("unexpected access");
        } catch (IllegalStateException ex) {
            System.out.println(
                    "afterClose=IllegalStateException");
        }
    }
}
~~~

### 5.2. Compiling and Running

Use **JDK 22 or newer**:

~~~bash
java -version
javac -version
javac SharedArenaDemo.java
java SharedArenaDemo
~~~

No C library, no JNI header step, and no `--enable-preview` are needed on JDK 22. If `javac` cannot find `java.lang.foreign`, check `JAVA_HOME`, `PATH`, and the actual JDK version the terminal is using.

### 5.3. Expected Output

~~~text
values=[10, 20, 30, 40]
sameScope=true
aliveInside=true
aliveOutside=false
afterClose=IllegalStateException
~~~

Analysis:

- The four workers run in arbitrary scheduler order, but each worker's index is fixed by `final int index`. Worker 0 writes 10 to slot 0, worker 1 writes 20 to slot 1, etc. There is no contention on the same region.
- `Future.get()` waits for task completion and provides the memory visibility guarantee so main sees the task results after completion.
- `shutdownAndJoin(pool)` waits for the executor to reach the terminated state **even on the error path** before try-with-resources can close the arena.
- `escapedSlice` shares its scope with `shared`; therefore `sameScope=true`.
- Inside `try`, the scope is alive. After a successful close, `aliveOutside=false`.
- The call `escapedSlice.get(...)` after close is rejected with `IllegalStateException`; because the exception is caught, there is no `unexpected access` line.

### 5.4. Why Not Just Call shutdown()?

`ExecutorService.shutdown()` **does not wait** for already-accepted tasks to finish: it only stops accepting new tasks and lets running tasks continue. If after `shutdown()` you immediately exit `try (Arena ...)`, the arena may be closed while a worker is still accessing it.

`Future.get()` waits for **one** task. If one Future throws `ExecutionException`, the get loop may stop while other tasks have not finished. That is why the example uses `finally` to call `awaitTermination` to wait for **all** tasks, not just the ones whose get succeeded.

`shutdownNow()` also does not guarantee workers have stopped. It attempts to interrupt, but native calls and uncooperative tasks may still run. **Do not close native memory just because a cancellation signal was sent.**

### 5.5. What If a Worker Hangs?

`shutdownAndJoin` above intentionally waits until completion and restores the interrupt flag in order to protect the lifetime. If a worker hangs indefinitely, the wait may last indefinitely. This is **a liveness trade-off**; production applications need their own cancellation, deadline, task tracking, and ownership protocol. However, **timing out does not mean the resource is safe to free**. When you cannot prove users have stopped, closing may fail or corrupt work outside Java's control.

For servers, design a graceful shutdown procedure and an explicit failure state instead of ignoring workers that are using native pointers.

## 6. Mistake: Submitting a Task and Closing the Arena Immediately

The following **anti-pattern** example has a race:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(2);
try (Arena arena = Arena.ofShared()) {
    MemorySegment region = arena.allocate(16);

    pool.submit(() -> {
        // The task may only start after the arena has closed.
        region.set(ValueLayout.JAVA_BYTE, 0L, (byte) 1);
    });
}
pool.shutdown();
~~~

This is an **illustrative method-level JDK 22+ snippet** (requires imports). `submit` does not wait. The coordinator thread can exit the try block before the task starts, so using `region` in the worker will fail with a closed lifetime, or create a competing close situation.

The right fix is to **join tasks inside the arena's scope**, or turn the arena into a coordinator-managed resource that outlives the tasks and only closes when all borrows have been returned.

Do not fix it with `Thread.sleep(100)`. Scheduler timing varies by machine, CPU load, GC, and I/O; sleeping does not prove the task has completed.

## 7. Mistake: Treating isAlive() as a Lock

~~~java
if (segment.scope().isAlive()) {
    // Another thread could close the arena right after the if.
    int x = segment.get(ValueLayout.JAVA_INT, 0L);
}
~~~

This is an **illustrative snippet**, assuming a properly allocated `segment` variable. `isAlive()` is a **point-in-time observation of state**. No lease is created by the if condition.

Even though an FFM operation detects access to a closed scope and throws `IllegalStateException`, the application may still need **consistency across a multi-step business operation**. For example:

~~~text
Thread A:
  checks isAlive() == true
                                  Thread B:
                                    close() succeeds
  read/write segment -> exception
~~~

**The right solution:** both check and use must reside inside a region protected by a lifecycle lock/lease; close cannot enter while the operation holds usage rights. If only processing batch tasks, joining all of them before close also satisfies the goal.

Do not rely on `try/catch IllegalStateException` around every access as a substitute for synchronization. Catching the error is useful for handling an invalid state, but it does not protect the atomicity of an operation consisting of multiple accesses.

## 8. Mistake: Two Threads Closing the Same Arena

`Arena.close()` is **not idempotent**. A program calling:

~~~java
Arena arena = Arena.ofShared();
arena.close();
// arena.close(); // IllegalStateException
~~~

is enough to see the contract. A shared arena can be closed from another thread, but that **does not** mean every thread should call close itself when it is done.

Wrong pattern:

~~~java
if (arena.scope().isAlive()) {
    arena.close();
}
~~~

If two threads both see true, both may call close; one thread succeeds, and the other hits `IllegalStateException`. `isAlive` is not a CAS/lock.

An owner can provide an **idempotent `close()` at the wrapper level**, where only one close path actually executes `arena.close()`. This is an additional application contract; it does not change the **non-idempotent** nature of the underlying Arena.

Important: only mark the wrapper CLOSED **after `arena.close` completes successfully**, not when close has just been called. If close fails, you must report the error and have a plan to handle the actual state.

## 9. State Machine for a Long-Lived Service

A service distributing segments to multiple asynchronous tasks should manage states:

~~~text
             CREATE / ALLOCATE
                    |
                    v
                   OPEN
         workers can acquire a lease
             |           |
           lease A      lease B
             |           |
             v           v
           USE A        USE B
             |           |
   requestClose()       |
             |           |
             v           |
          CLOSING       |
     block new leases   |
             |           |
             +---- wait--+
                    |
          active leases == 0
                    |
            arena.close() once
                    |
         +----------+------------+
         |                       |
      success                  failure
         |                       |
         v                       v
       CLOSED               CLOSE_FAILED
     scope invalid          do not treat as CLOSED
~~~

**Coordinator rules:**

- OPEN: accept new work according to the allocation policy.
- CLOSING: do not accept new usages; already-borrowed tasks are allowed to complete or are cancelled **with confirmation**.
- Wait for the total number of active leases to reach 0, or wait fully for `Future`/callback/native completion.
- Perform close exactly once, without competing with other operators.
- After a successful close, CLOSED; subsequent operations are rejected.
- When close throws an exception, do not silently transition to CLOSED. The error may be due to already being closed, an active access, or a custom cleanup failure; the policy depends on the cause.

A `MemorySegment` token returned to a worker **without a lifetime condition** is not a lease. A lease is a coordinated commitment with close: the resource will not be closed before the worker releases its usage rights.

## 10. Lifecycle Lease Pattern Using ReentrantReadWriteLock

In Java, `ReentrantReadWriteLock` can allow **multiple protected reads concurrently**, while `close` requires exclusive access and must wait for ongoing usages to finish.

The pattern below is a valid class on JDK 22+ that can be placed in `SharedInts.java`. It focuses on simple correctness: the `get` method holds the read lock while accessing; `put` uses the write lock to avoid data races; `close` also acquires the write lock and executes once.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

final class SharedInts implements AutoCloseable {
    private final Arena arena = Arena.ofShared();

    private final MemorySegment segment = arena.allocate(
            4L * ValueLayout.JAVA_INT.byteSize(),
            ValueLayout.JAVA_INT.byteAlignment());

    private final ReentrantReadWriteLock lifecycle =
            new ReentrantReadWriteLock(true);

    private boolean closed;

    private void checkOpen() {
        if (closed) {
            throw new IllegalStateException("SharedInts closed");
        }
    }

    int get(int index) {
        Lock lease = lifecycle.readLock();
        lease.lock();
        try {
            checkOpen();
            return segment.getAtIndex(
                    ValueLayout.JAVA_INT, index);
        } finally {
            lease.unlock();
        }
    }

    void put(int index, int value) {
        Lock exclusive = lifecycle.writeLock();
        exclusive.lock();
        try {
            checkOpen();
            segment.setAtIndex(
                    ValueLayout.JAVA_INT, index, value);
        } finally {
            exclusive.unlock();
        }
    }

    @Override
    public void close() {
        Lock exclusive = lifecycle.writeLock();
        exclusive.lock();
        try {
            if (closed) {
                return; // repeated wrapper close is a no-op
            }

            arena.close(); // no one holds read/write lock
            closed = true; // only update if close succeeds
        } finally {
            exclusive.unlock();
        }
    }
}
~~~

**Why does this pattern protect the lifetime?**

1. `get` holds the read lock from the OPEN check until after `segment.getAtIndex`. Close needs the write lock, so it cannot occur between check and get.
2. `put` holds the write lock throughout the `set` statement, so there are no concurrent overwrites through this wrapper.
3. `close` waits for all accesses inside the wrapper to release their locks, calls `arena.close`, and then marks closed. Calling close a second time just returns, **without** calling `arena.close` a second time.
4. Callers entering after closed will throw `IllegalStateException` from the wrapper before using the native segment.

**This is only a pattern for managing a wrapper.** If the raw segment is exported outside or native code retains the address itself, the lock in `SharedInts` **does not protect those consumers**. All users must participate in the same lease contract, or close can still happen while an external consumer is using it.

### Why Does put Use a Write Lock, Even Though the Arena Is Shared?

To avoid competing reads/writes on the same slot, the pattern chooses the simple policy of serializing writes and readers. That can limit concurrency. If you need workers to concurrently write **non-overlapping regions**, you can have usages hold the **read lock for lifetime** and use separate partition/atomic/data locks. However, you must prove there is no data race and not release the lifecycle lease before the operation actually finishes.

### Reentrant read-lock → close Pitfall

Do not call `close()` directly **inside** a callback or a code path already holding the read lock on the same wrapper: upgrading a read lock to a write lock can deadlock. For a native callback that can call back into Java and invoke close, design reentrancy, deferred close, or a separate state machine/lease. `ReentrantReadWriteLock` does not automatically solve transitioning from read ownership to exclusive close.

### When Is Simpler synchronized Better?

A wrapper can use `synchronized` on every operation and `close`, allowing **one** operation at a time. This approach is easy to review and is often sufficient for a small resource. `ReentrantReadWriteLock` is useful when multiple reads can run in parallel, but it does not replace data atomicity or native pointer ownership.

## 11. Downcalls and Native Pointer Escape

When using FFM, a `MemorySegment` can be passed to a native function via a downcall method handle. According to the JDK 22 API, `Arena.close()` **may throw `IllegalStateException`** if a segment belonging to the arena is being accessed concurrently, and the documentation uses a downcall as an example.

~~~text
Thread T1: downcall(nativeProcess, segment)
                     |
                     +------ native C is using the pointer
                                   |
Thread T2: requestClose() ---------+
                     |
             close may fail,
             does not implicitly wait until T1 finishes
~~~

Therefore, it is best to **coordinate at the application layer** so the arena is not closed while a downcall or another consumer is active.

**An even more dangerous case:** the C library receives the pointer from a downcall, **stores it in an internal queue**, and returns immediately; another C thread only uses the pointer later. The Java `Future.get()` of the submit operation has completed, but the native consumer has **not** finished. If the coordinator closes the arena at this point, the raw pointer in C may outlive its lifetime.

FFM can control access through its API, but **cannot automatically prove the lifetime of a raw address retained privately by native code**. A clear native contract is needed:

- Native code invokes a callback or completes a future only when the operation using the pointer has truly ended.
- Have a token/lease or retain/release for buffers used asynchronously.
- The owner only closes the arena when all native consumers have confirmed completion.
- Avoid passing pointers to systems that retain them longer than the arena's lifetime.

Do not treat `Arena.ofShared()` as a “pin every pointer forever” feature.

## 12. Lifecycle of Multiple Segments, Slices, and Mappings

An arena can serve multiple allocations:

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment root = arena.allocate(64);
    MemorySegment left = root.asSlice(0L, 32L);
    MemorySegment right = root.asSlice(32L, 32L);

    // left/right have non-overlapping bounds;
    // both share the same scope as root.
}
// root, left, right can no longer be used.
~~~

The snippet above is a Java JDK 22+ fragment. `asSlice` creates a view; it **does not copy** data and does not create a separate scope. Closing the arena invalidates access for **all** related segments. If worker T1 is done with left while T2 is still using right, you **cannot close the arena** without affecting T2.

Memory-mapped segments created with the `FileChannel.map(..., Arena)` overload can also use the arena's scope. When designing shutdown:

- Ensure workers have stopped reading/writing the mapping.
- For read-write mappings, call `force()` when flushing to the file is required by specification, and handle I/O errors.
- Close `FileChannel` and close `Arena` according to their respective ownership/lifetimes; **closing the channel does not replace closing the arena**.
- Do not let an external process truncate the file while the mapping is still in use unless the application has a handling policy.
- If task groups have different lifetimes, consider **separate arenas per group**; `Arena.close()` is not an API for freeing a single slice.

## 13. Exception Safety and Shutdown Failures

### One Failed Future Does Not Automatically Cancel Other Futures

~~~text
Future A: completes
Future B: throws ExecutionException
Future C: still writing to segment
Coordinator: exits the for loop due to B's error
~~~

If the coordinator exits `try (Arena ...)` here, Future C may still be using the native region. Therefore, in the runnable example, `finally` still calls `shutdownAndJoin` to wait for the pool to terminate. Afterward, the Java exception from B can be propagated outward, while the arena is closed once there are no more workers.

### InterruptedException While Waiting

If the coordinator thread is interrupted during `awaitTermination`, returning immediately and closing the arena could leave active workers using invalidated memory. The example uses an illustrative policy: record the interruption, continue waiting for all tasks to finish, and then restore the interrupt flag. Production code may need a different policy, but it must satisfy the condition **no remaining in-flight users before close**, even under timeout/cancellation.

### Failed Close or Custom Cleanup Error

Do not do:

~~~java
try {
    arena.close();
} catch (IllegalStateException ignored) {
    // Wrong: marking closed without knowing whether close succeeded.
}
~~~

This is an anti-pattern. `IllegalStateException` may indicate the arena is already closed or close is racing with an access; custom cleanup can also throw `RuntimeException`. A system needs to distinguish states, stop issuing new leases, preserve errors, and have an appropriate shutdown/recovery procedure. Do not loop endlessly retrying close until it “happens to stop failing”.

### When a Worker Is Holding a Data Lock

Waiting for all workers to finish can also deadlock if the coordinator holds a lock that a worker needs to complete, and then the coordinator calls `Future.get` under that lock. Clear lock ordering policies are crucial. A good shutdown **does not hold a lock that prevents workers from finishing while waiting on a Future**. If using `ReentrantReadWriteLock`, a write-lock close only waits when readers can release their locks independently.

### Do Not Confuse Arena.close with Cleaner/GC

`Arena.ofShared()` is a **manually** closed arena. Do not assume Java GC will close the arena at the right time if you forget `close()`. For shared native allocations, use `try-with-resources` or a formal owner lifecycle. `Arena.ofAuto()` has GC-managed cleanup but does not allow timely explicit close; `Arena.global()` is not deallocated through the arena. Choose according to the actual lifetime.

## 14. Common Mistakes

| Mistake | Consequence | How to fix |
|---|---|---|
| Thinking `ofShared` automatically synchronizes data | Lost updates, data race | Data locks/atomics or separate byte partitions |
| Letting every worker call `arena.close` when done | Duplicate close, invalidates other workers | Only one owner/coordinator closes |
| Exiting `try (Arena...)` right after `submit` | Task runs after close | Wait for completion before exiting |
| Calling `shutdown()` and assuming the pool has stopped | Running tasks still use memory | `awaitTermination`/Future join |
| One `Future.get` throws and remaining tasks are abandoned | Arena closes while other workers still use it | `finally` waits for all users |
| Using `isAlive()` instead of a lock | Race between check and use | Lease/lock held throughout the operation |
| Closing a shared arena a second time | `IllegalStateException` | Owner state ensures closing only once |
| Swallowing `IllegalStateException` from close | Mistaken state as freed | Handle the error; do not mark CLOSED |
| Closing the arena while a downcall is using a segment | Close may fail | Coordinate downcall completion |
| C stores a raw pointer after a downcall returns | JVM does not know C is still using the resource | Native completion/retain-release |
| Using `asSlice` and thinking the slice lives independently | Access after close is rejected | Slices share the scope |
| Using a confined arena from another worker | `WrongThreadException` | Choose a shared arena if cross-thread is needed |
| Using `Arena.global()` to avoid closing | Native memory is not reclaimed via the arena | Shared/confined with timely close |
| Using `Thread.sleep` to wait for workers | Hard-to-reproduce race | CountDownLatch/Future/Phaser/Executor termination |
| Calling close reentrantly while holding a read lock | Possible read→write upgrade deadlock | Forbid/rework callback and deferred close |
| Thinking close == atomic transaction | Multi-step operation can be cut off if protocol is wrong | Hold lease across the entire operation |
| Treating a Java memory segment as an unbounded raw C pointer | Pointer outlives its lifetime | Do not leak pointer or confirm native lifetime |

## 15. Testing and Observability

A test suite should verify:

1. **Cross-thread read/write while OPEN:** using `ofShared`, workers read/write valid regions; no `WrongThreadException`.
2. **Confined contrast:** the same access from a non-owner worker with `Arena.ofConfined()` must be rejected.
3. **Partitioned writes:** N workers write non-overlapping indices, main joins and receives the right results.
4. **Same-slot race:** if intentionally incrementing with get+set across multiple workers, do not assume a correct result; test the locked/atomic version.
5. **Scope after close:** `isAlive()==false` and an access after close throws `IllegalStateException`.
6. **Second close:** on the raw arena throws `IllegalStateException`.
7. **Wrapper idempotency:** calling wrapper `close` multiple times does not call `arena.close` again.
8. **Failed task path:** one Future throws, remaining tasks are still joined before close.
9. **Close-vs-operation:** an in-progress usage holds a lease; close must wait or be deferred by design.
10. **Async native pointer:** callback/ack ensures the native consumer has stopped before allowing close.
11. **Cancellation:** interrupt/timeout does not cause the coordinator to free memory while workers have not finished.
12. **Multiple segments in the same arena:** close invalidates all segments and slices.
13. **Close failure:** policy does not mark CLOSED without evidence that close completed.

### Avoid Sleep-Based Race Tests

A test that calls `Thread.sleep(10)` and hopes close happens right between two lines of code is non-deterministic. Use `CountDownLatch`, `CyclicBarrier`, or `Phaser` to coordinate phases; however, what needs to be proven is that **the protocol forbids closing while users remain**, not trying to guess the outcome of a scheduler run.

If there are JNI/FFM downcalls to C, additionally use native memory sanitizers, leak tracking, and ownership logging. `MemorySegment` supports temporal bounds, but does not automatically protect against another C library dereferencing a pointer outside FFM's reach.

## 16. Choosing a Solution by Need

| Scenario | Reasonable choice |
|---|---|
| One thread processes a native buffer in a short `try` | `Arena.ofConfined()` |
| Multiple threads share a native buffer, need timely close | `Arena.ofShared()` + join/lease |
| Multiple read methods; close must wait for readers | Lifecycle read-write lock |
| Concurrent writes to the same data | Appropriate data lock/VarHandle, separate from lifecycle lock |
| Independent tasks, only writing non-overlapping offsets | Shared arena + index partition + Future join |
| Memory used until the end of the process | `Arena.global()` when unbounded lifetime is truly needed |
| Cleanup can wait for GC, not an urgent resource | `Arena.ofAuto()` when non-deterministic timing is acceptable |
| Native SDK retains pointer across async call | Native ownership/retain-release/ack completion; shared arena alone is not enough |
| Tasks have different lifetimes | Multiple arenas by group/lifecycle, avoid cross-closing |

Do not choose `ofShared` just because you hear “multi-threaded is fast”. On-heap Java data structures may be more suitable if native memory is not needed. Off-heap has allocation overhead, memory pressure, and lifetime management costs; benchmark against the actual workload.

## 17. Self-Check Questions and Answers

**1. Main difference between `ofConfined` and `ofShared`?** Confined only allows the owner thread to use/close; shared allows other threads to use and close, but requires lifecycle coordination.

**2. Does a shared arena automatically prevent two threads from writing the same int?** No. If two threads modify the same slot, a data lock, atomic/VarHandle, or a design avoiding competing writers is required.

**3. Does `Arena.close()` on a shared arena always wait for an FFM downcall to finish?** No. The Java SE 22 specification allows `IllegalStateException` if a segment belonging to the arena is being accessed concurrently, such as by a downcall.

**4. Is closing twice harmless?** No for `Arena.close()`; the second call throws `IllegalStateException`. A wrapper can ensure idempotent close itself using state/lock.

**5. If `segment.scope().isAlive()` is true, is the next operation guaranteed to be valid?** No; another thread can close the arena between check and use.

**6. Is it safe to close right after `shutdown()`?** Not necessarily. Shutdown does not wait for running tasks; you must join/await termination or have an equivalent protocol.

**7. If one worker Future throws an exception, can the remaining Futures be ignored?** Not if they use the same arena. The cleanup path must wait for other users to stop before closing.

**8. Why does the 4-worker example have stable stdout despite non-deterministic thread scheduling?** Each worker writes to a separate index, and main only reads after completion/termination and prints in index order.

**9. Does a slice keep the native allocation alive after close?** No. A slice shares the scope and backing memory with the original segment.

**10. Can `Arena.ofAuto()` replace `ofShared()` for timely closing?** No. An auto arena does not support explicit close; cleanup timing is decided by GC.

**11. C retains a pointer and uses it after the Java Future completes; is it safe to close the arena?** No if the Future only indicates that submission finished. Native completion/lease confirmation is needed to verify the pointer is no longer in use.

**12. What does the `ReentrantReadWriteLock` in `SharedInts` protect?** It keeps methods using the segment from overlapping with close; the write lock also serializes writes. It only protects callers going through the wrapper, not users bypassing the lock.

## 18. Code Review Checklist

1. Is **JDK 22+** and the standard FFM API being used?
2. Is cross-thread sharing truly needed, or is `ofConfined` sufficient?
3. Who owns the arena? How many places can call close?
4. When shutdown begins, are new tasks prevented from acquiring the segment?
5. Are all active leases/tasks/native consumers tracked and awaited?
6. If a Future fails, are the remaining tasks joined before close?
7. After interruption/timeout, is it proven that users have actually stopped?
8. Is `close()` called once and only marked CLOSED when it succeeds?
9. Is `scope().isAlive()` being used instead of a lock/lease?
10. Do any methods return the raw segment externally without controlling its lifetime?
11. Does any callback call close reentrantly from an operation holding a lock?
12. Is data written at the same offset by multiple threads? Is there valid synchronization/atomics?
13. Are other segments, slices, or mapped regions sharing the same scope still in use?
14. Does a native downcall retain the pointer after returning? Who confirms completion?
15. Are there tests for after-close, double-close, concurrent tasks, and failed close?
16. Are native memory leaks, task completion, and shutdown deadlocks monitored?

## References

- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): shared/confined/auto/global, closing rules, and `IllegalStateException` on concurrent access.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): bounds checking, scope, access, and thread confinement.
- [Oracle Java SE 22 — MemorySegment.Scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html): `isAlive` and segment lifetimes.
- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): size, alignment, and layouts.
- [Oracle Java SE 22 — ExecutorService](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `awaitTermination`, and task lifecycle.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM becomes a standard API as of Java 22.

## Takeaways

**`Arena.ofShared()` allows multiple threads to use native memory, but closing must be controlled by a single coordinator.** Shared does not automatically make data thread-safe, and `close()` must not be treated as a way to wait for workers to finish.

The right flow:

1. Create a shared arena with a clear owner.
2. Only issue usage rights (leases) while the arena is OPEN.
3. Synchronize data reads/writes separately if multiple threads share the same bytes.
4. Stop issuing new work; wait for all workers/downcalls/native pointers to finish using it.
5. Call `arena.close()` **once**, and only consider it CLOSED after close succeeds.
6. Do not use any segment or slice belonging to a closed scope.

If you remember one thing: **shared is access across multiple threads; safety when closing is a lifecycle protocol that must be designed separately**.