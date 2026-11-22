# Byte Order, Address Alignment, and `struct` Padding Bytes in C and Interoperability with Java

## Objectives

When Java exchanges data with native code, a group of bytes only has meaning when both sides agree on **byte order (endianness)**, **field position/alignment**, and **padding bytes**. These three rules are related but do not replace one another. After this lesson, you will be able to:

- Correctly read the byte representation of multi-byte values on little-endian and big-endian machines.
- Predict `struct` layout according to a known ABI, and then verify it using `sizeof`, `_Alignof`, and `offsetof` rather than treating the prediction as a universal contract.
- Understand why the sum of field sizes can be smaller than `sizeof(struct)`, and why an array of `struct`s also requires tail padding.
- Correctly map offsets when using `ByteBuffer` in Java; know when an ABI-independent wire format must be used.
- Avoid bugs such as misreading numbers, misaligned accesses, directly comparing/writing memory regions containing padding, and wrongly depending on a compiler/platform.

## 1. Three Independent Concepts

| Concept | What does it determine? | Illustration |
|---|---|---|
| **Endianness** | The order of bytes of *a single multi-byte value* in memory or a data format | `0x01020304` can be `04 03 02 01` or `01 02 03 04` |
| **Alignment** | Which addresses are valid/suitable for placing an object or field; usually a multiple of a certain number of bytes | A 4-byte field may need to start at an offset divisible by 4 |
| **Padding** | Bytes inserted between fields or at the end of a `struct` to satisfy layout/alignment | After a 1-byte `char`, there may be 3 padding bytes before `uint32_t` |

An **ABI (Application Binary Interface)** is the set of binary conventions that separately compiled components must jointly follow. Depending on the platform, it can govern C type sizes/alignments, field placement, argument passing, return values, and calling conventions. The same C source code can still have a different layout under a different ABI or compiler configuration. CPU endianness alone is not enough to deduce the entire ABI either.

## 2. Endianness: Numeric Value and Byte Order

Suppose we want to store the 32-bit integer `0x01020304` into four consecutive bytes, with addresses increasing from left to right:

~~~text
Increasing address → +0  +1  +2  +3
Little-endian:       04  03  02  01
Big-endian:          01  02  03  04
Logical value:       0x01020304 (same)
~~~

- **Little-endian:** the least significant byte is at the lowest address. This is the common order on x86/x64 and many ARM systems running in little-endian mode.
- **Big-endian:** the most significant byte is at the lowest address. Many protocol formats define this order; the term *network byte order* usually refers to big-endian.
- Endianness **does not reverse the order of elements** in an array and **does not by itself change `struct` field offsets**. It determines how the bytes *within a single multi-byte value* are interpreted.
- For a single-byte value, there is no multi-byte ordering choice. Bit order within a byte or C bit-field layout is a separate matter; it should not be inferred from little-endian/big-endian.

For example, the bytes `01 02 03 04` read as a 32-bit unsigned integer yield:

~~~text
Big-endian:    0x01020304
Little-endian: 0x04030201
~~~

**Consequence:** a buffer written in little-endian but read in big-endian will produce the wrong value even when the byte count and offsets are exact. For data stored in files, networks, or wire protocols, specify endianness explicitly; do not implicitly rely on `ByteOrder.nativeOrder()`.

## 3. Alignment: Addresses and ABI Constraints

A C type has an alignment requirement. If `alignof(T) = A`, a valid address of an object of type `T` must satisfy that alignment constraint; on common ABIs, the address must usually be a multiple of `A`. For example, a field with alignment 4 usually sits at offset 0, 4, 8, 12, ... relative to the start of a properly aligned `struct`.

When laying out fields sequentially, a compiler typically applies the following calculation:

1. Place the first field's offset according to the type's layout.
2. Before each subsequent field, round the current offset up to a multiple of the alignment required by the ABI for that field.
3. After the last field, round the total size up to the alignment of the `struct` itself so that every element of an array of `struct`s is also aligned.

