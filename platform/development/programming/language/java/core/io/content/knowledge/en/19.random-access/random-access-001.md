# RandomAccessFile and the `r`, `rw`, `rws`, `rwd` Modes

## 1. The problem: reading and modifying an arbitrary position in a file

When processing a text file line by line, we usually read sequentially from beginning to end. Sometimes, however, an application needs to **read the 500th record**, **modify exactly 4 bytes in the middle of a file**, or **append bytes after the last byte** without re-reading the entire content. That is **random access**.

Java provides the **`java.io.RandomAccessFile`** class to read/write by **byte position** in a file:

- It maintains a **file pointer** (position cursor), starting at offset `0` when the file is opened.
- `seek(offset)` moves the pointer to the desired offset.
- `read...` operations fetch bytes starting at the pointer; `write...` operations write bytes at the pointer. After each operation, the pointer advances by the number of bytes read or written.
- `length()` returns the file size **in bytes**, which differs from the number of characters or records.
- The open mode (`"r"`, `"rw"`, `"rws"`, `"rwd"`) determines write permissions and the requirement to synchronize updates to the storage device.

`RandomAccessFile` implements `DataInput`, `DataOutput`, and `Closeable`; it is **not** a subclass of `InputStream` or `OutputStream`. Because the pointer can be moved both forward and backward, it is well suited for binary files, fixed-size record formats, header updates, or byte indexes.

Diagram of a file containing three `int` integers (Java writes each `int` as **4 bytes**, most significant byte first):

~~~text
Byte offset       0             4             8            12 = length
                  |  int = 10   |  int = 20   |  int = 30  |
                  ^ start         ^ seek(4)     ^ seek(8)   ^ EOF
~~~

Calling `seek(4)` followed by `writeInt(99)` replaces **only the four bytes from index 4 through 7**. The file remains 12 bytes long; the other two numbers stay unchanged.

## 2. The four file open modes

Syntax:

~~~java
// A Path can be converted to a File when using the default file system:
try (RandomAccessFile raf = new RandomAccessFile(path.toFile(), "rw")) {
    // Read/write at desired byte offsets
}
~~~

This snippet is shown in a context where `Path path` and the necessary imports are already declared. A complete runnable program is provided in Section 5.

| Mode | Read | Write | If the file does not exist | Synchronization guarantee on update |
|---|---|---|---|---|
| `"r"` | Yes | No | Open fails (`FileNotFoundException`) | No writes performed |
| `"rw"` | Yes | Yes | Attempts to create a new file | Does not require each update to be synchronized to the device |
| `"rws"` | Yes | Yes | Attempts to create a new file | Synchronizes **content and metadata** for each update |
| `"rwd"` | Yes | Yes | Attempts to create a new file | Synchronizes **content** for each update; metadata does not have the same requirement |

Key points to remember:

- `"r"` is **read-only**. Calling `writeInt`, `writeBytes`, `write`, or any other write method on this instance causes Java to throw an **`IOException`**.
- `"rw"` means **read/write**, which **does not mean** append to the end of the file. Unless you explicitly call `seek(length())`, the program writes at the **current pointer**; right after opening, the pointer is at offset 0, so it can **overwrite the beginning of the file**.
- `"rws"` and `"rwd"` are both read/write like `"rw"`, with an additional requirement for durable persistence on every update.
- Only the four strings above are valid. For example, `"w"`, `"a"`, `"rb"`, `"rw+"`, or `"R"` will cause an **`IllegalArgumentException`**.
- Opening the file can still fail due to insufficient permissions, inability to create the file, missing parent directories, OS access restrictions on the file, or I/O errors. `"rw"` does not automatically create missing parent directories.
- `RandomAccessFile` **does not automatically truncate** an existing file when opened with `"rw"`; to erase old content, you must explicitly call `setLength(0)`.

### 2.1. `rws`: synchronizing data **and metadata**

`"rws"` requires every update to the file's content or metadata to be written **synchronously** to the underlying storage device. File-related metadata can include file length and modification timestamps; details depend on the file system.

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rws")) {
    raf.seek(0);
    raf.writeInt(42); // Requires synchronizing content and related metadata.
}
~~~

This snippet assumes a valid `File file`. This mode is useful when durability is needed for both file-management information and data—for example, updates that extend the file's length. On some file systems, synchronizing metadata incurs additional I/O overhead.

### 2.2. `rwd`: synchronizing data, potentially cheaper

