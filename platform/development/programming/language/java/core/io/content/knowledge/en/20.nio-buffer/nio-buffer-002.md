# Capacity, position, limit, and mark in Java NIO Buffer

## 1. Why Does Buffer Need Four State Parameters?

In Java NIO, a **buffer** is a fixed-size data storage region that also maintains state for sequential reading and writing. These fundamental states are declared in `java.nio.Buffer` and appear in concrete classes such as `ByteBuffer`, `CharBuffer`, and `IntBuffer`:

- **capacity**: the maximum capacity of the buffer, fixed throughout that buffer's lifetime.
- **position**: the index of the next element to be operated on by **relative** (*relative*) reads/writes.
- **limit**: the exclusive upper bound of elements currently permitted to be accessed.
- **mark**: an optional saved position to which the cursor can return via `reset()`.

The tricky part of Buffer is that **the same memory region is used across multiple phases**. During the write phase, `position` usually indicates where the next element will be written. During the read phase, `position` usually indicates where the next element will be read. Therefore, to read data that was just written, the program must reset `position` and `limit` appropriately, typically using `flip()`.

For example, with `ByteBuffer.allocate(8)`: it has room for 8 bytes, so valid storage indices are 0–7. However, `limit` may be less than 8, in which case not all 8 positions belong to the region allowed for reading/writing in the current state.

## 2. Core Invariants of Buffer

At all times, a valid Buffer must satisfy:

\[
0 \leq position \leq limit \leq capacity
\]

If `mark` has been set, it must satisfy:

\[
0 \leq mark \leq position
\]

`mark` **may be undefined**; in that case, it must not be treated as a default number such as 0. The "no mark" state causes `reset()` to throw `InvalidMarkException`.

Consider a buffer with `capacity = 8`, `position = 3`, and `limit = 6`:

```text
Index:        0   1   2   3   4   5   6   7
Memory:      [ ] [ ] [ ] [ ] [ ] [ ] [ ] [ ]
                          ^
                       position = 3
                                       ^
                                    limit = 6
                                               ^
                                            capacity = 8

Relative operation range from position: [3, 6)
Remaining elements: limit - position = 3
```

In the diagram, `limit = 6` is the **boundary**, not an index of an element allowed to be accessed. When `position == limit`, there are no more elements left for relative operations.

| State | Obtained via | Meaning |
| --- | --- | --- |
| Capacity | `buffer.capacity()` | Total number of elements the buffer can hold |
| Position | `buffer.position()` | Index for the next relative operation |
| Limit | `buffer.limit()` | Upper bound, exclusive of this position |
| Mark | `buffer.mark()` / `buffer.reset()` | Saves and restores position; there is no `mark()` getter returning a number |
| Remaining | `buffer.remaining()` | `limit() - position()` |
| Has remaining | `buffer.hasRemaining()` | `position() < limit()` |

**The unit is elements of the Buffer's type**, not necessarily bytes. `ByteBuffer` tracks positions in bytes; `CharBuffer` in `char`s; `IntBuffer` in `int`s. When creating a view buffer, you must understand the position unit and its relationship to the underlying storage.

## 3. Initial State: `allocate`, `wrap`

