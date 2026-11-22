# Designing a Binary Record with Magic Number, Version, and Length in Java

## Lesson Objectives

A byte stream can contain a file, socket data, or multiple consecutive records. `InputStream` itself only provides bytes in order; it **does not inherently know which bytes belong to which record, what type a record is, or which version encoded it**. If you just write payloads and read by guesswork, a program will easily misalign positions, allocate the wrong memory, or misread data.

This lesson guides you through designing a binary record format with three leading fields:

1. **Magic number**: an identifier marking the data type/format.
2. **Version**: the structural version so the parser knows which rule set to apply.
3. **Length**: the byte count of the following payload, identifying record boundaries.

You will define an exact byte layout, encode and decode in Java 17+, handle malformed records, unsupported versions, and truncated payloads, and understand compatibility and safety boundaries.

## 1. Why Must a Clear Record Structure Exist?

Suppose an application needs to store or transmit the text message `Hi`, followed by another message. If it only writes the two UTF-8 bytes `48 69` and then writes the second payload, the reader cannot tell where the first message ends.

A fixed header answers several questions right at the start:

- **Magic number** provides a quick check: does this look like the right file/message type the parser expects?
- **Version** answers: which structural version should be used to interpret the following fields?
- **Length** answers: how many bytes must the parser read to finish the current payload?

This is called **framing** (wrapping data into frames). With TCP sockets, framing is especially vital: TCP carries a **continuous byte stream** and does not preserve the boundaries of each `write()` call or what the sender considers a message. A single `read()` may return a partial record, one record, or data from multiple records depending on timing and buffering.

## 2. Defining a Sample Protocol: JREC Version 1

Never arbitrarily write numbers to a stream before writing down a **formal byte contract**. Let us define a learning protocol named `JREC` as follows:

| Offset (bytes) | Byte Count | Field | Value / Rule |
| --- | ---: | --- | --- |
| `0..3` | 4 | `magic` | Four ASCII bytes `JREC`: hex `4A 52 45 43` |
| `4..5` | 2 | `version` | **Unsigned 16-bit** integer, big-endian; supports value `1` |
| `6..9` | 4 | `length` | **Signed 32-bit** integer, big-endian; must be in `0..1_048_576` |
| `10..(9 + length)` | `length` | `payload` | Exactly `length` UTF-8 bytes |
| Next | — | Next record or EOF | No padding/trailer in version 1 |

**Total size of each record = 10 + length bytes.** The header is always `10` bytes long; `length` counts **payload bytes**, excluding the header, and is not the number of Java `char`s or Unicode code points.

```text
   0                 3 4     5 6                 9 10
   +-------------------+-------+-------------------+---------------------+
   |  MAGIC "JREC"     | VER   | PAYLOAD_LENGTH    | PAYLOAD bytes ...   |
   |     4 bytes       |2 bytes|     4 bytes       |  length bytes       |
   +-------------------+-------+-------------------+---------------------+
     BE byte order for numeric header fields         UTF-8, no BOM
```

Specific conventions:

- Numeric fields in the header are **big-endian (network byte order)**. Both writer and reader must agree on this.
- Version only supports `1`; the parser **rejects** unknown versions. Do not guess new structures from old versions.
- `length` is encoded as a 32-bit `int` yet **capped at 1 MiB** by contract to prevent oversized payloads. Bounds must be checked **before allocating memory**.
- Version 1 payloads are **valid UTF-8**; a strict parser errors on invalid bytes rather than silently replacing them with replacement characters.
- A stream can consist of **multiple consecutive records**; each parser reads only the header + payload of the record it processes.
- Magic is solely a **format marker**, not a digital signature, checksum, or proof of sender authenticity.

For example, the text `Hi` has UTF-8 bytes `48 69`, meaning `length = 2`:

```text
Magic         Version  Length      Payload
4A 52 45 43 | 00 01 | 00 00 00 02 | 48 69
```

Concatenated without separators:

```text
4a5245430001000000024869
```

