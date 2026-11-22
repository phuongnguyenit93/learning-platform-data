# Java Networking API Map: `java.net`, `java.nio.channels`, `java.net.http`, JSSE, and `jdk.httpserver`

In Java, "working with the network" can mean resolving domain names, opening a TCP connection, sending UDP datagrams, building a custom protocol, calling a REST API over HTTPS, or receiving HTTP requests. These tasks sit at **different levels of abstraction**. Choosing the right API helps you avoid reimplementing HTTP from scratch, mishandling TCP data boundaries, or accidentally bypassing TLS verification.

This lesson focuses on the **JDK API selection map**, applicable to **Java 17+**. Some version-specific differences will be noted explicitly. This is a lesson on Java SE/JDK networking APIs and does not cover web frameworks such as Spring MVC, WebFlux, or Netty.

## 1. Objectives and Big Picture

After this lesson, you will be able to:

- Correctly identify the package, module, client/server role, and protocol for each API group.
- Choose `Socket`/`ServerSocket`, channels + `Selector`, `HttpClient`, JSSE, or `HttpServer` based on practical requirements.
- Understand that HTTP is an application protocol, TLS is a connection protection layer, and TCP/UDP are transport mechanisms; they are not interchangeable terms.
- Distinguish between blocking, non-blocking, and asynchronous I/O; understand why `read()` does not mean "a complete message has been received."
- Run a pure-JDK HTTP client/server example with timeouts, resource closing, and verifiable output.

### Quick Reference Table

| Group | Containing Module | Representative Classes/Types | Primary Tasks | Built-in Roles? |
| --- | --- | --- | --- | --- |
| `java.net` | `java.base` | `InetAddress`, `InetSocketAddress`, `URI`, `Socket`, `ServerSocket`, `DatagramSocket` | Addresses, low-level TCP/UDP, URI/URL | TCP client/server; UDP endpoint |
| `java.nio.channels` with `java.nio.ByteBuffer` | `java.base` | `SocketChannel`, `ServerSocketChannel`, `DatagramChannel`, `Selector`, `SelectionKey` | Buffer-based I/O; multiplexing multiple channels; optional non-blocking | Low-level TCP/UDP client/server |
| `java.net.http` | `java.net.http` | `HttpClient`, `HttpRequest`, `HttpResponse`, `WebSocket` | HTTP/1.1, HTTP/2, and WebSocket client | **Client**; not an HTTP server |
| JSSE: `javax.net.ssl` | `java.base` | `SSLContext`, `SSLSocket`, `SSLServerSocket`, `SSLEngine`, `SSLParameters` | TLS, certificates, and peer authentication | TLS client/server; does not define HTTP |
| `com.sun.net.httpserver` | `jdk.httpserver` | `HttpServer`, `HttpsServer`, `HttpExchange`, `HttpHandler` | Small, simple HTTP/HTTPS server | **Server**; not an HTTP client |

> **Common Point of Confusion:** `java.net.http` is a package in the `java.net.http` module; whereas `jdk.httpserver` is a **different** module that provides the `com.sun.net.httpserver` package. JSSE is referred to by its technology name; its core classes belong to `javax.net.ssl`, not a `jsse` package.

You can visualize the selection flow as follows:

~~~text
Do you want to exchange network data?
|
+-- Only need addresses, hostnames, ports, URIs? --> java.net
|
+-- Calling an HTTP(S) API from Java? -------------> java.net.http.HttpClient
|                                                   (HTTPS TLS is handled underneath)
|
+-- Receiving HTTP requests using the JDK? --------> jdk.httpserver.HttpServer
|                                                   or HttpsServer + TLS configuration
|
+-- Custom TCP/UDP protocol?
    |
    +-- Simple blocking stream I/O ---------------> java.net.Socket / ServerSocket
    |                                               or DatagramSocket for UDP
    |
    +-- ByteBuffer, many connections,              -> java.nio.channels
    |   multiplexed event loop?                     (+ Selector when non-blocking)
    |
    +-- Need to protect the connection with TLS? -> JSSE:
                                                    SSLSocket or SSLEngine
~~~

