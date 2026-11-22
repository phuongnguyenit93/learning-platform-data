# Reading InputStream, Writing OutputStream, and Detecting the End of a TCP Stream

## Objectives

When working with `java.net.Socket`, the two sides communicate primarily through `InputStream` and `OutputStream`. Reading and writing may seem simple, but hard-to-find network bugs often stem from misunderstanding three things:

1. **TCP is an ordered byte stream**, not a queue of independent messages. The boundary of each `write()` call on the sender side does **not** become the boundary of each `read()` call on the receiver side.
2. **No data available yet** is different from **end of stream**. A `read()` call may have to wait; receiving `-1` means the sender has ended that direction of transmission in a way observable by the input stream, after any remaining data in the stream has been read.
3. **End of stream** is different from **end of a message**. An application needs data framing rules (*framing*): length prefix, delimiter character, or using EOF if each connection carries only a single message.

This lesson progresses from the exact behavior of `read`/`write` to closing sockets, half-close with `shutdownOutput()`, timeouts, and Java 17+ examples running over loopback on a single machine.

## 1. A Socket Provides Two Independent Byte Transmission Directions

After the client calls `Socket.connect(...)` and the server's `ServerSocket.accept()` succeeds, each connected `Socket` has:

- `socket.getInputStream()`: reads **bytes sent by the other side**.
- `socket.getOutputStream()`: writes **bytes you want to send to the other side**.

On the client side, writing to the client's output causes bytes to arrive at the server's input; the reverse is also true. This is **full-duplex** communication: both sides can send and receive simultaneously.

```text
Client socket                              Server socket
┌──────────────────┐                      ┌──────────────────┐
│ OutputStream     │ ───── byte ────────► │ InputStream      │
│ InputStream      │ ◄───── byte ──────── │ OutputStream     │
└──────────────────┘                      └──────────────────┘

TCP preserves byte order in each direction.
Both directions can end independently (half-close).
There are no automatic message delimiters between write() calls.
```

A connected socket has local and remote addresses/ports; a server can accept multiple connected sockets on the same listening port. `ServerSocket` is used to wait for new connections, whereas the two read/write streams of `Socket` are used to exchange data **on an already accepted connection**.

These streams work with **bytes**. If the content is text, you must agree on an encoding (usually UTF-8), how to split messages, and how to signal when a message is complete.

## 2. `InputStream.read()`: The Return Value Is the Evidence

### 2.1. Reading One Byte at a Time

```java
InputStream in = socket.getInputStream();
int value = in.read();
```

`read()` returns an `int`:

| Result | Meaning |
|---|---|
| `0` to `255` | Read **one byte**; `0` is a valid data byte, not EOF |
| `-1` | **End-of-stream (EOF)**: no more bytes to read in this stream |
| Throws `IOException` | An I/O error occurred; could be connection reset, closed socket, or network error |
| Has not returned yet | `read()` is waiting for a byte/EOF/error; does not mean data has ended |

Do not cast the result of `read()` to `byte` before checking for `-1`, because `byte` in Java is signed (`-128`..`127`) and doing so can make it impossible to distinguish EOF from a data value.

In-memory example, runnable standalone with deterministic output:

**File `ReadByteValues.java`**

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;

