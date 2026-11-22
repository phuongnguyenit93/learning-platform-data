# Why Does Arena Manage a Shared Lifetime for Multiple Memory Regions?

## 1. Context: multiple native memory regions, one termination point

In Java, regular objects are managed by the Java heap and the garbage collector (GC). When interacting with native code, we often need **off-heap memory**: memory outside the Java heap to hold C structs, byte arrays, NUL-terminated strings, or regions returned from a foreign function. If managed by allocating each region individually and having to remember to free each one, code is prone to leaks, double-free, and use-after-free.

The Foreign Function & Memory API (FFM) solves an important part of the problem with two concepts:

- `MemorySegment`: a **view with size, bounds, and lifetime information** over a memory region. A segment is how Java performs checked memory access.
- `Arena`: an object that **allocates and defines the shared lifetime** of the native memory segments created from that arena.

Example:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment header = arena.allocate(16);
    MemorySegment payload = arena.allocate(128);
    MemorySegment checksum = arena.allocate(ValueLayout.JAVA_INT);

    // All three segments belong to the same arena scope.
    // Process data while the arena is still open ...
} // close: all three memory regions managed by the arena become invalid
~~~

This is an **illustrative snippet inside a Java method**, requiring imports of `java.lang.foreign.Arena`, `MemorySegment`, and `ValueLayout`. There is no need to call `free(header)`, `free(payload)`, and `free(checksum)` separately. `try-with-resources` closes exactly **one arena**, making the native regions owned by that arena no longer accessible through FFM segments.

**Key point:** An arena groups memory by **usage lifetime**, not necessarily packing all allocations into a single contiguous block of bytes. Three `allocate` calls may return three separate native regions, but they share the **same temporal boundary**: the scope of the arena.

### Lesson Objectives

After studying this lesson, you will be able to:

1. Explain why sharing an arena scope helps manage a group of memory regions consistently.
2. Distinguish between a **live Java reference** and **valid native memory**.
3. Understand the `allocate` → `MemorySegment.scope()` → `Arena.close()` mechanism and use-after-close checks.
4. Choose `Arena.ofConfined()`, `ofShared()`, `ofAuto()`, or `global()` based on ownership and lifetime.
5. Write and run complete examples on **JDK 22+**, where the FFM API is finalized.
6. Design APIs that accept an `Arena` or return multiple `MemorySegment` instances without letting pointers “escape” their valid lifetime.
7. Identify wrong-thread errors, premature close, concurrent access/close, and lifetime mismatches when calling native code.

## 2. JDK Version and API Group Used

This lesson uses **`java.lang.foreign`, the official API since JDK 22** (JEP 454). Run the examples with JDK 22 or later; **`--enable-preview` is not required** for the simple memory allocation/access operations here.

Do not copy the code verbatim into JDK 17 and expect it to compile: in JDK 17, foreign memory access was in a **different incubator API**, while JDKs 19–21 went through preview versions with changing signatures. This example intentionally chooses the stable API for consistent results.

Main types:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
~~~

| Component | Responsibility |
| --- | --- |
| `Arena` | Creates and owns native allocations, defines scope/lifetime and thread rules |
| `SegmentAllocator` | Abstract interface for allocation; `Arena` is also a `SegmentAllocator` |
| `MemorySegment` | Describes a memory region, byte size, and accessibility; every read/write undergoes spatial/temporal checks |
| `MemorySegment.Scope` | Liveness state of a scope, with `isAlive()` |
| `ValueLayout.JAVA_INT`, `JAVA_LONG`... | Size, alignment, and primitive access type |
| `MemoryLayout` | Describes complex native structures, enabling layout-based allocation instead of manual offset calculation |

**Distinction:** A `MemorySegment` can be a **heap segment** such as `MemorySegment.ofArray(int[])` or a **native segment** from `arena.allocate(...)`. A heap segment created from a Java array does not automatically become “memory owned by an arena”. This lesson focuses on **segments allocated from an Arena**.

## 3. A Shared Scope Is a Lifetime Contract

An arena has **one arena scope**. By API contract, every segment allocated by the arena is attached to that scope:

~~~text
                  Arena A
                     |
                     v
                Arena A.scope()
                   / | \
                  /  |  \
                 v   v   v
           segment 1  2   3
           (header) (body) (footer)
                 |   |   |
                 +---+---+
                     |
                     v
               arenaA.close()
                     |
              scope.isAlive() == false
                     |
         All 3 segments are inaccessible
         via the FFM API; native backing memory
         owned by the arena is freed
~~~

When `arena.close()` is called and the call **completes normally**:

- The arena's scope is no longer alive (`arena.scope().isAlive() == false`).
- **All** segments attached to that scope become invalid for FFM access.
- The native memory regions allocated by the arena are deallocated according to the contract.
- A segment may still exist as a **Java object/reference** in a variable, collection, field, or record, but that **does not restore** the invalidated memory region.
- Accessing memory through an out-of-scope segment throws `IllegalStateException`, rather than becoming a native pointer silently used after `free` in safe APIs.

Logic error example:

~~~java
MemorySegment escaped;

try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(ValueLayout.JAVA_INT);
    escaped.set(ValueLayout.JAVA_INT, 0, 42);
}

