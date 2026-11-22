# Processing Large Files in Chunks Instead of Loading the Entire File into Memory (Java Core I/O)

## 1. The Problem: Files Larger Than the Memory Budget

When a file is only a few kilobytes, reading its entire contents can be very convenient:

~~~java
byte[] bytes = Files.readAllBytes(path);
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

This is an **illustrative snippet**, where `path` is an existing `Path` and requires importing `Files`, `StandardCharsets`. These two calls are convenient for small files with clear size bounds; however, they should not be automatically applied to multi-gigabyte files or untrusted input data.

When reading everything into a `byte[]`, the program needs an array large enough to hold the file contents and may need additional copies during decoding, transformation, or processing. A `byte[]` uses an `int` index; loading a very large file into a single array is also constrained by array size limits and the JVM heap. `Files.readAllBytes` can throw `OutOfMemoryError` or `IOException` for overly large files; `Files.readString` also needs to materialize the entire content string in memory.

**The chunked approach (chunked/streaming I/O)** keeps only a bounded buffer—for example, 8 KiB, 64 KiB, or 1 MiB; reads data into it, processes/writes it out, and then reuses the buffer. When designed properly, the I/O buffer memory **does not grow with the total file size**.

This lesson helps you:

- Compare the full-read model and the chunked-read model, identifying their pros and cons.
- Write standard Java I/O read/write loops for large files, handling EOF and actual byte counts.
- Distinguish `InputStream`/`OutputStream` from `FileChannel`/`ByteBuffer`, especially regarding partial writes.
- Choose a buffer and data transfer mechanism suitable for the workload.
- Avoid integer overflow, data corruption in the final chunk, UTF-8 corruption, hidden memory accumulation, and lack of resource control.
- Understand when simple streaming is not enough—for instance, algorithms that require random access or sorting the entire dataset.

## 2. Two Processing Models

### 2.1. Read All Then Process

~~~text
File on disk: [................................ many GB ................................]
                            |
                            v
                       readAllBytes()
                            |
                            v
Heap:              [......... entire file .........]
                            |
                            v
                      Process / write out
~~~

The typical steps are reading all bytes, creating objects representing the content, transforming, and writing out. Pros: code can be short, with easy random access in the array for sufficiently small data. Cons: peak heap usage and wait time before data is available for processing grow with the file size.

A converter that inadvertently holds the input `byte[]`, an intermediate `String`, and an output `byte[]` simultaneously can increase RAM demand to several times the file size. There is no fixed multiplier formula for every program; it depends on encoding, object structures, algorithms, and GC.

### 2.2. Read in Chunks Then Process/Write Immediately

~~~text
Source file [block 1][block 2][block 3]...[block N]
               |          |         |          |
               v          v         v          v
           [reused 8 KiB buffer] ---> [target file / consumer]
~~~

Typical flow:

1. Allocate a `byte[]` or `ByteBuffer` with a fixed capacity.
2. Read up to a maximum number of bytes into the buffer.
3. Use **the exact number of bytes reported as read**, not always the full buffer size.
4. Write, inspect, or transform the data.
5. Repeat until EOF; close streams/channels and handle errors.

If you only use a single 8 KiB buffer, whether the file is 1 MiB or 100 GiB **does not force that buffer to grow larger**. However, total program memory also includes the JVM, libraries, page cache, queues, and business-level accumulated data; streaming **does not automatically guarantee** low total RAM if each chunk is retained in a `List` or an unbounded cache.

## 3. Commonly Used APIs in Java 17+

| API | Characteristics | When to Consider |
| --- | --- | --- |
| `Files.newInputStream(path)` | Opens an `InputStream` to read bytes from a file | Sequential chunked reading, integrating with parsers/transforms |
| `Files.newOutputStream(path, options...)` | Opens an `OutputStream` to write bytes | Sequential writing, copying/transforming |
| `BufferedInputStream`/`BufferedOutputStream` | Adds buffering for many small operations | When source/target has many small byte I/O calls |
| `FileChannel.read/write(ByteBuffer)` | NIO API with `ByteBuffer`, supporting offsets/channels | When needing random access, position, or buffer control |
| `FileChannel.transferTo/transferFrom` | Transfers data between channels | Copying/pushing large blocks of data; must check actual byte count |
| `Files.copy(source, destination, options...)` | High-level file copy API | When only copying is needed, without per-chunk processing |
| `BufferedReader`/`Files.newBufferedReader` | Reads text by characters/lines | When parser logic operates line by line; need to bound line length |
| `Files.lines(path)` | Returns a lazily read stream of lines | When processing lines sequentially; close the stream, avoid accumulating terminal operations |

