# Determining Message Boundaries over TCP: Fixed Length, Delimiter, and Length Prefix

**TCP transmits an ordered, reliable byte stream; it does not transmit "messages" with built-in boundaries.** If an application needs to send sequential `PING`, `PONG` messages or JSON objects, both ends of the connection must agree on a **message framing protocol** to know which bytes belong to which message. Three common approaches are **fixed length**, **delimiter**, and **length prefix**.

This lesson focuses on designing, encoding, and reading these three frame types over TCP using Java 17+, including handling partial reads, UTF-8, EOF, size limits, timeouts, and protocol desynchronization cases. Examples run both in memory and over loopback TCP, showing that the same framing rules apply to any `InputStream`/`OutputStream`.

After this lesson, you will be able to:

- Explain why a single `write()` call on the sender does not correspond to a single `read()` call on the receiver.
- Choose one of the three framing protocols based on data characteristics.
- Write a reader capable of assembling bytes received in chunks, reading multiple consecutive frames, and detecting truncated frames.
- Handle length in **bytes** and avoid bugs when strings contain multi-byte Unicode characters.
- Use `DataInputStream.readFully()`, `DataOutputStream.writeInt()`, and appropriate size/timeout policies.

## 1. The Nature of TCP: A Byte Stream with No Message-End Marker

Suppose the sender creates two messages:

~~~text
Application sends: "HELLO"        "WORLD"
send/write:        [ H E L L O ]  [ W O R L D ]

TCP byte stream seen by receiver:
                   H E L L O W O R L D
~~~

The receiver may receive them in many ways, all valid:

~~~text
Read 1:       HELLOWORLD
or
Read 1:       HE
Read 2:       LLOW
Read 3:       ORLD
or
Read 1:       H
Read 2:       E
...
~~~

**There is no guarantee that a single `InputStream.read(byte[])` call returns an entire frame, or returns exactly one frame.** A call may return fewer bytes than requested; a read may see the tail of the previous frame and the head of the next frame. At the transport layer, TCP guarantees byte ordering and retransmits data when possible; at the application layer, **you must define message structure yourself**.

You cannot use IP packet size, MTU, TCP segments, the PSH flag, or the number of `flush()` calls to infer message boundaries. `flush()` only pushes data currently buffered by wrappers (if any) down to the underlying layer; it **does not create a delimiter** on the TCP stream.

### Java I/O Behaviors to Remember

| API | What Is Actually Guaranteed | What Not to Assume |
| --- | --- | --- |
| `InputStream.read()` | Returns a byte 0–255 or `-1` on EOF | `-1` means end of **frame**; it actually means EOF of the stream |
| `InputStream.read(byte[])` | Returns the number of bytes read, which may be less than buffer length; `-1` on EOF | A single read always returns all data the application needs |
| `DataInputStream.readFully(byte[])` | Loops reading until the requested number of bytes is read or throws `EOFException` | It knows the message size; the size must be provided by the protocol |
| `DataInputStream.readInt()` | Reads exactly four bytes and interprets them as a signed big-endian integer | Reading the prefix means the payload has definitely arrived |
| `InputStream.available()` | Estimates bytes that can be read immediately without blocking | Total frame size or all data that will arrive |
| `InputStream.readAllBytes()` | Reads until EOF | Suitable for a single message on a long-lived TCP connection |
| `Socket.setSoTimeout(ms)` | Limits blocking time for socket read operations; throws `SocketTimeoutException` on expiration | Timeout alone can determine frame boundaries |

**Buggy example:** the sender calls `out.write(bytesOfA)` then `out.write(bytesOfB)`; the receiver calls `in.read(buffer)` once and assumes `buffer` contains exactly message A. The program may "work on localhost" but fail when data arrives fragmented or multiple messages are coalesced.

## 2. Framing Is a Protocol Contract

Before coding, both sides must agree on:

1. **How does a frame start and end?** Fixed 4 bytes, terminated by LF, or a 4-byte length header?
2. **What unit is length measured in?** With TCP, always specify the exact number of bytes on the wire, never ambiguously Java characters.
3. **How is data encoded?** ASCII, UTF-8, binary, JSON? Is the delimiter allowed inside the payload?
4. **What is the maximum limit?** Bound memory/CPU when a peer sends an oversized length or string.
5. **How is socket EOF handled?** EOF mid-frame is usually an error/truncation; EOF right at a frame boundary can be a normal connection close.
6. **What about multiple consecutive frames?** Must continue reading from the exact byte after the previous frame, without dropping leftover bytes or misreading into another frame.
7. **Are protocol errors recoverable?** With TCP, if the parser loses boundary alignment and cannot safely resynchronize, you usually must close the connection.

Three strategies on the wire:

~~~text
A. Fixed length, N = 4 bytes:
    [P I N G][P O N G]
     frame 1  frame 2

B. LF delimiter (byte 0A):
    [H E L L O 0A][W O R L D 0A]
     frame 1       frame 2

C. Length prefix, 4-byte big-endian header:
    [00 00 00 05][H E L L O][00 00 00 05][W O R L D]
     length = 5   payload    length = 5   payload
~~~

Each frame in the example is sent consecutively over the same TCP connection. The receiver must read according to the agreed format; TCP does not notify the application that a "frame is complete."

## 3. Option 1: Fixed-Length Framing

If every message is **exactly N bytes** long, the receiver simply reads N bytes for one frame and repeats:

~~~text
Protocol: each message is exactly 4 ASCII bytes

Wire:   P I N G P O N G
        |-------|-------|
         frame 1  frame 2

READ_4_BYTES -> EMIT -> READ_4_BYTES -> EMIT -> ...
~~~

In Java, `DataInputStream.readFully(byte[])` is a straightforward choice for this protocol:

~~~java
// Snippet: use in a method permitted to handle IOException.
DataInputStream input = new DataInputStream(socket.getInputStream());
byte[] frame = new byte[4];
input.readFully(frame); // Read all 4 bytes or throw EOFException.
~~~

**Condition:** all senders must write exactly 4 bytes per frame; the receiver reads with the exact same N. If a sender sends 1 byte short and starts the next frame, the receiver will consume the first byte of the next frame to compensate, and all subsequent boundaries will be misaligned.

For messages with fixed fields like `type(1 byte) + requestId(4 byte) + status(1 byte)`, a 6-byte frame can make sense. However, if actual content varies in length, you must clearly define **padding**, pad bytes, and unpadding rules; arbitrarily truncating payloads causes data loss.

### Characters Are Not Bytes

In Java, `String.length()` counts UTF-16 code units, not UTF-8 byte length. For example:

~~~java
String s = "cà";
System.out.println(s.length()); // 2 UTF-16 code units
System.out.println(s.getBytes(java.nio.charset.StandardCharsets.UTF_8).length);
// 3 UTF-8 bytes: 'c' = 1 byte, 'à' = 2 bytes
~~~

Therefore, a **"4-byte"** protocol does not mean **"4 characters."** If a fixed frame contains UTF-8 text, only slice at valid byte boundaries and define padding clearly; for variable-length text data, delimiter or length prefix is usually preferred.

**Pros:** simple parser, near-zero overhead; suitable for binary records of known size.  
**Cons:** wastes padding on short messages; inflexible for large/variable payloads; loses sync if sides disagree on N.

## 4. Option 2: Delimiter Framing

The sender writes the payload followed by **an agreed delimiter**, such as newline LF `\n` (byte `0A`):

~~~text
Protocol: UTF-8 text, each frame terminated by LF (0x0A)

Wire:   x i n ... 0A o k 0A
        |---------|------|
          frame 1  frame 2
~~~

The reader reads byte by byte or uses a stateful buffer, stopping when it encounters the delimiter. Only after a complete frame is assembled are the payload bytes converted to a UTF-8 string. If you decode each chunk before assembling, a Unicode character split across two reads can become corrupted data.

A line-based application can use `BufferedReader.readLine()` if the protocol is truly text and Java's CR/LF/CRLF conventions fit. However, `readLine()` strips line terminators; it accepts multiple line-ending types rather than just a single LF byte, and `BufferedReader` may read ahead past boundaries. **Do not mix `BufferedReader` directly with another binary reader on the same `Socket.getInputStream()`** unless buffers are managed uniformly.

