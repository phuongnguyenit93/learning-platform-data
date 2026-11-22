# Byte Order and Sending Integers with DataInputStream or ByteBuffer in TCP Messages

## 1. Objectives and Problem Statement

TCP only transmits **an ordered sequence of bytes**; it does not inherently understand "this is an integer," "this is a header," or "this is a message." When Java sends multi-byte integers, both sides must agree on **integer width**, **byte order**, **signed vs. unsigned type**, and **how message boundaries are determined**. If any of these conventions is missing, two programs may establish a TCP connection successfully yet misinterpret the data.

Consider the 32-bit integer `0x01020304`. For the same number, two common ways to write the 4 bytes are:

~~~text
Logical value: 0x01020304

Big-endian:     01 02 03 04   (most significant byte first)
Little-endian:  04 03 02 01   (least significant byte first)
~~~

If one side sends `01 02 03 04` and the other reads it as little-endian, it will obtain `0x04030201`—a **completely different** value, even though no bytes were lost or reordered on the wire.

After this lesson, you should be able to:

- Explain big-endian/little-endian, "network byte order," and the scope of TCP's responsibility.
- Know that `DataOutputStream.writeInt()` / `DataInputStream.readInt()` always use big-endian; know the default `ByteBuffer.order(...)` and how to select little-endian.
- Encode and decode fixed-width `short`, `int`, and `long` values; distinguish signed vs. unsigned bytes.
- Combine integers with **length-prefix framing**, reading all required bytes even when TCP splits data across multiple reads.
- Detect byte-order mismatches, insufficient bytes, invalid lengths, misread buffer states, and resource limits.

This lesson focuses on transmitting **binary integers** in TCP messages; this is the foundation before learning more complex application protocols.

## 2. What Is Byte Order and Why Must It Be Specified?

### 2.1. Bytes Do Not Carry Their Own Data Type

Each byte has 8 bits and a raw value from 0–255. A Java `int` has **32 bits = 4 bytes**; `short` has 16 bits = 2 bytes; `long` has 64 bits = 8 bytes. When transmitted over an `OutputStream` or socket, the value's bits must be represented as a sequence of bytes.

For the value `0x01020304`, the four bytes in order of significance are:

| Byte | Hex | Weight in 32-bit integer |
| --- | --- | --- |
| B3 (highest) | `01` | `0x01 × 2^24` |
| B2 | `02` | `0x02 × 2^16` |
| B1 | `03` | `0x03 × 2^8` |
| B0 (lowest) | `04` | `0x04 × 2^0` |

In **big-endian**, byte B3 comes first: `01 02 03 04`. In **little-endian**, B0 comes first: `04 03 02 01`. This ordering applies to the **bytes of a multi-byte field**, not to bits within each byte running in reverse. For a **single byte**, there is no endianness difference.

### 2.2. Is Network Byte Order a Feature of TCP?

In many standard network protocols, "**network byte order**" means **big-endian** for multi-byte integer fields. For example, binary fields following Internet specifications may mandate sending the most significant byte first.

However, it is important to distinguish:

- **TCP** only provides a byte stream; it preserves the order of bytes sent and **does not automatically convert byte order** in the application payload.
- **The application protocol** decides whether a 4-byte length header uses big-endian, a numeric payload uses little-endian, or vice versa.
- **The CPUs of the sending/receiving machines** may have different native byte orders; do not use native order as a wire format convention if you want clients to interoperate reliably.

A protocol is not wrong just because it chooses little-endian. The mistake lies in **failing to publish or agree on** how to decode it. For example, a custom protocol can perfectly well specify that the length is big-endian and measurement data is little-endian; both sides must follow each field's rule.

### 2.3. Visualizing the Difference on the Same 4 Bytes

~~~text
Wire bytes:     01 02 03 04
                │  │  │  │
Decode BE:      └───────────→ 0x01020304 = 16909060
Decode LE:      └───────────→ 0x04030201 = 67305985

Wire bytes:     04 03 02 01
Decode LE:                   → 0x01020304 = 16909060
Decode BE:                   → 0x04030201 = 67305985
~~~

This is a **representation** difference. Once decoded into a Java `int`, the logical value is used normally; byte order matters again when encoding the value back into bytes.

## 3. DataOutputStream and DataInputStream: Big-Endian Integers

### 3.1. Rules of `writeInt()` and `readInt()`

