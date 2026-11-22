# The last Flag and How a WebSocket Message Is Delivered Across Multiple Invocations

In Java 17+, the `java.net.http` WebSocket client provides the callbacks `WebSocket.Listener.onText(WebSocket, CharSequence, boolean last)` and `onBinary(WebSocket, ByteBuffer, boolean last)`. A **logical WebSocket message** may be received in **one or more invocations** of these callbacks. The `last` parameter indicates **whether the current invocation carries the final part of the message**.

- **`last=false`:** the data just received is only a part of the message. More parts are coming; do not prematurely parse/commit/ACK it as a complete message.
- **`last=true`:** the part received in this invocation completes the logical message. After appending that part to the buffer, the application can process the complete message and then reset the assembler for the next message.
- **One message does not mean one callback, one TCP read, or one WebSocket frame.** Do not write programs based on an assumed callback count.
- **The `last` flag on the sending side** is also present in `sendText(data,last)` and `sendBinary(data,last)`: false means more parts of the **same message** will follow, true ends that message.
- **`webSocket.request(n)` counts receive callback invocations**, not bytes, frames, or messages. If you only call `request(1)` and the first received part has `last=false`, you must continue granting receive demand according to policy to get the remaining parts.

This lesson accurately analyzes message boundaries, the callback and CompletionStage threading mechanism, how to assemble text/binary with proper ownership, memory limits, closing connections, sending subsequent parts in order, and includes **a runnable Java 17+ program** over WebSocket loopback to demonstrate both fragmented text and binary. The content does not depend on any specific Internet server.

## 1. Separating TCP, WebSocket Frames, and WebSocket Messages

WebSocket (RFC 6455) runs over a TCP connection after an HTTP Upgrade or an appropriate WebSocket opening mechanism. TCP is a **byte stream** and does not preserve the boundaries of a peer's single write. WebSocket has **frames** with an opcode, a FIN bit, and a payload. A text or binary message may consist of multiple frames; on the Java Listener side, data is received as a sequence of **callbacks** that are not guaranteed to correspond one-to-one with frames.

~~~text
Logical message: "Hello Java"
           |
           v
WebSocket frame A: TEXT, FIN=0, payload="Hello "
WebSocket frame B: CONTINUATION, FIN=1, payload="Java"
           |
           v
      TCP byte stream
      (may be split/coalesced across reads)
           |
           v
WebSocket client in the JDK
           |
           v
Listener.onText(socket, data, last)
   - one or more callbacks depending on the implementation
   - last=false: message has not ended
   - last=true : final part just received
           |
           v
Complete message: "Hello Java"
~~~

The diagram illustrates a specific pair of frames. **Do not claim that two frames always produce exactly two `onText` calls.** Regardless of how callbacks are split, whichever segment has `last=true` is the end boundary of the message.

| Boundary | Handled by | Is it an application message boundary? |
| --- | --- | --- |
| TCP packet / `SocketChannel.read()` | TCP/transport | No, just bytes |
| WebSocket frame FIN and continuation | WebSocket protocol implementation | Indicates the end of a fragment/frame sequence, but not the callback count |
| `onText/onBinary(data,last)` | Java WebSocket.Listener | `last=true` is the final part of **one WebSocket message** |
| JSON/object/business event | Self-defined application protocol | Can be one WebSocket message if agreed upon as such |

Do not turn a single callback into an HTTP request or a JSON object without a valid boundary. A WebSocket message may be a business command, a binary payload, or part of a higher-level protocol defined by the application.

## 2. Reading the last Flag on the Receiving Side

Java 17 signatures:

~~~java
// Fragment of a class implementing WebSocket.Listener.
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    socket.request(1);
    return null;
}

@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {
    socket.request(1);
    return null;
}
~~~

These two methods are called when receiving text or binary data. The input to `onText` is a decoded `CharSequence`; the input to `onBinary` is a `ByteBuffer` with data in the range `[position,limit)`. The boolean `last` has the same meaning for both:

| Receive callback | Meaning | Appropriate action |
| --- | --- | --- |
| `onText(ws,"A",true)` | An entire text message in this callback alone | Emit message "A", reset |
| `onText(ws,"Hel",false)` | An initial part of a text message | Copy/append; wait for more |
| `onText(ws,"lo",true)` | The final part of the current message | Append, emit "Hello", reset |
| `onBinary(ws,part,false)` | Binary message still in progress | Copy/consume per policy, keep state |
| `onBinary(ws,part,true)` | Binary message just ended | Complete binary message, reset |
| `onPing/onPong` | Separate control message | Do not reset text/binary accumulator |
| `onClose` | WebSocket input closed | Mark incomplete message as failed if last=true was not seen |

### A Single Invocation Does Not Have to Be a Complete Message

