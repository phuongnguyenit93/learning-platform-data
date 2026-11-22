# Java NIO Buffer: `rewind()`, `compact()`, and `reset()`

## 1. Why Distinguish These Three Operations?

When using `java.nio.ByteBuffer` to read data from files/sockets or to assemble message fragments, you regularly alternate between **writing data into the buffer** and **reading existing data out of the buffer**. A decision arises when you want to:

- **Re-read from the start of the currently readable region:** use `rewind()`.
- **Keep unprocessed data and shift it to the front to make room for more incoming data:** use `compact()`.
- **Return to a previously bookmarked position:** use `mark()` paired with `reset()`.

All three operations deal with cursors, yet they **do not mean the same thing**. Picking the wrong one can cause your program to re-read old data, lose an incomplete fragment, or attempt to read invalid bytes.

This article uses `ByteBuffer` on Java 17+ for explanation; the general principles regarding `position`, `limit`, and `mark` also apply across the `java.nio.Buffer` family. `compact()` is a method on specific buffer types that support it (such as `ByteBuffer` and `CharBuffer`), not an abstract method on the base `Buffer` class.

## 2. Four States to Know: capacity, limit, position, mark

| Property | Meaning |
|---|---|
| `capacity` | Maximum number of elements the buffer can hold; fixed over a buffer's lifetime. For `ByteBuffer`, the unit is **bytes**. |
| `limit` | First boundary index **not** accessible by relative operations; valid indices precede `limit`. |
| `position` | Index of the next relative `get()` / `put()` operation; a successful `get()` or `put()` typically advances `position` by one element. |
| `mark` | Optional bookmark recorded by `mark()`; `reset()` returns to this bookmark. Initially `mark` is **undefined**. |

For a buffer with a valid mark, the invariant is:

~~~text
0 <= mark <= position <= limit <= capacity
~~~

If mark has not been set, `0 <= position <= limit <= capacity` still holds.

Useful APIs:

- `buffer.position()`, `buffer.limit()`, `buffer.capacity()`: inspect these values.
- `buffer.remaining()` = `limit - position`; `buffer.hasRemaining()` indicates whether any region remains for relative access.
- `buffer.get()` / `buffer.put(value)`: relative access that **advances position**.
- `buffer.get(index)` / `buffer.put(index, value)`: absolute index access that **does not advance position**.
- `buffer.mark()`: sets `mark = position`.
- `buffer.reset()`: sets `position` back to `mark`.

**Position-control operations do not mean automatically erasing data.** They change which region is treated as valid for subsequent read/write calls. For `compact()`, there is also the action of **moving remaining data** in memory.

### State Example When Filling Data

Suppose:

~~~java
ByteBuffer buf = ByteBuffer.allocate(8); // position=0, limit=8, capacity=8
buf.put(new byte[] {10, 20, 30, 40, 50}); // position=5, limit=8
buf.flip(); // position=0, limit=5: ready to read 5 valid bytes
~~~

Diagram after `flip()`:

~~~text
index:      0    1    2    3    4   | 5    6    7
data:      10   20   30   40   50   | ?    ?    ?
           ^ position=0             ^ limit=5      capacity=8
usable:    [----- 5 readable bytes -----)
~~~

The `?` marks represent positions **outside the current readable region**. Even though `ByteBuffer.allocate` initializes memory to zeros, elements beyond `limit` should never be treated as message data.

## 3. `rewind()`: Re-reading from the Start of the Current Region

**Formal rules:**

- `position = 0`.
- **Keeps `limit` and `capacity` unchanged**.
- **Discards `mark`**, if previously set.
- **Does not copy/erase contents** in the buffer.

Example (illustrative snippet, requires `import java.nio.ByteBuffer;`):

~~~java
ByteBuffer buf = ByteBuffer.allocate(6);
buf.put(new byte[] {10, 20, 30, 40});
buf.flip();  // p=0, l=4, c=6
buf.get();   // 10; p=1
buf.get();   // 20; p=2

buf.rewind(); // p=0, l=4, c=6
byte firstAgain = buf.get(); // 10; p=1
~~~

After `rewind()`, the four bytes `10, 20, 30, 40` can still be read within `limit=4`. This method **does not turn the buffer into an empty write region**.

**When to use:**

- Needing to re-parse the same payload from the start.
- Needing to re-output/re-send an entire prepared data region, provided `limit` still reflects the payload length.
- Needing to compare or re-scan bytes without allocating/copying another buffer.

