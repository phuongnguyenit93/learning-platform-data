# HttpClient, HttpRequest, and HttpResponse in the java.net.http Module

Since Java 11, the JDK has included a **standard HTTP Client API** in the **`java.net.http`** module. Three core types form a clear HTTP flow:

- **`HttpClient`**: configures and executes HTTP/HTTPS connections, reusing resources across multiple calls; can send synchronously or asynchronously.
- **`HttpRequest`**: describes **a single request** including `URI`, HTTP method, headers, timeout, and request body publisher.
- **`HttpResponse<T>`**: the received result, including HTTP status, headers, HTTP version, final URI, and the body processed into type `T`.

Typical example:

~~~java
HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .GET()
        .build();

HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.statusCode());
System.out.println(response.body());
~~~

This is a **snippet**: it requires importing `java.net.URI`, `java.net.http.*`, and handling `IOException`/`InterruptedException`. It needs an Internet connection to a real host, so it is not an offline test. The two complete programs below replace the Internet host with an HTTP server running on **`127.0.0.1`**, and can be compiled/run with Java 17+.

## 1. Why Use java.net.http Instead of Manual Socket Programming?

HTTP sits on top of a transport: HTTP/1.1 typically uses TCP, while HTTP/2 multiplexes multiple HTTP streams over an appropriate connection. With only `Socket` or `SocketChannel`, the application would have to implement logic for methods, request lines, headers, response status, transfer framing, redirects, HTTP versions, TLS, and protocol details itself.

`HttpClient` provides an API at the **HTTP request/response level**, without requiring you to concatenate strings like `"GET / HTTP/1.1\r\n..."` or decode HTTP/2 frames manually.

~~~text
Java Application
       |
       | creates HttpRequest (URI, method, headers, body)
       v
   HttpClient
       |  HTTP/1.1 or HTTP/2
       |  manages connections, redirects/timeouts per configuration
       |  HTTPS/TLS per policy
       v
    Network
       |
       v
    HTTP server
       |
       | status + headers + body
       v
HttpClient + BodyHandler<T>
       |
       v
 HttpResponse<T>
       |
       +--> statusCode(), headers(), version(), uri(), body()
~~~

This model is suitable for calling REST APIs, fetching documents, calling internal services, sending JSON, downloading files, or fanning out multiple HTTP requests. It is **not** an HTTP server API; receiving inbound HTTP requests belongs to a server framework or another server implementation.

The `java.net.http` module was standardized in Java 11 (replacing the incubating HTTP Client in older JDK versions). It also contains WebSocket client APIs, but this article focuses on **HTTP request/response**.

## 2. Three Types Playing Different Roles

| Type / component | What data does it own? | Example methods |
| --- | --- | --- |
| `HttpClient` | Shared configuration: protocol preference, redirect, connect timeout, proxy, authenticator, cookie handler, SSL context, executor | `newHttpClient()`, `newBuilder()`, `send()`, `sendAsync()` |
| `HttpRequest` | A specific request: URI, method, request headers, timeout, body publisher | `newBuilder(uri)`, `GET()`, `POST(...)`, `build()` |
| `HttpRequest.BodyPublisher` | Emits **request** body data as a sequence of bytes | `BodyPublishers.noBody()`, `ofString(...)`, `ofByteArray(...)`, `ofFile(...)` |
| `HttpResponse<T>` | HTTP response metadata and body of type `T` | `statusCode()`, `headers()`, `body()`, `version()` |
| `HttpResponse.BodyHandler<T>` | Decides how to process **response** body data | `BodyHandlers.ofString()`, `ofByteArray()`, `ofInputStream()`, `ofFile(...)` |
| `HttpHeaders` | Response header map, immutable via the public API | `firstValue(name)`, `allValues(name)`, `map()` |
| `CompletableFuture<HttpResponse<T>>` | Result of an asynchronous send operation | `thenApply(...)`, `thenCompose(...)`, `allOf(...)`, `get()` |

**Distinguishing publisher and handler:** `BodyPublisher` is on the **outbound path** (request). `BodyHandler` is on the **inbound path** (response). A client can send a request without a body and still receive a response with a body.

**Immutability:** An `HttpClient` after `build()` is immutable at the configuration level; a built `HttpRequest` is also immutable. Builders are used during configuration, and can then be reused or new builders created as needed. Avoid letting multiple threads mutate a shared builder without synchronization.

## 3. Creating HttpClient: Shared Configuration, Reused Multiple Times

The shortest way:

~~~java
HttpClient client = HttpClient.newHttpClient();
~~~

Pattern with explicit configuration:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .version(HttpClient.Version.HTTP_2)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
~~~

This is a **snippet** (requires imports `java.net.http.HttpClient`, `java.time.Duration`). Meaning:

- `connectTimeout(...)` limits the time to **establish a new connection**, not the total time to download the entire response.
- `version(HTTP_2)` sets the **preferred version** when possible, without forcing the server to support HTTP/2.
- `followRedirects(NORMAL)` allows the client to handle standard redirects according to the API policy; consider redirects to different hosts carefully, especially when requests carry credentials.
- `build()` creates a client that can be reused across multiple requests and multiple threads.
- `HttpClient.newHttpClient()` uses default settings; it is not necessarily the best choice for every system because you may need explicit timeouts, proxy, or redirect policies.

