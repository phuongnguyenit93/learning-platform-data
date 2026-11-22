# How readFully Differs from read and Handling EOFException in Java I/O

When processing **binary data**, you cannot assume a single read call will receive the required number of bytes. A 4-byte header, a fixed 16-byte record, or a payload with a declared length of 1,024 bytes must each be read for the **exact requested byte count** before decoding into a complete structure. This is the core difference between `read(...)` and `readFully(...)`.

- **`read(...)`**: performs a single read attempt and **returns the number of bytes actually received**. This count may be smaller than the requested length; `-1` normally indicates EOF.
- **`DataInputStream.readFully(...)`**: reads repeatedly until **all requested bytes are obtained**, or throws **`EOFException`** if the stream ends beforehand. The method returns `void`, not a byte count.
- **`EOFException`**: signals "end of data reached before completing a required structure", which must be handled according to business meaning: truncated message, incomplete file, prematurely closed connection, or missing format data.

This article aims to clarify when to accept a **short read**, when to require an **exact length**, and how to avoid using incomplete data after an `EOFException`.

## 1. Distinguishing "Currently Available" vs. "Sufficient per Format"

Suppose part of a binary file declares that the next payload **must be 5 bytes long**. The I/O layer only delivers 2 bytes on the first pass:

```text
Required: 5 bytes of data

Source:   A B C D E
read #1:  A B           -> returns 2
read #2:      C D       -> returns 2
read #3:          E     -> returns 1
read #4: EOF

Single read(buffer[5]):     may only receive A B
readFully(buffer[5]):       continues until all A B C D E are received
```

If you call `read(buffer)` and assume the buffer already holds all 5 bytes, the remaining three slots may still hold default values or stale data. If bytes are truly missing, `readFully` must fail. **A read returning fewer bytes than the buffer size does not mean EOF**: a network stream can deliver data in multiple chunks.

| Criterion | `read(byte[])` | `DataInputStream.readFully(byte[])` |
| --- | --- | --- |
| Purpose | Get available bytes from one read attempt | Get **exactly N bytes** as requested |
| Underlying read calls | Not required to loop until filled | Keeps reading if a previous read was short |
| Return value | `int` = byte count, or `-1` on EOF | `void` |
| Source ends before N bytes | May return `-1` / fewer bytes | Throws `EOFException` |
| Must check byte count manually? | **Yes** | Success means all N were read |
| Suitable scenarios | Copying a stream to EOF, chunk processing | Reading headers, records, known-length payloads |

The rules above assume a buffer of **positive** length. Reading `0` bytes is a special case: `readFully(b, off, 0)` succeeds even when the stream is at EOF; `InputStream.read(b, off, 0)` returns `0`.

## 2. What Does `read(byte[])` Return?

`InputStream.read(byte[])` and `DataInputStream.read(byte[])` have the signature:

```java
int bytesRead = input.read(buffer);
```

This illustrative snippet assumes `input` is an existing `InputStream` or `DataInputStream` and `buffer` is a `byte[]`.

For `buffer.length > 0` and an `InputStream` adhering to the standard contract, the result is:

- `1..buffer.length`: valid byte count **from that single call**;
- `-1`: EOF, no more bytes to read;
- `IOException`: I/O error.

For example, `byte[] buffer = new byte[8192]` does not guarantee `read(buffer) == 8192`. The source might return 1, 2, or a few hundred bytes even while more data is forthcoming. **Never use a single `read` call to conclude an entire message was received.**

### When Total Length Is Unknown: Loop by Byte Count

```java
byte[] buffer = new byte[8192];
int n;

while ((n = input.read(buffer)) != -1) {
    output.write(buffer, 0, n);
}
```

This is an illustrative snippet with opened `input` and `output`. `output.write(buffer, 0, n)` writes **exactly the `n` bytes just read**, avoiding writing garbage from unfilled slots or stale data. Looping until EOF is suitable for **copying an entire stream**; if a protocol defines an individual length per message, EOF does not replace message boundary control.

## 3. How Does `DataInputStream.readFully(...)` Work?

`DataInputStream` implements the `DataInput` interface, providing methods to read structured binary data. Two main overloads:

```java
dataInput.readFully(buffer);
dataInput.readFully(buffer, offset, length);
```

These snippets assume `dataInput` is a `DataInputStream` and `buffer` is a `byte[]`.

