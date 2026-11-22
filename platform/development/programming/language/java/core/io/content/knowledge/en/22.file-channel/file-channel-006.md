# FileChannel and Zero-Copy: An Optimization Opportunity, Not a Universal Guarantee

## 1. What Does Zero-Copy Mean in I/O?

When transferring the contents of a file to another channel, the familiar approach is reading bytes from the file into a `ByteBuffer` inside the Java process and then writing those bytes to the destination. For large files, the transfer process can introduce extra copy steps between memory regions and consume CPU.

**Zero-copy** is the name for a group of techniques that **avoid certain unnecessary data copy steps**, especially those that must move the entire content through application memory. On some operating systems, a file-to-socket path can use an OS kernel mechanism such as `sendfile` to reduce the amount of data passing through user space.

In Java NIO, `java.nio.channels.FileChannel` provides methods that can enable this optimization:

- `transferTo(long position, long count, WritableByteChannel target)`: transfers bytes from a region of the **source FileChannel** to the target channel.
- `transferFrom(ReadableByteChannel src, long position, long count)`: transfers bytes from the source channel into a region of the **destination FileChannel**.

**However, calling `transferTo` or `transferFrom` does not prove that the system actually used zero-copy.** Java defines data transfer results at the API level; how it is executed depends on the JDK, operating system, channel type, filesystem, and runtime conditions. An implementation may use an optimized kernel path, use an intermediate buffer, or combine several strategies.

> **Key principle:** Zero-copy is an *optimization capability of a specific data path*, not a promise of "zero byte copies anywhere", "always faster", or "completes in a single call".

## 2. Distinguishing Copying via ByteBuffer vs. Zero-Copy Opportunities

### Copying Flow Through an Application Buffer

A conventional approach:

```text
Source file
    |
    v
FileChannel.read(ByteBuffer)
    |
    v
Application-managed ByteBuffer
    |
    v
WritableByteChannel.write(ByteBuffer)
    |
    v
Target (file, socket, ...)
```

Data is brought into storage that Java can manipulate. The application can inspect, transform, decode, encode, or process chunks of bytes before sending them onward.

### Potentially Optimized Path with FileChannel

With `source.transferTo(offset, count, target)`:

```text
Java Application:
  requests transferring byte range [offset, offset + count)
           |
           v
  FileChannel.transferTo(...)
           |
           v
  JDK / OS Implementation
           |
           +-- Possible: optimized path in kernel
           |
           +-- Otherwise: copy through intermediate buffer
           |
           v
  Target WritableByteChannel
```

The diagram only illustrates **implementation possibilities**. You cannot claim that every transfer via `transferTo` bypasses user space, needs no buffer, or consumes no CPU/memory resources. OS caches, DMA paths, network layers, TLS encryption, and drivers can introduce different processing or copying steps.

What the API guarantees is the **byte-transfer semantics**, the reported byte count transferred, and related state rules; physical optimization lies outside the program's functional contract.

## 3. The `FileChannel.transferTo` Contract

Signature:

```java
public abstract long transferTo(
    long position,
    long count,
    WritableByteChannel target
) throws IOException;
```

Meaning:

- **`position`**: 0-based absolute byte offset in the source FileChannel.
- **`count`**: maximum number of bytes requested to transfer, not the number guaranteed to be transferred.
- **`target`**: writable target channel.
- **Return value**: the number of bytes **actually** transferred, of type `long`, in the range from 0 to `count` when the operation succeeds.

Negative `position` or `count` is rejected. The operation may throw `IOException`, including exceptions related to a channel not opened in the proper mode or already closed.

### Does the Source FileChannel's Position Change?

**No.** The `position` parameter is specific to that transfer call. By `transferTo`'s contract, **`source.position()` is unchanged** after that call.

If the target channel has a current position (for example, a target `FileChannel`), data is normally written starting from the **target's** position, and the target's position can advance by the number of bytes written. When the target is a socket, there is no analogous public file offset to observe.

Example:

```text
Source "ABCDEFGHIJ" (10 bytes)
source.position() = 7

transferTo(2, 3, target)
          |
          +-- requests transferring "CDE"

source.position() after transfer: still 7
target: advances by bytes received, if it has a position
```

