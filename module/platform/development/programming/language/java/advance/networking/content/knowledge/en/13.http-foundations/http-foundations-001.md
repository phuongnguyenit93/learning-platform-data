# HTTP Adds a Request–Response Model on Top of Transport

HTTP (Hypertext Transfer Protocol) is an **application-layer protocol** that provides **request–response semantics** for a client to interact with resources provided by a server. The transport mechanism handles carrying data between endpoints; HTTP supplies answers to questions that the transport **does not define on its own**: *what is this request asking to do, which resource does it target, what type is the body, how did the server handle it, and can it be cached or retried?*

A TCP socket provides a reliable, ordered byte stream within a connection; it **does not know** what `GET`, `POST`, the path `/products/42`, the `Content-Type` header, or the `404` code are. HTTP defines the **message structure and meaning** of those parts. When using HTTP/1.1, messages are represented as a start line, headers, and a body over a byte-stream connection. HTTP/2 uses binary frames and logical streams over TCP; HTTP/3 carries HTTP semantics over **QUIC** (based on UDP, yet providing reliable per-stream data delivery and built-in security).

**Key takeaway:** *HTTP does not replace the transport; it uses the capabilities of the transport/connection session to carry messages with application semantics.* Conversely, having a working transport alone **is not enough** to know whether a request is valid, authorized, or successfully executed.

This lesson belongs to the **HTTP Foundations** topic of the **Java Advance - networking** module. The focus is on the request–response model, layering, format and semantics across HTTP versions, practical Java 17+ examples, and foundational mistakes to avoid.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **byte stream/transport** from **HTTP request, response, headers, body, and semantics**.
2. Trace a round trip from client creating a request → transport carrying data → server receiving/parsing/processing → creating a response → client checking status and body.
3. Read HTTP/1.1 messages: request line, header fields, blank separator line, body, status line; state the meaning of `Host`, `Content-Length`, and `Connection`.
4. Explain methods, target resources, status codes, representations, media types, cache metadata, and **safe/idempotent** properties.
5. Distinguish **stateless** HTTP from **persistent** TCP/TLS connections, cookies/sessions, and authentication.
6. Understand why HTTP/1.1, HTTP/2, and HTTP/3 **preserve the same application semantics** while differing in framing and transport.
7. Explain HTTPS/TLS, proxies, reverse proxies, gateways, and errors that occur at each layer.
8. Write a small HTTP client/server in Java 17; try sending HTTP/1.1 directly over a `Socket` to see which parts are implemented by the application.
9. Apply timeouts, body length/framing, resource limits, retry/caching, and error handling at the appropriate layer.

## 2. Layer Diagram: What Does Transport Provide and What Does HTTP Add?

~~~text
CLIENT APPLICATION                 SERVER APPLICATION
"Read resource /demo"              "Handle /demo"
       |                                   ^
       v                                   |
+-------------------+            +----------------------+
| HTTP semantics    |            | HTTP semantics       |
| GET /demo         |            | route, method, status|
| Host, Accept      |            | headers, response    |
+---------+---------+            +----------+-----------+
          |                                   ^
          v                                   |
+-------------------+            +----------------------+
| HTTP message      |            | HTTP parser/framer    |
| encoding/framing  |            | and response encoder  |
| HTTP/1.1, h2, h3  |            +----------+-----------+
+---------+---------+                       ^
          |                                 |
          v                                 |
+-------------------+            +----------------------+
| Transport/session | ---------->| Transport/session    |
| TCP, TLS/TCP      |   network  | TCP, TLS/TCP         |
| or QUIC over UDP  |            | or QUIC over UDP     |
+-------------------+            +----------------------+
~~~

**Distinction of responsibilities:**

| Layer / Concept | Solves | Does Not Solve by Itself |
| --- | --- | --- |
| IP/routing | Delivers packets between networks and endpoints | Does not understand HTTP method/status |
| TCP | Connection, ordered byte stream, retransmission, flow/congestion control | Does not define the boundary of an HTTP message or business semantics |
| TLS (commonly paired with HTTPS over TCP) | Protects confidentiality/integrity, authenticates the server via certificates, and other TLS capabilities | Does not understand `GET`/`POST` requests or satisfy application authorization |
| QUIC | Modern transport over UDP: multiplexed streams, per-stream reliability, connection security | Does not determine the meaning of URI/method/status |
| HTTP semantics | Resource, method, status, headers, representation, caching, and intermediary behavior | Does not guarantee a clear network route or that a business transaction is committed |
| Application | Checks permissions, data, transactions, domain rules, idempotency keys when needed | Should not treat a TCP ACK as a business confirmation |

Example: the client calls `Socket.write("GET /x ...")` to send bytes into TCP. If the other side does not have an **HTTP parser**, this string is just ASCII data; the server might interpret it as a command of an arbitrary protocol or understand nothing at all. Conversely, two programs using a proper HTTP library can communicate without the application having to manually count CRLF bytes or parse TCP segments.

### HTTP Communication Is Not 1 Request = 1 TCP Packet

- TCP can **split** one HTTP request into multiple chunks or **coalesce** multiple writes into network segments.
- A single `InputStream.read()` call may receive part of the headers, part of the body, or more bytes than expected for one message.
- One TCP connection can carry **multiple HTTP request–response exchanges** depending on the HTTP version and how the connection is used.
- HTTP/2 and HTTP/3 have **multiple logical streams** concurrently over the same transport connection. You must never assume the number of sockets always equals the number of HTTP requests.

**Invariant:** the application must determine **message boundaries** according to the HTTP version/framing, not by the number of `read()` calls or the number of network packets.

## 3. How Does the Request–Response Model Work?

A basic exchange:

~~~text
Client                                                Server
  |                                                     |
  | (1) GET /items/42 HTTP/1.1                          |
  |     Host: shop.example                              |
  |     Accept: application/json                        |
  |---------------------------------------------------->|
  |                    (2) receive and parse message    |
  |                    (3) route, auth, read resource   |
  |                                                     |
  | (4) HTTP/1.1 200 OK                                 |
  |     Content-Type: application/json                  |
  |     Content-Length: ...                             |
  |     {"id":42,"name":"Pen"}                          |
  |<----------------------------------------------------|
  |                                                     |
  | (5) client inspects status, headers, body           |
  |                                                     |
~~~

`shop.example` and `/items/42` are illustrative examples only, not real endpoints tested.

**Request** describes *what the client wants the server to do*, consisting of:

- **Method**: `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, `DELETE`, etc.
- **Target URI/resource**: the resource to access, e.g., `https://shop.example/items/42`.
- **Header fields**: metadata and control information such as `Host`, `Accept`, `Content-Type`, `Authorization`, `If-None-Match`.
- **Content/body**: optional; its meaning depends on the method and the media type/application protocol.

**Response** describes *the result of the server processing the request*, consisting of:

- **Status code**: such as `200` success, `201` created, `404` resource does not exist/not found, `500` server error.
- **Response header fields**: `Content-Type`, `Cache-Control`, `ETag`, `Location`, and other metadata.
- **Response content**: HTML, JSON, images, files, or other content; some responses have no body by semantics.

A request can receive an **interim 1xx response** (such as `100 Continue`) before the final response. Therefore, the "one request → one response" model is a **request–response transaction** model; at the wire level, interim messages may precede the final response.

**Do not equate a response with a domain outcome:** HTTP 200 means the server returned a response indicating success of the request at the HTTP level, but it does not prove that all subsequent downstream events have completed (e.g., sending an email asynchronously). HTTP 202 Accepted may indicate the request was accepted for further processing, not that the work has finished.

## 4. HTTP/1.1 over TCP: Visible Message Structure

When making a plain `http://` TCP connection to an HTTP/1.1 server, the beginning of the message is typically readable as text. A simple request:

~~~http
GET /hello?lang=vi HTTP/1.1
Host: example.test
Accept: text/plain
Connection: close

~~~

This is a **line-based representation**. In practice, each header/request line ends with **CRLF** (`\r\n`), and after the last header there is a **blank CRLF line**. Do not assume that the terminal newline on every OS is equivalent to HTTP/1.1 CRLF.

Illustrative response:

~~~http
HTTP/1.1 200 OK
Content-Type: text/plain; charset=UTF-8
Content-Length: 5
Connection: close

Hello
~~~

`Content-Length: 5` because the ASCII string `Hello` is 5 **bytes** long. With accented Vietnamese text, the UTF-8 length in bytes can **differ** from Java's `String.length()` character count. If a server writes HTTP/1.1 manually, it must calculate the exact **number of bytes sent**, not the number of code points or displayed characters.

### 4.1. Request Line and Resource Target

In HTTP/1.1, the request line typically has the form:

~~~text
METHOD SP request-target SP HTTP-version CRLF

GET /hello?lang=vi HTTP/1.1
~~~

- `GET` is the method defining the semantics of the action.
- `/hello?lang=vi` is the request target in **origin-form**, common when a client sends directly to an origin server.
- `HTTP/1.1` describes the version used for this exchange representation.
- `Host` in HTTP/1.1 is a required header for ordinary requests, helping the server identify the authority/virtual host. Do not choose the target resource solely from the local TCP port.

A full URI `https://example.test/hello?lang=vi` contains scheme, authority, path, and query; a fragment `#section`, if present, is handled locally by the client and is **not** sent as part of a normal HTTP request-target.

In HTTP/2 and HTTP/3, there is no text request line like this on the wire; equivalent semantics are encoded in pseudo-header fields such as `:method`, `:scheme`, `:authority`, `:path` (depending on the case).

### 4.2. Status Line and Status Code

In HTTP/1.1, a response begins with:

~~~text
HTTP/1.1 SP status-code SP reason-phrase CRLF

HTTP/1.1 404 Not Found
~~~

The reason phrase is optional descriptive text primarily for human readers in HTTP/1.1; client logic should rely on the **status code** rather than exact string matching against `"Not Found"`. HTTP/2 and HTTP/3 carry the status code via `:status` instead of a text status line.

### 4.3. Headers, Blank Line, and Body

Header fields further describe the request/response, for example:

~~~http
POST /messages HTTP/1.1
Host: example.test
Content-Type: application/json
Content-Length: 16

{"text":"hello"}
~~~

In this example, `{"text":"hello"}` is 16 ASCII bytes long, so `Content-Length` = 16. Headers are **not** the body; `Content-Type` describes the media type of the **representation content**. `Accept` on the request describes the response formats the client desires; it does not mean the `Content-Type` of the body the client sends.

HTTP header names are **case-insensitive** in semantics; however, you must not arbitrarily alter header contents/format when writing a parser. Use an HTTP library instead of parsing manually in production to avoid syntax and security bugs.

### 4.4. Message Framing: Where Does the Body End?

TCP only sees a byte stream, not HTTP message boundaries. In HTTP/1.1, the server/client must apply **message length determination rules** according to HTTP; common mechanisms include:

- **`Content-Length`**: specifies the length in **bytes** of the content when applicable under HTTP rules.
- **`Transfer-Encoding: chunked`**: splits content into chunks whose sizes are represented in hexadecimal, terminated by a zero-size chunk (and optional trailer fields). This is an HTTP/1.1 message framing mechanism, not JSON encoding or a form of compression.
- **Reading until connection close**: used only in cases where the response is defined as close-delimited; it is unsafe to treat this as a general rule, because persistent connections may remain open after a response.
- **Responses without a body by semantics**, such as responses to `HEAD`, `204 No Content`, and `304 Not Modified`, have their own rules; do not read a body just because an unfamiliar header is present.

Precedence and invalid cases must be handled strictly according to RFC 9112; if `Transfer-Encoding` and `Content-Length` conflict, differing proxy/parser behavior can lead to request smuggling. Do not write a manual HTTP/1.1 parser for production based solely on a few example lines in a lesson.

**Typical mistake:** the server sends a 12-byte body but declares `Content-Length: 20`; the client may wait for 8 more bytes or consider the response incomplete. Conversely, declaring too short a length causes the remaining bytes to be misinterpreted, especially when the connection is reused.

## 5. What Semantics Does HTTP Add on Top of Transport?

Transport can move data from A to B, but HTTP adds a **uniform interface** for resources, methods, metadata, status, and caching.

### 5.1. Resource, Representation, and URI

An HTTP resource is not "a file located at a path identical to the URL". It is a conceptual entity **identified by a URI** and mapped by the origin server to behavior or **representations**.

Examples:

- `GET /users/7` may return JSON containing user information.
- `GET /reports/monthly` may dynamically generate a PDF rather than reading a static file.
- `GET /images/logo` may return PNG/WebP depending on `Accept`, or an error if not permitted.
- `POST /jobs` may create an asynchronous job and return `202 Accepted`.

The **URI** identifies or locates the target; the **representation** is the concrete data that HTTP transfers along with its corresponding metadata. Do not equate a URI with a filesystem path, or JSON with the resource itself.

### 5.2. Methods Are Semantic Contracts, Not TCP Commands

| Method | Typical Meaning | Safe? | Idempotent? |
| --- | --- | --- | --- |
| `GET` | Retrieve the current representation of a resource | Yes | Yes |
| `HEAD` | Same as GET for metadata, but response has no body | Yes | Yes |
| `POST` | Ask the target resource to process content according to its specific semantics | Not by default | Not by default |
| `PUT` | Create/replace the state of the target resource with the sent representation | No | Yes |
| `DELETE` | Request removal of the target resource's association/functionality | No | Yes |
| `PATCH` | Apply partial modifications to a resource | No | Not by default |
| `OPTIONS` | Query communication capabilities/options | Yes | Yes |
| `TRACE` | Perform a message loop-back test as defined by HTTP (often disabled for security) | Yes by semantics | Yes |

