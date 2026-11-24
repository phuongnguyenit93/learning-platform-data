# 4.4 Hashing Large Files with Streams or ByteBuffer

## 1. Objective and Nature of the Problem

A cryptographic hash function such as **SHA-256** transforms an arbitrarily long sequence of bytes into a fixed-length value: SHA-256 produces **32 bytes = 256 bits = 64 hex characters**. When hashing a file, the input is **every byte of the file's contents, in exact order**, from the first byte to the last. File path, filename, modification time, and file size are not automatically included in the digest.

For files of several GB or larger than JVM memory, the following approach easily causes excessive RAM usage, array size limits, or `OutOfMemoryError`:

```java
// Illustrates what NOT to do when a file can be very large.
byte[] allBytes = Files.readAllBytes(path);
byte[] result = MessageDigest.getInstance("SHA-256").digest(allBytes);
```

Instead, keep only a fixed buffer (for example, **64 KiB**), loop until EOF, and call `MessageDigest.update(...)` for **the exact number of bytes actually read**:

```text
File (N bytes)
  | read at most 64 KiB per iteration
  v
[buffer] -> digest.update(chunk 1) -> digest.update(chunk 2) -> ...
                                                  |
                                                  v
                                           digest.digest()
                                                  |
                                                  v
                                   SHA-256: 32-byte result
```

In mathematical notation, if the file contents are split into `c1, c2, ..., ck`, the correct result is `SHA256(c1 || c2 || ... || ck)`, where `||` denotes byte concatenation. Streaming hashing must equal whole-file hashing **when both process the exact same byte sequence**. Chunk boundaries do not alter the digest.

- **Time:** approximately O(N) hashing and I/O read operations for an N-byte file.
- **Application memory:** approximately O(B), where B is the fixed buffer size; does not grow with file size. The provider may use additional internal state/memory.
- **Result:** `MessageDigest.digest()` finalizes and resets the object. For a new file, create a new `MessageDigest` or ensure a reset; do not accidentally merge two files' data.
- **Important condition:** reading the same file at two different times **does not mean** reading the same data snapshot if the file is being modified.

This lesson focuses on three approaches in Java 17+: `InputStream` + `byte[]`, `FileChannel` + `ByteBuffer`, and the `DigestInputStream` variant. It then examines files larger than 2 GiB, digest comparison, performance, consistency, and common mistakes.

## 2. Which API Should You Choose?

| Approach | Primary APIs | Strengths | Points to Watch |
| --- | --- | --- | --- |
| Sequential stream reading | `Files.newInputStream(path)`, `InputStream.read(byte[])`, `MessageDigest.update(byte[], off, len)` | Simple; works for streams from files, network, or download payloads | Hash only the `count` bytes just read; use try-with-resources; never use `available()` to detect EOF |
| Reading via NIO | `FileChannel.open(path)`, `channel.read(buffer)`, `MessageDigest.update(ByteBuffer)` | Manages file position, integrates cleanly with NIO and direct buffers | Must call `flip()` before `update` and `clear()` before the next read; `update(ByteBuffer)` advances `position` |
| Auto-updating hash stream | `DigestInputStream` | Convenient when an InputStream pipeline already exists | Do not call `update` on the digest a second time; must read to the end to hash the entire file |
| Memory-mapped (when needed) | `FileChannel.map(READ_ONLY, offset, length)` | Can be useful when reading in large windows | In Java 17, a single `MappedByteBuffer` mapping has `size <= Integer.MAX_VALUE`; mappings are not snapshots and have a different lifecycle from regular buffers |

**No single method is fastest by default on every system.** The OS, page cache, storage device, SHA-256 provider, buffer size, and concurrent readers all affect results. Choose `InputStream` first for clarity; consider `FileChannel` when the application already uses NIO or after benchmarking on real workloads.

## 3. Correct `MessageDigest` Lifecycle for Hashing a Single File

