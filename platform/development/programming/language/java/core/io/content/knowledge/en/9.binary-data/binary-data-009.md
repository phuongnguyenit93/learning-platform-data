# Validating Length Before Allocating or Reading Binary Data in Java

## 1. Why Is Length Validation Mandatory?

When a Java program reads binary data from a file, socket, packet, or stream built from external input, it may encounter a **length field** (length prefix) indicating how many bytes to read. If the application immediately trusts that value and calls `new byte[length]` or `readNBytes(length)`, a wrong or intentionally huge value can cause excessive memory consumption, allocation failures, indefinite blocking, short reads, or resource exhaustion.

The central rule is:

> **Define trusted limits, validate counts before allocating and reading, and then verify the actual bytes received.** For sources with unknown length, use chunked reading with a cumulative quota.

This lesson covers **binary data** in Java Core I/O. The techniques apply to `InputStream`, `DataInputStream`, `ByteBuffer`, `FileChannel`, and structured formats; never confuse byte size with character count in text.

After this lesson, you will be able to:

- Distinguish **declared length** from **actual bytes received**, as well as the unit of the length field.
- Check for negative numbers, zero, out-of-bounds values, format version mismatches, and overflowing length calculations.
- Read a complete binary frame via `DataInputStream.readFully` with explicit allocation bounds.
- Handle early EOF, non-EOF-emitting sources, I/O errors, and trailing data.
- Bound data without a length prefix using a streaming loop with a small buffer.
- Recognize when `Files.size`, `available()`, `readAllBytes()`, and `readNBytes(int)` are inadequate as safeguards.
- Enforce limits on **wire bytes**, element counts, decompressed size, and memory budgets at the appropriate layers.

## 2. Model of a Length-Prefixed Binary Frame

A simple format may consist of:

```text
+----------------------+----------------------+
| 4-byte payloadLength | payloadLength bytes  |
+----------------------+----------------------+
         header                 payload
```

For instance, assume the first 4 bytes represent a **signed, big-endian** `int` per `DataInputStream.readInt()`. When the header is `00 00 00 03`, the application expects the next three payload bytes.

However, a header received from outside is **not a verified truth**. Possible scenarios include:

| Declared Header | Actual Payload Received | Meaning and Handling |
| --- | --- | --- |
| 3 bytes | 3 bytes | Valid in length if within threshold and content meets format |
| 0 bytes | 0 bytes | Valid if the protocol permits empty payloads |
| -1 byte | Any | Negative value is invalid for a byte length |
| 2,147,483,647 bytes | Few bytes | Do not allocate a huge array; reject if over budget |
| 100 bytes | 20 bytes then EOF | **Truncated frame**: data is missing, must report error |
| 3 bytes | 5 bytes remaining in stream | One frame consumes 3 bytes; extra 2 bytes may be the next frame or invalid data depending on protocol |
| 3 bytes | 3 bytes but wrong checksum | Having the right length does not prove valid or intact content |

**Separate three concerns**: (1) the header is within valid range, (2) the source actually delivers enough bytes, and (3) the data passes syntax/type/integrity checks. Passing just one check does not replace the other two.

### 2.1. Unit of Measurement: Bytes, Elements, or Characters?

Formats can use different kinds of "length":

- **Payload byte count**: the application can use this directly as the byte buffer size *after validation*.
- **Element count**: if each record takes `elementSize` bytes, total bytes equal `count × elementSize`; check for overflow before allocating.
- **Character count**: length in Unicode code points, UTF-16 `char`s, or UTF-8 bytes can differ; never assume 1 character = 1 byte.
- **Total frame length**: some protocols include the header, others count payload only. Misreading this contract shifts frame boundaries.
- **Uncompressed or compressed length**: the two values can differ vastly; a limit only on compressed input does not prevent decompressed data from exploding.

Before writing code, document the contract: how many bytes is the header, signed/unsigned, endianness, unit, whether header is included, whether 0 is valid, maximum allowed size, and reaction to missing/trailing data.

