# FileChannel: Reading and Writing at Absolute Positions Without Changing Position

## 1. The Problem: Accessing a File Region While Preserving Current Position

In Java NIO, `java.nio.channels.FileChannel` provides two styles of read/write operations:

- **At the channel's current position**: `read(ByteBuffer dst)` and `write(ByteBuffer src)`.
- **At a specified absolute position** (*positional I/O*): `read(ByteBuffer dst, long position)` and `write(ByteBuffer src, long position)`.

The core difference: **the two methods with a `long position` argument perform I/O at the passed byte offset, without modifying the current position of the `FileChannel` itself**. They are very useful when reading a header, updating a record, or fetching a data slice at a known offset without disturbing a sequential processing flow sharing the same channel.

You must distinguish three different values:

1. **`channel.position()`**: the current byte offset of the *file* on the channel; used and usually changed by `read(dst)`/`write(src)` without an offset argument.
2. **The `position` parameter in `read(dst, position)` or `write(src, position)`**: the *absolute* byte offset for that operation; **not** a relative shift from `channel.position()`.
3. **`buffer.position()`**: the next index inside the `ByteBuffer`; **still advances** when bytes are actually read into or written from the buffer, even in positional I/O with an absolute offset.

For example, the channel is currently at offset 100. Calling `channel.read(dst, 20)` seeks to read starting from the 21st byte of the file (offset 20). After reading 8 bytes, `channel.position()` is still **100**, while `dst.position()` increases by **8** from the buffer's initial position.

## 2. API and Usage Conditions

Core methods of `FileChannel`:

```java
int read(ByteBuffer dst) throws IOException;
int read(ByteBuffer dst, long position) throws IOException;

int write(ByteBuffer src) throws IOException;
int write(ByteBuffer src, long position) throws IOException;

long position() throws IOException;
FileChannel position(long newPosition) throws IOException;
long size() throws IOException;
```

These are abbreviated API signatures for illustration, not a complete program.

| Method | Starting position in file | Changes `channel.position()`? | Changes `ByteBuffer.position()`? |
| --- | --- | --- | --- |
| `read(dst)` | Channel's current position | Yes when bytes are read | Yes when bytes are read |
| `write(src)` | Channel's current position | Yes when bytes are written | Yes when bytes are written |
| `read(dst, offset)` | Passed-in offset | **No** | **Yes** when bytes are read |
| `write(src, offset)` | Passed-in offset | **No** | **Yes** when bytes are written |
| `channel.position(newPosition)` | Changes channel position for subsequent I/O | **Yes** | No |

**Offsets are 0-based byte counts.** Passing a negative offset to positional I/O throws `IllegalArgumentException`. Do not confuse offset 0 as "byte zero" in human counting: it is the **first byte** of the file.

`FileChannel` can be created with `FileChannel.open(path, options...)` or obtained from related APIs such as `FileInputStream.getChannel()`, `FileOutputStream.getChannel()`, and `RandomAccessFile.getChannel()`. Read/write capability depends on permissions and open mode, not just the Java type.

Example of opening a channel with read and write permissions:

```java
try (FileChannel channel = FileChannel.open(
        path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
    // read/write with absolute offset
}
```

This snippet assumes `path` is a valid `Path` and required classes are imported. `READ`/`WRITE` modes must be specified according to the operation; reading a channel not opened for reading may throw `NonReadableChannelException`, and writing a channel not opened for writing may throw `NonWritableChannelException`.

## 3. Illustrating Two Independent Position Types

Suppose a file contains eight ASCII bytes:

```text
File:     A   B   C   D   E   F   G   H
Offset:   0   1   2   3   4   5   6   7
                                  ^
                         channel.position() = 6
```

We create `ByteBuffer.allocate(3)` with `buffer.position() == 0` and call:

```java
int count = channel.read(buffer, 2);
```

If the call reads all three bytes:

```text
File read from offset 2: C D E
Total bytes read: 3
channel.position(): 6       (unchanged)
buffer.position(): 3        (increased from 0 to 3)
buffer.limit(): 3           (unchanged, because allocate(3))
```

If only one byte is read, `count=1` and `buffer.position()=1`. **You cannot assert that a single call always reads all three bytes.**

For writing, suppose `src` has data `X Y`, `src.position()==0`, `src.limit()==2`. Calling `channel.write(src, 4)` to write at offset 4 replaces bytes `E, F` with `X, Y` if both bytes are written. `channel.position()` remains 6; `src.position()` becomes 2.

**Positional I/O does not change the channel position**, yet it **can still change file contents, file size, and the buffer's position**. It also does not automatically lock data to prevent other threads or processes from modifying it concurrently.

## 4. Standalone Java 17+ Example: Comparing Positions Before and After

This example creates a temporary file containing five ASCII bytes `ABCDE`, sets `FileChannel.position(2)`, reads two bytes from offset 0, and writes `XY` at offset 3.

To ensure the exact required byte count is processed, the program loops while the operation is incomplete. Each subsequent read/write must calculate **initial absolute offset + total bytes processed**, because the channel itself does not advance its position during positional I/O.

**File `PositionalFileChannelDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PositionalFileChannelDemo {
    static int readExactly(FileChannel channel, ByteBuffer dst, long offset)
            throws IOException {
        int total = 0;
        while (dst.hasRemaining()) {
            int n = channel.read(dst, offset + total);
            if (n == -1) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            total += n;
        }
        return total;
    }

    static int writeExactly(FileChannel channel, ByteBuffer src, long offset)
            throws IOException {
        int total = 0;
        while (src.hasRemaining()) {
            int n = channel.write(src, offset + total);
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
            total += n;
        }
        return total;
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("positional-", ".txt");

        try {
            Files.writeString(path, "ABCDE", StandardCharsets.US_ASCII);

            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                channel.position(2);
                System.out.println("Vi tri kenh ban dau: "
                        + channel.position());

                ByteBuffer dst = ByteBuffer.allocate(2);
                int read = readExactly(channel, dst, 0);
                System.out.println("So byte da doc: " + read);
                System.out.println("Vi tri kenh sau doc: "
                        + channel.position());
                System.out.println("Vi tri buffer sau doc: "
                        + dst.position());

                dst.flip();
                System.out.println("Noi dung doc: "
                        + StandardCharsets.US_ASCII.decode(dst));

                ByteBuffer src = ByteBuffer.wrap(
                        "XY".getBytes(StandardCharsets.US_ASCII));
                int written = writeExactly(channel, src, 3);

                System.out.println("So byte da ghi: " + written);
                System.out.println("Vi tri kenh sau ghi: "
                        + channel.position());
                System.out.println("Vi tri buffer sau ghi: "
                        + src.position());
                System.out.println("Kich thuoc tep: " + channel.size());
            }

            System.out.println("Noi dung tep: "
                    + Files.readString(path, StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile and run in the directory containing the source code:

```bash
javac PositionalFileChannelDemo.java
java PositionalFileChannelDemo
```

**Exact stdout if all I/O operations succeed:**

```text
Vi tri kenh ban dau: 2
So byte da doc: 2
Vi tri kenh sau doc: 2
Vi tri buffer sau doc: 2
Noi dung doc: AB
So byte da ghi: 2
Vi tri kenh sau ghi: 2
Vi tri buffer sau ghi: 2
Kich thuoc tep: 5
Noi dung tep: ABCXY
```

Explanation:

1. `channel.position(2)` sets the channel's current offset to 2.
2. `readExactly(channel, dst, 0)` reads two bytes from offsets 0 and 1, without affecting the channel's position=2. The read buffer receives data, so the position of **`dst`** increases from 0 to 2.
3. `dst.flip()` sets the buffer's position to 0 and limit to 2, so the decoder reads `AB` accurately. This method also does not change the channel's position.
4. `writeExactly(channel, src, 3)` writes two bytes `X Y` at offsets 3 and 4. Channel position remains 2; the position of **`src`** increases from 0 to 2.
5. The write **replaces** `D E` in the file `ABCDE`, so the file becomes `ABCXY` and remains 5 bytes long.

Thus, within the same program, **three positions remain unmixed**: `channel.position()` (currently 2), `dst.position()`, and `src.position()` (both advanced in their respective operations).

## 5. Why Must Partial Reads and Partial Writes Be Handled?

The methods `read(ByteBuffer, long)` and `write(ByteBuffer, long)` return the **actual number of bytes transferred in that call**, with no guarantee of consuming all of `buffer.remaining()`.

### Reading by Offset

A method reading all `N` bytes from a fixed offset must maintain:

\[
nextOffset = startOffset + bytesReadSoFar
\]

Suppose 6 bytes need to be read from offset 100, and three `read` calls return 2, 3, and 1 respectively:

| Call | Passed offset | Bytes read | Total read | Channel position |
| --- | ---: | ---: | ---: | --- |
| 1 | 100 | 2 | 2 | Unchanged |
| 2 | 102 | 3 | 5 | Unchanged |
| 3 | 105 | 1 | 6 | Unchanged |

If you **repeatedly call `read(dst, 100)` with the same offset 100**, the second call may re-read previously read bytes into the next part of the buffer. This is one of the easiest mistakes to make when switching from sequential reading APIs to positional I/O.

For `read`:

- `n > 0`: received `n` bytes.
- `n == 0`: no progress in that call; check whether the buffer is out of space, the file state, or I/O conditions.
- `n == -1`: EOF, no more bytes at the requested position to read. If you need exact `N` bytes, handle the missing data.

If the buffer has `remaining()==0`, there is no need to call I/O: the number of bytes to transfer is 0. The `readExactly`/`writeExactly` examples above use a `while (hasRemaining())` loop, so they stop immediately once complete.

### Writing by Offset

With `write(src, startOffset)`, if only `n` bytes are written, `src.position()` advances by `n`, yet the next call must still supply `startOffset + n`. Failing to do so can **overwrite** the bytes just transferred at the start of the target region.

Suppose 5 bytes need to be written at offset 200, and two writes return 2 then 3:

```text
write(src, 200)  --> writes first 2 bytes, src.position advances by 2
write(src, 202)  --> writes remaining 3 bytes
```

Calling `write(src, 200)` twice does not automatically turn the offset into 202, because the position parameter is absolute.

Safe loop pattern for **requiring a full write**:

```java
long startOffset = 200L;
long transferred = 0L;

