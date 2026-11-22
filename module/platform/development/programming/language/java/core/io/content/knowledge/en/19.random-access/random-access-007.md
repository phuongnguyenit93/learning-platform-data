# Do Not Share a File Pointer Across Operations Without Coordination

In **random access**, a file can be read or written at any arbitrary position rather than only sequentially from start to finish. Java provides `RandomAccessFile`, `FileChannel`, and `SeekableByteChannel` for this purpose. The easiest mistake to make when multiple operations or threads share a single I/O object is that **the file pointer (current position) belongs to the shared access object**, so one operation can change the position that another operation intends to use.

Practical rule:

> When operations require distinct offsets, use **absolute-position** read/write APIs whenever possible. If you must use a `seek/position → read/write` sequence based on a shared pointer, coordinate the **entire sequence of operations** with a common synchronization mechanism. And even when pointer contention is eliminated, operations overlapping on the same bytes or the same metadata still require data-coordination rules.

This lesson focuses on **correctness when using the file pointer**, the thread-safety limits of the APIs, and how to design verifiable read/write operations. Never assume data "is at the right position" merely because a prior `seek` returned successfully.

## 1. What is a file pointer and how does it differ from other offsets?

**The file pointer / current file position** is the byte position that the next *relative* I/O operation will use. Normally, after successfully reading/writing `n` bytes, the position advances by `n`. Offsets are measured from the start of the file, beginning at `0`, in **bytes**, not Unicode character indices.

Example of an 8-byte ASCII file containing `ABCDEFGH`:

- Position `0`: byte `A`; position `3`: byte `D`; position `8`: immediately after the end of the file (EOF).
- `seek(3)` or `position(3)` only sets the next read/write position; it does not read or write data on its own.
- A subsequent `read` returns one or more bytes and typically advances the current position by the number of bytes actually read.
- With UTF-8, a single Vietnamese character can occupy multiple bytes. `position(3)` does not mean "the fourth character"; positioning at the wrong encoding boundary can split a character in half.

Do not confuse these types of positions:

| Position type | Where does it live? | Meaning |
| --- | --- | --- |
| `RandomAccessFile.getFilePointer()` | State of the `RandomAccessFile` instance / underlying handle | Offset for the next read/write operation via `RandomAccessFile`. |
| `FileChannel.position()` | State of the channel | Offset for `read(ByteBuffer)` or `write(ByteBuffer)` calls that do not pass an explicit offset. |
| `FileChannel.read(dst, long position)` / `write(src, long position)` | Argument of a **single call** | Absolute offset for that call; does not modify `channel.position()`. |
| `ByteBuffer.position()` | State inside the caller's buffer | Index inside `ByteBuffer` where data will be written/read next; **not** a file offset. |

`ByteBuffer` is also mutable state: a single `read` modifies `buffer.position()` even when the file operation is positional. Each task should use its own buffer or enforce buffer ownership rules, rather than coordinating only the file pointer.

## 2. APIs that change or share position

### `RandomAccessFile`

`RandomAccessFile` provides:

- `seek(long pos)`: sets the file pointer before a read/write; `pos` must be non-negative.
- `getFilePointer()`: returns the current byte position.
- `read(...)`, `readFully(...)`, `write(...)`, and primitive read/write methods: use and then update the pointer.
- `length()` / `setLength(...)`: queries/changes file size; size-changing operations can affect the position or data used by other threads.

**Important detail:** `raf.getChannel()` returns a channel tied to the same `RandomAccessFile`. The Javadoc specifies that this channel's position is always equal to `raf`'s file pointer; calling `raf.seek` or reading/writing through `raf` affects `channel.position()`, and relative operations through the channel affect `raf.getFilePointer()`. Never treat them as two independent cursors.

### `FileChannel`

There are two API groups to distinguish:

```java
channel.position(100);     // sets the channel's shared current position
channel.read(buffer);      // reads from current position; advances position
channel.write(buffer);     // writes at current position; advances position

channel.read(buffer, 100); // reads at offset 100; does NOT change channel.position()
channel.write(buffer, 200);// writes at offset 200; does NOT change channel.position()
```

The snippet above is an **API illustration**, assuming `channel` and `buffer` are already declared with appropriate permissions and open mode. Read/write methods may transfer fewer bytes than `buffer.remaining()`; when you need to read/write completely, loop and advance the offset by the number of bytes *actually* processed.

