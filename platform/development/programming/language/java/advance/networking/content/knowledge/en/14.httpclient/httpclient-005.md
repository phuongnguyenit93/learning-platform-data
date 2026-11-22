# HttpClient connectTimeout and Per-HttpRequest Timeout in Java 17

In the **HttpClient** module of Java Advance — networking, two of the most easily confused configurations are **HttpClient.Builder.connectTimeout(Duration)** and **HttpRequest.Builder.timeout(Duration)**. Both take a positive Duration, but they **control two different scopes**:

- **The client's connectTimeout** sets the time limit for **establishing a new connection needed to send a request**. If the client **reuses an existing connection**, this limit **has no effect** on that request.
- **Each HttpRequest's timeout** limits the time spent waiting for **that request's response**. When it expires per the API contract, `send` throws **HttpTimeoutException**, while `sendAsync` completes exceptionally with the corresponding exception.

**Key takeaway:** a server can accept a connection very quickly yet take many seconds for business processing. In that case, `connectTimeout`—whether set to 100 ms or 10 seconds—**does not replace a request timeout**. Conversely, setting a request timeout that is too short can terminate a request while the connection is still being established or before the server has time to respond. To control **an entire multi-request/retry workflow**, the application also needs an **overall deadline** along with retry, cancellation, idempotency, and observability policies.

This lesson uses the Java 17 **java.net.http.HttpClient** and **HttpRequest** APIs (introduced in Java 11), analyzes Java API behavior, provides runnable loopback examples without depending on the Internet, distinguishes exceptions, covers operational pitfalls, and explains how to design production-ready timeouts.

## 1. Separating the Phases of an HTTP Call

When calling **HttpClient.send(request, bodyHandler)** or **sendAsync(request, bodyHandler)**, the client side may go through several phases:

~~~text
Application creates HttpRequest
        |
        v
HttpClient looks for a suitable connection in the pool
        |
        +-- Reusable connection available -----> use that connection
        |
        +-- New connection needed -------------> DNS / proxy / TCP / TLS*
                                                |
                                                | connectTimeout scoped to
                                                | establishing a new connection
                                                v
                                       usable connection
        |
        v
Send request headers/body
        |
        v
Server receives, queues, and processes business logic
        |
        v
Receive HTTP response headers
        |
        v
BodyHandler / BodySubscriber processes response body
        |
        v
HttpResponse and send / sendAsync result
~~~

The asterisk on **DNS / proxy / TCP / TLS** notes that **the exact steps counted toward connection establishment are not specified identically across every version/provider**. The Java 17 Javadoc only commits to the semantics "underlying connection needs to be established"; do not treat `connectTimeout` as an exact individual deadline for every DNS, TLS, or proxy step. Actual measurements must be done per JDK, network environment, and access method.

**A request timeout has a broader scope than opening a connection:** it is intended to limit the time waiting for a response under the `HttpRequest` contract. However, **do not assume by default that it equals a timeout for the caller's entire processing of every byte stream**, especially when using a `BodyHandler` that returns an `InputStream` or streaming mechanisms: when `HttpResponse` becomes available and when the body is fully read depend on the `BodyHandler` type.

### Quick Comparison Scenarios

| Scenario | HttpClient connectTimeout | HttpRequest.timeout |
|---|---|---|
| TCP connect to remote cannot complete within the limit | May cause **HttpConnectTimeoutException** | May also expire; final error depends on phase and deadline |
| Connection established, server processes slowly | **Does not limit** server processing time | Limits waiting for the request's response |
| HTTP keep-alive reuses a previous connection | **No effect** on requests that do not need a new connection | Still applies to each request that sets it |
| HTTP/2 sends multiple requests on one connection | Does not re-apply a connect deadline for every HTTP/2 stream | Each HttpRequest has its own timeout |
| Response returns quickly | Does not prove connectTimeout was used | No error if the response arrives on time |
| Request does not set a timeout | Does not automatically apply a request timeout | No request limit set by this Builder |
| Client does not set connectTimeout | No explicit connect timeout from the builder | Request can still have a timeout |
| HTTP status 408 or 504 | This is a response from the server/gateway, not Java connectTimeout | Does not automatically become HttpTimeoutException just because status is 408/504 |

**HTTP 408/504 are status codes inside an HttpResponse**, whereas **HttpTimeoutException** is an exception from a client-side timeout policy. A client receiving 504 can still have a normal `HttpResponse` with `statusCode() == 504`; do not assume every 504 is caused by `client.connectTimeout`.

## 2. HttpClient.Builder.connectTimeout(Duration)

The Java SE 17 Javadoc clearly defines **connectTimeout**: if a **new** connection needs to be established and establishment does not complete within the given duration, **HttpClient.send** throws **HttpConnectTimeoutException**; **sendAsync** completes exceptionally with **HttpConnectTimeoutException**. If no new connection is needed—for example, when reusing an existing connection—this timeout **has no effect** on that request.

### Configuring on HttpClient

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();
~~~

This is an illustrative API snippet, assuming **java.net.http.HttpClient** and **java.time.Duration** are imported. **HttpClient** is built from a builder; you should **reuse the same HttpClient** across multiple requests, rather than creating a new one each time, to take advantage of connection pooling and avoid unnecessary resource initialization.

**connectTimeout is a client-level configuration**, not a per-`HttpRequest` property. If two targets have different connect policies, you can use appropriately configured `HttpClient` instances or encapsulate them into a service-layer per-endpoint policy; there is no `HttpRequest.Builder.connectTimeout(...)` in Java 17.

### Checking the Configured Value

~~~java
Optional<Duration> configured = client.connectTimeout();
System.out.println(configured);
~~~

