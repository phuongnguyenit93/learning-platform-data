# JDK HttpServer: Closing HttpExchange, Handling Errors, and Preventing Clients from Waiting Forever

## 1. The problem: the handler receives a request, yet the client keeps spinning

You are using `com.sun.net.httpserver.HttpServer` to build a Java 17+ HTTP server. The server has received `GET /api`, yet `HttpClient`, `curl`, or the browser keeps waiting for a long time. There are several different reasons for this:

- The handler runs to the end **without calling `sendResponseHeaders(...)`**: no complete HTTP status/headers are sent.
- Headers were sent, but the handler **forgot to write enough bytes** to match `Content-Length` or **forgot to close the response stream**: the client may not know the response body has ended, or it may receive a truncated response / I/O error.
- An exception occurs inside the handler and escapes without **producing a controlled error response**, so the client may only see a closed connection, a network error, or wait until timeout.
- The handler **gets stuck reading the request body**, calling an external database/API, waiting on a lock, or sleeping with `Thread.sleep` for a long time; it has not reached the step of sending a response.
- Server worker threads are **exhausted**, the executor queue is long, or an upstream proxy/LB holds connections for a long time; the request has not been processed in time.
- The code passes the wrong `responseLength`: using `0` with the intention of "no body", whereas JDK `HttpExchange` interprets `0` as a **chunked response**, which requires closing the stream to finish.
- The client does not configure a timeout; if the server does not respond/close properly, the caller may wait longer than the application accepts.

This lesson is about **the lifecycle of a request/response in the lightweight HTTP server bundled with the JDK**, not a guide to building a full-featured web server framework. The goal is to use `HttpExchange` properly, **provide an intentional response on every valid and predictable error path**, know when it is no longer possible to change the HTTP status, close resources properly, design deadlines, and avoid leaving clients waiting indefinitely.

### 1.1. Diagram of an exchange

~~~text
Client                JDK HttpServer / HttpHandler
  |                              |
  | -------- request ----------> |  accept/dispatch exchange
  |                              |  read method, URI, headers
  |                              |  (read request body if needed)
  |                              |  validate -> service logic
  | <--- status + headers ------ |  sendResponseHeaders(...)
  | <------- body bytes -------- |  getResponseBody().write(...)
  | <------- end of body --------|  close response stream / exchange
  |                              |  release resources
  |                              |
  |  Error state if no response yet:
  | <---- 4xx/5xx + body ------- |  error response and close
  |
  |  If error occurs AFTER headers:
  | <--- may be truncated -------|  cannot change status to 500
~~~

**Fundamental rule:** an `HttpExchange` represents **one HTTP transaction**, consisting of one request and one response; you must ensure it **is terminated properly**. `HttpExchange.close()` closes the request body stream and the response body stream if they are not already closed. It is not a command that "automatically generates HTTP 200/500", so **do not just call `close()` and forget to send a valid response**.

## 2. Classes and roles in the `jdk.httpserver` module

JDK 17 provides the `jdk.httpserver` module, package `com.sun.net.httpserver`. Its main components:

| Component | Responsibility |
| --- | --- |
| `HttpServer` | Binds address/port, creates URL contexts, uses an executor to handle HTTP requests, start/stop |
| `HttpHandler` | Callback `handle(HttpExchange)` that processes **one exchange** |
| `HttpExchange` | Holds method, URI, request headers/body, and response headers/body |
| `HttpContext` | Maps a URL path to a handler and configures filters |
| `Headers` | Map of HTTP headers, with `getFirst`/`set` |
| `Filter` | Intercepts request/response in a filter chain; must also obey the response lifecycle |
| `HttpsServer` | HTTP server using TLS; requires `HttpsConfigurator` and appropriate certificate/trust configuration |

This is a **lightweight** HTTP server API for learning, testing, small services, or controlled environments. It **does not come with** full routing frameworks, authentication/authorization, multipart handling, body size quotas, rate limiting, distributed tracing, JSON serialization, transactional persistence, or production-grade endpoint security.

Example of setting up a server:

~~~java
HttpServer server = HttpServer.create(
        new InetSocketAddress("127.0.0.1", 8080), 0);

server.createContext("/api", exchange -> {
    // Handle one request, send the proper response, always finish the exchange.
});

server.start();
~~~

This is an **illustrative snippet**; it requires importing `com.sun.net.httpserver.*` and `java.net.*`, and running on a machine where port 8080 is available. `start()` launches a background thread to handle connections. Each handler is not automatically given a timeout just by calling `createContext`.

### 2.1. One exchange ≠ one TCP connection

HTTP/1.1 can **reuse a connection** across multiple requests via keep-alive. However, each individual request/response has its own `HttpExchange`. The handler must complete the current exchange before the client can continue reading the response and safely reuse the connection.

If the request body has not been fully read, the JDK may attempt to read/discard some amount of data when closing the stream, but according to the official documentation, **failing to consume the entire request body may prevent the TCP connection from being reused**. There is no guarantee that closing the exchange will preserve keep-alive in every situation.

## 3. Standard lifecycle of `HttpExchange`

The JDK 17 documentation describes the standard flow:

1. `exchange.getRequestMethod()`: determine the HTTP method.
2. `exchange.getRequestURI()`, `getRequestHeaders()`: read the path and metadata.
3. `exchange.getRequestBody()`: read the body if needed; **enforce size/time limits** and close it.
4. `exchange.getResponseHeaders()`: set appropriate headers **before committing the response**.
5. `exchange.sendResponseHeaders(statusCode, responseLength)`: **begin sending** the status and headers; once sent, the status cannot be changed at will.
6. `exchange.getResponseBody()`: write the exact bytes if there is a response body.
7. **Close the response stream and exchange** (try-with-resources or `finally`); clean up resources outside the exchange.

~~~java
static void hello(HttpExchange exchange) throws IOException {
    try (exchange) {
        byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);

        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);

        try (OutputStream body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }
}
~~~

The snippet above is a **method inside a class**, requiring imports for `HttpExchange`, `IOException`, `OutputStream`, and `StandardCharsets`. For a `GET` with no significant request body, this is the right minimal pattern: set headers, commit status/length, write the **exact number of bytes**, close the stream and the exchange.

**There is no need to call `close()` again manually** after `try (exchange)`; Java calls it when exiting the block, even on `return` or an exception. When the response stream has already been closed separately inside `try`, `exchange.close()` also checks and closes any remaining streams. If you manage `close()` manually with `finally` instead of try-with-resources, you must also ensure both success and failure paths go through cleanup.

