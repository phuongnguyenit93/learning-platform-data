# 9.3. Creating byte[] or ByteBuffer Views with VarHandle and Choosing Byte Order

## Learning Objectives

After this lesson, you will be able to:

- Create a `VarHandle` that reads/writes values of types `short`, `char`, `int`, `long`, `float`, `double` directly over the byte region of a `byte[]` or `ByteBuffer`, using the two factory methods in `MethodHandles`.
- Distinguish the **byte offset** used as the VarHandle coordinate from the **element index of an array of a type larger than a byte**.
- Choose `ByteOrder.BIG_ENDIAN`, `ByteOrder.LITTLE_ENDIAN`, or when appropriate `ByteOrder.nativeOrder()`; explain the result of reading the same data with different byte orders.
- Understand that the VarHandle byte order chosen at creation time is **independent** of the `ByteBuffer.order()` property.
- Identify errors related to memory bounds, `limit` boundaries, read-only buffers, unsupported view types, alignment conditions, and unguaranteed access modes.
- Apply this to binary data formats with multiple fields and deterministically test byte results on Java 17+.

## 1. The Problem: Multiple Bytes Representing One Value

A packet, file header, binary record, or native memory region is often a sequence of bytes. For example, four bytes:

~~~text
01 02 03 04
~~~

We may want to interpret those four bytes as a 32-bit integer. The result depends on **byte order** (endianness):

| Ordering | What does the first byte mean? | 4 bytes stored for the value `0x01020304` |
| --- | --- | --- |
| **Big-endian** | Most significant byte comes first | `01 02 03 04` |
| **Little-endian** | Least significant byte comes first | `04 03 02 01` |

A sequence of bytes **does not carry its own label** of "big" or "little". The parser/serializer author must know the specification of the data format. If stored in big-endian and decoded as little-endian, the result becomes `0x04030201`; the JVM does not necessarily throw an error because both interpretations can be valid at the byte level.

Java can do this using bit shifts and masks, or `ByteBuffer.getInt/putInt`. With `VarHandle`, we create a **typed view** over the already existing byte region:

~~~text
byte[] bytes or ByteBuffer
    |
    +--> VarHandle int, BIG_ENDIAN    -> combines 4 bytes into an int
    |
    +--> VarHandle int, LITTLE_ENDIAN -> combines 4 bytes in reverse order
    |
    +--> VarHandle short, BIG_ENDIAN  -> combines 2 bytes into a short
~~~

These views **do not copy** the data into a new `int[]` or `short[]` array. A `set` call through the view mutates the underlying source bytes directly; `get` reads those same bytes and combines them according to the view's type and byte order.

## 2. The Two Factory Methods and Exact Signatures

Java 9+ provides:

~~~java
// Excerpted API signatures (illustrative); not standalone class code:
static VarHandle MethodHandles.byteArrayViewVarHandle(
        Class<?> viewArrayClass, ByteOrder byteOrder);

static VarHandle MethodHandles.byteBufferViewVarHandle(
        Class<?> viewArrayClass, ByteOrder byteOrder);
~~~

Two common calls:

~~~java
// Fragment using imports java.lang.invoke.* and java.nio.*:
VarHandle arrayIntsBE = MethodHandles.byteArrayViewVarHandle(
        int[].class, ByteOrder.BIG_ENDIAN);

VarHandle bufferIntsLE = MethodHandles.byteBufferViewVarHandle(
        int[].class, ByteOrder.LITTLE_ENDIAN);
~~~

**`int[].class` here only describes "wanting to view bytes as int elements."** It does not mean we pass an `int[]` as the data source. The actual source for the first factory is still `byte[]`, and for the second factory is still `ByteBuffer`.

| Property | `byteArrayViewVarHandle` | `byteBufferViewVarHandle` |
| --- | --- | --- |
| Object containing bytes | `byte[]` | `ByteBuffer` (heap, direct, or suitable view) |
| Example view type | `int[].class` | `int[].class` |
| `varType()` for example | `int.class` | `int.class` |
| `coordinateTypes()` | `[byte[].class, int.class]` | `[ByteBuffer.class, int.class]` |
| `int` coordinate | **Byte offset** in the `byte[]` array | Absolute **byte index** in the passed buffer |
| Bounds limit | `byte[].length` | `ByteBuffer.limit()` |
| Out-of-bounds error | `ArrayIndexOutOfBoundsException` | `IndexOutOfBoundsException` |
| Read-only rule | Normal byte array is writable | Read-only buffer rejects write access |
| Byte order | At VarHandle creation | At VarHandle creation, **overrides `buffer.order()`** |

