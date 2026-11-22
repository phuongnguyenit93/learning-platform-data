# Choosing the Right Byte Order for Native Data or File Formats

## 1. Why does byte order matter when working with MemorySegment?

In the Java FFM API (Foreign Function & Memory API), a `MemorySegment` is a memory region made up of **bytes**. To read or write a multi-byte value — such as `short`, `int`, `long`, `float`, or `double` — the program needs to know **what order the bytes are arranged in**. That order is called *byte order* or *endianness*.

A 32-bit integer value has the same mathematical value, but can be represented in memory as follows:

```text
Logical value: 0x12345678 (4 bytes)

BIG_ENDIAN:
byte position   0     1     2     3
               12    34    56    78
               ↑                 ↑
     most significant byte   least significant byte

LITTLE_ENDIAN:
byte position   0     1     2     3
               78    56    34    12
               ↑                 ↑
     least significant byte  most significant byte
```

If the four bytes `12 34 56 78` are **read as big-endian**, the resulting value is `0x12345678`. If those same four bytes are **read as little-endian**, the value is `0x78563412`. There is no bounds error or mandatory exception: the software may receive **a valid number with the wrong meaning**.

Therefore, the right question is not “is my computer using little-endian or big-endian?”, but rather:

> **Under what convention are the bytes being read/written defined: the native ABI of the process, a fixed file format, or a data transmission protocol?**

The answer determines whether to use `ByteOrder.nativeOrder()`, `ByteOrder.BIG_ENDIAN`, or `ByteOrder.LITTLE_ENDIAN`.

**Version:** The FFM code in this article uses `java.lang.foreign`, finalized in **JDK 22** (JEP 454). Java 17 does not have the same stable API; examples requiring only `ByteBuffer` can run on JDK 17+, whereas `MemorySegment` examples require **JDK 22+**. This is advanced Java content on memory/native interoperability, not a claim that every JDK 17 can compile `java.lang.foreign`.

## 2. Three byte order types and selection rules

`java.nio.ByteOrder` provides:

- `ByteOrder.BIG_ENDIAN`: the *most significant byte* comes first at the lower address.
- `ByteOrder.LITTLE_ENDIAN`: the *least significant byte* comes first at the lower address.
- `ByteOrder.nativeOrder()`: returns the byte order **of the platform the JVM is running on**; the return value is one of the two constants above.

| Data source | Byte order to choose | Why |
| --- | --- | --- |
| A C `int32_t` written directly by a native library into memory in the same process | Usually `nativeOrder()` | The C compiler/CPU represents integer scalars according to the platform's ABI; type and alignment must also match |
| A native library whose public ABI specifies that a field is always big-endian | `BIG_ENDIAN` | The specific **ABI contract** takes precedence over CPU architecture |
| A file format that specifies 32-bit integers in big-endian form | `BIG_ENDIAN` | The file must be read consistently on every machine |
| A file format that specifies 32-bit integers in little-endian form | `LITTLE_ENDIAN` | Independent of the machine running Java |
| A packet/protocol that defines “network byte order” by standard convention | Usually `BIG_ENDIAN`, if that protocol specifies it | Must rely on the protocol specification, not assume all protocols are big-endian |
| A memory region received from a native API whose documentation does not state endianness/ABI | **Insufficient information to choose** | Must check the contract or exchange protocol |
| A 1-byte data sequence (`byte`, ASCII/UTF-8 byte stream) | Endianness does not affect individual bytes | Byte order only has meaning when combining **multiple bytes** into a single value |

**Design rule:** byte order is **a property of the data/field by contract**. You should not assign `nativeOrder()` just because the application is running on an x86 machine or because “native” appears in the API name.

### 2.1. What does native byte order mean?

On many x86-64 CPUs, `ByteOrder.nativeOrder()` is `LITTLE_ENDIAN`; however, Java still supports other environments. Do not write code assuming **every** JVM is little-endian.

```java
import java.nio.ByteOrder;

System.out.println(ByteOrder.nativeOrder());
```

This is a fragment from a valid Java snippet if placed inside a method; the output depends on the platform, so there is no fixed stdout common to all machines.

Native order is typically useful for **memory-mapped or shared memory of a native program running under the same ABI**, especially when both sides directly exchange an array of C and Java scalars. It is **not enough** to prove that an arbitrary `struct` is compatible: there are also `sizeof`, padding, alignment, `long`/`size_t` types, enums, booleans, ABI, and pointer lifetimes.

### 2.2. Fixed endianness for file formats and network protocols

A file written on a little-endian machine may be opened years later on a big-endian machine. If the file format specifies a big-endian `uint32`, Java must read it using big-endian **on both machines**. Conversely, if the file specifies little-endian, the layout must be fixed to little-endian.

You should not save a file by simply calling `fwrite(&someInt, sizeof someInt, 1, file)` on the C side and assuming the file is portable. That writes bytes in the native representation; when moving across platforms, the file can be misinterpreted. If you want a durable format, **choose a documented on-disk convention** and encode/decode properly at the boundary.

