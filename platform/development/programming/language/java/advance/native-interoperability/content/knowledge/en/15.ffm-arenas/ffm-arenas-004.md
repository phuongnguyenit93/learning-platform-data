# Arena.ofAuto, GC, and Non-Deterministic Deallocation Timing in Java FFM

`Arena.ofAuto()` is one of the four ways to create an `Arena` in the Foreign Function & Memory API (FFM). The decisive difference is that the native memory allocated by the arena is **managed for reclamation by the garbage collector (GC)** instead of being explicitly freed by the application at a deterministic `close()` call.

**Do not confuse GC-managed with immediate free:** the Java 22 documentation specifies that native regions belonging to an automatic arena are freed at an **unspecified time**, after **the arena itself and all memory segments allocated from it are no longer reachable**. Exiting a method, assigning a variable to `null`, or calling `System.gc()` does not guarantee that the native memory has been freed immediately at that moment.

`Arena.ofAuto()` is suitable when a non-deterministic lifetime is acceptable and native memory costs are under control. If immediate reclamation is needed when a request/batch/task finishes, `Arena.ofConfined()` or `Arena.ofShared()` should be used with a clear owner and `close()`. This is a **resource management** decision, not merely a syntactic difference.

**Version:** the runnable Java snippets in this article use **JDK 22+**, when FFM was finalized under JEP 454. Java 17 used a different incubator API; Java 19–21 used a preview API with differences. Do not copy `java.lang.foreign.Arena` code from this article into Java 17 and expect it to compile unchanged.

## 1. Properly Understanding the Lifecycle of an Automatic Arena

An allocation typically looks like this:

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

Arena arena = Arena.ofAuto();
MemorySegment segment = arena.allocate(
        2L * Integer.BYTES,
        ValueLayout.JAVA_INT.byteAlignment());

segment.setAtIndex(ValueLayout.JAVA_INT, 0, 12);
segment.setAtIndex(ValueLayout.JAVA_INT, 1, 30);
int answer = segment.getAtIndex(ValueLayout.JAVA_INT, 0)
           + segment.getAtIndex(ValueLayout.JAVA_INT, 1);
// answer == 42
```

This is an **illustrative snippet inside a Java method**, not a standalone runnable class. It allocates 8 native bytes (two `int`s, 4 bytes each), aligned according to `ValueLayout.JAVA_INT`, then writes/reads. `MemorySegment` is a Java object describing the address, size, and scope of the native region. The Java object itself **is not** those 8 native bytes.

```text
GC roots in the JVM
      |
      +--> Arena auto --------+
      |                       |
      +--> MemorySegment A ---+--> native bytes of A
      |                       |
      +--> MemorySegment B ---+--> native bytes of B
               |
               +--> Slice/View (same arena scope)

If a reference to the arena or a related segment still exists
    -> it cannot be inferred that the whole group of native memory has been freed.

When the Arena and ALL related segments are unreachable
    -> the native regions become eligible for GC-managed deallocation
       at AN UNSPECIFIED TIME.