Both factories only support the primitive component types **`short`, `char`, `int`, `long`, `float`, `double`**. They do not create views for `boolean[].class` or `byte[].class`. If you want to manipulate individual bytes, use `bytes[i]`, `ByteBuffer.get(index)/put(index, value)`, or the standard array element VarHandle mechanism when appropriate.

**The array class form must be valid**: for example `int[].class`, not `int.class`. The factory may throw `IllegalArgumentException` when the passed class is not an array class, `UnsupportedOperationException` when the primitive component type is not in the supported set, and `NullPointerException` if a required factory argument is null.

### 2.1. The Handle Type Is Decided at Creation Time

Example with `int[].class`:

~~~java
VarHandle vh = MethodHandles.byteArrayViewVarHandle(
        int[].class, ByteOrder.BIG_ENDIAN);
// vh.varType() == int.class
// vh.coordinateTypes().equals(List.of(byte[].class, int.class))
~~~

This is a fragment (requires importing `VarHandle`, `MethodHandles`, `ByteOrder`, and `List`). Then operate on it:

~~~java
// Fragment, assuming byte[] bytes has at least 4 bytes and vh is as above:
vh.set(bytes, 0, 0x01020304);
int value = (int) vh.get(bytes, 0);
~~~

`VarHandle.get/set` are access modes supported by the JVM as signature-polymorphic calls. From this code, the JVM knows `get` returns `int` and `set` accepts an `int` value when the VarHandle has variable type `int`. Passing the wrong coordinate type or expecting an incompatible return type can cause `WrongMethodTypeException` or a related type error at runtime; it should not be treated as an arbitrary `Object` parser.

## 3. The Coordinate Is a Byte Offset, Not an Int Element Index

Suppose we need to write `int 0x01020304` into a 10-byte array, starting at **byte index 1**:

~~~text
byte index:  0  1  2  3  4  5  6  7  8  9
value:      00 01 02 03 04 00 00 00 00 00
               |----------|
              int from byte 1, BIG_ENDIAN
~~~

The call is `view.set(bytes, 1, 0x01020304)` and it uses **bytes[1] through bytes[4]**. If you are modeling contiguous 4-byte-wide int elements, the offset of the `i`-th element must be computed by your code: `baseOffset + i * Integer.BYTES`. The factory does not automatically multiply the coordinate `i` by 4.

This is where it differs from a real `int[]`: `ints[1]` is the second int element; whereas `vh.get(bytes, 1)` reads **starting at the second byte**.

Rule for each view:

| View | Bytes read/written | Last valid offset on an array of length `n` |
| --- | ---: | --- |
| `short[].class`, `char[].class` | 2 | `n - 2` |
| `int[].class`, `float[].class` | 4 | `n - 4` |
| `long[].class`, `double[].class` | 8 | `n - 8` |

General condition for a region of `size` bytes: **`0 <= offset` and `offset <= limit - size`**. If the region is shorter than `size`, no offset is valid. With `ByteBuffer`, use the current `limit()`, do not arbitrarily use `capacity()`. Do not only check `offset < length`: that does not guarantee there are 4 or 8 bytes available to read.

## 4. Byte Order Is Bound to the VarHandle at Creation Time

Two views with the same variable type `int` but different `ByteOrder`s can produce two different results when reading the same four bytes.

~~~text
Physical bytes:               01 02 03 04
BIG_ENDIAN view.get(...)   -> 0x01020304
LITTLE_ENDIAN view.get(...) -> 0x04030201
~~~

The `set` call works similarly: writing `0x01020304` in big-endian produces `01 02 03 04`; writing in little-endian produces `04 03 02 01`.

**Do not automatically flip byte order when transferring from network to CPU.** Choose the order according to the **on-the-wire/on-disk format**. Many protocols specify big-endian; some file formats, devices, or wire protocols use little-endian. "Running on a little-endian CPU" is not a reason to read every format in little-endian.

