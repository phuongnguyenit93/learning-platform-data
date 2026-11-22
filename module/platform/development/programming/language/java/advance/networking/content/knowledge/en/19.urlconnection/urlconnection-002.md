# Setting Timeouts, Request Properties, and Input/Output Direction Before Connecting URLConnection in Java

**`java.net.URLConnection` has two phases: creating and configuring the connection object, then establishing communication and performing I/O.** With Java 17+, you should set the **connect timeout**, **read timeout**, **request properties (especially HTTP headers)**, and **input/output direction** on the URLConnection object **before calling any method that can trigger a connection**.

Safe order for a typical HTTP GET:

~~~java
URL url = new URL("https://example.com/data"); // Illustrative URL
URLConnection conn = url.openConnection();       // Does not actively send request yet

conn.setConnectTimeout(2_000);                  // 2 seconds
conn.setReadTimeout(3_000);                     // 3 seconds
conn.setDoInput(true);
conn.setDoOutput(false);
conn.setRequestProperty("Accept", "text/plain");

// getInputStream() may connect implicitly if not already connected.
try (InputStream in = conn.getInputStream()) {
    byte[] content = in.readAllBytes();
    // Process content; enforce size limits in production.
}
~~~

This is a **snippet**, requiring `java.net.*`, `java.io.*` imports and `IOException` handling. The sample URL requires Internet access, so it is not an offline example. The two complete programs below use an HTTP server at `127.0.0.1` on a dynamic port to verify the sequence without external network access.

**Most common pitfall:** `getInputStream()`, `getOutputStream()`, `getResponseCode()` (with `HttpURLConnection`), `getContent()`, or querying certain response headers can **implicitly perform a connect**. Even without explicitly calling `connect()`, the connection can still happen. From that point on, changing many properties such as `setDoInput`, `setDoOutput`, or `setRequestProperty` will result in an `IllegalStateException`.

This Knowledge article belongs to the **URLConnection** topic in Java Advance - networking, focusing on the exact four pre-connect setting groups, usage with `HttpURLConnection`, consequences of doing things out of order, handling HTTP errors, and Java 17+ practices.

## 1. URLConnection Lifecycle: configure → connect → use → cleanup

According to the Java API, obtaining an object via `URL.openConnection()` **does not mean a network connection to the remote endpoint has been opened**. Logical flow:

~~~text
                URL / URI
                   |
                   v
            url.openConnection()
                   |
                   v
         [NEW / not yet connected]
                   |
      +------------+-------------+
      |                          |
 setConnectTimeout()        setReadTimeout()
 setDoInput()               setDoOutput()
 setRequestProperty()       setUseCaches()
 setRequestMethod() (*)     setInstanceFollowRedirects() (*)
 setFixedLengthStreamingMode() (*)
      |                          |
      +------------+-------------+
                   |
         configuration complete
                   |
          +--------+-------------+
          |                      |
      conn.connect()       I/O operation auto-calls connect
          |                      |
          +-----------+----------+
                      |
                [CONNECTED]
                      |
            send / receive bytes
            response code / headers
                      |
                close streams
                disconnect (*) / cleanup
~~~

APIs marked `(*)` exist only on `HttpURLConnection` or specific HTTP classes. `URLConnection` is the superclass; not every protocol has HTTP methods or status codes.

**The two phases are an important invariant:**
1. **Setup:** Configure the object before it is used. Properties such as `doInput/doOutput`, request headers, and HTTP method must be determined before connecting.
2. **Connected/I/O:** Begin transmitting data and reading the response. Do not expect late configuration changes to alter bytes that have already been sent.

How to avoid errors: place all setup calls in one contiguous block right after `openConnection()`, before any `connect()`, `getInputStream()`, or `getOutputStream()`.

## 2. Which settings must be configured beforehand?

| Setting | API | Purpose | Constraints / default |
| --- | --- | --- | --- |
| **Connect timeout** | `setConnectTimeout(int milliseconds)` | Limits the time to establish a link to the URL | Value 0 = no limit; negative value → `IllegalArgumentException` |
| **Read timeout** | `setReadTimeout(int milliseconds)` | Limits the time a read operation waits for data | Value 0 = no limit; negative value → `IllegalArgumentException` |
| **Request property** | `setRequestProperty(key,value)` | Sets a specific request header/property | After connecting → `IllegalStateException` |
| **Add request property** | `addRequestProperty(key,value)` | Appends a value for a key instead of replacing | Also must be before connecting |
| **Allow reading** | `setDoInput(true/false)` | Application intends to get `InputStream` | Default `true`; after connecting → `IllegalStateException` |
| **Allow writing** | `setDoOutput(true/false)` | Application intends to get `OutputStream` | Default `false`; after connecting → `IllegalStateException` |
| **HTTP method** | `HttpURLConnection.setRequestMethod("POST")` | Selects GET/POST/PUT/DELETE… as supported by API | Must be before connecting; not on generic URLConnection |
| **Body streaming mode** | `setFixedLengthStreamingMode(...)` or `setChunkedStreamingMode(...)` | Specifies how to send request body without buffering it all internally | HttpURLConnection only; must be set before connecting |
| **HTTP redirects** | `setInstanceFollowRedirects(false)` | Selects per-instance redirect following policy | Should be set before sending request |
| **Use caches** | `setUseCaches(false)` | Controls caching supported by the protocol handler | Not a way to control HTTP response cache at every layer |

**Regarding timeout setters:** The `setConnectTimeout` and `setReadTimeout` Javadoc describes setting the value and checking for negative numbers, and **does not guarantee that all providers throw `IllegalStateException` if called late**. However, calling them before connecting/reading remains the proper implementation rule, because changing them after I/O has started is not a reliable way to apply timeouts retroactively.

