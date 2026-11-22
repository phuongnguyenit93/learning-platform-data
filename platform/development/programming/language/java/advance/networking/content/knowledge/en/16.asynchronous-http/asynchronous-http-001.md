# sendAsync Returns a CompletableFuture and Represents an In-Flight HTTP Exchange

## 1. Learning Objectives

Java `java.net.http.HttpClient` supports sending HTTP requests synchronously with `send(...)` or asynchronously with **`sendAsync(...)`**. What makes `sendAsync` special is that it **immediately returns a `CompletableFuture<HttpResponse<T>>`** representing the result of an **in-flight HTTP exchange** (sending the request and receiving the response), rather than making the calling thread wait for the response to finish before returning.

This is not an object “just for printing the result later”: `CompletableFuture` is a **representation of a future result** that can complete normally with an `HttpResponse<T>`, or complete exceptionally when sending/receiving fails or is cancelled. It is also the mechanism for declaring subsequent steps using methods such as `thenApply`, `thenCompose`, `thenAccept`, `whenComplete`, `exceptionally`, and `allOf`.

After this lesson, you should be able to:
1. Write the `sendAsync` signature correctly and understand that the type parameter `T` comes from `HttpResponse.BodyHandler<T>`.
2. Explain the difference between **having started the HTTP exchange**, **the response being ready according to the BodyHandler**, and **the entire body having been consumed by the application**.
3. Understand that the future may **not yet be completed** when `sendAsync` returns; do not infer its state from the call timing.
4. Use callback/chaining APIs to process the status/body **without blocking the caller thread**.
5. Distinguish HTTP 404/500 (normal HTTP responses) from I/O/timeout/SSL errors that cause the future to complete exceptionally.
6. Combine multiple requests, coordinate sequential dependencies, and apply controlled deadlines and cancellation.
7. Run two Java 17+ programs with a **loopback** server, verifying the in-flight state and the streaming body case.
8. Avoid production pitfalls: calling `join()` too early, blocking the event loop/UI, resource leaks when streaming, retrying side effects, and running heavy callbacks on an inappropriate thread.

## 2. Synchronous `send` and Asynchronous `sendAsync`

Two important signatures in Java 17:

```java
<T> HttpResponse<T> send(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler)
        throws IOException, InterruptedException;

<T> CompletableFuture<HttpResponse<T>> sendAsync(
        HttpRequest request,
        HttpResponse.BodyHandler<T> responseBodyHandler);
```

These are **abbreviated API signatures** for learning, not a standalone Java program; the actual methods belong to `HttpClient` and have the appropriate modifiers/generics. `sendAsync` also has an overload that accepts a `PushPromiseHandler<T>` when the application handles HTTP/2 server push.

Comparison:

| Aspect | `send(...)` | `sendAsync(...)` |
| --- | --- | --- |
| Direct result | `HttpResponse<T>` | `CompletableFuture<HttpResponse<T>>` |
| Caller thread | Waits until the method has a response according to the handler or throws an error | Receives the future early and can continue other work |
| Common network errors | `IOException`/interruption as declared | The future usually completes exceptionally; some parameter errors may still be thrown directly |
| Composing steps | Sequential code | Chaining `thenApply`/`thenCompose`/`handle`... |
| Active waiting | Calling `send` is a blocking operation | Can call `join()/get()`, but doing so blocks at the wait point |
| Large/streaming bodies | `BodyHandler<T>` decides when the response is returned | **`BodyHandler<T>` also decides** when the future completes |

**Asynchronous does not mean the HTTP request runs “faster” or that network latency disappears.** It changes **how the program schedules waiting time**, allowing the caller to do other work while I/O is in progress.

## 3. CompletableFuture Describes an HTTP Exchange

Conceptual view:

```text
Application thread                     HttpClient / network
       │                                      │
       ├── client.sendAsync(request, handler) ►│
       │                                      │
       ◄── CompletableFuture<Response<T>> ───┤
       │    (may still be PENDING)            │
       │                                      ├─ DNS/connect if needed
       ├── continues other processing         ├─ TLS handshake if HTTPS
       │                                      ├─ sends request (possibly streaming)
       │                                      ├─ receives status and headers
       │                                      ├─ selects BodySubscriber per handler
       │                                      ├─ receives/consumes body per handler
       │                                      │
       │     future completes ◄──────────────┤
       │     normally or exceptionally        │
       ▼                                      │
  callback/thenApply ...                      │
```

This is a **logical** diagram; it does not claim one thread per step or that every request must open a new TCP connection. `HttpClient` may reuse connections, use HTTP/2 multiplexing, authentication, and redirects depending on configuration.

Points to distinguish:

- **Returned future:** an object representing the result. It may be incomplete, completed very quickly, or in the process of completing; there is no guarantee that it will always remain pending for a positive amount of time before completing.
- **`future.isDone()`:** returns true if the future has completed normally, exceptionally, or been cancelled. It does **not** indicate the percentage of bytes downloaded.
- **`future.isCompletedExceptionally()`:** true if the future completed exceptionally, including cancellation per the API.
- **`future.isCancelled()`:** true when the future is marked as cancelled.
- **`future.join()`/`get()`:** retrieves the result when the future finishes or **waits** if it is not yet finished; calling them immediately after `sendAsync` can negate the benefits of asynchrony.

Therefore, to preserve the asynchronous model, describe what needs to happen **after** the response is ready using callbacks/stages, rather than immediately blocking on the current request-handling thread.

## 4. T Is the Body Type, Not the “HTTP Packet Type”

`sendAsync` is generic:

```java
CompletableFuture<HttpResponse<String>> f1 =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<byte[]>> f2 =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofByteArray());

CompletableFuture<HttpResponse<Void>> f3 =
        client.sendAsync(request, HttpResponse.BodyHandlers.discarding());
```

These lines are **code snippets**, assuming `client` and `request` have already been created, with imports `java.net.http.*` and `java.util.concurrent.CompletableFuture`.

`HttpResponse.BodyHandler<T>` determines **how body bytes are processed**, for example decoding a `String`, storing a `byte[]`, writing to a file, returning an `InputStream`, or discarding the content. It does not merely change the Java generic type; it also affects **when the future response is considered ready to be returned to the application**.