## 3. How to represent byte order with ValueLayout

FFM uses `ValueLayout` to interpret bytes according to a specific Java type. In JDK 22+:

```java
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

// 4-byte int layout in native byte order.
ValueLayout.OfInt nativeInt = ValueLayout.JAVA_INT;

// Same width and int carrier, but fixed to BIG_ENDIAN.
ValueLayout.OfInt bigInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN);

// Same width and int carrier, but fixed to LITTLE_ENDIAN.
ValueLayout.OfInt littleInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.LITTLE_ENDIAN);
```

This is a **variable declaration fragment** that can be placed inside a Java method. `JAVA_INT` has `byteSize() == 4` and `order() == ByteOrder.nativeOrder()`. `withOrder(order)` returns **a new layout**, does not modify the data in `MemorySegment`, and does not mutate the original layout.

Access example:

```java
int value = segment.get(bigInt, 0L);
segment.set(littleInt, 4L, 0x12345678);
```

`get(layout, offset)` and `set(layout, offset, value)` use a **byte offset** relative to the start of the current segment. On the first line, `get(bigInt, 0)` reads from byte 0 as big-endian; the second line writes 4 bytes starting at offset 4 as little-endian.

### 3.1. Byte order is a property of the *access*, not of the entire segment

A `MemorySegment` only provides bytes and access constraints. The same segment can be accessed with multiple layouts:

```java
int bigValue = segment.get(bigInt, 0L);
int littleValue = segment.get(littleInt, 0L);
```

The two variables can hold different values even at the same address. **There is no data copy or permanent byte swap** when calling `withOrder`. Each `get` interprets the existing bytes according to the chosen layout; each `set` encodes the value according to that layout.

A file header can also contain multiple fields with different endianness. You are allowed to use `bigInt` for field A and `littleInt` for field B if the format documentation specifies it.

### 3.2. `order()` tells which order a layout is using

```java
ByteOrder order = ValueLayout.JAVA_INT.order();
boolean matchesHost = order == ByteOrder.nativeOrder();
```

This is a fragment. `matchesHost` is always `true` for the standard `JAVA_INT` layout on that JVM, whereas:

```java
ByteOrder fileOrder =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.BIG_ENDIAN).order();
```

gives `BIG_ENDIAN` on every platform. Do not infer byte order from `segment.byteSize()` or a memory address; **bytes do not carry metadata saying whether they are big- or little-endian**.

### 3.3. Types where byte order is meaningful

| Layout | Width | Example meaning |
| --- | ---: | --- |
| `ValueLayout.JAVA_BYTE` | 1 byte | A single byte does not change when switching endianness |
| `ValueLayout.JAVA_SHORT` | 2 bytes | How a 16-bit number is interpreted from two bytes |
| `ValueLayout.JAVA_CHAR` | 2 bytes | A UTF-16 code unit; not synonymous with the encoding of an entire string |
| `ValueLayout.JAVA_INT` | 4 bytes | 32-bit integer |
| `ValueLayout.JAVA_LONG` | 8 bytes | 64-bit integer |
| `ValueLayout.JAVA_FLOAT` | 4 bytes | 32-bit IEEE 754 as used by Java |
| `ValueLayout.JAVA_DOUBLE` | 8 bytes | 64-bit IEEE 754 as used by Java |
| `ValueLayout.ADDRESS` | Platform-dependent | Native address; **not a portable file field** |

Byte order only controls **the order of the bytes of a single value**. It does not change the number of bytes of the value, the Java carrier type, the offset position, or the element count. For pointers, `size_t`, and C `long`, you must consider the ABI, not just endianness.

## 4. Java 22+ example: same value, two different byte sequences

This standalone example uses `MemorySegment.ofArray(new byte[8])` to view a byte array directly. It writes the same value `0x12345678` as big-endian and little-endian in turn, then prints the bytes and the result when intentionally reading with the wrong order.

Because the backing memory is `byte[]`, **the maximum alignment for this heap segment is 1 byte**. Therefore we use `JAVA_INT_UNALIGNED` instead of `JAVA_INT`. Choosing `UNALIGNED` **does not change the 4-byte width**, it only relaxes alignment; byte order is still determined by `withOrder`.

### 4.1. File `EndianMemorySegmentDemo.java`

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.Locale;

