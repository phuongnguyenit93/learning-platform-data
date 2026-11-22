# Designing Headers, Message Types, Lengths, and Protocol Versions over TCP

## 1. Goal: Turning a TCP Byte Stream into Meaningful Messages

TCP provides both ends of a connection with an **ordered byte stream**. TCP has no concept of "business message #1", "business message #2", a JSON object, or an API call. If the sender calls `OutputStream.write(frameA)` and then `write(frameB)`, the receiver might see half of `frameA` on the first `read`, the rest on the next, or multiple frames at once. The boundaries of `write` calls **do not become the boundaries of `read` calls**; TCP may fragment or coalesce data depending on transmission results and buffers.

For example, a client sends two logical messages:

```text
Message A: DATA("Xin chào")
Message B: PING()
```

The receiver might see arbitrary reads such as:

```text
read #1: [half of header A]
read #2: [remaining header A][part of payload A]
read #3: [remaining payload A][entire header B]
read #4: [possibly the next part or no data yet]
```

If you treat each `InputStream.read(...)` call as one message, the parser will break. **The application-layer protocol must itself determine the start, size, and meaning of each message**. This task is called *message framing*.

This lesson focuses on four core decisions: **header, message type, length, and protocol version**. The goal is to build a contract that can be decoded independently of how TCP splits or coalesces data, while allowing software versions to communicate in a controlled manner.

After this lesson, you will:
- Describe clear frame boundaries and distinguish a frame from a TCP segment.
- Design a binary header structure with *magic*, version, type, flags, correlation ID, and payload length, along with offsets, endianness, and constraints.
- Know when to choose fixed-length, delimiter, length-prefix, or extensible TLV structures.
- Write a Java 17+ encoder/decoder that reads the complete header and payload, blocks dangerous lengths, and detects mid-frame EOF.
- Specify DATA/ACK/ERROR/PING messages, version compatibility, handling of unknown messages, and testing.

## 2. Separating Three Concepts: Bytes, Frames, and Business Messages

| Concept | Which layer? | What to remember |
| --- | --- | --- |
| TCP segment | TCP / network | Has a TCP header; segment boundaries are not business message boundaries |
| Byte stream | Socket API | `InputStream`/`OutputStream` deliver bytes in order; the number of bytes per read is not fixed |
| Frame | Application protocol we define | A unit defined by a header and a payload length |
| Message type | Application protocol | Indicates which schema/processing flow the payload should be interpreted with |
| Request / response | Business logic | Can map multiple messages onto one connection; needs an ID if correlating results asynchronously |

Example with *length-prefixed framing*:

```text
TCP byte stream
┌───────────────────────────┬────────────────────┬───────────────────────┐
│ header A │ payload A      │ header B │ payload B│ header C │ payload C  │
└───────────────────────────┴────────────────────┴───────────────────────┘
         ↑ one frame                    ↑ next frame
```

One frame can span multiple segments; conversely, one segment can contain multiple frames. The decoder preserves byte-stream order and slices each frame based on the header contract, **not** by guessing based on network packet boundaries.

The concept of **TCP ACK** differs from **business ACK**: TCP ACK represents the byte acknowledgment mechanism at the TCP layer; an `ACK` message sent by the application can carry the meaning "received and processed request #42" according to its own contract. Merely seeing that TCP sent successfully **does not** prove that the business logic has committed.

## 3. Options for Creating Message Boundaries

| Approach | How it delimits | Pros | Limitations |
| --- | --- | --- | --- |
| Fixed-length | Every frame has exactly N bytes | Simple parser, fixed offsets | Wasteful for variable payloads; hard to extend |
| Delimiter, e.g. `\n` | Reads until a terminating character | Suits text-line protocols | Must escape if the delimiter appears in data; line-length limits |
| Length prefix | Header contains payload byte count | Supports binary payloads and variable sizes | Must validate length before allocating; must read exact byte count |
| Header + length + type | Header has metadata, variable-length body | Easy message routing, versioning, and request correlation | Requires a complete byte-level specification |
| Varint length / TLV | Lengths or fields are flexibly encoded | Can save bytes / be extensible | More complex parser; needs limits and compatibility rules |

This lesson chooses a **16-byte fixed header + declared-length payload** to fully illustrate all four aspects. This is a sample protocol for learning purposes, **not a widely used wire protocol standard named "JMSG"**. Real systems may choose HTTP/2, gRPC, WebSocket, MQTT, Redis RESP, or Protobuf framing depending on their needs; you should not build a custom protocol if an existing standard already fits.

**Prerequisite when choosing framing:** both sides must agree on header size, byte order (endianness), how unsigned numbers are read, payload data types, length limits, and how to react to invalid data. Missing any decision, two implementations may decode differently even when receiving the exact same byte sequence.

## 4. Illustrative Protocol Specification: 16-Byte Header

We design the v1.0 format:

```text
Offset (byte)     0           4   5   6   7          8          12       16
                  │           │   │   │   │          │           │        │
                  ▼           ▼   ▼   ▼   ▼          ▼           ▼        ▼
Frame =          [MAGIC:4][MAJ:1][MIN:1][TYPE:1][FLAGS:1][REQUEST_ID:4][LENGTH:4][PAYLOAD:LENGTH]
                  └──────────────── header = 16 bytes ──────────────────┘
```