This diagram shows the **developer's entry points**, not a claim that each package corresponds to a single OSI layer. For example, `HttpClient` uses transport and TLS via its underlying implementation; normally, callers do not create sockets themselves.

## 2. Distinguishing Protocols, Connections, and Data

- **IP/Addresses:** identify destinations at the network layer. `InetAddress` represents an IP address; `InetSocketAddress` pairs an address/hostname with a port.
- **TCP:** an **ordered, reliable byte stream within the scope of an active connection** that does not preserve application message boundaries. A single send may be received across multiple `read()` calls, or multiple sends may be coalesced when reading.
- **UDP:** transmits individual datagrams, preserving packet boundaries in the API, but does not guarantee delivery, ordering, or deduplication. Oversized datagrams may be fragmented or lost.
- **HTTP:** an application protocol consisting of method, URI, headers, status, and body; it runs over connections managed by the HTTP client/server. `HttpClient` handles syntax/protocol details so the application can focus on requests and responses.
- **TLS:** a cryptographic mechanism to protect confidentiality, integrity, and peer authentication using certificates/trust configuration. **HTTPS = HTTP over TLS** in the appropriate HTTP versions; TLS by itself does not create HTTP requests.

For example: "send a JSON POST to `https://api.example.com/items`" is an **HTTP client** task, so start with `HttpClient`. "Send binary frames of a custom protocol over TCP" is a **socket/channel** task, then consider JSSE if TLS is needed. Do not choose a low-level API just because HTTP also uses the network.

## 3. `java.net`: Addresses, URIs, and Traditional Sockets

### 3.1. Address and Resource Types

- `InetAddress`: represents IPv4/IPv6; `InetAddress.getByName("example.com")` may perform name resolution. Resolution depends on DNS/environment and can fail (`UnknownHostException`).
- `InetSocketAddress`: an endpoint consisting of host/IP and port. Used in `connect`, `bind`; `new InetSocketAddress("127.0.0.1", 8080)` is the loopback endpoint on port 8080.
- `NetworkInterface`: queries the machine's network interfaces and addresses; useful when working with multiple NICs, IPv4/IPv6, or multicast.
- `URI`: syntactically models an identifier with scheme, authority, path, query, and fragment; creating a `URI` does not open a network connection. A URI can be relative.
- `URL`/`URLConnection`: older APIs for locating/opening resource connections. For modern HTTP clients, `java.net.http.HttpClient` is usually preferred; `URI` is still used to specify request addresses.

Example of distinguishing components:

~~~java
URI endpoint = URI.create("https://example.com:443/api/items?page=2");
String scheme = endpoint.getScheme(); // "https"
String host = endpoint.getHost();     // "example.com"
int port = endpoint.getPort();        // 443
~~~

This is an **illustrative snippet inside a method** (requires `import java.net.URI;`); it does not send a request. When accepting URIs from untrusted sources, validate the scheme, host, port, and redirect policy to prevent SSRF or unintended access to internal targets.

### 3.2. Blocking TCP: `Socket` and `ServerSocket`

- **Client:** `Socket` connects to a TCP endpoint; `getInputStream()` and `getOutputStream()` read/write bytes.
- **Server:** `ServerSocket.bind(...)` opens a listening port; `accept()` returns **a new `Socket` for the accepted connection**. The listening socket and connected socket have different lifecycles.
- `connect(endpoint, timeoutMillis)` limits the time to **establish the connection**; `socket.setSoTimeout(timeoutMillis)` limits the wait time of the corresponding blocking read operation. They are not a single overall timeout for the entire transaction.
- `InputStream.read(...)` may return fewer bytes than requested, and returns `-1` at end of stream; this does **not** mean each `read` corresponds to one message.
- Close `Socket` with try-with-resources; design how to detect EOF, errors, and connection cancellation.

TCP client configuration pattern (illustrative snippet inside a method; requires a real server at `host:port`):

~~~java
try (Socket socket = new Socket()) {
    socket.connect(new InetSocketAddress("host.example", 9000), 2_000);
    socket.setSoTimeout(3_000);
    InputStream in = socket.getInputStream();
    OutputStream out = socket.getOutputStream();
    // Send/receive according to the application protocol framing.
}
~~~