- `readFully(buffer)` requires filling **all** `buffer.length` bytes.
- `readFully(buffer, offset, length)` requires filling exactly `length` bytes, starting at index `offset`. Elements outside the target slice are not written to.
- If **enough bytes are read**, the method completes normally and returns no count. **There is no need** for an extra `read` to "confirm completeness".
- If **EOF occurs before completion**, it throws `EOFException`, a subclass of `IOException`.
- If another I/O error occurs, it may throw the corresponding `IOException`.
- If `offset` or `length` arguments are invalid, the method throws an index error; do not treat this programming bug in the EOF handling branch.

Example requiring the exact first 8 bytes of a record:

```java
byte[] header = new byte[8];
dataInput.readFully(header);  // Proceed only after all 8 bytes are received.
parseHeader(header);         // parseHeader is an illustrative business method.
```

**Key point:** do not call `parseHeader` if `readFully` throws `EOFException`. When bytes are missing, the buffer contents may have been **partially modified**. Because `readFully` returns `void`, it does not report how many bytes were filled before failing; never treat a partial buffer as a valid header.

### Internal Loop Principle

You can picture `readFully(b, off, len)` performing logic similar to:

```java
// Pseudocode to explain the idea, not library source code.
int total = 0;
while (total < len) {
    int n = input.read(b, off + total, len - total);
    if (n == -1) {
        throw new EOFException();
    }
    total += n;
}
```

This is **pseudocode** assuming `input` obeys the contract for positive-length buffer reads; do not use it to replace the JDK implementation or skip handling custom contract-violating streams that repeatedly return `0`. The goal is to understand why a short `read` does **not** make `readFully` give up, whereas EOF before filling completely **is an error**.

## 4. Standalone Java 17+ Example: Short Read, readFully, and EOFException

The following program intentionally wraps `InputStream` so that **each array read receives at most 2 bytes**, even when a larger buffer is requested. This lets us observe the behavior even though a normal `ByteArrayInputStream` could deliver many bytes in a single call.

Save with the exact filename **`ReadFullyDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;

public class ReadFullyDemo {

    public static void main(String[] args) throws IOException {
        demonstrateShortRead();
        demonstrateTruncatedInput();
        demonstrateLengthPrefixedFrame();
    }

    private static void demonstrateShortRead() throws IOException {
        byte[] source = "ABCDE".getBytes(StandardCharsets.US_ASCII);
        byte[] result = new byte[5];

        try (DataInputStream input = new DataInputStream(
                new TwoByteInputStream(new ByteArrayInputStream(source)))) {

            int first = input.read(result);
            System.out.println("First read: " + first);

            input.readFully(result, first, result.length - first);
            System.out.println("Reconstructed: " +
                    new String(result, StandardCharsets.US_ASCII));
            System.out.println("EOF after data: " + input.read());
        }
    }

    private static void demonstrateTruncatedInput() throws IOException {
        byte[] shortSource = {10, 20, 30};
        byte[] requestedFive = new byte[5];
        Arrays.fill(requestedFive, (byte) -1);

        try (DataInputStream input = new DataInputStream(
                new TwoByteInputStream(
                        new ByteArrayInputStream(shortSource)))) {

            try {
                input.readFully(requestedFive);
                System.out.println("Unexpected success");
            } catch (EOFException e) {
                System.out.println("Truncated: " +
                        e.getClass().getSimpleName());
            }
        }

        // Only illustrates a partially filled buffer; NEVER
        // process this buffer as a valid record.
        System.out.println("Partial buffer (invalid): " +
                Arrays.toString(requestedFive));
    }

    private static void demonstrateLengthPrefixedFrame()
            throws IOException {
        byte[] message = "Xin chào".getBytes(StandardCharsets.UTF_8);

        ByteArrayOutputStream wire = new ByteArrayOutputStream();
        try (DataOutputStream output = new DataOutputStream(wire)) {
            output.writeInt(message.length);
            output.write(message);
        }

        try (DataInputStream input = new DataInputStream(
                new TwoByteInputStream(
                        new ByteArrayInputStream(wire.toByteArray())))) {

            int declaredLength = input.readInt();

            if (declaredLength < 0 || declaredLength > 1024) {
                throw new IOException("Invalid frame length");
            }

            byte[] payload = new byte[declaredLength];
            input.readFully(payload);

            System.out.println("Frame bytes: " + payload.length);
            System.out.println("Frame text: " +
                    new String(payload, StandardCharsets.UTF_8));
        }
    }

    private static final class TwoByteInputStream
            extends FilterInputStream {

        private TwoByteInputStream(InputStream source) {
            super(source);
        }

        @Override
        public int read(byte[] target, int offset, int length)
                throws IOException {
            return super.read(
                    target, offset, Math.min(length, 2));
        }
    }
}
```