This is **12 bytes**: 4 magic + 2 version + 4 length + 2 payload. The `|` characters and spaces in the diagram are only for readability and are not present in the actual data.

## 3. Why Choose Magic, Version, and Length as Above?

### Magic number: quickly detecting the wrong input type

A magic number is typically an easily recognizable value in the opening bytes, such as four fixed ASCII bytes. With `JREC`, reading the wrong magic can mean:

- The user accidentally supplied a file of another format.
- The parser started at the wrong offset, perhaps due to reading too few or too many bytes earlier.
- The content was altered or corrupted.
- The stream does not adhere to the agreed protocol.

Do not rely on magic alone to conclude data is **definitely valid**: any sender can emit those four magic bytes. After checking magic, you still must validate version, length, payload, and other data constraints.

Magic can be written with `DataOutputStream.writeInt(0x4A524543)` because that API writes integers in **big-endian**. In other protocols, magic may also be written directly as four ASCII bytes. What matters is consistent byte layout across languages.

### Version: do not read new data as an old version

Version identifies the **wire format structure**, which does not necessarily match the application version. A version 1 parser knows the current payload is UTF-8; if in version 2 the payload changes to binary fields, a v1 parser must reject version 2 (unless designed to support it).

You should clearly specify:

- Which values are supported.
- When unsupported: fail with appropriate error information.
- Bump the version when a change is incompatible with old rules.
- If multiple versions must be read: branch parsers by version rather than using one single layout to "guess" all versions.

### Length: defining boundaries and preventing over-reads

The `length` field must explicitly specify whether it measures **bytes**, not characters; whether it counts **payload or the whole record**; whether negative values are forbidden; and whether there is a **maximum bound**.

In the sample protocol, `length` is the payload byte count `0..1_048_576`. Negative values or values above the threshold are rejected. You do not call `InputStream.available()` to find the length: `available()` only estimates bytes readable immediately without blocking, not total record length.

## 4. Java 17+: Writing and Reading a Complete Record

Java's `DataOutputStream` and `DataInputStream` fit well when a format has fixed big-endian numeric fields:

- `writeInt(int)`: writes four big-endian bytes.
- `writeShort(int)`: writes two big-endian bytes, taking the low 16 bits.
- `readInt()`: reads a full four big-endian bytes as an `int`.
- `readUnsignedShort()`: reads two bytes as a number `0..65535`.
- `readFully(byte[])`: reads the **exact number of bytes** matching the array length, or throws `EOFException` if the stream ends early.

