# Practical Exercise: Designing a Versioned and Length-Prefixed Binary Format in Java

## 1. Problem and Objectives

Suppose a Java application needs to store thousands of records in a binary file or transmit them sequentially over TCP. Each record has an identifier and a name; in a newer version, a record also includes a priority. We need a format in which the program can:

- Determine the **boundaries** of each record without guessing end-of-record bytes.
- Know the **structure version** to decode the data fields accurately.
- Sequentially read multiple records within the same file or TCP stream.
- Detect invalid, truncated, or checksum-mismatched input.
- Bound sizes before allocating memory.
- Have a clear policy when encountering a record of an unsupported version.
- Work across processes/JDKs without relying on Java's default class serialization.

This is a **binary protocol design** and **record framing** problem. You should not simply write a series of integers/strings and expect the reader to figure out on its own where a record ends.

~~~text
Binary file or TCP stream
  |
  +-- [HEADER record 1][PAYLOAD 1][CHECKSUM 1]
  +-- [HEADER record 2][PAYLOAD 2][CHECKSUM 2]
  +-- [HEADER record 3][PAYLOAD 3][CHECKSUM 3]
                 |
                 v
        Frame-by-frame parser
                 |
       validate -> decode by version
~~~

**The version + length pair solves two different questions:**

- **Version:** Which structure should the bytes inside the payload be interpreted with?
- **Length:** Where do the bytes of the current frame end and where does the next frame begin?

Version does not replace length, and length does not by itself tell the decoder what structure the inner data has.

## 2. Write the Byte Format Specification First

A good protocol does not consist only of Java code. It needs to specify **field order, lengths, byte order, encoding, bounds, and error conditions** precisely. We choose an illustrative format named `JBIN`:

| Offset in frame | Length | Field | Rule |
| ---: | ---: | --- | --- |
| 0 | 4 bytes | `magic` | ASCII `JBIN`, equivalent to hex `4A 42 49 4E` |
| 4 | 1 byte | `version` | Unsigned integer 0–255; supports versions 1 and 2 |
| 5 | 4 bytes | `payloadLength` | Signed 32-bit integer, **big-endian**, accepts only 0 to 65,536 |
| 9 | `payloadLength` bytes | `payload` | Structure per version |
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
  magic       u8          i32 BE        bytes by version        u32 BE

Frame 1 | Frame 2 | Frame 3 | ... | EOF at frame boundary
~~~

This is a **custom format designed for practice**, not a JDK standard. Two programs in different languages can still exchange data if they adhere to the same specification.

### Why Do We Need Magic?

Magic helps detect malformed input early. If the first four bytes do not equal `JBIN`, the parser rejects it before interpreting length or payload.

Magic **is not a security authentication** and does not guarantee automatic boundary recovery when a file is corrupted. Arbitrarily scanning for the `JBIN` sequence inside payloads can mistake data bytes for a real header. When recovery capability is needed, build an explicit resynchronization/commit/index mechanism with clear rules.

### Why Use a Fixed-Size Integer Length?

Length-prefixing allows finding the next frame without needing a delimiter character. That matters for binary payloads, where every byte value from 0 to 255 can be valid.

However, do not trust a length value coming from a file or network. Four bytes can be interpreted as a negative number or billions of bytes. **Validate bounds before creating `new byte[length]`.**

In this exercise, the practice limit is 65,536 bytes **per payload**, not the total file size. Production needs a maximum tailored to business rules, memory, and concurrent connections.

## 3. Designing Payloads by Version

Choose two deliberately different versions:

### Version 1

~~~text
+------------+----------------+-----------------------+
| id: i32 BE | nameLen: u16 BE| nameUtf8: nameLen B   |
+------------+----------------+-----------------------+
     4B             2B             0..65535 B
~~~

For example, a message with `id=7` and `name="Alpha"`. The name is encoded in **UTF-8**, while `nameLen` is the **number of UTF-8 bytes**, not `String.length()`.

### Version 2

