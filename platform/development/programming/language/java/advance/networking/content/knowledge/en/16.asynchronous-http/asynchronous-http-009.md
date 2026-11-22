# Future Completion While a Streaming Body Remains Open and Consumer Responsibility

**Topic:** Java Advance - networking  
**Group:** Asynchronous HTTP  
**Core APIs:** Java 17+, **java.net.http.HttpClient.sendAsync(...)**, **HttpResponse.BodyHandlers.ofInputStream()**, **ofLines()**, **ofPublisher()**, **CompletableFuture**, **InputStream**, **Stream<String>**, **Flow.Publisher<List<ByteBuffer>>**.

When using the asynchronous Java HTTP client, a developer can easily assume:

> **sendAsync completing successfully means the HTTP response has been completely read and all network resources have been returned.**

That assumption is **wrong for streaming response bodies**. **CompletableFuture<HttpResponse<InputStream>>** can complete right after the headers are received and an **InputStream** is ready for the caller. Meanwhile, the server may still be sending the rest of the body, the network connection is still transferring bytes, and associated resources may still be held. With **ofLines()** or **ofPublisher()**, the separation between when the response object is received and when the body is fully consumed is similar.

**Core principle:** **future completion only means the HttpResponse<T> value according to the BodyHandler is ready; it does not certify that a streaming body has been fully read, closed, or cancelled.** The recipient of **T** is responsible for completing the rest of the body consumption/cancellation lifecycle. Neglecting that step can hold I/O resources, prevent connections from being reused, create stalled backpressure, or prevent HttpClient shutdown from completing as expected.

This lesson clarifies when the future completes, stream ownership responsibilities, cancellation, errors after the future has completed, backpressure, safe usage patterns, and a **Java 17** example with a loopback server that intentionally holds the body unfinished to verify this accurately.

## 1. Separating Two Moments: Response Ready and Body Ended

Consider the progression of an HTTP response with a long body:

~~~text
Client                                  Server
  |                                       |
  | ------------ HTTP request ---------> |
  |                                       |
  | <----- HTTP status + headers -------- |
  |           (status = 200)              |
  |                                       |
  |  CompletableFuture<HttpResponse<
  |      InputStream>> may complete
  |              │                        |
  |              ▼                        |
  |    response.body(): InputStream       |
  |                                       |
  | <---------- body chunk A ------------ |
  |    read() can return bytes of A       |
  |                                       |
  |       server is still producing data  |
  |            (waiting / slow)           |
  |                                       |
  | <---------- body chunk B ------------ |
  |                                       |
  | <-------- end of response body -------|
  |                                       |
  |    read to EOF / close stream         |
  |    => release associated resources    |
~~~

Suppose a server returns **status 200** and the **Transfer-Encoding: chunked** header for HTTP/1.1, then keeps the connection open while generating chunks. Java can return **HttpResponse<InputStream>** after the headers without waiting for the final chunk. The caller reads **InputStream** as data arrives; if it neither reads nor closes it, response processing at the body level **is still incomplete**.

Distinguish three milestones:

| Milestone | What is available? | What is not guaranteed? |
| --- | --- | --- |
| **Future just created** | CompletableFuture representing sending/receiving the response | Headers, status, and body may not be available yet |
| **Future completes successfully** | HttpResponse<T> is ready per the BodyHandler; status/headers/body object are available | With streaming **T**, the entire body is not necessarily read/closed |
| **Body drained to EOF, completed, or cancelled/closed** | Consumer has finished its responsibility to receive the body per contract | No guarantee a specific connection will definitely be reused; depends on protocol and state |

Do not confuse **future.isDone()** with **inputStream.available()**, **having seen EOF**, **body.close()**, or **having released the socket**. **available()** does not tell you the total remaining body size; it only reflects an estimate of bytes that can be read without blocking per the InputStream contract.

## 2. Java Mechanism: BodyHandler, BodySubscriber, and getBody()

At the Java HTTP client layer, the caller passes a **BodyHandler<T>** to decide how the body will be represented. The client receives status/headers, creates a **BodySubscriber<T>**, forwards received data into the subscriber, and completes the future when the body object **T** is available according to the subscriber's semantics.

**HttpResponse.BodySubscriber<T>.getBody()** returns a **CompletionStage<T>**. When this stage completes depends on the type **T**:

- For **String**, **byte[]**, or data that must be fully collected before producing the final value, the stage usually completes **after the entire body has been processed**.
- For **InputStream**, the stage can complete **before all body bytes have been read**, because the caller needs the InputStream to continue reading.
- For **Stream<String>** or **Flow.Publisher<List<ByteBuffer>>**, the stage can also become ready early so the caller can actively consume parts incrementally.

This is a **contract difference**, not a timing bug or a CompletableFuture bug. With streaming, the **body object** itself is the input to the next processing phase. The rest does not happen automatically just because the caller received HttpResponse.

### Comparing Common BodyHandlers

| BodyHandler | Body type T | When can Future/HttpResponse become ready? | What does the user need to do? |
| --- | --- | --- | --- |
| **ofString()** | String | When the body has been completely accumulated/decoded | Process the String; watch memory for large bodies |
| **ofByteArray()** | byte[] | When the body has been completely accumulated | Process byte[]; limit size to avoid OOM |
| **ofFile(path)** | Path | After the response body has been written to the file per handler | Process Path; clean up file per application lifecycle |
| **discarding()** | Void | After the subscriber has received/discarded content per semantics | No need to manually read InputStream |
| **ofInputStream()** | InputStream | Early, after headers; body may not be fully received yet | **Read to EOF or close** |
| **ofLines()** | Stream<String> | Early, after headers; lines may not have all arrived yet | **Consume to the end or close Stream** |
| **ofPublisher()** | Flow.Publisher<List<ByteBuffer>> | Early, after headers; bytes are still in flight | **Subscribe once, request until terminal signal or cancel** |