### 3.1. Which sequences are wrong?

~~~java
// WRONG: body before sending status/headers.
OutputStream body = exchange.getResponseBody();
body.write("hello".getBytes(StandardCharsets.UTF_8));
exchange.sendResponseHeaders(200, 5);
~~~

`getResponseBody()` must be used **after** `sendResponseHeaders(...)` according to the API. Reversing the order can cause errors or an invalid state; avoid relying on implementation details.

~~~java
// WRONG: returning without an HTTP response.
if (invalidInput) {
    return;
}
~~~

An `HttpHandler` that finishes without sending a valid response may cause the client to get a connection error or wait until timeout, rather than **automatically producing `400 Bad Request`**. If `invalidInput` can be detected, **send a proper 400** and then close the exchange.

~~~java
// WRONG: sending headers twice on the same exchange.
exchange.sendResponseHeaders(200, 5);
exchange.sendResponseHeaders(500, 0);
~~~

You cannot "fix" an already started response like this; calling `sendResponseHeaders` after it has already been committed can throw `IOException`. There is only **one response status/header commit** per exchange.

## 4. The `responseLength` parameter: three cases to remember accurately

This is one of the most important points of `HttpExchange`:

| Call | Meaning in JDK 17 | What to do |
| --- | --- | --- |
| `sendResponseHeaders(200, n)`, **n > 0** | Fixed-length response body, exactly **n bytes** | Write **exactly n bytes**, close output |
| `sendResponseHeaders(200, 0)` | **Chunked transfer coding** for a response body of undeclared length | Can write any number of bytes; must **close output** to end the chunked body |
| `sendResponseHeaders(204, -1)` | **No response body** | Do not write a body; still finish exchange/streams |

**Very common mistake:** "0 means return an empty body" — **incorrect** in this API. With `HttpExchange.sendResponseHeaders`, **0 enables a chunked response**, not a completed response with no body. To **send no body**, use `-1`; statuses such as **204 No Content** and **304 Not Modified**, as well as HEAD responses, must respect HTTP no-body semantics.

### 4.1. Fixed-length: count **bytes**, not Java characters

~~~java
String message = "Xin chào";
byte[] bytes = message.getBytes(StandardCharsets.UTF_8);

exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, bytes.length);

try (OutputStream out = exchange.getResponseBody()) {
    out.write(bytes);
}
~~~

`"Xin chào"` has **8 UTF-16 code units** but **9 UTF-8 bytes**. Because `responseLength` is the number of **bytes on the wire**, you must not use `message.length()` to declare the length. If you declare fewer bytes and write more, `write` may throw `IOException`; if you declare more than the actual count and close, `close` may throw `IOException`. In both cases, the JDK may **abort the exchange and close the TCP connection**, causing the client to report a truncated response rather than automatically producing a 500.

### 4.2. Chunked: use 0 when the size is not known in advance

~~~java
exchange.getResponseHeaders().set(
        "Content-Type", "text/plain; charset=utf-8");
exchange.sendResponseHeaders(200, 0);

try (OutputStream out = exchange.getResponseBody()) {
    out.write("part-1\n".getBytes(StandardCharsets.UTF_8));
    out.write("part-2\n".getBytes(StandardCharsets.UTF_8));
} // Close output to send the end of the chunked response.
~~~

This is an **illustrative snippet** inside a handler. `sendResponseHeaders(..., 0)` allows a body whose size is unknown upfront in HTTP/1.1, suitable for some streaming responses. However, if the stream is forgotten or the generator never finishes, **the client may keep waiting for the body**. For intentionally long-lived streams like SSE, dedicated protocol/timeout/cancellation handling is needed; do not use chunked encoding to mask a handler that lacks a completion path.

### 4.3. No body: use -1

~~~java
try (exchange) {
    exchange.sendResponseHeaders(204, -1);
}
~~~

A `204 No Content` response **sends no representation body**. `-1` is the appropriate choice. Do not send `Content-Type: application/json` and a `{}` body with 204 expecting the client to read content; 204 is a status that carries no body. `304 Not Modified` is also a no-body response. For `HEAD`, the server must implement HTTP HEAD semantics (metadata matching GET, **no message body sent**); use the length/headers option appropriate for the JDK and test directly.

### 4.4. "Already called sendResponseHeaders" can still fail

`sendResponseHeaders` can throw `IOException` if headers were already sent or an I/O error occurs. To guard against sending two responses, a `Reply` wrapper can mark **commit started before calling the API**. This is **conservative**: even if writing the headers fails partway through, the code will not try to emit a second `500` onto the same socket in an unknown state.

## 5. Why must we close the response body and the entire exchange?

### 5.1. Closing the stream is part of the protocol, not just saving RAM

When choosing fixed-length, the server must send the full byte count. When choosing chunked, the end of the body usually depends on **closing the response stream**, because that is when the implementation finishes framing. If you forget to close output, the client may not know the body is done; the connection cannot be safely reused and server resources may be held for a long time.

In JDK 17, `HttpExchange.close()` closes the **request InputStream first, then the response OutputStream** if they are not already closed. That is the mechanism for terminating an exchange on every exit path. Even for a response with no body, the exchange must still be closed properly.

### 5.2. `try (exchange)` is an important guard

~~~java
static void handler(HttpExchange exchange) {
    try (exchange) {
        // Every normal path must commit a response before exiting the block.
        // If handling an error before commit: send a 4xx/5xx response.
    }
}
~~~

This is a **skeleton snippet**, not a complete handler: if the block does not send status/headers, there is still a problem at the HTTP layer. `try-with-resources` guarantees cleanup when the method returns or throws an exception, but it **does not decide** the appropriate HTTP status code for you.

### 5.3. Closing an unread request body affects keep-alive

`exchange.getRequestBody()` is an `InputStream` that may contain a request body. For POST/PUT, you should read the amount allowed by the protocol and API, bound size/time, and then close it. If a client sends a large request body and the handler returns an error early (e.g., 413) without consuming the body, the JDK may discard a portion on close, **with no guarantee of keeping the connection for reuse**. This does not mean the handler has an HTTP bug; it is a connection-management tradeoff.

Do not **read/discard unbounded** untrusted data just for the sake of keep-alive: a sender can stream very slowly, forcing a server thread to wait forever. Accept closing the connection when the body is too large or shows signs of abuse, alongside infrastructure timeout and quota policies.

### 5.4. There is no "magic finally"

