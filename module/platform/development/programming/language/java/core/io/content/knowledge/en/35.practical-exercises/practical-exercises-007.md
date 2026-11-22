# Comparing `RandomAccessFile` and `FileChannel` on Fixed-Length Records

## 1. Practice Problem and Objectives

Suppose a Java program stores multiple account records in a binary file. Each record is exactly **16 bytes**, so we immediately know the position of record `i` without reading all preceding records. The program needs to:

- Create a file containing several records using the same layout.
- Read any record by index.
- Update a value inside a record without rewriting the entire file.
- Detect invalid indices, EOF, and an incomplete trailing record.
- Compare two approaches: **`RandomAccessFile`** and **`FileChannel`** with **`ByteBuffer`**.
- Understand the difference between `RandomAccessFile`'s **file pointer**, channel **position**, and buffer **position/limit**.
- Avoid assuming which approach is faster before measuring on a real workload.

**Conclusion before writing code:** both APIs can perform random access on fixed-length records. `RandomAccessFile` is convenient with primitive read/write methods and `seek()`; `FileChannel` is convenient with positional reads/writes and NIO operations. **Reading the exact same 16 bytes at the exact same offset** is the prerequisite for a valid comparison.

This exercise uses **Java 17+** and Java SE only. All standalone runnable examples include their corresponding filename/class, `javac`/`java` commands, and stdout independent of temporary file paths.

## 2. What Is a Fixed-Length Record?

A **fixed-length record** is a record whose byte count and field order are defined upfront; every record of the same format version has the same length.

In this exercise, one record consists of:

| Offset in record | Field | Binary type | Bytes |
| --- | --- | --- | --- |
| 0–3 | `id` | `int` signed 32-bit | 4 |
| 4–11 | `balance` | `long` signed 64-bit | 8 |
| 12–15 | `status` | `int` signed 32-bit | 4 |
| **Total** | | | **16 bytes** |

Both write approaches use **big-endian**: the most significant byte appears first. `RandomAccessFile.writeInt/writeLong` uses big-endian per the `DataOutput` contract; `ByteBuffer` defaults to `BIG_ENDIAN` but should be set explicitly to prevent bugs when code is refactored.

For example, record `id=1002`, `balance=7250`, `status=1` has these byte groups:

```text
Offset:     0          4                     12
            |          |                      |
Field:      id:int     balance:long           status:int
Bytes:      00 00 03 EA  00 00 00 00 00 00 1C 52  00 00 00 01
Size:       < 4 bytes > <      8 bytes      > < 4 bytes >
```

Because `1002 = 0x000003EA` and `7250 = 0x0000000000001C52`, both APIs must interpret the exact same bytes when using the same layout and byte order.

**Not Java object serialization:** a fixed-record file holds application-defined bytes. It does not use `ObjectOutputStream`, carries no class descriptors, and does not automatically reconstruct an object graph. The program itself is responsible for schema and version compatibility.

## 3. Formula for Computing Offset

Let:

- `R`: bytes per record (here `R=16`).
- `i`: zero-based record index starting from **0**.
- `base`: starting position of the data region, equal to 0 when the file has no header.
- `offset`: byte position of the first byte of the record in the file.

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

A file with exactly three records must be `3 × 16 = 48` bytes long. If the file is 50 bytes long, the last two bytes do not form a valid record; that is a **partial/truncated/corrupt record**, not a fourth record.

### Avoiding Overflow When Computing Offset

Do not use:

```java
long offset = index * RECORD_BYTES;
```

if both `index` and `RECORD_BYTES` are `int`: the multiplication runs in `int` **before widening to `long`**, so it can overflow. Also guard against negative indices and `long` multiplication overflow.

Use:

```java
static long offsetOf(long index, int recordBytes) {
    if (index < 0 || recordBytes <= 0) {
        throw new IllegalArgumentException("Invalid index/size");
    }
    return Math.multiplyExact(index, (long) recordBytes);
}
```

This is an **illustrative helper snippet**; `Math.multiplyExact` throws `ArithmeticException` if the product cannot fit in a `long`. For files with a header, add `base` using `Math.addExact(base, product)`.

The offset formula is only valid if **every record truly has exact length R**. It cannot be applied directly if you insert variable-length UTF-8 strings, arbitrary metadata, or non-fixed markers between records.

## 4. `RandomAccessFile`: A Single Read/Write Pointer

`java.io.RandomAccessFile` provides an API for reading and writing data at arbitrary positions in a file. Core methods:

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

**`seek(long pos)`** sets the file pointer to an **absolute byte offset from the start of the file**, not a record index. Subsequent reads/writes continue from the current file pointer:

- `readInt()` reads exactly 4 bytes, returns `int`, and advances the file pointer by 4.
- `readLong()` reads exactly 8 bytes, returns `long`, and advances the file pointer by 8.
- `writeInt(x)` writes 4 bytes and advances the file pointer by 4.
- `writeLong(x)` writes 8 bytes and advances the file pointer by 8.
- `readFully(byte[])` attempts to read enough bytes to fill the array, throwing `EOFException` if EOF occurs before completion.
- `length()` returns file size in bytes.
- `setLength(newLength)` changes file length, requiring attention to truncation/extension.

Example reading record `i=1`:

```java
file.seek(1L * 16);
int id = file.readInt();       // Pointer: 20
long balance = file.readLong();// Pointer: 28
int status = file.readInt();   // Pointer: 32
```

**The file pointer has changed.** If another method calls `file.readInt()` right afterward without calling `seek`, it reads from offset 32—the start of the next record—rather than returning to offset 16.

The strength is concise primitive reading code. What must be managed is the **shared read/write position state inside a single `RandomAccessFile`**.

### Open Modes

| Mode | Meaning |
| --- | --- |
| `"r"` | Read-only, writing disallowed |
| `"rw"` | Read and write |
| `"rws"` | Read/write, requesting sync of data and metadata per contract |
| `"rwd"` | Read/write, requesting sync of file content per contract, differing from `"rws"` regarding metadata |

Higher sync modes can significantly alter write cost; **do not use `"rws"` in a head-to-head benchmark against an unforced `FileChannel`**, because those are two unequal durability guarantees.

## 5. `FileChannel`: Positional Read/Write with `ByteBuffer`

`java.nio.channels.FileChannel` can also read and write at arbitrary offsets:

```java
int read(ByteBuffer dst, long position) throws IOException;
int write(ByteBuffer src, long position) throws IOException;
```

These two overloads have important properties:

1. `position` is an **absolute byte offset** in the file, not a record index.
2. `read(dst, position)` does not modify `channel.position()`.
3. `write(src, position)` does not modify `channel.position()`.
4. **`ByteBuffer.position()` still changes** by the actual number of bytes read/written.
5. A single call may transfer **fewer bytes than requested**; you must loop until full or until EOF/error.
6. `FileChannel` supports length management via `size()`/`truncate(...)` and other NIO operations.

Conceptual example:

```java
ByteBuffer buffer = ByteBuffer.allocate(16);
buffer.order(ByteOrder.BIG_ENDIAN);

long offset = 1L * 16;
int received = channel.read(buffer, offset);

// channel.position() stays unchanged;
// buffer.position() may increase by received bytes.
```

This snippet is only illustrative, not a standalone program; `channel` must be opened and `received` must be checked. Do not call `buffer.getInt()` immediately while the buffer is still in write mode after `read` without calling `flip()`/managing positions properly.

### Buffer Position Differs from Channel Position

| Component | `RandomAccessFile` | `FileChannel` positional overload |
| --- | --- | --- |
| I/O position | `getFilePointer()`; changed via `seek/read/write` | Offset passed directly in each call |
| Internal position | File pointer changes | `channel.position()` **does not change** when using the offset overload |
| Intermediate buffer | Primitive methods can be used directly | `ByteBuffer` with `position/limit/capacity` |
| Reading primitives | `readInt()/readLong()` advance pointer automatically | `ByteBuffer.getInt()/getLong()` advance buffer position |
| Partial read | `readInt`/`readLong` require full bytes, throwing `EOFException` if short | `read(ByteBuffer,offset)` may return fewer bytes; application loops manually |
| Byte order | `DataInput`/`DataOutput` primitives use big-endian | Configure `buffer.order(...)` explicitly |

**Common mistake:** hearing "positional I/O does not change position" and assuming `ByteBuffer.position()` stays unchanged too. In fact, only the internal position of **`FileChannel`** is preserved; the buffer is still filled/consumed.

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

At this point `channel.write(bytes, offset)` reads data from `[position, limit)`. After each write, `bytes.position` advances accordingly. To send the remaining bytes next, **do not call `clear()`**, because `clear` could cause the program to resend out-of-range old bytes.

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

This snippet is not standalone because the read loop/error handling and `channel` are omitted. Calling `flip()` after receiving all 16 bytes prepares for the `get` methods. Three `get` calls consume exact 4+8+4=16 bytes.

`ByteBuffer.clear()` **does not physically erase bytes** in the backing array; it only resets position/limit. If a buffer is reused for sensitive data, apply a dedicated zeroing policy rather than treating `clear` as a security operation.

## 7. Direct Comparison Table

