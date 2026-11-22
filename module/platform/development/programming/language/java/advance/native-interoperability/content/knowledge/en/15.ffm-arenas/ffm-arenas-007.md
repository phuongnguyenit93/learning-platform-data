# Distinguishing a Retained MemorySegment Object from Expired Memory

## 1. The Core Problem: A Living Java Object Does Not Mean Native Memory Is Still Valid

In pure Java, developers often think: “If I still hold a strong reference to an object, that object has not been collected by the garbage collector (GC), so I can still use it.” This rule is **not sufficient** when the Java object is only a *view* into a **native resource with an independent lifecycle**, typically `java.lang.foreign.MemorySegment` in the Foreign Function & Memory API (FFM).

For example, a method holding a `MemorySegment` in a Java variable:

```java
MemorySegment segment;

try (Arena arena = Arena.ofConfined()) {
    segment = arena.allocate(8);
} // Arena.close() has run.

// segment is still a non-null Java reference,
// but the segment's backing native memory has expired!
```

After the `try` block, there are **two simultaneous facts**:

1. The `segment` variable still holds the **Java object** representing the view; it does not automatically become `null` and the object does not need to be collected by GC.
2. `arena.close()` has **invalidated the scope** and released the off-heap memory owned by the arena. Therefore, `segment.get(...)`/`set(...)` operations will not be permitted even though the Java variable still exists.

This distinction is the focus of this lesson:

> **An existing Java reference** is a matter of *object reachability on the Java heap*. **Accessible memory** is a matter of *lifetime/scope and access permissions of the native backing memory*.

**Version requirement:** the examples use `java.lang.foreign.Arena`, `MemorySegment`, and `ValueLayout` in the finalized standard API from **JDK 22** (JEP 454). Use **JDK 22+**; `--enable-preview` is not required for standard memory access operations. JDK 17 uses a different incubator API and will not compile these code snippets directly.

### Learning Objectives

You should be able to answer:

- Why `segment != null` or a `final MemorySegment` variable does **not** prove the memory is still alive?
- Why `segment.scope().isAlive()` can return `false` even though the Java object is still reachable?
- Why `byteSize()`, `address()`, or slice metadata may still be present without implying read/write permission?
- When creating a slice or `ByteBuffer` view, do those view objects extend the lifetime of the native allocation?
- How do `Arena.ofConfined` and `Arena.ofShared` differ from `Arena.ofAuto`/`Arena.global` regarding closing rights and GC?
- How to design an arena-owning API to avoid returning an expired segment, and how to **copy data** if it must be kept after closing?
- Which cases does FFM block with an exception, and which cases using raw native pointers can cause serious errors outside FFM's checks?

## 2. Three Different Entities: Wrapper, Scope, and Backing Memory

A segment should be understood through **three layers**, not a single pointer:

```text
Java heap                             Native / off-heap memory
---------------------------------     --------------------------------
MemorySegment object (view)
  ├─ byteSize = 16
  ├─ address = A --------------------> [16 bytes at native address A]
  └─ Scope -----------------+
                           |
Arena.ofConfined() ---------+
  └─ close() -> invalidates Scope
                 and releases backing native memory

After close:
  segment Java object may still be reachable
  Scope.isAlive() == false
  address metadata may still equal A
  native bytes at A NO LONGER belong to this allocation
  get()/set() on segment -> IllegalStateException
```

Breakdown:

**(A) The `MemorySegment` Java object** is a descriptor of a view: starting location, size, how backing memory is shared, and scope/usage conditions. The Java object can still be referenced by a variable, field, collection, or closure. Retaining a strong reference prevents the **Java object** from becoming unreachable, but it does not “reopen” a closed arena.

**(B) `MemorySegment.Scope`** sets **temporal bounds** for accesses managed by FFM. Each segment is associated with a scope, queried via `segment.scope()`. For a segment allocated by an arena, the segment's scope is the arena scope. When close succeeds, the scope is no longer alive.

**(C) Backing memory** is the actual bytes: an off-heap region, a mapped file, or an array on the Java heap. When the arena managing a native allocation is closed, the native backing memory may be reclaimed and must no longer be used. The `MemorySegment` Java object does not necessarily disappear when reclamation occurs.

**Terminology:** `MemorySegment` is not the allocation itself. It is a *view of the allocation*. One allocation can have multiple views (the root segment, a slice, a read-only view, a `ByteBuffer` view), all subject to the corresponding lifetime constraints.

## 3. Four Different Checks — Do Not Conflate Them

