# When Should You Use WebSocket? Long-Lived Bidirectional Communication with Java 17+

## 1. The Short Answer: Choose WebSocket When Both Sides Need to Send Proactively Multiple Times

**WebSocket** is appropriate when **the client and server must keep a connection open longer than a single request**, **both sides can proactively push messages**, and the application needs **near real-time responsiveness** with repeated exchanges: chat, live collaboration, continuous status events, interactive control, monitoring dashboards, games with a reliable message channel, or a long-lived administration/orchestration session.

"Bidirectional" does not merely mean "client sends a request, server returns a response." Over an already open WebSocket, **the server can send new messages even when the client has not issued a new request**, and the client can send messages at any time. Neither side **has to establish a new HTTP request for each message**.

~~~text
Traditional HTTP request/response:

Client            Server
  | --- GET -----> |
  | <--- 200 ----- |
  |                |
  | --- GET -----> |   poll again (polling)
  | <--- 200 ----- |

WebSocket:

Client            Server
  | - Upgrade ---> |
  | <--- 101 ----- |   WebSocket connection established
  | <--- event A - |   server pushes proactively
  | ---- cmd 1 --> |   client sends proactively
  | ---- cmd 2 --> |
  | <--- event B - |
  | <--- ack 2 --- |
  | <--- event C - |
  | -- Close ----> |
  | <--- Close --- |   close handshake
~~~

**Not every requirement for updates calls for WebSocket.** If the client only needs to call an API once, fetch a cacheable list, submit a form, download a file, or receive **one-way** events from the server via a simple mechanism, standard HTTP, polling/long-polling, or **Server-Sent Events (SSE)** may be the right choice and easier to operate.

This lesson focuses on: **signs of when to use or not use WebSocket**, how a long-lived full-duplex channel works, differences from REST, polling, and SSE; limits regarding delivery guarantees, security, state, backpressure, heartbeat, reconnect, and scaling; and a **Java 17+** demo using the built-in JDK WebSocket client to connect to a minimal loopback server.

## 2. What Is WebSocket Really?

According to RFC 6455, WebSocket is a communication protocol over **a single bidirectional connection**, typically using TCP as the transport. It starts with an **HTTP/1.1 Upgrade handshake**, after which both sides switch to exchanging **WebSocket frames** instead of every message being a full HTTP response.

Some essential characteristics:

1. **Full-duplex:** the client and server can transmit data **simultaneously** over the same session; the server does not need to wait for the client to ask before sending.
2. **Message-oriented:** WebSocket has **text messages** (UTF-8) and **binary messages**, rather than just an unframed raw byte stream like raw TCP.
3. **Connection-oriented and stateful at the session layer:** after the handshake, each endpoint holds the socket/session, buffers, authentication state, and associated subscriptions; a connection can last from a few seconds to many hours depending on network conditions and the application.
4. **Ordering within a single connection:** because the common transport is TCP, bytes are delivered in order rather than reordered like UDP datagrams. However, that **does not provide an exactly-once guarantee across disconnect/reconnect**.
5. **An event channel, not an automatic RPC API:** WebSocket does not define out of the box "call method/receive status 200," JSON schemas, request IDs, ACKs, or retries. Those rules must be **designed by the application** or handled via an appropriate protocol/framework.

### 2.1. Is "WebSocket Stays Always Open" True?

No. A WebSocket *can* be kept open for a long time, but **there is no guarantee it stays open forever**. Wi-Fi network switches, device sleep, mobile apps going to the background, proxy idle timeouts, deployment restarts, load balancer rotations, NAT mapping expiry, server overload, or peer crashes can all cause the connection to close. Therefore, "long-lived" means **the design goal of the session**, not an SLA that the socket will never drop.

A production application needs to **detect stale connections, reconnect in a controlled manner, re-authenticate, and restore state/subscriptions**, rather than assuming the same TCP socket will survive for the entire user session.

### 2.2. A Message Is Not the Same as a Frame

WebSocket splits data into frames. A **message** may contain **one frame or multiple continuation frames**. APIs may deliver message parts incrementally (for example, Java `WebSocket.Listener.onText(..., last)`), so a parser must not assume "each callback = one complete message."

~~~text
WebSocket TEXT message "abcdef"
   |
   +-- frame 1: "abc" (FIN=0)
   +-- frame 2: "def" (continuation, FIN=1)

Java Listener.onText may be called multiple times:
   onText(ws, "abc", false)
   onText(ws, "def", true)
   -> assembled into one application message "abcdef"
~~~

**Control frames** such as Ping/Pong/Close have their own rules. Do not mix bytes from two text messages just because they arrive on the same connection; rely on the message boundary/`last` flag provided by the API.

## 3. When Is WebSocket Truly a Good Fit?

### 3.1. Chat, Messaging, and Conversation Events

One person sends a message in a chat room; others need to see it immediately without clicking refresh. Clients may also send typing indicators, read receipts, reactions, presence, or room join/leave requests. **Continuous bidirectional traffic, many small messages, and unsolicited events from the server** are a classic fit.

Example application messages:

~~~json
{"type":"chat.send","roomId":"java","requestId":"req-17","text":"Hello everyone"}
{"type":"chat.message","roomId":"java","sequence":381,"text":"Hello everyone"}
{"type":"presence.changed","userId":"u42","online":true}
~~~

Each JSON line above is an **application-defined format example**, not the default WebSocket frame format. The server still needs chat room authorization, message limits, and spam protection. If offline messages must be delivered to absent users, they must be persisted in a database/queue and replayed when the user connects; WebSocket **does not store offline messages automatically**.

### 3.2. Live Collaboration: Documents, Whiteboards, Cursors

In a document edited by multiple people simultaneously, each action can generate a small event: inserting characters, editing cells, moving cursors, user status. The server distributes changes to many participants within a short time.

**WebSocket is only the transport channel for operations.** It **does not automatically solve** conflict resolution, OT (Operational Transformation), CRDTs, locking, version vectors, ordering across multiple servers, or durable history. The application must choose a consistency model and a recovery mechanism after disconnect.

### 3.3. Live Dashboards, Trading Quotes, In-Flight Order Status

Market prices, operational metrics, task logs, delivery statuses, or job monitoring sessions can emit updates **at any moment**. Having the server proactively push updates avoids heavy polling.

However, ask: does the dashboard only **receive** updates, or does it also need to send interactive commands continuously? If it is strictly one-way receiving, **SSE** is often simpler; WebSocket is more advantageous when you need to change subscriptions, control the server, update filters, or exchange bidirectional traffic frequently over the session.

For financial markets or critical data, you also need sequences, snapshot/replay, gap detection, rate limiting, and a clock policy. **An always-open channel does not guarantee every update is processed by the application exactly once.**

### 3.4. Multiplayer Games and Interactive Control