public class EndianMemorySegmentDemo {
    public static void main(String[] args) {
        byte[] bytes = new byte[8];
        MemorySegment segment = MemorySegment.ofArray(bytes);

        ValueLayout.OfInt big =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);
        ValueLayout.OfInt little =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.LITTLE_ENDIAN);

        int number = 0x12345678;

        // First region: 4 big-endian bytes.
        segment.set(big, 0L, number);

        // Second region: 4 little-endian bytes.
        segment.set(little, 4L, number);

        String hexBytes = HexFormat.ofDelimiter(" ")
                .withUpperCase().formatHex(bytes);
        System.out.println("bytes: " + hexBytes);

        System.out.printf(Locale.ROOT,
                "big @0: %08X%n", segment.get(big, 0L));
        System.out.printf(Locale.ROOT,
                "little @4: %08X%n", segment.get(little, 4L));

        // Intentionally read big-endian bytes using a little-endian layout.
        System.out.printf(Locale.ROOT,
                "wrong order @0: %08X%n", segment.get(little, 0L));
    }
}
```

**Build and run with JDK 22+:**

```bash
javac EndianMemorySegmentDemo.java
java EndianMemorySegmentDemo
```

**Expected stdout, independent of the machine's byte order:**

```text
bytes: 12 34 56 78 78 56 34 12
big @0: 12345678
little @4: 12345678
wrong order @0: 78563412
```

### 4.2. Why is the output platform-independent?

- `big` and `little` are both layouts **with fixed order**, independent of `nativeOrder()`.
- `set(big, 0L, number)` writes `12 34 56 78` into bytes 0..3.
- `set(little, 4L, number)` writes `78 56 34 12` into bytes 4..7.
- `get(big, 0L)` and `get(little, 4L)` reconstruct the same Java value `0x12345678`.
- `get(little, 0L)` attempts to read the sequence `12 34 56 78` as little-endian; it gets `0x78563412` — a **semantically wrong value**, not a memory safety error.
- `HexFormat` prints **each byte intact**, using hex notation to make the bytes clearly visible. It does not automatically reverse the byte order of multi-byte integers.

No JNI calls or `Arena` are needed for this example because it only demonstrates the FFM view of a `byte[]` array. For real native memory, you can use `Arena.allocate`; the `withOrder` rule remains the same.

## 5. Native data: when to choose ByteOrder.nativeOrder()?

When exchanging data directly with a native library in the same process, a C/C++ program may provide a memory region containing an `int32_t` array according to the platform ABI. When **the native API contract guarantees** that the elements use the current machine's representation, Java can read:

```java
var nativeInt = ValueLayout.JAVA_INT;
int first = segment.getAtIndex(nativeInt, 0);
int second = segment.getAtIndex(nativeInt, 1);
```

This is a fragment assuming `segment` points to live memory of sufficient size, proper alignment, read permission, and stores valid native 32-bit integers. `ValueLayout.JAVA_INT.order()` is already `ByteOrder.nativeOrder()`, so `withOrder(nativeOrder())` is not needed unless you want to express intent explicitly.

You can write it explicitly:

```java
ValueLayout.OfInt nativeInt =
        ValueLayout.JAVA_INT.withOrder(ByteOrder.nativeOrder());
```

**Important:** “native data” does not mean every value in native memory uses native order. For example, native code reads a big-endian file into a `uint8_t *` buffer and **has not decoded it yet**; the buffer still contains **big-endian bytes** even though it resides in the RAM of a little-endian machine. Java must read according to **the actual byte format in the buffer**, not according to the language that allocated it.

### 5.1. Distinguishing *native scalar* and *opaque byte buffer*

Suppose a C API returns:

```c
/* C fragment: assumes out has been allocated large enough. */
uint32_t value = 0x12345678u;
memcpy(out, &value, sizeof(value));
```

If `uint32_t` exists and the C API genuinely returns bytes from the object representation of this native value, the byte order is the platform's native order. The Java side receiving the buffer must use the corresponding layout (and know the exact byte count/type).

Another API returns:

```c
/* C fragment: writes standard big-endian regardless of CPU. */
out[0] = 0x12;
out[1] = 0x34;
out[2] = 0x56;
out[3] = 0x78;
```

The memory may likewise have been created with `malloc`, but **the byte contract has changed**. Java must use `BIG_ENDIAN`. If you only know that `out` is a “native pointer” without knowing which side produced the data under what rule, there is not enough information to decode it correctly.

`memcpy` in the example does not byteswap automatically; it copies the bytes of the source variable. Conversely, `segment.get(layout, offset)` interprets bytes based on the specific layout and returns a Java value, decoupled from the representation order of the Java caller's machine.

### 5.2. For native structs, byte order is only part of the ABI

A C `struct` can have ABI-dependent padding, alignment, and field sizes. For example, a struct with `uint8_t kind` followed by `uint32_t count` usually requires padding before `count` on many ABIs. Choosing the right endianness for `count` **is not enough** if Java reads at the wrong offset.

When describing a C struct, you should verify:

1. Field sizes: `uint32_t` differs from `unsigned long`, `size_t`, and pointers; do not map all of them to Java `int`.
2. Offsets/padding: determine via the ABI/`offsetof`/library headers, rather than guessing by addition without considering alignment.
3. Byte order of **each scalar field**, especially if the struct contains a network-order buffer handled separately.
4. Lifetime and ownership of the native memory region; `MemorySegment` does not automatically keep a C pointer alive indefinitely.
5. Read/write permissions and thread access of the segment, especially during callbacks from native threads.

If an external format requires high portability, it is usually better to define an **explicit serialization layout**, rather than dumping C structs directly to a file.

## 6. File formats: fixing endianness per field

Suppose a hypothetical file format has a 12-byte header with the following specification:

| Byte offset | Length | Field name | Type/byte order |
| ---: | ---: | --- | --- |
| 0 | 4 | `magic` | 4 ASCII bytes `DMO1`, unrelated to endianness |
| 4 | 2 | `version` | Unsigned 16-bit **little-endian** |
| 6 | 2 | `flags` | Unsigned 16-bit **big-endian** |
| 8 | 4 | `payloadLength` | Unsigned 32-bit **big-endian** |

This format intentionally uses mixed endianness to show that **byte order is a field-level contract**, not a single property of the file or CPU.

Header bytes:

```text
offset:   00 01 02 03   04 05   06 07   08 09 10 11
hex:      44 4D 4F 31   01 02   A0 B1   00 00 01 00
meaning:  D  M  O  1    version  flags   payload length