**Choose the tool based on requirements**, rather than assuming `FileChannel` is always faster than streams or `transferTo` is always zero-copy. They have different overheads, OS optimizations, and behaviors.

## 4. The Correct Byte Stream Loop

Common pattern:

~~~java
byte[] buffer = new byte[8192];
long totalBytes = 0;

try (InputStream in = Files.newInputStream(source);
     OutputStream out = Files.newOutputStream(
             target, StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n == 0) {
            throw new IOException("No progress while reading file");
        }
        out.write(buffer, 0, n);
        totalBytes += n;
    }
}
~~~

This is an **illustrative snippet** where `source`/`target` are existing `Path`s, requiring imports for `InputStream`, `OutputStream`, `Files`, `StandardOpenOption`, and `IOException`. `target` must not already exist because `CREATE_NEW` is used. A complete runnable program will appear in Section 7.

Essential points:

- `in.read(buffer)` returns **the actual number of bytes read** within the allowed range, or `-1` at end of stream.
- A read call **does not** guarantee filling all 8192 bytes; it might read only a few hundred bytes even when the file still has data.
- `out.write(buffer, 0, n)` uses the exact `n` bytes. Writing `buffer.length` unconditionally would inject stale bytes from the previous read into the output on the final read.
- For a synchronous `OutputStream`, when `write(byte[],off,len)` succeeds, it means the method has written all `len` bytes per the API contract; when it cannot complete, it throws `IOException`. A partial-write loop is not needed **for this `OutputStream.write` call itself**; however, channel APIs have a different contract.
- `long totalBytes` allows counting data larger than 2 GiB; in very long-running processing loops, `long` overflow and business quotas must also be considered.
- `try-with-resources` closes both input and output even when an exception occurs. Closing/flushing and durability on storage devices are separate concerns if the application needs to guarantee data survives power loss.

### EOF and 0 Bytes

With `InputStream.read(byte[])` and a positive-length buffer, a normal blocking file stream makes progress with a positive byte count or `-1`. However, code working through an unusual wrapper/provider should not turn a `0` result into an infinite spin loop; the example above chooses to fail with an error.

**Do not use `in.available() == 0` to detect EOF.** `available()` only estimates how many bytes can be read without blocking—it is **not** the remaining bytes in the file, nor is it a reliable termination condition for an arbitrary stream.

**Do not use `read(...) == buffer.length` to guess whether any file has finished being read.** Each read may return fewer bytes; only `-1` means EOF for `InputStream.read`.

## 5. Why Is the Final Chunk So Easy to Write Wrong?

Suppose a file has 20,003 bytes and the buffer is 8,192 bytes long. Depending on read behavior, one scenario might be:

~~~text
Read 1: 8192 bytes --> write 8192
Read 2: 8192 bytes --> write 8192
Read 3: 3619 bytes --> write 3619
Read 4: -1         --> finish
Total: 20003 bytes
~~~

There is **no guarantee** that the first three reads match the example: the API may return shorter chunks. However, the sum of positive reads must equal the number of bytes the application actually received before EOF. Never derive the byte count from the number of iterations multiplied by buffer size.

A common bug:

~~~java
int n = in.read(buffer);
if (n > 0) {
    out.write(buffer); // WRONG: always writes 8192 bytes, including stale bytes.
}
~~~

Fix it to:

~~~java
int n = in.read(buffer);
if (n > 0) {
    out.write(buffer, 0, n); // Only write the bytes just read.
}
~~~

These two snippets are **illustrative**, not standalone programs. A real loop must handle `-1` and error cases according to the API.

## 6. Choosing Buffer Size: There Is No Magic Number

Some sizes commonly tested in benchmarks: 4 KiB, 8 KiB, 64 KiB, 256 KiB, or 1 MiB. There is no "bigger buffer is always better" rule.

