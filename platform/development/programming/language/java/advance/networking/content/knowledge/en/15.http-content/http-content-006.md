# Receiving an HttpResponse Differs from Reading the Entire Body

## 1. Distinguishing the two points in time

**In Java 17, receiving an `HttpResponse<T>` does not always mean the HTTP response body has been completely downloaded and consumed.** This depends on the `HttpResponse.BodyHandler<T>` passed to `HttpClient.send(...)` or `sendAsync(...)`.

- With `BodyHandlers.ofString()`, `BodyHandlers.ofByteArray()`, and `BodyHandlers.ofFile(...)`, a **successful** response completion indicates that the body has been completely read/processed by the subscriber as a `String`, `byte[]`, or file.
- With `BodyHandlers.ofInputStream()`, `BodyHandlers.ofLines()`, and `BodyHandlers.ofPublisher()`, `HttpResponse` may be returned **immediately after all headers are received**, while the body continues to arrive later. `response.body()` is only an **InputStream**, **Stream<String>**, or **Flow.Publisher<List<ByteBuffer>>** for the caller to consume further.
- For `BodyHandlers.discarding()`, a successful response indicates that the body has been discarded/consumed by the subscriber, not that the response body is empty according to the protocol.

**Remember:** completion of the **response handle**, completion of the **HTTP body**, and completion of **business processing** are three different events. They may coincide for some handlers, but must not be conflated in HTTP client design.

~~~text
Server:  sends headers --- body chunk #1 ------- body chunk #2 ---- END
                 |             |                      |            |
Client:          v             v                      v            v
                 status/headers ready
                 |
                 +-- ofInputStream / ofLines / ofPublisher:
                 |     HttpResponse may appear from here
                 |     body is still arriving; must read/subscribe further
                 |
                 +-- ofString / ofByteArray / ofFile:
                       HttpResponse succeeds after the subscriber
                       has finished reading/processing the entire body
~~~

The `HttpResponse` Javadoc explicitly states that when the response becomes available depends on the BodyHandler. The name `send` or `sendAsync` **does not by itself determine** whether the body is complete before the response is returned.

## 2. Related API classes

`HttpClient` organizes receiving a response into two phases:

1. **Receiving the status code and headers.** `BodyHandler<T>.apply(ResponseInfo)` is called once metadata is available, **before body bytes are delivered to the subscriber**.
2. **Receiving the body via the `BodySubscriber<T>`** selected by the handler. The subscriber may collect the data into a `String`/`byte[]` or return a stream/publisher for the caller to process incrementally.

~~~text
                 HttpRequest
                      |
                      v
                HttpClient.send/sendAsync
                      |
                      v
                STATUS + HEADERS
                      |
                      v
           BodyHandler.apply(ResponseInfo)
                      |
                      v
                BodySubscriber<T>
                   /           \
              collector      streaming
                |               |
        waits for full body   returns handle early
                |               |
                +------ HttpResponse<T> ------+
                                              |
                                      response.body(): T
~~~

Crucially, **`response.body()` returns an object of type `T`**. An `InputStream` object does not mean all bytes have been read; a complete `String` from `ofString` is different. Similarly, a publisher may be ready even before any subscriber has subscribed.

### 2.1. Verification milestones

| Milestone | What is known | What cannot yet be concluded |
|---|---|---|
| TCP/TLS opened successfully | A suitable transport connection exists | That the server has responded |
| Headers received | Status, headers, and some metadata are known | Complete body |
| `BodyHandler.apply` called | The client has read metadata and chosen a subscriber | That the body has been completely processed by the subscriber |
| `HttpResponse<InputStream>` obtained | A stream is available to continue reading | That EOF has been reached |
| `HttpResponse<String>` succeeded | The subscriber has built the String from the body | Valid JSON, business logic succeeded |
| `InputStream.read() == -1` | The body stream reached EOF per the API | That file/DB has committed |
| `Flow.Subscriber.onComplete()` | The publisher signaled successful body completion | That another business consumer has finished |
| Database commit | Business data written per transaction semantics | Does not replace earlier error checks |

Two kinds of "finished reading" must also be distinguished: **the network transport has received all body bytes** and **the application has read/parsed/persisted the data**. With streaming, they can be separated by queues, backpressure, another thread, or business processing steps.

## 3. Comparison table of key BodyHandlers

