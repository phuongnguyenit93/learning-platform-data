# Sending Status Codes, Headers, Lengths, and Response Bodies

*Java Advance – networking · Group: JDK HTTP Server · Java 17+*

## 1. The Four Components of an HTTP Response

With the built-in HTTP server in the JDK (`com.sun.net.httpserver.HttpServer`), a handler author must decide **which status code to return, which headers to set, how many bytes long the body is, and how to write the body**. These four tasks are closely related but cannot substitute for one another:

1. **Status code** (`200`, `201`, `204`, `302`, `404`, `500`…) communicates the processing result according to HTTP semantics.
2. **Response headers** (`Content-Type`, `Cache-Control`, `Location`, `ETag`, custom headers…) provide metadata and instructions to the client.
3. **Response body length** in `sendResponseHeaders(status, responseLength)` controls **how the server sends and frames the body**: fixed-length, chunked, or no body.
4. **Response body** is written to the `OutputStream` from `exchange.getResponseBody()`; writing all bytes, closing the stream, and releasing the exchange are the handler's responsibility.

**Most important note for Java 17 `HttpExchange`:** the parameter `responseLength = 0` **does not mean "empty body"**. It requests **chunked transfer encoding**, meaning the body has a length not known in advance. To return a response **with no body**, use `responseLength = -1`.

~~~text
Client                        JDK HttpServer / HttpExchange
  |                                     |
  | ---- HTTP request ----------------> |  getRequestMethod(), getRequestURI()
  |                                     |  getRequestHeaders(), getRequestBody()
  |                                     |
  |                           Business logic / choose status
  |                                     |
  |                          getResponseHeaders().set/add(...)
  |                                     |
  |                          sendResponseHeaders(status, length)
  | <--- status line + headers -------- |
  |                                     |
  |                             getResponseBody()
  | <--- body bytes (if any) ---------- |  OutputStream.write(...)
  |                                     |
  |                    OutputStream.close() / exchange.close()
  | <--- body ends per framing -------- |
~~~

Inside a handler, **headers must be set before sending the status/headers**, and **`sendResponseHeaders` must be called before `getResponseBody`**. Once the response headers have been sent, there is no safe way to change the status from `200` to `500` for the same response.

## 2. Key Classes to Know in the jdk.httpserver Module

| Class / API | Role |
|---|---|
| `HttpServer` | Creates an HTTP server listening on an address/port; registers contexts/handlers |
| `HttpHandler` | Receives an `HttpExchange` and writes the response for that request |
| `HttpExchange` | Holds request metadata, request body, response headers, and status/body output |
| `Headers` | Multimap from header name to list of values; use `set` or `add` |
| `getResponseHeaders()` | Gets the headers **about to be sent** to the client to populate before committing |
| `sendResponseHeaders(int,long)` | Sends status + response headers and selects body framing |
| `getResponseBody()` | OutputStream for writing the body; must be closed when finished |
| `close()` | Ends the exchange / closes request and response streams per contract |
| `HttpsServer` | HTTPS variant of the lightweight server, requiring separate TLS configuration |

For the source used in examples:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.Headers;
~~~

The module in the JDK is **`jdk.httpserver`**, which differs from web framework libraries. It is a small server, useful for examples, internal testing, or simple HTTP services; **it does not come with full production framework features** (advanced routing, authentication, security filters, observability, request quotas…). The `com.sun.net.httpserver` classes are APIs exported by the `jdk.httpserver` module and should not be confused with internal `sun.*` packages.

## 3. Correct Sequence in an HttpHandler

Basic flow:

~~~text
handle(HttpExchange exchange)
          |
          v
Read method, URI, request headers/body (if needed)
          |
          v
Process logic and choose status/representation
          |
          v
exchange.getResponseHeaders().set(...)
          |
          v
exchange.sendResponseHeaders(status, responseLength)
          |
          v
try (OutputStream out = exchange.getResponseBody()) {
    out.write(payload);
}
          |
          v
OutputStream is closed -> exchange completes
~~~

**Do not reverse the order** between sending headers and writing the body. `HttpExchange.sendResponseHeaders(...)` may throw `IOException` if headers have already been sent or an I/O error occurs; `getResponseBody()`, per Javadoc, must be called **after** `sendResponseHeaders(...)`.

### 3.1. Fixed-Length Handler Skeleton