Keep the v1 fields and **append at the end of the payload** an integer `priority`:

~~~text
+------------+----------------+----------------------+------------------+
| id: i32 BE | nameLen: u16 BE| nameUtf8: nameLen B | priority: i32 BE |
+------------+----------------+----------------------+------------------+
     4B             2B            n bytes                4B
~~~

With version 2, the decoder must read exactly four more bytes for priority. If there are not four bytes available, the frame is invalid. If the decoder encounters unspecified trailing bytes, **do not silently ignore them** for a known version: the schema may have been encoded wrongly or the parser may be misaligned.

### Unsupported Versions

If the reader currently supports versions 1 and 2 but encounters version 99:

- It **still reads and bounds length** according to the common header.
- It **reads and validates the entire frame** according to the common rules it understands.
- It **does not guess** the version 99 payload structure.
- It can **skip the whole frame intact** and read the next frame, if protocol policy permits; or **reject the entire file/connection** if every message must be understood.

Both policies can be right. Skipping is only valid when each frame is self-contained and carries no state that alters the meaning of subsequent frames. If a new version changes the **common header structure**, older readers may not be able to skip it; in that case, protocol negotiation or a container-level file-format major version is required.

## 4. Byte Order: Java Must Write and Read Consistently

For multi-byte integers, byte order (*endianness*) must be specified. We choose **big-endian**:

~~~text
int value 0x01020304
Big-endian:    01 02 03 04
Little-endian: 04 03 02 01
~~~

`DataOutputStream.writeInt()` and `DataInputStream.readInt()` use **big-endian** order. `writeShort/readUnsignedShort` also exchange bytes from most significant to least significant.

`ByteBuffer` defaults to big-endian, but it can be changed with `order(ByteOrder.LITTLE_ENDIAN)`; do not assume a `ByteBuffer` passed from other code still retains the default byte order. If implementing the same format with `ByteBuffer`, deliberately set `buffer.order(ByteOrder.BIG_ENDIAN)`.

A C/Python/Go reader must follow the same endianness. Do not dump arbitrary native C `struct` layouts and assume C padding/alignment matches Java.

### Unsigned and Signed

- Version: 1 unsigned byte; Java uses `readUnsignedByte()` to receive 0..255.
- `nameLen`: 2 unsigned bytes; Java uses `readUnsignedShort()` to receive 0..65,535.
- `payloadLength`: 4 signed bytes. We specify **0..65,536 as valid**; negative or above the ceiling is an error.
- CRC32: 32-bit bit pattern, written with `writeInt((int) crc.getValue())` and compared by bit pattern when reading.

Java `byte` is signed; if you need to print a byte in hex, use `value & 0xFF` to avoid sign extension.

## 5. UTF-8 and String Length Pitfalls

For example, the string `"A"` is 1 UTF-16 character long and has 1 UTF-8 byte. The string `"Đ"` is 1 UTF-16 code unit long but has **2 UTF-8 bytes**; characters outside the BMP can require 4 UTF-8 bytes and 2 UTF-16 code units.

Therefore, do not do this:

~~~java
out.writeShort(name.length()); // WRONG if length must be counted in UTF-8 bytes
out.write(name.getBytes(StandardCharsets.UTF_8));
~~~

The snippet above illustrates the bug. The correct way:

~~~java
byte[] encodedName = name.getBytes(StandardCharsets.UTF_8);
if (encodedName.length > 65535) {
    throw new IOException("Name too long");
}
out.writeShort(encodedName.length);
out.write(encodedName);
~~~

`writeShort` writes the lower 16 bits; **it does not automatically reject** names longer than 65,535 bytes per protocol intent, so you must check beforehand.

Do not use `DataOutputStream.writeUTF()` as an arbitrary substitute for the format just designed. That method uses **modified UTF-8** with Java's own framing and limits; it is not equivalent to this specification's "u16 length + standard UTF-8". For cross-language compatibility, write standard UTF-8 bytes explicitly along with the byte length.