| Handler | `T` | When is the response/future typically ready? |
| --- | --- | --- |
| `BodyHandlers.ofString()` | `String` | After the body has been fully received and decoded into a string |
| `BodyHandlers.ofByteArray()` | `byte[]` | After all body bytes have been received |
| `BodyHandlers.ofFile(path)` | `Path` | When the body has been completely written to the file per the handler |
| `BodyHandlers.discarding()` | `Void` | When the handler has received and discarded the body |
| `BodyHandlers.ofInputStream()` | `InputStream` | **After response headers have been sufficiently received; the body may still be arriving** |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | The response may be ready after headers; data will continue via the publisher/subscription |
| `BodyHandlers.ofLines()` | `Stream<String>` | The response may be ready before the body has been fully received/read |

The statement “a completed future means the entire response body has finished downloading” is only true **for handlers whose completion is tied to collecting the full body**, such as `ofString`/`ofByteArray`. It is **not generally true** for `ofInputStream` or `ofPublisher`.

A successfully created response **does not automatically confirm that the application has finished reading or closed** a streaming body. With `InputStream`, you must read until EOF or close the stream so that the HTTP exchange resources can be properly released.

## 5. Creating Client and Request Before sendAsync

Minimal example:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3))
        .build();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://api.example.com/items"))
        .timeout(Duration.ofSeconds(8))
        .header("Accept", "application/json")
        .GET()
        .build();

CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(
                request, HttpResponse.BodyHandlers.ofString());
```

This is a **code snippet**, not an offline-runnable program: the URI requires network access/a valid certificate; you must import `java.net.URI`, `java.net.http.HttpClient/HttpRequest/HttpResponse`, `java.time.Duration`, and `java.util.concurrent.CompletableFuture`.

Explanation:
- `HttpClient` is an object that can be reused across multiple requests; reusing it enables connection pooling per the implementation.
- `HttpRequest` describes a request to be sent; it is not an HTTP response and does not start I/O just by being `build()`ed.
- `sendAsync(...)` initiates the logical HTTP exchange and returns the corresponding future.
- `BodyHandlers.ofString()` instructs the library to collect the body and provide a `String` when the response is ready.
- `connectTimeout(...)` limits the connection establishment step per the API; `request.timeout(...)` limits waiting for the response per request semantics. Do not use that single timeout to infer that the entire business transaction has completed in every streaming model.
- If using credentials, proxies, cookies, redirects, or a custom `SSLContext`, configure them on the client before building; do not assume an asynchronous method replaces security policies.

**There is no need** to write `new Thread(() -> client.send(...))` to get a standard async API: `sendAsync` already provides an abstraction integrating the HTTP exchange and `CompletableFuture`.

## 6. Future States and the Logical Exchange Lifecycle

A `CompletableFuture<HttpResponse<T>>` has the following conceptual states:

```text
                              ┌─────────────────────┐
      sendAsync(...) ───────► │ INCOMPLETE          │
                              │ pending / in-flight │
                              └─────────┬───────────┘
                                        │
                ┌───────────────────────┼───────────────────────┐
                ▼                       ▼                       ▼
       Normal completion     Exceptional completion         Cancelled
       HttpResponse<T>         I/O / TLS / timeout     CancellationException
                │                       │                       │
                └───────────────────────┴───────────────────────┘
                                        │
                                 future.isDone() = true
```

This is a learning model. At the moment `sendAsync` returns, the future **may** already have completed quickly; do not test code with the assumption “the future always stays pending for at least 100ms”. Conversely, if the server holds back the result, the future can remain pending for a long time.

The future state is **not necessarily identical** to the transport state:
- An HTTP 500 response with a valid body can **complete the future normally**.
- A streaming body handler can produce a normal future **before** all response bytes arrive.
- `cancel(true)` may mark the future as cancelled, but the HTTP request may already have been sent to the server; cancellation is an attempt to stop, not a guarantee that the server has not processed it.
- An exception from a `thenApply` callback can cause the **dependent stage** to fail, while the **original HTTP future** has already completed normally.

It is helpful to distinguish four observable states:
1. The request has been **created**.
2. The request has been **sent/is being processed** on the network.
3. The response future has **completed** according to the handler.
4. Business logic has **processed the result successfully**.

They are not a single boolean.

## 7. Runnable Java 17+: Proving the Future Is In-Flight

The first example creates an HTTP server **only on 127.0.0.1** using `com.sun.net.httpserver.HttpServer`. The server receives the `/wait` request but **deliberately waits on a CountDownLatch** before sending the response. Because of this, the application can prove:
- The server actually received the request.
- The returned future is still incomplete, because the response has not yet been allowed to be sent.
- The caller can build a pipeline with `thenApply` without blocking.
- When the server sends the response, the future and subsequent stages complete.
- HTTP 404 is also **a normal HttpResponse**, not an exception from `sendAsync`.

Save the file with the exact name **`AsyncExchangeDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class AsyncExchangeDemo {
    private static void respond(HttpExchange exchange, int status, String text)
            throws IOException {
        byte[] body = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, body.length);
        try (var out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch arrived = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/wait", exchange -> {
            arrived.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    respond(exchange, 504, "timed-out");
                    return;
                }
                respond(exchange, 200, "hello");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                exchange.close();
            }
        });
        server.createContext("/missing", exchange ->
                respond(exchange, 404, "not-found"));
        server.start();

        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(base.resolve("/wait"))
                    .timeout(Duration.ofSeconds(8)).GET().build();
            CompletableFuture<HttpResponse<String>> inFlight = client.sendAsync(
                    request, HttpResponse.BodyHandlers.ofString());
            if (!arrived.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Server did not receive request");
            }
            System.out.println("request-arrived=true");
            System.out.println("in-flight=" + !inFlight.isDone());

            CompletableFuture<String> processed = inFlight
                    .thenApply(response -> {
                        if (response.statusCode() != 200) {
                            throw new IllegalStateException("Unexpected status");
                        }
                        return response.body();
                    })
                    .thenApply(String::toUpperCase);
            release.countDown();
            System.out.println("processed=" + processed.get(5, TimeUnit.SECONDS));
            System.out.println("completed=" + inFlight.isDone());

            HttpRequest missing = HttpRequest.newBuilder(
                    base.resolve("/missing")).GET().build();
            CompletableFuture<HttpResponse<String>> missingFuture =
                    client.sendAsync(
                            missing, HttpResponse.BodyHandlers.ofString());
            HttpResponse<String> missingResponse =
                    missingFuture.get(5, TimeUnit.SECONDS);
            System.out.println("http-status=" + missingResponse.statusCode());
            System.out.println("exceptional="
                    + missingFuture.isCompletedExceptionally());
        } finally {
            release.countDown();
            server.stop(0);
        }
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac AsyncExchangeDemo.java
java AsyncExchangeDemo
```

Verified output when run with a JDK supporting the Java 17 API:

```text
request-arrived=true
in-flight=true
processed=HELLO
completed=true
http-status=404
exceptional=false
```

### Line-by-line Output Explanation

- `request-arrived=true`: the server's `/wait` handler has started running. The `arrived` latch ensures the main thread only prints after the server sees the request.
- `in-flight=true`: the server has **not been released yet** so it has not sent the response; `BodyHandlers.ofString()` cannot create a `String` from a response that has not appeared yet. Therefore `!inFlight.isDone()` is true in this controlled test.
- `processed=HELLO`: the main thread calls `release.countDown()`, the server sends `"hello"`; the future completes normally and the two `thenApply` stages run sequentially: checking for `200` and then converting the text to uppercase.
- `completed=true`: after `processed.get(...)` has finished, the parent HTTP future is guaranteed to have completed. `get` is used here only to **wait so the test can finish**, not as a pattern to call right after `sendAsync` in a production event loop.
- `http-status=404`: the server returns HTTP 404 with a valid body; `HttpClient` still creates an `HttpResponse<String>`.
- `exceptional=false`: status 404 **does not cause the future to complete exceptionally**. The application itself must define which statuses are considered business errors.

### Why Use CountDownLatch Instead of Thread.sleep?

If you do:

```java
CompletableFuture<HttpResponse<String>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
System.out.println(future.isDone());
```

then the result depends on server/network speed: it could be true or false. Sleeping for a few milliseconds also does not guarantee a deterministic execution order. The latch example lets us know with certainty that the response has not been sent when checking `isDone()`. **Do not use these latches to make a production server wait**; this is a deterministic testing technique.

## 8. Chaining: Processing Results Later Without Blocking the Caller

`CompletableFuture` allows creating dependent stages:

```java
CompletableFuture<String> bodyFuture = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body);

