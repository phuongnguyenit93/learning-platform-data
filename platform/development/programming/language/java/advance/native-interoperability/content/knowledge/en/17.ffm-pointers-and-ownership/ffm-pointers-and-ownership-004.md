# reinterpret changes visible bounds without verifying the actual memory region

## 1. Core problem: a declared size is not a verified size

In the **Foreign Function & Memory API (FFM)**, a `MemorySegment` is how Java views a memory region. Every segment has at least three important characteristics: **starting address**, **visible size** (spatial bounds, in bytes), and **scope/lifetime** (temporal bounds). A segment is also subject to thread-access rules and can be marked read-only.

`MemorySegment.reinterpret(...)` is a group of **restricted** operations that allow creating a new segment representing the **same memory address** but with a different visible size, or a different scope. The danger lies not in the syntax, but in the **assertion made by the caller**: Java can treat the new view as 100 bytes long even though the actual native memory region was only allocated 10 bytes. `reinterpret` **does not ask the OS, allocator, or native library** to verify that assumption.

Keep this in mind immediately:

> **`reinterpret(100)` does not allocate 100 bytes, does not extend the C memory region, does not copy data, and does not prove that 100 valid bytes exist. It only creates a view carrying "100 bytes" metadata for the same address.**

If subsequent code reads/writes in the part of the view that exceeds the actual allocation, checks **against the declared bounds** may let it pass, but the real machine access is **out-of-bounds**, which can crash the JVM or silently cause memory corruption. Java does not guarantee that an `IndexOutOfBoundsException` can save this case.

This article focuses on **JDK 22+**, when FFM became a standard API under JEP 454; the JDK 21 version is FFM preview under JEP 442, so it requires `--enable-preview` and the API must be cross-checked against the exact version.

## 2. Three types of bounds to distinguish

### 2.1. Spatial bounds: the size that Java sees

A segment has:

~~~java
long visibleBytes = segment.byteSize();
~~~

This is a **snippet** inside a method that already has a valid `segment` variable.

When reading a 4-byte `int` at byte offset 8, the API checks whether the byte range 8–11 lies within the range from 0 to `byteSize() - 1`. Read/write operations such as `get(ValueLayout.JAVA_INT, offset)` perform this check against the **segment passed to the operation**.

For a normal segment created by `Arena.allocate(16)`, Java knows the allocation has at least 16 bytes and can block access at offset 16. However, with `reinterpret(24)`, Java only knows that **the new view declares 24 bytes**; the reinterpret operation itself does not check whether the additional 8 bytes actually exist.

### 2.2. Temporal bounds: how long the memory remains alive

`MemorySegment.scope()` defines the lifetime that Java uses to check validity. A segment bound to `Arena.ofConfined()` is no longer valid after the arena closes. A segment carrying only the global scope may always return `true` for `scope().isAlive()`, even when a **separate native allocator** has already `free`d the memory region at the same address.

**A live scope does not prove that the backing memory is alive.** Java cannot automatically know that a native library has reclaimed or reused a pointer outside FFM's ownership mechanism.

### 2.3. Ownership: who is responsible for allocation/deallocation?

Ownership is not identical to spatial/temporal bounds:

| Component | What does it tell you? | What does it NOT tell you? |
|---|---|---|
| `segment.address()` | Starting address | Allocation size, whether it can be read/written |
| `segment.byteSize()` | **Visible bounds** of the view | Whether the actual allocation is correspondingly large if the view was reinterpreted |
| `segment.scope()` | Temporal bounds/lifetime tracking according to FFM | Whether the native library has called `free` |
| `Arena` used to allocate | May be the owner of the backing memory | Does not own every pointer just because it is attached to that scope |
| `reinterpret(newSize)` | Creates a new view with the same address and scope with the new size | Does not perform `malloc`, `realloc`, `memcpy`, or memory region verification |
| `reinterpret(size, arena, cleanup)` | Creates a view with the same address, requested size/scope, and optional cleanup | Does not automatically turn an unknown pointer into a properly owned allocation |

**Design rule:** you may only widen a view when there is **reliable evidence** that the actual backing allocation contains at least the requested number of bytes, throughout the entire time the view is used.

## 3. Why does Java receive native pointers as zero-length segments?

A C function can return `void *`, `char *`, or `int *`. A pointer value carries an **address**, but usually **does not carry the allocation size** or information on "who must free". For example:

~~~c
/* Illustrative C signature, without implementation. */
void *get_buffer(void);
~~~

From this prototype alone, Java cannot know whether the returned pointer points to one byte, a 4 KiB array, or already-freed memory. Therefore, FFM typically represents pointers received from foreign functions, upcall arguments, or read via `ValueLayout.ADDRESS` as a **zero-length native segment**:

~~~text
Native pointer: 0x1234...  (carries only the address)
        |
        v
