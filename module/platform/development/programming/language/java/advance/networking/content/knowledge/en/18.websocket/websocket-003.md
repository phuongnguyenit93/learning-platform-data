# WebSocket.Builder, Subprotocols, and Asynchronous Connections in Java 17+

**`WebSocket.Builder`** is the API for creating a WebSocket client in the `java.net.http` module (Java 11+, stable in Java 17). You obtain a builder from `HttpClient.newWebSocketBuilder()`, configure additional headers, **subprotocol** preference order, and connection establishment timeout, and then call `buildAsync(URI, WebSocket.Listener)`. The result is a **`CompletableFuture<WebSocket>`**, not an immediately connected socket. Once the handshake succeeds, you can send data using async methods that return futures and receive data via `WebSocket.Listener` with the `request(n)` mechanism.

A common mistake is thinking `subprotocols("chat.v2", "chat.v1")` means Java **forces** the server to use `chat.v2`. In reality, the client only **proposes options in preference order**. The server selects one accepted subprotocol, or may select none; the client must check **`socket.getSubprotocol()`** and refuse to proceed if the application requires a specific protocol.

This article belongs to the **WebSocket** section of **Java Advance - networking**. The content covers the HTTP opening handshake mechanism, builder, async completion and handshake errors, subprotocol selection, listener demand, fragmentation, close/abort lifecycle, security, and two standalone Java 17+ programs running on loopback (one successful handshake, one rejected with HTTP 403).

## 1. When to use WebSocket, and how does it differ from HTTP request–response?

HTTP is typically used by applications in **request → response** pairs. WebSocket establishes a **long-lived bidirectional message channel**: after a valid opening handshake, both client and server can send text/binary messages without creating a separate HTTP request for each message. It is suitable for chat, presence, real-time price/status updates, games, or notifications.

```text
Traditional HTTP:
client -- GET /updates --> server
client <-- JSON response -- server
client -- GET /updates --> server
client <-- JSON response -- server

WebSocket:
client -- HTTP opening handshake --> server
client <-- 101 Switching Protocols - server
             [maintain connection]
client --> text/binary message --> server
client <-- event/message -------- server
client --> ping/close ----------> server
```

WebSocket **does not automatically turn every call into a reliable transaction**: there are still disconnects, data loss when a process crashes, business ordering, retries, authorization, and queue control. The WebSocket protocol delivers messages over a connection, but **does not inherently provide exactly-once delivery or message persistence**; if the system needs them, the application must implement sequence numbers/ACK/replay itself.

In Java 17, the `java.net.http.WebSocket` API is a **WebSocket client**, and does not include a production WebSocket server in the same package. The example below writes a minimal RFC 6455 server **solely for loopback verification**, not as a replacement for a full server/framework.

## 2. The HTTP opening handshake is the state transition point

With `ws://`, the client opens a TCP connection and sends an HTTP opening handshake. An illustrative request:

```http
GET /chat HTTP/1.1
Host: example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <base64-nonce>
Sec-WebSocket-Protocol: chat.v2, chat.v1
X-Demo: present
```

A valid response might be:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <calculated-value>
Sec-WebSocket-Protocol: chat.v2
```

The two HTTP examples above are **protocol illustrations**, not strings to copy as Java code. In practice, the JDK generates `Sec-WebSocket-Key` and verifies `Sec-WebSocket-Accept` automatically. **Do not manually set protocol-defined WebSocket headers** via `WebSocket.Builder.header`.

`Sec-WebSocket-Accept` is derived from `Base64(SHA-1(Sec-WebSocket-Key + GUID))` per RFC 6455. This is a **protocol handshake confirmation rule**, **not** a password hashing scheme or a signature authenticating the server's identity. With `wss://`, channel security requires proper TLS/hostname verification.

**Key states:**

- Before `101`: it is still an HTTP handshake; 401/403/404 errors or an invalid handshake do not produce a usable WebSocket.
- After a valid handshake: sender and receiver exchange **WebSocket frames**, rather than treating each message as a new HTTP body.
- On a close frame or error: both sides transition toward output/input closed states according to `WebSocket` rules.

## 3. Basic API: obtaining a builder from HttpClient

Common pattern:

```java
// Illustrative snippet: URI endpoint and listener are defined externally.
HttpClient client = HttpClient.newHttpClient();

WebSocket.Builder builder = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .subprotocols("chat.v2", "chat.v1")
        .header("X-Request-Id", "request-123");

CompletableFuture<WebSocket> connection =
        builder.buildAsync(endpoint, listener);
```

The snippet above is **not yet a standalone program**; it requires imports and declarations for `endpoint` and `listener`. Key details to remember:

1. `HttpClient.newWebSocketBuilder()` belongs to `HttpClient`; do not call `new WebSocket.Builder()` because `Builder` is an interface.
2. `WebSocket.Builder` has **mutable** state and is **not safe for concurrent modification by multiple threads**. Construct a builder for one connection in a single initialization thread; do not share the same builder across hundreds of tasks calling `subprotocols/header/buildAsync` concurrently.
3. A built `HttpClient` is immutable and can be shared per policy; you can call `sharedClient.newWebSocketBuilder()` **separately for each connection**.
4. `buildAsync` returns `CompletableFuture<WebSocket>`; only when the future completes **normally** do you have a WebSocket whose handshake succeeded. Do not call `sendText` on a `WebSocket` you have not received yet.
5. `HttpClient.newWebSocketBuilder()` is an **optional operation** of the interface. Standard clients created with `HttpClient.newHttpClient()` or the JDK default builder support it; a custom `HttpClient` implementation may throw `UnsupportedOperationException`.

The builder configures the handshake for **a single connection**. It is not a registry for managing rooms, domain subscriptions, or application message buffers.

## 4. Four core operations of WebSocket.Builder

| Method | Responsibility | What to avoid |
| --- | --- | --- |
| `header(String name, String value)` | Adds valid HTTP headers during the **opening handshake** | Do not set prohibited WebSocket protocol headers; do not log bearer tokens |
| `connectTimeout(Duration timeout)` | Limits the time to **establish the WebSocket** | Do not mistake this for a per-message timeout after connecting |
| `subprotocols(String mostPreferred, String... lesserPreferred)` | Proposes subprotocols in **preference order** | Do not treat subprotocol as a TLS version or authentication |
| `buildAsync(URI uri, WebSocket.Listener listener)` | Performs the async opening handshake, returns a future | Do not equate the returned future with a ready connection |

