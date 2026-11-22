# Copying Binary Files with a Bounded Buffer in Java Core I/O

## 1. Practice Objectives

This exercise requires **copying every byte of a binary file accurately** from a source path to a destination path, **without reading the entire file into memory**. The file may be a few bytes or many gigabytes in size; the program uses only a single fixed-size buffer, reusing it until EOF is reached.

Skills to master:

1. Distinguishing byte copying from text reading/writing and charset decoding.
2. Using `FileChannel`, `ByteBuffer`, `clear()`, `flip()`, and `hasRemaining()`.
3. Reading data in chunks, interpreting the return value of `read()` accurately, and not confusing `0` with EOF `-1`.
4. **Handling partial writes**: a single `write()` call is not required to write all pending data.
5. Requiring only **O(B)** memory, where `B` is the buffer capacity, independent of file size.
6. Closing channels upon completion or error; avoiding unintended overwriting of the destination.
7. Verifying both the **byte count** and **content** of the two files.
8. Knowing when to use `Files.copy`, traditional streams, `FileChannel.transferTo()`, or a temporary-file write design for greater safety.

Context: **Java Core - io → Practical Exercises → Copying binary files with a bounded buffer**. The article includes a **complete Java 17+ program**, with compile/run commands and deterministic stdout.

## 2. Why Not Use `Files.readAllBytes()` for Large Files?

The following simple approach is suitable for testing small files, but it is not a bounded-memory streaming solution:

```java
byte[] all = Files.readAllBytes(source);
Files.write(destination, all);
```

This is an illustrative snippet; it requires importing `java.nio.file.Files` and two appropriate `Path` variables.

Drawbacks:

- `readAllBytes()` attempts to load the **entire file content** into a single Java array, causing heap demand to grow with file size.
- Java arrays have an `int` index limit, so they cannot serve as an arbitrary container for multi-GiB files.
- Prone to `OutOfMemoryError` when files are large or multiple copy operations run concurrently.
- Each execution can allocate a huge array, increasing GC pressure and competing for memory with other work.

A **bounded buffer** solves this problem with a loop:

```text
Source (may be very large)
  │
  │ read up to B bytes/pass
  ▼
┌──────────────────────────┐
│ Fixed ByteBuffer: B      │
└──────────────────────────┘
  │
  │ write all bytes actually received
  ▼
Destination

Repeat until read() returns -1.
```

For example, a 10,257-byte file with a 4,096-byte buffer capacity may require multiple read passes. The buffer always has a capacity of only 4,096 bytes. You must not assume the actual number of passes is exactly 3, because `read` can return fewer bytes than capacity; the program must handle every valid read pass.

**Conclusion:** there is no need to allocate an array equal to the file size, no need to hold all bytes in RAM, and no need to know the file size in advance to complete a sequential copy.

## 3. Binary Copying vs. Text Copying

**Binary copying** must preserve every byte as-is, including:

- Byte `0x00` (NUL);
- Byte `0xFF` (represented in Java `byte` as `-1` when viewed as a signed number);
- Line feed `0x0A`, carriage return `0x0D`;
- Any byte sequence that is not valid UTF-8;
- Headers, compressed data, checksums, trailing zeros, or binary metadata.

Do not do this for binary data:

```java
String text = Files.readString(source);
Files.writeString(destination, text);
```

Reason: **decoding and then re-encoding** based on a charset may be undefined for arbitrary data, alter bytes, or throw an error. In addition, line-based operations may change newline/terminators. `.png`, `.zip`, `.pdf`, `.class`, `.dat`, executable files, and custom binary files do not need to pass through `String`.

**Rule:** take bytes from the source and write those exact bytes to the destination. If the requirement is **encoding conversion**, that is a different problem and the result is no longer a byte-for-byte copy.

## 4. Essential Java NIO Components

| Component | Role | Must Remember |
| --- | --- | --- |
| `Path` | File path | Distinguish source and destination; check overwrite policy |
| `FileChannel` | Channel capable of reading/writing bytes and managing file position | `read`/`write` return the number of bytes actually transferred |
| `ByteBuffer` | Fixed byte region with `position/limit/capacity` state | Will not know what the "new bytes" are if state is misused |
| `buffer.clear()` | Prepares buffer for **writing from channel into buffer** | Does not erase old bytes in backing storage |
| `buffer.flip()` | Prepares buffer for **reading from buffer out to destination channel** | Sets `limit` to the number of bytes received |
| `buffer.hasRemaining()` | Whether there are bytes not yet consumed by the destination channel | Mandatory for handling partial writes |
| `StandardOpenOption.READ` | Opens source for reading only | Does not require permission to modify source |
| `StandardOpenOption.CREATE_NEW` | Creates a new destination, fails if the name already exists | Prevents accidental overwriting |
| `StandardOpenOption.WRITE` | Opens destination for writing | Paired with destination creation policy |