| Criterion | `RandomAccessFile` | `FileChannel` |
| --- | --- | --- |
| Package | `java.io` | `java.nio.channels` |
| Opening a file | `new RandomAccessFile(file, "r"/"rw")` | `FileChannel.open(path, StandardOpenOption...)` |
| Offset access | `seek(offset)` | `read/write(buffer, offset)` |
| I/O advances object position | Yes, after `seek/read/write` | Positional overloads **do not change** `channel.position` |
| Integer read/write | `readInt/readLong/writeInt/writeLong` | `ByteBuffer.putInt/getInt` and `putLong/getLong` |
| Big-endian | Fixed for `DataInput`/`DataOutput` primitives | Configured on buffer, defaults to `BIG_ENDIAN` |
| Code volume for small records | Usually small | More buffer ops and partial I/O loops |
| Buffer reuse/direct buffers | Not the API's primary model | Can reuse heap/direct `ByteBuffer` |
| Positional access across tasks | Must manage file pointer, synchronize if shared | Offset overloads avoid shared position; data sync still needed |
| Length management | `length/setLength` | `size/truncate` |
| File locks, transfer, mapping | Has `getChannel()` for NIO access | Exposes NIO methods directly |
| Full-record atomic update? | Not guaranteed | Not guaranteed |
| Absolute performance | Workload-dependent | Workload-dependent |

**Not two isolated worlds:** `RandomAccessFile.getChannel()` returns a `FileChannel` attached to the same underlying file. Per the API contract, `RandomAccessFile`'s file pointer and **the channel position returned by `getChannel()` are linked**. Therefore, mixing `raf.seek`, `raf.readInt`, and **non-positional** channel methods can cause one operation to affect the position seen by the other side's next operation.

The `channel.read(buffer, absoluteOffset)` overload still does not change the channel's internal position; however, sharing streams and updating records requires clear ownership and concurrency control. The main example below opens **two separate files** with the two APIs to compare byte outputs fairly and avoid unintended file-pointer interference.

## 8. Complete Java 17 Example: Same Layout, Same Operations, Identical Bytes

The example creates a temporary directory and two files holding the same three 16-byte records. The first file is created/read/updated **only via `RandomAccessFile`**; the second file is created/read/updated **only via `FileChannel` positional I/O**.

Sequence of operations:

1. Write three records:
   - `(1001, 5000, 1)`.
   - `(1002, 7250, 1)`.
   - `(1003, 9000, 0)`.
2. Read record `index=1` at offset 16 using both APIs.
3. Set `channel.position(7)` to prove positional I/O does not alter that value.
4. Update the balance of record `index=1` to `7777` using both APIs.
5. Observe `raf.getFilePointer()==32` and `channel.position()==7`.
6. Re-read the modified record and compare entire file contents using `Files.mismatch`.

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

### Compile and Run

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

### Analysis of Key Takeaways

**First — identical layout.** `RandomAccessFile.writeInt/writeLong` and `ByteBuffer.putInt/putLong` with `BIG_ENDIAN` produce the exact same 16-byte sequence, so `Files.mismatch(...) == -1` when both files hold the same final state.

**Second — offsets are in bytes.** Record 1 starts at offset `1*16=16`. Reading record index 1 does not mean calling `seek(1)` or `read(buffer,1)`.

**Third — pointers differ.** `writeRaf(raf,1,...)` calls `seek(16)` and writes 16 bytes, leaving `raf.getFilePointer()==32`. In contrast, `writeChannel(channel,1,...)` uses only the offset overload, so `channel.position()` stays **7**.

**Fourth — partial I/O.** `FileChannel.read/write` returns the number of bytes actually transferred. The example tracks `received`/`written` to advance the file offset and avoid dropping the remainder. If the channel returns 0 when progress is needed, the example throws an error rather than spinning CPU infinitely.

**Fifth — check size before accessing.** `requireReadable` checks that the file size is divisible by 16 and the index is in bounds. `requireWritable` only allows overwriting an existing record or appending right at the end of the file, avoiding accidental holes from out-of-bounds offsets.

**Sixth — functional verification differs from benchmarking.** The example verifies that the APIs reflect identical contents; it **does not measure time** and does not prove which approach is faster.

### Why Does `FileChannel` Use Positional Overloads?

Calling `channel.position(offset); channel.read(buffer);` can also work, but it mutates the shared channel position. In this example, positional overloads express the contract **read/write at a specified offset without changing the channel's current position**. This is convenient when operations jump between arbitrary records, especially if you do not want one operation to shift another's sequential position.

Synchronizing data updates still remains necessary, because "not changing channel position" **does not mean** reading and modifying multiple fields of a record becomes an atomic transaction.

