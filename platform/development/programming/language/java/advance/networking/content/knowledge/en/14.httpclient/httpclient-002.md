# Creating a Reusable HttpClient and Sharing Connection Resources (Java 17+)

`java.net.http.HttpClient` is Java's standard HTTP client since Java 11, supporting HTTP/1.1, HTTP/2, and two invocation styles: **synchronous** (`send`) or **asynchronous** (`sendAsync`). To use it effectively, **create an `HttpClient` once for an appropriate configuration/service group, then reuse that instance across multiple requests and multiple threads**, rather than creating `HttpClient.newHttpClient()` on every API call.

A built `HttpClient` is **immutable** and designed for multiple requests. It holds configuration information and shares internal resources of the HTTP exchange process. The implementation typically manages the client's own connection pool so connections can be reused when appropriate. However, **there is no guarantee that every request will use the exact same TCP connection**: the server, proxy, HTTP version, idle timeout, connection health, and implementation policies can all affect it.

This article belongs to **HttpClient** in **Java Advance - networking**, focusing on reuse architecture, connection pooling, scope selection, thread safety, `send`/`sendAsync`, configuration, body lifecycle, overload, timeouts, security, and runnable examples on JDK 17+.

## 1. Three levels not to confuse: client, HTTP request, and TCP connection

```text
Application / service (multiple API calls)
       |
       +---- request A (immutable HttpRequest) -----+
       +---- request B (immutable HttpRequest) -----+----> SHARED HttpClient
       +---- request C (immutable HttpRequest) -----+         |
                                                         | preferred HTTP version
                                                         | proxy / SSLContext / cookies
                                                         | executor / authentication
                                                         v
                                              HTTP transport & connections
                                               /          |           \
                                           socket 1    socket 2     HTTP/2 streams
                                               \          |           /
                                               remote HTTP server / proxy
```

Distinctions:

- **`HttpClient`:** a long-lived component of the application. It holds the client's configuration and provides resource sharing across multiple HTTP exchanges.
- **`HttpRequest`:** a request built from `HttpRequest.Builder`, containing URI, method, headers, timeout, and body publisher if needed. The `HttpRequest` object after `build()` is immutable; creating a new request per operation is usually clearest when data changes.
- **HTTP connection:** a physical transport-layer connection or TCP/TLS session that the implementation may open, keep idle, reuse, or close. **The application must not infer "one client = one socket".**

Multiple requests using one client are **not required** to run on the same connection. With HTTP/1.1, multiple sequential requests can reuse a persistent connection; when concurrent or when the peer closes the socket, the client may have to open multiple connections. With HTTP/2, multiple requests can share one connection using independent streams if HTTP/2 has been negotiated and conditions allow.

## 2. Why should you not create a new client for every request?

A common anti-pattern:

```java
// Example of poor resource management structure:
// the function is called repeatedly, creating a new HttpClient each time.
static String fetch(URI uri) throws Exception {
    HttpClient client = HttpClient.newHttpClient();
    HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
    return client.send(request,
            HttpResponse.BodyHandlers.ofString()).body();
}
```

This is only an illustrative snippet, missing imports/class. Functionally, it can return the right content, but it has drawbacks:

1. **No opportunity to share transport on the same instance:** a new client typically has its own set of connections/internal resources. Each creation may cost TCP setup, TLS, and managing threads/buffers.
2. **Increased cost under high load:** many short-lived clients create many objects and socket lifecycles, reducing the effectiveness of keep-alive and session reuse.
3. **Scattered configuration:** timeouts, proxy, redirect policy, TLS trust, and cookies/authentication easily diverge across calls.
4. **Hard to observe:** there is no consistent "client policy", making it difficult to attach metrics, retry/backpressure, and resource quotas to the service.

**Creating a new client does not necessarily open an extra TCP connection immediately**; connecting also depends on the invocation method and provider. The accurate point is: creating a new client **loses the opportunity to share at the instance level**, whereas reuse aligns with how the API is designed.

## 3. Recommended architectural pattern: one shared instance per appropriate scope

A simple approach:

```java
// Illustrative snippet, placed inside an application/service class.
private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .followRedirects(HttpClient.Redirect.NEVER)
        .build();

String fetch(URI uri) throws Exception {
    HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();
    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString(
                    StandardCharsets.UTF_8));
    return response.body();
}
```

Imports and the enclosing class are omitted, so this is **not a standalone program**. The key point is that `HttpClient` is **initialized when the service is created**, not inside `fetch`. `HttpRequest` is created anew for each specific URI, timeout, and header.

A convenient pattern for dependency injection (illustrative):

```java
final class ProductApi {
    private final HttpClient http;

    ProductApi(HttpClient http) {
        this.http = http;
    }

    // All API-calling methods of ProductApi use this.http.
}
```