| Java 17 Handler | `response.body()` type | Can response return **before body completes**? | Caller responsibility |
|---|---|---|---|
| `BodyHandlers.ofString()` | `String` | No, once response completes successfully | Parse/validate data and manage size |
| `BodyHandlers.ofByteArray()` | `byte[]` | No | Avoid unbounded heap allocation |
| `BodyHandlers.ofFile(Path)` | `Path` | No | Verify file, checksum, and clean up failed files |
| `BodyHandlers.discarding()` | `Void` | No; body is discarded | Check HTTP status |
| `BodyHandlers.replacing(value)` | Replacement `T` | No; body is discarded | Do not confuse value with server-sent content |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Yes** | Read to EOF or close stream |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Yes** | Consume all lines or close stream |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Yes** | Subscribe once; demand/onComplete/onError/cancel |
| `BodyHandlers.ofByteArrayConsumer(...)` | `Void` | No, after body is delivered to consumer | Consumer must process fast enough |
| Custom BodyHandler | Depends on `BodySubscriber<T>` | Depends on subscriber contract | Define precisely when getBody completes |

**Do not say every handler "waits until download finishes".** `ofInputStream` returns the handle after headers because it creates a stream for the caller to read; `ofPublisher` returns a publisher for the caller to subscribe to. Conversely, `ofFile` waits until the body is completely written to the file before returning `Path` via a successful response.

### 3.1. Notes on `ofString()`

~~~java
// Excerpt: client/request are already created.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
String text = response.body();
~~~

When `send` completes successfully, `text` contains the body content converted into a String by the handler. Per the Java 17 Javadoc, `ofString()` uses the charset specified in the response `Content-Type` when applicable, or UTF-8 if missing/unsupported. A successfully constructed String **does not prove** that the content is valid JSON or that the server processed the business logic correctly.

For large responses, `ofString()` can create heap pressure. If you need to read files of several gigabytes, switch to `ofFile` or body streaming instead of buffering all bytes into a String.

### 3.2. `ofFile` is not proof of a durable or valid file

~~~java
// Excerpt: outputPath has been determined and properly prepared.
HttpResponse<java.nio.file.Path> downloaded = client.send(
        request, HttpResponse.BodyHandlers.ofFile(outputPath));
java.nio.file.Path saved = downloaded.body();
~~~

The Java 17 documentation states that when `HttpResponse<Path>` is returned, the body has been completely written to the file. However, this **does not automatically guarantee** that the file has been `fsync`ed to physical storage, that its checksum is valid, that its file signature is authentic, or that its content is non-malicious. The caller still has to check the status, size, checksum, and file cleanup policy. An error response can also write an error body to the file, so `statusCode()` must not be ignored.

### 3.3. `discarding()` differs from "forgetting to read the stream"

`discarding()` consumes and discards the body inside the handler, so it does not leave an unread `InputStream` for the application to manage. Conversely, calling `ofInputStream()` and neither reading nor closing it can cause the app to hold unnecessary resources/connections. When the body is not needed, choose `discarding()` or close the streaming body early per policy rather than abandoning it.

## 4. `send` and `sendAsync`: completion depends on the handler

### 4.1. `HttpClient.send(...)`

`send` is a synchronous call with respect to the **completion point defined by the BodyHandler**:

~~~java
HttpResponse<InputStream> early = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());
// Headers are available; the HTTP body may still be arriving.

HttpResponse<String> buffered = client.send(
        request, HttpResponse.BodyHandlers.ofString());
// A complete String is available when this call succeeds.
~~~

These are **API excerpts** on two independent requests. Do not treat "synchronous send" as "every HTTP body has finished reading". The returned stream can still block on `read` after `send` has returned.

### 4.2. `HttpClient.sendAsync(...)`

~~~java
CompletableFuture<HttpResponse<InputStream>> streamFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<HttpResponse<String>> textFuture =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
~~~

Common pitfalls:

- `streamFuture.join()` may return `HttpResponse<InputStream>` right after headers. `join` **does not read the stream to EOF**.
- `textFuture.join()` only returns successfully after the `ofString` subscriber has built the String.
- `thenApply(HttpResponse::statusCode)` on a streaming future may run **very early** and only knows metadata.
- `CompletableFuture.isDone()` being true does not prove success if the future **failed/was canceled**; even success of a streaming future does not prove body completion.
- `HttpResponse<T>.body()` for a publisher is a one-shot publisher, **not a future that automatically completes the business consumer**.

