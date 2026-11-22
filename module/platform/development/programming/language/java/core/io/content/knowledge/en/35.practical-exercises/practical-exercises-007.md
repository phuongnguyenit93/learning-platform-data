# Comparing `RandomAccessFile` vs. `FileChannel` on Fixed-Length Records

## 1. Practice Problem and Goals

Suppose a Java program stores many account records in a binary file. Every record is exactly **16 bytes**, so we immediately know the position of record `i` without reading all preceding records. The program needs to:

- Create a file containing several records using the same layout.
- Read any record by index.
- Modify a value inside a record without rewriting the entire file.
- Detect invalid indices, EOF, and a trailing record missing bytes.
- Compare two approaches: **`RandomAccessFile`** and **`FileChannel`** with **`ByteBuffer`**.
- Understand the difference between `RandomAccessFile`'s **file pointer**, a channel's **position**, and a buffer's **position/limit**.
- Refrain from guessing which option is faster without measuring on a real workload.

**Conclusion before writing code:** both APIs can perform random access on fixed-length records. `RandomAccessFile` is convenient with primitive read/write methods and `seek()`; `FileChannel` is convenient with positional read/write and NIO operations. **Reading the exact same 16 bytes at the exact same offset** is the prerequisite for a valid comparison.

This lesson uses **Java 17+** and Java SE only. Standalone runnable examples include their corresponding filenames/classes, `javac`/`java` commands, and stdout independent of temporary file paths.

## 2. What Is a Fixed-Length Record?

A **fixed-length record** is a record whose byte count and field order are defined in advance; every record of the same format version has the same length.

In this exercise, one record consists of:

| Offset in record | Field | Binary type | Byte count |
| --- | --- | --- | --- |
| 0–3 | `id` | signed 32-bit `int` | 4 |
| 4–11 | `balance` | signed 64-bit `long` | 8 |
| 12–15 | `status` | signed 32-bit `int` | 4 |
| **Total** | | | **16 bytes** |

Both write approaches use **big-endian**: the most significant byte comes first. `RandomAccessFile.writeInt/writeLong` use big-endian per the `DataOutput` contract; `ByteBuffer` defaults to `BIG_ENDIAN`, though setting it explicitly prevents bugs if code is refactored later.

For example, a record with `id=1002`, `balance=7250`, `status=1` has these byte groups:

```text
Offset:     0          4                     12
            |          |                      |
Field:      id:int     balance:long           status:int
Bytes:      00 00 03 EA  00 00 00 00 00 00 1C 52  00 00 00 01
Size:       < 4 bytes > <      8 bytes      > < 4 bytes >
```

Because `1002 = 0x000003EA` and `7250 = 0x0000000000001C52`, both APIs must interpret the exact same bytes when using the same layout and byte order.

**Not Java object serialization:** a fixed-record file stores application-defined bytes. It does not use `ObjectOutputStream`, carries no class descriptors, and does not automatically reconstruct object graphs. The program itself is responsible for schema and version compatibility.

## 3. Offset Calculation Formula

Let:

- `R`: bytes per record (here `R=16`).
- `i`: **0-based** record index.
- `base`: starting position of the data region, equal to 0 when the file has no header.
- `offset`: byte position of the record's first byte in the file.

Formula:

\[
\text{offset}(i)=\text{base}+i\times R
\]

With `base=0`:

| Record index | Byte offset | Record byte range |
| --- | --- | --- |
| 0 | 0 | 0–15 |
| 1 | 16 | 16–31 |
| 2 | 32 | 32–47 |
| 3 | 48 | 48–63 |

A file with three records must be exactly `3 × 16 = 48` bytes long. If the file is 50 bytes long, the last two bytes do not form a valid record; that is a **partial/truncated/corrupt record**, not a fourth record.

### Avoiding Overflow When Computing Offsets

Do not write:

```java
long offset = index * RECORD_BYTES;
```

if both `index` and `RECORD_BYTES` are `int`: multiplication occurs in `int` **before widening to `long`**, so it can overflow. You must also check for negative indices and `long` multiplication overflow.

Use:

```java
static long offsetOf(long index, int recordBytes) {
    if (index < 0 || recordBytes <= 0) {
        throw new IllegalArgumentException("Invalid index/size");
    }
    return Math.multiplyExact(index, (long) recordBytes);
}
```

This is an **illustrative helper**; `Math.multiplyExact` throws `ArithmeticException` if the product does not fit in `long`. For files with a header, add `base` using `Math.addExact(base, product)`.

The offset formula is valid only if **every record truly occupies exactly R bytes**. It cannot be applied directly if you insert variable-length UTF-8 strings, arbitrary metadata, or variable markers between records.

## 4. `RandomAccessFile`: A Single Read/Write Pointer

`java.io.RandomAccessFile` provides an API for reading/writing data at arbitrary file positions. Core methods include:

```java
RandomAccessFile file = new RandomAccessFile(path.toFile(), "rw");
file.seek(byteOffset);
long position = file.getFilePointer();
int id = file.readInt();
long amount = file.readLong();
file.writeInt(newStatus);
long size = file.length();
```

This is an illustrative snippet: `path` and `byteOffset` must be declared, `IOException` handled, and the resource closed.

**`seek(long pos)`** sets the file pointer to an **absolute byte offset from the start of the file**, not a record index. Subsequent read/write methods continue from the current file pointer:

- `readInt()` reads exactly 4 bytes, returns an `int`, and advances the file pointer by 4.
- `readLong()` reads exactly 8 bytes, returns a `long`, and advances the file pointer by 8.
- `writeInt(x)` writes 4 bytes and advances the file pointer by 4.
- `writeLong(x)` writes 8 bytes and advances the file pointer by 8.
- `readFully(byte[])` attempts to fill the entire array, throwing `EOFException` if EOF occurs beforehand.
- `length()` retrieves the file size in bytes.
- `setLength(newLength)` changes the file length, requiring attention to truncation/extension.