Some practical assumptions:

- Not calling `subprotocols` means **no subprotocol is requested**, and `getSubprotocol()` will return an empty string if no selection is established.
- `connectTimeout` must be a positive `Duration` per contract; do not use `Duration.ZERO` or negative values. If unset, the API specifies **no default finite timeout for establishment**.
- `header` adds headers for server authentication/routing/tracing during the handshake; it does not turn every subsequent WebSocket message into an HTTP request with its own headers.
- `buildAsync` may complete exceptionally with `IOException`, `WebSocketHandshakeException`, `HttpTimeoutException`, `InterruptedException`, or configuration/permission errors depending on the case.

Do not wrap the entire lifecycle in a single builder and call `buildAsync` again on reconnect without controlling listener state/credentials; on reconnect, create a **new builder**, URI, policy, and listener for the new connection.

## 5. Subprotocol is not an extension or URI path

A **subprotocol** is an **application protocol** for interpreting WebSocket messages, such as `chat.v2` or `json.rpc.v1`. It is not the WebSocket transport version (RFC 6455 version 13), not an HTTP method, and not a negotiated TLS cipher suite.

```text
Client preference:
  chat.v2 (highest)
  chat.v1 (lower)

Sec-WebSocket-Protocol: chat.v2, chat.v1
                    |
                 Server
                    |
                    +-- understands chat.v2 -> selects chat.v2
                    +-- only understands chat.v1 -> may select chat.v1
                    +-- selects none -> no negotiated subprotocol
```

Java configuration:

```java
// Snippet: builder is a WebSocket.Builder not used concurrently.
builder.subprotocols("chat.v2", "chat.v1");
```

After connecting:

```java
// Snippet: socket is a WebSocket completed by buildAsync.
String selected = socket.getSubprotocol();
if (!"chat.v2".equals(selected) && !"chat.v1".equals(selected)) {
    // If business logic requires a selection: close/reject.
    socket.sendClose(WebSocket.NORMAL_CLOSURE,
            "Unsupported subprotocol");
}
```

Selection conditions must be defined by the **application protocol**. If the client only implements the `chat.v2` schema and the server selects `chat.v1`, do not proceed with sending v2 messages. If no subprotocol is selected and the application defines a clear default protocol, you may allow it; if negotiation is mandatory, you must reject it.

The server must **select at most one subprotocol proposed by the client**; it must not arbitrarily return a different token. Subprotocol IDs must satisfy valid token syntax; do not embed URLs, JSON, spaces, or user secrets in subprotocol names. The order provided by the client is a **preference level**, and the server is not forced to always pick the first element.

## 6. When does the client receive no subprotocol?

`socket.getSubprotocol()` returns **`""`** if the handshake did not establish a subprotocol. Scenarios:

1. The client did not call `subprotocols` and the server did not select one.
2. The client proposed subprotocols, but a compliant server chose not to select one, if the application permits it.
3. A proxy/server does not support custom negotiation; depending on behavior, the handshake may complete without a subprotocol or fail.

**Do not infer** that because `buildAsync` succeeded, the content protocol is compatible. If the app exchanges JSON with a specific schema, verify the negotiated subprotocol **before sending business messages**.

Policy example:

```java
// Illustrative snippet for an application that only supports chat.v2.
WebSocket connected = future.get(10, TimeUnit.SECONDS);
if (!"chat.v2".equals(connected.getSubprotocol())) {
    connected.sendClose(WebSocket.NORMAL_CLOSURE,
            "Protocol mismatch");
    throw new IllegalStateException("Unsupported subprotocol");
}
```

In production, you can use a policy-appropriate close code and complete the close handshake with a deadline; do not default to calling `abort()` just because a fallback version is unsupported. If the server selects a value not in the offer set, that is an **opening handshake/protocol error**, not grounds to silently parse messages according to an unadvertised token.

## 7. `ws://` and `wss://`: subprotocol does not provide security

WebSocket URIs typically look like:

```text
ws://localhost:8080/chat
wss://api.example.test/realtime
```

- **`ws://`** uses an unencrypted WebSocket connection without TLS. It is suitable for loopback demos and environments with a clear threat model; it is unsuitable for transmitting sensitive tokens/user data over untrusted networks.
- **`wss://`** uses TLS to protect content and authenticate the server according to trust/endpoint verification configuration. Production over the Internet typically uses `wss://`.
- A **subprotocol** like `chat.v2` specifies how messages are interpreted; it **does not encrypt** data and **does not authenticate** users.
- **URI path/query** are sent in the opening handshake; avoid placing long-lived access tokens in the query string because proxies/access logs often record URLs.
- HTTP **CORS** is not an authorization mechanism for a WebSocket server. The server must verify identity/cookie/token/origin according to the threat model and enforce permissions on each channel/message.

With `wss://`, you can configure `HttpClient.newBuilder().sslContext(customContext).build()` in systems requiring a private CA/mTLS. However, a misconfigured truststore/custom `SSLContext` can cause the TLS handshake to fail before the WebSocket handshake even starts; do not fix this with a trust-all manager.

## 8. Adding headers properly in the opening handshake

`WebSocket.Builder.header(name, value)` adds **additional HTTP request headers**. The headers `Sec-WebSocket-Key`, `Sec-WebSocket-Version`, `Sec-WebSocket-Protocol`, `Connection`, and `Upgrade` belong to the WebSocket opening protocol and must be managed by the JDK; the API forbids manually adding protocol-defined headers.

```java
// Illustrative snippet: token managed by a secrets system.
builder.header("X-Trace-Id", traceId);
builder.header("Authorization", "Bearer " + accessToken);
```

Notes:

- Headers here are used **during the handshake**. A subsequent `sendText` message **does not carry a new HTTP Authorization header**; if session/credential refresh is needed, you must have an application protocol or a new connection.
- A server/proxy may inspect headers and reject the handshake with HTTP 401/403. Not all arbitrary headers are preserved by proxies; you should test the actual network path.
- Do not share a mutable builder with user A's Authorization header and reuse it for user B. Create a builder per connection with a clear security scope.
- Do not print `Authorization`, cookies, query credentials, or full handshake headers in test/production logs.
- Do not use subprotocols as a place to store secret tokens; subprotocol tokens may be exposed in handshake logs and must follow identifier syntax.
- You can attach a correlation ID to the handshake; to trace individual WebSocket messages, you need a **message-level operation ID** within the subprotocol's format.

