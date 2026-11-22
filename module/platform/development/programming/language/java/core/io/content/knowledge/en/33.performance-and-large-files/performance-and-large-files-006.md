# Bounding Parallel Reads and Ordering Results in Java IO/NIO.2

When a large file needs to be read and processed in chunks, you can split work across multiple threads: the first chunk reads from offset 0, the next from offset `chunkSize`, and so on. However, **reading or processing in parallel** does not mean **results arrive in their original order**. A chunk at the end of the file can finish before the first chunk; if written immediately in completion order, the output data will be scrambled.

Beyond correctness, unbounded parallel reads easily spawn thousands of tasks, numerous data-holding buffers, and excessive concurrent I/O calls. A sound design must simultaneously guarantee:

1. **Exact read ranges:** each chunk reads a defined byte interval, without overlaps or gaps.
2. **Resource bounds:** limit executing tasks, submitted-but-unconsumed tasks, buffered data volume, and open files/channels.
3. **Ordered assembly:** results are written to output in exact chunk-index/offset order, regardless of which thread finishes first.
4. **Error handling and shutdown:** read errors propagate back to the coordinator; remaining tasks and resources are stopped, never publishing an incomplete output file.

This article focuses on Java 17+ mechanisms using `FileChannel`, `ExecutorService`, `Future`, and bounded result queues. Similar principles apply to computing per-chunk checksums, decoding/transforming independent chunks, or assembling processed parts.

## 1. Three Distinct Orders

Suppose a file has 4 chunks:

```text
File by offset:
[0: AAAA] [1: BBBB] [2: CCCC] [3: DDDD]
```

If two workers run concurrently, the schedule might be:

```text
Submit order:       0 → 1 → 2 → 3
Completion order:   1 → 0 → 3 → 2
Required write:     0 → 1 → 2 → 3
Correct output:     AAAABBBBCCCCDDDD
```

- **Submit order:** the order work is submitted to the executor; makes zero promise about completion order.
- **Completion order:** the order tasks actually finish; depends on the scheduler, device speed, cache, and processing duration.
- **Output order:** the business order that must be preserved; for file reassembly, usually ascending offset order.

`Future.get()` waits for a specific task to finish. If you store futures in chunk order and sequentially `get()` and write them, output stays ordered. If using `ExecutorCompletionService.take()`, results arrive in completion order, requiring a reordering mechanism before assembly.

**A common mistake:** calling `ExecutorService.submit` repeatedly and having each task write directly to the same `OutputStream` via `out.write(data)`. Write order is then dictated by thread scheduling; even if individual `write` calls do not interleave bytes, blocks can still land out of order.

## 2. Partitioning a File by Byte Position

For a file of size `fileSize` bytes and chunk size `chunkSize > 0`, the chunk count is:

\[
\text{chunkCount}=\left\lceil\frac{\text{fileSize}}{\text{chunkSize}}\right\rceil.
\]

Chunk `i` (0-indexed) has:

- `offset = i * chunkSize` (use `long` for large file positions).
- `length = min(chunkSize, fileSize - offset)`.
- Byte range `[offset, offset + length)`, i.e., inclusive start, exclusive end.

Example: a 15-byte file with `chunkSize = 4` → four chunks at offsets 0, 4, 8, 12; lengths 4, 4, 4, 3 respectively. An empty file has 0 chunks; do not create read tasks past EOF.

With `FileChannel.read(ByteBuffer dst, long position)`, `position` is an **absolute** byte position. This is the right API for multiple workers reading separate regions of the same channel without contending over the channel's sequential read position. Each worker must use **its own `ByteBuffer`**, never sharing a buffer's `position/limit` across threads.

Note carefully:

- A single `read` call **does not guarantee filling the buffer**. Always loop until all bytes of the chunk are read, EOF is hit, or an error occurs.
- `FileChannel.size()` and input offsets must match **a stable file** during processing. If another actor truncates, appends, or overwrites the file being read, partitioning based on initial size is no longer a consistent snapshot.
- `FileChannel` has a thread-safe API per channel contract, yet issuing parallel reads **does not guarantee higher throughput**: provider, filesystem, cache, HDD/SSD, and I/O load can throttle or serialize operations.

Do not split bytes arbitrarily and call `new String(bytes, UTF_8)` on **each chunk** if characters must remain intact: a UTF-8 code point can be cut between two chunks. Read/assemble bytes before decoding, or design splitting at valid character/line boundaries with a stateful decoder. The example below assembles **verbatim bytes**; it does not transform each chunk as text.

