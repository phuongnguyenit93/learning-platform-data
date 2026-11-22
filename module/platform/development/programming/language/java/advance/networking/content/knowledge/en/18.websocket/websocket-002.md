# ws, wss, the Opening Handshake, and the Role of HttpClient in Java WebSocket

## Lesson Objectives

WebSocket creates a **bidirectional, long-lived** communication channel between client and server. With WebSocket under RFC 6455, the connection begins with an **HTTP/1.1 opening handshake**, but once accepted, the parties exchange **WebSocket frames** rather than continuing to send ordinary HTTP requests/responses over the same upgraded channel. Java 17 includes a **WebSocket client** directly in the `java.net.http` module, integrated via `HttpClient.newWebSocketBuilder()`; developers do not have to manually generate `Sec-WebSocket-Key`, compute `Sec-WebSocket-Accept`, or read individual frames in typical applications.

This lesson focuses on four core questions:

1. **How do `ws://` and `wss://` differ?** Why does `wss` use TLS and default to port 443, while `ws` does not protect bytes on the wire?
2. **How does the opening handshake actually work?** HTTP GET, `Upgrade: websocket`, `Connection: Upgrade`, `Sec-WebSocket-Key`, `Sec-WebSocket-Version: 13`, the `101 Switching Protocols` response, and the `Sec-WebSocket-Accept` verification.
3. **What is the role of `HttpClient`?** How to use `newWebSocketBuilder().buildAsync(uri, listener)` and the responsibilities of the HTTP client, WebSocket builder, WebSocket instance, and Listener.
4. **What changes after the handshake?** Text/binary messages, masking, fragments, Ping/Pong, Close, `request(n)` flow control, Future completion, and distinguishing byte-send completion from business responses.

There are **three standalone Java 17+ programs**, compiled and verified: computing `Sec-WebSocket-Accept` using the RFC 6455 test vector; opening a loopback WebSocket, performing the 101 handshake, exchanging text, and closing with 1000; and testing handshake rejection via HTTP 403 or an invalid Accept value. The hands-on examples use `ws` on **localhost** to avoid needing certificates; production deployments should prefer `wss`.

## 1. What WebSocket Is and What It Is Not

Traditional HTTP is often taught as a `request → response` cycle. If a browser/client needs continuous updates, the application can poll with multiple HTTP requests or use Server-Sent Events. WebSocket solves a different problem: **maintaining a bidirectional connection**, so **both client and server can proactively send messages** after the connection is established.

```text
Sequential HTTP request/response:
Client ─── GET /messages ───► Server
Client ◄─── HTTP 200 ──────── Server
Client ─── GET /messages ───► Server
Client ◄─── HTTP 200 ──────── Server

WebSocket:
Client ─── HTTP opening handshake ───► Server
Client ◄─── 101 Switching Protocols ─ Server
       ╔════ WebSocket connection ════╗
Client ─── text/binary frame ────────► Server
Client ◄─── text/binary frame ──────── Server
Client ◄─── ping? / updates ───────── Server
Client ─── pong? / commands ────────► Server
       ╚════ Close handshake ═════════╝
```

From the moment a valid handshake succeeds:

- **HTTP status lines/headers are no longer used for each WebSocket message**; application data resides in WebSocket frames.
- **Sending each WebSocket text message does not open a new HTTP connection.**
- WebSocket uses a single **TCP connection** in its basic RFC 6455 form; TLS can be layered via `wss`.
- WebSocket does not itself define JSON schemas, chat permissions, transaction confirmations, subscription permissions, idempotency, or message ID conventions. Those belong to the **application protocol** layered on top of WebSocket.
- “Send succeeded” in the `sendText` API does not mean “the server has processed the business command”; if needed, the application must implement its own message IDs and ACKs.

WebSocket is well suited for real-time dashboards, chat, collaborative editing, game events, and state update streams. However, not every API needs WebSocket: a single CRUD request over HTTPS is usually simpler and easier to cache and monitor.

### Distinguishing the Terms

| Concept | Level | What It Manages |
|---|---|---|
| TCP connection | Transport | Byte stream between endpoints |
| TLS (with `wss`) | Transport security | Encryption, integrity, and endpoint authentication as configured |
| HTTP opening handshake | Protocol establishment | Proposing/agreeing to switch from HTTP to WebSocket |
| WebSocket frame | Framing | Opcode, length, mask, payload, FIN |
| WebSocket message | Application/protocol | Text or binary, potentially spanning multiple frames |
| Application message | Business logic | JSON commands, events, request IDs, ACKs, etc. defined by the app |

One WebSocket **message** does not equate to one `onText` call: the API may deliver **fragments** across multiple callbacks, using the `last` boolean to indicate the final segment.

## 2. `ws://` and `wss://`: Scheme, Port, TLS

RFC 6455 defines two URI schemes:

```text
ws://host[:port]/path?query
wss://host[:port]/path?query
```

| Property | `ws://` | `wss://` |
|---|---|---|
| Connection protected by TLS? | No | **Yes** |
| Default port if omitted in URI | **80** | **443** |
| Data encryption on the transport leg | No default TLS | TLS for the established leg |
| TLS certificate and hostname verification | Not applicable on `ws` transport | Trust/hostname certificate validation required |
| Production use with credentials/sensitive data | Should not be used over untrusted networks | **Recommended**, alongside auth/authorization |
| Example URI | `ws://127.0.0.1:9000/chat` | `wss://api.example.test/realtime` |

**Crucial point:** `wss` uses **TLS**, not “WebSocket with its own JSON encryption”. The TLS handshake occurs **before** the HTTP/WebSocket opening handshake over the secured connection. The handshake headers, messages, and frames then travel inside TLS.

```text
ws:
TCP connect → HTTP GET Upgrade → HTTP 101 → WebSocket frames → Close

wss:
TCP connect → TLS handshake, certificate/hostname validation
            → HTTP GET Upgrade inside TLS
            → HTTP 101 inside TLS
            → WebSocket frames inside TLS → Close
```

If TLS terminates at a reverse proxy/load balancer, the browser→proxy leg is protected by `wss`; the proxy→backend leg may use HTTP/WebSocket over an internal network or separate TLS, depending on configuration. Do not assume “the entire path is end-to-end encrypted” without verifying all hops.

### URI Path, Query, and Fragment

- `ws://example.test/chat?room=java` is structurally valid, and `/chat?room=java` forms the request target/resource name of the handshake.
- **Fragments `#section` are not allowed in a WebSocket URI** per RFC 6455; fragments are not data sent to the server.
- Avoid putting long-lived access tokens/secrets in the query string when possible because URLs easily leak into logs/analytics. Prefer credential flows or auth mechanisms defined by the backend.
- `ws`/`wss` are **WebSocket schemes**; do not substitute `http`/`https` directly when calling `WebSocket.Builder.buildAsync`.
- Do not assume an `https://api.../rest` endpoint automatically supports `wss://api.../rest`; the server/proxy must configure routing and protocol upgrade properly.

### Mixed Content and Browsers

Web pages loaded over **HTTPS** are typically disallowed by browser security policies from establishing an insecure `ws://` WebSocket to an unsecured endpoint. `wss://` is the standard choice on HTTPS pages. Java desktop/server-side `HttpClient` is not a browser, so it does not automatically enforce browser mixed-content and cookie-origin policies; Java applications must apply appropriate connection policies themselves.

## 3. HTTP/1.1 Opening Handshake: What Does the Client Send?

WebSocket under RFC 6455 begins with an **HTTP/1.1 GET request** proposing a connection upgrade:

```http
GET /chat HTTP/1.1
Host: example.test
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Sec-WebSocket-Protocol: chat.v1, chat.v0

```

