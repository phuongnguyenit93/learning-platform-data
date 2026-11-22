# Draining, Closing, or Cancelling Streaming HTTP Response Bodies to Release Resources in Java

When making HTTP calls with `java.net.http.HttpClient`, developers often focus on the status code and the data they need to retrieve. However, with **streaming response bodies**, receiving an `HttpResponse` object **does not mean the response has been completely read**. If the application only inspects the headers/status and abandons the `InputStream`, `Stream<String>`, or reactive `Publisher` without consuming or cancelling it properly, the HTTP exchange may continue holding buffers, subscriptions, connections, or other resources. When repeated across many requests, the consequences can include reduced connection reuse, prolonged pending responses, slowdowns, rising memory usage, pool/stream exhaustion, or timeouts on subsequent requests.

The core takeaway of this lesson: **every streaming body must have an owner and a clear termination path**. After receiving a response, choose **one of three approaches**, corresponding to the API:

1. **Read to the end (EOF / terminal signal)** when you still want the full content and the size/rate is reasonable.
2. **Close the body stream** when you no longer want to read (`InputStream.close()` or `Stream.close()`).
3. **Cancel the subscription** for a reactive publisher (`Flow.Subscription.cancel()`), or cancel an async exchange **before the future completes** per the contract.

Reading to completion generally gives the implementation an opportunity to reuse the HTTP connection; **early close/cancel** is the way to release responsibility for processing a response that is no longer needed, though it may prevent the connection from being reused. **There is no rule to “always download every body just to save a connection”**: for unbounded, very large, or slow-peer bodies, continuing to download can cost far more bandwidth, CPU, and time than opening a new connection.

This lesson uses **Java 17+**, the `java.net.http` module (available since Java 11), along with two standalone programs that run on loopback without Internet access: one program thoroughly testing `InputStream`/`ofLines` and another practicing `Flow.Publisher` with completion/cancellation.

## 1. The HTTP Response Lifecycle Differs from the Java Object Lifecycle

A request may go through:

~~~text
Create HttpRequest
       |
HttpClient.send / sendAsync
       |
Receive status + headers
       |
       +------ BodyHandlers.ofString()/ofByteArray()
       |            |
       |       body is fully collected before the response is ready
       |            |
       |          DONE
       |
       +------ BodyHandlers.ofInputStream()
       |            |
       |       HttpResponse<InputStream> has been returned,
       |       but response bytes may not have arrived completely yet
       |            |
       |       READ TO EOF  ---- or ---- CLOSE EARLY
       |
       +------ BodyHandlers.ofLines()
       |            |
       |       Stream<String> still reads line by line from the HTTP body
       |            |
       |       CONSUME ALL ---- or ---- Stream.close()
       |
       +------ BodyHandlers.ofPublisher()
                    |
               Flow.Publisher<List<ByteBuffer>>
                    |
                SUBSCRIBE EXACTLY ONCE
                    |
              request items -> onNext...
                    |
               onComplete/onError ---- or ---- cancel
~~~

`HttpResponse<T>` has `body()` returning the type `T` selected by the `BodyHandler`. Some bodies are **completed values** (`String`, `byte[]`, `Path` after `ofFile`); others are **portals for reading further data** (`InputStream`, `Stream<String>`, `Flow.Publisher`). The `HttpResponse` object in Java 17 **does not have `close()`** and is not `AutoCloseable`; close/consume **the body object itself**.

| BodyHandler | `HttpResponse.body()` Type | When Response Is Ready | What the Caller Must Do |
| --- | --- | --- | --- |
| `ofString()` | `String` | After the body has been read/decoded | Process the data; no stream to close, but must limit input size |
| `ofByteArray()` | `byte[]` | After the body has been fully read | Manage memory; no body stream to close |
| `discarding()` | `Void` | After the body has been consumed and discarded | Use when you know upfront you do not need the body; **still incurs download/consumption cost** |
| `ofFile(path)` | `Path` | After the body has been written to the file | Manage output file/quota/partial file on error |
| `ofInputStream()` | `InputStream` | **After headers**, before the body is necessarily complete | **Read to EOF or close** |
| `ofLines()` | `Stream<String>` | **After headers**, the body may still be streaming | **Consume all lines or close the stream** |
| `ofPublisher()` | `Flow.Publisher<List<ByteBuffer>>` | **After headers**, the body may still be streaming | **Subscribe once, consume to terminal or cancel** |

**The status code does not change the cleanup obligation.** A 404 or 500 response can still carry a full response body; reading `response.statusCode()` and then `return`ing without closing `body()` is the same ownership bug as with a 200 response.

### 1.1. Two Different Kinds of Completion

Example:

~~~java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());
System.out.println(response.statusCode());
// THIS LINE DOES NOT PROVE the body has been read to EOF.
~~~

`HttpClient.send(...)` here has returned the headers/status and a readable stream, **not necessarily having received the entire body**. If you subsequently forget to handle the stream, the response exchange may retain resources. Conversely:

~~~java
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
// response.body() at this point is a String that has already been created.
~~~

These two snippets are **illustrative excerpts placed inside a Java method**, assuming `client`/`request` are available, `java.net.http.*` is imported, and `IOException`/`InterruptedException` are handled. With `ofString`, the library collects the body before completing the response; therefore it should be avoided for unbounded payloads. With streaming, the library hands over consumption responsibility to the caller earlier.

## 2. Choosing “Read to End” vs. “Close/Cancel” Based on Actual Data

| Case | Primary Decision | Why |
| --- | --- | --- |
| Small, valid response; the application truly needs every byte | Read to `-1`/EOF | Ensures complete data and enables connection reuse |
| Large JSON/file stream that must be fully processed | Read via chunked/streaming parser with a size cap | Avoids holding the entire body in RAM |
| Only the first 2 lines are needed, or sufficient info was found | Close `InputStream` / `Stream` right after the needed part | Do not download indefinitely just hoping to reuse the connection |
| Status 404/500, small error detail needed | Read capped error body and then to EOF if appropriate | Can capture diagnostic info while avoiding an abandoned exchange |
| Non-success status and body could be very large | Read only the needed error portion, then close | Protects memory/bandwidth, accepting loss of reuse |
| Body not needed from the outset | `BodyHandlers.discarding()` or an appropriate cancel policy | Simplifies cleanup, though `discarding` still receives/drops data |
| Reactive subscriber processes everything | Request items, receive `onComplete`/`onError` | Terminal signal completes the subscriber protocol |
| Reactive subscriber cannot continue processing | `subscription.cancel()` | Signals to stop consuming; do not wait for `onComplete` |
| Async request still pending and user withdraws request | `future.cancel(true)` on the future returned by `sendAsync` | Attempts to cancel the HTTP exchange, best-effort |
| Streaming future has already completed and handed out `InputStream` | **Close the body**, not just call `future.cancel(true)` | A completed future does not replace ownership of the body |

