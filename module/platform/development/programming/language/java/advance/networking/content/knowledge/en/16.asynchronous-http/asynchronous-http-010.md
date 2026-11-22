# Closing HttpClient After In-Flight Requests and Bodies Are Handled

A `java.net.http.HttpClient` can be shared across many HTTP requests, reusing its connection pool and executing `sendAsync()` operations in the background. However, “Future completed” **does not always mean the entire response body has been consumed**, and “closing HttpClient” should not be understood simply as closing a socket. To shut down an application safely, you must coordinate the **lifecycle of the request, response-body stream, subscriber, executor, connection, and client**.

This Knowledge article focuses on **asynchronous HTTP in Java 17+**, while clearly highlighting the differences across JDK versions:

- **Java 11–20, including Java 17:** `HttpClient` **does not implement `AutoCloseable`** and **does not have** the new API methods `close()`, `shutdown()`, `shutdownNow()`, `awaitTermination()`, or `isTerminated()`. Do not copy `try (HttpClient client = ...)` examples from Java 21 into a Java 17 project: it will not compile.
- **Java 21 and later:** `HttpClient` **implements `AutoCloseable`** and provides `close()`/`shutdown()`/`awaitTermination(Duration)`/`shutdownNow()`/`isTerminated()`. The JDK's built-in implementation provides **best-effort** shutdown. `close()` initiates an orderly shutdown and **waits** for related operations to complete; if a body stream remains open or a publisher has no demand requested, it may wait for a very long time.
- **For both version groups:** you must fully process the body or cancel/close it according to the `BodyHandler`, manage `CompletableFuture`s/deadlines, and release resources only after a policy is in place for all in-flight operations.

The article includes **two standalone runnable examples**: a Java 17 example coordinating `sendAsync + ofString + ofInputStream + ofPublisher` on a loopback server; and a Java 21+ example using a bounded shutdown after receiving the full response. Each example has stdout output verified on a compatible recent JDK for the APIs used.

## 1. The Right Lifecycle: Do Not Close While Data Is Still in Flight

Separate at least five concepts:

| Layer | Unit to Manage | Completion Condition |
| --- | --- | --- |
| Request | `HttpRequest`, upload `BodyPublisher` | Request no longer needs to emit bytes, or a cancel/abort decision has been made |
| Result | `CompletableFuture<HttpResponse<T>>` | Stage completed successfully/exceptionally; body semantics depend on `BodyHandler<T>` |
| Response body | `String`, `InputStream`, `Stream<String>`, `Flow.Publisher<List<ByteBuffer>>`… | Body consumed to EOF/terminal signal, or explicitly closed/cancelled |
| Client/transport | `HttpClient`, HTTP/1.1 connection pool, HTTP/2 streams | No new requests accepted; existing operations resolved; resources reclaimed per API/JDK |
| Application executor | `ExecutorService` if created by application code and passed to the client | Tasks belonging to the executor completed/cancelled; executor shut down according to ownership |

Ideal coordination pattern:

~~~text
Application is still serving
     |
     v
[RUNNING] accept new requests; sendAsync(...)
     |
     | orderly stop requested
     v
[QUIESCING] stop creating/accepting new HTTP work
     |
     v
[DRAINING] wait for existing requests + BODY CONSUMERS to finish
     |            |
     |            +-- small body ofString/ofByteArray: future completes after body is collected
     |            +-- ofInputStream/ofLines: read to EOF or close
     |            +-- ofPublisher: subscribe once, request until terminal or cancel
     |            +-- custom subscriber: issue demand/complete or cancel
     |
     v
[CLOSING] Java 21+: shutdown/awaitTermination or close
     |         Java 17: no HttpClient.close(); clean up streams,
     |                  futures, owned executors, and release references appropriately
     v
[TERMINATED or STOPPED BY POLICY]
~~~

Rule of thumb: **stop accepting new work first, resolve already-accepted work, handle in-flight bodies, and only then shut down the client/transport**. If you close the client first and then wait for a subscriber that is waiting for data without ever having called `request(1)`, you can create a wait loop with no progress.

Distinguish between **the application no longer using the client** and **the JDK having immediately released every socket**. The API may perform resource cleanup asynchronously, especially when cancelling a request mid-flight; do not use `future.isDone()` as proof that the kernel has closed all connections.

## 2. Comparing Java 17 and Java 21+: Mandatory API Differences

| API / Issue | Java 17 | Java 21+ |
| --- | --- | --- |
| Create and reuse `HttpClient.newBuilder().build()` | Yes | Yes |
| `HttpClient.sendAsync()` returns `CompletableFuture<HttpResponse<T>>` | Yes | Yes |
| `HttpClient implements AutoCloseable` | **No** | **Yes** |
| `HttpClient.close()` | **No** | **Yes**, may wait for a very long time |
| `HttpClient.shutdown()` | **No** | **Yes**, initiates orderly shutdown, does not wait |
| `HttpClient.awaitTermination(Duration)` | **No** | **Yes**, bounded wait once shut down |
| `HttpClient.shutdownNow()` | **No** | **Yes**, attempts immediate stop; best-effort |
| `HttpClient.isTerminated()` | **No** | **Yes**, status after shutdown |
| `InputStream.close()` for `BodyHandlers.ofInputStream()` | Yes, and required if not read to completion | Yes, and still required |
| `Flow.Subscription.cancel()` for `ofPublisher()` | Yes, and required if not consuming further | Yes, and still required |

Example that **does not compile on Java 17**:

~~~java
// Java 21+ ONLY; DOES NOT compile with --release 17.
try (HttpClient client = HttpClient.newHttpClient()) {
    // Send/receive HTTP and consume the entire body before exiting.
} // client.close() on exiting try.
~~~

Example that is **valid on Java 17**:

~~~java
// Java 17+; HttpClient is a shared resource, not AutoCloseable in Java 17.
HttpClient client = HttpClient.newHttpClient();

// Coordinate sendAsync, consume/close response bodies.
// Cannot call client.close()/shutdown() using the Java 17 API.
~~~