**Consequence:** if code uses `sendAsync(...ofInputStream()).thenAccept(r -> logSuccess())`, the word "success" is easily mistaken for a completed download. It is more accurate to log **response_headers_received**, and separately log **body_completed/body_failed/body_aborted**.

## 5. `ofInputStream()`: getting the response before EOF

With `BodyHandlers.ofInputStream()`, the Java 17 Javadoc states that **headers have been fully read when `HttpResponse` returns**, but the body **may not have been fully received yet**. `response.body()` gives the caller an `InputStream` to read bytes as they arrive.

~~~java
// Excerpt: client/request already exist.
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

System.out.println(response.statusCode()); // HTTP status is known.
try (InputStream in = response.body()) {
    byte[] bytes = in.readAllBytes();        // Only at EOF is the full body present.
}
~~~

Using `readAllBytes()` in the example is only suitable for small/bounded bodies. For large data, read in blocks and enforce a total byte limit. Clearly separate:

1. `HttpResponse` available: response metadata and stream are present.
2. `in.read(buffer)`: may **block** if no new bytes are available; a single read is not the whole body.
3. `in.read() == -1` or `readAllBytes()` completing without error: the stream reached EOF.
4. `InputStream.close()` before EOF: **terminates/cancels consumption**, not "body processed successfully".

### 5.1. Reading to completion or closing the stream is mandatory

The `BodySubscribers.ofInputStream()` Javadoc requires the user to **read to EOF or call `close()`** in order to release resources associated with the HTTP exchange. Closing before reading everything **may** prevent the underlying connection from being reused; that is a reasonable trade-off when you want to stop the download.

**Do not use `available() == 0` as an EOF criterion.** `available()` only estimates bytes that can be read without blocking, not the remaining response length. Nor should `Content-Length` be taken as proof that all bytes have actually been received.

### 5.2. Errors can occur after printing status 200

~~~java
// Excerpt, assuming response is HttpResponse<InputStream>.
try (InputStream in = response.body()) {
    byte[] data = new byte[8192];
    for (int n; (n = in.read(data)) != -1;) {
        consume(data, n);
    }
} catch (IOException ex) {
    // Body processing/transport errors can occur AFTER headers.
}
~~~

`consume` here is an application function, not a standalone program. The server may close abnormally, send malformed framing, or encounter a network error mid-transfer. `HttpResponse` already exists, yet the body has not completed; record status **body_failed** instead of treating response status 200 as download success.

If a worker thread consumes the stream, ownership must be clear: the caller's scope must not auto-close the stream right after handing the reference to a worker that has not finished processing.

## 6. `ofLines()`: lazy `Stream<String>`

~~~java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(System.out::println);
}
~~~

Here `Stream<String>` is not an already-built `List<String>`. Lines are read/decoded as data arrives; an incomplete line may cause the next iteration to wait for more bytes. The response may be returned **before the body is fully received**.

Important:

- **Consume to the end or close `Stream<String>`** per the Javadoc.
- Using a short-circuiting terminal operation such as `limit(5)` or `findFirst()` may not read the whole body; you still need `close()`.
- A text line is not a TCP packet, an HTTP chunk, or a guaranteed business message. You must define newline encoding, record size limits, and error policies.
- If the application uses SSE, NDJSON, or live log streams, the body may continue indefinitely: "waiting for the full response" may be the wrong goal; read record by record with dedicated deadlines/backpressure.

## 7. `ofPublisher()`: HttpResponse containing a Publisher

`BodyHandlers.ofPublisher()` returns `HttpResponse<Flow.Publisher<List<ByteBuffer>>>` **after headers, without waiting for the full body**. The body is a publisher for the caller to subscribe to:

~~~java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
~~~

A subscriber has four basic methods:

| Callback | Meaning |
|---|---|
| `onSubscribe(Flow.Subscription s)` | Receives the subscription; issues `request(n)` or `cancel()` |
| `onNext(List<ByteBuffer> items)` | Receives one **event** carrying a list of ByteBuffers |
| `onError(Throwable error)` | Stream failed; do not treat as successful completion |
| `onComplete()` | Stream signaled successful completion |

`subscription.request(1)` requests **one `onNext` invocation**, **not one byte**. Each event may carry multiple ByteBuffers, each containing a variable number of bytes depending on I/O. Choose demand according to downstream processing speed to avoid unbounded queue/memory growth.

**The `ofPublisher` publisher allows only a single subscription.** A second subscribe does not create a new copy of the response; per the Javadoc, the second subscriber receives `onError` with an `IllegalStateException`. If fan-out to multiple consumers is needed, the application must implement its own multicast mechanism at the body-receiving layer.