public class ReadByteValues {
    public static void main(String[] args) throws Exception {
        byte[] data = {(byte) 0xFF, 0x00};
        try (InputStream in = new ByteArrayInputStream(data)) {
            System.out.println(in.read());
            System.out.println(in.read());
            System.out.println(in.read());
        }
    }
}
```

```bash
javac -encoding UTF-8 ReadByteValues.java
java ReadByteValues
```

```text
255
0
-1
```

`0xFF` is a byte with unsigned value 255, so `read()` returns 255; byte `0x00` returns 0; **only the third call** returns `-1`. This illustrates the rules of `InputStream`; there is no TCP connection in this example.

### 2.2. Reading into a Buffer

```java
byte[] buffer = new byte[4096];
int n = in.read(buffer);
if (n == -1) {
    // EOF received.
} else {
    // Only bytes buffer[0..n-1] are data from this read.
}
```

When the buffer has a positive length, `read(buffer)` will normally wait until at least one byte, EOF, or an error occurs; a successful call can return **any number of bytes from 1 to `buffer.length`**. For a read request of length 0, the API may return `0` without reading any bytes; do not treat that special case as a network message.

**Do not assume** that if the client calls `write(bytes)` with 4,096 bytes, the server will receive all 4,096 bytes in a single `read(buffer)` call. The operating system, send scheduling, TCP, buffers, and read timing may split or coalesce data; TCP only guarantees byte ordering and reliable delivery while the connection succeeds.

The correct way to accumulate data when **the protocol specifies that EOF is the end of the message**:

```java
// Illustrative snippet inside a method that already has InputStream in.
byte[] buffer = new byte[4096];
int n;
while ((n = in.read(buffer)) != -1) {
    consume(buffer, 0, n); // consume is a method the application must define itself.
}
```

The snippet above only illustrates the loop; it is **not a standalone program** because `consume(...)` is an application method. Use `ByteArrayOutputStream`, streaming processing, or a parser depending on your needs; for data from the network, you must enforce a reasonable size limit instead of accumulating indefinitely.

### 2.3. Incorrect Ways to Read

- **Wrong:** `if (in.read(buffer) < buffer.length)` means the message is finished. A read that returns fewer bytes than the buffer size only means that specific read returned fewer bytes than its capacity.
- **Wrong:** `if (in.available() == 0)` means EOF. `available()` is an estimate of the number of bytes that can be read immediately without blocking; `0` can still mean the connection is waiting for future data.
- **Wrong:** `if (socket.isConnected())` means the peer is still online. `isConnected()` reflects the socket's connection state history, not a real-time liveness check.
- **Wrong:** reading just once will receive the entire request. TCP can deliver a message in multiple chunks; you must use framing.
- **Wrong:** treating `SocketTimeoutException` as EOF. A timeout means **waiting too long**, not a signal that the sender has closed its output direction.

## 3. `OutputStream.write()`: Sending Bytes, Not "Framed Messages"

Commonly used overloads:

```java
OutputStream out = socket.getOutputStream();
out.write(65);                     // One byte: ASCII value for A.
out.write(new byte[] {66, 67});    // Two bytes: B, C.
out.flush();
```

On the reading side, TCP might deliver `ABC` in a single `read` or split it into chunks. Whether `write` is called three times or once does not create message boundaries visible to the receiver.

**What `write()` returning means:** the bytes have been handed off to Java's output layer and the I/O system; it **does not prove** that the other side has received, read, validated, or processed them at the application level. Writing to a socket can block due to buffer limits/flow control; an abrupt close error by the peer sometimes only surfaces on a subsequent write or read.

### 3.1. When Is `flush()` Needed?

There are two layers that are often confused:

- `Socket.getOutputStream()` returns the stream sending to the socket; it does not create a Java `BufferedOutputStream` by default. Calling `flush()` on the raw stream does not create a message-end marker.
- If you wrap it in `BufferedOutputStream` or `BufferedWriter`, data may sit in **the Java-side buffer**. You must call `flush()` at the point where the protocol requires the peer to start processing; if you wait for the buffer to fill or close while waiting for a response, the program may hang.

`flush()` pushes data held in Java's buffer down to the underlying stream; **it does not mean TCP has been ACKed by the peer or that the other application has finished reading**. It also **does not send EOF**, does not close the connection, and does not automatically add a newline or length prefix.

Example when both sides agree that messages end with a newline:

```java
BufferedWriter writer = new BufferedWriter(
        new OutputStreamWriter(socket.getOutputStream(),
                java.nio.charset.StandardCharsets.UTF_8));