A response body may have an indeterminate length (`Transfer-Encoding: chunked` in HTTP/1.1, HTTP/2 streaming, server-sent events). **Without a byte limit, deadline, and business need**, “read to EOF” can wait forever or occupy the network unnecessarily. Use timeouts/deadlines, max body bytes, and clear cancel/close policies.

## 3. `BodyHandlers.ofInputStream()`: Always Handle via `try-with-resources`

The Java 17 Javadoc states explicitly: to release the HTTP exchange’s resources, the caller must **read all bytes to EOF** or **call `InputStream.close()`** if it cannot or does not want to read to completion. Closing before EOF may cause the underlying HTTP connection to be closed and not reused.

Correct pattern when the body is still needed:

~~~java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] buffer = new byte[8192];
    int n;
    while ((n = body.read(buffer)) != -1) {
        processBytes(buffer, 0, n);
    }
}
// Reached EOF; try-with-resources still closes if processBytes throws.
~~~

This is an **illustrative snippet, not standalone runnable**: it assumes `java.io.*`, `java.net.http.*` are imported and `client`, `request`, `processBytes` exist. `processBytes` is a business logic method. The key lesson is that **close resides in lexical scope**, so even if the parser throws an exception, the loop breaks, or the caller returns, the stream is still closed.

### 3.1. Only `read() == -1` Means EOF

`InputStream.read(byte[])` returns:
- a positive number of bytes when data is available;
- `-1` when EOF is reached;
- may block when no data is available yet;
- throws `IOException` on I/O/connection error.

`body.available() == 0` **does not prove EOF**; `available()` only estimates the number of bytes that can be read without blocking. Do not write:

~~~java
while (body.available() > 0) {
    body.read(buffer);
}
// WRONG: may stop early when the network has not delivered all DATA yet.
~~~

If you need to verify completion, you must read until `-1` or until the terminal signal per the API. Do not treat `Content-Length` in headers as sole proof that all data was received: the response may lack that header, use transfer encoding, experience a dropped connection, or have other framing/transfer semantics. When integrity is required, verify with a dedicated protocol/size/checksum check.

### 3.2. Cap Bytes Before Processing

To defend against untrusted or oversized response bodies:

~~~java
long maxBytes = 10L * 1024 * 1024;
long total = 0;
byte[] buffer = new byte[8192];

try (InputStream body = response.body()) {
    int n;
    while ((n = body.read(buffer)) != -1) {
        if (n > maxBytes - total) {
            throw new IOException("Body exceeds 10 MiB limit");
        }
        total += n;
        processBytes(buffer, 0, n);
    }
}
~~~

This is **pseudocode inside a Java method**, with assumed `response`/`processBytes`. Using `n > maxBytes - total` avoids addition overflow when counts could be large. When the cap is exceeded, throwing an exception causes `try-with-resources` to **close the body early**. Do not keep draining several gigabytes just to keep a connection reusable.

For JSON/XML/ZIP parsers, separate caps may need to be placed on **bytes transferred**, **decompressed bytes**, **object count/nesting level**, or file size. A 10 MiB limit on received bytes does not by itself prevent decompression bombs or CPU-exhausting parses.

### 3.3. Avoid `readAllBytes()` on Unbounded Sources

~~~java
byte[] all = response.body().readAllBytes(); // easily exceeds heap if body is large
~~~

The snippet above both risks accumulating too much data and **does not show close**. Even if a small body has a verified limit, `try-with-resources` is still required. For bodies that could be very large, use chunked reads or `BodyHandlers.ofFile(...)` with quotas and file cleanup. `readNBytes(k)` only reads **at most k bytes**, and does not imply that the entire response has completed.

## 4. Early `close()`: Intentionally Discarding the Body, No Reuse Guarantee

When you only need headers/status or the first few bytes:

~~~java
HttpResponse<InputStream> response =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = response.body()) {
    byte[] prefix = body.readNBytes(8);
    usePrefix(prefix);
}
// If body remains: close has been called; the exchange is not abandoned.
~~~

This snippet is **illustrative**; `usePrefix` is an application-defined method. `close()` does not mean “the server stops sending at the exact instant that Java line executes”; cancellation may be performed **asynchronously/best-effort** depending on the implementation and network state. You must not assert that the underlying TCP connection is definitely still alive or definitely closed.

### 4.1. Why Can Early Close Lose Keep-Alive?

An HTTP connection can be reused when the library has finished resolving the previous message and it still fits the pooling policy. With HTTP/1.1 keep-alive, if the body has not been fully read, unconsumed bytes may still be sitting on the same TCP stream; the implementation may **close the connection** instead of keeping it for the next request, avoiding byte mix-ups. With HTTP/2, a connection carries multiple independent streams, so cancelling one stream can result in resetting that stream without necessarily closing the entire connection. However, **the JDK 17 Javadoc only promises the possibility**, not exact protocol-specific reuse after every kind of cancellation.

- **Consuming to EOF** ends the exchange cleanly and *gives an opportunity* to reuse the connection.
- **Early close** releases the responsibility of reading the body but *may* forfeit reuse.
- **Neither closing nor consuming** is a resource retention risk, not a keep-alive strategy.

Do not force downloading a huge body just to save one TCP/TLS handshake; choose based on actual cost and SLA.

### 4.2. `close` Does Not Mean Releasing All Application Resources

When a parser holds references to `byte[]`, connection-level queues, temp files, worker tasks, or caches, closing the body stream **does not automatically clean up** those other application resources. Always design explicit owners for:
- input stream;
- output file/temporary file;
- decoder/parser;
- task/`CompletableFuture`;
- queued buffers;
- network request deadline.

Closing the stream does not mean releasing the `HttpClient` object in the sense of having to call `HttpClient.close()` on Java 17. **Java 17 `HttpClient` does not provide `close()` as an official API**; managing ownership of each streaming body is the central point.

## 5. HTTP Error Responses Still Have Bodies to Handle

A common design mistake:

~~~java
HttpResponse<InputStream> r =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

if (r.statusCode() >= 400) {
    throw new IOException("HTTP error " + r.statusCode());
}
// WRONG: exits early without closing r.body().
~~~

Calling `send` with `ofInputStream()` may already have returned a response body stream even for status codes `404`, `429`, or `500`. Throwing an exception before retrieving/closing the body leaves the exchange abandoned.