```

An automatic arena can allocate multiple segments. They share the same **arena scope**. When discussing GC eligibility, the entire group must be considered, not just a single `segment` variable in a code block.

## 2. Three Layers to Distinguish: Java Object, Native Allocation, Scope

| Layer | What does it contain? | Who manages it? | Common misconception |
| --- | --- | --- | --- |
| Java references | `Arena`, `MemorySegment`, and aliases/views | Java GC/reachability | Losing a reference does not mean native bytes are freed immediately |
| Native backing memory | Bytes located outside the Java heap | Arena/JVM or appropriate native allocator | Not fully measured via Java heap usage |
| Arena scope | Lifetime and access constraints of segments | Arena and FFM runtime | `scope().isAlive()` is not a clock indicating when GC frees memory |

`Arena.ofAuto()` creates an **automatic scope**. The Java GC manages when the backing memory region is reclaimed once reachability conditions are met. An automatic scope differs from the closeable scope of a confined/shared arena: the programmer is not permitted to manually close it to force the lifecycle to end.

A `MemorySegment` Java object can be tiny compared to its allocation. For example, a segment representing a 128 MiB off-heap region does not necessarily cause the Java heap to grow by 128 MiB. An application that only watches the heap chart may miss memory pressure at the process/container level.

## 3. What Does `Arena.ofAuto()` Guarantee?

According to the Java 22 FFM Javadoc:

1. `Arena.ofAuto()` creates an GC-managed **automatic arena**.
2. Native memory regions allocated from the arena are **zero-initialized**; reading primitive values before writing will see all 0 bytes (given a valid layout/offset).
3. Segments of an automatic arena **can be accessed from any Java thread**, not restricted to a single owner thread like a confined arena.
4. **`auto.close()` throws `UnsupportedOperationException`**. Automatic arenas do not support manual close.
5. Native regions are only **freed at an unspecified time after the automatic arena and all of its segments become unreachable**.

There are also things that are **not guaranteed**:

- No SLA such as 10 ms, 1 second, or a specific GC cycle for freeing.
- No guarantee that `System.gc()` will clean up immediately.
- Not a promise that RSS will drop immediately after GC.
- No automatic synchronization of reads/writes to shared native memory.
- No automatic lifetime preservation for a raw C pointer for which Java no longer holds corresponding references.
- No freeing of other native resources (sockets, global native state, file descriptors) merely because a Java automatic arena loses reachability.

`Arena.ofAuto()` is an **ownership/lifetime policy** choice, not an API for destroying all native resources in a program.

## 4. Comparison Table of the Four Arena Types

| Type | Lifetime | Explicit `close()`? | Thread access | When to choose |
| --- | --- | --- | --- | --- |
| `Arena.ofConfined()` | Bounded, deterministic close point | **Yes**, closed by owner thread | Owner thread only | Synchronous processing, resource used within a single method |
| `Arena.ofShared()` | Bounded, deterministic close point | **Yes**, coordinated close after consumers finish | Any thread | Buffers used by multiple workers/callbacks with independent lifecycles |
| **`Arena.ofAuto()`** | Bounded, **non-deterministic GC deallocation timing** | **No**; calling close throws `UnsupportedOperationException` | Any thread | Short/medium-lived native data where GC-managed cleanup is acceptable |
| `Arena.global()` | Unbounded for the lifetime of the VM | **No**; calling close throws `UnsupportedOperationException` | Any thread | Data intentionally kept alive for the entire JVM lifetime |

Both `ofAuto` and `global` cannot be closed, but they are **not synonymous**. Automatic has GC-managed deallocation conditions; global has an unbounded lifetime and its native regions are not automatically freed during the VM's lifetime. Do not use `global()` as a "faster auto" replacement for repeated allocations.

Conversely, `ofConfined` and `ofShared` are designed so the application can decide precisely when to end the lifetime. If close succeeds, the backing native regions are deallocated and accesses through associated segments become invalid.

## 5. Why Unreachable Is Different from Already Freed

Consider the example:

```java
// Conceptual illustration; do not use to assert GC timing.
MemorySegment segment = Arena.ofAuto().allocate(1024);
segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 7);

// ... use segment ...

