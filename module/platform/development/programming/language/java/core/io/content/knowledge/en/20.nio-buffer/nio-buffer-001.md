# Buffer, ByteBuffer, CharBuffer, and Other Buffer Types in Java NIO

## 1. What Problem Does Buffer Solve?

In Java NIO (New I/O), a **buffer** is a container of fixed capacity used to write data into and then read data out of. A buffer also tracks state indicating **how much has been used** and **how many elements remain available to read or write**. It serves as a key bridge between a program and APIs such as `FileChannel`, `SocketChannel`, or character encoders/decoders.

For example, a channel reads 5 bytes from a file and places them into an 8-byte `ByteBuffer`. The program needs to distinguish the 5 valid bytes just received from the 3 positions not filled by that read operation. A buffer achieves this via `position` and `limit`; relying solely on the byte array size would not be enough.

Related classes belong to the `java.nio` package:

- `Buffer` is the abstract base class: it defines the state and cursor-control operations.
- `ByteBuffer` holds `byte` units; the type most commonly used when interacting with channels and binary encoding.
- `CharBuffer` holds `char` units (each `char` is a *UTF-16 code unit*).
- `ShortBuffer`, `IntBuffer`, `LongBuffer`, `FloatBuffer`, and `DoubleBuffer` hold their respective primitive types.
- `MappedByteBuffer` is a kind of `ByteBuffer` representing a file region mapped into memory.

There is no standard `BooleanBuffer` class in Java NIO. These buffers manage `position`, `limit`, and `capacity` in a similar way, while each class provides `get`/`put` operations for its specific element type.

## 2. State Model: capacity, limit, position, and mark

Four values you must master:

| Property | Meaning | Invariant |
| --- | --- | --- |
| `capacity()` | Maximum capacity, **counted in buffer elements**. | Fixed capacity throughout the buffer's lifetime. |
| `limit()` | *Exclusive* boundary: relative operations do not reach or go past this index. | `0 <= limit <= capacity`. |
| `position()` | Index of the next element to be used by a relative `get()` or `put(...)`. | `0 <= position <= limit`. |
| `mark()` / `reset()` | Remembers a position to return to later; may be unset. | If set, `0 <= mark <= position`. |

Illustration of a buffer with `capacity=8`, `limit=5`, `position=2`:

~~~text
index:     0   1   2   3   4   5   6   7
         +---+---+---+---+---+---+---+---+
buffer:  | A | B | C | D | E | ? | ? | ? |
         +---+---+---+---+---+---+---+---+
                 ^           ^           ^
             position=2    limit=5    capacity=8

remaining() = limit - position = 3
hasRemaining() = true
~~~

The question marks indicate elements outside the **region currently considered valid for reading**, not necessarily bytes that have been erased or never written.

A buffer created with `ByteBuffer.allocate(8)` starts with `position=0`, `limit=8`, `capacity=8`. If `put` is called 5 times, `position=5` while `limit` remains 8. After `flip()`, `position=0` and `limit=5`: we are ready to read the exact 5 elements just written.

Key formulas:

~~~text
0 <= position <= limit <= capacity
remaining = limit - position
~~~

`remaining()` counts the **number of elements**, not the number of bytes in all cases. For an `IntBuffer`, `remaining() == 3` means 3 `int` values remain, which typically corresponds to 12 bytes of stored data.

## 3. Write-Then-Read Workflow: put → flip → get → clear/compact

### 3.1. State Control Operations

| Operation | State Change | When to Use |
| --- | --- | --- |
| `flip()` | `limit = position`; `position = 0`; clears mark. | Switching from **writing into the buffer** to **reading the written data**. |
| `clear()` | `position = 0`; `limit = capacity`; clears mark. | Ready for a new write pass without needing to keep old data. |
| `rewind()` | `position = 0`; keeps limit unchanged; clears mark. | Wanting to re-read the current data region. |
| `compact()` | Moves elements from `position` to `limit-1` to the start of the container; `position = number of retained elements`, `limit = capacity`; clears mark. | Already read part of the data and want to **keep unread data** while continuing to write. |
| `mark()` | Saves current position into mark. | Wanting to mark a position to return to later. |
| `reset()` | Sets position back to mark, if mark is valid. | Re-reading/re-writing from the marked point. |
| `position(n)` / `limit(n)` | Sets boundaries directly; may invalidate mark. | Needing exact control over the data region. |