~~~java
try {
    doWork();
} finally {
    exchange.close();
}
~~~

The block above ensures resources are closed, **but sends no HTTP status** if `doWork()` throws before commit. The client may see a connection close/network error, with no `500`. Always **handle errors before commit** and then clean up in `finally`.

## 6. Handling errors at the right time: before commit and after commit

A response has two essential phases:

~~~text
[PRE-COMMIT]                [COMMITTED]                    [DONE]
validate -> service work -> sendResponseHeaders -> body.write -> body.close()
      |                             |
      |                             +-- Error after commit:
      |                                 cannot change status 200 -> 500;
      |                                 close stream/socket and log.
      |
      +-- Error before commit:
          can choose 400/404/405/413/500/503,
          set headers + status + body once.
~~~

### 6.1. Errors **before** sending headers

For example, a database lookup throws `IllegalStateException` before a response is started. The handler can catch the exception, log internally, and send:

~~~http
HTTP/1.1 500 Internal Server Error
Content-Type: text/plain; charset=utf-8
Cache-Control: no-store

internal-error
~~~

Do not return stack traces, SQL, API tokens, or filesystem paths to the client. **500 is a server-side error**, distinct from 400 caused by an invalid request. For intentional transient upstream failures, 503 may be appropriate and may include `Retry-After` per policy; do not blindly turn every runtime exception into 503.

### 6.2. Errors **after** sending headers

Suppose the server has already sent:

~~~http
HTTP/1.1 200 OK
Content-Length: 1000
~~~

Then after writing 200 bytes, file I/O fails. **You cannot change the status** of an in-flight response to 500, nor can you send a second 500 response on the same exchange. Practical options:

- Log the cause, correlation ID, bytes sent, and committed state.
- Close the stream/exchange or let the implementation abort the connection when fixed-length is short.
- The client receives an incomplete body, EOF, IOException, or length mismatch depending on transport; receiving 500 is not guaranteed.
- If you must avoid exposing partial success, you must **compute/validate the entire output before committing** (when the size is reasonable), or design a protocol supporting chunk-level checksums/trailers/aborts that the client understands.
- If streaming is very long, the status may have been committed long ago; this requires error handling **at the application stream layer** instead of pretending HTTP status can still be changed.

### 6.3. Marking commit conservatively

In a response helper, set `committed=true` **right before** `sendResponseHeaders(...)`; if the call hits an I/O error midway, we **do not attempt to send another status** because we do not know how many header bytes already went onto the network.

~~~java
void send(int status, byte[] bytes) throws IOException {
    if (committed) {
        throw new IllegalStateException("Already committed");
    }
    committed = true;
    exchange.sendResponseHeaders(status, bytes.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(bytes);
    }
}
~~~

This is an illustrative snippet (only valid when `bytes.length > 0`); the full runnable class below distinguishes no-body `-1`. If `write` or `close` throws an error, the committed state remains accurate. **Do not call `sendResponseHeaders(500, ...)` again**.

### 6.4. Handling `IOException` when the client has already left

If the client times out, closes the tab, loses Wi-Fi, or cancels the request, `OutputStream.write()` may throw `IOException`. At that point there may not be any client left to read a `500`; the sensible thing to do is **close resources, log at an appropriate level, and update metrics**. Do not create an infinite loop trying to "send an error back to a client" that is already gone.

## 7. Which status code to choose when handling a request

| Situation | Usually appropriate status | Notes |
| --- | --- | --- |
| Successful GET with body | **200 OK** | Send Content-Type and exact bytes |
| Request has invalid input data | **400 Bad Request** | Not every Java error is a 400 |
| Resource does not exist | **404 Not Found** | May include an error representation |
| Method not supported at endpoint | **405 Method Not Allowed** | Send `Allow` header with allowed methods |
| Request body exceeds quota | **413 Content Too Large** | Limit actual bytes read; may need to close connection |
| Unexpected logic/server error before commit | **500 Internal Server Error** | Log internally; short/generic error message |
| Service temporarily unable to serve | **503 Service Unavailable** | May include `Retry-After`; avoid using for all errors |
| Success with no response body | **204 No Content** | Use no-body `-1` |
| Client sends request too slowly or incompletely | **408 Request Timeout** *if the server can return this status* | Not synonymous with every Java timeout |
| Gateway/proxy timed out waiting on upstream | **504 Gateway Timeout** | Usually from an intermediary/proxy, not a default JDK handler |

**Distinguish two kinds of "timeout":** `HttpTimeoutException` on the Java client side is an **exception**, which can occur when **no HTTP response** is received at all. It is **not HTTP status 408/504**. Do not invent a response code just because the client gave up waiting.

### 7.1. `400` is different from `500`

If query parameter `limit=abc` fails to parse as a number, returning 400 with a safe explanation is reasonable. If the database driver throws an unexpected exception, it should be treated as a server error (500/503 depending on nature), not 400 blaming the client. Classify exceptions by **source and meaning**, rather than catching everything and returning a single status.

### 7.2. `405` requires Allow

~~~java
if (!"GET".equals(exchange.getRequestMethod())) {
    exchange.getResponseHeaders().set("Allow", "GET");
    // Send 405 + appropriate body and finish exchange.
}
~~~

The HTTP specification requires a 405 response to include `Allow` listing the currently supported methods. When only GET is supported, note that HTTP HEAD semantics are a separate concern; the demo below intentionally restricts to GET and returns 405 for all other methods, rather than being a REST framework supporting HEAD by default.

## 8. Self-contained Java 17+ example: every normal path responds, errors get 500, client has a timeout

This example uses **HttpServer** and **HttpClient**, both from the JDK. The server runs on IPv4 loopback `127.0.0.1` with a random port (port 0), without Internet access. Routes:

- `GET /ok`: `200` with body `ok`.
- `GET /bad`: `400` with body `bad-request`.
- `GET /fail`: intentionally throws `IllegalStateException` **before commit**; wrapper returns `500` + `internal-error`.
- `GET /missing`: `404` + `not-found`.
- `GET /empty`: `204` **no body**, using `-1`.
- `POST /ok`: `405` + `method-not-allowed`, header `Allow: GET`.
- `GET /slow`: intentionally delays 1.5 seconds; client sets a 150 ms timeout and receives `HttpTimeoutException`. **This timeout is decided by the client**, not by the server generating status 408/504.

The handler uses `try (exchange)`, a `Reply` helper that writes a response **only once** and tracks the `committed` flag. The server has its own executor and cleans it up when the program exits. This is an educational example: response bodies are tiny, routes are fixed; `Executors.newFixedThreadPool` uses an **unbounded** default queue, which is not a production load-handling configuration.

