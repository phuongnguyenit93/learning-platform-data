# `remaining()`, `hasRemaining()`, and NIO Buffer Overflow or Underflow Errors

## 1. Lesson Objectives

In Java NIO, a `Buffer` is not just a memory region holding data. It also maintains a **read/write state** consisting of `capacity`, `limit`, and `position`. The two methods `remaining()` and `hasRemaining()` answer questions about the remaining span **between `position` and `limit`**, without themselves knowing whether that span holds meaningful data or whether there is enough free space in a file.

After this lesson, you will be able to:

- Compute `remaining()` and interpret `hasRemaining()` from buffer state.
- Properly use `flip()`, `clear()`, `rewind()`, and `compact()` to switch between writing data into a buffer and reading data out of a buffer.
- Distinguish `BufferUnderflowException` (relative read with insufficient data) from `BufferOverflowException` (relative write with insufficient space).
- Recognize other exceptions: `IndexOutOfBoundsException`, `ReadOnlyBufferException`; avoid confusing channel EOF with buffer underflow.
- Write `ByteBuffer` read/write loops over `FileChannel`, including handling cases where a single write does not drain the entire buffer.

The examples use Java 17+ and the classes `java.nio.Buffer`, `java.nio.ByteBuffer`, `java.nio.BufferUnderflowException`, and `java.nio.BufferOverflowException`. The same foundational rules apply to buffers with other element types such as `CharBuffer`, `IntBuffer`, or `DoubleBuffer`; pay attention that their counting unit is **elements**, not necessarily bytes.

## 2. The Trio: `position`, `limit`, `capacity`

A buffer maintains these values:

| Property | Meaning | Constraint |
| --- | --- | --- |
| `capacity()` | Maximum number of elements the buffer can hold | `capacity >= 0`, constant throughout the buffer's lifetime |
| `limit()` | Exclusive boundary of the region accessible in the current state | `0 <= limit <= capacity` |
| `position()` | Index of the next **relative** read/write operation | `0 <= position <= limit` |
| `mark` | Optional position bookmarked by `mark()` for `reset()` to return to | If set, `mark <= position` |

**Core formulas:**

```text
remaining() = limit() - position()
hasRemaining() = (position() < limit())
               = (remaining() > 0)
```

Because the API enforces `0 <= position <= limit`, `remaining()` is never negative. A buffer can still have physical capacity (`capacity > limit`) while `remaining() == 0`, because only the range from `position` to the **current limit** is available for relative operations.

Illustration of a byte buffer with `capacity = 8`:

```text
index:       0 1 2 3 4 5 6 7 |8 (capacity)
             . . . . . . . .
                       ^     ^
                  position=5 limit=8
remaining=8-5=3; hasRemaining=true
```

If `position = limit = 8`, then `remaining = 0` and `hasRemaining = false`. If `limit` is lowered to 6 and `position` is 6, the result is also 0 **even though capacity is still 8**.

`remaining()` does not measure how much data was written in the past; the meaning of `[position, limit)` is established by your operational phase:

- In **write mode** (e.g., newly created buffer or after `clear()/compact()`), `remaining()` is typically how many more elements can be written.
- In **read mode** (after `flip()`), `remaining()` is typically how many elements are ready to be consumed, **provided** the data was properly prepared beforehand.

Read/write mode concepts here are **usage conventions** set up by the programmer via `position` and `limit`. `ByteBuffer` has no `isReadMode()` boolean property and will not automatically block every out-of-phase operation.

## 3. Typical Buffer States

Suppose `ByteBuffer buffer = ByteBuffer.allocate(6)`. The new buffer has `position = 0`, `limit = capacity = 6`.

### Step 1: Write 4 bytes into the buffer

```text
After put([10,20,30,40]):
index:       0   1   2   3   4   5
value:      10  20  30  40   ?   ?
                           ^
                         position=4; limit=6
remaining = 2  (space left to write in write mode)
```

### Step 2: `flip()` to prepare for reading

