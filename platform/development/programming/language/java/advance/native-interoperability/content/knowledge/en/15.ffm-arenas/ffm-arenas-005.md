# Arena.global and Unbounded-Lifetime Memory

## 1. The problem: how long does native memory live?

In Java's **Foreign Function & Memory API (FFM)**, `MemorySegment` represents a region of memory (which may reside outside the Java heap), and `Arena` is the mechanism for allocating and defining the **lifetime** of native memory regions allocated through it. When working with native libraries, choosing the wrong arena can cause two opposite kinds of bugs:

- **Deallocating too early:** native code still holds a pointer to the data, but the `Arena` has already been closed. Java accesses to the segment will fail lifetime checks; native C code holding the stale pointer may use invalid memory.
- **Holding memory too long:** each request creates a native buffer with no way to reclaim it until the process exits, causing off-heap memory growth even after Java objects or Java variables are no longer referenced.

`Arena.global()` sits at the second extreme: it provides a **global arena with an unbounded lifetime**. Native memory regions allocated by this arena **are not reclaimed by the arena throughout the JVM's lifetime**, and the corresponding `MemorySegment`s are permitted to be accessed from **any Java thread**.

Therefore, it is necessary to understand the phrase “memory with an unbounded lifetime” accurately: it is **the lifetime contract of the arena scope**, not a guarantee of infinite RAM, absence of allocation failures, absence of access constraints, nor **automatic thread safety for the data being read/written**.

This article uses the **official FFM API of JDK 22+ (JEP 454)** to demonstrate `Arena.global()`. In **JDK 21 (JEP 442)**, FFM was still a preview feature and required `--enable-preview`; some allocation overloads had different names, so do not copy JDK 22 examples verbatim into JDK 21.

## 2. The four types of Arena and the role of Arena.global

FFM has four important arena types. They differ in **lifetime**, **who deallocates**, **whether they can be closed**, and **cross-thread access permissions**.

| Arena | Native memory lifetime | Can `close()`? | Threads allowed to access segment | Reclamation mechanism |
|---|---|---|---|---|
| `Arena.ofConfined()` | Bounded, decided by the developer | **Yes**, from the owning thread | Owner thread only | Freed when the arena is successfully closed |
| `Arena.ofShared()` | Bounded, decided by the developer | **Yes**, from an appropriate thread | Multiple threads | Freed when the arena is successfully closed |
| `Arena.ofAuto()` | Bounded, but reclamation timing is non-deterministic | **No** | Multiple threads | Managed by the JVM/GC, when the arena and its segments are no longer reachable |
| **`Arena.global()`** | **Unbounded** | **No** | **Multiple threads** | **Not reclaimed by the arena** during the JVM process lifetime |

Two criteria should be kept separate:

1. **Lifetime:** does the memory automatically become invalid? Can reclamation be requested via `close()`?
2. **Thread access:** does the segment belong to a specific thread or can it be accessed from multiple threads?

`Arena.global()` has both an **unbounded lifetime** and **thread-unrestricted** access. `Arena.ofAuto()` also allows multiple threads to access it, but does **not** have an infinite lifetime: its native memory becomes eligible for JVM reclamation after it is no longer reachable and GC decides to collect it.

**Do not use `global` just because an application is multithreaded.** When data needs to be shared among threads **but still needs to be freed at an explicit point**, `Arena.ofShared()` is usually the better choice.

### 2.1. Visualizing with a lifetime diagram

~~~text
JVM process time ------------------------------------------------------>

Arena.ofConfined():
    create arena -> allocate -> use (owner thread) -> close -> memory freed
                                                          ^
                                                 segment is no longer valid

Arena.ofShared():
    create arena -> allocate -> use across multiple threads -> close -> memory freed
                                                        (requires thread coordination)

Arena.ofAuto():
    create arena -> allocate -> still reachable -> no longer reachable
                                             -> GC decides to reclaim (timing uncertain)

Arena.global():
    Arena.global() -> allocate ---------------------------> ...
                     memory always belongs to the global scope, no close/free by the arena
                     memory is reclaimed by the OS when the process exits
~~~

