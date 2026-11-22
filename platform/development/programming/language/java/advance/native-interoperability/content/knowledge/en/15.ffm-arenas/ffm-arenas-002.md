# Arena.ofConfined and Owner Thread Access (Java FFM)

## 1. The Big Picture: Who Owns the Allocated Memory Region?

Java's Foreign Function & Memory API (FFM) lets you create, read, write, and pass native (off-heap) memory regions through `MemorySegment`. Since JDK 22, FFM has been a standard API in the `java.lang.foreign` package. A common way to allocate is by creating a **confined arena**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

// Illustrates a snippet inside a method, not a standalone program.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment value = arena.allocate(ValueLayout.JAVA_INT);
    value.set(ValueLayout.JAVA_INT, 0, 42);
    int answer = value.get(ValueLayout.JAVA_INT, 0);
}
~~~

An `Arena` is the **lifecycle manager** of the memory regions it allocates. `Arena.ofConfined()` creates an arena with three key properties:

1. **Has an owner thread:** the thread that calls `Arena.ofConfined()` is the owner.
2. **Thread confinement:** memory regions allocated from a confined arena can only be validly accessed by the owner thread, even if another thread holds a Java variable of type `MemorySegment` pointing to the same region.
3. **Bounded lifetime and deterministic cleanup:** the owner closes the arena with `close()` (usually via `try-with-resources`). After closing, all segments allocated from the arena become invalid, and the native memory owned by the arena is freed.

Two boundaries must be checked for **every access**:

~~~text
                          Is a MemorySegment valid?
                                    |
               +--------------------+--------------------+
               |                                         |
      Is scope alive?                         Does this thread have permission?
     scope().isAlive()                           segment.isAccessibleBy(T)
               |                                         |
               +--------------- both valid --------------+
                                    |
                  Further check bounds, alignment,
                  read-only, layout of the operation
                                    |
                             Can be accessed
~~~

If it is the **right thread but the arena is closed**, the read/write operation may throw `IllegalStateException`. If the **arena is alive but it is the wrong thread**, the read/write operation may throw `WrongThreadException`. These are two different errors; do not lump them into a single "invalid segment" error.

> **Core rule:** Not every thread that **sees** a `MemorySegment` in Java has permission to **access the contents** of that segment. Passing a reference across threads does not transfer ownership of a confined arena.

## 2. Arena, Scope, and Segment: Three Easily Confused Concepts

| Concept | Java Representation | Purpose | What Not to Infer |
| --- | --- | --- | --- |
| Arena | `Arena` | Allocates native memory and manages the lifecycle of associated segments | Does not mean every arena is multi-thread accessible |
| Scope | `MemorySegment.Scope` | Represents the shared lifetime of segments bound to the scope | `isAlive() == true` does not prove the current thread has access permission |
| Segment | `MemorySegment` | A view with address, size, read/write permissions, and scope for a memory region | Not a Java array; does not independently own memory outside the scope |
| Value layout | `ValueLayout.JAVA_INT`, `JAVA_LONG`, ... | Specifies type, size, alignment, and byte order when reading/writing | Does not bypass thread, lifetime, or bounds limits |
| Owner thread | `Thread` creating the confined arena | The thread allowed to access segments belonging to the confined arena | Cannot change the owner just by variable assignment or `Thread.start()` |

Example:

~~~java
// Illustration inside a method.
Arena arena = Arena.ofConfined();
MemorySegment first = arena.allocate(16);
MemorySegment second = arena.allocate(32);
MemorySegment view = first.asSlice(4, 8);

// first, second, and view are bound to the arena's scope.
// asSlice does NOT create a new owner and does NOT extend lifetime.
arena.close();
~~~

- `first` and `second` are different segments but share the same scope.
- `view` is just a *slice* of `first`, with narrower spatial bounds; it is still subject to the **same owner and lifetime constraints**.
- Do not close `view` separately: it does not have a `close()` method for independent release.
- Some metadata methods (`byteSize()`, `scope()`) can provide information without reading native bytes; obtaining metadata does **not** mean having permission to dereference memory.

`MemorySegment.ofArray(...)`, on the other hand, is a **heap segment** backed by a Java array, not an allocation managed by `Arena.ofConfined()`. Heap segments have different ownership/lifetime rules; do not use them to infer access permissions for a native segment of a confined arena.

## 3. How Is the Owner Established?

Suppose `main` creates the arena:

~~~text
Thread main
    |
    +-- Arena.ofConfined()  -> owner = main
    |       |
    |       +-- arena.allocate(...) -> segment S
    |       +-- S.get(...)          -> valid on main
    |       +-- S.set(...)          -> valid on main
    |       +-- arena.close()       -> valid on main
    |
    +-- Thread worker holds a Java reference to S
            |
            +-- S.get(...)          -> WrongThreadException
            +-- S.set(...)          -> WrongThreadException
            +-- arena.close()       -> WrongThreadException
~~~

In a confined arena, the **owner thread is the thread that creates the arena** according to the API, not:

- Whichever thread holds the `Arena arena` or `MemorySegment segment` variable on the heap;
- The thread running `main` in general, if the arena was actually created in a worker thread;
- The thread that calls the last method;
- The thread managing the `ExecutorService`;
- A thread currently holding a Java `synchronized` lock;
- A native OS thread calling an FFM function on behalf of the Java owner.

If a `Runnable` creates a confined arena **inside** `run()`, the owner of that arena is the thread executing `run()`, not necessarily the thread that *instantiated the Runnable object*.

### 3.1. Common Mistake: Passing the Segment Object to a Worker

