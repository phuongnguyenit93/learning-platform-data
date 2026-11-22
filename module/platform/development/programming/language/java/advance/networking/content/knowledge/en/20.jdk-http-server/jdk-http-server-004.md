# HttpHandler and HttpExchange in a Request — JDK HTTP Server (Java 17+)

## 1. From an HTTP request to an HTTP response: who is responsible?

In the `jdk.httpserver` module, the JDK provides a relatively compact embedded HTTP server, suitable for internal tools, testing, networking learning examples, and some simple HTTP serving needs. The main components are:

- `HttpServer`: binds an address/port, listens for TCP connections, finds the matching `HttpContext`, and dispatches the request.
- `HttpContext`: associates a root path (e.g., `/api/`) with an `HttpHandler`, optionally adding `Filter` or `Authenticator`.
- `HttpHandler`: **the handling contract** for an HTTP request, with the single method to implement being `handle(HttpExchange exchange)`.
- `HttpExchange`: **the object representing one exchange** consisting of a received HTTP request and the response the handler will produce; it contains request metadata, the request body stream, response headers, response status/body stream, and connection information.

Basic signature:

~~~java
@FunctionalInterface
public interface HttpHandler {
    void handle(HttpExchange exchange) throws IOException;
}
~~~

This is a **simplified API signature for illustration** (you do not need to declare this interface yourself when importing `com.sun.net.httpserver.HttpHandler`). `HttpHandler` decides **what to do** for a request. `HttpExchange` tells you **which request is being processed**, and provides **the way to produce the response**.

Most importantly: **each invocation of `handle(exchange)` represents a separate exchange**. You should not use an `HttpExchange` after the exchange has completed, nor assume each exchange always corresponds to a new TCP connection: HTTP/1.1 persistent connections can serve multiple sequential exchanges over the same connection.

This lesson belongs to the **Java Advance - networking** module, parent section **JDK HTTP Server**, direct topic **“HttpHandler and HttpExchange in a Request”**. The content explains the standard lifecycle, the methods to understand, two tested standalone Java 17+ examples, and common mistakes when building a small server yourself.

## 2. Learning objectives

After completing this lesson, you can:

1. Describe the `HttpServer → HttpContext → HttpHandler.handle(HttpExchange)` relationship.
2. Distinguish a **reused handler** from a **request/response-specific exchange**, avoiding storing request state in shared fields.
3. Use `getRequestMethod()`, `getRequestURI()`, `getRequestHeaders()`, and `getRequestBody()` to read a request; understand the data types and limitations of each API.
4. Use `getResponseHeaders()`, `sendResponseHeaders(status, length)`, and `getResponseBody()` to send a response in the right order.
5. Understand the three characteristic response-length modes of the JDK server: **positive = fixed byte count**, **0 = chunked transfer encoding**, **-1 = no response body**.
6. Know why **response body length is in UTF-8 bytes**, not the Java `String.length()` character count.
7. Ensure **closing the exchange**, consuming/closing the request body, and closing the response output, even when an error occurs.
8. Classify 200, 204, 404, 405, 413, and 415 and use appropriate response headers such as `Content-Type`/`Allow`.
9. Know that context mapping is **prefix path selection**, not an automatic REST router by full method/route.
10. Design safe body limits, timeouts, concurrency, authentication, error responses, and logging.
11. Run two Java 17+ programs: **handler/exchange lifecycle** and **fixed/chunked/no-body/HEAD**.
12. Distinguish the embedded HTTP server approach in the JDK from `java.net.http.HttpClient` on the client side and production frameworks.

## 3. Lifecycle diagram: what does a request go through?

~~~text
HTTP client                         JDK HttpServer
    |                                     |
    | TCP connect + HTTP request         |
    |------------------------------------>|
    |                             accept / parse HTTP/1.1
    |                                     |
    |                         find HttpContext by URI path
    |                                     |
    |                           HttpHandler.handle(exchange)
    |                                     |
    |                           +---------+-----------+
    |                           | request metadata    |
    |                           | request body stream |
    |                           +---------+-----------+
    |                                     |
    |                           business logic/validation
    |                                     |
    |                           +---------+-----------+
    |                           | response headers    |
    |                           | sendResponseHeaders |
    |                           | response body bytes |
    |                           +---------+-----------+
    |                                     |
    |<------------------------------------|
    | HTTP status + headers + body        |
    |                                     |
    |                      close streams / close exchange
    |                                     |
    |                         connection reuse if appropriate
~~~

**An `HttpExchange` has two sides:**

~~~text
                  HttpExchange
             +---------------------+
  REQUEST    | getRequestMethod    |     GET /api/hello
             | getRequestURI       |     /api/hello?lang=vi
             | getRequestHeaders   |     Accept: text/plain
             | getRequestBody      |     InputStream
             +---------------------+
  RESPONSE   | getResponseHeaders  |     Content-Type: text/plain
             | sendResponseHeaders |     HTTP status 200, length N
             | getResponseBody     |     OutputStream
             +---------------------+
                  close()
~~~

Data from `getRequestHeaders()` is **read-only** per the API, while `getResponseHeaders()` allows the handler to add/modify response headers **before committing**. `sendResponseHeaders(...)` initiates sending the status/headers and the response framing rules; after that point, headers cannot be treated as unsent.

## 4. Responsibilities of the four objects

| Component | Lifecycle | Typical APIs | Responsibility |
| --- | --- | --- | --- |
| `HttpServer` | From creation/bind until `stop(delay)` | `create`, `createContext`, `setExecutor`, `start`, `stop` | Listener, context routing, dispatch, executor |
| `HttpContext` | Server context configuration | `getPath`, `getHandler`, `getFilters`, `setAuthenticator` | Binds a path prefix to a handler, filters, auth |
| `HttpHandler` | Usually created/registered **once**, used for many exchanges | `handle(HttpExchange)` | Runs processing logic for each exchange |
| `HttpExchange` | Bound to **one** HTTP request and response | `getRequest*`, `sendResponseHeaders`, `getResponseBody`, `close` | Metadata, streams, response status/body |

### 4.1. One handler can process many exchanges

~~~java
HttpHandler handler = exchange -> {
    try (exchange) {
        byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }
};

server.createContext("/health", handler);
~~~

This is a **code snippet** inside a method that has `server`, importing `HttpHandler`, `StandardCharsets`, and `OutputStream`; it is not a standalone program. `handler` can be invoked by the JDK multiple times for different exchanges.

**Bad design:** storing the current request in a handler field and using it on another thread:

~~~java
// WRONG: request-specific mutable state must not be shared
private HttpExchange currentExchange;
public void handle(HttpExchange exchange) {
    currentExchange = exchange;
}
~~~

If the executor runs concurrently, exchange B can overwrite exchange A; even if not concurrent, keeping an exchange beyond its lifecycle causes leaks or attempts to use closed streams. Request data should be **local variables** inside `handle` or an explicitly passed immutable request context. Shared counters/caches should only be used with proper thread safety.

### 4.2. `HttpContext` selects a handler by path, not by method

~~~java
server.createContext("/api/", new ApiHandler());
~~~

The handler may be called for `/api/hello`, `/api/echo`, `/api/missing`. The Java server selects the context by **URI path** (prefix mechanism, longest matching prefix); it does **not** automatically understand that `GET /api/hello` and `POST /api/hello` are two REST endpoints with different valid methods.

You still have to write the validation logic:

~~~java
String method = exchange.getRequestMethod();
String path = exchange.getRequestURI().getPath();

if (path.equals("/api/hello") && method.equals("GET")) {
    // Handle GET /api/hello.
} else {
    // Send 404 or 405 depending on path/method.
}
~~~