int value = escaped.get(ValueLayout.JAVA_INT, 0);
// IllegalStateException: arena scope has already closed.
~~~

This is an example explaining behavior, not a complete program. Even though `escaped` still points to a Java `MemorySegment` object, reading the native memory is **no longer valid**.

### 3.1. “Shared Scope” Does Not Mean “Shared Address”

Three segments allocated from the same arena **do not implicitly share bytes** or form three parts of a contiguous block. The `Arena.allocate` API guarantees that separate allocations **do not overlap** under the usual allocator contract. What is shared is **scope/lifetime**, not content or address.

~~~text
Arena A
  segment header:   [ address X ... X+15 ]
  segment body:     [ address Y ... Y+127 ]
  segment trailer:  [ address Z ... Z+3 ]

X, Y, Z are not required to be contiguous.
But A.close() terminates all three regions.
~~~

If you need multiple “views” pointing to the bytes of **one allocation**, use `segment.asSlice(...)`; a slice shares backing memory **and** inherits the scope of the original segment. Do not confuse “allocations in the same arena” with “slices of the same allocation”.

### 3.2. Two Important Forms of Safety

An FFM segment has:

- **Spatial bounds:** no reading/writing past `segment.byteSize()`. A wrong offset typically causes `IndexOutOfBoundsException`, and wrong alignment may cause `IllegalArgumentException`.
- **Temporal bounds:** no reading/writing once the scope is no longer alive. A lifetime violation typically causes `IllegalStateException`.

Arena carries a major responsibility for **temporal safety**: a single close call shuts down access for the **entire group**.

However, this safety applies to **FFM access through a Java segment**. If you obtain a raw address, pass it to C, and keep the native pointer after the arena closes, **C can use a dangling pointer** and cause dangerous errors; FFM cannot check every raw pointer access path on the native side.

## 4. Why Is Grouping Multiple Memory Regions into the Same Arena Reasonable?

Suppose a C library call needs:

- A buffer for the header.
- A buffer for the data.
- A buffer for a filename or NUL-terminated UTF-8 string.
- A result struct.
- A temporary region for conversion operations.

If each region had a different owner, the code would need many cleanup statements and error-branch handlers. When an intermediate step throws an exception, some buffers might already be allocated without yet being added to the cleanup list.

Pattern using a single arena:

~~~java
void processOneRequest() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment header = arena.allocate(32);
        MemorySegment payload = arena.allocate(2048);
        MemorySegment result = arena.allocate(ValueLayout.JAVA_LONG);

        // Write prepared data.
        // Call synchronous native function, ensuring native does not retain pointers after returning.
        // Read result while arena is still alive.
    } // All native allocations for the request are reclaimed together.
}
~~~

This is an **illustrative snippet**, containing no actual native downcall. The benefit is **one lifetime boundary corresponding to one unit of work**.

### 4.1. Three Main Benefits

**First — auditable ownership.** You can state: “All temporary data for request R exists from the opening of Arena R until the end of processing R.” Code review only needs to check the open/close points and where references are shared.

**Second — cleanup on exception.** `try-with-resources` automatically calls `close()` when the block exits normally or via an exception, reducing the risk of forgetting to free on an error branch. One arena can manage many allocations without requiring each buffer to have its own `finally`.

**Third — avoiding partial use of an expired dataset.** If three segments share a scope, closing makes the entire set invalid for access together. You do not end up in a state where “the header is already freed while the payload is still treated as data of the same request.” Of course, **the application must still synchronize** if another thread is using those segments.

### 4.2. Ownership Mindset: “Borrowing” Rather Than “Transferring Ownership”

When a helper receives an `Arena` and allocates segments, it usually **borrows allocation capability**, and should not automatically close the caller's Arena:

~~~java
record Buffers(MemorySegment header, MemorySegment payload) { }

static Buffers newBuffers(Arena arena) {
    return new Buffers(arena.allocate(16),
                      arena.allocate(128));
}

static void useBuffers() {
    try (Arena arena = Arena.ofConfined()) {
        Buffers b = newBuffers(arena);
        b.header().set(ValueLayout.JAVA_INT, 0, 42);
        int x = b.header().get(ValueLayout.JAVA_INT, 0);
        System.out.println(x);
    } // caller closes Arena, both buffers become invalid.
}
~~~

This is an **illustrative source snippet inside a class**, not a standalone program. The key point: `newBuffers` does not call `arena.close()`, because the **caller** is responsible for the lifetime.

**Do not** let a helper create a local confined arena with `try-with-resources` and then return a `MemorySegment` outside:

~~~java
static MemorySegment wrongFactory() {
    try (Arena arena = Arena.ofConfined()) {
        return arena.allocate(16);
    } // closes before the caller can use the segment
}
~~~

This is a **wrong** example; do not put it in production. The returned Java value still exists, but the backing memory is no longer valid.

## 5. Runnable Program: One Arena, Three MemorySegments

Experiment goal: allocate **two independent native regions** and create **one slice**; verify all three have the same scope, then close the Arena once and observe that all become unreadable.