| Buffer | Potential Benefit | Cost/Consideration |
| --- | --- | --- |
| Very small (a few dozen bytes) | Less heap per thread | Very many read/write calls, high overhead |
| 4–16 KiB | Easy to use, low memory per operation | May not be optimal for high throughput |
| 64–256 KiB | Fewer read/write rounds in sequential copy | Increases memory with concurrent tasks |
| 1 MiB or larger | Can help in some large workloads | Consumes lots of RAM if thousands of requests hold buffers simultaneously |

For example, with 2,000 concurrent tasks, each holding a 1 MiB buffer, the buffers alone can occupy roughly **2,000 MiB** (~1.95 GiB), excluding everything else. If each buffer is 8 KiB, total buffer memory is around **15.6 MiB**. Therefore, budget memory by **buffer size × concurrency × buffers per task**.

Benchmarks must fix the dataset, environment, storage device, page cache state, and concurrency level. Measure throughput, CPU, garbage collection, heap/RSS, and P95/P99 latency instead of just a single warm-cache run.

### Outer-Layer Buffering

`BufferedInputStream` or `BufferedOutputStream` is useful when many small read/write calls (e.g., byte-by-byte) cause overhead. If you already call `in.read(buffer)` with 64 KiB chunks, adding another buffer layer does not automatically improve performance; sometimes it just adds another copy layer. Measure on the real workload.

### Should You Allocate a Buffer in Every Loop Iteration?

Avoid:

~~~java
while (moreData) {
    byte[] data = new byte[8192]; // Repeated reallocation.
    // Read and process.
}
~~~

This is an **anti-pattern snippet** where `moreData` represents the loop condition. Allocating a new array on every read creates unnecessary GC pressure. For simple tasks, allocate the buffer **once before the loop** and reuse it.

If pooling buffers across multiple tasks, clearly define ownership. Never hand the same mutable buffer to two threads reading/writing concurrently without safe coordination.

## 7. Complete, Verifiable Java 17+ Example

The program creates a source file containing **12 blocks of 8,192 bytes of `'A'`** and **3 bytes `XYZ`**, totaling **98,307 bytes**. It then copies it to a new file using an 8 KiB buffer, counts copied bytes, verifies target content, and cleans up temporary data upon completion.

So that stdout does not depend on whether `InputStream.read` returns shorter or longer chunks in different environments, the program only prints **total bytes**, **buffer size**, and **content comparison**; it does not assert a fixed number of read calls.

Save as **`ChunkedFileCopyDemo.java`**:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;

public class ChunkedFileCopyDemo {
    private static final int BUFFER_SIZE = 8192;

    public static void main(String[] args) throws IOException {
        Path directory = Files.createTempDirectory("chunked-copy-");
        Path source = directory.resolve("source.bin");
        Path target = directory.resolve("target.bin");

        try {
            makeSource(source);
            long copied = copyByChunks(source, target);

            System.out.println("Source bytes: " + Files.size(source));
            System.out.println("Copied bytes: " + copied);
            System.out.println("Buffer bytes: " + BUFFER_SIZE);
            System.out.println("Content equal: "
                    + (Files.mismatch(source, target) == -1));
        } finally {
            Files.deleteIfExists(target);
            Files.deleteIfExists(source);
            Files.deleteIfExists(directory);
        }
    }

    private static void makeSource(Path source) throws IOException {
        byte[] block = new byte[BUFFER_SIZE];
        Arrays.fill(block, (byte) 'A');

        try (OutputStream out = Files.newOutputStream(
                source,
                StandardOpenOption.CREATE_NEW,
                StandardOpenOption.WRITE)) {
            for (int i = 0; i < 12; i++) {
                out.write(block);
            }
            out.write("XYZ".getBytes(StandardCharsets.US_ASCII));
        }
    }

    private static long copyByChunks(Path source, Path target)
            throws IOException {
        byte[] buffer = new byte[BUFFER_SIZE];
        long total = 0;

        try (InputStream in = Files.newInputStream(source);
             OutputStream out = Files.newOutputStream(
                     target,
                     StandardOpenOption.CREATE_NEW,
                     StandardOpenOption.WRITE)) {

            int n;
            while ((n = in.read(buffer)) != -1) {
                if (n == 0) {
                    throw new IOException("No progress while reading");
                }
                out.write(buffer, 0, n);
                total = Math.addExact(total, n);
            }
        }
        return total;
    }
}
~~~