The diagram is a **conceptual model**, not a guarantee that GC will reclaim `ofAuto` the moment a Java variable is assigned `null`. With `global`, even when the Java wrapper is no longer referenced, the native allocation is still not freed by the arena mechanism.

## 3. The Arena.global API and the meaning of global scope

In Java SE 22, the API provides the factory method:

~~~java
Arena global = Arena.global();
~~~

This is a **snippet**; `import java.lang.foreign.Arena;` is required when used in an actual class. The Java documentation describes the global arena as an arena with a **global scope** and an **unbounded lifetime**.

Three core properties:

- **`global.scope().isAlive()` always indicates the scope is alive**: the global arena has no valid close event that invalidates the scope.
- **Segments returned by `global.allocate(...)` are bound to the global scope**: the native memory backing them **is not automatically deallocated by the arena**.
- **Segments can be used across multiple Java threads** under FFM's access-checking rules: there is no owner-thread restriction like a confined arena.

### 3.1. Allocating through the global arena

JDK 22 example:

~~~java
MemorySegment bytes = Arena.global().allocate(64);
MemorySegment ints = Arena.global().allocateFrom(
        ValueLayout.JAVA_INT, 10, 20, 30
);
~~~

This is a **snippet**, not a standalone program; `MemorySegment` and `ValueLayout` must be imported. Depending on the overload, `allocate` takes a byte count or a `MemoryLayout`, while `allocateFrom` creates a new region and **copies initial Java data** into it.

The `Arena.global()` specification states that segments it allocates are **zero-initialized**. If no other value has been written, reading a valid location with an appropriate layout yields the value corresponding to zero bytes. However, **zero-initialized does not mean every bit-pattern interpretation is business-valid**: a C struct or pointer has its own rules.

### 3.2. The word “global” is not a Java global variable

There are two different concepts:

~~~java
// This is a JAVA local variable referencing a segment with global scope.
MemorySegment data = Arena.global().allocate(128);
~~~

- The Java variable `data` may only live within a single method. When it goes out of scope or becomes unreachable, the **Java wrapper** can be handled by GC.
- **The backing off-heap memory** allocated by `Arena.global()` is still **not freed by the arena**. The disappearance of the Java reference does not turn a global allocation into an automatic allocation.
- Declaring `static MemorySegment data` is also not what creates a global scope: you can have a `static` field holding a segment from `Arena.ofShared()`; that arena can still be closed. **The scope is determined by the arena, not by the Java `static` keyword.**

This is the fundamental difference between **object reachability on the Java heap** and the **lifetime of native memory**.

## 4. Complete Java 22 example: a long-lived global segment, readable from another thread and non-closeable

Create the file **`GlobalArenaDemo.java`** with the code below. The program uses only the *foreign memory* part of FFM and **does not call any native C functions**, so neither a C compiler nor native-access permission flags are needed.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class GlobalArenaDemo {
    public static void main(String[] args) throws InterruptedException {
        Arena global = Arena.global();

        // Allocate and copy three ints from Java into native memory.
        MemorySegment values = global.allocateFrom(
                ValueLayout.JAVA_INT, 10, 20, 30
        );

        // Allocate an int region without initial source data.
        // Memory allocated by an Arena is zero-initialized.
        MemorySegment zero = global.allocate(ValueLayout.JAVA_INT);

        System.out.println("bytes = " + values.byteSize());
        System.out.println("alive = " + values.scope().isAlive());
        System.out.println("zero = " + zero.get(ValueLayout.JAVA_INT, 0));
        System.out.println("main = " + values.getAtIndex(
                ValueLayout.JAVA_INT, 0
        ));

        // Worker only READS while main waits on join: no concurrent writes.
        Thread reader = new Thread(() -> {
            int number = values.getAtIndex(ValueLayout.JAVA_INT, 1);
            System.out.println("other thread = " + number);
        });
        reader.start();
        reader.join();

        try {
            global.close();
        } catch (UnsupportedOperationException ex) {
            System.out.println("close = unsupported");
        }

        // A failed close attempt does not invalidate the scope.
        System.out.println("alive after close = "
                + values.scope().isAlive());

        values.setAtIndex(ValueLayout.JAVA_INT, 2, 99);
        System.out.println("last = " + values.getAtIndex(
                ValueLayout.JAVA_INT, 2
        ));
    }
}
~~~