### 5.1. File `ArenaLifetimeDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class ArenaLifetimeDemo {
    private ArenaLifetimeDemo() {
    }

    private static void checkClosed(
            String name, MemorySegment segment) {
        try {
            segment.get(ValueLayout.JAVA_INT, 0);
            System.out.println(name + ": unexpectedly accessible");
        } catch (IllegalStateException ex) {
            System.out.println(name + ": IllegalStateException");
        }
    }

    public static void main(String[] args) {
        MemorySegment first;
        MemorySegment second;
        MemorySegment secondView;

        try (Arena arena = Arena.ofConfined()) {
            first = arena.allocate(ValueLayout.JAVA_INT);
            second = arena.allocate(ValueLayout.JAVA_INT);

            first.set(ValueLayout.JAVA_INT, 0, 10);
            second.set(ValueLayout.JAVA_INT, 0, 32);

            // Alias the same backing memory as second.
            secondView = second.asSlice(
                    0, ValueLayout.JAVA_INT.byteSize());

            int sum = first.get(ValueLayout.JAVA_INT, 0)
                    + second.get(ValueLayout.JAVA_INT, 0);

            System.out.println("sum=" + sum);
            System.out.println(
                    "view=" + secondView.get(ValueLayout.JAVA_INT, 0));

            boolean sameScope =
                    first.scope() == second.scope()
                    && second.scope() == secondView.scope();
            System.out.println("same scope=" + sameScope);
            System.out.println(
                    "alive inside=" + arena.scope().isAlive());
        } // AutoCloseable.close() is called exactly once.

        System.out.println(
                "alive after=" + first.scope().isAlive());

        checkClosed("first", first);
        checkClosed("second", second);
        checkClosed("view", secondView);
    }
}
~~~

### 5.2. Compile, Run, and Stdout

Use **JDK 22+**:

~~~bash
javac ArenaLifetimeDemo.java
java ArenaLifetimeDemo
~~~

Stdout:

~~~text
sum=42
view=32
same scope=true
alive inside=true
alive after=false
first: IllegalStateException
second: IllegalStateException
view: IllegalStateException
~~~

Line-by-line explanation:

1. `first` stores `10`, `second` stores `32`, so the sum is `42`.
2. `secondView` is a slice of `second`, so it reads the same bytes and gets `32`.
3. Both independent allocations are attached to `arena.scope()`; the slice inherits that scope.
4. Inside `try`, the scope is alive.
5. Upon exiting `try`, a successful `Arena.close()` makes the scope no longer alive.
6. `first`, `second`, and `secondView` are all denied access; the Java references still exist, but the native backing memory is invalidated.

The example catches `IllegalStateException` **only to demonstrate temporal safety**. In production, do not attempt to access after close to ask “is it closed yet?”; design ownership so an expired object cannot be misused, and only use `scope().isAlive()` for diagnostics when appropriate.

### 5.3. Why Does `first.scope().isAlive()` Alone Tell Us Something?

In the example, all three segments are attached to the same scope, so the `isAlive()` state of that scope applies to the entire group. This is precisely the **point of centralized lifetime management**. However, checking `isAlive()` does not make multithreaded code safe: another thread can close right **after the check** and before the read/write. You must coordinate ownership and actual synchronization.

## 6. Another Arena Is Not Closed Along with the First Arena

