# Redirects, HTTP Keep-Alive, and the Meaning of `disconnect()` in URLConnection

## Objectives

In Java, the code `(HttpURLConnection) url.openConnection()` creates an **object that manages a single HTTP request**, which does not mean it has already opened a new TCP socket. `HttpURLConnection` can **automatically follow HTTP redirects** if policy permits. A single HTTP request can go through `302 Location: /new` before receiving `200 OK`; at the same time, multiple different `HttpURLConnection` objects can **reuse a single TCP connection** if the server and client support HTTP/1.1 keep-alive. Therefore, calling `disconnect()` on an object must not be understood as a command that “is guaranteed to close every related TCP socket and clear the pool.”

This lesson places three questions at their proper layers:

1. **Redirects**: the server returns a 3xx status code and `Location`; when does Java follow automatically, how do you disable automatic following per connection, and what is the impact on the target URL, HTTP method, and request body, especially when streaming mode is enabled?
2. **HTTP keep-alive/persistence**: HTTP/1.1 can send multiple requests over a single TCP connection, yet why does one `HttpURLConnection` object still **represent only one HTTP call**? What are the conditions for a connection to actually be reused?
3. **`disconnect()`**: what does this method actually guarantee, and how does it differ from `InputStream.close()`, `Connection: close`, and TCP FIN/RST? Why is calling `disconnect()` not proof that a new socket is used on the next request?

You will practice with **three standalone Java 17+ programs**, running over loopback HTTP with no Internet required: (1) follow and no-follow redirects, (2) streaming POST encountering 307 and `HttpRetryException`, and (3) observing TCP reuse both before and after a `disconnect()` call. All are compiled with `javac --release 17` and run on a Java 17-compatible JDK. The final section includes a checklist for handling HTTP errors, secure redirects, resource cleanup, and exercises.

## 1. What Roles Do URLConnection and HttpURLConnection Play?

`java.net.URLConnection` is the abstract class for a connection to a URL, not limited to HTTP. `java.net.HttpURLConnection` extends it with HTTP-specific methods, such as `getResponseCode()`, `setRequestMethod(...)`, `setInstanceFollowRedirects(...)`, `setFixedLengthStreamingMode(...)`, and `disconnect()`. `HttpsURLConnection` is the subclass that supports HTTPS/TLS.

A typical GET flow follows these steps:

```text
1. Resource URL/URI
      │
      ▼
2. URL.openConnection()
   → URLConnection / HttpURLConnection object
      │
      ▼
3. Configure BEFORE connecting:
   request method, request headers, connect timeout,
   read timeout, follow-redirect policy
      │
      ▼
4. getResponseCode(), getInputStream(), getOutputStream()
   → Actual connection may be opened implicitly
   → HTTP request is sent
      │
      ▼
5. Read response status/headers/body
   → May have followed 3xx redirects before seeing the final result
      │
      ▼
6. Fully read and close the response stream, cleanup
   → TCP connection may be kept in the keep-alive cache
      │
      ▼
7. Another request creates a DIFFERENT HttpURLConnection
   → May reuse the old TCP connection if eligible
```

**Distinguishing three kinds of “connection”:**

| Term | Nature | Proof of a new TCP socket? |
|---|---|---|
| An `HttpURLConnection` object | Java object for **one logical HTTP request** | **No** |
| An HTTP/1.1 persistent connection | Transport channel for multiple request–response exchanges | May be shared across instances |
| A TCP socket | OS transport endpoint consisting of IP/port and TCP state | Opened/closed by runtime, protocol, server, and pool |

The Java 17 Javadoc states clearly: **each `HttpURLConnection` instance is used to make a single request**, but the **underlying network connection** to the HTTP server may be transparently shared by other instances. An automatic redirect can cause **one logical API request** to result in **multiple HTTP requests on the network**, without turning the object into an arbitrary coordinator for multiple business operations.

### Does calling `openConnection()` connect immediately?

Not by default. `URL.openConnection()` typically **creates the object** and allows setting properties. A call such as `getResponseCode()`, `getInputStream()`, or `getOutputStream()` may cause the implementation to connect and send the request if not already connected.

```java
// Illustrative snippet; not yet a standalone program.
HttpURLConnection connection =
        (HttpURLConnection) URI.create(
                "http://127.0.0.1:8080/resource").toURL().openConnection();

connection.setRequestMethod("GET");
connection.setConnectTimeout(3000);
connection.setReadTimeout(3000);
connection.setInstanceFollowRedirects(false);

// getResponseCode() may perform the connect/request implicitly.
int code = connection.getResponseCode();
```

Practical takeaway: configure `setRequestMethod`, `setRequestProperty`, `setInstanceFollowRedirects`, streaming mode, and timeouts **before** triggering network I/O for the first time. Do not treat `connect()` as a step that must always be called explicitly; the I/O getters can connect automatically.

## 2. A Redirect Is an HTTP Response, Not a TCP Instruction

The server uses a 3xx status code, usually accompanied by `Location`, to inform the client that it may need to request a different URI:

```http
HTTP/1.1 302 Found
Location: /new-location
Content-Length: 0

```

`/new-location` is a relative reference resolved against the original URI. When the client chooses to follow:

```text
Logical GET /old
    |
    |  Server: 302 Found + Location: /new
    ▼
GET /new
    |
    |  Server: 200 OK
    ▼
Caller sees final result 200
```

**Status 302 is not a TCP redirect.** TCP does not automatically switch a socket from server A to server B just because of a 302 status. The HTTP client must interpret `Location`, check policy, and issue a **subsequent HTTP request**; it may reuse the connection if it is the same endpoint and meets the conditions, or it may have to open a new connection if the host, port, proxy, TLS context, or connection health changes.

### Important redirect status codes

| Status | Common interpretation | Method/body when following |
|---|---|---|
| `301 Moved Permanently` | The new URI is permanent | HTTP semantics allow user agents to change POST→GET; do not assume the request body is preserved |
| `302 Found` | Temporary redirect | Also has a history of changing POST→GET; know your implementation |
| `303 See Other` | View the result resource via another URI | For POST, typically switches to GET without replaying the POST body |
| `307 Temporary Redirect` | Temporary redirect while preserving the method | If followed, **do not change the method**; the original body may need to be replayed |
| `308 Permanent Redirect` | Permanent redirect while preserving the method | If followed, **do not change the method**; the original body may need to be replayed |

