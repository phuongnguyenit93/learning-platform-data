# Scope, Lifetime, and Thread-Access Safety Checked by FFM

The Java Foreign Function & Memory API (FFM) provides a way to model memory regions outside the Java heap, access them with checks, and call native functions via `java.lang.foreign`. The key difference compared to using raw C addresses is that a `MemorySegment` is not just a pointer. It carries **size bounds**, **scope/lifetime**, and, where appropriate, **thread constraints**. As a result, certain memory errors can be detected with a Java exception before an invalid access occurs.

For example, an 8-byte memory region allocated by `Arena.ofConfined()` for thread A:

- Thread A reads an `int` at offset `0` while the arena is still open → valid.
- Thread A reads 4 bytes at offset `8` → `IndexOutOfBoundsException` because it exceeds the 8-byte bound.
- Thread B tries to read this region while the arena is still open → `WrongThreadException` because it is the wrong owner thread.
- The arena is closed properly; thread A tries to read again → `IllegalStateException` because the scope is no longer alive.

**What needs to be understood correctly:** These checks apply to **accesses performed through the FFM API and the constraints that the segment actually describes**. FFM cannot automatically infer the lifetime of a native address of unknown origin, cannot fix all data races between threads, and cannot guarantee the safety of all C/C++ code called via FFM. Misallocating a memory region or assigning a fake size/lifetime using a restricted method still carries the risk of serious memory errors.

## 1. Version Milestone: Example Code in This Article Uses Java 22+

FFM has evolved across multiple versions and API names have changed. To avoid confusion between older examples and the current API:

| JDK | API Status | Points to Note |
| --- | --- | --- |
| Java 17 | Foreign memory/function API in the **incubator** era in module `jdk.incubator.foreign` | Does not use the same `java.lang.foreign.Arena`/`MemorySegment` code below |
| Java 19 | FFM API **preview** under JEP 424 | Preview must be enabled; API names/behavior still change |
| Java 20 | Subsequent preview, JEP 434 | Some factories and arena usage differ from the final version |
| Java 21 | Subsequent preview, JEP 442 | Has `java.lang.foreign`, but preview still differs from Java 22 |
| **Java 22 and above** | FFM **finalized under JEP 454** | Uses `java.lang.foreign.Arena`, `MemorySegment`, `ValueLayout` and the examples in this article |

The runnable snippets here require **JDK 22+**, and do not claim to compile with JDK 17. They only perform ordinary native memory allocation/access, **without calling restricted foreign functions**, so `--enable-native-access` is not needed to run the demonstration program. When an application uses restricted APIs such as opening a native library to perform a downcall or `MemorySegment.reinterpret`, the native access policy of the running JDK must be checked, such as `--enable-native-access=ALL-UNNAMED` for programs on the classpath when appropriate.

**Do not just change the version number:** a JDK 20 snippet using `Arena.openConfined()` or `allocateUtf8String` may no longer match the finalized API. In JDK 22+, the common way to create an arena is `Arena.ofConfined()`/`Arena.ofShared()`, and string allocation methods in the new API have appropriate names such as `allocateFrom(String)`. All security/concurrency guidelines must be tied to the exact API version.

## 2. Three Layers of Safety: Spatial, Temporal, and Thread

An FFM access is valid if it satisfies independent conditions:

```text
MemorySegment (address + size + scope + access properties)
             │
             ├── [1] Spatial: offset + sizeof(layout)
             │         must lie completely within byteSize()
             │
             ├── [2] Temporal: scope must still be alive
             │         for the duration of the operation
             │
             ├── [3] Thread access: current thread
             │         must be compatible with confinement
             │
             └── [4] Other access rules:
                       alignment matches ValueLayout,
                       no writing to a read-only segment,
                       compatible layout/operation
             │
             ▼
        Valid memory read/write via FFM
```

| Check | How does FFM know? | Common Error |
| --- | --- | --- |
| **Spatial safety** | `byteSize()`, offset, layout size | `IndexOutOfBoundsException` |
| **Temporal safety** | `scope()` and arena alive/closed state | `IllegalStateException` on access after close |
| **Thread confinement** | Owner thread/scope properties | `WrongThreadException` |
| **Alignment** | `ValueLayout.byteAlignment()` and address/offset | `IllegalArgumentException` |
| **Read-only** | `segment.isReadOnly()` | `IllegalArgumentException` on write |
| **Is the foreign pointer actually valid?** | Cannot verify all external native addresses, allocations/lifetimes | Can lead to crash/corruption if declared incorrectly or calling buggy native code |

Do not rely on exception names as a normal control-flow mechanism. The design should **prevent invalid accesses right from ownership/lifecycle**, while exceptions help detect and diagnose errors. If an operation violates multiple conditions simultaneously, do not build logic based on a check order/exception priority not guaranteed by the API.

## 3. `MemorySegment` Is Not Just an Address