CompletableFuture<Integer> lengthFuture =
        bodyFuture.thenApply(String::length);
```

This is a code snippet, assuming `client` and `request` are available. `thenApply` transforms the value:
- `HttpResponse<String>` into `String`.
- `String` into `Integer`.
- The stages **do not need** to block the thread building the pipeline if the future has not completed yet.

What you should not do in an event loop/UI thread:

```java
HttpResponse<String> response = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .join(); // blocks until the future completes
```

This snippet is still **valid** Java, but it turns the caller into a waiter; usually that is not the goal of choosing `sendAsync`. If the code only needs a single synchronous request in a simple CLI program, `send(...)` may express the intent more clearly.

### Type of Each Stage

```text
CompletableFuture<HttpResponse<String>>
         │ thenApply(HttpResponse::body)
         ▼
CompletableFuture<String>
         │ thenApply(String::length)
         ▼
CompletableFuture<Integer>
```

`thenApply` does not create a new HTTP request; it creates a **dependent future**. If the parent HTTP future fails, subsequent stages typically do not invoke their transform functions and propagate the failure down the chain, unless a `handle`/`exceptionally` stage transforms the result.

## 9. thenApply, thenAccept, thenRun, and whenComplete

| Method | Callback receives | Return value for dependent future | Use when |
| --- | --- | --- | --- |
| `thenApply(fn)` | Success value `T` | `CompletableFuture<U>` | Transforming the response into a model/body/result |
| `thenAccept(consumer)` | Success value `T` | `CompletableFuture<Void>` | Writing output, updating state/metrics |
| `thenRun(action)` | Receives no value | `CompletableFuture<Void>` | Performing a next step when the parent stage succeeds |
| `whenComplete((value,error) -> ...)` | Value or error | Future with the same result/type (unless the action throws an error) | Logging/cleanup, does not recover from errors on its own |
| `handle((value,error) -> U)` | Value or error | `CompletableFuture<U>` | Producing a replacement result or transforming both success/failure |
| `exceptionally(error -> T)` | Error | `CompletableFuture<T>` | Recovering from an error with a value of the same type |

Example of checking status before extracting the body:

```java
CompletableFuture<String> result = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> {
            if (response.statusCode() / 100 != 2) {
                throw new IllegalStateException(
                        "Unexpected HTTP status: " + response.statusCode());
            }
            return response.body();
        })
        .whenComplete((body, error) -> {
            if (error != null) {
                System.err.println("Request failed");
            }
        });
```

This is a code snippet. If the server returns 404, the original HTTP future **can succeed**, but `thenApply` itself throws `IllegalStateException`, causing the **dependent `result`** to complete exceptionally. Do not confuse business exceptions with network exceptions from `sendAsync`.

### A Warning About Callbacks

`thenApply` without the `Async` suffix may be executed by the thread **that completes the parent future** or the thread **registering the callback after the future has already completed**; do not rely on thread names or scheduler ordering. In an event-driven service, callbacks must be fast enough or offload heavy work to an appropriate executor. Do not place huge CPU-bound parsing, blocking DB queries, or long `Thread.sleep` calls inside an I/O callback.

## 10. thenApplyAsync and Executor: Explicitly Setting Thread Boundaries

If post-response processing is CPU-intensive or needs to be separated from the I/O completion path:

```java
ExecutorService workers = Executors.newFixedThreadPool(4);

CompletableFuture<Result> stage = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApplyAsync(response -> parseBusinessData(response.body()),
                workers);
