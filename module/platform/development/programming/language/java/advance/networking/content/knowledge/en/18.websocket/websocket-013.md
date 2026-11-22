# JDK WebSocket Client API Boundaries and How to Build a WebSocket Server in Java

## 1. Architectural Conclusion Before Writing Code

**JDK 17+ has a standard WebSocket _client_ API in the `java.net.http` module; it does not provide a corresponding high-level WebSocket _server_ API in this module.** Therefore, creating a client that connects to `wss://...` can use the built-in JDK classes, whereas **listening for and serving multiple WebSocket clients** typically requires a **server framework or WebSocket implementation** such as Jakarta WebSocket in a container, Spring WebSocket, Jetty, Netty, or a suitable RFC 6455-compliant library.

Distinguish the two responsibilities:

~~~text
                Java 17+ client application
                       |
       HttpClient.newWebSocketBuilder()
                       |
       WebSocket.Builder.buildAsync(...)
                       |
          java.net.http.WebSocket
                       |
          ws:// or wss://
                       |
            proxy/load balancer
                       |
          WebSocket server endpoint
           (Jakarta / Spring / Jetty /
            Netty / suitable library)
                       |
        validation, authorization,
        message handlers, state,
        pub/sub, backpressure, storage
~~~

**`HttpClient.newWebSocketBuilder()` does not turn an `HttpClient` into a server.** `HttpClient` actively **makes outbound connections** and has no `accept()` to receive incoming WebSocket connections. Conversely, `java.net.ServerSocket` knows how to accept TCP connections but **does not implement the WebSocket protocol itself**. `com.sun.net.httpserver.HttpServer` helps write a simple HTTP server, but does not provide a high-level RFC 6455 WebSocket server endpoint equivalent to `java.net.http.WebSocket`.

Lesson objectives:

1. Accurately identify which standard Java classes are **client-only** and which responsibilities belong to the **server**.
2. Understand the handshake, masking, frames, fragmentation, Ping/Pong, Close, and authentication milestones that the server must handle.
3. Choose an appropriate server stack: **Jakarta WebSocket**, Spring, Jetty/Undertow, Netty, or a tested implementation.
4. Read and run a **standalone JDK 17+** example: a standard client calling a small loop server written with `ServerSocket` solely to **illustrate the boundary**.
5. Understand the limitations of the demo server and do not copy it as a production server.
6. Properly design security, resource quotas, session state, backpressure, reconnect, and scaling.

## 2. What JDK 17 Provides — and What It Does NOT Provide

| Need | API available in JDK 17? | Notes |
| --- | --- | --- |
| Synchronous/asynchronous HTTP client | **Yes**: `HttpClient` | `send`, `sendAsync` |
| WebSocket **client** | **Yes**: `java.net.http.WebSocket` | Handshake, sending text/binary/Ping/Close, callbacks |
| WebSocket client builder | **Yes**: `HttpClient.newWebSocketBuilder()` | Configures URI, timeout, subprotocol/headers per the API |
| WebSocket client event callbacks | **Yes**: `WebSocket.Listener` | `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose`, `onError` |
| TCP listening socket | **Yes**: `ServerSocket`/`ServerSocketChannel` | TCP only, does **not** understand WebSocket handshake/frames on its own |
| Small HTTP server for demos | **Yes**: `com.sun.net.httpserver.HttpServer` | No built-in high-level WebSocket server API |
| Jakarta's `@ServerEndpoint` | **Not part of JDK `java.net.http`** | Requires Jakarta WebSocket API + server implementation/container |
| Spring WebSocket/Netty/Jetty server | **Not included in the JDK** | External libraries/frameworks requiring dependencies and runtime |
| Multi-node messaging, rooms, event persistence | **Not automatically provided by the WebSocket API** | Belongs to the application/broker/database architecture |
| Automatic message ACK, exactly-once across reconnect | **No** | The application must define its own request IDs/cursors/transactions |

**Important boundary:** the JDK WebSocket client can **connect to and exchange messages with a standard server**, rather than turning Java SE into a WebSocket hosting framework. The JDK itself has enough TCP, I/O, and crypto primitives to **write** an implementation from scratch, but doing so requires full RFC 6455 compliance and a host of security/operational duties.

### 2.1. Do Not Confuse the Three Package Groups

- `java.net.http.HttpClient` and `java.net.http.WebSocket`: standard HTTP/WebSocket **client** in the `java.net.http` module.
- `java.net.ServerSocket`, `java.nio.channels.ServerSocketChannel`: **TCP listener** primitives, with no WebSocket semantics.
- `jakarta.websocket.*` and `jakarta.websocket.server.*`: WebSocket API used with a Jakarta-compatible implementation/runtime, featuring the concept of **server endpoints**. These packages **do not appear automatically when only the JDK is installed**.

Some legacy projects use `javax.websocket.*` from earlier Java EE/Jakarta versions; modern Jakarta EE projects typically use `jakarta.websocket.*`. **Do not mix the two namespaces** in code/dependencies without knowing which version your container supports.

## 3. How Do the Roles of WebSocket Client and WebSocket Server Differ?

### 3.1. Client: Actively Connects Outbound

The client knows a URI such as `wss://chat.example.test/live`, creates an **opening handshake**, verifies the upgrade response, and then exchanges WebSocket messages. With JDK 17:

~~~java
HttpClient client = HttpClient.newHttpClient();

WebSocket socket = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .buildAsync(URI.create("wss://chat.example.test/live"),
                    listener)
        .join();
~~~

This is a **non-standalone illustration snippet**; `listener` is a declared `WebSocket.Listener`, and imports `java.net.URI`, `java.net.http.*`, and `java.time.Duration` are required. In an async app, do not use `join()` to block the UI/event loop; chain with `thenAccept`/`thenCompose` where appropriate.

The client API is responsible for **client-side** WebSocket details, such as generating the handshake key, verifying `Sec-WebSocket-Accept`, encoding/decoding frames, **masking outbound client frames**, handling control frames per the API, and dispatching events to `Listener`. The client must still handle **message content, schema, permissions, retries, and application state** itself.

### 3.2. Server: Passively Accepts and Maintains Many Sessions