## 3. Validating Before `new byte[length]`

Dangerous code:

```java
// Illustrating UNSAFE code style:
// InputStream/dataInput and protocol are unchecked.
int length = dataInput.readInt();
byte[] payload = new byte[length];
dataInput.readFully(payload);
```

This is an **illustrative snippet**, not a standalone program; `dataInput` is assumed to be a valid `DataInputStream`. The bug lies in trusting `length` immediately:

- `length < 0` throws `NegativeArraySizeException` when creating the array.
- Huge values can trigger `OutOfMemoryError` or exhaust the heap before reading any payload.
- If reading from the network and the peer declares a huge length while sending only a few bytes, the program may hold huge memory while waiting.
- `readFully` throws when data is truncated, yet that check occurs **after** allocation; thus it cannot protect memory resources.

Safer pattern:

```java
int length = dataInput.readInt();

if (length < 0 || length > MAX_PAYLOAD_BYTES) {
    throw new IOException("Invalid payload length: " + length);
}
byte[] payload = new byte[length];
dataInput.readFully(payload);
```

This is also an **illustrative snippet**; `MAX_PAYLOAD_BYTES` must be a defined constant/policy, and `dataInput` a valid source. For empty data, whether to accept `length == 0` depends on the format.

**Core point:** The maximum limit must come from system requirements and resource budgets, not from "the maximum Java permits" or whatever number the sender claims.

### 3.1. Choosing an Allocation Budget

A per-frame limit needs to consider:

1. **Data type:** thumbnails, 1 KiB metadata, and hundred-MiB raw images have different needs.
2. **Concurrent requests:** 1,000 requests each allocating 8 MiB already means roughly 8,000 MiB of temporary payloads, excluding other objects/GC/buffers.
3. **Records per request:** a 1 MiB frame may be valid, yet 100,000 consecutive frames cannot all be buffered into RAM.
4. **Processed output size:** decompressed data, transcoded data, object graphs, or element lists can exceed input bytes.
5. **Latency and source speed:** a single request can pin memory for a long time over a slow network; timeouts and total duration quotas are needed.
6. **Outputs:** writing into a `ByteArrayOutputStream` or collecting payloads into a `List<byte[]>` grows memory with total data even if individual frames are small.

Enforce per-frame, per-request, and concurrency limits across **three distinct layers** when global protection is required. Java's `int`/array size cap is a technical limit, not a sensible operational budget.

## 4. Complete Java 17+ Example: Bounded Frame Reading and Detecting Early EOF

The program below uses `DataInputStream` to read a **4-byte big-endian length prefix**, then checks the `1,024-byte` cap **before** allocating the array. `readFully` ensures either the full payload is read or `EOFException` is thrown.

Save as **`SafeFrameDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.util.Arrays;

public class SafeFrameDemo {
    private static final int MAX_PAYLOAD_BYTES = 1024;

    static byte[] readFrame(InputStream source) throws IOException {
        // Caller owns source and closes it when finished.
        DataInputStream input = new DataInputStream(source);

        int declaredLength = input.readInt();
        if (declaredLength < 0
                || declaredLength > MAX_PAYLOAD_BYTES) {
            throw new IOException(
                    "Invalid frame length: " + declaredLength);
        }

        byte[] payload = new byte[declaredLength];
        input.readFully(payload);
        return payload;
    }

    static byte[] makeFrame(int announcedLength, byte[] actualPayload)
            throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(buffer)) {
            output.writeInt(announcedLength);
            output.write(actualPayload);
        }
        return buffer.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] valid = makeFrame(3, new byte[] {10, 20, 30});
        try (InputStream input = new ByteArrayInputStream(valid)) {
            System.out.println(
                    "Valid: " + Arrays.toString(readFrame(input)));
        }

        byte[] tooLarge = makeFrame(2048, new byte[0]);
        try (InputStream input = new ByteArrayInputStream(tooLarge)) {
            try {
                readFrame(input);
            } catch (IOException error) {
                System.out.println("Rejected: " + error.getMessage());
            }
        }

        byte[] truncated = makeFrame(3, new byte[] {10});
        try (InputStream input = new ByteArrayInputStream(truncated)) {
            try {
                readFrame(input);
            } catch (EOFException error) {
                System.out.println("Truncated: "
                        + error.getClass().getSimpleName());
            }
        }
    }
}
```