FFM MemorySegment [address = 0x1234..., byteSize = 0]
        |
        | get(JAVA_BYTE, 0) -> invalid because the view has 0 bytes
        |
        | reinterpret(16)  [CALLER PROMISES there are at least 16 bytes]
        v
FFM MemorySegment [address = 0x1234..., byteSize = 16]
        |
        | get(JAVA_INT, 12) -> within the view's bounds
        v
But FFM does NOT prove the native allocator allocated at least 16 bytes!
~~~

**Zero-length** is a defensive measure: you cannot arbitrarily dereference an address of unknown length. `reinterpret` is the boundary where the binding author **explicitly takes responsibility** for specifying the valid byte count and lifetime.

### 3.1. A pointer read from memory has global scope

In JDK 22, if you read an address via:

~~~java
MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);
~~~

then `pointer` typically has **`byteSize() == 0`** and **global scope**. That scope is always alive, but this is **default metadata of the address wrapper**, not a guarantee that the actual address resides in an infinitely lived allocation.

Similarly:

~~~java
MemorySegment pointer = MemorySegment.ofAddress(address);
~~~

returns a zero-length native segment wrapping the provided address. `ofAddress` **does not allocate** and does not verify the address. If `address == 0`, it represents a null pointer; never reinterpret it to a positive size and dereference `NULL`.

The two snippets above are **illustrative snippets**; `slot` and `address` must be validly declared in a real program.

## 4. The reinterpret overloads in standard JDK 22 FFM

| API | Size result | Scope result | Notes |
|---|---|---|---|
| `segment.reinterpret(long newSize)` | `newSize` | **Keeps the source segment's scope** | Does not automatically verify backing allocation; does not allocate |
| `segment.reinterpret(Arena arena, Consumer<MemorySegment> cleanup)` | **Keeps `byteSize()`** | Scope of the provided arena | Can register cleanup if authorized to free the native region |
| `segment.reinterpret(long newSize, Arena arena, Consumer<MemorySegment> cleanup)` | `newSize` | Scope of the provided arena | Changes both spatial and temporal bounds; both must be verified |

All three overloads above are **restricted methods** and apply only to **native segments**, not heap segments. If the caller does not have native access permission in the current JVM mode, `IllegalCallerException` may occur; `newSize < 0` causes `IllegalArgumentException` for overloads that take a size.

In JDK 22, code running from the **classpath (unnamed module)** can grant permission explicitly as follows:

~~~bash
javac --release 22 ReinterpretViews.java
java --enable-native-access=ALL-UNNAMED ReinterpretViews
~~~

This is the command for the full example in a later section. If the application is in a **named module**, grant permission to the appropriate module name instead of `ALL-UNNAMED`. Some JDK releases use a warning for restricted operations when permission is not granted; use the explicit flag to avoid depending on the runtime's warning/default mode.

**Changing a view does not mutate the old view.** `MemorySegment` instances are immutable/value-based descriptors; `reinterpret` returns a new reference and does not modify the `byteSize()` of the source variable.

## 5. First example — widening metadata while only accessing actually allocated data

This runnable example on **JDK 22+** intentionally requests a 24-byte view over an actual 16-byte allocation to show **the difference between metadata and backing memory**. The program **never reads or writes** beyond the 16 allocated bytes.

### 5.1. File `ReinterpretViews.java`

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class ReinterpretViews {
    public static void main(String[] args) {
        MemorySegment wider;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment original = arena.allocate(16);

            original.setAtIndex(ValueLayout.JAVA_INT, 0, 10);
            original.setAtIndex(ValueLayout.JAVA_INT, 1, 20);
            original.setAtIndex(ValueLayout.JAVA_INT, 2, 30);
            original.setAtIndex(ValueLayout.JAVA_INT, 3, 40);

            // A 24-byte view over the same actual 16-byte allocation.
            // Only creates the view; does NOT dereference bytes 16..23.
            wider = original.reinterpret(24);

            System.out.println("original bytes = " + original.byteSize());
            System.out.println("wider bytes = " + wider.byteSize());
            System.out.println("same address = "
                    + (original.address() == wider.address()));

            // Reading within the 16 actually allocated bytes is valid.
            System.out.println("valid value = "
                    + wider.getAtIndex(ValueLayout.JAVA_INT, 3));

            // Safe slice within original's range: bytes 8..15.
            MemorySegment slice = original.asSlice(8, 8);
            System.out.println("slice bytes = " + slice.byteSize());
            System.out.println("slice value = "
                    + slice.getAtIndex(ValueLayout.JAVA_INT, 1));

            try {
                original.asSlice(12, 8);
                throw new AssertionError("slice must not exceed 16 bytes");
            } catch (IndexOutOfBoundsException ex) {
                System.out.println("oversized slice = rejected");
            }

            // This only checks the DECLARED view, without dereferencing.
            System.out.println("wider claims room = "
                    + (wider.byteSize() >= 20));
        }

        // reinterpret(24) keeps original's scope, which is the closed arena.
        System.out.println("wider alive after close = "
                + wider.scope().isAlive());

        try {
            wider.get(ValueLayout.JAVA_INT, 0);
            throw new AssertionError("closed scope must not be read");
        } catch (IllegalStateException ex) {
            System.out.println("after close = rejected");
        }
    }
}
~~~