```text
MessageDigest.getInstance("SHA-256")
              |
              v
       digest.update(...)   <--- call 1
              |
       digest.update(...)   <--- call 2
              |
               ...
              |
       digest.update(...)   <--- final call, may be shorter than buffer
              |
              v
         digest.digest()
              |
              v
      32-byte SHA-256; digest reset
```

`update(byte[], offset, len)` consumes a slice of an array; you **do not need** to wait for a full 64 KiB before updating. `update(ByteBuffer)` consumes only the bytes between `position` and `limit`. After `digest()`, you do not need to call `reset()` if reusing the object, though creating a dedicated instance per hash avoids state confusion under concurrency.

In particular, **do not** compute `digest()` after each chunk and concatenate those digests. `SHA256(c1) || SHA256(c2)` does not equal `SHA256(c1 || c2)` and is not the file's SHA-256 value. Call `digest()` **only once after reading the entire file**.

## 4. Complete Example: Two Ways to Hash the Same File

The program below performs two independent reads to compare `InputStream` against `FileChannel + ByteBuffer`. If run **with no arguments**, it creates a temporary file containing the exact three ASCII bytes of `"abc"`, then deletes the temporary file. This case yields deterministic output for self-checking. If a path is passed, the program hashes the real file; you can also pass a trusted SHA-256 digest to verify it.

Save the source code as **`FileSha256Demo.java`** (Java 17+):

```java
import java.io.IOException;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.channels.FileChannel;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class FileSha256Demo {
    private static final int CHUNK_SIZE = 64 * 1024;
    private static final String SHA256_ABC =
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";

    private FileSha256Demo() {}

    public static byte[] hashStream(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] chunk = new byte[CHUNK_SIZE];

        try (InputStream in = Files.newInputStream(path)) {
            int count;
            while ((count = in.read(chunk)) != -1) {
                if (count > 0) {
                    digest.update(chunk, 0, count);
                }
            }
        }
        return digest.digest();
    }

    public static byte[] hashChannel(Path path)
            throws IOException, NoSuchAlgorithmException {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        ByteBuffer buffer = ByteBuffer.allocateDirect(CHUNK_SIZE);

        try (FileChannel channel =
                     FileChannel.open(path, StandardOpenOption.READ)) {
            while (true) {
                int count = channel.read(buffer);
                if (count == -1) {
                    break;
                }
                buffer.flip();
                digest.update(buffer);
                buffer.clear();
            }
        }
        return digest.digest();
    }

    public static void main(String[] args) throws Exception {
        if (args.length > 2) {
            throw new IllegalArgumentException(
                    "Usage: java FileSha256Demo [file [trusted-sha256-hex]]");
        }

        boolean temporary = args.length == 0;
        Path path = temporary
                ? Files.createTempFile("hash-demo-", ".bin")
                : Path.of(args[0]);

        try {
            if (temporary) {
                Files.write(path, "abc".getBytes(StandardCharsets.US_ASCII));
            }

            byte[] fromStream = hashStream(path);
            byte[] fromChannel = hashChannel(path);
            System.out.println("stream=" +
                    HexFormat.of().formatHex(fromStream));
            System.out.println("channel=" +
                    HexFormat.of().formatHex(fromChannel));
            System.out.println("same=" +
                    MessageDigest.isEqual(fromStream, fromChannel));

            String trustedHex = temporary
                    ? SHA256_ABC
                    : (args.length == 2 ? args[1] : null);
            if (trustedHex != null) {
                byte[] expected = HexFormat.of().parseHex(trustedHex);
                if (expected.length != 32) {
                    throw new IllegalArgumentException(
                            "Expected a 64-character SHA-256 hex digest");
                }
                System.out.println("expectedMatch=" +
                        MessageDigest.isEqual(expected, fromStream));
            }
        } finally {
            if (temporary) {
                Files.deleteIfExists(path);
            }
        }
    }
}
```

Compile and run with the sample input:

```bash
javac -encoding UTF-8 FileSha256Demo.java
java FileSha256Demo
```

Output:

```text
stream=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
channel=ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad
same=true
expectedMatch=true
```

This hash string is the standard SHA-256 test vector for the exact three bytes `abc`, **not** the hash of a string with a newline character after `abc`.

Run with a real file (replace the path):

```bash
java FileSha256Demo "/data/large-archive.zip"
```

If you received the expected SHA-256 hex from a **trusted source** (for example, a signed and verified manifest), pass it as the second argument:

```bash
java FileSha256Demo "/data/large-archive.zip" "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
```

The hex string in this command only illustrates the argument format, **not the actual checksum of the example file**. When a second argument is supplied, `expectedMatch=true` occurs only if the real file's digest matches the exact 32 expected bytes. If a modified file is compared against a new checksum fetched from the same untrusted source, a match still **does not establish authenticity**.

### 4.1 Explaining the `InputStream` Approach

```java
byte[] chunk = new byte[64 * 1024];
try (InputStream in = Files.newInputStream(path)) {
    int count;
    while ((count = in.read(chunk)) != -1) {
        if (count > 0) {
            digest.update(chunk, 0, count);
        }
    }
}
byte[] sha256 = digest.digest();
```

The snippet above is **an excerpt from the full program**, assuming `path` and `digest` have already been created.

- `read(chunk)` returns **the number of bytes actually read**, which can be smaller than the array capacity (for example, the final chunk might have only 7 bytes). `-1` indicates EOF. Therefore you must call `update(chunk, 0, count)`, **not** `update(chunk)` on every iteration, otherwise leftover old bytes at the tail of the buffer will be hashed again.
- With a positive-length buffer, a normal file stream reads until data is available or EOF is reached. Checking `count > 0` avoids updating anything if a 0-byte read ever occurs.
- `Files.newInputStream` returns a byte stream; `try-with-resources` closes the file even if `read` or `update` throws an exception. Do not rely on `available()` to stop: that method estimates bytes readable immediately without blocking, **not** file size or EOF.
- A single read is not guaranteed to fill the buffer; you must loop until `-1`. Do not convert bytes into a `String` before hashing, because decoding and re-encoding can alter the data.
- With 64 KiB bulk reads, adding `BufferedInputStream` is not strictly necessary; benchmark if your pipeline performs many very small reads.

### 4.2 Explaining `FileChannel` and the `ByteBuffer` Lifecycle

`FileChannel.open(path, StandardOpenOption.READ)` creates a sequential read channel; `FileChannel.read(buffer)` writes bytes into the buffer starting at the current `position` and increments `position` by the number of bytes actually read. The cycle per iteration:

```text
Newly allocated / after clear:
    position=0               limit=capacity (65536)
After channel.read(...), e.g., reading 100 bytes:
    position=100             limit=65536
After buffer.flip():
    position=0               limit=100
After digest.update(buffer):
    position=100             limit=100
After buffer.clear():
    position=0               limit=65536
```

`buffer.flip()` switches the buffer from write mode to read mode: it sets `limit` to the current write position, then resets `position` to 0. `digest.update(buffer)` consumes **exactly** the bytes from `position` to `limit` and advances `position` to `limit`; it does not call `flip` itself and does not modify `limit`. `buffer.clear()` resets the indices to be ready for writing again, **without erasing old contents from memory**.

`FileChannel.read` returns `-1` at EOF, and by API contract may return fewer bytes or 0 bytes. The code still safely runs `flip/update/clear` if `count == 0`; in that case the data range is empty. With `FileChannel` reading a file in blocking mode while the buffer has remaining space, reads normally wait for data or EOF, so no busy-wait loop is needed. For **other non-blocking channels** (such as sockets), you must handle 0-byte returns to avoid CPU spin loops.

