# Sending Text, Binary, Ping, Pong, and Receiving Send Completion Results

## 1. Context of the WebSocket Client in Java

`java.net.http.WebSocket` is a built-in client API available since Java 11 (works well in Java 17+). After upgrading the connection via HTTP Upgrade, the client can send **text messages**, **binary messages**, and **control messages** such as **Ping**, **Pong**, and **Close**. A WebSocket maintains two independent directions: **input** and **output**. Data from the client goes through the `send...` methods; data returning from the peer is delivered to `WebSocket.Listener`.

This topic focuses on four commands:

| Send command | Data | API result | Where is it received back from the peer? |
| --- | --- | --- | --- |
| `sendText(CharSequence, boolean last)` | Text, can be a fragment | `CompletableFuture<WebSocket>` | `Listener.onText` if the peer sends text |
| `sendBinary(ByteBuffer, boolean last)` | Binary bytes | `CompletableFuture<WebSocket>` | `Listener.onBinary` if the peer sends binary |
| `sendPing(ByteBuffer)` | Ping payload up to 125 bytes | `CompletableFuture<WebSocket>` | `Listener.onPong` when the peer replies with Pong |
| `sendPong(ByteBuffer)` | Pong payload up to 125 bytes | `CompletableFuture<WebSocket>` | No automatic ACK; the peer side may receive Pong |
| `sendClose(int,String)` | WebSocket Close control | `CompletableFuture<WebSocket>` | `Listener.onClose` when receiving Close from the peer |

**A future completes when the send operation is finished, which does not mean the peer has processed the business logic.** For example, `ws.sendPing(payload).join()` indicates that the Ping was sent from the Java client side; only `Listener.onPong` indicates that the client **has received** a Pong. For text/binary, the application may need a **separate ACK message** to confirm that the server has processed/committed it.

~~~text
Application                       java.net.http.WebSocket                 Peer
    |                                      |                                |
    |-- sendText("HELLO", true) ---------->| ------ outbound text -------> |
    |<--- CompletableFuture done ---------|       send operation finished   |
    |                                      |                                |
    |                          <--------------- text/ACK from peer ---------|
    |<--- Listener.onText ----------------|       receive inbound message   |
    |                                      |                                |
    |-- sendPing("id") ------------------>| -------- Ping --------------> |
    |<--- send future done ---------------|                               |
    |                          <--------------- Pong("id") ---------------|
    |<--- Listener.onPong ----------------|       response from peer       |
~~~

## 2. Initializing the WebSocket Client and Distinguishing the Handshake Future

The WebSocket client is built into the JDK:

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }
};

WebSocket ws = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(URI.create("wss://example.org/ws"), listener)
        .join();
~~~

*This is an **illustrative snippet** (requires imports, a real endpoint, error handling, and timeouts), not a standalone program. The complete example in section 9 uses loopback only.*

`buildAsync(...)` returns a `CompletableFuture<WebSocket>` for the **HTTP Upgrade / connection initialization phase**. It is different from the futures returned by `sendText`/`sendBinary`/`sendPing`/`sendPong` **after the connection is established**. Do not send application data if the handshake has not succeeded. A normal HTTP endpoint does not automatically become a WebSocket server just because the client calls `buildAsync`.

Choose `wss://` in production systems to protect the transport with TLS and verify the server/certificate according to standard configuration. `ws://127.0.0.1` in this lesson is only for local testing on the same machine, without TLS.

## 3. sendText and the Exact Meaning of last

Sending a complete text message:

~~~java
CompletableFuture<WebSocket> sent = ws.sendText("Xin chào", true);
WebSocket sameSocket = sent.join();
~~~

*Illustrative snippet, assuming `ws` and imports exist externally.*

`last=true` means **this part ends the message**, not a synchronous command. If the message is not finished yet, it can be fragmented:

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("Xin ", false)
          .thenCompose(socket -> socket.sendText("chào", true));
sent.join();
~~~

A `sendText(..., false)` is not a complete message. Do not switch to `sendBinary` while the previous text message has not ended: the Javadoc states that a text/binary send future can complete exceptionally with `IllegalStateException` if a text/binary send operation is pending or a message of another type has not properly ended.

The `CharSequence` passed into `sendText` **must not be modified before the send command's future completes**. Therefore, using an immutable `String` is usually simpler than passing a `StringBuilder` being modified by another thread. An invalid UTF-16 sequence may cause the operation to fail during encoding.