WebSocket fits many **turn-based game commands or state updates that require reliability/ordering**: in-game chat, matchmaking, lobbies, session control, word games, board games, or control events that are not overly sensitive to head-of-line blocking.

For real-time games requiring **ultra-low latency and willing to drop stale updates** (for example, character positions 60 times/second), TCP's reliability/ordering can cause a lost segment to stall newer data behind it. In such cases, appropriately configured UDP/QUIC DATAGRAM/WebRTC DataChannel may make more sense, depending on the platform. Do not assume WebSocket is the "fastest protocol" for every game.

### 3.5. Remote Terminals, Device Interaction, and Control Sessions

A remote terminal or debugging task has commands sent by the client and continuous output pushed by the server. A log streaming session where the user can **pause/resume, change filters, and send commands** is a useful full-duplex case.

Strict permission control is required: every command must be authorized, audited, input-validated, and subject to rate limits/timeouts. WebSocket only carries bytes/messages; it does not make dangerous shell commands safe.

### 3.6. Long-Running Job Tracking and Progress Updates

The client starts an analysis task, and the server pushes `started`, `progress`, `warning`, `completed`. If the client also has `pause`, `resume`, `cancel` buttons and priority changes over the same channel, WebSocket can be very convenient.

However, if you only need to **receive one-way progress**, SSE or HTTP polling at a reasonable interval may be less complex. For jobs lasting many hours, the canonical state must be stored on the server; if the WebSocket drops, the job **should not vanish**.

### 3.7. Systems Requiring Dynamic Subscriptions

The client can send:

~~~json
{"type":"subscribe","channels":["orders.123","alerts"]}
{"type":"unsubscribe","channels":["alerts"]}
{"type":"filter.update","severity":"warning"}
~~~

The server proactively pushes events belonging to the authorized subscriptions. This is a strength when **subscriptions change rapidly**: the client can modify what it wants to receive right on the same session. Still, the server must check ACLs **on every subscribe**, rather than assuming the user is authorized just because they are connected.

## 4. When NOT to Use WebSocket Just to "Be Modern"

| Need | Often Simpler Solution | Why |
| --- | --- | --- |
| GET a profile or list | HTTP GET + caching, ETag | No requirement for continuous server push |
| POST a form, create an order, PUT a resource | REST/HTTP API | Convenient methods, status codes, idempotency, caching, proxies/logs |
| One-way notifications from server to browser | SSE (`EventSource`) | Simple HTTP stream, built-in event IDs/reconnect at browser API level |
| Updates every few tens of seconds or minutes | Reasonable HTTP polling | Avoids managing thousands of stateful sockets |
| Waiting for a job to finish with few updates | Long polling/SSE/periodic GET | Full-duplex may be unnecessary |
| Uploading/downloading very large files | HTTP streaming, multipart/resumable upload | HTTP supports progress, range requests, retries, and CDNs well |
| Public data meant to be cached at a CDN | HTTP GET/Cache-Control | WebSocket messages do not pass through HTTP object caches automatically |
| Streaming video/audio to viewers | HLS/DASH/WebRTC/RTP as required | WebSocket does not handle codecs, congestion/jitter, or media semantics |
| Real-time media/video calls | WebRTC | Provides NAT traversal, media transports, and appropriate jitter handling |
| Receiving webhooks between backends | HTTPS webhook/event queue | No need to maintain a bidirectional connection from the receiver |
| Backend tasks with transactions and high durability | Queue/broker + HTTP/RPC | WebSocket does not replace persistence/transactions |

**Design principle:** choose the simplest protocol that satisfies **flow direction, frequency, latency, reliability, scalability, and operational cost**. Keeping a WebSocket open "just in case" carries non-trivial costs in sockets, memory, auth state, heartbeats, and reconnects.

## 5. Comparing WebSocket with HTTP, Polling, SSE, and Other Options

| Criterion | HTTP request/response | Short polling | Long polling | SSE | WebSocket |
| --- | --- | --- | --- | --- | --- |
| Primary direction | Client calls, server responds | Client asks repeatedly | Client asks, server waits for event then responds | Server → client over one HTTP response stream | **Client ↔ server** |
| Server pushes proactively between requests | Not in the simple model | No | Responds to a hanging request | **Yes**, one-way | **Yes**, two-way |
| Client sends messages proactively after setup | Must create a request | Next request | Next request | Uses another HTTP request | **Sends on the same connection** |
| Overhead with frequent continuous messages | Many requests/headers | Many empty requests | Many request cycles | Stream stays open | Small frames on an open connection |
| Ease of use with HTTP caches/CDNs | Very good | Depends on response | More complex | Proxy-dependent; not standard object caching | No per-message HTTP caching |
| Resume/replay capability | Request/API-based | API-based | API-based | Browser has `Last-Event-ID` if server designs IDs | **Application must design its own** |
| Long-lived server connection state | Usually lower | Low/fluctuating | Has waiting requests | Has open streams | Has open WebSocket sessions |
| Best suited for | CRUD/reading resources | Infrequent, simple changes | Irregular events, without WebSocket | One-way live feeds | Continuous two-way interactive communication |

### 5.1. How Does SSE Differ from WebSocket?

**Server-Sent Events** use an HTTP response with media type `text/event-stream`; the server pushes text events down to the browser, while the client must use separate HTTP requests to send commands. The browser's `EventSource` has built-in auto-reconnect behavior and resends the last event ID in supported scenarios.

If a dashboard only needs a "new events available" feed, SSE is usually enough. If the application needs to send **many small commands, subscription controls, typing indicators, or continuous interactive state**, WebSocket provides a more natural bidirectional channel.

SSE does not make events durable on its own: the server must still store history if replay from an event ID is desired. The same applies to WebSocket, except WebSocket lacks a built-in `Last-Event-ID` mechanism like the SSE API.

### 5.2. WebSocket and HTTP/2 / HTTP/3

The basic handshake described here is WebSocket **RFC 6455 over HTTP/1.1 Upgrade**. There is a mechanism to open WebSocket over **HTTP/2 extended CONNECT** (RFC 8441) in supported environments, but you cannot assume every proxy or Java client automatically uses or supports that mode. The concept of **a long-lived bidirectional session** remains the key architectural decision.

Some systems use gRPC bidirectional streaming over HTTP/2 in the backend. For Java-to-Java backends, gRPC streaming has schemas/service contracts and dedicated tooling that sometimes fit better than WebSocket; for direct browser access, traditional gRPC streaming capabilities differ from WebSocket. **HTTP/2 multiplexing does not automatically turn REST requests into WebSocket.**

### 5.3. WebSocket and WebRTC/QUIC DATAGRAM