The snippet above is not standalone. A longer context prefix can be selected before a shorter one, such as `/api/admin/` before `/api/`, if both are registered. Context matching is **case-sensitive**, and does not automatically decode/normalize URLs/paths according to your business policy.

Do not rely on `createContext("/api", ...)` assuming all paths are cleanly separated by segment; the `/api` prefix can also match `/apix`. Use a prefix with a sensible `/` and check the full route yourself inside the handler.

## 5. Reading a request through HttpExchange

### 5.1. Method: `getRequestMethod()`

~~~java
String method = exchange.getRequestMethod();
~~~

Values are for example `GET`, `POST`, `PUT`, `HEAD`, `DELETE`. TCP does not understand these strings on its own; this is information parsed by the HTTP server and passed to the handler.

- Identify the resource first, then decide **which methods are supported**.
- For an existing resource where the method is unsupported, return **405 Method Not Allowed** and the **`Allow`** header.
- For a non-existent resource, return **404 Not Found**.
- When permission policies are needed, check **authentication/authorization** at the application level, not just by looking at the method.
- **GET does not implicitly have permission to read everything**, and POST does not guarantee a database write has occurred.

### 5.2. URI: `getRequestURI()`

~~~java
URI target = exchange.getRequestURI();
String path = target.getPath();
String rawPath = target.getRawPath();
String query = target.getRawQuery();
~~~

This is a code snippet inside a handler, requiring `import java.net.URI`. Example request:

~~~http
GET /api/hello?lang=vi HTTP/1.1
Host: localhost

~~~

Corresponding values:

~~~text
getPath()     -> /api/hello
getRawPath()  -> /api/hello
getRawQuery() -> lang=vi
~~~

**Be careful with percent-encoding:** `getPath()` returns the path decoded according to URI semantics, `getRawPath()` preserves escaped characters; `getRawQuery()` does **not** automatically turn the query into a map. Do not take `getRawQuery()` and split on every `&`/`=` as a production URL parser without handling percent-encoding, duplicate parameters, and character encoding.

Do not use `URI.getPath()` directly as a filesystem path to read arbitrary files (risk of traversal/normalization, encoded separators). Route names are **application resources**, not necessarily tied to physical files.

### 5.3. Request headers: `getRequestHeaders()`

~~~java
Headers requestHeaders = exchange.getRequestHeaders();
String contentType = requestHeaders.getFirst("Content-Type");
String accept = requestHeaders.getFirst("Accept");
~~~

Snippet with `import com.sun.net.httpserver.Headers`. Keys are **case-insensitive** per HTTP semantics, but header field values can appear **multiple times**. `getFirst(...)` is convenient when policy accepts a single value; for `Cookie`, `Set-Cookie`, or multiple header lines, you need to understand the rules of each field.

- **Read-only:** request headers are not a map for you to mutate client-sent values.
- **Do not trust input:** `Content-Type` is only a client declaration; still validate bytes/body schema.
- **`Content-Length` is not a safe limit**: it can be missing due to chunked transfer or malformed input; you must limit the number of bytes **actually read**.
- **`Host`** is not trustworthy resource proof; if generating absolute redirects/links based on Host, you need an authority allowlist.
- **`Authorization`** is sensitive data; do not log raw tokens/basic credentials.

### 5.4. Request body: `getRequestBody()`

~~~java
try (InputStream input = exchange.getRequestBody()) {
    byte[] requestBytes = input.readNBytes(65);
    // This example keeps at most 65 bytes in the array.
}
~~~

This is a code snippet, importing `java.io.InputStream`. With a 64-byte body limit in the demo, reading up to **65 bytes** allows detecting an oversized body without reading the entire input unboundedly into the heap.

**Request body lifecycle:**

- `getRequestBody()` returns the `InputStream` of the request **currently being processed**, not the stream of the entire TCP connection.
- You should **read the entire request body** when appropriate and then close the stream. Closing early can prevent the underlying TCP connection from being reused; the JDK may only drain remaining bytes **up to an implementation-dependent limit**.
- Calling `getRequestBody()` multiple times returns the **same stream**, without rewinding to the beginning.
- Do not call `readAllBytes()` on input coming from the Internet without a body limit; an attacker can send very large or slow content.
- When an endpoint rejects early with 413/415, you may decide to close the connection instead of draining a large body, after sending the response/cleaning up per policy.
- If you have already consumed the body for logging, the business parser cannot automatically re-read it unless you buffer with a limit or recreate the stream via a filter.
- Do not skip reading the body if business logic doesn't need it and assume the connection is guaranteed to be reused; it depends on the JDK/how it's closed and the remaining size.

**Bounded payload reading example:**

~~~java
int maxBytes = 64 * 1024;
byte[] bounded = exchange.getRequestBody().readNBytes(maxBytes + 1);
if (bounded.length > maxBytes) {
    exchange.sendResponseHeaders(413, -1);
    return; // The outer try(exchange) will clean up.
}
~~~

This is an illustrative snippet, not standalone, but it clearly shows **counting actual bytes** instead of only checking Content-Length. Production may also need a streaming parser/sink, total deadline, and post-decompression limits.

## 6. Creating a response in the right order: headers → sendResponseHeaders → body

Typical lifecycle according to the API:

~~~text
(1) getRequestMethod() / getRequestURI() / getRequestHeaders()
(2) getRequestBody() -> consume & close (if appropriate)
(3) getResponseHeaders() -> set Content-Type, Cache-Control, Allow...
(4) sendResponseHeaders(status, responseLength)
(5) getResponseBody() -> write bytes -> close
(6) close HttpExchange (try-with-resources)
~~~

Core part:

~~~java
byte[] bytes = "Xin chào".getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);

try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

This snippet needs an open `exchange` and imports `StandardCharsets` and `OutputStream`. Calling `sendResponseHeaders` **before** `getResponseBody` is mandatory; trying to get the body stream first goes against the lifecycle.

**Response headers should be configured before sending:** after `sendResponseHeaders`, the response headers have already been sent; you should not keep adding `Content-Type`/`Allow` expecting the client to see them.

### 6.1. Why count bytes instead of String.length()?

`"café"` has 4 Java characters but **5 bytes** in UTF-8 (`c` `a` `f` = 3, `é` = 2). Therefore:

~~~java
String text = "café";
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
System.out.println(text.length());  // 4
System.out.println(bytes.length);   // 5
~~~

This is a snippet inside a method. With `sendResponseHeaders(200, 5)`, the handler must write **exactly 5 bytes**. Using `String.length()==4` as a fixed length will break response body framing, potentially causing `OutputStream.write(...)` to throw `IOException` and aborting the exchange.

### 6.2. Three modes of `sendResponseHeaders(status, length)`

| `responseLength` | Meaning in JDK HTTP server | How to finish |
| --- | --- | --- |
| **positive** (e.g., `5`) | Fixed response body length, must send **exactly N bytes** | Write N bytes then close `OutputStream` |
| **0** | Enables **chunked transfer encoding** (HTTP/1.1), arbitrary byte count | Write 0..N bytes then close to emit the final chunk |
| **-1** (or smaller) | **No response body** | Do not write a body; close exchange/output per lifecycle |

**Important syntax note:** `sendResponseHeaders(200, 0)` does **not** mean “return an empty response with fixed length 0”. It selects **chunked**. To have no body, use `-1`, especially with `204 No Content`, `304 Not Modified`, and appropriate HEAD responses.

**Exact fixed-length:** if you write more than N bytes, `OutputStream.write()` throws `IOException`; if you write fewer than N bytes, `OutputStream.close()` throws `IOException`. The JDK aborts the exchange and closes the underlying TCP connection in these situations.

**Do not set Content-Length manually for every response:** when using `sendResponseHeaders(status, bytes.length)`, the JDK manages framing/length accordingly. For HEAD, you can provide the **hypothetical GET** length header so the client understands the metadata, even though no body is sent; see the second demo.