`MemorySegment` is an interface modeling a **contiguous memory region**. A native segment can be created by an arena:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(8, 4);
    segment.set(ValueLayout.JAVA_INT, 0, 123);
    System.out.println(segment.get(ValueLayout.JAVA_INT, 0));
}
```

This snippet illustrates a code block placed inside an appropriate method; if used as Java source, an enclosing class/method is needed. `allocate(8, 4)` allocates **8 bytes** with **4-byte alignment**; `ValueLayout.JAVA_INT` reads/writes a 4-byte Java `int`. The output under successful conditions is `123`.

Concepts:

- `segment.address()`: the address describing the memory region. For a native segment, it is a native address; for a heap segment, it has a different meaning. Do not use raw address numbers as a substitute for a segment with scope and byte bounds.
- `segment.byteSize()`: the size of the region **in bytes**, not the number of `int`/`long` elements.
- `segment.scope()`: the `MemorySegment.Scope` object modeling the **lifetime** of the region.
- `segment.scope().isAlive()`: indicates whether the scope is still valid at the time of the query.
- `segment.isAccessibleBy(Thread)`: indicates whether the segment can be accessed by a given thread.
- `segment.isReadOnly()`: distinguishes a writable region from a read-only view.
- `segment.asSlice(offset, size)`: creates a view into a portion of the original region, **does not allocate additional backing memory**, and **does not extend lifetime**.

Do not confuse `byteSize()` with unconditional accessibility. A `MemorySegment` Java object can still exist on the heap after the backing memory has been freed. Holding onto the `segment` variable only means holding onto the **metadata/handle**, not reviving a closed scope.

### Heap segments and native segments are not the same

`MemorySegment.ofArray(new int[]{10, 20})` creates a **heap segment** using a Java array backing store. By specification, heap segments have an automatic scope tied to the Java object lifecycle and can be accessed from any thread; it is neither necessary nor possible to arbitrarily close a separate confined arena for that array.

Conversely, `arena.allocate(...)` creates a native segment outside the Java heap, and the arena chooses **when** the backing memory is freed as well as **which thread** can access it. Both are subject to FFM bounds/alignment checks, but the close policy of native memory should not be applied to Java arrays.

## 4. `Arena` Defines Lifecycle and Confinement

`Arena` implements `AutoCloseable` and `SegmentAllocator`. Segments allocated from the same arena are tied to the arena scope; when a closeable arena is **successfully** closed, the scope is no longer alive and the native regions backing the arena's segments are freed.

| Arena Type (JDK 22+) | Lifetime | Explicitly Closeable? | Can Multiple Threads Access Segment? | Suitable For |
| --- | --- | --- | --- | --- |
| `Arena.ofConfined()` | Bounded, managed by caller | **Yes**, by owner thread | **No**; owner only | Short-lived native buffers within one method/thread |
| `Arena.ofShared()` | Bounded, managed by caller | **Yes**, from any thread per contract | **Yes** | Multi-threaded workflows with synchronized ownership |
| `Arena.ofAuto()` | GC-managed, reclamation time indeterminate | **No**; `close` throws `UnsupportedOperationException` | **Yes** | Automatically managed regions when deterministic close is not needed |
| `Arena.global()` | Unbounded for the VM runtime | **No**; `close` throws `UnsupportedOperationException` | **Yes** | Long-lived regions, with awareness of memory cost |

**There is no single "best" arena type for all situations.** You should start with `ofConfined()` for data that lives only within one thread and use `try-with-resources` for deterministic cleanup. Use `ofShared()` when multiple threads are truly needed; add synchronization/lifecycle policy. Use `ofAuto()` when a GC-controlled lifetime is appropriate, without relying on a specific release time. Avoid overusing `Arena.global()` for arbitrary data or allocations in loops without a reclamation plan: native memory can grow without being freed during the process lifetime.

### Why is `try-with-resources` a good default?

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment input = arena.allocate(64);
    MemorySegment output = arena.allocate(64);
    // Process quickly on the owner thread, without letting the segment escape the scope.
} // arena.close() is automatically called when leaving the block.
```

This is an illustrative snippet inside a method. When the block ends normally or with a Java exception, `try-with-resources` executes `close()`. An arena owning multiple segments is still cleaned up centrally. There is no need to call `free` for each segment or store raw addresses.

Note: `Arena.close()` is not idempotent. If already closed and called again, the JDK specifies it may throw `IllegalStateException`. Do not design two components to independently call `close` on the same arena without ownership rules.

## 5. Temporal Safety: Access Is Only Allowed While Scope Is Alive

The most common example:

```java
MemorySegment escaped;
try (Arena arena = Arena.ofConfined()) {
    escaped = arena.allocate(4, 4);
    escaped.set(ValueLayout.JAVA_INT, 0, 7);
}
int x = escaped.get(ValueLayout.JAVA_INT, 0);
// Wrong: access after close -> IllegalStateException.
```

This is an illustrative snippet, requiring appropriate imports. The `escaped` variable still points to a `MemorySegment`, but the arena has been closed. FFM detects the **use-after-close** error on the Java `get` operation and disallows reading backing memory through that API.

Forms of "re-wrapping" that do not extend lifetime:

- `MemorySegment view = segment.asSlice(0, 4)`: the view inherits the scope; closing the original segment's arena makes the slice inaccessible.
- `MemorySegment readonly = segment.asReadOnly()`: the readonly view does not own a new native allocation, nor does it extend lifetime.
- `ByteBuffer buffer = segment.asByteBuffer()`: the buffer has a lifecycle tied to the segment; after the scope closes, accessing the buffer is also checked per contract.
- Storing a segment in a `static`, field, collection, lambda, or closure **does not** make the memory region global.
- Keeping the address `long address = segment.address()` even less so extends the lifecycle of the backing memory.

### Distinguishing `scope().isAlive()` from safety until the end of an operation

`scope().isAlive()` is useful for diagnostics. However, the following snippet is **not sufficient** as a synchronization barrier when multiple threads operate on a shared arena:

```java
// Code illustrating a TOCTOU bug, not a synchronization solution.
if (segment.scope().isAlive()) {
    // Another thread may try to close the arena at this moment.
    consume(segment);
}
```

This is a *time-of-check to time-of-use* issue: checking alive at time T1 is not a contract guaranteeing that the scope is still open at T2. FFM has mechanisms to prevent use-after-free in valid FFM operations and arena closing rules, but application logic still needs to determine who has the right to close, when workers have finished, and when there are no outstanding operations/callbacks.

For Java APIs based on native data, it is safest **not to return a segment whose scope is about to close** to the outside. If a longer-lived result needs to be returned, **copy the values** to the Java heap or allocate it from an arena with an appropriate owner/lifetime, explicitly managed by the caller.

## 6. Thread Confinement: `ofConfined()` Truly Restricts Threads

A confined arena has an **owner thread**, usually the thread that created the arena. Native segments allocated from it can only be accessed from the owner thread. Passing a `MemorySegment` reference to thread B via `Thread`, `ExecutorService`, `CompletableFuture`, or a virtual thread **does not transfer ownership**.

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(4, 4);
    segment.set(ValueLayout.JAVA_INT, 0, 41);

    Thread worker = new Thread(() -> {
        // Accessing a native segment from another thread: WrongThreadException.
        segment.get(ValueLayout.JAVA_INT, 0);
    });
    worker.start();
    worker.join();
}
```

The illustrative snippet above lacks exception-handling code in the new thread; the full practical section below uses `catch`, so there is no unexpected stack trace. Notable characteristics:

- `segment.isAccessibleBy(Thread.currentThread())` on the owner thread returns `true`.
- The same check in another thread returns `false` for a segment from a confined arena.
- `get`/`set` on a segment from another thread throws `java.lang.WrongThreadException`.
- Calling `arena.close()` on a **thread other than the owner** also throws `WrongThreadException`; this is a lifetime ownership check.
- `WrongThreadException` belongs to **`java.lang`**, not `java.lang.foreign`. Do not import from the wrong package.

Placing a `synchronized` block around a confined segment **does not** change the owner thread. Using `volatile` also does not make it multi-thread accessible. This is an **FFM access rule**, not just a race condition that you can solve with a lock.

### Choosing how to pass data to a worker

There are two common ways:

1. **Copy to Java data:** the owner thread reads/copies data while the confined arena is still alive, handing `byte[]`, `int[]`, an immutable record, or `String` to the worker. Those Java objects have their own lifecycle and synchronization rules, independent of the closed confined scope.
2. **Use a controlled shared arena:** threads share a native segment from `Arena.ofShared()`, and the coordinator only closes the arena after all outstanding tasks have finished (e.g., `Future.get`/`join`).

Do not create a confined arena on thread A and expect worker thread B to "inherit" it after A finishes. If the worker creates its own confined arena **inside the worker itself**, it can use the native segment on that thread and close it itself before completing.

## 7. Shared Arena: Multi-Thread Accessibility Does Not Mean Thread-Safe Data

`Arena.ofShared()` allows its segments to be accessed from multiple threads, and the arena can be closed from any thread per the API contract. It **does not automatically synchronize every read/write of data** residing in native memory.

```java
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(8, 4);

    segment.set(ValueLayout.JAVA_INT, 0, 100);

    Thread worker = new Thread(() -> {
        int v = segment.get(ValueLayout.JAVA_INT, 0);
        segment.set(ValueLayout.JAVA_INT, 4, v + 7);
    });

    worker.start();
    worker.join(); // Wait for the worker to finish before closing the arena.

    System.out.println(segment.get(ValueLayout.JAVA_INT, 4)); // 107
}
```

In this example, the main thread **writes before the worker starts**, the worker reads/writes, and the main thread **waits for `join`** before reading the result and closing the arena. That ordering avoids concurrent access to the region being processed. One cannot omit `join` and conclude that `ofShared` is sufficient to guarantee consistency.

If two threads simultaneously update a counter in a shared segment using `get` → increment → `set`, this can be a **read-modify-write race**, similar to unsynchronized access to shared Java fields. Use appropriate synchronization mechanisms, memory ordering, and `VarHandle` with atomic operations when supported (and with proper alignment/ABI). FFM checks **access rights and memory regions**, and does not automatically make every operation atomic.

### What if one thread closes a shared arena while another thread is working?

The specification provides temporal safety: after a successful close, segments are no longer accessible. `Arena.close()` may throw `IllegalStateException` if an operation on a segment is occurring concurrently, such as a downcall; this is not an API to "force-close" all activities. Close should not be used as a task cancellation primitive.

Good policy:

```text
Application owner
  |
  +-- Create Arena.ofShared()
  +-- Distribute segment to workers with clear boundaries
  +-- Stop dispatching new tasks
  +-- Wait for workers/callbacks to complete
  +-- Close shared arena once
  +-- Disallow new tasks from using the old segment
