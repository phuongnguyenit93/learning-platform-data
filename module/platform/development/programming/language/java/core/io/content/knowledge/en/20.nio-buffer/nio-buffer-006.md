# NIO Buffer: Relative and Absolute `get` and `put` in Java

In `java.nio`, a **Buffer** is a data region with read/write state: `capacity`, `limit`, and `position`. The two core groups of operations are **relative** and **absolute**:

- **Relative** `get()` and `put(value)` operate at the current `position`, and then **increment `position`**.
- **Absolute** `get(index)` and `put(index, value)` operate directly at `index`, **without changing `position`**.

This is the fundamental distinction for sequential reading, sequential writing, peeking at data ahead, patching a known offset, and building binary parsers. "Absolute" here means an **index inside the buffer**, not a RAM address, file byte offset, or `FileChannel` position.

## 1. Understand Buffer State Before Using get/put

Every `Buffer` has three core properties:

| Property | Meaning |
| --- | --- |
| `capacity()` | Total number of elements the buffer can hold; immutable throughout that buffer's lifetime. |
| `limit()` | The **exclusive** boundary of the region currently permitted for reading or writing. |
| `position()` | Index of the next element for a **relative** operation. |

Invariants:

```text
0 <= position <= limit <= capacity
remaining = limit - position
```

Valid indices for a single-element absolute access are **`0` through `limit - 1`**, not merely anything smaller than `capacity`. If `limit = 3` and `capacity = 8`, `get(3)` is still out of bounds; `capacity` alone does not authorize accessing past `limit`.

Example of a capacity-8 buffer after writing three bytes relatively:

```text
Index:       0    1    2    3    4    5    6    7
Content:    10   20   30    ?    ?    ?    ?    ?
                             ^
position = 3, limit = 8, capacity = 8
```

When `flip()` is called, state transitions to `position = 0, limit = 3, capacity = 8`. Now three elements have been written and can be read via relative operations, while absolute `get(3)` or `put(3, value)` is rejected because `index >= limit`.

**Allocated byte space does not equal valid data.** `ByteBuffer.allocate` initializes memory to zeros, yet the program must still track which portion was actually written and manage `position`/`limit` properly.

## 2. Relative get/put: Read/Write and Advance the Cursor

The following examples use `ByteBuffer`, where the index unit is **bytes**:

```java
ByteBuffer b = ByteBuffer.allocate(5);    // position=0, limit=5
b.put((byte) 10);                         // writes index 0; position=1
b.put((byte) 20);                         // writes index 1; position=2
b.put((byte) 30);                         // writes index 2; position=3
b.flip();                                 // position=0, limit=3
byte a = b.get();                         // a=10; position=1
byte c = b.get();                         // c=20; position=2
```

This is an illustrative snippet; it requires `import java.nio.ByteBuffer;` and must be placed inside a valid Java method.

For `get()`, the buffer needs at least one remaining element (`position < limit`). For `put(value)`, space must also remain in the buffer's writable region. Otherwise:

- `get()` when `remaining() == 0` throws **`BufferUnderflowException`**.
- `put(value)` when `remaining() == 0` throws **`BufferOverflowException`**, subject to other constraints such as a read-only buffer.
- `ByteBuffer.put` returns the buffer itself so calls can be chained: `put(...).put(...)`.
- For `byte`, the result of `get()` is signed (`-128..127`). If you want an unsigned `0..255` integer, use `b.get() & 0xFF`.

You do not need to call `position(position() + 1)` manually after a relative `get`/`put`: the API already advances `position`. Incrementing it yourself skips elements.

## 3. Absolute get/put: Access an Index While Keeping position Unchanged

With an open `ByteBuffer b` in a valid state:

```java
byte first = b.get(0);      // Reads element 0, position unchanged.
b.put(1, (byte) 99);       // Overwrites element 1, position unchanged.
```

Points to remember:

1. Indices are **zero-based**; a negative index or `index >= limit` throws **`IndexOutOfBoundsException`** for single-element operations.
2. `get(index)` does not consume data at the current `position`. For instance, if `position = 2`, calling `get(0)` leaves `position = 2`.
3. `put(index, value)` does not append an element after the "already processed" part; it **overwrites** the element at the given index. If the buffer is writable and the index is valid, the old value there changes.
4. `get(index)` can still read even when `position == limit`, provided `index` lies in `[0, limit)`, because absolute operations do not pull from the current `position`.
5. `put(index, value)` does not move `position`, does not alter `limit`, and does not update "valid written byte count" for `flip()` to discover automatically.

