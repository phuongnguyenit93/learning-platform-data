# Limiting HTTP Response Size and Avoiding Unbounded Heap Buffering in Java

In the **HTTP Content** module of Java Advance — networking, a memory protection principle must be enforced **before converting a response body into a String, byte[], or object**: **every response from an external system must have an explicit size limit and processing lifecycle**. A request can receive status 200 and valid headers yet return a gigabyte-sized body, a never-ending stream, a small compressed document that expands into an enormous amount of data, or JSON with an extreme number of elements or nesting depth. If a Java application buffers the entire body into the heap without bounds, the result can be **OutOfMemoryError (OOM), prolonged Garbage Collector pauses, reduced throughput, or inability to serve other requests**.

With Java 17 **java.net.http.HttpClient**, common ways of reading the body carry different memory risks:

- **HttpResponse.BodyHandlers.ofString()**: converts the entire body into a **String**; convenient for small payloads with a verified ceiling, but **does not enforce an application-level size limit on its own**.
- **HttpResponse.BodyHandlers.ofByteArray()**: collects the body into a **byte[]**; also **does not enforce an application-level byte limit on its own**.
- **BodyHandlers.ofInputStream()**: provides an **InputStream** for the application to consume incrementally, avoiding buffering the entire payload upfront, **but does not automatically limit bytes or reading time**; the caller must count, abort, and close.
- **BodyHandlers.ofFile(...)**: writes the body to disk instead of holding it all in the heap, but **can fill up the disk** without a quota/limit.
- **Custom BodyHandler/BodySubscriber**: can enforce a byte limit while the subscriber receives **ByteBuffer** chunks, cancel the subscription when exceeded, and coordinate backpressure.

**Core rule:** **Content-Length** can be used **as a signal for early rejection**, but it **does not replace counting the actual bytes received**. Rejecting solely based on Content-Length is insufficient when the response is chunked, missing the header, has a decompression layer, or comes from an untrusted source. It is also necessary to distinguish **the HTTP body limit in wire bytes** from **the decompressed data limit**, **line count, item count, JSON depth**, and **the process-wide memory budget**.

This lesson provides two **Java 17 runnable programs on loopback**, compiled with **javac --release 17** and run successfully on a JDK supporting the **jdk.httpserver** module. The examples use an embedded HTTP server to compare Content-Length, chunked responses, a capped InputStream, and a bounded BodySubscriber. This is followed by production concerns: timeout configuration, decompression bombs, file downloads, concurrency, metrics, testing, and common pitfalls.

## 1. Why Is an Unbounded Response Body Dangerous?

A typical application calls a REST API as follows:

~~~java
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
String json = response.body();
~~~

This is an **illustrative API snippet**, assuming **client** and **request** are already initialized. The code looks simple but makes two dangerous assumptions: the sender **will not send too many bytes**, and the resulting String/JSON **will not consume too much heap**. For services with small, controlled responses, this approach may suffice. However, when the body comes from the Internet, third parties, user uploads, proxies, or a malfunctioning service, the application needs a mechanism to check size **while receiving**.

**Concurrent load example:** suppose 200 requests simultaneously return a 10 MiB body. The payload data alone can occupy up to about **2,000 MiB** if all requests hold the full body in the heap, not counting HTTP byte buffers, String, JSON object graphs, logs, caches, and intermediate layers. **Having 1 GiB of heap does not mean the system can safely receive a 1 GiB body**.

### Three Frequently Overlooked Layers of Memory Amplification

1. **Byte[] from transport:** an 8 MiB body may be copied across multiple buffers/stages before the application uses it.
2. **String from charset decoding:** a UTF-8 payload converted to String; internal representation/copies depend on the JVM, charset, reference retention time, and parser.
3. **Object graph after parsing:** a JSON string is much smaller than the number of Map, List, String, wrapper, and metadata objects created by the parser; deeply nested data or data with many entries also causes CPU and stack exhaustion.

Therefore, **a byte-based limit is the first layer, not the only layer**. A production policy needs to define **maxEncodedBytes**, **maxDecodedBytes**, **maxItems**, **maxDepth**, **maxDuration**, **maxConcurrentResponses**, and a system-wide memory target.

## 2. BodyHandlers in Java 17 and Their Memory Characteristics

| BodyHandler | Result Type | Advantages | Risks Without Additional Limits |
|---|---|---|---|
| **ofString()** | String | Good for small text/JSON, convenient to use | Entire body is buffered, decoded, can cause OOM |
| **ofByteArray()** | byte[] | Preserves raw bytes | Buffers entire body in heap, no application ceiling |
| **ofInputStream()** | InputStream | Application reads incrementally | Must count bytes, close, timeout; buffering all read bytes can still OOM |
| **ofLines()** | Stream<String> | Consumes text line by line | A single overly long line or collecting all lines still consumes heap; stream must be closed |
| **ofFile(path)** | Path | Can avoid holding the whole body in heap | Disk quota/path/cleanup; can download indefinitely |
| **ofPublisher()** | Flow.Publisher<List<ByteBuffer>> | Reactive processing, backpressure | Subscriber can still buffer unboundedly or request too much |
| **discarding()** | Void | No need to keep payload | Still receives/consumes body; no built-in byte cap policy |
| **Custom BodySubscriber** | Custom design | Counts bytes, enforces cap, cancels when exceeded | Easy to get Flow contract/concurrency wrong; needs QA |

**Note:** the **BodyHandlers.ofString/ofByteArray/ofFile/ofInputStream** methods describe **how to handle the body**; there is no **maxBodyBytes** parameter on these factories in Java 17. You must not assume that HttpClient itself enforces a safe size limit suited to your application's needs.

### Code Reading Trap

~~~java
byte[] bytes = client.send(
        request, HttpResponse.BodyHandlers.ofByteArray()).body();

if (bytes.length > MAX_BYTES) {
    throw new IOException("too large");
}
~~~

**The pattern above is flawed for memory limiting**, even though it checks the size! By the time the `if` condition runs, Java **has already loaded the entire body into the heap**. For large payloads, the program can OOM **before it ever reaches the check**. To guarantee a maximum of MAX_BYTES, you must **count and block while streaming**, not just check `byte[].length` after completion.

Nor should you check **Content-Length <= MAX_BYTES and then call ofByteArray()** and claim a safe ceiling: the header may be missing (chunked transfer), the system may perform decompression, and another processing layer may introduce data larger than the expected limit. If a strict limit is needed, the subscriber/reader must enforce it on the actual bytes.

## 3. Content-Length: A Fast Check, Not a Guarantee