Do not equate “the RFC describes the status meaning” with “every JDK’s `HttpURLConnection` will automatically follow all of these statuses.” `HttpURLConnection` has a long implementation history; practical rules regarding methods, streaming, protocol/scheme, and redirect count depend on the JDK, version, and configuration. For requests with side effects or complex auth, **do not guess automatic behavior**—test on the target runtime or handle redirects manually.

### `Location` can alter security properties

A `Location` can be:

- A same-origin path, such as `/v2/items`.
- An absolute URI with the same scheme/host/port.
- A URI with a different host or port.
- A URI that switches between HTTP and HTTPS.
- A URI pointing to an external service, internal IP, or sensitive address if the server is manipulated.

For applications that accept user-supplied input URLs or automatically follow untrusted `Location` headers, you should **allowlist origins/hosts**, block private DNS/IPs if required by the domain, limit the redirect chain, verify TLS, and avoid sending `Authorization`/cookies/sensitive bodies to unauthorized destinations. Do not manually copy credentials to a new origin just because the original request had those headers.

## 3. Controlling Redirects in HttpURLConnection

The Java 17 Javadoc defines two configuration levels:

- **Global/class-level:** `HttpURLConnection.setFollowRedirects(boolean)` and `HttpURLConnection.getFollowRedirects()`. **Defaults to `true`** according to the Javadoc; this is a **static** setting and should not be changed arbitrarily when multiple modules share a JVM.
- **Per-instance:** `connection.setInstanceFollowRedirects(boolean)` and `connection.getInstanceFollowRedirects()`. The instance's default value is taken from the **static setting at the time the object is constructed**; changing one instance does not affect all others.
- If you want to inspect the 3xx status and decide yourself, set **`setInstanceFollowRedirects(false)` before connecting**.
- If you want to follow redirects automatically as permitted by the runtime and policy, use **`setInstanceFollowRedirects(true)`**; this does not guarantee that redirects always succeed or that every host/credential is safe.

Example:

```java
// Illustrative snippet; a URL variable "url" must already exist.
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setInstanceFollowRedirects(false);
c.setConnectTimeout(3000);
c.setReadTimeout(3000);
int status = c.getResponseCode();

if (status >= 300 && status < 400) {
    String location = c.getHeaderField("Location");
    // Validate Location, target scheme/host, method, replayability
    // before creating a NEW HttpURLConnection.
}
```

This is an **illustrative snippet**, not a complete Java program. Do not assume every status in 300–399 has a `Location`; some, like `304 Not Modified`, have cache validation semantics and are **not** a redirect invitation to follow. You must inspect the exact status and `Location`, not just check a numeric range.

### `getURL()` after a redirect

In the tested implementation, when `HttpURLConnection` automatically follows from `/start` to `/final`, `getURL().getPath()` returns `/final`. This is useful information for logging the **effective URL**. However, every hop still needs security validation; do not treat the final URL as proof that there was no intermediate hop to an unauthorized origin.

### Why should you avoid the static setting?

`HttpURLConnection.setFollowRedirects(false)` affects **instances created afterward** in the same JVM (unless they override it themselves). In a server application with multiple libraries, changing a global static setting can cause unexpected behavior. Prefer **per-instance** settings for a specific request.

## 4. Java 17+: Follow vs. No-Follow Redirect 302 on Localhost

The following program uses `com.sun.net.httpserver.HttpServer` to create two endpoints:

- `/start` returns `302 Found` and `Location: /final`, with no body.
- `/final` returns `200 OK` with body `DESTINATION` and increments a counter.

The client creates **two different `HttpURLConnection` objects**, both starting at `/start`:

1. The first instance enables follow and receives the final 200 response.
2. The second instance disables follow and therefore sees status 302 and the raw `Location`.
3. The server endpoint `/final` is called **only once** in this test run.

**File `RedirectPolicyDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;

public class RedirectPolicyDemo {
    private static String read(HttpURLConnection c) throws IOException {
        try (InputStream in = c.getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        } finally {
            c.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        AtomicInteger finalHits = new AtomicInteger();
        server.createContext("/start", ex -> {
            try (ex) {
                ex.getResponseHeaders().set("Location", "/final");
                ex.sendResponseHeaders(302, -1);
            }
        });
        server.createContext("/final", ex -> {
            try (ex) {
                finalHits.incrementAndGet();
                byte[] bytes = "DESTINATION".getBytes(StandardCharsets.UTF_8);
                ex.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = ex.getResponseBody()) {
                    out.write(bytes);
                }
            }
        });
        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/start").toURL();

            HttpURLConnection follow = (HttpURLConnection) url.openConnection();
            follow.setInstanceFollowRedirects(true);
            follow.setConnectTimeout(3000);
            follow.setReadTimeout(3000);
            int followedStatus = follow.getResponseCode();
            String followedPath = follow.getURL().getPath();
            String followedBody = read(follow);

            HttpURLConnection noFollow = (HttpURLConnection) url.openConnection();
            noFollow.setInstanceFollowRedirects(false);
            noFollow.setConnectTimeout(3000);
            noFollow.setReadTimeout(3000);
            int rawStatus = noFollow.getResponseCode();
            String location = noFollow.getHeaderField("Location");
            noFollow.disconnect();

            System.out.println("Follow status: " + followedStatus);
            System.out.println("Follow final path: " + followedPath);
            System.out.println("Follow body: " + followedBody);
            System.out.println("No-follow status: " + rawStatus);
            System.out.println("No-follow Location: " + location);
            System.out.println("Destination requests: " + finalHits.get());
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run on JDK 17+:

```bash
javac --release 17 -encoding UTF-8 RedirectPolicyDemo.java
java RedirectPolicyDemo
```

**Verified stdout on a Java 17+ compatible JDK:**

```text
Follow status: 200
Follow final path: /final
Follow body: DESTINATION
No-follow status: 302
No-follow Location: /final
Destination requests: 1
```

**Systematic explanation:**

- `url.openConnection()` creates a new object, which does not mean a socket is opened immediately; `getResponseCode()` triggers the request.
- With `follow.setInstanceFollowRedirects(true)`, the result the caller sees is the final **200**, not the intermediate **302**. This is useful when you want to fetch a resource, but it can hide information about intermediate redirects if the application needs to audit each hop.
- `follow.getURL().getPath()` reflects `/final` on the tested runtime; if you need security decisions for each `Location`, do not check only the initial URL.
- With `noFollow`, the caller sees **302** and `Location: /final`. No second request is made to `/final` from this instance.
- The counter `finalHits=1` confirms that only the follow instance reached the destination. This is a **same-origin test on localhost**, not representative of cross-origin policies or HTTPS downgrades.
- `read(follow)` uses try-with-resources for `InputStream`, then calls `disconnect()` in `finally`. This does **not** prove that `disconnect()` always closes a physical TCP socket—a later section explains why.
- If you replace `302` with `307` or `308` in a POST application, you must consider method/body and replayability, rather than using this GET result to make claims about other methods.

## 5. With POST, Redirects Also Involve the Request Method and Body

A GET redirect can be straightforward to handle: send GET to the new URI. With POST/PUT/uploads, the client may have already **sent the body** before receiving the 3xx response, and resending requires the body to be **replayable**.

```text
Client                              Server
 POST /upload + body bytes ───────► 307 Location: /new-upload
        │
        └── If auto-following 307:
            must preserve POST method
            and have the body again for the next request