Example:

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
```

Immediately after creation:

```text
capacity = 8
position = 0
limit    = 8
mark     = undefined
remaining = 8
```

This is the state **ready to write up to 8 bytes** using relative operations such as `put(byte)`. Newly written bytes advance `position`.

With `ByteBuffer.wrap(byte[])`, the buffer is created around an existing array. Normally `position = 0`, `limit = capacity = array.length`. **The fact that data is already in the array does not mean you must call `flip()` before reading**: `wrap` already sets the state so you can start reading from the first element.

Example:

```java
ByteBuffer wrapped = ByteBuffer.wrap(new byte[] {10, 20, 30});
System.out.println(wrapped.get()); // 10
```

Note: the `wrap(array, offset, length)` overload has a different initial state: `position = offset`, `limit = offset + length`, `capacity = array.length`. `offset` does not make the buffer's indices start at 0 as a newly sliced range.

## 4. `position`: Next Index and Movement on Read/Write

**Relative** (*relative*) operations use the current position:

```java
ByteBuffer b = ByteBuffer.allocate(5);
b.put((byte) 11);         // writes at index 0, position becomes 1
b.put((byte) 22);         // writes at index 1, position becomes 2
b.put((byte) 33);         // writes at index 2, position becomes 3
```

In contrast, **absolute** (*absolute*) operations specify an explicit index and do not move `position`:

```java
b.put(0, (byte) 99);      // replaces byte at index 0, position stays 3
byte first = b.get(0);    // reads byte at index 0, position stays 3
```

The two snippets above illustrate the same variable `b` and are not a complete program. When using absolute operations, the index must be valid relative to the current `limit`; access past `limit` is not permitted simply because `capacity` is larger.

**`position(int newPosition)`** can reposition the cursor directly without reading/writing data. `newPosition` must be between 0 and `limit`; if out of range, it throws `IllegalArgumentException`. If `position` is set below the current mark, the mark is discarded.

Do not assume that commands changing position alter bytes in storage. They **only change state**.

## 5. `limit`: Operation Boundary

`limit()` returns the **exclusive** upper bound index, meaning valid indices for absolute read/write fall within `[0, limit)`. `limit(int newLimit)` can decrease or increase the boundary, provided `0 <= newLimit <= capacity`.

If `newLimit` is set smaller than the current `position`, `position` is pulled down to the new limit to preserve the invariant. If `mark` exceeds the new limit, `mark` is discarded.

Example:

```java
ByteBuffer b = ByteBuffer.allocate(8);
b.position(5);
b.limit(3);
System.out.println(b.position()); // 3
System.out.println(b.limit());    // 3
```

After these two calls, no elements remain for relative operations: `remaining() == 0`.

**When `position == limit`:**

- `hasRemaining()` returns `false`.
- `remaining()` returns 0.
- Relative `get()` throws `BufferUnderflowException`.
- Relative `put(byte)` on a writable buffer throws `BufferOverflowException`.
- A read-only buffer throws `ReadOnlyBufferException` when any write operation is called.

Distinguishing `capacity` from `limit` helps prevent errors such as processing parts of storage that do not yet contain new data or writing beyond the boundary of the current phase.

## 6. `mark` and `reset`: Remembering a Position, Not Backing Up Data

`mark()` saves the **current position** as the mark. `reset()` restores position to the saved mark; it **does not change contents**, does not reset `limit`, and does not discard `mark` after a successful reset.

Sequential example:

```java
ByteBuffer b = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});

System.out.println(b.get());   // 10; position = 1
b.mark();                       // mark = 1
System.out.println(b.get());   // 20; position = 2
System.out.println(b.get());   // 30; position = 3
b.reset();                      // position returns to 1
System.out.println(b.get());   // 20 again; position = 2
```

Here the value `20` is not copied; the program simply re-reads the same position.

`mark` becomes invalid when:

- `clear()`, `flip()`, or `rewind()` is called.
- `compact()` is called on buffers that support this method.
- `position` is set **lower than mark**.
- `limit` is set **lower than mark**.

Calling `reset()` when no mark is set or after the mark has been discarded throws `java.nio.InvalidMarkException`. This is an unchecked exception, not an `IOException`.

**Mark is not a multi-level history**: a buffer holds at most one mark. Calling `mark()` again overwrites the previous mark with the current position.

## 7. Four Phase-Transition Operations: `flip`, `clear`, `rewind`, `compact`

You need to understand the purpose of each operation to switch between writing and reading on **the same buffer**.

| Operation | Position After | Limit After | Mark | Data Contents |
| --- | --- | --- | --- | --- |
| `flip()` | 0 | old position | Discarded | Does not modify bytes |
| `clear()` | 0 | capacity | Discarded | **Does not erase bytes** |
| `rewind()` | 0 | Keeps limit unchanged | Discarded | Does not modify bytes |
| `compact()` | Remaining elements before compact | capacity | Discarded | **Copies** unread portion to the beginning |

### 7.1. `flip()`: From Writing to Reading

During the write phase, position trails behind the written data. `flip()` performs exactly:

```text
limit = oldPosition
position = 0
mark = undefined
```

Example with `capacity = 8`, writing 3 bytes:

```text
After put(10), put(20), put(30):
[10][20][30][  ][  ][  ][  ][  ]
             ^
         position = 3
                             limit = 8

