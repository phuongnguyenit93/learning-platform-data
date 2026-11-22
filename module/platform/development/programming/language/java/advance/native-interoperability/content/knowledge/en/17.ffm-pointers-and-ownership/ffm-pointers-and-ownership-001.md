# ValueLayout.ADDRESS and MemorySegment.NULL Represent C Addresses

## 1. Learning Objectives

In the **Foreign Function & Memory API (FFM)**, Java needs to exchange pointer values according to the C ABI convention without assuming that a pointer is always a Java `long`. The two core tools are:

- **`ValueLayout.ADDRESS`**: describes a **machine address** type (`void *`, `int *`, `char *`, etc. per the C contract), used as an element type or parameter/return in `FunctionDescriptor`. The corresponding Java carrier is `MemorySegment.class`.
- **`MemorySegment.NULL`**: a **0-byte native memory segment** representing a **C pointer with address 0**, equivalent in address to `MemorySegment.ofAddress(0L)`.

Most important objective: **distinguish a pointer value from the memory region pointed to by the pointer**. An address does not carry allocation size, liveness state, read/write permissions, or ownership on its own. FFM has safety checks, but restricted operations that allow assigning arbitrary bounds shift verification responsibility back to the native bridge author.

You will learn how to read/write a pointer slot, detect NULL, distinguish pointer-to-pointer, use `AddressLayout.withTargetLayout` in a controlled manner, and avoid dangling pointers, use-after-free, and double-free. The examples include standalone Java files, build/run commands, and deterministic stdout.

**Version requirements:** `java.lang.foreign` is stable in **JDK 22+** (JEP 454). The examples have been verified against the Java 22/24 API and tested on JDK 24. **Do not apply directly to Java 17**: FFM was still an incubator API at that time and had different packages/signatures.

## 2. C Pointers and FFM: What Is a Value, What Is Memory?

In C:

~~~c
#include <stdint.h>

void inspect(void) {
    int32_t number = 2026;
    int32_t *p = &number;
    int32_t *none = NULL;

    /* p is the pointer, *p is the data at address p. */
    (void) p;
    (void) none;
}
~~~

This is a standalone C example of variable declarations inside a function, **not a JNI method**. `p` is an **address value**. `number` is a **4-byte region holding int32_t data**, and `*p` is only valid while `number` still exists. `none` represents a null pointer; dereferencing `*none` is a critical error.

In FFM, `MemorySegment` has two common roles:

| Java value kind | Example | What does it mean? |
| --- | --- | --- |
| Segment with size and scope managed by Java | `arena.allocate(ValueLayout.JAVA_INT)` | Represents a 4-byte region accessible within the arena's lifetime |
| Segment wrapping only an address | `MemorySegment.ofAddress(0x1234L)` or `slot.get(ValueLayout.ADDRESS, 0)` | Represents a **pointer value**, typically `byteSize()==0`, does not prove any 4 bytes are valid |
| Native null pointer constant | `MemorySegment.NULL` | Address 0; no bytes can be dereferenced |
| Heap segment from a Java array | `MemorySegment.ofArray(new byte[] {1, 2})` | GC-managed Java heap region, **not** a stable native C pointer |

**Do not equate a Java reference/JNI `jobject` with a C pointer.** JNI references are managed by the JVM under GC; `MemorySegment` used as FFM's pointer carrier has a different contract. Raw addresses must not be used to infer the internal structure of a Java object.

### A Layout Is Different from a Segment

`ValueLayout.ADDRESS` belongs to the `AddressLayout` interface and is a **data descriptor**. `MemorySegment` is a **Java value carrying address/bounds/scope**. A layout does not allocate native memory; you need an `Arena` or another FFM API to obtain an actual segment.

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

AddressLayout layout = ValueLayout.ADDRESS;
System.out.println(layout.carrier() == MemorySegment.class); // true
~~~

This is a snippet inside a Java method/JShell, not a complete Java class. Java `int`, `long`, and `MemorySegment` are not interchangeable carriers just by casting.

## 3. `ValueLayout.ADDRESS`: Width, Alignment, and ABI

`ValueLayout.ADDRESS` is an `AddressLayout` with carrier `MemorySegment.class`, size equal to a platform machine address, ABI-defined alignment, and default byte order equal to native order.