| Question | Check / Concept | Correct Interpretation |
| --- | --- | --- |
| Is there a Java reference? | `segment != null` | The variable points to a Java object; **says nothing about the lifetime of the backing allocation** |
| Is the attached scope of the native backing still alive? | `segment.scope().isAlive()` | Reports the **current** state of the scope; does not replace access-time checks |
| Are there enough bytes to read? | `segment.byteSize()`, offset, `ValueLayout.byteSize()` | Checks **spatial bounds**; sufficient size does not prove the scope is still alive |
| Does the thread have access permission? | `segment.isAccessibleBy(Thread.currentThread())` | Checks **thread confinement** restrictions; does not guarantee valid scope/offset |
| Is the address properly aligned? | `segment.maxByteAlignment()` and `ValueLayout.byteAlignment()` | Alignment condition; does not prove lifetime |
| Is the backing still readable via FFM? | `segment.get(layout, offset)` | Access is performed with the relevant checks: scope, thread, bounds, alignment, etc. |

Do not use reasoning like:

```java
if (segment != null && segment.byteSize() >= 8) {
    // WRONG if the arena has already closed.
    long value = segment.get(ValueLayout.JAVA_LONG, 0);
}
```

Nor should you treat:

```java
if (segment.scope().isAlive()) {
    // Not a "license" to use the raw native pointer indefinitely.
    nativeOperation(segment.address());
}
```

as a complete lifecycle protocol if another thread can close the arena **between the check and when the native operation uses the pointer**.

**Key point:** `isAlive()` is a point-in-time observation, not an arena “lock”. For managed FFM accesses, the API checks validity at access time and protects according to its contract. When handing off a **raw pointer outside FFM**, you must establish your own ownership, lifetime, and synchronization rules.

## 4. Closing an Arena: The Object May Remain, the Bytes Have Expired

### 4.1. The Arena Is Responsible for Lifetime

An arena coordinates the allocation and deallocation of native memory:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16, 8);
    segment.set(ValueLayout.JAVA_LONG, 0, 100L);
    System.out.println(segment.get(ValueLayout.JAVA_LONG, 0)); // 100
} // close() is called at the end of try-with-resources.
```

When `Arena.close()` **completes successfully**:

1. The arena scope transitions to the **not alive** state.
2. Memory segments attached to that scope can no longer be used for access.
3. Off-heap regions allocated by the arena are deallocated according to the arena's mechanism.
4. `MemorySegment` Java objects may **still exist**, but now represent an **invalidated** view.

Therefore, `MemorySegment` does not have a separate `close()` method that makes its region outlive the arena. **The arena is the owner in terms of deallocation** for the native allocations it allocates.

### 4.2. Post-Close State Does Not Turn the Object into Null

Valid example:

```java
MemorySegment remembered;
try (Arena arena = Arena.ofConfined()) {
    remembered = arena.allocate(8);
}
System.out.println(remembered != null);           // true
System.out.println(remembered.scope().isAlive()); // false
```

Accessing the memory:

```java
try {
    remembered.get(ValueLayout.JAVA_BYTE, 0);
} catch (IllegalStateException expected) {
    System.out.println("Already closed");
}
```

On the standard FFM API, this is a **blocked lifecycle management error** rather than reading freed bytes. `IllegalStateException` here has a different meaning from `NullPointerException`: the object still exists, **the scope has closed**.

### 4.3. Metadata Is Not “Permission to Use”

After close, view-describing properties such as `byteSize()` or the `address()` value may still be readable per the API. **The existence of metadata is only data about the view**, not a test of whether a C pointer is still valid.

For example, after the arena closes, it may still print:

```text
Segment retained: true
Scope alive: false
Size metadata: 16
Address metadata unchanged: true
```

This does **not** imply that the 16 bytes at the old address still belong to your allocation. The allocator may reuse that address for another purpose; dereferencing a raw pointer at the old address can cause use-after-free, data corruption, or a crash.

Do not use `address() != 0`, `byteSize() > 0`, or `maxByteAlignment() >= 8` as a condition to decide whether a native region is allocated or not yet freed.

## 5. Runnable Program: Retaining Segment, Slice, and ByteBuffer After Close

This example demonstrates the **independence between Java reachability and native lifetime** using three views of the **same native allocation**.

### 5.1. File SegmentLifetimeDemo.java

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public class SegmentLifetimeDemo {
    public static void main(String[] args) {
        MemorySegment retained;
        MemorySegment slice;
        ByteBuffer view;
        long oldAddress;

        try (Arena arena = Arena.ofConfined()) {
            retained = arena.allocate(16, 8);
            retained.set(ValueLayout.JAVA_INT, 0, 2026);

            slice = retained.asSlice(0, 4);
            view = retained.asByteBuffer().order(ByteOrder.nativeOrder());
            oldAddress = retained.address();

            System.out.println("In scope: "
                    + retained.scope().isAlive());
            System.out.println("Read in scope: "
                    + slice.get(ValueLayout.JAVA_INT, 0));
            System.out.println("Buffer in scope: "
                    + view.getInt(0));
        } // Closes the arena; none of the three views keep the allocation open.

        System.out.println("Segment retained: " + (retained != null));
        System.out.println("Scope alive: "
                + retained.scope().isAlive());
        System.out.println("Slice scope alive: "
                + slice.scope().isAlive());
        System.out.println("Size metadata: " + retained.byteSize());
        System.out.println("Address metadata unchanged: "
                + (retained.address() == oldAddress));

        try {
            retained.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("Segment read after close: blocked");
        }

        try {
            slice.get(ValueLayout.JAVA_INT, 0);
        } catch (IllegalStateException expected) {
            System.out.println("Slice read after close: blocked");
        }

        try {
            view.getInt(0);
        } catch (IllegalStateException expected) {
            System.out.println("Buffer read after close: blocked");
        }
    }
}
```