This is a non-standalone snippet, with **java.util.Optional** imported. **HttpClient.connectTimeout() returns Optional<Duration>**. If the builder did not set `connectTimeout`, **Optional.empty()** is valid. Do not conclude "empty means every network call will succeed and wait indefinitely": the OS, proxy, TLS, and other layers can still report errors or terminate waiting for their own reasons.

### Invalid Values

**Duration.ZERO** or a negative `Duration` is not accepted by **connectTimeout(Duration)**: Java throws **IllegalArgumentException**. Do not use `0` to mean "disable limit"; if you want no connect timeout on the builder, **do not call** that method. If configuration comes from env/config, validate it before building the client.

~~~java
HttpClient.newBuilder().connectTimeout(Duration.ofMillis(500));
// Valid: 500 ms.

HttpClient.newBuilder().connectTimeout(Duration.ZERO);
// IllegalArgumentException: must be a positive Duration.
~~~

These are two illustrative API statements, not a complete program.

### Why Keeping a Long-Lived HttpClient Matters

An `HttpClient` can reuse HTTP/1.1 keep-alive connections and HTTP/2 connections. When a request uses an existing connection, **there is no new TCP connect** to apply `connectTimeout` to. Therefore, a "1-second client connect timeout" configuration **does not** protect you from a server holding a request for 30 seconds on an otherwise healthy connection.

A reused connection can also die mid-flight, hit an idle timeout, reset, or pass through a load balancer; in that case, the request may fail or the client may have to establish another connection. **Do not predict** whether every request will be reused or always open a new connection—that is a runtime, protocol, and connection-pool state decision. To control response time **in both cases**, set **timeout on the request**.

## 3. HttpRequest.Builder.timeout(Duration)

The Java 17 Javadoc describes **HttpRequest.Builder.timeout(Duration)** as the timeout for **the request itself**. If the response is not received within the specified duration, **send(...)** throws **HttpTimeoutException**; **sendAsync(...)** completes exceptionally with the corresponding exception.

~~~java
HttpRequest request = HttpRequest.newBuilder()
        .uri(URI.create("https://api.example.com/orders/42"))
        .timeout(Duration.ofSeconds(2))
        .GET()
        .build();
~~~

This is an illustrative API snippet (the domain is not accessed in the runnable demo). It uses **java.net.http.HttpRequest**, **java.net.URI**, and **java.time.Duration**.

**This timeout belongs to HttpRequest and does not change HttpClient's connectTimeout.** Two requests sent with the same `HttpClient` can have different timeouts:

~~~java
HttpRequest quick = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofMillis(800)).GET().build();

HttpRequest report = HttpRequest.newBuilder(uri)
        .timeout(Duration.ofSeconds(15)).GET().build();
~~~

The two lines above assume **uri** is an already-defined `URI`; this is an API illustration rather than a runnable file. A problem may need a short timeout for status lookups and a longer one for generating reports, but specific values **must be measured against actual workload, SLOs, and users**—do not copy these numbers as a system-wide default configuration.

### What Does an Unset Request Timeout Mean?

**HttpRequest.timeout()** returns **Optional<Duration>**. If `builder.timeout` was not called, the `Optional` is empty. According to the Javadoc, not setting a request timeout has the same effect as an infinite `Duration` for waiting on the response, meaning **there is no request time limit at this API level**. However, the request can still terminate due to TCP, DNS, TLS, socket errors, server close, application cancellation, client `connectTimeout` if opening a new connection, or other errors.

Both **Duration.ZERO** and negative `Duration` values cause **IllegalArgumentException**. There is no meaning of "0 ms means return immediately" or "0 means unlimited."

### "Response Received" and Reading the Body

Especially important in Java 17: **HttpClient.send** returns `HttpResponse`, but the `HttpClient` documentation notes that **whether the response body has been fully read depends on the BodyHandler type**.

- **BodyHandlers.ofString():** typically completes once the body has been collected to form a `String`. This is a suitable choice for simple examples of request timeout and slow-responding servers.
- **BodyHandlers.ofByteArray():** also collects the body into a byte array, and size limits must be considered to avoid excessive memory usage.
- **BodyHandlers.ofInputStream():** may return an `HttpResponse` containing an **InputStream that has not been fully consumed**. If subsequent code reads the stream slowly or blocks waiting for data, do not treat the request timeout as a **hard end-to-end deadline that protects your entire processing loop**.
- **BodyHandlers.ofLines(), publishers, or custom subscribers:** body consumption timing, backpressure, and completion semantics depend on the handler type. You must understand the handler's contract and close/cancel resources properly.

Do not claim unconditionally that **HttpRequest.timeout(Duration)** in Java 17 always covers **all bytes of every response body**. The Java 17 specification states the condition as **the response not being received in time**; to protect streaming and downstream processing, add dedicated deadlines/budgets, content limits, cancellation, and proper ownership.

## 4. How Do the Two Timeouts Work Together?

A helpful mental model is to set **connectTimeout less than or equal to a portion of the request budget**, for example 1 second for connect and 4 seconds for the request. This is only a **budgeting guideline**, not an absolute timing formula:

~~~text
Request has a 4-second response wait budget
     |
     +-- new connection needed:
     |       client connectTimeout = 1 second
     |       cannot connect in time -> possible HttpConnectTimeoutException
     |       connect succeeds       -> remaining time for HTTP request/response
     |
     +-- connection reuse:
             connectTimeout skipped
             request timeout still governs response
~~~

Three things to keep in mind:

1. **Do not mechanically add 1 + 4 into a default of 5 seconds.** Request timeout is a configuration of the request; connect is a phase that may occur during the request's lifecycle. Actual elapsed time and the error surfaced are influenced by the provider/phase.
2. If the request timeout is shorter than `connectTimeout` and the connection does not open in time, **do not assume with certainty** that you will always see **HttpConnectTimeoutException** or always see **HttpTimeoutException** at an exact instant; competing policies and network errors can vary.
3. On connection reuse, client `connectTimeout` **is not re-applied**. You still must set a request limit to avoid waiting indefinitely for a slow response.

### Usage Table by Goal

| Your Goal | Primary Configuration | What to Add |
|---|---|---|
| Avoid waiting too long to establish a new connection | HttpClient.Builder.connectTimeout | DNS/proxy/TLS policy, request timeout |
| Avoid waiting too long for an HTTP response | HttpRequest.Builder.timeout | Care with BodyHandler and response body processing |
| Wait on a CompletableFuture in the current thread for at most N seconds | CompletableFuture.get(timeout) | Do not assume the underlying HTTP operation is cancelled |
| Limit an entire chain of multiple HTTP requests | Overall deadline in the service | Allocate remaining budget per request, retry/backoff |
| Limit server load | Server-side timeouts, queues, deadlines | Rate limiting, circuit breaker, backpressure |
| Limit streaming responses or data processing | Streaming deadline, byte limits, close/cancel | Do not rely solely on HttpRequest.timeout |

## 5. Runnable Java 17 Example: fast, slow, send, and sendAsync

To verify that **request timeout differs from connect timeout**, this example starts a small HTTP server right inside the JVM using **com.sun.net.httpserver.HttpServer** from the **jdk.httpserver** module. The server binds to **127.0.0.1 on an ephemeral port**, has no Internet dependency, and exposes two endpoints:

- **/fast:** immediately returns the response body **FAST**.
- **/slow:** waits about **1.2 seconds** before producing the **SLOW** response. A TCP connection to this same server can open very quickly, but the response is intentionally delayed.

The client is configured with **connectTimeout = 2 seconds**, while the **/slow** request is configured with **timeout = 150 ms**. Because the server deliberately withholds the response for `/slow` for 1.2 seconds, both synchronous and asynchronous calls hit the per-request timeout policy under normal lab conditions. The demo prints stable error labels rather than actual port numbers or measured timings.

