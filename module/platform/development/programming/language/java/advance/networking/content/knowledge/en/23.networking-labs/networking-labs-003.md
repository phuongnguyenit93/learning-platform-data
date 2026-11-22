# Splitting One Message Across Multiple Writes and Coalescing Multiple Messages Into One Write

## Objective of the Experiment

TCP carries an **ordered byte stream**, rather than transmitting a list of "messages" whose boundaries an application can automatically receive intact. Therefore:

- An application message can be **split across multiple `OutputStream.write(...)` calls** by the sender.
- Multiple messages can be **combined into a single byte array and sent with a single `write(...)` call** by the sender.
- On the receiving side, a single `InputStream.read(buffer)` call may receive **less than one message, exactly one message, multiple messages, or any arbitrary slice of them**; a program **must not rely on the byte count per `read` call to detect message boundaries**.
- TCP preserves byte ordering on a connection when delivery succeeds; it does **not** promise a correspondence between `write` calls and `read` calls, nor does it have any mechanism to "preserve application message boundaries."

This is a **Java 17+ Networking Lab**. We intentionally vary the **write shape on the sending side** while still requiring the receiver to recover **the exact same logical messages**. The right approach is to define an application-layer **framing** protocol, such as **4-byte length + payload**, **newline delimiter**, or fixed-size frames when appropriate for the contract.

The lab consists of four **standalone programs, compiled and verified on a Java 17-compatible JDK**:

1. `TcpWriteShapeLab.java`: one frame split across **3 write calls**, two other frames coalesced into **1 write call**, with the server receiving `[ALPHA, RED, BLUE]` over loopback.
2. `IncrementalFrameDecoderDemo.java`: feeds a decoder **arbitrary chunks**: a split header, a split payload, and then two frames in the same chunk.
3. `TruncatedFrameDefenseDemo.java`: distinguishes EOF at a valid frame boundary from a truncated header/body, and bounds the length to block oversized data.
4. `LineFramingLab.java`: a similar experiment using **`\n` delimiters** and `BufferedReader.readLine()`, clarifying the pros and cons of delimiter framing.

The examples use `127.0.0.1` and ephemeral ports, requiring no Internet access; `Socket` calls use reasonable timeouts. **Do not treat the number of `read` calls or TCP segments observed on one machine as a guarantee across all operating systems/JDKs.** What is established here is the ability to decode accurately regardless of chunking.

## 1. Distinguishing Message, Frame, Write Call, Read Call, and TCP Segment

Five concepts are easily confused:

| Concept | Layer | Preserves application message boundaries? |
|---|---|---|
| **Logical message** — "ALPHA", a JSON command, an RPC request | Application | Yes, **defined by the application** |
| **Application frame** — e.g., length-prefix + payload | Application protocol | Yes, **if both encoder and decoder agree on the contract** |
| **`OutputStream.write` call** — a single write to the stream | Java API | Does not create message boundaries on TCP |
| **`InputStream.read` call** — a single read of available bytes | Java API | No; returns actual bytes read, which may be smaller than the buffer |
| **TCP segment** — segmentation unit when TCP transmits | Transport/network | Does not preserve write/message boundaries for the application |

**RFC 9293 Section 3.7** describes TCP segmentation and explicitly states that there is no guaranteed correlation between **TCP segment boundaries** and **application read/write buffer boundaries**. A single large `write` may produce multiple segments; multiple small `write` calls may be processed/coalesced by the network stack into different segments. Meanwhile, the receiver calls `read` with its own buffer size, scheduling, and socket state.

### Comparison with UDP

With `DatagramSocket`/UDP, the unit of sending and receiving is a **datagram**, which has its own boundaries; an oversized datagram may be truncated according to the API buffer, and the network can drop or reorder datagrams. With a **TCP `Socket`**, the receiver only sees a stream; to have message units, the application must frame them itself or use a library protocol that handles framing.

**This does not mean TCP "can drop bytes between two messages" during normal operation**: TCP guarantees ordering and reliable delivery, or reports a transport failure. The problem addressed in this lab is **not knowing message boundaries** from read calls, not TCP arbitrarily scrambling bytes.

## 2. One Message Can Be Sent Using Three `write` Calls

Let us define a message `ALPHA` with a 5-byte UTF-8 payload. We choose the protocol:

```text
[4 bytes signed int length, big-endian][UTF-8 payload]
```

Thus the frame corresponding to `ALPHA` is **9 bytes** long:

```text
Offset: 00 01 02 03 | 04 05 06 07 08
Hex:    00 00 00 05 | 41 4C 50 48 41
        └── length 5 ┘   └── "ALPHA" ─┘
```

The sender **intentionally** splits the same frame across three API calls:

```java
// Illustrative excerpt; "out" is the OutputStream of a connected socket.
byte[] firstFrame = frame("ALPHA"); // Application-defined frame helper.
out.write(firstFrame, 0, 2);                       // 00 00
out.write(firstFrame, 2, 3);                       // 00 05 41
out.write(firstFrame, 5, firstFrame.length - 5);   // 4C 50 48 41
```

Three `write` calls do **not** create three logical messages. It is still **one frame** with a length header of 5 and payload `ALPHA`. The receiver might read:

```text
Read #1: 00 00
Read #2: 00 05 41
Read #3: 4C 50 48 41
```

but it could also read:

```text
Read #1: 00 00 00 05 41 4C 50 48 41
```

or any other partitioning into contiguous slices. **Both of the read examples above are merely possible reception patterns**; you must never assume a machine will always execute with that exact number of reads or fragments.

### The Problem with Treating One `read` as One Message

Broken code typically looks like this:

```java
// ANTI-PATTERN: not standalone runnable; falsely assumes boundaries.
byte[] buf = new byte[1024];
int n = socket.getInputStream().read(buf);
String message = new String(buf, 0, n, StandardCharsets.UTF_8);
handle(message); // Wrong if only part of a frame or multiple frames arrived.
```

Here `handle` and `socket` are illustrative variables/methods without standalone declarations. If `n=2`, the code will treat the two length-header bytes as text content; if `n=15`, it may contain more than one frame. Increasing the buffer to 65,536 bytes **does not solve this**: a single `read` is still allowed to return fewer bytes than requested or contain more messages than expected.

## 3. Two Messages Coalesced Into **One** `write` Call

Under the same length-prefix contract:

```text
Frame "RED":
  00 00 00 03 52 45 44           (4 + 3 = 7 bytes)

Frame "BLUE":
  00 00 00 04 42 4C 55 45        (4 + 4 = 8 bytes)

Combined into a single 15-byte byte[]:
  00 00 00 03 52 45 44 00 00 00 04 42 4C 55 45
      frame #2                   frame #3
```

One send call:

```java
// Illustrative excerpt, not standalone; out and frame(...) are provided by the app.
ByteArrayOutputStream joined = new ByteArrayOutputStream();
joined.write(frame("RED"));
joined.write(frame("BLUE"));
out.write(joined.toByteArray()); // One write call containing TWO frames.
```