### 6.3. Response with no body

~~~java
exchange.sendResponseHeaders(204, -1);
~~~

This is a snippet inside a handler. Do not write `"null"`, `"{}"`, or a newline as the body of a 204. When the client receives `204`, `HttpResponse.BodyHandlers.ofByteArray()` yields an empty array.

A `404`, `400`, or `405` response may contain a small error description body with an appropriate Content-Type. `HttpClient.send(...)` does not automatically throw an exception just for an HTTP error status; the client can read the status and body normally.

### 6.4. Response headers and `Allow`

Example of an unsupported method:

~~~java
exchange.getResponseHeaders().set("Allow", "GET");
byte[] message = "method not allowed".getBytes(StandardCharsets.UTF_8);
exchange.sendResponseHeaders(405, message.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(message);
}
~~~

If the resource exists but the method is not supported, the `Allow` header per HTTP semantics should list the available methods. Do not confuse `405` with `404`: one says **the resource may exist but the method is rejected**, while the other says **the target was not found or cannot be disclosed**.

## 7. Closing streams and closing the exchange: unbreakable rules

`HttpExchange` implements `AutoCloseable`, so use:

~~~java
@Override
public void handle(HttpExchange exchange) throws IOException {
    try (exchange) {
        // Read request, process, send response.
    }
}
~~~

This is a method snippet in an `HttpHandler`, requiring `import java.io.IOException`. JDK `HttpExchange.close()` will attempt to close the request `InputStream` and then the response `OutputStream`. According to Oracle Java 17:

- An exchange ends when both the request input stream and the response output stream are closed.
- Closing the response output stream also **implicitly closes** the request input if it is not yet closed.
- You should fully consume the request body before closing if you want the connection to be reusable.
- Failing to close the exchange can leak resources or prevent connection reuse.
- Calling `getRequestBody()`/`getResponseBody()` multiple times returns the same stream, not independent new streams.
- If you close the output stream yourself in try-with-resources and `exchange.close()` is called afterward, that repeated close is compatible with the cleanup model, but you must **not** use the exchange after closing it.

### 7.1. Why is closing critical for HTTP keep-alive?

~~~text
Client TCP connection
   |
   +-- HTTP request A → HttpExchange A → body/close
   |
   +-- HTTP request B → HttpExchange B → body/close
   |
   +-- HTTP request C → HttpExchange C → body/close
~~~

The JDK server can reuse a connection for multiple HTTP/1.1 requests, depending on framing, stream states, networking, and headers. If handler A does not consume/close the response output, B may be blocked or the connection may not be reused.

**Do not claim** “`try(exchange)` always reuses the connection”: when a handler leaves a large unread request body, the JDK cannot always drain all of it; it may close the connection to avoid framing corruption. A `Connection: close` response header can also force closing the connection after the exchange depending on the implementation.

### 7.2. Handling exceptions at the right time

~~~text
Before sendResponseHeaders:
  Still possible to choose an appropriate 4xx/5xx status.

After sendResponseHeaders:
  Status/headers are committed → cannot send a second 500 response
  on the same exchange when writing the body fails.
~~~

Some errors:

- `IOException` when the client disconnects or TCP write fails.
- Body decoder/validator reports invalid data: if the response is not yet committed, return `400 Bad Request`.
- File/database error: return `500 Internal Server Error` if the response is not yet committed and writing is still possible.
- Response stream under-writes/over-writes fixed length: `IOException` and the exchange may be aborted.
- Thread interrupted/cancellation: do not attempt to keep sending a response over broken streams.

**Anti-pattern:**

~~~java
try {
    exchange.sendResponseHeaders(200, declaredLength);
    exchange.getResponseBody().write(data);
} catch (Exception ex) {
    // WRONG: 200 headers may already be sent. Cannot send another valid 500.
    exchange.sendResponseHeaders(500, -1);
}
~~~

This snippet is intentionally **wrong**, not an example to run. Validate/prepare the response before committing; if writing fails after committing, log/cancel/close rather than writing a new HTTP response into the old body.

## 8. Standalone Demo #1: handler routing methods and managing one exchange

### 8.1. Example contract

The program has an HTTP server **bound only to loopback `127.0.0.1`** and creates the `/api/` context prefix. `ApiHandler.handle(...)` implements:

| Request | Result |
| --- | --- |
| `GET /api/hello?lang=vi` | `200`, UTF-8 body `Xin chào` |
| `POST /api/echo` with `text/plain` and body `abc` | `200`, body `echo:abc`; header `X-Handled-Method: POST` |
| `DELETE /api/hello` | `405`, header `Allow: GET` |
| `GET /api/empty` | `204`, no body |
| `POST /api/echo` with `application/json` | `415 Unsupported Media Type` |
| `POST /api/echo` with 65 bytes of text | `413 Content Too Large` due to the 64-byte demo limit |
| `GET /api/missing` | `404 Not Found` |

This is a **minimal controlled API**, not a production server. A POST missing Content-Type returns 415; the Java example only uses `startsWith("text/plain")` to illustrate a header check, **not** a complete media type parser (for example, `text/plain-malicious` also matches the prefix; production must parse according to standards).

### 8.2. File `HandlerExchangeLifecycleDemo.java`

~~~java
import com.sun.net.httpserver.*;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Locale;

public class HandlerExchangeLifecycleDemo {
    static final int MAX_BODY = 64;

    static class ApiHandler implements HttpHandler {
        @Override public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                String path = exchange.getRequestURI().getPath();
                String method = exchange.getRequestMethod();
                if (path.equals("/api/hello")) {
                    if (!method.equals("GET")) {
                        exchange.getResponseHeaders().set("Allow", "GET");
                        send(exchange, 405, "method not allowed");
                        return;
                    }
                    String rawQuery = exchange.getRequestURI().getRawQuery();
                    send(exchange, 200, rawQuery != null &&
                            rawQuery.equals("lang=en") ? "Hello" : "Xin chào");
                    return;
                }
                if (path.equals("/api/echo")) {
                    if (!method.equals("POST")) {
                        exchange.getResponseHeaders().set("Allow", "POST");
                        send(exchange, 405, "method not allowed");
                        return;
                    }
                    String type = exchange.getRequestHeaders()
                            .getFirst("Content-Type");
                    if (type == null || !type.toLowerCase(Locale.ROOT)
                            .startsWith("text/plain")) {
                        send(exchange, 415, "unsupported media type");
                        return;
                    }
                    byte[] body;
                    try (InputStream input = exchange.getRequestBody()) {
                        body = input.readNBytes(MAX_BODY + 1);
                    }
                    if (body.length > MAX_BODY) {
                        send(exchange, 413, "too large");
                        return;
                    }
                    exchange.getResponseHeaders().set("X-Handled-Method", method);
                    send(exchange, 200, "echo:" +
                            new String(body, StandardCharsets.UTF_8));
                    return;
                }
                if (path.equals("/api/empty")) {
                    if (!method.equals("GET")) {
                        exchange.getResponseHeaders().set("Allow", "GET");
                        send(exchange, 405, "method not allowed");
                        return;
                    }
                    exchange.sendResponseHeaders(204, -1);
                    return;
                }
                send(exchange, 404, "not found");
            }
        }

        static void send(HttpExchange exchange, int status, String text)
                throws IOException {
            byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(status,
                    bytes.length == 0 ? -1 : bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/api/", new ApiHandler());
        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3)).build();

            HttpResponse<String> greeting = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/hello?lang=vi"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("GET hello: " + greeting.statusCode()
                    + " | " + greeting.body());
            System.out.println("GET media: " + greeting.headers()
                    .firstValue("Content-Type").orElse("missing"));

            HttpResponse<String> echo = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/echo"))
                            .header("Content-Type", "text/plain; charset=UTF-8")
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.ofString("abc"))
                            .build(),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("POST echo: " + echo.statusCode()
                    + " | " + echo.body());
            System.out.println("POST method observed: " + echo.headers()
                    .firstValue("X-Handled-Method").orElse("missing"));

            HttpResponse<String> badMethod = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/hello"))
                            .timeout(Duration.ofSeconds(5))
                            .method("DELETE", HttpRequest.BodyPublishers.noBody())
                            .build(), HttpResponse.BodyHandlers.ofString());
            System.out.println("DELETE: " + badMethod.statusCode()
                    + " | Allow=" + badMethod.headers()
                    .firstValue("Allow").orElse("missing"));

            HttpResponse<byte[]> empty = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/empty"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("No content: " + empty.statusCode()
                    + " | bytes=" + empty.body().length);

            HttpResponse<String> wrong = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/echo"))
                            .header("Content-Type", "application/json")
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.ofString("{}"))
                            .build(), HttpResponse.BodyHandlers.ofString());
            System.out.println("Wrong media: " + wrong.statusCode());

            HttpResponse<String> huge = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/echo"))
                            .header("Content-Type", "text/plain")
                            .timeout(Duration.ofSeconds(5))
                            .POST(HttpRequest.BodyPublishers.ofString("x".repeat(65)))
                            .build(), HttpResponse.BodyHandlers.ofString());
            System.out.println("Oversized: " + huge.statusCode());

            HttpResponse<String> unknown = client.send(
                    HttpRequest.newBuilder(root.resolve("/api/missing"))
                            .timeout(Duration.ofSeconds(5)).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            System.out.println("Unknown route: " + unknown.statusCode());
        } finally {
            server.stop(0);
        }
    }
}
~~~