~~~java
// Illustrates an error; not a standalone program.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);

    Thread worker = new Thread(() -> {
        segment.set(ValueLayout.JAVA_INT, 0, 99);
        // Wrong thread: may throw WrongThreadException.
    });

    worker.start();
    worker.join();
}
~~~

The `segment` variable is a Java object reference that can be captured by a lambda; the Java compiler does not forbid it. **However, FFM checks access permissions when operating on native memory**. The variable can be passed, but the access permission of a confined arena cannot.

If the worker catches the exception and stays silent, the program can give the impression of "work completed" while not writing a single byte. In real applications, you must propagate the error or change the ownership design.

### 3.2. Reverse Mistake: Worker Creates Arena, Main Cannot Read

~~~java
// Illustrates a wrong handoff model:
Thread worker = new Thread(() -> {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment created = arena.allocate(8);
        // owner is worker, not main.
        // Passing created to main does not automatically grant permission to main.
    }
});
~~~

If the worker returns after exiting `try`, the arena is also closed, so the segment on `main` is both **not owned by main** and **past its lifetime**. The right design is to have the worker copy the result to a Java value/array, or design an intentionally managed shared arena.

## 4. What Access Is Considered Valid?

Content access operations bound by confinement include:

- `segment.get(ValueLayout.JAVA_INT, offset)` and `segment.set(...)`;
- `segment.getAtIndex(...)`, `setAtIndex(...)`;
- `segment.copyFrom(other)` or memory copy methods: both source and destination segments must have appropriate scopes and access permissions;
- `segment.toArray(...)` when reading native memory into a Java array;
- reading/writing elements through a `VarHandle` obtained from `MemoryLayout`;
- using the segment in an FFM downcall if the downcall needs to read/write the native pointer that the segment represents.

**It is not only `set` calls that are checked.** Even reading an `int` with `get` from another thread violates confinement. `asReadOnly()` only makes the memory region non-writable through that view; it does **not** turn a confined segment into a segment readable from any thread.

### 4.1. Built-in Check APIs in JDK 22

~~~java
// JDK 22+, illustrated with an existing segment:
boolean ownerCanAccess =
        segment.isAccessibleBy(Thread.currentThread());

boolean stillAlive =
        segment.scope().isAlive();

long size = segment.byteSize();
~~~

- `isAccessibleBy(thread)` checks **thread** accessibility allowed by the segment API.
- `scope().isAlive()` reports **lifetime** status.
- `byteSize()` reports the logical size in bytes.

You should check **both thread and lifetime** when proactive branching is needed, while still letting the FFM access API perform the real checks at the time of the operation because scope state can change. An `if (scope().isAlive())` statement is not a license to bypass owner permissions.

Do not use these predicates to "prove" that a **raw native pointer** created with `MemorySegment.ofAddress` has valid backing memory. When working with raw pointers, FFM cannot automatically verify all external ABI/ownership boundaries.

## 5. Lifecycle: `try-with-resources` and `Arena.close()`

Standard pattern:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

// Illustration inside a Java 22+ method.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(ValueLayout.JAVA_INT);
    segment.set(ValueLayout.JAVA_INT, 0, 25);

    int value = segment.get(ValueLayout.JAVA_INT, 0);
    // value == 25, and the operation is on the right owner.
} // arena.close() is called automatically, also on the owner thread.
~~~

`Arena` implements `AutoCloseable`, so `try-with-resources` is the usual way to release **all** native allocations associated with a confined arena with a clear lifecycle, even if the block throws an exception. Segments allocated from the arena must not be used after the arena is closed.

Important characteristics:

1. **Closing is final:** a successful close makes the scope no longer alive.
2. **Not idempotent:** attempting to call `close()` again on an already-closed arena throws `IllegalStateException`, not a safe no-op.
3. **Right thread:** closing a confined arena from another thread throws `WrongThreadException`; closing does **not** transfer the owner.
4. **Currently accessed:** if a foreign downcall holds a segment being accessed concurrently with close, the JVM may report `IllegalStateException` per contract instead of freeing recklessly.
5. **Do not use segment after close:** accessing contents after the scope expires throws `IllegalStateException` on the right thread (in the normal case).

### 5.1. After Arena Close, What Data Remains Alive?

~~~java
// Illustration inside a method, not a standalone program.
MemorySegment escaped;

try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(ValueLayout.JAVA_INT);
    escaped.set(ValueLayout.JAVA_INT, 0, 101);
}

boolean alive = escaped.scope().isAlive(); // false
// escaped.get(ValueLayout.JAVA_INT, 0) -> IllegalStateException.
~~~

**The Java variable `escaped` may still exist**, but the native region it represents has ended its lifetime. The fact that Java GC has not yet collected the `MemorySegment` object itself **does not keep the native memory region alive**. This is the *temporal safety* aspect.

With `Arena.ofConfined()`, resource management does **not** rely on GC to finish at a deterministic time: proactively close the arena on the right thread.

### 5.2. Arena Close Is Not Arbitrary `free(pointer)`

The arena tracks the memory it allocates. Do not manually `free` a native address obtained from `segment.address()` via JNI or C `free()` while the arena still owns the allocation: that risks double-free or use-after-free. Similarly, do not pass the address to a native library that will retain the pointer after the arena closes, unless explicit ownership transfer has been designed with a compatible contract.

## 6. Runnable Example 1: Owner Permissions, Worker Permissions, and Close

This is a standalone **JDK 22+** program, using no JNI or C libraries. It tests three cases:

1. The owner thread reads/writes the native segment successfully.
2. A worker thread has a Java reference to the segment, but reading fails with `WrongThreadException`; the worker also cannot close the arena.
3. The owner closes the arena properly. After close, the owner attempting to read again receives `IllegalStateException`.

Create file **`ConfinedArenaOwnerDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicReference;

public final class ConfinedArenaOwnerDemo {
    public static void main(String[] args)
            throws InterruptedException {

        MemorySegment escaped;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment =
                    arena.allocate(ValueLayout.JAVA_INT);

            segment.set(ValueLayout.JAVA_INT, 0, 42);

            System.out.println(
                    "ownerAccessible="
                    + segment.isAccessibleBy(Thread.currentThread()));
            System.out.println(
                    "ownerValue="
                    + segment.get(ValueLayout.JAVA_INT, 0));

            AtomicReference<String> readOutcome =
                    new AtomicReference<>();

            Thread reader = new Thread(() -> {
                boolean allowed =
                        segment.isAccessibleBy(Thread.currentThread());

                try {
                    segment.get(ValueLayout.JAVA_INT, 0);
                    readOutcome.set(allowed + "/unexpectedSuccess");
                } catch (WrongThreadException ex) {
                    readOutcome.set(allowed + "/WrongThreadException");
                }
            }, "reader");

            reader.start();
            reader.join();
            System.out.println("workerRead=" + readOutcome.get());

            AtomicReference<String> closeOutcome =
                    new AtomicReference<>();

            Thread closer = new Thread(() -> {
                try {
                    arena.close();
                    closeOutcome.set("unexpectedSuccess");
                } catch (WrongThreadException ex) {
                    closeOutcome.set("WrongThreadException");
                }
            }, "closer");

            closer.start();
            closer.join();
            System.out.println("workerClose=" + closeOutcome.get());
            System.out.println(
                    "aliveBeforeOwnerClose="
                    + arena.scope().isAlive());

            escaped = segment;
        }

        System.out.println(
                "aliveAfterOwnerClose=" + escaped.scope().isAlive());

        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
            System.out.println("afterClose=unexpectedSuccess");
        } catch (IllegalStateException ex) {
            System.out.println("afterClose=IllegalStateException");
        }
    }
}
~~~

Compile and run with **JDK 22 or higher**:

~~~bash
javac ConfinedArenaOwnerDemo.java
java ConfinedArenaOwnerDemo
~~~

**Expected stdout on successful run:**

~~~text
ownerAccessible=true
ownerValue=42
workerRead=false/WrongThreadException
workerClose=WrongThreadException
aliveBeforeOwnerClose=true
aliveAfterOwnerClose=false
afterClose=IllegalStateException
~~~

Line-by-line analysis:

- Main creates the arena with `Arena.ofConfined()`, so `isAccessibleBy(Thread.currentThread())` returns `true`. Main writes and reads `42`.
- `reader` receives the `segment` variable via Java lambda capture, but it is a different Java thread. `isAccessibleBy` returns `false`; `get` is rejected with `WrongThreadException`.
- `closer` is also a different thread. `arena.close()` is rejected with `WrongThreadException`, so the arena is **not closed yet**. At this point `scope().isAlive()` on main is still `true`.
- When main exits `try`, Java automatically calls `close()` **on main**; the arena closes successfully.
- `escaped` still points to the Java `MemorySegment`, but the backing native memory has expired, so `scope().isAlive()` is `false`. Main (still the right thread) reading again encounters `IllegalStateException`.

The program uses `AtomicReference` and `join()` to bring worker results back to main in a deterministic order; it does not rely on print order from concurrently running threads. The code intentionally catches exceptions from the two invalid behaviors for **illustration**; in business logic, instead of routinely triggering exceptions and catching them, design ownership properly from the start.

**Remember:** `WrongThreadException` is in the **`java.lang`** package, so it can be used directly as above; do not mistakenly import `java.lang.foreign.WrongThreadException`. It is an unchecked exception, not a subtype of `IllegalStateException`.

## 7. Runnable Example 2: Sharing Results via Java Copy, Not Sharing a Confined Segment

When another worker thread needs data, the safe and usually simplest option is:

1. The owner allocates native memory with `Arena.ofConfined()`.
2. The owner computes and **copies the data** into an `int[]` or regular Java value **before close**.
3. Close the arena on the owner.
4. Pass the Java copy to the worker; the worker does not touch the confined segment.

Create file **`ConfinedCopyHandoffDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicInteger;

public final class ConfinedCopyHandoffDemo {
    public static void main(String[] args)
            throws InterruptedException {

        int[] snapshot;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 2, 3, 5, 7);

            snapshot = numbers.toArray(ValueLayout.JAVA_INT);
        }

        AtomicInteger result = new AtomicInteger();

        Thread worker = new Thread(() -> {
            int sum = 0;
            for (int number : snapshot) {
                sum += number;
            }
            result.set(sum);
        }, "sum-worker");

        worker.start();
        worker.join();

        System.out.println("copiedLength=" + snapshot.length);
        System.out.println("copiedSum=" + result.get());
    }
}
~~~

Compile and run:

~~~bash
javac ConfinedCopyHandoffDemo.java
java ConfinedCopyHandoffDemo
~~~

**Stdout:**

~~~text
copiedLength=4
copiedSum=17
~~~

`arena.allocateFrom(ValueLayout.JAVA_INT, 2, 3, 5, 7)` is JDK 22+ syntax; `numbers.toArray(ValueLayout.JAVA_INT)` copies the data into an **independent Java `int[]`**. After the arena is closed, the Java array remains valid because its lifetime no longer depends on the native arena. The worker only reads Java data, so it does not violate FFM thread confinement.