**One `write` does not mean one message**. If the server parses only one frame and discards the remaining bytes in the buffer, it will lose `BLUE`. A correct decoder must **loop until no complete frame remains** in the buffered data, and preserve any incomplete fragment for the next `read`.

### No Need to Synchronize Timing Between Both Ends

If the server calls `read` with an 8-byte buffer, it may read the start of the `RED` frame, or all of `RED` plus one byte of `BLUE`'s header, or other slices. The sender has no authority to dictate how the receiving JVM invokes `read` in response. **Message boundaries come from protocol framing, not from scheduling.**

## 4. Length-Prefix Framing Rules

A minimal contract, sufficient for this lab:

1. Each frame starts with **4 bytes** representing the **UTF-8 payload byte count**, in **big-endian** order.
2. Immediately following are exact `length` payload bytes.
3. Valid length values are `0..1024` in the demo programs; production systems choose an appropriate limit based on domain requirements.
4. After decoding the first frame, resume at the **byte immediately following the payload** for the second frame, regardless of previous `read` counts.
5. If EOF occurs **while waiting for a new frame**, the stream may terminate cleanly; if EOF occurs **mid-header or mid-body**, it must be treated as a truncated frame.
6. Negative, oversized, or overflowing lengths must be rejected **before allocating any array**.
7. Use `UTF-8` to **encode bytes first**, then take the byte length; do not use `String.length()` (UTF-16 units) as the byte length.

### Why Choose 4 Bytes Big-Endian?

`java.nio.ByteBuffer` defaults to **big-endian**, and `DataInputStream.readInt()` reads four bytes high-byte first, making them compatible in these examples. This is a **custom protocol convention**, not a TCP requirement that every application use a 4-byte header or big-endian. Both sides must **agree on the contract**; if the client sends little-endian while the server reads big-endian, the length will be misinterpreted.

### A Max Frame Limit Is Essential

An untrusted client can send a header like:

```text
7F FF FF FF → length = 2,147,483,647 bytes
```

If the server blindly executes `new byte[length]` from network input, it can run out of RAM. Validate `0 <= length <= MAX_FRAME_BYTES` before allocating. Real-world systems must also limit **concurrent connections**, header/body read timeouts, buffered bytes, decode CPU, messages/second, and authentication.

### Is a Zero-Length Frame Valid?

In this lab's contract, length 0 is a valid empty frame, **distinct from EOF**. If an application wants to forbid empty messages, it must state so explicitly in the contract. Do not use `length == 0` as a "connection closed" signal when the protocol still uses empty payloads as data.

## 5. Java 17+: Real TCP Program — 3 Writes for 1 Frame, 1 Write for 2 Frames

The server opens a `ServerSocket` on `127.0.0.1`, accepts **one** connection, and reads **three** length-prefixed frames via `DataInputStream.readInt()` and `readFully(...)`. The client builds `frame("ALPHA")` and splits it across three `write` calls; it then joins `frame("RED")` and `frame("BLUE")` into one `byte[]` and sends it in a single `write` call.

The program explicitly calls `Socket.shutdownOutput()` after sending so the server can observe EOF **after** decoding the three frames; that is a sender-side half-close, **not the only way to delimit frames**. The server reads all three frames via **length-prefixing**, not via EOF.

**File `TcpWriteShapeLab.java`:**

```java
import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class TcpWriteShapeLab {
    record Result(List<String> messages, boolean sawCleanEof) {}

    static byte[] frame(String message) {
        byte[] payload = message.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + payload.length)
                .putInt(payload.length).put(payload).array();
    }

    static String readFrame(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 0 || length > 1024) throw new IOException("Invalid length");
        byte[] payload = new byte[length];
        input.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<Result> server = pool.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(4000);
                    DataInputStream input = new DataInputStream(peer.getInputStream());
                    List<String> messages = new ArrayList<>();
                    for (int i = 0; i < 3; i++) messages.add(readFrame(input));
                    boolean cleanEof = input.read() == -1;
                    return new Result(messages, cleanEof);
                }
            });
            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress("127.0.0.1",
                        listener.getLocalPort()), 2000);
                OutputStream output = client.getOutputStream();

                byte[] first = frame("ALPHA");
                output.write(first, 0, 2);
                output.write(first, 2, 3);
                output.write(first, 5, first.length - 5);

                byte[] second = frame("RED");
                byte[] third = frame("BLUE");
                ByteArrayOutputStream joined = new ByteArrayOutputStream();
                joined.write(second);
                joined.write(third);
                output.write(joined.toByteArray());
                output.flush();
                client.shutdownOutput();

                Result result = server.get(3, TimeUnit.SECONDS);
                System.out.println("First frame write calls: 3");
                System.out.println("Other two frames write calls: 1");
                System.out.println("Server decoded: " + result.messages());
                System.out.println("Clean EOF after frames: " + result.sawCleanEof());
            }
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Run from the directory containing the file with JDK 17+:

```bash
javac --release 17 -encoding UTF-8 TcpWriteShapeLab.java
java TcpWriteShapeLab
```

**Verified stdout on loopback:**

```text
First frame write calls: 3
Other two frames write calls: 1
Server decoded: [ALPHA, RED, BLUE]
Clean EOF after frames: true
```

### What Does This Prove — and What Does It Not Prove?

**Directly evidenced:**

- The client **made three `write` calls** for bytes belonging to the single `ALPHA` frame, and **one `write` call** for the two consecutive `RED`/`BLUE` frames.
- The server decoded **three logical messages**, in the exact order, regardless of how many underlying reads the receiver performed.
- `DataInputStream.readInt()` retrieves the 4-byte header; `readFully(payload)` does not stop just because an underlying raw read returns partial data. This is why this API fits a **known, valid length**.
- `shutdownOutput()` causes the peer to see EOF once no more bytes are in flight, so `input.read()` after the three frames returns `-1` on the normal test path.

**Does not prove:**

- "One `write` is one TCP packet." The program **does not count packets**.
- "Three `write` calls definitely produce three `read` calls." The program makes no such assumption, and the server remains correct even if the number of raw reads differs.
- "Every client automatically receives three messages when using TCP." This only holds because both sides agreed on the **framing contract**.
- "TCP guarantees the remote application succeeded in business processing." This is decoding evidence; if business-level ACKs are needed, they must be defined separately.
- "A production server is allowed to read indefinitely and accept any length." The code has a max of 1024 and timeouts, yet only handles one connection for educational purposes.

### Details on `DataInputStream.readFully`

`readFully(byte[])` attempts to read the **exact requested number of bytes** from the stream (possibly using multiple underlying reads). If EOF arrives before enough bytes are read, it throws `EOFException`. `readInt()` likewise requires 4 bytes and throws EOF if short. This solves **partial reads for a valid frame** once the length is known, but does not replace server-side resource limits or protocol versioning.

On a long-lived connection, after three frames the server **does not need to wait for EOF to know the third frame is complete**: the length-prefix already tells it. EOF is only used to end the session in this test program.

## 6. Why Is a Stateful Decoder Needed When Using `SocketChannel` or `read(buffer)`?

`DataInputStream` is convenient in **blocking I/O** where you can block waiting for 4 header bytes and the full payload. However, with:

- `SocketChannel` in nonblocking mode,
- a Selector event loop,
- asynchronous I/O,
- byte buffers delivered via framework callbacks,
- or data from a parser/transport layer split into arbitrary chunks,

you typically only receive **a slice of newly arrived bytes**. You must not call `ByteBuffer.getInt()` when only 2 header bytes have arrived; nor may you discard leftover buffer bytes after a complete frame.

A correct decoder must maintain state across multiple `feed(chunk)` calls:

```text
[WAIT FOR 4-BYTE HEADER]
    │ incomplete → retain, wait for next chunk
    │ complete → read length, validate 0..MAX
    ▼