Lifetime sharing is a relationship **within one arena**, not a global JVM state. You can keep one arena longer and use a shorter arena for temporary data:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class TwoArenasDemo {
    public static void main(String[] args) {
        MemorySegment temporary;

        try (Arena longLived = Arena.ofConfined()) {
            MemorySegment persistentForOperation =
                    longLived.allocate(ValueLayout.JAVA_INT);
            persistentForOperation.set(
                    ValueLayout.JAVA_INT, 0, 100);

            try (Arena shortLived = Arena.ofConfined()) {
                temporary = shortLived.allocate(ValueLayout.JAVA_INT);
                temporary.set(ValueLayout.JAVA_INT, 0, 7);
                System.out.println(
                        "temp=" + temporary.get(ValueLayout.JAVA_INT, 0));
            }

            System.out.println(
                    "short alive=" + temporary.scope().isAlive());
            System.out.println(
                    "long alive="
                            + persistentForOperation.scope().isAlive());
            System.out.println(
                    "long value="
                            + persistentForOperation.get(
                                    ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Run:

~~~bash
javac TwoArenasDemo.java
java TwoArenasDemo
~~~

Stdout:

~~~text
temp=7
short alive=false
long alive=true
long value=100
~~~

Lesson learned: `shortLived.close()` only invalidates **segments belonging to shortLived**, without affecting `persistentForOperation` allocated by `longLived`. “One arena for everything” is not a mandatory rule; using **multiple arenas matching actual lifetimes** is often more appropriate.

Do not mistake nested `try` blocks for nested scopes with a parent-child relationship: two arenas created with `ofConfined()` are **two independent owners**, with no dependent reclamation relationship just because the code is written nested.

## 7. Arena Types and Lifetime Selection

JDK 22 provides four common factories:

| Type | Created via | Manual close? | Accessible threads | When freed |
| --- | --- | --- | --- | --- |
| Confined | `Arena.ofConfined()` | **Yes** | **Owner thread only** | When `close()` succeeds |
| Shared | `Arena.ofShared()` | **Yes** | **Multiple threads** | When `close()` succeeds |
| Automatic | `Arena.ofAuto()` | **No** | Multiple threads | Reclaimed by GC at an unspecified time after the arena and segments are no longer reachable |
| Global | `Arena.global()` | **No** | Multiple threads | Native regions allocated by the global arena are **not automatically reclaimed** by the arena |

Both **confined** and **shared** have a **bounded lifetime with explicit close**. Both **automatic** and **global** have no explicit close, but **automatic** can be reclaimed by the GC in the future, whereas **global** has a lifetime unbounded by the program.

### 7.1. `Arena.ofConfined()`: single-thread ownership

A confined arena is owned by the thread that creates it. Only the owner thread may allocate, access segments, and close. If another thread reads a segment or tries to close the arena, the API may throw `WrongThreadException`.

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(ValueLayout.JAVA_LONG);
    data.set(ValueLayout.JAVA_LONG, 0, 123L);

    // Reading on the owner thread: valid.
    long value = data.get(ValueLayout.JAVA_LONG, 0);
}
~~~

This is a non-standalone snippet. Confined is typically suitable for sequentially processed requests, short synchronous native calls, temporary codecs/buffers, or single-threaded parsing.

It is **not** a synchronized lock: owner confinement lets the JVM check for the valid thread; it does not automatically marshal execution to the owner when called from another thread.

### 7.2. `Arena.ofShared()`: one lifetime for multiple threads

A shared arena does not restrict access to a single owner. Different threads can use segments allocated by it, but **data access still requires synchronization** to avoid data races and visibility problems.

~~~java
try (Arena arena = Arena.ofShared()) {
    MemorySegment value = arena.allocate(ValueLayout.JAVA_LONG);

    Thread writer = new Thread(
            () -> value.set(ValueLayout.JAVA_LONG, 0, 123L));

    writer.start();
    writer.join(); // Establishes happens-before for the write result.

    System.out.println(
            value.get(ValueLayout.JAVA_LONG, 0));
} // Only close after the writer has finished.
~~~

This is a snippet inside a method that declares or handles `InterruptedException`. `Thread.join()` prevents closing while the worker is still using the segment and provides a happens-before relationship from the writer to the waiting thread. **A shared scope does not automatically make reads/writes atomic**, nor does it protect two threads writing concurrently.

### 7.3. `Arena.ofAuto()`: GC manages the shared lifetime

~~~java
Arena arena = Arena.ofAuto();
MemorySegment a = arena.allocate(64);
MemorySegment b = arena.allocate(128);
// Do not call arena.close(): automatic arena does not support manual close.
~~~

An automatic arena has a shared lifetime for a group of allocations, but **no deterministic deallocation time**. The memory it allocates can only be reclaimed after the arena **and its associated segments** are no longer reachable; when the GC runs is not controlled by the application.

Do not use `ofAuto` just because you “don't want to write try-with-resources” if the service has high native memory pressure: off-heap memory may stay around longer than expected. When deterministic cleanup is needed, confined/shared with explicit close is better.

### 7.4. `Arena.global()`: practically unbounded lifetime

~~~java
MemorySegment permanent = Arena.global().allocate(1024);
// There is no close for the global arena.
~~~

The global arena can be used for data regions that need to live **for the entire lifetime of the process/VM**, such as static native tables not reclaimed per request. However, **every allocation from global is a native region not reclaimed by Arena**, so repeated per-request allocation into the global arena is an easy way to accumulate off-heap memory.

Do not use global as “the easiest solution to avoid IllegalStateException”. Get **ownership and lifetime** right instead.

## 8. Multithreaded Program Demonstrating Shared and Confined

The following is complete source code runnable on JDK 22+, with deterministic output. It demonstrates:

- `ofShared` allows another thread to write to a segment.
- `join()` completes the work before closing the shared arena.
- `ofConfined` rejects a non-owner thread accessing a segment.

### 8.1. File `ArenaThreadsDemo.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class ArenaThreadsDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofShared()) {
            MemorySegment shared = arena.allocate(ValueLayout.JAVA_INT);

            Thread worker = new Thread(
                    () -> shared.set(ValueLayout.JAVA_INT, 0, 77),
                    "arena-writer");
            worker.start();
            worker.join();

            System.out.println(
                    "shared read=" + shared.get(ValueLayout.JAVA_INT, 0));
        }

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment confined =
                    arena.allocate(ValueLayout.JAVA_INT);

            Thread worker = new Thread(() -> {
                try {
                    confined.get(ValueLayout.JAVA_INT, 0);
                    System.out.println("unexpected success");
                } catch (WrongThreadException ex) {
                    System.out.println("confined wrong thread");
                }
            }, "foreign-thread");

            worker.start();
            worker.join();
        }
    }
}
~~~

### 8.2. Compile and Run

~~~bash
javac ArenaThreadsDemo.java
java ArenaThreadsDemo
~~~

Stdout:

~~~text
shared read=77
confined wrong thread
~~~

In `java.lang`, `WrongThreadException` is implicitly imported like other classes in `java.lang`. The writer thread `join`ed before the shared arena closed, so the example has no race between read and close. The thread accessing the confined segment runs while the arena is still alive, so the thread check is triggered and prints a consistent message.

**Multithreaded interaction:** `Arena.ofShared()` allows using segments across multiple threads; it **does not replace** `synchronized`, locks, `VarHandle` with appropriate access modes, or task coordination mechanisms.

