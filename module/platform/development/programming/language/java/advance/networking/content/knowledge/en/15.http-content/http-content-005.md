# Streaming Recognition with ofInputStream, ofLines, or ofPublisher in Java HttpClient (Java 17+)

When receiving a large or incrementally sent HTTP response, an application should not default to calling `HttpResponse.BodyHandlers.ofString()` or `ofByteArray()` to buffer the **entire body in memory**. Java 17 provides three **streaming** body-handling modes: `ofInputStream()` returns a byte-oriented `InputStream`, `ofLines()` returns a line-split `Stream<String>`, and `ofPublisher()` returns a `Flow.Publisher<List<ByteBuffer>>` with **demand/backpressure** following the `java.util.concurrent.Flow` standard. Choosing the wrong one or neglecting the stream can prevent the HTTP connection from being released, cause the application to hold resources for too long, or corrupt byte/text processing.

This is a Knowledge article in the **HTTP Content** section of **Java Advance - networking**, focusing on **identifying the three body-streaming approaches**, how to choose based on data type, exchange completion responsibilities, Flow subscriptions, and error scenarios. The examples run standalone on **JDK 17+**, using a loopback HTTP server so no public API or Internet access is required.

## 1. Quick Comparison Table of the Three BodyHandlers

| Java 17 API | `HttpResponse<T>.body()` Type | Abstraction Level | When Appropriate | Responsibility After `send` |
| --- | --- | --- | --- | --- |
| `BodyHandlers.ofInputStream()` | `InputStream` | **Byte stream**, read in arbitrary byte counts | Binary files, unknown-format data, parsers accepting `InputStream` | **Read to EOF or close `InputStream`** |
| `BodyHandlers.ofLines()` | `Stream<String>` | **Text line stream**, charset-decoded and line-split | Logs, text lists, NDJSON, event lines when paired with a proper parser | **Iterate to the end or close `Stream`** |
| `BodyHandlers.ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **Reactive byte stream**, with `Subscription` | Asynchronous pipelines, consumers processing `ByteBuffer` and demand | **Subscribe exactly once; request until terminal event or cancel** |

**Key commonality:** with all three approaches, `client.send(request, handler)` or the `sendAsync` future may provide the `HttpResponse` object **after the response headers are read**, while the **body has not yet been fully received**. "Having the `HttpResponse`" does not mean "finished processing the body", and it does **not** mean the connection is definitely ready for reuse.

Further comparison:

- `ofString()` and `ofByteArray()` normally return the response after the **entire body** has been accumulated; simple, but not ideal for overly large content.
- `ofFile(path)` writes directly to a file via the handler, which is often more convenient than reading `InputStream` manually when the sole goal is downloading a file, though path, size, time, and I/O errors still need to be controlled.
- None of these approaches turns HTTP into UDP datagrams. **A TCP/HTTP body remains a byte sequence that can be split across multiple receives**; all batch/buffer boundaries are determined by the transport, not application message boundaries.

## 2. What Roles Do HttpClient, BodyHandler, and BodySubscriber Play?

The processing chain in JSSE/JDK HttpClient can be viewed as follows:

```text
HttpClient.send / sendAsync
          |
          v
HTTP response status + headers received
          |
          v
BodyHandler<T> receives ResponseInfo
          |
          | selects a BodySubscriber<T>
          v
BodySubscriber<T> receives data as List<ByteBuffer>
          |
          +-- ofInputStream -> InputStream (caller pulls bytes)
          +-- ofLines       -> Stream<String> (caller pulls lines)
          +-- ofPublisher   -> Flow.Publisher<List<ByteBuffer>> (caller subscribes)
          |
          v
body drained / stream closed / subscription cancelled
          |
          v