**`clear()` does not erase bytes or zero them out.** It only resets `position` and `limit` so the memory region can be overwritten. Nor should you read leftover bytes after `clear` and treat them as new data.

### 3.2. Step-by-Step Example

~~~java
ByteBuffer b = ByteBuffer.allocate(6);
b.put((byte) 'A');
b.put((byte) 'B');
b.put((byte) 'C');
// position=3, limit=6, capacity=6

b.flip();
// position=0, limit=3; only A, B, C are in the readable region

byte first = b.get(); // A; position=1
byte next = b.get();  // B; position=2

b.compact();
// Unread portion is C -> moves C to index 0.
// position=1, limit=6: can continue writing after C.

b.put((byte) 'D');
b.flip();
// position=0, limit=2: readable region is C, D.
~~~

This is an **illustrative snippet** assuming `java.nio.ByteBuffer` is imported and placed inside a method. `compact()` is especially useful for data streams arriving in multiple chunks, such as incomplete network messages.

### 3.3. Why `flip()` Usually Cannot Be Skipped

A `Channel.read(buffer)` or a series of `put` calls typically **advances position** as data is written into the buffer. If you immediately call `get()` without calling `flip()`, the program will read at the position after the last written element instead of from the beginning of the newly received data. The result may be wrong or throw `BufferUnderflowException`, depending on the state.

Conversely, after reading everything and wanting to overwrite from the beginning, you need `clear()`. If unprocessed elements remain, use `compact()`. Choosing the wrong one of these two methods often causes applications to lose part of a message.

## 4. ByteBuffer: Working with Bytes and Binary Data

`ByteBuffer` is the central buffer in many NIO applications because channels read and write sequences of bytes.

### 4.1. Creating a ByteBuffer

~~~java
ByteBuffer heap = ByteBuffer.allocate(1024);
ByteBuffer direct = ByteBuffer.allocateDirect(1024);

byte[] source = {10, 20, 30};
ByteBuffer wrapped = ByteBuffer.wrap(source);
~~~

Distinction:

- `allocate(1024)` allocates a **heap byte buffer**; elements are usually backed by a byte array on the heap. `isDirect()` is `false`.
- `allocateDirect(1024)` creates a **direct byte buffer**; the JVM attempts to reserve memory suitable for native I/O operations. `isDirect()` is `true`. Allocation and management overhead can be higher; it is not automatically faster by default.
- `wrap(source)` creates a buffer backed by an **existing array** and shares its contents with that array. Modifying elements through the buffer can alter the original array and vice versa.

`ByteBuffer.wrap(array, offset, length)` creates a buffer with `capacity=array.length`, `position=offset`, and `limit=offset+length`. It does **not** automatically slice the array into a buffer starting at position 0. To get a new view starting at 0, use `slice()` after setting `position`/`limit` appropriately.

### 4.2. Writing and Reading: Relative and Absolute Operations

~~~java
ByteBuffer b = ByteBuffer.allocate(4);

b.put((byte) 10);             // Writes at position and increments position.
b.put((byte) 20);
byte second = b.get(1);       // Absolute read at index 1; position DOES NOT change.
int p = b.position();         // p == 2

b.flip();
byte first = b.get();         // Relative read at index 0, then increments position.
~~~

Common overloads:

| API | Meaning |
| --- | --- |
| `get()` / `put(byte)` | Reads/writes a single byte at position and advances position. |
| `get(index)` / `put(index, value)` | Reads/writes at an absolute index; does not change position. |
| `get(byte[])` / `put(byte[])` | Transfers multiple bytes, updating position by the number of elements transferred. |
| `getInt()` / `putInt(int)` | Reads/writes 4 bytes as an `int`, according to the buffer's `ByteOrder`. |
| `getLong()` / `putLong(long)` | Reads/writes 8 bytes as a `long`, according to `ByteOrder`. |
| `getChar()` / `putChar(char)` | Reads/writes a `char` as two bytes according to byte order; **not** UTF-8 transcoding. |

For absolute `get(index)`/`put(index, ...)`, the index is checked against `limit`; you cannot arbitrarily access past `limit` even if `capacity` is larger. When checking how many elements are available, use `remaining()` and `hasRemaining()`.