```

Only one component decides the final lifecycle. If using an async API, it is necessary to understand that callbacks may run after the Java method returns; closing the arena immediately in the `finally` block of the function that initiates the async work may be **too early**.

## 8. Spatial Safety, Alignment, and Read-Only Are Also Part of the Checks

### Bounds: offsets are measured in **bytes**

An `arena.allocate(8, 4)` region contains 8 bytes, enough for 2 `int` values. With the 4-byte layout `ValueLayout.JAVA_INT`:

| Operation | Offset | Region Touched | Result |
| --- | ---: | --- | --- |
| `get(JAVA_INT, 0)` | 0 | Bytes 0–3 | Valid |
| `get(JAVA_INT, 4)` | 4 | Bytes 4–7 | Valid |
| `get(JAVA_INT, 8)` | 8 | Bytes 8–11 | **Out of bounds** |
| `get(JAVA_INT, 1)` | 1 | Bytes 1–4 | Within 8 bytes, but **not 4-byte aligned** |

Therefore, checking only `offset < byteSize()` is not enough; there must be room for the **entire `layout.byteSize()`**, and proper alignment. `MemorySegment.get`/`set` perform the necessary checks per the API. For offset 8 in the table, `IndexOutOfBoundsException`; for offset 1 when the base region is 4-byte aligned, `IllegalArgumentException` due to alignment.

`getAtIndex(ValueLayout.JAVA_INT, index)` calculates the offset by element index rather than byte offset; avoid confusing index 1 with a 1-byte offset. `ValueLayout.JAVA_INT` carries the default byte order of the layout (native order), but the encoding/ABI of a C struct still needs to be checked separately.

### A slice has its own bounds, but not its own lifetime

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(16, 4);
    MemorySegment secondInt = block.asSlice(4, 4);

    secondInt.set(ValueLayout.JAVA_INT, 0, 99);
    // secondInt.get(JAVA_INT, 4) is wrong: the slice is only 4 bytes long.
}
```

Every access through `secondInt` must lie within the 4 bytes of the **slice**, not the 16 bytes of `block`. When the arena closes, both `block` and `secondInt` lose access rights.

### Read-only view

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment block = arena.allocate(4, 4);
    block.set(ValueLayout.JAVA_INT, 0, 5);

    MemorySegment readOnly = block.asReadOnly();
    int value = readOnly.get(ValueLayout.JAVA_INT, 0); // valid.
    // readOnly.set(ValueLayout.JAVA_INT, 0, 6): IllegalArgumentException.
}
```

`asReadOnly()` only creates a **view**; it does not make the backing bytes immutable if another writable alias still exists. And it does not make the segment readable from all threads or live forever after the arena closes.

## 9. Standalone Practice: Distinguishing Each FFM Error (Java 22+)

The following program uses only FFM memory access, without calling native functions or `reinterpret`. It tests:

- `Arena.ofConfined()`: valid read on the owner thread and failure on another thread.
- Bounds/alignment/read-only: three different error types.
- `scope().isAlive()`: `true` inside the block, `false` after `close`.
- Slice still exists as a Java object after close but cannot be `get`.
- `Arena.ofShared()`: worker can read/write before the arena closes.
- Heap segment: `MemorySegment.ofArray` accesses a Java array.

**File `FfmScopeSafetyDemo.java`**

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class FfmScopeSafetyDemo {
    public static void main(String[] args) throws InterruptedException {
        MemorySegment escaped = null;

        try (Arena confined = Arena.ofConfined()) {
            MemorySegment segment = confined.allocate(8, 4);
            segment.set(ValueLayout.JAVA_INT, 0, 42);
            segment.set(ValueLayout.JAVA_INT, 4, 99);

            escaped = segment.asSlice(4, 4);

            System.out.println("confined=" +
                    segment.get(ValueLayout.JAVA_INT, 0));
            System.out.println("aliveInside=" +
                    segment.scope().isAlive());

            Thread worker = new Thread(() -> {
                System.out.println("otherAccessible=" +
                        segment.isAccessibleBy(Thread.currentThread()));
                try {
                    segment.get(ValueLayout.JAVA_INT, 0);
                    System.out.println("unexpectedThreadSuccess");
                } catch (WrongThreadException e) {
                    System.out.println(
                            "otherThread=WrongThreadException");
                }
            });

            worker.start();
            worker.join();

            try {
                segment.get(ValueLayout.JAVA_INT, 8);
                System.out.println("unexpectedBoundsSuccess");
            } catch (IndexOutOfBoundsException e) {
                System.out.println(
                        "outOfBounds=IndexOutOfBoundsException");
            }

            try {
                segment.get(ValueLayout.JAVA_INT, 1);
                System.out.println("unexpectedAlignmentSuccess");
            } catch (IllegalArgumentException e) {
                System.out.println("misaligned=IllegalArgumentException");
            }

            try {
                segment.asReadOnly().set(ValueLayout.JAVA_INT, 0, 1);
                System.out.println("unexpectedReadOnlySuccess");
            } catch (IllegalArgumentException e) {
                System.out.println("readOnly=IllegalArgumentException");
            }
        }

        System.out.println("aliveAfter=" +
                escaped.scope().isAlive());

        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
            System.out.println("unexpectedAfterCloseSuccess");
        } catch (IllegalStateException e) {
            System.out.println("afterClose=IllegalStateException");
        }

        try (Arena shared = Arena.ofShared()) {
            MemorySegment segment = shared.allocate(8, 4);
            segment.set(ValueLayout.JAVA_INT, 0, 100);

            Thread worker = new Thread(() -> {
                int value = segment.get(ValueLayout.JAVA_INT, 0);
                segment.set(ValueLayout.JAVA_INT, 4, value + 7);
            });

            worker.start();
            worker.join();

            System.out.println("sharedResult=" +
                    segment.get(ValueLayout.JAVA_INT, 4));
        }

        MemorySegment heap = MemorySegment.ofArray(
                new int[] {5, 6});
        System.out.println("heapValue=" +
                heap.getAtIndex(ValueLayout.JAVA_INT, 1));
    }
}
```