Exchange resources released according to implementation mechanism
```

- **`BodyHandler<T>`** is selected when status and headers are available, *before* reading the full body. The handler decides which subscriber receives the content.
- **`BodySubscriber<T>`** is essentially a subscriber to a `List<ByteBuffer>` flow published by the HTTP implementation. It transforms bytes into the result type `T`.
- **`HttpResponse<T>`** carries the status code, headers, request, version, and `body()` of type `T`.
- **`BodyHandlers.ofInputStream/ofLines/ofPublisher`** create the corresponding adapters. Do not confuse the *response* being returned to the application with the *subscriber* having emitted its terminal `onComplete`.

The Java 17 contract on streaming/cleanup is explicitly documented in [BodySubscribers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html).

## 3. Case 1 — ofInputStream(): Receiving a Raw Byte Stream

Correctly typed declaration:

```java
HttpResponse<InputStream> response = client.send(
        request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream input = response.body()) {
    // Read a bounded portion or read to completion depending on the protocol.
}
```

This is an **illustrative snippet**; `client`, `request`, imports, and the enclosing method are not declared. With `InputStream`:

1. `read(byte[])` or `read(byte[], off, len)` returns the actual number of **bytes** received, with **no** guarantee that one read corresponds to one write by the server. Check `-1` for EOF. When the buffer has space and no data is available yet, read may block.
2. When consuming incrementally, use a fixed buffer to avoid allocating a massive array. Do not call `readAllBytes()`/`transferTo(ByteArrayOutputStream)` unconditionally on unbounded bodies.
3. If the body contains UTF-8, a multi-byte character **may straddle two `read` calls**. Do not decode each chunk as an independent `String`; use a stateful decoder or assemble bytes into complete frames/records before decoding.
4. **Always have a cleanup path**: read to EOF, or call `input.close()` if stopping early/on error. Closing early may cause the underlying HTTP connection to be closed and ineligible for reuse.
5. The response code may be 4xx/5xx while a body still exists and must be read/closed; `send` does not throw an exception by default for HTTP error statuses.

In particular, in Java 17, `ofInputStream` **does not wait for the body to finish downloading before returning the response**. Therefore, code that measures only how long `send` takes to return may be measuring primarily header receipt rather than the full content download time.

## 4. When Should You Read a Byte Stream Instead of Text?

Choose `ofInputStream` if:

- The response is a **binary file** (image, PDF, ZIP, protobuf, non-text payload). Do not use `ofLines` to process arbitrary bytes, because charset conversion can alter the data.
- You need to process data sequentially using an API that already accepts `InputStream`: a streaming JSON parser, decompressor, or copy-to-file with checksum verification.
- You need the **exact byte size** to compare a digest, signature, or validate `Content-Length`.
- You want to control **byte limits**, chunk size, rate, buffering, and when to cancel/close.
- The data may lack newlines or line formatting; processing with a line abstraction offers no benefit.

Avoid keeping an `InputStream` in a singleton or sharing it across multiple concurrent workers to read. `HttpResponse<InputStream>.body()` is a data source for a **specific exchange**, not a replayable cache. If consumers need to replay content, write it to a file or bounded buffer according to policy and open a new source.

## 5. Correctness and Resource Cleanup with ofInputStream

A bounded read loop to guard against oversized response bodies:

```java
// Illustrative snippet: input is InputStream; maxBytes is the safe ceiling.
long total = 0;
byte[] chunk = new byte[8192];
int n;
while ((n = input.read(chunk)) != -1) {
    total += n;
    if (total > maxBytes) {
        throw new IOException("Response body too large");
    }
    // Process chunk[0..n) immediately; DO NOT retain the whole mutable buffer.
}
```

To make the code above run standalone, external variables/imports/exception handling are needed. In production, place the ceiling check **before allocating/accumulating**, avoid integer overflow in addition, and account for post-decompression size if the application decompresses the response. When the ceiling is exceeded, `try-with-resources` must close the stream. Do not wait indefinitely for a peer that never sends EOF; set timeouts/deadlines and an appropriate cancellation strategy.

`Content-Length` can assist with early decisions, but it is **not a safety guarantee**: a response may use chunked encoding, HTTP/2 may omit this header, or metadata may come from an untrusted source. Enforce an **actual bytes consumed cap** alongside header checks.

**Reading the entire body does not guarantee the TCP connection will be reused**; it only satisfies the cleanup requirement to allow reuse according to the implementation and server policy. Closing the stream early may close the connection so unread body data is discarded, especially in HTTP/1.1.

## 6. Case 2 — ofLines(): Text Split into Lines

Correctly typed declaration:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.forEach(line -> processLine(line));
}
```

This is an **illustrative snippet**; `client`, `request`, `processLine`, and imports must be defined. `ofLines()` automatically decodes the body according to the charset and returns a `Stream<String>`, where each string is a line following `BufferedReader.lines()` rules. **Do not** treat it as a preloaded `List<String>`. At the moment `send` returns, the stream may still be waiting for bytes from the server.

Choose `ofLines` for content that is **genuinely line-delimited**, such as:

- **NDJSON / JSON Lines**: each complete line is a JSON object, and the parser is invoked per line.
- **Log streaming**: the server sends text lines and the consumer processes them sequentially.
- **Simple line-based CSV** if the protocol guarantees fields **do not contain quoted newlines**. RFC 4180 CSV with multiline fields requires a full CSV parser; `ofLines` alone is insufficient.
- **SSE (Server-Sent Events)**: each line is a component of the event protocol; an **SSE parser** is needed to handle multiple `data:` lines, blank-line event separators, `id`, `retry`, and comments. **Do not** equate "one line = one SSE event".

Blank lines can be meaningful to the protocol. Do not strip all `""` automatically without understanding the protocol.

## 7. Charset and Text Boundaries of ofLines

Under the Java 17 API, `BodyHandlers.ofLines()` uses the character set from the `Content-Type` header when identifiable, and defaults to UTF-8 when the header does not specify a supported charset. It relies on a character decoder, so multi-byte UTF-8 characters split across TCP reads/chunking are still handled via decoder state.

Example text response:

```text
Content-Type: text/plain; charset=UTF-8

alpha
Xin chào
omega
```

`Stream<String>` will yield elements line by line: `"alpha"`, `"Xin chào"`, `"omega"`. Line terminators are **not** part of each returned `String`. Important nuance: a final line without a trailing newline can still be returned as a line; do not assume every string ended with a newline.

Limitations to keep in mind:

- If the server declares an incorrect charset, or data is invalid for that encoding, decoding may produce unintended text; verify **Content-Type/charset** when strictness is required.
- `Stream<String>` is a **sequential, consumable stream** for a single exchange. Do not invoke a second terminal operation to "re-read" from the start.
- `Stream.toList()` will also collect every line into memory. It is convenient in small demos, but **not a safe choice for unbounded streams**; production code should process line by line with limits on line count, line length, total bytes, and deadlines.
- If the consumer stops early with `limit(10)`, that **does not mean the response has reached EOF**. You must `close()` the stream in `try-with-resources`; the connection may not be reused.
- For an overly long line with no newline, the decoder/line reader can buffer substantial memory **before yielding a single line**. With untrusted sources, enforce size limits using a byte-oriented parser/decoder with a quota rather than relying solely on the number of lines read.