[WAIT FOR length-BYTE PAYLOAD]
    │ incomplete → retain, wait for next chunk
    │ complete → decode 1 message, consume frame
    ▼
[ADVANCE TO NEXT FRAME]
    ├─ buffer still has a full frame → decode next in same feed
    ├─ buffer has a fragment → retain
    └─ buffer empty → wait for next feed
```

**Both conditions are mandatory**: (a) preserve incomplete fragments; (b) parse **multiple frames** if a single chunk contains more than one.

### Avoiding the "Each `onRead` Is One Message" Trap

A Selector reports **readiness**, not "a complete message is available." An `onRead` callback can receive very few or very many bytes. The parser must accumulate according to framing. `OP_READ` readiness does not imply a length-prefix header or body is complete.

## 7. Java 17+: Decoder Receiving Arbitrary Chunks — Deterministic Experiment

The second program does not use sockets. It is a **byte-stream parser-layer test** with **explicitly controlled** chunk sizes, ensuring the verification does not depend on live TCP scheduling.

It feeds frame `ONE` into the decoder in three pieces: the first 2 header bytes, the next 2 header bytes plus 2 payload bytes, and finally the last 1 payload byte. The decoder emits **no** message for the first two pieces because the frame is incomplete. Then it feeds **two frames `TWO` and `THREE` in a single chunk**, and the decoder must emit **two messages** without dropping the remainder.

The decoder uses a fixed 4096-byte pending buffer and rejects lengths over 1024. This remains a demo, not a production parser for arbitrary loads/frame counts; production code needs to handle larger chunks or bounded queues without losing bytes.

**File `IncrementalFrameDecoderDemo.java`:**

```java
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.*;
import java.util.*;

public class IncrementalFrameDecoderDemo {
    static final class Decoder {
        private final byte[] pending = new byte[4096];
        private int count;

        List<String> feed(byte[] part) throws IOException {
            if (part.length > pending.length - count)
                throw new IOException("Pending buffer full");
            System.arraycopy(part, 0, pending, count, part.length);
            count += part.length;
            List<String> decoded = new ArrayList<>();
            while (count >= 4) {
                int size = ByteBuffer.wrap(pending, 0, 4).getInt();
                if (size < 0 || size > 1024)
                    throw new IOException("Frame length rejected: " + size);
                if (count < size + 4) break;
                try {
                    String text = StandardCharsets.UTF_8.newDecoder()
                            .onMalformedInput(CodingErrorAction.REPORT)
                            .onUnmappableCharacter(CodingErrorAction.REPORT)
                            .decode(ByteBuffer.wrap(pending, 4, size)).toString();
                    decoded.add(text);
                } catch (CharacterCodingException badUtf8) {
                    throw new IOException("Invalid UTF-8", badUtf8);
                }
                int remaining = count - size - 4;
                System.arraycopy(pending, 4 + size, pending, 0, remaining);
                count = remaining;
            }
            return decoded;
        }

        int pendingBytes() { return count; }

        void finish() throws IOException {
            if (count != 0) throw new IOException("Incomplete final frame");
        }
    }

    static byte[] frame(String message) {
        byte[] data = message.getBytes(StandardCharsets.UTF_8);
        return ByteBuffer.allocate(4 + data.length)
                .putInt(data.length).put(data).array();
    }

    static byte[] concat(byte[] a, byte[] b) {
        byte[] combined = Arrays.copyOf(a, a.length + b.length);
        System.arraycopy(b, 0, combined, a.length, b.length);
        return combined;
    }

