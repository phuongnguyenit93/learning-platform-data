# Building a Local HTTP Server That Returns Error Codes, Redirects, and Streaming Content

## 1. Why build a custom HTTP server for networking experiments?

When learning or testing Java Networking, we often need to simulate uncommon but critical responses: `400/404/429/503` errors, `302/307` redirects, streaming responses, mid-body connection drops, and `Content-Length` headers that do not match actual bytes. Depending on a public API for these scenarios makes tests flaky, hard to reproduce, and may violate service rate limits.

A **local HTTP server** gives you full control over HTTP status codes, headers, when bytes are sent, and when the connection is closed. The Java client runs on the same machine to verify the exact behavior you want to study, with no Internet dependency.

```text
                A single Java 17 program
  +------------------------------------------------+
  |                                                |
  |  HttpClient                                    |
  |      |                                         |
  |      | GET http://127.0.0.1:<ephemeral-port>   |
  |      v                                         |
  |  HttpServer (JDK jdk.httpserver)               |
  |      |                                         |
  |      +-- /fixed         -> 200, fixed-length   |
  |      +-- /bad-request   -> 400 JSON            |
  |      +-- /not-found     -> 404 JSON            |
  |      +-- /limited       -> 429 Retry-After     |
  |      +-- /unavailable   -> 503 Retry-After     |
  |      +-- /redirect      -> 302 Location        |
  |      +-- /redirect-307  -> 307 Location        |
  |      +-- /stream        -> 200 chunked         |
  |      +-- /stream-large  -> body exceeds quota  |
  |      +-- /truncated     -> closes before length|
  +------------------------------------------------+
```

This lesson focuses on **creating a controllable test server** and observing it from an HTTP client. It does not build a production web framework, does not expose a public server, and requires no database, TLS certificate, or external service. The examples use **Java 17+**; the complete code is compiled and run for real in Section 9.

Learning objectives:

1. Create and stop `com.sun.net.httpserver.HttpServer`, bound to `127.0.0.1` and port `0`.
2. Use `HttpExchange` to read the request method/URI and set the status, headers, and response body.
3. Choose the right `sendResponseHeaders(status, responseLength)` mode for fixed-length, streaming/chunked, or empty bodies.
4. Return HTTP error codes with appropriate bodies/headers; understand how protocol errors differ from business errors.
5. Create relative `Location` redirects and compare client `Redirect.NEVER` with `Redirect.NORMAL`.
6. Build over-limit streaming and truncated-body scenarios, and test fail-closed client behavior.
7. Clean up all sockets/servers in `finally` so tests are repeatable.

## 2. Choosing the right tools in the JDK

### 2.1. Available APIs

| API | Role | Where used |
| --- | --- | --- |
| `com.sun.net.httpserver.HttpServer` | Creates an HTTP listener and maps requests to handlers | Server side |
| `HttpHandler` | Interface for handling each HTTP exchange | Server side |
| `HttpExchange` | Request method/URI/headers/body and response headers/body | Server side |
| `HttpContext` | Maps a path prefix to a handler and filters | Server side |
| `Headers` | Case-insensitive map of header field names | Server side |
| `java.net.InetSocketAddress` | IP address/port that the server binds to | Configuration |
| `java.net.http.HttpClient` | Client sending GET/HEAD/POST requests to loopback | Testing |
| `HttpRequest` | Request URI/method/timeout | Testing |
| `HttpResponse` | Status/headers/body and final URI | Testing |
| `InputStream`/`OutputStream` | Reading and writing bodies incrementally | Client and server |

`HttpServer` belongs to the **`jdk.httpserver` module** included in JDK 17; no Maven/Gradle dependency is needed to run the samples. You can specify the module explicitly:

```bash
javac --release 17 --add-modules jdk.httpserver LocalHttpLab.java
java --add-modules jdk.httpserver LocalHttpLab
```

Some IDEs resolve the module automatically from the project classpath, but the commands above declare the dependency explicitly for easy reproducibility. Note that Java 17 already includes `HttpServer`, so you do **not** need `SimpleFileServer` or `jwebserver` (components added in JDK 18 for static file serving).

### 2.2. Why use HttpServer instead of parsing HTTP manually with Socket?

With raw `ServerSocket`, you have to implement the request line, headers, message framing, chunked encoding, keep-alive, protocol errors, and many security edge cases yourself. Because this lesson focuses on testing **status codes, redirects, and body streaming**, `HttpServer` eliminates repetitive parser boilerplate.

However, this JDK server is a lightweight tool for testing and prototyping. It **does not automatically provide authentication, authorization, business validation, rate limiting, production-grade observability, or HTTPS**. If a real application needs HTTPS, Java provides `HttpsServer` and `SSLContext`, though configuring TLS securely is a separate topic; never expose a test HTTP server to the Internet.

## 3. Binding to loopback and choosing port 0 to avoid collisions

Creating the server:

```java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 0), 0);

server.createContext("/hello", exchange -> {
    byte[] bytes = "Hello".getBytes(StandardCharsets.UTF_8);
    try (exchange) {
        exchange.getResponseHeaders().set("Content-Type", "text/plain");
        exchange.sendResponseHeaders(200, bytes.length);
        exchange.getResponseBody().write(bytes);
    }
});

server.start();
try {
    int actualPort = server.getAddress().getPort();
    // Use URI http://127.0.0.1:<actualPort>/hello in tests.
} finally {
    server.stop(0);
}
```

*This snippet belongs inside a method declaring `throws Exception` with imports for `HttpServer`, `InetSocketAddress`, and `StandardCharsets`. See Section 9 for the complete example.*

Explanation:

- **`127.0.0.1`** is the IPv4 loopback address. Only processes with access to loopback in the corresponding network namespace can connect; this is **not authentication**.
- **Port `0`** asks the operating system to pick an available ephemeral port. For automated or parallel tests, this is better than hardcoding port `8080` or `8000` because it avoids port collisions.
- The second argument in `HttpServer.create(address, backlog)` is the **TCP accept backlog**. Passing `0` lets the implementation choose a default value; it **does not mean the server accepts 0 requests**.
- `createContext("/hello", handler)` registers a route before the server starts serving. Context mapping uses **path prefix matching**; do not treat it as a router that automatically enforces HTTP methods or authorization.
- `start()` begins accepting requests. `getAddress().getPort()` retrieves the **actual port** after binding.
- `stop(0)` stops serving and closes open connections per the API's behavior—it does not cancel a single request with status 0. The parameter is the **maximum wait time in seconds** for in-flight handlers; a stopped server instance cannot be started again.

Do not use `new InetSocketAddress("0.0.0.0", 0)` in simple tests unless access from another device is required. Binding all interfaces can expose the service unintentionally. This lesson is **strictly for test fixtures without secrets**.

## 4. Lifecycle of an HttpExchange

A single request/response follows this sequence:

```text
HTTP request arrives at listener
    |
    v
HttpServer selects HttpContext and calls HttpHandler.handle(exchange)
    |
    +--> exchange.getRequestMethod()
    +--> exchange.getRequestURI()
    +--> exchange.getRequestHeaders()
    +--> if request body exists: read InputStream with a quota
    |
    v
exchange.getResponseHeaders().set(...)
    |
    v
exchange.sendResponseHeaders(statusCode, responseLength)
    |
    v
exchange.getResponseBody().write(...)
    |
    v
close response body / HttpExchange
    |
    v
HTTP response completes or connection is aborted
```

**Order matters:** you must set all headers you want to send **before** calling `sendResponseHeaders`. Once that call runs, the response headers have started being sent; do not expect modifying headers after writing the body to take effect.

`HttpExchange` is `AutoCloseable` in Java 17; use:

```java
try (exchange) {
    // Set headers, send status, write body.
}
```

When the exchange is closed, its request and response streams are also closed. If the client sent a request body, consume or intentionally handle/close it; closing the exchange without draining the request body may affect connection reuse in the JDK API.

**Do not** store an `HttpExchange` in a global variable to process after the handler has returned and closed it. For asynchronous streaming, lifecycle and thread ownership must be designed explicitly; the examples below use bounded synchronous writes so they remain easy to follow.

## 5. Three responseLength modes of sendResponseHeaders

This is the **most important** technical detail for producing valid responses on JDK 17:

| Call | JDK HttpExchange semantics | Use case |
| --- | --- | --- |
| `sendResponseHeaders(200, N)` with **N > 0** | Fixed-length body of **exact N bytes** | Text/JSON/small file of known size |
| `sendResponseHeaders(200, 0)` | Uses **chunked transfer encoding**; write any number of bytes, finish by closing stream | HTTP/1.1 streaming |
| `sendResponseHeaders(status, -1)` | **No response body** | HEAD, 204, 304, bodyless redirects in the demo |

**Do not mistake `0` for an "empty body".** In the `HttpExchange` API, `0` signals **chunked** transfer encoding. If you want a response with no body, use `-1`. The Java SE 17 documentation for `HttpExchange.sendResponseHeaders` defines these three cases explicitly.

### 5.1. Fixed Content-Length

```java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);
exchange.getResponseBody().write(bytes);
```

*Handler fragment; `exchange` must be closed afterward.*

`"Xin chào"` has **8 UTF-16 code units** but **9 UTF-8 bytes**. If you write:

```java
// ANTI-PATTERN: String.length() is not the wire byte count.
exchange.sendResponseHeaders(200, "Xin chào".length());
exchange.getResponseBody().write(
        "Xin chào".getBytes(StandardCharsets.UTF_8));
```

then you declared 8 bytes but attempt to write 9 bytes: the fixed-length response **exceeds the declared byte count**. The JDK will throw `IOException` and abort the exchange. Always **compute `byte[]` first**, then pass `bytes.length`.

If you declare N bytes but write only M bytes where **M is less than N**, closing the response body may throw `IOException` and close the connection. This is how to intentionally induce a truncated-body failure to test a client (Section 9), **not normal server behavior**.

### 5.2. Chunked body (streaming)

```java
try (exchange) {
    exchange.getResponseHeaders().set("Content-Type", "text/plain");
    exchange.sendResponseHeaders(200, 0);
    OutputStream out = exchange.getResponseBody();
    out.write("one|".getBytes(StandardCharsets.UTF_8));
    out.flush();
    out.write("two".getBytes(StandardCharsets.UTF_8));
    out.flush();
}
```

When the server closes the stream cleanly, the HTTP stack terminates the chunked body per the protocol; the client receives the **logical body** `one|two`. In the HTTP/1.1 test, the `Transfer-Encoding: chunked` header is verified with `HttpClient`.

**Note:** each `out.write/flush` call **does not guarantee the client sees a matching `InputStream.read()`**. TCP/HTTP buffers, chunk encoding, proxies, and the HTTP client may coalesce or split bytes. Tests must assert on **content and protocol state**, never assuming "one server flush equals one client read."

### 5.3. No body

```java
try (exchange) {
    exchange.getResponseHeaders().set("Location", "/fixed");
    exchange.sendResponseHeaders(302, -1);
}
```

This is a valid redirect response for the demo's design: `Location` in the header, no response body. `-1` is also appropriate for `204 No Content` and a `HEAD` response. For `HEAD`, you can include metadata headers such as `Content-Type` and the `Content-Length` **of the corresponding GET representation** without sending body bytes.

Do not call `sendResponseHeaders(204, 0)` and then attempt to stream a body. Status 204 has no message content under HTTP semantics.

## 6. Generating testable 4xx/5xx error codes

An HTTP error is not always equivalent to a Java exception. A server can handle a request cleanly at the TCP layer and **intentionally return 400/404/429/503** so the client exercises its error-handling branches.

| Status | Lab scenario | What the client should do |
| --- | --- | --- |
| `400 Bad Request` | Invalid input or schema | Do not retry the same request; fix input |
| `401 Unauthorized` | Unauthenticated or bad credentials | Re-authenticate according to policy |
| `403 Forbidden` | Authenticated but lacks permission | Do not auto-retry indefinitely |
| `404 Not Found` | Resource not found | Report missing resource, do not parse as a success document |
| `405 Method Not Allowed` | POST to a GET/HEAD-only endpoint | Read `Allow`; use a supported method |
| `409 Conflict` | Current state prevents the operation | Handle business conflict |
| `413 Content Too Large` | Upload request exceeds quota | Reduce payload per contract |
| `415 Unsupported Media Type` | Header/body uses an unsupported media type | Choose a valid `Content-Type` |
| `422 Unprocessable Content` | Valid syntax, invalid business content | Fix the data |
| `429 Too Many Requests` | Rate limit exceeded | Respect `Retry-After`/backoff |
| `500 Internal Server Error` | Unexpected server error | Do not assume client fault; log safely on server |
| `503 Service Unavailable` | Maintenance/overload/temporarily unavailable | Retry with bounds and backoff when appropriate |
| `504 Gateway Timeout` | Gateway/upstream did not respond in time | Distinguish upstream timeout from client timeout |

**Do not treat every 4xx as a Java exception to catch indiscriminately**, and do not assume every 5xx is safe to retry. For requests with side effects such as a POST creating an order, the server may have committed before the response was lost; require an idempotency key or server-side deduplication before resending.

### 6.1. Small, clear JSON error bodies

```java
static void sendJsonError(HttpExchange ex, int status, String errorCode)
        throws IOException {
    String json = "{\"error\":\"" + errorCode + "\"}";
    byte[] body = json.getBytes(StandardCharsets.UTF_8);
    try (ex) {
        ex.getResponseHeaders().set(
                "Content-Type", "application/json; charset=UTF-8");
        ex.sendResponseHeaders(status, body.length);
        ex.getResponseBody().write(body);
    }
}
```