The general rounding function for a non-negative offset and `A > 0` is:

~~~text
align_up(offset, A) = ceil(offset / A) * A
~~~

For instance, `align_up(1, 4) = 4`, resulting in 3 padding bytes. On many ABIs, the alignment of a `struct` equals the largest alignment among its fields, but compilers, ABIs, and layout attributes can apply different constraints; **measure the actual struct**.

Accessing a C object through a pointer that does not satisfy the type's alignment can cause **undefined behavior**, even if on a particular CPU a misaligned access sometimes still runs. Some architectures raise a hardware fault; others run slower or the compiler optimizes based on the assumption that the address is properly aligned. Do not conclude that "it runs on my machine" means it is safe.

## 4. Internal Padding, Tail Padding, and True Size

Consider a C `struct`:

~~~c
struct Record {
    char tag;        // 1 byte if CHAR_BIT == 8
    uint32_t value;  // 4 bytes if CHAR_BIT == 8 and the type exists
    uint16_t code;   // 2 bytes if CHAR_BIT == 8 and the type exists
};
~~~

On a common ABI with `CHAR_BIT = 8`, where the alignment of `char` is 1, `uint32_t` is 4, and `uint16_t` is 2, the layout may be:

| Offset | Bytes | Contents |
|---:|---:|---|
| 0 | 1 | `tag` |
| 1–3 | 3 | **Internal padding** before `value` |
| 4–7 | 4 | `value` |
| 8–9 | 2 | `code` |
| 10–11 | 2 | **Tail padding** at the end of `struct` |

~~~text
Offset:  00 | 01 02 03 | 04 05 06 07 | 08 09 | 10 11
         tag|  padding |    value    |  code | padding
sizeof(struct Record) = 12 bytes; alignment is typically 4
Total useful field bytes = 1 + 4 + 2 = 7 bytes
~~~

**Internal padding** serves to align the following field. **Tail padding** serves to align the next element in an array: if `Record records[2]`, the second element typically starts at `base + 12`, not `base + 10` or `base + 7`. `sizeof(struct Record)` includes the padding and is the stride between array elements.

The numbers above are **examples under an assumed ABI**, not a fixed layout rule for every compiler. The types `uint32_t`/`uint16_t` come from `<stdint.h>` and are only present when the environment provides types of the exact width indicated by their names; C byte size also depends on `CHAR_BIT`. Do not assume `long`, `size_t`, pointers, or `enum` have the same size across all architectures: for example, 64-bit Windows commonly uses the LLP64 model, whereas many 64-bit Unix systems use LP64.

### Measuring with a C11 Program

Save the following code to `record.c`:

~~~c
#include <limits.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

struct Record {
    char tag;
    uint32_t value;
    uint16_t code;
};

int main(void) {
    printf("CHAR_BIT=%d\n", CHAR_BIT);
    printf("sizeof=%zu, align=%zu\n",
           sizeof(struct Record), _Alignof(struct Record));
    printf("offsets: tag=%zu, value=%zu, code=%zu\n",
           offsetof(struct Record, tag),
           offsetof(struct Record, value),
           offsetof(struct Record, code));
    return 0;
}
~~~

Compile with GCC or Clang supporting C11:

~~~bash
gcc -std=c11 -Wall -Wextra -pedantic record.c -o record
./record
~~~

A **common** output on x86-64 is:

~~~text
CHAR_BIT=8
sizeof=12, align=4
offsets: tag=0, value=4, code=8
~~~

If your machine prints different numbers, the layout measured by that environment is the data that must be used for native interoperability. `offsetof` takes the name of a normal member; do not use it to infer the offset of a C bit-field. Use `_Static_assert` when a specific ABI is a mandatory condition of the program, for example:

~~~c
_Static_assert(offsetof(struct Record, value) == 4,
               "Unexpected Record.value offset");
_Static_assert(sizeof(struct Record) == 12,
               "Unexpected Record size");
~~~