**Content-Length** in HTTP indicates the body length according to message framing when the header is present. It is useful for early rejection, but not every response includes it, and which part of the stack controls framing depends on the HTTP version/encoding.

### Case with Content-Length

~~~text
HTTP/1.1 200 OK
Content-Type: application/octet-stream
Content-Length: 10485760

... body ...
~~~

If the application accepts at most **128 KiB**, this header announces a **10 MiB** response upfront, so the response stream can be closed **immediately after reading headers**, without actively copying 10 MiB into the heap.

Java 17 HttpHeaders supports:

~~~java
OptionalLong announced = response.headers()
        .firstValueAsLong("Content-Length");

if (announced.isPresent()
        && announced.getAsLong() > MAX_BYTES) {
    throw new IOException("Response body too large");
}
~~~

This is an illustrative snippet, where **response** is an HttpResponse whose headers are available and **MAX_BYTES** is the configured limit. **Do not use this header to allocate a byte[] of the server-supplied length**. Even when the declared length is valid, a **ceiling on actual bytes received** must still be enforced.

### Case Without Content-Length or Using Chunked Transfer

HTTP/1.1 can send **Transfer-Encoding: chunked**, and HTTP/2 and streaming formats do not always require a single Content-Length. Not seeing Content-Length **does not mean the body is empty**. The server may emit data for minutes or with no clear ceiling, so a header pre-check may detect nothing.

~~~text
HTTP/1.1 200 OK
Transfer-Encoding: chunked

chunk 1 -> 64 KiB
chunk 2 -> 64 KiB
chunk 3 -> 64 KiB
...
~~~

You must continuously **accumulate bytes read** and **close/cancel** when about to exceed the threshold.

### Spoofed, Multiple, Negative, or Malformed Content-Length

- **Do not trust headers supplied by an untrusted peer** as proof that the payload is guaranteed to be small.
- An HTTP parser may reject messages with invalid framing or conflicting Content-Length/Transfer-Encoding; applications should not write a custom HTTP parser just to "let it slide".
- If a response has valid framing but undergoes upper-layer transformation/decompression, **the byte count after transformation may exceed the header**.
- Also check the **status code** before parsing the body; 4xx/5xx error responses can also be huge and may return untrusted HTML or JSON.
- If you want early rejection in **BodyHandler.apply(ResponseInfo)**, you can inspect headers when selecting the subscriber and apply policy before the body arrives; you still need to enforce actual bytes inside the subscriber to guard against missing or semantically altered headers.

**Distinguishing HTTP status 413:** **413 Content Too Large** usually refers to a **request body that the server refuses to accept**, not a standard Java exception when a client refuses to download an oversized response. In an HTTP client, the application typically throws an internal error categorized as **BODY_TOO_LARGE**, records a metric, and decides how to map it to its own API.

## 4. Overflow-Safe Rule for Counting Actual Bytes Received

A safe counter needs to manage **maxBytes** (a reasonable positive value) and **received** (initially 0). Before adding a chunk of length n:

~~~text
if n > maxBytes - received:
    reject and close
else:
    received += n
    append/process chunk
~~~

**Do not carelessly check `received + n > maxBytes`** when using numeric types that can overflow; the expression **`n > maxBytes - received`** avoids overflowing addition as long as the invariant **`0 <= received <= maxBytes`** holds. For very small data, `int` may suffice, but **`long`** is usually clearer for byte totals. Validate that `n` is non-negative and the limit is valid before using this in general-purpose code.

**A classic off-by-one bug:** when **`received == maxBytes`** and the source sends 1 more byte, it **must be rejected**. However, a body whose size is **exactly equal to maxBytes** must be accepted if your policy is "at most". This case requires its own unit test.

**Simply using a small read buffer does not impose a memory cap.** An application can use `byte[8192]`, read indefinitely, and unconditionally append to a `ByteArrayOutputStream`; the total byte count still grows without bound. The buffer size **is only the I/O chunk size**, not the total ceiling.

## 5. Runnable Java 17: Limiting the Body via BodyHandlers.ofInputStream

The following example creates an HTTP server on **127.0.0.1/ephemeral port** inside the JVM, with no external services. The server has four endpoints:

- **/small** returns the body **hello** (5 bytes), with an accurate Content-Length.
- **/declared** returns 256 bytes and Content-Length 256.
- **/chunked** returns 256 bytes but **does not advertise Content-Length**, using HTTP/1.1 chunked transfer.
- **/exact** returns **exactly 128 bytes**, matching the configured limit.

The client sets **MAX_BYTES = 128** per response. The **readBounded(...)** method uses `BodyHandlers.ofInputStream()`, rejects early when the declared length exceeds the limit, **counts every chunk actually read** to block the chunked case, and **closes the InputStream even when an exception is thrown**.