`"rwd"` requires every **content** update to be written synchronously; Java does not require synchronizing metadata as `"rws"` does.

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rwd")) {
    raf.seek(0);
    raf.writeInt(42); // Requires synchronizing file data.
}
~~~

If you frequently overwrite an **already existing** byte region, `"rwd"` can make sense because it does not require the same level of metadata synchronization. However, you cannot assume `"rwd"` will always be faster than `"rws"` on every device; results depend on the OS, caching, file system, and update pattern.

**Very important:** `rwd` only guarantees data synchronization per the API contract. For an operation that **extends a file**, metadata such as the file size can also be critical so that the new data remains accessible after a crash. Do not assume "data is synchronized" means the entire file structure has been persisted the same way as with `rws`.

### 2.3. Durability does not mean atomicity or transactions

According to the Java 17 specification, for **local storage devices**, when a method on a `RandomAccessFile` opened with `"rws"` or `"rwd"` returns successfully, the changes within that method's synchronization scope have been written to the device. For **non-local devices** (such as certain network file systems), the API **makes no such guarantee**.

Regardless of which mode you use:

- A sequence of calls to `seek`, `writeInt`, and `writeLong` **does not become an atomic transaction**. A crash mid-way can still leave a partially updated record.
- Successful synchronization does not replace **locks**, journals, checksums, backups, or recovery protocols when data integrity is critical.
- Synchronization can slow down the application due to increased write I/O. Balance durability and performance based on actual requirements, and measure on the target environment.
- `"rw"` lacks a **per-write** synchronization requirement; that does not mean data definitely stays only in RAM or is guaranteed to be lost after a crash.

### 2.4. Comparison with `FileChannel.force`

With `"rw"`, an application can **perform multiple writes and then request a flush/force at a single point**:

~~~java
try (RandomAccessFile raf = new RandomAccessFile(file, "rw")) {
    raf.seek(0);
    raf.writeInt(10);
    raf.writeInt(20);
    raf.getChannel().force(true); // Requests flushing content + metadata to the device.
}
~~~

- `raf.getChannel().force(true)` corresponds closely to requesting synchronization of **content and metadata**.
- `raf.getChannel().force(false)` corresponds closely to requesting synchronization of **content**.
- `"rws"` and `"rwd"` apply that requirement **to each I/O update**, rather than waiting for an explicit `force` call. The specification notes that the synchronous modes may perform better than calling `force` manually after every operation; this does not dictate which approach is fastest when batching multiple operations.
- `force` is also subject to guarantee limitations when the file does not reside on a local device. Opening a file read-only does not turn `force` into a write operation.

See the official documentation for `RandomAccessFile` and `FileChannel.force(boolean)` at the end of this article.

## 3. Byte pointer: `seek`, `getFilePointer`, `length`, `setLength`

### 3.1. `seek(offset)` only changes position; it does not write

~~~java
raf.seek(12L);                           // Sets the byte offset for the next I/O operation.
long position = raf.getFilePointer();   // 12
long size = raf.length();                // Actual size of the file.
~~~

If you call `seek(1000)` when the file is only 20 bytes long, **no bytes are added yet**. Only when you actually **write** past that position can the file grow. The bytes between the old data and the newly written region should not be relied upon by the application unless the data format explicitly defines or initializes them.

- Offsets are measured in **bytes**, starting at `0`—not character, line, or record indices.
- `seek(-1)` is invalid and throws `IOException`.
- `read()` at end-of-file returns **`-1`**; `readInt()`, `readLong()`, and `readFully(...)` throw **`EOFException`** when fewer than the required bytes remain.
- `read(byte[])` may read **fewer bytes than requested**. If you need exactly N bytes or an EOF error, use `readFully(buffer)`.

### 3.2. Reading/writing primitive types and byte order

`RandomAccessFile` supports `readInt`, `readLong`, `readBoolean`, `readDouble`, etc., and `writeInt`, `writeLong`, `writeBoolean`, `writeDouble`, etc.

~~~java
raf.seek(0);
raf.writeInt(0x01020304);  // Writes exactly four bytes: 01 02 03 04.
raf.seek(0);
int number = raf.readInt(); // 0x01020304.
~~~

Multi-byte `DataInput`/`DataOutput` methods use **big-endian** byte order. Typical sizes: `byte` = 1, `short` = 2, `int` = 4, `long` = 8 bytes. Do not treat `writeInt(1000)` as writing the text string `"1000"` into the file.