The Java loopback example only uses `X-Demo: present` to verify that the builder forwards headers; there are no real credentials.

## 9. `buildAsync` timeout is not a message receive timeout

`WebSocket.Builder.connectTimeout(Duration)` limits **WebSocket connection establishment**. If the handshake does not complete within the limit, the future may complete exceptionally with `HttpTimeoutException`.

```java
// Snippet: do not put the entire API into a single standalone class.
CompletableFuture<WebSocket> future =
        client.newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .subprotocols("chat.v2")
                .buildAsync(uri, listener);

WebSocket socket = future.get(8, TimeUnit.SECONDS);
```

Two different timeouts:

- `connectTimeout(5s)` belongs to the **builder/connection establishment** and the JDK WebSocket client.
- `future.get(8s)` belongs to the **thread waiting for completion**. If it throws `TimeoutException`, that **does not automatically cancel the future**; the application must decide cancellation/cleanup according to its lifecycle policy.

Once connected, these two values are **not an idle timeout or a per-message processing timeout**. The application needs its own heartbeat (ping/pong), business response deadlines, queue limits, close deadlines, and reconnect strategy.

**Do not use `join()` on an event-loop or UI thread if it may block for a long time.** `buildAsync` itself is asynchronous, though the caller can actively wait with `join()/get()`; on an event-driven backend, use `thenCompose/whenComplete` to preserve asynchronicity.

## 10. Asynchronous connection: future completion does not mean the job is done

Model:

```text
WebSocket.Builder
   |
   | buildAsync(uri, listener)
   v
CompletableFuture<WebSocket>
   |
   +-- normal completion -> WebSocket ready
   |         |
   |         +-- getSubprotocol()
   |         +-- sendText(...), sendBinary(...)
   |         +-- Listener receives messages
   |         +-- sendClose(...) / abort()
   |
   +-- exceptional completion
             |
             +-- WebSocketHandshakeException
             +-- HttpTimeoutException
             +-- IOException / network/TLS issues
             +-- illegal arguments / policy/security failure
```

In Java:

```java
// Illustrative snippet: future is already obtained.
future.whenComplete((ws, error) -> {
    if (error != null) {
        // Classify handshake/TLS/timeout error and clean up.
        logFailure(error);
        return;
    }
    // Only use ws after subprotocol compatibility is verified.
    onConnected(ws);
});
```

This is not a standalone class: `logFailure` and `onConnected` are app functions. When using `get()`, async exceptions are typically wrapped in `ExecutionException`; `join()` typically wraps them in `CompletionException`. You must **unwrap the cause** to classify `WebSocketHandshakeException` and retrieve the status.

Chaining stages:

```java
// Snippet: connectFuture is already obtained.
connectFuture.thenCompose(ws -> ws.sendText("hello", true))
             .thenCompose(ws -> ws.sendClose(
                     WebSocket.NORMAL_CLOSURE, ""))
             .exceptionally(error -> {
                 handleAsyncError(error);
                 return null;
             });
```

Do not send/close immediately before confirming subprotocol and application auth requirements. In a real pipeline, a message reaching the peer can cause side effects; a **completed send future** proves the client's send operation completed, **not** that the server sent a business ACK.

## 11. What does Listener receive, and how is callback ordering handled?

`WebSocket.Listener` has the following callbacks:

| Callback | Purpose |
| --- | --- |
| `onOpen(WebSocket)` | Client is connected; typically calls `request(1)` or `request(n)` |
| `onText(WebSocket, CharSequence, boolean last)` | Receives a **part** of a text message |
| `onBinary(WebSocket, ByteBuffer, boolean last)` | Receives a **part** of a binary message |
| `onPing(WebSocket, ByteBuffer)` | Receives a Ping control frame |
| `onPong(WebSocket, ByteBuffer)` | Receives a Pong control frame |
| `onClose(WebSocket, int code, String reason)` | Peer sent Close, input closed; terminal callback |
| `onError(WebSocket, Throwable)` | Error in WebSocket, terminal callback |

For **a single WebSocket**, listener callbacks are invoked sequentially and are non-reentrant; for multiple WebSockets sharing one listener, callbacks **may occur concurrently**, so shared state must be protected.

A crucial point: every new WebSocket starts with **receive invocation counter = 0**. Only when `webSocket.request(n)` increments demand can the implementation invoke receive methods such as `onText/onBinary/onPing/onPong/onClose`. `onOpen` and `onError` do not consume demand like receive methods.

**If you override `onOpen` without calling `request`, the application may connect successfully but never see any message callbacks.** Java 17's default `onOpen` calls `request(1)`; when overriding it, you must consciously preserve that behavior.

## 12. `webSocket.request(n)` counts callbacks, not messages or bytes

Per Java 17, `request(n)` increments the number of additional **receive callback** invocations permitted. It is **not** a request to read n bytes, n WebSocket messages, or n TCP packets.

```text
onOpen -> request(1)
                |
                v
onText("Hel", last=false)     [1 callback]
        |
        +-> request(1)
                |
                v
onText("lo", last=true)       [2nd callback]
        |
        +-> assembled into one message: "Hello"
        +-> request(1) for the next event
```

A text message may be delivered across **multiple `onText` calls**; `last` indicates the **final part of the message**. A single callback can also carry a complete message.

`WebSocket.Listener` must return a `CompletionStage<?>` for `onText/onBinary/onPing/onPong/onClose`. The completion stage indicates **when the implementation is permitted to reclaim the CharSequence/ByteBuffer data**; it is not the same as the receive demand counter. If a callback returns `null`, the implementation treats it as immediately completed; when processing asynchronously, do not retain a reference to a mutable buffer after the stage has completed. Copy within bounds or keep the stage incomplete per the contract.

Do not perform unbounded blocking database calls directly inside `onText`; listener threads can become a bottleneck. If offloading to a worker, use a bounded queue, clear payload ownership, and a policy for when to increment `request`.

## 13. Fragmentation: one message may span multiple callbacks

WebSocket has the concepts of **message** and **frame**. A message can be fragmented into multiple frames, and the Java API may deliver the corresponding parts across multiple `onText` or `onBinary` calls.

```java
// Illustrative snippet inside a per-socket WebSocket.Listener.
private final StringBuilder parts = new StringBuilder();

@Override
public CompletionStage<?> onText(
        WebSocket socket, CharSequence data, boolean last) {
    parts.append(data);
    if (last) {
        String wholeMessage = parts.toString();
        parts.setLength(0);
        handleMessage(wholeMessage);
    }
    socket.request(1);
    return CompletableFuture.completedFuture(null);
}
```