Correct pattern:

~~~java
HttpResponse<InputStream> r =
        client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (InputStream body = r.body()) {
    int status = r.statusCode();
    if (status >= 400) {
        byte[] detail = body.readNBytes(4096);
        logSafeError(status, detail);
        // After this point the body may not be at EOF; try still closes it.
        throw new IOException("HTTP " + status);
    }
    consumeSuccess(body);
}
~~~

This is **application pseudocode**: `logSafeError` and `consumeSuccess` are undefined, and a policy is needed to avoid logging secrets/PII. `readNBytes(4096)` limits the amount **stored for logging**, but the application must have a deadline to avoid hanging on a slow server while reading. If the error body is not needed, still capture the body in `try` and close it immediately. There is no `HttpResponse.getErrorStream()` in `java.net.http.HttpClient`; that is a different API from `HttpURLConnection`.

Note: `204 No Content`, `304 Not Modified`, or responses to `HEAD` have HTTP semantics with no body. With a streaming `BodyHandler`, the consistent practice is still to **own/close the returned body object** when present; an empty EOF is valid. Do not rely on a status being “guaranteed empty” to skip generic cleanup.

## 6. `BodyHandlers.ofLines()`: `Stream<String>` Also Needs `close()`

`ofLines()` returns `HttpResponse<Stream<String>>`; each line is decoded as the body is read. This is a **resource-backed stream**, not a `List<String>` preloaded upfront. It must be **exhausted** or **closed** per the `BodySubscribers.ofLines` Javadoc.

Example:

~~~java
HttpResponse<Stream<String>> r =
        client.send(request, HttpResponse.BodyHandlers.ofLines());

try (Stream<String> lines = r.body()) {
    lines.forEach(System.out::println); // runs to completion if no error
}
~~~

This is an illustrative snippet; import `java.util.stream.Stream`. If the stream errors while decoding/receiving or the consumer throws an exception, `try-with-resources` still closes it. Do not invoke parallel operations on the same body stream unless the library/source stream guarantees support for it.

### 6.1. `limit(2)` and `findFirst()` Do Not Mean Fully Read

~~~java
try (Stream<String> lines = response.body()) {
    List<String> firstTwo = lines.limit(2).toList();
    handle(firstTwo);
}
~~~

If the server sends 10,000 lines, `limit(2)` is a **short-circuiting terminal operation**; it only takes the first two lines and can leave a large number of bytes unread. The `try` block calls `lines.close()` on exit, cleaning up the streaming body's resources. `findFirst()`, `anyMatch()`, and `takeWhile()` can also stop early. **A completed terminal operation does not by itself prove the underlying HTTP body reached EOF**.

`Stream.close()` is a separate action: reading the stream to completion is one event, closing the resource is another; this lesson recommends using `try-with-resources` for all processing paths to stay safe on exceptions or short-circuits.

### 6.2. Charset and Line Length

`BodyHandlers.ofLines()` obtains the charset from the response headers per the Javadoc; if the charset is absent/unsuitable, the handler's default policy applies. **Reading line by line does not mean each line is small**. A single very long line with no delimiter can still consume large amounts of memory. For untrusted data, consider a parser that caps characters/bytes per line, total line count, and total body size, or a custom `BodySubscriber`.

Do not take the `Stream<String>` returned from a response and cache it for “later” processing without lifetime rules; a task could hold the network exchange open for minutes. Transfer ownership explicitly, set deadlines, and close within the exact task responsible for consumption.

## 7. `BodyHandlers.ofPublisher()`: Subscribe Once, Terminal or Cancel

`ofPublisher()` produces `HttpResponse<Flow.Publisher<List<ByteBuffer>>>`. This response is ready **after headers**, and the publisher delivers the body via the `Flow` mechanism. From the Java 17 Javadoc:

- A response's publisher **may only be `subscribe`d to once**.
- The caller must **subscribe** and request data until `onComplete`/`onError` **or** call `subscription.cancel()` when stopping early.
- `onSubscribe(Flow.Subscription)` provides the subscription that the subscriber uses to `request(n)` and `cancel()`.
- `onNext(List<ByteBuffer>)` receives **one item containing a list of buffers**. `request(1)` asks for one **item**, not 1 byte.
- When calling `cancel()`, you may **not receive `onComplete` or `onError`**; cancellation is best-effort and in-flight data signals may still arrive per the `Flow` contract.

Logic example:

~~~java
publisher.subscribe(new Flow.Subscriber<List<ByteBuffer>>() {
    private Flow.Subscription subscription;

    @Override public void onSubscribe(Flow.Subscription s) {
        this.subscription = s;
        s.request(1);
    }
    @Override public void onNext(List<ByteBuffer> buffers) {
        processBuffers(buffers); // must handle/retain ownership properly
        if (stillNeeded()) {
            subscription.request(1);
        } else {
            subscription.cancel();
        }
    }
    @Override public void onError(Throwable error) {
        reportError(error);
    }
    @Override public void onComplete() {
        reportCompleted();
    }
});
~~~

This is **pseudocode**, because `publisher`, `processBuffers`, `stillNeeded`, `reportError`, and `reportCompleted` are application components. The Java syntax is valid for an anonymous subscriber when `publisher` has the appropriate type and `java.nio.ByteBuffer`, `java.util.List`, `java.util.concurrent.Flow` are imported.

**Important:** if the caller obtains the publisher but never `subscribe`s, it does not drive the flow enough to finish the body. If it subscribes without calling `request(n)`, the flow may stall permanently. If it stops processing without `cancel()`, the exchange may retain resources. And **do not wait for `onComplete` after cancel** because the Flow contract does not guarantee that signal will occur.

### 7.1. `onError` Is Also Terminal

In a failure at the network layer, `onError` is a terminal signal; do not call `request` again. Distinguish:
- HTTP status code `500` is a **normal HTTP response at the transport level** and may have a body, not automatically an `onError`.
- A subscriber's `onError` is an error in the stream/transport/subscriber processing.
- `onComplete` means the publisher finished sending items per the contract, not that the application's business operation succeeded.

Do not let an unchecked exception thrown from `onNext` leave the subscriber in a state without cleanup; design the handler to catch it and transition to cancel/report per policy.

### 7.2. Ownership of `List<ByteBuffer>` Is Required