**Character strings:** `writeUTF` writes a length prefix (2 bytes) followed by content encoded in `DataOutput`'s **modified UTF-8**, so it must be read back using `readUTF` in the matching format; this is not raw UTF-8 meant to be opened in a text editor. The data encoded in a single `writeUTF` call is limited by a length representable in **2 unsigned bytes** (at most 65,535 bytes of modified UTF-8). `writeChars` writes each UTF-16 code unit as 2 bytes, while `writeBytes` discards the high byte of each `char`; neither should be used casually to write Vietnamese/Unicode text to a text file. For standard UTF-8 text formats, explicitly encode strings with `StandardCharsets.UTF_8` and store the length or use a consistent framing protocol when reading.

### 3.3. `setLength(newLength)`: truncating/extending a file

`setLength(0)` empties the file; `setLength(8)` keeps only the first 8 bytes when the file is longer than 8 bytes. If the length is increased, **the contents of the newly added bytes are unspecified**, so do not assume they are initialized to any particular value for your application.

When `setLength(newLength)` returns, the file pointer is **clamped so it does not exceed `newLength`**; if the previous pointer was greater than the new length, the pointer is moved to the new end of the file. `setLength` requires the file to be opened in a writable mode and may throw `IOException` if the file system cannot perform the operation.

### 3.4. Read, update, append: do not confuse with append mode

~~~java
raf.seek(0);            // Overwrite from the beginning.
raf.writeInt(10);

raf.seek(4);            // Update a region at offset 4.
raf.writeInt(20);

raf.seek(raf.length()); // Manually move pointer to EOF to append.
raf.writeInt(30);
~~~

This snippet illustrates operations on a `raf` instance opened for writing. **There is no valid `"a"` mode** for `RandomAccessFile`. Calling `seek(length())` followed by `write...` is also **not an atomic append** when multiple threads or processes access the same file concurrently.

## 4. Rules for choosing a mode by use case

| Scenario | Usually appropriate choice | Why |
|---|---|---|
| Inspecting headers, reading records at known offsets | `"r"` | Prevents accidental writes through the instance |
| Creating/updating working files whose contents can be regenerated | `"rw"` | Flexible read/write, low per-operation synchronization overhead |
| Overwriting existing data regions; requiring per-update data sync | `"rwd"` | Guarantees content synchronization on local devices |
| Creating records that grow the file/change metadata; requiring stricter sync | `"rws"` | Synchronizes both content and metadata |
| Batching multiple writes together | `"rw"` + `getChannel().force(...)` | Lets you choose when to request synchronization, while designing your own error/crash handling |

**No single mode is best for every problem.** Choose based on durability requirements, failure models, device characteristics, and recovery needs. If you only need sequential text reading/writing, `Files.newBufferedReader`, `Files.newBufferedWriter`, or stream APIs may be more straightforward.

## 5. Runnable Java 17+ program: overwrite, append, truncate, and `r` mode

Save the file with the exact name **`RandomAccessFileModesDemo.java`**:

~~~java
import java.io.IOException;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Path;

