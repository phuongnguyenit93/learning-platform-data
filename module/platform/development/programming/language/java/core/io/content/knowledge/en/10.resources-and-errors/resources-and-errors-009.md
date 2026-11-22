# Partial Reads or Writes When Exceptions Occur in Java I/O

## 1. What Does "Partially Read/Written" Mean?

An I/O operation typically passes through multiple steps: fetching bytes from a source, passing through buffers or encoders, and reaching a file, socket, or device. If one step fails, data may already have been **partially consumed or sent** before the method throws an exception.

Examples:

- Reading a record expected to be 100 bytes, receiving 40 bytes, and then the connection fails.
- Writing 5 bytes to a stream: the first three reach the destination, and the fourth triggers `IOException`.
- Writing text to a `BufferedWriter` reports no error yet, while `flush()` or `close()` later discovers the destination is broken.
- Creating an output file and crashing mid-way, leaving the file with content that is **incomplete**.

**Principle:** `IOException` does not automatically roll back bytes already read or written. "The method threw an exception" **does not mean** "zero bytes changed". Conversely, a `write()` call returning normally does not by itself prove data was durably persisted or processed by the receiver.

Therefore, three states must be separated:

| State | What Is Known | What Is Not Guaranteed |
| --- | --- | --- |
| Partial read succeeded | Some amount of data reached the application | Not necessarily a complete record/message |
| Write returned | The API accepted the operation under that layer's contract | Not necessarily flushed, durably stored, or ACKed |
| I/O exception | The operation did not finish as requested | Not necessarily that prior effects were undone |

This is a matter of **data integrity and error management**, not merely adding a `catch` block.

## 2. Block Reads: Returning Fewer Bytes Is Not Always an Error

An `InputStream.read(byte[])` or `read(byte[], offset, length)` call can return **fewer bytes than requested**, even before reaching the end of the source. For instance, requesting 1,024 bytes and getting `37` is valid: the first 37 bytes of the array were just populated, and the rest do not belong to the new read.

- **Positive** result: actual number of bytes just read.
- **`-1`** result: EOF, source reports no more data.
- **`IOException`**: I/O error. Do not equate this error with EOF.
- For a length-**0** request, the result can be `0`; do not treat every `0` as EOF.

Pattern for reading until EOF, processing the exact number of bytes received:

```java
byte[] block = new byte[4096];
int count;

while ((count = input.read(block)) != -1) {
    consume(block, 0, count);
}
```

This is an **illustrative code snippet**: `input` is an open `InputStream`; `consume` is an application method that may throw; resource lifecycle should be managed with `try-with-resources` at the appropriate level.

If you only want one fixed-length record, **reading until EOF** can be the wrong approach. You must know the expected byte count and loop until enough bytes arrive (or use `DataInputStream.readFully(...)`). Returning fewer bytes because more are not ready yet differs from a **truncated** record.

**Note on mid-block read errors:** The base `InputStream` contract allows some implementations of `read(byte[], off, len)` to return bytes already received if an exception occurs **after the first byte** within the same call; other classes throw directly. Therefore, do not assume an exception always aligns precisely with the failing byte when using block reads. For critical data, manage record boundaries and verify the length of the entire message.

## 3. Java 17+ Example: Input Source Fails After Three Bytes

Create **`PartialReadDemo.java`**:

```java
import java.io.IOException;
import java.io.InputStream;
import java.util.StringJoiner;

public class PartialReadDemo {
    static class FailingInputStream extends InputStream {
        private final byte[] data = {10, 20, 30, 40};
        private int position;

        @Override
        public int read() throws IOException {
            if (position == 3) {
                throw new IOException("simulated connection loss");
            }
            if (position >= data.length) {
                return -1;
            }
            return data[position++] & 0xFF;
        }
    }

    public static void main(String[] args) {
        StringJoiner received = new StringJoiner(" ");

        try (InputStream input = new FailingInputStream()) {
            int value;
            while ((value = input.read()) != -1) {
                received.add(Integer.toString(value));
            }
        } catch (IOException ex) {
            System.out.println("Lỗi đọc: " + ex.getMessage());
        }

        System.out.println("Đã nhận: " + received);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 PartialReadDemo.java
java PartialReadDemo
```