**Do not assume one `sendText` leads to exactly one `Listener.onText` on the peer.** A WebSocket listener may receive multiple parts with the `last=false` parameter followed by `last=true`; you must accumulate the full message before parsing business content.

## 4. sendBinary and the ByteBuffer Lifecycle

Sending three binary bytes:

~~~java
ByteBuffer bytes = ByteBuffer.wrap(new byte[] {1, 2, 3});
CompletableFuture<WebSocket> sent = ws.sendBinary(bytes, true);
sent.join();
System.out.println(bytes.hasRemaining()); // false if completed normally
~~~

*Illustrative snippet with imports and `ws` already available.*

The data sent consists of the bytes **from `ByteBuffer.position()` to `limit()`**, equivalent to `remaining()` bytes, not the entire `capacity()`. If a buffer has `capacity=8, position=2, limit=5`, only 3 bytes are sent.

**Ownership rule:** after `sendBinary(buffer, ...)`, **do not access or modify the buffer before the future completes**, because Java WebSocket may still be using it. If the future completes **normally**, the buffer will have no `remaining()` bytes left. Do not call `clear()`/`flip()` or reuse the buffer too early. When the future completes exceptionally, do not assume how many bytes were sent; you must inspect/close the connection according to policy before replaying.

For multi-part binary data, use `last=false` for the initial parts and `last=true` for the final part, while ensuring each send is ordered. If you must send files or large data, you need to limit the number of pending bytes; a send completion future does not replace queue limits/outbound backpressure.

## 5. sendPing and sendPong: Control Messages Differ from Application Data

Both `sendPing(ByteBuffer)` and `sendPong(ByteBuffer)` use a **payload of at most 125 bytes**, counted by `remaining()` from position to limit. The payload can be empty. Do not manually add opcode/mask/WebSocket frame headers to the send buffer; the JDK handles that.

Example of sending Ping:

~~~java
CompletableFuture<WebSocket> pingSent = ws.sendPing(
        ByteBuffer.wrap("hi".getBytes(StandardCharsets.US_ASCII)));
pingSent.join(); // Ping send completed; does not guarantee Pong was received.
~~~

Example of sending an explicit Pong:

~~~java
CompletableFuture<WebSocket> pongSent = ws.sendPong(
        ByteBuffer.wrap("ok".getBytes(StandardCharsets.US_ASCII)));
pongSent.join();
~~~

*Two illustrative snippets; require `ws`, imports, and an open connection.*

### How do Ping and Pong relate?

- When a peer receives a Ping, according to the WebSocket protocol it normally sends a corresponding Pong. The Java `WebSocket` implementation **automatically sends a reciprocal Pong when receiving a Ping**; therefore, it is **rarely necessary** to call `sendPong` manually inside `onPing`.
- Explicit `sendPong` is still a valid API, for example to test control frames or send an unsolicited Pong. Do not use Pong as an "order saved ACK".
- The `sendPing` future completing is an **outbound signal**; `Listener.onPong` is an **inbound signal**. If a heartbeat is needed, you must match the payload or ID and manage a timeout for Pong, rather than just waiting on `sendPing().get()`.
- Ping/Pong do not have a `last` parameter and **cannot be fragmented**; exceeding 125 bytes may complete exceptionally with `IllegalArgumentException`.
- If a Ping/Pong operation is already pending, a new Ping/Pong command may fail with `IllegalStateException`. You should track the future and serialize control sends when needed.
- Do not touch or modify a control `ByteBuffer` being sent until the future finishes. Do not put sensitive data in Ping/Pong payloads.

## 6. Send Completion Future: Three Different States

`sendText`, `sendBinary`, `sendPing`, and `sendPong` all return `CompletableFuture<WebSocket>`:

1. **Normal completion:** the send operation succeeded; `future.get()`/`future.join()` returns the WebSocket itself. This **does not confirm the peer has read, parsed, or processed** the data.
2. **Exceptional completion:** sending failed, for example output closed, I/O error, a send of the same kind is pending, mixing message types before the previous message ended, or control payload too long.
3. **Pending:** the operation has been initiated but is not finished yet. Do not modify the buffer/CharSequence being sent; handle timeouts and cancellation in a controlled manner.