The application creates the client in the composition root layer and passes it into services that **share the same proxy/TLS/auth/cookie policy**, instead of calling `newHttpClient()` repeatedly inside domain methods. The service can be tested with a local HTTP server or a dedicated adapter, and centralized configuration helps control timeouts.

## 4. Immutability does not mean all related components are immutable

The Java 17 API confirms `HttpClient` is **immutable after `build()`**, able to serve multiple requests. However:

- **`HttpClient.Builder` is mutable and not thread-safe.** Do not share the same builder and call `version`, `proxy`, or `sslContext` from concurrent threads. Configure it, then `build()`, and share the client.
- **`HttpRequest.Builder` is also a mutable builder**, and should not have headers/URI/body modified concurrently by multiple threads. Create a separate builder for each request.
- **A built `HttpRequest` is immutable**, and can be used as a request configuration. However, the ability to **resend the body** also depends on `BodyPublisher`; a stateful input stream/file/producer cannot necessarily be replayed arbitrarily. For a new GET, creating a new request is usually clearer.
- **`CookieHandler`, `Authenticator`, `Executor`, and custom body publisher/subscriber** that the application passes into the client may carry their own mutable state. An immutable client **does not automatically make every collaborator thread-safe**.
- **`HttpResponse.BodyHandler`** and per-exchange response processing must adhere to the interface and safety of the handler itself; do not share one receiving `InputStream` across multiple requests.
- **Security configuration** may hold references to providers/custom objects; an "immutable client" does not mean the policy of an external credential store automatically rotates when a file on disk changes.

**Rule:** share `HttpClient`, create separate requests; manage mutable components with clear ownership and execution flow.

## 5. Creating the client once: client-level configuration options

Illustrative example of basic configuration:

```java
HttpClient shared = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .version(HttpClient.Version.HTTP_2)
        .followRedirects(HttpClient.Redirect.NORMAL)
        .build();
```

Four notes:

1. `connectTimeout` only controls the time to **establish a new connection**. When an existing connection is reused, this connect limit is not the timeout for the entire request.
2. `version(HTTP_2)` is a **preference/recommendation**, not a promise that every server/proxy supports HTTP/2. Check `response.version()` to know which version that request actually used. The local demos below use `HTTP_1_1` for compatibility with `jdk.httpserver.HttpServer`.
3. `followRedirects` must be designed according to security and the API contract. `Redirect.NEVER` does not automatically follow redirects; `Redirect.NORMAL` allows following certain redirects but does not replace checking target domains, secret headers, and policies.
4. `HttpClient.newHttpClient()` is equivalent to a client built with the default builder. According to Java 17 documentation, the default **prefers HTTP/2**, and the redirect policy is `NEVER`. If different requirements apply, configure them at build time.

Other client-level configurations: `proxy(ProxySelector)`, `authenticator(Authenticator)`, `cookieHandler(CookieHandler)`, `sslContext(SSLContext)`, `sslParameters(SSLParameters)`, and `executor(Executor)`. To avoid session/credential bleed, **do not lump requests from different tenants/principals into a shared client** when collaborators such as a cookie jar, authenticator, or trust policy could cause cross-tenant leakage.

## 6. When must you create multiple HttpClients instead of a JVM-wide singleton?

The goal is not "the entire application has exactly one `HttpClient` object". Scope should be decided by **resource sharing and security policies**:

| Case | Usually reasonable scope | Reason |
| --- | --- | --- |
| A service calling the same group of APIs with the same proxy/TLS/trust and credential boundary | One `HttpClient` for the service/integration | Shares configuration and resources |
| Multiple workers/threads calling the same external API, same policy | Share instance via injection | No need to create per thread or per request |
| An application calling systems requiring different truststores/proxies | Multiple `HttpClient`s per policy | Avoids overly broad trust and conflicting configuration |
| Tenants that must isolate cookies/authorization state | Client or collaborators partitioned per tenant | Avoids session/credential leakage |
| Need to isolate load/resource limits for two very different downstreams | Can separate clients + quotas/bulkhead | Separates failure domains, measurement, and policy |
| One-off CLI or quick experiment | Create one client for the command's lifecycle | No complex DI system needed |

The same client can send requests to multiple origins, but **that does not mean one TCP connection is used across all hostnames/ports/trust contexts**. Connection keying/pooling depends on the implementation, origin, proxy, protocol, TLS, security policy, and network state. Use "one shared client per policy", not "one socket for the whole system".

## 7. HTTP/1.1 keep-alive and HTTP/2 multiplexing

### HTTP/1.1

With persistent connections, the server/client can reuse the same TCP connection for **sequential requests** when the protocol allows. Under high concurrent load, the client may use **multiple TCP connections** to the same origin. Do not infer that all requests share a single socket; nor should you manually set the `Connection: keep-alive` header to force JDK internals. Java's `HttpClient` manages connection lifecycle and certain headers are restricted by the implementation.