Example reading record `i=1`:

```java
file.seek(1L * 16);
int id = file.readInt();       // Pointer: 20
long balance = file.readLong();// Pointer: 28
int status = file.readInt();   // Pointer: 32
```

**The file pointer has changed.** If another method calls `file.readInt()` right afterward without calling `seek`, it reads from offset 32—the start of the next record—not back at offset 16.

The strength is concise primitive reading code. What requires management is the **shared read/write position state inside a single `RandomAccessFile`**.

### Open Modes

| Mode | Meaning |
| --- | --- |
| `"r"` | Read-only, writes disallowed |
| `"rw"` | Read and write |
| `"rws"` | Read/write, requiring data and metadata synchronization per contract |
| `"rwd"` | Read/write, requiring file content synchronization per contract, differing from `"rws"` regarding metadata |

Higher-sync modes can significantly alter write cost; **do not benchmark `"rws"` head-to-head against a `FileChannel` without `force`**, because those are unequal data durability guarantees.

## 5. `FileChannel`: Positional Read/Write with `ByteBuffer`

`java.nio.channels.FileChannel` can also read/write at arbitrary offsets:

```java
int read(ByteBuffer dst, long position) throws IOException;
int write(ByteBuffer src, long position) throws IOException;
```

These two overloads have key properties:

1. `position` is an **absolute byte offset** in the file, not a record index.
2. `read(dst, position)` does not alter `channel.position()`.
3. `write(src, position)` does not alter `channel.position()`.
4. **`ByteBuffer.position()` still advances** by the actual number of bytes read/written.
5. A single call can return **fewer bytes than requested**; you must loop until full or EOF/error.
6. `FileChannel` allows length management via `size()`/`truncate(...)` and other NIO operations.

Conceptual example:

```java
ByteBuffer buffer = ByteBuffer.allocate(16);
buffer.order(ByteOrder.BIG_ENDIAN);

long offset = 1L * 16;
int received = channel.read(buffer, offset);

// channel.position() stays unchanged;
// buffer.position() may advance by the received byte count.
```

This snippet is illustrative only, not a standalone program; `channel` must be opened and `received` checked. Never call `buffer.getInt()` immediately while the buffer is still in write-into-buffer state after `read` without `flip()` or proper position management.

### Buffer Position vs. Channel Position

| Aspect | `RandomAccessFile` | `FileChannel` positional overload |
| --- | --- | --- |
| I/O position | `getFilePointer()`; changes via `seek/read/write` | Offset passed directly in each call |
| Internal position | File pointer moves | `channel.position()` **does not change** when using offset overloads |
| Intermediate buffer | Primitive methods available | `ByteBuffer` with `position/limit/capacity` |
| Reading primitives | `readInt()/readLong()` advance pointer automatically | `ByteBuffer.getInt()/getLong()` advance buffer position |
| Partial read | `readInt`/`readLong` demand full bytes or throw `EOFException` | `read(ByteBuffer,offset)` may return fewer bytes; application loops |
| Byte order | `DataInput/DataOutput` primitives are big-endian | Explicitly configure `buffer.order(...)` |

**Common misconception:** hearing "positional I/O does not change position" and assuming `ByteBuffer.position()` doesn't change either. In reality, only the **`FileChannel`**'s internal position stays unchanged; the buffer is still filled/consumed.

## 6. `ByteBuffer` Lifecycle: `clear`, `flip`, `get`/`put`

To encode a 16-byte record:

```java
ByteBuffer bytes = ByteBuffer.allocate(16);
bytes.order(ByteOrder.BIG_ENDIAN);
bytes.putInt(1002);
bytes.putLong(7250L);
bytes.putInt(1);
bytes.flip();
```

Before `flip()`, the buffer has:

```text
position = 16
limit    = 16
capacity = 16
```

After `flip()`:

```text
position = 0
limit    = 16
capacity = 16
```

Now `channel.write(bytes, offset)` reads data from `[position, limit)`. After each write, `bytes.position` increases accordingly. To send any remaining bytes, **do not call `clear()`**, because `clear` can cause the program to resend stale or out-of-range bytes.

When reading:

```java
ByteBuffer bytes = ByteBuffer.allocate(16);
bytes.order(ByteOrder.BIG_ENDIAN);

// Loop channel.read(bytes, ...) until the buffer is full.
bytes.flip();
int id = bytes.getInt();
long balance = bytes.getLong();
int status = bytes.getInt();
```

This snippet is not standalone because the read loop, error handling, and `channel` are omitted. Calling `flip()` after receiving all 16 bytes prepares for the `get` methods. The three `get` calls consume exactly 4+8+4=16 bytes.

`ByteBuffer.clear()` **does not physically zero bytes** in the backing array; it only resets `position`/`limit`. If a buffer is reused for sensitive data, implement an explicit zeroing policy rather than treating `clear` as a security wipe.

## 7. Direct Comparison Table

| Criterion | `RandomAccessFile` | `FileChannel` |
| --- | --- | --- |
| Package | `java.io` | `java.nio.channels` |
| Opening file | `new RandomAccessFile(file, "r"/"rw")` | `FileChannel.open(path, StandardOpenOption...)` |
| Offset access | `seek(offset)` | `read/write(buffer, offset)` |
| I/O advances object position | Yes, after `seek/read/write` | Positional overload **leaves `channel.position` unchanged** |
| Reading/writing integers | `readInt/readLong/writeInt/writeLong` | `ByteBuffer.putInt/getInt` and `putLong/getLong` |
| Big-endian | Fixed for `DataInput/Output` primitives | Configured on buffer, defaults to BIG_ENDIAN |
| Code volume for small records | Usually less | More buffer operations and partial I/O loops |
| Buffer reuse/direct buffers | Not the API's primary model | Can reuse heap/direct `ByteBuffer` |
| Positional access across tasks | Must manage file pointer and synchronize if shared | Offset overload avoids shared position; data synchronization still needed |
| Length management | `length/setLength` | `size/truncate` |
| File locks, transfer, mapping | Has `getChannel()` for NIO | Provides NIO methods directly |
| Whole record updated atomically? | Not guaranteed | Not guaranteed |
| Absolute performance | Workload-dependent | Workload-dependent |