`BodySubscriber` receives an ordered list of `ByteBuffer`s representing the response body. When retaining references for async processing, define who owns the buffers, who is allowed to mutate `position/limit`, whether copies are made when handing off to workers, memory caps, and how backpressure is signaled upstream. Do not accumulate every `List<ByteBuffer>` into an unbounded `ArrayList` when downstream is slow. Only call `request(1)` after finishing the current item or enqueuing it in a bounded queue; do not blindly call `request(Long.MAX_VALUE)`.

## 8. Async `sendAsync` Cancellation Differs from Closing the Body After Future Completion

Java 17 Javadoc for `HttpClient.sendAsync`: the default implementation returns a `CompletableFuture` that supports cancellation. If the `future` **has not completed yet**, `future.cancel(true)` attempts to cancel the HTTP exchange to release resources **as soon as possible**, though there is **no guarantee of the exact moment** cancellation takes effect.

- With HTTP/1.1, cancelling may cause the underlying connection to be closed abruptly.
- With HTTP/2, cancelling may cause a stream reset rather than closing the entire connection.
- The request may already have been sent and processed by the server before cancellation arrives. **Cancel does not undo the side effects of POST/PUT**.

Example:

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

if (userCancelledBeforeResponse) {
    future.cancel(true);
}
~~~

This snippet is **illustrative**: `userCancelledBeforeResponse` is an undefined application state. Once the future **has completed** with `HttpResponse<InputStream>`, the caller/continuation is the owner of `response.body()`. Cancelling an already-completed future **does not replace closing the body stream**. For streaming responses, the future can complete as soon as the headers are read, making this especially important.

### 8.1. Safe Async Pattern: The Continuation Owns the Stream

~~~java
CompletableFuture<HttpResponse<InputStream>> future =
        client.sendAsync(request, HttpResponse.BodyHandlers.ofInputStream());

CompletableFuture<Long> processed = future.thenApplyAsync(response -> {
    try (InputStream body = response.body()) {
        long total = 0;
        byte[] chunk = new byte[8192];
        int n;
        while ((n = body.read(chunk)) != -1) {
            total += n;
            processChunk(chunk, n);
        }
        return total;
    } catch (IOException ex) {
        throw new UncheckedIOException(ex);
    }
}, dedicatedBodyExecutor);
~~~

This is **pseudocode with dependencies**: `client`, `request`, `processChunk`, and `dedicatedBodyExecutor` are provided by the application. Reading a network body can **block**, so do not pile hundreds of response-consuming continuations onto an undersized executor or an event-loop/selector thread. Use a bounded executor/work queue and backpressure, timeouts/deadlines, and protect tasks that are cancelled while still owning a stream.

An advanced point: if `thenApplyAsync` never executes because of cancellation/race/executor rejection after the response is already ready, the application needs a mechanism for **ownership handoff and cleanup** of the returned body. In production code, enforce queue limits before accepting workload, or use a callback/response manager that guarantees **every received response has an owner closing the body**. Simply “attaching a callback” does not guarantee zero leaks.

### 8.2. Interrupted `HttpClient.send` and Resource Release

With synchronous `send`, if the thread is interrupted, the default implementation attempts to cancel the exchange and throws `InterruptedException`. The Java 17 Javadoc warns that the HTTP exchange may already have been sent; release may be asynchronous. At the application layer:

~~~java
try {
    // send + consume inside try-with-resources as above
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    // propagate/abort per policy; do not swallow the interrupt.
}
~~~

This is an **illustrative** snippet with the `try` body filled in by the caller. A cancel/interrupt does not guarantee the server has not processed the request; an idempotency token/correlation ID is needed if business retries have side effects.

## 9. Choosing the Right `BodyHandler` Upfront to Reduce Cleanup Burden

Choose a handler that matches your actual needs, avoiding receiving a streaming body if there is no clear consumer:

| Need | Appropriate BodyHandler | Notes |
| --- | --- | --- |
| Only need status + headers, finite response body can be discarded | `BodyHandlers.discarding()` | Consumes and discards without accumulating on the heap; **still receives bytes** |
| File download | `BodyHandlers.ofFile(path)` | Downloads and writes file before completing the response; manage quota/path/partial files |
| Small payload with clear bounds | `ofByteArray()` or `ofString()` | Memory risk if the server sends too much |
| Stream bytes to parse/forward | `ofInputStream()` | Caller reads to EOF or closes |
| Log lines/line-oriented NDJSON | `ofLines()` | Exhaust or close, plus add a line-size limit |
| Reactive pipeline needing demand | `ofPublisher()` | Subscribe exactly once; terminal or cancel |
| Need to pick handler by status/headers | Custom `BodyHandler<ResponseType>` | Can select `BodySubscribers.discarding()` for certain statuses |

### 9.1. `discarding()` Is Not the Same as Cancelling a Request

~~~java
HttpResponse<Void> response =
        client.send(request, HttpResponse.BodyHandlers.discarding());
System.out.println(response.statusCode());
~~~

This snippet is **illustrative**. With the default `discarding` handler, the response is returned after the body has been consumed and discarded. If the server streams for hours, `discarding` can also take hours. Therefore:
- If you know upfront the response is small and you do not need the body: `discarding` is reasonable.
- If the body could be unbounded/huge and you do not need the content: have a **cancel/close policy**, do not try to “discard everything”.
- If you only need to inspect the status and decide after headers arrive: a `BodyHandler` can choose a subscriber based on `ResponseInfo`; note that choosing `discarding` still consumes the body.

### 9.2. `ofFile` and Incomplete Files

`BodyHandlers.ofFile(path)` completes the response after the body has been written to the file; when the application uses `HttpResponse<Path>`, it no longer has an unread `InputStream` to close. However, the file may contain partial content if the download fails before completion, and it can consume disk/quota. For important downloads:
1. Create a safe temporary path (do not take arbitrary paths from untrusted sources).
2. Cap download size, timeout, permissions, and disk quota.
3. Verify status, length/checksum/signature as appropriate.
4. Only publish/rename the file once the download is complete and verified.
5. Delete the temporary file on error/cancel.

That is the **output file lifecycle**, which is not solved by `response.close()`.

## 10. Complete Java 17+ Example 1: Reading to EOF, Error Body, Closing Lines, and Early Close

The program below runs **entirely on loopback** using `com.sun.net.httpserver.HttpServer` from the JDK `jdk.httpserver` module. It creates four endpoints:
- `/small`: small content, client reads to EOF in chunks.
- `/missing`: status 404 and error body, client still consumes/closes.
- `/lines`: three lines, client only needs the first two lines and closes `Stream<String>`.
- `/large`: larger body, client reads only 8 bytes and closes early.

No Internet, DNS, or external server is needed. **The example does not attempt to claim that the underlying HTTP TCP socket is reused after an early close**; that detail depends on the implementation.