**When not to use:** when part of a message has been processed and the **unprocessed** portion must be preserved to receive more data. `rewind()` jumps back to index 0 and causes already processed bytes to be read again. Consider `compact()` instead.

### `rewind()` and `flip()` Are Not the Same

If `position=3, limit=8, capacity=8`:

- `rewind()` → `position=0, limit=8`.
- `flip()` → `position=0, limit=3`.

`flip()` switches from the write phase to the read phase by **taking the old position as the new limit**. `rewind()` preserves the existing limit to **re-read** the current region.

A classic bug is calling `rewind()` right after `put` without `flip()`: since `limit` is still `capacity`, the program can read past the actual payload bytes just written.

## 4. `reset()`: Returning to a Previously Set Mark

`reset()` does not restore a buffer to its newly created state, nor does it **automatically jump to index 0**.

Rules:

1. Call `mark()` to save `mark = position`.
2. Read or advance `position` forward.
3. Call `reset()` to set **`position = mark`**.
4. `limit` and `capacity` **remain unchanged**.
5. **The mark remains valid after `reset()`**, so you can call `reset()` multiple times as long as no other operation discards it.

Example:

~~~java
ByteBuffer buf = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
buf.get();     // 10; p=1
buf.mark();    // mark=1
buf.get();     // 20; p=2
buf.get();     // 30; p=3
buf.reset();   // p=1
byte again = buf.get(); // 20; p=2
buf.reset();   // p=1, since mark has not been discarded
~~~

Distinguish clearly:

- `mark()` **only remembers a position**, it does not copy the data at that position.
- `reset()` **only restores the position**, it does not restore bytes that were overwritten.
- Calling `reset()` without a valid mark throws `java.nio.InvalidMarkException` (**unchecked exception**).

### Operations That Invalidate Mark

`clear()`, `flip()`, `rewind()`, and `compact()` **always discard the mark**. Additionally, `position(newPosition)` discards the mark if `newPosition < mark`; `limit(newLimit)` discards the mark if `newLimit < mark`. Setting a new mark via `mark()` replaces the old one.

Example:

~~~java
ByteBuffer buf = ByteBuffer.wrap(new byte[] {1, 2, 3, 4});
buf.position(2).mark(); // mark=2
buf.position(1);        // Moved before mark -> discards mark
buf.reset();            // Throws InvalidMarkException
~~~

By contrast, absolute index reads such as `buf.get(0)` **do not change `position`**, so by themselves they do not invalidate the mark.

**Typical scenario:** a parser speculatively reads a header, setting a mark before a variable-length field; if not enough bytes are present or a branch does not match, it calls `reset()` to re-read that section. For complex parsers with multiple rollback points, a single mark may not suffice; you can save positions into `int saved = buffer.position()` variables and restore carefully via `position(saved)`, keeping current limits and mark-discard rules in mind.

## 5. `compact()`: Keep Unread Data, Make Room for More Writes

Unlike the two methods above, `compact()` **moves the remaining elements** in `[position, limit)` to the beginning of the buffer.

Let:

- `p = position` before compacting.
- `l = limit` before compacting.
- `n = l - p = remaining()`.

After `compact()` on a writable buffer:

1. Copies the `n` elements of `[p, l)` into `[0, n)` in the exact same order.
2. Sets `position = n`, **not 0**.
3. Sets `limit = capacity`.
4. Discards `mark`.
5. Returns the buffer to a **state ready to `put` more** after the incomplete data.

### Visualizing the Retained Bytes

~~~text
Before compact:
capacity = 8, position = 2, limit = 5
index:       0    1  | 2    3    4  | 5    6    7
data:       10   20  |30   40   50  | ?    ?    ?
               read    ^----- unread -------^
remaining = 5 - 2 = 3

After compact:
capacity = 8, position = 3, limit = 8
index:       0    1    2  | 3    4    5    6    7
data:       30   40   50  | ... space for new writes ...
                            ^ position=3
~~~

Positions beyond the three retained elements may still contain old bytes; **`compact()` makes no promise to wipe the rest**.

In practice:

~~~java
ByteBuffer buf = ByteBuffer.allocate(8);
buf.put(new byte[] {10, 20, 30, 40, 50});
buf.flip();                  // p=0, l=5
buf.get();                   // 10; p=1
buf.get();                   // 20; p=2

buf.compact();               // keeps [30,40,50]; p=3, l=8
buf.put(new byte[] {60, 70}); // p=5, l=8
buf.flip();                  // p=0, l=5