If you do not want to copy because the data is very large, you must choose a more suitable architecture, such as one confined owner thread handling all native operations, or `Arena.ofShared()` accompanied by clear synchronization and lifecycle management. There is no "transfer owner" operation on a confined arena via a simple setter.

## 8. Runnable Example 3: Truly Needing the Same Segment Across Multiple Threads

Comparing `Arena.ofConfined()` and `Arena.ofShared()`:

| Criterion | Confined arena | Shared arena |
| --- | --- | --- |
| Factory | `Arena.ofConfined()` | `Arena.ofShared()` |
| Owner thread | Yes, the thread that creates the arena | Not bound to a single owner thread |
| Can the segment be read/written from another thread? | **No** | **Yes**, if the scope is alive and other conditions are met |
| Who can close? | Owner thread | Any thread per contract, must coordinate with ongoing accesses |
| Responsibility for synchronizing mutable memory | Can be simpler thanks to thread confinement | **Still mandatory to design yourself**; not automatically thread-safe |
| Lifetime | Deterministic cleanup via close | Deterministic cleanup via close, but must avoid closing while users remain |
| Suitable scenarios | Short, single-threaded native work, temporary buffers | Parallel reading or controlled sharing of a native region |

The following program uses a shared arena and **only reads** from the worker after main has finished writing; `join()` ensures the worker finishes **before the arena closes**.

Create file **`SharedArenaReadDemo.java`**:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicReference;

public final class SharedArenaReadDemo {
    public static void main(String[] args)
            throws InterruptedException {

        try (Arena arena = Arena.ofShared()) {
            MemorySegment values = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 11, 13);

            AtomicReference<String> observation =
                    new AtomicReference<>();

            Thread reader = new Thread(() -> {
                boolean allowed = values.isAccessibleBy(
                        Thread.currentThread());
                int total = values.getAtIndex(
                        ValueLayout.JAVA_INT, 0)
                        + values.getAtIndex(
                        ValueLayout.JAVA_INT, 1);

                observation.set(allowed + "/" + total);
            }, "shared-reader");

            reader.start();
            reader.join();

            System.out.println(
                    "sharedRead=" + observation.get());
        }
    }
}
~~~

Compile and run:

~~~bash
javac SharedArenaReadDemo.java
java SharedArenaReadDemo
~~~

**Stdout:**

~~~text
sharedRead=true/24
~~~

Analysis:

- `Arena.ofShared()` allows the worker to access `values`.
- Main creates and populates the segment **before** `Thread.start()`; `Thread.start()` establishes an appropriate happens-before relationship for publishing the initial result to the worker. There is no concurrent native memory reading/writing in the example.
- The worker only reads, then `join()` returns; only then does main exit `try` to close the arena.
- **Do not conclude** that all concurrent accesses to native memory through a shared arena are safe. With multiple writers or concurrent writer-reader access, proper synchronization is required; the FFM API does not automatically apply the full Java Memory Model to off-heap access operations the way it does for object fields.

If you adopt `ofShared()` just to "dodge `WrongThreadException`" without specifying which thread closes and when no users remain, you have traded an **obvious confinement error** for more complex **race and lifecycle** risks.

## 9. Valid and Invalid Handoff Patterns

### 9.1. Owner Performs Native Work; Other Threads Only Send Requests

A useful contract in actor/event-loop designs:

~~~text
Thread owner
    |
    +-- Arena.ofConfined()
    +-- creates native segments
    +-- message/command processing loop
    |       +-- receives requests from workers via thread-safe queue
    |       +-- performs get/set itself on the owner thread
    |       +-- returns Java result/snapshot
    +-- stops accepting new commands
    +-- closes arena on the owner thread
~~~

Worker threads do not hold the confined arena's `MemorySegment` to dereference directly. They only send commands via a Java `BlockingQueue`, a single-threaded `Executor`, or an equivalent message-passing mechanism; the **owner** performs the FFM operations.

Benefits: memory safety is easy to reason about, close happens on the same thread, no need to share native mutable state between threads. Cost: cannot directly utilize the same memory region across multiple threads, queue overhead, and potential bottleneck.

### 9.2. Each Worker Creates Its Own Confined Arena

~~~java
// Illustrates a call inside a worker thread, not a complete program.
Runnable job = () -> {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment tmp =
                arena.allocate(ValueLayout.JAVA_LONG);
        tmp.set(ValueLayout.JAVA_LONG, 0, 100L);

        long computed = tmp.get(ValueLayout.JAVA_LONG, 0);
        // Send computed back to Java queue/future, do NOT send tmp.
    }
};
~~~

If the work can be split into independent parts, letting **each worker create and close its own arena** is often simpler than sharing a confined segment. Note: a task submitted to a thread pool may run on any thread, but an arena created **inside the running worker** establishes the owner properly.

Do not create an arena in a producer thread and put the arena instance into a queue for a consumer worker to use. The arena is already confined to the producer from the moment of creation.

### 9.3. Java Snapshot or Copy to a Native Shared Allocation

For small/medium results: a Java `byte[]`/`int[]`/record/immutable object snapshot. For large data that truly needs native shared memory, you can allocate the **destination in `Arena.ofShared()`**, then **copy data from the confined source on the owner thread** into the destination, and only then let workers use it. During the copy, both source and destination must be alive and accessible to the owner.