`flip()` sets `limit = old position` and then `position = 0`; mark is discarded.

```text
After flip():
index:       0   1   2   3   4   5
value:      10  20  30  40   ?   ?
             ^               ^
         position=0        limit=4
remaining = 4  (written bytes ready to be consumed in read mode)
```

Now `get()` reads the byte at `position` and increments `position`. After reading 3 bytes, `position = 3`, `limit = 4`, and `remaining = 1`.

### Step 3: `compact()` preserves the unread portion

`compact()` copies the unread `[position, limit)` segment to the beginning of the buffer, then sets `position` to the number of retained elements, `limit = capacity`, and discards mark. If byte 40 remains unread:

```text
Before compact:  position=3, limit=4, remaining=1
After compact:   byte 40 is moved to index 0
                 position=1, limit=6, remaining=5
```

The buffer returns to a state suited for **appending writes** starting at position 1. Writing byte 50 and then calling `flip()` lets the buffer read 40 and 50 in order. Do not call `clear()` instead of `compact()` when unread data must be preserved: `clear()` only resets the cursors and does not preserve the boundary of the pending portion.

## 4. Complete Java 17+ Example: Tracking `remaining()` and `hasRemaining()`

Create **`BufferLifecycleDemo.java`**:

```java
import java.nio.ByteBuffer;
import java.util.Arrays;

public class BufferLifecycleDemo {
    private static void state(String label, ByteBuffer buffer) {
        System.out.printf(
                "%s: position=%d, limit=%d, capacity=%d, remaining=%d, has=%s%n",
                label,
                buffer.position(),
                buffer.limit(),
                buffer.capacity(),
                buffer.remaining(),
                buffer.hasRemaining()
        );
    }

    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(6);
        state("new", buffer);

        buffer.put(new byte[] {10, 20, 30, 40});
        state("after put", buffer);

        buffer.flip();
        state("after flip", buffer);

        System.out.println("first=" + buffer.get());
        state("after get", buffer);

        byte[] pair = new byte[2];
        buffer.get(pair);
        System.out.println("pair=" + Arrays.toString(pair));
        state("after pair", buffer);

        buffer.compact();
        state("after compact", buffer);

        buffer.put((byte) 50);
        buffer.flip();

        byte[] result = new byte[buffer.remaining()];
        buffer.get(result);
        System.out.println("result=" + Arrays.toString(result));
        state("at end", buffer);
    }
}
```

```bash
javac BufferLifecycleDemo.java
java BufferLifecycleDemo
```

Stdout on successful run:

```text
new: position=0, limit=6, capacity=6, remaining=6, has=true
after put: position=4, limit=6, capacity=6, remaining=2, has=true
after flip: position=0, limit=4, capacity=6, remaining=4, has=true
first=10
after get: position=1, limit=4, capacity=6, remaining=3, has=true
pair=[20, 30]
after pair: position=3, limit=4, capacity=6, remaining=1, has=true
after compact: position=1, limit=6, capacity=6, remaining=5, has=true
result=[40, 50]
at end: position=2, limit=2, capacity=6, remaining=0, has=false
```

Key point: on the `after put` line, `remaining = 2` means **two empty slots remain for `put` in the write phase**. After `flip`, `remaining = 4` means **four bytes are waiting to be read**. Both measurements use the exact same formula but are interpreted according to the current phase.

`compact()` keeps the unread byte 40; byte 50 is appended right after it. The line `result=[40, 50]` confirms processing the next chunk without losing the pending data from the previous chunk.

## 5. `BufferUnderflowException`: Requesting a Read Beyond `limit`

`BufferUnderflowException` is a runtime exception thrown when a **relative read** from a buffer asks for more elements than `remaining()`. For example:

```java
ByteBuffer b = ByteBuffer.allocate(2);
b.get(); // BufferUnderflowException? NO:
         // allocate(2) creates position=0, limit=2;
         // in terms of NIO state, get() can still read one byte.
```