*This fragment assumes `errorCode` is a **server-controlled constant** like `"invalid_input"`, not an arbitrary user string; for dynamic data, use a proper JSON serializer to escape values safely. Required imports: `HttpExchange`, `IOException`, `StandardCharsets`.*

Never return stack traces, filesystem paths, database credentials, or internal details in HTTP error responses. For test environments, a fixed schema body such as `{"error":"invalid_input"}` makes assertions fast and avoids coupling to changing exception messages.

### 6.2. Retry-After on 429 and 503

A handler simulating rate limiting:

```java
server.createContext("/limited", ex -> {
    ex.getResponseHeaders().set("Retry-After", "2");
    text(ex, 429, "text/plain", "slow down");
});
```

This snippet assumes the `text(...)` helper from Section 9 and an initialized `server`. `Retry-After: 2` is an **advisory 2-second wait** under HTTP semantics (the header can also be an HTTP-date); it is not an automatic Java sleep command. Java's `HttpClient` **does not automatically enforce application-level retry/backoff** for all 429/503 errors by default. Test clients should read the header, classify the status, and apply a bounded retry policy.

Never implement unbounded retries; add jitter, an overall deadline, a maximum attempt limit, and idempotency checks.

## 7. Redirects: 301/302/303/307/308 and Location

A redirect test server can be minimal:

```java
server.createContext("/redirect", ex -> {
    try (ex) {
        ex.getResponseHeaders().set("Location", "/fixed");
        ex.sendResponseHeaders(302, -1);
    }
});
```

**Location** can be a relative URI such as `/fixed`. The client resolves it against the current URI to obtain the absolute URL. Related status codes:

| Status | Core meaning | Testing notes |
| --- | --- | --- |
| `301 Moved Permanently` | Permanent redirect | Caches/clients may remember the redirect depending on semantics |
| `302 Found` | Temporary redirect | Historically changed POST to GET in some clients |
| `303 See Other` | Redirect to another URI, typically using GET | Fits "POST then view result" contracts |
| `307 Temporary Redirect` | Temporary redirect, **preserves method/body semantics** | Be careful when the body cannot be replayed |
| `308 Permanent Redirect` | Permanent redirect, preserves method/body | Do not blindly resend non-idempotent requests |

The demo uses **GET**, so the `307 -> 302 -> 200` chain can be verified without side effects.

### 7.1. Client configuration: NEVER vs. NORMAL

```java
HttpClient never = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

HttpClient normal = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

With `NEVER`, `GET /redirect` returns **302 and `Location: /fixed`** directly; the client does not follow the destination.

With `NORMAL` and **same-origin loopback** redirects in the demo, `GET /redirect-307` goes through `/redirect` to `/fixed`; the final status is **200**, and `HttpResponse.uri().getPath()` is `/fixed`.

**Warning:** `Redirect.NORMAL` is not a complete SSRF defense. It blocks certain scheme downgrades (HTTPS→HTTP), but **does not enforce an application allowlist of hosts, ports, or paths**. For user-controlled URLs, use `NEVER` and **validate each `Location` before making a new request**, checking DNS/IP/egress rules, limiting hops/loops, and never forwarding `Authorization` or cookies to unauthorized origins.

### 7.2. Safe redirect handling for GET

```text
GET /initial --302--> Location: /next
    |
    v
URI.resolve(Location)
    |
    +-- validate scheme, host, port, path, userinfo
    +-- reject off-origin / forbidden destination
    +-- maxRedirects / seen URI / total deadline
    |
    v
GET /next
```

Do not read `response.headers().firstValue("Location")` and blindly follow it while sending secrets off-origin. The demo uses safe local redirects, whereas production SSRF defenses need both network policy and validation at connection time (DNS rebinding can bypass a pre-connect DNS lookup).

## 8. Streaming responses: HTTP/1.1 chunked vs. fixed Content-Length

### 8.1. How do fixed-length and streaming differ?

**Fixed-length:** the server knows the exact byte count before sending, can declare `Content-Length: N`, and must write exactly N bytes.

**Chunked:** the server begins sending before knowing the total byte count—for example, live log output, a file generated on the fly, or an API emitting incremental results. In the JDK 17 API:

```java
ex.sendResponseHeaders(200, 0); // chunked response
OutputStream out = ex.getResponseBody();
out.write("first".getBytes(StandardCharsets.UTF_8));
out.flush();
out.write("second".getBytes(StandardCharsets.UTF_8));
out.flush();
```

This snippet requires closing the exchange after writing. The **logical** data read by the client is `firstsecond`; chunked framing is encoded and decoded by the HTTP stack.

### 8.2. Chunked wire framing vs. what the client sees

HTTP/1.1 chunked transfer uses chunk sizes on the wire (illustrative diagram—**not a guarantee of how the JDK splits chunks per flush**):

```http
HTTP/1.1 200 OK
Transfer-Encoding: chunked
Content-Type: text/plain

4
one|
3
two
0

```

The client HTTP library handles framing so the application only sees the bytes `one|two`. Therefore:

- Do not manually parse strings like `4\r\none|\r\n...` from `BodyHandlers.ofInputStream()`: `HttpClient` **already decodes** HTTP chunked framing.
- Do not assume `InputStream.read()` returns exactly one server write or one HTTP chunk.
- Do not treat `flush()` as an application ACK or a guarantee that bytes have reached the consumer at that instant.
- If the peer closes TCP before the terminating zero-size chunk, the HTTP client may report a framing error; never mark a stream successful just because partial data was read.
- HTTP/2 and HTTP/3 use their own stream framing; **HTTP/1.1 chunked encoding is not the payload framing model of WebSocket or SSE**.

### 8.3. Reading the body as an InputStream on the client

```java
HttpResponse<InputStream> response = client.send(
        request,
        HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    long count = 0;
    int n;
    while ((n = body.read(buffer)) != -1) {
        if (n > MAX_BYTES - count) {
            throw new IOException("Body exceeds limit");
        }
        count += n;
        // Process available bytes; do not buffer everything in RAM.
    }
}
```

*Fragment inside a method with `client`, `request`, and `MAX_BYTES`; requires importing `HttpResponse`, `InputStream`, and `IOException`.*

Important note: with `BodyHandlers.ofInputStream()`, `client.send(...)` may return as soon as the response headers arrive, **before the body has been fully read**. You must handle exceptions while reading the stream, close the body even on error, enforce a byte quota, and apply a deadline/cancellation for the full operation.

### 8.4. Streaming logs/SSE as an application-layer pattern

To stream simple events, a server can set `Content-Type: text/event-stream; charset=UTF-8` and send lines formatted as **Server-Sent Events (SSE)**:

```text
event: progress
data: {"percent":25}

event: progress
data: {"percent":50}