After flip():
[10][20][30][  ][  ][  ][  ][  ]
 ^
 position = 0
             ^
         limit = 3
```

Now only the three written bytes belong to the readable range for relative operations. **`flip` does not reverse byte order** and does not "transform" bytes into another form; it only changes the boundaries.

If you call `flip()` a second time immediately afterward, `limit` becomes 0 and the buffer looks as if it has no data to read. Do not call `flip` repeatedly without a new write step that needs a phase transition.

### 7.2. `clear()`: Returning to Ready-to-Write from the Beginning

`clear()` performs:

```text
position = 0
limit = capacity
mark = undefined
```

**`clear()` does not wipe storage.** Old bytes may remain in the backing array/direct memory until overwritten, but logically the buffer discards that data to begin a new write cycle. Do not use `clear()` to erase sensitive information.

When old data **has been fully read and no longer needs to be kept**, use `clear()` to reuse the write region.

### 7.3. `rewind()`: Re-reading from the Start Within the Current Limit

`rewind()` sets position to 0, **keeps limit unchanged**, and discards mark. It is useful when you need to re-read the same bounded slice of data.

For example, after `flip()` sets `limit = 3`, you read all three bytes and then call `rewind()`: `position` returns to 0 while `limit` remains 3; you can read the three bytes again. It differs from `clear()` because `clear` raises `limit` to the full `capacity`.

### 7.4. `compact()`: Keeping the Unread Portion When More Writes Are Needed

Suppose the buffer is in **read mode**:

```text
capacity = 8, position = 2, limit = 5

[10][20][30][40][50][ ?][ ?][ ?]
         ^
      position = 2
                     ^
                  limit = 5
```

Three **unread** bytes sit at offsets 2, 3, and 4. `compact()` copies them to the beginning:

```text
After compact():
[30][40][50][ ?][ ?][ ?][ ?][ ?]
             ^
          position = 3
                             ^
                          limit = 8
```

Then you continue calling `put` for new bytes, and `flip()` to read both the retained portion and the new data.

Formula for `compact()`:

\[
newPosition = oldLimit - oldPosition
\]

`newLimit = capacity` and mark is cleared. **Never rely on the values of slots outside the portion shifted to the front**; those positions are treated as space for subsequent writes. `compact()` does not have the same effect as `clear()` because it **preserves unread elements**.

## 8. Standalone Java 17+ Example: Observing Every State

The following program demonstrates all four state parameters and exercises `mark`, `remaining`, `flip`, `rewind`, and `clear`.

**File `BufferStateDemo.java`:**

```java
import java.nio.ByteBuffer;
import java.nio.InvalidMarkException;