Subtle point: **a newly allocated buffer is not automatically in read mode**. It has `remaining = 2`, so `get()` does not throw underflow merely because the application has not explicitly called `put()`. Data read from a newly created `ByteBuffer.allocate` is zero-initialized by the allocation contract, even though you have not yet placed meaningful protocol data in it.

For a **proper** example of underflow, set `limit` to 0 via `flip()` when zero bytes have been written:

```java
ByteBuffer emptyForRead = ByteBuffer.allocate(2);
emptyForRead.flip();       // position=0, limit=0
emptyForRead.get();        // BufferUnderflowException
```

Or after consuming all valid data in read mode:

```java
ByteBuffer b = ByteBuffer.allocate(2);
b.put((byte) 7);
b.flip();                  // position=0, limit=1
b.get();                   // OK: 7; position=1
b.get();                   // BufferUnderflowException
```

Similarly, if the buffer has only `2` bytes left in read mode yet you call `b.get(new byte[3])`, that is underflow. For bulk `get` calls, the API checks that enough elements exist before transferring; if insufficient, the buffer's `position` is not partially advanced because the call fails.

**Important:** `BufferUnderflowException` indicates that **the current buffer** does not have enough elements within `limit`, not that the file/channel has ended. Reading from `FileChannel.read(buffer)` returns `-1` at EOF; reading from `SocketChannel` in non-blocking mode may return `0` when no data is available yet. Those two states are distinct from an exception caused by calling `ByteBuffer.get()` for too many elements.

## 6. `BufferOverflowException`: Writing Beyond `limit`

`BufferOverflowException` occurs when a **relative write** into a buffer requires more elements than the current `remaining()` space.

```java
ByteBuffer b = ByteBuffer.allocate(2);
b.put((byte) 7);
b.put((byte) 8);
b.put((byte) 9);            // BufferOverflowException
```

Once 2 bytes are written, `position = limit = capacity = 2`; `remaining = 0`. To continue writing into the buffer, you must consume/drain existing data following the proper cycle and then call `clear()` or `compact()`. Do not simply call `flip()` after the buffer fills and keep calling `put()`: `flip()` prepares to **read** the written data, setting `position=0` and `limit=2`; calling `put()` then would **overwrite** data waiting to be read.

Important note for bulk put:

```java
ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
ByteBuffer target = ByteBuffer.allocate(2);
target.put(source); // BufferOverflowException
```

Because `source.remaining() = 3` while `target.remaining() = 2`, `target.put(source)` throws `BufferOverflowException`; under the buffer bulk-put contract, it is not allowed to "copy 2 bytes and then throw." Both positions stay unchanged. You must slice into appropriately sized chunks manually if you want partial copying.

**Buffer overflow does not mean disk space is exhausted.** It signals the logical capacity boundary of the current `Buffer`. Disk write failures typically surface as `IOException` or storage-specific exceptions.

## 7. Distinguishing Underflow, Overflow, Index, and Read-Only

| Situation | Typical Exception or Result | How to Handle |
| --- | --- | --- |
| `get()` when `remaining() == 0` | `BufferUnderflowException` | Read only while elements remain, or fill more data then `flip()` |
| `get(byte[4])` when remaining is only 3 | `BufferUnderflowException` | Request fewer bytes or gather more input |
| `put(byte)` when remaining is 0 | `BufferOverflowException` | Drain/consume the buffer then `clear()/compact()` |
| `put(sourceBuffer)` when source.remaining exceeds target.remaining | `BufferOverflowException` | Split data into chunks or use a larger target buffer |
| `get(index)` or `put(index, value)` with index invalid relative to limit | `IndexOutOfBoundsException` | Validate the **absolute** access index |
| `put(...)` into a read-only buffer | `ReadOnlyBufferException` | Use a writable buffer or only read from this view |
| `FileChannel.read(buffer)` at EOF | Returns `-1` | Finish processing final data; do not treat this as BufferUnderflowException |
| `Channel.write(buffer)` writes partially | Returns actual bytes written | Continue while `buffer.hasRemaining()`, handling zero-progress cases |