**Safe** means the client does not *request* any state change on the resource; the server may still log, collect statistics, or have unintended side effects. GET should be designed not to cause business state changes even if users refresh or crawlers access it.

**Idempotent** means multiple identical requests have the **same intended effect on state** as executing once, not that the response is identical every time. For example, deleting a resource the first time may return 204, and the next time 404; that does not negate DELETE's idempotent semantics.

PUT and DELETE are defined as idempotent at the HTTP semantics level, but an application implementation with side effects (charging money each time, sending an email each time) can break that property; the API must uphold the contract. A creating POST often needs an `Idempotency-Key` or a separate deduplication mechanism if the client might retry without wanting to create duplicate transactions.

**Do not skip authorization based on the method name.** A GET request does not mean "everyone is allowed to read the data"; a POST request does not mean "the server definitely wrote to the database".

### 5.3. Status Codes: Outcomes at the HTTP Layer

| Group | Basic Meaning | Important Examples |
| --- | --- | --- |
| `1xx` | Informational, before final response | `100 Continue`, `101 Switching Protocols` |
| `2xx` | Request was received/understood/accepted with success semantics | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` |
| `3xx` | Redirect or client action needed on representation/URI | `301`, `302`, `304 Not Modified`, `307`, `308` |
| `4xx` | Client request has an issue, is unauthorized, or reflects a request-related error | `400`, `401`, `403`, `404`, `405`, `408`, `409`, `429` |
| `5xx` | Server cannot fulfill a valid request or encountered a server/downstream error | `500`, `502`, `503`, `504` |

A few easily confused distinctions:

- `401 Unauthorized` typically indicates **missing or invalid authentication credentials** (requiring an authentication scheme), whereas `403 Forbidden` means the server denies permission even though the principal may be known.
- `404 Not Found` says the resource was not found or the server does not wish to disclose its existence; it does not prove a DNS/TCP failure.
- `429 Too Many Requests` is commonly used for rate limiting; it may be paired with `Retry-After` per policy.
- `502 Bad Gateway` / `504 Gateway Timeout` typically originate from a gateway/proxy regarding an upstream; this differs from a client transport error failing to open a connection to the proxy.
- `304 Not Modified` is the result of a conditional request using cache, **not a new response body**.
- `204 No Content` indicates success with no content in the response.
- `201 Created` is commonly used after creating a resource and may include a `Location` header.
- `202 Accepted` does not by itself guarantee that asynchronous processing will ultimately succeed.

These are **HTTP semantic codes**, not TCP error codes from `Socket.connect()`. When a client receives HTTP 500, at least one HTTP server/gateway has replied; when DNS lookup fails, there is usually **no HTTP response** to read.

### 5.4. Headers Describing Representation, Conditions, and Caching

Some foundational headers worth learning:

| Header | Usually In | Role |
| --- | --- | --- |
| `Host` | HTTP/1.1 Request | Authority/virtual host |
| `Accept` | Request | Media types the client can accept for the response |
| `Content-Type` | Request/response with content | Media type/charset of the representation |
| `Content-Length` | Message needing length framing | Number of content bytes per version rules |
| `Authorization` | Request | Authentication credentials for server verification |
| `Cookie` / `Set-Cookie` | Request / response | Carries/sets application-layer state when using cookies |
| `Cache-Control` | Request/response | Caching directives, freshness, and policy |
| `ETag` | Response | Validator of the representation |
| `If-None-Match` | Request | Conditional request based on ETag |
| `Location` | Applicable response | Redirect target / newly created resource |
| `Accept-Encoding` / `Content-Encoding` | Request / response | Negotiating and indicating content coding |
| `Connection` | HTTP/1.1 | Connection-control metadata for the current hop, **not used this way in HTTP/2/3** |
| `Via` | Request/response through intermediary | Records proxy/gateway hops per standard |

Headers are **metadata**, not a license for the server to trust every value sent by the client. `Authorization` must be validated, `Content-Length` must be parsed accurately, and `Host` must be protected against host-header attacks when generating links/redirects. Hop-by-hop headers follow different rules from end-to-end fields; proxies must handle them properly when forwarding.

## 6. HTTP Is Stateless, Yet Has Sessions and Connection Reuse

HTTP is defined as a **stateless protocol in semantics**: the meaning of each request can be understood independently, without requiring prior request history to be kept on the transport connection.

**Stateless does not mean:**

- The server cannot store data in a database or maintain application state.
- A client cannot log in.
- Cookies/authorization tokens do not exist.
- Every HTTP request must open a new TCP connection.
- An HTTP server cannot handle multiple requests from the same user across a workflow.

Example of an app maintaining a session with a cookie:

~~~http
GET /account HTTP/1.1
Host: example.test
Cookie: session=opaque-token

~~~

The server reads the cookie, validates the token/session, and returns the corresponding account. **State** resides in the cookie/token/server-side session store or infrastructure, not because TCP itself remembers that "the client just logged in". If the client opens a new connection and sends valid credentials, the API can continue working.

Distinguish between:

- **HTTP request state**: method, URI, headers/body of the exchange.
- **Application session state**: cookie, token, database record, business transaction.
- **Transport connection state**: TCP/TLS/QUIC connection, flow control windows, retransmission, and peer endpoints.

These are three different lifecycles. One connection can carry many requests, multiple connections can serve the same session, and an HTTP request can finish while a server background job continues running.

## 7. Persistent Connections, Reuse, and Multiplexing

### 7.1. HTTP/1.1: Default Keep-Alive

HTTP/1.1 typically keeps a connection open to send multiple request–response exchanges, reducing TCP/TLS handshake overhead. The `Connection: close` header indicates that the sender intends to close the connection after completing the corresponding response; it is **not** the delimiter of a single message in all cases.

~~~text
TCP connection 1 (HTTP/1.1 persistent):
  Client -> request A
  Server -> response A
  Client -> request B
  Server -> response B
  ... (while permitted and connection is alive)

Multiple requests do not require multiple TCP connections.
~~~

HTTP/1.1 also has pipelining in the protocol specification, but modern applications/browsers generally do not rely on it due to complexity, response ordering, and head-of-line blocking. Do not equate "one request, one socket" with all of HTTP/1.1, and certainly not with HTTP/2 or HTTP/3.

When a connection is persistent, reading `InputStream.readAllBytes()` "until EOF" to get a response is **wrong** if the server keeps the connection open. The parser must read up to the **exact message boundary** per HTTP framing.

### 7.2. HTTP/2: Logical Streams Over One TCP Connection

HTTP/2 preserves semantics such as GET/POST, target, headers, and status, but replaces the HTTP/1.1 format with:

- **Binary frames**: such as `HEADERS`, `DATA`, `SETTINGS`, and `WINDOW_UPDATE`.
- **Streams**: multiple request–response exchanges multiplexed over a single TCP connection.
- **HPACK header compression** and stream/connection-level flow control management.
- **Pseudo-headers** such as `:method`, `:scheme`, `:authority`, `:path`, and `:status`.
- **No longer** has HTTP/1.1-style start lines and chunked transfer coding on the wire.

~~~text
TCP connection
  |
  +-- HTTP/2 Stream 1: GET /a -> 200, DATA...
  +-- HTTP/2 Stream 3: GET /b -> 200, DATA...
  +-- HTTP/2 Stream 5: POST /c -> 201, DATA...
  |
  Frames from multiple streams interleaved on the same TCP connection.
~~~

**Important limitation:** TCP is still a single ordered byte stream underneath. Losing one TCP segment can force data for multiple HTTP/2 streams to wait for retransmission (*transport-level head-of-line blocking*), even though HTTP/2 allows interleaving application frames.

### 7.3. HTTP/3: HTTP Semantics Over QUIC (UDP Does Not Mean Unreliable)

HTTP/3 per RFC 9114 uses **QUIC**, where QUIC runs over **UDP** but itself provides the mechanisms needed for **reliable, ordered per-stream** byte delivery, along with encryption/authentication, congestion control, stream multiplexing, and flow control.

~~~text
HTTP semantics: GET, POST, 200, Content-Type, Cache-Control
                    |
              HTTP/3 frames
                    |
            QUIC streams + TLS 1.3
                    |
                     UDP
                    |
                     IP
~~~

Compared to HTTP/2:

- HTTP/3 multiplexing happens via **QUIC streams**, rather than packing all HTTP/2 streams into a single TCP byte stream.
- Losing a QUIC packet belonging to stream A does not force already-received data of stream B to wait for A's bytes to be recovered in order **on a shared TCP stream**. QUIC still has shared congestion control and resource limits; performance is not completely independent.
- HTTP/3 uses **QPACK** for header compression (instead of HTTP/2's HPACK).
- Security is integrated via QUIC/TLS 1.3; do not view HTTP/3 as "unencrypted HTTP text sent over UDP".
- Method/status/URI/caching semantics remain based on common HTTP, though wire framing differs.

Do **not** call `DatagramSocket.send("GET / HTTP/1.1")` and assume you just made an HTTP/3 request. HTTP/3 requires a compliant **QUIC implementation**, handshake, streams, and HTTP/3 framing.

## 8. Comparison Table of the Three HTTP Versions

| Aspect | HTTP/1.1 | HTTP/2 | HTTP/3 |
| --- | --- | --- | --- |
| Request–response semantics | Yes | Preserves HTTP semantics | Preserves HTTP semantics |
| Common transport | TCP (often TLS for HTTPS) | TCP + TLS in common web deployments | QUIC over UDP, built-in security |
| Format | Start line + text headers + body | Binary frames | HTTP/3 frames over QUIC streams |
| Message demarcation | HTTP/1.1 framing (length/chunked/semantics) | Frame and stream state | QUIC stream + HTTP/3 frames |
| Multiplexing multiple requests | No h2-equivalent multiplexing layer | Yes, over one TCP connection | Yes, via QUIC streams |
| Header compression | No standard HPACK/QPACK | HPACK | QPACK |
| Head-of-line blocking | Yes at the HTTP/1.1 connection level depending on usage | TCP-level can block h2 streams | No same TCP-level HoL between QUIC streams |
| Status/method principles | `GET`/`200`/... | Same HTTP semantics | Same HTTP semantics |
| Java 17 `java.net.http.HttpClient` | Supported | Supports HTTP/2 via API and negotiation | **Does not support HTTP/3 in standard Java 17 API** |

**Be careful when reading output:** `HttpClient.Version.HTTP_2` is an **HTTP version preference**; when connecting to a server that does not support it, Java's HttpClient may fall back to HTTP/1.1. Read `HttpResponse.version()` to know the actual version used. Java 17 `HttpClient` has no `HTTP_3` enum, so this lesson's demo **forces HTTP/1.1** to clearly illustrate format and semantics.

## 9. Where Does HTTPS Add TLS? Does HTTP Replace TCP/QUIC?

Common URI schemes:

- `http://example.test/path`: plain HTTP over the configured transport (on the web, HTTP/1.1 over TCP); **does not** provide TLS encryption under this scheme.
- `https://example.test/path`: HTTP over a secured connection; commonly HTTP/1.1 or HTTP/2 over TLS/TCP, or HTTP/3 over QUIC with built-in security.