// Five readable bytes: 30, 40, 50, 60, 70.
~~~

**Standard cycle:** `flip() → process partial data → compact() → fill more → flip()`.

### Why Not `rewind()` After `compact()`?

Immediately after `compact()`, the buffer is in **write mode**: `position = number of unprocessed bytes`, `limit = capacity`. Calling `rewind()` here sets `position=0` while **keeping `limit=capacity`**, which can expose stale bytes or bytes not yet belonging to the payload. When you want to read the available data after appending new writes, use **`flip()`** to bound the exact valid byte count.

### What If No Unread Bytes Remain?

If `position == limit` before `compact()`, then `remaining=0`:

- No elements are shifted to the front.
- The result is `position=0, limit=capacity`.
- New data can be filled in, matching `clear()`'s write-ready cursor state.

Yet the intent of the two methods still differs: `compact()` follows a policy of **preserving unprocessed data**; `clear()` declares the current read region discarded and prepares for fresh writes. Neither guarantees erasing old bytes from memory.

### Read-Only Buffers and Portability

`compact()` is an operation that **writes/copies elements** inside the buffer; on a read-only `ByteBuffer` (e.g., from `asReadOnlyBuffer()`), it throws `ReadOnlyBufferException`. Meanwhile, `rewind()`, `mark()`, and `reset()` can still adjust the position of a read-only buffer.

`ByteBuffer`, `CharBuffer`, and other primitive buffers support `compact()` in units of their own elements. Positions and counts in `CharBuffer` are measured in **char code units**, not bytes; in `IntBuffer`, in 32-bit integers. Do not impose `ByteBuffer`'s byte unit on every buffer type.

## 6. Direct Comparison Table

Assume before the operation: `position=p`, `limit=l`, `capacity=c`, and a mark may be set.

| Method | position after | limit after | Data | Mark after | Usage |
|---|---:|---:|---|---|---|
| `rewind()` | `0` | `l` (unchanged) | Not moved/erased | Discarded | Re-read from start of current region |
| `reset()` | old `mark` | `l` (unchanged) | Not moved/erased | **Preserved** | Return to bookmarked position |
| `compact()` | `l - p` | `c` | **Shifts unread data to front** | Discarded | Keep incomplete portion to write more |
| `flip()` *(reference)* | `0` | old `p` | Not moved/erased | Discarded | Switch write → read |
| `clear()` *(reference)* | `0` | `c` | Not physically erased | Discarded | Prepare new writes, ignoring unread data |

If `mark()` was never called, `reset()` throws `InvalidMarkException`. `compact()` throws `ReadOnlyBufferException` if the buffer is read-only.

**Mnemonic:**

- **re-wind** → brings cursor back to the **start** to re-read;
- **re-set** → brings cursor back to the **mark**;
- **com-pact** → **packs unread data to the front**, placing cursor after the retained data to write more.

## 7. Runnable Java 17+ Program and Exact Stdout

Save the following code as **`BufferNavigationDemo.java`**. The program separates two buffers to trace both flows: re-reading with mark/rewind and handling partial data with compact.

~~~java
import java.nio.ByteBuffer;
import java.nio.InvalidMarkException;
import java.util.StringJoiner;

public class BufferNavigationDemo {

    private static void show(String name, ByteBuffer b) {
        System.out.printf(
                "%s: p=%d, l=%d, c=%d, remaining=%d%n",
                name, b.position(), b.limit(),
                b.capacity(), b.remaining());
    }

    public static void main(String[] args) {
        // Part 1: mark/reset and rewind.
        ByteBuffer a = ByteBuffer.allocate(6);
        a.put(new byte[] {10, 20, 30, 40});
        a.flip();

        show("after flip", a);
        System.out.println("first=" + Byte.toUnsignedInt(a.get()));

        a.mark(); // mark = 1
        System.out.println("next=" + Byte.toUnsignedInt(a.get()));
        System.out.println("another=" + Byte.toUnsignedInt(a.get()));

        a.reset(); // Return to mark = 1.
        show("after reset", a);
        System.out.println("again=" + Byte.toUnsignedInt(a.get()));

        a.rewind(); // Back to position = 0, discard mark.
        show("after rewind", a);
        System.out.println("replay=" + Byte.toUnsignedInt(a.get()));

        try {
            a.reset(); // Mark was discarded by rewind().
        } catch (InvalidMarkException e) {
            System.out.println("reset after rewind: InvalidMarkException");
        }

        // Part 2: preserve unprocessed bytes then write more.
        ByteBuffer b = ByteBuffer.allocate(8);
        b.put(new byte[] {10, 20, 30, 40, 50});
        b.flip();

        System.out.println("consumed="
                + Byte.toUnsignedInt(b.get()) + ","
                + Byte.toUnsignedInt(b.get()));
        show("before compact", b);

        b.compact(); // Keep 30,40,50 at front; p=3, l=8.
        show("after compact", b);
        b.put(new byte[] {60, 70});
        b.flip();
        show("after next flip", b);

        StringJoiner values = new StringJoiner(",");
        while (b.hasRemaining()) {
            values.add(Integer.toString(Byte.toUnsignedInt(b.get())));
        }
        System.out.println("recovered=" + values);
    }
}
~~~