The server must:

1. **Listen** on a port/route and accept HTTP Upgrade requests (or other handshakes supported by standards/infrastructure).
2. **Validate** the method, headers, WebSocket version, key, origin/auth, and session count limits.
3. **Accept/reject the handshake**, and if accepted, return a valid response and switch the socket to WebSocket framing.
4. **Handle many concurrent connections**, per-connection state, listener lifecycle, and message size/rate limits.
5. **Read/write frames**, handle fragmentation, masking, control frames, UTF-8, and proper close handshakes.
6. **Route messages** to business logic, check authorization on every operation, and send responses/events/fan-out.
7. **Manage slow clients**, outbound queues, timers, idle timeouts, errors, and graceful shutdown.
8. **Integrate with infrastructure**, TLS/WSS, reverse proxies, load balancers, brokers, and observability.

These responsibilities are **not automatically solved** by a `ServerSocket.accept()`. Therefore, choose a battle-tested server implementation instead of building handlers from TCP primitives for Internet-facing applications.

### 3.3. WebSocket Is Not Infinitely Re-sent HTTP CRUD

After the HTTP/1.1 `101 Switching Protocols` handshake, messages are **WebSocket frames**, not new `GET/POST` requests over the same connection. Business logic wanting "create/update/subscribe" must have an application protocol, for example:

~~~json
{"type":"subscribe","channel":"orders/123","requestId":"req-41"}
{"type":"subscribed","channel":"orders/123","requestId":"req-41"}
{"type":"order.updated","channel":"orders/123","sequence":782,"status":"packed"}
~~~

This is an **application-designed JSON envelope**, not a format mandated by RFC 6455. WebSocket itself provides **message boundaries and transport framing**, not database transactions, API authorization, JSON schemas, or durable subscriptions.

## 4. JDK Client API: How to Build a Connection Properly

### 4.1. `WebSocket.Builder` and `buildAsync`

~~~java
CompletableFuture<WebSocket> opened =
        HttpClient.newHttpClient()
                .newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .subprotocols("chat.v1")
                .buildAsync(URI.create("wss://example.test/room"),
                            listener);
~~~

This is an **illustrative snippet** with a declared listener; it imports `java.net.http.*`, `java.net.URI`, `java.time.Duration`, and `CompletableFuture`. `buildAsync` returns a future that completes with `WebSocket` after a successful handshake, or fails when the handshake/network/TLS is invalid.

`subprotocols("chat.v1")` **proposes** an application subprotocol; the server must agree and respond validly. Do not confuse subprotocols with the HTTP `Content-Type` header, and do not treat a subprotocol name as proof that the client is authorized.

For certain valid custom HTTP headers, the builder provides `header(name, value)`. Do not manually set **JDK-controlled handshake headers** such as `Sec-WebSocket-Key`/`Upgrade` arbitrarily; certain headers are rejected by the API or must be managed by the handshake engine. The header customization capabilities of the **Java client** also differ from the browser `WebSocket` API.

### 4.2. `WebSocket.Listener`: Callbacks and Receive Demand

~~~java
WebSocket.Listener listener = new WebSocket.Listener() {
    @Override
    public void onOpen(WebSocket ws) {
        ws.request(1);
    }

    @Override
    public CompletionStage<?> onText(
            WebSocket ws, CharSequence data, boolean last) {
        System.out.println("chunk=" + data + ", last=" + last);
        ws.request(1);
        return null;
    }

    @Override
    public void onError(WebSocket ws, Throwable error) {
        error.printStackTrace();
    }
};
~~~

This is an **illustrative fragment**, requiring imports `java.net.http.WebSocket` and `java.util.concurrent.CompletionStage`. The listener receives events **asynchronously**. The `request(n)` method regulates the number of callbacks requested to process incoming data; if the application does not signal appropriate demand, subsequent callbacks may not be delivered as expected.

**Do not misunderstand `request(1)`**: it does not send a WebSocket application request to the server, nor does it mean "request one chat message" in the business protocol; it is the **receive demand** of the Java client Listener. If the workload requires slow processing, throttle further requests using a bounded queue/executor rather than calling `request(Long.MAX_VALUE)` and buffering messages unboundedly.

### 4.3. Text Messages Can Be Split Across Multiple Callbacks

The `boolean last` parameter of `onText` only indicates the **final part of a single text message**, not the end of the connection. A message may arrive in multiple chunks:

~~~text
onText(ws, "order.", false)
onText(ws, "updated", true)
=> one application message: "order.updated"
~~~

A JSON parser should **accumulate per session until `last=true`**, then validate the entire message. Do not assume each callback invocation is a complete JSON payload, and do not use an unbounded `StringBuilder` against a malicious sender.

### 4.4. Send Methods

~~~java
// With ws being a connected WebSocket:
ws.sendText("hello", true);
ws.sendBinary(ByteBuffer.wrap(new byte[]{1, 2, 3}), true);
ws.sendPing(ByteBuffer.wrap(new byte[]{7}));
ws.sendClose(WebSocket.NORMAL_CLOSURE, "done");
~~~

This is a **snippet illustrating individual APIs**, not advice to call all four sequentially in a production program. `sendText` and `sendBinary` return futures; data can be sent in multiple fragments, and the `last` parameter indicates the end of the **message**, not the end of the socket. `sendPing` is for a control frame with a maximum RFC payload of **125 bytes**. `sendClose` initiates the close handshake.

**Completion of `sendText` does not prove the server committed the business operation.** If you send `{"type":"payment.capture"}`, to know whether processing succeeded you must wait for an **application ACK/status** with a request ID. TCP/WebSocket delivery also does not provide exactly-once semantics across reconnects.

### 4.5. Sending Multiple Fragments in Order

~~~java
CompletableFuture<WebSocket> sent =
        ws.sendText("hel", false)
          .thenCompose(ready -> ready.sendText("lo", true));
~~~

Illustrative snippet with a connected `ws`. The chain above creates **a single text message "hello"** from two parts and serializes the sends. Do not issue two sends concurrently and assume every implementation will order them as you expect; manage a per-connection writer/queue when there are multiple producers.