WebSocket typically runs over a **reliable ordered stream** (TCP). Other transport/datagram APIs can prioritize latency and allow packet loss, or provide multiple independent streams. If a system genuinely needs to drop stale updates rather than wait for retransmission, evaluate WebRTC DataChannel/QUIC based on your environment and libraries.

Do not call WebSocket "UDP for the web," do not assume it provides NAT traversal for P2P, and do not treat WebSocket as an automatic solution for media codecs or real-time control signals with ultra-tight deadlines.

## 6. How Does a WebSocket Connection Work?

### 6.1. Basic HTTP Upgrade Handshake

Over HTTP/1.1, the client proposes switching protocols:

~~~http
GET /realtime HTTP/1.1
Host: example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
~~~

If the server accepts per RFC 6455, it can respond:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
~~~

The example above uses the well-known key/accept pair from RFC 6455 for illustration. `Sec-WebSocket-Accept` is computed from the key and a magic GUID. **This handshake is not authentication:** any client can generate a valid key on its own. When an application requires login, it must use sessions/tokens/authorization with real permission checks.

Once the handshake succeeds, the endpoints switch to **WebSocket frames**. Do not continue sending individual JSON messages as regular HTTP `POST /realtime` requests over the upgraded socket.

### 6.2. ws:// and wss://

- `ws://`: WebSocket over a connection without TLS protection on the WebSocket URL; suitable for **loopback demos**.
- `wss://`: WebSocket over TLS, appropriate for real data over the Internet; requires certificate/trust/hostname verification—do not disable validation just to force a connection.

An HTTPS page in a browser is normally not allowed to connect to an insecure `ws://` endpoint due to mixed-content policies. For real deployments, use `wss://`, ensure the reverse proxy allows upgrades, and configure idle, keepalive, and close timeouts properly.

### 6.3. WebSocket Frames Are Not HTTP Messages

After the handshake, payloads use common opcodes:

| Opcode | Meaning | Notes |
| --- | --- | --- |
| `0x1` | Text frame | Message payload is UTF-8, may be fragmented |
| `0x2` | Binary frame | Byte array/binary payload |
| `0x0` | Continuation frame | Subsequent part of a fragmented message |
| `0x8` | Close control frame | Close handshake and close status/reason |
| `0x9` | Ping control frame | Protocol-level liveness check |
| `0xA` | Pong control frame | Response to Ping or corresponding notification |

In WebSocket RFC 6455, **client-to-server frames must be masked**; server-to-client frames **must not be masked**. Masking **is not encryption** and does not replace TLS: it is a protocol-specific framing/protection mechanism. Control frames have strict length and fragmentation constraints.

The JDK's `WebSocket.Listener` helps the client manage frames, masking, handshakes, and callbacks; you **do not need to manually construct masked bytes** when using the client API. A custom-built server must handle the full RFC, security, and extensions—do not implement one by hand for production.

## 7. Designing an Application Message Protocol over WebSocket

WebSocket guarantees text/binary messages, but **does not define business content**. An application-level JSON envelope might be structured like:

~~~json
{
  "version": 1,
  "type": "order.subscribe",
  "requestId": "req-8f3",
  "channel": "orders/123",
  "lastSeenSequence": 501
}
~~~

The server might send:

~~~json
{
  "version": 1,
  "type": "order.updated",
  "channel": "orders/123",
  "sequence": 502,
  "occurredAt": "2026-11-01T10:00:00Z",
  "payload": {
    "status": "shipped"
  }
}
~~~

This is an **illustrative application-designed schema**, not a mandatory WebSocket RFC format. Fields should be chosen according to real needs:

- `type` classifies the event/command; `version` aids schema compatibility.
- `requestId` correlates commands with ACKs/errors, useful when multiple requests are in flight.
- `sequence` helps detect gaps and resynchronize the event stream.
- `channel`/`topic` represents the subscription, but the server **must check authorization**.
- `occurredAt` helps with observability/time ordering, but **does not replace sequence numbers or clock-safe ordering**.
- `payload` holds domain data, requiring size limits, validation, and sensitive-field controls.

### 7.1. Commands and Acknowledgments

Example:

~~~text
Client -> Server: {"type":"order.cancel","requestId":"q77","orderId":"123"}
Server -> Client: {"type":"ack","requestId":"q77","accepted":true}
Server -> Client: {"type":"order.updated","sequence":503,"status":"cancelled"}
~~~

An "accepted" ACK does not necessarily mean the business operation has **committed**; you must clearly define what an ACK signifies. If the connection drops after sending a command but before receiving the ACK, the client cannot guess whether the command failed. For side effects, you need **idempotency keys, request status lookups, and a transaction policy** for safe retries.

### 7.2. Do Not Rely on a Single WebSocket for System-Wide Ordering

A TCP connection orders bytes. However, if servers A and B both emit events through a pub/sub, sources update across multiple partitions, or a client reconnects to a different node, **global ordering** does not emerge automatically. You must define per-topic/per-entity ordering, origin sequence/version numbers, and how stale events are handled.

### 7.3. JSON or Binary?

- JSON text: easy to debug, clear schema, well-suited for small commands/events.
- Binary (protobuf, CBOR, or a custom format): can reduce byte size and parsing CPU under certain conditions; requires versioning/schema and validation checks.
- Do not use binary as an excuse to skip input validation; the server must always check type, size, permissions, and rate limits.
- Do not push multi-gigabyte files over WebSocket just because it supports binary. HTTP streaming/resumable uploads usually have a much better ecosystem.

## 8. Java 17 Provides a WebSocket Client, Not an Equivalent High-Level WebSocket Server

Since Java 11, the `java.net.http` module includes:

- `HttpClient.newWebSocketBuilder()` to create a builder.
- `WebSocket.Builder.buildAsync(URI, WebSocket.Listener)` to start the handshake asynchronously and obtain a `CompletableFuture<WebSocket>`.
- `WebSocket.sendText(text, last)`, `sendBinary(ByteBuffer, last)`, `sendPing`/`sendPong`, and `sendClose`.
- `WebSocket.Listener` with `onOpen`, `onText`, `onBinary`, `onPing`, `onPong`, `onClose`, and `onError`.

**Common point of confusion:** Standard JDK 17 includes a **WebSocket client API**, but **does not have an equivalent high-level WebSocket server in `java.net.http`**. Java's simple `com.sun.net.httpserver.HttpServer` does not provide WebSocket server endpoints out of the box. For a real server, you typically use Jakarta WebSocket, Spring WebSocket, Netty, Jetty, Undertow, or another suitable runtime/framework.

WebSocket client example:

~~~java
WebSocket client = HttpClient.newHttpClient()
        .newWebSocketBuilder()
        .buildAsync(URI.create("wss://example.test/live"), listener)
        .join();

client.sendText("hello", true);
~~~

