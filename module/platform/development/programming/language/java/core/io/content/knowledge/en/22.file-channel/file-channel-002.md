# FileChannel: Reading and Writing at Current Position in Java NIO

## 1. Nature of the Current File Position

`java.nio.channels.FileChannel` is the file read/write channel in Java NIO. Each channel object has a **current file position** of type `long`, measured in **bytes** from the beginning of the file. Two important methods:

- `position()`: returns the current offset.
- `position(long newPosition)`: sets the offset for subsequent relative I/O operations.

When calling `read(ByteBuffer)` or `write(ByteBuffer)` **without passing an offset**, the channel processes bytes starting from the current position, then advances by the **actual number of bytes** read/written. This is **reading and writing at the current position**.

In contrast, `read(ByteBuffer, long position)` and `write(ByteBuffer, long position)` operate at the specified offset **without changing the current file position**. Both mechanisms allow random access; they differ in whether they use and advance the channel's shared cursor.

**Goals:** know how to open a channel with the right permissions, control the position, implement read/write loops for all bytes, distinguish between the channel's position and `ByteBuffer`'s position, detect EOF, overwrite in the middle of a file, re-read from the beginning, and avoid contention when multiple threads use the same channel.

## 2. Visualizing the File and the Cursor

Suppose a file has six ASCII bytes `ABCDEF`:

```text
Byte offset: 0 1 2 3 4 5 6
Content:     A B C D E F |EOF|
             ^
           position=0
```

After `read(dst)` successfully reads 2 bytes from offset 0:

```text
Byte offset: 0 1 2 3 4 5 6
Content:     A B C D E F |EOF|
                 ^
               position=2
```

If position is 2, `write(ByteBuffer.wrap(new byte[]{'X','Y'}))` (writing both bytes) replaces `CD` with `XY`, producing `ABXYEF`, and position advances to 4. Writing in the middle of a file is an **overwrite**, not an automatic insertion that shifts trailing bytes.

Characteristics to remember:

1. Position is a **byte offset**, not a character index in a UTF-8 string.
2. `size()` returns the file length; `position()` is where the next relative I/O starts. They can differ.
3. `position(newPosition)` does not itself read, write, truncate, or extend the file.
4. Setting the position past the file size is allowed. Reading where no bytes exist hits EOF; writing may extend the file and create a gap depending on the filesystem/provider.
5. **Separately** opened `FileChannel` instances on the same file have independent position cursors, even though the file data is shared.
6. Multiple components using the **same FileChannel instance** share that object's current position.

## 3. Opening FileChannel for the Right Purpose

Java 17+ typically uses `FileChannel.open(Path, OpenOption...)` combined with try-with-resources:

```java
import java.nio.channels.FileChannel;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

Path path = Path.of("data.bin");

try (FileChannel channel = FileChannel.open(
        path,
        StandardOpenOption.CREATE,
        StandardOpenOption.READ,
        StandardOpenOption.WRITE)) {
    // channel.position(), channel.read(...), channel.write(...)
}
```

This is an **illustrative snippet**, not a standalone program.

| OpenOption | Effect |
|---|---|
| `READ` | Allows reading the file |
| `WRITE` | Allows writing the file |
| `CREATE` | Creates the file if it does not exist when opened for writing |
| `CREATE_NEW` | Creates a new file, failing if the path already exists |
| `TRUNCATE_EXISTING` | If opened for writing, truncates existing file content to empty |
| `APPEND` | Write operations follow append-to-end semantics; not for modifying arbitrary offsets |

Opening for reading only:

```java
try (FileChannel channel =
             FileChannel.open(path, StandardOpenOption.READ)) {
    // Read-only.
}
```

Do not add `TRUNCATE_EXISTING` if the goal is to modify a file that already holds data. With `APPEND`, do not combine it with `READ`: an invalid combination may throw `IllegalArgumentException`. To read and write at arbitrary offsets, choose `READ` + `WRITE` instead of `APPEND`.