```

However, “being able to reproduce the same bytes” says nothing about **business idempotency**. The server may have already received and processed the first POST before returning 3xx or before the client timed out. Sending the POST again can cause duplicate side effects if there is no request ID/dedup or proper transaction design.

### 5.1. When does a redirect switch the method?

According to HTTP semantics (RFC 9110):

- `301`/`302` historically allow user agents to switch **POST→GET** when following.
- `303` typically uses **GET** to view the result of a POST, without resending the POST body.
- `307`/`308` are used specifically to redirect to a new URI **without changing the HTTP method** when following. That is the appropriate choice if the server wants to preserve POST/PUT under redirect semantics.

With legacy `HttpURLConnection`, **do not assume every redirect type shares the same policy as the modern `java.net.http.HttpClient`**. Verify the final method with a server test and check the runtime documentation, especially when using streaming mode.

### 5.2. `Location` does not automatically grant permission to send data

A new `Location` may change the host. For a POST carrying cookies, a bearer token, or an internal file, do not automatically forward all credentials/headers/body to the new host. If an API endpoint has side effects, consider **disabling automatic redirects**, checking the allowlist, TLS, target URI, and business contract, and only then deciding whether to send the next request.

## 6. Fixed-Length and Chunked Streaming Modes Restrict Redirects

`HttpURLConnection` has two important methods to **stream the request body without buffering the entire body inside the handler**:

- `setFixedLengthStreamingMode(int)` and `setFixedLengthStreamingMode(long)`: the request body byte count is known; you **must write the exact number of bytes** before closing the output stream. For large payloads, the `long` overload avoids the `int` limit.
- `setChunkedStreamingMode(int chunklen)`: the byte count is not known in advance; uses **HTTP chunked transfer encoding**. Not all HTTP servers support this mode as expected.

**Call these methods before the `URLConnection` is connected.** You need `setDoOutput(true)`, an appropriate method (typically POST/PUT), and `getOutputStream()` to send the body.

The Java 17 Javadoc states clearly: **when output streaming is enabled, HTTP authentication and redirection cannot be handled automatically** as in normal request mode. When the server requires authentication or a redirect and the application reads the response, an `HttpRetryException` may be thrown.

### Why is this not a “Java bug”?

Once the body has been streamed directly over the socket and the handler **has not saved a full copy**, making a new request to another URI requires **resending the body**. But the Java handler cannot reconstruct a single-pass live stream on its own. Rather than silently altering request semantics or sending an empty body, the API signals that the application must manage the retry.

This is an **intentional limitation** of streaming mode. Do not try to fix it by catching `HttpRetryException` and calling `getInputStream()` again on the same already-used `HttpURLConnection`; you must decide whether to create a new request, whether you have a stable body source, and whether a safe retry/redirect policy applies.

### What does `HttpRetryException` provide?

`java.net.HttpRetryException` lets you retrieve:

- `responseCode()`: the HTTP status that triggered the retry/redirect requirement, e.g., 307.
- `getLocation()`: the `Location` string from the response, if present.
- `getReason()`: the failure reason per the API, not a substitute for the business source of truth.

If you want to follow manually, check the target URI using `URI.resolve(...)`/`URL` via safe APIs, validate the origin, control method/body replay, and enforce hop limits and request IDs. Do **not** automatically resend every POST/PUT simply because the exception includes a `Location`.

## 7. Java 17+: Streaming POST Encountering 307 and `HttpRetryException`

This loopback example demonstrates a situation that is very easy to misunderstand:

1. The client POSTs `HELLO` with `setFixedLengthStreamingMode(5)` and `setInstanceFollowRedirects(true)`.
2. The server endpoint `/moved` **receives and reads the entire body**, then returns `307 Temporary Redirect` to `/destination`.
3. When the client calls `getInputStream()` to read the response, the handler throws `HttpRetryException`; it **does not automatically issue a new POST** to the target URI in streaming mode.
4. The destination server `/destination` sees zero requests.

**File `StreamingRedirectDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.*;

public class StreamingRedirectDemo {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        AtomicReference<String> firstBody = new AtomicReference<>("");
        AtomicInteger destinationHits = new AtomicInteger();