### 5.2. Run commands

Select **JDK 22** (not JDK 21 preview):

~~~bash
java -version
javac -version
javac --release 22 ReinterpretViews.java
java --enable-native-access=ALL-UNNAMED ReinterpretViews
~~~

**Expected stdout:**

~~~text
original bytes = 16
wider bytes = 24
same address = true
valid value = 40
slice bytes = 8
slice value = 40
oversized slice = rejected
wider claims room = true
wider alive after close = false
after close = rejected
~~~

Explanation of each result:

1. `arena.allocate(16)` actually allocates **16 bytes**. Four `setAtIndex(JAVA_INT, i, value)` calls write four 4-byte `int`s at offsets 0, 4, 8, and 12.
2. `original.reinterpret(24)` **does not allocate 8 additional bytes**: `original.byteSize() == 16` while `wider.byteSize() == 24`. Both views start at **the same address**.
3. `wider.getAtIndex(JAVA_INT, 3)` only reads bytes 12..15 **within the original allocation**, so it gets 40.
4. `original.asSlice(8, 8)` creates a sub-view within the known real bounds and contains two `int`s; element index 1 returns 40.
5. `original.asSlice(12, 8)` needs bytes 12..19 and is **rejected** based on the original bound of 16. `asSlice` differs from `reinterpret` because it does not extend bounds past the known range.
6. `wider.byteSize() >= 20` is `true`, but **only means the view declares it has enough bytes for a read at offset 16**. The example **does not perform that read**.
7. When try-with-resources closes `arena`, `wider`'s scope also expires, so reading even at offset 0 is rejected with `IllegalStateException`.

**Never add** `wider.get(ValueLayout.JAVA_INT, 16)` to "see if the JVM throws an error": it lies within the 24-byte metadata but **outside the 16-byte allocation**, risking access to unowned memory. There is no guarantee Java will throw `IndexOutOfBoundsException`; running such a test can cause a crash or read/write unrelated data.

## 6. Diagram of "visible bounds" vs. "actual memory region"

~~~text
Actual backing allocation allocated by arena: 16 bytes

Base address
    |
    v
    +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
    |  0 |  1 |  2 |  3 |  4 |  5 |  6 |  7 |  8 |  9 | 10 | 11 | 12 | 13 | 14 | 15 |
    +----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+----+
    <---------------------- 16 actually allocated bytes ---------------------------->

original.byteSize() = 16
    [------------------------------------------------------------]

wider = original.reinterpret(24)
    [------------------------------------------------------------][................]
                                                                  16..23:
                                                         extra declared metadata;
                                                         NO evidence that the
                                                         actual allocation has more

original.asSlice(8, 8)
                                    [----------------------------]
                                    only 8 valid bytes of original
~~~

Key takeaway: **`byteSize()` is not a region-size detection system via `malloc_usable_size`, OS page map, or C allocator**. The result of `reinterpret` is **a programmer assertion**, not a validation. Even if an out-of-bounds read test "seems to succeed" because adjacent memory happens to be mapped, the code can still be severely wrong.

## 7. Second example — pointer read from memory has 0 bytes, then bound with known bounds

A legitimate use case for `reinterpret` is when Java receives an **address whose origin and size are known**. To avoid depending on a C compiler, this example simulates a native pointer by storing the address of an allocation **allocated by Java itself** into an `ADDRESS` memory slot and reading it back.

### 7.1. File `PointerReinterpret.java` (JDK 22+)

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public class PointerReinterpret {
    public static void main(String[] args) {
        MemorySegment rawPointer;
        MemorySegment scopedView;

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment numbers = arena.allocateFrom(
                    ValueLayout.JAVA_INT, 11, 22, 33, 44
            );

            // A memory slot holding a native pointer.
            MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
            slot.set(ValueLayout.ADDRESS, 0, numbers);

            // Read pointer: only has address, length is unknown.
            rawPointer = slot.get(ValueLayout.ADDRESS, 0);

            System.out.println("raw bytes = " + rawPointer.byteSize());
            System.out.println("raw scope alive = "
                    + rawPointer.scope().isAlive());

            // Exact size taken from the allocation we own.
            // New scope matches the actual arena that allocated it, no free callback.
            scopedView = rawPointer.reinterpret(
                    numbers.byteSize(), arena, null
            );

            System.out.println("scoped bytes = " + scopedView.byteSize());
            System.out.println("scoped value = "
                    + scopedView.getAtIndex(ValueLayout.JAVA_INT, 2));
        }

        System.out.println("scoped alive after close = "
                + scopedView.scope().isAlive());

        // Note: rawPointer still reports scope alive after the arena has closed.
        // This does NOT make the backing memory valid.
        System.out.println("raw scope alive after close = "
                + rawPointer.scope().isAlive());
    }
}
~~~