Do not use `source.position()` to find the "next offset" in a positional transfer loop; track the starting offset and total transferred bytes yourself.

### When Can `transferTo` Return 0?

There are several causes depending on circumstances:

1. `count == 0`.
2. `position` is already at or beyond the source size.
3. The target cannot accept more data yet, such as a non-blocking socket experiencing backpressure.
4. A specific transfer path or implementation limit could not transfer any bytes in that call.

**`0` does not necessarily mean EOF or "finished".** Distinguish based on expected byte count, source state, target type, and readiness-waiting mechanism. Do not write a `while` loop that repeatedly calls `transferTo` on a `0` result without a progress condition.

## 4. Why Can One `transferTo` Call Transfer Fewer Than `count` Bytes?

The contract allows **partial transfers**. Even when the source file has enough data and the target can receive it, a single call may still transfer fewer bytes than requested due to system limits, I/O conditions, target state, or implementation decisions.

Suppose we want to transfer 10,000 bytes starting at offset 1,000:

| Call | Passed offset | Requested count | Actual bytes transferred | Cumulative bytes transferred |
| --- | ---: | ---: | ---: | ---: |
| 1 | 1,000 | 10,000 | 4,096 | 4,096 |
| 2 | 5,096 | 5,904 | 4,096 | 8,192 |
| 3 | 9,192 | 1,808 | 1,808 | 10,000 |

This is a **hypothetical scenario** for learning offset calculation; it is not a byte count guaranteed by any operating system.

The correct formula after each round with `n > 0`:

\[
nextPosition = startPosition + transferredSoFar
\]

\[
remaining = requestedCount - transferredSoFar
\]

The loop must advance the **source** position explicitly:

```java
long offset = startOffset;
long remaining = byteCount;

while (remaining > 0) {
    long n = source.transferTo(offset, remaining, target);
    if (n == 0) {
        // No progress: check conditions, wait for readiness,
        // or use an appropriate fallback; do not spin indefinitely.
        break;
    }

    offset += n;
    remaining -= n;
}
```

This snippet is **not a standalone program**; it assumes `source`, `target`, `startOffset`, and `byteCount` already exist. It illustrates the looping mechanism, though after the loop the caller must still check `remaining` and decide how to handle missing bytes. When offset addition risks `long` overflow, check bounds beforehand.

**Common mistake:** repeating `source.transferTo(startOffset, byteCount, target)` with the same initial offset without incrementing it. The next call may transfer the same byte slice again and leave duplicate data in the target file or stream.

## 5. Java 17+ Example: `transferTo` with ByteBuffer Fallback

The example creates two temporary files so no network or external resources are needed. The program first **asks** the implementation to use `transferTo`; if a pass makes no progress while bytes still remain to transfer, it performs a pass using `ByteBuffer` and normal `read`/`write` calls. Thus, the program directly illustrates the message "zero-copy is an optimization choice, while copy correctness is a mandatory requirement".

Because a single `transferTo` call is not guaranteed to transfer everything, both the primary path and the fallback path track actual byte counts.

**File `TransferToWithFallbackDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.channels.WritableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TransferToWithFallbackDemo {
    static long copy(FileChannel source, WritableByteChannel target)
            throws IOException {
        long offset = 0;
        long end = source.size();
        ByteBuffer fallback = ByteBuffer.allocate(8);

        while (offset < end) {
            long count = end - offset;
            long n = source.transferTo(offset, count, target);

            if (n > 0) {
                offset += n;
                continue;
            }

            // No progress: fall back to normal read/write
            // for a small chunk, preserving source's position.
            fallback.clear();
            fallback.limit((int) Math.min(
                    fallback.capacity(), end - offset));

            int bytesRead = source.read(fallback, offset);
            if (bytesRead <= 0) {
                throw new IOException(
                    "Source ended or read made no progress");
            }

            fallback.flip();

            while (fallback.hasRemaining()) {
                int bytesWritten = target.write(fallback);
                if (bytesWritten <= 0) {
                    throw new IOException(
                        "Target write made no progress");
                }
            }

            offset += bytesRead;
        }
        return offset;
    }

    public static void main(String[] args) throws IOException {
        Path sourcePath = Files.createTempFile("nio-source-", ".txt");
        Path targetPath = Files.createTempFile("nio-target-", ".txt");

        try {
            Files.writeString(sourcePath, "Hello NIO!",
                    StandardCharsets.US_ASCII);

            try (FileChannel source = FileChannel.open(
                        sourcePath, StandardOpenOption.READ);
                 FileChannel target = FileChannel.open(
                        targetPath, StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING)) {

                source.position(2); // Source position currently in use.
                long copied = copy(source, target);

                System.out.println("So byte da chuyen: " + copied);
                System.out.println("Vi tri nguon: "
                        + source.position());
                System.out.println("Vi tri dich: "
                        + target.position());
            }

            System.out.println("Noi dung dich: "
                    + Files.readString(targetPath,
                            StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(sourcePath);
            Files.deleteIfExists(targetPath);
        }
    }
}
```