### 4.6. `onClose` and `onError` Do Not Replace Application State

`onClose(ws, statusCode, reason)` observes the close handshake, and `onError(ws, error)` handles failures. A peer that drops off the network may not send a valid Close frame. The application needs timeouts, reconnects, and state recovery; close code **1000** means normal closure at the protocol level, not proof that preceding commands were successfully persisted.

## 5. Server-Side WebSocket Handshake: Some Things Frameworks Must Do

### 5.1. Starting from HTTP/1.1 Upgrade

An illustrative opening handshake:

~~~http
GET /ws HTTP/1.1
Host: chat.example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://chat.example.test
~~~

If accepted, the server responds:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

`Sec-WebSocket-Accept` is:

~~~text
Base64(SHA-1(
    Sec-WebSocket-Key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
))
~~~

The key and accept value above are the well-known example from **RFC 6455**. **SHA-1 here only serves handshake/protocol verification**, not message encryption, password hashing, or identity proof. For sensitive data, use **`wss://` over TLS** and application-layer authentication/authorization.

### 5.2. Checks the Server Must Treat as Real Responsibilities

Before accepting:

- Valid HTTP method and version for the handshake, and the correct request target/route.
- `Upgrade: websocket` and `Connection` containing the corresponding tokens per header syntax.
- `Sec-WebSocket-Version: 13` and `Sec-WebSocket-Key` with valid format/structure; reject missing keys or invalid values.
- Origin matching browser application policy; valid cookies/sessions/tokens/credentials.
- Allowed route/subprotocol; if negotiating `Sec-WebSocket-Protocol`, the server only selects a value proposed by the client and supported by the server.
- Rate/count limits on connections/handshakes and header sizes; infrastructure-level anti-amplification/DoS protection.
- Trusted TLS/proxy forwarding context; do not rely on spoofed headers from a public client.

This is **not yet an exhaustive list of all RFC 6455 rules**; let a tested server framework handle framing/handshake and use application hooks for authentication/authorization.

### 5.3. HTTP/2 Does Not Just Copy the Upgrade Header

RFC 6455 WebSocket over HTTP/1.1 uses `101 Switching Protocols`. RFC 8441 defines a way to bootstrap WebSockets over **HTTP/2 extended CONNECT** in supporting environments; you **cannot** copy HTTP/1.1's `Upgrade: websocket` verbatim into HTTP/2 and treat it as equivalent. Do not assume the Java 17 client, proxy, and server all support this HTTP/2 option. In operations, explicitly verify which protocol/stack is actually being used.

## 6. Server After the Handshake: Not Just Receiving a String

After the handshake, WebSocket no longer exchanges ordinary HTTP requests/responses over that connection. The server must handle **frames**, fragmentation, control messages, and lifecycle.

| Aspect | What the server must do properly |
| --- | --- |
| Text frame `0x1` | Read payload, validate UTF-8 of the text message, reassemble continuations |
| Binary frame `0x2` | Receive bytes and pass them to the parser per application schema |
| Continuation `0x0` | Reassemble fragmented messages in order within size limits |
| Close `0x8` | Validate code/reason, reply to close handshake, clean up |
| Ping `0x9` / Pong `0xA` | Follow control frame limits, detect liveness |
| Client frame masking | **Client → server must be masked** per RFC 6455 |
| Server frames | **Server → client is unmasked** per RFC 6455 |
| Extended payload lengths | Properly handle 7-bit, 16-bit, 64-bit forms and practical limits |
| Message boundaries | Do not mistake a single TCP read for a full WebSocket message |
| Compression/extensions | Negotiate properly, bound inflate/decompression |
| Backpressure | Do not queue responses/events unboundedly for slow clients |
| Closing on errors | Return valid close/error when possible; release resources exactly once |

### 6.1. Why One `Socket.read()` Is Not Equivalent to `onMessage(String)`

TCP is a **byte stream**, whereas WebSocket defines **message/frame structure**. One `InputStream.read(buffer)` might receive half a frame header, multiple frames at once, or a small portion of a payload. The server must parse **according to the bytes actually received**, rather than assuming every read yields exactly one message.

In production, use an implementation that supports partial network reads, fragmentation, extended lengths, UTF-8 validation, and max sizes. A parser that "reads the first byte, the second byte, then reads exactly N bytes" only works for **a very narrow subset of frames** in a demo.

### 6.2. Masking Is Not Encryption

A client frame carries a 4-byte masking key, and the payload on the wire is XORed with the key per the RFC. The server unmasks it to recover the bytes. It **does not provide confidentiality** and does not replace TLS/WSS. Malicious code can easily send properly masked frames; masking also **does not prove who sent the frame**.

### 6.3. One WebSocket, Many Business Messages

The server needs to distinguish:

~~~text
FRAME -> MESSAGE -> PARSE -> VALIDATE -> AUTHORIZE -> COMMAND/EVENT
                                 |
                                 +-> store/queue/service
                                 |
                                 +-> response/ack / fan-out
~~~

Clearly separating **wire transport** from **business semantics** makes debugging easier: receiving all bytes on the socket does not mean the request is authorized; a network-layer ACK does not mean a database transaction has committed.

## 7. Choosing a WebSocket Server Implementation in Java

### 7.1. Jakarta WebSocket: Container-Based Endpoint/Event Model

The Jakarta WebSocket API defines annotations/types to implement WebSocket endpoints. An **illustrative** server endpoint example:

~~~java
import jakarta.websocket.OnMessage;
import jakarta.websocket.server.ServerEndpoint;

@ServerEndpoint("/echo")
public class EchoEndpoint {
    @OnMessage
    public String onMessage(String message) {
        return "echo:" + message;
    }
}
~~~

**This snippet does NOT compile with plain JDK 17 alone.** It requires the Jakarta WebSocket API and a **supporting server runtime/container** (with matching namespace/dependency versions), such as a Jakarta-compatible container or corresponding library. Handshake/frame implementation is handled by the runtime; `@OnMessage` only processes text already decoded by the framework.

In production, you still need auth/Origin, schemas, size limits, concurrency, outbound handling, metrics, and container configuration. `@ServerEndpoint` does not make user data safe by default.