while (src.hasRemaining()) {
    int n = channel.write(src, startOffset + transferred);
    if (n == 0) {
        throw new IOException("No write progress");
    }
    transferred += n;
}
```

This is an illustrative snippet requiring `src` and `channel` to be declared, not a standalone program. With `FileChannel` and regular files, zero-progress errors usually need to be handled as abnormal conditions. Backoff/wait mechanisms or retry limits must be designed according to the channel class and application requirements, rather than spinning indefinitely.

### Why Not Use `channel.position(...)` Before Every Operation?

You can call `channel.position(offset); channel.read(buffer);`, but doing so **mutates the shared position state**. When you need to access an arbitrary region while preserving the position for another sequential operation, using `channel.read(buffer, offset)` or `channel.write(buffer, offset)` directly makes the intent clearer.

## 6. Reading a Header While the Channel Continues Sequential Processing

A common scenario is:

1. A reader has read sequentially up to offset 512.
2. The application wants to re-check the 16-byte header at offset 0.
3. The reader then needs to resume from offset 512.

If you temporarily call `channel.position(0)`, read the header, and then `channel.position(512)`, the program must save/restore the position itself and control concurrent access. With positional read:

```java
long previous = channel.position(); // e.g., 512

ByteBuffer header = ByteBuffer.allocate(16);
int read = channel.read(header, 0);