According to the Java 21 `FileChannel` Javadoc, a channel **is safe for use by multiple concurrent threads**. The implementation allows only one operation involving the channel's position or that can change the file size to be in progress at any given time; subsequent operations of the same kind wait until the first completes. Operations with explicit offsets may proceed concurrently, though whether they actually execute in parallel depends on the implementation.

This does **not** mean a sequence `position(x); write(data)` is protected like a transaction, nor does it mean two tasks updating the same file region will preserve application invariants. A "thread-safe API" describes the internal state contract of a single call, whereas **correctness of multi-step operations** is the program's responsibility.

### `SeekableByteChannel` and other sources

`SeekableByteChannel` defines `position()`, `position(long)`, `read`, `write`, `size`, and `truncate`, but does not provide absolute-offset read/write overloads in the interface itself. When working only with `SeekableByteChannel`, do not automatically assume `FileChannel`'s specific thread-safety guarantees apply to every provider. If you must change the pointer before I/O, guard the entire operation group with a shared synchronization mechanism or give each task an independent channel when appropriate.

## 3. How race conditions happen even when every single call is valid

Suppose a `FileChannel` opens a 10-byte file initially containing `abcdefghij`. Two business operations need to write:

- **A** wants to write `XX` at bytes `0..1`.
- **B** wants to write `YY` at bytes `4..5`.

If both use relative calls, a valid interleaving schedule can be:

| Step | Operation | Current position after operation |
| --- | --- | --- |
| 1 | A: `channel.position(0)` | `0` |
| 2 | B: `channel.position(4)` | `4` |
| 3 | A: `channel.write(XX)` | `6` if all 2 bytes are written |
| 4 | B: `channel.write(YY)` | `8` if all 2 bytes are written |

A accidentally writes at `4..5` and B writes at `6..7`. Under this schedule the result is `abcdXXYYij`, different from `XXcdYYghij` that the two operations intended. Both positioning calls and both write calls can complete cleanly without throwing any exception.

This schedule is an **illustrative model of one interleaving**, not a claim about which thread the scheduler will definitely run first. The root cause is that setting the position and performing I/O are **two separate calls**. Synchronizing each call individually does not create atomicity for the sequence.

Common variants:

1. One thread calls `seek(start)`, another thread calls `seek(otherStart)`, and the first thread reads the wrong block.
2. One thread reads a header with `readInt()`, another thread writes data and moves the pointer, causing the subsequent payload read to start at the wrong position.
3. One helper method uses `RandomAccessFile` while another uses `raf.getChannel()`, mistakenly assuming they are two separate cursors when they actually share one.
4. Two threads share a single `ByteBuffer`, so `flip`, `clear`, or buffer `position` interleave even though each call's file offset is absolute.
5. A program computes `long end = channel.size()` and lets multiple threads write at `end`, causing threads to compute the same offset and overwrite one another.

Adding `Thread.sleep(...)`, changing thread counts, or observing "it ran fine" many times does not prove the code is race-free. Thread scheduling, OS caching, file systems, and machine load can cause the bug to appear and disappear unpredictably.

## 4. Runnable example: `RandomAccessFile` and `getChannel()` sharing a pointer

Create a file named `PointerCoupling.java`:

```java
import java.io.RandomAccessFile;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

public class PointerCoupling {
    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("raf-position-", ".dat");
        try {
            Files.writeString(file, "ABCDE", StandardCharsets.US_ASCII);
            try (RandomAccessFile raf = new RandomAccessFile(file.toFile(), "rw")) {
                FileChannel channel = raf.getChannel();
                raf.seek(1);
                System.out.println("channel-after-seek=" + channel.position());

                ByteBuffer next = ByteBuffer.allocate(1);
                channel.read(next);
                next.flip();
                System.out.println("relative-byte=" + (char) next.get());
                System.out.println("raf-after-relative=" + raf.getFilePointer());

                ByteBuffer atFour = ByteBuffer.allocate(1);
                channel.read(atFour, 4);
                atFour.flip();
                System.out.println("absolute-byte=" + (char) atFour.get());
                System.out.println("raf-after-absolute=" + raf.getFilePointer());
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

Compile/run with Java 17+:

```bash
javac --release 17 PointerCoupling.java
java PointerCoupling
```

Output on a normal file system:

```text
channel-after-seek=1
relative-byte=B
raf-after-relative=2
absolute-byte=E
raf-after-absolute=2
```

Step-by-step explanation:

- `raf.seek(1)` sets `channel.position()` to `1`.
- `channel.read(next)` reads `B` at position `1` and advances the shared pointer to `2`.
- `channel.read(atFour, 4)` reads `E` at absolute offset `4`, so the shared pointer **stays at `2`**.
- `next.flip()` and `atFour.flip()` adjust each buffer's position to read the loaded byte; they do not adjust the file pointer.

To keep the program concise, the example operates on a 5-byte temporary file with no other writers and reads 1 byte at a time. In applications handling files whose size may change or involving unpredictable sources, check the `read` result and EOF (`-1`), and handle short reads.

**Lifecycle note:** `RandomAccessFile` and the channel from `getChannel()` are coupled; closing `raf` also closes its associated channel and vice versa. Never hand this channel to a task that needs to outlive the owner's lifecycle. If one thread closes the channel while another thread is performing I/O, handle closed/asynchronous cancellation exceptions per the contract rather than blaming the pointer.

## 5. Preferred approach: dedicated offsets with `FileChannel.read/write(ByteBuffer, long)`

When tasks already know the offsets they need to process, the positional overloads are a simple way to eliminate **current position** contention:

```java
int count = channel.read(targetBuffer, offset);  // does not change channel.position()
int sent  = channel.write(sourceBuffer, offset); // does not change channel.position()
```

Here:

- `offset` is assigned by business logic for each data region, typically passed as a task parameter.
- The buffer is owned exclusively by one task for the duration of the I/O; `ByteBuffer` is not thread-safe when multiple threads mutate its state.
- After each `read`/`write`, check the actual byte count, advance the offset, and continue while data remains.
- Offsets must be non-negative; adding processed bytes to the offset must avoid `long` overflow.
- Do not open the channel with `StandardOpenOption.APPEND` if logic relies on absolute write offsets: the Javadoc specifies that `write` at a given position when the channel is open in APPEND mode has **unspecified** behavior.

This approach prevents A from altering B's pointer, **yet does not automatically solve** two tasks writing bytes `100..199` concurrently, reading one record while another record is being modified, overlapping appends, or concurrent `truncate` calls. To preserve consistency, you still must allocate non-overlapping regions or lock at the data/record level.

### Runnable example: two threads writing two independent regions

Create a file named `IndependentOffsets.java`:

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.concurrent.*;

public class IndependentOffsets {
    static int writeAllAt(FileChannel channel, ByteBuffer source, long offset)
            throws IOException {
        int written = 0;
        while (source.hasRemaining()) {
            int n = channel.write(source, Math.addExact(offset, written));
            if (n == 0) throw new IOException("Write made no progress");
            written += n;
        }
        return written;
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("nio-slots-", ".dat");
        try {
            Files.writeString(file, "........", StandardCharsets.US_ASCII);
            try (FileChannel channel = FileChannel.open(file,
                    StandardOpenOption.READ, StandardOpenOption.WRITE)) {
                ExecutorService pool = Executors.newFixedThreadPool(2);
                try {
                    Future<Integer> a = pool.submit(() -> writeAllAt(channel,
                        ByteBuffer.wrap("ABCD".getBytes(StandardCharsets.US_ASCII)), 0));
                    Future<Integer> b = pool.submit(() -> writeAllAt(channel,
                        ByteBuffer.wrap("WXYZ".getBytes(StandardCharsets.US_ASCII)), 4));
                    System.out.println("bytes=" + a.get() + "," + b.get());
                    System.out.println("file=" + Files.readString(file, StandardCharsets.US_ASCII));
                    System.out.println("channel-position=" + channel.position());
                } finally {
                    pool.shutdown();
                }
            }
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

```bash
javac --release 17 IndependentOffsets.java
java IndependentOffsets
```

Verified output with Java 17 bytecode on a standard file system:

```text
bytes=4,4
file=ABCDWXYZ
channel-position=0
```

Because the two tasks have **non-overlapping absolute offsets** (`0..3` and `4..7`), the resulting file is consistent regardless of which task finishes first. Each task owns a separate `ByteBuffer`, and `Future.get()` confirms both have completed before reading the file. The channel's current position is never modified; it remains `0`. `writeAllAt` loops on short writes, increments the offset by the bytes written, and intentionally throws if no progress is made to prevent infinite loops. The requirement to coordinate overlapping writes or file-size changes still applies.

The example intentionally creates a file of exactly 8 bytes before the two tasks begin. For files that can grow, positional writes past the end of the file can still change the file size; `FileChannel`'s contract includes serialization rules for size-changing operations. **That does not substitute for proper offset allocation.**

## 6. When a shared cursor is unavoidable: lock the entire multi-step operation

Some libraries or interfaces only expose `seek` / `position` followed by `read` / `write`. In that case, define *one* common lock for every place accessing the same pointer:

```java
final Object cursorLock = new Object(); // shared field of the owner

