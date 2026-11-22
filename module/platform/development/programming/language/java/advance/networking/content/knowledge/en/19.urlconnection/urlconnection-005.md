# Fixed-length, chunked streaming, and content replay limitations with HttpURLConnection (Java 17+)

When sending an HTTP request body with `HttpURLConnection`, **two streaming modes** solve two different problems: `setFixedLengthStreamingMode(long)` is for a body whose **exact byte length is known**; `setChunkedStreamingMode(int)` is for a body whose **total length is unknown** when sending begins. Both allow sending the body through `OutputStream` without **`HttpURLConnection` buffering the entire body before transmission**.

The trade-off is critical: **when output streaming is enabled, `HttpURLConnection` cannot automatically handle HTTP authentication or redirects that require resending the request body** as it can when an internal buffer is available. If the server requires resending, reading the response may throw `java.net.HttpRetryException`. The client must decide according to application policy: whether retrying is allowed, whether the data source can be reopened, whether the redirect target is safe, whether the operation is idempotent, and whether the server has already performed a side effect.

This article belongs to the **URLConnection** group in **Java Advance - networking**, using the Java SE 17 API. The content covers framing mechanisms, configuring in the right order, the difference between UTF-8 character count and byte count, OutputStream control, replay limitations, 307/308 redirects, 401/407 authentication, response cleanup, and two Java 17+ programs using a loopback HTTP server to verify actual behavior.

## 1. Distinguishing URLConnection and HttpURLConnection

`java.net.URLConnection` is the abstract API for connecting to a resource by URL. `java.net.HttpURLConnection` extends it and adds HTTP-specific operations such as `setRequestMethod`, `getResponseCode`, `setFixedLengthStreamingMode`, and `setChunkedStreamingMode`. With `https://`, the object is typically `HttpsURLConnection`, which extends `HttpURLConnection` and adds TLS.

```text
java.net.URLConnection
          |
          v
java.net.HttpURLConnection
          |
          v
javax.net.ssl.HttpsURLConnection

URI -> URL -> openConnection() -> per-request HttpURLConnection
                                      |
                            configure BEFORE connect
                                      |
                   getOutputStream() / getInputStream()
```

Example where the application only works with HTTP(S):

```java
// Illustrative snippet; requires importing URI, URL, and HttpURLConnection.
HttpURLConnection conn = (HttpURLConnection)
        URI.create("https://api.example.test/upload")
                .toURL().openConnection();
```

**Do not unconditionally cast** a `file:`, `jar:`, or custom-protocol connection to `HttpURLConnection`. Only apply these HTTP methods when the source genuinely yields an appropriate HTTP URL connection.

One `HttpURLConnection` instance is used for **one HTTP request**. Do not reuse that same object to send another request after reading the response. Underlying keep-alive sockets may be implicitly shared by Java across different instances, but **one `HttpURLConnection` is not equivalent to a permanent socket**.

## 2. Three request body sending strategies and the cost of buffering

| Configuration approach | When to use | Common HTTP/1.1 framing | Strengths | Limitations |
| --- | --- | --- | --- | --- |
| No streaming mode selected | Small body, want to keep client auto-handling where supported | Determined by implementation once body is available | Easy to use; implementation can buffer content and handle replay | May have to hold the entire body in memory, especially for large uploads |
| `setFixedLengthStreamingMode(length)` | Know the **exact number of bytes** to write | `Content-Length: length` | No need to buffer the whole body; server knows length upfront | Wrong byte count causes IOException; no auto replay on auth/redirect |
| `setChunkedStreamingMode(chunklen)` | Total byte count is unknown | `Transfer-Encoding: chunked` | Can generate/send the body incrementally | Server/proxy must support chunked; no auto replay on auth/redirect |

**“Not buffering the entire body” does not mean “using no buffer at all.”** The implementation may still use I/O buffers, TLS encoders, TCP send buffers, or chunk buffers; the difference is that it is not forced to hold **the entire content** to know `Content-Length` before sending.

Do not immediately infer that one option is “X% faster”: throughput/latency depend on the network path, TLS, server, proxy, chunk size, body size, garbage collection, and backpressure. The primary goal is **correctness and memory bound**.

## 3. Fixed-length mode: exact byte-count contract

Java 17 API:

```java
void setFixedLengthStreamingMode(int contentLength);
void setFixedLengthStreamingMode(long contentLength);
```

These are API signatures for reference, not a standalone Java class. According to the `HttpURLConnection` Javadoc, fixed-length streaming enables sending a body without buffering the whole content when the length is already known. Calling `setFixedLengthStreamingMode(long)` is usually clearer and supports lengths exceeding the `int` range.

With HTTP/1.1, the application promises to write **exactly `contentLength` bytes**. If it writes **more**, the write operation may throw `IOException`; if it **closes `OutputStream` before writing enough**, closing may throw `IOException`. Do not assume Java will automatically pad with zero bytes or silently change `Content-Length`.

Illustrative example:

```java
// Snippet: conn is not yet connected, body is a prepared byte[].
conn.setDoOutput(true);
conn.setRequestMethod("POST");
conn.setFixedLengthStreamingMode((long) body.length);
try (OutputStream output = conn.getOutputStream()) {
    output.write(body);
}
```

**`body.length` here is the number of bytes**. Do not use the character count `text.length()` when data is UTF-8 encoded. If the data contains multi-byte characters, character count and byte count differ.

## 4. UTF-8: “Xin chào” is 8 characters but 9 bytes

A very practical bug:

```java
String text = "Xin chào";
int chars = text.length();                      // 8 UTF-16 code units
byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
int contentLength = bytes.length;                // 9 bytes
```

The snippet requires importing `StandardCharsets`. The character `à` uses multiple bytes in UTF-8; `String.length()` counts UTF-16 code units, not the bytes sent. With emoji, the difference can be even larger due to UTF-16 surrogate pairs.

**Wrong:**

```java
conn.setFixedLengthStreamingMode(text.length());
out.write(text.getBytes(StandardCharsets.UTF_8));
```