version bytes 01 02 (little) -> 0x0201 = 513
flags   bytes A0 B1 (big)    -> 0xA0B1
length  bytes 00 00 01 00    -> 0x00000100 = 256
```

### 6.1. File `MixedEndianHeader.java`

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public class MixedEndianHeader {
    public static void main(String[] args) {
        byte[] header = {
                0x44, 0x4D, 0x4F, 0x31,
                0x01, 0x02,
                (byte) 0xA0, (byte) 0xB1,
                0x00, 0x00, 0x01, 0x00
        };

        if (header.length != 12) {
            throw new IllegalArgumentException(
                    "expected 12-byte header");
        }

        MemorySegment segment = MemorySegment.ofArray(header);

        // byte[] heap segment: use UNALIGNED layout, alignment 1.
        ValueLayout.OfShort shortLittle =
                ValueLayout.JAVA_SHORT_UNALIGNED
                        .withOrder(ByteOrder.LITTLE_ENDIAN);
        ValueLayout.OfShort shortBig =
                ValueLayout.JAVA_SHORT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);
        ValueLayout.OfInt intBig =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);

        String magic = new String(
                header, 0, 4, StandardCharsets.US_ASCII);
        int version = Short.toUnsignedInt(
                segment.get(shortLittle, 4L));
        int flags = Short.toUnsignedInt(
                segment.get(shortBig, 6L));
        long payloadLength = Integer.toUnsignedLong(
                segment.get(intBig, 8L));

        System.out.println("magic: " + magic);
        System.out.println("version: " + version);
        System.out.printf(Locale.ROOT, "flags: %04X%n", flags);
        System.out.println("payload length: " + payloadLength);
    }
}
```

**JDK 22+ commands:**

```bash
javac MixedEndianHeader.java
java MixedEndianHeader
```

**Expected stdout:**

```text
magic: DMO1
version: 513
flags: A0B1
payload length: 256
```

### 6.2. Points to verify when reading a real header

- The `magic` field is treated as **four ASCII bytes**, and must not be “byteswapped” into an integer just because the CPU is little-endian.
- `version` is little-endian, so `01 02` means `0x0201`, not `0x0102`.
- `flags` is big-endian. Because Java `short` is **signed**, `Short.toUnsignedInt` interprets the 16 bits as unsigned as specified by the file format.
- `payloadLength` is also big-endian. Java `int` is signed, so use `Integer.toUnsignedLong` when the header specifies **uint32**. If `int` is used directly, values larger than `Integer.MAX_VALUE` will appear negative.
- The example only contains the **header**, not an actual payload. It demonstrates how to read the length, **not claiming** that 256 payload bytes are present after the header.

When processing real files, you must check that **the file/header has enough bytes** *before* reading each field, and validate `payloadLength` against the remaining bytes, size-limit policies, and overflow before allocating. Some dangerous mismatches do not throw an exception immediately when reading the header — for instance, a length interpreted with the wrong endianness may still be a very large positive number.

### 6.3. Two separate concerns: byte order and unsignedness

Byte order answers the question “how are the bytes arranged?”, whereas **signed/unsigned** answers “is the bit pattern interpreted as a negative number or not?”. Choosing `BIG_ENDIAN` correctly but forgetting unsigned conversion can still produce wrong values when reading large `uint16`/`uint32` values.

Example:

```java
short rawFlags = segment.get(shortBig, 6L);
int flagsUnsigned = Short.toUnsignedInt(rawFlags);

int rawLength = segment.get(intBig, 8L);
long lengthUnsigned = Integer.toUnsignedLong(rawLength);
```

This is a **fragment**, using the `segment`/`shortBig`/`intBig` variables from section 6. `Short.toUnsignedInt` and `Integer.toUnsignedLong` **do not change endianness**; they only interpret the same bit pattern as unsigned in a wider Java type.

## 7. Struct/file layouts with per-field byte order

For a record with fixed integer fields, we can attach `withOrder` directly to leaf layouts:

```java
import java.lang.foreign.MemoryLayout;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;

var fileRecord = MemoryLayout.structLayout(
        ValueLayout.JAVA_SHORT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN).withName("type"),
        ValueLayout.JAVA_SHORT_UNALIGNED
                .withOrder(ByteOrder.LITTLE_ENDIAN).withName("flags"),
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN).withName("length")
);

long lengthOffset = fileRecord.byteOffset(
        MemoryLayout.PathElement.groupElement("length"));
```