This is a snippet inside a listener, **not standalone**: it requires an enclosing class, imports, and a `handleMessage` definition. Although reading an internal `StringBuilder` from serialized per-socket callbacks is safe, it is not suitable for sharing across multiple sockets without synchronization.

**Memory protection:** do not append without bounds. If a peer sends a 500 MiB message without `last` anytime soon, `StringBuilder` can OOM. Enforce `maxMessageChars/maxBinaryBytes`; when exceeded, close the socket per policy (e.g., with the appropriate close code when valid) and stop queuing unbounded input.

For binary data, `ByteBuffer` only contains bytes from `position` to `limit`; use `remaining()`. UTF-8 text is provided by `onText` as a valid UTF-16 `CharSequence` per the API, without splitting UTF-8 bytes mid-character like a raw socket. Still, **do not assume one callback = one JSON object**; only parse after `last==true` or using subprotocol framing.

## 14. Sending messages is also asynchronous: sendText and sequencing

After connecting:

```java
CompletableFuture<WebSocket> a = ws.sendText("Hello", true);
CompletableFuture<WebSocket> b = a.thenCompose(
        socket -> socket.sendText(" world", true));
```

This is an illustrative snippet. In the example above, `true` each time means **one complete text message**, so the server will receive two messages: `"Hello"` and `" world"`, not one `"Hello world"` message. If you want one message **split into multiple parts**, use:

```java
ws.sendText("Hello ", false)
  .thenCompose(socket -> socket.sendText("world", true));
```

**`last` rules:**

- `last=false`: the current part **does not end** the text/binary message.
- `last=true`: ends the message.
- If multiple threads send text/binary concurrently while a similar send is pending, the future may fail with `IllegalStateException`. **Queue sends in order and serialize** them via `thenCompose` chaining or a bounded outgoing queue.
- `sendText` returns `CompletableFuture<WebSocket>` when the send operation completes on the client side; it does not indicate that the server has parsed/committed the message.
- `CharSequence` must not be modified while the send future is pending. For `sendBinary(ByteBuffer, last)`, do not touch the buffer until the future completes per the Java 17 contract.

The first example sends `"ping"` using `sendText("ping", true)` and the server returns a text message `ACK:ping` **split into two frames**; the listener reassembles it safely even if the JDK delivers a different number of callbacks.

## 15. Java 17+ Example 1: successful handshake, subprotocol selection, and receiving text

The file **`WebSocketBuilderLoopback.java`** is a complete program with no external libraries required. It uses `ServerSocket` **bound only to IPv4 loopback** as a tiny WebSocket test server. The server performs the HTTP/1.1 Upgrade, computes `Sec-WebSocket-Accept` per RFC 6455, selects `chat.v2`, reads the client-masked `ping` text frame, sends back a text message fragmented into `ACK:` and `ping`, and responds with Close status 1000.

The client uses the exact APIs to learn:

- `HttpClient.newHttpClient().newWebSocketBuilder()`.
- `header("X-Demo", "present")`.
- `subprotocols("chat.v2", "chat.v1")`.
- `connectTimeout(Duration.ofSeconds(5))`.
- `buildAsync(uri, listener)` returning `CompletableFuture<WebSocket>`.
- `getSubprotocol()` verifying the server selected `chat.v2`.
- `WebSocket.Listener.onOpen/onText/onClose/onError` and `request(1)`.
- `sendText(...).get(...)` and `sendClose(...)` with a deadline.