On the actual wire, lines are terminated by `\r\n` (CRLF) and **an empty line** terminates the headers section. The `Sec-WebSocket-Key` value in the example is the **standard RFC test vector**, not a session key or user password. On a real connection, the client must generate a fresh, sufficiently random nonce per the RFC.

**Components:**

1. **`GET /chat HTTP/1.1`**: classic HTTP/1.1 opening handshake requesting a protocol upgrade for the `/chat` resource. It is not a POST sending a JSON body to “open a socket”.
2. **`Host`**: informs the server/proxy of the target host and port per HTTP/1.1.
3. **`Upgrade: websocket`**: proposes switching to the websocket protocol.
4. **`Connection: Upgrade`**: specifies that `Upgrade` is a hop-by-hop option of the HTTP/1.1 connection; proxies must handle forwarding appropriately and not treat hop-by-hop headers as end-to-end by default.
5. **`Sec-WebSocket-Key`**: a 16-byte nonce Base64-encoded; used in the mechanism proving the server understands the handshake.
6. **`Sec-WebSocket-Version: 13`**: WebSocket protocol version per RFC 6455; not HTTP/1.3 or Java version 13.
7. **`Sec-WebSocket-Protocol`** (optional): application subprotocols proposed by the client in order of preference.
8. **`Origin`** (client/context-dependent): sent by browsers so the server can enforce origin policy; a Java non-browser client is not automatically subject to browser-origin rules.

HTTP header field names are case-insensitive. `Connection` is a token list, not necessarily containing only the single word `Upgrade`. Therefore, when validating a request, a parser should check tokens case-insensitively rather than performing a rigid full-string comparison.

### Is `Sec-WebSocket-Key` an Authentication Token?

**No.** It is not a certificate, password, session key, OAuth token, or secret. RFC 6455 uses the nonce together with `Sec-WebSocket-Accept` to verify that the response comes from a peer that understands the WebSocket protocol and is not merely an HTTP server/proxy returning mistaken content. **Do not use Key/Accept as a user authentication mechanism or encryption secret.**

If user authentication is required, use TLS, cookies/sessions/tokens, or a valid application mechanism and verify permissions on the server. For browser security, `Origin` is an important control layer, but it **does not replace authentication/authorization**.

## 4. Server Response: `101 Switching Protocols` and Accept

When the server agrees, the classic handshake response looks like:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Sec-WebSocket-Protocol: chat.v1

```

**`101 Switching Protocols`** does not mean “any 101 succeeds”. The client must verify the required headers, protocol/version constraints, and that `Sec-WebSocket-Accept` was derived correctly from the key it sent.

RFC 6455 specifies:

```text
clientKey = text value of Sec-WebSocket-Key
GUID      = 258EAFA5-E914-47DA-95CA-C5AB0DC85B11

Sec-WebSocket-Accept =
  Base64( SHA-1( ASCII(clientKey + GUID) ) )
```

**Important:** concatenate the **Base64 string of `Sec-WebSocket-Key`**, not the 16 decoded raw bytes. For the standard example:

```text
Sec-WebSocket-Key:    dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

SHA-1 here is a **protocol-mandated transformation**, not used for password storage and not a substitute for TLS. There is no reason to invent a “stronger SHA-256 version” for `Sec-WebSocket-Accept`; doing so would break RFC 6455 WebSocket compatibility.

### When Is the Handshake Incomplete?

- The server returns `403 Forbidden` (not allowed), `401 Unauthorized` (auth required), `404 Not Found`, `400 Bad Request`, or any status other than **101**: there is no WebSocket connection under classic RFC 6455.
- The server returns 101 but is missing the appropriate `Upgrade`/`Connection` headers, has an invalid `Sec-WebSocket-Accept`, or has an invalid subprotocol: the client must **reject the handshake**.
- The TLS handshake fails (for `wss`) before reaching the HTTP request: there is no WebSocket connection.
- A proxy strips/blocks hop-by-hop headers or fails to forward the upgrade: the handshake can fail.
- The server redirects via 3xx: do not automatically treat a redirect as a successful WebSocket; follow behavior depends on the client implementation/policy and target URI.

Once the HTTP opening handshake is accepted, subsequent bytes on that connection must be **decoded as WebSocket framing**, not sent as a second HTTP request like ordinary HTTP/1.1 keep-alive. For WebSocket over HTTP/2, RFC 8441 defines an **extended CONNECT** mechanism distinct from classic 101/Upgrade; **do not assume HTTP/1.1 101 applies to every infrastructure variant**. This lesson covers the classic WebSocket handshake and the Java 17 client.

## 5. Java 17+: Computing `Sec-WebSocket-Accept` from the RFC Vector

Create the file **`WebSocketAcceptKeyDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Base64;

public class WebSocketAcceptKeyDemo {
    public static void main(String[] args) throws Exception {
        String clientKey = "dGhlIHNhbXBsZSBub25jZQ==";
        String guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
        byte[] sha1 = MessageDigest.getInstance("SHA-1").digest(
                (clientKey + guid).getBytes(StandardCharsets.US_ASCII));
        String accept = Base64.getEncoder().encodeToString(sha1);
        System.out.println("Decoded key bytes: "
                + Base64.getDecoder().decode(clientKey).length);
        System.out.println("Sec-WebSocket-Accept: " + accept);
        System.out.println("Matches RFC 6455 example: "
                + accept.equals("s3pPLMBiTxaQ9kYGzzhZRbK+xOo="));
    }
}
```

Run commands:

```bash
javac --release 17 -encoding UTF-8 WebSocketAcceptKeyDemo.java
java WebSocketAcceptKeyDemo
```

**Compiled and verified stdout:**

```text
Decoded key bytes: 16
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
Matches RFC 6455 example: true
```

Analysis:

1. `Base64.getDecoder().decode(clientKey)` yields 16 bytes; this is the nonce length encoded in `Sec-WebSocket-Key`.
2. Concatenate the **key string** with the GUID, encode as ASCII, and hash with `SHA-1`.
3. Base64-encode the 20-byte hash to produce Accept per the RFC; the program is verified to match the standard vector.
4. This is an **educational experiment on the handshake**, not code you should embed into a Java WebSocket client using `HttpClient`: the library already handles this.
5. Do not store `clientKey` as an API key, do not mark a user as logged in because Accept matches, and do not treat this SHA-1 as `wss` encryption.

## 6. Subprotocols, Extensions, and Origin: Three Distinct Mechanisms

### 6.1. `Sec-WebSocket-Protocol` Selects an Application Subprotocol

WebSocket only provides **transport frames and message types**. Both sides need to know what the payload means (JSON commands, STOMP, GraphQL transport, custom binary). The client can offer:

```http
Sec-WebSocket-Protocol: chat.v2, chat.v1
```

The server **may select only one subprotocol** from the offered list (or none), for example:

```http
Sec-WebSocket-Protocol: chat.v1
```

Java:

```java
// Illustrative snippet; 'client' is an already created HttpClient.
WebSocket.Builder builder = client.newWebSocketBuilder()
        .subprotocols("chat.v2", "chat.v1");
// After buildAsync(...), ws.getSubprotocol() returns the negotiated protocol.
```

`subprotocols(mostPreferred, lesserPreferred...)` takes identifiers in order of preference. Once connected, `WebSocket.getSubprotocol()` reports the selected value. Do not assume the server will pick the first preferred one; the server may choose another protocol offered by the client or none at all.

**A subprotocol does not authenticate a user.** A subprotocol named `admin.v1` does not grant the client admin privileges; authorization must still be checked on the server.

### 6.2. `Sec-WebSocket-Extensions` Negotiates Features

