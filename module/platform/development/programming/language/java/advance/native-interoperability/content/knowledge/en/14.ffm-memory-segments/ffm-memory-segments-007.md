# MemorySegment: Read-Only Limits, Out-of-Bounds Access, and Misalignment

## Learning Objectives

`MemorySegment` in Java's Foreign Function & Memory API (FFM) represents **a contiguous region of memory with a defined size**. When accessing this region, the JVM checks several conditions that raw C pointers do not automatically check: whether the memory region is still valid, whether the current thread has access permission, whether the operation is within the segment bounds, whether the layout satisfies alignment requirements, and **whether write operations are prohibited because the segment is read-only**.

After this lesson, you can:

- Explain the meaning of `byteSize()`, `isReadOnly()`, and `asReadOnly()`.
- Correctly calculate the valid range for `get`/`set` by **byte offset** and `ValueLayout` size.
- Distinguish between `IndexOutOfBoundsException`, `IllegalArgumentException` (including read-only and misalignment), `IllegalStateException` (expired scope), and `WrongThreadException` (wrong thread).
- Understand why a slice with offset 0 can still be **misaligned**, and when `JAVA_INT_UNALIGNED` is useful.
- Design native parsers/bridges with bounds checking without assuming `asReadOnly()` creates a data copy or freezes physical memory.

**Version:** The content and compiled programs are based on the standard `java.lang.foreign` **API from JDK 22 and later** (JEP 454), verified on JDK 24. **JDK 17** has the FFM API in the incubator stage with different package names and signatures, so the examples below are **not** advertised to run directly on JDK 17. The examples only use memory access; no native C linking or downcall invocation is required.

## 1. Mental Model: A Segment Is a "Window" with an Access Contract

A native memory region allocated by an `Arena` may consist of many bytes, but a `MemorySegment` only allows operations on **the byte range that the segment itself describes**.

~~~text
Arena.allocate(16, 8) -> 16-byte segment, starting address is 8-byte aligned

byte offset       0  1  2  3 | 4  5  6  7 | 8  9 10 11 |12 13 14 15
                  <-------------- entire segment: byteSize() = 16 ------------>
JAVA_INT at 0     [ 4 bytes  ]
JAVA_INT at 12                                           [ 4 bytes  ]
JAVA_BYTE at 16                                                      X out of bounds
JAVA_INT at 1        [ 4 bytes  ]   within region but violates alignment 4
~~~

A valid access must **simultaneously** satisfy the following conditions:

1. **Scope is alive:** the arena/scope associated with the segment is still valid.
2. **Thread is permitted:** for a confined arena, only the owner thread is allowed to access.
3. **Valid byte range:** do not read/write before the first byte or past the end of the segment.
4. **Valid alignment:** the starting address of the access satisfies `layout.byteAlignment()`.
5. **Valid write permission:** for `set`, `fill`, copy-to, and data-modifying operations, the destination must not be a read-only segment.

`get` reads data so it does not require a writable segment, but it still checks scope, thread, bounds, and alignment. `set` must additionally satisfy the writable condition. No check means "if a segment is readable, every offset is valid".

## 2. Core Properties and APIs

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment data = arena.allocate(16, 8);
    System.out.println(data.byteSize());         // 16
    System.out.println(data.isReadOnly());       // false

    MemorySegment view = data.asReadOnly();
    System.out.println(view.byteSize());         // 16
    System.out.println(view.isReadOnly());       // true
}
~~~

This is a **code snippet inside a Java method**, not a standalone Java file: to run a file, place it in `main` or refer to the complete example in section 8.

