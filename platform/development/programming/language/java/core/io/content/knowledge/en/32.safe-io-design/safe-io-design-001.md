# Limiting Input Size and Memory Usage in Java I/O

## 1. Why Is Limiting Data Part of Safe Design?

Java applications often read data from HTTP requests, sockets, uploaded files, ZIP files, logs, message queues, or sources from other systems. Many introductory examples simply read the entire input:

```java
byte[] data = input.readAllBytes();
```

This approach is convenient for **small, trusted, and clearly bounded** data, but it is dangerous if the input size is determined by an external source. A client can send gigabytes of data, a stream may never terminate, or a compressed file can be very small on disk yet decompress into enormous amounts of data. In those cases, the program risks:

- Exceeding the heap limit, throwing `OutOfMemoryError`.
- Creating GC pressure, increasing latency for other requests.
- Occupying CPU, I/O, disk, or network bandwidth for too long.
- Leaving a thread stuck because the input never terminates.
- Allowing denial of service due to disproportionate resource consumption (*resource exhaustion/DoS*).
- Leaving temporary files, partial output, or inconsistent business state after exceeding the limit.

**Goal:** limit the **actual amount of data accepted**, use **buffers with controllable size**, limit concurrent requests, and complete or reject the input according to a defined policy.

This article focuses on techniques in **Java Core I/O and NIO**, using Java 17+ without depending on web frameworks. This is foundational knowledge for implementing upload policies in Spring, servlets, or other streaming systems.

## 2. Distinguishing Different Types of Limits

A safe system usually needs multiple types of limits, because **a single number like “maximum 10 MB” cannot protect every resource**.

| Limit Type | Controlled Resource | Example |
| --- | --- | --- |
| Raw input size | Number of bytes received from source before decoding/decompression | Maximum upload bytes |
| Decompressed size | Number of actual data bytes after GZIP/ZIP | Prevent compressed files from expanding excessively |
| Memory per request | Arrays, buffers, parser objects, and state | Working memory quota/request |
| Item count | Number of ZIP entries, JSON nodes, records, headers | Avoid millions of small objects |
| Structural depth | Nested JSON/XML/archive/object graph | Avoid deep recursion and stack/resource exhaustion |
| Processing time | Timeout for reading, parsing, and the entire request | Prevent slow/non-terminating input |
| Concurrency | Number of tasks holding resources | Avoid multiplying many small limits into a large total |
| Temporary disk space | Spool files and content awaiting processing | Prevent filling the filesystem |
| Output size | Bytes returned and temporary data generated | Avoid unbounded output |

For example: limiting each request to 8 MiB **does not mean** 100 concurrent requests only use 8 MiB. If each request holds an 8 MiB `byte[]`, those arrays alone can occupy around 800 MiB, not counting auxiliary buffers, metadata, strings, parsers, other heap objects, and runtime overhead. If decoded into `String`, parsed as JSON, and kept as copies in a cache, peak memory can be much larger.

Quotas must be tied to **how data is actually read, processed, decompressed, allocated, and parallelized**. A size limit is only valuable when checked **before or while the corresponding resource is being consumed**.

## 3. APIs That Easily Read All Data into RAM

The following APIs are useful but must be used in the right scenarios:

| API | Behavior to Watch Out For |
| --- | --- |
| `InputStream.readAllBytes()` | Reads all remaining bytes until EOF and returns a `byte[]` |
| `Files.readAllBytes(path)` | Reads the entire file content into a `byte[]` |
| `Files.readString(path)` | Reads the entire file into a `String` |
| `InputStream.transferTo(output)` | Transfers until EOF; can write unbounded output without a controlling wrapper |
| `ByteArrayOutputStream` | Accumulates bytes on the heap; capacity grows with the number of bytes written |
| `StringBuilder` | Holds the entire string being built, which can grow with the input |
| `BufferedReader.lines().toList()` | Can keep all lines in memory |
| `ZipInputStream.readAllBytes()` on an entry | Can decompress and hold the entire entry without limits |
| `GZIPInputStream.readAllBytes()` | Can decompress into far more bytes than the source file |

Java 17 Javadoc explicitly states that `InputStream.readAllBytes()` is intended for simple cases where it is convenient to read all bytes into a byte array; **it is not the default choice for large inputs**. It can throw `OutOfMemoryError` if the required array cannot be allocated. `InputStream.transferTo()` does not return a large `byte[]`, but it still **reads and writes until EOF**; if the destination is a `ByteArrayOutputStream` or an uncontrolled disk, resources can still grow without bound.

**Do not confuse a “streaming API” with an “enforced limit policy”.** A pipeline that merely has a streaming loop without limiting total bytes, record count, or time can still consume unbounded resources at another layer.

### Is `readNBytes(int)` Automatically Safe?

`input.readNBytes(n)` (Java 11+) reads at most `n` bytes and returns an array containing the actual number of bytes read. This can be an appropriate tool **if `n` has been validated and bounded by policy**. However:

- If a huge client-supplied value of `n` is passed, it can still cause memory pressure.
- If you need to reject input **longer than `n`**, merely reading `n` bytes **is not enough** to conclude the input has ended; you need to read one more byte to detect any remainder, or use a protocol that specifies the exact length.
- If you do not need to keep the entire content in RAM, the resulting array is still unnecessary memory overhead; using a fixed buffer is better.

## 4. Do Not Treat `InputStream.available()` as File Size

`available()` returns an **estimate of the number of bytes that can be read without blocking**, not the total input size and not a guarantee of the remaining bytes until EOF.

Incorrect approach:

```java
byte[] data = new byte[input.available()];
input.read(data); // May read fewer bytes; array size may be wrong.
```

This illustrative snippet can produce incomplete results and ignores the actual number of bytes returned. With a network stream, `available()` may be 0 even though the peer will send data later. With `ByteArrayInputStream`, it may appear to work because the implementation knows the remaining byte count, but **you must not generalize that contract to every InputStream**.

To read until EOF, you need a loop based on the **actual return value** of `read`. To enforce a maximum limit, you need to **count each byte read and reject when the total exceeds the budget**.

## 5. Checking Declared Size: Necessary but Not Sufficient

Some sources know or announce the size upfront:

- `Files.size(path)` returns the file size at the time of inspection.
- HTTP `Content-Length` is the declared number of bytes in the request header, if present.
- Binary frames have a 32-bit/64-bit length field.
- `ZipEntry.getSize()` returns the uncompressed data size according to metadata if known; it may return `-1` when unknown.

These values are signals for **early rejection** or choosing a processing strategy, but they do not replace limiting during reading:

1. **Metadata may be absent or untrusted**; a client can send data of a different length than declared.
2. **A file may change** between checking `Files.size` and reading (*TOCTOU*).
3. **Negative, excessively large, or overflowing values** during addition/multiplication can cause incorrect allocations.
4. **Compressed size does not indicate decompressed size**; you must count bytes after decompression.
5. **Multiple components** may reside under a single container: you must limit **both each individual part and the whole**.

Validation pattern before allocation:

```java
int length = input.readInt(); // Example of a 4-byte length-prefixed frame.
if (length < 0 || length > MAX_FRAME_BYTES) {
    throw new IOException("Invalid frame length");
}
byte[] payload = input.readNBytes(length);
if (payload.length != length) {
    throw new EOFException("Truncated frame");
}
```

This is an illustrative snippet, assuming `input` is a `DataInputStream` and `MAX_FRAME_BYTES` is a **reliably bounded** configuration value. The `length` value must be checked **before** creating the array. Do not do `new byte[length]` and check afterward. If the payload is large yet still within policy, consider streaming it rather than holding the entire block in RAM.

## 6. Limiting Input by Bytes Actually Read

A foundational solution is **bounded streaming copy**: read using a fixed buffer, accumulate the bytes actually read, and do not allow exceeding the quota.

Suppose the policy allows **at most 10 bytes**. There are three scenarios:

| Input | Conclusion |
| --- | --- |
| Exactly 10 bytes followed by EOF | Accept |
| 9 bytes followed by EOF | Accept if the protocol allows less than the limit |
| 11 bytes | Reject because the limit is exceeded |

A correct implementation must avoid **off-by-one** errors: if it reads exactly 10 bytes without checking for EOF, it cannot yet know whether an 11th byte exists. At the same time, to detect limit exceedance without holding much data, it can **probe by reading exactly one more byte** after consuming 10 bytes.

Define the contract clearly:

- `maxBytes` is an **inclusive** limit: 10 bytes are still accepted.
- `copied` is the total number of bytes successfully transferred to the output.
- Read at most the number of bytes remaining in the budget.
- When the budget is reached, read **one additional byte** to detect longer input; do not write the probe byte to the output.
- If the budget is exceeded, throw an exception and **treat the previously written output as incomplete**, which must be rolled back/deleted or not published.
- Do not cast `(int) maxBytes` when the value may exceed `Integer.MAX_VALUE`; count the total using `long` and bound each read chunk size by an `int` buffer.

## 7. Runnable Java 17 Example: `boundedCopy` Without Holding the Entire Input in RAM

The program below uses an 8 KiB array and does not allocate memory proportional to the total input size. It runs on `ByteArrayInputStream` so the result can be verified precisely, but the algorithm can also be used with network/file stream inputs. When input exceeds the quota, the output may have already received a **valid prefix**: the example demonstrates this so learners do not mistake an exception for automatic rollback.