The decoder also needs a policy for malformed UTF-8. `new String(bytes, UTF_8)` may replace invalid bytes with a replacement character; if the protocol requires **rejecting corrupted UTF-8 data**, use `CharsetDecoder` with `CodingErrorAction.REPORT`.

## 6. Why Need a Checksum? What Does CRC32 Check?

We add CRC-32 to detect **many forms of accidental byte corruption** in the payload, such as storage or transmission errors. CRC32 is not encryption, has no secret key, and **does not protect against intentional tampering**: an attacker can modify the payload and recompute the CRC.

Example:

~~~text
Original payload     → CRC32 0x12345678 (illustrative value)
One byte modified    → recomputed CRC32 usually differs
Reader compares stored CRC with recomputed CRC → reports error
~~~

In this exercise's format, CRC **only protects the payload**, not magic/version/length. The parser still checks header validity and length bounds, but if business requirements demand detecting modified headers or authenticating the data source, add a checksum covering the appropriate fields or use a cryptographic authentication mechanism like MAC/AEAD.

For very large frames, CRC can be computed while streaming chunk by chunk without holding the entire payload in RAM. In the example below, since `MAX_PAYLOAD` is only 65,536 bytes, holding each frame's payload in an array is reasonable for illustration.

## 7. Complete Java 17+ Program: Writing and Reading Three Frames

The example below builds a serializer/deserializer with `DataOutputStream` and `DataInputStream`. It writes three frames into a byte stream:

1. Version 1 containing `id=7`, `name="Alpha"`.
2. Version 99, a frame whose **payload is unknown**, but with valid header/length/CRC, to test the skip policy.
3. Version 2 containing `id=8`, `name="Beta"`, `priority=42`.

Then the program intentionally truncates a frame and flips one payload byte to test two error cases. All tests use an in-memory byte array so stdout does not depend on filesystem or timing.

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
        // Valid EOF ONLY when no byte of the next header has been read yet.
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

        // Header is 9 bytes long; the first byte of payload is at offset 9.
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

### Step-by-Step Analysis of the Program

**Step 1 — Write payload:** `encodeMessage` builds a byte array according to the v1/v2 schema: `id`, `nameLen`, and UTF-8 bytes, adding `priority` if v2. The method verifies that `nameLen` and total payload do not exceed the limits.

**Step 2 — Write frame:** `writeFrame` writes magic, version, length, payload, and CRC32. `DataOutputStream` enforces big-endian for multi-byte integers. One call corresponds to one clearly delimited frame.

**Step 3 — Read header:** `readFrame` allows returning `null` **only when EOF occurs right at the start of the next frame**. If only 1–3 bytes of magic remain or version/length is missing, `readUnsignedByte`/`readInt` throw `EOFException`; that is truncated data, not a valid end.

**Step 4 — Guard allocation:** `length < 0` or `length > MAX_PAYLOAD` is rejected **before** `new byte[length]`. The parser does not trust a length supplied by a peer.

**Step 5 — Read payload and CRC:** `readFully` enforces reading the exact `length` bytes; `readInt` enforces the full trailer. A recomputed CRC32 differing from the stored checksum throws `IOException`.

**Step 6 — Branch by version:** `decodeMessage` understands only v1/v2. Version 99 was already read as a complete frame and CRC-checked, so it can be skipped as an independent unit; the following v2 frame is still read accurately.

**Step 7 — Validate schema inside payload:** The decoder uses `readUnsignedShort` to get name length, verifies enough bytes remain for the name **and the priority field if v2**, performs strict UTF-8 decoding, and then requires zero leftover bytes.

**Step 8 — Test corrupted data:** Truncating the last two CRC bytes raises `EOFException`. Modifying one payload byte while keeping the CRC trailer raises `IOException` with message `CRC32 mismatch`. There is no dependence on network timing or thread ordering.

The example intentionally uses `ByteArrayInputStream` for reproducible results. When moving to real files or sockets, the framing logic stays the same, while buffering, I/O handling, and lifecycle must adapt to the source.