**Important warning:** `FileChannel.read(ByteBuffer)` may return a positive number of bytes smaller than the initial `buffer.remaining()`. `FileChannel.write(ByteBuffer)` may also consume fewer bytes than remain. Loops must rely on **actual return counts** and buffer state, not on an expectation that a single read/write completes an entire chunk.

## 5. ByteBuffer State Flow in One Pass

Suppose the buffer has capacity 8 and this pass only reads 3 bytes `A`, `B`, `C`.

```text
Newly allocated / after clear():
  position=0, limit=8, capacity=8
  [ _ _ _ _ _ _ _ _ ]

After source.read(buffer) returns 3:
  position=3, limit=8
  [ A B C ? ? ? ? ? ]
        ^
        position

After buffer.flip():
  position=0, limit=3
  [ A B C | bytes beyond limit are invalid for this pass ]

During destination.write(buffer):
  May write 1 byte, then 2 bytes;
  or write all 3 bytes in one call.
  When done: position=3, limit=3, hasRemaining()=false.

Next pass:
  clear() → position=0, limit=8;
  buffer is reused, not reallocated.
```

Do not call `clear()` while the buffer still has bytes not yet written to the destination. Doing so **loses track of the remaining data**; on the next pass the source may overwrite bytes that have not finished copying.

Conversely, do not forget `clear()` before the next source read pass. If the buffer stays at `position==limit`, it has `remaining()==0`, causing reads to make no progress even though the source may still have data.

## 6. Standard Algorithm: read → flip → write all → repeat

```text
buffer = allocate(fixedCapacity)
totalCopied = 0

open source READ
open destination CREATE_NEW + WRITE

loop:
    buffer.clear()
    n = source.read(buffer)

    if n == -1:
        break                  # EOF of source file
    if n == 0:
        apply no-progress policy
        do not treat as EOF

    buffer.flip()              # Only the n new bytes are valid
    while buffer.hasRemaining():
        written = destination.write(buffer)
        if written == 0:
            apply no-progress policy
            do not discard unwritten bytes

    totalCopied += n

close both channels
verify size and content when needed
```

### 6.1. Why Must We Loop on `hasRemaining()`?

`destination.write(buffer)` advances `buffer.position()` by the **exact number of bytes written**. If the destination only accepts part of it, the remainder stays in the buffer and can be written next. The `hasRemaining()` condition keeps the loop running until **the entire chunk has been transferred**.

Incorrect code:

```java
buffer.flip();
destination.write(buffer); // May write partially!
buffer.clear();            // Unwritten portion has lost its state.
```

Correct code:

```java
buffer.flip();
while (buffer.hasRemaining()) {
    int written = destination.write(buffer);
    if (written == 0) {
        throw new IOException("No progress while writing");
    }
}
```

This is an illustrative snippet inside a method, assuming `ByteBuffer buffer` and `FileChannel destination` already exist, along with `import java.io.IOException`. For a `FileChannel` writing to a regular file in common scenarios, `0` while bytes remain is abnormal; this exercise chooses to **report an error** instead of spinning infinitely. For non-blocking sockets, `write()==0` can be normal, and `Selector`/`OP_WRITE` or an appropriate wait mechanism must be used rather than throwing an error by default.

### 6.2. Why Is `read()==0` Different from EOF?

- `n > 0`: the source transferred **n bytes**, even if n is smaller than capacity.
- `n == 0`: the call transferred no bytes, **not asserting that the source is exhausted**.
- `n == -1`: the source reports **end-of-stream**.
- Exception: an actual I/O error, which must not be silently treated as EOF.

In this exercise with `FileChannel` and a positive-capacity buffer that is always cleared with `clear()`, `read()==0` is treated as a **no-progress error** to avoid a CPU-burning loop. If implemented on a non-blocking `SocketChannel`, this policy must change: `0` can be a completely valid situation while waiting for data.

## 7. Complete Java 17+ Program: Copying a Binary File with 4 KiB

The example below:

1. Creates a temporary directory.
2. Creates a **10,257-byte** source file with a deterministic binary pattern containing many values including `0x00` and `0xFF`.
3. Copies using **one reused 4,096-byte `ByteBuffer`**.
4. Opens the destination file with `CREATE_NEW`, so an existing file is not silently overwritten.
5. Verifies `Files.size()` and `Files.mismatch()` after copying finishes.
6. Prints results independent of temporary file names.
7. Closes streams/channels via `try-with-resources` and cleans up temporary files in `finally`.