For HTTPS over TCP:

~~~text
HTTP request/response
       |
       v
HTTP encoding/framing
       |
       v
TLS records (encryption, integrity, server authentication)
       |
       v
TCP byte stream
       |
       v
IP packets
~~~

Typical sequence: DNS → TCP connection → TLS handshake (ALPN may negotiate `http/1.1` or `h2`) → HTTP request/response → connection reuse or close.

HTTP/3 over QUIC does not stack a separate TLS record layer like TLS/TCP; QUIC uses TLS 1.3 for key establishment/security but integrates it differently into the transport. Do **not** describe HTTP/3 as `TLS/TCP` or "running over raw UDP".

**HTTPS secures the transport channel, not business authentication/authorization.** Even with TLS, you still must check whether the user has permission to read `/users/7`, avoid leaking API keys, and never trust client input.

## 10. Java 17+ — Full Demo: Loopback HTTP Server and HttpClient

This example uses the **built-in lightweight HTTP server in the `jdk.httpserver` module** and the **standard HTTP client `java.net.http.HttpClient`**.

Goals:

- The server exposes resource `/demo`; GET returns a message, POST reads the request body and returns an echo message.
- The client builds an `HttpRequest` containing method, URI, body, and timeout.
- `HttpClient` handles transport, HTTP serialization/parsing, and message framing; the application focuses solely on **HTTP semantics**.
- Print status code, body, and HTTP version. The server binds to loopback on port `0`, so no external port is needed.

