# Reading resource metadata and streams with explicit resource closing

## 1. Goal: read the right information, read enough data, always release resources

In Java Networking, `java.net.URLConnection` is the abstract class representing **a link to a resource located by a URL**. A resource can come from `http:`, `https:`, `file:`, or another protocol handler supported by the Java environment. A resource does not only have **content bytes**: the connection can also provide **metadata** such as content type, content length, content encoding, last-modified, and response headers.

When using URLConnection, there are three distinct things to do:

1. **Configure before connecting:** timeouts, request headers, caching, method, and redirect policy if it is HTTP.
2. **Read metadata and stream at the right time:** the connection may be created lazily; metadata may be absent, and an HTTP error response differs from a success response.
3. **Close resources explicitly:** put `InputStream`/`OutputStream` in `try-with-resources`, use `finally` when `HttpURLConnection.disconnect()` must be called, and clean up temporary files if the download fails.

A short example of the intent:

```java
URLConnection connection = url.openConnection();
connection.setConnectTimeout(3000);
connection.setReadTimeout(3000);

String type = connection.getContentType();
long size = connection.getContentLengthLong();

try (InputStream input = connection.getInputStream()) {
    // Read and process bytes; limit size if the URL is untrusted.
}
// input is closed here even if an exception occurs inside the block.
```

This is an **illustrative code snippet**, requiring `java.net.URL`, `java.net.URLConnection`, `java.io.InputStream`, and a valid `URL url` variable. Calling `getContentType()` or `getInputStream()` can trigger network I/O; do not treat them as merely reading an object whose data is already in memory.

After this lesson, you should be able to:
- Explain the relationship `URL.openConnection()` → configuration → connection → metadata → stream.
- Properly use `getContentType()`, `getContentLengthLong()`, `getHeaderField()`, `getHeaderFields()`, `getLastModified()`, and related getters.
- Understand `-1` (unknown content length) and `null`/`0` (metadata not available).
- Distinguish between `HttpURLConnection.getInputStream()` and `getErrorStream()` when HTTP returns an error code.
- Read streams in a loop, knowing the boundary between **byte count** and **UTF-8 characters**.
- Place close/disconnect/file cleanup operations in structures that are not skipped when errors occur.
- Run two **Java 17+** programs using HTTP loopback and temporary files, without needing Internet access.
- Avoid traps involving memory, timeouts, redirects, content compression, and untrusted URLs.

## 2. URL, URLConnection, and HttpURLConnection are not the same object

Architecture map:

```text
String URL or URI (resource address)
        │
        ▼
    URL object
        │ url.openConnection()
        ▼
  URLConnection object ── configure before connect:
        │                   timeouts, headers, cache, ...
        │
        ├─ if URL is http:/https: usually supports HttpURLConnection
        │      │
        │      ├─ getResponseCode()       HTTP status
        │      ├─ getInputStream()        success body
        │      ├─ getErrorStream()        error body if present
        │      └─ disconnect()            finish using connection instance
        │
        └─ if URL is file:
               metadata and InputStream of the file resource
        │
        ▼
  resource bytes + related metadata
```

Key points:
- **`URL`** describes the resource location, but simply creating a `URL` does not read data yet.
- **`URLConnection`** is an abstract class; `openConnection()` creates a connection object but **is not required to open the connection immediately when called**.
- **`HttpURLConnection`** is the subclass for HTTP; for HTTPS, its subclass `HttpsURLConnection` is typically used. It has HTTP status, method, redirect control, and an error stream.
- **`InputStream`** is the actual byte-reading resource; it **does not close automatically** just because the connection variable goes out of scope.
- **`HttpURLConnection` does not implement `AutoCloseable`**, so do not use `try (HttpURLConnection connection = ...)`. Instead, close the stream and call `disconnect()` in `finally` when appropriate.

For file URLs, you should not cast the connection to `HttpURLConnection`; use the general `URLConnection` APIs. Conversely, when you need to distinguish HTTP 200 and 404, working only through `URLConnection.getInputStream()` misses HTTP-specific APIs; cast only when the URL scheme is known and after checking the type.

## 3. Connection lifecycle: configure first, I/O later

The Java 17 documentation describes the general process:

```text
1. URL url = ...
2. URLConnection c = url.openConnection()
3. c.setConnectTimeout(...), c.setReadTimeout(...),
   c.setRequestProperty(...), c.setUseCaches(...)
4. c.connect() or a metadata/stream read operation that triggers connect automatically
5. c.getHeaderField(...), c.getContentType(), c.getInputStream()
6. Read/write content, close streams; if HTTP, disconnect when finished
```

`connect()` can be called explicitly, but usually it is not required because several methods such as `getInputStream()` will connect automatically if needed. The **logically mandatory** point is to **set configuration before any operation that may connect**.

Wrong example:

```java
URLConnection c = url.openConnection();
InputStream stream = c.getInputStream(); // may have already connected
c.setRequestProperty("Accept", "application/json"); // too late
```

Correct example:

```java
URLConnection c = url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(5000);
c.setRequestProperty("Accept", "application/json");
try (InputStream stream = c.getInputStream()) {
    // read body
}
```

These two snippets are **code fragments** that do not run on their own because they need the `url` variable and imports. With `URLConnection`, many setters will throw `IllegalStateException` if already connected; even if they do not throw, do not expect new configuration to alter a request that has already been sent.

### connectTimeout and readTimeout

| API | Main effect | Unit |
| --- | --- | --- |
| `setConnectTimeout(int)` | Limits the time waiting to **establish** the connection | Milliseconds; `0` is infinite |
| `setReadTimeout(int)` | Limits the time **waiting for data when reading** from the connection | Milliseconds; `0` is infinite |
| Overall application deadline | Limits the entire operation, including redirects, multiple reads, parsing, and saving files | Managed by the application itself |

A read timeout **is not a deadline for downloading the entire file**: a server sending a little bit each time before the timeout expires can keep the stream open longer than expected. When downloading data from untrusted URLs, you should also have **limits on total time, byte count, and redirect hops**.

## 4. Important metadata of URLConnection

`URLConnection` has common accessors:

| Method | Data retrieved | When unknown |
| --- | --- | --- |
| `getContentType()` | MIME type, possibly with charset, e.g. `text/plain; charset=UTF-8` | `null` |
| `getContentLengthLong()` | Content length as a `long` | `-1` |
| `getContentLength()` | Content length as an `int` | `-1` if unknown or exceeds `Integer.MAX_VALUE` |
| `getContentEncoding()` | Content coding such as `gzip` if declared by the server | `null` |
| `getDate()` | `Date` time of the response, milliseconds since Unix epoch | `0` |
| `getLastModified()` | `Last-Modified` time, milliseconds since Unix epoch | `0` |
| `getExpiration()` | `Expires` time, milliseconds since Unix epoch | `0` |
| `getHeaderField("ETag")` | Value of the corresponding header | `null` |
| `getHeaderFieldDate(name, defaultValue)` | Parses a date header into epoch millis if supported | The passed-in default value |
| `getHeaderFields()` | Map of response headers and lists of values | May lack the sought header, depending on protocol |
| `getURL()` | URL attached to the connection object | Not a dedicated “final response URI” API |

Metadata **may require an actual connection** to obtain the headers. Therefore, calling `getContentType()` is not equivalent to fetching static data without network I/O.

### Why prefer getContentLengthLong?

`getContentLengthLong()` uses `long`, supporting values larger than 2 GiB. `getContentLength()` uses `int` and can return `-1` if the size is greater than `Integer.MAX_VALUE`. For files/downloads, use `long` for byte counts, while **still enforcing a practical download limit** according to business rules.

Example:

```java
long declaredLength = connection.getContentLengthLong();
if (declaredLength >= 0) {
    System.out.println("Declared length: " + declaredLength);
} else {
    System.out.println("Length unknown; read until EOF, with a size limit.");
}
```

This is a code fragment; the `connection` variable must already be initialized. `-1` **does not mean the resource is empty**. It only says that metadata did not provide a reliable size at query time.

## 5. Metadata is not absolute truth about content

For resources fetched over the network:
- `Content-Type` is declared by the server/handler and can be wrong or missing. Do not rely solely on MIME type to decide whether to execute/accept an untrusted file.
- `Content-Length` represents the declared length in **bytes** for the representation/message according to HTTP semantics, not the number of Unicode characters. It may be missing if the response uses chunked encoding or other HTTP framing.
- `Content-Length` can be wrong in an invalid response. Code must handle streams ending prematurely, more bytes than expected, and I/O errors.
- `Last-Modified` is advertised by the server; it does not by itself prove content integrity or a trustworthy source.
- `ETag` is an HTTP validator, not a cryptographic signature against file tampering.
- `Content-Encoding: gzip` relates to content coding; **it is not synonymous** with `charset=UTF-8`. The two concepts are byte compression and character decoding.

Distinguish them:

```text
HTTP response:
Content-Type: text/plain; charset=UTF-8
Content-Encoding: gzip
Content-Length: 128

=> Content-Type states the media type and expected character encoding.
=> Content-Encoding states the representation bytes are gzip-compressed.
=> Content-Length is the byte length of the representation per framing,
   not directly the number of Unicode characters after decoding.
```

When decoding, follow the protocol/content-coding and verified charset; do not call `new String(rawBytes)` with the default charset and expect every machine to read Vietnamese correctly.

## 6. HTTP status and metadata: using HttpURLConnection at the right time

For `http:` or `https:` URLs, status code and response message information live on `HttpURLConnection`:

```java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
c.setInstanceFollowRedirects(false);
try {
    int code = c.getResponseCode(); // may connect and read status/headers
    System.out.println("HTTP status = " + code);
    System.out.println("Content type = " + c.getContentType());
} finally {
    c.disconnect();
}
```

This is a code fragment assuming `url` is an HTTP/HTTPS URL. For `file:`, this cast is **invalid**.

`getResponseCode()` can return `-1` if the response is not valid HTTP or throw `IOException` when I/O fails. Statuses `404`/`500` are still meaningful HTTP responses, unlike failing to establish a TCP connection.

A data-downloading program **should not** just look at `getContentLengthLong()` and call `getInputStream()` while ignoring the status code. If the server returns 404, the user needs an **HTTP 404** notice, and sometimes there is a useful error body.

## 7. Success stream and error stream are two handling paths

`HttpURLConnection` provides:
- **`getInputStream()`:** the normal data stream of the resource, typically used when the status succeeds.
- **`getErrorStream()`:** the error content stream **if present**. For example, the server returns 404 along with an error description page.
- **`getResponseCode()`:** the status for the application to choose the right path.

With 404, `getInputStream()` may throw `FileNotFoundException` or `IOException` instead of returning the error body. Do not use that exception as a reason to ignore a useful body; check the status first and try `getErrorStream()`.

General example:

```java
int status = c.getResponseCode();
if (status >= 200 && status < 300) {
    try (InputStream body = c.getInputStream()) {
        // consume success body
    }
} else {
    InputStream error = c.getErrorStream();
    if (error != null) {
        try (InputStream body = error) {
            // read error body up to a safe limit
        }
    }
    // Decide whether to retry, report error, or handle business status.
}
```

This is a **code fragment**; `c` is a configured `HttpURLConnection`, and body-handling functions are provided by the application. Some responses such as 204 or 304 **have no response body**, and `getErrorStream()` is allowed to return `null`. Do not assume every 4xx/5xx always has a JSON error payload.

**Important:** `getErrorStream()` **does not initiate a connection on its own** if the connection has not been connected yet. Calling it before `getResponseCode()` and seeing `null` does not prove the server sent no body. You must check the response code/headers and appropriate connection state.

## 8. Reading HTTP headers properly without leaking sensitive metadata

Common ways to read headers:

```java
String type = c.getHeaderField("Content-Type");
String etag = c.getHeaderField("ETag");
String modified = c.getHeaderField("Last-Modified");

Map<String, List<String>> headers = c.getHeaderFields();
headers.forEach((name, values) -> {
    // Log only allowlisted header names and non-sensitive values.
});
```

This is a code fragment requiring `java.util.Map`, `java.util.List`, and variable `c` as a connection with accessible headers. `getHeaderFields()` returns an unmodifiable map and unmodifiable lists of values per the Java SE 17 API. In HTTP implementations, there may be an entry with key `null` representing the status line; iteration code must handle a `null` key instead of calling `name.toLowerCase()` unconditionally.

A header may appear multiple times. `getHeaderField(String)` returns a single value (the Java docs describe it as the last value when a header has multiple values); `getHeaderFields()` gives you the list, which is more suitable for `Set-Cookie` and headers where multiple occurrences need to be distinguished.

However, **do not log the entire headers map** in production: `Set-Cookie`, `WWW-Authenticate`, bearer tokens in custom headers, signed `Location` headers, and personal data can be leaked into logs.

### Header names are case-insensitive in HTTP