**File `BoundedCopyDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class BoundedCopyDemo {
    static long copyBounded(InputStream input, OutputStream output,
                            long maxBytes) throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException("maxBytes < 0");
        }

        byte[] buffer = new byte[8192];
        long copied = 0;

        while (copied < maxBytes) {
            int wanted = (int) Math.min(
                    (long) buffer.length, maxBytes - copied);
            int n = input.read(buffer, 0, wanted);

            if (n == -1) {
                return copied;
            }
            if (n == 0) {
                throw new IOException("Input made no progress");
            }

            output.write(buffer, 0, n);
            copied += n;
        }

        // Budget reached: probe exactly one next byte.
        if (input.read() != -1) {
            throw new IOException(
                    "Input exceeds " + maxBytes + " bytes");
        }
        return copied;
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream accepted = new ByteArrayOutputStream();
        byte[] exactlyTen =
                "ABCDEFGHIJ".getBytes(StandardCharsets.US_ASCII);

        long size = copyBounded(
                new ByteArrayInputStream(exactlyTen),
                accepted, 10);

        System.out.println("Accepted bytes: " + size);
        System.out.println("Accepted data: "
                + accepted.toString(StandardCharsets.US_ASCII));

        ByteArrayOutputStream partial = new ByteArrayOutputStream();
        byte[] eleven =
                "ABCDEFGHIJK".getBytes(StandardCharsets.US_ASCII);

        try {
            copyBounded(new ByteArrayInputStream(eleven),
                    partial, 10);
            System.out.println("Unexpected acceptance");
        } catch (IOException ex) {
            System.out.println("Rejected: " + ex.getMessage());
            System.out.println(
                    "Partial output bytes: " + partial.size());
        }

        long empty = copyBounded(
                new ByteArrayInputStream(new byte[0]),
                new ByteArrayOutputStream(), 0);
        System.out.println("Zero limit, empty input: " + empty);
    }
}
```

Compile/run commands:

```bash
javac BoundedCopyDemo.java
java BoundedCopyDemo
```

**Exact stdout when the program succeeds:**

```text
Accepted bytes: 10
Accepted data: ABCDEFGHIJ
Rejected: Input exceeds 10 bytes
Partial output bytes: 10
Zero limit, empty input: 0
```

Analysis:

1. Input of exactly 10 bytes: the loop reads 10 bytes; the subsequent probe `input.read()` returns `-1`, so it is accepted.
2. Input of 11 bytes: the loop writes only 10 bytes; the probe returns the 11th byte, so `IOException` is thrown. The output already holds the **first 10 bytes** — rollback must be managed.
3. When `maxBytes=0` and the input is empty, the loop does not execute, the probe returns EOF, so it returns `0`.
4. No matter how large the input is, **the working array remains only 8 KiB**; the counter uses `long`.
5. Checking `n==0` avoids a no-progress loop caused by a non-compliant/unexpected implementation; per the standard `InputStream.read(byte[], off, len)` contract with `len>0`, a normal result is a positive byte count or `-1`, not 0.

**Limitation of the example:** a fixed read buffer does not mean the entire application uses only 8 KiB: the output here is `ByteArrayOutputStream`, so it still holds accepted data up to 10 bytes. When input comes from the network and output is a temporary file, the memory increase can be much smaller; to truly bound RAM, you must control **the source, intermediate buffers, and destination**.

## 8. Partial Output: A Commit/Rollback Step Is Required

If the copy method writes directly to the final filename, when input exceeds the budget it may leave behind a file containing the beginning of the data. Users or other processes might assume that file is complete.

A safer strategy:

```text
Untrusted source
       |
       v
bounded copy (check actual byte count)
       |
       v
temporary file owned by the application
       |
       +-- Failure/limit exceeded --> close + delete temporary file
       |
       +-- Success -----------------> validate format/checksum
                                         |
                                         v
                                    publish/rename
```

Recommended workflow:

1. Create a temporary file in a location with an appropriate quota and access permissions.
2. Write to the temporary file while performing bounded reads.
3. Only publish the file to consumers if the limit, content, and structural checks succeed.
4. If an `IOException`, timeout, validation error, or request cancellation occurs, close the streams and delete the temporary file in `finally`.
5. If writers can contend, use an appropriate naming, overwrite, and synchronization policy.
6. `Files.move(..., ATOMIC_MOVE)` may be supported depending on the filesystem/provider; do not assume atomic move is always available.

**Rule:** “read no more than X bytes” does not mean “processed successfully”. The data may be missing formatting, failing checksums, failing decompression, or cut off midway. Only record **COMPLETED** status after the corresponding conditions have truly succeeded.

## 9. Java 17 Example: Length-Prefixed Frame, Validating Before Allocation

Many binary protocols use the structure:

```text
[ length: 4-byte signed int ][ payload: length bytes ]
```

If you read the client-sent length and immediately create `new byte[length]`, a client can cause the server to request a huge array or use a negative number. You must validate **before allocating**. The `readNBytes(length)` method is suitable when `length` has already been capped by a relatively small quota, and you must check whether enough bytes were actually read.