**Compile and run (JDK 22+):**

```bash
javac FfmScopeSafetyDemo.java
java FfmScopeSafetyDemo
```

This is **complete Java 22+ source** (class and file name match); use both `javac` and `java` from the same JDK 22 or newer. Do not use `--enable-preview` for FFM finalized in Java 22. If using JDK 21 or older, do not treat compilation failure as a program bug: choose the right JDK for the example.

**Expected stdout:**

```text
confined=42
aliveInside=true
otherAccessible=false
otherThread=WrongThreadException
outOfBounds=IndexOutOfBoundsException
misaligned=IllegalArgumentException
readOnly=IllegalArgumentException
aliveAfter=false
afterClose=IllegalStateException
sharedResult=107
heapValue=6
```

Output explanation:

1. The confined native region has 8 bytes, holding two `int`s. The value at offset 0 is 42, and the scope is alive before leaving `try`.
2. The worker thread sees `isAccessibleBy` as `false`; a `get` on the confined segment raises `WrongThreadException`. The main thread uses `join`, so the output is in order.
3. Offset 8 for a 4-byte `int` is out of bounds; offset 1 does not satisfy 4-byte alignment; the read-only view does not allow `set`.
4. `escaped` is a 4-byte slice located at offset 4 of the original block, but shares the **same scope** as the confined arena. After leaving `try`, `isAlive() == false`; accessing the slice produces `IllegalStateException`.
5. The shared arena allows the worker to read 100 and write 107 at offset 4, and then the main thread reads 107 after `join`. There is no access after the shared arena closes.
6. The heap segment wraps `int[]{5,6}`, so `getAtIndex(..., 1)` returns 6.

The example does not use `System.loadLibrary`, JNI, FFM downcalls, or C pointers, because the goal is to test **memory safety/lifecycle** before adding the risks of native function interoperability.

## 10. Common Mistakes When Passing Segments Through Async APIs

### Mistake: closing the arena before the callback uses the segment

```java
// Pseudocode: service.submit() is a configured executor.
MemorySegment segment;
try (Arena arena = Arena.ofShared()) {
    segment = arena.allocate(128);
    service.submit(() -> consume(segment));
} // Flawed design: the arena may close before consume() runs.
```

This is **illustrative code** with `service`/`consume` undeclared. `ofShared` allows workers to access by thread, but **does not** guarantee existence until the worker actually runs. The program may encounter `IllegalStateException` or fail at the time of use if the arena has already closed.

### Correct way: the owner waits for all tasks to finish before closing

```java
// Illustration inside a method with ExecutorService executor and
// a declared consume(MemorySegment) method.
try (Arena arena = Arena.ofShared()) {
    MemorySegment segment = arena.allocate(128);

    java.util.concurrent.Future<?> task =
            executor.submit(() -> consume(segment));

    task.get(); // This example needs appropriate checked-exception handling.
} // Only close after the task has completed.
```

This is a **conceptual snippet**, not standalone code. In a real application, you must also ensure no other tasks, callbacks, or native code are still using the segment, handle cancellation/failure, and close on the owner after all outstanding operations are confirmed complete. `Future.get()` throws checked exceptions, requiring `throws` or `catch` in the appropriate place.

### Mistake: using ThreadLocal to assume transferring confined ownership

```java
// Invalid by design:
MemorySegment confinedData = createOnThreadA();
startThreadB(() -> confinedData.get(ValueLayout.JAVA_INT, 0));
```

This is pseudocode; there is no "owner change" by passing through a Java collection, `ThreadLocal`, `CompletableFuture`, or changing the thread name. If access on thread B is needed, either copy the data to a Java object, or create a confined arena **on B**, or use a shared arena from the start.

## 11. Bridge API Cases: Slice, ByteBuffer, and Closure

A Java library can wrap a segment into a very ordinary-looking API:

```java
// Illustrative snippet; not a standalone program.
final class NativeBlock implements AutoCloseable {
    private final Arena arena = Arena.ofConfined();
    private final MemorySegment data = arena.allocate(64);

    byte read(long index) {
        return data.get(ValueLayout.JAVA_BYTE, index);
    }

    @Override
    public void close() {
        arena.close();
    }
}
```

The pattern above is useful when `NativeBlock` is always used **on the thread that created it**, closed exactly once, and does not let `MemorySegment`/`ByteBuffer` escape to places with a longer lifetime. However, if `NativeBlock` is passed between threads or registered with a callback without coordination, the Java wrapper cannot resolve `WrongThreadException`/`IllegalStateException` on its own.

Do not write APIs that directly return a `ByteBuffer` or `MemorySegment` from a `try (Arena arena = ...)` and then close the arena before the caller uses the data. A `ByteBuffer` created from `segment.asByteBuffer()` retains the segment's lifetime/thread constraints. The caller holding the buffer does not mean the backing native memory is still valid.

Clearer API choices:

- For small data or when zero-copy is not needed, return `byte[]`, `int[]`, `String`, or an immutable record and copy out while the arena is still alive.
- For large data and zero-copy, require the caller to manage the `AutoCloseable` owner or a callback that receives the segment **only within** the lifetime scope.
- For multi-threading, use a shared arena but still have a reference-counting/leases/task-coordinator mechanism and a single place responsible for closing.
- For native plugins, clearly determine whether library handles, downcall handles, and callbacks/upcall stubs outlive the arena.

`try-with-resources` only controls **when the Java owner calls close**; to be safe across the entire system, you must know every alias/consumer using this resource.

## 12. Expected Exceptions and How to Diagnose Them

| Symptom | Common Cause | How to Handle |
| --- | --- | --- |
| `IllegalStateException` on `get`/`set` | Scope is closed, segment or slice/buffer is still being used | Fix lifetime; copy data or extend arena ownership appropriately |
| `WrongThreadException` on `get` | Confined segment accessed from a non-owner thread | Use on owner thread, copy, or switch to a shared arena properly |
| `WrongThreadException` on `arena.close()` | Closing a confined arena from a thread other than the owner | Owner thread closes; do not offload closing to any executor |
| `IndexOutOfBoundsException` | Offset/length exceeds `byteSize()` or slice bounds | Calculate in **bytes**, account for full layout size, and check indices |
| `IllegalArgumentException` regarding alignment | Address+offset does not satisfy layout alignment | Allocate/offset according to `byteAlignment()`, use an appropriate layout |
| `IllegalArgumentException` on `set` | Segment/read-only view does not allow writing | Read only or work with a writable segment |
| `IllegalStateException` on `Arena.close()` | Arena already closed, or concurrent segment operations in progress per contract | Designate one owner to close once; wait for operations to finish |
| `UnsupportedOperationException` on `Arena.ofAuto().close()`/`Arena.global().close()` | Arena type does not allow explicit closing | Choose confined/shared for deterministic lifetime |
| `IllegalCallerException` on `reinterpret`/restricted API | Caller module does not have native access | Configure `--enable-native-access` appropriately while assessing risk |
| Native crash/segfault despite Java segment having bounds | Native code uses invalid pointer, wrong ABI, or restricted reinterpret assigns wrong bounds/lifetime | Check C ownership/ABI/symbols, avoid forged pointers, use sanitizers/logs |

**Do not use a broad try/catch catching `RuntimeException` to ignore FFM errors** and then continue with the same segment. Lifetime or wrong-thread errors indicate a flawed ownership structure; fix the design instead of repeatedly retrying with an old pointer.

### `scope().isAlive()` is not an all-powerful debugger

`isAlive() == true` only indicates the scope state according to the FFM model **at the time it is queried**. It does not prove:

- That the native address returned by a C library still has a real backing allocation.
- That the thread has access permission (confinement check is still needed).
- That the offset and layout are valid (bounds/alignment still apply).
- That data is synchronized between multiple threads.
- That native code does not retain the pointer after Java closes the arena.
- That no async callback will access it after the time you close the arena.

To diagnose, log the **arena type**, owner/caller thread, allocate/close timestamps, byteSize, segment source, and callback phase. Do not log/exchange native memory addresses as tokens that can be accessed forever.

## 13. FFM Safety Boundaries: Raw Pointers, Reinterpret, and Native Functions

FFM checks very well when a segment **is properly created from a valid arena** and all accesses are performed through the FFM API. However, when interacting with a C library, FFM often receives only an **address** rather than full allocation metadata:

```c
/* C illustration: a native function may return a buffer address.
 * The definitions of create_buffer/free_buffer and ownership
 * must be clearly stated in the C library documentation.
 */
void *create_buffer(size_t *size_out);
void free_buffer(void *buffer);
```

A `MemorySegment` representing a raw address may only have **byteSize 0** because Java does not know how long that region is. If you try `get(JAVA_INT, 0)` on a zero-length segment, FFM has no proof of valid bounds and will block it with `IndexOutOfBoundsException`. This is by design.