**Save as `RecordProtocolDemo.java`:**

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class RecordProtocolDemo {
    private static final int MAGIC = 0x4A524543; // ASCII "JREC"
    private static final int VERSION = 1;
    private static final int MAX_PAYLOAD_BYTES = 1_048_576;

    static void writeRecord(OutputStream target, String text) throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_PAYLOAD_BYTES) {
            throw new IllegalArgumentException("payload too large");
        }

        // Do not close wrapper because target is owned by the caller.
        DataOutputStream out = new DataOutputStream(target);
        out.writeInt(MAGIC);
        out.writeShort(VERSION);
        out.writeInt(payload.length);
        out.write(payload);
        out.flush();
    }

    static String readRecord(InputStream source) throws IOException {
        DataInputStream in = new DataInputStream(source);

        int magic = in.readInt();
        if (magic != MAGIC) {
            throw new IOException("invalid magic");
        }

        int version = in.readUnsignedShort();
        if (version != VERSION) {
            throw new IOException("unsupported version");
        }

        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD_BYTES) {
            throw new IOException("invalid length");
        }

        byte[] payload = new byte[length];
        in.readFully(payload);

        // Strict decoding: malformed UTF-8 throws CharacterCodingException.
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(payload))
                .toString();
    }

    private static void expectFailure(String label, byte[] wire) {
        try {
            readRecord(new ByteArrayInputStream(wire));
            System.out.println(label + " = unexpectedly accepted");
        } catch (IOException e) {
            System.out.println(label + " = "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();
        writeRecord(destination, "Hi");
        byte[] wire = destination.toByteArray();

        System.out.println("wire = " + HexFormat.of().formatHex(wire));
        System.out.println("decoded = "
                + readRecord(new ByteArrayInputStream(wire)));
        System.out.println("total bytes = " + wire.length);

        byte[] badMagic = wire.clone();
        badMagic[0] = 0;
        expectFailure("bad magic", badMagic);

        byte[] badVersion = wire.clone();
        badVersion[5] = 2;
        expectFailure("unsupported version", badVersion);

        byte[] tooLarge = wire.clone();
        tooLarge[6] = 0x7F; // Length > MAX_PAYLOAD_BYTES.
        expectFailure("oversized length", tooLarge);

        byte[] truncated = Arrays.copyOf(wire, wire.length - 1);
        expectFailure("truncated payload", truncated);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac RecordProtocolDemo.java
java RecordProtocolDemo
```

Exact output:

```text
wire = 4a5245430001000000024869
decoded = Hi
total bytes = 12
bad magic = IOException
unsupported version = IOException
oversized length = IOException
truncated payload = EOFException
```

### Processing Flow Explanation

**Write (serialize):**

1. Convert `text` to UTF-8 bytes with `getBytes(StandardCharsets.UTF_8)`. Length comes from **`payload.length`**, not `text.length()`.
2. Check size limits before emitting the header.
3. Write magic, version, and length in order using the exact published byte widths.
4. Write the entire payload; `flush()` pushes data to the lower layer. It **does not prove** the data is durably persisted on disk or processed by the remote side.

**Read (deserialize):**

1. `readInt()` fetches all four magic bytes or throws `EOFException` when the header is incomplete.
2. `readUnsignedShort()` fetches version; if unsupported, reject it.
3. `readInt()` reads length; reject negative or out-of-bounds values **before calling `new byte[length]`**.
4. `readFully(payload)` retrieves the exact `length` bytes, even if the source returns fewer bytes per read. If payload bytes are missing, it throws `EOFException`.
5. Strict UTF-8 decoding: malformed data throws `CharacterCodingException` (a subclass of `IOException`).

The methods above do not close `source` or `target` themselves. In real applications, the class owning the stream controls its lifecycle, typically using `try-with-resources` where the file/socket is opened. This lets multiple records share one stream without being closed mid-way.

### Why Do the Error Test Cases Work?

- When modifying the first magic byte to `00`, the parser rejects a magic not matching `JREC`.
- When modifying the last byte of the version field at offset `5` to `02`, version becomes `2`, and the parser rejects it.
- When modifying the first byte of the length field at offset `6` to `7F`, length exceeds the 1 MiB cap. The program **does not allocate** a multi-billion-byte array.
- When trimming the last byte of the payload, the header still declares `length=2`, yet only one byte remains. `readFully` throws `EOFException` rather than pretending a valid record was received.

## 5. Why Can't a Single `read(byte[])` Be Used?

This is the **wrong** way to read exactly `length` bytes:

```java
// WRONG ILLUSTRATION; assumes existing InputStream in and int length.
byte[] payload = new byte[length];
int count = in.read(payload); // May read fewer than length bytes.
```

On files or TCP streams, a single `read` is **not guaranteed** to fill the array. Data can arrive in multiple parts; `count` can be smaller than `length` even before EOF.

For protocols requiring the full byte count:

```java
// Illustrative snippet: in is a DataInputStream, length has been safely validated.
byte[] payload = new byte[length];
in.readFully(payload); // Reads completely or throws EOFException.
```

Only call `readFully` after validating length and resource bounds. For large payloads that you do not want to hold entirely in RAM, use a loop reading chunks until total bytes read equals length. **Reading until EOF to determine the end of a record is wrong** if a connection can carry multiple records: EOF may only arrive when the connection closes, long after the current message finishes.

### Do Not Rely on `available()`

`available() == 0` does not mean a record has ended. It only indicates that at that moment no bytes are guaranteed to be immediately readable without blocking. Use the declared length field and verify read results instead of relying on `available()`, even when wrapping with `BufferedInputStream`.

## 6. Multiple Consecutive Records on the Same Stream

If data contains three records, the byte sequence is:

```text
[MAGIC | VERSION | LENGTH | PAYLOAD #1]
[MAGIC | VERSION | LENGTH | PAYLOAD #2]
[MAGIC | VERSION | LENGTH | PAYLOAD #3]
```

After `readRecord` finishes reading **exactly** `length` payload bytes, the stream position sits right before the next record's header. No separator is needed between records because length provides the boundary.

If the application already knows the record count (e.g., specified by an outer container header), it can call `readRecord` that exact number of times on the same `InputStream`. If the count is unknown and you want to stop when the stream ends, distinguish:

- **Clean EOF before starting a new header:** no more records remain.
- **Mid-stream EOF inside magic/version/length/payload:** data was truncated or incompletely transmitted; must report an error.

For example, `DataInputStream.readInt()` throws `EOFException` both when **zero bytes of magic were read** and when **only a few bytes of magic were read**. Therefore, do not catch every `EOFException` and treat it as normal termination.

One way to design a multi-record stream parser is to read the **first byte of magic**:

1. If the first byte returns `-1`, only then treat it as a clean EOF before a new record.
2. If the first byte was received, require all three remaining bytes of magic; any missing byte is a malformed record.
3. Then apply all version, length, and payload checks as above.

Do not let two `BufferedInputStream`s or two independent parsers compete over one source: the buffering layer may have read ahead into the next header's bytes.

## 7. Safe Length Validation and Preventing Over-Allocation

The length field is **data supplied by the sender or file**. Even with a magic check, data can be malicious or corrupted. Treat every header field as untrusted until validated:

| Risk | Mitigation |
| --- | --- |
| Negative length | Reject before creating an array. |
| Extremely large length | Set an application/protocol limit; reject before allocating. |
| Length smaller than actual payload | Parser treats leftover bytes as the next header; can cause bad magic or misaligned framing. Verify sender formatting. |
| Length larger than actual data | `readFully` throws `EOFException`; if a network stream hasn't hit EOF, it may block waiting for more bytes. |
| Header missing bytes | Report an incomplete record; do not read past into unrelated data. |
| Invalid UTF-8 bytes | Strict decoder reports an error. |
| Valid length but excessive total records | Add limits on record count, total bytes, time, or rate as appropriate. |

**Do not use `Files.size(path)` or remaining file bytes in place of each record's length**, unless the format genuinely specifies "one file contains only one payload". With multiple consecutive records, file size belongs to the whole container, whereas length belongs to each frame.

For large payloads, avoid allocating a full `byte[length]`. You can use a fixed buffer and a `remaining` counter:

```java
// ALGORITHM ILLUSTRATION, not a standalone runnable program.
// in: DataInputStream after reading header; out: target OutputStream; remaining = validated length.
byte[] buffer = new byte[8192];
while (remaining > 0) {
    int chunk = (int) Math.min(buffer.length, remaining);
    in.readFully(buffer, 0, chunk);
    out.write(buffer, 0, chunk);
    remaining -= chunk;
}
```

In this snippet, `remaining` is a `long` or `int` initialized with the validated length; `in` and `out` are managed by the caller. This approach avoids RAM usage proportional to payload size while still reading the **exact frame byte count**. It does not yet perform magic/version checks, checksums, or app-specific policies; those belong in the outer parser layer.

## 8. Byte Order, Charset, and Data Boundaries

### Big-Endian Must Be an Explicit Rule

`DataOutputStream.writeInt` and `DataInputStream.readInt` write/read big-endian integers, yet not every library, language, CPU, or custom `ByteBuffer` defaults the same way.

If the sender writes length `2` in little-endian (`02 00 00 00`) while the receiver reads big-endian, the value becomes `33_554_432` and may be rejected or cause huge allocations if unchecked. Therefore, the specification must declare endianness **for every numeric field**.

Do not "try flipping bytes" uncontrollably when a length looks wrong. When multiple representations look valid, guessing leads to parser ambiguity and security bugs. Byte order must be fixed by specification and version.

### UTF-8 Length Counts Bytes

The payload `"é"` has:

- One Unicode code point.
- One Java UTF-16 code unit (so `"é".length() == 1`).
- **Two UTF-8 bytes**: `C3 A9`.

Thus the length for this payload must be `2`, not `1`. For the emoji 😀, UTF-8 needs four bytes, whereas `String.length()` in Java returns `2` (a surrogate pair). When writing, **always encode first and take `payload.length`**.

### Do Not Confuse `writeUTF/readUTF` with the Protocol's UTF-8 Payload

`DataOutputStream.writeUTF(String)` uses a form of **modified UTF-8** with a leading 2-byte length and different encoding rules from standard UTF-8 for certain characters. `DataInputStream.readUTF()` is appropriate only when both sides deliberately use **`writeUTF`'s exact format**.

For JREC v1, the header already has a 4-byte length and the payload is standard UTF-8; **do not use `writeUTF/readUTF`** to replace `writeInt(payload.length)` + `write(payload)`. Doing so alters the layout and hinders cross-language compatibility.

## 9. Designing Versions for Evolution

A good format not only reads today's records, it also defines behavior when encountering tomorrow's data.

Examples of future scenarios:

- **Version 1:** UTF-8 text payload as in the example.
- **Version 2:** payload adds record type, timestamp, or checksum fields.
- **Version 3:** adds compression or structural variants.

If the byte meaning of the header changes, clearly specify **where version is read and when the parser branches**. In the example, v1 and future versions must keep magic and version position as part of the shared contract, or publish a new format-detection mechanism.

Evolution strategies:

1. **Increment version** when layout or field semantics change incompatibly.
2. **Keep a minimal header stable**, sufficient to select the right parser version.
3. **Place optional fields inside a structured payload** (e.g., TLV: type-length-value) when adding fields without breaking old data, while clearly defining types, endianness, duplicate fields, and how unknown fields are handled.
4. **Never automatically treat any higher version as compatible.** Skipping unknown fields is only safe if the protocol was designed to support it from the start.
5. **Keep canonical test vectors (golden bytes)** in cross-language test suites: the same string must produce the same bytes and decode back to the same value.

In all cases, changing the length field's byte width or unit is also a breaking protocol change: never alter it silently on one side.

## 10. Checksums, Authentication, and Stream Resynchronization

Magic + version + length handle **framing and identification**, yet do not guarantee integrity or authenticity.

- **Checksum/CRC** (e.g., CRC32) can detect many accidental byte corruptions; if added, specify whether it precedes or follows the payload, which bytes it covers, its endianness, and how parsers verify it. A CRC does not protect against an adversary who actively modifies data and recomputes the CRC.
- **MAC or digital signature** is a separate concern: used when the protocol must resist tampering and authenticate the sender. Key management and the authenticated data scope must follow the application's security model.
- **Magic does not guarantee stream resynchronization.** When a length is corrupted, the parser can land at the wrong offset. Scanning forward for magic bytes is only a heuristic; a byte sequence matching magic can legitimately appear inside a payload.
- **Write durability:** `flush()` is not equivalent to an atomic record commit or fsync. A process may crash between header and payload, leaving a truncated final record. Parsers must report mid-frame EOF; if atomic commits are required, a dedicated file/transaction design is needed.

For learning files or trusted data, the sample header suffices to understand framing. In production systems, choosing checksums, authentication, or compression must be driven by concrete needs and reflected in explicit version or flag fields.

## 11. Distinguishing Errors and How to Respond

| Detection | Likely Meaning | Recommended Handling |
| --- | --- | --- |
| Wrong magic | Wrong file type, wrong offset, corrupted data | Reject; log position and actual magic if safe. |
| Unsupported version | Newer format or outdated parser | Reject explicitly; upgrade parser if permitted. |
| Negative length | Invalid header | Reject before allocation. |
| Length over limit | Policy violation / resource-exhaustion attack | Reject; limit source and processed byte count. |
| EOF mid-header or mid-payload | Truncated file, incomplete transfer, closed connection | Report incomplete-frame error; do not treat as clean EOF. |
| Malformed UTF-8 | Payload violates protocol | Report strict decoding error. |
| Semantically invalid content despite valid framing | Payload violates business rules | Perform additional validation after decoding. |

Not every error can be fixed by trying to read more. With invalid magic/version/length, the parser may have lost boundary alignment; continuing to read blindly risks masking errors and misinterpreting subsequent data.

## 12. Common Mistakes to Avoid

1. **Formatting header numbers as text** such as `out.print(length)`: this writes text digits, not four big-endian bytes like `writeInt`.
2. **Leaving byte order unspecified**: two sides can interpret the same four bytes as two different numbers.
3. **Using `String.length()` as UTF-8 payload length**: wrong for many Unicode characters.
4. **Using `available()` to determine whether the full payload has arrived**: this does not measure total incoming bytes.
5. **Calling `read(payload)` once and assuming the array is full**: must loop until full or use `readFully`.
6. **Allocating `new byte[length]` before bounding length**: untrusted data can force huge allocations.
7. **Catching every `EOFException` as normal end-of-file**: header/payload might be only partially read.
8. **Using `writeUTF/readUTF` for standard UTF-8 payloads**: those APIs use modified UTF-8 and their own prefix.
9. **Assuming valid magic means the record is safe**: you still must check version, length, payload data, and business rules.
10. **Changing fields without changing version**: breaks older readers' understanding of the wire format.
11. **Reading until EOF for one record on a socket**: connections may stay open and carry multiple records; stop after exact `length` bytes.
12. **Neglecting stream lifecycle control**: closing a wrapper per record may close the connection needed for subsequent records.
13. **Forgetting TCP packets are not application records**: the number of `write` calls does not determine the number of `read` calls.
14. **Checking checksums without checking length bounds**: a checksum does not prevent over-allocation or reading past limits.

## 13. Self-Check Exercises

**1.** With a `JREC` v1 header and a payload of UTF-8 bytes `48 69`, what is the total byte size of the record?

**Answer:** `10 + 2 = 12` bytes; 10-byte header and 2-byte payload.

**2.** If sending payload `é` yet writing length as `"é".length()`, what bug occurs?

**Answer:** Length is written as `1` while the UTF-8 payload is `2` bytes. The parser under-reads the payload, leaving a leftover byte that misaligns the next record's header.

**3.** Why must version be checked *before* parsing the payload?

**Answer:** Payload structure depends on version. A v1 parser must not blindly apply v1 rules to new-version bytes without knowing compatibility.

**4.** When `readFully(payload)` throws `EOFException`, should the partially read payload be returned as a valid record?

**Answer:** No. The published protocol requires all `length` bytes; a short record must raise an error and cannot be treated as complete.

**5.** Does a magic number prevent a sender from forging a record?

**Answer:** No. Magic only marks the data type. Authenticating the source and resisting intentional tampering require purpose-built cryptographic authentication.

**6.** Why shouldn't a multi-record stream parser close `InputStream` right after each `readRecord`?

**Answer:** Because all records may share the same source. Closing the stream after the first record prevents reading subsequent records.

**7.** If the sender writes a little-endian length while the reader uses `DataInputStream.readInt()`, what happens?

**Answer:** The parser may receive the wrong length value, leading to misreads or rejection by bounds checks. Both sides must agree on byte order in the specification.

## Summary

A binary record with **magic number + version + length + payload** is trustworthy only when backed by an **explicit byte contract**: field positions/sizes, byte order, length units, charset, bounds, and error-handling rules.

With Java 17+, `DataOutputStream`/`DataInputStream` handle big-endian numeric fields. Validate magic, version, and length **before allocating**, read the exact payload with `readFully`, distinguish clean EOF from truncated records, and verify content and version compatibility. As system demands grow, consider checksum/authentication mechanisms and versioning strategies rather than silently mutating the v1 format.