`ByteOrder.nativeOrder()` represents the platform's native order. It is only the right choice when your data format **explicitly specifies native order**, or when you are working with a specific memory interface that requires it. Do not use it for files/protocols with a fixed order, because the results can be incompatible across platforms.

### 4.1. Does ByteBuffer.order() Control the VarHandle View?

**No.** With `MethodHandles.byteBufferViewVarHandle(int[].class, ByteOrder.BIG_ENDIAN)`, the view's `get/set` calls always use **BIG_ENDIAN** per the factory argument. Even if you call `buffer.order(ByteOrder.LITTLE_ENDIAN)`, that only controls the corresponding ByteBuffer operations such as `buffer.getInt(index)` or `buffer.putInt(index, value)`.

Example reading the same bytes `11 22 33 44`:

~~~text
ByteBuffer.order(LITTLE_ENDIAN)
ByteBuffer.getInt(offset)                  -> 0x44332211
VarHandle(BIG_ENDIAN).get(buffer, offset)  -> 0x11223344
~~~

**Both different results are consistent**, because the two APIs were instructed to use two different byte orders.

## 5. Complete Example 1: byte[] and ByteBuffer, Bounds, and Read-Only

Save the file **ViewVarHandleDemo.java** in an empty directory:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ReadOnlyBufferException;
import java.util.HexFormat;

public class ViewVarHandleDemo {
    private static String hex(byte[] value) {
        return HexFormat.of().withUpperCase().formatHex(value);
    }
    private static String hexInt(int value) {
        return String.format("%08X", value);
    }

    public static void main(String[] args) {
        VarHandle bigArray = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.BIG_ENDIAN);
        VarHandle littleArray = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.LITTLE_ENDIAN);

        byte[] packet = new byte[10];
        bigArray.set(packet, 1, 0x01020304);
        littleArray.set(packet, 5, 0x0A0B0C0D);
        System.out.println("array.hex=" + hex(packet));
        System.out.println("array.be1=" + hexInt((int) bigArray.get(packet, 1)));
        System.out.println("array.le1=" + hexInt((int) littleArray.get(packet, 1)));
        System.out.println("array.le5=" + hexInt((int) littleArray.get(packet, 5)));
        System.out.println("array.byteIndex="
                + bigArray.coordinateTypes().equals(
                        java.util.List.of(byte[].class, int.class)));
        System.out.println("array.valueType=" + bigArray.varType().getSimpleName());
        try {
            bigArray.get(packet, 7);
        } catch (ArrayIndexOutOfBoundsException ex) {
            System.out.println("array.bounds=" + ex.getClass().getSimpleName());
        }

        ByteBuffer buffer = ByteBuffer.allocate(8);
        buffer.order(ByteOrder.LITTLE_ENDIAN);
        VarHandle bigBuffer = MethodHandles.byteBufferViewVarHandle(
                int[].class, ByteOrder.BIG_ENDIAN);
        bigBuffer.set(buffer, 2, 0x11223344);
        System.out.println("buffer.hex=" + hex(buffer.array()));
        System.out.println("buffer.view=" + hexInt((int) bigBuffer.get(buffer, 2)));
        System.out.println("buffer.getInt=" + hexInt(buffer.getInt(2)));
        buffer.position(1);
        int previousPosition = buffer.position();
        bigBuffer.get(buffer, 2);
        System.out.println("buffer.positionUnchanged="
                + (buffer.position() == previousPosition));
        System.out.println("buffer.valueType=" + bigBuffer.varType().getSimpleName());

        ByteBuffer readOnly = buffer.asReadOnlyBuffer();
        System.out.println("readonly.get=" + hexInt((int) bigBuffer.get(readOnly, 2)));
        try {
            bigBuffer.set(readOnly, 2, 0xAABBCCDD);
        } catch (ReadOnlyBufferException ex) {
            System.out.println("readonly.set=" + ex.getClass().getSimpleName());
        }
        buffer.limit(5);
        try {
            bigBuffer.get(buffer, 2);
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("buffer.limit=" + ex.getClass().getSimpleName());
        }
    }
}
~~~

Run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 ViewVarHandleDemo.java
java ViewVarHandleDemo
~~~

Exact stdout:

~~~text
array.hex=00010203040D0C0B0A00
array.be1=01020304
array.le1=04030201
array.le5=0A0B0C0D
array.byteIndex=true
array.valueType=int
array.bounds=ArrayIndexOutOfBoundsException
buffer.hex=0000112233440000
buffer.view=11223344
buffer.getInt=44332211
buffer.positionUnchanged=true
buffer.valueType=int
readonly.get=11223344
readonly.set=ReadOnlyBufferException
buffer.limit=IndexOutOfBoundsException
~~~

### 5.1. Analyzing the Result on byte[]

- `packet` has **10 bytes**. `bigArray.set(packet,1,0x01020304)` writes to indices 1–4 in big-endian; `littleArray.set(packet,5,0x0A0B0C0D)` writes to indices 5–8 in little-endian. Bytes 0 and 9 remain `00`. Therefore, the hex of the entire array is `00 01 02 03 04 0D 0C 0B 0A 00`.
- For the same bytes 1–4, big-endian returns `0x01020304`, and little-endian returns `0x04030201`. Java does not report a byte order error because both reads are valid.
- `array.le5=0A0B0C0D` shows that writing and reading with the same little-endian view recovers the exact original value.
- `coordinateTypes()` returns a list containing `byte[].class`, `int.class`, so `array.byteIndex=true`; `varType()` is `int`.
- For `int`, 4 bytes are needed. Offset 7 on an array of length 10 is not enough (only bytes 7–9 remain), hence `ArrayIndexOutOfBoundsException`.

The example intentionally places the `int` regions at **offsets 1 and 5** to emphasize **byte** coordinates and show that plain `get/set` can operate at offsets that are not multiples of 4. Do not interpret this as a guarantee that atomic/volatile access modes also allow such offsets.

### 5.2. Analyzing the Result on ByteBuffer

- `ByteBuffer.allocate(8)` creates 8 bytes on the heap. `bigBuffer.set(buffer,2,0x11223344)` writes bytes 2–5 as `11 22 33 44`; the remaining bytes are 0. Therefore `buffer.hex=0000112233440000`.
- `bigBuffer.get(buffer,2)` reads in fixed big-endian: `0x11223344`. `buffer.getInt(2)` reads the same position according to **`buffer.order(LITTLE_ENDIAN)`**: `0x44332211`.
- The VarHandle coordinate `2` is an **absolute byte index**, not automatically added to `position()`. Calling `bigBuffer.get` also **does not advance the buffer's position**.
- When converted via `asReadOnlyBuffer()`, the read mode `get` can still read; `set` gets `ReadOnlyBufferException`.
- When reducing `buffer.limit(5)`, reading 4 bytes from offset 2 would require reaching byte 5, exceeding the last allowed index (4). Thus `get` throws `IndexOutOfBoundsException`, even though `capacity()` is still 8.

**Note on `buffer.array()`:** The example uses a heap buffer from `allocate`, so accessing the underlying array works. **Direct buffers** and some other buffers do not allow calling `array()`. You can use a view VarHandle with a direct buffer without calling `array()`; to print the bytes of a direct buffer, read via `get(index)` calls or make a copy for display.

## 6. Complete Example 2: A Record with Fields Using Different Byte Orders

In practice, a binary schema might define:

| Byte offset | Field | Type read by VarHandle | Byte order | Size |
| ---: | --- | --- | --- | ---: |
| 0 | `header` | `short` | BIG_ENDIAN | 2 |
| 2 | `length` | `int` | LITTLE_ENDIAN | 4 |
| 6 | `value` | `float` | BIG_ENDIAN | 4 |
| 10 | `reserved` | raw bytes | Not applicable | 2 |

This is an **illustrative format defined by this lesson**, not representing an existing standard protocol. The data is stored in a 12-byte `byte[]`; there is no need to convert it into three different typed arrays.

Create the file **BinaryPacketDemo.java**:

~~~java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.VarHandle;
import java.nio.ByteOrder;
import java.util.HexFormat;