segment = null;
// There is no guarantee that the 1024 native bytes are freed right here.
```

There are three states to keep distinct:

1. **Still reachable:** a reference path from GC roots still keeps the arena/segment/alias alive. The memory has not yet met the reachability condition to be collected by the automatic arena.
2. **Eligible for GC-managed cleanup:** the arena **and all of its segments** are no longer reachable. The JVM may process freeing the native memory later.
3. **Actually deallocated:** cleanup actually occurs. The documentation publishes no deadline from state 2 to state 3.

One more point: even when the runtime/allocator has freed a block of native memory, **RSS might not drop** because the native allocator or OS may retain pages for reuse. Therefore, a static RSS observation cannot distinguish all of the states above.

The line `segment = null` also only drops **one** reference. If a cache holds a slice, a callback holds another segment, or the arena variable is still reachable, one cannot conclude that the condition for the whole group has been met.

### Scope Does Not Exactly Match Curly Brace Scope

```java
// This is an illustrative example, not a standalone class.
MemorySegment outside;
{
    Arena automatic = Arena.ofAuto();
    outside = automatic.allocate(4);
}
// outside can still use the native region at this point;
// leaving the block does NOT call close() and does not force GC reclamation.
outside.set(ValueLayout.JAVA_INT, 0, 5);
```

In this example, `outside` continues to keep the segment reachable. Leaving the **lexical** scope of the `automatic` variable is not the same as ending the **FFM arena scope**.

## 6. One Still-Used Segment Can Retain the Whole Group of Allocations

An automatic arena can allocate multiple segments with different usage lifecycles:

```java
// Retention illustration, not a standalone runnable benchmark.
Arena automatic = Arena.ofAuto();

MemorySegment large = automatic.allocate(64L * 1024 * 1024);
MemorySegment tiny = automatic.allocate(4);