Create **`HttpBodyInputStreamDemo.java`**:

~~~java
import com.sun.net.httpserver.*;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;
import java.util.stream.*;

public final class HttpBodyInputStreamDemo {
    private static void reply(HttpExchange exchange, int status,
                              byte[] bytes) throws IOException {
        exchange.getResponseHeaders().set(
                "Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(status, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    private static HttpRequest get(URI base, String path) {
        return HttpRequest.newBuilder(base.resolve(path))
                .timeout(Duration.ofSeconds(5)).GET().build();
    }

    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(loopback, 0), 0);

        server.createContext("/small", e ->
                reply(e, 200,
                        "alpha\nbeta\n".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/missing", e ->
                reply(e, 404,
                        "not-found".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/lines", e ->
                reply(e, 200,
                        "one\ntwo\nthree\n".getBytes(StandardCharsets.UTF_8)));
        server.createContext("/large", e -> {
            e.sendResponseHeaders(200, 0);
            try (OutputStream out = e.getResponseBody()) {
                byte[] block = new byte[8192];
                Arrays.fill(block, (byte) 'X');
                for (int i = 0; i < 64; i++) out.write(block);
            } catch (IOException expectedWhenClientStopsEarly) {
                // Early client close may abort the server-side write.
            }
        });

        server.start();
        try {
            URI base = new URI("http", null,
                    loopback.getHostAddress(),
                    server.getAddress().getPort(),
                    "/", null, null);

            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5)).build();

            HttpResponse<InputStream> full = client.send(
                    get(base, "/small"),
                    HttpResponse.BodyHandlers.ofInputStream());

            ByteArrayOutputStream collected =
                    new ByteArrayOutputStream();
            long count = 0;
            try (InputStream body = full.body()) {
                byte[] buf = new byte[4];
                int n;
                while ((n = body.read(buf)) != -1) {
                    count += n;
                    collected.write(buf, 0, n);
                }
            }
            System.out.println(
                    "full status: " + full.statusCode());
            System.out.println("full bytes: " + count);
            System.out.println("full text: " +
                    collected.toString(StandardCharsets.UTF_8)
                            .replace("\n", "|"));

            HttpResponse<InputStream> error = client.send(
                    get(base, "/missing"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = error.body()) {
                System.out.println(
                        "error status: " + error.statusCode());
                System.out.println("error text: " +
                        new String(body.readAllBytes(),
                                StandardCharsets.UTF_8));
            }

            HttpResponse<Stream<String>> lines = client.send(
                    get(base, "/lines"),
                    HttpResponse.BodyHandlers.ofLines());
            try (Stream<String> bodyLines = lines.body()) {
                System.out.println(
                        "first lines: " +
                        bodyLines.limit(2).toList());
            }

            HttpResponse<InputStream> large = client.send(
                    get(base, "/large"),
                    HttpResponse.BodyHandlers.ofInputStream());
            try (InputStream body = large.body()) {
                System.out.println(
                        "early bytes: " +
                        body.readNBytes(8).length);
            }
            System.out.println("early body closed: true");
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 HttpBodyInputStreamDemo.java
java HttpBodyInputStreamDemo
~~~

When the JDK's loopback HTTP server is working, **the exact verified stdout** is:

~~~text
full status: 200
full bytes: 11
full text: alpha|beta|
error status: 404
error text: not-found
first lines: [one, two]
early bytes: 8
early body closed: true
~~~

Points to explain:

1. `/small` returns exactly 11 UTF-8 bytes: `"alpha\nbeta\n"`. The read buffer array is only 4 bytes, but the loop runs to EOF and `collected.write(buf,0,n)` preserves all data in the right order.
2. `ByteArrayOutputStream` is used **only in the demo with a known small payload**, not as advice to collect unbounded bodies in production.
3. HTTP 404 does not automatically throw `IOException` when transport is normal; the body still contains `"not-found"` and is read inside `try`.
4. `body.readAllBytes()` in the error branch is safe **in this test because the server produces exactly 9 bytes**; for external endpoints, use limits/chunked reads.
5. `ofLines` returns the response while the body may still be incomplete; `limit(2)` does not prove all three lines were read. `try` ensures `Stream.close()`.
6. `/large` is created with a chunked response; the caller reads only 8 bytes and closes the body. The server may see an `IOException` when the client stops, which is caught so the example does not clutter stdout.
7. `early body closed: true` describes that **the code has exited the try-with-resources block**; it does **not** measure connection reuse and does not claim all network buffers were freed in a single nanosecond.
8. The bind port is 0 so the OS picks a free port; the host comes from `InetAddress.getLoopbackAddress()` (which may be IPv4 or IPv6). There is no hard-coded external endpoint.

If run in a sandbox that disallows binding loopback, the example may throw a network exception instead of the stdout above. `jdk.httpserver` is included in standard JDKs; a custom runtime image that excludes this module will not run the class. In real applications, add body size limits, request deadlines, accurate exception logging, and do not swallow server I/O errors if they represent critical business data. Here, the server write error is intentionally ignored because the client **deliberately closed early**.

## 11. Complete Java 17+ Example 2: Reactive Publisher, Terminal, and Cancel

The second example demonstrates **two lifecycle branches of `BodyHandlers.ofPublisher()`**:
- `/all`: the subscriber requests 1 item at a time, consumes all 8,192 bytes, and receives `onComplete`.
- `/early`: the subscriber requests 1 item and then calls `subscription.cancel()` immediately upon receiving the first item; **it does not wait for `onComplete`**.

The program keeps separate state per subscriber and uses `CountDownLatch` to ensure the test has a timeout. **A `Flow.Publisher` returned from a response can only be subscribed to once**; we create two separate HTTP responses for the two tests.

Create **`HttpPublisherLifecycleDemo.java`**:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.io.*;
import java.net.*;
import java.net.http.*;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class HttpPublisherLifecycleDemo {
    private static final class Receiver
            implements Flow.Subscriber<List<ByteBuffer>> {
        private final boolean stopEarly;
        private final CountDownLatch done = new CountDownLatch(1);
        private final AtomicLong count = new AtomicLong();
        private volatile Flow.Subscription subscription;
        private volatile boolean complete;
        private volatile boolean cancelRequested;
        private volatile Throwable error;

        Receiver(boolean stopEarly) {
            this.stopEarly = stopEarly;
        }

        @Override public void onSubscribe(Flow.Subscription s) {
            subscription = s;
            s.request(1);
        }

        @Override public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer b : buffers) {
                count.addAndGet(b.remaining());
            }
            if (stopEarly) {
                cancelRequested = true;
                subscription.cancel();
                done.countDown(); // cancel does not promise onComplete
            } else {
                subscription.request(1);
            }
        }

        @Override public void onError(Throwable t) {
            error = t;
            done.countDown();
        }

        @Override public void onComplete() {
            complete = true;
            done.countDown();
        }

        void await() throws Exception {
            if (!done.await(5, TimeUnit.SECONDS)) {
                Flow.Subscription s = subscription;
                if (s != null) s.cancel();
                throw new IOException("Timed out waiting for body");
            }
            if (error != null) {
                throw new IOException("Body failed", error);
            }
        }
    }

    private static void serve(
            com.sun.net.httpserver.HttpExchange e,
            int chunks) throws IOException {
        e.sendResponseHeaders(200, chunks * 8192);
        try (OutputStream out = e.getResponseBody()) {
            byte[] block = new byte[8192];
            Arrays.fill(block, (byte) 'X');
            for (int i = 0; i < chunks; i++) {
                out.write(block);
            }
        } catch (IOException expectedIfCancelled) {
            // The client may stop reading before the server finishes sending.
        }
    }

    public static void main(String[] args) throws Exception {
        InetAddress host = InetAddress.getLoopbackAddress();
        HttpServer server = HttpServer.create(
                new InetSocketAddress(host, 0), 0);
        server.createContext("/all", e -> serve(e, 1));
        server.createContext("/early", e -> serve(e, 64));
        server.start();

        try {
            URI base = new URI("http", null,
                    host.getHostAddress(),
                    server.getAddress().getPort(),
                    "/", null, null);
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(5))
                    .build();

            Receiver full = new Receiver(false);
            HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                    completeResponse =
                    client.send(
                        HttpRequest.newBuilder(base.resolve("/all"))
                                .GET().build(),
                        HttpResponse.BodyHandlers.ofPublisher());

            completeResponse.body().subscribe(full);
            full.await();
            System.out.println("full bytes: " + full.count.get());
            System.out.println("full completed: " + full.complete);

            Receiver early = new Receiver(true);
            HttpResponse<Flow.Publisher<List<ByteBuffer>>>
                    earlyResponse =
                    client.send(
                        HttpRequest.newBuilder(base.resolve("/early"))
                                .GET().build(),
                        HttpResponse.BodyHandlers.ofPublisher());

            earlyResponse.body().subscribe(early);
            early.await();
            System.out.println(
                    "early received bytes: " +
                    (early.count.get() > 0));
            System.out.println(
                    "early cancel requested: " +
                    early.cancelRequested);
        } finally {
            server.stop(0);
        }
    }
}
~~~