~~~java
CompletableFuture<WebSocket> pending = ws.sendText("hello", true);
pending.whenComplete((socket, error) -> {
    if (error == null) {
        System.out.println("outbound send completed");
    } else {
        System.err.println("outbound send failed: " + error);
    }
});
~~~

*Illustrative snippet; the `whenComplete` callback only observes the send result.*

`join()` may block the calling thread and typically throws `CompletionException` when the operation completes exceptionally. `get(timeout, unit)` may block for up to a specified duration and throw `TimeoutException`, `ExecutionException`, or `InterruptedException`. **A timeout while waiting on a future does not prove the operation was cancelled or that the peer did not receive the bytes.** On error, you must inspect the cause/connection state and not blindly retry non-idempotent business commands.

To avoid multiple pending text/binary sends, use **sequential chaining**:

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("start", true)
          .thenCompose(socket -> socket.sendBinary(
                  ByteBuffer.wrap(new byte[] {1, 2}), true))
          .thenCompose(socket -> socket.sendPing(
                  ByteBuffer.wrap(new byte[] {7})))
          .thenCompose(socket -> socket.sendPong(
                  ByteBuffer.wrap(new byte[] {8})));
sent.join();
~~~

*Illustrative snippet on sequencing, not a standalone program.*

**Do not initiate all `sendText` and `sendBinary` calls concurrently with `allOf` without a serialization mechanism:** later calls may see a text/binary send already pending and complete exceptionally with `IllegalStateException`. You need a per-connection outbound queue, `thenCompose`, a limit on pending bytes, and per-part error handling.

## 7. Inbound Listener: request(n), onText, onBinary, onPong

`WebSocket.Listener` handles the **inbound direction**. The methods `onText(ws, chars, last)`, `onBinary(ws, bytes, last)`, `onPing(ws, payload)`, `onPong(ws, payload)`, and `onClose(...)` are not return results of the send methods. They are callbacks for messages **coming from the peer**.

`WebSocket.request(long n)` grants **n receive callback invocations**, **not n bytes or n complete messages**. Because text/binary can be fragmented across multiple callbacks, the application must accumulate until `last=true` and call `request(1)` according to policy to continue receiving. If demand is 0, WebSocket will not invoke further receive methods even if data is available on the network.

Shortened example:

~~~java
class ExampleListener implements WebSocket.Listener {
    private final StringBuilder pending = new StringBuilder();

    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence part, boolean last) {
        pending.append(part);
        if (last) {
            System.out.println("whole message: " + pending);
            pending.setLength(0);
        }
        ws.request(1);
        return null;
    }

    @Override
    public CompletionStage<?> onPong(
            WebSocket ws, ByteBuffer data) {
        byte[] copy = new byte[data.remaining()];
        data.get(copy);
        ws.request(1);
        return null;
    }
}
~~~

*Illustrative snippet requiring imports; the full standalone class is in section 9.*

According to the JDK, receive callbacks return a `CompletionStage<?>` to tell the runtime **when it can reclaim the data region passed into the callback**. Returning `null` means immediate completion. The `CompletionStage` of a receive callback is **different** from the `CompletableFuture<WebSocket>` of a send operation; it **does not automatically increment the `request(n)` counter**. If processing the payload outside the callback, copy the data or keep the stage incomplete until you are done using it.

`onError` notifies of listener/receive errors and may occur separately from `onClose`. After an `onError` or `onClose` event, do not assume there will be subsequent receive callbacks. Inside the listener, keep logic short, thread-safe, and avoid long blocking.

## 8. Example Architecture: Loopback WebSocket Server to Test All Four Kinds

The JDK provides a `java.net.http.WebSocket` **client**, not a full production WebSocket server in the same usage style as `HttpServer` for regular HTTP. For the example to **run on its own without Internet or third-party libraries**, the program below creates a **very limited test server** on `127.0.0.1`:

- The server handles the required HTTP Upgrade/`Sec-WebSocket-Accept` using SHA-1 + Base64 as required by RFC 6455. SHA-1 here is the **RFC 6455 handshake mechanism**, not a choice for hashing passwords.
- The server reads **masked** WebSocket client frames (RFC 6455 rule), unmasks them, and only accepts short payloads up to 125 bytes with **FIN=1**.
- When receiving opcode 1 (text) or 2 (binary), the server **echoes** a frame of the same type; when receiving opcode 9 (Ping), the server replies with opcode 10 (Pong) with the exact payload.
- When receiving opcode 10 Pong explicitly sent by the client, the server verifies the `"ok"` payload. When receiving opcode 8 Close, the server replies with Close.
- The client uses the standard JDK WebSocket API, sends the four kinds in sequence; the listener waits for the echoes/Pong and then closes in an orderly manner.

