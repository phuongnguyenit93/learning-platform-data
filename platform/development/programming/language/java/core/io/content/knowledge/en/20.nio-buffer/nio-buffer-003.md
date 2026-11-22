# The Write-to-Buffer, `flip()`, and Read-from-Buffer Cycle in Java NIO

## 1. A Buffer Does Not Know on Its Own When You Want to Write or Read

In Java NIO (`java.nio`), a **buffer** is a data storage region paired with cursors describing which portion is currently permitted to be accessed. When reading data from a channel, data is typically **written into the buffer** first, and then the program **reads it out of the buffer** to process it or write it to another channel.

A `ByteBuffer` has three quantities you must watch continuously:

- **`capacity`**: total number of elements the buffer can hold, fixed throughout the buffer's lifetime.
- **`position`**: index of the next element to be read or written when using *relative* operations such as `get()` and `put(byte)`.
- **`limit`**: first index **outside the permitted operation region** in the current state.

Invariants:

~~~text
0 <= position <= limit <= capacity
remaining() = limit - position
hasRemaining() is equivalent to position < limit
~~~

**"Write mode" and "read mode" describe how the program uses the buffer**, not a `READ/WRITE` flag that switches automatically. Calls to `flip()`, `clear()`, `rewind()`, and `compact()` update `position`/`limit` to prepare for the next step.

Example of a buffer with `capacity = 8`, after writing 3 bytes:

~~~text
index:      0   1   2   3   4   5   6   7
data:       A   B   C   ?   ?   ?   ?   ?
           └─ written ─┘└── space to write ──┘
position = 3
limit    = 8
capacity = 8
~~~

The `?` symbol represents data without meaning for this write pass; those slots must not be read as valid content.

## 2. Phase 1: Writing *Into* the Buffer

After creation:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(8);
~~~

Initial state:

~~~text
position = 0
limit    = 8
capacity = 8
remaining = 8
~~~

Relative write calls:

~~~java
buffer.put((byte) 'A');
buffer.put((byte) 'B');
buffer.put((byte) 'C');
~~~

Each `put(byte)` places one byte at the current `position`, then increments `position` by 1. After three calls:

~~~text
position = 3
limit    = 8
capacity = 8
remaining = 5
~~~

This is the **writing/filling** state. `limit` is still 8 because `flip()` has not been called yet. If you call `get()` right now, `get()` will read starting at index 3 (since it is still within `limit`), which may hold old bytes or bytes not belonging to the current write pass. There is no automatic mechanism that knows "the 3 bytes just written are the entire valid data."

`channel.read(buffer)` also belongs to the **write-into-buffer** phase: the channel pulls data from the source and puts it into positions from `position` up to before `limit`. If `n > 0` bytes are read, `position` advances by `n`. A return value of `0` can occur when no data is available yet or the operation makes no progress; `-1` signals end-of-input for `ReadableByteChannel`.

Note on bounds: if `position == limit`, then `remaining() == 0`, and another relative `put(byte)` will throw `BufferOverflowException`. `ByteBuffer` does not automatically expand its capacity.

## 3. Phase 2: `flip()` Transitions from Writing to Reading

After finishing *a write batch*, call:

~~~java
buffer.flip();
~~~

State changes performed by `flip()`:

~~~text
limit = old position
position = 0
mark is discarded (if set)
capacity is unchanged
~~~

Before and after writing A, B, C into an 8-byte buffer:

| Moment | position | limit | capacity | remaining |
| --- | ---: | ---: | ---: | ---: |
| Newly created | 0 | 8 | 8 | 8 |
| After 3 `put` calls | 3 | 8 | 8 | 5 |
| After `flip()` | 0 | 3 | 8 | 3 |

~~~text
index:      0   1   2   3   4   5   6   7
data:       A   B   C   ?   ?   ?   ?   ?
           └─ read region ┘└─ beyond limit ────┘
position = 0          limit = 3          capacity = 8
~~~

Now `get()` can read the exact **3 bytes just written**, and will not read into the empty slots past index 2.

`flip()` does **not** reverse bytes, does not move data, does not allocate new memory, and does not turn the `ByteBuffer` into a read-only object. The name "flip" simply describes swapping the access boundary: the data that was just produced becomes the region to be consumed.

**Common mistake:** calling `flip()` twice in a row without an intervening purposeful write/read. After the first `flip`, `position = 0`; the second `flip` sets `limit = 0`, making the buffer look as if no bytes remain to be read. Only call `flip()` after an actual write phase.

## 4. Phase 3: Reading *From* the Buffer

After `flip()`:

~~~java
while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Process value.
}
~~~

Each relative `get()` fetches the element at the current `position` and increments `position`. Once A, B, and C have been read:

~~~text
position = 3
limit    = 3
remaining = 0
hasRemaining() = false
~~~

Calling another relative `get()` raises `BufferUnderflowException` because you have gone past the boundary of readable data.

The `while (buffer.hasRemaining())` loop clearly expresses "read until the end of available data." If you need to know how many unread bytes remain, use `remaining()` rather than `capacity - position`: after `flip`, the region from `limit` to `capacity` is not part of the current batch's data.

### Relative vs. Absolute

- `get()` and `put(value)` are **relative** operations that modify `position`.
- `get(index)` and `put(index, value)` are **absolute** operations affecting the specified index without **automatically advancing `position`**. These calls still check index bounds against `limit` and read/write permissions.
- If mixing both styles, you must track clearly whether `position` still points to the right place to continue reading/writing.

For sequential data processing, relative `put` → `flip` → `get` is usually the easiest to follow.

## 5. Standard Lifecycle Diagram

~~~text
        ┌──────────────────────────────────┐
        │ FILL: write data into buffer     │
        │ put(...) / channel.read(...)     │
        │ position advances, limit stays   │
        └───────────────┬──────────────────┘
                        │ flip()
                        ▼
        ┌──────────────────────────────────┐
        │ DRAIN: read available data       │
        │ get(...) / channel.write(...)    │
        │ position advances up to limit    │
        └───────────────┬──────────────────┘
                        │
                 All data read?
                  /            \
                Yes          Leftover
                │                │
              clear()         compact()
                │                │
                └─────→ FILL ←───┘
~~~

When reading a file via a channel and then reading out of a buffer, the familiar cycle is:

1. Buffer has space: write from source into buffer.
2. `flip()`: set the boundary of the received data so it can be read.
3. Read/write out of the buffer within `position..limit`.
4. If no unprocessed data remains, use `clear()`. If unconsumed data remains, consider `compact()`.
5. Continue with the next write pass into the buffer.

**Not every channel read will fill the buffer**, and not every channel write will consume all data. Always rely on `position`, `remaining()`, and the actual I/O return values.

## 6. Standalone Java 17+ Program: write → flip → read

Save the file `BufferCycleDemo.java`:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class BufferCycleDemo {

    private static void state(String name, ByteBuffer b) {
        System.out.printf(
                "%s: position=%d, limit=%d, capacity=%d, remaining=%d%n",
                name, b.position(), b.limit(), b.capacity(), b.remaining());
    }

    private static String readAscii(ByteBuffer b) {
        StringBuilder result = new StringBuilder();
        while (b.hasRemaining()) {
            result.append((char) b.get());
        }
        return result.toString();
    }

    public static void main(String[] args) {
        ByteBuffer b = ByteBuffer.allocate(8);
        state("new", b);

        b.put((byte) 'A');
        b.put((byte) 'B');
        b.put((byte) 'C');
        state("written", b);

        b.flip();
        state("flipped", b);

        System.out.println("read = " + readAscii(b));
        state("drained", b);

        b.rewind();
        System.out.println("reread = " + readAscii(b));

        b.clear();
        state("cleared", b);
        b.put((byte) 'X');
        b.flip();
        System.out.println("next = " + readAscii(b));

        ByteBuffer partial = ByteBuffer.allocate(6);
        partial.put("ABCD".getBytes(StandardCharsets.US_ASCII));
        partial.flip();

        System.out.println(
                "consumed = " + (char) partial.get() + (char) partial.get());
        state("two read", partial);

        partial.compact();
        state("compacted", partial);
        partial.put((byte) 'E');
        partial.put((byte) 'F');
        partial.flip();

        System.out.println("remaining + new = " + readAscii(partial));
        state("second drained", partial);
    }
}
~~~

Run from the directory containing the file using JDK 17+:

~~~bash
javac BufferCycleDemo.java
java BufferCycleDemo
~~~

Exact Stdout:

~~~text
new: position=0, limit=8, capacity=8, remaining=8
written: position=3, limit=8, capacity=8, remaining=5
flipped: position=0, limit=3, capacity=8, remaining=3
read = ABC
drained: position=3, limit=3, capacity=8, remaining=0
reread = ABC
cleared: position=0, limit=8, capacity=8, remaining=8
next = X
consumed = AB
two read: position=2, limit=4, capacity=6, remaining=2
compacted: position=2, limit=6, capacity=6, remaining=4
remaining + new = CDEF
second drained: position=4, limit=4, capacity=6, remaining=0
~~~