```

This is a **code snippet** and does not compile standalone; `Result` and `parseBusinessData` are application types/functions, with imports `java.util.concurrent.*`. You need to shut down `workers` when the application exits.

`thenApplyAsync(..., workers)` submits the transform task to the provided executor. If you use `thenApplyAsync(fn)` without supplying an executor, `CompletableFuture` uses the default async execution mechanism per its contract; you should not assume it is the **same executor** as `HttpClient.Builder.executor(...)`.

### What Does HttpClient.Builder.executor(...) Do?

`HttpClient.newBuilder().executor(executor)` provides an executor for certain asynchronous/dependent tasks per the implementation and API documentation. It does **not** mean every callback of every `CompletableFuture` is guaranteed to run on that executor. Callback design should use the `thenApplyAsync(..., executor)` variant when you genuinely want to bind a specific step to a thread pool you manage.

In JavaFX/Swing GUIs, do not update the UI arbitrarily from a callback thread. Dispatch the result back to the JavaFX Application Thread or Swing Event Dispatch Thread using the framework's mechanism. In servlet/reactive/event-loop servers, do not call blocking `join` directly on the request/event-loop thread.

## 11. thenCompose: When the Second Request Depends on the First

If request B can only be sent **after** response A is inspected, `thenCompose` is appropriate. Logical example: fetch authentication info or an ID in the first step, then call the next endpoint.

```java
CompletableFuture<HttpResponse<String>> secondResponse = client
        .sendAsync(firstRequest, HttpResponse.BodyHandlers.ofString())
        .thenCompose(first -> {
            if (first.statusCode() != 200) {
                return CompletableFuture.failedFuture(
                        new IllegalStateException("Step A failed"));
            }
            HttpRequest next = HttpRequest.newBuilder(
                    URI.create("https://api.example.com/next"))
                    .GET()
                    .build();
            return client.sendAsync(
                    next, HttpResponse.BodyHandlers.ofString());
        });
```

This is a **code snippet** and performs no network I/O just by being read; `client` and `firstRequest` must be available, and the URI must be permitted by the application. Required imports include `URI`, `HttpRequest`, `HttpResponse`, and `CompletableFuture`. `failedFuture` has existed since Java 9, so it works in Java 17.

**Core difference:**
- `thenApply(first -> client.sendAsync(second,...))` creates a **nested** future: `CompletableFuture<CompletableFuture<HttpResponse<String>>>`.
- `thenCompose(first -> client.sendAsync(second,...))` **flattens** the two layers into a single `CompletableFuture<HttpResponse<String>>`.

Avoid blindly using `first.body()` as the URL/host of request B without validation. For untrusted input, apply a scheme/host/port allowlist and anti-SSRF policy before constructing the next request.

## 12. Multiple Independent Requests: allOf and Combining Results

When there are two independent HTTP requests, you can start both before waiting:

```java
CompletableFuture<HttpResponse<String>> fa =
        client.sendAsync(requestA, HttpResponse.BodyHandlers.ofString());
CompletableFuture<HttpResponse<String>> fb =
        client.sendAsync(requestB, HttpResponse.BodyHandlers.ofString());

CompletableFuture<String> combined = CompletableFuture
        .allOf(fa, fb)
        .thenApply(ignored ->
                fa.join().body() + "|" + fb.join().body());
```

This is a **code snippet**, requiring valid `requestA`/`requestB` and an available `client`. `allOf(...)` completes when all futures have completed; inside `thenApply` of a succeeded `allOf`, `fa`/`fb` have already completed normally, so `join()` on them no longer waits on the network. However, `allOf` does not directly return a list of `HttpResponse`s, so you must keep references to the member futures.

Notes:
- If one future fails, `allOf` can also complete exceptionally; a dependent `thenApply` that handles success will not run.
- `allOf` does not **automatically cancel** all other requests when one request fails. You need an explicit policy if you want to cancel the rest.
- HTTP/2 multiplexing/connection pooling is decided by `HttpClient`; the number of `CompletableFuture`s does not guarantee that exact number of TCP connections.
- Do not fire tens of thousands of `sendAsync` calls simultaneously without bounding memory, connection pool, server rate, and pending responses. Asynchrony requires **concurrency limits/backpressure**, not unbounded execution.

### anyOf and applyToEither

- `CompletableFuture.anyOf(...)` completes with whichever future finishes first (including exceptional completion), returning `Object` and thus losing specific type information.
- `applyToEither` is suitable when you want a successful result from one of two compatible computations, but you must understand exception handling and side effects of requests that are still running.
- Avoid “racing” two HTTP POSTs that create transactions without idempotency. The first future completing does not prove the other request never reached the server.

## 13. HTTP Errors vs. Exceptional Completion

This is the most common misconception when handling async HTTP:

```text
HTTP request sent successfully
  ├─ server returns 200 -> HttpResponse (normal future)
  ├─ server returns 404 -> HttpResponse (normal future)
  ├─ server returns 500 -> HttpResponse (normal future)
  └─ server returns 302 -> HttpResponse or auto-redirect per policy

HTTP exchange encounters transport/protocol error before result:
  ├─ cannot connect
  ├─ TLS/certificate/handshake error
  ├─ timeout
  ├─ I/O or body handling error
  └─ future may complete exceptionally
```

`HttpResponse.BodyHandlers.ofString()` **does not automatically throw an exception when the status is not 2xx**. That is the responsibility of business code.

For example, in the Section 7 demo:

```text
http-status=404
exceptional=false
```

`future.isCompletedExceptionally()==false` means the HTTP future received the 404 response as designed; no business check has been applied yet. To make status 404 fail a downstream future, write it explicitly:

```java
CompletableFuture<String> verified = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(response -> {
            int code = response.statusCode();
            if (code < 200 || code >= 300) {
                throw new IllegalStateException("HTTP " + code);
            }
            return response.body();
        });
```

Only then does `verified` complete exceptionally on 4xx/5xx. The **original HTTP future** still completes normally. When debugging, you must know **which stage produced the exception** to avoid mistakenly thinking the server was unreachable.

## 14. How to Retrieve Exceptions: get, join, whenComplete, and exceptionally

A `CompletableFuture` can fail in the network layer or in a callback. Ways to observe it:

| Method | On normal completion | On error completion |
| --- | --- | --- |
| `future.get()` | Returns `T`; may block | Throws `ExecutionException` wrapping cause; or interruption/cancellation |
| `future.join()` | Returns `T`; may block | Throws `CompletionException` wrapping cause; or cancellation |
| `whenComplete((v,e) -> ...)` | Receives value and `e==null` | Receives error; mainly for observation/logging/cleanup |
| `handle((v,e) -> newValue)` | Can transform value | Can transform exception into another value |
| `exceptionally(e -> fallback)` | Keeps value unchanged | Runs fallback and lets dependent stage complete normally if fallback does not throw |

Example:

```java
CompletableFuture<String> safe = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body)
        .exceptionally(error -> {
            logFailure(error);
            return "unavailable";
        });