    public static void main(String[] args) throws Exception {
        Decoder decoder = new Decoder();
        byte[] one = frame("ONE");
        System.out.println("Partial header: "
                + decoder.feed(Arrays.copyOfRange(one, 0, 2)));
        System.out.println("Header plus partial payload: "
                + decoder.feed(Arrays.copyOfRange(one, 2, 6)));
        System.out.println("Remaining payload: "
                + decoder.feed(Arrays.copyOfRange(one, 6, one.length)));
        System.out.println("Two frames in one chunk: "
                + decoder.feed(concat(frame("TWO"), frame("THREE"))));
        decoder.finish();
        System.out.println("Pending after decode: " + decoder.pendingBytes());
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 IncrementalFrameDecoderDemo.java
java IncrementalFrameDecoderDemo
```

**Verified stdout:**

```text
Partial header: []
Header plus partial payload: []
Remaining payload: [ONE]
Two frames in one chunk: [TWO, THREE]
Pending after decode: 0
```

### Byte-Level Analysis

`frame("ONE")` is 7 bytes long:

```text
00 00 00 03 4F 4E 45
└ length 3 ┘ └ ONE ┘
```

The `feed` calls:

| Feed | New bytes | Pending before decode | Complete messages | Remaining pending |
|---|---|---:|---|---:|
| `one[0:2]` | `00 00` | 2 | None | 2 |
| `one[2:6]` | `00 03 4F 4E` | 6 | None (needs 1 more payload byte) | 6 |
| `one[6:7]` | `45` | 7 | ONE | 0 |
| `frame("TWO")+frame("THREE")` | 7+9 = 16 bytes | 16 | TWO, THREE | 0 |

**No TCP events were involved in constructing this table**: the segmentation was deliberately chosen at the test layer. This matters because parser tests must be **deterministic**, whereas whether a `Socket.read` receives 2 or 9 bytes depends on timing, OS buffers, and the network stack.

### Why `while (count >= 4)` Instead of `if`?

Because **a single chunk can contain multiple frames**. Once `TWO` is decoded, the entire `THREE` frame remains in `pending`; the `while` loop continues processing it. If you only used a single `if` and dropped the rest of the buffer, `THREE` would be lost or stuck until more data arrived.

### Why Must a Partial Header Be Buffered?

If you receive only 2 bytes `00 00` and try to call `ByteBuffer.getInt`, the decoder will suffer an underflow or read invalid bytes. The rule must be: **wait for all 4 bytes before reading length**. Similarly, if the header is complete but the payload is not, keep it buffered.

### Why Strict UTF-8 Decoding Only After All Bytes Arrive?

A Unicode character can span multiple UTF-8 bytes, and a chunk can split right in the middle of a character's byte sequence. Calling `new String(part, UTF_8)` on **each chunk** can produce replacement characters due to incomplete byte fragments. The decoder should decode text **only after assembling a full frame**, or use a stateful `CharsetDecoder` per the streaming contract.

In this example, `CharsetDecoder.onMalformedInput(REPORT)`/`onUnmappableCharacter(REPORT)` ensures **invalid UTF-8 is rejected** instead of silently replaced with an unrecognizable `` character. For binary protocols, do not decode UTF-8 at all—pass raw bytes up to the business layer.

### Limitations of the Demo Decoder

`Decoder.feed` caps **an input chunk plus pending bytes at <= 4096 bytes**. If a caller passes a very large chunk, it rejects rather than splitting it internally. This is an intentional safety choice for the demo, **not a full-featured parser**. A production decoder can use a bounded growable buffer, ring buffer, offset-based chunk processing, pooling, and backpressure to avoid unbounded allocations.

## 8. EOF Is Not the Same as "One Message Received"

Do not confuse:

- `InputStream.read() == -1`: **EOF**, the peer closed its sending side or the stream ended.
- `length-prefix payload complete`: **message complete**, regardless of whether the connection remains open.
- `BufferedReader.readLine()` sees a newline: a **line-delimited message is complete** per the protocol definition.
- `ByteBuffer.remaining() == 0` after a `read`: no more bytes in the current buffer; does **not** mean end of frame, message, or connection.
- `Socket.isConnected()==true`: has been connected at some point; does **not** mean the socket is still online or the peer is still sending data.

In a protocol with **multiple messages over a long-lived connection**, if the server calls `input.readAllBytes()` on the raw `Socket.getInputStream()`, it may **block forever** because the TCP peer does not close the stream after each message. This is a common pitfall when learning Java Networking.

### EOF at Three Different Points

```text
A. [complete frame][EOF]
   → Valid connection termination if the protocol allows closing at a boundary.

B. [1..3 header bytes][EOF]
   → Header has fewer than 4 bytes; must report truncated header.

C. [4 bytes length = 5][2 payload bytes][EOF]
   → Payload is missing 3 bytes; must report truncated frame.
```

If a program simply reads until EOF and treats whatever bytes arrived as "success," cases B and C will be mistaken for valid data. For RPC or financial protocols, that can be a critical bug: the parser accepts a truncated message and triggers side effects.

### Why `DataInputStream.readFully` Is Useful

It waits for `N` bytes or throws `EOFException` (and possibly `IOException` on network errors). However, you must **know a valid `N` beforehand**, read `N` accurately via a framing contract, and configure socket timeouts/cancellation policies to avoid waiting forever if the peer stops sending. `readFully` does not perform validation or enforce timeouts on its own.

## 9. Java 17+: Rejecting Truncated Headers, Truncated Bodies, and Oversized Lengths

The third example uses `ByteArrayInputStream` to test the parser **without network timing**. It reads the first byte of the header to distinguish **clean EOF before a frame** from **EOF mid-header**, then uses `DataInputStream.readFully` to read the remaining three header bytes and the payload.

Test cases:

1. Empty stream when waiting for a new frame → returns `null` as the clean boundary EOF signal of the **demo protocol**.
2. Only 2 header bytes → throws `EOFException`.
3. Header length 5 with only 2 payload bytes → throws `EOFException`.
4. Length 999999 > MAX 1024 → throws `IOException` before allocating payload.
5. Length 0 → returns empty string `""` as a **valid frame**.

**File `TruncatedFrameDefenseDemo.java`:**

```java
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

public class TruncatedFrameDefenseDemo {
    static String readFrame(DataInputStream input) throws IOException {
        int first = input.read();
        if (first == -1) return null;
        byte[] header = new byte[4];
        header[0] = (byte) first;
        input.readFully(header, 1, 3);
        int length = ByteBuffer.wrap(header).getInt();
        if (length < 0 || length > 1024)
            throw new IOException("Rejected length: " + length);
        byte[] payload = new byte[length];
        input.readFully(payload);
        return new String(payload, StandardCharsets.UTF_8);
    }

    static String outcome(byte[] bytes) {
        try {
            readFrame(new DataInputStream(new ByteArrayInputStream(bytes)));
            return "ACCEPTED";
        } catch (EOFException incomplete) {
            return "EOFException";
        } catch (IOException invalid) {
            return "IOException";
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println("Clean boundary EOF: "
                + (readFrame(new DataInputStream(
                    new ByteArrayInputStream(new byte[0]))) == null));
        System.out.println("Partial header: "
                + outcome(new byte[] {0, 0}));
        System.out.println("Truncated payload: "
                + outcome(new byte[] {0, 0, 0, 5, 'A', 'B'}));
        System.out.println("Oversized length: "
                + outcome(ByteBuffer.allocate(4).putInt(999999).array()));
        System.out.println("Valid zero-length frame: "
                + ("".equals(readFrame(new DataInputStream(
                    new ByteArrayInputStream(new byte[] {0, 0, 0, 0}))))));
    }
}
```

Run:

```bash
javac --release 17 -encoding UTF-8 TruncatedFrameDefenseDemo.java
java TruncatedFrameDefenseDemo
```

**Verified stdout:**

```text
Clean boundary EOF: true
Partial header: EOFException
Truncated payload: EOFException
Oversized length: IOException
Valid zero-length frame: true
```

### Accurate Error Classification

- **Clean boundary EOF** has no 4-byte header partially read, so it signals end of stream **per the demo contract**. A production protocol might also require a close reason, sequence number, or expected message count before accepting EOF.
- **Partial header**: detected that the first byte arrived, but 3 header bytes are missing. `EOFException` is appropriate rather than silently discarding leftover bytes.
- **Truncated payload**: a valid header declares 5 bytes, but the stream provides only 2. Returning `"AB"` as a successful message would be wrong.
- **Oversized length**: validation runs **before allocation**, thwarting attempts to use the header to exhaust RAM. The runtime is never forced to allocate 999,999 bytes.
- **Zero-length frame**: valid per the contract. Not confused with clean EOF because the `00 00 00 00` header is present in full.

**One area to extend for production:** returning `null` on clean EOF can collide if the message type allows `null`. Use `Optional<Message>` or a result enum/record to distinguish states. The demo uses `String` for clarity, with the contract explicitly documented.

## 10. Another Framing Approach: `\n` Delimiter and `BufferedReader.readLine`

Not every protocol needs a length-prefix. A **one-message-per-line** protocol can use a consistent delimiter such as LF `\n`. When the receiver uses `BufferedReader.readLine()`, it **accumulates until a line terminator or EOF** per the API contract, regardless of how many `write` calls the sender split the bytes across.

Example stream:

```text
"FIRST\nSECOND\nTHIRD\n"
```

The client might send:

```text
write #1: "FI"
write #2: "RST\n"
write #3: "SECOND\nTHIRD\n"
```

The server calls `readLine` three times and receives `FIRST`, `SECOND`, `THIRD`. Here the `\n` delimiter is the **application-protocol message boundary**, not TCP generating boundaries itself.

### Pros and Cons

| Criterion | Newline delimiter | Length-prefix |
|---|---|---|
| Easy to inspect with telnet/netcat/logs? | Yes, for UTF-8 text and LF | Harder to read visually due to binary header |
| Supports newlines inside payload? | Requires escaping/encoding or forbidding | Yes, newlines are ordinary payload bytes |
| Supports arbitrary binary data? | Requires escaping/Base64 | Can preserve raw bytes directly |
| Frame size known in advance? | No, only known upon hitting LF | Yes, once header is read |
| Size limiting | Must count bytes/chars until delimiter | Check length before allocating, still bounded |
| EOF mid-line | `readLine` may return the last line **without LF** | Truncated header/body is detected explicitly |
| Unicode/UTF-8 | Reader must decode properly across byte chunks | Decode payload after full frame arrives |
| Streaming parser | `BufferedReader.readLine`/scanner usable | Custom state machine/`readFully` |

**Important note:** According to the Java API, `BufferedReader.readLine()` accepts LF, CR, or CRLF, and if EOF arrives after characters with no terminator, it still returns that **final line**. If a protocol **requires every message to end with LF**, using `readLine` alone **does not prove** the last line had a terminator. A strict parser must preserve/check the terminator, enforce a line length limit, and treat EOF without LF as an incomplete message if the contract requires it.

## 11. Java 17+: Sending One Line in Two Writes, Two Lines in One Write

The server's `BufferedReader` reads until EOF, collecting lines. The client sends `FIRST` split in two, then coalesces `SECOND` and `THIRD`. The program **does not assume one `readLine` corresponds to one `write`**; it relies on the **delimiter**.

**File `LineFramingLab.java`:**

```java
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;

public class LineFramingLab {
    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<List<String>> decoded = workers.submit(() -> {
                try (Socket peer = listener.accept();
                     BufferedReader in = new BufferedReader(new InputStreamReader(
                             peer.getInputStream(), StandardCharsets.UTF_8))) {
                    peer.setSoTimeout(4000);
                    List<String> lines = new ArrayList<>();
                    String line;
                    while ((line = in.readLine()) != null) {
                        lines.add(line);
                        if (lines.size() > 3)
                            throw new IOException("Unexpected extra message");
                    }
                    return lines;
                }
            });

            try (Socket client = new Socket()) {
                client.connect(new InetSocketAddress("127.0.0.1",
                        listener.getLocalPort()), 2000);
                OutputStream out = client.getOutputStream();
                byte[] first = "FIRST\n".getBytes(StandardCharsets.UTF_8);
                out.write(first, 0, 2);
                out.write(first, 2, first.length - 2);
                out.write("SECOND\nTHIRD\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                client.shutdownOutput();

                System.out.println("First line write calls: 2");
                System.out.println("Next two lines write calls: 1");
                System.out.println("Server readLine messages: "
                        + decoded.get(3, TimeUnit.SECONDS));
            }
        } finally {
            workers.shutdownNow();
        }
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 LineFramingLab.java
java LineFramingLab
```

**Verified stdout:**

```text
First line write calls: 2
Next two lines write calls: 1
Server readLine messages: [FIRST, SECOND, THIRD]
```

### Why Does This Example Succeed?

- `FIRST\n` is **one message** per the delimiter contract even though it was sent in **two write calls**.
- `SECOND\nTHIRD\n` is **two messages** even though it was sent in **one write call**.
- `BufferedReader` handles charset decoding across the stream, and `readLine` looks for **line terminators**, not TCP segment or read counts.
- The server relies on `shutdownOutput()` on the client so `readLine` can return `null` after three lines. The delimiter still determines message boundaries before EOF.
- The program does not handle escaped newlines, maliciously long lines, or message IDs; when building a production protocol, you must add line length limits, escaping, and validation.

### When Not to Use a Delimiter?

Not suitable if the payload is arbitrary binary data that may contain `\n`, if you need to receive very large unescaped binary frames, or if the protocol does not guarantee a line terminator. You can use JSON Lines when each JSON document is strictly **one line** and newlines inside strings are encoded as `\\n` in the JSON representation. You cannot send multi-line "pretty JSON" using a simple LF delimiter and expect one JSON object to be treated as one message.

## 12. UTF-8: Character Length Is Not Byte Length

A Java `String` uses a UTF-16 representation, so `String.length()` is not the number of UTF-8 bytes that will be sent over TCP. For example:

```text
Text: "é"
Java String.length(): 1 UTF-16 code unit
UTF-8 payload bytes: C3 A9 (2 bytes)

Text: "🌍"
Java String.length(): 2 UTF-16 code units (surrogate pair)
UTF-8 payload bytes: F0 9F 8C 8D (4 bytes)
```

If the header writes `payload.length()` while the sender actually writes `payload.getBytes(UTF_8)`, the server will read **too few bytes** for the first frame and interpret the remaining bytes as the header of the next frame. This is a framing bug that often only surfaces with Unicode.

**Always compute:**

```java
// Illustrative snippet; DataOutputStream and message are defined by the application.
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);
out.writeInt(bytes.length); // BYTE count, not String.length().
out.write(bytes);
```

This is a non-standalone snippet; `out` is a `DataOutputStream`, and the server must call `readInt`/`readFully` under the same contract.

### Is Splitting Right in the Middle of a UTF-8 Code Point Safe?

TCP may deliver byte chunks split between `C3` and `A9`. **This is completely valid for a byte stream**. If the parser accumulates bytes and decodes only after a complete frame arrives, `é` is recovered normally. If the parser calls `new String(chunk, UTF8)` on each chunk independently, it can produce replacement characters. Use a stateful `CharsetDecoder` or decode **after the frame is complete**.

In `IncrementalFrameDecoderDemo`, the payload is decoded after enough bytes have arrived; therefore splitting the header or body across multiple `feed` calls does not alter the message.

## 13. `flush()`, `TCP_NODELAY`, Nagle, and PSH Do Not Create Message Boundaries

Four commonly misused concepts:

### `OutputStream.flush()`

`flush()` is an operation per the `OutputStream`/`BufferedOutputStream` contract to push data **currently buffered in the Java stream layer** down to the underlying layer. When writing through `BufferedOutputStream`, you must flush so data does not sit indefinitely in the Java buffer. However, **flush does not create a frame delimiter** for the peer; the receiver may still read a partial frame or multiple frames in a single `read`.

If using a raw `Socket.getOutputStream()` with no extra Java buffering layer, `flush()` may do nothing significant; do not treat it as "send packet now" or "receiver reads exactly one message."

### `Socket.setTcpNoDelay(true)`

This option controls `TCP_NODELAY`, commonly explained as disabling Nagle's algorithm to reduce one kind of delay for small writes. **It does not turn TCP into a message transport**. Whether Nagle is enabled or disabled, TCP remains a stream and read boundaries are never guaranteed.

### Nagle, Delayed ACK, and the Scheduler

Small writes can be coalesced or delayed by the TCP stack depending on network conditions, Nagle, congestion window, delayed ACK, MSS/MTU, and scheduling. Toggling `TCP_NODELAY` can change latency or packet patterns, but **does not change the parser's job**.

### The PSH Flag Is Not End-of-Message

PSH in TCP is not a mechanism guaranteeing that "all data up to PSH belongs to one application message." Do not use PSH or TCP segment boundaries as end-of-message markers. You need application-layer protocol framing.

**Rule of thumb:** if toggling `TCP_NODELAY` makes a bug "disappear," the parser is usually still broken; the bug is merely being masked by timing. Good tests actively vary chunk sizes while verifying the parser **still produces the exact same output**.

## 14. Nonblocking `SocketChannel`: Partial Reads/Writes and `ByteBuffer`

With Java NIO `SocketChannel` in nonblocking mode, a single `read(ByteBuffer)` call can return a small positive byte count, **0** if no data is currently ready, or **-1** when the stream ends. Do not conflate "read 0" with EOF; nor should you try to parse a 4-byte header when only 2 bytes are in the buffer.

A single nonblocking `write(ByteBuffer)` can write **fewer bytes than `remaining()`** (including 0) due to send buffers or flow control. To send a frame, you must **retain the remaining `ByteBuffer`** and continue writing when the channel is writable. Never drop unsent payload bytes.

```java
// Illustrative snippet, not a standalone program.
ByteBuffer outbound = ByteBuffer.wrap(frameBytes);
while (outbound.hasRemaining()) {
    int n = channel.write(outbound);
    if (n == 0) {
        // Do not busy-spin in nonblocking I/O:
        // register OP_WRITE and resume when the Selector signals writable.
        break;
    }
}
// Keep outbound with its current position to resume writing in the event loop.
// Only consider frame bytes fully flushed from the buffer when !hasRemaining().
```

Here `channel` is a connected `SocketChannel`, and `frameBytes` holds a frame per the contract. A production event loop must maintain a bounded send queue and manage `OP_WRITE` on demand, avoiding leaving `OP_WRITE` permanently enabled and causing a busy spin.

### `ByteBuffer.flip()` and `compact()`

A receive buffer in NIO typically follows this pattern:

```java
// Illustrative snippet: inputBuffer and channel are owned by the app.
int count = channel.read(inputBuffer); // Buffer is in write mode.
if (count > 0) {
    inputBuffer.flip();                // Read newly arrived bytes in buffer.
    decodeCompleteFrames(inputBuffer); // Do not read past limit.
    inputBuffer.compact();             // Retain leftover bytes, switch to write mode.
}
```

This is a non-standalone snippet: `decodeCompleteFrames` must maintain proper state and handle incomplete headers/payloads. `compact()` preserves unconsumed bytes; it does not parse the protocol for you. If a single read yields two frames, the decoder must process **both** in a loop before compacting.

### Never Interleave Bytes of Two Frames from Multiple Threads

TCP preserves the order of bytes accepted into the stream, but **does not automatically make "a frame sent via multiple `write` calls" atomic** if multiple threads share an `OutputStream` and write concurrently.

```text
Thread A: header A
Thread B: header B + payload B
Thread A: payload A

Wire stream can become:
  [header A][header B][payload B][payload A]
```

The decoder sees header A and interprets header B as **payload A**, corrupting the entire framing. Serialize **the entire frame** through a single writer thread/queue or hold a lock around **the whole frame send**, not just individual `write` calls. Even if a frame is usually sent with one `write`, that alone does not solve NIO backpressure or partial writes.

## 15. Defending the Decoder Against Malformed Data and Attacks

Framing is a **necessary** condition to reconstruct messages, but **not sufficient** to protect a production server.

| Risk | Example | Mitigation |
|---|---|---|
| Negative or huge length | Header `FF FF FF FF` = -1 or huge `7F FF FF FF` | Validate length range before allocating |
| Sending only 1–3 header bytes then stalling | Custom-protocol Slowloris | Timeouts, per-connection quotas, connection limits |
| Truncated payload | Header declares 500, peer sends 10 then EOF | Report truncated frame, clean up; do not process partial |
| Malformed Unicode | Bytes are not valid UTF-8 | `CharsetDecoder` `REPORT` if protocol requires strict UTF-8 |
| One chunk with thousands of tiny frames | Message flood | Limit frames per tick, CPU budget, queues, and rate limits |
| Fragmentation growing buffers | Long-lived partial frames | Max pending bytes, max frame bytes, deadlines |
| Client not reading responses | Send queue grows unbounded | Bounded queue, backpressure, timeout/close policy |
| Reader blocked forever while peer stays alive | Peer keeps TCP open without sending enough | `setSoTimeout`, application deadline, or async timeout |
| Two threads interleaving frame bytes | Corrupted header/payload | Single writer / serialized send queue / frame-level lock |
| Empty frame confused with EOF | Header length 0 | Distinguish clean EOF from zero-byte payload |
| Receiver duplicates work on retry | Timeout after server already processed | Application message IDs, idempotency, ACK protocol |

**Do not use `InputStream.available()` to decide if a message is complete.** It only estimates bytes currently readable without blocking, and knows nothing about application frame lengths. `available()==0` does not mean the peer finished sending the message; `available()>0` does not guarantee a full header/body is present.

### Bound Total RAM, Not Just Max Frame Size

If each connection is allowed up to 1 MiB of buffer, then 10,000 connections can consume roughly 10 GiB **just for pending buffers**. You need concurrency limits, pooled buffers/quotas, slow-client policies, and connection lifetimes. If the API supports compressed frames, you must bound the decompressed size; the length-prefix of compressed bytes does not limit memory after decompression.

### Do Not Decode Before Framing Is Complete

If the message is JSON, pass **only the exact payload bytes of one frame** to the JSON parser once complete; if the receiver parses while bytes are missing, the parser will throw spurious errors or hold half-parsed state. A streaming JSON parser can process incrementally, yet still requires a clear contract for message boundaries when multiple documents share one connection.

## 16. Debugging with Packet Capture: What to Measure and What Not to Guess

In a real experiment, you can enable packet capture on the **loopback interface** with appropriate privileges and use Wireshark/tcpdump or the OS equivalent. However:

- **TCP segment count** does not equal `write` call count; OS/NIC offloading, coalescing, and the capture layer can alter packet shapes.
- One TCP segment can carry **multiple application frames**; one application frame can also span multiple TCP segments.
- **Receive `read(buffer)` count** is the number of API calls made by the application, depending on buffer size and scheduling, not packet count.
- `tcpdump` may show retransmissions, duplicate ACKs, and congestion; these do not turn the same bytes into new logical messages at the Java layer when TCP delivers a normal stream.
- With TLS, packet capture cannot read plaintext payloads without valid decryption keys; learners can still verify application-layer framing via structured logs and byte arrays without exposing secrets.

### Proper Logging for Comparison

```text
txLogicalMessageId    = 123
txPayloadUtf8Bytes    = 5
txFrameBytes          = 9
txWriteCalls          = 3
rxSocketReadCalls     = (measurement only, may vary)
rxFramesDecoded       = 1
rxMessage             = "ALPHA"
rxBytesBuffered       = ...
rxIncompleteFrame     = false
```

Never write an assertion like `rxSocketReadCalls == 3`; it may pass once and fail the next time with **no bug present**. The right assertion is **rx decoded message count/order/payload == expected**, plus final parser state and error behavior.

### Why Don't the Examples Use `Thread.sleep(...)` to Force Read Boundaries?

Adding `Thread.sleep(50)` between writes **does not guarantee** the kernel/receiver will read in three chunks. Scheduler timing, Nagle, TCP buffers, and CPU load vary and make tests flaky. Therefore, this lab uses two complementary test styles with distinct goals: real sockets to **measure decode results**, and parser unit tests that **feed bytes in fixed chunks** to verify partial/coalesced inputs deterministically.

## 17. Mandatory Test Matrix for a Custom TCP Protocol

Any length-prefixed parser should pass at least:

| Case | Input fed to decoder | Expected outcome |
|---|---|---|
| Exact frame | `[header][payload]` | Exactly one message |
| Header split 1+3 | `[1 byte]` then `[3 header bytes+body]` | No premature decode; eventually one message |
| Header split 2+2 | `[2 bytes]` then `[2 bytes+body]` | No underflow |
| Payload split across pieces | `[header+1 byte]` then remainder | Waits until complete before decoding |
| One chunk with two frames | `[f1][f2]` | Returns both `f1` and `f2` |
| Chunk with `f1` and partial `f2` | `[f1][incomplete f2 header]` | Returns `f1`, retains partial `f2` |
| Multiple frames split arbitrarily | N random chunks preserving byte order | Message sequence matches identically |
| EOF at frame boundary | Empty stream when expecting new header | Clean close if protocol allows |
| EOF mid-header | Only 1–3 header bytes | Truncated header |
| EOF mid-payload | Length=N, fewer than N received | Truncated payload |
| Negative length | High bit set producing negative int | Rejected before allocation |
| Length over limit | Header greater than MAX | Rejected before allocation |
| Length 0 | Header equals 0 | Empty frame, if contract allows |
| Multi-byte UTF-8 | Character split across chunks | Text recovered intact once frame completes |
| Malformed UTF-8 | Invalid byte sequence | Rejected or handled per documented policy |
| Multiple requests on one connection | Consecutive frames in same stream | Does not require EOF between messages |
| NIO partial write | `write` returns less than remaining | Pending bytes not dropped |
| Two sender threads on one socket | Frames interleaved if unprotected | Use serialization; do not assume raw writes are atomic |
| Stalled peer | Partial header/body then idle | Deadline/timeout, cleanup |
| Fast sender | Many frames in one read | Bounded parsing, backpressure, ordering preserved |

### Property-Based Testing for the Decoder

Ideally, generate a byte sequence `frame(m1)+frame(m2)+...`, **split it randomly into chunks** across many seeds, feed them sequentially to the decoder, and compare the decoded message list against the original messages. This property must hold for every order-preserving split, including chunk size 1, large chunks containing multiple frames, and splits mid-UTF-8 character.

You do not need to induce real packet loss to test partial/coalesced frame decoding. Unit tests with deterministic byte slices are **better** for testing the parser; socket integration tests add end-to-end verification.

## 18. Advanced Hands-On Exercises

### Exercise A — Split One Frame Byte-by-Byte

In `TcpWriteShapeLab`, replace the three `write` calls for the `ALPHA` frame with:

```java
// Replacement snippet, not standalone.
for (byte b : first) {
    output.write(b & 0xff);
}
```

A 9-byte frame will be sent using **9 write calls**. Keep the server code unchanged. **Expected decoded messages remain `[ALPHA, RED, BLUE]`.** Do not expect `server.read` to run 9 times.

### Exercise B — Coalesce 100 Frames Into One Write

Create a `ByteArrayOutputStream`, append 100 frames in a loop per the contract, and send them in **a single `write` call**. Update the server's expected frame count from 3 to 100 and verify payload ordering/CRC. Cap total bytes so the test does not cause a memory spike. **Do not raise the 1024 frame limit** if each payload is under the limit.

### Exercise C — Random-Split Decoder

Create frames `M0..M99`, concatenate them into `byte[] all`, and pick chunk lengths using `Random(seed)`. Ensure the sum of chunks equals `all.length`, feed sequentially, and compare message lists. Run multiple seeds; on failure, log the seed and short hex dump to reproduce. The goal is to prove **chunking independence**.

### Exercise D — Unicode

Replace the `ALPHA` message with `"Xin chào 🌍"`, using `message.getBytes(UTF_8).length` in the header. Verify the server recovers the exact Unicode string even when network chunks split at any byte offset. Mind terminal encoding when printing Vietnamese on Windows, as a console encoding issue **does not mean a TCP framing bug**.

### Exercise E — Truncated Payload Error

Send a header with length 100, write only 10 bytes, and call `shutdownOutput()`. The server must report `EOFException`/protocol error instead of accepting a 10-byte message. You can unit-test with `TruncatedFrameDefenseDemo` before integration testing.

### Exercise F — Deliberately Trigger the `read(buffer)` Bug

Write a broken server that emits one message per `read` call. Then apply the split/coalesce sender and vary buffer sizes across 1, 2, 3, 8, and 4096. Record the misdecoded cases. Finally, replace the server with a length-prefix parser and run the same matrix to observe stable decoding. **Do not try to add sleep calls to fix a parser bug.**

### Exercise G — Delimiter Framing

Using `LineFramingLab`, change a payload to `"HELLO\nWORLD"` intending it as **one** logical message. Observe that `readLine` returns **two messages** without escaping. Design an escaping scheme or switch to length-prefixing, then re-test.

### Exercise H — Concurrency

Have two threads concurrently send frames on a single `Socket.getOutputStream()`, writing header and payload separately per frame. If each thread only locks individual `write` calls, bytes between frames can interleave. Implement **an outbound writer queue** and verify the decoder sees no corruption. Note this is a concurrency experiment: failure reproduction can depend on scheduling; the primary assertion is that once serialized, all messages decode cleanly.

## 19. Knowledge Check Questions

**Q1.** A client calls `write` three times for one message. Is the server guaranteed to call `read` three times in response?  
**Answer:** No. TCP only provides an ordered byte stream; read/write/segment boundaries have no 1:1 correspondence.

**Q2.** Can a single `write` call contain two application messages?  
**Answer:** Yes. If the sender concatenates two frames and writes one `byte[]`, the server must decode **two** messages based on framing.

**Q3.** Why does a 4 KB `read(buffer)` call not prove one message was received?  
**Answer:** Buffer capacity does not create boundaries. A `read` can return 1 byte, n bytes, or multiple frames depending on available data.

**Q4.** Does TCP preserve message boundaries of Java `OutputStream.write`?  
**Answer:** No. TCP is an ordered byte stream, not a datagram/message transport.

**Q5.** When is a 4-byte length-prefix typically decoded?  
**Answer:** Once all **4 header bytes** have arrived; validate the length before allocating or reading the body.

**Q6.** A frame header says length 5, but only two payload bytes arrive before EOF. Can the two-byte payload be accepted?  
**Answer:** No. This is a truncated frame and must raise a protocol error / `EOFException`.

**Q7.** Does a length-0 header mean stream EOF?  
**Answer:** No. Under this lab's contract, it is a valid empty frame; EOF only occurs when `read` returns `-1` at a boundary.

**Q8.** Why is `String.length()` unsuitable as a length header for UTF-8?  
**Answer:** Because `String.length()` measures UTF-16 code units, whereas the header must state the number of **UTF-8 bytes** sent.

**Q9.** Can `DataInputStream.readFully` use multiple underlying raw reads?  
**Answer:** Yes. It waits until `N` bytes are read or throws EOF/`IOException`, without relying on a single read.

**Q10.** A chunk contains `frame("TWO")+frame("THREE")`. How many messages does the decoder return?  
**Answer:** Two, in exact order; loop to process all complete frames.

**Q11.** When fed only 2 header bytes, what should the decoder do?  
**Answer:** Retain the pending bytes and wait for the next chunk, without calling `getInt` or parsing payload.

**Q12.** Does `ByteBuffer.compact()` automatically parse messages?  
**Answer:** No. It shifts unconsumed bytes and switches the buffer to write mode; the decoder must still perform framing.

**Q13.** Nonblocking `SocketChannel.write` returns 0 with pending bytes remaining; should you busy-loop?  
**Answer:** No. Register `OP_WRITE` / wait for readiness, retain the remaining buffer, and use a bounded queue.

**Q14.** Does `flush()` guarantee the receiver will get a corresponding `read`?  
**Answer:** No. `flush()` does not define TCP message boundaries.

**Q15.** Can `setTcpNoDelay(true)` fix a parser that treats one `read` as one message?  
**Answer:** No. It changes Nagle behavior, not TCP's byte-stream semantics.

**Q16.** Is the TCP PSH flag an End-of-Message marker?  
**Answer:** No. TCP segment flags do not replace application framing.

**Q17.** Does `InputStream.available()==0` mean a message is complete?  
**Answer:** No. It only estimates bytes currently readable without blocking.

**Q18.** Is an LF delimiter good for payloads that contain newlines?  
**Answer:** Not without escaping/encoding; a newline in the payload is interpreted as a separator.

**Q19.** If `BufferedReader.readLine` returns the final line on EOF without a trailing LF, is that valid in a protocol requiring a trailing newline?  
**Answer:** No. The API may return text before EOF, so a strict protocol must explicitly check for the terminator and reject missing delimiters.

**Q20.** If a header specifies a length of 2 billion bytes, should you execute `new byte[length]`?  
**Answer:** No. Validate against a max frame limit before allocation to prevent OOM/DoS.

**Q21.** Two threads interleave header/payload writes on the same socket; will TCP fix the frame boundaries?  
**Answer:** No. You must serialize the entire frame or use a single writer queue.

**Q22.** Why should you test a parser with fixed chunk sizes before varying network packet sizes?  
**Answer:** Because unit tests are deterministic; TCP packetization and scheduling are non-deterministic and do not determine whether application framing is correct.

**Q23.** If the receiver reads `ALPHA`/`RED`/`BLUE` intact, does that prove business-level ACKs are complete?  
**Answer:** It only proves the server decoder received/decoded them in the demo; business-level ACKs/commits require a separate protocol.

**Q24.** When a socket resets after a client sends a command, is it certain the server did not process the command?  
**Answer:** No. The server may have received and committed it before the reset; retries require idempotency or status queries per the contract.

## 20. Implementation Checklist and References

### Implementation Checklist

- [ ] Distinguish **application message**, **application frame**, **write call**, **read call**, and **TCP segment**.
- [ ] Never assume `read(buffer)` yields one message or `write` produces one TCP packet.
- [ ] Define an explicit framing contract: length-prefix, delimiter, fixed-size, or close-delimited as appropriate.
- [ ] For length-prefixing, agree on header size, endianness, payload **byte** count, charset, and max frame size.
- [ ] The decoder must **retain incomplete headers/payloads** across multiple receive chunks.
- [ ] The decoder must **process multiple frames in a single chunk** without dropping trailing bytes.
- [ ] Before allocating, **validate length** to prevent memory exhaustion, integer overflow, and malformed frames.
- [ ] Distinguish EOF at a frame boundary from EOF mid-header or mid-payload.
- [ ] Do not use `InputStream.available()` to measure message completeness.
- [ ] For text, decode UTF-8 **after assembling full message bytes** or use a streaming `CharsetDecoder` properly.
- [ ] For delimiters, specify escaping/line length limits and handle EOF without a terminator.
- [ ] For nonblocking `SocketChannel`, retain partial writes and handle `read()==0` separately from EOF.
- [ ] Serialize outbound frames when multiple threads share a connection.
- [ ] Enforce read timeouts, overall deadlines, per-connection quotas, concurrency limits, and backpressure.
- [ ] Do not rely on `flush()`, `TCP_NODELAY`, Nagle, or PSH/MSS to recover message boundaries.
- [ ] Unit-test the decoder across all chunk sizes and random seeds before TCP integration testing.
- [ ] Log byte counts and message IDs rather than asserting specific read or segment counts.
- [ ] For commands with side effects, design application-layer ACKs, deduplication, and idempotent retries.

**Key takeaway:** **Sending one message across multiple `write` calls is still one message** if framing says so. **Sending multiple messages in one `write` call is still multiple messages** if framing says so. TCP preserves the order of **bytes**, while **message boundaries are the responsibility of the application protocol and decoder**, not a byproduct of `read`/`write` call counts.

### References

- [RFC 9293 — Transmission Control Protocol, Sections 2.2 and 3.7](https://www.rfc-editor.org/rfc/rfc9293.html): TCP byte-stream service and segmentation do not guarantee mapping to application reads/writes.
- [Java 17 `InputStream.read`, `readNBytes`, `available`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): actual bytes read, EOF, `readNBytes`, and why `available` is not framing.
- [Java 17 `DataInputStream.readInt` and `readFully`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): reading length-prefixes and throwing EOF on truncated payloads.
- [Java 17 `Socket` — `setSoTimeout`, `shutdownOutput`, `setTcpNoDelay`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html).
- [Java 17 `SocketChannel` — nonblocking reads/writes](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html).
- [Java 17 `ByteBuffer` — flip, compact, endian](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html).
- [Java 17 `BufferedReader.readLine`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html).