## 9. Shared Close and Consequences for Aliases/Slices

When there is one native allocation:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(64);
    MemorySegment topHalf = block.asSlice(0, 32);
    MemorySegment bottomHalf = block.asSlice(32, 32);

    // topHalf and bottomHalf are non-overlapping views
    // on the SAME backing allocation, with the same scope.
}
~~~

Here **one** allocation creates **three Java segment views**. When the arena closes, all three become invalid. This also holds when a segment is:

- Placed in a `List<MemorySegment>` or stored in an object field.
- Returned from a helper method (if the helper does not close the arena).
- Converted into a slice or read-only view.
- Passed temporarily to a processing method and stored in multiple alias variables.

A reference does not own an independent “extra lease on life.” It is the **arena's scope** that decides when accesses through those views become invalid.

### 9.1. Do Not Rely on `isAlive()` Checks to Guard Against Concurrent Close

The following pattern has a race:

~~~java
// Pseudocode: threads A and B may run concurrently.
if (segment.scope().isAlive()) {
    // Thread B can close the shared arena right after the check.
    int value = segment.get(ValueLayout.JAVA_INT, 0);
}
~~~

This is an **example of incorrect synchronization**. `isAlive()` returns the state at the moment of the call and **does not lock the scope** for subsequent operations. With a shared arena, ensure all users have finished their work before the owner calls close, for example using `Future.get()`, `CountDownLatch`, `Thread.join()`, or an appropriate lifecycle lock.

The `Arena.close()` specification even allows `IllegalStateException` if a related segment is being concurrently accessed via a special FFM path (such as a native downcall). Do not use try/catch around close as a primary coordination mechanism; **finish using the memory regions first, then close**.

### 9.2. Arena Close Is Not an Idempotent Operation

~~~java
Arena arena = Arena.ofConfined();
arena.close();
arena.close(); // IllegalStateException: already closed previously.
~~~

This is an illustration. Therefore, design a clear owner to call close exactly once, typically via `try-with-resources`. Do not pass an arena to two components that both believe they are the owner and both actively close it.

## 10. Good API Design: Caller Owns the Arena

FFM supports separating **who provides the place to store results** from **who produces the results**. A service can accept an `Arena`/`SegmentAllocator` as a parameter and allocate multiple results with a **lifetime decided by the caller**.

Example of a parser creating two data regions:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class RequestBuffers {
    public record Parts(MemorySegment flags, MemorySegment count) { }

    public static Parts create(Arena arena) {
        MemorySegment flags = arena.allocate(8);
        MemorySegment count = arena.allocate(ValueLayout.JAVA_INT);

        flags.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
        count.set(ValueLayout.JAVA_INT, 0, 3);
        return new Parts(flags, count);
    }

    public static void main(String[] args) {
        try (Arena arena = Arena.ofConfined()) {
            Parts p = create(arena);
            byte active = p.flags().get(ValueLayout.JAVA_BYTE, 0);
            int count = p.count().get(ValueLayout.JAVA_INT, 0);

            System.out.println("active=" + active);
            System.out.println("count=" + count);
        }
    }
}
~~~

Run:

~~~bash
javac RequestBuffers.java
java RequestBuffers
~~~

Stdout:

~~~text
active=1
count=3
~~~

Even though `create` makes **two native allocations**, it does **not** own closing the arena. The caller wraps the entire request in one scope. The `Parts` record is a normal Java object and can hold references; however, after close, the segments inside the record remain inaccessible.

**The API contract should be documented:** “The returned segments are valid only while the caller-provided arena remains alive, and only from threads permitted by the arena.”

If a helper does not need to know the thread/close policy, it can accept `SegmentAllocator` instead of `Arena`. However, not every `SegmentAllocator` has the same lifetime/memory non-overlap guarantees as `Arena`; do not make arbitrary assumptions when the interface is more abstract.

## 11. When to Use One Arena, When to Separate Arenas?

There is no rule saying “always one arena for the whole application.” Use a shared scope **when the data expires at the same time**.

| Data type | Appropriate lifetime | Recommendation |
| --- | --- | --- |
| Header, payload, checksum of a synchronous native request | From request start to request end | One `ofConfined()` |
| Buffers of batch parsing on the same thread | Entire batch | One `ofConfined()` for the batch, not one arena per item |
| Segments in a task using multiple Java threads | Until all workers have completed | One `ofShared()`; close after join/future |
| Temporary buffer in a private helper that does not need to live with the request | Only inside the helper | A shorter arena, separate scope |
| Cached data that must live across multiple requests | Longer than one request | An arena with a longer-lived owner and explicit close |
| Regions where end of use cannot be controlled and GC can reclaim later | No precise cleanup needed | Consider `ofAuto()`, monitor off-heap pressure |
| Regions that truly live until VM/process exit | Entire application lifetime | `global()`, weigh accumulation risk |

For example, a batch of 1,000 records: if each record uses 3 allocations with the batch's lifetime, creating **one arena for the batch** keeps cleanup short and easy to verify. But if 10 records need to be kept as a cache after the batch, they **should not** remain in the batch arena and get closed; copy the data to keep into a longer-lived cache arena.

### 11.1. Copy to Transfer Ownership, Do Not Just Assign Variables