        server.createContext("/moved", ex -> {
            try (ex) {
                firstBody.set(new String(ex.getRequestBody().readAllBytes(),
                        StandardCharsets.UTF_8));
                ex.getResponseHeaders().set("Location", "/destination");
                ex.sendResponseHeaders(307, -1);
            }
        });
        server.createContext("/destination", ex -> {
            try (ex) {
                destinationHits.incrementAndGet();
                ex.getRequestBody().readAllBytes();
                ex.sendResponseHeaders(204, -1);
            }
        });

        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/moved").toURL();
            HttpURLConnection c = (HttpURLConnection) url.openConnection();
            try {
                c.setInstanceFollowRedirects(true);
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setConnectTimeout(3000);
                c.setReadTimeout(3000);
                byte[] body = "HELLO".getBytes(StandardCharsets.UTF_8);
                c.setFixedLengthStreamingMode(body.length);
                try (OutputStream out = c.getOutputStream()) {
                    out.write(body);
                }

                boolean retryRequired = false;
                int redirectCode = -1;
                String destination = "";
                try (InputStream in = c.getInputStream()) {
                    in.readAllBytes();
                } catch (HttpRetryException expected) {
                    retryRequired = true;
                    redirectCode = expected.responseCode();
                    destination = expected.getLocation();
                }
                System.out.println("HttpRetryException: " + retryRequired);
                System.out.println("Redirect response: " + redirectCode);
                System.out.println("Redirect Location: " + destination);
                System.out.println("First server body: " + firstBody.get());
                System.out.println("Destination requests: " + destinationHits.get());
            } finally {
                c.disconnect();
            }
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 StreamingRedirectDemo.java
java StreamingRedirectDemo
```

**Verified stdout:**

```text
HttpRetryException: true
Redirect response: 307
Redirect Location: /destination
First server body: HELLO
Destination requests: 0
```

**Meaning of each line:**

- `HttpRetryException: true` proves that **automatic redirect is not handled** when output streaming is enabled. This is not a `SocketTimeoutException` or a DNS failure.
- `Redirect response: 307` indicates the status to examine, not a final 200. `307` preserves the method per the RFC if the application decides to follow manually.
- `Redirect Location: /destination` is a **relative reference**; it must be resolved against the appropriate response URI rather than using the raw relative string as an absolute URL.
- `First server body: HELLO` confirms that the initial POST **sent the full body to the server**, even though the client did not successfully follow.
- `Destination requests: 0` means the HTTP handler in this test **did not automatically replay the POST**. If the application needs to follow, it must initiate a **new request** with a replayable body and a safe policy.
- Because the first server received the body, there is **no basis** to claim the first operation “definitely did not process business logic.” The demo creates no real side effects, but a production server might.
- `disconnect()` in `finally` is part of cleanup, not an “undo POST” command.

**Scope note:** The example intentionally uses `setFixedLengthStreamingMode` and does not test `setChunkedStreamingMode`; the Javadoc describes the same limitation on automatic auth/redirect when output streaming is enabled. Hop count, method, and body are up to the application if handled manually.

## 8. HTTP/1.1 Keep-Alive: One TCP Connection, Multiple Requests

According to RFC 9112 §9.3, HTTP/1.1 allows **persistent connections** by default unless `Connection: close` is present or a condition prevents the connection from continuing to be used. A single TCP byte stream can sequentially carry multiple requests and responses if the messages have **self-delimiting boundaries**.

```text
TCP connection #A
  │
  ├── GET /a HTTP/1.1        ──► server
  │◄─ HTTP/1.1 200 OK        (Content-Length: 2, body OK)
  │
  ├── GET /b HTTP/1.1        ──► server
  │◄─ HTTP/1.1 200 OK        (Content-Length: 3, body YES)
  │
  ├── GET /c HTTP/1.1        ──► server
  │◄─ HTTP/1.1 200 OK        (Content-Length: 1, body 1)
  │
  └── idle timeout, Connection: close, error, policy ... → TCP closes
```

**Three different `HttpURLConnection` objects can share TCP connection #A.** Each object still represents only a single HTTP request at the API level; the JDK manages the physical connection at the layer underneath.

### Conditions for safe reuse

- The HTTP response must have a well-defined end, such as `Content-Length`, `Transfer-Encoding: chunked`, or no body per status/method. Close-delimited responses require EOF and therefore **cannot reuse the same connection**.
- The client must consume the entire response body if it wants reuse. In Java, **reading to the end of the `InputStream` provided by `HttpURLConnection` and closing the stream** is the practical pattern; the HTTP implementation knows its own framing, so do not confuse it with a raw `Socket` `InputStream`.
- The server must read the entire request body or close the connection after the response; otherwise, leftover request bytes can desynchronize the next request.
- The connection must still be valid, not closed by the peer or idle timeout, have no `Connection: close`, have no I/O errors, and the runtime pool must decide it is eligible for reuse.
- Same origin/endpoint/proxy/TLS context per pool policy. Changing host/port/proxy cannot by default use the same TCP socket.
- Either side has the right to close the connection when needed; keep-alive is **not a guarantee that the socket lives forever**.

### Why is `Connection: keep-alive` not required in HTTP/1.1?

HTTP/1.1 is **persistent by default**, so the `Connection: keep-alive` header is generally unnecessary to enable it. Some older HTTP/1.0 mechanisms used explicit keep-alive negotiation, but you should not treat that as a mandatory requirement for HTTP/1.1.

### `Connection: close` is an HTTP-layer signal

If a request or response contains the `close` token in the `Connection` header, both sides must obey the semantics of closing the connection after the corresponding final response. This is a **protocol intent on the wire**. It differs from the Java call `connection.disconnect()`, which is not a header that automatically guarantees the peer sees `Connection: close` in every situation.

## 9. What Happens at the TCP Layer After HTTP Keep-Alive?

After a complete response is read, the JDK HTTP handler may place an idle TCP socket into a connection cache to serve another request. The next `URL.openConnection()` call creates a **new object**, but if selected by the pool, the network stack may use the **old socket** instead of performing a new TCP three-way handshake.

```text
HttpURLConnection instance A
  GET /first  ───────► [TCP socket #17] ─► server
  response ◄───────── [TCP socket #17]
  response stream close()
                             │
                             ▼
                        idle/keepalive pool
                             │
                             ▼
HttpURLConnection instance B
  GET /second ───────► [TCP socket #17] ─► server
  response ◄───────── [TCP socket #17]
```

This is a **possible execution model**, not a guarantee about socket IDs. In practice, the JVM may open a new socket due to server closure, timeouts, parallel requests, proxies, HTTP headers, lack of an eligible connection, pooling policy, or errors.

### Read the entire response body before reuse

Especially avoid:

```java
// ANTI-PATTERN: not consuming or closing the response body.
HttpURLConnection c = (HttpURLConnection) url.openConnection();
int code = c.getResponseCode();
// Discarded without closing InputStream/ErrorStream and without cleanup.
```

This is an **illustrative anti-pattern**. It is not certain that the application has released request resources; the HTTP handler may not yet have returned the socket to an idle state for reuse. For large bodies, you should not necessarily call `readAllBytes()` because it can consume large amounts of RAM; instead, process in chunks, close the stream, and adjust your policy when you need to abort a body.

**Important distinction:** `InputStream.readAllBytes()` on the **stream returned by `HttpURLConnection`** reads until the end of the entity according to the HTTP implementation. By contrast, `readAllBytes()` on a **raw `Socket.getInputStream()`** waits for TCP EOF and can hang while keep-alive is open. Do not equate the two kinds of streams.

### Does `setUseCaches(false)` disable keep-alive?

`URLConnection.setUseCaches(boolean)` controls **content caching / protocol-specific cache behavior**, not a direct switch for the TCP keep-alive pool lifecycle. Do not use `setUseCaches(false)` to claim that every HTTP request will get a new socket.

### `SO_KEEPALIVE` is also not HTTP keep-alive

TCP `SO_KEEPALIVE` is a transport mechanism that can send probes on idle connections according to OS configuration. HTTP keep-alive/persistence is the **ability to carry multiple HTTP messages over the same connection**. They differ in function, timing, and API; avoid calling them by the same name and drawing false conclusions.

## 10. What Does `disconnect()` Actually Do?

This is the central point of the topic. The Java 17 Javadoc describes `HttpURLConnection.disconnect()` with the meaning:

> Indicates that other requests to the server are unlikely in the near future.

The Javadoc also explains:

- Each `HttpURLConnection` instance is used to make **a single request**.
- The underlying TCP connection **may be shared** by other instances.
- Closing the `InputStream` or `OutputStream` after a request may free resources associated with **this instance**, but **does not affect any shared persistent connection** by contract.
- Calling `disconnect()` **may close the underlying socket if a persistent connection is otherwise idle** at that time.
- **You must not infer that calling `disconnect()` allows the same instance to be reused for another request.**

The keyword to remember is **“may”**, not **“must.”** There is no contract saying “a `disconnect()` call always generates a TCP FIN immediately,” nor is there a contract saying “calling `disconnect()` always keeps the socket for reuse.”

### Separating four commonly confused actions

| Action | What you know for sure | What you must not infer |
|---|---|---|
| `responseStream.close()` | Closes the request's stream per the API | Nothing proves that any shared keep-alive socket closes |
| `connection.disconnect()` | Hints to the handler that no other requests are expected soon; may close an idle socket | Does not guarantee the socket closes immediately; cannot reuse the same object |
| `Connection: close` on an HTTP message | Issues a protocol directive not to continue reusing this connection after the response | Does not replace safely closing Java resources |
| TCP `FIN`/`RST` | Transport connection closes/aborts | Not a business cancellation or rollback of the server request |

### When can `disconnect()` actually close a socket?

If a persistent connection is currently **idle** and the implementation chooses to close it rather than keep it cached, `disconnect()` may cause the socket to be closed. However, if the server/handler is still using resources or the underlying connection is shared, behavior varies across implementations and runtimes; do not treat a test on one JDK as a promise for all environments.

**Do not use `disconnect()` as an exact socket-count pool management tool** or a way to “reset” an HTTP client; if you need system-level connection lifecycle control, use an HTTP client with explicit lifecycle APIs and measure network metrics.

### Does `disconnect()` cancel an in-flight request on the server?

There is no such contract. The server may have already received the request, written data, or committed a transaction. The client stopping reads or closing the connection does not roll back server-side side effects; business cancellation requires a dedicated API and reliable responses.

## 11. Java 17+: Observing TCP Reuse and `disconnect()`

To observe real reuse, this example creates an HTTP server on loopback. For each request, the server records the **client's remote TCP port**. When sequential requests from the same `127.0.0.1` to the same server see the same remote port, that is a useful indicator of connection reuse in this test.

All four calls to `fetch(...)` create **a new `HttpURLConnection` object**. They read the response stream to completion and close it. Only the **third** call invokes `disconnect()` after closing the stream; the **fourth** call measures whether the runtime continues to use the same TCP connection.

**File `KeepAliveDisconnectDemo.java`:**

```java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;

public class KeepAliveDisconnectDemo {
    private static String fetch(URL url, boolean callDisconnect) throws IOException {
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setConnectTimeout(3000);
        connection.setReadTimeout(3000);
        try {
            if (connection.getResponseCode() != 200)
                throw new IOException("Unexpected HTTP status");
            try (InputStream input = connection.getInputStream()) {
                return new String(input.readAllBytes(), StandardCharsets.UTF_8);
            }
        } finally {
            if (callDisconnect) connection.disconnect();
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        List<Integer> remotePorts = Collections.synchronizedList(new ArrayList<>());
        AtomicInteger requests = new AtomicInteger();
        server.createContext("/value", ex -> {
            try (ex) {
                remotePorts.add(ex.getRemoteAddress().getPort());
                int request = requests.incrementAndGet();
                byte[] bytes = ("R" + request).getBytes(StandardCharsets.UTF_8);
                ex.sendResponseHeaders(200, bytes.length);
                try (OutputStream output = ex.getResponseBody()) {
                    output.write(bytes);
                }
            }
        });
        try {
            server.start();
            URL url = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/value").toURL();

            String first = fetch(url, false);
            String second = fetch(url, false);
            String third = fetch(url, true);
            String fourth = fetch(url, false);

            System.out.println("Responses: " + first + "," + second
                    + "," + third + "," + fourth);
            System.out.println("Server request count: " + requests.get());
            System.out.println("First two reused TCP: "
                    + remotePorts.get(0).equals(remotePorts.get(1)));
            System.out.println("Third reused same TCP: "
                    + remotePorts.get(1).equals(remotePorts.get(2)));
            System.out.println("Fourth reused after disconnect: "
                    + remotePorts.get(2).equals(remotePorts.get(3)));
        } finally {
            server.stop(0);
        }
    }
}
```

Compile/run:

```bash
javac --release 17 -encoding UTF-8 KeepAliveDisconnectDemo.java
java KeepAliveDisconnectDemo
```

**Stdout observed across two runs on the tested JDK:**

```text
Responses: R1,R2,R3,R4
Server request count: 4
First two reused TCP: true
Third reused same TCP: true
Fourth reused after disconnect: true
```

**This is an OBSERVED result, NOT an invariant output guarantee across OSes and JDKs.** The lines containing `reused TCP` may be `false` in other environments due to runtime differences, when the server closes idle sockets, or pooling policies. Two things remain stable in meaning:

1. **Four separate HTTP requests** (`R1` to `R4`) were made using **four different `HttpURLConnection` objects**.
2. Connection reuse **can happen** even though every object serves only one request; and in this specific run, calling `disconnect()` after the third request **did not produce evidence of a new socket** on the fourth request.

### Analysis without over-extrapolating

- Comparing `getRemoteAddress().getPort()` from the same loopback server is a good indicator in a test. However, a port number is **not an invariant socket identifier in all circumstances**: the OS can reuse an ephemeral port after another connection (rare in a quick test), and proxies/NAT can hide endpoints in real environments.
- `First two reused TCP: true` shows that the handler reused the connection after response #1 was fully read and its stream closed. There is no explicit `Connection: keep-alive` in the source; HTTP/1.1 allows persistence by default.
- `Third reused same TCP: true` shows that the connection from request #2 was still eligible for #3.
- `Fourth reused after disconnect: true` is what learners often find surprising. `disconnect()` **may** close an idle socket, but there is no mandatory promise in the Javadoc. This test observed the runtime continuing to reuse it; another environment may differ.
- There is no valid reason to call `disconnect()` and then **send another request on that same object**; each new request must still create a new `openConnection()`.
- The test server returns an explicit `Content-Length` via `sendResponseHeaders(200, bytes.length)` and the client reads the entire body. These are favorable conditions for persistent reuse.
- Do not use `getRemoteAddress()` or a proxy's port number as a definitive metric in cloud applications; to measure production connection pooling, use HTTP client metrics, tracing, server connection IDs, or authorized network captures.

### Does proper cleanup always require calling `disconnect()`?

There is no rule that says “you must always call `disconnect()` after every GET.” Reading/closing the stream is the critical part of the resource lifecycle; calling `disconnect()` may be appropriate when the application wants to signal that it is done with an endpoint or release resources, but it may reduce reuse opportunities in some implementations. Long-term usage patterns and performance goals determine whether to call it. Conversely, **never leave an opened stream unclosed**.

## 12. Comparing `disconnect()`, `Connection: close`, and Stream Close

All three relate to “closing,” but each operates at a different layer.

### 12.1. `InputStream.close()`

`HttpURLConnection.getInputStream()` returns a stream for the response entity. Use try-with-resources to close it, even if the parser/consumer throws an exception:

```java
// Snippet: connection and expectedStatus are application variables.
try (InputStream body = connection.getInputStream()) {
    byte[] bytes = body.readAllBytes();
    processBytes(bytes);
}
```

This is an illustrative snippet, not a complete class; for large bodies, process in a streaming fashion to avoid allocating a large array. Closing the stream may release resources tied to **that request**, but it does not automatically mean a shared persistent socket must close.

### 12.2. `HttpURLConnection.disconnect()`

`disconnect()` is a local API on the Java HTTP handler. It is **not an HTTP method sent to the server**. It signals that no further requests are expected soon and may close an idle socket. Its exact interaction with the keep-alive implementation is a detail that should not be assumed fixed.

### 12.3. `Connection: close`

This is an HTTP header with protocol meaning:

```http
GET /last HTTP/1.1
Host: example.test
Connection: close

```

A client sending `Connection: close` means this is the last request on that connection and it must be closed after reading the final response. A server can also send `Connection: close` to indicate it will not keep the connection open after the response. This header is observable on the wire; `disconnect()` does not guarantee sending that header.

### 12.4. TCP close/FIN/RST

TCP `FIN` performs an orderly close of one sending direction; `RST` can indicate a reset/abort. Those are transport events. If the server already committed a POST before the connection closed, the client calling `disconnect` or seeing FIN/RST **does not undo** the commit.

```text
close InputStream
    → client-side response resource scope
    → may keep TCP idle/in pool

HttpURLConnection.disconnect()
    → local handler hint: not expecting to use server soon
    → idle socket may be closed

HTTP Connection: close
    → protocol directive sent/received with peer
    → do not continue reusing connection after response

TCP FIN/RST
    → transport close/reset event
    → not a business operation rollback
```

## 13. How Can Redirects and Keep-Alive Interact?

Suppose a Java client fetches `http://a.example.test/old`, receives `302 Location: /new`, and then `200`. There are two distinct events:

1. **Redirect** decides whether to send an additional HTTP request to a **new URI**.
2. **Connection persistence** decides whether that new request can reuse an already-open **TCP socket**.

If `Location` stays on the same scheme/host/port and the old connection is still idle and eligible, reuse can occur. If the redirect goes to a different host, different port, or changes protocol/TLS, a connection suitable for the destination is needed; the old socket does not “morph.” Proxies can create different patterns at each hop; you cannot simply count `HttpURLConnection` objects to deduce the number of TCP sockets.

### Example scenarios

| Scenario | Redirect? | New TCP socket? |
|---|---|---|
| GET `/old` → 302 `/new` same host | Yes, if following | **May reuse** if eligible |
| GET `/old` → 302 to different host | Yes, if following | Cannot by default share the same endpoint socket |
| GET `/old` → no-follow returns 302 | No request to the new URL from this object | No subsequent network request due to following |
| Server returns 200 `Connection: close` | Unrelated to redirect | Current connection is not reused further |
| Calling `disconnect()` after response | Not a redirect | Idle socket **may** close or remain reusable depending on runtime |
| Partially reading response and abandoning stream | Not necessarily a redirect | Not eligible for safe reuse per RFC if body is unconsumed |
| Streaming POST receives 307 | Requires manual evaluation | `HttpRetryException`, does not auto-resend body |

Do not use a redirect loop to “refresh a socket,” and do not rely on keep-alive to conclude that every redirect is cheap in network cost. If origin, TLS, proxy, authentication, or DNS changes, latency and security risks can change.

## 14. Handling HTTP Errors and Resources in Real Applications

`getInputStream()` can throw `IOException` for error statuses (typically 4xx/5xx). `HttpURLConnection` provides `getErrorStream()` so the application can read the error response body **if one exists**. Do not simply catch `IOException` and discard the response body; it may contain a useful JSON message, though it should be processed with size/format limits.

### Controlled pattern

```java
// Illustrative snippet, not standalone; URL 'url' is validated beforehand.
HttpURLConnection c = (HttpURLConnection) url.openConnection();
c.setInstanceFollowRedirects(false);
c.setConnectTimeout(3000);
c.setReadTimeout(5000);
try {
    int status = c.getResponseCode();
    InputStream selected = status >= 400
            ? c.getErrorStream()
            : c.getInputStream();

    if (selected != null) {
        try (InputStream body = selected) {
            // Stream in chunks; do not necessarily readAllBytes for large bodies.
            byte[] buffer = new byte[8192];
            while (body.read(buffer) != -1) {
                // Decode/consume bytes with bounds; do not ignore errors.
            }
        }
    }
} finally {
    c.disconnect();
}
```

This is an **illustrative pattern, not a standalone class**. Calling `disconnect()` after every request is a simple cleanup policy in this snippet; if you are optimizing pooling, you may prefer reading to completion and closing the stream, managing the connection lifecycle per your client library/documentation. Do not call `getErrorStream()` when no error has occurred and do not assume it always returns a stream: the Javadoc allows it to return `null`.

### Connect timeout and read timeout

- `setConnectTimeout(ms)` sets the timeout for **establishing the connection** (a value of 0 is generally infinite per the Java contract).
- `setReadTimeout(ms)` sets the timeout for **reading data** on the connection; if no data arrives within the timeout, it can throw `SocketTimeoutException`.
- **They are not** a strict end-to-end total deadline for the entire redirect chain, body streaming, or business transaction. An application-managed overall deadline may be necessary.
- If a redirect traverses multiple hops, each hop can have its own connection and I/O; do not treat `readTimeout(3000)` as “the entire redirect chain is guaranteed to take at most 3 seconds.”
- If the caller times out or the connection drops after a POST, do not automatically retry with a new request ID because **the server may have already processed the side effect**.

### When should you close the request output stream?

For POST/PUT with a body, use try-with-resources for `getOutputStream()` to ensure buffered bytes are flushed per the stream contract, or to detect write errors. **Closing the output stream is not a business ACK.** Read the response status/body afterward, because the server may return 4xx/5xx or 3xx; do not treat “writing threw no exception” as a successful request.

## 15. Common Mistakes

| Mistake | Consequence or misconception | Fix |
|---|---|---|
| `openConnection()` = new TCP connect immediately | Miscounting sockets/cost | Distinguish the Java object from the network I/O trigger |
| Reusing one `HttpURLConnection` for multiple requests | Violates the one-request-per-instance model | Create a new connection object for each request |
| `setFollowRedirects(false)` in a shared JVM library | Alters static behavior for other modules | Use `setInstanceFollowRedirects(false)` per request |
| Enabling follow and assuming final 200 never went through 302 | Loses redirect audit information | Disable auto-follow if each hop must be inspected |
| Auto-following every `Location` without validation | SSRF, leaking credentials/internal files | Allowlist scheme/host/port, TLS, hop limit |
| Using GET redirect to assume POST 307 auto-resends | Lost/corrupted request body | Consider method, streaming mode, replayability |
| Streaming POST gets `HttpRetryException` and retries blindly | Duplicate side effects, data exposure | Use a policy, request ID/idempotency, and explicit resend |
| `setChunkedStreamingMode` when server does not support chunked | 411/400/connection failure | Verify server support, use appropriate fallback protocol |
| `getResponseCode()==200` then abandoning response stream | Leaks, reduced reuse eligibility | Read completely/close stream or abort per policy |
| Assuming `disconnect()` guarantees socket closure | Wrong inference; tests may still reuse | Use network metrics, understand Javadoc “may” |
| Calling `disconnect()` to reset an object for a new request | Misusing API lifecycle | Open a new `HttpURLConnection` |
| Omitting `Connection: close` while still expecting strict no-reuse | No protocol signal | Configure client/server/proxy per contract |
| `setUseCaches(false)` = disable keep-alive | Confuses HTTP caching with connection reuse | Distinguish the two kinds of caches |
| TCP `SO_KEEPALIVE` = HTTP/1.1 persistence | Confuses transport probes with reuse | Manage at the appropriate layer |
| `readAllBytes` on a raw TCP socket | May block on EOF forever with keep-alive | Use an HTTP parser/library framing |
| Only using `getInputStream()` for 404/500 | `IOException`, losing error body | Use `getErrorStream()` when an error response exists |
| Not limiting redirect hops | Loops, SSRF, resource exhaustion | Hop count, visited URLs, overall deadline |
| Ignoring cross-origin auth | Credential leakage | Do not copy `Authorization`/`Cookie` arbitrarily |
| Believing status/network failure means POST definitely did not commit | Retries can create duplicate data | Business ID, dedup/idempotency, status query |
| Calling `disconnect` on every GET “to improve performance” | May reduce reuse in some runtimes | Close response properly, benchmark policy |

### Differences between HTTP errors and transport errors

- HTTP `404/500` is a **response with an HTTP status**; the server may return an error body.
- `SocketTimeoutException` is an **I/O timeout**, not HTTP status `408`.
- `HttpRetryException` on streaming redirect/auth means **the handler did not auto-resend**, not proof that the server never received the body.
- `IOException`/`ConnectException` when unable to connect differs from the server returning `503`.
- `disconnect()` does not generate any HTTP status; it is a local call that may affect network resources depending on the implementation.

## 16. When to Use Modern HttpClient Instead of HttpURLConnection?

Since Java 11, the `java.net.http` module provides `HttpClient` for modern HTTP workflows, supporting `HttpRequest`/`HttpResponse`, `sendAsync` with `CompletableFuture`, HTTP/2 where negotiated, response body handlers, and explicit redirect policies.

Configuration example:

```java
// Illustrative snippet, not a standalone program.
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.test/resource"))
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();

HttpResponse<String> result = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Note: the snippet above requires imports from `java.net.http.*`, `java.net.URI`, and `java.time.Duration`; the URI `example.test` is illustrative. In Java 17, **`HttpClient.Redirect.NEVER` is the default**, unlike **`HttpURLConnection`'s static follow redirects which defaults to `true`**. Do not carry assumptions from one API to the other.

Modern `HttpClient` is usually appropriate when you need async requests, explicit redirect policies, HTTP/2, body publishers, and complex request management. However, **do not mistake a “newer” client for one that automatically guarantees idempotent retries, safe cross-origin authorization, or correct business transactions**: every security boundary still requires application policy.

### Do not switch APIs just to “guarantee disconnect closes TCP”

The goal of HTTP connection pooling is **safe connection reuse and reduced overhead**. Switching to `HttpClient` does not mean every request uses a new socket. If a special requirement demands immediate connection termination, the design must account for the right lifecycle APIs, server, and proxy; there is no simple switch that replaces understanding connection pooling.

## 17. Self-Check Questions

**Question 1.** `url.openConnection()` returns an `HttpURLConnection`. Is a TCP socket guaranteed to have just been opened?  
**Answer:** No. It may only create an unconnected object; `getResponseCode` or an I/O getter triggers the connect/request.

**Question 2.** Can the same `HttpURLConnection` object be used to send GET requests to two different paths?  
**Answer:** Not according to the API model; one instance represents one request. Create a new object for a new request. Auto-redirects may generate additional network hops within the same logical request.

**Question 3.** Does HTTP/1.1 keep connections persistent by default or close them after every response?  
**Answer:** Persistent if there is no condition to close. Actual reuse also depends on message framing, server policy, and the pool.

**Question 4.** With `setInstanceFollowRedirects(true)` enabled and the server returning 302→200, which status does `getResponseCode()` typically observe?  
**Answer:** The final 200 if following succeeds as in the demo, not the intermediate 302.

**Question 5.** If you want to inspect `Location` before deciding whether to follow, what should you configure?  
**Answer:** `setInstanceFollowRedirects(false)` before connecting, then read `getResponseCode/getHeaderField("Location")` and validate the URI.

**Question 6.** Does `HttpURLConnection.setFollowRedirects(false)` differ from `setInstanceFollowRedirects(false)`?  
**Answer:** Yes. The first is static/class-wide, while the second applies to a specific object.

**Question 7.** A server returns 307 after a fixed-length streaming POST. Is the handler guaranteed to automatically replay the body?  
**Answer:** No. The Javadoc states streaming mode cannot automatically handle redirects/auth and may throw `HttpRetryException` when reading the response.

**Question 8.** `HttpRetryException.responseCode()` is 307, and `getLocation()` is `/new`. Should you immediately resend the POST?  
**Answer:** Only after validating the target, method/body replayability, security, and idempotency; the first server may already have processed side effects.

**Question 9.** Does calling `disconnect()` after a GET mean the JDK is guaranteed to close the idle TCP socket and the next request must open a new socket?  
**Answer:** No. The Javadoc says **may close**, not **must close**. The demo shows a runtime that still reuses after `disconnect()`.

**Question 10.** How do response `InputStream.close()` and `Connection: close` differ?  
**Answer:** Closing the stream is local API cleanup; `Connection: close` is an HTTP signal on the wire requesting persistence to end after the response.

**Question 11.** Is `setUseCaches(false)` the right way to disable TCP keep-alive?  
**Answer:** No. It relates to resource caching, not a switch for socket persistence.

**Question 12.** A client does not read the entire response body but wants to reuse the same connection. Is that safe?  
**Answer:** It must not be assumed; RFC 9112 requires reading the entire response body to reuse the same connection, or else not reusing/closing per policy.

**Question 13.** `getInputStream()` throws an error on status 404. How do you read the error body if the server sent one?  
**Answer:** `getErrorStream()` can return the body; check for null and close it after reading.

**Question 14.** Does the demo's `Fourth reused after disconnect: true` line prove that every JDK always reuses after `disconnect()`?  
**Answer:** No. That is only an observation on the tested runtime; other environments may return `false`.

**Question 15.** Is `Connection: keep-alive` required in every HTTP/1.1 request?  
**Answer:** No. HTTP/1.1 is persistent by default unless a closing condition applies.

**Question 16.** Does `disconnect()` after a POST whose body was already sent automatically roll back a database transaction on the server?  
**Answer:** No. You need a separate protocol/transaction cancellation or business state verification.

**Question 17.** Should you automatically follow a redirect to a new host with `Authorization` and a body containing personal data?  
**Answer:** Not by default. You must verify origin, scheme/TLS, allowlist, permission to send the body, and credential protection.

**Question 18.** Are the default redirect settings of `HttpURLConnection` and Java 17 `java.net.http.HttpClient` the same?  
**Answer:** No. `HttpURLConnection`'s class setting defaults to `true`, whereas `HttpClient.Redirect` defaults to `NEVER`.

**Question 19.** To bound an entire redirect chain under 5 seconds, is `setReadTimeout(5000)` alone sufficient?  
**Answer:** Not necessarily. Read timeout is not an overall deadline across all hops; a separate coordinated deadline is needed.

**Question 20.** If TCP keep-alive probes are enabled, does that mean every HTTP request reuses the same socket?  
**Answer:** No. TCP keepalive checks/maintains an idle connection at the transport layer; HTTP reuse also depends on protocol framing and runtime policy.

## 18. Checklist and Summary

- [ ] Each **`HttpURLConnection` object** is one logical HTTP request; the transport may be shared across objects.
- [ ] An HTTP redirect is a **3xx response + `Location`**; following can generate additional requests and change URI/method/body per policy.
- [ ] Use **`setInstanceFollowRedirects(false)`** if you need to inspect `Location` and verify the target before following; avoid changing the global static setting unnecessarily.
- [ ] `HttpURLConnection` follows redirects by default per the Java 17 Javadoc, but **do not assume every status/method/scheme is followed**.
- [ ] For POST/PUT, verify method preservation, **body replayability**, and business idempotency before resending.
- [ ] With `setFixedLengthStreamingMode` or `setChunkedStreamingMode`, understand the limitation of **no automatic follow/auth resend**; handle `HttpRetryException` intentionally.
- [ ] HTTP/1.1 persistence does not require `Connection: keep-alive` in every message; **`Connection: close`** has semantics to terminate persistence.
- [ ] Read the **entire** response body properly and close `InputStream`/`ErrorStream` when used; do not read raw TCP to EOF to determine message length on a persistent connection.
- [ ] `disconnect()` is **not** “immediately close all sockets,” not an instance reset, and not a server rollback; the Javadoc says an idle socket **may** be closed.
- [ ] Do not equate HTTP keep-alive with TCP `SO_KEEPALIVE` or HTTP content caching.
- [ ] Use `setConnectTimeout` and `setReadTimeout`, and add an overall deadline/retry policy if the business logic requires it.
- [ ] Do not let redirects to untrusted hosts automatically receive credentials or sensitive bodies; enforce allowlists, TLS, hop counts, and observability.
- [ ] When you need HTTP/2, async, and an explicitly configured redirect policy, consider **`java.net.http.HttpClient`**, without carrying `HttpURLConnection` assumptions into the new API.

**Key takeaway:** redirects determine the **next URI/method/request**; keep-alive determines whether a **TCP socket can be reused**; `disconnect()` is only **a local hint that no new requests are expected soon and that an idle socket may be closed**. All three are related, but none are identical. Understanding these boundaries prevents lost request data, dangerous redirects, leaked streams, and false conclusions when measuring TCP connection counts.

### Official References

- [Java 17 `HttpURLConnection` — one-request-per-instance, redirects, streaming, disconnect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html)
- [Java 17 `URLConnection` — lifecycle, connect, input/output streams, timeouts](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html)
- [Java 17 `HttpRetryException` — response code, Location, reason](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpRetryException.html)
- [Java 17 `HttpsURLConnection` — HTTPS over TLS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html)
- [RFC 9112 9.3–9.6 — HTTP/1.1 persistence and close](https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3)
- [RFC 9110 15.4 — HTTP redirect semantics](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.4)
- [Java 17 `HttpClient.Redirect` — modern HTTP client redirect policy](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Redirect.html)