When reading by name, `Content-Type` and `content-type` are the same field name in HTTP. `HttpURLConnection.getHeaderField("Content-Type")` uses the protocol handler to look it up; do not implement a custom HTTP header text string parser if you do not need to.

If the server returns missing or malformed headers:
- `getHeaderField(...)` may return `null`.
- `getContentType()` may be `null`.
- `getContentLengthLong()` may be `-1`.
- The application can still read the stream if the protocol/status permits.

## 9. Java 17+ runnable: reading metadata and streams from HTTP/file

The first complete example creates an HTTP server on **127.0.0.1** at a random port, with three endpoints:
- `/ok`: status 200, body `hello-connection`, metadata Content-Type, Last-Modified, X-Demo, and Content-Length.
- `/missing`: status 404 and error body `not-found`.
- `/chunked`: status 200 and body `chunk-body`, but without a predetermined Content-Length (chunked response).
- Besides HTTP, the program creates a temporary file with body `file-data`, opens a `file:` URL, reads it via `URLConnection`, and deletes the file.

To avoid tests depending on the Internet or a changing public server, all data is generated in-process. The program closes every `InputStream` with `try-with-resources`, calls `disconnect()` on the HTTP connection in `finally`, stops the server in `finally`, and deletes the temporary file.

Save as exact file **`URLConnectionMetadataDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class URLConnectionMetadataDemo {
    private static void serve(HttpExchange exchange, int code,
                              String text, boolean knownLength)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type",
                "text/plain; charset=UTF-8");
        exchange.getResponseHeaders().set("Last-Modified",
                "Wed, 21 Oct 2015 07:28:00 GMT");
        exchange.getResponseHeaders().set("X-Demo", "metadata");
        exchange.sendResponseHeaders(code, knownLength ? data.length : 0);
        try (var out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    private static HttpURLConnection openHttp(URL url) throws IOException {
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setUseCaches(false);
        c.setRequestProperty("Accept", "text/plain");
        c.setInstanceFollowRedirects(false);
        return c;
    }

    private static void readOk(URL url) throws IOException {
        HttpURLConnection c = openHttp(url);
        try {
            int status = c.getResponseCode();
            String type = c.getContentType();
            long length = c.getContentLengthLong();
            String demo = c.getHeaderField("X-Demo");
            String modified = c.getHeaderField("Last-Modified");
            String body;
            try (InputStream in = c.getInputStream()) {
                body = new String(in.readAllBytes(), StandardCharsets.UTF_8);
            }
            System.out.println("status=" + status);
            System.out.println("content-type=" + type);
            System.out.println("content-length=" + length);
            System.out.println("x-demo=" + demo);
            System.out.println("last-modified=" + modified);
            System.out.println("body=" + body);
        } finally {
            c.disconnect();
        }
    }

    private static void readMissing(URL url) throws IOException {
        HttpURLConnection c = openHttp(url);
        try {
            System.out.println("404-status=" + c.getResponseCode());
            try (InputStream err = c.getErrorStream()) {
                String body = err == null ? "(no body)"
                        : new String(err.readAllBytes(),
                                     StandardCharsets.UTF_8);
                System.out.println("404-error=" + body);
            }
        } finally {
            c.disconnect();
        }
    }

    private static void readChunked(URL url) throws IOException {
        HttpURLConnection c = openHttp(url);
        try {
            System.out.println("chunk-status=" + c.getResponseCode());
            System.out.println("chunk-length=" + c.getContentLengthLong());
            try (InputStream in = c.getInputStream()) {
                System.out.println("chunk-body=" + new String(
                        in.readAllBytes(), StandardCharsets.UTF_8));
            }
        } finally {
            c.disconnect();
        }
    }

    private static void readFile() throws IOException {
        Path path = Files.createTempFile("urlconnection-", ".txt");
        try {
            Files.writeString(path, "file-data", StandardCharsets.UTF_8);
            URLConnection c = path.toUri().toURL().openConnection();
            try (InputStream in = c.getInputStream()) {
                System.out.println("file-body=" + new String(
                        in.readAllBytes(), StandardCharsets.UTF_8));
            }
        } finally {
            Files.deleteIfExists(path);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/ok", e ->
                serve(e, 200, "hello-connection", true));
        server.createContext("/missing", e ->
                serve(e, 404, "not-found", true));
        server.createContext("/chunked", e ->
                serve(e, 200, "chunk-body", false));
        server.start();
        try {
            String base = "http://127.0.0.1:" +
                    server.getAddress().getPort();
            readOk(new URL(base + "/ok"));
            readMissing(new URL(base + "/missing"));
            readChunked(new URL(base + "/chunked"));
            readFile();
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac URLConnectionMetadataDemo.java
java URLConnectionMetadataDemo
```

**Stdout verified with `javac --release 17` and run locally:**

```text
status=200
content-type=text/plain; charset=UTF-8
content-length=16
x-demo=metadata
last-modified=Wed, 21 Oct 2015 07:28:00 GMT
body=hello-connection
404-status=404
404-error=not-found
chunk-status=200
chunk-length=-1
chunk-body=chunk-body
file-body=file-data
```

### Why is Content-Length equal to 16?

`hello-connection` is a 16-byte ASCII string in UTF-8, and the server calls `sendResponseHeaders(200, data.length)`. `getContentLengthLong()` reflects the Content-Length header provided by the server. In the chunked response, the program calls `sendResponseHeaders(200, 0)` per `HttpServer`'s contract to use chunked transfer, so `getContentLengthLong()` returns `-1`.

Do not assume an Internet server will use chunked encoding when sending the same body. HTTP/2 does not use `Transfer-Encoding: chunked` like HTTP/1.1; the framing mechanism may differ. `-1` still means “length unknown via metadata”, not “no body”.

### Why is try-with-resources for the error stream allowed to be null?

In Java, a resource expression such as `try (InputStream err = c.getErrorStream())` can receive `null`; the try-with-resources construct does not call `close()` on a null resource. The code still explicitly checks `err == null` before reading. Even though the demo server has an error body, another server may very well not have one.

### Why doesn't a file URL call disconnect?

General `URLConnection` does not have `disconnect()`. File URLs use their own protocol handler; closing the `InputStream` is what matters. The program also uses `Files.deleteIfExists(path)` in `finally` to delete the temporary file **after the stream has closed** — especially necessary on operating systems that do not allow deleting an open file.

### Limitations of the example code