**Run with JDK 22+:**

```bash
javac SegmentLifetimeDemo.java
java SegmentLifetimeDemo
```

**Verified stdout on JDK 24:**

```text
In scope: true
Read in scope: 2026
Buffer in scope: 2026
Segment retained: true
Scope alive: false
Slice scope alive: false
Size metadata: 16
Address metadata unchanged: true
Segment read after close: blocked
Slice read after close: blocked
Buffer read after close: blocked
```

### 5.2. Result Analysis

- `retained != null` is `true`; this proves the Java object is still held by the variable after the arena closes.
- `retained.scope().isAlive()` is `false` because `Arena.close()` has invalidated the scope.
- `slice` was created before close via `asSlice(0, 4)`; it has its own view but **shares the same backing region and scope**. Therefore, the slice is also invalidated.
- `ByteBuffer view` was created via `asByteBuffer()` and retains a Java reference. It **does not become an independent copy**: when the arena closes, the byte buffer view associated with this segment also cannot be accessed normally.
- `byteSize()` is still 16; metadata existing after close does not grant access permission.
- Comparing `retained.address() == oldAddress` is still true in the example, but the old address value is no longer a usable pointer.
- The last three `get`/`getInt` accesses all encounter `IllegalStateException`; **this is not GC deleting the Java object**.

**Why use `ByteOrder.nativeOrder()`?** `ValueLayout.JAVA_INT` interprets bytes in native byte order; `ByteBuffer` defaults to **big-endian**. Setting the byte order on the view ensures `2026` is read consistently on common CPUs, avoiding endianness mismatch that would make the output confusing. Setting the byte order does **not** change the lifetime.

## 6. Slices, Views, and Collections Do Not Extend the Lifetime of an Explicitly Closed Arena

### 6.1. Does Storing Multiple Java References Help?

Suppose:

```java
List<MemorySegment> list = new ArrayList<>();
MemorySegment[] array = new MemorySegment[2];

try (Arena arena = Arena.ofConfined()) {
    MemorySegment root = arena.allocate(32, 8);
    list.add(root);
    list.add(root.asSlice(8, 8));
    array[0] = root;
    array[1] = root.asReadOnly();
}

// list and array still hold the Java objects,
// but do not return the closed arena to the alive state.
```

This is an **illustrative snippet**: it requires `import java.lang.foreign.*; import java.util.*;`. There is no rule saying “as long as a strong reference to a segment remains, the arena cannot be closed.” `Arena.ofConfined`/`ofShared` is an **explicit close** mechanism, not waiting for GC to lose references.

### 6.2. Operations That Create Views Sharing the Same Backing Memory

| Operation | Creates a byte copy? | When the original arena closes |
| --- | --- | --- |
| `segment.asSlice(offset, length)` | No, only creates a sub-view | Slice is invalidated along with the scope |
| `segment.asReadOnly()` | No; read-only view | Still invalidated |
| `segment.asByteBuffer()` | No; memory-sharing view | Buffer view cannot be accessed after the scope closes |
| `segment.asSlice(...).asByteBuffer()` | No | Nested views still share the same lifetime |
| Storing `segment` in a field/static/list | No | Java references may persist; native allocation is still closed |
| `segment.toArray(ValueLayout.JAVA_BYTE)` | **Yes, copies the data** | Separate copied Java array remains usable after close |
| `MemorySegment.copy(src, ..., dst, ...)` | **Yes, copies bytes into dst's backing** | Destination data lives according to **dst's scope**, independent of src |

**Warning:** with `MemorySegment.copy`, if `dst` is allocated in the **same arena** as `src`, closing the arena still invalidates both. “Copy” only solves lifetime when **the destination belongs to memory/scope that remains valid longer**, such as a Java byte array or an arena managed by the caller.

### 6.3. Extending a View Does Not Mean Extending the Backing Allocation

Methods like `asSlice` only change spatial bounds (offset/size), not temporal bounds. The correct model:

```text
Arena A: OPEN ------------------------ CLOSE -----------> CLOSED
             |                           |
root segment |===========================X
slice 1          |=======================X
slice 2                  |===============X
ByteBuffer view              |===========X

Symbol X: all accesses sharing the backing have ended.
Java objects of the views may still exist after X.
```

## 7. The Bug of Returning a Segment from a Closed Arena

### 7.1. Anti-pattern: Creating an Arena in a Helper and Returning the Segment Outside

```java
static MemorySegment brokenFactory() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment result = arena.allocate(8, 8);
        result.set(ValueLayout.JAVA_LONG, 0, 77);
        return result; // Java returns the object; the try's finally closes the arena.
    }
}
```

When the caller receives `result`, the native allocation **has already been released**. Java passing an object return value on the stack **does not keep the arena open** once `try-with-resources` has called `close()`.

The same thing happens if a service obtains a segment from a method and then closes the arena in `finally` before a callback finishes:

```java
static MemorySegment broken() {
    Arena arena = Arena.ofConfined();
    try {
        return arena.allocate(64);
    } finally {
        arena.close(); // Returned, but the segment has already expired.
    }
}
```

This is not a leak; it is a **dangling view**. A proper API must clearly transfer responsibility for the **lifetime owner**, or **copy the data** before the owner closes.

### 7.2. Correct Approach 1: The Caller Provides the Arena and Controls the Lifecycle

```java
static MemorySegment createIn(Arena owner) {
    MemorySegment segment = owner.allocate(8, 8);
    segment.set(ValueLayout.JAVA_LONG, 0, 77);
    return segment;
}

static void useResource() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = createIn(arena);
        System.out.println(s.get(ValueLayout.JAVA_LONG, 0));
    } // The caller decides to close here.
}
```

This is the **borrowed arena / caller-owned lifetime** pattern: the helper only allocates into the received arena and does not close the caller's arena itself. The caller ensures all operations, callbacks, or native downcalls requiring the backing memory finish before close.

If returning a segment to an object with a longer lifetime than the method, that object should hold the **arena/owner** and have a `close()` contract; do not close inside the factory right after returning the segment.

### 7.3. Correct Approach 2: Return an Independently Living Copy

If the caller only needs the **contents**, not the shared off-heap allocation, copy to the Java heap before closing:

```java
static byte[] safeCopy() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment s = arena.allocate(8, 8);
        s.set(ValueLayout.JAVA_BYTE, 0, (byte) 17);
        return s.toArray(ValueLayout.JAVA_BYTE);
    }
}
```

The resulting `byte[]` array is Java storage, not a view into a closed native allocation. Of course, the array holds the contents copied at the time `toArray` was called; it **does not automatically update** if the original native region changes later.

### 7.4. Correct Approach 3: An Object Owns Both the Arena and the Segment

Wrapper design:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

final class NativeBlock implements AutoCloseable {
    private final Arena arena = Arena.ofConfined();
    private final MemorySegment block = arena.allocate(32);

    MemorySegment view() {
        if (!block.scope().isAlive()) {
            throw new IllegalStateException("NativeBlock already closed");
        }
        return block;
    }

    @Override
    public void close() {
        arena.close();
    }
}
```

**This snippet illustrates architecture**, not a complete multithreaded protocol: with `Arena.ofConfined`, calls must be from the owner thread; a second `close` throws an exception per the Arena contract; `view()` returns a borrowed segment that cannot be used safely beyond the lifetime of `NativeBlock`. The caller retaining the `MemorySegment` after `NativeBlock.close()` **does not** by itself prevent the block from being invalidated.

If multiple threads need to be supported, `Arena.ofShared()` and an access/close synchronization contract are needed. If idempotent close is desired, separate state is needed, but concurrent users must **not** be ignored.

## 8. Standalone Program: Results of Broken Factory, Proper Owner, and Proper Copy

### 8.1. File ArenaOwnershipDemo.java

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaOwnershipDemo {
    private static MemorySegment unsafeEscape() {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment s = arena.allocate(8, 8);
            s.set(ValueLayout.JAVA_LONG, 0, 77);
            return s;
        }
    }

    private static MemorySegment createIn(Arena owner) {
        MemorySegment s = owner.allocate(8, 8);
        s.set(ValueLayout.JAVA_BYTE, 0, (byte) 17);
        return s;
    }

    public static void main(String[] args) {
        MemorySegment stale = unsafeEscape();
        System.out.println("Escaped scope alive: "
                + stale.scope().isAlive());

        try {
            stale.get(ValueLayout.JAVA_LONG, 0);
        } catch (IllegalStateException expected) {
            System.out.println("Escaped access: blocked");
        }

        byte[] copy;
        MemorySegment kept;

        try (Arena owner = Arena.ofConfined()) {
            kept = createIn(owner);
            copy = kept.toArray(ValueLayout.JAVA_BYTE);
            System.out.println("Inside owner: "
                    + kept.get(ValueLayout.JAVA_BYTE, 0));
        }

        System.out.println("Kept object: " + (kept != null));
        System.out.println("Kept scope alive: "
                + kept.scope().isAlive());
        System.out.println("Copied byte after close: " + copy[0]);
    }
}
```