In this example, the client declares `Content-Length = 8` and then attempts to write 9 bytes; the fixed-length contract will not be met. Do not fix this by truncating the 9th byte: it may be part of a Unicode character, corrupting the payload.

**Right:** encode to bytes *once* when the body is small enough, and take `bytes.length`. If streaming from a file, obtain the length via `Files.size(path)` **only if the file bytes are sent as-is**; if gzip/transcoding/transformation is applied before sending, the input file size may **not** be the final output size.

## 5. Long-length and large files: avoiding int overflow

`setFixedLengthStreamingMode(long)` exists because the upload byte count can exceed `Integer.MAX_VALUE`. In Java 17:

```java
// Illustrative snippet; path is a Path pointing to a stable file.
long length = Files.size(path);
HttpURLConnection conn = (HttpURLConnection)
        uri.toURL().openConnection();
conn.setRequestMethod("PUT");
conn.setDoOutput(true);
conn.setFixedLengthStreamingMode(length);

try (InputStream input = Files.newInputStream(path);
     OutputStream output = conn.getOutputStream()) {
    input.transferTo(output);
}
```

This is **not a standalone program**: it needs imports, initialization of `path/uri`, timeouts, status/error handling, and `disconnect()` in `finally`. The example also assumes **the file does not change during upload**. If the file is truncated mid-way, output may close with too few bytes; if the file grows, it may write beyond `Content-Length`.

Choosing `long` does not guarantee the server accepts a file of arbitrary size: reverse proxies, APIs, load balancers, storage, and security policies still impose upload limits. Do not attempt to upload tens of GiB just because the Java API accepts `long`.

## 6. Chunked mode: no need to know total byte count upfront

API:

```java
void setChunkedStreamingMode(int chunklen);
```

Enable this mode when the total body size is unknown, such as generating data from a pipeline, reading a stream from an unsized source, or having to send parts as they are produced. With HTTP/1.1, the client uses **chunked transfer coding** to delimit the body at the protocol layer instead of sending a `Content-Length` for the entire request.

Example:

```java
// Snippet: conn is not yet connected, source provides data incrementally.
conn.setRequestMethod("POST");
conn.setDoOutput(true);
conn.setChunkedStreamingMode(8192);

try (InputStream input = source;
     OutputStream output = conn.getOutputStream()) {
    input.transferTo(output);
}
```

**`source` and `conn` must be declared**; the snippet does not run standalone.

- The `chunklen` value is a **chunk buffer/transfer size configuration**, not the number of chunks or the total body length.
- `setChunkedStreamingMode(0)` uses the implementation's default; you do not need to know it and should not hardcode “default is always 4,096 bytes” into business logic.
- Calling `write(100)` once and `write(100)` a second time **does not force** the server to observe two chunks containing exactly 100 bytes. Framing/chunk boundaries are determined by the transport handler.
- **Do not manually set `Content-Length`** as if both fixed-length and chunked were active simultaneously; they are two mutually exclusive framing models.
- Some HTTP servers/proxies do not support chunked uploads and may reject them or require `Content-Length`. When encountering errors, investigate capabilities before choosing a strategy.

## 7. Chunked transfer coding differs from application message framing

HTTP/1.1 on-the-wire illustration:

```http
POST /upload HTTP/1.1
Host: api.example.test
Transfer-Encoding: chunked
Content-Type: text/plain

5
hello
6
 world
0
```

The block above **only illustrates** how hexadecimal chunk sizes and the end marker work, not a raw string with the full CRLFs required for actual transmission. An HTTP server framework typically **decodes chunked transfer coding** before the application handler receives the `InputStream` body.

Therefore:

- One server-side `read(byte[])` does not correspond to “one HTTP chunk” on the wire.
- Splitting `out.write` in Java into 2 calls **does not** automatically create 2 business records.
- If the content is JSON/CSV/binary stream, you must still use the content's own parser/framing; chunked does not automatically delimit objects.
- Chunked is also **not** a `WebSocket` fragment, `TCP` packet, HTTP/2 stream, or backpressure API.
- HTTP/2 has its own DATA frames and stream-end mechanisms and does not use HTTP/1.1 `Transfer-Encoding: chunked`. Do not apply observations from an HTTP/1.1 `HttpURLConnection` request to all HTTP versions/client APIs.

In the runnable program below, the server reads the body into a complete byte sequence. It only verifies the transfer encoding and total byte count, **not** assuming the number of chunks or the size of each read.

## 8. Configuring in the right order before connecting

Common sequence:

```text
1. new URL / URI.toURL + openConnection()
2. setRequestMethod("POST"/"PUT")
3. setDoOutput(true)
4. setConnectTimeout(...), setReadTimeout(...)
5. setRequestProperty("Content-Type", ...)
6. Choose EXACTLY ONE mode:
      fixed-length if byte count is known
      chunked if unknown
7. getOutputStream()  -> connection may start
8. write all request body bytes
9. close OutputStream
10. getResponseCode(), getInputStream() or getErrorStream()
11. close response stream
12. disconnect() in finally
```

`setFixedLengthStreamingMode`/`setChunkedStreamingMode` **must be called before connected**. Actions such as `connect()`, `getOutputStream()`, `getInputStream()`, or `getResponseCode()` can trigger connection establishment, so the mode cannot be changed at that point.

Calling fixed and then chunked (or vice versa) on the same connection will cause `IllegalStateException`. Calling a setter after connected can also cause `IllegalStateException`. Conditions should be checked right at configuration time rather than relying on exceptions to decide streaming mode at runtime.

One `HttpURLConnection` is only for one request. To send a new request/retry, you must call `openConnection()` to create a new instance with the appropriate configuration and body source.

## 9. Why automatic resending is impossible when streaming

In non-streaming mode, the implementation may have a **full buffer of the request body**, enabling it to replay the body in certain supported authentication/redirect flows. When you enable streaming, the body may already have been sent straight to the network and **no copy remains in the client**.