Run from the directory containing the source file:

~~~bash
javac BufferNavigationDemo.java
java BufferNavigationDemo
~~~

**Stdout:**

~~~text
after flip: p=0, l=4, c=6, remaining=4
first=10
next=20
another=30
after reset: p=1, l=4, c=6, remaining=3
again=20
after rewind: p=0, l=4, c=6, remaining=4
replay=10
reset after rewind: InvalidMarkException
consumed=10,20
before compact: p=2, l=5, c=8, remaining=3
after compact: p=3, l=8, c=8, remaining=5
after next flip: p=0, l=5, c=8, remaining=5
recovered=30,40,50,60,70
~~~

**Output explanation:**

1. Buffer `a` had 4 bytes filled, so after `flip()`: `p=0, l=4, c=6`. `get()` returns 10 and moves the cursor to 1.
2. `mark()` records bookmark 1. The next two reads get 20 and 30. `reset()` restores `p=1`, so the next read gets 20 again.
3. `rewind()` sets `p=0` while keeping `l=4`; reading again gets 10. Because the mark was cleared, the subsequent `reset()` throws `InvalidMarkException`.
4. Buffer `b` consumed 10 and 20, leaving exactly three bytes `30,40,50`. `compact()` moves those three bytes to the front and sets `p=3, l=8`.
5. Appending 60 and 70 in the next two slots sets `p=5`; `flip()` sets `p=0, l=5`. Reading produces **30,40,50,60,70**, without the two already consumed bytes.

## 8. Practical Example: Reading Incomplete Records from FileChannel

Suppose a data protocol consists of records of **exactly 4 bytes each**, decoded with `getInt()`. A single `FileChannel.read(buffer)` call might fill the buffer with a byte count that is not a multiple of 4. In that case, the remainder must be kept for the next read.

The following example is an **illustrative snippet** inside a processing method; `input` is an open `FileChannel` reading from a file source, and the surrounding code must handle I/O exceptions:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(1024);

while (input.read(buffer) != -1) {
    buffer.flip(); // Switch newly read + leftover bytes to read mode.

    while (buffer.remaining() >= Integer.BYTES) {
        int value = buffer.getInt(); // Process one exact 4-byte record.
        consume(value);              // Application-defined method.
    }

    // If 1..3 bytes remain, keep them and make room for the next read.
    buffer.compact();
}

buffer.flip(); // Check remaining bytes after EOF.
if (buffer.hasRemaining()) {
    throw new java.io.EOFException("Ban ghi 4 byte cuoi bi thieu");
}
~~~

Why use `compact()` here?

- Suppose a read produces 6 bytes: the parser handles the first 4 bytes, leaving 2 bytes in `[position, limit)`.
- `compact()` shifts those 2 bytes to index 0 and sets `position=2`; the next channel read appends bytes starting at index 2.
- Once at least 2 more bytes arrive, `flip()` lets the parser read the next complete 4-byte record.
- Using `clear()` instead would treat the 2-byte remainder as expendable and allow it to be overwritten; using `rewind()` could cause the parser to re-read the 4 already processed bytes.
- If EOF is reached while 1..3 bytes remain, the trailing data **is insufficient for one record**; the example explicitly throws an error instead of silently dropping data.

**Note for non-blocking I/O:** a read call can return `0` before EOF; integrate with a readiness/selector mechanism or an appropriate wait strategy to avoid busy-spinning. The example above shows buffer usage with sequential `FileChannel` reads; it is not a complete multi-threaded network decoder. If the file uses a byte order other than `ByteBuffer`'s default big-endian, set `buffer.order(ByteOrder.LITTLE_ENDIAN)` or match the protocol.