**ofFile** still processes the body in a streaming manner in the implementation, but **future<Path>** represents the file having been completely processed, unlike the caller receiving an InputStream and reading chunks after the future completes.

**Do not use ofString() for every large response** if the size is unknown: it may need to hold the entire content in RAM. Conversely, **ofInputStream()** reduces the need to hold the whole body in memory, but shifts lifecycle responsibility from the HTTP client to the consumer.

## 3. ofInputStream(): Future Completes Early, Stream Remains Open

Example:

~~~java
// Snippet: client and request already exist.
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

future.thenAccept(response -> {
    InputStream stream = response.body();
    // At this point status and headers are available.
    // stream may NOT have been completely read yet.
});
~~~

The snippet above is **not safe** because it neither reads nor closes the stream. It illustrates the phenomenon accurately, but does not release the resource. A complete consumer must ensure **read-to-EOF or close** even if parsing/file writing/business operations fail.

The **Java 17 Javadoc** states clearly: **ofInputStream** may return HttpResponse after headers are read, without waiting for the entire body; the caller must **read all the way to EOF** or **call InputStream.close()** if it does not want to continue. Closing early may cause the HTTP connection to be closed and not reused.

### Safe Pattern: try-with-resources

~~~java
// Snippet located where HttpResponse<InputStream> response is available.
try (InputStream in = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = in.read(buffer)) != -1) {
        processBytes(buffer, 0, n);
    }
}
~~~

**processBytes(...)** is a method the application must define itself; this snippet only illustrates resource ownership, not a standalone program. **try-with-resources** guarantees **close()** is called even when processBytes throws an exception. Even if EOF has been reached, close is still a clear way to express that the stream ownership scope has ended.

**Do not call** stream.close() immediately upon receiving HttpResponse if the consumer still needs to read data afterward. The receiving side must clearly define who owns the stream, when the body needs to stay open, and how ownership is transferred.

### Read to EOF or Close Early?

Both approaches **fulfill resource responsibility**, but have trade-offs:

- **Read to EOF**: usually allows the HTTP client to finish processing the response body completely and creates conditions for connection reuse; it still must adhere to the protocol and all connection states.
- **Close early** when data is no longer needed: releases the consumer's responsibility; depending on HTTP/1.1, HTTP/2, and the provider, closing/cancelling may cause the connection to close, the stream to reset, or prevent reuse.
- **Do nothing**: the most dangerous. The body remains unconsumed/uncancelled; the request may stay stuck, connection/pool slots may remain held, and shutdown may fail to finish.

Do not write **readAllBytes()** unconditionally to "drain the stream" when the response can be very large or an infinite stream: that can exhaust RAM and hang for a long time. Use bounded buffers, byte/time limits, safe decompression, and cancel if no longer needed.

## 4. ofLines(): Stream<String> Is Also a Resource That Must Be Closed

**HttpResponse.BodyHandlers.ofLines()** returns a body of type **Stream<String>**. This is not an ordinary java.util.stream.Stream reading from an already-materialized collection: it **is backed by an in-flight response body**, so iterating the stream may block waiting for new bytes from the network.

~~~java
// Snippet: client and request already exist.
CompletableFuture<HttpResponse<Stream<String>>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofLines());

future.thenAccept(response -> {
    try (Stream<String> lines = response.body()) {
        lines.forEach(line -> {
            System.out.println(line);
        });
    }
});
~~~

**try-with-resources** on the Stream is essential. If you call **limit(10)** to inspect only 10 lines, the terminal operation **does not read the entire body**; after 10 lines, closing the Stream is mandatory. If the stream fails during traversal, close must still run.

~~~java
// Wrong: take 3 lines and forget to close the Stream.
response.body().limit(3).forEach(System.out::println);
// The response may still have countless unreceived lines.
~~~

**Right:**

~~~java
try (Stream<String> lines = response.body()) {
    lines.limit(3).forEach(System.out::println);
} // closes even though only three lines were taken.
~~~

**Encoding:** ofLines() determines the charset from Content-Type information as specified in the Javadoc, and lines follow BufferedReader semantics. An unusually long line of text can increase memory usage; limit line length and total line count for untrusted data. **onClose on Stream** must not be used in place of the body closing contract; call **Stream.close()** via try-with-resources.

## 5. ofPublisher(): Subscribe Once, Request or Cancel

**HttpResponse.BodyHandlers.ofPublisher()** returns:

~~~java
Flow.Publisher<List<ByteBuffer>>
~~~

The future can complete as soon as headers are available, but **body bytes are delivered when the subscriber subscribes and requests data**. The caller owns the obligation to **subscribe exactly once** and manage the **Flow.Subscription** lifecycle.

Important rules from **BodySubscribers.ofPublisher()**:

1. The Publisher returned from a response **allows only one subscriber**. A subsequent subscribe receives an empty subscription and an **onError(IllegalStateException)** signal.
2. The Subscriber must retain the **Flow.Subscription** when **onSubscribe(subscription)** is called.
3. Call **subscription.request(n)** with **n > 0** to signal demand. Not requesting data can stall the source due to backpressure.
4. On **onNext(List<ByteBuffer>)**, process the buffers in order. Do not assume one callback corresponds to one HTTP packet, one message, or a single buffer.
5. If you want to receive the entire body, keep requesting until **onComplete** or **onError** is received.
6. If aborting early, call **subscription.cancel()**. Simply dropping the Publisher reference or having the subscriber stop requesting does **not** replace cancellation.

~~~text
HttpResponse<Publisher> returned
        |
        v
subscribe(new Flow.Subscriber<>())
        |
        v
onSubscribe(subscription)
        |
        +-- request(1) --> onNext(List<ByteBuffer>)
        |                      |
        |                      +-- process + request(1) --> ...
        |
        +-- when no longer wanting data --> cancel()
        |
        +-- at end of body --> onComplete()
        |
        +-- on failure --> onError(Throwable)