Restricted methods such as `reinterpret(long newSize)` or `reinterpret(long, Arena, Consumer)` allow **assigning an assumed size or scope** to a native address. They are useful when the C API provides a trustworthy contract on size and lifetime, but if the programmer declares it incorrectly:

- `newSize` larger than the real C region → FFM may allow accesses within the **declared bounds** that exceed the real backing allocation.
- Java arena is still alive while C has already `free`d the underlying region → **use-after-free** can occur even though `scope().isAlive() == true`.
- Cleanup callback calls `free` twice or uses a mismatched allocator → memory corruption.
- Holding a raw address after the arena is deallocated or the callback/upcall has expired → native code may crash.
- `Arena.global()` not freeing resources also does not mean another library's pointer remains valid.

**Therefore:** FFM does not eliminate the requirement to understand **C's ownership contract**. When using pointer-returning functions, you must know who allocates, the number of bytes, alignment, who frees, when callbacks are valid, and whether native code retains the pointer across calls. Using restricted APIs requires much more careful review than calling `Arena.ofConfined().allocate(...)`.

### Downcall/upcall and lifetime

With a foreign function call, a `MemorySegment` can be passed as a native pointer argument; a downcall handle can remain tied to the loaded library/lookup and the arena's lifetime; an upcall stub also has a scope/lifecycle and can be retained by native code. When the arena closes, Java wrappers may be invalidated, but **external native code does not necessarily obey all Java FFM checks**.

In design:

1. Clearly document which native library owns which allocation, and how long each callback function pointer needs to live.
2. Do not let native code store a pointer to a short-lived arena's buffer after the arena will close, unless there is a copy contract.
3. Manage the scope of symbol lookups/upcall stubs appropriately for the entire duration native code may call them.
4. Before closing, stop tasks/callbacks and wait for foreign calls still using the resource to finish per contract.
5. Do not arbitrarily `reinterpret` to "fix" a bounds/lifetime exception; fix the source of metadata and ownership.

## 14. Design Selection Patterns for Applications

| Need | Appropriate Approach | What Still Must Be Guaranteed |
| --- | --- | --- |
| Native buffer within a synchronous function | `try (Arena a = Arena.ofConfined())` | Use on the right owner thread, do not return segment out of scope |
| Multiple workers reading a shared native region | `Arena.ofShared()` | Wait for tasks to finish before closing; synchronize if there are writes |
| Result needing to live after the call | Copy to Java heap or return `AutoCloseable` owner | Caller knows who closes and when |
| Large temporary native region, GC-managed | `Arena.ofAuto()` | Do not rely on when GC frees it |
| Data truly living for the entire VM lifetime | `Arena.global()` under control | Accept unbounded lifetime and native memory pressure |
| Creating a view into part of a buffer | `asSlice(...)` | Slice has smaller bounds and inherits scope |
| Providing a non-writable view | `asReadOnly()` | Other writable aliases can still mutate data; same lifecycle |
| Using an existing Java array | `MemorySegment.ofArray(...)` | Heap lifecycle, Java thread synchronization |
| Receiving a C pointer + length from a native library | Check contract and restricted reinterpret if needed | Compute exact backing size, ownership, ABI, lifetime; avoid crash |
| Running on JDK 17 | Use API suitable for JDK 17, or upgrade JDK to use Java 22+ code | Do not copy finalized `java.lang.foreign` code verbatim into JDK 17 |

Choose an arena based on the **actual ownership model** and execution path, not on the goal of "just avoiding WrongThreadException". Moving every buffer to shared/global just to make errors disappear can make memory reclamation and shared data **harder to control**.

## 15. Review and Testing Checklist

Before putting FFM into production, walk through each item in order:

1. **Version:** build and runtime match the API policy, using JDK 22+ for finalized `java.lang.foreign`; restricted APIs have an appropriate native access policy.
2. **Data source:** is the memory segment heap/native/mapped/raw address? Who owns the backing memory?
3. **Byte bounds:** `byteSize()` matches the actual byte count, not confusing bytes with element count and not exceeding the native allocation.
4. **Alignment:** `ValueLayout.byteAlignment()` matches the C ABI/struct field alignment and actual offset.
5. **Scope:** who creates the arena, who closes it, which scope does it leave? Do any variables/lambdas/ByteBuffers/slices still hold the segment?
6. **Thread:** which thread is the confined owner; are there workers, virtual threads, async callbacks, or executors transferring work?
7. **Shared data:** are writers protected by appropriate locks/atomic operations/memory ordering?
8. **Close:** has the coordinator waited for all outstanding consumers, callbacks, and foreign calls before closing the shared arena?
9. **Heap conversion:** if returning results outside the scope, has the necessary data been copied to a Java-owned representation?
10. **Native contract:** have pointer-returning functions, `free`/allocator, restricted reinterpret, and callbacks had their actual size/lifetime verified?
11. **Error paths:** do all Java exceptions, task cancellations, and native failures lead to close/cleanup exactly once?
12. **Tests:** are there tests for off-by-one, read-only, misalignment, wrong-thread, access-after-close, concurrent lifecycle, and version mismatch?

### Small test suite for the three mechanisms