**Illustrative code**, assuming `listener` is an implemented `WebSocket.Listener` and `java.net.URI`, `java.net.http.*` are imported. Do not call `join()` on an event-loop/I/O worker if you can use `thenAccept`/`thenCompose` continuations; the snippet above only demonstrates the order of creating a connection and then sending.

### 8.1. `WebSocket.Listener` Is an Event/Callback API

In the Listener, `onOpen` runs when the WebSocket is established. `onText` can be invoked multiple times for a single message, with the `last` parameter indicating the final part. `onClose` receives the close status code and reason; `onError` reports errors.

Crucially in the JDK API: the listener controls **receive demand** via `webSocket.request(n)`. If you do not request more when needed, the application may stop receiving subsequent data callbacks as expected. Once a complete message arrives, dispatch it to an appropriate processing queue; do not block for long inside callbacks.

### 8.2. `sendText` Completing Is Not a Business Acknowledgment

`client.sendText(text, true)` returns a `CompletableFuture<WebSocket>`. When the future completes, it indicates send progress per the client API contract; **it does not prove the server has persisted the message to a database**. To know that processing succeeded, wait for an **application-level ACK** carrying the corresponding requestId or business result.

### 8.3. `last` Marks the End of a Message, Not the End of the Connection

~~~java
// Send a "hello" message in two parts:
client.sendText("hel", false)
      .thenCompose(ws -> ws.sendText("lo", true));
~~~

This is an illustrative fragment using an already connected `client`. `last=false` means more parts follow in **the same message**, while `last=true` completes the message. It **does not** close the WebSocket. When sending multiple parts, use a continuation chain to avoid overlapping text sends or corrupting message boundaries.

## 9. Self-Contained Java 17+ Example: Standard WebSocket Client and Minimal Loopback Server

To avoid depending on the Internet or public echo services, the following demo builds a **minimal RFC 6455 illustrative server on `ServerSocket`**, then uses the **JDK WebSocket client** to connect. The server:

1. Accepts a single HTTP/1.1 Upgrade request and reads headers up to `\r\n\r\n` with a small size limit.
2. Extracts `Sec-WebSocket-Key` and computes `Sec-WebSocket-Accept` using SHA-1 per the **RFC 6455 handshake requirement** (this is **not** a password hash or payload encryption).
3. Returns `101 Switching Protocols`; reads **one client text frame with FIN=1, length <= 125 bytes**, requiring client masking.
4. Echoes the exact text payload using an **unmasked server text frame**.
5. Reads **one Close frame** from the client, sends a Close frame back, and closes the socket.

The client uses `HttpClient.newWebSocketBuilder()`, `WebSocket.Listener`, `sendText`, and `sendClose`. The server is intentionally limited to demonstrate the wire protocol; **do not use this demo server in production** because it does not fully handle fragmented/extended frames, Unicode validation, TLS, Ping/Pong, Origin/auth, concurrency, rate limiting, or all RFC 6455 edge cases.

Create the file **WebSocketLoopbackDemo.java**:

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

public class WebSocketLoopbackDemo {
    record Frame(int opcode, byte[] payload) {}

    static String readHeaders(InputStream in) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        final String delimiter = "\r\n\r\n";
        int matched = 0;
        int b;

        while ((b = in.read()) != -1) {
            bytes.write(b);
            if (bytes.size() > 8192) {
                throw new IOException("Header too large");
            }

            if (b == delimiter.charAt(matched)) {
                matched++;
                if (matched == 4) {
                    return bytes.toString(StandardCharsets.ISO_8859_1);
                }
            } else {
                matched = b == '\r' ? 1 : 0;
            }
        }