byte[] readBlock(RandomAccessFile raf, long offset, int length)
        throws java.io.IOException {
    byte[] bytes = new byte[length];
    synchronized (cursorLock) {
        raf.seek(offset);
        raf.readFully(bytes);
    }
    return bytes;
}
```

This is an **illustrative snippet inside the class managing `cursorLock`**, not a standalone Java source file. `readFully` may throw `EOFException` if fewer than `length` bytes remain. You must use the **exact same lock** for all code calling `seek`, `read`, `write`, `getChannel().position`, or relative operations on that handle. Locking only `seek` or only `readFully` is not enough:

```java
// WRONG: two separate synchronized blocks; another thread can interleave between them.
synchronized (cursorLock) { raf.seek(offset); }
synchronized (cursorLock) { raf.readFully(bytes); }
```

The single synchronized block above ensures threads obeying the lock cannot interleave **between `seek` and `readFully`**. Avoid holding the lock during long operations unrelated to the cursor; perform complex data processing after reading finishes if feasible. This lock is effective only within the JVM; another process accessing the same file can still modify its contents.

You can use `ReentrantLock` instead of `synchronized` to support timeouts or interruptible lock acquisition; the principle stays the same: the lock must span the entire pointer-dependent unit of work, and every task using the pointer must participate.

**Do not rely on `volatile long lastOffset` to protect a `seek + read` sequence.** `volatile` only establishes visibility/ordering rules for that Java variable; it does not lock the file pointer state inside the I/O handle. `AtomicLong.getAndAdd(length)` can be used to **allocate non-overlapping offsets** for tasks if the file region is properly managed, but by itself it does not turn multi-step writes into a transaction.

## 7. Choosing a coordination architecture by scenario

| Scenario | Suitable design | Limits to verify |
| --- | --- | --- |
| Multiple tasks reading different regions of a mostly static file | Use `FileChannel.read(buffer, offset)` with a dedicated buffer per task. | Each task handles short reads / EOF; external writers may still alter the file. |
| Multiple tasks writing pre-allocated, non-overlapping slots/records | `FileChannel.write(buffer, offset)`, looping on short writes; centralized offset allocation. | Prevent offset overflow, avoid concurrent `truncate`, avoid APPEND, validate record layout. |
| Single `RandomAccessFile` requiring `seek → read/write` sequences | One shared lock spanning the entire sequence; optionally funnel operations through one owner/service. | Every caller must comply; tasks may block during I/O. |
| Each worker can open its own channel to the same file | One dedicated channel per worker, each with its own position. | File contents are still shared; overlapping writers must coordinate; does not imply record atomicity. |
| Multiple workers appending variable-length records | A single writer receiving records via a queue, or an exact offset/length allocator followed by positional writes. | Must define record framing, ordering, partial-write errors, and recovery; APPEND does not guarantee atomicity on all platforms. |
| Multiple processes operating on the same file | Design an inter-process coordination protocol; consider file locks and check OS/filesystem semantics. | File locks are OS-dependent; do not resolve intra-JVM thread synchronization. |
| Consistent snapshot reads needed alongside writers | Data/record locks, separate snapshots, copy-on-write, or appropriate versioning. | Positional APIs do not create snapshots or make multi-call groups transactional. |

If multiple tasks push work onto a queue served by a single owner, that owner can execute relative operations in a deterministic order. This pattern is often easier to reason about for logs with variable-length records or multi-field binary formats. However, managing a single writer worker still requires handling partial writes, I/O errors, and clean shutdown.

A **dedicated channel per thread** separates cursors, not files. If two channels open the same path, both can still write to the exact same bytes; without data coordination, lost updates can occur. If a channel comes from `raf.getChannel()`, it is **not** independent from `raf` itself.

## 8. Which lock protects what?

Distinguish three synchronization layers:

1. **In-JVM cursor lock:** `synchronized` or `ReentrantLock` protects `position`/`seek` state and multi-step sequences on the right I/O owner. This is the choice when coordinating threads sharing a pointer.
2. **Application data/record lock:** ensures two tasks do not update the same record in conflicting ways. This can be record/range locking, offset partitioning, or a single writer. It must cover the entire "read → compute → write" cycle if the logic is read-modify-write.
3. **OS-level file lock via `FileChannel.lock` / `tryLock`:** used to coordinate with other processes when the environment supports the required semantics. The Javadoc clearly states that file locks are held on behalf of **the entire JVM**, making them unsuitable for coordinating multiple threads inside the same JVM; advisory/mandatory behavior and shared-lock support vary by OS.

For example, `channel.lock(0, 100, false)` can request an exclusive lock on a file range, but you should **not** replace `synchronized(cursorLock)` with this call to protect two threads in the same process. Within a single JVM, overlapping lock requests can even throw `OverlappingFileLockException`. Depending on the system, other processes may ignore advisory locks, and network file systems may impose their own restrictions. Your design must explicitly identify whether you are preventing "cursor interleaving", "record overwrites", or "inter-process conflicts" before choosing a lock type.

### Atomicity differs from thread-safety and durability

- **Thread-safe:** the API can be called concurrently within its documented contract without corrupting internal state.
- **Business-level atomic:** a group of operations (e.g., reading a balance, adding 1, writing back) appears as an uninterruptible unit per application rules. `FileChannel` does not automatically provide transactions for such groups.
- **Durable:** data survives machine/power failure according to storage guarantees; `FileChannel.force(...)` relates to flushing updates to storage, not creating locks or guaranteeing logical transactions across writers.

Do not use `force(true)` to fix race conditions, and do not treat an in-JVM mutex as sufficient to guarantee crash durability.

## 9. Common mistakes and how to spot them

**Mistake 1 — Setting position and then doing something else before reading/writing.**

```java
channel.position(offset);
doSomethingThatMayUseTheSameChannel();
channel.read(buffer); // offset is no longer guaranteed to be as intended
```

This is an illustrative snippet. The best fix when using `FileChannel` is `channel.read(buffer, offset)`. If positional APIs are unavailable, guard the entire sequence under the same lock and never invoke arbitrary callbacks while holding the lock.

**Mistake 2 — Treating `FileChannel` thread-safety as a transaction.**

```java
long old = channel.position();
channel.position(recordOffset);
channel.write(record);
channel.position(old);
```

This is an illustrative snippet. Between individual calls, another task can still alter the position; restoring `old` can even clobber a position another task just set. Use a positional write or a lock spanning the entire sequence whenever saving/restoring position is truly required.

**Mistake 3 — Assuming a single `read`/`write` processes the entire buffer.**

```java
// The result may be less than buffer.remaining() before the call.
int n = channel.write(buffer, offset);
```

You must advance `offset += n` and loop while data remains; for reads, handle `-1` at EOF and define a policy for `0` when no progress occurs. Each task must own its buffer until the I/O finishes. If the file holds binary records, a partial write can leave an invalid record; an error and recovery strategy is needed.

**Mistake 4 — Multiple threads computing the end-of-file offset themselves.**

```java
long offset = channel.size();
channel.write(buffer, offset);
```

This is an illustrative snippet. Two tasks can obtain the exact same `size` value before either begins writing. The solution is a centralized writer or an application-level atomic region allocator, while also protecting related resize/truncate operations. `StandardOpenOption.APPEND` should also not be assumed to guarantee atomic single-record writes across all platforms.

**Mistake 5 — Misunderstanding `ByteBuffer` thread-safety.**

Sharing a single buffer between two tasks can write corrupted bytes or throw `BufferUnderflowException` / `BufferOverflowException` due to unexpected `position/limit` changes. `FileChannel.write(src, absoluteOffset)` does not lock the buffer for the caller. Create separate buffers, or transfer exclusive ownership to the worker until completion.

**Mistake 6 — Trying to fix a race using a file lock within the same JVM.**

`FileLock` is a file/OS-level coordination mechanism with platform-specific semantics; it does not protect threads from mutating a shared pointer through the same `RandomAccessFile`. Use an in-JVM mutex/owner for the cursor, and add file locks only when verified inter-process coordination is required.

**Mistake 7 — Ignoring concurrent close or truncate from another thread.**

When a channel is closed mid-I/O, exceptions such as `ClosedChannelException`/`AsynchronousCloseException` can occur. When one worker calls `truncate` or changes file length, offsets computed by another worker may become invalid. Manage lifecycles and metadata permissions explicitly, and avoid letting independent read/write workers close a shared channel arbitrarily.

## 10. Design and testing checklist

Before implementing:

1. **Identify pointer ownership:** which object holds the pointer? Are `RandomAccessFile` and `getChannel()` sharing it? Are any callbacks/helpers also using it?
2. **Identify business offsets:** where do byte offsets come from, who allocates them, and can they collide or overflow? Are byte offsets ever mixed with character indices?
3. **Prefer positional I/O:** when offsets are known, use `read/write(ByteBuffer, long)` with dedicated buffers; loop until all bytes are transferred.
4. **If a cursor must be used:** lock the entire `seek/position → read/write` block; ensure all callers use the same lock; never rely on the scheduler appearing sequential.
5. **Identify overlapping data regions:** can two tasks write the same bytes, the same record, the same EOF, or call `truncate`? Define a clear overlap protocol.
6. **Define ownership/lifecycle:** only the owner decides when to close the channel; ensure asynchronous work finishes before closing.
7. **Test controlled interleavings:** use `CountDownLatch`/barriers or scripted sequencing to reproduce A setting pointer → B changing pointer → A operating; never use `sleep` as proof of correctness.
8. **Verify actual file contents:** compare exact bytes at every offset, test record framing, short I/O, EOF, multi-worker runs, and mid-operation failures.
9. **Verify correctness before optimizing performance:** choose positional APIs or mutexes based on consistency requirements; tune channel counts/IOPS only after verifying correctness on the target file system.

### Self-check questions

**Question 1.** Two threads share one `FileChannel`, and each calls `position(...)` followed by `write(...)`. Does a thread-safe API guarantee both write at their intended offsets?

**No.** Each individual call is valid, but another thread can interleave between `position` and `write`. Use positional writes or lock the entire sequence.

**Question 2.** If you use `channel.write(buffer, offset)`, is it completely thread-safe across multiple threads?

**Not yet.** It eliminates channel pointer contention, but two threads writing overlapping byte ranges, sharing a `ByteBuffer`, resizing the file, or updating the same record still require coordination.

**Question 3.** Does `raf.seek(10)` change `raf.getChannel().position()`?

**Yes.** `RandomAccessFile` and its own channel share the same position. Conversely, `channel.read(dst, 20)` is an absolute-position read, so it does not change the shared pointer.

**Question 4.** Can `FileChannel.lock()` replace `synchronized` to protect a file pointer between two threads in the same JVM?

**No.** `FileLock` is not designed to synchronize threads within the same JVM; use an application lock across the entire multi-step operation.

**Question 5.** Why does the `IndependentOffsets` example writing two independent regions always yield `ABCDWXYZ` regardless of which task finishes first?

Because each task uses a distinct absolute offset, each owns an independent buffer, the two byte ranges do not overlap, and the program waits for both `Future`s to complete before reading the file. Neither task needs to modify `channel.position()`.

## Official documentation

- [Java SE 21 — `FileChannel`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html): multi-thread contract, current position, positional read/write, `APPEND` limitations, file locks.
- [Java SE 21 — `RandomAccessFile`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/RandomAccessFile.html): `seek`, `getFilePointer`, and position coupling with `getChannel()`.
- [Java SE 21 — `FileLock`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileLock.html): OS-level file locking, unsuitable for intra-JVM thread synchronization.
- [Java SE 21 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, and how to use buffers for I/O.

Consistent guiding principle: **managing a pointer means managing shared mutable state**. Choose absolute offsets when tasks are independent; if a workflow must rely on a shared pointer, synchronize the entire meaningful business sequence while also protecting data whenever operations can overlap.