Not every invalid access throws `BufferUnderflowException` or `BufferOverflowException`. Absolute methods such as `get(index)` check the index against `limit` and throw `IndexOutOfBoundsException` when out of bounds; they **do not change `position`**. For instance, `ByteBuffer.allocate(2).get(2)` exceeds limit 2, without changing cursor state.

`ReadOnlyBufferException` relates to write permissions on the buffer, not remaining count. View buffers such as `asReadOnlyBuffer()` can share underlying memory while disallowing writes through the read-only view.

## 8. Complete Java 17+ Example: Reproducing Each Error

Create **`BufferErrorsDemo.java`**:

```java
import java.nio.BufferOverflowException;
import java.nio.BufferUnderflowException;
import java.nio.ByteBuffer;
import java.nio.ReadOnlyBufferException;

public class BufferErrorsDemo {
    public static void main(String[] args) {
        ByteBuffer buffer = ByteBuffer.allocate(2);

        buffer.flip(); // no bytes were put; limit=0
        try {
            buffer.get();
        } catch (BufferUnderflowException ex) {
            System.out.println("underflow: position=" + buffer.position());
        }

        buffer.clear();
        buffer.put((byte) 7).put((byte) 8);
        try {
            buffer.put((byte) 9);
        } catch (BufferOverflowException ex) {
            System.out.println("overflow: position=" + buffer.position());
        }

        buffer.flip(); // position=0, limit=2
        try {
            buffer.get(new byte[3]);
        } catch (BufferUnderflowException ex) {
            System.out.println("bulk underflow: position=" + buffer.position());
        }

        try {
            buffer.get(2); // index=2 == limit => out of bounds
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("absolute index out of bounds");
        }

        ByteBuffer readOnly = buffer.asReadOnlyBuffer();
        try {
            readOnly.put((byte) 1);
        } catch (ReadOnlyBufferException ex) {
            System.out.println("read-only write rejected");
        }

        ByteBuffer source = ByteBuffer.wrap(new byte[] {1, 2, 3});
        ByteBuffer target = ByteBuffer.allocate(2);
        try {
            target.put(source);
        } catch (BufferOverflowException ex) {
            System.out.println("bulk overflow: source="
                    + source.position() + ", target=" + target.position());
        }

        System.out.println("first valid byte=" + buffer.get());
    }
}
```

```bash
javac BufferErrorsDemo.java
java BufferErrorsDemo
```

Stdout on successful run:

```text
underflow: position=0
overflow: position=2
bulk underflow: position=0
absolute index out of bounds
read-only write rejected
bulk overflow: source=0, target=0
first valid byte=7
```

Note: the initial `buffer.flip()` sets `limit=0` and guarantees underflow on the subsequent read; unlike the common buggy example of calling `get()` right after `allocate(2)` expecting underflow. A failed bulk read does not advance `position`, so the final `get()` reads byte 7 as expected.

## 9. Avoiding Errors by Checking Remaining Space

### Reading One Element

If the requirement is "read while available, stop when buffer ends," `hasRemaining()` is suitable:

```java
while (buffer.hasRemaining()) {
    byte value = buffer.get();
    // Process value
}
```

However, if the protocol requires **exactly 4 bytes**, checking only `hasRemaining()` is insufficient. With `ByteBuffer`:

```java
if (buffer.remaining() >= Integer.BYTES) {
    int value = buffer.getInt();
    // Process value
} else {
    // Fewer than 4 bytes: request more input, or report format error.
}
```

`getInt()` needs 4 consecutive bytes; `remaining() == 1` makes `hasRemaining()` return `true`, yet `getInt()` will still throw `BufferUnderflowException`. Likewise `getLong()` needs 8 bytes; whereas one `CharBuffer.get()` needs one `char` element.

### Writing an Element or Group of Elements

```java
if (buffer.remaining() >= Long.BYTES) {
    buffer.putLong(123L);
} else {
    // Flush/consume existing data, compact if unused portion must be kept,
    // or allocate a buffer large enough for the design requirements.
}
```