## 9. Another Program: Detecting a File with an Incomplete Record

A common failure is a file ending **mid-record**. For instance, with a 16-byte record definition and a 31-byte file: there is one complete record and 15 bytes of a second record, not two valid records.

The program below creates a 32-byte file, confirms record index 1 is readable, rejects index 2 and a huge index, and then truncates the file to 31 bytes. It uses both `RandomAccessFile.length()` and `FileChannel.size()` to show both APIs observe the true file size.

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

**Why does check order matter?** With `index=Long.MAX_VALUE`, `index*16` cannot fit in `long`. `Math.multiplyExact` catches the error before the program feeds a negative or overflowed offset to `seek`/`read`. With the 31-byte file, `size % 16 != 0` catches the broken layout before reading, rather than interpreting 15 trailing bytes as valid data.

Lesson: **fixed-length** does not make a file valid by itself. Files can be truncated by crashes, partial writes, manual truncation, incompatible formats, or data corruption. Validate structure before accessing and have a recovery or quarantine policy for malformed files.

## 10. Reading One Record: EOF and Partial Reads

**`RandomAccessFile.readInt/readLong`** attempts to read all bytes for the corresponding primitive. If EOF occurs before enough bytes are read, it throws `EOFException`. However, succeeding on one field **does not prove the entire record is valid**: `id` might be read while `balance` or `status` is short a few bytes.

With **`FileChannel.read(ByteBuffer,long)`**, return values can be:

| Result | Meaning |
| --- | --- |
| `n > 0` | Read `n` bytes, buffer position advanced by `n` |
| `n == 0` | Current call read zero bytes; may relate to buffer, I/O state, or progress condition |
| `n == -1` | Reached EOF |

Do not call `read(buffer,offset)` once and assume the 16-byte buffer is full. Correct loop:

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

This illustrative snippet requires `channel`, `recordOffset`, `buffer`, imports, and closing logic. When I/O runs on a file **being concurrently modified/truncated**, an upfront size check does not eliminate races—EOF or other errors during reading must still be handled.

**Do not use `available()` to compute remaining bytes of a `RandomAccessFile`:** `RandomAccessFile` does not implement `InputStream.available()` for this contract. Use `length` and `getFilePointer` or frame/layout checks, keeping in mind concurrent processes can still modify the file.

## 11. Writing One Record: Partial Writes, Appending, and Holes

### With `RandomAccessFile`

`seek(offset)` followed by `writeInt/writeLong/writeInt` writes primitives sequentially. If writing fails mid-way, the file can end up **partially updated**—for instance `id` updated while `balance` is not. Treat the business result as a failure rather than assuming the whole record updated.

### With `FileChannel`

`write(buffer,offset)` may write fewer bytes than `remaining`. Thus:

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

Both APIs can write to an offset beyond the file size. **Writing past EOF can extend the file and create a hole**; hole contents depend on the filesystem/API and must not be treated as an automatically valid record region. If the application permits only updates or appends, enforce rules:

- **Update:** `0 <= index < recordCount` and size must be divisible by `RECORD_BYTES`.
- **Append:** `index == recordCount` and write one complete record only.
- **Disallowed:** `index > recordCount` without an explicit procedure for allocating/initializing intermediate records.

The main example enforces `offset <= fileSize` for writes; when file size is a multiple of 16, this allows updates or appends without creating holes.

**Note:** two concurrent operations can observe the same initial size and both attempt to append at the same offset. Synchronization/locking or an atomic offset allocator is required per application architecture. A standalone size check **does not** guarantee concurrency safety.

## 12. Shared Position When Using `RandomAccessFile.getChannel()`

`RandomAccessFile.getChannel()` creates/returns a channel linked to the same file. Per contract:

- `raf.getFilePointer()` and `raf.getChannel().position()` represent a shared sequential position.
- `raf.seek(100)` affects the linked channel's position.
- `channel.position(200)` affects RAF's file pointer.
- `raf.readInt()` advances the pointer accordingly, and the channel sees the new position.
- `channel.read(buffer, absoluteOffset)` is a positional operation, so it does not change channel position; therefore it does not alter the shared pointer.
- Changing file length through one interface is also reflected through the other.

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

This is an illustrative snippet rather than a standalone program, since `file` is undeclared and imports are missing. Do not close `linked` and keep using `raf` expecting the file to stay open: the channel and RAF share the same underlying resource. Once one side is closed, remaining operations may become unusable.