public class BufferStateDemo {
    private static void show(String label, ByteBuffer b) {
        System.out.printf(
            "%s: cap=%d, pos=%d, lim=%d, remaining=%d%n",
            label, b.capacity(), b.position(), b.limit(), b.remaining());
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        show("Moi tao", b);

        b.put((byte) 10);
        b.put((byte) 20);
        b.put((byte) 30);
        b.put((byte) 40);
        show("Sau 4 put", b);

        b.flip();
        show("Sau flip", b);

        System.out.println("Doc dau: " + b.get());
        b.mark();
        System.out.println("Doc tiep: " + b.get());
        System.out.println("Doc nua: " + b.get());
        show("Truoc reset", b);

        b.reset();
        show("Sau reset", b);
        System.out.println("Doc lai: " + b.get());

        b.rewind();
        show("Sau rewind", b);

        try {
            b.reset();
            System.out.println("Mark van ton tai");
        } catch (InvalidMarkException ex) {
            System.out.println("Mark da bi huy");
        }

        b.clear();
        show("Sau clear", b);
        System.out.println("Byte cu tai 0: " + b.get(0));
        show("Sau get tuyet doi", b);
    }
}
```

Compile and run:

```bash
javac BufferStateDemo.java
java BufferStateDemo
```

**Exact Stdout:**

```text
Moi tao: cap=8, pos=0, lim=8, remaining=8
Sau 4 put: cap=8, pos=4, lim=8, remaining=4
Sau flip: cap=8, pos=0, lim=4, remaining=4
Doc dau: 10
Doc tiep: 20
Doc nua: 30
Truoc reset: cap=8, pos=3, lim=4, remaining=1
Sau reset: cap=8, pos=1, lim=4, remaining=3
Doc lai: 20
Sau rewind: cap=8, pos=0, lim=4, remaining=4
Mark da bi huy
Sau clear: cap=8, pos=0, lim=8, remaining=8
Byte cu tai 0: 10
Sau get tuyet doi: cap=8, pos=0, lim=8, remaining=8
```

**Key analysis:**

1. After four `put` calls, `position` is 4 even though `capacity` is 8.
2. `flip` turns the old position 4 into the new limit 4 and sets `position` to 0.
3. `mark()` is called at position 1; after two reads advance to position 3, `reset()` returns to 1, then re-reads `20`.
4. `rewind()` resets position to 0 and keeps limit 4, but **clears mark**; calling `reset()` afterward throws `InvalidMarkException`.
5. `clear()` raises limit to 8 but **does not erase old bytes**: `get(0)` still reads 10 in the example. `get(0)` is an absolute read, so `position` stays at 0. This does not mean old data remains valid at the application level after `clear`.

## 9. Java 17+ Example: `compact` and Partially Read Data

A common mistake when processing data from an I/O channel is receiving part of a message, reading only some bytes, and needing to preserve the unread part for the next receive pass. Calling `clear` immediately can lose the unprocessed portion when it gets overwritten. `compact` solves this case.

**File `BufferCompactDemo.java`:**

```java
import java.nio.ByteBuffer;

public class BufferCompactDemo {
    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(6);

        b.put(new byte[] {10, 20, 30, 40, 50});
        System.out.println("Sau ghi: pos=" + b.position()
                + ", lim=" + b.limit());

        b.flip();
        System.out.println("Da xu ly: " + b.get() + ", " + b.get());
        System.out.println("Chua xu ly: " + b.remaining());

        b.compact();
        System.out.println("Sau compact: pos=" + b.position()
                + ", lim=" + b.limit());

        b.put((byte) 60);
        b.put((byte) 70);
        b.flip();

        System.out.print("Du lieu con lai:");
        while (b.hasRemaining()) {
            System.out.print(" " + b.get());
        }
        System.out.println();
    }
}
```

Run:

```bash
javac BufferCompactDemo.java
java BufferCompactDemo
```

**Exact Stdout:**

```text
Sau ghi: pos=5, lim=6
Da xu ly: 10, 20
Chua xu ly: 3
Sau compact: pos=3, lim=6
Du lieu con lai: 30 40 50 60 70
```

`compact()` retains the three bytes `30 40 50` and moves them to the front of the buffer. Position becomes 3, leaving room for three new bytes. Writing `60` and `70` advances position to 5; `flip()` sets the readable range to exactly the five bytes `30 40 50 60 70`.

Note that calling `compact()` on a read-only buffer throws `ReadOnlyBufferException`. If the unread portion is close to `capacity`, the next write pass may still run out of space; the program must handle resizing, record limits, or an appropriate data-intake policy.

## 10. When Exactly Is Mark Discarded?

Consider `ByteBuffer.allocate(10)`, initially `position=0`, `limit=10`. Sequentially:

```java
ByteBuffer b = ByteBuffer.allocate(10);
b.position(4);
b.mark();       // mark = 4

b.position(6);  // mark 4 is still valid
b.reset();      // returns to position 4