writer.write("PING");
writer.newLine(); // Newline character belonging to the example's text protocol.
writer.flush();   // Flush data from BufferedWriter to the socket.
```

This is an **illustrative snippet**, assuming the `socket` variable is already connected. The receiving side can use `BufferedReader.readLine()`. Do not use `newLine()` for binary protocols or protocols that do not define this delimiter.

### 3.2. Beware of "Closing the Writer to Finish Sending the Request"

`BufferedWriter.close()` closes the writer and the underlying stream. For a stream obtained from `Socket`, closing the stream **closes the socket**, making the response-reading direction unusable in the normal way. If you only want to signal "the client has finished sending the request" while **still wanting to read the response on the same TCP connection**, use appropriate framing or `socket.shutdownOutput()`—do not close the entire socket prematurely.

`PrintWriter` also has the characteristic of **not throwing `IOException` directly** on certain write operations; you must call `checkError()` if using it. For network debugging examples, `OutputStream`/`BufferedWriter` generally make I/O errors easier to observe.

## 4. EOF in TCP: From FIN and Half-Close to Reset

### 4.1. Normal Output-Direction Closure

On a TCP connection, side A can announce that A **will not send any more bytes** by ending its output direction. In TCP, normal end-of-send is typically signaled by **FIN**. Side B still reads the bytes that arrived before the FIN, after which `InputStream.read()` returns `-1`.

```text
Client                                 Server
  │  write("HELLO")                      │
  │ ───────────────────────────────────►│  read(...) receives bytes
  │  shutdownOutput()                    │
  │ ─────────────── FIN ────────────────►│  read(...) -> -1 after all bytes
  │                                     │  write("ACK")
  │ ◄───────────────────────────────────│
  │  read(...) receives "ACK"            │
  │  read(...) -> -1 when server closes  │
  └─────────────────────────────────────┘
```

**Half-close** means one direction has ended while the other direction can still transmit. In Java:

- `socket.shutdownOutput()`: ends the **sending** direction of the socket; bytes written earlier precede the end signal. After this operation, continuing to write to the output stream will cause an I/O error.
- `socket.shutdownInput()`: ends the **local receiving direction**, placing the socket's input stream at EOF; any subsequently received data may be discarded. This is **not** a way to inform the peer that you have finished sending.
- `socket.close()`: closes the socket; not the appropriate tool if you still need to read a response. Closing a socket normally terminates use of both input and output.
- `Socket.shutdownOutput()` must not be interpreted as "ending an HTTP request" in HTTP keep-alive; HTTP has its own framing rules. Do not use half-close after every message on a connection intended to be reused.

### 4.2. `-1`, Reset Errors, and Timeouts Are Three Different Signals

| Situation | Observable Result in Java | How to Interpret |
|---|---|---|
| Peer sent some bytes but has not ended its sending direction | `read` returns available bytes, then subsequent reads may block | Not EOF yet |
| Peer sent a normal FIN; all bytes before FIN have been read | `read` returns `-1` | End of input stream |
| Peer or network aborted the connection, e.g., TCP RST | `read`/`write` may throw `SocketException` or `IOException` | Connection error; must not be equated with a clean EOF |
| Waited too long after setting `setSoTimeout` | `SocketTimeoutException` | No byte/EOF arrived within the timeout; does not by itself confirm the peer closed |
| We closed our own socket | Reading/writing on the closed stream may cause `SocketException` | Local action, not a normal remote EOF |

Do not infer that all forms of network loss will promptly produce `-1`. A "silent" physical link loss can cause `read` to keep blocking for a long time without an appropriate timeout/protocol timeout. TCP keepalive (if enabled and supported by the OS) is a mechanism to detect certain dead peers at the TCP layer; it does **not** provide message boundaries and is not a substitute for application timeouts/heartbeats.

### 4.3. What Does "End of a Message" Mean?

There are at least three different questions:

- **Is there no more data available right now?** Does not mean the message is finished. `available()==0` cannot answer this.
- **Is the message finished according to the protocol?** Known via a delimiter, length prefix, fixed size, or protocol parser.
- **Has the peer completely ended its TCP sending direction?** Read until `-1`. This **can** be used as the end-of-message marker if the protocol specifies that each direction sends one payload and then terminates; it is unsuitable for connections with multiple sequential messages.

## 5. Java 17+: Demonstrating `shutdownOutput()` and EOF with a Runnable Program

This program opens a server on loopback at an ephemeral port chosen by the OS, runs the server part in a separate thread, and runs the client part on the main thread. The client writes two byte chunks `HEL` and `LO` and then calls `shutdownOutput()`. The server **does not assume boundaries between the two write calls**, reads until EOF, and then returns `ACK` to the client.

Create the file **`SocketHalfCloseDemo.java`**:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketHalfCloseDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(3000);

            Future<String> serverResult = executor.submit(() -> {
                try (Socket accepted = server.accept()) {
                    accepted.setSoTimeout(3000);
                    InputStream input = accepted.getInputStream();
                    ByteArrayOutputStream body = new ByteArrayOutputStream();
                    byte[] buffer = new byte[3];
                    int count;

                    while ((count = input.read(buffer)) != -1) {
                        if (body.size() + count > 1024) {
                            throw new IOException("Request too large");
                        }
                        body.write(buffer, 0, count);
                    }

                    OutputStream output = accepted.getOutputStream();
                    output.write("ACK".getBytes(StandardCharsets.UTF_8));
                    output.flush();
                    return body.toString(StandardCharsets.UTF_8);
                }
            });

            try (Socket client = new Socket()) {
                client.connect(
                        new InetSocketAddress(loopback, server.getLocalPort()),
                        3000);
                client.setSoTimeout(3000);

                OutputStream output = client.getOutputStream();
                output.write("HEL".getBytes(StandardCharsets.UTF_8));
                output.write("LO".getBytes(StandardCharsets.UTF_8));
                output.flush();
                client.shutdownOutput();

                InputStream input = client.getInputStream();
                ByteArrayOutputStream reply = new ByteArrayOutputStream();
                int value;
                while ((value = input.read()) != -1) {
                    reply.write(value);
                }

                System.out.println("Client response: "
                        + reply.toString(StandardCharsets.UTF_8));
            }

            System.out.println("Server request: "
                    + serverResult.get(4, TimeUnit.SECONDS));
        } finally {
            executor.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac -encoding UTF-8 SocketHalfCloseDemo.java
java SocketHalfCloseDemo
```