~~~java
// This is a snippet used inside HttpHandler.
byte[] payload = "Hello".getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders()
        .set("Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, payload.length);

try (OutputStream output = exchange.getResponseBody()) {
    output.write(payload);
}
~~~

Meaning:

- Choose `200 OK`.
- Set `Content-Type` before committing.
- Set the length to the **actual number of bytes** to be written.
- Use try-with-resources to guarantee closing the output stream even if an error occurs during processing; this is the step that completes the HTTP exchange.

Imports for `StandardCharsets` and `OutputStream` are needed in a complete program. **Do not treat this snippet as a standalone runnable Java file**; the full example is below.

### 3.2. Do Not Send a Status Code a Second Time

`sendResponseHeaders(...)` belongs to **a single response** of one `HttpExchange`. If it has already been called and an error occurs while writing the body, you cannot do:

~~~java
// Lifecycle error: response headers have already been sent.
// exchange.sendResponseHeaders(200, ...);
// write(...) throws IOException ...
exchange.sendResponseHeaders(500, -1); // Cannot send a new status line.
~~~

When an error occurs **before committing**, the handler can decide to return a properly structured error response. When an error occurs **after committing**, log it and close/abort the exchange; the client may see a truncated body or a connection error. The client having seen 200 does not guarantee the server finished sending the entire body.

## 4. Choosing Semantically Correct HTTP Status Codes

`sendResponseHeaders(rCode, responseLength)` takes an **integer code**. You do not need to manually write `HTTP/1.1 200 OK` into the response body: the JDK server sends the HTTP status line/headers according to the protocol. Choose the code based on the processing outcome, not on whether "the body has content".

| Status | Typical Meaning | Can Return a Body? |
|---|---|---|
| **200 OK** | GET/operation succeeded | Yes, depending on method/representation |
| **201 Created** | New resource created | May have a body; consider `Location` |
| **202 Accepted** | Request accepted for asynchronous processing | May have description/status; does **not** mean processing is complete |
| **204 No Content** | Succeeded with no response content | **No body** |
| **301/302** | Permanent/temporary redirect | Usually has `Location`; following is up to the client |
| **303 See Other** | View resource/result via another URI | May have metadata; has `Location` |
| **304 Not Modified** | Conditional cache | **No response content** |
| **400 Bad Request** | Malformed request / validation error | May return error JSON |
| **401 Unauthorized** | Valid authentication required | May return error body and `WWW-Authenticate` when appropriate |
| **403 Forbidden** | Not permitted to perform action | May return error body without leaking resources |
| **404 Not Found** | Resource not found | May return brief explanatory JSON/HTML |
| **405 Method Not Allowed** | Method not supported for resource | Requires `Allow` listing supported methods |
| **409 Conflict** | Resource state conflict | May have error JSON |
| **422 Unprocessable Content** | Structurally valid body but semantically unprocessable | May have filtered validation details |
| **429 Too Many Requests** | Rate limit | May have `Retry-After` |
| **500 Internal Server Error** | Unexpected server error | May have generic error body, **never** expose stack trace |
| **503 Service Unavailable** | Temporary overload/maintenance | May have `Retry-After` |

**Do not confuse HTTP status with Java exceptions.** A handler may complete I/O technically cleanly yet must return `404` because the resource does not exist. Returning `200` with body `{"error":"missing"}` just to "avoid client errors" often misleads monitoring, caching, retry policies, and API consumers.

### 4.1. Status Code and Response Body Are Two Independent Decisions

~~~text
200 + JSON body              -> success, with representation
201 + Location + JSON body   -> new resource created
204 + no body                -> success, no content
302 + Location               -> client can redirect
404 + error JSON             -> HTTP error with explanatory body
500 + safe error JSON        -> HTTP error, no internal details leaked
~~~

Do not use `-1` as a status code. `-1` is the **body length** value in the second parameter of `sendResponseHeaders` to indicate no body. The status code must still be a valid HTTP code such as `204` or `304`.

## 5. Setting Response Headers Properly

`exchange.getResponseHeaders()` returns a `Headers` object for the **response**, distinct from `exchange.getRequestHeaders()` (the client's request headers).

~~~java
Headers h = exchange.getResponseHeaders();
h.set("Content-Type", "application/json; charset=UTF-8");
h.set("Cache-Control", "no-store");
h.set("X-Request-Id", "demo-1");

// For headers that can legitimately repeat multiple times, use add:
h.add("Set-Cookie", "session=abc; HttpOnly; Secure; SameSite=Lax");
h.add("Set-Cookie", "theme=dark; Secure; SameSite=Lax");
~~~

This is a **snippet**; the cookie strings are illustrative only; the HTTP loopback demo below does not set real cookies or implement a login flow. Do not hardcode session IDs like `abc` in production. `Secure` only has its proper meaning when using HTTPS according to client rules.

### 5.1. set vs add

| API | Behavior |
|---|---|
| `headers.set(name, value)` | Replaces the existing list of values for the header with a single new value |
| `headers.add(name, value)` | Appends a value to the existing list |
| `headers.getFirst(name)` | Reads the first value for the header if present |
| `headers.get(name)` | Reads the list of values for the header name |
| `headers.remove(name)` | Removes the header from the set prepared to be sent |

HTTP header names are **case-insensitive** per protocol. For certain repeatable headers such as `Set-Cookie`, each field/value must be preserved appropriately; do not blindly join every header with commas by default.

**All headers must be set before `sendResponseHeaders`.** After headers have been sent, modifying `Headers` does not change the already-sent status/headers on the wire.

### 5.2. Commonly Important Headers

| Header | Role | Notes |
|---|---|---|
| `Content-Type` | Representation type and charset | `application/json; charset=UTF-8`, `text/plain; charset=UTF-8` |
| `Content-Length` | Number of body bytes per appropriate framing | For fixed-length, usually let `sendResponseHeaders` set it automatically |
| `Transfer-Encoding` | Wire encoding/framing method, e.g., `chunked` | With JDK HttpServer, let `responseLength=0` control it; do not set conflicting values manually |
| `Cache-Control` | Client/proxy caching rules | `no-store` is suitable for sensitive data |
| `Location` | Address of new resource / redirect | Used with 201 or redirects per semantics |
| `ETag` / `Last-Modified` | Metadata for conditional requests | `304` has specific rules |
| `Retry-After` | Retry guidance when appropriate | Does not replace client-side retry policy |
| `Allow` | Methods supported for the resource | Important with `405 Method Not Allowed` |
| `Vary` | Indicates request headers affecting representation selection | Prevents caching the wrong variant |
| `Content-Disposition` | Presentation / file download behavior | Be careful with user-supplied filenames |
| `X-Content-Type-Options: nosniff` | Restricts browser MIME sniffing in context | Does not replace authentication/authorization |
| `Access-Control-Allow-Origin` | Browser CORS policy for allowed origins | CORS is not server authentication |

### 5.3. Do Not Put Untrusted Data Directly into Headers

Header names and values must conform to HTTP syntax. If taking `Location`, filename, or custom headers from user input, **validate and encode according to context**. Do not allow input containing CR/LF to cause HTTP response splitting or protocol errors. Do not insert exception messages, tokens, passwords, session cookies, or stack traces into headers.

**CORS is not an authentication mechanism**: the server must still verify credentials and permissions. For `Access-Control-Allow-Origin`, choose a valid origin policy; do not blindly reflect all `Origin` values, especially when using credentials.

## 6. sendResponseHeaders(int status, long responseLength): Three Modes

This is the core of the lesson. The Java 17 Javadoc specifies:

| responseLength | How the Server Sends the Body | Handler Responsibility |
|---|---|---|
| **`> 0`** | **Fixed-length** | Must write **exactly** the declared number of bytes; more or fewer is an error |
| **`0`** | **Chunked transfer encoding** over HTTP/1.1 | Length unknown in advance; can write any number of bytes, **must close output stream to finish** |
| **`-1`** (or other negative per Javadoc parameters) | **No response body sent** | Do not write a body; end the exchange, suitable for HEAD/204/304… |

**`0` does not mean an empty body.** If a `byte[]` has length `0` and you call `sendResponseHeaders(200, bytes.length)`, Java 17 will choose **chunked** instead of "no body"; it may still transmit a data-empty chunked body, but the framing differs from a response with no body.

### 6.1. Choosing Fixed-Length

~~~java
byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders()
        .set("Content-Type", "application/json; charset=UTF-8");
exchange.sendResponseHeaders(200, bytes.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes); // Exactly bytes.length bytes.
}
~~~

`bytes.length` is the byte count, **not `json.length()`**. When using UTF-8, accented characters or emojis have a different byte count than the number of Java UTF-16 code units. For example:

~~~text
Text:                  Xin chào
Java String.length():  8
UTF-8 byte[].length:   9
~~~

If you call `sendResponseHeaders(200, 8)` but write all 9 UTF-8 bytes, `OutputStream.write` may throw `IOException` for **writing more bytes than declared**. If you declare 10 but only write 9, `OutputStream.close` may throw `IOException` for **writing too few bytes**. Per Javadoc, in both cases the exchange is aborted and the underlying TCP connection is closed.

### 6.2. What Fixed-Length Guarantees and Does Not Guarantee

Fixed-length gives the server/client clear framing and detects byte-count mismatches. However:

- It does not prove the bytes are valid JSON or that the content was parsed by the client.
- It does not prove the client received/processed the response successfully if the connection drops after the server writes.
- If compression such as gzip is used, you must count the **byte length of the representation after compression**, not the length of the original text.
- If the body is empty, consider **`-1`** rather than passing `0` thinking it means Content-Length 0.
- Avoid manually setting a `Content-Length` that conflicts with the `responseLength` parameter. Let the server implementation choose the header/framing based on the API, except in special cases like `HEAD` where metadata is needed.

## 7. Chunked: responseLength = 0

When the total byte count is not yet known or you want to emit data incrementally, you can call:

~~~java
exchange.getResponseHeaders()
        .set("Content-Type", "text/plain; charset=UTF-8");
exchange.sendResponseHeaders(200, 0); // 0 means chunked!

try (OutputStream out = exchange.getResponseBody()) {
    out.write("alpha-".getBytes(StandardCharsets.UTF_8));
    out.write("beta".getBytes(StandardCharsets.UTF_8));
}
~~~

In HTTP/1.1, the JDK server uses `Transfer-Encoding: chunked` for this case; the client receives the body `alpha-beta` without needing a fixed `Content-Length`. **Closing the output stream** is the operation that terminates the chunked response. If not closed, the client may wait forever for the final chunk / EOF logic.

### 7.1. Chunked Does Not Mean Each Write Becomes One Wire Chunk

Two `out.write(...)` calls in Java do not necessarily correspond to **exactly two HTTP chunks** on the wire. Buffering, `flush`, networking, and the implementation may split or coalesce data. An application protocol must not use server `write` boundaries as client message boundaries. If multiple records are needed, use JSON Lines / SSE / explicit protocol framing.

### 7.2. Flush Is Not Close

`out.flush()` may push data down to lower layers, but **does not mark the response as complete**. A chunked body typically ends when the stream is closed (the server emits the appropriate chunk terminator). For a streaming client, having read a few bytes does not mean the response is finished.

**Do not manually attach `Transfer-Encoding: chunked` and still call `sendResponseHeaders(status, fixedLength)`.** Two competing framing mechanisms cause undefined behavior or malformed responses; let the API manage it.

### 7.3. HTTP/1.0 and Unknown Framing

The `chunked` concept belongs to HTTP/1.1. Other HTTP protocols/versions do not necessarily use the same wire framing; do not build applications assuming `Transfer-Encoding` is always identical across every client/proxy. The test below uses `HttpURLConnection` with HTTP/1.1 to observe `Transfer-Encoding: chunked`, but **application data is still the body after HTTP framing is decoded**.

## 8. Sending No Body: responseLength = -1

When a response should not / need not have a body:

~~~java
exchange.getResponseHeaders()
        .set("Cache-Control", "no-store");
exchange.sendResponseHeaders(204, -1); // No Content, do not send body.
exchange.close();
~~~

`-1` indicates **no response body**. `exchange.close()` releases the exchange, including associated streams. The Javadoc emphasizes that even when no body is sent, the response stream/exchange must still be closed to complete it. Calling `exchange.close()` is the simple approach for the no-body branch.

Typical scenarios:

| Scenario | Is an HTTP Body Sent? | How to Set in JDK |
|---|---|---|
| `204 No Content` | No | `sendResponseHeaders(204, -1)` |
| `304 Not Modified` | No | `sendResponseHeaders(304, -1)` |
| `HEAD` | No, even though metadata describes GET representation | Set required headers then `sendResponseHeaders(200, -1)` |
| `205 Reset Content` | Per RFC must not have content | Use no-body and verify semantics |
| `1xx` informational | No response content per semantics | Do not treat 1xx as a final body response |
| `200` with no need to send representation | May have no body | `sendResponseHeaders(200, -1)`, though consider appropriate status |

**Do not attempt to write a body after `sendResponseHeaders(status, -1)`.** There is no response body to write; close the exchange.

### 8.1. HEAD: Content-Length Represents the Corresponding GET Body

Per HTTP, a response to `HEAD` **must not contain a body**, but may contain `Content-Length` indicating **the number of bytes that would have been sent if the corresponding request were GET** under similar conditions.

~~~java
byte[] wouldBeGetBody = "Xin chào".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=UTF-8");
exchange.getResponseHeaders().set(
        "Content-Length", String.valueOf(wouldBeGetBody.length));
exchange.sendResponseHeaders(200, -1); // HEAD: do not write body.
exchange.close();
~~~

In the demo, `Content-Length: 9` is **corresponding GET metadata**, and no actual 9 bytes are sent in the HEAD response. Do not call `sendResponseHeaders(200, 9)` and try to write 9 bytes on a HEAD request: that violates HEAD semantics, and the implementation may warn or error.

### 8.2. 204 and 304 Are Not the Same

`204 No Content` is a successful response with no content. `304 Not Modified` is a response to a conditional request telling the client/cache to reuse a stored representation; **it is not a new document being sent**. Both statuses have no body, but their metadata/semantics differ. With `304`, validators such as `ETag` and `Last-Modified` must be consistent with the resource when caching applies.

### 8.3. Why Not Use 0 to Mean No-Body?

Remember the **Java API parameter** rather than inferring from arithmetic:

~~~text
sendResponseHeaders(200, 9)    -> fixed-length, write exactly 9 bytes
sendResponseHeaders(200, 0)    -> chunked, write any number of bytes then close
sendResponseHeaders(204, -1)   -> do not send response body
sendResponseHeaders(304, -1)   -> do not send response body
sendResponseHeaders(200, -1)   -> do not send response body
~~~

For statuses that disallow a body such as 204/304, the JDK may adjust framing to comply with semantics instead of using chunked even if you pass 0, but do not rely on that implicit adjustment. **Explicitly choose -1** in your handler.

## 9. Error Responses Also Have Useful Bodies

**An HTTP error is not necessarily a connection error.** If a resource does not exist, the handler can return status `404` and a JSON body:

~~~java
byte[] error = "{\"error\":\"missing\"}"
        .getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
exchange.sendResponseHeaders(404, error.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(error);
}
~~~

The client reads:

~~~text
HTTP/1.1 404 Not Found
Content-Type: application/json; charset=UTF-8
Content-Length: 19

{"error":"missing"}
~~~

The headers/lines shown above are illustrative; `HttpServer` may add headers like `Date`, and header order/casing may vary. **Clients should not branch on the reason phrase** or depend on header ordering.

On the Java client side:

- `java.net.http.HttpClient` with `BodyHandlers.ofString()` normally returns an `HttpResponse<String>` with status 404 **and the JSON body**; HTTP 4xx does not automatically become an `IOException`.
- Legacy `HttpURLConnection` has `getResponseCode()` for the status; `getInputStream()` on 404 may throw `IOException`, whereas `getErrorStream()` can return the error body and **may be null** if there is no error data.

**Security:** error JSON should use stable error codes and minimal information; do not embed stack traces, SQL queries, sessions/tokens, sensitive filesystem paths, or internal details in the response body.

### 9.1. 201 Created with Location

When a handler creates a resource successfully, the response can set `Location`:

~~~java
exchange.getResponseHeaders().set("Location", "/items/42");
byte[] body = "{\"id\":42}".getBytes(StandardCharsets.UTF_8);
exchange.getResponseHeaders().set(
        "Content-Type", "application/json; charset=UTF-8");
exchange.sendResponseHeaders(201, body.length);
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);
}
~~~