If writing an array `data` with `offset` and `length`, check both the expected byte count and the validity of `offset`/`length`. Never treat `hasRemaining()` as sufficient for a bulk operation larger than 1 element.

### When a Full Record Is Mandatory

In network protocols with fixed headers or length-prefixed payloads, you may need to wait until all bytes of a record arrive. The typical processing pattern is:

1. Read into the buffer while in write mode.
2. `flip()` to read the received bytes.
3. Parse only when `remaining()` is enough for the current field.
4. If not enough, **do not arbitrarily consume a partial record**; you can use `mark()/reset()` under controlled state or read only after verifying sufficient bytes.
5. `compact()` to preserve unread bytes, read more, and repeat.

`mark()` saves `position`; `reset()` returns to the mark. Calling `flip()`, `clear()`, `rewind()`, or `compact()` invalidates the mark; calling `reset()` without a valid mark throws `InvalidMarkException`. `position(newPosition)` or `limit(newLimit)` can also discard the mark when the mark is no longer compatible with the new state.

## 10. `flip()`, `clear()`, `rewind()`, `compact()`: Picking the Right One

| Method | Position After | Limit After | Meaning |
| --- | --- | --- | --- |
| `flip()` | 0 | Old position | Switch from writing data to consuming data |
| `clear()` | 0 | Capacity | Prepare to reuse the entire buffer; **does not erase physical bytes** |
| `rewind()` | 0 | Unchanged | Re-read/re-write from the start of the current range; does not expand limit |
| `compact()` | Remaining elements before compact | Capacity | Keep unconsumed portion, switch to preparing more writes |

These commands manipulate buffer **state**; `clear()` does not fill memory with zeros. After `clear()`, memory may still hold old bytes, yet the program must treat the new logical state as ready for writing. Calling `clear()` followed immediately by `flip()` without writing any bytes sets `limit=0` and `hasRemaining()=false`.

`compact()` is meaningful only with respect to the unconsumed `[position, limit)` segment. Calling `compact()` thoughtlessly while the buffer is in write mode can copy regions the application has not yet treated as valid data. Track the phase before calling it.

## 11. Channel Loops: Remaining Buffer Data May Not Write in One Call

`WritableByteChannel.write(buffer)` attempts to write bytes from the current `[position, limit)` range, increments `position` by the bytes actually written, and **may perform only a partial write**. Thus:

```java
buffer.flip();
while (buffer.hasRemaining()) {
    channel.write(buffer);
}
buffer.clear();
```

This shows the core idea, yet a loop like that **can busy-spin infinitely** if the channel makes no write progress (`write` repeatedly returns 0, common with non-blocking channels when not ready). Choose an appropriate waiting mechanism: with non-blocking `SocketChannel`, use `Selector` / `OP_WRITE` or backpressure; with blocking channels, understand the corresponding I/O semantics.

Another point: `hasRemaining()` only tells you the buffer still has bytes waiting; it does **not** guarantee the destination resource is ready, has space, or will persist the write durably. Successful writes still require checking progress and handling `IOException`.

### Full Example: Copying a File via `FileChannel`

