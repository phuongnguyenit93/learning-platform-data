# Practice: Designing a Versioned and Length-Prefixed Binary Format in Java

## 1. Problem Statement and Goals

Suppose a Java application needs to store thousands of records in a binary file or transmit them sequentially over TCP. Each record has an identifier and a name; in a newer version, records also carry a priority. We need a format that lets the program:

- Determine the **boundary** of each record without guessing delimiter bytes.
- Know the **structure version** to decode the fields accurately.
- Read multiple records sequentially from the same file/TCP stream.
- Detect invalid, truncated, or checksum-mismatched input.
- Enforce size limits before allocating memory.
- Follow a clear policy when encountering a record with an unsupported version.
- Interoperate across processes/JDKs without relying on default Java class serialization.

This is a **binary protocol design** and **record framing** problem. Do not simply write a sequence of integers/strings and expect the reader to guess where each record ends.

~~~text
Binary file or TCP stream
  |
  +-- [HEADER record 1][PAYLOAD 1][CHECKSUM 1]
  +-- [HEADER record 2][PAYLOAD 2][CHECKSUM 2]
  +-- [HEADER record 3][PAYLOAD 3][CHECKSUM 3]
                 |
                 v
        Per-frame parser
                 |
       validate -> decode by version
~~~

**The version + length pair answers two distinct questions:**

- **Version:** Which structure should be used to interpret the bytes inside the payload?
- **Length:** Where do the bytes of the current frame end and where does the next frame begin?

Version does not replace length, and length alone does not tell the decoder what structure the inner data has.

## 2. First, Write the Byte Format Specification

A good protocol is not just Java code. It must precisely specify **field order, lengths, byte order, encoding, limits, and error conditions**. Let us define an illustrative format named `JBIN`:

| Offset in frame | Length | Field | Rule |
| ---: | ---: | --- | --- |
| 0 | 4 bytes | `magic` | ASCII `JBIN`, equivalent to hex `4A 42 49 4E` |
| 4 | 1 byte | `version` | Unsigned integer 0–255; supports versions 1 and 2 |
| 5 | 4 bytes | `payloadLength` | Signed 32-bit integer, **big-endian**, accepts only 0 to 65,536 |
| 9 | `payloadLength` bytes | `payload` | Structure determined by version |
| 9 + length | 4 bytes | `crc32` | CRC-32 value **of the payload only**, written as 32-bit big-endian |

Total length of one frame:

\[
\mathrm{frameBytes} = 4 + 1 + 4 + \mathrm{payloadLength} + 4
= 13 + \mathrm{payloadLength}.
\]

Byte diagram:

~~~text
      4B       1B          4B                 L bytes         4B
+-----------+---------+--------------+-----------------------+----------+
|   JBIN    | version | payloadLength|       payload         |  CRC32   |
+-----------+---------+--------------+-----------------------+----------+
  magic       u8          i32 BE        bytes per version       u32 BE

Frame 1 | Frame 2 | Frame 3 | ... | EOF at frame boundary
~~~

This is a **custom format designed for practice**, not a JDK standard. Two programs in different languages can still exchange data if they follow the same specification.

### Why Is Magic Needed?

Magic helps detect malformed input early. If the first four bytes do not equal `JBIN`, the parser rejects the stream before interpreting length or payload.

Magic is **not security authentication** and does not guarantee automatic resynchronization when a file is corrupted. Blindly scanning for the byte sequence `JBIN` inside payloads can mistake data bytes for a real header. When recovery is needed, build explicit resynchronization/commit/index mechanisms with clear rules.

### Why Use a Fixed-Size Integer Length?

Length-prefixing allows locating the next frame without separator characters. This is vital for binary payloads, where every byte value from 0 to 255 can be valid.

However, never trust a length value coming from a file or network. Four bytes can be interpreted as a negative number or billions of bytes. **Validate bounds before allocating `new byte[length]`.**

In this exercise, the limit is 65,536 bytes **per payload**, not the total file size. Production systems need a maximum appropriate for business requirements, memory, and concurrent connections.

## 3. Designing the Payload by Version

Deliberately choose two different versions:

### Version 1