`DataOutputStream` wraps an `OutputStream` and provides methods for writing Java primitive types. `writeInt(int v)` writes **exactly 4 bytes**, high byte first—that is, **big-endian**. `DataInputStream.readInt()` reads **all 4 bytes** and assembles them using the same big-endian convention into a signed `int`.

Illustrative example:

~~~java
// Illustrative snippet; requires importing java.io.*
ByteArrayOutputStream bytes = new ByteArrayOutputStream();
try (DataOutputStream out = new DataOutputStream(bytes)) {
    out.writeInt(0x01020304);
}

byte[] encoded = bytes.toByteArray(); // [0x01, 0x02, 0x03, 0x04]
try (DataInputStream in = new DataInputStream(
        new ByteArrayInputStream(encoded))) {
    int decoded = in.readInt();        // 0x01020304
}
~~~

The snippet above is illustrative code inside a method that can throw `IOException`, not a standalone program. It uses memory so you can see the exact bytes before applying it to TCP.

Commonly used methods:

| Method | Width | Byte order / interpretation |
| --- | --- | --- |
| `DataOutputStream.writeByte(int)` | Low 1 byte | No endianness difference |
| `writeShort(int)` / `readShort()` | 2 bytes | Big-endian; reading returns signed `short` |
| `writeInt(int)` / `readInt()` | 4 bytes | Big-endian; reading returns signed `int` |
| `writeLong(long)` / `readLong()` | 8 bytes | Big-endian; reading returns signed `long` |
| `DataInputStream.readUnsignedByte()` | 1 byte | Returns `int` in range 0–255 |
| `DataInputStream.readUnsignedShort()` | 2 bytes | Big-endian; returns `int` in range 0–65535 |
| `DataInputStream.readFully(byte[])` | Array length | Reads all bytes, or throws `EOFException` on premature end of stream |

`DataInputStream` and `DataOutputStream` **have no option to switch to little-endian** for `readInt()`/`writeInt()`. If the protocol requires little-endian, use `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` or encode each byte explicitly; do not assume `ByteOrder.nativeOrder()` will change `DataOutputStream`.

### 3.2. What Happens If Fewer Than 4 Bytes Have Arrived?

`readInt()` waits until all 4 bytes are read, EOF is reached, or an I/O error occurs according to the stream/socket timeout policy. If EOF arrives after 1, 2, or 3 bytes, `readInt()` throws `EOFException`. It **does not** return a "partial" integer. That is why `readInt()` is suitable for a 4-byte header over TCP.

Important: a single `InputStream.read(byte[4])` call **does not** guarantee reading all 4 bytes at once. In contrast, `DataInputStream.readFully(byte[])` loops until the array is full and throws an error if EOF occurs prematurely. For a frame, you should use `readInt()` for the prefix and `readFully(payload)` for the payload whose length has been validated.

If you already have a `DataInputStream` wrapping a socket, do not create an additional `BufferedReader` or independent reading stream on the same socket to handle other frames: the buffering layer may read ahead, causing the wrappers to compete for bytes.

### 3.3. Writing Numbers to a Socket and `flush()`

~~~java
// Connected socket; illustrative example, not a standalone program.
DataOutputStream out = new DataOutputStream(
        new BufferedOutputStream(socket.getOutputStream()));
out.writeInt(0x01020304);
out.flush();
~~~

`writeInt()` converts the value into 4 big-endian bytes. `flush()` ensures that the Java-layer buffer pushes data down to the underlying stream, because `BufferedOutputStream` may hold unsent bytes. It **does not** confirm that the peer has received or processed the number; for that, an application-layer response is required.

Note that `DataOutputStream.writeUTF()` uses a **modified UTF-8** variant and its own length prefix; it is unrelated to the fixed 4-byte rule of `writeInt()` and is not automatically a general cross-language UTF-8 wire format.

## 4. ByteBuffer: Explicitly Choosing BIG_ENDIAN or LITTLE_ENDIAN

### 4.1. Creating and Using a ByteBuffer

`java.nio.ByteBuffer` stores bytes with read/write ordering and provides `putInt()`/`getInt()`, `putShort()`/`getShort()`, and `putLong()`/`getLong()` methods. **The default byte order of a new ByteBuffer is BIG_ENDIAN.** To change it, call `order(ByteOrder.LITTLE_ENDIAN)`.

~~~java
import java.nio.ByteBuffer;
import java.nio.ByteOrder;