File **BoundedStreamDemo.java**:

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
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import java.util.OptionalLong;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class BoundedStreamDemo {
    private static byte[] repeat(int count) {
        byte[] value = new byte[count];
        Arrays.fill(value, (byte) 'X');
        return value;
    }

    private static void reply(HttpExchange exchange, byte[] bytes,
                              boolean chunked) throws IOException {
        exchange.sendResponseHeaders(200, chunked ? 0 : bytes.length);
        try (OutputStream output = exchange.getResponseBody()) {
            output.write(bytes);
        }
    }

    private static byte[] readBounded(HttpClient client, URI uri, long maxBytes)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(3))
                .GET().build();

        HttpResponse<InputStream> response = client.send(
                request, HttpResponse.BodyHandlers.ofInputStream());

        try (InputStream body = response.body()) {
            if (response.statusCode() != 200) {
                throw new IOException("Unexpected HTTP status");
            }

            OptionalLong declared = response.headers()
                    .firstValueAsLong("Content-Length");
            if (declared.isPresent() && declared.getAsLong() > maxBytes) {
                throw new IOException("Declared body exceeds limit");
            }

            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] chunk = new byte[64];
            long total = 0;
            int read;

            while ((read = body.read(chunk)) != -1) {
                if (read > maxBytes - total) {
                    throw new IOException("Actual body exceeds limit");
                }
                output.write(chunk, 0, read);
                total += read;
            }
            return output.toByteArray();
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getByName("127.0.0.1");
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);
        ExecutorService workers = Executors.newFixedThreadPool(2);
        server.setExecutor(workers);

        server.createContext("/small", exchange -> {
            try {
                reply(exchange, "hello".getBytes(StandardCharsets.UTF_8),
                        false);
            } catch (IOException ignored) {
                // Client may abort an oversized response.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/declared", exchange -> {
            try {
                reply(exchange, repeat(256), false);
            } catch (IOException ignored) {
                // A closed client stream can stop delivery.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/chunked", exchange -> {
            try {
                reply(exchange, repeat(256), true);
            } catch (IOException ignored) {
                // A closed client stream can stop delivery.
            } finally {
                exchange.close();
            }
        });
        server.createContext("/exact", exchange -> {
            try {
                reply(exchange, repeat(128), false);
            } catch (IOException ignored) {
                // A closed client stream can stop delivery.
            } finally {
                exchange.close();
            }
        });

        server.start();
        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY)
                    .connectTimeout(Duration.ofSeconds(2))
                    .build();

            byte[] small = readBounded(client, root.resolve("/small"), 128);
            System.out.println("Small: "
                    + new String(small, StandardCharsets.UTF_8));

            try {
                readBounded(client, root.resolve("/declared"), 128);
                System.out.println("Declared oversized: unexpected success");
            } catch (IOException expected) {
                System.out.println("Declared oversized: rejected");
            }

            try {
                readBounded(client, root.resolve("/chunked"), 128);
                System.out.println("Chunked oversized: unexpected success");
            } catch (IOException expected) {
                System.out.println("Chunked oversized: rejected");
            }

            byte[] exact = readBounded(client, root.resolve("/exact"), 128);
            System.out.println("Exactly at limit: " + exact.length + " bytes");
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

**Compile and run** with JDK 17 or newer (requires the **jdk.httpserver** module):

~~~bash
javac --release 17 --add-modules jdk.httpserver BoundedStreamDemo.java
java --add-modules jdk.httpserver BoundedStreamDemo
~~~

Stdout on successful run:

~~~text
Small: hello
Declared oversized: rejected
Chunked oversized: rejected
Exactly at limit: 128 bytes
~~~

Both rejection paths **are necessary**: **/declared** can be rejected before reading the body thanks to Content-Length; **/chunked** has no Content-Length to rely on, so **exceeding the limit is detected while reading actual bytes**. **/exact** shows that the comparison accepts a value equal to the ceiling.

### Source Code Analysis and What It Guarantees

1. **Loopback server/ephemeral port:** no dependency on the Internet, proxies, or fixed ports. **HttpServer.sendResponseHeaders(200, 0)** uses chunked transfer for responses with a body in this lab.
2. **BodyHandlers.ofInputStream():** HttpClient returns an HttpResponse with an InputStream; the application actively reads and processes each chunk. **HttpRequest.timeout(3s)** is a request timeout and should not be claimed to hard-limit the entire InputStream reading duration after HttpResponse has been returned.
3. **Early reject:** **HttpHeaders.firstValueAsLong("Content-Length")** is used as a hint; no `byte[]` is allocated with the server-suggested size.
4. **Actual-byte cap:** each chunk is appended only if **`read <= maxBytes - total`**, so **ByteArrayOutputStream never holds more than maxBytes of payload data** in this call.
5. **Try-with-resources:** both success and error paths close **response.body()**. When rejecting mid-stream, the connection may not be reused; that is a reasonable trade-off to protect the application.
6. **Status check:** the code rejects any status other than 200 instead of trying to parse malformed HTML/JSON errors. Production code can apply a separate limit for error bodies.
7. **Demo scope:** a 128-byte maximum is small enough for easy observation in the lesson. If a 100 MiB cap is set for hundreds of concurrent requests, buffering into `ByteArrayOutputStream` can still consume tens of GiB. Use **stream-to-file, an incremental parser**, or bounded concurrency for large payloads.
8. **Exceptions caught in main:** the oversized tests catch `IOException` thrown by the reader itself. In a real system, **do not catch all IOExceptions and always report BODY_TOO_LARGE**; distinguish IOExceptions caused by network, timeout, or closed streams from limit errors using a dedicated exception.

**Compiled with `javac --release 17` and run successfully**, stdout matches the four lines in a JDK with the `jdk.httpserver` module. This result demonstrates the byte-cap policy, **not a stress test** with unbounded requests.

## 6. Designing a Dedicated Exception for Oversized Bodies

In production, use an application-specific error type so "body exceeded cap" is not confused with "socket reset":

~~~java
public final class BodyTooLargeException extends IOException {
    public BodyTooLargeException(String message) {
        super(message);
    }
}
~~~

This is a class declaration snippet, **not a standalone program** (requires `import java.io.IOException` and a filename matching the public class if used separately).

When a header or actual byte count exceeds the ceiling, throw **BodyTooLargeException**; when **InputStream.read()** itself throws `IOException` due to network issues, preserve/wrap the cause. At the service layer, classify metrics, circuit breakers, and retries by error type. **Do not retry an oversized response with the same cap and repeatedly re-download it**, as the server will likely still return an oversized response and only increase load.

**Note on characters:** a **maxBytes** limit differs from a **maxCharacters** limit. UTF-8 can use multiple bytes for a single Unicode character, or contain control sequences and combining characters. If the application needs to limit character count or display length, perform a separate check on the decoded text after the byte cap, rather than replacing the byte cap with `String.length()`.

## 7. Runnable Java 17: Custom BodySubscriber Limiting Bytes in sendAsync

With **HttpClient.sendAsync(...)**, applications often want the subscriber to **inspect and block as ByteBuffers arrive**, avoiding waiting for the full body. Java 17 provides the **HttpResponse.BodySubscriber<T>** interface, which is a **Flow.Subscriber<List<ByteBuffer>>** that also exposes **CompletionStage<T> getBody()**.

The subscriber must manage four events:

- **onSubscribe(subscription):** store the subscription and call **request(1)** to request one **onNext** signal (the unit requested here is **a list of ByteBuffers**, not "1 byte").
- **onNext(List<ByteBuffer>):** check **remaining()** of each buffer before copying. If about to exceed the cap, call **completeExceptionally(...)** and then **subscription.cancel()**; if valid, copy and call `request(1)` again.
- **onError(Throwable):** complete the `CompletableFuture` exceptionally.
- **onComplete():** once the publisher signals the end of the body, return the **bounded** `byte[]`. For small-payload examples, `ByteArrayOutputStream` is used; for large payloads with high ceilings, replace storage with incremental processing or a file.

File **CappedSubscriberDemo.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
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
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;

public class CappedSubscriberDemo {
    private static final class CappedSubscriber
            implements HttpResponse.BodySubscriber<byte[]> {
        private final long limit;
        private final CompletableFuture<byte[]> result =
                new CompletableFuture<>();
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();
        private Flow.Subscription subscription;
        private long received;

        CappedSubscriber(long limit) {
            this.limit = limit;
        }

        @Override
        public CompletionStage<byte[]> getBody() {
            return result;
        }

        @Override
        public void onSubscribe(Flow.Subscription next) {
            if (subscription != null) {
                next.cancel();
                return;
            }
            subscription = next;
            next.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> data) {
            if (result.isDone()) {
                return;
            }
            try {
                for (ByteBuffer buffer : data) {
                    int count = buffer.remaining();
                    if (count > limit - received) {
                        result.completeExceptionally(
                                new IOException("Body exceeds byte cap"));
                        subscription.cancel();
                        return;
                    }
                    byte[] piece = new byte[count];
                    buffer.get(piece);
                    output.write(piece, 0, piece.length);
                    received += count;
                }
                subscription.request(1);
            } catch (RuntimeException error) {
                result.completeExceptionally(error);
                subscription.cancel();
            }
        }

        @Override
        public void onError(Throwable error) {
            result.completeExceptionally(error);
        }

        @Override
        public void onComplete() {
            result.complete(output.toByteArray());
        }
    }

    private static void reply(HttpExchange exchange, int size)
            throws IOException {
        byte[] body = new byte[size];
        Arrays.fill(body, (byte) 'Z');
        exchange.sendResponseHeaders(200, body.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(body);
        }
    }

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        server.setExecutor(pool);
        server.createContext("/small", e -> {
            try { reply(e, 5); }
            catch (IOException ignored) { }
            finally { e.close(); }
        });
        server.createContext("/large", e -> {
            try { reply(e, 256); }
            catch (IOException ignored) { }
            finally { e.close(); }
        });
        server.start();

        try {
            URI root = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort());
            HttpClient client = HttpClient.newBuilder()
                    .proxy(HttpClient.Builder.NO_PROXY).build();

            HttpResponse.BodyHandler<byte[]> capped =
                    info -> new CappedSubscriber(128);
            HttpRequest small = HttpRequest.newBuilder(
                            root.resolve("/small"))
                    .timeout(Duration.ofSeconds(3)).GET().build();
            HttpResponse<byte[]> ok = client.sendAsync(small, capped).join();
            System.out.println("Small body: " + ok.body().length + " bytes");

            HttpRequest large = HttpRequest.newBuilder(
                            root.resolve("/large"))
                    .timeout(Duration.ofSeconds(3)).GET().build();
            try {
                client.sendAsync(large, capped).join();
                System.out.println("Large body: unexpected success");
            } catch (CompletionException expected) {
                System.out.println("Large body: rejected");
            }
        } finally {
            server.stop(0);
            pool.shutdownNow();
        }
    }
}
~~~