**File `HttpRequestResponseDemo.java`:**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpRequestResponseDemo {
    private static void handle(HttpExchange exchange) throws java.io.IOException {
        try (exchange) {
            String method = exchange.getRequestMethod();
            String result;
            if (method.equals("GET")) {
                result = "Hello from HTTP";
            } else if (method.equals("POST")) {
                byte[] input = exchange.getRequestBody().readAllBytes();
                result = "Echo: " + new String(input, StandardCharsets.UTF_8);
            } else {
                exchange.getResponseHeaders().set("Allow", "GET, POST");
                exchange.sendResponseHeaders(405, -1);
                return;
            }
            byte[] bytes = result.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getLoopbackAddress(), 0), 0);
        server.createContext("/demo", HttpRequestResponseDemo::handle);
        server.start();
        try {
            URI endpoint = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort() + "/demo");
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest get = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> first = client.send(
                    get, HttpResponse.BodyHandlers.ofString());
            System.out.println("GET: " + first.statusCode() +
                    " | " + first.body());

            HttpRequest post = HttpRequest.newBuilder(endpoint)
                    .timeout(Duration.ofSeconds(5))
                    .POST(HttpRequest.BodyPublishers.ofString("ping"))
                    .build();
            HttpResponse<String> second = client.send(
                    post, HttpResponse.BodyHandlers.ofString());
            System.out.println("POST: " + second.statusCode() +
                    " | " + second.body());
            System.out.println("Version: " + second.version());
        } finally {
            server.stop(0);
        }
    }
}
~~~

**Compile/run commands with JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HttpRequestResponseDemo.java
java --add-modules jdk.httpserver HttpRequestResponseDemo
~~~

**Stdout compiled and run in practice with OpenJDK 24, using `--release 17` to verify Java 17 API:**

~~~text
GET: 200 | Hello from HTTP
POST: 200 | Echo: ping
Version: HTTP_1_1
~~~

### 10.1. Which HTTP Layer Does Each Part Represent?

1. `HttpServer.create(new InetSocketAddress(..., 0), 0)` creates a server on an OS-assigned loopback port. This is the **transport endpoint**.
2. `server.createContext("/demo", ...)` associates an **HTTP resource path** with an application handler. TCP has no built-in concept of "context /demo".
3. `exchange.getRequestMethod()` reads the **HTTP method**, not a `Socket` flag.
4. `exchange.getRequestBody()` reads bytes of the **HTTP request body** already decoded/framed by the HTTP implementation. In a real application you must **limit the body size**; the demo uses `readAllBytes()` only because the small payload is sent by the program itself.
5. `getResponseHeaders().set("Content-Type", ...)` describes the media type of the representation.
6. `sendResponseHeaders(200, bytes.length)` produces the **HTTP status/headers + response framing**; the body is written to the output stream. `bytes.length` is the exact number of UTF-8 encoded bytes.
7. `HttpRequest.newBuilder(endpoint).GET()` and `POST(BodyPublishers.ofString("ping"))` express the client's **intent**; the library sends the request with valid HTTP syntax.
8. `HttpResponse.statusCode()` and `body()` provide results at the HTTP layer without requiring the application to manually parse raw CRLF.
9. `second.version()` reports the actual protocol used, which is `HTTP_1_1` because the demo sets HTTP/1.1 preference.
10. `server.stop(0)` shuts down the HTTP server at the end. Java `HttpClient` in **Java 17 does not implement `AutoCloseable`**, so the demo does not use `try (HttpClient client=...)`; that is an important API difference when targeting JDK 17.

**Demo scope:** `com.sun.net.httpserver.HttpServer` is a minimal embedded server for learning/testing purposes, **not** a default production solution for the public Internet or APIs requiring high security/observability. The code intentionally omits authentication, request body limits, concurrency tuning, TLS, or logging. If running on a machine where default loopback prefers IPv6 so the hardcoded `127.0.0.1` URI does not match the bound server interface, use the explicitly bound IPv4 loopback address or construct a properly formatted IPv6 URI; do not open the listener to the entire network just to avoid a test error.

## 11. Java 17+ — Full Demo: Reading HTTP/1.1 Directly Over a TCP Socket

The previous example used an HTTP library, so the HTTP message bytes were hidden. This example intentionally uses **plain `ServerSocket` and `Socket`**, manually reading the request headers and writing an HTTP/1.1 response. It **only supports a single GET without a body**, has no TLS, no persistent connection, and is **not a complete HTTP parser**.

It demonstrates: **TCP only transfers bytes; the application must actively apply HTTP structure/semantics for the receiver to understand the request/response.**

**File `RawHttpOverTcpDemo.java`:**

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class RawHttpOverTcpDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try (ServerSocket server = new ServerSocket(
                0, 8, InetAddress.getLoopbackAddress())) {
            server.setSoTimeout(5000);
            Future<String> observed = worker.submit(() -> {
                try (Socket accepted = server.accept()) {
                    accepted.setSoTimeout(5000);
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(
                                    accepted.getInputStream(),
                                    StandardCharsets.US_ASCII));
                    String startLine = reader.readLine();
                    String header;
                    while ((header = reader.readLine()) != null && !header.isEmpty()) {
                        // Consume the rest of the HTTP/1.1 header section.
                    }
                    if (header == null || startLine == null) {
                        throw new IllegalStateException("Incomplete request");
                    }
                    byte[] reply = (
                            "HTTP/1.1 200 OK\r\n" +
                            "Content-Type: text/plain\r\n" +
                            "Content-Length: 4\r\n" +
                            "Connection: close\r\n\r\n" +
                            "PONG").getBytes(StandardCharsets.US_ASCII);
                    accepted.getOutputStream().write(reply);
                    accepted.getOutputStream().flush();
                    return startLine;
                }
            });

            try (Socket client = new Socket(
                    InetAddress.getLoopbackAddress(), server.getLocalPort())) {
                client.setSoTimeout(5000);
                byte[] request = (
                        "GET /ping HTTP/1.1\r\n" +
                        "Host: localhost\r\n" +
                        "Connection: close\r\n\r\n")
                        .getBytes(StandardCharsets.US_ASCII);
                client.getOutputStream().write(request);
                client.getOutputStream().flush();
                String response = new String(
                        client.getInputStream().readAllBytes(),
                        StandardCharsets.US_ASCII);
                System.out.println("Response status: " +
                        response.substring(0, response.indexOf("\r\n")));
                System.out.println("Response body: " +
                        response.substring(response.indexOf("\r\n\r\n") + 4));
            }
            System.out.println("Server request: " +
                    observed.get(5, TimeUnit.SECONDS));
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

**Compile/run commands:**

~~~bash
javac --release 17 -encoding UTF-8 RawHttpOverTcpDemo.java
java RawHttpOverTcpDemo
~~~

**Stdout compiled/run successfully:**

~~~text
Response status: HTTP/1.1 200 OK
Response body: PONG
Server request: GET /ping HTTP/1.1
~~~

### 11.1. Why Do Both Server and Client Need Extra HTTP Code?