### 7.1. When is a publisher body considered done?

- **`HttpResponse<Publisher>` appears:** only the publisher handle is available.
- **`onSubscribe` appears:** subscription is established; bytes are not necessarily received yet.
- **`onNext`:** some bytes arrived; the full body is not guaranteed.
- **`onComplete`:** signaled that **the entire body has arrived** according to the publisher.
- **`onError`:** no successful completion.
- **`cancel`:** the caller abandoned further reception; **not success**.

When the full body is not needed, the subscriber must call `cancel()` instead of "subscribing without requesting or canceling". Canceling may prevent the connection from being reused depending on the HTTP version/implementation; it is still better than leaving resources hanging indefinitely.

### 7.2. ByteBuffer ownership in callbacks

An `onNext` event contains a list of ByteBuffers. A safe pattern typically processes/copies the data inside the callback before requesting the next event:

~~~java
// Excerpt inside onNext(List<ByteBuffer> items):
for (ByteBuffer item : items) {
    byte[] copy = new byte[item.remaining()];
    item.get(copy);
    output.write(copy, 0, copy.length);
}
subscription.request(1);
~~~

`output` is an application sink (for example, `ByteArrayOutputStream` in a test), not a production pattern for unbounded bodies. Do not hold references to upstream ByteBuffers indefinitely and assume ownership or backing storage remains immutable forever; use explicit copying/leasing and backpressure.

## 8. Runnable Java 17+ demo: holding back half the body to prove completion milestones

The demo uses the local `HttpServer` in the `jdk.httpserver` JDK module. The server sends `part1-part2` in two parts, but **pauses after the first part** until the client releases a `CountDownLatch`. Therefore, the program **does not rely on Thread.sleep or lucky timing**.

Three cases on three different endpoints:

1. `/stream` with `ofInputStream()`: the client already has the HttpResponse and status 200 while the final part has not yet been sent. It then reads `part1-`, opens the latch, and reads `part2` until EOF.
2. `/string` with `ofString()`: the client knows the server has sent the first part, yet the response future **has not completed**; only after opening the latch and receiving the full body is the String `part1-part2` available.
3. `/publisher` with `ofPublisher()`: the client gets the response/publisher while the final part has not been sent; the subscriber requests events, waits for `onComplete`, and only then records the full body.