## 3. Two Different Concurrency Limits

`Executors.newFixedThreadPool(3)` caps active executing tasks around 3, yet **does not bound submitted tasks**: a fixed pool executor uses a task queue that can grow enormously. If the program creates a `Future` for every chunk of a multi-terabyte file, memory still grows with task count even though only 3 workers run.

Separate two parameters:

| Limit | Purpose | Example |
| --- | --- | --- |
| `WORKERS` | Concurrent workers executing tasks; affects CPU, IOPS, and read contention | `2` |
| `MAX_IN_FLIGHT` | Tasks submitted whose results are not yet consumed/written; bounds task queue, futures, and pending buffers | `2` |
| `CHUNK_BYTES` | Data buffer size per chunk; affects syscall count and memory pressure | `4` in demo, usually larger in practice |

With bounded byte assembly, the bytes of submitted chunks waiting for consumption are roughly **`MAX_IN_FLIGHT × CHUNK_BYTES`** in the worst case, plus `OutputStream` buffers, task structures, system buffers, and other processing components. This is an application-level estimate, not an exact JVM RSS limit.

If each task produces variable-sized outputs (e.g., decompression or allocating many objects), bound **output size** as well: capping task count alone may not cap total memory if a single task can generate gigabytes.

A sensible dispatch mechanism is a **sliding window**: submit only when unconsumed tasks are fewer than `MAX_IN_FLIGHT`; take one result in order, write it to output, release that chunk's data, and only then free a slot for a new task. When output slows down, read rate slows down accordingly (*backpressure*) instead of accumulating unboundedly.

## 4. Runnable Java 17+ Example: Concurrent Reads, Ordered Writes

The program below creates a small source file for deterministic stdout, then copies it via multiple absolute-position reads. The `copyOrdered` method can apply the same pattern to large files without holding the entire file in RAM.

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

                    // Submit new tasks only while the window has room.
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

                    // The head future is the block with the lowest index
                    // not yet written. Wait for it even if later blocks finished.
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
                // Cancel unused futures on error; shut down pool upon exit.
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

Compile/run in the file's directory on JDK 17 or higher:

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
2. Each `readBlock` creates its own `ByteBuffer`, looping positional reads until `length` bytes are collected, then returns `Block(index, bytes)`.
3. `inFlight` stores futures **in submit order**, which is also offset order; at most 2 unconsumed futures exist at any time.
4. The consumer calls `removeFirst().get()` and only writes the block matching `expectedIndex`. If block 1 finishes earlier than block 0, it waits; it cannot be written before block 0.
5. Each block's data is written before opening a slot for the next task; only **one thread** writes to `OutputStream`, avoiding output position contention.
6. The `Arrays.equals` check is only to prove correctness on the **15-byte fixture**; for large files, verify with a streaming checksum rather than calling `Files.readAllBytes` on the entire file.

**Note on error handling:** The example cancels remaining futures in the window and calls `shutdownNow()` on exit. `cancel(true)` or `shutdownNow()` only requests interruption—it does not guarantee blocking tasks or I/O stop instantaneously. In systems requiring clean shutdown, wait for pool termination via `awaitTermination` with a timeout, handle the interrupted flag, and ensure resources still used by tasks are not closed prematurely. On failure, any created output file may contain only a prefix; do not publish it as a finished product.

In the demo, `CHUNK_BYTES=4` and `MAX_IN_FLIGHT=2` are intentionally small to make chunking visible. For large datasets, measure before selecting real sizes.

## 5. Why Not Submit All Chunks at Once?

An easy-to-write but poorly scalable approach:

```java
// Illustrative code, not a standalone program.
List<Future<byte[]>> futures = new ArrayList<>();
for (long offset = 0; offset < size; offset += chunkSize) {
    final long start = offset;
    futures.add(pool.submit(() -> readAt(start)));
}
for (Future<byte[]> f : futures) {
    output.write(f.get());
}
```

This **preserves output order** because it iterates futures in order, yet every task and future is created upfront. Without a submit limit, the fixed thread pool's queue, references to `Future`s, and pending completed results can grow proportionally to file size.

Other errors often accompany this: using `int` for large file offsets causing overflow; accidentally calling `byte[] data = Files.readAllBytes(bigPath)` to load the whole file; spawning too many threads causing I/O contention; or writing chunks to one `OutputStream` from multiple workers without numbering/coordination.