```

**This is an example SSE payload, not output from the Section 9 demo.** SSE uses a unidirectional HTTP response stream; it differs from **WebSocket**, which is a full-duplex channel after handshake. A real SSE server must manage request cancellation, heartbeats, timeouts, backpressure, and access control. Chunked HTTP transports the stream over HTTP/1.1, but chunk boundaries do **not** correspond to SSE events; events are delimited by blank lines in the SSE format.

## 9. Complete Java 17 program — server + client + error branches

This is a **self-contained program running in a single JVM with no Internet access**. It starts a localhost server on port 0, registers routes, and uses two `HttpClient` instances to compare responses.

Scenarios covered:

- Fixed 200 body and bodyless HEAD (whose `Content-Length` matches the representation length of 5).
- HTTP 400/404 with JSON errors, and HTTP 429/503 with `Retry-After`.
- POST rejected with 405 and `Allow: GET, HEAD`.
- GET `302` redirect not followed under `NEVER`, versus a `307→302→200` chain followed under `NORMAL`.
- Chunked streaming returning `one|two`, with the client observing `Transfer-Encoding`.
- Chunked stream exceeding a 10-byte quota and a fixed response truncated before its declared length of 20; the client rejects both.

**Filename: `LocalHttpLab.java`**

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public final class LocalHttpLab {
    static void text(HttpExchange ex, int status, String media, String value)
            throws IOException {
        byte[] bytes = value.getBytes(StandardCharsets.UTF_8);
        try (ex) {
            ex.getResponseHeaders().set("Content-Type", media);
            ex.sendResponseHeaders(status, bytes.length);
            ex.getResponseBody().write(bytes);
        }
    }

    static void redirect(HttpExchange ex, int status, String location)
            throws IOException {
        try (ex) {
            ex.getResponseHeaders().set("Location", location);
            ex.sendResponseHeaders(status, -1);
        }
    }

    static HttpClient newClient(HttpClient.Redirect redirects) {
        return HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .followRedirects(redirects)
                .connectTimeout(Duration.ofSeconds(3))
                .build();
    }

    static HttpRequest request(URI base, String method, String path) {
        return HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(5))
                .method(method, HttpRequest.BodyPublishers.noBody())
                .build();
    }

    static HttpResponse<String> stringReply(HttpClient client, URI base,
            String method, String path) throws Exception {
        return client.send(request(base, method, path),
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
    }

    static long consumeBounded(InputStream body, long max)
            throws IOException {
        byte[] bytes = new byte[8];
        long count = 0;
        int n;
        while ((n = body.read(bytes)) != -1) {
            if (n > max - count)
                throw new IOException("Body exceeds limit");
            count += n;
        }
        return count;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/fixed", ex -> {
            if ("HEAD".equals(ex.getRequestMethod())) {
                try (ex) {
                    ex.getResponseHeaders().set("Content-Type", "text/plain");
                    ex.getResponseHeaders().set("Content-Length", "5");
                    ex.sendResponseHeaders(200, -1);
                }
            } else if ("GET".equals(ex.getRequestMethod())) {
                text(ex, 200, "text/plain; charset=UTF-8", "hello");
            } else {
                ex.getResponseHeaders().set("Allow", "GET, HEAD");
                text(ex, 405, "text/plain", "method not allowed");
            }
        });
        server.createContext("/bad-request", ex ->
                text(ex, 400, "application/json",
                        "{\"error\":\"invalid_input\"}"));
        server.createContext("/not-found", ex ->
                text(ex, 404, "application/json",
                        "{\"error\":\"not_found\"}"));
        server.createContext("/limited", ex -> {
            ex.getResponseHeaders().set("Retry-After", "2");
            text(ex, 429, "text/plain", "slow down");
        });
        server.createContext("/unavailable", ex -> {
            ex.getResponseHeaders().set("Retry-After", "3");
            text(ex, 503, "text/plain", "maintenance");
        });
        server.createContext("/redirect", ex ->
                redirect(ex, 302, "/fixed"));
        server.createContext("/redirect-307", ex ->
                redirect(ex, 307, "/redirect"));
        server.createContext("/stream", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 0); // Chunked HTTP/1.1
                OutputStream out = ex.getResponseBody();
                out.write("one|".getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.write("two".getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
        });
        server.createContext("/stream-large", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 0);
                OutputStream out = ex.getResponseBody();
                for (int i = 0; i < 4; i++) {
                    out.write("123456".getBytes(StandardCharsets.US_ASCII));
                    out.flush();
                }
            } catch (IOException earlyClose) {
                // A bounded client may stop reading before completion.
            }
        });
        server.createContext("/truncated", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Content-Type", "text/plain");
                ex.sendResponseHeaders(200, 20);
                ex.getResponseBody().write(
                        "cut".getBytes(StandardCharsets.US_ASCII));
            } catch (IOException expected) {
                // Intentionally close before the declared 20 bytes.
            }
        });
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient never = newClient(HttpClient.Redirect.NEVER);
            HttpClient normal = newClient(HttpClient.Redirect.NORMAL);

            HttpResponse<String> fixed =
                    stringReply(never, base, "GET", "/fixed");
            System.out.println("GET: " + fixed.statusCode()
                    + " body=" + fixed.body());

            HttpResponse<String> head =
                    stringReply(never, base, "HEAD", "/fixed");
            System.out.println("HEAD: " + head.statusCode()
                    + " bodyLength=" + head.body().length()
                    + " declared=" + head.headers()
                            .firstValue("Content-Length").orElse("none"));

            for (String path : new String[]{"/bad-request", "/not-found",
                    "/limited", "/unavailable"}) {
                HttpResponse<String> r =
                        stringReply(never, base, "GET", path);
                System.out.println(path + ": " + r.statusCode()
                        + " retryAfter=" + r.headers()
                                .firstValue("Retry-After").orElse("none"));
            }
            HttpResponse<String> badMethod =
                    stringReply(never, base, "POST", "/fixed");
            System.out.println("POST: " + badMethod.statusCode()
                    + " allow=" + badMethod.headers()
                            .firstValue("Allow").orElse("none"));

            HttpResponse<String> redirect =
                    stringReply(never, base, "GET", "/redirect");
            System.out.println("redirect NEVER: " + redirect.statusCode()
                    + " location=" + redirect.headers()
                            .firstValue("Location").orElse("none"));

            HttpResponse<String> followed =
                    stringReply(normal, base, "GET", "/redirect-307");
            System.out.println("redirect NORMAL: " + followed.statusCode()
                    + " path=" + followed.uri().getPath()
                    + " body=" + followed.body());

            HttpResponse<String> stream =
                    stringReply(never, base, "GET", "/stream");
            System.out.println("stream: " + stream.statusCode()
                    + " transfer=" + stream.headers()
                            .firstValue("Transfer-Encoding").orElse("none")
                    + " body=" + stream.body());

            HttpResponse<InputStream> large = never.send(
                    request(base, "GET", "/stream-large"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream in = large.body()) {
                consumeBounded(in, 10);
                throw new AssertionError("size limit not enforced");
            } catch (IOException expected) {
                System.out.println("stream-limit: rejected");
            }

            try {
                HttpResponse<InputStream> truncated = never.send(
                        request(base, "GET", "/truncated"),
                        HttpResponse.BodyHandlers.ofInputStream());
                try (InputStream in = truncated.body()) {
                    long count = consumeBounded(in, 100);
                    if (count != 20)
                        throw new IOException("Content-Length mismatch");
                    throw new AssertionError("truncation not rejected");
                }
            } catch (IOException expected) {
                System.out.println("truncated: rejected");
            }
        } finally {
            server.stop(0);
        }
    }
}
```