When opening a channel normally, the initial position is 0. In situations requiring clarity, call `channel.position(0L)` to establish the starting point. Always close the channel with try-with-resources.

Besides `FileChannel.open`, a channel can be obtained from `RandomAccessFile.getChannel()`. When doing so, **`RandomAccessFile` and its associated channel share the file position**: `raf.seek(...)` affects `channel.position()` and vice versa. Avoid mixing the two APIs arbitrarily on the same object.

## 4. Distinguishing Two Kinds of Position

`FileChannel.position()` and `ByteBuffer.position()` are **not the same variable**:

| Object | What `position()` represents | Unit |
|---|---|---|
| FileChannel | Offset of the next relative I/O operation in the **file** | File bytes |
| ByteBuffer | Next read/write index in the **buffer memory** | Buffer bytes |

Suppose channel position=100, buffer position=3, and remaining=5. If `channel.read(buffer)` successfully reads 4 bytes:

- Channel position changes from 100 to **104**.
- Buffer position changes from 3 to **7**.
- The four bytes from the file are placed in the buffer at indices 3, 4, 5, and 6.

A relative I/O call can advance **both positions by the same amount**, but calling `buffer.flip()`, `buffer.clear()`, or `buffer.rewind()` **does not move the channel's position**. Likewise, `channel.position(0)` does not change the buffer's position.

Buffer state lifecycle:

| Method | Meaning |
|---|---|
| `put(...)` | Puts bytes into the buffer and advances buffer position |
| `flip()` | Sets limit = old position, position = 0; prepares to read the newly written bytes |
| `clear()` | Sets position = 0 and limit = capacity; **does not erase memory contents** |
| `rewind()` | Resets buffer position to 0, keeping limit |
| `remaining()` | Number of bytes still readable/writable in the buffer (`limit - position`) |
| `hasRemaining()` | Checks whether unprocessed bytes remain |

A common mistake is calling `write(buffer)` right after `put` into the buffer while **forgetting `flip()`**, leaving the buffer at the end of the data or writing an unintended region.

## 5. Reading at Current Position: `read(ByteBuffer)`

Signature:

```java
int bytesRead = channel.read(destination);
```

Workflow:

1. Starts at `channel.position()`.
2. Reads bytes from the file into `destination` starting at `destination.position()`.
3. Processes at most `destination.remaining()` bytes in a single call.
4. Returns the **actual** number of bytes read, which may be fewer than remaining or 0; if EOF has been reached and no bytes could be read, returns `-1`.
5. When `n > 0`, both channel position and destination position increase by `n`.

Illustrative example (assuming the channel is open for reading):

```java
ByteBuffer buffer = ByteBuffer.allocate(8);
int n = channel.read(buffer);
if (n > 0) {
    buffer.flip();
    while (buffer.hasRemaining()) {
        byte b = buffer.get();
        // Process byte b.
    }
}
```

**A single `read` call is not guaranteed to fill the buffer.** If the format requires reading exact N bytes, use a loop that checks the received byte count and detects EOF before reaching N bytes:

```java
static void readFully(FileChannel channel, ByteBuffer destination)
        throws IOException {
    while (destination.hasRemaining()) {
        int n = channel.read(destination);
        if (n == -1) {
            throw new EOFException("Tệp kết thúc trước số byte yêu cầu");
        }
        if (n == 0) {
            throw new IOException("Lần đọc không tiến thêm byte");
        }
    }
}
```

This is an **illustrative method**, requiring imports for `java.io.EOFException`, `java.io.IOException`, `java.nio.ByteBuffer`, and `java.nio.channels.FileChannel`. The example's error policy on `n == 0` prevents an infinite loop. Applications with special providers may choose bounded retries and other liveness management. You still must handle cases where the file is truncated or data is modified by another process during reading.

If you want to read all the way to EOF (without knowing the size beforehand), you typically use a `read` loop, processing each chunk after `flip` and preparing the buffer again. Stop when `read` returns `-1`; do not treat buffer capacity as the valid byte count.