~~~

**There is no standard Publisher.close()** on Flow.Publisher. The mechanism to release consumption rights is **subscription.cancel()**; when consuming to the end, **onComplete** or **onError** is the terminal signal.

### Minimal Demand-Driven Subscriber Example

~~~java
// Snippet: publisher has type Flow.Publisher<List<ByteBuffer>>.
publisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    private Flow.Subscription subscription;
    private long bytes;

    @Override
    public void onSubscribe(Flow.Subscription s) {
        subscription = s;
        s.request(1);
    }

    @Override
    public void onNext(List<ByteBuffer> buffers) {
        for (ByteBuffer buffer : buffers) {
            bytes += buffer.remaining();
            // Must actually process or copy data before requesting more.
            buffer.position(buffer.limit());
        }
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Body failed: " + error);
    }

    @Override
    public void onComplete() {
        System.out.println("Body finished, bytes=" + bytes);
    }
});
~~~

This is a **snippet**; the **publisher** variable and imports for **java.util.concurrent.Flow**, **java.nio.ByteBuffer**, and **java.util.List** must exist in scope. The snippet uses **position(limit)** only to show consumption without retaining content; real applications need to copy/transfer data per protocol, handle backpressure, and enforce size limits. For a subscriber that may stop early, add a branch calling **subscription.cancel()** instead of continuing to request.

**Do not perform unbounded slow work directly inside onNext** if the implementation's callback runs on an event/client thread. For large pipelines, hand off data to a bounded queue/worker with backpressure, and ensure you do not request unboundedly before the worker finishes consuming.

## 6. Future Success Is Not Consumer Completion

Compare three futures with the same URL but different BodyHandlers:

~~~java
CompletableFuture<HttpResponse<String>> a =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());

CompletableFuture<HttpResponse<InputStream>> b =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<HttpResponse<Flow.Publisher<List<ByteBuffer>>>> c =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofPublisher());
~~~

**a** typically completes when the string body has finished accumulating; **b** and **c** can complete after headers while the body continues. These are three independent requests in the snippet, not three free ways to "view the same response".

**Flawed mental model:**

~~~text
Future completed successfully
    -> HTTP status = 200
    -> mark job completed
    -> forget InputStream
    -> network body still open / transport resources still held
~~~

**Proper design has two distinct stages/ownerships:**

~~~text
Stage A: acquire response (headers + streaming body handle)
    -> CompletableFuture<HttpResponse<InputStream>>

Stage B: consume or close body
    -> separate CompletableFuture<Result> managed by the application
    -> completes when reading/parsing/writing/verifying finishes,
       or fails/cancels and has cleaned up
~~~

For an API where the caller only needs the complete content, return a **CompletableFuture<Result>** that already encompasses phase B instead of handing out an InputStream without clear ownership. Conversely, if the API is a streaming API, return the **body handle** and require the consumer to close/cancel per contract.

### After the Future Succeeds, Reading Can Still Fail

A server can send status 200 + headers, causing the ofInputStream future to complete, and then abruptly close TCP mid-body. When **in.read(...)** runs afterward, the caller can receive an **IOException**, EOF/truncated body, or protocol decoding error. **The CompletableFuture<HttpResponse<InputStream>> that already completed successfully will not flip back to exceptional** because a later read fails.

Similarly:

- **Stream<String>** can fail while iterating/decoding.
- **Flow.Publisher** can emit **onError** after the outer future has completed.
- JSON/application protocol parse errors can arise when the consumer processes the final bytes; that is a **consumer-stage error**, not something to ignore because the outer future succeeded.

Record the **status/header stage** and the **body-consumption stage** separately when accurate observability is needed.

## 7. Complete Java 17+ Program: Proving the Future Is Done While the Body Is Unfinished

This demo uses **HttpServer** on **127.0.0.1** and **java.net.http.HttpClient**. The server has a **/held** endpoint whose response body is split into two parts:

1. The server sends headers + the first chunk **alpha**, then flushes.
2. The server **waits on a CountDownLatch** without sending the final chunk.
3. The client's **sendAsync(... ofInputStream())** obtains HttpResponse while the server is waiting.
4. The client prints **futureDoneBeforeBodyEOF=true** and **serverBodyEndedBeforeRelease=false** to prove the two lifecycles are independent.
5. The client reads the first chunk, opens the latch so the server sends **omega**, then reads to EOF and closes the InputStream.
6. The demo also checks **ofLines()**, **ofPublisher()** with demand, and **ofString()**.

Using CountDownLatch **deterministically** confirms that the future completed before the body finished; it does not rely on sleep or a hard-to-reproduce race. Using port 0 lets the OS assign an actual port, requiring no Internet access.

### Source Code: AsyncBodyOwnershipDemo.java

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
import java.util.stream.Stream;

public class AsyncBodyOwnershipDemo {
    private static final CountDownLatch allowLastChunk = new CountDownLatch(1);
    private static final CountDownLatch serverBodyEnded = new CountDownLatch(1);

