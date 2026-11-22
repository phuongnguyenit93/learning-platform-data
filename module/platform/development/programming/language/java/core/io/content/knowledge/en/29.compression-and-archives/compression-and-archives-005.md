# finish vs. flush and close in Java: Compressing and Packaging Data

## 1. Three Distinct Actions on an Output Stream

Compression and archiving classes in `java.util.zip` wrap an underlying `OutputStream` and transform application data into ZIP, GZIP, or DEFLATE/zlib data. Learners often confuse three methods:

- **`flush()`**: requests forwarding currently buffered bytes down to the underlying layer per the current stream's contract. It does not mark the compressed format as finished, and does not close the stream.
- **`finish()`**: finalizes *the current compressed stream or archive structure*, writing any remaining compressed data and required ending metadata; **does not close the underlying destination stream**.
- **`close()`**: closes the compression stream, typically invoking format-finalization logic if still needed, releasing resources, and **closing the wrapped destination stream**.

Calling `flush()` alone does not give a ZIP archive its central directory or a GZIP member its trailer. Conversely, calling `close()` on a wrapper may close a stream that the caller or framework still needs to use. `finish()` is useful when you want a complete compressed format while leaving the underlying stream open.

The goals of this lesson are to identify the proper lifecycle when using `ZipOutputStream`, `GZIPOutputStream`, and `DeflaterOutputStream`; understand `ZipOutputStream.closeEntry()`; build a runnable Java 17+ example; and recognize errors such as missing footers, misusing ownership, and confusing flush with durability.

## 2. A Multi-Layer Pipeline

Data flow example:

~~~text
Application writes bytes
       |
       v
ZipOutputStream / GZIPOutputStream / DeflaterOutputStream
       |    compression / archive metadata
       v
BufferedOutputStream (optional)
       |    Java-side buffering
       v
FileOutputStream / socket OutputStream / ByteArrayOutputStream
       |
       v
Storage / network / memory
~~~

Each layer manages **a different kind of state**. The compressor's output may not yet have emitted the final bytes needed for a valid archive, even if lower layers have flushed all bytes they hold. Conversely, after the compressor finishes, the underlying layer may still be open with data not yet durably persisted to disk or acknowledged by a network peer.

| Requirement | Appropriate Tool | What Must NOT Be Inferred |
| --- | --- | --- |
| Push buffered bytes while continuing to write | `flush()` | Does not mean the archive is finished |
| Complete ZIP/GZIP while keeping destination open | `finish()` | Does not mean the destination is closed |
| Finalize and release a stream chain you own | `close()`, usually via `try-with-resources` | Does not mean all consumers have received/processed it |
| Persist data durably on storage media | Storage protocol/`FileChannel.force(...)` where appropriate | Not achieved merely by calling `flush()` or `finish()` |
| Ensure the consumer read successfully | Archive validation and application acknowledgment when needed | Not replaced by sender-side close status |

Therefore, two independent questions must be answered: **is the format complete?** and **who owns the destination resource?**

## 3. flush() Is Not the End-of-Stream Marker for Compressed Data

`OutputStream.flush()` behaves according to the implementation. For example, `BufferedOutputStream.flush()` transfers Java's buffer to the next stream; `DeflaterOutputStream.flush()` may push compressed data outward and invoke flush on the underlying output.

For `DeflaterOutputStream` and `GZIPOutputStream`, constructors accept `syncFlush=true` so that flushing executes `Deflater.SYNC_FLUSH`. This helps a receiver decompress **a partial ongoing stream**, even though the compressor has not received an end signal. That is important for streaming, though it can reduce compression ratio if flushed too frequently.

However:

1. `flush()` does not signal *end-of-input* to the compressor.
2. `flush()` does not write the ZIP central directory to finish the archive.
3. `flush()` does not guarantee writing the GZIP trailer containing CRC32 and ISIZE.
4. `flush()` does not automatically release compression resources or close the destination.
5. `flush()` does not substitute for forcing data onto disk or TCP acknowledgment.

Illustrative snippet:

~~~java
GZIPOutputStream gzip = new GZIPOutputStream(destination, true);
gzip.write(payloadPart1);
gzip.flush();                // Allows consumer to receive more compressed data so far.
gzip.write(payloadPart2);   // Can still continue adding payload.
gzip.finish();               // Only now is the GZIP member finalized.
~~~