## 6. Writing at Current Position: `write(ByteBuffer)`

Signature:

```java
int bytesWritten = channel.write(source);
```

When `n > 0` bytes are actually written:

- Bytes are written to the file at the current position, potentially overwriting existing bytes.
- Channel position increases by `n`.
- `source.position()` increases by `n` because `write` consumed bytes from the buffer.
- File size may grow if the write extends past the old EOF.

Example sending three ASCII bytes (illustrative snippet; channel must have write access):

```java
ByteBuffer source = ByteBuffer.wrap(new byte[]{'A', 'B', 'C'});
while (source.hasRemaining()) {
    int n = channel.write(source);
    if (n == 0) {
        throw new IOException("Lần ghi không tiến thêm byte");
    }
}
```

When the loop finishes successfully, the buffer has no remaining bytes; channel position has advanced by exactly 3 bytes from the start. Do not rely on the assumption that a single `write(source)` always writes the entire content.

Pattern for writing multiple primitives:

```java
ByteBuffer record = ByteBuffer.allocate(Integer.BYTES + Long.BYTES);
record.putInt(2026);
record.putLong(1000L);
record.flip();
while (record.hasRemaining()) {
    channel.write(record);
}
```

Here the buffer holds 12 bytes (4 + 8). If the file format requires little-endian, set `record.order(ByteOrder.LITTLE_ENDIAN)` **before** putting values and use the same byte order when decoding. Channel offsets are still measured in bytes, not in counts of `int`/`long` values.

## 7. Complete Java 17+ Example

The program creates a temporary file, writes `ABCDEF`, seeks back to the beginning and reads two bytes, reads the single byte at offset 4 using positional I/O, and then overwrites `CD` with `XY` starting from **current position=2**.

Save as **`FileChannelPositionDemo.java`**:

```java
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FileChannelPositionDemo {

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("file-channel-position-", ".bin");

        try {
            try (FileChannel channel = FileChannel.open(
                    file,
                    StandardOpenOption.READ,
                    StandardOpenOption.WRITE,
                    StandardOpenOption.TRUNCATE_EXISTING)) {

                ByteBuffer initial = ByteBuffer.wrap(
                        "ABCDEF".getBytes(StandardCharsets.US_ASCII));

                writeFully(channel, initial);
                System.out.println("After write: position="
                        + channel.position() + ", size=" + channel.size());

                channel.position(0);
                ByteBuffer firstTwo = ByteBuffer.allocate(2);
                readFully(channel, firstTwo);
                firstTwo.flip();
                System.out.println("Read: "
                        + StandardCharsets.US_ASCII.decode(firstTwo)
                        + ", position=" + channel.position());

                ByteBuffer atFour = ByteBuffer.allocate(1);
                readFullyAt(channel, atFour, 4L);
                atFour.flip();
                System.out.println("Absolute read: "
                        + StandardCharsets.US_ASCII.decode(atFour)
                        + ", position=" + channel.position());

                ByteBuffer change = ByteBuffer.wrap(
                        "XY".getBytes(StandardCharsets.US_ASCII));
                writeFully(channel, change);
                System.out.println("After overwrite: position="
                        + channel.position());

                channel.position(0);
                ByteBuffer whole = ByteBuffer.allocate(6);
                readFully(channel, whole);
                whole.flip();
                System.out.println("Final: "
                        + StandardCharsets.US_ASCII.decode(whole)
                        + ", position=" + channel.position());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }

    // Relative I/O: channel position and buffer position advance together.
    private static void readFully(FileChannel channel, ByteBuffer target)
            throws IOException {
        while (target.hasRemaining()) {
            int n = channel.read(target);
            if (n < 0) {
                throw new EOFException("Not enough bytes");
            }
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
        }
    }

    private static void writeFully(FileChannel channel, ByteBuffer source)
            throws IOException {
        while (source.hasRemaining()) {
            int n = channel.write(source);
            if (n == 0) {
                throw new IOException("Write made no progress");
            }
        }
    }

    // Positional I/O does not change channel.position().
    private static void readFullyAt(
            FileChannel channel, ByteBuffer target, long offset)
            throws IOException {
        long position = offset;
        while (target.hasRemaining()) {
            int n = channel.read(target, position);
            if (n < 0) {
                throw new EOFException("Not enough bytes at offset " + offset);
            }
            if (n == 0) {
                throw new IOException("Positional read made no progress");
            }
            position += n;
        }
    }
}
```