```

This is a **code snippet**; `logFailure` is an application-defined function. `exceptionally` allows the dependent `safe` future **to complete normally** with `"unavailable"` even if the HTTP exchange actually failed. If the data is critical, **do not** return a fallback and silently report business success. You can use `whenComplete` to log while still propagating the error to the caller.

### Multi-Layer Wrapped Exceptions

`join()` may throw `CompletionException`, while `get()` typically throws `ExecutionException` when a computation fails. You need to inspect `getCause()`/the cause chain, such as an underlying `HttpConnectTimeoutException`, `HttpTimeoutException`, `SSLHandshakeException`, or `IOException`. Do not just print the wrapper's stack trace and conclude the root cause cannot be found.

There are errors **thrown synchronously when calling sendAsync**, such as `IllegalArgumentException` if the request is not a validly built request per the API. You cannot assume **every error** will necessarily surface only through the future.

## 15. BodyHandler Defines What “Completed” Means

A request may receive headers early while the body arrives slowly over many seconds or minutes. Therefore:

```text
Server                      Client HttpClient

send status+headers  ───────► BodyHandler selected
                            │
  if ofInputStream          ├─ returns HttpResponse<InputStream>
                            │   future may be DONE
send body chunk #1 ─────────►│   application reads from InputStream
send body chunk #2 ─────────►│
end stream ─────────────────►│   application reads until EOF/close
                            │
  if ofString               └─ future DONE after full body collected
```

The Java SE 17 API for `HttpResponse.BodyHandlers.ofInputStream()` states explicitly: **response headers have been sufficiently read when `HttpResponse` is returned, though the body may not have been completely received yet**. With `ofString()`, the body has already been collected into a string when the response is returned.

This is a very practical difference:
- `future.isDone()` with `ofInputStream` does **not** mean the entire file has been downloaded.
- If you only obtain `response.body()` and neither read nor close it, connection resources may remain held.
- To stream large JSON, media, or downloads, you must design how to read/consume the stream, timeouts, backpressure, and cleanup.
- To handle small bodies as strings, `ofString` is convenient but can consume memory proportional to the response size.

## 16. Runnable Java 17+: Future Completes Before Body Finishes Sending

The second program uses a local server with two latches:
1. The server sends **status + headers** and calls `flush()` so header data goes out.
2. The server holds back the body, waiting on another latch.
3. The client calls `sendAsync(..., BodyHandlers.ofInputStream())`.
4. The client receives `HttpResponse<InputStream>` and the future is **already complete**, even though the server has not sent the body yet.
5. The client releases the latch, then reads the `InputStream` and closes it with try-with-resources.

Save the file with the exact name **`StreamingCompletionDemo.java`**:

```java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.InputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class StreamingCompletionDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch sentHeaders = new CountDownLatch(1);
        CountDownLatch releaseBody = new CountDownLatch(1);
        CountDownLatch sentBody = new CountDownLatch(1);
        HttpServer server = HttpServer.create(
                new InetSocketAddress(InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/stream", exchange -> {
            byte[] bytes = "stream-body".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            exchange.getResponseBody().flush();
            sentHeaders.countDown();
            try {
                if (!releaseBody.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Body release timed out");
                }
                try (var output = exchange.getResponseBody()) {
                    output.write(bytes);
                }
                sentBody.countDown();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                exchange.close();
            }
        });
        server.start();

        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/stream");
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(8)).GET().build();

            CompletableFuture<HttpResponse<InputStream>> future =
                    client.sendAsync(
                            request, HttpResponse.BodyHandlers.ofInputStream());

            if (!sentHeaders.await(3, TimeUnit.SECONDS)) {
                throw new IllegalStateException("No headers");
            }
            HttpResponse<InputStream> response = future.get(3, TimeUnit.SECONDS);
            System.out.println("status=" + response.statusCode());
            System.out.println("future-complete-before-body=" + future.isDone());
            System.out.println("body-sent-before-release="
                    + (sentBody.getCount() == 0));

            releaseBody.countDown();
            try (InputStream stream = response.body()) {
                String text = new String(
                        stream.readAllBytes(), StandardCharsets.UTF_8);
                System.out.println("body=" + text);
            }
        } finally {
            releaseBody.countDown();
            server.stop(0);
        }
    }
}
```

Compile/run:

```bash
javac StreamingCompletionDemo.java
java StreamingCompletionDemo
```

Verified output with the Java 17 API:

```text
status=200
future-complete-before-body=true
body-sent-before-release=false
body=stream-body
```

### Output Explanation

- `status=200`: the future already has `HttpResponse<InputStream>` with headers/status.
- `future-complete-before-body=true`: the corresponding future **has completed** per `BodyHandlers.ofInputStream`, even though the server has not finished sending the body.
- `body-sent-before-release=false`: the server's `sentBody` latch has not yet counted down to zero; the body is still waiting.
- `body=stream-body`: after `releaseBody.countDown()`, the server sends the body; the client calls `readAllBytes()` from the stream and closes it.

The takeaway is that **the future represents the state of the HTTP exchange per the BodyHandler contract**, not a flag guaranteeing that the business consumer has processed every byte. With streaming, the application's responsibility continues after future completion.

### Why Must Headers Be Flushed in the Example?

Some HTTP servers may buffer data when calling `sendResponseHeaders`. The example needs to **push headers out to the socket before holding back the body** so it does not create a false deadlock in the test. `exchange.getResponseBody().flush()` ensures the relevant output buffer is flushed before the main thread waits on the future. This is specific to the local test; you cannot infer from it that every server sends headers independently of the body in all situations.

## 17. Production Streaming: Close, Backpressure, and Ownership

When using `BodyHandlers.ofInputStream()`, the application must:
1. Read from the `InputStream` until EOF, or call `close()` if it does not want to read further.
2. Not keep the stream open indefinitely in an object that is no longer used.
3. Not perform blocking `InputStream.read()` on an event loop/UI thread if reception may take a long time.
4. Set read timeouts and size limits if the response can be large.
5. Ensure both exceptions and cancellation lead to cleanup.
6. Check status and Content-Type/Content-Length per protocol before parsing; Content-Length may be missing or wrong in untrusted input, so do not treat it as an absolute guarantee.

With `BodyHandlers.ofPublisher()`, `HttpResponse.body()` is a `Flow.Publisher<List<ByteBuffer>>` used for streaming with subscriber/backpressure. Java 17 JDK specifies that this publisher may only be subscribed to **once**; the application must subscribe/consume and handle cancellation according to the Flow contract. If you only hold the publisher without subscribing, resources may not be properly released.

**Do not** rely solely on `future.isDone()` to mark a file as “100% downloaded” in the UI. With `ofFile`, the future completes after the file is fully written; with `ofInputStream`, the future can complete before the application finishes reading the content. Choose the handler according to the resource/UX model actually needed.

## 18. Timeouts: Connect Timeout, Request Timeout, Stage Timeout

There are multiple different timeout layers:

| Timeout/mechanism | Where set | Scope |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(Duration)` | On the client | Time limit for establishing a new connection; does not replace all timeouts |
| `HttpRequest.Builder.timeout(Duration)` | On the request | Time limit waiting for the response per HttpRequest contract; error may be `HttpTimeoutException` |
| `future.orTimeout(time, unit)` | On `CompletableFuture` | Causes the future to complete exceptionally if still incomplete after the stage deadline |
| `future.completeOnTimeout(value, time, unit)` | On `CompletableFuture` | Can complete the future with a fallback of the **same type** after timeout |
| Overall business deadline | Application logic | Covers retries, multiple requests, parsing/consuming streaming body, DB work, callbacks |