~~~text
onText(ws, "Hel", false) -> keep "Hel"
onText(ws, "lo",  true) -> complete "Hello"

onText(ws, "OK", true)  -> complete "OK"

onText(ws, "A", false)  -> keep "A"
onText(ws, "B", false)  -> keep "AB"
onText(ws, "C", true)   -> complete "ABC"
~~~

The example above has **three messages** (Hello, OK, ABC) but **six callbacks**. If an application treats each callback as a message, it will produce extra events, fail JSON parsing, or process incomplete payloads. Conversely, if an application always waits for at least two callbacks, the message `"OK"` received in one call will hang despite `last=true`.

### Resetting at the Right Time

When receiving `last=true`, **append the final part first**, then emit one message, and then reset for the next message. Resetting the buffer on **every callback** is wrong because it loses earlier parts. Not resetting after `last=true` is also wrong because it will concatenate the contents of two different messages.

## 3. Assembling Text with StringBuilder in Listener

Pattern for a WebSocket with dedicated state:

~~~java
// Java 17+ fragment, inside a class implementing WebSocket.Listener.
private final StringBuilder partialText = new StringBuilder();

@Override
public void onOpen(WebSocket socket) {
    socket.request(1);
}

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    partialText.append(data); // Copy immediately during the callback.

    if (last) {
        String whole = partialText.toString();
        partialText.setLength(0);
        handleWholeMessage(whole); // Application-defined helper.
    }

    socket.request(1); // Request the next callback turn.
    return null;
}
~~~

This is a **fragment**, not a standalone Java file; `handleWholeMessage()` must be defined. This pattern is suitable when messages are small, internal processing is fast, and one Listener owns the state of one WebSocket. Size limits and parser error handling must be added for production use.

### JSON Example

Suppose the protocol specifies **one WebSocket text message = one JSON document**:

~~~text
Callback 1: data="{\\"name\\":"    last=false
Callback 2: data="\\"An\\"}"      last=true
Complete message: {"name":"An"}
~~~

Only when fully assembled and `last=true` should it be parsed as an independent JSON document. If you want to parse incrementally, you must use a **stateful streaming parser** and only commit when structure/validation is complete; do not invoke a regular JSON parser on individual fragments.

### CharSequence Is UTF-16, Not TCP Bytes

According to the Javadoc, `onText` receives a valid UTF-16 sequence. The JVM/WebSocket implementation has already handled WebSocket text decoding at the protocol layer. `data.length()` is the number of **UTF-16 code units**, not the number of UTF-8 bytes or Unicode graphemes. An emoji may take two code units, and combining characters may have multiple code points. Callback boundaries are not JSON object boundaries or text line boundaries.

**Ownership:** Java has the right to reclaim the `CharSequence` passed to the callback once the returned `CompletionStage` completes. If the callback returns `null`, it is equivalent to signaling that it can be reclaimed immediately. Do not store the `data` reference itself in a list to process minutes later; use `data.toString()` or `StringBuilder.append(data)` immediately inside the callback.

## 4. Assembling Binary from ByteBuffer

With `onBinary`, the useful bytes lie from `data.position()` to `data.limit()`. Use `remaining()` to get the exact byte count, do not use `capacity()`, and do not assume `array()` exists (direct/read-only buffers may not have an accessible backing array).

~~~java
// Fragment: inside Listener, requires importing ByteArrayOutputStream.
private final ByteArrayOutputStream pendingBinary =
        new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(
        WebSocket socket, ByteBuffer data, boolean last) {

    byte[] chunk = new byte[data.remaining()];
    data.get(chunk); // Read the current part, do not read past limit.
    pendingBinary.write(chunk, 0, chunk.length);

    if (last) {
        byte[] whole = pendingBinary.toByteArray();
        pendingBinary.reset();
        handleWholeBinary(whole);
    }

    socket.request(1);
    return null;
}
~~~

The pattern above is only valid for small messages **with a size limit**. For large binary files, you should stream to a sink/file with a quota and only mark the file complete when `last=true`, verifying checksums/metadata according to the application protocol. If you keep accumulating in a `ByteArrayOutputStream` without bound, `request(1)` will not prevent running out of memory.

According to the Javadoc, **do not access the ByteBuffer provided by the Listener after the callback's CompletionStage completes**. If you pass the buffer directly to an executor and immediately return null, the worker may read data that the implementation has already reclaimed/reused. Fix this by copying bytes inside the callback or keeping the CompletionStage pending until downstream stops using the buffer; you still need to manage thread-safety, ordering, and backpressure.

## 5. request(n) Counts Receive Invocations, Not Messages