**Compile and run with Java 17** (the `jdk.httpserver` module provides the local server):

```bash
javac --release 17 --add-modules jdk.httpserver LocalHttpLab.java
java --add-modules jdk.httpserver LocalHttpLab
```

**Observed stdout from compiling and running:**

```text
GET: 200 body=hello
HEAD: 200 bodyLength=0 declared=5
/bad-request: 400 retryAfter=none
/not-found: 404 retryAfter=none
/limited: 429 retryAfter=2
/unavailable: 503 retryAfter=3
POST: 405 allow=GET, HEAD
redirect NEVER: 302 location=/fixed
redirect NORMAL: 200 path=/fixed body=hello
stream: 200 transfer=chunked body=one|two
stream-limit: rejected
truncated: rejected
```

### 9.1. What each line proves

- **GET 200:** the server returns exactly 5 bytes `hello` as a fixed-length body.
- **HEAD 200:** the response body is empty, while the `Content-Length` header is explicitly `5`, matching the GET body.
- **400/404:** handlers deliberately emit error status codes without breaking the TCP connection.
- **429/503:** the client receives the `Retry-After` headers as text `2` and `3`. It **does not auto-retry**; retry decisions belong to the application.
- **POST 405:** the `/fixed` endpoint allows only GET/HEAD and returns `Allow: GET, HEAD`.
- **Redirect NEVER:** receives the raw 302 response and `Location: /fixed`.
- **Redirect NORMAL:** the client follows `307→302→200` to `/fixed`, observing the final URI and body.
- **Stream chunked:** even though the server performs two write/flush calls, the client receives a single logical body `one|two` after `HttpClient` decodes HTTP framing.
- **Stream limit rejected:** the server emits 24 bytes total via chunked encoding; the client enforces a 10-byte limit, checks on each read, throws `IOException`, and refuses data beyond the quota.
- **Truncated rejected:** the server declares 20 bytes but intentionally writes 3 bytes. On write/close, the exchange is aborted; the client read throws `IOException` or fails the count check, preventing the response from being treated as complete.

**Test reliability note:** this program's output was observed in a Java 17-compatible environment compiled with `javac --release 17`. The demo does not measure network timing and does not assert read callback counts, because those depend on scheduling and buffering. This test does not prove the server is safe to expose publicly or cover every HTTP/2 or TLS case.

### 9.2. Why doesn't the program use sleep to prove streaming?

A stream is still a **stream** when the server calls `sendResponseHeaders(200, 0)`, writes in increments, and closes `OutputStream` properly. Adding `Thread.sleep(...)` only slows execution for human observation; it does not change HTTP transfer semantics.

If a test must prove the client processes data **as soon as the first chunk arrives**, use synchronization such as `CountDownLatch` or futures (with a deadline) or measure controlled application events—never write an assertion like "after 50 ms the client has definitely received part 1," as timing depends on the environment and causes flaky tests.

## 10. Manual testing with curl against a separate server process

The `LocalHttpLab` program starts the server, runs its self-tests, and exits immediately. To test with `curl`, write a server variant that keeps the process alive until you press Enter or Ctrl+C. **Do not run curl after the Section 9 program exits**, because the ephemeral port has already been released.

Against a local server running on `http://127.0.0.1:8000` with the same route logic, use:

```bash
curl -i http://127.0.0.1:8000/fixed
curl -I http://127.0.0.1:8000/fixed

# Show error responses and Retry-After:
curl -i http://127.0.0.1:8000/bad-request
curl -i http://127.0.0.1:8000/limited
curl -i http://127.0.0.1:8000/unavailable

# Do not follow redirects: observe 302 and Location:
curl -i http://127.0.0.1:8000/redirect

# Let curl follow redirects in a trusted loopback environment:
curl -iL http://127.0.0.1:8000/redirect-307

# Streaming: -N reduces curl's output buffering:
curl -iN http://127.0.0.1:8000/stream
```

These `curl` commands assume a live server on a known port. On Windows PowerShell, `curl` may be an alias for another command depending on the shell version; use `curl.exe` when you want the real curl CLI.

**Important:** `curl -L` enables automatic redirect following, which is **unsafe to use blindly with untrusted URIs in production**. Use it only against trusted loopback test servers like this example; production software must revalidate every `Location`.

## 11. Testing errors without breaking the server permanently

A **valid HTTP error code** and a **transport failure** are distinct:

```text
Branch A: Server processes the request and returns 404
   -> Client receives status 404 + error body (complete protocol exchange)

Branch B: Server sends 200 / Content-Length: 20 headers
          but closes after writing only 3 bytes
   -> Client sees incomplete body / IOException
   -> No valid artifact to consume

Branch C: Server not listening / TCP reset before response
   -> Client send/connect may throw IOException
   -> No HTTP status may have been received at all
```

Avoid collapsing all three cases into a single exception type; the client should clearly distinguish **HTTP response status**, **network/transport failure**, and **application-level invalid payload**.

### 11.1. Wrong Content-Length scenarios

The `HttpExchange.getResponseBody()` Javadoc specifies that for fixed-length responses, the server must write the exact number of declared bytes. Writing more throws `IOException` on `write(...)`; writing fewer may throw `IOException` on `close()` and abort the exchange.

You can leverage this behavior for fault injection (as in the `/truncated` route), but you must **catch the intentional exception** inside the handler so the test server does not print noisy stack traces or swallow real, unintended errors.

**Never use "server sends 200 and terminates early" to represent a business error such as missing permissions**; if the error can be detected before sending headers, return the **appropriate 4xx/5xx status before starting the body**.

### 11.2. You cannot change HTTP status once streaming has started

Once `sendResponseHeaders(200, 0)` has been called, the server **cannot switch to 500** if an error occurs mid-stream. When an exception happens:

- Close/abort the response per policy and log the error server-side without secrets.
- The client must detect the incomplete stream or an error at the application protocol layer.
- If you need event streaming with structured error reporting, define an `error` event type and an end marker/sequence in the payload before closing, while still recognizing that **the initial HTTP status may be 200**.
- For critical data, use an expected checksum, count, end marker, or manifest from a trusted source to verify completion at the application layer.
- Never commit an artifact solely because a 200 status header was received.