Compile/run with JDK 17+:

```bash
javac -encoding UTF-8 ReadFullyDemo.java
java ReadFullyDemo
```

**Expected stdout:**

```text
First read: 2
Reconstructed: ABCDE
EOF after data: -1
Truncated: EOFException
Partial buffer (invalid): [10, 20, 30, -1, -1]
Frame bytes: 9
Frame text: Xin chào
```

Interpreting the three cases:

1. **Short read:** the source has all of `ABCDE`, yet is capped at returning at most 2 bytes per read. `read(result)` returns `2`; calling `readFully(result, 2, 3)` reads the remaining `CDE`. Only now can all 5 bytes be processed.
2. **Truncated:** the source only has `10, 20, 30` while the target requires 5 bytes. `readFully(requestedFive)` fills several bytes, hits EOF, and throws `EOFException`. Buffer contents after the error may have changed; printing the buffer **only reveals partially filled data**, not an "approximate result" permitted for use.
3. **Length-prefixed frame:** `DataOutputStream.writeInt(message.length)` writes a 4-byte length per `DataOutput`'s big-endian convention, then writes the UTF-8 payload. `DataInputStream.readInt()` reads the exact bytes for an `int`, then `readFully(payload)` receives the full declared byte count. The string `"Xin chào"` has 9 UTF-8 bytes and is decoded properly after full receipt.

The `TwoByteInputStream` wrapper is a tool simulating a source returning few bytes; code must never rely on per-read byte counts when operating on real networks or files.

## 5. Understanding `EOFException` Properly

`EOFException` inherits from `IOException`:

```text
Exception
  -> IOException
       -> EOFException
```

Core differences:

| Operation | On EOF | Interpretation |
| --- | --- | --- |
| `InputStream.read()` | Returns `-1` | No more bytes per single-byte read API |
| `InputStream.read(byte[])` (positive buffer) | Returns `-1` if already ended before reading more | Normal end of a stream |
| `DataInputStream.readFully(byte[N])` | Throws `EOFException` if fewer than N remain | Insufficient data for a required structure |
| `DataInputStream.readInt()` | Throws `EOFException` if bytes for `int` are missing | Cannot form a complete `int` |
| `RandomAccessFile.readFully(byte[N])` | Throws `EOFException` if fewer than N bytes remain | Insufficient data in the file |

**EOF is not always an error.** Reading a stream until it ends is valid business logic: `read(...)` returning `-1` is a normal signal. However, when a record **must** be N bytes long, hitting EOF before N bytes means the record is incomplete; `readFully` actively throws an exception instead of returning a short dataset.

### Catch the Right Class at the Right Scope

```java
try {
    input.readFully(record);
    processCompleteRecord(record);
} catch (EOFException truncated) {
    throw new IOException(
            "Record bị cắt trước khi đủ " + record.length + " byte",
            truncated);
}
```

This is an illustrative snippet requiring `input` (of type `DataInputStream`), `record` (a byte array), and `processCompleteRecord`. Wrapping the exception informs the caller that a specific record is incomplete while preserving the underlying reason via `cause`.

If this is a multi-record protocol, **do not continue reading the next record after an EOFException as if the previous record succeeded**. The connection ended before completing a frame; typically you must treat the frame as failed and stop reading/close or report an error.

### Clean EOF at a Record Boundary vs. a Truncated Record

Suppose a protocol has a 4-byte header containing a length. When `readInt()` encounters `EOFException`, there are two possibilities:

- **Clean EOF:** zero bytes of the new header were present, meaning the stream ended right at a record boundary.
- **Truncated header:** 1–3 bytes of the header were present before ending—malformed data.

