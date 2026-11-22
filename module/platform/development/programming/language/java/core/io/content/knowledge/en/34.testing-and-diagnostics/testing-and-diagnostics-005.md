# Java I/O: Testing Empty Files, Large Files, Premature EOF, and Incomplete Records

## 1. Why Test Boundary Cases?

File read/write code may work on a small, complete file yet fail when data is smaller than expected or exceeds memory limits. These bugs commonly surface during file uploads, log processing, reading binary records, file transfers, crash recovery, or reading files being written concurrently by another application.

Typical scenarios:

- A **0-byte** file has no header, yet the format requires one.
- A header indicates a **0-byte** payload, which may be **a valid record**.
- A single `read(...)` call returns fewer bytes than the buffer requested, without being EOF.
- EOF occurs when only 1–3 bytes of a header have arrived, or while the payload is incomplete.
- A multi-GiB file causes code to cast `long` to `int` and allocate a single array.
- A length prefix is negative or huge; allocating immediately can trigger `NegativeArraySizeException` or `OutOfMemoryError`.
- A reader opens a file while a writer is appending or truncating it; `Files.size(...)` no longer describes a stable snapshot.
- A writer crashes mid-record, leaving a valid header followed by only part of the payload.
- Code confuses `read()==0` with `read()==-1`, or calls `ByteBuffer.getInt()` before four bytes are available.
- A record has all expected bytes yet contains corrupted data; checking size alone fails to detect it.

This lesson defines a simple contract to explain these concepts, accompanied by a Java 17+ program that generates fixtures and verifies **which cases must succeed and which must fail**.

## 2. Example Binary Format and EOF Rules

Suppose a file contains **exactly one record**:

~~~text
+----------------------------+--------------------------+
| Header: 4 bytes, big-endian| Payload: length bytes    |
| int length >= 0            | may be empty if length=0 |
+----------------------------+--------------------------+
   file offsets [0,4)             file offsets [4,4+N)
~~~

Examples:
- `00 00 00 02 4F 4B`: 2-byte payload containing ASCII `OK`.
- `00 00 00 00`: **a complete record** containing an empty payload.
- 0-byte file: **no record**, an error if the format requires one record.
- `00 00`: **truncated header**, since only 2 of 4 bytes exist.
- `00 00 00 05 41 42`: header declares 5 payload bytes, only 2 exist; **incomplete record**.

Distinguish **valid EOF on a boundary** from **premature EOF mid-record**:

~~~text
Multi-record:
  [record #1 complete][record #2 complete][EOF]
    -> Valid termination if the format allows multiple records.

  [record #1 complete][2/4 byte header #2][EOF]
    -> TRUNCATED_HEADER.

  [record #1 complete][header #2 says 5][2 payload bytes][EOF]
    -> TRUNCATED_PAYLOAD.
~~~

The demo program's policy is a **single-record file**, so any byte after the payload is a `TRAILING_BYTES` error. A multi-record parser differs: it continues looking for the next header and treats EOF as normal only when zero bytes of the next header have been read.

## 3. EOF, Short Reads, and `read` Returning 0 Are Not the Same

### `InputStream`

`InputStream.read()` returns:
- `0..255` when one byte is read.
- `-1` at end of stream.

`InputStream.read(byte[], off, len)` returns the number of bytes read, which may be **smaller than `len`**. When `len == 0`, it can return `0` immediately. Never assume a single `read` always fills the requested length.

`InputStream.readNBytes(int n)` returns an array that may be **shorter than `n`** if EOF arrives earlier. If you need exact `n` bytes, check the returned array/count. `DataInputStream.readFully(byte[])` attempts to read all bytes or throws `EOFException` if insufficient bytes remain.

~~~java
// Illustrative: in is a DataInputStream, expected is validated.
if (expected < 0 || expected > MAX_RECORD_BYTES) {
    throw new IOException("Invalid length");
}
byte[] payload = new byte[expected];
in.readFully(payload); // Incomplete payload => EOFException.
~~~

This snippet is not standalone because `expected`, `MAX_RECORD_BYTES`, and `in` must be defined. Never pass an unvalidated length prefix to `readFully`, because the array is allocated before the call.

### `FileChannel` and `ByteBuffer`

`FileChannel.read(ByteBuffer dst)` returns:
- A positive integer when `n` bytes are read, advancing `dst.position()`.
- `-1` at EOF.
- `0` when no bytes were read on that call; for an ordinary file with remaining space in the buffer, this is not an EOF signal.

~~~java
int n = channel.read(buffer);
if (n < 0) {
    // EOF.
} else if (n == 0) {
    // No progress yet.
} else {
    // n new bytes loaded, position advances by n.
}
~~~

**Never turn `0` into `-1`.** With a non-blocking `SocketChannel`, `0` is normal; wait on `Selector`/readiness instead of spinning. With `FileChannel`, test code may fail explicitly if looping makes no progress so it does not hang indefinitely.

### Read-Exactly Is a Loop, Not a Single `read`

~~~java
// Illustrative: FileChannel is open, dst is allocated.
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

The method returns the actual number of bytes received. The caller knows the expected length and classifies the result:
- Header needs 4, receives 0 initially ⇒ `EMPTY_FILE` or normal EOF depending on the contract.
- Header needs 4, receives 1–3 then EOF ⇒ `TRUNCATED_HEADER`.
- Payload needs `N`, receives `k < N` then EOF ⇒ `TRUNCATED_PAYLOAD`.

## 4. `ByteBuffer`: `position`, `limit`, and `flip`

A common mistake:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
channel.read(header);
int length = header.getInt(); // Wrong: unknown if enough bytes arrived, not flipped.
~~~

When reading into a `ByteBuffer`, `position()` advances toward the end. Verify enough data was read, then call `flip()` to switch to read mode:

~~~java
ByteBuffer header = ByteBuffer.allocate(4);
int actual = readUpTo(channel, header);
if (actual != 4) {
    throw new EOFException("incomplete header: " + actual + "/4");
}
header.flip();
int length = header.getInt();
~~~

In a multi-record parser, `compact()` keeps unparsed trailing bytes after a read pass, whereas `clear()` treats remaining bytes as no longer needed. Misusing `clear()` when the buffer already holds half of the next record's header drops data even when the file is intact.

## 5. Validate Length Before Allocating

A binary header can contain a negative or huge number. Never write:

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

`MAX_RECORD_BYTES` is a limit **dictated by the protocol and application memory**, not a standard Java constant. The demo uses `MAX=1024` to keep fixtures readable; real services must define it based on workload and quotas.

Key conditions:
- `length == 0` can be a valid empty payload, **distinct from an empty file**.
- `length < 0` must be rejected if the format uses a signed non-negative `int`.
- `length > MAX` must be rejected **before** allocation.
- When adding offsets and lengths, compute in `long` to prevent `int` overflow.
- If a parser supports unsigned 32-bit lengths, specify it explicitly with `Integer.toUnsignedLong(length)` and check bounds first; **never assume signed and unsigned behave identically**.
- Do not report success merely because the header is valid; still verify the full payload and checksum if present.

## 6. Empty Files and Empty Payloads: Minimum Test Suite

| Fixture | File Size | Result Under Single-Record Contract |
|---|---:|---|
| Completely empty file | 0 | `EMPTY_FILE` |
| Header with length 0 | 4 | `COMPLETE`, empty payload |
| Header with length 0, plus 1 byte | 5 | `TRAILING_BYTES` |
| Header with only byte `00` | 1 | `TRUNCATED_HEADER(1/4)` |
| Header with 3 bytes | 3 | `TRUNCATED_HEADER(3/4)` |
| Header with length 1 + one byte | 5 | `COMPLETE` |
| Header with length 1 + no payload | 4 | `TRUNCATED_PAYLOAD(0/1)` |

These test **format** boundaries, not `Files` API bugs. `Files.createTempFile` creates a valid empty file at the filesystem layer; the parser decides whether an empty file is acceptable.

Never write `catch(EOFException e) { return new byte[0]; }`, as that hides incomplete records and makes valid empty payloads indistinguishable from corrupted data.

## 7. Large Files and Data-Type Overflow Risks

A 3 GiB file is larger than `Integer.MAX_VALUE`. In Java:

- `Files.size(path)` returns `long`.
- `FileChannel.size()` returns `long`.
- `FileChannel.position(long)` and `read(dst, long offset)` handle `long` offsets.
- `ByteBuffer.allocate(int capacity)` is bounded by `int` and available memory.
- `Files.readAllBytes(path)` is bounded by array size and heap memory, unsuitable for huge files.

Wrong:

~~~java
int size = (int) Files.size(path);
byte[] all = new byte[size];
~~~

Casting can produce a negative value or wrong size. Even for files under 2 GiB, allocating a single huge array can cause `OutOfMemoryError`.

Better—read in blocks:

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

The buffer uses around 16 KiB whether the file is 5 MiB or many GiB, excluding parser state. If the file or stream is untrusted, enforce **total byte quotas** and deadlines, not just a per-chunk limit.

### Sparse Files and Tests Larger Than 2 GiB

Some filesystems support sparse files: a large logical size without consuming every disk block. Testing with `RandomAccessFile.setLength(long)` or writing at a very high offset can exercise `long`-offset logic, but:
- Not every provider supports sparse files the same way.
- A large logical file size does not prove streaming code works across full real data.
- Never blindly create multi-GiB fixtures on CI or production volumes.
- Use dedicated tests for `long` offsets and separate tests for streaming throughput.

## 8. Complete Java 17+ Program: Eight Boundary Cases

The program below creates fixtures in a temporary directory, reads **a single record** formatted as `[int32 length][payload]`, and prints deterministic results.

The cases cover: empty file, empty payload, complete record, truncated header, truncated payload, oversized length, trailing data, and a 5 MiB file read via streaming.

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
            // Directory contains only fixtures just created by the demo.
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

Compile and run:

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

### Output and Correctness Explanation

1. `empty-file`: 0/4 header bytes. Under a single-record contract, this cannot be treated as a valid record.
2. `empty-payload`: full 4-byte header, `length=0`, empty payload array; output prints `ok=` with no characters.
3. `complete`: 4-byte header and two bytes `OK`, reaching EOF cleanly after the payload.
4. `short-header`: only 2 bytes; the parser accurately reports `2/4` instead of calling `getInt` prematurely.
5. `short-payload`: header declares 5 bytes, only two bytes `A`/`B` exist; parser reports `2/5`.
6. `too-large`: `length=1025` exceeds `MAX=1024`; rejected **before allocation**.
7. `trailing`: `length=1` reads only `Q`; the extra `!` byte violates the single-record contract.
8. `large-file`: 640 writes of 8,192-byte blocks = **5,242,880 bytes**, read with a 16 KiB buffer without allocating an array sized to the whole file.

The program intentionally uses a blocking `FileChannel`, not a non-blocking `SocketChannel`. On non-blocking sockets, `read()==0` is normal and requires returning to the event loop—never throw an `IOException` as the demo helper does.

The demo uses ASCII only and a fixed big-endian header so stdout does not depend on OS locale or charset. Temporary files and directories are cleaned up along both normal and exception paths; JVM crashes or kills can still leave fixtures behind, as with any `finally`-based cleanup.

## 9. Reading a File Containing Multiple Records

If a file holds sequential records, we cannot reuse `readOneRecord` as-is because it forbids trailing bytes. Instead:

~~~text
LOOP:
   read 4-byte header
      - 0 bytes then EOF     -> END_OF_STREAM (normal)
      - 1..3 bytes then EOF  -> TRUNCATED_HEADER (error)
      - all 4 bytes          -> validate length
   read length payload bytes
      - short then EOF       -> TRUNCATED_PAYLOAD (error)
      - complete             -> COMPLETE(frame), process record
   loop back to LOOP
~~~

Use explicit result types or error codes:
`END_OF_STREAM_AT_BOUNDARY`, `TRUNCATED_HEADER`, `INVALID_LENGTH`, `TRUNCATED_PAYLOAD`, `CHECKSUM_MISMATCH`, and `IO_FAILURE`.

For an append-only log, EOF at the tail requires context: a writer may **still be appending**, unlike a committed snapshot file that was cut short. Recovery may discard an uncommitted tail **only if the log protocol is designed that way**—never blindly truncate arbitrary files on EOF.

## 10. Partial Writes and Files Cut Off Mid-Stream

Incomplete records often originate on the writing side:

~~~java
// Illustrative code: FileChannel opened for WRITE, buffer prepared.
while (buffer.hasRemaining()) {
    int n = channel.write(buffer);
    if (n <= 0) {
        throw new IOException("no write progress");
    }
}
~~~

A single `write` is not guaranteed to drain the entire buffer. If a writer writes a header with `length=100` and crashes after writing only 60 payload bytes, the reader hits EOF at `60/100`. Never turn that error into a "valid but shorter" record.

A complete file-publishing design typically looks like:

1. Create a temporary file on the same filesystem as the target.
2. Write all data, handling partial writes.
3. Verify length, checksum, and content format.
4. Explicitly call `channel.force(...)` if durability is required by the storage contract.
5. Close the writer.
6. Publish via `Files.move(temp, target, ATOMIC_MOVE)` when supported.
7. The reader must still validate record boundaries and checksums.

`ATOMIC_MOVE` **does not by itself guarantee crash durability**, nor is it a multi-file transaction. On network filesystems, also account for server consistency and durability guarantees.

## 11. Checksums: Having Enough Bytes Does Not Mean Valid Content

A record with complete header and payload bytes where a single byte was flipped still passes every length check.

~~~text
Expected: length=4, payload=01 02 03 04
Actual:   length=4, payload=01 02 03 05
Both have file size=8, yet their contents differ.
~~~

Common approaches:
- **CRC32/CRC32C** to detect accidental bit errors in data.
- **SHA-256** when a strong hash is needed to verify exact content.
- **HMAC/digital signatures** when defending against intentional tampering where an attacker could alter both file and checksum.

The parser order should be: check magic/version if present → read complete header → validate length → read complete payload → validate checksum/schema → accept record. Never feed data into business logic before verifying required invariants.

## 12. Deliberately Testing Short Reads

A local `FileChannel` may happen to fill the buffer in one call, hiding "single-read assumption" bugs. Use a wrapper returning at most 2 bytes per call:

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

For a payload with a 4-byte header and 5-byte body, the wrapper splits reads into `2+2+2+2+1` bytes; a correct parser must still reassemble the record completely.

**Short reads differ from early EOF:** a short read is followed by more bytes on subsequent reads; early EOF means the source returns `-1` before required bytes arrive. Write negative tests for both behaviors.

A wrapper returning `0` repeatedly (when the caller asked for a positive length) can trigger a busy loop in a buggy parser. Tests should have finite timeouts to catch non-progress loops.

## 13. File Size Is Not a Snapshot

Example:

~~~java
long observed = Files.size(path);
try (InputStream in = Files.newInputStream(path)) {
    // File may be truncated or appended to after size().
}
~~~

Never treat `Files.size()==expected` as proof that the file stays unchanged once reading begins. Another writer can modify, truncate, or replace the path, or cause the reader to hit premature EOF. Depending on the use case:

- Publish immutable files only after writing completes.
- Use file locking or coordination when multiple processes access the file.
- Use filesystem snapshots or transactional storage when true snapshots are needed.
- For tailers, preserve parser state and apply wait/timeout policies for in-flight records.

This matters even more over network filesystems with distinct caching and visibility rules; an accurate `read` only guarantees reading the bytes **exposed by the system**, not an atomic system-wide storage snapshot.

## 14. Exception Diagnostic Table

| Symptom | Possible Cause | What to Check |
|---|---|---|
| `EOFException` at header | 0–3 byte file, or normal boundary EOF depending on format | Header bytes received |
| `EOFException` at payload | Valid length, but body is short | Declared vs. actual bytes |
| `BufferUnderflowException` | Buffer lacks data or wasn't flipped | `position`/`limit`/`remaining` |
| `NegativeArraySizeException` | Negative length used directly | Validate before allocating |
| `OutOfMemoryError` | Reading a huge file into one array | Streaming and limits |
| `IOException` on `read()==0` | No progress in file-specific helper | Blocking mode / provider |
| `ClosedChannelException` | Channel closed mid-use | Resource ownership |
| `NonReadableChannelException` | Channel opened without `READ` | `OpenOption` |
| `AccessDeniedException` | File permissions / ACL | Filesystem permissions |
| `NoSuchFileException` | File deleted or path replaced | Concurrent operations |
| `FileSystemException` | Storage/mount error or file busy | Cause and platform diagnostics |
| Corrupted decoded data | Mismatched charset, byte order, or framing | Big-endian/UTF-8 and parser |
| Correct byte count, wrong content | Corruption, overwrite, or race | Checksums and concurrency |
| Parser hangs at high CPU | Unhandled `read()==0` loop | Readiness/backoff/timeout |

Never catch `IOException` and return an empty payload as if it succeeded. Read failures must remain distinct from a genuine zero-length payload.

## 15. Logging and Instrumentation to Reproduce Bugs

Information to include in diagnostic logs (without logging sensitive content):

- Request ID or job ID.
- Operation name: `open`, `read-header`, `read-payload`, `verify`, `write`, `close`.
- Record offset in the file (`long`), bytes received, and bytes expected.
- Length prefix, maximum allowed limit, and observed file size.
- Exception class and cause, channel/EOF state.
- Retry count and deadline if reading from an asynchronous source.
- Checksum/version state and cleanup performed.

Example message:

~~~text
job=42 op=read-payload offset=4 declared=100
received=60 status=TRUNCATED_PAYLOAD
~~~

Prefer **structured error codes** such as `EMPTY_FILE`, `TRUNCATED_HEADER`, `TRUNCATED_PAYLOAD`, `INVALID_LENGTH`, `TRAILING_BYTES`, and `CHECKSUM_MISMATCH` rather than having business logic parse exception message strings.

## 16. Recommended Test Matrix

| Test | Input | Expected |
|---|---|---|
| Empty file | 0 bytes | `EMPTY_FILE` if 1 record is required |
| Empty payload | Header `N=0`, no body | `COMPLETE` |
| 1-byte header | EOF | `TRUNCATED_HEADER 1/4` |
| 2-byte header | EOF | `TRUNCATED_HEADER 2/4` |
| 3-byte header | EOF | `TRUNCATED_HEADER 3/4` |
| Payload short by 1 byte | `N-1/N` | `TRUNCATED_PAYLOAD` |
| Payload completely missing | `0/N` with `N>0` | `TRUNCATED_PAYLOAD` |
| Negative length | `-1` | `INVALID_LENGTH` |
| Length equal to `MAX` | Full bytes | `COMPLETE` |
| Length `MAX+1` | Header exceeds max | `INVALID_LENGTH`, no allocation |
| Trailing garbage | Extra bytes after record | `TRAILING_BYTES` |
| Partial read | 1–2 byte/read wrapper | `COMPLETE` if all bytes arrive |
| Repeated zero reads | Simulated custom channel | No infinite spin |
| 5 MiB file | Stream chunks | Accurate count, small heap |
| Long offset >2 GiB | Sparse fixture | No `int` cast |
| Checksum mismatch | Full body with flipped byte | `REJECT` |
| Writer crash mid-payload | Missing record tail | Clear recovery policy |
| Concurrent truncate | File altered while reader open | Never falsely report complete |
| Permission error | File cannot be opened | Report I/O error |
| Disk full on write | Partially written | Do not publish file |
| Clean EOF in multi-record stream | No next header | `END_OF_STREAM` |
| EOF mid-next-header | 1–3 bytes | `TRUNCATED_HEADER` |

Generating fixtures from byte arrays or isolated temporary files keeps results reproducible and independent of external repo files. With JUnit 5, `@TempDir` provides a dedicated workspace per test; still verify cleanup and resource closure.

## 17. Property-Based Testing and Invariant Checks

Properties to prove for a length-prefixed codec:

~~~text
decode(encode(payload)) == payload
    for 0 <= payload.length <= MAX.

Truncate encoded stream before 4 bytes:
    TRUNCATED_HEADER or EMPTY_FILE.

Truncate encoded stream after header but before full payload:
    TRUNCATED_PAYLOAD.

Replace declared length with a negative value or >MAX:
    INVALID_LENGTH before allocating.

Append any byte to a complete record:
    TRAILING_BYTES when the contract allows only one record.
~~~

This is a **pseudo-spec**, not Java syntax. Test boundary values `0`, `1`, `MAX`, `MAX+1`, `Integer.MAX_VALUE`, negative values, and multi-byte UTF-8 payloads (where byte length differs from character count).

If a parser handles UTF-8 strings, the length prefix should normally count encoded **bytes**, not Java `String.length()`; Vietnamese characters can occupy multiple bytes.

## 18. Performance and Safety of Large-File Readers

1. Read in fixed-size blocks; never allocate an array for the whole file.
2. Use `long` for total byte counts and offsets.
3. Enforce quotas on total bytes and record counts.
4. Never loop indefinitely when `read` returns `0`.
5. Cap open files and pending I/O operations.
6. Monitor overall application memory, not just a single `ByteBuffer`.
7. With non-blocking sockets, use `Selector` and keep state across events.
8. Never use a single `MappedByteBuffer` to map a file beyond `int` capacity; map in regions if needed.
9. Use distinct timeout/retry policies for transient I/O errors versus malformed data.
10. Never treat atomic rename or `force()` as a substitute for validating headers, payloads, and checksums.

## 19. Common Misconceptions

| Misconception | Correct Understanding |
|---|---|
| A 0-byte file is the same as a 0-length payload | A 0-byte file has no header; a 0-length payload has a valid header |
| A single `read` fills the buffer | Reads can be partial |
| `read` returning `0` means EOF | EOF is `-1` |
| A valid header means the payload is complete | The writer may crash before finishing the body |
| File size returns `int` | Java returns `long` |
| Casting `long` to `int` is always fine | It can overflow |
| `readNBytes` always returns `N` bytes | It can be shorter at EOF |
| `readFully` returns fewer bytes silently | It throws `EOFException` when short |
| `Buffer.getInt` works right after `read` | You must check byte count and `flip()` |
| EOF mid-record is normal termination | That is a truncated record |
| EOF at a multi-record boundary is an error | It can be a normal end of stream |
| Length values in files are trustworthy | Validate negative/max bounds before allocating |
| Correct file size means valid checksum | Size does not verify content |
| One `write` call writes everything | Check and loop while `hasRemaining()` |
| `Files.size` is a fixed snapshot | The file can change after the check |
| Local file unit tests catch all short reads | Use a wrapper forcing partial reads |
| Catching an exception means the parser succeeded | Must surface the proper error state |

## 20. Self-Check Questions

1. 0-byte file when one 4-byte-header record is required: result? **`EMPTY_FILE`**.
2. File consisting of four `0` bytes: result? **Valid empty-payload record**.
3. Only 3/4 header bytes before EOF: **`TRUNCATED_HEADER`**.
4. Header says length 9, only 7 body bytes arrive before EOF: **`TRUNCATED_PAYLOAD 7/9`**.
5. `FileChannel.read` returns `2` when `remaining=4`: **continue reading**, not EOF.
6. Does `read()==0` mean EOF? **No**, EOF is `-1`.
7. Should negative length be checked before or after allocation? **Before**.
8. Can a 3 GiB file's `long` size be cast to `int`? **No**.
9. What does `DataInputStream.readFully` do when bytes are missing? **Throws `EOFException`**.
10. What does `InputStream.readNBytes(100)` return at EOF after 40 bytes? **A 40-byte array**.
11. Does a valid header length prove the record is complete? **No**.
12. Does a matching file size guarantee valid content? **No**, validate checksum/schema.
13. Should a parser be tested only with complete files? **No**, test partial reads and premature EOF.
14. What if a multi-record parser hits EOF before the first byte of the next header? **It can terminate validly**.
15. How should EOF mid-payload in an actively appended log be handled? **Per recovery protocol; never arbitrarily treat as complete or truncate blindly**.
16. Why use streaming for large files? **Reduces memory footprint and avoids file-sized allocations**.
17. Why clean up temporary fixtures even when tests fail? **Prevents resource leaks and interference with later tests**.

## 21. Official Java SE 17 Documentation

- [FileChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/FileChannel.html): read/write, size, position, and `long` offsets.
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `position`/`limit`/`flip`/`getInt`/`compact` and byte order.
- [InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read`, `readNBytes`, and EOF.
- [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): `readFully`, `readInt`, and `EOFException`.
- [Files](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html): `size`, `newInputStream`, `readAllBytes`, temporary files.
- [EOFException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/EOFException.html): unexpected end-of-file in binary data.
- [SocketChannel](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html): non-blocking reads, zero reads, and partial I/O.