### 4.1. Compiling and running

Requires **JDK 22 or later** with finalized FFM. On JDK 22:

~~~bash
java -version
javac -version
javac --release 22 GlobalArenaDemo.java
java GlobalArenaDemo
~~~

In PowerShell, Command Prompt, bash, and zsh, the `javac`/`java` commands above have the same form if they are already in `PATH`. **Do not add `--enable-preview`** just to run FFM on JDK 22. In this example, there is no `Linker.downcallHandle` or `SymbolLookup.libraryLookup`, so **`--enable-native-access` is also unnecessary** for ordinary allocate/get/set operations.

**Exact stdout of the program:**

~~~text
bytes = 12
alive = true
zero = 0
main = 10
other thread = 20
close = unsupported
alive after close = true
last = 99
~~~

Why the output has a deterministic order: main prints the first four lines, then waits for `reader.join()` to finish, and only then attempts `close()` and writes the final value. The other thread **only reads**; the program does not attempt to demonstrate unsynchronized concurrent read/write behavior.

### 4.2. Line-by-line explanation

- `allocateFrom(JAVA_INT, 10, 20, 30)` creates three contiguous 32-bit `int` elements; the segment length is **3 × 4 = 12 bytes**.
- `allocate(JAVA_INT)` allocates enough memory for one `int` and guarantees the new region is zero-initialized, so reading with `get(JAVA_INT, 0)` returns 0.
- `values.scope().isAlive()` returns `true` because the scope of `Arena.global()` has no ending lifetime.
- Another thread reading the value `20` is valid with respect to **scope access permissions**; there is no `WrongThreadException` merely because another thread accesses a global segment.
- `global.close()` throws **`UnsupportedOperationException`** per the specification; the program catches that exception and prints `close = unsupported`.
- After the failed close, the scope remains `alive`, and writing the third element to `99` is valid within the segment's bounds.

**What must not be inferred from stdout:** the program **does not prove that the allocations will be freed when `values`/`zero` go out of scope**. The specification states the opposite for backing memory allocated by the global arena: it is not deallocated through the arena. When the process exits, the OS typically reclaims process resources; that is **not** an `Arena.close()` call or a programmatic GC collection.

## 5. Why can't Arena.global be closed?

`Arena` extends `AutoCloseable`, but **not every arena supports closing**. For the global arena, Java SE 22 specifies:

~~~java
Arena global = Arena.global();
global.close(); // Throws UnsupportedOperationException.
~~~

This is a **deliberately failing snippet**, not an example of proper resource usage. Do not write:

~~~java
// WRONG: try-with-resources will call close() and throw an exception.
try (Arena global = Arena.global()) {
    MemorySegment data = global.allocate(64);
}
~~~

This is a **WRONG example, not to be used as a runnable guide**. At the end of the `try`, Java automatically calls `global.close()` and receives `UnsupportedOperationException`. Some code might run all the way to the end of the block before failing, making the root cause easy to misunderstand.

**The right way** when an unbounded lifetime is intentionally desired:

~~~java
Arena global = Arena.global();
MemorySegment data = global.allocate(64);
// Do not call global.close() and do not put global in try-with-resources.
~~~

If the application's requirement is “allocate and reliably return the memory when done,” do not try to force the global arena to close. **Choose a different arena from the start**: `ofConfined` or `ofShared` depending on thread needs.

### 5.1. Why are both Global and Auto non-closeable yet very different?

`Arena.ofAuto()` also throws `UnsupportedOperationException` if `close()` is called. However:

- **Auto:** backing native memory *may be deallocated* when the runtime/GC determines the arena and its segments are no longer reachable. **There is no deterministic reclamation time**.
- **Global:** backing native memory allocated by `global` **is never deallocated by the arena**; the disappearance of Java references does not make the memory an automatic allocation.

Therefore, “cannot be closed” **does not mean** “lives forever.” You must check the exact arena type.

## 6. Java GC and native memory: two parallel lives

Two kinds of resources must be distinguished:

| Component | What can the JVM/GC manage? | Conclusion |
|---|---|---|
| Java variable of type `MemorySegment` | The wrapper object can become unreachable and be processed by GC | Does not determine that the backing global allocation will be returned |
| Native backing memory of `Arena.global().allocate(...)` | Per the global arena spec, **not deallocated** during the process lifetime | Destroying the Java wrapper does not free the native bytes |
| Native backing memory of `Arena.ofAuto()` | GC may trigger deallocation after it is no longer reachable | No deterministic timing |
| Native backing memory of `Arena.ofConfined()/ofShared()` | Freed via a successful `close()` | Can be controlled deterministically |
| Memory from C `malloc` | Subject to the native library's ownership/release rules | Cannot be treated as a global-arena allocation just because a Java pointer references it |

A very dangerous misconception: “I just need to set `segment = null`, and when GC runs, the global arena will free the off-heap memory.” This is **false**. `Arena.global` is not designed with the reclamation mechanism of `ofAuto`.

### 6.1. Memory growth bug despite a flat heap chart

Suppose a service handles requests:

~~~java
// WRONG lifecycle-management example: do not run in a real service.
public static void handleRequest() {
    MemorySegment temp = Arena.global().allocate(1024 * 1024);
    // Process request...
}
~~~

Each call can retain about **1 MiB of native backing memory** for the rest of the JVM process's life. If called 1,000 times, the total requested size is roughly **1,000 MiB**, even though the Java variable `temp` goes out of scope after every call. **Do not run a large allocation loop just to “observe a memory leak”**; such an experiment can exhaust the process's native memory.

A heap profiler that only measures the Java heap may not directly reflect this native memory usage. When investigating, also examine process-level memory usage, native memory metrics, and relevant error logs. Do not assume all native memory growth comes from `Arena.global`; C libraries, direct buffers, JVM subsystems, and mapped files also consume native resources.

### 6.2. Memory responsibility does not vanish at the FFM boundary

If a C library allocates memory with `malloc` or its own allocator, it usually has a corresponding release function. Even if Java receives that address as a `MemorySegment` with global scope, **you cannot conclude that FFM owns that memory** or that the memory will never be freed by C code.

Similarly, never call C `free` directly on an address allocated by `Arena.global().allocate(...)` to “manually free” it unless an API contract permits it. Doing so can lead to **use-after-free**, freeing with the wrong allocator, or an inconsistent JVM state. The Arena API does not provide an individual deallocation operation for global allocations.

**Global scope describes Java segment checking boundaries; memory ownership must follow the allocation source and the native library's contract.**

## 7. Allowing multithreaded access does not mean data is automatically thread-safe

Java SE 22 guarantees that segments allocated by `Arena.global()` **can be accessed from any thread**. This means:

- No “owner thread only” restriction like `Arena.ofConfined()` is applied.
- No valid `close` operation can invalidate the entire global scope across threads.
- **However**, two threads reading/writing the same memory location without synchronization can still create a **data race** and violate application correctness.

Distinguish between:

~~~text
Allowed by scope:
    Thread A reads index 0
    Thread B reads index 1
    -> can be performed on a global segment, not blocked by owner-thread checks

NOT automatically synchronized:
    Thread A writes index 0
    Thread B writes index 0 at the same time
    -> no ordering/data-coordination guarantees just because the arena is global
~~~

Even when a segment is always alive and has enough bytes, you still need to define **memory consistency** for accesses to the same memory region. You can use appropriate Java synchronization, `VarHandle` with suitable access modes when alignment is ensured, or design data as immutable/read-only after a safely published initialization step.

### 7.1. Safe read-only sharing pattern

In the `GlobalArenaDemo` example, the main thread initializes all values **before** calling `reader.start()`, the worker only reads, and main waits via `reader.join()`. There are no competing reads/writes on the same location.

The key point: the program uses `Arena.global()` to **permit** cross-thread access, while also relying on **start/join ordering and no concurrent writes** to preserve data semantics.

If an application has multiple workers updating the same native region, a concrete synchronization design is required. Simply switching from `Arena.ofConfined()` to `Arena.global()` will not solve data races on its own.

### 7.2. Global does not lift size or alignment bounds