```java
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
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.Base64;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketBuilderLoopback {
    record ServerResult(boolean offered, boolean customHeader,
                        boolean closeSeen) {}

    static class Listener implements WebSocket.Listener {
        final StringBuilder message = new StringBuilder();
        final CompletableFuture<String> received = new CompletableFuture<>();
        final CompletableFuture<Boolean> closed = new CompletableFuture<>();

        @Override
        public void onOpen(WebSocket socket) {
            socket.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket socket,
                                         CharSequence part, boolean last) {
            message.append(part);
            socket.request(1);
            if (last) {
                received.complete(message.toString());
            }
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public CompletionStage<?> onClose(WebSocket socket,
                                          int code, String reason) {
            closed.complete(code == WebSocket.NORMAL_CLOSURE);
            return CompletableFuture.completedFuture(null);
        }

        @Override
        public void onError(WebSocket socket, Throwable error) {
            received.completeExceptionally(error);
            closed.completeExceptionally(error);
        }
    }

    static String headers(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        byte[] suffix = new byte[]{13, 10, 13, 10};
        while (b.size() < 8192) {
            int next = in.read();
            if (next == -1) {
                throw new IOException("EOF before HTTP headers");
            }
            b.write(next);
            byte[] data = b.toByteArray();
            if (data.length >= 4) {
                boolean end = true;
                for (int i = 0; i < 4; i++) {
                    end &= data[data.length - 4 + i] == suffix[i];
                }
                if (end) {
                    return new String(data, StandardCharsets.ISO_8859_1);
                }
            }
        }
        throw new IOException("Oversized headers");
    }

    static String headerValue(String request, String field) {
        for (String line : request.split("\r\n")) {
            int colon = line.indexOf(':');
            if (colon > 0 &&
                    line.substring(0, colon).equalsIgnoreCase(field)) {
                return line.substring(colon + 1).trim();
            }
        }
        return "";
    }

    static void sendFrame(OutputStream out, int opcode,
                          boolean last, byte[] payload) throws IOException {
        if (payload.length > 125) {
            throw new IOException("Demo only supports small frames");
        }
        out.write((last ? 128 : 0) | opcode);
        out.write(payload.length); // Server frames are not masked.
        out.write(payload);
        out.flush();
    }

    record Frame(int opcode, byte[] payload) {}
    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();
        if (first < 0 || second < 0 || (second & 128) == 0) {
            throw new IOException("Missing masked client frame");
        }
        int length = second & 127;
        if (length > 125) {
            throw new IOException("Frame too large for this demo");
        }
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(length);
        if (mask.length != 4 || data.length != length) {
            throw new IOException("Incomplete frame");
        }
        for (int i = 0; i < data.length; i++) {
            data[i] ^= mask[i & 3];
        }
        return new Frame(first & 15, data);
    }

    static ServerResult serve(ServerSocket listener) throws Exception {
        try (Socket peer = listener.accept()) {
            peer.setSoTimeout(8000);
            InputStream in = peer.getInputStream();
            OutputStream out = peer.getOutputStream();
            String request = headers(in);
            String key = headerValue(request, "Sec-WebSocket-Key");
            if (key.isEmpty()) {
                throw new IOException("No WebSocket key");
            }
            String offered = headerValue(request, "Sec-WebSocket-Protocol");
            boolean hasOffer = offered.contains("chat.v2")
                    && offered.contains("chat.v1");
            boolean hasHeader = "present".equals(
                    headerValue(request, "X-Demo"));
            byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                    (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                            .getBytes(StandardCharsets.US_ASCII));
            String accept = Base64.getEncoder().encodeToString(digest);
            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept + "\r\n"
                    + "Sec-WebSocket-Protocol: chat.v2\r\n\r\n";
            out.write(response.getBytes(StandardCharsets.ISO_8859_1));
            out.flush();

            Frame sent = readClientFrame(in);
            if (sent.opcode() != 1 ||
                    !"ping".equals(new String(sent.payload(),
                            StandardCharsets.UTF_8))) {
                throw new IOException("Unexpected request message");
            }
            sendFrame(out, 1, false,
                    "ACK:".getBytes(StandardCharsets.UTF_8));
            sendFrame(out, 0, true,
                    "ping".getBytes(StandardCharsets.UTF_8));

            Frame close = readClientFrame(in);
            if (close.opcode() != 8) {
                throw new IOException("Expected close");
            }
            sendFrame(out, 8, true,
                    new byte[]{3, (byte) 232}); // Status 1000.
            return new ServerResult(hasOffer, hasHeader, true);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        try (ServerSocket server = new ServerSocket(0, 1, local)) {
            server.setSoTimeout(8000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<ServerResult> handled =
                        worker.submit(() -> serve(server));
                Listener receiving = new Listener();
                URI target = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/chat");
                WebSocket socket = HttpClient.newHttpClient()
                        .newWebSocketBuilder()
                        .header("X-Demo", "present")
                        .subprotocols("chat.v2", "chat.v1")
                        .connectTimeout(Duration.ofSeconds(5))
                        .buildAsync(target, receiving)
                        .get(8, TimeUnit.SECONDS);

                socket.sendText("ping", true).get(8, TimeUnit.SECONDS);
                String text = receiving.received.get(8, TimeUnit.SECONDS);
                socket.sendClose(WebSocket.NORMAL_CLOSURE, "")
                        .get(8, TimeUnit.SECONDS);
                boolean closed = receiving.closed.get(8, TimeUnit.SECONDS);
                ServerResult result = handled.get(8, TimeUnit.SECONDS);

                System.out.println("Selected subprotocol: "
                        + socket.getSubprotocol());
                System.out.println("Received: " + text);
                System.out.println("Close status 1000: " + closed);
                System.out.println("Server saw both offers: "
                        + result.offered());
                System.out.println("Server saw custom header: "
                        + result.customHeader());
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
```

Compile/run with JDK 17 or later:

```sh
javac -encoding UTF-8 WebSocketBuilderLoopback.java
java WebSocketBuilderLoopback
```

Verified stdout:

```text
Selected subprotocol: chat.v2
Received: ACK:ping
Close status 1000: true
Server saw both offers: true
Server saw custom header: true
```

**Why this is not a fake test:**

1. The server opens a **real TCP socket on 127.0.0.1**, and the JDK client actually sends an HTTP handshake and actually waits for `101 Switching Protocols` with `Sec-WebSocket-Accept`.
2. The server reads both `Sec-WebSocket-Protocol` and `X-Demo` headers. The two `Server saw ... true` lines show that the builder included the **subprotocol offers and additional header** in the handshake.
3. The server decides `Sec-WebSocket-Protocol: chat.v2`. Only **after buildAsync succeeds** does the client read `socket.getSubprotocol()` and print the value **accepted by the server**.
4. The WebSocket client **masks** frames sent to the server. The demo server reads the four mask bytes and XORs the payload to extract `ping`. The server sends unmasked frames per RFC 6455 rules.
5. The server returns the message using a **non-FIN initial text frame**, followed by a **FIN continuation frame**. `Listener.onText` assembles all parts until `last=true` to produce `ACK:ping`. Even if the JDK merges or splits callbacks differently, the logic remains correct.
6. `request(1)` in `onOpen` and after each `onText` ensures demand for the next callback, including Close.
7. `sendClose(WebSocket.NORMAL_CLOSURE,"")` sends close code 1000; the server replies with close, and the listener receives `onClose`. Do not confuse `sendClose` with Java `AutoCloseable.close()`.

**Demo scope:** the server only handles small payloads (up to 125 bytes), one client, one text message, and one Close; it does not check all RFC frame sizes/fragmentation/control semantics, and has no TLS, auth, concurrent clients, or production backpressure. **Do not use the `serve` class as an Internet-facing WebSocket server**. SHA-1 in the demo only serves the RFC handshake formula, not as a recommended password-storage algorithm.

## 16. Java 17+ Example 2: handshake rejected by server with HTTP 403

`buildAsync` does not always succeed. If the endpoint rejects the opening handshake, the default `HttpClient` can complete the future exceptionally with **`WebSocketHandshakeException`**, giving access to the **`HttpResponse<?>`** of the failed handshake.

The file **`WebSocketHandshakeRejected.java`** sets up a loopback TCP server that reads the HTTP handshake and returns `HTTP/1.1 403 Forbidden` instead of `101`. The client calls `buildAsync` and uses `Future.get`, catches `ExecutionException`, checks that the root cause is `WebSocketHandshakeException`, and prints the status:

```java
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.WebSocket;
import java.net.http.WebSocketHandshakeException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class WebSocketHandshakeRejected {
    static void reject(ServerSocket server) throws Exception {
        try (Socket peer = server.accept()) {
            peer.setSoTimeout(8000);
            InputStream in = peer.getInputStream();
            ByteArrayOutputStream headers = new ByteArrayOutputStream();
            while (headers.size() < 8192) {
                int current = in.read();
                if (current == -1) {
                    throw new IllegalStateException("No HTTP request");
                }
                headers.write(current);
                String value = headers.toString(
                        StandardCharsets.ISO_8859_1);
                if (value.endsWith("\r\n\r\n")) {
                    break;
                }
            }
            OutputStream out = peer.getOutputStream();
            out.write(("HTTP/1.1 403 Forbidden\r\n"
                    + "Content-Length: 0\r\n"
                    + "Connection: close\r\n\r\n")
                            .getBytes(StandardCharsets.US_ASCII));
            out.flush();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[]{127, 0, 0, 1});
        try (ServerSocket server = new ServerSocket(0, 1, local)) {
            server.setSoTimeout(8000);
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<?> served = worker.submit(() -> {
                    reject(server);
                    return null;
                });
                URI endpoint = URI.create("ws://127.0.0.1:"
                        + server.getLocalPort() + "/denied");
                CompletableFuture<WebSocket> open =
                        HttpClient.newHttpClient()
                                .newWebSocketBuilder()
                                .subprotocols("chat.v1")
                                .connectTimeout(Duration.ofSeconds(5))
                                .buildAsync(endpoint,
                                        new WebSocket.Listener() {});
                boolean rejected = false;
                int status = -1;
                try {
                    open.get(8, TimeUnit.SECONDS);
                } catch (ExecutionException error) {
                    if (error.getCause()
                            instanceof WebSocketHandshakeException handshake) {
                        rejected = true;
                        status = handshake.getResponse().statusCode();
                    } else {
                        throw error;
                    }
                }
                served.get(8, TimeUnit.SECONDS);
                System.out.println("Handshake rejected: " + rejected);
                System.out.println("HTTP status: " + status);
                System.out.println("WebSocket available: "
                        + (open.isDone() && !open.isCompletedExceptionally()));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
```

Compile/run:

```sh
javac -encoding UTF-8 WebSocketHandshakeRejected.java
java WebSocketHandshakeRejected
```

Verified stdout:

```text
Handshake rejected: true
HTTP status: 403
WebSocket available: false
```

`WebSocketHandshakeException.getResponse().statusCode()` helps distinguish whether the server returned 403, 401, 404, a redirect, or an HTTP status not accepted for an upgrade. However, **do not log full sensitive headers/bodies** just to debug auth errors. Some errors occur **before an HTTP response exists**, such as DNS/TCP/TLS failures, in which case the cause is `IOException`/TLS exception/timeout rather than necessarily `WebSocketHandshakeException`.

Do not blindly retry every 401/403: you need to fix credentials/permissions/Origin/middleware first. Do not treat 403 as just a network outage. In the demo, the code verifies that the future does not provide a socket after the handshake is rejected.

## 17. Why doesn't the Java client API have a built-in WebSocket server?

`java.net.http.WebSocket` is defined by JDK 17 as a **WebSocket Client**; JDK `HttpClient.newWebSocketBuilder()` only creates a **client builder**. `jdk.httpserver.HttpServer` supports an HTTP server for HTTP examples, but it is not a built-in WebSocket server framework guaranteed to handle full upgrade/framing.

Therefore, to have a **self-contained example with no external libraries**, the demo uses `ServerSocket` and implements minimal RFC 6455 handshake, masking, and a few frames. This choice has two limitations:

- It does not handle all large frames/fragmentation, rate-limiting, invalid UTF-8, ping/pong, compression, authentication, concurrent sessions, TLS, or complex graceful shutdown.
- The demo is suitable as an **educational test fixture for builder and subprotocols**, not as a production server implementation template.

In real applications, use a proven WebSocket server/framework that supports RFC 6455, TLS, admission controls, origin validation, client authentication, and quotas. The fact that the Java client API supports `WebSocket.Builder` **does not** mean it is meant for accepting server-side connections.

## 18. Explicit error handling and connection states

A WebSocket client needs to handle at least three error categories:

| Phase | Example errors | How to handle |
| --- | --- | --- |
| **Before upgrade** | DNS/TCP fail, TLS cert mismatch, timeout | Configure endpoint/trust, bounded retries if policy allows |
| **During handshake** | 401/403/404, 426/invalid 101, invalid subprotocol | Inspect `WebSocketHandshakeException` or selected protocol; fix auth/routing |
| **After connected** | Peer close, I/O error, server restart, heartbeat timeout, payload overflow | Handle `onClose/onError`, clean up, mark session state, controlled reconnect/replay |

Normal completion of `buildAsync` **only confirms that the WebSocket opening handshake succeeded**. It does not guarantee the connection will last forever; the server may send Close immediately afterward or the network may drop.

When `onError` is called, it is the terminal callback for that socket per the JDK API. Do not create a loop calling `ws.sendText` directly inside `onError`. Record that the connection failed, clean up pending sends, and open a new connection if policy dictates.

When `onClose` is called, input is already closed; this terminal callback carries the status code and reason. Do not assume every Close is 1000: the server can send other codes, and network failures can surface via `onError` without a complete close handshake.

## 19. `sendClose` and `abort` are not the same

`WebSocket` in Java 17 has two independent directions: **input** and **output**:

- `sendClose(statusCode, reason)` **initiates an orderly close of output** with a Close message. The method returns `CompletableFuture<WebSocket>`, meaning sending Close is also asynchronous. **It does not immediately close input**; wait for the peer's Close or an error/abort.
- `abort()` closes input and output **abruptly**, without performing the normal close handshake. Use it when the close deadline expires, a critical error occurs, or an emergency stop is needed.
- `isOutputClosed()` and `isInputClosed()` report the state of both directions. Once closed, they do not reopen; reconnecting creates a new `WebSocket` instance.
- `WebSocket.NORMAL_CLOSURE` is status code **1000**. `sendClose` also validates valid close codes and a UTF-8 reason of at most 123 bytes per Java 17.
- Java 17 `WebSocket` **is not `AutoCloseable`**; do not write `try (WebSocket ws = ...)` expecting a `close()` like a TCP Socket.

A production application should have a **deadline for graceful close**: send Close, wait for `onClose` for a reasonable duration, then call `abort()` if the peer does not respond. Do not wait on futures/close callbacks without a timeout during critical shutdown tasks.

## 20. Ping, Pong, heartbeat, and health checks

WebSocket has `Ping` and `Pong` control frames. Java 17 API:

```java
// Illustrative snippet: ws is a connected WebSocket.
ByteBuffer probe = ByteBuffer.wrap(new byte[]{1, 2, 3});
ws.sendPing(probe).whenComplete((ignored, error) -> {
    if (error != null) {
        reportTransportFailure(error);
    }
});
```