This is a **fragment inside a Java method**, assuming imports are placed at the top of the file. The layout above uses field widths 2+2+4 = 8 bytes, all intentionally `UNALIGNED` for a packed-file format. `lengthOffset` is **4 bytes** from the start of the record; the byte order of `length` is big-endian, independent of the little-endian `flags`.

In other formats that have padding, you must not omit padding just to “make it fit”. `MemoryLayout.structLayout` describes members in the declared order; it **does not automatically insert all padding for every C ABI**. For real C struct data, verify the compiler's offsets/layout and use `MemoryLayout.paddingLayout(...)` when needed.

### 7.1. Record stride and endianness are two independent axes

For example, a `uint32_t value` field sits at byte offset 8 of each 16-byte record. The `i`-th record element has byte offset:

```text
recordOffset = i * 16
valueOffset  = recordOffset + 8
```

If the file specifies the field as big-endian:

```java
long valueByteOffset = Math.addExact(
        Math.multiplyExact(recordIndex, 16L), 8L);

int raw = segment.get(
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN),
        valueByteOffset);
long value = Integer.toUnsignedLong(raw);
```

This is a fragment assuming `recordIndex` and `segment` are valid. `Math.multiplyExact`/`Math.addExact` catch overflow; `get` checks bounds, alignment, and lifetime. Even with the right endianness, if the record stride/field offset is wrong, you will still read **the wrong bytes**.

**Do not use `getAtIndex(JAVA_INT, recordIndex)` to automatically apply a stride of 16**. `getAtIndex` scales by `layout.byteSize()`, which is 4 for `JAVA_INT`. It does not know that the domain record is 16 bytes long.

### 7.2. When does endianness not matter?

For **byte sequences or opaque payloads**, there is no need to convert endianness byte by byte. For example, a 4-byte `magic` field, a JPEG image, a UTF-8 string, or a compressed buffer — read as a sequence of bytes, not as multi-byte `int`s (unless the format specifies particular multi-byte fields). Byte order also **does not reverse character order in strings**.

Conversely, **UTF-16** has rules for storing multi-byte code units and may involve BOM/big-endian/little-endian. In that case, use the charset decoder matching the format specification; do not pick an arbitrary `JAVA_CHAR` layout and assume it correctly interprets every text file.

## 8. MemorySegment and ByteBuffer: an easy-to-miss default difference

**`ByteBuffer` has a default byte order of `BIG_ENDIAN`.** `ValueLayout.JAVA_INT` and FFM's standard primitive layouts, by contrast, have a default byte order of **`ByteOrder.nativeOrder()`**. Consequently, **the two APIs can interpret the same bytes differently when unconfigured**.

Comparison:

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

byte[] data = {0x12, 0x34, 0x56, 0x78};

// ByteBuffer defaults to BIG_ENDIAN.
int fromBuffer = ByteBuffer.wrap(data).getInt();

// FFM JAVA_INT_UNALIGNED defaults to nativeOrder.
int fromSegment = MemorySegment.ofArray(data)
        .get(ValueLayout.JAVA_INT_UNALIGNED, 0);

// Fix FFM to BIG_ENDIAN to match ByteBuffer's default:
int portable = MemorySegment.ofArray(data).get(
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN), 0);
```

This is a **fragment**; `fromBuffer` and `portable` are both `0x12345678`, while `fromSegment` depends on the host byte order. On a little-endian host, `fromSegment` is `0x78563412`. Do not assume APIs “within the same JVM” share the same default endianness.

If you want a little-endian `ByteBuffer`:

```java
ByteBuffer view = ByteBuffer.wrap(data)
        .order(ByteOrder.LITTLE_ENDIAN);

int fromLittle = view.getInt(0); // 0x78563412
```

`ByteBuffer.order(...)` changes how the buffer's **view** reads/writes primitive values. It does not directly reverse existing bytes. Similarly, `ValueLayout.withOrder(...)` creates a **new layout**, and likewise does not change bytes in memory until a `set` occurs.

### 8.1. Do not byteswap twice

A common mistake:

1. Read big-endian data using `get(BIG_ENDIAN, offset)` — Java already has **the correct logical value**.
2. Call `Integer.reverseBytes(value)` as well, thinking you must “convert from big to little”.
3. The result gets reversed a second time and becomes wrong.

If accessed via FFM with the right layout, **the API has already interpreted the bytes according to the specified order**. `Integer.reverseBytes` is only useful in cases where code genuinely needs to reverse **the bit pattern of a number**; it is not a required step after `get(...withOrder(...))`.

Similarly, `MemorySegment.copy(...)` or copying `byte[]`/`ByteBuffer` bytewise **does not automatically convert endianness**. If you want to convert a sequence of ints from big-endian to little-endian, you must **read each value with a big-endian layout and write it with a little-endian layout** (or an appropriate conversion algorithm), not merely copy bytes from source to destination.

## 9. Example of converting encoding between two memory regions

Goal: the source contains two big-endian encoded int values; the destination must contain **the same two logical values** in little-endian. Independent of the machine running the code.

**File `EndianConversion.java` (JDK 22+):**

```java
import java.lang.foreign.MemorySegment;
import java.lang.foreign.ValueLayout;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.Locale;