large = null;
// tiny is still in use; automatic is also still referenced here.
tiny.set(ValueLayout.JAVA_INT, 0, 1);
```

One must not claim the 64 MiB buffer has been freed individually because the `large` variable became null. The condition from the Javadoc applies at the level of the automatic arena **and all memory segments allocated by it**. If a single segment or a reference to the arena lives long, the native memory of the entire group may be retained longer than expected.

A dangerous case is using **a single automatic arena** to allocate many large buffers for different requests, then storing some small segments from that arena into a long-lived cache. The lifetime of the small cache may be incompatible with the life of the large buffers.

**Better design:** separate arenas by lifetime, or only keep a **Java primitive/value object** if 4 bytes of state are needed. For large buffers with a clear processing end point, use a closeable arena and free them there rather than letting the GC guess.

### Aliases and Views Also Matter

`segment.asSlice(...)` creates a new segment with its own view/bounds but the same arena scope; `segment.asReadOnly()` also does not grant an independent arena lifetime. If a Java object, collection, lambda, or task still holds these views, merely setting the original reference to null does not necessarily make the backing memory eligible for reclamation.

`segment.asByteBuffer()` creates a Java `ByteBuffer` view into the segment. When sharing buffers/views across layers, treat them as **aliases that can extend reachability** and adhere to the same lifetime contract, rather than only looking at the field storing the original `MemorySegment`.

## 7. Runnable Java 22+ Example Independent of GC Timing

The following program demonstrates **deterministic behaviors** according to the FFM API. It intentionally does **not** call `System.gc()` and does **not** print a "memory freed" message, because automatic arena cleanup timing cannot be guaranteed by a short test.

The program shows:

- The native region of an auto arena is initially 0.
- `byteSize`, `get`, `set`, and `asSlice` produce accurate results.
- An auto arena segment is accessible from a worker thread.
- `auto.close()` throws `UnsupportedOperationException`, and the failed close does not invalidate the segment.
- A confined arena can be closed, and after closing, all of its segments are no longer accessible.

### File `AutoArenaGcDemo.java`

```java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class AutoArenaGcDemo {
    public static void main(String[] args)
            throws InterruptedException {

        Arena auto = Arena.ofAuto();
        MemorySegment values = auto.allocate(
                2L * Integer.BYTES,
                ValueLayout.JAVA_INT.byteAlignment());

        System.out.println("bytes=" + values.byteSize());
        System.out.println("initial=" +
                values.getAtIndex(ValueLayout.JAVA_INT, 0));

        values.setAtIndex(ValueLayout.JAVA_INT, 0, 12);
        values.setAtIndex(ValueLayout.JAVA_INT, 1, 30);

        MemorySegment second = values.asSlice(
                Integer.BYTES, Integer.BYTES);
        int sum = values.getAtIndex(ValueLayout.JAVA_INT, 0)
                + second.get(ValueLayout.JAVA_INT, 0);

        System.out.println("sum=" + sum);
        System.out.println("autoAlive=" +
                auto.scope().isAlive());

        Thread worker = new Thread(() -> {
            int value = second.get(ValueLayout.JAVA_INT, 0);
            System.out.println("workerRead=" + value);
        });
        worker.start();
        worker.join();

        try {
            auto.close();
            System.out.println("unexpectedCloseSuccess");
        } catch (UnsupportedOperationException expected) {
            System.out.println(
                    "autoClose=UnsupportedOperationException");
        }

        System.out.println("afterCloseAttempt=" +
                values.getAtIndex(ValueLayout.JAVA_INT, 0));

        MemorySegment escaped;
        try (Arena confined = Arena.ofConfined()) {
            escaped = confined.allocate(ValueLayout.JAVA_INT);
            escaped.set(ValueLayout.JAVA_INT, 0, 7);
            System.out.println("confinedInside=" +
                    escaped.get(ValueLayout.JAVA_INT, 0));
        }

        try {
            escaped.get(ValueLayout.JAVA_INT, 0);
            System.out.println("unexpectedAccessAfterClose");
        } catch (IllegalStateException expected) {
            System.out.println(
                    "confinedAfterClose=IllegalStateException");
        }

        System.out.println("end");
    }
}
```

### Compile and Run

Use **JDK 22+**, with `javac` and `java` from the same JDK. FFM was finalized in JDK 22, so this code does not need `--enable-preview`. The code only allocates/reads/writes memory and does not call restricted foreign functions, so `--enable-native-access` is also unnecessary for this example.

```bash
java -version
javac AutoArenaGcDemo.java
java AutoArenaGcDemo
```

`java -version` prints the version depending on the environment; the deterministic stdout of the `java AutoArenaGcDemo` command is:

```text
bytes=8
initial=0
sum=42
autoAlive=true
workerRead=30
autoClose=UnsupportedOperationException
afterCloseAttempt=12
confinedInside=7
confinedAfterClose=IllegalStateException
end
```

### Why Do Those Results Occur?

1. `bytes=8` because there are two `int`s, 4 bytes each.
2. `initial=0` because a native region newly allocated with an auto arena is zero-initialized.
3. `sum=42` because element 0 = 12 and the slice at offset 4 contains element 1 = 30.
4. `autoAlive=true` because the auto arena/segment is currently in use within the method. This is not a promise about future GC timing.
5. `workerRead=30` because an automatic arena allows access from another thread; `join()` stabilizes the output order.
6. `autoClose=UnsupportedOperationException` because an automatic arena does not allow explicit close.
7. `afterCloseAttempt=12` demonstrates that a failed close does not free the memory.
8. `confinedInside=7` inside `try-with-resources`; after the confined arena closes, the `get` operation throws `IllegalStateException`.
9. No native free time is printed; the FFM documentation **does not specify** such an assertable time for `ofAuto()`.

The takeaway is distinguishing **deterministic API behavior** from **non-deterministic GC scheduling**.

## 8. Why Not Use try-with-resources with `ofAuto()`?

Every `Arena` implements `AutoCloseable`, so the following snippet can **compile**, but it is the wrong lifetime choice:

```java
// Error illustration; place inside a method of a Java 22+ class.
try (Arena arena = Arena.ofAuto()) {
    MemorySegment segment = arena.allocate(16);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
}
// Upon leaving the block, try-with-resources calls arena.close():
// UnsupportedOperationException.
```

`AutoCloseable` does not mean every arena type supports close according to the contract. `Arena.ofAuto()` and `Arena.global()` **do not allow manual closing**. If exiting the block is expected to free native memory immediately, replace it with:

```java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment segment = arena.allocate(16);
    segment.set(ValueLayout.JAVA_BYTE, 0, (byte) 1);
} // close() succeeds: native regions are deallocated.
```

If the buffer must be accessed by other worker threads, replace `ofConfined()` with `ofShared()` **and wait for all workers/callbacks to complete before closing**. Do not treat `ofShared` as a complete replacement for concurrency coordination.

## 9. GC Has No Deadline; System.gc Is Not free

`System.gc()` sends a request for the JVM to consider GC. It does not provide a contract for the application to say:

- GC has definitely run completely before the call returns.
- An automatic arena that is no longer referenced will be cleaned up immediately.
- Native pages are returned to the OS immediately after cleanup.
- RSS must drop by a certain amount after a GC.
- The program can rely on 100 ms or 5 seconds to free auto memory.

The following example **is not a valid test**:

```java
// Anti-pattern illustration code; not a valid benchmark.
MemorySegment block = Arena.ofAuto().allocate(1024 * 1024);
block = null;
System.gc();
// WRONG if claiming here that 1 MiB native has been freed.
```

A JVM may delay or skip explicit GC depending on configuration; even when cleanup happens, the native allocator/OS does not necessarily reduce the RSS metric immediately. Tests relying on `Thread.sleep(...)` after `System.gc()` are also flaky and do not form a portable guarantee.

### Does WeakReference Prove Native Free?

No. A `WeakReference<MemorySegment>` only provides observation of **the weakly referenced Java referent**; it does not prove that all segments of the arena are no longer reachable, that native cleanup has run, or that the OS has reclaimed pages. Using weak references to diagnose reachability can be useful, but **do not** use the result of a weak reference as a memory-free clock.

### Does Cleaner Make Auto Deterministic?

No. `Cleaner` is also tied to reachability/GC and has no deadline like `finally` or `try-with-resources`. Do not register another cleaner to manually `free` a buffer from `Arena.ofAuto()`; the JVM/arena already owns that allocation. Applying an incorrect allocator/free to this region can cause double-free/corruption. For external native resources, clear ownership and an appropriate cleanup callback are needed, not adding cleaners by guesswork.

## 10. `ofAuto()` Allows Any-Thread Access, But Does Not Auto-Synchronize Data

FFM distinguishes **thread accessibility** from **data-race freedom**. An automatic arena does not have the owner-thread restriction of a confined arena, so a worker can call `segment.get(...)` while the segment is valid. However, two threads concurrently modifying a value via read-modify-write can lose updates:

```java
// Illustrative snippet in a method; 'counter' is a MemorySegment
// from an automatic/shared arena.
int oldValue = counter.get(ValueLayout.JAVA_INT, 0);
counter.set(ValueLayout.JAVA_INT, 0, oldValue + 1);
```

If two threads run concurrently, the result is not guaranteed to be correct merely because the arena is `ofAuto()`. Synchronization, memory ordering, or a `VarHandle` with atomic operations appropriate for the layout, address, and ABI is required. Thread-safe access to a segment does not make a `get` + `set` combination an atomic transaction.

Using `Arena.ofShared()` does not automatically solve races either; it only permits multi-thread access and **adds explicit close** to the contract. Therefore, the auto/shared decision is based on **lifetime**, while the lock/atomic decision is based on **concurrency**.

## 11. Especially Dangerous: Native C Holds a Pointer After Java Drops the Reference

An FFM program can pass a native address to C. Suppose C saves a `void*` in a global variable for a callback to use later:

```c
/* Illustrative C declarations, not a standalone program. */
void native_store_pointer(void *buffer);
void native_use_later(void);
```

If Java **does not hold** a strong reference to the arena or segment for the entire time native code needs the pointer, the JVM GC does not automatically know that a C global variable holds that raw pointer. When the automatic arena becomes eligible for cleanup and the backing memory is freed, C reading the old pointer can cause **use-after-free**.

```text
Java MemorySegment ----> native allocation
      |
      +-- C receives raw address and stores it for later use
      |