## 8. Design Decisions to Lock Down Before Implementation

### File-Level Header or Per-Record Header?

Two models can be chosen:

**Model A — once-per-file header:**

~~~text
[FILE_MAGIC][FILE_FORMAT_VERSION]
[RECORD_LENGTH][RECORD]
[RECORD_LENGTH][RECORD]
...
~~~

Suitable when the entire file always shares one schema/format or when the application wants to negotiate a file version before reading contents. The reader must know whether every record shares a version or carries its own type/version.

**Model B — per-frame header**, as in this exercise:

~~~text
[MAGIC][VERSION][LENGTH][PAYLOAD][CRC]
[MAGIC][VERSION][LENGTH][PAYLOAD][CRC]
...
~~~

Suitable when mixing record versions or appending frames independently is needed. In exchange, header and CRC overhead repeat on every record.

There is no single right choice for every application. What matters is a **consistent specification** and independence of each frame if skipping unknown versions is desired.

### Protocol-Level Version or Payload-Level Version?

A **protocol major version** can describe the common header syntax; a **payload schema version** describes the fields inside a message type. In the example, they are combined into one `version` byte because the format is simple.

If later you want to change the frame structure itself (for instance, changing length from 32-bit to 64-bit), older readers will not necessarily recognize boundaries anymore. Treat that as a **major protocol change**, not just bumping payload version from 2 to 3.

### Are Type and Flags Needed?

If a file contains multiple record types, you can extend the header to:

~~~text
[MAGIC][FORMAT_VERSION][RECORD_TYPE][FLAGS][PAYLOAD_LENGTH][PAYLOAD][CRC]
~~~

Then the specification must also add:

- Valid type/flag values.
- Whether unknown type/flag values may be skipped.
- Which flags the reader is required to understand in order to decode the payload properly.
- Rules for reserved future bits and the order of compression/encryption processing.
- Maximum decompressed size if the payload is compressed.

Do not add types/flags arbitrarily while forgetting to update the parser and compatibility tests.

## 9. `DataInputStream` vs. `ByteBuffer`/`FileChannel`

Java provides several abstraction levels:

| Tool | When Useful? | Points to Watch |
| --- | --- | --- |
| `DataOutputStream` / `DataInputStream` | Writing/reading primitives over OutputStream/InputStream | Big-endian; `readFully` suits frame lengths |
| `ByteBuffer` | Packing/unpacking bytes from arrays/direct buffers | Must manage `position/limit/flip` and byte order |
| `FileChannel` | Random access, reading/writing by offset for large files | `read`/`write` can transfer partially; must check in a loop |
| Non-blocking `SocketChannel` | Network protocols with Selector | Can return 0 bytes; state machine must accumulate header/payload across passes |
| `BufferedInputStream` | Reduces small I/O calls when reading streams | Does not alter protocol framing |
| `CRC32` | Detects many random byte errors | Not authentication / tamper-resistant |

In the demo, `DataInputStream` fits well because `readFully` waits/reads the exact requested byte count or throws EOF. With a non-blocking `SocketChannel`, never assume a single `read(buffer)` returns all 9 header bytes or the full payload. A **state machine** is needed:

~~~text
NEED_HEADER
    |
    | receive all 9 bytes
    v
VALIDATE_LENGTH
    |
    | valid length, allocate bounded buffer
    v
NEED_PAYLOAD_AND_CRC
    |
    | receive all length + 4 bytes
    v
VERIFY_CRC
    |
    v
DECODE_OR_SKIP
    |
    v
NEED_HEADER (next frame)
~~~

One TCP request can be split across multiple packets, or multiple frames can arrive in one `read`. A length-based protocol makes accumulation explicit, independent of packet boundaries.

## 10. Very Large Files: Stream Frame by Frame

A file may be tens of gigabytes large while each frame is only a few kilobytes long. Do not use `Files.readAllBytes` to load the entire file just because the format is binary.