~~~bash
javac --release 17 HttpPublisherLifecycleDemo.java
java HttpPublisherLifecycleDemo
~~~

When loopback is working, **verified stdout**:

~~~text
full bytes: 8192
full completed: true
early received bytes: true
early cancel requested: true
~~~

**Do not over-interpret:**
- `full completed: true` confirms `onComplete` during the full read; it is not proof that the HTTP business operation succeeded — status/validation is still required.
- `early cancel requested: true` confirms `subscription.cancel()` was called; it does **not** promise a terminal signal or confirm that the TCP socket closed at that exact moment.
- `early received bytes: true` only guarantees the first item contained data in the test; the size of a `List<ByteBuffer>` is implementation-dependent, so the program does not assert an exact byte count for the early branch.
- `request(1)` requests one **`onNext` item**, not one byte and not the equivalent of HTTP/2 `WINDOW_UPDATE(+1)`.
- In the example, `Receiver.await()` counts down immediately on the cancel branch, **deliberately not waiting for `onComplete`** because cancel does not force the publisher to emit a terminal signal.
- `AtomicLong` and `volatile` are used to share state between the HTTP client callback thread and the main test thread; `CountDownLatch` provides the completion mechanism. In production, a bounded downstream queue and cancellation on error/timeout are still required.
- `server.stop(0)` shuts down the test server in `finally`; no external Internet requests are made.

## 12. When Should You “Drain for Reuse”?

Some people write:

~~~java
try (InputStream body = response.body()) {
    body.transferTo(OutputStream.nullOutputStream());
}
~~~

This is an **illustrative snippet**: it reads to EOF and discards the data. The usual goal is to help the connection be reused. However, it **still downloads the entire response**. With a 1 GiB body or a continuous server stream, this can consume minutes/hours, bandwidth, battery/CPU, and may never reach EOF.

Practical decision rules:

- If the body is **nearly finished**, has a known small size, and has a deadline, draining can be reasonable.
- If the body is **large, unknown, or slow/stalled**, **close/cancel** is usually safer to protect resources, even at the cost of losing connection reuse.
- Do not rely solely on `Content-Length` to decide: the server may omit the header, use compression, or report an untrustworthy length. Always include **bytes actually received** and **max remaining drain time** in your policy.
- If the response is truly not needed upfront and the server sends a small finite body, choose `BodyHandlers.discarding()` so the library consumes/discards it; do not create a stream and forget it.

`InputStream.transferTo(...)` is from Java 9+, and `OutputStream.nullOutputStream()` is from Java 11+, so the syntax is valid in Java 17. However, “valid syntax” does not make it suitable for every workload.

## 13. HTTP/1.1 vs. HTTP/2: Resource Reuse Differs, Cleanup Is the Same

A request-response exchange with an unfinished body can hold onto resources such as:
- parser state, chunked framing, or HTTP/2 stream state;
- TCP/TLS connection and buffers;
- flow-control demand, publisher/subscriber, or `InputStream` queue;
- worker/selector tasks;
- pooled connection slot or HTTP/2 stream capacity.

**With HTTP/1.1**, the response body lives directly in the TCP byte stream. If the app stops reading early, the connection may not be reused because the exact response boundary must be known before reusing it. **With HTTP/2**, DATA for multiple streams carries distinct stream IDs, allowing a single stream to be cancelled via reset; the connection can still serve other streams. Both protocols have situations where the implementation chooses to close the connection due to error/cancel, and the Java 17 Javadoc **does not guarantee** that every close/cancel only affects a single stream.

Protocol differences **do not change the ownership rule**: `InputStream` must be read to EOF or closed, `Stream<String>` must be exhausted or closed, and a publisher must reach a terminal signal or be cancelled. Do not leave an unfinished body around just because “HTTP/2 multiplexes so it probably won’t affect others.”

### 13.1. Closing a Body Is Not the Same as `HttpClient.close()`