```text
WITHOUT streaming:
  Application --> [possible full request-body buffer] --> server
                           |
                           +--> implementation may replay where allowed

WITH streaming:
  Application InputStream --> HttpURLConnection OutputStream --> server
             [one-shot?]      [no full body buffer in client]
                                   |
                 server returns 307 / 401 / 407
                                   |
                 client does NOT know how to recreate body
                                   |
                 HttpRetryException when reading response
```

**Do not equate “streaming mode” with “the body can never be replayed.”** A `byte[]` source or a stable file can be reopened and sent again **if the application does so intentionally**. Conversely, a stream from a camera, a pipe, content generation with side effects, an already-exhausted stream, or a modified file may be **non-replayable**.

The API cannot arbitrarily decide to re-upload a POST with side effects, change the URI on redirect, carry credentials to another domain, or reopen a stream you own. That is an **application-layer decision**, not a missing feature to work around by suppressing exceptions.

## 10. Critical limitation: HTTP 307/308 redirects

A commonly used redirect:

```http
HTTP/1.1 307 Temporary Redirect
Location: /target
```

With **307** or **308**, HTTP semantics require preserving the **HTTP method and request content** if following automatically. For a streaming POST, the client would need to recreate the body bytes to send to the new target. Java 17's `HttpURLConnection` does not do this automatically when streaming is enabled; reading the response may throw `HttpRetryException` even with `setInstanceFollowRedirects(true)`.

**Do not just see status 307 and immediately POST again**. A controlled workflow must check:

1. Is `Location` valid and within the origin/path allowlist?
2. Is redirecting from HTTPS to HTTP forbidden by policy?
3. Has the original server already performed a side effect before returning the redirect?
4. Can the body source be reopened to send **the exact same bytes**?
5. Are there an idempotency key, operation ID, retry budget, and overall deadline?
6. Are `Authorization` headers, cookies, client certificates, or sensitive data allowed to be sent to the new origin?
7. Is there a redirect loop or an overly long chain?

In sensitive systems, you may choose **not to auto-follow** any POST redirect; return a structured error or require a clearer application protocol.

## 11. HTTP 301/302/303 have different semantics from 307/308

| HTTP status | Key point to understand on redirect | Issue with streaming body |
| --- | --- | --- |
| 301 Moved Permanently | Has history and method-rewriting rules across client implementations; check RFC/contract | Do not assume the POST body is preserved across all clients |
| 302 Found | Some clients may change POST to GET per semantics/history | Do not send transaction-creating content to the new URI without policy |
| 303 See Other | Allows client to fetch another resource, typically via GET, per protocol | Does not mean “replay POST body” |
| 307 Temporary Redirect | **Does not change method** when following redirect | Re-POSTing requires recreating the body |
| 308 Permanent Redirect | **Does not change method** when following redirect | Requires retry decision and protecting the body source |

**In streaming mode, the general rule of `HttpURLConnection` remains that authentication and redirection are not handled automatically as they are with a buffered body.** Do not design an application around an accidental behavior of one status code or Java version without testing.

If the server intends a job-creation operation to happen only at one canonical endpoint, eliminating redirect paths for streaming POSTs is usually simpler and safer than trying to handle every redirect type on the client.

## 12. HTTP 401/407 authentication challenges also require replay