`WebSocket.request(long n)` increments a counter for **the number of times the WebSocket is allowed to invoke receive methods**. The counter starts at 0. Receive methods include `onText`, `onBinary`, `onPing`, `onPong`, `onClose`. `onOpen` and `onError` are not counted. `request(0)` or `request(n<0)` throws `IllegalArgumentException`; do not use 0 as a pause operation.

~~~text
socket.request(1)
       |
       v
onText("Hel", false)
       |
       +-- Consumes this invocation's allowance.
       +-- Text message is not finished.
       |
If no further request: no allowance yet for the next onText.
       |
socket.request(1)
       |
       v
onText("lo", true)
       |
       +-- Emit complete message "Hello"
~~~

The default `Listener.onOpen` calls `request(1)`; if you override `onOpen` as in the examples here, you must call it explicitly. The default `onText/onBinary/onPing/onPong` also request one more, but when you override them, your own code is responsible for supplying demand. A Listener that wants to receive full messages can call `request(1)` after each callback, or use a larger window n with bounded processing.

### Ping Can Be Interleaved Between Parts

RFC 6455 allows control frames to be interleaved between frames of a fragmented message:

~~~text
onText("Hel", false)
onPing(ByteBuffer(...))   # a separate control message
onText("lo", true)        # text message "Hello" just completed
~~~

`onPing` is a receive invocation and may consume allowance. Do not reset the text accumulator just because a Ping or Pong arrives. `onPing/onPong` do not have a last flag because control messages are not fragmented like text/binary data messages. The JDK WebSocket typically replies with Pong automatically upon receiving Ping per the API contract, so do not arbitrarily send an extra Pong unless required by protocol.

### Byte Count Is Not Bounded by request(1)

A single callback can contain a significant number of bytes/characters. `request(1)` only limits one **invocation**, and does not cap the size inside a callback or the capacity of JDK/OS buffers. You need a max-size per message, max concurrent sockets, a queue byte budget, and a deadline for partial messages.

### CompletionStage Does Not Replace Demand

`WebSocket.Listener.onText/onBinary/onPing/onPong` returns a `CompletionStage<?>`. This stage tells the WebSocket **when it may reclaim the delivered data**, not whether the message is complete or how many new callback invocations are permitted. The Javadoc states that an uncompleted Stage **does not automatically prevent new callbacks** if the application has already granted demand.

| Signal | Indicates | Does not indicate |
| --- | --- | --- |
| `last=true` | Callback ends the current message | Socket closed / server business ACK |
| `request(1)` | Allows at most one more receive method call | One message or one byte |
| `CompletionStage.complete` | Callback has finished using the data | Entire message has arrived |
| `sendText(...).join()` | Send operation completed on the client side | Server has processed/committed business logic |
| `onClose` | WebSocket input is closing | Previous message missing last can be accepted |

A proper way to implement backpressure when processing fragments on a worker: **copy the data**, submit to a bounded queue, and only call `request(1)` when the worker finishes processing or the queue has space. Do not request thousands of turns and hope returning a slow Stage will substitute for queue control. If offloading multiple fragments, you must preserve order so messages are not assembled incorrectly.

## 6. Sending Multiple Parts with sendText and sendBinary

On the sending side, the JDK provides:

~~~java
CompletableFuture<WebSocket> sendText(
        CharSequence data, boolean last);

CompletableFuture<WebSocket> sendBinary(
        ByteBuffer data, boolean last);
~~~

In both APIs, `last=false` indicates that the current outbound message has more parts to follow; `last=true` indicates that the part just sent completes the message. **Do not use `last=true` as a command to close the WebSocket.**

### Sending One Text Message in Two Operations

~~~java
// Java 17+ fragment, socket is a connected WebSocket.
socket.sendText("Hello ", false)
      .thenCompose(ws -> ws.sendText("Java", true))
      .join();
~~~

This chain sends **one** text message “Hello Java”. `thenCompose` waits for the previous operation to complete before sending the next part. If you call two `sendText` data operations concurrently, the operation may complete exceptionally because a send is still pending. The Javadoc specifies `IllegalStateException` when a sendText/sendBinary is pending or the previous message type is still unfinished.

### Sending a Multi-Part Binary Message

~~~java
// Java 17+ fragment.
ByteBuffer first = ByteBuffer.wrap(new byte[] {1, 2});
ByteBuffer lastPart = ByteBuffer.wrap(new byte[] {3, 4});

socket.sendBinary(first, false)
      .thenCompose(ws -> ws.sendBinary(lastPart, true))
      .join();
~~~

According to the Javadoc, you must not read/write/modify the send buffer while the Future is not yet complete; upon normal completion, the buffer has no remaining bytes. The buffer has `position/limit` state, and not necessarily its entire capacity is sent.

### Do Not Mix Types While a Message Is Unfinished

