# HttpURLConnection: method, status code, and error stream

*Java Advance – networking · URLConnection Group · Using Java 17+*

## 1. Key Takeaways

`java.net.HttpURLConnection` is the traditional HTTP API in the JDK, extending `java.net.URLConnection`. It lets you create HTTP requests, set the method and headers, read the HTTP status code, read the response body, and also provides `getErrorStream()` for **error response content sent by the server**.

**A very common mistake:** calling `getInputStream()` for every response, hitting an `IOException` on HTTP 404/500, and then concluding that the server **did not send a body**. In reality, the server may send a JSON/HTML payload containing error details. In `HttpURLConnection`, the body of an HTTP error response is typically accessed via **`getErrorStream()`**, not `getInputStream()`.

Three questions must be handled **separately**:

1. **HTTP method:** is the application sending `GET`, `POST`, `PUT`, `DELETE`, `HEAD`…? Is there a request body?
2. **HTTP status:** has the server returned `200`, `201`, `204`, `302`, `400`, `404`, `500`…? Could `getResponseCode()` read a status?
3. **Response body stream:** if successful, read `getInputStream()`; if an HTTP error occurred, check `getErrorStream()`, which **may be `null`**; if a network error occurred before an HTTP response, there may be **neither a status nor a body**.

~~~text
             URL.openConnection()
                     |
                     v
              HttpURLConnection
                     |
      set method / headers / timeouts
      setDoOutput / write request body
                     |
                     v
        connect / getOutputStream /
            getResponseCode
                     |
             HTTP response?
            /               \
           v                 v
   Has status code       DNS/TCP/TLS error/
   e.g. 200/404          timeout before headers
           |                 |
           v                 +--> IOException
   getResponseCode               usually no status
           |                      or error body
      +----+----+
      |         |
  2xx / ok     >=400
      |         |
getInputStream  getErrorStream()
      |         |  (may be null)
      +----+----+
           |
  consume/close stream
           |
       disconnect()
~~~

This diagram shows the **typical flow**, not a rule that all HTTP 3xx responses always have a success body or that all statuses >=400 always have an error body. You need to check the redirect policy and protocol for each case.

## 2. Differences Between URLConnection and HttpURLConnection

| Component | Role |
|---|---|
| `URL` / `URI` | Represents a resource address |
| `URL.openConnection()` | Creates a `URLConnection` object; does not by default prove a network connection has been made |
| `URLConnection` | Base API for connections, request properties, timeouts, input/output |
| `HttpURLConnection` | HTTP-specific API: method, status, redirect, error stream, streaming request body |
| `HttpsURLConnection` | Subclass for HTTPS, adding SSL/TLS-related APIs |
| `java.net.http.HttpClient` | Modern HTTP client (Java 11+), different API: `HttpRequest`, `HttpResponse`, `BodyHandlers`, supports HTTP/2 |

~~~java
// GET snippet; only cast when you know the URL uses HTTP/HTTPS.
URL url = URI.create("http://127.0.0.1:8080/status").toURL();
URLConnection base = url.openConnection();
if (!(base instanceof HttpURLConnection conn)) {
    throw new IllegalArgumentException("Not an HTTP URL");
}
conn.setRequestMethod("GET");
~~~

`HttpURLConnection` is designed for **one logical HTTP request per instance**, though the underlying HTTP persistent connection may be reused across multiple instances. **Do not create one object and then change its method to perform a second request on the same object.** Instead, create a new instance for another request.

The examples in this article use `HttpServer` on loopback so no Internet or proxy is required. When using `https://`, implementations typically return `HttpsURLConnection`, and TLS certificate/hostname verification must be handled properly.

## 3. Lifecycle: Configure Before Connecting

According to the `URLConnection` Javadoc, the typical process is:

1. Create the connection object via `URL.openConnection()`.
2. Configure `setRequestMethod`, `setRequestProperty`, `setDoOutput`, `setConnectTimeout`, `setReadTimeout`, redirect policy, and streaming mode.
3. The connection is opened **when a call requiring I/O** such as `connect()`, `getOutputStream()`, `getInputStream()`, or `getResponseCode()` needs to connect.
4. Read the status, response headers, and body.
5. Close the streams and call `disconnect()` in `finally`.

~~~text
CREATED
  |
  +-- setRequestMethod(...)
  +-- setRequestProperty(...)
  +-- setConnectTimeout(...) / setReadTimeout(...)
  +-- setInstanceFollowRedirects(...)
  +-- setDoOutput(...) / setFixedLengthStreamingMode(...)
  |
  v
CONNECTED (implicit or explicit)
  |
  +-- getResponseCode() / getResponseMessage()
  +-- getHeaderField(...)
  +-- getInputStream() or getErrorStream()
  |
  v
CONSUMED / CLOSED / DISCONNECTED
~~~

Many setters **cannot be called after the connection has been established**: depending on the setter, it may throw `IllegalStateException`, `ProtocolException`, or have no effect per the contract. Therefore, configure **everything before I/O**. In particular, `setRequestMethod(...)` is not an API for changing the method on an already-sent request.

**`connect()` does not always have to be called explicitly.** I/O methods will proactively open the connection if needed. Calling `openConnection()` only creates the object and **does not mean the server has received the request**.