Compile and run:

```bash
javac TransferToWithFallbackDemo.java
java TransferToWithFallbackDemo
```

**Exact stdout when I/O operations complete:**

```text
So byte da chuyen: 10
Vi tri nguon: 2
Vi tri dich: 10
Noi dung dich: Hello NIO!
```

Explanation:

1. `"Hello NIO!"` consists of exactly **10 ASCII bytes**.
2. `source.position(2)` sets the source cursor before copying.
3. `source.transferTo(offset, ..., target)` uses the passed offset, **without moving** the source cursor at 2.
4. If `transferTo` reports zero progress, `source.read(fallback, offset)` is a **positional read** call, also leaving `source.position()` unchanged. The newly read slice is sent through `target.write(fallback)` with a loop so no bytes are dropped.
5. `target.position()` advances by the bytes written to the destination file, ending at 10.
6. Either the optimized path or the fallback may be chosen depending on the machine; **stdout contains no line claiming zero-copy occurred**. What learners need to verify is the content and the number of bytes transferred.

This is an example for a **regular file FileChannel with a writable FileChannel target**. With a non-blocking `SocketChannel`, `transferTo == 0` or `write == 0` can be normal backpressure: the program must preserve offset/remaining, register appropriate readiness, and resume on the next round. Do not reuse the blocking example's "throw immediately when write returns 0" policy to handle non-blocking sockets.

## 6. The `FileChannel.transferFrom` Contract

Signature:

```java
public abstract long transferFrom(
    ReadableByteChannel src,
    long position,
    long count
) throws IOException;
```

`transferFrom` pulls at most `count` bytes from channel `src` and places them into the **destination FileChannel** starting at offset `position`.

Direct comparison table:

| Property | `sourceFile.transferTo(pos, count, target)` | `targetFile.transferFrom(src, pos, count)` |
| --- | --- | --- |
| The FileChannel is | **Source** | **Destination** |
| `position` is offset of | Source FileChannel | Destination FileChannel |
| Position of the FileChannel method is called on | **Unchanged** | **Unchanged** |
| Partner channel | `WritableByteChannel` | `ReadableByteChannel` |
| Position of partner channel | May advance by bytes written, if partner has position | May advance by bytes read, if source has position |
| Return value | Actual bytes transferred | Actual bytes transferred |
| Guaranteed to use zero-copy? | **No** | **No** |

**Do not confuse the position of the FileChannel called on with the position of the partner channel.** In `transferTo`, the source FileChannel keeps its position; the receiving target may change its position. In `transferFrom`, the destination FileChannel keeps its position; the source being consumed may change its position.

A notable limitation of `transferFrom`: if the destination offset is **greater than the current size of the destination file**, the API contract transfers no bytes in that call. If you need to write into a region past EOF and create a gap, design an appropriate file-expansion approach rather than assuming `transferFrom` automatically creates gaps past EOF.

`transferFrom` can also transfer fewer than `count` bytes, even when other conditions look favorable; call again with `position + bytesTransferred` when more data must be transferred. Because the source is a `ReadableByteChannel`, you may encounter an unready source or EOF; `0` must be handled according to the specific state.

## 7. Java 17+ Example: `transferFrom` Preserves Destination FileChannel Position

The example receives data from a `ReadableByteChannel` wrapped around a `ByteArrayInputStream`. The program sets `destination.position(2)` yet transfers data into offset **0** using `transferFrom`.