~~~text
+------------+----------------+-----------------------+
| id: i32 BE | nameLen: u16 BE| nameUtf8: nameLen B   |
+------------+----------------+-----------------------+
     4B             2B             0..65535 B
~~~

For example, a message with `id=7` and `name="Alpha"`. The name is encoded in **UTF-8**, and `nameLen` is the **UTF-8 byte count**, not `String.length()`.

### Version 2

Keep the v1 fields intact and **append at the end of the payload** a `priority` integer:

~~~text
+------------+----------------+----------------------+------------------+
| id: i32 BE | nameLen: u16 BE| nameUtf8: nameLen B | priority: i32 BE |
+------------+----------------+----------------------+------------------+
     4B             2B            n bytes                4B
~~~

For version 2, the decoder must read exactly four additional bytes for priority. If fewer than four bytes remain, the frame is invalid. If the decoder encounters unspecified trailing bytes, **do not silently ignore them** for a known version: the sender may have encoded the wrong schema or the parser may be misaligned.

### Unsupported Versions

If a reader currently supports versions 1 and 2 and encounters version 99:

- It **still reads and bounds-checks length** per the common header.
- It **reads and validates the entire frame** according to the common rules it understands.
- It **does not guess** the structure of a version 99 payload.
- It may **skip the frame intact** and move on to the next frame, if the protocol policy permits; or **reject the entire file/connection** if every message must be understood.

Both policies can be valid. Skipping is only valid when each frame is self-contained and carries no state that alters the meaning of subsequent frames. If a new version changes the **common header layout**, an older reader may not be able to skip it; in that case, protocol negotiation or a container-level file-format major version is required.

## 4. Byte Order: Java Must Write and Read Consistently

For multi-byte integers, byte order (*endianness*) must be specified. We choose **big-endian**:

~~~text
Int value 0x01020304
Big-endian:    01 02 03 04
Little-endian: 04 03 02 01
~~~

`DataOutputStream.writeInt()` and `DataInputStream.readInt()` use **big-endian** order. `writeShort/readUnsignedShort` also exchange bytes from most significant to least significant.

`ByteBuffer` defaults to big-endian, though it can be switched with `order(ByteOrder.LITTLE_ENDIAN)`; do not assume a `ByteBuffer` passed from other code still retains the default byte order. If implementing the same format with `ByteBuffer`, explicitly call `buffer.order(ByteOrder.BIG_ENDIAN)`.

A C/Python/Go reader must follow the same endianness. Never dump raw native C `struct` layouts and assume C padding/alignment matches Java.

### Unsigned vs. Signed

- Version: 1 unsigned byte; Java uses `readUnsignedByte()` to get 0..255.
- `nameLen`: 2 unsigned bytes; Java uses `readUnsignedShort()` to get 0..65,535.
- `payloadLength`: 4 signed bytes. We specify **0..65,536 as valid**; negative or above the ceiling is an error.
- CRC32: 32-bit pattern, written via `writeInt((int) crc.getValue())` and compared by bit pattern on read.

Java `byte` is signed; when printing a byte in hex, use `value & 0xFF` to avoid sign extension.

## 5. UTF-8 and String Length Pitfalls

For example, `"A"` is 1 UTF-16 char and 1 UTF-8 byte. `"Đ"` is 1 UTF-16 code unit yet **2 UTF-8 bytes**; non-BMP characters can require 4 UTF-8 bytes and 2 UTF-16 code units.

Therefore, never do this:

~~~java
out.writeShort(name.length()); // WRONG if length must be UTF-8 byte count
out.write(name.getBytes(StandardCharsets.UTF_8));
~~~

The snippet above illustrates the bug. Correct approach:

~~~java
byte[] encodedName = name.getBytes(StandardCharsets.UTF_8);
if (encodedName.length > 65535) {
    throw new IOException("Name too long");
}
out.writeShort(encodedName.length);
out.write(encodedName);
~~~

`writeShort` writes the low 16 bits; **it does not automatically reject** names longer than 65,535 bytes per the protocol intent, so you must check beforehand.

Do not use `DataOutputStream.writeUTF()` as an arbitrary substitute for the format just designed. That method uses **modified UTF-8** with Java-specific framing and limits; it is not equivalent to this specification's "u16 length + standard UTF-8". For cross-language compatibility, write standard UTF-8 bytes together with an explicit length.