## 8. Cleanup of Stream<String> Is Also Mandatory

Safe pattern:

```java
HttpResponse<Stream<String>> response = client.send(
        request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = response.body()) {
    lines.limit(100).forEach(line -> System.out.println(line));
} // close even when stopping early.
```

This is an illustrative snippet only, without `client`/`request`. For text streams:

- **Read all lines** or **close the stream** so the implementation releases exchange resources.
- If `Stream.limit(100)` stops while the server is still sending, closing early **may prevent the HTTP connection from being reused**.
- Do not return `response.body()` directly to a higher-level API without specifying who must close it; for example, a service returning `Stream<String>` to a caller must clearly document **caller owns stream**.
- Do not run different terminal operations concurrently on the same stream. It is not a broadcast publisher and cannot be subscribed to multiple times.
- When an exception occurs while parsing a line, `try-with-resources` still runs `close()`. Handle both I/O and decoding exceptions appropriately across transport and business layers.

In Java 17, `HttpResponse.BodySubscribers.ofLines(Charset)` is the underlying class using the selected charset; simply calling `BodyHandlers.ofLines()` is the standard way to let the API infer it from headers.

## 9. Case 3 — ofPublisher(): Flow.Publisher<List<ByteBuffer>>

Correctly typed declaration (do not omit `List`):

```java
HttpResponse<Flow.Publisher<List<ByteBuffer>>> response =
        client.send(request, HttpResponse.BodyHandlers.ofPublisher());

Flow.Publisher<List<ByteBuffer>> publisher = response.body();
// Must register exactly one Flow.Subscriber receiving List<ByteBuffer>.
```

This is an illustrative snippet; imports and request/client setup are needed. **This publisher allows only a single subscriber**. A second subscription is signaled with `onError(IllegalStateException)` per the Java 17 contract. If you do not subscribe, or subscribe without requesting or cancelling, the response body may hang unconsumed and hold onto resources.

The actual type is **`Flow.Publisher<List<ByteBuffer>>`**, not `Flow.Publisher<ByteBuffer>` and not `Flow.Publisher<byte[]>`. Each `onNext` receives **a list** containing one or more `ByteBuffer`s; the bytes in the list are in the same order as the HTTP response body. The number of lists/buffers and the length of each buffer are determined by the implementation and transport. Do not use the number of `onNext` calls to count NDJSON messages or HTTP chunks.

## 10. Flow Subscription: request(n) Counts Batches, Not Bytes

`Flow` provides four core callbacks:

| Callback | When | What the Consumer Must Do |
| --- | --- | --- |
| `onSubscribe(subscription)` | Subscription is accepted | Store `Flow.Subscription`, call `request(n)` with `n > 0` when ready |
| `onNext(List<ByteBuffer>)` | Producer delivers a batch per demand | Process buffers in the list in order, update byte count/state |
| `onError(Throwable)` | Stream terminates with an error | Complete future, clean up, do not wait for `onComplete` |
| `onComplete()` | Entire body has been emitted | Finalize result, release state, do not request more |

A single `request(1)` allows the producer to emit **one `onNext` call** (one `List<ByteBuffer>`), with **no** guarantee of one byte, one HTTP frame, or one text line. To regulate consumption by exact byte count, the consumer must count `remaining()` bytes and manage its own queue/quota.

```text
HTTP body bytes -> Publisher
                     |
                    onSubscribe(s)
                     |
                    s.request(1)
                     |
                    onNext([bufA, bufB])
                     |
                 process entire batch
                     |
                    s.request(1)
                     |
                    onNext([bufC])
                     |
                    ... onComplete or onError
```

When the consumer cannot continue, call `subscription.cancel()`. Cancelling early may cause the HTTP connection to close or the HTTP/2 stream to reset depending on the situation. **Do not assume cancel will "keep pooling intact".**

## 11. ByteBuffer in onNext: Safe and Correct Handling

Java 17 specifies the `List<ByteBuffer>` stream from `BodySubscriber` as **unmodifiable lists containing read-only ByteBuffers**; the underlying contents must not be mutated. Consumers can read via `get`, `remaining`, and create `duplicate()` when a separate view position is needed.

```java
// Snippet: called from Flow.Subscriber<List<ByteBuffer>>.onNext.
long bytesInThisBatch = 0;
for (ByteBuffer item : batch) {
    ByteBuffer view = item.duplicate();
    bytesInThisBatch += view.remaining();
    // Read view.get(...) with bounds so buffers are not retained indefinitely.
}
```

Important:

- `ByteBuffer.remaining()` counts the number of **bytes remaining from position to limit**, not capacity.
- A UTF-8 Unicode code point can be split **across two ByteBuffers**, across two lists, or across events. **Do not decode each buffer into a String** and concatenate, as this can produce replacement characters. Use a `CharsetDecoder` that preserves state across batches, or accumulate **one bounded logical unit** before decoding.
- Do not assume buffers are always heap-backed with `array()`; byte buffers may be read-only/direct where `array()` is unsupported. Use `get(...)` on a duplicate/slice or a streaming decoder mechanism.
- Do not retain received `ByteBuffer`s indefinitely in a consumer queue. If asynchronous processing after `onNext` is needed, define ownership, bounded capacity, and a strategy for when to call `request` next.
- One `onNext` is **one delivery batch**, not a guaranteed individual request/response body or network packet.