Output:

```text
Lỗi đọc: simulated connection loss
Đã nhận: 10 20 30
```

The stream permits reading the first three bytes; the fourth read throws `IOException`. There is no `-1`: the program **never observed a valid EOF**. The three bytes already accepted by the application remain in `StringJoiner`; Java does not automatically retract them.

If the data represents a four-byte record, you must not silently treat `10 20 30` as a valid record. Report an incomplete record, discard uncommitted processing results, or await protocol recovery.

## 4. Partial Writes: An Error Does Not Mean the Destination Is Untouched

`OutputStream.write(int)` writes one byte or throws `IOException`. When an application writes **multiple bytes**, the initial bytes may already have been written before failure strikes. The `OutputStream` contract provides no rollback.

Standalone example **`PartialWriteDemo.java`** creates a simulated destination accepting only three bytes:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.HexFormat;

public class PartialWriteDemo {
    static class LimitedOutputStream extends OutputStream {
        private final ByteArrayOutputStream destination;
        private final int limit;
        private int written;

        LimitedOutputStream(ByteArrayOutputStream destination, int limit) {
            this.destination = destination;
            this.limit = limit;
        }

        @Override
        public void write(int value) throws IOException {
            if (written >= limit) {
                throw new IOException("simulated disk failure");
            }
            destination.write(value);
            written++;
        }
    }

    public static void main(String[] args) {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (OutputStream output = new LimitedOutputStream(destination, 3)) {
            output.write(new byte[]{1, 2, 3, 4, 5});
        } catch (IOException ex) {
            System.out.println("Lỗi ghi: " + ex.getMessage());
        }

        System.out.println("Byte còn lại: "
                + HexFormat.of().formatHex(destination.toByteArray()));
    }
}
```

Run command:

```bash
javac -encoding UTF-8 PartialWriteDemo.java
java PartialWriteDemo
```

Output:

```text
Lỗi ghi: simulated disk failure
Byte còn lại: 010203
```

In this example, `OutputStream.write(byte[])` inherited from `OutputStream` calls `write(int)` sequentially; after the third byte, the fourth triggers an error. **The three bytes `01 02 03` remain in the destination.** This simulation shows that a "write array" operation is not an all-or-nothing array transaction.

Specialized implementations may write in blocks differently. Do not infer from this example that every `write(byte[])` writes byte by byte, or that exceptions always reveal the exact byte count written. For real files or sockets, destination state may only be known via verification or protocol acknowledgment.

## 5. Buffering Delays When Errors Are Detected

`BufferedOutputStream` and `BufferedWriter` can hold data in RAM. When calling `write(...)`, data enters the **buffer** first; errors at the underlying destination sometimes only surface when:

- The buffer fills up and flushes down automatically.
- The program calls `flush()`.
- The program calls `close()`, which normally pushes remaining data down before closing.

Standalone example **`BufferedFailureDemo.java`**:

```java
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.HexFormat;

public class BufferedFailureDemo {
    static class LimitedOutputStream extends OutputStream {
        private final ByteArrayOutputStream destination;
        private int written;

        LimitedOutputStream(ByteArrayOutputStream destination) {
            this.destination = destination;
        }

        @Override
        public void write(int value) throws IOException {
            if (written == 3) {
                throw new IOException("simulated device failure");
            }
            destination.write(value);
            written++;
        }
    }