int value = 0x01020304;

ByteBuffer big = ByteBuffer.allocate(Integer.BYTES);
big.putInt(value); // Default BIG_ENDIAN: 01 02 03 04

ByteBuffer little = ByteBuffer.allocate(Integer.BYTES)
        .order(ByteOrder.LITTLE_ENDIAN);
little.putInt(value); // LITTLE_ENDIAN: 04 03 02 01
~~~

These are two independent writes into **4-byte** buffers. For a heap buffer created with `allocate(...)`, `array()` can be used to access the backing byte array; for a direct buffer created with `allocateDirect(...)`, you should not assume `array()` is supported. If you need to extract bytes generically, you can read them via `get(byte[])` after calling `flip()`.

When receiving 4 bytes from the network, set the order **before reading the number**:

~~~java
byte[] raw = {4, 3, 2, 1};
int decoded = ByteBuffer.wrap(raw)
        .order(ByteOrder.LITTLE_ENDIAN)
        .getInt();
// decoded == 0x01020304
~~~

`ByteBuffer.order(ByteOrder.BIG_ENDIAN)` is used when the protocol writes the high byte first; `ByteBuffer.nativeOrder()` describes the platform's native byte order, but **is not a protocol default**. Declare the wire format's byte order with an explicit constant, independent of hardware.

### 4.2. Position, Limit, Flip, and BufferUnderflowException

`ByteBuffer` has three concepts:

- **capacity:** the total number of bytes it can hold.
- **position:** the index of the next operation.
- **limit:** the allowed boundary of bytes currently being read or written.

After `putInt()`, `position` advances by 4. If you want to read back from **the same buffer**, you must switch from write phase to read phase using `flip()`:

~~~java
ByteBuffer buf = ByteBuffer.allocate(4)
        .order(ByteOrder.LITTLE_ENDIAN);

buf.putInt(0x01020304);      // position = 4, limit = 4
buf.flip();                  // position = 0, limit = 4
int number = buf.getInt();   // number == 0x01020304
~~~

If you forget `flip()`, `getInt()` may throw `BufferUnderflowException` because there are not 4 readable bytes remaining from the current position. Conversely, calling `putInt()` on a buffer without enough space throws `BufferOverflowException`. These buffer errors are distinct from network stream `EOFException` and `SocketTimeoutException`.

`clear()` only resets the indices and **does not erase the actual bytes**; `compact()` preserves unread bytes for the next write. In non-blocking NIO, `SocketChannel.read(ByteBuffer)` may read fewer bytes than requested or return 0; `SocketChannel.write(ByteBuffer)` may also write fewer bytes than remaining. You must maintain `position`, `limit`, and `hasRemaining()` state across multiple passes, using a `Selector` to wait when not ready instead of busy-spinning the CPU.

### 4.3. DataInputStream and ByteBuffer Are Equivalent Under the Same Order

Given the same 4 bytes `01 02 03 04`:

~~~text
new DataInputStream(...).readInt()              -> 0x01020304
ByteBuffer.wrap(bytes).getInt()                 -> 0x01020304
ByteBuffer.wrap(bytes).order(BIG_ENDIAN)
                      .getInt()                 -> 0x01020304

ByteBuffer.wrap(bytes).order(LITTLE_ENDIAN)
                      .getInt()                 -> 0x04030201
~~~

The equivalence only comes from **having the same byte-order convention**, not from the two APIs reading from TCP in the same way. `DataInputStream` directly reads the required bytes from the stream; `ByteBuffer.getInt()` only reads **bytes already present in the buffer**, throwing underflow if there are not enough. When using `ByteBuffer` over a socket, accumulating enough bytes is the responsibility of the network reader/state machine.

## 5. Sending Integers in a TCP Message: Framing + Endianness

### 5.1. Why Are Message Boundaries Necessary?

TCP guarantees an ordered byte stream within a connection, but does not preserve the boundaries of each `write()` call. If you send two `int` values consecutively, the receiver cannot assume that two `read(byte[])` calls will correspond to the two integers. What can happen is:

~~~text
Sender calls write() containing 8 bytes:  01 02 03 04 05 06 07 08

Receiver may read:
  Call 1: 01 02
  Call 2: 03 04 05
  Call 3: 06 07 08

Or:
  Call 1: 01 02 03 04 05 06 07 08
~~~