Place these checks in the source only when you **intentionally require** the 12-byte layout for the corresponding target; they cause compilation to fail early when the ABI mismatches, but they do not make that layout portable.

## 5. Seeing Both Endianness *and* Padding in the Same Buffer

Assume the ABI measures the 12-byte layout above, with `tag = 0x7A`, `value = 0x01020304`, and `code = 0x0506`. If `value` and `code` are represented in little-endian, we want the explicitly specified byte sequence as follows:

~~~text
Offset:  00 01 02 03 04 05 06 07 08 09 10 11
Byte:    7A 00 00 00 04 03 02 01 06 05 00 00
         └tag┘ pad   └─ value ───┘ └code┘ pad
~~~

Here the padding bytes are **deliberately set to 00 in the example format**. For an ordinary C `struct` object, padding bytes may contain indeterminate/unreliable values to be used as data: one should not treat all `sizeof(struct)` bytes as a stable serialization format. Compiler-generated padding and integer endianness are two separate decisions.

If we switch to big-endian while **keeping the field layout unchanged**, the offsets remain 0, 4, 8; only the bytes belonging to `value` and `code` change order:

~~~text
Offset:  00 01 02 03 04 05 06 07 08 09 10 11
Byte:    7A 00 00 00 01 02 03 04 05 06 00 00
~~~

You also need to check the size, signedness, and encoding convention of each field if Java and C exchange signed values, floating-point numbers, or non-fixed-width types.

## 6. Transparent Layout Mapping in Java 17 Using ByteBuffer

`ByteBuffer` lets you set endianness for multi-byte read/write operations, but **does not automatically add padding according to the C ABI**. We must use verified offsets. This example constructs the exact 12 bytes illustrated in little-endian in the previous section.