| API | Effect | Key Points to Remember |
| --- | --- | --- |
| `byteSize()` | Total number of bytes of the region described by the current segment | This is the size of the **view**, not necessarily the entire original allocation |
| `isReadOnly()` | Indicates whether the segment blocks FFM write operations | Does not prove physical data cannot be modified through another alias |
| `asReadOnly()` | Returns a **read-only view** of the same memory region | Does not copy data; the original writable alias can still modify it |
| `asSlice(offset, size)` | Creates a sub-segment with smaller relative bounds | Uses byte offset, does not allocate new memory |
| `get(layout, offset)` | Reads a value of the layout type at the byte offset | Checks bounds and alignment |
| `set(layout, offset, value)` | Writes a value of the layout type at the byte offset | Checks read-only, bounds, and alignment |
| `ValueLayout.JAVA_INT` | 4-byte int layout, alignment 4, native byte order | Not suitable for addresses shifted by 1, 2, or 3 bytes |
| `ValueLayout.JAVA_INT_UNALIGNED` | 4-byte int layout, alignment 1 | Still requires 4 bytes, and still respects read-only |
| `Arena.ofConfined()` | Manages the lifetime of native allocations on a single thread | Access after `close()` or from an unpermitted thread will fail |

Two common types of segments: **heap segments** created via `MemorySegment.ofArray(...)` pointing to elements of a Java array; **native segments** allocated by an `Arena` off-heap or from other mechanisms such as memory mapping. The rules for segment bounds/read-only apply to both, though memory source and lifetime have different characteristics.

## 3. Read-Only: What Does `asReadOnly()` Prohibit?

Calling `asReadOnly()` creates a view through which write operations via **this view** are not allowed. `isReadOnly()` helps check that property before choosing a processing branch, though the JVM still enforces the check on writes.

~~~java
MemorySegment writable = MemorySegment.ofArray(new byte[] {10, 20, 30});
MemorySegment readOnly = writable.asReadOnly();

byte before = readOnly.get(ValueLayout.JAVA_BYTE, 0); // readable: 10
writable.set(ValueLayout.JAVA_BYTE, 0, (byte) 99);
byte after = readOnly.get(ValueLayout.JAVA_BYTE, 0);  // readable: 99

// The line below throws IllegalArgumentException with the MemorySegment.set API:
// readOnly.set(ValueLayout.JAVA_BYTE, 0, (byte) 42);
~~~

This is an abbreviated illustrative snippet. **Read-only does not mean an immutable snapshot**: `readOnly` and `writable` both look at the underlying data. Changes via a writable alias, via the backing Java array, or via another permitted native pointer can be visible in the read-only view.

### Protection Levels to Distinguish

- `readOnly.get(layout, offset)`: **allowed** if other access conditions are valid.
- `readOnly.set(layout, offset, value)`: **not allowed**; according to `MemorySegment.set`, it throws **`IllegalArgumentException`** when read-only.
- `readOnly.fill(value)`, `readOnly.copyFrom(source)`, and other write APIs: a read-only destination is also rejected; do not use a read-only view as a mutable destination.
- `readOnly.asSlice(...).isReadOnly()`: remains **true** because the slice is created from a read-only view.
- `writable.asReadOnly()` does **not** turn the original `writable` into read-only; other views created from `writable` can still be writable.

When sharing a read-only view as an API contract, make sure there are **no other writers** if the actual requirement is that the data does not change during reading. A read-only view does not automatically lock concurrency or create a transaction snapshot.

### Read-Only `MemorySegment` Differs from Read-Only `ByteBuffer` in Exceptions

If you call `readOnly.asByteBuffer()` and then write via `ByteBuffer.put(...)`, the `ByteBuffer` API may throw **`java.nio.ReadOnlyBufferException`** per the NIO contract. Meanwhile, `MemorySegment.set(...)` on the read-only segment itself throws **`IllegalArgumentException`** per the FFM contract. Do not catch all read-only errors with a single fixed exception class when using two different APIs.

## 4. Bounds: Offset Is in Bytes, and the Entire Value Must Fit Within the Segment

Suppose `segment.byteSize() == 16` and you access a `ValueLayout.JAVA_INT` with `byteSize() == 4`. The bounds condition is:

~~~text
offset >= 0
offset + 4 <= 16
    equivalently, avoiding overflow:
offset <= 16 - 4

offset 0: 4 bytes at [0,4)   -> OK, if alignment is right
offset 12: 4 bytes at [12,16) -> OK, if alignment is right
offset 13: 4 bytes at [13,17) -> out of bounds
offset 16: 1 byte at [16,17)  -> out of bounds
offset -1: starts before region -> out of bounds
~~~

The end point is **end-exclusive**: reading four bytes at offset 12 uses bytes 12, 13, 14, and 15. Byte offset 16 is the **position after the end**, not a readable byte.