    public static void main(String[] args) {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (BufferedOutputStream output = new BufferedOutputStream(
                new LimitedOutputStream(destination), 8)) {
            output.write(new byte[]{1, 2, 3, 4, 5});
            System.out.println("write() chưa báo lỗi");
            output.flush();
        } catch (IOException ex) {
            System.out.println("Lỗi: " + ex.getMessage());
        }

        System.out.println("Byte đã xuống đích: "
                + HexFormat.of().formatHex(destination.toByteArray()));
    }
}
```

Run:

```bash
javac -encoding UTF-8 BufferedFailureDemo.java
java BufferedFailureDemo
```

Output:

```text
write() chưa báo lỗi
Lỗi: simulated device failure
Byte đã xuống đích: 010203
```

Because the buffer has an 8-byte capacity and the application only wrote 5 bytes, `write()` completed without calling the underlying stream. `flush()` began transferring bytes to `LimitedOutputStream` and failed after 3 bytes.

**Consequence:** A successful `BufferedWriter.write(...)` or `BufferedOutputStream.write(...)` may only mean **writing to the buffer succeeded**. You must handle exceptions on both `flush()` and `close()`. Nor does `flush()` mean data was safely synced to storage or processed by the remote side: those are different guarantees at different layers.

If an error occurs during flush, the buffer may still hold untransferred data, or the lower layer may have accepted part of it. Blindly repeating the same `write(...)` call risks **duplicate data**.

## 6. Structured Records: Complete Only When All Bytes Are Present

Consider a binary format:

```text
[int payloadLength: 4 bytes][payload: exact payloadLength bytes]
```

The reader must obtain exactly four bytes for `int`, followed by exact `payloadLength` bytes for the payload. Either step can fail partway through.

`DataInputStream` provides:

- `readInt()`: needs four bytes to construct an `int`; if the source ends early, it throws `EOFException`.
- `readFully(byte[])`: attempts to read enough to fill the array; if EOF arrives before filling it, throws `EOFException`. **The array may have been partially populated before the exception occurred.**
- `read(byte[])`: can return fewer bytes than requested, so never substitute one call for `readFully`.

Example **`TruncatedRecordDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.util.HexFormat;