In small demos, the callback processes the entire batch and immediately calls `request(1)`. In multi-stage production pipelines, request more only when the downstream stage **has capacity**.

## 12. Java 17+ Example 1 — All Three Handlers on a Loopback HTTP Server

The file **`StreamingBodyHandlersDemo.java`** starts a standard JDK `HttpServer` from module `jdk.httpserver` on `127.0.0.1` with an ephemeral port. The server returns the same three-line UTF-8 body, including multibyte Vietnamese. A shared `HttpClient` performs three separate GET requests using `ofInputStream`, `ofLines`, and `ofPublisher`, respectively.

```java
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
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
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Stream;

public class StreamingBodyHandlersDemo {
    private static final String CONTENT = "alpha\nXin chào\nomega\n";

    private static final class Collector
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final ByteArrayOutputStream data =
                new ByteArrayOutputStream();
        private final CompletableFuture<byte[]> done =
                new CompletableFuture<>();
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> batch) {
            try {
                for (ByteBuffer item : batch) {
                    ByteBuffer copy = item.duplicate();
                    byte[] bytes = new byte[copy.remaining()];
                    copy.get(bytes);
                    data.write(bytes, 0, bytes.length);
                }
                subscription.request(1);
            } catch (RuntimeException ex) {
                subscription.cancel();
                done.completeExceptionally(ex);
            }
        }

        @Override
        public void onError(Throwable error) {
            done.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            done.complete(data.toByteArray());
        }

        byte[] await() throws Exception {
            return done.get(10, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        byte[] payload = CONTENT.getBytes(StandardCharsets.UTF_8);
        AtomicInteger hits = new AtomicInteger();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService serverPool = Executors.newFixedThreadPool(2);
        server.createContext("/data", exchange -> {
            try {
                hits.incrementAndGet();
                exchange.getResponseHeaders().set("Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, payload.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(payload);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverPool);
        server.start();

        try {
            URI target = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/data");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest request = HttpRequest.newBuilder(target)
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<InputStream> a = client.send(
                    request, HttpResponse.BodyHandlers.ofInputStream());
            ByteArrayOutputStream inputBytes = new ByteArrayOutputStream();
            try (InputStream in = a.body()) {
                byte[] buffer = new byte[5];
                int n;
                while ((n = in.read(buffer)) != -1) {
                    inputBytes.write(buffer, 0, n);
                }
            }
            System.out.println("InputStream matches: "
                    + java.util.Arrays.equals(
                            payload, inputBytes.toByteArray()));

            HttpResponse<Stream<String>> b = client.send(
                    request, HttpResponse.BodyHandlers.ofLines());
            List<String> lines;
            try (Stream<String> stream = b.body()) {
                lines = stream.toList();
            }
            System.out.println("ofLines: " + lines);

            HttpResponse<Flow.Publisher<List<ByteBuffer>>> c =
                    client.send(request,
                            HttpResponse.BodyHandlers.ofPublisher());
            Collector collector = new Collector();
            c.body().subscribe(collector);
            byte[] raw = collector.await();
            System.out.println("Publisher matches: "
                    + java.util.Arrays.equals(payload, raw));
            System.out.println("Requests served: " + hits.get());
        } finally {
            server.stop(0);
            serverPool.shutdownNow();
        }
    }
}
```

Compile and run with JDK 17+:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 StreamingBodyHandlersDemo.java
java --add-modules jdk.httpserver StreamingBodyHandlersDemo
```

Stdout on a successful run:

```text
InputStream matches: true
ofLines: [alpha, Xin chào, omega]
Publisher matches: true
Requests served: 3
```

**Why is this program valuable for verification?**

1. `HttpServer` returns a fixed body with `Content-Type: text/plain; charset=UTF-8`; `ofLines` reads all three lines accurately even though Unicode characters may span multiple reads.
2. `ofInputStream` reads with a **5-byte** buffer (smaller than consecutive Unicode characters) and compares the **raw bytes** of the entire body. The code **does not decode per chunk**, avoiding UTF-8 corruption.
3. `try (InputStream in = a.body())` guarantees the stream is closed on completion or read error.
4. `ofLines` returns `Stream<String>`; the program uses `try (Stream<String> stream = b.body())`. `toList()` is acceptable only in this demo because the body is tiny; for unbounded streams, process line by line with a quota.
5. `ofPublisher` returns `Flow.Publisher<List<ByteBuffer>>`. `Collector` requests **one batch** at a time, copies bytes from `duplicate()`, and then requests the next. `CompletableFuture` is completed in `onComplete` or `onError`, and the caller awaits with a timeout.
6. `Requests served: 3` counts **three HTTP requests**, not three TCP connections; the code does not claim socket reuse from this number alone.
7. The demo requires no Internet access and bounds request time. It is **not** a production HTTP server, lacking authentication, compression policies, or memory limits on the `Collector` consumer (since the payload is fixed and very small).

## 13. Java 17+ Example 2 — Body Limits and Single-Subscriber Enforcement

The file **`StreamingLimitsDemo.java`** illustrates two often-overlooked constraints:

- An HTTP response with a 4,096-byte body is **rejected** once the `ofInputStream` consumer exceeds the 100-byte ceiling; `try-with-resources` closes the stream even when throwing.
- An `ofPublisher` publisher for the body `PUBLISHER` (9 bytes) is subscribed to once, processed to completion with `request(1)`, and a second subscribe attempt is notified with **`IllegalStateException`** per the API contract.

```java
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
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.TimeUnit;