If data needs to outlive the source arena, you **cannot** extend its lifetime by assigning it to a field or record:

~~~java
// CONCEPTUALLY WRONG: saved points to a region belonging to temp.
MemorySegment saved;
try (Arena temp = Arena.ofConfined()) {
    saved = temp.allocate(16);
}
// saved is already invalid.
~~~

The right approach is to **reallocate in the destination arena** and copy bytes while both scopes are still alive:

~~~java
// Pseudocode placed in an owner thread's method.
try (Arena longLived = Arena.ofConfined()) {
    MemorySegment saved = longLived.allocate(16);

    try (Arena shortLived = Arena.ofConfined()) {
        MemorySegment temp = shortLived.allocate(16);

        // Prepare temp while it is still alive.
        // Copy into saved while both scopes are still valid.
        saved.copyFrom(temp);
    }

    // saved is still valid: longLived's scope is alive.
}
~~~

The above is illustrative; `MemorySegment.copyFrom` copies bytes within appropriate bounds and does not replace ownership rules for raw pointers embedded inside a struct. **Critically important:** if the copied struct contains a C address field pointing to `shortLived` memory, copying **bytes** to `longLived` **does not automatically make the inner pointer valid**. You must deep-copy/adjust pointer fields according to the native API contract.

### 11.2. Separate Arenas When Lifetimes Differ

Wrong design:

~~~text
Request Arena (contains both temp buffers and long-lived cache)
    |
    +-- temporary A   (should die after request)
    +-- temporary B   (should die after request)
    +-- cached C      (must live across multiple requests)
    |
    +-- close request
               |
               +-- cached C invalidated too early
~~~

Better design:

~~~text
Request Arena: temp A, temp B  --> close after request
Cache Arena:   cached C       --> close when cache is disposed
~~~

An arena does not infer which data is “more important.” If you attach multiple segments to the same scope, **you are actively choosing a single shared expiration point** for all of them.

## 12. Near-Real-World Example: Preparing Arguments for a Native Call

Suppose Java wants to call a C library with the conceptual API:

~~~c
int process_request(
    const char *name,
    const unsigned char *bytes,
    size_t length,
    int *result);
~~~

This is an **illustrative prototype**; this lesson does not implement or link this C library. A single call may need:

- A NUL-terminated `name` string in native memory.
- A native `bytes` buffer.
- A `result` region for output.
- Some additional temporary structs.

The Java side prepares these using the same arena (illustrative, **not a self-running program**):

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment name = arena.allocateFrom("report.bin");

    byte[] input = { 1, 2, 3, 4 };
    MemorySegment bytes = arena.allocateFrom(
            ValueLayout.JAVA_BYTE, input);

    MemorySegment result = arena.allocate(ValueLayout.JAVA_INT);

    // Make synchronous downcall while arena is still alive.
    // FunctionDescriptor and MethodHandle must match the native ABI.
    // After the downcall returns, read result.
} // Terminate all 3 native regions within the same lifetime boundary.
~~~

On JDK 22, `arena.allocateFrom(String)` creates a NUL-terminated UTF-8 native string. `arena.allocateFrom(ValueLayout.JAVA_BYTE, input)` allocates and copies from the byte array to native memory. Allocation/copy overhead still exists; Arena primarily solves **lifetime**, not promising every conversion is zero-copy.

**Mandatory condition:** The synchronous C function being called must **not retain these pointers after returning**. If native code starts a background job or stores pointers in static state, the arena must stay alive **at least until native code confirms it no longer uses the pointers**. Closing the arena right after a “submit_async” function returns would be a potential use-after-free on the C side.

### 12.1. Downcall, Callback/Upcall, and Lifetime

Several other FFM resources also accept an arena to bind their lifetime, such as an upcall stub or native library symbol lookup. When a callback pointer is passed to C, it is only valid within the scope bound by the API/contract. You must close the arena **after** native code stops invoking the callback. Do not close the arena and expect C to see an `IllegalStateException`; C only has a machine address and can crash or corrupt memory.

The relationship should be:

~~~text
Java owner creates arena
     |
     +-- allocate inputs/outputs
     +-- create native callback stub if needed
     |
     +-- native process uses synchronously
     |   or async with an explicit completion handshake
     |
     +-- native confirms it has stopped using pointers/stubs
     |
     +-- arena.close()
~~~

For **restricted FFM APIs** such as certain linker/symbol lookup and reinterpret operations, the JDK has a mechanism to grant native access permissions. Those permissions are a separate topic; **the four runnable examples only allocate/read/write using the Java 22 API and do not require `--enable-native-access`**. Do not conflate the requirements of restricted downcall APIs with plain `Arena.allocate` usage.

## 13. Thread Confinement and Close in a Shared Arena

### 13.1. Confined: safe management by a single owner

A confined arena avoids many race scenarios: the JVM only allows the owning thread to access memory segments and close. This suits temporary data of a native call executed sequentially on one thread.

But if you pass a segment to another worker:

~~~java
// Illustrative code snippet inside the owner thread.
Arena a = Arena.ofConfined();
MemorySegment s = a.allocate(ValueLayout.JAVA_INT);

Thread other = new Thread(() -> {
    s.get(ValueLayout.JAVA_INT, 0); // WrongThreadException
});
other.start();
other.join();