    private static void heldBody(HttpExchange exchange) throws IOException {
        try (exchange) {
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=utf-8");
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write("alpha\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                try {
                    if (!allowLastChunk.await(5, TimeUnit.SECONDS)) {
                        throw new IOException("Consumer did not release the last chunk");
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Server interrupted", e);
                }
                out.write("omega\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
            }
        } finally {
            serverBodyEnded.countDown();
        }
    }

    private static void fixedBody(HttpExchange exchange, String content)
            throws IOException {
        try (exchange) {
            byte[] bytes = content.getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.createContext("/held", AsyncBodyOwnershipDemo::heldBody);
        server.createContext("/lines", e -> fixedBody(e, "one\ntwo\n"));
        server.createContext("/publisher", e -> fixedBody(e, "DATA"));
        server.createContext("/string", e -> fixedBody(e, "DONE"));
        server.start();
        try {
            URI base = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/");
            HttpClient client = HttpClient.newHttpClient();

            HttpRequest heldRequest = HttpRequest.newBuilder(
                    base.resolve("held"))
                    .timeout(Duration.ofSeconds(8)).GET().build();
            CompletableFuture<HttpResponse<InputStream>> firstFuture =
                    client.sendAsync(heldRequest,
                            HttpResponse.BodyHandlers.ofInputStream());
            HttpResponse<InputStream> first =
                    firstFuture.get(5, TimeUnit.SECONDS);

            System.out.println("status=" + first.statusCode());
            System.out.println("futureDoneBeforeBodyEOF=" +
                    firstFuture.isDone());
            System.out.println("serverBodyEndedBeforeRelease=" +
                    (serverBodyEnded.getCount() == 0));

            try (InputStream stream = first.body()) {
                byte[] prefix = stream.readNBytes(6);
                System.out.println("first=" +
                        new String(prefix, StandardCharsets.UTF_8).trim());

                allowLastChunk.countDown();
                byte[] suffix = stream.readAllBytes();
                System.out.println("remaining=" +
                        new String(suffix, StandardCharsets.UTF_8).trim());
            } finally {
                allowLastChunk.countDown();
            }

            if (!serverBodyEnded.await(5, TimeUnit.SECONDS)) {
                throw new IOException("Server stream did not close");
            }
            System.out.println("serverBodyEndedAfterRead=true");

            HttpRequest linesRequest = HttpRequest.newBuilder(
                    base.resolve("lines")).GET().build();
            HttpResponse<Stream<String>> linesResponse = client.sendAsync(
                    linesRequest, HttpResponse.BodyHandlers.ofLines()).join();
            try (Stream<String> lines = linesResponse.body()) {
                System.out.println("lines=" +
                        String.join("|", lines.toList()));
            }

            HttpRequest pubRequest = HttpRequest.newBuilder(
                    base.resolve("publisher")).GET().build();
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> pubResponse =
                    client.sendAsync(pubRequest,
                            HttpResponse.BodyHandlers.ofPublisher()).join();
            CompletableFuture<String> consumed = new CompletableFuture<>();
            ByteArrayOutputStream collected = new ByteArrayOutputStream();

            pubResponse.body().subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1);
                }

                @Override
                public void onNext(List<ByteBuffer> buffers) {
                    for (ByteBuffer buffer : buffers) {
                        byte[] bytes = new byte[buffer.remaining()];
                        buffer.get(bytes);
                        collected.writeBytes(bytes);
                    }
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    consumed.completeExceptionally(error);
                }

                @Override
                public void onComplete() {
                    consumed.complete(
                            collected.toString(StandardCharsets.UTF_8));
                }
            });
            System.out.println("publisherBody=" +
                    consumed.get(5, TimeUnit.SECONDS));

            HttpResponse<String> textResponse = client.sendAsync(
                    HttpRequest.newBuilder(base.resolve("string"))
                            .GET().build(),
                    HttpResponse.BodyHandlers.ofString()).join();
            System.out.println("stringBody=" + textResponse.body());
        } finally {
            allowLastChunk.countDown();
            server.stop(0);
        }
    }
}
~~~

### Compile and Run

Requires **JDK 17+** with the standard **jdk.httpserver** module. Create **AsyncBodyOwnershipDemo.java** with the exact content above in a temporary directory to practice:

~~~bash
javac --release 17 -encoding UTF-8 AsyncBodyOwnershipDemo.java
java AsyncBodyOwnershipDemo
~~~

**Verified stdout from compiling with --release 17 and running on JDK 24:**

~~~text
status=200
futureDoneBeforeBodyEOF=true
serverBodyEndedBeforeRelease=false
first=alpha
remaining=omega
serverBodyEndedAfterRead=true
lines=one|two
publisherBody=DATA
stringBody=DONE
~~~

### Explaining the Demo's Evidence

- **status=200**: headers were read by the client and HttpResponse is ready.
- **futureDoneBeforeBodyEOF=true**: the future providing the response has completed.
- **serverBodyEndedBeforeRelease=false**: the server has not ended the body; it is waiting on the client's latch. Because the latch has not opened, you cannot mistakenly assume the body is complete just by looking at status.
- **first=alpha**: the client reads the first part of the data from InputStream while the stream is still open.
- **remaining=omega**: after opening the latch, the client receives the remainder, reads to EOF, and closes the stream.
- **serverBodyEndedAfterRead=true**: the server has closed the body per the demo flow.
- **lines=one|two**: Stream<String> was consumed to the end inside try-with-resources.
- **publisherBody=DATA**: the subscriber subscribed, requested in batches, received onNext and onComplete.
- **stringBody=DONE**: contrasted with BodyHandlers.ofString(), which returns a complete String.

The demo does **not** claim every streaming body always has remaining bytes when the future completes: a very short body may already have finished by that moment. What matters is that **the Java API allows the future to complete before the body ends**; the program uses a latch to prove this in a deterministic scenario.

**Why isn't HttpClient in try-with-resources?** The HttpClient API in Java 17 does **not yet** extend AutoCloseable; HttpClient closing APIs (close/shutdown/awaitTermination) were added in **Java 21**. Code compiled with --release 17 must maintain compatibility; production Java 21+ can use client.close() at app shutdown, but **closing the client does not replace the responsibility to release streaming bodies**.

**Caution:** In the demo, **readAllBytes()** is safe because the server sends only one small final chunk. Do not copy this pattern for long or unbounded downloads/streams.

## 8. Designing a Responsible Asynchronous Pipeline: A Dedicated Body-Reading Stage

A common but incorrect pattern:

~~~java
CompletableFuture<Void> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream())
                .thenAccept(response -> {
                    System.out.println("status=" + response.statusCode());
                    // FORGOT response.body(): neither read nor closed.
                });
~~~