## 4. HTTP Methods and setRequestMethod

### 4.1. Default Method and Accepted API List

`HttpURLConnection` has a default method of **GET**. Java SE 17 `setRequestMethod(String)` supports the following methods, subject to protocol restrictions:

| Method | Common Semantics | Notes |
|---|---|---|
| `GET` | Read a resource | Usually sends no request body |
| `POST` | Submit data / trigger an action | Use `setDoOutput(true)` and `getOutputStream()` when there is a body |
| `HEAD` | Same as GET for metadata, no response body | Do not try to read body content |
| `OPTIONS` | Query options / protocol capabilities | Execution restricted depending on the server |
| `PUT` | Put / replace a resource | Can send a body |
| `DELETE` | Request deletion of a resource | Do not infer deletion succeeded without checking the status |
| `TRACE` | Diagnostic trace | Often disabled due to security policy |
| `PATCH` | Valid HTTP method under modern standards | **Not in the Java 17 HttpURLConnection setRequestMethod list**, typically throws `ProtocolException` |

**Important:** The HTTP protocol may support more methods than the `HttpURLConnection` class. The Java 17 legacy API **does not accept PATCH via `setRequestMethod("PATCH")`** according to the official list. When you need PATCH, a custom method, or a modern API, you should use:

~~~java
// Java 17 snippet; requires importing HttpClient, HttpRequest, URI.
HttpRequest patch = HttpRequest.newBuilder(
        URI.create("https://api.example.test/items/7"))
    .method("PATCH", HttpRequest.BodyPublishers.ofString(
            "{\"name\":\"new\"}"))
    .header("Content-Type", "application/json")
    .build();
~~~

This is a snippet that **does not send a real request yet**. `java.net.http.HttpRequest.Builder.method` accepts custom methods according to its contract. Do not use reflection/hacks to mutate the internal `method` field of `HttpURLConnection` to "force PATCH", as it easily breaks on newer JDKs and is not portable.

### 4.2. setRequestMethod Must Be Called Before Connecting

~~~java
// Snippet, c is a newly created and not-yet-connected HttpURLConnection.
c.setRequestMethod("GET");
c.setRequestProperty("Accept", "application/json");
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
int status = c.getResponseCode(); // May initiate I/O.
~~~

After reading the status or body, do not reuse `c.setRequestMethod("POST")` to turn it into a second request. **One instance – one request**; create a new connection.

`getRequestMethod()` returns the configured method name, not proof that the server processed the corresponding logic. To know whether the server accepted the method, check `getResponseCode()`, such as `405 Method Not Allowed`, `501 Not Implemented`, or the API-specific status.

## 5. Sending a POST Body: setDoOutput and getOutputStream

A POST with a body is typically performed as:

~~~java
// Snippet, c was just opened and is not yet connected.
byte[] payload = "ping".getBytes(StandardCharsets.UTF_8);
c.setRequestMethod("POST");
c.setDoOutput(true);
c.setRequestProperty("Content-Type", "text/plain; charset=UTF-8");
c.setFixedLengthStreamingMode(payload.length);
try (OutputStream output = c.getOutputStream()) {
    output.write(payload);
}
int status = c.getResponseCode();
~~~

**Notes to remember:**

- `setDoOutput(true)` enables permission to write a request body; by default `URLConnection.doOutput` is **false**.
- **You should call `setRequestMethod("POST")` explicitly.** Some legacy implementations have behavior that switches the default GET to POST when output is requested, but relying on that side effect is unclear and should not be used as a programming interface.
- `Content-Type` describes the representation (`application/json`, `text/plain`…), not that the body matches the schema.
- `payload.length` is the **number of bytes**, not `String.length()`, which counts UTF-16 code units. With Vietnamese characters or emoji, the two values can differ significantly.
- `getOutputStream()` may **trigger the connection**. You must finish configuring the method, headers, timeouts, and streaming mode **before** this call.
- Closing `OutputStream` completes writing the request body per the contract; only after that should you read the status/response body.

### 5.1. Fixed-Length and Chunked Streaming Mode

`HttpURLConnection` provides:

| API | When to use? | Pitfalls |
|---|---|---|
| `setFixedLengthStreamingMode(int)` | Exact request body byte count is known and fits in `int` | Writing fewer or more bytes than declared will fail |
| `setFixedLengthStreamingMode(long)` | Large known length, avoiding `int` limits | Length must be exact in bytes |
| `setChunkedStreamingMode(int)` | Body length is unknown or streaming is desired | Some servers/proxies do not accept chunked requests |
| No streaming mode enabled | Implementation may buffer the request body before sending | Can consume significant memory; unsuitable for large payloads |

**Java 17 Javadoc warning:** when output streaming mode is enabled, **authentication and redirection cannot be handled automatically** as in buffering mode; if they are needed, reading the response may throw `HttpRetryException`. This is **not** a normal HTTP 4xx body and must be handled according to the API contract. Do not blindly retry POST because the server may have already received part or all of the body.

`setFixedLengthStreamingMode` and `setChunkedStreamingMode` must be called **before connecting**. If an application sets both fixed-length and chunked mode, it may encounter `IllegalStateException`.

## 6. Status Codes: getResponseCode and getResponseMessage