public class StreamingLimitsDemo {
    private static byte[] readLimited(InputStream input, int max)
            throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] buffer = new byte[7];
        int total = 0;
        for (int n; (n = input.read(buffer)) != -1;) {
            if (n > max - total) {
                throw new IOException("body limit exceeded");
            }
            output.write(buffer, 0, n);
            total += n;
        }
        return output.toByteArray();
    }

    private static final class CountSubscriber
            implements Flow.Subscriber<List<ByteBuffer>> {
        final CompletableFuture<Long> result = new CompletableFuture<>();
        private Flow.Subscription subscription;
        private long count;

        @Override
        public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }
        @Override
        public void onNext(List<ByteBuffer> batch) {
            for (ByteBuffer buffer : batch) {
                count += buffer.remaining();
            }
            subscription.request(1);
        }
        @Override
        public void onError(Throwable error) {
            result.completeExceptionally(error);
        }
        @Override
        public void onComplete() {
            result.complete(count);
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress local =
                InetAddress.getByAddress(new byte[]{127, 0, 0, 1});
        HttpServer server = HttpServer.create(
                new InetSocketAddress(local, 0), 0);
        ExecutorService serverPool = Executors.newFixedThreadPool(2);
        byte[] large = new byte[4096];
        byte[] small = "PUBLISHER".getBytes(
                java.nio.charset.StandardCharsets.UTF_8);

        server.createContext("/large", exchange -> {
            try {
                exchange.sendResponseHeaders(200, large.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(large);
                }
            } finally {
                exchange.close();
            }
        });
        server.createContext("/small", exchange -> {
            try {
                exchange.sendResponseHeaders(200, small.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(small);
                }
            } finally {
                exchange.close();
            }
        });
        server.setExecutor(serverPool);
        server.start();

        try {
            String base = "http://127.0.0.1:"
                    + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();
            HttpRequest largeRequest = HttpRequest.newBuilder(
                    URI.create(base + "/large"))
                    .timeout(Duration.ofSeconds(5)).GET().build();

            HttpResponse<InputStream> response = client.send(
                    largeRequest,
                    HttpResponse.BodyHandlers.ofInputStream());

            boolean rejected = false;
            try (InputStream in = response.body()) {
                readLimited(in, 100);
            } catch (IOException ex) {
                rejected = "body limit exceeded".equals(ex.getMessage());
            }
            System.out.println("Body limit rejected: " + rejected);

            HttpRequest smallRequest = HttpRequest.newBuilder(
                    URI.create(base + "/small"))
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<Flow.Publisher<List<ByteBuffer>>> published =
                    client.send(smallRequest,
                            HttpResponse.BodyHandlers.ofPublisher());

            CountSubscriber first = new CountSubscriber();
            published.body().subscribe(first);
            System.out.println("Publisher bytes: "
                    + first.result.get(10, TimeUnit.SECONDS));

            CompletableFuture<Boolean> secondRejected =
                    new CompletableFuture<>();
            published.body().subscribe(
                    new Flow.Subscriber<List<ByteBuffer>>() {
                        @Override
                        public void onSubscribe(Flow.Subscription s) {
                            s.request(1);
                        }
                        @Override
                        public void onNext(List<ByteBuffer> value) {
                            secondRejected.complete(false);
                        }
                        @Override
                        public void onError(Throwable error) {
                            secondRejected.complete(
                                    error instanceof IllegalStateException);
                        }
                        @Override
                        public void onComplete() {
                            secondRejected.complete(false);
                        }
                    });
            System.out.println("Second subscriber rejected: "
                    + secondRejected.get(10, TimeUnit.SECONDS));
        } finally {
            server.stop(0);
            serverPool.shutdownNow();
        }
    }
}
```

Run:

```sh
javac --add-modules jdk.httpserver -encoding UTF-8 StreamingLimitsDemo.java
java --add-modules jdk.httpserver StreamingLimitsDemo
```

Expected stdout:

```text
Body limit rejected: true
Publisher bytes: 9
Second subscriber rejected: true
```

Explanation:

1. `readLimited` checks `n > max - total` **before** adding and writing more bytes, avoiding exceeding the budget. When the body exceeds the ceiling, it throws `IOException`. `try-with-resources` in the caller ensures the body stream is closed.
2. Closing early is a choice to protect memory, though it may **close the connection** and prevent reuse, especially in HTTP/1.1. Application correctness and safety **are more important than trying to keep a socket open by reading an untrusted body to completion**.
3. `CountSubscriber` requests one batch at a time and sums `remaining()` across the byte buffers in the list until `onComplete`. A `Publisher` has no "re-read" API like a collection.
4. The second `subscribe` call still receives `onSubscribe` followed by `onError(IllegalStateException)` per `ofPublisher` rules; the program prints `true` when the error type matches.
5. This test cannot measure the number of reused connections, nor can it prove that flow backpressure bounds byte memory in all cases. It verifies the data types and publisher/lifecycle contract on JDK 17.

## 14. Does sendAsync Mean the Body Has Finished Downloading?

Not necessarily. With streaming handlers:

```java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request,
                HttpResponse.BodyHandlers.ofInputStream());