### 7.2. Spring WebSocket

If the application is Spring Boot, you can use Spring WebSocket handlers/`WebSocketHandler` or STOMP messaging with a broker relay depending on the design. Spring helps integrate the HTTP handshake, interceptors, security, session handlers, and container operations.

**STOMP is not a mandatory part of WebSocket.** It is an **application messaging protocol** that can run over WebSocket; use it when you need its topics/subscribe/ack model, and do not turn on STOMP just to echo two text strings.

Both Spring WebSocket and Jakarta WebSocket require **dependencies and a runtime outside Java SE**, and endpoint/proxy configuration depends on the version. Do not label a snippet as standalone Java SE when it actually requires a server container.

### 7.3. Jetty / Undertow / Netty and Low-Level Choices

- **Jetty, Undertow:** suitable HTTP/WebSocket server implementations if the system uses an embedded server, servlet/HTTP integration, or corresponding runtime.
- **Netty:** powerful event-driven networking framework when you need fine-grained control over the I/O pipeline, frame handlers, TLS, high throughput, and protocol-specific codecs.
- **Jakarta-based servers:** suitable for Jakarta EE environments and the official endpoint model.
- **Rolling your own with `ServerSocket`:** should only be considered for **lessons, protocol research, or cases with very high security-testing capability**, not as the default choice for a public service.

Choose a framework based on **maintenance/security updates**, version compatibility, Java runtime, WebSocket extensions, observability, TLS/proxy support, backpressure API, load profile, and the operations team. There is no single choice that is always right for every product.

### 7.4. Quick Decision Guide

| Scenario | Where to start |
| --- | --- |
| Writing a Java client to call a WebSocket service | `java.net.http.WebSocket` from JDK 17 |
| Writing an endpoint for a Jakarta EE application | Jakarta WebSocket + implementation/container |
| Application already uses Spring Boot | Spring WebSocket or appropriate Spring messaging |
| Custom server networking, high traffic | Evaluate Netty/Jetty/Undertow and benchmarks |
| Building a demo to explain handshake/frames | Plain `ServerSocket` with **explicitly stated limits** |
| Only need one-way notifications from the server | Consider SSE instead of WebSocket |
| Only HTTP CRUD or file uploads | HTTP/REST/streaming, no WebSocket session needed |
| Need durable messaging/exactly-once | Add a broker/database/business protocol; WebSocket alone is not enough |

## 8. Standalone Java 17+ Example: JDK WebSocket Client and Low-Level Demo Server

This example intentionally shows the **boundary very clearly**: the **client** uses the official JDK WebSocket API; the **server** must manually perform part of the handshake and frame parsing using `ServerSocket` because the JDK does not provide an equivalent high-level server endpoint.

The demo opens exactly **one connection** on `127.0.0.1`. After a successful handshake:

1. **The server proactively sends** the text message `server-ready` as soon as the session opens.
2. **The client receives the server push**, then sends the text `client-hello`.
3. **The server unmasks the client frame**, and sends back `ack:client-hello`.
4. The client sends Close with code `1000`, the server echoes the Close frame, the futures complete, and the sockets close.

On the server side, the code **only accepts a single frame with FIN=1, payload ≤125 bytes, RSV=0, and client mask**. It does **not** handle extended lengths, binary, fragmented messages, ping/pong, WSS, Origin, authentication, all HTTP handshake edge cases, or multiple clients. **THIS IS NOT A FULL-FEATURED SERVER / DO NOT DEPLOY TO THE INTERNET.**

Save the entire code as **WebSocketApiBoundaryDemo.java**:

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
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.TimeUnit;

public class WebSocketApiBoundaryDemo {
    record Frame(int opcode, byte[] payload) {}

