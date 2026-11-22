# Java I/O: Testing Empty Files, Large Files, Early EOF, and Incomplete Records

## 1. Why Test Boundary Cases?

File reading/writing code may pass on a small, complete file, yet break when data is shorter than expected or exceeds memory limits. These bugs commonly surface during file uploads, log processing, binary record parsing, file transfers, crash recovery, or reading files written concurrently by another application.

Representative cases:

- A **0-byte** file has no header, yet the format requires a header.
- A header declares a **0-byte** payload, which may be a **valid record**.
- A `read(...)` call returns fewer bytes than the buffer requested, without being EOF.
- EOF occurs when only 1–3 header bytes have arrived, or mid-payload.
- A multi-GiB file causes code to cast `long` to `int` and allocate an array.
- A length prefix is negative or huge; allocating immediately triggers `NegativeArraySizeException`/`OutOfMemoryError`.
- A reader opens a file while a writer is appending/truncating; `Files.size(...)` no longer reflects a stable snapshot.
- A writer crashes mid-record, leaving a valid header with only a partially written payload.
- Code confuses `read() == 0` with `read() == -1`, or calls `ByteBuffer.getInt()` before four bytes arrive.
- A record has enough bytes yet corrupted content; size checks alone fail to catch it.

This lesson defines a simple contract to explain these scenarios, paired with a Java 17+ program that generates fixtures and verifies **which cases must succeed and which must fail**.

## 2. Example Binary Format and EOF Rules

Assume a file contains **exactly one record**:

~~~text
+----------------------------+--------------------------+
| Header: 4 bytes, big-endian| Payload: length bytes    |
| int length >= 0            | may be empty if length=0 |
+----------------------------+--------------------------+
   file offsets [0,4)             file offsets [4,4+N)
~~~

Examples:
- `00 00 00 02 4F 4B`: 2-byte payload, ASCII content `OK`.
- `00 00 00 00`: **a complete record** containing an empty payload.
- 0-byte file: **no record**, an error if the format mandates one record.
- `00 00`: **truncated header**, since only 2/4 bytes exist.
- `00 00 00 05 41 42`: header declares 5 payload bytes, only 2 exist; **incomplete record**.

Distinguish **valid EOF at a boundary** from **early EOF mid-record**:

~~~text
Multi-record:
  [record #1 complete][record #2 complete][EOF]
    -> Valid termination if the format allows multiple records.

  [record #1 complete][2/4 bytes header #2][EOF]
    -> TRUNCATED_HEADER.

  [record #1 complete][header #2 says 5][2 payload bytes][EOF]
    -> TRUNCATED_PAYLOAD.
~~~

The demo program's policy is a **single-record file**, so any byte after the payload is a `TRAILING_BYTES` error. A multi-record parser differs: it continues looking for the next header and treats EOF as normal only when zero bytes of the next header have been read.

## 3. EOF, Short Reads, and Returning 0 Are Not the Same

### InputStream

`InputStream.read()` returns:
- `0..255` when one byte is read.
- `-1` at end-of-stream.

`InputStream.read(byte[], off, len)` returns the number of bytes read, which can be **less than `len`**. When `len == 0`, it may return `0` immediately. Never assume a single `read` call fills the full length.

`InputStream.readNBytes(int n)` may return an array **shorter than `n`** if EOF arrives first. If you require exactly `n` bytes, check the actual returned array/count. `DataInputStream.readFully(byte[])` attempts to read all bytes or throws `EOFException` if insufficient.

~~~java
// Illustration: in is a DataInputStream, expected is validated.
if (expected < 0 || expected > MAX_RECORD_BYTES) {
    throw new IOException("Invalid length");
}
byte[] payload = new byte[expected];
in.readFully(payload); // Missing payload => EOFException.
~~~

This snippet is not standalone because `expected`, `MAX_RECORD_BYTES`, and `in` must be defined. Never pass an unvalidated length prefix to `readFully`, because the array is allocated before the call.

### FileChannel and ByteBuffer

`FileChannel.read(ByteBuffer dst)` returns:
- A positive value when `n` bytes are read, advancing `dst.position()`.
- `-1` at EOF.
- `0` when no bytes were read on that call; on a normal file with buffer space remaining, this is not an EOF signal.

~~~java
int n = channel.read(buffer);
if (n < 0) {
    // EOF.
} else if (n == 0) {
    // No progress yet.
} else {
    // n new bytes loaded, position increased by n.
}
~~~

**Do not turn `0` into `-1`**. On a `SocketChannel` in non-blocking mode, `0` is routine; wait via `Selector`/readiness instead of spinning. With `FileChannel`, test code may fail explicitly if looping with no progress to avoid infinite hangs.

### Read-exactly is a loop, not a single read

~~~java
// Illustration: FileChannel is open, dst is allocated.
static int readUpTo(FileChannel channel, ByteBuffer dst)
        throws IOException {
    int total = 0;
    while (dst.hasRemaining()) {
        int n = channel.read(dst);
        if (n == -1) {
            break;
        }
        if (n == 0) {
            throw new IOException("no read progress");
        }
        total += n;
    }
    return total;
}
~~~

The method returns the actual byte count received. The caller knows the expected length and classifies the result:
- Header needs 4, gets 0 on first read ⇒ `EMPTY_FILE` or normal EOF depending on contract.
- Header needs 4, gets 1–3 then EOF ⇒ `TRUNCATED_HEADER`.
- Payload needs `N`, gets `k < N` then EOF ⇒ `TRUNCATED_PAYLOAD`.

## 4. `ByteBuffer`: `position`, `limit`, and `flip`

A common bug:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
channel.read(header);
int length = header.getInt(); // Wrong: didn't verify byte count, didn't flip.
~~~

When reading into a `ByteBuffer`, `position()` advances toward the end. You must verify enough bytes arrived and call `flip()` to switch to read mode:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
int actual = readUpTo(channel, header);
if (actual != 4) {
    throw new EOFException("incomplete header: " + actual + "/4");
}
header.flip();
int length = header.getInt();
~~~

In a multi-record parser, `compact()` preserves unparsed trailing bytes after a read pass, whereas `clear()` treats the remaining data region as no longer needed. Mistakenly calling `clear()` when the buffer already holds half of the next record's header loses data even when the file is intact.

## 5. Validate Length Before Allocating

A binary header can contain negative or huge numbers. Do not write:

~~~java
int length = header.getInt();
byte[] bytes = new byte[length]; // Unbounded, unsafe.
~~~

Replace with:

~~~java
int length = header.getInt();
if (length < 0 || length > MAX_RECORD_BYTES) {
    throw new IOException("invalid record length: " + length);
}
byte[] bytes = new byte[length];
~~~

`MAX_RECORD_BYTES` is an **application protocol and memory limit**, not a standard Java constant. The demo sets `MAX=1024` to keep fixtures readable; real services define it based on workload and quotas.

Critical conditions:
- `length == 0` can be a valid empty payload, **distinct from an empty file**.
- `length < 0` must be rejected if the format uses signed nonnegative ints.
- `length > MAX` must be rejected **before** allocation.
- When adding offsets/lengths, compute in `long` to prevent `int` overflow.
- If a parser supports unsigned 32-bit lengths, specify it explicitly via `Integer.toUnsignedLong(length)` and check bounds first; **never assume signed and unsigned are equivalent**.
- Never report success just because the header is valid; still verify complete payload and any checksum.

## 6. Empty Files and Empty Payloads: Minimum Test Set

| Fixture | File Size | Result Under Single-Record Contract |
|---|---:|---|
| Completely empty file | 0 | `EMPTY_FILE` |
| Header length 0 | 4 | `COMPLETE`, empty payload |
| Header length 0, plus 1 byte | 5 | `TRAILING_BYTES` |
| Header with only byte `00` | 1 | `TRUNCATED_HEADER(1/4)` |
| 3-byte header | 3 | `TRUNCATED_HEADER(3/4)` |
| Header length 1 + one byte | 5 | `COMPLETE` |
| Header length 1 + no payload | 4 | `TRUNCATED_PAYLOAD(0/1)` |

These test **format** boundaries, not `Files` API bugs. `Files.createTempFile` creates a valid empty file at the filesystem layer; the parser decides whether an empty file is acceptable.

Never write `catch(EOFException e) { return new byte[0]; }` because that hides truncated records and makes a valid empty payload indistinguishable from corrupted data.

## 7. Large Files and Data-Type Overflow Risks

A 3 GiB file is larger than `Integer.MAX_VALUE`. In Java:

- `Files.size(path)` returns `long`.
- `FileChannel.size()` returns `long`.
- `FileChannel.position(long)` and `read(dst, long offset)` handle `long` offsets.
- `ByteBuffer.allocate(int capacity)` is bounded by `int` and available memory.
- `Files.readAllBytes(path)` has array/memory limits and is unsuitable for huge files.

Wrong:

~~~java
int size = (int) Files.size(path);
byte[] all = new byte[size];
~~~

Casting can yield a negative value or truncated size. Even below 2 GiB, allocating one giant array risks OOM.

Better—stream in blocks:

~~~java
long total = 0L;
byte[] buffer = new byte[16 * 1024];

try (InputStream in = Files.newInputStream(path)) {
    int n;
    while ((n = in.read(buffer)) != -1) {
        if (n == 0) {
            throw new IOException("no stream progress");
        }
        total += n;
        // Process/hash/forward each chunk here.
    }
}
~~~

The buffer stays around 16 KiB whether the file is 5 MiB or many GiB, excluding parser state. If the file or stream is untrusted, enforce a **total byte quota** and deadline, not just per-chunk limits.

### Sparse files and tests exceeding 2 GiB

Some filesystems support sparse files: a large logical size without allocating every disk block. Testing with `RandomAccessFile.setLength(long)` or writing at very high offsets can verify `long`-offset logic, but:
- Not all providers support sparse files identically.
- A large logical file size does not prove streaming code handles actual full-data throughput.
- Never create multi-GiB fixtures recklessly on CI or production volumes.
- Write dedicated tests for `long` offsets and separate tests for streaming/throughput data.

## 8. Complete Java 17+ Program: Eight Boundary Cases

The following program creates fixtures in a temporary directory, reads a **single record** formatted as `[int32 length][payload]`, and prints deterministic output.

Cases include: empty file, empty payload, complete record, truncated header, truncated payload, oversized length, trailing data, and a 5 MiB file read via streaming.

Save as **`IoBoundaryCasesDemo.java`**:

~~~java
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.Arrays;
import java.util.stream.Stream;

public class IoBoundaryCasesDemo {
    private static final int MAX_RECORD_BYTES = 1024;

    private static int readUpTo(FileChannel ch, ByteBuffer dst)
            throws IOException {
        int total = 0;
        while (dst.hasRemaining()) {
            int n = ch.read(dst);
            if (n < 0) {
                break; // EOF.
            }
            if (n == 0) {
                throw new IOException("no read progress");
            }
            total += n;
        }
        return total;
    }

    private static byte[] readOneRecord(Path file)
            throws IOException {
        try (FileChannel ch = FileChannel.open(
                file, StandardOpenOption.READ)) {

            ByteBuffer header = ByteBuffer.allocate(4);
            int headerCount = readUpTo(ch, header);

            if (headerCount == 0) {
                throw new EOFException("empty file");
            }
            if (headerCount < 4) {
                throw new EOFException(
                        "incomplete header: " + headerCount + "/4");
            }

            header.flip();
            int length = header.getInt();

            if (length < 0 || length > MAX_RECORD_BYTES) {
                throw new IOException(
                        "invalid record length: " + length);
            }

            byte[] payload = new byte[length];
            int payloadCount = readUpTo(
                    ch, ByteBuffer.wrap(payload));

            if (payloadCount < length) {
                throw new EOFException(
                        "incomplete payload: "
                        + payloadCount + "/" + length);
            }

            // Per contract, the file contains only one record.
            if (ch.read(ByteBuffer.allocate(1)) != -1) {
                throw new IOException("unexpected trailing bytes");
            }

            return payload;
        }
    }

    private static byte[] framed(byte[] payload) {
        return ByteBuffer.allocate(4 + payload.length)
                .putInt(payload.length)
                .put(payload)
                .array();
    }

    private static void testCase(
            Path dir, String label, byte[] input)
            throws IOException {

        Path file = Files.createTempFile(dir, "case-", ".bin");
        Files.write(file, input);

        try {
            byte[] value = readOneRecord(file);
            System.out.println(label + ": ok="
                    + new String(value, StandardCharsets.US_ASCII));
        } catch (IOException ex) {
            System.out.println(label + ": error="
                    + ex.getMessage());
        }
    }

    private static long largeStreamingCase(Path dir)
            throws IOException {
        Path file = Files.createTempFile(dir, "large-", ".bin");
        byte[] writeBuffer = new byte[8192];
        Arrays.fill(writeBuffer, (byte) 'x');

        try (OutputStream out = Files.newOutputStream(file)) {
            for (int i = 0; i < 640; i++) {
                out.write(writeBuffer);
            }
        }

        byte[] readBuffer = new byte[16 * 1024];
        long total = 0L;
        try (InputStream in = Files.newInputStream(file)) {
            int n;
            while ((n = in.read(readBuffer)) != -1) {
                if (n == 0) {
                    throw new IOException("no stream progress");
                }
                total += n;
            }
        }
        return total;
    }

    public static void main(String[] args)
            throws IOException {
        Path dir = Files.createTempDirectory("io-boundary-");

        try {
            testCase(dir, "empty-file", new byte[0]);
            testCase(dir, "empty-payload",
                    framed(new byte[0]));
            testCase(dir, "complete", framed(
                    "OK".getBytes(StandardCharsets.US_ASCII)));

            testCase(dir, "short-header",
                    new byte[] {0, 0});

            testCase(dir, "short-payload",
                    ByteBuffer.allocate(6)
                            .putInt(5)
                            .put((byte) 'A')
                            .put((byte) 'B')
                            .array());

            testCase(dir, "too-large",
                    ByteBuffer.allocate(4)
                            .putInt(MAX_RECORD_BYTES + 1)
                            .array());

            testCase(dir, "trailing",
                    ByteBuffer.allocate(6)
                            .putInt(1)
                            .put((byte) 'Q')
                            .put((byte) '!')
                            .array());

            System.out.println("large-file: bytes="
                    + largeStreamingCase(dir));
        } finally {
            // Directory contains only fixtures created by this demo.
            try (Stream<Path> entries = Files.list(dir)) {
                for (Path p : entries.toList()) {
                    Files.deleteIfExists(p);
                }
            }
            Files.deleteIfExists(dir);
        }
    }
}
~~~

Compile/run:

~~~bash
javac IoBoundaryCasesDemo.java
java IoBoundaryCasesDemo
~~~

**Expected stdout when temporary file operations succeed:**

~~~text
empty-file: error=empty file
empty-payload: ok=
complete: ok=OK
short-header: error=incomplete header: 2/4
short-payload: error=incomplete payload: 2/5
too-large: error=invalid record length: 1025
trailing: error=unexpected trailing bytes
large-file: bytes=5242880
~~~

### Explaining the output and correctness

1. `empty-file`: 0/4 header bytes. Under a single-record contract, cannot be considered a valid record.
2. `empty-payload`: full 4-byte header, `length=0`, payload is an empty array; output shows `ok=` with no characters.
3. `complete`: 4-byte header and two `OK` bytes, reading to EOF past the payload.
4. `short-header`: only 2 bytes; parser reports `2/4` instead of calling `getInt` prematurely.
5. `short-payload`: header declares 5 bytes, only two bytes `A`/`B` exist; parser reports `2/5`.
6. `too-large`: `length=1025` exceeds `MAX=1024`; rejected **before allocation**.
7. `trailing`: `length=1` consumes `Q`, and the extra `!` byte violates the single-record contract.
8. `large-file`: 640 writes of 8,192-byte blocks = **5,242,880 bytes**, read with a 16 KiB buffer without allocating an array sized to the file.

The program intentionally uses a normal `FileChannel`, not a non-blocking `SocketChannel`. On a non-blocking socket, `read() == 0` is normal and should return to the event loop instead of throwing `IOException` as the demo helper does.

Demo data uses only ASCII and a fixed big-endian header so stdout does not depend on OS locale/charset. The temporary directory and files are cleaned up on both normal exit and standard exceptions; JVM crash/kill can still leave fixtures behind, as with any `finally`-based cleanup.

## 9. Reading a File Containing Multiple Records

If a file holds sequential records, we cannot reuse `readOneRecord` because it forbids trailing bytes. Instead:

~~~text
LOOP:
   read 4-byte header
      - 0 bytes then EOF    -> END_OF_STREAM (normal)
      - 1..3 bytes then EOF -> TRUNCATED_HEADER (error)
      - full 4 bytes        -> validate length
   read length bytes of payload
      - short then EOF      -> TRUNCATED_PAYLOAD (error)
      - complete            -> COMPLETE(frame), process record
   jump to LOOP
~~~

Use explicit result types or error codes:
`END_OF_STREAM_AT_BOUNDARY`, `TRUNCATED_HEADER`, `INVALID_LENGTH`, `TRUNCATED_PAYLOAD`, `CHECKSUM_MISMATCH`, and `IO_FAILURE`.

If it is an append-only log, EOF at the tail needs context: a writer might **still be writing**, unlike a committed snapshot file that is truncated. Recovery may discard an uncommitted tail **only if the log protocol is designed for it**—never silently truncate every file that hits EOF.

## 10. Partial Writes and Mid-Record Truncation

Incomplete records often originate on the write side:

~~~java
// Illustrative code: FileChannel opened for WRITE, buffer prepared.
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n <= 0) {
        throw new IOException("no write progress");
    }
}
~~~

A single `write` is not guaranteed to drain the whole buffer. If a writer writes a header with `length=100` and only 60 payload bytes before crashing, the reader hits EOF at `60/100`. Never turn that error into a "valid short" record.

A complete file publishing pattern typically looks like:

1. Create a temporary file on the target filesystem.
2. Write all data, handling partial writes.
3. Verify length, checksum, and content format.
4. Explicitly call `channel.force(...)` if durability is required under the storage contract.
5. Close the writer.
6. Publish via `Files.move(temp, target, ATOMIC_MOVE)` where supported.
7. Readers must still validate record boundaries and checksums.

`ATOMIC_MOVE` **does not by itself guarantee crash durability**, nor is it a multi-file transaction. On network filesystems, also account for server consistency and durability guarantees.

## 11. Checksums: Having Enough Bytes Does Not Guarantee Valid Content

A record with a complete header and payload can still pass all length checks if a single byte is corrupted.

~~~text
Expected: length=4, payload=01 02 03 04
Actual:   length=4, payload=01 02 03 05
Both have file size=8, yet contents differ.
~~~

Common approaches:
- **CRC32/CRC32C** to detect common accidental data corruption.
- **SHA-256** when a strong hash is needed to verify specific content.
- **HMAC/digital signatures** when defending against tampering where an attacker can modify both the file and its checksum.

The parser order should be: verify magic/version if present → read full header → validate length → read full payload → verify checksum/schema → accept record. Never feed data into business logic before verifying required invariants.

## 12. Deliberately Testing Short Reads

A local `FileChannel` may happen to fill a buffer in one call, hiding "single-read-only" bugs. Use a wrapper returning at most 2 bytes per read:

~~~java
// Illustrative code: source is an InputStream, add required imports.
InputStream shortReads = new FilterInputStream(source) {
    @Override
    public int read(byte[] dst, int off, int len)
            throws IOException {
        return super.read(dst, off, Math.min(len, 2));
    }
};
~~~

For a frame with a 4-byte header and 5-byte body, the wrapper splits reads into `2+2+2+2+1` bytes; a correct parser must still reconstruct it intact.

**Short reads differ from early EOF:** a short read is followed by remaining bytes in subsequent calls; early EOF returns `-1` before required bytes arrive. Negative tests are needed for both behaviors.

A wrapper returning `0` repeatedly (when the caller requests a positive length) can trigger a busy loop in a poorly written parser. Tests need finite timeouts to catch non-progress loops.

## 13. File Size Is Not a Snapshot

Example:

~~~java
long observed = Files.size(path);
try (InputStream in = Files.newInputStream(path)) {
    // File may be truncated or appended after size().
}
~~~

Never treat `Files.size() == expected` as proof that the file stays unchanged once reading begins. Another writer can modify, truncate, or replace the path, causing the reader to hit early EOF. Depending on the use case:

- Publish immutable files only after completion.
- Use file locking/coordination when multiple processes require access.
- Use filesystem snapshots or transactional storage when true snapshots are needed.
- For tailers, maintain parser state and a wait/timeout policy for records currently being written.

This matters even more when files are shared over network filesystems with separate caching/visibility semantics; an accurate `read` only guarantees reading the bytes **the system supplies**, not a system-wide storage snapshot.

## 14. Exception Diagnostic Table

| Symptom | Likely Cause | What to Check |
|---|---|---|
| `EOFException` during header | 0–3 byte file or EOF at boundary depending on format | Header bytes received |
| `EOFException` during payload | Valid length but truncated body | Declared vs actual |
| `BufferUnderflowException` | Buffer lacks data or was not flipped | `position`/`limit`/`remaining` |
| `NegativeArraySizeException` | Negative length passed directly | Validate before allocating |
| `OutOfMemoryError` | Loading huge file into one array | Streaming, limits |
| `IOException` on `read()==0` | No progress, file-specific helper | Blocking mode/provider |
| `ClosedChannelException` | Channel closed mid-use | Resource ownership |
| `NonReadableChannelException` | Channel opened without `READ` | `OpenOption` |
| `AccessDeniedException` | File permissions/ACLs | Filesystem permissions |
| `NoSuchFileException` | File deleted or path replaced | Concurrent operations |
| `FileSystemException` | Storage/mount/file-busy error | Cause, platform diagnostics |
| Corrupted decoded data | Charset/byte-order/framing mismatch | Big-endian/UTF-8 and parser |
| Right byte count, wrong content | Corruption/overwrite/race | Checksum, concurrency |
| Parser hangs at high CPU | `read()==0` loop with no exit | Readiness/backoff/timeout |

Never catch `IOException` and return an empty payload as success. Read failures must stay distinct from a genuine zero-length payload.

## 15. Logging and Instrumentation to Reproduce Failures

Diagnostic logs should include (without logging sensitive content):

- Request ID or job ID.
- Operation name: open, read-header, read-payload, verify, write, close.
- Record offset in the file (`long`), bytes received, and bytes expected.
- Length prefix, max limit, observed file size.
- Exception class and cause, channel/EOF state.
- Retry count, deadline if reading from an asynchronous source.
- Checksum/version status and cleanup performed.

Example log message:

~~~text
job=42 op=read-payload offset=4 declared=100
received=60 status=TRUNCATED_PAYLOAD
~~~

Prefer **structured error codes** such as `EMPTY_FILE`, `TRUNCATED_HEADER`, `TRUNCATED_PAYLOAD`, `INVALID_LENGTH`, `TRAILING_BYTES`, and `CHECKSUM_MISMATCH` rather than having business logic parse exception messages.

## 16. Recommended Test Matrix

| Test | Input | Expected Outcome |
|---|---|---|
| Empty file | 0 bytes | `EMPTY_FILE` if 1 record required |
| Empty payload | Header `N=0`, no body | `COMPLETE` |
| 1-byte header | EOF | `TRUNCATED_HEADER` 1/4 |
| 2-byte header | EOF | `TRUNCATED_HEADER` 2/4 |
| 3-byte header | EOF | `TRUNCATED_HEADER` 3/4 |
| Payload short 1 byte | `N-1`/`N` | `TRUNCATED_PAYLOAD` |
| Payload missing completely | `0`/`N` with `N>0` | `TRUNCATED_PAYLOAD` |
| Negative length | `-1` | `INVALID_LENGTH` |
| Length at `MAX` | Complete bytes | `COMPLETE` |
| Length `MAX+1` | Header over limit | `INVALID_LENGTH`, no allocation |
| Trailing garbage | Extra bytes after record | `TRAILING_BYTES` |
| Partial read | 1–2 byte/turn wrapper | `COMPLETE` if all bytes arrive |
| Repeated read 0 | Simulated custom channel | No infinite spin |
| 5 MiB file | Stream chunks | Accurate count, low heap |
| Long offset >2 GiB | Sparse fixture | No `int` cast |
| Checksum mismatch | Full body with flipped byte | `REJECT` |
| Writer crash mid-payload | Incomplete tail record | Explicit recovery policy |
| Concurrent truncate | File changed while reader open | Does not report false complete |
| Permission error | File cannot be opened | Reports I/O error |
| Disk full on write | Partial write | Does not publish file |
| EOF cleanly between records | No next header | `END_OF_STREAM` |
| EOF mid-next-header | 1–3 bytes | `TRUNCATED_HEADER` |

Generating fixtures from byte arrays or isolated temporary files keeps results reproducible without relying on files outside the repo. With JUnit 5, `@TempDir` provides an isolated workspace per test; still verify cleanup and resource closing.

## 17. Property-Based Testing and Invariant Checks

Properties to prove for a length-prefixed codec:

~~~text
decode(encode(payload)) == payload
    for 0 <= payload.length <= MAX.

Truncate encoded stream before 4 bytes:
    TRUNCATED_HEADER or EMPTY_FILE.

Truncate encoded stream after header before full payload:
    TRUNCATED_PAYLOAD.

Replace declared length with negative or >MAX value:
    INVALID_LENGTH before allocation.

Append any byte to a complete record:
    TRAILING_BYTES when contract allows only one record.
~~~

This is a **pseudo-spec**, not Java syntax. Test boundary values `0`, `1`, `MAX`, `MAX+1`, `Integer.MAX_VALUE`, negative values, and multi-byte UTF-8 data (where byte length differs from character count).

If a parser handles UTF-8 strings, length prefixes should usually count **encoded bytes**, not Java `String.length()` character counts; Vietnamese characters can span multiple bytes.

## 18. Performance and Safety of Large-File Readers

1. Read in fixed-size blocks; never allocate the entire file.
2. Use `long` for total bytes and offsets.
3. Enforce quotas on total bytes and record counts.
4. Never loop unboundedly when `read` returns `0`.
5. Limit open file descriptors and pending I/O operations.
6. Monitor memory across the entire application, not just a single `ByteBuffer`.
7. For non-blocking sockets, use a `Selector` and keep state across events.
8. Never use a single `MappedByteBuffer` to map a file exceeding `int` capacity; map in regions if needed.
9. Apply distinct timeout/retry policies for transient I/O errors vs malformed data.
10. Never treat atomic rename or `force()` as a substitute for verifying headers, payloads, and checksums.

## 19. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| 0-byte file equals length-0 payload | 0-byte file lacks a header; length-0 payload has a valid header |
| One read fills the buffer | Reads can be partial |
| Read 0 means EOF | EOF is `-1` |
| Valid header means full payload exists | Writer may crash before finishing the body |
| File size returns `int` | Java returns `long` |
| Casting `long` to `int` is always safe | Can overflow |
| `readNBytes` always returns enough | Can be short at EOF |
| `readFully` returns fewer bytes silently | It throws `EOFException` when short |
| Buffer `getInt` works right after read | Must check byte count and `flip` |
| EOF mid-record is normal termination | It is a truncated record |
| EOF at multi-record boundary is an error | It can be normal termination |
| Length in file is trustworthy | Validate negative/max before allocating |
| Right file size means checksum is valid | Size does not verify content |
| Calling `write` once is enough | Must check and loop while `hasRemaining` |
| `Files.size` is a fixed snapshot | File can change after measurement |
| Local file unit tests catch all short reads | Use a wrapper forcing partial reads |
| Catching an exception means parser succeeded | Must reflect the actual error state |

## 20. Self-Check Questions

1. 0-byte file, single record with 4-byte header required: outcome? **`EMPTY_FILE`**.
2. File containing four `0` bytes: outcome? **Valid record with empty payload**.
3. Header only 3/4 bytes then EOF: **`TRUNCATED_HEADER`**.
4. Header length 9, received 7 body bytes then EOF: **`TRUNCATED_PAYLOAD 7/9`**.
5. `FileChannel.read` returns 2 when `remaining=4`: **keep reading**, not EOF.
6. Is `read() == 0` EOF? **No**, EOF is `-1`.
7. Should negative length be handled before or after allocation? **Before**.
8. Can a 3 GiB file's `long` size be cast to `int`? **No**.
9. What does `DataInputStream.readFully` do when bytes are missing? **Throws `EOFException`**.
10. What does `InputStream.readNBytes(100)` return at EOF after 40 bytes? **A 40-byte array**.
11. Does a valid header length prove a complete record? **No**.
12. Does an expected file size guarantee valid content? **No**, verify checksum/schema.
13. Should parsers be tested only with complete files? **No**, test partial reads and early EOF.
14. What if a multi-record parser hits EOF before the first byte of the next header? **It can terminate validly**.
15. How can EOF mid-payload in a newly written log be handled? **Per recovery protocol; do not blindly mark complete or truncate**.
16. Why stream large files? **Reduces memory footprint and avoids file-size allocations**.
17. Why clean up temporary fixtures even when tests fail? **Prevents resource leaks and interference with subsequent tests**.

## 21. Official Java SE 17 Documentation

- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): read/write, size, position, and long offsets.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): position/limit/flip/getInt/compact and byte order.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): read, readNBytes, and EOF.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): readFully, readInt, and EOFException.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): size, newInputStream, readAllBytes, temp files.
- [EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): unexpected end-of-file in binary data.
- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking reads, zero reads, and partial I/O.