**Regarding default values:** `doInput` defaults to true and `doOutput` defaults to false in Java 17. Do not automatically assume that `setDoOutput(true)` is equivalent to selecting the HTTP POST method; explicitly specify `setRequestMethod("POST")` when POST is needed.

## 3. Connect timeout and read timeout are two different kinds of limits

### 3.1. setConnectTimeout — waiting to create the communications link

~~~java
conn.setConnectTimeout(2_000); // milliseconds
~~~

The value `2_000` means **2,000 ms = 2 seconds**, not 2,000 seconds. If a standard provider cannot establish a connection within this time, it may throw `java.net.SocketTimeoutException`.

This limit does **not** automatically protect the entire HTTP processing lifecycle. Once the TCP connection is established and the server is slow to generate a response, the connect timeout is no longer the relevant limit.

### 3.2. setReadTimeout — waiting for bytes during a read operation

~~~java
conn.setReadTimeout(3_000); // milliseconds
~~~

If an `InputStream.read(...)` operation waits too long for data, the provider typically throws `SocketTimeoutException`. With HTTP, this wait can occur while reading response headers or the response body, depending on the implementation.

**Read timeout is not a "whole-request deadline".** A response that trickles small amounts of data steadily before each timeout expiration can drag on for a very long time. If business logic requires a maximum total time of 10 seconds for the entire operation, you must organize **deadline/cancellation** and cleanup yourself; the two socket timeouts alone do not guarantee a wall-clock deadline across DNS, redirects, upload, download, and application processing.

### 3.3. Zero and negative values

| Call | Meaning |
| --- | --- |
| `setConnectTimeout(0)` | No connect timeout limit for this option |
| `setReadTimeout(0)` | No data wait timeout limit for this option |
| `setConnectTimeout(-1)` | `IllegalArgumentException` |
| `setReadTimeout(-5)` | `IllegalArgumentException` |

Some non-standard implementations may ignore timeout settings; `getConnectTimeout()` and `getReadTimeout()` report the value configured on the object, **not proof that the entire network operation has an SLA equal to that number**.

**Practical recommendation:** Choose positive timeouts grounded in your API/SLA, and do not leave them at 0 unintentionally. Log the timeout type and failing phase; do not retry infinitely, especially for POST requests with side effects.

## 4. Request property: setting HTTP headers before connect

In `URLConnection`, "request property" is the generic mechanism for supplying outgoing properties; for HTTP, many properties correspond to **request headers**.

~~~java
URLConnection conn = url.openConnection();
conn.setRequestProperty("Accept", "application/json");
conn.setRequestProperty("User-Agent", "JavaNetworkLesson/1.0");
conn.setRequestProperty("X-Trace-Id", "request-123");
~~~

This is a snippet: `url` must be declared, and `setRequestProperty` must be called **before connecting**.

There are two easily confused methods:

~~~java
conn.setRequestProperty("Accept", "text/plain");
// Overwrites the key's value if the key was already set.

conn.addRequestProperty("Accept", "application/json");
// Appends a value for the same key instead of overwriting.
~~~

With HTTP, not every header allows arbitrary multiple instances; the HTTP standard typically uses comma-separated lists for headers that support multiple values. Do not misuse `addRequestProperty` to add multiple `Authorization`, `Content-Length`, or `Host` headers.

**Do not mix up request headers and response headers:**
- Before connecting, use `setRequestProperty("Accept", ...)` or `addRequestProperty(...)`.
- After receiving the response, use `getHeaderField("Content-Type")`, `getHeaderFields()`, `getContentType()`.
- `getRequestProperty(...)` and `getRequestProperties()` are also APIs for reading **pre-connect request configuration**; per the Javadoc, they throw `IllegalStateException` if already connected.
- `getHeaderField("Content-Type")` is not a way to read back a request property.

A safety note: the header name must not be `null`; `setRequestProperty(null, ...)` causes a `NullPointerException`. Protocol handlers may reject or specially manage restricted headers. Do not trust unvalidated input data when constructing headers, to avoid CR/LF injection and credential leaks.

### Content-Type vs. Accept

| Header | Typically describes | Example |
| --- | --- | --- |
| `Accept` | Which response representation the client wants to receive | `application/json` |
| `Content-Type` | Data type of the **request body** being sent | `application/json; charset=utf-8` |
| `Authorization` | Credentials attached to the request | `Bearer …`, must be kept secret |
| `If-None-Match` | Conditional GET via ETag | `"etag-value"` |
| `User-Agent` | Client metadata | `JavaNetworkLesson/1.0` |

Do not manually set `Content-Length` using a String's character count; when sending UTF-8 with diacritics, the byte length can be longer than the String length. If using `HttpURLConnection.setFixedLengthStreamingMode(...)`, you must pass the actual **byte count**.

## 5. Input/Output direction: setDoInput and setDoOutput

**`setDoInput(boolean)`** states that the application intends to read from the URL connection via `getInputStream()`. **`setDoOutput(boolean)`** states that the application intends to write data via `getOutputStream()`.

| Scenario | doInput | doOutput | Meaning |
| --- | --- | --- | --- |
| HTTP GET reading response | true | false | Default is usually suitable |
| HTTP POST with request body and reading response | true | true | Both sends request body and receives response |
| Sending data without needing to read response | false or true depending on protocol | true | HTTP still needs to understand status/cleanup; usually should read response |
| Neither reading nor writing body | false | false | Only meaningful for certain specific protocols/operations; not for normal GET |

**Input/output direction is not the HTTP method.** Example:

~~~java
HttpURLConnection http =
        (HttpURLConnection) url.openConnection();

http.setRequestMethod("POST");
http.setDoOutput(true);
http.setDoInput(true);
~~~

This is a snippet for `http/https` URLs; `HttpURLConnection` is a subclass of `URLConnection`. `setDoOutput(true)` **does not automatically send a body** and does not guarantee every `URLConnection` understands POST. You must still call `getOutputStream()` and write bytes.