**Notable defaults in Java 17:**
- If no protocol version is requested, the client **prefers HTTP/2** but can fall back to HTTP/1.1.
- If redirect is not configured, the default policy is **`NEVER`**.
- No special cookie handler is configured automatically for all applications; add a `CookieHandler` if you need to store/read cookies according to policy.
- Not setting `connectTimeout` does not mean a request has a business-appropriate deadline; you should also set a request timeout if needed.

**Reusing the client:** Create one `HttpClient` for a group of related requests instead of creating a new one for each request, because the client holds configuration and the opportunity to reuse resources/connections. However, **do not force a single client to be shared across all tenants** if they require different proxy, auth, cookies, or SSL configurations.

**Version detail:** In **Java 17**, `HttpClient` does not have an `AutoCloseable`/`close()` lifecycle like newer APIs; do not write `try (HttpClient client = ...)` and claim that code runs on JDK 17. The two examples below let the client be managed by the runtime and stop the test server; do not assume a `close()` API exists on Java 17.

## 4. Creating HttpRequest: URI, HTTP Method, Headers, Timeout

A GET request:

~~~java
HttpRequest get = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/items?page=1"))
        .timeout(Duration.ofSeconds(10))
        .header("Accept", "application/json")
        .GET()
        .build();
~~~

A POST sending UTF-8:

~~~java
String json = "{\"name\":\"An\",\"active\":true}";

HttpRequest post = HttpRequest.newBuilder(
                URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(10))
        .header("Content-Type", "application/json; charset=utf-8")
        .header("Accept", "application/json")
        .POST(HttpRequest.BodyPublishers.ofString(
                json, StandardCharsets.UTF_8))
        .build();
~~~

Both are **snippets**, using illustrative hostnames and requiring imports `java.net.URI`, `java.net.http.HttpRequest`, `java.time.Duration`, `java.nio.charset.StandardCharsets`. Nothing is sent over the network until the request is passed to `HttpClient.send/sendAsync`.

Some methods:
- `GET()` — request without a body, typically to retrieve a resource.
- `POST(BodyPublisher)` — sends a body to an endpoint, typically to create a resource or perform an action per the API.
- `PUT(BodyPublisher)` — sends a body to update/replace a resource per the HTTP contract.
- `DELETE()` — creates a DELETE request without a body.
- `method("PATCH", publisher)` — uses another method such as PATCH as supported by the protocol/target.
- `header(name, value)` **adds** a header value, whereas `setHeader(name, value)` sets/replaces the value on the builder. Names and values must be valid.

**URI vs. arbitrary URL string:** `URI.create(...)` does not automatically percent-encode user data concatenated into the path or query. When inserting dynamic query parameters, encode them according to context. `URLEncoder` primarily produces `application/x-www-form-urlencoded` format; it should not be used mechanically to assemble an entire URL path. In particular, do not concatenate strings and pass an arbitrary user-supplied host without validating scheme/host/IP to prevent SSRF.

### Request timeout is not the same as connect timeout

`HttpRequest.Builder.timeout(Duration)` sets a deadline for the request. It does **not** replace the client-wide connect timeout, nor does the connect timeout limit response body phases in the way you might expect. Production environments should have both a timeout policy and business-designed retry/backoff.

## 5. BodyPublisher: Outbound Data in the Request

`HttpRequest.BodyPublisher` describes **how to supply bytes** of the request body to the client. Common factories:

| Factory | Use when | Things to watch out for |
| --- | --- | --- |
| `BodyPublishers.noBody()` | Method/request needs no body | Does not mean the response body is also empty |
| `BodyPublishers.ofString(text, UTF_8)` | JSON, form text, plain text | UTF-8 determines bytes; **Content-Type** header should still be set explicitly |
| `BodyPublishers.ofByteArray(bytes)` | Binary payload already in RAM | For large files, avoid loading the entire payload into memory |
| `BodyPublishers.ofFile(path)` | Upload content from a file on disk | File must be readable; consider file changes between retries |
| `BodyPublishers.ofInputStream(supplier)` | Streaming data via InputStream | Supplier should support creating a new stream if replay is needed; manage lifecycle |
| `BodyPublishers.fromPublisher(flowPublisher)` | Integrating into a Java Flow pipeline | Pay attention to backpressure, content length, and repeatability |
| `BodyPublishers.concat(...)` | Combining multiple publishers | Control content/length and semantics on retry |

Text upload example:

~~~java
HttpRequest request = HttpRequest.newBuilder(uri)
        .header("Content-Type", "text/plain; charset=utf-8")
        .POST(HttpRequest.BodyPublishers.ofString(
                "Content", StandardCharsets.UTF_8))
        .build();
~~~

This is a snippet with an existing `uri` variable. **Do not use `String.length()` as the byte length**: Unicode characters can take multiple bytes in UTF-8. The client/publisher manages how body bytes are emitted; do not manually attach `Content-Length` without a reason and unless header rules allow it.