A pre-access check pattern:

~~~java
static boolean fits(MemorySegment segment, long offset, long accessBytes) {
    return offset >= 0
            && accessBytes >= 0
            && accessBytes <= segment.byteSize()
            && offset <= segment.byteSize() - accessBytes;
}
~~~

This helper method returns false if there are not enough bytes and avoids the `offset + accessBytes` expression that could overflow. However, **`fits` only checks bounds**: it does not guarantee layout alignment, scope/thread, or write permission. Production code should still let the FFM API perform the final check, because conditions can change if the scope closes or the operation happens on another thread.

For `MemorySegment.get(ValueLayout.JAVA_INT, offset)`, an out-of-bounds access throws **`IndexOutOfBoundsException`**. For `getAtIndex`, the `index` parameter is an **element index**, multiplied by the layout byte size; completely different from a byte offset:

~~~java
// For a 16-byte segment with appropriate alignment:
segment.get(ValueLayout.JAVA_INT, 12);        // byte offset 12
segment.getAtIndex(ValueLayout.JAVA_INT, 3);  // index 3 -> byte offset 12

// Index 4 -> byte offset 16 and requires 4 bytes -> out of bounds.
// segment.getAtIndex(ValueLayout.JAVA_INT, 4);
~~~

This is a snippet, assuming `segment` exists and has sufficient alignment. If index multiplication overflows or the element lies outside the segment, `getAtIndex` can also throw `IndexOutOfBoundsException`.

### An Empty Slice at the End Can Still Be Valid

`segment.asSlice(segment.byteSize(), 0)` represents a 0-byte region right at the end of the segment and can be validly created. However, **there are no bytes to read from it**. Conversely, `segment.asSlice(15, 2)` on a 16-byte segment must be rejected because the slice requires up to byte 16 (byte 17 end-exclusive).

Do not confuse being able to create a 0-sized view with the right to access the byte offset equal to `byteSize()`.

## 5. Alignment: A Region Large Enough May Still Not Be Readable with the Desired Layout

**Alignment** requires the starting address of an access to match a byte boundary. `ValueLayout.JAVA_INT` has size 4 and alignment 4, `ValueLayout.JAVA_LONG` has size 8 and alignment 8. `ValueLayout.JAVA_BYTE` has size 1 and alignment 1.

On a native segment created with:

~~~java
MemorySegment segment = arena.allocate(16, 8);
~~~

`arena` is a live `Arena`. The second argument `8` requests 8-byte alignment for the **starting address of the allocation**. When byte offset 0 is 8-byte aligned, offset 4 is 4-byte aligned, while offset 1 is not 4-byte aligned.

~~~text
Base address A: A % 8 == 0

A + 0: valid for JAVA_INT (4-byte alignment)
A + 4: valid for JAVA_INT
A + 8: valid for JAVA_INT
A + 1: NOT valid for JAVA_INT
A + 1: valid for JAVA_BYTE
~~~

If you call:

~~~java
segment.get(ValueLayout.JAVA_INT, 1);
~~~

when `segment` is the 16-byte native segment above, the data at offset 1..4 is **not out of bounds** but **violates alignment**. FFM throws **`IllegalArgumentException`** because the access is incompatible with `layout.byteAlignment()`.

### UNALIGNED Layouts: Changes One Constraint, Does Not Remove All Constraints

~~~java
int value = segment.get(ValueLayout.JAVA_INT_UNALIGNED, 1);
~~~

`JAVA_INT_UNALIGNED` still reads **4 bytes** but its alignment is reduced to **1**. Therefore, byte offset 1 can be read with this layout within the valid segment range. However:

- `get(JAVA_INT_UNALIGNED, 13)` on a 16-byte segment is still blocked by the bounds check because it requires up to byte offset 16.
- `set(JAVA_INT_UNALIGNED, ..., ...)` on a **read-only** segment is still rejected.
- A closed scope or unpermitted thread still causes an error even though the layout allows unaligned access.
- Unaligned access may have performance costs or portability issues; you should not choose this layout by default to mask data structure bugs.