This is why large-file downloaders write to a **temporary file** and publish it only after reading the full body and verifying integrity.

## 12. Adding routes for latency, timeouts, and connection drops

To test client timeouts, you can add a handler that simulates latency **in a local environment**:

```java
server.createContext("/slow", ex -> {
    try (ex) {
        Thread.sleep(250); // Demo: simulate slow processing.
        byte[] body = "late".getBytes(StandardCharsets.UTF_8);
        ex.sendResponseHeaders(200, body.length);
        ex.getResponseBody().write(body);
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
    }
});
```

*This snippet is not part of the complete program in Section 9; it requires the corresponding imports and proper exception/lifecycle handling. This is a latency simulation scenario—do not use sleep to enforce security policies.*

If you configure a client request timeout shorter than the server's response delay, you can observe `HttpTimeoutException` per the API. However, do not write tests that assume millisecond-accurate OS scheduling; use clear timing margins and deadline-aware synchronization.

**Streaming caveat:** `HttpClient.send(..., BodyHandlers.ofInputStream())` can return as soon as headers are ready, before the body is consumed. The duration in `HttpRequest.timeout(...)` must not be mistaken for a **guaranteed deadline covering the entire `InputStream.read()` loop** across all implementations. A reliable client test needs an overall deadline, idle-read timeout/cancellation, a byte cap, and stream closure.

Simulating raw connection resets sometimes requires a specialized HTTP test framework or lower-level socket control because `HttpServer` actively manages framing and lifecycle. Never write a raw HTTP server for public traffic just to inject framing faults.

## 13. Controlling request input and server-side resource limits

A test server may intentionally serve broken or adversarial routes, yet it must still prevent a single test from hanging the entire JVM:

- **Allow only the required HTTP methods.** For example, `/fixed` allows GET/HEAD and rejects POST with 405 + `Allow`. Accepting all methods unchecked makes tests unrepresentative of real APIs.
- **Bound the request body** as you read the stream if the server accepts POST/PUT. `Content-Length` is metadata to check early, not a substitute for an actual byte quota.
- **Bound URLs, queries, and headers** per test requirements; never log raw `Authorization` or cookie headers if present.
- **Isolate test roots/contexts:** `HttpServer.createContext("/api", ...)` uses prefix matching; it can match unintended paths unless the handler validates the path itself. Never use context prefixes as authorization.
- **Bound concurrency:** when serving multiple requests, use an executor with bounded threads and queue; avoid unbounded threads per request.
- **Limit streaming rate and total bytes:** an infinite data route can hang tests or clients; use finite fixtures, cancellable tasks, and deadlines.
- **Stop the server in `finally`** even if a test assertion throws; prevent leaked ports and threads after tests.

Example bounded request body reader:

```java
static long discardUpTo(InputStream body, long limit)
        throws IOException {
    byte[] buffer = new byte[4096];
    long total = 0;
    int n;
    while ((n = body.read(buffer)) != -1) {
        if (n > limit - total)
            throw new IOException("Request body too large");
        total += n;
    }
    return total;
}
```

*This snippet requires importing `InputStream` and `IOException`; it is not a complete HTTP handler.* When the quota is exceeded, decide whether to return 413 or close the connection depending on whether headers have already been sent. Errors after response headers begin cannot change the status code.

## 14. Executors, threads, and experimental limits

If you do not call `server.setExecutor(...)`, JDK `HttpServer` uses the implementation's default executor. Java 17 documentation states that the default runs tasks on the thread created by `server.start()`. For short demos, that is sufficient and keeps output reproducible.

If you need to test concurrency or long-lived streams, set a custom executor **before** calling `start()`:

```java
ExecutorService pool = Executors.newFixedThreadPool(4);
server.setExecutor(pool);
server.start();
try {
    // Test concurrent requests.
} finally {
    server.stop(0);
    pool.shutdownNow();
}
```

*This snippet requires importing `ExecutorService` and `Executors`. Note that `newFixedThreadPool` has an unbounded queue by default; this small configuration is only for fixtures **with controlled load**. A server accepting untrusted requests must use a bounded queue, a rejection policy, and ingress quotas.*

Do not spawn an unbounded thread per request. Do not put `Thread.sleep(10000)` in every handler if you want to test concurrent connections on the default executor. For timing tests, use an explicit executor, synchronization primitives, timeouts, and cleanup.

Every test should know the server is alive and its actual port. Never use `Thread.sleep(200)` as a "guarantee" that the server has started; once `server.start()` returns and you read its address, you can send client requests, and the test should catch and report errors clearly.

## 15. Choosing status, headers, and body to match test goals

Some endpoints are defined primarily by status:

```text
GET /health    -> 200 OK
GET /missing   -> 404 Not Found
GET /limited   -> 429 Too Many Requests + Retry-After
GET /shutdown  -> Do NOT expose outside test scope
```

Responses also carry a contract:

| Goal | Status | Headers | Body |
| --- | --- | --- | --- |
| Success text | 200 | `Content-Type` `text/plain`, `Content-Length` | Exact UTF-8 bytes |
| Success no content | 204 | No body | Empty |
| HEAD metadata | 200 | `Content-Type`, `Content-Length` of GET | Empty |
| Input error | 400 | `Content-Type` `application/json` | Stable JSON error code |
| Missing resource | 404 | `Content-Type` `application/json` | JSON error code |
| Unsupported method | 405 | `Allow: GET, HEAD` | Error body per contract |
| Redirect | 302/307 | `Location: /path` | May have no body |
| Rate limit | 429 | `Retry-After` if applicable | Error body without secrets |
| Temporary unavailable | 503 | `Retry-After` if applicable | Short error body |
| Streaming text | 200 | `Content-Type` `text/plain`; `Transfer-Encoding` `chunked` | Bytes sent incrementally |
| Forced truncation | 200, large declared length | `Content-Length` exceeds actual body | Broken body, connection may abort |

### About HEAD and 204

HTTP semantics require `HEAD` **not to contain response content**. It may carry the `Content-Length` of the corresponding GET response, which does not mean a HEAD client should attempt to read that many bytes. `204 No Content` also has no body. In `HttpExchange`, pass `sendResponseHeaders(status, -1)` when sending no body; valid metadata headers for that status may be set beforehand.

Do not blindly set `Content-Length: 0` for every status and then write content. Clients and proxies may reject responses with conflicting framing.

## 16. Choosing media types, charsets, and JSON accurately

**Server configuration:**

```java
ex.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
```

The actual body must then be encoded in UTF-8. For JSON:

```java
ex.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
```

Never set a JSON `Content-Type` and return an HTML stack trace. Never use `String.length()` instead of `getBytes(UTF_8).length` to declare a fixed length.

If a test only needs static error codes, you can write a fixed JSON literal as in the program. However, **when building JSON from dynamic input**, always use a JSON serializer to escape quotes, newlines, and special characters; arbitrary string concatenation can produce malformed JSON or injection bugs.