b.position(3);  // position < mark 4: mark is discarded
// b.reset();    // would throw InvalidMarkException
```

In another sequence of operations:

```java
ByteBuffer b = ByteBuffer.allocate(10);
b.position(6).mark(); // mark 6
b.limit(5);           // position is pulled down to 5; mark 6 is discarded
// b.reset();         // would throw InvalidMarkException
```

These two examples are independent. Do not think of `mark` as a "permanent restore point"; it exists only within the allowed state bounds of the buffer.

When you need multiple restore points, or need to restore after operations that clear the mark, an application can **store `position` values in `int` variables** and later call `position(savedPosition)` after verifying `savedPosition <= limit()`. This is not equivalent to `mark/reset`, and you still must ensure the data and `limit` remain valid.

## 11. Full Buffer, Empty Buffer, and Exceptions to Distinguish

**A buffer full in the write phase** means `position == limit` and there is no room for relative `put`. **A fully read buffer** also has `position == limit`, though its business meaning is different. The arithmetic state is identical; the processing cycle determines the next step.

| Situation | Typical Outcome |
| --- | --- |
| `get()` when `position == limit` | `BufferUnderflowException` |
| `put(byte)` when `position == limit` on a writable buffer | `BufferOverflowException` |
| `get(-1)` or `get(index >= limit)` | `IndexOutOfBoundsException` |
| `position(-1)` or `position(limit + 1)` | `IllegalArgumentException` |
| `limit(capacity + 1)` | `IllegalArgumentException` |
| `reset()` when no mark is set | `InvalidMarkException` |
| Writing to a read-only buffer | `ReadOnlyBufferException` |

`remaining()` and `hasRemaining()` help avoid many cases of reading/writing past `limit`:

```java
while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Process value.
}
```

This is an illustrative snippet; to compile standalone, a properly typed `buffer` variable and processing logic must be defined. Do not infer that such a loop automatically understands message or protocol boundaries. It simply reads up to the current `limit`.

When reading/writing with `FileChannel`, the number of bytes processed in a single call may be smaller than the desired `remaining()`; write loops according to the channel API contract, handling EOF and zero-progress cases where applicable. `flip`, `compact`, and `clear` only manage **buffer state**; they do not themselves read data from the filesystem or send bytes over the network.

## 12. Applying This to the NIO Read-and-Process Cycle

A common cycle when reading from a byte source into a `ByteBuffer`:

```text
Initial buffer:        position=0, limit=capacity
       |
       v
Source writes to buf:  position advances by bytes received
       |
       v
flip():                limit=oldPosition, position=0
       |
       v
Process data:          read bytes, position advances
       |
       +-- All bytes processed:
       |        clear() --> prepare for next write pass
       |
       +-- Unprocessed bytes remain:
                compact() --> keep remainder, prepare for more writes
```

Choosing `clear` or `compact` depends on whether **the bytes from `position` to `limit` still need to be kept**. For example, when receiving chunks of a variable-length message, the parser may not yet have enough data to decode a record; `compact` preserves the incomplete part so more data can be appended.

For UTF-8 text, a character can be split across two receive calls. Do not force each byte chunk into an independent `String` and corrupt partial character data; use a stateful decoder or buffer accumulation according to the protocol. This is a direct application of `position`, `limit`, and `compact`.

When **writing data from the application to a channel**, the flow goes in reverse: `put` to prepare data → `flip` so the channel reads bytes → loop `write` until the buffer has no remaining bytes → `clear` or `compact` as appropriate for partial writes. The key is keeping clear track of whether the buffer is currently in the write-into-buffer phase or the read-out-of-buffer phase.

## 13. `slice`, `duplicate`, `asReadOnlyBuffer`, and Independent State

A `ByteBuffer` can produce views:

- `duplicate()` creates a buffer sharing the same contents, while maintaining **independent `position`, `limit`, and `mark`** from the original buffer; initial state copies the current values.
- `slice()` creates a view of the region from the current `position` to the current `limit`. The new view has `position=0` and `limit=capacity=remaining` of the original buffer at creation time, and shares the data of that slice.
- `asReadOnlyBuffer()` creates a read-only view sharing contents with its own `position`/`limit`/`mark` state. Any write operation through this view is rejected.

**Sharing contents does not mean sharing `position`.** Moving `position` in a view does not directly move `position` in the original buffer; however, writing data through one view can modify bytes observed by another view. Views also do not automatically provide thread safety.

Small example:

```java
ByteBuffer base = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
base.position(1);
base.limit(3);