~~~java
// Illustrative pattern on the owner thread:
try (Arena confined = Arena.ofConfined();
     Arena shared = Arena.ofShared()) {

    MemorySegment source = confined.allocate(16);
    MemorySegment destination = shared.allocate(16);

    // source and destination are alive, owner can access both.
    destination.copyFrom(source);

    // After copy, workers only access destination and must finish
    // before shared.close() occurs.
}
~~~

This is **not a complete multi-threaded program**; the sample only illustrates the copy operation. If native memory contains pointers pointing to allocations in the confined arena, **copying the pointer bytes does not extend the lifetime of the memory region those pointers point to**. You need a deep copy or to adjust ownership according to the real ABI.

### 9.4. There Is No Automatic `transferOwnership()`

Do not use the following methods to "transfer" the owner:

- Assigning `MemorySegment` to a static field;
- Putting a segment into a `CompletableFuture` and completing it on the owner;
- Passing a segment through a `BlockingQueue`;
- Converting `segment.address()` to `long` and reconstructing `MemorySegment.ofAddress(...)` on another thread;
- Creating `segment.asSlice(...)`, `segment.asReadOnly()`, or passing via `ByteBuffer`;
- Using `ThreadLocal` to hold the handle on another worker.

These actions can move the **value/address** across threads, but do not change ownership of the backing allocation. Trying to use a raw address to bypass checks is even more dangerous because the JVM may not track bounds/lifetime on the new wrapper layer.

## 10. Why `asSlice` and `asReadOnly` Do Not Break Confinement

~~~java
// Illustration, segment belongs to Arena.ofConfined():
MemorySegment slice = segment.asSlice(8, 16);
MemorySegment ro = segment.asReadOnly();
~~~

- `slice` has a different size/offset, but the **scope and backing allocation still belong to the original segment**.
- `ro` carries the read-only attribute, but does **not** change the scope's owner thread.
- `slice.get(...)` and `ro.get(...)` from a non-owner worker are still checked for confinement upon access.
- After the arena closes, the original segment, slice, and read-only view can no longer be read or written.
- A `ByteBuffer` view created from a native segment is also not a "license" to bypass the lifetime/thread access contract; do not build solutions relying on the fact that a view can be passed like a Java object.

### Why Not Use `reinterpret` to Escape Limits?

`MemorySegment.reinterpret(...)` is a restricted API group because it can re-assume spatial/temporal bounds for a native address. If misused, the risk is no longer just `WrongThreadException`: it can cause **memory corruption or crash the JVM**.

Do not use `reinterpret`, `ofAddress`, and pointer arithmetic as a workaround for confined arena thread ownership. When multi-threading is needed, design a **shared arena with synchronization and ownership** or copy the data; do not bypass safety checks with a wrapper holding a raw address.

## 11. Other Common Errors: Lifetime, Alignment, Bounds, Read-Only

`WrongThreadException` is not the only error that can occur when working with segments:

| Situation | Error Type Commonly Seen per JDK 22 API | Proper Fix |
| --- | --- | --- |
| Reading/writing confined segment from another thread | `WrongThreadException` | Operate on the owner or choose a controlled shared architecture |
| Closing confined arena from non-owner | `WrongThreadException` | Ensure the owner executes close |
| Reading/writing segment after arena close | `IllegalStateException` | Do not escape segment past lifetime; copy data before close |
| Calling `arena.close()` a second time | `IllegalStateException` | One owner responsible for closing exactly once |
| Accessing outside byte bounds | `IndexOutOfBoundsException` | Use `byteSize()`, proper offsets/indices, and layouts |
| Unsuitable layout alignment | `IllegalArgumentException` | Choose an aligned layout or unaligned layout when needed |
| Writing through a read-only view | `IllegalArgumentException` | Choose a writable segment or do not write |
| Allocating negative size/invalid alignment | `IllegalArgumentException` | Validate size/alignment before allocation |
| Closing shared arena while segment is in a foreign call | May be rejected or need to wait for the related activity | Coordinate lifecycle, wait for worker/downcall completion |
| Accessing an arbitrarily reconstructed native address | May crash/corrupt outside FFM protection | Do not assign pointer bounds/lifetime without verifying ABI |

### 11.1. `byteSize()` Does Not Replace Scope/Owner Checks

For example, a segment having a `byteSize` of 16 does not prove you can read 16 bytes right now. **Four validity dimensions** are needed:

1. **Spatial bounds:** `0 <= offset` and `offset + layout.byteSize() <= byteSize()`, avoiding overflow when computing manually.
2. **Temporal bounds:** the scope is still alive.
3. **Thread access:** the current thread is allowed to access.
4. **Layout/write permissions:** correct alignment, segment is not read-only if writing; matching native layout/endianness.

### 11.2. Do Not Confuse Confined with "Synchronized"

A confined arena ensures the segment is only accessed on the owner thread. This eliminates many kinds of shared-memory races because **there are no valid accesses from other threads**. However, an arena is **not a Java lock**:

- There is no "lock the arena so another worker can access it";
- `synchronized(arena)` does not grant permission to a non-owner;
- `volatile MemorySegment` only guarantees visibility of the **Java reference**, not changing confinement;
- `AtomicReference<MemorySegment>` only passes the reference across threads atomically, it does **not** transfer ownership.

## 12. Comparing `ofConfined`, `ofShared`, `ofAuto`, and `global`

| Factory | Access Permission | Explicit Close? | Key Point to Remember |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Only the thread that creates the arena | Yes; owner must close | Recommended for single-threaded native work with clear lifetime |
| `Arena.ofShared()` | Any thread | Yes; must coordinate all users | Shared access is not automatically data-race-free |
| `Arena.ofAuto()` | Any thread | No; close throws `UnsupportedOperationException` | Lifetime is managed by GC, non-deterministic release time |
| `Arena.global()` | Any thread | No; close throws `UnsupportedOperationException` | Memory has global lifetime, not temporary memory to be cleaned up |

