# `skip`, `skipNBytes`, and the Limits of Skipping Data in Java Byte Streams

In Java I/O, a program sometimes needs to skip over a segment of data to read what follows: skipping a fixed header, skipping a field that does not need to be processed yet, or advancing to the payload. Two commonly used methods on `java.io.InputStream` are `skip(long n)` and `skipNBytes(long n)`. Both *consume/skip bytes from the current position*, but they differ in their completion guarantee, return value, and error reporting.

This article belongs to the **byte streams** (`InputStream`) group. Every `n` below is measured in **bytes**, not characters, line counts, or Java elements.

## 1. Understanding What “Skipping” Really Means

Imagine a stream containing the bytes `A B C D E F G` with the read cursor currently at `A`:

```text
Before: [A] B  C  D  E  F  G
Skip 3 bytes:
After:   A  B  C [D] E  F  G
```

The three bytes `A`, `B`, and `C` have been consumed; the next `read()` returns the byte `D`. Skipped data is not automatically restored. Neither method closes the stream, returns the skipped content, or creates a random-access position that can jump backward like `FileChannel.position(...)`.

“Skipping” is not synonymous with “fast seeking”. The default `InputStream.skip` implementation may **read and discard** bytes using a temporary buffer; some subclasses use a more efficient mechanism. With network streams, decompression streams, or wrapper streams, skipping may still have to read/process underlying data and can block.

## 2. `skip(long n)`: Request to Skip, Receive the Actual Byte Count

API signature:

```java
public long skip(long n) throws IOException
```

- `n` is the desired number of bytes to skip.
- The `long` return value indicates **the actual number of bytes skipped**. It can be smaller than `n`, or even `0`; never assume the result is always equal to `n`.
- A partial skip can be caused by end-of-stream (EOF), subclass characteristics, or other I/O conditions. `skip(n) == 0` is **not enough** to conclude for certain that EOF has been reached.
- For `n <= 0`, the default `InputStream` implementation skips 0 bytes and returns `0`; subclasses may specify different behavior for negative numbers. Application code should reject `n < 0` if it represents an invalid length.
- When an I/O error occurs, the method may throw `IOException`. Do not assume the stream position remains unchanged after an error.

**Rule:** If you only need to skip *at most* `n` bytes and a smaller count is acceptable, always use the return value to calculate how many bytes were actually consumed.

For example, on a `ByteArrayInputStream` containing three bytes, `skip(5)` skips only three bytes and returns `3`. The next read returns `-1` because the stream is exhausted. This is the behavior of that specific example; do not treat that result as a guarantee for every kind of `InputStream`.

## 3. `skipNBytes(long n)`: Require Skipping the Full Number of Bytes

API signature (available since **Java 12**, usable in Java 17+):

```java
public void skipNBytes(long n) throws IOException
```

- If it completes normally, the method has skipped exactly `n` bytes per the API contract; there is no return value.
- If EOF is encountered before `n` bytes have been skipped, it throws `EOFException` (a subclass of `IOException`).
- It can also throw `IOException` if an I/O error occurs, the underlying `skip` result is abnormal, or it cannot advance to the required position.
- In the default implementation, `n == 0` or `n < 0` skips no bytes; subclasses may handle negative values differently. Validate `n >= 0` at business boundaries so invalid lengths are not silently accepted.
- The method may block until enough bytes are skipped, EOF is reached, or an error occurs; it does not impose a timeout.

How the **default implementation** works (worth remembering): it calls `skip(remaining)` repeatedly. If `skip` returns `0`, it tries `read()` for one byte to make progress or detect EOF. If `skip` returns a negative number or more than the remaining bytes to skip, it throws `IOException`. Subclasses may override this for optimization.

**Rule:** Use `skipNBytes(n)` when the data structure requires skipping **exactly** `n` bytes before reading the next part. If the stream is too short, the failure is clearly signaled with an exception.

## 4. Quick Comparison