FFM still performs spatial checks:

~~~java
MemorySegment s = Arena.global().allocate(8);
s.get(ValueLayout.JAVA_INT, 8); // Error: needs 4 bytes starting at offset 8.
~~~

This is a **deliberately failing snippet**, not valid runnable code. The segment has valid byte offsets from 0 to 7, whereas reading an `int` at offset 8 requires accessing bytes 8 through 11, which is out of bounds. The result is **`IndexOutOfBoundsException`**.

Layouts also have **alignment requirements**; an address with enough bytes that is not aligned according to the layout is still invalid for operations requiring alignment. `Arena.global()` does not bypass these checks.

## 8. Comparison with a second program: how does a closed confined arena differ from a global arena?

Create the file **`ArenaLifetimeComparison.java`** to observe a short-lived memory segment becoming invalid while the global one remains alive. This program also uses **JDK 22+**, with no native C library needed.

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ArenaLifetimeComparison {
    public static void main(String[] args) {
        MemorySegment local;

        try (Arena confined = Arena.ofConfined()) {
            local = confined.allocateFrom(ValueLayout.JAVA_INT, 7);
            System.out.println("confined inside = "
                    + local.get(ValueLayout.JAVA_INT, 0));
        }

        try {
            local.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("confined should be closed");
        } catch (IllegalStateException ex) {
            System.out.println("confined after close = invalid");
        }

        MemorySegment global = Arena.global().allocateFrom(
                ValueLayout.JAVA_INT, 7
        );
        System.out.println("global value = "
                + global.get(ValueLayout.JAVA_INT, 0));
        System.out.println("global alive = "
                + global.scope().isAlive());
    }
}
~~~

Run:

~~~bash
javac --release 22 ArenaLifetimeComparison.java
java ArenaLifetimeComparison
~~~

**Exact stdout:**

~~~text
confined inside = 7
confined after close = invalid
global value = 7
global alive = true
~~~

Why:

1. Inside `try (Arena confined = Arena.ofConfined())`, the segment `local` is alive and the value 7 can be read.
2. Exiting the block, `confined.close()` is called automatically, the native memory is freed, and the segment `local` becomes invalid.
3. Attempting to read `local` after close throws `IllegalStateException`, which the program catches to print the second line.
4. The segment allocated by `Arena.global()` does not depend on the confined scope; it can still be read as 7 and has an alive scope.

This comparison demonstrates the **lifetime difference**, not a measurement of how much memory the OS has freed. Do not dereference a raw pointer from C after its arena has closed just to “test” the error: native use-after-free can crash the JVM rather than throwing a clean Java exception.

## 9. When is Arena.global a reasonable choice?

`Arena.global()` is **not a bad API**; it has a clear role when *the design intentionally* requires native memory to live until the end of the JVM's lifetime.

Some situations may be appropriate, provided the size is small and controlled:

- **Long-lived shared immutable data**: for example, a very small native configuration table, initialized once and used continuously until the process exits.
- **Pointers/callbacks that must live for the entire program**: in some FFM upcall designs, stubs/callback addresses are held with an appropriate scope; if they truly must live as long as the process and their count is strictly bounded, the global arena can make sense. Having native code store and invoke callbacks also requires correct ABI, thread, and loader lifecycles.
- **Process-lifetime structures**: a native library loaded once and keeping fixed structures, with no requirement to tear down/reinitialize within the same JVM.

Even then, always document in the design: **who decides allocations, the maximum number of allocations, what total size limit applies, and why non-reclamation is acceptable**. “Data is used by multiple threads” is **not enough** reason to choose global; `ofShared()` also supports multiple threads and **can be closed**.

### 9.1. Cases where global should not be used

| Need | Usually more suitable Arena | Reason |
|---|---|---|
| Single native call, data unneeded afterward | `Arena.ofConfined()` | Deterministic cleanup immediately after the call |
| A batch running in one thread | `Arena.ofConfined()` | Simple ownership, minimizes lifecycle bugs |
| Multiple workers share a buffer, then the batch ends | `Arena.ofShared()` | Cross-thread access and close on completion |
| Memory can be cleaned up when unreferenced, latency acceptable | `Arena.ofAuto()` | GC can reclaim native backing memory |
| Cache that can be evicted or scales with traffic | `ofShared()`/`ofConfined()` with clear owner | Avoids retaining every allocation until JVM exit |
| Temporary request, message, query, or transaction | `Arena.ofConfined()` or properly scoped shared | Request-scoped memory must have a deallocation boundary |