Create the file **`HttpBodyTimingDemo.java`**:

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
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class HttpBodyTimingDemo {
    private static final int SECONDS = 5;

    static class Gate {
        final CountDownLatch firstSent = new CountDownLatch(1);
        final CountDownLatch finish = new CountDownLatch(1);
    }

    private static void sendInTwoParts(HttpExchange exchange, Gate gate)
            throws IOException {
        byte[] first = "part1-".getBytes(StandardCharsets.US_ASCII);
        byte[] last = "part2".getBytes(StandardCharsets.US_ASCII);
        exchange.getResponseHeaders().set("Content-Type", "text/plain");
        exchange.sendResponseHeaders(200, first.length + last.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(first);
            out.flush();
            gate.firstSent.countDown();
            try {
                if (!gate.finish.await(SECONDS, TimeUnit.SECONDS)) {
                    throw new IOException("Test server release timeout");
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw new IOException(e);
            }
            out.write(last);
        } finally {
            gate.firstSent.countDown();
            exchange.close();
        }
    }

    private static void await(CountDownLatch latch) throws Exception {
        if (!latch.await(SECONDS, TimeUnit.SECONDS)) {
            throw new IOException("Deadline exceeded");
        }
    }

    public static void main(String[] args) throws Exception {
        Gate streamGate = new Gate();
        Gate stringGate = new Gate();
        Gate publisherGate = new Gate();
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(new InetSocketAddress(host, 0), 0);
        server.createContext("/stream",
                exchange -> sendInTwoParts(exchange, streamGate));
        server.createContext("/string",
                exchange -> sendInTwoParts(exchange, stringGate));
        server.createContext("/publisher",
                exchange -> sendInTwoParts(exchange, publisherGate));
        server.start();
        try {
            URI base = new URI("http", null, host.getHostAddress(),
                    server.getAddress().getPort(), "/", null, null);
            HttpClient client = HttpClient.newHttpClient();

            HttpResponse<InputStream> streamed = client.sendAsync(
                    HttpRequest.newBuilder(base.resolve("stream")).GET().build(),
                    HttpResponse.BodyHandlers.ofInputStream())
                    .get(SECONDS, TimeUnit.SECONDS);
            await(streamGate.firstSent);
            System.out.println("streamStatus=" + streamed.statusCode());
            System.out.println("streamBeforeBodyEnd=" +
                    (streamGate.finish.getCount() == 1));
            try (InputStream in = streamed.body()) {
                System.out.println("streamFirst=" +
                        new String(in.readNBytes(6), StandardCharsets.US_ASCII));
                streamGate.finish.countDown();
                System.out.println("streamRest=" +
                        new String(in.readAllBytes(), StandardCharsets.US_ASCII));
            }

            CompletableFuture<HttpResponse<String>> buffered = client.sendAsync(
                    HttpRequest.newBuilder(base.resolve("string")).GET().build(),
                    HttpResponse.BodyHandlers.ofString());
            await(stringGate.firstSent);
            System.out.println("stringDoneBeforeRelease=" + buffered.isDone());
            stringGate.finish.countDown();
            System.out.println("stringBody=" +
                    buffered.get(SECONDS, TimeUnit.SECONDS).body());

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> published =
                    client.sendAsync(
                            HttpRequest.newBuilder(base.resolve("publisher"))
                                    .GET().build(),
                            HttpResponse.BodyHandlers.ofPublisher())
                            .get(SECONDS, TimeUnit.SECONDS);
            await(publisherGate.firstSent);
            System.out.println("publisherBeforeBodyEnd=" +
                    (publisherGate.finish.getCount() == 1));
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            CountDownLatch completed = new CountDownLatch(1);
            AtomicReference<Throwable> error = new AtomicReference<>();

            published.body().subscribe(new Flow.Subscriber<>() {
                Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1);
                }

                @Override
                public void onNext(List<ByteBuffer> items) {
                    for (ByteBuffer item : items) {
                        byte[] copy = new byte[item.remaining()];
                        item.get(copy);
                        bytes.write(copy, 0, copy.length);
                    }
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable failure) {
                    error.set(failure);
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    completed.countDown();
                }
            });

            publisherGate.finish.countDown();
            await(completed);
            if (error.get() != null) {
                throw new IOException("Publisher failure", error.get());
            }
            System.out.println("publisherBody=" +
                    bytes.toString(StandardCharsets.US_ASCII));
        } finally {
            streamGate.finish.countDown();
            stringGate.finish.countDown();
            publisherGate.finish.countDown();
            server.stop(0);
        }
    }
}
~~~

Run on **JDK 17 or higher**:

~~~bash
javac --release 17 --add-modules jdk.httpserver HttpBodyTimingDemo.java
java --add-modules jdk.httpserver HttpBodyTimingDemo
~~~

**Exact stdout verified when compiled with `--release 17` and run on OpenJDK 24:**

~~~text
streamStatus=200
streamBeforeBodyEnd=true
streamFirst=part1-
streamRest=part2
stringDoneBeforeRelease=false
stringBody=part1-part2
publisherBeforeBodyEnd=true
publisherBody=part1-part2
~~~

### 8.1. What do the results actually show?

- `streamStatus=200` and `streamBeforeBodyEnd=true`: the client already has response metadata even though the server has not opened the latch to send the final part. That is **response-before-body-completed**.
- `streamFirst=part1-`: the application only read the first six bytes after the response was returned. Reading is a separate step and can block.
- `streamRest=part2`: after opening the latch, the client receives the final part and then EOF.
- `stringDoneBeforeRelease=false`: `ofString` has not completed the response future while the body has not finished sending, even though headers and the first part have arrived.
- `stringBody=part1-part2`: the body collector returns the String after receiving the entire body.
- `publisherBeforeBodyEnd=true`: the publisher handle is returned early.
- `publisherBody=part1-part2`: the subscriber received the body and then `onComplete` was called; the program prints the content only after the completion latch.

The program does **not** claim that each server `write` corresponds to one client `read` or one `onNext`. TCP and the HTTP client may split or coalesce bytes depending on conditions. The synchronization latch guarantees that **the final part has not been allowed to be sent yet**, independent of packet boundaries.

### 8.2. Limitations of the demo