    // Read HTTP/1.1 request headers up to CRLFCRLF (demo limits to 8192 bytes).
    static String readHttpHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        int tail = 0;
        for (int c; (c = in.read()) != -1;) {
            buffer.write(c);
            if (buffer.size() > 8192) {
                throw new IOException("HTTP headers too large");
            }
            tail = (tail << 8) | c;
            if (tail == 0x0d0a0d0a) {
                return buffer.toString(StandardCharsets.ISO_8859_1);
            }
        }
        throw new EOFException("HTTP upgrade incomplete");
    }

    static String requiredHeader(String request, String name)
            throws IOException {
        for (String line : request.split("\r\n")) {
            int colon = line.indexOf(':');
            if (colon > 0
                    && line.substring(0, colon).trim()
                            .equalsIgnoreCase(name)) {
                return line.substring(colon + 1).trim();
            }
        }
        throw new IOException("Missing header " + name);
    }

    // Demo ONLY: one client frame FIN=1, RSV=0, payload length <= 125.
    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();
        if (first < 0 || second < 0) {
            throw new EOFException("Frame header");
        }
        if ((first & 0x80) == 0 || (first & 0x70) != 0) {
            throw new IOException("Demo needs FIN=1, RSV=0");
        }
        if ((second & 0x80) == 0) {
            throw new IOException("Client frame not masked");
        }
        int length = second & 0x7f;
        if (length >= 126) {
            throw new IOException("Demo only allows short frames");
        }

        byte[] mask = in.readNBytes(4);
        byte[] bytes = in.readNBytes(length);
        if (mask.length != 4 || bytes.length != length) {
            throw new EOFException("Short frame");
        }
        for (int i = 0; i < bytes.length; i++) {
            bytes[i] ^= mask[i & 3];
        }
        return new Frame(first & 15, bytes);
    }

    static void sendServerFrame(
            OutputStream out, int opcode, byte[] bytes)
            throws IOException {
        if (bytes.length > 125) {
            throw new IOException("Frame too large for demo");
        }
        out.write(0x80 | opcode); // FIN=1; server frame unmasked.
        out.write(bytes.length);
        out.write(bytes);
        out.flush();
    }

    static void serveOnce(
            ServerSocket listener, CompletableFuture<Void> finished) {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(5000);
            InputStream input = peer.getInputStream();
            OutputStream output = peer.getOutputStream();

            String request = readHttpHeaders(input);
            if (!request.startsWith("GET /ws HTTP/1.1\r\n")) {
                throw new IOException("Unexpected request");
            }

            String key = requiredHeader(request, "Sec-WebSocket-Key");
            if (Base64.getDecoder().decode(key).length != 16) {
                throw new IOException("Bad key");
            }

            String toHash =
                    key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            String accept = Base64.getEncoder().encodeToString(
                    MessageDigest.getInstance("SHA-1")
                            .digest(toHash.getBytes(
                                    StandardCharsets.US_ASCII)));

            String reply = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n\r\n";
            output.write(reply.getBytes(StandardCharsets.US_ASCII));
            output.flush();

            // Server push without the client sending a message first.
            sendServerFrame(output, 1,
                    "server-ready".getBytes(StandardCharsets.US_ASCII));

            Frame text = readClientFrame(input);
            if (text.opcode() != 1) {
                throw new IOException("Expected text frame");
            }
            String body = new String(
                    text.payload(), StandardCharsets.UTF_8);
            sendServerFrame(output, 1,
                    ("ack:" + body).getBytes(StandardCharsets.UTF_8));

            Frame close = readClientFrame(input);
            if (close.opcode() != 8) {
                throw new IOException("Expected close");
            }
            sendServerFrame(output, 8, close.payload());
            finished.complete(null);
        } catch (Throwable problem) {
            finished.completeExceptionally(problem);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {
            listener.setSoTimeout(5000);

            CompletableFuture<Void> serverDone =
                    new CompletableFuture<>();
            Thread worker = new Thread(
                    () -> serveOnce(listener, serverDone));
            worker.setDaemon(true);
            worker.start();

            CompletableFuture<String> greeting =
                    new CompletableFuture<>();
            CompletableFuture<String> acknowledgement =
                    new CompletableFuture<>();
            CompletableFuture<Integer> closeCode =
                    new CompletableFuture<>();

            WebSocket.Listener listenerCallback =
                    new WebSocket.Listener() {
                final StringBuilder message = new StringBuilder();
                int completed = 0;

                @Override
                public void onOpen(WebSocket ws) {
                    ws.request(1);
                }

                @Override
                public CompletionStage<?> onText(
                        WebSocket ws,
                        CharSequence data, boolean last) {
                    message.append(data);
                    if (last) {
                        String whole = message.toString();
                        message.setLength(0);
                        if (completed++ == 0) {
                            greeting.complete(whole);
                        } else {
                            acknowledgement.complete(whole);
                        }
                    }
                    ws.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onClose(
                        WebSocket ws, int statusCode, String reason) {
                    closeCode.complete(statusCode);
                    return null;
                }

                @Override
                public void onError(WebSocket ws, Throwable error) {
                    greeting.completeExceptionally(error);
                    acknowledgement.completeExceptionally(error);
                    closeCode.completeExceptionally(error);
                }
            };

            URI uri = URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/ws");

            WebSocket ws = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(uri, listenerCallback)
                    .get(5, TimeUnit.SECONDS);

            System.out.println("server push: "
                    + greeting.get(5, TimeUnit.SECONDS));

            ws.sendText("client-hello", true)
                    .get(5, TimeUnit.SECONDS);
            System.out.println("client receives: "
                    + acknowledgement.get(5, TimeUnit.SECONDS));

            ws.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                    .get(5, TimeUnit.SECONDS);
            System.out.println("close code: "
                    + closeCode.get(5, TimeUnit.SECONDS));

            serverDone.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 WebSocketApiBoundaryDemo.java
java WebSocketApiBoundaryDemo
~~~

**Stdout verified with Java 17 JShell:**

~~~text
server push: server-ready
client receives: ack:client-hello
close code: 1000
~~~

### 8.1. Why Does the Output Demonstrate the Client/Server Boundary?

**The client** does not compute `Sec-WebSocket-Accept`, does not generate masking keys manually, and does not parse raw frame headers — `java.net.http.WebSocket` handles those parts. **The demo server** had to read HTTP request bytes, compute the accept hash, write `101`, read the masking key, unmask the payload, and emit frames itself. In production, these low-level server tasks must be handled by a **real WebSocket implementation**.

**Server push before the client sends:** the string `server-ready` is sent immediately after the handshake, proving the server can proactively push messages, unlike the ordinary HTTP request/response model.

**`client-hello` and `ack:client-hello`:** this is just application-layer text. The server does not have an `ack:` format per the RFC; the code explicitly creates it. The ACK in the demo is unrelated to a database commit.

**Close `1000`:** the JDK client and demo server exchange Close frames, and the client Listener receives the normal closure code. This code only confirms termination at the protocol level and does not replace business logic.

### 8.2. Do Not Use the Demo Server on the Internet

Although the program **runs**, it intentionally lacks many mandatory or essential requirements of a production implementation:

- Only checks `GET /ws HTTP/1.1` and `Sec-WebSocket-Key` minimally; does not fully verify `Upgrade`/`Connection`/`Sec-WebSocket-Version`/subprotocols or all HTTP edge cases.
- Does not use TLS/WSS, user authentication, Origin validation, CSWSH defense, or authorization.
- Does not handle frame fragmentation/continuation, extended lengths, multiple text messages, or binary.
- Does not handle Ping/Pong/control interleaving, compression/extensions, UTF-8 validation, or full Close codes/reasons.
- Does not support multiple concurrent clients, admission control, slow-client/backpressure, max total message size, rate limiting, or quotas.
- Catches `Throwable` to report to the future in the demo; production needs an error/resource cleanup strategy and must avoid turning serious errors into fake responses.
- Has no graceful shutdown/reconnect/durable state or broker/monitoring.

Keep it on **loopback** to learn the protocol. To build a real server, use Jakarta/Spring/Jetty/Netty and run security/compatibility tests.

## 9. Designing a Production Server Endpoint: From Handshake to Message Handler

A real WebSocket endpoint needs more layers than a single `onMessage` method:

~~~text
HTTP server / TLS listener
          |
          v
WebSocket handshake validator
  - origin, authentication, route, version, subprotocol
  - connection quotas, proxy policy
          |
          v
WebSocket protocol implementation
  - RFC frames, masking, fragmentation, control frames
  - max sizes, UTF-8, compression, close states
          |
          v
Session manager per connection
  - principal, subscriptions, heartbeat, outbound queue
          |
          v
Application message dispatcher
  - parse schema / validate / authorization / rate limit
          |
          +-> command handler / service / database
          |
          +-> event publisher / message broker
          |
          v
Send coordinator
  - per-session order, backpressure, ACK policy
~~~

### 9.1. Per-Connection State Ownership

For a WebSocket session, items that need to be stored:

| State | Scope |
| --- | --- |
| `sessionId` and socket handle | One TCP/WebSocket connection |
| `userId`/principal and credential expiry | Authenticated session and auth policy |
| `subscriptions`, rooms, filters | Channels the user is authorized to listen to |
| `outboundQueue`, queued byte count | Outbound buffer limit for slow clients |
| `lastPing`/`lastPong`/idle deadline | Liveness tracking |
| `lastDeliveredSequence`, request IDs | Recovery after reconnect if needed |
| `closeState`/cleanup guard | Prevent closing and releasing multiple times |

Do not keep all durable events solely in the RAM of a WebSocket connection. When a node restarts, sockets are lost; messages, job statuses, and transaction results need a database/broker if recovery is required.

### 9.2. Thread Safety of Sends and Sessions

Frameworks have specific semantics for concurrent send calls. Do not assume two business workers can concurrently write frames/text fragments while preserving the application message order you expect. A per-connection **outbound queue/writer coordinator** serializes messages and maintains backpressure.

When using the Java `WebSocket` client, do not keep a mutable `ByteBuffer` passed to `sendBinary` and mutate its bytes before the send future completes. On the server side, likewise do not share a single request parser/`StringBuilder` across all sessions without synchronization; each connection needs its own state or an explicit actor/event-loop mechanism.

### 9.3. Server Push Does Not Mean Unbounded Sending

If a producer generates 10,000 messages/s and a client consumes 100 messages/s, an unbounded queue will lead to memory pressure. The server must have:

- A **queue size limit in bytes**, not just message count.
- A coalesce/drop policy for droppable events (e.g., stale temperature readings).
- A policy not to drop critical events, instead persisting/replaying them or disconnecting slow clients.
- Outbound timeouts and closing slow connections with clear reasons/metrics.
- Max message size, per-principal rate limits, and subscription quotas.

`WebSocket.Listener.request(n)` in the JDK is a **client-side receive demand** mechanism; it does not automatically solve end-to-end backpressure from broker to server to network to UI.

## 10. Server Security: WSS, Authentication, Origin, and CSWSH

### 10.1. WSS and TLS

Production servers typically accept `wss://`, perform TLS, and verify server identity on the client side. With termination at a load balancer, the path from proxy to backend must be secured according to the threat model; do not rely on public `ws://` to transmit sensitive data.

**WebSocket masking does not encrypt data.** `Sec-WebSocket-Key` is not a secret that protects a session. Do not replace TLS with XOR masking or the handshake accept hash.

### 10.2. Origin Validation When Using Cookies

An untrusted website can attempt to open a cross-site WebSocket to a backend that uses session cookies under conditions permitted by the browser/cookie policy. If the server **does not check `Origin`**, there is a risk of **Cross-Site WebSocket Hijacking (CSWSH)**. A browser-facing server should enforce a realistic Origin allowlist combined with cookie/session protection and authentication.

Do not treat Origin validation as user authentication: **non-browser clients can spoof `Origin`**. Access control requires sessions/tokens/mTLS and **authorization per message/subscription**, not just an Origin check.

Do not treat `fetch` CORS preflight as automatic protection for the WebSocket handshake; appropriate WebSocket server controls must be used.

### 10.3. Do Not Use the Query String for Long-Lived Secrets

A URL like `wss://example.test/ws?token=long-lived-secret` can appear in proxy logs, browser history, or monitoring. For browser clients that cannot arbitrarily add any custom authorization headers, use a well-designed auth mechanism (secure session cookie, short-lived scoped token, or authenticated handshake flow) with log redaction, short TTL, and rotation.

The Java JDK client has an API to configure certain request headers, but **do not infer that the browser WebSocket API behaves the same way**. Always distinguish client platforms.

### 10.4. Every Message Is Untrusted Data

After authenticating the connection, the server must continue validating **every** command:

- Type/JSON schema/UTF-8/size limits.
- ID/path data free of injection or exposing another user's objects.
- Rate/message quotas and anti-spam/abuse controls.
- Re-checking permissions when revoked or when tokens expire.
- Safe logging without printing cookies/tokens/sensitive payloads.

An accepted WebSocket connection is not a free pass to all backend APIs.

## 11. Heartbeat, Close, and Reconnect: Application Responsibilities

### 11.1. Ping/Pong

WebSocket `Ping`/`Pong` control frames help detect unresponsive connections. A successful Pong **does not prove the server processed a business command**. Heartbeat frequency should account for load balancer idle timeouts, mobile battery, network variability, and connection count.

The browser JavaScript API has limitations with Ping control frames; many browser apps use application-level heartbeat messages. The Java JDK client has `sendPing`/`sendPong`, but that alone is not a global liveness policy.

### 11.2. Close Handshake Differs from Network Drop

When closing intentionally, both sides can exchange Close control frames; code **1000** is normal closure. However, when the Internet drops or a process crashes, Close frames are not always exchanged. The server needs idle deadlines and cleanup; the client needs to distinguish user logout/cancel from network failure to avoid reconnecting infinitely.

### 11.3. Reconnect Does Not Mean Old State Remains

~~~text
Connected to Node A
    |
    +-- subscribe(room-7)
    +-- receive event sequence=120
    X network loss / node restart

Reconnect to Node B
    |
    +-- authenticate again
    +-- restore subscriptions
    +-- request missed events since 120
    +-- if history missing: fetch snapshot / resync
~~~

This is **application-designed logic**, not built into the WebSocket protocol. If exactly-once or reliable commands are required, you need request IDs, idempotency keys, durable event cursors, ACK semantics, and transaction handling.

### 11.4. Reconnect Backoff and Deployment

After a node restarts, tens of thousands of clients may reconnect simultaneously. Use bounded exponential backoff, random jitter, and server admission caps to prevent a reconnect storm. During a rolling deploy, the server can drain sessions, send an appropriate close code/reason, wait for a bounded time, and then shift to new nodes. Do not keep sockets alive forever by avoiding deployments.

## 12. Deploying Multiple Server Nodes: Sockets Bind to One Node, Events Do Not

Each open WebSocket connection is typically bound to a specific node. If user A connects to Node 1 and user B connects to Node 2, Node 1 cannot directly call send on a `WebSocketSession` in Node 2's memory.

~~~text
User A --WS--> Node 1 --\
                        +--> broker / topic bus --> events
User B --WS--> Node 2 --/               |
                                        v
                           each node fans out to
                           connected sessions
~~~

Therefore, a production architecture typically needs:

- A distributed broker/pub-sub for events across multiple nodes.
- Shared or recoverable session/subscription state if the application needs resume.
- Durable storage for messages/commands that require replay.
- A load balancer/WebSocket-aware proxy, idle timeouts/connection limits.
- Metrics: concurrent connections, handshake failures, active sessions, outgoing queued bytes, slow clients, ping RTT, reconnect rates.
- Ordering rules per room/user/entity, without assuming a global system-wide order exists automatically.

**Sticky sessions** can keep a connection stable on one node, but do not solve reconnecting to another node or node crashes. A WebSocket server framework only solves **protocol/session hosting**, not creating a reliable distributed system by itself.

## 13. Which Systems Should Build Their Own WebSocket Server?

Building a standalone **WebSocket service** makes sense when:

1. The product needs to manage many live sessions, subscriptions, or has a specialized workload.
2. It needs controlled integration with brokers, per-user quotas, and state reconciliation.
3. There is a team maintaining security updates, performance tests, failover, and observability.
4. The API/web client needs both sides to exchange messages actively and frequently, not just fetch data sparsely.

However, **building your own WebSocket service** does not mean **rewriting the WebSocket protocol with TCP primitives**. The standard protocol layer should be delegated to a framework, while subscription/command/fan-out logic is owned by the application.

If the browser only needs one-way progress updates, **SSE** may be less complex. If there is only CRUD/REST, use HTTP. If real-time video/voice with jitter buffers and NAT traversal is needed, WebRTC may be more appropriate. If large file uploads are needed, HTTP streaming/resumable upload is usually more convenient.

## 14. Common Mistakes About JDK Client and Server Boundaries

| Misconception | Why it is wrong | How to handle it |
| --- | --- | --- |
| `HttpClient.newWebSocketBuilder()` creates a server | The builder only initiates outbound client WebSockets | Use a server framework/implementation |
| JDK `HttpServer` has `@ServerEndpoint` built in | `jdk.httpserver` does not provide Jakarta WebSocket | Add a Jakarta runtime or another server |
| `ServerSocket.accept()` is enough for a WebSocket server | Only accepts TCP, has no RFC 6455 state machine | Choose an implementation or learn with a bounded demo |
| `javax.websocket` and `jakarta.websocket` are always interchangeable | Namespaces/versions and containers may differ | Align dependencies/runtime |
| Setting `Sec-WebSocket-Accept` authenticates the user | This is only a handshake correctness check | Add auth/session/authorization |
| Sending unmasked client frames | Violates RFC 6455 | Use a standard client library |
| Masking server frames like client frames | Wrong RFC 6455 frame masking direction | Let the server implementation handle it |
| Each TCP read = one full text message | Frames can be split/coalesced in the stream | Proper parser/frame handling and size limits |
| One `onText` callback is always a complete message | `last=false` means more parts may follow | Accumulate until `last=true` |
| Java Listener does not call `request(n)` | Receive demand is not replenished | Manage demand/backpressure |
| `sendText()` future completing = DB commit | No application ACK | RequestId + ACK/transaction |
| Ping/Pong is proof the login is still valid | Liveness does not replace authentication | Separate token/ACL policy |
| Fetch CORS automatically protects WebSocket | WebSocket handshake differs from fetch/XHR | Origin allowlist + auth + CSWSH defense |
| Disabling TLS verification to connect WSS | Opens MITM risk | Fix certificates/trust properly |
| Unbounded outbound queues | Slow clients cause server OOM | Backpressure/quotas |
| Sharing one per-connection buffer across all users | Data leaks/mixes between sessions | Per-session isolation and concurrency control |
| Joining a WebSocket to all rooms without ACL checks | Users receive unauthorized data | Authorize every subscribe/action |
| Using the demo raw server in production | Lacks RFC corner cases and security | Maintained and tested framework |
| Treating WebSocket as durable event storage | Events are lost on node crash/reconnect | Broker/database + sequence/replay |

## 15. Exercises with Answers

### Exercise A — Can You Run a High-Level WebSocket Server Immediately with Only JDK 17 Installed?

The team needs to expose `wss://company.test/updates` for browser clients. `java.net.http.WebSocket` is available on JDK 17. Can this API alone be used to accept incoming connections?

**Answer:** No. That is a **client API**. Choose Jakarta/Spring/Jetty/Netty or another WebSocket runtime. The JDK provides TCP primitives to write the protocol yourself, but does not have an equivalent high-level WebSocket server endpoint.

### Exercise B — A Spring Boot Project Wants `/ws`

The project already uses Spring Boot, authentication, and controllers. Is it necessary to build a custom `ServerSocket` for WebSocket to work?

**Answer:** No. Evaluate **Spring WebSocket** and the application's server container; configure the endpoint, authentication, Origin, limits, and message handler. Writing a low-level frame parser manually usually increases risk.

### Exercise C — Jakarta `@ServerEndpoint` Reports Package Not Found

The code `import jakarta.websocket.server.ServerEndpoint` fails to compile when running only `javac EchoEndpoint.java` on JDK 17.

**Answer:** This is an **external API**, not part of Java SE/JDK. Add a compatible Jakarta WebSocket API and runtime implementation/container; check that you are not confusing `javax.websocket` with `jakarta.websocket` packages.

### Exercise D — Server Receives an Unmasked Frame from Client

A raw WebSocket server reads a client text frame with `MASK=0`, but the payload is still valid JSON. Should it accept it?

**Answer:** It should not be accepted per RFC 6455; client-to-server frames **must be masked**. A valid JSON payload does not compensate for a wire protocol violation.

### Exercise E — Client Finished Sending, but Server Did Not Write to DB

`ws.sendText("pay", true)` completes its future; the application displays "payment successful". Is there a basis for this?

**Answer:** No. The future reflects the send operation in the client API, not the business commit. You need an **application-level ACK**/status from the server with a request ID and idempotency policy.

### Exercise F — Server Returns 101 Without Checking Origin

The application uses cookie login for browsers; the server accepts WebSockets from any Origin. What is the risk?

**Answer:** There is a risk of **Cross-Site WebSocket Hijacking** under conditions allowed by cookies/browsers. Use an Origin allowlist where appropriate, authentication, SameSite/session policies, and permission checks on every message.

### Exercise G — Node B Does Not See Sockets on Node A

Client A is on Node 1, user B is on Node 2, and the application sends a chat message from A, but B does not receive it. Why?

**Answer:** Sockets and sessions are state within each process. A broker/pubsub is needed to fan out across nodes, along with durable storage/cursors if replay is required, rather than just using a static map inside each JVM.

### Exercise H — Java Listener Receives Only One Message

`onOpen` calls `request(1)`, and `onText` processes the first message but does not request more. What happens?

**Answer:** The client Listener has not provided further demand for receive callbacks; do not assume remaining messages will arrive at the callback automatically. Manage `request(n)` according to consumption/queue progress.

### Exercise I — WebSocket Server Uses HTTP Headers on Every Message

After `101`, the server tries to parse each chat message as a `POST /send` with new headers over the same upgraded socket.

**Answer:** Wrong wire protocol. After the upgrade, both sides exchange WebSocket frames/messages; `"type=send"` belongs to the JSON/binary application protocol, not new HTTP request framing.

### Exercise J — Using the Demo Server to Receive Video

The demo server only supports FIN=1, payload <=125 bytes, and one message. The client sends a binary video frame of several kilobytes. What is the result?

**Answer:** The demo will fail by design, because it does not support binary/extended lengths/fragmentation. Use a full server framework; for real-time video, evaluate WebRTC/media transport instead of forcing the demo server.

### Exercise K — Client Loses Connection After an Order Command

The client sends command ID=72, and the server finishes processing it, but the ACK is lost. Is it safe to reconnect and resend with a new ID?

**Answer:** Not necessarily. WebSocket does not guarantee exactly-once delivery across reconnects. Keep the idempotency key, check the transaction status, and retry according to policy to avoid creating duplicate orders.

### Exercise L — Slow Client Causes Out-of-Memory

A server pushes 5000 events/s to a client that only reads 20 events/s, using an unbounded queue.

**Answer:** Queued bytes must be bounded, coalesced/dropped if business logic allows, throttled, or slow clients must be closed, coordinated with a broker/replay. TCP/WebSocket does not automatically solve application memory/backpressure.

## 16. Java WebSocket Client and Server Implementation Checklist

- [ ] Identified which side **connects outbound** (client) and which side **listens** (server)?
- [ ] Understood that `java.net.http.WebSocket` is **client-only** in JDK 17?
- [ ] For the server, chosen Jakarta/Spring/Jetty/Netty/a suitable implementation and kept security patches updated?
- [ ] Distinguished `javax.websocket` from `jakarta.websocket`/container compatibility?
- [ ] Does the server implementation handle RFC 6455 handshake, masking, fragmentation, control frames, close, and size limits?
- [ ] Not using the `ServerSocket` demo as a production server?
- [ ] Does the JDK client Listener use `request(n)` properly for receive demand and accumulate text until `last=true`?
- [ ] Does message sending have a coordinator/queue to preserve per-session order?
- [ ] Is there an application schema version, type, requestId, ACK, validation, and authorization?
- [ ] Chosen WSS/TLS, trust verification, and Origin policy/CSWSH defense?
- [ ] Disallowed unauthorized subscriptions/topics even if the WebSocket is authenticated?
- [ ] Configured max message size, inbound/outbound quotas, rate limits, and per-user connection limits?
- [ ] Implemented Ping/Pong heartbeats/idle timeouts, Close cleanup, and reconnect backoff/jitter?
- [ ] Implemented snapshot/replay/resync after reconnect if data is critical?
- [ ] Included a broker/pubsub and durable store when running multiple server nodes?
- [ ] Added metrics for handshake errors, active connections, queued bytes, ping RTT, close codes, and reconnect failures?
- [ ] Tested malformed handshakes/frames, fragmented messages, extended lengths, slow clients, and oversized payloads?
- [ ] Tested rolling deploys, proxy idle timeouts, network drops, and user logouts?
- [ ] Considered HTTP/SSE as a simpler option when full-duplex is not required?

**Conclusion:** JDK 17 allows creating a **WebSocket client** directly with `HttpClient.newWebSocketBuilder()` and `java.net.http.WebSocket`. However, a Java server needs an **HTTP/WebSocket server implementation** capable of listening, handshaking, framing, securing, and managing many connections. `ServerSocket` only provides TCP; the JDK's `HttpServer` is not a WebSocket server framework by itself. Writing a protocol demo helps understand the fundamentals, while production should use a battle-tested stack and build application protocols, state, authorization, backpressure, and distributed messaging on top of it.

## 17. Official API Documentation and Standards

- **Java 17 — WebSocket client:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Java 17 — WebSocket.Builder:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Java 17 — WebSocket.Listener:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java 17 — HttpServer:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- **RFC 6455 — The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455
- **RFC 8441 — Bootstrapping WebSockets with HTTP/2:** https://www.rfc-editor.org/rfc/rfc8441
- **Jakarta WebSocket Specification:** https://jakarta.ee/specifications/websocket/

For WebSocket servers, consult the documentation of your specific runtime/container/framework and deployed version. The JDK client API does not guarantee WebSocket server support, nor does it replace security, proxy, reconnect, and real-load testing.