ByteBuffer view = base.slice();
System.out.println(view.capacity()); // 2
System.out.println(view.position()); // 0
System.out.println(view.limit());    // 2
System.out.println(view.get());      // 20
System.out.println(base.position()); // 1 (unchanged)
```

The view holds two bytes corresponding to `20, 30`, with its own indices `0, 1`. For direct-allocated or memory-mapped buffers, resource ownership and backing-storage lifecycle must also be designed appropriately; those concerns are orthogonal to the `capacity`/`position`/`limit`/`mark` invariants.

## 14. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Writing with `put` and reading immediately with `get` without `flip()` | Position sits past the data just written | Call `flip()` before the read phase |
| Thinking `flip()` reverses element order | Flip only changes state | Follow the limit/position formulas properly |
| Using `clear()` to wipe secrets | Clear does not overwrite contents | Use an appropriate data-zeroing routine and manage memory lifecycle |
| Using `clear()` when unprocessed bytes remain | Leftover bytes are easily overwritten | Use `compact()` when remaining bytes must be kept |
| Using `rewind()` to start a full-capacity write phase | Rewind keeps the old limit | If discarding old data to write from scratch across capacity, use `clear()` |
| Calling `reset()` after `flip/clear/rewind/compact` | Mark has been discarded | Call `mark()` again in the appropriate phase |
| Confusing `capacity` with the number of bytes written | May read into uninitialized/invalid space | Use `flip` to set `limit` to the amount written |
| Calling `get()` when `remaining() == 0` | Underflow | Check `hasRemaining()`, or handle the exception intentionally |
| Calling `put()` when `position == limit` | Overflow | Check available space, switch phase, or use a larger buffer |
| Thinking `get(index)` increments `position` | That is an absolute access | Use `get()` if you want `position` to advance |
| Mistaking positions in `IntBuffer` for byte offsets | IntBuffer positions count `int` elements | Remember each buffer type has its own element unit |
| Sharing a buffer whose `position` changes across multiple threads | State changes can interleave | Synchronize or establish clear buffer ownership |

## 15. State-Tracking Exercise

Given a new buffer:

```java
ByteBuffer b = ByteBuffer.allocate(6);
b.put((byte) 1);
b.put((byte) 2);
b.put((byte) 3);
b.flip();
b.get();
b.mark();
b.get();
b.compact();
```

**Predict `position`, `limit`, and `capacity` after each key step.**

Answer:

1. Newly created: `capacity=6`, `position=0`, `limit=6`.
2. After three `put` calls: `position=3`, `limit=6`, data written `1, 2, 3`.
3. After `flip`: `position=0`, `limit=3`.
4. After first `get()`: `position=1`, reads byte `1`.
5. `mark()` sets mark at **1**; does not change `position`.
6. After second `get()`: `position=2`, reads byte `2`.
7. Before `compact`, `remaining = 3 - 2 = 1`, unread byte is **3**.
8. After `compact`: byte `3` is moved to index 0; `position=1`, `limit=6`, `capacity=6`, **mark is gone**. The buffer is ready to write more bytes starting at offset 1.

If `reset()` is called after the last step, the program throws `InvalidMarkException` because `compact()` clears the mark.

## 16. Summary

**The four state parameters always obey `0 <= position <= limit <= capacity`**, and `mark` (if present) must lie in `[0, position]`. `position` is the index for the next relative operation, `limit` is the exclusive upper bound, `capacity` is the fixed capacity, and `mark` is used to remember and restore `position`.

When writing I/O logic, always know which phase the buffer is in:

- **Done writing → read:** `flip()`.
- **Done reading and discard old data → write again:** `clear()`.
- **Need to re-read data within limit:** `rewind()`.
- **Not finished reading and need to receive/write more:** `compact()`.
- **Just want to return to a marked position:** `mark()` then `reset()`, provided the mark has not been discarded.

References: Java SE 17 API — `java.nio.Buffer`, `java.nio.ByteBuffer`, `java.nio.InvalidMarkException`, and `java.nio.channels.FileChannel`.