- The TCP server accepts a connection via `accept()`, but **does not automatically return `200 OK`**. The worker writes the literal bytes of the status line and HTTP headers.
- The client sends bytes for the method, request target, version, `Host`, and `Connection`. Sending just `PING` over TCP is **not** a valid HTTP/1.1 request.
- The worker reads the request start-line and loops through headers until the blank line to find where the body would begin; the demo code **does not read a request body**, because the demo GET sends no body.
- The response sends `Content-Length: 4` because the body `PONG` is four ASCII bytes; `Connection: close` lets the client's `readAllBytes()` reach EOF and finish after the response.
- The client manually searches for `\r\n` and `\r\n\r\n` to print. This is **only a way to verify the example's format**, not sufficient to parse an arbitrary HTTP/1.1 response (chunking, interim responses, encoding, malformed input, header limits, pipelining...).
- With a persistent connection, `readAllBytes()` can block indefinitely; proper framing must be used. Do not copy `substring(...)` parsing to build a production HTTP client.

**Why is the raw example only for learning?** It omits full routing, target validation, header/body limits, chunked encoding, `Expect: 100-continue`, keep-alive, HTTP method semantics, and request smuggling defenses. In production, use `HttpClient`, an HTTP server framework, or a battle-tested implementation instead of rolling your own parser.

## 12. Distinguishing Transport, TLS, HTTP, and Business Errors

A request can fail at multiple layers; how you retry and inform the user depends on where the error occurred.

~~~text
Client starts calling https://api.example.test/orders/1
    |
    +-- DNS lookup fails
    |     -> TCP/QUIC not opened; no HTTP status yet
    |
    +-- TCP connect timeout / connection refused
    |     -> transport incomplete; no HTTP response yet
    |
    +-- TLS certificate invalid / handshake fail
    |     -> secure session failed; no final HTTP status yet
    |
    +-- HTTP server returns 401/403/404/500/503
    |     -> HTTP response received at application layer
    |
    +-- HTTP 200 but business error JSON (if API is designed that way)
          -> must check API contract, do not infer from TCP/TLS success
~~~

**Verification rules:**

- `ConnectException`, `UnknownHostException`, `SSLHandshakeException`, `HttpTimeoutException` are errors **not equivalent to status codes**.
- `HttpClient.send(...)` normally **returns an `HttpResponse` for 4xx/5xx statuses**; Java's HttpClient does not throw an exception just because the server returned HTTP 404 or 500. The application should check `response.statusCode()`.
- A `503 Service Unavailable` response is an HTTP signal; retrying may be reasonable with delay/backoff or `Retry-After`, but you must consider whether repeating the request is safe.
- A connection dropped **after the client sends a POST** creates uncertainty as to whether the server finished processing the business action. Automatic retry can **create duplicate orders**; use an idempotency key or check the outcome by resource id if the design requires it.
- TLS certificate failures should not be "fixed" by temporarily disabling TLS verification in production.

### 12.1. Timeouts at Which Layer?

| Timeout | Meaning | Java Example |
| --- | --- | --- |
| DNS resolution | Time to resolve hostname | Usually depends on resolver/OS; not the same as connectTimeout |
| TCP connect | Waiting to establish connection | `HttpClient.Builder.connectTimeout(Duration)` |
| Overall HTTP request | Waiting for request–response to complete per API contract | `HttpRequest.Builder.timeout(Duration)` |
| Read idle / application | No qualifying bytes within limit | May require separate timeout policy per server/client library |
| Proxy/gateway | Waiting for upstream | May surface as `504 Gateway Timeout` |
| Business deadline | Limit for processing an order/task | Requires separate app design and cancellation |

A timeout **does not** prove the server did not execute side effects. Even less can HTTP 200 or a TCP ACK be used as proof that an asynchronous business operation has committed.

## 13. Caching and Conditional Requests Are Also Capabilities HTTP Adds

Transport usually does not know whether "this response is stale" or "previously stored data can be reused". HTTP has headers and semantics for caching.

Illustrative idea:

~~~http
GET /articles/10 HTTP/1.1
Host: example.test
If-None-Match: "v7"

~~~

If the representation has not changed according to the validator, the server may return:

~~~http
HTTP/1.1 304 Not Modified
ETag: "v7"
Cache-Control: max-age=120

~~~

The client/cache uses the stored representation according to HTTP caching conditions; **304 has no new body**. This is something TCP cannot infer on its own.

Terminology:

- **Freshness**: a response can be reused according to cache policy (e.g., `max-age`).
- **Validation**: checking whether a stored copy is still valid via `ETag`/`If-None-Match` or `Last-Modified`/`If-Modified-Since`.
- **Private vs shared cache**: personal data needs appropriate `private` or `no-store` policies to prevent public proxies from caching sensitive information.
- **Vary**: cache key is affected by specified request headers.
- **Unsafe methods** can make cached representations stale or require invalidation.

Proper caching reduces request/response size and latency, but a wrong cache policy can leak private content. Do not assume "GET is always cached" or "with TLS nothing can be cached": consult HTTP caching semantics and headers.

## 14. Proxies, Reverse Proxies, and Gateways Still Exchange HTTP Semantics

A request may pass through several components:

~~~text
Browser / Java HttpClient
        |
        v
Forward proxy (if configured)
        |
        v
Reverse proxy / load balancer / gateway
        |
        +------ HTTP/1.1 to backend A
        |
        +------ HTTP/2 to backend B
        |
        v
Origin application
~~~

- **Forward proxy** acts on behalf of the client toward servers; used for policy, routing, or caching.
- **Reverse proxy** fronts the server system, receiving requests at the edge and forwarding them to backends; it can terminate TLS, load balance, and apply auth/rate limiting.
- **Gateway** can translate between protocols or between HTTP versions.
- **Origin server** holds ultimate responsibility for resource semantics (even if a response may be cached or generated by an intermediary).

HTTP enables intermediaries to understand method, target, headers, cache controls, and status to act at the application level. A TCP router does not automatically know whether a `/health` request is cacheable. However, one HTTP **hop** may use a different connection/version from the next hop. For example, the client uses HTTP/2 to the reverse proxy, and the proxy uses HTTP/1.1 to the backend. Do not infer the backend version solely from the client version.

**Hop-by-hop** headers such as `Connection` in HTTP/1.1 must be handled properly by proxies; do not forward them as end-to-end headers. Do not trust arbitrary `X-Forwarded-For`/`Forwarded` headers from clients: only accept them from configured trusted proxies.

## 15. Practical Impact for Java Networking

### 15.1. When to Use Plain `Socket`?

Use `Socket` / `ServerSocket` when:

- Designing a custom byte-stream protocol (you still need framing, versioning, auth, and timeouts).
- Learning networking fundamentals or debugging transport.
- Writing an adapter/protocol other than HTTP, such as a specifically defined binary protocol.
- Testing raw wire messages in a controlled, authorized environment.

Do **not** use `Socket` just to hand-assemble HTTP for an ordinary API. When building your own HTTP serializer/parser, you take on responsibility for framing, encoding, security, keep-alive, redirects, TLS, proxies, compression, HTTP/2/3 compatibility, and compliance.

### 15.2. When to Use `java.net.http.HttpClient`?