**thenAccept** finishes, but network resources may still be held. A CompletableFuture<Void> variable created by thenAccept also completes, without causing the stream to clean itself up.

### Correct Pattern: Processing the Body in an Ownership-Aware Stage

~~~java
// Snippet: client/request/ioExecutor already created.
// ioExecutor should be an ExecutorService with bounded threads/queue.
CompletableFuture<Long> consumed =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofInputStream())
        .thenApplyAsync(response -> {
            try (InputStream in = response.body()) {
                long total = 0;
                byte[] buffer = new byte[8192];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    total += n;
                    if (total > 10_000_000L) {
                        throw new IOException("Response exceeds size limit");
                    }
                    // Process chunk here, without holding the entire body in RAM.
                }
                return total;
            } catch (IOException e) {
                throw new java.io.UncheckedIOException(e);
            }
        }, ioExecutor);
~~~

This is a **non-standalone snippet**: it needs imports, the **ioExecutor**, **client**, and **request** variables, and the application's resource-limiting policy. It shows:

1. The **outer future** completes when the response/InputStream is ready.
2. **thenApplyAsync** offloads **blocking read** work to an application-managed executor, avoiding heavy work on the network callback.
3. **try-with-resources** ensures the stream closes even if parsing/IO fails.
4. **consumed** represents the result of **having finished reading the body or cleaned up after an error**, not merely receiving headers.
5. **UncheckedIOException** preserves the body-read cause for the caller to classify; handle **CompletionException** when joining.

**Important:** **thenApplyAsync** is not an automatic backpressure control mechanism. If the executor has an unbounded queue and many response streams wait to be read, you can still exhaust resources. Use bounded worker/queue counts, per-host quotas, timeouts, and cancellation policies.

### Who Owns InputStream When the Stage Fails Before Running?

This is a tricky corner case: if a pipeline uses an executor and the task **is rejected/cancelled** after HttpResponse is available but **before handing the stream into try-with-resources**, the resource may never be closed. Production design must define the handoff clearly:

- The callback receiving HttpResponse must own the handle immediately and **guarantee** a consumer will take over.
- If the consumer cannot be scheduled, **close the stream immediately** in the failure branch.
- After a successful handoff, only one owner is responsible for closing.
- Avoid letting both sides arbitrarily read/close without a synchronization policy.
- Ensure executor shutdown does not abandon open response bodies.

A simple approach for small workloads is to process the body in a method with clear ownership and call it directly from an application-controlled worker; for large workloads, build a stream manager with a registry of active bodies and cleanup on shutdown.

## 9. Cancellation: Cancelling a Future Differs from Closing an Already-Received Stream

**CompletableFuture.cancel(true)** on the default HttpClient can request cancellation of the HTTP exchange **while the future has not yet completed**. The Javadoc does not promise immediate cancellation, and the request may already have been sent / the server may have started processing. Transport behavior depends on the HTTP version (HTTP/1.1 may close the connection, HTTP/2 may reset the stream).

**After the future has completed** with **HttpResponse<InputStream>**, calling **cancel(true)** on **that same future** usually has no cancellation effect: CompletableFuture is already in a terminal state and cannot revert completion to cancellation. **To stop the body, close the InputStream**, or for a publisher, call **subscription.cancel()**.

~~~text
Future still pending:
    cancel(true) -> attempt to cancel HTTP exchange
                    (best effort; does not mean server rollback)

Future already succeeded -> HttpResponse<InputStream>:
    future.cancel(true) does not replace body.close()
    caller must read to EOF or close InputStream

Future already succeeded -> HttpResponse<Publisher>:
    future.cancel(true) does not replace subscription.cancel()
    caller must subscribe and drain to terminal or cancel
~~~

### Cancellation Rules by Timing

| Timing | What needs to be managed? | Correct action |
| --- | --- | --- |
| Before sending | Request not yet submitted | Do not send; release input data if owned by caller |
| After sendAsync, before future completes | HTTP exchange in progress | May call cancel(true), understanding it is best-effort |
| Future already has HttpResponse<InputStream> | Streaming body open | Close body stream or read to EOF |
| Future already has HttpResponse<Stream<String>> | Line-backed stream open | Close Stream or consume to the end |
| Future already has HttpResponse<Publisher> | Subscription not yet received/completed | Subscribe once, request to terminal or cancel |
| Body completely read/cancelled | Resource lifecycle ended per contract | Verify no abandoned references/workers remain |

### Timeout Does Not Automatically Turn the Future into a Body-Consumption Deadline

**HttpRequest.Builder.timeout(Duration)** is the request limit per the API; with a streaming BodyHandler, the future can complete early while body reading is still waiting. Therefore, do **not** assume **future.orTimeout(...)** after headers are ready will automatically terminate all subsequent read operations. If the body needs its own deadline/idle timeout, the application must design monitoring and actively **close/cancel the body** when overdue.

For example, a service returns headers and opens a long-lived event stream: that can be valid protocol behavior, not a "failed" HTTP request just because the body has not ended. The consumer needs a policy for when to keep waiting and when to exit.

## 10. Flow.Publisher: Full Consumption, Early Cancellation, and Backpressure

Unlike blocking InputStream, **Flow.Publisher** follows the **Reactive Streams** model, receiving demand via **Flow.Subscription.request(n)**. This mechanism fits pipelines that consume batches of **List<ByteBuffer>**.

### Why Subscribing Without Requesting Is Not Enough

~~~java
publisher.subscribe(new Flow.Subscriber<>() {
    @Override
    public void onSubscribe(Flow.Subscription s) {
        // BUG: no s.request(...)
    }

    @Override
    public void onNext(List<ByteBuffer> buffers) {
        // Not called if there is no demand.
    }

    @Override public void onError(Throwable error) {}
    @Override public void onComplete() {}
});
~~~

A subscriber that has not generated demand can cause upstream **to send no further data**, even while the server and connection remain active. If the whole pipeline waits on each other, resources can be held for a very long time. If the consumer does not want data, call **s.cancel()**; if it wants data, call **s.request(n)** with a reasonable bound.