| Offset (from frame start) | Width | Field | Interpretation / v1.0 rule |
| --- | ---: | --- | --- |
| `0..3` | 4 bytes | `magic` | Constant 0x4A4D5347, ASCII "JMSG"; checks for wrong header/protocol |
| `4` | 1 byte | `versionMajor` | `1`; unsupported major version → reject |
| `5` | 1 byte | `versionMinor` | `0` in demo; different minor versions are also rejected since there is no negotiation yet |
| `6` | 1 byte | `messageType` | `1` DATA, `2` ACK, `3` ERROR, `4` PING |
| `7` | 1 byte | `flags` | `0`; all remaining bits are undefined so they must be 0 |
| `8..11` | 4 bytes | `requestId` | Correlation ID `uint32`, stored in Java using the bits of an `int` |
| `12..15` | 4 bytes | `payloadLength` | Number of **bytes** of the payload; v1.0 only allows `0..1_048_576` |
| `16..` | `payloadLength` bytes | `payload` | Data according to each type's schema |

**Byte order:** all multi-byte numeric fields are written in **big-endian** (network byte order). This is a rule defined by the protocol; it does not depend on whether the CPU runs little-endian or big-endian. In Java, `DataOutputStream.writeInt` writes the most significant byte first; `ByteBuffer.order(ByteOrder.BIG_ENDIAN)` decodes consistently.

**Field widths:** the total is `4 + 1 + 1 + 1 + 1 + 4 + 4 = 16` bytes. An empty frame (like PING) still takes a 16-byte header. If the payload has N bytes, the frame is exactly `16 + N` bytes long. `payloadLength` **does not include** the 16-byte header in this protocol.

**1 MiB limit:** is an example rule, not a TCP limit. The decoder must reject larger lengths before creating an array, even though the field on the wire can represent larger numbers. If a protocol wants larger frames in another system, it must measure memory, deadlines, concurrency, backpressure, and streaming mechanisms.

### 4.1. Why is magic needed?

`magic` helps detect the start of a stream not using this protocol or a corrupted header. With 4 bytes "JMSG", the probability of accidental collision is lower than relying on just a single type byte. However:
- Magic **does not authenticate** the sender.
- Magic **is not a checksum or digital signature**.
- When an invalid magic is detected, v1.0 proactively **closes the connection** and does not scan for the next "JMSG" sequence: in untrusted data, scanning can mistake magic bytes inside a payload and cause the parser to lose frame alignment.

### 4.2. Why is requestId needed?

TCP preserves byte order but does not automatically indicate which response belongs to which request when the application has multiple pending tasks. The `requestId` field helps the client match results, track timeouts, and correlate logs.

v1.0 rules:
- `DATA`, `ACK`, `ERROR` have `requestId != 0`.
- `PING` is a one-way liveness check, has `requestId == 0`, and an empty payload.
- `ACK` carries back the same ID as the `DATA` being acknowledged.
- The 32-bit `requestId` is an **opaque identifier**, not a security credential or proof of exactly-once delivery. When the number wraps around its range, a wraparound policy is needed to avoid colliding with active IDs.

## 5. Byte-by-Byte Wire Representation Example

Sending DATA (`type=1`), version 1.0, `flags=0`, requestId `42`, UTF-8 payload `Xin chào`.

The UTF-8 encoding of `Xin chào` takes **9 bytes**, even though the string has **8 Unicode characters**. The payload is:

```text
58 69 6E 20 63 68 C3 A0 6F
 X  i  n     c  h    à     o
```

16-byte header:

```text
4A 4D 53 47 | 01 | 00 | 01 | 00 | 00 00 00 2A | 00 00 00 09
    JMSG     major minor type flags requestId=42  payloadLength=9
```

Total frame = 16-byte header + 9-byte payload = **25 bytes**. The character `à` encodes to `C3 A0`; if the sender writes the length as `String.length() == 8`, the decoder will only read 8 bytes, leaving byte `6F` behind as "garbage" before the next header, and the protocol will lose synchronization.

This is also why you must not use "character count" or "object count" instead of `payloadLength`. Encode the payload first, take `byteArray.length`, and then write the header and that exact byte array.

## 6. Defining Message Types as a Business Contract

The purpose of type is not just to route to a `switch`. You need to clearly specify **who is allowed to send it, what schema the payload has, whether there is a response, and the validity conditions**.

| Type v1.0 | Value | Payload | requestId | Demo meaning |
| --- | ---: | --- | --- | --- |
| `DATA` | 1 | UTF-8 content, length ≤ 1 MiB | Non-zero | Client sends data; the demo does not specify a deeper business schema |
| `ACK` | 2 | Acknowledgment info (e.g. `OK`) | Matches received request | Server confirms processing according to application rules |
| `ERROR` | 3 | Error code + description per published schema | Matches failed request | Returns a business error while the connection may remain valid |
| `PING` | 4 | Must be empty | Must be 0 | Liveness signal defined by the sample protocol |

The demo in section 11 only sends `DATA`, `PING`, and `ACK`; `ERROR` has an identifier but does not yet define a detailed payload encoding. **Do not assume ERROR content is JSON or structured UTF-8** before specifying the schema. In a real application, you must clarify:
- Does each type's payload use UTF-8, JSON, CBOR, Protobuf, or another format?
- What are the required fields, optional fields, length limits, and validation rules?
- Does the server return `ACK` when "received into buffer", "persisted", or "transaction committed"? Those are three different points in time.
- Will a duplicate request ID from a retry be rejected, return the old result, or be reprocessed? A correlation ID does not automatically guarantee **idempotency**.
- Are multiple concurrent requests allowed on one connection? If so, a single reader must sequentially parse the byte stream and route responses to the corresponding requests by ID; two threads must not concurrently call `readFrame` from the same `InputStream`.

**Unsupported types:** the demo rejects any `type` outside `1..4`. This is a fail-closed choice for v1.0. A larger protocol may define a range of optional types, but must specify whether old clients can safely skip them and how capabilities are negotiated.

## 7. Protocol Versioning: Avoiding "Parseable" but Misunderstood

The header has two bytes: `major` and `minor`. Recommended semantics:

- **Major** changes when the wire format or semantics break: changing header offsets/widths, changing endianness, changing how length is interpreted, changing required fields, or changing message type behavior incompatibly.
- **Minor** is intended for compatible additions, but only when the protocol actually defines a mechanism for reading new fields, skipping optional parts, and capability negotiation.
- **Patch version**, if any, usually belongs to software releases and does not need to appear in the wire header unless the protocol has a reason.

In the **current demo**, the decoder only accepts the pair **(major=1, minor=0)**. This is intentional: there is no version negotiation or "skip optional field" mechanism yet, so automatically accepting any minor version would promise a level of compatibility that the code does not guarantee.

### 7.1. When Deploying Multiple Versions Simultaneously

Suppose server v2 wants to add compression or a new message type. Steps to consider:
1. Determine whether the change is compatible with the 16-byte layout and old parsers.
2. If there are optional extensions, clearly design **how to determine the extension length**, TLV namespaces/types, and rules for "which fields must be understood".
3. If the change breaks the contract, increment `major` and choose an upgrade/routing solution or separate old–new endpoints.
4. If you want the same connection to support multiple capabilities, you can add a `HELLO`/`HELLO_ACK` handshake (with corresponding types formally defined in the new revision) to exchange supported versions/features before business data.
5. Roll out in order to avoid downtime: servers support both old and new versions first; clients upgrade gradually; collect telemetry on version distribution; retire the old version once no callers remain.

**Do not use `minor` as an excuse to silently redefine old fields.** For example, if v1.0 interprets bit 0 of flags as "reserved=0" and v1.1 changes that bit to "compressed", an old client might reject it or decode the body incorrectly. Clear negotiation and flag rules are required; otherwise, treat it as an incompatible change.

### 7.2. Example of an Extensible Design (Not Yet Supported in v1.0)

Another revision could add `headerLength` along with TLVs after the base header:

```text
[type:1][length:2][value:length] ...
```

However, to be safe, you must simultaneously limit the total extension length, specify TLV ordering/duplicates, how to skip unknown optional TLVs, how to handle unknown required TLVs, endianness, and maximum field count. **The 16-byte v1.0 protocol in this lesson has no `headerLength` field and no TLVs**; the representation above is only an option for a new design and must not be appended to the sample frame.

## 8. Flags and Payload Format Must Be Explicitly Specified

In the v1.0 header, `flags` has 8 bits, all of which are reserved and must be 0. Why not "ignore unknown flags"?
- A newer peer might set a bit indicating a compressed body, encryption, or a required checksum; an old peer that ignores it will misinterpret the bytes.
- A bit might alter the semantics of other fields; if not understood, continuing is unsafe.
- Explicit rejection produces an easily diagnosable compatibility error instead of silent data corruption.

When flags are genuinely needed, publish a bit table such as `COMPRESSED=0x01`, `CHECKSUM_PRESENT=0x02` along with algorithm selection conditions, decompressed length limits, negotiation mechanisms, and handling when unsupported. Do not reserve bits for the future and then infer meanings in an unspecified version.

### 8.1. Payload Structure Is Independent of Framing

The header knows `type` and `length`; it **does not automatically make the payload JSON, a Java object, or Unicode text**. If DATA uses UTF-8, both sides need to agree on:
- Fixed charset `UTF-8`.
- Schema/required fields and payload version structure if the payload contains objects.
- Size limits, nesting limits, unknown fields, and behavior on malformed payloads.
- For JSON: rules for duplicate keys, numbers, Unicode, parser safety, and depth limits.
- If using Protobuf/CBOR: their schema versions and official wire formats, while the outer header is used only for framing/dispatch.

Do not use `DataOutputStream.writeUTF` in place of plain UTF-8 without stating it clearly: this API writes **modified UTF-8** prefixed with a 2-byte length, which differs from `"text".getBytes(StandardCharsets.UTF_8)`. The example below uses **plain UTF-8**.

## 9. Correct Decoding Flow: Header → Validate → Payload

A proper decoder must follow this sequence:

```text
At start of frame
    │
    ├─ read first byte == -1? ──► Clean EOF (no more frames)
    ▼
Read all 16 header bytes (do not assume 1 read gets everything)
    │
    ├─ EOF mid-header? ─────────────► ERROR truncated frame
    ▼
Validate magic, major/minor, type, flags, requestId
    │
    ├─ Mismatch? ──────────────────► Protocol ERROR / close connection
    ▼
Check 0 <= payloadLength <= MAX_PAYLOAD
    │
    ├─ Negative or exceeds max? ────────────► ERROR before allocating
    ▼
Allocate buffer of exact length and read full payload
    │
    ├─ EOF mid-payload? ────────────► ERROR truncated frame
    ▼
Dispatch frame by type/schema/requestId
    │
    ▼
Repeat at start of next frame
```

There is an essential distinction here:
- If a valid frame just finished and `InputStream.read()` returns `-1` **at the start of the next frame**, that is a clean end of byte stream.
- If at least one byte of the header has been seen and the rest does not arrive before EOF, that is a **truncated header**.
- If the header says the body is 9 bytes long but only 8 bytes arrive before EOF, that is a **truncated payload**.
- If the header says the body is longer than the limit, reject **before** creating a byte array or waiting to receive it all.

`DataInputStream.readFully(byte[])` only returns when the buffer is completely filled, or throws `EOFException` if EOF arrives early. It **does not** treat a single `read` as one message. However, `readFully` can also block for a long time if the peer sends very slowly; production requires deadlines, timeouts, and resource limits.

### 9.1. Endianness and Unsigned Numbers in Java