**Version milestone:** `Arena.ofConfined()` appeared in the JDK 21 preview API, and FFM became a standard API in **JDK 22 (JEP 454)**. The `import java.lang.foreign.*` code snippets in this article are presented for JDK 22+. JDK 20 preview used the `Arena.openConfined()` factory and different signatures, so you cannot simply copy these examples to JDK 20 without checking that version's Javadoc.

**Do not use `ofAuto()` just to avoid calling close** when memory needs to be freed by a specific deadline. Conversely, do not use `global()` for each small request because native memory may persist until the process exits.

## 13. Arenas in FFM Downcalls: Responsibility When Passing Pointers to C

Confined arenas are commonly used to allocate a bounded-lifetime buffer and pass it to a **synchronous** native function via an FFM downcall.

Conceptual example:

~~~text
Java owner thread
    |
    +-- try (Arena arena = Arena.ofConfined()) {
    |       buffer = arena.allocate(...)
    |       downcall.invokeExact(buffer)  <-- C uses buffer during the call
    |       read result after downcall returns
    |   }  <-- owner closes arena
    |
    +-- Buffer is no longer used.
~~~

Conditions:

- The downcall is executed from the exact thread that has permission to access the confined segment; native code knows the buffer's size/alignment/ABI.
- C does not store the pointer in global state to use **after Java has closed the arena**.
- When C returns, the application must ensure no **asynchronous native worker** is still reading/writing the buffer; the "function return" event is not enough if the function only enqueues work.
- If C retains the pointer for a later callback, a **short-lived confined buffer is unsuitable**, unless the callback and lifetime are designed not to outlive the arena's scope.
- Do not use a raw `long address` to replace a verified ownership decision.

### 13.1. Example Error Scenario with an Asynchronous Native Library

~~~text
Java:
  try (Arena a = Arena.ofConfined()) {
      MemorySegment buffer = a.allocate(4096);
      native_enqueue_work(buffer); // Returns immediately, C uses it later!
  } // a.close(): buffer is freed

C worker a few milliseconds later:
  reads buffer -> use-after-free / corruption / crash
~~~

The issue is not "JNI vs. FFM method" but the **lifetime of the native allocation**. Before closing the arena, you must wait for confirmation that native work has stopped using the memory region. When sharing between native threads and Java threads is required, a shared arena with clear keep-alive/synchronization mechanisms is usually needed, or a buffer allocated and owned by the native library itself according to an appropriate API.

**Remember:** Native code does not automatically understand `Arena` and is not completely "protected" by Java exceptions if an expired pointer is used on the C side. FFM bounds/lifetime checks protect Java-side operations going through the API, and cannot guarantee safety for every raw C pointer escape.

## 14. Coordinating with ExecutorService and CompletableFuture

### 14.1. A Task Creates the Arena Where It Executes

~~~java
// Illustrates a design pattern; executor is declared/closed elsewhere.
Future<Integer> future = executor.submit(() -> {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment cell = arena.allocate(ValueLayout.JAVA_INT);
        cell.set(ValueLayout.JAVA_INT, 0, 123);
        return cell.get(ValueLayout.JAVA_INT, 0);
    }
});
~~~

This code is correct regarding **thread confinement** because the same task creates, uses, and closes the arena on the worker thread executing the task. It returns an **`Integer`** to the calling thread, not a `MemorySegment` bound to an arena about to close.

### 14.2. Do Not Return a Closed Confined Segment via a Future

~~~java
// Illustrative anti-pattern:
CompletableFuture<MemorySegment> bad = CompletableFuture.supplyAsync(() -> {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(ValueLayout.JAVA_INT);
    } // closes before caller can use result
});
~~~

The future may complete with a Java `MemorySegment` object, but the memory has already expired. Changing `return MemorySegment` to `return int[]` or a Java value materialized before close is usually more appropriate. If you truly want to return a native buffer to the caller, define proper ownership and an arena so the caller is allowed to read **within a managed lifetime**, rather than using a confined arena created and closed by the worker.

### 14.3. Characteristics of Virtual Threads

Thread confinement binds to **Java `Thread` identity**, not to an assumption that a virtual thread always stays attached to a single OS carrier thread. If a virtual thread creates an arena and continues running in that same virtual thread, reason using Java thread identity and lifetime, do not infer the carrier OS thread; in particular, do not carry a segment over to **another virtual thread** just because they run on the same carrier.

Re-check the target JDK and specific FFM/downcall library if the program combines pinning, synchronous downcalls, or native callbacks; confinement does not automatically guarantee that a native operation can be freely moved between threads.

## 15. Checking and Handling Errors in Production Code

### 15.1. Choose One Entity Responsible for Closing

For each closeable arena, document:

- Which owner thread creates the arena?
- How many code paths are allowed to access it?
- When does the work end?
- Who calls close and how is calling it exactly once guaranteed?
- Are any downcalls/native callbacks/auxiliary threads holding the pointer?
- Is data that needs to be exported copied to Java before close?

For a confined arena, the answer is simple and reviewable: "**Worker T creates the arena, T performs all accesses, T closes the arena at the end of try**". If the model no longer fits, do not try to bypass the safety check.

### 15.2. Do Not Treat Catching `WrongThreadException` as a Synchronization Strategy

Bad pattern:

~~~java
// Anti-pattern, illustration:
try {
    segment.get(ValueLayout.JAVA_INT, 0);
} catch (WrongThreadException e) {
    // Retry later or add synchronized? Does not solve owner.
}
~~~

`WrongThreadException` signals a **wrong ownership model**, not transient lock contention. Sleeping and retrying from the same non-owner thread does not make the owner change on its own. The fix is to change which thread performs the access or intentionally change the arena/lifetime.

### 15.3. Avoid Confusing `IllegalStateException` on Arena Close with Thread Permission Errors

A piece of code can violate multiple conditions simultaneously (the arena is already closed **and** running on a non-owner thread). Do not write tests forcing a specific **exception precedence order** if the Javadoc does not commit to one; to test errors accurately, separate the cases: wrong thread **while the arena is still alive**, and right thread **after the arena has closed**. The first runnable example is organized this way.

### 15.4. Consider Synchronized Data and Raw Off-Heap

If using a shared arena and multiple writers, Java `synchronized`/locks or appropriate native atomic/VarHandle mechanisms may be necessary. `get`/`set` operations on native memory **do not by default** have all the visibility/atomicity guarantees of Java field access. JMM rules for off-heap memory should be read according to the FFM package specification; if atomic updates are needed, choose supported primitives/VarHandle modes and appropriate memory ordering constraints.

**A confined arena** does not solve application-level synchronization between different Java objects; it only controls access to segments based on the owner thread.

## 16. Arena Selection Decision Scenarios

| Need | Suitable Approach | Reason |
| --- | --- | --- |
| Call a synchronous C function, create a temporary buffer on one thread | `Arena.ofConfined()` inside `try` | Simple lifetime, clear owner, deterministic cleanup |
| Each request runs independently on a thread pool | Create confined arena **inside** each task | Owner matches the thread running the task |
| Pass small results from worker to main | Copy to Java array/value/record before close | Does not transfer native pointer/arena ownership |
| A shared read-only native buffer read by multiple threads | `Arena.ofShared()`, publish then join before close | Threads are allowed to access, lifetime must be coordinated |
| Multiple threads both reading and writing the same memory | Shared arena plus synchronization/atomic design | Thread access is allowed, but memory consistency is not free |
| Data retained by native library after function return | Longer lifetime contract, synchronized ownership | Avoids premature arena close and use-after-free |
| Data needs to persist until process exit | `Arena.global()` if truly needed | No explicit close, unsuitable for temporary requests |
| No requirement for exact-time close | `Arena.ofAuto()` when acceptable | GC manages release timing, unsuitable for hard deadlines |

Selection tip: if you are still confused about "which thread is allowed to close", **revisit the ownership design** instead of randomly switching from `ofConfined` to `ofShared`.

## 17. Some Anti-Patterns and Fixes

### Mistake 1: "Passing a `MemorySegment` through a queue is thread-safe"

~~~java
// Illustrates a logic error:
MemorySegment segment = confinedArena.allocate(128);
queue.put(segment); // Only passes the Java reference.
~~~

The worker retrieves the variable from the queue, but does not thereby gain permission to read/write the backing native memory. **Fix:** queue a command for the owner to process, queue a Java snapshot, or use a shared arena with real lifetime management.

### Mistake 2: "Call `synchronized (arena)` and then close on another thread"

~~~java
// Wrong ownership despite having a monitor.
synchronized (arena) {
    arena.close(); // Non-owner still violates the confined contract.
}
~~~

A Java monitor does not change the arena's owner field. **Fix:** require the owner to execute close; use a queue/owner executor if needed.

### Mistake 3: "Just take a new slice and anyone can read it"

`segment.asSlice` does not allocate a new arena, does not transfer scope, and does not change the owner. **Fix:** copy into a Java array or a separate native shared allocation if needed.

### Mistake 4: "`asReadOnly` is definitely multi-thread accessible"

Read-only only forbids writing through the view, it does not change the owner. **Fix:** use a shared arena for intentional cross-thread access; read-only is not a solution for WrongThreadException.

### Mistake 5: "A `long` address has escaped the arena so there's no need to fear close"

A raw address does not keep the allocation alive. After close, it may point to a freed/reused region. **Fix:** ensure pointers do not escape past their lifetime; do not reconstruct `ofAddress` to bypass checks.

### Mistake 6: "GC automatically cleans up a confined arena, so `try` can be omitted"

`Arena.ofConfined()` is designed for explicit close and deterministic lifetime. Omitting close can leak native resources. **Fix:** `try-with-resources` and close on the owner thread.

### Mistake 7: "Just close the arena from a watchdog thread when the worker hangs"

A confined arena does not allow a watchdog thread to close it; furthermore, a native function might still be using the pointer. **Fix:** cooperative cancellation contract, owner worker closes when safe; if native code is uncooperative, handle timeouts at the right layer or use process isolation.

### Mistake 8: "`scope().isAlive() == true` is enough"

An alive scope does not indicate owner permission; a non-owner still cannot `get/set`. **Fix:** use proper owner design, check `isAccessibleBy` when diagnosing, and let the access API check at operation time.

### Mistake 9: "Switching to `Arena.ofShared()` automatically eliminates data races"

A shared arena allows other threads to access, but does **not** automatically coordinate mutable accesses or ensure native code processing a pointer finishes before close. **Fix:** define a publish/consume/close protocol, locks, or appropriate atomics.

## 18. Review and Testing Process

### 18.1. Review Checklist