Non-standalone snippet: missing class/imports and `reportTransportFailure`. Key points:

- `sendPing` completes when the **ping send operation** succeeds on the client, **not** when the server has replied with Pong.
- The Java WebSocket implementation **automatically sends a Pong in response to a received Ping** per the protocol, so the app usually does not need to manually call `sendPong` when `onPing` is invoked.
- `sendPing/sendPong` payload is at most **125 bytes**.
- `onPong` can be used to track liveness/RTT using app-managed IDs/timestamps, while maintaining appropriate timeout policies, false-positive handling, and a monotonic clock.
- `onPing/onPong` are also **receive callbacks** subject to `request(n)` demand; do not let demand run out and prevent heartbeat logic from progressing as designed.
- `connectTimeout` does not replace heartbeat/idle timeouts for a socket that stays open for hours.

If the server has an idle policy, agree on a heartbeat frequency so as not to flood the server. Implementing pings every few milliseconds to "keep the socket alive" can cause overload.

## 21. Auth, Origin, validation, and subprotocol in real systems

**Subprotocol negotiation is not authorization.** A server returning `chat.v2` only confirms it accepts the **protocol format**; it does not mean the caller is allowed to join every room or send every command.

Layering is needed:

1. **Connection:** use `wss://`, valid TLS, restrict origin/host, and verify reverse proxy upgrades.
2. **Identity:** authenticate session/cookie/bearer token during the handshake or in an application authentication step with timeouts; protect credentials and rotation.
3. **Subprotocol:** the server only picks one of the client's proposed values; the client verifies the selected token matches the message schema.
4. **Message-level authorization:** user A must not be allowed to subscribe/publish to room/tenant B merely by virtue of a successful connection.
5. **Payload validation:** validate text/binary format, max message size, JSON schema, operation IDs, rate limits, and backpressure.
6. **Lifecycle:** handle token expiration, resume/reconnect, auditing, and subscription cleanup when the socket closes.

The server must check `Origin` when browser clients use cookie-based sessions to mitigate cross-site WebSocket hijacking per the threat model; however, **Origin alone is not authentication**. Non-browser clients can send arbitrary headers. Similarly, a JWT/Authorization header in the handshake does not exempt subsequent resource permission checks.

Do not try to "fix" TLS errors by disabling hostname validation or using trust-all. If the client uses `wss://` to a private CA, configure the truststore/`SSLContext` explicitly and verify the server certificate against the proper hostname.

## 22. Backpressure, multi-client, and real-world reconnects

WebSocket is a long-lived connection; you cannot treat each connection as an unbounded fire-and-forget queue.

**Outbound:**

- `sendText/sendBinary` return futures; bound the number of pending messages and total pending bytes. If the producer is faster than the socket can send, the queue will grow.
- Concurrent text/binary sends can conflict with an already pending send. Queue and serialize them to preserve application ordering.
- Do not use completion of `sendText` as a **business ACK**. When at-least-once is required, give each message a `messageId` and server ACK; the client should have an appropriate durable queue/retry window.
- Do not retry infinitely when the server rejects subprotocol/auth; use exponential backoff + jitter and a circuit breaker for network failures.

**Inbound:**

- `request(n)` is credit for **callback invocations**, not an absolute memory cap. A single callback can contain a large fragment; enforce message size limits.
- Do not request more when downstream has no capacity if you use a bounded queue; at the same time, do not forget to request forever, leaving the socket with data while the listener makes no progress.
- Data in `CharSequence/ByteBuffer` only has a lifetime managed by the callback's completion stage; copy it when handing off to a worker that runs after stage completion.
- A listener attached to **multiple sockets** can be invoked concurrently across sockets; `StringBuilder` is not thread-safe for such shared state.

**Reconnect:**

- When a socket fails, build a **new WebSocket.Builder** and new listener/session state; do not mutate an old builder concurrently across threads.
- Use operation/sequence IDs, resume tokens, or a snapshot endpoint if the server supports them; do not assume reconnecting automatically replays all missed messages.
- If a message has side effects, retry based on an idempotency policy rather than blindly calling `sendText` again.

## 23. Twenty common mistakes and how to fix them

1. **Calling `new WebSocket.Builder()`:** `Builder` is an interface; obtain it from `HttpClient.newWebSocketBuilder()`.
2. **Using the same mutable builder from multiple threads:** Builder is not thread-safe; create a separate one per connection.
3. **Thinking `buildAsync` immediately returns a WebSocket:** it returns `CompletableFuture<WebSocket>`.
4. **Treating `subprotocols("v2","v1")` as forcing the server to use v2:** the client proposes preference order, and the server selects.
5. **Checking only `buildAsync` success and ignoring `getSubprotocol()`:** the app's supported protocol might be absent or different.
6. **Putting a bearer token in a subprotocol name:** wrong scope, secret exposure risk, and syntax issues.
7. **Manually adding `Sec-WebSocket-Key` via `builder.header`:** WebSocket protocol headers are managed by the JDK; the API forbids it.
8. **Confusing `connectTimeout` with post-connect idle/read timeout:** separate heartbeats/deadlines are needed.
9. **Not calling `request(n)` in a custom `onOpen`:** the listener may never receive text/binary/close.
10. **Thinking `request(1)` means one complete message:** it grants one callback; a message may be fragmented.
11. **Parsing JSON as soon as `onText` is called even when `last=false`:** you may only have a fragment.
12. **Ignoring `onError` and only waiting for `onClose`:** network errors do not guarantee a close handshake.
13. **Returning a completed `CompletionStage` and retaining `CharSequence/ByteBuffer` for later use:** data may be used past its valid lifetime; copy or hold the stage per contract.
14. **Sending multiple text/binary messages without serialization while pending:** can cause `IllegalStateException` and wrong ordering.
15. **Treating `sendText` future completion as server processing:** there is no business ACK.
16. **Calling `sendClose` and assuming input is already closed:** `sendClose` closes output; input requires peer close/error/abort.
17. **Using `abort` as normal graceful shutdown:** `abort` closes immediately and can drop in-flight messages.
18. **Thinking `ws://` is encrypted because WebSocket uses an HTTP handshake:** there is no TLS; use `wss://` for sensitive data.
19. **Assuming Java 17 `java.net.http` includes a production WebSocket server:** the package provides a client, not a full server stack.
20. **Retrying 401/403 handshakes infinitely:** fix tokens, permissions, proxy/origin/subprotocol instead of just backing off.