Java `byte` is signed (`-128..127`). Reading a 1-byte field carrying an unsigned value requires `Byte.toUnsignedInt(byteValue)`. For `requestId` of type `uint32`, Java `int` simply stores the same 32 bits; if you want to print it as unsigned, use `Integer.toUnsignedString(id)`. Since requestId is just a correlation identifier, preserving the bits when echoing is sufficient.

`payloadLength` on the wire is designed as `uint32`, but the Java decoder reads it into an `int`: if the high bit is 1, the Java value will be negative. Because the demo limit is ≤ 1 MiB, **any negative value exceeds the valid limit** and must be rejected. Do not add `16 + length` into an `int` **before** validating the length to avoid overflow or unintended allocation.

## 10. The Encoder Must Build a Complete Frame Under One Contract

The encoder operates symmetrically:

1. Validate that `type`, requestId, and payload are non-null and length ≤ limit.
2. Encode the payload into a **byte[]** first (e.g. UTF-8).
3. Write the 4-byte magic, major, minor, type, flags, 4-byte requestId, and 4-byte payload length in big-endian.
4. Write the exact `payloadLength` bytes of the body.
5. Flush as required by the application or manage buffers appropriately, without treating a single `flush` as a frame or a TCP packet.

When multiple threads send on the same socket, you must serialize **the entire header + body of each frame** using a single writer/queue or a shared lock. If thread A writes half of header A and then thread B writes header B, the byte stream becomes interleaved and cannot be decoded properly. A correct `writeFrame` per thread is **not enough** if threads do not coordinate access to the same `OutputStream`.

**Frame ordering:** TCP preserves byte order on a single connection, so the decoder will read A before B if the encoder actually writes all of A before writing B. However, this is not *distributed business* ordering: the server may process requests concurrently and return responses in a different order; requestId helps match results.

## 11. Java 17+ Program: Binary Codec and Exchange over TCP Loopback

This is **a standalone Java file** with no external libraries. The program has two parts:
- **Memory test:** creates two consecutive frames in a byte stream, simulates each bulk `read` returning at most 3 bytes, and verifies clean EOF, truncated payload, and a header declaring an oversized length.
- **Socket test:** opens a loopback server on a random port, the client sends DATA then PING over **one TCP connection**, and the server reads both frames and returns ACK with the same requestId.

Save the file `TcpFrameDemo.java`:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.concurrent.atomic.AtomicReference;

public class TcpFrameDemo {
    private static final int MAGIC = 0x4A4D5347; // "JMSG"
    private static final int HEADER_BYTES = 16;
    private static final int MAX_PAYLOAD = 1_048_576;
    private static final int DATA = 1, ACK = 2, ERROR = 3, PING = 4;

    record Frame(int type, int requestId, byte[] payload) {
        Frame {
            if (payload == null) throw new IllegalArgumentException("payload");
            payload = payload.clone();
        }
        @Override public byte[] payload() {
            return payload.clone();
        }
    }

    private static void validateFields(int type, int requestId, int length)
            throws IOException {
        if (type < DATA || type > PING) throw new IOException("type");
        if (length < 0 || length > MAX_PAYLOAD) throw new IOException("length");
        if (type == PING && (requestId != 0 || length != 0)) {
            throw new IOException("ping");
        }
        if (type != PING && requestId == 0) {
            throw new IOException("requestId");
        }
    }

    static void writeFrame(OutputStream stream, Frame frame) throws IOException {
        byte[] bytes = frame.payload();
        validateFields(frame.type(), frame.requestId(), bytes.length);
        DataOutputStream out = new DataOutputStream(stream);
        out.writeInt(MAGIC);
        out.writeByte(1); // major
        out.writeByte(0); // minor
        out.writeByte(frame.type());
        out.writeByte(0); // flags reserved
        out.writeInt(frame.requestId());
        out.writeInt(bytes.length);
        out.write(bytes);
        out.flush();
    }

    static Frame readFrame(InputStream stream) throws IOException {
        DataInputStream in = new DataInputStream(stream);
        int firstByte = in.read();
        if (firstByte == -1) return null; // clean EOF between frames

        byte[] header = new byte[HEADER_BYTES];
        header[0] = (byte) firstByte;
        in.readFully(header, 1, HEADER_BYTES - 1);

        ByteBuffer fields = ByteBuffer.wrap(header).order(ByteOrder.BIG_ENDIAN);
        int magic = fields.getInt();
        int major = Byte.toUnsignedInt(fields.get());
        int minor = Byte.toUnsignedInt(fields.get());
        int type = Byte.toUnsignedInt(fields.get());
        int flags = Byte.toUnsignedInt(fields.get());
        int requestId = fields.getInt();
        int length = fields.getInt();

        if (magic != MAGIC) throw new IOException("magic");
        if (major != 1 || minor != 0) throw new IOException("version");
        if (flags != 0) throw new IOException("flags");
        validateFields(type, requestId, length);

        byte[] payload = new byte[length];
        in.readFully(payload);
        return new Frame(type, requestId, payload);
    }