In Java 17, the absence of `close()` on the client **does not exempt you from the responsibility** of cleaning up `InputStream`/`Stream`/Flow Subscriptions and application-owned executors. However, you also should not claim that “once the body is closed, the client immediately closes the connection pool”: `HttpClient` may keep connections for reuse, and internal resources are reclaimed according to runtime mechanisms.

For Java 21+, the Javadoc explicitly states that **the JDK's built-in implementation** overrides the shutdown methods. `HttpClient` is an abstract class and the shutdown methods have default implementations; do not assume a custom subclass always manages resources as well as the built-in client.

## 3. Future Completion: You Must Know Which BodyHandler Is Used

`sendAsync(request, bodyHandler)` returns `CompletableFuture<HttpResponse<T>>`. What “the response is ready” means differs depending on the type `T`.

| Handler | Result Type `T` | When the response Future completes, is the body fully handled? | Next Action |
| --- | --- | --- | --- |
| `BodyHandlers.ofString(UTF_8)` | `String` | Normally **yes**, because the handler collects the entire body before returning | Parse/validate, business processing |
| `BodyHandlers.ofByteArray()` | `byte[]` | Normally **yes**, if the exchange succeeded | Decode/write/process; watch memory |
| `BodyHandlers.ofFile(path)` | `Path` | Normally the handler has processed/written the body until completion | Check the file, close other resources per design |
| `BodyHandlers.discarding()` | `Void` | Body is read and discarded by the handler when the exchange completes | Check status or side effects |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Not necessarily**; may return the response right after headers | Read to EOF or `close()` |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Not necessarily**; stream lines are read afterwards | Consume or `Stream.close()` |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **No**; the publisher may still have the entire body waiting for a subscriber | Subscribe exactly once, request until `onComplete/onError` or `cancel()` |
| Custom `BodyHandler/BodySubscriber<T>` | Implementation-dependent | **Depends on when the `getBody()` stage completes** | Follow the custom contract and resource ownership |

**Common trap:**

~~~java
CompletableFuture<HttpResponse<InputStream>> f =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = f.join();
// join() here does NOT guarantee the body InputStream has been read to EOF.
// If the application discards response.body() without reading/closing it, the exchange may hold resources.
~~~

Another counterexample:

~~~java
CompletableFuture<HttpResponse<Flow.Publisher<List<ByteBuffer>>>> f =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofPublisher());

CompletableFuture.allOf(f).join();
// Only proves the response Future has completed.
// Does not guarantee the publisher has been subscribed to, nor that onComplete has run.
~~~

With streaming handlers, **a second stage/state is needed** to track the body: the subscriber's completion signal, finishing reading the `InputStream`, or handling close/error.

Do not use `HttpResponse.statusCode()==200` as proof that the body has been read: status and headers can arrive first, while the body is still streaming or fails later.

## 4. Managing Multiple sendAsync() Calls with CompletableFuture.allOf()

When the body is fully collected by the handler, you can wait for multiple asynchronous requests:

~~~java
// Java 17+ fragment, client/request1/request2 already exist.
CompletableFuture<HttpResponse<String>> first =
        client.sendAsync(
                request1,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

CompletableFuture<HttpResponse<String>> second =
        client.sendAsync(
                request2,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

CompletableFuture<Void> all = CompletableFuture.allOf(first, second);
all.orTimeout(10, TimeUnit.SECONDS).join();

System.out.println(first.join().statusCode());
System.out.println(second.join().statusCode());
~~~

Use `allOf()` when you need both exchanges to complete. With `ofString`, the response body has already been materialized before the Future succeeds. **However**:

- `allOf()` completes exceptionally if one component future fails. That is **not a guarantee that all remaining futures have been cancelled**. During shutdown, you must inspect/resolve all still-active work.
- `join()` can throw `CompletionException`, not just `IOException`. Extract the actual cause using `getCause()` when logging/handling errors.
- If `allOf(...).orTimeout(...)` expires, it completes the aggregate future with a timeout; the component request futures **are not automatically cancelled**. You need an explicit policy for each still-pending request.
- If the application has downstream stages such as parsing JSON, writing to a DB, updating a cache, or streaming to a file, `allOf(first,second)` **does not wait for those separately created stages**. Wait on the `CompletableFuture<Void> processingFutures` representing **all required work**, not just the original response futures.
- `Future.isDone()` includes success, failure, and cancellation—it does not mean success. `isCompletedExceptionally()` and handling `join/get` help classify the outcome.

### allOf Is Different from “Waiting for Full Business Completion”

~~~text
sendAsync(A) ----> full HTTP response --+--> parse A ---> save A
                                        |
sendAsync(B) ----> full HTTP response --+--> parse B ---> save B

allOf(sendAsync(A), sendAsync(B))  = only waits at the + mark.
allOf(save(A), save(B))            = waits for save stages to complete,
                                    if properly chained/error-propagated.
~~~

Dependency chain example:

~~~java
// Fragment: saveResult is a helper returning CompletionStage<Void>.
CompletableFuture<Void> processed =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8))
        .thenCompose(response -> saveResult(response.statusCode(),
                                            response.body()))
        .toCompletableFuture();

// Wait on processed if the shutdown condition requires saveResult to complete as well.
processed.join();
~~~

Do not put long blocking tasks into an `HttpClient` callback if that executor has a limited number of threads; you can use `thenApplyAsync/thenComposeAsync` with a bounded application executor, while managing that executor's lifecycle.

## 5. Reading to Completion or Closing InputStream from BodyHandlers.ofInputStream()

`BodyHandlers.ofInputStream()` returns an `InputStream` for streaming the body **after response headers may already have arrived**. The Java 17 documentation states that the caller **must** read to EOF **or** call `InputStream.close()` if they do not want to or cannot continue reading.

Successful reading pattern:

~~~java
// Java 17+ fragment, input/URI/client already configured.
CompletableFuture<HttpResponse<InputStream>> pending =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