### When the Delimiter Appears in the Payload

Suppose the protocol uses LF as the terminator, but the user sends:

~~~text
Line 1
Line 2
~~~

If sent raw with `\n`, the receiver will interpret this as **two frames**. You must agree on one of these approaches:

- **Forbid the delimiter** in the payload and validate when sending; for example, single-line text commands.
- **Escape the delimiter** with a clear grammar, such as converting `\n` inside the payload to two literal characters `\` and `n`; the reader must unescape after finding boundaries and handle the escape character itself.
- **Encode the payload** so it cannot contain the delimiter (e.g., base64), accepting the overhead.
- **Switch to length-prefix** if the payload is binary/multi-line JSON or may contain arbitrary bytes.

Do not simply call `String.split("\n")` on individual chunks returned by `read()`: the delimiter may lie at a chunk boundary, and leftovers must be retained across reads.

### Limits and EOF

The reader should count **payload bytes** since the previous delimiter and enforce a limit, such as 1 KiB max. If LF is not seen before exceeding the limit, report an error and usually close the connection; do not wait indefinitely letting the buffer grow forever.

Cases must be clearly defined:

| Received Data | Illustrative LF-Only Convention |
| --- | --- |
| `hello\n` | One frame with payload `hello` |
| `\n` | One empty frame (valid if protocol allows) |
| `hello\nok\n` | Two consecutive frames |
| `hello` then TCP EOF | Incomplete frame; **protocol error** |
| TCP EOF right after `\n` or before any bytes | EOF at boundary; can be treated as normal end of stream |

With CRLF, the delimiter must be **two bytes** `0D 0A`, and the reader must check/strip it according to the contract; do not let stray `\r` bytes leak into the payload if the protocol requires CRLF.

**Pros:** easy to inspect with telnet/netcat/logs, flexible for line-oriented text, small overhead.  
**Cons:** requires escaping or payload restrictions; reader must scan for delimiter and enforce size limits; not ideal for unrestricted binary data.

## 5. Option 3: Length-Prefixed Framing

Before each payload, the sender writes a header carrying the **payload byte count**, then writes that exact number of bytes. For example, a protocol using a 4-byte **signed big-endian int** length and UTF-8 payload:

~~~text
Text:       "xin chào"
UTF-8:       9 bytes

Frame:
    00 00 00 09 | 78 69 6E 20 63 68 C3 A0 6F
    -----------   --------------------------
    length = 9           UTF-8 payload
~~~

**Receive flow:**

1. Read **all 4 header bytes**.
2. Interpret as a 32-bit big-endian integer.
3. Validate `0 <= length <= MAX_FRAME_BYTES` **before allocating** a buffer.
4. Read **exactly `length` bytes** using `readFully` or an equivalent loop.
5. Decode the payload according to the agreed encoding and process the message; continue reading the next frame.

Parser states:

~~~text
[READ_HEADER_4]
      |
      v
[VALIDATE_LENGTH] -- invalid (<0 or >MAX) --> [REJECT/CLOSE]
      |
      v
[READ_EXACT_BODY_N] -- EOF mid-body --> [TRUNCATED/CLOSE]
      |
      v
[EMIT_MESSAGE]
      |
      +------------------------------> [READ_HEADER_4]
~~~

Java natively supports the network byte order of this example:

~~~java
// Snippet: use in a method that throws/catches IOException.
byte[] body = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
DataOutputStream out = new DataOutputStream(socket.getOutputStream());
out.writeInt(body.length); // 4-byte big-endian.
out.write(body);

DataInputStream in = new DataInputStream(socket.getInputStream());
int length = in.readInt(); // Header only: 4 bytes.
if (length < 0 || length > 1024 * 1024) {
    throw new IOException("Invalid frame length");
}
byte[] received = new byte[length];
in.readFully(received); // Full payload bytes, regardless of how many reads TCP splits it into.
~~~

This is a **two-sided illustrative snippet**: having `out` and `in` on the same socket does not mean the program has set up both server/client sides or a request-response protocol; each part must be placed in its respective side's logic in the proper order. The 1 MiB limit is only an example and must be chosen per system.

**Count length after encoding:** `"xin chào"` has 8 visible Unicode characters but **9 UTF-8 bytes**. The header must be `9` because the receiver reads bytes. Never use `String.length()` as the length.

**Endianness and signedness:** `DataOutputStream.writeInt` and `DataInputStream.readInt` both use big-endian, but other languages must be configured identically. Java's `int` is signed; if a negative value or a value larger than the allowed limit is received, reject immediately. The prefix could be `uint16`/`uint32`, varint, or another size, but both sides must share the same specification; never change one side to a different format unilaterally.

**Pros:** suitable for binary, multi-line JSON, UTF-8 with internal delimiters; knows the exact byte count to read, easy to send multiple consecutive frames.  
**Cons:** has prefix overhead; must validate length before allocating, handle truncated headers/bodies, and protect against unrealistic sizes.

## 6. Comparing the Three Options

| Criterion | Fixed Length | Delimiter | Length Prefix |
| --- | --- | --- | --- |
| How boundaries are detected | Count exact `N` bytes | Scan for delimiter byte/sequence | Read header then exact byte count |
| Overhead | None (but may require padding) | Delimiter/escape cost | Header size, e.g. 4 bytes |
| Variable-length payload | Inconvenient | Yes | Yes |
| Delimiter inside payload | No issue since N is known | Must escape/forbid/encode | Can contain any byte |
| Binary data | Good for fixed records | Difficult if delimiter can appear | Suitable |
| Line-oriented text | Somewhat awkward | Very natural | Suitable |
| Notable risk | Boundary shift from wrong N | Unbounded frame if delimiter missing | Huge fake prefix, memory allocation |
| State parser must keep | Remaining bytes of N | Bytes awaiting delimiter + escaping | Missing header bytes, length, missing body bytes |

Situational guidance: small commands of exactly 4 bytes use fixed; text protocols with one command per line using LF and clear escaping rules use delimiter; variable payloads or mixed binary usually choose length-prefix. None of these options replaces timeouts and resource limits.

## 7. Java 17+ Program: One Stream, Correctly Reading All Three Framing Styles

The following example creates multiple consecutive frames using `ByteArrayOutputStream`, then reads them through a simulated `InputStream` where **each `read(byte[])` returns at most 1 byte**. This technique does not create real TCP, but demonstrates that the parsers still work when data is fragmented as in TCP.

Create file **`FramingDemo.java`** (UTF-8):

~~~java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.*;

public class FramingDemo {
    private static final int FIXED_BYTES = 4;
    private static final int MAX_PAYLOAD = 1024;

    private static String strictUtf8(byte[] bytes)
            throws CharacterCodingException {
        return StandardCharsets.UTF_8.newDecoder()
                .onMalformedInput(CodingErrorAction.REPORT)
                .onUnmappableCharacter(CodingErrorAction.REPORT)
                .decode(ByteBuffer.wrap(bytes))
                .toString();
    }

    // Each message is fixed at exactly 4 bytes.
    private static void writeFixed(OutputStream out, byte[] payload)
            throws IOException {
        if (payload.length != FIXED_BYTES) {
            throw new IllegalArgumentException("expected 4 bytes");
        }
        out.write(payload);
    }

    private static byte[] readFixed(DataInputStream in) throws IOException {
        byte[] payload = new byte[FIXED_BYTES];
        in.readFully(payload);
        return payload;
    }

    // LF-only protocol; sender forbids CR/LF in payload.
    private static void writeDelimited(OutputStream out, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        if (text.indexOf('\n') >= 0 || text.indexOf('\r') >= 0
                || data.length > MAX_PAYLOAD) {
            throw new IllegalArgumentException("invalid LF record");
        }
        out.write(data);
        out.write('\n');
    }

    // null means EOF right at a frame boundary, when no payload bytes have been read yet.
    private static String readDelimited(InputStream in) throws IOException {
        ByteArrayOutputStream body = new ByteArrayOutputStream();

        while (true) {
            int b = in.read();
            if (b < 0) {
                if (body.size() == 0) {
                    return null;
                }
                throw new EOFException("partial LF record");
            }
            if (b == '\n') {
                return strictUtf8(body.toByteArray());
            }
            if (body.size() >= MAX_PAYLOAD) {
                throw new IOException("record too large");
            }
            body.write(b);
        }
    }

    // 4-byte big-endian header containing the UTF-8 byte count of the body.
    private static void writePrefixed(DataOutputStream out, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_PAYLOAD) {
            throw new IllegalArgumentException("message too large");
        }
        out.writeInt(data.length);
        out.write(data);
    }

    private static String readPrefixed(DataInputStream in)
            throws IOException {
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD) {
            throw new IOException("invalid length");
        }
        byte[] body = new byte[length];
        in.readFully(body);
        return strictUtf8(body);
    }

    // Simulate read(byte[]) returning at most 1 byte at a time.
    private static InputStream oneByteAtATime(byte[] bytes) {
        return new FilterInputStream(new ByteArrayInputStream(bytes)) {
            @Override
            public int read(byte[] b, int off, int len)
                    throws IOException {
                if (len == 0) {
                    return 0;
                }
                return super.read(b, off, Math.min(len, 1));
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ByteArrayOutputStream fixed = new ByteArrayOutputStream();
        writeFixed(fixed, "PING".getBytes(StandardCharsets.US_ASCII));
        writeFixed(fixed, "PONG".getBytes(StandardCharsets.US_ASCII));
        try (DataInputStream in = new DataInputStream(
                oneByteAtATime(fixed.toByteArray()))) {
            System.out.println("Fixed: "
                    + new String(readFixed(in), StandardCharsets.US_ASCII)
                    + " | "
                    + new String(readFixed(in), StandardCharsets.US_ASCII));
        }

        ByteArrayOutputStream delimited = new ByteArrayOutputStream();
        writeDelimited(delimited, "xin chào");
        writeDelimited(delimited, "ok");
        try (InputStream in = oneByteAtATime(
                delimited.toByteArray())) {
            System.out.println("Delimiter: "
                    + readDelimited(in) + " | " + readDelimited(in));
        }

        ByteArrayOutputStream prefixed = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(prefixed)) {
            writePrefixed(out, "xin chào");
            writePrefixed(out, "hi");
        }
        try (DataInputStream in = new DataInputStream(
                oneByteAtATime(prefixed.toByteArray()))) {
            System.out.println("Length-prefixed: "
                    + readPrefixed(in) + " | " + readPrefixed(in));
        }

        // Header declares 5 bytes, but the payload only has 2 bytes.
        ByteArrayOutputStream cut = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(cut)) {
            out.writeInt(5);
            out.write(new byte[] {1, 2});
        }
        try (DataInputStream in = new DataInputStream(
                oneByteAtATime(cut.toByteArray()))) {
            readPrefixed(in);
        } catch (EOFException e) {
            System.out.println("Truncated: EOFException");
        }
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 FramingDemo.java
java FramingDemo
~~~

Output (UTF-8-capable terminal):

~~~text
Fixed: PING | PONG
Delimiter: xin chào | ok
Length-prefixed: xin chào | hi
Truncated: EOFException
~~~

**Points to observe:**

- `writeFixed` requires exactly 4 bytes per message. `readFully` receives all 4 bytes even though the underlying `read(byte[])` is capped at 1 byte.
- `writeDelimited` appends LF; `readDelimited` stops right at LF and preserves subsequent frames. It returns `null` when EOF occurs between two frames; EOF after a partial payload throws `EOFException`.
- `writePrefixed` writes the **byte length** before the body; `readPrefixed` checks the length and then calls `readFully`. UTF-8 messages can contain multi-byte characters.
- `strictUtf8` uses a reporting decoder instead of silently replacing invalid UTF-8 bytes with ``. It is applied **after** a complete frame is assembled.
- The last lines prove that when the header says 5 but only 2 payload bytes exist, the reader **must not treat those 2 bytes as a valid message**.

This is a test of **reading a fragmented stream**, not a simulation of all network behaviors (disconnection, latency, timeouts, TLS, flow control). It verifies a key principle: the parser does not depend on the size of each `read` call.

## 8. Running Length-Prefix over Real Loopback TCP

The following example starts a `ServerSocket` on loopback and a client connecting to the automatically assigned port. They use **the same 4-byte length-prefix format** and exchange one request and one response. The server thread serves only one connection for illustration. No Internet access is required.

Create file **`LengthPrefixTcpExample.java`**:

~~~java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class LengthPrefixTcpExample {
    private static final int MAX_FRAME = 4096;

    private static void send(DataOutputStream out, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        if (body.length > MAX_FRAME) {
            throw new IllegalArgumentException("too large");
        }
        out.writeInt(body.length);
        out.write(body);
        out.flush();
    }

    private static String receive(DataInputStream in) throws IOException {
        int n = in.readInt();
        if (n < 0 || n > MAX_FRAME) {
            throw new IOException("invalid length");
        }
        byte[] body = new byte[n];
        in.readFully(body);
        return new String(body, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> handled = pool.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(3000);
                        DataInputStream in =
                                new DataInputStream(peer.getInputStream());
                        DataOutputStream out =
                                new DataOutputStream(peer.getOutputStream());
                        String request = receive(in);
                        send(out, "ACK: " + request);
                        return request;
                    }
                });

                try (Socket client = new Socket(
                        InetAddress.getLoopbackAddress(),
                        listener.getLocalPort())) {
                    client.setSoTimeout(3000);
                    DataOutputStream out =
                            new DataOutputStream(client.getOutputStream());
                    DataInputStream in =
                            new DataInputStream(client.getInputStream());
                    send(out, "xin chào");
                    System.out.println("Client got: " + receive(in));
                }

                System.out.println("Server got: " + handled.get());
            } finally {
                pool.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 LengthPrefixTcpExample.java
java LengthPrefixTcpExample
~~~

Output when the loopback exchange succeeds:

~~~text
Client got: ACK: xin chào
Server got: xin chào
~~~

Both directions use **the same format but on two opposite streams**: the client writes the request to the client's output; the server reads from the peer's input. The server then writes the response; the client reads the response. `flush()` pushes data out of wrappers, but does not create a frame; the frame boundary is `writeInt(length)` followed by `length` bytes.

In the sample code, `new String(body, UTF_8)` suffices to display the valid payload sent. For untrusted input, reuse the **strict decoder** from `FramingDemo` or a dedicated format/schema validation mechanism. `setSoTimeout(3000)` here sets a 3-second read wait limit so the demo does not hang; production code must choose timeouts suited to actual latency and load, handle `SocketTimeoutException`, close sockets, and clean up resources.

**Demo limitations:** this is a single request-response exchange, not a production server with multiple clients, authentication, TLS, bounded thread pools, or retry systems. Those components do not change framing rules: both sides must parse the exact same byte structure.

## 9. EOF, Partial Reads, and Protocol Errors

In a TCP stream carrying multiple messages, **EOF is a state of the connection/read direction**, not a natural message terminator. Handling rules depend on the read position:

| Current Read State | EOF Received | Typically Correct Action |
| --- | --- | --- |
| Not yet started a new frame; all previous frames processed | Connection closed orderly | Can end the read loop normally |
| Waiting for N fixed-length bytes, only k bytes received with k < N | Truncated frame | Report error and stop processing |
| Reading a delimited frame with partial payload, delimiter not yet seen | Truncated frame | Report error |
| Only 1–3 of 4 prefix bytes received | Truncated header | Report error |
| Full prefix read, but body has fewer bytes than declared | Truncated payload | Report error |

`DataInputStream.readInt()` throws `EOFException` both when the peer has already closed right at the start of reading a header and when the header is mid-way through. If the application needs to distinguish "clean EOF between two frames" from "truncated header," it can read the first header byte separately: `-1` at the first byte is a clean EOF; if the first byte exists, require **the remaining header bytes** via `readFully`. Alternatively, the protocol can treat unexpected connection closure at any point as an error.

`InputStream.readNBytes(length)` can also return an array shorter than `length` when hitting EOF; if using this API, you must check `result.length == length`. Never treat "read some bytes" as success. On a socket kept open, `readAllBytes()` normally blocks until EOF, so do not use it in place of a frame-based reader.

### Timeouts Do Not Define Frames

`Socket.setSoTimeout(3000)` prevents socket read operations from blocking too long (raising `SocketTimeoutException`), but it **does not** mean "after 3 seconds the frame is over." If the peer may still send more, framing decisions must come from a fixed count, delimiter, or length. Timeouts are a resource-protection mechanism, often paired with an overall per-frame deadline, minimum throughput (slow sender), and connection-closing policies.

After detecting a negative/oversized prefix, invalid UTF-8, missing delimiter, or schema-invalid payload, avoid guessing where the next frame starts. When a stream loses synchronization, you should usually close the connection and log the error at an appropriate level; do not arbitrarily feed leftover bytes into another parser.

## 10. Memory, Performance, and Safety Controls

### Size Limits Are Mandatory

An untrusted peer can send prefix `0x7fffffff` (2,147,483,647 bytes) and then send no payload. If the application immediately allocates `new byte[length]` without checking, it can exhaust memory. Always:

- Check `length >= 0` and `length <= MAX_FRAME_BYTES` before allocating.
- Limit **bytes before finding a delimiter**; do not use `readLine()` on an unbounded source without size controls.
- For large allowed payloads, consider streaming/file chunk processing instead of holding everything in RAM, while still counting exact bytes to delimit frames.
- Maintain limits on concurrent connections, total memory, queues, and work per message.
- Set timeouts and support cancelling reads when a sender stops making progress.

### Text-to-Byte Conversion Must Be Consistent

Use `StandardCharsets.UTF_8`; do not rely on the machine's default charset. Convert text to bytes before computing the length prefix. Invalid UTF-8 bytes on the wire should be handled under an explicit policy (reject or replace), never silently altering message meaning. If there is an additional JSON/Protobuf schema, schema validation happens **after** the payload has been read accurately.

### Reading and Writing the Same Socket Is Stateful

- A TCP connection has **two byte-stream directions** (input and output). Each direction can use its own framing, but both sides must know the applied protocol.
- **One reader owns the input stream**, or a single dispatcher distributes bytes. Two threads reading `socket.getInputStream()` concurrently can steal bytes from each other, corrupting frames.
- If using `BufferedInputStream` or `BufferedReader`, understand that they **read ahead**: do not switch back and forth between different parsers on the same source without managing the same buffer.
- When multiple threads write to the same stream, they must synchronize at the **frame level** so header A is not interleaved with body B. Separate `writeInt` and `write` calls do not make the whole frame atomic across threads.
- `flush()` is not a message boundary and does not guarantee the peer has processed anything. Only a protocol acknowledgement tells you what step the remote application has confirmed receiving/processing.

### When to Add Version, Type, or Checksum?

In real-world protocols, a header may look like:

~~~text
[magic: 2 B][version: 1 B][type: 1 B][length: 4 B][payload: N B]
~~~

This is still length-prefix, just with a richer header. `magic` helps identify the protocol, `version` supports format evolution, and `type` classifies messages. Application-layer checksums can verify payloads per custom requirements, but **do not replace TLS** for security and authentication. When a receiver encounters an unknown version/type, it must have a clear rejection rule; do not attempt to parse the payload using a guessed format.

## 11. Common Mistakes

| Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| "Each `write` is one message" | Receiver gets merged/split messages when TCP fragments/coalesces | Design framing over the byte stream |
| Calling `read(buffer)` once without checking bytes returned | Partial read or mixing into next message | Loop reading until full frame or delimiter |
| Using `available()` as message length | Reads timing-dependent data, wrong frame | Get length from protocol |
| Using `readAllBytes()` to read a message while socket stays open | Waits indefinitely for EOF | Read up to frame boundary |
| Writing prefix using `String.length()` | Wrong for multi-byte UTF-8 Unicode | `getBytes(UTF_8).length` |
| Sender little-endian, receiver `readInt()` big-endian | Decodes wrong length | Specify consistent byte order |
| Allocating `new byte[length]` before checking | Easy OOM on malicious prefix | Check 0 ≤ length ≤ max first |
| Using LF delimiter when payload contains LF | One message split into many | Escape/forbid delimiter or change protocol |
| Forgetting to check EOF mid-header/body | Treats incomplete frame as complete message | `readFully` and handle `EOFException` |
| Decoding UTF-8 per TCP chunk | Multibyte character split and corrupted | Assemble full frame then decode, or use stateful decoder |
| Mixing `BufferedReader` and `DataInputStream` on same input | Read-ahead buffer steals bytes from the other parser | One parser owns stream and buffer |
| Multiple writers interleaving headers/bodies | Bytes from another frame interleave | Serialize/synchronize at frame level |
| Assuming `flush` corresponds to a complete packet/message | Protocol depends on TCP details | Delimit frames via application-layer rules |
| No limit on line/length | Memory exhaustion or long read blocking | Max frame, timeout, quota/backpressure |

## 12. Self-Check Exercises and Answers

**Exercise 1.** The sender calls `write("HELLO")` then `write("WORLD")`. The receiver calls `read(1024)` once. Is it guaranteed to receive `HELLO`?

**Answer:** No. The receiver may get a partial chunk, exactly 5 bytes, all 10 bytes, or another byte count depending on timing and buffers. Protocol framing must be used to determine boundaries.

**Exercise 2.** A fixed frame has N = 4 bytes; the receiver has received `AB` and then hits TCP EOF. Should it return message `AB`?

**Answer:** No. The frame requires exactly 4 bytes; EOF after 2 bytes is a truncated frame.

**Exercise 3.** An LF-delimited protocol receives `one\ntwo\n` in order across 3 reads: `"on"`, `"e\nt"`, `"wo\n"`. How many messages are there?

**Answer:** Two: `one` and `two`. The parser must retain partial payload across reads and never use the number of `read` calls to count messages.

**Exercise 4.** The UTF-8 payload is `xin chào` (8 visible characters). What value should the 4-byte big-endian prefix contain?

**Answer:** `9`, because the payload is 9 **UTF-8 bytes**; the prefix is `00 00 00 09`.

**Exercise 5.** A prefix declares 2 GiB when the system limit is 1 MiB. What should the reader do?

**Answer:** Reject immediately after checking the header and close/handle the error per protocol; never allocate 2 GiB waiting for the body.

**Exercise 6.** When can EOF be normal in LF-delimited framing?

**Answer:** When EOF occurs **right between two frames**, i.e., the last byte of the previous frame was LF and no partial payload remains. If payload bytes have arrived without an LF, that is an incomplete-frame error.

**Exercise 7.** Can you rely on `out.flush()` to know that the receiver has seen a complete message?

**Answer:** No. `flush` does not transmit application boundaries or acknowledgements. The receiver only knows a frame is complete when the parser has seen N bytes, the delimiter, or the full header+body.

**Exercise 8.** When a socket has two workers concurrently calling `read` on the same `InputStream`, what can happen?

**Answer:** Each worker can consume part of a frame that the other worker is parsing, causing desynchronization. There should be a single reader/dispatcher managing the stream or strict synchronization over the entire frame-reading process.

## References

- [Java SE 21 — `InputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html): contracts for `read`, `readNBytes`, `available`, and `readAllBytes`.
- [Java SE 21 — `DataInputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html): `readFully`, `readInt`, EOF.
- [Java SE 21 — `DataOutputStream`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataOutputStream.html): `writeInt`, big-endian format.
- [Java SE 21 — `Socket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html) and [`ServerSocket`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/ServerSocket.html): TCP byte streams, timeouts, and lifecycle.
- [RFC 9293 — Transmission Control Protocol (TCP)](https://www.rfc-editor.org/rfc/rfc9293): TCP provides a byte-stream service and does not carry application message boundaries.