The constants `JAVA_SHORT_UNALIGNED`, `JAVA_CHAR_UNALIGNED`, `JAVA_LONG_UNALIGNED`, `JAVA_FLOAT_UNALIGNED`, and `JAVA_DOUBLE_UNALIGNED` are also available when a format genuinely requires reading at unaligned byte offsets.

### Endianness Differs from Alignment

`layout.order()` specifies the byte order (big-endian/little-endian) when decoding multi-byte numbers. It does **not** make a misaligned address aligned. For example:

~~~java
import java.nio.ByteOrder;

var bigEndianInt = ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);
// bigEndianInt still has byteAlignment() == 4.
~~~

To require both unaligned access and a specific byte order, you can use `ValueLayout.JAVA_INT_UNALIGNED.withOrder(ByteOrder.BIG_ENDIAN)` when the binary format contract requires it. Choose byte order according to **the data protocol**; do not blindly use native order if the file/network format defines a different byte order.

## 6. Slice and Offset 0: The "Start of the View" Is Not Necessarily Aligned

A slice is a **view over the same memory** and has **its own bounds**. The offset when calling `slice.get(layout, 0)` is offset 0 **relative to the slice**, not offset 0 of the original allocation.

~~~java
MemorySegment base = arena.allocate(16, 8);
MemorySegment shifted = base.asSlice(1, 4);

shifted.get(ValueLayout.JAVA_BYTE, 0); // OK, byte alignment 1

// Wrong: shifted's address is base-address + 1; JAVA_INT requires alignment 4.
// shifted.get(ValueLayout.JAVA_INT, 0);

// Correct when the format requires unaligned:
// shifted.get(ValueLayout.JAVA_INT_UNALIGNED, 0);
~~~

This is a snippet requiring a valid `Arena arena`; it cannot be run standalone as a file. By using `JAVA_INT_UNALIGNED`, you accept decoding an int from four bytes starting at a misaligned address. **You cannot fix an alignment error by changing the offset variable to 0 on an already-shifted view**.

A slice also **narrows the access range**: if `shifted.byteSize() == 4`, calling `shifted.get(JAVA_BYTE, 4)` is still out of bounds even though `base` has many more bytes after it. The JVM checks against **the segment object used in the call**, without expanding to the original allocation.

### Read-Only Propagates Through Slices

~~~java
MemorySegment ro = base.asReadOnly();
MemorySegment child = ro.asSlice(4, 4);

System.out.println(ro.isReadOnly());    // true
System.out.println(child.isReadOnly()); // true
~~~

If you want a read-only view of a portion of memory, you can create a slice and then call `asReadOnly()`. Read-only is preserved when creating a slice from an already read-only view. However, this is still a **permission of the view**, not a change to the write permissions of all aliases.

## 7. Error Table: The Same Exception Does Not Necessarily Mean the Same Cause

| Violated Condition | Typical API | Commonly Specified Exception | How to Check and Fix |
| --- | --- | --- | --- |
| Writing to an `asReadOnly()` view | `set(JAVA_INT, 0, ...)` | `IllegalArgumentException` | Check `isReadOnly()`; choose a writable destination with proper ownership |
| Access does not satisfy layout alignment | `get(JAVA_INT, 1)` on aligned base | `IllegalArgumentException` | Fix offset/layout or intentionally use `JAVA_INT_UNALIGNED` |
| Out-of-bounds segment access | `get(JAVA_BYTE, byteSize())` | `IndexOutOfBoundsException` | Check bounds using byte offset and access size |
| Creating a slice exceeding bounds | `asSlice(15, 2)` on a 16-byte segment | `IndexOutOfBoundsException` | Ensure offset and newSize fit within parent |
| Arena already closed | `get` after `arena.close()` | `IllegalStateException` | Do not use segment after its scope has expired |
| Confined segment from another thread | `get` from worker thread | `WrongThreadException` | Use owner thread or appropriate Arena policy |
| Writing through a read-only NIO buffer | `asByteBuffer().put(...)` | `ReadOnlyBufferException` | Distinguish NIO exception from FFM; use writable view |
| `getAtIndex` with index overflow/exceeding element count | `getAtIndex(JAVA_INT, 4)` on 16 bytes | `IndexOutOfBoundsException` | Check logical index and element count per layout |