### A Closely Related Case: Partial Writes to a Channel

When `SocketChannel.write(buffer)` consumes only **part of the remaining bytes**, the buffer keeps `position` at the first unsent byte. If you need to **append another payload** to the same buffer before the next write, `compact()` shifts the unsent bytes to the front so the program can `put(...)` the new part and call `flip()` to prepare for sending again.

If you only need to continue sending the existing bytes **without adding new data**, compacting is usually unnecessary: just continue calling `write(buffer)` according to your readiness policy until `hasRemaining()==false`. Do not use `rewind()`, as that could re-send bytes already consumed by the channel.

## 9. Common Errors, Causes, and Fixes

| Symptom | Common Cause | Fix |
|---|---|---|
| Re-reading already processed bytes | Using `rewind()` instead of `compact()` after partial parsing | Compact only the remainder, fill more, then `flip()` before the next parse |
| `InvalidMarkException` | Forgot `mark()`, or mark was discarded by `flip/clear/rewind/compact` | Set mark right before the speculative read; track mark lifecycle |
| `reset()` does not go to buffer start | Mark was placed at a non-zero position | Use `rewind()` if you truly want position 0 |
| `rewind()` reads extra values after writing | `limit` is still `capacity`, forgot `flip()` | Call `flip()` after the `put` phase to bound written data |
| Reading immediately after `compact()` sees stale data | Compact leaves buffer in **write mode** with `limit=capacity` | Fill more as needed, then `flip()` before reading |
| `BufferUnderflowException` | Reading more than `remaining()` | Check enough bytes exist before decoding; compact partial data to fill more |
| `BufferOverflowException` | No space left for `put` calls | Check `remaining()`, drain some data, or allocate an appropriate buffer |
| `ReadOnlyBufferException` on compact | Buffer does not allow writes | Use a writable buffer or copy data into a new writable buffer |
| Content changes after `reset()` are not undone | Mark only saves **position** | If value rollback is needed, manage separate data copies/transactions |
| Old bytes remain in backing array after `compact()` | Compact does not erase unused space | Judge valid data by `position/limit`, not the whole backing array |

## 10. Choosing the Right One in Practice

- **Need to re-read the entire active region:** `rewind()`. Condition: `limit` already represents the exact read boundary.
- **Need to read speculatively and return to a specific point:** `mark()` then `reset()`. Condition: mark is still valid; do not expect mark to snapshot old bytes.
- **Need to keep unparsed/unsent data and append more:** `compact()`, continue `put` or `channel.read(buffer)`, then `flip()`.
- **Just finished writing into the buffer and want to read:** `flip()`.
- **Want to discard all unprocessed content and fill from scratch:** `clear()`.
- **Need random movement to an arbitrary offset:** validate range and consider `position(index)`; do not use `reset()` without an active mark.

### Quick Self-Check

1. `position=4, limit=7, capacity=10`. After `rewind()`? **`position=0, limit=7, capacity=10`**.
2. Same initial state, after `compact()`? **Moves the 3 remaining elements to the front, `position=3, limit=10, capacity=10`**.
3. `mark()` at 2, read up to 5, then `reset()`? **`position=2`**, limit unchanged.
4. Calling `rewind()` then `reset()` without re-calling `mark()`? **`InvalidMarkException`**.
5. After `compact()` with `position=3, limit=8`, you want to read the exact three retained bytes without writing more—what do you call? **`flip()`** to yield `position=0, limit=3`.
6. The parser consumed 7 out of 10 valid bytes, leaving 3 bytes—not enough for a record. What should you use before the next fill? **`compact()`**, not `rewind()`.
7. Does `reset()` discard the mark? **No.** `clear()`, `flip()`, `rewind()`, and `compact()` do.
8. Does `compact()` guarantee writing zeros into empty trailing slots? **No.** Data outside the payload region must be treated as meaningless.

## 11. Official Documentation

- [Java SE 17 — `Buffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/Buffer.html): `position`, `limit`, `capacity`, `mark`, `reset`, `rewind`, `clear`, `flip`, and buffer invariants.
- [Java SE 17 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `compact`, `get/put` operations, views, and read-only constraints.
- [Java SE 17 — `FileChannel`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): reading/writing buffers via channels.
- [Java SE 17 — `InvalidMarkException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/InvalidMarkException.html): exception thrown when `reset()` is called without a valid mark.