Extensions change how certain frames are interpreted, such as message compression extensions. The server must not return an extension that was not in the offer or is not supported by the client. When an extension is active, the frame parser must obey RSV bits and extension rules. **Do not set RSV bits manually or assume every peer supports compression.** Java 17 `WebSocket.Builder` does not provide a general API like `subprotocols` to arbitrarily enable any WebSocket extension; do not invent `builder.extensions(...)`.

### 6.3. `Origin` and Browser Security Policy

Browsers typically send `Origin` in the opening handshake so the WebSocket server can evaluate which site initiated the connection. WebSocket **does not work like XHR subject to CORS in the same way**; the server must validate Origin appropriately to mitigate **cross-site WebSocket hijacking** when the application relies on automatic browser cookies/sessions.

- If the server only allows UI from `https://app.example.test`, validate Origin against an allowlist while also requiring auth/authorization.
- **Origin can be spoofed by non-browser clients**, so never use Origin as proof of identity.
- Java `HttpClient` is a non-browser client; do not expect it to automatically emulate full browser cookie/Origin policies.
- If the application uses its own tokens, restrict token scope and TTL, and avoid exposing secrets in URI queries/logs.
- With `wss`, verify the TLS certificate, hostname, trust store, and any proxy/TLS termination points.

## 7. The Exact Role of `HttpClient` in Java 17

Key classes in the **`java.net.http`** module (available since Java 11):

- `java.net.http.HttpClient`: configures the HTTP client; used to obtain a `WebSocket.Builder`.
- `java.net.http.WebSocket.Builder`: configures the opening handshake, optional headers, connect timeout, and subprotocols.
- `java.net.http.WebSocket`: a successfully built WebSocket connection; sends text/binary/ping/pong/close and inspects input/output state.
- `java.net.http.WebSocket.Listener`: receives open, text/binary, ping/pong, close, and error callbacks.

**The right path:**

```java
// Illustrative snippet; imports URI, Duration, HttpClient, WebSocket.
HttpClient client = HttpClient.newHttpClient();

CompletableFuture<WebSocket> opening = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .subprotocols("chat.v1")
        .buildAsync(URI.create("wss://api.example.test/ws"), listener);

WebSocket socket = opening.join();
```

This is a **non-standalone snippet**: `listener` must be defined, the example endpoint must exist with a valid certificate, and exceptional completion, timeouts, and cleanup must be handled. Do not run an example URI and guess network results.

**What Java does for you:**

1. Uses the `ws`/`wss` URI scheme to open the appropriate transport and TLS when needed.
2. Builds the classic opening handshake per the protocol; manages required headers and the random nonce.
3. Validates the 101 response, header tokens, Accept, and subprotocol/extension constraints per the implementation.
4. After the handshake, encodes/decodes WebSocket frames, **masks** client-to-server frames, and enforces frame protocol rules.
5. Dispatches `WebSocket.Listener` callbacks and manages demand via `request(n)`.
6. Supports `sendText`, `sendBinary`, `sendPing`, `sendPong`, `sendClose`, and `abort`.

**What Java does NOT do for the application:**

- Define JSON formats/schemas or decide who can subscribe to which topic.
- Grant access based solely on `Sec-WebSocket-Key` or subprotocol.
- Guarantee that the server has applied a business command when the `sendText` future completes.
- Automatically reconnect with backoff, resume cursors, or deduplicate messages according to business logic.
- Decide application-level heartbeat periods/liveness policies.
- Provide a production WebSocket server using only `HttpClient`. `java.net.http.WebSocket` is a **client API**, not a built-in hosted WebSocket server listener.

### Why Not Use `HttpClient.send()` for WebSocket?

`client.send(HttpRequest, BodyHandler)` / `sendAsync` are for **HTTP request–response** and do not provide `WebSocket.Listener`, framing, ping/pong, or automatic close handshake handling for an upgraded connection. Do not manually set `Upgrade: websocket` on an `HttpRequest` expecting `send(...)` to return a `WebSocket` object.

Instead, use **`client.newWebSocketBuilder().buildAsync(...)`**. The same `HttpClient` can share proxy, authenticator, and SSL context configuration depending on the implementation, but an **opened WebSocket connection is not an ordinary HTTP request**.

### Do Not Manually Set Reserved Handshake Headers

`WebSocket.Builder.header(name, value)` allows adding appropriate HTTP headers during the handshake, but the Javadoc explicitly states that **headers defined by the WebSocket protocol are invalid to add this way**. Do not manually call `header("Sec-WebSocket-Key", ...)`, `header("Sec-WebSocket-Accept", ...)`, or `header("Upgrade", ...)` to “force” a handshake.

```java
// Illustrates structurally valid configuration;
// endpoint and authorization must follow the application contract.
WebSocket.Builder builder = client.newWebSocketBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .header("X-Trace-Id", "trace-123")
        .subprotocols("chat.v1");
```

This is a snippet, not a standalone program; `client`/imports must be declared. Do not put passwords/access tokens into `X-Trace-Id`. If the server requires login, use proper protocol credentials/cookies/auth and send them only over `wss`.

## 8. `WebSocket.Builder.buildAsync` Returns a Future for the Opening Handshake

Signature:

```java
CompletableFuture<WebSocket> buildAsync(URI uri,
        WebSocket.Listener listener);
```

When the **connection succeeds**, the future completes with the opened `WebSocket`. When it fails, it completes exceptionally. Errors to know per the Java 17 Javadoc:

| Scenario | Observable Symptom/Error | How to Handle |
|---|---|---|
| Server returns HTTP 403/401/404 instead of 101 | `WebSocketHandshakeException`; response status can be read from exception | Check auth/permissions, URI/route |
| Server returns HTTP 101 with invalid Accept/headers | `WebSocketHandshakeException` | Fix server/proxy handshake; do not bypass validation |
| Timeout establishing/opening handshake | `HttpTimeoutException` with builder connect timeout | Check TCP/TLS/proxy/handshake and deadline |
| DNS/TCP refused, TLS validation, or I/O error | `IOException` or related cause | Check address, cert, TLS, proxy, port |
| Invalid URI/header/subprotocol argument | `IllegalArgumentException` | Fix configuration per API |
| Thread waiting on `Future.get` interrupted | `InterruptedException` on waiting thread | Restore interrupt / follow shutdown policy |

**`WebSocket.Builder.connectTimeout` only sets the deadline for establishing the WebSocket connection**, not “a maximum 5-second lifetime for the WebSocket”. Once open, you need a separate timeout/heartbeat/idle policy if the application requires it.

When using `buildAsync(...).get(timeout, unit)`, the `get` timeout **only limits how long the thread waits on the Future** — it does not prove that the handshake/network attempt was cancelled if the caller hits `TimeoutException`. Do not confuse `WebSocket.Builder.connectTimeout` with `CompletableFuture.get(timeout)`.

### Properly Classifying an Exceptional Future

`buildAsync` returns a Future. When using `get`, errors are typically wrapped in `ExecutionException`:

```java
// Illustrative snippet; variable 'opening' is CompletableFuture<WebSocket>.
try {
    WebSocket socket = opening.get(5, TimeUnit.SECONDS);
} catch (ExecutionException failed) {
    Throwable cause = failed.getCause();
    if (cause instanceof WebSocketHandshakeException rejected) {
        int status = rejected.getResponse().statusCode();
        // Record allowed status and metadata; do not log secrets.
    }
}
```

`getResponse()` lets you inspect the HTTP response that caused the handshake failure; it **does not give the application a connected WebSocket**. The complete programs in the next sections demonstrate both the success and rejection paths.

## 9. After the Handshake: WebSocket Frames, Masking, and Messages

WebSocket does not send unframed “raw text” directly. A basic frame has:

```text
FIN | RSV1..3 | opcode | MASK | payload length | [mask key] | payload bytes
```

- **FIN**: whether this is the final frame of the message; text/binary messages can be split into multiple fragments.
- **Opcode**: `0x1` = text, `0x2` = binary, `0x0` = continuation, `0x8` = close, `0x9` = ping, `0xA` = pong.
- **Payload length**: 7 bits, or extended 16/64-bit forms when needed; you must read the exact byte count, not treat socket read boundaries as frame boundaries.
- **MASK**: per RFC 6455, **all client→server frames must be masked**. Server→client frames are **unmasked**. The 4-byte mask key uses XOR; masking **is not encryption** and does not protect secrets in place of TLS.
- **RSV bits** must be 0 unless a negotiated extension permits their use.
- **Control frames** such as ping/pong/close must not be fragmented and have a maximum payload length of 125 bytes.

```text
Client text message "HELLO":
client -> server: FIN=1, opcode=1, MASK=1, payloadLength=5,
                  4-byte mask key, 5 masked bytes

Server echo:
server -> client: FIN=1, opcode=1, MASK=0, payloadLength=10,
                  UTF-8 bytes "ECHO:HELLO"

Close:
client -> server: FIN=1, opcode=8, MASK=1, payload status 1000
server -> client: FIN=1, opcode=8, MASK=0, payload status 1000
```

**A WebSocket message is not the same as a frame.** A large message may be fragmented; listener `onText(..., last)` can be invoked multiple times. Do not parse/slice an individual JSON object in each callback if `last=false` and the application protocol expects the assembled message.

## 10. Java 17+: Opening a Loopback WebSocket, Handshake, and Real Exchange

This program demonstrates both **the role of `HttpClient` and the minimal bytes of the server-side RFC handshake**. A local `ServerSocket` acts as an educational WebSocket server: it receives the HTTP GET Upgrade, computes `Sec-WebSocket-Accept`, returns `101`, reads a **masked text frame**, sends an **unmasked text echo**, and completes the Close handshake.

The client application uses JDK 17's own **`HttpClient.newWebSocketBuilder()`**, not a raw socket client. It opens `ws://127.0.0.1:port/chat`, offers subprotocol `demo.chat`, sends `HELLO`, receives `ECHO:HELLO`, and closes with normal status `1000`.

**This is not a production WebSocket server.** The demo server only reads short frames (payload up to 125 bytes), one text message, and one Close frame; it does not support fragmented messages, extended lengths, arbitrary Ping/Pong timing, compression extensions, multiple clients, or TLS. Its purpose is to make the handshake/masking visible and verify the client API, **not** to build an Internet-facing server.

**File `WebSocketLoopbackDemo.java`:**

```java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public class WebSocketLoopbackDemo {
    private record Frame(int opcode, boolean masked, byte[] payload) {}
    private record Evidence(boolean correctRequest, boolean upgradeHeaders,
                            boolean version13, boolean validKey, String text) {}

    private static String line(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        for (;;) {
            int c = in.read();
            if (c < 0) throw new EOFException("Header ended unexpectedly");
            if (c == '\r') {
                if (in.read() != '\n') throw new IOException("Expected CRLF");
                return b.toString(StandardCharsets.US_ASCII);
            }
            if (c == '\n' || b.size() >= 8192)
                throw new IOException("Invalid/oversized line");
            b.write(c);
        }
    }

    private static Map<String, String> headers(InputStream in) throws IOException {
        Map<String, String> result = new TreeMap<>(String.CASE_INSENSITIVE_ORDER);
        for (int count = 0; count < 32; count++) {
            String l = line(in);
            if (l.isEmpty()) return result;
            int p = l.indexOf(':');
            if (p <= 0) throw new IOException("Invalid header");
            String name = l.substring(0, p).trim();
            String value = l.substring(p + 1).trim();
            result.merge(name, value, (a, b) -> a + ", " + b);
        }
        throw new IOException("Too many headers");
    }

    private static boolean token(String value, String name) {
        if (value == null) return false;
        for (String part : value.split(",")) {
            if (part.trim().equalsIgnoreCase(name)) return true;
        }
        return false;
    }

    private static Frame readClientFrame(InputStream in) throws IOException {
        int b0 = in.read(), b1 = in.read();
        if (b0 < 0 || b1 < 0) throw new EOFException("No frame");
        if ((b0 & 0x80) == 0) throw new IOException("Fragmented demo frame");
        boolean masked = (b1 & 0x80) != 0;
        int length = b1 & 0x7f;
        if (length >= 126 || length > 125 || !masked)
            throw new IOException("Expected short masked frame");
        byte[] mask = in.readNBytes(4);
        byte[] data = in.readNBytes(length);
        if (mask.length != 4 || data.length != length)
            throw new EOFException("Incomplete frame");
        for (int i = 0; i < data.length; i++)
            data[i] ^= mask[i % 4];
        return new Frame(b0 & 0x0f, masked, data);
    }

    private static void sendUnmasked(OutputStream out, int opcode, byte[] data)
            throws IOException {
        if (data.length > 125) throw new IllegalArgumentException("Demo limit");
        out.write(0x80 | opcode);
        out.write(data.length);
        out.write(data);
        out.flush();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress(loopback, 0));
            listener.setSoTimeout(5000);

            Future<Evidence> server = worker.submit(() -> {
                try (Socket peer = listener.accept()) {
                    peer.setSoTimeout(5000);
                    InputStream in = peer.getInputStream();
                    OutputStream out = peer.getOutputStream();
                    boolean correct = line(in).equals("GET /chat HTTP/1.1");
                    Map<String, String> h = headers(in);
                    boolean upgrade = token(h.get("Upgrade"), "websocket")
                            && token(h.get("Connection"), "Upgrade");
                    boolean v13 = "13".equals(h.get("Sec-WebSocket-Version"));
                    String key = h.get("Sec-WebSocket-Key");
                    byte[] decoded = Base64.getDecoder().decode(key);
                    boolean validKey = decoded.length == 16;

                    byte[] digest = MessageDigest.getInstance("SHA-1").digest(
                            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11")
                                    .getBytes(StandardCharsets.US_ASCII));
                    String accept = Base64.getEncoder().encodeToString(digest);
                    String response = "HTTP/1.1 101 Switching Protocols\r\n"
                            + "Upgrade: websocket\r\n"
                            + "Connection: Upgrade\r\n"
                            + "Sec-WebSocket-Accept: " + accept + "\r\n"
                            + "Sec-WebSocket-Protocol: demo.chat\r\n\r\n";
                    out.write(response.getBytes(StandardCharsets.US_ASCII));
                    out.flush();

                    Frame text = readClientFrame(in);
                    if (text.opcode() != 1 || !text.masked())
                        throw new IOException("Expected masked text frame");
                    String message = new String(text.payload(), StandardCharsets.UTF_8);
                    sendUnmasked(out, 1, ("ECHO:" + message)
                            .getBytes(StandardCharsets.UTF_8));

                    Frame close = readClientFrame(in);
                    if (close.opcode() != 8)
                        throw new IOException("Expected close frame");
                    sendUnmasked(out, 8, new byte[] { 0x03, (byte) 0xE8 });
                    return new Evidence(correct, upgrade, v13, validKey, message);
                }
            });

            CountDownLatch textReceived = new CountDownLatch(1);
            CountDownLatch closeReceived = new CountDownLatch(1);
            AtomicReference<String> echo = new AtomicReference<>("");
            AtomicInteger closeStatus = new AtomicInteger(-1);
            AtomicReference<Throwable> callbackError = new AtomicReference<>();
            WebSocket.Listener clientListener = new WebSocket.Listener() {
                private final StringBuilder parts = new StringBuilder();

                @Override public void onOpen(WebSocket socket) {
                    socket.request(1);
                }
                @Override public CompletionStage<?> onText(
                        WebSocket socket, CharSequence data, boolean last) {
                    parts.append(data);
                    if (last) {
                        echo.set(parts.toString());
                        textReceived.countDown();
                    }
                    socket.request(1);
                    return CompletableFuture.completedFuture(null);
                }
                @Override public CompletionStage<?> onClose(
                        WebSocket socket, int code, String reason) {
                    closeStatus.set(code);
                    closeReceived.countDown();
                    return CompletableFuture.completedFuture(null);
                }
                @Override public void onError(WebSocket socket, Throwable error) {
                    callbackError.set(error);
                    textReceived.countDown();
                    closeReceived.countDown();
                }
            };

            URI uri = URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/chat");
            WebSocket socket = HttpClient.newHttpClient().newWebSocketBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .subprotocols("demo.chat")
                    .buildAsync(uri, clientListener).get(5, TimeUnit.SECONDS);
            try {
                socket.sendText("HELLO", true).get(3, TimeUnit.SECONDS);
                if (!textReceived.await(3, TimeUnit.SECONDS) || callbackError.get() != null)
                    throw new IllegalStateException("No echo", callbackError.get());
                socket.sendClose(WebSocket.NORMAL_CLOSURE, "").get(3, TimeUnit.SECONDS);
                if (!closeReceived.await(3, TimeUnit.SECONDS) || callbackError.get() != null)
                    throw new IllegalStateException("No close", callbackError.get());
                Evidence info = server.get(3, TimeUnit.SECONDS);
                System.out.println("Request GET /chat HTTP/1.1: " + info.correctRequest());
                System.out.println("Upgrade headers: " + info.upgradeHeaders());
                System.out.println("WebSocket version 13: " + info.version13());
                System.out.println("Key is 16 bytes: " + info.validKey());
                System.out.println("Negotiated subprotocol: " + socket.getSubprotocol());
                System.out.println("Server received masked text: " + info.text());
                System.out.println("Client received text: " + echo.get());
                System.out.println("Close status: " + closeStatus.get());
            } finally {
                socket.abort();
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
```