The decoder also needs a policy for malformed UTF-8. `new String(bytes, UTF_8)` can substitute invalid bytes with replacement characters; if the protocol requires **rejecting corrupted UTF-8**, use `CharsetDecoder` with `CodingErrorAction.REPORT`.

## 6. Why Need a Checksum? What Does CRC32 Verify?

We add CRC-32 to detect **many forms of accidental byte corruption** in the payload, such as storage or transmission errors. CRC32 is not encryption, has no secret key, and **does not defend against intentional tampering**: an attacker can modify the payload and recompute the CRC.

Example:

~~~text
Original payload   → CRC32 0x12345678 (illustrative value)
One byte altered   → Recomputed CRC32 usually differs
Reader compares stored CRC with recomputed CRC → reports error
~~~

In this exercise's format, CRC **protects only the payload**, not magic/version/length. The parser still validates the header and length bounds, though if business requirements demand detecting header tampering or authenticating the data source, add a checksum covering the appropriate fields or use cryptographic authentication such as MAC/AEAD.

For very large frames, CRC can be computed incrementally while streaming chunks without holding the entire payload in RAM. In the example below, since `MAX_PAYLOAD` is only 65,536 bytes, holding each frame's payload in a single array is reasonable for demonstration.

## 7. Complete Java 17+ Program: Writing and Reading Three Frames

The example below builds a serializer/deserializer with `DataOutputStream` and `DataInputStream`. It writes three frames to a byte stream:

1. Version 1 containing `id=7`, `name="Alpha"`.
2. Version 99, a frame whose **payload is unknown**, yet has a valid header/length/CRC, to test the skip policy.
3. Version 2 containing `id=8`, `name="Beta"`, `priority=42`.

Afterward, the program intentionally truncates one frame and flips one payload byte to test both error modes. All tests use in-memory byte arrays so stdout does not depend on the filesystem or wall-clock time.