Compile and run in the directory containing the source code:

```bash
javac FileChannelPositionDemo.java
java FileChannelPositionDemo
```

**Exact stdout when having permissions to create/read/write/delete temporary files:**

```text
After write: position=6, size=6
Read: AB, position=2
Absolute read: E, position=2
After overwrite: position=4
Final: ABXYEF, position=6
```

Step by step:

1. Writes six bytes starting at position 0, so `channel.position() == 6` and `size() == 6`.
2. `position(0)` moves the cursor to the beginning without losing data. Reading `AB` advances the cursor to 2.
3. `readFullyAt(...,4L)` reads byte `E`, **keeping channel position=2**.
4. Writes `XY` with relative write from position 2, replacing the two bytes `CD`, resulting in position=4.
5. Moves to 0 and reads six bytes yielding `ABXYEF`; after reading, position=6.

The example uses full loops because `read/write` can return fewer bytes than the buffer size. The positional helper increments the local `position` variable after each iteration so that if a read is fragmented it still fetches the subsequent bytes, rather than repeatedly reading the same offset.

## 8. Relative and Positional I/O: Differences in Position

```java
int n1 = channel.read(dst);         // Uses current position.
int n2 = channel.read(dst, 128L);   // Reads from offset 128.

int n3 = channel.write(src);        // Uses current position.
int n4 = channel.write(src, 256L);  // Writes from offset 256.
```

This is an illustrative snippet; assumes variables are declared and the channel has corresponding permissions.

| Method, with n bytes succeeded | Starting point in file | FileChannel.position after call | ByteBuffer.position after call |
|---|---|---|---|
| `read(dst)` | Current position before call | Increases by n | Increases by n |
| `write(src)` | Current position before call | Increases by n | Increases by n |
| `read(dst, offset)` | Passed-in offset | **Unchanged** | Increases by n |
| `write(src, offset)` | Passed-in offset | **Unchanged** | Increases by n |
| `position(offset)` | No I/O | Set to offset | Unchanged |

With positional read/write, **the buffer still advances its position**, even though the channel does not. This is a common confusion when reusing one buffer across multiple offsets.

If an application is scanning a file using relative reads but needs to update a header at offset 0, positional write can be suitable to avoid losing the scan cursor. You still need to handle overwriting the file structure, permissions, and data length properly.

## 9. EOF, Short I/O, and Actual Byte Counts

### EOF When Reading

When the file position is already at the end of the file and the buffer still has capacity, `read(buffer)` typically returns `-1`. It **does not automatically rewind position to the beginning**. To read again, you must call `channel.position(0)` and prepare the buffer state properly.

If `read` returns `0`, do not jump to treating it as EOF: it means "no bytes transferred in that call", which can happen when the buffer has no remaining space or in provider-specific situations. When `remaining()==0`, there is no need to call read.

### Short Read / Short Write

For example, needing to read 4096 bytes but receiving only 1024 on the first pass. That is **not necessarily an error**. The method continues while the buffer has remaining space, using the automatically advanced position. Similarly when writing: `write` returns the actual bytes written, so always check `hasRemaining()` if the protocol requires the full block.

With positional I/O, you must update the offset yourself:

```java
long offset = 1000L;
while (buffer.hasRemaining()) {
    int n = channel.read(buffer, offset);
    if (n == -1) {
        throw new EOFException("Unexpected EOF");
    }
    if (n == 0) {
        throw new IOException("No progress");
    }
    offset += n;  // Required: current file position does not auto-advance.
}
```