`readAllBytes()` is used with **small responses created by the test server itself**. For user-supplied URLs or untrusted servers, do not call `readAllBytes()` unboundedly: it can cause excessive heap usage. The second example in section 12 demonstrates reading in chunks and **limiting the total byte count**.

## 10. Reading a stream: read() is not guaranteed to fill the buffer

`InputStream.read(byte[])` returns the number of bytes read, which may be smaller than the buffer capacity; `-1` means EOF. Correct code must continue until EOF or until enough bytes are read according to its own framing.

```java
try (InputStream in = connection.getInputStream()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        processBytes(buffer, 0, n);
    }
}
```

This is a **code fragment**; `processBytes(...)` is an application-defined function and `connection` is already connected/configured. You must process exactly `n` bytes, not pass the entire `buffer.length` bytes to the consumer because the remainder could contain old data.

Regarding `readNBytes(n)` or `readAllBytes()`:
- They keep code short for **small and bounded** data.
- They **do not automatically create a safe memory limit** for untrusted responses.
- Using `readAllBytes()` on an infinite streaming endpoint or a multi-gigabyte file is a dangerous design.
- Using `BufferedInputStream` can reduce overhead when reading small amounts at a time, but it does not replace a size limit or timeout.

**A response body** is a stream of bytes. Do not treat a single `InputStream.read` as a new HTTP message, and do not infer HTTP/TCP boundaries from each read call.

## 11. Closing resources: try-with-resources and finally

Minimal pattern for HTTP:

```java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setConnectTimeout(3000);
c.setReadTimeout(5000);
try {
    try (InputStream in = c.getInputStream()) {
        // consume
    }
} finally {
    c.disconnect();
}
```

This is a code fragment; you still need to check status/error stream in production cases. Benefits:
- If parsing/reading throws an exception, `InputStream.close()` is still called.
- If closing finishes or setup/read fails, `disconnect()` is still called in `finally`.
- You do not have to write `in.close()` on every return/throw path.
- Exceptions thrown during close can be preserved as suppressed exceptions, aiding debugging.

### Closing a stream and disconnect are different

According to Java SE 17:
- Calling `close()` on the `InputStream` or `OutputStream` of a `URLConnection` **may** release network resources depending on the protocol.
- Each `HttpURLConnection` instance represents one HTTP request; the underlying persistent TCP connection **may be shared/reused** across other instances.
- `disconnect()` signals that the application will no longer use this connection; it **may close the underlying socket** if the persistent connection is idle, but **does not guarantee** all TCP resources are closed immediately.
- `disconnect()` **does not** allow reusing that same `HttpURLConnection` instance to send a new request.

Therefore, **do not replace `try-with-resources` with just `disconnect()`**. With streaming/large responses, you must close the stream to release the associated resources properly.

### Close resources even when the body is not fully read

Some applications only need metadata or part of the body. If you have opened the input stream and do not need the rest, you should still close the stream. With HTTP keep-alive, closing early may prevent connection reuse or trigger closing the socket; that is the right trade-off if the app does not want to consume the remaining data. Do not leave the stream hanging just in “hope that the connection pool reuses it better”.

## 12. Java 17+ runnable: chunked download, byte limit, and temp file cleanup

`Content-Length` metadata is only a **hint** and may be missing. To limit a file downloaded from a URL, you need **two checks**:
1. If `getContentLengthLong() > MAX_BYTES`, reject early to avoid waste.
2. While actually reading, sum the **actual bytes received**. If the limit is exceeded, stop and delete the temporary file.

The following program uses a loopback server with two endpoints:
- `/small` body `ABCDEF` = 6 bytes.
- `/large` body `ABCDEFGHIJKL` = 12 bytes.
- The client sets `maxBytes = 8` and accepts only the small content.

The code uses `try-with-resources` for **both InputStream and OutputStream**, cleans up the temp file, and disconnects in `finally`.

Save file **`BoundedDownloadDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class BoundedDownloadDemo {
    private static void serve(HttpExchange exchange, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(200, data.length);
        try (var out = exchange.getResponseBody()) {
            out.write(data);
        }
    }

    private static long receive(URL url, long maxBytes) throws IOException {
        if (maxBytes < 0) throw new IllegalArgumentException("negative limit");
        HttpURLConnection c = (HttpURLConnection) url.openConnection();
        c.setConnectTimeout(3000);
        c.setReadTimeout(3000);
        c.setInstanceFollowRedirects(false);
        Path temporary = null;
        try {
            if (c.getResponseCode() != 200) {
                throw new IOException("Unexpected HTTP status");
            }
            long declared = c.getContentLengthLong();
            if (declared > maxBytes) {
                throw new IOException("Declared body exceeds limit");
            }
            temporary = Files.createTempFile("bounded-download-", ".part");
            long bytes = 0;
            try (InputStream in = c.getInputStream();
                 OutputStream out = Files.newOutputStream(temporary)) {
                byte[] buffer = new byte[4096];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    if (n > maxBytes - bytes) {
                        throw new IOException("Actual body exceeds limit");
                    }
                    out.write(buffer, 0, n);
                    bytes += n;
                }
            }
            return bytes;
        } finally {
            if (temporary != null) Files.deleteIfExists(temporary);
            c.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/small", e -> serve(e, "ABCDEF"));
        server.createContext("/large", e -> serve(e, "ABCDEFGHIJKL"));
        server.start();
        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            System.out.println("small-bytes=" +
                    receive(new URL(base + "/small"), 8));
            try {
                receive(new URL(base + "/large"), 8);
                System.out.println("large-rejected=false");
            } catch (IOException expected) {
                System.out.println("large-rejected=true");
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run:

```bash
javac BoundedDownloadDemo.java
java BoundedDownloadDemo
```

Verified stdout:

```text
small-bytes=6
large-rejected=true
```

### Why does the code use maxBytes - bytes?

`if (n > maxBytes - bytes)` avoids **overflow on addition** in case of large data: comparing against the remaining capacity is safer than adding `bytes + n` first and then comparing. `bytes` only increases after confirming the received amount does not exceed `maxBytes`.

### Why create a temporary file and then delete it?

The example only needs to demonstrate the limit and cleanup, so it deletes the temporary file **on both success and failure**. In a real download application, you can:
1. Create a temporary file alongside the destination directory.
2. Write the whole thing and verify size/hash/content-type/signature per policy.
3. Flush and close the stream.
4. Move the temporary file to the official location with a safe rename/move step, if the filesystem allows.
5. Delete the temporary file if an error occurs or the limit is exceeded.

**Do not** let a partially downloaded file be treated as a complete artifact. Across different filesystems, `ATOMIC_MOVE` may not be supported; design clear fallback/rollback handling.

### What if Content-Length = -1?

When metadata does not know the size, the code **does not reject immediately** just because of `-1`. The read loop still monitors **actual bytes received**, so a chunked response is also blocked when it exceeds 8 bytes. This is more important than relying solely on Content-Length to decide allocations.

## 13. Reading text: charset must be explicit

InputStream provides bytes. To read Vietnamese text, you must choose the right charset, usually UTF-8.

```java
try (InputStream in = connection.getInputStream();
     InputStreamReader decoder =
             new InputStreamReader(in, StandardCharsets.UTF_8);
     BufferedReader reader = new BufferedReader(decoder)) {
    String line;
    while ((line = reader.readLine()) != null) {
        processLine(line);
    }
}
```

This is a code fragment with `processLine` as an application function. It can be simplified with `new BufferedReader(new InputStreamReader(in, UTF_8))`. Do not use `new InputStreamReader(in)` without specifying a charset if the protocol has not defined one and you want consistent behavior across runtimes/locales.

### Content-Type and charset

Metadata example:

```http
Content-Type: text/plain; charset=UTF-8
```

The server declares the text is UTF-8. For real HTTP responses, you should parse `charset` according to MIME rules or use an appropriate library, with a protocol-based fallback; do not use an overly simple `String.split(";")` for all content-type syntaxes. If the header is missing, the charset choice **depends on the application protocol**; there is no single safe default rule for all files.

`Content-Encoding` such as `gzip` is a **compression layer**, which must be decompressed (if the client does not already handle it via the handler) before decoding characters. Do not feed gzip bytes straight into a UTF-8 decoder and conclude the file is corrupted.

## 14. HTTP case without Content-Length: chunked and streaming

For HTTP/1.1:
- The server may send the body using `Transfer-Encoding: chunked` when the size is not known in advance.
- In that case `Content-Length` is usually absent, and `URLConnection.getContentLengthLong()` returns `-1`.
- Client code still **reads through InputStream** as usual; the HTTP protocol handler handles chunk framing.
- The app does not have to parse chunk lengths manually from the stream returned by `HttpURLConnection.getInputStream()`.

```text
HTTP response (wire, conceptual):
HTTP/1.1 200 OK
Transfer-Encoding: chunked