The URI in `Location` may be relative depending on the protocol/use case. Validate input before building the URI/Location so you do not create an open redirect or header injection.

### 9.2. 405 Method Not Allowed with Allow

If an endpoint only accepts GET/HEAD but the client sends DELETE:

~~~java
exchange.getResponseHeaders().set("Allow", "GET, HEAD");
exchange.sendResponseHeaders(405, -1);
exchange.close();
~~~

`Allow` is an important header per HTTP semantics for 405. **Do not accept an unsupported method and still return 200** simply because the handler code did not check the method.

## 10. Complete Java 17+ Program: Six Response Types

The example uses **`HttpServer` on loopback `127.0.0.1` and a dynamic port**. There are no outbound Internet requests, no TLS certificates required, and no libraries outside the JDK.

Endpoints:

1. **`GET /fixed`:** status 200, `Content-Type` and custom `X-Lesson-Mode`, UTF-8 body `Xin chào` has **9 bytes** though the Java String has 8 code units; sent fixed-length.
2. **`GET /chunked`:** status 200, responseLength `0`, body written in two `write` calls combined into `alpha-beta`; client sees `Transfer-Encoding: chunked` over HTTP/1.1.
3. **`GET /empty`:** status 204, responseLength `-1`, no body.
4. **`HEAD /head`:** status 200, sets `Content-Length: 9` like the corresponding GET but sends no body.
5. **`GET /not-modified`:** status 304, no body.
6. **`GET /error`:** status 404, fixed-length JSON error; client reads via `HttpURLConnection.getErrorStream()`.