Create **`ChannelCopyDemo.java`**:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class ChannelCopyDemo {
    public static void main(String[] args) throws IOException {
        Path source = Files.createTempFile("nio-source-", ".bin");
        Path destination = Files.createTempFile("nio-dest-", ".bin");

        try {
            byte[] input = "abcdefghi".getBytes(StandardCharsets.UTF_8);
            Files.write(source, input);

            try (FileChannel from = FileChannel.open(
                         source, StandardOpenOption.READ);
                 FileChannel to = FileChannel.open(
                         destination,
                         StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer buffer = ByteBuffer.allocate(4);

                while (true) {
                    int read = from.read(buffer);
                    if (read == -1) {
                        break; // File EOF, not buffer underflow
                    }
                    if (read == 0) {
                        continue; // Rare here with standard FileChannel
                    }

                    buffer.flip();
                    while (buffer.hasRemaining()) {
                        int written = to.write(buffer);
                        if (written == 0) {
                            throw new IOException("FileChannel write made no progress");
                        }
                    }
                    buffer.clear();
                }
            }

            System.out.println("copied bytes=" + Files.size(destination));
            System.out.println("matches=" + Arrays.equals(
                    input, Files.readAllBytes(destination)));
        } finally {
            Files.deleteIfExists(source);
            Files.deleteIfExists(destination);
        }
    }
}
```

```bash
javac ChannelCopyDemo.java
java ChannelCopyDemo
```

Stdout on successful run:

```text
copied bytes=9
matches=true
```

Step-by-step explanation: the buffer has capacity 4; `from.read(buffer)` fills bytes and advances `position`; `flip()` sets `limit` to the bytes loaded; `to.write(buffer)` transfers part or all of the remaining bytes, possibly across multiple calls; `clear()` prepares the buffer for the next read. The 9-byte file is transferred in chunks of up to 4 bytes without losing the final (1-byte) chunk.

The example uses a **regular `FileChannel`** for local files. With non-blocking channels, handling `read == 0` or `write == 0` requires an event-driven wait strategy; never spin continuously in a `continue` loop burning CPU. In production code, creating two temp files sequentially should also ensure proper cleanup even if the second creation fails; here the primary focus is demonstrating the buffer state protocol.

## 12. Buffer Views, Slices, and Shared Memory

`duplicate()`, `slice()`, and `asReadOnlyBuffer()` create buffers sharing underlying contents while having **independent `position`/`limit`/`mark`**. This directly affects `remaining()` and `hasRemaining()`:

```java
ByteBuffer original = ByteBuffer.wrap(new byte[] {10, 20, 30, 40});
original.position(1);
original.limit(3);          // original remaining = 2

ByteBuffer slice = original.slice(); // capacity=2, position=0, limit=2
slice.get();                // slice position=1, remaining=1

System.out.println(original.remaining()); // 2
System.out.println(slice.remaining());    // 1
```

Even though backing data is shared, calling `get()` on `slice` does not advance `original`'s position. Changes to **data bytes** through one view are visible through the other, while their state cursors remain independent.

In multi-threaded code, buffers are not guaranteed thread-safe for arbitrary concurrent access. If threads share a buffer or shared backing memory, an explicit coordination strategy is needed; never treat `remaining()` as an invariant snapshot before a subsequent operation.

## 13. Important Conceptual Boundaries

- `remaining()` on `ByteBuffer` counts **bytes**, on `CharBuffer` counts **`char`s**, and on `IntBuffer` counts **`int`s**. When sizing records, compute in the right unit.
- `buffer.get(byte[])` can raise underflow if too many bytes are requested; `buffer.get(index)` is absolute, checks the index, and does not increment `position`.
- `ByteBuffer.putInt` and `getInt` consume **four bytes**; `hasRemaining() == true` is not enough. Check `remaining() >= Integer.BYTES`.
- `BufferOverflowException` does not mean a file is out of disk space, and `BufferUnderflowException` does not equal network EOF.
- `clear()`, `flip()`, `rewind()`, and `compact()` do not write to disk or read from sockets on their own; they only adjust cursors/limits and, in the case of `compact`, copy unread bytes within the buffer.
- The names **UNDERFLOW/OVERFLOW** in the character decoding API `java.nio.charset.CoderResult` are **coder result states** (checked via `isUnderflow()/isOverflow()`), not `BufferUnderflowException` or `BufferOverflowException`. When working with `CharsetDecoder` or `CharsetEncoder`, follow the coder state contract.
- `ByteBuffer.allocate(...)` creates a heap buffer zero-initialized by Java's defaults, yet "bytes equal to 0" does not automatically constitute a "valid data frame." Your application protocol contract still needs to track how many bytes were validly written/received.
- `ByteBuffer.allocateDirect(...)` differs from heap buffers in allocation and native interaction; `position`/`limit`/`remaining` logic still follows the exact same `Buffer` contract, so bounds-checking principles remain unchanged.

## 14. Common Mistakes and How to Prevent Them

1. **Forgetting `flip()` before reading bytes just `put`.** `position` is still at the end of written data and `limit` has not been narrowed to the actual written count. Switch phases explicitly.
2. **Forgetting `clear()/compact()` before filling the next batch.** The buffer may run out of `remaining` in read mode or write at the wrong index.
3. **Calling `clear()` while unconsumed data remains.** State treats the buffer as empty for new writes; use `compact()` when the remainder must be kept.
4. **Assuming `hasRemaining()` suffices for every operation.** Before calling `getLong()`, check for at least 8 bytes.
5. **Catching underflow/overflow for normal loop control.** When lengths can be checked ahead of time, `remaining()` keeps code cleaner and avoids exceptions in the main control flow.
6. **Confusing buffer overflow with disk errors.** Inspect `position/limit` and the `flip/clear` sequence first.
7. **Buffer-to-buffer copying without checking target capacity.** `target.put(source)` requires room for all of `source.remaining()`; chunk the transfer or use a large enough target.
8. **Calling `get(index)` expecting `position` to advance.** Absolute access does not move `position`; checking with `getFilePointer` is unrelated—use the buffer's `position()`.
9. **Not handling partial channel writes.** A single `write(buffer)` is not guaranteed to consume all bytes; use a loop that checks progress.
10. **Busy-waiting in a non-blocking loop when I/O returns 0.** Use selectors/events instead of spinning indefinitely.
11. **Using `limit=capacity` as the received byte count.** When a channel read fetches fewer bytes, `flip()` sets `limit` to the prior `position`; `capacity` is only the maximum size.
12. **Sharing views and assuming shared `position`.** `slice` and `duplicate` maintain independent cursors even when sharing underlying storage.

## 15. Self-Check Questions and Exercises

1. A buffer has `capacity=16`, `limit=11`, and `position=7`. What are `remaining()` and `hasRemaining()`? What if `position=11`?
2. A newly created `allocate(8)` buffer has `remaining=8`. Does this prove the application has written 8 meaningful bytes into it?
3. After `put`ting 5 bytes into a capacity-8 buffer, why must you call `flip()` before reading those 5 bytes? After `flip`, what are `position` and `limit`?
4. With `remaining()=3` and `hasRemaining()=true`, is calling `getInt()` valid? What must be checked?
5. A buffer holds 10 bytes of data and 7 bytes have been read. Should you use `clear()` or `compact()` if the last 3 bytes must be preserved to combine with a new chunk?
6. Why does `ByteBuffer.get(10)` when `limit=10` throw `IndexOutOfBoundsException`, whereas `get()` when `position=limit` throws `BufferUnderflowException`?
7. Why does `FileChannel.read(buffer)==-1` mean something different from `BufferUnderflowException`?
8. Can you conclude all data was sent if a single `SocketChannel.write(buffer)` returns fewer bytes than `buffer.remaining()` before the call? How would you design the loop?
9. Two buffers `original` and `original.slice()` share memory; does calling `slice.get()` increment `original.position()`?
10. Predict the full stdout of `BufferLifecycleDemo`, run it to verify, and then modify the program so `compact()` retains the last 2 bytes instead of 1.

## 16. Knowledge Summary

The core of NIO Buffer is **`0 <= position <= limit <= capacity`**, from which:

```text
remaining() = limit - position
hasRemaining() = remaining() > 0
```

In the write phase, `remaining()` is typically space available to write more; in the read phase, it is the number of elements left to consume. `BufferUnderflowException` reports a relative read exceeding the available span, while `BufferOverflowException` reports a relative write exceeding the remaining space. Use `flip()` to start reading newly loaded data, `clear()` to reuse once fully consumed, `compact()` to retain leftovers, and `remaining()` to verify enough space/data for the exact **element count** the next API call needs. When integrating with channels, whether the buffer still has elements is only one loop condition; EOF, partial writes, and non-blocking readiness must be handled explicitly.