Command to run on JDK 17+:

~~~bash
javac --release 17 --add-modules jdk.httpserver CappedSubscriberDemo.java
java --add-modules jdk.httpserver CappedSubscriberDemo
~~~

Stdout on successful run:

~~~text
Small body: 5 bytes
Large body: rejected
~~~

**Compiled with `javac --release 17` and run successfully.** For the 5-byte body, the subscriber receives it completely and returns a 5-byte `byte[]`; for the 256-byte body, **the bytes to copy exceed 128**, so the subscriber calls `completeExceptionally` and cancels the subscription, causing **sendAsync.join()** to complete with a **CompletionException** in the example.

### Analysis of Limits and Responsibilities of a Custom Subscriber

- **BodyHandler** receives **ResponseInfo** when response headers are available. In the demo, the handler simply creates a new subscriber per response: **`info -> new CappedSubscriber(128)`**. Production code can check status/Content-Length here to reject even earlier.
- **Each response has its own subscriber/state**, avoiding sharing `ByteArrayOutputStream`/`received` across requests. This enforces the cap per response.
- **onNext** takes **`List<ByteBuffer>`**; neither the list size nor each `ByteBuffer` size is guaranteed to be small. The demo checks **`remaining()` before allocating `byte[]`** so it does not copy a single large buffer that exceeds the cap.
- **request(1)** is a demand signal per the Flow API, **not a limit of 1 byte, 1 network packet, or 1 MiB**. Even when calling `request(1)`, you must still check all bytes in the list delivered to `onNext`.
- **subscription.cancel()** tells the publisher no further data is needed, but **does not guarantee that all bytes in the kernel or on the network are immediately reclaimed**. Some data may already have arrived before cancellation is processed.
- **CompletionStage<byte[]> getBody()** notifies `HttpClient` when the body completes or fails. If the cap is exceeded, the `CompletableFuture` fails; **you must not return a truncated `byte[]` and silently treat it as a full valid response**.
- **onError** and **onComplete** must resolve the result exactly once; `CompletableFuture` has idempotent semantics for subsequent completions. Production code should log the cause and clean up according to policy.
- **Code scope:** the demo uses `ByteArrayOutputStream` for a 128-byte cap and only two requests. A production subscriber needs to define positive limits, handle stream cancellation, concurrency, exception types, downstream parsing, status/error bodies, timeouts, and total quotas. Do not treat this example snippet as proof of a production-hardened HTTP client SDK.

**Difference from the InputStream example:** the custom subscriber enforces the ceiling **as chunks arrive at the subscriber** and can be used with `sendAsync` without blocking the caller thread on `InputStream.read`. However, **heavy callback processing** can stall `HttpClient`'s executor; keep `onNext` handling short, memory-bounded, and non-blocking inside callbacks. When CPU-bound parsing is needed, offload work to a bounded executor while preserving backpressure.

## 8. Do Not Confuse a Per-Response Limit with a System-Wide Limit

A 5 MiB body cap only limits **one** response. If the app has 1,000 concurrent calls, the theoretical upper bound of held payloads can reach around **5 GiB**, excluding overhead. Therefore, a production resource budget needs three layers:

1. **Per-response cap:** for example, a JSON endpoint may return at most 256 KiB, an export endpoint 10 MiB, etc. Numbers must be based on schema/service contracts, not copied from examples.
2. **Concurrent operation budget:** limit the number of active responses, total buffered bytes, and queue depth using semaphores, bounded executors, and admission control.
3. **Global process memory budget:** compare caps and concurrency against heap size, String/JSON object overhead, caches, thread stacks, direct memory, HTTP library buffers, and GC safety margins.

### Simple Budget Inequality

~~~text
MAX_ACTIVE_RESPONSES * MAX_HEAP_BODY_BYTES_PER_RESPONSE
    + parser/object/copy overhead
    + existing application heap usage
    <= safe heap budget
~~~

This is a **budgeting model**, not a formula that predicts exact JVM heap usage. When data does not need to be kept in RAM, use a streaming processor or managed file writes to reduce body retention.