**File `FrameLimitDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public class FrameLimitDemo {
    private static final int MAX_FRAME_BYTES = 8;

    static byte[] readFrame(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 0 || length > MAX_FRAME_BYTES) {
            throw new IOException("Rejected length: " + length);
        }

        byte[] payload = input.readNBytes(length);
        if (payload.length != length) {
            throw new EOFException("Truncated frame");
        }
        return payload;
    }

    static byte[] frame(int declaredLength, byte[] payload)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(bytes)) {
            output.writeInt(declaredLength);
            output.write(payload);
        }
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] cat = "CAT".getBytes(StandardCharsets.US_ASCII);

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(frame(cat.length, cat)))) {
            System.out.println("Accepted: " + new String(
                    readFrame(input), StandardCharsets.US_ASCII));
        }

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(frame(1_000_000, new byte[0])))) {
            readFrame(input);
        } catch (IOException ex) {
            System.out.println(ex.getMessage());
        }

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(frame(5, cat)))) {
            readFrame(input);
        } catch (EOFException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Run commands:

```bash
javac FrameLimitDemo.java
java FrameLimitDemo
```

**Exact stdout:**

```text
Accepted: CAT
Rejected length: 1000000
Rejected: Truncated frame
```

Scenarios:

- Payload `CAT` of 3 bytes, declared 3: accepted.
- Declared 1,000,000 bytes while policy only allows 8: rejected **before allocating the payload array**.
- Declared 5 bytes while actually only 3 exist: `readNBytes(5)` returns a 3-byte array; the application throws `EOFException` because the frame is truncated.

**Do not call `read(byte[])` once and assume the frame is complete.** `InputStream.read` can return fewer bytes than requested. `readNBytes(len)` or a loop reading the exact amount helps handle short reads according to contract.

If the protocol uses an **unsigned 32-bit length**, convert to `long` and check the valid range **without overflowing `int`** before allocating. The configured quota must be a trusted server-side value, not chosen by the client.

## 10. Numeric Types and Preventing Overflow When Computing Sizes

A proper limit can still be bypassed by incorrect arithmetic.

### 10.1. Do Not Add Two Large `int` Values Before Comparing

Avoid:

```java
int total = currentBytes + nextBytes;
if (total > maxBytes) {
    throw new IOException("Too large");
}
```

Because adding two `int` values can **overflow** before the comparison, `total` may become negative or smaller than expected. The snippet is illustrative using existing variables.

If handling only non-negative values and `currentBytes <= maxBytes`, you can use subtraction:

```java
if (nextBytes < 0 || nextBytes > maxBytes - currentBytes) {
    throw new IOException("Limit exceeded");
}
currentBytes += nextBytes;
```

Or use `Math.addExact(...)` and catch `ArithmeticException` when exact addition is needed. Use `long` for total bytes, record counts, and large offsets, while still preventing `long` overflow when input/metadata is untrusted.

### 10.2. Do Not Cast Down to `int` Without Checking

```java
long declaredLength = input.readLong();
byte[] buffer = new byte[(int) declaredLength]; // Wrong if long is too large.
```

A large `long` cast to `int` can have its bits truncated or become negative. Only cast after validating `0 <= length <= configuredMaximum` and `length <= Integer.MAX_VALUE`. For large files, read in chunks or write to disk instead of allocating an array holding everything.

### 10.3. Both Item Count and Total Bytes Must Be Checked Together

For example, 10,000 items of 10 KiB each can occupy nearly 100 MiB before overhead even though a single item is small. If a format contains multiple headers/records, you must limit **both the count and the size of each item**.

## 11. File Size and the Possibility of Modification During Reading

For a file source:

```java
long announcedSize = Files.size(path);
if (announcedSize > MAX_BYTES) {
    throw new IOException("File too large");
}
```

This is a good *early rejection* step when metadata is available. However, between checking and calling `Files.newInputStream(path)` or `Files.readAllBytes(path)`, the file can be modified by another process. There are also special files or filesystems whose size behavior does not correspond to a stable data stream.

**A more reliable approach:** check the size for early rejection, and **still** enforce a bounding counter in the read loop on the actual bytes received. If high consistency is required, coordinate locking/snapshots/versioning, or read from a handle with suitable semantics; do not treat `Files.size` as a transaction blocking other writers.

A file that slightly exceeds the quota might only be detected on the final read; therefore, temporary file, cleanup, and rollback policies remain necessary even after a precheck.

## 12. GZIP/ZIP: Check **Data After Decompression**

For compressed data, the compressed size **is not** the RAM or output budget after decompression.

For example, a stream containing many repeated bytes can compress into a very small file yet decompress into a huge number of bytes. If a server only checks the total HTTP body bytes before wrapping with `GZIPInputStream` or `ZipInputStream`, it is still vulnerable to a **decompression bomb/zip bomb**.

Limits must be enforced **downstream of decompression**:

```text
Compressed input
    |
    | limit compressed bytes / time / source
    v
GZIPInputStream or ZipInputStream
    |
    | limit actual decompressed bytes read
    v
bounded parser / temp file / output
    |
    v
validate then publish
```

In addition to decompressed size, you should limit the number of ZIP entries, size per entry, total size across entries, nested archive depth, number of extracted files, and disk space. The compression/decompression ratio can serve as an **additional signal**, not a replacement for actual total bytes.

`ZipEntry.getSize()` may be `-1` or untrusted at read time, so only use it for early rejection when appropriate; **counting actual `ZipInputStream.read(...)` bytes** is the primary control layer.

## 13. Java 17 Example: Limiting GZIP by Decompressed Bytes

The following program creates a small GZIP in memory, then decompresses it using `GZIPInputStream`. Every byte coming out of the decoder is counted against the limit in the read loop. The example uses a 10-byte limit: the text `Java` is valid, while a 12-character string of `X` exceeds the quota and is rejected.

**File `GzipLimitDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;