// The response may appear before the entire body has been received.
HttpResponse<InputStream> response = future.join();
try (InputStream in = response.body()) {
    // Read according to your own lifecycle.
}
```

This is an illustrative snippet. `sendAsync` returns a future containing `HttpResponse<InputStream>` **when the body object is ready according to the handler**, without promising that the body has been fully consumed. With `ofPublisher`, you must also **subscribe and wait for the publisher's terminal event**; if you only wait on `sendAsync(...).join()` and discard the publisher, the exchange has no reason to complete on its own and release resources.

With `ofLines`, it is also normal for the future to have the response before lines arrive. The caller must decide who holds the stream, who consumes it, who closes it, and at which layer errors/deadlines are handled. Do not conflate "future completed" with "last business record processed".

## 15. Flow Backpressure Does Not Replace Application Size Limits

Flow request/demand helps the consumer control the number of batches it is ready to receive, but a single batch can contain **multiple `ByteBuffer`s of varying total size**. Therefore:

- `request(1)` is not a limit of **1 byte** or **1 KiB**.
- If all received buffers are retained in a global `List`, memory can still grow with the body.
- If you subscribe and never request, the body may wait indefinitely while exchange resources remain held. Timeouts/cancellation are required.
- If downstream is not ready, do not request more until capacity is available. Combine bounded queues with progress signaling.
- The `onNext` callback should not perform slow I/O or blocking work that stalls the delivery thread; when handing off to a worker, design buffer lifetimes, copying/slicing, and ordering properly.

**Batch-level flow control does not mean perfect backpressure across every buffer/transport layer.** The JDK, TLS, HTTP/2, and internal queues may still buffer data. Total byte caps, request timeouts/deadlines, in-flight request limits, and cancellation policies are still required.

## 16. Resource Ownership and Connection Reuse: Which Path Releases Resources?

| Handler | "Happy Path" | Early Stop / Error | Reuse Potential |
| --- | --- | --- | --- |
| `ofInputStream` | Read to EOF then close stream | `InputStream.close()` in `finally`/try-with-resources | Reading to completion enables reuse; closing before EOF may force connection closure |
| `ofLines` | Iterate through all lines and close stream | `Stream.close()` | Stopping early may prevent reuse |
| `ofPublisher` | Subscribe **once**, request until `onComplete`/`onError` | `subscription.cancel()` | Cancelling before completion may affect reuse |
| `ofString`/`ofByteArray` | Handler already buffers full body before returning response | Limit download/memory via policy | Reuse possible if exchange completes; body size is the risk |

With **streaming responses**, the party that creates the `HttpRequest` is not necessarily the party responsible for closing the body. Clarify the contract between service and caller. For instance, a service API returning `Stream<String>` may need to require the caller to use `try-with-resources`; if the service reads everything into DTOs itself, the service should close it before returning the result.

**In Java 17, `HttpClient` has no public `close()` to substitute for closing body streams**. Even when a client is reused long-term, body-specific resources must still be closed properly. Do not skip closing a response's `InputStream` just because you reuse the same `HttpClient` across many requests.

## 17. Controlling Status Codes, Content-Type, and Streaming Reads

`BodyHandlers.ofInputStream/ofLines/ofPublisher` **do not automatically discard the body** when a response has HTTP 404, 429, or 500. The response still has status/headers and often an error body. Build logic as follows:

```text
1. Receive status + headers via HttpResponse.
2. Accept only status/content-type supported by the application protocol.
3. If status is successful:
     Select the appropriate streaming parser, set limits/quotas.
4. If status is an error:
     Optionally read up to N bytes of the error body or discard with a clear policy.