System.out.println(channel.position() == previous);
```

The print statement outputs `true` if other actions do not change the position concurrently. However, **`read` may return fewer than 16 bytes**, and `header.position()` increases only by the number of bytes read. If the full header is needed, use a loop incrementing the offset by the amount received, along with EOF checking like `readExactly` in the runnable example.

**The main benefit** is that reading the header does not itself change `channel.position()`. However, file contents can still be modified by another process between reads; positional I/O **does not guarantee a consistent snapshot**.

## 7. Updating a Fixed Record with Positional Write

Suppose a file contains multiple fixed-length records:

| Field | Encoding | Bytes |
| --- | --- | ---: |
| `id` | big-endian `int` | 4 |
| `quantity` | big-endian `int` | 4 |
| Total |  | **8** |

The record at `index` (0-based) starts at:

\[
recordOffset = (long) index \times 8
\]

The `quantity` field starts at `recordOffset + 4`. To change the quantity of the record at index=2, the offset to write is `2 * 8 + 4 = 20`.

Using `ByteBuffer`, we can encode the integer and write 4 bytes at that exact offset without changing the channel position.

**File `PositionalRecordDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class PositionalRecordDemo {
    private static final int RECORD_SIZE = 8;

    private static void writeAll(
            FileChannel channel, ByteBuffer src, long offset)
            throws IOException {
        long written = 0;
        while (src.hasRemaining()) {
            int n = channel.write(src, offset + written);
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
            written += n;
        }
    }

    private static void readAll(
            FileChannel channel, ByteBuffer dst, long offset)
            throws IOException {
        long read = 0;
        while (dst.hasRemaining()) {
            int n = channel.read(dst, offset + read);
            if (n == -1) {
                throw new IOException("Unexpected EOF");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            read += n;
        }
    }

    public static void main(String[] args) throws IOException {
        Path path = Files.createTempFile("records-", ".bin");

        try {
            try (FileChannel channel = FileChannel.open(
                    path, StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer records = ByteBuffer.allocate(3 * RECORD_SIZE);
                records.order(ByteOrder.BIG_ENDIAN);
                records.putInt(101).putInt(5);
                records.putInt(102).putInt(7);
                records.putInt(103).putInt(9);
                records.flip();
                writeAll(channel, records, 0);

                channel.position(6);
                System.out.println("Vi tri truoc: "
                        + channel.position());

                long quantityOffset = 2L * RECORD_SIZE + 4;
                ByteBuffer update = ByteBuffer.allocate(4);
                update.order(ByteOrder.BIG_ENDIAN);
                update.putInt(90).flip();
                writeAll(channel, update, quantityOffset);

                ByteBuffer result = ByteBuffer.allocate(RECORD_SIZE);
                result.order(ByteOrder.BIG_ENDIAN);
                readAll(channel, result, 2L * RECORD_SIZE);
                result.flip();

                System.out.println("Ban ghi index 2: "
                        + result.getInt() + ", " + result.getInt());
                System.out.println("Vi tri sau: "
                        + channel.position());
                System.out.println("Do dai file: " + channel.size());
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile and run:

```bash
javac PositionalRecordDemo.java
java PositionalRecordDemo
```

**Exact stdout under successful I/O conditions:**

```text
Vi tri truoc: 6
Ban ghi index 2: 103, 90
Vi tri sau: 6
Do dai file: 24
```

Why:

- Three records of 8 bytes each create a 24-byte file.
- Initially, record index 2 was `id=103, quantity=9` at offsets 16–23.
- `writeAll(..., 20)` replaces the exact 4 bytes of `quantity` with the big-endian integer 90.
- `readAll(..., 16)` reads back the full record to get `103,90`.
- Neither operation with an explicit offset changes `channel.position()`, which stays at 6.

**Limitation of this example:** writing 4 bytes and reading back does not form an atomic transaction when multiple writers access concurrently. For files with critical data, you must design lock control, writer coordination, crash handling, and consistency structures separately. `channel.position()==6` only proves the cursor state is preserved; **it does not prove the update operation is atomic**.

## 8. ByteBuffer Still Changes Position; Limit Does Not Auto-Change

The `FileChannel.read(dst, offset)` contract reads bytes into the buffer from the current `dst.position()` up to `dst.limit()`:

```text
Initial dst: capacity=10, position=3, limit=7
remaining = 4

If read(dst, 100) returns 2:
dst.position() becomes 5
dst.limit() remains 7
dst.capacity() remains 10
channel.position() is unchanged
```

Similarly, `write(src, offset)` consumes data from `src.position()` to `src.limit()`, advancing the buffer's position by the number of bytes successfully written.

When preparing data for a channel:

- `put(...)` writes into the buffer and advances `buffer.position()`.
- `flip()` switches to draining mode: `limit=old position`, `position=0`.
- `write(buffer, offset)` consumes bytes from the buffer, advancing `buffer.position()`.
- `clear()` only resets state for reusing the buffer, **it does not erase bytes**.
- `compact()` is used when you need to retain unconsumed bytes and write more.

In particular, **`ByteBuffer.get(index)` / `put(index, value)`** are also absolute operations, but they apply to **indices inside the buffer**. They generally do not change `buffer.position()`; do not confuse them with `FileChannel.read(dst, fileOffset)`, which still changes `dst.position()`. Both APIs carry the word "absolute", yet the state they preserve is **different**.

## 9. Edge Cases That Need Explicit Design

### 9.1. Offset At or Beyond EOF

Suppose a file is 10 bytes long; valid offsets for existing bytes are 0–9. `channel.read(dst, 10)` with a buffer that still has space hits EOF and normally returns `-1`. `channel.read(dst, 20)` likewise cannot read bytes from a region without data. **Positional read does not automatically extend the file.**

Be mindful when `dst.remaining()==0`: there is no byte transfer requested. Do not use an empty buffer to detect EOF; check `size()` or attempt reading with a buffer that has remaining space, handling the return value per contract. You should not rely on a fixed return value from a zero-length read call as a way to conclude the file has ended.

### 9.2. Writing Beyond EOF

`channel.write(src, offset)` with an offset larger than the file size can extend the file if bytes are actually written. For example, a 10-byte file having one byte written at offset 20 may cause the new size to become 21. Bytes between the old EOF and the newly written region are **not guaranteed to have a defined value by the `FileChannel` contract**.

If the file format requires empty regions to be initialized with 0 or another value, the program must perform initialization according to design. Merely setting an absolute position without writing bytes **does not extend the file**.

### 9.3. Never Access Negative Offsets

`read(dst, -1)` or `write(src, -1)` violates parameter preconditions and throws `IllegalArgumentException`. Validate offsets and lengths before passing them to the API; pay special attention to additions `startOffset + bytesTransferred` and multiplications `recordIndex * recordSize` to avoid `long` overflow.

When reading an existing record, check that the data is within bounds, for example:

```java
if (offset < 0 || length < 0
        || offset > channel.size()
        || length > channel.size() - offset) {
    throw new IOException("Record outside file");
}
```

This is an illustrative snippet, assuming `offset` and `length` are `long` integers and `channel` is open. The form `length > size - offset` avoids overflow when computing `offset + length`, yet only checks **the state at the time of the call**; another process can still modify the file afterward.

### 9.4. Channel Opened in an Incompatible Mode

`FileChannel.open(path, READ)` does not permit `write`; `FileChannel.open(path, WRITE)` does not permit `read`. The exceptions can be `NonWritableChannelException`/`NonReadableChannelException`.

If the file is opened in `APPEND` mode, the behavior of **positional write** can be system-dependent: the Java specification states that the effect of positional writes when opened for append is implementation-defined. **Avoid combining `APPEND` with positional write when exact offset writes must be guaranteed**; use an appropriate write mode and define an explicit append strategy if business logic requires it.

### 9.5. Read-Only Buffers, Closed Channels, and I/O Errors

Reading bytes into a read-only `ByteBuffer` is invalid and can cause `ReadOnlyBufferException`. A closed channel can cause `ClosedChannelException`; I/O operations can also encounter system errors, locking issues, or thread interruption.

Even if `isOpen()` returns `true`, the channel can be closed before the next operation. Handle errors at the `read` or `write` call itself and close the channel using `try-with-resources`.

## 10. Positional I/O and Concurrent Access

Positional I/O is especially useful when multiple operations need different offset regions without running `channel.position(x)` → `read/write` pairs through a shared channel cursor.

**However, it does not automatically make operations thread-safe or atomic.**

Distinguish clearly:

1. **Channel position is preserved:** each `read(buffer, offset)`/`write(buffer, offset)` call does not modify `channel.position()`.
2. **Buffer is still mutable state:** if multiple threads share **one `ByteBuffer`**, the buffer's position/limit can be altered interleaved.
3. **File contents are still shared:** two writers writing to overlapping regions can race; a reader can observe data changing mid-processing.
4. **Parallelism of file operations is implementation-dependent:** the `FileChannel` contract does not guarantee that all positional I/O runs concurrently or is atomized per record.

When handling multiple threads, each task should have its own buffer and offset range, along with coordination/locking mechanisms when data regions overlap. `FileLock` can assist certain inter-process coordination models, but you must understand lock scope and limits per OS and filesystem; locks also do not replace crash handling, flushing, or file update transactions.

**Why does this matter?** If thread A calls `channel.position(100)` and before it can `read(dst)`, thread B changes position to 200, thread A may read the wrong offset without synchronization. Replacing this with `read(dst, 100)` lets thread A pass the exact offset for its operation. Even so, you must still keep buffers separate and control writers.

## 11. When Should You Use Positional I/O?

Suitable scenarios:

| Scenario | Meaning of absolute offset |
| --- | --- |
| Reading a header while sequentially processing the body | No need to save/restore channel position |
| Reading fixed-length records | Compute `offset = index * recordSize` |
| Updating a binary field at a known offset | Overwrite the exact region to modify |
| Reading multiple distinct segments by an index | Each segment uses an explicit offset |
| Multiple independent tasks processing disjoint file regions | Avoids mutating the file cursor via individual positional I/O calls |

Positional I/O is not always necessary. If an application only reads an entire file sequentially once, `channel.read(buffer)` in a simple loop can be easier to understand. If shared file-pointer-like behavior is needed, `channel.position(...)` remains appropriate when thread access is controlled.

Positional I/O is not necessarily faster. Performance depends on the filesystem, storage device, caches, buffer size, access pattern, concurrency level, and data nature. When optimizing, benchmark against realistic workloads.

## 12. Comparison with `RandomAccessFile.seek` and ByteBuffer Absolute get/put

| API | Whose position is specified | Effect on state |
| --- | --- | --- |
| `RandomAccessFile.seek(offset)` | `RandomAccessFile`'s file pointer | **Changes** the file position used by the next operation |
| `FileChannel.position(offset)` | Channel's current position | **Changes** the file position used by the next operation |
| `FileChannel.read(dst, offset)` | Read call's own file offset | **Preserves** channel position; advances `dst.position()` when bytes are read |
| `FileChannel.write(src, offset)` | Write call's own file offset | **Preserves** channel position; advances `src.position()` when bytes are written |
| `ByteBuffer.get(index)` | Index inside buffer | Usually **preserves** `buffer.position()` |
| `ByteBuffer.put(index, byte)` | Index inside buffer | Usually **preserves** `buffer.position()` |

If a `FileChannel` is obtained via `RandomAccessFile.getChannel()`, the two objects share a relationship regarding file position. Positional I/O does not change that file position, yet calling `seek` or `position(long)` on one side can affect the position observed from the other side. Avoid mixing these APIs and assuming they have two independent file cursors.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `read(dst, offset)` updates `channel.position()` | Subsequent sequential read still starts at the old offset | Understand both `read` forms; use `position(long)` only when genuinely wanting to move channel position |
| Thinking positional I/O changes **no** position at all | Buffer position still changes; data processed incorrectly | Inspect `channel.position()` and `buffer.position()` separately |
| Looping `read(dst, sameOffset)` after a partial read | Duplicate data is read from the same offset | Accumulate `bytesRead` into the offset each time |
| Looping `write(src, sameOffset)` on partial write | Later bytes overwrite earlier bytes | Use `startOffset + bytesWritten` |
| Not `flip`ping the buffer after `put`ting before writing to channel | Wrong buffer region written | `flip()` before the consumption phase |
| Assuming a single `read/write` always transfers all remaining | Incomplete read/write | Loop checking progress, EOF, and I/O conditions |
| Using record index as the offset argument | Wrong bytes accessed | Multiply `index * recordSize` using `long` arithmetic |
| Writing at an offset past EOF and thinking the gap is auto-zeroed | Intermediate data has no guaranteed value | Initialize bytes according to format |
| Using `APPEND` with positional write to guarantee offsets | Implementation-dependent behavior | Open channel with appropriate read/write options, avoiding APPEND |
| Sharing one `ByteBuffer` across multiple threads | Prone to races on buffer position/limit | Each task uses its own buffer or synchronizes |
| Believing positional write is an atomic transaction | Can encounter partial writes or overlapping data | Design writer coordination, recovery, and consistency |

## 14. Self-Check Exercise

Suppose a file has 10 bytes, `channel.position()==7`, and `ByteBuffer dst` has `capacity=6`, `position=1`, `limit=5`. The program calls:

```java
int n = channel.read(dst, 2);
```

If the call returns `n==3`, what outcomes can be concluded with certainty?

- **Channel position** remains **7**.
- **Buffer position** increases from **1** to **4**.
- **Buffer limit** remains **5**, capacity remains 6.
- The three requested bytes start from file offset **2** and are placed into the buffer starting at index **1**.
- `dst.remaining()` is now `5 - 4 = 1`.

If you want to read one more contiguous byte from the file into the buffer, the next read's offset must be **`2 + 3 = 5`**. Calling `read(dst, 2)` again will go back to offset 2, even though the buffer position is now 4.

This is the crucial difference between **a fixed input file offset** and **ByteBuffer's auto-advancing position**.

## 15. Takeaways

1. **`FileChannel.read(dst, offset)` and `write(src, offset)` operate at an absolute byte offset without changing `FileChannel.position()`.**
2. **`ByteBuffer.position()` still moves** by the number of bytes successfully read/written. Data must have `position/limit` prepared properly.
3. Positional I/O may transfer only **part** of the buffer; to complete the whole transfer, loop with **`offset + total bytes transferred`**, handling EOF and zero-progress errors.
4. Positional write can change file size, and using positional I/O does not automatically provide consistency or atomicity.
5. Watch channel open permissions, non-negative offsets, integer overflow, EOF, APPEND, and concurrent access.
6. When you want to **change the channel's current position**, use `position(long)`; when you want to **access an offset while preserving channel position**, use the overloads taking a `long position` parameter.

**References:** Java SE 17 API — `java.nio.channels.FileChannel`, `java.nio.ByteBuffer`, `java.nio.file.StandardOpenOption`, and `java.io.RandomAccessFile`.