### 4.3. Byte Order (Endianness)

Multi-byte data requires a convention for which byte comes first:

- **Big-endian**: the most significant byte is written first.
- **Little-endian**: the least significant byte is written first.

~~~java
ByteBuffer b = ByteBuffer.allocate(4);
b.order(ByteOrder.LITTLE_ENDIAN);
b.putInt(0x01020304);
// Four bytes in the buffer: 04 03 02 01
~~~

By default, `ByteBuffer` uses `ByteOrder.BIG_ENDIAN`; when reading/writing a binary protocol, you must choose the exact convention specified by the protocol. Using the wrong byte order can yield incorrect integers even when all bytes were received.

`order(ByteOrder)` does **not** convert existing data; it determines how subsequent multi-byte read/write operations interpret bytes. Primitive view buffers created from a `ByteBuffer` capture the appropriate byte order at creation time; changing the byte order later requires deliberate design.

## 5. CharBuffer: A Character Container, Different from ByteBuffer

`CharBuffer` holds elements of Java type `char`, each being a UTF-16 code unit. It is appropriate when you already have character data or when a decoder converts bytes into characters.

~~~java
CharBuffer a = CharBuffer.allocate(10);
a.put('J').put('a').put('v').put('a');
a.flip();
System.out.println(a.toString()); // Java

CharBuffer b = CharBuffer.wrap("Hello");
System.out.println(b.get());      // H
~~~

These are **illustrative snippets** with `java.nio.CharBuffer` imported. Distinguish the two forms of `wrap`:

- `CharBuffer.wrap(char[])` shares the `char[]` array and is usually writable through the buffer unless the array/buffer is turned into read-only.
- `CharBuffer.wrap(CharSequence)`, such as `wrap("Hello")`, creates a **read-only** buffer backed by the character sequence; calling `put` on this buffer throws `ReadOnlyBufferException`.

`CharBuffer` implements `CharSequence` and useful methods such as `length()`, `charAt(...)`, `subSequence(...)`, and `toString()`. `toString()` reflects **the remaining characters from position to limit**, not automatically the entire capacity.

Do not equate a single `char` with a complete Unicode character: characters outside the Basic Multilingual Plane (such as some emojis) require a **surrogate pair**, i.e., two `char` elements. To count *code points*, follow Unicode rules, for example via `String.codePointCount(...)` on the resulting string.

### 5.1. Converting Between ByteBuffer and CharBuffer Using Charset

**Byte ≠ char.** To convert text to bytes, you must know the charset such as UTF-8. Do not use `ByteBuffer`'s `getChar()`/`putChar()` as a substitute for a UTF-8 encoder/decoder.

~~~java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.StandardCharsets;

ByteBuffer bytes = StandardCharsets.UTF_8.encode("Tiếng Việt");
CharBuffer chars = StandardCharsets.UTF_8.decode(bytes);
System.out.println(chars.toString()); // Tiếng Việt
~~~

This is an illustrative snippet placed inside `main`. The `Charset.encode`/`decode` helpers return a buffer with position/limit positioned to read the output. `decode(bytes)` **consumes the read position of bytes**; if you need to read the bytes again later, deliberately `rewind`/`duplicate` it.

In applications processing multiple chunks of bytes, a UTF-8 character can be split across two read calls. In that case, use `CharsetDecoder` in streaming mode, handle the `CoderResult`, and retain leftover partial bytes; do not arbitrarily decode each chunk independently, as that can produce replacement characters or decoding errors.

## 6. Other Primitive Buffer Types

| Buffer | Element Type | Capacity `allocate(n)` | Use Case |
| --- | --- | --- | --- |
| `ByteBuffer` | `byte` (8-bit) | `n` bytes | Files, sockets, protocols, binary payloads. |
| `CharBuffer` | `char` (16-bit) | `n` UTF-16 code units | Characters after decoding, text processing. |
| `ShortBuffer` | `short` (16-bit) | `n` `short` values | 16-bit binary values. |
| `IntBuffer` | `int` (32-bit) | `n` `int` values | Integer data, binary views. |
| `LongBuffer` | `long` (64-bit) | `n` `long` values | 64-bit integers. |
| `FloatBuffer` | `float` (32-bit) | `n` `float` values | 32-bit floating-point data. |
| `DoubleBuffer` | `double` (64-bit) | `n` `double` values | 64-bit floating-point data. |