Merely catching `EOFException` from `readInt()` **does not provide enough information to distinguish** the two cases, because both throw the same exception type. To distinguish them, the protocol/decoder must track boundaries explicitly, or read the first header byte separately and then require all 3 remaining bytes. Never assume every `EOFException` from `readInt` means "clean end of file".

Example custom logic for a stream of records with 4-byte headers:

```java
int first = input.read();

if (first == -1) {
    // EOF before the first header byte: clean end of stream at record boundary.
    return;
}

byte[] restOfHeader = new byte[3];
input.readFully(restOfHeader); // Missing 1-3 bytes: truncated header error.

// Assemble header per protocol standard (big-endian) if needed.
int length = ((first & 0xFF) << 24)
        | ((restOfHeader[0] & 0xFF) << 16)
        | ((restOfHeader[1] & 0xFF) << 8)
        | (restOfHeader[2] & 0xFF);
```

This is an **illustrative snippet** placed inside a method allowed to `return`, with `input` as a `DataInputStream`. The example header format uses a 32-bit big-endian integer like `DataInputStream.readInt()`. You still must **validate `length`** against protocol limits before allocating a buffer; if payload bytes are missing, `readFully` will throw `EOFException`.

## 6. Using Offset and Length

`readFully(buffer, off, len)` only requires filling the slice `[off, off + len)`. For example, with a 12-byte array, to read 4 bytes of data starting at index 5:

```java
byte[] frame = new byte[12];
input.readFully(frame, 5, 4);
```

The method requires 4 new bytes for indices `5, 6, 7, 8`. If it succeeds, bytes outside the specified range are not new data from this call.

When manually inspecting read data, do not mistake `len` for an *end index*: `off=5, len=4` means four bytes starting at index 5, not the range from 5 to 4.

With `read(buffer, off, len)`, the method returns `n` bytes just read within that slice; to fill a slice via a manual read loop, advance the offset by `n`, **not by `len`**.

## 7. Without `readFully`, How Do You Manually Read Exactly N Bytes?

When you only have an `InputStream`, you can write a helper to read the exact requested number of bytes. The example below works with any `InputStream` conforming to the standard contract for positive-length buffers:

```java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;

static void readExactly(InputStream input, byte[] buffer)
        throws IOException {
    int offset = 0;

    while (offset < buffer.length) {
        int n = input.read(
                buffer, offset, buffer.length - offset);

        if (n == -1) {
            throw new EOFException(
                    "Unexpected EOF after " + offset +
                    " of " + buffer.length + " bytes");
        }

        offset += n;
    }
}
```

This is an illustrative method that must be placed inside a class. `offset` advances solely by **the actual bytes read `n`**. Once the buffer is full, the method returns. If EOF occurs before filling, it throws `EOFException`.

In practice, `DataInputStream.readFully` already provides this capability when exact N-byte reads are needed. Do not rewrite it just to "optimize" when the standard API already fits.

With custom I/O sources that might repeatedly return `0` even when a positive byte count is requested (violating the `InputStream` contract), an unguarded custom loop risks spinning forever; handle according to the source's specific contract. The learning code above relies on the standard contract.

## 8. Comparison with `InputStream.readNBytes` and `readAllBytes`

Since Java 9, `InputStream` includes convenient APIs:

| API | Behavior when EOF occurs before desired count |
| --- | --- |
| `readNBytes(int len)` | Returns a `byte[]` that may be **shorter than `len`**; caller checks length |
| `readNBytes(byte[] b, int off, int len)` | Returns actual bytes read, which may be **less than `len`** |
| `readAllBytes()` | Reads all remaining bytes until EOF; cannot guarantee an N-byte structure without checking |
| `DataInputStream.readFully(byte[] b)` | **Throws `EOFException`** if fewer than `b.length` bytes are available |

If you want a "strictly require N bytes" policy, you can still use `readNBytes` and check:

```java
byte[] bytes = input.readNBytes(expectedLength);
if (bytes.length != expectedLength) {
    throw new EOFException("Expected " + expectedLength
            + " bytes, got " + bytes.length);
}
```

This illustrative snippet assumes `input` is an `InputStream`, `expectedLength` is a non-negative integer that has **passed bounds validation**, and `EOFException` is imported. The difference is that `readNBytes` **does not automatically throw on short EOF like `readFully`**, leaving the programmer to verify the length.

**Do not use `available()` as the remaining byte count of a file/network stream**: `available()` only gives an estimate of bytes readable immediately without blocking in some situations, not a message size or an exact termination condition.