These are guidelines; the choice also depends on ownership, concurrency, and native library behavior. One arena can hold **multiple allocations** to be cleaned up together as a group when the scope ends.

## 10. Alternative design: shared memory that is still freed

If the real goal is “multiple threads share a buffer, but it must be freed when finished,” use **`Arena.ofShared()`** with an explicit resource-closing flow.

Complete **JDK 22 example** — file `SharedArenaDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class SharedArenaDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena shared = Arena.ofShared()) {
            MemorySegment data = shared.allocateFrom(
                    ValueLayout.JAVA_INT, 3, 5, 7
            );

            Thread reader = new Thread(() -> {
                System.out.println("worker = " +
                        data.getAtIndex(ValueLayout.JAVA_INT, 1));
            });
            reader.start();
            reader.join();

            System.out.println("main = " +
                    data.getAtIndex(ValueLayout.JAVA_INT, 2));
        } // shared.close(): cleans up native memory when no thread is using it.
        System.out.println("shared closed");
    }
}
~~~

Run:

~~~bash
javac --release 22 SharedArenaDemo.java
java SharedArenaDemo
~~~

**Stdout:**

~~~text
worker = 5
main = 7
shared closed
~~~

`reader.join()` ensures the worker has finished reading before the block exits and the arena is closed. Thus threads can use the segment while it is alive, **yet the application still has a deterministic deallocation point**.

**Do not close a shared arena while another thread is using it.** FFM's temporal safety checks and close rules may fail if closed while an access is in progress; furthermore, native pointers held by C code require separate coordination so they do not become dangling pointers. `Arena.ofShared()` does not automatically synchronize data and does not automatically wait for all native callbacks to finish.

## 11. Crucial misconceptions about global scope

### 11.1. “Unbounded lifetime” does not mean unlimited memory capacity

You can request a very large allocation, but the JVM/OS may not have enough native memory. When allocation fails, the application may receive **`OutOfMemoryError`**. `Arena.global()` does not provide infinite RAM or the ability to shrink memory automatically when unused.

A process's native resources are also constrained by virtual address space, container quotas, OS configuration, native dependencies, and physical memory. Production designs must **budget the number of allocated bytes** and must not allocate per-request into the global arena indefinitely.

### 11.2. “Any thread may access” does not mean “operations are atomic”

Ordinary `get` and `set` operations do not become atomic/volatile just because they are in the global arena. If a shared counter is needed, design synchronization or a `VarHandle` with the right layout and memory ordering.

Safety for **lifetime** and **races** are two separate axes:

~~~text
Arena.global() guarantees:
    Global scope is always alive
    Segment can be accessed from multiple threads (no owner restriction)

Arena.global() does NOT guarantee:
    Concurrent reads/writes have the desired ordering
    All field updates are atomic
    Native code respects segment bounds
    C pointers from external libraries remain valid
    Memory is always available for allocation
~~~

### 11.3. “Global scope always alive” does not mean external pointers are always valid

A `MemorySegment` with an unbounded scope can represent **an address managed by a native library**, such as a pointer returned from C. If the library has freed that memory, having a Java wrapper with a global scope **does not bring the memory back to life**.

FFM checks cannot automatically know the full ownership of `malloc`/`free` outside the JVM. Do not reinterpret or expand unfamiliar addresses with `reinterpret` without knowing their size, lifetime, and owner. Dangerous operations may be restricted and risk memory corruption.

### 11.4. “Cannot be closed” is different from “needs no management”

Not having `close()` makes management responsibility **greater**, not smaller: you must cap the number of allocations, create them only at startup if appropriate, and evaluate reusing data structures.

If hot reload, redeploy, recreating resources within the same JVM, or releasing on user logout is required, a global arena is very likely unsuitable. You need a bounded arena (confined/shared) with ownership and lifecycle tied to the component.

### 11.5. Global arena does not automatically create inter-process shared memory

“Global” in this API means **JVM process scope**, not a shared-memory segment between processes. Two Java programs running in two different JVMs cannot share an address allocated via `Arena.global()` just because it has the same API name.

For IPC/shared memory between processes, you must use a separate OS/native library mechanism and manage synchronization as well as access permissions; the `Arena.global()` API does not provide that on its own.

## 12. Common errors and how to handle them

| Error or misconception | Consequence | How to handle |
|---|---|---|
| Putting `Arena.global()` in try-with-resources | `close()` at the end of the block throws `UnsupportedOperationException` | Do not close global; use confined/shared if you want to close |
| Thinking `segment = null` frees a global native allocation | Native memory stays held by the arena for the JVM's lifetime | Choose `ofAuto` or a bounded arena |
| Allocating buffers for all requests with global | Off-heap memory footprint grows steadily | Use a request-scoped arena, set a memory budget |
| Choosing global just for multithreading | Unnecessary unbounded lifetime | Consider closeable `Arena.ofShared()` |
| Two threads writing the same offset without synchronization | Race, lost updates, or inconsistent data | Synchronization, immutable data, VarHandle with proper semantics |
| Using `MemorySegment` after closing confined/shared | `IllegalStateException` | Restrict accesses within the arena lifetime |
| Reading past `segment.byteSize()` | `IndexOutOfBoundsException` | Calculate offsets in bytes and layouts |
| Using wrong alignment | `IllegalArgumentException`/API alignment error | Allocate by `MemoryLayout` and check byte alignment |
| Calling C `free` directly on a global allocation | Wrong-allocator free, risk of use-after-free | Do not manually free allocations managed by the global arena |
| Assigning global scope to an already-freed C pointer | Scope check cannot detect true ownership/liveness | Track the native allocator's contract accurately |
| Thinking a stable Java heap means stable native memory | Misses off-heap memory growth | Monitor process/native memory separately |
| Copying `allocateFrom` into JDK 21 preview | API differs across versions, may not compile | Use JDK 22+ for the example or adapt to the JDK 21 API |
| Using JDK 17 to run a class with final `java.lang.foreign` | Final FFM does not exist in Java 17 | Run with JDK 22+ |
| Using `--enable-native-access` unnecessarily for all FFM programs | Overly broad native-permission configuration | Grant permission only when using restricted APIs |

During debugging, separate **lifetime** issues (closed arena), **spatial bounds** (offset/layout), **thread confinement**, and **resource exhaustion**. Each category has a different fix; switching everything to `Arena.global()` just to “make it run” often masks a flawed design.

## 13. JDK 21 preview and JDK 22 final: syntax notes

`Arena.global()` already appeared in **JDK 21**'s FFM preview, but all of `java.lang.foreign` in that version was **preview** (JEP 442). With JDK 21, you must compile/run with the flags:

~~~bash
javac --enable-preview --release 21 MyFfm21Class.java
java --enable-preview MyFfm21Class
~~~

These two commands are **templates**, not commands to run a file included in this article; replace `MyFfm21Class` with your project's actual file/class name using the JDK 21 preview API.

JDK 22 finalized FFM (JEP 454), so the programs `GlobalArenaDemo`, `ArenaLifetimeComparison`, and `SharedArenaDemo` in this article run without `--enable-preview`. However, **do not** expect `arena.allocateFrom(...)` to exist on JDK 21 as it does in JDK 22. In JDK 21, some initialization methods were named `allocateArray`, `allocateUtf8String`, `allocate(ValueLayout, value)`.

For this article, the semantics that **the global arena has an unbounded lifetime and cannot be closed** are the core point in both versions. Differences in API status and allocation methods do not make global “self-cleaning” on any JDK.

**Warning about the native access flag:** the examples here that only allocate/read/write memory with FFM **do not invoke restricted native downcalls**. When a real program uses `Linker.downcallHandle`, `SymbolLookup.libraryLookup`, upcall stubs, or other restricted operations, you must check the `--enable-native-access` policy for that JDK/runtime. “Final” does not mean all foreign function calls require no permission.

## 14. Design checklist when considering Arena.global

Before using the global arena in production, verify at least:

1. **Lifetime:** must the data truly live until the JVM exits? If it is only needed until the end of a request/batch, choose a bounded arena.
2. **Allocation count:** is the number of allocations guaranteed to be finite, not scaling unboundedly with traffic?
3. **Byte limit:** has the maximum total process-lifetime memory been calculated and monitored?
4. **Ownership:** is the native region allocated by the FFM arena or by a C library? Who has the authority to free it?
5. **Passing pointers to native code:** could C hold the pointer longer than the data's valid lifetime?
6. **Thread safety:** do threads only read or also write? Is there a synchronization mechanism with proper memory ordering?
7. **Reload/teardown capability:** will the component ever have to be freed before the JVM exits? If so, global is unsuitable.
8. **Failure conditions:** if native memory allocation fails, does the system degrade/fail-fast appropriately?
9. **Bounds and alignment:** have byteSize, offset, and layout calculations according to the C ABI been verified?
10. **Operational observability:** which metrics/native memory logs can detect off-heap memory growth?
11. **Version:** JDK 22+ uses final FFM and `allocateFrom`; JDK 21 preview uses a different set of APIs/flags.
12. **Internal documentation:** is it clearly documented why an allocation is never returned during the JVM lifetime?

If you cannot answer the question “**why does this memory not need to be returned before the JVM exits?**”, the sensible default choice is usually an arena with a **bounded** lifetime rather than `Arena.global()`.

## 15. Questions and exercises

1. How does `Arena.global()` differ from `Arena.ofAuto()` if neither can be closed?
2. What does `Arena.global().scope().isAlive()` return after a failed `close()` call? Why?
3. When a Java method creates `MemorySegment s = Arena.global().allocate(1024)` and then returns, is the native memory freed because `s` goes out of scope?
4. In what cases should `Arena.ofShared()` be used instead of global even with multiple worker threads?
5. Why does allowing access to a global segment from any thread not automatically make `get`/`set` operations atomic?
6. What are the initial byte values of `Arena.global().allocate(ValueLayout.JAVA_INT)` and why?
7. Why is `try (Arena a = Arena.global())` an inappropriate pattern?
8. If a C buffer is needed only for a single downcall, which arena type is the simplest choice with easy cleanup?
9. Does `MemorySegment.ofAddress` with a global scope make an already-`free`d C pointer safe?
10. A service allocates 1 MiB using global for each request. After 1,000 requests, what resource issue should be examined?
11. When can a small process-lifetime allocation be a reasonable design choice rather than a bug?
12. Why must the Java heap and native memory be analyzed separately when profiling an FFM application's memory?
13. If a segment has a byteSize of 8, what error will reading `JAVA_INT` at offset 8 cause?
14. Can Java 22 example code using `allocateFrom` be copied verbatim to JDK 21? Why?

**Conclusion:** `Arena.global()` allocates native memory with an **unbounded lifetime**, a scope that is always alive, and segments accessible by multiple threads. In return, **it cannot be `close()`d and has no arena-driven deallocation**, even when the Java wrapper is no longer reachable. It is the right tool for **small, finite, intentional** process-lifetime data, not the default choice for temporary buffers or traffic-scaling caches. For finite-lived resources, choose `Arena.ofConfined()`, `Arena.ofShared()`, or `Arena.ofAuto()` according to lifecycle-control and threading needs.

### Official documentation

- [Java SE 22 — Arena API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): global scope, unbounded lifetime, `close()`, and arena comparison table.
- [Java SE 22 — MemorySegment API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): memory scope, bounds, alignment, thread access, scope.
- [Java SE 22 — SegmentAllocator API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/SegmentAllocator.html): `allocate`, `allocateFrom`, and overloads.
- [Java SE 22 — FFM API, JEP 454](https://openjdk.org/jeps/454): finalized status of FFM.
- [Java SE 21 — Arena API preview](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/foreign/Arena.html): global arena in FFM preview.
- [Dev.java — Access Off-Heap or On-Heap Memory with Memory Segments](https://dev.java/learn/api/io/ffm/access-memory/): practical guide to the four arena types and memory lifetime.
