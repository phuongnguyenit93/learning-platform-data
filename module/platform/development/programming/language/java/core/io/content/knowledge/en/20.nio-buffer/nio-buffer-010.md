# ByteOrder and Primitive View Buffers in Java NIO

## 1. The Problem to Solve

When exchanging binary data, a sequence of bytes can represent different values depending on **byte order (endianness)** and the **data type** used to decode it. Java NIO provides `ByteBuffer` to hold bytes, `ByteOrder` to specify how bytes combine into multi-byte values, and **view buffers** such as `IntBuffer`, `ShortBuffer`, and `FloatBuffer` to read/write multiple elements of the same type over that exact memory region.

Three questions to keep distinct:

1. **Byte order:** in what order are the bytes of an `int`, `short`, `long`, `float`, `double`, or `char` arranged?
2. **View type:** as what element type are we interpreting the byte memory, and how many bytes does each element occupy?
3. **Buffer state:** how do the view's `position`, `limit`, `capacity`, and `mark` relate to the source buffer?

Key answer: **a view shares byte contents, yet maintains independent cursor state; the view's byte order is fixed at the time the view is created**.

## 2. Big-Endian and Little-Endian

`java.nio.ByteOrder` defines two constants:

- `ByteOrder.BIG_ENDIAN`: stores the most significant byte first.
- `ByteOrder.LITTLE_ENDIAN`: stores the least significant byte first.

Consider the 32-bit integer `0x01020304`:

| Byte Order | Offset 0 | Offset 1 | Offset 2 | Offset 3 |
|---|---|---|---|---|
| Big-endian | `01` | `02` | `03` | `04` |
| Little-endian | `04` | `03` | `02` | `01` |

This is the **byte storage order of the same value**, not bit reversal within each byte. Endianness only affects combining multiple bytes; a single-byte `get()`/`put(byte)` operation has no big/little-endian difference.

Illustrative example:

~~~java
ByteBuffer big = ByteBuffer.allocate(4);
big.putInt(0x01020304); // 01 02 03 04

ByteBuffer little = ByteBuffer.allocate(4);
little.order(ByteOrder.LITTLE_ENDIAN);
little.putInt(0x01020304); // 04 03 02 01
~~~

This is an **illustrative code snippet** with `java.nio.ByteBuffer` and `java.nio.ByteOrder` imported. The comments describe the byte contents, not automatically printed strings.

### ByteBuffer's Default

Every **newly created** `ByteBuffer` starts with byte order **`BIG_ENDIAN`** per the Java 17 specification, whether created via `allocate(...)`, `allocateDirect(...)`, or `wrap(...)`.

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
System.out.println(buffer.order()); // BIG_ENDIAN

buffer.order(ByteOrder.LITTLE_ENDIAN);
System.out.println(buffer.order()); // LITTLE_ENDIAN
~~~

`ByteBuffer.order(ByteOrder)` changes how the buffer **reads/writes multi-byte values from that point onward**. Calling it does not reverse bytes already stored. Given the same four bytes `01 02 03 04`, `getInt()` in big-endian reads `0x01020304`, whereas in little-endian it reads `0x04030201`.

### Is `ByteOrder.nativeOrder()` the Default Choice?

No. `ByteOrder.nativeOrder()` returns the byte order of the underlying platform running the JVM. It is useful when optimizing operations with native memory or native libraries, yet **does not change the `BIG_ENDIAN` default of newly created `ByteBuffer`s** and is not a standard for file/network protocols.

**Rule:** whatever endianness the binary format specifies, pick that exact endianness regardless of what `nativeOrder()` returns on the development machine. In some network protocols, multi-byte fields use big-endian; various file formats use little-endian.

## 3. ByteBuffer Multi-Byte Primitive Reads/Writes

`ByteBuffer` supports operations for primitives: `char` (2 bytes), `short` (2), `int` (4), `long` (8), `float` (4), `double` (8). There is no corresponding `getBoolean()` or `asBooleanBuffer()`.

Example:

~~~java
ByteBuffer b = ByteBuffer.allocate(12)
        .order(ByteOrder.LITTLE_ENDIAN);
b.putShort((short) 0x1234); // takes 2 bytes
b.putInt(0x01020304);       // takes 4 bytes
b.putFloat(1.5f);           // takes 4 bytes
b.flip();

short s = b.getShort();
int i = b.getInt();
float f = b.getFloat();
~~~

**Note:** `ByteBuffer.getInt(int index)` uses a **byte index**, so `getInt(4)` reads 4 bytes starting at byte index 4; by contrast, `IntBuffer.get(4)` reads the **5th `int` element** of the view (a 16-byte offset from the start of the view).

Two common operation forms:

- **Relative:** `getInt()`, `putInt(value)` operate at and advance `position` by the number of bytes read/written (4 for `int`).
- **Absolute:** `getInt(index)`, `putInt(index, value)` use the specified byte offset and **do not change `position`**.

The same rules apply to `short`, `long`, `float`, `double`, and `char`. When insufficient bytes remain for a relative operation, `BufferUnderflowException` or `BufferOverflowException` is thrown; an absolute operation with an invalid index throws `IndexOutOfBoundsException`. Writing to a read-only buffer throws `ReadOnlyBufferException`.

`flip()` only sets `limit` to the current write position and resets `position` to 0 to prepare for reading. It **does not change endianness**.

## 4. What Are Primitive View Buffers?

A view buffer is a primitive-typed buffer created **over the existing byte contents** of a `ByteBuffer` via:

| Method on ByteBuffer | View Type | Bytes/Element |
|---|---|---:|
| `asCharBuffer()` | `CharBuffer` | 2 |
| `asShortBuffer()` | `ShortBuffer` | 2 |
| `asIntBuffer()` | `IntBuffer` | 4 |
| `asLongBuffer()` | `LongBuffer` | 8 |
| `asFloatBuffer()` | `FloatBuffer` | 4 |
| `asDoubleBuffer()` | `DoubleBuffer` | 8 |

There is no `asByteBuffer()` because the source is already a `ByteBuffer`; nor is there a view for `boolean`.

A view provides a convenient API for that element type—such as `IntBuffer.get()`, `put(int)`, `get(int index)`, and bulk `get(int[])` / `put(int[])`—instead of manually reading 4-byte groups. **Creating a view does not copy contents:** both the view and the byte buffer access the same data region. Changes made through the view are visible from the original buffer and vice versa.

### Table of Contents and State Relationships

| Property | Relationship Between View and Source ByteBuffer |
|---|---|
| Byte contents | **Shared**; writes affect both views |
| `position`, `limit`, `mark` | **Independent**; relative read/write on the view does not advance `ByteBuffer`'s position |
| Start offset of view | `ByteBuffer.position()` **at the moment the view is created** |
| View capacity | `floor(ByteBuffer.remaining() / bytesPerElement)` |
| New position/limit | `position=0`, `limit=capacity`; mark is unset |
| Byte order | Locked to `ByteBuffer.order()` at the time the view is created |
| Direct | View is direct if and only if the source byte buffer is direct |
| Read-only | View is read-only if and only if the source byte buffer is read-only |

For example, if `ByteBuffer` has `position=2` and `limit=13`, then `remaining=11` bytes. Calling `asIntBuffer()` yields `capacity=floor(11/4)=2` integers, backed by 8 bytes starting at offset 2. **The 3 leftover odd bytes do not belong to this `IntBuffer` view**; they remain in the original `ByteBuffer`.

If after creating the view you move `position` or `limit` on the source buffer, the already created view **does not automatically resize or shift its starting offset**. To view a different region, adjust the byte buffer and create a new view.

### A View's Byte Order Is Fixed

~~~java
ByteBuffer bytes = ByteBuffer.allocate(4);
bytes.order(ByteOrder.LITTLE_ENDIAN);
IntBuffer first = bytes.asIntBuffer();  // fixed LITTLE_ENDIAN