With `InputStream`/`DataInputStream`, the parser can read one frame at a time and process it immediately. With `FileChannel`, you can read into a bounded buffer, track offsets, and parse incrementally.

Rules:

- **Bound per-frame payload**, total frame count, and total processed bytes per requirements.
- Do not allocate `new byte[fileSize]`; process frame by frame.
- Guard concurrent frame count when many clients send data.
- Do not pass references to reusable buffers into asynchronous jobs without clear ownership.
- Track bytes read, frames rejected, and failure reasons for operations.
- When a genuinely large frame requires streaming, compute CRC incrementally and use bounded input so it does not overread into the next frame.

In the example, we use a maximum payload buffer of 65,536 bytes, small enough to demonstrate standalone without gigabyte-handling machinery.

## 11. Truncation, Crash, and Append Protocols

There is an important distinction between **valid EOF** and a **file truncated mid-record**:

~~~text
Valid:
[complete frame 1][complete frame 2][EOF]

Invalid:
[complete frame 1][half header frame 2][EOF]

Invalid:
[complete frame 1][header frame 2][half payload][EOF]
~~~

Therefore `readFrame` returns `null` only when **no byte of the next frame has been read**. Once any header byte has been seen, missing remaining data must be an error—or a state requiring waiting for more bytes if reading from an unclosed network stream.

If an application appends records to a file and loses power or the JVM crashes mid-write, the file can end with an incomplete frame. Common production strategies:

1. Read complete frames from the start and track the **last valid commit offset**.
2. If the tail is truncated, reject the entire file or quarantine the incomplete tail according to policy.
3. For an append-only log, recovery can **truncate back to the last valid offset**, but only after independent verification, when no other writer is active, and with proper state persistence.
4. When durability is needed, use `FileChannel.force(...)` per policy and consider write ordering, metadata, and filesystem behavior.
5. When whole-file atomic updates are needed, consider writing a complete temporary file and moving/renaming on the same filesystem, noting that `ATOMIC_MOVE` support depends on the provider.

**A length-prefix does not automatically turn multiple writes into an atomic transaction.** It helps detect incomplete records; recovery and durability are separate design decisions.

## 12. Compatibility: Backward, Forward, and Schema Evolution

Three scenarios must be tested independently:

| Scenario | Expectation If Design Supports It |
| --- | --- |
| New reader reads v1 record | Readable using the v1 decoder |
| New reader reads v2 record | Readable using the v2 decoder |
| Old reader encounters v2/v99 record | Safely skipped if protocol permits; or clear error |

### Backward Compatibility

New readers can understand older versions. In the demo, the decoder handles v1 and v2. That is **the ability to read older data**, which does not mean every older writer will understand data produced by a newer writer.

### Forward Compatibility

Old readers can tolerate newer changes within the specified scope. For example, the parser reads length, verifies checksum, and **skips unknown versions** to continue with the next frame. However, if an unknown frame alters state—such as setting a dictionary or encryption key for subsequent frames—skipping can be **unsafe**.

### Migrations and Defaults

If you need to lift a v1 record onto a new data model, one approach is picking a sensible default for `priority` when reading v1, or leaving it `null` to mean "absent". **Do not use 0 as a default without stating the semantics clearly**, because 0 may be a valid priority level.

Similarly, when removing a field in v3, specify explicitly what the v1/v2/v3 schemas are, rather than treating all bytes after the name as optional unmarked fields.

## 13. Safety Against Untrusted Input

A binary parser should assume files/input can be corrupted or crafted by an untrusted peer. Safe processing order:

1. **Check magic** before interpreting the payload.
2. **Read version within bounds** and enforce the unknown-version policy.
3. **Validate length**: non-negative, within max, and free of integer overflow when computing `header + length + trailer`.
4. **Bound allocation** before creating buffers.
5. **Read the exact full length** and treat mid-frame EOF as an error.
6. **Verify checksum** over the exact defined byte range.
7. **Validate internal schema**, string/array lengths, and valid UTF-8.
8. **Reject trailing bytes** if the known schema version forbids them.
9. **Limit total load**: frame count, rate, deadlines, nesting, connection count, memory budget, and CPU.
10. **Do not treat CRC as authentication**: if defending against tampering by an attacker, use MAC/AEAD/signatures under a proper security protocol.