| Criterion | `skip(n)` | `skipNBytes(n)` |
| --- | --- | --- |
| Contract | Skips up to as much as the implementation can; may fall short | Skips all `n` bytes or reports an error |
| Return value | `long`: number of bytes skipped | `void` |
| EOF before enough bytes | May return a number smaller than requested | Throws `EOFException` |
| Returning `0` when more skipping is needed | Possible; the caller must decide how to proceed | Default implementation tries `read()` to advance or detect EOF |
| Use when | Best-effort skipping, and you need the actual count | Mandatory headers/fields requiring full length |
| Java version | Available since the earliest Java versions | Available since Java 12 |

Both methods consume the stream at the **current position**. Do not use `skipNBytes` on Java 8/11 because this API does not exist in those versions.

## 5. Directly Runnable Java 17+ Example

Save as `SkipExample.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class SkipExample {
    public static void main(String[] args) throws IOException {
        byte[] sevenBytes = "ABCDEFG".getBytes(StandardCharsets.US_ASCII);

        // skip returns the actual number of bytes skipped.
        try (InputStream in = new ByteArrayInputStream(sevenBytes)) {
            long skipped = in.skip(3);
            System.out.println("skip(3): " + skipped
                    + ", next: " + (char) in.read());
        }

        // skipNBytes guarantees the full length if it returns normally.
        try (InputStream in = new ByteArrayInputStream(sevenBytes)) {
            in.skipNBytes(3);
            System.out.println("skipNBytes(3) next: " + (char) in.read());
        }

        // The source has only 3 bytes, but 5 bytes are requested to be skipped.
        try (InputStream in = new ByteArrayInputStream(new byte[] {10, 20, 30})) {
            System.out.println("skip(5) on 3 bytes: " + in.skip(5));
            System.out.println("next at EOF: " + in.read());
        }

        try (InputStream in = new ByteArrayInputStream(new byte[] {10, 20, 30})) {
            try {
                in.skipNBytes(5);
                System.out.println("unexpected success");
            } catch (EOFException e) {
                System.out.println("skipNBytes(5): EOFException");
            }
        }

        // This wrapper intentionally allows skipping at most 1 byte per call.
        try (InputStream in = new OneByteSkippingInputStream(
                new ByteArrayInputStream(sevenBytes))) {
            System.out.println("single skip(3): " + in.skip(3));
            System.out.println("next after one skip: " + (char) in.read());
        }

        try (InputStream in = new OneByteSkippingInputStream(
                new ByteArrayInputStream(sevenBytes))) {
            in.skipNBytes(3);
            System.out.println("next after exact skip: " + (char) in.read());
        }
    }

    private static final class OneByteSkippingInputStream
            extends FilterInputStream {
        OneByteSkippingInputStream(InputStream in) {
            super(in);
        }

        @Override
        public long skip(long n) throws IOException {
            return super.skip(Math.min(n, 1L));
        }
    }
}
```

Compile and run in the directory containing the file:

```bash
javac SkipExample.java
java SkipExample
```

Exact stdout:

```text
skip(3): 3, next: D
skipNBytes(3) next: D
skip(5) on 3 bytes: 3
next at EOF: -1
skipNBytes(5): EOFException
single skip(3): 1
next after one skip: B
next after exact skip: D
```

The final part intentionally uses a wrapper that skips at most 1 byte per call: a single `skip(3)` advances only one byte so the next read is `B`; `skipNBytes(3)` continues calling `skip` until all three bytes are skipped so the next read is `D`. This is why you must never write `in.skip(3);` and assume the stream has definitely advanced three bytes.

## 6. When You Need the Actual Count but Want to Try Skipping Up to a Limit

If the business requirement is “skip at most `n` bytes, stop upon reaching EOF, and **return the actual total bytes skipped**”, a single `skip(n)` call is not reliable enough because it may under-skip. You can write a loop helper with a safeguard against infinite loops when `skip` returns `0`.

The following method can be placed in a Java class that uses `java.io.InputStream` / `java.io.IOException`:

```java
static long skipUpTo(InputStream in, long requested) throws IOException {
    if (requested < 0) {
        throw new IllegalArgumentException("requested must be >= 0");
    }

    long remaining = requested;

    while (remaining > 0) {
        long skipped = in.skip(remaining);

        if (skipped < 0 || skipped > remaining) {
            throw new IOException("Invalid skip result: " + skipped);
        }

        if (skipped > 0) {
            remaining -= skipped;
            continue;
        }

        // skip(remaining) == 0: try consuming 1 byte to make progress.
        if (in.read() == -1) {
            break;  // EOF: return however many bytes were skipped up to that point.
        }
        remaining--;
    }

    return requested - remaining;
}
```

With the source `"ABCDE"`, calling `skipUpTo(in, 3)` returns `3` and the next `read()` returns byte `D`. Calling `skipUpTo(in, 8)` on a new stream with the same data returns `5` and leaves the stream at EOF. Each iteration either decreases `remaining`, breaks out, or throws an exception; thus it avoids an infinite loop when a subclass returns `0`.

This method is suitable when running short of data is an acceptable outcome. If **missing bytes is an error**, use `skipNBytes` to express intent directly; do not rewrite an unnecessary loop. For inputs from networks or pipes, both `skipNBytes` and a custom loop can wait for data; timeouts/cancellation must be managed using mechanisms appropriate to the I/O source.

## 7. Limits and Important Misconceptions

### 7.1. Byte Count Differs from Character Count

`InputStream` operates on raw bytes. For example, the UTF-8 encoded string `"é"` is typically **2 bytes** long; `skip(1)` inside UTF-8 data can leave the next decode in the middle of a character and produce replacement characters or decoding errors. Do not use `skip` to jump “5 characters” in a multibyte text file. When text processing is needed, use a `Reader` with an explicit charset and count in corresponding character units, or design a format with clear byte boundaries.

### 7.2. `skip` Does Not Prove You Have Reached the Required Position

This is a bug:

```java
in.skip(headerLength);             // Skips fewer bytes without knowing!
int firstPayloadByte = in.read();   // May still be in the middle of the header.
```

If the header has a mandatory length, after checking `headerLength >= 0`, use:

```java
in.skipNBytes(headerLength);
int firstPayloadByte = in.read();   // Only runs when the full header has been skipped.
```

Both snippets are **illustrative code fragments**: `in` is a valid `InputStream`, `headerLength` is a determined byte count, and the caller must handle `IOException`. If the file/protocol does not contain the full header, the second snippet throws `EOFException` before processing the payload.

### 7.3. `available()` Is Not “the Number of Bytes Remaining in the File”

`available()` is only an **estimate of bytes that can be read or skipped without blocking**, not the remaining data size of every kind of stream. It may return `0` while data will arrive later (especially with network streams). Therefore, never use `skip(in.available())` to “go to EOF”, and never rely on `available() == 0` to conclude that data is exhausted.

### 7.4. Exceptions Do Not Automatically Undo Consumed Bytes

When `skipNBytes(100)` throws `EOFException` at byte 80, the bytes already consumed **do not rewind automatically**. After an `IOException`, the stream position/state may no longer be trustworthy; handle errors at the record/protocol level, typically by stopping parsing and closing the stream. If re-reading is needed, `mark/reset` only works when `markSupported()` is `true` and the mark limit still holds; never assume every stream supports it.

### 7.5. Results and Cost Depend on the `InputStream` Subclass

- `ByteArrayInputStream` operates on a byte array already in memory; the examples above have clear, reproducible behavior.
- `BufferedInputStream` can take advantage of buffered data; wrapping with a buffer does not turn a stream into a random-access device.
- `FileInputStream` and `InputStream` implementations for sockets, ZIP, or decompression streams have different mechanisms. Never assume `skip` is always O(1), never blocks, or always stops cleanly at file boundaries.
- `skipNBytes` may call `skip` multiple times, and in the default implementation may read byte-by-byte when `skip` returns `0`. A guarantee on **byte count** is different from a guarantee on **performance**.
- Do not use `skip` to bypass validation of a field whose content, checksum, or record boundary must be verified. Skipping bytes only moves forward in the stream; it does not validate data.