        throw new EOFException("Incomplete HTTP upgrade");
    }

    static String header(String headers, String name)
            throws IOException {
        for (String line : headers.split("\r\n")) {
            int sep = line.indexOf(':');
            if (sep > 0
                    && line.substring(0, sep).trim()
                            .equalsIgnoreCase(name)) {
                return line.substring(sep + 1).trim();
            }
        }
        throw new IOException("Missing HTTP header " + name);
    }

    static Frame readClientFrame(InputStream in) throws IOException {
        int first = in.read();
        int second = in.read();

        if (first < 0 || second < 0) {
            throw new EOFException("Missing frame");
        }
        if ((first & 0x80) == 0) {
            throw new IOException("Demo only supports FIN=1");
        }

        int opcode = first & 0x0f;
        if ((second & 0x80) == 0) {
            throw new IOException("Client frame must be masked");
        }

        int length = second & 0x7f;
        if (length > 125) {
            throw new IOException("Demo only supports short frames");
        }

        byte[] mask = in.readNBytes(4);
        byte[] payload = in.readNBytes(length);
        if (mask.length != 4 || payload.length != length) {
            throw new EOFException("Truncated frame");
        }

        for (int i = 0; i < payload.length; i++) {
            payload[i] ^= mask[i % 4];
        }
        return new Frame(opcode, payload);
    }

    static void writeServerFrame(
            OutputStream out, int opcode, byte[] payload)
            throws IOException {

        if (payload.length > 125) {
            throw new IOException("Too long for demo frame");
        }

        out.write(0x80 | opcode); // FIN=1 + opcode.
        out.write(payload.length); // Server does not mask.
        out.write(payload);
        out.flush();
    }

    static void serveOne(
            ServerSocket listener,
            CompletableFuture<Void> done) {

        try (Socket socket = listener.accept()) {
            socket.setSoTimeout(5000);
            InputStream in = socket.getInputStream();
            OutputStream out = socket.getOutputStream();

            String headers = readHeaders(in);
            if (!headers.startsWith("GET ")) {
                throw new IOException("Expected HTTP GET");
            }
            String key = header(headers, "Sec-WebSocket-Key");

            String acceptInput = key
                    + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
            String accept = Base64.getEncoder().encodeToString(
                    MessageDigest.getInstance("SHA-1")
                            .digest(acceptInput.getBytes(
                                    StandardCharsets.US_ASCII)));

            String response = "HTTP/1.1 101 Switching Protocols\r\n"
                    + "Upgrade: websocket\r\n"
                    + "Connection: Upgrade\r\n"
                    + "Sec-WebSocket-Accept: " + accept
                    + "\r\n\r\n";

            out.write(response.getBytes(StandardCharsets.US_ASCII));
            out.flush();

            Frame text = readClientFrame(in);
            if (text.opcode() != 1) {
                throw new IOException("Expected text frame");
            }
            writeServerFrame(out, 1, text.payload());

            Frame close = readClientFrame(in);
            if (close.opcode() != 8) {
                throw new IOException("Expected close frame");
            }
            writeServerFrame(out, 8, close.payload());

            done.complete(null);
        } catch (Throwable error) {
            done.completeExceptionally(error);
        }
    }

    public static void main(String[] args) throws Exception {
        try (ServerSocket listener = new ServerSocket(
                0, 1, InetAddress.getByName("127.0.0.1"))) {

            CompletableFuture<Void> serverDone =
                    new CompletableFuture<>();
            Thread worker = new Thread(
                    () -> serveOne(listener, serverDone));
            worker.setDaemon(true);
            worker.start();

            CompletableFuture<String> received =
                    new CompletableFuture<>();
            CompletableFuture<Integer> closed =
                    new CompletableFuture<>();

            WebSocket.Listener callbacks = new WebSocket.Listener() {
                final StringBuilder parts = new StringBuilder();

                @Override
                public void onOpen(WebSocket socket) {
                    // Accept at least one message callback.
                    socket.request(1);
                }

                @Override
                public CompletionStage<?> onText(
                        WebSocket socket,
                        CharSequence data, boolean last) {

                    parts.append(data);
                    if (last) {
                        received.complete(parts.toString());
                    }
                    socket.request(1);
                    return null;
                }

                @Override
                public CompletionStage<?> onClose(
                        WebSocket socket,
                        int statusCode, String reason) {
                    closed.complete(statusCode);
                    return null;
                }

                @Override
                public void onError(
                        WebSocket socket, Throwable error) {
                    received.completeExceptionally(error);
                    closed.completeExceptionally(error);
                }
            };

            String endpoint = "ws://127.0.0.1:"
                    + listener.getLocalPort() + "/";

            WebSocket client = HttpClient.newHttpClient()
                    .newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .buildAsync(URI.create(endpoint), callbacks)
                    .join();

            client.sendText("hello WebSocket", true).join();
            System.out.println("echo: "
                    + received.get(5, TimeUnit.SECONDS));

            client.sendClose(WebSocket.NORMAL_CLOSURE, "done")
                    .join();
            System.out.println("close: "
                    + closed.get(5, TimeUnit.SECONDS));

            serverDone.get(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac -encoding UTF-8 WebSocketLoopbackDemo.java
java WebSocketLoopbackDemo
~~~

Stdout verified on Java 17:

~~~text
echo: hello WebSocket
close: 1000
~~~

### 9.1. Step-by-Step Code Walkthrough

**Step 1 — ServerSocket listens on loopback.** A server socket is opened on `127.0.0.1` with port 0 (the OS assigns an available ephemeral port); the demo runs the server on a daemon thread. The client reads the actual bound port, so the output does not contain a random port number.

**Step 2 — HTTP Upgrade handshake.** The JDK WebSocket client automatically sends an HTTP upgrade request with `Sec-WebSocket-Key`. The demo server uses the RFC 6455 formula to return a valid `Sec-WebSocket-Accept` and status 101. This is why the JDK client accepts the connection, not because the server issued a login token.

**Step 3 — Client sends text.** `sendText("hello WebSocket", true)` sends a text message. The demo server supports **only a single short frame with FIN=1** from the client, reads the 4-byte masking key and unmasks the payload, then sends back an unmasked text frame. The JDK WebSocket client reads/decodes the frame automatically and invokes the Listener.

**Step 4 — Listener receives the message.** `onOpen` calls `request(1)`. `onText` appends text chunks to `StringBuilder`, and when `last=true`, completes `received`; `received.get(5s)` lets `main` wait and print `echo: hello WebSocket`. In a multi-message application, you must **reset the buffer after each complete message** and handle concurrency/demand properly; this demo only receives one message.

**Step 5 — Close handshake.** The client calls `sendClose(1000,"done")`; the server receives the Close frame and replies with a Close frame. Listener `onClose` observes status `1000` (normal closure) and completes the `closed` future; `main` prints `close: 1000`. Normal closure differs from a peer losing network connectivity, which drops the connection without a Close frame.

### 9.2. Explicit Limitations of the Illustrative Server

This is **not a fully RFC-compliant WebSocket server**. What it **does not** do:

- Does not validate `Origin`, cookies/sessions/tokens, ACLs, or protect against Cross-Site WebSocket Hijacking.
- Does not serve HTTPS/WSS or verify TLS; binds only to loopback for learning.
- Does not support extensions, subprotocols, compression, fragmentation/continuation frames, binary messages, ping/pong, or extended payload lengths 126/127.
- Does not parse/validate all RFC 6455 handshake details (version, Upgrade/Connection tokens, key length, duplicates, protocol negotiation, error responses).
- Does not fully validate UTF-8 text or Close codes/reasons.
- Does not support multiple concurrent clients, heartbeats, bidirectional idle timeouts, rate limits, per-user quotas, backpressure, or application-level ACKs.
- Does not use a hardened server framework; unsuitable for accepting clients from the Internet.

The value of this demo is **seeing the standard Java client API work end-to-end with HTTP upgrade, text echo, masking, and close frames**. When writing a production WebSocket server, use a framework/WebSocket implementation with protocol and security testing—do not copy the demo server and expose it on a public port.

## 10. What State Does a Long-Lived Connection Require?

Production servers typically maintain several layers of state:

| State | Belongs To | Examples |
| --- | --- | --- |
| **Transport** | One WebSocket connection | socket, buffers, close state, last ping/pong |
| **Authentication** | Authenticated user/device | user ID, token expiry, allowed scopes |
| **Subscriptions** | Topics the session listens to | rooms, order IDs, filters |
| **Application protocol** | A command/event stream | request IDs, sequence, ACK, and phase |
| **Durable state** | Server-side storage | messages, job progress, last committed event |
| **Recovery state** | Survives across reconnects | resume token, last confirmed sequence |

Not everything should live in the RAM of a WebSocket session. A socket disappears when the server restarts; **durable state must reside in a database/broker** if business logic requires recovery.

For example, for a user in a chat room: the server should check room permissions on subscribe and when permissions change, rather than holding an `authorized=true` boolean forever from socket open and ignoring revocation.

## 11. Heartbeat, Ping/Pong, and Liveness Checks

Keeping a WebSocket open for a long time can encounter **half-open** connections: one side thinks the socket is alive while the network path is broken. There are two layers of checks:

1. **WebSocket protocol-level Ping/Pong:** one endpoint sends a Ping, and the peer replies with a Pong per the RFC. Used to detect unresponsive connections within an appropriate window; do not equate a single missed pong with a user intentionally logging out.
2. **Application heartbeat/presence:** client/server exchange `{"type":"heartbeat"}` messages or timestamps/sequences, used to determine business/session health and presence policies if needed.

### 11.1. Ping/Pong Does Not Guarantee Data Was Processed

`Pong` only indicates that the peer's WebSocket layer responded to the ping; it **does not** prove that an `order.cancel` command was committed. Business ACKs remain separate messages.

### 11.2. Higher Heartbeat Frequency Is Not Always Better

Pinging every 100 ms across one million connections drives up CPU/network/battery usage. Choose the interval based on **proxy/load balancer idle timeouts, disconnect detection SLA, mobile environment, connection count, jitter, and backpressure capacity**. For example, a heartbeat every few tens of seconds may fit some infrastructures, though it is not a mandatory universal number.

If no Pong arrives past the deadline, close the session and reconnect with backoff. Do not let clients trigger a "reconnect storm" simultaneously after a restart; add jitter and cap maximum attempts.

### 11.3. Browser Clients Differ from Java Clients

The browser WebSocket API typically **does not let JavaScript applications send Ping control frames directly**; the browser/transport handles control frames. If you want a heartbeat observable from JavaScript, design an application-level ping/pong message with the server.

The Java JDK `WebSocket` client provides `sendPing(ByteBuffer)`; a Ping control frame payload is limited to **125 bytes** by the RFC. Do not abuse Ping as a channel for large business payloads.

## 12. Disconnects, Reconnects, and Delivery Semantics

### 12.1. No Exactly-Once Across Reconnects

A scenario:

~~~text
Client -> Server: command id=42 "submit"
Server processes and commits id=42
Server -> Client: ack id=42
                 X (network drops before client receives)

Client reconnects: does not know whether id=42 committed.
~~~

If the client blindly resends the command with a new ID without checking, it may trigger **duplicate** side effects. WebSocket guarantees transmission order **within an active connection**, not certainty **after a disconnect**.

Safe design for operations with side effects:

- Every command carries an **idempotency key/request ID** stable across retries.
- The server stores processed results or provides a mechanism to check transaction status.
- After reconnecting, the client can ask "has command id=42 been processed?" instead of blindly creating a new command.
- Event streams have a `sequence` or cursor, and the server can return a snapshot/replay; if the log has been trimmed, the client fetches a snapshot and resumes.
- Business errors and transport errors are not conflated; "no ACK seen" does not mean "server did not process."

### 12.2. Resuming Subscriptions

After a reconnect, subscriptions tied to the **old socket** may be lost. The client needs to resend its list of allowed topics, last cursor, protocol version, and auth. The server re-authenticates and returns a snapshot or missed events if supported.

~~~json
{"type":"resume","channels":["orders.123"],"lastSeenSequence":502}
~~~

The server should decide whether it can replay from 503; if there is an unrecoverable gap, send a `resync.required` signal so the client reloads state over HTTP. Do not silently append new events to a UI that missed older events without notifying it.

### 12.3. Reconnecting with Backoff

~~~text
disconnect -> wait + jitter -> reconnect
           -> on failure: delay increases up to a cap
           -> on success: authenticate, resubscribe, resync, reset retry budget
~~~

This is an illustrative flow; exact delays depend on the network and server policy. Do not retry infinitely every 1 ms. When the user logs out or cancels, **stop retrying** and close the socket instead of running in the background.

## 13. Backpressure: Slow-Reading Clients Can Exhaust Server Memory

Suppose a producer generates 50,000 events/s while a client can only process 500 events/s. Even though WebSocket runs over TCP, **the mismatch does not disappear on its own**. If the server keeps pushing every message into an unbounded `ArrayList`, the heap will grow.

Mitigation approaches:

1. **Bound outbound queues by byte size and message count** per connection.
2. **Coalesce** superseding updates (for instance, keeping only the latest sensor reading) instead of queuing all historical events.
3. **Drop non-essential data** such as expired typing indicators per application rules; never silently drop critical financial transactions.
4. **Slow down the producer** or close overly slow sessions with an appropriate close/error reason.
5. **Limit connections and subscriptions per user**; each connection consumes file descriptors, buffers, and authentication state.
6. Monitor pending bytes, oldest queued message age, send latency, and slow-consumer disconnects.

### 13.1. `WebSocket.Listener.request(n)` Is Only JDK Client Receive Demand

`request(n)` tells the listener you are ready for more corresponding callbacks; **it does not automatically create an end-to-end backpressure policy** for brokers, producers, databases, or servers. When a callback receives a message, do not block for long writing to a database on the callback thread; offload to a bounded executor/queue and only request more when enough capacity is consumed.

Do not use an unbounded `StringBuilder` to assemble fragmented text without a **max message size**: a malicious peer can send many fragments and exhaust RAM.

### 13.2. Head-of-Line Blocking

WebSocket RFC 6455 commonly runs over TCP: losing one segment forces subsequent bytes to wait for TCP retransmission, even if newer messages have already been sent. This is the trade-off of reliability/ordering. For telemetry/games where old data loses value quickly, evaluate latency and choose a different transport if needed.

## 14. Scaling Many Connections and Fan-Out to Many Users

WebSocket servers hold state per connection, so **scale-out** design differs from most stateless HTTP request/response services:

~~~text
Client A --WebSocket--> Node 1 --\
                                  \        +--------------------+
Client B --WebSocket--> Node 2 ---->-------| Pub/Sub / broker   |
                                  /        +--------------------+
Client C --WebSocket--> Node 3 --/
        |
        +-- each node is responsible for sending to its own WebSockets
~~~

If someone on Node 1 sends to a room containing users on Node 2, Node 1 needs an event distribution mechanism (broker/pub-sub or service bus), as it cannot directly find sockets in Node 2's memory.

### 14.1. Do Sticky Sessions Solve Everything?

Load balancers can use sticky routing so a client's connection stays on one node for the lifetime of the connection; however, after a reconnect or deployment, the client can still land on a different node. **Sticky routing does not replace a database, broker, or resume protocol.** Store durable state out-of-process when needed, and design connection-state cleanup properly.

### 14.2. Fan-Out to Many Users

Broadcasting an event to 100,000 users does not mean the server simply calls `sendText` once. You need a fan-out strategy, partitioning, batching/coalescing, message prioritization, bandwidth caps, and isolation so one slow client does not stall all other clients.

You can partition by room/topic or shard, while still guaranteeing **ACLs and event ordering** per entity. A broker can hold history while WebSocket nodes manage active online connections.

### 14.3. Deployments and Graceful Shutdown

During a rolling deployment:

1. Stop accepting new connections on the old node.
2. Signal drain/reconnect if the protocol supports it.
3. Allow buffered messages to flush within a reasonable deadline.
4. Send a valid WebSocket Close if possible, close sessions, and release subscriptions.
5. Clients reconnect with backoff and resubscribe; new servers can replay/snapshot.

Do not wait forever because a few WebSockets have not closed; at the same time, do not abruptly sever all sockets if the application is sending critical messages and has a drain plan.

## 15. WebSocket Security: Upgrade Is Not Authentication

### 15.1. Use WSS on Real Networks

`wss://` protects the stream with TLS, defending against eavesdropping/tampering in transit when trust is configured properly. For browsers, HTTPS pages generally must use WSS to avoid mixed content. The Java `HttpClient` must also verify certificates/hostnames; **do not disable TLS verification** to work around certificate errors.

### 15.2. Origin and Cross-Site WebSocket Hijacking

Browsers may send an `Origin` header when initiating a WebSocket. Servers must enforce an appropriate **Origin allowlist** for browser clients; do not assume `fetch`/XHR CORS policies block WebSocket handshakes.

If a server uses cookie sessions and does not check `Origin`, a malicious page can attempt to open a cross-site WebSocket carrying the user's cookies depending on browser/cookie policies, leading to **Cross-Site WebSocket Hijacking (CSWSH)**. Beyond `Origin`, authenticate the session, configure cookies/`SameSite` appropriately, and **authorize each subscription/command**.

For non-browser clients, `Origin` can be spoofed; Origin validation **is not authentication** and cannot replace access tokens/mTLS or session authorization.

### 15.3. Tokens and Browser Limitations

The browser `WebSocket` API does not provide a general way to attach **arbitrary custom Authorization headers** like `fetch` does. Common approaches include protected cookies, short-lived scoped tokens in a tightly designed handshake flow, or subprotocols when a secure convention exists. Do not casually put bearer tokens in the query string, as URLs are easily logged in proxy/access logs. If query tokens are used in a specific architecture, enforce short TTLs, tight scopes, and log redaction.

The Java backend WebSocket client has builder APIs for headers within implementation constraints, but **do not assume browsers have the exact same capability**.

### 15.4. Validate Every Message, Not Just Connect

After the WebSocket handshake completes, every text/binary message is still **untrusted user input**. The server needs to:

- Validate schema, type, length, encoding, and message size.
- Authenticate and **authorize actions at processing time**, especially when user permissions can be revoked.
- Rate-limit message counts and bytes per user/IP.
- Limit room/topic subscriber counts and subscription churn.
- Never execute shell/SQL commands from arbitrary text; prevent injection.
- Limit decompression ratios if `permessage-deflate` is enabled; do not assume compression is free.
- Control logging of PII and tokens, using metrics that do not leak sensitive payloads.

### 15.5. Ping Is Not Authentication

Receiving a Pong only proves a connection has a responsive peer; **it does not prove the user is still authorized** or that their token has not expired. For sessions lasting hours, implement a token refresh/re-auth strategy or let the server close subscriptions when permissions change.

## 16. Infrastructure Configuration: Proxies, Load Balancers, and Idle Timeouts

WebSocket works across many HTTP infrastructures but requires proper support:

- Proxies/reverse proxies must allow WebSocket Upgrade (in HTTP/1.1), forward `Upgrade`/`Connection` headers properly, and not buffer the entire stream.
- TLS termination at a proxy must configure WSS origins, certificates, and trusted forwarding headers per the architecture.
- Load balancer idle timeouts may be shorter than the intended session lifetime; adjust heartbeats or timeouts accordingly.
- NATs/firewalls/mobile devices can drop connections; clients must reconnect and resume.
- Gateways and corporate networks may block or inspect WebSocket differently from regular HTTP; have a fallback plan if required by the product.
- Do not use HTTP CDN object caches assuming WebSocket messages have cache semantics.

**Important:** after a successful HTTP Upgrade, **not all HTTP middleware continues to inspect every WebSocket message**. Logging/auth/audit/size limits at the message layer must be enforced inside the WebSocket server/framework.

### 16.1. When WebSocket "Fails to Connect"

Diagnostic checklist:

1. Does the URL use `ws://` or `wss://` with the right scheme, host, port, and path?
2. Are the TLS certificate/hostname and trust chain valid?
3. Does the server/proxy return `101 Switching Protocols` (or the transport-appropriate handshake) or `400/401/403/404/502`?
4. Are `Upgrade` and `Connection` headers forwarded properly by the reverse proxy?
5. Is `Origin`/session/auth being rejected?
6. Are proxy/LB idle timeouts, firewalls, and connection limits configured appropriately?
7. Is there a subprotocol/extension negotiation error?
8. What `onError`/close code did the client receive? Have you checked server logs and correlation IDs?

It is strongly discouraged to "fix" issues by **removing Origin checks, disabling TLS, or exposing unauthenticated public endpoints**.

## 17. Common Mistakes When Designing WebSocket Applications

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using WebSocket for a single simple GET/POST | Adds unnecessary state, reconnects, and infrastructure | Use HTTP request/response |
| Needing one-way server push but forcing WebSocket | Adds protocol complexity | Evaluate SSE |
| Treating WebSocket as unordered/lossy UDP | Misunderstands latency/reliability | Understand TCP and head-of-line blocking |
| Assuming one message = one frame/callback | Incomplete parsing or mixed text fragments | Buffer parts until `last=true` |
| Not calling `request(n)` in a Java listener | Stops receiving expected callbacks | Manage demand intentionally |
| Calling `sendText().join()` and assuming server commit | No business ACK | Use request IDs and application ACKs |
| Assuming a lost socket means data must be lost | No resume/durable state | Database/queue + snapshot/replay |
| Retrying commands with side effects using a new ID | Duplicate transactions | Idempotency keys and transaction lookup |
| Unbounded queued messages | OOM with slow consumers | Per-connection byte quotas/backpressure |
| Storing room members only in each node's RAM | Missed events for users on other nodes | Shared broker/presence coordination |
| Enabling overly frequent heartbeats for all clients | Wastes CPU/network/battery | Base on SLA/proxy idle and real load |
| Not checking `Origin` when using browser cookies | CSWSH risk | Origin allowlist + auth/session checks |
| Authenticating only at handshake | Revoked users still receive events | Re-auth/authorize commands/subscriptions |
| Treating `ws://` as sufficient over the Internet | Data can be sniffed/tampered | Use `wss://` and validate TLS |
| Pushing large files through unbounded messages | Memory spikes and hard to resume | HTTP streaming/resumable upload |
| Not sending Close or handling network drops | Session leaks, stale presence | Close handshake, idle timeout, cleanup |
| Using the raw `ServerSocket` demo as a public server | Missing RFC edge cases and security | Standard WebSocket framework |
| Treating close status 1000 as a business ACK | Unknown whether commands completed | Rely on application state |
| Not testing long sessions across deploys/network switches | Lost subscriptions, reconnect storms | Load/reconnect/rolling-deploy tests |

## 18. Architecture Decision Exercises

### Exercise A — Simple Notification Page

A page only needs to receive "new notification available" alerts and sends no commands during the session. What should you choose?

**Answer:** **SSE** is usually worth trying first because it is a server → browser channel, uses HTTP, and browser `EventSource` supports reconnects. WebSocket is still possible, but not required just because of the word "real-time."

### Exercise B — Chat Room with Typing and Reactions

Clients send messages, typing indicators, and reactions; the server continuously pushes messages and presence to all members.

**Answer:** WebSocket fits well thanks to full-duplex communication and low latency for many small messages. You still must design authentication, per-room authorization, history storage, sequences, rate limiting, and ACKs.

### Exercise C — Dashboard Changing Once Every 10 Minutes

The server has roughly 100,000 viewers; data changes every 10 minutes, with no commands from clients.

**Answer:** HTTP GET with cache headers, sparse polling, or SSE can be simpler and cheaper than maintaining 100,000 WebSocket connections. Measure actual costs before choosing.

### Exercise D — Shooter Game at 60 Updates/Second

Old position state becomes obsolete after a few frames; the application prefers dropping old messages over waiting for retransmissions.

**Answer:** WebSocket/TCP ordered delivery can cause head-of-line latency. Evaluate a transport supporting real-time datagrams/partial reliability (depending on client/platform) instead of defaulting to WebSocket for all data.

### Exercise E — 2-Hour Processing Job

The client needs to track progress, occasionally send pause/cancel, and may close their laptop and return later.

**Answer:** WebSocket can be convenient for progress + commands while online, but **job state must be durable**. When the user reconnects, fetch a snapshot via HTTP and/or resume the event stream from a sequence; do not tie job lifetime to socket lifetime.

### Exercise F — Mobile Drops Wi-Fi Mid-Transaction

The client sends an order cancellation command and loses network before seeing an ACK. When back online, should it create a new command and resend?

**Answer:** Do not blindly resend with a new ID. Use a request ID/idempotency key, check server state, and resend safely per policy. WebSocket does not provide exactly-once across reconnects.

### Exercise G — WSS Through a Reverse Proxy

Locally `ws://` works, but in production `wss://` returns 502 or 400.

**Answer:** Check TLS termination, route/path, `Upgrade`/`Connection` headers, proxy support, auth/Origin, timeouts, and logs. Do not fix it by disabling TLS.

### Exercise H — 500,000 Online Clients

A single node holds 500,000 sockets and room memberships in heap; a deployment wipes all node state.

**Answer:** You need a scale-out design, connection partitioning, quotas, a broker/pubsub, durable offsets/subscriptions, and reconnect/resume. Sticky sessions alone do not solve lost state.

### Exercise I — A Text Message Split Across 3 Callbacks

The Java listener invokes `onText(ws, part1, false)`, `onText(ws, part2, false)`, `onText(ws, part3, true)`.

**Answer:** Concatenate the parts along the message boundary until `last=true`, then parse a single JSON/document; enforce a max total size and do not interleave multiple messages.

### Exercise J — Using Browser Cookies Without Checking Origin

Another website can open a WebSocket to a server where the user already has a login cookie under certain conditions. What is the risk?

**Answer:** CSWSH; the server must check allowed `Origin` (for browsers), authenticate, enforce `SameSite`/cookie policies, and authorize each action. `fetch` CORS does not automatically replace WebSocket `Origin` validation.

### Exercise K — `sendText` Future Completes

The client calls `sendText(...).join()` and immediately displays "order paid successfully." Is that right?

**Answer:** No. The future only indicates the send operation completed per the API; there is no business ACK/commit. Wait for a business response message/HTTP status with `requestId` and verify server state.

### Exercise L — Slow Client, Fast Server

The server generates 10,000 events/s for a client that is not reading, and the queue grows without bound. What should you do?

**Answer:** Bound queued bytes, coalesce superseding events, drop non-critical events per policy, slow down the producer, or close the slow consumer; do not expect TCP to eliminate all RAM pressure on its own.

## 19. Production Readiness Checklist for WebSocket

- [ ] **Do both sides truly need to send proactively** in a long-lived, highly interactive session?
- [ ] Have HTTP, polling, long-polling, SSE, and alternative transports been evaluated?
- [ ] Are messages, frames, fragmented text/binary, and control frames distinguished?
- [ ] Does the Java `Listener` manage `request(n)` and message completion via `last`?
- [ ] Are message schema/type/version, request IDs, validation, max size, and per-action permissions in place?
- [ ] Is there a separate business ACK, rather than treating send completion or Pong as a commit?
- [ ] Are sequence/cursor, snapshot/replay, or resync implemented for reconnects?
- [ ] Are timeouts, Ping/Pong, or heartbeats configured per SLA without being overly frequent?
- [ ] Are reconnect backoff/jitter, max attempts, and stopping on user logout implemented?
- [ ] Are outbound queues, subscriptions, users, connections, rates, and memory bounded?
- [ ] Is there a broker/pubsub or fan-out architecture if running multiple server nodes?
- [ ] Is durable state decoupled from socket lifetime?
- [ ] Are WSS/TLS, origin allowlist, and session/token authentication configured properly?
- [ ] Is CSWSH prevented when using browser cookies, with per-subscription/command authorization?
- [ ] Do reverse proxies/LBs/CDNs support Upgrade, idle timeouts, and rolling deploys?
- [ ] Is observability in place: concurrent sockets, connection lifetime, handshake failures, RTT, queue bytes, slow consumers, close codes, reconnect rate, missed events?
- [ ] Have you tested network drops, offline/resume, Wi-Fi switches, deploy restarts, duplicate commands, large frames, malformed JSON, and unauthorized subscribes?
- [ ] Are you using a full RFC-compliant implementation instead of the demo's raw `Socket` server?

**Conclusion:** WebSocket is ideal **when continuous bidirectional exchange is a core requirement**, not just because an application wants to be "real-time." It lets both client and server proactively send text/binary messages over a long-lived connection, making it very useful for chat, collaboration, interactive dashboards, and control. However, WebSocket **does not provide durable messaging, exactly-once delivery, authorization, schemas, offline replay, or automatic scaling**. A sound design must include authentication, a message protocol, backpressure, heartbeats, reconnects, persistence, and infrastructure operations. If you only need one-way server push or infrequent requests, **SSE or HTTP is usually simpler**.

## 20. References

- **RFC 6455 — The WebSocket Protocol:** https://www.rfc-editor.org/rfc/rfc6455
- **RFC 8441 — Bootstrapping WebSockets with HTTP/2:** https://www.rfc-editor.org/rfc/rfc8441
- **Java 17 — WebSocket client API:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html
- **Java 17 — WebSocket.Listener:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html
- **Java 17 — WebSocket.Builder:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html
- **Java 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **WHATWG HTML — WebSocket API in Browsers:** https://websockets.spec.whatwg.org/

The RFCs define the protocol framing, while the Java APIs define the JDK's callbacks, futures, and flow control. When building a production server, use a standards-compliant WebSocket framework and test proxy infrastructure, TLS, browser Origin checks, and reconnect flows.