Save to **ExchangeLifecycleDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ExchangeLifecycleDemo {
    static final class Reply {
        final HttpExchange exchange;
        boolean committed;

        Reply(HttpExchange exchange) {
            this.exchange = exchange;
        }

        void text(int code, String text) throws IOException {
            if (committed) {
                throw new IllegalStateException(
                        "Response already committed");
            }

            byte[] data = text.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.getResponseHeaders().set(
                    "Cache-Control", "no-store");

            // Set true BEFORE attempting to commit so status is not written a second time.
            committed = true;
            exchange.sendResponseHeaders(code, data.length);

            try (OutputStream out = exchange.getResponseBody()) {
                out.write(data);
            }
        }

        void empty(int code) throws IOException {
            if (committed) {
                throw new IllegalStateException(
                        "Response already committed");
            }
            committed = true;
            exchange.sendResponseHeaders(code, -1);
        }
    }

    static void handle(HttpExchange exchange) {
        try (exchange) {
            Reply reply = new Reply(exchange);

            try {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.getResponseHeaders().set(
                            "Allow", "GET");
                    reply.text(405, "method-not-allowed");
                    return;
                }

                String path = exchange.getRequestURI().getPath();
                switch (path) {
                    case "/ok" ->
                            reply.text(200, "ok");

                    case "/bad" ->
                            reply.text(400, "bad-request");

                    case "/empty" ->
                            reply.empty(204);

                    case "/fail" ->
                            throw new IllegalStateException(
                                    "simulated service failure");

                    case "/slow" -> {
                        // Only for testing client timeout.
                        Thread.sleep(1500);
                        reply.text(200, "late");
                    }

                    default ->
                            reply.text(404, "not-found");
                }
            } catch (Exception problem) {
                // Production: safely log problem + request ID.
                // Do not send stack trace / secrets to the client.
                if (problem instanceof InterruptedException) {
                    Thread.currentThread().interrupt();
                }

                if (!reply.committed) {
                    int status =
                            problem instanceof InterruptedException
                                    ? 503 : 500;
                    String message = status == 503
                            ? "unavailable" : "internal-error";

                    try {
                        reply.text(status, message);
                    } catch (IOException sendFailed) {
                        // Socket may already be closed by the client.
                        // Do not attempt to send a response again.
                    }
                }

                // After commit: cleanup/log only, do not change status.
            }
        }
    }

    static String get(
            HttpClient client, URI base, String path) throws Exception {

        HttpRequest request = HttpRequest.newBuilder(
                    base.resolve(path))
                .timeout(Duration.ofSeconds(3))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));

        return response.statusCode() + " " + response.body();
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        ExecutorService pool = Executors.newFixedThreadPool(4);
        server.createContext("/", ExchangeLifecycleDemo::handle);
        server.setExecutor(pool); // Required before start().
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            System.out.println("OK: "
                    + get(client, base, "ok"));
            System.out.println("Bad: "
                    + get(client, base, "bad"));
            System.out.println("Fail: "
                    + get(client, base, "fail"));
            System.out.println("Missing: "
                    + get(client, base, "missing"));

            HttpResponse<String> empty = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("empty")).GET().build(),
                    HttpResponse.BodyHandlers.ofString());

            System.out.println("Empty: " + empty.statusCode()
                    + " body-length=" + empty.body().length());

            HttpResponse<String> method = client.send(
                    HttpRequest.newBuilder(
                            base.resolve("ok"))
                            .POST(HttpRequest.BodyPublishers.noBody())
                            .build(),
                    HttpResponse.BodyHandlers.ofString());

            System.out.println("Method: "
                    + method.statusCode() + " " + method.body());

            try {
                client.send(
                        HttpRequest.newBuilder(base.resolve("slow"))
                                .timeout(Duration.ofMillis(150))
                                .GET()
                                .build(),
                        HttpResponse.BodyHandlers.ofString());

                System.out.println("Timeout: unexpected-success");
            } catch (HttpTimeoutException expected) {
                System.out.println("Timeout: HttpTimeoutException");
            }
        } finally {
            server.stop(0);
            pool.shutdownNow();
            pool.awaitTermination(3, TimeUnit.SECONDS);
        }
    }
}
~~~

Compile/run with **JDK 17+** that includes the `jdk.httpserver` module:

~~~bash
javac -encoding UTF-8 ExchangeLifecycleDemo.java
java ExchangeLifecycleDemo
~~~

If running in an environment with a custom module graph that does not automatically resolve `jdk.httpserver`, add `--add-modules jdk.httpserver` to `javac` and `java`. On a standard JDK 17 installation, the demo program runs without external dependencies.

**Stdout verified directly on JDK 17 with JShell:**

~~~text
OK: 200 ok
Bad: 400 bad-request
Fail: 500 internal-error
Missing: 404 not-found
Empty: 204 body-length=0
Method: 405 method-not-allowed
Timeout: HttpTimeoutException
~~~

### 8.1. Why are these lines right?

1. **`OK: 200 ok`**: the route sends status 200, exact length 2 bytes for `ok`; the stream is closed.
2. **`Bad: 400 bad-request`**: the input data is simulated as invalid; the handler **proactively** sends 400 instead of silently returning.
3. **`Fail: 500 internal-error`**: the exception on route `/fail` is caught before the response starts; the helper sends 500 and a generic message. This is the most important example for **preventing a hanging client just because of a handler exception**.
4. **`Missing: 404 not-found`**: an undefined path still receives a cleanly terminated response.
5. **`Empty: 204 body-length=0`**: uses `sendResponseHeaders(204,-1)`, with no body. This is **no-body**, not an empty chunked stream.
6. **`Method: 405 method-not-allowed`**: POST is rejected and the server sends `Allow: GET`; a response is still sent, not leaving the client waiting forever.
7. **`Timeout: HttpTimeoutException`**: `/slow` intentionally sleeps for 1.5 seconds, while the client only waits 150 ms. The client ends its wait via HTTP request timeout; **no HTTP 408 or 504 code was returned by the server**.

### 8.2. Limitations of the demo to understand clearly