**Compile and run:**

```bash
javac ArenaOwnershipDemo.java
java ArenaOwnershipDemo
```

**Verified stdout on JDK 24:**

```text
Escaped scope alive: false
Escaped access: blocked
Inside owner: 17
Kept object: true
Kept scope alive: false
Copied byte after close: 17
```

Explanation:

- `unsafeEscape` creates native memory in an arena that is closed **before the caller uses** the segment, so the caller receives an expired view.
- `createIn(Arena owner)` does not close the arena; the caller decides the boundary.
- Inside `try`, `kept` is usable. After `try`, the Java object `kept` is still non-null, but the backing memory has expired.
- `copy` is a separate Java array created before close, so reading `copy[0]` after the arena closes still works normally.

Lesson from the example: **for data to live long, you need an owner with a sufficiently long lifetime or an independent storage copy; retaining a Java reference to the view is not enough**.

## 9. Comparing Arenas: When Does a Java Reference Actually Affect GC Lifetime?

Another misconception is transferring the rules of an **automatic arena** to a **closeable arena**. They have different contracts.

| Arena type | How long does the off-heap region live? | Explicit `close()`? | If Java code still holds the segment |
| --- | --- | --- | --- |
| `Arena.ofConfined()` | Until the arena is successfully closed | Yes; the thread that created the arena closes it | **Can still be invalidated** if the owner closes |
| `Arena.ofShared()` | Until the arena is successfully closed | Yes; threads can close, subject to concurrent access rules | **Can still be invalidated** if the owner closes |
| `Arena.ofAuto()` | Until GC decides to reclaim, after the auto arena and all associated segments are no longer reachable | No; calling `close` is unsupported | Strong references keep the auto-backed resource reachable; **no release deadline is guaranteed** |
| `Arena.global()` | Unbounded lifetime per API; backing allocations are not deallocated during the arena's lifetime | No | Retaining or losing segment references **does not create a deallocation point** |
| Heap segment from `MemorySegment.ofArray(...)` | Backing Java array is managed by GC, not an `Arena.allocate` native allocation | Unrelated to closeable native arenas | Segment references keep the array reachable via backing; does not imply a native arena |

**Very important:** two seemingly contradictory statements are both true:

- With `Arena.ofConfined()/ofShared()`, **a retained Java segment** does not prevent the arena from being **explicitly closed**.
- With `Arena.ofAuto()`, **a reachable Java segment** is one of the conditions that prevents GC from **yet** reclaiming the auto arena's backing allocation.

Do not apply “as long as the segment exists, native memory is alive” to closeable arenas; nor say “GC can collect an auto arena's backing while the segment is still validly in use,” as that is wrong about the reachability contract.

### 9.1. Why Is `Arena.ofAuto` Unsuitable for Release Deadlines?

`Arena.ofAuto()` is useful when accepting automatic lifecycle management by GC. However, the amount of native bytes can be large while the Java wrapper is small; GC has no obligation to run immediately after you assign `segment = null` or call `System.gc()`.

Do not write tests like:

```java
MemorySegment s = Arena.ofAuto().allocate(1024 * 1024);
s = null;
System.gc();

// WRONG: asserting native memory has been freed right here.
```

There is no guarantee about when GC or native free occurs after `System.gc()`.

### 9.2. The Global Arena Has No Close Point

`Arena.global()` is suitable for memory regions that truly need an unbounded lifetime per the API. If too much is allocated into the global arena, the application may retain native memory until the process exits even if Java references to the segments are lost.

Therefore, by default when a resource has an end point, use `Arena.ofConfined()` or `ofShared()` with `try-with-resources`, rather than relying on GC or allocating into the global arena.

## 10. Standalone Program: Auto, Heap, and Confined Arena