Imports for the snippet above: `java.net.Socket`, `java.net.InetSocketAddress`, `java.io.InputStream`, `java.io.OutputStream`. The port and hostname are **example values** only, not guaranteed active service addresses.

With TCP, the application **must define its own framing**, for example:

1. Each message ends with `\\n` (requires escaping rules and charset convention).
2. Each message has a 4-byte length prefix in a defined byte order, followed by exactly N bytes of data.
3. A delimiter or equivalent structure (requires handling size limits).

Do not use `in.available()` to conclude that a full message has arrived; it only reports how many bytes can be read immediately without blocking under the current implementation, not the total message length.

### 3.3. UDP: `DatagramSocket`, `DatagramPacket`

`DatagramSocket` sends/receives `DatagramPacket` instances containing bytes, an address, and a port. Unlike TCP, there is no `accept()` per connection; the application must handle packet loss, retries, ordering, and duplicates itself **if the protocol requires them**. `MulticastSocket` relates to multicast; at the channel level, there is `DatagramChannel`.

Example of sending a loopback UDP datagram (illustrative inside a method; with no receiver, no output is expected):

~~~java
byte[] payload = "ping".getBytes(StandardCharsets.UTF_8);
try (DatagramSocket udp = new DatagramSocket()) {
    DatagramPacket packet = new DatagramPacket(
        payload, payload.length, InetAddress.getLoopbackAddress(), 9999);
    udp.send(packet);
}
~~~

Imports: `java.net.DatagramSocket`, `java.net.DatagramPacket`, `java.net.InetAddress`, `java.nio.charset.StandardCharsets`. A successful send does **not** prove the receiver received or processed the packet.

## 4. `java.nio.channels`: Channels, Buffers, and Multiplexing

NIO does not mean "automatically faster" or "always non-blocking." Many channels can operate in **blocking** mode; a newly created `SocketChannel` is in blocking mode by default. Only after calling `configureBlocking(false)` on a selectable channel can you perform operations in the proper non-blocking model and register with a `Selector`.

| Component | Role |
| --- | --- |
| `SocketChannel` | TCP endpoint for connecting and reading/writing via `ByteBuffer` |
| `ServerSocketChannel` | TCP listener; `accept()` returns a `SocketChannel` |
| `DatagramChannel` | UDP via `ByteBuffer` |
| `Selector` | Waits for readiness events across multiple `SelectableChannel` instances in an event loop |
| `SelectionKey` | Uses `OP_ACCEPT`, `OP_CONNECT`, `OP_READ`, `OP_WRITE` to track readiness conditions |
| `AsynchronousSocketChannel` / `AsynchronousServerSocketChannel` | Asynchronous API completing via `Future` or `CompletionHandler`; distinct from the `Selector` event loop |

### 4.1. `ByteBuffer` Lifecycle

A buffer has `capacity`, `position`, and `limit`:

~~~text
When receiving bytes:
channel.read(buffer) -> buffer.flip() -> process valid bytes
                   -> buffer.compact() or clear() -> next read
When sending bytes:
buffer holds bytes -> buffer.flip() -> channel.write(buffer)
                  -> continue writing while buffer.hasRemaining()
~~~

- `flip()`: switches from writing into the buffer to reading from the buffer.
- `clear()`: resets indices for new writes; **does not erase physical bytes**.
- `compact()`: preserves unconsumed bytes and moves the position for subsequent writes.
- `SocketChannel.read(buffer)` in non-blocking mode may return `0`; in both modes it may read fewer bytes than desired; `-1` indicates the peer has closed its sending side.
- `write(buffer)` may write **part** of the remaining bytes in the buffer. You must keep the remainder and continue writing under the appropriate condition; never assume a single `write` sent everything.
- UTF-8 sequences can be split across multiple `read` calls; decoders/framing must handle incomplete bytes rather than arbitrarily decoding each chunk into a `String`.

### 4.2. What Does `Selector` Do?

Typical workflow:

1. Open `ServerSocketChannel`, bind, and call `configureBlocking(false)`.
2. Open `Selector`, register the server channel with `OP_ACCEPT`.
3. Loop calling `selector.select()` to wait for at least one ready channel; iterate over `selectedKeys()`.
4. On `OP_ACCEPT`, call `accept()`, configure the accepted channel as non-blocking, and register `OP_READ`.
5. On `OP_READ`, read into a buffer, accumulate frames, and process; on `OP_WRITE`, flush any remaining unsent data.
6. Remove processed keys from the selected set, handle connection errors/EOF, and close resources.