- [ ] Compiles on **JDK 22+** with `java.lang.foreign` imports; does not mix preview API `Arena.openConfined`.
- [ ] Confined arena is created in the **exact thread** that will use it.
- [ ] All `get/set/toArray/copy` operations on native memory happen on the owner thread.
- [ ] Every closure is designed to **close exactly once** on the owner thread.
- [ ] Do not return a `MemorySegment` of a closed arena from a `Future` or public API.
- [ ] Do not use `asSlice/asReadOnly/ByteBuffer` to mask invalid access permissions.
- [ ] When using upcall/downcall, native pointers do not escape past the scope.
- [ ] When using `Arena.ofShared()`, there is synchronization and a protocol waiting for all workers to finish before close.
- [ ] Tests cover two distinct errors: non-owner access and owner access-after-close.
- [ ] Tests cover bounds, alignment, read-only, size/overflow for important inputs.
- [ ] Tests verify exceptions inside `try` still close without double-close.
- [ ] When benchmarking performance, do not trade off thread safety and lifetime just to avoid a small copy.

### 18.2. Minimum Tests

| Test | Expectation |
| --- | --- |
| Owner creates confined arena, `get/set` inside `try` | Succeeds |
| Worker calls `isAccessibleBy(worker)` on confined segment | `false` |
| Worker calls `get` on alive confined segment | `WrongThreadException` |
| Worker calls `arena.close()` on alive confined arena | `WrongThreadException`, arena is not closed |
| Owner calls `arena.close()` when no longer used | Succeeds, scope is no longer alive |
| Owner reads segment after owner close | `IllegalStateException` |
| Slice of confined segment read from worker | Also bound by owner |
| Owner `toArray` before close, then worker reads Java array after close | Succeeds |
| Shared arena, worker only reads after publish and before join/close | Succeeds |
| Shared arena, concurrent mutable access | Must test actual synchronization/visibility, not rely solely on `ofShared` |

For runnable programs, you can check versions:

~~~bash
java -version
javac -version
javac ConfinedArenaOwnerDemo.java
java ConfinedArenaOwnerDemo
~~~

The program only uses allocation and Java-side FFM segment access, so in **JDK 22** neither `--enable-preview` nor a C library is needed. `--enable-native-access=ALL-UNNAMED` relates to **restricted** FFM methods such as certain downcalls/`reinterpret`, not the default requirement for `Arena.ofConfined()` + `allocate` + `get/set` in this example.

## 19. Self-Check Questions

1. In `Arena.ofConfined()`, which thread becomes the owner?
2. A `MemorySegment` is created on main and passed into a worker lambda. Can the worker call `get(ValueLayout.JAVA_INT, 0)`? Even while main keeps the arena open?
3. When a worker calls `arena.close()` on a confined arena created by main, what type of exception is thrown?
4. If main is the owner but the arena is already closed, what error does `segment.get(...)` typically encounter?
5. Why is `scope().isAlive()` not enough to determine whether a thread is allowed to access?
6. Does creating `segment.asSlice(...)` or `asReadOnly()` change the owner?
7. Why is `AtomicReference<MemorySegment>` not a way to transfer the owner?
8. If you want to send data to a Java worker thread after the arena closes, in what order can you use `segment.toArray(...)`?
9. When should you choose `Arena.ofShared()` instead of `ofConfined()`?
10. Does `ofShared()` automatically make all off-heap `get/set` operations thread-safe?
11. If C stores a raw pointer to a segment and runs asynchronously after Java closes the arena, what consequences can occur?
12. Can you use `Arena.global()` for each short request and expect memory to be released after the request?
13. When submitting a task to an executor, should you create the confined arena in the producer or in the worker?
14. Is calling `Arena.close()` twice considered a no-op?
15. In the owner demo example, why is `aliveBeforeOwnerClose=true` even though the worker tried to close the arena?
16. Is `WrongThreadException` in `java.lang.foreign`?

**Suggested answers:** (1) The Java thread that calls the factory; (2) no, `WrongThreadException` when reading native memory; (3) `WrongThreadException`; (4) `IllegalStateException`; (5) lifetime and thread permission are two separate checks; (6) no; (7) it only transfers the Java reference, not changing the scope; (8) owner copies **before close**, worker reads the Java array afterward; (9) when multiple threads need to access the same native segment within a controlled lifetime; (10) no, synchronization is still needed; (11) use-after-free/corruption/crash; (12) unsuitable because it does not close; (13) inside the worker that actually performs the operations; (14) no, typically `IllegalStateException`; (15) wrong-thread close failed and did not close the arena; (16) no, it belongs to `java.lang`.

## 20. Official Documentation

- [Java SE 22 — `Arena` (`ofConfined`, `ofShared`, `close` factories)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- [Java SE 22 — `MemorySegment` (access, `isAccessibleBy`, scope, slices)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [Java SE 22 — `MemorySegment.Scope` (lifetime, `isAlive`)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [Java SE 22 — `WrongThreadException` in `java.lang`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/WrongThreadException.html)
- [Java SE 22 — package `java.lang.foreign`: memory model, restricted methods](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- [JEP 454 — Foreign Function & Memory API (Final), JDK 22](https://openjdk.org/jeps/454)
- [Java Developers — Access Off-Heap or On-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/)

**Conclusion:** `Arena.ofConfined()` is a strong choice for temporary native memory when **one Java thread** can create, access, and close the entire arena. It enforces **both thread-based access permissions** and **memory region lifetime**. If results must be passed to another thread, prefer copying into Java data or letting each worker create its own arena; when shared native memory access is genuinely needed, use `Arena.ofShared()` with proper synchronization and lifetime management. Do not use sharing Java references, slices, read-only views, or raw pointers as a way to bypass confined arena limits.