Example:

```text
HttpClient A --- request 1 ---> [TCP connection X] ---> api.example
             <--- response 1 ---
             --- request 2 ---> [may reuse X]
             <--- response 2 ---
             --- request 3 ---> [may be X, or Y if X closed]
```

### HTTP/2

HTTP/2 has **multiplexing**: multiple requests/responses are assigned stream IDs and can travel in parallel over the same connection; this saves some overhead and avoids the corresponding limitations of non-multiplexed HTTP/1.1. However:

- The server/proxy must support it; with HTTPS this typically uses TLS/ALPN. The client merely *preferring* HTTP/2 does not guarantee the actual version.
- The server may limit the number of concurrent streams; the client may open or use multiple connections in appropriate situations.
- A single underlying TCP connection can create some interaction between streams during packet loss; HTTP/2 does not eliminate all transport-layer head-of-line issues.
- Do not use `client.version()` as proof of the response's version; read **`response.version()`**.

In both protocols, connection reuse is affected by idle timeouts, server `Connection: close`/GOAWAY, load balancers, proxies, TLS policy, and the OS. **Reusing the client increases the chance of reuse; it is not a guarantee of the number of TCP connections.**

## 8. Java 17+ Example 1: one client sending three sequential requests

The file **`ReuseHttpClientDemo.java`** creates a local HTTP server in the same JVM using the standard JDK module `jdk.httpserver`, binding to `127.0.0.1` and an OS-assigned port. The program builds **one HttpClient** before the loop and uses it to send three GET requests. The server replies `hello-1`, `hello-2`, `hello-3` in turn.

No Internet, public DNS, or API account is needed to run it.

```java
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
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class ReuseHttpClientDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(2);
        AtomicInteger hits = new AtomicInteger();

        server.createContext("/hello", exchange -> {
            try {
                byte[] body = ("hello-" + hits.incrementAndGet())
                        .getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverWorkers);
        server.start();

        try {
            int port = server.getAddress().getPort();
            URI endpoint = URI.create(
                    "http://127.0.0.1:" + port + "/hello");

            // One immutable client configured once and reused.
            HttpClient client = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .followRedirects(HttpClient.Redirect.NEVER)
                    .build();

            List<String> responses = new ArrayList<>();
            for (int i = 0; i < 3; i++) {
                // A new immutable request per operation.
                HttpRequest request = HttpRequest.newBuilder(endpoint)
                        .timeout(Duration.ofSeconds(5))
                        .GET()
                        .build();
                HttpResponse<String> reply = client.send(
                        request,
                        HttpResponse.BodyHandlers.ofString(
                                StandardCharsets.UTF_8));
                if (reply.statusCode() != 200) {
                    throw new IOException("Unexpected status");
                }
                responses.add(reply.body());
            }

            System.out.println("Responses: " + responses);
            System.out.println("Server requests: " + hits.get());
            System.out.println("Client HTTP preference: "
                    + client.version());
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Compile and run on JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 ReuseHttpClientDemo.java
java --add-modules jdk.httpserver ReuseHttpClientDemo
```

Stdout for a completed run:

```text
Responses: [hello-1, hello-2, hello-3]
Server requests: 3
Client HTTP preference: HTTP_1_1
```

**Takeaways from the code:**

1. `HttpClient client` is created only **once**, outside the `for` loop. Each request uses a new `HttpRequest`, with the same URI but its own timeout, to separate lifetime and data changes.
2. `HttpResponse.BodyHandlers.ofString(UTF_8)` consumes the body into a `String`, so all three requests actually complete content exchange. It does not intentionally leave an unread streaming response.
3. `HttpServer` receives 3 requests on loopback; `AtomicInteger` counts requests, not sockets. The output **does not assert that a single TCP connection** was reused.
4. `client.version()` is the **configured preferred HTTP version**, not a verification of each response's version. To check the actual version, you can add logging for `response.version()`.
5. `server.stop(0)` and `serverWorkers.shutdownNow()` clean up the test HTTP server. In Java 17, **`HttpClient` does not have `close()`/does not implement `AutoCloseable`**: do not invent a `client.close()` call or put `HttpClient` in try-with-resources on JDK 17. Other lifecycle APIs may appear in newer JDKs.
6. The successful test proves one client can send multiple requests and the server handles them properly. To confirm **TCP socket reuse**, you need to measure/capture the remote port or separate connection metrics and accept that the network/implementation may change its decision.

## 9. Is reusing HttpClient across multiple threads safe?