### 6.1. getResponseCode Is the Primary Signal

~~~java
int code = c.getResponseCode();
~~~

`HttpURLConnection` Javadoc: `getResponseCode()` returns the status code from an HTTP response, such as `200`, `401`, `404`, `500`. **It may return `-1` if no valid status can be parsed**, and it may throw `IOException` if an error occurs while connecting or receiving the response.

**Do not use `getInputStream()` to guess the status.** Retrieve `code`, classify the status, and then decide which stream to use. An HTTP error status and a network-induced `IOException` are **two different kinds of events**.

### 6.2. getResponseMessage Is Only Secondary Information

~~~java
int code = c.getResponseCode();
String reason = c.getResponseMessage();  // "OK", "Not Found", or null.
~~~

`getResponseMessage()` provides the reason phrase **if one can be parsed**, and may return `null`. Do not use the reason phrase text to branch business logic: servers/proxies may change wording or language, and modern HTTP versions do not have reason phrases in the traditional HTTP/1.1 sense.

**Use the integer status code**, not `reason.equals("OK")`.

### 6.3. HTTP Status Groups

| Group | Examples | How to interpret |
|---|---|---|
| **1xx** | `100 Continue`, `101 Switching Protocols` | Protocol/progress information; do not treat every 1xx as a final response |
| **2xx** | `200 OK`, `201 Created`, `202 Accepted`, `204 No Content` | Request succeeded per HTTP semantics; check body rules |
| **3xx** | `301`, `302`, `303`, `307`, `308`, `304` | Redirect/caching; do not route all 3xx into the error stream |
| **4xx** | `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`, `429 Too Many Requests` | Client/application request error; may have a body containing details |
| **5xx** | `500 Internal Server Error`, `502 Bad Gateway`, `503 Service Unavailable` | Server/proxy error; may have a body and Retry-After |

**`404` or `500` does not mean the socket failed.** These are **protocol-valid HTTP responses** with statuses indicating the request did not succeed at the application or server layer.

### 6.4. Some Statuses Have No Response Body

- `204 No Content`: successful response, but **no body**.
- `304 Not Modified`: caching semantics; **not a new response body**.
- `HEAD` request: response only has corresponding metadata, **no message body**.
- `202 Accepted`: server accepted the request for processing per semantics, **does not guarantee the business task has completed**.

Do not call `getErrorStream()` just because there is no body on 204/304. Nor should you assume `getInputStream()` will always yield readable text just because the status is 2xx; 204 may yield an empty stream, and some statuses/semantics have no payload.

## 7. getInputStream and getErrorStream: Choosing the Right Body Source

### 7.1. Receiving a Success Body

~~~java
int status = c.getResponseCode();
if (status >= 200 && status < 300) {
    try (InputStream in = c.getInputStream()) {
        // Read the body if the status/method allows content.
    }
}
~~~

`getInputStream()` from `URLConnection` returns a stream to read the response body; the stream may block while waiting for data and may throw `IOException`. Usually used for 2xx responses that have a body.

**Not every status below 400 is guaranteed valid to read as a success.** For 3xx, some implementations allow reading the redirect's body, but proper handling depends on the redirect policy and status. For 204/HEAD there is no body per HTTP semantics.

### 7.2. Receiving an Error Body

~~~java
int status = c.getResponseCode();
if (status >= 400) {
    InputStream error = c.getErrorStream();
    if (error != null) {
        try (InputStream in = error) {
            byte[] bytes = in.readAllBytes();
            // Decode/parse with limits according to Content-Type and needs.
        }
    }
}
~~~

`getErrorStream()` is the **stream containing the response error body when the server sent useful data**. It **does not return an exception object**; it does not auto-close; and it may be `null`. The Java 17 documentation gives the example that a 404 often causes `getInputStream()` to throw `FileNotFoundException`, while the server still provides an HTML error page readable via `getErrorStream()`.

**Two very important rules:**

1. `getErrorStream()` **does not initiate a connection on its own**. If called when not yet connected, it typically returns `null` even if the server **would later return an error**.
2. Even when the status is 404/500, **`getErrorStream()` can still be `null`** if the server sent no error data or the connection has not reached a state with a stream. You must check for null rather than calling `c.getErrorStream().readAllBytes()` directly.

### 7.3. Why Not Rely on getInputStream for Every Status?

For a GET to a nonexistent endpoint:

~~~text
Server:
HTTP/1.1 404 Not Found
Content-Type: application/json

{"error":"item_not_found"}

Client HttpURLConnection:
getResponseCode() -> 404
getInputStream()  -> may throw IOException / FileNotFoundException
getErrorStream()  -> error JSON stream (if body is ready)
~~~

If an application does the following, it will easily lose information:

~~~java
// WRONG handling: may discard the response error body.
try (InputStream in = c.getInputStream()) {
    parseJson(in);
} catch (IOException ex) {
    log(ex.getMessage());
}
~~~

The sensible pattern is to **read the status first, choose the response stream, close the stream, and distinguish HTTP errors from transport errors**.

## 8. A Response-Handling Pattern with Clear Success/Error Branches

