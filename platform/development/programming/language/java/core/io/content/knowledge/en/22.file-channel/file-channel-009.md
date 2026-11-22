# Using FileChannel Concurrently: Shared Position vs. Explicit-Position Operations

## 1. The Problem: One FileChannel, Multiple Threads

`java.nio.channels.FileChannel` provides two basic groups of read/write operations:

- **Relative to the current position**: `read(ByteBuffer dst)` and `write(ByteBuffer src)` use the **channel's shared position**. When reading/writing succeeds, this position advances by the number of bytes processed.
- **Explicit-position operations** (*positional I/O*): `read(ByteBuffer dst, long position)` and `write(ByteBuffer src, long position)` accept a starting byte offset in the file; they **do not change the channel's current position**.

Both groups can be called from multiple threads, yet they differ in state management and concurrency potential. By the `FileChannel` contract, a channel itself **is safe for use by multiple concurrent threads**. This does **not** mean all operations run simultaneously, that a sequence of multiple calls automatically becomes atomic, or that passed-in `ByteBuffer` instances are safe when shared.

The core question is: *Do tasks want to share a single file cursor for sequential processing, or does each task need to access a position it determines independently?*

## 2. Two Types of Position That Must Not Be Confused

A read/write through `FileChannel` can involve **two independent positions**:

1. **The channel's file position**, retrieved/set via `channel.position()` and `channel.position(long)`. This is the byte index within the file; each `FileChannel` has its own position.
2. **The `ByteBuffer`'s position**, retrieved/set via `buffer.position()`. This is the byte index **inside the buffer**. Channel read/write operations still typically move the buffer's position by the number of bytes transferred, even when calling overloads with an explicit offset.

For example, suppose a file contains `ABCDEFGHIJ`, the channel is currently at offset 3, and a newly allocated buffer has `position=0`:

~~~java
ByteBuffer dst = ByteBuffer.allocate(2);
int n = channel.read(dst, 7L);
~~~

This is an **illustrative snippet**, assuming `channel` is open for reading and the file is long enough. When two bytes are read, `dst` contains `HI` and `dst.position() == 2`; meanwhile **the channel's position remains 3**. To read the contents just written into the buffer, call `dst.flip()` and then use `get()` or a charset decoder.

Conversely, calling `channel.read(dst)` uses the **current file position**. If two bytes are read at offset 3, the channel advances to offset 5 and the buffer advances to position 2.

| API | Starting position in file | Changes channel's file position? | Changes buffer position? |
| --- | --- | --- | --- |
| `channel.read(dst)` | `channel.position()` at read time | **Yes**, by bytes read | **Yes** |
| `channel.write(src)` | `channel.position()` at write time | **Yes**, by bytes written | **Yes** |
| `channel.read(dst, offset)` | Passed-in `offset` | **No** | **Yes** |
| `channel.write(src, offset)` | Passed-in `offset` | **No** | **Yes** |
| `channel.position(offset)` | Sets position used for next relative operation | **Yes**, replaces current value | No |
| `channel.size()` | Inspects file length | Does not actively move cursor | No |
| `channel.truncate(size)` | Reduces file size if needed | May adjust file position if beyond new size | No |

In every read/write, actual bytes may be **fewer** than `dst.remaining()` or `src.remaining()`; always check the return value. For `read`, `-1` signals end of file. The looping examples below do not assume a single call suffices for an entire data region.

## 3. Thread-Safe FileChannel: What Exactly Is Guaranteed?

The Java SE contract for `FileChannel` specifies:

- `FileChannel` instances are safe for use by multiple threads.
- **At most one operation on the same channel that involves the channel's position or can change its file size may be in progress at any given time.** A second operation in this category may have to wait for the first to finish.
- Other operations, notably those accepting an **explicit position**, *may* proceed concurrently; whether they actually execute in parallel or are serialized depends on the implementation.
- `close()` may be called from another thread per the `Channel` contract; closing while another operation is in progress can raise errors such as `AsynchronousCloseException`.