**Multithreading pitfall:** thread A calls `raf.seek(offsetA)`, thread B calls `raf.seek(offsetB)`, and then thread A calls `raf.readInt()`, reading from the wrong offset unless the entire seek+read sequence is synchronized. Positional `FileChannel` avoids **contention over channel position**, yet **does not** prevent multiple threads from overwriting the same 16 bytes or guarantee consistent snapshots.

## 13. Byte Order and Format Compatibility

### RAF Primitive Methods

`RandomAccessFile` implements `DataInput` and `DataOutput`, under which `writeInt`, `writeLong`, `readInt`, and `readLong` use big-endian for multi-byte values. It has no direct equivalent to `ByteBuffer.order(LITTLE_ENDIAN)`.

### `FileChannel`'s `ByteBuffer`

`ByteBuffer` defaults to big-endian on creation, but can be configured:

```java
ByteBuffer buffer = ByteBuffer.allocate(16)
        .order(ByteOrder.LITTLE_ENDIAN);
```

If a file is written little-endian with `ByteBuffer` and read using big-endian RAF primitives, integer values will be decoded wrongly. **Define endianness in the file schema**, never leaving it implicit.

In files using mixed APIs, do not assume calling `ByteBuffer.order(LITTLE_ENDIAN)` changes `RandomAccessFile.readInt()`. If you want RAF to read little-endian values, combine bytes manually or use an appropriate helper class.

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

When adding a header, offset becomes `headerSize + index * recordSize`, computed in `long` with overflow checks. Header fields coming from untrusted files must be validated before allocating buffers or computing offsets.

If a schema changes from 16 to 24 bytes, old code cannot read the new file using `i*16` and expect correct results. API names do not protect you from format version mismatches.

## 14. Adding Names or Strings to Fixed-Length Records

For `int`/`long`, field length is constant. For `String`, **character count is not byte count**:

- `"ABC"` in UTF-8 is 3 bytes.
- Vietnamese strings with diacritics can take more bytes than visible characters.
- Emojis can take 4 UTF-8 bytes yet 2 UTF-16 code units.

If each name must occupy exactly 20 bytes, specify:

1. Charset, typically UTF-8.
2. Policy if the name exceeds 20 bytes (reject or truncate at a character boundary, never split mid-character bytes).
3. Padding for unused bytes (e.g., `0` bytes).
4. How to determine actual length on read (length prefix or controlled trailing-padding strip).
5. Policy for NUL bytes inside content if NUL is used as a marker.
6. Unicode normalization if the system compares names by character.

`RandomAccessFile.writeUTF()` **is unsuitable for automatically creating a fixed 20-byte field**, because it uses *modified UTF-8* with a length prefix and variable byte count. `ByteBuffer.put(text.getBytes(UTF_8))` likewise does not produce a fixed-width field by itself.

In this exercise, records use only integers to isolate the essentials: **same 16 bytes, same endianness, same offset**.

## 15. Atomicity, Locks, and Consistency

One 16-byte record contains multiple fields. Calling three `raf.write...` methods or multiple `FileChannel.write` calls does not form an atomic transaction. If the program crashes mid-update, the file can hold mixed old/new state.

Scenarios to control:

- Two threads updating the same record.
- One thread reading a record while another thread is writing it.
- Two processes appending to the end of the file concurrently.
- Process killed abruptly after a partial write.
- File truncated or reformatted by another process.

**`FileLock`** (via channel) can assist with coordinating access, though enforcement/scope and lock compliance depend on the OS/filesystem/processes; locks do not turn multiple writes into a crash-safe transaction. Do not treat "holding a file lock" as a guarantee of data durability across power loss.

Solutions depending on requirements:

- For a simple single process, synchronize entire record updates within a critical section.
- For multiple processes, use file locking and a consistent protocol.
- For crash-consistent updates, use a write-ahead log/journal, dual record slots with version/checksum, or a transactional database.
- For snapshot reads, use version numbers and re-verify before/after reading (with a matching protocol).
- For real transactional workloads, consider using a database rather than building a custom binary record engine.

**Positional I/O only avoids mutating channel position. It does not by itself provide record atomicity, isolation, or durability.**

## 16. Data Durability: Difference Between `sync` and `force`

When `write...` returns, data has been handed off through the API per the I/O contract, but **is not guaranteed to be persisted on the physical storage device** when the application or OS caches writes.

With `RandomAccessFile`:

- `"rw"` differs from `"rwd"`/`"rws"` in sync policy.
- `raf.getFD().sync()` or an explicit policy can be used when requesting synchronization.
- `raf.getChannel().force(true)` is the NIO counterpart.

With `FileChannel`:

```java
channel.force(true);
```

This snippet assumes the channel is opened with appropriate permissions. `force(boolean metaData)` requests flushing updates per contract; `true` includes relevant metadata, while `false` may focus on file content depending on the API. Limitations on remote filesystems or special devices still apply.