### 8.3. Compile, run, verified stdout

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HandlerExchangeLifecycleDemo.java
java --add-modules jdk.httpserver HandlerExchangeLifecycleDemo
~~~

**Stdout from an actual test run on OpenJDK 24 compiled with `--release 17`:**

~~~text
GET hello: 200 | Xin chào
GET media: text/plain; charset=UTF-8
POST echo: 200 | echo:abc
POST method observed: POST
DELETE: 405 | Allow=GET
No content: 204 | bytes=0
Wrong media: 415
Oversized: 413
Unknown route: 404
~~~

### 8.4. Explaining the order of actions in a request

**GET `/api/hello?lang=vi`:**

1. `HttpServer` selects the `/api/` context prefix.
2. `ApiHandler.handle(exchange)` is called with its own exchange.
3. The handler reads `getRequestURI().getPath()` and `getRequestMethod()`.
4. It checks the GET method; reads `getRawQuery()` but only compares against the exact demo value `lang=en`, otherwise returning the UTF-8 string `Xin chào`.
5. `send(...)` encodes the `String` into `byte[]` as UTF-8 and sets `Content-Type`.
6. `sendResponseHeaders(200, bytes.length)` commits status/headers and the fixed byte length.
7. `getResponseBody()` returns the output stream; the handler writes the exact bytes.
8. `OutputStream.close()` and `HttpExchange.close()` finish the exchange.
9. The client `HttpClient.send(...)` receives status 200 and the expected body.

**POST `/api/echo`:**

1. The handler verifies the path, POST method, and Content-Type header.
2. Reads up to 65 bytes from the request body; the payload `abc` is 3 bytes so it does not exceed 64.
3. Sets the response header `X-Handled-Method: POST` to demonstrate that the handler read the method.
4. Returns `echo:abc` with HTTP 200 and fixed byte length.
5. The client reads the status, body, and header — **the same exchange** holds the POST input and its corresponding response output.

**DELETE `/api/hello`:**

1. The resource path is valid, but the DELETE method is not supported.
2. The handler sets `Allow: GET` and sends 405.
3. The client receives status 405 normally. It is not a TCP error or exception because the client allows receiving HTTP error responses.

**GET `/api/empty`:** sends 204 with length -1; the client receives a byte array of length 0.

**POST over 64 bytes:** the handler detects that the request body exceeds the policy and returns 413. Closing the request body while unread data remains may prevent the server from **reusing the connection**; the demo does not attempt to prove keep-alive always works in this branch.

### 8.5. Why is the demo code not suitable for production?

- `Content-Type` is checked by prefix; it can falsely match `text/plain-malicious`. A standard media type parser/allowlist is needed.
- The query `lang=vi` has not gone through a complete URL query decoder; in production, percent-encoding, duplicate keys, and invalid characters must be handled.
- Reading 65 bytes only illustrates a hard cap for a small payload; real upload APIs need streaming quotas, deadlines, and content validation.
- There is no authentication/authorization, rate limiting, CSRF/cookie policy, security headers, access logs, or HTTP/TLS termination.
- The server binds only to loopback and lacks the security checks required if exposed to the Internet; do not simply replace `127.0.0.1` with `0.0.0.0` and consider it safe.
- The built-in `HttpServer` is not a full framework; if a production endpoint is needed, evaluate server/platform choices and security/observability requirements.
- A handler uses `getRequestURI().getPath()` as the path for routing; it does not automatically handle canonicalization, encoded separators, or path traversal if routes touch the filesystem.
- `server.stop(0)` in the lab stops the server immediately when the client test finishes; production usually wants graceful draining and a worker shutdown policy.
- All responses use `text/plain`; a real REST application may choose `application/json` or problem details according to its contract.

## 9. Standalone Demo #2: fixed-length, chunked, 204, and HEAD

In the JDK API, **the second argument of `sendResponseHeaders` is just as important as the status**. This example tests four exchanges handled by the same handler instance:

1. GET `/fixed`: returns `200`, UTF-8 body `café` = **5 bytes**, fixed length.
2. GET `/chunked`: calls `sendResponseHeaders(200, 0)` and writes `part-` + `two`, returning **8 bytes** with `Transfer-Encoding: chunked`.
3. GET `/none`: calls `sendResponseHeaders(204, -1)`, returning **0 bytes** and no chunked body.
4. HEAD `/head`: returns headers only; `Content-Length: 5` represents the hypothetical GET payload `hello`, but the body is **0 bytes**.
5. The handler uses `AtomicInteger` to count total `handle(exchange)` invocations: **4 times**.

Unlike the previous example, the server sets an explicit `ExecutorService` via `server.setExecutor(workers)`. Having one handler instance used multiple times illustrates that handling shared state must be thread-safe: `AtomicInteger` is safer than an `int count++` field when the server runs multiple concurrent requests.