public class EndianConversion {
    public static void main(String[] args) {
        byte[] source = {
                0x01, 0x02, 0x03, 0x04,
                0x11, 0x22, 0x33, 0x44
        };
        byte[] destination = new byte[source.length];

        MemorySegment input = MemorySegment.ofArray(source);
        MemorySegment output = MemorySegment.ofArray(destination);

        ValueLayout.OfInt be =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.BIG_ENDIAN);
        ValueLayout.OfInt le =
                ValueLayout.JAVA_INT_UNALIGNED
                        .withOrder(ByteOrder.LITTLE_ENDIAN);

        long count = source.length / be.byteSize();
        for (long index = 0; index < count; index++) {
            int value = input.getAtIndex(be, index);
            output.setAtIndex(le, index, value);
        }

        System.out.println("source: " +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(source));
        System.out.println("result: " +
                HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(destination));

        System.out.printf(Locale.ROOT, "first value: %08X%n",
                output.getAtIndex(le, 0));
        System.out.printf(Locale.ROOT, "second value: %08X%n",
                output.getAtIndex(le, 1));
    }
}
```

**Commands:**

```bash
javac EndianConversion.java
java EndianConversion
```

**Expected stdout:**

```text
source: 01 02 03 04 11 22 33 44
result: 04 03 02 01 44 33 22 11
first value: 01020304
second value: 11223344
```

Why: `getAtIndex(be, index)` reads each logical value from source; `setAtIndex(le, index, value)` writes that value in little-endian byte order. The destination byte sequence is **different**, while the logical values when read with the right endianness **match** the source.

The example assumes the byte count is divisible by 4; for real inputs you must check the length/element count, verify sufficient data, and enforce resource limits before allocating. If a file contains fields of different sizes, you cannot “swap the entire file in 4-byte blocks”: you must read per the schema for each field to avoid reversing headers, padding, strings, or unrelated payloads.

## 10. Alignment and memory bounds: a separate issue, not endianness

`ValueLayout` also holds:

- `byteSize()`: how many bytes the value uses.
- `byteAlignment()`: the byte boundary the access position must be aligned to.
- `order()`: interprets bytes as big/little/native.
- `carrier()`: the Java type such as `int.class`, `long.class`.

**`withOrder` does not automatically relax alignment.** For example:

```java
var beInt = ValueLayout.JAVA_INT
        .withOrder(ByteOrder.BIG_ENDIAN);
```

still has 4-byte alignment. For `MemorySegment.ofArray(new byte[4])`, the maximum alignment of a heap segment backed by `byte[]` is only 1, so accessing with `beInt` can throw `IllegalArgumentException` even at offset 0.

The right way to read a packed-file header from `byte[]`:

```java
var beIntUnaligned = ValueLayout.JAVA_INT_UNALIGNED
        .withOrder(ByteOrder.BIG_ENDIAN);

int value = MemorySegment.ofArray(
        new byte[] {0x01, 0x02, 0x03, 0x04})
        .get(beIntUnaligned, 0L); // 0x01020304