public class RandomAccessFileModesDemo {
    public static void main(String[] args) throws IOException {
        Path file = Files.createTempFile("raf-modes-demo-", ".bin");

        try {
            try (RandomAccessFile raf =
                         new RandomAccessFile(file.toFile(), "rw")) {
                raf.writeInt(10); // Offset 0..3
                raf.writeInt(20); // Offset 4..7
                System.out.println("initial: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                raf.seek(4);
                raf.writeInt(99); // Replace the second int without changing file length.
                System.out.println("update: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());

                raf.seek(0);
                System.out.println("values: " + raf.readInt()
                        + ", " + raf.readInt());

                raf.seek(raf.length()); // Move pointer to EOF.
                raf.writeByte(7);       // Append 1 byte.
                System.out.println("append: length=" + raf.length());

                raf.setLength(8);       // Truncate the appended byte.
                System.out.println("truncate: length=" + raf.length()
                        + ", pointer=" + raf.getFilePointer());
            }

            try (RandomAccessFile reader =
                         new RandomAccessFile(file.toFile(), "r")) {
                System.out.println("read-only: " + reader.readInt()
                        + ", " + reader.readInt());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Compile and run from the directory containing the source file:

~~~bash
javac RandomAccessFileModesDemo.java
java RandomAccessFileModesDemo
~~~

**Expected stdout when all I/O succeeds:**

~~~text
initial: length=8, pointer=8
update: length=8, pointer=8
values: 10, 99
append: length=9
truncate: length=8, pointer=8
read-only: 10, 99
~~~

Explanation:

1. Two `writeInt` calls write 8 bytes; the pointer ends at offset 8.
2. `seek(4)` moves the pointer back to the start of the second integer; `writeInt(99)` overwrites 4 bytes, keeping the length at 8.
3. `seek(0)` and two `readInt` calls recover the values `10`, `99`.
4. `seek(length())` positions at offset 8; `writeByte(7)` appends one byte, making the total length 9.
5. `setLength(8)` truncates the extra byte; the pointer, which was at offset 9, is clamped to 8.
6. Closing the `"rw"` instance and reopening with `"r"` still reads both numbers; `"r"` does not allow writes.

`try-with-resources` ensures `close()` is called upon exiting the block, even if an exception occurs. Using a dedicated temporary file avoids overwriting user data. If an I/O error occurs, the program may not print all of the lines above and will throw an exception; this behavior must be handled in real applications.

## 6. Using offsets for fixed-size records

Suppose a file stores each record as:

~~~text
Record 0: [id: int (4 bytes)] [balanceCents: long (8 bytes)] = 12 bytes
Record 1: [id: int (4 bytes)] [balanceCents: long (8 bytes)] = 12 bytes
Record 2: [id: int (4 bytes)] [balanceCents: long (8 bytes)] = 12 bytes
...
~~~

The byte offset of record `i` (**0-based**) is `i * 12`. To read and update the balance of the third record (`i=2`), start at offset 24; the `balanceCents` field is located at offset 28.

This snippet can be placed into a utility class; it assumes the file follows the binary layout described above:

~~~java
private static final int RECORD_SIZE =
        Integer.BYTES + Long.BYTES; // 12

static long readBalance(RandomAccessFile raf, long index)
        throws IOException {
    if (index < 0) {
        throw new IllegalArgumentException("index must be >= 0");
    }
    long offset = Math.multiplyExact(index, RECORD_SIZE);
    if (offset > raf.length() - RECORD_SIZE) {
        throw new java.io.EOFException("record does not exist");
    }
    raf.seek(offset + Integer.BYTES);
    return raf.readLong();
}

static void updateBalance(RandomAccessFile raf, long index, long cents)
        throws IOException {
    if (index < 0) {
        throw new IllegalArgumentException("index must be >= 0");
    }
    long offset = Math.multiplyExact(index, RECORD_SIZE);
    if (offset > raf.length() - RECORD_SIZE) {
        throw new java.io.EOFException("record does not exist");
    }
    raf.seek(offset + Integer.BYTES);
    raf.writeLong(cents);
}
~~~

**Notes for proper usage:**

- Validate negative indices; use `Math.multiplyExact` to prevent **integer overflow** when computing byte offsets.
- Perform bounds checking before updating so you do not accidentally extend the file at an invalid offset. Records are 0-indexed.
- `updateBalance` requires the file to be opened in `"rw"`, `"rwd"`, or `"rws"`; a read-only `"r"` instance will fail to write.
- Define a consistent layout (field order, byte sizes, endianness, version), and avoid using `String.length()` to compute offsets for variable-length UTF-8 strings.
- Writing an 8-byte `long` **is not a transaction** across the remaining fields; consider checksums, write-ahead logs, or update strategies when data is critical.
- The snippet above provides no concurrency locking; if multiple actors update the same record, appropriate synchronization must be added.

If records have variable sizes (such as UTF-8 strings of varying lengths), `i * RECORD_SIZE` cannot be used; you need an **offset index** or a format with explicit length fields.

## 7. Concurrency, `FileChannel`, locks, and operational risks

### 7.1. The pointer is shared state within the same instance

On a single `RandomAccessFile` instance, calling `seek` followed by `read`/`write` is **a sequence of actions**, not an application-level atomic operation. For example:

~~~text
Thread A: seek(100)
Thread B: seek(200)
Thread A: writeInt(42)  // May write starting at offset 200 without coordination.
~~~

Avoid sharing the same instance across multiple threads without access control. Across multiple processes, `synchronized` within a single JVM cannot protect against other processes. You may consider `FileChannel.lock()`/`tryLock()`, but you must understand lock scope, support, and OS semantics; a file lock **is not** a transaction, and some systems only enforce advisory locking.

### 7.2. `RandomAccessFile.getChannel()` shares the position

`getChannel()` returns a `FileChannel` attached to the same file. **`channel.position()` and `raf.getFilePointer()` represent the same logical position**: moving one changes the position of the other. Changing the file size through either one also affects the other.

Therefore, if you mix `raf.seek(...)` and `channel.position(...)` in the same processing flow, you must maintain strict rules for controlling the pointer. Closing the `RandomAccessFile` also closes its associated channel; conversely, closing the channel causes the corresponding `RandomAccessFile` stream to close as well.

### 7.3. Error handling and data protection rules

- Use `try-with-resources` to close file handles; do not keep files open indefinitely.
- Catch `EOFException` separately when reading a record with insufficient bytes; distinguish it from `IOException` caused by permissions, hardware, or file corruption.
- Use trusted paths and check permissions before allowing a user-chosen file to be opened for writing. Opening `"rw"` on an existing file can overwrite data starting right at offset 0.
- Do not rely on `"rws"`/`"rwd"` to automatically prevent **race conditions**, duplicate writes, partial records, file format corruption, or multi-step writes that require rollback.
- If concurrent appends across multiple threads/processes are required, design an explicit lock/protocol or choose an API with proper append guarantees rather than treating `seek(length())` + `write` as atomic.

## 8. Common misconceptions and how to fix them

| Misconception | Correct understanding |
|---|---|
| "`RandomAccessFile` is only for random reads" | It can both **read and write** when opened with `rw/rws/rwd`. |
| "`rw` means read/write and always appends" | `rw` specifies access permission; the write position is determined by the **file pointer**. |
| "Opening with `rw` clears the old file" | It does not auto-truncate; only `setLength(0)` or writing at specific offsets alters existing data. |
| "`seek(1000)` makes the file 1000 bytes long" | `seek` only moves the pointer; the file grows when written to (or via `setLength`). |
| "`rwd` also synchronizes file metadata" | `rwd` requires synchronizing **content**; `rws` requires **content + metadata**. |
| "`rws` turns multiple writes into a transaction" | There is no transaction/atomicity guarantee across multiple calls. |
| "`readInt` reads integers written as ASCII digits" | `readInt` reads **4-byte big-endian binary** values. |
| "`read(byte[])` always fills the entire buffer" | It may read fewer bytes; use `readFully` when an exact byte count is required. |
| "`writeUTF` writes standard raw UTF-8" | It writes **modified UTF-8 with a 2-byte length prefix**, which must be read with `readUTF`. |
| "Obtaining a channel gives an independent pointer" | The channel and `RandomAccessFile` **share the same position**. |
| "`rwd/rws` guarantees data on a network FS is always crash-safe" | Device-write guarantees are specified for **local storage**; remote file systems do not carry the same guarantee. |

## 9. Self-check

1. Open a 100-byte file with `"rw"`, call `seek(20)`, then `writeInt(123)`. New size? **100 bytes** (overwrites bytes 20–23); pointer is at **24**.
2. Open a new file with `"rw"`, then call `writeLong(5L)`. Size? **8 bytes**, pointer at **8**.
3. A file is currently 8 bytes long. Call `seek(100)` without writing. `length()`? **8**, while `getFilePointer()` is **100**.
4. Open a file with `"r"` only, then call `writeByte(1)`. What happens? **`IOException`**.
5. In which mode does Java require synchronizing both content and metadata on each update? **`"rws"`**.
6. How does `"rwd"` primarily differ from `"rw"`? **`"rwd"` requires synchronous content updates on every write**, whereas `"rw"` does not.
7. After a series of `write...` calls in `"rw"`, if you want to request synchronization of both content and metadata before continuing, what do you use? **`raf.getChannel().force(true)`**.
8. Two threads share the same `RandomAccessFile`, each calling `seek` then `write`. Is this automatically thread-safe? **No**; coordination is required to preserve the correctness of the pointer and write target.

## 10. Official documentation

- [Java SE 17 — RandomAccessFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/RandomAccessFile.html): four modes, `seek`, `setLength`, `getFilePointer`, `read`/`write`.
- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): `force(boolean)`, `position`, file locks, and synchronization limits.
- [Java SE 17 — DataInput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInput.html) and [DataOutput](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html): binary layout, big-endian, `readFully`, modified UTF-8.