**Yes, for a built instance used according to the API.** `HttpClient` is immutable and provides send methods designed to execute multiple requests. A service can have multiple threads/tasks send requests through the same client. This **does not mean the entire program is automatically thread-safe**.

- **Safe:** sharing a `final HttpClient sharedClient` reference across multiple services; each task creates its own `HttpRequest.Builder` and `HttpRequest`, and owns its body and future.
- **Unsafe:** sharing one mutable `HttpRequest.Builder` and having multiple threads call `header`/`uri`/`build` concurrently.
- **Unsafe:** using a custom `CookieStore` or `Authenticator` that does not guarantee concurrency and tenant boundaries; the client's thread-safety does not fix bugs in collaborators.
- **Unsafe:** multiple tasks reading the same response `InputStream`/mutating a stateful request body publisher concurrently without synchronization.
- **Considerations:** choose thread pool size and number of outstanding requests; thread-safe does not mean infinite resources.

Thus, instead of creating a client "per thread", one usually designs **one client per logical integration** and shares it across worker threads. Resource isolation and credentials are the important reasons to create additional instances.

## 10. Synchronous `send` and asynchronous `sendAsync`

| Criterion | `client.send(request, handler)` | `client.sendAsync(request, handler)` |
| --- | --- | --- |
| Invocation | Blocks the calling thread while sending/receiving synchronously | Returns `CompletableFuture<HttpResponse<T>>` to track completion |
| Result | `HttpResponse<T>` or exceptions | Success/failure completion; `join` may wrap errors in `CompletionException` |
| Best suited for | Simple control flow, concurrency bounded by thread count | High concurrent I/O with future composition |
| Client usage | Still shares one client | Still shares that same client |
| Limits | Thread-per-request is bounded by the worker pool | Needs **in-flight request limits** via semaphore/batch/queue |
| Callback | Logic after `send` runs on the caller | `thenApply`/`thenCompose`/`handle` have executor policies; avoid blocking I/O threads |

`sendAsync` **does not mean "automatically limits request count"**. Creating 100,000 futures in a row without controlling outstanding requests can spike memory, sockets, server load, and queues. Custom handlers should not perform heavy CPU/blocking work in callbacks running on an uncontrolled execution context.

`CompletableFuture.allOf` is well suited for waiting on a small batch. For large workloads, you can use a bounded scheduler, semaphore, or reactive backpressure. Concurrency limits must go along with **deadlines, rate limits, retry budgets, and circuit breakers** per SLA, not just thread counts.

## 11. Java 17+ Example 2: one shared client for 12 async requests, capped at 4 in-flight

The file **`SharedHttpClientAsyncDemo.java`** creates a local HTTP server, then **one shared HttpClient** sends 12 GET requests. It splits them into three batches, each with at most **4 outstanding futures**. Each request carries its own `id`; the server replies `id-0` through `id-11`. The client stores responses in **future creation order** so output is deterministic even if the network completes out of order.

```java
import com.sun.net.httpserver.HttpServer;
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
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class SharedHttpClientAsyncDemo {
    private static final int TOTAL = 12;
    private static final int BATCH = 4;

    public static void main(String[] args) throws Exception {
        InetAddress loopback =
                InetAddress.getByAddress(new byte[] {127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService serverWorkers = Executors.newFixedThreadPool(4);
        AtomicInteger hits = new AtomicInteger();

        server.createContext("/item", exchange -> {
            try {
                String query = exchange.getRequestURI().getRawQuery();
                if (query == null || !query.matches("id=[0-9]+")) {
                    exchange.sendResponseHeaders(400, -1);
                    return;
                }
                int id = Integer.parseInt(query.substring(3));
                hits.incrementAndGet();
                byte[] body = ("id-" + id)
                        .getBytes(StandardCharsets.UTF_8);
                exchange.sendResponseHeaders(200, body.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(body);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverWorkers);
        server.start();

        try {
            int port = server.getAddress().getPort();
            HttpClient sharedClient = HttpClient.newBuilder()
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            List<String> bodies = new ArrayList<>();
            boolean allOk = true;

            // At most four outstanding exchanges in each batch.
            for (int start = 0; start < TOTAL; start += BATCH) {
                List<CompletableFuture<HttpResponse<String>>> pending =
                        new ArrayList<>();
                for (int i = start; i < Math.min(TOTAL, start + BATCH);
                     i++) {
                    URI target = URI.create("http://127.0.0.1:"
                            + port + "/item?id=" + i);
                    HttpRequest request = HttpRequest.newBuilder(target)
                            .timeout(Duration.ofSeconds(5))
                            .GET()
                            .build();
                    pending.add(sharedClient.sendAsync(request,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8)));
                }

                CompletableFuture.allOf(
                        pending.toArray(new CompletableFuture<?>[0]))
                        .join();

                // Reading futures in submission order makes output stable.
                for (CompletableFuture<HttpResponse<String>> future
                        : pending) {
                    HttpResponse<String> reply = future.join();
                    allOk &= reply.statusCode() == 200;
                    bodies.add(reply.body());
                }
            }

            boolean ordered = true;
            for (int i = 0; i < TOTAL; i++) {
                ordered &= ("id-" + i).equals(bodies.get(i));
            }
            System.out.println("Responses: " + bodies.size());
            System.out.println("Max submitted per batch: " + BATCH);
            System.out.println("All HTTP 200: " + allOk);
            System.out.println("Bodies match request order: " + ordered);
            System.out.println("Server handled: " + hits.get());
        } finally {
            server.stop(0);
            serverWorkers.shutdownNow();
        }
    }
}
```