Point 5 is the easiest trap to fall into:

```java
ByteBuffer b = ByteBuffer.allocate(4); // position=0, limit=4
b.put(2, (byte) 7);                    // position stays 0
b.flip();                              // limit becomes 0!
System.out.println(b.remaining());    // 0
```

This example shows that **`flip()` uses the old `position` as the new `limit`**; it does not scan memory to detect every index modified by `put(index, ...)`. If you intentionally store a fixed structure, manage the valid region explicitly (for example, write sequentially first, then use absolute `put` to patch the header) and only call `flip` once `position` reflects the prepared data length.

## 4. Standalone Java 17+ Example: Direct Comparison

Save as **`RelativeAbsoluteBufferDemo.java`**:

```java
import java.nio.BufferUnderflowException;
import java.nio.ByteBuffer;

public class RelativeAbsoluteBufferDemo {
    private static String state(ByteBuffer b) {
        return "pos=" + b.position()
                + " limit=" + b.limit()
                + " capacity=" + b.capacity();
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(6);
        System.out.println("initial: " + state(b));

        // Relative put: increments position on each write.
        b.put((byte) 10).put((byte) 20).put((byte) 30);
        System.out.println("relative put: " + state(b));

        // Absolute put: overwrites index 1; position unchanged.
        b.put(1, (byte) 99);
        System.out.println("absolute put: " + state(b));

        // Switch from writing to reading the 3 prepared bytes.
        b.flip();
        System.out.println("flip: " + state(b));

        // Absolute get: peek at the second byte without consuming it.
        System.out.println("peek get(1): " + b.get(1));
        System.out.println("after peek: " + state(b));

        // Relative get: read and advance position.
        System.out.println("consume get(): " + b.get());
        System.out.println("after consume: " + state(b));
        System.out.println("remaining=" + b.remaining());

        // Rewind to re-read the entire [0, limit) range.
        b.rewind();
        System.out.println("rewind: " + state(b));
        System.out.println(
                "values=" + b.get() + "," + b.get() + "," + b.get());

        try {
            b.get(); // position == limit, no bytes left to read.
        } catch (BufferUnderflowException e) {
            System.out.println("read past limit: BufferUnderflowException");
        }

        b.clear(); // Only resets state, does not erase bytes in memory.
        System.out.println("clear: " + state(b));
        try {
            b.get(6); // index equal to limit is invalid.
        } catch (IndexOutOfBoundsException e) {
            System.out.println("get(6): IndexOutOfBoundsException");
        }
    }
}
```

Compile and run (Java 17 or higher):

```bash
javac RelativeAbsoluteBufferDemo.java
java RelativeAbsoluteBufferDemo
```

Stdout:

```text
initial: pos=0 limit=6 capacity=6
relative put: pos=3 limit=6 capacity=6
absolute put: pos=3 limit=6 capacity=6
flip: pos=0 limit=3 capacity=6
peek get(1): 99
after peek: pos=0 limit=3 capacity=6
consume get(): 10
after consume: pos=1 limit=3 capacity=6
remaining=2
rewind: pos=0 limit=3 capacity=6
values=10,99,30
read past limit: BufferUnderflowException
clear: pos=0 limit=6 capacity=6
get(6): IndexOutOfBoundsException
```

Walkthrough:

- Three relative `put`s write to indices 0, 1, and 2 in turn; `position` advances to 3.
- `put(1, 99)` changes byte 20 to 99, while `position` stays 3; thanks to that, `flip` sets the exact `limit = 3`.
- After `flip`, `get(1)` returns 99 while `position` remains 0; `get()` reads 10 and increments `position` to 1.
- `rewind` preserves limit 3 and resets position to 0, allowing `10,99,30` to be read again.
- Relative reading past limit causes underflow; absolute reading at an index equal to limit causes `IndexOutOfBoundsException`. Those are **two distinct errors**.
- `clear` resets state to `position=0, limit=capacity`; it does not wipe array memory, so it must not be treated as a way to sanitize sensitive data.

## 5. Exact Comparison Table of Operations