**Compile and run with JDK 17+:**

```bash
javac --release 17 -encoding UTF-8 WebSocketLoopbackDemo.java
java WebSocketLoopbackDemo
```

**Verified stdout over TCP loopback:**

```text
Request GET /chat HTTP/1.1: true
Upgrade headers: true
WebSocket version 13: true
Key is 16 bytes: true
Negotiated subprotocol: demo.chat
Server received masked text: HELLO
Client received text: ECHO:HELLO
Close status: 1000
```

### Step-by-Step Explanation

1. The demo server binds `127.0.0.1` on port 0 so the OS assigns an ephemeral local port; both sides use the **same IPv4 loopback address** and send no traffic over a public network.
2. `HttpClient.newHttpClient().newWebSocketBuilder()` creates a builder; `.subprotocols("demo.chat")` offers a subprotocol.
3. `buildAsync(...)` constructs the HTTP GET opening handshake and validates the HTTP response. The demo server reads the request line and header fields, checking the `Upgrade`/`Connection` tokens, version 13, and 16-byte key length.
4. The server computes `Sec-WebSocket-Accept` using the standard formula and sends `HTTP/1.1 101 Switching Protocols` with `Sec-WebSocket-Protocol: demo.chat`.
5. The JDK client accepts the handshake and completes `CompletableFuture<WebSocket>`; `WebSocket.getSubprotocol()` returns the negotiated `demo.chat`.
6. In `onOpen`, the listener calls `socket.request(1)` to permit one receive callback. Without requesting demand, `onText` may never be called even if bytes have arrived.
7. `sendText("HELLO", true)` sends **one complete text message**. The client automatically builds a properly masked frame; the demo server reads the mask key and XORs the data to recover `HELLO`.
8. The server sends the unmasked frame `ECHO:HELLO`. Client `onText` appends fragments into a `StringBuilder` and uses `last` to know when the message is complete; the test triggers the latch once the full message arrives.
9. `sendClose(1000,"")` sends a Close frame to the server. The server reads it and sends a Close frame with status 1000; listener `onClose` observes the status, and the latch lets `main` finish.
10. `socket.abort()` in `finally` is defensive cleanup for the **test**; the graceful path already used the Close handshake beforehand. In production, do not treat `abort` as equivalent to an orderly close.
11. `readClientFrame` intentionally rejects large/fragmented frames and **is not a complete parser**. A public-facing server must use a production WebSocket implementation that supports protocol validation and resource limits.

One technical detail: `MessageDigest.getInstance("SHA-1")` in the demo server is strictly for the RFC handshake algorithm and adds no security to `ws`. To encrypt network data, use `wss` with TLS.

## 11. Java 17+: Handshake Failures and Inspecting the Response

Not every HTTP server is ready to upgrade to WebSocket. The third program opens a loopback raw server and intentionally creates **two failure cases**:

1. The server returns `HTTP/1.1 403 Forbidden` instead of 101 — the handshake is not accepted.
2. The server returns `101 Switching Protocols` but with an invalid `Sec-WebSocket-Accept` — **status 101 alone is not enough** for the client to trust this as a WebSocket.

`buildAsync(...)` must complete exceptionally. Java 17 provides `WebSocketHandshakeException.getResponse()` to inspect the status code of the rejected HTTP response, rather than returning an open socket.

**File `WebSocketHandshakeFailureDemo.java`:**

```java
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public class WebSocketHandshakeFailureDemo {
    private static void consumeHeaders(InputStream in) throws IOException {
        int matched = 0, total = 0;
        while (matched < 4) {
            int b = in.read();
            if (b < 0 || ++total > 16384) throw new IOException("Bad request");
            if (b == "\r\n\r\n".charAt(matched)) {
                matched++;
            } else {
                matched = b == '\r' ? 1 : 0;
            }
        }
    }

    private static int attempt(HttpClient client, URI uri) throws Exception {
        try {
            WebSocket connected = client.newWebSocketBuilder()
                    .buildAsync(uri, new WebSocket.Listener() {}).get(4, TimeUnit.SECONDS);
            connected.abort();
            return -1;
        } catch (ExecutionException failed) {
            Throwable cause = failed.getCause();
            if (cause instanceof WebSocketHandshakeException handshake)
                return handshake.getResponse().statusCode();
            throw new IllegalStateException("Unexpected error", cause);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (ServerSocket listener = new ServerSocket()) {
            listener.bind(new InetSocketAddress("127.0.0.1", 0));
            listener.setSoTimeout(4000);
            Future<?> server = executor.submit(() -> {
                try {
                    for (int i = 0; i < 2; i++) {
                        try (Socket peer = listener.accept()) {
                            peer.setSoTimeout(4000);
                            consumeHeaders(peer.getInputStream());
                            String reply = i == 0
                                    ? "HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
                                    : "HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                                    + "Connection: Upgrade\r\nSec-WebSocket-Accept: invalid-value\r\n\r\n";
                            peer.getOutputStream().write(
                                    reply.getBytes(StandardCharsets.US_ASCII));
                            peer.getOutputStream().flush();
                        }
                    }
                } catch (IOException error) {
                    throw new UncheckedIOException(error);
                }
            });
            URI uri = URI.create("ws://127.0.0.1:"
                    + listener.getLocalPort() + "/protected");
            HttpClient client = HttpClient.newHttpClient();
            int forbidden = attempt(client, uri);
            int invalidAccept = attempt(client, uri);
            server.get(4, TimeUnit.SECONDS);
            System.out.println("Rejected status: " + forbidden);
            System.out.println("Invalid accept rejected: " + (invalidAccept == 101));
            System.out.println("No usable WebSocket created: "
                    + (forbidden == 403 && invalidAccept == 101));
        } finally {
            executor.shutdownNow();
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WebSocketHandshakeFailureDemo.java
java WebSocketHandshakeFailureDemo
```