- The `/slow` code intentionally **blocks** a handler thread to illustrate a timeout; **do not** use `Thread.sleep(1500)` as a real service design.
- `HttpRequest.timeout(...)` prevents the client from waiting indefinitely, but **does not guarantee the server task was canceled**. If the server is writing to a database, it may continue even though the client has timed out.
- The demo uses `FixedThreadPool(4)` to illustrate the lifecycle; the default queue of `Executors.newFixedThreadPool` is **unbounded** and can accumulate requests under heavy load. Production needs bounded queues/concurrency and an overload policy.
- The demo only reads the URI/method of GET; endpoints reading large bodies need **byte limits**, deadlines, and safe parsers.
- Once `Reply.text(...)` sets `committed=true` and I/O fails, the handler **does not try to recover by sending a second response**. It closes the exchange; the client may receive an IOException/truncated body.
- The `catch (Exception)` block in the demo is not a full framework exception mapper. Production needs error classification (400/404/409/413/429/500/503), logging/metrics, and must not swallow severe failures.
- Timeout results depend on timing/JDK/network scheduler; the loopback path with a 1.5-second delay and 150 ms deadline passed successfully, but timing output should not be hard-coded for extremely loaded environments without controlling the test clock/scheduling.

## 9. Do not let the server get stuck reading the request body

### 9.1. `Content-Length` is not data you can trust unconditionally

A malicious or buggy client can declare a body larger than the server can handle, send the body slowly, abandon it midway, or never finish. If the handler calls:

~~~java
byte[] body = exchange.getRequestBody().readAllBytes();
~~~

without byte/time limits, the server can consume a large amount of RAM and **wait until the stream ends**. With file uploads or large request bodies, the risk of exhausting the heap is even clearer.

A minimal size limit:

~~~java
static byte[] readSmallBody(InputStream in, int maxBytes)
        throws IOException {
    byte[] data = in.readNBytes(maxBytes + 1);
    if (data.length > maxBytes) {
        throw new RequestTooLargeException();
    }
    return data;
}
~~~

This is an **illustrative snippet**; `RequestTooLargeException` is an application exception you need to define, and `maxBytes` must be validated to avoid overflow/OOM. When the limit is exceeded, return **413 Content Too Large** if not yet committed, then handle closing/draining the connection according to policy. **`readNBytes` only limits the byte count**, it does not enforce a deadline: a sender can send 1 byte/minute. You need to add request read timeouts, proxy policies, and resource quotas at the appropriate layers.

### 9.2. Server reading body until EOF because the client does not close

With standard HTTP requests, framing/chunked/content-length is managed by the parser. However, a client may **send an incomplete body**, causing the handler to wait or I/O to fail. Do not invent a protocol based on "the client will close the TCP socket so I'll know the body ended" when HTTP framing of the request already provides size/termination information.

### 9.3. Returning an error early and keep-alive

If a request has `Content-Length: 1000000000` exceeding the allowed limit, you should not try to read/discard all 1 GB just to reuse the TCP connection. After returning 413 (if possible), you can request closing the connection with `Connection: close` before commit depending on the environment. Per the JDK documentation, closing an exchange without reading the entire body **may prevent the connection from being reused**; this can be an acceptable outcome.

### 9.4. Streaming instead of loading the entire body into RAM

For real uploads, read the body with a bounded buffer and write to a quota-enforced destination; maintain a total byte counter, deadline, checksum if needed, and clean up temporary files on error. Avoid allocating a `byte[]` sized by arbitrary input. For multipart, use a tested parser instead of trying to find boundaries with `String.split(...)` on a binary payload.

## 10. Preventing handlers from being blocked by databases, upstream HTTP, or locks

### 10.1. Every external I/O dependency needs a deadline

A handler can wait on:

- Database connection acquisition/query/transaction.
- An HTTP client calling another API.
- Internal queues, thread pools, locks, or `Future.get()`.
- File I/O/network file shares.
- A user sending a request body very slowly.

Merely closing the exchange in `finally` **does not help execution reach `finally`** if the thread is blocked indefinitely. You must configure **timeouts on the blocking operations themselves**, along with a total request deadline and concurrency limits.

Example when a handler calls an upstream HTTP service using the JDK client:

~~~java
HttpClient upstream = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest req = HttpRequest.newBuilder(upstreamUri)
        .timeout(Duration.ofSeconds(5))
        .GET()
        .build();
~~~

This is **illustrative code**; it requires importing `HttpClient`/`HttpRequest`, `Duration`, `URI`, and defining `upstreamUri`. `connectTimeout` bounds the connection phase, and request timeout bounds the request per the API; you still need an overall processing/response deadline, blocking body controls, and a retry policy.

### 10.2. `CompletableFuture.orTimeout` does not cancel I/O automatically

~~~java
CompletableFuture<String> timed =
        computeAsync()
                .orTimeout(2, TimeUnit.SECONDS);
~~~

This is a fragment with a hypothetical `computeAsync`. On timeout, the future may complete exceptionally with `TimeoutException`, **but the underlying blocking operation may keep running**. Do not leak resources held by the backend or return status 503 while leaving thousands of work items running in the background indefinitely. You need proper cancellation, bounded executors, per-operation timeouts, and observability.

### 10.3. Be careful with `Future.get(timeout)`

~~~java
try {
    return future.get(2, TimeUnit.SECONDS);
} catch (TimeoutException timedOut) {
    future.cancel(true);
    throw timedOut;
}
~~~

This is an **illustrative snippet** inside a method with an appropriate return type; cancellation is only a request to cancel per the task/implementation contract, and does not guarantee that a query or I/O has stopped immediately. If the handler catches the timeout **before commit**, it can send 503 or an appropriate error. If already committed, the HTTP status must not be changed.

### 10.4. Reading the request body and sending the response have different deadlines

- **Header/read timeout:** protects against the time a client takes to send request headers/body.
- **Application deadline:** protects logic depending on DB/API.
- **Response write timeout:** protects against a client reading very slowly; the JDK API does not provide a single high-level "set per-exchange write timeout" switch.
- **Client request timeout:** protects the HTTP caller; does not replace the three server deadlines.

There is no standard `exchange.setTimeout(...)` method in JDK 17 `HttpExchange` that solves every case. Implementation-specific system properties may exist, but **do not treat them as a stable public per-exchange API**; use a reverse proxy, OS, appropriate provider/runtime, and per-dependency timeouts.

## 11. Executor: letting the queue grow too large also makes clients wait

### 11.1. `HttpServer.setExecutor` before `start`

Per JDK 17, call `server.setExecutor(executor)` **before** `server.start()`. If no executor is set, the default implementation uses the thread created by `start()` to run tasks. One long-blocking handler can delay other requests.

Example:

~~~java
ExecutorService pool = Executors.newFixedThreadPool(8);
server.setExecutor(pool);
server.start();
~~~

Illustrative code requiring `ExecutorService`/`Executors` imports. **Do not stop here in production**: `Executors.newFixedThreadPool` has an unbounded work queue by design, so when more requests arrive than can be processed, tasks can wait a very long time and consume a lot of RAM. You need a **bounded queue**, admission control, backpressure/overload responses, and metrics.

### 11.2. A bounded executor needs a clear rejection policy

You can use `ThreadPoolExecutor` with a bounded queue, fixed pool sizing, and an appropriate `RejectedExecutionHandler`. However, rejecting a task at the executor **does not automatically guarantee an HTTP 503 will be sent** if the handler has not been dispatched or the exchange never reaches application code. Test the implementation, reverse proxy, and overload architecture.

Do not pick `CallerRunsPolicy` mechanically if it causes the connection-accepting thread to be occupied by a slow handler. Depending on architecture, backpressure from a reverse proxy, connection limits, and pre-handler load shedding may be necessary.

### 11.3. Shutdown also needs to account for in-flight exchanges

`server.stop(delay)` stops the listener, stops accepting new exchanges, and waits for current handlers to finish within `delay` seconds; afterward, it closes TCP connections. Once `stop` is called, **the server object cannot be restarted**. An executor you created has its own lifecycle and must be shut down / awaited for termination.

The demo uses:

~~~java
finally {
    server.stop(0);
    pool.shutdownNow();
    pool.awaitTermination(3, TimeUnit.SECONDS);
}
~~~

This is a **demo cleanup procedure**, not a safe graceful shutdown pattern for every workload. `stop(0)` can cut off active exchanges; in production, you need draining/deadlines, stopping new requests first, signaling overload if needed, and then releasing worker resources.

### 11.4. Thread interruption is not an HTTP status

If a handler is interrupted while in `Thread.sleep`, Java throws `InterruptedException`. In the example, the callback restores the interrupt flag and attempts to send 503 **if not yet committed and the socket is still usable**. In production, the cause of interruption may be shutdown/cancellation, so avoid creating side effects and clean up resources. Do not try to send 500 after the server has already closed the socket.

## 12. Structuring a response writer so you never forget to close

When you have multiple handlers, use a centralized helper:

- Accepts `status` and bytes (or a streaming source).
- Sets `Content-Type` and headers **before commit**.
- Distinguishes no-body/fixed/chunked.
- Marks `committed` before `sendResponseHeaders`.
- Uses `try-with-resources` when writing output.
- Never produces **two responses** on one exchange.
- Never swallows `IOException` without logging and metrics.

For small known bodies, the simplest approach is usually `getBytes(UTF_8)` followed by a fixed-length send. For large or unknown bodies, chunked allows streaming, but needs deadlines/closing/flow control. For empty responses, `-1` and valid no-body semantics apply.

### 12.1. Avoid nested response writers

A risky pattern:

~~~java
try {
    sendJson(exchange, 200, compute());
} catch (Exception ex) {
    sendJson(exchange, 500, errorObject);
}
~~~

If `sendJson(...,200,...)` **already called `sendResponseHeaders`** and then failed during write, the catch block will try to send 500 a second time and fail. Separate them instead:

~~~text
validate/compute (before commit)
      |
      +-- fail -> send error once
      |
      +-- success -> begin response once
                        |
                        +-- write fail -> cleanup/log only
~~~

If a streamed body is required, sometimes it cannot be fully computed before commit; in that case **do not try to emit a new status** after an error.

### 12.2. Handling errors when serialization throws

For small JSON objects, serialize/validate before committing so that if an error occurs you can still send `500`. Do not write half of the JSON and then call getters/serializers that can throw unexpectedly; the client may receive truncated JSON inside a 200 response.

For large response streams, you can use a message format with checksums/sequences or provide an offset-based resume endpoint per the application contract, rather than claiming "sending 200 means every byte definitely reached the client".

## 13. Filter chains and exceptions before the handler

`HttpServer` supports `Filter` for logging/auth/metrics. If a filter throws an exception **before calling the handler**, the `try(exchange)` inside the handler may **never have executed**. Therefore, response/cleanup policies must be designed for **the entire chain**, not just the body of a single route.

An error-boundary filter can catch uncommitted errors and send a generic response, but it must know whether downstream has already committed. Do not assume a filter knows the exact commit state when multiple components call `sendResponseHeaders` directly. Use a shared response abstraction or standardize error policy in the framework.

Filters can help record elapsed time and `requestId`, but **do not log Authorization, cookies, or entire bodies**. Do not let a logging callback throw a new error that masks the original exception.

## 14. Keep-alive, chunked, and body length: three tightly coupled points

### 14.1. Not reading the entire request body

When a handler returns a response while bytes remain in the request body, the implementation may have to read/discard some of it to keep the TCP connection able to serve the next request. If many unread bytes remain, the connection may not be reused. Do not try to preserve keep-alive by blocking to read an unbounded input.

### 14.2. Not ending a chunked response

With `sendResponseHeaders(status, 0)`, the output stream must be closed to mark **the end of the body**. If a handler returns without closing the stream/exchange, the client may wait for the next chunk or time out. `try (exchange)` helps clean up even when the callback returns.

### 14.3. Fixed Content-Length mismatch

If you declare length N but write fewer than N bytes and close, the JDK may abort the connection; the client may throw an IOException due to premature end of a fixed-length body. This **is not** a new 500 response; status 200 may already be on the wire.

Do not set `Content-Length` manually using `String.length()` or a buffer size, and do not add the header manually while letting `sendResponseHeaders` use a different length. **Encode bytes first, take the byte length from the actual payload**, or use a contract-compliant streaming strategy.

### 14.4. When you truly need to send an empty body

Do not confuse:

~~~java
exchange.sendResponseHeaders(200, 0);  // chunked response, can send 0+ bytes
exchange.sendResponseHeaders(204, -1); // no-body response
~~~

If the API contract requires `200` with an empty body, you can use no-body length `-1` (and appropriate metadata) or a properly terminated chunked transfer, depending on semantics. The key point is **do not pass 0 thinking it finishes by itself without closing the stream**.

## 15. How to measure and diagnose "client waiting forever"

### 15.1. Breaking down request timing

A request should have observable milestones:

~~~text
t0: socket/request accepted
t1: handler dispatched
t2: request body consumed/validated
t3: business work completed
t4: response headers committed
t5: response body finished/closed
t6: exchange closed