**ByteArrayOutputStream has an internal buffer:** even when writing at most `MAX_BYTES`, the structure can expand its capacity, and calling **`toByteArray()`** creates another copy. Thus, for large caps you must still account for **allocation/copy amplification**, and not treat the data byte limit as an exact byte-for-byte memory limit. To reduce heap usage, parse incrementally or stream to disk/a controlled destination.

### Do Not Retain References for Long

A response body parsed into a large object may remain retained via caches, `CompletableFuture`s, logs, queues, metric labels, or closures; GC cannot reclaim it while live references remain. The response lifecycle design must be explicit: read, validate, process, close stream, release buffers, and do not accumulate entire object graphs in a global `List`.

## 9. Compression: Limit Bytes Before and After Decompression

With **Content-Encoding: gzip/br/deflate** or ZIP archives inside a response, **the payload transmitted over the network can be much smaller than the decompressed data**. A compressed file of a few kilobytes can expand into hundreds of megabytes or multiple gigabytes in an intentional attack (*decompression bomb/zip bomb*).

**Do not place a limit solely on the gzip Content-Length and skip checking after decompression.** For example:

~~~text
HTTP Content-Length (compressed bytes):       75 KiB
maxWireBytes:                                 1 MiB   => passes step 1
Decompressed UTF-8/body:                      90 MiB
maxDecodedBytes:                              4 MiB   => MUST block at step 2
~~~

These numbers only illustrate the risk of a high compression ratio, not the output of any specific file.

### Two-Counter Design

~~~text
network response body
    |
    v
count compressed/raw entity bytes <= maxWireBytes
    |
    v
decompressor (if Content-Encoding is valid and allowed)
    |
    v
count decompressed bytes <= maxDecodedBytes
    |
    v
parse JSON/XML/CSV... with maxDepth/maxItems/maxTextLength
    |
    v
application object / incremental processing
~~~

**Java 17 HttpClient should not be assumed to auto-decompress every Content-Encoding and enforce your desired decoded size ceiling.** When an application uses `GZIPInputStream`, an HTTP library, a proxy, or a JSON deserializer with auto-decompression, you must know whether the byte counter sits **before** or **after** the transform. If using a library that auto-decompresses, verify its limit mechanisms and test with high-ratio compressed payloads.

For ZIP archives with multiple entries, limit **total uncompressed bytes**, **entry count**, **compression ratio**, **directory depth**, **filenames/path traversal**, and **processing time**; do not check only the size of the received ZIP file.

### Gzip/InputStream Illustration

~~~java
try (InputStream compressed = response.body();
     GZIPInputStream decoded = new GZIPInputStream(compressed)) {
    // Count bytes read from decoded: these are uncompressed bytes.
    // Read up to maxDecodedBytes; abort immediately when exceeding the ceiling.
}
~~~

This is an **API snippet**, not a standalone program (requires `java.util.zip.GZIPInputStream` and a response with matching `Content-Encoding`). A `maxWireBytes` counter must wrap the `InputStream` **before** `GZIPInputStream` if you want to limit compressed bytes as well; a `maxDecodedBytes` counter is placed when reading from `GZIPInputStream`. Do not trust peer-supplied encoding names without validating them against policy.

**Content-Length trap:** the header of a compressed HTTP response typically indicates the compressed entity byte count (if present), **not the byte count of the JSON/XML after decompression**. Checking it and then reading the entire decompressed body into a `String` can still cause OOM.

## 10. Using BodyHandlers.ofFile and Streaming-to-Disk Properly

**BodyHandlers.ofFile(path)** writes the response body to a file, avoiding holding the whole body in a `byte[]`/`String`. This is a good option for policy-governed large downloads, but **it is not free**:

- Without a disk quota, a remote peer can fill up the disk or inodes.
- If the path is constructed from a user-supplied filename without validation, there is a risk of **path traversal, overwriting, or writing to sensitive locations**.
- If a download fails midway, an **incomplete file** may remain that needs cleanup.
- If the file is persisted, you must verify `Content-Type`, checksum/signature, expected size/format, and quarantine/scan according to data type.
- If multiple downloads run concurrently, a **global disk budget**, queue, and retention cleanup are required.

**Strict implementation** when a maximum size is needed: choose a safe server-generated temp path, open the output with appropriate flags (avoiding overwrites), stream the body through a small buffer, and **count bytes before writing each chunk**; if the limit is exceeded, close input/output, delete the temp file per policy, and record a metric. Rename the temp file to the target name via an atomic operation only after reading completes, checksum matches, and validation succeeds.

### BodyHandlers.ofFile Has No maxBytes Parameter

~~~java
HttpResponse<Path> response = client.send(
        request, HttpResponse.BodyHandlers.ofFile(targetPath));
~~~

This is only an illustrative snippet, **not a complete bounded download pattern**. By the time it completes, the file may already have been written larger than intended if you only check `Files.size(path)` afterward. To cap **while receiving**, use an `InputStream` with bounded copy, a custom subscriber that writes to a file under a quota, or a downloader library that supports hard limits and cleanup.

### Temp Files and Path Safety

- Create a managed directory; do not let callers choose arbitrary absolute paths.
- Use random temp names and minimal file permissions; restrict symlinks/path traversal when uploads/downloads have security impact.
- Only **move/commit** the file once size, checksum, content type, and response status checks have succeeded.
- If the request is cancelled/times out/exceeds the limit, ensure `finally` closes streams and cleans up the temp file.
- For cloud object storage, consider multipart/streamed uploads and quotas; there is no need to buffer the entire response before pushing to storage.

## 11. Streaming JSON/XML/CSV Does Not Make the Parser Automatically Safe

Another way to avoid oversized `String`/`byte[]` values is to use a **streaming parser**: reading tokens or records incrementally and processing with bounded memory. However, you must enforce limits **while parsing**, rather than trusting the parser to protect itself.

### JSON

- Limit **raw bytes** and **decoded bytes** before the parser.
- Limit **nesting depth**, **number of fields**, **array length**, **string length**, and **numeric precision** if the library supports them.
- Do not build a `Map`/`List` containing the entire response if you only need aggregates or to filter a few fields.
- For very large JSON arrays, the protocol should support **pagination, NDJSON, or streaming items**; a monolithic array makes O(1) memory hard to maintain if the application needs to reorder everything.
- Be careful with Unicode surrogates; do not arbitrarily slice UTF-8 bytes and decode them into independent `String` chunks when a multi-byte character spans a buffer boundary.

### XML

- Limit bytes, element depth, and entity expansion; disable/limit **external entities** when not needed to prevent XXE/entity-expansion attacks.
- Use SAX/StAX streaming where appropriate; a DOM parser builds the entire tree on the heap and is inherently unsuitable for huge XML.

