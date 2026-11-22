# Bounding Parallel Reads and Ordering Result Assembly with Java IO/NIO.2

When a large file needs to be read and processed in blocks, work can be split across multiple threads: the first block reads from offset 0, the next from offset `chunkSize`, and so on. However, **parallel reading or processing** does not mean **results arrive in their original order**. A block at the end of the file may finish before the first block; if written immediately in completion order, the output data will be scrambled.

Beyond correctness, unbounded parallel reads easily spawn thousands of tasks, many data-holding buffers, and too many concurrent I/O calls. A sound design must simultaneously guarantee:

1. **Exact read ranges:** each block reads a defined byte range without overlaps or gaps.
2. **Resource bounds:** limit executing tasks, submitted tasks whose results are not yet consumed, buffered data, and open files/channels.
3. **Ordered assembly:** results are written to the output in exact block/offset order regardless of which thread finishes first.
4. **Error handling and termination:** read errors propagate to the coordinator; remaining resources and tasks are stopped rather than publishing an incomplete output file.

This lesson focuses on Java 17+ patterns using `FileChannel`, `ExecutorService`, `Future`, and a bounded result queue. The same principles apply to per-block checksums, decoding/transforming independent blocks, or assembling processed chunks.

## 1. Three Different Orders

Suppose a file has 4 blocks:

```text
File by offset:
[0: AAAA] [1: BBBB] [2: CCCC] [3: DDDD]
```

If two workers run concurrently, the schedule might be:

```text
Submit order:       0 → 1 → 2 → 3
Completion order:   1 → 0 → 3 → 2
Required write:     0 → 1 → 2 → 3
Correct result:     AAAABBBBCCCCDDDD
```

- **Submit order:** the order work is submitted to the executor; makes no guarantee about completion order.
- **Completion order:** the order tasks actually finish; depends on the scheduler, device speed, cache, and processing duration.
- **Output order:** the business order to preserve; for file assembly, typically ascending offset order.

`Future.get()` waits for a specific task to finish. If futures are stored in block order and sequentially `get()`ed and written, output stays ordered. If `ExecutorCompletionService.take()` is used, results arrive in completion order and need a reordering mechanism before assembly.

**A common mistake:** calling `ExecutorService.submit` repeatedly and letting each task write directly to the same `OutputStream` via `out.write(data)`. Write order is then dictated by thread scheduling; even if individual `write` calls do not interleave bytes, blocks can still be out of order.

## 2. Partitioning a File by Byte Position

For a file of `fileSize` bytes and block size `chunkSize > 0`, the number of blocks is:

\[
\text{chunkCount}=\left\lceil\frac{\text{fileSize}}{\text{chunkSize}}\right\rceil.
\]

Block `i` (0-based) has:

- `offset = i * chunkSize` (use `long` for large file positions).
- `length = min(chunkSize, fileSize - offset)`.
- Byte range is `[offset, offset + length)`, i.e., inclusive start, exclusive end.

Example: a 15-byte file with `chunkSize = 4` → four blocks at offsets 0, 4, 8, 12; lengths 4, 4, 4, 3 respectively. An empty file has 0 blocks; do not create read tasks past EOF.

With `FileChannel.read(ByteBuffer dst, long position)`, `position` is an **absolute** byte offset. This API suits multiple workers reading disjoint regions of the same channel without contending on the channel's sequential read position. Each worker must use **its own `ByteBuffer`**, never sharing one buffer's `position/limit` across threads.

Keep in mind:

- A single `read` call **does not guarantee filling the buffer**. Always loop until the block's full byte count is read, EOF is hit, or an error occurs.
- `FileChannel.size()` and input offsets must correspond to **a stable file** during processing. If another party truncates, appends, or overwrites the file while reading, chunking based on initial size is no longer a consistent snapshot.
- `FileChannel` has a thread-safe API per channel contract, yet calling parallel reads **does not guarantee higher throughput**: the provider, filesystem, cache, HDD/SSD, and I/O load may throttle or serialize operations.

Do not split bytes arbitrarily and call `new String(bytes, UTF_8)` on **each block** if characters must stay intact: a UTF-8 code point can be sliced across two blocks. Read/assemble bytes before decoding, or explicitly split at character/line boundaries using a stateful decoder. The example below assembles **raw bytes verbatim**; it does not transform each block as text.