This is an illustrative snippet, requiring the buffer to be prepared with the proper remaining space. **Do not** keep using offset 1000 for every iteration; doing so would repeat the start of the segment when the first read only processes part of it.

## 10. Overwriting, Appending, and Resizing

### Overwriting in the Middle of a File

If the file is `ABCDE`, calling `channel.position(1)` and writing both bytes of `XY`:

```text
Before: A B C D E
Offset  0 1 2 3 4

After:  A X Y D E
              ^
         position = 3
```

The size remains 5. `FileChannel.write` does not automatically insert two bytes and shift `BCDE` to the right. When the format requires true insertion, the application must move/rewrite the tail itself.

### Writing at the End

In a simple single-writer scenario:

```java
channel.position(channel.size());
ByteBuffer tail = ByteBuffer.wrap(new byte[]{'F', 'G'});
while (tail.hasRemaining()) {
    channel.write(tail);
}
```

This snippet does not guarantee **atomic append** against other writers because `size()`, `position(...)`, and `write(...)` are separate operations. If append semantics are needed, consider opening the channel with `StandardOpenOption.APPEND` and environment constraints; APPEND is not suitable for editing at arbitrary offsets and cannot be combined with READ.

### Position Beyond EOF

Suppose size=10; `channel.position(100)` is valid and **does not** make size equal to 100. Reading from there may return `-1`; writing at that position can lengthen the file, creating a gap from the old EOF to the newly written region. The content of the gap depends on the system and should not be relied upon as application-initialized data.

### `truncate`, `size`, and `force`

- `size()`: gets the current byte count without changing position.
- `truncate(newSize)`: trims the tail if the old size is greater than newSize; if the current position is greater than newSize, position is reduced to newSize. If the old size is already less than newSize, `truncate` **does not expand** the file.
- `force(metaData)`: requests syncing file content (and metadata if `true`) to the storage system per API semantics; it does not change position and does not automatically turn multiple updates into an atomic transaction.

```java
channel.position(18);
channel.truncate(10);
// When the file before truncate was larger than 10:
// channel.position() becomes 10 if it was previously 18.
```

This snippet is illustrative; the channel needs write permission and the filesystem must permit the operation.

## 11. Thread Safety When Sharing One Channel

A `FileChannel` has a single shared current position among components holding the **same instance**. For example, two tasks:

```text
Task A: channel.position(100)
Task B: channel.position(500)
Task A: channel.read(bufferA)  ← may read from offset 500.
```

Even though I/O operations on FileChannel have internal coordination rules, an application's **multi-call sequence** of `position(offset)` followed by `read/write(buffer)` is **not automatically atomic** with respect to other threads.

Solutions depend on the requirement:

- Have only **one owner** perform sequential relative I/O operations.
- Lock the entire `position + read/write` group when forced to share the same channel.
- Use `read(buffer, offset)` / `write(buffer, offset)` for tasks with their own offsets, so they do not contend over current position.
- Open separate channels if the architecture fits; each channel has its own position, though they still share the file and do not prevent overlapping writes or concurrent truncation.

Even positional I/O needs synchronization when tasks modify the same region, change file length, or read data that must stay consistent across multiple steps. Using explicit offsets reduces cursor hazards; it does not replace concurrency design.

## 12. Common Mistakes