~~~java
// Snippet: c already has method, headers, and timeouts configured.
// Not a standalone program: readLimited is an application-defined helper.
try {
    int status = c.getResponseCode();
    InputStream body = status >= 400
            ? c.getErrorStream()
            : c.getInputStream();

    if (body != null) {
        try (InputStream in = body) {
            byte[] bytes = readLimited(in, 1024 * 1024);
            // Only parse and store data permitted by policy.
        }
    }

    if (status < 200 || status >= 300) {
        // Classify 3xx/4xx/5xx status; do not treat as business success.
    }
} finally {
    c.disconnect();
}
~~~

**Pattern limitations:** 3xx may be a redirect/304 with special body rules; in real applications, 3xx should be handled separately. `getInputStream()` in some cases may throw `IOException` for reasons other than 4xx; you need a catch/log path for transport errors around this block if needed. `readLimited` is not defined here, so this code is an **illustrative snippet**, not runnable standalone.

A practical pattern for JSON APIs should classify as follows:

~~~text
getResponseCode
  ├── 2xx -> success status -> read body if present -> parse/validate
  ├── 3xx -> redirect/cache policy -> check Location
  ├── 4xx -> may read error stream -> classify client error
  ├── 5xx -> may read error stream -> classify server error
  └── IOException before status -> DNS/connect/TLS/timeout error
~~~

Do not write `if (status == 200) success else networkError`: 201/204 can be successes; 404/500 are HTTP responses; and `IOException` can happen at the I/O layer.

## 9. Complete Runnable Java 17+ Example on Loopback

The following program uses `com.sun.net.httpserver.HttpServer` (built-in JDK module: `jdk.httpserver`) to create an HTTP server at **127.0.0.1 on an ephemeral port**. No Internet is required and no real credentials are used.

It simulates:

1. **GET /ok** returns `200 READY`.
2. **POST /create** receives request body `ping` and returns `201 CREATED:ping`.
3. **GET /missing** returns `404 NOT_FOUND`; demonstrates that the error stream is **null before connecting**, `getInputStream()` throws `IOException` in the test runtime, yet `getErrorStream()` still reads the error content.
4. **GET /fail** returns `500 SERVER_ERROR`, read via the error stream.
5. **GET /empty** returns `204`, with no body and a null error stream.
6. **GET /redirect** returns `302 Location: /ok`; the client disables following redirects to observe the original status and header.
7. **PATCH** is rejected by `setRequestMethod` with `ProtocolException` in Java 17, even though the HTTP protocol has PATCH.

**File: `HttpUrlConnectionDemo.java`**

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ProtocolException;
import java.net.URI;
import java.nio.charset.StandardCharsets;

public class HttpUrlConnectionDemo {
    private static void reply(HttpExchange ex, int status, String text)
            throws IOException {
        byte[] data = text.getBytes(StandardCharsets.UTF_8);
        ex.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        if (status == 302) {
            ex.getResponseHeaders().set("Location", "/ok");
        }
        if (status == 204 || status == 302) {
            ex.sendResponseHeaders(status, -1);
            ex.close();
            return;
        }
        ex.sendResponseHeaders(status, data.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(data);
        }
    }

    private static HttpURLConnection open(URI base, String path, String method)
            throws Exception {
        HttpURLConnection conn = (HttpURLConnection)
                base.resolve(path).toURL().openConnection();
        conn.setConnectTimeout(3000);
        conn.setReadTimeout(3000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method);
        return conn;
    }