## 24. Quick troubleshooting table

| Symptom | Possible cause | How to handle |
| --- | --- | --- |
| `buildAsync` future throws `WebSocketHandshakeException`, HTTP 403 | Token/permission/origin/routing rejected | Check `getResponse().statusCode()`, inspect server policy without logging secrets |
| HTTP 404 during handshake | Wrong URI path/reverse proxy upgrade route | Verify `ws(s)://host/path` and routing |
| `HttpTimeoutException` on connect | Handshake/transport did not finish within timeout | Check DNS/TCP/TLS/proxy; do not mistake for idle timeout |
| TLS `SSLHandshakeException` | WSS truststore, hostname, cert chain | Fix TLS trust/identity; do not use trust-all |
| Connected successfully but no `onText` | Overrode `onOpen` and forgot `request(1)` | Add receive demand, check whether server is sending |
| `getSubprotocol()` is empty | Server did not negotiate a subprotocol | Check whether the app requires a subprotocol |
| `getSubprotocol()` is v1, app sends v2 payload | Did not check negotiated version | Branch to the right schema or close connection |
| `sendText` throws `IllegalStateException` | Pending send or invalid message state | Serialize sends and handle `last` properly |
| Only partial text seen | `onText(...,last=false)` is a fragment | Assemble fragments until `last=true` with a memory bound |
| `onError` after flaky network | I/O/remote disconnect | Clean up, reconnect with backoff and replay protocol |
| Socket does not exit on shutdown | Close handshake incomplete or no deadline | `sendClose` + wait for `onClose` + `abort` fallback |
| CPU/RAM grows during realtime stream | Unbounded queue, oversized messages, slow listener | Bounded queues/demand, payload limits, metrics |

Do not rely on a single exception name to guess whether the server processed a business message. Controlled logs on both ends, operation IDs, and subprotocol/HTTP status information may be needed.

## 25. Self-check questions

**1.** Is `WebSocket.Builder` thread-safe? **No.** Intermediate methods mutate the builder; create a separate builder or synchronize externally.

**2.** What does `buildAsync` return? **`CompletableFuture<WebSocket>`**, completing normally when the opening handshake succeeds.

**3.** The client proposes `chat.v2` then `chat.v1`; is it valid for the server to select `chat.v1`? **Yes**, if the token is in the offered list and policy/implementation allows it; the client must use the v1 schema.

**4.** Does `getSubprotocol()` returning `""` prove the handshake failed? **No.** The handshake may have succeeded without negotiating a subprotocol.

**5.** Does `request(1)` allow reading one complete WebSocket message? **No**, it grants one receive callback invocation; a text message may be fragmented.

**6.** `onText(data,false)` returns an incomplete JSON chunk. Should you parse it immediately? **No** if the format assumes a complete JSON document/message; assemble until `last=true`.

**7.** If `onOpen` is overridden without calling `request`, what can happen? **The connection may succeed with no receive callbacks**, because initial demand is 0.

**8.** After the `sendText` future completes, can you be sure the server wrote to the database? **No.** You need a business ACK, operation ID, and server semantics.

**9.** Does `sendClose` close input immediately? **No.** It initiates closing output; input waits for peer close/error or `abort`.

**10.** Why does the demo use `ServerSocket` to handle frames manually? **Because JDK `java.net.http.WebSocket` provides a client API, not a built-in production WebSocket server; the demo server is only a minimal RFC 6455 test fixture.**

**11.** When `buildAsync` fails due to HTTP 403, where can you inspect the HTTP status? **`WebSocketHandshakeException.getResponse().statusCode()`**.

**12.** Do `wss://` and `subprotocols("chat.v2")` have the same responsibility? **No.** WSS protects transport with TLS; subprotocol defines application message semantics.

## 26. Implementation checklist and conclusion

When reviewing a Java 17 WebSocket client:

1. **Choose the right URI:** `ws://` for loopback labs, `wss://` for sensitive data; proper TLS/hostname trust.
2. **Use an `HttpClient` with appropriate policy:** proxy, `SSLContext`, executor; do not mix tenant authentication.
3. **Create a separate `WebSocket.Builder` per connection:** do not share a mutable builder concurrently.
4. **Add only allowed headers:** do not manually set WebSocket protocol headers; protect tokens/cookies.
5. **Propose subprotocols in preference order:** only offer formats the app actually supports.
6. **Set a finite `connectTimeout`** and an appropriate future wait deadline; do not confuse with post-connect liveness timeout.
7. **Handle both normal and exceptional `buildAsync`:** classify handshake HTTP status, TLS, timeout, and configuration errors.
8. **Check `getSubprotocol()`:** do not send payloads in the wrong schema when the server selects a different/missing one.
9. **Ensure Listener has `onOpen` `request(n)` and `onError/onClose` cleanup:** avoid stalled channels due to exhausted demand.
10. **Handle fragments according to `last`:** do not mistake one callback for one business message; bound sizes.
11. **Serialize sends and control outbound/inbound queues:** do not let pending messages grow unboundedly.
12. **Manage the `CompletionStage` lifetime of received data:** do not retain buffers after callback completion without copying.
13. **Have heartbeat, idle deadline, close handshake, and abort fallback:** do not leave sockets silently dead.
14. **Have a reconnect policy and replay/idempotency if needed:** WebSocket transport does not guarantee persistence/exactly-once.
15. **Have message-level validation/authorization, logs/metrics:** handshake and subprotocol do not replace business permissions.
16. **Test positive and negative handshakes:** subprotocol selected, absent, HTTP 401/403, timeout, malformed frame, server close, and reconnect.

**Conclusion:** `WebSocket.Builder` configures **a single handshake** and `buildAsync` returns the result **asynchronously**. `subprotocols` only provides options in preference order; **`getSubprotocol()`** confirms the final selection. Once connected, all receiving/sending/closing still follows futures, listener callbacks, `request(n)` demand, and lifecycle rules. Keeping a clear boundary between transport, subprotocol, authentication, and business logic is essential for a Java WebSocket client to operate correctly and securely.

### Official References

- [Java SE 17 — WebSocket.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html)
- [Java SE 17 — HttpClient.newWebSocketBuilder()](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — WebSocket (sendText, request, sendClose, abort, getSubprotocol)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html)
- [Java SE 17 — WebSocket.Listener](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html)
- [Java SE 17 — WebSocketHandshakeException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).