Compile and run commands:

~~~bash
javac -encoding UTF-8 ChunkedFileCopyDemo.java
java ChunkedFileCopyDemo
~~~

**Expected stdout when temporary files are created and copied successfully:**

~~~text
Source bytes: 98307
Copied bytes: 98307
Buffer bytes: 8192
Content equal: true
~~~

### Detailed Explanation

1. `makeSource` writes 12 × 8,192 = 98,304 bytes of `A`, then appends exactly three ASCII bytes `XYZ`. The total is 98,307 bytes; the source is created on disk via multiple writes, not via a single 98,307-byte array.
2. `copyByChunks` allocates **one** `byte[8192]`. File size does not affect the buffer capacity; the program reuses it after each write completes.
3. `in.read(buffer)` can return any byte count allowed by the API contract. `out.write(buffer, 0, n)` ensures stale bytes left in the buffer are not written, especially on the final block.
4. `Math.addExact(total, n)` detects `long` overflow with an exception rather than silently wrapping around to negative numbers. For the short demo file, overflow cannot happen.
5. `CREATE_NEW` refuses to overwrite an existing target file.
6. `Files.mismatch(source, target) == -1` confirms that the byte contents of the two files are identical after closing the streams. This operation reads additional data to compare, suitable for demo verification but carries extra I/O cost for very large production files.
7. `finally` cleans up both temporary files and the temporary directory when done. If I/O fails, the method throws an exception; the program does not print a false success result.
8. The final block of data may be returned in one or multiple `read` calls; **stdout remains the same** because of counting actual bytes and comparing contents, not because the API guarantees the last read is exactly 3 bytes.

## 8. Version Using FileChannel and ByteBuffer

`FileChannel` is suitable when you need positional operations, random read/write, or using `ByteBuffer` in NIO. Sequential streaming pattern:

~~~java
ByteBuffer buffer = ByteBuffer.allocate(64 * 1024);
long total = 0;

try (FileChannel src = FileChannel.open(source, StandardOpenOption.READ);
     FileChannel dst = FileChannel.open(
             target, StandardOpenOption.CREATE_NEW,
             StandardOpenOption.WRITE)) {

    while (src.read(buffer) != -1) {
        buffer.flip(); // Read the bytes just received from buffer to write out.

        while (buffer.hasRemaining()) {
            int n = dst.write(buffer);
            if (n == 0) {
                throw new IOException("Channel write made no progress");
            }
            total = Math.addExact(total, n);
        }
        buffer.clear(); // Ready to receive the next chunk.
    }
}
~~~

This is an **illustrative snippet**, requiring imports for `java.nio.ByteBuffer`, `java.nio.channels.FileChannel`, `java.nio.file.Files`, `java.nio.file.Path`, `StandardOpenOption`, and `java.io.IOException`; `source`/`target` are existing `Path`s. For use in environments with special providers, you should also handle `src.read(...) == 0` under a no-progress policy rather than hot-looping.

Important differences compared to `OutputStream`:

- `FileChannel.write(ByteBuffer)` can return **fewer** bytes than `buffer.remaining()`; the `while (buffer.hasRemaining())` loop ensures the entire chunk just read is flushed before reusing the buffer.
- `ByteBuffer.flip()` switches from writing data into the buffer to reading data out of it to send.
- `ByteBuffer.clear()` resets `position/limit`, **without erasing bytes**. Only do this after the entire chunk has been written.
- If `FileChannel.read(buffer)` returns `0`, `buffer.flip()` produces a region with no remaining bytes; the example does not busy-spin on the inner write loop because it won't execute, though the outer loop continues immediately. With unusual providers or non-blocking channels, an appropriate backoff/readiness policy is needed.

### Should You Use a Direct Buffer?

`ByteBuffer.allocateDirect(size)` creates a direct memory region outside the Java heap per JVM/provider capabilities and can reduce some copies during native I/O. In return, allocation/cleanup has overhead and native memory still needs monitoring. Do not create a new direct buffer in every read iteration; reuse it across an appropriate lifecycle. Never assume a direct buffer is faster than a heap buffer on every platform.