Compile and run with JDK 17+:

```bash
javac -encoding UTF-8 SafeFrameDemo.java
java SafeFrameDemo
```

**Exact stdout:**

```text
Valid: [10, 20, 30]
Rejected: Invalid frame length: 2048
Truncated: EOFException
```

**Explanation of each case:**

- **Valid:** header specifies 3 bytes; limit permits 3, a 3-byte array is created, `readFully` retrieves all three bytes and prints them in order.
- **Rejected:** header declares `2048 > 1024`. The program errors immediately upon reading the header, **never allocating a large payload array and never attempting to read the payload**.
- **Truncated:** valid header declares 3 bytes, yet source only has 1 byte. `readFully` throws `EOFException` instead of returning a "full-length" array padded with zeros.
- **Lifecycle:** the `ByteArrayInputStream` instances are closed in the caller's `try-with-resources`. `readFrame` wraps `DataInputStream` without closing `source` because the caller owns the `InputStream`; for streams shared across many frames, the wrapper can be created once and managed at the caller layer.

### 4.1. Scope Limitations of the Example

The program above validates **one frame** in a simple format. When handling multiple consecutive frames, it does not yet limit total frame count or total bytes on a connection. Headers or payloads may also contain checksums, magic numbers, versions, data types, and content constraints that must be verified separately.

`readFrame` does not read an extra byte to "check stream-wide EOF" because in a multi-frame protocol, the remaining bytes could be the next frame's header. If a protocol specifies **strictly one single frame**, the caller layer should check for trailing data and decide how to handle it. On long-lived open network streams, reading ahead for EOF can block; you cannot blindly check for trailing data by waiting forever.

## 5. When Total Length Is Unknown: Streaming Read with a Quota

Some sources provide no reliable size: socket streams, chunked HTTP bodies, certain compressed formats, or sources generating data over time. Calling `readAllBytes()`, an unbounded `ByteArrayOutputStream`, or `transferTo` into an unbounded sink can consume massive resources.

How to handle it:

1. Set a **maximum total byte limit** per business rules, e.g., `MAX_BYTES`.
2. Use a small buffer and request at most **the remaining permitted bytes**.
3. Update the counter after each successful read; do not confuse `read() == -1` with empty data.
4. Upon reaching the exact quota, determine whether the source has ended or still has bytes. If more bytes remain, report a quota-exceeded error; do not report success with a truncated result when the protocol requires completeness.
5. If writing a business-critical file, use a **temporary file**, clean up on error, and only publish once the whole process succeeds.

### 5.1. Java 17+ Example with Cumulative Quota

Save as **`BoundedBinaryCopyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

public class BoundedBinaryCopyDemo {
    static long copyWithLimit(
            InputStream input, OutputStream output, long maxBytes)
            throws IOException {
        if (maxBytes < 0) {
            throw new IllegalArgumentException(
                    "maxBytes must be nonnegative");
        }

        byte[] buffer = new byte[4096];
        long copied = 0;

        while (true) {
            long remaining = maxBytes - copied;

            if (remaining == 0) {
                // One extra read distinguishes exact size from overflow.
                if (input.read() != -1) {
                    throw new IOException(
                            "Limit exceeded: " + maxBytes);
                }
                return copied;
            }

            int requested = (int) Math.min(
                    (long) buffer.length, remaining);
            int count = input.read(buffer, 0, requested);

            if (count == -1) {
                return copied;
            }
            if (count == 0) {
                throw new IOException("Input made no progress");
            }

            output.write(buffer, 0, count);
            copied += count;
        }
    }

    public static void main(String[] args) throws IOException {
        byte[] source = {10, 20, 30, 40, 50};

        try (InputStream input = new ByteArrayInputStream(source);
             ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            System.out.println("Allowed: "
                    + copyWithLimit(input, output, 5));
        }

        try (InputStream input = new ByteArrayInputStream(source);
             ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            try {
                copyWithLimit(input, output, 4);
            } catch (IOException error) {
                System.out.println("Rejected: " + error.getMessage());
            }
            System.out.println("Partial bytes: " + output.size());
        }
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 BoundedBinaryCopyDemo.java
java BoundedBinaryCopyDemo
```