- The server uses **loopback** HTTP, without the Internet or TLS; the goal is to test **when HttpResponse is received**, not to measure HTTPS security.
- The total body is 11 bytes, so `ByteArrayOutputStream` is safe in the demo; real file downloads need quotas and a streaming sink.
- The demo keeps each exchange finite with a 5-second deadline; live production streams may never terminate.
- The demo's publisher subscribes only once, requests 1 event at a time, and copies data before requesting the next.
- On test failure, `finally` opens the latches and stops the server; real callers also need deeper timeout/cancellation policies.

## 9. HTTP metadata is not a certificate of a complete body

An `HttpResponse<T>` provides access to:

| Method | Content |
|---|---|
| `statusCode()` | HTTP status code |
| `headers()` | Map of response headers |
| `version()` | HTTP version |
| `uri()` | Request URI corresponding to the response, possibly the final one after auto-redirect |
| `request()` | Associated request |
| `body()` | Value of type `T` per the handler |

This metadata is available when the response handle is returned. However, **`response.body()` may be a streaming handle**, without the final bytes yet. A status of 200 says nothing about bytes lost or failing later; a valid Content-Length does not prove Java has received the full body.

A 404/500 response status can also contain a body. Built-in `BodyHandlers` such as `ofString` **do not automatically discard the body when status >= 400**. If you want to choose a policy by status, use a custom `BodyHandler` or handle the response status with appropriate cleanup.

### 9.1. HTTP framing and EOF

HTTP/1.1 has body length mechanisms such as `Content-Length` or `Transfer-Encoding: chunked`; HTTP/2/HTTP/3 have corresponding frames/end-of-stream. `HttpClient` handles framing so the caller receives `InputStream`/Publisher at the level of **HTTP body bytes**, without having to parse raw chunk delimiters manually.

- **`Content-Length`** describes the byte count in HTTP semantics, not the number of decoded Unicode characters or the number of bytes already downloaded at the moment the header is inspected.
- **Chunked** splits the body on the wire, but does not guarantee each `InputStream.read` or `onNext` matches one HTTP chunk.
- **HTTP/2 end-of-stream** can complete a body stream while the TCP connection stays alive to serve multiple requests.
- **HEAD, 204, 304**, and special cases have HTTP rules for having no body; do not force waiting for a non-existent payload.
- If the server closes early or truncates framing, the consumer may receive an IOException/onError **after the response handle has already been provided**.

Therefore, EOF on `InputStream` is the **EOF of the HTTP response body** in the abstraction, not necessarily the closure of the TCP connection.

## 10. Timeouts: a response timeout does not necessarily cover subsequent body reads

| Mechanism | Purpose | Misconception to avoid |
|---|---|---|
| `HttpClient.Builder.connectTimeout` | Bounds the connection establishment phase per contract | Not a body download deadline |
| `HttpRequest.Builder.timeout` | Bounds the HTTP request/response exchange per API | Does not by default monitor caller stream reads indefinitely after an early response |
| `CompletableFuture.orTimeout` on `sendAsync` | Bounds when the response future completes | A streaming future may complete right after headers |
| `InputStream.read` | Reads body bytes; may block | `response` having arrived does not mean each read has a deadline |
| `Flow.Subscription.cancel()` | Stops consuming the publisher | Not full body success |

Using `sendAsync(...ofInputStream()).orTimeout(...)` is **not sufficient** to set a deadline for reading the entire streaming body: once the future has completed early, the Future's deadline no longer governs reading. A service needs an **overall deadline**, a byte limit, an **idle timeout** (where appropriate), and stream cancellation/close mechanisms suited to the actual JDK environment.

Do not treat `CompletableFuture.cancel(true)` on a future that **has already succeeded and returned a stream** as an operation that automatically reads or closes the stream. The caller holding the handle must manage resource release itself.

## 11. Connection reuse, cleanup, and terminal states

For streaming handlers, **the caller is responsible for ending consumption**:

| Body type | Successful completion | When aborting |
|---|---|---|
| `InputStream` | Read until `-1` | `close()` |
| `Stream<String>` | Consume to the end | `Stream.close()` |
| `Flow.Publisher` | `onComplete()` | `Subscription.cancel()` |
| `String` / `byte[]` | Handler finished collecting the body | Manage memory/application processing separately |
| `Path` from `ofFile` | Handler finished writing the file | Clean up failed/invalid files, verify checksum |

Closing a stream early or canceling a publisher may prevent the HTTP connection from **being reused**. Still, you must close/cancel if the consumer will not continue, rather than holding network resources and heap memory forever.

**Three outcomes must not be conflated:**