```

This is a fragment, not a standalone Java file. Use `*_UNALIGNED` only when the data requires/allows a packed layout; in some cases unaligned access has performance costs or platform restrictions, especially when interfacing directly with a native ABI.

### 10.1. Non-negotiable checks

| Constraint | Check |
| --- | --- |
| Byte offset | `0 <= offset` and `offset + layout.byteSize() <= segment.byteSize()`, avoiding overflow when adding manually |
| Element index | `getAtIndex` multiplies `index * layout.byteSize()`, not by struct length if different |
| Alignment | Access address satisfies `layout.byteAlignment()`; unaligned layouts may be used when the data contract permits |
| Lifetime | `Arena` or backing scope is still alive; using after close may throw `IllegalStateException` |
| Thread confinement | Confined arena/segment must be accessed from the allowed thread, otherwise may throw `WrongThreadException` |
| Write permission | `set` on a read-only segment is invalid |
| Unsignedness | Use `Short.toUnsignedInt`/`Integer.toUnsignedLong` when the file specifies unsigned fields |
| Byte order | Always take from **the field/protocol/ABI specification**, not from guessing the CPU |
| Data type | A 4-byte `int` and a 4-byte `float` have the same size but different bit-pattern meanings |

A wrong-endian result may **not throw any exception**, whereas bounds/alignment/lifetime errors usually raise corresponding exceptions. Therefore, byte order testing must rely on **fixed sample bytes and expected numeric values**, not merely on whether the code “runs”.

## 11. Common mistakes

| Mistake | Consequence | How to fix |
| --- | --- | --- |
| Reading a big-endian file with default `JAVA_INT` | Receives wrong numbers on a little-endian host | `JAVA_INT[_UNALIGNED].withOrder(BIG_ENDIAN)` |
| Reading a native scalar buffer with `BIG_ENDIAN` on every CPU | Wrong when the native ABI is little-endian | Use layout matching the native contract/`nativeOrder()` |
| Assuming `ByteBuffer` and `ValueLayout.JAVA_INT` share the same order | Same bytes yield different values | Specify explicit order in both APIs |
| Assuming `withOrder` reverses bytes in `MemorySegment` | Data is unchanged, only interpretation changes | `get` with the right order, `set` with target order if re-encoding |
| Calling `Integer.reverseBytes` after `get(BIG_ENDIAN)` | Reverses a second time, producing wrong result | Do not swap again if the layout is already right |
| Reading `uint32` then processing as a negative `int` | Wrong size/length when value exceeds 2^31-1 | `Integer.toUnsignedLong` |
| Using `JAVA_INT` on packed `byte[]` | Alignment violation | `JAVA_INT_UNALIGNED` then `withOrder` |
| Fixing only endianness, ignoring C struct padding | Reads the wrong field despite right endianness | Use offsets/layout matching the ABI |
| Splitting a file into 4-byte blocks and reversing every block | Corrupts strings, padding, and differently sized fields | Decode/encode per field according to schema |
| Saving a file with native `fwrite` and expecting portability | Bytes vary by ABI/endianness | Choose a fixed-endian file specification |
| Trusting Java `char`/file `String` to follow FFM endianness automatically | Confuses text encoding with primitive layouts | Use the right charset (UTF-8/UTF-16LE/BE...) |
| Using native order on data already converted to network order | Data has a standardized order different from CPU | Choose order according to the standardized data protocol |

### 11.1. Confusing endianness with offset

Suppose a 16-byte segment has an 8-byte header and a 4-byte big-endian number at offset 8. Reading with `get(BIG_ENDIAN, 0)` is still wrong because the position is wrong; reading with `get(LITTLE_ENDIAN, 8)` is also wrong because the order is wrong. A correct access needs **both position and order**:

```java
long byteOffset = 8L;
int number = segment.get(
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN),
        byteOffset);
```

This is a fragment in a context that already has `segment`. With `getAtIndex`, the index is multiplied by `layout.byteSize()`; do not use a byte offset as an element index. Endianness does not change index multiplication.

### 11.2. Confusing endianness with bit order or network-bit-stream encoding

Byte order determines **the positions of the bytes of a scalar**. It **does not define bit order within each byte**, C bitfield packing, or how a codec compresses data. If a wire format has bitfields like “3-bit type + 5-bit flags”, you must use mask/shift operations per the specification; `withOrder` does not parse bitfields.

Similarly, a UTF-8 string is a byte sequence with its own encoding. Do not reverse the bytes of UTF-8 characters according to `nativeOrder()`. For UTF-16 files, rely on the BOM or the format's `UTF-16BE`/`UTF-16LE` specification.

## 12. Decision workflow when receiving a native buffer or file

Before choosing a layout to read data:

1. **Identify the source:** C scalar memory in the same process, buffer holding a file, network payload, or native struct.
2. **Read the schema:** how many bytes wide each field is, signed/unsigned, endianness, base offset, record stride, and padding.
3. **Choose byte order by contract:** `nativeOrder()` only for data genuinely using native representation; if the format is fixed, use `BIG_ENDIAN`/`LITTLE_ENDIAN` per the documentation.
4. **Choose the right `ValueLayout`:** `JAVA_SHORT`/`JAVA_INT`/`JAVA_LONG`...; for heap `byte[]` or packed data, consider `*_UNALIGNED` layouts.
5. **Check size/bounds/alignment/lifetime:** do not allocate based on an unvalidated length value. Mind signedness.
6. **Read/write with an explicit layout:** `segment.get(layout, byteOffset)` or `getAtIndex(layout, elementIndex)`; do not mix byte offsets and element indices.
7. **Verify against golden bytes:** test a value like `0x12345678` to get clearly distinct bytes; also test data with bytes 0x80 and above, large lengths, and truncated files.
8. **Test on at least two environments when possible:** little-endian hosts are common, but fixed-endian tests can ensure portability even without a big-endian machine.
9. **Make the contract explicit in the API:** name variables `bigEndianInt`, `fileOrder`, `nativeIntLayout`; avoid a generic `layout` variable reused for fields of different order.

A well-designed API might define:

```java
private static final ValueLayout.OfInt FILE_INT32_BE =
        ValueLayout.JAVA_INT_UNALIGNED
                .withOrder(ByteOrder.BIG_ENDIAN);

private static final ValueLayout.OfShort FILE_UINT16_LE =
        ValueLayout.JAVA_SHORT_UNALIGNED
                .withOrder(ByteOrder.LITTLE_ENDIAN);
