# Bounding Message Size Before Memory Allocation

## 1. The Problem: TCP Is a Byte Stream, While Message Size May Be Supplied by the Peer

TCP provides an **ordered byte stream**. It has no concept of "one `write` is one message": a single `read` may receive a partial piece, multiple pieces, or data from multiple writes. To distinguish boundaries, an application needs **framing rules**, such as sending four bytes announcing the length before each piece of data.

The danger arises when using an unvalidated length from the network to allocate memory:

~~~java
DataInputStream in = new DataInputStream(socket.getInputStream());
int length = in.readInt();
byte[] payload = new byte[length]; // Wrong: client data dictates allocation.
in.readFully(payload);
~~~

*The snippet above illustrates **what not to do**, not a standalone program.*

Simply by sending a four-byte header describing a very large length, an untrusted peer can cause the program to request a huge array. When that happens, the server may suffer `OutOfMemoryError`, GC pressure, high latency, or denial of service for other connections. The peer does not even **need to send a single byte of payload**. A negative header can cause `new byte[length]` to throw `NegativeArraySizeException`.

**Rule:** validate the length value and resource budget **before any allocation or size calculation based on length**. Only after it is valid should you begin reading the full frame and decoding the content.

## 2. Limits Must Be Defined Based on the Wire Format

This example uses a custom TCP protocol:

~~~text
       4-byte header            length-byte payload
+------------------------+------------------------------+
| Signed 32-bit length   | Message content              |
+------------------------+------------------------------+

Frame of "HELLO":
00 00 00 05  48 45 4C 4C 4F
[4 bytes=5]  [5-byte payload]
~~~

`DataOutputStream.writeInt` writes a 4-byte `int` in big-endian byte order; `DataInputStream.readInt` reads those exact four bytes into a signed `int`. **This is an application framing convention**, not a built-in feature of TCP.

Example convention: the length value counts only the **payload**, excluding the four header bytes. Therefore, a 1024-byte payload frame has a total wire size of 1028 bytes.

An explicit policy might be:

| Component | Rule |
| --- | --- |
| Header | 4-byte signed `int`, big-endian |
| Maximum payload size | `MAX_PAYLOAD_BYTES = 1_048_576` (1 MiB), for example only |
| Negative header | Reject immediately |
| Header equal to 0 | Accept if the protocol allows empty messages |
| Header from 1 to `MAX_PAYLOAD_BYTES` | Valid in size, begin reading the exact payload |
| Header greater than `MAX_PAYLOAD_BYTES` | Reject before creating an array or buffer |

The 1 MiB mark is **not a default limit or a safe value for every system**. A control command might be limited to a few KiB; a file transfer stream requires a chunked reading design. In the two demonstration runs below, the limits are intentionally chosen as 1024 and 16 bytes so that errors are clearly visible.

Do not confuse **byte count** with **character count**. A UTF-8 string, especially in Vietnamese, can take more bytes than visible characters; `String.length()` counts UTF-16 code units. If the protocol declares "maximum 1024 bytes", enforce the limit on the **number of bytes received from the network before converting to String**.

## 3. Standard Workflow: read header → validate → allocate → readFully

With a 4-byte length prefix:

1. Read **exactly four bytes** using `DataInputStream.readInt()`. If the header is incomplete, the method throws `EOFException`; do not guess the length.
2. Check both ends of the range: `length < 0` or `length > MAX_PAYLOAD_BYTES` are both errors. If empty messages are forbidden, also check `length == 0`.
3. Only **after validation**, allocate `new byte[length]`.
4. Use `readFully(payload)` to receive all declared bytes. TCP can split a payload across multiple reads, so **do not** assume a single `read(payload)` will suffice.
5. If EOF, timeout, or connection loss occurs before the full payload arrives, **do not process the incomplete frame**. Close/discard the connection according to policy to avoid decoding partial data.
6. Once the full payload is received, proceed to validate format, charset, authentication, compression, or business content; a valid header only proves that **the declared length is within the limit**, not that the payload is valid.

Core algorithm pattern:

~~~java
static final int MAX_PAYLOAD_BYTES = 1024;

static byte[] readFrame(InputStream source) throws IOException {
    DataInputStream in = new DataInputStream(source);
    int length = in.readInt();
    if (length < 0 || length > MAX_PAYLOAD_BYTES) {
        throw new IOException("invalid length: " + length);
    }
    byte[] payload = new byte[length]; // Only executed after the check.
    in.readFully(payload);
    return payload;
}
~~~