| Category | `ByteBuffer` API | Read/Write Location | After Success | Typical Out-of-Bounds |
| --- | --- | --- | --- | --- |
| Relative get | `get()` | Current `position` | `position += 1` | `BufferUnderflowException` |
| Relative put | `put(byte)` | Current `position` | `position += 1` | `BufferOverflowException` |
| Absolute get | `get(int index)` | Specified `index` | `position` unchanged | `IndexOutOfBoundsException` |
| Absolute put | `put(int index, byte)` | Specified `index` | `position` unchanged | `IndexOutOfBoundsException` |
| Relative typed get | `getInt()` | 4 bytes from `position` | `position += 4` | `BufferUnderflowException` |
| Absolute typed get | `getInt(index)` | 4 bytes from `index` | `position` unchanged | `IndexOutOfBoundsException` |
| Relative typed put | `putInt(value)` | 4 bytes from `position` | `position += 4` | `BufferOverflowException` |
| Absolute typed put | `putInt(index, value)` | 4 bytes from `index` | `position` unchanged | `IndexOutOfBoundsException` |

`getInt(index)` and `putInt(index, value)` require **all four bytes** to lie before `limit`, i.e., `index >= 0` and `index + 4 <= limit`. Likewise `getLong`/`putLong` require 8 bytes. For write calls, a read-only buffer can also throw `ReadOnlyBufferException`.

The table uses `ByteBuffer` for illustration; `IntBuffer`, `LongBuffer`, `CharBuffer`, `ShortBuffer`, `FloatBuffer`, and `DoubleBuffer` also have relative and absolute `get`/`put` in **their own element units**. For example, `IntBuffer.get(2)` means the third `int` element, not byte offset 2.

## 6. Understanding limit, flip, clear, rewind, and compact

These methods **manage state**, without copying data into a new buffer:

| Method | Position After | Limit After | Purpose |
| --- | --- | --- | --- |
| `flip()` | 0 | Position **before** call | Switch sequentially written data into read mode. |
| `clear()` | 0 | Capacity | Prepare to write from the start; **does not** erase old bytes. |
| `rewind()` | 0 | Keep limit unchanged | Re-read the current region from the start. |
| `compact()` | Remaining elements before call | Capacity | Shift unread portion to the front and prepare to write more. |
| `position(n)` | n | Keep limit unchanged | Set the relative cursor within the valid range. |
| `limit(n)` | May be clamped down to n | n | Change valid region; position cannot exceed limit. |

Example processing loop when data arrives in batches:

```text
WRITE:
position = bytes placed into buffer, limit = capacity
      |
      | flip()
      v
READ:
position = bytes consumed, limit = bytes containing data
      |
      | compact() if remaining bytes are not yet enough for a message
      v
CONTINUE WRITING:
unread bytes sit at the front of the buffer
position = retained byte count, limit = capacity
```

A typical workflow: `channel.read(buffer)` writes at the current position → `buffer.flip()` → process via `buffer.get()` → `buffer.compact()` to retain partial data; or `clear()` when sure everything has been consumed. At end-of-stream, `flip()` and process any remainder according to protocol rules. If data consists of 4-byte integers or multi-byte UTF-8 sequences, never assume each read batch delivers a complete unit; the parser must preserve incomplete parts.

**Note:** `compact()` can copy bytes between positions; any previously saved absolute index may no longer point to the intended message offset. Recompute positions and maintain clear state reasoning.

## 7. Absolute get Is Commonly Used to Peek Headers and Patch Offsets

A binary parser may want to peek at a header without advancing the cursor:

```java
// Snippet: assume b is a flipped ByteBuffer with >= 4 bytes remaining.
if (b.remaining() >= Integer.BYTES) {
    int magic = b.getInt(b.position()); // peek: position unchanged
    if (magic == 0x01020304) {
        int consumed = b.getInt();     // relative: advances 4 bytes
        // consumed == magic
    }
}
```

By default `ByteBuffer` uses `ByteOrder.BIG_ENDIAN`. If the protocol requires little-endian, configure `b.order(ByteOrder.LITTLE_ENDIAN)` and ensure writer and reader agree. Both `getInt()` and `getInt(index)` use that buffer's byte order; relative vs. absolute nature does **not** determine byte order.