### CSV/NDJSON/Log Lines

- Limit **bytes per line**, **line count**, **total bytes**, and **field count**.
- Using **`BufferedReader.readLine()`** without a line-length ceiling can still create a massive `String` before you have a chance to inspect it. If the source is untrusted, use a reader/parser with a **line-length cap** enforced while reading.
- If a single record can reach several MB, a streaming parser still needs a per-record limit.

**Do not equate "holding only one record" with "heap is always small"**: if a single record has unbounded size, it alone is enough to exhaust the heap.

## 12. Timeouts, Cancellation, and Response-Size Limits Are Orthogonal Axes

**A byte limit does not stop a server from trickling 1 byte per minute.** A body under 1 MiB can still take hours to finish. Likewise, a 2-second timeout does not guarantee low memory usage if the server sends 200 MiB in 1 second.

At minimum, you need:

1. **Max bytes:** body cap before decoding and/or after decompression.
2. **Per-request response timeout:** `HttpRequest.Builder.timeout(Duration)` limits the response wait time per the Java 17 contract.
3. **Overall operation deadline:** total time for reading the stream, parsing, validating, downstream writing, and retries.
4. **Idle/read progress timeout:** a policy to abort when no valid bytes/records arrive within a specified interval (if the protocol needs it).
5. **Cancellation/close:** when a ceiling or deadline is exceeded, release the response body/subscription/connection and backend resources.

### Important Note for BodyHandlers.ofInputStream

`HttpClient` can return `HttpResponse<InputStream>` **before the entire body has been consumed**; if the application subsequently reads the body over a long period, do not assume `HttpRequest.timeout` still covers the entire `InputStream` consumption. To bound long reads, use an external deadline, cancellation, and lifecycle-aware I/O interruption/closing.

**`Future.get(timeout)`** or **`CompletableFuture.orTimeout`** only bounds waiting for/completing the future; it **does not guarantee that bytes in flight over the network are reclaimed or that the server stops processing**. On timeout, cleanup must be actively orchestrated, especially when an `InputStream` or an open file is involved.

### Do Not Retry Infinitely After an Oversized Body

If a server returns a 50 MiB payload while the app only allows 1 MiB, immediately retrying the same request will keep downloading the 50 MiB payload and incur extra cost. Classify **BODY_TOO_LARGE** as a policy/non-retryable error unless there is a specific reason (for example, the request is adjusted to a paginated range with a different limit). For network/timeout errors, retries need **bounded attempts**, backoff, jitter, an overall deadline, and idempotency if the operation has side effects.

## 13. HTTP Caching, Redirects, and Error Responses Need a Unified Policy

### Redirects

An `HttpClient` can be configured with `followRedirects`. If request A returns 302 to location B, B may return a large untrusted body. Limits must apply to **the final response and any responses processed by the application**, not merely trusting `Content-Length` from the initial host. Protect against **SSRF/redirect-to-internal-address** in systems that accept user-supplied URLs.

### Error Bodies

A 500/502/429 response can contain very long error HTML or debug output. If the application calls **`ofString()`** to log the full error body, an attacker can still exploit it to exhaust heap or log storage. Set a separate cap for **error bodies**, typically smaller than for success bodies; log a bounded preview and mask secrets.

### Cache

A cache storing `String`/`byte[]` of every HTTP response can retain data long after a request finishes. You need **max entry bytes**, **max aggregate bytes**, TTL, an admission/eviction policy, and bounded key/cardinality. Responses that fit the per-item cap can still OOM an unbounded aggregate cache.

### Content-Type

**`Content-Type: application/json`** does not prove the payload is valid or small JSON. The header may be spoofed, the charset wrong, or the schema mismatched. Use parser validation, data limits, and reject on mismatch; do not rely on `Content-Type` to arbitrarily relax byte caps.

## 14. Memory-Safe Design by Endpoint Type

Not every endpoint should have the same limit:

| Response Type | Recommended Strategy | Additional Constraints Needed |
|---|---|---|
| Small config JSON | Bounded InputStream/custom subscriber then parse | Max bytes, max depth, schema, deadline |
| Paginated API list | Limit each page, hold one page at a time during processing | Max page count, total item count, rate limit |
| Large CSV/NDJSON | Incremental decoder/parser, process record by record | Max line length, bytes, records, time |
| PDF/image download | Bounded streaming to temp file | Disk quota, MIME sniffing, checksum, virus scan if needed |
| Gzip JSON | Byte cap both before and after decompression | Compression ratio, parser depth, CPU budget |
| Unknown third-party endpoint | Reject via allowlist, strict size/time quota | Proxy, redirect, SSRF, auth, egress policy |
| Error response for logging | Bounded preview and metadata | Do not log secrets/unbounded bodies |

**There is no single `maxBytes` that is "right for every project".** An API returning 10 KiB JSON might choose a cap of a few hundred KiB; a 200 MiB report requires a different streaming/disk design. Choose based on the endpoint contract, expected p99 size, content type, concurrency, and actual available resources.

### Pagination Is a Key Optimization

If an API supports **limit/pageSize/cursor**, request small pages instead of downloading a massive JSON array. However, **server-side `pageSize` does not replace a client-side byte cap**, because a single record or a buggy server can still return an oversized payload. Pagination and byte caps are complementary layers of defense.

### Range Requests Are Not an Exact Slicing Guarantee

HTTP **Range** can be used to request a portion of data, but a server **may not support it or may ignore Range** and return 200 with the full resource. The client must check for **206 Partial Content**, **Content-Range**, expected offset, and still enforce an actual byte cap. Do not rely on the `Range` header as the sole memory limiter.

## 15. Backpressure and Flow.Subscriber: `request(1)` Does Not Mean One Byte

In the Java Flow API, **`Subscription.request(n)`** expresses demand for **n `onNext` signals**, not n bytes. When a `BodySubscriber` receives **`List<ByteBuffer>`**, a single `onNext` signal can contain multiple buffers and many bytes. Therefore:

~~~text
request(1)
    -> onNext([ByteBuffer 4 KiB, ByteBuffer 8 KiB, ...])
    -> count all remaining bytes
    -> reject if total > cap
    -> otherwise process and request(1) again
~~~

**The subscriber must enforce the byte limit inside `onNext`**, regardless of how many `n` were requested. If a subscriber calls **`request(Long.MAX_VALUE)`** for unbounded demand and enqueues every chunk into an unbounded queue, it can easily OOM even though the producer uses the Flow API.

### Practical Rules