For example:

~~~java
IntBuffer numbers = IntBuffer.allocate(3);
numbers.put(10).put(20).put(30);
numbers.flip();

while (numbers.hasRemaining()) {
    System.out.println(numbers.get());
}
~~~

Output:

~~~text
10
20
30
~~~

This snippet requires `import java.nio.IntBuffer;` and must be placed inside a Java method. The loop reads **by `int` element**, not byte by byte.

Many typed buffers also support `wrap(array)`, `slice()`, `duplicate()`, `asReadOnlyBuffer()`, `get`/`put`, and corresponding operations to view data; memory allocation details and backing-array support depend on the buffer type and how it was created.

## 7. View Buffers, slice, duplicate, and read-only

This group of APIs is error-prone because multiple buffers **share the same underlying data region**, even though their `position` and `limit` states are independent.

| Creation Method | Data | Position/limit | Characteristics |
| --- | --- | --- | --- |
| `duplicate()` | Shares memory with the original buffer. | Copies initial state, then moves independently. | Modifying a byte via one buffer is visible in the other. |
| `slice()` | Shares the subsequence from position to limit of the original buffer. | New view starts with position=0 and capacity=remaining at slice time. | Index 0 of the slice corresponds to the original's position at the time of slicing. |
| `asReadOnlyBuffer()` | Shares data with the original. | Independent position state. | Writing through the view is forbidden, even though the original can still write. |
| `asIntBuffer()` and other primitive views | Shares bytes as primitive-typed data. | Position/limit counted in **elements of the view type**. | Interprets bytes using the source's byte order at the time the view is created. |

Example of `slice()`:

~~~java
ByteBuffer original = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
original.position(1);
original.limit(3);

ByteBuffer view = original.slice(); // View contains 20, 30.
view.put(0, (byte) 99);             // Replaces the first byte of the slice.

System.out.println(original.get(1)); // 99
System.out.println(original.position()); // 1
~~~

**Why is the original's position still 1?** Because `view.put(0, ...)` is an absolute access inside the slice; the two buffers share data but do not share cursors. Likewise, `duplicate()` does not synchronize cursors.

### 7.1. Primitive View from ByteBuffer

~~~java
ByteBuffer bytes = ByteBuffer.allocate(8);
bytes.order(ByteOrder.BIG_ENDIAN);
IntBuffer ints = bytes.asIntBuffer();

ints.put(0, 42);
ints.put(1, 7);

System.out.println(bytes.getInt(0)); // 42
System.out.println(bytes.getInt(4)); // 7
~~~

This is an illustrative snippet with imports `java.nio.ByteBuffer`, `java.nio.ByteOrder`, and `java.nio.IntBuffer`. `asIntBuffer()` creates a view over the remaining bytes, with capacity measured in groups of 4 bytes. Calling `ints.put(index, value)` modifies the shared memory; `bytes.getInt(...)` reads back the same bytes.

If the number of remaining bytes is not divisible by the element type size, the view contains only the **whole** elements that can be represented. Byte order and alignment can affect correctness or performance in low-level operations.

## 8. Heap Buffer and Direct Buffer

`ByteBuffer.allocate(...)` and `ByteBuffer.allocateDirect(...)` both provide similar read/write APIs, but differ in how memory is managed.

| Criterion | Heap ByteBuffer | Direct ByteBuffer |
| --- | --- | --- |
| Creation | `ByteBuffer.allocate(n)` | `ByteBuffer.allocateDirect(n)` |
| `isDirect()` | `false` | `true` |
| Backing array | Usually accessible via `array()` if writable and backed by an array. | Must not assume an accessible Java array exists. |
| Allocation/deallocation | Primarily managed by Java heap memory mechanisms. | Incurs native memory management overhead and depends on JVM/GC. |
| Native I/O | May require intermediate copy operations. | Can reduce extra copies with suitable channel I/O. |
| When to choose | Small, short-lived buffers, general data manipulation. | Large/reused buffers, I/O where benchmarks prove a benefit. |