Compile and run:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 SharedHttpClientAsyncDemo.java
java --add-modules jdk.httpserver SharedHttpClientAsyncDemo
```

Stdout on completion:

```text
Responses: 12
Max submitted per batch: 4
All HTTP 200: true
Bodies match request order: true
Server handled: 12
```

Explanation:

1. `sharedClient` is built **once** before sending the 12 requests. Every `sendAsync` call uses that exact instance, giving the implementation the opportunity to manage connections.
2. Each request has its own URI, `HttpRequest`, and future, without sharing mutable builders. The server replies `id-i` per query, so you can verify whether responses match each request.
3. `CompletableFuture.allOf(...).join()` ensures the previous batch finishes (or reports an error) before sending the next batch, so there are **at most 4 outstanding requests from the program** in this scenario.
4. `pending` is iterated in submission order, so `bodies` preserves ID order, **which does not prove the network returned them in order**. Asynchronous completions can reorder; the code decouples output ordering from completion order.
5. The server has a 4-thread worker pool, but thread count **is not identical to TCP connection count**. The client may use multiple HTTP/1.1 sockets when sending concurrently.
6. `BodyHandlers.ofString` consumes the response body before the future completes per this handler, reducing the risk of keeping connections busy due to unread responses.
7. If a future fails or times out, `allOf().join()` can throw `CompletionException`; production code should map exceptions, cancel what needs cancelling, and apply a per-request retry policy.

Batching is a **simple form of limiting**, but introduces latency between batches. For continuous traffic, a bounded semaphore/queue can keep at most N in-flight without waiting for the entire batch to finish. Whichever model is used, the important invariant is that **the number of in-flight/processing requests cannot grow unbounded**.

## 12. The response body determines when a connection can be returned to the pool

This is an often-overlooked point when optimizing "reuse HttpClient": **reusing the client does not help much if old exchanges hold onto unreleased bodies or resources**.

Some `BodyHandlers`:

| Handler | When content is available/conditions | Resource consequence |
| --- | --- | --- |
| `BodyHandlers.ofString(...)` | Collects the entire body then creates a `String` | Suitable for small/medium bodies, but large bodies can consume heap |
| `BodyHandlers.ofByteArray()` | Collects the entire body into `byte[]` | Convenient for bounded payloads, do not use indiscriminately for unbounded bodies |
| `BodyHandlers.discarding()` | Receives and discards the body per handler mechanism | Useful when only status/headers are needed; does not keep a stream for the caller |
| `BodyHandlers.ofFile(path)` | Writes the body to a file | Suitable for controlled large content; handle disk/permission errors |
| `BodyHandlers.ofInputStream()` | Returns `InputStream` once headers are ready | **Caller must read fully to EOF or close** to release the exchange |
| `BodyHandlers.ofLines()` | Returns a stream of lines | **Read fully or close** the stream to complete resource release |

With a streaming handler, `HttpResponse<InputStream> response = client.send(..., BodyHandlers.ofInputStream())` **does not mean the response body has been fully read**. Use try-with-resources for the **body stream**:

```java
// Illustrative snippet: client and request already exist.
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    // Read with a maximum size, time limit, and error handling.
    // Or read fully if protocol and capacity allow.
}
```

If the caller closes the stream **before reading to completion**, the implementation may have to **close the underlying HTTP connection**, making it **unreusable**. Reading fully to EOF enables proper resource release but does not guarantee the socket will be reused, because many other conditions apply. Do not try to load a 2 GB response with `ofString` just to keep keep-alive.

## 13. Setting timeouts at the right layer, avoiding "shared client waits forever"

Two easily confused timeout types:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3)) // when a new connection is needed
        .build();

HttpRequest request = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(10))        // deadline for this exchange
        .GET()
        .build();
```

This is an illustrative snippet, not standalone. According to the Java 17 API:

- **`HttpClient.Builder.connectTimeout`** applies when **a new connection needs to be established**; if the request reuses an existing connection, this limit **is not used to time out request processing on that connection**.
- **`HttpRequest.Builder.timeout`** applies to receiving the request's HTTP response per the API contract; when expired it may throw `HttpTimeoutException` or complete the future exceptionally. Business deadline design also needs to consider body streaming after headers arrive.
- **`send`** is a synchronous call that may throw `IOException`, `InterruptedException`. If interrupted, preserve interrupt status/clean up appropriately and do not automatically assume the server has **not** received the request.
- **`sendAsync`** has a future. `future.cancel(true)` is an attempt to cancel the exchange; per the API it **does not guarantee** immediate cancellation before the server processes it. In HTTP/1.1 it may close the connection; HTTP/2 may reset the stream or affect the connection.
- `CompletableFuture.orTimeout` only applies a deadline to the future's completion per its mechanism; it does not turn an already-executed remote write into "never happened" and does not automatically ensure all resources/side effects are reclaimed.

Do not configure timeouts with one value for all integrations without considering latency, SLA, endpoint, request size, and retry policy. A shared client has a **shared connect timeout**, while each request may need its own **request timeout**.

## 14. Retry and idempotency: sharing connections does not replace business logic

If a request fails due to a closed socket during reuse, reset, timeout, or HTTP 503:

- For **idempotent GET**, you can retry per policy and retry budget when appropriate; still consider load/backoff, rate limits, cache consistency, and actual errors.
- For **POST creating an order/payment**, do not automatically retry just because no response was seen: the server may have already processed the transaction and the response was lost. You need an idempotency key and server-supported policy, or verify status before retrying.
- **Do not assume `HttpClient` always retries every request or never retries**; the implementation may have its own behavior for connection errors under certain conditions. Build application rules with proper semantics, not relying on uncontrolled implicit retries.
- **`BodyPublisher` must be replayable** if you intend to resend the body. `BodyPublishers.ofInputStream` with a stateful supplier/stream needs careful examination; do not reuse an already-exhausted stream.
- Retrying may require a **new request** with fresh headers/token/date. Do not keep a mutable builder with an old token or accidentally repeat another tenant's authorization.

Safe takeaway: "the client is reused" is a **transport** matter, while "the request can be retried" is a matter of **HTTP method, idempotency, body publisher, and business contract**.

## 15. Sharing configuration: cookie jar, authenticator, token, and TLS trust

An `HttpClient` can hold a `CookieHandler`, `Authenticator`, `ProxySelector`, and `SSLContext`. Sharing these components has major implications:

- **Cookies/session:** if a shared `CookieHandler` stores shared cookies, requests from different accounts/tenants can mix sessions if not partitioned properly. Do not share a cross-user jar just to save sockets.
- **Authentication:** `Authenticator` may be called when HTTP/proxy requires it; custom implementations and secret state must be thread-safe. A per-request Bearer token is usually passed via `HttpRequest.Builder.header("Authorization", ...)`, not stuffed as a shared mutable token in the client.
- **TLS trust/client certificate:** `sslContext` carries trust policy and local key material. Different truststores, mTLS identities, or security boundaries may need **separate clients per policy**, rather than sharing an overly broad trust context.
- **Proxy:** proxy configuration can change routes and reuse conditions. Do not assert that two requests going through two different proxies will reuse the same TCP socket.
- **Default settings:** Java 17 notes that some system-wide defaults are captured **when building the client**; changing `ProxySelector.setDefault(...)` or `SSLContext.setDefault(...)` afterward **does not automatically update already-built clients**. To change policy, create a new configuration/client during a rotation process.

Focusing on "sharing resources" does not mean "sharing credentials". **Security scope always takes precedence** over minimizing instance count.

## 16. Executor and lifecycle in JDK 17: do not misapply newer-version documentation

`HttpClient.Builder.executor(Executor)` lets you choose an executor for the client's asynchronous/dependent tasks per the API/provider; if not provided, the implementation may use a default executor not directly exposed via `client.executor()`.

**When providing your own executor:**

1. Typically provide it at the service/application layer with clear ownership; **do not** create a separate thread pool inside every request.
2. Do not let heavy/unbounded blocking tasks exhaust the executor so that HTTP callbacks/handlers cannot make progress.
3. Do not `shutdownNow()` the executor while requests/futures still need to run, or you will cut off ongoing processing.
4. On application shutdown, stop accepting new requests, wait for outstanding exchanges per deadline, close streaming bodies, and then release application-owned executors.
5. Do not infer that the custom executor's size is the total number of connections or the total number of internal implementation threads; network I/O and protocol mechanisms may have their own resources.

**Important version constraint:** `java.net.http.HttpClient` in **Java 17** does not implement `AutoCloseable` and **has no public `close()`**. The following **does not compile on Java 17**:

```java
// INVALID ON JAVA 17 — HttpClient is not AutoCloseable.
try (HttpClient client = HttpClient.newHttpClient()) {
    // ...
}
```