**BodyPublisher is not a JSON serializer**: `ofString(json)` simply converts the exact string you provide into bytes; it does not validate JSON syntax and does not generate a JSON object from a POJO. Use an appropriate JSON library if serialization/deserialization is needed.

## 6. BodyHandler<T>: Inbound Data in the Response

With `client.send(request, handler)`, the handler determines the body type `T` in `HttpResponse<T>`.

| BodyHandler | Response type | When to use |
| --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `HttpResponse<String>` | Moderately sized text body, known charset |
| `BodyHandlers.ofByteArray()` | `HttpResponse<byte[]>` | Small/medium binary payload |
| `BodyHandlers.ofInputStream()` | `HttpResponse<InputStream>` | Want streaming; **must read or close the stream** |
| `BodyHandlers.ofFile(path)` | `HttpResponse<Path>` | Download response to a file; handle file permissions and status |
| `BodyHandlers.discarding()` | `HttpResponse<Void>` | Do not need to keep body, while still processing/discarding response payload |
| `BodyHandlers.ofLines()` | `HttpResponse<Stream<String>>` | Process a stream of lines; must close `Stream` |
| `BodyHandlers.ofPublisher()` | `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` | Reactive streaming and downstream backpressure |

Example:

~~~java
HttpResponse<byte[]> binary =
        client.send(request, HttpResponse.BodyHandlers.ofByteArray());

HttpResponse<String> text =
        client.send(request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

These are two **separate** calls in a snippet; you should not resend a state-changing request just to change the return type. For large responses, `ofByteArray` or `ofString` may force buffering the entire body in RAM; use streaming/file handlers and enforce size limits per policy.

**Special streaming behavior:** `ofInputStream()` can return the response right after receiving headers, **before the entire body is downloaded**. The caller must read to EOF **or close the stream** to release associated resources. With `ofLines()`, you must close the `Stream<String>` per contract. Never leave a response stream "dangling" without consuming/closing it.

**Default BodyHandlers do not inspect HTTP status codes to reject a body**. `BodyHandlers.ofString()` can still read the entire body of an HTTP 404 or 500; to handle by status, check `response.statusCode()` or write a custom handler based on `HttpResponse.ResponseInfo`.

## 7. HttpResponse<T>: Status, Headers, Body, HTTP Version, and URI

After sending a request:

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());

int status = response.statusCode();
HttpHeaders headers = response.headers();
String body = response.body();
HttpClient.Version negotiated = response.version();
URI finalUri = response.uri();
~~~

In the snippet, `HttpHeaders` belongs to `java.net.http`. Key properties:

- `statusCode()`: HTTP code, e.g., 200, 201, 204, 301, 404, 500.
- `headers()`: HTTP response metadata. You can read `firstValue("Content-Type")` or `allValues("Set-Cookie")`. The first value returns `Optional<String>`; a header may be absent.
- `body()`: type `T` determined by the BodyHandler, not necessarily String. With a streaming handler, `body()` may be an unread stream.
- `version()`: **the actual HTTP version used for the response**, not necessarily the preference set when creating the client.
- `uri()`: the URI from which the final response was received, which may differ from the initial request URI if redirected.
- `request()`: the request corresponding to the response; during a redirect this may be the new target request.
- `previousResponse()`: optional intermediate response such as redirect/auth, not always present.
- `sslSession()`: optional TLS session metadata for HTTPS, typically empty for plain HTTP.

### How is 200 different from 404 to HttpClient?

**An HTTP error status is not an IOException by default.** If the server returns a valid `404 Not Found`, `client.send(...)` normally completes and you receive an `HttpResponse<T>` with `statusCode() == 404`. Exceptions only occur when there is a network/protocol error, deadline expiration, TLS failure, or system I/O error.

Therefore, classify it yourself:

~~~java
int code = response.statusCode();
if (code >= 200 && code < 300) {
    // Success per common HTTP status policy.
} else if (code >= 400 && code < 500) {
    // Client error: 400, 401, 403, 404, 429, ...
} else if (code >= 500) {
    // Server error: 500, 502, 503, ...
} else {
    // 1xx, 3xx, or other status depending on flow and redirect policy.
}
~~~

This is a snippet, not a complete HTTP policy. Some 3xx codes may be auto-followed; 204 has no response body; the API requires understanding your specific business semantics. Do not automatically assume every 4xx should be retried.

## 8. Synchronous Sending with HttpClient.send(...)

API:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString(
                StandardCharsets.UTF_8));
~~~

`send(...)` **blocks the calling thread** until the operation completes according to the BodyHandler's semantics. With `ofString`, the body has already been processed into a String before the response returns. With streaming handlers, some body data is still consumed after metadata appears.

Exceptions to know:
- `IOException`: can be caused by DNS/network/TLS/protocol/timeout depending on the error type.
- `InterruptedException`: the waiting thread was interrupted; the HTTP exchange may have already sent the request or may not have been completely canceled on the network.
- `HttpTimeoutException`: request timeout.
- `HttpConnectTimeoutException`: timeout while establishing the connection, a specialized subtype of HTTP timeout.

Pattern for handling interrupts in a business method:

~~~java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException e) {
    Thread.currentThread().interrupt();
    throw e;
}
~~~