### Cancelling After Receiving Some Chunks

~~~java
// Snippet: cancel once the desired threshold is reached.
@Override
public void onNext(List<ByteBuffer> chunks) {
    for (ByteBuffer buf : chunks) {
        processed += buf.remaining();
        consume(buf);
    }
    if (processed >= byteLimit) {
        subscription.cancel();
    } else {
        subscription.request(1);
    }
}
~~~

This is a **snippet** using application-defined variables/methods. Calling cancel does not guarantee receiving onComplete: after cancel, upstream may not invoke onComplete; the caller should complete its **consumer-level CompletableFuture** in the **cancelled/early-stop** state as required.

**Do not hold onto a ByteBuffer from onNext indefinitely** assuming its content never changes: if needed after the callback, copy the data according to your memory-management and ownership strategy. Avoid copying an entire large response into a ByteArrayOutputStream in production without a size limit. The demo only collects 4 bytes for easy observation.

### A Subscriber Can Separate Body Completion

~~~text
responseFuture: CompletableFuture<HttpResponse<Publisher>>
   └─ completes when headers and Publisher are ready

bodyDone: CompletableFuture<Result>
   ├─ completes when onComplete + final parse succeed
   ├─ completes exceptionally on onError/parse failure
   └─ cancelled/early-stop after subscription.cancel() per policy
~~~

Merely calling **responseFuture.thenAccept(response -> response.body().subscribe(...))** without returning/observing **bodyDone** makes the upper calling layer see "completion" before the actual body is consumed. Maintain bodyDone separately and expose it outward when the final result is needed.

## 11. Errors After Future Completion Must Be Handled Separately

An HTTP response can have status 200 and a completed future, yet during body consumption still produce:

- **IOException** when InputStream reads from a reset/closed network connection or a corrupted body.
- **UncheckedIOException/exception** when iterating Stream<String> or when a decoder encounters malformed data depending on the handler.
- **Flow.Subscriber.onError** when the publisher encounters a network/protocol/cancellation error.
- **ParseException, IllegalArgumentException, JSON decoding error** when the consumer parses the body, even though transport succeeded.
- **Size limit exceeded** when the consumer detects the body exceeds the limit.
- **Checksum mismatch** when the application requires end-to-end integrity independent of HTTP/TLS.
- **Application timeout** when the stream stops emitting new data for too long.
- **Disk I/O failure** when writing a download from InputStream to a file.

**Do not record the metric request_success=true as soon as responseFuture completes** if business success requires the full body. At minimum, separate:

~~~text
http_response_ready=true
http_status=200
response_future_completed=true
body_state=READING
body_bytes_received=...
body_result=PENDING
connection_state=not_asserted
~~~

When the body finishes:

~~~text
http_response_ready=true
http_status=200
response_future_completed=true
body_state=EOF_AND_CLOSED
body_bytes_received=...
body_result=SUCCESS
~~~

Or:

~~~text
http_response_ready=true
http_status=200
response_future_completed=true
body_state=CLOSED_EARLY
body_result=CANCELLED_BY_CONSUMER
reason=size_limit
~~~

An **HttpResponse.statusCode() == 200** also does not prove the JSON body parsed validly or that the business operation succeeded. Define success by the application's contract, not by the state of an intermediate future.

## 12. When to Close Early and the Impact on Connection Pooling

The Java HTTP client can reuse a connection for other requests if still eligible, but a streaming body may be occupying network resources.

**Read to EOF** is a good approach if you genuinely need the content and the body is bounded. It usually helps the client finish the response cleanly, enabling connection reuse.

**Close early** is the right approach when the caller wants to reject/abort the body, for example:

- The response has a **Content-Type** that violates the contract.
- The **Content-Length** header exceeds the limit (still protect against missing/incorrect headers).
- Only the first few bytes are needed to decide, without downloading the rest.
- The user cancels the file download.
- The job times out or the parent request is cancelled.
- The parser reports corrupted data and cannot continue.

However, **close() before EOF may cause an HTTP/1.1 connection to close or not be reused**; with multiplexed protocols such as HTTP/2, cancelling a stream may have different mechanics. **Do not** promise socket reuse after an early close. Nor should you try to read unnecessary gigabytes just to keep keep-alive if doing so harms bandwidth/RAM/latency.

### Why Are Resource Leaks Hard to Spot in Small Tests?

A program that sends one request and exits may not expose the issue. In a long-running server, hundreds of abandoned streaming bodies can cause:

- Rising **active connections** or stream counts.
- Connection pool having no usable slots even though future counts have dropped.
- Memory retaining buffers/callback references.
- Too many threads blocked on read.
- Prolonged backpressure between client and server.
- **HttpClient.close()** in Java 21+ waiting very long or failing to complete because of undrained/uncancelled streams.

According to the **Java 21+ HttpClient Javadoc**, orderly shutdown of the client requires submitted requests to run to completion. If the caller does not close/cancel/drain streaming bodies, shutdown may not complete as expected. **Closing HttpClient is not a substitute for closing body streams**.

## 13. Stream Ownership Across Multiple Services/Layers

Suppose Service A calls the HTTP client and returns InputStream to Service B:

~~~text
Service A
  -> HttpClient.sendAsync(... ofInputStream())
  -> HttpResponse<InputStream>
  -> returns InputStream to Service B
                              |
                              +-- Who must close?
                              +-- When A times out?
                              +-- When B is cancelled?
                              +-- When the response body is too large?
~~~

If A closes immediately when the method returns, B will not be able to read. If A does not close and B forgets to close, a leak occurs. One of the following contracts is needed:

1. **A owns and consumes:** A reads the body within its scope, parses/writes, and returns **CompletableFuture<Result>**; A is responsible for closing.
2. **Ownership transfer:** A returns an explicit **streaming handle** to B, documents that **B must close/cancel**, and A ensures cleanup if handoff fails.
3. **Structured streaming:** A returns a Publisher or abstraction with cancellation, backpressure, deadline, and lifecycle managed by a pipeline manager.
4. **No stream needed:** if the body is small and bounded, use **ofString/ofByteArray** to avoid transferring ownership of a live resource.

**One resource, one owner at any given time** is a sound principle. Which side holds ultimate responsibility must be expressed in the API contract, code reviews, and tests. Do not hide an InputStream inside a response record where users assume all data is already materialized.

## 14. Common Mistakes in Asynchronous Code

| Anti-pattern | Consequence | How to fix |
| --- | --- | --- |
| **future.isDone() = true** so ignore the body | Response body stays open, resource leak | Read to EOF or close/cancel |
| **thenAccept(HttpResponse::statusCode)** without reading stream | HTTP request remains outstanding at the body layer | Build a consumer with clear ownership |
| **future.cancel(true)** after successful completion | Does not cancel the already-delivered InputStream | Close InputStream or cancel subscription |
| **ofLines().limit(3)** without closing | Stops early while stream stays open | try-with-resources for Stream |
| **ofPublisher()** without subscribing | Body bytes are never consumed | Subscribe once and request/cancel |
| Subscribing twice to publisher | Second call gets onError(IllegalStateException) | Only one subscriber |
| Subscriber never requests | Backpressure stalls the pipeline | request(n) or cancel |
| Subscriber aborts mid-way without cancelling | Exchange may remain unfinished | subscription.cancel() |
| **readAllBytes()** for unbounded bodies | Risk of OOM or infinite wait | Bounded chunk processing, byte/deadline limits |
| Not closing on parse failure | Exception branch leak | try-with-resources and finally |
| Reading body on uncontrolled callback thread | Blocks network/executor, starvation | Use a bounded worker executor |
| Seeing 200 and treating business job as done | Body may still fail or be incomplete | Separate BodyDone/parseDone future |
| Closing InputStream before handoff | Consumer encounters an already-closed stream | Define ownership transfer |
| Only calling close on HttpClient at shutdown | Shutdown may hang on open streams | Close/drain/cancel each body |
| Trusting Content-Length absolutely | Server may still send errors/malformed data | Enforce limit on actual bytes read |
| Lumping body failure into HTTP 500 | Misclassifies transport vs consumer errors | Log exception/cause separately |
| Reading body arbitrarily from multiple threads | Races on position/state/close | Single reader or protocol-level synchronization |

## 15. Designing Timeouts, Cancellation, and Long-Lived Streams

### Do Not Conflate Response Timeout and Body Idle Timeout

A streaming request such as **Server-Sent Events (SSE)**, log streaming, long data downloads, or media may be intended to stay open for minutes or hours. The future providing **InputStream/Publisher** can complete early; the body not reaching EOF is not necessarily an error. The application itself must manage **heartbeats, idle timeouts, cancellation, max duration, and maximum bytes**.

A policy might include:

| Threshold | Example | Action when exceeded |
| --- | --- | --- |
| **Connect timeout** | 3 seconds | Cancel attempt / fail with exception |
| **Response headers deadline** | 5 seconds | Time out request if no response yet |
| **Body idle timeout** | 30 seconds with no bytes | Close/cancel body per API contract |
| **Maximum body duration** | 10 minutes for a bounded job | Stop, clean up, report timeout |
| **Max body bytes** | 20 MiB | Reject/close when exceeded; even if Content-Length is missing |
| **Max active streams** | 100 per service | Appropriate backpressure/queue/reject |

The numbers above are **illustrative only**, not Java API defaults. **HttpClient.Builder.connectTimeout()** and **HttpRequest.Builder.timeout()** have their own semantics; do not assume they enforce a **body idle timeout** in all streaming cases. When an application deadline expires, the owner must actively manage close/cancel and completion of the consumer-level future.

### Caution When Cancelling from Another Thread

If one thread is blocking in **InputStream.read()** and another thread calls **close()**, the exact reaction depends on the implementation/transport; code must handle IOException/cancellation and close exactly once. In the default JDK client, some interrupts during a blocking read can cause the request to be cancelled and the stream closed. **Do not** rely on an exact exception message or socket release timing across all JDK/HTTP versions.

If using Publisher, keep the Subscription reference in thread-safe state for external cancellation. Call **cancel()** when no longer receiving, and complete the consumer-level future appropriately; do not wait on onComplete after cancel as a guarantee.

## 16. Tests Needed Before Deployment

| Scenario | How to simulate | What to verify |
| --- | --- | --- |
| Headers arrive before body end | Use CountDownLatch on server as in demo | responseFuture completes while server still holds final chunk |
| Very small body | Server returns 1–2 bytes then ends | Consumer still closes/drains properly |
| Large body | Stream MB/GB in a controlled manner | Does not buffer all in RAM unnecessarily |
| Infinite/slow body | Server keeps stream open | Application deadline/cancel triggers when needed |
| Early close | Read only prefix then close | No resource retention; do not assume keep-alive reuse |
| Parser throws exception | Consumer throws mid-read loop | finally/try-with-resources still closes |
| Publisher demand=0 | Subscriber does not request | Does not hang forever when app decides to cancel |
| Publisher cancel | Reach byte limit then cancel | Does not require onComplete to release |
| Publisher second subscribe | Subscribe twice to one body publisher | Second attempt receives error per contract |
| Body I/O failure after future completes | Server aborts mid-body | Future success does not mask read/onError failure |
| Caller cancels before future done | Cancel sendAsync future | Best-effort cancellation, no false guarantee |
| Caller cancels after future done | Cancel future then check body ownership | Must still close body |
| Executor rejects task | Saturate bounded executor | Stream is closed if consumer handoff fails |
| Client shutdown with open stream | Open body without consuming | Shutdown may block; clean up stream first |