Under normal loopback socket operation, stdout **in the exact order printed by the main thread** is:

```text
Client response: ACK
Server request: HELLO
```

Explanation:

1. `server.bind(..., 0)` lets the OS assign a port; therefore, there is no need to guess a fixed port and no need for two terminals.
2. The server calls `read(buffer)` repeatedly until `-1`. The buffer is only 3 bytes to remind you that a 5-byte message is not guaranteed to be received in a single read. The number of iterations and bytes per read are non-deterministic details.
3. The client's two `write()` calls do not create two messages. The entire payload is reassembled in order into `HELLO`.
4. `client.shutdownOutput()` allows the server to observe EOF **without closing the client's receiving direction**. The server can still return `ACK`.
5. After the server writes the reply and closes the accepted socket upon exiting the `try` block, the client finishes reading the reply and receives EOF on the server's output direction.
6. `setSoTimeout(3000)` prevents read operations from hanging indefinitely in the example. If the environment is constrained or runs too slowly, the program may throw an exception; that is an error during the experiment run rather than a standard stdout line.
7. The 1,024-byte limit on the request illustrates that a server should not read payloads from untrusted clients into unbounded memory.

**Important:** the example uses **EOF as the end-of-request marker**, so each client sends only one request and then half-closes. This is an intentional demo protocol. For chat, RPC, HTTP keep-alive, or multiple messages on the same connection, you must use a different framing mechanism.

## 6. Distinguishing Message Boundaries from EOF Using Framing

Three common strategies:

| Framing | Message Completion Signal | When Suitable | Risks to Handle |
|---|---|---|---|
| **EOF-based** | Peer ends sending direction and `read() == -1` | A single request per transmission direction, followed by a response | Cannot reuse the sending direction; easy to deadlock if both sides wait on each other |
| **Line-delimited** | `\n`, `\r\n`, or a protocol-defined delimiter | Simple text commands: `PING\n`, `QUIT\n` | Payloads containing the delimiter need escaping; length limits; encoding |
| **Length-prefixed** | Read a header containing the size, then read the exact number of payload bytes | Binary/multi-record messages on one TCP connection | Byte order, malicious lengths, short reads, overflow, and memory limits |
| **Standard protocol parser** | Rules defined by HTTP, WebSocket, TLS, or another protocol | Real-world systems using standard protocols | Must use a proper parser/library; do not treat TCP packets as messages |

Do not decode individual `byte[]` chunks into `String` when each read may not contain complete UTF-8 characters: a single character can span across two reads. Use `InputStreamReader` or a streaming decoder, or accumulate **one complete framed message** before decoding.

### 6.1. Why Doesn't `readLine()` Always Need EOF?

`BufferedReader.readLine()` reads until a line terminator (or EOF), stripping the line terminator from the returned string. For a newline-delimited protocol:

- `readLine()` returns `"PING"` when receiving `PING\n`; it does not need the client to close the connection.
- `readLine()` returns `""` for a **blank line**; this is not EOF.
- `readLine()` returns **`null`** when EOF is reached with **no remaining characters** to return. If EOF arrives after a piece of text without a trailing newline, the method may return that text first, and only return `null` on the next call.
- If the client writes `"PING"` without sending a newline and without closing output while the server is waiting on `readLine()`, the server may keep waiting. `flush()` alone does not append a newline.

This is why you must explicitly document the **delimiter contract** in the protocol and enforce a line-length limit; `BufferedReader.readLine()` does not automatically enforce a maximum size on a line sent by a peer.

## 7. Java 17+: Multiple Messages on the Same Connection Using Newlines

The next standalone example sends two lines—`alpha` and an empty line—and receives a response `ACK 2` **before the client closes the socket**. It demonstrates how the application knows both messages are complete without waiting for EOF.

Create the file **`SocketLineMessages.java`**:

```java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketLineMessages {
    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(3000);

            Future<String[]> messages = executor.submit(() -> {
                try (Socket socket = server.accept()) {
                    socket.setSoTimeout(3000);
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(socket.getInputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedWriter writer = new BufferedWriter(
                            new OutputStreamWriter(socket.getOutputStream(),
                                    StandardCharsets.UTF_8));

                    String first = reader.readLine();
                    String second = reader.readLine();
                    writer.write("ACK 2");
                    writer.newLine();
                    writer.flush();
                    return new String[] {first, second};
                }
            });

            try (Socket socket = new Socket()) {
                socket.connect(
                        new InetSocketAddress(loopback, server.getLocalPort()),
                        3000);
                socket.setSoTimeout(3000);

                BufferedWriter writer = new BufferedWriter(
                        new OutputStreamWriter(socket.getOutputStream(),
                                StandardCharsets.UTF_8));
                BufferedReader reader = new BufferedReader(
                        new InputStreamReader(socket.getInputStream(),
                                StandardCharsets.UTF_8));

                writer.write("alpha");
                writer.newLine();
                writer.newLine(); // An empty line is the second message.
                writer.flush();

                System.out.println("Client response: " + reader.readLine());
            }

            String[] result = messages.get(4, TimeUnit.SECONDS);
            System.out.println("Server first: " + result[0]);
            System.out.println("Server second empty: " + result[1].isEmpty());
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 SocketLineMessages.java
java SocketLineMessages
```

Stdout on a successful run:

```text
Client response: ACK 2
Server first: alpha
Server second empty: true
```

Explanation:

- `writer.newLine()` adds the delimiter; `flush()` moves data from the Java buffer down to the socket's output.
- The server reads **two lines** without waiting for EOF. The second line `""` is still a valid message under the assumed protocol.
- The server responds and then closes the socket after returning; the client has already received `ACK 2` and does not need to call `shutdownOutput()`.
- The server cannot distinguish individual TCP `read` calls and does not need to. `BufferedReader` handles buffering and UTF-8 decoding, while **line-based formatting** is the application rule.
- The demo assumes a fixed number of lines and small messages. A real server must limit length, handle newlines inside payloads, unexpected EOF, timeouts, multiple clients, and protocol errors.

**Protocol note:** `newLine()` depends on the platform (for example, LF on many Unix systems, CRLF on Windows), whereas `readLine()` understands common line-ending styles. When designing a protocol that requires a fixed delimiter byte across all platforms, **specify the delimiter explicitly** (for example, always `\n` via `writer.write('\n')`) and avoid relying on the OS default line separator.

## 8. Java 17+: Reading Exact Payloads with a Length Prefix

For binary data or text that may contain newlines, a common approach is to place a **4-byte big-endian integer** before the UTF-8 payload. The reader extracts the length, validates limits, and then reads **that exact number of bytes**. Below, `DataOutputStream.writeInt` and `DataInputStream.readInt` are used, which standardize integer byte order.

Create the file **`SocketLengthFrames.java`**:

```java
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class SocketLengthFrames {
    private static final int MAX_BYTES = 4096;

    private static void sendFrame(DataOutputStream output, String text)
            throws IOException {
        byte[] payload = text.getBytes(StandardCharsets.UTF_8);
        if (payload.length > MAX_BYTES) {
            throw new IOException("Payload too large");
        }
        output.writeInt(payload.length);
        output.write(payload);
    }

    private static String readFrame(DataInputStream input) throws IOException {
        int length = input.readInt();
        if (length < 0 || length > MAX_BYTES) {
            throw new IOException("Invalid frame length: " + length);
        }
        byte[] payload = new byte[length];
        input.readFully(payload); // Read exactly length bytes or throw EOFException.
        return new String(payload, StandardCharsets.UTF_8);
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket()) {
            InetAddress loopback = InetAddress.getLoopbackAddress();
            server.bind(new InetSocketAddress(loopback, 0));
            server.setSoTimeout(3000);

            Future<String[]> messages = executor.submit(() -> {
                try (Socket socket = server.accept()) {
                    socket.setSoTimeout(3000);
                    DataInputStream input =
                            new DataInputStream(socket.getInputStream());
                    DataOutputStream output =
                            new DataOutputStream(socket.getOutputStream());

                    String first = readFrame(input);
                    String second = readFrame(input);
                    sendFrame(output, "ACK");
                    output.flush();
                    return new String[] {first, second};
                }
            });

            try (Socket socket = new Socket()) {
                socket.connect(
                        new InetSocketAddress(loopback, server.getLocalPort()),
                        3000);
                socket.setSoTimeout(3000);
                DataInputStream input =
                        new DataInputStream(socket.getInputStream());
                DataOutputStream output =
                        new DataOutputStream(socket.getOutputStream());

                sendFrame(output, "HELLO");
                sendFrame(output, "JAVA");
                output.flush();
                System.out.println("Client response: " + readFrame(input));
            }

            String[] result = messages.get(4, TimeUnit.SECONDS);
            System.out.println("Server first: " + result[0]);
            System.out.println("Server second: " + result[1]);
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac -encoding UTF-8 SocketLengthFrames.java
java SocketLengthFrames
```

Stdout when TCP loopback operates normally:

```text
Client response: ACK
Server first: HELLO
Server second: JAVA
```

**Why doesn't this program wait for EOF between the two messages?** The server's `readFrame` reads the `4-byte header`, then uses `readFully` to read the exact number of payload bytes. Once the first frame is complete, the following bytes belong to the second frame, regardless of whether TCP delivers the data in 1 read or multiple reads. To send the response, the server only needs to finish reading **two frames per the demo contract**, without waiting for the client to close its output.

Key points to remember:

1. Length in the example is measured by `payload.length` (**number of UTF-8 bytes**), not `String.length()` (number of UTF-16 code units). For example, accented characters may require multiple UTF-8 bytes.
2. `DataInputStream.readFully(payload)` attempts to read the full size; if the peer ends the stream before enough bytes arrive, it throws `EOFException`. `readInt()` can also throw `EOFException` if fewer than 4 header bytes are received.
3. A real protocol must specify **byte order**, header size, encoding type, maximum length, versioning, and how to handle malformed frames. Outside Java, servers/clients must use this exact 4-byte big-endian format; do not infer it from the `DataInputStream` class name.
4. `MAX_BYTES` prevents untrusted senders from forcing the server to allocate excessive memory. Beyond per-frame limits, real systems also need limits on total time, frame count, rate, and resources.
5. `DataInputStream.readUTF()/writeUTF()` use **Java's modified UTF-8** format and their own length prefix; do not blindly substitute them for standard UTF-8 protocols using `getBytes(StandardCharsets.UTF_8)`.
6. If a peer opens a connection, sends the header, and then stops, `readFully` will wait; `setSoTimeout` helps break out of a hung read, though that is a **timeout**, not a successful EOF.

## 9. Reading Until EOF vs. Reading a Complete Message: Choosing the Right Contract

### 9.1. APIs That Can Hang If the Peer Does Not Close

- `InputStream.readAllBytes()`: reads until EOF and returns a byte array. Useful for files or a stream **guaranteed to end**. For a TCP connection kept open for reuse, calling it can wait forever, and also cause memory issues if the data is large.
- `InputStream.transferTo(output)`: transfers continuously until EOF. Does not automatically detect the end of an HTTP/WebSocket message, and should not be used indefinitely without a lifecycle.
- `InputStream.readNBytes(n)`: attempts to read up to `n` bytes, but may return fewer if EOF is reached. You must check the returned length if the protocol requires **exactly `n` bytes**.
- `DataInputStream.readFully(bytes)`: reads the exact requested length or throws `EOFException` on premature EOF; can still block/timeout if the peer keeps the connection open without sending enough bytes.
- `BufferedReader.readLine()`: waits for a delimiter or EOF. If the protocol has no newline and the peer does not close its output, the call can wait.