    private static String read(InputStream in) throws IOException {
        if (in == null) return "<none>";
        try (in) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/ok", ex -> reply(ex, 200, "READY"));
        server.createContext("/create", ex -> {
            String input = new String(ex.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);
            reply(ex, 201, "CREATED:" + input);
        });
        server.createContext("/missing", ex -> reply(ex, 404, "NOT_FOUND"));
        server.createContext("/fail", ex -> reply(ex, 500, "SERVER_ERROR"));
        server.createContext("/empty", ex -> reply(ex, 204, ""));
        server.createContext("/redirect", ex -> reply(ex, 302, ""));
        server.start();
        try {
            URI base = new URI("http", null, "127.0.0.1",
                    server.getAddress().getPort(), "/", null, null);

            HttpURLConnection get = open(base, "ok", "GET");
            try {
                int code = get.getResponseCode();
                System.out.println("GET status=" + code
                        + " body=" + read(get.getInputStream())
                        + " method=" + get.getRequestMethod());
            } finally {
                get.disconnect();
            }

            HttpURLConnection post = open(base, "create", "POST");
            try {
                byte[] payload = "ping".getBytes(StandardCharsets.UTF_8);
                post.setDoOutput(true);
                post.setRequestProperty("Content-Type",
                        "text/plain; charset=UTF-8");
                post.setFixedLengthStreamingMode(payload.length);
                try (OutputStream out = post.getOutputStream()) {
                    out.write(payload);
                }
                int code = post.getResponseCode();
                System.out.println("POST status=" + code
                        + " body=" + read(post.getInputStream())
                        + " method=" + post.getRequestMethod());
            } finally {
                post.disconnect();
            }

            HttpURLConnection missing = open(base, "missing", "GET");
            try {
                boolean wasNull = missing.getErrorStream() == null;
                int code = missing.getResponseCode();
                boolean inputThrew = false;
                try (InputStream ignored = missing.getInputStream()) {
                    ignored.readAllBytes();
                } catch (IOException expected) {
                    inputThrew = true;
                }
                System.out.println("404 status=" + code
                        + " error=" + read(missing.getErrorStream()));
                System.out.println("404 errorBeforeConnectNull=" + wasNull
                        + " inputStreamThrows=" + inputThrew);
            } finally {
                missing.disconnect();
            }

            HttpURLConnection fail = open(base, "fail", "GET");
            try {
                System.out.println("500 status=" + fail.getResponseCode()
                        + " error=" + read(fail.getErrorStream()));
            } finally {
                fail.disconnect();
            }

            HttpURLConnection empty = open(base, "empty", "GET");
            try {
                int code = empty.getResponseCode();
                boolean errorNull = empty.getErrorStream() == null;
                int count;
                try (InputStream in = empty.getInputStream()) {
                    count = in.readAllBytes().length;
                }
                System.out.println("204 status=" + code
                        + " errorStreamNull=" + errorNull
                        + " bodyBytes=" + count);
            } finally {
                empty.disconnect();
            }

            HttpURLConnection redirect = open(base, "redirect", "GET");
            try {
                System.out.println("302 status=" + redirect.getResponseCode()
                        + " location=" + redirect.getHeaderField("Location")
                        + " autoRedirect="
                        + redirect.getInstanceFollowRedirects());
            } finally {
                redirect.disconnect();
            }

            HttpURLConnection invalid = open(base, "ok", "GET");
            try {
                boolean rejected = false;
                try {
                    invalid.setRequestMethod("PATCH");
                } catch (ProtocolException expected) {
                    rejected = true;
                }
                System.out.println("PATCH rejected=" + rejected);
            } finally {
                invalid.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile and run on **JDK 17+**. Since the demo uses `HttpServer`, provide the `jdk.httpserver` module:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpUrlConnectionDemo.java
java --add-modules jdk.httpserver HttpUrlConnectionDemo
~~~

**Verified stdout when compiled with `--release 17` and run on OpenJDK 24:**

~~~text
GET status=200 body=READY method=GET
POST status=201 body=CREATED:ping method=POST
404 status=404 error=NOT_FOUND
404 errorBeforeConnectNull=true inputStreamThrows=true
500 status=500 error=SERVER_ERROR
204 status=204 errorStreamNull=true bodyBytes=0
302 status=302 location=/ok autoRedirect=false
PATCH rejected=true
~~~

### 9.1. Output Analysis

| Output line | What it proves |
|---|---|
| `GET status=200 body=READY method=GET` | GET succeeded; body was read from `getInputStream()` |
| `POST status=201 body=CREATED:ping method=POST` | POST body was read by the server; 201 response was retrieved via input stream |
| `404 status=404 error=NOT_FOUND` | HTTP 404 **has an error body**, read via `getErrorStream()` |
| `404 errorBeforeConnectNull=true inputStreamThrows=true` | `getErrorStream` does not connect on its own; `getInputStream` may throw `IOException` for HTTP 404 |
| `500 status=500 error=SERVER_ERROR` | A 5xx status is still an HTTP response with an error body |
| `204 status=204 errorStreamNull=true bodyBytes=0` | Response has no content; error stream is nullable |
| `302 status=302 location=/ok autoRedirect=false` | Disabling redirects per instance allows reading the original response's status and Location |
| `PATCH rejected=true` | Legacy `setRequestMethod` API does not accept PATCH per the Java 17 list |

**Understand the scope of the experiment:** the line count and body content are fixed by the local server. That `getInputStream()` throws `IOException` on HTTP 404 was verified on the JDK used for testing, but **you should not rely on a specific exception name as an API to classify HTTP statuses**: always get `getResponseCode()`. The demo server only runs HTTP on loopback and does not simulate TLS, the Internet, authentication, error JSON schemas, or proxies.

## 10. getErrorStream() Is Nullable and Does Not Open a Connection

According to the Java SE 17 Javadoc, `getErrorStream()`:

- Returns the **InputStream of the error response**, if the connection has experienced an HTTP error but the server still sent useful data.
- **Does not initiate a connection** if not yet connected.
- Returns **`null`** if the connection has not been established, no error occurred, or the server sent no error data.
- Is not an exception-creating API, and is not a signal guaranteeing that the server sent a valid error body.

Therefore, the following code easily causes a `NullPointerException`:

~~~java
// WRONG: error stream can be null, even for 4xx/5xx.
String error = new String(
        connection.getErrorStream().readAllBytes(),
        StandardCharsets.UTF_8);
~~~

Replace it with:

~~~java
InputStream error = connection.getErrorStream();
if (error == null) {
    // Record "error response provided no body" instead of NPE.
} else {
    try (InputStream in = error) {
        // Limit size, decode according to Content-Type if needed.
    }
}
~~~

**Order matters:** you should call `getResponseCode()` first to connect and determine the status, and only then obtain the stream. `getErrorStream()` on a fresh connection is usually null. Do not write business logic that depends on `getErrorStream() != null` instead of checking the status code.

### 10.1. Should You Fall Back from Error Stream to Input Stream?

In standard `HttpURLConnection`, for error statuses >=400, `getInputStream()` usually throws `IOException` rather than providing the error body. If `getErrorStream() == null`, **do not** blindly call `getInputStream()` to "try to read a message": you may only get another exception. Record the **status code** and that the error body may be absent; if the API requires error JSON, handle the empty/null case intentionally.

For 3xx, depending on the redirect policy and status, `getInputStream()` may provide the response body, but **Location + redirect policy** are usually the more important data. For 204/HEAD, do not try to parse a nonexistent body.

### 10.2. The Error Stream Can Fail to Read Too

Even when you have an error stream object, `InputStream.read` can still throw `IOException` due to a dropped connection, read timeout, or malformed response. Therefore:

~~~text
HTTP status = 500
errorStream != null
      |
      +-- read completes -> can parse error payload
      |
      +-- read fails     -> HTTP 500 is known, but error body may be incomplete
~~~

Do not treat a known status as proof that the body finished downloading, and do not swallow `IOException` while still reporting that the error response was completely handled.

## 11. An HTTP Error Is Not the Same as an IOException

| Scenario | Has HTTP status? | Has stream? | Assessment |
|---|---|---|---|
| Server returns `200` + body | Yes | Usually `getInputStream` | HTTP success; still needs body validation |
| Server returns `201` + body | Yes | `getInputStream` | Resource creation request succeeded per API |
| Server returns `204` | Yes | Empty body | Not a network failure |
| Server returns `404` + JSON | Yes | May have `getErrorStream` | HTTP client error, **does not mean DNS/TCP failed** |
| Server returns `500` + HTML | Yes | May have `getErrorStream` | HTTP server error |
| Server returns `404` with no body | Yes | `getErrorStream == null` can happen | HTTP error missing payload |
| DNS resolution fails / connect refused | Usually no | No HTTP response body | `UnknownHostException` / `ConnectException`… |
| TCP read timeout before headers | Possibly no | No | `SocketTimeoutException` |
| Body stream fails after status | Status may already be known | Stream errors during read | Transport/body failure after HTTP metadata |

`IOException` covers many cases: network connections, TLS handshakes, timeouts, stream read errors, and even `getInputStream()`'s status-mapping behavior on 404. **You cannot classify HTTP errors by exception name alone**; check the status whenever possible and distinguish cases where there is no response at all.

### 11.1. What If getResponseCode Throws IOException?

`getResponseCode()` can throw `IOException` if an error occurs while connecting or receiving the status. On this path:

- **Do not assume** the status code has a reliable value.
- Do not call `getErrorStream()` and assume it has a body; the method may return null because there is no valid HTTP response.
- Log the error type, sanitized URI, timeout phase, and exception chain; do not log credentials or the full request body.
- For idempotent requests, retry only when policy permits; for POST, you need an idempotency key/business logic because the server may have already processed the request before the response was lost.

## 12. HttpURLConnection Redirect Policy and 3xx Statuses

`HttpURLConnection` provides:

| API | Scope | Notes |
|---|---|---|
| `HttpURLConnection.getFollowRedirects()` | Class-wide static default state | Default is **true** in Java 17 |
| `HttpURLConnection.setFollowRedirects(boolean)` | Changes default redirect behavior at class/JVM level | Should not be toggled between requests in a multi-threaded service |
| `connection.getInstanceFollowRedirects()` | Instance policy | Inherits from the static policy when the connection is created |
| `connection.setInstanceFollowRedirects(boolean)` | Enables/disables redirects for the instance before I/O | Use `false` to handle `Location` yourself |
| `connection.getHeaderField("Location")` | Next URL suggested by the server | May be relative, missing, or untrusted |

**Difference from Java 17 `java.net.http.HttpClient`:** `HttpURLConnection` defaults to **follow redirects = true**, whereas modern `HttpClient` defaults to `HttpClient.Redirect.NEVER`. Do not port code between the two APIs assuming the same behavior.

~~~java
HttpURLConnection c = (HttpURLConnection)
        URI.create("https://api.example.test/old").toURL().openConnection();

c.setInstanceFollowRedirects(false);
int code = c.getResponseCode();
String location = c.getHeaderField("Location");
~~~

This is an HTTP client snippet, **not an offline-runnable demo**. If the status is 302, the application may want to evaluate the destination itself before making another request. Do not blindly follow `Location` to a host outside the trust boundary with Authorization/Cookie/POST body. You must check scheme, origin, allowlist, hop count, method, and HTTPS security.

**Especially with streaming request bodies:** `setFixedLengthStreamingMode` / `setChunkedStreamingMode` can prevent auto-redirect/authentication from working and lead to `HttpRetryException`. Therefore, do not assume every 3xx/401 will be handled automatically and hidden from the caller.

## 13. Timeouts: connectTimeout vs. readTimeout

`URLConnection` provides:

| Setting | Purpose | Default |
|---|---|---|
| `setConnectTimeout(int millis)` | Maximum time for the network link-opening phase per contract | `0` (no limit imposed by this setting) |
| `setReadTimeout(int millis)` | Wait limit for data during a read operation | `0` (no limit imposed by this setting) |

Example:

~~~java
connection.setConnectTimeout(3000);
connection.setReadTimeout(5000);
~~~

**Read timeout does not mean total response download time.** If the server keeps sending a few bytes before each read deadline, the total time can be much longer. For large responses, you also need an overall deadline, maximum body bytes, retry policy, and appropriate cancellation.

Usually `SocketTimeoutException` is a subtype of `IOException` when a wait exceeds the deadline. However, status 504 **Gateway Timeout** is an HTTP response returned by a server/proxy; it is **not equivalent** to a client-side Java `SocketTimeoutException`.

Do not leave `0` (infinite) in production when an endpoint might hang. Set timeouts according to your SLA and environment. When a timeout occurs during POST, the server may still have received/executed the request, so do not automatically retry blindly.

## 14. Headers, Content-Type, and Decoding the Response Body

`getHeaderField("Content-Type")` may return:

~~~http
Content-Type: application/json; charset=UTF-8
~~~

However, **`getInputStream()` and `getErrorStream()` return byte streams**, and do not automatically guarantee the exact JSON/text charset your application uses. In the demo, the body is ASCII/UTF-8, so it uses:

~~~java
String body = new String(in.readAllBytes(), StandardCharsets.UTF_8);
~~~

This is convenient **only for small, bounded bodies**. For untrusted or large responses:

- Check `Content-Type` and charset against the API contract.
- Limit total bytes **while reading**, rather than trusting only `Content-Length` (which may be missing or wrong).
- Avoid logging entire HTML error pages or JSON containing PII/tokens.
- Distinguish 204/HEAD statuses (no body) from a server returning `Content-Length: 0`.
- If the server compresses the body using `Content-Encoding`, the application must handle the appropriate encoding; **do not assume the raw stream is already plain text**.
- A JSON parse failure is an **application data error**, not necessarily an HTTP transport error.

### 14.1. Reading the Stream in Blocks Instead of readAllBytes

~~~java
// Snippet: in is an InputStream with proper ownership.
// Count bytes read to block oversized responses.
long maxBytes = 1_000_000;
long total = 0;
byte[] buffer = new byte[8192];
for (int n; (n = in.read(buffer)) != -1;) {
    total += n;
    if (total > maxBytes) {
        throw new IOException("Body too large");
    }
    // Pass exactly n bytes to a parser, file, or bounded sink.
}
~~~

This snippet does not solve the parser/sink by itself; for large response bodies and sensitive data, you need proper memory management, content compression handling, decoding, and cleanup.

### 14.2. HTTP Content-Length vs. String.length

`Content-Length` describes the **number of bytes in the HTTP message representation** per the protocol, not the number of Java characters. With UTF-8, accented Vietnamese letters or emoji often occupy multiple bytes; use `payload.getBytes(StandardCharsets.UTF_8).length` to set `setFixedLengthStreamingMode` accurately.

## 15. Closing Streams and Calling disconnect() Properly

According to the Java 17 Javadoc, each `HttpURLConnection` serves one request, though the underlying persistent connection may be **shared** across multiple connection instances.

- `InputStream.close()` / `OutputStream.close()` releases stream-owned resources and may allow the network connection to be reused depending on the implementation.
- `HttpURLConnection.disconnect()` indicates that no further requests are expected in the near future and may close the socket if the persistent connection is idle.
- `disconnect()` **does not make the HttpURLConnection instance reusable**; once an instance is used, create a new instance for a new request.
- **Do not use `disconnect()` as a substitute for closing streams with try-with-resources.** The two operations have different meanings.

Pattern:

~~~java
HttpURLConnection c = (HttpURLConnection) url.openConnection();
try {
    c.setConnectTimeout(3000);
    c.setReadTimeout(3000);
    int code = c.getResponseCode();
    InputStream candidate = code >= 400
            ? c.getErrorStream()
            : c.getInputStream();
    if (candidate != null) {
        try (InputStream in = candidate) {
            // Read body appropriate for status/method, with quota.
        }
    }
} finally {
    c.disconnect();
}
~~~

This is a **snippet** with `url` already declared. If you want to handle 3xx/204/HEAD statuses separately, you must add branches; do not turn this snippet into a full HTTP policy with just two status branches.

## 16. Practical Mistakes and How to Fix Them

| Symptom | Common mistake | Fix |
|---|---|---|
| 404 has error JSON, but app only sees FileNotFoundException | Calling `getInputStream` for every status | Get `getResponseCode`, then try `getErrorStream` |
| NPE when reading errors | Not checking `getErrorStream() == null` | Error stream is nullable |
| getErrorStream is null right after openConnection | It does not initiate I/O on its own | Get status via `getResponseCode` first |
| POST sends GET instead | Not setting method explicitly, misunderstanding `doOutput` | Call `setRequestMethod("POST")` before output |
| `PATCH` throws `ProtocolException` | Legacy `HttpURLConnection` does not support PATCH directly | Use `java.net.http.HttpClient` |
| `setRequestMethod` fails after calling `getInputStream` | Connection already initiated | Set method/properties before I/O |
| 204 breaks the JSON parser | 204 has no body | Skip body parsing when there is no payload |
| 401 treated as "Java lost network" | Confusing HTTP auth status with `IOException` | Classify HTTP status and network errors separately |
| 302 automatically redirects to another URL | Redirects default to true | Call `setInstanceFollowRedirects(false)` when control is needed |
| Fixed streaming POST hits `HttpRetryException` | Auto auth/redirect cannot be used in streaming mode | Design controlled replay/auth/redirect |
| `getResponseMessage` is null or wording differs | Reason phrase is unstable | Use the integer status code |
| Hanging requests | Not setting connect/read timeouts | Set both + overall policy |
| Loading large responses causes OOM | Unbounded `readAllBytes` | Bounded streaming / size limit |
| Corrupted Unicode content | Using default charset | Read `Content-Type`, decode per contract |
| Socket leak | Not closing streams or disconnecting | Use try-with-resources and `finally` |
| Reusing the same connection to send a second request | An instance is for one request only | Open a new `HttpURLConnection` |
| Logs leak tokens in URL/error body | Logging raw body/headers | Redact credentials, sanitize URI |
| HTTPS handshake bypassed | Trust-all SSL manager to "fix errors" | Fix truststore/certificate, never disable TLS verification |

## 17. Code Review Checklist

**Before I/O:** Does the URL have an allowed HTTP/HTTPS scheme? Is there an SSRF risk if the URL is user-supplied? Is the method set explicitly? Are `setDoOutput`, `Content-Type`, and `Content-Length`/streaming mode correct? Are headers, connect/read timeouts, and redirect policy set before connecting?

**When receiving the HTTP response:** What status did `getResponseCode` return? Does 2xx have a body or not? Does 3xx have a `Location` to inspect? For 4xx/5xx, was `getErrorStream` tried and null handled? Are network `IOException`s distinguished from bad HTTP statuses?

**When reading the body:** Are byte quotas, encoding, compression, and an appropriate parser in place? Are tokens/PII in the error body logged? If the stream times out mid-read, is the state marked body-failed or does the app still mark it as success?

**When finishing:** Are `InputStream`/`OutputStream` closed, and is `disconnect` called in `finally`? Is the code actively avoiding reusing the same `HttpURLConnection` instance? Is a non-idempotent POST prevented from unauthorized retries?

## 18. Self-Check Questions

**1. What is the default method of HttpURLConnection?** `GET`.

**2. When must the HTTP method be set?** Before `connect`/`getInputStream`/`getOutputStream`/`getResponseCode`.

**3. Does Java 17 HttpURLConnection support `setRequestMethod("PATCH")`?** Not in the official list of legal methods; use modern `HttpClient` if you need PATCH.

**4. Can `getResponseCode()` return `-1`?** Yes, when no valid HTTP status can be parsed; it can also throw `IOException` if the connection fails.

**5. Should logic be driven by `getResponseMessage().equals("OK")`?** No, the reason phrase is unstable and can be null.

**6. The server returns HTTP 404 and error JSON. Where do you read it?** `getErrorStream()`, after determining status/connection, remembering to check for null.

**7. Does `getErrorStream` create a network connection on its own?** No; when not yet connected, it usually returns null.

**8. Does every 500 have a non-null getErrorStream?** No. The server may not send an error body.

**9. Does status 204 mean Java failed because the body is empty?** No, `204 No Content` is an HTTP success status.

**10. Are HTTP 504 and `SocketTimeoutException` the same?** No: 504 is an HTTP response from a server/proxy; the exception is a client-side I/O error.

**11. Is `setDoOutput(true)` enough on its own to indicate POST?** You should set `setRequestMethod("POST")` explicitly.

**12. What does fixed-length streaming calculate length in?** In the number of **bytes** of the payload, not `String.length`.

**13. Why can auth/redirect with a streaming body throw `HttpRetryException`?** The Javadoc states that when output streaming is enabled, automatic replay for authentication/redirection cannot be performed.

**14. Why did redirects in the demo not follow automatically?** Because `setInstanceFollowRedirects(false)` was called before I/O.

**15. Does `disconnect` allow reusing the same instance for another request?** No, each `HttpURLConnection` instance is for one request.

**16. Does `getInputStream()` throwing IOException always mean HTTP 404?** No. There are many network/transport causes; classify the status whenever possible.

## 19. References

- [Java SE 17 – HttpURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): `setRequestMethod`, `getResponseCode`, `getResponseMessage`, `getErrorStream`, redirects, streaming mode, `disconnect`.
- [Java SE 17 – URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): connection lifecycle, request properties, timeouts, input/output streams.
- [Java SE 17 – URL](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URL.html): `openConnection` and `openStream`.
- [Java SE 17 – HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): TLS-specific HTTP URL connection API.
- [Java SE 17 – HttpRetryException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html): cases where a request with streaming output cannot be retried on authentication/redirect.
- [Java SE 17 – java.net.http.HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): modern HTTP client replacing many legacy needs.
- [Java SE 17 – HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): custom methods and body publishers.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback server used in the demo.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP methods, status codes, redirect, and content semantics.

**Conclusion:** Always **specify the method before connecting**, use **`getResponseCode()` as the primary source to classify the HTTP response**, and then read **`getInputStream()` for success content** or **`getErrorStream()` for the error body if present**. `getErrorStream()` is **nullable and does not connect on its own**; HTTP 404/500 are statuses returned by the server and do not mean Java lost network connectivity. Always close streams, set timeouts, handle redirects/auth in a controlled manner, and call `disconnect()` in `finally` when finished with the instance.