5. In all branches: drain or close/cancel the body.
6. Handle metrics/retries according to request semantics; do not blindly retry side effects.
```

If you need to decide on the **subscriber immediately upon seeing status/headers**, a custom `BodyHandler<T>` can inspect `ResponseInfo` and choose `BodySubscribers.discarding()` when the body is unwanted, or the appropriate subscriber when streaming is desired. Avoid downloading a huge HTML error page just to inspect the status.

**With streaming text**, do not rely on `Content-Type: text/plain` without checking the upstream's charset/body encoding. When the server sends `Content-Encoding` (gzip/br...), do not assume `ofLines` will automatically yield decompressed text for every encoding: check HTTP client/proxy/provider behavior and protocol agreements, as a separate decompression stage may be needed.

## 18. Specific Notes for NDJSON, SSE, and Binary Streaming

### NDJSON

Each independent line contains a JSON value with an agreed structure. `ofLines()` helps **deliver each line**, but JSON parsing, schema validation, line length limits, charset verification, and retry logic still belong to the application. Do not collect the entire `Stream<String>` with `toList()` when the server can send unbounded data.

### Server-Sent Events

`text/event-stream` contains `data:`, `event:`, `id:`, `retry:` lines and blank lines separating events. `ofLines()` is suitable as a line input source, **not as a complete SSE parser**. An event can span multiple `data:` lines; you must assemble them per SSE rules and handle reconnects and `Last-Event-ID` if implementing the protocol properly.

### Binary / Checksums / Codecs

`ofInputStream()` is suitable as input for byte-based parsers/codecs. `ofPublisher()` is suitable when a pipeline consumes `List<ByteBuffer>` via Flow; both require verifying total bytes/hash/signature per protocol. **Do not** convert binary data into Unicode lines with `ofLines()` and expect the original bytes to remain intact.

### UTF-8 Split Across Reads

With `ofInputStream` or `ofPublisher`, `read`/`onNext` boundaries are arbitrary. Characters like `à`, `ộ`, and emojis can have their bytes split; decode using a decoder that preserves state across chunks or at complete frame boundaries. `ofLines` handles decoding and line splitting for text cases.

## 19. Timeouts, Cancellation, and Mid-Stream Errors

Scenarios:

- **`client.send` succeeds and returns `HttpResponse<InputStream>`**, yet `input.read` can still block, throw `IOException`, or hit EOF while reading the body. Catch errors in the **stream-consuming layer**, not only around `send`.
- **`Stream<String>` encountering an I/O error during iteration** may report it via an unchecked wrapper such as `UncheckedIOException` per the line/stream API; clean up and propagate appropriately to business logic.
- **`ofPublisher` encountering an I/O error after headers** signals it via `onError(Throwable)`. The consumer must complete its future/promise on both `onComplete` and `onError`, otherwise the caller may wait forever.
- **Failing to subscribe** to the publisher or **failing to request** after `onSubscribe` can leave the response hanging: request positive demand or cancel.
- **Per-request timeout** and **end-to-end deadline** are two distinct goals, especially for long-lived or EOF-less streaming bodies. `HttpRequest.Builder.timeout(...)` should not be treated as a self-sufficient mechanism to terminate an unbounded business stream after headers have arrived.
- **Cancelling after the server has processed the request** does not undo side effects. For POST/payment operations, do not use cancellation/retry as proof that the request did not execute.

A well-operated architecture must have a **designed stream termination mechanism**: the HTTP server may provide a protocol-level end marker; the application has deadlines, byte caps, line caps, pause/resume, or graceful cancellation when the user aborts. On cancellation, release state and drop references to the stream/subscription.

## 20. Performance and API Selection Trade-offs

| Goal | Prefer | Why |
| --- | --- | --- |
| Small JSON of a few KB, need DTO immediately | `ofString` or suitable byteArray/parser handler | Simple, minimal state |
| Large ZIP/PDF/image | `ofInputStream` or `ofFile` | Preserves bytes, can stream to disk/hash |
| Line-based text | `ofLines` | Eliminates manual decoding + line splitting |
| NDJSON/log stream | `ofLines` + per-line parser + quota | Each record processed incrementally |
| SSE | `ofLines` + SSE state machine | Lines ≠ events |
| Reactive pipeline with downstream Flow | `ofPublisher` | Controls demand via `Subscription` |
| Consumer already works with `InputStream` | `ofInputStream` | Minimal conversion, easy integration |
| Body not needed | `discarding()` | Avoids opening a stream and forgetting it |
| Want to download file directly to a path | `ofFile(path)` | Avoids copying all bytes onto the heap |

**Do not choose `ofPublisher` just because it sounds "high performance"**. It requires handling asynchronous completion, demand, errors, cancellation, and potential batching. If simple business logic consumes an `InputStream`, a bounded blocking solution may be **easier to verify** and good enough.

Conversely, if you already have a Flow/reactive pipeline and genuine backpressure needs, `ofPublisher` connects the HTTP source into the pipeline in the right model instead of blocking threads just to wait on `InputStream.read`.

## 21. Common Mistakes to Avoid

1. **Treating `ofInputStream` as downloading the whole body before returning the response.** Wrong: the response can be ready right after headers while the body is still arriving.
2. **Not closing `InputStream` after reading only a few bytes.** Can leak exchange resources and prevent pool reuse.
3. **Calling `readAllBytes()` on an unbounded Internet body.** Can cause OOM.
4. **Decoding UTF-8 on every `read` into a String.** Multi-byte characters can be split; use a stateful decoder.
5. **Keeping `Stream<String>` after returning from a service without documenting who closes it.** Easy to leak resources.
6. **Calling `toList()` on an infinite stream.** Turns streaming into unbounded buffering.
7. **Using `ofLines` for binary content.** Charset conversion corrupts byte data.
8. **Assuming one SSE line = one SSE event.** An event can contain multiple `data:` lines; use a proper parser.
9. **Registering `Flow.Subscriber<ByteBuffer>` instead of `Subscriber<List<ByteBuffer>>`.** Wrong generic type.
10. **Assuming `subscription.request(1)` = 1 byte.** It is one `List<ByteBuffer>` item of non-fixed size.
11. **Never requesting after `onSubscribe`.** The flow makes no progress and resources may be held indefinitely.
12. **Subscribing twice to `ofPublisher()`.** The publisher allows only one subscriber; the second receives `onError(IllegalStateException)`.
13. **Ignoring `onError` and waiting only on `onComplete`.** Business futures hang forever when the HTTP body fails.
14. **Storing every ByteBuffer into an unbounded list.** Still OOMs despite using a reactive API.
15. **Assuming ByteBuffer always has a backing `array()`.** Read-only/direct buffers may not.
16. **Calling `new String(chunk, UTF_8)` on each `onNext`.** Easily splits Unicode and produces corrupted characters.
17. **Assuming early close/cancel still guarantees HTTP connection reuse.** It may cause the underlying connection to close.
18. **Assuming HTTP status 500 makes the body handler discard the body automatically.** No: the caller/handler must define the policy.
19. **Assuming one `read`/`onNext` equals one TCP packet or one HTTP/2 frame.** Delivery boundaries do not correspond that way.
20. **Omitting byte/line/deadline caps.** Streaming does not automatically protect against unbounded resources.
21. **Doing all data processing inside the `onNext` callback, blocking the I/O thread without downstream capacity.** Use lightweight handling, clear ownership, and bounded handoff.
22. **Failing to distinguish body completion from business processing completion.** Receiving the full HTTP body does not prove the record was committed.

## 22. Self-Check Quiz

**Q1.** Which method is best when you need to pass response bytes into a ZIP decoder? **`ofInputStream()`** or an appropriate file/raw-byte API, not `ofLines()`.

**Q2.** `HttpResponse<Stream<String>>` has been returned but the stream has not been iterated yet; does that mean the body has reached EOF? **No**. It must be consumed or closed.

**Q3.** `Flow.Publisher<List<ByteBuffer>>` emits a `List` of 3 buffers; does `request(1)` allow receiving it? **Yes**, one item is **one List**, not one ByteBuffer or one byte.

**Q4.** To read the first 50 lines and stop, is calling `lines.limit(50).forEach(...)` enough cleanup? **No**. You must use `try-with-resources` to close the stream when stopping early.

**Q5.** Two threads want to independently parse a response body produced by `ofPublisher`; can both subscribe to the same publisher? **No**. This publisher allows only one subscriber. If multicasting is needed, build a separate stage with proper ownership/backpressure and copies.

**Q6.** If you close `InputStream` after reading only 1/100 of the body, is the connection guaranteed to be reused? **No**; it may be closed and not used for subsequent exchanges.

**Q7.** A body arrives across two ByteBuffers, with the first byte of a UTF-8 character in buffer A and the remaining bytes in buffer B. Should you create independent Strings for A and B and concatenate them? **No**; use a stateful decoder.

**Q8.** `ofPublisher()` returns `HttpResponse` after headers; can you discard the publisher object without subscribing? **You should not**. Subscribe/request until a terminal event or cancel per the contract to release resources.

**Q9.** Is `BodyHandlers.ofLines()` a complete SSE parser? **No**. It only splits text into lines; SSE event framing has additional rules.

**Q10.** If the response status is 404 and the body handler is `ofInputStream()`, can the error body be read? **Yes**, unless a custom application handler decides otherwise; you must still close the body.

## 23. Checklist for Applying in Java 17 Applications

1. **Are you handling raw bytes, line-based text, or a Flow pipeline?** Choose `ofInputStream`, `ofLines`, or `ofPublisher` accordingly.
2. **Did you write the exact generic type?** `InputStream`, `Stream<String>`, `Flow.Publisher<List<ByteBuffer>>`.
3. **Who is responsible for closing/cancelling?** For InputStream/Stream use `try-with-resources`; for publisher, subscribe once and request to terminal or cancel.
4. **Do you have a body cap/line cap/deadline?** Do not let Internet bodies cause OOM or infinite streams.
5. **Have you validated Content-Type, charset, and status?** Do not parse an HTML error as NDJSON, and do not read binary as text.
6. **Are UTF-8 boundaries handled properly?** Do not decode buffer chunks independently.
7. **Is Flow demand calculated in `List<ByteBuffer>` items?** One `request(1)` is not 1 byte.
8. **Are `onError`/`onComplete`/`cancel` handled and your own future completed?** Do not leave business logic waiting forever.
9. **Are resources released after an early stop?** Close the stream/cancel, accepting the connection reuse trade-off when needed for safety.
10. **Do you distinguish response headers ready from body processing finished?** Base timings, metrics, and retry policies on the right milestone.
11. **Is HttpClient shared appropriately without mixing multi-tenant data across scopes?** Connection pooling is a conditional optimization; stream lifecycle remains per-exchange.
12. **Have you tested with large bodies, small chunks, split multibyte Unicode, invalid charsets, slow sources, early cancellation, and a second subscribe?** Pay special attention to bugs that do not appear with small responses on loopback.

**Conclusion:** `ofInputStream()` provides **byte-oriented pull streaming**, `ofLines()` provides **text-oriented line streaming**, and `ofPublisher()` provides **Flow-oriented push with demand and a single subscriber**. All three allow incremental body processing once headers are ready. Every choice requires **consuming to completion or closing/cancelling properly**, enforcing resource limits, and handling errors after `HttpResponse` has been returned. That is what enables a large-scale HTTP application to remain both data-correct and capable of reusing connections.

### Java 17 API Documentation

- [HttpResponse.BodyHandlers](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html)
- [HttpResponse.BodySubscribers — ofInputStream, ofLines, ofPublisher](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html)
- [HttpResponse.BodySubscriber and Flow<List<ByteBuffer>>](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html)
- [HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [HttpResponse](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html)
- [java.util.concurrent.Flow](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
- [ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html)
- [jdk.httpserver.HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html).