### 10.1. File ArenaModesDemo.java

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaModesDemo {
    public static void main(String[] args) throws InterruptedException {
        Arena automaticArena = Arena.ofAuto();
        MemorySegment auto = automaticArena.allocate(8);

        System.out.println("Auto alive while retained: "
                + auto.scope().isAlive());

        try {
            automaticArena.close();
        } catch (UnsupportedOperationException expected) {
            System.out.println("Auto close: unsupported");
        }

        System.out.println("Auto alive after attempted close: "
                + auto.scope().isAlive());

        MemorySegment heap = MemorySegment.ofArray(new byte[4]);
        System.out.println("Heap native: " + heap.isNative());
        System.out.println("Heap alive: " + heap.scope().isAlive());

        try (Arena confined = Arena.ofConfined()) {
            MemorySegment s = confined.allocate(4);

            Thread other = new Thread(() -> {
                try {
                    s.get(ValueLayout.JAVA_BYTE, 0);
                } catch (WrongThreadException expected) {
                    System.out.println("Other thread access: blocked");
                }
            });

            other.start();
            other.join();

            System.out.println("Owner thread access: "
                    + s.get(ValueLayout.JAVA_BYTE, 0));
        }
    }
}
```

**Compile and run:**

```bash
javac ArenaModesDemo.java
java ArenaModesDemo
```

**Verified stdout on JDK 24:**

```text
Auto alive while retained: true
Auto close: unsupported
Auto alive after attempted close: true
Heap native: false
Heap alive: true
Other thread access: blocked
Owner thread access: 0
```

The snippet above does **not** try to force GC to prove auto-backed memory is freed; it only tests deterministic contracts: an auto arena does not allow explicit closing while objects exist, a heap segment is not native, and a confined arena does not allow other threads to access it.

**A nuance:** `scope.isAlive()` on `Arena.ofAuto` returns true while the segment is retained in the example; it does not provide an API to “close by GC right now”. Only when both the segment and the auto arena are no longer reachable does the runtime have the opportunity to reclaim at an unspecified time.

## 11. Closing Arenas and Races with Other Threads

Keeping a Java reference and keeping an arena open are two different things; **access synchronization** is a third aspect.

### 11.1. Confined Arena

`Arena.ofConfined()` is bound to the creating thread. Another thread attempting to access the segment may encounter `WrongThreadException` even while the scope is still alive.

```text
Thread A (owner)
   Arena.ofConfined()
       |
       +-- native segment still alive
       |
Thread B calls segment.get(...)
       |
       +-- WrongThreadException (wrong owner)