public class TruncatedRecordDemo {
    public static void main(String[] args) throws IOException {
        byte[] truncated = {0, 0, 0, 3, 0x41, 0x42};

        try (DataInputStream input = new DataInputStream(
                new ByteArrayInputStream(truncated))) {
            int length = input.readInt();
            if (length < 0 || length > 1024) {
                throw new IOException("Invalid payload length");
            }

            byte[] payload = new byte[length];
            try {
                input.readFully(payload);
                System.out.println("Bản ghi hoàn chỉnh");
            } catch (EOFException ex) {
                System.out.println("Thiếu byte của payload");
                System.out.println("Không commit: "
                        + HexFormat.of().formatHex(payload));
            }
        }
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 TruncatedRecordDemo.java
java TruncatedRecordDemo
```

Output:

```text
Thiếu byte của payload
Không commit: 414200
```

The payload requires 3 bytes, yet only `41 42` remain in the stream. `readFully` wrote two bytes into the array before hitting EOF; the third element keeps its default `00`. **Never treat `41 42 00` as real data**: the `00` byte here is memory zero-initialization, not a third byte from the source.

Key takeaway: `readFully` helps detect incomplete records, yet **does not undo** mutations already made to the destination array. Only publish the record to the rest of the application **after** verifying both length and validity.

## 7. Distinguishing EOF, IOException, and Invalid Data Read Without Errors

| Scenario | Meaning | Appropriate Action |
| --- | --- | --- |
| `read() == -1` | Source reports no more bytes | Check whether EOF is permitted by schema at this position |
| `EOFException` | Method needed more bytes for a value/record, yet none remained | Treat as truncated data unless protocol defines otherwise |
| `IOException` | I/O malfunction, such as device or socket error | Preserve error context; determine processed portion and recovery policy |
| Enough bytes yet wrong checksum | Data arrived yet failed integrity verification | Reject record; do not publish data |
| Enough bytes yet wrong field order | Parser misinterprets data, possibly without throwing | Check schema, version, types, and offsets |

Do not write:

```java
try {
    parseRecord(input);
} catch (IOException ex) {
    // ignore and keep using half-parsed results
}
```

This is **code illustrating an anti-pattern**. If the parser already mutated a business object before finishing the record, ignoring the exception can leave inconsistent state.

A better approach is reading into **local variables/temporary objects**, validating all fields and checksums (if any), and only then adding to lists or mutating official state. Never publish a partial record before completion criteria are satisfied.

## 8. Safer File Writing: Temporary File Then Publish

Writing directly to the destination path can expose a **partially written new file** to readers if the program or device fails. When completely replacing file contents, a standard pattern is:

1. Create a **temporary file in the same directory/filesystem** as the target.
2. Write the **entire** new content to the temporary file.
3. Finalize the writer and verify data if needed.
4. Rename/move the temporary file to the target name once ready.
5. If an error occurs before publishing, delete the temporary file; preserve the old target file if still intact.

Java 17+ illustrative snippet:

```java
Path target = Path.of("result.txt").toAbsolutePath();
Path directory = target.getParent();
Path temporary = Files.createTempFile(directory, ".result-", ".tmp");

try {
    Files.writeString(temporary, text, StandardCharsets.UTF_8);
    // When format requires, validate contents of temporary file here.
    Files.move(temporary, target,
            StandardCopyOption.ATOMIC_MOVE,
            StandardCopyOption.REPLACE_EXISTING);
} finally {
    Files.deleteIfExists(temporary);
}
```

This is an **illustrative snippet**, not a standalone program. It requires imports for `java.nio.file.Files`, `java.nio.file.Path`, `java.nio.file.StandardCopyOption`, and `java.nio.charset.StandardCharsets`; declaring `String text`, handling `IOException`, and deciding overwrite policy per business rules. Never run against critical data paths without checking ownership and replacement needs.

**Limitations to understand:**

- `ATOMIC_MOVE` **may not be supported by the filesystem**, which throws `AtomicMoveNotSupportedException`. Never silently drop the atomic flag and still claim data is published atomically.
- When `ATOMIC_MOVE` is combined with other options, details of replacing an existing target can depend on filesystem/provider. Check the contract and test on your target deployment environment.
- Atomic rename pertains to **atomic visibility of the filename**, not **durability across power loss**. When strict durability is required, use sync/force mechanisms and directory management appropriate for the OS/filesystem.
- If the application writes multiple files or updates a database concurrently, rename **does not create a cross-resource transaction**.
- When move fails or concurrent writers exist, ensure cleanup does not accidentally delete someone else's file or overwrite a newer version.

For small files not requiring atomicity, direct `Files.writeString(...)` can suffice. Yet when requiring "either the old intact file or the complete new file", design an explicit commit path rather than relying solely on `try-with-resources`.

## 9. `try-with-resources` and Errors in `close()`

`try-with-resources` closes resources even when code inside throws an exception. However:

- Closing a resource **does not roll back** already written bytes.
- `close()` itself can throw `IOException`, especially when flushing pending buffers down to lower layers.
- If the `try` block already has a primary exception and `close()` also fails, Java keeps the block's exception as the **primary exception**, while the close error is normally attached in `getSuppressed()`.
- Do not overwrite or lose the primary exception just because you focus on close errors.

Standalone example **`SuppressedCloseDemo.java`**:

```java
import java.io.IOException;

public class SuppressedCloseDemo {
    static class FailingResource implements AutoCloseable {
        @Override
        public void close() throws IOException {
            throw new IOException("close failed");
        }
    }

    public static void main(String[] args) {
        try (FailingResource resource = new FailingResource()) {
            throw new IOException("write failed");
        } catch (IOException ex) {
            System.out.println("Primary: " + ex.getMessage());
            for (Throwable suppressed : ex.getSuppressed()) {
                System.out.println("Suppressed: "
                        + suppressed.getMessage());
            }
        }
    }
}
```

Run:

```bash
javac SuppressedCloseDemo.java
java SuppressedCloseDemo
```

Output:

```text
Primary: write failed
Suppressed: close failed
```

During real debugging, record both the primary exception and suppressed exceptions in appropriate logs. Avoid duplicate logging or accidentally exposing sensitive data, tokens, or entire customer payloads.

## 10. Retries and the Risk of Data Duplication

When writing to a socket, database gateway, or remote service, the sender does not always know **how many bytes were successfully delivered/received** after an error:

```text
Client                       Server
  | ---- message bytes ---->  |
  | ---- message bytes --X    |  connection error on client side
  |                            |
  |  Server may have received/ |
  |  processed partial or all. |
```

Resending the entire request without deduplication can create two transactions. Conversely, sending only the missing portion without knowing the exact acknowledged offset can corrupt the stream.

Protocol-dependent approaches:

- **Framing**: length prefixes, message IDs, versions, and checksums/hashes to identify boundaries and validity.
- **Idempotency key**: the receiver records a unique ID and does not execute the same action twice if the request is resent. Deduplication must be implemented on the receiving side.
- **Per-message ACK**: treat a request as complete only after receiving a protocol response; ACKs themselves can be lost, so deduplication is still needed.
- **Resume with confirmed offset**: only use when the protocol supports byte positions, checksums, and explicit session state; never guess an offset from how many bytes the client passed to `write()`.
- **Bounded retries**: timeouts, backoff, and rules on which errors are retryable. One exception alone is not enough to prove the prior operation is safe to repeat.

For large file transfers, you can write to a temporary name on the server, verify length and checksum, and only then publish; never allow consumers to read a partially received document.

## 11. When Using `Reader`, `Writer`, and Charsets

Character data can also be incomplete:

- `Reader.read(char[])` returns the actual number of `char` units read. It does not guarantee filling the array.
- `BufferedReader.readLine()` can return a final line without a newline if **valid EOF** occurs after line content. Yet if the source hits `IOException` mid-line, never treat that as a complete record.
- `OutputStreamWriter` converts `char` to bytes per charset. One Unicode character can produce multiple UTF-8 bytes, so stream interruption can leave an **incomplete UTF-8 byte sequence**.
- `BufferedWriter` can hold characters not yet passed to the encoder. Errors in `close()` or `flush()` can leave the destination incomplete.
- With `CharsetDecoder` configured with `CodingErrorAction.REPORT`, invalid byte sequences trigger clear encoding/decoding errors rather than silently inserting replacement characters.

Text data is a **structured document or record**, not just a bag of characters. For instance, CSV may be mid-quoted string; JSON may miss closing braces. Successfully reading a `String` does not prove the document is valid. Parse and publish data only after syntax and business validation complete.

For network sources, a final line without a newline may still be valid content if the protocol uses EOF to mark termination; yet if the stream errors mid-line, you cannot claim it was a normal EOF. Valid boundaries must be defined by the **protocol**.

## 12. Tracking Progress and Controlled Recovery

When reading/writing large blocks, track processed byte counts **confirmed at the appropriate layer**, for example:

```java
long totalRead = 0;
byte[] buffer = new byte[8192];
int count;

while ((count = input.read(buffer)) != -1) {
    process(buffer, 0, count);
    totalRead += count;
}
```

This is an **illustrative snippet**, requiring valid `input` and `process`. `totalRead` only indicates **bytes processed by the application after `process` succeeds**, not that data was committed elsewhere. If `process` throws after processing half a block, the counter may not accurately reflect every side effect that occurred. Offset updates and commit designs must align with actual operation semantics.

When exceptions happen, collect enough context for debugging:

1. Operation name: reading header, reading payload, flushing output, closing, renaming...
2. Record/chunk index, expected offset, confirmed processed bytes.
3. Expected length and checksum, plus actual check results.
4. Exception cause and suppressed exceptions if present.
5. Whether the same stream can continue or a fresh session must be opened.
6. Whether state is **temporary**, **committed**, or **indeterminate**.

Logging raw byte contents or entire files is unnecessary, especially when data holds private information. Technical metadata and error codes are usually enough for diagnosis.

## 13. Common Mistakes and Fixes

| Mistake | Risk | Fix |
| --- | --- | --- |
| `catch (IOException)` and treating it as EOF | Uses incomplete data as a valid record | Distinguish schema-valid termination from failure |
| Assuming `read(byte[])` always fills the array | Stale/default bytes mix into results | Use returned byte count or `readFully` |
| Catching `EOFException` and still using the target array | Array may be partially overwritten | Publish payload only after full completion |
| Thinking `write(byte[])` throwing means 0 bytes were written | File/socket may have partially changed | Treat outcome as indeterminate; verify or use commit flow |
| Ignoring `flush()`/`close()` errors | Data stuck or lost in buffers | Handle errors at all completion boundaries |
| Immediately retrying full `write` after an error | Can duplicate records | Use message IDs, ACKs, idempotency, or confirmed resume |
| Writing directly to critical target files | New file may be left truncated | Write temp file then publish per filesystem capabilities |
| Treating atomic rename as equivalent to fsync | Power loss can still affect durability | Distinguish atomic visibility from durability |
| Ignoring declared length | Oversized allocation or accepting incomplete records | Validate length and actual bytes read |
| Parser mutating real objects field by field | Exceptions leave half-updated state | Parse into temporary state and commit when valid |
| Losing primary exception due to `close` error | Misdiagnoses root cause | Use `try-with-resources` and inspect suppressed exceptions |
| Counting "bytes written" by number of `write` calls | Unknown how much the destination actually received | Rely on protocol/destination acknowledgments |

## 14. Checklist and Self-Practice Exercises

**Before reading:**

- [ ] Specify exact length, delimiter, EOF marker, or framing rules.
- [ ] Expect and handle `read(...)` returning fewer bytes than requested.
- [ ] Never publish data to business logic before reading completely and validating.
- [ ] Distinguish valid EOF from `IOException` and mid-record EOF.
- [ ] Bound lengths/record counts to avoid uncontrolled allocations.

**Before writing:**

- [ ] Determine whether data needs "all-or-nothing" guarantees at file/message level.
- [ ] Never assume a single `write(...)` is a transaction.
- [ ] Finalize writers, checking `flush`, `close`, and all exceptions.
- [ ] Use a commit mechanism (temp file/rename) or protocol ACKs if needed.
- [ ] Build retry strategies that avoid both duplication and data loss.
- [ ] Distinguish "bytes accepted by API", "received by peer", "durably written", and "processed".

**Exercise 1 — truncated source:** Given format `[int length=5][5-byte payload]` where the source holds only 3 payload bytes, use `DataInputStream.readFully` and verify `EOFException`. Explain why the 5-byte array can contain three real bytes and two default bytes.

**Exercise 2 — failing destination:** Create an `OutputStream` that throws `IOException` after `N` bytes. Write data through `BufferedOutputStream`, test different buffer sizes, and predict whether the error surfaces at `write`, `flush`, or `close`. Do not blindly call `write` again after failure.

**Exercise 3 — file update:** Design exporting a large report so other readers never see an incomplete report. Clearly describe the temporary file, validation timing, publication method, policy when `ATOMIC_MOVE` is unsupported, and whether durability guarantees are required.

**Key Takeaway:** I/O is a process that can **partially succeed**. Java signals failures via exceptions without automatically undoing prior effects. To be safe, define record boundaries, verify complete byte counts, separate temporary results from committed data, handle buffer/close errors, and design recovery or retries around the protocol.