**Do not benchmark `RandomAccessFile("rws")` against `FileChannel.open(..., WRITE)` without `force` and declare `FileChannel` faster.** The two setups request different durability levels. Define identical durability requirements before measuring.

## 17. Performance: Small Records, Random Access, and Many Operations

Comparing the two APIs on performance depends on the workload:

| Workload | Where RAF May Have an Edge | Where `FileChannel` May Have an Edge |
| --- | --- | --- |
| Reading a few primitives from one record | Concise `readInt/readLong`, fewer app-managed buffer layers | Positional read makes offset coordination explicit |
| Many consecutive records | Sequential pointer reads, simple code | Buffer reuse or block reads to cut call count |
| Random reads by index | `seek` then read primitives | `read(buffer, absoluteOffset)` without changing channel position |
| Multiple threads reading different regions | Shared RAF requires coordinating seek+read | Positional reads avoid shared position, though real I/O limits still apply |
| Updating records in the same file | Straightforward `seek + write...` | `write(buffer, offset)` with buffer encoding and partial-write retries |
| High-volume writes | Direct binary API usable | Buffer reuse, batching, scattering/gathering where appropriate |
| Very large files | `long` offsets allow wide seeking | `long` offsets, size, transfer/mapping, and more options |
| Code readability / verifiability | Explicit primitive reads/writes | Extra `position/limit/flip/order` state must be right |

**There is no universal answer on which is faster.** `FileChannel` may require more application code for a 16-byte record due to packing primitives into a buffer. Conversely, when reading many records in one block, `FileChannel` can cut low-level call overhead compared to repeated `RAF.readInt()` calls, depending on design.

Both are affected by OS page cache, SSD/HDD, filesystem, JDK, file size, access pattern, and concurrency. For random reads of many small records, physical HDD seek latency can dominate; for cached files, CPU overhead and buffer allocation strategy may stand out.

## 18. Fair Benchmarking for This Exercise

To measure speed meaningfully:

1. Generate the **exact same record set**, same layout, same endianness, and same file size.
2. Run the same operation count and same index pattern (sequential, uniform random, Zipf/hotspot...).
3. For RAF, **do not** pit per-field `readInt` against `FileChannel` reading a 1 MiB block and claim one API is faster; those are two different batching strategies.
4. For `FileChannel`, avoid allocating `ByteBuffer.allocate(16)` every iteration when measuring steady-state throughput; also test buffer reuse.
5. Verify both produce identical results without missing partial reads/writes.
6. Warm up the JVM and run multiple iterations, alternating test order.
7. Separate **cold vs. warm page cache**; the algorithm running second may benefit from files warmed by the first.
8. Report environment: JDK, OS, filesystem, storage device, heap, buffer size, record count, and thread count.
9. Isolate file open, buffer creation, encode/decode, I/O operations, and verification if analyzing bottlenecks.
10. Measure throughput, p50/p95 latency, allocation/GC, and memory pressure rather than just single-run milliseconds.

A mini benchmark suite could test:
- 1,000 records and 1 million repeated random reads.
- 1 million records and skewed random reads.
- 1 million records and sequential scans.
- 100,000 scattered record updates.
- 1 thread versus 4/16 threads; per-thread handles/buffers versus a shared channel under an explicit contract.

**Those are illustrative workloads, not pre-measured numbers.** Running on an SSD with cached files can differ dramatically from network/NFS/HDD. Never claim "NIO is 2x faster" from a single 48-byte demo.

## 19. When You Need to Read Many Records at Once

The main example creates a 16-byte `ByteBuffer` per read. For learning, this isolates each operation cleanly. When scanning millions of records, consider **batching**:

- One buffer holding, say, `4096` 16-byte records = 65,536 bytes.
- Read one large block, then loop `getInt/getLong/getInt` to decode records in RAM.
- Reset the buffer with `clear/flip` between blocks.
- Handle end-of-file if the returned block is not an exact record multiple.
- Keep the same byte order and schema boundaries.
- Benchmark heap/direct buffers, block sizes, and record counts.

`RandomAccessFile` can also `readFully(byte[])` a large block and decode with `ByteBuffer.wrap(array).order(BIG_ENDIAN)` or a custom parser. Thus **batching is not exclusive to `FileChannel`**.

Sample calculation:

```text
16 bytes/record * 4096 records = 65536 bytes
65536 bytes = 64 KiB
```

For sequential workloads, block reads can drastically reduce call count compared to one record at a time. Yet if an application typically needs only a single record at a random offset, reading a full 64 KiB block each time can waste I/O and cache bandwidth.