Code snippet setting a deadline for a transform stage:

```java
CompletableFuture<String> bodyFuture = client
        .sendAsync(request, HttpResponse.BodyHandlers.ofString())
        .thenApply(HttpResponse::body)
        .orTimeout(5, TimeUnit.SECONDS);
```

This is a code snippet requiring `java.util.concurrent.TimeUnit`. `orTimeout` can cause the **called future** to complete exceptionally, but **setting a deadline on a stage should not be treated as a guarantee that the underlying HTTP transport has terminated immediately**. Set a timeout on the request and implement active cancellation/cleanup per policy.

Do not use `completeOnTimeout` with a fake `HttpResponse` to pretend “the server returned HTTP 200” when no response arrived. If you want a business fallback, represent it explicitly with a result type such as `Success/Timeout/Error` rather than fabricating network data.

### Special Deadline Attention for Streaming

An `ofInputStream` future may already have completed when headers arrive; at that point, a timeout applied only to the **already-completed future** will not bound the time the application spends reading the body stream afterward. You must manage stream-reading deadlines and close the stream when the limit is exceeded. That is why you cannot say “`orTimeout` protects the entire download duration” for every BodyHandler.

## 19. Cancellation: Cancelling the Future Does Not Guarantee the Server Has Not Processed It

The default `HttpClient` in Java 17 returns cancellable `CompletableFuture`s. Calling:

```java
boolean requested = future.cancel(true);
```

is a **cancellation request** when the future has not yet completed. Per the Java 17 `HttpClient` API:
- Cancelling is an **attempt** to terminate the HTTP exchange and release resources early.
- **There is no guarantee** that cancellation will take effect immediately.
- The request may already have been sent to the server, and the server may even have started processing it.
- With HTTP/1.1, the client may abruptly close the connection.
- With HTTP/2, the client may reset the stream and in some situations close the connection.
- Derived futures from cancellable futures may also have cancellation semantics depending on the implementation.
- Cancellation may cause `join`/`get` to throw `CancellationException`.

**Do not cancel a future to “guarantee a money transfer will not happen”** after sending the request. The network layer does not provide exactly-once business semantics; you must use an idempotency key, transaction ID, server state, and business confirmation/cancellation workflows.

### Why Doesn't `cancel(true)` Replace Timeouts?

Cancellation may be called when the user clicks “Cancel” or an app deadline expires. However:
1. The future may already have completed before cancel.
2. The HTTP request may already have gone over the network.
3. The server may still be processing it.
4. Network resources may be released asynchronously.
5. Streaming responses need stream/subscriber cleanup per their lifecycle.

Therefore, you need to combine deadlines, cancellation attempts, resource closing, and **server-side result reconciliation** when requests have side effects.

## 20. Retries: When Safe, When Dangerous?

When a future completes exceptionally due to a timeout/connection reset, the client **does not necessarily know whether the server received and processed the request**. If you retry automatically:
- `GET` is usually idempotent in HTTP semantics, but still needs attempt limits/backoff and a network policy.
- `POST` creating orders, payments, or writing data is **not automatically idempotent**. Retrying can create duplicate effects if an idempotency key is missing.
- Body publishers may not be replayable; retrying may fail or send different data.
- Redirects, authentication challenges, proxies, and HTTP/2 multiplexing can also complicate defining a “send attempt”.

A production retry policy should have:
- A list of methods/statuses/exceptions **allowed** to be retried.
- Attempt limits, backoff with jitter, and an overall deadline.
- An idempotency key/request ID for write operations when supported by the server.
- Concurrency/rate limits, without multiplying requests unboundedly.
- Observability recording which attempts were made, without logging secrets.
- Cancellation checks and resource cleanup between attempts.

`CompletableFuture.exceptionally(...)` by itself **does not** retry an HTTP request. It only provides a fallback for a stage on error. To retry, you must actually issue a new `sendAsync` per policy; do not call the client unboundedly inside a callback.

## 21. Request Timeout Does Not Completely Replace Pipeline Structure

An API request may consist of multiple stages:

```text
sendAsync(request A)                    (network)
        │
        ▼
thenApply(validate status)              (cheap CPU)
        │
        ▼
thenCompose(sendAsync(request B))       (dependent network)
        │
        ▼
thenApply(parse response B)             (CPU)
        │
        ▼
write database / publish event          (business I/O)
```

`HttpRequest.timeout(...)` on A applies to request A; it **does not automatically cover** request B, the DB write, and the entire pipeline. To ensure the whole task finishes within 5 seconds, you need an overall deadline tracked/applied across the chain of work, while also bounding the internal components.

Placing `orTimeout` at the **end of the dependent future** prevents the caller from waiting indefinitely, but the stage timeout itself does not guarantee all network/DB side effects have actually stopped. You must actively propagate cancellation, close body streams, request dependent tasks to stop where possible, and track ambiguous outcomes.