## 3. Two Different Kinds of Concurrency Limits

`Executors.newFixedThreadPool(3)` caps concurrently executing tasks at around 3, yet **does not automatically bound submitted tasks**: a fixed pool's work queue can grow huge. If the program creates a `Future` for every block of a multi-terabyte file, memory can still grow with task count even with only 3 active workers.

Separate two parameters:

| Limit | Purpose | Example |
| --- | --- | --- |
| `WORKERS` | Concurrent task-executing workers; affects CPU, IOPS, and read contention | `2` |
| `MAX_IN_FLIGHT` | Tasks submitted whose results are not yet taken/written; bounds task queue, futures, and waiting buffers | `2` |
| `CHUNK_BYTES` | Data memory size per block; affects syscall count and memory pressure | `4` in demo, typically larger in practice |

With bounded byte assembly, bytes of submitted blocks waiting to be consumed are roughly **`MAX_IN_FLIGHT × CHUNK_BYTES`** in the worst case, plus `OutputStream` buffers, task structures, system buffers, and other processing components. This is an application-level estimate, not the exact JVM RSS limit.

If each task produces variable-sized outputs (e.g., decompression or generating many objects), you must bound **output size** as well: capping task count alone may not cap total memory if one task can produce gigabytes.

A clean work-dispatching mechanism is a **sliding window**: only submit while unconsumed tasks are below `MAX_IN_FLIGHT`; take one result in order, write it to output, release that block's data, and only then open a slot for a new task. When the output slows down, reading slows down too (*backpressure*), rather than accumulating without bound.

## 4. Runnable Java 17+ Example: Concurrent Reads, Offset-Ordered Writes

The program below creates a small source file for deterministic stdout, then copies it via multiple absolute-offset reads. `copyOrdered` can use the same pattern for large files without holding the whole file in RAM.