- `BODY_COMPLETED`: read completely and successfully via EOF/onComplete.
- `BODY_FAILED`: encountered IOException, publisher onError, decode error, timeout, or framing error.
- `BODY_ABORTED`: the caller intentionally closed/canceled before the body completed.

For long-lived live streams, not receiving the entire body is not necessarily an error; apps typically rely on **the number of processed records and subscription state** rather than trying to wait for an infinite body to end.

## 12. Memory optimization and backpressure for large bodies

For small bodies, `ofString()/ofByteArray()` is simple. For a 500 MiB download, buffering everything can cause heap pressure or `OutOfMemoryError`. Consider `ofFile`, `ofInputStream`, or `ofPublisher`:

| Requirement | Usually suitable choice |
|---|---|
| Small JSON with clear size bounds | `ofString` or `ofByteArray`, then parse |
| Large file download to disk | `ofFile`, verify status/checksum/file size |
| Feeding bytes to a streaming parser | `ofInputStream` with quota/deadline |
| Receiving NDJSON or text lines incrementally | `ofLines`, must close when stopping early |
| Reactive/backpressure pipeline | `ofPublisher`, demand-driven and single subscriber |
| Body not needed | `discarding` |

`Content-Length` may be absent, wrong, or reflect compressed content, so **count the actual bytes consumed** and enforce limits rather than trusting the header alone. For compressed content, apply a post-decompression quota to guard against zip bombs. Also limit idle time without progress and the number of ByteBuffers queued downstream.

With a publisher, `request(1)` counts **events**, not bytes; each event can contain multiple buffers. Do not blindly call `request(Long.MAX_VALUE)` and store all data in an unbounded list.

## 13. HTTP status vs. errors while reading the body

HTTP 404/500 is a **status returned by the server**, not necessarily a Java exception thrown. Conversely, transport I/O can fail while downloading the body after a 200 status.

Example processing flow:

~~~text
response_received(status=200)
    |
    +-- body_stream read/Flow onNext ... 
           |
           +-- EOF/onComplete: body_completed
           |
           +-- IOException/onError: body_failed
           |
           +-- app close/cancel: body_aborted
~~~

Do not log download_success immediately inside `thenApply(HttpResponse::statusCode)` when using streaming. Log time-to-headers, time-to-first-byte, body-duration, bytes-read, and business completion separately. An app may have committed 20 records and then hit an error on record 21; the business layer must have an appropriate transaction/idempotency policy.

### 13.1. Custom BodyHandler choosing handling by status

Because `BodyHandler` receives status/headers before the body, you can choose how to consume it:

~~~java
// Excerpt: client/request exist and StandardCharsets is imported.
HttpResponse.BodyHandler<String> handler = info ->
        info.statusCode() == 200
                ? HttpResponse.BodySubscribers.ofString(StandardCharsets.UTF_8)
                : HttpResponse.BodySubscribers.replacing("BODY_SKIPPED");

HttpResponse<String> response = client.send(request, handler);
~~~

When status is not 200, the string `BODY_SKIPPED` is a **client-generated value**, not the actual body content from the server. `replacing` discards the body and returns the value. Do not accidentally report "the server returned BODY_SKIPPED".

## 14. Common mistakes to fix

| Misconception | Why it is wrong | How to fix |
|---|---|---|
| `send` returned => entire body downloaded | With `ofInputStream` and `ofLines` it can return before EOF | Read to EOF/close per policy |
| `sendAsync(...).join()` => full body | The future may be for a **stream handle** | Check the handler and track body completion |
| `response.body()` is always byte[]/String | It may be InputStream/Publisher/Stream | Check the type `T` |
| `statusCode()==200` => download success | Body I/O can still fail | Record body completion separately |
| `InputStream.available()==0` => EOF | `available` is not remaining length | Use `read()==-1` |
| `ofFile` returns Path before writing finishes | The handler waits until the body is completely written | Only process Path after a successful response |
| `ofLines().limit(1)` closes the body automatically | Short-circuiting does not consume everything | Use try-with-resources |
| Publisher can be subscribed to multiple times | `ofPublisher` accepts only one subscriber | Implement fan-out yourself if needed |
| `subscription.request(1)` is one byte | It is one `onNext` event | Handle List<ByteBuffer> and quotas |
| `close` on stream = download succeeded | Closing early is aborted | Maintain an aborted state |
| Body size from Content-Length is guaranteed | Metadata may be missing/wrong | Count bytes and enforce limits |
| Reading the whole body means parsing succeeded | Schema/encoding/commit may fail | Separate app processing success |
| A 500 response automatically throws IOException | HTTP status is not itself an I/O error | Handle status/body and close |
| No need to close stream because client manages it | The caller owns the stream handle | EOF or close/cancel |
| Response future timeout monitors the whole stream | The future may complete before the body | Set a separate deadline for the body |