**Defaults in URLConnection:**
- `getDoInput()` → true.
- `getDoOutput()` → false.
- If you call `getOutputStream()` when output is not enabled, the provider may throw an error; do not expect the flag to turn on automatically.
- If input is set to false, do not try to read the response via `getInputStream()` and expect it to succeed.

**Do not set `setDoInput(false)` just because "I am sending a POST".** An HTTP POST still typically needs to read the status code, headers, and response/error body. For typical client programs, `doInput` should be true.

## 6. How do explicit connect() and implicit connect differ?

After creating a `URLConnection`, you can call:

~~~java
conn.connect();
~~~

to open the communication link if not yet connected. However, you are **not required** to call this method:

~~~java
try (InputStream input = conn.getInputStream()) {
    // Retrieve data: implementation connects implicitly if needed.
}
~~~

Similarly, `getOutputStream()` to write the request body can initiate the connection; `HttpURLConnection.getResponseCode()` needs the HTTP response so it can trigger sending the request and reading the status. Some operations that read response metadata on `URLConnection` can also implicitly connect, such as `getContentLength()`, `getContentType()`, or `getHeaderField()`.

Therefore, the **wrong** order:

~~~java
URLConnection conn = url.openConnection();
InputStream in = conn.getInputStream();   // May already be connected.
conn.setRequestProperty("Accept", "application/json"); // Too late!
~~~

In Java 17, calling `setRequestProperty` when connected throws `IllegalStateException`. Likewise, `setDoInput(...)` and `setDoOutput(...)` after connecting cause an error.

**The issue is not whether `connect()` is written or not.** It is the milestone of the **first I/O call that can connect**. Do not split setup and I/O across multiple methods without realizing a `getResponseCode` helper ran first.

### A seemingly harmless case

~~~java
URLConnection conn = url.openConnection();
String type = conn.getContentType(); // May cause an implicit connect.
conn.setDoOutput(true);              // Too late!
~~~

`getContentType()` serves response metadata and thus may trigger a connect. If you are unsure whether a method performs implicit I/O, complete **all setup before calling it**.

## 7. Complete Example 1 — GET with timeouts, headers, and input/output flags

The following program demonstrates:
1. `openConnection()` creates a URLConnection.
2. Before connecting, it prints the defaults `doInput=true` and `doOutput=false`.
3. It sets connect timeout 2000 ms, read timeout 3000 ms, `Accept`, and `X-Trace`.
4. Without calling `connect()` explicitly, `getInputStream()` receives the HTTP response from the local server.
5. After reading the response, it attempts to change a request header and output direction; both are rejected with `IllegalStateException`.

The `com.sun.net.httpserver.HttpServer` fixture only accepts `GET /inspect` and returns the structured string `GET|text/plain|lesson-231`. The output is deterministic and does not depend on the OS-chosen port.