```

If you pass the segment to thread B, the Java reference still exists, but **access permission is not granted**. That is not an expired lifetime, but **wrong thread permission**.

### 11.2. Shared Arena

`Arena.ofShared()` allows access from multiple threads. However, that does **not** mean accesses or closing the arena are automatically synchronized according to application logic.

Suppose thread A is using a segment, and thread B tries to close the shared arena:

- FFM performs temporal-safety checks; `Arena.close()` may throw `IllegalStateException` when an FFM operation is concurrently using a segment in the arena.
- The caller needs a clear lifecycle management policy: wait for in-flight operations to complete, disallow starting new operations after a “closing” state, and then close.
- If native code outside FFM holds a raw pointer longer than the FFM call, the runtime mechanism **does not necessarily know** that the raw pointer is still in use. Coordination with the native side is mandatory before releasing the allocation.

### 11.3. Why Does Check-Then-Use Have a Race?

```java
if (segment.scope().isAlive()) {
    // Another thread may close the shared arena after the check.
    int value = segment.get(ValueLayout.JAVA_INT, 0);
}
```

This is not an operation that “reserves” memory. `isAlive()` may be true at the time of the check, but change before `get`. With FFM, the result may be an exception instead of a successful access. In your API, do not turn a single `isAlive()` call into an unconditional lifetime promise for subsequent work.

Architectural solutions: use explicit ownership, a state machine (OPEN → CLOSING → CLOSED), a lock/lease/borrow to block concurrent close while operations are running, or a centralized owner thread coordinating close.

## 12. Still Holding a Raw Native Address: The Danger Zone FFM Cannot Protect Automatically

FFM can only control accesses **performed through APIs with bounds/lifetime checks**. If you extract the address and pass it outside:

```java
long rawAddress = segment.address();
```

`rawAddress` is just an **integer**. It does not keep the segment alive, does not keep the arena open, and does not carry `byteSize` or scope information. After `arena.close()`, that number may still equal the old address, but the native memory has already been deallocated.

Passing `rawAddress` to C/C++ and dereferencing it after the arena closes can cause use-after-free, a crash, reading wrong data, or memory corruption. A Java exception for a closed scope **does not automatically appear** inside a C function receiving a raw address.

### 12.1. Restricted Reinterpret Does Not Resurrect Memory

JDK 22+ has `MemorySegment.ofAddress(long)`, which creates a zero-length view attached to an address (without allocating memory), and `reinterpret(...)` APIs to redeclare size/scope in cases requiring native interoperability.

**Do not use `reinterpret` to “reopen” an expired segment** or make a fake scope appear alive. Restricted methods can violate memory safety when misused: for example, declaring a view with a different scope that outlives the backing allocation and then dereferencing it after the real owner frees it. The Javadoc warns this can lead to a JVM crash or memory corruption.

Safe practices:

1. Preserve the owner of the native allocation and the actual close/`free` point.
2. Only create views with size and scope matching the actual backing memory.
3. Do not create a “global view” to a pointer allocated in an arena about to close.
4. For third-party APIs that return a pointer, understand the contract of who owns the pointer and who is allowed to free it; do not put it into the wrong arena to auto-free.
5. After close, do not try to work around errors by reading the raw address or casting to `Unsafe`/JNI.

### 12.2. A Heap Segment Cannot Be Treated as a Native Pointer

`MemorySegment.ofArray(new byte[16])` has a Java heap backing; its address is virtualized, not an actual native address to pass to C. For a heap-backed segment, `address()` of the root segment may be 0, but that does **not** mean the Java array has been freed or the C pointer is `NULL`.

If a native function needs to access those bytes, use a supported API path and ensure the backing storage is handled validly; do not cast `heap.address()` to a C pointer. This is an independent issue from whether a native arena has closed or not.

## 13. Common Mistakes and How to Fix Them

| Bug pattern | What is wrong? | Correct approach |
| --- | --- | --- |
| `segment != null` so `get` must be valid | A Java reference does not guarantee the native backing is alive | Check the owner/scope contract; perform valid accesses within the lifetime |
| Storing `MemorySegment` in a `static` field so it is “never freed” | Cannot prevent the owner from closing `Arena.ofConfined`/`ofShared` | Store the owner as well if needed; manage when to close |
| Returning a segment from `try (Arena arena = ...)` | The scope has already closed before the caller uses it | Caller owns the arena or copy the data |
| Returning `asSlice` and closing the parent arena | The slice shares the same backing/scope | Keep the parent arena open until all views are done |
| Thinking `asByteBuffer` detaches from the arena | The buffer view shares the native backing memory | Copy to `byte[]` or an independent storage buffer |
| `byteSize() > 0` means memory is still there | Metadata is unrelated to runtime lifetime | `scope().isAlive()` and access-time checks |
| `address()` after close is still non-zero so the C pointer is valid | An address number does not carry ownership | Do not dereference raw pointers after free |
| Checking `isAlive()` once and using indefinitely | Another thread may close after the check | Synchronize lifecycle and access; handle exceptions |
| Thinking `Arena.ofAuto()` closes when the method ends | Managed by GC, no deadline | Use a closeable arena + `try-with-resources` when a deadline is needed |
| Thinking all arenas are governed by GC the same way | Confined/shared close explicitly; auto is managed by GC | Distinguish arena ownership |
| Closing `Arena.ofConfined` from another thread | Violates confinement | Close on the owner thread or design with a shared arena |
| Using `reinterpret` to bypass invalidation | The new view's scope may outlive the actual backing | Only reinterpret when the memory's lifetime/size is known for certain |
| Copying to another segment in the same arena | Both die with the same scope | Copy to heap or to a destination arena that lives long enough |
| Relying on `System.gc()` to verify free | GC does not guarantee reclamation timing | Test deterministically with close |
| Ignoring in-flight native uses when closing | Raw C pointers lack FFM temporal checks | Wait for callbacks/native tasks to finish before closing |

## 14. Proper Testing: Separating Reachability, Lifetime, and Access Permission

A test suite should measure **things guaranteed by the contract** rather than depending on unstable GC conditions.

### Testing with Closeable Arenas

- Create a confined arena, allocate, and read/write while the scope is alive.
- Store the `MemorySegment` in a variable that remains alive outside `try`.
- Close the arena using `try-with-resources`.
- Verify `segment != null` is still true.
- Verify `segment.scope().isAlive() == false`.
- Verify `get` or `set` on the segment throws `IllegalStateException`.
- Create `asSlice` and `asByteBuffer` **before** closing; verify the views cannot be read after close.
- Do not assert a specific raw native address or `address()` value because it depends on the environment.

### Testing Ownership/Copy

- Test a factory that closes the arena before returning: the caller receives a stale view, access is blocked.
- Test a factory that receives the arena from the caller: access succeeds **within** the caller's scope.
- Test snapshotting via `toArray`: the Java array copy still has the data after close.
- Test not closing the arena inside a helper that the caller itself still owns, avoiding double close.

### Testing Multi-Thread

- `Arena.ofConfined`: another worker thread attempting access will encounter `WrongThreadException`.
- `Arena.ofShared`: threads can access, but tests need to coordinate with close and shared data. Do not rely on random race tests to prove there is no use-after-free in C.
- Simulate proper close when all in-flight tasks have completed and handle the case of access from a thread arriving after close.

### Do Not Write Tests Requiring GC to Free Immediately

```java
MemorySegment s = Arena.ofAuto().allocate(1024);
s = null;
System.gc();