public class GzipLimitDemo {
    static byte[] gzip(byte[] data) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (GZIPOutputStream output = new GZIPOutputStream(sink)) {
            output.write(data);
        }
        return sink.toByteArray();
    }

    static String decodeBounded(byte[] compressed, int maxBytes)
            throws IOException {
        ByteArrayOutputStream result = new ByteArrayOutputStream();

        try (GZIPInputStream input = new GZIPInputStream(
                new ByteArrayInputStream(compressed))) {

            byte[] buffer = new byte[4];
            int total = 0;
            int n;

            while ((n = input.read(buffer)) != -1) {
                if (n == 0) {
                    throw new IOException("No read progress");
                }
                if (n > maxBytes - total) {
                    throw new IOException("Decompressed limit exceeded");
                }
                total += n;
                result.write(buffer, 0, n);
            }
        }
        return result.toString(StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws IOException {
        byte[] small = gzip(
                "Java".getBytes(StandardCharsets.UTF_8));
        System.out.println("Accepted: "
                + decodeBounded(small, 10));

        byte[] large = gzip(
                "XXXXXXXXXXXX".getBytes(StandardCharsets.US_ASCII));

        try {
            System.out.println(decodeBounded(large, 10));
        } catch (IOException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Run:

```bash
javac GzipLimitDemo.java
java GzipLimitDemo
```

**Stdout on success:**

```text
Accepted: Java
Rejected: Decompressed limit exceeded
```

**Notes:**

- The program counts **decompressed bytes**, not `compressed.length`.
- In `decodeBounded`, the working array is only 4 bytes to illustrate multi-chunk reads.
- `ByteArrayOutputStream` accumulates output but is indirectly bounded by the 10-byte policy; with larger quotas, stream directly to a parser or temporary file.
- In production, `maxBytes` must be verified to be non-negative and within the allowed configuration range before calling; here it is a trusted constant 10.
- Having only a decompressed byte limit is **not enough** if the compressed stream never terminates or the decoder consumes excessive CPU; you must add timeouts and a total compressed input size limit.

Do not call `GZIPInputStream.readAllBytes()` on compressed content from an untrusted source and **only then** check the output array size. By the time the check is reached, resources may already have been excessively consumed.

## 14. Controlling ZIP by Entry Count and Total Decompressed Bytes

A ZIP has **multiple entries**. If you only limit each entry to 1 MiB but the archive contains tens of thousands of entries, total data is still huge. Therefore use these counters:

- `maxEntries`: maximum number of entries.
- `maxBytesPerEntry`: maximum decompressed bytes per entry.
- `maxTotalExpandedBytes`: maximum total decompressed bytes across the entire archive.
- `maxDepth`: if ZIP-inside-ZIP or other nested containers are allowed.
- `maxOutputFiles` and total disk space when extracting to files.

Each time a chunk of length `n` is read:

```java
if (n > maxEntryBytes - entryBytes
        || n > maxTotalBytes - totalBytes) {
    throw new IOException("Expanded ZIP limit exceeded");
}

entryBytes += n;
totalBytes += n;
```

This is an illustrative snippet, assuming counters/budgets have been verified non-negative and counters have not exceeded budgets. Use **subtraction-based** comparisons to prevent overflow. You do not need to keep the entire entry in RAM just to know whether it exceeds the limit.

### Java 17 Example: Rejecting a ZIP When Total Bytes Exceed the Limit

**File `ZipExpansionLimitDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class ZipExpansionLimitDemo {
    static byte[] createZip(String body) throws IOException {
        ByteArrayOutputStream sink = new ByteArrayOutputStream();
        try (ZipOutputStream output = new ZipOutputStream(sink)) {
            output.putNextEntry(new ZipEntry("item.txt"));
            output.write(body.getBytes(StandardCharsets.US_ASCII));
            output.closeEntry();
        }
        return sink.toByteArray();
    }

    static int inspect(byte[] bytes, int maxEntries,
                       int maxPerEntry, int maxTotal)
            throws IOException {
        if (maxEntries < 0 || maxPerEntry < 0 || maxTotal < 0) {
            throw new IllegalArgumentException("Negative budget");
        }

        int entries = 0;
        int total = 0;

        try (ZipInputStream input = new ZipInputStream(
                new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            byte[] buffer = new byte[4];

            while ((entry = input.getNextEntry()) != null) {
                entries++;
                if (entries > maxEntries) {
                    throw new IOException("Entry count exceeded");
                }

                int entryBytes = 0;
                int n;
                while ((n = input.read(buffer)) != -1) {
                    if (n == 0) {
                        throw new IOException("No read progress");
                    }
                    if (n > maxPerEntry - entryBytes
                            || n > maxTotal - total) {
                        throw new IOException(
                                "Expanded ZIP limit exceeded");
                    }

                    entryBytes += n;
                    total += n;
                }
                input.closeEntry();
            }
        }

        return total;
    }

    public static void main(String[] args) throws IOException {
        byte[] small = createZip("CAT");
        System.out.println("Accepted bytes: "
                + inspect(small, 2, 10, 10));

        byte[] large = createZip("ABCDEFGHIJKL");
        try {
            inspect(large, 2, 10, 10);
        } catch (IOException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Commands:

```bash
javac ZipExpansionLimitDemo.java
java ZipExpansionLimitDemo
```

**Exact stdout when the program succeeds:**

```text
Accepted bytes: 3
Rejected: Expanded ZIP limit exceeded
```

Key point: the program counts **decompressed** bytes and does not rely on `ZipEntry.getSize()`. It also bounds the entry count and each entry individually. The example creates the ZIP in RAM for easy reproducibility; in real applications you can read from `Files.newInputStream` or a bounded network source, and avoid extracting all entries into a `ByteArrayOutputStream`.

**Not yet a production extractor**: the program above only *inspects and counts*; it does not write files. If extended into an extractor, it must prevent **Zip Slip**, control symlinks, path traversal, file permissions, file count, disk space, timeouts, nested archives, and cleanup on failure.

## 15. Byte Limit, Character Limit, and Unicode Are Not the Same

A text with few characters does not necessarily have few bytes. For example, UTF-8 encodes ASCII using 1 byte, but many accented characters use more than 1 byte; emoji can use 4 bytes. Java's `String.length()` returns the number of **UTF-16 code units**, not the number of UTF-8 bytes and not necessarily the number of user-perceived characters (*grapheme clusters*).

Illustrative example:

```java
String text = "A😀B";

System.out.println(text.length()); // 4 UTF-16 code units
System.out.println(text.codePointCount(0, text.length())); // 3
System.out.println(text.getBytes(StandardCharsets.UTF_8).length); // 6
```

With UTF-8 encoded Java source, `A` and `B` are two ASCII bytes, and the emoji uses four UTF-8 bytes. The total is **6 bytes**, **3 Unicode code points**, yet `String.length()==4`.

**Place limits at the right layer:**

1. **Raw input byte limit**: before decoding, protecting network/file/memory.
2. **Decoded text length limit**: after decoding, protecting parsers and text logic.
3. **Line count, token count, nesting depth**: protecting data structures.
4. **Output byte limit**: if serializing/encoding the response can expand further.

Do not treat `String.length()` as the byte limit of an HTTP request. Do not automatically truncate `byte[]` at the limit if it could split a UTF-8 sequence or binary data requiring integrity. When the limit is exceeded, **reject the entire payload** or use a streaming protocol that supports explicit framing.

### Strict Charset Decoder

If data must be valid UTF-8, use a decoder with `CodingErrorAction.REPORT` when invalid byte sequences must be rejected rather than silently replaced with another character. You can use `CharsetDecoder` or an equivalent parser API, and control the byte budget before decoding. For text streaming, retain trailing incomplete character bytes across chunks — do not decode each chunk independently with `new String(buffer, 0, n, UTF_8)` and concatenate them if a chunk can end in the middle of a UTF-8 sequence.

## 16. Peak Memory Can Exceed Input Size

Reading a 5 MiB input into `byte[]`, decoding to a `String`, parsing into an object tree, and keeping a copy in a cache can hold **multiple representations simultaneously**. Furthermore:

- `byte[]` has an object header and alignment.
- `ByteArrayOutputStream` may retain an internal array and `toByteArray()` creates a copy.
- `String` and decoders use their own representations/arrays.
- JSON/XML parsers can create many small objects, maps, lists, strings, and node metadata.
- Compression/decompression has native or internal buffers.
- Libraries may cache or retain references causing objects to outlive the request.
- Direct `ByteBuffer` and memory mapping use off-heap resources, which do not appear solely in heap metrics.

Therefore, **the input byte limit is not a 1:1 heap consumption limit**. You must measure **peak retained + temporary allocations** under realistic workloads, factoring in headroom for GC/runtime and concurrent requests.

### Design-Level Budget Example

Suppose each task holds:
- at most 4 MiB of accepted input in one array;
- at most 4 MiB of intermediate output;
- plus parser and runtime overhead.

If 50 such tasks exist concurrently, just the two 4 MiB arrays per task can occupy around **400 MiB**, not counting overhead. Instead of allowing up to 50 requests to parse on the heap simultaneously, the system can use a semaphore to limit heavy tasks or stream data to temporary files.

These numbers illustrate the budgeting technique, **not a universal recommended configuration**. Choose quotas based on heap, container memory, actual workload, and SLOs.

## 17. Concurrency Limits and Backpressure

A 1 MiB request may be small, but if 50,000 requests are allowed to each hold a 1 MiB copy in RAM, total memory will far exceed the limit of most application processes.

**Two layers of admission control** are needed:

- **Per-request limit:** bytes/records/depth/time of a single request.
- **Global limit:** total active requests, in-flight bytes, worker tasks, pending connections, or queue capacity.

Common techniques:

1. Use a `Semaphore` to limit the number of requests concurrently holding large memory or decompressing.
2. Use a bounded queue and reject early when full.
3. Pause reading from upstream when downstream cannot keep up (*backpressure*).
4. Separate small working memory from spool files with disk quotas and TTL cleanup.
5. Release resources via `try-with-resources`, cancel tasks on timeout/cancellation, and update metrics.
6. Use instrumentation and alerts when approaching limits; **do not wait for `OutOfMemoryError` to react**.

With non-blocking Java NIO, `SocketChannel.read(ByteBuffer)` can return 0 when no data is available yet; enforcing the byte cap still belongs in **per-connection state**, not just in the buffer size. `ByteBuffer.clear()` reuses the buffer but **does not reset the total bytes received**; the application must maintain a separate counter across multiple reads.

## 18. Timeouts and Inputs That Never Terminate

A byte limit **cannot stop a client that sends very slowly** (e.g., only a few bytes per minute) or a source that hangs before EOF. Therefore, time policies are required:

- **Connect timeout**: maximum wait to establish a connection.
- **Read idle timeout**: maximum time without receiving progress.
- **Overall deadline**: total time for the entire request, even if slow yet still making progress.
- **Parsing/decompression budget**: CPU/time limit after receiving data.
- **Cancellation**: when the user cancels or the deadline expires, stop the processing flow and clean up.

Do not use an unconditional `while (read(...) == 0)` loop with a non-blocking channel; that is a **busy spin**. Use readiness/`Selector`, appropriate backoff, or event-driven scheduling. With blocking `InputStream`, enforcing a deadline may require socket/transport timeouts or closing/cancelling from another thread per the specific API; `Thread.interrupt()` does not have the same effect on every I/O source.

**Total byte limits and timeouts are two distinct axes** that must work together.

## 19. EOF, Partial Reads, and Parser Responsibilities

`InputStream.read(byte[])` returns the **actual number of bytes received**, which may be smaller than the buffer size; `-1` indicates EOF. Never assume a single read has retrieved all required data.

For fixed-size message frames, EOF before enough bytes arrive is **truncated input**. For uploads without a known size, EOF can be the terminating boundary, but the application must still verify total bytes <= limit and validate the format.

`DataInputStream.readFully(byte[])` can be useful if you have allocated an array of a **pre-validated** size; on premature EOF, it throws `EOFException`. However, it **does not automatically bound input** if you allocate the array using an untrusted length.

A good parser must clearly define:
- How many bytes constitute “enough read”?
- If insufficient, what is the rejection action?
- If excess bytes exist, is it a protocol error or the start of the next frame?
- If the data is valid in size but fails checksum/schema, how should it be handled?
- If data arrives in multiple chunks, what state is retained and when is it cleaned up?

For multi-frame streaming, **do not read a probe byte and lose it** if that byte belongs to the next frame. The single-byte probe technique in `BoundedCopyDemo` is suitable for **a single input expected to end at EOF**. For multi-frame protocols, rely on declared boundaries and preserve reader state for the next frame.

## 20. Limit the Entire Pipeline, Not Just One Component

A real processing flow may pass through:

```text
HTTP body / socket
      |
      v
transport request limit
      |
      v
decompression / decoding
      |
      v
expanded-byte and character limit
      |
      v
parser depth / item count limit
      |
      v
business validation
      |
      v
temporary file / output quota
      |
      v
commit / publish
```

For example, an HTTP body limited to 10 MiB that allows a ZIP payload inside it:

- 10 MiB only controls the **compressed input**.
- A 10 MiB ZIP can contain a **huge number of entries** or decompress into gigabytes.
- The parser after decompression can build an object tree many times larger than the raw bytes.
- Multiple concurrent requests can compound the cost.

One failing control layer should not cause all downstream layers to completely trust the data. **Defense in depth** means enforcing limits with independent counters at the exact data transformation points.

## 21. Common Design Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using `readAllBytes()` on unbounded input | Can consume huge heap / OOME | Bounded stream and byte limit |
| Using `InputStream.available()` as total size | Wrong assumptions, short reads | Count bytes returned from `read` |
| Blindly trusting `Content-Length` | Client may misreport/omit it | Precheck early and enforce during read |
| `new byte[untrustedLength]` before validating | Huge/negative/overflowing allocation | Validate length first |
| Using `readNBytes(max)` and assuming input does not exceed max | Trailing bytes may still remain | Probe EOF or use frame protocol |
| Using `transferTo(ByteArrayOutputStream)` without limits | Holds all data on heap | Bounded copy or bounded sink |
| Checking the limit after accumulating all bytes | Resources already excessively consumed | Check on every chunk |
| Using `int` for large byte totals and adding directly | Overflow bypasses the limit | Use `long` and subtraction-based checks |
| Limiting only compressed ZIP/GZIP file size | Can decompress into many GBs | Limit bytes after decompression |
| Limiting only per-entry ZIP size | Many entries accumulate too much | Limit total bytes and entry count |
| Limiting only raw bytes | Parser can build a huge object graph | Add item/depth/char limits |
| Small per-request max but unbounded concurrency | Total heap still grows uncontrollably | Admission control/semaphore/queue |
| Exceeding limit yet keeping partial output file | May publish corrupted data | Temp file + commit/rollback |
| Having only a byte cap without a deadline | Slow client ties up resources indefinitely | Idle timeout and overall deadline |
| Splitting UTF-8 on byte boundaries and decoding chunks separately | Corrupted characters / replacement chars | Stateful decoder and validation |
| Thinking `ByteBuffer.clear()` resets the byte budget | Limit can be bypassed across multiple reads | Separate counter per request/connection |
| Catching `OutOfMemoryError` and continuing normally | Process may be in a degraded state | Enforce limits upfront, monitor resources |
| Not closing streams on error | Leaked file descriptors/temp files | `try-with-resources` and cleanup in `finally` |

## 22. Self-Check Exercises

**Question 1.** An API accepts at most 1024 bytes. `input.readNBytes(1024)` returns an array of exactly 1024 bytes. Can you conclude the input size is valid?

**Answer:** Not yet. The input might still have a 1025th byte. For a payload that must end at EOF, read one probe byte and reject if present. For a multi-frame protocol, do not arbitrarily consume a byte of the next frame; use proper framing.

**Question 2.** A ZIP file is 1 MiB and contains 100 entries, each decompressing to 2 MiB. Is checking only that the ZIP file <= 5 MiB safe?

**Answer:** No. Total decompressed data can be around 200 MiB. You must limit **compressed size, per-entry size, total decompressed bytes, entry count, and processing resources**.

**Question 3.** There are 100 concurrent requests, each holding a 4 MiB input array and a 4 MiB output array. How much do those two arrays alone occupy?

**Answer:** Around **800 MiB**, not counting overhead and intermediate representations. A per-request cap does not replace a concurrency limit.

**Question 4.** Why does `available()==0` not mean EOF?

**Answer:** `available` only estimates non-blocking readable bytes; a socket that has not received data yet may return 0 while still receiving more bytes later. EOF must be determined from `read` return values and the protocol.

**Question 5.** If a streaming pipeline uses an 8 KiB buffer and writes to a temporary file without a quota, is the pipeline completely safe from resource exhaustion?

**Answer:** Not yet. Working heap may be small, but the temporary file can grow without bound, time/CPU may be unbounded, and multiple requests can fill the disk. You need byte limits, disk quotas, timeouts, concurrency caps, and cleanup.

**Question 6.** Why check `n > max - current` instead of just `current + n > max`?

**Answer:** Subtraction-based checks prevent overflow in addition, provided `current` and `max` have been validated and `current<=max`.

**Question 7.** A Java string has `text.length()==4` while its UTF-8 representation has 6 bytes. Is this a contradiction?

**Answer:** No. `String.length()` counts UTF-16 code units; UTF-8 is a byte representation. Byte caps must be measured at the byte layer, and character caps must be measured at the text layer according to the desired convention.

## 23. Practical Implementation Checklist

Before receiving input:

1. Define the unit of each limit: **raw bytes**, **decompressed bytes**, **characters**, **record count**, **time**, **memory**, **disk**.
2. Set trusted server-side values; do not allow clients to relax limits.
3. Set concurrency limits for tasks requiring large memory allocations.
4. Identify which sources have trusted metadata and how to perform early rejection.

While reading/decoding:

1. Read in **fixed-size chunks**, without holding the entire input if unnecessary.
2. Accumulate **actual bytes received**, enforcing the limit before writing/accepting more.
3. Validate declared length before `new byte[n]` or `readNBytes(n)`.
4. Additionally limit **decompressed** data and entry/record/depth counts.
5. Handle partial reads, premature EOF, idle timeouts, and overall deadlines.
6. Track request-level state across all reads; do not reset it just because a buffer is reused.

On completion or failure:

1. Verify the data is complete and valid according to schema/protocol.
2. Publish the artifact only after all checks succeed.
3. Close streams/channels, delete temporary files, and release semaphores/quotas.
4. Record metrics: bytes accepted/rejected, peak memory, temp disk, timeouts, overflows, concurrent requests.
5. Test boundaries: **0**, **limit−1**, **limit**, **limit+1**, negative/huge metadata, truncated input, compressed bombs, high concurrency, and slow readers.

## 24. Summary

Limiting input size is a **resource contract**, not just checking a header field. In Java I/O:

- **Do not call `readAllBytes` indiscriminately on untrusted sources**. Prefer chunked reading and counting actual bytes.
- **Do not trust `available()` or metadata** to infer total data volume; they only play a supporting role.
- **Do not allocate before checking length**; handle overflow, negative lengths, and truncated data.
- **Enforce the exact byte budget**, including the exact limit and one byte over the limit.
- **Limit ZIP/GZIP after decompression**, along with entry counts and total archive bytes.
- **Budget concurrency and peak memory**, not just per-request limits.
- **Handle errors with a transactional workflow**: temporary output → validate → publish; on error → cleanup.
- **Add deadlines, disk quotas, and parser limits**, because each resource has a different exploitation path.

A safe design ensures that **policy-violating input is rejected before the corresponding resource grows uncontrollably**, and even when errors occur, the application still knows how to release the resources it used.

**Java SE 17 Documentation:**

- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html) — `read`, `readAllBytes`, `readNBytes`, `available`, `transferTo`.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html) — `size`, `newInputStream`, `readAllBytes`, `createTempFile`, `move`.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html) — `readInt` and `readFully`.
- [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html) and [ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html).
- [ByteArrayOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ByteArrayOutputStream.html), [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html), [CharsetDecoder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/CharsetDecoder.html).