**Not two separate worlds:** `RandomAccessFile.getChannel()` returns a `FileChannel` linked to the exact same file. Per the API contract, `RandomAccessFile`'s file pointer and **the position of the channel returned by `getChannel()` are coupled**. Therefore, mixing `raf.seek`, `raf.readInt`, and **non-positional** channel methods means an operation on one side changes the position seen by the next operation on the other side.

The `channel.read(buffer, absoluteOffset)` overload still leaves the channel's internal position unchanged; nevertheless, sharing streams and updating records requires clear ownership and concurrency control. The main example below opens **two separate files** with the two APIs to compare byte outputs fairly and avoid unintended file-pointer interference.

## 8. Complete Java 17 Example: Same Layout, Same Operations, Identical Bytes

The example creates a temporary directory and two files holding the same three 16-byte records. The first file is created/read/updated **exclusively with `RandomAccessFile`**; the second file is created/read/updated **exclusively with `FileChannel` positional I/O**.

Sequence of steps:

1. Write three records:
   - `(1001, 5000, 1)`.
   - `(1002, 7250, 1)`.
   - `(1003, 9000, 0)`.
2. Read record `index=1` at offset 16 using both APIs.
3. Set `channel.position(7)` to prove positional I/O does not alter that value.
4. Update the balance of record `index=1` to `7777` using both APIs.
5. Observe `raf.getFilePointer()==32` and `channel.position()==7`.
6. Re-read the modified record and compare the full file contents via `Files.mismatch`.