When a client sends a streaming POST to an endpoint requiring authentication, the server or proxy may return:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="private-api"
```

Or a proxy may return `407 Proxy Authentication Required`. An HTTP client with a buffered body may have a chance to perform the authentication challenge/response and resend the request per policy and credential provider. However, **in streaming mode**, `HttpURLConnection` cannot automatically resend the body if a retry is needed and may throw `HttpRetryException` when reading the response.

The application must choose:

- If the contract supports it, **authenticate upfront** using a secure mechanism instead of waiting for 401 after uploading a large body; do not let tokens be logged.
- When 401/407 occurs, determine whether it is a credential error, proxy configuration issue, or permissions issue; **do not retry indefinitely with the same wrong credentials**.
- When retrying, you must create a **new connection**, provide a fresh body source, and apply an appropriate policy; do not reuse a connected `HttpURLConnection`.
- Do not send origin A's `Authorization` header to origin B just because of a redirect. Prevent credential leakage and SSRF.
- With HTTPS, still verify TLS certificates and hostnames; do not use a trust-all manager to “fix” authentication.

You can read the HTTP error stream when the server sends useful details, but `getErrorStream()` **may be null**; bound the number of bytes read/logged and protect sensitive data.

## 13. HttpRetryException: a signal “needs handling,” not an auto-retry command

`java.net.HttpRetryException` extends `IOException`. When caught, the application can access:

```java
// Illustrative snippet in a catch block.
catch (HttpRetryException ex) {
    int status = ex.responseCode();
    String reason = ex.getReason();
    String location = ex.getLocation(); // may be null
    // Log metadata safely; decide per policy, do not blind retry.
}
```

In real code, you must open a proper try/catch structure, handle checked exceptions, and avoid leaking full URLs containing secrets. `getLocation()` provides redirect information **if present**, which does not mean the location is valid to access automatically.

Distinguish between:

- `HttpRetryException`: HTTP response requires further authentication/redirect action that the streaming client cannot automatically replay.
- `SocketTimeoutException`: connect/read wait timed out according to timeout settings; does not guarantee the server has not processed it.
- `ProtocolException`: inappropriate method, state, or protocol API usage.
- Other `IOException`: network/stream failure; remote state may be ambiguous.

An `HttpRetryException` does not mean “Java already retried and failed a second time” in a business sense. It indicates that **the automatic flow requiring replay cannot continue** in this mode.

## 14. Java 17+ demo #1: fixed-length and chunked on a loopback HTTP server

The file **`HttpStreamingModesDemo.java`** creates an `HttpServer` from the standard `jdk.httpserver` module, binds **only** to IPv4 loopback `127.0.0.1` and an ephemeral port. It receives two POSTs:

- `/upload/fixed`: the client sends `"Xin chào"` in UTF-8, computes the exact 9 bytes, calls `setFixedLengthStreamingMode((long) fixed.length)`, and writes the payload in **two `write` calls**.
- `/upload/chunked`: the client sends the 20-byte string `"part-A|part-B|part-C"` using `setChunkedStreamingMode(1024)`, also written in **two `write` calls**.
- The server decodes the body via the HTTP framework, records the `Content-Length` or `Transfer-Encoding` header, and returns `200 OK` with body `OK`. The client reads the response, closes streams, and calls `disconnect()`.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class HttpStreamingModesDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        AtomicInteger requests = new AtomicInteger();
        AtomicInteger fixedBytes = new AtomicInteger();
        AtomicInteger chunkedBytes = new AtomicInteger();
        AtomicReference<String> fixedLengthHeader =
                new AtomicReference<>();
        AtomicReference<String> fixedText = new AtomicReference<>();
        AtomicReference<String> transferEncoding =
                new AtomicReference<>();

        server.createContext("/upload", exchange -> {
            try {
                byte[] body;
                try (InputStream in = exchange.getRequestBody()) {
                    body = in.readAllBytes();
                }
                requests.incrementAndGet();
                if (exchange.getRequestURI().getPath()
                        .endsWith("/fixed")) {
                    fixedBytes.set(body.length);
                    fixedLengthHeader.set(exchange.getRequestHeaders()
                            .getFirst("Content-Length"));
                    fixedText.set(new String(
                            body, StandardCharsets.UTF_8));
                } else {
                    chunkedBytes.set(body.length);
                    transferEncoding.set(exchange.getRequestHeaders()
                            .getFirst("Transfer-Encoding"));
                }
                byte[] ok = "OK".getBytes(StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(200, ok.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(ok);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            String text = "Xin chào";
            byte[] fixed = text.getBytes(StandardCharsets.UTF_8);
            byte[] chunked = "part-A|part-B|part-C".getBytes(
                    StandardCharsets.UTF_8);

            HttpURLConnection one = (HttpURLConnection)
                    URI.create(base + "/upload/fixed")
                            .toURL().openConnection();
            boolean fixedOk;
            try {
                one.setRequestMethod("POST");
                one.setDoOutput(true);
                one.setConnectTimeout(3000);
                one.setReadTimeout(3000);
                one.setRequestProperty("Content-Type",
                        "text/plain; charset=UTF-8");
                one.setFixedLengthStreamingMode((long) fixed.length);
                try (OutputStream out = one.getOutputStream()) {
                    out.write(fixed, 0, 3);
                    out.write(fixed, 3, fixed.length - 3);
                }
                fixedOk = one.getResponseCode() == 200;
                try (InputStream in = one.getInputStream()) {
                    fixedOk &= "OK".equals(new String(
                            in.readAllBytes(), StandardCharsets.US_ASCII));
                }
            } finally {
                one.disconnect();
            }

            HttpURLConnection two = (HttpURLConnection)
                    URI.create(base + "/upload/chunked")
                            .toURL().openConnection();
            boolean chunkedOk;
            try {
                two.setRequestMethod("POST");
                two.setDoOutput(true);
                two.setConnectTimeout(3000);
                two.setReadTimeout(3000);
                two.setChunkedStreamingMode(1024);
                try (OutputStream out = two.getOutputStream()) {
                    out.write(chunked, 0, 6);
                    out.write(chunked, 6, chunked.length - 6);
                }
                chunkedOk = two.getResponseCode() == 200;
                try (InputStream in = two.getInputStream()) {
                    chunkedOk &= "OK".equals(new String(
                            in.readAllBytes(), StandardCharsets.US_ASCII));
                }
            } finally {
                two.disconnect();
            }

            System.out.println("Fixed body bytes: " + fixedBytes.get());
            System.out.println("Fixed Content-Length correct: "
                    + String.valueOf(fixed.length).equals(
                            fixedLengthHeader.get()));
            System.out.println("UTF-8 bytes exceed char count: "
                    + (fixed.length > text.length()));
            System.out.println("Fixed body matches: "
                    + text.equals(fixedText.get()));
            System.out.println("Chunked Transfer-Encoding: "
                    + "chunked".equalsIgnoreCase(
                            transferEncoding.get()));
            System.out.println("Chunked body bytes: "
                    + chunkedBytes.get());
            System.out.println("Responses OK: " + (fixedOk && chunkedOk));
            System.out.println("Requests served: " + requests.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Compile/run with JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 HttpStreamingModesDemo.java
java --add-modules jdk.httpserver HttpStreamingModesDemo
```

Verified stdout:

```text
Fixed body bytes: 9
Fixed Content-Length correct: true
UTF-8 bytes exceed char count: true
Fixed body matches: true
Chunked Transfer-Encoding: true
Chunked body bytes: 20
Responses OK: true
Requests served: 2
```

**Explanation of each assertion:**

1. `Fixed body bytes: 9` comes from the number of bytes the server **read**, not the char count of the Java `String`.
2. `Fixed Content-Length correct: true` confirms **the header sent by the HTTP client** has the right length. The client did not manually set the `Content-Length` header.
3. `UTF-8 bytes exceed char count` shows the discrepancy between UTF-8 and UTF-16 char count in Vietnamese text.
4. `Fixed body matches` confirms the payload arrived at the server without truncation or lost bytes when the client wrote in two calls.
5. `Chunked Transfer-Encoding: true` confirms the server received the `chunked` transfer coding header. The demo **does not count chunk frames** and does not treat two `write` calls as corresponding to two chunks.
6. `Chunked body bytes: 20` shows the HTTP server received the decoded body as contiguous bytes with the expected total size.
7. `Responses OK` requires both requests to have HTTP 200 and response body `OK`, rather than stopping at `getOutputStream().close()`.
8. `HttpURLConnection` is request-specific; the demo uses **two separate instances**, rather than reusing one object to switch upload modes.