Create `OrderedParallelRead.java`:

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Deque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class OrderedParallelRead {
    private static final int CHUNK_BYTES = 4;
    private static final int WORKERS = 2;
    private static final int MAX_IN_FLIGHT = 2;

    private record Block(long index, byte[] bytes) { }

    private static Block readBlock(
            FileChannel channel, long index, long offset, int length)
            throws IOException {
        ByteBuffer buffer = ByteBuffer.allocate(length);

        while (buffer.hasRemaining()) {
            long position = offset + buffer.position();
            int n = channel.read(buffer, position);
            if (n < 0) {
                throw new EOFException("File changed or ended early");
            }
            if (n == 0) {
                throw new IOException("No progress reading a file block");
            }
        }
        return new Block(index, buffer.array());
    }

    private static long copyOrdered(Path source, Path destination)
            throws Exception {
        // Open output stream with CREATE_NEW to avoid overwriting existing files.
        try (FileChannel channel =
                     FileChannel.open(source, StandardOpenOption.READ);
             OutputStream out = Files.newOutputStream(
                     destination, StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            ExecutorService executor =
                    Executors.newFixedThreadPool(WORKERS);
            Deque<Future<Block>> inFlight = new ArrayDeque<>();

            long fileSize = channel.size();
            long nextOffset = 0;
            long nextIndex = 0;
            long expectedIndex = 0;

            try {
                while (nextOffset < fileSize || !inFlight.isEmpty()) {

                    // Submit more tasks only while the window has room.
                    while (nextOffset < fileSize
                            && inFlight.size() < MAX_IN_FLIGHT) {
                        final long offset = nextOffset;
                        final long index = nextIndex++;
                        final int length = (int) Math.min(
                                (long) CHUNK_BYTES, fileSize - nextOffset);

                        inFlight.addLast(executor.submit(
                                () -> readBlock(
                                        channel, index, offset, length)));
                        nextOffset += length;
                    }

                    // The head future in the queue is the lowest-index
                    // unwritten block. Wait for it even if later blocks finished.
                    Future<Block> oldest = inFlight.removeFirst();
                    Block block;
                    try {
                        block = oldest.get();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        throw e;
                    }

                    if (block.index() != expectedIndex) {
                        throw new IOException("Unexpected block order");
                    }
                    out.write(block.bytes());
                    expectedIndex++;
                }

                return expectedIndex;
            } finally {
                // Cancel unused work on error; shut down pool upon completion.
                for (Future<Block> future : inFlight) {
                    future.cancel(true);
                }
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path dir = Files.createTempDirectory("ordered-read-");
        Path input = dir.resolve("source.bin");
        Path output = dir.resolve("copy.bin");

        Files.writeString(input, "ABCDEFGHIJKLMNO",
                StandardCharsets.UTF_8);

        long blocks = copyOrdered(input, output);

        System.out.println("blocks=" + blocks);
        System.out.println("output="
                + Files.readString(output, StandardCharsets.UTF_8));
        System.out.println("equal=" + Arrays.equals(
                Files.readAllBytes(input),
                Files.readAllBytes(output)));
    }
}
```

Compile/run in the file's directory using JDK 17 or newer:

```bash
javac -encoding UTF-8 OrderedParallelRead.java
java OrderedParallelRead
```

Deterministic stdout:

```text
blocks=4
output=ABCDEFGHIJKLMNO
equal=true
```

**Why is the output right even if tasks finish out of order?**

1. Task 0 reads 4 bytes from offset 0; task 1 reads from offset 4; followed by 8 and 12 (the final length is only 3 bytes).
2. Each `readBlock` creates its own `ByteBuffer`, loops positional reads until `length` is met, and returns `Block(index, bytes)`.
3. `inFlight` stores futures **in submit order**, which is also offset order; at most 2 unconsumed futures exist.
4. The consumer takes `removeFirst().get()` and only writes the block matching `expectedIndex`. If block 1 finishes earlier than block 0, it waits and cannot be written ahead of block 0.
5. Each block's data is written before opening a slot for more work; `OutputStream` has **only one writer thread**, avoiding output position races.
6. The `Arrays.equals` line is only for proving the **15-byte fixture**; for large files, verify with a streaming checksum rather than `Files.readAllBytes` on the entire file.

**Error management note:** The example cancels remaining futures in the window and calls `shutdownNow()` on exit. `cancel(true)` or `shutdownNow()` only requests interruption and does not guarantee tasks or blocking I/O stop immediately. In systems requiring clean shutdown, wait for pool termination using `awaitTermination` with a timeout, handle the interrupted flag, and ensure resources still used by tasks are not closed prematurely. On failure, the created output file may contain only the beginning; do not publish it as a finished artifact.

In the demo, `CHUNK_BYTES=4` and `MAX_IN_FLIGHT=2` are deliberately small to make block counts visible. For large datasets, measure before picking real sizes.

## 5. Why Not Submit All Blocks at Once?

An easy-to-write approach with poor scalability:

```java
// Illustrative snippet, not a standalone program.
List<Future<byte[]>> futures = new ArrayList<>();
for (long offset = 0; offset < size; offset += chunkSize) {
    final long start = offset;
    futures.add(pool.submit(() -> readAt(start)));
}
for (Future<byte[]> f : futures) {
    output.write(f.get());
}
```

This approach can **preserve output order** by iterating over futures sequentially, yet all tasks and futures are created upfront. Without a submit bound, the fixed thread pool's queue, `Future` references, and completed pending results can grow proportionally to file size.

Other common accompanying bugs: using `int` for large file offsets and overflowing; `byte[] data = Files.readAllBytes(bigPath)` accidentally loading the whole file; spawning huge thread counts and causing I/O device contention; writing blocks into one `OutputStream` from multiple workers without numbering or coordination.

The sliding window in the example can make later tasks wait on a slow first task (**head-of-line blocking**). This is the trade-off to keep output ordered and memory bounded by a maximum block count. If per-block processing times vary wildly, consider more uniform block sizes, separating CPU processing from reading, or a suitable credit/scheduling scheme.

## 6. Using CompletionService and a Reorder Buffer

`ExecutorCompletionService` is useful when you want to know **which task finished first**, e.g. for metrics, running independent downstream steps, or reducing idle time. However, `take()` does not return by block index.

Correct assembly model when receiving in completion order:

```text
workers → completed Block(index, bytes)
                   ↓
        pendingByIndex (map)
                   ↓
nextExpected=0 → emit block 0 if available → increment nextExpected
                   ↓
        continue emitting consecutive available blocks
```

Keep `Map<Long, Block> pendingByIndex`, insert results by `index`, and only write when `nextExpected` is present. After writing, drain any consecutive blocks waiting next.

**Resource bound trap:** If every completion immediately triggers submitting a new task while the first block is slow, `pendingByIndex` can grow unboundedly: all later blocks finish, yet none can be emitted. You must bound the **total number of submitted tasks not yet written in order** (including running, queued, and completed tasks sitting in the reorder buffer). Release a “slot” only after the result is actually consumed/written, not merely when a task finishes.

If each block is **written to its own offset** via `FileChannel.write(buffer, position)`, a sequential physical assembly step might be unnecessary. However, you must then guarantee non-overlapping write ranges, handle partial writes, manage target file size, handle mid-way failures, and verify full completion before publishing the file. With compression/encryption formats sharing a header or transforms altering per-block length, output offsets no longer simply equal input offsets.

## 7. Reading by Lines, Characters, and Records: Do Not Treat Byte Chunks as Data Boundaries

Splitting a byte file into `64 KiB` segments can slice a UTF-8 character, a CSV line, a variable-length record, or a log entry in half. If workers decode segments independently, you risk replacement characters, split records, or semantically corrupted assembly.

Approaches:

- **To preserve binary files:** read and assemble exact bytes by offset; do not decode individual blocks. This is the requirement/design of the example.
- **To process line by line:** use a single sequential reader responsible for splitting complete lines and dispatching **batches of lines/records** to workers. Number batches, bound queues/in-flight work, and emit results by batch index; avoid sharing one `BufferedReader` across multiple threads calling `readLine` uncoordinated.
- **To split text files at offsets:** read slightly across boundaries to locate valid record delimiters, and define clearly who owns bytes of boundary-spanning records; UTF-8 decoders must handle multi-byte characters at boundaries. Do not add bytes blindly and drop or duplicate data.
- **To stream records over a network:** consider backpressure, timeouts, retries, and protocol ordering semantics; “internal parallelism” does not automatically keep responses ordered.
- **To use parallel Streams:** `Files.lines(path)` returns a `Stream<String>` that must be closed; `parallel()` does not replace problem-specific memory/I/O bounds. `forEach` does not preserve encounter order, while `forEachOrdered` preserves element order yet may limit concurrency and does not automatically guarantee bounded buffering for custom pipelines.

Even for text data, separating “sequential reading + parallel CPU processing + ordered assembly” is often simpler and more effective than “multiple threads seeking/reading the text file.”

## 8. Error Handling, Task Cancellation, and Atomic File Output

For important files, outputs need a clear lifecycle:

1. Read approved input metadata; if possible, use a snapshot or immutable file during processing. Prevent other jobs from writing/truncating the same file.
2. Create a **temporary file on the appropriate filesystem/directory**, never writing directly to the final published name.
3. Have a single coordinator manage submission and output order. All workers return results or errors; never silently swallow exceptions.
4. When `Future.get()` throws `ExecutionException`, the root cause is in `getCause()`. Stop dispatching, cancel pending tasks, and transition to error state. On `InterruptedException`, restore the interrupt flag and exit.
5. Only when all blocks are processed, `OutputStream` closes cleanly, and verification checks (e.g., size/checksum) pass should you publish the temp file via move/rename. If atomicity is needed, check `Files.move(..., ATOMIC_MOVE)` support; platforms may throw `AtomicMoveNotSupportedException`.
6. On error, delete the incomplete temp file per policy; log offset/index and cause while avoiding exposing sensitive data. Consider limited retries for **idempotent read-only tasks** on immutable inputs; do not retry carelessly when side effects occur.

The complete example in Section 4 intentionally omits file publishing protocols, streaming checksums, and retries. It demonstrates bounding and ordering; in systems requiring durable storage, add the output lifecycle above.

One key detail: if workers perform non-idempotent mutations (e.g., incrementing shared counters, sending notifications), retries risk applying side effects twice. Separate pure per-block computation from ordered commits, or enforce idempotency.

## 9. Choosing Thread Count and Block Size by Measurement

No `WORKERS=8` or `CHUNK_BYTES=1MiB` setting is right for every system.

- On **HDDs**, sequential reads usually beat many random accesses; parallel reads on one disk can increase seeks and slow things down.
- On **SSDs/NVMe**, a few concurrent reads can improve throughput, though once cache is warm or other limits hit, adding threads stops helping.
- If each block has independent **heavy CPU work**, separate the I/O read pool from the CPU pool or balance total workers by profile. The bottleneck may be CPU, memory allocation/GC, or the output disk rather than the input disk.
- Across **many distinct files**, reading files in parallel can bring gains and a simpler structure than slicing one file into countless blocks.
- If the output is a slow sequential stream, it may cap overall speed; adding readers only makes results wait longer.
- Use `long` for sizes/offsets; keep each `byte[]` buffer moderately sized (`int`), and guard against overflow when multiplying/adding offsets across billions of blocks.

Metrics to measure include throughput (MiB/s), total duration, per-block p95/p99 latency, in-flight task count, total waiting bytes, CPU, GC, context switches, I/O device utilization, and how long the coordinator waits on the head block. Benchmark with sufficiently large files, explicit cold/warm cache states, realistic data, and identical test conditions. Do not conclude “more workers is always faster” from tiny examples.

Depending on needs, `AsynchronousFileChannel` offers async I/O completion APIs, yet callbacks/futures can still complete out of offset order and still require in-flight bounds, reorder buffers, error handling, and closing. It does not remove any of those requirements.

## 10. Common Bugs and Fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Output contains valid blocks in wrong order | Writing in completion order or workers sharing `OutputStream` | Number blocks and assemble by offset/sequence; use one writer |
| Byte regions duplicated or missing | Wrong offset/length math, short final block, uncoordinated shared channel position | Define `[offset, offset+length)`, loop positional reads to full length |
| Only 2 workers yet heap keeps growing | Submitting millions of tasks/futures or buffering all results | Use a bounded in-flight window and write/release block by block |
| Corrupted text characters at boundaries | Decoding UTF-8 across unaligned byte chunks | Decode statefully or split records before processing |
| `Future.get()` hangs long on the first block | First block is slow or blocked; head-of-line | Set timeout/cancellation policies, monitor metrics, consider scheduling strategy |
| Output missing end of file | Reading once assuming buffer filled, or `int` overflow | Loop reads, handle EOF, and use `long` offsets |
| Small files copy fine, breaks when source changes | File truncated/overwritten while reading | Use immutable inputs/snapshots and validation checks |
| Partial output file left behind when one task fails | Writing directly to published path without cleanup | Write to temp, commit on success, handle failures and cleanup |
| Adding threads slows reading down | I/O contention, seeks, cache pressure, or output bottleneck | Measure on real hardware; try sequential and controlled worker/chunk tuning |

## 11. Self-Check Questions

1. A 10-byte file with chunk size 4. How many blocks and what is each block's length? **3 blocks**, lengths 4, 4, 2 respectively; offsets 0, 4, 8.
2. Does a 4-thread fixed thread pool automatically prevent 1 million tasks from being submitted? **No.** You need in-flight/queue bounds beyond thread count.
3. Task 3 finishes before task 2. Can you append task 3's bytes to `OutputStream` right away? **No**, if original file order must be restored and block 2 is not yet written.
4. Why must `channel.read(buffer, position)` run in a loop? **A single read may return fewer bytes than requested.**
5. Does `CompletionService.take()` return results in submit order? **No**, it returns completed tasks; you must number and reorder them for proper assembly.
6. Does increasing workers from 2 to 32 guarantee higher throughput on large files? **No.** The bottleneck may be the I/O device, cache, CPU, RAM/GC, or the writer.
7. Can a UTF-8 text file be decoded independently per arbitrary byte block? **No**, you must maintain decoder state or split on valid record/character boundaries.

**Official API documentation:** Java SE 17 `java.nio.channels.FileChannel` (positional `read`/`write`), `java.nio.ByteBuffer`, `java.util.concurrent.ExecutorService`, `Future`, `ExecutorCompletionService`, `java.nio.file.Files`, and `StandardOpenOption`.