**Readiness does not guarantee** that an operation will read/write all data. In particular, keeping `OP_WRITE` registered when there is no pending data can cause the event loop to spin continuously because sockets are usually writable. Enable it only when there is pending output and disable it once everything has been sent.

This model fits when you must manage many concurrent connections with explicit framing and state. In return, the application is responsible for state machines, backpressure, partial I/O, and key/channel cleanup. For a moderate number of connections and simple processing, blocking I/O is often easier to read, test, and maintain. Java 21+ also offers virtual threads to express many blocking tasks straightforwardly; that is a **concurrency choice**, not a change to TCP semantics or framing.

## 5. `java.net.http`: High-Level HTTP Client

This is the standard API since Java 11 for sending HTTP requests, receiving HTTP responses, and creating WebSocket clients. This package belongs to the `java.net.http` module, independent of the `jdk.httpserver` module.

- `HttpClient`: configures preferred HTTP version, redirect policy, proxy, executor, cookie handler, authenticator, TLS, and connect timeout. Reuse instances to benefit from connection management.
- `HttpRequest`: URI, method (`GET`, `POST`, ...), headers, body publisher, per-request timeout.
- `HttpResponse<T>`: status code, headers, URI/version, and body of type `T` via `BodyHandlers` (String, byte array, file, stream, etc.).
- `send(request, handler)`: **synchronous** call that waits for the result; `sendAsync(...)`: returns `CompletableFuture<HttpResponse<T>>`, without blocking the calling thread until the response completes.
- `WebSocket`: WebSocket protocol client with builder/listener; does not turn `HttpClient` into a WebSocket server.

HTTP/2 is supported and often preferred, but the actual version used depends on the server, TLS/ALPN, and negotiation; it may fall back to HTTP/1.1. Do not assume every request uses HTTP/2. This API **does not implement HTTP/3 as a standard capability in Java 17/21**.

An illustration of an HTTPS call (inside a method, requires network connectivity):

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
System.out.println(response.statusCode());
~~~