**Exact stdout:**

```text
Allowed: 5
Rejected: Limit exceeded: 4
Partial bytes: 4
```

**Analysis:**

- Case with limit 5: copies all 5 bytes. The extra probe read returns EOF, so the result is 5.
- Case with limit 4: only the first four bytes are written. The subsequent probe read finds the fifth byte and throws `IOException` rather than returning success.
- The target `ByteArrayOutputStream` still retains the **4 bytes written before the error**. There is no automatic rollback. For real data, never publish partial output; use a temporary file or an appropriate transactional mechanism.
- The extra one-byte read to detect quota overflow **may block** if the source has not emitted EOF. For sockets or infinite sources, configure deadlines, timeouts, or cancellation at the source layer. Some protocols have trusted length prefixes after validation and do not need to wait for connection-wide EOF.
- The example uses `ByteArrayOutputStream` because there are only 5 bytes. In real systems, the output must be a bounded/streaming sink if data is large; a 4 KiB buffer **does not bound total bytes** if the output keeps accumulating.

**Crucial lesson:** Bounding the **buffer** (`4096`) and bounding the **total input** (`maxBytes`) are two distinct things. A loop with a small buffer can still read endlessly if it does not enforce a total cap.

## 6. Reading Exact Bytes and Detecting Truncated Payloads

Different APIs have different contracts:

| API | Behavior to Remember |
| --- | --- |
| `InputStream.read()` | Returns 0–255 for the byte read; `-1` on EOF |
| `InputStream.read(byte[])` | Returns actual bytes read; may be fewer than array size |
| `InputStream.read(byte[], off, len)` | Reads at most `len` bytes; may return fewer; check `count` |
| `DataInputStream.readFully(byte[])` | Reads until array is full or throws `EOFException` if source ends early |
| `DataInputStream.readFully(byte[], off, len)` | Reads the exact requested slice or throws `EOFException` |
| `InputStream.readNBytes(int len)` | Returns array with at most `len` bytes, **may be shorter** on EOF; must check length |
| `InputStream.readAllBytes()` | Reads until EOF, may need huge memory; applies no quota of its own |
| `InputStream.transferTo(OutputStream)` | Copies until EOF; return value is bytes transferred, enforces no quota |
| `Files.size(Path)` | Gets file size reported at one point in time; does not lock contents during reading |
| `InputStream.available()` | Estimates bytes immediately readable without blocking; does **not** report total size or EOF |

Dangerous loop example that assumes one read returns enough:

```java
// WRONG per protocol if exactly 100 bytes are required:
byte[] payload = new byte[100];
int count = input.read(payload);
// count could be 17, 40, or -1; payload is not guaranteed to be full.
```

For a protocol requiring exactly 100 bytes, after bounds validation you can use `DataInputStream.readFully(payload)` or a loop accumulating `count` until full; early EOF must be treated as incomplete data, not zero-padded tails.

### 6.1. Handling Truncated Headers

`DataInputStream.readInt()` reads 4 bytes in big-endian. If only 1–3 bytes arrive before EOF, it throws `EOFException` before producing a valid `declaredLength`. Never substitute a default of 0 and treat it as an empty frame. You must distinguish EOF right at a frame boundary (potentially a valid end) from EOF **mid-header** or **mid-payload** (malformed format).

### 6.2. What About Bytes After the Frame?