**Do not block inside `thenCompose` using `send(...).get()`** to “wait for request B then return”. Return the future of request B and let composition handle the rest.

## 22. Asynchronous I/O Still Has Threads, Memory, and Backpressure

`sendAsync` is not zero-resource magic:
- `HttpClient` uses internal mechanisms to manage sockets, buffers, tasks, and TLS.
- Some callbacks may run on completion threads or executors.
- Body handlers like `ofString` buffer the body in memory, unsuitable for unbounded large responses.
- If you fire 50,000 futures at once, the application can still exhaust memory, sockets/FDs, connection slots, or overload the server.

In production:
1. Bound the number of pending HTTP exchanges (e.g., semaphore or bulkhead).
2. Use `sendAsync` to avoid holding a blocked caller thread per request, but **do not** allow unbounded concurrency.
3. Measure queue wait, time-to-first-byte, body completion, and total pipeline duration.
4. Choose the appropriate `BodyHandler` (bytes/string/file/stream/publisher).
5. Manage thread pools/`ExecutorService` and clean up properly in the lifecycle.
6. Do not treat Java 17 `HttpClient` as an HTTP/3 client; standard Java 17 API implementations are primarily HTTP/1.1/HTTP/2, independent of `sendAsync`'s nature.
7. Restrict logging of personal payloads, Authorization headers, tokens, and signed URLs.

**One future is not one TCP connection.** An `HttpClient` can reuse connections; HTTP/2 can multiplex multiple HTTP requests over the same transport. The number of futures reflects the number of logical operations awaiting results, **not** the number of network sockets.

## 23. Usage in Servers and User Interfaces

### Async-Style Backend

In an asynchronous request handler, you can directly return a `CompletionStage` or `CompletableFuture` to a supporting framework:

```java
CompletionStage<String> fetch(HttpClient client, HttpRequest request) {
    return client
            .sendAsync(request, HttpResponse.BodyHandlers.ofString())
            .thenApply(response -> {
                if (response.statusCode() != 200) {
                    throw new IllegalStateException(
                            "Remote status " + response.statusCode());
                }
                return response.body();
            });
}
```

This is an **illustrative method**, requiring imports `java.net.http.*` and `java.util.concurrent.CompletionStage`. It does not contain a class, `main`, or import statements so it does not run standalone; a specific framework can handle the returned stage according to its own mechanism.

Good point: the method **returns a stage**, without blocking the caller with `join()`. The framework can register a callback to send the response when upstream completes. Things to manage: cancellation when the incoming client disconnects, downstream timeouts, tracing context propagation, and mapping failures to appropriate HTTP statuses.

### Desktop Applications

With Swing/JavaFX:
- Initiate `sendAsync` on a UI action.
- In callbacks, parse/validate in an appropriate background context.
- Dispatch UI updates back to the **Swing EDT** or **JavaFX Application Thread**; do not modify the UI arbitrarily from an HTTP worker thread.
- When the window is closed, you can perform best-effort cancellation while still managing streams/side effects.

### CLI Programs

If there is only a single request and you need the result before the process exits, using `send` may be simpler; or `sendAsync(...).thenApply(...).get(...)` at the exit boundary. What to avoid is **faking async** at every layer while actually blocking on every step.

## 24. Testing Asynchronous Code Properly

Async code is prone to test flakiness if it relies on `Thread.sleep`. With a local HTTP server, test using a `CountDownLatch` or barrier:
- Ensure the server **has seen the request** before checking the pending state.
- Deliberately hold back the response so the future does not complete yet.
- Release the server and then wait for the final stage with a timeout.
- Do not rely on “the network will probably take a few milliseconds”.
- Use the loopback address and OS-assigned port `0` to avoid port conflicts.
- Close/stop the server in `finally`, even if the test fails.

Useful test matrix:

| Case | Result to verify |
| --- | --- |
| Server holds response | Future is pending while caller can continue |
| Server sends 200 + small body | `ofString` future returns `HttpResponse<String>`, accurate body |
| Server sends 404 or 500 | HTTP future **succeeds**; status handled by app |
| DNS/connection/TLS failure | Future completes exceptionally with appropriate cause |
| `BodyHandler.ofInputStream`, headers before body | Future completes when headers are ready even if body is not finished |
| Stream is read and closed | Does not leave HTTP exchange resources held indefinitely |
| Transform callback throws error | Dependent future is exceptional even though original HTTP response succeeded |
| `thenCompose` creates request B after A | Does not send B before conditions are met, does not create nested future |
| `allOf` two requests | Combines only after both succeed; handles aggregate errors |
| Request timeout | Future reports error; does not block indefinitely |
| Cancellation while server is processing | Client cancels best-effort; does not assume server has not processed |
| Many concurrent requests | Has concurrency limit, no out-of-memory or starvation |
| Redirect/auth | Final status and response interpreted correctly per client config |

**Do not** use a test server that immediately returns 200 to assert that the future “must be pending after sendAsync”: on loopback, the response may complete before the test thread calls `isDone()`. Latches are the way to control state conditions, as shown in the programs in Sections 7 and 16.

## 25. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `sendAsync(...).join()` right in the event loop | Caller is still blocked | Return the future or register a callback |
| Assuming every future is not done right when returned | Test flakiness | Use a latch/barrier to control timing |
| Assuming a completed future means the full body is downloaded | Wrong for `ofInputStream`/`ofPublisher` | Understand handler contract and consume/close stream |
| Assuming HTTP 404 is a `CompletionException` | Not automatically true | Check `HttpResponse.statusCode()` |
| Ignoring the returned future | Async failures go unobserved | Attach success/failure handler or return stage to caller |
| Using `thenApply` for a second HTTP request | Nested future hard to manage | Use `thenCompose` |
| Using `whenComplete` to “recover” by returning a fallback | Does not replace value by design | Use `handle`/`exceptionally` explicitly |
| Letting heavy CPU/blocking callbacks run in the completion path | Slows I/O or causes starvation | `thenApplyAsync` with an appropriate executor |
| Calling `get()` without a deadline on the UI thread | UI freezes | Use async callbacks, set timeouts |
| Retrying POST without idempotency | Transaction may be executed twice | Idempotency key + retry policy |
| Calling `cancel(true)` and assuming the server never received it | Ambiguous transaction outcome | Best-effort cancel + server reconciliation |
| Not bounding futures/pending requests | Exhausts memory/sockets | Concurrency limit/backpressure |
| Not reading/closing the body stream | Resource leaks, connections not reused | Try-with-resources/consume to EOF |
| Catching exceptions and returning a fake “200 OK” response | Hides real errors | Typed error result / status mapping |
| Using only `connectTimeout` for the entire pipeline | Does not cover body/callback/DB work | Request/stage/business deadlines |
| Confusing a future with 1 TCP socket | Wrong metrics, hard to optimize | Observe logical exchange and transport separately |
| Not checking response code before parsing JSON | Parse error or treating 404 as success | Validate status/content-type before parsing |
| Logging full body/URL tokens | Information leak | Mask/limit logs and tracing metadata |