~~~java
long bytes = ValueLayout.ADDRESS.byteSize();
long alignment = ValueLayout.ADDRESS.byteAlignment();
Class<?> carrier = ValueLayout.ADDRESS.carrier();
~~~

Some 64-bit systems typically have a pointer width of 8 bytes and alignment 8; 32-bit systems typically differ. Therefore, **do not hard-code width 8** and do not replace the `ADDRESS` layout with `JAVA_LONG` just because both are usually 8 bytes wide on a development machine.

| Purpose | FFM Layout | Java Type Used |
| --- | --- | --- |
| Native pointer (data/function pointer per corresponding ABI/API) | `ValueLayout.ADDRESS` | `MemorySegment` |
| Native pointer in a struct field | `ValueLayout.ADDRESS` | `MemorySegment` on `get`/`set` |
| 32-bit scalar Java int | `ValueLayout.JAVA_INT` | `int` |
| 64-bit scalar Java long | `ValueLayout.JAVA_LONG` | `long` |
| Pointer value at an unaligned byte offset in a verified packed format | `ValueLayout.ADDRESS_UNALIGNED` | `MemorySegment`; still requires sufficient bytes |

`JAVA_LONG` represents a 64-bit **integer**, not a portable C pointer type. A C pointer also does not by itself represent a size length or ownership; for example, `void *buffer` and `size_t length` are two separate pieces of information.

`ADDRESS_UNALIGNED` only relaxes the alignment requirement of the **slot storing the pointer**. It does **not** make the data pointed to by the pointer valid, does not fix bounds errors, and does not create ownership. For native structs containing padding, field positions must be calculated according to the ABI (`offsetof`, actual headers, or corresponding FFM layouts), not by blindly summing Java type sizes.

## 4. `MemorySegment.NULL` Is Not Java `null`

`MemorySegment.NULL` is a native segment with:

~~~java
System.out.println(MemorySegment.NULL.address());  // 0
System.out.println(MemorySegment.NULL.byteSize()); // 0

MemorySegment anotherNull = MemorySegment.ofAddress(0L);
System.out.println(anotherNull.address() == 0L);   // true
~~~

**C `NULL` corresponds to native address 0**, so when a C API accepts an optional pointer, `MemorySegment.NULL` is the appropriate argument. Java `null` means the absence of an object reference; it is not a `MemorySegment` value with address 0 and should not be used as a substitute by guesswork.

Comparison table:

| Value | `address() == 0L` | `byteSize() == 0` | Means C NULL? |
| --- | --- | --- | --- |
| `MemorySegment.NULL` | true | true | Yes |
| `MemorySegment.ofAddress(0L)` | true | true | Yes, by address value |
| A non-zero raw native pointer read via `get(ADDRESS)` | false | true | **No** |
| Native segment allocated by `Arena` with size 4 | typically false | false | No |
| Heap segment `MemorySegment.ofArray(new byte[0])` | may be 0 by heap representation | true | **No**: not a native pointer |

**Check for a null native pointer with `pointer.address() == 0L`, not `pointer.byteSize() == 0L`.** A non-null pointer can also have a 0-size wrapper. In particular, for a heap segment, `address()` may be offset 0 within the backing region, not a physical address; do not infer C NULL from a heap `address()`.

### Never Dereference NULL

~~~java
try {
    MemorySegment.NULL.get(ValueLayout.JAVA_BYTE, 0);
} catch (IndexOutOfBoundsException expected) {
    System.out.println("NULL has no readable bytes");
}
~~~

This is a snippet. The API blocks reading because the segment has no valid bytes. Do not use `MemorySegment.NULL.reinterpret(4)` and then read: declaring size 4 does not allocate memory at address 0, and restricted access can break memory safety.

## 5. Pointer Slot and Data Region Are Two Different Allocations

C example:

~~~c
int32_t value = 2026;
int32_t *pointer = &value;
~~~

A pointer slot holds an **address**; where the pointer points holds the **data**:

~~~text
Native data region                 Pointer slot
+----------------------+          +----------------------+
| int32_t value = 2026 | <--------| address of data      |
+----------------------+          +----------------------+
    4 bytes                         width = sizeof(pointer)

ValueLayout.JAVA_INT             ValueLayout.ADDRESS
~~~

In Java:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
    data.set(ValueLayout.JAVA_INT, 0, 2026);

    MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
    slot.set(ValueLayout.ADDRESS, 0, data);

    MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);

    System.out.println(pointer.address() == data.address()); // true
    System.out.println(pointer.byteSize());                   // 0
}
~~~