### 9.2. A Common Deadlock Example

A flawed design where **both sides wait for each other**:

```text
Client: write("REQUEST") -> read response (waits)
Server: readAllBytes() -> build response (waits for EOF)
```

The client has not sent EOF because it still wants to reuse its output; the server has not built a response because `readAllBytes()` has not seen EOF yet. Result: **both sides wait**, not because the network "swallowed" bytes. There are three fixes depending on the protocol:

1. Single request: client writes payload, `flush()`, and `shutdownOutput()`; server reads until EOF and then returns the response.
2. Line-based: client writes `REQUEST\n` and `flush()`; server calls `readLine()` and processes it, and can continue receiving more lines.
3. Length-prefixed: client writes length + payload; server reads the exact length and processes it without waiting for EOF.

Do not use `sleep()` or increase buffer sizes to "fix" a protocol deadlock. The problem lies in **missing message-termination rules**.

## 10. Timeouts, Resource Closing, and Error Handling

### 10.1. Timeouts Must Be Applied by Operation Type

```java
// Illustrative example inside a method that already has Socket socket.
socket.connect(remoteEndpoint, 3000);
socket.setSoTimeout(5000);
```

`remoteEndpoint` must be a valid `SocketAddress` provided externally; this is an **illustrative snippet**, not a standalone program.

- The timeout parameter of `connect(endpoint, milliseconds)` applies when attempting to establish the **TCP connection**. It does not automatically set a timeout for subsequent reads.
- `setSoTimeout(milliseconds)` applies to **read** operations on the socket's input according to `SO_TIMEOUT` semantics. After the wait duration, `SocketTimeoutException` may be thrown; the socket generally remains usable, though the application must decide whether to retry or close.
- `setSoTimeout(0)` means an **infinite** read timeout. Do not let data from untrusted peers hold a thread indefinitely without a proper timeout policy.
- Connect/read timeouts do not replace **total request time** limits, size limits, and task cancellation mechanisms. `OutputStream.write` can also block due to backpressure; do not assume `setSoTimeout` limits write duration.

### 10.2. Closing the Right Object That Owns the Socket

```java
try (Socket socket = new Socket()) {
    // Connect and use input/output within this scope.
}
// The socket is closed automatically, even if an exception occurs.
```

For streams obtained from a socket, closing `InputStream` or `OutputStream` **also closes the corresponding socket** per the Java `Socket` contract. When one direction has finished sending but you still need to read a reply, use `shutdownOutput()` or application framing. Do not close individual streams prematurely.

If designing wrappers like `BufferedReader`, `BufferedWriter`, `DataInputStream`, or `DataOutputStream`, clearly define **who owns closing the socket**. Once all operations are complete, `try-with-resources` on the socket is the simplest and most reliable approach for small examples.

**Distinguishing states:**

| State | Common Symptom | Action |
|---|---|---|
| Peer sent normal EOF | `read == -1` or `readLine == null` when no characters remain | Exit loop, verify complete message |
| Read timed out | `SocketTimeoutException` | Log timeout clearly; retry/close per protocol |
| Connection reset | `SocketException` or specific I/O error | Do not treat as a successful response |
| Fewer bytes than length prefix | `EOFException` from `readFully` | Reject incomplete frame |
| Client sent payload exceeding limit | App checks size and throws protocol error | Close or reject per policy |
| Writing after `shutdownOutput()` | `IOException`/`SocketException` | Do not write further; open another connection if needed |

**Do not rely on `Socket.isClosed()` to check whether the peer has closed.** It indicates whether the local Java socket has been closed, not a mechanism for detecting remote EOF. Similarly, `isInputShutdown()`/`isOutputShutdown()` reflect local shutdown calls, not a substitute for reading and parsing the protocol.

### 10.3. Data Control Responsibilities

Any code reading from an untrusted peer should have:

- **Appropriate limits on message size**, frame size, read count, requests/connection, or total bytes.
- **Time limits** on connect, read, and processing; prevent a client from holding a connection open forever without sending a complete message.
- **Clear protocol rules** for encoding, delimiter/length, request-response ordering, and when half-close/close is permitted.
- **Separated error handling**: normal EOF, premature EOF, timeout, reset, parse failure, and business errors should not be lumped together as "no network".
- **Ensure all bytes are handled** when writing a custom protocol. With a standard `OutputStream`, a single `write(byte[])` writes the array per the API contract; the receiver **still** needs a framed read loop and must not rely on a single read.
- **Do not infer delivery from `flush()`**. To know a request was processed, the protocol needs a response or acknowledgement at the appropriate layer.

## 11. Comprehension Check Scenarios

**Scenario A — Byte `0` and EOF:** the client sends bytes `0x41 0x00 0x42`. `InputStream.read()` on the server side may return 65, 0, 66 in turn, and only return `-1` **after the sender ends its output direction** and the server finishes reading all data. Never treat `0` as EOF.

**Scenario B — Reading less than the buffer:** the client `write`s 1,000 bytes; the server allocates a 4,096-byte buffer and the first read receives 400 bytes. Is the message finished? **Cannot conclude yet.** At least 600 more bytes from that write may arrive later, and the protocol may have additional messages.

**Scenario C — Timeout:** server `read()` waits 5 seconds and throws `SocketTimeoutException`. Did the client send a FIN? **No.** That only means waiting too long; a clean EOF is represented by `-1`.

**Scenario D — Client still wants to read response:** the client writes a payload whose protocol defines termination by EOF; the server only processes it upon seeing EOF. What should the client do after `flush()`? **Call `shutdownOutput()`**, keeping the input direction open to receive the reply; do not `close()` the entire socket before reading the reply.

**Scenario E — Multiple messages:** the client sends `"A"` and then `"B"` in two `write` calls; the server reads once and receives `"AB"`. Is this a TCP bug? **No.** TCP can coalesce data across reads; a delimiter or length prefix is needed to distinguish the two messages.

**Scenario F — What does `readLine()` return?** Given `"HELLO\n\n"`, the first two `readLine()` calls return `"HELLO"` and `""`; if the peer then closes its sending direction, the next call returns `null`. **An empty line is not EOF.**

**Scenario G — Header is 10, but peer sends only 6 bytes and then FIN:** should `DataInputStream.readFully(new byte[10])` read what is there or report `EOFException`? It throws **`EOFException`**, because the frame is incomplete. Do not process 6 bytes as a valid message if the protocol requires 10.

**Scenario H — Can a reply be received after `shutdownOutput()`?** Yes. Half-close only ends the **sending direction** of the socket; the receiving direction remains usable until the peer ends it or an error occurs.

## 12. Practical Summary

- `Socket.getInputStream()` reads bytes from the peer; `Socket.getOutputStream()` writes bytes to the peer. TCP guarantees **byte order**, with no message boundaries created by `write()` calls.
- `read() == -1` is **EOF**, while `read() == 0` can be a data byte of value 0 (with the single-byte read overload). Waiting, timeouts, and resets are **not synonymous** with EOF.
- `flush()` pushes the Java buffer down to the stream; it is not an end-of-message marker, nor an application-layer peer ACK.
- `shutdownOutput()` ends the sending direction while still allowing responses to be read; `close()` terminates use of the socket. Do not close the output stream prematurely when you still need to receive a reply.
- When **EOF is the delimiter**, read until `-1`; when there are **multiple messages on one connection**, use newlines, length prefixes, or a standard parser; always include timeouts, size limits, and error-handling rules.
- To debug a "hung" connection, ask: **is the reader waiting for bytes, a delimiter, remaining bytes, or EOF? Has the sender called `flush()` and actually emitted the corresponding termination signal?**

### Java 17 Reference Documentation

- [`InputStream`: `read`, `readNBytes`, `readAllBytes`, `transferTo`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html)
- [`OutputStream`: `write`, `flush`, `close`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html)
- [`Socket`: `getInputStream`, `getOutputStream`, `shutdownInput`, `shutdownOutput`, `setSoTimeout`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html)
- [`BufferedReader` and `BufferedWriter`: `readLine`, `newLine`, `flush`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [`DataInputStream` and `DataOutputStream`: `readFully`, `readInt`, `writeInt`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