Run commands:

~~~bash
javac --release 22 PointerReinterpret.java
java --enable-native-access=ALL-UNNAMED PointerReinterpret
~~~

**Expected stdout:**

~~~text
raw bytes = 0
raw scope alive = true
scoped bytes = 16
scoped value = 33
scoped alive after close = false
raw scope alive after close = true
~~~

Mechanism:

- `numbers` is an actual 16-byte allocation, with `arena`'s scope.
- `slot.get(ValueLayout.ADDRESS, 0)` extracts the pointer value into a **zero-length segment** with **global scope**. The global scope **does not prove the backing memory has a global lifetime**.
- `rawPointer.reinterpret(numbers.byteSize(), arena, null)` uses the **reliably known** size from the allocation and binds the view to **the very arena that owns the memory region**. Passing `null` cleanup here is intentional: the arena already frees `numbers`'s allocation when it closes, so no extra `free` step is added.
- `scopedView.getAtIndex(JAVA_INT, 2)` reads bytes 8..11 of the 16-byte backing region, yielding 33.
- After close, `scopedView.scope().isAlive()` is `false`; conversely, the `rawPointer` wrapper still has global scope and reports `true`, even though its address may point to a reclaimed region. **Never dereference `rawPointer` after close.**

This is a **safely grounded** case of `reinterpret` because the size and owner are known from the very allocation we control, not from guessing or relying on the program "not having crashed yet".

### 7.2. Incorrect usage in real applications

The following pattern is **WRONG, do not run**:

~~~java
// A native pointer with unknown backing allocation/lifetime.
MemorySegment untrusted = MemorySegment.ofAddress(unknownAddress);
MemorySegment assumed = untrusted.reinterpret(4096);
// WRONG: immediately read/write 4096 bytes as if they were actually allocated.
// assumed.getAtIndex(ValueLayout.JAVA_INT, 1023);
~~~

This is **pseudocode illustrating an error**; the variable `unknownAddress` is undeclared and the example intentionally omits dereferencing. `4096` is just a guessed number; there is no basis to assume the native allocator allocated a page or that the pointer is still valid.

## 8. Three overloads: distinguishing size change, scope change, and cleanup callback

### 8.1. `reinterpret(long newSize)`

~~~java
MemorySegment resized = original.reinterpret(verifiedByteCount);
~~~

This is a **snippet** with a native segment `original` and `verifiedByteCount` validated outside JNI/FFM according to the native contract. The new view has the **same address and scope**; only `byteSize()` changes.

If `original` belongs to an already-closed arena, reinterpreting does not bring the backing memory back to life. The view is not a new owner. If `newSize` exceeds the actual allocation, FFM checks still rely on the **declared `newSize`** and do not protect the excess portion.

### 8.2. `reinterpret(Arena arena, Consumer<MemorySegment> cleanup)`

~~~java
MemorySegment rebound = pointer.reinterpret(targetArena, null);
~~~

This is a **snippet**; do not use when `targetArena` or `pointer` is undefined. The API keeps the size unchanged and changes **temporal bounds** to the new arena. If the source is a 0-length pointer, the resulting view **is still 0 bytes long**; you cannot read data just because the scope changed.

Changing the scope does not automatically transfer ownership of the backing allocation. If the new arena outlives the actual backing pointer, **use-after-free** can occur even though Java considers the scope still alive.

### 8.3. `reinterpret(long, Arena, Consumer<MemorySegment>)`

~~~java
MemorySegment managedView = pointer.reinterpret(
        verifiedByteCount, ownerArena, cleanupAction
);
~~~

This is a **snippet**: `cleanupAction` should only be passed when there is an **exact deallocation contract**. Changing size/lifetime and registering cleanup can produce a wrapper with an API similar to a Java allocation, but the **binding programmer** themselves must prove:

1. `pointer` points to at least `verifiedByteCount` valid bytes.
2. The pointer remains alive for as long as `ownerArena` exists, without being freed early by the native library.
3. The cleanup action is authorized to free that exact allocation using the **right deallocation function**, **exactly once**.
4. No Java/native consumer uses the pointer after the arena closes and the callback frees it.

If `cleanupAction == null`, the method **does not automatically know** whether to call C `free` or a library function. If the pointer was `malloc`'d in C and has no valid cleanup/release, you can create a **native memory leak**. Conversely, if the pointer was allocated via `Arena.allocate` itself and you also call C `free` in the callback, you can create a **double-free**.