The client checks status, headers, and body and prints reproducible stdout. This demo uses legacy `HttpURLConnection` solely to observe the wire response; the server is written entirely with JDK `HttpServer`.

Create the file **`HttpResponseWriteDemo.java`**:

~~~java
import com.sun.net.httpserver.Headers;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;

public class HttpResponseWriteDemo {
    static final byte[] HELLO = "Xin chào".getBytes(StandardCharsets.UTF_8);

    private static void common(HttpExchange ex, String mode, String contentType) {
        Headers h = ex.getResponseHeaders();
        h.set("Content-Type", contentType);
        h.set("X-Lesson-Mode", mode);
        h.set("Cache-Control", "no-store");
    }

    private static void fixed(HttpExchange ex) throws IOException {
        common(ex, "fixed", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(200, HELLO.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(HELLO);
        }
    }

    private static void chunked(HttpExchange ex) throws IOException {
        common(ex, "chunked", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(200, 0);
        try (OutputStream out = ex.getResponseBody()) {
            out.write("alpha-".getBytes(StandardCharsets.UTF_8));
            out.write("beta".getBytes(StandardCharsets.UTF_8));
        }
    }

    private static void empty(HttpExchange ex) throws IOException {
        common(ex, "empty", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(204, -1);
        ex.close();
    }

    private static void head(HttpExchange ex) throws IOException {
        common(ex, "head", "text/plain; charset=UTF-8");
        ex.getResponseHeaders().set("Content-Length", String.valueOf(HELLO.length));
        ex.sendResponseHeaders(200, -1);
        ex.close();
    }

    private static void notModified(HttpExchange ex) throws IOException {
        common(ex, "not-modified", "text/plain; charset=UTF-8");
        ex.sendResponseHeaders(304, -1);
        ex.close();
    }

    private static void error(HttpExchange ex) throws IOException {
        byte[] payload = "{\"error\":\"missing\"}".getBytes(StandardCharsets.UTF_8);
        common(ex, "error", "application/json; charset=UTF-8");
        ex.sendResponseHeaders(404, payload.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(payload);
        }
    }

    private static void check(URI base, String path, String method)
            throws IOException {
        HttpURLConnection conn = (HttpURLConnection)
                base.resolve(path).toURL().openConnection();
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        try {
            int status = conn.getResponseCode();
            InputStream source = status >= 400
                    ? conn.getErrorStream() : conn.getInputStream();
            byte[] body;
            if (source == null) {
                body = new byte[0];
            } else {
                try (InputStream in = source) {
                    body = in.readAllBytes();
                }
            }
            switch (path) {
                case "fixed" -> System.out.println(
                        "fixed status=" + status
                        + " len=" + conn.getContentLengthLong()
                        + " mode=" + conn.getHeaderField("X-Lesson-Mode")
                        + " body=" + new String(body, StandardCharsets.UTF_8));
                case "chunked" -> System.out.println(
                        "chunked status=" + status
                        + " transfer=" + conn.getHeaderField("Transfer-Encoding")
                        + " len=" + conn.getContentLengthLong()
                        + " body=" + new String(body, StandardCharsets.UTF_8));
                case "empty" -> System.out.println(
                        "empty status=" + status + " bodyBytes=" + body.length);
                case "head" -> System.out.println(
                        "head status=" + status
                        + " advertised=" + conn.getContentLengthLong()
                        + " bodyBytes=" + body.length);
                case "not-modified" -> System.out.println(
                        "notModified status=" + status
                        + " bodyBytes=" + body.length);
                case "error" -> System.out.println(
                        "error status=" + status
                        + " type=" + conn.getHeaderField("Content-Type")
                        + " body=" + new String(body, StandardCharsets.UTF_8));
                default -> throw new IOException("Unexpected path");
            }
        } finally {
            conn.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/fixed", HttpResponseWriteDemo::fixed);
        server.createContext("/chunked", HttpResponseWriteDemo::chunked);
        server.createContext("/empty", HttpResponseWriteDemo::empty);
        server.createContext("/head", HttpResponseWriteDemo::head);
        server.createContext("/not-modified", HttpResponseWriteDemo::notModified);
        server.createContext("/error", HttpResponseWriteDemo::error);
        server.start();
        try {
            URI base = new URI("http", null, "127.0.0.1",
                    server.getAddress().getPort(), "/", null, null);
            check(base, "fixed", "GET");
            check(base, "chunked", "GET");
            check(base, "empty", "GET");
            check(base, "head", "HEAD");
            check(base, "not-modified", "GET");
            check(base, "error", "GET");
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run with **JDK 17+**:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpResponseWriteDemo.java
java --add-modules jdk.httpserver HttpResponseWriteDemo
~~~

**Exact verified stdout when compiled with `--release 17` and run on OpenJDK 24:**

~~~text
fixed status=200 len=9 mode=fixed body=Xin chào
chunked status=200 transfer=chunked len=-1 body=alpha-beta
empty status=204 bodyBytes=0
head status=200 advertised=9 bodyBytes=0
notModified status=304 bodyBytes=0
error status=404 type=application/json; charset=UTF-8 body={"error":"missing"}
~~~

### 10.1. Explaining Each Result

| Stdout | Meaning |
|---|---|
| `fixed status=200 len=9 mode=fixed body=Xin chào` | Server sends status 200, custom header, and 9 UTF-8 bytes as fixed-length |
| `chunked status=200 transfer=chunked len=-1 body=alpha-beta` | Client sees `Transfer-Encoding` header, no fixed `Content-Length`; body has been de-chunked |
| `empty status=204 bodyBytes=0` | 204 has no response body |
| `head status=200 advertised=9 bodyBytes=0` | HEAD advertises the GET representation length but **sends no body** |
| `notModified status=304 bodyBytes=0` | 304 is a response with no content |
| `error status=404 type=application/json; charset=UTF-8 body={"error":"missing"}` | 404 still has an error JSON body read by the client |

**Example scope:** uses only the HTTP/1.1 loopback JDK implementation; does not test TLS, HTTP/2, proxies, concurrent stress tests, or infinite streaming. The `Transfer-Encoding: chunked` result reflects the implementation/test case; applications must not rely on it to determine valid business data, and must instead follow HTTP semantics and reader APIs.

### 10.2. Why Is the UTF-8 byte[] Created Before sendResponseHeaders?

In the fixed-length branch, the server creates `byte[]` once and then **uses that exact `bytes.length` for both metadata and writing**. This avoids confusing `String.length()` and prevents changing charsets between length calculation and writing. If using gzip, you must build/count the length of the compressed bytes or choose chunked streaming so the length does not need to be known upfront.

### 10.3. Why Use -1 for No-Body and Still Close the Exchange?

`sendResponseHeaders(204,-1)` / `(304,-1)` / `HEAD -1` indicates no body is emitted. `ex.close()` releases resources and finishes the exchange. Not writing a body does not mean you do not need to complete the exchange. When there is a body, closing `OutputStream` via try-with-resources completes the response and releases resources.

### 10.4. Why Does the Client Have a Separate getErrorStream?

The server sends a **completely valid** HTTP 404 response with a JSON body. Legacy `HttpURLConnection.getInputStream()` may throw `IOException` on HTTP 4xx/5xx; therefore, the demo client code chooses `getErrorStream()` when `status >= 400`. This is a **client-side API** characteristic; it does not mean the server uses a different stream to write errors: the server still uses **the same `HttpExchange.getResponseBody()`** for every HTTP status that has a body.

## 11. Fixed-Length Errors: Writing Too Few or Too Many Bytes

The Java 17 Javadoc is very specific:

- `responseLength > 0` means the handler must write **exactly** that number of bytes.
- If **too many** are written, `OutputStream.write` throws `IOException`.
- If **too few** are written, `OutputStream.close()` throws `IOException`.
- In both cases, the exchange is aborted and the underlying TCP connection is closed.

~~~java
// Example NOT RUN in the main demo: intentional byte count mismatch.
byte[] body = "abc".getBytes(StandardCharsets.US_ASCII);
exchange.sendResponseHeaders(200, 4); // Declare 4 bytes.
try (OutputStream out = exchange.getResponseBody()) {
    out.write(body);                    // Only write 3 bytes.
} // close() may throw IOException because 1 byte is missing.
~~~

This is a **counterexample** of a protocol error, not a snippet recommended to run. Once the response has committed and a write error occurs, you cannot fix `Content-Length`/status on the wire. The client may receive a truncated response / abnormal EOF. In production, log the exception and check client download status rather than recording success just because status 200 left the server.

### 11.1. Avoid Using Character Count as Content-Length

~~~text
String s = "Xin chào";
s.length()                 = 8 Java UTF-16 code units
s.getBytes(UTF_8).length   = 9 UTF-8 bytes

sendResponseHeaders(200, 8)  + write(9 UTF-8 bytes) => wrong
sendResponseHeaders(200, 9)  + write(9 UTF-8 bytes) => correct
~~~

If a response contains emojis, Java `String.length()` may count **two UTF-16 code units** for a single Unicode supplementary code point; meanwhile, UTF-8 may use four bytes. **HTTP transfer length must always be measured in bytes**, not `String.length()` or the number of visible characters on screen.

## 12. Large Bodies or Incremental Generation: Choosing the Right Model

| Scenario | Response Mode | Why |
|---|---|---|
| Small JSON already encoded into `byte[]` | Fixed-length, `bytes.length` | Simple, exact, and full size is known |
| File with known byte size | Fixed-length if it can be written accurately | Client gets length metadata and detects truncation |
| Incrementally generated / unknown-size content | Chunked, length `0` | No need to buffer everything before writing |
| Long-lived SSE/log streaming | Chunked + controlled protocol flushing | Must design deadlines, heartbeats, and cancellation |
| `204`/`304`/`HEAD` responses | No-body, length `-1` | Complies with HTTP semantics |
| Small known error JSON | Fixed-length with proper 4xx/5xx status | Client can parse bounded error body |

**Chunked does not automatically make code asynchronous.** If a handler calls a slow data-generating function and then `write`, the handler thread remains occupied on the executor used by `HttpServer`. To serve many concurrent streaming exchanges, you must configure the executor, limit concurrency, and handle backpressure, timeouts, client disconnects, and bytes sent.

**Do not store unbounded chunks in RAM** before calling `write`. The advantage of chunked is sending bytes incrementally; if you already built a small body into a `byte[]`, fixed-length is simpler.

### 12.1. Streaming, Flushing, and Ending the Body

~~~java
exchange.sendResponseHeaders(200, 0);
try (OutputStream out = exchange.getResponseBody()) {
    for (byte[] chunk : chunks) {
        out.write(chunk);
        out.flush(); // May help client receive incrementally; does not end body.
    }
} // close() is what marks the end of the response.
~~~

This is a **snippet**: `chunks` is an application-provided source of `byte[]`; size/progress must be bounded, not turned into an infinite stream. `flush()` does not guarantee each call produces a single HTTP chunk that the client reads as one record. Use content framing such as newline-delimited JSON if logical messages must be distinguished.

### 12.2. Compression Changes the Length

If you want `Content-Encoding: gzip`:

- The bytes on the wire must be the **gzipped bytes**, not the pre-gzip String.
- With fixed-length, use the **byte count of the compressed representation**, not the source byte count.
- If compressing in a stream and total bytes are unknown upfront, you can choose chunked, but you must **properly close both the gzip wrapper and the response stream**, handling close order and buffering carefully.
- Add/control `Vary: Accept-Encoding` when the response representation depends on the request header; do not use gzip for every client without proper negotiation.
- Set `Content-Type` for the underlying media type; `Content-Encoding` describes the content coding applied to the representation.

**Do not manually set `Content-Length` to the uncompressed data length and then enable gzip**: the client will hit framing or parsing mismatches.

## 13. Resource Management of HttpExchange

The `HttpExchange` Javadoc states that an exchange is completed when both the request input stream and response output stream are closed. Closing the response output also closes the request input if it is still open; however, for more reliable TCP connection reuse, you should **consume valid request bodies before closing**. Closing while unread request body remains may render the connection unusable for subsequent exchanges.

### 13.1. Long Request Bodies Also Have Consequences

A handler processing POST may read `exchange.getRequestBody()`. If the server only reads a few bytes and then returns a response, `close()` may have to discard a bounded amount of bytes or prevent persistent connection reuse. Do not assume connection reuse will always happen.

Apply byte/time limits to the request body, avoid accepting overly large payloads, and choose a **reject early vs drain remaining body** policy suitable for the service. Do not read every request body with `readAllBytes()` without a quota.

### 13.2. OutputStream Must Be Closed

- For fixed-length/chunked: `try (OutputStream out = exchange.getResponseBody()) { ... }`.
- For no-body: `sendResponseHeaders(..., -1)` then `exchange.close()`.
- In real handlers, use `try/finally` to clean up resources even when an exception occurs, but **do not send a new response after the old response has committed**.

An abnormally terminated response may leave the client knowing status 200 while failing to read the body. **Application-level success must be counted after writing the body completes and downstream handling succeeds**, not merely after `sendResponseHeaders`.

### 13.3. Request Handlers and Exceptions

`HttpHandler.handle` can throw `IOException`. The system needs a mechanism to log/sanitize exceptions and prevent error responses from containing stack traces or credentials. If an error occurs **before sending headers**, an appropriate 500 status can be sent; if an error occurs **after headers**, end the exchange and record a partial response without trying to change the status.

## 14. Header Framing Issues

### 14.1. Content-Length and Transfer-Encoding Must Not Conflict

HTTP/1.1 has clear rules on message framing. **Do not both manually set a fixed `Content-Length` and manually attach `Transfer-Encoding: chunked` for the same body assuming every proxy/client will interpret it identically**. The least error-prone approach with JDK HttpServer:

- Fixed body: `sendResponseHeaders(status, bytes.length)`, **let the server handle `Content-Length`**.
- Unknown length: `sendResponseHeaders(status, 0)`, **let the server handle chunked framing**.
- No body: `sendResponseHeaders(status, -1)`, do not write a body.
- HEAD: may set `Content-Length` to describe the corresponding GET but still **send no body**.

### 14.2. Chunked Is HTTP Message Framing, Not Application Framing

The wire representation has chunk sizes, delimiters, and a terminating chunk. `HttpURLConnection` or `java.net.http.HttpClient` handles HTTP framing; application data only sees **the body bytes decoded from HTTP transfer framing**. If the server writes `alpha-` and `beta`, the client may read `alpha-beta` in one read or multiple reads. Do not attach protocol meaning to the number of Java writes or network packets.

### 14.3. Caching, 304, and Body Rules

`304` does not send a new body. When returning 304, metadata such as `ETag`, `Cache-Control`, `Last-Modified`, or `Vary` must follow conditional request semantics; not every GET can return 304 without checking request conditional headers.

`204` also sends no body, but it is not a "Not Modified" cache signal. Do not use 204 as a substitute for 304 or vice versa.

## 15. How Clients Observe Status/Headers/Body

You can use the modern Java 17 client:

~~~java
// Snippet: client and URI have been validly created.
HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.headers()
        .firstValue("Content-Type").orElse("unknown"));
System.out.println(response.body());
~~~

When `BodyHandlers.ofString()` completes successfully, the String has been read and decoded by the body subscriber, but **does not automatically prove valid business JSON**. The body of an HTTP 404/500 can also be read into a String by the handler without automatically throwing an exception just because `status >= 400`.

With `BodyHandlers.ofInputStream()`, `HttpResponse<InputStream>` may be returned after headers **before the entire body finishes transferring**; the caller must still read the stream to EOF/close. On the server side, `sendResponseHeaders` having sent headers does not mean the client has received/consumed the entire body.

Legacy `HttpURLConnection` provides `getResponseCode()`, `getHeaderField(...)`, `getInputStream()`, and `getErrorStream()`; the demo uses it to print `byte[]` and metadata, but **the HTTP error body path** must handle a nullable error stream. Do not treat `getErrorStream() == null` as proof that 404 can never have a body in all cases.

## 16. Security When Returning Status and Headers

| Risk | Mitigation |
|---|---|
| Leaking internal details via 500 response | Return stable error code, short message; log stack traces server-side with controls |
| Header injection / response splitting | Validate/encode data placed into `Location` and custom headers; reject CR/LF |
| Leaking tokens/PII via error body | Redact, return only fields permitted by API contract |
| Accidentally caching sensitive data | Consider `Cache-Control: no-store` and proper cache keys |
| Treating CORS as authentication | Do not; still verify session/token/authorization server-side |
| Overly large bodies | Limit request/response size, concurrency, latency, buffer size |
| Unclosed streams | try-with-resources and finally; design cancellation |
| Writing wrong Content-Length | Count actual `byte[]`, do not rely on character count or estimated JSON size |
| Browser MIME sniffing of content | Set proper `Content-Type` and `X-Content-Type-Options: nosniff` when appropriate |
| Open redirect | Validate `Location` and target URI before returning input-controlled redirects |

**JDK `HttpServer` is lightweight**; production use requires adding authentication, access control, rate limiting, TLS configuration, observability, graceful shutdown, thread pool policies, and appropriate reverse proxy/ingress security. The illustrative exercise only runs HTTP on loopback.

## 17. Common Mistakes and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Calling `sendResponseHeaders(200, 0)` expecting Content-Length 0 | `0` means chunked | For no-body, use `-1` |
| Fixed-length body returns client error/truncated | Counting `String.length()` instead of UTF-8 bytes | Calculate `byte[].length` |
| `OutputStream.close()` throws IOException | Wrote **fewer** bytes than fixed-length | Ensure exact byte count before closing |
| `OutputStream.write()` throws IOException | Wrote **more** bytes than fixed-length | Write exact length or use chunked |
| Client hangs waiting on chunked response | Forgot to close response body stream | try-with-resources |
| Sending 204 while still trying to write JSON | 204 has no response body | `sendResponseHeaders(204, -1)` |
| HEAD returns a body | Confusing metadata with representation body | Send headers only; `-1` |
| Using 304 as a success status with JSON | 304 is conditional cache, no content | Set appropriate validators/headers |
| Client receives `{"error":"..."}` body with status 200 | Server did not classify error | Return appropriate 4xx/5xx status |
| Setting Content-Length and chunked at the same time | Conflicting framing | Let `sendResponseHeaders` manage it |
| Modifying header after `sendResponseHeaders` and client doesn't see it | Headers already committed | Set all headers before calling |
| Trying to send status 500 after 200 response already started | Cannot send two status lines per exchange | Log partial response/close, fix flow |
| `getResponseBody()` before `sendResponseHeaders` | Wrong API order | Send headers first, then get stream |
| GET /error has status 404 but client sees no body | Legacy client only called `getInputStream` | Use `getErrorStream` when error body exists |
| Cannot log final byte | Stream error or client disconnect | Catch IOException, record `body_failed` status |
| Sending very large response causes OOM | Buffering entire body in heap | Stream chunked or fixed from file with quota |
| Compression breaks body | Length computed before compression | Count compressed bytes or use chunked |
| Sending body with 204 breaks parser | 204 has no payload | Do not parse/send body with 204 |
| Header contains CR/LF from input | Header injection or invalid syntax | Validate input and reject forbidden characters |

## 18. HttpHandler Design Checklist

**Before sending headers:** Are method/URI validated? Is there a request body to read or bound? Is the status code semantically correct? Are `Content-Type`, encoding, cache headers, `Location`/`Allow`/`ETag` ready if needed? Is untrusted input used in headers or error JSON?

**Choosing framing:** Does the body have a `byte[]` with a known length? If fixed-length, `responseLength = bytes.length > 0` and exact byte count must be written. If streaming a body of unknown length, use `0` (chunked). If sending no body, use `-1`. For HEAD/204/304, follow no-body rules. Do not manually create a `Content-Length` header competing with the API.

**While writing:** Is `sendResponseHeaders` called once before `getResponseBody`? Is try-with-resources used? Can the program report errors before committing? If an error occurs after committing, is there cleanup and partial response logging?

**After writing:** Is the stream closed and the exchange ended? Are there any request input or output leaks? Does monitoring distinguish status codes, byte counts, I/O failures, and client disconnects? Does the client verify the actual status/body after receiving?

## 19. Self-Check Questions

**1. Does `sendResponseHeaders(200, 0)` mean a 0-byte response body?** No. `0` selects chunked transfer encoding.

**2. To send a 204 response with no body, which `responseLength` should be used?** `-1`.

**3. What happens if `sendResponseHeaders(200, 12)` is called but only 10 bytes are written?** Closing the output stream may throw `IOException`; the exchange is aborted.

**4. What if `sendResponseHeaders(200, 12)` is called and 13 bytes are written?** `write` may throw `IOException` and abort the exchange.

**5. Why must `bytes.length` be used instead of `String.length()`?** HTTP length is measured in bytes of the sent representation; UTF-8 bytes differ from UTF-16 code units.

**6. Should you manually set `Transfer-Encoding: chunked` when `responseLength` is already `0`?** No; let the HTTP server manage framing.

**7. Is `out.flush()` the signal that ends a chunked body?** No. You must close the response body output stream.

**8. Can a `HEAD` response have `Content-Length` without a body?** Yes. The length describes the corresponding GET when appropriate.

**9. Does `304 Not Modified` carry a new JSON body?** No. It is a conditional cache response and sends no content.

**10. If an error occurs after calling `sendResponseHeaders(200, ...)`, can the status be changed to 500?** No. Headers are already committed.

**11. If the server returns 404 with JSON, does the Java server use `getErrorStream` to write the body?** No. The server still uses `getResponseBody`; `getErrorStream` is a legacy client API.

**12. When should status 201 be chosen?** When a resource has been successfully created per semantics; `Location` may be added.

**13. What header should be added for `405 Method Not Allowed`?** `Allow` listing the methods supported by the resource.

**14. Does a chunked response guarantee one `write` becomes one network chunk?** No. HTTP/TCP may split or coalesce data.

**15. Does running the example require Internet access or external libraries?** No. It uses loopback `127.0.0.1` and JDK module `jdk.httpserver`.

**16. Does `HttpServer` come with built-in production authentication/rate limiting?** Not in the full-framework sense; the application must design those policies additionally.

**17. Does chunked mean every client must see `Content-Length`?** No. HTTP/1.1 chunked typically has `Transfer-Encoding` instead of a fixed length.

**18. If no response body needs to be sent, do you still need to close the exchange?** Yes; ending the exchange releases resources.

## 20. Official Documentation

- [Java SE 17 – HttpExchange](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html): lifecycle, `getResponseHeaders`, `sendResponseHeaders`, `getResponseBody`, errors on writing wrong fixed length, close/connection reuse.
- [Java SE 17 – Headers](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html): `set`, `add`, `getFirst`, and case-insensitive header names.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): creating server, binding port, contexts, start/stop, executor.
- [Java SE 17 – HttpHandler](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html): handling an HTTP exchange.
- [Java SE 17 – HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html): HTTPS variant of the lightweight JDK HTTP server.
- [Java SE 17 – HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): observing status, headers, input/error stream from the client.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): modern HTTP client.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): status, representation, HEAD, 204/304, and request/response semantics.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): Content-Length, chunked transfer encoding, and framing.

**Conclusion:** In JDK `HttpServer`, first choose the **right status code**, set **response headers** on `getResponseHeaders()`, then call **`sendResponseHeaders(status, length)` exactly once** and write/close the body. Remember the mandatory convention: **positive length = exact byte count; 0 = chunked; -1 = no response body**. Follow HTTP semantics for HEAD/204/304, do not confuse Unicode character count with byte count, and always close the stream/exchange so the response truly completes.