**Do not call `array()` without checking availability.** `hasArray()` returns `false` for direct buffers and read-only buffers; `array()` may throw `UnsupportedOperationException` or `ReadOnlyBufferException` depending on the buffer type. Even when an array exists, pay attention to `arrayOffset()` and the position of any view/slice.

When you need to read any `ByteBuffer` into an independent array, you can do the following:

~~~java
ByteBuffer copy = source.duplicate();
byte[] bytes = new byte[copy.remaining()];
copy.get(bytes);
~~~

This is an illustrative snippet where `source` is an existing `ByteBuffer`. It extracts the **remaining bytes** of `source` at that moment. Using `duplicate()` preserves `source`'s position and works with heap, direct, and read-only buffers alike.

Do not allocate direct buffers for every operation believing they are guaranteed to be faster. Data size, reuse frequency, providers, encoding operations, and the actual I/O path determine effectiveness; if performance matters, benchmark on the real workload.

## 9. MappedByteBuffer: Mapping File Regions

`MappedByteBuffer` extends `ByteBuffer`. Through `FileChannel.map(...)`, an application can map a region of a file into memory and read/write via the buffer API.

~~~java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    MappedByteBuffer mapped = channel.map(
            FileChannel.MapMode.READ_WRITE, 0, channel.size());

    if (mapped.hasRemaining()) {
        byte first = mapped.get(0);
        mapped.put(0, (byte) (first + 1));
        mapped.force();
    }
}
~~~

This is an **illustrative snippet**; it requires importing `java.nio.MappedByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Path`, and `java.nio.file.StandardOpenOption`, and requires a valid `path` file. `force()` requests flushing mapping changes to the storage device per the API contract; mapping behavior, durability, and interaction with external file modifications also depend on the platform and map mode.

Closing `FileChannel` **does not necessarily unmap the memory region immediately**. The mapping's lifetime can extend until the buffer is reclaimed. Do not use mmap as a default choice; it has limitations regarding resource management, file locking, or coordinating multi-process reads/writes.

## 10. How Does Buffer Work with Channel?

When reading from a channel into a `ByteBuffer`:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(4096);
int n = channel.read(buffer);  // Channel writes bytes into buffer.
buffer.flip();                 // Switch to reading what was just received.

while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Process value...
}

buffer.clear();                // Ready for the next pass.
~~~

This is an **illustrative snippet** assuming `channel` supports `read(ByteBuffer)` and has been initialized. The `read` call can return:

- A positive number: the actual number of bytes received, which may be smaller than the available space.
- `0`: no bytes were transferred in that call (for instance, on a non-blocking channel that is not ready).
- `-1`: end-of-stream (EOF) has been reached for channels that support this contract.

Never assume a **single** `read` is guaranteed to fill the buffer or a single `write` is guaranteed to flush all `remaining()` bytes; for channels allowing partial I/O, use appropriate loops and waiting rules.

### 10.1. When Unprocessed Data Remains: Use compact()

Suppose an application receives data packets where a message is split across two reads. After processing the complete messages in the buffer, retain the incomplete trailing bytes:

~~~java
buffer.flip();           // Read the newly received data.
consumeCompleteFrames(buffer); // Advances position only past complete frames.
buffer.compact();        // Keep bytes not yet belonging to a complete frame.
~~~

This is **illustrative pseudocode**; `consumeCompleteFrames` is an application-defined function, not a Java API. The example explains why `compact()` is valuable: `clear()` would reset the cursor and allow unprocessed data to be overwritten.

When writing a buffer out to a channel, the buffer is normally already in read mode after `flip()`:

~~~java
while (buffer.hasRemaining()) {
    int written = channel.write(buffer);
    if (written == 0) {
        // For non-blocking channels, register/wait for write readiness.
        break;
    }
}
~~~

This snippet illustrates flow control; if stopping on `written == 0`, the application must **preserve the remaining bytes** to continue when the channel becomes ready. For blocking channels, the waiting semantics differ. Do not use an infinite busy-spin loop on a non-blocking channel.

## 11. Runnable Program on Java 17+: Multiple Buffer Types and compact()

Save the following content to `BufferDemo.java`. The program uses deterministic operations and does not depend on the OS or external files.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.CharBuffer;
import java.nio.IntBuffer;
import java.nio.charset.StandardCharsets;
import java.util.HexFormat;