// There is no guarantee that the native allocation
// has been reclaimed immediately after calling System.gc().
```

A test forcing GC is a **non-deterministic** experiment regarding reclamation timing, not a verification of an absolute lifetime contract.

## 15. Self-Check Exercises

**Question 1.** A `final MemorySegment s` variable is still reachable. If the `Arena.ofConfined()` containing it has closed, is `s.get(ValueLayout.JAVA_BYTE, 0)` valid?

**Answer:** No. `final` only restricts reassigning the Java variable; it does not change the scope or the right to close the arena. After close, access is invalid and is rejected.

**Question 2.** A segment has `byteSize() = 1024` and `address() = A`. Can those two values still be observed after close? Does that mean the 1024 bytes at A still belong to you?

**Answer:** Metadata can still be observed, but the backing memory was deallocated when close succeeded. The old address is not ownership; do not access bytes via a raw pointer.

**Question 3.** `slice = root.asSlice(8, 8)` is held in a `List`. Does closing `root`'s arena invalidate `slice`?

**Answer:** Yes. The slice shares backing memory and scope with root. The collection only holds the Java view object; it does not keep the scope alive.

**Question 4.** What if `toArray(ValueLayout.JAVA_BYTE)` is called before close?

**Answer:** It returns a Java array copying the bytes; the data in that array remains usable after the native arena closes, because its backing storage is independent.

**Question 5.** Do the two calls `segment.scope().isAlive()` and `segment.get(...)` form an atomic “keep-alive” operation?

**Answer:** No. `isAlive()` is a snapshot; another thread can close a shared arena between the two calls. FFM access checks validity, but the API caller needs lifecycle synchronization if a guarantee for the whole workflow is required.

**Question 6.** When does a strong reference to a segment play a role in protecting the backing native memory's lifetime from GC?

**Answer:** With an auto arena, GC only reclaims the backing after the auto arena and all associated segments are no longer reachable; retaining a segment prevents the reclamation condition from being met. This is **different** from closeable arenas, which can be explicitly closed while the segment is still reachable.

**Question 7.** A `MemorySegment.ofArray(new byte[8])` has `address() == 0`. Does that mean the backing memory has expired?

**Answer:** No. This is a heap segment with a virtualized address, not a raw native pointer; do not infer lifetime from the address value.

**Question 8.** A Java caller receives a `MemorySegment` from a helper, but the helper already called `close()` on the arena in `finally`. What is the most reasonable fix?

**Answer:** Let the caller manage the arena until finished using it, or return an independent data copy. Do not return a borrowed view out of an already-closed owner.

**Question 9.** If FFM blocks `get` after close, is it safe to use `long oldAddress = segment.address()` with JNI/C?

**Answer:** No. A raw pointer carries no scope/bounds and may point to freed memory; FFM does not automatically check dereferences in C.

**Question 10.** An `Arena.ofShared` is still alive at the moment you check. Can you close it immediately while a native worker is using the raw pointer?

**Answer:** No. You must coordinate so the native worker finishes and returns ownership before closing; checking `isAlive()` alone does not prevent races or use-after-free outside FFM.

## 16. Practical Summary

- **Reachable Java object** ≠ **living native backing memory**.
- A successful `Arena.close()` makes the scope not alive and invalidates segments with that scope, even if Java still retains all views.
- `segment != null`, `byteSize()`, and `address()` are only indicators **about the view**, not replacements for lifetime control.
- Slices, read-only views, and `ByteBuffer` views **share backing/scope** and do not extend the lifetime of an explicitly closed arena.
- `toArray` or copying to storage with an independent lifetime preserves the **data**, not the original native allocation.
- `Arena.ofConfined/ofShared` have **explicit close**; `Arena.ofAuto` is managed by GC, and `Arena.global` has no release deadline.
- `scope().isAlive()` is an instantaneous state; for a workflow to use memory safely across multiple steps, **owner/borrow/lifecycle synchronization** is required, especially when multiple threads or native code may hold pointers.
- When needing to share a segment across layers or return it from a helper, pass the arena from the caller or return a wrapper holding the arena; do not close the owner before the consumer finishes using it.

## Official References

- [JDK 24 API — MemorySegment: access, scope, lifetime, views](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- [JDK 24 API — Arena: lifetime, close, automatic, and confined/shared](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html)
- [JDK 24 API — MemorySegment.Scope](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html)
- [JDK 24 API — ValueLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html)
- [OpenJDK JEP 454 — Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- [Dev.java — Access On/Off-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/)

**Conclusion:** retaining a Java reference to a `MemorySegment` **cannot resurrect native memory that has already been closed by its arena**. Do not ask only “is the object still there?”; instead ask “**is the arena/scope still valid, on the right thread, the right size, and does the backing memory still belong to the owner?**”. That is the boundary between an existing Java view and memory that is actually still usable.