Documentation from newer JDKs may describe `HttpClient.close()/shutdown()`, but **do not backport that API into Java 17 articles**. With Java 17, create a long-lived client, complete requests, read/close body streams, and clean up self-managed resources. If a connection-pool draining policy is needed, check provider limitations and application architecture; do not pretend there is a portable `client.close()` on JDK 17.

## 17. Backpressure, resource limits, and rate limiting

A shared client is **not** an automatic traffic controller. For example, 500 threads concurrently calling `client.send` to a small downstream, even with a shared instance, can still cause:

- Too many outstanding exchanges, connections, or HTTP/2 streams.
- Mass timeouts, socket/buffer pressure, and increased memory.
- Saturation of server and downstream thread pools, creating a cascading failure.
- Rate limits 429/503, retry storms, and prolonged latency.

Each integration needs budgets for **concurrent requests**, **requests per second**, **response size**, **timeouts**, and **retries**. Illustrative example:

```text
Shared HttpClient for Billing API
    |
    +-- bounded queue: accept at most 100 waiting requests
    +-- in-flight limit: 20 active requests
    +-- per-request timeout: per billing SLA
    +-- retry budget: only eligible methods/operations
    +-- circuit breaker / bulkhead: when downstream fails
    +-- per-tenant authentication: no credential mixing
```

These are **hypothetical policy numbers**, not Java defaults or recommendations to apply mechanically.

The `SharedHttpClientAsyncDemo` example chose an easy-to-verify approach: **4 outstanding requests per batch**. Production can use a bounded queue or semaphore to fill slots more flexibly. If the queue is full, reject/wait with a specific deadline; do not queue indefinitely just because the client is thread-safe.

## 18. How is connection reuse observed, and what should not be inferred?

In real systems, observe several metrics:

| Metric | Tells you | Does not tell you alone |
| --- | --- | --- |
| `response.version()` | Actual HTTP version of the response | Not the number of open TCP sockets |
| `client.version()` | Preferred version when creating the client | Does not guarantee the server uses that version |
| Server access log with remote IP:port | Same remote TCP source port during an observation window may suggest reuse on that path | Proxy/NAT can change/hide ports; does not certify every request always reuses |
| New TCP connects / TLS handshakes | Cost of opening new connections, session setup | Does not measure application message logic completion |
| Connection counts/idle pools (provider metrics) | Transport utilization per implementation | Not a portable `HttpClient` API across all JDKs |
| p95/p99 latency + throughput | Performance seen from the workload | Cannot isolate all causes without a network trace |
| In-flight requests/queued bytes | Concurrency pressure and backpressure | Not directly a socket count |

A proper benchmark should compare **one shared client** against **client-per-request** on the same server/path, request count, and warmup; measure connections/handshakes/latency/resources with appropriate tools. Do not conclude from a single loopback test that the Internet will always reuse or be faster by a fixed percentage.

Conversely, measuring multiple TCP connections **is not necessarily a bug**: concurrent HTTP/1.1 requests, servers closing idle connections, or load balancers changing routes can all make creating new connections completely normal.

## 19. Common mistakes to avoid

1. **Creating `HttpClient.newHttpClient()` on every request.** Reduces the chance to share configuration and connection resources; create per service.
2. **Using one global client for all tenants regardless of cookies/trust/credentials.** Misplaced optimization, risking session leaks. Scope by security boundary.
3. **Saying "one HttpClient = one TCP socket".** Inaccurate; connection management belongs to the implementation and protocol.
4. **Using `client.version()` to claim requests run over HTTP/2.** That is only a preference; check `response.version()`.
5. **Creating a shared `HttpClient.Builder` and letting multiple threads mutate it.** Builders are not thread-safe; only share the client after building.
6. **Sharing a mutable `HttpRequest.Builder` across tasks.** Headers/URI easily race; create a separate builder for each request.
7. **Using the same `InputStream` body publisher for retries.** The stream may already be consumed; check repeatability.
8. **Not reading/closing a `BodyHandlers.ofInputStream()` body.** Resources are not released properly; connections are hard to reuse.
9. **Reading an unbounded body with `ofString()`.** Holds many bytes in heap; use a bounded stream for protection.
10. **Setting only `connectTimeout` and thinking you have a whole-request timeout.** Request timeout/deadline is a different layer.
11. **Using `sendAsync` and creating unbounded futures.** Uncapped in-flight/queue growth; enforce bounded concurrency.
12. **Running heavy blocking callbacks on the client's executor.** Can stall all exchanges; separate compute executors.
13. **Retrying every POST after timeout without an idempotency key.** Can duplicate side effects already executed by the server.
14. **Using `client.close()` in Java 17.** That API does not exist there; check the real documentation version.
15. **Shutting down a custom executor while async calls are running.** Can cause futures to fail/stall; drain first.
16. **Changing the default SSLContext and thinking an already-built client updates automatically.** Java 17 captures certain defaults when the client is built.
17. **Forcing `Connection: keep-alive` manually to "enable pooling".** Not the API's standard way to control pooling; may be restricted.
18. **Inferring pool size from worker thread count.** Threads, futures, connections, and HTTP/2 streams are different resource types.
19. **Using a shared client while the server sends `Connection: close` and blaming the JDK.** Not every response allows reuse.
20. **Not testing server idle-socket closure/retries after load balancer rotation.** Connections can drop between requests; the application must handle IOException/timeouts appropriately.