public class BufferDemo {
    public static void main(String[] args) {
        ByteBuffer bytes = ByteBuffer.allocate(8);
        bytes.order(ByteOrder.BIG_ENDIAN);
        bytes.putInt(0x01020304);
        bytes.put((byte) 'A');
        bytes.flip();

        System.out.println("capacity=" + bytes.capacity());
        System.out.println("limit=" + bytes.limit());
        System.out.println("hex=" + Integer.toHexString(bytes.getInt()));
        System.out.println("letter=" + (char) bytes.get());
        System.out.println("hasRemaining=" + bytes.hasRemaining());

        bytes.clear();
        bytes.put((byte) 'B');
        bytes.flip();
        System.out.println("reuse=" + (char) bytes.get());

        CharBuffer chars = CharBuffer.wrap("Java");
        System.out.println("charRemaining=" + chars.remaining());
        System.out.println("firstChar=" + chars.get());

        IntBuffer numbers = IntBuffer.allocate(3);
        numbers.put(10).put(20).put(30);
        numbers.flip();
        System.out.println("sum=" + (numbers.get() + numbers.get() + numbers.get()));

        ByteBuffer partial = ByteBuffer.allocate(8);
        partial.put("abcde".getBytes(StandardCharsets.US_ASCII));
        partial.flip();
        partial.get(); // Consume a.
        partial.get(); // Consume b.
        partial.compact(); // Keep cde.
        partial.put("FG".getBytes(StandardCharsets.US_ASCII));
        partial.flip();

        byte[] remaining = new byte[partial.remaining()];
        partial.get(remaining);
        System.out.println("compact=" +
                new String(remaining, StandardCharsets.US_ASCII));

        ByteBuffer little = ByteBuffer.allocate(4);
        little.order(ByteOrder.LITTLE_ENDIAN);
        little.putInt(0x01020304);
        System.out.println("littleEndian=" +
                HexFormat.of().formatHex(little.array()));

        ByteBuffer encoded = StandardCharsets.UTF_8.encode("Tiếng Việt");
        CharBuffer decoded = StandardCharsets.UTF_8.decode(encoded);
        System.out.println("decoded=" + decoded);
    }
}
~~~

Compile/run:

~~~bash
javac BufferDemo.java
java BufferDemo
~~~

Stdout:

~~~text
capacity=8
limit=5
hex=1020304
letter=A
hasRemaining=false
reuse=B
charRemaining=4
firstChar=J
sum=60
compact=cdeFG
littleEndian=04030201
decoded=Tiếng Việt
~~~

Explanation of the key lines:

1. After `putInt` (4 bytes) and `put('A')` (1 byte), `position=5`. `flip` sets `limit=5` to read exactly 5 bytes, while `capacity` remains 8.
2. `getInt()` reads four big-endian bytes and returns `0x01020304`; `Integer.toHexString` prints `1020304` (without leading zeros). The next `get()` reads `'A'`, leaving no elements between position and limit.
3. `clear` allows writing back into the existing memory, rather than erasing contents. `put('B')`/`flip` creates a new data pass containing a single byte.
4. `CharBuffer.wrap("Java")` has four `char` values remaining; reading the first element yields `J`.
5. `IntBuffer` holds three integers, so the sum is 60.
6. With `partial`, two bytes `a` and `b` are read; `compact` retains `cde`, then appends `FG` so the final readable region is `cdeFG`.
7. Little-endian byte order represents `0x01020304` as the hex byte sequence `04 03 02 01`.
8. UTF-8 encoding/decoding preserves the string `Tiếng Việt`. This process converts **bytes** into **chars** and does not depend on the `ByteBuffer`'s byte order.

## 12. Common Errors and Diagnosis