Thus, the statement "FileChannel is thread-safe" refers to a **channel-operation-level coordination contract**, and does not guarantee:

1. Two consecutive relative reads by thread A are treated as a transaction immune to interleaving with calls from thread B.
2. A `channel.position(n)` followed by `channel.read(dst)` always reads at `n` if another thread can change the position between the two calls.
3. Two writers writing **the same byte region** with positional I/O produce a consistent record or a "winning writer" in an order you expect.
4. Opening two separate `FileChannel` instances to the same file automatically creates a shared lock across both instances.
5. Every buffer passed into a channel is thread-safe. `ByteBuffer` has mutable position/limit state and provides no inherent safety for concurrent sharing.

Distinguishing **internal safety of a single call** from **correctness of a multi-call business operation** is the most important part of using `FileChannel` in multithreaded systems.

## 4. Bugs When Coordinating position() + read()

Suppose two threads want to read at two different offsets:

~~~java
// Thread A
channel.position(100);
channel.read(bufferA);

// Thread B
channel.position(200);
channel.read(bufferB);
~~~

This is **illustrative code**. There is no guarantee that A's calls execute contiguously; one possible interleaving is:

~~~text
A: channel.position(100)
B: channel.position(200)
A: channel.read(bufferA)  // May read at offset 200
B: channel.read(bufferB)  // Continues after what A just read
~~~

The channel serializing individual calls that touch the file position **does not** wrap the `position(...) + read(...)` pair into a transaction. The exact same problem occurs with `position(...) + write(...)`.

If a task needs to read at a specific offset, the more direct approach is:

~~~java
channel.read(bufferA, 100L);
channel.read(bufferB, 200L);
~~~

These two calls have independent offsets and do not mutate the channel's shared position. They still move **each buffer's position**, so each task should best use its own buffer. If a full record must be read, loop the positional read and increment the offset by the bytes actually received.

When business logic genuinely requires a shared cursor, you can lock a code block:

~~~java
synchronized (channel) {
    channel.position(100);
    while (bufferA.hasRemaining()) {
        int n = channel.read(bufferA);
        if (n < 0) throw new java.io.EOFException();
        if (n == 0) throw new java.io.IOException("No read progress");
    }
}
~~~

This is an **illustrative snippet**, assuming channel/buffer are declared. Locking works only if **all code touching the shared position follows this protocol**. Synchronizing on `channel`'s monitor does not stop another component from calling `channel.read(...)` without acquiring that monitor. When only a predetermined offset is needed, positional overloads usually yield a simpler contract.

## 5. Runnable Example: Sharing a Cursor vs. Reading at Independent Offsets

The Java 17+ program below creates a temporary file containing 10 ASCII bytes, then has two threads use **the same `FileChannel`** through both access styles.

Part A: two threads read using `read(buffer)`, sharing a single file position. `CountDownLatch` forces A to read 2 bytes first, B to read the next 2 bytes, and then A to read the final byte. The example uses `synchronized(channel)` inside the helper so an entire chunk-read loop cannot be interleaved if `FileChannel.read` returns fewer bytes than requested. Hence the output does not depend on race luck.

Part B: two threads use `read(buffer, offset)` with offsets 0 and 5, each keeping its own `ByteBuffer`. With only concurrent reads on an unmodified file, they retrieve the two intended regions while the channel's file position does not move.

Create file `ChannelPositionDemo.java`:

~~~java
import java.io.*;
import java.nio.*;
import java.nio.channels.*;
import java.nio.charset.*;
import java.nio.file.*;
import java.util.concurrent.*;

public class ChannelPositionDemo {
  static void await(CountDownLatch latch) {
    try {
      latch.await();
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new IllegalStateException(e);
    }
  }