Imports: `java.net.URI`, `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `java.time.Duration`, `java.nio.charset.StandardCharsets`. The method containing this snippet must handle/declare `IOException` and `InterruptedException`. HTTP 4xx/5xx statuses **are still valid responses**; check `statusCode()` yourself rather than expecting `send()` to always throw an exception for application errors.

For async:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
future.thenAccept(r -> System.out.println(r.statusCode()));
~~~

This snippet uses the `client` and `request` created above; it requires importing `java.util.concurrent.CompletableFuture`. Production code must manage completion, timeouts, cancellation, and `CompletableFuture` errors; if the program exits before the future completes, the callback is not guaranteed to have run.

**Different timeouts:** `connectTimeout` only bounds the connection phase; `HttpRequest.Builder.timeout` is the request/response timeout defined by the API. Streaming, retries, cancellation, and overall business deadlines must still be designed explicitly. Avoid reading large bodies entirely into RAM when you can stream or write to a file.

## 6. JSSE (`javax.net.ssl`): Securing Connections with TLS

JSSE stands for Java Secure Socket Extension, providing TLS at the transport layer. It does **not** build HTTP requests, routing, or JSON. Its core components include:

| Component | Responsibility |
| --- | --- |
| `SSLContext` | Configures TLS protocols and creates factories/`SSLEngine`; can be initialized with key/trust managers |
| `SSLSocket` / `SSLServerSocket` | TLS-enabled TCP sockets, suitable for the blocking stream model |
| `SSLEngine` | Transport-independent TLS processor; the developer coordinates wrap/unwrap, handshake, buffers, and I/O, typically with NIO |
| `SSLParameters` | TLS configuration such as endpoint identification, appropriate cipher suites/protocols, SNI/ALPN when needed |
| `KeyManager` / `KeyManagerFactory` | Provides **your own** certificates and private keys, when needed for a TLS server or mutual TLS |
| `TrustManager` / `TrustManagerFactory` | Makes trust decisions for the **peer's** certificates |
| `KeyStore` (`java.security`) | Stores keys/certificates or trusted certificate sets, depending on configuration |

For a typical **HTTPS client**, `HttpClient` uses the platform's default TLS/trust mechanism; the application does not need to call `SSLSocket` directly. JSSE matters when building a custom secure TCP protocol, requiring mTLS/custom truststores, or integrating TLS into an event loop.

Illustrative example of **TLS handshake only**, without sending HTTP (placed in a method with `throws Exception`, with network access to example.com:443):

~~~java
SSLContext context = SSLContext.getDefault();
try (SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket("example.com", 443)) {
    SSLParameters params = socket.getSSLParameters();
    params.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(params);
    socket.startHandshake();
}
~~~

Imports: `javax.net.ssl.SSLContext`, `SSLSocket`, `SSLParameters`. Set `HTTPS` endpoint identification **before the handshake** to verify the hostname against the certificate. With raw `SSLSocket`/`SSLEngine`, never assume the application already has proper hostname verification; you must configure/verify it actively. A proper chain-of-trust is also required. Skipping certificate checks, writing a "trust-all" trust manager, or disabling hostname verification just to "make it work" creates MITM vulnerabilities.

High-level TLS steps: establish TCP connection → negotiate version/cipher and receive certificate → authenticate peer and complete handshake → transmit protected application data. With `SSLEngine`, `NEED_WRAP`, `NEED_UNWRAP`, `NEED_TASK` states and buffer sizes must be coordinated properly; using `SSLEngine` does not automatically turn a channel into HTTPS.

### Two Security Questions That Must Be Separated

- **Truststore:** "Which CAs/certificates do I trust to authenticate the peer?"
- **Keystore/identity:** "Which certificate/private key do I present to prove my own identity?" (TLS servers usually need this; clients only need it when mTLS requires it).

You also need **hostname verification** (does the service being called match the certified name?), certificate expiration checks, and TLS restrictions per JDK policy. TLS encrypts the transport channel, but it does not replace authentication/authorization at the HTTP or application level.

## 7. `jdk.httpserver`: The JDK's Lightweight HTTP Server

The `jdk.httpserver` module exports the `com.sun.net.httpserver` package, featuring:

- `HttpServer`: creates an HTTP listener, registers path contexts, and starts/stops.
- `HttpHandler`: processes an `HttpExchange` for a request.
- `HttpExchange`: reads method/URI/request headers/body; sets response headers, status, length, and writes the response body.
- `HttpsServer` + `HttpsConfigurator`: turns the listener into HTTPS when configured with a proper `SSLContext` and certificate.
- `jwebserver`/`SimpleFileServer` (modern JDKs): convenient for serving static resources during development and testing.

`HttpServer` is useful for demos, mocks, callbacks, or small HTTP endpoints in controlled environments. It is **not a full web framework**: it lacks built-in utilities for validation, dependency injection, observability, reverse proxying, security middleware, etc. When building public production APIs, you must explicitly design authentication, payload limits, timeouts, threads/executors, logging, abuse protection, and TLS/proxy deployment; dedicated frameworks/servers are usually more suitable.

`HttpServer.create(address, backlog)` binds the socket; `createContext(path, handler)` registers a handler; `start()` enables receiving requests; `stop(delaySeconds)` stops the server. The handler must close the response stream/exchange so resources are released. For fixed-length responses, `sendResponseHeaders(status, byteLength)` requires the **actual UTF-8 byte count**, not `String.length()`; write the exact number of bytes declared.

## 8. Runnable Example: Java HTTP Server and HTTP Client in One Process

This example uses two API groups: `com.sun.net.httpserver.HttpServer` to **receive** HTTP requests and `java.net.http.HttpClient` to **send** HTTP requests. Both communicate over `127.0.0.1`; port `0` asks the OS to pick an available port, avoiding fixed-port conflicts. This is plain HTTP over loopback to illustrate the API map, **without TLS**.

Create a file named **`NetworkApiMapDemo.java`** with the following content:

~~~java
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class NetworkApiMapDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/hello", exchange -> {
            byte[] payload = "Hello from JDK HTTP Server"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, payload.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(payload);
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();
            URI uri = URI.create(
                    "http://127.0.0.1:" + port + "/hello");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

            System.out.println("HTTP " + response.statusCode());
            System.out.println(response.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run from the directory containing the file using JDK 17+:

~~~bash
javac --add-modules jdk.httpserver NetworkApiMapDemo.java
java --add-modules jdk.httpserver NetworkApiMapDemo
~~~

**Expected stdout when the environment allows loopback binding:**

~~~text
HTTP 200
Hello from JDK HTTP Server
~~~

Step-by-step explanation:

1. `HttpServer.create(..., 0)` creates a server listening on `127.0.0.1` using an OS-assigned ephemeral port.
2. `createContext("/hello", ...)` registers the handler; the server returns the `Content-Type` header and status `200`.
3. `payload.length` is the UTF-8 **byte** length; `try` closes the response stream after writing that exact number of bytes.
4. `server.start()` allows the server to accept connections. `getAddress().getPort()` passes the bound port to the client.
5. `HttpClient` builds an HTTP GET request, sends it synchronously, receives the body as a `String`, and prints the status/body.
6. `finally` ensures the listener is stopped even if sending the request or reading the response throws an exception.

**Remember:** this example does not need to create `Socket`, `SocketChannel`, or `SSLSocket` manually, because the HTTP client/server abstract away the transport layer. When switching to `https://`, you cannot simply change the scheme for `HttpServer`: you must use `HttpsServer`, configure certificates/`SSLContext`, and use an HTTPS URI.