In Java 17, `HttpClient` is a configuration object that shares resources across many requests; this version's API does not provide a standard `close()` method to replace per-response cleanup. Do not infer from newer JDK docs and call the wrong method when targeting `javac --release 17`.

Later, if you use a JDK version with different lifecycle APIs, still read the contract for that exact version; individual body resources still need to be handled according to the body handler. Never adopt a “wait for GC to clean it up” rule in any version.

## 14. Differences from the Legacy `HttpURLConnection`

In projects still using `java.net.HttpURLConnection`, the response body is usually read from `getInputStream()` (on success) or `getErrorStream()` (potentially available on HTTP error). This is a different API from `java.net.http.HttpClient`.

**Illustrative** pattern, not standalone runnable:

~~~java
HttpURLConnection con = (HttpURLConnection) url.openConnection();
con.setConnectTimeout(5000);
con.setReadTimeout(5000);

try {
    int status = con.getResponseCode();
    InputStream source =
            status >= 400 ? con.getErrorStream() : con.getInputStream();

    if (source != null) {
        try (InputStream body = source) {
            consumeWithLimit(body);
        }
    }
} finally {
    con.disconnect();
}
~~~

Here `url` and `consumeWithLimit` are caller-provided components. `getErrorStream()` **may return `null`** even when the status is an error. The `HttpURLConnection` Javadoc states that an instance is typically used for one request, but the underlying persistent HTTP connection may be shared transparently across instances. Calling `InputStream.close()` may release resources belonging to the instance; `disconnect()` may close the underlying socket when idle and is not guaranteed to tear down every shared persistent connection.

Do not use `con.disconnect()` to explain the new `HttpClient` — they are two different APIs. The main part of this lesson uses `java.net.http.HttpClient` because its body handlers clearly separate stream/subscriber ownership.

## 15. Backpressure, Timeouts, and Resource Limits

A streaming response is not just “read or don’t read.” With many concurrent requests, you need to limit:

- **Maximum response size**: actual bytes and post-decode/decompression bytes where appropriate.
- **Per-chunk size**: temporary buffers allocated in the loop.
- **Per-request deadline**: time for headers plus total body processing time, with a stop/close policy on expiry.
- **Idle read deadline**: if the peer sends no further bytes within the allowed time, stop the request instead of blocking indefinitely.
- **Concurrent responses/streams**: semaphore/bounded task queue; do not spawn unbounded `sendAsync` calls.
- **Downstream capacity**: if the parser/file/DB is too slow, pause demand or close the body; do not enqueue unboundedly.
- **Disk quota**: with `ofFile` and download streams, avoid filling the disk.

An `HttpRequest.Builder.timeout(...)` has meaning per the `HttpClient`/request contract, but **should not be treated as an all-encompassing application deadline covering arbitrary `InputStream.read` operations after the streaming response has been returned**. Add progress monitoring, a separate deadline, and a way to close/cancel if the body is no longer worth continuing.

### 15.1. Do Not Abuse Blocking on the HTTP Client Executor

The `BodySubscribers.mapping(...)` Javadoc warns that the mapper runs on the client's executor. If the mapper **reads a blocking `InputStream` to completion** right inside the callback, it can occupy a worker thread for a long time and cause executor starvation. Similarly, writing a custom subscriber whose `onNext` blocks on I/O or DB for long periods can destroy throughput.

Options:
- Consume blocking `InputStream` on a bounded dedicated executor.
- Use `BodyHandler.ofFile`/a streaming parser if appropriate.
- For reactive pipelines, use `request(1)` or finite demand and bounded queues; when processing capacity is exhausted, call `cancel()`.
- When transferring ownership to a worker task, verify the task is accepted and has guaranteed cleanup even if the executor shuts down/rejects it.

### 15.2. Cancel Does Not Solve Business Correctness

HTTP GET can often be retried per policy, but POST/PUT have side effects that may already have been executed by the server before the client cancelled. If a request is cancelled mid-flight:
- Do not assert “the server definitely did not process it.”
- Use an idempotency key/transaction semantics/correlation ID if retries exist.
- Record cancellations separately from HTTP error responses; a 500 status with a body is not the same as a network cancel.
- Do not report “download complete” if the body was closed/cancelled before EOF.

## 16. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Read status then return, abandoning `InputStream` | Response body is still pending; resource retention | `try (InputStream in = response.body()) { ... }` |
| Use `available()==0` as EOF | Does not prove the peer finished sending | Read until `read()==-1` or close |
| Call `readNBytes(100)` and assume response is done | Only reads at most 100 bytes | Close if the remainder is not needed |
| `lines.limit(2).toList()` then abandon `Stream` | Short-circuit; body may not be fully read | `try (Stream<String> lines = r.body())` |
| `publisher` returned but never subscribed to | Unconsumed; exchange may retain resources | Subscribe exactly once, request to terminal or cancel |
| Subscribe to publisher twice | `ofPublisher` only allows one subscriber | Split response/stream if fan-out is needed; do not re-subscribe |
| Call `subscription.request(0)` | Invalid; Flow specifies `onError` | Request a positive number of items |
| Call cancel then wait forever for `onComplete` | Terminal signal after cancel is not guaranteed | Clean up on a separate cancel branch |
| `sendAsync` future already completed, then `cancel(true)` and drop body | Future cancellation does not replace stream close | Retrieve `response.body()` and close/cancel |
| On HTTP 404/500, just throw an exception | Error response still has a body | Consume bounded error detail or close |
| Use `discarding()` on an infinite body to “cancel” | Discarding still receives the body | Cancel/close appropriately when you do not want to continue |
| `readAllBytes()` on untrusted body | Could accumulate a huge response | Chunked processing + max bytes |
| Always drain huge bodies to keep keep-alive | Can waste bandwidth/hang | Capped drain, or close early |
| Use `HttpResponse.close()` | Java 17 `HttpResponse` has no such method | Close the streaming body itself |
| Use `HttpClient.close()` in Java 17 | Not a standard API in JDK 17 | Manage per-response resources |
| Assume close guarantees the TCP socket closes immediately | Cancel may be async; semantics differ for HTTP/1.1 and HTTP/2 | Record intent to close; do not fabricate socket state |
| Pass `InputStream` body to a task that never runs | Lost owner, resource retention | Bounded executor + guaranteed cleanup |
| Attach exception logging containing the full error body | May leak secrets/PII and spike memory | Limit and sanitize logs |

## 17. Self-Check Exercises

**Q1.** If `HttpResponse<InputStream>` is returned after `send()`, is the body guaranteed to be at EOF?  
**Answer:** No. `ofInputStream` returns the response after headers; the caller must continue reading the body or close it.