This is a snippet placed inside a method returning `HttpResponse<String>` and declaring `throws IOException, InterruptedException`. Restore the interrupt flag when you decide to propagate appropriately; do not swallow the interrupt and keep retrying indefinitely.

**When to use:** Simple and clear for a small number of requests or code running on threads where blocking is acceptable. For many requests that need to overlap, `sendAsync` avoids blocking directly on the send call.

## 9. Example 1 — Java 17+: GET and POST on a Localhost Server

This example creates a small HTTP server in the **same process**, requiring no Internet:

- The test server uses `com.sun.net.httpserver.HttpServer` from the **`jdk.httpserver` module**, distinct from the client module `java.net.http`. This is only a fixture for the practice exercise, not a production HTTP server.
- The server binds to `127.0.0.1` and **port 0**; the OS picks an available port.
- GET `/hello` returns 200 + `"hello"`.
- POST `/echo` reads the request body and returns 201 + `"echo:"` + body.
- The client sets HTTP/1.1 so stdout does not depend on HTTP/2 negotiation; it checks status, body, header, and negotiated version.

Create file **`HttpClientLocalDemo.java`**:

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
import java.nio.charset.StandardCharsets;
import java.time.Duration;

public class HttpClientLocalDemo {
    private static void respond(
            HttpExchange exchange, int status, String text)
            throws IOException {

        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static void hello(HttpExchange exchange)
            throws IOException {
        if (!"GET".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "wrong method");
            return;
        }
        respond(exchange, 200, "hello");
    }

    private static void echo(HttpExchange exchange)
            throws IOException {
        if (!"POST".equals(exchange.getRequestMethod())) {
            respond(exchange, 405, "wrong method");
            return;
        }

        byte[] content = exchange.getRequestBody().readAllBytes();
        respond(exchange, 201, "echo:" + new String(
                content, StandardCharsets.UTF_8));
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/hello", exchange -> {
            try {
                hello(exchange);
            } catch (IOException e) {
                exchange.close();
            }
        });
        server.createContext("/echo", exchange -> {
            try {
                echo(exchange);
            } catch (IOException e) {
                exchange.close();
            }
        });

        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            HttpRequest get = HttpRequest.newBuilder(
                            base.resolve("/hello"))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    get, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("GET status: " + response.statusCode());
            System.out.println("GET body: " + response.body());
            System.out.println("GET Content-Type: "
                    + response.headers()
                    .firstValue("content-type").orElse("-"));
            System.out.println("GET version: " + response.version());

            HttpRequest post = HttpRequest.newBuilder(
                            base.resolve("/echo"))
                    .timeout(Duration.ofSeconds(3))
                    .header("Content-Type", "text/plain; charset=utf-8")
                    .POST(HttpRequest.BodyPublishers.ofString(
                            "greeting", StandardCharsets.UTF_8))
                    .build();

            HttpResponse<String> posted = client.send(
                    post, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));

            System.out.println("POST status: " + posted.statusCode());
            System.out.println("POST body: " + posted.body());
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile/run from the directory containing the file, on **JDK 17+**:

~~~bash
javac -encoding UTF-8 HttpClientLocalDemo.java
java HttpClientLocalDemo
~~~

**Verified stdout on a Java 17-compatible JDK:**

~~~text
GET status: 200
GET body: hello
GET Content-Type: text/plain; charset=utf-8
GET version: HTTP_1_1
POST status: 201
POST body: echo:greeting
~~~

**What happens under the hood:**

1. The server creates a loopback HTTP socket on an ephemeral port; it never touches the Internet.
2. `HttpClient` is built **once** for both GET and POST, with explicit HTTP/1.1.
3. `HttpRequest get` has its own URI and request timeout; `GET()` is a bodyless request.
4. `client.send(get, BodyHandlers.ofString(UTF_8))` converts the HTTP response bytes into `HttpResponse<String>`.
5. `response.statusCode()` = 200, `body()` = `"hello"`, `headers().firstValue(...)` retrieves a potentially missing header, which is set by the server here.
6. POST uses `BodyPublishers.ofString("greeting", UTF_8)` and adds `Content-Type`; the server reads the bytes and responds with HTTP 201.
7. `finally` stops the fixture server via `server.stop(0)`, without calling `HttpClient.close()` (not available on Java 17).

**Example limitation:** The server uses `readAllBytes()` without a request size limit only because it is a localhost fixture completely controlled by the test. Do not apply this pattern to a public server without byte limits, deadlines, and strict method/header handling.

If writing an application with **`module-info.java`** as a named module, declare the module dependencies:

~~~java
module http.training {
    requires java.net.http;
    requires jdk.httpserver; // Only needed for the fixture server in the example.
}
~~~

When compiling a classpath/unnamed-module program with a suitable JDK, you do not need to add `module-info.java`. The actual Client API resides in **`java.net.http`**, while `jdk.httpserver` is only used to spin up the localhost server for the demo.

## 10. Asynchronous Sending with sendAsync and CompletableFuture

API:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofString(
                        StandardCharsets.UTF_8));
~~~