~~~java
// Anti-pattern: text message is not yet complete.
socket.sendText("partial", false)
      .thenCompose(ws ->
              ws.sendBinary(ByteBuffer.wrap(new byte[]{1}), true));
~~~

`sendBinary` may fail with `IllegalStateException` because the preceding text part has not ended the message. You must finish the text with `sendText(...,true)` before starting an independent binary message.

### last and close Are Two Different Things

- `sendText("A",true)`: closes this **text message**, and the socket can still receive/send other messages.
- `sendBinary(buffer,true)`: closes this **binary message**.
- `sendClose(WebSocket.NORMAL_CLOSURE, "")`: initiates closing **WebSocket output** with a Close control message; not a data fragment.
- `abort()`: closes input/output abruptly.

Example of two text messages followed by close:

~~~java
socket.sendText("one", true)
      .thenCompose(ws -> ws.sendText("two", true))
      .thenCompose(ws ->
              ws.sendClose(WebSocket.NORMAL_CLOSURE, ""))
      .join();
~~~

A successful `sendText/sendBinary` Future **does not confirm that the recipient has processed the business logic**. If you need to be sure the server has persisted the transaction, you must design a separate ACK/message ID/timeout mechanism.

## 7. Java 17+ WebSocket Verification Program on Loopback

The example uses the **standard JDK WebSocket client** and a mini WebSocket server based on `ServerSocket`, strictly for this lesson and bound only to `127.0.0.1`. The server performs the RFC 6455 HTTP Upgrade, receives masked frames from the client, and then sends one text message and one binary message, **each split into two WebSocket frames**. The client assembles the callbacks using the last flag, then performs an orderly close.

**Do not use this mini server on the Internet:** it only handles short frames, a single client, lacks many validations (extensions, long frame sizes, authentication, other protocol errors), and has no TLS. It only demonstrates the core API behavior, not a production server.