  static String relative(FileChannel ch, int size) throws IOException {
    ByteBuffer b = ByteBuffer.allocate(size);
    synchronized (ch) {
      while (b.hasRemaining()) {
        int n = ch.read(b);
        if (n < 0) throw new EOFException();
        if (n == 0) throw new IOException("No read progress");
      }
    }
    return new String(b.array(), StandardCharsets.US_ASCII);
  }

  static String at(FileChannel ch, long p, int size) throws IOException {
    ByteBuffer b = ByteBuffer.allocate(size);
    while (b.hasRemaining()) {
      int n = ch.read(b, p);
      if (n < 0) throw new EOFException();
      if (n == 0) throw new IOException("No read progress");
      p += n;
    }
    return new String(b.array(), StandardCharsets.US_ASCII);
  }

  public static void main(String[] args) throws Exception {
    Path path = Files.createTempFile("nio-demo-", ".bin");
    try (FileChannel ch = FileChannel.open(path,
        StandardOpenOption.READ, StandardOpenOption.WRITE)) {
      ByteBuffer input = ByteBuffer.wrap(
          "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII));
      while (input.hasRemaining()) {
        int n = ch.write(input, (long) input.position());
        if (n <= 0) throw new IOException("No write progress");
      }
      System.out.println("Initial position: " + ch.position());

      CountDownLatch aDone = new CountDownLatch(1);
      CountDownLatch bDone = new CountDownLatch(1);
      String[] a = new String[2], b = new String[1];

      Thread ta = new Thread(() -> {
        try {
          a[0] = relative(ch, 2);
          aDone.countDown();
          await(bDone);
          a[1] = relative(ch, 1);
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      Thread tb = new Thread(() -> {
        await(aDone);
        try {
          b[0] = relative(ch, 2);
          bDone.countDown();
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      ta.start();
      tb.start();
      ta.join();
      tb.join();

      System.out.println("A relative: " + a[0] + " then " + a[1]);
      System.out.println("B relative: " + b[0]);
      System.out.println("Position after relative: " + ch.position());

      ch.position(0);
      String[] result = new String[2];
      Thread t1 = new Thread(() -> {
        try {
          result[0] = at(ch, 0, 5);
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      Thread t2 = new Thread(() -> {
        try {
          result[1] = at(ch, 5, 5);
        } catch (IOException e) {
          throw new UncheckedIOException(e);
        }
      });
      t1.start();
      t2.start();
      t1.join();
      t2.join();

      System.out.println("At 0: " + result[0]);
      System.out.println("At 5: " + result[1]);
      System.out.println("Position after positional: " + ch.position());
    } finally {
      Files.deleteIfExists(path);
    }
  }
}
~~~

Compile/run with JDK 17 or later:

~~~bash
javac ChannelPositionDemo.java
java ChannelPositionDemo
~~~

Stdout:

~~~text
Initial position: 0
A relative: AB then E
B relative: CD
Position after relative: 5
At 0: ABCDE
At 5: FGHIJ
Position after positional: 0
~~~

The code was tested on a JDK producing the output above; the version with progress checks added inside the loop preserves the logic for regular files.

**How to read the output:**

1. Writing with `write(input, offset)` uses an explicit offset, so after writing 10 bytes, `ch.position()` is still 0. Buffer `input`, meanwhile, moves its position to the end of the data.
2. In the relative section, thread A reads `AB`; B continues reading `CD`; A then reads `E`. Neither thread has "its own" file position; `ch.position()` after the three passes equals 5.
3. After explicitly setting `ch.position(0)`, two other threads directly read slices [0, 4] and [5, 9] using `read(buffer, offset)`. Both obtain the right data, and the file position stays 0.
4. `CountDownLatch` enforces a deterministic order for the first pass of reads. `Thread.join()` waits for threads to finish and ensures `main` observes results written into both arrays in the example.
5. Each helper call allocates a **new** buffer. The two threads have no data race on `ByteBuffer.position()`. The positional section has no concurrent writers, so it does not have to resolve file-content conflicts.

**Note on example error handling:** to keep focus on file positions, the code uses plain threads and prints results after `join()`. Real applications should capture thread exceptions via `Future.get()`, `CompletableFuture`, or equivalent, and ensure latches/futures fail properly; never let one thread wait forever when another thread terminates due to an exception.

## 6. Choosing Relative vs. Explicit-Position Operations?

| Scenario | Choice | Reason |
| --- | --- | --- |
| Single thread reading the entire file sequentially | `read(dst)` | File position auto-advances, simple code |
| Threads processing records at separate offsets | `read(dst, offset)` | No contention on shared file position |
| Multiple workers writing non-overlapping blocks | `write(src, offset)` + each worker has its own buffer | Each worker knows its exact position |
| Need one sequential read cursor serving multiple consumers | Define a single owner or use locks/queues | Prevents logic interleaving between calls |
| Must move position then read a multi-call transaction | Lock the entire sequence, or switch to positional | `position()+read()` is not atomic |
| Need to update a multi-field record consistently | Design lock/version/transaction mechanisms at record level | Positional write alone does not give atomicity |
| Need appends from multiple producers | Single centralized writer, offset allocator, or verified append policy | Concurrent append depends on platform and write policy |

Using **positional I/O** does not mean you can ignore file size bounds, buffer lengths, permissions, or coordination when multiple threads write overlapping regions.

## 7. File Size and Operations That Change File Size

`FileChannel` has special serialization rules for operations **that can change file size**, even when they take an explicit position. For instance, writing at an offset beyond current EOF can lengthen the file. Therefore, you must not say "every `write(buffer, offset)` definitely runs in parallel" or cite having an `offset` parameter as proof of concurrency optimization.

Several cases:

- **Reading at an offset beyond EOF**: `read(dst, offset)` returns `-1` when at or past end of file (if the buffer still has space to fill), without adding data.
- **Writing beyond EOF**: `write(src, offset)` may extend the file. The gap between the old EOF and the write offset follows filesystem rules; do not interpret it as a valid record.
- **`truncate(newSize)`** can shorten the file. If the file position is larger than the post-truncate size, the channel position is adjusted per the API contract. Concurrent readers may hit EOF earlier or lose expected data.
- **`size()` returns point-in-time state**. `long pos = channel.size(); channel.write(src, pos);` does not create an atomic append. Multiple threads could read the same size and choose that same offset.
- **`force(true)`** requests flushing updates to the storage device per API and device guarantees, yet does not replace a mutex, provide transactions, or combine multiple writes into one atomic update.

If a multi-threaded design needs appending, allocate non-overlapping offsets via a synchronized coordinator; if file size changes dynamically, manage the file's structural lifecycle/state. Avoid mixing `truncate` or file extension with workers using old offsets without a protocol.

## 8. The Buffer Passed into FileChannel Is Also Stateful Resource

Positional overloads preserve **file position**, yet still update **buffer position**. For example, two threads both call:

~~~java
channel.read(sharedBuffer, 0L);
channel.read(sharedBuffer, 128L);
~~~

This is an erroneous illustration if both threads share `sharedBuffer` without synchronization/ownership. Even though file offsets differ, both contend on `sharedBuffer.position()`, and can write concurrently into the same backing storage. `ByteBuffer` is not thread-safe by default.

Common organization patterns:

- Each thread/task owns its own `ByteBuffer` and does not hand that buffer to another thread before finishing.
- If using `duplicate()`/`slice()`, views have independent cursors but **still share backing storage**. Writing is safe only when memory regions do not overlap or proper synchronization exists.
- When reading immutable data, read-only views can be used with safe publication and guarantees that no alias is writing. `asReadOnlyBuffer()` prevents writes through the view; it **does not** make underlying bytes immutable.
- While an asynchronous task is still using a buffer, do not return the buffer to a pool and call `clear()` prematurely.

In the full example, the `at(...)` helper creates a fresh `ByteBuffer.allocate(size)` for each read, cleanly isolating buffer state.

## 9. Handling Partial Read/Write and Offsets by Actual Bytes

A single `read(dst, offset)` call may return fewer bytes than `dst.remaining()`. When reading a full fixed-size record, increment the **explicit file offset** after each read:

~~~java
long current = recordOffset;
while (dst.hasRemaining()) {
    int n = channel.read(dst, current);
    if (n < 0) throw new java.io.EOFException("Truncated record");
    if (n == 0) throw new java.io.IOException("No progress");
    current += n;
}
~~~

This is an **illustrative snippet**, assuming `recordOffset`, `channel`, and `dst` are valid. Crucially, increment `current` by `n`; reading repeatedly at the same `recordOffset` in the loop can duplicate data inside the buffer.

Similarly for positional write:

~~~java
long current = recordOffset;
while (src.hasRemaining()) {
    int n = channel.write(src, current);
    if (n <= 0) throw new java.io.IOException("No write progress");
    current += n;
}
~~~

Here `src.position()` also increases by `n`, while the **shared file position** remains unchanged. When calculating the offset for the N-th record, use `long` and overflow checks:

~~~java
long offset = Math.addExact(
        headerSize, Math.multiplyExact(recordIndex, recordSize));
~~~

This is an illustrative snippet assuming `headerSize`, `recordIndex`, and `recordSize` are valid non-negative `long` values. If the offset is miscalculated or two workers receive the same index, positional I/O can overwrite each other's data despite zero contention on file position.

## 10. Concurrent Writes: No Guarantee That One Record Is Atomic

Two threads assigned disjoint regions such as [0, 999] and [1000, 1999] can share the same channel via positional I/O. That design avoids data-position collisions if each thread has its own buffer, the file has been pre-sized appropriately, and no other thread calls `truncate` or edits overlapping ranges.

However, if two threads write **the same region**:

~~~java
// Writer A
channel.write(dataA, 4096L);

// Writer B
channel.write(dataB, 4096L);
~~~

This is an **illustrative snippet**. You cannot assume the final bytes are cleanly all A's or all B's, or that one `write` call always writes the entire buffer. Even if calls are serialized in some circumstances, that does not turn **an entire read-modify-write sequence** into an atomic transaction. Operations updating balances, version numbers, status, and checksums in one record require locking/versioning or higher-level consistent storage protocols.

If durable updates and crash recovery are required, consider copy-on-write, checksum + version, a write-ahead log, or a transactional database. Avoid treating `channel.force(true)` or `channel.lock()` as automatic proof of transactions.

## 11. FileLock and Multiple FileChannels to the Same File

`FileChannel.lock(...)` or `tryLock(...)` supports locking file regions when access coordination is needed. However, note that:

- File locks are managed at the OS/provider level and have platform differences (advisory vs. mandatory, region granularity support, enforcement timing).
- Locks cover byte regions, not always all data automatically. You must define the exact region to protect.
- File locks **are held on behalf of the entire JVM**. Attempting to acquire a lock overlapping one already held or pending by the JVM can throw `OverlappingFileLockException`, rather than acting as an ideal mutex between two threads in the same JVM.
- Do not use `FileLock` as the sole intra-JVM thread locking mechanism. Use `synchronized`, `ReentrantLock`, or an in-JVM ownership manager when coordinating workers; use file locks when cooperating with external processes and platform limits are well understood.
- If multiple separate channels open the same file, they have **separate file positions**, yet share the file contents. Two channels writing to the same region still require coordination.

You can use one shared channel across multiple workers when ownership and byte-range contracts are clear; you can also use separate channels depending on management cost and I/O characteristics. Having multiple channels does not by itself make updating the same region safe.

## 12. Common Mistakes and How to Fix Them

| Wrong claim or action | Why it is wrong | How to handle it |
| --- | --- | --- |
| "FileChannel is thread-safe, so `position(100); read(dst)` always starts at 100" | Another thread can interleave between the two calls | Use `read(dst, 100L)` or lock the entire sequence |
| "Two threads call `read(dst)`, so each gets its own cursor" | One `FileChannel` has a single shared file position | One owner reads sequentially, or use positional I/O |
| "`read(dst, offset)` changes no state at all" | Buffer position still advances | Give each task its own buffer or synchronize |
| "Having an offset means FileChannel must run in parallel" | Contract permits implementation serialization | Do not rely on parallelism for correctness |
| "Writing at an explicit offset cannot extend the file" | Writing past EOF can grow file size | Control size, boundaries, and offset allocation |
| "Two threads reading `size()` then appending is fine" | Both can pick the exact same offset | Allocate offsets through a coordinator |
| "One `read` call always fills the buffer" | Partial I/O is allowed | Loop, track bytes, and handle EOF |
| "Sharing one `ByteBuffer` is fine because the channel has locks" | Buffer has its own cursor and backing memory | Do not share mutable buffers outside contract |
| "`force(true)` makes updates atomic" | Durability and atomicity are different | Use transactions/WAL/versioning as required |
| "A `FileLock` is a complete mutex across threads in the JVM" | File locking and lock overlap differ from internal mutexes | Use JVM locks and ownership protocols |
| "Can `close()` the channel while another thread is doing I/O" | Can cause `AsynchronousCloseException` / failed I/O | One owner manages closing after all workers finish |

### API Selection Workflow in Applications

1. Determine whether read/write tasks are **sequential** or have **independent offsets**.
2. Determine whether each thread has its own `ByteBuffer` or shares backing storage.
3. If an operation spans multiple calls, determine whether atomicity is needed at the **single-call level** or the **record/transaction level**.
4. Check whether writes alter **file size** or conflict with truncation.
5. With multiple writers, establish non-overlapping region allocation and retry/error policies.
6. Close the channel only after all tasks using it have finished; propagate errors back to the owner so no I/O failures are lost.

## 13. Self-Check

**Question 1.** `channel.position() == 10`; thread A reads 3 bytes with `read(dst, 100)`. What does the channel's file position become?

**Answer:** 10. The explicit-offset overload does not change the file position; `dst.position()`, however, increases by 3 if 3 bytes were read.

**Question 2.** Two threads call `channel.position(x)` then `channel.read(buffer)` for two different offsets. Why can bugs still occur even though the channel is thread-safe?

**Answer:** Because one thread's two calls are not treated as a single transaction. The other thread can modify the shared position between `position(x)` and `read(buffer)`.

**Question 3.** Two threads read two non-overlapping regions with `read(dst, offset)`. Should they share one `ByteBuffer` to save memory?

**Answer:** No. Use a separate buffer per task to isolate cursor state and underlying bytes; an unchanged file offset does not mean buffer position stays unchanged.

**Question 4.** Do two `write(src, offset)` calls with different offsets always execute in parallel?

**Answer:** No. The contract allows concurrency in many cases, yet actual parallel execution depends on the implementation; if an operation can change file size, related serialization rules also apply.

**Question 5.** Does writing new blocks at EOF via `long p = channel.size(); channel.write(src, p)` across 10 threads guarantee non-overlapping appends?

**Answer:** No. Querying size and writing are two separate operations; multiple threads can obtain the same `p`. You need an offset allocator or a coordinating writer.

**Question 6.** Can `FileChannel.lock()` always replace `ReentrantLock` between threads inside the same JVM?

**Answer:** No. File locks target coordinating access to file regions and have OS-dependent characteristics; overlapping locks within the same JVM can throw `OverlappingFileLockException`.

## API Documentation

- [Java SE 17 — FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): concurrent access contract; read/write overloads with shared position and explicit position; file locking, truncate, force.
- [Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): buffer position/limit, byte transfer on read/write, buffer thread safety.
- [Java SE 17 — FileLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileLock.html): region locking, JVM scope, and platform limits.
- [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html): ordering coordination and happens-before relationships.