Java 17 `HttpClient` provides:

- `HttpRequest` builder: URI, method, headers, body publisher, timeout.
- `HttpResponse`: status, headers, body, version.
- `BodyPublishers`/`BodyHandlers` for bytes, strings, files, and many other types.
- Synchronous `send()`; `sendAsync()` returning `CompletableFuture` for asynchronous handling.
- HTTP/1.1 and HTTP/2 via API, connection reuse, redirects, and configurable proxy/TLS options.
- Avoids having the application write CRLF or handle `Content-Length` manually.

Short example (illustrative snippet inside a method `throws Exception`):

~~~java
HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/data"))
    .header("Accept", "application/json")
    .timeout(Duration.ofSeconds(5))
    .GET()
    .build();

HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

int status = response.statusCode();
String contentType = response.headers()
        .firstValue("Content-Type").orElse("unknown");
String body = response.body();
~~~

Requires imports `java.net.URI`, `java.net.http.*`, and `java.time.Duration`; the URL is illustrative only, with **no** stdout/guarantee that the endpoint returns JSON. Do not treat the response `Content-Type` as absolute truth: you still need to parse/validate the body, limit size, and handle errors. Java's HttpClient does not guarantee that a server supports HTTP/2 just because the client prefers that version.

### 15.3. Why Is an HTTP Server Not Like a TCP Server?

A TCP server typically has an `accept() -> Socket -> InputStream/OutputStream` loop. An HTTP server must also:

- Decode/accept HTTP versions and framing.
- Identify URI/Host/authority, HTTP method, and request target.
- Enforce header/body limits, timeouts, and security policies.
- Map resources to specific handlers/methods.
- Read representations by media type; validate data.
- Authenticate and check authorization.
- Generate status, headers, and body with valid framing.
- Handle persistent connections, concurrency, proxies, and errors/cancellation.
- Track request-id, latency, and success/failure at the HTTP level.

Therefore, **simply adding `GET` to a TCP string** does not give you a complete HTTP server. In real applications, use a maintained HTTP server and avoid writing a hand-rolled parser.

## 16. Security and Dangerous Assumptions

1. **HTTPS does not replace authorization.** TLS protects the channel and typically authenticates the server, but the application must still determine user/resource permissions.
2. **Do not hand-parse HTTP in production**: HTTP/1.1 has many framing rules, and parser differences across proxies can create request smuggling.
3. **Limit inputs**: header size/count, URI length, body size, upload size, decompression ratio, request duration, concurrent connections, and active requests; the demo uses `readAllBytes()` only when the payload is bounded and controlled by the code itself.
4. **Avoid SSRF**: a server should not arbitrarily fetch any URL supplied by a client if it could reach metadata/internal services.
5. **Do not trust `Host`, forwarded headers, or client-set `Content-Length`** if they affect routing/security; let the HTTP stack parse and enforce proper policies.
6. **Cookies and tokens** need protection: `Secure`, `HttpOnly`, `SameSite` as appropriate, reasonable lifetimes, never log secrets or send tokens over plain HTTP.
7. **Retries** must consider idempotency and business side effects; `GET` is expected to be safe, while `POST` by default should not be blindly retried if the outcome is unknown.
8. **Caching** can expose personal data if a shared cache stores responses meant to be private; configure `Cache-Control` and token/vary properly.
9. **HTTP 200 response does not guarantee a distributed transaction**; the application contract must explicitly state completion status.
10. **HTTP/3 is not unencrypted UDP**; it is HTTP semantics over QUIC, with transport security and stream semantics.

## 17. Common Foundational Misconceptions

| Misconception | Reality |
| --- | --- |
| "TCP already knows HTTP request/response" | TCP knows a byte stream; HTTP defines messages and semantics |
| "One HTTP message equals one TCP packet" | No; TCP can split/coalesce bytes freely |
| "Every HTTP request always opens a new TCP connection" | No; HTTP/1.1 reuses connections, HTTP/2/3 multiplex |
| "HTTP is a TCP protocol so HTTP/3 also runs on TCP" | HTTP/3 is a mapping over QUIC/UDP |
| "HTTP/3 uses UDP so the body can reorder bytes like datagrams" | QUIC provides reliable in-order data per stream |
| "HTTP/2 is text HTTP/1.1 with compression added" | HTTP/2 uses binary framing, streams, and HPACK |
| "An HTTP method is an OS network command" | Methods belong to HTTP semantics at the application layer |
| "GET always has no side effects and needs no auth" | Safe semantics do not eliminate logging and authorization |
| "PUT is idempotent so the response must be identical every time" | Idempotency refers to the intended effect on the resource |
| "POST can never be retried" | It can be retried when idempotency/deduplication is designed or safety is known |
| "TCP ACK means the server saved the order" | TCP ACK only confirms byte receipt at the transport layer, not a business commit |
| "HTTP 404 is a TCP connection failure error" | 404 is an HTTP response; a connect failure has no HTTP status |
| "HTTP 500 makes Java HttpClient automatically throw an exception" | `HttpClient.send()` normally returns `HttpResponse`; check status |
| "Content-Length is the character count in a Java String" | It is the byte count of the content per wire framing |
| "One read() call gets the entire response" | TCP streams have partial reads; HTTP parsers need framing |
| "Content-Type and Accept are the same kind of header" | `Content-Type` describes the sent representation; `Accept` expresses desired response types |
| "HTTP is stateless so you cannot log in" | Sessions/cookies/tokens are state at the application layer |
| "Connection: close works the same way in HTTP/2/3" | HTTP/2/3 have different frame/connection rules; connection-specific headers are invalid as in h1 |
| "With HTTPS there is no need to check user permissions" | TLS does not replace authorization |
| "A proxy is just a normal IP router" | A proxy understands/routes HTTP messages and sometimes changes transport/version between hops |
| "An HTTP/2 client sending to an HTTP/1.1 server will definitely fail" | HTTP clients can negotiate/fall back per standard; check the actual version received |
| "Having HttpClient means Java 17 automatically supports HTTP/3" | Standard Java 17 API supports HTTP/1.1 and HTTP/2, with no HTTP/3 enum |

## 18. Practice Exercises and Answers

### Exercise 1 — Comparing TCP and HTTP

A TCP program sends the byte sequence `"PING"` to port 9000. Can that be called an HTTP request?

**Answer:** No, unless the program applies proper HTTP message framing and semantics. `PING` is just a TCP payload; an HTTP/1.1 request needs a properly structured method, target, version, and headers such as `GET /ping HTTP/1.1` with `Host`, ending the headers with CRLF CRLF.

### Exercise 2 — Distinguishing Request/Response Parts

Read the message:

~~~http
POST /notes HTTP/1.1
Host: example.test
Content-Type: application/json
Content-Length: 13

{"text":"hi"}
~~~

Identify the method, resource target, request headers, and request body.