a.close();
~~~

The `join()` call here assumes the method handles `InterruptedException`. If the exception on the worker is uncaught, it prints a stack trace; **do not run this snippet as a deterministic-stdout demo**; use `ArenaThreadsDemo` in section 8.

`WrongThreadException` does not mean the arena has closed; it indicates that the current thread **is not permitted to access** that memory region.

### 13.2. Shared: easier to share, but close needs a protocol

A shared arena allows multiple threads to access it, but if one thread closes while another thread is still running a native downcall involving a segment, the JVM may block the invalid close with `IllegalStateException`; even though the FFM runtime detects some races, **do not rely on exceptions for synchronization**.

A recommended pattern:

1. The owner stops accepting new tasks that use the arena.
2. Send a stop request or wait for in-flight futures/threads.
3. Confirm all code paths using segments/upcall pointers have completed.
4. Call `arena.close()` once.
5. Forbid any new tasks from using expired memory segments.

If threads concurrently write to the same memory, you also need **data** synchronization rules, independent of the arena being shared. Memory safety regarding lifetime does not automatically equal thread safety of the algorithm.

## 14. MemorySegment Is a View, Not the Resource Owner

A helpful design approach is to separate three questions:

1. **Who owns the resource?** The Arena (or exceptions: heap array, external allocation with its own owner).
2. **Which view reads/writes it?** One or more `MemorySegment` instances, slices, or read-only views.
3. **When does the resource expire?** When the arena scope closes or according to the automatic/global policy.

~~~text
                         Lifetime owner
                              Arena
                                |
                        (a single scope)
                                |
          +---------------------+-------------------+
          |                     |                   |
       Allocation 1         Allocation 2       Allocation 3
          |                     |                   |
       Segment A            Segment B           Segment C
          |                     |
          +-- Slice A1         +-- read-only B1
          +-- Slice A2
                                |
                    Arena closes -> all views over
                    those allocations become invalid
~~~

This is why **one Arena managing multiple memory regions** is stronger than a variable holding a pointer: lifetime is defined at the **resource-group level**, while each segment is a **checked view**.

### 14.1. Do Not Confuse Lifetime with Java Object GC

- **Confined/shared:** Keeping a `MemorySegment` Java object in a field **does not prevent** an explicit `arena.close()` from invalidating the backing memory.
- **Automatic:** Lifetime is managed by the reachability of the arena **and its segments**; the GC decides when native memory is reclaimed.
- **Global:** Lifetime is not terminated by `close()`; simply losing the Java reference does not mean the native allocation is deallocated by the arena.
- **Heap segment:** The underlying Java array continues to have its lifetime managed by the Java heap/GC, not by a native arena you just closed.

FFM reduces use-after-free risk **in Java-level FFM accesses**, but does not replace proper ownership management when C holds a raw pointer.

## 15. Common Mistakes and How to Fix Them

| Mistake | Consequence | Proper fix |
| --- | --- | --- |
| Returning `MemorySegment` from a helper's own `try (Arena arena=...)` | Caller receives an expired segment | Caller creates/closes the arena; helper takes the arena as a parameter |
| Keeping segments in a cache when the arena is per-request | Cache holds Java references that are no longer accessible | Separate a long-lived cache arena or copy valid data |
| Using `Arena.global()` per request | Native memory accumulates because global has no cleanup | Confined/shared per request with explicit close |
| Treating `Arena.ofAuto()` as equivalent to immediate close | Off-heap memory is reclaimed at an unspecified time | Explicit close when predictable cleanup is required |
| Reading `segment.get(...)` after `arena.close()` | `IllegalStateException` | Organize scope with try-with-resources |
| Passing a confined segment to another thread | `WrongThreadException` | Keep on owner thread or choose a shared arena |
| Using a shared arena and assuming it is automatically thread-safe | Data race / visibility bugs | Appropriate lock, join, futures, or VarHandle |
| Closing a shared arena while a worker/downcall still uses data | Access errors, close may fail, dangerous with C raw pointers | Use a completion handshake and close after all users finish |
| Calling `close()` twice on an explicit arena | `IllegalStateException` | One owner, one close |
| Copying struct bytes while keeping old addresses inside the struct | Dangling native pointer after source closes | Deep copy and update pointer fields |
| Assuming allocations in the same arena must be contiguous | Wrong C offset calculation, out-of-bounds reads | Respect each segment's address/byteSize |
| Believing Java GC always frees off-heap immediately | Wrong RAM estimates, logical leaks | Use try-with-resources and measure native footprint |

### 15.1. Which Exceptions Should Be Distinguished?

- `IllegalStateException`: usually a closed scope, or calling close a second time; can also occur when closing while a resource is being accessed in certain cases.
- `WrongThreadException`: accessing/closing a confined arena from the wrong thread.
- `IndexOutOfBoundsException`: offset/length outside segment bounds.
- `IllegalArgumentException`: invalid alignment or allocation size.
- `UnsupportedOperationException`: attempting to `close()` an automatic/global arena.
- `OutOfMemoryError`: insufficient resources to allocate; must consider native memory pressure, not just the Java heap.

Do not catch all of these exceptions and then keep “trying to use” a segment whose state is uncertain. Review the scope, ownership, and shutdown rules instead.