HttpResponse<InputStream> response = pending.join();
try (InputStream body = response.body()) {
    // This is only suitable for SMALL bodies with a verified limit.
    byte[] all = body.readAllBytes();
    processBytes(all);
}
~~~

**For large responses**, do not use unbounded `readAllBytes()`. Read in fixed-size buffers and write to a bounded file/decoder:

~~~java
// Fragment: streaming processing with a fixed buffer.
// outputStream is an application-owned sink, to be closed at the appropriate layer.
try (InputStream body = response.body()) {
    byte[] chunk = new byte[8192];
    int n;
    long total = 0;
    long maxBytes = 20L * 1024 * 1024;

    while ((n = body.read(chunk)) != -1) {
        if (n > maxBytes - total) {
            throw new IOException("Response body exceeds size limit");
        }
        outputStream.write(chunk, 0, n);
        total += n;
    }
}
~~~

If the network or server stops sending before EOF, reading the stream can block; the design needs **an overall deadline, an activity timeout, and a cancel/close decision**, not just a small timeout on `CompletableFuture<HttpResponse<InputStream>>` for receiving headers.

### What If You Only Read Part of the Body and Discard the Rest?

You must call `body.close()`; otherwise, the connection may still hold unconsumed data. Closing the stream may cause an HTTP/1.1 connection to be closed and no longer reusable; for HTTP/2, the stream may be reset/affected at the protocol level. This is an intentional trade-off, better than silently leaking the body stream or keeping client shutdown blocked indefinitely.

If you use `BodyHandlers.ofLines()`, the body is a `Stream<String>`. You must also **consume it completely or close the stream**, rather than leaving the stream unfinished and assuming `sendAsync().join()` did everything. A `Stream` is not like an already-collected `String` body.

## 6. Closing the Publisher and Subscription Lifecycle of an HTTP Body

With `BodyHandlers.ofPublisher()`:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofPublisher())
                .join();

Flow.Publisher<List<ByteBuffer>> body = response.body();
body.subscribe(mySubscriber);
~~~

This publisher must be subscribed to **exactly once** per the JDK contract. The subscriber must:

1. Receive `onSubscribe(subscription)`.
2. Call `subscription.request(n)` with **n > 0** to allow receiving `List<ByteBuffer>` items. `request(1)` means **one List item**, not one byte.
3. Process each `onNext(batch)`, such as writing to a file, parsing, or forwarding downstream. When ready for more, call `request(n)` again.
4. On `onComplete()`, mark the body as finished; on `onError(error)`, report failure and clean up resources.
5. If deciding to stop before EOF or when a deadline expires, call `subscription.cancel()` and do not keep waiting for `onComplete`, because **cancel is not required to emit a terminal callback**.

### Anti-pattern: Publisher Without Demand

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    // Wrong if waiting for onComplete without ever requesting data:
    // the publisher may not be able to emit and can lead to a hung shutdown.
}
~~~

This is a **fragment** of a subscriber, not a standalone program. Java 21+ `HttpClient.close()` may have to wait for outstanding requests whose body publisher never received demand. The official documentation explicitly names `ofInputStream`/`ofLines`/`ofPublisher` and custom `BodySubscriber`s that do not request/cancel as reasons an orderly shutdown can **stall**.

### Using a Separate CompletableFuture to Track Body Completion

~~~java
// Java 17+ fragment; bodyPublisher is Flow.Publisher<List<ByteBuffer>>.
CompletableFuture<Void> bodyFinished = new CompletableFuture<>();
AtomicReference<Flow.Subscription> active = new AtomicReference<>();

bodyPublisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    @Override
    public void onSubscribe(Flow.Subscription s) {
        active.set(s);
        s.request(1);
    }

    @Override
    public void onNext(List<ByteBuffer> batch) {
        try {
            for (ByteBuffer buffer : batch) {
                handleChunk(buffer); // Helper: synchronous processing or with backpressure.
            }
            active.get().request(1);
        } catch (Throwable failure) {
            Flow.Subscription s = active.get();
            if (s != null) s.cancel();
            bodyFinished.completeExceptionally(failure);
        }
    }

    @Override
    public void onError(Throwable failure) {
        bodyFinished.completeExceptionally(failure);
    }

    @Override
    public void onComplete() {
        bodyFinished.complete(null);
    }
});
~~~

This is a **fragment**: `handleChunk`, imports, and timeout/response management belong to the application. If the deadline for `bodyFinished` expires before a terminal signal, **cancel the subscription**, then resolve the future along the “cancelled” branch without waiting for `onComplete` forever. With an asynchronous sink, do not call `request(1)` immediately after merely enqueuing if there is no end-to-end backpressure: wait for the sink to finish processing or keep the queue bounded.

Note that `onNext(List<ByteBuffer>)` delivers a list of read-only buffers; bytes can be split arbitrarily and do not align with business messages or UTF-8 characters. When decoding text, preserve decoder state or assemble bytes within limits. Do not grow memory unboundedly by collecting everything into a `ByteArrayOutputStream` while still calling it “bounded-memory streaming”.

## 7. Java 21+: close(), shutdown(), awaitTermination(), shutdownNow()

These new methods **were added in Java 21**.

### close() — Orderly Shutdown and Wait Until Completion