Create the file **`BoundedBinaryCopyDemo.java`**:

```java
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class BoundedBinaryCopyDemo {
    private static final int BUFFER_BYTES = 4096;
    private static final int FILE_BYTES = 10_257;
    private static final int MAX_BUFFER_BYTES = 1024 * 1024;

    static void createFixture(Path source) throws IOException {
        byte[] block = new byte[257];
        for (int i = 0; i < block.length; i++) {
            block[i] = (byte) ((i * 31 + 7) & 0xFF);
        }

        try (OutputStream out = Files.newOutputStream(
                source, StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            int remaining = FILE_BYTES;
            while (remaining > 0) {
                int n = Math.min(remaining, block.length);
                out.write(block, 0, n);
                remaining -= n;
            }
        }
    }

    static long copy(Path source, Path destination, int capacity)
            throws IOException {

        if (capacity <= 0 || capacity > MAX_BUFFER_BYTES) {
            throw new IllegalArgumentException(
                    "Buffer must be between 1 and " + MAX_BUFFER_BYTES);
        }
        if (!Files.isRegularFile(source, LinkOption.NOFOLLOW_LINKS)) {
            throw new IOException("Source is not a regular file");
        }

        ByteBuffer buffer = ByteBuffer.allocate(capacity);
        long totalCopied = 0L;

        try (FileChannel in = FileChannel.open(
                     source, StandardOpenOption.READ);
             FileChannel out = FileChannel.open(
                     destination, StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            while (true) {
                buffer.clear();
                int n = in.read(buffer);

                if (n == -1) {
                    break;
                }
                if (n == 0) {
                    throw new IOException(
                            "Read made no progress");
                }

                buffer.flip();
                while (buffer.hasRemaining()) {
                    int written = out.write(buffer);
                    if (written == 0) {
                        throw new IOException(
                                "Write made no progress");
                    }
                }
                totalCopied += n;
            }
        }
        return totalCopied;
    }

    public static void main(String[] args) throws IOException {
        Path directory =
                Files.createTempDirectory("bounded-binary-copy-");
        Path source = directory.resolve("source.bin");
        Path destination = directory.resolve("destination.bin");

        try {
            createFixture(source);

            long copied = copy(source, destination, BUFFER_BYTES);
            boolean identical =
                    Files.mismatch(source, destination) == -1L;

            System.out.println("Source bytes: " + Files.size(source));
            System.out.println("Copied bytes: " + copied);
            System.out.println("Target bytes: "
                    + Files.size(destination));
            System.out.println("Buffer capacity: " + BUFFER_BYTES);
            System.out.println("Content identical: " + identical);
        } finally {
            Files.deleteIfExists(destination);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac BoundedBinaryCopyDemo.java
java BoundedBinaryCopyDemo
```

Expected stdout when the filesystem supports creating/reading/writing and deleting temporary files:

```text
Source bytes: 10257
Copied bytes: 10257
Target bytes: 10257
Buffer capacity: 4096
Content identical: true
```

### 7.1. Step-by-Step Program Explanation

**A. The source data is genuinely binary.** The `block` initialization loop computes `(i * 31 + 7) & 0xFF` and casts to `byte`. Across different indices, the block can contain byte 0, byte 255, and many values that have no meaning as text characters. `createFixture()` writes all 10,257 bytes using only a 257-byte array without allocating an array equal to the entire file.

**B. Buffer size is controlled.** The `copy` method takes `capacity`, checks the positive bound and 1 MiB maximum, and then allocates **one** `ByteBuffer.allocate(capacity)` before the read loop. In the demo call, capacity is exactly 4,096.

**C. The source is opened read-only.** `FileChannel.open(source, READ)` does not require permission to modify the source content. The example checks `isRegularFile(..., NOFOLLOW_LINKS)` to reject a symbolic link source at the initial validation stage. However, this is **not an absolute TOCTOU defense** if another actor can change the path between checking and opening the file.

**D. The destination is newly created.** `CREATE_NEW` rejects an existing destination filename (even if it is a symbolic link, per API rules). The demo does not overwrite an existing file. If an error occurs after creating the destination, **a partially copied destination file may already exist**; the `finally` block in the demo proactively deletes the temporary files. Real applications must define their own cleanup policy.

**E. `n` is not a byte value.** `in.read(buffer)` returns the number of bytes actually received. If byte `0xFF` or `0x00` is read, `n` is still a **count**, not `-1` or `0` corresponding to the content.