Java drops all owner references
      |
automatic arena can be GC-managed deallocated
      |
C still reads old raw pointer ----> memory corruption / crash
```

FFM checks temporal/spatial safety when code accesses via `MemorySegment` with valid metadata. However, **C dereferencing a raw pointer falls outside these Java checks**. An automatic arena does not turn every C pointer into a Java GC root.

### How to Handle This

- If C only uses the buffer during **a single synchronous downcall**, keep the segment alive throughout the operation. When working with raw addresses and needing to prevent the JVM/JIT from shortening liveness, consider `java.lang.ref.Reference.reachabilityFence(segment)` at a point after the last use; this call **does not free** native memory and does not validate already-corrupted pointers.
- If C **holds the pointer for asynchronous processing**, design an owner with an explicit lifetime (typically confined/shared depending on threads), and wait for all native work/callbacks to complete before closing.
- If the native subsystem needs **its own ownership of the memory region**, use allocation/deallocation APIs appropriate for the native library with a clear copy/ownership contract, rather than arbitrarily `free`ing regions allocated by an arena.
- With restricted methods like `MemorySegment.reinterpret(...)`, do not arbitrarily declare a size or scope for an unverified C pointer. Bounds/scope known to Java cannot prove an external native allocation is still alive if C has already `free`d it.

**In summary:** to safely share memory with C long-term, **native ownership** must be managed. Do not rely on auto GC to protect callbacks/pointers that the JVM cannot see.

## 12. Native Memory Pressure: Why Can You Run Out of RAM Even When the Heap Has Free Space?

Java GC tracks Java objects and can participate in reclaiming native allocations of an automatic arena, but a large native region does not mean the heap contains the same number of bytes. For example, a small Java `MemorySegment` object can describe many MiB off-heap; increasing the number of native buffers does not necessarily increase heap usage proportionally.

Common scenarios:

- A server allocates an automatic arena with a large buffer per request and expects GC to clean up fast enough for the request rate.
- Image/video/ML jobs allocate hundreds of MiB of native buffers while only watching the heap chart.
- A cache retains a small segment from an arena that allocated many large buffers.
- Async tasks hold segment references longer than expected.
- A C native library holds a pointer after Java has dropped references, creating a use-after-free risk.

**There is no guarantee that the JVM will run GC in time to prevent all kinds of native memory exhaustion.** An application can hit allocation failures or container/OS limits even before the Java heap reaches its threshold.

### Operational Observability

- Measure **process RSS/container memory** alongside Java heap, rather than using heap alone.
- Record metrics for native bytes **requested for allocation** and active tasks; avoid calling a self-computed total "currently unfreed bytes" without an accurate free signal.
- Track the number of cached segments and Java owners still holding references.
- On HotSpot, Native Memory Tracking can be useful if enabled appropriately; it is not guaranteed to cover every external library/allocator.
- Run stress tests at memory limits close to production; measure peak/steady-state and distinguish **retention due to references** from **slow cleanup**.
- Do not write unit tests asserting RSS drops immediately after `System.gc()`.

If predictable release timing is needed, **changing the arena type** is the design solution, not increasing calls to `System.gc()`.

## 13. Three Design Choice Patterns

### Pattern A: Synchronous Temporary Buffer, Needs Freeing on Return

```java
// Illustration inside a method on JDK 22+.
try (Arena arena = Arena.ofConfined()) {
    MemorySegment work = arena.allocate(4096);
    work.set(ValueLayout.JAVA_INT, 0, 123);
    // Process completely on the owner thread.
} // Native memory is cleaned up when close succeeds.
```

Reason for choice: the data's lifetime is tied to a deterministic processing block. GC does not decide the free time.

### Pattern B: Buffer Used by Multiple Workers, with a Completion Point

```java
// Structural illustration; application must define concrete workers.
try (Arena arena = Arena.ofShared()) {
    MemorySegment work = arena.allocate(4096);
    // Dispatch work to workers, synchronizing data if needed.
    // Wait for all outstanding tasks/callbacks to finish.
} // Close the shared arena after all consumers are done.
```

Reason for choice: multiple threads need access, yet the owner must still control when deallocation happens. Do not close the arena while callbacks are still using the memory.

### Pattern C: Buffer with Reference-Dependent Lifetime and No Need for Timely Close

```java
// Illustration inside a JDK 22+ method.
MemorySegment data = Arena.ofAuto().allocate(4096);
data.set(ValueLayout.JAVA_INT, 0, 88);
// Use data while still reachable.
// Do not call data.scope().close(): automatic scope is not closeable.
// Native region is eligible for cleanup after the arena and all
// related segments are unreachable; GC timing is unspecified.
```

Reason for choice: the application accepts non-deterministic deallocation, and allocation size and rate stay within the memory budget. If data becomes a long-lived cache or native C holds the pointer, ownership must be reconsidered.

### Returning Results to the Java Heap to Avoid Extending Lifetime

```java
// Illustrative method, place in a class with appropriate FFM imports.
static long result() {
    try (Arena arena = Arena.ofConfined()) {
        MemorySegment data = arena.allocate(ValueLayout.JAVA_LONG);
        data.set(ValueLayout.JAVA_LONG, 0, 900L);
        return data.get(ValueLayout.JAVA_LONG, 0);
    }
}
```

The method returns a Java `long`, not a `MemorySegment` whose scope is about to close. This is a good solution when the caller only needs a small value rather than a zero-copy native buffer.

## 14. Common Pitfalls

| Mistake | Cause | Fix |
| --- | --- | --- |
| `try (Arena a = Arena.ofAuto())` throws an error when leaving the block | Auto does not support explicit close | Use confined/shared if you want `try-with-resources` |
| RSS does not drop after `System.gc()` | GC/allocator/OS has no obligation to reduce RSS immediately | Do not infer cleanup from a single instantaneous measurement |
| Setting `segment = null` and assuming native memory is freed immediately | The arena, aliases, other segments may remain, or GC has not cleaned up yet | Check reachability of the whole group and accept latency |
| Caching a 4-byte segment accidentally retains large memory | Allocations of one auto arena share a lifetime | Split arenas by task/lifetime or copy small values out to Java |
| Watching only heap memory | Auto arena allocates off-heap regions | Monitor RSS/native memory and workload |
| Switching to `Arena.global()` to avoid close errors | Global does not free allocated regions during the JVM's lifetime | Use global only for state intentionally scoped to the entire process lifetime |
| Treating auto arena as single-thread-only | Confined is what restricts to an owner thread | Auto allows multi-thread, but needs synchronization for shared mutable data |
| Treating `get` + `set` as automatically atomic on an auto arena | Thread accessibility differs from atomicity | Use proper locks/atomic VarHandles |
| C holds a native pointer longer than Java holds the segment | GC does not see a C pointer as a Java root | Explicit ownership/lifetime contract |
| Calling `free()` on memory allocated by an arena | Wrong allocator owner | Let the arena/JVM handle that region |
| Tests relying on `Thread.sleep()` or `WeakReference` to wait for free | No native cleanup deadline | Test API behaviors and memory trends, do not assert timing |
| Changing `MemorySegment.reinterpret` to bypass bounds errors | New metadata may not reflect the real allocation | Verify C pointer size/ownership first |

## 15. Self-Check Questions

**1. A method creates `MemorySegment s = Arena.ofAuto().allocate(1024)` and returns. Is it certain that the 1024 bytes are freed immediately?**

**No.** Lifetime is managed by GC; only after the arena and all related segments become unreachable does the memory become eligible for cleanup, at an unspecified time.

**2. Why do neither `ofAuto` nor `global` allow calling close, yet they are not the same?**

Auto has a bounded lifetime managed by GC, whereas global has an unbounded lifetime for the life of the JVM. Global regions are not automatically cleaned up based on the reachability of a few Java segments.

**3. Can holding a small slice from the same automatic arena affect another large memory region?**

**Yes.** The slice is tied to the arena scope; while references to the arena/segments of the same group remain, it cannot be assumed that the native regions are eligible for deallocation. Design allocations with different lifetimes in different arenas.

**4. Why is `System.gc()` not a way to return native buffers of `ofAuto()`?**

`System.gc()` is a GC request, with no contract guaranteeing completion of deallocation for an automatic arena at the time of the call. For deterministic release, choose a closeable arena from the start.

**5. `Arena.ofAuto()` can be accessed by two threads. Can all synchronization be omitted?**

No. Access permission differs from guaranteeing data is race-free. Two threads writing to the same region need appropriate synchronization/atomic semantics.

**6. Java keeps the Java heap at only 100 MiB, yet auto allocations create large native memory usage. Can that happen?**

Yes. Off-heap native memory is not Java heap; you must monitor process/native memory as well and limit concurrent allocation volume.

**7. If C stores a raw address and Java no longer holds the segment/arena, does auto GC know that pointer needs to stay alive?**

Not automatically. A C pointer is not a Java strong reference to the segment. Once backing memory is cleaned up, native code could use a freed address. An owner/callback contract is needed.

**8. A program wants to return native memory immediately when a batch finishes; which arena type is appropriate?**

Confined if a single owner thread processes it; shared if multiple workers are involved and a coordinator waits for completion. Both types support explicit close, unlike auto.

**9. Can we try `WeakReference<MemorySegment>` and assert native memory is freed when `get()==null`?**

No. A weak reference only tracks the Java referent; it does not prove all segments/arena are unreachable, cleanup has completed, or the OS has reduced RSS.

**10. When is `ofAuto()` a reasonable choice?**

When data does not need to be released by a deadline, the application accepts non-deterministic cleanup, no C raw pointers are retained past the Java lifetime, and an appropriate memory budget/monitoring is in place.

## 16. Production Checklist

Before deciding to use `Arena.ofAuto()`:

1. **Version:** JDK 22+ for finalized FFM; verify the exact runtime/build JDK.
2. **Bytes:** calculate byte count/alignment accurately, avoid unbounded large allocations.
3. **Ownership:** document who still holds the arena/segments, views, callbacks, and caches.
4. **Grouping:** only group allocations with similar lifetimes into the same auto arena.
5. **Close policy:** do not use `try-with-resources` expecting close; understand `UnsupportedOperationException`.
6. **GC assumption:** no free deadline; tests do not assert `System.gc()` has cleaned up.
7. **Thread safety:** distinguish multi-thread accessible from thread-safe data access.
8. **C pointers:** do not let native C hold raw pointers outside the Java lifetime contract.
9. **Monitoring:** monitor process/native memory, not just the heap.
10. **Fallback:** if deterministic deallocation is needed, switch to confined/shared and close at the right time.
11. **Memory tests:** check peak/steady-state under load, OS/container limits, and retained references.
12. **Documentation:** clearly state why the application accepts GC-managed native cleanup instead of an explicit lifetime.

## 17. Official Documentation

- Oracle Java SE 22 — [`Arena`, automatic arena, GC reachability, and unspecified deallocation timing](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html)
- Oracle Java SE 22 — [`MemorySegment`, spatial/temporal bounds, and scope](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html)
- Oracle Java SE 22 — [`java.lang.foreign` package overview](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html)
- OpenJDK — [JEP 454: Foreign Function & Memory API, finalized in JDK 22](https://openjdk.org/jeps/454)
- Dev.java — [Access Off-Heap or On-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/)
- Oracle Java SE 22 — [`System.gc()`](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/System.html)

**Conclusion:** `Arena.ofAuto()` allocates native memory with a **GC-managed lifetime but non-deterministic reclamation timing**. One must distinguish **eligible for reclamation** from **already freed**, manage the reachability of the entire arena/segments, and understand that `close()` is not supported. For large resources or requirements to release at a clear point in time, use **`Arena.ofConfined()` or `Arena.ofShared()`** and manage work completion before closing.