~~~java
// Java 21+ ONLY. Before exiting try, all bodies must be drained/closed/cancelled.
try (HttpClient client = HttpClient.newHttpClient()) {
    CompletableFuture<HttpResponse<String>> future =
            client.sendAsync(
                    request,
                    HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

    HttpResponse<String> response = future.join();
    consumeResult(response);
} // close() performs orderly shutdown and waits for the client to terminate.
~~~

This is a **fragment** requiring `request` and `consumeResult`. Key point: `try-with-resources` automatically calls `close()` when exiting the block, but **does not impose a finite deadline** for waiting on unhandled bodies. When a request has a Publisher body that was never requested, `close()` can wait indefinitely. `close()` is a **blocking** mechanism to finish, not `shutdownNow()`.

If the thread waiting in `close()` is interrupted, the API allows it to attempt `shutdownNow()` and then continue waiting until operations finish; afterward, the interrupt flag is restored. Do not rely on interruption as a “timeout that always finishes closing the client immediately”.

### shutdown() — Stop Accepting New Requests, Give Existing Ones a Chance to Finish

~~~java
// Java 21+ ONLY.
client.shutdown();
// Do not submit new requests through this client.
// Already-submitted requests and body consumers must continue to completion.
~~~

`shutdown()` **does not wait**. It initiates an orderly shutdown: existing requests may still need to read responses, invoke subscriber demand, write files, or wait on the network. If the caller stops running all body consumers immediately after `shutdown()`, the pipeline may not complete.

### awaitTermination(Duration) — Bounded Wait

~~~java
// Java 21+ ONLY; used after shutdown() or shutdownNow().
client.shutdown();

boolean terminated =
        client.awaitTermination(Duration.ofSeconds(10));

if (!terminated) {
    // Not completed within 10 seconds; escalation policy needed.
    client.shutdownNow(); // best-effort, does not guarantee immediate stop.
}
~~~

`awaitTermination(Duration)` returns `true` if terminated, `false` if it timed out first; it can throw `InterruptedException`. If duration ≤ 0, it performs an instantaneous status check without waiting. `isTerminated()` is meaningful after shutdown; before that, it is not expected to return `true` merely because no requests are currently in flight.

### shutdownNow() — Stronger Cancellation, but NOT a “Guaranteed Kill”

~~~java
// Java 21+ ONLY, for forced-stop after the deadline has passed.
client.shutdownNow();
boolean stopped =
        client.awaitTermination(Duration.ofSeconds(2));
if (!stopped) {
    reportStillRunning(); // Application helper: record that cleanup is not yet finished.
}
~~~

According to the Javadoc, `shutdownNow()` **attempts** an immediate shutdown and may interrupt running operations. The behavior of interrupted operations is **undefined**, and there is no guarantee that operations will terminate or that waiting threads will receive notifications. Therefore:
- Do not claim `shutdownNow()` always frees sockets in exactly 2 seconds.
- Do not assume a POST/upload was rolled back on the server.
- Do not reuse a shut-down client for new requests.
- If the deadline expires with `isTerminated()==false`, report the uncertain state and decide process/health/readiness shutdown policy according to your system.

### Preferred Normal Ordering

~~~text
1) Stop accepting/creating new HTTP work
2) Wait for all processing futures with an overall deadline
3) Drain or close/cancel all unfinished body streams
4) client.shutdown()
5) client.awaitTermination(gracePeriod)
6) If timed out: cancel pending, client.shutdownNow() (best-effort)
7) awaitTermination(shortFollowUp) and log remaining activity if not finished
8) Reclaim application-owned executors/app resources
~~~

For small applications with clear boundaries and no neglected streaming bodies, `try-with-resources HttpClient` can be a concise approach. For large servers needing a bounded shutdown deadline, `shutdown()/awaitTermination()/shutdownNow()` provide measurability and coordination instead of calling `close()` and waiting indefinitely.

## 8. Java 17+ — Complete Program That Finishes Requests and Streaming Bodies

This example uses `com.sun.net.httpserver.HttpServer` on `127.0.0.1` with an ephemeral port to simulate four endpoints: two String responses, one InputStream response, and one Flow Publisher response. The program demonstrates **actually waiting for the bodies** before ending the application-side lifecycle on **Java 17**; it does not call any `HttpClient.close/shutdown` methods because they do not exist in JDK 17.