**F. `flip()` then write completely.** `buffer.flip()` restricts the valid region to exactly `n` bytes. `while (buffer.hasRemaining())` handles every case where the destination writes only a portion. If the first write consumes 1 KiB of a 4 KiB chunk, the remaining 3 KiB stay preserved for the next pass.

**G. Using `long` for the total.** `totalCopied` is `long`, so it is not limited to 2 GiB like `int`; this is a safe counter for large files. `capacity` remains `int` because the `ByteBuffer` API uses an `int` capacity.

**H. Verifying the result.** `Files.size()` reflects the file size, while `Files.mismatch(source,destination)` returns `-1L` when no differing byte is found; if they differ, it returns the position of the first mismatched byte. Comparing sizes alone **is not sufficient** to confirm identical content. `Files.mismatch()` has been available since Java 12 and works on Java 17.

**I. Closing resources.** Both `FileChannel` instances are closed even if `read` or `write` throws `IOException`. Only after closing does the demo verify and delete the temporary data. Note that deletion can also throw `IOException` depending on permissions and filesystem state.

## 8. Invariants to Prove the Algorithm Loses No Bytes

In a single read pass, let:

- `p`: total source bytes read before the pass;
- `n`: number of bytes returned by `in.read(buffer)`;
- `w`: total bytes actually written to the destination from the buffer in this pass.

Before calling `flip()`, `buffer.position()` has increased by `n`. After `flip()`, `limit=n`, `position=0`.

When the `while (hasRemaining())` loop finishes normally:

```text
w == n
buffer.position() == buffer.limit() == n
totalCopied_new == p + n
```

Therefore, every byte of the read chunk is transferred to the destination **exactly once** according to its buffer position, provided no external actor interferes with the channel/file. Afterward, the loop resets the buffer to receive the next source bytes.

At EOF:

```text
in.read(buffer) == -1
→ no new bytes
→ no further flip/write needed
→ exit read loop
```

If the source file contains `N` bytes and does not change during copying, on success `totalCopied == N`, the destination file contains the bytes in exact order, and `Files.mismatch(source,dest) == -1L`.

**Do not infer** that `n < capacity` means EOF. For example, `n=1` when capacity=4096 is still a successful data read; continue until `-1`.

## 9. Why Does `CREATE_NEW` Matter?

By default, if certain write-opening APIs are used with other options, an application may create/overwrite/truncate the destination file, causing data loss.

Policy comparison:

| Destination Open Option | Significant Behavior |
| --- | --- |
| `CREATE_NEW, WRITE` | Creates only a new file; fails if the name already exists, preventing accidental overwrite |
| `CREATE, WRITE, TRUNCATE_EXISTING` | May create or wipe old file content; use only when the application has explicit overwrite authority |
| `APPEND, WRITE` | Appends data to the end of the file; **unsuitable** for a full-replacement copy requirement |
| `READ` | Read-only, not used for output |
| `SYNC`/`DSYNC` or `force()` | Relates to durability synchronization levels, does not replace content verification |

**Do not copy onto the source file itself.** If you open the source first and then open the destination with `TRUNCATE_EXISTING` when they are actually the same file, truncating can destroy the source data. In the demo, `CREATE_NEW` together with a new destination path avoids this simple case.

In real applications, if source and destination could collide via hard links, symbolic links, or equivalent paths, use `Files.isSameFile()` when both already exist and design a race-control policy. Pre-operation checks are not strong enough if another actor can modify the directory tree concurrently.

## 10. `InputStream` / `OutputStream` Version Using `byte[]`

NIO is not mandatory. If the goal is simply copying bytes with a bounded buffer, the stream API can be easier to read:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

static long copyWithStreams(
        Path source, Path destination, int bufferBytes)
        throws IOException {

    if (bufferBytes <= 0 || bufferBytes > 1024 * 1024) {
        throw new IllegalArgumentException("Invalid buffer size");
    }

    byte[] buffer = new byte[bufferBytes];
    long total = 0L;

    try (InputStream in = Files.newInputStream(source);
         OutputStream out = Files.newOutputStream(
                 destination, StandardOpenOption.CREATE_NEW,
                 StandardOpenOption.WRITE)) {

        int n;
        while ((n = in.read(buffer)) != -1) {
            if (n == 0) {
                throw new IOException("Read made no progress");
            }
            out.write(buffer, 0, n);
            total += n;
        }
    }
    return total;
}
```

This is a **method to place inside a class**, not a standalone program with `main`. It shares the same characteristics of allocating **one fixed `byte[]`**, using `long` for counting bytes, opening a new destination, and closing streams automatically.

**Important difference:** `OutputStream.write(byte[], 0, n)` has a contract to write all `n` bytes or throw an exception; the API does not return a partial write count like `FileChannel.write(ByteBuffer)`. Therefore, no `hasRemaining()` loop is needed at the `OutputStream` layer, though you still must handle `IOException`, partial destination corruption, and timely flush/close.

If you only need to transfer bytes, `InputStream`/`OutputStream` is a reasonable choice; use `FileChannel` to practice `ByteBuffer`/NIO mechanics deeply, positional access, or workload-specific optimizations when measured.

## 11. `Files.copy()` and Why We Still Learn Buffered Copying

Java already provides:

```java
long copied = Files.copy(
        sourceInputStream, destinationPath);