## 9. FileChannel.transferTo/transferFrom and Large Files

If the goal is solely to transfer bytes from a file to another channel, you can consider:

~~~java
long remaining = sourceChannel.size();
long offset = 0;

while (remaining > 0) {
    long n = sourceChannel.transferTo(
            offset, remaining, destinationChannel);
    if (n == 0) {
        throw new IOException("Transfer made no progress");
    }
    offset += n;
    remaining -= n;
}
~~~

This is an **illustrative snippet**, where `sourceChannel` is an open source `FileChannel`, `destinationChannel` is an open target `WritableByteChannel`, requiring `IOException`. Calling once with a large `count` **does not guarantee** transferring all bytes: the OS may cap each transfer, EOF may arrive early, and the destination may apply backpressure.

Some providers use copy-reduction techniques (commonly called *zero-copy*) for certain channel pairs, but Java does not guarantee `transferTo` is zero-copy in all cases. You must also consider the source changing mid-copy and ensuring the target does not contain leftover stale data.

`Files.copy(source, target)` is a simpler choice when per-chunk processing is unnecessary; prefer high-level APIs before optimizing manually if the business requirement is just copying.

## 10. Processing Text Files in Chunks: Byte Boundaries Differ from Character Boundaries

Raw byte copying can split arbitrarily: when concatenated in order, the output bytes remain identical to the input. However, **text decoding** introduces a new constraint.

UTF-8 represents a character in 1–4 bytes. For example, accented letters or emojis can be split across the boundary between two chunks. If you call:

~~~java
String text = new String(buffer, 0, n, StandardCharsets.UTF_8);
~~~

on **each independent chunk**, you can decode part of a character into replacement characters or corrupted data. This is an illustrative snippet showing the potential bug if UTF-8 bytes are cut across chunks.

### Correct Approaches by Problem

**Approach A — process text line by line with Reader:**

~~~java
try (BufferedReader reader = Files.newBufferedReader(
        path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        process(line);
    }
}
~~~

This is an illustrative snippet with `path` and an application-defined `process(String)` method. `BufferedReader` manages character decoding across internal byte reads; however, `readLine()` still builds **an entire line into a `String`**. A gigabyte-long line still risks running out of memory. If input is untrusted, enforce a line length limit or use a streaming parser with bounded state.

**Approach B — process custom binary or text formats by chunk:** use `CharsetDecoder` with `CoderResult` and retain undecoded trailing bytes in the buffer using `compact()` or equivalent state. Emit only validly decoded characters; manage EOF and incomplete data at the end of the stream. This is more complex but fits when strict control over RAM, framing, or encoding error policies is required.

**Approach C — raw byte copying only:** no decoding needed; use `InputStream`/`OutputStream` or `FileChannel`. This is the simplest option and avoids unintended Unicode transformations.

### Record Boundaries Can Span Across Chunks

Even when data is ASCII, a CSV line, JSON block, or binary record can be split between two reads. The parser must retain **the unprocessed tail** from the previous chunk and join it with the next chunk, or design a state machine that reads tokens/records incrementally.

If a single record can grow unboundedly, a fixed buffer alone is not enough to guarantee RAM: you must enforce `MAX_RECORD_BYTES`, spill the record to temporary storage, or change the protocol/algorithm.

## 11. Large-Scale Processing Is Not Just Copying: Checksums, Compression, Transformation

### 11.1. Streaming SHA-256 Calculation

You can compute a hash without loading the whole file:

~~~java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
byte[] buffer = new byte[64 * 1024];

try (InputStream in = Files.newInputStream(path)) {
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n > 0) {
            digest.update(buffer, 0, n);
        }
    }
}
byte[] sha256 = digest.digest();
~~~

This is an **illustrative snippet** with an existing `path`; requires importing `InputStream`, `Files`, `MessageDigest` and handling `NoSuchAlgorithmException`/`IOException`. Buffer size and digest state do not grow with file size; the SHA-256 result is 32 bytes.

**Caution:** a hash verifies identical content when compared against a **trusted** digest; computing a hash yourself on an untrusted file does not prove the sender is legitimate. If the goal is tamper detection, you need an independent, secure process for receiving/distributing the digest.

### 11.2. Streaming Compression and Decompression