`ByteBuffer.allocateDirect(64 * 1024)` allocates a direct buffer, which can avoid some copying during I/O operations, but has higher allocation overhead and uses off-heap memory. `ByteBuffer.allocate(...)` creates a heap buffer that is also compatible with `MessageDigest.update(ByteBuffer)`. Direct buffers are not guaranteed to always be faster and should not be allocated in large sizes per request without accounting for memory budgets.

### 4.3 Why Can Files Larger Than 2 GiB Be Processed?

`InputStream.read` and `FileChannel.read(ByteBuffer)` only need to know **the byte count of a single chunk** (type `int`). The loop can execute tens of thousands of times for multi-GB files; total file size is tracked via metadata or `long` when needed. Neither a `byte[]` sized to the entire file nor fitting the total file length into a single `ByteBuffer` is required.

A single 64 KiB buffer can be reused to read a 5 GiB or 50 GiB file as long as the filesystem/provider supports it and the program has sufficient time and I/O bandwidth. The size ceiling is imposed by the filesystem/API/data source length, **not** by 64 KiB. If progress reporting is needed, maintain a `long processed += count` counter per read, rather than adding `buffer.capacity()`.

## 5. Testing Empty Chunks, Exact Boundaries, and +1 Byte Remainder

A common bug appears only when a file has `65536 + 1` bytes: the final read contains 1 byte, yet the author hashes the entire 65536-byte array. Another mistake is forgetting `flip`, causing `ByteBuffer` to feed unread regions. Testing multiple lengths around buffer boundaries catches these bugs.

Save as **`HashBoundaryCheck.java`** in the same directory as `FileSha256Demo.java`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;