queue_wait    = t1 - t0
request_read  = t2 - t1
business_work = t3 - t2
response_send = t5 - t4
total         = t6 - t0
~~~

If you cannot measure `t0` in the application, use timestamps from a reverse proxy or server instrumentation. Distinguish waiting in **executor queue**, **body read**, **service work**, **response write**, and **network/client** instead of just saying "Java HttpServer is slow".

### 15.2. Cause-finding table

| Client-side symptom | Where to check | Remedy |
| --- | --- | --- |
| No HTTP status, client timeout | Handler did not call `sendResponseHeaders` / is blocked | Log entry/exit, deadlines, and bounded dependencies |
| Received 200 but body truncated/EOF | Wrong fixed-length or I/O error after commit | Exact byte length, close, log bytes sent |
| Chunked response never finishes | Response stream not closed | `try-with-resources` and close exchange |
| One slow request stalls all others | Default executor or insufficient concurrency | Configure proper executor, measure queue wait |
| Many requests wait long then time out | Unbounded queue/overload | Bounded queue, admission control, load shedding |
| Large client POST stalls handler | `readAllBytes` / waiting for EOF / slow client | Body size/time limits, quotas, proxy |
| Handler throws, client sees no 500 | No error boundary before commit | Catch/format error response + cleanup |
| Handler tries to send 500 after 200 | Response already committed | Do not retry headers; close/log |
| After a few requests, connection not reused | Request body not fully consumed | Read within limits or intentionally close connection |
| Client times out but DB still writes | Client deadline does not cancel server work | Idempotency/cancellation/transaction policy |
| Shutdown drops responses | `stop(0)` cuts off exchanges | Graceful drain and deadline |
| Response header/metadata wrong | Header set after commit | Set headers before `sendResponseHeaders` |

### 15.3. Log enough to investigate without leaking data

A safe log record can include `requestId`, sanitized method/path, status code (if committed), elapsed time, source error type, bytes intended/sent, and a client-disconnected flag. For pre-commit errors, log the root cause/stack trace on the server. Do not print API keys, cookies, bearer tokens, personal request bodies, or raw queries containing secrets.

Distinguish metrics for **status sent**, **body completed**, **exchange aborted**, and **client timed out**. Do not increment "200 success" just because `sendResponseHeaders(200, N)` returned if the body later broke midway.

## 16. Automated testing of completion and failure paths

Beyond the demo in section 8, in production you should test:

1. **GET success:** receives expected status/headers/body, request completes.
2. **400/404/405:** clear status, finite response body, `Allow` appropriate for 405.
3. **500 before commit:** callback throws `RuntimeException`, client receives generic 500, server logs cause.
4. **Error after commit:** partial write then source fails; verify client sees truncated/IOException per framing and server **does not send a second 500**.
5. **204/HEAD/304:** no body, correct framing, response does not hang.
6. **Chunked:** properly closes output so client receives end-of-body.
7. **Fixed-length mismatch:** test a handler that intentionally writes too few/too many bytes; client must not treat it as a valid body.
8. **Slow request reader/writer:** test server body limits, proxy timeouts, and upload quotas.
9. **Slow application dependency:** DB/API mock blocks then times out; handler has deadline/response or intentional abort.
10. **Executor saturated:** test queue limits and overload policy; no thread/process resource leaks.
11. **Client canceled:** drops connection midway; server cleans up resources and does not loop endlessly trying to send an error.
12. **Shutdown:** multiple in-flight exchanges, drain/stop per policy and metrics.
13. **Keep-alive:** multiple requests on the same TCP connection, verify leftover body does not corrupt subsequent exchanges.

### 16.1. Testing with curl

Since the demo server listens on a random port, the URL changes on every run; you can change it to a suitable fixed port and run:

~~~bash
curl -i http://127.0.0.1:8080/ok
curl -i http://127.0.0.1:8080/bad
curl -i http://127.0.0.1:8080/fail
curl -i -X POST http://127.0.0.1:8080/ok
curl --max-time 1 -i http://127.0.0.1:8080/slow
~~~

The commands above are **illustrative**; only run them if you have actually modified the program to bind port 8080 and keep the server running. With the server code in section 8, the program creates and stops the server on a dynamic port after running the tests, so there is no `localhost:8080` endpoint available for curl to call.

`curl --max-time` limits total time on the client side; a timeout result **does not prove the server canceled its work**. You can check verbose output and server logs to see when headers were sent.

## 17. Scenario exercises and answers

### Exercise A — `return` immediately when a parameter is missing

A handler checks `id` and finds it missing. It returns without calling `sendResponseHeaders`.

**Answer:** wrong. If it can be handled before commit, return `400 Bad Request` (or an appropriate domain error) and close the stream/exchange in `finally`/`try`. `close` does not replace sending a status.

### Exercise B — Unicode byte count

The server sends UTF-8 `"Xin chào"` but declares `responseLength=8` because `String.length()==8`.

**Answer:** wrong; the data is **9 UTF-8 bytes**. You must call `getBytes(StandardCharsets.UTF_8)` and use `bytes.length`. A fixed-length mismatch can abort the exchange.

### Exercise C — Is 0 an empty body?

A handler calls `sendResponseHeaders(200, 0)`, writes nothing, and does not close the stream.

**Answer:** in JDK `HttpExchange`, `0` means chunked transfer coding, and the stream must be closed to terminate the body. If you want **no-body**, use `-1` with the corresponding status semantics; if using chunked, you still must close.

### Exercise D — Error occurs after 200 headers

A handler sends `200` with length 1000, writes 200 bytes, then file I/O fails. The catch block calls `sendResponseHeaders(500,...)`.

**Answer:** you cannot change an already committed status. You must clean up/log and let the stream/connection abort when the fixed-length body cannot be completed; the client may see a truncated body, not a second 500.

### Exercise E — Client expires after 150 ms

A client sends GET to `/slow` with `HttpRequest.timeout(150 ms)`, and the server sleeps for 1.5 seconds. The client receives `HttpTimeoutException`. Did the server return 504?

**Answer:** no. The HTTP client timeout is a **local exception**, not an HTTP status from the server. The server may still be processing the request; stopping backend work requires its own deadline/cancellation mechanism.

### Exercise F — Executor with an unbounded queue

A team uses `newFixedThreadPool(2)`, each handler blocks for 5 seconds, and 100,000 requests arrive in one minute.