**Extremely important limitation:** the server fixture **does not support** multiple clients, long frames, extended length, fragmented messages, extensions, TLS, subprotocols, complex malformed protocol cases, or production security. Do not build a real deployment from this test server. This lesson uses it solely to observe the **client's send API** against real wire-level WebSocket framing.

## 9. Runnable Java 17+ Code: text, binary, Ping, Pong, and Send Completion

Create the file `WebSocketSendKindsDemo.java` containing the entire program:

~~~java
import java.io.ByteArrayOutputStream;
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
import java.util.Arrays;
import java.util.Base64;
import java.util.Locale;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class WebSocketSendKindsDemo {
    private static final String GUID =
            "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

    record Frame(int opcode, byte[] data) {}

    static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream line = new ByteArrayOutputStream();
        for (int i = 0; i < 8192; i++) {
            int b = in.read();
            if (b < 0) throw new EOFException("HTTP header incomplete");
            if (b == '\n') {
                byte[] bytes = line.toByteArray();
                int len = bytes.length;
                if (len > 0 && bytes[len - 1] == '\r') len--;
                return new String(bytes, 0, len, StandardCharsets.US_ASCII);
            }
            line.write(b);
        }
        throw new IOException("HTTP header line too long");
    }

    static void handshake(InputStream in, OutputStream out) throws Exception {
        String first = readLine(in);
        if (!first.startsWith("GET /echo HTTP/1.1"))
            throw new IOException("unexpected upgrade path");
        String key = null;
        for (int lineCount = 0; lineCount < 80; lineCount++) {
            String line = readLine(in);
            if (line.isEmpty()) break;
            int colon = line.indexOf(':');
            if (colon > 0
                    && line.substring(0, colon).trim().toLowerCase(Locale.ROOT)
                        .equals("sec-websocket-key")) {
                key = line.substring(colon + 1).trim();
            }
        }
        if (key == null) throw new IOException("missing Sec-WebSocket-Key");
        byte[] sha1 = MessageDigest.getInstance("SHA-1").digest(
                (key + GUID).getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(sha1);
        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.US_ASCII));
        out.flush();
    }

    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        if (first < 0) throw new EOFException("missing WebSocket frame");
        int second = in.read();
        if (second < 0) throw new EOFException("missing frame length");
        if ((first & 0x80) == 0) throw new IOException("demo requires FIN");
        if ((second & 0x80) == 0) throw new IOException("client must mask frames");
        int length = second & 0x7f;
        if (length > 125) throw new IOException("demo only supports <=125 bytes");
        byte[] mask = in.readNBytes(4);
        if (mask.length != 4) throw new EOFException("missing frame mask");
        byte[] payload = in.readNBytes(length);
        if (payload.length != length)
            throw new EOFException("truncated WebSocket payload");
        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return new Frame(first & 0x0f, payload);
    }

    static void writeServerFrame(OutputStream out, int opcode, byte[] payload)
            throws IOException {
        if (payload.length > 125)
            throw new IOException("demo frame too large");
        out.write(0x80 | opcode);
        out.write(payload.length); // Server frames are unmasked.
        out.write(payload);
        out.flush();
    }

    static boolean serveOne(ServerSocket listener) throws Exception {
        boolean explicitPongReceived = false;
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5_000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            handshake(in, out);
            while (true) {
                Frame frame = readClientFrame(in);
                switch (frame.opcode()) {
                    case 1, 2 -> writeServerFrame(
                            out, frame.opcode(), frame.data()); // echo
                    case 9 -> writeServerFrame(out, 10, frame.data()); // ping -> pong
                    case 10 -> explicitPongReceived =
                            Arrays.equals(frame.data(),
                                    "ok".getBytes(StandardCharsets.US_ASCII));
                    case 8 -> {
                        writeServerFrame(out, 8, frame.data());
                        return explicitPongReceived;
                    }
                    default -> throw new IOException("unexpected opcode");
                }
            }
        }
    }

    static final class Events implements WebSocket.Listener {
        private final CountDownLatch messages = new CountDownLatch(3);
        private final CountDownLatch closed = new CountDownLatch(1);
        private final StringBuilder text = new StringBuilder();
        private final ByteArrayOutputStream binary = new ByteArrayOutputStream();
        private final AtomicReference<Throwable> failure = new AtomicReference<>();
        private volatile String pong = "";

        @Override
        public void onOpen(WebSocket ws) {
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(
                WebSocket ws, CharSequence data, boolean last) {
            text.append(data);
            if (last) messages.countDown();
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onBinary(
                WebSocket ws, ByteBuffer data, boolean last) {
            byte[] chunk = new byte[data.remaining()];
            data.get(chunk);
            binary.write(chunk, 0, chunk.length);
            if (last) messages.countDown();
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onPong(WebSocket ws, ByteBuffer data) {
            byte[] bytes = new byte[data.remaining()];
            data.get(bytes);
            pong = new String(bytes, StandardCharsets.US_ASCII);
            messages.countDown();
            ws.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(
                WebSocket ws, int statusCode, String reason) {
            closed.countDown();
            return null;
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            failure.compareAndSet(null, error);
            while (messages.getCount() > 0) messages.countDown();
            closed.countDown();
        }

        void check() throws Exception {
            if (failure.get() != null)
                throw new IOException("WebSocket listener failed", failure.get());
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 8, InetAddress.getLoopbackAddress())) {
            listener.setSoTimeout(5_000);
            ExecutorService serverThread = Executors.newSingleThreadExecutor();
            Future<Boolean> serverResult =
                    serverThread.submit(() -> serveOne(listener));
            try {
                Events events = new Events();
                URI uri = URI.create("ws://127.0.0.1:"
                        + listener.getLocalPort() + "/echo");
                WebSocket ws = HttpClient.newHttpClient().newWebSocketBuilder()
                        .buildAsync(uri, events).get(5, TimeUnit.SECONDS);
                try {
                    boolean textDone = ws.sendText("Hello WS", true)
                            .get(5, TimeUnit.SECONDS) == ws;
                    ByteBuffer data = ByteBuffer.wrap(new byte[] {1, 2, 3});
                    boolean binaryDone = ws.sendBinary(data, true)
                            .get(5, TimeUnit.SECONDS) == ws;
                    boolean pingDone = ws.sendPing(ByteBuffer.wrap(
                            "hi".getBytes(StandardCharsets.US_ASCII)))
                            .get(5, TimeUnit.SECONDS) == ws;
                    boolean pongDone = ws.sendPong(ByteBuffer.wrap(
                            "ok".getBytes(StandardCharsets.US_ASCII)))
                            .get(5, TimeUnit.SECONDS) == ws;

                    if (!events.messages.await(5, TimeUnit.SECONDS))
                        throw new IOException("response events timed out");
                    events.check();

                    boolean closeDone = ws.sendClose(
                            WebSocket.NORMAL_CLOSURE, "done")
                            .get(5, TimeUnit.SECONDS) == ws;
                    if (!events.closed.await(5, TimeUnit.SECONDS))
                        throw new IOException("close callback timed out");
                    events.check();
                    boolean serverSawPong =
                            serverResult.get(5, TimeUnit.SECONDS);

                    System.out.println("sendText completed: " + textDone);
                    System.out.println("sendBinary completed: " + binaryDone);
                    System.out.println("sendPing completed: " + pingDone);
                    System.out.println("sendPong completed: " + pongDone);
                    System.out.println("client text: " + events.text);
                    System.out.println("client binary bytes: "
                            + Arrays.toString(events.binary.toByteArray()));
                    System.out.println("client pong payload: " + events.pong);
                    System.out.println("server saw explicit pong: "
                            + serverSawPong);
                    System.out.println("sendClose completed: " + closeDone);
                } finally {
                    ws.abort();
                }
            } finally {
                serverThread.shutdownNow();
            }
        }
    }
}
~~~

### Compile and Run Commands

In the directory containing the file:

~~~bash
javac WebSocketSendKindsDemo.java
java WebSocketSendKindsDemo
~~~

When loopback is working and JDK 17+ supports the WebSocket client, stdout:

~~~text
sendText completed: true
sendBinary completed: true
sendPing completed: true
sendPong completed: true
client text: Hello WS
client binary bytes: [1, 2, 3]
client pong payload: hi
server saw explicit pong: true
sendClose completed: true
~~~

The program has the test `ServerSocket` and the client in the **same JVM**, using an `ExecutorService` for the server so handshake/read/write happen concurrently. Port `0` lets the OS assign a free port. The `get(5, TimeUnit.SECONDS)` calls and latches with timeouts are for **deterministic testing**, not an API requirement that all WebSocket programs must block after every send.

## 10. Analyzing Each Output Line: Send Completion vs. Inbound Receipt Differ

| Output | Signal checked | Exact meaning |
| --- | --- | --- |
| `sendText completed: true` | `ws.sendText(...).get(...) == ws` | Text send future completed normally |
| `sendBinary completed: true` | `ws.sendBinary(...).get(...) == ws` | Binary send completed normally |
| `sendPing completed: true` | `ws.sendPing(...).get(...) == ws` | Ping **was sent**; does not mean Pong was received |
| `sendPong completed: true` | `ws.sendPong(...).get(...) == ws` | Explicit Pong **was sent** |
| `client text: Hello WS` | `Listener.onText` | Client received text **echo from server** |
| `client binary bytes: [1, 2, 3]` | `Listener.onBinary` | Client received binary **echo from server** |
| `client pong payload: hi` | `Listener.onPong` | Client actually received Pong with payload `hi` |
| `server saw explicit pong: true` | Result future from test server | Test server actually read explicit Pong `ok` |
| `sendClose completed: true` | `sendClose` future | Close **was sent**, demo also waits for `Listener.onClose` separately |

In `Events`, `CountDownLatch messages` starts with a value of 3. The text/binary callbacks only call `countDown()` when `last==true`, while Pong counts after copying the payload. This prevents mistakenly counting individual fragments as a complete message.

Why does the demo wait on two different signal sources? `sendPing(...).get(...)` checks **sending the Ping**, whereas `events.messages.await(...)` checks **receiving the Pong and the two echoes**. The separate server future indicates that **the Pong sent manually by the client reached the server**. A real application also needs to separate three layers: send completed, peer response received, and business request committed.

## 11. Send Future Errors and Diagnosis

| Case | Symptom/API | How to handle |
| --- | --- | --- |
| Sending text/binary while a send of this kind is already pending | Future completes exceptionally with `IllegalStateException` | Serialize sends via a queue/`thenCompose` |
| Previous text message had `last=false`, then switching to binary | Future may complete exceptionally with `IllegalStateException` | Properly finish the previous text message first |
| A Ping/Pong send is pending, initiating another control send | Future may complete exceptionally with `IllegalStateException` | Track/serialize control send completion |
| Ping or Pong payload exceeds 125 bytes | `IllegalArgumentException` on send result | Check `ByteBuffer.remaining()` |
| Output closed, I/O error, broken connection | `IOException`/exceptional future | Check connection and cause, clean up |
| `get(timeout)` expires | `TimeoutException` in caller | Do not assume the send stopped or the peer did not receive it |
| `join()` of a failed future | `CompletionException` | Inspect cause; do not swallow the error |
| `sendPing` completes but no `onPong` | Peer may not have replied; listener may lack demand | Check `request(n)`, deadline, errors |
| `sendClose` completes but no `onClose` yet | Two different events | Wait for peer Close when needed, with deadline/cleanup |
| `ws.isOutputClosed()==true` | WebSocket output is closed | Do not send new data |

Do not just wrap `sendText` in `try/catch` and assume you have checked all errors: the operation may **return a future** and only **later complete exceptionally**. Use `whenComplete` or read `get/join` to observe the actual outcome.

## 12. Text/Binary Fragmentation and Ordering

For a two-part text message:

~~~java
ws.sendText("Hello, ", false)
  .thenCompose(socket -> socket.sendText("world!", true))
  .join();
~~~

For a two-part binary message:

~~~java
ws.sendBinary(ByteBuffer.wrap(new byte[] {1, 2}), false)
  .thenCompose(socket -> socket.sendBinary(
          ByteBuffer.wrap(new byte[] {3, 4}), true))
  .join();
~~~

Only when the final part sets `last=true` is the message marked complete. `last=false` does not by itself create a finished message. On the receiving side, the listener must accumulate callbacks until `last=true` and process them as **one** message. Do not switch message types between parts before finishing.

**Do not test these two fragmentation examples directly against the limited server fixture in section 9**, because the test server intentionally only accepts FIN frames and will reject fragmented frames. Use a full WebSocket server or extend the fixture according to RFC 6455 before running.

Control Ping/Pong are a different message type and have no `last`. The JDK automatically replies with Pong when receiving Ping, so avoid sending an extra duplicate Pong just because of the `onPing` callback. Control frames may appear in communication while an application message is being sent in multiple parts; heartbeat and proper ordering must still be handled.

## 13. Closing the Connection: sendClose Is Not onClose

After sending the necessary application messages, you can call:

~~~java
CompletableFuture<WebSocket> closeSent =
        ws.sendClose(WebSocket.NORMAL_CLOSURE, "done");
closeSent.join();
~~~

*Illustrative snippet; does not automatically produce a signal that Close was received from the peer.*

`WebSocket.NORMAL_CLOSURE` is code **1000**, indicating normal termination. The future here checks the **Close send operation**. To know whether **Close was received from the peer**, observe `Listener.onClose(WebSocket, int, String)`. A WebSocket can close its output before its input closes; the `isOutputClosed()`/`isInputClosed()` APIs help observe state, but races and errors must be handled.

`ws.abort()` is an **abrupt** close, typically used for cleanup on error or deadline expiration, not a replacement for `sendClose` in an orderly shutdown procedure. A client after Close/abort must not be reused for further sends; to reconnect, you must create a new WebSocket and clearly decide which requests are safe to replay.

## 14. Backpressure and Send Queues in Real Applications

Multiple producers (UI handlers, heartbeat schedulers, background workers) may want to send over one WebSocket concurrently. A good design needs:

1. **A per-connection outbound queue**, holding message type, payload, requestId, and priority.
2. **No overlapping pending text/binary sends**. Only initiate the next message when the previous future has completed appropriately. `thenCompose` is useful for a simple chain; a queue helps scale to multiple producers.
3. **Limit the number of pending messages and total pending bytes**, avoiding running out of RAM if the network is slow or the peer is not reading.
4. **Distinguish send completion from application ACK**. A successful `sendText` is not enough to mark an RPC as completed.
5. **Separate heartbeat**: wait for a Pong with a matching ID/nonce and deadline; do not use the `sendPing` future as a Pong future.
6. **Layered timeouts**: connect/handshake, send, peer response, heartbeat, and close handshake are distinct conditions.
7. **Controlled shutdown**: stop accepting new messages, process/cancel the queue according to policy, send Close, wait for the peer when needed, then clean up.
8. **Contextual error observability**: log type/size/requestId, cause, and socket state; do not log tokens, passwords, or sensitive payloads.

Because `whenComplete` and listener callbacks may run on runtime-managed threads, avoid blocking/CPU-heavy work directly inside callbacks. When you need to retain received data after a callback, **copy the ByteBuffer/CharSequence according to its lifecycle** before handing it off to another thread.

## 15. Common Misconceptions to Avoid

| Misconception | Why is it wrong? | Correct understanding |
| --- | --- | --- |
| “sendText returns WebSocket immediately” | Returns `CompletableFuture<WebSocket>` | Observe normal/exceptional completion |
| “sendPing completed means the peer is alive” | Only sent the Ping | Wait for `onPong` and match payload/deadline |
| “onPong is the future of sendPing” | It is an inbound callback | Two different signals |
| “Pong is an ACK that the request was processed” | Pong is a control message | Design a separate business ACK |
| “Must manually send Pong in onPing” | JDK automatically sends reciprocal Pong | Only send manually when truly needed |
| “Ping can send 1000 bytes” | Control payload is limited to 125 bytes | Check `remaining()` |
| “ByteBuffer capacity = bytes sent” | Sends from position to limit | Check `remaining()` |
| “Can clear buffer right after sendBinary” | Future may still be pending | Wait for completion first |
| “last=false is a complete message” | Message has not ended | Continue sending until `last=true` |
| “One sendText = one onText callback” | Receiver may get multiple parts | Accumulate until `last=true` |
| “request(1) grants 1 byte” | It grants 1 receive callback | Maintain demand properly |
| “Listener CompletionStage is the send future” | Manages received data lifecycle | Distinguish outbound/inbound |
| “get(timeout) cancels the send” | Only a caller wait timeout | Manage cancel/close separately |
| “sendClose completed = peer has closed” | Does not mean onClose was received | Track peer closure separately |
| “Loopback demo server is production-ready” | Missing many RFC cases | Use a standard server library |
| “ws:// is always as safe as wss://” | ws:// has no TLS | Use wss:// in real deployments |

## 16. Self-Check Questions

**Question 1.** What does `ws.sendText("abc", true)` return? Is the server guaranteed to have saved the data?

*Answer:* Returns `CompletableFuture<WebSocket>`. Normal completion only indicates that the send operation finished; it does not prove the server processed or saved it. A business ACK is required.

**Question 2.** `sendBinary(buffer,true)` was called, but the future is not done yet. Can you call `buffer.clear()`?

*Answer:* No. The buffer is still in use by the send API. Only access it again after completion according to the contract.

**Question 3.** Why is a successful `sendPing` future not enough to record “heartbeat OK”?

*Answer:* Because it does not confirm the client **received a Pong**. You need the `onPong` listener, matching nonce, and a deadline.

**Question 4.** Is it necessary to call `sendPong` immediately in every `onPing`?

*Answer:* Usually no; the JDK WebSocket client automatically emits a reciprocal Pong. Send Pong manually if a test protocol requires it.

**Question 5.** Is `ws.sendText("A",false)` followed immediately by `sendBinary(...)` valid?

*Answer:* The text message has not ended. Do not switch types before finishing; the operation may complete exceptionally with `IllegalStateException`.

**Question 6.** How many messages are `onText(ws,"Xin ",false)` followed by `onText(ws,"chào",true)`?

*Answer:* One complete text message; they must be concatenated into `Xin chào`.

**Question 7.** Why must `request(1)` be called in the listener to receive the next Pong?

*Answer:* Demand is the number of callbacks permitted to be delivered. Without demand, callbacks may not be invoked even when frames arrive.

**Question 8.** Does a successful `sendClose` future mean `onClose` has already been seen?

*Answer:* No. One is send completion, and the other is the event of receiving Close from the peer.

## 17. Practice Exercises

1. Run `WebSocketSendKindsDemo.java`, pointing out the four lines sending text/binary/Ping/Pong and what each `get(5, TimeUnit.SECONDS)` is verifying.
2. Replace `Hello WS` with `Xin chào`, verifying that the text listener still receives Unicode correctly; do not modify the CharSequence before completion.
3. Change binary `[1,2,3]` to `[10,20,30,40]` and verify the exact echoed bytes.
4. Change the Ping payload from `hi` to `probe-42` and compare the payload received in `onPong`; add a heartbeat deadline.
5. Send a 126-byte Ping payload on a **connected client**, handle the future failure in a controlled manner, and explain the 125-byte limit.
6. Implement a bounded queue so multiple producers can sequentially send text/binary, tracking futures and in-flight byte count.
7. Try removing `ws.request(1)` in the listener in a test environment and observe that receive callbacks stop progressing, then restore it.
8. Write an ACK protocol: the client sends text with `requestId=42`, the server only replies `ack:42` **after processing**, and the client does not mark the business operation as succeeded based solely on the send future.
9. Practice fragmentation with `sendText(...,false)` then `sendText(...,true)` **against a full WebSocket server**; the test server in this lesson only supports FIN frames.
10. Add timeout/exception handling from `get` or `whenComplete` and describe how to clean up using `sendClose` or `abort` when needed.
11. Switch from testing `ws://127.0.0.1` to a `wss://` test endpoint with a valid certificate, keeping TLS verification enabled.

## Official References

- [`WebSocket` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/WebSocket.html): sendText, sendBinary, sendPing, sendPong, sendClose, send futures, and receive demand.
- [`WebSocket.Listener` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/WebSocket.Listener.html): onText, onBinary, onPing, onPong, onClose, onError, and inbound CompletionStage.
- [`WebSocket.Builder` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/WebSocket.Builder.html): `buildAsync` and handshake.
- [`CompletableFuture` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/CompletableFuture.html): get, join, thenCompose, whenComplete, exceptions, and timeouts.
- [`ByteBuffer` — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html): position, limit, remaining, and buffer lifetime.
- [RFC 6455 — WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455): framing, client masking, Ping/Pong/Close, and control payload limits.