**Verified stdout on a JDK 17-compatible runtime:**

```text
Rejected status: 403
Invalid accept rejected: true
No usable WebSocket created: true
```

Do not misread `Invalid accept rejected: true` as “101 is an HTTP error code”. It means **HTTP 101 was sent by the server**, but **the client detected an invalid Accept and rejected it**. This confirms that upgrading to WebSocket also requires **valid headers**, not just the status code.

In practice, if `WebSocketHandshakeException` contains `401`/`403`, check auth/permissions, Origin, cookies, tokens, routes, and proxies. If HTTP 101 fails, check server/client compatibility, the key/accept pair, subprotocol/extensions, and whether intermediate hops are modifying headers. Never disable handshake validation just to “make it work”.

## 12. Using `WebSocket.Listener` Properly: `onOpen`, `request(n)`, and Fragments

Java 17 `WebSocket.Listener` receives these callbacks:

| Callback | When Invoked | What the Application Should Do |
|---|---|---|
| `onOpen(WebSocket)` | After the WebSocket is opened | Prepare state and call `request(n)` to receive callbacks |
| `onText(WebSocket, CharSequence, boolean last)` | Receiving part or all of a text message | Append text fragments, check size and `last`, request more demand |
| `onBinary(WebSocket, ByteBuffer, boolean last)` | Receiving binary data | Read/copy buffer bytes properly, save state, and check `last` |
| `onPing(WebSocket, ByteBuffer)` | Receiving a Ping control frame | JDK supports auto-Pong; can record metrics/liveness |
| `onPong(WebSocket, ByteBuffer)` | Receiving a Pong | Update liveness/RTT if the app uses a heartbeat |
| `onClose(WebSocket, int code, String reason)` | Receiving Close and ending the receive side | Transition to CLOSED state, clean up, stop sending data messages |
| `onError(WebSocket, Throwable)` | Error on the WebSocket channel/handler | Log with context, fail pending operations, clean up |

### `request(n)` Is Demand for the Number of **Receive Callbacks**

WebSocket maintains a counter of permitted receive method invocations. When newly opened, the counter is 0. `webSocket.request(1)` permits **one more** data-receiving callback; if the listener does not increase demand, text/binary messages may not be dispatched to the application even though the I/O stack is active.

```java
// Illustrative snippet; not a standalone class.
@Override public void onOpen(WebSocket ws) {
    ws.request(1);
}

@Override public CompletionStage<?> onText(
        WebSocket ws, CharSequence fragment, boolean last) {
    // Parse/accumulate fragments per the connection's context.
    ws.request(1);
    return CompletableFuture.completedFuture(null);
}
```

**One `request(1)` does not mean “one complete message”**: the Javadoc counts receive method invocations, and one message can produce multiple `onText`/`onBinary` callbacks due to fragmentation. `onOpen` and `onError` do not count as receive methods. After `onClose`/`onError`, the API stops calling listener methods.

### When Callbacks Process Slowly

Each receive method returns a `CompletionStage<?>`. If processing completes immediately, returning `CompletableFuture.completedFuture(null)` is appropriate. If it must be processed asynchronously, you can return a stage that completes once the state/buffer has been handled per policy; avoid blocking the event-loop/dispatcher thread. Also consider **when to call `request(n)`** so you do not build an unbounded backlog.

**Do not call `request(Long.MAX_VALUE)` just to mask bugs** if the application does not control memory and buffers/queues. Enforce message size limits, queue size limits, client rate limits, and an appropriate slow-consumer policy.

### Fragmented Text

Applications should not assume every `onText` call is a complete JSON document. When `last=false`, it is a fragment; you may need to append to a `StringBuilder` and parse when `last=true`. For large messages, cap accumulated bytes/chars to prevent memory exhaustion. In the loopback example, `HELLO` and `ECHO:HELLO` are tiny, yet the listener still uses the `last` boolean.

## 13. Sending Text/Binary, Ping/Pong, and Close

### 13.1. Sending Text or Binary

```java
// Illustrative snippet: 'ws' is a connected WebSocket.
CompletableFuture<WebSocket> sent =
        ws.sendText("hello", true);

// For binary:
ByteBuffer buffer = ByteBuffer.wrap(new byte[] {1, 2, 3});
CompletableFuture<WebSocket> binarySent =
        ws.sendBinary(buffer, true);
```

`sendText`/`sendBinary` **initiates a send operation** and returns a `CompletableFuture<WebSocket>` for that operation. **Future completion does not prove the remote application has read or committed it.** If you need to know the server processed it successfully, the application protocol must have **response/ACK correlation**.

The `last` boolean determines whether this is the final fragment of the text/binary message. If `last=false`, you can send continuation data of the same type afterward. Do not issue two conflicting send operations while a previous operation is still pending; the Javadoc notes it can return an exceptional future with `IllegalStateException` if sent out of order or in the wrong state.

Do not modify the source `CharSequence` or `ByteBuffer` while the send Future is pending. For binary, the buffer has mutable position/limit and payload; manage ownership to avoid races.

### 13.2. Ping/Pong

```java
// Illustrative snippet; requires importing java.nio.ByteBuffer.
ws.sendPing(ByteBuffer.wrap(new byte[] {0x01}));
```

WebSocket `Ping` checks liveness or latency as needed by the application. The JDK WebSocket **automatically handles received Pings** by sending a Pong per the protocol; the listener can still receive `onPing` if demand permits. Do not confuse Ping/Pong control frames with a business protocol's JSON heartbeat.

If measuring RTT, attach a small correlation payload and track the pong deadline, while also accounting for proxy/server/load-balancer idle timeouts. **Do not treat a single missed Pong as definitive proof that a user is offline**, as scheduling, network, and policies can affect it.

### 13.3. Orderly Close and Abort

```java
// Illustrative snippet:
ws.sendClose(WebSocket.NORMAL_CLOSURE, "")
        .whenComplete((ignored, error) -> {
            // Record Close send result and clean up app state.
        });

// When graceful cleanup is not possible, you can:
ws.abort();
```

`sendClose(1000, "")` initiates a normal Close frame. The JDK WebSocket automatically responds to a received Close per the contract, and `onClose` is invoked when the peer sends Close. `abort()` closes input/output abruptly rather than performing a graceful Close handshake; use it only for errors or forced-deadline cleanup.

**Code `1000`** = normal closure. Code `1006` is commonly used as an observed “abnormal closure” status and **must not be sent on the wire** as a Close code. A TCP connection cut without a Close handshake must be logged as abnormal and pending requests handled accordingly.

### 13.4. Data Sources and Business ACKs

Suppose a client sends `{"action":"charge","amount":100}` over WebSocket. `sendText` completing only indicates the send operation finished on the client/JDK side. The server may not have parsed or committed it yet, or the connection may drop before the response arrives. You need message IDs, server deduplication/idempotency, and ACKs per the business contract. **WebSocket does not provide exactly-once business delivery** out of the box.

## 14. `wss` in Production: TLS, Proxies, Routing, and Deployment

A production endpoint typically looks like:

```text
Java WebSocket client
     |
     | wss://realtime.example.test/chat
     | DNS → TCP 443 → TLS
     v
Reverse proxy / Load balancer (TLS terminator or passthrough)
     |
     | HTTP/1.1 Upgrade + Connection headers preserved properly
     v
WebSocket backend
     |
     | 101 Switching Protocols
     v
Long-lived bidirectional connection
```