Save to `LayoutDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

public final class LayoutDemo {
    public static void main(String[] args) {
        ByteBuffer data = ByteBuffer.allocate(12)
                .order(ByteOrder.LITTLE_ENDIAN);

        // Offsets from the verified C layout: tag=0, value=4, code=8.
        // Memory is zero-initialized by allocate(), so the padding offsets are 00.
        data.put(0, (byte) 0x7A);
        data.putInt(4, 0x01020304);
        data.putShort(8, (short) 0x0506);

        for (int i = 0; i < data.capacity(); i++) {
            System.out.printf("%02X%s", data.get(i) & 0xFF,
                    i == data.capacity() - 1 ? "\n" : " ");
        }

        System.out.printf("value=0x%08X, code=0x%04X%n",
                data.getInt(4), data.getShort(8) & 0xFFFF);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac LayoutDemo.java
java LayoutDemo
~~~

Output:

~~~text
7A 00 00 00 04 03 02 01 06 05 00 00
value=0x01020304, code=0x0506
~~~

Clarifying common points of confusion:

- `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` controls how `short`, `int`, `long`, etc. are decoded/written; `put(int index, byte b)` writes only a single byte.
- `ByteBuffer` defaults to **BIG_ENDIAN** byte order; set it explicitly according to the data contract. `ByteOrder.nativeOrder()` only reflects the native order of the machine running Java, does not represent a protocol/file, and does not indicate padding.
- `data.putInt(4, ...)` writes starting at offset 4 precisely because **we chose 4**, not because `ByteBuffer` knows about `struct Record`. `putInt(1, ...)` on a heap buffer will also write bytes, but it will not match the measured C layout.
- Java's `byte` is a signed type, so use `data.get(i) & 0xFF` when printing byte values 0–255. For C's `uint16_t`, Java's `short` is also signed; `& 0xFFFF` lets you read the 16-bit unsigned value arithmetically.
- This is **building the bytes in Java**, which does not mean a Java heap `ByteBuffer` is a native pointer to the `struct`. To share real memory with C via JNI or the Foreign Function & Memory API, you must also adhere to lifetime, ownership, address, access safety, and the ABI of the native object.

In newer Java versions, the Foreign Function & Memory API (finalized in JDK 22) provides `MemoryLayout`, `MemorySegment`, and `ValueLayout`s to describe/read native memory. You must still explicitly specify size, alignment, byte order, and any required padding when modeling a C `struct`; do not guess the layout solely from Java type names.

## 7. Why Must You Not Write a `struct` Directly to a File or Network?

A C operation like:

~~~c
// Anti-pattern for a platform-independent file/network format:
fwrite(&record, sizeof record, 1, file);
~~~

may also write **internal/tail padding**. Padding contents are not meaningful fields, may not be stable across assignments, and risk containing unintended memory bytes. Furthermore, a raw dump carries the endianness, alignment, type sizes, and layout rules of the environment that produced it. A file created on ABI A will not necessarily be read correctly on ABI B, even if the `struct` name is the same.

Similarly, `memcmp(&a, &b, sizeof a) == 0` is not a reliable logical value comparison of two `struct`s: two objects with equal fields can still differ in their padding bytes. Compare each meaningful field individually.

**A better wire format:** define a sequential stream of fields rather than copying the `struct` directly. For example, `Record` can be encoded into **7 bytes**:

~~~text
Byte 0       : tag (1 byte)
Byte 1..4    : value (uint32, big-endian per protocol)
Byte 5..6    : code (uint16, big-endian per protocol)
Total        : 7 bytes; carries no C padding
~~~

This contract must clearly state size, byte order, signedness, string encoding (if any), version, and invalid-value handling. Both Java and C decode according to this contract without needing the same ABI. Conversely, if you must pass an **array of `struct`s in native memory**, you must obtain the exact C layout on the same target ABI and use a stride equal to `sizeof(struct Record)`.

## 8. Misaligned Access, Packed Structs, and Binary Data

### Misaligned Pointers

Do not arbitrarily cast the address of a byte array to a pointer with stricter alignment:

~~~c
// Wrong/unsafe: buf+1 may not be properly aligned for uint32_t.
uint32_t *p = (uint32_t *)(buf + 1);
uint32_t value = *p;
~~~

Even if the buffer has enough bytes, such a dereference can violate alignment or C's effective type rules. When reading bytes from a buffer, `memcpy` into a variable of the appropriate type avoids dereferencing a misaligned pointer:

~~~c
uint32_t value;
memcpy(&value, buf + 1, sizeof value); // buf must contain enough bytes
~~~

This `memcpy` approach only copies bytes: **it does not convert endianness**. If the data follows network byte order, decode the byte order explicitly or use an appropriate conversion API. Include `<string.h>` for `memcpy`.

### `packed` and Pragmas

`#pragma pack` (such as on MSVC) or `__attribute__((packed))` (such as on GCC/Clang) are compiler extensions. They can reduce/change padding and alignment, but they also change the layout contract, can create unaligned fields, and can cause slow/faulting accesses on some targets. Taking the address of a packed field as a normal-type pointer and dereferencing it is especially dangerous. Use them only when the binary specification and compiler/target are controlled, and then check `sizeof`, `offsetof`, and how the code actually accesses the fields.

### Bit-fields, Unions, and Environment-Dependent Types

C bit-field layout (allocation unit, bit order, spanning across boundaries) is implementation/ABI-dependent, so it is unsuitable for defining a portable protocol by dumping raw memory. A `union` shares storage among its members; interpreting reads must account for C rules and data representation, and cannot rely solely on endianness. Nor should you send `long`, pointers, `size_t`, or native `struct`s directly across system boundaries without standardizing width and layout.

## 9. Layout Verification Checklist for JNI/FFM or Binary Reading