## 16. Lifetime Design Checklist in Native Interoperability Projects

Before introducing an Arena into a public API or JNI/FFM bridge, answer:

- Do the segments **truly expire at the same time**? If not, split arenas.
- Who is the **sole owner** allowed to close the arena, and where do they close it?
- Is `try-with-resources` used to guarantee cleanup even when Java code throws an exception?
- Does any Java object/collection/cache hold a segment **longer than the scope**?
- Does any native code retain a raw pointer after the call returns or after a coroutine/task has completed?
- If multithreaded: does the arena need to be **shared** or can it be confined? Have data races been prevented and workers guaranteed to finish before close?
- Are there any slice/read-only aliases that might mislead users into thinking they have a separate allocation/lifetime?
- Are `ofAuto`/`global` being used just to avoid solving ownership?
- Have structs/arrays containing pointers to other allocations been **deep-copied or given the same lifetime**?
- On cancellation, timeout, or exception, could any thread/native code still hold a pointer?
- Have native memory footprint, lifetime, and concurrency behavior been measured under realistic workloads?

**Principle:** An arena should be tied to a **unit of work** with a clear lifetime (a request, batch, transaction, native invocation, cache object). When the unit of work ends, **closing the arena** declares “all memory regions belonging to this work are no longer valid.”

## 17. Self-Check Questions

**1.** An arena allocates three segments. Two segments are “done being used”, one is still in use. Should you close the arena to free the first two?  
**Answer:** No, if the third segment still needs to be accessed. `close()` terminates the **entire arena scope**. If you want separate deallocation, split allocations into arenas with different lifetimes or change ownership.

**2.** A `MemorySegment` is still in a `List` after `arena.close()`. Why can it no longer be read?  
**Answer:** A live Java reference does not determine whether native backing memory is still valid. A segment has **temporal bounds** tied to the arena scope; closing makes the scope no longer alive.

**3.** Are two segments created with `arena.allocate(...)` necessarily at the same address or adjacent to each other?  
**Answer:** No. They share a **scope**, not necessarily the same backing allocation or contiguous placement in the address space.

**4.** Can a slice of a segment allocated by Arena A live longer than Arena A?  
**Answer:** No; a slice inherits the temporal bounds of the source segment.

**5.** Why is `Arena.ofConfined()` suitable for a request running on one thread?  
**Answer:** The owner thread is fixed, the API prevents other threads from accessing it, and a single close can reclaim all native buffers of the request.

**6.** Does `Arena.ofShared()` automatically guarantee that two threads writing the same `int` will not race?  
**Answer:** No. It allows multithreaded access with respect to **lifetime**, but the algorithm still needs proper synchronization and memory ordering.

**7.** Can you use `Arena.ofAuto()` and then call `close()` to quickly free all allocations?  
**Answer:** No. An automatic arena does not support explicit close; the GC decides when to reclaim after it becomes unreachable.

**8.** Why is using `Arena.global()` for millions of small requests dangerous?  
**Answer:** Native allocations from the global arena are not deallocated by the arena; memory can grow with the number of requests even after Java drops references.

**9.** A native function retains a pointer passed from a segment for asynchronous use. Can you close the arena right when the submit function returns?  
**Answer:** No, unless the native contract guarantees it has copied the data and does not retain the pointer. If C still uses the pointer after close, FFM does not automatically control raw C accesses; it can cause corruption/crash.

**10.** Do two arenas opened nested with `try` automatically create a “closing parent closes child” relationship?  
**Answer:** No. They are two independent arenas; each arena's close only affects allocations belonging to its corresponding scope. Nested `try` code only specifies lexical cleanup order.

**11.** `arena.scope().isAlive()` returns `true` in a shared arena. Can you safely use the segment on another thread without coordinating close?  
**Answer:** No. The status check can become stale immediately afterward; a protocol for lifetime and task completion is needed.

**12.** A helper API needs to create multiple buffers within a lifecycle decided by the caller. Why is accepting an `Arena` good design?  
**Answer:** The caller retains ownership, chooses confined/shared and when to close; the helper creates multiple segments all with a clear shared lifetime without freeing them prematurely.

## 18. Official Documentation for Deeper Study

- [Oracle Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): arena scope, confined/shared/automatic/global classification, `close`, owner thread, and invalidation of all segments.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): temporal/spatial bounds, slicing, `scope()`, `get`/`set`, and `IllegalStateException`.
- [Oracle Java SE 22 — SegmentAllocator](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): allocation by layout/value, benefits of accepting an allocator as a parameter.
- [Oracle Java SE 22 — FFM package overview](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html): context on memory access, off-heap, and foreign function calls.
- [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): official FFM API in JDK 22, design motivation, and memory segment lifecycle.
- [Oracle Java 22 Core Libraries Guide — Memory Segments and Arenas](https://docs.oracle.com/en/java/javase/22/core/java-core-libraries-developer-guide.pdf): examples of allocation, native memory access, and ownership.

**Conclusion:** An arena manages a **shared lifetime** because segments allocated from it reference **one scope**, so a single close shuts down access to the **entire group of memory regions**. This gives JNI/FFM code clear ownership and centralized cleanup; choosing the right **work boundary**, **thread model**, and **close timing** is what determines safety.