```

Here `sourceInputStream` is an open `InputStream` and `destinationPath` is a `Path`. This approach is convenient for many use cases. With `Files.copy(Path,Path,CopyOption...)`, the API also supports direct file copying, symbolic link handling rules, and provider-dependent attribute copying options.

Yet in this **bounded-buffer exercise**, we manage the read/write loop ourselves because we want to:

- Specify the application code's buffer size;
- Count bytes and monitor progress chunk by chunk;
- Compute checksums/hashes while copying;
- Enforce read/write quotas, deadlines, cancellation, or rate limits;
- Handle partial writes and understand `ByteBuffer` state;
- Compare the performance of different capacities with verification.

Do not assume `Files.copy()` consumes RAM proportional to file size; implementations may use streaming or dedicated optimizations. When **loop control is not needed**, prefer the standard library API over writing an untested custom copy.

## 12. Large Files Over 2 GiB: Avoiding the `int` Limit

A `ByteBuffer` has an `int` `capacity()`, whereas file position and `FileChannel.size()` use `long`. There is no need for a buffer matching the file size.

**Incorrect approach:**

```java
long size = Files.size(source);
ByteBuffer all = ByteBuffer.allocate((int) size);
```

This is an **intentionally wrong** snippet, because `(int) size` can overflow and even a very large positive `int` can exceed the heap budget. A 5 GiB file cannot fit into a single `ByteBuffer` with 5 GiB capacity.

**Correct approach in this exercise:**

```java
final int bufferBytes = 64 * 1024;
ByteBuffer buffer = ByteBuffer.allocate(bufferBytes);
long copied = 0L;

// Each read/write pass processes at most bufferBytes;
// copied increases by actual n and stays long.
```

Empty files, files smaller than the buffer, files not divisible by the buffer size, or files tens of GiB in size all go through **the same logic**. Larger files increase loop iterations and time, not buffer growth with file size.

Also do not use `while (copied < Files.size(source))` as the sole stopping condition: file size may change while reading, and `read()==-1` is the EOF signal of the current channel. If a "byte snapshot at start time" is required, a separate synchronization/immutable-file policy must be designed.

## 13. Choosing Buffer Size by Goal and Measurement

Common starting candidates are **4, 16, 64, 256 KiB, or 1 MiB**; however, there is no single fixed optimal size for every file and system.

| Size | Potential Advantage | Cost to Consider |
| --- | --- | --- |
| 4 KiB | Small, easy to practice, low RAM per job | More I/O passes |
| 16–64 KiB | Often a reasonable testing range for sequential copying | Needs benchmarking on real workloads |
| 256 KiB | Can reduce call count compared to small buffers | Higher memory/connection |
| 1 MiB | Useful if throughput still scales in a specific workload | Not guaranteed faster; increases heap/direct memory |

For example, 1,000 tasks concurrently holding a 64 KiB buffer: total buffer space is about **62.5 MiB**. If 1,000 buffers are each 1 MiB, that is about **1,000 MiB** (nearly 0.98 GiB), not counting objects, sockets, file descriptors, and queues.

Measure:

1. Actual file copy duration (not only source read time);
2. End-to-end MiB/s;
3. Memory and GC when multiple tasks run concurrently;
4. Heap `allocate` vs. `allocateDirect`, if under consideration;
5. Warm-up, OS page cache, device load, p95/p99 latency;
6. Correctness via `Files.mismatch()` or an appropriate checksum.

If a 64 KiB buffer achieves nearly the same throughput as a 1 MiB buffer within margin of error, the smaller configuration can benefit memory usage. **Do not conclude 1 MiB is better just because it is larger.**

## 14. Do Heap and Direct ByteBuffers Affect Correctness?

The line in the program:

```java
ByteBuffer buffer = ByteBuffer.allocate(capacity);
```

can be tested by replacing it with:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(capacity);
```