Because the example writes only single-byte ASCII characters, casting from `byte` to `char` in `readAscii` is sufficient to demonstrate cursor behavior. **Do not** use that cast as a general UTF-8 decoder: Vietnamese characters can occupy multiple bytes. For real text data, use `CharsetDecoder` or decoding APIs via `StandardCharsets.UTF_8` and preserve byte sequences that are not yet complete characters.

Reading the key milestones:

- `written`: three bytes have been written, while `limit` is still 8.
- `flipped`: `position` goes to 0, `limit` becomes 3, matching the number of bytes written.
- `drained`: the `readAscii` loop consumes all three bytes, so `remaining` drops to 0.
- `reread`: `rewind()` allows reading A, B, C again because `limit` is still 3.
- `cleared`: `clear()` resets the write window; next only X is written and `flip`ped, so the new read sees only X.
- `two read`/`compacted`: the two unread bytes C and D are kept so E and F can be appended in the next pass.

## 7. How Do `clear()`, `rewind()`, and `compact()` Differ?

These three operations are **not equivalent**, even though all three commonly appear near the end of a read phase.

### `clear()`: Prepare for New Writes, Discarding Unread Portion

~~~java
buffer.clear();
~~~

Effect:

~~~text
position = 0
limit = capacity
mark is discarded
~~~

`clear()` **does not erase physical data** in the backing array or direct memory; the method name means "reset access state to reuse the container." If unread data remained before `clear`, the program is intentionally discarding it. Therefore, only call `clear()` when the old contents have been fully consumed or you decide they are no longer needed.

### `rewind()`: Re-read the Same Data Region

~~~java
buffer.rewind();
~~~

Effect:

~~~text
position = 0
limit remains unchanged
mark is discarded
~~~

After reading all of A, B, C with `limit=3`, `rewind()` lets you read all three bytes again without calling `flip()` again. `rewind()` is suitable when you need to re-scan data within the current window, not to prepare for receiving a new batch of data from a channel.

### `compact()`: Preserve Unread Portion, Make Room for More Writes

Suppose a 6-byte buffer containing A, B, C, D has been `flip`ped and only A and B have been read:

~~~text
index:        0   1   2   3   4   5
data:         A   B   C   D   ?   ?
                  ↑       ↑
             position=2  limit=4
unread: C D
~~~

Call:

~~~java
buffer.compact();
~~~

Then `compact()` moves the **two unread bytes (C, D)** to the front of the buffer and sets:

~~~text
index:        0   1   2   3   4   5
data:         C   D   ?   ?   ?   ?
position = 2
limit    = 6
capacity = 6
remaining = 4
~~~

The `?` marks do not imply memory is cleared: bytes outside the valid region may still hold old values. After `compact`, the buffer is ready to **append writes starting at position 2**. Writing E and F and then calling `flip` gives a readable range of C, D, E, F.

`compact()` is especially useful when a packet, record, or multi-byte character has not yet arrived in full for processing. It preserves unconsumed data. If the buffer is read-only, `compact()` throws `ReadOnlyBufferException`.

| Method | position after call | limit after call | Usable Data Portion |
| --- | --- | --- | --- |
| `flip()` | 0 | old position | Data just written, from 0 to old position |
| `clear()` | 0 | capacity | No guarantee old data is kept for further reading |
| `rewind()` | 0 | old limit | Same data region within current limit |
| `compact()` | Number of unread elements | capacity | Elements from old position to old limit, shifted to the front |

`compact()` incurs the cost of moving unread elements; if everything has already been consumed, `clear()` is simpler and typically needs no copying.

## 8. Connecting the Cycle to `Channel`

There are two directions that are easy to confuse:

- `channel.read(buffer)`: **read from channel**, meaning **write into buffer**. It advances `buffer.position()` by the number of bytes read.
- `channel.write(buffer)`: **write to channel**, meaning **read out of buffer**. It advances `buffer.position()` by the number of bytes actually written.

Flow when copying a file:

~~~text
Source FileChannel
     │ read(buffer)   — fill
     ▼
ByteBuffer: position advances toward limit/capacity
     │ flip()
     ▼
ByteBuffer: position=0, limit=bytes received
     │ write(buffer)  — drain
     ▼
Destination FileChannel
     │ clear() or compact()
     └────────────────────→ next batch
~~~

### Example Illustrating Batch File Copying

This snippet assumes two existing `FileChannel input` and `FileChannel output` objects opened in the appropriate read/write modes. **This is an illustrative code snippet inside a method**, not a standalone Java program:

~~~java
ByteBuffer buf = ByteBuffer.allocate(4096);
int count;
while ((count = input.read(buf)) != -1) {
    buf.flip();
    while (buf.hasRemaining()) {
        output.write(buf);
    }
    buf.clear();
}
~~~

Meaning:

1. `input.read(buf)` fills bytes into the buffer; never assume it will receive the full 4096 bytes.
2. `flip()` sets `limit` to the number of bytes received.
3. The `while (buf.hasRemaining())` loop ensures the output channel gets a chance to receive all unwritten bytes. A single `write` does not necessarily drain the entire buffer.
4. `clear()` is safe in this example because the inner loop only finishes after every byte in the buffer has been transferred.
5. `read` returning `-1` signals EOF; there are no more batches of bytes to put into the buffer.

The code above shows the cycle for a normal file channel; with a **non-blocking channel**, `read/write` can return `0` when no progress is made. In particular, never busy-wait indefinitely in a `while` loop calling `write` continuously if the output is not ready. In a non-blocking NIO environment, use a `Selector`/write-readiness notifications or an appropriate scheduler, while retaining unsent data with `compact()` or avoiding premature buffer state transitions.

For fragmented data (such as a record lacking enough bytes to parse), the rule is **after `flip`, consume only complete records; then `compact` to preserve the unprocessed tail** before reading more from the source. `clear` would lose the data region needed to stitch two batches together.

## 9. Common Mistakes When Managing `position` and `limit`

### Forgetting `flip()` Before Reading

~~~java
ByteBuffer b = ByteBuffer.allocate(8);
b.put((byte) 'A');
byte x = b.get(); // Wrong intent: reads from position=1, not A at index=0.
~~~

`get()` in this example may return an old value at index 1 without throwing an error, making the bug hard to spot. The fix is calling `b.flip()` before starting to read the bytes just written.

### Using `flip()` Instead of `clear()` Before a New Write Pass

After draining the entire buffer, `position == limit`. Calling `flip()` sets `limit` to the number of bytes read and `position` to 0, which does not necessarily mean "prepare a fresh write across full capacity." To reuse the buffer for a new write pass, use `clear()` if no data needs to be preserved, or `compact()` if unprocessed data remains.

### Using `clear()` While Unprocessed Bytes Remain

Suppose part of a message has been received, and only the header could be parsed while the body is incomplete. `clear()` resets the write area and wipes out the state pointing to the waiting body fragment. As a result, the message is lost or fails to assemble. When unread data sits in `position..limit`, use `compact()`.

### Reading Past `limit` or Writing When Out of Space

Relative operations check state bounds:

- `get()` when `position == limit` ⇒ `BufferUnderflowException`.
- `put(byte)` when `position == limit` ⇒ `BufferOverflowException`.

Use `hasRemaining()` or `remaining()`; when writing multiple bytes in a single call, verify enough space remains beforehand.

### Mistaking `capacity` for Valid Byte Count

`capacity` reflects the container size, not the amount of data received. After `flip()`, **`limit`** is the boundary of readable data; `remaining()` is the number of unread elements starting from `position`.

### Thinking `flip()` Turns a `ByteBuffer` into Text Data

A buffer is a sequence of bytes. With UTF-8, a single character can span multiple `channel.read` calls. Reading byte by byte and casting to `char` is reliable only for ASCII in learning examples. When building a text parser, use a charset decoder that handles incomplete byte sequences and handles end-of-stream state properly.

### Misunderstanding `mark()` and `reset()`

`mark()` saves the current position; `reset()` returns to the mark if still valid. `flip()`, `clear()`, `rewind()`, and `compact()` all discard the mark, so calling `reset()` after those operations throws `InvalidMarkException`. Re-apply the mark after a state transition if needed.

## 10. Self-Check

1. A `ByteBuffer.allocate(10)` just had 4 bytes `put` into it. Determine `position=4`, `limit=10`. After `flip()`, the result is `position=0`, `limit=4`, `remaining=4`.
2. After the `flip` in question 1, the program reads 2 bytes. `remaining=2` remains. To keep those two bytes and append the next batch, choose **`compact()`**, yielding `position=2`, `limit=10`.
3. If all bytes in the buffer have been read and a new batch needs to be written, choose **`clear()`**. Why is `compact()` unnecessary? There is no unread data left to shift to the front.
4. To re-read the same 4 bytes without changing `limit`, choose **`rewind()`**.
5. A `channel.write(buffer)` writes fewer bytes than `buffer.remaining()`. Why not call `clear()` immediately? Because the remaining portion in the buffer has not been sent yet and must be retained for further sending.
6. Why is `flip()` mandatory in the relative write-then-read model? Because it sets `limit` to the exact amount of data just written and moves `position` back to the start of the valid data region.

**Practical takeaway:** The standard pattern is **`put`/`channel.read` → `flip` → `get`/`channel.write` → `clear` or `compact`**. Always use `position`, `limit`, and `remaining()` as the source of truth for which bytes are present, which have been consumed, and where more can still be written.