If the protocol allows consecutive frames, read the exact bytes of the current frame and leave remaining bytes for reading the next header. If the file format permits only one frame, trailing bytes are either an error or metadata depending on the specification. Never call `available() == 0` to conclude "end of frame": `available` is insufficient to determine structure.

## 7. Arithmetic Checks to Prevent Overflow and Unit Errors

When a length field is an **element count**, you must compute total bytes. For example, an image has `width`, `height`, `channels`, and `bytesPerChannel`, each potentially supplied by input. Never write:

```java
// DANGEROUS: int multiplication can overflow.
int bytes = width * height * channels * bytesPerChannel;
byte[] pixels = new byte[bytes];
```

This is an illustrative snippet with undeclared variables. `int` multiplication can overflow into negative or small positive numbers; the code may then allocate incorrectly or pass bounds checks wrongly. Widen to `long` **before the first multiplication**, check each dimension's range and total bytes, and only cast to `int` after confirming it fits.

Illustrative pattern using `long` and `Math.multiplyExact`:

```java
// Illustration: width, height, channels are numbers read from the header.
// Not standalone without variable declarations and constraints.
if (width <= 0 || height <= 0 || channels <= 0) {
    throw new IOException("Invalid dimensions");
}

long pixels;
long totalBytes;
try {
    pixels = Math.multiplyExact((long) width, (long) height);
    totalBytes = Math.multiplyExact(pixels, (long) channels);
} catch (ArithmeticException overflow) {
    throw new IOException("Dimensions overflow", overflow);
}

long maxImageBytes = 8L * 1024 * 1024;
if (totalBytes > maxImageBytes) {
    throw new IOException("Image too large");
}
byte[] image = new byte[(int) totalBytes];
```

The example assumes **one byte per channel**; if `bytesPerChannel` exists, multiply it using checked arithmetic too. This illustrates the validation structure and does not yet verify colors, stride, padding, metadata size, or image integrity.

Why not just check `bytes <= Integer.MAX_VALUE`? Because real budgets are usually much smaller, and allocating near Java's array size limit is completely inappropriate under concurrent requests. Avoid narrowing `long` or unsigned lengths to `int` **before** checking bounds, as casting alters values.

### 7.1. Unsigned Length and Endianness

A 4-byte header might be defined as `uint32` instead of signed `int`. Java's `DataInputStream.readInt()` interprets it as signed two's complement; if the actual format is unsigned, values above `Integer.MAX_VALUE` appear as negative numbers.

If the protocol uses unsigned 32-bit big-endian, interpret it via:

```java
// Illustration assuming an opened DataInputStream input:
long unsignedLength = Integer.toUnsignedLong(input.readInt());
if (unsignedLength > MAX_ALLOWED_BYTES) {
    throw new IOException("Length too large");
}
```

**Do not** cast `unsignedLength` to `int` right away. `MAX_ALLOWED_BYTES` must be defined and enforced first, usually far below `int` limits. For little-endian, use an appropriate API/reader, such as `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` after bounding input sizes. Reading with the wrong endianness can turn a tiny length into an enormous number.

### 7.2. Addition When Summing Parts

If multiple chunks have length `length`, do not write `total += length` first and then ask "did it exceed max?" when `total` risks overflowing. For non-negative numbers and a defined limit, check first:

```java
// Illustration: total >= 0, length >= 0, maxBytes >= 0.
if (length > maxBytes - total) {
    throw new IOException("Total size exceeded");
}
total += length;
```

This is sound when `0 <= total <= maxBytes` and `length >= 0` hold. If those invariants aren't maintained, use `Math.addExact` and bounds checks before using the sum. Never treat a per-chunk quota as sufficient protection for the sum across many chunks.

## 8. File Metadata, TOCTOU, and Data Changing During Reads

You can check size before opening a file:

```java
// Illustration; path is a valid Path controlled by the caller.
long size = java.nio.file.Files.size(path);
if (size < 0 || size > MAX_ALLOWED_BYTES) {
    throw new IOException("File too large");
}
```

This check is helpful for regular files of stable size, yet **it is not the sole safeguard**:

- Between calling `Files.size` and opening/reading, the file may be modified, replaced, or grow. This is the *time of check to time of use* (TOCTOU) issue.
- Many non-regular-file sources (sockets, pipes, devices, compressed streams) have no reliable total length.
- Special filesystems can behave differently from regular files regarding size.
- `InputStream.available()` does not mean "total remaining bytes"; using it to allocate or confirm end-of-data is wrong.

When strict limits are required, **enforce them while reading**, while optionally using metadata to fail fast on obviously oversized files. When defending against intentional file/path modification, also control path resolution, permissions, symlinks, file identity, and handle lifecycles per system design.

## 9. Data Forms Needing More Than One Quota

### 9.1. Compressed Data and Expansion Risks

A ZIP/gzip file can be tiny on disk yet decompress into vast amounts of data. Checking compressed file size before allocating is **not enough**. When using `GZIPInputStream`, `ZipInputStream`, or other decompressors, enforce quotas on **total decompressed output bytes** and total files/entries, sanitize entry paths if writing to disk, and bound nesting depth and processing time if required by the application.

### 9.2. Record Counts, Dimensions, and Nested Structures

If a header states there are 10 million elements, a single frame might not look huge on its own, yet the resulting Java object graph can be many times larger than the wire bytes. Cap element counts, nesting depth, array dimensions, and estimated total memory before constructing structures. For matrices, images, or multi-channel audio, check dimension multiplications safely as in section 7.

### 9.3. Character Strings Inside Binary Frames

If a frame holds a UTF-8 string, cap the **byte count** before allocating/decoding; Java character counts can differ from byte counts. Then validate charset, malformed-input policy, and character/code-point limits if required by business logic. Never use `String.length()` as a proxy for wire byte count.

### 9.4. Data Coming from the Network

Length prefixes can be forged. Beyond byte limits, enforce read timeouts/deadlines, cancellation, connection limits, and concurrent request limits. If a peer announces 1,024 bytes and trickles them very slowly, a `readFully` can still hang for a long time even after the size passed validation. Never use `InputStream.available()` to "avoid blocking": it does not tell you when a complete frame will arrive.

## 10. Pre-Allocate or Process in Chunks?

| Scenario | Suitable Approach | Why |
| --- | --- | --- |
| Small frame with trusted size after validation | Validate bounds → `new byte[length]` → `readFully` | Easy array parsing, clear EOF control |
| Very large file needing sequential copy/hash/scan | Bounded buffer, chunked loop | Avoids holding all bytes in memory |
| Source with unknown length | Streaming + total quota + timeout/cancellation | Avoids unbounded reads/accumulation |
| Metadata declares size, yet file may change | Metadata check to fail fast **plus** read-time quota | Prevents size TOCTOU |
| Compressed data | Limit both input and decompressed output | Prevents decompression bombs |
| Collection of records with count/length | Validate count, length, cumulative sum, and products | Prevents overflow and heap exhaustion |
| Need to preserve old output file if input fails | Write temp file → verify → publish/replace per policy | Avoids overwriting real file with partial data |

If you only need the SHA-256 of a multi-GB file, read in chunks to update the digest; do not read all bytes into one array. If you want to parse a small frame into an object, validating length upfront and reading that exact frame makes sense.

## 11. Common Mistakes and How to Fix Them