    private static void memoryDemo() throws IOException {
        ByteArrayOutputStream wire = new ByteArrayOutputStream();
        writeFrame(wire, new Frame(DATA, 42,
                "Xin chào".getBytes(StandardCharsets.UTF_8)));
        writeFrame(wire, new Frame(PING, 0, new byte[0]));
        byte[] bytes = wire.toByteArray();
        System.out.println("HEADER=" + HexFormat.ofDelimiter(" ")
                .withUpperCase().formatHex(bytes, 0, HEADER_BYTES));

        InputStream fragmented = new FilterInputStream(new ByteArrayInputStream(bytes)) {
            @Override public int read(byte[] buffer, int offset, int length)
                    throws IOException {
                return super.read(buffer, offset, Math.min(length, 3));
            }
        };
        Frame first = readFrame(fragmented);
        Frame second = readFrame(fragmented);
        System.out.println("FRAME1=DATA id="
                + Integer.toUnsignedString(first.requestId())
                + " bytes=" + first.payload().length
                + " text=" + new String(first.payload(), StandardCharsets.UTF_8));
        System.out.println("FRAME2=PING id=" + second.requestId()
                + " bytes=" + second.payload().length);
        System.out.println("EOF_AT_BOUNDARY=" + (readFrame(fragmented) == null));

        try {
            readFrame(new ByteArrayInputStream(
                    Arrays.copyOf(bytes, HEADER_BYTES + 3)));
            throw new AssertionError("must reject truncated body");
        } catch (EOFException expected) {
            System.out.println("TRUNCATED_BODY=EOFException");
        }
        byte[] oversized = Arrays.copyOf(bytes, HEADER_BYTES);
        ByteBuffer.wrap(oversized).order(ByteOrder.BIG_ENDIAN)
                .putInt(12, MAX_PAYLOAD + 1);
        try {
            readFrame(new ByteArrayInputStream(oversized));
            throw new AssertionError("must reject oversize");
        } catch (IOException expected) {
            System.out.println("OVERSIZE=" + expected.getMessage());
        }
    }