This is a snippet inside a Java method. `arena.allocate(ValueLayout.ADDRESS)` allocates enough bytes to **store one pointer-sized value**, not the pointee. `slot.set(ValueLayout.ADDRESS, 0, data)` writes the **address of data**, does not copy 2026 bytes, does not move data, and does not transfer ownership. `slot.get(ADDRESS,0)` reads the pointer from the slot, typically returning a **size-0 native segment attached to the global scope**.

That is why you should use the original `data` segment for reading/writing when you already have it. `pointer` only has an address and does not know how many bytes that region has, so `pointer.get(JAVA_INT,0)` typically throws `IndexOutOfBoundsException`.

## 6. Complete Java Program: Reading/Writing ADDRESS and NULL

Create the file `PointerAddressDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class PointerAddressDemo {
    public static void main(String[] args) {
        System.out.println("carrier="
                + (ValueLayout.ADDRESS.carrier() == MemorySegment.class));
        System.out.println("null-address=" + MemorySegment.NULL.address());
        System.out.println("null-size=" + MemorySegment.NULL.byteSize());

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
            data.set(ValueLayout.JAVA_INT, 0, 2026);

            MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
            slot.set(ValueLayout.ADDRESS, 0, data);

            MemorySegment pointer = slot.get(ValueLayout.ADDRESS, 0);
            System.out.println("same-address="
                    + (pointer.address() == data.address()));
            System.out.println("pointer-size=" + pointer.byteSize());
            System.out.println("data-value="
                    + data.get(ValueLayout.JAVA_INT, 0));

            try {
                pointer.get(ValueLayout.JAVA_INT, 0);
                throw new AssertionError("Expected bounds failure");
            } catch (IndexOutOfBoundsException expected) {
                System.out.println("pointer-read="
                        + expected.getClass().getSimpleName());
            }

            slot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);
            MemorySegment nullPointer = slot.get(ValueLayout.ADDRESS, 0);
            System.out.println("null-in-slot="
                    + (nullPointer.address() == 0L));
        }
    }
}
~~~

Compile and run with JDK 22+; **no** need to load a native library or enable restricted native access:

~~~bash
javac -encoding UTF-8 PointerAddressDemo.java
java PointerAddressDemo
~~~

Exact stdout:

~~~text
carrier=true
null-address=0
null-size=0
same-address=true
pointer-size=0
data-value=2026
pointer-read=IndexOutOfBoundsException
null-in-slot=true
~~~

Explanation: 2026 is read from `data` (the original segment), not from the raw pointer wrapper. `pointer` carries the right address, but `byteSize()==0` so direct dereferencing is blocked. Changing the pointer slot contents to `NULL` **does not free data**. After the arena closes, both `data` and `slot` become invalid; a raw pointer that once pointed to data is not proof that the allocation is still alive.

The example deliberately does not print actual address numbers (because ASLR/allocator/OS can change them), comparing only deterministic logical results.

## 7. Why Does a Pointer Read from `ADDRESS` Have Size 0?

A C pointer does not tell you:

- Whether the pointee is an `int`, a struct, a NUL-terminated string, or a binary array.
- How many bytes follow the address.
- Which allocator allocated it and whether `free` or `library_free` must be used.
- Until when the address is used in a callback.
- Whether the pointer has already been freed, modified by realloc, or released by another native thread.
- What alignment or thread-safety requirements the region has.

FFM therefore represents a read pointer as a **0-byte** segment, with global scope per the API: no bytes are permitted to be dereferenced by default.

~~~text
+------------------------------+
| pointer slot with address X  |
+------------------------------+
                 |
          get(ADDRESS, 0)
                 v
    MemorySegment(address=X,
                  byteSize=0,
                  scope=global)
                 |
        +--------+--------+
        |                 |
     address()       get(JAVA_INT,0)
        |                 |
        X          IndexOutOfBoundsException
~~~

**Global scope does not make the pointee's memory live forever**. It only describes the scope of the wrapper, not transferring ownership of the allocation that created address X. In particular, a pointer read from a slot may still exist as a Java object after the native arena that created data has closed, but it becomes a **dangling address** if the pointee has been freed.

## 8. Target Layout and Controlled Dereferencing

When it is **known for certain** that a native pointer points to a live, aligned `int32_t`, `AddressLayout.withTargetLayout` allows describing the target memory region:

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.ValueLayout;

AddressLayout pointerToInt =
        ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);
~~~

Normally `slot.get(ValueLayout.ADDRESS, 0)` returns a size-0 segment; with `pointerToInt`, `slot.get(pointerToInt, 0)` returns a segment of size **`JAVA_INT.byteSize() == 4`**. The pointer slot still occupies the number of bytes of `ADDRESS`, not replaced by an int.

**`withTargetLayout` is a restricted operation**: it trusts the layout declared by the caller and does not verify the allocation itself. Wrong target size, null address, dangling pointer, or wrong alignment can cause **JVM crash/memory corruption**. The caller needs native-access permission (with classpath: `--enable-native-access=ALL-UNNAMED`).

### Standalone Example `TypedPointerDemo.java`

~~~java
import java.lang.foreign.AddressLayout;
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class TypedPointerDemo {
    public static void main(String[] args) {
        // Restricted: use only when the pointee is understood and controlled.
        AddressLayout intPointer =
                ValueLayout.ADDRESS.withTargetLayout(ValueLayout.JAVA_INT);

        try (Arena arena = Arena.ofConfined()) {
            MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
            data.set(ValueLayout.JAVA_INT, 0, 41);

            MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
            slot.set(ValueLayout.ADDRESS, 0, data);

            MemorySegment view = slot.get(intPointer, 0);
            System.out.println("view-size=" + view.byteSize());
            System.out.println("view-value="
                    + view.get(ValueLayout.JAVA_INT, 0));
        }
    }
}
~~~

Compile/run on JDK 22+:

~~~bash
javac -encoding UTF-8 TypedPointerDemo.java
java --enable-native-access=ALL-UNNAMED TypedPointerDemo
~~~

Stdout:

~~~text
view-size=4
view-value=41
~~~

This is a case with **valid grounds to trust the target**: the program itself allocated 4 bytes using the arena, set the value, and read it inside the `try` block while the allocation was still alive. Do not store `view` for use after `arena.close()`; the raw pointer view has a different scope from the original data segment, so it will not automatically stop at the right time if the pointee has been freed.

### `reinterpret` and Scope

`MemorySegment.reinterpret(newSize)` and the variant `reinterpret(newSize, arena, cleanup)` are also **restricted methods** to create new bounds/scope for a native pointer. Neither allocates the target region nor proves the address is safe. Using the overload with `Arena` can bind the **view** to a new scope, but you must still ensure the real backing memory belongs to the right lifetime/owner; do not attach a fake cleanup or duplicate a native deallocator.

**Preference:** If you already have `MemorySegment data` returned by `Arena.allocate(...)` itself, use `data` or `data.asSlice(...)` instead of round-tripping through a pointer and calling `reinterpret`. Only construct a view from a raw address when you truly need to work with a C API result and have the full contract.

## 9. Check NULL Before Expanding Bounds

A C API may return a 0 pointer to indicate missing data. The consumer should check first:

~~~java
// Snippet: pointer is a native MemorySegment with an address from C.
if (pointer.address() == 0L) {
    // C NULL: do not dereference.
} else {
    // Not enough: still need valid size, lifetime, alignment, owner.
}
~~~

**Non-NULL does not mean valid**: a dangling pointer or a pointer to freed memory still has a non-zero address. Therefore, checking NULL is a necessary condition for many APIs, **not a sufficient condition** for safe access.

`MemorySegment.ofAddress(someLong)` by itself also only creates a 0-byte segment and does not validate that the pointer exists. Do not use a constant `0x12345678L` as an address to try reading in a demo: an arbitrary number can point to an invalid region and cause a JVM error when reinterpreted.

## 10. `T*` vs `T**`: Pointer and Pointer Slot

A C API can fill in a result pointer via an out-parameter:

~~~c
#include <stdint.h>

/* Illustrative C prototype only, no implementation yet. */
int make_buffer(int32_t **out, size_t *count);
~~~

`out` is a **pointer-to-pointer**, i.e., the address of a region storing a pointer. For FFM, you must allocate a pointer slot and pass the **slot's segment** to the native function:

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment outputSlot = arena.allocate(ValueLayout.ADDRESS);
    outputSlot.set(ValueLayout.ADDRESS, 0, MemorySegment.NULL);

    // Corresponding native function will receive outputSlot:
    // make_buffer(outputSlot, countSlot) -- simulation only.

    MemorySegment result = outputSlot.get(ValueLayout.ADDRESS, 0);
    if (result.address() != 0L) {
        // Need to know count, size, allocator, and release function.
    }
}
~~~

This is a **conceptual snippet**, not performing a foreign downcall. After C writes `*out`, read the slot with `get(ADDRESS)` to obtain the pointer value.

Distinguish the three things passed:

| Passed to C | What does C see? |
| --- | --- |
| `MemorySegment.NULL` | A **null pointer** for the argument |
| `outputSlot` | Address of a **slot large enough to hold a pointer**, suitable for a `T **` argument |
| `result` | The pointer value held in the slot after C writes; **not** the address of the slot |

C `size_t *count` is **another out-parameter** and must be declared according to the real ABI (do not take `JAVA_LONG` as a universal answer for every `size_t`). When retrieving a buffer from C, `get(ADDRESS)` does not know the length or whether it has permission to free. Read the API's contract: caller-owned or library-owned, how long the lifetime is, and which release function?

## 11. ADDRESS in `FunctionDescriptor`

If a C API defines:

~~~c
void *identity(void *p);
~~~

then the FFM descriptor (excluding symbol lookup/downcall setup) can be:

~~~java
import java.lang.foreign.FunctionDescriptor;
import java.lang.foreign.ValueLayout;

FunctionDescriptor descriptor = FunctionDescriptor.of(
        ValueLayout.ADDRESS,  // C return void*
        ValueLayout.ADDRESS   // C parameter void*
);
~~~

Here, the **machine** type of the parameter and return value is a pointer. The carrier in Java is `MemorySegment`. `FunctionDescriptor` does not create memory, does not check whether the allocation is alive, and does not encode ownership. Performing an actual downcall requires the right C symbol, `Linker`, ABI, lifetime, and native-access permission for restricted operations.

For APIs with `const void *`, the pointer layout can still be `ADDRESS`, but C `const` is a **contract not to modify data** that FFM does not enforce by itself when looking only at the pointer layout. You need to separate the read-only contract from the writeability of other aliases.

## 12. Ownership: What Frees a C Address?

**A pointer value does not own memory**. To write correct code, determine who allocates and who must clean up:

| Data source | Owner/lifetime | Rule |
| --- | --- | --- |
| `arena.allocate(...)` | The `Arena` in use; for confined/shared closeable arenas, becomes invalid on `close()` | Do not store raw pointers for native code to use after close |
| C `malloc` or factory returning a caller-owned pointer | Per C API; typically the caller has the right to release with the corresponding native deallocator | Use the exact `free`/`library_free` per contract; release only once |
| C library returning a pointer into an internal buffer | Library-owned, may be invalidated on the next call | Do not `free` yourself; copy within lifetime if you need to keep it |
| Pointer to a local C stack variable after return | Dangling | Do not "fix" with `ofAddress` or `reinterpret`; fix the C API |
| Heap `MemorySegment.ofArray` | JVM manages Java heap | Do not use as a raw native pointer into C if the API does not support it |
| `MemorySegment.ofAddress(rawLong)` | Wrapper only, **no additional allocation/cleanup registered** | Do not treat a live Java object as a live pointee |

Counter-example:

~~~java
MemorySegment raw;
try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(ValueLayout.JAVA_INT);
    raw = MemorySegment.ofAddress(data.address());
}
// raw.address() may still be non-zero.
// Do not use raw.reinterpret(4).get(JAVA_INT, 0) after the arena closes!
~~~

The snippet does not dereference the dangling pointer. When the arena closes, the source memory has expired. `raw` has global scope, but that does not make the backing allocation live forever. **The global scope of the wrapper is not the lifetime of the pointee**.

If a native asynchronous callback still holds the pointer, only close the arena once all native consumers have finished. If the native library owns its own allocator, do not use an arena to free memory outside the contract (and do not call C `free` from another allocator by guesswork).

### Heap Memory Is Not a C Native Pointer

~~~java
try (Arena arena = Arena.ofConfined()) {
    MemorySegment slot = arena.allocate(ValueLayout.ADDRESS);
    MemorySegment heap = MemorySegment.ofArray(new byte[] {1, 2});

    try {
        slot.set(ValueLayout.ADDRESS, 0, heap);
    } catch (IllegalArgumentException expected) {
        System.out.println("heap-not-native=true");
    }
}
~~~

On JDK 24, the printed line is `heap-not-native=true`. The `set(ADDRESS,...)` API only accepts a **native segment value**; a heap segment may have an `address()` offset of 0, but it is not C `NULL` or the physical address of the backing array. Java GC can move arrays; do not pass heap offset numbers to C.

## 13. Bounds, Alignment, Lifecycle, and Thread-Safety Are Separate Checks

An ABI-correct pointer only resolves the **address type**. Valid dereferencing also requires:

1. **Bounds:** the pointer must point to at least the number of bytes to be read. `get(ADDRESS)` defaults to size 0 to avoid guessing the size.
2. **Alignment:** `JAVA_INT` typically requires 4-byte alignment; `ADDRESS` requires suitable slot alignment. `ADDRESS_UNALIGNED` only affects where the **pointer is stored**, not automatically fixing the pointee.
3. **Scope/lifetime:** the Arena may have closed, C may have freed it, or a native function may have invalidated the pointer.
4. **Thread access:** `Arena.ofConfined()` only allows the owner thread to access the original segment. Constructing a raw address wrapper can lose that check and does **not** make sharing safe.
5. **Read/write:** C `const`, FFM read-only views, and native permissions are different contracts; a pointer layout does not enforce immutable data by itself.
6. **Ownership:** who frees it, with which API, after which operation, and can ownership be transferred across the FFM boundary?

Do not rely on a single check like `ptr.address()!=0L` to skip the remaining five conditions. An invalid pointer can still be a valid non-zero number in terms of bit representation.

## 14. Common Mistakes

| Mistake | Cause | How to fix |
| --- | --- | --- |
| Using `ValueLayout.JAVA_LONG` instead of `ADDRESS` | Guessing width from the current machine, wrong pointer ABI/semantics | Use `ADDRESS` for pointers |
| Passing Java `null` for C NULL | Not a `MemorySegment` object carrying address 0 | Use `MemorySegment.NULL` |
| Checking `byteSize()==0` to detect null | Non-null raw pointers also have size 0 | Check `address()==0L` |
| `get(ADDRESS).get(JAVA_INT,0)` fails | Zero-length raw pointer wrapper | Keep the original segment or ensure bounds and use a controlled restricted target |
| Trying `NULL.reinterpret(...)` to read | Address 0 does not point to a valid data region | Never dereference NULL |
| `withTargetLayout` on an unknown pointer | Caller assigns wrong size; memory corruption | Use only with a trusted C contract |
| `ofAddress` and assuming memory belongs to an arena | Wrapper does not allocate or attach an owner | Manage the actual allocation |
| `set(ADDRESS, 0, heapSegment)` fails | Heap segment is not a native value | Copy data through a native segment when needed |
| Confusing `T **` with `T *` | Out pointer needs a slot to hold a pointer | Allocate `arena.allocate(ADDRESS)` and pass the slot |
| Closing Arena while C still uses the pointer | Dangling/use-after-free | Synchronize lifetime until C work finishes |
| Freeing a library-managed pointer | Double-free/wrong allocator | Follow the native ownership contract |
| Assuming global scope means immortal memory | Pointer wrapper does not manage the pointee | Track the owner/scope of the source allocation |
| Comparing numeric pointers across runs | ASLR, allocator, platform vary | Do not hard-code raw addresses |
| Interpreting heap `address()==0L` as C NULL | Heap address is a virtual offset, which can be 0 | Apply null-check only to native pointers |

**A very easy mistake to make:** `ValueLayout.ADDRESS` represents a **C address**, not automatically inferring that it is a UTF-8 C string, binary buffer, or pointer to a struct. If C returns `char *` without a length, you must know the NUL-terminator/encoding contract clearly; if it contains binary data, do not read up to byte 0 as a string.

## 15. Self-Check Questions

**Question 1.** In what sense is `MemorySegment.NULL` equivalent to `MemorySegment.ofAddress(0L)`?

**Answer:** Both represent native address 0 and zero-length, i.e., C NULL. You do not need nor should you rely on Java object identity between them.

**Question 2.** Does `byteSize()==0` prove a pointer is NULL?

No. A nonzero pointer read via `get(ValueLayout.ADDRESS,offset)` is also typically a zero-length wrapper. Use `address()==0L` on a native pointer.

**Question 3.** Why is using `JAVA_LONG` instead of `ADDRESS` not portable?

`JAVA_LONG` is always a 64-bit Java scalar, whereas `ADDRESS` selects pointer-sized representation/alignment per the ABI, with `MemorySegment` as carrier.

**Question 4.** Does `slot.set(ADDRESS,0,data)` copy the contents of `data` or write the address?

It only **writes the address**. `slot` is sized for a pointer value; `data` still retains its data and old owner/lifetime.

**Question 5.** `slot.get(ADDRESS,0)` returns a pointer with the same address as `data`, so why does `pointer.get(JAVA_INT,0)` fail?

Because the default pointer wrapper has `byteSize()==0` and **does not know the target region's size**; access throws `IndexOutOfBoundsException`.

**Question 6.** Does `withTargetLayout(JAVA_INT)` guarantee a valid pointer?

No. It is a restricted method that trusts the caller's contract; an invalid, NULL, or dangling pointer can crash the JVM or corrupt memory.

**Question 7.** A native API takes `int **out`. Can you pass `MemorySegment.NULL` directly for C to write `*out`?

No. C needs the **address of a pointer slot** with enough bytes. Allocate `arena.allocate(ADDRESS)`, pass the slot, then read the pointer with `slot.get(ADDRESS,0)`.

**Question 8.** A raw pointer has global scope, but the arena that allocated the source has closed; is it still safe to access?

No. Global scope belongs to the wrapper and does not extend the backing allocation. Dereferencing after `arena.close()` is a dangerous use-after-free.

**Question 9.** When reading a non-NULL ADDRESS from a C pointer, is anything else needed to access the data?

Yes. You must determine the **byte count**, alignment, owner, lifetime, thread access, and whether the C API allows reading/writing. With a raw address, FFM cannot automatically recover missing information.

**Question 10.** `MemorySegment.ofArray(new byte[0])` can have address 0; is it C NULL?

No. This is a **heap segment** whose address is a logical offset, not a native null pointer. Do not force it into a C pointer without an appropriate mechanism.

## Checklist Before Passing Addresses Across FFM

- [ ] Native signature verified: `T *`, `T **`, or scalar `size_t`?
- [ ] `ValueLayout.ADDRESS` used for pointer parameters/returns/fields, not inferred from `JAVA_LONG`?
- [ ] Null pointer uses `MemorySegment.NULL`, checked with `address()==0L` for native pointers?
- [ ] Not checking null with `byteSize()==0`?
- [ ] Distinguished **pointer slot** address from **pointee** address?
- [ ] Every size-0 raw pointer wrapper treated as an **opaque address** until an access contract is established?
- [ ] Restricted `withTargetLayout`/`reinterpret` used only when the target is known for certain and native access is enabled?
- [ ] Sufficient length, alignment, scope, thread ownership, and read/write permissions?
- [ ] Allocator/deallocator identified, avoiding use-after-free/double-free?
- [ ] Tested NULL and non-null pointers; program does not hard-code actual address numbers?
- [ ] Not passing heap `MemorySegment.ofArray` directly as a C pointer?
- [ ] When C holds a pointer across a callback/async job, memory is kept alive until the work finishes?

## Official Documentation

1. [Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `NULL`, `ofAddress`, `get/set(AddressLayout,...)`, zero-length wrappers, `reinterpret`, and scope.
2. [Java SE 24 — AddressLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/AddressLayout.html): carrier `MemorySegment.class`, restricted `withTargetLayout`.
3. [Java SE 24 — ValueLayout](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/ValueLayout.html): `ADDRESS`, `ADDRESS_UNALIGNED`, width/alignment/order.
4. [Java SE 24 — Arena](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/Arena.html): allocation, lifetime, confined/shared scope.
5. [Java SE 24 — FunctionDescriptor](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/FunctionDescriptor.html): pointer values in FFM downcall ABI.
6. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API stable since JDK 22.

**Conclusion:** `ValueLayout.ADDRESS` describes **how C addresses are stored and passed**. `MemorySegment.NULL` describes a **C NULL pointer with address 0**. However, a raw address does not prove that the pointee has valid memory; safety requires explicitly verifying **bounds, lifetime, alignment, and ownership** before any dereference.