### 8.4. The cleanup action receives a new segment

According to the JDK 22 documentation, the cleanup callback receives a **fresh segment** with **global scope**, the same address, and the corresponding size. It is provided so you can call the right native deallocator during cleanup; do not store or hand that segment out for external use after the backing memory has been reclaimed.

In particular, if you use `Arena.ofAuto()` as the target arena, the cleanup action **must not inadvertently hold a reference** that prevents the arena from becoming unreachable, because then the runtime cannot trigger native memory reclamation. For native code with complex ownership, consider creating a resource-owning wrapper with `AutoCloseable` and a transparent lifecycle.

## 9. Differences between reinterpret, asSlice, and withTargetLayout

| API | Can make view longer than known backing allocation? | Changes owner/lifetime? | How to think about it |
|---|---|---|---|
| `segment.asSlice(offset, bytes)` | **Cannot exceed `byteSize()` of source segment** | Keeps source scope | Narrows/shifts start **within known bounds** |
| `segment.reinterpret(bytes)` | **Can declare longer**, not verified by FFM | Keeps source scope | New assertion about **spatial bounds** |
| `segment.reinterpret(bytes, arena, cleanup)` | **Can declare longer** | Changes scope, optional cleanup | New assertion about **size and lifetime** |
| `ValueLayout.ADDRESS.withTargetLayout(layout)` | Adds view size when reading pointer | Pointer still needs guaranteed real lifetime | Encodes target layout into pointer metadata, also restricted |
| `segment.asReadOnly()` | Does not lengthen view | Keeps scope | Blocks writes through the view, **does not verify size/owner** |

**`asSlice` is the default choice** when you only need a smaller window inside a segment that already has a reliable size. It checks bounds based on `segment.byteSize()` of the **source**. If the source is already an oversized `reinterpret` alias, `asSlice` on the alias also **cannot recover the true size**: it only knows the alias's declared bounds.

`AddressLayout.withTargetLayout(layout)` helps avoid calling `reinterpret` explicitly when a pointer points to data with a fixed layout. However, **the layout is also supplied by the programmer** and this method is **restricted**: a wrong layout can give the pointer view a size/type that does not match actual memory.

`asReadOnly()` is useful when you want to forbid writes through a view, but it **does not prevent other native code from modifying the memory region** and does not verify that the pointer is still alive. A read-only view with a wrong size can still cause the JVM to read outside the allocation.

## 10. What evidence is needed to reinterpret a pointer from a C library?

Not all pointers are equally dangerous. A good native API may return **a pointer and a length**, or return a handle with a size-query method and a clear release function.

C design example:

~~~c
/* Illustrative API; not a complete C program. */
typedef struct Buffer {
    unsigned char *data;
    size_t length;
} Buffer;

/* The C contract must clearly state:
   - data points to at least length bytes if length > 0
   - who owns data
   - when data becomes invalid
   - whether the caller may write or only read
   - which function must be called to free (if caller owns) */
~~~

Merely seeing a `length` field is **not enough** if the library has bugs, the field is controlled by untrusted data, the pointer has already been freed, `length` was rounded incorrectly, or it is the byte count of another view. However, a clear C contract **allows Java code to verify beforehand** instead of guessing.

### 10.1. Checking length before reinterpret

The following Java pattern is **only a snippet** for a situation where `pointer`, `count`, `layout`, and `ownerArena` are already obtained from a reliable native API. Do not assemble the snippet verbatim into a program without defining them according to the C ABI:

~~~java
long maxElements = 1_000_000L;
long count = nativeCount;            // Read from the C API's contract.
long elementBytes = layout.byteSize();

if (count < 0 || count > maxElements) {
    throw new IllegalArgumentException("invalid element count");
}

long byteCount = Math.multiplyExact(count, elementBytes);
if (byteCount > 16L * 1024 * 1024) {
    throw new IllegalArgumentException("buffer exceeds policy limit");
}

if (byteCount > 0 && pointer.address() == 0L) {
    throw new IllegalArgumentException("null pointer with nonzero size");
}

// MANDATORY condition beyond numeric checks:
// The C API guarantees actual backing memory has >= byteCount bytes,
// proper alignment, and lives at least until ownerArena closes.
MemorySegment view = pointer.reinterpret(byteCount, ownerArena, null);
~~~

These steps help control **arithmetic overflow** (`Math.multiplyExact`), resource limits, null pointers, and logical sizes. However, they **do not check with the OS** that the pointer actually owns `byteCount` bytes. The final guarantee still comes from the **ABI/protocol and native owner**.

For `count == 0`, you can use a zero-length view and not dereference it. Do not add one element to the length to handle empty arrays if the C API does not specify a sentinel element.

### 10.2. Knowing that size is in bytes, not element count