## 20. When to Choose `RandomAccessFile`?

`RandomAccessFile` is an approachable choice when:

- You want an introductory example of file pointers/`seek`/primitive reads and writes.
- The schema holds fixed big-endian binary primitives.
- The application has few threads, low contention, and simple index-based updates.
- Special NIO features like `transferTo` or mapped buffers are not needed.
- You want concise code with fewer `ByteBuffer.position/limit` details.

Drawbacks to keep in mind:

- `seek` and subsequent reads/writes form **a sequence dependent on a shared pointer**.
- Fixed big-endian primitives with no buffer `ByteOrder`.
- A record written in multiple calls can be partially written.
- When parallelizing or integrating into NIO buffer pipelines, you may have to manage `getChannel` or switch APIs.

Do not dismiss RAF merely because it lives in `java.io`. For a simple record problem, it can be **easier to inspect and maintain**.

## 21. When to Choose `FileChannel`?

`FileChannel` typically fits when:

- You need explicit offset-based positional I/O independent of channel position.
- You need `ByteBuffer`-based I/O and integration with NIO APIs.
- You want buffer reuse to scan records in large blocks.
- You need `FileLock`, `force`, `transferTo/transferFrom`, or `map`.
- A design divides tasks by offset without letting tasks shift a shared file position.

Drawbacks to keep in mind:

- You must manage `ByteBuffer.order` and `position/limit/flip` state.
- Reads/writes can be partial; you must loop over `remaining`.
- Allocating a buffer per record can raise allocation pressure.
- Using `FileChannel.map` introduces mapping lifecycle issues and costs; mapping **is not automatically faster**.
- Positional reads/writes do not resolve races when multiple threads update the same record.

**Choose `FileChannel` for matching semantics and capabilities, then optimize via measurement**, rather than picking it under the assumption that NIO is guaranteed faster.

## 22. Common Mistakes in Exercises

| Mistake | Consequence | Fix |
| --- | --- | --- |
| `seek(index)` instead of `seek(index*16)` | Reads mid-record | Compute byte offset with formula |
| Using `int index*recordSize` then assigning to `long` | Integer overflow | `Math.multiplyExact(index, (long) recordSize)` |
| Not checking negative index | Invalid offset | Validate upfront |
| Assuming `getFilePointer()` is record index | Wrong unit | Pointer is in **bytes** |
| Calling `raf.readInt()` after `seek` assuming pointer stays fixed | Next read uses wrong offset | Make position explicit before each record |
| Assuming `FileChannel.read(buffer, offset)` always reads 16 bytes | Record decodes incomplete data | Retry partial reads until full/EOF |
| Assuming positional I/O leaves `ByteBuffer.position()` unchanged | Buffer state mishandled | Distinguish channel position from buffer position |
| Forgetting `flip()` before writing buffer after `putInt` | Zero `remaining` to write | `flip` after encoding |
| Forgetting `flip()` before `getInt` after reading | Reads wrong phase | `flip` after receiving all bytes |
| RAF big-endian, channel little-endian | Numeric values differ | Fix byte order in spec |
| Using `writeUTF` for fixed-size string fields | Variable-length field | Define byte-based field manually |
| File length not divisible by 16 | Trailing record truncated | Validate `size % 16` |
| Writing past EOF and assuming gap records are valid | Holes or undefined data | Update/append only at valid offsets |
| Updating 16 bytes and assuming atomicity | Torn records on crash/race | Locks/protocols/journals as needed |
| Sharing RAF and channel without understanding shared position | Seeks/reads interfere | Clear ownership or positional overloads |
| Forgetting to close files | Descriptor leaks | `try-with-resources` |
| Comparing speeds under unequal durability modes | Incomparable benchmark | Match sync/force modes |
| Using `FileChannel.map` assuming it is always faster | Page faults and cleanup have costs | Benchmark per workload |
| Skipping checksum/result validation in benchmarks | Measures incomplete data | Verify byte/record counts |
| Changing schema without versioning the file | Old code decodes wrong offsets | Header/magic/version/record size |

## 23. Self-Check Questions

**Question 1.** Records are 16 bytes, zero-indexed. What byte offset does record 25 start at?

**Answer:** `25 × 16 = 400` bytes. `seek(25)` is wrong because offsets are not record indices.

**Question 2.** `RandomAccessFile.seek(16)`, followed by `readInt()`, `readLong()`, and `readInt()`. Where is the pointer?

**Answer:** `16 + 4 + 8 + 4 = 32`. Reading one full 16-byte record advances the pointer to the start of the next record.

**Question 3.** `FileChannel.position()==7`. Call `channel.read(buffer, 16)` and read 16 bytes. Does `channel.position()` become 23?