bytes.order(ByteOrder.BIG_ENDIAN);
IntBuffer second = bytes.asIntBuffer(); // fixed BIG_ENDIAN
~~~

Both `first` and `second` read the same 4 bytes, yet interpret them in opposite orders. `first.order()` returns `LITTLE_ENDIAN`, and `second.order()` returns `BIG_ENDIAN`. These primitive views have an `order()` getter, **no `order(ByteOrder)` setter** like `ByteBuffer`. To read in another order, configure the byte buffer and create a new view.

## 5. Illustrating Positions and Memory Sharing

Suppose the byte region is:

~~~text
offset:      0   1   2   3   | 4   5   6   7
LE bytes:   04  03  02  01  | 0D  0C  0B  0A
IntBuffer: [      int[0]    |     int[1]     ]
LE value:         01020304  |     0A0B0C0D
BE value:         04030201  |     0D0C0B0A
~~~

Creating a view from `ByteBuffer.position()==0` and `limit()==8` yields an `IntBuffer` of 2 elements. Writing `0x11223344` through the **LITTLE_ENDIAN view** at index 1 turns the second four bytes into `44 33 22 11`; reading the same index through the BIG_ENDIAN view returns `0x44332211`.

Although both views and the `ByteBuffer` share memory, calling **absolute-index** `little.get(0)` or `little.put(1, value)` does not change any `position`. Calling relative `little.get()` or `little.put(value)` changes only `little`'s `position`.

## 6. Complete Runnable Java 17+ Example

The following example verifies the byte order of two views, data sharing, cursor state, and creating a view from a non-zero byte offset.

**File: `ByteOrderViewDemo.java`**

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.IntBuffer;
import java.nio.ShortBuffer;
import java.util.HexFormat;

public class ByteOrderViewDemo {
    public static void main(String[] args) {
        ByteBuffer bytes = ByteBuffer.allocate(8)
                .order(ByteOrder.LITTLE_ENDIAN);
        bytes.putInt(0x01020304);
        bytes.putInt(0x0A0B0C0D);
        bytes.flip();

        IntBuffer little = bytes.asIntBuffer();
        System.out.println(HexFormat.of().formatHex(bytes.array()));
        System.out.printf("LE[0]=%08X%n", little.get(0));

        bytes.order(ByteOrder.BIG_ENDIAN);
        IntBuffer big = bytes.asIntBuffer();
        System.out.printf("BE[0]=%08X%n", big.get(0));
        System.out.println("orders=" +
                little.order() + "," + big.order());

        little.put(1, 0x11223344);
        System.out.println(HexFormat.of().formatHex(bytes.array()));
        System.out.printf("BE[1]=%08X%n", big.get(1));

        System.out.println("positions=" + bytes.position()
                + "," + little.position() + "," + big.position());

        bytes.position(2);
        ShortBuffer shorts = bytes.asShortBuffer();
        System.out.println("shortCapacity=" + shorts.capacity());
        System.out.printf("BE short=%04X%n", shorts.get(0) & 0xFFFF);
    }
}
~~~

Compile/run (JDK 17+):

~~~bash
javac ByteOrderViewDemo.java
java ByteOrderViewDemo
~~~

Stdout:

~~~text
040302010d0c0b0a
LE[0]=01020304
BE[0]=04030201
orders=LITTLE_ENDIAN,BIG_ENDIAN
0403020144332211
BE[1]=44332211
positions=0,0,0
shortCapacity=3
BE short=0201
~~~

Detailed explanation:

1. `putInt` in little-endian mode writes bytes `04 03 02 01 0D 0C 0B 0A`. `HexFormat` displays the raw bytes clearly without depending on hardware endianness.
2. `little` reads the first four bytes as `01020304`; `big` was created **after switching order**, so it reads those same bytes as `04030201`.
3. `little.put(1, 0x11223344)` writes `44 33 22 11` into the second 4-byte slot. Because contents are shared, `big.get(1)` gets `44332211`.
4. `get(index)`/`put(index, value)` are **absolute**, so all three positions stay at 0.
5. Moving `bytes.position(2)` and calling `asShortBuffer()` creates a view starting at byte offset 2 with 6 bytes remaining ⇒ 3 shorts. The byte buffer is big-endian at that point, so the two bytes `02 01` become `0x0201`.
6. `bytes.array()` is valid here because `ByteBuffer.allocate(...)` creates a heap buffer with an accessible array. For a **direct buffer** or **read-only buffer**, do not blindly call `array()`; check `hasArray()` or read via buffer APIs.