Create file **`PreConnectGetDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URL;
import java.net.URLConnection;
import java.nio.charset.StandardCharsets;

public class PreConnectGetDemo {
    static void respond(HttpExchange ex) throws IOException {
        String method = ex.getRequestMethod();
        String accept = ex.getRequestHeaders().getFirst("Accept");
        String trace = ex.getRequestHeaders().getFirst("X-Trace");

        byte[] body = (method + "|" + accept + "|" + trace)
                .getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(200, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/inspect", ex -> {
            try {
                respond(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            URL url = new URL("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/inspect");
            URLConnection connection = url.openConnection();

            System.out.println("Initial doInput/doOutput: "
                    + connection.getDoInput()
                    + "/" + connection.getDoOutput());

            // All configuration must be performed right now.
            connection.setConnectTimeout(2000);
            connection.setReadTimeout(3000);
            connection.setDoInput(true);
            connection.setDoOutput(false);
            connection.setRequestProperty("Accept", "text/plain");
            connection.setRequestProperty("X-Trace", "lesson-231");

            System.out.println("Configured connect/read: "
                    + connection.getConnectTimeout() + "/"
                    + connection.getReadTimeout() + " ms");

            // Without calling connect() explicitly, getInputStream
            // triggers the connection if needed.
            try (InputStream in = connection.getInputStream()) {
                System.out.println("Response: " + new String(
                        in.readAllBytes(), StandardCharsets.UTF_8));
            }

            boolean propRejected = false;
            try {
                connection.setRequestProperty("X-Trace", "late");
            } catch (IllegalStateException expected) {
                propRejected = true;
            }

            boolean directionRejected = false;
            try {
                connection.setDoOutput(true);
            } catch (IllegalStateException expected) {
                directionRejected = true;
            }

            System.out.println("Late request property rejected: "
                    + propRejected);
            System.out.println("Late direction change rejected: "
                    + directionRejected);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 PreConnectGetDemo.java
java PreConnectGetDemo
~~~

**Verified execution output on the JVM with the standard HTTP handler:**

~~~text
Initial doInput/doOutput: true/false
Configured connect/read: 2000/3000 ms
Response: GET|text/plain|lesson-231
Late request property rejected: true
Late direction change rejected: true
~~~

### Result Breakdown

- Line 1 proves the defaults `doInput=true, doOutput=false`.
- Line 2 shows timeouts are stored in **milliseconds**, not seconds.
- The response has three parts read by the server from the **actual HTTP request**; thus `setRequestProperty` before connect took effect.
- The program did not call `connection.connect()`: `getInputStream()` performed the necessary I/O phase automatically.
- The final two `true` lines prove the connection has now transitioned to the connected state and the corresponding setters are no longer valid.

**Do not interpret this demo as a timeout measurement:** The local server responds very quickly. Seeing 2000/3000 only proves the configuration was set; you need a controlled delayed server/network if you want to test `SocketTimeoutException`.

**Educational example note:** `InputStream.readAllBytes()` is used because the local response is very small. In production, read in chunks and cap total bytes to avoid exhausting memory with a peer-controlled body.

## 8. HTTP POST: setting method, output direction, Content-Type, and body length before connecting

For an HTTP POST with a request body, configure in this order:

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();

conn.setConnectTimeout(2000);
conn.setReadTimeout(3000);
conn.setRequestMethod("POST");
conn.setDoOutput(true);
conn.setDoInput(true);
conn.setRequestProperty(
        "Content-Type", "application/json; charset=utf-8");

byte[] payload = json.getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(payload.length);

// Now obtain the stream to send bytes.
try (OutputStream out = conn.getOutputStream()) {
    out.write(payload);
}

int code = conn.getResponseCode();
// Then read the input/error stream based on status.
~~~

**This is a snippet**, requiring `url/json` declarations, imports, and error cleanup. It is not a standalone runnable class. Use `setRequestMethod("POST")` explicitly to avoid relying on implementation behavior that might automatically switch GET to POST when output is requested.

**Important order:**
1. Create the HTTP-specific connection instance.
2. Set timeouts/method/input-output/request headers.
3. If streaming a large body or avoiding internal buffering, set the body streaming mode.
4. **Only then** call `getOutputStream()` and write bytes.
5. Close/flush the output stream before awaiting the response so the server knows the request body has ended according to framing.
6. Call `getResponseCode()`, then read the appropriate response stream.
7. Close streams and call `disconnect()` in `finally`.

**If `setDoOutput(true)` is placed after `getOutputStream()`:** You requested the output stream while the output flag was not yet enabled; an I/O or protocol error typically occurs. If you only set request headers after obtaining the output stream, the headers may be rejected because the connection has already started.

## 9. setFixedLengthStreamingMode and setChunkedStreamingMode

When sending an HTTP request body, `HttpURLConnection` provides specific buffering/streaming mechanisms.

### 9.1. Body with known size

~~~java
byte[] body = "hello-java".getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(body.length);
~~~

`body.length` is the **byte count**. When fixed-length streaming is enabled, you must write the **exact** number of declared bytes. Writing more or closing the stream before writing enough can throw an exception. For UTF-8 content with Vietnamese characters, do not use `String.length()` as `Content-Length`.

### 9.2. Body with unknown size beforehand

~~~java
conn.setChunkedStreamingMode(8192);
~~~

When appropriate, an HTTP/1.1 request body can be sent using chunked transfer encoding without buffering the entire payload. However:
- Some servers/proxies do not handle chunked request bodies well.
- Do not enable both fixed-length and chunked streaming modes on the same connection.
- These methods must be called before connecting.
- Per the `HttpURLConnection` Javadoc, when output streaming mode is enabled, **authentication and redirects may not be handled automatically**, and `HttpRetryException` may occur when reading the response if a retry is needed due to authentication/redirect.
- Do not implement `multipart/form-data` solely by calling `setChunkedStreamingMode`: the application-layer content format must still be valid.

### 9.3. Why might streaming be needed?

If sending a large file, buffering the entire request body in memory puts pressure on the heap. Streaming mode allows transmitting data incrementally. However, if a request is not idempotent and fails mid-way, you **cannot** assume the server has not processed anything; you need a retry policy/idempotency at the business layer.

The local POST example below chooses fixed-length streaming because the body is only 10 bytes and its content is known.

## 10. getResponseCode, getInputStream, and getErrorStream

Generic `URLConnection` has stream and metadata methods, while HTTP-specific status/error methods reside on `HttpURLConnection`.

| Need to retrieve | API | Notes |
| --- | --- | --- |
| HTTP status | `HttpURLConnection.getResponseCode()` | May trigger I/O/implicit connect |
| Success response | `conn.getInputStream()` | Reads body; for 4xx/5xx may throw `IOException` |
| HTTP error response | `conn.getErrorStream()` | May be `null` if there is no error body or no response yet |
| Response content type | `conn.getContentType()` | Response metadata, not a request header |
| HTTP response headers | `conn.getHeaderFields()` | May trigger implicit connect |
| Close logical link | `conn.disconnect()` | HTTP-specific; not a generic URLConnection method |

Handling example:

~~~java
int status = conn.getResponseCode();
InputStream responseStream =
        status >= 400 ? conn.getErrorStream() : conn.getInputStream();

if (responseStream != null) {
    try (InputStream in = responseStream) {
        byte[] response = in.readAllBytes();
        // Only use readAllBytes when sure the body is small; production needs limits.
    }
}

conn.disconnect();
~~~

This is a **snippet**, requiring `conn` to be an `HttpURLConnection`. Do not equate an HTTP error status like 422 with a connection error: the server sent a valid HTTP response. Use `getErrorStream()` to read the body containing error details if present, but always check for `null`.

HTTP redirects can cause the URL handler to perform additional network I/O if enabled. Do not assume `setConnectTimeout` is a total limit across all redirects or all retries.

## 11. Complete Example 2 — POST with body, then reading HTTP error body

The program **`PreConnectPostDemo.java`** uses a local HTTP server with two endpoints:
- `POST /echo` receives a text body and returns HTTP 201 with `METHOD|CONTENT_TYPE|BODY`.
- `GET /reject` returns HTTP 422 and body `invalid-request`.

The client creates **a new HttpURLConnection for each HTTP request**, configures everything before opening I/O, uses `setFixedLengthStreamingMode` for POST, and reads errors using `getErrorStream()`.

Create file **`PreConnectPostDemo.java`**:

~~~java
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

public class PreConnectPostDemo {
    static void reply(
            HttpExchange ex, int status, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        ex.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(bytes);
        }
    }

    static void handle(HttpExchange ex) throws IOException {
        if (ex.getRequestURI().getPath().equals("/echo")) {
            String method = ex.getRequestMethod();
            String type = ex.getRequestHeaders()
                    .getFirst("Content-Type");
            String body = new String(
                    ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            reply(ex, 201, method + "|" + type + "|" + body);
        } else {
            reply(ex, 422, "invalid-request");
        }
    }

    static HttpURLConnection open(URL url, String method)
            throws IOException {
        HttpURLConnection conn =
                (HttpURLConnection) url.openConnection();

        // Configure BEFORE getOutputStream/getResponseCode/connect.
        conn.setConnectTimeout(2000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        conn.setDoInput(true);
        return conn;
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/", ex -> {
            try {
                handle(ex);
            } catch (IOException error) {
                ex.close();
            }
        });
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            HttpURLConnection post =
                    open(new URL(base + "/echo"), "POST");

            try {
                post.setDoOutput(true);
                post.setRequestProperty(
                        "Content-Type", "text/plain; charset=utf-8");

                byte[] payload = "hello-java"
                        .getBytes(StandardCharsets.UTF_8);
                post.setFixedLengthStreamingMode(payload.length);

                try (OutputStream out = post.getOutputStream()) {
                    out.write(payload);
                }

                System.out.println(
                        "POST status: " + post.getResponseCode());

                try (InputStream in = post.getInputStream()) {
                    System.out.println("POST body: " + new String(
                            in.readAllBytes(), StandardCharsets.UTF_8));
                }
            } finally {
                post.disconnect();
            }

            HttpURLConnection err =
                    open(new URL(base + "/reject"), "GET");

            try {
                System.out.println(
                        "Error status: " + err.getResponseCode());

                InputStream stream = err.getErrorStream();
                if (stream != null) {
                    try (InputStream in = stream) {
                        System.out.println("Error body: " + new String(
                                in.readAllBytes(),
                                StandardCharsets.UTF_8));
                    }
                } else {
                    System.out.println("Error body: (none)");
                }
            } finally {
                err.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Run with Java 17+:

~~~bash
javac -encoding UTF-8 PreConnectPostDemo.java
java PreConnectPostDemo
~~~

**Output when the HTTP fixture responds as designed:**

~~~text
POST status: 201
POST body: POST|text/plain; charset=utf-8|hello-java
Error status: 422
Error body: invalid-request
~~~

### Analysis

1. `open(url,method)` creates a new object and sets connect/read timeouts, redirect policy, HTTP method, and `doInput` **before** any I/O.
2. For POST, `setDoOutput(true)` is called **before** `getOutputStream()`.
3. `Content-Type` is set while the request is not yet connected; the server receives the exact header.
4. `payload.length` passed to fixed-length streaming mode is 10 ASCII bytes. If the payload contains Unicode, the byte count must come from the array after UTF-8 encoding.
5. `getOutputStream()` initiates sending the body; after closing output, `getResponseCode()` receives HTTP 201 and `getInputStream()` reads successfully.
6. Another request to `/reject` receives HTTP 422. The program uses `getErrorStream()` instead of trying to read the error body via `getInputStream()`.
7. Each HttpURLConnection has its own request lifecycle; `disconnect()` in `finally` is the cleanup operation for the HTTP-specific connection object.

The HTTP server is built with `jdk.httpserver` for testing only; it is not a production server framework. It reads the entire request body under test control. A public server must limit body size and handle malicious input scenarios.

## 12. Common wrong operation sequences

### Mistake 1: setting header after getInputStream

~~~java
URLConnection conn = url.openConnection();
InputStream in = conn.getInputStream();
conn.setRequestProperty("Accept", "application/json");
~~~

**Why it is wrong:** `getInputStream()` can connect implicitly. The subsequent `setRequestProperty` call hits `IllegalStateException`.

**Fix:** Set request headers before `getInputStream()`.

### Mistake 2: calling connect() then changing direction

~~~java
URLConnection conn = url.openConnection();
conn.connect();
conn.setDoOutput(true);
~~~

**Why it is wrong:** `setDoOutput` belongs to pre-connect configuration. Changing it after `connect` is rejected.

**Fix:** Determine whether you want to write a body and set the flag before connecting.

### Mistake 3: not enabling output before getting the output stream

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
conn.setRequestMethod("POST");
// Missing conn.setDoOutput(true)
try (OutputStream out = conn.getOutputStream()) {
    out.write(payload);
}
~~~

**Why it is wrong:** `doOutput` defaults to false; a request body requires output to be enabled. Set `setDoOutput(true)` before `getOutputStream()`.

### Mistake 4: setDoOutput(true) and assuming the method automatically becomes POST

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
conn.setDoOutput(true);
~~~

This **only changes I/O direction**, not a generic API way of declaring the HTTP method choice. Some HTTP handlers may automatically switch GET to POST when output is requested, but relying on that makes code hard to understand and implementation-dependent. **Fix:** Call `conn.setRequestMethod("POST")` explicitly before I/O.

### Mistake 5: reversing read and write order in POST

~~~java
HttpURLConnection conn = ...; // already configured POST/doOutput
int status = conn.getResponseCode();
try (OutputStream out = conn.getOutputStream()) {
    out.write(payload);
}
~~~

**Why it is wrong:** `getResponseCode()` can start/send the HTTP request while the body has not yet been provided, making the subsequent write too late. **Fix:** Write/close the output stream before reading the status and response.

### Mistake 6: forgetting the read timeout

~~~java
conn.setConnectTimeout(1000);
// Read timeout not set.
~~~

**Why it is wrong:** TCP may connect quickly, but the server returns no bytes; the thread remains blocked on read. **Fix:** Set both timeout types according to your latency budget.

### Mistake 7: mistakenly using String.length() as Content-Length

~~~java
String body = "Tiếng Việt";
conn.setFixedLengthStreamingMode(body.length()); // May be wrong!
~~~

**Why it is wrong:** Java String length is not the UTF-8 byte count. **Fix:**

~~~java
byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
conn.setFixedLengthStreamingMode(bytes.length);
~~~

### Mistake 8: ignoring getErrorStream

~~~java
int status = conn.getResponseCode();
try (InputStream in = conn.getInputStream()) {
    // For 4xx status, the implementation may throw IOException.
}
~~~

**Fix:** For HTTP error statuses, read `getErrorStream()` if non-null; still distinguish valid HTTP errors from network errors.

The snippets in this section are **illustrative error/fix code**, not standalone programs; do not copy anti-patterns verbatim into production.

## 13. Errors and exceptions to handle

| Exception/scenario | Commonly occurs when | Handling approach |
| --- | --- | --- |
| `IllegalStateException` | Setting `doInput/doOutput` or request headers after connect; setting streaming mode too late | Fix setup order, create a new connection object |
| `IllegalArgumentException` | Negative timeout or negative fixed-length body length | Validate input configuration before creating request |
| `SocketTimeoutException` | Timeout when opening link or waiting for bytes in read | Classify phase, close/clean up streams, retry per policy |
| `UnknownHostException` | DNS cannot resolve host | Check hostname, DNS/network; do not retry infinitely |
| `ConnectException` | Cannot establish TCP connection | Check service/port/network; appropriate backoff |
| `ProtocolException` | Invalid/unsupported HTTP method or unable to change method | Use a valid method and set before I/O |
| `HttpRetryException` | Output streaming mode where redirect/authentication requires retry | Handle intentionally; do not assume handler replays body automatically |
| `IOException` when reading normal body on HTTP 4xx/5xx | Server returns HTTP error response | Check status, `getErrorStream` may contain body |
| `IOException` when writing/reading | Peer closes connection, connection reset, stream error | Clean up, do not assume server did not process request |
| Valid HTTP 404/422/500 | Server returns response with error status code | Do not confuse with `connect timeout`; handle in business logic |

**Do not swallow exceptions and continue using the same `HttpURLConnection` for another request.** One `HttpURLConnection` represents one request; create a new instance for another send. The underlying TCP connection may be reused by the implementation, but that is the protocol handler's job.

**Do not retry POST immediately after a timeout without understanding idempotency.** The server may have already received and processed the body even though the client could not read the response. For operations with side effects, use an idempotency key or server-supported mechanism to avoid duplicate processing.

## 14. Resource lifecycle: streams, disconnect, and connection reuse

When using URLConnection/HttpURLConnection:

- Close `InputStream` after reading or on error.
- Close `OutputStream` after finishing writing the body, before reading the response according to HTTP flow.
- With HttpURLConnection, call `disconnect()` in `finally` if you want to release the logical connection context.
- Do not assume `disconnect()` always closes the physical socket immediately: Java's HTTP handler may use a keep-alive/persistent connection pool; the Javadoc describes that `disconnect()` may close the underlying socket if it is idle.
- Do not reuse an `HttpURLConnection` for a new request by changing headers/method on an already-connected object. Create a new `openConnection()`.

Pattern example (snippet):

~~~java
HttpURLConnection conn =
        (HttpURLConnection) url.openConnection();
try {
    conn.setConnectTimeout(2000);
    conn.setReadTimeout(3000);
    conn.setRequestMethod("GET");
    conn.setDoInput(true);

    int status = conn.getResponseCode();
    InputStream selected = status >= 400
            ? conn.getErrorStream() : conn.getInputStream();

    if (selected != null) {
        try (InputStream in = selected) {
            // Process data with size bounds.
        }
    }
} finally {
    conn.disconnect();
}
~~~

Generic `URLConnection` does not have a `disconnect()` method; that is an API of HttpURLConnection and certain subclasses. If using a `file:` URL or another protocol, cleanup depends on how the implementation provides streams.

### Do not use readAllBytes for large untrusted data

In the two local programs, the responses are small and fixed. In practice, if a response body can be large, use a buffer and a limit:

~~~java
byte[] buffer = new byte[8192];
long total = 0;
int n;
while ((n = in.read(buffer)) != -1) {
    total += n;
    if (total > MAX_BYTES) {
        throw new IOException("Body too large");
    }
    // Consume buffer[0..n) chunk by chunk.
}
~~~

This is a snippet; `in`, `MAX_BYTES`, and output handling must be declared. Choosing timeouts allows measuring *wait time for data* and does not replace a **total byte limit** to prevent OOM/disk exhaustion.

## 15. Proxies, redirects, HTTPS, and securing request properties

`URLConnection` is often used to call HTTP/HTTPS endpoints, so there are several boundaries to keep in mind.

**Proxy:** You can use `URL.openConnection(Proxy)` if you want to specify a route for that request instead of changing the JVM-wide proxy configuration. A proxy may require authentication or could forward requests to another host. **Do not use an untrusted proxy to transmit sensitive credentials** without evaluating the threat model.

**Redirects:** `HttpURLConnection.setInstanceFollowRedirects(false)` helps the application control automatic host/path switching. If redirects are allowed, a request may travel to another URL, requiring verification of destination/credentials/SSRF policy. Avoid using static `HttpURLConnection.setFollowRedirects(...)` to "temporarily change" the policy in multithreaded systems because it is a class-level setting with wide impact.

**HTTPS:** For `https:`, the handler is typically `HttpsURLConnection`. It implements TLS according to trust/hostname verification configuration; do not disable certificate or hostname verification just to bypass errors. `setConnectTimeout` and `setReadTimeout` **do not create** a guaranteed total deadline for DNS + proxy + TLS + upload + response.

**Authorization and Cookie:** If you need to send:

~~~java
conn.setRequestProperty(
        "Authorization", "Bearer " + token);
~~~

this is a snippet; only use it when the token is obtained from a secure source. This header contains a secret and must be set **before connecting**. Do not log the raw header, and do not use a mutable global variable holding the current user's token shared across concurrent HTTP requests. Cookie and Authorization can carry user identity; create a separate URLConnection per request and maintain clear tenant boundaries.

**SSRF:** If the `URL` comes from untrusted data, the backend could be forced to send requests to localhost, cloud metadata services, or private networks. Validate the scheme (http/https), host allowlist, DNS/IP/private ranges, proxy path, and post-redirect destinations. Do not rely on timeouts to consider fetching arbitrary URLs safe.

**Header injection:** Do not concatenate unvalidated header values containing CR/LF or control characters; API implementations may reject some malformed forms, but that does not replace application-layer validation.

## 16. URLConnection and HttpURLConnection: different API scopes

`URLConnection` is the **abstract superclass** for communicating with URL-addressed resources. `URL.openConnection()` may return a subclass depending on the scheme/provider. For HTTP/HTTPS, you typically work with `HttpURLConnection` / `HttpsURLConnection`.

| API | URLConnection | HttpURLConnection |
| --- | --- | --- |
| Timeouts `setConnectTimeout/setReadTimeout` | Yes | Inherited |
| Direction `setDoInput/setDoOutput` | Yes | Inherited |
| Request properties | Yes | Inherited, HTTP headers per implementation |
| `connect/getInputStream/getOutputStream` | Yes | Inherited |
| `setRequestMethod` | No | Yes |
| `getResponseCode` | No | Yes |
| `getErrorStream` | No | Yes |
| `disconnect` | No | Yes |
| Streaming modes | No | Yes |

Do not cast every `URLConnection` to `HttpURLConnection`:

~~~java
URLConnection conn = url.openConnection();

if (conn instanceof HttpURLConnection http) {
    http.setRequestMethod("GET");
}
~~~

This is a Java 17 snippet using pattern matching for `instanceof`. For `file:` or `jar:` URLs, a direct cast can cause `ClassCastException`. Exercises targeting HTTP endpoints may cast after verifying scheme/handler, but general-purpose library code should check.

### Caching and doInput/doOutput are not equivalent

`setUseCaches(boolean)` only tells the protocol handler whether it may use a caching mechanism it supports. It does not mean `GET` is idempotent, does not replace server `Cache-Control` directives, and does not isolate users in an application cache.

`setDoInput/DoOutput` only declares the need to read/write streams. HTTP methods remain GET/POST/PUT/DELETE per the protocol. Do not use `setDoOutput(true)` to "pick a method" or `setDoInput(false)` to "automatically ignore status".

## 17. When should you use java.net.http.HttpClient instead of URLConnection?

When building a new HTTP client on Java 11+ / Java 17+, the **`java.net.http`** module is usually more convenient:
- `HttpClient` has a builder API, connect timeout, redirect policy, and HTTP/2 preference.
- `HttpRequest` describes the URI, method, request headers, body publisher, and per-request timeout.
- `HttpResponse<T>` has typed BodyHandlers to read String, bytes, file, or discard.
- `sendAsync` returns a `CompletableFuture` for asynchronous coordination.

Example:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(2))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(5))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

This is a snippet with imports from `java.net.http.*` and `java.time.Duration`. **Do not confuse**:
- `HttpClient.Builder.connectTimeout(...)` with `URLConnection.setConnectTimeout(int)`.
- `HttpRequest.Builder.timeout(Duration)` with `URLConnection.setReadTimeout(int)`: the semantics are not completely equivalent.
- `HttpRequest.Builder.header(...)` with `URLConnection.setRequestProperty(...)`.
- `HttpRequest.BodyPublisher` with `URLConnection.setDoOutput(true)`.
- `HttpClient.send/sendAsync` with manual I/O via `getInputStream/getOutputStream`.

**However, URLConnection is still worth learning** because it exists in longstanding Java codebases, supports several non-HTTP protocols, and helps build a clear understanding of **pre-connect configuration** and I/O lifecycle. When maintaining legacy systems, setter ordering bugs are a direct cause of hard-to-detect runtime errors.

## 18. Code review checklist before calling connect/getInputStream/getOutputStream

| Question | Status to verify |
| --- | --- |
| Is the object created from a URL with the right scheme/host? | No SSRF or wrong protocol cast |
| Is a positive `setConnectTimeout(ms)` set? | Link establishment is bounded |
| Is a positive `setReadTimeout(ms)` set? | Each wait for bytes is bounded |
| Are all request headers set? | Valid `Accept`, `Content-Type`, auth, trace ID |
| Is `setRequestProperty` used appropriately for the header? | Set replaces value; add only when header allows |
| Are `doInput/doOutput` decided? | GET input, POST body output+input |
| Is `setRequestMethod` set explicitly? | POST/PUT/DELETE as supported by API |
| Are body bytes encoded properly? | Byte length, charset, and content type match |
| Is fixed-length/chunked mode set before connect? | Not changed after obtaining output stream |
| Is any API implicitly called before configuration? | No early `getResponseCode/getContentType/getInputStream` |
| Are HTTP error statuses classified? | `getErrorStream` may be null |
| Are streams closed? | Try-with-resources, cleanup in finally |
| Is the HTTP-specific object disconnected? | Do not reuse instance as a new request |
| Are body size/retries/redirects bounded? | Prevents OOM/SSRF/retry storms |
| Are secrets in request properties protected? | No credential logging, no cross-tenant mixing |

## 19. Common errors and fixes

| Error | Cause | Fix |
| --- | --- | --- |
| `IllegalStateException` on `setRequestProperty` | Called after connected | Set request properties before any I/O |
| `IllegalStateException` on `setDoOutput` | `connect()` or implicit connect already occurred | Set output flag right after `openConnection()` |
| `getOutputStream()` fails | `doOutput` not enabled | `setDoOutput(true)` beforehand |
| HTTP POST sends wrong method | Relied only on `setDoOutput(true)` | Explicitly call `setRequestMethod("POST")` |
| Server receives wrong Content-Type | Header set too late or wrong charset declared | Set before connect; align encoding and header |
| POST body missing/corrupted | Wrong fixed-length declared or stream not closed | Use `payload.length`, write all bytes then close |
| Connection succeeds but read hangs | Only connect timeout set | Add read timeout |
| Treating `readTimeout` as total request time | Server sends data bit by bit so request drags on | Design a separate overall deadline |
| Timeout 0 thinking it means "immediate" | Value 0 means infinite | Use a positive ms number |
| `SocketTimeoutException` then blindly retrying POST | Unknown whether server already processed it | Idempotency/retry policy |
| HTTP 422 but `getInputStream()` errors | Error body is in error stream | Read response code, `getErrorStream()` if present |
| Calling `getRequestProperty` after connect | API is pre-connect only | Save needed metadata before connecting |
| Using HTTP methods on non-HTTP URLConnection | Wrong subclass cast | Check scheme/type |
| Using static follow-redirects for one request | Changes behavior for other requests | `setInstanceFollowRedirects(...)` |
| Keeping one HttpURLConnection to send multiple requests | Mutating connected state is invalid | One connection instance per HTTP request |
| Not closing input/error/output stream | Resource leak/holding connection | Try-with-resources and disconnect |
| Using `readAllBytes()` for unbounded responses | OOM | Bounded streaming and size limits |
| Logging `Authorization`/Cookie | Secrets leaked | Mask/redact, isolate user context |
| Allowing untrusted URLs to fetch freely | SSRF, internal network access | Allowlist, validate redirects and outbound policy |

## 20. Self-check questions

**1.** Does `URL.openConnection()` mean a connection to the HTTP server is already established?  
**Answer:** No. It creates a URLConnection object for configuration. Afterward, `connect()` or I/O may establish the connection.

**2.** Why must request properties be set before `getInputStream()`?  
**Answer:** Because `getInputStream()` can implicitly connect; afterward, `setRequestProperty` may throw `IllegalStateException`.

**3.** Is `setConnectTimeout(2000)` 2000 seconds or 2000 ms?  
**Answer:** **2000 milliseconds = 2 seconds**.

**4.** The TCP connection succeeded, but the server sends no bytes. How does connect timeout help?  
**Answer:** It does not bound the read phase; `setReadTimeout` is needed to limit how long to wait for data.

**5.** Does `setReadTimeout(3000)` guarantee the entire response finishes within three seconds?  
**Answer:** No. It is a timeout for a read operation waiting for bytes, not a total request deadline.

**6.** Does a timeout value of 0 mean immediate timeout?  
**Answer:** No, the Javadoc interprets 0 as an infinite wait time for the corresponding option.

**7.** What are the default `doInput/doOutput` values of URLConnection?  
**Answer:** `doInput=true`, `doOutput=false`.

**8.** To send a POST with a body and read the response, what settings are needed?  
**Answer:** `HttpURLConnection.setRequestMethod("POST")`, `setDoOutput(true)`, `setDoInput(true)`, timeouts, and request headers before obtaining the output stream; write/close the body, then read the status/response.

**9.** How do `setRequestProperty` and `addRequestProperty` differ?  
**Answer:** Set overwrites an existing key; add appends a value. Do not use add arbitrarily with headers that do not allow multiple values.

**10.** Does `setFixedLengthStreamingMode(...)` take Java chars or UTF-8 bytes?  
**Answer:** The number of **bytes** to send; obtain it from the byte array after encoding.

**11.** If the server returns HTTP 422, where do you read the error body?  
**Answer:** With HttpURLConnection, read `getErrorStream()` if non-null after checking the status.

**12.** What can calling `getContentType()` before setting headers cause?  
**Answer:** It can trigger an implicit connect, making subsequent changes to request properties or I/O direction too late.

**13.** Does `URLConnection` have `getResponseCode()` and `disconnect()`?  
**Answer:** No. These are HTTP-specific methods on `HttpURLConnection`.

**14.** Is `setDoOutput(true)` always POST?  
**Answer:** It must not be treated as defining the HTTP method; call `setRequestMethod("POST")` explicitly.

**15.** Why shouldn't you use one HttpURLConnection to send three requests by changing headers three times?  
**Answer:** An already-connected object cannot have its setup changed for the next request; create a new instance per request.

**16.** What is the key difference when switching to `java.net.http.HttpClient`?  
**Answer:** HttpClient/HttpRequest uses builders, body publishers, and send/sendAsync; URLConnection uses mutable pre-connect configuration and directly manages input/output streams.

## Official References

- [Java SE 17 — URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): two setup/connect phases, `setConnectTimeout`, `setReadTimeout`, `setDoInput/Output`, `setRequestProperty`, implicit connect, and streams.
- [Java SE 17 — HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): HTTP method, response status, error stream, disconnect, streaming modes, and redirect policy.
- [Java SE 17 — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS/TLS subclass, SSL socket factory, and hostname verification.
- [Java SE 17 — SocketTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/SocketTimeoutException.html): timeout error when handling socket I/O.
- [Java SE 17 — HttpRetryException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html): cases where automatic retry is not possible after streaming a request body.
- [Java SE 17 — URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): creating URL/openConnection and protocol handlers.
- [Java SE 17 — InputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html) and [OutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/OutputStream.html): I/O stream lifecycle, close, read/write.
- [Java SE 17 — HttpClient (java.net.http)](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): modern HTTP client API, used when sendAsync/HTTP/2 is needed.
- [Java SE 17 — jdk.httpserver](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): `HttpServer` as the localhost fixture in both programs.