public final class HashBoundaryCheck {
    public static void main(String[] args) throws Exception {
        int[] lengths = {0, 1, 65535, 65536, 65537, 131079, 1048577};
        Path file = Files.createTempFile("hash-boundaries-", ".bin");

        try {
            for (int length : lengths) {
                byte[] data = new byte[length];
                for (int i = 0; i < length; i++) {
                    data[i] = (byte) (31 * i + 7);
                }
                Files.write(file, data);

                byte[] expected = MessageDigest.getInstance("SHA-256")
                        .digest(data);
                byte[] stream = FileSha256Demo.hashStream(file);
                byte[] channel = FileSha256Demo.hashChannel(file);
                if (!MessageDigest.isEqual(expected, stream)
                        || !MessageDigest.isEqual(expected, channel)) {
                    throw new AssertionError(
                            "Mismatch for file length " + length);
                }
            }
            System.out.println("cases=" + lengths.length);
            System.out.println("allMatch=true");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
```

`HashBoundaryCheck` is a **complete runnable** program, though it **depends** on the two methods `FileSha256Demo.hashStream` and `FileSha256Demo.hashChannel` from the previous example class. The program generates temporary files with reproducible binary data, tests 7 sizes, and deletes the file when finished. The test dataset is only ~1 MiB in the largest case, so holding the full array in memory **for testing** is reasonable; this is not a pattern for handling large files in production.

```bash
javac -encoding UTF-8 FileSha256Demo.java HashBoundaryCheck.java
java HashBoundaryCheck
```

```text
cases=7
allMatch=true
```

The tested lengths are **0, 1, 65535, 65536, 65537, 131079, and 1048577** bytes. SHA-256 over the small `byte[]` acts as the independent ground truth for both chunked readers; `AssertionError` indicates a reading path diverged from the original data.

Testing should be expanded to include real files containing zero bytes, bytes with negative values when viewed as Java `byte`, multilingual content in various encodings, and files larger than 2 GiB when the integration environment supports them. For small cases, the empty input has standard SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`; this is a great test vector to verify the loop handles EOF right at the start.

## 6. Variant: `DigestInputStream` Auto-Updates Hash While Reading

If an application already uses an `InputStream` to copy, parse, or read data from another source, you can wrap the stream in `java.security.DigestInputStream` to update the digest **automatically as bytes are read through the wrapper**:

```java
// Illustrative standalone-signature helper; place in a Java class with imports:
// java.io.IOException, java.nio.file.Files, java.nio.file.Path,
// java.security.DigestInputStream, java.security.MessageDigest,
// java.security.NoSuchAlgorithmException.
static byte[] hashWithDigestInputStream(Path path)
        throws IOException, NoSuchAlgorithmException {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (DigestInputStream input =
                 new DigestInputStream(Files.newInputStream(path), digest)) {
        byte[] chunk = new byte[64 * 1024];
        while (input.read(chunk) != -1) {
            // DigestInputStream already called digest.update(...) inside read().
        }
    }
    return digest.digest();
}
```

Explanation: `DigestInputStream.read(...)` invokes `digest.update(...)` while update mode is enabled (enabled by default). **Do not** call `digest.update(chunk)` inside the loop as well: doing so hashes every byte twice. You must read the stream **all the way to EOF** to hash the full contents; closing early only hashes the consumed portion. The `on(false)` method can disable updates if a protocol requires skipping a section (such as a header), though the digest value will then **no longer be the SHA-256 of the entire file**.

This approach fits when you both process incoming data and want to hash the exact data consumed by the pipeline. If you must hash the entire file regardless of how many bytes the business logic reads, separate full consumption from early-stop logic.

## 7. Should You Memory-Map Large Files?

Some systems use `FileChannel.map(READ_ONLY, offset, size)` to create a `MappedByteBuffer` and pass it directly to `MessageDigest.update(ByteBuffer)`. That works under the same `position/limit` rules, but in Java 17, the overload creating `MappedByteBuffer` limits **each mapping to at most `Integer.MAX_VALUE` bytes**. Thus, you cannot map an entire 5 GiB file in a single call.

If mapping is genuinely needed, you must map **in bounded windows** using a `long` offset; hash each window in exact order, and finally call `digest()` once. Algorithmic illustration (skeleton snippet, **not** a standalone program):

```java
// channel: FileChannel opened for READ, digest: SHA-256 MessageDigest
final long WINDOW = 1L << 30; // 1 GiB, smaller than Integer.MAX_VALUE
long size = channel.size();
for (long pos = 0; pos < size; ) {
    long length = Math.min(WINDOW, size - pos);
    ByteBuffer mapped =
            channel.map(FileChannel.MapMode.READ_ONLY, pos, length);
    digest.update(mapped);
    pos += length;
}
byte[] result = digest.digest();
```

Caution: a mapped region has a lifecycle independent of closing the channel; if the file/data is modified or truncated after mapping, OS-dependent behavior can occur, including access faults on the mapped region. Mapping can also increase address-space pressure and make timely release harder to manage. For **purely sequential hashing**, reading via `InputStream` or `FileChannel.read` is usually easier to control and more portable. To conclude that mapping is faster, you must benchmark in the target environment on real files.

## 8. Checksum Verification: Matching Hashes vs. Authenticating Origin

An unkeyed SHA-256 allows checking **whether two byte sequences share the same digest** (with negligible collision probability for SHA-256 when used properly). However, a hash does not prove who the sender is; anyone who can modify both the file and the accompanying hash value can supply a new, self-consistent pair.

A safer verification workflow:

1. Obtain the expected SHA-256 from a **trusted source**: for example, metadata over an authenticated channel, or a manifest with a **digital signature verified** using a trusted key.
2. Decode the hex string into exactly **32 bytes**; standard SHA-256 hex input must be 64 hex characters, without spaces or a `0x` prefix unless the parser handles them.
3. Hash the exact bytes of the file with `MessageDigest`, without decoding to text.
4. Compare bytes using `MessageDigest.isEqual(expected, actual)` after checking lengths. This method avoids stopping at the first differing byte; however, you still need protections around data sources and security boundaries.
5. If they do not match, **reject the file**; never take the newly computed digest to "fix" the expected value unless a trusted source confirms the update.

In the main program, `same=true` only states that both reading methods produced the same digest, **not** that the file is trustworthy. Only when `expected` comes from a trusted manifest does `expectedMatch=true` allow proceeding under the verification workflow's rules. SHA-256 does not encrypt the file and does not hide its contents. Use HMAC or digital signatures when authenticity guarantees are needed; hashing a file alone does not replace a signature.

The output length is **the digest's byte count**, independent of file size; 64 hex characters arise because each byte is formatted as two hex digits. Java 17 provides `HexFormat.of().formatHex(...)` and `HexFormat.of().parseHex(...)`; you do not need to manually convert Java's signed negative bytes via ad-hoc string concatenation.

## 9. Files Modified During Hashing: Consistency and TOCTOU

For very large files, hashing can take noticeable time. Meanwhile, another process might write, truncate, replace, or alter content at that path. A sequential read **is not guaranteed by JCA/FileChannel to be an atomic snapshot** of the file.

- The `InputStream` pass and `FileChannel` pass in the main program run **sequentially**, so if the file is modified between passes, `same=false` can reflect **two different versions** rather than an algorithm bug.
- A file extended while being read can cause bytes to be read up to a different EOF boundary; a truncated file causes failures or incomplete data. Hashing a file while it is being mutated may correspond to no stable state at all.
- Checking `Files.size(path)` or modification time **before and after** only catches some changes; it **does not guarantee** the file was not modified and restored. `FileChannel.lock(...)` is also not a strictly portable mandatory lock across all processes/OSes.
- When reliable evidence is required, hash an **immutable snapshot**, a temporary file that has finished writing and been closed, a copy with write permissions controlled, or a version-pinned storage object. During downloads, you can hash on the fly while writing to a temp file, verify the expected digest upon completion, and only then publish/rename the file via a safe workflow.
- For user-supplied paths, evaluate symlinks, directory traversal, permissions, and path replacement between check and open. File access decisions must rest on application policy, not solely on hashes.

A hash reflects only the bytes consumed by the engine during that execution. If the application needs to guarantee the integrity of data that will **be used later**, it must ensure the exact hashed data is what gets stored, transmitted, or processed—not re-read another file from the same path without version control.

## 10. Common Mistakes and Fixes

| Mistake | Consequence | Correct Practice |
| --- | --- | --- |
| `Files.readAllBytes` on very large files | O(N) RAM; can cause `OutOfMemoryError` or hit array limits | Read fixed chunks with stream/channel |
| `digest.update(chunk)` even when `read` returned 1 byte | Hashes stale leftover data in the array from the previous read | `digest.update(chunk, 0, count)` |
| `while (in.available() > 0)` | Can stop early, dropping data | Read until `read(...) == -1` |
| Calling `digest()` after every chunk | Produces a sequence of per-chunk digests, not the file hash | Finalize only once after reading finishes |
| Forgetting `buffer.flip()` | Hashes wrong memory region, including bytes not from the file | `read → flip → update → clear` |
| Forgetting `buffer.clear()` | Buffer runs out of space; subsequent reads may keep returning 0 | Clear indices after update; do not retain stale position |
| Calling `flip()` twice or misusing `rewind()` | Corrupts valid range/byte count; drops or double-hashes data | Follow exact `position/limit` state on every iteration |
| Using `String`/`Reader` to hash a "text file" | Encoding and newlines can alter original bytes | Hash raw bytes from `InputStream` or `ByteBuffer` |
| Reading into the same `MessageDigest` from multiple threads | Interleaves state across files; corrupted digest | Create a separate digest per task/thread |
| Seeing `same=true` and concluding the file is safe | Both passes could have read a compromised file | Compare against a trusted digest; verify signatures/HMAC when needed |
| Relying on `size`/`lastModifiedTime` as a snapshot | Misses modifications occurring during reading | Use immutable snapshots or a controlled workflow |
| Swallowing `IOException` and still returning a digest | Incomplete data hash is treated as complete | Let the exception fail the operation; discard/reject the result |

**Error handling notes:** `NoSuchAlgorithmException` occurs if no provider supports the algorithm; Java SE is required to support `SHA-256` per the standard list. `IOException` can result from a missing file, permission denied, failing hardware, or mid-stream read errors. If hashing a file fails, never return a "partial" digest as a valid result. `try-with-resources` closes I/O resources even on exception; never swallow exceptions or substitute an empty hash string.

## 11. Performance and Memory: Measure Instead of Guessing

**Start with a moderate buffer** such as 32–256 KiB, e.g., 64 KiB, and measure on real file types and storage devices. Buffers that are too small increase I/O call count; buffers that are too large increase memory footprint (especially with hundreds of concurrent requests) and can pressure heap or direct memory without proportional I/O gains.

**Direct vs. heap ByteBuffer:** direct buffers can benefit certain native I/O paths, yet allocating direct buffers is usually costlier than heap buffers, and the hash provider may still copy data into internal implementations. Do not assume `allocateDirect` yields higher throughput; measure CPU, GC, direct memory, latency, and concurrency together.

**Fair comparisons:** test across file sizes, storage devices, and cache states. Reading twice in a row typically lets the second pass hit the OS page cache; alternate ordering, warm up, and run multiple iterations. Use raw `System.nanoTime` only for rough diagnostics; for serious benchmarking, use tools like JMH and include realistic I/O.

**Do not try to parallelize a digest by concatenating chunk hashes.** SHA-256 of a file has a sequential state dependency; hashing each chunk independently and concatenating does not produce the file's SHA-256. Hash tree/Merkle tree designs are **different protocols** with different outputs, to be used only when specified by the consuming format.

**One task, one instance:** `MessageDigest` is stateful; do not share one instance across multiple files processed in parallel. If optimizing by reusing objects per thread, guarantee `reset()` before each new message and zero concurrent sharing; creating a fresh instance is simpler whenever cost is acceptable.

## 12. Self-Check Knowledge Questions

1. Does an 8 GiB file require creating an 8 GiB byte array to compute SHA-256? **No**; a 64 KiB chunk buffer and repeated `update` calls suffice.
2. If `InputStream.read(chunk)` returns 19 when the buffer has 65536 elements, how many bytes should be hashed? **19 bytes**: `digest.update(chunk, 0, 19)`.
3. A `ByteBuffer` has `position=19, limit=65536` after `channel.read`; what must you do before `digest.update`? **`flip()`**, so the read range covers exactly 19 bytes; call `clear()` after updating.
4. Why not call `digest()` after each chunk? Because `digest()` finishes **one hash** and resets state; individual chunk results **differ** from the hash of concatenated bytes.
5. Does an empty file have a digest? **Yes**: the SHA-256 of a 0-byte stream is `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
6. Does two reading methods producing the same digest prove the file came from the publisher? **No**; you must compare against a digest from a trusted source or verify a digital signature.
7. Why does `lastModifiedTime` not prove a file stayed stable while hashing? A process can modify and restore the timestamp, or edit while reading. You need a snapshot or an immutable versioning workflow.
8. Can you hash a 10 GiB file with a single `MappedByteBuffer` from Java 17 `FileChannel.map`? **No** with a single `MappedByteBuffer` mapping; you must map in windows or use a `read` loop.

## Official API Documentation

- [MessageDigest (Java SE 21): update(ByteBuffer), digest(), reset(), isEqual()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/MessageDigest.html)
- [Files.newInputStream(Path)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html#newInputStream(java.nio.file.Path,java.nio.file.OpenOption...))
- [InputStream.read(byte[])](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
- [FileChannel.read(ByteBuffer) and map()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/FileChannel.html)
- [ByteBuffer: flip(), clear(), position(), limit()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
- [DigestInputStream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/DigestInputStream.html)
- [HexFormat (Java 17+)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HexFormat.html)