**Do not rely on Thread.sleep to "prove the future completed before the body".** Sleep can vary with scheduling/CPU. Use **CountDownLatch** or a barrier so the server holds the response body until the client has observed the completed future.

### Tips for Testing Publisher

Use a **Flow.Subscriber** that records the counts of **onSubscribe**, **onNext**, **onComplete**, **onError**, and **cancel**. Write assertions to guarantee **only one** terminal signal on the normal completion path, no data requests after terminal, and no retained subscription after consumer cancellation.

For large HTTP responses, use bounded buffers to test backpressure: the subscriber only requests more after the previous chunk has been processed. This creates a testable contract instead of relying on socket buffer sizes or random delays.

## 17. Operational Observability: Two Different Dimensions of Completion

In a real service, separate metrics should be tracked:

~~~text
HTTP response stage:
  request_started
  response_headers_received
  response_future_completed
  http_status

Streaming body stage:
  response_body_open
  response_body_bytes_received
  response_body_eof
  response_body_close
  response_body_cancel
  response_body_error
  active_stream_count
  body_lifetime_ms
~~~

A system with many **response_future_completed** events but very few **response_body_close** events may have **resource leaks**, or it may be an intentional long-lived streaming application; correlate with **active stream count**, stream age, and cancellation policy.

Do not log raw bodies containing sensitive information. When debugging incidents, log **request/trace ID, redacted endpoint if it contains personal data, status, body handler type, open/close/cancel events, duration, bytes**. If HTTP status is 200 but reading the body fails, record the HTTP response stage and the body failure stage separately.

### Avoid Wrong Optimizations

- Increasing the number of HTTP connections does not fix logic that forgets to close bodies.
- Adding worker threads does not replace backpressure and bounded queues.
- Disabling timeouts to "let streams live forever" is inappropriate for non-infinite-streaming APIs.
- Using ofByteArray to avoid closing may turn a socket leak into an **OOM**.
- Using a body stream but immediately calling readAllBytes can lose all streaming benefits.

## 18. Self-Check Exercises

1. Why can **CompletableFuture<HttpResponse<InputStream>>** complete when the server has not yet sent the final chunk? What in the BodySubscriber contract produces this behavior?
2. Compare **ofString()** with **ofInputStream()** regarding future completion time, memory, and ownership.
3. A client uses **thenAccept(response -> log(status))** and never touches InputStream. What can happen to request completion and the connection pool?
4. A consumer calls **input.readNBytes(1024)** and stops because it only needs a prefix. How must it handle the stream?
5. With **ofLines()**, why does **limit(5)** + **forEach** not mean the entire body has been read? Explain the role of **Stream.close()**.
6. A **Flow.Publisher<List<ByteBuffer>>** is returned from ofPublisher but not yet subscribed to. Can you assert that the HTTP exchange has released all resources?
7. A subscriber has subscribed but neither calls **request(n)** nor cancels. What can this cause for the body pipeline?
8. A Publisher is subscribed to twice. What does the Java Javadoc specify the second attempt receives?
9. The outer future completes with status 200 and then InputStream.read throws IOException. Does the future revert to exceptional? On which future should you report the error?
10. If **CompletableFuture.cancel(true)** is called after the outer future has completed, can it replace **InputStream.close()**?
11. Explain why **HttpClient.close()** from Java 21 is not a fix for an application that fails to drain/close streaming bodies.
12. Design an API returning **CompletableFuture<Result>** where Result only appears once the body is fully parsed; identify which callback owns InputStream.
13. Build a service that receives a large response when only a checksum is needed. How do you read chunk-by-chunk and bound bytes instead of calling readAllBytes?
14. Create a test server that intentionally aborts the body after sending headers. What do you expect the outer future and the consumer-stage future to show?
15. For an SSE stream open for hours, design idle timeout, cancellation, resource ownership, and active streams monitoring.

## 19. Code Review Checklist

- [ ] With **ofInputStream()**, who calls **close()** or reads to EOF?
- [ ] With **ofLines()**, who consumes to the end or **closes the Stream**?
- [ ] With **ofPublisher()**, is it subscribed **once** and either requested to completion or cancelled?
- [ ] Are **responseFuture completed** and **bodyConsumption completed** separated?
- [ ] Is there a cleanup path on parse exception, timeout, caller cancel, and executor rejection?
- [ ] Are there limits on total bytes, idle time, active streams, worker queue, and memory?
- [ ] Are **status 200** or **future.isDone()** never treated as certification of a complete body?
- [ ] Are IOExceptions handled after the future has completed?
- [ ] Are blocking reads avoided on uncontrolled callbacks/executors?
- [ ] Is there an ownership policy when handing off a body stream across multiple layers?
- [ ] Is it understood that early close can affect connection reuse?
- [ ] If Java 21+ uses HttpClient.close(), is it ensured that streaming requests can complete or be cancelled?
- [ ] Is there a deterministic test proving the future completes while the body remains open?

**Remember:** **sendAsync + a streaming BodyHandler splits the work into two phases.** Phase 1 completes **CompletableFuture<HttpResponse<T>>** when the response and streaming handle are ready. Phase 2 is owned by the **consumer**: **read-to-EOF or close InputStream; consume to the end or close Stream<String>; subscribe/request to a terminal signal or cancel Flow.Subscription**. Only after properly handling phase 2 is there a basis to say **the body is finished from a usage standpoint and resources have a valid release path**. Do not use future completion as a substitute for this obligation.

### Official Documentation

- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpResponse.BodyHandler — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html)
- [HttpResponse.BodySubscriber — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html)
- [HttpResponse.BodyHandlers — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpResponse.BodySubscribers — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [Flow.Publisher — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Publisher.html)
- [Flow.Subscription — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html)
- [HttpClient — Java SE 21: close/shutdown and streaming resources](https://docs.oracle.com/en/java/javase/21/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpServer — Java SE 17 (test fixture)](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