A pointer to 10 32-bit `int` values may need **40 bytes**, not 10 bytes. Conversely, if the C API returns a byte count and Java multiplies by `sizeof(int)` again, the result can be inflated 4x.

Separate variable names: `elementCount`, `elementByteSize`, `byteCount`, use `Math.multiplyExact`, and check the maximum limit before creating the view. C `size_t` has an ABI-dependent width, so converting `size_t` to Java `long` requires understanding the architecture; **do not assume** every `size_t` on every platform is 64-bit.

### 10.3. Knowing how long the memory region remains alive

Some native APIs return a pointer that lives only until the **next call**, a pointer to an overwritten internal buffer, or a pointer valid only while a lock/resource handle remains open. In those cases, attaching the pointer to `Arena.global()` or a long-lived `Arena.ofShared()` **does not extend the actual lifetime** of the backing memory.

A pointer freed by a library from another C thread can become invalid between two Java calls even though `view.scope().isAlive() == true`. FFM temporal checks **cannot stop** bugs created by native code outside the arena's knowledge.

### 10.4. Knowing write permissions, alignment, and concurrency

- **Read-only vs writable:** A C API may return `const char *`. FFM does not automatically infer all C `const` qualifiers from a pointer; the binding should expose only a read-only view or a non-writing API.
- **Alignment:** `ValueLayout.JAVA_INT` or a struct layout has alignment constraints. A memory region with enough bytes but a misaligned address can cause `IllegalArgumentException`.
- **Thread safety:** The fact that a view can be shared across multiple threads does not mean the underlying native object is safe to access concurrently.
- **Endianness:** Integer layout may depend on native byte order or a C protocol; `reinterpret` does not convert endianness.
- **Struct layout:** Padding/alignment between fields depends on the ABI; `reinterpret` does not make a struct with the wrong layout correct.

## 11. Three types of mistakes to distinguish: spatial, temporal, and ownership

### 11.1. Spatial bug — declaring more bytes than actually exist

~~~text
C malloc: 10 bytes
Java zero-length pointer
Java reinterpret(100): view allows up to 100 bytes
Java read offset 80: Java checks view and sees OK
Actual native memory: offset 80 is OUTSIDE the allocation

Possible consequences: JVM crash, reading garbage data, corrupting memory,
not necessarily an IndexOutOfBoundsException.
~~~

Remedy: only widen to the **byte count guaranteed by the native API** and verified; do not use "guess a 4096-byte page", "scan to NUL indefinitely", or "trial-read until error" to find the size.

### 11.2. Temporal bug — view is alive while backing was freed

~~~text
Java receives pointer from C
Java reinterpret(size, Arena.global(), null)    // metadata always alive
C library free(pointer)                         // actual backing becomes invalid
Java view.scope().isAlive() == true             // still true
Java get(view)                                  // use-after-free, dangerous
~~~

This is a **warning diagram, not runnable code**. You must constrain the Java view's lifetime to be **no longer than** the actual lifetime; use the proper arena/cleanup and avoid early native frees, including across multiple threads.

### 11.3. Ownership bug — double-free or leak

~~~text
Case A: C malloc -> Java reinterpret(size, arena, null)
        -> arena closes without C free cleanup
        -> C allocation may leak

Case B: Arena.allocate -> Java reinterpret(size, arena, s -> C_free(s))
        -> arena frees the allocation itself
        -> callback also tries to free
        -> double-free / allocator mismatch

Case C: C malloc -> Java reinterpreted view + C free cleanup
        -> native library also frees pointer earlier
        -> double-free / dangling pointer
~~~

All of these are **bug descriptions, not recommended code**. There must be **a single owner** responsible for deallocation and a clear lifecycle endpoint.

## 12. If you don't know the size, what should you do instead of blindly calling reinterpret?

There are alternative approaches:

1. **Redesign the C API** to return `pointer + length`, or accept a Java-allocated buffer with a known capacity. This is the best option when you control the native interface.
2. **Use a C API to query the size** before reading data; if it returns an element count, convert to bytes using overflow-checked multiplication.
3. **Have the native library copy data** into a Java-managed buffer, or copy out to a Java array when you must decouple the lifetime from C resources.
4. **Use a bounded `Arena`** (confined/shared) for memory allocated by Java; when you need a subrange, use only `asSlice` instead of widening with `reinterpret`.
5. **Read fixed-size data per the C contract** using an appropriate `MemoryLayout`; only use `AddressLayout.withTargetLayout` when the target layout is truly certain.
6. **Only pass opaque pointers back to native code** if Java does not need to dereference them; a zero-length pointer is a valid way to pass an address without guessing bytes.
7. **If you only have a pointer of unknown size/lifetime and no reliable documentation**, do not dereference it in Java: there is no safe guess in `reinterpret`.

Some C APIs allow a two-call pattern: the first call queries the length, and the next call fills a Java-allocated buffer. When such an option exists, prefer it because ownership, size, and cleanup are easy to manage.