## 9. Choosing an API by Real-World Scenario

| Scenario | Start with API | Reason |
| --- | --- | --- |
| Java service calling REST/JSON over HTTPS endpoints | `java.net.http.HttpClient` | Built-in methods, headers, status, body, TLS, HTTP versions, and async |
| Local mock webhook/callback server or HTTP demo | `jdk.httpserver.HttpServer` | Spin up a small endpoint without a framework |
| TCP client/server for a custom binary protocol, few connections | `java.net.Socket`/`ServerSocket` | Simple blocking streams, easy to add framing |
| Custom UDP telemetry/game protocol | `DatagramSocket` or `DatagramChannel` | Send/receive datagrams, accepting UDP semantics |
| Single event loop managing many TCP connections and buffers | `SocketChannel` + `Selector` | Multiplexed readiness, backpressure control |
| Custom TCP protocol requiring encryption and authentication | `SSLSocket` or `SSLEngine` + socket/channel | JSSE protects the byte stream; does not define the protocol itself |
| HTTP server with heavy production requirements | Framework/server designed for that environment | `jdk.httpserver` only provides a minimal server API |

**A sensible decision process:**

1. Identify the **application protocol**: HTTP, WebSocket, or custom binary frames?
2. Identify the **role**: outbound client, inbound server, or both?
3. Choose the **transport**: TCP or UDP? Are ordering, reliability, or message boundaries required?
4. Choose the **I/O model**: blocking, non-blocking event loop, or asynchronous completion; weigh complexity and connection count.
5. Decide **security**: TLS/mTLS, hostname validation, truststore, key material; `https` already includes TLS at the HTTP client layer.
6. Design **protocol framing, timeouts, size limits, retries/idempotency, resource closing, and error observability** before scaling.

There is no rule saying "NIO is always better than sockets" or "HTTPS requires coding `SSLSocket` yourself." Choose the highest level of abstraction that accurately expresses your problem's protocol.

## 10. Common Mistakes and Self-Checks