- Do not call **`onNext`** directly from application code; the publisher is responsible for invoking it per the Flow contract.
- Do not share the publisher's `ByteBuffer` for async processing elsewhere without clear ownership/copying/lifecycle management.
- Complete the **`getBody()` stage** when the body finishes or fails; do not leave the future pending forever upon rejection.
- When exceeding the cap, **cancel the subscription** and complete exceptionally; do not return a truncated body and treat it as valid JSON.
- Request more signals only when the system has processing capacity; if a downstream queue is full, pause requesting instead of buffering unboundedly.
- If callbacks require heavy parsing/blocking I/O, use a bounded executor and do not block `HttpClient`'s dispatch threads.
- Provide close/cancel/cleanup mechanisms if the application discards the future or the overall deadline expires.

These requirements are concurrency/backpressure principles; `CappedSubscriberDemo` only models the byte cap and does not claim to solve every production edge case of Flow.

## 16. Testing Response Limits: Required Test Matrix

| Test | Input Response | Expected Safe Behavior |
|---|---|---|
| Below threshold | 5 bytes, cap 128 | Processed normally |
| At threshold | Exactly 128 bytes, cap 128 | Accepted, no off-by-one bug |
| 1 byte over threshold | 129 bytes, cap 128 | Rejected before appending the 129th byte |
| Large Content-Length | Declared 256, cap 128 | Can reject immediately after headers |
| Chunked without Content-Length | Chunked 256, cap 128 | Rejected when actual bytes exceed cap |
| Small header, expanding decoder | Small gzip, large decoded | Blocked by `maxDecodedBytes` |
| Body with one ultra-long line | NDJSON/CSV without newline | Line length limited before creating oversized String |
| Infinite trickle stream | Total bytes still below cap | Stopped by deadline/idle timeout |
| Many concurrent responses | N requests each near cap | Protects total heap budget, queue/concurrency |
| Oversized error response | HTTP 500 with huge HTML | Does not log/read unbounded error body |
| Redirect to another host | 302 to large response | Applies same policy/allowlist/SSRF protection |
| Client timeout/cancel mid-stream | Future/stream pending | Closes/cancels and cleans up buffers/temp files |
| Oversized file download | Body larger than disk quota | Stops writing, deletes temp file, does not commit |
| Deep/too many parser items | Moderate JSON but deeply nested | Parser depth/complexity limits enforced |

**Local server tests can predict exact byte counts**, but should not assert millisecond-exact network timings. When adding concurrency and backpressure, measure both **peak heap/GC pressure** and **request completion time** under authorized load. Never send huge payloads to public services just to test limits.

### Operational Metrics

Record **`response_bytes_received`**, **`Content-Length` declared**, **`body_limit_bytes`**, **`BODY_TOO_LARGE` rejections**, **`decoded_bytes`**, **`compression_ratio`**, **`active_response_streams`**, **`buffered_bytes_global`**, **`stream_duration`**, **`timeouts`**, **`cancellation_count`**, **`file_cleanup_failures`**, and **`GC pause/p95/p99 latency`**.

You can use **per-endpoint/body-policy labels**, but must bound cardinality: do not include full URLs with user IDs/tokens or request bodies in metric names. Log sufficient correlation IDs and failure reasons; mask secrets and avoid logging entire large responses.

## 17. When Responses Come from APIs You Control

If you control both client and server, **the best solution often starts with protocol design**:

- Design **pagination** or streaming instead of unbounded JSON arrays.
- Enforce **maxResults/pageSize**, byte/record limits, and deadlines on the server; return structured errors when requests ask for too much data.
- Provide an **accurate `Content-Length`** when the size is known, while the client still checks actual bytes.
- Compress responses when appropriate, while capping decompressed size on the receiving side.
- Limit **records/bytes/time** during serialization so the server does not OOM itself while building the response.
- Send small error statuses without attaching stack traces or massive sensitive data.
- Use backpressure over HTTP/2 or reactive pipelines; do not merely shift data accumulation from the client to the server's queue.
- Establish SLOs for response size/latency and run two-sided contract tests.

**An API advertising `Content-Length <= 64 KiB` is not enough to drop the client-side ceiling.** The network, proxies, new code versions, or server bugs can still violate the contract.

## 18. Common Programming Mistakes and Fixes

### Mistake 1 — Buffering Everything Before Checking

Wrong: using **`ofByteArray()/ofString()`** for an untrusted source, then checking length. Fix: enforce the limit in a subscriber or bounded `InputStream` **before creating `byte[]`/`String`**.

### Mistake 2 — Blindly Trusting Content-Length

Wrong: rejecting only if `firstValueAsLong > cap` and then reading the rest unboundedly. Fix: **count actual bytes read**, supporting missing headers and chunked transfer.

### Mistake 3 — Confusing Chunk Size with Total Size

Wrong: choosing a 4 KiB buffer and appending indefinitely to a `ByteArrayOutputStream`. Fix: maintain a total byte counter and a rejection policy at the threshold.

### Mistake 4 — Ignoring Decompressed Data Volume

Wrong: 100 KiB gzip is under the cap, decompresses to 500 MiB, and then parses JSON. Fix: **two ceilings (encoded/decoded)** and parser limits.

### Mistake 5 — Failing to Close InputStream on Exception

Wrong: throwing when the cap is exceeded but leaving the stream open. Fix: **try-with-resources**, close/cancel, and cleanup.

### Mistake 6 — Streaming to File Without Limits

Wrong: assuming `BodyHandlers.ofFile` is safe enough by itself. Fix: enforce disk/body quotas **while writing**, use temp files, clean up, and commit safely.

### Mistake 7 — Truncating the Body and Treating It as Complete JSON

Wrong: taking the first N bytes and returning success if the JSON parser does not fail immediately. Fix: **reject oversized** responses unless the protocol explicitly supports **truncation** with clear markers and checksum/partial semantics.

### Mistake 8 — Not Limiting Error Responses

Wrong: HTTP 500 returns tens of MiB of HTML and the code logs the entire body. Fix: limited error preview, masking, and short policy.

### Mistake 9 — Limiting Only One Request, Forgetting Concurrency

Wrong: max 10 MiB per response, 1,000 parallel requests. Fix: semaphores, max aggregate buffered bytes, load shedding, and bounded queues.

### Mistake 10 — Setting Only a Timeout, Without Byte Limits

Wrong: `HttpRequest.timeout(2s)` and assuming the body cannot OOM. Fix: time budget **and** byte budget are two independent limits.

### Mistake 11 — Treating `Flow.Subscription.request(1)` as 1 Byte