Save the entire code below as **`WebSocketLastDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.EOFException;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.HexFormat;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class WebSocketLastDemo {
    private static final java.nio.charset.Charset ASCII =
            StandardCharsets.US_ASCII;
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final String MAGIC =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    private static String readHeaders(InputStream in)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int match = 0;

        while (bytes.size() < 16_384) {
            int c = in.read();
            if (c == -1) {
                throw new EOFException("EOF in handshake");
            }
            bytes.write(c);
            if (c == "\r\n\r\n".charAt(match)) {
                match++;
                if (match == 4) {
                    return bytes.toString(ASCII);
                }
            } else {
                match = c == '\r' ? 1 : 0;
            }
        }
        throw new IOException("Oversized HTTP headers");
    }

    // Server-to-client frames are NOT masked per RFC 6455.
    private static void frame(
            OutputStream out, int opcode, boolean last,
            byte[] data) throws IOException {
        if (data.length > 125) {
            throw new IllegalArgumentException(
                    "Demo handles only short frames");
        }
        out.write((last ? 0x80 : 0x00) | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    private record Frame(
            int opcode, boolean last, byte[] payload) { }

    // Client-to-server frames MUST be masked per RFC 6455.
    private static Frame readClientFrame(DataInputStream in)
            throws IOException {
        int first = in.readUnsignedByte();
        int second = in.readUnsignedByte();
        int len = second & 0x7f;

        if ((second & 0x80) == 0) {
            throw new IOException("Client frame must be masked");
        }
        if (len > 125) {
            throw new IOException("Demo only handles short frames");
        }

        byte[] key = in.readNBytes(4);
        byte[] data = in.readNBytes(len);
        if (key.length != 4 || data.length != len) {
            throw new EOFException();
        }
        for (int i = 0; i < data.length; i++) {
            data[i] ^= key[i % 4];
        }

        return new Frame(
                first & 0x0f,
                (first & 0x80) != 0,
                data);
    }

    private static String serve(ServerSocket listener)
            throws Exception {
        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5_000);
            InputStream input = socket.getInputStream();
            OutputStream output = socket.getOutputStream();

            // RFC 6455 HTTP opening handshake.
            String headers = readHeaders(input);
            String key = null;
            for (String line : headers.split("\r\n")) {
                if (line.regionMatches(
                        true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                    key = line.substring(18).trim();
                }
            }
            if (key == null) {
                throw new IOException("Missing WebSocket key");
            }

            byte[] hash = MessageDigest.getInstance("SHA-1")
                    .digest((key + MAGIC).getBytes(ASCII));
            String accept =
                    Base64.getEncoder().encodeToString(hash);

            output.write(
                    ("HTTP/1.1 101 Switching Protocols\r\n"
                     + "Upgrade: websocket\r\n"
                     + "Connection: Upgrade\r\n"
                     + "Sec-WebSocket-Accept: " + accept
                     + "\r\n\r\n").getBytes(ASCII));
            output.flush();

            DataInputStream frames = new DataInputStream(input);
            ByteArrayOutputStream fromClient =
                    new ByteArrayOutputStream();

            // Read one fragmented text message from client.
            while (true) {
                Frame f = readClientFrame(frames);
                if (f.opcode() != 1 && f.opcode() != 0) {
                    throw new IOException(
                            "Unexpected opcode " + f.opcode());
                }
                fromClient.write(f.payload());
                if (f.last()) {
                    break;
                }
            }

            // TEXT FIN=0 then CONTINUATION FIN=1.
            frame(output, 1, false,
                    "Hello ".getBytes(UTF8));
            frame(output, 0, true,
                    "Java".getBytes(UTF8));

            // BINARY FIN=0 then CONTINUATION FIN=1.
            frame(output, 2, false,
                    new byte[]{1, 2});
            frame(output, 0, true,
                    new byte[]{3, 4});

            // Read Close from client, reply with Close code 1000.
            Frame close = readClientFrame(frames);
            if (close.opcode() != 8) {
                throw new IOException("Expected close handshake");
            }
            frame(output, 8, true,
                    new byte[]{3, (byte) 232});

            return fromClient.toString(UTF8);
        }
    }

    public static void main(String[] args)
            throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try (ServerSocket listener =
                     new ServerSocket(0, 1, loopback)) {
            Future<String> receivedByServer =
                    worker.submit(() -> serve(listener));

            CountDownLatch wholeMessages =
                    new CountDownLatch(2);
            AtomicReference<Throwable> error =
                    new AtomicReference<>();
            AtomicReference<String> text =
                    new AtomicReference<>();
            AtomicReference<byte[]> binary =
                    new AtomicReference<>();

            WebSocket.Listener callbacks =
                    new WebSocket.Listener() {
                private final StringBuilder parts =
                        new StringBuilder();
                private final ByteArrayOutputStream binaryParts =
                        new ByteArrayOutputStream();

                @Override
                public void onOpen(WebSocket socket) {
                    socket.request(1);
                }

                @Override
                public CompletionStage<?> onText(
                        WebSocket socket,
                        CharSequence part, boolean last) {
                    parts.append(part);

                    if (last) {
                        text.set(parts.toString());
                        parts.setLength(0);
                        wholeMessages.countDown();
                    }
                    socket.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onBinary(
                        WebSocket socket,
                        ByteBuffer part, boolean last) {
                    byte[] chunk =
                            new byte[part.remaining()];
                    part.get(chunk);
                    binaryParts.write(
                            chunk, 0, chunk.length);

                    if (last) {
                        binary.set(binaryParts.toByteArray());
                        binaryParts.reset();
                        wholeMessages.countDown();
                    }
                    socket.request(1);
                    return null;
                }

                @Override
                public void onError(
                        WebSocket socket, Throwable cause) {
                    error.compareAndSet(null, cause);
                    wholeMessages.countDown();
                    wholeMessages.countDown();
                }
            };

            HttpClient client = HttpClient.newHttpClient();
            WebSocket socket = client.newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .buildAsync(
                            URI.create(
                                    "ws://127.0.0.1:"
                                    + listener.getLocalPort()
                                    + "/demo"),
                            callbacks)
                    .get(5, TimeUnit.SECONDS);

            // Send one text message with two sendText calls.
            socket.sendText("Hi ", false)
                    .thenCompose(s ->
                            s.sendText("server", true))
                    .get(5, TimeUnit.SECONDS);

            // Wait for two complete messages: one text, one binary.
            if (!wholeMessages.await(
                    5, TimeUnit.SECONDS)) {
                throw new TimeoutException(
                        "Inbound messages not complete");
            }
            if (error.get() != null) {
                throw new IOException(
                        "WebSocket listener failed", error.get());
            }

            System.out.println(
                    "inboundText=" + text.get());
            System.out.println(
                    "inboundBinary="
                            + HexFormat.of().formatHex(
                                    binary.get()));

            socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
                    .get(5, TimeUnit.SECONDS);
            System.out.println(
                    "serverReceived="
                            + receivedByServer.get(
                                    5, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

### Compile Command and Output

~~~bash
javac WebSocketLastDemo.java
java WebSocketLastDemo
~~~

**Actual verified result on JDK 24, using Java 17+ APIs:**

~~~text
inboundText=Hello Java
inboundBinary=01020304
serverReceived=Hi server
~~~

Precise explanation:

1. The mini server binds loopback `127.0.0.1` and OS-assigned port 0, returning HTTP 101 with `Sec-WebSocket-Accept`.
2. The client sends `Hi ` via `sendText(...false)` and then `server` via `sendText(...true)`. The server receives the masked client frames, unmasks them, and reconstructs the text **Hi server**.
3. The server sends text “Hello Java” across two **WebSocket frames** and then sends binary `01 02 03 04` across two more frames. The client callbacks append data and only complete a message when the callback reports `last=true`.
4. `CountDownLatch(2)` on the client decrements **once per complete message**, not per fragment. Whether the JDK delivers 1 or multiple callbacks per message, the final result remains correct.
5. `HexFormat.of().formatHex(...)` has been available since Java 17, so the program is compatible with version 17+.
6. After receiving both messages, the client sends Close; the server reads Close and replies with code 1000. This is a WebSocket close, distinct from the last flag that ends a text/binary message.

**Do not print the callback count to stdout**, because there is no contract binding the callback count to the number of WebSocket frames. What needs to be verified is the **complete message**. The mini server is not an authenticated Internet server and is not for production use. If the environment blocks loopback sockets, an IOException/timeout may occur.

## 8. When to Process Incrementally and When to Wait for last?

| Content | Can it be processed when `last=false`? | When `last=true` |
| --- | --- | --- |
| JSON document under 1 message = 1 JSON convention | Only parse incrementally if the parser keeps state; do not commit the document | Validate the entire JSON and emit the complete event |
| Short chat text | Can show a preview if the design has a partial state | Mark the message as fully received |
| Large file/binary | Can write each chunk to a temporary file | Finalize file, verify checksum/metadata, then publish |
| Protobuf or business framing | Depends on custom parser/framing | Complete WebSocket message, check protocol-level framing |
| Compressed data | Can feed a bounded streaming decompressor | Finish stream/verify integrity per format |
| Transaction with side effects | Do not commit just because a fragment arrived | Only after the entire payload is valid and business rules allow |

**Do not treat last=true as the peer's ACK** when you are the sender. On the receiving side, last=true only proves that the WebSocket client has received the full message per the API; it does not prove that the data schema or signature is valid. A complete message can still be malformed JSON or an unauthorized command.

## 9. Memory Limits: Do Not Append Without Bound

Receiving multiple callbacks easily leads to a bug: the application keeps appending text/binary until last=true, while the peer sends a message hundreds of MB long or never finishes the message. That can cause an OOM even if you only call request(1) one turn at a time.

### Text: Limiting UTF-16 Code Units

~~~java
// Fragment in onText; MAX_CHARS is a limit > 0.
if (data.length() > MAX_CHARS - partialText.length()) {
    handleOversize(); // Helper that reports error and stops per policy.
    return null;
}
partialText.append(data);
if (last) {
    String whole = partialText.toString();
    partialText.setLength(0);
    processWholeText(whole);
}
socket.request(1);
return null;
~~~

This is a limit in **UTF-16 code units**, not UTF-8 bytes on the network. If the policy limits to 1 MB, you must measure bytes via encoding/decoder or maintain a separate quota. Using `MAX_CHARS - partialText.length()` avoids integer overflow in the check.

### Binary: Limiting Bytes

~~~java
// Fragment in onBinary; MAX_BYTES and binaryParts are dedicated state.
int amount = data.remaining();
if (amount > MAX_BYTES - binaryParts.size()) {
    handleOversize();
    return null;
}
byte[] copy = new byte[amount];
data.get(copy);
binaryParts.write(copy, 0, copy.length);

if (last) {
    byte[] complete = binaryParts.toByteArray();
    binaryParts.reset();
    processWholeBinary(complete);
}
socket.request(1);
return null;
~~~

Beyond a per-message limit, set a **deadline** for incomplete messages, max connections, max in-flight bytes, a bounded work queue, and a backpressure policy. For very large files, prefer streaming to a file or stateful parser rather than collecting everything into a single array.

**When exceeding the limit:** do not blindly keep requesting; fail/cancel/abort according to policy. The Java 17 `sendClose` Javadoc forbids certain status codes, including **1009**, so do not mechanically instruct calling `sendClose(1009, ...)`. You can choose an appropriate valid close code or `abort()`, and record the failure of the business request.

## 10. When the WebSocket Closes or Errors While a Message Is Incomplete

If `last=false` and then Close/Error occurs, the accumulated parts **do not become a complete message**. Do not try to parse an incomplete body as if `last=true` had arrived.

~~~java
// Fragment in WebSocket.Listener.
@Override
public CompletionStage<?> onClose(
        WebSocket socket, int code, String reason) {
    discardPartialMessages(); // Helper: reset, report incomplete.
    notifyConnectionClosed(code, reason);
    return null;
}

@Override
public void onError(WebSocket socket, Throwable error) {
    discardPartialMessages();
    notifyConnectionFailed(error);
}
~~~

The WebSocket Javadoc specifies that after `onClose` or `onError`, no further Listener methods will be invoked for that connection. `onClose` is input-side closure; `sendClose` closes the output side, while `abort()` closes both sides abruptly. On abort or network error, do not assume the full close handshake will take place.

In real applications, cleanup must be idempotent because timeouts, producers, workers, and callbacks may concurrently try to complete the same request. If the application is waiting for a response matching a request ID, complete that future with an error/timeout when the connection closes mid-message.

## 11. Concurrency and Callback CompletionStage

The Javadoc states that Listener callbacks for **a single WebSocket** are invoked sequentially and **non-reentrantly**: a new invocation can only begin after the previous invocation has returned. This allows a dedicated Listener to hold its own `StringBuilder` and append inside the callback without sharing state with a second concurrent callback on the same socket.

However, you must distinguish:

- Callbacks do not necessarily always run on the same thread.
- `onError` may be invoked in asynchronous situations; state shared with another executor must be thread-safe.
- If **the same Listener is used for multiple WebSockets**, callbacks from different sockets can run concurrently.
- If `onText` offloads processing to a worker and returns immediately, the worker may finish processing chunks out of order, even though the original callbacks were sequential.
- The Stage returned from a callback does not replace `request(n)`; if demand remains, the WebSocket may continue invoking callbacks while the previous callback's stage has not yet completed.

Example fragment for background processing and copying data:

~~~java
// Java 17+ fragment; executor/processChunk/reportFailure are provided by the app.
@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    String copy = data.toString();

    CompletableFuture<Void> done =
            CompletableFuture.runAsync(
                    () -> processChunk(copy, last), executor);

    done.whenComplete((ignored, failure) -> {
        if (failure == null) {
            socket.request(1);
        } else {
            reportFailure(failure);
            socket.abort();
        }
    });
    return done;
}
~~~

If using a multi-threaded worker pool, you must preserve **fragment order** before assembling. Do not grant many requests while the queue is already overloaded; you can use a serial executor per connection or a state-machine actor. Any exception from the worker must be handled according to deadline/cancel/lifecycle, never leaving the session waiting indefinitely.

## 12. Common Pitfalls and How to Diagnose Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| Random JSON parse errors | Parsing every `onText` even when `last=false` | Append until `last=true` or use a streaming parser |
| Receives only the first part then stalls | Only calling `request(1)` in onOpen | Request again after callback when ready |
| Two messages concatenated | Forgot to reset accumulator at `last=true` | Emit then reset |
| Lost initial fragment | Resetting accumulator on **every** callback | Reset only after a complete message |
| Ping received but in-progress text lost | Resetting text upon receiving a control frame | Handle Ping/Pong separately |
| Different results across JDKs | Assuming 1 frame = 1 callback | Rely only on `last` |
| ByteBuffer contains "garbage" | Using capacity or the entire backing array | Copy exact `remaining()` |
| Worker reads wrong CharSequence | Keeping ref after Stage completes | Copy with toString inside callback |
| Binary data gets mutated | Reusing send buffer before send Future completes | Wait for Future before reusing |
| `sendBinary` throws IllegalStateException | Previous text message not yet finished | Finish text with last=true first |
| Two parallel sendText calls fail | A data-send is still pending | Chain thenCompose or use a serial send queue |
| OOM from large message | Unbounded append before last | Max-size, deadlines, streaming |
| Callback has no next invocation | Demand exhausted, or socket closed | Track receive allowance/onError/onClose |
| Error/Close while partial remains | Transport or protocol interrupted | Do not emit partial as complete |
| Callback Stage not complete yet new callback arrives | Confusing Stage with demand | Manage request(n) and queue separately |
| No server ACK seen | Confusing send Future with business result | Design response/ACK and request ID |
| WebSocket does not close when message last=true | Last is not Close | Use sendClose for orderly shutdown |
| sendClose(1009) rejected | Java 17 Javadoc forbids this code | Use a valid status/abort per policy |

### Checklist for Debugging a Callback

Record the minimum without logging sensitive payloads:

~~~text
connectionId
callbackKind = onText | onBinary | onPing | onPong | onClose | onError
last = true | false | N/A
fragmentSize = data.length() or data.remaining()
accumulatedSize
messageCountCompleted
receiveRequestsGranted
error / close code / latency
~~~

If the callback count differs between two environments but the final message content matches, that may be a normal difference in how the JDK splits data delivery. Do not try to fix it by waiting for a fixed number of callbacks.

## 13. Recommended Test Cases

| Scenario | Simulated data | Expected result |
| --- | --- | --- |
| Single callback | `"OK", true` | One message "OK" |
| Two callbacks | `"Hel",false`; `"lo",true` | One message "Hello" |
| Multiple callbacks | `"A",false`; `"B",false`; `"C",true` | One message "ABC" |
| Two consecutive messages | `"A",true`; `"B",true` | Two independent messages |
| Two-part binary | `[01,02],false`; `[03],true` | One payload 010203 |
| Interleaved Ping | Text false; Ping; Text true | One text message + one Ping |
| Close while incomplete | Text false; onClose | Do not publish incomplete |
| Zero demand | Only request1 then callback false | No guarantee of further callbacks without requesting |
| Invalid | request(0) | IllegalArgumentException |
| Oversize | Multiple fragments exceeding quota | Report error/abort, no OOM |
| Slow worker | Offload with bounded queue | Real backpressure, no out-of-order |
| Two-part send | sendText false then true | One message on server side |
| Mixed type mid-message | sendText false then sendBinary true | State error |
| Frame vs callback | Change network/frame segmentation | Final message unchanged |

Prefer **unit testing the assembler** and **real integration testing** like the program in section 7. In unit tests, you can call a pure `accept(part,last)` function to verify reset/boundaries; in integration tests, use a real WebSocket and do not depend on TCP packet counts.

## 14. Self-Check Questions

**Q1.** `onText(ws,"Hel",false)` occurs. Is this a complete message yet?  
**Answer:** No; more parts are needed, only process at message-level when last=true.

**Q2.** `onText(ws,"OK",true)` is the first callback. Do we need to wait for a next part?  
**Answer:** No. A single callback can contain the entire message.

**Q3.** Does `request(1)` grant permission for one message, frame, or callback?  
**Answer:** One receive callback invocation, not necessarily one message.

**Q4.** Why can `request(1)` cause an incomplete message to stall?  
**Answer:** The first callback with last=false consumes the allowance. You must request again for the WebSocket to deliver the remaining callbacks.

**Q5.** If `onPing` arrives between two onText fragments, should the text be reset?  
**Answer:** No. Ping is a separate control message that can be interleaved between fragments.

**Q6.** Does `data.length()` in onText measure UTF-8 bytes?  
**Answer:** No, it is the UTF-16 code units of the CharSequence.

**Q7.** `onBinary` has position=10, limit=14, capacity=100. How many bytes need to be read?  
**Answer:** 4 bytes (remaining), not 100.

**Q8.** Is it safe to keep the original CharSequence after the callback returns null?  
**Answer:** Not safe; the implementation has the right to reclaim it. Copy immediately or manage Stage lifetime.

**Q9.** `sendText("A",false)` then `sendText("B",true)` is how many messages?  
**Answer:** One text message “AB” if sent validly in order.

**Q10.** Does `sendText("A",true)` close the WebSocket?  
**Answer:** No. It only completes the message; the socket continues operating.

**Q11.** While a text message is still unfinished, can sendBinary be called immediately?  
**Answer:** No; you must finish the text first, otherwise IllegalStateException may be thrown.

**Q12.** Does a completed sendText Future prove that the server wrote to the DB?  
**Answer:** No; that is the client's send result, a business ACK is needed.

**Q13.** If partial text is received and then the connection errors before last=true, should that message be emitted?  
**Answer:** No. That is an incomplete message; report error and clean up state.

**Q14.** Can you rely on each WebSocket frame having exactly one onText callback?  
**Answer:** No. The API makes no such guarantee; use last to assemble.

**Q15.** Why is request(1) not enough to guarantee bounded RAM?  
**Answer:** A single fragment can be large, a message can have very many fragments, and state can be held for a long time; you need max-size, deadlines, max concurrency, and bounded queues.

**Q16.** What is the CompletionStage returned from onText used for?  
**Answer:** To signal permission to reclaim callback data; it does not determine end-of-message or the number of callback invocations.

**Q17.** Can a single Listener used for multiple WebSockets share an unlocked StringBuilder?  
**Answer:** Not safe: callbacks from different WebSockets can run concurrently; use per-socket state or proper synchronization.

**Q18.** Why does the loopback example not log the callback count?  
**Answer:** Because the callback count is not fixed by the API to equal the frame count. The accurately assembled content is what needs to be tested.

## 15. Official References

- Oracle Java SE 17 — `WebSocket`: `request(long)` counts callbacks; `sendText/sendBinary(last)`, IllegalStateException, sendClose and abort: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- Oracle Java SE 17 — `WebSocket.Listener`: `onText/onBinary(data,last)`, callback ordering, `CompletionStage` and buffer ownership lifetime: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- Oracle Java SE 17 — `WebSocket.Builder.buildAsync`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- Oracle Java SE 17 — `HttpClient.newWebSocketBuilder()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `ByteBuffer.remaining/position/limit`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html
- Oracle Java SE 17 — `CompletionStage`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html
- IETF RFC 6455 — The WebSocket Protocol, fragmentation/continuation, masking, control frames: https://www.rfc-editor.org/rfc/rfc6455