### File `FixedRecordComparisonDemo.java`

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FixedRecordComparisonDemo {
    static final int RECORD_BYTES = Integer.BYTES
            + Long.BYTES + Integer.BYTES; // 16

    record Entry(int id, long balance, int status) { }

    static long offset(long index) {
        if (index < 0) {
            throw new IllegalArgumentException("Negative record index");
        }
        return Math.multiplyExact(index, (long) RECORD_BYTES);
    }

    static void requireReadable(long offset, long size)
            throws IOException {
        if (size % RECORD_BYTES != 0) {
            throw new IOException("Misaligned record file");
        }
        if (offset > size - RECORD_BYTES) {
            throw new EOFException("Record is outside the file");
        }
    }

    static void requireWritable(long offset, long size)
            throws IOException {
        if (size % RECORD_BYTES != 0 || offset > size) {
            throw new IOException("Invalid write position");
        }
    }

    static void writeRaf(RandomAccessFile file, long index, Entry e)
            throws IOException {
        long pos = offset(index);
        requireWritable(pos, file.length());
        file.seek(pos);
        file.writeInt(e.id());
        file.writeLong(e.balance());
        file.writeInt(e.status());
    }

    static Entry readRaf(RandomAccessFile file, long index)
            throws IOException {
        long pos = offset(index);
        requireReadable(pos, file.length());
        file.seek(pos);
        int id = file.readInt();
        long balance = file.readLong();
        int status = file.readInt();
        return new Entry(id, balance, status);
    }

    static void writeChannel(FileChannel channel, long index, Entry e)
            throws IOException {
        long pos = offset(index);
        requireWritable(pos, channel.size());

        ByteBuffer bytes = ByteBuffer.allocate(RECORD_BYTES);
        bytes.order(ByteOrder.BIG_ENDIAN);
        bytes.putInt(e.id());
        bytes.putLong(e.balance());
        bytes.putInt(e.status());
        bytes.flip();

        int written = 0;
        while (bytes.hasRemaining()) {
            int n = channel.write(bytes, pos + written);
            if (n <= 0) {
                throw new IOException("Channel write made no progress");
            }
            written += n;
        }
    }

    static Entry readChannel(FileChannel channel, long index)
            throws IOException {
        long pos = offset(index);
        requireReadable(pos, channel.size());

        ByteBuffer bytes = ByteBuffer.allocate(RECORD_BYTES);
        bytes.order(ByteOrder.BIG_ENDIAN);

        int received = 0;
        while (bytes.hasRemaining()) {
            int n = channel.read(bytes, pos + received);
            if (n == -1) {
                throw new EOFException("Incomplete record");
            }
            if (n == 0) {
                throw new IOException("Channel read made no progress");
            }
            received += n;
        }

        bytes.flip();
        return new Entry(
                bytes.getInt(), bytes.getLong(), bytes.getInt());
    }

    static String describe(Entry e) {
        return "id=" + e.id() + ", balance=" + e.balance()
                + ", status=" + e.status();
    }

    public static void main(String[] args) throws IOException {
        Path folder = Files.createTempDirectory("records-");
        Path rafPath = folder.resolve("raf.bin");
        Path channelPath = folder.resolve("channel.bin");

        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(rafPath.toFile(), "rw");
                 FileChannel channel = FileChannel.open(
                         channelPath,
                         StandardOpenOption.CREATE,
                         StandardOpenOption.READ,
                         StandardOpenOption.WRITE,
                         StandardOpenOption.TRUNCATE_EXISTING)) {

                Entry[] initial = {
                        new Entry(1001, 5000L, 1),
                        new Entry(1002, 7250L, 1),
                        new Entry(1003, 9000L, 0)
                };

                for (int i = 0; i < initial.length; i++) {
                    writeRaf(raf, i, initial[i]);
                    writeChannel(channel, i, initial[i]);
                }

                System.out.println("Record bytes: " + RECORD_BYTES);
                System.out.println("Before RAF: "
                        + describe(readRaf(raf, 1)));

                channel.position(7);
                System.out.println("Before FileChannel: "
                        + describe(readChannel(channel, 1)));

                Entry updated = new Entry(1002, 7777L, 1);
                writeRaf(raf, 1, updated);
                writeChannel(channel, 1, updated);

                System.out.println("RAF pointer after update: "
                        + raf.getFilePointer());
                System.out.println("FileChannel position after update: "
                        + channel.position());

                System.out.println("After RAF: "
                        + describe(readRaf(raf, 1)));
                System.out.println("After FileChannel: "
                        + describe(readChannel(channel, 1)));
            }

            System.out.println("Byte identical: "
                    + (Files.mismatch(rafPath, channelPath) == -1));
            System.out.println("File bytes: " + Files.size(rafPath));
        } finally {
            Files.deleteIfExists(channelPath);
            Files.deleteIfExists(rafPath);
            Files.deleteIfExists(folder);
        }
    }
}
```

### Compiling and Running

```bash
javac FixedRecordComparisonDemo.java
java FixedRecordComparisonDemo
```

**Stdout when file operations succeed:**

```text
Record bytes: 16
Before RAF: id=1002, balance=7250, status=1
Before FileChannel: id=1002, balance=7250, status=1
RAF pointer after update: 32
FileChannel position after update: 7
After RAF: id=1002, balance=7777, status=1
After FileChannel: id=1002, balance=7777, status=1
Byte identical: true
File bytes: 48
```

### Analyzing Key Takeaways

**First — identical layout.** `RandomAccessFile.writeInt/writeLong` and `ByteBuffer.putInt/putLong` with `BIG_ENDIAN` produce the exact same 16-byte ordering, so `Files.mismatch(...) == -1` when both files share the same final state.

**Second — offsets are in bytes.** Record 1 starts at offset `1*16=16`. Reading record index 1 does not mean calling `seek(1)` or `read(buffer,1)`.

**Third — pointers behave differently.** `writeRaf(raf,1,...)` calls `seek(16)` and writes 16 bytes, leaving `raf.getFilePointer()==32`. Conversely, `writeChannel(channel,1,...)` uses only the offset overload, so `channel.position()` stays **7**.

**Fourth — partial I/O.** `FileChannel.read/write` return actual bytes transferred. The example tracks `received`/`written` to advance the file offset manually and never lose the remainder. If the channel returns 0 when progress is needed, the example throws an error rather than spinning CPU forever.

**Fifth — validate size before accessing.** `requireReadable` ensures the file size is divisible by 16 and the index is in bounds. `requireWritable` allows overwriting an existing record or appending cleanly at EOF, avoiding accidentally creating holes if an offset lies beyond EOF.

**Sixth — functional verification differs from benchmarking.** The example verifies both approaches yield identical content; it **measures no timing** and proves neither API is faster.

### Why Does `FileChannel` Use Positional Overloads?

Calling `channel.position(offset); channel.read(buffer);` can still be correct, yet it mutates the shared channel position. Here, positional overloads express the clear contract of **reading/writing at a specified offset without disturbing the channel's current position**. This is handy when operations jump between arbitrary records, especially if you do not want one operation to shift another operation's sequential position.

Synchronizing data updates is still necessary, because "unchanged channel position" **does not mean** reading and modifying multiple fields of a record becomes an atomic transaction.

## 9. Another Program: Detecting a File with an Incomplete Record

A common bug is a file ending **mid-record**. Suppose 16-byte records are defined yet the file is 31 bytes long: there is one complete record and 15 bytes of a second record, not two full records.

The program below creates a 32-byte file, confirms reading record index 1, rejects index 2 and an excessively large index, and then truncates the file to 31 bytes. It uses both `RandomAccessFile.length()` and `FileChannel.size()` to show both APIs observe the true file size.

### File `FixedRecordValidationDemo.java`

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class FixedRecordValidationDemo {
    private static final int RECORD_BYTES = 16;

    static long checkedOffset(long index, long fileSize)
            throws IOException {
        if (fileSize < 0 || fileSize % RECORD_BYTES != 0) {
            throw new IOException("Misaligned file");
        }
        if (index < 0) {
            throw new IOException("Negative record index");
        }

        long offset;
        try {
            offset = Math.multiplyExact(index, (long) RECORD_BYTES);
        } catch (ArithmeticException ex) {
            throw new IOException("Record offset overflow", ex);
        }

        if (offset > fileSize - RECORD_BYTES) {
            throw new EOFException("Record out of range");
        }
        return offset;
    }

    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("validate-records-", ".bin");

        try {
            Files.write(file, new byte[32]);

            try (RandomAccessFile raf =
                         new RandomAccessFile(file.toFile(), "rw");
                 FileChannel channel = FileChannel.open(
                         file, StandardOpenOption.READ)) {

                System.out.println("RAF length: " + raf.length());
                System.out.println("Channel size: " + channel.size());

                System.out.println("Record 1 offset: "
                        + checkedOffset(1, raf.length()));

                try {
                    checkedOffset(2, channel.size());
                } catch (EOFException ex) {
                    System.out.println("Out of range: "
                            + ex.getClass().getSimpleName());
                }

                try {
                    checkedOffset(Long.MAX_VALUE, channel.size());
                } catch (IOException ex) {
                    System.out.println("Huge index: " + ex.getMessage());
                }

                raf.setLength(31);
                System.out.println("Aligned after truncate: "
                        + (channel.size() % RECORD_BYTES == 0));

                try {
                    checkedOffset(0, channel.size());
                } catch (IOException ex) {
                    System.out.println("Truncated record: "
                            + ex.getMessage());
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile and run:

```bash
javac FixedRecordValidationDemo.java
java FixedRecordValidationDemo
```

**Stdout when I/O succeeds:**

```text
RAF length: 32
Channel size: 32
Record 1 offset: 16
Out of range: EOFException
Huge index: Record offset overflow
Aligned after truncate: false
Truncated record: Misaligned file
```

**Why does check order matter?** For `index=Long.MAX_VALUE`, `index*16` cannot fit in a `long`. `Math.multiplyExact` catches the error before the program feeds a negative or overflowed offset into `seek`/`read`. For a 31-byte file, `size % 16 != 0` catches the broken layout before reading, instead of interpreting 15 partial bytes as valid data.

Lesson: **fixed-length** does not automatically make a file valid. A file can be cut short by crashes, incomplete writes, truncation, incompatible formats, or data corruption. Validate structure before accessing and define a recovery/rejection policy for abnormal files.

## 10. Reading a Record: EOF and Partial Reads

**`RandomAccessFile.readInt/readLong`** attempt to read all required bytes for the respective primitive. If insufficient due to EOF, they throw `EOFException`. However, succeeding on one field **does not prove the entire record is valid**: you might read `id` yet be missing bytes of `balance` or `status`.

With **`FileChannel.read(ByteBuffer,long)`**, return values can be:

| Result | Meaning |
| --- | --- |
| `n > 0` | Read `n` bytes; buffer position advances by `n` |
| `n == 0` | This call read no bytes; may relate to buffer, I/O state, or progress condition |
| `n == -1` | EOF reached |

Never call `read(buffer,offset)` once and assume a 16-byte buffer is full. Correct loop:

```java
int total = 0;