| Case | Setup | Expected Result |
| --- | --- | --- |
| Valid access | Owner thread, scope alive, valid offset | Written value is read accurately |
| Out of bounds | 8-byte segment, read `JAVA_INT` at offset 8 | `IndexOutOfBoundsException` |
| Wrong alignment | 4-byte aligned segment, read `JAVA_INT` at offset 1 | `IllegalArgumentException` |
| Wrong thread | Worker reads segment from main's confined arena | `WrongThreadException` |
| After close | Main closes arena, reads old segment/slice | `IllegalStateException` |
| Read-only | `asReadOnly().set(...)` | `IllegalArgumentException` |
| Coordinated shared | Worker processes, main `join`s, then closes | Success |
| Uncoordinated shared | Close while tasks may still be running | Design violation; do not program relying on a specific exception |
| Forge native pointer | Assign wrong bounds/lifetime via restricted API | Can lead to native memory errors/JVM crash; do not test on production systems |

## 16. Self-Check Questions

**1. Why is keeping a `MemorySegment` in a `static` field not enough to access it after `Arena.close()`?**

Because `MemorySegment` is a Java object describing a **scope**. When the arena closes, the scope becomes invalid and the native backing region is freed; a reference to the Java object does not extend the lifetime of the native region. Access via FFM after close is normally blocked with `IllegalStateException`.

**2. Can `synchronized(segment)` be used so thread B can access a segment from `Arena.ofConfined()`?**

**No.** A lock does not change the owner thread bound to a confined arena. Thread B still receives `WrongThreadException` on access. Copy the data, use an arena created on B, or use a shared arena with appropriate synchronization.

**3. If using `Arena.ofShared()`, are two threads incrementing a counter with `get` then `set` automatically atomic?**

**No.** Shared only allows access from multiple threads; it does not guarantee a read-modify-write sequence is race-free. Use `VarHandle` atomic operations or a lock with valid memory ordering.

**4. A Java snippet creates a slice `asSlice(4,4)` from a 16-byte original segment. Can the slice read offset 12?**

**No.** The slice's offset is calculated from the **base of the slice**, and the slice is only 4 bytes long. Reading `JAVA_INT` at offset 12 is out of bounds, even though the original region still has bytes at offset 16. A slice has its own spatial bounds but shares the same lifetime scope.

**5. Does `isAlive()==true` guarantee that a C pointer wrapped with `reinterpret` is still alive?**

**No.** It only reflects the declared Java scope. If native code freed the allocation earlier, the Java information may not match the real lifetime and there is still a risk of use-after-free.

**6. When should `Arena.ofAuto()` be used instead of `ofConfined()`?**

When a GC-managed lifecycle meets requirements and a deterministic close time is not needed. `ofAuto()` allows multi-thread access, but `close` is not supported; it is not suitable when native memory must be reclaimed immediately upon completing an operation.

**7. Why does Java 17 fail to compile the `FfmScopeSafetyDemo.java` program in this article?**

Because finalized `java.lang.foreign` APIs (JEP 454) are only available starting in JDK 22. Java 17 has an **incubator** foreign API with a different package/module and shape; you must use that JDK's exact API or upgrade the JDK.

**8. Should you catch `IllegalStateException` and retry `segment.get(...)` after the arena closes?**

No. A closed scope cannot be revived by retrying; you must allocate a new segment in an alive arena and transfer/copy data according to an appropriate ownership contract.

**9. Does `WrongThreadException` indicate that the program has a data race?**

It primarily indicates a **thread confinement violation** of the segment/arena. It is not a detector for all data races. A shared arena can allow two threads to access while the code is still buggy due to missing synchronization.

**10. Why not use `Arena.global()` to bypass both close and thread restrictions?**

A global arena has an unbounded lifetime and cannot be explicitly closed, so native allocations may not be freed during the JVM's lifetime. It also does not fix data races, native ABI, ownership of external pointers, or bugs in C/C++ code. You should choose the right lifetime rather than discarding lifecycle management for easy access.

## 17. Official Documentation

- Oracle Java SE 22 — [`java.lang.foreign` package: spatial and temporal safety](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html).
- Oracle Java SE 22 — [`Arena`: confined/shared/automatic/global, `close()`, and thread confinement](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html).
- Oracle Java SE 22 — [`MemorySegment`: scope, `isAccessibleBy`, `asSlice`, bounds, and alignment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html).
- Oracle Java SE 22 — [`MemorySegment.Scope` and `isAlive()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.Scope.html).
- OpenJDK JEP 454 — [Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454).
- Oracle Java SE 25 — [Foreign Function and Memory API guide, memory segments and foreign functions](https://docs.oracle.com/en/java/javase/25/core/foreign-function-and-memory-api.html).

**Remember:** FFM helps prevent **out-of-bounds**, **use-after-close**, and **wrong-thread access** on valid memory segments through corresponding runtime checks. `Arena` determines lifetime and confinement; `MemorySegment` holds byte bounds and scope; the application is responsible for deciding when to close, which thread owns it, and how consumers coordinate. With arbitrary C addresses, restricted reinterpret, callbacks, and data races, **safety still depends on ownership design and the real native contract**.