*This is an illustrative method that must be placed in a class that imports `java.io.*`. The complete program is in section 5.*

`readFully` continues reading until the requested length is satisfied, end of stream (`EOFException`) is reached, or an I/O error occurs. A 0-length array is handled immediately without waiting for any payload.

A production system typically keeps one reader per connection and reads frames sequentially. For a frame whose header exceeds the limit, the simplest way to avoid losing synchronization is to **reject the frame and close the connection**, rather than trying to read and discard a huge number of bytes according to a malicious header.

## 4. Unsafe Patterns and How to Fix Them

| Pattern | Why It Is Wrong | How to Handle |
| --- | --- | --- |
| `new byte[in.readInt()]` | Uses an unvalidated length to allocate immediately | Read into a variable, check min/max first |
| `if (length <= MAX)` | Fails to exclude negative lengths | Use `length >= 0 && length <= MAX` |
| `byte[] p = new byte[length]; if (length > MAX)...` | Check after allocation | Move check before allocation |
| `int total = length + 4; if (total <= MAX)...` | Adding before checking can overflow `int` | Validate length first; use `long` or `Math.addExact` |
| `if (in.available() >= length) ...` | `available()` does not reflect bytes yet to arrive or message length | Read proper framing with `readFully` and timeout |
| `in.readAllBytes()` on a long-lived socket | Can accumulate unbounded data or wait for EOF forever | Bound frames and read in a controlled manner |
| `in.readNBytes(length)` before validation | Can allocate according to a malicious length | Only use after checking bounds |
| Comparing `String.length()` against a byte limit | UTF-16 code unit count differs from UTF-8 byte count | Enforce limit on raw bytes before decoding |
| Limiting only compressed data | A small payload can expand enormously | Limit decompressed size as well |
| Allocating 1 MiB across thousands of connections | Each frame fits its limit, yet total memory is still too large | Total RAM quota, connection limits, and backpressure |

When you want to calculate the **total bytes of a frame**, remember the protocol's prefix length: for example, `4L + length` for a 4-byte header. Use `long` to avoid `int` overflow before comparing. Do not allocate a "total frame" array before checking.

If the length format is actually **unsigned 32-bit**, do not use `readInt()` and then pass a negative number as an array size. You can convert `int raw = in.readInt()` to `long unsignedLength = Integer.toUnsignedLong(raw)`, then check `unsignedLength <= MAX_PAYLOAD_BYTES` as a `long` **before casting to `int`**. Both sender and receiver must agree on signed/unsigned; neither side may unilaterally change the convention.

## 5. Java 17+ Example: Demonstrating Length Rejection Before Allocation

The example runs on an in-memory byte stream, without depending on a server or the Internet. The `frame(...)` helper intentionally accepts an arbitrary header to **simulate a peer sending malformed data**. A production writer must validate length before sending, but a reader must never trust that every peer is a well-behaved writer.