Save as `VersionedBinaryFormatDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.zip.CRC32;

public class VersionedBinaryFormatDemo {

    private static final int MAGIC = 0x4A42494E; // ASCII "JBIN"
    private static final int MAX_PAYLOAD = 65_536;

    record Frame(int version, byte[] payload) {}

    record Message(int id, String name, Integer priority) {}

    static byte[] encodeMessage(
            int version, int id, String name, Integer priority)
            throws IOException {

        if (version != 1 && version != 2) {
            throw new IllegalArgumentException("Unsupported writer version");
        }
        if (version == 2 && priority == null) {
            throw new IllegalArgumentException("V2 needs priority");
        }

        byte[] nameBytes = name.getBytes(StandardCharsets.UTF_8);
        if (nameBytes.length > 65_535) {
            throw new IOException("Name length exceeds u16");
        }

        ByteArrayOutputStream raw = new ByteArrayOutputStream();
        try (DataOutputStream payload = new DataOutputStream(raw)) {
            payload.writeInt(id);
            payload.writeShort(nameBytes.length);
            payload.write(nameBytes);
            if (version == 2) {
                payload.writeInt(priority);
            }
        }

        byte[] result = raw.toByteArray();
        if (result.length > MAX_PAYLOAD) {
            throw new IOException("Payload exceeds maximum");
        }
        return result;
    }

    static void writeFrame(
            DataOutputStream out, int version, byte[] payload)
            throws IOException {

        if (version < 0 || version > 255
                || payload.length > MAX_PAYLOAD) {
            throw new IOException("Invalid version or payload size");
        }

        CRC32 crc = new CRC32();
        crc.update(payload);

        out.writeInt(MAGIC);
        out.writeByte(version);
        out.writeInt(payload.length);
        out.write(payload);
        out.writeInt((int) crc.getValue());
    }

    static Frame readFrame(DataInputStream in) throws IOException {
        // Valid EOF ONLY when no bytes of the next header have been read yet.
        int first = in.read();
        if (first == -1) {
            return null;
        }

        int magic = (first << 24)
                | (in.readUnsignedByte() << 16)
                | (in.readUnsignedByte() << 8)
                | in.readUnsignedByte();
        if (magic != MAGIC) {
            throw new IOException("Invalid magic");
        }

        int version = in.readUnsignedByte();
        int length = in.readInt();

        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("Invalid payload length");
        }

        byte[] payload = new byte[length];
        in.readFully(payload); // EOF mid-payload => EOFException.

        int storedCrc = in.readInt(); // EOF mid-trailer => EOFException.
        CRC32 calculated = new CRC32();
        calculated.update(payload);

        if ((int) calculated.getValue() != storedCrc) {
            throw new IOException("CRC32 mismatch");
        }
        return new Frame(version, payload);
    }

    static Message decodeMessage(Frame frame) throws IOException {
        if (frame.version() != 1 && frame.version() != 2) {
            throw new IOException("Unknown message schema");
        }

        try (DataInputStream payload = new DataInputStream(
                new ByteArrayInputStream(frame.payload()))) {

            int id = payload.readInt();
            int nameLength = payload.readUnsignedShort();
            int extraBytes = frame.version() == 2 ? 4 : 0;

            if (nameLength > payload.available() - extraBytes) {
                throw new IOException("Invalid name length");
            }

            byte[] nameBytes = new byte[nameLength];
            payload.readFully(nameBytes);

            String name = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(nameBytes)).toString();

            Integer priority =
                    frame.version() == 2 ? payload.readInt() : null;

            if (payload.available() != 0) {
                throw new IOException("Unexpected trailing payload bytes");
            }

            return new Message(id, name, priority);
        }
    }

    public static void main(String[] args) throws IOException {
        ByteArrayOutputStream destination = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(destination)) {
            writeFrame(out, 1,
                    encodeMessage(1, 7, "Alpha", null));
            writeFrame(out, 99, new byte[] {1, 2, 3});
            writeFrame(out, 2,
                    encodeMessage(2, 8, "Beta", 42));
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(destination.toByteArray()))) {
            Frame frame;
            while ((frame = readFrame(in)) != null) {
                if (frame.version() != 1 && frame.version() != 2) {
                    System.out.println(
                            "unknown version=" + frame.version()
                                    + " skipped");
                    continue;
                }

                Message message = decodeMessage(frame);
                String priority = message.priority() == null
                        ? "n/a"
                        : message.priority().toString();

                System.out.println("v" + frame.version()
                        + ": id=" + message.id()
                        + " name=" + message.name()
                        + " priority=" + priority);
            }
        }

        ByteArrayOutputStream one = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(one)) {
            writeFrame(out, 1,
                    encodeMessage(1, 1, "Test", null));
        }

        byte[] original = one.toByteArray();

        // Simulate a file truncated by two bytes at the end of the CRC.
        byte[] truncated = Arrays.copyOf(
                original, original.length - 2);
        boolean truncationDetected = false;
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(truncated))) {
            readFrame(in);
        } catch (EOFException expected) {
            truncationDetected = true;
        }
        System.out.println(
                "truncated detected=" + truncationDetected);

        // Header is 9 bytes; first byte of payload is at offset 9.
        byte[] corrupted = original.clone();
        corrupted[9] ^= 1;
        boolean crcDetected = false;
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(corrupted))) {
            readFrame(in);
        } catch (IOException ex) {
            crcDetected = "CRC32 mismatch".equals(ex.getMessage());
        }
        System.out.println("crc mismatch detected=" + crcDetected);
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac VersionedBinaryFormatDemo.java
java VersionedBinaryFormatDemo
~~~

Stdout:

~~~text
v1: id=7 name=Alpha priority=n/a
unknown version=99 skipped
v2: id=8 name=Beta priority=42
truncated detected=true
crc mismatch detected=true
~~~

### Step-by-Step Program Analysis

**Step 1 — Write payload:** `encodeMessage` constructs a byte array per the v1/v2 schema: `id`, `nameLen` and UTF-8 bytes, plus `priority` if v2. It validates that `nameLen` and total payload do not exceed limits.

**Step 2 — Write frame:** `writeFrame` writes magic, version, length, payload, and CRC32. `DataOutputStream` enforces big-endian for multi-byte integers. Each call produces one frame with explicit boundaries.

**Step 3 — Read header:** `readFrame` allows returning `null` **only when EOF occurs right at the start of the next frame**. If 1–3 bytes of magic remain or version/length are incomplete, `readUnsignedByte`/`readInt` throw `EOFException`; that is truncated data, not a valid end.

**Step 4 — Guard allocation:** `length < 0` or `length > MAX_PAYLOAD` is rejected **before** `new byte[length]`. The parser does not trust a peer-supplied length.

**Step 5 — Read payload and CRC:** `readFully` requires reading all `length` bytes; `readInt` requires the complete trailer. A recomputed CRC32 differing from the stored checksum throws `IOException`.

**Step 6 — Branch by version:** `decodeMessage` understands only v1/v2. Version 99 has already had its entire frame read and CRC verified, so it can be skipped as an independent unit; the subsequent v2 frame still reads cleanly.

**Step 7 — Validate internal payload schema:** The decoder uses `readUnsignedShort` for name length, checks that enough bytes remain for the name **and the priority field if v2**, decodes UTF-8 strictly, and then requires zero trailing bytes.

**Step 8 — Test corrupted data:** Truncating the last two CRC bytes raises `EOFException`. Flipping one payload byte while keeping the CRC trailer raises `IOException` with message `CRC32 mismatch`. None of this depends on network timing or thread ordering.

The example intentionally uses `ByteArrayInputStream` for reproducible results. When moving to real files or sockets, the framing logic stays identical while buffering, I/O handling, and lifecycle adapt to the source.

## 8. Design Decisions to Lock Down Before Implementation

### File-Level Header or Per-Record Header?

Two models can be chosen:

**Model A — single header for the entire file:**

~~~text
[FILE_MAGIC][FILE_FORMAT_VERSION]
[RECORD_LENGTH][RECORD]
[RECORD_LENGTH][RECORD]
...
~~~

Suitable when the entire file always shares one schema/format or when the application wants to negotiate a file version before reading content. The reader must know whether every record shares one version or carries its own type/version.

**Model B — header per frame**, as in this exercise:

~~~text
[MAGIC][VERSION][LENGTH][PAYLOAD][CRC]
[MAGIC][VERSION][LENGTH][PAYLOAD][CRC]
...
~~~

Suitable when record versions can be mixed or frames appended independently. In return, header and CRC overhead repeat per record.

There is no single right choice for every application. What matters is a **consistent specification** and frame independence if unknown versions are to be skipped.

### Protocol-Level Version or Payload-Level Version?

A **protocol major version** can describe the common header syntax; a **payload schema version** describes the fields inside a message type. In the example both share a single `version` byte because the format is simple.

If later you want to change the frame structure itself (for instance, 32-bit length to 64-bit length), old readers will not necessarily recognize boundaries anymore. Treat that as a **major protocol change**, not just bumping a payload version from 2 to 3.

### Are Type and Flags Needed?

If a file holds multiple record types, the header can be extended to:

~~~text
[MAGIC][FORMAT_VERSION][RECORD_TYPE][FLAGS][PAYLOAD_LENGTH][PAYLOAD][CRC]
~~~

Then the specification must additionally define:

- Valid type/flag values.
- Whether unknown types/flags may be skipped.
- Which flags a reader must understand to decode the payload properly.
- Reserved future bits and ordering of compression/encryption.
- Maximum decompressed size if payloads are compressed.

Never add types/flags casually while forgetting to update the parser and compatibility tests.

## 9. `DataInputStream` vs. `ByteBuffer`/`FileChannel`

Java offers several levels of abstraction:

| Tool | When Useful? | Points to Watch |
| --- | --- | --- |
| `DataOutputStream` / `DataInputStream` | Writing/reading primitives on OutputStream/InputStream | Big-endian; `readFully` pairs well with frame length |
| `ByteBuffer` | Packing/unpacking bytes from arrays/direct buffers | Must manage `position/limit/flip` and byte order |
| `FileChannel` | Random access, reading/writing by offset for large files | `read`/`write` can transfer partial amounts; must check in a loop |
| Non-blocking `SocketChannel` | Network protocols with Selector | Can return 0 bytes; state machine must accumulate header/payload across passes |
| `BufferedInputStream` | Reduces small I/O calls when reading streams | Does not alter protocol framing |
| `CRC32` | Detects many random byte errors | Not authentication/tamper protection |

In the demo, `DataInputStream` fits well because `readFully` blocks/reads all requested bytes or throws EOF. With a non-blocking `SocketChannel`, you must not assume a single `read(buffer)` returns all 9 header bytes or the full payload. A **state machine** is needed:

~~~text
NEED_HEADER
    |
    | received all 9 bytes
    v
VALIDATE_LENGTH
    |
    | valid length, allocate bounded buffer
    v
NEED_PAYLOAD_AND_CRC
    |
    | received all length + 4 bytes
    v
VERIFY_CRC
    |
    v
DECODE_OR_SKIP
    |
    v
NEED_HEADER (next frame)
~~~

A TCP request may be split across multiple packets, or multiple frames may arrive in a single `read`. Length-based framing clarifies how to accumulate bytes regardless of packet boundaries.

## 10. Very Large Files: Stream Frame by Frame

A file may be tens of gigabytes while each frame is only a few kilobytes. Do not use `Files.readAllBytes` to load the whole file just because the format is binary.

With `InputStream`/`DataInputStream`, the parser can read one frame at a time and process it immediately. With `FileChannel`, you can read into a bounded buffer, track offsets, and parse incrementally.

Rules:

- **Cap payload per frame**, total frame count, and total bytes processed as required.
- Never allocate `new byte[fileSize]`; process frame by frame.
- Protect concurrent frame counts when multiple clients send data.
- Do not pass references to reusable buffers into asynchronous jobs without clear ownership.
- Track bytes read, frames rejected, and failure reasons for observability.
- When a genuinely huge frame requires streaming, compute CRC incrementally and use bounded input so you do not read past into the next frame.

In the example, we use a maximum payload buffer of 65,536 bytes, small enough to demonstrate standalone without gigabyte-handling machinery.

## 11. Truncation, Crashes, and Append Protocols

There is an important distinction between a **valid EOF** and a **file truncated mid-record**:

~~~text
Valid:
[complete frame 1][complete frame 2][EOF]

Invalid:
[complete frame 1][half header of frame 2][EOF]

Invalid:
[complete frame 1][header of frame 2][half payload][EOF]
~~~

Hence `readFrame` returns `null` only when **zero bytes of the next frame have been read**. Once any header byte has been seen, missing remaining data must be an error—or a wait state for more bytes if reading from an open network stream.

If an application appends records to a file and suffers power loss or a JVM crash mid-write, the file can end with an incomplete frame. Common production strategies:

1. Read complete frames from the start and record the **last valid commit offset**.
2. If the tail is truncated, reject the entire file or quarantine the partial tail per policy.
3. For append-only log structures, recovery can **truncate back to the last valid offset**, but only after independent verification, ensuring no other writer is active, and with proper state persistence.
4. If durability is required, use `FileChannel.force(...)` per policy and account for write ordering, metadata, and filesystem behavior.
5. If atomic whole-file updates are needed, consider writing a complete temporary file and moving/renaming on the same filesystem, keeping in mind `ATOMIC_MOVE` support depends on the provider.

**A length-prefix does not by itself turn multiple writes into an atomic transaction.** It helps detect incomplete records; recovery and durability are separate decisions.

## 12. Compatibility: Backward, Forward, and Schema Evolution

Three scenarios require independent testing:

| Scenario | Expectation If Supported by Design |
| --- | --- |
| New reader reads v1 record | Readable using v1 decoder |
| New reader reads v2 record | Readable using v2 decoder |
| Old reader encounters v2/v99 record | Safely skipped if protocol allows; otherwise clear error |

### Backward Compatibility

A new reader can understand older versions. In the demo, the decoder handles v1 and v2. This is the **ability to read older data**; it does not imply every old writer understands data produced by a new writer.

### Forward Compatibility

An older reader can tolerate newer changes within specified bounds. For example, the parser reads length, verifies checksum, and **skips unknown versions** to continue to the next frame. However, if an unknown frame mutates state—such as configuring a dictionary or encryption for subsequent frames—skipping may be **unsafe**.

### Migrations and Defaults

If v1 records must map onto a new data model, one option is choosing a sensible default for `priority` when reading v1, or leaving it `null` to mean "absent". **Do not use 0 as a default without documenting semantics**, because 0 might be a valid priority level.

Similarly, when dropping a field in v3, document explicitly what schema v1/v2/v3 represent, rather than treating all bytes after the name as an unmarked optional field.

## 13. Safety Against Untrusted Input

A binary parser must assume files/inputs may be corrupted or crafted by an untrusted peer. Safe processing order:

1. **Check magic** before interpreting payload.
2. **Read bounded version** and enforce the unknown-version policy.
3. **Validate length**: non-negative, within max, and no integer overflow when computing `header + length + trailer`.
4. **Bound allocations** before creating buffers.
5. **Read exact length completely** and treat mid-frame EOF as an error.
6. **Verify checksum** over the exact defined byte range.
7. **Validate internal schema**, string/array lengths, and valid UTF-8.
8. **Reject trailing bytes** if the known schema version forbids them.
9. **Cap total load**: frame count, rate, deadlines, nesting, connection count, memory budget, and CPU.
10. **Do not treat CRC as authentication**: if guarding against forged tampering, use MAC/AEAD/signatures under a secure protocol.

In particular, this code:

~~~java
int length = in.readInt();
byte[] payload = new byte[length]; // DANGEROUS if unchecked
~~~

is an anti-pattern. A negative length causes an allocation exception; a huge length can cause `OutOfMemoryError`. In the demo, `MAX_PAYLOAD` is checked before allocation. In production, you must also limit how many frames are held concurrently.

### Nested Lengths

A frame already has `payloadLength`, yet the payload itself may contain `nameLen`, `arrayLength`, or element lists. **Every nested length** must be validated against remaining bytes and business limits; do not assume every field inside the payload is valid just because the outer frame passed.

For instance, the demo decoder asserts `nameLength <= remaining - extraBytes`. If adding a list of child records, the parser must cap the count and check required bytes before looping or allocating.

## 14. `ByteBuffer`: Brief Example of a Big-Endian Header

To build the header with `ByteBuffer` instead of `DataOutputStream`:

~~~java
ByteBuffer header = ByteBuffer.allocate(9)
        .order(ByteOrder.BIG_ENDIAN);

header.putInt(0x4A42494E); // "JBIN"
header.put((byte) 1);      // version
header.putInt(123);       // payloadLength

header.flip();             // Prepare for channel.write(header)
~~~

This is an **illustrative snippet**; import `java.nio.ByteBuffer` and `java.nio.ByteOrder`, and note it does not send data by itself.

`flip()` is essential: after `put`, position sits at the end of the written region; if you forget `flip` and call `channel.write(header)`, it may send 0 bytes or unwanted data. On a non-blocking `SocketChannel`, even after `flip`, `write` may send only part of the header; retain the buffer until fully sent.

Reader side with `ByteBuffer`:

~~~java
header.order(ByteOrder.BIG_ENDIAN);
int magic = header.getInt();
int version = Byte.toUnsignedInt(header.get());
int length = header.getInt();
~~~

Call `get` methods only after **all 9 bytes have been received**; otherwise `BufferUnderflowException` may occur. Read and validate length before allocating the payload buffer. These bytes match the `DataInputStream` demo specification.

## 15. Common Mistakes

**Mistake 1 — No length-prefix.** When concatenating multiple binary records, the parser cannot tell boundaries apart. Fix: specify length-based framing or another strict framing mechanism.

**Mistake 2 — Length without version.** When adding a field, older parsers misinterpret bytes. Fix: schema version and compatibility policy.

**Mistake 3 — Forgetting to specify byte order.** Java, C, and OSes can use different representations. Fix: define big-endian/little-endian in the spec and test raw bytes.

**Mistake 4 — Using `String.length()` as UTF-8 length.** Multi-byte characters shift the reader's offsets. Fix: encode UTF-8 first, then write byte length.

**Mistake 5 — Using `writeUTF/readUTF` for a standard UTF-8 protocol.** That uses modified UTF-8 with its own framing. Fix: write u16/u32 byteLength followed by standard UTF-8 bytes.

**Mistake 6 — Allocating from an unchecked length.** Can create giant or negative-sized arrays. Fix: range-check before allocation.

**Mistake 7 — Treating mid-payload EOF as valid end of file.** That is a truncated frame. Fix: distinguish boundary EOF from mid-frame EOF.

**Mistake 8 — Reading an unknown version with a similar schema.** Can completely misparse data. Fix: skip the entire frame if allowed by protocol, or fail clearly.

**Mistake 9 — Failing to check trailing bytes on a known schema.** Parser may accept records encoded with the wrong schema. Fix: require payloads to be consumed completely for fixed versions.

**Mistake 10 — Thinking CRC protects against malicious tampering.** CRC32 is not a MAC. Fix: use cryptographic authentication if attackers exist.

**Mistake 11 — Assuming one TCP read returns a full frame.** TCP is a byte stream; use a state machine to accumulate header and payload.

**Mistake 12 — Not testing multiple consecutive frames.** Parser may overrun into the next frame or fail to reset state properly. Fix: round-trip multiple versions, unknown versions in the middle, final frame, EOF, and corrupted inputs.

## 16. Practice Exercises and Self-Check Questions

### Exercise 1 — Reading Bytes per Specification

Given header:

~~~text
4A 42 49 4E 01 00 00 00 0B
~~~

Determine:

- Magic: **`JBIN`**.
- Version: **1**.
- Payload length: **11 bytes**.
- Total frame length per the lesson layout: **13 + 11 = 24 bytes**, including the 4-byte trailing CRC32.

This is only the **header**; without the accompanying payload and CRC, you cannot conclude the whole frame is valid.

### Exercise 2 — Version 1 and Version 2

If v1 has id=7 and name `"Alpha"`:

- id: 4 bytes.
- name length: 2 bytes.
- UTF-8 `Alpha`: 5 bytes.
- Total v1 payload: **11 bytes**.
- Total frame: **24 bytes**.

If v2 has the same name/id plus an i32 priority, the payload is **15 bytes** and the frame is **28 bytes**. Never substitute Java char count for UTF-8 byte count when non-ASCII characters appear.

### Exercise 3 — Adding a Message Type

Add a type field to the header: shared version, 1-byte type, 4-byte length. You need to:

1. Update header size from 9 to 10 bytes.
2. Rewrite encoder/decoder symmetrically.
3. Decide whether unsupported types must be skipped or rejected.
4. Decide how to distinguish files using the old header from the new header (e.g., changing format major version or magic) rather than silently misreading.

### Exercise 4 — Invalid Length Cases

Write tests for `payloadLength = -1`, `65_537`, `0`, `65_536`. In the demo:

- -1 and 65,537: **rejected**.
- 0 and 65,536: **within the allowed frame-level length range**; however, a 0-byte payload does not satisfy the v1/v2 schema and will be rejected by their decoders.

### Questions

1. What is version used for? **Selecting the payload field structure/semantics**.
2. What is length used for? **Defining frame boundaries, bounding allocations, and enabling skipping**.
3. Can magic alone safely locate the next frame? **Unsafe by default**, because magic bytes can appear inside payloads.
4. What byte order does `DataOutputStream.writeInt` use? **Big-endian**.
5. Does UTF-8 byte length always equal `String.length()`? **No**.
6. If a reader encounters an unknown version while still knowing frame length, can it always skip it? **Only if the protocol contract permits and frames are independent**.
7. Does `readFully` return fewer bytes without error on mid-payload EOF? **No**, it throws `EOFException` when fewer bytes are available.
8. Is CRC32 secure against attackers? **No**, it only detects many accidental data corruptions.
9. How does EOF right at a frame boundary differ from EOF after a few header bytes? **The former can be valid; the latter is a truncated frame**.
10. If length = 2 GiB and the reader has limited RAM, what should it do? **Reject per limit** or design bounded streaming; never allocate directly.
11. What must be documented when adding an optional field? **Version, presence flag/schema, order, size, default, and unknown handling policy**.
12. To store a file that could lose power mid-append, what is needed besides length? **Partial-record detection, commit/recovery rules, and durability policies if required**.

**Remember:** a binary format with **magic + version + length** helps the parser recognize the data type and record boundaries; adding byte-order/UTF-8 schemas, length limits, checksums, and error rules turns it into an operable protocol. Always **validate length before allocating**, distinguish valid EOF from truncated data, and skip unknown versions only when backed by the specification. A working round-trip example must be tested with multiple versions, multiple frames, invalid inputs, and error recovery.
