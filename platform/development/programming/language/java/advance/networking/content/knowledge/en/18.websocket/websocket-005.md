# WebSocket.Listener with onOpen, onText, onBinary, onClose, onError in Java

**Topic:** Java Advance - networking  
**Group:** WebSocket  
**Technology:** Java 17+, **java.net.http** module, **HttpClient.newWebSocketBuilder()**, **WebSocket.Listener**.

When a Java application connects over WebSocket to receive chat messages, telemetry, stock ticks, or real-time events, **WebSocket.Listener** is the interface that receives callbacks from the JDK's standard **WebSocket client**. The core callbacks include:

- **onOpen(WebSocket)** — the connection has been established; typically starts with **webSocket.request(1)**.
- **onText(WebSocket, CharSequence, boolean last)** — receives a text message that may arrive in multiple parts; **last=true** indicates the end of the message.
- **onBinary(WebSocket, ByteBuffer, boolean last)** — receives a binary message; you must read only the **position..limit** range and manage the buffer.
- **onClose(WebSocket, int statusCode, String reason)** — a Close message has been received; the WebSocket input is closed and this is the final callback for that connection.
- **onError(WebSocket, Throwable error)** — an error occurred, input/output is closed; this is also a final callback.

Two control callbacks, **onPing/onPong**, are essential to know because they also consume **receive demand**. According to the Java Javadoc, **WebSocket.request(n)** does not request n **complete messages**, but rather at most **n receive callback invocations**. A fragmented message can consume multiple onText/onBinary invocations. The **CompletionStage** returned from a callback has a different role: it signals when the callback's data can be reclaimed by the implementation; it is **not** a demand counter.

**Goal:** understand signatures, ordering, fragmentation, flow control, data sources, and closure lifecycle; build a safe listener; run real tests with Java 17 against a test WebSocket server on loopback; distinguish opening handshake failure, normal close, and connection error. Do not use the Java WebSocket client API pretending it is a WebSocket server framework.

## 1. WebSocket and the event flow

Unlike the traditional HTTP request/response model, WebSocket provides a **bidirectional**, typically **long-lived** channel. The client initiates with an **opening handshake**. With WebSocket over traditional HTTP/1.1, the client sends a request with `Upgrade: websocket`, and a valid server responds with **101 Switching Protocols**; thereafter both sides exchange **WebSocket frames** until closed.

~~~text
Java client                                WebSocket server
    |                                            |
    |  HTTP GET + Upgrade: websocket ----------> |
    | <------------- HTTP/1.1 101 -------------- |
    |                                            |
    | -------- WebSocket connection OPEN ------- |
    |                 onOpen                     |
    |                                            |
    | <-------- Text fragments ----------------- |
    |    onText(part,last=false/true)            |
    | <-------- Binary fragments --------------- |
    |    onBinary(buffer,last=false/true)        |
    | <-------- Ping --------------------------- |
    |    onPing, automatic Pong from client      |
    |                                            |
    | <-------- Close(1000,"bye") -------------- |
    |    onClose; client sends Close reply       |
    |                                            |
    |  input/output CLOSED                       |
~~~

**ws://** does not use TLS; **wss://** uses TLS protection. Production should use **wss://**, properly verify certificates/hostnames, and manage authentication, authorization, origin, limits, and logging. The demo uses **ws://127.0.0.1** on loopback to avoid Internet dependency; that is a choice **for learning purposes only**.

**The standard Java API is client-side:** **java.net.http.WebSocket** opens connections and sends/receives WebSocket traffic; **HttpClient.newWebSocketBuilder()** creates a WebSocket.Builder. Java SE does not provide a full production WebSocket server using only WebSocket.Listener. The demo at the end of this article writes a minimal server socket for testing rather than a public production deployment.

## 2. Creating a WebSocket and listener with HttpClient

General pattern:

~~~java
// Snippet: MyListener is an application-defined class.
HttpClient httpClient = HttpClient.newHttpClient();
WebSocket.Listener listener = new MyListener();

CompletableFuture<WebSocket> opening =
        httpClient.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .buildAsync(
                        URI.create("wss://service.example/events"),
                        listener);
~~~

You need to import **java.net.URI**, **java.net.http.HttpClient**, **java.net.http.WebSocket**, **java.time.Duration**, and **java.util.concurrent.CompletableFuture**. **opening** completes with **WebSocket** after a successful opening handshake; it can also **complete exceptionally** due to DNS/connect/TLS/handshake/timeout. **Do not** assume an opening failure is always reported via **onError** of an opened WebSocket. The two phases must have separate handling branches.

The Builder can configure connectTimeout, subprotocols, valid headers, and use HttpClient settings such as proxy/TLS/executor. When using **wss://**, do not disable certificate/hostname verification just to make the connection succeed.

**Opening future ≠ lifecycle future:** a successfully opened WebSocket can receive messages for hours; the application should maintain a separate **CompletableFuture<Void> closed** in the listener, completing normally in **onClose** or exceptionally in **onError**. Every send operation returns its own future, while business acknowledgements require separate application logic.