while (buffer.hasRemaining()) {
    int n = channel.read(buffer, recordOffset + total);

    if (n == -1) {
        throw new EOFException("Incomplete fixed record");
    }
    if (n == 0) {
        throw new IOException("No progress");
    }
    total += n;
}

buffer.flip();
// Decode from buffer.
```

This illustrative snippet requires `channel`, `recordOffset`, `buffer`, imports, and closing logic. When I/O occurs on a file **being written/truncated concurrently**, an initial size check does not eliminate races — you still must handle EOF or other errors while reading.

**Do not call `available()` to count remaining bytes in a `RandomAccessFile`:** `RandomAccessFile` does not implement `InputStream.available()` for that contract. Use `length` and `getFilePointer` or check against frame/layout, keeping in mind concurrent processes can still change the file.

## 11. Writing a Record: Partial Writes, Appends, and Holes

### With `RandomAccessFile`

`seek(offset)` followed by `writeInt/writeLong/writeInt` writes primitives sequentially. If writing fails mid-way, the file can end up **partially updated**, e.g., `id` changed while `balance` did not. Treat the business result as failed; never assume the whole record updated.

### With `FileChannel`

`write(buffer,offset)` can write fewer bytes than `remaining`. Thus you need:

```java
int sent = 0;
while (buffer.hasRemaining()) {
    int n = channel.write(buffer, recordOffset + sent);
    if (n <= 0) {
        throw new IOException("Partial write made no progress");
    }
    sent += n;
}
```

Both approaches can write to offsets past the file size. **Writing beyond EOF can extend the file and create a gap (hole)**; the contents of the gap depend on the filesystem/API and must not be assumed to form valid records automatically. If the application permits only updates or appends, enforce rules:

- **Update:** `0 <= index < recordCount` and size must be divisible by `RECORD_BYTES`.
- **Append:** `index == recordCount` and write only one complete record.
- **Disallowed:** `index > recordCount` without a workflow to allocate/initialize intermediate records.

The main example requires `offset <= fileSize` for writes; when file size is a multiple of 16, this permits updates or appends without creating holes.

**Note:** two concurrent operations can both observe the initial size and both attempt to append at the same offset. You need synchronization/locking or an atomic offset allocator per your architecture. A standalone size check **does not** guarantee concurrency safety.

## 12. Shared Position When Using `RandomAccessFile.getChannel()`

`RandomAccessFile.getChannel()` creates/returns a channel linked to the same file. Per contract:

- `raf.getFilePointer()` and `raf.getChannel().position()` represent a shared position for sequential operations.
- `raf.seek(100)` affects the linked channel's position.
- `channel.position(200)` affects the RAF's file pointer.
- `raf.readInt()` advances the pointer accordingly, and the channel sees the new position.
- `channel.read(buffer, absoluteOffset)` is positional, so it leaves the channel position unchanged and therefore does not move the shared pointer via the positional call itself.
- Changing file length through one interface is also reflected in the other.

Illustrative example:

```java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    FileChannel linked = raf.getChannel();

    raf.seek(8);
    System.out.println(linked.position()); // 8

    linked.position(16);
    System.out.println(raf.getFilePointer()); // 16
}
```

This is an illustrative snippet, not a standalone program, because `file` is undeclared and imports are missing. Never close `linked` and keep using `raf` expecting the file to stay open: the channel and RAF share the same underlying resource. Once one is closed, operations on the other may fail.

**Multithreading pitfall:** thread A calls `raf.seek(offsetA)`, thread B calls `raf.seek(offsetB)`, and then thread A's `raf.readInt()` can read the wrong offset unless the entire seek+read sequence is synchronized. Positional `FileChannel` **avoids contention on the channel's position**, yet it **does not** automatically prevent multiple threads from overwriting the same 16 bytes or guarantee consistent snapshots.

## 13. Byte Order and Format Compatibility Issues

### RAF Primitive Methods

`RandomAccessFile` implements `DataInput` and `DataOutput`, under which `writeInt`, `writeLong`, `readInt`, and `readLong` use big-endian for multi-byte values. It has no `order(LITTLE_ENDIAN)` method directly equivalent to `ByteBuffer.order`.

### `FileChannel`'s `ByteBuffer`

`ByteBuffer` defaults to big-endian when allocated, yet can be configured:

```java
ByteBuffer buffer = ByteBuffer.allocate(16)
        .order(ByteOrder.LITTLE_ENDIAN);
```

If you write a file in little-endian using `ByteBuffer` and read primitives with big-endian RAF, integers will be decoded incorrectly. **Define endianness in the file schema**, never leave it implicit.

Do not assume calling `ByteBuffer.order(LITTLE_ENDIAN)` changes how `RandomAccessFile.readInt()` behaves. To read little-endian using RAF, assemble bytes manually or use a suitable helper class.

### File Formats Should Be Versioned

The 16-byte fixed record in the example has no file header. For real applications, consider:

```text
Header:
  magic            4 bytes
  version          2 bytes
  record size      2 bytes
  record count     8 bytes (if needed)