The `sendAsync(...)` call returns a **`CompletableFuture`** representing the result of the HTTP operation. It normally does not block the calling thread when initiating the request; the response completes once sufficient data has arrived according to the BodyHandler.

You can chain transformations:

~~~java
CompletableFuture<String> bodyFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
                .thenApply(HttpResponse::body);
~~~

Or wait for a group of requests:

~~~java
CompletableFuture<?> all =
        CompletableFuture.allOf(firstFuture, secondFuture, thirdFuture);
all.join(); // Only blocks at the point waiting for results.
~~~

The snippets above assume `client`, `request`, and the futures are appropriately declared/imported. `join()` can throw `CompletionException` when a future fails. `get()` can throw `ExecutionException` / `InterruptedException`, or `TimeoutException` if using the overload with a deadline.

**Asynchronous does not mean the application ignores result handling:** a request can fail; do not "fire-and-forget" and lose exceptions, and do not discard futures when business logic requires the response.

**Do not assume completion order equals send order.** If you send three requests concurrently, callbacks receive results based on server/network progress; if you want to print in order, store futures in request order and read results after `allOf`.

## 11. Example 2 — Java 17+: Three Concurrent Requests and Status 404

This program uses a localhost server with endpoint `/item/{id}`:
- `/item/1`, `/item/2`, `/item/3` return bodies `item-1`, `item-2`, `item-3` with HTTP 200.
- `/item/99` returns HTTP **404**, which is still a valid `HttpResponse<String>`.
- The client sends the first three requests using `sendAsync`; waits for the entire group; prints results in creation order, independent of completion order.
- The last request shows that an HTTP error status does not automatically turn into an I/O exception.