Both support `clear()`, `flip()`, `hasRemaining()`, `get/put`, and `FileChannel.read/write` under the buffer protocol. If operated correctly, **the copied content is identical**.

Differences:

- Heap buffers may allocate faster and use heap memory.
- Direct buffers typically use off-heap memory; the JVM may optimize native I/O, though it does not promise faster speed across all workloads.
- Direct allocation/deallocation is usually more expensive, so reusing buffers and controlling concurrent buffer count is especially important.
- `buffer.clear()` **does not wipe sensitive data in memory** and does not release direct memory.
- With direct buffers, you must not assume `buffer.array()` can be called.

Choose the buffer type via actual measurement rather than a belief that "direct is always faster".

## 15. How to Verify Byte-for-Byte Equality

### 15.1. Comparing Size

```java
boolean sameSize = Files.size(source) == Files.size(destination);
```

This is useful for detecting under-copying or over-copying, but **not sufficient**: two files with the same byte count can have different content.

### 15.2. `Files.mismatch()` (Java 12+)

```java
long firstMismatch = Files.mismatch(source, destination);

if (firstMismatch == -1L) {
    System.out.println("Identical bytes");
} else {
    System.out.println("Different at offset " + firstMismatch);
}
```

Per the API contract, `-1L` means no bytes differ (and sizes match). If they differ, the method returns the position of the first differing byte, or the length of the shorter file when one file is a prefix of the other.

This is a **snippet to place inside a method** after both files are closed and stable. `Files.mismatch()` is not atomic against concurrent modifications: if another process modifies a file during comparison, the result does not represent an immutable snapshot.

### 15.3. Hashing for Large File Verification or Audit Logs

SHA-256 can be computed via `MessageDigest` while reading each block. Hashing lets you report verification results independently of a byte-by-byte comparison pass, but:

- A hash **does not replace** a source authentication protocol when files come from untrusted parties, unless the expected hash is provided over a trusted channel.
- If computing a digest during copying, pay attention to the checksum of the source just read versus the checksum of the destination after writing, or cross-check with `Files.mismatch()` to catch write-path errors.
- Do not use CRC32 as a tamper-resistant signature.

For testing the demo or a stable local file, `Files.mismatch()` is an intuitive, direct tool built into JDK 17.

## 16. Error Handling: Incomplete Destination Files

If the program copies 8 MiB and then hits disk full, loses write permission, or is interrupted, **the destination file may contain 8 MiB of incomplete data**. `try-with-resources` closes the channels, but **does not automatically delete a partially copied destination file**.

Three common policies exist:

1. **Delete the destination file on failure:** suitable when we just created a new file and are certain the application owns it.
2. **Write to a temporary file in the same directory and rename upon success:** avoids publishing an incomplete destination under its official name; note that `ATOMIC_MOVE` may not be supported by the provider.
3. **Keep the copied portion to resume:** requires progress metadata, verifying the source is unchanged, offsets, checksums, and handling crash consistency. You cannot simply look at an existing destination file and assume resuming is safe.

### 16.1. Why Use a Temporary File to Publish?

Diagram:

```text
source.bin
   |
   | bounded-buffer copy
   v
destination.bin.part-<random>  (temporary file, same filesystem)
   |
   | verify bytes/size; close channels
   v
Files.move(temp, destination, ATOMIC_MOVE if supported)
```

If copying fails, the application deletes the temp file and the official destination name is never created by this workflow. If copying succeeds, the application **publishes** the file only after verification.

**Note:** `ATOMIC_MOVE` can throw `AtomicMoveNotSupportedException`. Behavior when the target already exists with `ATOMIC_MOVE` varies by provider; do not rely on omitting `REPLACE_EXISTING` as an absolute guarantee against overwriting in every situation. You must decide the existing-target policy and handle race checking/synchronization appropriately. To guarantee data is durable on the device after power loss, also consider `force()`/directory synchronization depending on filesystem/provider.

Writing to a temp file should have clear disk quotas, cleanup, rollback, and logging. A `Files.move()` call by itself does not turn all check/copy steps into a full atomic transaction.

## 17. Filenames, Symbolic Links, and Concurrency Cases

For user-supplied paths:

- Do not allow arbitrary source/destination paths into unauthorized directories; enforce root restrictions, canonicalization, and permissions per your threat model.
- `Files.isRegularFile(path, NOFOLLOW_LINKS)` only checks at a single point in time. If another actor swaps the path to a symlink between check and open, that is **TOCTOU**; safer platform opening mechanisms are needed if input is untrusted.
- `CREATE_NEW` is useful for protecting an existing destination file; a policy is still needed to clean up a newly created file on failure.
- Avoid source and destination being two different names for the **same inode/file**; when both files exist, `Files.isSameFile()` can be used.
- If the source is being modified/truncated by another process while copying, the copy may not match a consistent snapshot. Calling `Files.size()` at one point in time does not solve that.
- `FileLock` can help coordinate within a system, but mandatory/advisory semantics and filesystem support vary. Do not assume it replaces full versioning or quiescence mechanisms.