`destination`, `payloadPart1`, and `payloadPart2` must be declared, with imports and `IOException` handling. This is not a standalone program. If you want to close `destination` because the method owns it, call `close()` or use an appropriate resource-management construct.

**Distinction:** `flush()` may make immediate bytes decompressible, but **does not prove the compressed stream is valid as a complete unit**. Some decoders will wait or report unexpected EOF when ending trailer/metadata are missing.

## 4. finish(): Finalizes the Compressed Stream While Keeping Destination Open

`finish()` signals that **all bytes belonging to this compressed content have been written**. The compressor must flush remaining output, terminate the compressed stream, and write format-specific metadata. For example:

- `ZipOutputStream.finish()`: finalizes the ZIP archive, writing the central directory and ending records.
- `GZIPOutputStream.finish()`: finishes the DEFLATE payload and writes the GZIP trailer with checksum and size.
- `DeflaterOutputStream.finish()`: finishes the compressed stream from `Deflater`, pushing remaining data downstream.

Per the contract of these classes, `finish()` **does not close the underlying output stream**. That lets the caller decide when to close the destination after performing any further valid pipeline steps.

**You cannot continue appending data to the same compressed stream/ZIP archive after finish.** To write remaining content, do so **before** finish. If multiple compressed messages are needed over the same connection, use a framing protocol or container structure with corresponding writer/reader objects. Never assume arbitrarily appending bytes after a completed ZIP/GZIP will be supported by every consumer.

When `finish()` throws `IOException`, never mark the output as successful. The compressor may have written most of the payload without finishing the ending metadata. The archive can be corrupted even though earlier `write()` calls succeeded.

## 5. close(): Ends the Lifecycle and Propagates Close Downstream

For standard compression output streams in `java.util.zip`, `close()` performs any needed format finalization, closes the compression stream, and closes the underlying stream per the class contract. It also releases resources owned by the compression stream.

When **the method itself opens the output file** to create a ZIP, the usual pattern is:

~~~java
Path output = Path.of("archive.zip");
try (ZipOutputStream zip = new ZipOutputStream(
        Files.newOutputStream(output))) {
    zip.putNextEntry(new ZipEntry("hello.txt"));
    zip.write("hello".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
} // zip.close() finalizes the ZIP if needed and closes the file stream.
~~~

This is an illustrative snippet to place in a method handling `IOException` with appropriate imports. If you intend to close the ZIP right after writing entries, **there is no need to call `finish()` explicitly** because `close()` is already responsible for finalizing it.

However, when **the destination is provided by the caller** (for example, an output stream managed by a web framework), you must not arbitrarily close it just to finalize the ZIP. You can call `finish()` and leave closing the destination to the caller; if you need to close the wrapper to release compression state without closing the destination, use a non-closing adapter with a clear contract. The ownership section below covers details.

## 6. ZIP: How Does closeEntry() Differ from finish()?

A ZIP archive contains one or more `ZipEntry` items. The typical lifecycle is:

~~~text
putNextEntry("a.txt")
write bytes of a.txt
closeEntry()            [finalize first entry]
putNextEntry("b.txt")
write bytes of b.txt
closeEntry()            [finalize second entry]
finish()                [write ending metadata for entire ZIP archive]
close()                 [close stream and destination stream if owned]
~~~

`ZipOutputStream.closeEntry()` only ends **the current entry**. For DEFLATED entries, compressed data and metadata such as size and CRC may be finalized at this step per the ZIP format. However, ZIP also has a **central directory** at the end of the archive describing entries and an *End of Central Directory* record. Those are written when `finish()`/`close()` finalizes the archive.

Therefore, a ZIP file that has called `closeEntry()` but not `finish()` **may not yet be openable by `ZipFile`** or ZIP readers that rely on the central directory. Do not treat the fact that `ZipInputStream` can sometimes read the first entry as proof that the whole archive is complete: `ZipInputStream` reads sequentially; `ZipFile` requires the central directory.

### Example Building a Two-Entry Archive

~~~java
ZipOutputStream zip = new ZipOutputStream(destination);

zip.putNextEntry(new ZipEntry("a.txt"));
zip.write("A".getBytes(StandardCharsets.UTF_8));
zip.closeEntry();

zip.putNextEntry(new ZipEntry("b.txt"));
zip.write("B".getBytes(StandardCharsets.UTF_8));
zip.closeEntry();

zip.finish(); // Central directory written; destination remains open.
~~~

This is an illustrative snippet. `destination` must be a valid `OutputStream` with proper imports in real code. Do not add entries to a ZIP object after `finish()`; to put multiple files into **one** ZIP, write them as multiple entries before finishing, rather than arbitrarily concatenating another ZIP.

For `ZipEntry.STORED` (uncompressed), the entry requires accurate size and CRC before writing per the API, unlike `DEFLATED`. Entry-level rules do not change the principle that `closeEntry()` differs from `finish()`.

## 7. GZIP: flush Does Not Write the GZIP Trailer

A GZIP member typically has the structure:

~~~text
+-------------+-------------------+------------------+
| GZIP header | DEFLATE payload   | GZIP trailer     |
+-------------+-------------------+------------------+
                                    CRC32 + ISIZE
~~~

`GZIPOutputStream.finish()` finishes compressed data and writes the trailer. `CRC32` is the checksum of the uncompressed data; `ISIZE` stores the uncompressed size modulo 2^32. Thus a receiver should only consider the member complete when the ending structure is written and read properly, rather than relying solely on `gzip.flush()`.

Usage:

~~~java
GZIPOutputStream gzip = new GZIPOutputStream(destination, true);
gzip.write("hello".getBytes(StandardCharsets.UTF_8));
gzip.flush();  // syncFlush: useful for streaming, does not emit the ending trailer yet.
gzip.finish(); // Finalizes the member and writes the trailer without closing destination.
~~~

This is an illustrative fragment, not a standalone program. You may call `gzip.close()` after finish if you actually own the destination stream.

Unlike ZIP, GZIP typically packages **a single data stream** rather than multiple entries with path names. Although some decoders support concatenated GZIP members, never assume every consumer or your protocol supports that. If you need to send multiple messages, define clear framing and test the receiver.

## 8. DeflaterOutputStream: Compression Layer, Not a ZIP Container

`DeflaterOutputStream` provides a stream compressed by `Deflater`. A default `Deflater` normally produces a zlib-wrapped DEFLATE stream; `GZIPOutputStream` and `ZipOutputStream` place different metadata around DEFLATE.

| Writer Object | Content | What Is Written on finish |
| --- | --- | --- |
| `DeflaterOutputStream` | Compressed stream configured by `Deflater`, default zlib-wrapped DEFLATE | Ends the deflater's compressed stream, including zlib trailer/checksum when applicable |
| `GZIPOutputStream` | One GZIP member | Final DEFLATE block and GZIP trailer |
| `ZipOutputStream` | A multi-entry ZIP archive | Entry-closing metadata and central directory/end record |

`DeflaterOutputStream.finish()` cannot replace `ZipOutputStream.finish()` when the goal is a complete ZIP file. Nor can you feed bytes from a default `DeflaterOutputStream` into `GZIPInputStream` or `ZipFile` expecting those readers to recognize the format: zlib, GZIP, and ZIP are not the same file format.

With `DeflaterOutputStream`, `syncFlush=true` enables `Deflater.SYNC_FLUSH` during `flush()` so streaming can make progress, yet the official end point remains `finish()`/`close()`.

## 9. Complete Java 17+ Example: ZIP and GZIP with All Three Methods

The `CompressionLifecycleDemo.java` program uses `ByteArrayOutputStream` as storage and a `TrackedOutput` to observe whether `close()` was propagated down to the destination. The tracker is necessary because `ByteArrayOutputStream.close()` is a no-op: you cannot simply check whether a `ByteArrayOutputStream` still exposes its byte array to infer whether a wrapper closed the stream.

Save file **`CompressionLifecycleDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.FilterOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.zip.GZIPInputStream;
import java.util.zip.GZIPOutputStream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;
import java.util.zip.ZipOutputStream;

public class CompressionLifecycleDemo {
    private static final byte[] HELLO =
            "hello".getBytes(StandardCharsets.UTF_8);

    static final class TrackedOutput extends FilterOutputStream {
        boolean closed;
        TrackedOutput(OutputStream out) { super(out); }
        @Override public void close() throws IOException {
            try { super.close(); } finally { closed = true; }
        }
    }

    public static void main(String[] args) throws IOException {
        zipExample();
        gzipExample();
    }

    private static void zipExample() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        TrackedOutput destination = new TrackedOutput(bytes);
        ZipOutputStream zip = new ZipOutputStream(destination);
        zip.putNextEntry(new ZipEntry("hello.txt"));
        zip.write(HELLO);
        zip.closeEntry();
        zip.flush();
        int sizeAfterFlush = bytes.size();
        System.out.println("ZIP flush closed destination: " + destination.closed);
        zip.finish();
        System.out.println("ZIP finish added bytes: " + (bytes.size() > sizeAfterFlush));
        System.out.println("ZIP finish closed destination: " + destination.closed);
        zip.close();
        System.out.println("ZIP close closed destination: " + destination.closed);

        try (ZipInputStream in = new ZipInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            ZipEntry entry = in.getNextEntry();
            System.out.println("ZIP entry: " + entry.getName());
            System.out.println("ZIP content: " +
                    new String(in.readAllBytes(), StandardCharsets.UTF_8));
        }
    }

    private static void gzipExample() throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        TrackedOutput destination = new TrackedOutput(bytes);
        GZIPOutputStream gzip = new GZIPOutputStream(destination, true);
        gzip.write(HELLO);
        gzip.flush();
        int sizeAfterFlush = bytes.size();
        System.out.println("GZIP flush closed destination: " + destination.closed);
        gzip.finish();
        System.out.println("GZIP finish added bytes: " + (bytes.size() > sizeAfterFlush));
        System.out.println("GZIP finish closed destination: " + destination.closed);
        gzip.close();
        System.out.println("GZIP close closed destination: " + destination.closed);

        try (GZIPInputStream in = new GZIPInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            System.out.println("GZIP content: " +
                    new String(in.readAllBytes(), StandardCharsets.UTF_8));
        }
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac CompressionLifecycleDemo.java
java CompressionLifecycleDemo
~~~

Stdout actually verified on the JDK:

~~~text
ZIP flush closed destination: false
ZIP finish added bytes: true
ZIP finish closed destination: false
ZIP close closed destination: true
ZIP entry: hello.txt
ZIP content: hello
GZIP flush closed destination: false
GZIP finish added bytes: true
GZIP finish closed destination: false
GZIP close closed destination: true
GZIP content: hello
~~~

Explanation:

1. After `zip.flush()`, the tracker shows the destination is not closed. At that point the archive is not yet guaranteed to have a central directory.
2. After `zip.finish()`, the byte count grows because ZIP ending metadata is written, yet `destination.closed` remains false.
3. `zip.close()` closes the wrapper and forwards `close()` to the tracker, setting the flag to true. Decompressing the finalized archive succeeds with entry `hello.txt` and text `hello`.
4. Similarly, `gzip.flush()` (with syncFlush enabled here) has not written the member-ending trailer; `gzip.finish()` appends the final bytes without closing destination.
5. `gzip.close()` closes the destination; `GZIPInputStream` decompresses `hello` after format completion.
6. The `finish added bytes: true` lines are **specific outcomes of this example**. Do not infer that every finish in all states/implementations always increases size in the exact same way. Rely on the format-completion contract, not a fixed byte delta.

The demo gives each compressed writer its own destination. It does not send over a network and does not feed unfinished bytes to a reader to claim a reader must always throw; decoder behavior on partial input can depend on verification logic.

## 10. Who Has the Right to Close the Destination?

**Precedence rule:** whoever **creates and owns** the resource decides when it is closed; code that **borrows** a stream must obey the caller's contract.

Case of creating a standalone file:

~~~java
Path file = Path.of("backup.zip");
try (ZipOutputStream zip = new ZipOutputStream(Files.newOutputStream(file))) {
    zip.putNextEntry(new ZipEntry("metadata.txt"));
    zip.write("done".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
} // Owns closing rights, so try-with-resources is appropriate.
~~~

This is an in-method snippet requiring imports and IOException handling. If `close()` succeeds, the ZIP is finalized and the file output is closed. If close throws an error, do not publish that file as valid output.

Case of a method receiving only `OutputStream destination`:

~~~java
static void writeZip(OutputStream destination) throws IOException {
    ZipOutputStream zip = new ZipOutputStream(destination);
    zip.putNextEntry(new ZipEntry("note.txt"));
    zip.write("sample".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
    zip.finish();
    // Do not call zip.close() here since destination belongs to the caller per contract.
}
~~~

This is an illustrative method. It finalizes the archive while avoiding closing the caller's destination. Tradeoff: the compression wrapper is not closed immediately; in production code wanting deterministic cleanup while keeping the destination open, you can use a **non-closing** wrapper so `zip.close()` only closes the compression layer and flushes to the caller without closing the real destination.

Illustrative adapter (not part of the standard library):

~~~java
final class NonClosingOutputStream extends FilterOutputStream {
    NonClosingOutputStream(OutputStream wrapped) { super(wrapped); }

    @Override
    public void close() throws IOException {
        flush(); // Does not close wrapped.
    }
}
~~~

Usage:

~~~java
try (ZipOutputStream zip =
        new ZipOutputStream(new NonClosingOutputStream(destination))) {
    zip.putNextEntry(new ZipEntry("note.txt"));
    zip.write("sample".getBytes(StandardCharsets.UTF_8));
    zip.closeEntry();
} // zip.close: finishes ZIP; adapter close only flushes destination.
~~~

This is also illustrative code; variables and imports must be supplied appropriately. The caller retains ultimate responsibility for flushing/closing `destination` when it owns it. Never make non-closing wrappers the default for every stream, as doing so can mask resource leaks.

If a method borrows a stream from a servlet/HTTP framework, check the framework's policy. Do not arbitrarily close an HTTP response output if the framework still needs to write other framing/headers/body data. Conversely, do not ignore a `finish` error in a compressed response: the client may receive a GZIP/ZIP missing its ending structure despite an HTTP success status.

## 11. finish Does Not Mean Flushed to Disk or Transactional

There are at least four independent milestones:

~~~text
Application writes content
          |
          v
Compression finish   -> archive/member has ending structure
          |
          v
Output buffer flush  -> bytes handed off to lower I/O layer
          |
          v
OS/storage sync      -> request durable write per storage contract
          |
          v
Application ACK      -> receiver/consumer business confirmation
~~~

The exact order depends on architecture, yet **no step automatically substitutes for the others**. Closing a ZIP stream finalizes the format and closes the file descriptor, but does not turn a series of multi-file updates into an atomic transaction. `FileChannel.force(true)` is designed to request syncing channel data/metadata, yet does not create an atomic transaction across multiple writes either.

If you need to produce a ZIP file safely for consumers:

1. Create a temporary file in the intended storage location.
2. Write contents through `ZipOutputStream`.
3. Finish and close the writer, handling any errors on finish/close.
4. If required, validate the archive and request durability via the appropriate storage API/layer.
5. Only when all requirements pass, publish the official filename, e.g., an atomic move **when supported by the platform**.

Do not treat atomic move as an absolute guarantee across all network filesystems or providers. If `finish()`/`close()` fails, dispose of the failed temp file and do not transition business metadata to a "completed" state.

## 12. Flush Over Sockets/HTTP: Does It Help Streaming?

Over a network, `GZIPOutputStream(..., true)` with syncFlush can help a consumer decompress bytes already received while the stream stays open. However, exact arrival timing at the peer still depends on the network stack, HTTP framing, TLS, flow control, and how the receiver reads. There is no promise that each flush produces one packet or that the consumer has seen a complete business message.

For ZIP, if the consumer format requires the central directory, never use `flush()` as a signal that "the downloaded ZIP is complete". Finish the archive before ending the response. Nor should you append unframed bytes after a ZIP/GZIP hoping readers will ignore the trailing data.

If a server sends multiple messages over one socket, design one of the following: length-prefixing, protocol-framed records, or a compressed container with explicit entries. Calling `finish()` on an object does not by itself define message boundaries for every protocol.

A performance measurement tip: flushing too frequently during compression can add overhead and degrade compression ratio; only enable syncFlush when streaming latency demands it, rather than habitually calling flush after every write.

## 13. Exception Handling: Successful write Does Not Guarantee Successful finish

The `finish()` and `close()` steps must also write additional metadata bytes, so they can throw `IOException`/`ZipException`. For instance, if the disk fills up right when writing the central directory, compressed entries may already be in the file, yet the ZIP is incomplete.

Wrong:

~~~java
try {
    zip.finish();
} catch (IOException ignored) {
    // Publishing ZIP even though finish failed: wrong.
}
~~~

This illustrates an **anti-pattern**. You must signal the error, clean up temporary files, and never transition state to success. With `try-with-resources`, Java still attempts to close when an exception occurs; an exception during close may surface as a *suppressed exception* if a primary error already occurred.

Resource limits are also advisable when decompressing archives from untrusted sources. GZIP/ZIP can exhibit abnormally high compression ratios; unbounded `ZipInputStream` reads can exhaust application RAM/time via decompression bombs. `ByteArrayOutputStream` in the demo is solely for small inputs to verify round-trip behavior; for large files use streaming and bound output size.

## 14. Typical Mistakes and How to Handle Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Only calling `zip.flush()` then publishing ZIP | Missing central directory | Call `zip.finish()` or `close()` |
| Only calling the final `closeEntry()` | Entry finished, archive not necessarily finished | Call `finish()` for the whole ZIP |
| Only calling `gzip.flush()` then reporting completion | GZIP trailer may be missing | Call `finish()`/`close()` |
| Calling `close()` when only borrowing destination | Closes caller-owned resource | Call `finish()` and follow ownership/non-closing adapter rules |
| Calling `finish()` then adding more ZIP entries | Violates archive lifecycle | Add all entries before finishing |
| Not guaranteeing closure of self-opened streams | Possible resource leaks and incomplete output | Use `try-with-resources` |
| Thinking `flush()` is fsync | Misunderstanding durability | Separate storage sync mechanism |
| Assuming flush equals client ACK | Client may not have received or processed data | Application acknowledgment protocol |
| Always enabling syncFlush | Increases overhead, reduces compression efficiency | Enable only when streaming latency requires it |
| Swallowing `IOException` from finish/close | Publishes corrupted archive | Report error and clean up |
| Using `ByteArrayOutputStream.close()` to test close propagation | BAOS close is a no-op | Use a tracking wrapper in tests |
| Feeding zlib bytes into a GZIP/ZIP reader | Wrong file format | Use the reader matching the format |
| Arbitrarily appending bytes after ZIP/GZIP | Non-portable | Define container/framing |

## 15. Self-Check Questions

1. Calling `zip.flush()` and then reading the ZIP with `ZipFile`: is reading the entire archive guaranteed? **No**, the central directory may not exist yet.
2. How do `closeEntry()` and `finish()` differ? **One finalizes the current entry; the other terminates the ZIP archive**.
3. Does `zip.finish()` close the destination stream? **No**.
4. Does `zip.close()` automatically finalize the ZIP if not yet finished? **Yes**, before closing the output.
5. Does `gzip.flush()` with `syncFlush=true` write the member-terminating CRC32/ISIZE trailer? **No**, `finish()`/`close()` is required.
6. What does a GZIP trailer contain? **CRC32 and ISIZE** of the uncompressed data (ISIZE modulo 2^32).
7. Can `putNextEntry()` be called after `zip.finish()`? **No**; the archive has already ended.
8. Should a method receiving a framework-managed output always close a `ZipOutputStream` wrapping that output directly? **Not by default**; follow ownership rules, using `finish` or a non-closing adapter.
9. In code creating its own ZIP file, is `try-with-resources` enough to finalize the archive and close the file? **Yes**, provided close succeeds.
10. Why can `finish` fail even if prior `write` calls succeeded? **Footer/central directory bytes still need to be written to the destination**.
11. Does `flush()` guarantee data is durable on an SSD? **No**; a separate durability contract is required.
12. Why did the demo need `TrackedOutput`? Because `ByteArrayOutputStream.close()` does not indicate whether the wrapper called close on the underlying stream.
13. Do `GZIPOutputStream` and `ZipOutputStream` produce the same byte format? **No**, even though both can use the DEFLATE algorithm.
14. Should a compressed file be considered valid if part of its payload decompresses? **No**, format completion and full validation per requirements are needed.
15. If multiple messages are needed over one socket, is finishing one ZIP/GZIP and appending more bytes enough? **No**, the protocol must define framing and compatible readers.

## API Reference Documentation

- [Java SE 17 — ZipOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipOutputStream.html): `putNextEntry`, `closeEntry`, `finish`, `close`.
- [Java SE 17 — GZIPOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPOutputStream.html): `finish`, `syncFlush` constructor, and GZIP metadata.
- [Java SE 17 — DeflaterOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/DeflaterOutputStream.html): `finish`, `flush`, `close`, and `Deflater.SYNC_FLUSH`.
- [Java SE 17 — OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): `flush()` and `close()` contracts.
- [Java SE 17 — ZipInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipInputStream.html), [ZipFile](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/ZipFile.html), [GZIPInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/zip/GZIPInputStream.html): reading and verifying formats.