**File `TransferFromDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.channels.Channels;
import java.nio.channels.FileChannel;
import java.nio.channels.ReadableByteChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public class TransferFromDemo {
    public static void main(String[] args) throws IOException {
        byte[] payload = "DATA".getBytes(StandardCharsets.US_ASCII);
        Path path = Files.createTempFile("transfer-from-", ".txt");

        try {
            try (ReadableByteChannel input = Channels.newChannel(
                        new ByteArrayInputStream(payload));
                 FileChannel destination = FileChannel.open(
                        path, StandardOpenOption.READ,
                        StandardOpenOption.WRITE,
                        StandardOpenOption.TRUNCATE_EXISTING)) {

                destination.position(2);

                long copied = 0;
                while (copied < payload.length) {
                    long n = destination.transferFrom(
                            input, copied, payload.length - copied);
                    if (n == 0) {
                        throw new IOException("No transfer progress");
                    }
                    copied += n;
                }

                System.out.println("So byte da chuyen: " + copied);
                System.out.println("Vi tri dich: "
                        + destination.position());
                System.out.println("Kich thuoc tep: "
                        + destination.size());
            }

            System.out.println("Noi dung tep: "
                    + Files.readString(path,
                            StandardCharsets.US_ASCII));
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

Compile and run:

```bash
javac TransferFromDemo.java
java TransferFromDemo
```

**Exact stdout if I/O operations complete:**

```text
So byte da chuyen: 4
Vi tri dich: 2
Kich thuoc tep: 4
Noi dung tep: DATA
```

Four bytes `DATA` are written starting at offset 0. `destination.position()` remains **2**, because `transferFrom`'s `position` argument is specific to the transfer call. The transferred byte count is taken from the **actual return value**, not defaulted to `count`.

This example uses an in-memory stream wrapped as a channel as its source. **You cannot rely on it to claim zero-copy occurred**: this is correct usage of the API contract, while the actual execution path is decided by the JDK and operating system.

## 8. Situations Where Zero-Copy Is Not Used or Is Ineffective

### 8.1. Different Source and Target Types

A file → socket path has OS-level optimization opportunities that differ from file → file, socket → file, or custom channels. Each combination may pass through different adapter layers or buffering mechanisms.

For example, `Channels.newChannel(OutputStream)` enables calling `transferTo` with a `WritableByteChannel` wrapped from an `OutputStream`, but does not guarantee the kernel can transfer directly from the file to the underlying stream without copying through Java.

### 8.2. Encryption, Compression, or Content Transformation

If the application needs **TLS encryption/decryption**, gzip compression, restructuring data, inspecting and modifying bytes, or inserting headers between chunks, the transfer may have to pass through an intermediate processing layer. Some platforms have offload or special integration; however, you must not assume plain `transferTo` automatically handles transformations while retaining zero-copy optimization.

With HTTP, an application can send headers separately and then use an optimized path for the file body **if** the target and execution stack support it. Distinguish specific channel types and protocols carefully.

### 8.3. OS and JDK Limitations

Limits on bytes transferred per call, file size, device, filesystem, handle type, kernel memory, file open flags, or I/O conditions can affect how data is moved. A number of transfers may succeed and then the next call returns 0, or only transfers part of the requested bytes.

Do not assume a fixed maximum value, such as "every call always transfers 2 GB", across all JDKs/OSes. Use the returned byte count and write a progress loop, while measuring in the real environment.

### 8.4. Network Backpressure and Non-Blocking I/O

If the target is a non-blocking socket, its send buffer can fill up. Then `transferTo` may return **0** because it temporarily cannot send; retrying continuously will cause a *busy spin*. The right approach is to retain offset and remaining bytes, wait for the appropriate write-readiness event, and retry when progress is possible.

Do not use `while (remaining > 0) { transferTo(...); }` without handling `0`, as the loop could run forever.

### 8.5. Copies Within the System Can Still Exist

Even when a transfer path avoids copying through an application buffer, data may still reside in the page cache, socket buffers, DMA regions, or other I/O layers. **Zero-copy does not mean total physical copies equal 0** across the entire data lifecycle. "Zero" usually refers to a specific layer of copy steps being eliminated.

### 8.6. Small Files May Not Benefit Noticeably

For very small files, the time spent opening files, creating resources, syscalls, dispatching, establishing connections, and protocol handling can dominate total time. Reducing copy counts does not necessarily reduce end-to-end latency significantly. Performance must be measured for the use case, not inferred from API names.

## 9. Preserving Correctness Matters More Than Choosing an Optimization Path

A reliable file-transfer routine must define **completion conditions** and **incomplete states** before worrying about zero-copy.

Points to clarify:

1. **Does the data source have a fixed size throughout the operation?** If the file is modified, truncated, or extended mid-way, an initial `size()` may no longer reflect current data. When consistency is needed, design snapshots/locks/versioning or an appropriate retry-and-verify workflow.
2. **How many bytes are requested?** Use `long` for offsets, counts, and transfer totals; ensure non-negative values and no overflow on addition.
3. **When `n>0`:** increment offset and decrement remaining based on the actual `n`.
4. **When `n==0`:** do not automatically treat it as done; identify EOF, backpressure, implementation limits, or switch to a fallback path.
5. **On I/O errors:** report the error and close resources; never report success when the destination file was only partially written.
6. **When data durability must be guaranteed:** completing the copy does not mean all bytes are synchronized to the storage device. `FileChannel.force(boolean)` or another safe-write workflow may be needed depending on requirements, though these also have device and filesystem limits.

In a system producing official output files, you can write to a temporary file, verify size/hash, and rename according to an appropriate strategy rather than exposing a half-written file. Details of atomic renaming depend on filesystem support and options used; do not assume every move operation is atomic.

## 10. Comparing `transferTo`, `transferFrom`, and Manual Copying

| Characteristic | `transferTo` | `transferFrom` | `read` + `write` with `ByteBuffer` |
| --- | --- | --- | --- |
| Usage direction | FileChannel → WritableByteChannel | ReadableByteChannel → FileChannel | Source channel → buffer → target channel |
| Absolute file offset | Source offset | Destination offset | Depends on chosen read/write API |
| Position of FileChannel invoked on | Preserved | Preserved | Depends on read/write form |
| Partial transfer | Can occur | Can occur | Can occur |
| Zero-copy | May be optimized | May be optimized | Bytes normally pass through application buffer |
| Suitable when transforming bytes | Not directly | Not directly | More suitable |
| Guaranteed faster? | No | No | No |
| Guaranteed atomic or durable? | No | No | No |

Do not use "fewer lines of code" or "an API named transfer" as proof of copy counts or speed. An appropriate kernel path can significantly reduce CPU usage for large files, yet the magnitude of benefit comes from measurement and specific deployment conditions.

## 11. Measuring and Verifying Optimizations Meaningfully

To conclude whether zero-copy helps an application, separate two questions:

### A. Was the Data Transferred Correctly?

Check functional properties:

- Total actual bytes transferred equals the expected amount of data, or there is an explicit stop reason.
- Output bytes match input bytes over the exact range, via byte comparison or hashing if appropriate.
- Channel and buffer positions match the contract.
- No lost data on partial transfers; no duplicated slices on retries.
- Properly handles EOF, missing bytes, premature close, and mid-transfer errors.

### B. Was the Transfer Path Actually Optimized?

Once functional correctness is established, measure in the real environment: elapsed time, throughput, CPU, bytes allocated in the process, syscall counts, or profiler/tracing metrics if available. Operating systems may provide tools to observe syscalls/kernel behavior (for example, tracing the `sendfile` path on supported systems). However, **seeing a syscall alone does not prove zero copies occur at every layer**.

When benchmarking:

1. Use the same source/target types, same data, blocking mode, buffer sizes, and close/flush policy.
2. Run multiple iterations, separate warmup from measured numbers, and inspect latency distributions rather than a single run.
3. Watch the effect of the OS page cache: cold reads and warm reads can differ dramatically.
4. For network transfers, distinguish application-measured throughput, CPU load, and receiver speed; network pressure/backpressure can mask copy efficiency.
5. Do not compare a path doing verification/encryption with one doing no equivalent work and conclude the difference is entirely due to zero-copy.

**No standard `FileChannel` API returns a flag saying "zero-copy was used on the last call".** Determining the data path requires observation and understanding the actual implementation.

## 12. Common Mistakes

| Assumption or bad practice | Problem | Solution |
| --- | --- | --- |
| "Calling `transferTo` guarantees zero-copy" | Implementation may use a copy fallback | Treat it as an optimization opportunity and measure on the real platform |
| "Zero-copy means zero bytes copied at all layers" | Page cache, drivers, network, and devices still exist | State precisely which copy step is reduced |
| "One `transferTo` sends all `count` bytes" | Partial transfers cause missing data | Check `long n`, advance offset, and loop with control |
| Reusing the old source offset after a partial transfer | Sends duplicate slices | Use `offset + transferredSoFar` |
| "`n == 0` means sending finished" | May be backpressure or a limit | Distinguish remaining data/EOF and waiting mechanism |
| Tight retry loop when `n == 0` | Busy spin | Wait for readiness or switch to an appropriate fallback |
| Assuming `source.position()` increases after `transferTo` | Reads from wrong next position | Maintain offset yourself; source position stays unchanged |
| Assuming `destination.position()` increases after `transferFrom` | Next data is placed at the wrong location | Update destination offset yourself when looping |
| `transferFrom` writing to an offset well past EOF | May transfer 0 bytes per contract | Define and prepare appropriate size/offset |
| Publishing a file after partial write | Readers observe incomplete contents | Verify total bytes and publish after verification |
| Expecting zero-copy to auto-encrypt/transform data | Transfer does not replace a processing pipeline | Choose a processing path suited to the format/protocol |
| Concluding "NIO is always faster than streams" | Depends on size, cache, I/O, and platform | Benchmark fairly for the workload |
| Believing `transferTo` guarantees atomicity and durability | No transaction or persistence guarantee | Design coordination/flushing/recovery separately |

## 13. Practical Scenario: Sending an 8 KiB File Region

Suppose a source is 100 KiB long, and we need to transfer the exact 8 KiB region starting at offset 20 KiB to a `WritableByteChannel`.

Values:

```text
startOffset     = 20 * 1024 = 20480
requestedCount  =  8 * 1024 = 8192
currentOffset   = 20480
remaining       = 8192
```

If the first `transferTo` returns 3,000:

```text
nextOffset = 20480 + 3000 = 23480
remaining  = 8192 - 3000 = 5192
```

If the second returns 2,000:

```text
nextOffset = 23480 + 2000 = 25480
remaining  = 5192 - 2000 = 3192
```

If the third returns **0**, even though `remaining = 3192`, **never report completion**. For a non-blocking socket, save the state `(nextOffset=25480, remaining=3192)` to resume when the socket is ready; for a blocking channel in an appropriate environment, use a fallback/diagnostics or handle the lack of progress.

To complete the transfer region, total bytes **must equal 8192**, and destination bytes must match the source slice `[20480, 28672)`. The source FileChannel may keep `source.position()` unchanged across all `transferTo` calls.

**Do not infer** how many internal copies occurred just from the three numbers `3000, 2000, 0`. They describe the amount of data transferred, not the kernel's byte-transfer mechanism.

## 14. Takeaways

1. **`FileChannel.transferTo` and `transferFrom` can enable zero-copy transfer paths**, yet the Java contract **does not guarantee that mechanism is used**.
2. **`transferTo` preserves the source FileChannel's position**; **`transferFrom` preserves the destination FileChannel's position**. The partner channel may update its state/position according to bytes consumed or received.
3. **The return value is the actual bytes transferred**, not the requested count. Partial transfers must be handled by advancing the offset and reducing remaining by the returned count.
4. **A result of 0 does not necessarily mean EOF or success**; check length, channel state, readiness, or fallback.
5. **Zero-copy does not mean absolutely zero data copies remain**, nor does it replace byte verification, storage durability, consistency, or security.
6. **Correctness first, performance second**: verify destination data, handle errors, and then benchmark/trace on the target platform to evaluate gains.

**References:** Java SE 17 API: `java.nio.channels.FileChannel#transferTo`, `FileChannel#transferFrom`, `java.nio.channels.ReadableByteChannel`, `WritableByteChannel`, `java.nio.ByteBuffer`, and `java.nio.file.StandardOpenOption`.