The sliding window in the earlier example can make later tasks wait behind a slow first task (**head-of-line blocking**). This is a trade-off so output remains ordered while memory is bounded by maximum in-flight chunks. If per-chunk processing times vary wildly, consider more uniform chunk sizes, separating CPU processing from I/O reading, or an appropriate credit-based scheme.

## 6. Using CompletionService and a Reorder Buffer

`ExecutorCompletionService` is useful when you want to know **which task finishes first**—for example, for metrics, independent downstream work, or reducing idle time. However, `take()` does not return results in chunk-index order.

Proper assembly model when receiving in completion order:

```text
workers → completed Block(index, bytes)
                   ↓
        pendingByIndex (map)
                   ↓
nextExpected=0 → emit block 0 if present → increment nextExpected
                   ↓
        continue emitting consecutive available blocks
```

Keep `Map<Long, Block> pendingByIndex`, insert results by `index`, and write only when `nextExpected` is present. After writing, drain consecutive waiting blocks.

**Resource-limit trap:** If you submit a new task every time a completion arrives while block 0 is stalled, `pendingByIndex` can grow without bound: all subsequent blocks finish yet none can be emitted. You must cap **the total number of submitted tasks not yet written in order** (including running, queued, and completed tasks sitting in the reorder buffer). Only return a "slot" after a result is actually consumed/written, not merely when a task completes.

If each block is **written to its own offset** via `FileChannel.write(buffer, position)`, physical sequential reassembly may not be needed. Even then, you must guarantee non-overlapping write ranges, handle partial writes, manage target file size, handle mid-run errors, and verify complete success before publishing the file. For compressed/encrypted formats with shared headers or variable-length block transforms, output offsets no longer trivially equal input offsets.

## 7. Reading Lines, Characters, and Records: Do Not Treat Byte Chunks as Data Boundaries

Splitting a byte file into `64 KiB` segments can bisect a UTF-8 character, a CSV row, a variable-length record, or a log message. If workers decode segments independently, you can get replacement characters, split records, or semantically broken outputs.

Handling approaches:

- **Need to preserve binary files:** read and assemble exact bytes by offset; do not decode per chunk. This is the requirement/design of our example.
- **Need line-by-line processing:** use one sequential reader responsible for splitting complete lines and dispatching **batches of lines/records** to workers. Number batches, bound queue/in-flight counts, and emit results by batch index; avoid letting multiple threads call `readLine` uncoordinated on a shared `BufferedReader`.
- **Need to split text files at offsets:** read slightly past boundaries to locate a valid record delimiter, explicitly define who owns boundary-straddling record bytes, and ensure UTF-8 decoders handle multi-byte boundary sequences. Never add byte offsets blindly and drop or duplicate records.
- **Need record-by-record network streaming:** account for backpressure, timeouts, retries, and protocol ordering semantics; "internal parallelism" does not automatically ensure responses remain ordered.
- **Need parallel Streams:** `Files.lines(path)` returns a `Stream<String>` that must be closed; `parallel()` does not replace memory/I/O bounding policies for your task. `forEach` does not preserve encounter order, whereas `forEachOrdered` preserves element order yet can limit concurrency and does not automatically guarantee bounded buffering for custom pipelines.

Even for text data, separating "sequential reading + parallel CPU processing + ordered assembly" is often simpler and faster than "multiple threads seeking/reading a text file simultaneously".

## 8. Error Handling, Task Cancellation, and Atomic File Output

For critical files, outputs need a clear lifecycle:

1. Read approved input metadata; if possible, use a snapshot/immutable file during processing. Prevent other tasks from writing/truncating the same file.
2. Create a **temp file in the appropriate same filesystem/directory**, never writing directly to the published target name.
3. Have a single coordinator manage submissions and output order. Every worker returns a result or error; never silently swallow exceptions.
4. When `Future.get()` throws `ExecutionException`, the root cause is in `getCause()`. Stop submitting, cancel pending tasks, and transition to an error state. On `InterruptedException`, restore the interrupt flag and exit.
5. Only after all blocks are processed, `OutputStream` closes cleanly, and verification checks (e.g., size/checksum) pass should you publish the temp file via move/rename. If atomicity is required, verify support for `Files.move(..., ATOMIC_MOVE)`; the platform may throw `AtomicMoveNotSupportedException`.
6. On failure, delete incomplete temp files per policy; log offset/index and cause while avoiding leaking sensitive data. You may consider bounded retries for **idempotent read-only tasks** when input is immutable; never retry blindly when writing side effects.

The complete example in Section 4 intentionally omits file publication protocols, streaming checksums, and retries. It demonstrates bounding and ordering; when used in systems requiring durable storage, add the output lifecycle described above.