`GZIPInputStream`/`GZIPOutputStream` can wrap I/O streams to compress/decompress over byte streams. However, decompression is where you must watch out for **zip/decompression bombs**: small compressed payloads can expand enormously. You must cap **actual output bytes**, ratio, time, and resources—never use streaming as an excuse to skip quotas.

### 11.3. Stateful Transformations

If transforming data requires knowing previous/next records, you must retain only enough state for the algorithm. Do not sneak the entire file into memory via `List<String> allLines`, `Collectors.toList()`, or an unbounded `ByteArrayOutputStream` and still call the program streaming.

An algorithm like sorting an entire file cannot just use a small buffer while holding all sort keys/data in RAM if the file is larger than RAM. In that case, consider **external merge sort**: split the file into memory-sized runs, sort each run to temporary files, and merge using a bounded queue.

## 12. Backpressure and Multi-Stage Pipelines

Chunked reading bounds memory for **one step**, but a system may consist of multiple steps: read → decode → parse → process → write.

If the consumer is slower than the producer and you push every chunk into an unbounded queue, RAM still grows with the backlog of chunks. You need **backpressure**:

- Use a queue with a concrete capacity; when full, the source must wait/pause or reject/slow down fetching.
- Cap the number of concurrent workers and buffers.
- Only reuse a buffer after the consumer has finished using it.
- Define timeouts, cancellation, and cleanup when one stage fails.
- Monitor queue depth, read/write rates, wait times, throughput, and memory.

In a single-threaded `read -> process -> write` model, backpressure is natural: the next chunk is read only after the current chunk is processed. In async I/O or reactive pipelines, demand/capacity must be coordinated to avoid exceeding the budget.

## 13. Correctness When the Source File Can Change

When processing large files over seconds or minutes, the source may be modified by another application mid-read. Clarify your consistency needs:

- If you only need to copy **the bytes observed during the run**, sequential streaming works; however, a mutating file can yield an inconsistent mixed result.
- If you need an intact copy of **a specific version**, you need snapshots, producer coordination, immutable versions, or an appropriate locking protocol. Reading `Files.size()` beforehand does not freeze the contents.
- If you need to publish the result only when the copy succeeds, write to a **staging file**, verify, and move to the published path according to filesystem capabilities. `Files.move(..., ATOMIC_MOVE)` only provides guarantees if supported by the provider; handle `AtomicMoveNotSupportedException` by design.
- If the target already exists, `CREATE_NEW` refuses overwriting. If business logic permits replacement, define overwrite/truncate and rollback procedures on copy failure.

### Quotas and Untrusted Data

Streaming does not mean infinite files are safe. When accepting external files, bound total bytes, duration, file count, rate, and disk space. Example quota check to prevent overflow:

~~~java
if (n > allowedBytes - totalBytes) {
    throw new IOException("Byte quota exceeded");
}
totalBytes += n;
~~~

This is an illustrative snippet requiring `n > 0`, `totalBytes >= 0`, and `totalBytes <= allowedBytes` prior to the comparison. If the quota is exceeded, **do not write that chunk**. Do not wait until the end to check, as disk/RAM may already be exhausted.

## 14. Performance: What Should You Measure?

If using very large files for benchmarking, compare against the actual storage workload. Key metrics:

| Metric | Meaning |
| --- | --- |
| Throughput (MiB/s) | Actual bytes processed per second |
| Peak heap / native RSS | Evaluates memory pressure and allocations |
| CPU utilization | Detects decoding, copying, or hashing overhead |
| GC pauses / allocation rate | Detects allocating too many objects per chunk |
| Disk I/O, page cache | Distinguishes cache reads from real storage reads |
| P95/P99 latency | Crucial when handling many concurrent requests |
| Queue depth / wait time | Measures backpressure and producer/consumer balance |
| Bytes/records processed successfully | Detects data loss or incomplete processing |

**Do not pick the largest block size just because one single benchmark run looked fast.** Under 1,000 concurrent requests, RAM and GC can flip the rankings. Measure cold/warm cache separately if the target is disk performance.

For large stable files, `Files.mismatch` or post-copy hashing validates content, but verification itself generates extra I/O. Decide business integrity requirements and include this cost in benchmarks.