## 20. Self-check questions

**Q1:** If 40 threads call the same `HttpClient.send(...)`, is it mandatory to create 40 clients? **No.** One built instance can serve multiple requests. You must ensure external state (builders, cookies, body handlers) is safe and limit load.

**Q2:** After sending 100 GETs through one `HttpClient`, is it guaranteed that only one TCP connection was opened? **No.** That is the transport/provider's decision and depends on HTTP version, server, proxy, and load.

**Q3:** Does `connectTimeout(3s)` cap the entire response time within 3 seconds? **No.** It applies to establishing a new connection; set a separate request timeout.

**Q4:** Can you use `HttpClient` in try-with-resources on Java 17? **No.** The Java 17 version does not implement `AutoCloseable`.

**Q5:** Does `response.version() == HTTP_1_1` on one request mean no other request can be HTTP/2? **No.** The actual version depends on each exchange and negotiation conditions.

**Q6:** When using `BodyHandlers.ofInputStream()`, can you leave the stream unread/unclosed and expect pool reuse? **No.** You must read to completion/close to release the exchange; closing early may prevent socket reuse.

**Q7:** Should thirty internal services with different credentials and cookie jars use one shared singleton client? **Not automatically.** Partition by policy and tenant; creating multiple clients can be appropriate.

**Q8:** Since `sendAsync` returns a `CompletableFuture`, there is no need to limit outstanding requests? **False.** Futures and network resources still consume memory/capacity and require backpressure.

**Q9:** Can an immutable `HttpRequest` be used multiple times for a POST with a one-shot input stream body? **Not by default**; you must ensure the body publisher can recreate the data properly on resend, especially with retries.

**Q10:** If a call times out, is it guaranteed that the server has not processed the request? **No.** Cancellation may arrive late; methods with side effects need an idempotency policy.

## 21. Reusable HttpClient design checklist and conclusion

Before going to production, check:

1. **At which layer is the client created?** Create a sufficiently long-lived instance per service/integration/policy, avoiding creation per operation.
2. **Is `HttpClient.Builder` used sequentially and built once?** Do not use the mutable builder concurrently.
3. **Is request state separated from the shared client?** URI, headers, tokens, timeouts, and body publishers belong in request/call-specific state.
4. **Does sharing respect security boundaries?** Proxy, TLS trust, mTLS identity, cookie handler, authenticator, and tenant isolation must align.
5. **Is connection reuse understood as a conditional optimization?** Do not assume the same TCP socket or HTTP/2 always; check `response.version()` and metrics.
6. **Are response bodies consumed/closed properly?** Especially `ofInputStream`/`ofLines` and unbounded bodies.
7. **Are timeouts set at both connect and request levels?** Do not let threads/futures wait indefinitely when downstream fails.
8. **Is there backpressure/bounded in-flight?** A reusable client does not automatically throttle floods.
9. **Do retries follow HTTP semantics/idempotency?** Avoid duplicate operations on timeout.
10. **Is there a lifecycle/owned-executor policy for Java 17?** Do not use shutdown APIs that do not exist on JDK 17; release app-owned resources.
11. **Are real network reuse and latency observed?** Real metrics are what guide scope and tuning.
12. **Have multi-threaded load, server idle-connection closure, TLS renegotiation/rotation, proxy, malformed/oversized bodies, and shutdown been tested?** Do not test only a single GET.

**Conclusion:** A built `HttpClient` is **immutable and reusable across multiple requests and multiple threads**. Create and share instances according to **the same network/security policy**, use a separate `HttpRequest` per operation, consume/close response bodies properly, and set deadlines and in-flight limits. This enables the implementation to leverage connection pooling/HTTP/2 multiplexing, but **does not promise that one client always corresponds to exactly one socket**. In Java 17 there is no `HttpClient.close()`, so manage lifecycle at the service level and for the executors/body streams owned by the application.

### Official documentation

- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 17 — HttpRequest and HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.html)
- [Java SE 17 — HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html) and [BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [Java SE 17 — BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Java SE 17 — CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html).