Save the file `FrameBoundsDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class FrameBoundsDemo {
    private static final int MAX_PAYLOAD_BYTES = 1024;

    static byte[] readFrame(InputStream source) throws IOException {
        DataInputStream in = new DataInputStream(source);
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD_BYTES) {
            throw new IOException("invalid length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return payload;
    }

    static byte[] frame(int announcedLength, byte[] actualPayload)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(bytes);
        out.writeInt(announcedLength);
        out.write(actualPayload);
        return bytes.toByteArray();
    }

    public static void main(String[] args) throws IOException {
        byte[] hello = "HELLO".getBytes(StandardCharsets.UTF_8);
        System.out.println("valid payload: " +
                new String(readFrame(new ByteArrayInputStream(
                        frame(hello.length, hello))), StandardCharsets.UTF_8));

        System.out.println("empty payload bytes: " +
                readFrame(new ByteArrayInputStream(frame(0, new byte[0]))).length);

        try {
            readFrame(new ByteArrayInputStream(frame(-1, new byte[0])));
        } catch (IOException e) {
            System.out.println("negative rejected: " + e.getMessage());
        }

        try {
            readFrame(new ByteArrayInputStream(frame(1025, new byte[0])));
        } catch (IOException e) {
            System.out.println("oversize rejected: " + e.getMessage());
        }

        try {
            readFrame(new ByteArrayInputStream(frame(5, new byte[] { 65, 66 })));
        } catch (EOFException e) {
            System.out.println("truncated rejected: " + e.getClass().getSimpleName());
        }
    }
}
~~~

Compile and run:

~~~bash
javac FrameBoundsDemo.java
java FrameBoundsDemo
~~~

Output:

~~~text
valid payload: HELLO
empty payload bytes: 0
negative rejected: invalid length: -1
oversize rejected: invalid length: 1025
truncated rejected: EOFException
~~~

Demonstrated cases:

- Header `5` with all five bytes `HELLO` succeeds.
- Header `0` is valid under the current policy and returns an empty array.
- Header `-1` or `1025` is rejected **immediately after reading the header** when `MAX_PAYLOAD_BYTES == 1024`, without requiring the peer to send any payload.
- Header `5` with only two bytes `AB` causes `readFully` to throw `EOFException`; the reader must not turn `AB` into a successful message.

`readInt()` can also throw `EOFException` if the stream ends before all 4 header bytes are read. When receiving multiple frames on the same TCP connection, the protocol should distinguish **EOF at a clean frame boundary** (normal client close) from **EOF after a header/payload has started** (incomplete frame). Calling `readInt()` alone does not tell you whether 0 or 1–3 bytes were received before EOF; if you need to distinguish them, you must read/count header bytes yourself based on the number of bytes received.

## 6. Java 17+ Example: Frame Limit Over Real TCP Loopback

Now use `ServerSocket` and `Socket` on the same machine. The server sets `MAX_PAYLOAD_BYTES = 16`. The first connection sends `"OK"`; the second connection sends only the header `17` and **sends no payload**. The reader must reject immediately because 17 exceeds 16, rather than waiting for payload or creating an array.

Save the file `TcpFrameLimitDemo.java`:

~~~java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

public class TcpFrameLimitDemo {
    private static final int MAX_PAYLOAD_BYTES = 16;

    static byte[] readFrame(InputStream source) throws IOException {
        DataInputStream in = new DataInputStream(source);
        int length = in.readInt();
        if (length < 0 || length > MAX_PAYLOAD_BYTES) {
            throw new IOException("invalid length: " + length);
        }
        byte[] payload = new byte[length];
        in.readFully(payload);
        return payload;
    }

    public static void main(String[] args) throws IOException {
        try (ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(2_000);

            try (Socket sender = new Socket(
                    listener.getInetAddress(), listener.getLocalPort());
                 Socket receiver = listener.accept()) {
                receiver.setSoTimeout(2_000);
                DataOutputStream out = new DataOutputStream(sender.getOutputStream());
                byte[] message = "OK".getBytes(StandardCharsets.UTF_8);
                out.writeInt(message.length);
                out.write(message);
                out.flush();

                byte[] received = readFrame(receiver.getInputStream());
                System.out.println("accepted: " +
                        new String(received, StandardCharsets.UTF_8));
            }

            try (Socket sender = new Socket(
                    listener.getInetAddress(), listener.getLocalPort());
                 Socket receiver = listener.accept()) {
                receiver.setSoTimeout(2_000);
                DataOutputStream out = new DataOutputStream(sender.getOutputStream());
                out.writeInt(MAX_PAYLOAD_BYTES + 1);
                out.flush();

                try {
                    readFrame(receiver.getInputStream());
                } catch (IOException e) {
                    System.out.println("oversize rejected: " + e.getMessage());
                }
            }
        }
    }
}
~~~

Run:

~~~bash
javac TcpFrameLimitDemo.java
java TcpFrameLimitDemo
~~~

Output when the environment permits TCP loopback connections:

~~~text
accepted: OK
oversize rejected: invalid length: 17
~~~

Why this example is valuable:

1. `new ServerSocket(0, 8, InetAddress.getLoopbackAddress())` listens on loopback and lets the OS assign a server port, avoiding reliance on a hardcoded port number.
2. `DataOutputStream.writeInt` is compatible with `DataInputStream.readInt`: one side declares the byte length, and the other reads the exact same format.
3. `receiver.setSoTimeout(2_000)` bounds the duration of a single blocking read operation; it protects if the peer declares a valid length but stops sending the payload. This timeout is **not a total deadline for the entire frame**.
4. On the second connection, the program checks `length > MAX_PAYLOAD_BYTES` before `new byte[length]`; no allocation depending on `17` occurs and `readFully` is not called.
5. `try-with-resources` closes the sockets. In a real service, you need to distinguish protocol violation error types and handle/log them appropriately; the demo uses a generic `IOException` to focus on the validation order.

## 7. A Per-Message Limit Is Not a System-Wide Memory Limit

Suppose each valid frame is at most **1 MiB**. If 200 concurrent connections all cause the server to hold arrays of nearly 1 MiB, **the payload arrays alone** already occupy nearly **200 MiB**, not counting TCP buffers, Java objects, threads, parsed data, and copies.

Therefore, a system under load needs two layers of protection:

- **Per-frame limit:** check `0 <= length <= MAX_PAYLOAD_BYTES` before allocation, independent of how much the client claims it wants.
- **Aggregate limits:** bound the number of connections, bytes queued for processing, frames being decoded, and task queues. When the budget is exhausted, apply **backpressure**, reject, or pause accepting more by design.

In addition, a small frame does not guarantee cheap processing:

| Incoming Data | Remaining Risk | Mitigation |
| --- | --- | --- |
| Many very small frames | Total requests or bytes/second too high | Rate limit, global quota, bounded queues |
| Small compressed payload | Expands into huge data (decompression bomb) | Limit decompressed bytes and cost |
| Deeply nested JSON/XML | Parser consumes excessive RAM or CPU | Limit depth, node count, string size |
| Payload sends only header then stalls | Buffers/connections stay open long, wasting resources | Timeout, overall deadline, read-rate |
| Many frames awaiting business logic | Backlog data accumulates | Bounded queue, semaphore, streaming processing |

`OutOfMemoryError` should not be treated as a normal exception for rejecting payloads. By the time it happens, the JVM may already have lost its ability to serve stably.

## 8. Streaming: Reading Payload in Chunks When Keeping Everything in RAM Is Unnecessary

For use cases that need to forward or store long data, instead of allocating `byte[length]` after validation, you can **validate length and then read in fixed-size chunks**. The helper example below uses an 8 KiB buffer and does not read past the remaining bytes of the frame:

~~~java
static void copyLimitedFrame(InputStream input, OutputStream output, int length)
        throws IOException {
    final int maxFrameBytes = 1024 * 1024;
    if (length < 0 || length > maxFrameBytes) {
        throw new IOException("invalid length: " + length);
    }

    byte[] chunk = new byte[8192];
    int remaining = length;
    while (remaining > 0) {
        int count = input.read(chunk, 0, Math.min(chunk.length, remaining));
        if (count < 0) {
            throw new EOFException("truncated payload");
        }
        if (count == 0) {
            continue;
        }
        output.write(chunk, 0, count);
        remaining -= count;
    }
}
~~~

*Illustrative method; requires a class with `import java.io.*`. The caller reads the header first and passes a valid length, managing streams, timeouts, and the destination. This is not a standalone program.*

`remaining` decreases by the number of bytes **actually read**, not by the number of bytes requested. This both handles short reads and avoids consuming bytes belonging to the next frame. The fixed `8192`-byte buffer keeps RAM usage bounded per stream.

However, if `output` is a `ByteArrayOutputStream`, it can **still** hold all the data in memory. For true streaming, you need a bounded consumer destination, such as writing to a temporary file or processing chunks continuously. Do not publish a file/object as "complete" until all data has been received and necessary integrity and authentication checks have passed. Temporary files/disk also need quotas to avoid shifting the DoS problem from RAM to storage.

## 9. Avoiding Integer and Type Conversion Bugs When Reading Length

A dangerous bug is computing the total size using `int` **before** validation:

~~~java
int total = length + 4; // Can overflow integer.
if (total <= MAX_FRAME_BYTES) {
    byte[] frame = new byte[total];
}
~~~

*This is a wrong example of check ordering; do not use it as production code.*

If length is near `Integer.MAX_VALUE`, adding 4 can wrap around to a negative number. The right workflow is to check the **non-negative and at-most-max** range first, then compute `long total = 4L + length` or `Math.addExact(4, length)` and compare against the total frame limit.

With an 8-byte header, `DataInputStream.readLong()` can read numbers far larger than Java array sizes: you must compare as `long` **before** casting. With an unsigned 32-bit header, read raw `int` and convert via `Integer.toUnsignedLong(raw)`, validating the `long` value before casting to `int`; never let a large unsigned value become a negative signed value and enter allocation.

Do not assume byte order: `DataInputStream.readInt` is big-endian. If an external protocol is little-endian, decode accordingly; a byte-order mismatch between two sides can turn a small header into a massive length.

## 10. EOF, Timeouts, and Handling Malformed Frames

- `DataInputStream.readInt()` reads four header bytes. If there are not enough, `EOFException` signals the stream ended early; do not attempt to guess the length.
- `DataInputStream.readFully(byte[])` returns only when the entire payload has been read; if EOF occurs midway, it throws `EOFException`. Do not treat a partially populated array as a complete message.
- `Socket.setSoTimeout(milliseconds)` is the timeout for **each blocking read operation** on the socket, which can raise `SocketTimeoutException`. It is not an overall deadline for the entire frame: a peer sending one byte slowly can stretch out the total time. An overall deadline or minimum read-rate requirement is needed when the system must defend against slow clients.
- If a header exceeds the limit, reject immediately and close the connection; do not read and discard a huge number of bytes based on an untrusted length field, unless the protocol has its own bounded recovery mechanism.
- If a read times out after receiving part of a payload, to preserve framing you should generally close the connection; continuing as if the frame had never started easily desynchronizes boundaries.
- Use `try-with-resources` for `Socket`/`ServerSocket` and handle `IOException`. Do not log entire untrusted payloads or include sensitive data/stack traces in peer responses.
- Limit concurrent connections and bytes held simultaneously, even when **each** message obeys the max. An array of valid length can still fail to allocate if the global budget is exhausted.

Valid length is only a **necessary condition**. The payload can still have an invalid charset, invalid JSON/XML, invalid checksum/signature, or content that makes processing expensive. Downstream decoding layers must further limit element counts, nesting depth, decompressed bytes, and generated records.

## 11. Questions to Decide When Designing a Protocol

| Question | Must Be Agreed Upon Before Implementation |
| --- | --- |
| How are frame boundaries defined? | 4/8-byte prefix, delimiter, or other framing |
| What does length include? | Payload only, or total header + payload |
| What are the type and endianness? | Signed/unsigned, big-endian/little-endian |
| Are empty messages valid? | Whether `length == 0` is allowed |
| Max frame and max payload? | Configured values **controlled by the server**, with a budget |
| Where does validation live? | Before any allocation and overflow-prone arithmetic |
| EOF mid-frame? | Discard partial frame, do not process incomplete data |
| Oversized header error? | Close connection or use a clearly bounded recovery mechanism |
| Total concurrent bytes/connections? | Quotas for RAM, time, queues, and disk |
| Compression or nested parsing? | Limit decompressed bytes/depth/objects |
| Must the whole payload stay in RAM? | If not, use a fixed buffer and a quota-bounded consumer |

A useful invariant for code review: **on every execution path, no peer-controlled length data reaches an allocation or dangerous size calculation before being constrained to a valid value range**.

## 12. Questions and Hands-On Practice

**Question 1.** A client sends the prefix `2_000_000_000` and disconnects immediately. Why is `new byte[in.readInt()]` dangerous even with no payload?

Answer: the JVM attempts to allocate nearly 2 billion bytes as soon as the header is received; out-of-memory can occur before the payload read step.

**Question 2.** A protocol allows `0 <= length <= 1024`. How should lengths `-1`, `0`, `1024`, and `1025` be handled?

Answer: reject `-1` and `1025`; allow `0` and `1024`. If the protocol forbids empty messages, add a condition to reject `0`.

**Question 3.** A header announces 6 bytes, but one `read()` returns only 2 bytes. Is the peer violating the protocol?

Answer: **not yet**. TCP is allowed to deliver data in pieces. Keep reading until all 6 bytes arrive, EOF occurs, or a timeout is hit according to policy.

**Question 4.** Does a 1 MiB max frame protect the JVM from all out-of-memory scenarios?

Answer: no. Many connections holding frames simultaneously and copies made after parsing/decompression can still consume lots of memory; aggregate limits are required.

**Question 5.** A header says 100 KiB compressed, which decompresses to 500 MiB. Is checking a 1 MiB MAX payload enough?

Answer: no. You must limit **decompressed bytes**, parser node count/depth, and total resources.

**Practice:** reduce `MAX_PAYLOAD_BYTES` in `FrameBoundsDemo` to `4`. Change the `"HELLO"` payload (5 bytes) to `"JAVA"` (4 bytes) to verify the exact upper-bound valid value. Next, try declaring `4` while sending only 2 bytes, and verify `EOFException`. In `TcpFrameLimitDemo`, try declaring a valid length but delaying sending the payload to observe the timeout; do not increase the timeout indefinitely just to make the run pass.

## API Documentation (Java SE 21)

- [`DataInputStream`, `readInt`, and `readFully`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html)
- [`DataOutputStream` and `writeInt`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataOutputStream.html)
- [`DataInput` and `readFully` behavior on EOF](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInput.html)
- [`Socket` and `setSoTimeout`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/Socket.html)
- [`InputStream` and `readNBytes`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/InputStream.html)