```

This is a fragment belonging to a class with `ValueLayout`/`ByteOrder` imports. These constants encode **the file format contract**, avoiding platform dependence and avoiding changing layouts on every read.

## 13. Self-check questions

**Question 1.** What two results do the four bytes `12 34 56 78` produce when read as big-endian and little-endian?  
**Answer:** Big-endian `0x12345678`, little-endian `0x78563412`. Byte order changes how the same bytes are **interpreted**.

**Question 2.** What is the default byte order of `ValueLayout.JAVA_INT`?  
**Answer:** `ByteOrder.nativeOrder()`. Do not assume it is always little-endian on every JVM.

**Question 3.** A file stores 32-bit numbers in big-endian, and the application runs on little-endian x86-64. Should you use `nativeOrder()` for better performance?  
**Answer:** No. The file format specifies `BIG_ENDIAN`, so use `ValueLayout.JAVA_INT_UNALIGNED.withOrder(BIG_ENDIAN)` if the buffer is a packed `byte[]`; correctness matters more than native defaults.

**Question 4.** Can `MemorySegment.ofArray(new byte[4]).get(ValueLayout.JAVA_INT, 0)` fail even with offset 0 and enough bytes?  
**Answer:** Yes. A heap segment from `byte[]` only supports a maximum alignment of 1, whereas `JAVA_INT` requires alignment 4. Use `JAVA_INT_UNALIGNED` (adding `withOrder` matching the format).

**Question 5.** Does `withOrder(BIG_ENDIAN)` immediately reorder the bytes in the segment?  
**Answer:** No. It returns a new layout; bytes are only written in that order when calling `set`, or interpreted in that order when calling `get`.

**Question 6.** After `get(bigEndianLayout, offset)` returns `0x12345678`, do you need `Integer.reverseBytes` so Java has a “native int”?  
**Answer:** No. The Java `int` is already the correct logical value; calling reverse bytes would change the bit pattern to `0x78563412` and cause a wrong result unless there is an explicit reason.

**Question 7.** A file has a big-endian `uint16` field `A0 B1`, and Java `get(JAVA_SHORT_UNALIGNED.withOrder(BIG_ENDIAN), off)` returns a negative `short`. Should you change the endianness?  
**Answer:** No. The endianness is already right. Use `Short.toUnsignedInt` to represent the unsigned value, giving `0xA0B1`.

**Question 8.** A C API allocates a buffer containing a big-endian file payload. Should Java choose `nativeOrder` because the memory was allocated with `malloc`?  
**Answer:** No. How memory is allocated does not determine the payload's byte order; you must rely on the contract of **the bytes stored in the buffer**.

**Question 9.** Does `MemorySegment.copy` automatically convert a big-endian int array to little-endian?  
**Answer:** No. It copies bytes. To convert order, you must decode each value using the source layout and encode it using the destination layout.

**Question 10.** If you chose the right endianness for a 32-bit field in a C struct but still read the wrong value, what should you check next?  
**Answer:** Field size and signedness, ABI padding, alignment, byte offset, record stride, segment lifetime, and struct version.

## 14. Key takeaways

- **Endianness belongs to the data**, not to the word “native”, pointer type, or where the buffer was allocated.
- **`BIG_ENDIAN`:** most significant byte first; **`LITTLE_ENDIAN`:** least significant byte first; **`nativeOrder()`:** follows the current platform.
- In **FFM JDK 22+**, `ValueLayout.JAVA_INT` uses native order. **`withOrder(...)` creates a new layout**, while `MemorySegment` keeps its bytes unchanged until written.
- **Fixed-endian file/protocol formats must be respected on every host**, even when the host uses a different order. Only use native order when the native contract genuinely requires it.
- For `MemorySegment.ofArray(byte[])`, use `*_UNALIGNED` layouts for multi-byte fields; endianness and alignment are two separate conditions.
- `ByteBuffer` defaults to **BIG_ENDIAN**, not necessarily matching FFM `JAVA_INT`'s default of **native order**.
- To convert encoding, **read in the source order and write in the destination order**; copying bytes or changing layouts does not transform data automatically.
- You must check **offset, stride, padding, unsignedness, bounds, lifetime, and schema** alongside byte order.

### Official documentation

- [Oracle Java SE 22 — ValueLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.html): `JAVA_INT` and default layouts in native order; `order()`, `withOrder(...)`, unaligned layouts.
- [Oracle Java SE 22 — ValueLayout.OfInt](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/ValueLayout.OfInt.html): `withOrder` returns a typed layout; relationship between byte size and alignment.
- [Oracle Java SE 22 — MemorySegment](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemorySegment.html): `get`, `set`, byte offsets, memory safety, heap alignment, using big-endian layouts.
- [Oracle Java SE 22 — MemoryLayout](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/lang/foreign/MemoryLayout.html): group/struct layouts, padding, field offsets.
- [Oracle Java SE 22 — ByteBuffer](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteBuffer.html): `order`, big-endian default, and primitive read/write operations.
- [Oracle Java SE 22 — ByteOrder](https://docs.oracle.com/en/java/javase/22/docs/api/java.base/java/nio/ByteOrder.html): `BIG_ENDIAN`, `LITTLE_ENDIAN`, `nativeOrder()`.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): FFM API finalized in JDK 22.