In particular, this code snippet:

~~~java
int length = in.readInt();
byte[] payload = new byte[length]; // DANGEROUS if not yet validated
~~~

is an anti-pattern. A negative length causes an allocation error; a huge length can lead to `OutOfMemoryError`. In the demo, `MAX_PAYLOAD` is checked before allocation. In production, you must also limit how many frames are held concurrently.

### Nested Lengths

A frame already has `payloadLength`, yet the payload itself may contain `nameLen`, `arrayLength`, or element lists. **Every nested length** must be checked against the remaining bytes and business limits; do not trust all inner payload fields just because the outer frame passed.

For instance, the demo decoder verifies `nameLength <= remaining - extraBytes`. If adding a list of sub-records, the parser must bound the count and check the required byte count before looping or allocating.

## 14. `ByteBuffer`: Short Example of a Big-Endian Header

If you want to build the header with `ByteBuffer` instead of `DataOutputStream`:

~~~java
ByteBuffer header = ByteBuffer.allocate(9)
        .order(ByteOrder.BIG_ENDIAN);

header.putInt(0x4A42494E); // "JBIN"
header.put((byte) 1);      // version
header.putInt(123);       // payloadLength

header.flip();             // Prepare for channel.write(header)
~~~

This is an **illustrative snippet**; import `java.nio.ByteBuffer` and `java.nio.ByteOrder`, and note it does not send data by itself.

`flip()` is crucial: after `put`, position sits at the end of the written region; if you forget `flip` and call `channel.write(header)`, it may transmit 0 bytes or unwanted data. With a non-blocking `SocketChannel`, even after `flip`, `write` may send only part of the header; you must keep the buffer until all bytes are sent.

Reader side with `ByteBuffer`:

~~~java
header.order(ByteOrder.BIG_ENDIAN);
int magic = header.getInt();
int version = Byte.toUnsignedInt(header.get());
int length = header.getInt();
~~~

Only call these `get` methods after **all 9 bytes have been received**; otherwise, `BufferUnderflowException` may occur. Read and validate length before allocating the payload buffer. These bytes follow the exact same specification as the `DataInputStream` demo.

## 15. Common Mistakes

**Mistake 1 — No length-prefix.** When concatenating multiple binary records, the parser does not know the boundaries. Solution: specify length-based framing or another sufficiently strict framing mechanism.

**Mistake 2 — Length only, no version.** When adding a field, older parsers can misinterpret bytes. Solution: schema version and a compatibility policy.

**Mistake 3 — Forgetting to specify byte order.** Java, C, and operating systems can use different representations. Solution: define big-endian/little-endian in the spec and test raw bytes.

**Mistake 4 — Using `String.length()` as UTF-8 length.** Multi-byte characters shift the reader's offset. Solution: encode UTF-8 first, then write byte length.

**Mistake 5 — Using `writeUTF/readUTF` for a standard UTF-8 protocol.** That is modified UTF-8 with its own framing. Solution: write u16/u32 byteLength followed by standard UTF-8 bytes.

**Mistake 6 — Allocating from an unchecked length.** Can create giant or negative arrays. Solution: range-check before allocation.

**Mistake 7 — Treating mid-payload EOF as valid end of file.** That is a truncated frame. Solution: distinguish boundary EOF from mid-frame EOF.

**Mistake 8 — Reading an unknown version with a similar-looking schema.** Can be completely wrong. Solution: skip the whole frame if the protocol permits, or raise a clear error.

**Mistake 9 — Not checking trailing bytes in a known schema.** The parser may accept records encoded with a mismatched schema. Solution: require the payload to be consumed completely when the version is fixed.