This is a test of **Java API framing**, not a throughput benchmark, does not verify how many TCP sockets are reused, and does not represent Internet proxies/servers. The protocol does not guarantee that chunk boundaries observed on the server match write-call boundaries.

## 15. Java 17+ demo #2: 307 redirect rejected for automatic replay

The file **`StreamingRedirectDemo.java`** creates a loopback server with two endpoints:

1. `POST /redirect` reads the request body, increments the request counter, and returns `307 Temporary Redirect` with `Location: /target`.
2. `/target` counts how many requests actually arrive.

The client creates an `HttpURLConnection` for `/redirect`, enables `setInstanceFollowRedirects(true)` **while simultaneously** enabling `setFixedLengthStreamingMode(...)`, sends the POST body once, and calls `getInputStream()`.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpRetryException;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class StreamingRedirectDemo {
    public static void main(String[] args) throws Exception {
        InetAddress local = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        AtomicInteger redirectHits = new AtomicInteger();
        AtomicInteger targetHits = new AtomicInteger();

        server.createContext("/redirect", exchange -> {
            try {
                try (InputStream in = exchange.getRequestBody()) {
                    in.transferTo(OutputStream.nullOutputStream());
                }
                redirectHits.incrementAndGet();
                exchange.getResponseHeaders().set("Location", "/target");
                exchange.sendResponseHeaders(307, -1);
            } finally {
                exchange.close();
            }
        });
        server.createContext("/target", exchange -> {
            try {
                targetHits.incrementAndGet();
                byte[] ok = "TARGET".getBytes(
                        StandardCharsets.US_ASCII);
                exchange.sendResponseHeaders(200, ok.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(ok);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(workers);
        server.start();

        try {
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort()
                    + "/redirect").toURL();
            byte[] body = "change=1".getBytes(
                    StandardCharsets.UTF_8);
            HttpURLConnection conn = (HttpURLConnection)
                    url.openConnection();
            boolean retryNeeded = false;
            int code = -1;
            try {
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setInstanceFollowRedirects(true);
                conn.setConnectTimeout(3000);
                conn.setReadTimeout(3000);
                conn.setFixedLengthStreamingMode((long) body.length);
                try (OutputStream out = conn.getOutputStream()) {
                    out.write(body);
                }
                try (InputStream in = conn.getInputStream()) {
                    in.transferTo(OutputStream.nullOutputStream());
                } catch (HttpRetryException ex) {
                    retryNeeded = true;
                    code = ex.responseCode();
                }
            } finally {
                conn.disconnect();
            }
            System.out.println("Redirect needs caller handling: "
                    + retryNeeded);
            System.out.println("Redirect status: " + code);
            System.out.println("Redirect requests: "
                    + redirectHits.get());
            System.out.println("Target requests: " + targetHits.get());
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
```

Compile/run:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 StreamingRedirectDemo.java
java --add-modules jdk.httpserver StreamingRedirectDemo
```

Verified stdout:

```text
Redirect needs caller handling: true
Redirect status: 307
Redirect requests: 1
Target requests: 0
```

**Most important takeaway:** even though `setInstanceFollowRedirects(true)` is enabled, the server returns a redirect and Java still throws `HttpRetryException` because **streaming** is active. The counter `Target requests: 0` proves the client **did not automatically resend the body** to `/target`. Here, the application **intentionally does not retry** because it only aims to demonstrate the limitation and avoid uncontrolled behavior.

The code has a 307 *relative location* redirect but does not use `getLocation()` to automatically open the new URL. If a real application decides to perform a manual retry, it must resolve the URI against the base, check the scheme/host/port/path allowlist, have a replayable body source, and understand request semantics; **never access an arbitrary URL from the Location header by default**.

## 16. Errors from writing too few or too many bytes in fixed-length mode

Detecting a byte-count mismatch is **part of the API contract**, not optional:

```java
// Incorrect illustrative snippet: body is promised to be 10 bytes,
// but the caller only writes 9 bytes and closes output.
conn.setFixedLengthStreamingMode(10L);
try (OutputStream output = conn.getOutputStream()) {
    output.write(new byte[9]);
} // IOException due to not supplying enough declared bytes.
```

When writing **too many** bytes, `write` may throw `IOException` as soon as the allowed byte count is exceeded. When writing **too few** bytes, `close` may throw `IOException`. Therefore, do not put `try` only around `getResponseCode()`; you must catch/clean up exceptions on the **body-writing path**.

Sources of mismatch:

- Computing `text.length()` instead of `text.getBytes(UTF_8).length`.
- Using `Files.size` before the file is modified during upload.
- Computing data size **before** gzip/base64/transcoding while sending data **after** transformation.
- A producer fails mid-way and closes the stream as if all bytes had been sent.
- Using wrong offset/length or ignoring partial reads from the source.
- Arithmetic/type conversion causing `int` overflow for large files.

**Do not immediately auto-retry** when bytes are missing: the server may have received a partial payload and its processing state is unclear, especially if the server streams/parses the upload incrementally. An upload session/operation ID API is needed to know which parts the server retained.

## 17. Does chunked avoid “reading everything at once” during upload?

It can reduce the need to buffer the entire content, but the upload still needs a **data producer** with the right lifetime:

```java
// Snippet; input source and conn are already configured.
try (InputStream input = source;
     OutputStream output = conn.getOutputStream()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = input.read(buffer)) != -1) {
        output.write(buffer, 0, n);
    }
}
```

Here `buffer` holds at most 8192 bytes per iteration. However:

1. `InputStream.read` may return any positive number of bytes up to the buffer length, not guaranteeing “exactly one chunk.”
2. `OutputStream.write` may block if the network/server is slow; *streaming* does not automatically create an async non-blocking producer.
3. With a non-replayable source, when 401/307 occurs, there is no way to automatically “rewind” an already-consumed `InputStream`.
4. Closing `OutputStream` signals the end of the body according to framing; do not forget to close when the producer reaches EOF.
5. Cancellation/deadlines/byte caps are needed so you do not read endlessly from an untrusted source.
6. Content may be compressed/encoded or transformed in the pipeline; chunked framing does not define JSON record boundaries or checksums.

**Streaming upload does not mean streaming response**: sending via `getOutputStream` and reading the response via `getInputStream/getErrorStream` are separate I/O phases and must be cleaned up separately.

## 18. Response information and handling HTTP statuses/errors

A safe HTTP routine must observe the status:

```java
// Illustrative snippet: request body has been sent, conn is active.
int status = conn.getResponseCode();
InputStream responseStream = status >= 400
        ? conn.getErrorStream()
        : conn.getInputStream();
if (responseStream != null) {
    try (InputStream in = responseStream) {
        // Read with a maximum size limit and the right charset.
    }
}
```

In practice, `getResponseCode()`/`getInputStream()` can throw exceptions related to streaming redirects/auth, so you must have separate catch blocks for `HttpRetryException` and `IOException`. As for the error stream, it **can be null** if the server sends no body or an error occurs before a response; do not call `read` on null.

`HttpURLConnection.getInputStream()` may throw `IOException` for error HTTP statuses, while response headers/status can still be useful. Do not neglect reading/closing the response; the backend may hold connection resources longer if the stream is abandoned.

Bound the size of **the error body as well**: an erroring server might return huge HTML or data containing secrets. Do not log unbounded raw responses; parse/redact according to `Content-Type`/encoding and policy.

In the two loopback programs, the response body is only a few bytes, so `InputStream.readAllBytes()` is reasonable. In production, do not use `readAllBytes()` for unbounded Internet content.

## 19. connectTimeout, readTimeout, and upload deadline

Several timeouts:

- `setConnectTimeout(ms)` limits the time to establish the network connection; it is **not** the overall upload deadline.
- `setReadTimeout(ms)` limits the time spent waiting to read data from `InputStream` per the API contract; it is **not** the total time budget for a large body.
- `OutputStream.write(...)` can block due to network backpressure, TLS buffering, and provider behavior; do not assume `readTimeout` controls total write time.
- A large file might send each chunk in a few seconds while **the entire upload** takes minutes or hours. An application-level deadline or controlled async/cancel structure is needed when SLAs require it.
- If a timeout occurs **after the server has received all or part of the request**, do not infer from the exception that the server has not processed anything.

For critical operations, use an idempotency key or upload session ID in the API to query status. If the user cancels an upload, a separate server-side cleanup/session-cancel mechanism is needed; closing TCP does not automatically delete all temporary chunks or database records.

## 20. Security in manual redirects and authentication

When streaming, an application might be tempted to write:

```java
// Anti-pattern: DO NOT automatically resend every POST to Location.
String location = ex.getLocation();
HttpURLConnection another = (HttpURLConnection)
        URI.create(location).toURL().openConnection();
// ... resend original body + Authorization (WRONG without validation).
```

This is a **warning snippet**, not code to use. A `Location` controlled by a server/proxy could point to an internal address, metadata endpoint, unexpected `file` scheme, different domain, or non-TLS HTTP. If the client carries `Authorization`/cookies/PII along, there is a risk of **SSRF and credential leakage**.

Manual following must have an explicit policy:

1. Verify the scheme is only an allowed HTTP(S) scheme, and host/port/path are on the allowlist.
2. Block HTTPS → HTTP downgrades when sensitive data is present.
3. Define redirect method semantics: 307/308 preserve method/body; 301/302/303 must be handled per API contract.
4. Do not pass credentials or cookies from the old origin to a new origin unless permitted.
5. Limit the number of redirects and detect loops.
6. Only replay if the body can be recreated identically, the operation is allowed to retry, and an idempotency key/operation ID is present.
7. Cap total time, byte volume, and attempt count; maintain logs/tracing without logging secrets.
8. Do not work around 401/407 by disabling TLS verification/trust-all.

**An HTTP redirect does not prove the new endpoint is safe or that the previous business operation was not processed.**

## 21. “Replayable” is a property of both the content source and the business operation

| Body source | Can it replay identical content? | How to handle |
| --- | --- | --- |
| Immutable `byte[]` for the operation | Usually yes | Create a new connection, write bytes again if method/policy allows |
| Stable file with locked checksum | Possible | Open a new stream, verify length/hash/version before retrying |
| File modified by user during upload | Not guaranteed | Versioning/locking/snapshot; do not reuse old byte count |
| One-shot `InputStream` from pipe/network | Usually no | Do not blind retry; use bounded spool or resumable protocol |
| Nondeterministic compression/transcoding producer | Not guaranteed byte-for-byte | Snapshot output or design semantic idempotency instead of byte equality |
| Request generates a new transaction ID per call | Body may be replayable, **operation lacks the same identity** | Keep idempotency key/operation ID stable |
| Payment/order POST committed before response was lost | Replaying bytes **is not automatically safe** | Query status, use server-side idempotency |

Three independent questions:

1. **Technical:** Can the exact same bytes be recreated?
2. **HTTP semantics:** Do the method and redirect/auth allow retrying?
3. **Business:** Will resending the request cause an additional side effect?

Having only question 1 be true **is not enough** to decide to retry. A completely replayable file can still be POSTed to a job-creation endpoint **twice**. Server-side deduplication and confirmation/reconciliation mechanisms are required.

## 22. Safer retries with idempotency and resumable uploads

A server accepting large uploads typically provides an upload-session API:

```text
POST /uploads                   -> 201, uploadId=U123
PUT  /uploads/U123/parts/1      -> upload segment with checksum
PUT  /uploads/U123/parts/2      -> upload segment with checksum
GET  /uploads/U123              -> current committed segments/status
POST /uploads/U123/complete     -> finalized artifact
DELETE /uploads/U123            -> cancel, per policy
```

This is a **protocol example**, not a built-in Java endpoint. Combine:

- **Idempotency key** identifying the logical create/complete operation; the server persists durable state alongside the side effect.
- **Part number/offset + checksum** so the server knows which segments were received without resending the whole file.
- **Conditional update/ETag/version** to prevent erroneous overwrites.
- **Status endpoint** enabling reconciliation after timeouts, auth challenges, or connection resets.
- **TTL and quota** for incomplete upload sessions.
- **Authorization** for owner, tenant, size, content type, MIME sniffing, and virus scanning as needed.
- **Retry budget/backoff** to avoid overloading the server when thousands of clients retry simultaneously.

Choose fixed-length when the exact segment byte count is known, chunked when it is not; however, **safe retryability comes primarily from protocol/server design**, not from a setter on `HttpURLConnection`.

## 23. Relationship with modern Java 17 HttpClient

This article focuses on `HttpURLConnection` because that is where these specific streaming mode setters live. Java 17 also has `java.net.http.HttpClient` and `HttpRequest.BodyPublisher`:

| API | How body is sent | How length is provided |
| --- | --- | --- |
| `HttpURLConnection` | `getOutputStream()` + choosing fixed/chunked mode | `setFixedLengthStreamingMode` / `setChunkedStreamingMode` |
| `java.net.http.HttpClient` | `HttpRequest.BodyPublishers.ofString/ofByteArray/ofFile/ofInputStream/fromPublisher` | `BodyPublisher.contentLength()` and publisher semantics |
| `HttpsURLConnection` | `HttpURLConnection` API combined with TLS | Same fixed/chunked behavior as the `URLConnection` family |

Do not copy the `setChunkedStreamingMode` API directly onto `java.net.http.HttpClient.Builder`: they are **two different APIs**. With the modern client, `BodyPublisher` can provide a known content length or unknown length; the protocol implementation decides HTTP/1.1 framing or HTTP/2. You still need to understand body replayability, redirect/auth behavior, timeouts, and idempotency according to **the specific contract of the API you are using**.

Do not assume that being newer means it can “safely auto-retry every streaming POST.” A non-replayable request body and business side effects remain issues in any HTTP stack.

## 24. Facts to distinguish about connection pooling

The `HttpURLConnection` Javadoc states that each object is used to make a single request, but the underlying network connection may be **transparently shared** by other objects. `disconnect()` indicates no further requests are expected on this connection; it **may** close the underlying socket if the socket is idle. Closing response streams frees exchange resources and **does not promise either a new socket or a reused socket**.

Unsafe inferences:

- “Using fixed-length means TCP always stays keep-alive”: false; server/proxy/timeouts can close it.
- “Using chunked guarantees splitting into multiple TCP packets”: TCP segmentation may coalesce or split data depending on conditions.
- “Calling `disconnect()` means the server hasn't read the unsent body yet”: uncertain; the network and server may already be processing.
- “Every `openConnection()` creates a new TCP socket”: not required; keep-alive may be reused.
- “Two `out.write` calls equal two HTTP chunks”: there is no such contract.
- “One HTTP chunk is one business upload part”: false; upload parts must have application-level IDs/framing.

To measure reuse, you need server metrics/TCP tracing/connection IDs, not counts of `HttpURLConnection` objects or `OutputStream.write` calls.

## 25. Troubleshooting common errors

| Symptom | Primary cause | How to check |
| --- | --- | --- |
| `IOException: too many bytes written` | Body is longer than fixed declared length | Count bytes after encoding/transformation; use proper `long` length |
| `IOException: insufficient data written` | Closed before writing full fixed length | Check producer EOF/exception, modified file |
| `IllegalStateException: Already connected` | Streaming mode set after `connect/getOutputStream` | Move setter before connection |
| `IllegalStateException` when calling both fixed and chunked | The two modes are mutually exclusive | Choose one mode based on known/unknown byte count |
| `HttpRetryException` after 307/308 response | Redirect requires body replay, but streaming does not auto-replay | Check location, method, byte source, idempotency, security |
| `HttpRetryException` after 401/407 | Auth challenge requires replaying request body | Authenticate upfront, do not blind retry with wrong credentials |
| HTTP 411 Length Required | Server/proxy requires `Content-Length` | Switch to fixed-length when byte length is known; check server policy |
| HTTP 400/501 with chunked | Server/proxy does not support transfer coding | Verify each hop, avoid mangling chunked |
| Server body parser receives corrupted UTF-8 | Used char length or decoded per chunk | Encode UTF-8 once / use stateful decoder |
| Client hangs indefinitely in `getOutputStream/write` | Backpressure, slow peer, network | Deadline/cancellation policy, observability |
| HTTP 413 Payload Too Large | Server/proxy quota | Enforce size limit upfront, do not retry the same body indefinitely |
| `getErrorStream() == null` | No error body or early I/O failure | Null-check, extract available status/headers |
| Response body left open | Forgot to close/consume `InputStream` | Try-with-resources, `finally` cleanup |

An exception on the **client while reading the response** does not prove the server did not process the POST. Business records need an operation ID/status endpoint rather than inferring from transport failures.

## 26. Twenty common design mistakes

1. **Calculating `Content-Length` with `String.length()`.** Wrong for UTF-8/non-BMP; count bytes.
2. **Enabling fixed-length mode and writing extra bytes.** Throws `IOException`, does not auto-resize `Content-Length`.
3. **Enabling fixed-length mode and closing with too few bytes.** Contract is violated, does not auto-pad.
4. **Calling both fixed and chunked on one connection.** Invalid.
5. **Setting streaming mode after `getOutputStream()`.** Too late; the connection may have already started.
6. **Thinking `chunklen` is the total body length.** It is chunking configuration; the body can be of unknown length.
7. **Thinking `setChunkedStreamingMode(0)` means a zero-byte body.** No, it selects the default chunk size.
8. **Treating two `write` calls as two chunks appearing on the server.** Chunk boundaries are not guaranteed.
9. **Assuming the server understands chunked without checking.** Some servers/proxies do not support it.
10. **Manually adding `Content-Length` alongside `Transfer-Encoding: chunked`.** Conflicting framing.
11. **Thinking streaming is always faster than buffering for every workload.** Must benchmark with realistic data.
12. **Thinking streaming guarantees zero buffering.** Finite I/O/TLS/TCP buffers still exist.
13. **Enabling `followRedirects` and assuming a streaming body is automatically replayed.** `HttpRetryException` can occur.
14. **Receiving 307/308 and re-POSTing to an unvalidated URI.** SSRF, credential leak, duplicate side effects.
15. **Receiving 401/407 and repeatedly resending the same credentials.** Futile and adds load.
16. **Reusing an `HttpURLConnection` instance for a second request.** An instance is for one request; open a new one.
17. **Retrying with an already-exhausted `InputStream`.** No data left to replay; need a fresh source.
18. **Relying on an old file size when the file is being mutated.** The fixed byte contract can break.
19. **Calling `readAllBytes()` on unbounded responses/uploads.** OOM; use bounded streaming.
20. **Treating a timeout/`IOException` as “the server definitely hasn't created the order.”** Uncertain; check status/idempotency.

## 27. Self-check questions

**Q1.** For the UTF-8 body `"Xin chào"`, can you declare `setFixedLengthStreamingMode(text.length())`? **No**; use the byte count of the UTF-8 encoding, e.g., 9 bytes.

**Q2.** Output size is unknown, but the server supports chunked uploads—what should you choose? **`setChunkedStreamingMode(...)`** before opening the output stream.

**Q3.** Does `setChunkedStreamingMode(0)` send an empty body? **No**; it selects the default chunk size.

**Q4.** Can you call fixed first and then chunked? **No**; the two modes are mutually exclusive.

**Q5.** `setInstanceFollowRedirects(true)` is enabled on a streaming POST, and the server returns 307. Why is `HttpRetryException` thrown? **The client has no body buffer to auto-replay**, so the application must handle it safely.

**Q6.** Does `HttpRetryException` prove the server has not processed the request? **No**. Side-effect outcomes require evidence from the server ledger.

**Q7.** If a file can be reopened from the beginning, is retrying the POST automatically safe? **Not yet**. You must consider HTTP semantics, idempotency, and the redirect target.

**Q8.** The server reads 8192 bytes in one `InputStream.read` call; does that mean the HTTP wire chunk was 8192 bytes? **No**. Chunked transfer coding has already been decoded by the HTTP parser; boundaries do not match.

**Q9.** Can one `HttpURLConnection` be used to send two different requests? **No**. Each object is for one request; open a new connection object for a retry/new operation.

**Q10.** Does closing the response `InputStream` guarantee the socket is completely closed? **No**. Keep-alive sharing and `disconnect()` have their own semantics.

**Q11.** The server returns HTTP 411 after a chunked upload. What should you do? **Verify server policy; if the true byte count is known, you can choose fixed-length on a new request per contract**, rather than fabricating a fake `Content-Length`.

**Q12.** The content source is a one-shot pipe. The server returns 401 and requires replay. Can you call `getOutputStream` again on the old connection? **No**. You need a recreatable source or a different protocol; handle auth before sending.

## 28. Production deployment checklist

1. **Right API:** the request is HTTP(S) `HttpURLConnection/HttpsURLConnection`, not mixed with `java.net.http.HttpClient`.
2. **Choose fixed or chunked by true byte length:** fixed if known exactly; chunked if unknown and supported by server/proxy.
3. **Configure all modes before connected:** method, `doOutput`, headers, timeouts, streaming mode.
4. **Count UTF-8 bytes, not char count**; watch out for gzip/transcoding/changing files.
5. **Bound upload bytes, memory, time, and concurrency**; incremental streaming does not mean an unbounded source is safe.
6. **Full try-with-resources/`finally`:** close request output, read/close response body or error stream, and call `disconnect()`.
7. **Read HTTP status and handle HTTP errors with quotas:** `getErrorStream` can be null.
8. **Have you verified server/proxy support for chunked uploads?** Including HTTP 411/413 and intermediate proxies.
9. **Is there a 301/302/303/307/308 redirect policy?** Do not blindly follow every URI or POST side effect.
10. **Is there a 401/407 auth solution that avoids replaying large bodies?** Valid credentials before sending, no secret leaks.
11. **Is the body source replayable?** `byte[]`, snapshot file, one-shot input stream, generator state.
12. **Do retries have an idempotency key/server-side dedup?** Especially for order/payment/job POSTs.
13. **Is there an operation ID/status reconciliation for ambiguous outcomes?**
14. **No leaking `Authorization`/cookies across origins:** prevent SSRF, HTTPS downgrades, redirect loops.
15. **Are there end-to-end deadlines, cancellation, and backoff?** Connect/read timeouts do not replace an overall operation SLA.
16. **Are there real tests on Java 17 and a real server?** Fixed byte count, chunked framing, 307/401, large uploads, file mutation, error bodies, pool reuse.

**Conclusion:** Use `setFixedLengthStreamingMode(long)` when **the exact body byte count is known**, and `setChunkedStreamingMode(int)` when **the byte count is unknown**. Both modes avoid forcing the client to hold the entire request body to send it, at the cost of **not being able to safely auto-replay** when the server requires a redirect or authentication. `HttpRetryException` is a signal for the application to decide, **not a license to automatically resend the POST**. Upload correctness depends on byte count/framing, and retry safety depends on a replayable data source, HTTP semantics, a valid destination, and server-side idempotency.

### Official references

- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): `setFixedLengthStreamingMode`, `setChunkedStreamingMode`, `getErrorStream`, `disconnect`.
- [Java SE 17 — HttpRetryException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html): `responseCode`, `getReason`, `getLocation`.
- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): connection state, timeouts, and input/output configuration.
- [Java SE 17 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): TLS-protected HTTP connection.
- [Java SE 17 — HttpClient / BodyPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublisher.html): differences in the modern HTTP API.
- [RFC 9112 — HTTP/1.1 transfer coding](https://www.rfc-editor.org/rfc/rfc9112.html).
- [RFC 9110 — HTTP Semantics / Redirects and Idempotence](https://www.rfc-editor.org/rfc/rfc9110.html).