1. **Trusting the header immediately:** reading `length` from an untrusted source and allocating without a `MAX_LENGTH`.
2. **Checking only `length > MAX`:** misses negative numbers; some formats also forbid length 0.
3. **Narrowing `long`/unsigned to `int` too early:** can overflow or turn negative, breaking bounds checks.
4. **Multiplying/adding sizes in `int`:** arithmetic overflows before total-byte checks run.
5. **Assuming `read(byte[])` fills the buffer:** may return fewer bytes; must loop until full or fail on early EOF.
6. **Treating early EOF as valid data:** the pre-allocated array holds zero bytes in the unread tail; never accept silently.
7. **Trusting `available()` for total size:** this API only estimates bytes available without blocking.
8. **Calling `readAllBytes()` on unbounded sources:** can exhaust heap or block indefinitely.
9. **Enforcing quotas only per chunk:** a million small chunks still blow the budget.
10. **Measuring only compressed bytes:** decompressed data can expand massively.
11. **Confusing bytes with characters:** UTF-8 maps a code point to varying byte counts.
12. **Failing to limit record counts beyond expectation:** one small frame does not mean the whole connection is small.
13. **Assuming `Files.size` never changes:** does not protect against file growth/modification while reading.
14. **Omitting timeouts on network sources:** a length-valid frame might still never finish arriving.
15. **Writing output directly and leaving it visible on error:** partial data may look like a finished file.
16. **Skipping magic/version/checksum checks:** a valid length does not guarantee valid format or content.

## 12. Testing Checklist and Exercises

### 12.1. Testing a Length-Prefixed Frame

- **Length = 0**: accept or reject per specification; do not assume automatically invalid.
- **Length = 1**: reads exactly one byte.
- **Length = MAX**: accept when sufficient payload and resources exist.
- **Length = MAX + 1**: reject **before allocating**.
- **Length = -1**: reject before creating array.
- **Header missing 1–3 bytes**: `readInt` reports early EOF.
- **Payload missing one byte**: `readFully` throws `EOFException`.
- **Exact payload**: parse/validate contents per format.
- **Trailing bytes**: handle per single-frame or multi-frame rules.
- **Multiple consecutive valid frames**: enforce total byte and count quotas.
- **Slow source**: timeouts/deadlines trigger at the source layer.

### 12.2. Practice Exercises

1. Change `MAX_PAYLOAD_BYTES` in `SafeFrameDemo` to `3`, test lengths 0, 3, 4, and -1; record the expected behavior.
2. Modify the example's input to have a 4-byte header yet only 3 payload bytes; demonstrate that the code throws `EOFException`.
3. Write a parser for `count (int) + count × 8 bytes`, using `Math.multiplyExact((long) count, 8L)`, validating negative values, element count, and total bytes before allocating.
4. In `BoundedBinaryCopyDemo`, test max values of 0, 4, 5, and 6. Distinguish empty input, exact-fit, and over-limit cases; point out the partial output after an error.
5. Design a multi-frame protocol: each frame ≤ 1 MiB, total per request ≤ 16 MiB. How do you check the total quota **before adding a frame's length**?
6. Compare calling `Files.size` before opening with counting bytes while reading; describe a file change between those two steps that invalidates the metadata.
7. Design compressed-file processing with a 50 MiB output cap; explain why checking initial ZIP/gzip size alone is insufficient.
8. For a protocol with a little-endian `uint32` field, choose the right API to read the header, convert to `long`, validate, and only cast to `int` afterward when truly necessary.
9. Simulate a slow source or one throwing `IOException`; verify graceful stopping, stream closing, and that no incomplete target file is published.

## 13. Self-Assessment

You have mastered this lesson when you can clearly explain:

- Why `new byte[dataInput.readInt()]` is risky even when "normal" senders only send small payloads?
- Why `DataInputStream.readFully` is essential yet **does not replace** pre-allocation size validation?
- How `readNBytes(length)` and `readAllBytes()` can drive up memory usage?
- Why the byte count from `available()` differs from total source size?
- Why multiplications/additions must be checked **before** passing the result to an allocator?
- What is the difference between a 4 KiB buffer limit and a 4 MiB total input limit?
- When must **decompressed bytes** and element counts be bounded rather than compressed bytes alone?
- If reading fails mid-payload, how must bytes already written to the target file be handled?

**Takeaway:** A length obtained from an external source is only an **untrusted claim**. Define valid units and ceilings, validate size arithmetic and counts before allocating, then demand exact bytes or fail. For data without a trusted length, read in chunks with a **cumulative quota**, enforce timeouts, and handle partial outputs cleanly. This protects both data correctness and memory/I/O resource budgets.