## 15. Common Mistakes

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Calling `Files.readAllBytes` on uncontrolled file sizes | OOM, excessive heap | Read in chunks, limit input |
| Writing full `buffer.length` even when the last read is shorter | Stale trailing bytes in copy | Write exact actual `n` bytes |
| Using `available() == 0` as EOF | Early stop or wrong logic | Rely on `read() == -1` |
| Using `int` to count total bytes | Overflow on files >2 GiB | Use `long`, check overflow/quota |
| Calling `new byte[8192]` on every loop iteration | Increased allocation/GC | Reuse buffer |
| Calling `ByteBuffer.clear()` before flushing everything | Loss of unwritten data | `flip` then `while(hasRemaining)`, then `clear` |
| Assuming a single `FileChannel.write` writes everything | Incomplete copy | Check return value and loop |
| Decoding UTF-8 independently per byte chunk | Corrupted multi-byte characters | Stateful Reader/CharsetDecoder |
| `readLine()` on text with unbounded line length | Can accumulate a massive single line | Per-line quota or bounded parser |
| Collecting all chunks into an unbounded `List` | Fake streaming, RAM grows with file | Process and release each chunk |
| Unbounded pipeline queue | Slow consumer bloats RAM | Bounded queue/backpressure |
| Not closing streams/channels | Leaked file descriptors, file locks | `try-with-resources` |
| Advancing offset by requested size of `transferTo` | Skipped data on partial transfer | Advance by actual bytes transferred |
| Assuming a file is stable while being written | Mixed-version copy | Snapshot/version/publish protocol |
| Missing quotas and error cleanup | Full disk, half-written target file | In-loop quotas, staging, and cleanup |

## 16. Self-Check Questions

**Q1.** You have a 30 GiB file and a 512 MiB JVM heap. Should you call `Files.readAllBytes`?

**Answer:** No. You cannot fit a 30 GiB file into a `byte[]` or a 512 MiB heap. Process in chunks or use another appropriate file-level API.

**Q2.** Buffer is 8192 bytes; the final `read` returns only 27. Is `out.write(buffer)` correct?

**Answer:** No. You must use `out.write(buffer, 0, 27)` to avoid writing stale bytes.

**Q3.** `FileChannel.write(buffer)` returns 2000 when 8192 bytes remain. What should you do?

**Answer:** 6192 bytes remain in the buffer. Keep writing until `!buffer.hasRemaining()` before reusing the buffer.

**Q4.** Does streaming with a 64 KiB buffer guarantee the application uses exactly 64 KiB of RAM?

**Answer:** No. That is only one buffer. The JVM, parsers, queues, caches, native memory, and other tasks still require RAM.

**Q5.** Why can `new String(bytes, UTF_8)` on each 8 KiB chunk fail even on a valid text file?

**Answer:** Chunk boundaries can split between the UTF-8 bytes of a single character. Use a stateful Reader or CharsetDecoder.

**Q6.** If there are 500 tasks, each holding a 1 MiB input buffer and a 1 MiB output buffer, roughly how much memory do the buffers alone consume?

**Answer:** 500 × 2 × 1 MiB = 1000 MiB (~0.98 GiB), excluding other heap/runtime usage.

**Q7.** Does chunked file reading automatically provide a consistent snapshot while a producer is writing?

**Answer:** No. You must coordinate versioning/snapshots or a safe publication protocol.

**Q8.** When is `Files.copy` better than writing a manual streaming loop?

**Answer:** When you only need to copy a file and do not need to inspect, enforce chunk-level limits, or perform custom data transformations; the high-level API is shorter and easier to maintain.

## 17. Key Takeaways

- **Chunked processing** keeps I/O buffer memory independent of file size, provided data is processed and released rather than accumulated.
- **Always rely on the actual bytes read**; `-1` is EOF for `InputStream`, and `out.write(buffer,0,n)` prevents writing stale bytes in the final chunk.
- With **`FileChannel`**, handle partial writes, `flip`/`clear`, and progress checks.
- For **text/records**, do not confuse byte chunk boundaries with character or record boundaries.
- **Buffer size × concurrency** drives your RAM budget; queues must enforce backpressure.
- When data is large or untrusted, combine **quotas, cleanup, staging, integrity checks, and measurement** instead of simply increasing JVM heap.