1. **Forgetting to move the channel back to the start before re-reading.** After writing, current position is usually at the end; call `position(0)` when reading from the start.
2. **Assuming read/write always processes the whole buffer.** Check the return value, `hasRemaining()`, and loop when needed.
3. **Not handling EOF.** `-1` is different from `0`; for fixed records, missing bytes is an explicit error or recovery condition.
4. **Forgetting `flip()` before sending a newly populated buffer to the channel.** Wrong buffer position/limit leads to writing the wrong number of bytes.
5. **Calling `clear()` and thinking old data was erased.** `clear()` only changes buffer state.
6. **Confusing channel position with buffer position.** They are independent even though one relative I/O call can advance both.
7. **Confusing the two read/write overloads.** The overload with offset does not change current position, yet still advances buffer position.
8. **Using a fixed offset when looping positional read/write.** You must add the processed byte count to the offset.
9. **Thinking writing in the middle of a file inserts.** It overwrites existing bytes.
10. **Confusing position and size.** `position(size)` cannot guarantee atomic append against other writers.
11. **Thinking `truncate` can extend a file.** It only trims if the old size is larger than the argument.
12. **Opening with `TRUNCATE_EXISTING` when intending to keep data.** This open mode can empty the file.
13. **Using APPEND when random overwrite is needed.** Append has its own semantics and is unsuitable for setting arbitrary write offsets.
14. **Treating offset as UTF-8 character index.** Offsets are measured in bytes; one character can span multiple bytes.
15. **Letting multiple threads call `position + read/write` on the same channel.** The pair of calls is not atomic; use a single owner, locking, or positional I/O.
16. **Forgetting to close the channel.** Use try-with-resources and handle `IOException` and `ClosedChannelException` as appropriate.

## 13. Applicable Scenarios

**Reading a log file sequentially:** relative `read(buffer)` fits well because each read advances past the processed part. Prepare the buffer properly and parse record boundaries/charsets separately.

**Writing header and payload in sequence:** write the full header buffer then the payload buffer with relative `write`. Position advances automatically by the exact actual bytes written; no manual offset addition is needed if appending sequentially in a single writer.

**Editing a header while reading payload:** use positional `write(src, headerOffset)` to avoid disturbing the payload read cursor. Still manage format consistency if reads and writes interleave.

**Reading multiple file pages at independent offsets:** positional I/O gives each task an explicit offset, avoiding `position + read` on a shared cursor; watch out for advancing the offset on short reads.

**Creating fixed-size record files:** you can use `channel.position(headerSize + index * recordSize)` followed by relative `read/write` in single-owner logic. If multiple tasks access records concurrently, positional I/O usually makes offset relationships clearer. Compute offsets with `long` and guard against overflow when indices come from untrusted input.

## 14. Self-Check Questions

**1.** A file is 10 bytes long, channel position=3, buffer has room for 4 bytes. If relative `read` actually reads all 4 bytes, what is the new position?  
**Answer:** 7; buffer position also increases by 4 compared to before the call.

**2.** Afterward `channel.read(dst, 1L)` reads 2 bytes. Does the channel's current position change?  
**Answer:** No. Still 7. Only buffer position increases by 2.

**3.** File `ABCDE`, position=1, relative write of all of `XY`. What is the result?  
**Answer:** `AXYDE`, position=3, size remains 5.

**4.** Does `buffer.flip()` reset the current file position to 0?  
**Answer:** No. It only switches the buffer's mode. To move the channel to 0, call `channel.position(0L)`.

**5.** After writing to the end and `read(dst)` returns `-1`, does `dst.capacity()` tell you how many bytes were successfully read?  
**Answer:** No. Buffer capacity is not the count of valid data bytes. You must rely on the return value and before/after position/limit.

**6.** Why shouldn't two threads independently call `position(offset)` then `read(buffer)` on the same channel?  
**Answer:** Another thread can change position between the two calls; the sequence is not atomic. Use positional read or proper synchronization.

## 15. Summary

- **`FileChannel.read(ByteBuffer)` / `write(ByteBuffer)` read and write at the current position and advance the cursor by the actual bytes processed.**
- **`position(long)` only moves where the next operation starts; `size()` is the file size.**
- **FileChannel and ByteBuffer have separate positions.** `flip/clear` affect the buffer, not the file cursor.
- **`read/write(buffer, offset)` do not change channel position** but still advance buffer position by the processed byte count.
- **Short I/O and EOF must be handled explicitly**; exact-length read/write loops are the foundation of reliable binary processing.
- **Avoid shared-cursor contention under multithreading** via a single-owner model, proper synchronization, or positional I/O.

### References

- Java SE 17 `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `StandardOpenOption`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