**Q2.** A caller reads only the first 10 bytes of a 100 KiB response and returns. What is missing?  
**Answer:** The `InputStream` must be closed when the remaining 100 KiB is not needed; `try-with-resources` guarantees cleanup.

**Q3.** Does `body.available()==0` prove the stream has ended?  
**Answer:** No. There may temporarily be no bytes ready while the network still has more to deliver.

**Q4.** With `BodyHandlers.ofLines()`, does calling `limit(1).findFirst()` mean the response has been consumed?  
**Answer:** Not necessarily. This is a short-circuit; `Stream.close()` is needed if not exhausted.

**Q5.** A reactive publisher was just received from `BodyHandlers.ofPublisher()`, and the caller does not `subscribe`. Is it valid to ignore it?  
**Answer:** Not if you want to ensure resources are released; you must subscribe and consume to terminal or cancel.

**Q6.** Does `Flow.Subscription.request(1)` request exactly 1 byte?  
**Answer:** No. It requests 1 more item (one `onNext`), where the item is a `List<ByteBuffer>` of non-fixed byte length.

**Q7.** After `subscription.cancel()`, should you `latch.await` forever waiting for `onComplete`?  
**Answer:** No. Cancellation does not force a terminal signal; clean up separately on cancel.

**Q8.** Calling `future.cancel(true)` after the `sendAsync(...ofInputStream())` future has already returned a response—is that enough cleanup?  
**Answer:** No. You must close/consume the body whose ownership has been transferred.

**Q9.** Does 404 Not Found have `HttpResponse.body()==null` by default?  
**Answer:** No. With `ofInputStream`, a 404 can contain an error body stream; the status does not automatically cause `HttpClient` to throw an HTTP exception.

**Q10.** Does `BodyHandlers.discarding()` stop the network download immediately after headers?  
**Answer:** No. It consumes and discards the body, still incurring transfer cost.

**Q11.** Should you always drain the remaining 1 GiB to reuse a connection?  
**Answer:** No. You must weigh bandwidth/time/memory/deadlines; close/cancel may be more reasonable.

**Q12.** Does closing an HTTP/2 body guarantee resetting only that stream without affecting the connection?  
**Answer:** There is no absolute guarantee from the Java 17 API. Protocols/implementations may handle it differently; premature close can affect reuse.

**Q13.** When using `ofFile` to download a body, is there still a response `InputStream` to close?  
**Answer:** No. The response contains a `Path` after the body has been written; however, you must manage temp files/quotas and error cleanup.

**Q14.** When `processBytes` throws an exception inside the read loop, which pattern guarantees cleanup?  
**Answer:** `try-with-resources` wrapping `response.body()`; the JVM calls `close` on every exit path.

**Q15.** A consumer reads slowly on a small executor and the application creates thousands of streaming responses. Is calling `close` at the end of the task enough?  
**Answer:** No. You need bounded task/connection concurrency, backpressure, deadlines, and ownership handling when tasks are rejected/cancelled.

## 18. Pre-Production Deployment Checklist

1. **Know the body type before calling `send`/`sendAsync`.** Streaming responses have lifetimes extending beyond headers.
2. **Assign ownership of the body as soon as the response is returned.** Never leave an `HttpResponse<InputStream>` abandoned.
3. **`InputStream`:** read to `-1` or close; wrap the entire processing in `try-with-resources`.
4. **`Stream<String>`:** exhaust or close; remember short-circuiting terminal operations are not equivalent to EOF.
5. **`Flow.Publisher`:** subscribe exactly once; request until `onComplete/onError` or cancel; do not wait for a terminal signal after cancel.
6. **Async:** cancel pending futures when the request is no longer needed; once the future completes, clean up **the body separately**.
7. **Error statuses:** read with a limit or close the body on both 2xx and non-2xx.
8. **Do not read indefinitely just for reuse.** Choose a bounded drain or early close based on response size/time budget.
9. **Do not trust `available()`, `Content-Length`, or status as body completion**; measure actual bytes, EOF, and protocol semantics.
10. **Limit memory, body size, concurrency, thread/executor queues, timeouts, and downstream backpressure.**
11. **Distinguish HTTP/1.1 from HTTP/2** when reasoning about reuse/reset; do not predict low-level socket outcomes with certainty.
12. **Release files/temp files/parsers/tasks** separately; do not expect body close to clean up everything else automatically.
13. **Track metrics:** open streaming bodies, bytes read, early closes, cancels, body duration, connection reuse, timeouts, and pending futures.
14. **Test exit paths:** statuses 200/404/500, empty body, short-circuit lines, timeout, mid-stream `IOException`, subscriber cancel, executor rejection, concurrent requests.
15. **Protect logs:** cap error body to N bytes, sanitize PII/secrets, and avoid accidentally logging large payloads.

## Official Java 17 Documentation

- [Java SE 17 — `HttpResponse.BodySubscribers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscribers.html): API Notes on `ofInputStream()` (read to EOF or close), `ofLines(...)` (exhaust or `Stream.close`), and `ofPublisher()` (subscribe once, terminal or cancel).
- [Java SE 17 — `HttpResponse.BodyHandlers`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodyHandlers.html): `ofInputStream`, `ofLines`, `ofPublisher`, `discarding`, `ofFile`, and returning after headers.
- [Java SE 17 — `HttpResponse`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.html): body type, status/headers, and when the response is available.
- [Java SE 17 — `HttpClient`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): `send`/`sendAsync`, cancellation/interrupt, HTTP/1.1 vs. HTTP/2 behavior.
- [Java SE 17 — `HttpResponse.BodySubscriber`](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpResponse.BodySubscriber.html): `Flow.Subscriber<List<ByteBuffer>>`, streaming result completing before the full body.
- [Java SE 17 — `Flow.Subscription`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.Subscription.html): `request(n)` and `cancel()`, best-effort cancellation.
- [Java SE 17 — `InputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): `read`, EOF, `available`, `readNBytes`, `close`.
- [Java SE 17 — `HttpURLConnection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/HttpURLConnection.html): legacy API differences, `getErrorStream`, and `disconnect`.
- [Java SE 17 — `Stream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html): lazy/short-circuit operations and stream resource closure.

**Long-term principle to remember:** **receiving headers does not mean the body has been read; a streaming body does not have the GC as its “owner” for you**. If you still need the data, **read to EOF**; if you do not, **close** (`InputStream`/`Stream`) or **cancel** (`Flow.Subscription`). Place ownership and cleanup on every success, error, timeout, and cancellation branch so you never abandon an HTTP exchange.