One crucial detail: if a worker performs non-idempotent mutations (such as incrementing shared counters or sending notifications), retries risk applying side effects twice. Separate pure per-chunk computation from ordered commit, or use an idempotency mechanism.

## 9. Choosing Thread Counts and Chunk Sizes by Measurement

There is no `WORKERS=8` or `CHUNK_BYTES=1MiB` constant right for every system.

- On **HDDs**, sequential reads usually beat multiple random accesses; parallel reads on the same spindle can increase seeks and slow things down.
- On **SSDs/NVMe**, a few concurrent reads can boost throughput, yet once caches warm or other limits hit, adding threads stops helping.
- If each chunk involves heavy independent **CPU processing**, separate the I/O read pool from the CPU pool or balance total workers by profiling. The bottleneck may be CPU, memory allocation/GC, or output disk rather than input disk.
- Across **many distinct files**, reading in parallel per file can yield better gains and simpler structure than slicing one file into countless chunks.
- If output is a slow sequential stream, it may cap overall speed; adding more readers only piles up waiting results.
- Use `long` for sizes/offsets; bound each `byte[]` buffer to a reasonable `int` size, checking multiplication/addition when computing offsets across billions of blocks.

Metrics to measure include throughput (MiB/s), total duration, p95/p99 per-block latency, in-flight task count, total queued bytes, CPU, GC, context switches, I/O device utilization, and coordinator wait time on the head block. Benchmark with sufficiently large files, explicit cold/warm cache states, realistic data, and identical test conditions. Never deduce "more workers is always faster" from a tiny example.

Depending on needs, `AsynchronousFileChannel` offers asynchronous I/O completion APIs, yet callbacks/futures can still complete out of offset order and still require in-flight limits, reorder buffers, error handling, and closing. It does not eliminate those requirements.

## 10. Common Errors and Fixes

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Output has right chunks in wrong order | Writing in completion order or workers sharing `OutputStream` | Number chunks and assemble by offset/sequence; use single writer |
| Repeated or missing byte regions | Wrong offset/length math, short final block, uncoordinated shared channel position | Define `[offset, offset+length)`, read full bytes with positional read |
| Only 2 workers yet heap still grows | Submitting millions of tasks/futures upfront or retaining all results | Use bounded in-flight window and write/release per chunk |
| Corrupted characters at text boundaries | Decoding UTF-8 on unaligned byte chunks | Stateful decoding or split records before processing |
| `Future.get()` hangs on the first block | Slow or blocked head block; head-of-line | Set timeouts/cancellation policies, monitor metrics, review scheduling |
| Output missing end of file | Reading once and assuming buffer filled, or `int` overflow | Loop reads, handle EOF, and use `long` offsets |
| Copy works on small files but breaks when source mutates | File truncated/overwritten mid-read | Use immutable input/snapshots, validate errors |
| Leftover broken output when one task fails | Writing directly to published file without cleanup | Write to temp, commit after success, handle failures and cleanup |
| Adding threads makes reads slower | I/O contention, seeks, cache pressure, or slow output bottleneck | Measure on real hardware; test sequential and vary workers/chunks carefully |

## 11. Self-Check Questions

1. 10-byte file, chunk size 4. How many chunks and what are their lengths? **3 chunks**, lengths 4, 4, 2 respectively; offsets 0, 4, 8.
2. Does a fixed thread pool of 4 threads automatically stop 1 million tasks from being submitted? **No.** You need in-flight/queue limits beyond thread count.
3. Task 3 finishes before task 2. Can you immediately append task 3's bytes to `OutputStream`? **No**, if original file order must be preserved and block 2 is not ready yet.
4. Why must `channel.read(buffer, position)` run inside a loop? **A single read can return fewer bytes than requested.**
5. Does `CompletionService.take()` automatically return results in submit order? **No**, it returns completed tasks; you need indexing and reordering to assemble correctly.
6. Will increasing workers from 2 to 32 always boost large-file throughput? **No.** Bottlenecks may lie in the I/O device, cache, CPU, RAM/GC, or writer.
7. Can a UTF-8 text file be decoded independently per arbitrary byte block? **No**, you must preserve decoder state or split on valid record/character boundaries.

**Official API documentation:** Java SE 17 `java.nio.channels.FileChannel` (positional `read`/`write`), `java.nio.ByteBuffer`, `java.util.concurrent.ExecutorService`, `Future`, `ExecutorCompletionService`, `java.nio.file.Files`, and `StandardOpenOption`.