When a client receives an error response, `HttpClient.send(...)` normally **returns an `HttpResponse` with `statusCode() == 400/404`**; it does not automatically turn HTTP error statuses into `IOException`. The application must inspect the status and handle it according to policy. `IOException` typically represents network, framing, or I/O failures, not 404.

## 17. Which streaming test techniques produce stable results?

A good test prioritizes the **observable contract** over thread scheduling:

1. **Verify the complete body:** `/stream` returns exact `one|two`, with no extra or missing bytes.
2. **Verify status/headers:** 200 and, in the HTTP/1.1 demo, `Transfer-Encoding: chunked`.
3. **Verify client-side byte quota:** `/stream-large` emits 24 bytes; a client with a 10-byte limit must reject it.
4. **Verify truncation:** `/truncated` declares 20, sends 3, and closes; the client must fail and not commit an artifact.
5. **Close `InputStream` on every branch:** success, invalid status, over-limit, and cancellation.
6. **Test timeout/cancellation separately:** use controlled delays and deadlines rather than relying on a short arbitrary sleep.
7. **Do not assert `read()` call counts:** the HTTP client may coalesce or split data internally.
8. **Do not assert a fixed port:** use the ephemeral port assigned to the server.
9. **Do not depend on the Internet:** run both server and client on loopback with self-contained fixtures.
10. **Run tests repeatedly:** ensure the server stops and cleans up every time, even when an assertion fails.

One common testing mistake is using `BodyHandlers.ofString()` on a very large stream and waiting for completion: that **buffers the entire body in memory** before returning a `String`. To test streaming and quotas realistically, use `BodyHandlers.ofInputStream()` and read buffer by buffer.

## 18. Extending tests: SSE, file downloads, multipart, and specialized errors

A local HTTP server can support many experiment types without Internet data:

### 18.1. SSE progress

The server sets `Content-Type: text/event-stream; charset=UTF-8`, uses chunked streaming, and sends `event: progress` and `data: ...` separated by blank lines. An SSE client reads events one by one and handles reconnection per the application protocol (e.g., `Last-Event-ID`). This is an **application-layer protocol over HTTP**, not one HTTP chunk per SSE event.

### 18.2. File download

A `/file` route can open a fixture file via `Files.newInputStream` and copy it in buffered chunks to the response. If the size is known, use fixed-length `sendResponseHeaders(200, size)`; if the file is generated on the fly, use bounded streaming. For large data, avoid `Files.readAllBytes`, and never let users pick paths outside the document root.

### 18.3. Range and resume

To test `Range: bytes=...`, the server must intentionally return `206 Partial Content` with a `Content-Range` matching the byte offsets, or `416 Range Not Satisfiable` when invalid. The main example **does not implement Range**; do not emit status 206 arbitrarily and assume resume works. Test data also needs a validator/`ETag` if testing `If-Range`.

### 18.4. Multipart upload

An HTTP server receiving multipart uploads must parse boundaries and bound the request body, part count, filenames, total bytes, and rate. `HttpServer` does not include a full servlet or multipart parser; use a suitable parser or custom fixture handler. Do not expose an arbitrary file-upload endpoint just to study GET streaming.

### 18.5. TLS/HTTP proxy errors

The demo server is plaintext HTTP on loopback; to test certificate chains, hostname verification, mutual TLS, or proxy `CONNECT`, use a properly configured `HttpsServer` or mock proxy in a dedicated test. Never disable certificate verification just to "make tests pass."

## 19. Debugging by status line, headers, body, and finally business logic

When an experiment does not behave as expected, check in this order:

```text
(1) Is the port listening? Bound to 127.0.0.1?
    |
(2) Do the sent URI path and method match HttpContext?
    |
(3) Did the handler set headers before sendResponseHeaders?
    |
(4) Is responseLength N, 0, or -1?
    |
(5) Did the body write exact N bytes and close the stream?
    |
(6) Is the client configured to auto-follow redirects or not?
    |
(7) Is the client reading a String or streaming InputStream?
    |
(8) Is the failure an HTTP status, IOException, or parser error?
    |
(9) Did cleanup stop the server and close the body?
```

Use `curl -i` to inspect status+headers+body or `curl -I` to send a HEAD request. In Windows PowerShell, invoke `curl.exe` when needed to avoid the shell alias. Never log raw credentials, `Cookie`/`Authorization` headers, or private data in server logs.

**Very common bug:** an HTTP server returns a 9-byte fixed-length response while the code declares length 8 using `String.length()`. When the client reports an incomplete body or closed connection, check the byte count before blaming the network.

## 20. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Hardcoding port 8000 in all integration tests | Collisions during parallel runs | Use `InetSocketAddress("127.0.0.1", 0)` |
| Binding `0.0.0.0` for local fixtures | Unexpectedly exposed on the network | Bind loopback |
| Not calling `server.stop(0)` in `finally` | Leaked ports/threads | Clean up lifecycle |
| Calling `sendResponseHeaders(200, 0)` thinking it means empty body | Triggers unintended chunked semantics | Use `-1` for no body |
| `sendResponseHeaders(200, "Xin chào".length())` | UTF-8 byte count mismatch | Use `getBytes(UTF_8).length` |
| Declaring N bytes but writing fewer or more | Connection abort/truncation | Write exact N bytes |
| Modifying headers after sending headers | Headers are already committed | Set before `sendResponseHeaders` |
| Not closing `OutputStream`/`HttpExchange` | Exchange/connection leak | Use try-with-resources |
| Defining a `GET` route without validating method | Route accepts POST unintentionally | Switch on method, return 405/`Allow` |
| Treating `createContext("/api", ...)` as exact match | Prefix matching accepts other paths | Validate URI path in handler |
| Assuming server `write/flush` equals client `read()` | Flaky timing tests | Verify logical body and order |
| Using `ofString()` for unbounded payloads | OOM | `ofInputStream()` + size quota |
| Calling `send()` without checking status | 404/429 treated as success | Inspect `statusCode()` |
| Assuming `Retry-After` makes `HttpClient` auto-retry | Rate limits mishandled | Implement explicit client policy |
| Using `Redirect.NORMAL` on user-controlled URLs | May follow forbidden hosts | `NEVER` + validate every hop |
| Forwarding `Authorization` across redirects | Token leakage | Origin-scoped credential handling |
| Returning 200 and trying to switch to 500 mid-stream | Status is already sent | Application error event/abort + client validation |
| Leaving request body unbounded | Test server hangs or runs out of RAM | Bounded reader and timeout |
| Using an unbounded thread pool for multi-client tests | Overload / resource exhaustion | Bounded executor |
| Reading response without closing `InputStream` | HTTP connection leak | Use try-with-resources |
| Treating HEAD `Content-Length` as HEAD body bytes | Hanging waiting for absent body | HEAD carries metadata only |
| Treating a localhost server as production-ready | Missing auth/TLS/observability | Use only for tests/prototyping |