File **HttpClientTimeoutDemo.java**:

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
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpClientTimeoutDemo {
    private static void respond(HttpExchange exchange, String text)
            throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(3);
        server.setExecutor(pool);

        server.createContext("/fast", exchange -> {
            try {
                respond(exchange, "FAST");
            } finally {
                exchange.close();
            }
        });
        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1200);
                respond(exchange, "SLOW");
            } catch (InterruptedException error) {
                Thread.currentThread().interrupt();
            } catch (IOException ignored) {
                // Client may have closed the exchange when the request timed out.
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI root = URI.create(
                    "http://127.0.0.1:" + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            HttpRequest fast = HttpRequest.newBuilder(
                            root.resolve("/fast"))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();
            HttpResponse<String> ok = client.send(
                    fast, HttpResponse.BodyHandlers.ofString());

            HttpRequest slow = HttpRequest.newBuilder(
                            root.resolve("/slow"))
                    .timeout(Duration.ofMillis(150))
                    .GET().build();

            System.out.println("Connect timeout: "
                    + client.connectTimeout().orElseThrow().toMillis()
                    + " ms");
            System.out.println("Fast response: " + ok.body());

            try {
                client.send(slow, HttpResponse.BodyHandlers.ofString());
                System.out.println("Sync request: unexpectedly completed");
            } catch (HttpTimeoutException timeout) {
                System.out.println("Sync request: timed out");
            }

            try {
                client.sendAsync(slow,
                        HttpResponse.BodyHandlers.ofString()).join();
                System.out.println("Async request: unexpectedly completed");
            } catch (CompletionException error) {
                if (error.getCause() instanceof HttpTimeoutException) {
                    System.out.println("Async request: timed out");
                } else {
                    throw error;
                }
            }

            System.out.println("Per-request timeout: "
                    + slow.timeout().orElseThrow().toMillis() + " ms");
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpClientTimeoutDemo.java
java --add-modules jdk.httpserver HttpClientTimeoutDemo
~~~

Stdout **on a successful run**:

~~~text
Connect timeout: 2000 ms
Fast response: FAST
Sync request: timed out
Async request: timed out
Per-request timeout: 150 ms
~~~

**Compiled with `javac --release 17` and executed on a compatible JDK**, the output matches the five lines above. The server uses the `jdk.httpserver` module included in a full JDK; if a custom `jlink` runtime does not include this module, you must use a JDK/runtime that has the appropriate module or include it when packaging.

### Explanation of Each Key Point

**1. Server uses loopback:** binds to `127.0.0.1` with `port = 0` so no fixed port is chosen. The URI is built from **server.getAddress().getPort()** after `server.start()`. The example makes no external service calls and does not depend on Internet DNS.

**2. Two different endpoints:** `/fast` returns **FAST**; `/slow` intentionally waits **1,200 ms** before sending response headers. The slow metric is unrelated to TCP connect timeout: the server is already listening on the local port, but the application response arrives late.

**3. No proxy:** **HttpClient.Builder.NO_PROXY** prevents routing loopback requests through a machine-configured proxy. It only serves lab stability; production may require an approved proxy.

**4. Client uses a 2,000 ms connectTimeout:** this timeout only applies when `HttpClient` needs to open a connection; it is not a limit for the server processing `/slow`. Because requests may or may not reuse connections depending on the runtime, the example **does not claim** to have precisely measured connection reuse.

**5. /fast sets a 5-second timeout:** deliberately gives the fast request a generous budget to reduce false failures on slow test environments. **HttpResponse.BodyHandlers.ofString()** reads the body into a `String`, so it prints **FAST** once fully received.

**6. /slow sets a 150 ms timeout:** the response is delayed well beyond 150 ms; the **send** call throws an **HttpTimeoutException** (or a subclass if the connect phase also timed out). Catching the parent `HttpTimeoutException` is sufficient for the demo message.

**7. sendAsync does not throw the HTTP timeout directly on the calling thread:** it returns a **CompletableFuture**. When **join()** fails, the exception is wrapped in **CompletionException**, and the program inspects **getCause()** to distinguish the expected timeout error from other errors. Do not catch all exceptions and blindly print "timeout".

**8. Finally cleans up resources:** `server.stop(0)` stops the HTTP server; the executor is **shutdownNow()**. A sleeping handler may be interrupted; if the client already timed out and closed the exchange, the handler may see an `IOException` while sending the response, which the demo catches to clean up properly.

**9. Why does the output not contain a Connection timeout exception?** Because the loopback endpoint in the demo accepts connections quickly; the test's goal is to demonstrate **request timeout when a server responds slowly**, not to simulate an unresponsive TCP SYN.

**10. Output limitations:** this is the expected stdout when the local server is allowed to bind and the scheduler is not abnormally stalled. An extremely slow JVM/machine could encounter unexpected errors; in that case, read the exception rather than treating the program as proof that all timeouts have identical exact schedules.

## 6. Second Java 17 Example: Defaults, Invalid Durations, and Exception Relationship

The next example **sends no network requests**; it only queries API configuration state and checks common errors. Because it does not depend on the Internet or timing, stdout is deterministic.

File **HttpTimeoutDefaultsDemo.java**:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpConnectTimeoutException;
import java.net.http.HttpRequest;
import java.net.http.HttpTimeoutException;
import java.time.Duration;

public class HttpTimeoutDefaultsDemo {
    public static void main(String[] args) {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.invalid/")).GET().build();

        System.out.println("Client timeout configured: "
                + client.connectTimeout().isPresent());
        System.out.println("Request timeout configured: "
                + request.timeout().isPresent());

        try {
            HttpClient.newBuilder().connectTimeout(Duration.ZERO);
        } catch (IllegalArgumentException expected) {
            System.out.println("Zero connect timeout: rejected");
        }

        try {
            HttpRequest.newBuilder(URI.create("https://example.invalid/"))
                    .timeout(Duration.ZERO);
        } catch (IllegalArgumentException expected) {
            System.out.println("Zero request timeout: rejected");
        }

        System.out.println("Connect timeout extends request timeout: "
                + (new HttpConnectTimeoutException("sample")
                   instanceof HttpTimeoutException));
    }
}
~~~

~~~bash
javac --release 17 HttpTimeoutDefaultsDemo.java
java HttpTimeoutDefaultsDemo
~~~

Stdout:

~~~text
Client timeout configured: false
Request timeout configured: false
Zero connect timeout: rejected
Zero request timeout: rejected
Connect timeout extends request timeout: true
~~~

**Compiled with `javac --release 17` and ran successfully.** The URI `example.invalid` is used only as data in `HttpRequest`, **with no send/sendAsync calls**, so the program requires neither network connectivity nor DNS resolution.

Explanation:

- **false** on the first two lines simply means the builder did not set the corresponding timeout. Do not infer a hidden default value such as 30 seconds or 60 seconds.
- **Duration.ZERO** is rejected because both setters require a positive `Duration`.
- **HttpConnectTimeoutException is a subclass of HttpTimeoutException**; this hierarchy dictates the catch order when an application wants to distinguish connect timeouts from response timeouts.
- The two examples help separate **stable API contracts** from **network timing that cannot be perfectly simulated on localhost**.

## 7. Exception Hierarchy: Catch Properly Without Swallowing Errors

In Java 17:

~~~text
Throwable
  |
  Exception
  |
  IOException
  |
  HttpTimeoutException
  |
  HttpConnectTimeoutException
~~~

**HttpConnectTimeoutException extends HttpTimeoutException**, so catching the parent can handle both connect timeouts and response timeouts. If you need separate metrics, catch the subclass first:

~~~java
try {
    HttpResponse<String> result =
            client.send(request, HttpResponse.BodyHandlers.ofString());
    System.out.println(result.statusCode());
} catch (HttpConnectTimeoutException connectionTimedOut) {
    // New connection was not established in time.
} catch (HttpTimeoutException responseTimedOut) {
    // Request timed out waiting for response.
} catch (IOException networkFailure) {
    // DNS/TLS/reset/EOF/other network error.
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    // Respect the application's cancellation/shutdown policy.
}
~~~

**This is an illustrative snippet**, assuming `client` and `request` are already created; the appropriate classes must be imported. If you reverse the catch order and catch `HttpTimeoutException` first, a separate `HttpConnectTimeoutException` catch block afterward will be unreachable at compile time.

### Not Every IOException Is a Timeout

Possible errors you may encounter:

- **ConnectException** when the connection is refused, e.g., no listener on the target port.
- **UnknownHostException** when domain name resolution fails, depending on how the API/OS reports the error.
- **SSLHandshakeException** or certificate errors when TLS/hostname verification fails.
- **IOException** due to reset, socket close, HTTP protocol, or proxy issues.
- **HttpTimeoutException** when a request-level timeout occurs.
- **HttpConnectTimeoutException** when opening a new connection does not complete in time.

**Do not label every connect error as HttpConnectTimeoutException.** A quickly refused connection typically throws a different connection exception, not "waited until connectTimeout expired." Conversely, timeouts at a firewall or network layer can manifest differently depending on timing.

### sendAsync, CompletionException, and ExecutionException

With **sendAsync**, `HttpTimeoutException` can be the cause of a `CompletableFuture` completing exceptionally:

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

try {
    HttpResponse<String> result = future.join();
} catch (CompletionException failure) {
    Throwable cause = failure.getCause();
    // Check cause instanceof HttpConnectTimeoutException
    // before HttpTimeoutException if you want detailed classification.
}
~~~

This is an illustrative snippet with full imports in the calling application. If you use **future.get()** instead of `join`, the failure is typically wrapped in **ExecutionException**. If you use **get(timeout, unit)**, there is also the possibility of **java.util.concurrent.TimeoutException from the get call itself**—which is a *different* timeout from the HTTP exchange's `HttpTimeoutException`.

## 8. Four "Timeouts" Easily Confused in Asynchronous Code

A system can have up to four very similar-looking limits:

| Configuration or Operation | What Does It Limit? | Exception or Signal |
|---|---|---|
| **HttpClient.Builder.connectTimeout** | Opening a new connection | **HttpConnectTimeoutException** from send or exceptional completion |
| **HttpRequest.Builder.timeout** | Waiting for a response for one HttpRequest | **HttpTimeoutException** from send or exceptional completion |
| **CompletableFuture.get(timeout, unit)** | How long the current thread waits on the future | **TimeoutException** from java.util.concurrent |
| **CompletableFuture.orTimeout(timeout, unit)** | Time for the future to be marked complete; completes exceptionally if exceeded | **TimeoutException** in the future chain |

**Pitfall:** `future.get(500, MILLISECONDS)` expiring **does not automatically guarantee the underlying HTTP operation has stopped**. The call only proves the caller waited long enough without a result. Similarly, **orTimeout** can complete the future exceptionally via a scheduler, but should not be treated as a guarantee that the HTTP request never reached the server or that the server has definitely stopped processing.

If you need to stop/release work, design **cancellation**, limit outstanding work, and track lifecycle properly; cancellation is a request to cancel, **not proof that every sent byte has been recalled**. Across different JDK versions of `HttpClient`, the effect of task cancellation on the socket/HTTP exchange can differ; verify against your implementation and tests.

### Illustrative API Example

~~~java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

try {
    HttpResponse<String> response =
            future.get(600, TimeUnit.MILLISECONDS);
} catch (TimeoutException waitingTooLong) {
    future.cancel(true); // Requests cancellation, does NOT prove the server has not processed it.
}
~~~

This snippet is not standalone and the caller must still handle `InterruptedException`/`ExecutionException`. Remember that **TimeUnit.MILLISECONDS** belongs to **java.util.concurrent**, and **TimeoutException** here belongs to **java.util.concurrent**, not `java.net.http.HttpTimeoutException`.

## 9. Connection Reuse and HTTP/2 Can Change Test Results

Some articles state: "set connectTimeout=1 second, run 10 HTTP calls, each call gets 1 second to connect." This is a **misconception**.

### HTTP/1.1 keep-alive

`HttpClient` can use a newly opened connection to send subsequent requests to the same origin, depending on keep-alive and server state. When there is no new connect, **connectTimeout is not applied to the subsequent request**, though the request timeout still applies if configured.

### HTTP/2 multiplexing

HTTP/2 can carry multiple streams over the same connection. A stream that is slow due to server processing does not trigger an independent TCP connect just because that stream started. **connectTimeout does not become a stream timeout**; `HttpRequest`'s own timeout remains the useful constraint.

### Connections Are Not Always Reused

The connection pool may not reuse a connection due to idle timeout, server close, proxy configuration, transport requirements, pool limits, request handling, or errors. Some requests may open a new connection even with the same client. Therefore, **do not test connectTimeout by looking only at the first/second request and declaring a fixed result**. Observe connection events at the appropriate layer and read the provider documentation.

### How to Measure in Practice

Record **connect attempts**, connection establishment latency, request duration, response header latency, active/idle connections if observability allows, HTTP version, proxy hop, status, and exception class. Avoid inferring from a single signal such as "HTTP 200 means connectTimeout isn't working." Tests need to know **which request actually opened a new connection**.

## 10. Overall Deadline for a Multi-HTTP-Request Workflow

Suppose a workflow needs **at most 5 seconds total**, including service discovery, two HTTP requests, and one retry. If request A times out at 4 seconds, then retries A for 4 seconds, and then request B times out at 4 seconds, the entire workflow can far exceed 5 seconds.

**An HttpRequest.timeout only protects that single request**, not the entire business chain. Manage a shared **overall deadline**:

~~~text
totalBudget = 5 seconds
startNanos = System.nanoTime()
deadlineNanos = startNanos + totalBudget

before each HTTP step:
    remaining = deadlineNanos - System.nanoTime()
    if remaining <= 0: stop, fail with "deadline exceeded"
    choose perRequestTimeout <= remaining
    build a request with timeout(perRequestTimeout)

after failure:
    classify error
    if retry allowed and remaining > backoff + safetyMargin:
        backoff with jitter
        retry within the same original deadline
    else:
        stop; report exact outcome/unknown outcome
~~~

This is a conceptual algorithm, not standalone Java. **System.nanoTime()** is suitable for measuring elapsed time; do not use **System.currentTimeMillis()** as a monotonic clock because wall-clock time can be adjusted by NTP or an administrator.

### Converting Remaining Time to Duration

Use a positive `Duration`; do not pass `Duration.ZERO` because `Builder.timeout` will throw `IllegalArgumentException`. If `remaining` is very small or already negative, **stop before creating the request**. When combining with a scheduler, account for buffer time for serialization, queueing, and result processing. Setting a timeout on a request does not guarantee hard real-time response down to the exact nanosecond.

### When connectTimeout Is Larger Than the Overall Deadline

The client has `connectTimeout=10 seconds`, but the entire workflow only has 500 ms remaining. **The request timeout needs a shorter limit**, and the application deadline must protect the remaining path; do not assume a large `connectTimeout` will be cleanly truncated to 500 ms across all providers. For systems with diverse workloads, consider multiple `HttpClient` instances configured appropriately by profile, while avoiding creating a new client per request.

### Redirects, Authentication, Proxies, and TLS

A request can involve multiple hops: proxy, TLS handshake, redirects (if `followRedirects` is enabled), authentication challenges, or a new connection after a redirect. Each hop adds behavior and resource usage; **do not sum multiple connectTimeouts and treat that as the total request deadline**, nor rely on a single `connectTimeout` for an end-to-end deadline. Design with per-request timeouts and a multi-step task deadline.

**DNS and HTTPS do not mean all time falls neatly under one specific timeout.** Exactly which phase is constrained in a given provider/JDK version is a detail to verify. In particular, **SSLHandshakeException** errors cannot be "fixed" by disabling hostname/trust verification to avoid timeouts.

## 11. Retrying on Timeout: The Server May Have Already Processed It

An HTTP timeout **does not prove** the server never received the request or never executed side effects.

Example of a POST order-creation command:

~~~text
Client POST /orders (idempotency key = 7e1)
      |
      v
Server creates order successfully
      |
      X Response 201 lost / arrives after deadline
      |
Client sees HttpTimeoutException
      |
If retrying POST with a new business ID:
    may create a second order!
~~~

**Only retry an operation when you clearly understand business safety and transport policy.**

- **GET** typically has idempotent semantics; retrying may be appropriate if the request has no side effects and load permits.
- **PUT** is generally designed to be idempotent by HTTP method, though you still need to check the service's actual behavior.
- **POST** can produce side effects; if you want to retry, use a server-supported **idempotency key**, store results by key, and handle duplicates consistently.
- **HttpConnectTimeoutException** can occur when a connection was not established in time, but you still need to consider retry policy, network, and proxy; do not design business logic on the assumption that an exception subclass always proves the server saw zero bytes in every case.
- Retrying repeatedly without backoff can worsen overload. Use **bounded retries**, exponential backoff, jitter, rate limits, circuit breakers, and an overall deadline.

### Do Not Reset the Entire Deadline After Each Attempt

Suppose 1 second remains for the entire transaction. If backoff used 700 ms, the next attempt only has about 300 ms left—do not open a new 5-second request timeout and make the caller wait longer. To do this right, compute `remaining` from **a single starting timestamp**, rather than resetting the deadline from scratch after each retry.

### Data to Log on Timeout

Log **request ID**, appropriately masked method/host/path, **attempt number**, client `connectTimeout`, per-request timeout, deadline remaining, actual duration, HTTP version (if a response arrived), exception class, and root cause. Do not log `Authorization` headers, cookies, tokens, private data, or full sensitive response bodies. When a timeout occurs, correlate with server traces to determine whether the server **received the request / committed side effects / sent a response**.

## 12. Streaming Responses and Operations After send Completes

With **BodyHandlers.ofInputStream()**, the API can hand back an **HttpResponse<InputStream>** before the body is fully read. If the application reads the stream for 30 minutes, **HttpRequest.timeout must not be misunderstood as guaranteeing that all stream reading stops after 2 seconds**. Users need to:

1. **Close the InputStream** after reading or when no longer needed, avoiding holding connections and resources.
2. **Cap the maximum number of bytes** received and processed; an oversized response can fill memory or disk.
3. Have a **separate deadline for the stream consumption step**, with appropriate API/transport cancellation and closing.
4. With backpressure, do not hold request/response body subscribers indefinitely.
5. Distinguish **when response headers arrive** from **when the business payload is complete and validated**.
6. When callbacks/parsers take many seconds, a network timeout does not automatically bound CPU/business logic.

Similarly, an HTTP 200 with an incomplete response body, invalid JSON, or truncated content can still cause application errors **after** the transport has received headers. Business deadlines must include parsing, validation, DB commits, and other steps where required.

**Do not conflate "response received" with "valid business outcome."** `HttpRequest` timeout is a transport tool; business deadlines and data correctness are determined by the application.

## 13. Testing Properly: What Is Deterministic vs. Network-Dependent?

**Testing request timeouts** is relatively easy to make deterministic: a local server deliberately delays its response after receiving the request, such as **/slow** in `HttpClientTimeoutDemo`. This avoids relying on external hosts and distinguishes "TCP connection opened" from "response arrived late."

**Testing connect timeouts** is harder to make deterministic: it requires a new endpoint where connection establishment **actually hangs/stalls**, rather than a port with no listener (which usually returns connection refused very quickly) or a nonexistent DNS address (which may return `UnknownHostException`). Firewalls, proxies, VPNs, dual-stack IPv4/IPv6, and OS routing determine the outcome.

Do not promise that "calling 192.0.2.1 always throws HttpConnectTimeoutException in 1 second." Documentation-reserved addresses, network policies, or firewalls can route/reject differently, and the result is not guaranteed. If you need to test connect timeouts in a real system, use an **approved network emulator**, lab firewall rules, or fault injection with TCP observation, and record the OS/JDK/proxy/version.

### Testing Matrix

| Test | Expectation to Verify | Do Not Infer |
|---|---|---|
| Local /fast returns body immediately | HTTP 200, body FAST | How much connect timeout was "consumed" |
| Local /slow returns after > request timeout | Request's HttpTimeoutException | Server did not process the request |
| Calling sendAsync to /slow | Future completes exceptionally, cause is timeout | Exception is necessarily thrown directly on sendAsync call |
| Configuring Duration.ZERO | IllegalArgumentException | 0 means wait forever |
| Creating client without calling connectTimeout | Optional.empty() | No more network/OS timeout errors |
| Creating request without calling timeout | Optional.empty() | Every request will wait forever regardless of other errors |
| Connection refused quickly | Usually ConnectException or another IOException | Must be HttpConnectTimeoutException |
| Proxy returns HTTP 504 | HttpResponse statusCode() == 504 if response received normally | Always throws client-side HttpTimeoutException |
| Reused connection, server processes slowly | Request timeout is the needed limit | connectTimeout will be re-applied per request |
| Using Future.get(timeout) | TimeoutException only limits the waiting thread | Underlying HTTP exchange was definitely cancelled |
| Streaming InputStream | Body must be properly closed/handled by consumer | HttpRequest timeout is a deadline for all stream processing |

### Real-World Measurement and Latency Percentiles

To choose appropriate timeouts, collect at least **p50/p95/p99** request latencies, separating **connection establishment** and **time to response** if tracing allows; monitor **connect failures**, request timeouts, exception causes, active requests, reused connection ratio, retry rate, and server saturation. Avoid setting a timeout lower than p99 just to make the UI feel fast if doing so causes retry storms and slows down the system.

Timeout settings for **downstream dependencies** must also align with **upstream deadlines**. If the frontend expires at 3 seconds while the backend waits 30 seconds on the DB, the system can keep doing wasted work after the caller has given up. Coordinate propagated deadlines where libraries/protocols support them, and manage cancellation explicitly.

## 14. Common Coding Mistakes

### Mistake 1 — Setting only connectTimeout, without request timeout

~~~java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(1))
        .build();

HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
~~~

This is illustrative code. **request.timeout() is empty**: if the server accepts the connection but takes a very long time to process, connect timeout cannot solve it. Set `request.timeout` for requests that need a response limit.

### Mistake 2 — Setting only request timeout and assuming every DNS/TLS step is guaranteed to exact wall-clock timing

This is also over-inference. `HttpRequest.timeout` is an API-level response constraint, but it **does not by itself replace full DNS, proxy, TLS handshake, streaming, or application CPU/DB policies**, nor does it turn HTTP into hard real-time. When an overall SLA is required, use an overall deadline and verify provider behavior.

### Mistake 3 — Using Duration.ZERO as "no timeout"

Both Builder setters require a **positive** `Duration`. To leave that configuration level unset, omit the setter; if 0 wait time is needed, do not send a new request—handle the expired-deadline condition beforehand.

### Mistake 4 — Catching HttpTimeoutException before HttpConnectTimeoutException

When you need to distinguish the two, catch the **subclass first**; if you do not need to classify them, a single `catch (HttpTimeoutException)` covers both.

### Mistake 5 — Creating a new HttpClient for every HTTP request

Doing so prevents connection reuse and increases overhead. `HttpClient` can be reused across many requests and is immutable after building. Do not share and mutate a single builder concurrently from multiple threads.

### Mistake 6 — Treating a timeout as a business guarantee that "the server didn't process it"

A request timeout can arrive **after the server has already committed** but before the response reaches the client. For payments, orders, emails, and job creation, retries must have idempotency or reconciliation.

### Mistake 7 — Ignoring errors in CompletableFuture

~~~java
client.sendAsync(request, HttpResponse.BodyHandlers.ofString())
      .thenAccept(response -> System.out.println(response.statusCode()));
~~~

This example **lacks error handling** and is not standalone code. If the request times out, the stage completes exceptionally and the success logic never runs; you must add appropriate **whenComplete/exceptionally/handle**, logging, and cleanup. Do not let the caller assume the request finished just because `sendAsync` returns a `CompletableFuture` immediately.

### Mistake 8 — Using an overly short timeout on your own requests

A request's budget must accommodate network jitter, scheduling, TLS/connection setup, queueing, and server processing time within contract. Taking a number like "150 ms" from a lab exercise and applying it to an Internet API typically causes false failures and retry storms.

### Mistake 9 — Confusing HTTP status 408/504 with Java exceptions

Check **response.statusCode()** when an `HttpResponse` is present. For network timeout errors with no response, handle the exception. Gateway 504 metrics and client-side `HttpTimeoutException` measure two different events.

### Mistake 10 — Forgetting to close streams and cancel excess downloads

With **BodyHandlers.ofInputStream**, if you do not read/close it, the socket/stream can hold resources. Set byte limits and manage body consumption lifecycle; timing out a `Future` does not replace proper cleanup.

## 15. Practice Exercises

### Exercise A — Change one setting, observe the right phenomenon

In **HttpClientTimeoutDemo**, change `client.connectTimeout` from 2 seconds to 5 seconds while keeping `/slow` timeout at 150 ms. Predict what happens to `/slow` and explain why increasing connect timeout does not fix a slow server response.

### Exercise B — Change per-request timeout

Set `/slow` timeout = 2 seconds while the server sleeps 1.2 seconds. On a healthy loopback environment, the request can complete and return **SLOW**. Do not write tests asserting exact millisecond timing; assert status/body and use tolerance when measuring duration.

### Exercise C — Synchronous and asynchronous

Run both **send** and **sendAsync** against `/slow` 150 ms. Compare **catch HttpTimeoutException** in `send` with **CompletionException.getCause()** in `join`, and try a **future.get()** version to observe **ExecutionException**.

### Exercise D — Defaults and config validation

Run **HttpTimeoutDefaultsDemo**, then try a negative `Duration`. Record `Optional.empty` and `IllegalArgumentException`; explain why a client without a connect timeout can still encounter network exceptions.

### Exercise E — Distinguish connect failure from connect timeout

Create an HTTP URI pointing to a local port with no listener in the lab. Identify the actual exception; why can you not conclude from a "Connection refused" that `HttpClient.connectTimeout` expired? Do not assume all OSes produce the exact same error.

### Exercise F — Request timeout and HTTP 504

Modify the local HTTP server to return **HTTP 504** immediately with body `"Gateway Timeout"`. Keep the client request timeout long enough. Assert that you receive an `HttpResponse` with **statusCode() == 504**, rather than Java throwing `HttpTimeoutException`. Distinguish gateway timeout from client timeout.

### Exercise G — Overall deadline for three requests

Suppose a workflow has a 3-second total budget across A, B, and C. Use `System.nanoTime` to compute `remaining` before each call, build `HttpRequest.timeout` with a positive `Duration` not exceeding the budget, subtract backoff time, and stop when the budget is exhausted. Explain why giving each request a 3-second timeout does not create a 3-second overall deadline.

### Exercise H — Retry and idempotency

Design `POST /orders` with an idempotency key and server-side response cache, simulating the server committing successfully while the response is delayed past the request timeout. After retrying with the same key, only one order is created. If keys are not supported, return an **unknown outcome** status and reconcile instead of blindly retrying.

### Exercise I — Streaming response

Test `BodyHandlers.ofInputStream` with a server that sends headers and then streams data very slowly. Observe when `HttpResponse` is returned and how long reading the `InputStream` takes compared to the request timeout. Set a streaming deadline and ensure closing on error paths as well. Do not rely on a single JDK version to conclude the semantics of all `BodyHandlers`.

### Exercise J — Reused connections

Send multiple GET requests to the same origin using **one** `HttpClient`, recording server-side connection identity/remote port and duration. Compare HTTP/1.1 vs. HTTP/2 and server keep-alive. Explain why you cannot count requests and equate that to connection count; analyze `connectTimeout` in both new-connection and reuse cases.

## 16. Self-Check Knowledge Questions

**1. Does connectTimeout apply to every request or only when a new connection is needed?** Per the Java 17 Javadoc, it takes effect when establishing a **new connection**; reused connections are not subject to that `connectTimeout`.

**2. A server accepted the TCP connection but waits 20 seconds on the database; which timeout matters?** `HttpRequest.Builder.timeout` for waiting on the response, plus an overall deadline where needed.

**3. Can two HttpRequests using the same HttpClient have different timeouts?** Yes. Each request configures its own `Duration`.

**4. What do HttpClient.connectTimeout() and HttpRequest.timeout() return?** `Optional<Duration>`, empty if the corresponding timeout was not configured.

**5. Does Duration.ZERO mean unlimited?** No. Both setters throw `IllegalArgumentException` for non-positive `Duration` values.

**6. Is HttpConnectTimeoutException a subtype of HttpTimeoutException?** Yes, it is a subclass. Catch the subclass first if classifying them.

**7. Does an expired sendAsync throw HttpTimeoutException immediately at the call site?** Not necessarily; the `CompletableFuture` completes exceptionally, and the caller sees the cause via `get`/`join` or a callback.

**8. Does future.get(2, SECONDS) timing out mean the request was definitely cancelled?** No. Only the caller stopped waiting; the operation may continue unless cancellation is handled per policy.

**9. Is HTTP 504 synonymous with HttpTimeoutException?** No. 504 can be a valid HTTP response returned by a gateway.

**10. Why can HttpRequest.timeout not be claimed as a timeout for all stream-reading operations after receiving HttpResponse?** Because a `BodyHandler` can return a streaming object before the body is fully consumed, and reading/closing/cancelling responsibility lies with the consumer.

**11. Is a 300 ms connectTimeout enough to keep an API call under 300 ms?** No. The server can take a long time to process on an already-open connection; request timeout and an overall deadline address the rest.

**12. When a POST request times out, should you immediately retry with a new request ID?** Do not assume so. The server may have already committed; an idempotency key or reconciliation is required.

**13. Does Java HttpClient automatically retry all timeouts?** Do not assume a generic business retry policy. Actively control attempt counts, backoff, deadlines, and safety conditions; check implementation behavior when needed.

**14. Why is testing connect timeout using a port with no listener usually wrong?** Because the OS can reject the connection immediately, without waiting for the connect timeout duration to elapse.

**15. Are DNS/TLS/redirects/proxies always bounded precisely by Java 17's connectTimeout?** Do not assert that unconditionally; the API describes the scope of establishing a new connection, details of other steps must be verified per provider/JDK, and an overall deadline should be used if needed.

## Official Java SE 17 Documentation

- **HttpClient.Builder — connectTimeout:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html
- **HttpRequest.Builder — timeout:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- **HttpClient — send/sendAsync, response results, and BodyHandler:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **HttpResponse.BodyHandlers — ofString/ofInputStream and body handling types:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- **HttpTimeoutException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- **HttpConnectTimeoutException:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpConnectTimeoutException.html
- **Duration:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Duration.html

**Remember:** **HttpClient.Builder.connectTimeout** limits the time to establish a **new connection** and **does not** address slow responses on reused connections. **HttpRequest.Builder.timeout** sets a **per-request response wait limit** and leads to **HttpTimeoutException** if exceeded. In Java 17, **HttpConnectTimeoutException is a subclass of HttpTimeoutException**; `sendAsync` reports errors through `CompletableFuture`. When a workflow involves multiple requests, streaming, retries, or side effects, add an **overall deadline, cancellation/cleanup, backoff, idempotency, and monitoring**; do not assume a single timeout covers every network layer and application processing step.