A common technique is reserving space for a length header, writing the payload, and then going back to fill in the header with an absolute `put`. This keeps `position` at the end of the payload:

```java
import java.nio.ByteBuffer;

ByteBuffer b = ByteBuffer.allocate(64);
b.putInt(0);                 // Reserve 4 bytes for length; position=4.
int start = b.position();   // start=4
b.put(new byte[] {7, 8, 9});
int length = b.position() - start; // 3
b.putInt(0, length);        // Patch header; position stays = 7.
b.flip();                   // limit=7; ready to read.
int payloadLength = b.getInt(); // 3; position=4.
```

This is a **snippet** relying on imports and variables in context; it shows how to use relative `put` to establish the valid data extent and then absolute `put` to overwrite the header. However, it does not form a complete framing protocol on its own: the receiver must still validate `length >= 0`, bounds, and actual available bytes before reading the payload.

An absolute index belongs to the buffer **currently being used**. If the buffer is a slice starting in the middle of another buffer, `index=0` of the slice corresponds to the slice's first element, not necessarily element 0 of the original buffer.

## 8. Bulk get/put: Operating on a Group of Elements

With Java 17+, `ByteBuffer` supports both relative bulk and absolute bulk methods:

```java
ByteBuffer b = ByteBuffer.allocate(5);
b.put(new byte[] {11, 22, 33});   // relative: position=3
b.flip();                         // position=0, limit=3

byte[] firstTwo = new byte[2];
b.get(firstTwo);                  // relative: position=2

byte[] peek = new byte[2];
b.get(0, peek);                   // absolute bulk: position stays 2
```

`get(byte[])` reads a number of elements equal to the array length starting at `position` and increments `position`; if `remaining()` is insufficient, it throws underflow. `get(int index, byte[] dst)` reads from a fixed index without changing `position`. Variants with offset/length such as `get(index, dst, offset, length)` let you target a slice of the array. Absolute bulk methods on `ByteBuffer` are supported in Java 17; if building a library targeting older JDKs, check the API version.

Similarly, `put(byte[])` is a relative bulk write, while `put(index, src)` is an absolute bulk write. Do not confuse the **offset in the source/destination array** with the **index in the buffer**: they are two separate coordinate spaces.

If you need to process very large byte arrays, avoid loading everything into RAM at once; process in chunks, coordinating `remaining()` and checking format limits.

## 9. Read-only, duplicate, slice, and Shared Memory Regions

`duplicate()` creates a buffer with **independent `position`/`limit`/`mark` state** over the same data storage. `slice()` creates a view starting at the current `position` with capacity equal to `remaining()` at creation time; it also shares data, but indices inside the slice start from 0.

```java
ByteBuffer original = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
original.position(1); // original: position=1, limit=4

ByteBuffer duplicate = original.duplicate();
ByteBuffer slice = original.slice(); // slice index 0 -> original index 1

slice.put(0, (byte) 99); // Overwrites original index 1, without changing position.
System.out.println(original.get(1));  // 99
System.out.println(duplicate.position()); // 1
System.out.println(slice.position());     // 0
```

This is a snippet; it requires `import java.nio.ByteBuffer;`. Modifying contents through a slice or duplicate is visible from the other views, while cursors are managed independently. This is especially important when using absolute indices: the index is relative to **that view**, not a file position or global coordinate.

`asReadOnlyBuffer()` returns a read-only view that supports `get` but forbids `put`, whether relative or absolute. The contents of a read-only view can still change if the original writable buffer shares the same memory; it is not an immutable snapshot.

Never use `duplicate` as a concurrency-safety solution across threads: independent cursors do not give shared data transactions or synchronization. Define explicit synchronization and memory-ownership policies when multiple threads are involved.

## 10. Common Errors to Distinguish