Create file **`HttpClientAsyncDemo.java`**:

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
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class HttpClientAsyncDemo {
    private static void respond(
            HttpExchange exchange, int status, String body)
            throws IOException {

        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(status, bytes.length);

        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);

        server.createContext("/item/", exchange -> {
            try {
                String id = exchange.getRequestURI().getPath()
                        .substring("/item/".length());

                if (Arrays.asList("1", "2", "3").contains(id)) {
                    respond(exchange, 200, "item-" + id);
                } else {
                    respond(exchange, 404, "missing");
                }
            } catch (IOException e) {
                exchange.close();
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();

            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            List<CompletableFuture<HttpResponse<String>>> replies =
                    new ArrayList<>();

            for (int id = 1; id <= 3; id++) {
                HttpRequest request = HttpRequest.newBuilder(
                                URI.create("http://127.0.0.1:"
                                        + port + "/item/" + id))
                        .timeout(Duration.ofSeconds(3))
                        .GET()
                        .build();

                replies.add(client.sendAsync(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8)));
            }

            CompletableFuture.allOf(
                    replies.toArray(new CompletableFuture<?>[0]))
                    .get(4, TimeUnit.SECONDS);

            for (int i = 0; i < replies.size(); i++) {
                HttpResponse<String> response = replies.get(i).join();
                System.out.println("Async " + (i + 1) + ": "
                        + response.statusCode() + " " + response.body());
            }

            HttpRequest absent = HttpRequest.newBuilder(
                            URI.create("http://127.0.0.1:"
                                    + port + "/item/99"))
                    .GET()
                    .build();

            HttpResponse<String> missing = client.sendAsync(
                    absent, HttpResponse.BodyHandlers.ofString())
                    .get(3, TimeUnit.SECONDS);

            System.out.println("Missing status: " + missing.statusCode());
            System.out.println("Missing is success: "
                    + (missing.statusCode() >= 200
                    && missing.statusCode() < 300));
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 HttpClientAsyncDemo.java
java HttpClientAsyncDemo
~~~

**Verified output:**

~~~text
Async 1: 200 item-1
Async 2: 200 item-2
Async 3: 200 item-3
Missing status: 404
Missing is success: false
~~~

Explanation:
- All three `sendAsync` calls are **initiated** before waiting on `allOf`, so they can be in-flight together; this does not prove the server processes on three threads or uses HTTP/2 multiplexing (the demo selects HTTP/1.1).
- `allOf(...).get(4, SECONDS)` is the synchronization point so `main` does not exit before the three responses finish.
- The `for` loop reads futures by index, so the output has a deterministic order even though completion timing is not guaranteed.
- The server receives `/item/99` and returns **404**. The client still reads `HttpResponse<String>`, checks `statusCode()`, and computes success per the 2xx rule.
- In practice, `CompletableFuture.allOf` can complete exceptionally if one request/network operation fails; code needs to handle `ExecutionException`/`CompletionException` and clean up related tasks. This simple test covers the success path and HTTP 404.
- The demo picks a random port and does not use the Internet, making it suitable for repeated runs; in sandboxed environments that forbid TCP loopback, you may encounter an I/O exception instead of the stdout above.

## 12. Timeouts and Exceptions: Do Not Confuse HTTP Errors with I/O Failures

There are at least **three distinct classes of situations**:

| Situation | Observed API | Interpretation |
| --- | --- | --- |
| Server returns a valid HTTP 404 or 500 | `response.statusCode()` | Request received an HTTP response; classify per business logic |
| Unable to connect/transmit or TLS handshake error | `IOException` or future completes exceptionally | No successful HTTP response along the normal flow |
| Connect or request exceeds time limit | `HttpConnectTimeoutException` / `HttpTimeoutException` by phase | Timeouts do not prove the server has not processed the request |

Configuration at two levels:

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(7))
        .GET()
        .build();
~~~

`connectTimeout` applies when the client needs to **create a new connection**; if a connection is reused, not every request performs a new TCP connect. `request.timeout` is the request limit per the API; you should not infer that it will always stop all processing on the remote server at the exact deadline.

In an async flow:

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .whenComplete((response, error) -> {
            if (error != null) {
                // Unwrap CompletionException if needed, log appropriately.
            } else {
                // Still need to check response.statusCode().
            }
        });
~~~

This is a snippet; the error callback does not have an `HttpResponse` like the success path. `CompletableFuture.cancel(...)` and future timeouts must not be treated as confirmation that the remote side canceled the request. For state-changing POSTs, retrying after a timeout can cause **duplicate** side effects if the first attempt was already processed by the server.

Common exception classification:
- `UnknownHostException` or `ConnectException` when DNS/connection fails (exact cause depends on OS).
- `SSLHandshakeException` when TLS trust/cipher/identity handshake is invalid.
- `HttpConnectTimeoutException` if creating a new connection exceeds the limit.
- `HttpTimeoutException` if the HTTP request exceeds the configured timeout.
- `InterruptedException` on the `send` path when the waiting thread is interrupted.
- `ExecutionException`/`CompletionException` when calling `get/join` on a failed async future; inspect the root cause.
- HTTP 401/403/404/429/500 are **not by default** Java exceptions.

## 13. HTTP/1.1 and HTTP/2: Preference vs. Negotiated Version

`HttpClient.Version` has at least `HTTP_1_1` and `HTTP_2` in Java 17. Selecting:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
~~~

is only a **preference** when possible. The server, proxy, TLS/ALPN, upgrade capability, and implementation constraints affect the actual version. When HTTP/2 is requested but cannot be used, the Java client can fall back to HTTP/1.1.

Checking:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());

System.out.println(response.version());
~~~

If you need to verify HTTP/2 is active, **read the version from the response** and test against a real endpoint that supports it; do not infer from `client.version()`. HTTP/2 supports multiplexed streams over an appropriate connection, but the client's `sendAsync` API can still be used with HTTP/1.1. Conversely, `send` is a synchronous call on the Java side even if the transport chooses HTTP/2.

In both localhost demos, HTTP/1.1 is used for deterministic results because the `HttpServer` fixture is a simple HTTP server that does not implement HTTP/2. This is a **testing** decision, not a conclusion that Java HttpClient lacks HTTP/2 support.

## 14. Redirects, Cookies, Authentication, Proxy, and HTTPS

Configurations at the **client level**:

~~~java
HttpClient client = HttpClient.newBuilder()
        .followRedirects(HttpClient.Redirect.NORMAL)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
~~~

About redirects:
- `NEVER` does not auto-follow.
- `NORMAL` follows redirects according to API rules, without automatically following HTTPS → HTTP downgrades.
- `ALWAYS` has a broader policy; it should not be enabled by default for code handling sensitive data/credentials.
- If followed, `response.uri()` may differ from the initial request, and `previousResponse()` helps trace intermediate responses.
- Cross-host redirects can alter security boundaries; do not send bearer tokens/cookies to a new host without checking policy.

About cookies:
- A `CookieManager`/`CookieHandler` can be supplied via `HttpClient.Builder.cookieHandler(...)`.
- Do not assume response cookies are stored/resent unless configured appropriately.
- When sharing a client, consider **partitioning cookies** by user/tenant to prevent session leakage.

About credentials:
- Use the client's `Authenticator` when appropriate for authentication challenges; API auth does not mean every kind of token/API key is automatically generated.
- For bearer tokens, the application can set `Authorization: Bearer ...` on each request after managing the token securely.
- Do not hardcode secrets in source code, and do not log raw Authorization headers, Cookies, or bodies containing personal data.
- HTTPS/TLS uses the runtime's trust configuration or a configured `SSLContext`; **never use a trust-all certificate manager** to "fix" TLS errors in production.

About proxies:
- Use `HttpClient.Builder.proxy(ProxySelector)` when a proxy policy is needed.
- Proxies, DNS, and redirects can change where a request actually goes; do not treat the initial URI as sufficient access control when untrusted destinations exist.

## 15. Handling Large Response Bodies, Streaming, and Resources

A common mistake is using `BodyHandlers.ofString()` or `ofByteArray()` for responses that can be very large. That can cause memory pressure/OOM. Choose a handler based on your needs:

~~~java
HttpResponse<java.io.InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (java.io.InputStream in = response.body()) {
    // Read incrementally and limit total bytes per policy.
}
~~~

This is a snippet requiring imports and an already-created `client/request`. With streaming bodies:
- **Read to EOF or close the `InputStream`** if not reading completely.
- Catch `IOException` while consuming the body, not only during the request headers phase.
- Set byte/chunk/time limits on untrusted content.
- If saving to a file, choose a valid path, avoid arbitrary overwrites/remote-supplied paths, and validate content.
- Some BodyHandlers return the response after headers, before the body is fully consumed; the application must manage the streaming lifecycle itself.

For example, `BodyHandlers.ofFile(path)` returns `HttpResponse<Path>` once the body has been written to the file per contract. Do not confuse this response body type with `String`. For text bodies, if the encoding is unknown, check `Content-Type` and application rules before decoding. JSON mostly uses UTF-8, but that does not mean every `text/*` response is UTF-8.

**Backpressure:** In `Flow.Publisher/Subscriber`, consumption rate must be controlled; custom subscribers must not block or allocate unboundedly on critical threads. Only switch to reactive streaming when you truly need it and understand lifecycle, error handling, and cancellation.

## 16. Retries, Idempotency, and Request Body Repeatability

Not every HTTP request can be retried safely.

- `GET` is generally idempotent per HTTP, but backend/external side effects still need consideration.
- `PUT` and `DELETE` have idempotent semantics per HTTP when the server complies.
- `POST` can create resources/modify data; resending can duplicate effects without an idempotency key.
- `429 Too Many Requests` or `503 Service Unavailable` may require backoff and reading `Retry-After` per policy; do not retry indefinitely.
- Timeouts or connection resets do **not** prove the server has not processed the request.
- A `BodyPublisher` reading from a non-rewindable source (one-shot stream) may not be replayable when a request needs retry or authentication/redirect. Use a supplier that creates a fresh stream as appropriate or switch to a repeatable source.

Suggested retry policy:
1. Identify the operation type and business idempotency.
2. Cap the retry count and total deadline.
3. Use backoff with jitter and respect server load.
4. Only retry when the request body is replayable.
5. Track request IDs/idempotency tokens on both sides if double-processing must be avoided.
6. Log safe context (method, sanitized host/path, status, latency, attempt count) without logging secrets.

Do not use an `HttpClient` wrapper that automatically retries all errors in ways you have not verified; when business semantics matter, the application should control retries at a higher layer.

## 17. Security Notes: SSL, SSRF, and URL Validation

An HTTP client can become a risk point if a backend server accepts **user-supplied URLs** and fetches them itself:

- Check the **scheme**: typically only allow `https` (or `http` for controlled local environments).
- Use a host/service **allowlist** when possible; validate the hostname after canonicalization and guard against DNS rebinding and private/loopback/link-local IPs per your security model.
- Do not allow untrusted requests to fetch metadata endpoints/cloud credentials or unauthorized internal services.
- When auto-redirects are enabled, re-validate the **post-redirect destination**; prevent redirecting from a public host to a private endpoint.
- Limit response bytes, timeouts, redirect counts, concurrent requests, and output size.
- Ensure TLS certificate/hostname verification is active; do not disable it when hitting environment errors.
- Do not log URIs containing tokens in query strings or Authorization headers/cookies.
- If using a proxy, evaluate what the proxy can reach and whether it could leak credentials.

**The localhost examples in this article are only for API verification**; in production, use HTTPS, authentication, request/response validation, resource limits, and appropriate outbound network policies. `HttpClient` does not replace a service's authorization logic.

## 18. Performance and Application Design

Decisions that affect efficiency when making frequent HTTP calls:
- **Reuse client:** Avoid creating a new `HttpClient` for each request. Connection reuse reduces overhead in many cases.
- **Bound concurrency:** `sendAsync` allows many in-flight requests, but unbounded initiation can saturate peers, executors, and memory.
- **Keep operations short:** Do not block for long inside future callbacks unintentionally; use a dedicated executor for heavy CPU/DB logic if needed.
- **Choose body handler:** Do not buffer large responses into `String` or `byte[]` when streaming is possible.
- **Timeout policy:** Distinguish connect timeout, request timeout, outer-layer result wait timeout, and overall business deadline.
- **Separate auth contexts:** Do not share cookies/tokens across users or tenants without isolation.
- **Observe metrics:** Method, sanitized host, HTTP status, latency, retries, timeout cause, response size, and negotiated protocol version.
- **Respect interrupts:** With synchronous `send`, do not swallow `InterruptedException` or silently retry a request that already had side effects.

An async API does not make the network physically faster; the benefit is coordinating **multiple pending requests** without blocking the request-initiating thread. HTTP/2 can reduce needed connections in appropriate scenarios, but throughput still depends on the server, bandwidth, flow control, and TLS.

## 19. Common Mistakes

| Mistake | Symptom or consequence | How to fix |
| --- | --- | --- |
| Assuming `HttpClient` holds a fixed URL | Creating unnecessary clients | One client can send many different `HttpRequest`s |
| Assuming `HttpRequest` executes on `build()` | No network call happens | Call `client.send` or `sendAsync` |
| Confusing `BodyPublisher` with `BodyHandler` | Encoding/decoding in the wrong direction | Publisher for request; handler for response |
| Assuming `response.body()` always returns String | ClassCast/logic errors with byte[], Path, InputStream | Choose the matching `HttpResponse<T>` and handler |
| Believing HTTP 404 throws IOException | Ignoring error response body/status | Check `response.statusCode()` |
| Calling `sendAsync` and discarding the future | No visibility into request success/failure | Attach callbacks, collect futures, log, and clean up |
| Assuming `sendAsync` guarantees completion order | Data processed out of order | Attach correlation IDs/read futures in request order |
| Setting `version(HTTP_2)` and assuming response is always HTTP/2 | Wrong protocol diagnosis | Read `response.version()` |
| Not configuring a request timeout | May wait past business deadline | Configure timeouts and retry policy |
| Assuming timeout proves server did not process POST | Retries duplicate side effects | Idempotency token, bounded retries |
| Using `ofString()` for huge bodies | OOM or memory pressure | Streaming/file handler, size limits |
| Not closing `BodyHandlers.ofInputStream()` stream | Resource leaks / connections held open | Read to EOF or close stream |
| Omitting Content-Type for JSON | Server decodes/validates incorrectly | Set appropriate header and encoding |
| Concatenating query/path directly from input | Broken URL or SSRF | Context-aware encoding, URL allowlist |
| Using `try-with-resources` for HttpClient on Java 17 | Fails to compile due to missing AutoCloseable API | Check JDK version; Java 17 only reuses client |
| Using trust-all SSL manager to bypass cert errors | Loss of peer verification, vulnerable to MITM | Use valid trust store/certs |
| Auto-following redirects to hosts outside trust boundary | Credential leakage or SSRF | Validate redirects and auth policy |
| Sending unbounded async requests | Overloads server and client | Semaphore/rate limit/bounded queue |

## 20. Self-Check Questions

**1.** What roles do the three core types of the Java HTTP Client API play?  
**Answer:** `HttpClient` manages configuration/execution, `HttpRequest` describes the request, and `HttpResponse<T>` holds HTTP metadata and the body of type `T`.

**2.** Does `HttpRequest.newBuilder(...).GET().build()` send a network request immediately?  
**Answer:** No. You must call `HttpClient.send` or `sendAsync`.

**3.** How do `BodyPublishers.ofString(...)` and `BodyHandlers.ofString(...)` differ?  
**Answer:** Publisher encodes the request body to send; Handler decodes/creates a String from the response body.

**4.** An HTTP server returns a valid 404. Will `client.send` definitely throw `IOException`?  
**Answer:** No. You will normally receive an `HttpResponse` with `statusCode() == 404`.

**5.** Does `HttpClient.Version.HTTP_2` guarantee receiving an HTTP/2 response?  
**Answer:** No. You must read `response.version()`; the server/proxy/negotiation may result in HTTP/1.1.

**6.** What type does `sendAsync` return, and does it block the caller like `send`?  
**Answer:** It returns `CompletableFuture<HttpResponse<T>>` to handle completion; the send call does not block waiting for the entire response like `send`.

**7.** Does a `Future.get(3, SECONDS)` timeout prove the server has not processed a POST?  
**Answer:** No. Timing out while waiting for the result does not guarantee the remote side canceled the operation; you need an idempotency/retry policy.

**8.** Why should you not use `BodyHandlers.ofByteArray()` for files of unbounded size?  
**Answer:** Because it can buffer the entire file in RAM; choose streaming/file handlers and enforce resource limits.

**9.** With `ofInputStream()`, does receiving `HttpResponse<InputStream>` mean the body has been completely read?  
**Answer:** Not necessarily. You must read until EOF or close the stream.

**10.** What is the default redirect policy of Java 17 `HttpClient`?  
**Answer:** `NEVER` unless configured otherwise.

**11.** Should you create a new client for every GET to the same service?  
**Answer:** Usually no. Reuse the client to share configuration and resources.

**12.** Which module does `com.sun.net.httpserver.HttpServer` used in the localhost tests belong to?  
**Answer:** `jdk.httpserver`, used only as a test HTTP server; the three client types belong to `java.net.http`.

**13.** Why does `Content-Type: application/json` not turn an arbitrary string into valid JSON?  
**Answer:** The header declares the data type; `BodyPublisher` does not automatically serialize or validate JSON.

**14.** If a user-supplied request URL is sent to the backend, what risks exist besides URI syntax errors?  
**Answer:** SSRF, DNS rebinding, accessing internal services, and redirects to untrusted hosts; outbound policies/allowlists and network restrictions are required.

## Official References

- [Java SE 17 — Module java.net.http](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/module-summary.html): module and HTTP client/WebSocket APIs.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): client builder, configuration, send/sendAsync, versions, and thread safety.
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): connectTimeout, redirect, preferred version, proxy, executor.
- [Java SE 17 — HttpRequest](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html): URI, method, headers, and body publisher.
- [Java SE 17 — HttpRequest.BodyPublishers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html): string, bytes, file, streams, Flow publisher.
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): statusCode, headers, body, uri, version, and previousResponse.
- [Java SE 17 — HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): handling string/bytes/file/stream and resource lifecycle.
- [Java SE 17 — HttpHeaders](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html): accessing response headers via Optional and value lists.
- [Java SE 17 — HttpTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html) and [HttpConnectTimeoutException](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html): HTTP timeout types.
- [Java SE 17 — jdk.httpserver module](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): small HTTP server fixture used in the two local programs.