## 21. Extended test matrix

| Scenario | Input/handler | What the client must verify |
| --- | --- | --- |
| GET 200 | `/fixed` | Status 200, body `hello` of exact 5 bytes |
| HEAD | `HEAD /fixed` | Status 200, no body, `Content-Length=5` |
| 400 | `/bad-request` | Receives JSON error, not treated as success |
| 404 | `/not-found` | Clear not-found handling |
| 429 | `/limited` | `Retry-After=2`, no blind retry |
| 503 | `/unavailable` | `Retry-After=3`, classify overload |
| 405 | `POST /fixed` | `Allow=GET, HEAD` |
| 302 NEVER | `/redirect` | Status 302 + `Location` |
| 307→302 NORMAL | `/redirect-307` | Final status 200, final URI `/fixed` |
| Streaming chunked | `/stream` | Status 200, body `one|two`, `Transfer-Encoding` |
| Body exceeds quota | `/stream-large` | Client rejects beyond 10 bytes |
| Body truncated | `/truncated` | Client fails, does not publish |
| Empty response | 204 / -1 | No body, does not wait for bytes |
| Request body too large | POST with Content-Length / no length | Server rejects / 413 per policy |
| Wrong Content-Type | Server returns HTML instead of JSON | Client rejects before parsing |
| Disconnect before headers | Server/socket closes early | `IOException`, no HTTP status |
| Slow headers | Handler delays `sendResponseHeaders` | Client timeout/cancel |
| Slow body | Chunked 1 byte per minute | Idle-read / total deadline |
| Concurrent clients | Multiple `HttpClient` requests | Executor and queue stay bounded |
| Path prefix ambiguity | `/api` vs `/api-secret` | Handler does not grant access based on context prefix |
| Off-origin redirect | `Location` points to different host | Client policy rejects |
| Resume Range | Valid `206`/`Content-Range` | Append only on matching offset/version |
| SSE | `text/event-stream` | Parse events by blank lines, not chunks |
| Cleanup | Assertion fails mid-test | Server stops, streams close |
| Parallel CI | Two tests on the same machine | Port 0 avoids collisions |

This is a **recommended test matrix**—not every case listed here is executed by the Section 9 program. Only the lines printed to stdout by that program are directly observed test results; the remaining rows require additional handlers/tests if your product demands them.

## 22. Practice exercises

**Exercise 1.** Why does `sendResponseHeaders(200, 0)` not mean "send an empty body"? What second parameter should you pass to return `204 No Content`?

**Exercise 2.** A server returns the text `Xin chào`; if you pass `"Xin chào".length()` as `responseLength`, what can happen and why?

**Exercise 3.** When the HTTP status is 404, does `HttpClient.send(...)` necessarily throw `IOException`? Which property of the response should you inspect?

**Exercise 4.** For `GET /redirect`, the server returns `302 Location: /fixed`. What is the difference between `Redirect.NEVER` and `Redirect.NORMAL` on a same-origin loopback server?

**Exercise 5.** The server calls `out.write("one|")`, `flush()`, then `out.write("two")`. Can you guarantee the client reads twice with those two exact byte arrays?

**Exercise 6.** The server declares a fixed length of 20 bytes, sends only 3 bytes, and closes the connection. Can the client treat HTTP 200 as a completed download? What kind of failure must it handle?

**Exercise 7.** Why is binding `127.0.0.1:0` better than `0.0.0.0:8080` for integration tests running in CI?

**Exercise 8.** A handler returns 429 with `Retry-After: 2`. Does this make `HttpClient` automatically wait 2 seconds and retry? What is needed for safe retries?

**Exercise 9.** Why can't the server switch the status to 500 after calling `sendResponseHeaders(200, 0)` if a streaming parser/producer fails mid-stream?

**Exercise 10.** When using `BodyHandlers.ofString()` to test a very large stream, what is the main risk? Which API should you switch to if you need a per-read byte limit?

**Exercise 11.** A server registers context `/api`. Should invoking that context be treated as proof that the request path matched `/api` exactly and is authorized?

**Exercise 12.** What does `curl -L` do? Why should it only be used with trusted redirect chains in this lab?

**Exercise 13.** `HEAD /fixed` has `Content-Length=5` and `bodyBytes=0`. Is this an invalid response?

**Exercise 14.** When returning a JSON error built from user-supplied input, why shouldn't you concatenate `String` values directly to construct JSON?

**Exercise 15.** To test that an HTTP client detects a body exceeding a 10-byte quota, how should the server stream be written and what must the client check?

### Suggested answers

1. In JDK `HttpExchange`, `0` enables a chunked body; use `-1` for no body.
2. The string has 8 UTF-16 code units but 9 UTF-8 bytes; the fixed length mismatches and the server may throw `IOException`/abort.
3. No. HTTP 404 is still a valid HTTP response; inspect `response.statusCode()` and handle the error body per contract.
4. `NEVER` returns 302/`Location` directly; `NORMAL` follows valid same-environment redirects and can return 200 from `/fixed`.
5. No. Buffers, chunking, TCP, and the HTTP client may coalesce or split reads; verify the logical content and order.
6. No. The body is incomplete; handle `IOException` or the declared/actual length mismatch and do not commit.
7. Loopback restricts network exposure; port 0 avoids port conflicts when tests run in parallel.
8. No. `Retry-After` is an HTTP hint; you need a retry policy with a deadline, backoff, and idempotency.
9. The HTTP response status and headers are already committed; you can only signal errors via an application protocol or abort, not replace the status code.
10. It may buffer large payloads in RAM; use `ofInputStream()` and read buffer by buffer with a byte cap.
11. No. Contexts use prefix matching; validate the exact request path and authorization explicitly.
12. `-L` follows redirects; it could reach other hosts if unchecked, so use it only on trusted loopback fixtures.
13. No. `HEAD` has no body; `Content-Length` may describe the corresponding `GET` representation.
14. Improper escaping/serialization leads to malformed JSON or injection; use a JSON serializer.
15. Stream a chunked body larger than 10 bytes; the client reads the stream, accumulates the byte count, and rejects before exceeding the max.

## 23. References

- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): creating/binding listeners, `createContext`, `start`, `stop`, and executors.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): response lifecycle, `sendResponseHeaders` and the meaning of `N`/`0`/`-1`, closing exchanges.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handler receiving and processing exchanges.
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): context mapping and filters.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): response/request headers.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): sending HTTP requests and redirect policies.
- [Java SE 17 — HttpClient.Redirect](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html): `NEVER`, `NORMAL`, and `ALWAYS`.
- [Java SE 17 — HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request method and timeout.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString` and `ofInputStream`.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110.html): status codes, redirects, `Retry-After`, and `HEAD`.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112.html): chunked framing and truncated messages.
- [MDN — Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events): SSE format and events over a response stream.