For local practice, use a **dedicated temporary directory** like the demo. In a real service, clearly decide who is permitted to create/delete source and destination, and when data is considered immutable.

## 18. Edge Cases to Test

| Scenario | Expected Behavior |
| --- | --- |
| Empty source file | `read` returns `-1`; creates empty destination file; `copied=0` |
| 1-byte file | Copies one byte accurately |
| File smaller than buffer | Reads one or more valid passes then EOF, no garbage bytes copied |
| File size is exact multiple of buffer | No extra empty block added; stops at EOF |
| File size not divisible by buffer | Final chunk is shorter, still writes exact byte count |
| File with `0x00`, `0xFF`, invalid UTF-8 data | Copies raw bytes without decoding |
| File larger than 2 GiB | `long totalCopied`; does not allocate by file size |
| Destination already exists | `CREATE_NEW` fails instead of overwriting |
| Source does not exist | I/O/source-check error, no successful copy created |
| Out of disk space mid-copy | Write error; partial destination file needs cleanup |
| A single write writes less than buffer | `hasRemaining()` loop finishes the remainder |
| Source modified during copy | No snapshot guarantee; requires application policy |
| Missing read/write permissions | `IOException` or permission error, resources closed |
| Direct vs. heap | Copies identical content if code is right, performance must be measured |

### 18.1. Adding a Single-Byte Flip Test Yourself

After copying finishes, if you deliberately modify the first byte of the destination file:

```java
try (FileChannel out = FileChannel.open(
        destination, StandardOpenOption.WRITE)) {
    ByteBuffer one = ByteBuffer.wrap(new byte[] {(byte) 123});
    out.write(one, 0L);
}

long mismatch = Files.mismatch(source, destination);
```

This is a **fault-injection snippet**, not part of the main demo program; it assumes the source's first byte is not 123 and the relevant APIs are imported. The `mismatch` result will be the position of the first differing byte (with the demo fixture, the source's first byte is `7`, so `mismatch==0L`). After this test the two files **are no longer identical**; do not use the post-modification result to invalidate the original copy function.

## 19. Common Implementation Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| `readAllBytes()` for multi-GiB files | Exhausts heap or exceeds array limit | Fixed buffer, streaming |
| `new String(bytes)` for binary files | Corrupts/cannot represent data | Copy bytes directly |
| `new byte[(int) Files.size(path)]` | `int` overflow, OOM | Small capacity and `long` total |
| Forgetting `buffer.flip()` | Writes 0 bytes or reads wrong range | `clear` → `read` → `flip` → `write` |
| Calling `write` only once | May lose unwritten remainder | `while (buffer.hasRemaining())` |
| Calling `buffer.clear()` before destination finishes writing | Loses state of remaining bytes | Only clear on the next source read pass |
| Treating `read()==0` as EOF | Stops prematurely on non-blocking channels | Only `-1` is EOF |
| Treating `read() < capacity` as EOF | Misses remaining data | Loop until `-1` |
| Checking only destination size | Wrong content can still have the same size | `Files.mismatch` or hash |
| Opening destination with `TRUNCATE_EXISTING` unintentionally | Wipes old file content | `CREATE_NEW`/explicit overwrite policy |
| Not closing channels on error | File descriptor leaks, unflushed data | `try-with-resources` |
| Not cleaning up partial copy | Corrupted destination mistakenly used | Temp/publish or cleanup |
| Source and destination are the same file | Can corrupt its own content | Check path/identity and ownership |
| Creating a new buffer every read loop | Allocation, GC/native overhead | Reuse a single buffer |
| Claiming a 1 MiB buffer is always fastest | Not grounded in measurement | Benchmark on real workloads |
| Copying a file being modified by another writer | Result is not a guaranteed snapshot | Lock/version/immutable input per policy |

## 20. Practice Exercises and Solutions

**Question 1.** Why can't `BufferedReader.readLine()` be used to copy `.png` or `.zip` files?

**Answer:** It operates on text and charsets and also splits lines; arbitrary binary data does not preserve bytes across decode/encode. Use byte streams or byte channels.

**Question 2.** Source is 10,257 bytes, buffer capacity is 4,096. How many bytes is the final chunk if all previous passes filled the buffer?