## 13. NULL pointer and edge cases

`MemorySegment.NULL` represents the null address and has length 0. Do not turn it into a positive-sized view and dereference it. Check `pointer.address() == 0L` before using data with `byteCount > 0`.

Scenario table:

| Scenario | What to do |
|---|---|
| `byteCount == 0` | Keep zero-length segment; do not dereference |
| `pointer == NULL`, `byteCount > 0` | Report contract/input error |
| `byteCount < 0` | Throw `IllegalArgumentException` or validation error before `reinterpret` |
| `count × elementSize` overflows `long` | `Math.multiplyExact` and handle the error, do not wrap |
| `byteCount` exceeds application limit | Reject/stream/chunk, do not reinterpret a huge capacity |
| Pointer points into the middle of an allocation | Calculate **remaining bytes from the pointer's position**, do not use the full allocation size |
| Pointer points to a read-only region | Do not expose a write API |
| Backing is freed by native before deadline | Invalidate the view at the application layer, do not dereference |
| Native pointer held by callback with unknown lifetime | Establish an ownership/lifetime contract before passing to Java |

**Do not use `reinterpret(Long.MAX_VALUE)` to "bypass bounds checks".** It increases the danger surface and allocates no extra memory. Even when `reinterpret` accepts a large non-negative length, `offset + width` overflow or dangerous pointer arithmetic still cannot be treated as a real allocation.

## 14. Expected Java errors cannot save every native memory bug

Distinguish between errors FFM **has enough information** to detect and errors **it cannot prove from metadata**:

| Error | How can FFM detect it? | Limitation |
|---|---|---|
| Reading outside the view's `segment.byteSize()` | `IndexOutOfBoundsException` | If the view is declared too large, the check is based on wrong information |
| Reading after a confined/shared scope has closed | `IllegalStateException` | Does not detect an independent C `free` while the Java scope is still alive |
| Using a confined segment from another thread | `WrongThreadException` | Shared/global does not automatically synchronize data |
| `reinterpret(-1)` | `IllegalArgumentException` | Blocks negative sizes, does not verify positive sizes |
| `reinterpret` on a heap segment | `UnsupportedOperationException` | API applies only to native segments |
| Caller lacks appropriate native access | `IllegalCallerException` or warning depending on version/config | Granting permission does not make a pointer safe |
| Wrong alignment/`ValueLayout` | API-level alignment/type checks | Cannot infer the entire C ABI or ownership |
| 100-byte view on a 10-byte allocation, reading offset 80 | **No evidence to block in spatial metadata** | Can crash or corrupt memory |

**An outcome that does not throw an exception does not prove the operation was correct.** Native memory bugs sometimes only blow up in another request, another thread, or later during GC/JIT, making the root cause hard to trace.

## 15. Testing and code review suggestions for FFM bindings

### 15.1. Review criteria

Before every `reinterpret`, answer verbally or in a technical comment:

- **Pointer source:** from `Arena.allocate`, C `malloc`, pointer into a struct, internal buffer, or mapped region?
- **Length:** what data source guarantees `newSize`? Is it in bytes or elements? Are overflow/max size checked?
- **Lifetime:** who can close the arena/free the pointer? Can the view outlive the owner?
- **Cleanup:** is there a proper release function, and is it called exactly once? Is a `null` callback justified?
- **Permissions and threads:** are read-only/ABI/alignment and concurrency correct?
- **Environment flags:** which module has restricted native access? Is the build toolchain JDK 22+?
- **Safer alternative:** can you use `asSlice` or copy into an explicitly owned buffer?

If any question has no reliable answer, **push the requirement back to the C API design or native owner**; do not use `reinterpret` to paper over missing information.

### 15.2. Testing without intentionally crashing the JVM

You can test **cases explicitly controlled by FFM** without dereferencing bad pointers:

- Call `original.asSlice(12, 8)` on a 16-byte view, expecting `IndexOutOfBoundsException`.
- Close `Arena.ofConfined()` and then try reading a view in the same scope, expecting `IllegalStateException`.
- Verify `reinterpret(24)` produces a 24-byte view, but **do not read bytes 16..23** if the backing is only 16 bytes long.
- Verify `slot.get(ValueLayout.ADDRESS, 0)` produces a 0-length pointer view before rebinding.
- Test `Math.multiplyExact` with counts that overflow, test null pointers, and test size limits.
- Test owner cleanup with a counter/log and verify **exactly-once** execution in a controlled native harness; do not intentionally free an invalid address to observe a crash.

To check for native memory leaks, use process-level metrics / Native Memory Tracking or appropriate tools; do not rely solely on the Java heap chart and do not run OOB read/write loops in a production process.

### 15.3. Running the JVM when using restricted methods