No automatic data copies were made by `asIntBuffer()` or `asShortBuffer()` in this example.

## 7. How Do Views Differ from Similar Buffer Patterns?

### 7.1. `getInt()` vs. `asIntBuffer().get()`

Suppose `ByteBuffer` holds 12 bytes with position 0:

~~~java
int x = bytes.getInt();           // reads 4 bytes, bytes.position += 4
IntBuffer view = bytes.asIntBuffer(); // starts at bytes.position (4)
int y = view.get();               // reads 1 int, view.position += 1
// bytes.position does not advance when view.get() runs
~~~

This illustrative snippet assumes an existing `bytes` variable holding appropriate data. If the goal is viewing all 12 bytes, ensure `ByteBuffer` has the right `position` and `limit` before creating the view (e.g., `bytes.position(0)` if valid data starts at byte 0).

Use `getInt`/`putShort`/`getDouble` directly when **data mixes multiple types in a schema**; use a typed view when **there are many consecutive elements of the same type** and you want element-based indexing and bulk operations.

### 7.2. `slice()` and `duplicate()` Are Not Typed Views

- `ByteBuffer.slice()` creates a new **ByteBuffer** sharing content starting at the source's current `position`, with new position 0.
- `ByteBuffer.duplicate()` creates another **ByteBuffer** sharing the entire byte region, copying initial `position`/`limit`/`mark` state.
- `asIntBuffer()` creates an **IntBuffer** with 4-byte element units, capacity derived from `remaining`, and endianness locked to the order at creation time.

**Common Java 17 pitfall:** `ByteBuffer.slice()`, `duplicate()`, and `asReadOnlyBuffer()` return a **new `ByteBuffer` with default `BIG_ENDIAN` order**, even when the source is `LITTLE_ENDIAN`. Therefore you must re-apply `order` if your goal is preserving the source's endianness:

~~~java
ByteBuffer original = ByteBuffer.allocate(8)
        .order(ByteOrder.LITTLE_ENDIAN);

ByteBuffer part = original.slice();
part.order(original.order()); // must re-apply per protocol

IntBuffer ints = part.asIntBuffer(); // now LITTLE_ENDIAN
~~~

This is an illustrative snippet. Do not assume every buffer type or Java version copies `order` intuitively: rely on the specific method contract.

### 7.3. `asCharBuffer()` Is Not a UTF-8 Decoder

`CharBuffer` views every **2 bytes as one UTF-16 `char` code unit** in the chosen endianness. If the data is UTF-8 (where one character can take 1–4 bytes), it cannot be decoded via `asCharBuffer()`.

To decode text data, use `StandardCharsets.UTF_8.decode(byteBuffer)` or an appropriate `CharsetDecoder`. Typed views **reinterpret fixed-size binary types**; they do not replace charset decoders.

### 7.4. Native Byte Order, Direct Buffers, and Performance

A view inherits the **direct** property of its underlying `ByteBuffer`. `allocateDirect` can suit native I/O or efficient bulk access, though it carries higher allocation/reclamation costs in some scenarios. `ByteOrder.nativeOrder()` can benefit native operations on direct buffers, yet **you must prioritize the file/protocol format's endianness**. Never choose `nativeOrder()` arbitrarily just for speed.

Typed views and byte buffers are **not thread-safe**. If multiple threads modify shared contents through views, proper synchronization is required; independent positions do not guarantee thread safety over shared data.

## 8. Processing a Real Binary Format

Suppose a protocol specifies a 2-byte big-endian header followed by 4 little-endian integers. You can read it cleanly as:

~~~java
ByteBuffer packet = /* buffer containing at least 18 valid bytes */;
packet.order(ByteOrder.BIG_ENDIAN);
short header = packet.getShort();

packet.order(ByteOrder.LITTLE_ENDIAN);
IntBuffer values = packet.asIntBuffer(); // starts right after header
if (values.remaining() < 4) {
    throw new IllegalArgumentException("Thiếu dữ liệu");
}
for (int i = 0; i < 4; i++) {
    int value = values.get();
    // Process value.
}
~~~

**Non-standalone illustrative snippet:** `packet` must already hold received data with `position`/`limit` configured properly. After `getShort()`, `packet`'s position advances by 2; `asIntBuffer()` views from that offset in little-endian with 4-byte elements. Calling `values.get()` advances only `values`'s position. If you want `packet` to advance past the 16-byte payload afterward, explicitly update `packet.position(packet.position() + 16)` after checking bounds.

When designing a parser, you should:

1. Confirm byte order and field sizes from the specification (not from the OS).
2. Set `position`/`limit` accurately before creating a view.
3. Verify `remaining()` holds enough data; for views, check in **element count**.
4. Create the view with the right endianness for homogeneous payload sections.
5. Manage cursor updates for the source buffer and view separately if parsing spans multiple stages.
6. Account for read-only buffers or buffers lacking an accessible backing array.

## 9. Common Mistakes

1. **Forgetting `order(LITTLE_ENDIAN)`:** integers read with reversed byte values because `ByteBuffer` defaults to `BIG_ENDIAN`.
2. **Changing `bytes.order(...)` expecting an existing view to update:** a view retains the byte order from when it was created; for a new order, create a new view.
3. **Confusing byte indices with element indices:** `bytes.getInt(2)` reads starting at byte offset 2, while `ints.get(2)` is the third `int` element (typically starting at byte offset 8 relative to the view).
4. **Assuming creating a view advances the source position:** `asIntBuffer()` does not move `ByteBuffer`'s `position`.
5. **Assuming a view covers the entire capacity:** a view covers only from **current `position` to current `limit`**, with capacity rounded down by element size.
6. **Calling `array()` on a direct or read-only buffer:** it may not expose an accessible backing array; check `hasArray()` or use buffer read methods.
7. **Forgetting to re-apply `order` after `slice()`/`duplicate()`:** in Java 17, the new `ByteBuffer` defaults to `BIG_ENDIAN`.
8. **Using `asCharBuffer()` to decode UTF-8:** wrong because it views 2-byte `char` units, not text encoding.
9. **Using `nativeOrder()` for a file format:** data must match the file/network protocol specification.
10. **Believing views are safe when multiple threads write concurrently:** shared memory needs synchronization, especially for mutating operations.

## 10. Self-Check

**Question 1.** A `ByteBuffer` contains `01 02 03 04` and is set to `BIG_ENDIAN`. What does `getInt(0)` return? What if switched to `LITTLE_ENDIAN`?

**Answer:** `0x01020304` in `BIG_ENDIAN`; `0x04030201` in `LITTLE_ENDIAN`. The underlying bytes themselves do not change merely by calling `order`.

**Question 2.** A buffer has 10 bytes remaining; calling `asIntBuffer()` creates a view with how many elements? Does it change `ByteBuffer.position`?

**Answer:** `floor(10/4) = 2` `int` elements; the 2 leftover bytes are excluded from the view; `ByteBuffer.position` does not change.

**Question 3.** You create an `IntBuffer` while byte order is `LITTLE_ENDIAN`, then switch the `ByteBuffer` to `BIG_ENDIAN`. Which endianness does the existing view use?

**Answer:** `LITTLE_ENDIAN` permanently; to get `BIG_ENDIAN`, create a new view after changing `order`.

### Official Documentation

- [Java 17: ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [Java 17: ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html)
- [Java 17: IntBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/IntBuffer.html)
- [Java 17: Buffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html)
- [Java 17: StandardCharsets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/StandardCharsets.html)