Things to verify:

1. **Certificate trust:** valid TLS certificate, matching hostname, trusted chain; never disable SSL hostname verification just to get a connection working.
2. **Proxy Upgrade:** the reverse proxy must allow WebSocket upgrades and forward `Upgrade`/`Connection` properly on the corresponding HTTP/1.1 leg. Do not blindly copy hop-by-hop fields across multiple HTTP layers; the proxy must apply proper semantics.
3. **Idle timeout:** long-lived connections can be severed by load balancers/firewalls after idle periods; use Ping/Pong/heartbeats according to backend and infrastructure policy.
4. **Sticky sessions/state:** if the backend holds session state in memory, reconnects may land on a different node. Use a shared session store, routing, resume tokens, or a pub/sub service; do not assume the same server on reconnect.
5. **Origin/auth checks:** validate Origin for browser clients, and authenticate sessions/tokens and subscription permissions on the server. `wss` encrypts the transport but does not replace authorization.
6. **Resource limits:** each connection holds file descriptors, buffers, and thread/event-loop resources. Cap concurrent connections, per-user rates, message sizes, queues, and session lifetimes.
7. **Certificate rotation/reload:** opened WebSocket connections have long lifecycles; plan rotation/reconnection as needed, and do not assume all existing sessions immediately pick up TLS updates.
8. **Metrics:** handshake success/failure, 101/403/401 statuses, TLS errors, active connections, bytes/messages, ping RTT, close codes, reconnect counts, and failed authorizations.

### `wss` and Proxy Authentication

`HttpClient` has proxy and authenticator configuration; the Java WebSocket builder uses that client as its configuration source. However, origin `401`, proxy `407`, and authorization `403` must be distinguished. If the server returns HTTP `401` before upgrading, that is still a failed HTTP handshake. Do not treat every `401` response as “WebSocket connected, but the user lacks permission”.

### `wss` Does Not Mean “WebSocket Is Always Port 443”

The default port for `wss` is 443, but a URI can specify a custom port, such as `wss://test.example.test:8443/ws`. What matters is the correct scheme/TLS/proxy route and certificate, not a single port number.

## 15. Common Failures When Opening a WebSocket

| Symptom | Layer to Check | How to Fix |
|---|---|---|
| `buildAsync` fails with HTTP 404 | URL/route | Wrong `/ws` path, host, vhost, or WebSocket not enabled on API |
| HTTP 403 | Origin/ACL/auth | Allowlist, token/permissions, session, reverse proxy policy |
| HTTP 401 | Auth challenge | Credentials, cookies, realm, TLS; do not treat as 101 |
| HTTP 400 / 426 | Version/headers/proxy | `Upgrade`, `Connection`, version 13, handshake syntax |
| HTTP 101 but handshake exception | Invalid Accept/subprotocol/extension | Check key/Accept and header negotiation |
| `SSLHandshakeException` on `wss` | TLS/certificates | Truststore, hostname, SNI, cert expiry, and backend TLS |
| TCP connection refused | Network/listener | DNS, port, firewall, whether service is running |
| Handshake timeout | TCP/TLS/proxy/server | `WebSocket.Builder.connectTimeout`, network trace, proxy latency |
| Handshake succeeds but no `onText` | Listener demand | Was `request(n)` called? Any `onError`/`onClose`? |
| Client sends text but server app does not receive it | Framing/app handler | WebSocket path, opcode, payload format, auth, business routing |
| `sendText` future completes but no ACK | Missing app-level ACK | Design correlation IDs and status replies |
| Connection lives a few minutes then drops | Idle timeout, NAT/proxy | Ping/Pong policy, reconnect, and resume |
| Browser cannot connect `ws` from HTTPS page | Mixed-content policy | Use valid `wss` |
| `1006` in telemetry | Abnormal close | TCP reset, proxy idle, TLS/network error |
| Multiple `onText` calls for one message | Fragmentation | Assemble until `last=true`, enforce size limit |
| Unexpected `IllegalStateException` on send | Concurrent/pending send or bad state | Serialize sends, check close/output state |
| Slow subscriber causes memory growth | Demand/queue/backpressure | Bounded queue, sensible `request(n)`, drop/close policy |
| Need to write a WebSocket server in Java 17 | Misunderstanding `HttpClient`'s role | Use a framework/server implementation that supports WebSocket |

### Minimal Diagnostic Checklist

1. **Check the URI:** is it `ws` or `wss`, with the right host/port/path/query?
2. For `wss`, **isolate TLS**: are the certificate/hostname/ALPN/proxy correct?
3. **Check the HTTP handshake:** is there a valid 101 status, `Upgrade`/`Connection`, and Accept?
4. **Check subprotocol:** what did the client offer, what did the server pick, and is it valid?
5. Once the handshake completes, **stop debugging it like an HTTP response body**; switch to WebSocket frames/messages, Listener, and demand.
6. **Check `onOpen`/`request(n)`/`onText`/`onError`/`onClose`** to rule out a client bug where receive callbacks are never requested.
7. If there is no business response, inspect the **application protocol, authentication, message ID, and ACK**, not just network frames.
8. Inspect **Close codes**, Ping/Pong/idle timeouts, and proxy/firewall resources when failures only occur after running for a while.

Do not log `Authorization`/cookies/tokens or sensitive payloads directly. Log request/connection IDs and error statuses/classes for correlation.

## 16. Designing a Production WebSocket Client in Java 17

A real-world client needs lifecycle management rather than just calling `buildAsync` and discarding the object:

```text
DISCONNECTED
    |
    | validate URI, credentials, config
    v
CONNECTING
    |
    | newWebSocketBuilder().buildAsync(...)
    |    ├── failure → FAILED (diagnose handshake/TLS)
    v
OPEN
    |
    | onOpen -> request(n)
    | subscribe/authorize app-level, send/receive messages
    | track message ids, bounded outbound queue, heartbeat
    |
    ├── recoverable network failure
    |        -> retry with backoff, fresh auth, resume cursor
    |
    └── requested stop
          -> sendClose(1000,...)
          -> wait close handshake with deadline
          -> abort only when forced, cleanup state
```

**Do not auto-reconnect infinitely without limits**: if the server returns HTTP `403` because of missing permissions, retrying every 10 ms is pointless and creates load. Distinguish handshake rejections from transient network errors, cap attempts, and use backoff with jitter; when refreshing credentials, avoid repeatedly sending expired tokens.

**Do not assume reconnecting automatically restores prior state**: subscriptions, in-flight messages, and cursors can be lost when the TCP/WebSocket connection changes. If the application needs to resume, the server must provide a resume token, last-event ID, or query/snapshot mechanism. For commands with side effects, retrying the same message requires idempotency/correlation per the contract.

**Use `CompletableFuture` correctly:** the `buildAsync` future completes when the WebSocket is created, not when all future messages finish. The `sendText` future completes for the **send operation**, not the ACK. `onClose` reflects the peer's close; `onError` reflects an error; both should trigger cleanup while avoiding double-completing the request registry.

**Do not block for long inside callbacks.** With large JSON payloads, decoding business data, writing to a DB, or calling blocking APIs inside `WebSocket.Listener` can impact dispatching/backpressure. Offload heavy work to a separate executor with a bounded queue and managed lifecycle.

### Safe Behavior Pattern (Pseudocode)