### 7.6. Do Not Confuse `skipNBytes` with `readNBytes` or Seeking

- `readNBytes(...)` **retrieves data into a buffer/array**; `skipNBytes(...)` **discards** data as it advances.
- `skip(n)` returns the number of bytes **skipped**, whereas `read()` returns data or `-1` at EOF.
- If you need to access arbitrary positions in a file and know the absolute offset, consider `FileChannel.position(long)` / `SeekableByteChannel` instead of sequential reading/skipping. With ZIP or decompression streams, position in decompressed bytes is not the same as the offset in the compressed file.

## 8. Practical Scenario: Fixed-Length Header Before Payload

Suppose a binary message has 4 magic bytes and 2 version bytes, followed by the payload. If this step is only supposed to skip the exact 6 header bytes (because the header was already processed/verified elsewhere):

```java
static int readFirstPayloadByte(InputStream in) throws IOException {
    in.skipNBytes(6);
    return in.read();   // -1: no payload after the header.
}
```

With a stream shorter than 6 bytes, `skipNBytes(6)` throws `EOFException`, helping distinguish a **truncated header** from a **complete header with an empty payload** (`read() == -1`). In a real application, if magic/version must be checked, you must **read and validate the header bytes** instead of skipping them. If the header length comes from untrusted input, validate that it is non-negative and cap it at a maximum limit before skipping to avoid long waits or reading through an unreasonable amount of data.

## 9. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Solution |
| --- | --- | --- |
| Calling `skip(n)` and ignoring the return value | Parser reads misaligned fields on a short skip | Use `skipNBytes` or accumulate the actual byte count |
| Looping `while (remaining > 0) remaining -= in.skip(remaining);` | Can loop infinitely when `skip` returns `0` | When `0` is returned, try `read()` for one byte or stop per contract |
| Using `available()` as the total remaining size | Truncates data on streams/sockets | Rely on protocol length, EOF, or actual bytes read |
| Confusing Unicode character count with UTF-8 bytes | Splits in the middle of a character's bytes | Choose the right unit and charset; handle text with appropriate APIs |
| Treating `skipNBytes` as an atomic/rollback operation | Continues parsing in a corrupt state after EOF/IOException | Handle the error, terminate the record, and close the stream when needed |
| Targeting Java 8/11 while calling `skipNBytes` | Compilation error because the API does not exist | Require Java 12+ or implement a checked loop |
| Skipping a header that needs validation | Lets malformed data slip through | Read and validate the header before processing the payload |

## 10. Knowledge Self-Check

1. If a real stream only has 4 bytes, does calling `skip(10)` always return `4`? **No.** `skip` can return fewer bytes for many reasons; only the return value of the call tells you how many were skipped. For a four-byte `ByteArrayInputStream`, it returns `4`.
2. `skip(6)` returns `2`; can you read the payload immediately? **No**, if you need to skip all 6 bytes; you must handle the remaining 4 bytes or use `skipNBytes(6)` from the start.
3. What happens if `skipNBytes(5)` has only 3 bytes left until EOF? It throws `EOFException`; the three bytes may already have been consumed.
4. Does `skip(4)` returning `0` guarantee EOF? **No**. Never rely solely on `0` to draw that conclusion.
5. Should you use `skip(1)` to skip one UTF-8 character? **No**, unless you know the byte size and character boundaries.
6. When should you use `skipNBytes`? When the record/protocol requires **advancing an exact number of bytes**, and missing bytes must be treated as an error.

## API References

- [Java 17 — `InputStream.skip(long)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#skip(long)).
- [Java 17 — `InputStream.skipNBytes(long)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html#skipNBytes(long)).

**Key takeaway:** `skip` tells you *how much was skipped*; `skipNBytes` demands *skipping an exact amount or reporting an error*. Both operate on bytes of the current stream, so always validate lengths, handle EOF/IOException, and choose the appropriate data access method.