Save as **`AsyncCloseLessonDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class AsyncCloseLessonDemo {
    private static final java.nio.charset.Charset UTF8 =
            StandardCharsets.UTF_8;
    private static final long WAIT_SECONDS = 5;

    private static void reply(HttpExchange ex, String text)
            throws IOException {
        try (InputStream ignored = ex.getRequestBody()) {
            byte[] bytes = text.getBytes(UTF8);
            ex.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            ex.sendResponseHeaders(200, bytes.length);

            try (OutputStream out = ex.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    private static HttpRequest get(String root, String path) {
        return HttpRequest.newBuilder(
                    URI.create(root + path))
                .timeout(Duration.ofSeconds(WAIT_SECONDS))
                .GET()
                .build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext("/one", ex -> reply(ex, "ONE"));
        server.createContext("/two", ex -> reply(ex, "TWO"));
        server.createContext("/stream",
                ex -> reply(ex, "STREAM"));
        server.createContext("/publisher",
                ex -> reply(ex, "PUBLISH"));
        server.start();

        try {
            String root = "http://127.0.0.1:"
                    + server.getAddress().getPort();

            // Java 17: no try-with-resources HttpClient,
            // no close()/shutdown() on HttpClient.
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1)
                    .build();

            // A: Two HTTP exchanges collecting full bodies into String.
            CompletableFuture<HttpResponse<String>> first =
                    client.sendAsync(
                            get(root, "/one"),
                            HttpResponse.BodyHandlers.ofString(UTF8));

            CompletableFuture<HttpResponse<String>> second =
                    client.sendAsync(
                            get(root, "/two"),
                            HttpResponse.BodyHandlers.ofString(UTF8));

            CompletableFuture.allOf(first, second)
                    .orTimeout(WAIT_SECONDS, TimeUnit.SECONDS)
                    .join();

            System.out.println(
                    "first=" + first.join().body());
            System.out.println(
                    "second=" + second.join().body());

            // B: Future<InputStream> may complete after headers,
            // body still needs to be read to EOF or close().
            HttpResponse<InputStream> streamResponse =
                    client.sendAsync(
                            get(root, "/stream"),
                            HttpResponse.BodyHandlers.ofInputStream())
                    .orTimeout(WAIT_SECONDS, TimeUnit.SECONDS)
                    .join();

            try (InputStream input = streamResponse.body()) {
                // This response is only 6 bytes controlled by the demo server.
                // DO NOT use unbounded readAllBytes for untrusted data.
                System.out.println(
                        "stream="
                                + new String(
                                        input.readAllBytes(), UTF8));
            }

            // C: ofPublisher returns the response when headers are ready;
            // the body must be subscribed to and consumed separately.
            HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                    publisherResponse =
                    client.sendAsync(
                            get(root, "/publisher"),
                            HttpResponse.BodyHandlers.ofPublisher())
                    .orTimeout(WAIT_SECONDS, TimeUnit.SECONDS)
                    .join();

            CountDownLatch complete = new CountDownLatch(1);
            AtomicReference<Flow.Subscription> subscription =
                    new AtomicReference<>();
            AtomicReference<Throwable> problem =
                    new AtomicReference<>();
            ByteArrayOutputStream received =
                    new ByteArrayOutputStream();

            publisherResponse.body().subscribe(
                    new Flow.Subscriber<List<ByteBuffer>>() {
                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription.set(s);
                    s.request(1);
                }

                @Override
                public void onNext(List<ByteBuffer> group) {
                    try {
                        for (ByteBuffer buffer : group) {
                            byte[] chunk =
                                    new byte[buffer.remaining()];
                            buffer.get(chunk);
                            received.write(
                                    chunk, 0, chunk.length);
                        }
                        subscription.get().request(1);
                    } catch (Throwable failure) {
                        problem.compareAndSet(null, failure);
                        subscription.get().cancel();
                        complete.countDown();
                    }
                }

                @Override
                public void onError(Throwable failure) {
                    problem.compareAndSet(null, failure);
                    complete.countDown();
                }

                @Override
                public void onComplete() {
                    complete.countDown();
                }
            });

            if (!complete.await(
                    WAIT_SECONDS, TimeUnit.SECONDS)) {
                Flow.Subscription s = subscription.get();
                if (s != null) {
                    s.cancel();
                }
                throw new TimeoutException(
                        "Response publisher not completed");
            }
            if (problem.get() != null) {
                throw new IOException(
                        "Body failed", problem.get());
            }

            System.out.println(
                    "publisher="
                            + new String(
                                    received.toByteArray(), UTF8));
            System.out.println(
                    "requestsAndBodiesFinished=true");

            // End client usage at the application level.
            // Java 17 has no direct HttpClient close API.
        } finally {
            server.stop(0);
        }
    }
}
~~~

Compile/run commands:

~~~bash
javac AsyncCloseLessonDemo.java
java AsyncCloseLessonDemo
~~~

The program uses the JDK module `jdk.httpserver` (no external dependencies required). With custom module-path configurations, you may need to add `--add-modules jdk.httpserver` to both compile and run commands; on a standard JDK classpath this module is resolved automatically.

**Stdout verified on a compatible JDK via JShell:**

~~~text
first=ONE
second=TWO
stream=STREAM
publisher=PUBLISH
requestsAndBodiesFinished=true
~~~

Explanation:

1. The two `sendAsync(...ofString)` calls run concurrently in terms of the asynchronous API. `allOf` only allows printing the two Strings **after both response futures have completed successfully**.
2. The `InputStream` response already has headers, yet the program enters `try (InputStream ...)` and reads to EOF; even if an exception occurs, the stream is closed.
3. The `Publisher<List<ByteBuffer>>` response is subscribed to once. `onSubscribe` calls `request(1)`; `onNext` reads the `ByteBuffer`s, then issues further demand; `onComplete/onError` signals completion via the latch. On timeout, the code grabs the current subscription and cancels it so the body is not left dangling.
4. The program only uses `ByteArrayOutputStream` because the Publisher body is a fixed 7 bytes. For large production data, use a bounded sink and never accumulate unbounded responses in RAM.
5. `server.stop(0)` stops the loopback server after the sample operations finish. It **does not replace** the Java 21+ `HttpClient` close API and does not turn a Java 17 client into an `AutoCloseable`.

**Demo limitations:** `orTimeout(5s)` applies to the respective `CompletableFuture`; if it times out before the Future completes, it **does not reliably cancel** the underlying exchange. In the demo, endpoints return short bodies and always complete, so the cancellation branch is not triggered. Outside a lab environment, you must store and handle all pending futures, enforce application-level timeouts, cancel/close properly, and avoid letting slow connections hold resources indefinitely. The `InputStream` snippet with `readAllBytes()` does not set an independent timeout for *consuming the body*, so a real service needs a cancel/close plan.

## 9. Java 21+: Complete Program for Bounded Graceful Shutdown

This example requires **JDK 21+** because it uses `HttpClient.shutdown()`, `awaitTermination(Duration)`, and `shutdownNow()`. It creates its own loopback server and sends an HTTP request to `/done`. Because the response uses `BodyHandlers.ofString()`, a successful Future means the String body has already been collected; only then is the client shut down.

Save as **`HttpClientShutdown21Demo.java`**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

public class HttpClientShutdown21Demo {
    private static void reply(HttpExchange ex)
            throws IOException {
        byte[] body = "DONE".getBytes(StandardCharsets.UTF_8);

        try (InputStream ignored = ex.getRequestBody()) {
            ex.sendResponseHeaders(200, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByAddress(
                new byte[] {127, 0, 0, 1});

        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        server.createContext(
                "/done", HttpClientShutdown21Demo::reply);
        server.start();

        HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        try {
            URI uri = URI.create(
                    "http://127.0.0.1:"
                            + server.getAddress().getPort()
                            + "/done");
            HttpRequest req = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            CompletableFuture<HttpResponse<String>> response =
                    client.sendAsync(
                            req,
                            HttpResponse.BodyHandlers.ofString(
                                    StandardCharsets.UTF_8));

            System.out.println(
                    "response="
                            + response.get(
                                    5, TimeUnit.SECONDS).body());
        } finally {
            // Java 21+:
            client.shutdown(); // Accept no new requests.
            boolean stopped =
                    client.awaitTermination(Duration.ofSeconds(5));

            if (!stopped) {
                client.shutdownNow(); // Best-effort only.
                stopped = client.awaitTermination(
                        Duration.ofSeconds(2));
            }

            System.out.println("terminated=" + stopped);
            server.stop(0);
        }
    }
}
~~~

JDK 21+ compile/run commands:

~~~bash
javac HttpClientShutdown21Demo.java
java HttpClientShutdown21Demo
~~~

**Stdout observed in the JDK 24 loopback test environment:**

~~~text
response=DONE
terminated=true
~~~

The `terminated=true` result holds for **that run**: the server replied immediately, the body was already collected, and no streaming body remained outstanding. With a slow server, an unread body, or a stalled task, `awaitTermination` can return `false`, and `shutdownNow` **does not guarantee** that a subsequent wait will return `true`. That is why the code **prints the actual result** instead of asserting shutdown succeeded merely because the method was called.

Concise alternative pattern when all bodies are explicitly handled:

~~~java
// Java 21+ ONLY, suitable when waiting for orderly shutdown is acceptable.
try (HttpClient client = HttpClient.newHttpClient()) {
    // Send requests, wait for processing futures,
    // read to EOF/close InputStream and Stream,
    // subscribe-drain/cancel any Publisher.
} // AutoCloseable.close() is called here and may wait indefinitely.
~~~

**Do not choose between the two APIs blindly:** when a measurable shutdown deadline is needed, use `shutdown + awaitTermination + escalation` instead of unconditional blocking `close()`. When using `try-with-resources`, you must still consume/close all streaming responses inside the block; otherwise, closing the client itself can stall.

## 10. Application-Owned Executor: Shutdown Order

`HttpClient.Builder.executor(Executor)` lets you define an executor for asynchronous/dependent tasks per the contract. If you create your own `ExecutorService` and pass it to the client, you must have a shutdown policy **for your own executor**, separate from the client:

~~~java
// Java 17+ fragment; illustrates ownership only, not a standalone runnable class.
ExecutorService ioExecutor =
        Executors.newFixedThreadPool(4);
HttpClient client =
        HttpClient.newBuilder().executor(ioExecutor).build();

try {
    // Submit request(s) and body handler(s);
    // wait for all related work, handle/cancel streams.
} finally {
    // Shut down only when no operations still need the executor.
    ioExecutor.shutdown();
    if (!ioExecutor.awaitTermination(5, TimeUnit.SECONDS)) {
        ioExecutor.shutdownNow();
    }
}
~~~

**Warning:** calling `ioExecutor.shutdown()` too early **while HTTP exchanges or body subscribers are still running** can prevent tasks needing the executor from executing, causing the pipeline to hang or fail. In Java 17, shutting down the executor **does not mean closing the HttpClient connection pool** (that API does not exist). In Java 21+, you also should not assume `HttpClient.close()` will automatically close an externally owned executor passed in by the application; manage its lifecycle separately.

Do not use a single-threaded executor both to run HTTP callbacks **and to block in `future.get/join()` waiting on those callbacks**, as this risks deadlock/starvation. A shutdown plan must clearly separate HTTP handling tasks, business tasks, queues, callbacks, and waiting threads.

## 11. Cancelling Asynchronous Requests: No Guaranteed Rollback

With `sendAsync`, `CompletableFuture.cancel(true)` on the future returned by the JDK implementation is **an attempt** to cancel the HTTP exchange and reclaim resources. The API does not promise that the request has not left the machine or that the server has not processed it:

~~~java
// Java 17+ fragment, myFuture returned from client.sendAsync(...).
if (!myFuture.isDone()) {
    boolean cancelled = myFuture.cancel(true);
    // cancelled is the Future's status, not confirmation of a server rollback.
}
~~~

According to the Javadoc, for HTTP/1.1 cancellation may close the connection abruptly; for HTTP/2 it may reset the stream, which can also lead to closing the connection in certain situations. If a POST upload already reached the server before cancellation, **the server may already have completed the side effect**. Do not blindly retry payment POSTs, order creation, or data updates without an idempotency key/deduplication or a status API.

### Request Timeout, Future Wait Timeout, and Body Timeout Are Not Identical

| Timeout Source | Meaning | What Is Not Guaranteed |
| --- | --- | --- |
| `HttpClient.Builder.connectTimeout(d)` | Timeout when opening a new connection | Not a deadline for reading the body after connecting |
| `HttpRequest.Builder.timeout(d)` | Timeout of the HTTP exchange per API | For streaming bodies, stream-consuming code may need its own deadline |
| `future.get(d, unit)` | Time a thread waits on the Future | Does not automatically cancel the underlying exchange |
| `future.orTimeout(d, unit)` | Completes this Future exceptionally if not done before deadline | Does not prove the network operation was cancelled |
| `InputStream.read(...)` / `Flow.Subscriber` | Reading/body processing can take time independently | Cannot be replaced by a single header-wait timeout |

If the response body is read on another worker, the shutdown deadline must account for **worker/body completion as well**, not just `responseFuture.isDone()`.

## 12. Application Shutdown Scenario with an Overall Deadline

A large service might define `gracePeriod = 10 s`:

~~~text
T0: receive SIGTERM / stop event
    |
    +-- Set lifecycle = QUIESCING
    +-- Reject / block NEW sendAsync()
    |
    +-- Snapshot activeRequestFutures
    |      - futures needed to receive responses
    |      - bodyCompletionFutures needed to finish processing streams
    |      - processingFutures writing to file/DB/cache
    |
    +-- Wait with ONE overall deadline using a monotonic clock
    |      - do not reset 10 s for each individual stream/client
    |      - at each wait step, use remaining time
    |
    +-- If body is streaming: drain when reasonable;
    |      if expired/abandoning task: close InputStream or cancel Subscription
    |
    +-- Java 21+: client.shutdown() and awaitTermination(remaining)
    |
    +-- If not terminated: cancel pending / shutdownNow()
    |      - mark all requests with uncertain status
    |      - wait bounded follow-up, do not assume completion
    |
    +-- Close owned executors after HTTP no longer needs them
    +-- Update readiness/liveness, metrics, shutdown result
~~~

One way to measure remaining time:

~~~java
// Java 17+ fragment.
long deadlineNanos =
        System.nanoTime() + TimeUnit.SECONDS.toNanos(10);

// At each wait point:
long remainingNanos = deadlineNanos - System.nanoTime();
if (remainingNanos <= 0L) {
    // Overall deadline expired; cancel/close and escalate.
} else {
    // Wait at most remainingNanos; do not grant a fresh 10 s from scratch.
}
~~~

Use `System.nanoTime()` to measure elapsed time rather than wall-clock timestamps that can jump due to clock synchronization. For very large deadlines, account for integer overflow and cap durations appropriately, but a typical short shutdown grace period can be managed simply as shown above.

**Do not equate “remaining wait time equals 0” with “all requests have been processed”.** When the deadline expires, the application must escalate to a stronger shutdown, record unfinished operations, and not report false success.

## 13. How HTTP Streaming Can Hang Client Closing

### 13.1. Forgetting to Close InputStream

~~~java
HttpResponse<InputStream> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofInputStream())
        .join();

// Anti-pattern: neither reading response.body() nor closing it.
// The response Future is done, but the body/network exchange may remain active.
~~~

**Fix:** inside `try-with-resources InputStream`, read to EOF or close when no longer needed. For large responses, use bounded streaming rather than loading everything into RAM.

### 13.2. Forgetting to Subscribe or Not Requesting from Publisher

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.sendAsync(
                request,
                HttpResponse.BodyHandlers.ofPublisher())
        .join();

// Anti-pattern: no body.subscribe(...).
// No subscriber exists to process/cancel the body.
~~~

Or the subscriber has `onSubscribe` but does not call `request(n>0)`, so the body may never emit further. **Fix:** implement a subscriber with proper lifecycle, issue demand, process through `onComplete/onError`, or `cancel()` when giving up.

### 13.3. Closing Client Before Callbacks Can Run

~~~java
// Ordering anti-pattern (Java 21+):
client.shutdown();
executor.shutdownNow();
// A body handler or processing stage still needs that executor!
// awaitTermination may be delayed or fail.
~~~

**Fix:** stop creating new requests; let operations and callbacks using the executor finish or cancel; then shut down the client and executor according to ownership/role. If a custom executor serves multiple subsystems, do not shut it down just because one client no longer needs it.

### 13.4. `allOf` on Response Futures Instead of Body Futures

~~~java
// Anti-pattern:
CompletableFuture.allOf(responseFutures).join();
client.close(); // Java 21+: body Publisher may not have called onComplete yet.
~~~

**Fix:** also track the body completion stage (or close/cancel). With `BodyHandlers.ofPublisher()`, `responseFuture.join()` only returns the publisher to subscribe to; you must continue waiting for the subscriber's own completion signal.

### 13.5. Splitting the Wait Budget Causes Shutdown to Exceed Budget

If a service has 100 requests and each is given 10 s **sequentially**, total wait time can reach 1,000 s. **Fix:** wait concurrently across groups/futures, use a single overall monotonic deadline and remaining time, and then decide on cancellation/escalation.

### 13.6. Waiting Forever for onComplete After Cancelling

Under the Flow contract, `Subscription.cancel()` is not required to emit `onComplete()`. **Fix:** complete application state along the cancelled branch yourself, perform idempotent cleanup, and do not hold a latch waiting for an unguaranteed signal.

## 14. Troubleshooting Guide for Stopping Asynchronous HTTP

| Symptom | Likely Cause | Check / Action |
| --- | --- | --- |
| Java 17: `cannot find symbol: close()` | Using Java 21 API on JDK 17 | Remove `close`/`shutdown` on `HttpClient`; clean up bodies/executors individually; or upgrade JDK |
| Java 17: `HttpClient` cannot be used in `try-with-resources` | Does not implement `AutoCloseable` | Manage as a shared client; do not assume Java 21 APIs |
| Java 21+: `close()` does not return | Unread/unclosed stream, Publisher without request/cancel, stalled callback | Check outstanding bodies, subscribers, executors; switch to a bounded shutdown plan |
| `future.isDone()==true` but socket activity continues | Streaming handler returned response early; business callbacks still running | Track body completion/processing futures |
| `get(timeout)` times out but request still runs | Wait timeout is not cancellation | Cancel future, close/cancel body, or shut down per policy |
| `allOf` fails | One component future failed; other futures may still be active | Inspect each future; do not assume all were cancelled |
| Threads still running after `shutdown()` | Orderly shutdown does not wait; outstanding requests are active | `awaitTermination` with deadline; handle streaming and escalation |
| `awaitTermination()` returns `false` | Not terminated within allowed time | Best-effort `shutdownNow`, log unhandled requests, try bounded follow-up |
| `shutdownNow()` does not stop everything | API does not guarantee immediate stop | Monitor status/metrics and process policy; do not report false termination |
| Java 17 program does not exit due to custom `ExecutorService` | Executor has running non-daemon threads | Wait for required tasks, then `executor.shutdown` and `awaitTermination` |
| `ofPublisher()` response has no `onNext` | Subscriber has not requested `n>0` or did not subscribe | Check `onSubscribe`, demand, cancellation |
| Response truncated when closing `InputStream` early | Intentionally discarded remainder of body | Cancel/close early only when content is not needed; avoid parsing truncated body as success |
| Server receives POST even though future was cancelled | Request was already sent before cancellation | Idempotency key / business state check; do not retry blindly |
| High CPU/RAM during shutdown | Unbounded subscriber buffer, slow callbacks, stalled executor | Bounded queues, max body size, in-flight metrics, queue depth |
| HTTP/1.1 connection not reused after cancel | Cancelling mid-body may close the socket | This may be expected behavior; consider draining when cheap |
| HTTP/2 stream reset after cancel | Stream-level cancellation mechanism | Handle error on the specific request; do not equate with the whole client closing |

### Observing Accurately with Metrics

You should track:

- `activeRequests`: submitted requests that have not yet concluded with success/failure/cancel.
- `activeBodyStreams`: `InputStream`/`Stream`/`Publisher` instances not yet at EOF/terminal/close/cancel.
- `inFlightBytes` and `queuedBytes`: total bytes waiting to be consumed or sent.
- `processingFutures`: response-dependent work (parsing, DB, file, queue).
- `clientLifecycleState`: RUNNING/QUIESCING/DRAINING/SHUTDOWN/TERMINATED.
- `shutdownDuration`, `shutdownGraceExpired`, `forcedCancellationCount`, and `responseBodyAbandonedCount`.
- `statusCode`/error class/timeout/correlation ID, avoiding logging credentials or sensitive raw bodies.

A metric counting only `responseFuture.isDone()` is insufficient to confirm safe shutdown; it must reflect **unfinished bodies** and **downstream business tasks**.

## 15. Self-Check Questions

**Q1.** On Java 17, does `try (HttpClient client = HttpClient.newHttpClient()) { ... }` compile?  
**Answer:** No. Java 17 `HttpClient` does not implement `AutoCloseable`. The `close`/`shutdown` APIs were added in Java 21.

**Q2.** Does Java 21+ `HttpClient.close()` wait for existing requests?  
**Answer:** Yes. It initiates an orderly shutdown and waits for prior operations to complete; if a body stream is unread/unclosed or a publisher has not been requested/cancelled, it can wait a very long time. Do not treat `close()` as bounded by a default timeout.

**Q3.** Does `HttpClient.shutdown()` wait for all requests to finish?  
**Answer:** No. It initiates an orderly shutdown and stops accepting new requests, but returns immediately; use `awaitTermination` or `close` to wait.

**Q4.** Does `awaitTermination(Duration)` returning `false` mean shutdown failed permanently?  
**Answer:** No. It only means the client had not terminated before the timeout; it may finish eventually or require escalation/cancellation. Do not assume it has finished without evidence.

**Q5.** Does `shutdownNow()` guarantee stopping all threads/HTTP exchanges immediately?  
**Answer:** No. It is a best-effort attempt, and the behavior of active operations can be undefined.

**Q6.** Does `sendAsync(...ofString())` succeeding mean the body has been fully received?  
**Answer:** Normally yes, because the `BodyHandler` collects the response into a `String` before the future completes successfully. You still need to check status, content, and processing tasks.

**Q7.** Does `sendAsync(...ofInputStream())` completing mean the entire body has been read?  
**Answer:** No. The response can arrive right after headers. You must read the `InputStream` to EOF or close it if you do not want to continue.

**Q8.** If `ofPublisher()` returns a response but has not been subscribed to yet, can you start Java 21 `close()` and be sure it will not hang?  
**Answer:** No. The body may not have run yet, and orderly closing can be delayed. Subscribe exactly once and request until terminal or cancel.

**Q9.** Is `subscription.cancel()` required to invoke the `onComplete()` callback?  
**Answer:** No. Cancellation is best-effort and does not guarantee a terminal signal; handle the cancelled branch separately.

**Q10.** `CompletableFuture.allOf(first, second)` throws `CompletionException`. Have both requests been cancelled?  
**Answer:** No. One request may have failed while the other is still running. Check each future individually and handle still-active work.

**Q11.** Why can `future.get(5,SECONDS)` throw `TimeoutException` while the HTTP request is still seen on the server?  
**Answer:** Because this timeout only limits the thread waiting on the Future. The request may already have been sent/processed by the server; the timeout itself does not cancel.

**Q12.** When is a separate `processingFuture` needed after the HTTP response?  
**Answer:** When there is still parsing, file saving, DB writing, forwarding data, or asynchronous body processing. Waiting on `responseFuture` does not automatically wait on a separate stage unless it is composed or included in the wait group.

**Q13.** If you supply your own `ExecutorService` to `HttpClient`, can you call `shutdownNow()` on the executor right after submitting the HTTP request?  
**Answer:** You should not. HTTP callbacks/operations may still need it. Wait for or cancel related work first, then shut down the executor according to ownership.

**Q14.** How should `ofLines()` be handled if you do not read all lines?  
**Answer:** Close the returned `Stream<String>`. Like `InputStream`, do not abandon the resource once the response future is done.

**Q15.** Does closing the client guarantee that a POST already executed on the server is rolled back?  
**Answer:** No. The server may already have received and committed the request. Use an idempotency key, correlation ID, or a business status-check API.

**Q16.** Why should a 10-second grace period not be used as an individual timeout for each sequential request?  
**Answer:** Because the total wait time would accumulate. Use a single overall deadline with a monotonic clock and pass remaining time to each wait step.

**Q17.** When should `BodyHandlers.ofFile(path)` be preferred?  
**Answer:** When you want to download a large body to a file without writing a custom subscriber. The handler manages streaming to the file; after the Future succeeds, verify the file result.

**Q18.** If you stop reading the body right at the headers because the server returned 4xx, should you simply discard the `InputStream` without closing it?  
**Answer:** No. If you do not need the error body, close the `InputStream` or cancel the `Subscription` according to the handler; this may affect connection reuse, but avoids leaks.

## 16. Standard References

- Oracle Java SE 17 — `HttpClient`, `sendAsync()`, cancellation; **no close/shutdown yet**: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 21 — `HttpClient implements AutoCloseable`, `close/shutdown/shutdownNow/awaitTermination/isTerminated`, and implementation note on unfinished bodies: https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html
- Oracle Java SE 17 — `HttpResponse.BodyHandlers` and `ofInputStream/ofLines/ofPublisher/ofString/ofFile`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- Oracle Java SE 17 — `HttpResponse.BodySubscribers`, responsibility to read InputStream to EOF/close and subscribe/request/cancel Publisher: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- Oracle Java SE 17 — `HttpResponse.BodySubscriber` and `getBody()` CompletionStage: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html
- Oracle Java SE 17 — `HttpRequest.BodyPublishers`, source of HTTP request bodies: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.BodyPublishers.html
- Oracle Java SE 17 — `CompletableFuture`, `allOf/orTimeout/cancel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
- Oracle Java SE 17 — `Flow.Subscription.request/cancel`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Oracle Java SE 17 — `InputStream` and close: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- Oracle Java SE 17 — `HttpServer` for loopback verification: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html