The two complete examples in this article use final JDK 22 FFM and `reinterpret` is a restricted API:

~~~bash
javac --release 22 ReinterpretViews.java
java --enable-native-access=ALL-UNNAMED ReinterpretViews

javac --release 22 PointerReinterpret.java
java --enable-native-access=ALL-UNNAMED PointerReinterpret
~~~

The `--enable-native-access=ALL-UNNAMED` flag grants permission to code on the classpath. If you copy the code into a **named module**, specify the appropriate module name. The warning/deny policy for restricted operations may change in newer JDKs; projects should consult documentation for their target runtime.

## 16. Comparison with JNI and traditional native allocators

In JNI, native code can obtain a `jbyteArray`, call `GetByteArrayElements`, or manipulate a `jobject` via the JNI API; these operations have different pin/copy/release contracts than FFM. FFM does not use `JNIEnv *` for every downcall and does not turn C's `malloc`/`free` into automatic Java ownership.

| JNI / C | FFM | What to know |
|---|---|---|
| `malloc(n)` allocates `n` bytes | `Arena.allocate(n)` allocates memory via FFM | Has clear size and owner information when allocated by Java |
| Raw C pointer without size | `MemorySegment.ofAddress(address)` creates a 0-byte view | Cannot be dereferenced yet |
| Casting a C pointer | `reinterpret(bytes)` creates a view with a declared size | No runtime proof of native backing |
| `free(pointer)` per C allocator | Cleanup action or native deallocator called by binding | Must have a single owner and matching allocator |
| JNI local/global refs | FFM `MemorySegment`/`Arena` | Do not equate Java object ref lifetimes with off-heap memory |
| Native buffer view | `asSlice(...)` | Safe subrange if source bounds are trustworthy |

**Do not arbitrarily `free` a memory region allocated by `Arena.allocate`** through a C allocator. In an application that calls a C library's `malloc`, you must use the exact release function specified by the API. A reinterpreted view does not change how the memory region was originally allocated.

## 17. Self-check exercises

1. Does `MemorySegment.reinterpret(100)` allocate 100 new bytes or ask the OS whether the backing allocation has at least 100 bytes?
2. If `original.byteSize() == 16` and `wider = original.reinterpret(24)`, what is definitely true about `wider` and what is **not yet proven**?
3. Why can `original.asSlice(12, 8)` be rejected while `wider.get(JAVA_INT, 16)` can exceed the actual allocation without being caught by the view's bounds check?
4. Why is a pointer returned from a C function usually represented as a zero-length segment?
5. Does `rawPointer.scope().isAlive() == true` prove that the native backing has not been `free`d?
6. How do the three `reinterpret` overloads in JDK 22 differ in size, scope, and cleanup?
7. If you attach a pointer allocated by `malloc` to another arena with `cleanup == null`, what resource problem can the system encounter?
8. If you attach a `free` callback to a pointer that is already managed by `Arena.allocate`, what risk can occur?
9. A native API provides element count `count` and size `elementBytes`; what must you check before converting to `byteCount`?
10. A pointer points into the middle of a 1 KiB allocation; why can't you simply reinterpret it as the full 1 KiB from that pointer's position?
11. Does `Arena.global()` guarantee that a pointer returned by C still has its backing memory even if the library has reclaimed it?
12. What does `AddressLayout.withTargetLayout(layout)` help with, and why is it also restricted?
13. Why does granting `--enable-native-access` not prove that a `reinterpret` call has the right size?
14. If a native API does not document lifetime/size, what design solution is more reasonable than "calling `reinterpret` with a huge number"?
15. In the two sample programs, why do they **never** perform reads/writes on backing memory that is not proven to exist?

**Conclusion:** `reinterpret` is a way to **change a view's metadata** for native memory: same address, but potentially different size/scope. It **does not verify the actual allocation**, does not create extra bytes, and does not automatically guarantee proper lifetime/ownership. Use it only when there is a clear C/native contract for **valid byte count, lifetime, alignment, access permissions, and deallocator**. When you only need to look at part of a known allocation, `asSlice` is safer. When you do not know the size or owner, **do not dereference** the pointer in Java.

### Official references

- [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): explains zero-length pointers, spatial/temporal bounds, `reinterpret` overloads, and restricted semantics.
- [Java SE 22 — FFM package (Restricted Methods)](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/package-summary.html): why restricted FFM methods can cause JVM crashes/memory corruption.
- [Java SE 22 — Arena](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): ownership of allocations, confined/shared/automatic/global scopes.
- [JEP 454 — Foreign Function & Memory API (Final)](https://openjdk.org/jeps/454): foundation of the official FFM API in JDK 22.
- [Dev.java — Troubleshoot Calls to Native Library Functions](https://dev.java/learn/api/io/ffm/troubleshoot/): zero-length segments, native allocation, and safe contract-based pointer interpretation.