| Situation | Behavior / Exception | How to Handle |
| --- | --- | --- |
| `get()` when `position == limit` | `BufferUnderflowException` | Use `hasRemaining()`, `remaining()`, or verify sufficient length before reading. |
| `put(value)` when out of space | `BufferOverflowException` | Ensure buffer is in write phase with enough capacity; drain/flush old content. |
| `get(index)` with `index < 0` or `index >= limit` | `IndexOutOfBoundsException` | Check against `limit`, not just `capacity`. |
| `put(index, value)` past limit | `IndexOutOfBoundsException` | Avoid indices outside the valid region; adjust state deliberately. |
| `put` on a read-only buffer | `ReadOnlyBufferException` | Use a writable buffer; do not mutate a read-only view. |
| `getInt()` when only 2 bytes remain | `BufferUnderflowException` | Require `remaining() >= 4` before reading. |
| `getInt(index)` without 4 bytes before limit | `IndexOutOfBoundsException` | Validate the whole span `[index, index+4)`. |
| `put(index, ...)` then `flip()` sees limit 0 | Position did not move after absolute write. | Establish the prepared region via relative writes or explicitly set `position` before `flip`. |
| `clear()` then reading old bytes | `clear` resets metadata, does not erase contents. | Never use `clear` as a wipe or proof of fresh data. |
| `slice().get(0)` differs from `original.get(0)` | Slice uses indices relative to the start of the view. | Adjust indices according to the slice offset. |
| Reading integers with wrong byte order | Mismatched byte order. | Set `order(...)` per schema and verify with sample data. |

A subtle conceptual mistake: **`position` is not the sole storage address of data**. A buffer may hold many bytes before or after `position`, yet `limit` defines the valid operation boundary; the application must still track which bytes truly represent a complete data field.

## 11. When to Use Relative and When to Use Absolute?

**Relative get/put** is appropriate when:

- Reading elements sequentially from a `flip`ped stream.
- Writing messages, binary files, or data blocks sequentially.
- Consuming bytes in a `while (b.hasRemaining())` loop.
- Relying on `position` to track how far processing has progressed.

**Absolute get/put** is appropriate when:

- Peeking at a header, magic number, length, checksum, or tag before deciding to consume it.
- Updating a field at a known index after writing the payload.
- Re-reading an earlier element without disturbing the relative processing loop.
- Accessing fields by offset table in an already validated binary structure.

Do not use absolute `put` in place of a full sequential write loop if you still intend to call `flip()` without manually managing `position`. Likewise, avoid doing every read by manually incrementing an index when a relative loop directly expresses your intent.

## 12. Self-Practice and Verification Exercises

**Exercise 1 — Reading exact state.** Initialize `ByteBuffer.allocate(4)`, then call in order `put((byte)5)`, `put(0,(byte)9)`, `flip()`, `get(0)`, `get()`. Record `position`/`limit` after each call. Answer: `(1,4)` → `(1,4)` → `(0,1)` → `(0,1)` → `(1,1)`; both final `get` calls return 9.

**Exercise 2 — Header length.** Extend the header-patching snippet: write a 4-byte length and a 5-byte payload, use absolute `getInt(0)` to inspect the length **without changing `position`**, then read via `getInt()`. Why do both calls return the same value yet leave different states afterward?

**Exercise 3 — Exception diagnosis.** With a `ByteBuffer.allocate(4)` that had 2 bytes written and was then `flip`ped, try `get(2)` and try calling `get()` three times. Predict accurately `IndexOutOfBoundsException` vs. `BufferUnderflowException`.

**Exercise 4 — Slice and independent cursors.** Use `wrap(new byte[]{1,2,3,4})`, set `position(2)`, create a slice, and call `slice.put(0,(byte)8)`. Observe `original.get(2)` and the positions of `original` and `slice`. Explain why the two positions are independent while the contents change together.

**Exercise 5 — Byte order.** Create `ByteBuffer.allocate(4)`, call `putInt(0x01020304)`, `flip()`, and read back with `getInt()`. Try reading each byte using absolute `get(index)`; then apply `order(ByteOrder.LITTLE_ENDIAN)` **before writing** a new buffer and compare the byte order.

### Quick Self-Assessment

- Do relative `get` and absolute `get(index)` both update `position`?
- Why is an absolute index bounded by `limit` rather than just `capacity`?
- Why does `putInt(index, value)` not automatically inform `flip()` that data is present?
- When reading a frame with a 4-byte header, what minimum `remaining()` is required before `getInt()`?
- After `compact()`, do previously recorded absolute indices still apply unchanged?

**Remember:** Relative get/put operates and advances `position`; absolute get/put accesses by `index` while leaving the cursor unchanged. Both obey `limit` and the buffer's read/write permissions; structure your write → `flip` → read → `compact/clear` phases clearly, especially when handling multi-batch binary data.