## 3. Callback table and method contracts

| Callback | Simplified signature | When invoked | Result |
| --- | --- | --- | --- |
| **onOpen** | void onOpen(WebSocket) | WebSocket connected; first callback, at most once | Returns no stage |
| **onText** | CompletionStage<?> onText(WebSocket, CharSequence, boolean) | Text data available | Stage controlling CharSequence lifecycle |
| **onBinary** | CompletionStage<?> onBinary(WebSocket, ByteBuffer, boolean) | Binary data available | Stage controlling ByteBuffer lifecycle |
| **onPing** | CompletionStage<?> onPing(WebSocket, ByteBuffer) | Ping frame received | Stage for control payload |
| **onPong** | CompletionStage<?> onPong(WebSocket, ByteBuffer) | Pong frame received | Stage for control payload |
| **onClose** | CompletionStage<?> onClose(WebSocket, int, String) | Close received; input closed | Stage allowing output close |
| **onError** | void onError(WebSocket, Throwable) | Connection/callback error | Returns no stage; must not throw |

All methods have default implementations because Listener is an interface with **default methods**. However, if you override **onOpen** or receive callbacks without calling **request(n)** appropriately, the app may stop receiving data. **onClose and onError are terminal** for the same WebSocket: after either is invoked, no further callbacks will occur for that connection.

**Callback ordering** is guaranteed by the Javadoc at the **method level**: the next callback for the same WebSocket only starts after the previous callback **returns**. This does not guarantee that **async tasks** started by a callback have finished, and does not guarantee callback ordering between **two different WebSockets** sharing the same listener instance.

## 4. request(long n): counting callback invocations instead of messages

A newly created WebSocket has a **receive counter of 0**. Calling **webSocket.request(n)** with **n > 0** increments the counter by n. Each invocation of a receive method (**onText, onBinary, onPing, onPong, onClose**) decrements the counter by one. **onOpen** and **onError** are not receive methods and therefore do not consume the counter.

~~~text
New WebSocket: demand = 0
   |
   v
onOpen(ws): ws.request(1) -> demand = 1
   |
   v
onText("Hel", last=false) -> demand = 0
     append "Hel"; ws.request(1) -> demand = 1
   |
   v
onText("lo", last=true) -> demand = 0
     append "lo"; complete message "Hello"
     ws.request(1) -> demand = 1
   |
   v
onPing(ByteBuffer "p") -> demand = 0
     ws.request(1) -> demand = 1
   |
   v
onClose(...): final receive callback
~~~

This is an example flow; the Java implementation may fragment text into a different number of onText calls than the raw frames sent by the peer. **last** marks the **end of a message**, not a TCP packet or application chunk boundary that you can predict yourself.

**If you do not request more:** the WebSocket may not invoke further receive callbacks because the counter reached 0. This does not mean the server stopped sending; the system may be held at the backpressure/receive layer.

**request(0) or request(-1):** violates the contract and throws **IllegalArgumentException**. Do not use request(Long.MAX_VALUE) as a default when handling unbounded messages: the application must still manage memory and queues.

### Pitfall when overriding onOpen

~~~java
// WRONG: overrode the default method without creating demand.
@Override
public void onOpen(WebSocket ws) {
    System.out.println("Connected");
}
~~~

~~~java
// CORRECT when the listener is ready to receive the first callback.
@Override
public void onOpen(WebSocket ws) {
    System.out.println("Connected");
    ws.request(1);
}
~~~

According to the Javadoc, the default onOpen calls request(1). Overriding this method prevents the **default behavior from running**, so you must call it again when you want to receive. Default onText/onBinary/onPing/onPong also call request(1); do not forget to grant demand when replacing defaults with custom callbacks.

**Granting demand should match consumer capacity:** a fast listener can request a new turn right after copying/parsing a fragment; a busy listener can wait before requesting more. Avoid granting massive demand while pushing data into an unbounded executor queue, as that is not end-to-end backpressure.

## 5. onOpen: connection open, not necessarily application-authenticated

~~~java
@Override
public void onOpen(WebSocket ws) {
    // Initialize per-connection state and track liveness if needed.
    ws.request(1);
}
~~~

**onOpen** is the first callback, invoked at most once, confirming the WebSocket is connected. However, it does **not** guarantee that the user/application is authorized to subscribe to all channels. A service may require business authentication or a subscription message after the handshake; that is a separate application layer.

If you need to send a message after connecting, use **sendText(...)** and handle its future. Do not block indefinitely inside onOpen waiting on network/database calls; callbacks should be short, time-bounded, and have clear fail/cancel paths.

**Errors before onOpen:** the opening handshake can fail with **WebSocketHandshakeException** or another IOException; if the opening future completes exceptionally, do not wait for onClose of a connection that was never opened. Design separate cleanup for the CONNECTING phase.

## 6. onText: CharSequence, fragments, and boolean last

~~~java
CompletionStage<?> onText(
    WebSocket ws, CharSequence data, boolean last)