5\r\nHello\r\n0\r\n\r\n

InputStream at the application layer reads:
Hello

getContentLengthLong() = -1
```

This is a simplified description; actual chunk framing can include multiple chunks/trailers. Do not include `\r\n` chunk delimiters in the payload parser when using `HttpURLConnection`, because the protocol handler has already decoded HTTP transfer framing.

**Do not confuse** chunked transfer encoding with `Content-Encoding: gzip`. Chunked helps transmit a message over a connection with unknown length, while gzip compresses the representation bytes. A response may have corresponding encoding layers; code must know which layer is automatically handled by the HTTP implementation.

## 15. HEAD request: querying metadata without downloading the body, with limitations

For HTTP, the `HEAD` method asks the server to provide response headers roughly equivalent to `GET` **without sending the response body**. This is useful when you need content type, last-modified, etag, or estimated size before deciding to download.

```java
HttpURLConnection head = (HttpURLConnection) url.openConnection();
head.setRequestMethod("HEAD");
head.setConnectTimeout(3000);
head.setReadTimeout(3000);
try {
    int status = head.getResponseCode();
    long length = head.getContentLengthLong();
    String type = head.getContentType();
    // Use status, length, and type as needed by the application.
} finally {
    head.disconnect();
}
```

This is a code fragment assuming `url` is an HTTP(S) URL and requiring imports. **You must call `setRequestMethod("HEAD")` before connecting**.

Limitations:
- The server may not support HEAD properly; it may return 405 or different metadata.
- `Content-Length` of a HEAD response is usually the size of the representation corresponding to GET, not the number of body bytes transmitted in the HEAD response.
- Metadata can change between HEAD and GET due to dynamic resources, caching, or content negotiation.
- HEAD **does not replace** the size limit inside the GET read loop.
- Not every URL/protocol supports HEAD; this is HTTP-specific behavior of `HttpURLConnection`.

If you only want metadata for a local file, using `Files.size(path)` and `Files.getLastModifiedTime(path)` can be simpler/clearer than a `file:` URLConnection; URLConnection remains useful when the same abstraction handles multiple schemes.

## 16. Caching and conditional requests: ETag, Last-Modified, 304

Some metadata helps avoid re-downloading unchanged resources:
- `ETag`: validator provided by the server.
- `Last-Modified`: last modification time according to the server.
- `If-None-Match`/`If-Modified-Since`: client asks the server whether anything changed.
- `304 Not Modified`: server indicates the representation has not changed per the condition; **usually has no response body**.

Example:

```java
URLConnection c = url.openConnection();
c.setIfModifiedSince(lastSeenMillis);
try (InputStream in = c.getInputStream()) {
    // Read when protocol/status allows.
}
```

This is a code fragment; `lastSeenMillis` is saved by the application from a previous read. With HTTP, you should specifically check `HttpURLConnection.getResponseCode()` before opening the body, because 304 has different semantics from 200. `setIfModifiedSince(long)` only sets conditional semantics per the handler; it **does not** turn a server response into a ready-made application cache.

A caching model:
1. Store the old representation along with verified ETag/Last-Modified.
2. Send a conditional GET.
3. If `200`, read the body, verify, and update cache/metadata.
4. If `304`, use **the old body stored in your cache**; do not try to read a new body.
5. If an error status occurs, handle per policy instead of silently treating it as 304.

Cache validators are not tamper-proof signatures. For sensitive/high-security content, verify TLS, integrity hashes/signatures, and access permissions according to business requirements.

## 17. HeaderFieldDate and time from the server

`getLastModified()` and `getDate()` return `long` in Unix epoch milliseconds, or `0` if unknown. To parse another date header:

```java
long fallback = -1;
long expires = connection.getHeaderFieldDate("Expires", fallback);
if (expires != fallback) {
    Instant when = Instant.ofEpochMilli(expires);
    System.out.println(when);
}
```

This is a code fragment requiring import `java.time.Instant` and variable `connection`. In production, `-1` is an application-chosen sentinel; avoid treating server-returned dates as a reference clock or completely trustworthy data.

**Timezone note:** HTTP date headers use standard date formats in GMT/UTC; epoch milliseconds do not carry a display timezone. When displaying, convert `Instant` to a chosen timezone explicitly; do not use locale-dependent string parsing without checking the format.

A header may be completely absent. For `getLastModified()`, `0` per the API means “unknown”, but as an epoch value it is also a specific point in time; do not design business logic assuming `0` is always a meaningful timestamp.

## 18. Redirects and metadata: checking which final resource is being read

`HttpURLConnection` has a mechanism to automatically follow HTTP redirects depending on configuration. In Java 17, `getInstanceFollowRedirects()` of a new connection takes its default from the static value `getFollowRedirects()`; this static default is usually **true**, unlike `java.net.http.HttpClient` whose redirect default is **NEVER**.

If a URL returns 302 to another host:
- `getContentType()`/`getContentLengthLong()` after auto-follow may reflect the **target resource after the redirect**.
- Any request headers/credentials may be subject to separate forwarding rules.
- An app fetching user-supplied URLs could be directed to an internal IP/metadata service (SSRF).
- You should not assume that if an initial `URL` is safe, every subsequent Location will be safe.

Enable manual control for a specific connection:

```java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setInstanceFollowRedirects(false);
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
int status = c.getResponseCode();
// If 3xx, read Location and evaluate it yourself before sending a new request.
```

This is a code fragment without complete cleanup; in production put `try/finally` and `disconnect()`, and handle error streams. Checking only an initial URL and then enabling follow can allow a server to redirect to another unauthorized host.

**Security policy:** For untrusted URLs, restrict the scheme to HTTPS when appropriate, allowlist hostname/port, check DNS/egress policy, and validate **every redirect hop**. Do not send Authorization, Cookie, or custom API keys to a different destination just because `Location` suggests it. Do not disable HTTPS certificate/hostname verification just to “get the download through”.

## 19. InputStream is a resource with ownership and a lifecycle

When a function returns an `InputStream` to the caller, it must decide **who is responsible for closing it**. A non-ideal API example:

```java
InputStream openRemoteStream(URL url) throws IOException {
    URLConnection c = url.openConnection();
    return c.getInputStream();
}
```

This is a code fragment; it pushes the `close()` obligation onto the caller without making it explicit; if the caller forgets, the resource can be leaked. Moreover, if the function created an `HttpURLConnection`, the function cannot call `disconnect()` in `finally` right before the caller reads the stream because that would break the lifecycle.

Better designs:
1. **Process the stream completely inside the method** with `try-with-resources`, returning the parsed model/data.
2. If a streaming API is needed, **return an explicit resource owner** with a `close()` method that closes the stream and network state, or document that the API requires the caller to close the stream.
3. With multi-threaded streaming, ensure the parser/stream is not closed by another thread before the consumer finishes, unless cancellation policy allows it.
4. For file downloads, avoid exposing a `Path` to an incomplete file; only publish the target file after writing/verification completes.

Example of a method that reads a short string and closes itself:

```java
static String fetchSmallText(URLConnection c) throws IOException {
    try (InputStream in = c.getInputStream()) {
        byte[] bytes = in.readNBytes(4097);
        if (bytes.length > 4096) {
            throw new IOException("Too much data");
        }
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
```

This is a **code fragment**; `readNBytes(4097)` caps memory at the chosen level for **the read**, but you need to add deadline/network error handling, and if using HTTP you must check status/error stream beforehand. `readNBytes(4097)` returns at most 4097 bytes, not an unbounded amount. Reading one byte past the limit to detect oversized payloads is a simple technique for small payloads.

## 20. Common mistakes when closing

| Practice | Problem | Fix |
| --- | --- | --- |
| Calling `connection.getInputStream().readAllBytes()` without closing | Stream can hold onto resources | `try (InputStream in = ...)` |
| Calling only `disconnect()` | Does not replace the obligation to close the stream; does not always close the socket immediately | Close stream and disconnect in finally |
| Using `try (HttpURLConnection c = ...)` | `HttpURLConnection` is not AutoCloseable | Try-with-resources for stream, finally for connection |
| Returning early on status 404 without checking error stream | Misses error info and response resources | Read/close `getErrorStream()` if present, per policy |
| Deleting temp file before closing OutputStream | Can fail on Windows and hold file handle | Close streams first; delete in finally |
| Closing a stream while another worker is reading it | Race condition or truncated data | Enforce ownership/lifecycle |
| Trusting close ensures every byte was written to destination | May have IOException or storage errors | Check errors, flush/close, atomic publish, checksum |
| Leaving a partially downloaded file at the official path | Consumer may treat incomplete data as complete | Download to temp, verify, then move |
| Not closing error stream on HTTP 500 | Connection resources/response body may remain pending | Close error body after handling |
| Using one connection object for multiple HTTP requests | `HttpURLConnection` is not meant to reuse a request instance | One instance per request; underlying keepalive is managed by handler |

`try-with-resources` ensures close is called in reverse order of resource creation when exiting the block, even if an exception occurs. However, close **can also throw IOException**, so the application must still handle/rethrow/log appropriately; do not silently swallow the exception and report a successful file download.

## 21. Errors and timeouts: HTTP responses differ from I/O errors

Scenarios:
- HTTP 404/500: the server responded validly, `getResponseCode()` gives the status; there may be an error body.
- `UnknownHostException`: DNS failed to resolve the name.
- `ConnectException`: TCP connection was refused/could not be established.
- `SocketTimeoutException`: connect or read timed out per configured timeout.
- `SSLHandshakeException`: invalid TLS certificate/protocol/handshake on HTTPS.
- `EOFException` or missing data: body was truncated compared to the framing expected by the application.
- `IOException` when reading stream/writing disk/closing resources.

Do not write:

```java
try (InputStream in = url.openStream()) {
    return new String(in.readAllBytes(), StandardCharsets.UTF_8);
} catch (IOException e) {
    return "";
}
```

as a general production strategy. This snippet is an **anti-pattern**: it equates a network error with a valid empty resource, reports no status, and has no size limit. Replace it with an explicit result/exception and controlled observability.

When an error occurs, log sanitized hostname/scheme/status/duration; do not log Bearer tokens, cookies, signed query strings, or sensitive raw bodies.

## 22. File URLs and filesystem security boundaries

`Path.toUri().toURL().openConnection()` allows opening a `file:` URL with `URLConnection`, but if the URL source comes from a user, **do not** allow arbitrary filesystem access by accepting any URL.

Risks:
- `file:///etc/passwd` or sensitive local files.
- Path traversal via improperly resolved URLs/URIs.
- Windows drive/UNC paths and network shares have distinct semantics.
- Symlinks pointing to files outside the allowed directory.
- TOCTOU between path validation and file opening.

If the application only wants to read files within a directory, use `java.nio.file.Path` + canonical/real-path containment + appropriate file permissions/policy, and consider race/symlinks. Do not use `new URL(userInput).openStream()` in a backend service that has broad filesystem/network read permissions.

**Do not confuse the URLConnection file handler with safe reading:** the same API can open both remote and local sources; security policy must be applied per scheme and destination.

## 23. Performance and memory when reading large resources

A large stream can consume:
- Network bandwidth.
- Heap if the entire body is collected into a `byte[]`.
- File descriptors/socket handles.
- Disk if writing to a file.
- CPU during decompression, transcoding, parsing.
- Threads if each download blocks for a long time.

Techniques:
- Use a reasonably sized buffer (e.g., 8 KiB, 16 KiB); do not grow the buffer unboundedly based on remote Content-Length.
- Enforce **max bytes** even when the header is missing/wrong.
- Use a streaming parser instead of holding all text when data is large.
- Limit concurrent downloads, connections to the same host, and wait times.
- Verify content type/extension/signature according to consumption purpose; do not trust headers blindly.
- If computing a content hash, update `MessageDigest` chunk by chunk while reading, avoiding reading everything into heap.
- When downloading multiple files, do not let failed tasks leave temp files or streams open.

A streaming hash pattern, **code fragment**:

```java
MessageDigest digest = MessageDigest.getInstance("SHA-256");
try (InputStream in = c.getInputStream()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        digest.update(buffer, 0, n);
    }
}
byte[] hash = digest.digest();
```

Requires importing `java.security.MessageDigest`, `java.io.InputStream`, and providing an `HttpURLConnection c` whose status has been confirmed. A SHA-256 hash helps compare integrity against a **trusted digest** obtained from an independent channel; **a hash provided by the same untrusted server** does not prove authenticity on its own.

## 24. When to choose Java 17 HttpClient instead of URLConnection?

`URLConnection/HttpURLConnection` is a long-standing API, suitable when:
- Reading a simple URL or legacy code already relies on this API.
- You need to work with multiple protocol handlers such as `file:` under the same interface.
- You want to clearly understand connections, headers, streams, and lifecycle.
- You do not need asynchronous pipelining or modern HTTP/2 features.

`java.net.http.HttpClient` (Java 11+) is suitable when:
- You need to send synchronous/asynchronous HTTP requests with `send`/`sendAsync`.
- You need HTTP/2 when the endpoint supports it.
- You want clear `HttpRequest`/`HttpResponse` and `BodyHandler` APIs.
- You need composition with `CompletableFuture`, multiple requests, and deadline policies.

```java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/resource")).GET().build();
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
try (InputStream body = response.body()) {
    // consume stream; do not skip close responsibility
}
```

This is a code fragment requiring imports `java.net.URI`, `java.net.http.*`, `java.io.InputStream`, and handling checked exceptions. **HttpClient does not make the obligation to close a streaming body disappear**; `BodyHandlers.ofInputStream()` returns the body as a stream that the caller still must read/close.

This lesson focuses on `URLConnection` and does not turn into a full HttpClient guide. Note that the two APIs have different redirect/timeout/resource policies; do not infer a behavior from one API to the other.

## 25. Scenario-based testing and resource invariants

Tests you should have:

| Scenario | Expectation |
| --- | --- |
| HTTP 200, valid Content-Type and Content-Length | Read metadata accurately, body byte count accurate |
| HTTP 200 missing Content-Length/chunked | `getContentLengthLong() == -1` and still read stream until EOF |
| HTTP 404 with error body | `getResponseCode()==404`, handle readable `getErrorStream()` |
| HTTP 404 without body | `getErrorStream()` may be null; code does not NPE |
| Server closes early | Do not treat partial data as success if protocol requires complete length |
| Slow server sending no bytes | Read timeout occurs, stream/connection closed |
| Content-Length header exceeds max | Reject early, do not allocate based on header |
| No Content-Length, body exceeds max | Read loop still blocks it and cleans up temp |
| Existing File URL | InputStream reads properly, closes before deleting temp file |
| Non-existent File URL | Exception handled properly, no resource leak left |
| UTF-8 charset with multi-byte characters | Decode bytes properly after receiving fully |
| Content-Encoding gzip | Decompress appropriately then decode charset |
| Cross-host redirect | Do not automatically send secrets to non-allowlisted hosts |
| Multiple consecutive requests | Each HttpURLConnection uses one request instance, all streams closed |
| Download file then disk write error | Temp file deleted, incomplete file not published |
| Finished reading but close throws IOException | Do not falsely report success, handle suppressed errors |
| User-supplied URL has file/internal IP | Reject per scheme/host/egress policy |
| Date/Last-Modified metadata absent | Code handles sentinel `0` or `null` |

Using a loopback server with port `0` keeps output controlled without depending on public services. To test close, you can use a stream wrapper that records how many times `close()` is called; to test timeout, the server intentionally withholds sending the response until the deadline expires. Do not use `Thread.sleep()` unnecessarily making results scheduler-dependent when a latch/barrier can be used.

## 26. Common misconceptions

1. **“`openConnection()` downloads the body right away.”** No; it usually only creates the connection object, and I/O operations may be lazy.
2. **“You can set request headers after `getInputStream()`.”** Usually too late because the connection has already performed I/O.
3. **“`getContentLengthLong() == -1` means empty body.”** No, the length is unknown.
4. **“Content-Length is the number of Java String characters.”** No; it is byte length information per HTTP representation/framing.
5. **“Content-Type is always right.”** No; the header is advertised by the server and can be missing/wrong.
6. **“One stream read gets the whole body.”** No; `read` may return a partial chunk; you must loop.
7. **“`HttpURLConnection.getInputStream()` always reads 404 JSON too.”** No; errors may require `getErrorStream()`.
8. **“`getErrorStream()` always returns non-null.”** No; it can be null and does not connect on its own.
9. **“Closing the connection with `disconnect()` is enough.”** It does not replace the obligation to close streams and clean up.
10. **“HttpURLConnection implements AutoCloseable.”** No; use try-with-resources for input/output streams.
11. **“Every URLConnection has `getResponseCode()`.”** No; that is an HTTP-specific API.
12. **“`file:` URLConnection must call `disconnect()`.”** There is no such general method; close the file stream.
13. **“Chunked body requires manually parsing `\r\n` chunk frames.”** Not when using the HTTP InputStream returned by HttpURLConnection.
14. **“Content-Encoding gzip and charset=UTF-8 are the same.”** No; gzip is compression, UTF-8 is text decoding.
15. **“A HEAD response always accurately reflects the subsequent GET.”** No; metadata can change, and the server may not support HEAD properly.
16. **“`getLastModified()==0` means the file was modified at the epoch.”** The API uses 0 when unknown.
17. **“URLConnection metadata is a trustworthy security source.”** No; you must validate origin, certificate, and integrity/authorization.
18. **“`readAllBytes()` on the Internet is safe because there is Content-Length.”** No; the body may be unbounded or the header wrong.
19. **“HttpURLConnection default auto-redirect is the same as HttpClient.”** No; the two APIs have different defaults.
20. **“One HttpURLConnection can be reused for multiple requests.”** Each instance is one request; underlying TCP pooling does not change that.
21. **“If a partial download already created a file, it can be handed to the consumer.”** No; you need to verify, close, and publish atomically when appropriate.
22. **“With HTTPS, a user-supplied URL cannot cause SSRF.”** No; redirects/destination networks still require policy.

## 27. Self-check questions

**Question 1.** Why is `getContentLengthLong()` better than `getContentLength()` when reading large resources?  
**Answer:** It uses `long`, so it can represent lengths beyond the `int` limit; both can still report unknown.

**Question 2.** A chunked HTTP response has `getContentLengthLong() == -1`; how do you retrieve the body?  
**Answer:** Read `getInputStream()` until EOF (with size/time limits); the HTTP protocol handler handles transfer framing.

**Question 3.** `getContentType()` returns `text/plain; charset=UTF-8`. Can you immediately use `new String(bytes, UTF_8)`?  
**Answer:** Only after handling content encoding properly and confirming the content type/charset is valid for the protocol; server headers can be missing/wrong.

**Question 4.** When should `setConnectTimeout`/`setReadTimeout` be called?  
**Answer:** After `openConnection` but before any operation that may connect/read.

**Question 5.** HTTP returns `404` with an HTML error body. Why might `getInputStream` not be able to read it?  
**Answer:** `HttpURLConnection` distinguishes error responses; `getInputStream` may throw IOException—use `getResponseCode` and `getErrorStream` if present.

**Question 6.** Does `getErrorStream()` returning null mean the server does not exist?  
**Answer:** No; null can occur because it is not connected yet, there is no error data, or it is not an error response.

**Question 7.** Should you call `disconnect()` without closing `InputStream`?  
**Answer:** No; close the stream explicitly with try-with-resources, then disconnect per lifecycle.

**Question 8.** Why not use `try (HttpURLConnection c = ...)`?  
**Answer:** `HttpURLConnection` is not `AutoCloseable`, whereas InputStream/OutputStream are Closeable.

**Question 9.** A file downloaded in chunks exceeds the limit when Content-Length is missing. Where do you check?  
**Answer:** In the read loop, by accumulating actual bytes; stop before writing past the quota and delete the temporary file.

**Question 10.** What is the difference between Content-Encoding and charset?  
**Answer:** Content-Encoding is how bytes are represented/compressed (e.g., gzip), while charset is the rule for converting bytes into characters (e.g., UTF-8).

**Question 11.** Does `HEAD` replace checking the size of `GET`?  
**Answer:** No; HEAD metadata can be missing/change, and the GET body must still be checked against the actual limit.

**Question 12.** Does general `URLConnection` have `disconnect()`?  
**Answer:** No; that is an API of `HttpURLConnection`. For file URLs, close the InputStream.

**Question 13.** Why is each `HttpURLConnection` instance only used for one request even though TCP connections can use keep-alive?  
**Answer:** Request state lives on the instance; underlying socket pooling is a separate layer managed by the HTTP handler.

**Question 14.** When a user supplies a `file:` URL or a redirect to 127.0.0.1, what must you do?  
**Answer:** Check scheme/destination/allowlist and network/file policy; do not use openStream directly on untrusted URLs.

**Question 15.** The stream finished reading enough data, but writing to the file failed mid-way; should you keep the target file?  
**Answer:** Do not publish an incomplete file; clean up temp, handle the error, and only publish when writing/verification succeeds.

## 28. Implementation checklist

**Before reading:**
- Verify URL scheme, hostname/path/port, and allowed policy.
- Create a new URLConnection per logical request; do not reuse an old HTTP instance.
- Set connect/read timeouts, headers, cache, and redirects **before I/O**.
- For HTTP, check status code and avoid auto-following untrusted URLs.

**While reading metadata and stream:**
- Handle null `Content-Type`, `-1` `Content-Length`, and missing date metadata.
- Handle HTTP success/error streams separately, checking null on the error stream.
- Decode text with the appropriate charset; separate content encoding from charset.
- Read in a loop and process exactly n bytes, not relying on a single read.
- Limit actual bytes received, total deadline, and concurrency.
- Do not use remote headers as the authority for security policy decisions.

**When finished:**
- Close all InputStream/OutputStream instances using try-with-resources.
- For HTTP, use `finally` to call `disconnect()` when appropriate; do not treat it as a replacement for close.
- Delete temporary files on error/quota exceeded; only publish files after verification.
- Log sanitized status/metadata; do not record credentials, cookies, or signed URLs.
- Test 200, 404, unknown length, oversized body, connection timeout, and failure cleanup.

**Remember:** URLConnection provides **metadata + stream**, but the API does not automatically perform all **validation, download limiting, and resource closing** on behalf of the application. Proper design must keep the **configure/connect/read/close order** clear, handle missing metadata, and ensure every success or failure path releases resources.

## 29. References

- Java SE 17 `URLConnection` — lifecycle, metadata methods, streams, timeouts, and close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html
- Java SE 17 `HttpURLConnection` — status code, getErrorStream, redirect policy, and disconnect: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html
- Java SE 17 `HttpsURLConnection` — HTTPS-specific behaviors: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html
- Java SE 17 `URL` — openConnection/openStream: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html
- Java SE 17 `InputStream` — read, readAllBytes, readNBytes, and close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Java SE 17 `Files` — temporary files, streams, and move: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html
- Java SE 17 `HttpServer` — local HTTP test server: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- Java SE 17 `HttpResponse.BodyHandlers` — streaming alternatives on HttpClient: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- RFC 9110 — HTTP Semantics (media type, Content-Length, validators, HEAD, status codes): https://www.rfc-editor.org/rfc/rfc9110
- RFC 9112 — HTTP/1.1 message framing, Transfer-Encoding: https://www.rfc-editor.org/rfc/rfc9112