**Mistake 10 — Thinking CRC protects against intentional tampering.** CRC32 is not a MAC. Solution: use cryptographic authentication if attackers are in scope.

**Mistake 11 — Assuming one TCP read returns a complete frame.** TCP is a byte stream; a state machine is needed to accumulate header and payload.

**Mistake 12 — Not testing multiple consecutive frames.** The parser might overread into the next frame or fail to reset state properly. Solution: round-trip multiple versions, an unknown version in the middle, the final frame, EOF, and corrupted data.

## 16. Practice Exercises and Self-Check Questions

### Exercise 1 — Reading Bytes According to the Spec

Given the header:

~~~text
4A 42 49 4E 01 00 00 00 0B
~~~

Determine:

- Magic: **`JBIN`**.
- Version: **1**.
- Payload length: **11 bytes**.
- Total frame length per this lesson's structure: **13 + 11 = 24 bytes**, including the 4-byte CRC32 at the end.

This is **only the header**, without the accompanying payload/CRC to conclude the whole frame is valid.

### Exercise 2 — Version 1 and Version 2

If v1 has id=7 and name `"Alpha"`:

- id: 4 bytes.
- name length: 2 bytes.
- UTF-8 `Alpha`: 5 bytes.
- Total v1 payload: **11 bytes**.
- Total frame: **24 bytes**.

If v2 has the same name/id plus an i32 priority, then payload is **15 bytes** and frame is **28 bytes**. Do not use Java character count in place of UTF-8 byte count when non-ASCII characters are present.

### Exercise 3 — Adding a Message Type

Add a type field to the header: common version, 1-byte type, 4-byte length. You need to:

1. Update header size from 9 to 10 bytes.
2. Rewrite encoder/decoder in sync.
3. Decide whether unsupported types should be skipped or rejected.
4. Consider how to distinguish files using the old header from the new header (for example, changing the format major version/magic), rather than silently misreading.

### Exercise 4 — Invalid Length Cases

Write tests with `payloadLength = -1`, `65_537`, `0`, `65_536`. In the demo:

- -1 and 65,537: **rejected**.
- 0 and 65,536: **within the allowed length range** at the frame level; however, a 0-byte payload does not satisfy the v1/v2 schema and will be rejected by those versions' decoders.

### Questions

1. What is version used for? **Selecting the payload field structure/semantics**.
2. What is length used for? **Determining frame boundaries, bounding allocations, and supporting skipping**.
3. Can you use magic alone to locate the next frame? **Unsafe by default**, because magic bytes can appear inside payloads.
4. What is the byte order of `DataOutputStream.writeInt`? **Big-endian**.
5. Is UTF-8 byte length always equal to `String.length()`? **No**.
6. If a reader encounters an unknown version while still knowing frame length, can it always skip it? **Only if the protocol contract allows it and frames are independent**.
7. Does `readFully` return fewer bytes without an error on mid-payload EOF? **No**, it throws `EOFException` when it cannot read enough bytes.
8. Is CRC32 secure against an attacker? **No**, it only detects many forms of accidental data corruption.
9. How does EOF right at the boundary between two frames differ from EOF after a few header bytes? **The first case can be valid; the second case is a truncated frame**.
10. If length = 2 GiB and the reader has little RAM, what should it do? **Reject per bounds** or design streaming with an explicit budget; do not allocate directly.
11. When adding an optional field, what must be documented? **Version, presence flag/schema, order, size, default, and unknown policy**.
12. To store a file that might lose power mid-append, what is needed besides length? **Incomplete-record detection, commit/recovery rules, and a durability policy if required**.

**Remember:** a binary format with **magic + version + length** lets the parser recognize data type and record boundaries; adding byte order/UTF-8 schemas, length limits, checksums, and error rules turns it into an operable protocol. Always **validate length before allocation**, distinguish valid EOF from truncated data, and skip unknown versions only when justified by the specification. A proper round-trip example must be tested across multiple versions, multiple frames, invalid inputs, and error recovery.