### 9.1. File `HttpExchangeResponseModesDemo.java`

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class HttpExchangeResponseModesDemo {
    static final class ModeHandler implements HttpHandler {
        final AtomicInteger exchangeCount = new AtomicInteger();

        @Override public void handle(HttpExchange exchange) throws IOException {
            try (exchange) {
                exchangeCount.incrementAndGet();
                String path = exchange.getRequestURI().getPath();
                String method = exchange.getRequestMethod();
                if (path.equals("/fixed") && method.equals("GET")) {
                    byte[] body = "café".getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set("Content-Type",
                            "text/plain; charset=UTF-8");
                    exchange.getResponseHeaders().set("X-Mode", "fixed");
                    exchange.sendResponseHeaders(200, body.length);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write(body);
                    }
                    return;
                }
                if (path.equals("/chunked") && method.equals("GET")) {
                    exchange.getResponseHeaders().set("X-Mode", "chunked");
                    exchange.sendResponseHeaders(200, 0);
                    try (OutputStream out = exchange.getResponseBody()) {
                        out.write("part-".getBytes(StandardCharsets.US_ASCII));
                        out.write("two".getBytes(StandardCharsets.US_ASCII));
                    }
                    return;
                }
                if (path.equals("/none") && method.equals("GET")) {
                    exchange.sendResponseHeaders(204, -1);
                    return;
                }
                if (path.equals("/head") && method.equals("HEAD")) {
                    byte[] hypothetical = "hello".getBytes(StandardCharsets.UTF_8);
                    exchange.getResponseHeaders().set(
                            "Content-Length", Integer.toString(hypothetical.length));
                    exchange.getResponseHeaders().set("X-Mode", "head");
                    exchange.sendResponseHeaders(200, -1);
                    return;
                }
                byte[] error = "not found".getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(404, error.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(error);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        ModeHandler handler = new ModeHandler();
        server.createContext("/", handler);
        server.setExecutor(workers);
        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:" +
                    server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            for (String path : new String[]{"/fixed","/chunked","/none"}) {
                HttpRequest request = HttpRequest.newBuilder(root.resolve(path))
                        .timeout(Duration.ofSeconds(5)).GET().build();
                HttpResponse<byte[]> response = client.send(
                        request, HttpResponse.BodyHandlers.ofByteArray());
                System.out.println(path + " -> " + response.statusCode()
                        + " | bytes=" + response.body().length
                        + " | transfer=" + response.headers()
                                .firstValue("Transfer-Encoding").orElse("none"));
            }

            HttpRequest head = HttpRequest.newBuilder(root.resolve("/head"))
                    .timeout(Duration.ofSeconds(5))
                    .method("HEAD", HttpRequest.BodyPublishers.noBody())
                    .build();
            HttpResponse<byte[]> response = client.send(
                    head, HttpResponse.BodyHandlers.ofByteArray());
            System.out.println("/head -> " + response.statusCode()
                    + " | bytes=" + response.body().length
                    + " | Content-Length=" + response.headers()
                        .firstValue("Content-Length").orElse("missing"));
            System.out.println("Handler invocations: " +
                    handler.exchangeCount.get());
        } finally {
            server.stop(0);
            workers.shutdown();
            if (!workers.awaitTermination(2, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
~~~

Compile with the Java 17 API:

~~~bash
javac --release 17 -encoding UTF-8 --add-modules jdk.httpserver HttpExchangeResponseModesDemo.java
java --add-modules jdk.httpserver HttpExchangeResponseModesDemo
~~~

**Actually verified stdout:**

~~~text
/fixed -> 200 | bytes=5 | transfer=none
/chunked -> 200 | bytes=8 | transfer=chunked
/none -> 204 | bytes=0 | transfer=none
/head -> 200 | bytes=0 | Content-Length=5
Handler invocations: 4
~~~

### 9.2. Why do fixed and chunked share status 200 but differ in wire framing?

Both have response status 200:

~~~text
/fixed:
  sendResponseHeaders(200, 5) → exact 5 UTF-8 bytes
  Content-Length: 5
  body: café

/chunked:
  sendResponseHeaders(200, 0) → Transfer-Encoding: chunked
  logical body: part-two (8 bytes)
  wire message includes chunk sizes and chunk terminator

/none:
  sendResponseHeaders(204, -1) → no body

/head:
  HEAD request
  Content-Length: 5 (hypothetical GET representation length)
  sendResponseHeaders(200, -1) → no body sent
~~~

**Be careful:** the client's `HttpResponse<byte[]>.body().length` is the length of the **payload already deframed by the HTTP client**, not counting the chunk-size markers on the wire. Therefore, `/chunked` prints 8, which does not mean the entire HTTP/1.1 message on the wire is 8 bytes long.

### 9.3. Each request has its own exchange but shares the same handler object

Four client requests invoke `handle(exchange)` four times. A single shared `ModeHandler` object can serve multiple requests. The `AtomicInteger exchangeCount` field is an example of protected shared state; request-specific `path`, `method`, and `exchange` are all local variables, avoiding races between requests.

Because the program sends sequentially, stdout `count=4` is deterministic. A real concurrency test should send `sendAsync` to the same endpoint multiple times and synchronize with a `CountDownLatch`/barrier if you want to verify interleaving; do not treat a sequential example as proving thread safety for all application logic.

### 9.4. Avoiding misunderstandings about HEAD

**A HEAD response has no content**, but its headers can describe the representation corresponding to GET. In this example, the handler sets `Content-Length: 5` for the hypothetical payload `hello`, then calls `sendResponseHeaders(200,-1)`, and the client receives a zero-byte body. This does **not** violate the GET response's length framing, because HEAD has the semantics “headers as in GET, no content”.

If you want one endpoint to serve both GET and HEAD, make sure HEAD headers are consistent with GET where appropriate, and do not write a body for HEAD. Do not handle HEAD by writing a body and trusting the client to ignore it.

## 10. API call order: do/don't table

| Situation | Right | Easy-to-make mistake |
| --- | --- | --- |
| Read request method | `exchange.getRequestMethod()` | Guessing method from URI name or TCP port |
| Get request path | `exchange.getRequestURI().getPath()` | Parsing a custom raw request line string |
| Read header | `exchange.getRequestHeaders().getFirst(...)` | Trying to modify immutable request headers |
| Read small body | `readNBytes(limit+1)` and validate | Unbounded `readAllBytes()` on Internet input |
| Set response media type | `getResponseHeaders().set(...)` before sending | Setting after `sendResponseHeaders` and expecting the client to see it |
| Send status + fixed length | `sendResponseHeaders(200, bytes.length)` | `sendResponseHeaders(200, text.length())` |
| No body | `sendResponseHeaders(204,-1)` | Using `0` thinking it means fixed zero |
| Chunked | `sendResponseHeaders(200,0)` | Manually writing chunk lengths into OutputStream |
| Write response | `getResponseBody().write(bytes)` after sending | Calling getResponseBody before sending headers |
| Cleanup | `try(exchange)` and close output | Forgetting to close, leaving connections/resources hanging |
| Error after commit | Close/abort and log per policy | Calling `sendResponseHeaders(500,...)` again |
| Method error | 405 + Allow for existing resource | Returning 200 or 404 by default for all methods |
| No matching context | JDK server may return 404 itself | Assuming the handler is always called |
| Shared state | Atomic/lock/thread-safe executor policy | Global `HttpExchange current` field |

## 11. HttpServer executor and processing threads: is a handler concurrent?

`HttpServer.setExecutor(Executor executor)` determines the **thread execution context** for exchanges. It must be called before `start()`; `null` can be passed to use the default executor. If `Executors.newFixedThreadPool(n)` is used, multiple exchanges can be processed concurrently, so the handler **must be thread-safe**.

~~~java
ExecutorService workers = Executors.newFixedThreadPool(4);
HttpServer server = HttpServer.create(new InetSocketAddress(
        InetAddress.getByName("127.0.0.1"), 8080), 0);

server.createContext("/api/", new ApiHandler());
server.setExecutor(workers);
server.start();

try {
    // Server listens; the actual lifecycle is managed by the application.
} finally {
    server.stop(1);
    workers.shutdown();
}
~~~

This is an **architectural snippet**, not a standalone program: it requires imports for `ExecutorService`/`Executors`, `HttpServer`, `InetAddress`/`InetSocketAddress`, and a defined `ApiHandler` class. It illustrates the order of calling `setExecutor` before `start` and executor ownership, not an immediate start-then-stop pattern to copy into production.

**Notes:**

- One `HttpHandler` object is usually shared across many requests; do not put request body/response streams into instance fields.
- Do not perform long-running business I/O on a bounded number of threads; use deadlines and backpressure.
- Do not create a new unbounded thread pool per request, as that easily causes resource exhaustion.
- If `setExecutor(customExecutor)` is defined, the application must manage the executor lifecycle according to its ownership; `server.stop(...)` should not be assumed to shut down every custom executor automatically.
- `HttpServer.stop(delay)` blocks new requests, waits for existing exchanges to complete or up to the delay in seconds, and then closes TCP connections; a stopped server **cannot be reused/restarted**.
- Do not assume the JDK's default executor handles high load; read the docs and configure explicitly according to workload.
- Record metrics for queue length, active handlers, request latency, and rejection policy; do not log sensitive data.

### 11.1. An exchange is not an exclusive transaction

There are many concurrent requests, each with its own `HttpExchange`; at the same time, multiple exchanges can share a database, cache, the same handler, and the same backend. Closing `HttpExchange` **does not automatically roll back a database** or cancel all asynchronous application tasks. If you spawn background jobs, transactions/contexts must be managed separately; do not keep a reference to the exchange to write a response **after the exchange has closed**.

## 12. HttpContext, Filter, and Authenticator in an exchange

`HttpContext` is the attachment point for **middleware**:

~~~text
HttpServer
  |
  +--- HttpContext("/api/")
             |
             +--- Filter #1: request ID/metrics
             +--- Filter #2: request limits
             +--- Authenticator (if configured)
             |
             v
          ApiHandler.handle(exchange)
~~~

A filter can **attach an attribute** to `HttpExchange`:

~~~java
exchange.setAttribute("trace-id", "req-123");
Object trace = exchange.getAttribute("trace-id");
~~~

This is a code snippet. Attributes are for sharing internal data between filters and the handler **on the same exchange**, not HTTP headers sent by the client. Do not trust `trace-id` as access permission, and do not turn it into global mutable state outside the exchange lifecycle.

Related APIs:

- `exchange.getHttpContext()`: the context selected for the exchange.
- `exchange.getPrincipal()`: `HttpPrincipal` if the context has an authenticator and the request has been properly authenticated; otherwise it may be **null**.
- `exchange.getRemoteAddress()`: remote peer socket address; behind a reverse proxy this may be the **proxy IP**, not the real user IP.
- `exchange.getLocalAddress()`: the local address the request arrived on.
- `exchange.getProtocol()`: protocol string of the request, e.g., `HTTP/1.1`.
- `exchange.getAttribute(name)` / `setAttribute(name,value)`: attach data between filters/handler; should not be abused to store persistent session state.

**Do not use `getRemoteAddress()` instead of authentication.** If the server sits behind a reverse proxy, data from `Forwarded`/`X-Forwarded-For` must also be verified to come only from a trusted proxy; do not treat any client-supplied IP header as access authorization.

## 13. HTTP/HTTPS and limitations of the JDK built-in server

`com.sun.net.httpserver` provides both `HttpServer` and `HttpsServer`:

- `HttpServer` serves plain HTTP; if bound to a local port for testing, the client uses `http://127.0.0.1:port`.
- `HttpsServer` inherits the server's exchange-handling capabilities and configures TLS via `HttpsConfigurator`; `HttpsExchange` extends `HttpExchange` and provides `getSSLSession()`.
- These APIs are a **lightweight HTTP server provided by the JDK**, not a replacement for large server containers/frameworks if you need rich middleware, protocol upgrades, HTTP/2/3, distributed tracing, auth, and production hardening.
- Both examples above use **unencrypted** HTTP/1.1 on loopback to isolate the lesson on `HttpHandler`/`HttpExchange`. Do not send real credentials over `http://` on a public network.
- When deploying a production-facing API, you need TLS termination, certificate validation, reverse proxy, request limits, timeouts, security headers, auth/authorization, and proper observability.
- Do not assume `HttpsExchange` automatically authenticates a business user just because TLS succeeded; client certificates/mTLS and application identity must be designed separately.

### 13.1. Do not confuse client `HttpResponse` with server `HttpExchange`

| Client side | Server side |
| --- | --- |
| `java.net.http.HttpClient` | `com.sun.net.httpserver.HttpServer` |
| `HttpRequest` | `HttpExchange.getRequestMethod/getRequestURI/...` |
| `HttpResponse<T>` | `HttpExchange.getResponseHeaders/sendResponseHeaders/getResponseBody` |
| `BodyPublisher` sends request body | `HttpExchange.getRequestBody()` reads body |
| `BodyHandler<T>` consumes response body | `HttpExchange.getResponseBody()` writes response body |
| `client.send(...)` initiates HTTP exchange | `HttpHandler.handle(exchange)` handles dispatched exchange |

**Two different packages:** the Java 11+ client is in `java.net.http`; the embedded server is in `com.sun.net.httpserver` in the `jdk.httpserver` module. There is no standard “server.listen()” API in `HttpClient` and no `HttpResponse.BodyHandlers` in `HttpExchange`.

## 14. Status codes for a practical handler

| Situation | Appropriate HTTP status | Notes |
| --- | --- | --- |
| Successful GET, returning representation | `200 OK` | Correct Content-Type/charset/length |
| POST creates resource | `201 Created` | May set `Location` |
| POST accepted for async processing | `202 Accepted` | Does not mean the background job has finished |
| Successful delete, no content | `204 No Content` | `sendResponseHeaders(204,-1)` |
| Invalid JSON/query request | `400 Bad Request` | Do not log raw secrets |
| Unauthenticated | `401 Unauthorized` | Usually needs `WWW-Authenticate` per auth scheme |
| Authenticated but lacking permission | `403 Forbidden` | Do not rely on peer IP alone |
| Resource not found | `404 Not Found` | Do not leak private resources |
| Method not supported for resource | `405 Method Not Allowed` | Set `Allow` |
| Conflicting update | `409 Conflict` | Application semantics |
| Body larger than limit | `413 Content Too Large` | Stop reading/close connection in a controlled way |
| Unsupported Content-Type | `415 Unsupported Media Type` | Validate actual media type |
| Too many requests | `429 Too Many Requests` | Rate limit, optionally `Retry-After` |
| Server error before committing response | `500 Internal Server Error` | Avoid exposing stack traces |
| Server temporarily unavailable | `503 Service Unavailable` | Optionally `Retry-After` |

**An HTTP response does not equate to a business operation being guaranteed committed.** A handler returning 200 might still have background tasks; if an operation is critical, the API contract must properly distinguish accepted, committed, and idempotency.

## 15. Request body and security risks

### 15.1. Avoiding body memory exhaustion

~~~java
// DO NOT use on unbounded input from the Internet:
byte[] bytes = exchange.getRequestBody().readAllBytes();
~~~

Safer illustrative approach:

~~~java
int limit = 1024 * 1024; // 1 MiB
byte[] bytes = exchange.getRequestBody().readNBytes(limit + 1);
if (bytes.length > limit) {
    exchange.sendResponseHeaders(413, -1);
    return;
}
~~~

This is a code snippet; response body/closing must be managed in the outer scope. Do **not** treat this limit as protecting against all types of DoS: a malicious client can open many connections, hold requests open slowly, send large headers, send compressed payloads with a large decoded size, or cause CPU overload.

### 15.2. System-wide deadlines and quotas are needed

- HTTP request header size and header count: consider JDK/server/proxy configuration limits.
- Request body size: count actual bytes, do not only trust `Content-Length`.
- Time-to-first-header, body receive timeout, total request duration, and response write timeout.
- Connection count, pending requests, executor queue length, and active handler quota.
- JSON depth/nesting, decompression ratio, uploaded file scanning, and MIME/content validation.
- Authorization per resource, not just by method.
- Trusted proxy network and forwarded headers.
- Resource cleanup when the client disconnects/cancels.
- Rate limiting and circuit breakers for downstream dependencies.

JDK networking has some system properties for the built-in HTTP server (for example `sun.net.httpserver.maxReqHeaderSize`, `sun.net.httpserver.maxReqTime`, and `sun.net.httpserver.maxRspTime` in related documentation); **do not treat these properties as a portable Java SE contract across all vendors/runtimes**. Check against the deployed JDK, add security at the reverse proxy when needed, and test in practice.

### 15.3. Checking body and charset

`getRequestBody()` returns bytes. Only use `new String(bytes, StandardCharsets.UTF_8)` when the contract allows UTF-8. For JSON, parse according to standard and validate the schema; for binary, do not turn it into text. If a request contains `Content-Type: text/plain; charset=ISO-8859-1`, a demo forcing UTF-8 may not behave as expected; production needs a defined charset policy.

Likewise, if the response sends UTF-8, you must set `Content-Type` with the appropriate charset, compute `bytes.length`, and not write fewer bytes.

## 16. When does a request end?

This is an easy question to get wrong when first learning `HttpExchange`:

~~~text
Handler handle(...) returns
    DOES NOT automatically mean proper exchange cleanup if streams are not closed.

OutputStream.close()
    ends the response body, and also closes the request InputStream if still open.

HttpExchange.close()
    closes the request InputStream, then the response OutputStream;
    try-with-resources should be used.

TCP connection close
    is not necessarily the end of each exchange;
    HTTP/1.1 can use a persistent connection across multiple exchanges.
~~~

In the demo code, `try(exchange)` guarantees cleanup on every normal `return` or exception path. `try(OutputStream ...)` makes the exact byte length and the end of the response body explicit.

**A handler should not call `Thread.sleep(...)` for a long time after sending a response without closing the exchange**, because it holds resources unnecessarily. Nor should you keep `exchange` in a background task that outlives the request lifecycle; separate task results and business state from the response stream.

### 16.1. Client disconnects while the handler is writing

Behavior can be:

1. Client sends GET.
2. Server calls `sendResponseHeaders(200, n)`.
3. Client closes the TCP connection.
4. Handler calls `getResponseBody().write(bytes)` and receives `IOException`.
5. Handler closes the exchange in `finally/try-with-resources`, logs concisely, and cleans up resources.

**Do not** try to send status 500 after that IOException, because the 200 response was already committed or the connection is no longer usable. For business side effects, separate transactions/idempotency must be used if the client cancels mid-way.

## 17. Common mistakes with HttpHandler/HttpExchange

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using `String.length()` as fixed length | Counts UTF-16 units, not bytes | `String.getBytes(UTF_8).length` |
| Using `sendResponseHeaders(200,0)` to return empty body | `0` means chunked | `-1` when there is truly no body |
| Setting Content-Type after `sendResponseHeaders` | Headers are already committed | Set before sending |
| Calling `getResponseBody()` before sending headers | Wrong API lifecycle | `sendResponseHeaders` first |
| Not closing output/exchange | Resource leak, stuck connection | `try(exchange)` and close response |
| Not reading full request body yet expecting keep-alive | Unread bytes remain, JDK drains up to a limit | Consume appropriately or close connection |
| Using `readAllBytes()` on large uploads | Heap exhaustion | Bounded streaming/byte budget |
| Only checking `Content-Length` | Header may be missing/wrong | Enforce actual bytes received |
| Storing `HttpExchange` in a shared field | Race condition, lifetime leak | Request-local variables |
| Treating context path as a full REST router | Only prefix dispatch, no automatic method routing | Route by method/path in the handler |
| Choosing `createContext("/api")` expecting `/apix` not to match | Prefix is not necessarily segment-boundary | Use `/api/` and exact route checks |
| Returning 404 when resource exists but method is wrong | Loses 405 semantics | Return 405 and `Allow` |
| Returning 204 response with JSON body | Violates no-content semantics | `sendResponseHeaders(204,-1)` |
| Writing fewer/more fixed bytes | JDK throws IOException/aborts exchange | Compute byte length, write exact N |
| Sending 500 after sending 200 headers | Cannot commit two responses | Validate before commit, close on write failure |
| Not handling client disconnect | Exception leaks resources | Try-with-resources, bounded logging |
| Using global counter `int++` with fixedThreadPool | Race lost updates | `AtomicInteger`/lock |
| Using handler field `currentUser` | Shared request state | Local variable/context auth |
| Trusting `getRemoteAddress()` as real user | Reverse proxy turns remote into proxy IP | Trusted auth/forwarding policy |
| Assuming `getPrincipal()` always has a value | Only present when context auth is valid | Null check + auth design |
| Exposing `HttpServer` to public internet unprotected | Lacks TLS/rate limiting/hardening | Add gateway/security or choose suitable server |
| Not shutting down custom ExecutorService | Thread leak | `shutdown`/`awaitTermination` |
| Trying `server.start()` again after `stop` | Server is not reusable | Create a new HttpServer instance |
| Reading HTTP request line from raw Socket in handler | JDK already parsed HTTP | Use `HttpExchange` APIs |
| Assuming `java.net.http.HttpClient` is a server | Client side is a different module from server | Distinguish packages and roles |

## 18. Essential test suite for a handler

| Group | Case | Expectation |
| --- | --- | --- |
| Routing | Valid path, valid method | Handler is called, valid response status |
| Routing | Unmatched context | Server returns 404 |
| Routing | Similar prefix but different resource | Accurate router does not expose endpoint |
| Method | DELETE on GET-only endpoint | 405 and Allow |
| Body | Valid text POST | Reads bounded bytes, echo response |
| Body | POST missing/wrong Content-Type | 415 or defined policy |
| Body | Body exceeds limit | 413, no OOM |
| Body | Missing Content-Length | Bounded streaming still works if protocol allows |
| Body | Client sends body slowly | Deadline, does not hold thread indefinitely |
| Response | Fixed UTF-8 with multi-byte characters | Exact Content-Length bytes |
| Response | Chunked streaming | Client deframes, receives all bytes |
| Response | 204 | Zero bytes, no body sent |
| Response | HEAD | Valid headers, zero response body |
| Response | Client aborts mid-write | IOException is cleaned up |
| Response | Handler throws before commit | Appropriate error response if still possible |
| Response | Handler throws after commit | Does not send headers a second time |
| Concurrency | N concurrent requests | Thread-safe shared state |
| Shutdown | Stop while processing | Bounded stop and executor shutdown |
| Security | Unauthorized resource | 401/403, no data leaked |
| Security | Malformed query/URL/path | Reject/normalize per policy |
| Security | Oversized headers and large uploads | Bound memory/CPU/connections |
| Security | Input contains credentials | Do not log raw secrets |

### 18.1. Prefer deterministic tests

Both demos use port 0 so the OS picks a free port, bind loopback to avoid Internet exposure, and use a local `HttpClient` for reliable stdout. `HttpExchangeResponseModesDemo` uses `AtomicInteger` for the counter and calls sequentially, so output is predictable.

For concurrent tests, do not use `Thread.sleep(100)` and assume all handlers have finished running. Use `CountDownLatch`, `CompletableFuture`, a bounded executor, explicit deadlines, and guaranteed shutdown.

## 19. Exercises with answers

### Exercise 1 — Who calls handle?

You create an `HttpServer`, register `createContext("/hello", handler)`, and call `server.start()`. Who calls `handler.handle(exchange)`?

**Answer:** The JDK `HttpServer` receives and parses the HTTP request, selects the matching `HttpContext`, and dispatches to `HttpHandler.handle(exchange)`. The application **does not need to call handle itself** for normal requests.

### Exercise 2 — Exchange and TCP connection

Two HTTP/1.1 GETs travel over the same persistent TCP connection. Are they the same `HttpExchange`?

**Answer:** **No.** Each HTTP request/response exchange has its own `HttpExchange`; a TCP connection can be reused for multiple exchanges.

### Exercise 3 — Reading path and query

The client sends `GET /api/hello?lang=en`. Which APIs does the handler use to get the method, path, and raw query?

**Answer:** `getRequestMethod()`, `getRequestURI().getPath()`, and `getRequestURI().getRawQuery()`. `getRawQuery()` is not an automatically decoded query map.

### Exercise 4 — Should request headers be modified?

**Answer:** No. `getRequestHeaders()` returns read-only headers of the request. `getResponseHeaders()` allows preparing headers of the **response** before `sendResponseHeaders`.

### Exercise 5 — Wrong fixed length due to Unicode

`String text="café"` has `length()==4`, but its UTF-8 bytes are 5 long. What happens if you use `sendResponseHeaders(200,4)` and then write 5 bytes?

**Answer:** With fixed response length=4 and writing 5 bytes, the JDK may throw `IOException` and abort the exchange; you must use `bytes.length==5`.

### Exercise 6 — 0 and -1

How do `sendResponseHeaders(200,0)` and `sendResponseHeaders(204,-1)` differ?

**Answer:** `0` selects **chunked transfer encoding** with an arbitrary response length, whereas `-1` indicates **no response body**. Use `-1` for 204.

### Exercise 7 — Forgetting to close streams

The handler finishes writing the body but does not close `OutputStream` or `HttpExchange`. What can happen?

**Answer:** The exchange has not ended properly; connections/resources may be held or not reused. Use try-with-resources/close according to the lifecycle.

### Exercise 8 — Not reading the entire POST body

The handler reads the first 100 bytes and closes the exchange even though 10 MB remain unread. Is connection reuse guaranteed?

**Answer:** No. The JDK only tries to drain unread bytes up to an implementation-dependent limit; the TCP connection may have to be closed to avoid framing corruption.

### Exercise 9 — Route matching

Does `server.createContext("/api", handler)` automatically guarantee a `/apix` request will not enter the handler?

**Answer:** Not yet. Context matching is prefix-based, not a segment-aware router. Use an appropriate context prefix and check the full path.

### Exercise 10 — Error status after commit

The handler already called `sendResponseHeaders(200,...)`, then an IOException occurs while writing the body. Can it call `sendResponseHeaders(500,...)` next?

**Answer:** No. Response headers/status are already committed; clean up, log, and close/cancel the exchange.

### Exercise 11 — POST wrong media type

Resource `/api/echo` only accepts text/plain, and the client sends application/json. Which status is appropriate?

**Answer:** `415 Unsupported Media Type` per the demo contract; you must check the media type properly and not trust the header as proof of a valid payload.

### Exercise 12 — Unsupported method

Resource `/api/hello` exists, but the client sends DELETE. What should be returned?

**Answer:** `405 Method Not Allowed` with header `Allow: GET`; do not treat this as a TCP exception.

### Exercise 13 — Shared state

An `ApiHandler` serves 100 concurrent requests and uses a field `int count++`. Is `count=100` guaranteed?

**Answer:** No, `count++` is not atomic. Use `AtomicInteger.incrementAndGet()`, a lock, or an appropriate immutable state design.

### Exercise 14 — HEAD returning a body

The client sends HEAD, and the handler returns 200 with a 5-byte body `hello`. What is wrong?

**Answer:** HEAD must not have response content; headers may carry the hypothetical GET's Content-Length, but **do not write a body**.

### Exercise 15 — Client sees 404

When `HttpClient.send` returns an `HttpResponse` with status 404, is the `HttpServer` handler guaranteed to have been called?

**Answer:** Not necessarily. The JDK can return 404 when **no HttpContext is found**; if a context prefix matches but the handler does not recognize the resource, the handler itself returns 404.

### Exercise 16 — Null `getPrincipal()`

If a context has not configured an `Authenticator`, is `exchange.getPrincipal()` guaranteed to be the current user?

**Answer:** No. It can be **null**. Auth must be configured/validated per policy; do not treat the peer address as an authenticated principal.

### Exercise 17 — Stopping the server

After `HttpServer.stop(0)`, can `start()` be called again?

**Answer:** No. Per the API, a stopped server cannot be reused; a new server must be created.

### Exercise 18 — Is the response stream a raw TCP socket stream?

**Answer:** No. `exchange.getResponseBody()` is a stream attached by the HTTP server to **response framing**. You send representation bytes; you do not write `HTTP/1.1 200 OK\r\n...` into that stream yourself.

## 20. Pre-completion checklist

- [ ] I understand `HttpServer` bind/listen/dispatch via `HttpContext`.
- [ ] I understand `HttpHandler.handle(HttpExchange)` is called for **each HTTP exchange**.
- [ ] I do not keep a previous request's `HttpExchange` in shared fields.
- [ ] I know `getRequestMethod()`, `getRequestURI()`, `getRequestHeaders()`, and `getRequestBody()`.
- [ ] I know `getRequestHeaders()` is read-only and `getResponseHeaders()` is mutable.
- [ ] I route path and method accurately, without relying on default prefix matching.
- [ ] I limit the body by **actual bytes received**, not only `Content-Length`.
- [ ] I understand UTF-8 bytes can differ from `String.length()`.
- [ ] I set headers before `sendResponseHeaders`.
- [ ] I know `length > 0` = fixed exact bytes.
- [ ] I know `length == 0` = chunked, not fixed empty.
- [ ] I know `length == -1` = no response body.
- [ ] I close the response stream and exchange even when an exception occurs.
- [ ] I read/close the request body appropriately to avoid breaking reuse.
- [ ] I do not send a second 500 status after a 200 status has committed.
- [ ] I distinguish 404 vs 405, 413 vs 415, and 204 vs 200.
- [ ] I understand HEAD returns headers without sending a body.
- [ ] I know handler shared state must be thread-safe when using a custom executor.
- [ ] I shut down executors I own and call `server.stop(delay)` according to lifecycle.
- [ ] I do not use `getRemoteAddress` instead of authentication.
- [ ] I do not expose a built-in test server to the Internet without TLS/rate limiting/hardening.
- [ ] I have tests for fixed/chunked/no-body/HEAD and Unicode multi-byte response length.
- [ ] I compiled the examples with `javac --release 17` and ran them in a controlled environment.

## 21. Official documentation for reference

- [Java SE 17 — Module jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): module defining the JDK-specific HTTP server API.
- [Java SE 17 — Package com.sun.net.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/package-summary.html): HttpServer, HttpContext, HttpHandler, HttpExchange, Filter, and Authenticator.
- [Java SE 17 — HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): `handle(HttpExchange)`.
- [Java SE 17 — HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): official lifecycle, input/output streams, status/response length/close.
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): `create`, `createContext`, `setExecutor`, `start`, and `stop`.
- [Java SE 17 — HttpContext](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpContext.html): path mapping, filter chain, authentication.
- [Java SE 17 — Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): case-insensitive HTTP headers, `getFirst`, `set`.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP client used in both test programs.
- [Java SE 17 — HttpsExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsExchange.html): extension for HTTPS and SSL session.
- [Java SE 17 — Java Networking](https://docs.oracle.com/en/java/javase/17/core/java-networking.html): networking/server options and system properties.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): methods, statuses 204/404/405/413/415, HEAD, and content semantics.
- [RFC 9112 — HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing and response body length on the wire.

**Conclusion:** `HttpHandler` decides **how to handle a request**, while `HttpExchange` gives you **the full context of the request and the tools to produce the corresponding response**. The right lifecycle is always **read method/URI/headers/body → validate/route → set response headers → send status + proper body framing → close streams and exchange**. Once you understand fixed length, chunked, no-body, error timing, and shared handler concurrency, you have a solid foundation for writing and testing HTTP endpoints with JDK Java 17+.