**Do not assume an exception priority order when a single operation violates multiple conditions.** For example, reading `JAVA_INT` at offset 13 on a 16-byte segment can be both out of bounds (needs 4 bytes) and misaligned. To test clearly, create cases that **violate only one condition at a time**. Also, do not catch every `IllegalArgumentException` and always conclude "read-only", because misalignment can produce the same class.

## 8. Complete, Compilable, and Runnable Java 22+ Program

This example illustrates six behaviors: read-only; out-of-bounds; misalignment; unaligned layout; aliases viewing the same data; and expired scope.

Create the file `SegmentSafetyDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;

public final class SegmentSafetyDemo {
    private static void expect(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected " + expected.getSimpleName());
        } catch (RuntimeException actual) {
            if (!expected.isInstance(actual)) {
                throw new AssertionError("Unexpected exception", actual);
            }
            System.out.println(label + "=" + actual.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        MemorySegment[] afterClose = new MemorySegment[1];

        try (Arena arena = Arena.ofConfined()) {
            // Base address is 8-byte aligned, size = 16 bytes.
            MemorySegment writable = arena.allocate(16, 8);
            afterClose[0] = writable;

            writable.set(ValueLayout.JAVA_INT, 0, 100);
            writable.set(ValueLayout.JAVA_INT, 12, 500);
            MemorySegment readOnly = writable.asReadOnly();

            System.out.println("size=" + writable.byteSize());
            System.out.println("readOnly=" + readOnly.isReadOnly());
            System.out.println("first=" + readOnly.get(ValueLayout.JAVA_INT, 0));

            expect("write", IllegalArgumentException.class,
                    () -> readOnly.set(ValueLayout.JAVA_INT, 0, 300));

            // Offset 16 contains no valid byte.
            expect("bounds", IndexOutOfBoundsException.class,
                    () -> writable.get(ValueLayout.JAVA_BYTE, 16));

            // Offset 1 is still within 16 bytes but violates alignment 4.
            expect("alignment", IllegalArgumentException.class,
                    () -> writable.get(ValueLayout.JAVA_INT, 1));

            // UNALIGNED layout allows reading four bytes at offset 1.
            writable.get(ValueLayout.JAVA_INT_UNALIGNED, 1);
            System.out.println("unalignedAllowed=true");

            MemorySegment slice = readOnly.asSlice(0, 4);
            System.out.println("sliceReadOnly=" + slice.isReadOnly());

            expect("sliceBounds", IndexOutOfBoundsException.class,
                    () -> writable.asSlice(15, 2));
            System.out.println("emptyEnd=" + writable.asSlice(16, 0).byteSize());

            // Read-only view sees changes from the writable alias.
            writable.set(ValueLayout.JAVA_INT, 0, 200);
            System.out.println("updatedView="
                    + readOnly.get(ValueLayout.JAVA_INT, 0));
        }

        // Arena has been closed by try-with-resources.
        expect("closed", IllegalStateException.class,
                () -> afterClose[0].get(ValueLayout.JAVA_BYTE, 0));
    }
}
~~~

Compile and run with **JDK 22+** (no `--enable-preview` needed for the standard API):

~~~bash
javac -encoding UTF-8 SegmentSafetyDemo.java
java SegmentSafetyDemo
~~~

Expected stdout:

~~~text
size=16
readOnly=true
first=100
write=IllegalArgumentException
bounds=IndexOutOfBoundsException
alignment=IllegalArgumentException
unalignedAllowed=true
sliceReadOnly=true
sliceBounds=IndexOutOfBoundsException
emptyEnd=0
updatedView=200
closed=IllegalStateException
~~~

Explanation of each case:

1. `arena.allocate(16, 8)` creates a 16-byte segment with base alignment 8.
2. `readOnly.get(JAVA_INT, 0)` is valid and returns 100.
3. Writing through `readOnly` produces `IllegalArgumentException` due to read-only.
4. Reading one byte at offset 16 throws `IndexOutOfBoundsException` because the last valid byte is 15.
5. Reading an int at offset 1 is misaligned while still within bounds, so it throws `IllegalArgumentException`.
6. `JAVA_INT_UNALIGNED` accepts offset 1; the integer result is not printed because it depends on byte contents and byte order, which is not needed to demonstrate access permission.
7. A slice from `readOnly` remains read-only; slice 15,2 is out of bounds; slice 16,0 is a valid empty view.
8. When updating the value via the writable segment, the read-only view sees 200 — proving the view shares backing memory.
9. After `Arena.ofConfined()` is closed, the next access throws `IllegalStateException`. Do not attempt to re-read freed native memory using a C pointer.

**This is the output of the program when run normally.** If run with JDK 17 (which lacks the corresponding standard API), it will fail to compile; JDK 22+ is required.

## 9. Wrong Thread: A Different Error from Read-Only/Bounds/Alignment

`Arena.ofConfined()` restricts access to native segments it manages to the thread that owns the arena. Another thread reading byte offset 0, even if within bounds and aligned, is still not permitted.

Create `ConfinedThreadDemo.java`:

~~~java
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.util.concurrent.atomic.AtomicReference;

public final class ConfinedThreadDemo {
    public static void main(String[] args) throws InterruptedException {
        try (Arena arena = Arena.ofConfined()) {
            MemorySegment segment = arena.allocate(1);
            AtomicReference<String> error = new AtomicReference<>("none");

            Thread worker = new Thread(() -> {
                try {
                    segment.get(ValueLayout.JAVA_BYTE, 0);
                } catch (RuntimeException ex) {
                    error.set(ex.getClass().getSimpleName());
                }
            });

            worker.start();
            worker.join();
            System.out.println("otherThread=" + error.get());
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 ConfinedThreadDemo.java
java ConfinedThreadDemo
~~~

Stdout:

~~~text
otherThread=WrongThreadException
~~~

This is a **thread access permission error**, not a read-only or misalignment error. If you want to share native segments between threads, consider `Arena.ofShared()` along with appropriate application synchronization; a shared arena allows multi-threaded use but **does not automatically make all concurrent writes safe**.

Note the ordering: `worker.join()` before the arena closes helps clearly isolate the wrong-thread error; if both the scope is closed and access occurs from the wrong thread, multiple conditions are violated and you should not rely on which exception class takes precedence.

## 10. Pre-Check Rules Before Processing Untrusted Data

Suppose you read a binary structure coming from a file or native library:

~~~text
header: 4-byte int
payloadLength: 4-byte int
payload: payloadLength bytes
~~~

Things to check **before reading**:

- Does the segment have at least 8 bytes to read the two integers at offsets 0 and 4?
- Are offsets and sizes calculated in **bytes** or element counts?
- Which fields require aligned access? If the file has packed unaligned fields, do the layouts need `*_UNALIGNED`?
- Can the length integer be negative or very large? Could it overflow when added to the header?
- Is the segment read-only or writable? A parser only needs to read; it must not require `set` on a view where writes are prohibited.
- Do the arena/scope and thread permissions remain valid throughout the entire processing?

A simple helper to check bounds before access:

~~~java
static void requireRange(MemorySegment segment,
                         long offset,
                         long length) {
    long size = segment.byteSize();

    if (offset < 0 || length < 0
            || length > size
            || offset > size - length) {
        throw new IllegalArgumentException("Invalid byte range");
    }
}
~~~

**Note on exceptions:** this custom helper intentionally throws `IllegalArgumentException` to reflect invalid application input data. If calling `MemorySegment.get/set` directly out of bounds, FFM throws **`IndexOutOfBoundsException`**. Do not use the exception type from the helper to assert that FFM will throw the same type.

Avoid:

~~~java
// Wrong when offset + length can overflow long:
// if (offset + length <= segment.byteSize()) ...

// Wrong when confusing length in bytes with number of ints:
// segment.getAtIndex(ValueLayout.JAVA_INT, byteOffset);

// Wrong when assuming unaligned layout skips bounds:
// segment.get(ValueLayout.JAVA_INT_UNALIGNED, segment.byteSize());
~~~

For binary formats with a specified byte order, choose `ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN)` or `JAVA_INT_UNALIGNED.withOrder(...)` depending on both alignment and byte order. Byte order only determines how bytes are interpreted; it does not expand bounds or write permissions.

## 11. Is a Read-Only View Absolute Protection for Native Memory?

**No.** `MemorySegment.asReadOnly()` enforces the read-only rule **when accessed through that view using the FFM API**. It does not make the backing allocation globally immutable.

Example with a heap-backed segment:

~~~java
byte[] backing = {1, 2, 3};
MemorySegment ro = MemorySegment.ofArray(backing).asReadOnly();

System.out.println(ro.get(ValueLayout.JAVA_BYTE, 0)); // 1
backing[0] = 7;
System.out.println(ro.get(ValueLayout.JAVA_BYTE, 0)); // 7
~~~

Other valid update paths to the same data can change the values observed by the read-only view. Therefore:

- If an API requires an **immutable snapshot**, you must copy the contents to separate caller-managed storage and control all write paths; `asReadOnly()` alone is not enough.
- If an API requires **preventing accidental modification through a handle**, a read-only view is a good mechanism because FFM will reject write operations through that handle.
- If native code already has a C pointer to the same allocation, a read-only FFM wrapper does not automatically constrain all C accesses.
- If data is shared across multiple threads, memory visibility and synchronization policies are still needed; `isReadOnly()` does not replace synchronization.

Especially with native pointers and dangerous methods that can reinterpret the size or lifetime of a memory region, do not disable FFM constraints by trusting unvalidated pointers/lengths. The memory safety of FFM access relies on **the segment accurately describing the allocated memory region and its lifetime**.

## 12. Common Debugging Pitfalls

| Symptom | Possible Diagnosis | Resolution |
| --- | --- | --- |
| `set` throws `IllegalArgumentException` at offset 0 | View may be read-only, or layout alignment is incorrect | Check `isReadOnly()`, `byteAlignment()`, base/slice offset |
| `get(JAVA_INT, 1)` fails on a 16-byte segment | Not missing bytes; layout requires alignment 4 | Use an aligned offset or unaligned layout **if the format allows** |
| `get(JAVA_INT_UNALIGNED, 13)` still fails | 13 + 4 exceeds byteSize 16 | Check that the region is large enough; unaligned does not disable bounds |
| `asSlice(1, 4).get(JAVA_INT, 0)` fails | Slice starts at address base + 1, not 4-aligned | Consider an aligned slice or `JAVA_INT_UNALIGNED` |
| `readOnly.asSlice(...).set(...)` fails | Slice inherits read-only | To write, a valid separate writable alias/destination is needed |
| `asSlice(16, 0)` succeeds to create but `get` fails | Zero-length view has no bytes to read | Skip reading when size is 0 |
| `getAtIndex(JAVA_INT, 3)` is valid but 4 fails | Index 3 is byte offset 12, index 4 is 16 | Calculate index by element count; valid range 0..3 |
| Reading after `arena.close()` fails | Scope has expired | Do not use segment/pointer after close |
| Reading from another thread fails even at byte offset 0 | Confined arena binds to owner thread | Use the owning thread or a shared arena |
| Reading through a read-only view sees data change | Another alias modified the backing memory | Copy to take a snapshot if needed |
| `ByteBuffer.put` and `MemorySegment.set` throw different exceptions | Different APIs specify different exceptions | Distinguish `ReadOnlyBufferException` (NIO) and `IllegalArgumentException` (FFM) |

**Do not fix every error with `JAVA_INT_UNALIGNED`.** Doing so only relaxes the alignment requirement; if the root cause is out-of-bounds, read-only, expired scope, or wrong thread, it will still occur. In addition, unaligned access can be suboptimal and may not match native struct/ABI assumptions.

## 13. Self-Check Questions

**Question 1.** On a 16-byte segment, is `get(JAVA_INT, 12)` valid? What about `get(JAVA_INT, 13)`?

Answer: offset 12 reads bytes 12..15, **within bounds**; it only succeeds if alignment is also satisfied. Offset 13 requires bytes 13..16 so it is **out of bounds**. If alignment is also wrong at the same time, do not build code that depends on exception check ordering.

**Question 2.** Does `asReadOnly()` copy the underlying memory or block all other aliases from writing?

Answer: no; it creates a **read-only view** over the same backing memory. Aliases that are still writable can still modify the data.

**Question 3.** Does `MemorySegment.set` on a read-only segment throw `ReadOnlyBufferException` or `IllegalArgumentException`?

Answer: with the `MemorySegment.set` API in JDK 22+, **`IllegalArgumentException`**. `ReadOnlyBufferException` belongs to the write path through a read-only `java.nio.ByteBuffer`.

**Question 4.** After `base.asSlice(1, 4)`, is calling `slice.get(JAVA_INT, 0)` guaranteed to be aligned?

Answer: no; the slice's address starts at `base.address + 1`. If `base` is 8-byte aligned, the slice starts shifted by 1 byte, which does not satisfy `JAVA_INT` alignment 4. Offset 0 is only relative to the slice.

**Question 5.** Does `JAVA_INT_UNALIGNED` allow reading four bytes from offset 15 in a 16-byte segment?

Answer: no, because only one byte remains. An unaligned layout still requires **a full 4 bytes** and all other access permissions.

**Question 6.** Which bytes does `getAtIndex(JAVA_INT, 2)` on a 16-byte segment use?

Answer: index 2 corresponds to byte offset `2 * 4 = 8`, reading bytes 8, 9, 10, 11 when aligned.

**Question 7.** When `Arena.ofConfined()` closes, can an `asReadOnly()` view still be read because it only reads?

Answer: no. The scope of the backing memory has expired; accessing through the view still throws `IllegalStateException`. Read-only does not extend the arena lifetime.

**Question 8.** If you want multiple threads to read a native segment, is calling `asReadOnly()` on a confined segment enough?

Answer: no. Read-only controls write permission, **not** removing the thread confinement rule. You must choose the right lifetime/thread ownership, such as a shared arena, and handle synchronization if there are writers.

**Question 9.** Why might checking `offset >= 0 && offset + size <= byteSize` be unsafe when handling untrusted input?

Answer: `offset + size` can overflow `long`. Check non-negative quantities, `size <= byteSize`, and `offset <= byteSize - size` to avoid overflow when calculating bounds.

## MemorySegment Code Review Checklist

- [ ] Use JDK 22+ for the standard `java.lang.foreign` API, not the old incubator package by mistake.
- [ ] Know the `byteSize()` of **the actual segment/view being accessed**, rather than assuming the original allocation size?
- [ ] All `get/set` use byte offsets; `getAtIndex/setAtIndex` use element indices matching the layout?
- [ ] Checked bounds over **the entire value to be read/written**, not just the starting offset?
- [ ] Verified layout alignment and **slice** offset against the actual address of the view?
- [ ] If using `*_UNALIGNED`, is it required by the binary format and are portability/performance trade-offs understood?
- [ ] Distinguished data byte order from alignment and size?
- [ ] For write APIs, is `segment.isReadOnly()` considered, and no read-only destination used?
- [ ] Not treating `asReadOnly()` as a snapshot/copy or protection against all other writers?
- [ ] Arena scope is still alive and the calling thread is permitted to access?
- [ ] Properly handled `IllegalArgumentException`, `IndexOutOfBoundsException`, `IllegalStateException`, and `WrongThreadException` without guessing from a single error that may have multiple causes?
- [ ] Tested negative offsets, end positions, zero-length slices, packed data, misalignment, writable aliases, closed scopes, and cross-thread access?

## Official Documentation

1. [Java SE 22 — MemorySegment API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `asReadOnly`, `isReadOnly`, `byteSize`, `asSlice`, `get`/`set`, and error conditions.
2. [Java SE 22 — ValueLayout API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): size, byte alignment, byte order, `JAVA_*_UNALIGNED` layouts.
3. [Java SE 22 — Arena API](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/Arena.html): native memory allocation, scoped lifetime, confined/shared arenas.
4. [JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM becomes a standard API in JDK 22.
5. [Java SE 24 — MemorySegment](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/lang/foreign/MemorySegment.html): cross-reference error descriptions and access permissions on the JDK running the examples.

**Takeaway:** A valid memory access requires **correct bounds, alignment, scope, thread, and write permission**. `asReadOnly()` only constrains write operations through the view; `JAVA_INT_UNALIGNED` only relaxes the alignment constraint; and `byteSize()` is always the boundary of the exact segment you are using.