**Answer:** even with only 2 threads, the queue can grow huge, making callers wait and consuming RAM. Use a bounded executor/admission control, per-route limits, timeouts, and an overload policy. Test how the system responds/closes connections under overload.

### Exercise G — Unread POST body

A handler sees `Content-Length: 500MB`, sends 413, and closes the exchange. The TCP connection is not reused.

**Answer:** that can be the right tradeoff when rejecting an oversized body; you should not try to read/discard unbounded data just to preserve keep-alive. You need size/time limits, appropriate headers/responses, and proxy behavior testing.

### Exercise H — 204 yet trying to send JSON

A handler uses `sendResponseHeaders(204, -1)` and then writes `{"ok":true}` to the response body.

**Answer:** wrong semantics. 204 has no response body; if you want to return JSON, use a status that allows a body such as 200. With 204, stop at the headers and close the exchange.

### Exercise I — Exception when closing OutputStream

A handler declares fixed length 10 bytes, but writes only 3. `out.close()` throws `IOException`. Should it catch and send 500?

**Answer:** no, because headers are already committed and status cannot be re-sent. Log the partial-write error and clean up; the client may see an aborted connection/incomplete response.

### Exercise J — Database query without a timeout

A handler has `try (exchange)`, but `queryDatabase()` waits forever. Is that enough protection?

**Answer:** no. `try-with-resources` only closes upon **exiting the block**. You need a timeout/deadline for the database and bounded concurrency. When an error happens before commit, return 503/500 per classification; if a response cannot be sent because the connection is lost, clean up/log.

### Exercise K — Trying to "handle" an error by closing the socket immediately

A handler handles 404 by calling `exchange.close()`, without sending 404 headers. Should the client interpret this as a 404 response?

**Answer:** no. There is no 404 status on the wire. The client may see EOF/reset/timeout. Send `sendResponseHeaders(404, length)` + an appropriate body and then close.

### Exercise L — Server stop while a client is downloading

`server.stop(0)` is called while an exchange is still writing a large file.

**Answer:** `stop` may close the connection immediately, causing the client to receive an incomplete body. In production, use an appropriate drain/deadline and have a retry/resume plan for important downloads.

### Exercise M — Error in a filter before the handler

An authentication filter throws `IllegalStateException` before calling `chain.doFilter`; the handler has `try(exchange)` but has not run yet.

**Answer:** the handler's error boundary cannot catch errors before it. Filters must also have a cleanup/response policy or use a shared-layer abstraction/error boundary to avoid leaving the client without a status.

### Exercise N — Writing 1 million logs into the response stream

A handler uses chunked encoding and writes log lines forever. The client uses `BodyHandlers.ofString()` and waits for completion.

**Answer:** if this is an **intentional stream**, the client needs a streaming `BodyHandler`/protocol (e.g., SSE) and cancellation; `ofString()` tries to assemble the full response and may wait forever. If it is not an intentional stream, there must be a stopping point, limits, and output closing.

## 18. Checklist for safe HTTP exchange handling

- [ ] Does every handler **explicitly determine a response status** on success paths and predictable error paths?
- [ ] Do all branches returning before commit send an appropriate 4xx/5xx instead of a silent `return`?
- [ ] Are headers set before `sendResponseHeaders`, and is commit performed **only once**?
- [ ] Do you distinguish `responseLength>0` fixed byte count, `0` chunked, and `-1` no-body?
- [ ] For fixed length, do you compute **UTF-8 byte length** rather than `String.length()`?
- [ ] Is `OutputStream` always closed, even when write/copy/serialization fails?
- [ ] Is `HttpExchange` closed with `try-with-resources` or `finally` on all paths?
- [ ] Do you avoid sending a second response status after already committing?
- [ ] If an error happens after commit, do you log the partial body/abort instead of trying to send 500 again?
- [ ] Does the request body have a max size, time limit, and close/drain policy?
- [ ] Are you aware that an unread request body can prevent TCP keep-alive reuse?
- [ ] Do external I/O dependencies (DB, HTTP, disk, locks) have a deadline/cancel policy?
- [ ] Does the client have a request timeout so it does not wait indefinitely, without treating it as a server status?
- [ ] Is the executor configured before `start`, with bounded queue/concurrency in production?
- [ ] Are appropriate overload responses/policies in place at the proxy and server?
- [ ] Do `server.stop(delay)` and executor shutdown have a proper graceful/forced plan?
- [ ] Do errors from filters/auth/serialization also have an error boundary and cleanup?
- [ ] Do logs capture requestId, status/commit state, bytes intended/sent, latency, and root cause accurately without leaking secrets?
- [ ] Have you tested 200, 400, 404, 405, 413, 500, 503, 204, client timeout, and partial responses?
- [ ] Are you avoiding using this demo HTTP server as a drop-in replacement for the full hardening of a web server framework?

**Conclusion:** With `com.sun.net.httpserver.HttpServer`, preventing clients from waiting forever requires **three distinct disciplines**: (1) on every path a handler can take, **commit an HTTP response exactly once**; (2) write the exact response bytes and **close the stream/exchange** so framing finishes; (3) bound time/resources across body reads, business operations, executor queues, and client waits. `try(exchange)` prevents forgetting to close resources, **but does not send a status automatically**; `sendResponseHeaders(200, 0)` does not mean no-body; errors after commit cannot be turned into 500. Writing code along these boundaries helps distinguish real HTTP errors, network errors, and timeouts, while reducing hung requests and resource leaks.

## 19. Primary references to consult

- **Oracle Java 17 — HttpExchange:** lifecycle, `getRequestBody`/`getResponseBody`, `sendResponseHeaders` (0 = chunked, -1 = no body), `close`. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpExchange.html
- **Oracle Java 17 — HttpServer:** `setExecutor`, `start`, `stop(delay)`, contexts. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- **Oracle Java 17 — HttpHandler:** interface receiving an exchange. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpHandler.html
- **Oracle Java 17 — Headers:** get/set request/response headers. https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/Headers.html
- **Oracle Java 17 — HttpClient and HttpRequest:** request timeout, response handling. https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **RFC 9110 — HTTP Semantics:** HTTP status codes, method semantics, body constraints. https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9112 — HTTP/1.1:** framing, message body length, connections. https://www.rfc-editor.org/rfc/rfc9112

The JDK API documentation defines the exact meaning of `sendResponseHeaders` and `close`; the RFCs explain HTTP semantics on the wire. When deploying in environments with proxies, TLS, many clients, and heavy load, test **server, client, reverse proxy, queues, and backend dependencies** together rather than only observing a handler run to completion once.