~~~

Meaning:

- **data** is the text portion delivered by the callback; the **CharSequence** type is not guaranteed to be immutable like String. The Java implementation guarantees data is a valid UTF-16 sequence.
- **last=false** means there are still remaining parts of the **same message** yet to be delivered.
- **last=true** means the current fragment completes the message. It does not mean the connection is closing.
- **return CompletionStage<?>** signals when the WebSocket is allowed to reclaim data; do not access **data** after the stage completes.
- **ws.request(1)** allows the next callback invocation according to consumer demand.

### Message assembly pattern

~~~java
private final StringBuilder text = new StringBuilder();

@Override
public CompletionStage<?> onText(WebSocket ws,
                                 CharSequence fragment, boolean last) {
    text.append(fragment); // Copy content before stage completion.
    if (last) {
        String message = text.toString();
        text.setLength(0);
        processCompleteText(message);
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

**Snippet** requires defining **processCompleteText** and imports. When the message is JSON, only parse **once the full message is received**; do not expect the parser to receive complete JSON on every fragment. For servers that may send extremely long messages, **enforce a total character/byte limit per protocol**, e.g., reject messages exceeding 1 MiB and initiate Close 1009; do not let StringBuilder accumulate without bound.

If you need to retain **CharSequence** after the returned CompletionStage completes, **copy via toString()** beforehand. Do not pass raw data into a background task and return completedFuture if the task will still read it afterward.

### Relationship between callbacks and raw WebSocket frames

A message may consist of an initial raw text frame and multiple continuation frames. The **onText** callback delivers text data at the Java API level; you should not make a rigid assumption that "each raw frame produces exactly one callback" when designing logic. Use **last=true** to determine when a message is complete; the number of fragments is not stable across networks/implementations.

**last=false** is not "corrupted data" but a normal valid state. **last=true** can appear with an empty fragment terminating a message; parsers should handle empty text messages if the protocol allows them.

## 7. onBinary: ByteBuffer with exact position/limit, do not read array arbitrarily

~~~java
CompletionStage<?> onBinary(
    WebSocket ws, ByteBuffer data, boolean last)
~~~

**ByteBuffer** contains valid bytes in **[position, limit)**. Do not use **capacity()** as the payload size; do not assume **data.array()** exists (the buffer may be direct/read-only). Do not retain a reference to ByteBuffer after the returned CompletionStage completes, unless you have copied the data into owned memory.

### Correct copy pattern

~~~java
byte[] copy = new byte[data.remaining()];
data.get(copy); // Copy exact slice from position to limit.
~~~

For a ByteBuffer with position=5, limit=8, capacity=64, the delivered data is only **3 bytes**, not 64. Calling array() and reading the whole array may read out-of-range bytes or throw UnsupportedOperationException.

### Fragment assembly pattern

~~~java
private final ByteArrayOutputStream payload = new ByteArrayOutputStream();

@Override
public CompletionStage<?> onBinary(WebSocket ws,
                                   ByteBuffer data, boolean last) {
    byte[] chunk = new byte[data.remaining()];
    data.get(chunk);
    payload.writeBytes(chunk);

    if (last) {
        byte[] message = payload.toByteArray();
        payload.reset();
        processBinary(message);
    }
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

**Snippet** requires imports/defining **processBinary**. Use the example above only when a **size cap** is enforced for untrusted data; if binary payloads are large, process them incrementally with bounded buffers or write to a file by design, rather than accumulating in an unbounded ByteArrayOutputStream.

**onText and onBinary need separate state.** A Ping arriving between fragments does not mean a message has completed. Do not reset the accumulator when onPing occurs; reset when **last=true** or when the connection closes/errors.

## 8. CompletionStage<?> and request(n) are two independent mechanisms

A subtle point in the official documentation is that the **returned CompletionStage does not change the receive counter**. The stage from **onText/onBinary/onPing/onPong** signals when the implementation may reclaim the CharSequence/ByteBuffer. **request(n)** is what signals demand for subsequent callbacks. An incomplete stage **does not automatically block** the next callback if the listener has already requested more.

~~~text
onText(fragment A, last=false)
    |
    +-- copy fragment A
    +-- ws.request(1)             (demand granted)
    +-- return pendingStageA      (not yet completed)
              |
              |  work A still processing in background
              v
onText(fragment B, last=true)    (may be invoked)
    +-- process fragment B
    +-- return stage B
~~~

The Javadoc guarantees **non-overlapping method invocations** for the same WebSocket, but does not guarantee that **async work** spawned by those methods will finish in order. Therefore:

1. If processing synchronously and fast: copy data, process, **request(1)**, and return completedFuture.
2. If processing asynchronously using raw data: return an **incomplete stage** until the task finishes, and **do not access data after the stage completes**.
3. If data must outlive the callback lifecycle: copy before stage completion.
4. If ordering is required: use a per-connection queue/serial executor and grant demand accordingly; do not mistake "returning a pending stage" for automatic serialization.
5. If the stage completes exceptionally or the callback throws, the WebSocket may transition to **onError** per contract. Do not use an exceptional stage to report a validation warning that the application wants to ignore.

### What does a null stage mean?

The Javadoc allows onText/onBinary/onPing/onPong to return **null**; the WebSocket treats it as **a normally completed stage**. Returning null is only safe when the implementation is allowed to reclaim the data immediately, with no remaining work needing the buffer/CharSequence. For readability and consistency with async style, the examples use **CompletableFuture.completedFuture(null)**.

### Example of asynchronous data processing with proper ownership

~~~java
@Override
public CompletionStage<?> onBinary(WebSocket ws,
                                   ByteBuffer bytes, boolean last) {
    byte[] safeCopy = new byte[bytes.remaining()];
    bytes.get(safeCopy);
    CompletionStage<?> task = enqueueBounded(safeCopy, last);
    task.whenComplete((ignored, failure) -> {
        if (failure == null) {
            ws.request(1);
        } else {
            ws.sendClose(1011, "Consumer failed");
        }
    });
    return task;
}
~~~

**Non-standalone snippet:** **enqueueBounded** must have a bounded queue, clearly defined backpressure, cancellation, and return a CompletionStage. Copying allows the task to hold data independently of the implementation's ByteBuffer. Understand that the callback will not automatically retry if the task fails, and an exceptional returned stage may lead to onError. If you want to close intentionally instead of producing an exceptional stage, design an explicit error-handling policy.

## 9. onClose: Close message, input closed, and Close reply

~~~java
CompletionStage<?> onClose(
    WebSocket ws, int statusCode, String reason)
~~~

**onClose** is invoked when a Close message is received; **the input side is already closed upon entering the callback**. According to the Java API, this is the **final callback** of that connection. If output is not yet closed, the returned stage determines when the WebSocket may automatically close output/reply with Close. The built-in HttpClient sends an appropriate Close reply (same code, empty reason) when the stage completes.

~~~java
@Override
public CompletionStage<?> onClose(WebSocket ws,
                                  int statusCode, String reason) {
    System.out.println("Closed: " + statusCode + " " + reason);
    closed.complete(null);
    return CompletableFuture.completedFuture(null);
}
~~~

**closed** is a CompletableFuture created by the application. **Completing the application future inside onClose** means the app has received the close message; if you need to ensure the wire reply has been sent, track the operation and test it separately (as in the loopback program in section 12).

### Common Close codes

| Code | Meaning | Notes |
| --- | --- | --- |
| **1000** | Normal Closure | Use **WebSocket.NORMAL_CLOSURE** |
| **1001** | Going Away | Endpoint is going away |
| **1002** | Protocol Error | Protocol violation |
| **1003** | Unsupported Data | Unacceptable data type |
| **1008** | Policy Violation | Disallowed by application policy |
| **1009** | Message Too Big | Message size exceeds limit |
| **1011** | Unexpected Condition | Server encountered unexpected error |
| **1005**, **1006**, **1015** | Reserved / special status descriptors | **Do not send in a Close frame** |

**Reason** must fit the Close frame payload limit: reason has at most **123 UTF-8 bytes** after the 2-byte status code, not 123 Java characters. Do not send arbitrary status codes with **sendClose**; the method has a contract on valid codes.

### sendClose vs. abort

~~~java
ws.sendClose(WebSocket.NORMAL_CLOSURE, "");
~~~

**sendClose(...)** requests closing the **output side** in a protocol-compliant manner; it **does not immediately close the input side**. **ws.abort()** closes both input and output **abruptly** and is used when a graceful close is not possible (for example, peer timeout).

**Warning:** if onClose returns a **CompletionStage that never completes**, it can prevent the automatic reciprocal Close on output; this is explicitly stated in the Javadoc. Use a pending stage in onClose only when genuinely needed, with a timeout and shutdown policy.

## 10. onError: terminal error, do not throw exceptions from callback

~~~java
void onError(WebSocket ws, Throwable error)
~~~

**onError** can occur at any time **after onOpen**, without requiring remaining receive demand. When this callback starts, **both input and output are already closed**. This is the final callback for the connection; no further onClose/onText will occur after onError on the same WebSocket.

~~~java
@Override
public void onError(WebSocket ws, Throwable error) {
    closed.completeExceptionally(error);
    // Log connection ID, exception type, and cause according to security policy.
    // Never throw from onError.
}
~~~

**Do not let onError throw an exception.** The Javadoc states behavior is **undefined** if the onError callback throws. If a logger/metrics/custom hook might throw, isolate it with try/catch or a mechanism that cannot break the callback.

An **opening failure** can cause **buildAsync** to complete exceptionally before the WebSocket opens; do not assume onError replaces the handler for that future. An **exception in onText/onBinary** or an exceptional returned stage can terminate the connection via onError; do not conflate message validation errors with network errors if the application wants to keep running.

### Two valid termination paths

~~~text
Opening future:
  CONNECTING
      +-- failure --> buildAsync exceptionally (may not have onError)
      +-- success --> onOpen --> OPEN
                                  |
                                  +-- onClose --> CLOSED normal
                                  +-- onError --> CLOSED failure
~~~

In production, the application can add CLOSING/RECONNECTING states per contract. Do not allow a connection to have onClose followed by onError because the Javadoc defines terminal callbacks as final.

## 11. onPing/onPong: control frames also require receive demand

Besides the five main callbacks, onPing and onPong are very important. They are **receive methods**, so each invocation also consumes one unit of demand. Ping/Pong frames have a maximum payload of **125 bytes** per the WebSocket protocol.

~~~java
@Override
public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
    byte[] copy = new byte[data.remaining()];
    data.get(copy);
    observePing(copy);
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
~~~

**observePing** is an application function not defined in the snippet. **The JDK WebSocket automatically sends a Pong in reply to Ping** per contract; you do not need to send **ws.sendPong(...)** in a normal onPing. If you override it and forget **request(1)** after Ping, the receive pipeline can run out of demand before the next text/binary arrives.

**onPong** can be used as a heartbeat measurement when the client actively calls **ws.sendPing(...)**; however, a valid Pong does not prove a business operation has completed. Use separate message acknowledgements for business logic and a timeout/reconnection policy to detect half-open connections.

## 12. Complete Java 17 program: testing a real WebSocket.Listener

To avoid depending on an external WebSocket service, the following program creates a **server socket on 127.0.0.1**, returns an opening handshake **101 Switching Protocols** with a valid RFC 6455 **Sec-WebSocket-Accept**, and then emits small frames. The client side still uses **HttpClient.newWebSocketBuilder()** and a **real WebSocket.Listener**, not mock callback calls.

Server scenario:

1. Receive HTTP Upgrade request from Java WebSocket client, extract **Sec-WebSocket-Key**, and compute **Sec-WebSocket-Accept = Base64(SHA-1(key + RFC GUID))**.
2. Send text fragment **Hel** followed by continuation **lo**.
3. Send binary fragments **01 02** and **03 04**.
4. Send Ping with payload **p**; read the Pong automatically sent by the client.
5. Send Close **1000:bye**; read the client's Close reply.
6. Client verifies input/output are closed.

**Note:** the test server intentionally supports only **one connection, short frames <=125 bytes, no TLS, no extensions, and no production hardening**. It is a fixture demonstrating callbacks/flow; do not expose it to the Internet as a real server.

### WebSocketListenerDemo.java

~~~java
import java.io.ByteArrayOutputStream;
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
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketListenerDemo {
    static final class DemoListener implements WebSocket.Listener {
        final CompletableFuture<Void> closed = new CompletableFuture<>();
        final StringBuilder text = new StringBuilder();
        final ByteArrayOutputStream binary = new ByteArrayOutputStream();

        @Override
        public void onOpen(WebSocket ws) {
            System.out.println("onOpen");
            ws.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket ws, CharSequence part,
                                          boolean last) {
            text.append(part); // copy before stage completes
            if (last) {
                System.out.println("onText=" + text);
                text.setLength(0);
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onBinary(WebSocket ws, ByteBuffer part,
                                            boolean last) {
            byte[] copy = new byte[part.remaining()];
            part.get(copy); // only bytes position..limit
            binary.writeBytes(copy);
            if (last) {
                System.out.println("onBinary=" +
                        HexFormat.of().formatHex(binary.toByteArray()));
                binary.reset();
            }
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onPing(WebSocket ws, ByteBuffer data) {
            byte[] copy = new byte[data.remaining()];
            data.get(copy);
            System.out.println("onPing=" +
                    new String(copy, StandardCharsets.UTF_8));
            ws.request(1);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket ws, int code, String reason) {
            System.out.println("onClose=" + code + ":" + reason);
            closed.complete(null);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket ws, Throwable error) {
            closed.completeExceptionally(error);
        }
    }

    record Frame(int opcode, byte[] payload) {}

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        int matched = 0;
        int value;
        while ((value = in.read()) != -1) {
            bytes.write(value);
            if (value == "\r\n\r\n".charAt(matched)) {
                matched++;
                if (matched == 4) break;
            } else {
                matched = value == '\r' ? 1 : 0;
            }
            if (bytes.size() > 16384) throw new IOException("Headers too big");
        }
        if (matched != 4) throw new IOException("Incomplete upgrade request");
        return bytes.toString(StandardCharsets.ISO_8859_1);
    }

    static void upgrade(InputStream in, OutputStream out) throws Exception {
        String headers = readHeaders(in);
        String key = null;
        for (String line : headers.split("\r\n")) {
            if (line.regionMatches(true, 0, "Sec-WebSocket-Key:", 0, 18)) {
                key = line.substring(18).trim();
            }
        }
        if (key == null) throw new IOException("Missing WebSocket key");
        byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                        .getBytes(StandardCharsets.ISO_8859_1));
        String accept = Base64.getEncoder().encodeToString(digest);
        String response = "HTTP/1.1 101 Switching Protocols\r\n"
                + "Upgrade: websocket\r\n"
                + "Connection: Upgrade\r\n"
                + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
        out.write(response.getBytes(StandardCharsets.ISO_8859_1));
        out.flush();
    }

    static void serverFrame(OutputStream out, int header, byte[] data)
            throws IOException {
        if (data.length > 125) throw new IOException("Demo frame too long");
        out.write(header);
        out.write(data.length); // server frames are not masked
        out.write(data);
        out.flush();
    }

    static Frame clientFrame(InputStream in) throws IOException {
        int b0 = in.read();
        int b1 = in.read();
        if (b0 < 0 || b1 < 0) throw new IOException("Missing client frame");
        int size = b1 & 0x7f;
        if ((b1 & 0x80) == 0 || size > 125) {
            throw new IOException("Expected masked short client frame");
        }
        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(size);
        if (mask.length != 4 || payload.length != size) {
            throw new IOException("Incomplete frame");
        }
        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return new Frame(b0 & 0x0f, payload);
    }

    static String serveOnce(ServerSocket listener) throws Exception {
        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();
            upgrade(in, out);

            serverFrame(out, 0x01, "Hel".getBytes(StandardCharsets.UTF_8));
            serverFrame(out, 0x80, "lo".getBytes(StandardCharsets.UTF_8));
            serverFrame(out, 0x02, new byte[] {1, 2});
            serverFrame(out, 0x80, new byte[] {3, 4});
            serverFrame(out, 0x89, "p".getBytes(StandardCharsets.UTF_8));

            Frame pong = clientFrame(in);
            boolean gotPong = pong.opcode() == 10
                    && new String(pong.payload(), StandardCharsets.UTF_8)
                            .equals("p");

            byte[] close = {3, (byte) 232, 'b', 'y', 'e'}; // 1000 + "bye"
            serverFrame(out, 0x88, close);
            Frame reply = clientFrame(in);
            boolean gotClose = reply.opcode() == 8;
            return "serverSawPong=" + gotPong
                    + "\nserverSawClose=" + gotClose;
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket server = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            ExecutorService executor = Executors.newSingleThreadExecutor();
            try {
                Future<String> wireResult = executor.submit(() -> serveOnce(server));
                DemoListener listener = new DemoListener();
                HttpClient client = HttpClient.newHttpClient();
                URI uri = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/demo");
                WebSocket ws = client.newWebSocketBuilder()
                        .connectTimeout(Duration.ofSeconds(3))
                        .buildAsync(uri, listener)
                        .get(5, TimeUnit.SECONDS);
                listener.closed.get(5, TimeUnit.SECONDS);
                System.out.println(wireResult.get(5, TimeUnit.SECONDS));
                System.out.println("inputClosed=" + ws.isInputClosed());
                System.out.println("outputClosed=" + ws.isOutputClosed());
            } finally {
                executor.shutdownNow();
            }
        }
    }
}
~~~

### Compile and run

Create **WebSocketListenerDemo.java** in your practice directory with the code above, using JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 WebSocketListenerDemo.java
java WebSocketListenerDemo
~~~

**Stdout actually tested with javac --release 17 and run on JDK 24.0.2:**

~~~text
onOpen
onText=Hello
onBinary=01020304
onPing=p
onClose=1000:bye
serverSawPong=true
serverSawClose=true
inputClosed=true
outputClosed=true
~~~

**Explanation:**

- **onOpen** occurs when the opening handshake succeeds, then request(1) enables receiving.
- **onText=Hello** shows the listener assembled fragments until **last=true**.
- **onBinary=01020304** shows copying the exact 4 bytes and assembling the binary message.
- **onPing=p** was invoked, while the server confirmed **serverSawPong=true** even though the listener did not manually send a Pong.
- **onClose=1000:bye** notifies normal peer closure; returning a completed stage allowed the close reply, and the server verified **serverSawClose=true**.
- **inputClosed=true/outputClosed=true** were printed after the close reply had been sent.
- **onError** did not occur on this success path; it was declared to complete the lifecycle future exceptionally on error.

**Limitations:** Output is only guaranteed with this fixture/test logic on a compatible JDK/environment; the number of callbacks for a message split into frames may differ, but the example only prints when **last=true**, so no assertion on callback count is needed. The fixture has **no** TLS and **insufficient** checks to expose on a public network.

## 13. Why not write a WebSocket server with java.net.http.WebSocket?

**java.net.http.WebSocket** is a **client** API. The JDK does not provide a production WebSocket server using only this interface. To build a real server, use the WebSocket support of an appropriate server framework or a maintained server implementation tested for RFC compliance, TLS, auth, compression, limits, proxy/ingress, shutdown, and denial-of-service controls.

The ServerSocket fixture above only uses SHA-1 for **Sec-WebSocket-Accept** per the RFC 6455 handshake; this is **handshake validation**, not password hashing or confidentiality proof. It only supports small frames and does not handle all errors/extensions. Do not treat "SHA-1 in the opening handshake" as a security mechanism replacing TLS.

## 14. Sending data: sendText/sendBinary differ from receive callbacks

**webSocket.sendText(CharSequence, boolean last)**, **sendBinary(ByteBuffer, boolean last)**, and **sendClose(code, reason)** return a **CompletableFuture<WebSocket>** for the send operation. This future completes when the send operation finishes according to the JDK; it does **not** prove the peer application has processed the message.

~~~java
// Snippet: ws is a connected WebSocket.
ws.sendText("Hello ", false)
  .thenCompose(s -> s.sendText("WebSocket", true))
  .join();
~~~

~~~java
// Snippet: chain two binary send parts in order.
ws.sendBinary(ByteBuffer.wrap(new byte[] {1, 2}), false)
  .thenCompose(s -> s.sendBinary(
          ByteBuffer.wrap(new byte[] {3, 4}), true))
  .join();
~~~

**last=false** when sending means the message is not yet complete; **last=true** ends the message. Use **thenCompose** to serialize two related send operations. Do not fire-and-forget multiple sends of the same type while a pending send is disallowed by the API state. **Receive request(1)** does not control the number of bytes allowed to be **sent**.

For important business events, the application needs its own **message ID + acknowledgement/deduplication**. When a connection drops between send and server persistence, the send future alone cannot answer "did the server commit?". Do not unconditionally resend non-idempotent operations.

## 15. Production patterns: state management, closing, reconnecting

A long-lived listener should have at least:

- **Per-connection state:** text/binary accumulators, lifecycle future, request IDs, event queue, identity/subscription state.
- **Body/message limits:** max UTF-8/text length, max binary bytes, max fragments, bounded queues; reject or close on abuse.
- **Receive demand strategy:** request one or a few turns only when the pipeline has room; do not forget demand after Ping/Pong.
- **Fragment completion:** parse schema after **last=true**, reset accumulator at the right time, do not let ping wipe state.
- **Error semantics:** handshake failure from buildAsync; onError from established WebSocket; error stage from sends; business validation errors.
- **Timeouts:** connect timeout, idle timeout, close-handshake timeout, application ack deadline; do not wait for the peer indefinitely.
- **Graceful shutdown:** send Close 1000 when appropriate, wait for input Close, fall back to **abort** if timed out.
- **Reconnect:** exponential backoff with jitter, attempt limits, auth refresh, protocol-level subscription/cursor recovery; the Java API does not reconnect for you.
- **Security:** wss://, certificate trust/hostname verification, auth/permissions, origin/subprotocol validation, no secret logging.
- **Monitoring:** active connections, callback counts, message bytes, fragment counts, queue depth, close codes, failures, reconnect attempts, latency, and idle times.

### Different futures for different goals

~~~text
openingFuture: CompletableFuture<WebSocket>
   - succeeds when upgrade/connection is ready
   - fails when opening handshake fails

lifecycleFuture: CompletableFuture<Void>
   - completes normally on onClose
   - completes exceptionally on onError

sendFuture: CompletableFuture<WebSocket>
   - completes a send operation

businessAckFuture: CompletableFuture<Result>
   - follows application-level ack message
~~~

Avoid using **openingFuture.isDone()** to declare that the WebSocket is closed or has finished processing all messages. Avoid using **sendFuture completion** as a substitute for a business acknowledgement. If a listener is shared across multiple WebSockets, manage **per-socket state** because callbacks from different connections can run concurrently.

## 16. Common implementation mistakes

| Mistake | Consequence | Correct approach |
| --- | --- | --- |
| Overriding **onOpen** and forgetting request(1) | Connected, but no onText arrives | Create demand explicitly |
| Calling request(1) only once | Receiving stops after one callback | Grant more demand based on capacity |
| Assuming request(1) means one message | Missing fragments | Assemble until **last=true** |
| Parsing each onText fragment as complete JSON | Parse errors/incomplete data | Parse only when complete |
| No size limit on text/binary messages | Out of memory | Max bytes/chars + Close 1009 |
| Using ByteBuffer.array() | Wrong slice, throws on direct buffer | Use remaining()/get(copy) |
| Retaining CharSequence/ByteBuffer after stage completes | Data may be reclaimed | Copy beforehand or keep stage pending properly |
| Assuming an incomplete stage blocks callbacks | Async tasks race | Grant demand intentionally + serial execution |
| Overriding onPing without requesting | Receiving stops after control frame | Grant demand again |
| Always sending Pong manually in onPing | Duplicate Pong | Java client replies with Pong automatically |
| Returning a never-completing stage from onClose | Close reply may not be sent | Complete stage or apply timeout |
| Assuming sendClose closes input too | Input remains open waiting for peer | Wait for onClose or abort after deadline |
| Throwing an exception from onError | Undefined behavior | onError must not throw |
| Only waiting on onError when buildAsync fails | Missed opening errors | Monitor the opening future |
| Sharing mutable accumulators across sockets | Races between connections | Per-connection state |
| Confusing HTTP status from Upgrade failure with Close code | Wrong layer diagnosis | Separate opening handshake and WebSocket close |
| Treating sendText future done as server commit | Wrong duplicates/retries | App ack and deduplication |

## 17. Testing and diagnostics

### Connection opens but no data arrives

Check whether the listener called **request(n)** in onOpen, whether a previous onPing/onPong callback consumed demand, whether the server has accepted the subscription, and whether synchronous code is blocking the callback. Do not conclude "the server isn't sending" just because onText has not appeared.

### Wrong binary bytes

Print **data.position()**, **data.limit()**, and **data.remaining()** in your test environment and ensure you only copy **remaining()** bytes. Do not retain data after stage completion. Check fragments and message framing in the application protocol.

### Error occurs after a callback

Check whether the callback threw or returned an exceptional stage. Separate parser/domain validation (which may continue if policy allows) from protocol/network failure (onError/close). Do not issue unbounded requests in the error path.

### onClose ran but output is still open

Check whether onClose's **CompletionStage** completes and whether the application is actively calling sendClose/abort or holding a pending future indefinitely. onClose arrives when input closes; output may be waiting on separate close logic.

### onError does not appear when connection fails

Check the **CompletableFuture<WebSocket>** from **buildAsync**: opening handshake errors are recorded on this future. onError is not the way to catch DNS/TLS/HTTP 101 errors before a WebSocket is connected.

### Peer disappears, no onClose seen

This may be a network failure reported via onError, or an undetected half-open path. Implement an idle timeout, Ping/Pong liveness, retry/backoff, and proper cleanup. Do not allow the app to wait indefinitely without a deadline.

## 18. Exercises

1. Write a listener with only **onOpen/onText**. Why is **ws.request(1)** needed in onOpen and on each subsequent turn?
2. A text message is delivered across 3 callbacks with **last=false,false,true**. How do you assemble the JSON correctly?
3. A binary buffer has position=3, limit=7, capacity=64. How many valid bytes are there? Why can array() be wrong?
4. Compare **request(1)** and the returned **CompletionStage**. Does an incomplete stage automatically prevent the next callback?
5. If you must process a fragment on another executor, when must you copy CharSequence/ByteBuffer? When is the stage completed?
6. Does **onPing** consume demand? Does the Java client send Pong automatically or must you call sendPong?
7. Explain the differences between **onClose** and **onError** regarding input/output, terminal callback, and status/reason.
8. Why does **sendClose(1000,"")** not mean input is closed? When is abort necessary?
9. If **onClose** returns a CompletableFuture that never completes, what happens to the reciprocal close behavior?
10. Why can WebSocket opening **buildAsync** fail without the listener receiving onError as you might expect?
11. Run **WebSocketListenerDemo.java** and change the binary fragments to verify **onBinary** assembles them correctly.
12. Withhold demand after onOpen in the fixture; describe the expected hang/test timeout and how to avoid tests running forever.
13. Use the same listener instance for two WebSockets. How do you keep state separate and avoid races?
14. Propose a reconnect policy with jitter and max attempts, along with how to deduplicate business events.
15. Design a server that abruptly closes TCP after onOpen to test onError; do not assert a fixed exception class across all JDKs/networks.
16. Add an app-level acknowledgement for sendText and distinguish sendFuture completion from actual acknowledgement.

## 19. Code review checklist

- [ ] Does the opening future handle errors separately?
- [ ] Does onOpen call request(n) properly?
- [ ] Does onText assemble messages until last=true?
- [ ] Does onBinary copy exact position..limit?
- [ ] Are there limits on message size, time, and memory?
- [ ] Is data not retained after the returned CompletionStage completes?
- [ ] Is demand request(n) understood as separate from stage completion?
- [ ] Do onPing/onPong overrides still grant demand if continuing?
- [ ] Are duplicate Pongs avoided when the implementation already replies?
- [ ] Does onClose complete its stage in a controlled way and clean up resources?
- [ ] Is sendClose not confused with full-duplex termination?
- [ ] Does onError avoid throwing and complete the lifecycle future?
- [ ] Is per-connection state thread-safe if the listener is shared?
- [ ] Are sends tracked via their future and business acknowledgement?
- [ ] Is wss:// used for real applications with a reconnect/timeout policy?

**Conclusion:** WebSocket.Listener is the callback interface for receiving WebSocket events in the Java HTTP client. **onOpen** starts the flow and grants demand; **onText/onBinary** receive message fragments, which must be assembled until **last=true**; **onClose** notifies of a Close frame and ends input; **onError** terminates the connection due to an error. **request(n)** controls the number of callbacks received; **CompletionStage<?>** controls the callback data lifecycle — **they do not replace each other**. A proper listener must manage **fragments, ByteBuffer ownership, demand, closure, error handling, async work, and resources** rather than just logging each event.

### Official documentation

- [WebSocket.Listener — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [WebSocket — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html)
- [WebSocket.Builder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