| Issue | Typical Cause | Resolution |
| --- | --- | --- |
| `BufferUnderflowException` | Calling `get` when `remaining()` has fewer elements than required. | Check buffer state and required byte count before reading. |
| `BufferOverflowException` | Calling `put` past `limit` or when no space remains. | Check `remaining()`, allocate enough capacity, call `clear`/`compact` at the right step. |
| `InvalidMarkException` | Calling `reset()` when mark has not been set or was cleared. | Call `mark()` at an appropriate position and understand how `flip/clear/rewind` affect it. |
| `ReadOnlyBufferException` | Writing to a read-only buffer/view. | Use a different writable buffer or create a copy of the data. |
| `IndexOutOfBoundsException` | Accessing an invalid absolute index relative to limit or the specified range. | Use position/limit properly and validate before reading/writing. |
| `UnsupportedOperationException` on `array()` | Buffer has no accessible backing array. | Use `hasArray()` or `duplicate().get(byte[])`. |
| Missing read data | Forgetting `flip()`, or a single channel read returned fewer bytes than expected. | Manage state properly and handle partial reads. |
| Loss of unprocessed data | Calling `clear()` instead of `compact()` after consuming only part of the buffer. | Retain `remaining` with `compact` when needed. |
| Wrong binary numbers | Wrong `ByteOrder` or reading the wrong type (e.g., `getShort` instead of `getInt`). | Check against the data/protocol specification. |
| Garbled characters | Using `getChar()` instead of a decoder or splitting a UTF-8 character across two chunks. | Pick the right `Charset` and process multi-chunk streams with a decoder. |

### Safe Usage Principles

- **Buffers are not thread-safe by default.** If multiple threads read/write the same buffer, synchronization or clear ownership design is required. `duplicate()` separates cursors while still sharing data, so it does not solve race conditions on its own.
- **Do not guess `position`/`limit` state.** Document the input/output flow, use `remaining()`, and inspect read/write counts and positions after each step when diagnosing issues.
- **Do not assume `array()` works on every buffer.** Direct, read-only, and view buffers may not expose an array; when an array is exposed, `arrayOffset()` gives the proper index mapping.
- **Do not use `clear()` to wipe secrets from memory.** It only changes logical state; clearing sensitive data requires an explicit overwrite routine while also accounting for any existing copies of the data.
- **Do not treat element counts as byte counts for all buffers.** `IntBuffer.remaining()` counts `int`s; when computing binary data size, multiply by bytes per element explicitly.
- **Comparison methods may operate on remaining elements.** `equals` and `compareTo` on many typed buffers compare the region from `position` to `limit`; buffers sharing the same storage with different positions may not be equal.
- **Size buffers based on real workload.** Buffers that are too small can increase I/O call counts; buffers that are too large increase memory overhead. Direct buffers require extra attention to lifecycle and reuse.

## 13. Self-Check Questions

1. **What are the initial `position`, `limit`, and `capacity` of `ByteBuffer.allocate(10)`?** `0, 10, 10` respectively.
2. **After writing 4 bytes into a buffer of capacity 10 and calling `flip()`?** `position=0`, `limit=4`, `capacity=10`; exactly 4 bytes are in the region ready to be read.
3. **If you have read part of a buffer and want to keep the remaining bytes to receive more data, what should you call?** `compact()`, then write more data and `flip()` before the next read pass.
4. **Does `clear()` write zeros to all old bytes?** No. It only resets position to 0 and limit to capacity.
5. **Does `ByteBuffer.wrap(array)` copy the array's contents?** No. Its contents are shared with the original array.
6. **Do `duplicate()` and `slice()` have data independent from the original?** No. They share the backing storage; only `position`/`limit` state is independent.
7. **Does `CharBuffer` store UTF-8 bytes directly?** No. It stores `char`s, which are UTF-16 code units. To convert between bytes and characters, use `Charset`/encoders/decoders.
8. **What bytes does `ByteBuffer.putInt(0x01020304)` produce in little-endian order?** `04 03 02 01`.
9. **Does `ByteBuffer.allocateDirect(100)` guarantee `array()` can be used?** No. Access bytes via `get/put` or copy `remaining` into an array.
10. **Why is a single `FileChannel.read` insufficient to conclude a full message has arrived?** Because a single read may transfer fewer bytes than needed; the program must manage the buffer and continue reading according to the protocol.

**Remember:** `Buffer` defines **data region state**; `ByteBuffer` is the tool for working with **bytes and channel I/O**; `CharBuffer` and typed buffers interpret **elements by specific type**. The most important practical rule is **write → flip → read → clear or compact**, while keeping track of `position`, `limit`, `capacity`, byte order, and memory sharing.