Wrong: handling `onNext` without counting `List<ByteBuffer>` bytes. Fix: count `buffer.remaining()` before each copy, cancel on limit.

### Mistake 12 — Not Limiting Item Count and Parser Depth

Wrong: body is small and under the cap, but the JSON parser creates an unbounded object graph relative to application needs. Fix: schema/record/depth/token limits, streaming parsing, and CPU quotas.

## 19. Hands-On Exercises

### Exercise A — Exact One-Byte Boundary

Modify **BoundedStreamDemo** so the server returns **127, 128, and 129 bytes** on three endpoints. Verify that 127/128 are accepted and 129 is rejected. Explain why the right condition is **`read > maxBytes - total`**, not **`read >= maxBytes - total`**.

### Exercise B — Removing the Content-Length Check

Temporarily remove the header precheck from `readBounded` while keeping the actual-byte cap. Re-run the **/declared** endpoint; what causes the response to still be rejected? Because the actual-byte cap remains. Explain the **performance/bandwidth** benefit of the precheck for early rejection when the header is trustworthy.

### Exercise C — Chunked Stream

Using **/chunked**, add chunk count/size logging on the server and measure how many bytes reach the consumer before aborting. Do not hardcode the number of `InputStream.read` calls because read boundaries can vary per run.

### Exercise D — Without ByteArrayOutputStream

Modify `readBounded` to read each chunk and **compute a SHA-256 digest** without retaining the full payload. Keep the 128-byte cap and print the hex checksum of the small body. Compare peak heap against buffering the entire body.

### Exercise E — Custom BodySubscriber

Run **CappedSubscriberDemo**, changing 128 to 5. Confirm that the 5-byte response succeeds and the 256-byte response is rejected. Explain that **`request(1)`** counts **onNext signals**, not bytes.

### Exercise F — Disk Quota

Build a bounded downloader to a controlled temp path using `byte[8192]` and a total byte counter before writing. When the cap is exceeded, abort, close streams, and delete the temp file. Verify that no incomplete file remains after an error.

### Exercise G — Gzip Decompression Bomb

Create a small gzip sample containing repetitive data in a local environment, with `maxWireBytes` large enough to fit it but `maxDecodedBytes` low. Ensure the decoder stops when uncompressed bytes exceed the ceiling. Do not use massive data or run outside an authorized environment.

### Exercise H — Concurrency Budget

Suppose 256 MiB of usable heap remains, each response needs at most 2 MiB of raw bytes, and the parser may use several times that amount. Propose a maximum number of concurrent requests with headroom, then apply a semaphore/bounded queue. Use a small load test to observe GC and peak heap rather than evaluating by theoretical formula alone.

### Exercise I — Error Body

Have the server return HTTP 500 with 1 MiB of HTML, while the client logs **at most 1 KiB inspected** and does not parse it as JSON. Distinguish a "truncated error preview" from a "valid HTTP body processed in full"; do not drop protections just because the status is not 200.

### Exercise J — Streaming Parser

Have the server return NDJSON with many small records and one ultra-long record. Use a streaming decoder to count records, `maxTotalBytes`, and `maxRecordBytes`, rejecting the long record before creating an oversized `String`.

## 20. Self-Check Questions

**1. Why is `ofString()` dangerous with untrusted sources?** Because it can buffer the entire body into a `String` with no business-level byte cap.

**2. Is `ofByteArray() + if (length > cap)` heap-safe?** No; the large `byte[]` allocation happens **before** the check.

**3. Is `Content-Length` sufficient as a limit?** No; it can be missing/chunked or fail to cover decompression. You must count actual bytes.

**4. Does reading an `InputStream` with a 4 KiB buffer mean total memory is 4 KiB?** Not if you keep appending into a `ByteArrayOutputStream`/`List`; a total ceiling is needed.

**5. What is the right condition when `total` bytes have been received and `n` more bytes are read?** **`n > cap - total`** to reject before copying, with invariant `0 <= total <= cap`.

**6. Is a response equal to the cap valid?** Yes, under an "at most `cap` bytes" policy; reject only when **exceeding** the cap.

**7. Why does a compressed body need two limits?** A small compressed size does not guarantee a small decompressed size; both `maxEncodedBytes` and `maxDecodedBytes` are needed.

**8. Does `ofFile()` protect the disk from unbounded payloads?** No; you must use a disk quota, a byte cap while writing, and cleanup.

**9. Does `request(1)` in Flow mean downloading exactly one byte?** No; it requests one `onNext` signal, which can carry a large `List<ByteBuffer>`.

**10. Should `BodySubscriber` return truncated data or fail when exceeding the cap?** It should fail/cancel, not treat truncated data as a complete response.

**11. Can `HttpRequest.timeout` replace a byte cap?** No. High network speeds can transfer a huge number of bytes before the timeout fires.

**12. Is a 1 MiB per-response cap with 10,000 parallel requests enough to protect the heap?** No; max concurrency/aggregate buffered bytes are required.

**13. Why must JSON have depth/item limits after reception?** Because the object graph and parser CPU can far exceed the raw byte size.

**14. Why must `response.body()` be closed when exceeding the threshold?** To release stream/connection resources and stop receiving unnecessary data.

**15. Is HTTP 413 Java's standard client oversized-download exception?** No; 413 is an HTTP status code typically used for oversized request content.

**16. If `BodyHandler` returns an `InputStream`, has the body definitely finished being read when `HttpResponse` appears?** No; the application is still responsible for reading/closing it and setting a separate deadline for stream consumption.

## Official Java 17 and HTTP Documentation

- **Java SE 17 — HttpResponse.BodyHandlers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html
- **Java SE 17 — HttpResponse.BodySubscribers:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html
- **Java SE 17 — HttpResponse.BodySubscriber:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html
- **Java SE 17 — HttpClient:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Java SE 17 — HttpHeaders:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpHeaders.html
- **Java SE 17 — Flow.Subscription:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- **Java SE 17 — InputStream:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html
- **RFC 9110 — HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9112 — HTTP/1.1 Message Framing:** https://www.rfc-editor.org/rfc/rfc9112

**Takeaway:** **Do not buffer unbounded HTTP responses into the heap** with `ofString`/`ofByteArray` before checking. Use **Content-Length for early rejection**, but **always count actual bytes received**; for large streams, process incrementally or write to a quota-controlled file instead of collecting everything into an unbounded `String`/`List`/`ByteArrayOutputStream`. For compressed data, check **both encoded and decoded bytes**. Combine **body byte caps, parser limits, total concurrency/memory budgets, deadlines, backpressure, cancellation, and cleanup** to protect the system against oversized payloads, malfunctioning servers, and intentional overload data.