public class BinaryPacketDemo {
    public static void main(String[] args) {
        VarHandle shortBE = MethodHandles.byteArrayViewVarHandle(
                short[].class, ByteOrder.BIG_ENDIAN);
        VarHandle intLE = MethodHandles.byteArrayViewVarHandle(
                int[].class, ByteOrder.LITTLE_ENDIAN);
        VarHandle floatBE = MethodHandles.byteArrayViewVarHandle(
                float[].class, ByteOrder.BIG_ENDIAN);

        byte[] frame = new byte[12];
        shortBE.set(frame, 0, (short) 0x1234);
        intLE.set(frame, 2, 0x01020304);
        floatBE.set(frame, 6, 1.5f);

        System.out.println("frame=" + HexFormat.of().withUpperCase().formatHex(frame));
        System.out.println("header=" + String.format("%04X", (short) shortBE.get(frame, 0) & 0xFFFF));
        System.out.println("length=" + String.format("%08X", (int) intLE.get(frame, 2)));
        System.out.println("value=" + (float) floatBE.get(frame, 6));
        System.out.println("tail=" + (frame[10] == 0 && frame[11] == 0));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 BinaryPacketDemo.java
java BinaryPacketDemo
~~~

Stdout:

~~~text
frame=1234040302013FC000000000
header=1234
length=01020304
value=1.5
tail=true
~~~

Data breakdown:

~~~text
Offset : 00 01 | 02 03 04 05 | 06 07 08 09 | 10 11
Bytes  : 12 34 | 04 03 02 01 | 3F C0 00 00 | 00 00
Field  : header   length         value        reserved
Order  : BIG      LITTLE         BIG          —
~~~

- `shortBE` stores `0x1234` as `12 34`.
- `intLE` stores `0x01020304` as `04 03 02 01`.
- `floatBE` stores `1.5f` in the IEEE 754 representation of `float`, yielding bytes `3F C0 00 00` in big-endian.
- The two reserved bytes were not written, so they remain 0.
- When displaying `header`, `& 0xFFFF` lets us view the 16 bits of `short` as an unsigned number for formatting. `VarHandle` still has primitive `short` as its variable type; it does not create an "unsigned short" on its own.

The example shows that a record can contain **multiple different types and byte orders**, as long as the schema specifies the exact offset, size, and interpretation. Do not guess the byte order based on field names or the configuration of the machine running the code.

## 7. Length, Limit, Position, and Slice: Four Distinct Concepts

### 7.1. Byte Arrays

For `byte[]`, the valid region is always from offset 0 to `length-1`. An `int` view needs a 4-byte contiguous window. Condition to check before calling (avoiding integer overflow):

~~~java
// Illustrative fragment: bytes is byte[], offset is int.
int size = Integer.BYTES;
if (offset < 0 || offset > bytes.length - size) {
    throw new IllegalArgumentException("Not enough bytes for int");
}
int value = (int) intBE.get(bytes, offset);
~~~

This snippet requires defining `intBE` beforehand and adding imports if turned into a complete program. If `bytes.length - size` is negative, every non-negative offset is rejected, matching the meaning that the data region is too short.

### 7.2. ByteBuffer

`ByteBuffer` distinguishes:

- **capacity:** total capacity of the buffer region.
- **limit:** current logical end point, exclusive; a VarHandle view must not read/write a value straddling the limit.
- **position:** location for relative operations such as `get()` and `put(byte)`; VarHandle uses an absolute index and does not move the position.
- **slice:** a new `ByteBuffer` viewing the corresponding sub-region of the source; the view's offset is measured from the start of the new **slice**, not from offset 0 of the original buffer.

Conceptual example:

~~~java
// Fragment: base is a suitable ByteBuffer, vh is an int-view VarHandle.
base.position(4);
ByteBuffer segment = base.slice();
// segment has index 0 corresponding to the byte at position 4 of base.
int value = (int) vh.get(segment, 0);
~~~

The snippet above **does not run standalone** because `base` and `vh` are undeclared. The bounds of `segment` are enforced independently. If you need to access exact bytes of the original buffer, compute the correct offset before slicing or maintain an offset map.

**Comparison with the `asIntBuffer()` view buffer:** `ByteBuffer.asIntBuffer()` creates an `IntBuffer` whose element indices are counted in **`int`s** and whose initial region starts at the ByteBuffer's position when the view is created. Meanwhile, `byteBufferViewVarHandle(int[].class,...).get(buffer,index)` still takes the **byte index** of the passed `ByteBuffer`. Do not mix the two coordinate systems.

## 8. Alignment and Access Modes: Plain get/set Differs from Synchronized Operations

`VarHandle` does not only have `get/set`; it also has modes such as `getVolatile`, `setVolatile`, `getAcquire`, `setRelease`, `compareAndSet`, `getAndAdd`, and bitwise atomic updates. However, a view over a byte region **does not guarantee that all modes are valid at every offset, for every type, and on every platform**.

Per the contract of the two factories:

1. **Plain `get` and `set` can read/write at unaligned offsets** relative to the type's width, provided there are enough bytes and access permissions are valid.
2. Access modes **other than plain `get/set`** must pay attention to **alignment according to the underlying address** of the byte region and the type size. If accessed misaligned, the API may throw `IllegalStateException` for those modes.
3. Some atomic update groups are supported for `int`, `long`, `float`, `double`; the numeric/bitwise atomic update groups have a narrower supported type set, mainly `int`, `long`. Check the specific method and platform.
4. `isAccessModeSupported(VarHandle.AccessMode.X)` only indicates whether an access mode is supported for the handle **in general**; a specific offset may still be misaligned or out of bounds.
5. For `ByteBuffer`, **read-only** blocks write modes even if the buffer has enough bytes. For views over `byte[]`, using atomic modes also requires proper alignment.

### 8.1. Checking Alignment on ByteBuffer

A meaningful way to check for an `int` view:

~~~java
// Fragment: buffer is a created ByteBuffer, index is the byte offset.
int byteWidth = Integer.BYTES;
int misalignment = buffer.alignmentOffset(index, byteWidth);
if (misalignment != 0) {
    // Do not use atomic/volatile modes at this offset.
}
// Plain get/set has its own contract; limit must still be checked.
~~~

`alignmentOffset` considers the underlying address, not just `index % 4`. A slice with a different base address, or a heap/direct buffer, can make the check less simple than relying solely on the offset. For heap buffers, the ability to determine alignment for certain `unitSize` values is also implementation-dependent; if it cannot be determined, handle the API limitation rather than guessing.

For `byte[]`, the official API describes determining misalignment via `ByteBuffer.wrap(new byte[0]).alignmentOffset(0, sizeOfT)` combined with the index and size. Do not assume that `index % 4 == 0` guarantees atomicity on every JVM and every array base address.

### 8.2. Do Not Equate Endianness with Memory Ordering

**Byte order** answers the question "in what direction are the bytes of a multi-byte value arranged?". **Memory ordering** (plain, opaque, acquire, release, volatile) answers the question "what ordering and visibility guarantees exist for reads/writes between threads?".

These two dimensions are **different**:

~~~text
BIG_ENDIAN / LITTLE_ENDIAN    -> how bytes are assembled into a value
get / set / getVolatile / ... -> memory access semantics
~~~

Choosing `ByteOrder.BIG_ENDIAN` does not turn a plain `get` into volatile, and choosing `getVolatile` does not change the big/little rule. If data is shared across multiple threads or threads communicate with devices/native code, synchronization must be designed according to the exact specification, not based solely on byte order.

### 8.3. Should This VarHandle Be Used as an Atomic Counter?

Only when the need is right, the variable type/mode is supported, the data is validly aligned, and the memory region has a clear ownership model. You should not build an atomic counter by picking any 4-byte location in a packet and calling `getAndAdd`. Normal binary formats use VarHandle mainly to **read/write with a deterministic byte order**; if the goal is a concurrent counter, an `int/long` field with a corresponding VarHandle or an atomic class is usually easier to reason about.

## 9. Error Handling and Data Validation

| Action | Issue | Error or symptom to handle |
| --- | --- | --- |
| Create view with `int.class` instead of `int[].class` | `viewArrayClass` is not an array class | `IllegalArgumentException` |
| Create view with `byte[].class` or `boolean[].class` | Element type is not supported for byte views | `UnsupportedOperationException` |
| Create view with `viewArrayClass` or `byteOrder` as `null` | Missing factory argument | `NullPointerException` |
| `get(byte[],offset)` exceeds type length | Not enough bytes in array | `ArrayIndexOutOfBoundsException` |
| `get(ByteBuffer,offset)` exceeds current `limit` | Not enough bytes in logical region | `IndexOutOfBoundsException` |
| `set(readOnlyBuffer,...)` | Read-only buffer | `ReadOnlyBufferException` |
| Access mode requires alignment but data is misaligned | Mode precondition not met | `IllegalStateException` |
| Access mode not supported for view type | Wrong atomic operation type | `UnsupportedOperationException` |
| Wrong coordinate or variable type when calling `get/set` | Signature-polymorphic call incompatible with handle | `WrongMethodTypeException` or related type error |
| Reading within bounds but with wrong byte order | Misinterpreted data | **Usually no exception**: receives a different value |

Do not catch every `RuntimeException` and return 0: doing so hides byte-bounds bugs, byte-order configuration bugs, and data bugs. For files/protocols, validate header/version/length, determine byte order from the specification, and report parse errors with context.

### 9.1. Checks Before Decoding a Packet

A practical parser should have a contract:

1. Ensure the container has the minimum number of bytes.
2. Determine the layout and **offsets measured in bytes**.
3. Choose `ByteOrder` **based on the specification**; do not take `nativeOrder()` if the protocol does not allow it.
4. Decode each field using a view of the right type and right offset.
5. Validate the read values: version, magic, length, range, checksum, or schema rules.
6. When encoding, write fields in the right order and size; test golden bytes (hex) to avoid bugs that do not show up when round-tripping the same buggy codec.

**Golden bytes matter more than round-trip alone**: if you both write and read using the same wrong order, round-trip tests can still pass. Comparing against the expected byte sequence from the protocol is what catches reversed order.

## 10. When to Choose byte[] View, ByteBuffer View, or Another API?

| Need | Usually reasonable choice | Considerations |
| --- | --- | --- |
| Binary data is in `byte[]`, need to read/write multiple primitive values | `byteArrayViewVarHandle` | Does not create a new primitive array; manage byte offsets yourself |
| Data is in `ByteBuffer`, may be heap/direct/sliced | `byteBufferViewVarHandle` | Bounded by `limit`, read-only, and alignment |
| Need a few simple `getInt/putInt` calls on a buffer | `ByteBuffer.order(...).getInt(index)` | Clear, often easier to read when there is only one byte order |
| Need multiple fields with different orders on the same byte region | Multiple VarHandles, each bound to its own order/type | Avoids mutating `buffer.order()` back and forth |
| Want `int`-based indexing and bulk operations | `ByteBuffer.asIntBuffer()` | View buffer uses element index, separate position/limit; byte order fixed at view creation |
| Only processing a few individual bytes | `bytes[i]` or `ByteBuffer.get(index)` | No multi-byte view needed |
| Need to decode a protocol with variable-length fields, bit fields, checksums | Combine byte views + schema-aware parser | VarHandle does not parse structure or validate data automatically |
| Need multi-threaded atomic memory access | Field/array-element VarHandle or byte view with verified mode/alignment | Do not confuse byte order with memory ordering |

The strength of `VarHandle` here is a **typed view with fixed order** over the original byte region itself. It does not replace all of `ByteBuffer`, does not define the schema by itself, and does not make binary data safe without bounds checks.

## 11. Common Pitfalls

**Pitfall 1: `int[].class` means we can pass an `int[]` to `get`.** False. It only selects the element type of the view; the first coordinate is still `byte[]` or `ByteBuffer` depending on the factory.

**Pitfall 2: Offset 3 means the fourth int element.** False. It is **byte offset 3**, starting to read bytes 3, 4, 5, 6 if within bounds.

**Pitfall 3: `ByteBuffer.order()` determines the byte order of any VarHandle viewing it.** False. The VarHandle uses the byte order passed at creation time, independent of `ByteBuffer.order()`.

**Pitfall 4: Calling `buffer.position(10)` makes `vh.get(buffer,0)` read from byte 10.** False. A ByteBuffer view VarHandle uses the absolute byte index of the passed buffer. If you want a separate coordinate system from the current position, create an appropriate slice and use the slice's index.

**Pitfall 5: Reading data without error means the byte order is right.** False. The wrong order usually still yields a valid primitive value. Verify with golden bytes, magic/version, and protocol rules.

**Pitfall 6: An `int`-writing view is always atomic because it is 4 bytes wide.** False. You must check access mode, alignment, platform, and API documentation. Plain `get/set` does not automatically become `getVolatile/setVolatile`.

**Pitfall 7: Using `buffer.capacity()` to check if there are enough bytes.** False if `limit()` has been reduced; the view accesses according to the current limit.

**Pitfall 8: `ByteBuffer.array()` can always retrieve the array.** False. Direct buffers or read-only buffers may not expose a backing array through that API.

**Pitfall 9: `byte[].class` is a valid view type to get a single byte back.** False. The two multi-byte view factories support short/char/int/long/float/double; read individual bytes with standard byte APIs.

**Pitfall 10: `nativeOrder()` always gives the best performance so use it for network data.** There is no such universal guarantee; more importantly, network/file formats must be read in their specified byte order, even if the host has a different order.

## 12. Self-Check

**Question 1.** Given bytes `01 02 03 04` and two `int` VarHandles: one big-endian, one little-endian. What are the two `get` values?

**Answer:** `0x01020304` and `0x04030201`. These are the two ways of assembling the same four bytes.

**Question 2.** To write the third `int` into a byte region starting at offset 6, with consecutive ints being 4 bytes long, what is the offset of the third int?

**Answer:** `6 + 2 * 4 = 14` if elements are 0-indexed. The coordinate passed to VarHandle is **14 bytes**, not 2.

**Question 3.** Does `byteArrayViewVarHandle(int[].class, BIG_ENDIAN)` require the source to be `int[]`?

**Answer:** No. The source is always `byte[]`; `int[].class` describes the view's `int` variable type.

**Question 4.** If `buffer.order(LITTLE_ENDIAN)`, but the view was created with `byteBufferViewVarHandle(int[].class, BIG_ENDIAN)`, which order does `view.get(buffer,index)` read in?

**Answer:** BIG_ENDIAN. The ByteBuffer's order property does not override the VarHandle's order.

**Question 5.** `ByteBuffer.allocate(8)` followed by `limit(5)`. Is a VarHandle int get at offset 2 valid?

**Answer:** No. It needs bytes 2, 3, 4, 5, but byte index 5 is outside the exclusive limit 5. It may throw `IndexOutOfBoundsException`.

**Question 6.** Why does `set` on `readOnlyBuffer` fail even though the offset is valid?

**Answer:** A read-only buffer forbids write access; the VarHandle view does not bypass read-only permissions.

**Question 7.** Plain `get` at offset 1 on an int view works. Can we conclude that `getVolatile` or `compareAndSet` at offset 1 will always work?

**Answer:** No. Modes other than plain get/set have different alignment requirements and support scope. You must check alignment and the API contract.

**Question 8.** Writing/reading the same record in LITTLE_ENDIAN produces a correct round-trip. Does that prove the file conforms to a BIG_ENDIAN specification?

**Answer:** No. A codec can both write and read in the wrong order and still pass round-trip. You must compare bytes against test vectors/golden bytes from the specification.

## Key Takeaways

- `MethodHandles.byteArrayViewVarHandle(T[].class, order)` creates a view over **byte[]**; `MethodHandles.byteBufferViewVarHandle(T[].class, order)` creates a view over **ByteBuffer**.
- The two coordinates are always **the byte-containing object + byte offset**; the offset is not automatically multiplied by `sizeof(T)`.
- Supported `T` types: **short, char, int, long, float, double**. The view does not allocate a new `T[]` array.
- **The VarHandle's ByteOrder is fixed at creation time**. `ByteBuffer.order()` does not change how the view combines bytes.
- Check **length/limit, read-only, offset, alignment, and access mode** before use; plain get/set differs from atomic access.
- Always verify **golden bytes of the format**; reading the same data in the wrong order usually still yields a valid number.

## References

- Java SE 17, **MethodHandles** — `byteArrayViewVarHandle` and `byteBufferViewVarHandle`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html
- Java SE 17, **VarHandle** — types, coordinates, access modes, atomicity: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html
- Java SE 17, **ByteBuffer** — absolute get/put, position/limit/capacity, slice, alignmentOffset: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17, **ByteOrder** — BIG_ENDIAN, LITTLE_ENDIAN, nativeOrder: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html