## 9. Applying to Files and Length-Declared Protocols

Common problem: the start of each frame contains the **payload length**, followed by that exact number of payload bytes. Once the header is read and validated, typical logic is:

```java
int payloadSize = input.readInt();

if (payloadSize < 0 || payloadSize > MAX_PAYLOAD_BYTES) {
    throw new IOException("Payload length out of bounds");
}

byte[] payload = new byte[payloadSize];
input.readFully(payload); // Missing bytes => EOFException.
handlePayload(payload);
```

This is a non-standalone illustrative snippet: `input` is a `DataInputStream`, `MAX_PAYLOAD_BYTES` is a trusted limit, and `handlePayload` is an application method.

**You must validate the length before allocating.** External data can declare a negative, huge, or intentionally bogus number. Never allocate `new byte[untrustedLength]` first and check afterward, as that can cause memory errors. Beyond maximum size, network applications also need timeouts, total-bytes-allowed policies, and dead/slow connection handling.

Safe structured binary reading steps are typically:

1. Determine the stream state and current record boundary.
2. Read the complete header per format; distinguish a clean boundary EOF from a truncated header.
3. Decode and **validate the length value**.
4. Allocate within validated bounds, or process in chunks if payloads are too large for RAM.
5. `readFully` the exact payload byte count; if EOF occurs early, report a truncated frame.
6. Decode or process **only a complete payload**.

Do not treat a successful `readFully` as full validation of the payload's contents. Data may have enough bytes yet contain an invalid magic number, checksum, UTF-8 content, structure, or business rule violation; those validation checks are still required.

## 10. Common Mistakes

| Wrong Practice | Consequence | Resolution |
| --- | --- | --- |
| Calling `read(buffer)` once then parsing N bytes | Data may only be partially received | Loop until full or use `readFully` |
| Stopping when `bytesRead < buffer.length` | A short read does not mean EOF | End normal stream reading only on `-1` |
| Calling `write(buffer)` after a short read | Writes unfilled/stale bytes too | `write(buffer, 0, bytesRead)` |
| Catching `EOFException` then parsing buffer as complete | Buffer may be partially filled | Discard incomplete record; report error |
| Catching `EOFException` on `readInt` as clean end every time | Cannot tell boundary EOF from truncated header | Track header bytes or design clear framing |
| Thinking `readFully` returns a byte count | Method returns `void` | Success means the full byte count was read |
| Using `available()` to decide if N bytes are ready | Does not accurately reflect remaining bytes | Rely on protocol contract and `readFully` |
| Allocating directly from an unvalidated length | Memory risk, denial of service | Validate bounds before allocating |
| Using `readAllBytes()` on unbounded/huge inputs | Can consume excessive RAM | Bound data, read with control |
| Ignoring frame EOF when a socket closes | Treats incomplete message as success | Report truncated frame and stop processing |

## 11. Self-Check

1. `byte[] b = new byte[10]`, calling `read(b)` returns `3`. May you parse all 10 bytes? **No**; only 3 bytes are valid.
2. `readFully(b)` needs 10 bytes, but only 7 remain in the stream. What happens? **Throws `EOFException`**; it does not return 7, and the buffer must not be used as a complete record.
3. Which indices does `readFully(b, 4, 3)` read into? **4, 5, 6**.
4. Does `readFully(b, 0, 0)` at EOF throw `EOFException`? **No**, because 0 bytes are requested.
5. Does `readNBytes(10)` encountering EOF after 7 bytes always throw `EOFException`? **No**; it normally returns a 7-byte array, and the programmer checks length if 10 bytes are mandatory.
6. `readInt()` throws `EOFException`. Can you be certain it was a "clean end of records"? **No**; the header could be missing 1–3 bytes.
7. A file's 4-byte header declares a 2 GB payload while the application only permits 1 MB. What should you do? **Reject the length before creating `byte[]`**.
8. Does `readFully` receiving the full payload mean the content is completely valid? **No**; you still need to validate format, checksums, and data rules.

**Takeaway:** `read` returns **how many bytes were actually received right now**; `readFully` demands **exactly N bytes or throws `EOFException`**. Decode a structure only after reading it completely, and treat EOF in the middle of a required record as **truncated data**, not a successful record.