**Answer:** **No.** With the positional overload, channel position stays 7; **buffer position** advances by the 16 bytes received.

**Question 4.** A file is 48 bytes long and record size is 16. Is reading index 3 valid?

**Answer:** **No.** The file holds 3 records, so valid indices are 0, 1, 2. Offset 48 is right at EOF and contains no 16-byte record.

**Question 5.** To append a new record to a valid 48-byte file, what offset should writing start at?

**Answer:** **48**. After writing 16 bytes, file size becomes 64 bytes. Using index 4 (offset 64) when the file is 48 bytes could create a hole; this exercise rejects that operation.

**Question 6.** RAF writes balance via `writeLong(7250L)`; `ByteBuffer` sets `LITTLE_ENDIAN` to read via `getLong()`. Do you get the same number?

**Answer:** Not guaranteed; normally it will **differ**. RAF writes big-endian. To get the same result, read as big-endian or convert explicitly.

**Question 7.** Two threads call `raf.seek` and `raf.readInt` on the same RAF. Without synchronization, what is the risk?

**Answer:** The other thread can alter the shared file pointer in between steps, causing a read at the wrong offset. Synchronize the entire sequence or design offset I/O without a shared pointer, while also coordinating data updates.

**Question 8.** A 32-byte file is truncated to 31 bytes. Can you use `file.length()/16` and silently ignore the last 15 bytes?

**Answer:** That **hides signs of data corruption**. With a fixed 16-byte format, `length % 16 != 0` is an anomaly signal that must be reported or recovered per policy, never treated as valid.

**Question 9.** Why does the comparison program print `Byte identical: true` yet draw no performance conclusion?

**Answer:** Because this is a **correctness check**. There are no latency/throughput measurements, warmups, page-cache controls, or iteration counts. Matching bytes only prove both APIs applied the same modifications.

## 24. Checklist for Real Systems

Before reading/writing:

- Define record schema and version, with explicit offset/byte order/length per field.
- Validate index, offset math, and `long` limits.
- Check file size and `size % recordBytes == 0`.
- Define policies for updates, appends, and corrupt files.
- Pick the API matching requirements: primitive `seek` or positional buffer I/O.

During execution:

- With RAF: `seek` exact offset, read/write in exact order, guard shared pointer.
- With `FileChannel`: set `ByteBuffer` order, loop partial I/O, `flip` in the right phase, never confuse buffer and channel positions.
- For concurrent appends or updates: design locks, operation ordering, retries, and consistency.
- If durability is needed: define sync/force policy before benchmarking.
- For very large files: use buffer reuse/batching if workload suits, without assuming it is always faster.

After execution:

- Verify size, byte count, decoded fields, and EOF cases.
- Close streams/channels with `try-with-resources`.
- Have a recovery plan for torn records caused by crashes or partial writes.
- Benchmark with identical inputs and conditions before choosing optimizations.
- Test boundaries: empty file, single record, last record, negative index, `index == recordCount`, overflowing index, truncated record, wrong byte order, concurrent updates.

## 25. Summary

**Both `RandomAccessFile` and `FileChannel` are suitable for reading/writing fixed-length records by offset.**

- `RandomAccessFile` uses `seek(byteOffset)` and primitive `readInt/readLong/writeInt/writeLong`. It has a **shared file pointer** that advances by the bytes transferred.
- `FileChannel` uses `read/write(ByteBuffer, absoluteOffset)`. Positional overloads keep `channel.position()` intact while advancing `ByteBuffer.position()`; partial I/O, `flip`, and byte order must be handled.
- The offset formula `base + index * recordSize` must use safe arithmetic; EOF and size divisibility by record size must be checked.
- Fixed-length records do not automatically provide transactions, crash safety, concurrency safety, or schema compatibility.
- Identical byte output is the correctness prerequisite for comparison; **only benchmarks decide performance for a specific workload**.

For records of simple primitives with low contention, **RAF often yields readable code**. When explicit offsets, buffer batching, and NIO integration are needed, **FileChannel is often more convenient**. Evaluate suitability by semantics, correctness, and operational properties before optimizing.

**Official References — Java SE 17:**

1. [RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html) — `seek`, `getFilePointer`, `readInt`, `writeLong`, `getChannel`.
2. [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html) — positional `read/write`, `size`, `position`, `force`, and locks.
3. [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html) — `putInt/getInt`, `putLong/getLong`, `flip`, `position/limit`.
4. [ByteOrder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteOrder.html) — `BIG_ENDIAN` and `LITTLE_ENDIAN`.
5. [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `mismatch`, temporary files, and path access.