| Misconception/Mistake | Consequence | Correct Approach |
| --- | --- | --- |
| Using `Socket` and manually concatenating `GET / HTTP/1.1` for REST APIs | Must handle HTTP framing, redirects, content length, proxies, TLS, etc. yourself | Use `HttpClient` |
| Assuming `Socket.read()` receives a whole request | Messages get truncated, split, or coalesced | Define framing and loop until enough data is read |
| Calling `write(ByteBuffer)` once and ignoring remaining bytes | Lost bytes at the application layer in non-blocking mode | Check `buffer.hasRemaining()` and keep sending |
| Leaving `register(OP_WRITE)` enabled when there is no data to send | Event loop can spin hot, wasting CPU | Enable `OP_WRITE` only when output is pending |
| Thinking `java.net.http` contains an HTTP server | Picking the wrong module/API | `HttpClient` is in `java.net.http`, `HttpServer` is in `jdk.httpserver` |
| Thinking `SSLSocket` always verifies hostnames like an HTTPS client | May accept a peer with the wrong hostname | Set the endpoint identification algorithm and verify the certificate chain |
| Using a trust manager that accepts all certificates | Vulnerable to MITM attacks | Configure a valid truststore; do not disable verification |
| Treating HTTP 404/500 as socket errors that automatically throw exceptions | Business status codes go unhandled | Read `HttpResponse.statusCode()` |
| Configuring only the connect timeout | Can hang while reading the response/application data | Add appropriate request/read deadlines and cancellation |
| Binding a demo server to all interfaces instead of loopback | Accidentally exposing the endpoint to the network | Use `127.0.0.1` for local demos |
| Forgetting to close streams/sockets/exchanges | Descriptor/connection leaks | Use `try-with-resources`, `finally`, and stop the listener |
| Confusing `String.length()` with byte count when sending UTF-8 HTTP responses | Wrong `Content-Length`, truncated responses | Create a `byte[]` and use `bytes.length` |

When diagnosing failures, separate the layers:

- **DNS/address:** `UnknownHostException`, wrong host/port, firewall.
- **TCP/UDP:** `ConnectException`, timeouts, EOF, peer closed connection, UDP packet loss.
- **TLS:** `SSLHandshakeException`, untrusted CA, wrong hostname, incompatible protocol/cipher.
- **HTTP:** status, redirects, body, media type, headers, timeouts; 4xx/5xx is distinct from failing to connect.
- **I/O loop:** partial read/write, buffer state, selector keys, and uncleaned timeouts/cancellations.

## 11. Self-Check Exercises with Answers

**Exercise 1.** An application needs to call `POST https://api.example.com/orders` with JSON. Should you start with `SocketChannel`?

**Answer:** Usually no. Use `HttpClient` + `HttpRequest.BodyPublishers.ofString(json, UTF_8)`, add `Content-Type: application/json`, configure timeouts, and check the status/body. Low-level channels are only needed when there are special protocol constraints that an HTTP client cannot satisfy.

**Exercise 2.** A TCP server reads 3 bytes in one call while the declared frame is 100 bytes. Does that prove the sender only sent 3 bytes?

**Answer:** No. TCP is a byte stream; the application needs a loop to read all 100 bytes (or detect EOF/timeout), enforce size limits, and reassemble the reads.

**Exercise 3.** Do `SocketChannel` and `Selector` automatically encrypt data?

**Answer:** No. They are I/O mechanisms. If you need TLS for a custom protocol, you must integrate JSSE (typically `SSLEngine` for an event loop), or choose an abstraction that already supports TLS.

**Exercise 4.** Does an `HttpClient` calling `https://` necessarily need to be passed an `SSLSocket` manually?

**Answer:** No. The HTTP client integrates TLS via the implementation/JDK; only customize `SSLContext`/TLS settings when there is a clear requirement (mTLS, internal CA, certificate policies).

**Exercise 5.** If you want to write a local HTTP endpoint for testing, which package has `HttpServer`? Is it in `java.net.http`?

**Answer:** `com.sun.net.httpserver.HttpServer` belongs to the `jdk.httpserver` module, **not** `java.net.http`. You can compile/run with `--add-modules jdk.httpserver`.

## 12. Standard Reference Documentation

- `java.net` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/package-summary.html
- `java.nio.channels` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/channels/package-summary.html
- `java.net.http` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/module-summary.html
- `HttpClient` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- Java Secure Socket Extension (JSSE) Reference Guide: https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html
- `jdk.httpserver` module (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/module-summary.html
- `HttpExchange.sendResponseHeaders` (JDK 21 API): https://docs.oracle.com/en/java/javase/21/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html

**Connecting the dots:** from business requirements, identify whether it is HTTP or a custom protocol; from the protocol, determine client/server and TCP/UDP; from load characteristics, choose blocking/NIO; from security requirements, decide on TLS/JSSE. This is the map for choosing the right entry point in the Java Networking API.