**Answer:** `10257 - 2 * 4096 = 2065` bytes. However, in practice previous passes **are not guaranteed** to always fill the buffer, so the algorithm relies on `read()` returning the actual byte count, not on an expected chunk count.

**Question 3.** After `read` returns 3 into a capacity-8 buffer, what `position` and `limit` does `flip()` set?

**Answer:** `position=0`, `limit=3`, so only the three new bytes are used for the write pass.

**Question 4.** After the first `write()`, `buffer.hasRemaining()==true`. Can we call `clear()` right away?

**Answer:** No. You must continue writing the remainder; `clear()` would erase the boundary of unwritten data.

**Question 5.** Does byte `0xFF` cause `FileChannel.read(ByteBuffer)` to return `-1`?

**Answer:** No. `read` returns the number of bytes transferred; `-1` is EOF, not a data byte.

**Question 6.** Why is `Files.size(src)==Files.size(dst)` insufficient to prove a correct copy?

**Answer:** Two files of the same length can have different bytes. Verify with `Files.mismatch(src,dst)` (returns `-1L` if identical) or compare hashes when appropriate.

**Question 7.** For a 5 GiB file, can `long totalCopied` and `ByteBuffer.allocate(65536)` be used?

**Answer:** Yes, if the filesystem and resources permit. Each iteration processes at most 64 KiB; the total bytes are counted in `long`, not `int`.

**Question 8.** What problem does `CREATE_NEW` solve?

**Answer:** It prevents silently opening/truncating an existing destination file. If the destination name already exists, creation fails.

**Question 9.** Why clean up the destination if an error occurs mid-copy?

**Answer:** The destination file may contain only part of the data. Treating it as a complete result would cause users or downstream tasks to read truncated data.

**Question 10.** If we switch from a heap `ByteBuffer` to a direct `ByteBuffer`, is copying guaranteed to be faster?

**Answer:** No. You must benchmark in a real environment; direct memory still consumes resources and has its own allocation/lifecycle costs.

**Question 11.** Does `Files.copy()` always read the entire file into RAM?

**Answer:** No. It is a standard library API that can use streaming/optimized implementations. Writing a manual buffer loop is mainly to learn the mechanics or customize progress, limits, hashing, or transformations.

**Question 12.** The source file is being modified during copying. Does a subsequent `Files.mismatch` guarantee a copy of a snapshot at the start time?

**Answer:** No. Copying and comparing are not atomic with external writers. Data must be protected or version-frozen per business requirements.

## 21. Pre-Production Application Checklist

1. Use byte-transfer APIs (`FileChannel`, `InputStream`, `OutputStream`), never `Reader`/`Writer` for binary data.
2. Set a positive buffer limit fitting the memory budget; allocate **exactly once** and reuse.
3. When reading, check `-1` for EOF; do not treat short reads or `0` as EOF.
4. `clear()` before source read, `flip()` before destination write, `hasRemaining()` to write the full chunk.
5. Use `long` for total byte counts and offsets on large files.
6. Open the source read-only; define the destination policy (CREATE_NEW, overwrite, temp staging).
7. Use `try-with-resources` and handle `IOException`, no-progress, disk full, and interruption.
8. Handle partial output files on failure; publish only after completion and verification if required.
9. Check size and content with `Files.mismatch` or an appropriate checksum; never trust size alone.
10. Ensure source and destination differ, accounting for symlinks/hardlinks and concurrent source modification.
11. Test empty files, 1-byte files, short final chunks, binary data with 0x00/0xFF, large files, and write failures.
12. Measure throughput/latency/memory on real workloads before arbitrarily increasing buffer size.

## Conclusion

Copying binary files safely in terms of **content and memory** requires three principles:

- **Transfer bytes intact**, without decoding or text conversion.
- **Use a bounded buffer and manage state properly**: `clear → read → flip → write until !hasRemaining`.
- **Verify and handle errors deliberately**: EOF, partial writes, existing destinations, partial destination files, changing sources, and byte-for-byte verification.

A fixed buffer of a few KiB to a few hundred KiB, properly reused, can process multi-GiB files without allocating an array sized to the file. The specific size should be chosen via measurement and the application's memory budget.

## Official References

- Java SE 17 — `FileChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html
- Java SE 17 — `ByteBuffer`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 — `ReadableByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/ReadableByteChannel.html
- Java SE 17 — `WritableByteChannel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/WritableByteChannel.html
- Java SE 17 — `Files` (`mismatch`, `copy`, `size`, `newInputStream`): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 — `StandardOpenOption`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/StandardOpenOption.html
- Java SE 17 — `InputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Java SE 17 — `OutputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html