**Answer:** Method `POST`, target `/notes`, headers `Host`, `Content-Type`, and `Content-Length`, and body is JSON `{"text":"hi"}` of exactly 13 ASCII bytes. TCP does not understand creating a note; semantics are defined by HTTP + the application.

### Exercise 3 — Status Is Not a Transport Error

A client calls an API and receives `HTTP/1.1 404 Not Found`; another client gets `ConnectException`. How do these two situations differ?

**Answer:** In the 404 case, a valid **HTTP response** was received reporting that the resource was not found; `ConnectException` occurs at the transport establishment layer, so there is usually no HTTP response. Recovery and logging should classify them differently.

### Exercise 4 — Persistence

An HTTP/1.1 server has returned response A, but the TCP connection remains open. Should the client wait for `readAllBytes()` until EOF to determine that response A is finished?

**Answer:** No. A persistent connection may continue carrying other requests/responses; use HTTP/1.1 framing (content length/chunked/semantics) to determine the boundary of A.

### Exercise 5 — HTTP/2 and HTTP/3

What is the fundamental transport difference between the two versions? Do you have to relearn the semantics of GET/POST and HTTP 200 from scratch?

**Answer:** HTTP/2 transfers binary frames and multiplexes streams over TCP; HTTP/3 uses QUIC over UDP with reliable streams and integrated TLS 1.3. Common semantics (methods, resources, status, representations) are preserved per standard HTTP.

### Exercise 6 — Idempotency

Two identical PUT requests to `/settings/theme` might return 201 the first time and 200 the second time; is it still idempotent?

**Answer:** It can still be idempotent, because the criterion is the **intended effect on the resource when repeated**, not that the status code or response must be identical each time. However, the implementation must avoid unintended non-idempotent side effects.

### Exercise 7 — POST Timeout

A client sends a POST to create an order, and then the connection drops before seeing a response. Can it be assumed the server has not created the order and immediately retry?

**Answer:** No. The outcome is unknown because the server may have succeeded and the response was lost. You should design an idempotency key, operation ID, or a result-checking API; retry in a controlled manner.

### Exercise 8 — Cache Validation

A client sends `If-None-Match: "v7"` and the server returns `304 Not Modified`. How should the client interpret this?

**Answer:** The server indicates the representation has not changed according to the validator; the cache/client can reuse the stored representation per HTTP caching rules. `304` does not contain a new body equivalent to a full `200` response.

### Exercise 9 — Content-Length and Unicode

A response has body `"Việt"`, encoded in UTF-8. Why should you not use `String.length()` directly as `Content-Length`?

**Answer:** Because `Content-Length` is measured in **bytes**, whereas Java's `String.length()` counts UTF-16 code units. You must encode the text into bytes and take `bytes.length` for the chosen charset.

### Exercise 10 — Java HttpClient and HTTP 404

In Java 17, `client.send(req, BodyHandlers.ofString())` receives HTTP 404. Does the method necessarily throw an exception because of 404?

**Answer:** No. It normally returns an `HttpResponse` with `statusCode() == 404`; the caller decides whether this is a business error. Exceptions are used for I/O errors, timeouts, interruption, and other failures—not merely because the status code is 4xx/5xx.

### Exercise 11 — Request–Response Does Not Mean Synchronous API

Does HTTP request–response prevent a Java client from using `sendAsync()` or a server from processing a background job?

**Answer:** No. Request–response describes **interaction semantics**. The Java API can still be asynchronous; the server can return `202 Accepted` with a URI to track a running job. Do not confuse the message model with blocking threads.

### Exercise 12 — Proxy Changing Transport

A client uses HTTP/2 over TLS to a reverse proxy, and the proxy uses HTTP/1.1 to the backend. Does GET change into a different meaning?

**Answer:** No. A proxy/gateway must preserve or apply valid translations of **HTTP semantics** across hops. Representation/framing/transport may differ, but the client is still requesting the same resource/method under the API contract.

## 19. Learning and Java HTTP Implementation Checklist

- [ ] I distinguish TCP byte streams, TLS/QUIC transport, and HTTP message semantics.
- [ ] I understand that resource/URI, method, headers, status, and response body belong to the HTTP layer.
- [ ] I know HTTP/1.1 uses start lines + CRLF + headers + body, requiring accurate framing.
- [ ] I do not assume one `read()` equals one HTTP request/response.
- [ ] I know `Content-Length` is byte length and when a response has no body.
- [ ] I know HTTP/2 has binary frames/multiplexing and HTTP/3 runs over QUIC streams, not raw UDP text.
- [ ] I understand stateless HTTP differs from sessions/cookies and connection persistence.
- [ ] I distinguish `safe` and `idempotent` before designing retries.
- [ ] I check `HttpResponse.statusCode()` and do not treat 4xx/5xx as `Socket` exceptions.
- [ ] I configure connect/request timeouts and limits on body, headers, and concurrency.
- [ ] I do not write a custom HTTP parser for production just because I know CRLF.
- [ ] I choose HTTPS for sensitive information and verify certificates, authorization, and input validation.
- [ ] I understand a proxy can change HTTP version/connection per hop.
- [ ] I have an appropriate plan for caching, conditional requests, retries, and observability.
- [ ] I know Java 17 `HttpClient` supports HTTP/1.1/2, not HTTP/3 via the standard API.
- [ ] I use a full HTTP library for ordinary APIs and only use raw sockets for labs/custom protocols.

## 20. Standard and Java References

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): defines request/response, application-level stateless semantics, resource/method/status/headers, and HTTP versions.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): request line, status line, CRLF, message syntax, and framing.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): binary frames, streams, multiplexing, HPACK header compression.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): HTTP semantics over QUIC, streams, and HTTP/3 framing.
- [RFC 9000 — QUIC: A UDP-Based Multiplexed and Secure Transport](https://www.rfc-editor.org/rfc/rfc9000): transport reliability, streams, and connection management.
- [RFC 9204 — QPACK](https://www.rfc-editor.org/rfc/rfc9204): field compression for HTTP/3.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache freshness, validation, reuse, and shared caches.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): building HTTP clients, versions, timeouts, `send`, and `sendAsync`.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): method, URI, headers, body publisher.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): status, body, version, headers.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): embedded HTTP server for learning/testing, `HttpExchange`, context routing.
- [Java SE 17 — Socket](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html): TCP byte stream; used as a baseline for comparing with HTTP semantics.

**Conclusion:** Transport moves data between two ends, while **HTTP defines what the client is requesting and how the server responds** through resources, methods, status, headers, content, and message rules. **HTTP/1.1, HTTP/2, and HTTP/3 preserve these core semantics while differing in transport and framing**. In Java, use `HttpClient`/an HTTP server to work at the application layer; only use raw sockets when researching or implementing a strictly defined custom protocol.