    private static void socketDemo() throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(3000);
            AtomicReference<String> received = new AtomicReference<>("none");
            AtomicReference<Throwable> failure = new AtomicReference<>();
            Thread server = new Thread(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(3000);
                    Frame data = readFrame(peer.getInputStream());
                    Frame ping = readFrame(peer.getInputStream());
                    if (data == null || data.type() != DATA
                            || ping == null || ping.type() != PING) {
                        throw new IOException("unexpected frames");
                    }
                    received.set("DATA,PING");
                    writeFrame(peer.getOutputStream(), new Frame(
                            ACK, data.requestId(),
                            "OK".getBytes(StandardCharsets.UTF_8)));
                } catch (Throwable e) {
                    failure.set(e);
                }
            });
            server.start();
            try (Socket client = new Socket(
                    "127.0.0.1", listener.getLocalPort())) {
                client.setSoTimeout(3000);
                writeFrame(client.getOutputStream(), new Frame(
                        DATA, 42, "Xin chào".getBytes(StandardCharsets.UTF_8)));
                writeFrame(client.getOutputStream(), new Frame(
                        PING, 0, new byte[0]));
                Frame reply = readFrame(client.getInputStream());
                if (reply == null || reply.type() != ACK) {
                    throw new IOException("missing ACK");
                }
                System.out.println("CLIENT_ACK="
                        + Integer.toUnsignedString(reply.requestId())
                        + ":" + new String(reply.payload(), StandardCharsets.UTF_8));
            }
            server.join(5000);
            if (server.isAlive()) throw new IOException("server timeout");
            if (failure.get() != null) throw new IOException("server failed", failure.get());
            System.out.println("SERVER_RECEIVED=" + received.get());
        }
    }

    public static void main(String[] args) throws Exception {
        memoryDemo();
        socketDemo();
    }
}
```

Compile and run:

```bash
javac --release 17 TcpFrameDemo.java
java TcpFrameDemo
```

Program stdout when the loopback socket works normally:

```text
HEADER=4A 4D 53 47 01 00 01 00 00 00 00 2A 00 00 00 09
FRAME1=DATA id=42 bytes=9 text=Xin chào
FRAME2=PING id=0 bytes=0
EOF_AT_BOUNDARY=true
TRUNCATED_BODY=EOFException
OVERSIZE=length
CLIENT_ACK=42:OK
SERVER_RECEIVED=DATA,PING
```

### 11.1. The Decoder Tolerates Multiple Reads

`FilterInputStream` in the example limits each **bulk** `read(byte[], off, len)` call to at most 3 bytes. If the code assumed a single read receives all 16 bytes, it would fail immediately; `DataInputStream.readFully` loops until enough bytes are read. The result still decodes DATA and PING correctly, proving that framing does not depend on how the byte stream is split.

This only simulates **fragmented reads**, not a test of actual TCP packet fragmentation models. The behavior to guarantee is that the decoder handles **any valid partition of the byte stream**, not "one packet per frame".

### 11.2. Stream Start, EOF, and Frame Errors

`readFrame` reads the first byte before requesting the next 15 bytes to distinguish:
- No bytes at the start of a new frame → return `null` (clean EOF).
- A few header bytes present but missing the rest → `EOFException`.
- Complete header but missing payload bytes → `EOFException`.
- Header reports length 1_048_577 → `IOException("length")` **before payload allocation**.

Do not catch every `EOFException` and treat it as "no message", because a stream ending mid-frame means the data is **incomplete**. In a real application, you should typically log/count a protocol error metric and close the connection.

### 11.3. Synchronization Between Client and Server

The server receives `DATA` and `PING` in sequence, then sends `ACK` with requestId 42. The client reads ACK on the same connection and matches the ID. Binding the server to `127.0.0.1` means the program needs no Internet connection or external services. `ServerSocket(0, ...)` asks the OS to pick an available port, avoiding fixed-port conflicts.

`setSoTimeout(3000)` causes a blocking read/accept to fail if there is no progress within the socket timeout. It **is not a total deadline for the entire frame**: a peer could trickle a few bytes across many reads. Production needs an overall time budget, socket limits, and policies against slow clients.

### 11.4. Record `Frame` and Data Safety

`Frame` copies `payload` on creation and when returned via the accessor so external code cannot silently mutate the frame's `byte[]`. However, each clone uses extra memory; production may use an immutable byte buffer/slice, zero-copy, or bounded allocation mechanisms if optimization is needed. That is a separate performance decision and must not affect the wire contract.

## 12. Does the Algorithm Change If Moving to NIO/Netty?

The frame contract does not change; only how bytes are accumulated changes.

With `SocketChannel` and `ByteBuffer`:
- A single `channel.read(buffer)` may return 0 or fewer bytes than needed. In non-blocking mode, 0 only means "no data available right now"; it is not EOF.
- When fewer than 16 header bytes are available, stay in `READ_HEADER` state and keep the received bytes in the buffer.
- Full header → parse and validate length → transition to `READ_BODY`, continuing to accumulate exact N bytes.
- Full body → dispatch one frame → transition to `READ_HEADER` for the next frame; if the buffer still has bytes, continue parsing, because there can be **multiple frames in a single read**.
- When writing, `SocketChannel.write(ByteBuffer)` may write **fewer than the remaining bytes**; you must continue until the buffer is empty or register for writable events, avoiding the assumption that one write sends the whole frame.

Netty provides `LengthFieldBasedFrameDecoder` for length-prefixed protocols, but its configuration must match **offset=12, fieldLength=4, lengthAdjustment, and initialBytesToStrip** according to the protocol's exact definition. If length only counts the payload and the header is 16 bytes long, the total frame length must be computed accurately. Even with a built-in decoder, you still need **maxFrameLength**, version/type/flags validation, and byte-order handling.

For high-performance systems, a large frame can be processed via streaming instead of allocating everything into a single `byte[]`; however, streaming requires the parser to know how to accurately skip/drain when a request is rejected without breaking the boundary of the next frame.

## 13. Length Design Flaws and Resource Limits

A `payloadLength` field is convenient, but it is also an attack vector if you trust the sender:

1. **Reading length before validating:** if the receiver sees length `4_000_000_000` and tries to allocate a buffer, it can overflow or run out of memory. In the demo, 4 bytes are read into a signed `int`; negative values or values > 1 MiB are rejected.
2. **Confusing total length with payload length:** the sender writes `16 + payload.length` while the receiver treats it as the body byte count → reads into the next frame's header and loses synchronization.
3. **Confusing bytes with character count:** UTF-8 is multi-byte, such as `Xin chào` having a 9-byte payload. Do not use `String.length()` as the length when the body is encoded.
4. **Not limiting concurrent frames:** a 1 MiB max frame can still cause DoS if the server allows thousands of concurrent connections or pending requests.
5. **Limiting only compressed length:** if compression is later enabled, you also need limits on **decompressed** data size, compression ratio, CPU, time, and nesting.
6. **Not limiting rate/progress:** a peer sending 1 byte every few seconds can occupy a slot for too long. You need a full-frame deadline, idle timeout, quotas, and backpressure.
7. **Allocating by length before reading/validating the header:** you must verify magic, version, flags, type, and length first; payload format validation happens once the full body is received.
8. **Not handling connection close mid-message:** if the body is incomplete, reject it; do not carry remaining body bytes into a new request.

A policy should clearly define at minimum `MAX_PAYLOAD`, `MAX_CONNECTIONS`, the number of unacknowledged requests, the time to read 1 frame, queue sizes, and memory usage thresholds. Limits beyond length depend on the service type; there is no single number that fits every system.

## 14. Connection Session Management, Ordering, and Backpressure

### 14.1. One Connection Can Carry Multiple Frames

If the same connection sends consecutively:

```text
DATA(id=41,len=100) | DATA(id=42,len=250) | PING(id=0,len=0)
```

The decoder must read:
1. Exactly 16 + 100 bytes for frame ID 41.
2. Exactly 16 + 250 bytes for frame ID 42.
3. Exactly 16 bytes for PING.
4. Only then wait for the next frame or EOF.

Do not `read` "until the socket closes" and treat the entire connection as one message, because the protocol allows **multiple messages on a long-lived connection**.

### 14.2. Pipelining, Multiplexing, and Delayed Responses

TCP delivers bytes in order; the application might process DATA ID 42 faster than DATA ID 41 and send ACKs out of order if the protocol permits. If the protocol requires responses to preserve order, the server must enforce it. If out-of-order responses are allowed, the client needs a `requestId → pending request` map with timeouts, cleanup, and a limit on entry count.

`requestId` helps **correlate**, and does not replace:
- Database transaction IDs.
- Idempotency keys with guaranteed scope and TTL.
- Authorization tokens or session identity.
- TCP sequence numbers (which live at a different layer).

If the stream closes after the client sends DATA but before seeing ACK, the client **cannot know for sure** whether the server committed or not from TCP state alone. Retries require an idempotency/ack mechanism with business meaning.

### 14.3. Slow Readers and Output Queues

If the receiver processes slowly, TCP flow control will slow down the sender; however, the application can still accumulate millions of frames in its own queue before writing. You need:
- Limits on queue size, in-flight requests, and total pending bytes.
- Backpressure: pause reading / reject requests / signal overload according to the contract.
- Do not spawn unbounded new threads per frame.
- A single write path guaranteeing that **each frame's header and body do not interleave** with another frame.
- Clear timeouts and request cancellation, releasing buffers on disconnect.

With Java blocking I/O, you can use a bounded per-connection worker or a pool; with NIO/Netty, manage state machines, event loops, and watermarks. The specific mechanism differs, while the wire contract remains the same.

## 15. Protocol Errors: Return ERROR or Close the Socket?

Not every error should send an ERROR frame.

| Situation | Recommended handling |
| --- | --- |
| Valid DATA but business logic rejects it, parser still in sync | Can return `ERROR` with requestId and specified error code |
| Invalid magic or unsupported version | Reject/close connection; do not guess how to interpret the header |
| Unsupported flags/type | Per v1.0 policy: reject frame and close; another revision may have negotiated optional types |
| Negative/oversized length | Reject immediately, close socket; do not attempt to drain an untrusted body |
| EOF mid-header/body | Truncated frame, discard incomplete data and close |
| Read timeout mid-frame | Close or abort connection per protocol; do not reuse old bytes as a new frame |
| JSON/Protobuf payload fails schema but header is valid | If the full body has been read and the protocol allows it, return `ERROR`; never lose synchronization |

When returning ERROR, avoid turning the parser into an unbounded error-data reflector, such as echoing back an entire sensitive payload sent by the client. Each ERROR should have a machine-readable error code, a maximum content size, and versioning rules. For severe wire errors, closing the connection cleanly is usually simpler and safer than "self-recovery".

**Why not scan for magic?** Arbitrary payloads can contain the byte sequence `JMSG`. Once the parser loses its position, a single magic match does not prove it is a real header. Resynchronization requires a dedicated design; the sample protocol does not support it.

## 16. Versioning, Rolling Upgrades, and Compatibility Control

Suppose there are three application versions:
- **A:** understands v1.0 headers, basic DATA/ACK/PING.
- **B:** wants to add a new message type while keeping the 16-byte layout.
- **C:** wants compressed payloads via flags, an added checksum, or a larger max frame.

Questions to ask in order:

1. **Can old peers safely recognize the new frame?** With the demo code, any unknown type or non-zero flags are rejected, so B/C cannot unilaterally enable new features while client A is still around.
2. **Do we need to keep a v1.0 endpoint?** If the new version breaks syntax or semantics, maintain the old decoder on a separate endpoint or route by version/handshake.
3. **Is a "skip unknown" spec valid?** Only when length/schema and optional semantics are specified; for types that must be processed, skipping loses business logic.
4. **Is there a capability-selection handshake?** For example, a new version defines HELLO with a list of `(major,minor,features)`, and the receiver picks the intersection; however, the handshake itself must have a base format recognized by both sides.
5. **Is bidirectional communication tested?** Old client ↔ new server, new client ↔ old server, downgrade, migration, rolling restart, and rollback.
6. **Do logs have enough metadata for debugging?** Record version, type, requestId, length, and error code (avoid logging raw sensitive payloads).

A practical rollout approach: first update servers to understand both v1 and v2; next release clients capable of negotiation; finally drop v1 when telemetry proves no clients still depend on it. **Do not automatically bump minor and assume both sides are always compatible.**

## 17. Deterministic Wire Protocol Testing

The demo already tested:
- Reading two consecutive frames from the same stream.
- Returning the same messages when bulk-read is capped at 3 bytes per call.
- Exact header bytes and a UTF-8 length of exactly 9.
- Clean EOF at the boundary between frames.
- Missing body bytes → `EOFException`.
- Length exceeding 1 MiB → rejected before allocation.
- TCP loopback client/server in the same process, DATA + PING and ACK with the same requestId.

A production test suite should expand to:

| Case | How to construct | Expectation |
| --- | --- | --- |
| Split header | Have stream return 1..15 bytes first, remainder later | Decoder waits for full header |
| Split body | Send 1 byte at a time up to exact length | Decoder reassembles full payload |
| Coalesced frames | Push all bytes of 100 frames into a single read | Decodes all 100 frames in order |
| Truncated header | Cut first 1..15 bytes of frame then EOF | Reports truncated header |
| Truncated body | Header declares N, send only N-1 then EOF | Reports truncated body |
| Wrong magic | Corrupt 1 byte at offset 0..3 | Reject |
| Wrong major/minor | Modify offset 4/5 | Reject v1.0 |
| Wrong type | Set byte offset 6 to 0 or 255 | Reject |
| Unsupported flags | Offset 7 non-zero | Reject |
| Invalid requestId | PING with non-zero ID, DATA with ID 0 | Reject |
| Negative/huge uint32 length | Set 4 bytes at offset 12 to `FF FF FF FF` | Reject before allocation |
| Boundary lengths | Test 0, 1, 1_048_576, 1_048_577 | Accept/reject at exact limit |
| UTF-8 payload | Use ASCII, Vietnamese diacritics, emoji | Length = UTF-8 byte count |
| Type schema mismatch | ACK with nonsensical payload | Schema error per contract |
| Parallel writes | Have multiple producers write to same socket | No interleaved bytes between frames |
| Slowloris / slow send | Send 1 byte slowly and stall mid-frame | Bounded deadline/timeout |
| Connection lost awaiting ACK | Close socket after server reads DATA | Retry/idempotency per contract |
| Old/new peers | Every supported and unsupported version pair | Negotiate/reject per spec |

Fuzzing combinations of 16-byte headers, boundary lengths, invalid UTF-8, partial-byte states, and unknown types helps catch bugs before production. Do not stop at the "send once, receive once on localhost" happy path: loopback often hides packet fragmentation/aggregation and backpressure scenarios.

## 18. Common Mistakes

1. **"One `write` is one message; one `read` is too."** False: TCP only preserves the byte stream and order, not the message boundaries called by the application.
2. **"`available() == 0` means end of frame."** False: `InputStream.available()` only estimates bytes readable without blocking; never use it to determine protocol boundaries or EOF.
3. **"One `read(byte[])` call is enough to get the 16-byte header."** False: read may return fewer bytes; use `readFully` or a state machine.
4. **"Length is `String.length()`."** False: you must use the UTF-8 encoded byte count.
5. **"The length field is 4 bytes, so allow up to 4 GiB arbitrarily."** False: real resources need limits; never allocate based on untrusted values.
6. **"Integers in Java handle unsigned automatically."** False: `byte` and `int` are signed; you must define wire byte interpretation and validate bounds.
7. **"Matching endianness to the host platform is faster."** False: a protocol needs a fixed byte order to interoperate across systems.
8. **"Adding a new type is always a compatible change."** False: old clients may reject it, misparse it, or lack required handling; a version/feature policy is needed.
9. **"A higher minor version is always allowed."** False for the strict 1.0 demo; only allow it once compatibility and negotiation mechanisms are specified.
10. **"TCP ACK means the server finished processing."** False: that is a TCP-layer acknowledgment; application ACK must have defined semantics.
11. **"Magic is enough to verify data is safe."** False: magic provides no authentication, confidentiality, or integrity.
12. **"Each thread writing a frame to the same socket is safe."** Not necessarily: bytes of different frames can interleave; use a one-writer queue or synchronized write.
13. **"EOF is always a normal end of message."** False: EOF mid-header/body means a truncated frame.
14. **"Catching IOException and continuing to read is fine."** False if the parser has lost boundary alignment; on severe wire errors, close the connection and handle reconnect per protocol.

## 19. Applying It: Choose the Contract Before Coding

**Scenario A — IoT device sending measurements every second:** payloads may be only a few bytes; you can choose a fixed frame or minimal length-prefixed frame. Even so, you still need version/type/length or clear limit rules, reconnect recovery, and rate control.

**Scenario B — Internal RPC with many concurrent requests:** headers should have a correlation ID and DATA/RESULT/ERROR types. Per-request timeouts, idempotency, out-of-order response handling, and in-flight limits are needed. At large scale, evaluate gRPC/HTTP/2 before inventing a binary protocol.

**Scenario C — Large payloads or streaming:** a 32-bit length field and buffering a full 1 MiB may not fit. Clearly define chunk framing, stream IDs, total size, purpose-built checksums, and flow control, instead of silently raising MAX to hundreds of MiB.

**Scenario D — Zero-downtime upgrades:** old and new clients run side by side. Design a clear negotiation/version policy, telemetry on client counts per version, and a downgrade/rollback plan; do not send new types to peers that have not declared support.

A checklist before finalizing the protocol:
- Who owns the spec? Is there documentation for byte offsets, byte order, length semantics, and test vectors?
- What payload schema does each type carry? Do header/version affect the schema?
- Which `(major, minor)` pairs are supported, and how are unknown versions handled?
- How do sender/receiver limit size, time, and requests/connections?
- What encryption/authentication, application checksums, logs, and metrics exist?
- How are mid-frame errors, timeouts, reconnects, duplicate requests, and replays handled?
- Do we need one long-lived connection, multiple connections, or streaming/chunking?

## 20. Security: Framing Is Only the Foundation

A valid header does not prove a trustworthy client. The application protocol must place other mechanisms at the right layers:
- **TLS** for channel confidentiality and peer authentication where appropriate, with trusted certificate configuration; do not send sensitive credentials over plaintext TCP just because magic/version exist.
- **Authentication/authorization** per connection or request; `requestId` is not a token.
- **Application integrity** if the problem requires checksums/hashes/signatures on the payload; checksums detect accidental corruption but do not replace MACs/cryptographic signatures.
- **Resource management**: max frame, total bytes, timeouts, concurrency, backpressure, buffer pooling, and quotas.
- **Parser limits** for payload schemas, decompressed sizes, nested structures, and malformed input.
- **Observability**: count rejected magic/version/type/length, truncated frames, processing time, and queue depth; avoid logging raw payloads containing personal/secret data.

Never use a custom binary header as a substitute for a security system or to redefine TCP semantics.

## 21. Self-Check Questions

**1. The client calls `write(frame1)` and `write(frame2)` back-to-back. Is the server guaranteed to get two `read` calls?**  
No. The server may get more or fewer `read` calls depending on TCP/buffering. Only framing based on header+length accurately determines each frame.

**2. The header is 16 bytes, and the UTF-8 encoded body `Xin chào` is 9 bytes. What length should be written?**  
Write `9` because the field defines the number of body bytes, excluding the header and not using character count.

**3. The header reports payloadLength = 2_000_000 while MAX_PAYLOAD = 1_048_576. What must the decoder do?**  
Reject before allocating/reading the body, then handle the protocol error and close the connection per the v1.0 contract.

**4. Can v1.0 receiving `major=1, minor=1` simply ignore the minor version?**  
No: the demo only understands 1.0 and has no negotiation/extension mechanism yet, so it rejects it. A later version may only accept a new minor version according to a specific compatibility spec.

**5. What is the wire size of a PING with ID 0 and an empty body?**  
`16` bytes: exactly one header, with zero payload bytes.

**6. The server returns ACK ID 42, but the client is waiting for ID 43. Can request 43 be considered done?**  
No. The correlation ID must be matched against the pending request; TCP ACK does not replace business ACK either.

**7. Why is missing 1 payload byte followed by EOF different from EOF before seeing the next header?**  
Missing payload bytes means an incomplete frame; EOF at the boundary between frames can be treated as a clean end of stream.

**8. If you want to add compression via flags without breaking old clients, what is needed?**  
You need an exact specification of the bit/algorithm, decompressed size limits, and negotiation/capability or a new version. Old v1.0 clients reject non-zero flags.

## 22. References

- RFC 9293 — Transmission Control Protocol, `3.7 Segmentation: https://www.rfc-editor.org/rfc/rfc9293
- Java SE 17 `DataInputStream` / `readFully` / `EOFException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html
- Java SE 17 `DataOutputStream` and byte order in `writeInt`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html
- Java SE 17 `ByteBuffer` and `ByteOrder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Java SE 17 `Socket` / `ServerSocket`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17 `HexFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HexFormat.html
- RFC 2119 — Key words for use in RFCs to Indicate Requirement Levels: https://www.rfc-editor.org/rfc/rfc2119