For a fixed-structure sequence of integers, the receiver can read **exactly 4 bytes per integer** according to the protocol. For variable-length messages, a **length prefix** is commonly used—for example, a 4-byte big-endian length followed by a payload of `length` bytes. When the payload contains a little-endian integer, the protocol can explicitly specify **BE header, LE payload**.

### 5.2. A Concrete Demo Protocol

In the demo in the next section, the request has the format:

~~~text
┌─────────────────────────┬──────────────────────────┐
│ Header: length (4 byte) │ Payload: integer (4 byte)│
│ Big-endian              │ Little-endian            │
└─────────────────────────┴──────────────────────────┘

Sending 0x01020304:
    header length = 4             payload integer = 0x01020304
        00 00 00 04                    04 03 02 01

Full wire bytes:
        00 00 00 04 | 04 03 02 01
~~~

The server reads sequentially:

1. Uses `DataInputStream.readInt()` to read the **4-byte header** in big-endian to get the payload length.
2. Validates that the length is valid (**exactly 4 bytes** in the demo) before allocating the array.
3. Calls `readFully(payload)` to gather all 4 payload bytes, regardless of how TCP segments the data.
4. Uses `ByteBuffer.wrap(payload).order(LITTLE_ENDIAN).getInt()` to decode the integer.
5. Sends an ACK via `DataOutputStream.writeInt(value)`, meaning a **4-byte big-endian ACK**.

The wire bytes of the ACK are `01 02 03 04`. This is a custom protocol defined for learning the difference between the two APIs; it is neither a default TCP format nor a general standard.

The format assumes every request message contains exactly one 32-bit integer. For a larger protocol, you need to document the version, message type, maximum frame size, signedness, byte order of each field, error reporting, and responses.

## 6. Complete Java 17+ Example: TCP Sending Little-Endian Int with Big-Endian Header and ACK

The demo runs **entirely on loopback**, without any external server. It creates a TCP server on an ephemeral port, runs a worker, opens a local client, sends a length-prefixed frame, and receives an ACK. The code uses both `DataOutputStream`/`DataInputStream` and `ByteBuffer` to make byte order clear.

Create the file **ByteOrderTcpDemo.java** and save the code as UTF-8:

~~~java
import java.io.BufferedInputStream;
import java.io.BufferedOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.UncheckedIOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.HexFormat;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ByteOrderTcpDemo {
    private static void serve(ServerSocket listener) throws IOException {
        try (Socket peer = listener.accept();
             DataInputStream in = new DataInputStream(
                     new BufferedInputStream(peer.getInputStream()));
             DataOutputStream out = new DataOutputStream(
                     new BufferedOutputStream(peer.getOutputStream()))) {

            peer.setSoTimeout(3_000);

            // 4-byte header: always big-endian via DataInputStream.
            int length = in.readInt();
            if (length != Integer.BYTES) {
                throw new IOException("Invalid payload length: " + length);
            }

            // Do not assume TCP will return 4 bytes in a single read().
            byte[] payload = new byte[length];
            in.readFully(payload);

            // 4-byte payload: little-endian as agreed by the protocol.
            int value = ByteBuffer.wrap(payload)
                    .order(ByteOrder.LITTLE_ENDIAN)
                    .getInt();

            // Fixed 4-byte big-endian ACK.
            out.writeInt(value);
            out.flush();
        }
    }

    public static void main(String[] args) throws Exception {
        int number = 0x01020304;

        // Inspect bytes produced by DataOutputStream.writeInt().
        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(memory)) {
            out.writeInt(number);
        }
        System.out.println("DataOutputStream BE: "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(memory.toByteArray()));

        // Inspect bytes produced by little-endian ByteBuffer.
        ByteBuffer little = ByteBuffer.allocate(Integer.BYTES)
                .order(ByteOrder.LITTLE_ENDIAN);
        little.putInt(number);
        byte[] payload = little.array();
        System.out.println("ByteBuffer LE:       "
                + HexFormat.ofDelimiter(" ").withUpperCase()
                        .formatHex(payload));

        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getLoopbackAddress())) {

            ExecutorService workers = Executors.newSingleThreadExecutor();
            try {
                Future<?> serverTask = workers.submit(() -> {
                    try {
                        serve(listener);
                    } catch (IOException ex) {
                        throw new UncheckedIOException(ex);
                    }
                });

                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            InetAddress.getLoopbackAddress(),
                            listener.getLocalPort()), 2_000);
                    client.setSoTimeout(3_000);

                    try (DataOutputStream out = new DataOutputStream(
                                 new BufferedOutputStream(
                                         client.getOutputStream()));
                         DataInputStream in = new DataInputStream(
                                 new BufferedInputStream(
                                         client.getInputStream()))) {

                        // BIG_ENDIAN length prefix.
                        out.writeInt(payload.length);
                        // LITTLE_ENDIAN integer payload.
                        out.write(payload);
                        out.flush();

                        // BIG_ENDIAN ACK.
                        int ack = in.readInt();
                        System.out.printf("ACK BE:              0x%08X%n", ack);
                    }
                }

                // Receive worker exception if server processing fails.
                serverTask.get(5, TimeUnit.SECONDS);
            } finally {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ByteOrderTcpDemo.java
java ByteOrderTcpDemo
~~~

Stdout on a successful run:

~~~text
DataOutputStream BE: 01 02 03 04
ByteBuffer LE:       04 03 02 01
ACK BE:              0x01020304
~~~

**Tracing the execution flow:**

1. `DataOutputStream.writeInt(number)` produces bytes `01 02 03 04` in the memory stream. `ByteBuffer.order(LITTLE_ENDIAN).putInt(number)` produces `04 03 02 01` in the payload array.
2. `ServerSocket(0, ..., loopback)` picks an available port; the worker only serves one connection for a compact demo, not a production server.
3. The client calls `writeInt(payload.length)` to write header `00 00 00 04`, then `write(payload)` to write `04 03 02 01`; `flush()` pushes buffered data down to the output stream.
4. The server's `readInt()` reads `length=4`, checks validity, `readFully()` reads all 4 bytes, and little-endian `ByteBuffer` decodes `0x01020304`.
5. The server's `writeInt(value)` sends a big-endian ACK; the client's `readInt()` receives all 4 bytes and prints the hex value.
6. The sockets and streams are closed via `try-with-resources`. Read timeouts prevent the demo from hanging indefinitely if one side stops sending; `Future.get()` propagates worker errors to the main thread.

The server part does not print to the console, so the stdout order is deterministic. In environments restricted from opening loopback sockets, the program may fail to start, but that does not change the byte-order rules.

## 7. Signed, Unsigned Integers, and Byte Conversion

### 7.1. Java `byte` Is Signed

In Java, `byte` has the range `-128..127`; the binary byte value `0xFF`, when read into a `byte`, becomes `-1` at the language level, even though the 8 bits on the wire are still `11111111`.

~~~java
byte b = (byte) 0xFF;
System.out.println(b);                     // -1
System.out.println(Byte.toUnsignedInt(b)); // 255
System.out.println(b & 0xFF);              // 255
~~~

This is a standalone illustrative snippet on byte interpretation that can be placed in `main`. When manually assembling multiple bytes via bit shifting, you must mask each byte before shifting to avoid **sign extension**:

~~~java
// Big-endian illustration for byte[4].
int value = ((bytes[0] & 0xFF) << 24)
          | ((bytes[1] & 0xFF) << 16)
          | ((bytes[2] & 0xFF) << 8)
          |  (bytes[3] & 0xFF);
~~~

`bytes` is a `byte[]` variable with **at least 4 bytes**; the snippet does not check length itself. To reduce manual errors, prefer `readInt()` or `ByteBuffer.getInt()` when suitable for the protocol.

### 7.2. 32 Bits on the Wire Do Not Specify Signedness

`DataInputStream.readInt()` and `ByteBuffer.getInt()` return a **signed** `int` in two's complement representation. If the protocol defines a 32-bit field as **unsigned**, you can read the bit pattern as an `int` and convert it to `long`:

~~~java
int bits = 0xFFFFFFFF;                      // -1 as a signed int
long unsigned32 = Integer.toUnsignedLong(bits);
System.out.println(unsigned32);             // 4294967295
~~~

Byte order only determines byte positions, while **signedness** determines how the highest bit is interpreted. Therefore, both must be specified explicitly. `DataInputStream.readUnsignedShort()` reads 2 big-endian bytes and returns 0..65535, but there is no direct `readUnsignedInt()`; use `Integer.toUnsignedLong(in.readInt())` if you need the full unsigned 32-bit range.

When transmitting 64-bit integers, use `writeLong()/readLong()` or `putLong()/getLong()` with **8 bytes** and the same byte order. Avoid switching from 32 to 64 bits on one side without updating the protocol: the number of bytes consumed will be wrong, shifting all subsequent fields out of alignment.

### 7.3. Do Not Confuse Integers, Floats, and Character Strings

- The binary integer `123` in a 4-byte frame differs from the 3-byte ASCII/UTF-8 string `"123"`.
- `writeInt(123)` writes `00 00 00 7B`; `"123".getBytes(UTF_8)` writes `31 32 33`.
- Endianness affects the arrangement of **bytes in a multi-byte number**; charset is a different convention used to encode text. If a payload contains both numbers and text, you must separately define field length, endianness, and charset.

Do not use `new String(integerBytes)` to decode binary integers; likewise, do not use `Integer.parseInt(...)` on 4 bytes unless an agreed text format is in use.

## 8. Handling TCP Partial Reads, EOF, and Frame Limits

### 8.1. DataInputStream Reads Fully; ByteBuffer Requires Ensuring Enough Bytes Before getInt

With blocking streams:

~~~java
// Illustrates a server receiving a frame consisting of a 4-byte length + payload.
int length = in.readInt();        // 4 bytes big-endian
if (length < 0 || length > MAX_BYTES) {
    throw new IOException("Invalid frame length");
}
byte[] payload = new byte[length];
in.readFully(payload);            // reads full length or throws EOFException
~~~

This is an illustrative snippet requiring `in` to be a `DataInputStream` and `MAX_BYTES` to be configured as a positive value. Avoid `new byte[length]` before validating bounds: a peer could send a large or negative number, causing excessive allocation, `NegativeArraySizeException`, or out-of-memory errors. In the demo, because the payload consists of only one integer, checking `length == Integer.BYTES` is the tightest bound.

`readFully()` throws `EOFException` if the peer closes its sending side before enough bytes arrive. It may have already consumed **part of the payload** before failing; the application must not assume it can re-read the frame from the beginning on the same socket. If `SO_TIMEOUT` is set, a blocking read may throw `SocketTimeoutException`; that is a **different condition from EOF**, and the socket is not necessarily closed automatically. Retry/resume behavior must be based on parser state and the protocol.

With a `ByteBuffer` populated from NIO, only call `getInt()` when there are **at least 4 valid bytes** in the readable portion. When using `SocketChannel` in non-blocking mode, a single `read(buffer)` may return 0 or 1–3 bytes; you must accumulate all 4 bytes across multiple events before calling `flip()` and decoding. Do not busy-loop when `read() == 0`; use a readiness mechanism like `Selector` to avoid burning CPU.

### 8.2. An Endianness Bug Can Turn Length into a Dangerous Value

Suppose a valid big-endian wire header is `00 00 00 04`, meaning a 4-byte payload. If the receiver mistakenly uses little-endian, it will interpret that as `0x04000000` = **67,108,864 bytes**. A tiny header can be turned into an allocation request of tens of MiB or more.

Therefore, the parser must:

1. Read **all bytes of the header**.
2. Decode using the **byte order defined by the protocol**.
3. Check `0 <= length <= MAX_FRAME_SIZE` and any minimum/version conditions.
4. Only then allocate the buffer or proceed to receive the payload.
5. Enforce read timeouts, connection limits, and memory limits; handle malformed frames by closing or reporting errors clearly per the protocol.

Checking byte order, framing, and size limits form a shared set of responsibilities: a byte-order mistake in a header often has far more severe consequences than misreading a single business value.

## 9. Common Errors and Fixes

| Error | Consequence | Fix |
| --- | --- | --- |
| Sender writes little-endian, receiver uses `readInt()` | Byte-swapped value | Agree on BE or have receiver read via `ByteBuffer.order(LITTLE_ENDIAN)` |
| Using `ByteOrder.nativeOrder()` as an implicit wire format | Machine/architecture dependent | Explicitly choose `BIG_ENDIAN`/`LITTLE_ENDIAN` |
| Assuming TCP provides network byte order for payloads | Misdecoding or ambiguous protocol | Specify endianness explicitly for each field |
| Calling `in.read(bytes)` once then `getInt()` | May lack 4 bytes due to partial read | Use `readFully()` or a loop to read all required bytes |
| Calling `putInt()` then `getInt()` immediately without `flip()` | `BufferUnderflowException` | Call `flip()` before switching to read phase |
| Calling `ByteBuffer.array()` on a direct buffer | May throw `UnsupportedOperationException` | Call `flip()` and `get(byte[])`, or use a heap buffer appropriately |
| Confusing 32-bit unsigned with Java signed `int` | Values from `0x80000000` upward become negative | Interpret via `Integer.toUnsignedLong()` when needed |
| Manually shifting negative bytes without `& 0xFF` | Sign extension, wrong assembled number | Mask before shifting or use standard APIs |
| Reading length with wrong endianness without bounds checking | May allocate excessively large memory | Decode with the right endianness and validate bounds before allocation |
| Forgetting `flush()` with `BufferedOutputStream` | Peer may wait while frame sits in buffer | Flush at appropriate frame boundaries |
| Letting multiple threads write to the same socket unsynchronized | Frame headers/payloads may interleave | Use a single writer/queue or lock around the entire frame |
| Retrying from the start after mid-frame EOF/timeout | Parser may lose synchronization with the stream | Track bytes already read or close the connection per protocol |

## 10. Self-Check Practice Exercises

### Exercise A: Determining Byte Order from 4 Bytes

The wire bytes are `78 56 34 12`. Results:

- **Big-endian:** `0x78563412`.
- **Little-endian:** `0x12345678`.

If the receiver uses `DataInputStream.readInt()`, it always interprets them as big-endian. If it uses `ByteBuffer.wrap(bytes).order(LITTLE_ENDIAN).getInt()`, it interprets them as little-endian.

### Exercise B: Decoding 2 Unsigned Bytes

Wire bytes `FF FE`; the protocol specifies unsigned 16-bit big-endian. The value is `65534`. If you use `readShort()`, Java returns `-2`; if you use `readUnsignedShort()`, Java returns `65534`. Byte order **does not replace** signedness rules.

### Exercise C: Big-Endian Header, Little-Endian Payload

Given the wire sequence:

~~~text
00 00 00 04 | 78 56 34 12
  length 4   | int payload LE
~~~

`DataInputStream.readInt()` returns `length=4`. Reading the next 4 bytes and calling `ByteBuffer.order(LITTLE_ENDIAN).getInt()` returns `0x12345678`. If the payload is mistakenly decoded with `readInt()`, you get `0x78563412`.

### Exercise D: Reading an Integer from TCP in Multiple Chunks

The client sends four bytes `01 02 03 04`, and the server's first `read(bytes)` only receives `01 02`. There are not 4 bytes yet, so **you must not call `getInt()` on the 2-byte buffer**. Continue reading the remaining 2 bytes; or use `DataInputStream.readInt()`, which requires all 4 bytes before returning the number.

### Exercise E: Trying to Change the Wire Format in the Demo

Change the client's payload encoding to `ByteOrder.BIG_ENDIAN` while keeping the server at `LITTLE_ENDIAN`. They are no longer compatible: the server will interpret `0x04030201` and the ACK will differ from the original number. To fix this, change both sides to the same order or explicitly update the protocol to use BE for the payload.

## 11. Checklist When Designing Integer Formats Over TCP

- [ ] Does every numeric field have a specific width (**8/16/32/64 bits**) and clear signedness?
- [ ] Is the byte order of **each multi-byte field** explicitly defined, without relying on native order implicitly?
- [ ] Do both sides use the same `DataInputStream` (BE) or `ByteBuffer.order(...)` convention?
- [ ] Does the protocol have message boundaries; does the length header have a defined size, endianness, and maximum limit?
- [ ] Are all bytes always read using `readInt()/readFully()` or a stateful buffer parser, rather than assuming a single `read()` is enough?
- [ ] With `ByteBuffer`, are position/limit/flip/compact handled properly?
- [ ] Is length validated before allocation, and are EOF, timeout, and malformed frames distinguished?
- [ ] When using buffered output, is it flushed **after the frame** when fast response is needed?
- [ ] Are there tests with easily verifiable byte patterns like `0x01020304`, negative values, large unsigned values, partial reads, and endianness mismatches?
- [ ] If multiple tasks share a socket, is **the entire frame** serialized so bytes do not interleave?

**Remember:** TCP preserves byte order, while **the meaning of four bytes is defined by the protocol**. `DataInputStream`/`DataOutputStream` give you consistent big-endian integers; `ByteBuffer` lets you choose big-endian or little-endian explicitly. Combining endianness selection with framing, reading all required bytes, and length validation is the foundation for transmitting integers over TCP accurately and safely.