## 15. Practical checklist

**Before choosing a handler:** Is the body large, is incremental processing needed, is downstream slow, is there a file path/quota/checksum policy? Use a collector or streaming? Do you need to measure response headers and body bytes separately?

**When HttpResponse is available:** only record status/headers and body type. If the body is InputStream/Stream/Publisher, clearly assign the owner and cleanup mechanism. Do not treat the response handle as a full download unless the contract allows it.

**While consuming:** read until EOF or onComplete, check for mid-stream errors, limit bytes/time, do not trust Content-Length as an absolute figure; text streams must preserve charset/record framing state.

**When finishing:** distinguish complete, failed, and aborted; close/cancel when aborting, handle connection reuse impact; files need checksums, and business data needs separate parse/transaction checks.

## 16. Self-check questions

**1. Does receiving `HttpResponse<InputStream>` prove the body is complete?** No. Headers are ready; the stream may still be transferring.

**2. What does `send(...ofString())` returning successfully mean?** The subscriber has built the full String from the body; it does not by itself prove the content is valid.

**3. `sendAsync(...ofPublisher()).join()` succeeded, but no one has subscribed yet—is the body complete?** Cannot conclude that. You must subscribe once and wait for onComplete or handle onError/cancel.

**4. Does `InputStream.read() == -1` mean the TCP connection is definitely closed?** No. It is EOF of the body stream per the API; the HTTP connection may be reused.

**5. Does `InputStream.available() == 0` mean the body has ended?** No; `available` is not EOF.

**6. When does `BodyHandlers.ofFile` return the Path?** After the body has been completely written to the file by the subscriber.

**7. If `ofLines` stops at the fifth line using limit(5), what must you do?** Close the Stream if you do not read it to the end.

**8. Can a Publisher be subscribed to twice so two consumers receive the same body?** Not with `ofPublisher`; you must implement fan-out yourself.

**9. Does `request(1)` in Flow request one byte?** No, one `onNext` event; an event may carry multiple ByteBuffers.

**10. HTTP 200 arrived, but `InputStream.read` later throws IOException. Is the body a success?** No; that is a body failure after headers.

**11. Why does the demo use CountDownLatch instead of Thread.sleep?** To deterministically ensure the server holds back the final part of the body, without depending on the scheduler.

**12. How does `BodyHandlers.discarding` differ from ignoring an InputStream?** Discarding consumes and drops the body; ignoring a stream can keep connections/resources open.

**13. Is closing a stream before EOF considered body completed?** No, mark it aborted, even though connection resources may be released.

**14. If `response.body()` is a String, has the JSON schema been validated?** No; String is only the decoding step.

## 17. Official Java and HTTP documentation

- [Java SE 17 – HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): whether the response is available before/after the body depends on `BodyHandler`.
- [Java SE 17 – HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofString`, `ofByteArray`, `ofFile`, `ofInputStream`, `ofLines`, `ofPublisher`, and discard.
- [Java SE 17 – HttpResponse.BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): streaming completion, EOF/close, single subscription, and cleanup.
- [Java SE 17 – HttpResponse.BodyHandler](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandler.html): custom handler invoked after headers/before body.
- [Java SE 17 – HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`/`sendAsync`.
- [Java SE 17 – Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html): `Publisher`/`Subscriber`/`Subscription`.
- [Java SE 17 – HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html): loopback test server.
- [RFC 9110 – HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP status and response semantics.
- [RFC 9112 – HTTP/1.1](https://www.rfc-editor.org/rfc/rfc9112): message framing and body.
- [RFC 9113 – HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): DATA frames and end-of-stream.

**Conclusion:** `HttpResponse<T>` signals **that the result determined by the BodyHandler is available**, not a general guarantee that all body bytes have arrived. With body-collecting handlers such as `ofString/ofByteArray/ofFile`, a successful response corresponds to the body having been completely processed into the desired form. With `ofInputStream/ofLines/ofPublisher`, the response may appear after headers while the body is still arriving; you must track **EOF/onComplete**, errors/cancel, quotas, timeouts, and cleanup to know when the body actually completes.