Records:
  16 bytes * count
```

When adding a header, offset is `headerSize + index * recordSize`, which must be computed in `long` with overflow checks. Header fields read from untrusted files must be validated before allocating buffers or computing offsets.

If the schema changes from 16 to 24 bytes, old code cannot read new files using `i*16` and expect correct results. API names alone do not protect you from format version mismatches.

## 14. Adding Names or Strings to Fixed-Length Records

For `int/long`, field length is constant. For `String`, **character count is not byte count**:

- `"ABC"` in UTF-8 is 3 bytes.
- Accented Vietnamese strings can take more bytes than visible characters.
- Emojis can take 4 UTF-8 bytes yet 2 UTF-16 code units.

If every name must occupy exactly 20 bytes, you must specify:

1. Charset, typically UTF-8.
2. Policy if a name exceeds 20 bytes (reject or truncate at character boundaries, never slice mid-character causing invalid sequences).
3. Padding scheme for unused space (e.g., 0 bytes).
4. How to determine actual length on read (length prefix or controlled stripping of trailing padding).
5. Policy for NUL bytes inside content if NUL is used as a marker.
6. Unicode normalization rules if the system compares names by characters.

`RandomAccessFile.writeUTF()` **is unsuitable for automatically creating a fixed 20-byte field**, because it uses *modified UTF-8* with a length prefix and variable byte length. `ByteBuffer.put(text.getBytes(UTF_8))` likewise does not create a fixed-width field automatically.

In this lesson, records contain only integers to isolate the essentials: **same 16 bytes, same endianness, same offsets**.

## 15. Atomicity, Locking, and Consistency

A 16-byte record spans multiple fields. Calling three `raf.write...` methods or multiple `FileChannel.write` calls does not form an atomic transaction. If the program crashes mid-update, the file can hold a mixed state.

Scenarios requiring control:

- Two threads updating the same record.
- One thread reading a record while another writes it.
- Two processes concurrently appending to the end of the file.
- Process killed abruptly after a partial write.
- File truncated or reformatted by another process.

**`FileLock`** (via a channel) can help coordinate access, though limits, scope, and enforcement depend on the OS, filesystem, and processes; locks do not turn multiple writes into a crash-safe transaction. Never treat "holding a file lock" as a promise of data durability after power loss.

Solutions depending on requirements:

- For a single simple process, synchronize the entire record update inside one critical section.
- For multiple processes, use file locking alongside a consistent protocol.
- For updates needing crash consistency, use a write-ahead log/journal, dual record copies with versions/checksums, or a transactional database.
- For reads needing snapshots, use version numbers and re-verify before/after reading (with an appropriate protocol).
- For production workloads with transactional semantics, consider a database rather than building your own binary record engine.

**Positional I/O only avoids mutating channel position. It does not automatically provide record atomicity, isolation, or durability.**

## 16. Data Durability: Sync/Force Differences

Once `write...` finishes, data has passed through the API per the I/O contract, yet it **is not automatically durable on the storage device** if the application or OS buffers/caches writes.

With `RandomAccessFile`:

- `"rw"` differs from `"rwd"`/`"rws"` in synchronization policy.
- `raf.getFD().sync()` or an explicit mode can be used when synchronization is required.
- `raf.getChannel().force(true)` is the NIO equivalent.

With `FileChannel`:

```java
channel.force(true);
```

This snippet assumes the channel was opened with appropriate permissions. `force(boolean metaData)` requests flushing updates per contract; `true` covers relevant metadata as well, while `false` may focus on content depending on the API. Limitations of remote filesystems and special devices must still be considered.

**Never benchmark `RandomAccessFile("rws")` against `FileChannel.open(..., WRITE)` without calling `force` and declare `FileChannel` faster.** Those two setups request different durability guarantees. Define identical durability requirements before measuring.

## 17. Performance: Small Records, Random Access, and High Access Counts

Comparing the two APIs on performance depends on the workload:

| Workload | Where RAF May Have an Edge | Where `FileChannel` May Have an Edge |
| --- | --- | --- |
| Reading a few primitives from one record | Concise `readInt/readLong`, fewer app-managed buffer layers | Positional read clarifies explicit offset coordination |
| Many consecutive records | Sequential pointer reads, simple code | Buffer reuse or block reads to cut call overhead |
| Random read by index | `seek` then primitive reads | `read(buffer, absoluteOffset)` without shifting channel position |
| Multiple threads reading different regions | Shared RAF requires locking seek+read | Positional read avoids shared position, though real I/O limits remain |
| In-place record updates | Easy-to-follow `seek + write...` | `write(buffer, offset)` with buffer encoding and partial-write retries |
| High-volume writes | Can use binary API directly | Buffer reuse, batching, scattering/gathering when appropriate |
| Huge files | `long` offsets allow wide seeking | `long` offsets, size, transfer/mapping, and more options |
| Readability/verifiability | Clear primitive read/write calls | Requires getting `position/limit/flip/order` right |

**There is no universal conclusion on which is faster.** `FileChannel` can require more application code for 16-byte records due to packing primitives into a buffer. Conversely, when reading many records in a single block, `FileChannel` can reduce low-level call overhead compared to individual `RAF.readInt()` calls, depending on design.

Both are shaped by the OS page cache, SSD/HDD hardware, filesystem, JDK, file size, access patterns, and concurrency. Under heavy random reads of tiny records, physical HDD seek latency can dominate; when files sit in the page cache, CPU overhead and buffer allocation patterns stand out more.

## 18. Fair Benchmarking for This Exercise

To measure speed meaningfully, you must:

1. Generate the **exact same record set**, layout, endianness, and file size.
2. Run the same operation count and index pattern (sequential, uniform random, Zipf/hotspot...).
3. For RAF, **do not** compare per-field `readInt` calls against `FileChannel` reading a 1 MiB block and attribute the gap to the API; those are two different batching strategies.
4. For `FileChannel`, avoid `ByteBuffer.allocate(16)` on every call when measuring steady-state throughput; also benchmark buffer reuse.
5. Verify both options produce identical results without skipping partial read/write handling.
6. Warm up the JVM and run multiple iterations, alternating test order.
7. Separate **cold vs. warm page cache**; the later algorithm may benefit from the file already warmed by the earlier one.
8. Report the environment: JDK, OS, filesystem, storage device, heap, buffer size, record count, and thread count.
9. Isolate file open, buffer allocation, encode/decode, I/O calls, and result checks when analyzing bottlenecks.
10. Measure throughput, p50/p95 latency, allocation/GC, and memory pressure instead of a single run's milliseconds.

A mini benchmark suite might test:
- 1,000 records with 1 million repeated random reads.
- 1 million records with skewed random reads.
- 1 million records with a sequential scan.
- 100,000 scattered record updates.
- 1 thread vs. 4/16 threads; each thread with its own handle/buffer or sharing a channel under clear contracts.

**Those are example workloads, not pre-measured numbers.** Running on an SSD with cached files can behave completely differently from network/NFS/HDD storage. Never claim "NIO is 2x faster" from a 48-byte toy demo.

## 19. If You Need to Read Many Records at Once

The main example allocates a 16-byte `ByteBuffer` per read. Pedagogically, that keeps operations distinct. When scanning millions of records, consider **batching**:

- One buffer holding, say, `4096` 16-byte records = 65,536 bytes.
- Read one large block, then loop `getInt/getLong/getInt` to decode records in RAM.
- Reset the buffer via `clear/flip` between blocks.
- Handle end-of-file if a returned block is not an exact multiple of record size.
- Maintain identical byte order and schema boundaries.
- Benchmark heap/direct buffers, block sizes, and record counts.

`RandomAccessFile` can also `readFully(byte[])` a large block and decode with `ByteBuffer.wrap(array).order(BIG_ENDIAN)` or a custom parser. Thus **batching is not exclusive to `FileChannel`**.

A quick calculation:

```text
16 bytes/record * 4096 records = 65536 bytes
65536 bytes = 64 KiB
```

For sequential workloads, block read counts can be drastically lower than reading one record at a time. However, if the application typically needs one record at a random offset, reading a full 64 KiB block each time can waste I/O and cache bandwidth.

## 20. When to Choose `RandomAccessFile`?

`RandomAccessFile` is an intuitive choice when:

- You want an introductory example of file pointers/`seek`/primitive read/write.
- The schema contains fixed-width, big-endian binary values.
- The application has low concurrency/contention and simple index-based updates.
- Special NIO features like `transferTo` or mapped buffers are unnecessary.
- You want concise code with fewer `ByteBuffer.position/limit` details.

Drawbacks to keep in mind:

- `seek` plus subsequent read/write forms a **sequence tied to a shared pointer**.
- Fixed big-endian primitives; no buffer `ByteOrder`.
- A record spanning multiple write calls can be torn mid-write.
- When scaling to concurrency or NIO buffer pipelines, you may have to manage `getChannel` or switch APIs.

Do not dismiss RAF solely because it lives in `java.io`. For a straightforward record task, it can be **easier to audit and maintain**.

## 21. When to Choose `FileChannel`?

`FileChannel` typically fits best when:

- Explicit offset-based positional I/O independent of channel position is needed.
- Reading/writing via `ByteBuffer` integrates with NIO APIs.
- You want buffer reuse to scan records in large blocks.
- `FileLock`, `force`, `transferTo/transferFrom`, or `map` are required.
- Multiple tasks operate at separate offsets without mutating a shared file position.

Drawbacks to keep in mind:

- Must manage `ByteBuffer.order` and `position/limit/flip` state.
- Reads/writes can be partial; loops checking `remaining` are required.
- Allocating a new buffer per record increases allocation pressure.
- Using `FileChannel.map` introduces mapping lifecycle and cleanup overhead; memory mapping **is not automatically faster**.
- Positional read/write does not solve races when multiple threads update the same record.

**Choose `FileChannel` for its semantics and capabilities, then optimize through measurement**, rather than choosing it under the assumption NIO is guaranteed faster.

## 22. Common Exercise Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `seek(index)` instead of `seek(index*16)` | Reads mid-record | Use the byte-offset formula |
| `int index*recordSize` then assigning to long | Integer overflow | `Math.multiplyExact(index, (long) recordSize)` |
| Failing to check negative indices | Invalid offset | Validate beforehand |
| Assuming `getFilePointer()` returns a record index | Wrong unit | Pointer is in **bytes** |
| Calling `raf.readInt()` after seek and assuming pointer stays put | Next read starts at wrong place | Be explicit about position before each record |
| Assuming `FileChannel.read(buffer, offset)` always reads 16 bytes | Record decoded with missing data | Retry partial reads until full/EOF |
| Thinking positional I/O leaves `ByteBuffer.position()` unchanged | Buffer state mismanaged | Distinguish channel position from buffer position |
| Forgetting `flip()` before writing buffer after `putInt` | Zero `remaining` bytes to write | `flip` after encoding |
| Forgetting `flip()` before `getInt` after reading | Reads from wrong phase | `flip` after receiving all bytes |
| Big-endian RAF with little-endian channel | Different numeric values | Lock down byte order |
| Using `writeUTF` for a fixed-size string field | Variable-length field | Define byte-level field explicitly |
| File length not divisible by 16 | Truncated trailing record | Validate `size % 16` |
| Writing past EOF and assuming gap records are valid | Sparse holes or undefined bytes | Update/append only at valid offsets |
| Updating 16 bytes and assuming atomicity | Torn record on crash/race | Use locking/protocol/journal per requirements |
| Mixing RAF and channel without understanding shared position | Seek/read interfere with each other | Clear ownership or positional overloads |
| Forgetting to close files | Descriptor leaks | `try-with-resources` |
| Comparing speeds across different durability modes | Invalid benchmark | Match sync/force modes |
| Using `FileChannel.map` assuming it is always faster | Page faults and cleanup costs | Benchmark per workload |
| Skipping result/checksum checks during benchmarks | Measuring broken code | Verify bytes/record counts |
| Changing schema without versioning the file | Old code reads wrong offsets | Add header/magic/version/record size |

## 23. Self-Check Questions

**Question 1.** Records are 16 bytes long, 0-indexed. At what byte offset does record 25 begin?

**Answer:** `25 × 16 = 400` bytes. `seek(25)` is wrong because the offset is not a record index.

**Question 2.** `RandomAccessFile.seek(16)`, followed by `readInt()`, `readLong()`, and `readInt()`. Where is the pointer now?

**Answer:** `16 + 4 + 8 + 4 = 32`. Reading a full 16-byte record advances the pointer to the start of the next record.

**Question 3.** `FileChannel.position()==7`. You call `channel.read(buffer, 16)` and read 16 bytes. Does `channel.position()` become 23?

**Answer:** **No.** With the positional overload, the channel position remains 7; the **buffer position** advances by the 16 bytes received.

**Question 4.** A file is 48 bytes long and record size is 16. Is reading index 3 valid?

**Answer:** **No.** The file holds 3 records; valid indices are 0, 1, 2. Offset 48 sits right at EOF and contains no 16-byte record.

**Question 5.** To append a new record to a valid 48-byte file, at which offset do you begin writing?

**Answer:** **48**. After writing all 16 bytes, the file becomes 64 bytes long. Writing at index 4 (offset 64) when the file is 48 bytes would create a hole; this exercise rejects that.

**Question 6.** RAF writes balance with `writeLong(7250L)`; a `ByteBuffer` configured as `LITTLE_ENDIAN` reads it with `getLong()`. Do you get the same number?

**Answer:** Not guaranteed; normally it will **differ**. RAF writes big-endian. To get the same value, read as big-endian or swap bytes explicitly.

**Question 7.** Two threads call `raf.seek` and `raf.readInt` on the same RAF. Without synchronization, what is the risk?

**Answer:** Another thread can alter the shared file pointer between steps, causing a read at the wrong offset. Synchronize the entire sequence or use offset-based I/O without a shared pointer, while also coordinating data updates.

**Question 8.** A 32-byte file was truncated to 31 bytes. Can you compute `file.length()/16` and silently ignore the last 15 bytes?

**Answer:** That **hides signs of data corruption**. For a fixed 16-byte format, `length % 16 != 0` is an anomaly that must be reported/recovered per policy rather than treated as valid.

**Question 9.** Why does the comparison program print `"Byte identical: true"` yet allow no performance conclusion?

**Answer:** Because that is a **correctness check**. There is no latency/throughput timing, warmup, page-cache control, or repeated trials. Byte equality only proves both APIs produced the exact same file changes.

## 24. Checklist for Real-World Systems

Before reading/writing:

- Define record schema and version, with explicit offset/byte order/length per field.
- Validate indices, offset arithmetic, and `long` bounds.
- Check file size and `size % recordBytes == 0`.
- Define policies for updates, appends, and corrupted files.
- Pick the API based on requirements: primitive `seek` or positional buffer I/O.

During execution:

- With RAF: `seek` to the exact offset, read/write in order, guard the shared pointer.
- With `FileChannel`: configure `ByteBuffer` order, loop partial I/O, `flip` in the right phase, never confuse buffer and channel positions.
- For concurrent appends or updates: design locking, operation ordering, retries, and consistency.
- When durability matters: lock down sync/force policies before benchmarking.
- For huge files: use buffer reuse/batching if workload permits, without assuming it is always faster.

After execution:

- Verify size, byte counts, decoded fields, and EOF behavior.
- Close streams/channels with `try-with-resources`.
- Have a recovery plan for torn records from crashes or partial writes.
- Benchmark with identical inputs and conditions before optimizing.
- Test boundaries: empty file, single record, last record, negative index, `index == recordCount`, overflowing index, truncated record, wrong byte order, concurrent updates.

## 25. Summary

**Both `RandomAccessFile` and `FileChannel` are suitable for reading/writing fixed-length records by offset.**

- `RandomAccessFile` uses `seek(byteOffset)` and primitive `readInt/readLong/writeInt/writeLong`. It maintains a **shared file pointer** that advances by the bytes transferred.
- `FileChannel` uses `read/write(ByteBuffer, absoluteOffset)`. Positional overloads preserve `channel.position()`, while still advancing `ByteBuffer.position()`; partial I/O, `flip`, and byte order must be handled.
- The offset formula `base + index * recordSize` must use overflow-safe arithmetic; EOF and file-size divisibility by record size must be checked.
- Fixed-length records do not automatically provide transactions, crash safety, concurrency safety, or schema compatibility.
- Identical byte output is a prerequisite for comparison; **only benchmarking decides performance for a specific workload**.

For records made of simple primitives with minimal concurrency, **RAF often yields cleaner code**. When explicit offsets, buffer batching, and NIO integration are needed, **FileChannel is usually more convenient**. Judge suitability by semantics, correctness, and operational traits before optimizing.

**Official Documentation — Java SE 17:**

1. [RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html) — `seek`, `getFilePointer`, `readInt`, `writeLong`, `getChannel`.
2. [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html) — positional `read/write`, `size`, `position`, `force`, and locking.
3. [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — `putInt/getInt`, `putLong/getLong`, `flip`, `position/limit`.
4. [ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html) — `BIG_ENDIAN` and `LITTLE_ENDIAN`.
5. [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `mismatch`, temporary files, and path access.