1. **Identify the contract:** is the data a native in-memory ABI or a file/wire format? If it is a wire format, specify every byte independently of the ABI; if it is native, identify the OS, architecture, compiler, ABI/packing flags, and library version.
2. **Inspect the actual C:** measure `CHAR_BIT`, `sizeof(type)`, `_Alignof(type)`, `offsetof(type, field)`, and `sizeof(struct)`. For a mandatory native C format, place `_Static_assert`s for the confirmed offsets/sizes.
3. **Distinguish fields and padding:** build an offset–size–alignment table; for arrays, use the stride `sizeof(struct)`. Do not measure layout by summing field sizes.
4. **Agree on byte order:** specify the order for each multi-byte field; in Java, use `ByteBuffer.order(...)` or the corresponding layout/order. Do not interpret "native" as synonymous with "little-endian" on every machine.
5. **Read/write safely:** check bounds, alignment, signedness, and memory lifetime. For raw buffers, avoid misaligned pointer casts; for wire formats, encode/decode fields explicitly.
6. **Test with fixed sample bytes:** pick an easily recognizable value such as `0x01020304`, print a hex dump with offsets, cross-check a C ↔ Java sample, and verify padding/stride regions when needed.
7. **Test on another environment if supported:** change the target ABI/compiler/packing or the sample decode endianness; tests should fail clearly if a native assumption no longer holds.

## 10. Common Bugs and Diagnostics

| Symptom | Common Cause | How to Check/Fix |
|---|---|---|
| `0x01020304` becomes `0x04030201` | Read with the wrong endianness | Print a hex dump, set byte order explicitly |
| Java misreads from the second field onward | Forgot internal padding or offsets differ from ABI | Compare C `offsetof` with Java index |
| Second array element is wrong even though the first is right | Ignored tail padding | Use stride `sizeof(struct)`, not the sum of field sizes |
| Runs on x86 but fails/crashes on another target | Misaligned dereference or packed member | Check alignment, use `memcpy`/safe accessors |
| Two `struct`s have the same fields but `memcmp` differs | Padding contains different bytes | Compare meaningful fields |
| Binary file is misread on another system | Dumped raw struct; different endian/type size/ABI | Design a wire format with fixed widths and byte order |
| Enabling `#pragma pack` causes crash/changes native API | Field layout no longer matches library ABI | Remove arbitrary overrides; verify compile flags and offsets |

## 11. Practice Exercises

**Exercise 1 — predict and verify.** On an assumed ABI where `char` has align 1, `uint16_t` has align 2, and `uint32_t` has align 4, reorder the declarations to:

~~~c
struct CompactRecord {
    uint32_t value;
    char tag;
    uint16_t code;
};
~~~

Prediction: `value` at offset 0–3, `tag` at 4, one padding byte at 5, `code` at 6–7; `sizeof(struct CompactRecord) = 8` and alignment 4. Verify with a C program rather than treating `8` as a cross-platform guarantee. Lesson: **reordering fields can reduce padding**, but it also changes the ABI and is unsafe if the library on the other side still uses the old layout.

**Exercise 2 — reading bytes.** Given the sequence `11 22 33 44`, the 32-bit unsigned value is `0x11223344` in big-endian and `0x44332211` in little-endian. Try `ByteBuffer.wrap(new byte[]{0x11, 0x22, 0x33, 0x44})` and read `getInt()` after setting each byte order.

**Exercise 3 — choosing a contract.** A file needs to store `tag`, `value`, and `code` for both Java and C to read across multiple operating systems. Choose a 7-byte format with fixed endianness and describe the byte offsets. If the requirement changes to sharing a native `struct Record[]`, add the ABI parameters, assumed 12-byte layout, stride 12, alignment, lifetime, and a compatibility verification test suite.

## Key Takeaways

- **Endianness** answers "within a multi-byte number, which byte comes first?"; **alignment** answers "at which address does a field/object start?"; **padding** is the empty space added to satisfy the layout.
- `sizeof(struct)` can be larger than the sum of `sizeof` of its fields; `offsetof` and `_Alignof` are verification tools on the target, not an excuse to predict the layout of every ABI.
- Java's `ByteBuffer` does not model a C `struct` automatically. Offsets, byte order, field widths, and padding must be agreed upon and verified.
- Data that must persist across files/networks should have an **ABI-independent wire format**. Sharing native objects in memory requires a strict ABI contract and actual verification.