```text
connect():
    validate ws/wss URI + allowed origins/hosts + auth configuration
    opening = client.newWebSocketBuilder()
                    .connectTimeout(handshakeDeadline)
                    .subprotocols(expectedProtocol)
                    .buildAsync(uri, listener)
    on success -> state OPEN; send subscribe/auth message if protocol requires
    on failure -> classify TLS / HTTP handshake / network; retry per policy

onOpen(socket):
    socket.request(1)

onText(fragment, last):
    append with maxMessageBytes
    if last:
        decode/validate application envelope
        correlate messageId; update business state
    request next fragment when consumer capacity available

sendCommand(command):
    assign stable id and enqueue in bounded queue
    ws.sendText(serialize(command), true)
    on send error -> mark transport failure (business outcome unknown)
    await app ACK if API requires confirmation

stop():
    stop accepting new outbound commands
    ws.sendClose(1000, "")
    wait for close with deadline; abort if necessary
    fail/reconcile in-flight commands
```

This is a descriptive algorithm, **not standalone Java code**, because state machine management, queuing, authentication, and timeouts vary by application.

## 17. Self-Check Questions

**Question 1.** What is the core difference between `ws://` and `wss://`?  
**Answer:** `wss` runs WebSocket over TLS to protect the transport leg and defaults to port 443; `ws` has no TLS and defaults to port 80.

**Question 2.** Does WebSocket keep using HTTP request/response throughout the entire session?  
**Answer:** No. Classic RFC 6455 starts with an HTTP/1.1 GET Upgrade and 101; afterward, WebSocket frames are exchanged over the upgraded connection.

**Question 3.** Is `Sec-WebSocket-Key` a password or TLS encryption key?  
**Answer:** No. It is a nonce used to verify the opening handshake; it does not replace user authentication or TLS.

**Question 4.** What is the formula for `Sec-WebSocket-Accept`?  
**Answer:** Base64 of the SHA-1 hash of the **Base64 `Sec-WebSocket-Key` string concatenated with the GUID** `258EAFA5-E914-47DA-95CA-C5AB0DC85B11`.

**Question 5.** The server returns HTTP 101, but `Sec-WebSocket-Accept` is wrong. What should the Java client do?  
**Answer:** Reject the opening handshake; `buildAsync` completes exceptionally (typically with `WebSocketHandshakeException`).

**Question 6.** Does Java 17 open a WebSocket client via `HttpClient.send(HttpRequest)` or another API?  
**Answer:** Via `HttpClient.newWebSocketBuilder().buildAsync(uri, listener)`. `send/sendAsync` is the HTTP request-response API.

**Question 7.** Is `WebSocket.Builder.header("Sec-WebSocket-Key", "...")` the way to choose your own Key?  
**Answer:** No. WebSocket protocol headers are reserved and the builder API does not allow setting them manually; the HTTP client generates the Key automatically.

**Question 8.** After `buildAsync` succeeds, you call `sendText("hello", true)`; does the completed Future mean the server committed a command?  
**Answer:** No. The Future reflects the send operation in the WebSocket API, not a business ACK.

**Question 9.** The listener is open, but `onText` never arrives even though the server sent data. What should you check?  
**Answer:** Check whether `onOpen` called `request(n)` and check `onError`/`onClose` state before investigating network/protocol issues.

**Question 10.** Should `onText(ws, data, false)` immediately parse `data` as a complete JSON message?  
**Answer:** Not by default. `last=false` means it is not the final fragment, so it must be accumulated with proper context and size limits.

**Question 11.** Are client→server frames required to be masked, and does masking provide secret encryption?  
**Answer:** `MASK=1` with an XOR mask key is mandatory per RFC 6455; masking is not encryption, so secrets require `wss`.

**Question 12.** Is it valid for the server to return a `Sec-WebSocket-Protocol` name not in the client's offered list?  
**Answer:** No. The subprotocol must be from the valid offer; the Java client can reject an invalid handshake.

**Question 13.** Why do browsers send `Origin`, yet the server must not use Origin as proof of user identity?  
**Answer:** Origin is used to evaluate the source of a browser connection; non-browser clients can spoof the header. Separate auth/authorization is required.

**Question 14.** Does `WebSocket.Builder.connectTimeout(5s)` mean the WebSocket automatically closes after 5 seconds?  
**Answer:** No. It limits establishing the connection/handshake, not the session lifetime.

**Question 15.** `wss://example.test` uses a certificate that does not match the hostname. Should you disable certificate validation to make it run?  
**Answer:** No. Fix the certificate/truststore/hostname rather than lowering security to hide errors.

**Question 16.** When a WebSocket closes abnormally, does reconnecting automatically deliver all missed messages?  
**Answer:** No. Separate resume cursors, replay history, or application ACKs are needed if business requirements demand it.

**Question 17.** How does `sendClose(1000, "")` differ from `abort()`?  
**Answer:** `sendClose` attempts an orderly close handshake; `abort` closes abruptly, typically for errors or forced cleanup.

**Question 18.** If the server returns `401`/`403` during the opening handshake, is there a WebSocket to send a fix-up message on?  
**Answer:** No. The handshake never completed; the client handles the HTTP handshake/auth failure and initiates a new connection once conditions are met.

**Question 19.** Does `wss` through a TLS-terminating proxy guarantee that the backend leg also uses TLS?  
**Answer:** No. You must verify each hop's configuration; outer HTTPS/WSS does not automatically guarantee an encrypted backend leg.

**Question 20.** When do you need to implement a `WebSocket server` using a framework other than Java `HttpClient`?  
**Answer:** When the server must accept many WebSocket connections and manage upgrades, authentication, frames, resource limits, and the app protocol. Java 17's `java.net.http.WebSocket` is a client API.

## 18. Summary and Standard References

- `ws` is WebSocket without TLS; `wss` uses TLS. Default ports are **80** and **443** respectively; custom ports can be specified.
- Classic RFC 6455: **HTTP/1.1 GET Upgrade → valid server HTTP 101 → WebSocket frames**. The `Sec-WebSocket-Accept` header must be computed accurately from `Sec-WebSocket-Key` and the GUID.
- `Sec-WebSocket-Key`/Accept **are not authentication or encryption**.
- Java 17 uses **`HttpClient.newWebSocketBuilder().buildAsync(uri, listener)`**; `HttpClient.send/sendAsync` is not the API for handling WebSocket sessions.
- `WebSocket.Builder` manages handshake configuration, optional headers, and subprotocols; `WebSocket` sends text/binary/ping/pong/close; `WebSocket.Listener` receives callbacks.
- **`request(n)` is demand for callbacks**, not sending an HTTP request and not guaranteeing n complete messages.
- Client frames **must be masked**, server frames **must not be masked**; masking does not replace TLS.
- `sendText` completing is not a business ACK; long-lived connections need resource limits, heartbeats, reconnects, timeouts, and separate correlation/idempotency.
- Handshakes fail on HTTP 403/401/404, TLS errors, 101 with an invalid Accept, or proxy issues; never bypass checks to “force connect”.
- The hands-on examples use loopback `ws` to show the handshake clearly; **in production use `wss`** and enforce TLS, Origin, authentication, subprotocol, and authorization controls.

### References

- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455.html), especially Sections 3–5, 7, and 10.
- [RFC 8441 — Bootstrapping WebSockets with HTTP/2](https://www.rfc-editor.org/rfc/rfc8441.html), extended CONNECT mechanism distinct from HTTP/1.1 Upgrade.
- [Java 17 `HttpClient` — creating a WebSocket Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java 17 `WebSocket.Builder` — `header`, `connectTimeout`, `subprotocols`, `buildAsync`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Builder.html).
- [Java 17 `WebSocket` — `sendText`, `request`, `sendClose`, `abort`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.html).
- [Java 17 `WebSocket.Listener` — callbacks, fragments, and demand](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocket.Listener.html).
- [Java 17 `WebSocketHandshakeException` — failed handshake HTTP response](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/WebSocketHandshakeException.html).