## 26. Self-Check Questions

**Question 1.** What type does `sendAsync(request, BodyHandlers.ofString())` return?  
**Answer:** `CompletableFuture<HttpResponse<String>>`. The future represents the response that will be available in the future, not a `String` directly.

**Question 2.** Must the returned future always be incomplete?  
**Answer:** No. The request can complete quickly; `isDone` when the caller checks may be true or false. When testing pending state, use a server gate/latch.

**Question 3.** How does `sendAsync` mainly differ from `send`?  
**Answer:** `send` blocks the caller waiting for the response and returns `HttpResponse<T>`; `sendAsync` returns `CompletableFuture<HttpResponse<T>>` early, allowing subsequent work to be registered.

**Question 4.** If the server returns HTTP 404, is `future.isCompletedExceptionally()` necessarily true?  
**Answer:** No. Status 404 is still a normal `HttpResponse` if the exchange succeeded at the HTTP layer; business logic must check the status itself.

**Question 5.** How does `thenApply(HttpResponse::body)` change the type?  
**Answer:** From `CompletableFuture<HttpResponse<String>>` to `CompletableFuture<String>`, with a string handler.

**Question 6.** Should you call `join()` right after `sendAsync` in a JavaFX UI handler?  
**Answer:** No. It can block the UI thread. Use callbacks and dispatch results to the JavaFX Application Thread.

**Question 7.** When should you use `thenCompose`?  
**Answer:** When the function in the chain returns another future, such as request B depending on response A; `thenCompose` flattens the nested future.

**Question 8.** Does `allOf` return a list of `HttpResponse`s?  
**Answer:** No. It returns `CompletableFuture<Void>`; keep references to the member futures to retrieve their results after all complete.

**Question 9.** Why can `ofInputStream` produce a completed future before the body arrives?  
**Answer:** The contract allows returning `HttpResponse<InputStream>` once headers are sufficiently read; reading the body continues via the `InputStream` which the caller must consume/close.

**Question 10.** If `future.cancel(true)` succeeds, is it certain the server has not processed the request?  
**Answer:** No. Cancel is only best-effort; the request may already have reached the server or caused side effects.

**Question 11.** Is `whenComplete` a good way to replace an error with a fallback value?  
**Answer:** That is not its primary purpose. `whenComplete` is for observation/cleanup; `handle` or `exceptionally` expresses recovery more clearly.

**Question 12.** Is the number of milliseconds from `sendAsync` to callback guaranteed by the API?  
**Answer:** No. Timing depends on the network, server, executor, body handler, and load; do not use a small stopwatch to infer semantics.

**Question 13.** What is the problem if you use `ofInputStream` and do not read/close the stream?  
**Answer:** HTTP exchange/resources may remain held, causing connection/thread/buffer leaks and improper backpressure.

**Question 14.** If the response is 200 but business JSON parsing throws an exception, which future fails?  
**Answer:** The dependent parse stage can become exceptional, even though the original HTTP future completed normally. You need to know which stage produced the error.

**Question 15.** Should two independent requests run sequentially or can both futures be started and combined with `allOf`?  
**Answer:** You can start both and use `allOf` if appropriate for concurrency/rate limits. If B depends on A, `thenCompose` is more suitable.

## 27. Summary of the Application Workflow

For an asynchronous HTTP exchange in Java 17:

1. Create `HttpClient` and `HttpRequest` with proper timeouts, SSL/auth/proxy, and redirect policy.
2. Choose `BodyHandler<T>` according to the **body lifetime** and desired result type.
3. Call `sendAsync(request, handler)`, keeping or returning `CompletableFuture<HttpResponse<T>>`.
4. Register `thenApply`/`thenCompose`/`whenComplete`/`exceptionally` to handle success/failure and dependencies **without blocking** the caller.
5. Check HTTP status and headers explicitly; **4xx/5xx do not automatically become future exceptions**.
6. When streaming, read/close the body stream or subscribe/consume the publisher per contract; do not equate future done with body consumed.
7. Set request/stage/overall deadlines; perform best-effort cancellation and resource cleanup.
8. Bound concurrency, memory, and retries; protect idempotency for requests with side effects.
9. Observe root errors and callback errors separately; do not swallow failures with fake fallbacks.
10. Test the in-flight state with latches, and test body streaming and edge cases on loopback.

**Core conclusion:** `sendAsync` does not return “the HTTP result right now”. It returns a **CompletableFuture** representing **the result of an in-flight HTTP exchange**, allowing the application to describe the steps to take **after** the response becomes usable according to the `BodyHandler`. Completion of the future does not by itself replace status validation, business processing, cancellation policies, or streaming body lifetime management.

## 28. Official References

- Java SE 17 `HttpClient` — `send`/`sendAsync`, response body handler, cancellation semantics: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Java SE 17 `HttpRequest.Builder` — `timeout`, URI, method, headers, body publisher: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html
- Java SE 17 `HttpResponse` — status, headers, body, URI, and previousResponse: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html
- Java SE 17 `HttpResponse.BodyHandlers` — `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `ofPublisher`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Java SE 17 `HttpResponse.BodySubscribers` — body completion timing, streaming, and close obligations: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- Java SE 17 `CompletableFuture` — chaining, `thenApply`/`thenCompose`/`allOf`, cancellation, deadlines: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Java SE 17 `HttpTimeoutException` and `HttpConnectTimeoutException`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpTimeoutException.html
- Java SE 17 `HttpServer` — JDK local test HTTP server: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
- RFC 9110 — HTTP Semantics, status codes, and request properties: https://www.rfc-editor.org/rfc/rfc9110
